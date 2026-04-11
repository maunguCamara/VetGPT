"""
vetgpt/backend/database.py

SQLAlchemy async database setup.
Models: User, QueryLog, Subscription

Dev:  SQLite (aiosqlite) — zero config
Prod: swap DATABASE_URL to PostgreSQL in .env
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime,
    Integer, Float, Text, ForeignKey, Enum
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum
from .config import get_settings

settings = get_settings()

# Engine — async
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class SubscriptionTier(str, enum.Enum):
    FREE    = "free"
    PREMIUM = "premium"
    CLINIC  = "clinic"      # future: multi-seat clinic plan


class QueryStatus(str, enum.Enum):
    SUCCESS  = "success"
    ERROR    = "error"
    FILTERED = "filtered"   # content policy


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id              = Column(String(36), primary_key=True)  # UUID
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name       = Column(String(255), default="")
    is_active       = Column(Boolean, default=True)
    is_verified     = Column(Boolean, default=False)
    tier            = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    created_at      = Column(DateTime, default=datetime.utcnow)
    last_login      = Column(DateTime, nullable=True)

    # Relationships
    queries = relationship("QueryLog", back_populates="user", lazy="select")


class QueryLog(Base):
    """
    Every RAG query is logged for:
    - Usage tracking / billing
    - Quality monitoring
    - Fine-tuning dataset collection
    """
    __tablename__ = "query_logs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(String(36), ForeignKey("users.id"), nullable=True)
    query_text      = Column(Text, nullable=False)
    answer_text     = Column(Text, default="")
    sources_used    = Column(Text, default="")      # JSON: list of source citations
    chunks_retrieved = Column(Integer, default=0)
    top_score       = Column(Float, default=0.0)    # best RAG similarity score
    llm_model       = Column(String(100), default="")
    latency_ms      = Column(Integer, default=0)
    status          = Column(Enum(QueryStatus), default=QueryStatus.SUCCESS)
    error_message   = Column(Text, default="")
    is_premium_query = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="queries")


class Subscription(Base):
    """Stripe subscription records."""
    __tablename__ = "subscriptions"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    user_id             = Column(String(36), ForeignKey("users.id"), nullable=False)
    stripe_customer_id  = Column(String(100), default="")
    stripe_sub_id       = Column(String(100), default="")
    tier                = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    status              = Column(String(50), default="active")  # active | cancelled | past_due
    current_period_end  = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    event_type = Column(String(100), nullable=False)
    properties = Column(Text, default="{}")  # JSON stored as string
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", foreign_keys=[user_id])
# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────

async def init_db():
    """Create all tables. Call on app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
