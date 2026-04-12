"""
vetgpt/backend/rate_limiter.py

Rate limiting configuration and utilities.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from .config import get_settings

settings = get_settings()

# Create the limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/hour"],
    storage_uri="memory://"  # Use Redis in production: "redis://localhost:6379"
)

def get_rate_limit_for_user(user_tier: str | None) -> str:
    """Return rate limit string based on user tier."""
    if not user_tier:
        return "5/minute"  # Unauthenticated
    if user_tier == "free":
        return "20/minute"
    elif user_tier in ["premium", "clinic"]:
        return "100/minute"
    return "20/minute"

async def check_rate_limit(request: Request, user_tier: str | None = None):
    """Check rate limit based on user tier."""
    limit_str = get_rate_limit_for_user(user_tier)
    # Parse limit string (e.g., "20/minute" -> 20, 60)
    parts = limit_str.split('/')
    limit = int(parts[0])
    
    # Get client identifier
    client_id = request.headers.get('X-Forwarded-For', request.client.host)
    if user_tier:
        client_id = f"{user_tier}:{client_id}"
    
    # Check if rate limit exceeded
    if not limiter._check_limit(client_id, limit, 60):
        raise RateLimitExceeded()
    
    return True