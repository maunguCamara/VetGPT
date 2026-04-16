"""
vetgpt/backend/config.py

Centralised settings loaded from .env file.
All backend config lives here — no scattered os.getenv() calls.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "VetGPT API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"  # development | production

    # Auth
    secret_key: str = "change-this-in-production-min-32-chars!!"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/vetgpt.db"

    # LLM
    llm_provider: str = "anthropic"           # anthropic | openai
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model_anthropic: str = "claude-sonnet-4-5"
    llm_model_openai: str = "gpt-4o"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.1              # low temp = factual, consistent

    # RAG
    rag_top_k: int = 5                        # chunks to retrieve per query
    rag_min_score: float = 0.3               # minimum similarity score
    chroma_db_path: str = "./data/chroma_db"
    chroma_collection_name: str = "vet_manuals"
    embedding_provider: str = "local"         # local | openai

    # Rate limiting
    rate_limit_free: str = "20/minute"
    rate_limit_premium: str = "100/minute"

    # Premium features
    premium_features: list[str] = ["xray", "image_recognition", "advanced_ocr"]

    admin_emails: str = "camara@admin.com"  # comma-separated list of admin emails

    #Stripe Billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_premium_monthly: str = ""
    stripe_price_clinic_monthly: str = ""
    stripe_success_url: str = "vetgpt://billing/success"
    stripe_cancel_url: str = "vetgpt://billing/cancel"
    stripe_portal_return_url: str = "vetgpt://profile"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
