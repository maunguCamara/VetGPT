# VetGPT Phase 1 — Complete End-to-End Test Checklist

Run every item in order. Each section must pass before moving to the next.
Mark each ✅ as you go. Do not proceed to Phase 2 until all items are ✅.

---

## SETUP VERIFICATION

- [ ] Python 3.11+ installed: `python --version`
- [ ] Virtual environment active: `source venv/bin/activate`
- [ ] All backend deps installed: `pip install -r requirements.txt -r requirements_backend.txt`
- [ ] `.env` file exists and configured (copy from `.env.example`)
- [ ] `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` set in `.env`
- [ ] `SECRET_KEY` changed from default placeholder in `.env`
- [ ] `data/pdfs/` folder exists
- [ ] `data/chroma_db/` folder exists

---

## SECTION 1 — INGESTION PIPELINE

### 1A — PDF Parser
```bash
# Drop any vet PDF into data/pdfs/ first, then:
python -c "
from ingestion.pdf_parser import VetPDFParser
p = VetPDFParser()
doc = p.parse_directory('data/pdfs/')
print(f'Parsed {len(doc)} documents')
for d in doc:
    print(f'  {d.filename}: {d.total_pages} pages, {d.total_words:,} words')
"
```
- [ ] No import errors
- [ ] At least 1 document parsed
- [ ] Page count > 0 for each document
- [ ] Word count > 100 for each document
- [ ] Metadata dict contains `title`, `filename`, `source`

### 1B — Chunker
```bash
python -c "
from ingestion.pdf_parser import VetPDFParser
from ingestion.chunker import VetChunker
docs = VetPDFParser().parse_directory('data/pdfs/')
chunks = VetChunker().chunk_documents(docs)
print(f'Total chunks: {len(chunks):,}')
print(f'Sample chunk: {chunks[0].text[:100]}')
print(f'Sample ID: {chunks[0].chunk_id}')
"
```
- [ ] Chunks generated (expect 50-500 per PDF page)
- [ ] Each chunk has `chunk_id`, `text`, `source_file`, `page_number`
- [ ] Chunk text is 30-600 characters
- [ ] No duplicate chunk IDs

### 1C — Embedder + ChromaDB
```bash
python ingest.py ingest --dir data/pdfs/
```
- [ ] No errors during embedding
- [ ] Progress bar completes
- [ ] `data/chroma_db/` folder has files in it

```bash
python ingest.py stats
```
- [ ] Shows total chunks > 0
- [ ] Collection name is `vet_manuals`

```bash
python ingest.py list-sources
```
- [ ] Lists the PDF filenames you ingested

### 1D — Vector Search Quality
```bash
python ingest.py query "canine parvovirus treatment"
python ingest.py query "feline hyperthyroidism diagnosis"
python ingest.py query "bovine respiratory disease"
python ingest.py query "drug dosage antibiotic dog"
python ingest.py query "equine colic surgery"
```
- [ ] Each query returns results (not empty)
- [ ] Top result score > 0.3
- [ ] Results are relevant to the query (read the excerpts)
- [ ] Source file and page number shown for each result

### 1E — Book Registry Auto-Detection
```bash
python -c "
from config.book_registry import detect_book, print_registry_summary
print_registry_summary()
# Test auto-detection:
import os
for f in os.listdir('data/pdfs/'):
    book = detect_book(f)
    print(f'{f} -> {book.short_title if book else \"UNKNOWN\"}')
"
```
- [ ] Registry summary prints 30+ books
- [ ] PDFs in `data/pdfs/` are detected where filename matches registry

---

## SECTION 2 — WEB SCRAPERS

### 2A — eClinPath Scraper
```bash
python scrape.py eclinpath
```
- [ ] Scraper starts without error
- [ ] Articles collected from at least 3 sections
- [ ] Cache file created at `data/scraped/eclinpath/articles.jsonl`
- [ ] At least 20 articles scraped
- [ ] Articles have `title`, `text`, `section` fields

### 2B — WikiVet Scraper
```bash
python scrape.py wikivet
```
- [ ] API requests succeed (not 404/403)
- [ ] At least 100 articles collected
- [ ] Cache file created at `data/scraped/wikivet/articles.jsonl`

### 2C — PubMed Scraper
```bash
python scrape.py pubmed
```
- [ ] NCBI API responds without error
- [ ] At least 50 abstracts fetched
- [ ] Cache file created at `data/scraped/pubmed/articles.jsonl`

### 2D — FAO Scraper
```bash
python scrape.py fao
```
- [ ] PDFs downloaded to `data/pdfs/fao/`
- [ ] Cache file created at `data/scraped/fao/documents.jsonl`

### 2E — Full Pipeline Run
```bash
python scrape.py run-all
```
- [ ] All 4 scrapers run to completion
- [ ] Summary table shows chunks indexed for each source
- [ ] ChromaDB total chunks increases

### 2F — Post-Scrape Query Test
```bash
python ingest.py stats
python scrape.py test-query "packed cell volume interpretation"
python scrape.py test-query "bovine foot and mouth disease control"
python scrape.py test-query "veterinary drug withdrawal period"
```
- [ ] Total chunks > 1,000 (ideally > 5,000)
- [ ] Queries return results from multiple sources
- [ ] eClinPath content appears in clinical pathology results

---

## SECTION 3 — FASTAPI BACKEND

### 3A — Server Start
```bash
uvicorn backend.main:app --reload --port 8000
```
- [ ] Server starts without error
- [ ] Output shows: `Application startup complete`
- [ ] Output shows ChromaDB chunk count on startup
- [ ] No import errors in terminal

### 3B — Swagger UI
Open: `http://localhost:8000/docs`
- [ ] Swagger UI loads in browser
- [ ] All routes visible: `/api/auth/register`, `/api/auth/login`, `/api/auth/me`, `/api/query`, `/api/query/stream`, `/api/query/history`, `/api/health`

### 3C — Health Check
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/full
```
- [ ] `/api/health` returns `{"status": "ok"}`
- [ ] `/api/health/full` shows `chroma_chunks` > 0
- [ ] `/api/health/full` shows `anthropic_ready: true` (or openai)

### 3D — Auth Flow via Swagger
Using Swagger UI (`/docs`):
1. POST `/api/auth/register` with email + password + full_name
   - [ ] Returns 201 with `access_token`
   - [ ] User `tier` is `"free"`
2. Click "Authorize" button, paste the token
3. GET `/api/auth/me`
   - [ ] Returns your user profile
4. POST `/api/auth/login` with same email + password
   - [ ] Returns 200 with new token
5. POST `/api/auth/login` with wrong password
   - [ ] Returns 401

### 3E — RAG Query via Swagger
POST `/api/query`:
```json
{"query": "What are the symptoms of canine parvovirus?", "top_k": 5}
```
- [ ] Returns 200
- [ ] `answer` field is non-empty and clinically relevant
- [ ] `citations` list has at least 1 entry
- [ ] Each citation has `document_title`, `page_number`, `score`
- [ ] `disclaimer` field is present
- [ ] `latency_ms` is a positive integer

Additional queries to test:
- [ ] `"feline hyperthyroidism methimazole dose"` → relevant drug info
- [ ] `"bovine respiratory disease BRD antibiotic"` → treatment info
- [ ] `"x"` (too short) → 422 validation error
- [ ] Very long string (2001 chars) → 422 validation error
- [ ] Empty `query` field → 422 validation error

### 3F — Query History
After making 3+ queries via `/api/query`:
GET `/api/query/history`
- [ ] Returns list of past queries
- [ ] Each item has `query_text`, `answer_text`, `created_at`
- [ ] Unauthenticated request → 401

### 3G — Rate Limiting
```bash
# Run 25 rapid queries (exceeds free tier limit of 20/min)
for i in {1..25}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    http://localhost:8000/api/query \
    -H "Content-Type: application/json" \
    -d '{"query":"test query"}';
done
```
- [ ] First 20 return 200
- [ ] Later ones return 429 (Too Many Requests)

### 3H — Automated Test Suite
```bash
pip install pytest httpx pytest-asyncio
pytest tests/test_phase1_e2e.py -v
```
- [ ] All non-integration tests pass
- [ ] Integration tests pass if LLM key is set
- [ ] Zero test failures (skips are OK if DB is empty)

Expected output:
```
tests/test_phase1_e2e.py::TestPDFParser::test_import                    PASSED
tests/test_phase1_e2e.py::TestPDFParser::test_parser_initialises        PASSED
tests/test_phase1_e2e.py::TestChunker::test_chunk_document_...          PASSED
tests/test_phase1_e2e.py::TestVectorStore::test_add_and_query           PASSED
tests/test_phase1_e2e.py::TestBookRegistry::test_registry_loads         PASSED
tests/test_phase1_e2e.py::TestAuth::test_password_hash_and_verify       PASSED
tests/test_phase1_e2e.py::TestAuth::test_jwt_encode_decode              PASSED
tests/test_phase1_e2e.py::TestHealthEndpoints::test_health_ok           PASSED
tests/test_phase1_e2e.py::TestAuthEndpoints::test_register_success      PASSED
tests/test_phase1_e2e.py::TestQueryEndpoints::test_query_authenticated  PASSED
...
```

---

## SECTION 4 — MOBILE APP CONNECTION

### 4A — Find Your Machine's IP
```bash
# Mac/Linux:
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows:
ipconfig | findstr IPv4
```
- [ ] IP found (e.g. `192.168.1.105`)

### 4B — Update API Base URL
In `vetgpt-mobile/lib/api.ts`:
```typescript
const LOCAL_BASE_URL = 'http://192.168.1.105:8000';  // your actual IP
```
- [ ] URL updated with real IP (not `localhost`)

### 4C — Run Mobile App
```bash
cd vetgpt-mobile
npm install
npx expo start
```
- [ ] Expo dev server starts
- [ ] QR code displayed
- [ ] No TypeScript errors in terminal

### 4D — Install on Device
- [ ] Expo Go installed on phone (iOS App Store / Google Play)
- [ ] Phone and laptop on same WiFi network
- [ ] QR code scanned → app opens on device

### 4E — Auth Flow on Device
- [ ] Register screen loads correctly
- [ ] Register with test email → redirected to chat tab
- [ ] All 4 tabs visible: Chat, Search, Manuals, Profile
- [ ] Profile shows correct email and tier (`free`)
- [ ] Sign out → redirected to login
- [ ] Login with same credentials → back to chat

### 4F — Chat Screen
- [ ] 5 suggested starter questions visible
- [ ] Tap a suggestion → query sends
- [ ] Answer streams in token by token
- [ ] Citation panel appears below answer
- [ ] Disclaimer text visible
- [ ] "New chat" button clears conversation

### 4G — Search Screen
- [ ] Search input accepts text
- [ ] Species filter chips tappable (Canine, Feline, Bovine...)
- [ ] Source filter chips tappable (WikiVet, PubMed...)
- [ ] Submit search → results appear
- [ ] Each result shows score %, title, page number, excerpt

### 4H — Manuals Screen
- [ ] Open access sources listed in green section
- [ ] Pending license sources listed and marked
- [ ] Tapping an available source → filter applied

### 4I — Offline Handling
Turn off phone WiFi:
- [ ] Offline banner appears (red bar at top)
- [ ] Sending a chat message shows helpful offline error
- [ ] App does not crash
Turn WiFi back on:
- [ ] Banner disappears
- [ ] Queries work again

---

## SECTION 5 — FINAL DATA QUALITY CHECKS

### 5A — Minimum Data Volume
```bash
python ingest.py stats
```
- [ ] Total chunks ≥ 1,000 (minimum viable)
- [ ] Total chunks ≥ 5,000 (recommended before Phase 2)

### 5B — Multi-Source Coverage
```bash
python ingest.py list-sources
```
- [ ] At least 2 different sources listed (e.g. wikivet + eclinpath)
- [ ] At least 1 PDF source listed

### 5C — Answer Quality Spot Check
For each query below, manually read the answer and rate it 1-5:
```bash
# Run via Swagger or curl
```
| Query | Min Score | Your Rating |
|-------|-----------|-------------|
| "Clinical signs of canine distemper" | 3/5 | |
| "Feline lower urinary tract disease treatment" | 3/5 | |
| "Bovine milk fever (hypocalcemia) treatment" | 3/5 | |
| "Equine strangles Streptococcus equi" | 3/5 | |
| "Packed cell volume interpretation dog" | 3/5 | |
| "Plumb's methimazole dosage cat" | 3/5 | |

- [ ] All queries score ≥ 3/5
- [ ] Answers cite sources (not hallucinating)
- [ ] No answers are completely off-topic

### 5D — Git Status
```bash
cd vetgpt && git status
cd vetgpt-mobile && git status
```
- [ ] `data/` folder not staged for commit
- [ ] `.env` not staged for commit
- [ ] `venv/` not staged for commit
- [ ] `node_modules/` not staged for commit
- [ ] `*.gguf` not staged for commit

---

## PHASE 1 SIGN-OFF

| Category | Status |
|----------|--------|
| PDF ingestion pipeline | ☐ |
| ChromaDB populated | ☐ |
| All scrapers working | ☐ |
| FastAPI backend running | ☐ |
| Auth flow working | ☐ |
| RAG queries returning answers | ☐ |
| Mobile app connected | ☐ |
| Offline handling working | ☐ |
| Automated tests passing | ☐ |
| Data quality acceptable | ☐ |
| Git repos clean | ☐ |

**All boxes checked? → You are ready for Phase 2 (Offline Mode).**
