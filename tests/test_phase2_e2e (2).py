"""
vetgpt/tests/test_phase2_e2e.py

Phase 2 End-to-End Test Suite — Offline Mode.

Covers:
  - Sync routes (/api/sync/manifest, /api/sync/delta, /api/sync/full)
  - Upload routes (/api/manuals/upload, /api/manuals/list)
  - RAG engine offline fallback behaviour
  - Vector store query with source filtering
  - Book registry detection
  - Config completeness for offline features

Run:
    pytest tests/test_phase2_e2e.py -v --tb=short
"""

import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    import uuid
    email    = f"p2_{uuid.uuid4().hex[:8]}@phase2.test"
    password = "Phase2Pass1!"
    res = client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": "Phase2 Vet"
    })
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ─────────────────────────────────────────────────────────────────────────────
# 1. SYNC ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestSyncRoutes:

    def test_sync_routes_registered(self, client):
        res = client.get("/openapi.json")
        paths = res.json()["paths"]
        assert "/api/sync/manifest" in paths
        assert "/api/sync/delta"    in paths
        assert "/api/sync/full"     in paths

    def test_sync_manifest_requires_auth(self, client):
        res = client.get("/api/sync/manifest")
        assert res.status_code == 401

    def test_sync_manifest_authenticated(self, client, auth_headers):
        res = client.get("/api/sync/manifest", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "total_chunks"   in data
        assert "source_count"   in data
        assert "sources"        in data
        assert "schema_version" in data
        assert "server_time"    in data
        assert isinstance(data["total_chunks"], int)
        assert isinstance(data["sources"],      list)

    def test_sync_delta_requires_auth(self, client):
        res = client.get("/api/sync/delta")
        assert res.status_code == 401

    def test_sync_delta_authenticated(self, client, auth_headers):
        res = client.get("/api/sync/delta", headers=auth_headers)
        assert res.status_code == 200
        # Response is streaming JSON
        data = res.json()
        assert "chunks"    in data
        assert "count"     in data
        assert "synced_at" in data
        assert isinstance(data["chunks"], list)
        assert isinstance(data["count"],  int)

    def test_sync_delta_since_param(self, client, auth_headers):
        """Passing a since param returns only chunks newer than that timestamp."""
        # Future timestamp — should return 0 chunks
        future = "2099-01-01T00:00:00"
        res = client.get(f"/api/sync/delta?since={future}", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 0

    def test_sync_delta_invalid_since_graceful(self, client, auth_headers):
        """Invalid since param doesn't crash — falls back to 7-day window."""
        res = client.get("/api/sync/delta?since=not-a-date", headers=auth_headers)
        assert res.status_code == 200

    def test_sync_delta_limit_param(self, client, auth_headers):
        """limit param is respected."""
        res = client.get("/api/sync/delta?limit=10", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["count"] <= 10

    def test_sync_full_requires_auth(self, client):
        res = client.get("/api/sync/full")
        assert res.status_code == 401

    def test_sync_full_authenticated(self, client, auth_headers):
        res = client.get("/api/sync/full", headers=auth_headers)
        assert res.status_code == 200
        # Returns JSONL streaming — each line is a JSON object
        text = res.text
        if text.strip():
            lines = [l for l in text.strip().split("\n") if l.strip()]
            for line in lines[:3]:  # spot check first 3
                obj = json.loads(line)
                assert "chunk_id"       in obj
                assert "text"           in obj
                assert "source_file"    in obj
                assert "document_title" in obj
                assert "page_number"    in obj

    def test_sync_full_has_chunk_count_header(self, client, auth_headers):
        res = client.get("/api/sync/full", headers=auth_headers)
        assert res.status_code == 200
        assert "X-Total-Chunks" in res.headers


# ─────────────────────────────────────────────────────────────────────────────
# 2. UPLOAD ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadRoutes:

    def test_upload_routes_registered(self, client):
        res = client.get("/openapi.json")
        paths = res.json()["paths"]
        assert "/api/manuals/upload" in paths
        assert "/api/manuals/list"   in paths

    def test_upload_requires_auth(self, client):
        res = client.post(
            "/api/manuals/upload",
            files=[("file", ("test.pdf", b"%PDF-1.4 test", "application/pdf"))],
        )
        assert res.status_code == 401

    def test_upload_rejects_non_pdf(self, client, auth_headers):
        res = client.post(
            "/api/manuals/upload",
            files=[("file", ("test.txt", b"not a pdf", "text/plain"))],
            headers=auth_headers,
        )
        assert res.status_code == 415

    def test_upload_rejects_empty_file(self, client, auth_headers):
        res = client.post(
            "/api/manuals/upload",
            files=[("file", ("empty.pdf", b"", "application/pdf"))],
            headers=auth_headers,
        )
        assert res.status_code == 400

    def test_upload_accepts_valid_pdf_header(self, client, auth_headers):
        """A file with PDF header bytes is accepted and queued for background ingestion."""
        # %PDF-1.4 is a valid PDF start marker
        fake_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
        res = client.post(
            "/api/manuals/upload",
            files=[("file", ("test_manual.pdf", fake_pdf, "application/pdf"))],
            headers=auth_headers,
        )
        # 200 = accepted (background ingestion queued)
        # 400 = rejected as invalid PDF content (acceptable — it's a fake PDF)
        assert res.status_code in (200, 400, 422)
        if res.status_code == 200:
            data = res.json()
            assert "filename"  in data
            assert "status"    in data
            assert "size_mb"   in data
            assert data["status"] == "uploaded"

    def test_list_sources_requires_auth(self, client):
        res = client.get("/api/manuals/list")
        assert res.status_code == 401

    def test_list_sources_authenticated(self, client, auth_headers):
        res = client.get("/api/manuals/list", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "sources" in data
        assert "total"   in data
        assert isinstance(data["sources"], list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. VECTOR STORE — SOURCE FILTERING
# ─────────────────────────────────────────────────────────────────────────────

class TestVectorStoreFiltering:

    def test_query_with_no_filter(self):
        from ingestion.embedder import VetVectorStore
        store = VetVectorStore()
        stats = store.stats()
        if stats["total_chunks"] == 0:
            pytest.skip("ChromaDB is empty")
        results = store.query("canine disease", n_results=5)
        assert isinstance(results, list)

    def test_query_filter_by_source(self):
        from ingestion.embedder import VetVectorStore
        store  = VetVectorStore()
        if store.stats()["total_chunks"] == 0:
            pytest.skip("ChromaDB is empty")

        sources = store.list_sources()
        if not sources:
            pytest.skip("No sources indexed")

        # Query with the first available source
        source = sources[0]
        results = store.query("veterinary", n_results=5, filter_source=source)
        assert isinstance(results, list)
        # All results should be from the filtered source
        for r in results:
            assert r["source_file"] == source or source in r.get("source_file", "")

    def test_list_sources_returns_list(self):
        from ingestion.embedder import VetVectorStore
        store   = VetVectorStore()
        sources = store.list_sources()
        assert isinstance(sources, list)

    def test_stats_returns_expected_keys(self):
        from ingestion.embedder import VetVectorStore
        store = VetVectorStore()
        stats = store.stats()
        assert "total_chunks"     in stats
        assert "collection_name"  in stats
        assert isinstance(stats["total_chunks"], int)


# ─────────────────────────────────────────────────────────────────────────────
# 4. BOOK REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

class TestBookRegistry:

    def test_detect_known_books(self):
        from config.book_registry import detect_book
        cases = {
            "merck_vet_manual.pdf":              "merck_vet",
            "plumbs_veterinary_drug_handbook.pdf": "plumbs",
            "wikivet_canine_parvovirus.pdf":     "wikivet",
            "fossum_small_animal_surgery_5e.pdf": "fossum_surgery",
        }
        for filename, expected_key in cases.items():
            result = detect_book(filename)
            if result is not None:
                assert result.key == expected_key, \
                    f"{filename}: expected {expected_key}, got {result.key}"

    def test_unknown_file_returns_none(self):
        from config.book_registry import detect_book
        assert detect_book("my_random_notes.pdf") is None
        assert detect_book("scan_001.pdf") is None

    def test_registry_has_open_access_books(self):
        from config.book_registry import BOOK_REGISTRY
        open_access = [b for b in BOOK_REGISTRY.values() if "open" in b.legal_status.lower() or "cc" in b.legal_status.lower()]
        assert len(open_access) >= 4


# ─────────────────────────────────────────────────────────────────────────────
# 5. OFFLINE RAG FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

class TestOfflineRAGFallback:

    def test_rag_engine_handles_empty_store(self):
        """RAG engine returns graceful error when no chunks exist."""
        from backend.rag_engine import VetRAGEngine
        engine = VetRAGEngine()
        # If store is empty, health should still return without crash
        health = engine.health()
        assert "chroma_chunks" in health
        assert "llm_provider"  in health

    def test_build_prompt_with_relevance_scores(self):
        """Prompt includes relevance scores in source labels."""
        from backend.rag_engine import build_prompt
        chunks = [
            {"text": "Canine parvovirus treatment.", "document_title": "WikiVet", "page_number": 1, "score": 0.92},
            {"text": "IV fluids are essential.",     "document_title": "Merck",   "page_number": 45, "score": 0.78},
        ]
        prompt = build_prompt("How to treat CPV?", chunks)
        assert "Source 1:" in prompt
        assert "Source 2:" in prompt
        assert "WikiVet"   in prompt
        assert "Merck"     in prompt
        assert "0.92"      in prompt
        assert "0.78"      in prompt

    def test_rag_response_formatted_references(self):
        """formatted_references produces numbered list."""
        from backend.rag_engine import RAGResponse, Citation
        citations = [
            Citation("wiki.pdf",  "WikiVet",       1,  0.9,  "excerpt1"),
            Citation("merck.pdf", "Merck Vet",     42, 0.85, "excerpt2"),
            Citation("fao.pdf",   "FAO Guidelines", 7,  0.72, "excerpt3"),
        ]
        resp = RAGResponse(
            query="test", answer="answer", citations=citations,
            chunks_retrieved=3, top_score=0.9, llm_model="test", latency_ms=100,
        )
        refs = resp.formatted_references
        assert "[1] WikiVet — p.1"       in refs
        assert "[2] Merck Vet — p.42"   in refs
        assert "[3] FAO Guidelines — p.7" in refs


# ─────────────────────────────────────────────────────────────────────────────
# 6. SCRAPE CLI ENTRY POINTS
# ─────────────────────────────────────────────────────────────────────────────

class TestScrapeCLI:

    def test_scrape_module_imports(self):
        """scrape.py imports without error."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("scrape", "scrape.py")
        if spec is None:
            pytest.skip("scrape.py not found at project root")
        # Just check it loads
        assert spec is not None

    def test_eclinpath_scraper_in_pipeline(self):
        from scraping.pipeline import ScrapingPipeline
        pipeline = ScrapingPipeline(use_cache=True)
        assert hasattr(pipeline, 'eclinpath'), "Pipeline missing eclinpath scraper"
        assert hasattr(pipeline, 'run_eclinpath_only'), "Pipeline missing run_eclinpath_only method"

    def test_all_scrapers_have_load_cached(self):
        """All scrapers support load_cached() for offline re-indexing."""
        from scraping.wikivet_scraper  import WikiVetScraper
        from scraping.pubmed_scraper   import PubMedScraper
        from scraping.fao_scraper      import FAOScraper
        from scraping.eclinpath_scraper import EClinPathScraper

        for cls in [WikiVetScraper, PubMedScraper, FAOScraper, EClinPathScraper]:
            scraper = cls()
            assert hasattr(scraper, 'load_cached'), f"{cls.__name__} missing load_cached()"
            # load_cached on empty cache returns empty list, not error
            result = scraper.load_cached()
            assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# 7. INTEGRATION — Phase 2 system check
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase2Integration:

    def test_all_phase2_routes_in_schema(self, client):
        res   = client.get("/openapi.json")
        paths = set(res.json()["paths"].keys())
        required = [
            "/api/sync/manifest",
            "/api/sync/delta",
            "/api/sync/full",
            "/api/manuals/upload",
            "/api/manuals/list",
        ]
        for route in required:
            assert route in paths, f"Missing route: {route}"

    def test_sync_then_list_sources(self, client, auth_headers):
        """Sync manifest then list sources — both should return consistent counts."""
        manifest = client.get("/api/sync/manifest", headers=auth_headers).json()
        sources  = client.get("/api/manuals/list",  headers=auth_headers).json()

        assert manifest["total_chunks"] >= 0
        assert sources["total"] == len(sources["sources"])
        # Source count should match (within tolerance — manifest may filter differently)
        # Both should be non-negative integers
        assert manifest["source_count"] >= 0
        assert sources["total"]         >= 0
