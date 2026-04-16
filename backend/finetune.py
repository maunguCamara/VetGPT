"""
vetgpt/backend/finetune.py

Fine-tuning data pipeline.

Exports high-quality query→answer pairs from QueryLog for fine-tuning
the on-device Qwen2.5-3B model.

Quality filters:
  - RAG score ≥ 0.6 (high-relevance retrieval)
  - Answer length ≥ 100 chars
  - Status = SUCCESS
  - Has at least 1 citation

Output formats:
  - Alpaca JSON  (for llama.cpp / most fine-tuning frameworks)
  - ShareGPT     (for axolotl / FastChat)
  - JSONL        (generic, one record per line)

Routes:
  GET  /api/admin/finetune/export   — export training data (admin only)
  GET  /api/admin/finetune/stats    — dataset statistics
"""

import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import User, QueryLog, QueryStatus, get_db
from .admin_routes import require_admin

finetune_router = APIRouter(prefix="/api/admin/finetune", tags=["fine-tuning (admin)"])

SYSTEM_PROMPT = (
    "You are VetGPT, an AI veterinary reference assistant. "
    "Answer questions for veterinary professionals accurately and concisely, "
    "citing your sources."
)

QUALITY_FILTERS = {
    "min_score":        0.6,
    "min_answer_len":   100,
    "min_chunks":       1,
}


# ─── Export ───────────────────────────────────────────────────────────────────

@finetune_router.get("/export")
async def export_training_data(
    format:     str = Query(default="alpaca",  description="alpaca | sharegpt | jsonl"),
    days:       int = Query(default=30,         ge=1, le=365),
    min_score:  float = Query(default=0.6,      ge=0.0, le=1.0),
    limit:      int = Query(default=5000,       ge=1, le=50000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Export high-quality query/answer pairs as fine-tuning data.
    Returns a downloadable JSONL or JSON file.
    """
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(QueryLog)
        .where(
            QueryLog.created_at   >= since,
            QueryLog.status       == QueryStatus.SUCCESS,
            QueryLog.top_score    >= min_score,
            QueryLog.answer_text  != "",
            QueryLog.chunks_retrieved >= 1,
        )
        .order_by(QueryLog.top_score.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    # Filter by answer length
    logs = [
        log for log in logs
        if len(log.answer_text or "") >= QUALITY_FILTERS["min_answer_len"]
    ]

    if format == "alpaca":
        records = _to_alpaca(logs)
        content = json.dumps(records, indent=2, ensure_ascii=False)
        media   = "application/json"
        fname   = "vetgpt_finetune_alpaca.json"

    elif format == "sharegpt":
        records = _to_sharegpt(logs)
        content = json.dumps(records, indent=2, ensure_ascii=False)
        media   = "application/json"
        fname   = "vetgpt_finetune_sharegpt.json"

    else:  # jsonl
        lines   = [json.dumps(_to_jsonl_record(log), ensure_ascii=False) for log in logs]
        content = "\n".join(lines)
        media   = "application/jsonl"
        fname   = "vetgpt_finetune.jsonl"

    return StreamingResponse(
        iter([content]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@finetune_router.get("/stats")
async def finetune_stats(
    days:      int   = Query(default=30, ge=1, le=365),
    min_score: float = Query(default=0.6),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Dataset statistics — how much fine-tuning data is available."""
    from sqlalchemy import func
    since = datetime.utcnow() - timedelta(days=days)

    total = await db.scalar(
        select(func.count(QueryLog.id)).where(
            QueryLog.created_at  >= since,
            QueryLog.status      == QueryStatus.SUCCESS,
            QueryLog.top_score   >= min_score,
        )
    ) or 0

    avg_score = await db.scalar(
        select(func.avg(QueryLog.top_score)).where(
            QueryLog.created_at >= since,
            QueryLog.status     == QueryStatus.SUCCESS,
            QueryLog.top_score  >= min_score,
        )
    ) or 0

    return {
        "exportable_records": total,
        "avg_rag_score":      round(avg_score, 3),
        "period_days":        days,
        "min_score_filter":   min_score,
        "formats_available":  ["alpaca", "sharegpt", "jsonl"],
    }


# ─── Format converters ────────────────────────────────────────────────────────

def _to_alpaca(logs: list[QueryLog]) -> list[dict]:
    """
    Alpaca format — used by llama.cpp fine-tuning, axolotl, LLaMA-Factory.
    {instruction, input, output}
    """
    return [
        {
            "instruction": SYSTEM_PROMPT,
            "input":       log.query_text,
            "output":      log.answer_text,
        }
        for log in logs
        if log.query_text and log.answer_text
    ]


def _to_sharegpt(logs: list[QueryLog]) -> list[dict]:
    """
    ShareGPT format — used by FastChat, axolotl.
    {conversations: [{from, value}]}
    """
    return [
        {
            "conversations": [
                {"from": "system",    "value": SYSTEM_PROMPT},
                {"from": "human",     "value": log.query_text},
                {"from": "gpt",       "value": log.answer_text},
            ]
        }
        for log in logs
        if log.query_text and log.answer_text
    ]


def _to_jsonl_record(log: QueryLog) -> dict:
    """Generic JSONL record with full metadata."""
    sources = []
    try:
        sources = json.loads(log.sources_used) if log.sources_used else []
    except Exception:
        pass

    return {
        "query":        log.query_text,
        "answer":       log.answer_text,
        "sources":      sources,
        "rag_score":    log.top_score,
        "chunks":       log.chunks_retrieved,
        "model":        log.llm_model,
        "latency_ms":   log.latency_ms,
        "created_at":   log.created_at.isoformat() if log.created_at else "",
    }
