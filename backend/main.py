"""
vetgpt/backend/main.py

FastAPI application entry point — all routers registered.

Run dev:   uvicorn backend.main:app --reload --port 8000
Run prod:  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
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

# Route groups
from .routes        import auth_router, query_router, health_router, set_rag_engine
from .vision_routes import vision_router
from .admin_routes  import admin_router
from .upload_routes import upload_router
from .billing       import billing_router
from .finetune      import finetune_router
from .sync_routes   import sync_router

settings = get_settings()


# ── Rate limiter key ──────────────────────────────────────────────────────────

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


# slowapi Limiter — this is NOT InMemoryRateLimiter
# app.state.limiter must be slowapi's Limiter for SlowAPIMiddleware to work
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
    print(f"✓ RAG engine — {h['chroma_chunks']:,} chunks | LLM: {h['llm_provider']}")
    print("✓ All systems ready")
    yield
    print("VetGPT API shutting down...")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = settings.app_name,
    version     = settings.app_version,
    description = (
        "VetGPT — AI veterinary reference. "
        "RAG over WikiVet, PubMed, FAO, eClinPath and uploaded vet manuals. "
        "Premium: X-ray, lesion, parasite, cytology AI analysis."
    ),
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

# IMPORTANT: app.state.limiter must be slowapi's Limiter, not InMemoryRateLimiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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


# ── Request timing ────────────────────────────────────────────────────────────

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
            "error":  "Internal server error",
            "detail": str(exc) if settings.debug else "Something went wrong",
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────

# Core
app.include_router(auth_router)        # /api/auth/*
app.include_router(query_router)       # /api/query/*
app.include_router(health_router)      # /api/health/*

# Premium vision
app.include_router(vision_router)      # /api/vision/*

# Admin + analytics + fine-tuning
app.include_router(admin_router)       # /api/admin/*
app.include_router(finetune_router)    # /api/admin/finetune/*

# Billing (Stripe)
app.include_router(billing_router)     # /api/billing/*

# PDF upload
app.include_router(upload_router)      # /api/manuals/*

# Mobile offline sync
app.include_router(sync_router)        # /api/sync/*


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "name":    settings.app_name,
        "version": settings.app_version,
        "docs":    "/docs",
        "health":  "/api/health",
        "routes": {
            "auth":    "/api/auth",
            "query":   "/api/query",
            "vision":  "/api/vision  (premium)",
            "billing": "/api/billing",
            "sync":    "/api/sync",
            "manuals": "/api/manuals",
            "admin":   "/api/admin   (admin only)",
        },
    }