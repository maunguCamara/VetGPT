"""
vetgpt/backend/main.py

FastAPI application entry point.

Run dev:
    uvicorn backend.main:app --reload --port 8000

Run prod:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import get_settings
from .database import init_db
from .rag_engine import VetRAGEngine
from .routes import auth_router, query_router, health_router, set_rag_engine
from .vision_routes import vision_router
from .admin_routes import admin_router
from .upload_routes import upload_router

settings = get_settings()


# ── Rate limiter key: user_id from JWT if present, else IP ───────────────────

def rate_limit_key(request: Request) -> str:
    """Authenticated → key by user_id. Anonymous → key by IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt as jose_jwt
            token   = auth.split(" ", 1)[1]
            payload = jose_jwt.decode(
                token, settings.secret_key,
                algorithms=[settings.algorithm],
                options={"verify_exp": False},
            )
            return f"user:{payload.get('sub', get_remote_address(request))}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


# ── slowapi Limiter (NOT our InMemoryRateLimiter) ────────────────────────────
# slowapi's Limiter handles the @limiter.limit() decorator pattern.
# Our InMemoryRateLimiter handles the Depends() pattern in routes.
# They are separate — do not mix them.

limiter = Limiter(key_func=rate_limit_key)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 VetGPT API starting...")
    await init_db()
    print("✓ Database ready")
    engine = VetRAGEngine()
    set_rag_engine(engine)
    h = engine.health()
    print(f"✓ RAG engine ready — {h['chroma_chunks']:,} chunks, LLM: {h['llm_provider']}")
    yield
    print("VetGPT API shutting down...")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "VetGPT — AI-powered veterinary reference tool. "
        "RAG over WikiVet, PubMed, FAO, eClinPath and uploaded vet manuals."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Attach slowapi's Limiter to app state (required by slowapi middleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add slowapi middleware BEFORE CORS so rate limits are checked first
app.add_middleware(SlowAPIMiddleware)


# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8081",
        "https://vetgpt.app",
        "vetgpt://",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start    = time.time()
    response = await call_next(request)
    ms       = int((time.time() - start) * 1000)
    response.headers["X-Response-Time"] = f"{ms}ms"
    return response


# ── Global error handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "Something went wrong",
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(query_router)
app.include_router(health_router)
app.include_router(vision_router)
app.include_router(admin_router)
app.include_router(upload_router)


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "name":    settings.app_name,
        "version": settings.app_version,
        "docs":    "/docs",
        "health":  "/api/health",
    }