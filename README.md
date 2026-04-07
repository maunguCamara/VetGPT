# VetGPT — Backend

AI-powered veterinary reference tool. RAG pipeline over vet manuals,
research abstracts, and open-access sources — served via FastAPI.

---

## Project Structure

```
vetgpt/
│
├── ingestion/                        # Phase 1 — PDF pipeline
│   ├── __init__.py                   # Module exports
│   ├── pdf_parser.py                 # Parse PDFs → clean text + metadata
│   ├── pdf_parser_v2.py              # Extended parser with book registry detection
│   ├── chunker.py                    # Split text → chunks with full provenance
│   └── embedder.py                   # Embed chunks → ChromaDB (local or OpenAI)
│
├── scraping/                         # Phase 1 — Web scrapers
│   ├── __init__.py
│   ├── wikivet_scraper.py            # WikiVet CC BY-SA — MediaWiki API
│   ├── pubmed_scraper.py             # PubMed — NCBI E-utilities API (public domain)
│   ├── fao_scraper.py                # FAO animal health — open access PDFs + HTML
│   └── pipeline.py                   # Orchestrator — runs all scrapers → ChromaDB
│
├── config/                           # Phase 1 — Configuration
│   ├── __init__.py
│   └── book_registry.py              # 35 vet books: metadata, citations, legal status
│
├── backend/                          # Phase 1 — FastAPI server
│   ├── __init__.py
│   ├── main.py                       # App entry point, CORS, rate limiting, lifespan
│   ├── config.py                     # Pydantic settings loaded from .env
│   ├── database.py                   # SQLAlchemy models: User, QueryLog, Subscription
│   ├── auth.py                       # JWT auth, bcrypt hashing, FastAPI dependencies
│   ├── rag_engine.py                 # Core RAG: ChromaDB retrieval → LLM → response
│   └── routes.py                     # All API endpoints (auth, query, history, health)
│
├── data/                             # Runtime data — never commit
│   ├── pdfs/                         # Drop your vet manual PDFs here
│   │   └── fao/                      # FAO PDFs auto-downloaded here
│   ├── chroma_db/                    # ChromaDB vector store (auto-created)
│   ├── scraped/                      # Scraper cache (auto-created)
│   │   ├── wikivet/articles.jsonl
│   │   ├── pubmed/articles.jsonl
│   │   └── fao/documents.jsonl
│   └── vetgpt.db                     # SQLite user/query database (auto-created)
│
├── venv/                             # Virtual environment — never commit
│
├── ingest.py                         # CLI: PDF ingestion pipeline
├── scrape.py                         # CLI: web scraping pipeline
├── requirements.txt                  # Ingestion + scraping dependencies
├── requirements_backend.txt          # FastAPI backend dependencies
├── .env.example                      # Environment variable template
├── .env                              # Your config — NEVER commit
└── .gitignore
```

---

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# 2. Install all dependencies
pip install -r requirements.txt
pip install -r requirements_backend.txt

# 3. Configure environment
cp .env.example .env
# Open .env and set:
#   ANTHROPIC_API_KEY=sk-ant-...
#   SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# 4. Create data directories
mkdir -p data/pdfs data/chroma_db data/scraped

# 5. Ingest your first PDF
python ingest.py ingest --pdf data/pdfs/your_vet_manual.pdf

# 6. Start the API server
uvicorn backend.main:app --reload --port 8000

# 7. Open Swagger UI
open http://localhost:8000/docs
```

---

## Ingestion Pipeline

### PDF Ingestion

```bash
# Ingest a single PDF
python ingest.py ingest --pdf data/pdfs/merck_vet_manual.pdf

# Ingest an entire folder (recursive)
python ingest.py ingest --dir data/pdfs/

# Test retrieval
python ingest.py query "treatment for canine parvovirus"
python ingest.py query "drug dosage for feline hyperthyroidism" --n 3
python ingest.py query "bovine respiratory disease" --source merck_vet_manual.pdf

# Manage the index
python ingest.py stats
python ingest.py list-sources
python ingest.py delete merck_vet_manual.pdf   # remove before re-indexing
```

### Web Scraping

```bash
# Scrape all open-access sources (WikiVet + PubMed + FAO)
python scrape.py run-all

# Individual sources
python scrape.py wikivet
python scrape.py pubmed
python scrape.py pubmed --api-key YOUR_NCBI_KEY   # 10 req/s vs 3 req/s free
python scrape.py fao

# Re-index from local cache (no network calls)
python scrape.py from-cache

# Test results
python scrape.py test-query "canine parvovirus treatment"
python scrape.py test-query "bovine respiratory disease" --source wikivet
```

### How it works

```
PDF files / Web sources
        │
        ▼
VetPDFParser / Scrapers     → Extract clean text + metadata
        │                      pdf_parser_v2: auto-detect book from filename
        │                      Strip headers, footers, page numbers
        │                      Handle multi-column layouts
        │
        ▼
VetChunker                  → Split into ~512-char chunks
        │                      64-char overlap (no answer lost at boundaries)
        │                      Each chunk tagged: source, page, title, citation
        │
        ▼
VetVectorStore              → Embed (local sentence-transformers or OpenAI)
                               Upsert to ChromaDB (idempotent — safe to re-run)
                               Persisted to data/chroma_db/
```

---

## FastAPI Backend

### Running

```bash
# Development (auto-reload on file change)
uvicorn backend.main:app --reload --port 8000

# Production
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/register` | None | Create account → returns JWT |
| POST | `/api/auth/login` | None | Login → returns JWT |
| GET | `/api/auth/me` | JWT | Get current user profile |
| POST | `/api/query` | Optional | RAG query — standard response |
| POST | `/api/query/stream` | Optional | RAG query — streaming SSE |
| POST | `/api/query/image` | Premium JWT | Image + OCR query (Phase 3 stub) |
| GET | `/api/query/history` | JWT | User's query history |
| GET | `/api/health` | None | Public health check |
| GET | `/api/health/full` | None | DB + ChromaDB stats |

### Example query

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "treatment for canine parvovirus", "top_k": 5}'
```

```json
{
  "query": "treatment for canine parvovirus",
  "answer": "Treatment is primarily supportive...",
  "citations": [
    {
      "document_title": "WikiVet Veterinary Encyclopedia",
      "page_number": 1,
      "score": 0.89,
      "excerpt": "Canine parvovirus treatment involves..."
    }
  ],
  "chunks_retrieved": 5,
  "top_score": 0.89,
  "llm_model": "claude-sonnet-4-5",
  "latency_ms": 1243,
  "disclaimer": "⚠️ AI-generated reference. Verify with a licensed veterinarian."
}
```

### Rate limits by tier

| Tier | Limit | top_k cap |
|------|-------|-----------|
| Unauthenticated | 5/min | 3 |
| Free | 20/min | 5 |
| Premium / Clinic | 100/min | 20 |

---

## Book Registry

35 veterinary titles registered in `config/book_registry.py`:

```python
from config.book_registry import detect_book, books_by_species, print_registry_summary

# Auto-detect book from PDF filename — used by pdf_parser_v2
book = detect_book("fossum_small_animal_surgery_5e.pdf")
# → BookMeta(key='fossum_surgery', publisher='Elsevier', legal_status='pending_license')

# Filter by species
equine_books = books_by_species("equine")

# Print full registry table in terminal
python config/book_registry.py
```

### Legal status summary

| Status | Count | Examples |
|--------|-------|---------|
| ✅ Open access | 6 | WikiVet, FAO, OIE/WOAH, eClinPath, Extension Guides, Liautard (pre-1928) |
| ⏳ Pending license | 28 | Elsevier (14 titles), Wiley/Blackwell (10), Merck, Plumb's, VIN |
| 🔵 Personal use only | 1 | Crow & Walshaw |

**Licensing priority:** Plumb's → Merck (has existing API program) → Elsevier (one deal covers 14 titles) → Wiley/Blackwell

---

## Embeddings

```bash
# Default: local sentence-transformers — offline capable, no API key
EMBEDDING_PROVIDER=local

# Better vet accuracy: biomedical-tuned model
# Edit ingestion/embedder.py:
model_name="pritamdeka/S-PubMedBert-MS-MARCO"

# Production: OpenAI text-embedding-3-small
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

---

## Environment Variables (.env)

```bash
# App
DEBUG=false
ENVIRONMENT=development

# Auth
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-64-char-random-string-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080       # 7 days

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/vetgpt.db
# Prod: DATABASE_URL=postgresql+asyncpg://user:pass@localhost/vetgpt

# LLM
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...                   # optional fallback
LLM_MODEL_ANTHROPIC=claude-sonnet-4-5
LLM_MODEL_OPENAI=gpt-4o
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0.1

# RAG
RAG_TOP_K=5
RAG_MIN_SCORE=0.3
CHROMA_DB_PATH=./data/chroma_db
CHROMA_COLLECTION_NAME=vet_manuals
EMBEDDING_PROVIDER=local

# Scraping
NCBI_API_KEY=                           # free at ncbi.nlm.nih.gov/account
```

---

## .gitignore

```
venv/
data/
.env
__pycache__/
*.pyc
*.db
.chroma/
*.gguf
*.bin
```

---

## Data Sources

| Source | License | Type | Scraper |
|--------|---------|------|---------|
| WikiVet | CC BY-SA | Encyclopedia | `wikivet_scraper.py` |
| PubMed / NCBI | Public Domain | Research abstracts | `pubmed_scraper.py` |
| FAO Animal Health | Open Access | Manuals + PDFs | `fao_scraper.py` |
| OIE / WOAH | Open Access | Disease codes | Manual PDF download |
| eClinPath (Cornell) | Open Access | Clinical pathology | Pending scraper |
| Your own PDFs | You own them | Any vet manual | `ingest.py` |
| Merck Vet Manual | Pending license | Core reference | Pending |
| Plumb's Drug Handbook | Pending license | Drug dosages | Pending |
| Elsevier titles (14) | Pending license | Textbooks | Pending |
| Wiley/Blackwell (10) | Pending license | Textbooks | Pending |

---

## Phase Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | PDF ingestion pipeline | ✅ Complete |
| 1 | WikiVet scraper | ✅ Complete |
| 1 | PubMed scraper | ✅ Complete |
| 1 | FAO scraper | ✅ Complete |
| 1 | Book registry (35 titles) | ✅ Complete |
| 1 | FastAPI backend + RAG engine | ✅ Complete |
| 1 | JWT auth + user management | ✅ Complete |
| 1 | Query logging | ✅ Complete |
| 1 | eClinPath scraper | ⏳ Pending |
| 1 | End-to-end integration test | ⏳ Pending |
| 2 | On-device Qwen2.5-3B offline | 🔄 In progress (mobile side built) |
| 3 | OCR — Google ML Kit | 🔲 Planned |
| 3 | Image recognition (premium) | 🔲 Planned |
| 3 | X-ray vision (premium) | 🔲 Planned |

---

## Before Moving to Phase 2

Complete these 5 checks:

```bash
# 1. Ingest a test PDF and confirm chunks appear
python ingest.py ingest --pdf data/pdfs/any_vet_doc.pdf
python ingest.py stats
# → Should show chunk count > 0

# 2. Test RAG query returns an answer
python ingest.py query "veterinary treatment"

# 3. Start backend and confirm Swagger UI loads
uvicorn backend.main:app --reload --port 8000
# → Open http://localhost:8000/docs

# 4. Register a user and run a query via Swagger
# POST /api/auth/register → copy the token
# POST /api/query with Authorization: Bearer <token>

# 5. Run WikiVet scraper and confirm articles index
python scrape.py wikivet
python ingest.py stats
# → Chunk count should increase significantly
```
