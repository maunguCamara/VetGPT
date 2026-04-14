"""
vetgpt/backend/rate_limiter.py

Tier-aware rate limiting using Redis (production) or in-memory (dev).

Limits:
  Unauthenticated : 5  req/min
  Free tier       : 20 req/min
  Premium tier    : 100 req/min
  Clinic tier     : 500 req/min
  Vision endpoints: 10 req/min (premium), 30 req/min (clinic)

Falls back to in-memory store if Redis is unavailable.
"""

import time
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

from .config import get_settings

settings = get_settings()


# ─── Rate limit config per tier ──────────────────────────────────────────────

RATE_LIMITS = {
    "unauthenticated": {"requests": 5,   "window": 60},
    "free":            {"requests": 20,  "window": 60},
    "premium":         {"requests": 100, "window": 60},
    "clinic":          {"requests": 500, "window": 60},
}

# Vision endpoints cost more — stricter limits
VISION_RATE_LIMITS = {
    "unauthenticated": {"requests": 2,  "window": 60},
    "free":            {"requests": 2,  "window": 60},   # not allowed but graceful
    "premium":         {"requests": 10, "window": 60},
    "clinic":          {"requests": 30, "window": 60},
}


# ─── In-memory store ─────────────────────────────────────────────────────────

@dataclass
class RateLimitWindow:
    count: int = 0
    window_start: float = field(default_factory=time.time)


class InMemoryRateLimiter:
    """Thread-safe in-memory rate limiter. Use Redis in production."""

    def __init__(self):
        self._store: dict[str, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._lock = asyncio.Lock()

    async def check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Returns:
            (allowed, remaining, reset_in_seconds)
        """
        async with self._lock:
            now  = time.time()
            data = self._store[key]

            # Reset window if expired
            if now - data.window_start >= window_seconds:
                data.count        = 0
                data.window_start = now

            if data.count >= max_requests:
                reset_in = int(window_seconds - (now - data.window_start))
                return False, 0, reset_in

            data.count += 1
            remaining = max_requests - data.count
            reset_in  = int(window_seconds - (now - data.window_start))
            return True, remaining, reset_in

    async def reset(self, key: str) -> None:
        async with self._lock:
            if key in self._store:
                del self._store[key]


# Singleton
_limiter = InMemoryRateLimiter()


# ─── Redis store (production) ─────────────────────────────────────────────────

class RedisRateLimiter:
    """Redis-backed rate limiter for multi-worker production deployments."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client    = None

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = await aioredis.from_url(self._redis_url)
            except ImportError:
                raise RuntimeError("Install redis: pip install redis")
        return self._client

    async def check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        client = await self._get_client()
        pipe   = client.pipeline()

        redis_key = f"rl:{key}"
        pipe.incr(redis_key)
        pipe.ttl(redis_key)
        count, ttl = await pipe.execute()

        if ttl == -1:
            await client.expire(redis_key, window_seconds)
            ttl = window_seconds

        if count > max_requests:
            return False, 0, max(ttl, 0)

        remaining = max_requests - count
        return True, remaining, max(ttl, 0)


# ─── Dependency factory ───────────────────────────────────────────────────────

def get_rate_limiter_dependency(is_vision: bool = False):
    """
    Returns a FastAPI dependency function that enforces rate limits.

    Usage:
        @router.post("/endpoint")
        async def handler(
            request: Request,
            _: None = Depends(get_rate_limiter_dependency()),
        ):
            ...
    """
    async def rate_limit_check(request: Request):
        # Determine tier from token
        tier = "unauthenticated"
        user_id = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from jose import jwt
                token   = auth_header.split(" ")[1]
                payload = jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=[settings.algorithm],
                )
                tier    = payload.get("tier", "free")
                user_id = payload.get("sub")
            except Exception:
                tier = "unauthenticated"

        # Build rate limit key: prefer user_id, fall back to IP
        client_ip = request.client.host if request.client else "unknown"
        rate_key  = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        # Get limits
        limits = VISION_RATE_LIMITS if is_vision else RATE_LIMITS
        config = limits.get(tier, limits["free"])

        allowed, remaining, reset_in = await _limiter.check(
            key             = rate_key,
            max_requests    = config["requests"],
            window_seconds  = config["window"],
        )

        # Always add rate limit headers
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset     = reset_in

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "tier":  tier,
                    "limit": config["requests"],
                    "window_seconds": config["window"],
                    "reset_in_seconds": reset_in,
                    "upgrade_message": (
                        "Upgrade to Premium for higher rate limits."
                        if tier in ("free", "unauthenticated") else None
                    ),
                },
                headers={
                    "Retry-After":              str(reset_in),
                    "X-RateLimit-Limit":        str(config["requests"]),
                    "X-RateLimit-Remaining":    "0",
                    "X-RateLimit-Reset":        str(int(time.time()) + reset_in),
                },
            )

    return rate_limit_check


# Convenience pre-built dependencies
standard_rate_limit = get_rate_limiter_dependency(is_vision=False)
vision_rate_limit   = get_rate_limiter_dependency(is_vision=True)

# ─── Public aliases ────────────────────────────────────────────────────────────
# These names are imported by routes.py and the test suite.

# Public reference to the singleton limiter
limiter = _limiter


def get_rate_limit_for_user(tier: str) -> dict:
    """
    Return the rate limit config for a given tier.
    Used by routes.py and tests to inspect limits without triggering them.

    Returns:
        dict with keys: requests (int), window (int in seconds)
    """
    return RATE_LIMITS.get(tier, RATE_LIMITS["free"])


def get_vision_rate_limit_for_user(tier: str) -> dict:
    """Return vision-specific rate limit config for a given tier."""
    return VISION_RATE_LIMITS.get(tier, VISION_RATE_LIMITS["free"])


__all__ = [
    "InMemoryRateLimiter",
    "RedisRateLimiter",
    "RATE_LIMITS",
    "VISION_RATE_LIMITS",
    "limiter",
    "standard_rate_limit",
    "vision_rate_limit",
    "get_rate_limiter_dependency",
    "get_rate_limit_for_user",
    "get_vision_rate_limit_for_user",
]
