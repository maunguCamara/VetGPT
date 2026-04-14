"""
vetgpt/backend/analytics.py

Model performance analytics and usage tracking.

Tracks:
  - Query latency (p50, p95, p99)
  - RAG retrieval quality (score distribution)
  - LLM model usage breakdown
  - Error rates by type
  - Vision endpoint usage
  - Queries per user tier
  - Daily/weekly/monthly active users
  - Top queries (for fine-tuning dataset curation)
"""

from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .database import QueryLog, User, QueryStatus, SubscriptionTier


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(int(len(values) * p / 100), len(values) - 1)
    return round(values[idx], 2)


class AnalyticsService:

    async def overview(self, db: AsyncSession, days: int = 30) -> dict:
        since = datetime.utcnow() - timedelta(days=days)

        total_q = await db.scalar(
            select(func.count(QueryLog.id)).where(QueryLog.created_at >= since)
        ) or 0

        success_q = await db.scalar(
            select(func.count(QueryLog.id)).where(
                QueryLog.created_at >= since,
                QueryLog.status == QueryStatus.SUCCESS,
            )
        ) or 0

        total_users = await db.scalar(select(func.count(User.id))) or 0

        active_users = await db.scalar(
            select(func.count(func.distinct(QueryLog.user_id))).where(
                QueryLog.created_at >= since,
                QueryLog.user_id.isnot(None),
            )
        ) or 0

        premium_users = await db.scalar(
            select(func.count(User.id)).where(
                User.tier.in_([SubscriptionTier.PREMIUM, SubscriptionTier.CLINIC])
            )
        ) or 0

        avg_latency = await db.scalar(
            select(func.avg(QueryLog.latency_ms)).where(
                QueryLog.created_at >= since,
                QueryLog.status == QueryStatus.SUCCESS,
            )
        ) or 0

        return {
            "period_days":     days,
            "total_queries":   total_q,
            "success_queries": success_q,
            "error_rate_pct":  round(((total_q - success_q) / max(total_q, 1)) * 100, 1),
            "total_users":     total_users,
            "active_users":    active_users,
            "premium_users":   premium_users,
            "avg_latency_ms":  round(avg_latency, 0),
        }

    async def latency_stats(self, db: AsyncSession, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(QueryLog.latency_ms).where(
                QueryLog.created_at >= since,
                QueryLog.status == QueryStatus.SUCCESS,
                QueryLog.latency_ms > 0,
            )
        )
        latencies = [r[0] for r in result.fetchall()]
        return {
            "count":  len(latencies),
            "p50_ms": percentile(latencies, 50),
            "p75_ms": percentile(latencies, 75),
            "p95_ms": percentile(latencies, 95),
            "p99_ms": percentile(latencies, 99),
            "min_ms": round(min(latencies), 0) if latencies else 0,
            "max_ms": round(max(latencies), 0) if latencies else 0,
        }

    async def rag_quality(self, db: AsyncSession, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(QueryLog.top_score, QueryLog.chunks_retrieved).where(
                QueryLog.created_at >= since,
                QueryLog.status == QueryStatus.SUCCESS,
            )
        )
        rows   = result.fetchall()
        scores = [r[0] for r in rows if r[0] and r[0] > 0]
        chunks = [r[1] for r in rows if r[1] and r[1] > 0]
        return {
            "avg_top_score":          round(sum(scores) / max(len(scores), 1), 3),
            "avg_chunks_retrieved":   round(sum(chunks) / max(len(chunks), 1), 1),
            "pct_low_score_queries":  round(sum(1 for s in scores if s < 0.4) / max(len(scores), 1) * 100, 1),
            "score_p50":              percentile(scores, 50),
            "score_p25":              percentile(scores, 25),
            "total_analyzed":         len(scores),
        }

    async def model_usage(self, db: AsyncSession, days: int = 30) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(
                QueryLog.llm_model,
                func.count(QueryLog.id).label("count"),
                func.avg(QueryLog.latency_ms).label("avg_latency"),
            )
            .where(QueryLog.created_at >= since)
            .group_by(QueryLog.llm_model)
            .order_by(func.count(QueryLog.id).desc())
        )
        return [
            {"model": r.llm_model or "unknown", "count": r.count, "avg_latency_ms": round(r.avg_latency or 0, 0)}
            for r in result.fetchall()
        ]

    async def queries_by_tier(self, db: AsyncSession, days: int = 30) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(User.tier, func.count(QueryLog.id).label("count"))
            .join(User, QueryLog.user_id == User.id)
            .where(QueryLog.created_at >= since)
            .group_by(User.tier)
        )
        rows = [{"tier": r.tier.value, "count": r.count} for r in result.fetchall()]
        unauth = await db.scalar(
            select(func.count(QueryLog.id)).where(
                QueryLog.created_at >= since, QueryLog.user_id.is_(None)
            )
        ) or 0
        if unauth:
            rows.append({"tier": "unauthenticated", "count": unauth})
        return sorted(rows, key=lambda x: x["count"], reverse=True)

    async def daily_volume(self, db: AsyncSession, days: int = 30) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(
                func.date(QueryLog.created_at).label("date"),
                func.count(QueryLog.id).label("total"),
            )
            .where(QueryLog.created_at >= since)
            .group_by(func.date(QueryLog.created_at))
            .order_by(func.date(QueryLog.created_at))
        )
        return [{"date": str(r.date), "total": r.total} for r in result.fetchall()]

    async def top_queries(self, db: AsyncSession, days: int = 7, limit: int = 20) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(
                QueryLog.query_text,
                func.count(QueryLog.id).label("count"),
                func.avg(QueryLog.top_score).label("avg_score"),
            )
            .where(QueryLog.created_at >= since, QueryLog.status == QueryStatus.SUCCESS)
            .group_by(QueryLog.query_text)
            .order_by(func.count(QueryLog.id).desc())
            .limit(limit)
        )
        return [
            {"query": r.query_text[:120], "count": r.count, "avg_score": round(r.avg_score or 0, 3)}
            for r in result.fetchall()
        ]

    async def error_breakdown(self, db: AsyncSession, days: int = 7) -> list[dict]:
        since = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(
            select(QueryLog.error_message, func.count(QueryLog.id).label("count"))
            .where(
                QueryLog.created_at >= since,
                QueryLog.status == QueryStatus.ERROR,
                QueryLog.error_message != "",
            )
            .group_by(QueryLog.error_message)
            .order_by(func.count(QueryLog.id).desc())
            .limit(15)
        )
        return [{"error": r.error_message[:100], "count": r.count} for r in result.fetchall()]


analytics = AnalyticsService()
