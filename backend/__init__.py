"""
vetgpt/backend/__init__.py

Backend package initialization.
"""

from .config import get_settings
from .database import init_db, get_db, User, QueryLog, Subscription, SubscriptionTier, QueryStatus
from .auth import (
    hash_password, verify_password, create_access_token, decode_token,
    get_current_user, get_current_user_optional, require_premium,
    create_user, authenticate_user
)
from .rag_engine import VetRAGEngine, RAGResponse, Citation
from .routes import auth_router, query_router, health_router, set_rag_engine

__all__ = [
    "get_settings",
    "init_db",
    "get_db",
    "User",
    "QueryLog", 
    "Subscription",
    "SubscriptionTier",
    "QueryStatus",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "get_current_user_optional",
    "require_premium",
    "create_user",
    "authenticate_user",
    "VetRAGEngine",
    "RAGResponse",
    "Citation",
    "auth_router",
    "query_router",
    "health_router",
    "set_rag_engine",
]