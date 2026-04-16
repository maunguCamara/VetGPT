"""
vetgpt/backend/sync_routes.py

Delta sync endpoint — serves incremental vector index updates to mobile.

Mobile devices call GET /api/sync/delta?since=<timestamp> periodically
when online to download new chunks for the local sqlite-vec database.

Flow:
  1. Mobile comes online
  2. Calls /api/sync/delta?since=<last_sync_timestamp>
  3. Backend returns new/updated chunks since that timestamp
  4. Mobile writes chunks to localVectorStore via syncDelta()
  5. Mobile updates its last_sync timestamp

Routes:
  GET /api/sync/delta        — download new chunks since timestamp
  GET /api/sync/manifest     — index metadata (version, chunk count)
  GET /api/sync/full         — full index download (first install)
"""

import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .database import User, get_db
from ingestion.embedder import VetVectorStore
from .config import get_settings

settings   = get_settings()
sync_router = APIRouter(prefix="/api/sync", tags=["sync"])

MAX_DELTA_CHUNKS = 1000    # per request
MAX_FULL_CHUNKS  = 50000   # full download cap


# ─── Manifest ─────────────────────────────────────────────────────────────────

@sync_router.get("/manifest")
async def sync_manifest(user: User = Depends(get_current_user)):
    """
    Returns index metadata the mobile app uses to decide if sync is needed.
    """
    store = VetVectorStore()
    stats = store.stats()
    sources = store.list_sources()

    return {
        "total_chunks":   stats["total_chunks"],
        "source_count":   len(sources),
        "sources":        sources,
        "schema_version": 1,
        "server_time":    datetime.utcnow().isoformat(),
    }


# ─── Delta sync ───────────────────────────────────────────────────────────────

@sync_router.get("/delta")
async def sync_delta(
    since: str = Query(
        default="",
        description="ISO timestamp of last sync. Empty = last 7 days.",
    ),
    limit: int = Query(default=500, ge=1, le=MAX_DELTA_CHUNKS),
    user: User = Depends(get_current_user),
):
    """
    Returns new chunks added since `since` timestamp.
    Mobile calls this on reconnect to update the local sqlite index.

    Response is a JSON array of chunk objects ready for localVectorStore.syncDelta().
    """
    # Parse since timestamp
    try:
        since_dt = datetime.fromisoformat(since) if since else datetime.utcnow() - timedelta(days=7)
    except ValueError:
        since_dt = datetime.utcnow() - timedelta(days=7)

    store = VetVectorStore()

    # Query ChromaDB for chunks — ChromaDB doesn't support time filtering natively,
    # so we retrieve all and filter by a stored timestamp in metadata.
    # In production this should be backed by a proper SQL table for efficiency.
    try:
        result = store._collection.get(
            include=["documents", "metadatas"],
            limit=limit,
        )
    except Exception:
        return {"chunks": [], "synced_at": datetime.utcnow().isoformat(), "count": 0}

    chunks = []
    ids        = result.get("ids", [])
    documents  = result.get("documents", [])
    metadatas  = result.get("metadatas", [])

    for chunk_id, text, meta in zip(ids, documents, metadatas):
        # Include chunk if it has no scraped_at (older data) or was added after since_dt
        scraped_at_str = meta.get("scraped_at", "")
        if scraped_at_str:
            try:
                scraped_at = datetime.fromisoformat(scraped_at_str)
                if scraped_at <= since_dt:
                    continue
            except ValueError:
                pass   # include if unparseable

        chunks.append({
            "chunk_id":       chunk_id,
            "text":           text,
            "source_file":    meta.get("source_file", ""),
            "document_title": meta.get("document_title", ""),
            "page_number":    meta.get("page_number", 1),
            "score":          0.0,   # placeholder — score is query-time
        })

    synced_at = datetime.utcnow().isoformat()

    # Stream as JSONL for memory efficiency on large deltas
    def generate():
        yield '{"chunks":['
        for i, chunk in enumerate(chunks):
            if i > 0:
                yield ","
            yield json.dumps(chunk, ensure_ascii=False)
        yield f'],"count":{len(chunks)},"synced_at":"{synced_at}"}}'

    return StreamingResponse(
        generate(),
        media_type="application/json",
        headers={"X-Chunk-Count": str(len(chunks))},
    )


# ─── Full download ────────────────────────────────────────────────────────────

@sync_router.get("/full")
async def sync_full(
    user: User = Depends(get_current_user),
):
    """
    Full index download for first install.
    Returns all chunks as a JSONL stream.
    Only call this once — use /delta for subsequent syncs.
    """
    store = VetVectorStore()

    try:
        result = store._collection.get(
            include=["documents", "metadatas"],
            limit=MAX_FULL_CHUNKS,
        )
    except Exception:
        return Response(content="{}", media_type="application/json")

    ids       = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    def generate():
        for chunk_id, text, meta in zip(ids, documents, metadatas):
            record = {
                "chunk_id":       chunk_id,
                "text":           text,
                "source_file":    meta.get("source_file", ""),
                "document_title": meta.get("document_title", ""),
                "page_number":    meta.get("page_number", 1),
                "score":          0.0,
            }
            yield json.dumps(record, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/jsonl",
        headers={
            "X-Total-Chunks": str(len(ids)),
            "Content-Disposition": 'attachment; filename="vetgpt_index.jsonl"',
        },
    )
