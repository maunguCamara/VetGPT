"""
vetgpt/backend/routes.py

All API route handlers grouped by domain.

Routes:
  POST /api/auth/register
  POST /api/auth/login
  GET  /api/auth/me

  POST /api/query          — main RAG query (free)
  POST /api/query/stream   — streaming RAG query (free)
  POST /api/query/image    — image + OCR query (premium)
  GET  /api/query/history  — user's query history

  GET  /api/health         — public health check
  GET  /api/health/db      — DB + ChromaDB status (admin)
"""

import json
import time
from datetime import datetime
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Request
)
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from .rate_limiter import limiter, get_rate_limit_for_user


from .auth import (
    UserCreate, UserOut, Token,
    create_user, authenticate_user, create_access_token,
    get_current_user, get_current_user_optional, require_premium,
)
from .database import User, QueryLog, QueryStatus, get_db
from .rag_engine import VetRAGEngine
from .config import get_settings

settings = get_settings()
router = APIRouter()


# ──────────────────────────────────────────────
# Dependency: shared RAG engine (set by main app)
# ──────────────────────────────────────────────

_rag_engine: VetRAGEngine | None = None

def set_rag_engine(engine: VetRAGEngine):
    global _rag_engine
    _rag_engine = engine

def get_rag_engine() -> VetRAGEngine:
    if _rag_engine is None:
        raise HTTPException(status_code=503, detail="RAG engine not initialised")
    return _rag_engine

def get_rate_limit(user: User | None) -> str:
    """Return rate limit string based on user tier."""
    if not user:
        return "5/minute"  # Unauthenticated
    if user.tier.value == "free":
        return "20/minute"
    elif user.tier.value in ["premium", "clinic"]:
        return "100/minute"
    return "20/minute"

# ──────────────────────────────────────────────
# Request / Response schemas
# ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    filter_species: str | None = Field(default=None, description="e.g. canine, equine, bovine")
    filter_source: str | None = Field(default=None, description="e.g. wikivet, plumbs, pubmed")
    stream: bool = False


class QueryResponse(BaseModel):
    query: str
    answer: str
    citations: list[dict]
    chunks_retrieved: int
    top_score: float
    llm_model: str
    latency_ms: int
    disclaimer: str


class HistoryItem(BaseModel):
    id: int
    query_text: str
    answer_text: str
    sources_used: list[dict]
    latency_ms: int
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/register", response_model=Token, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account."""
    user = await create_user(db, data)
    token = create_access_token(user)
    return Token(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@auth_router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email + password.
    Returns a JWT access token valid for 7 days.
    """
    user = await authenticate_user(db, form.username, form.password)
    token = create_access_token(user)
    return Token(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@auth_router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return UserOut.model_validate(user)


# ──────────────────────────────────────────────
# QUERY ROUTES
# ──────────────────────────────────────────────

query_router = APIRouter(prefix="/api/query", tags=["query"])


@query_router.post("", response_model=QueryResponse)
@limiter.limit("20/minute")
async def query(
    request: Request,
    query_req: QueryRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
    engine: VetRAGEngine = Depends(get_rag_engine),
):
    # Get rate limit based on user tier
    user_tier = user.tier.value if user else None
    limit_str = get_rate_limit_for_user(user_tier)
  
    request.state.user = user  # for rate limiter
    # Cap top_k by tier
    top_k = query_req.top_k
    if not user:
        top_k = min(top_k, 3)
    elif user.tier.value == "free":
        top_k = min(top_k, 5)

    try:
        rag_response = await engine.query(
            query_text=request.query,
            top_k=top_k,
            filter_species=request.filter_species,
            filter_source=request.filter_source,
        )
    except Exception as e:
        await _log_query(
            db, user, request.query, "", [], 0, 0.0, "", 0,
            QueryStatus.ERROR, str(e)
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    # Log to DB
    await _log_query(
        db=db,
        user=user,
        query=request.query,
        answer=rag_response.answer,
        citations=[c.to_dict() for c in rag_response.citations],
        chunks=rag_response.chunks_retrieved,
        top_score=rag_response.top_score,
        model=rag_response.llm_model,
        latency=rag_response.latency_ms,
        status=QueryStatus.SUCCESS,
    )

    return QueryResponse(**rag_response.to_dict())


@query_router.post("/stream")
async def query_stream(
    request: QueryRequest,
    user: User | None = Depends(get_current_user_optional),
    engine: VetRAGEngine = Depends(get_rag_engine),
):
    """
    Streaming RAG query — returns tokens as server-sent events.
    Used by mobile app for real-time typing effect.
    """
    top_k = min(request.top_k, 5) if not user else request.top_k

    async def event_generator():
        async for token in engine.stream_query(request.query, top_k=top_k):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@query_router.post("/image")
async def query_with_image(
    query: str,
    file: UploadFile = File(...),
    user: User = Depends(require_premium),   # premium only
    engine: VetRAGEngine = Depends(get_rag_engine),
):
    """
    Premium: Submit an image (wound, lesion, X-ray) + question.
    Phase 3 feature — stub returns 501 until vision pipeline is built.
    """
    raise HTTPException(
        status_code=501,
        detail="Image analysis coming in Phase 3. Upgrade to premium to get early access.",
    )


@query_router.get("/history", response_model=list[HistoryItem])
async def get_history(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's query history."""
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.user_id == user.id)
        .order_by(desc(QueryLog.created_at))
        .limit(limit)
        .offset(offset)
    )
    logs = result.scalars().all()

    return [
        HistoryItem(
            id=log.id,
            query_text=log.query_text,
            answer_text=log.answer_text,
            sources_used=json.loads(log.sources_used) if log.sources_used else [],
            latency_ms=log.latency_ms,
            created_at=log.created_at,
        )
        for log in logs
    ]


# ──────────────────────────────────────────────
# HEALTH ROUTES
# ──────────────────────────────────────────────

health_router = APIRouter(prefix="/api/health", tags=["health"])


@health_router.get("")
async def health():
    """Public health check — used by mobile app to detect connectivity."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "timestamp": datetime.utcnow().isoformat(),
    }


@health_router.get("/full")
async def health_full(
    engine: VetRAGEngine = Depends(get_rag_engine),
    db: AsyncSession = Depends(get_db),
):
    """Full health check including DB and ChromaDB stats."""
    engine_health = engine.health()

    # Check DB
    try:
        await db.execute(select(User).limit(1))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": settings.app_version,
        "database": db_status,
        "chroma_chunks": engine_health["chroma_chunks"],
        "llm_provider": engine_health["llm_provider"],
        "anthropic_ready": engine_health["anthropic_ready"],
        "openai_ready": engine_health["openai_ready"],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ──────────────────────────────────────────────
# Private helper
# ──────────────────────────────────────────────

async def _log_query(
    db, user, query, answer, citations, chunks, top_score,
    model, latency, status, error=""
):
    """Log a query to the database."""
    try:
        log = QueryLog(
            user_id=user.id if user else None,
            query_text=query,
            answer_text=answer[:4000],      # cap length
            sources_used=json.dumps(citations),
            chunks_retrieved=chunks,
            top_score=top_score,
            llm_model=model,
            latency_ms=latency,
            status=status,
            error_message=error,
            is_premium_query=user.tier.value != "free" if user else False,
        )
        db.add(log)
    except Exception:
        pass  # never let logging break a query response

@router.post("/api/analytics")
async def track_analytics(
    data: dict,
    user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Track analytics events like query latency, model performance"""
    
    events = data.get('events', [])
    
    for event in events:
        # Create analytics record
        analytics = AnalyticsEvent(
            user_id=user.id if user else None,
            event_type=event.get('event'),
            properties=event.get('properties', {}),
            created_at=datetime.utcnow()
        )
        db.add(analytics)
    
    await db.commit()
    return {"status": "ok", "events_received": len(events)}
