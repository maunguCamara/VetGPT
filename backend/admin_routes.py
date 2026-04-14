"""
vetgpt/backend/admin_routes.py

Admin dashboard API endpoints.
All routes require admin role (is_admin flag on User model).

Routes:
  GET  /api/admin/overview           — key metrics
  GET  /api/admin/analytics/latency  — latency percentiles
  GET  /api/admin/analytics/rag      — RAG quality
  GET  /api/admin/analytics/models   — model usage breakdown
  GET  /api/admin/analytics/tiers    — queries by tier
  GET  /api/admin/analytics/volume   — daily volume
  GET  /api/admin/analytics/queries  — top queries
  GET  /api/admin/analytics/errors   — error breakdown
  GET  /api/admin/users              — user list (paginated)
  PUT  /api/admin/users/{id}/tier    — change user tier
  GET  /api/admin/system             — system health + ChromaDB
  POST /api/admin/reindex            — trigger re-indexing (async)
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user, require_premium
from .database import User, SubscriptionTier, get_db
from .analytics import analytics
from .config import get_settings
from ingestion.embedder import VetVectorStore
from .routes import get_rag_engine
from .rag_engine import VetRAGEngine

settings = get_settings()
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Admin guard ──────────────────────────────────────────────────────────────

async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """
    Dependency: only users with is_admin=True can access admin routes.
    Add is_admin column to User model or use a hardcoded admin email list.
    """
    admin_emails = set(
        e.strip() for e in settings.admin_emails.split(",")
        if e.strip()
    ) if hasattr(settings, "admin_emails") and settings.admin_emails else set()

    is_admin = (
        getattr(user, "is_admin", False)
        or user.email in admin_emails
        or user.tier == SubscriptionTier.CLINIC
    )

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TierUpdate(BaseModel):
    tier: str   # free | premium | clinic


class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str
    tier: str
    is_active: bool
    created_at: str
    last_login: str | None

    class Config:
        from_attributes = True


# ─── Overview ─────────────────────────────────────────────────────────────────

@admin_router.get("/overview")
async def admin_overview(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """High-level dashboard metrics."""
    return await analytics.overview(db, days=days)


# ─── Analytics ────────────────────────────────────────────────────────────────

@admin_router.get("/analytics/latency")
async def admin_latency(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Query latency percentiles (p50, p75, p95, p99)."""
    return await analytics.latency_stats(db, days=days)


@admin_router.get("/analytics/rag")
async def admin_rag_quality(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """RAG retrieval quality metrics."""
    return await analytics.rag_quality(db, days=days)


@admin_router.get("/analytics/models")
async def admin_model_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """LLM model usage breakdown."""
    return await analytics.model_usage(db, days=days)


@admin_router.get("/analytics/tiers")
async def admin_tier_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Query volume by user tier."""
    return await analytics.queries_by_tier(db, days=days)


@admin_router.get("/analytics/volume")
async def admin_daily_volume(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Daily query volume."""
    return await analytics.daily_volume(db, days=days)


@admin_router.get("/analytics/queries")
async def admin_top_queries(
    days: int  = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Most frequent queries — useful for fine-tuning dataset curation."""
    return await analytics.top_queries(db, days=days, limit=limit)


@admin_router.get("/analytics/errors")
async def admin_errors(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Recent error breakdown."""
    return await analytics.error_breakdown(db, days=days)


# ─── User management ──────────────────────────────────────────────────────────

@admin_router.get("/users")
async def admin_list_users(
    limit: int  = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Paginated user list."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    users = result.scalars().all()
    return [
        {
            "id":         u.id,
            "email":      u.email,
            "full_name":  u.full_name,
            "tier":       u.tier.value,
            "is_active":  u.is_active,
            "created_at": u.created_at.isoformat(),
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@admin_router.put("/users/{user_id}/tier")
async def admin_update_tier(
    user_id: str,
    body: TierUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Update a user's subscription tier."""
    try:
        new_tier = SubscriptionTier(body.tier)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{body.tier}'. Must be: free, premium, clinic"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_tier   = user.tier.value
    user.tier  = new_tier
    await db.flush()

    return {
        "user_id":   user_id,
        "email":     user.email,
        "old_tier":  old_tier,
        "new_tier":  new_tier.value,
        "updated":   True,
    }


@admin_router.put("/users/{user_id}/deactivate")
async def admin_deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Deactivate (soft-delete) a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await db.flush()
    return {"user_id": user_id, "deactivated": True}


# ─── System health ────────────────────────────────────────────────────────────

@admin_router.get("/system")
async def admin_system(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Full system health including ChromaDB, DB, and vision pipeline."""
    from .rag_engine import VetRAGEngine

    store      = VetVectorStore()
    db_status  = "ok"

    try:
        await db.execute(select(User).limit(1))
    except Exception as e:
        db_status = f"error: {e}"

    chroma_stats = store.stats()
    sources      = store.list_sources()

    return {
        "database":       db_status,
        "chroma_chunks":  chroma_stats["total_chunks"],
        "indexed_sources": sources,
        "source_count":   len(sources),
        "llm_provider":   settings.llm_provider,
        "environment":    settings.environment,
    }


@admin_router.post("/reindex")
async def admin_reindex(
    source: str = Query(description="Source to reindex: wikivet|pubmed|fao|eclinpath|all"),
    _: User = Depends(require_admin),
):
    """
    Trigger background re-indexing of a scraping source.
    Returns immediately — check /api/admin/system for updated chunk counts.
    """
    valid = {"wikivet", "pubmed", "fao", "eclinpath", "all"}
    if source not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid source '{source}'. Must be one of: {', '.join(valid)}"
        )

    return {
        "message": f"Re-indexing '{source}' queued. "
                   f"Run: python scrape.py {source if source != 'all' else 'run-all'} "
                   f"from the vetgpt/ directory.",
        "note": "Background job scheduling (Celery/RQ) not yet configured. "
                "Re-indexing must be triggered manually via CLI.",
    }