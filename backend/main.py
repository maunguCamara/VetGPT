"""
vetgpt/backend/main.py

FastAPI application entry point.

Run dev server:
    uvicorn backend.main:app --reload --port 8000

Run production:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config.book_registry import BOOK_REGISTRY, get_book_metadata, detect_book
from .database import init_db
from .rag_engine import VetRAGEngine
from .routes import auth_router, query_router, health_router, set_rag_engine
from .rate_limiter import limiter
from .config import get_settings
from .admin_routes import admin_router
from .analytics import AnalyticsService
from .admin_routes import admin_router
from .vision_routes import vision_router

settings = get_settings()

# ──────────────────────────────────────────────
# Lifespan — startup / shutdown
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup: initialise DB and RAG engine.
    Runs on shutdown: cleanup.
    """
    print("VetGPT API starting up...")

    # Create DB tables
    await init_db()
    print("Database ready")

    # Initialise RAG engine (loads ChromaDB + LLM clients)
    engine = VetRAGEngine()
    set_rag_engine(engine)
    print(f"RAG engine ready ({engine.health()['chroma_chunks']:,} chunks indexed)")

    yield  # app is running

    print("VetGPT API shutting down...")

async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "Something went wrong",
        },
    )
# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "VetGPT — AI-powered veterinary reference tool. "
        "RAG over Merck, WikiVet, PubMed, FAO and more."
    ),
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc UI
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter

# Add rate limiting middleware
app.add_middleware(SlowAPIMiddleware)

# Add rate limit exception handler

app.add_exception_handler(Exception, global_exception_handler)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded. Try again later.",
            
        }
    )




# CORS — allow mobile app and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",        # web dev
        "http://localhost:8081",        # React Native Expo dev
        "https://vetgpt.app",           # production web
        "vetgpt://",                    # mobile deep link
        "http:192.168.*.*",
        "*",                   
    ],
                        
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ──────────────────────────────────────────────
# Global error handler
# ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else "Something went wrong",
        },
    )

# ──────────────────────────────────────────────
# Register routers
# ──────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(query_router)
app.include_router(health_router)
app.include_router(admin_router)
app.include_router(vision_router)

# ──────────────────────────────────────────────
# Root
# ──────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
    }
