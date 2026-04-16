"""
vetgpt/backend/config.py

Centralised settings loaded from .env file.
All backend config lives here — no scattered os.getenv() calls.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    # ── App ───────────────────────────────────────────────────────────────────
    app_name:    str  = "VetGPT API"
    app_version: str  = "1.0.0"
    debug:       bool = False
    environment: str  = "development"   # development | production

    # ── Auth ──────────────────────────────────────────────────────────────────
    secret_key:                  str = "change-this-in-production-min-32-chars!!"
    algorithm:                   str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7   # 7 days

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/vetgpt.db"

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider:        str   = "anthropic"           # anthropic | openai
    anthropic_api_key:   str   = ""
    openai_api_key:      str   = ""
    llm_model_anthropic: str   = "claude-sonnet-4-5"
    llm_model_openai:    str   = "gpt-4o"
    llm_max_tokens:      int   = 1500
    llm_temperature:     float = 0.1

    # ── RAG ───────────────────────────────────────────────────────────────────
    rag_top_k:             int   = 5
    rag_min_score:         float = 0.3
    chroma_db_path:        str   = "./data/chroma_db"
    chroma_collection_name:str   = "vet_manuals"
    embedding_provider:    str   = "local"             # local | openai

    # ── Language ──────────────────────────────────────────────────────────────
    # Supported query languages — Qwen2.5-3B handles these natively
    # The LLM detects the input language and responds in kind.
    # No translation layer is needed; Claude and Qwen are multilingual.
    supported_languages: str = "en,sw,fr,ar,pt,es,zh"   # comma-separated ISO-639-1
    default_language:    str = "en"
    auto_detect_language:bool = True

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_free:    str = "20/minute"
    rate_limit_premium: str = "100/minute"

    # ── Admin ─────────────────────────────────────────────────────────────────
    admin_emails: str = ""    # comma-separated admin email addresses

    # ── Premium / Vision ──────────────────────────────────────────────────────
    google_ai_api_key:                str = ""
    google_cloud_project_id:          str = ""
    google_cloud_location:            str = "us"
    google_document_ai_processor_id:  str = ""
    google_application_credentials:   str = ""

    # ── Scraping ──────────────────────────────────────────────────────────────
    ncbi_api_key: str = ""

    # ── Stripe Billing ────────────────────────────────────────────────────────
    stripe_secret_key:            str = ""
    stripe_webhook_secret:        str = ""
    stripe_price_premium_monthly: str = ""
    stripe_price_clinic_monthly:  str = ""
    stripe_success_url:           str = "vetgpt://billing/success"
    stripe_cancel_url:            str = "vetgpt://billing/cancel"
    stripe_portal_return_url:     str = "vetgpt://profile"

    class Config:
        env_file          = ".env"
        env_file_encoding = "utf-8"
        extra             = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
