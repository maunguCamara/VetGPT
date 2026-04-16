# vetgpt/Dockerfile
# Multi-stage build for production FastAPI backend

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for PyMuPDF and other native libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_backend.txt ./
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    -r requirements_backend.txt \
    stripe


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/     ./backend/
COPY ingestion/   ./ingestion/
COPY scraping/    ./scraping/
COPY config/      ./config/
COPY alembic/     ./alembic/

# Create data directories
RUN mkdir -p data/pdfs data/chroma_db data/scraped data/pdfs/uploaded

# Non-root user for security
RUN useradd -m -u 1000 vetgpt && chown -R vetgpt:vetgpt /app
USER vetgpt

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
