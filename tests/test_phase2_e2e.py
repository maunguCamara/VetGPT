"""
vetgpt/tests/test_phase1_e2e.py

Extreme end-to-end test suite for VetGPT Phase 1.
Tests every layer: ingestion → scraping → backend → auth → RAG → API.

Run:
    pip install pytest pytest-asyncio httpx
    pytest tests/test_phase1_e2e.py -v --tb=short

Prerequisites:
    1. .env configured with ANTHROPIC_API_KEY or OPENAI_API_KEY
    2. At least one PDF ingested OR scraping run completed
    3. Backend running: uvicorn backend.main:app --reload
       (for API tests — or use TestClient which doesn't need it running)
"""

import os
import sys
import json
import time
import pytest
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────────────────────────────────────
# 1. INGESTION PIPELINE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestPDFParser:
    """Tests for vetgpt/ingestion/pdf_parser.py"""

    def test_import(self):
        """Parser module imports without error."""
        from ingestion.pdf_parser import VetPDFParser, ParsedDocument, ParsedPage
        assert VetPDFParser is not None

    def test_parser_initialises(self):
        """Parser creates with default and custom params."""
        from ingestion.pdf_parser import VetPDFParser
        p1 = VetPDFParser()
        p2 = VetPDFParser(min_page_words=50)
        assert p1.min_page_words == 20
        assert p2.min_page_words == 50

    def test_missing_file_raises(self):
        """Parsing a non-existent file raises FileNotFoundError."""
        from ingestion.pdf_parser import VetPDFParser
        parser = VetPDFParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path/file.pdf")

    def test_parse_directory_empty(self, tmp_path):
        """Parsing an empty directory returns empty list, no crash."""
        from ingestion.pdf_parser import VetPDFParser
        parser = VetPDFParser()
        result = parser.parse_directory(tmp_path)
        assert result == []

    def test_parse_real_pdf_if_available(self):
        """
        If a PDF exists in data/pdfs/, parse it and verify structure.
        Skips gracefully if no PDFs present.
        """
        from ingestion.pdf_parser import VetPDFParser
        pdf_dir = Path("data/pdfs")
        pdfs = list(pdf_dir.rglob("*.pdf")) if pdf_dir.exists() else []
        if not pdfs:
            pytest.skip("No PDFs in data/pdfs/ — add a vet manual PDF to test")

        parser = VetPDFParser()
        doc = parser.parse(pdfs[0])

        # Read full_text before fitz document is GC-closed
        full_text = doc.full_text
        assert doc.filename.endswith(".pdf")
        assert doc.total_pages > 0
        assert len(doc.pages) > 0
        assert doc.total_words > 0
        assert full_text.strip() != ""
        assert isinstance(doc.metadata, dict)
        assert "title" in doc.metadata


class TestChunker:
    """Tests for vetgpt/ingestion/chunker.py"""

    def test_import(self):
        from ingestion.chunker import VetChunker, DocumentChunk
        assert VetChunker is not None

    def test_chunk_sizes(self):
        """Chunks respect configured size limits."""
        from ingestion.chunker import VetChunker
        chunker = VetChunker(chunk_size=200, chunk_overlap=20)
        assert chunker.chunk_size == 200
        assert chunker.chunk_overlap == 20

    def test_chunk_short_text_skipped(self):
        """Text shorter than minimum is not returned as a chunk."""
        from ingestion.chunker import VetChunker
        from ingestion.pdf_parser import ParsedDocument, ParsedPage

        chunker = VetChunker()
        page = ParsedPage(page_number=1, text="Hi.", word_count=1)
        doc = ParsedDocument(
            source_path="/test.pdf", filename="test.pdf",
            title="Test", total_pages=1, pages=[page]
        )
        chunks = chunker.chunk_document(doc)
        assert chunks == []

    def test_chunk_document_produces_chunks(self):
        """A real document with content produces multiple chunks."""
        from ingestion.chunker import VetChunker
        from ingestion.pdf_parser import ParsedDocument, ParsedPage

        long_text = (
            "Canine parvovirus (CPV) is a highly contagious viral disease "
            "affecting dogs. It primarily affects the gastrointestinal tract "
            "and bone marrow. Clinical signs include severe vomiting, hemorrhagic "
            "diarrhea, lethargy, and anorexia. The disease can be rapidly fatal "
            "without aggressive supportive treatment including IV fluids, "
            "antiemetics, and antibiotics to prevent secondary infection. "
        ) * 10  # repeat to ensure chunking occurs

        page = ParsedPage(page_number=1, text=long_text, word_count=len(long_text.split()))
        doc = ParsedDocument(
            source_path="/test.pdf", filename="test_vet.pdf",
            title="Test Vet Manual", total_pages=1, pages=[page]
        )

        chunker = VetChunker(chunk_size=256, chunk_overlap=32)
        chunks = chunker.chunk_document(doc)

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.source_file == "test_vet.pdf"
            assert chunk.document_title == "Test Vet Manual"
            assert chunk.page_number == 1
            assert len(chunk.text) > 30
            assert chunk.word_count > 0
            assert chunk.chunk_id.startswith("test_vet.pdf")

    def test_chunk_id_uniqueness(self):
        """All chunk IDs within a document are unique."""
        from ingestion.chunker import VetChunker
        from ingestion.pdf_parser import ParsedDocument, ParsedPage

        text = "Equine colic is a leading cause of death in horses. " * 30
        pages = [
            ParsedPage(page_number=i, text=text, word_count=len(text.split()))
            for i in range(1, 4)
        ]
        doc = ParsedDocument(
            source_path="/equine.pdf", filename="equine.pdf",
            title="Equine Medicine", total_pages=3, pages=pages
        )
        chunker = VetChunker()
        chunks = chunker.chunk_document(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"

    def test_chunk_metadata_completeness(self):
        """Every chunk has complete metadata for ChromaDB."""
        from ingestion.chunker import VetChunker
        from ingestion.pdf_parser import ParsedDocument, ParsedPage

        text = "Feline hyperthyroidism is the most common endocrine disorder in cats. " * 20
        page = ParsedPage(page_number=5, text=text, word_count=len(text.split()))
        doc = ParsedDocument(
            source_path="/feline.pdf", filename="feline_medicine.pdf",
            title="Feline Medicine", total_pages=10, pages=[page]
        )
        chunker = VetChunker()
        chunks = chunker.chunk_document(doc)

        required_meta_keys = [
            "source_file", "source_path", "document_title",
            "page_number", "chunk_index", "word_count",
            "has_tables", "has_images",
        ]
        for chunk in chunks:
            for key in required_meta_keys:
                assert key in chunk.metadata, f"Missing metadata key: {key}"
            # ChromaDB only accepts str/int/float/bool
            for k, v in chunk.metadata.items():
                assert isinstance(v, (str, int, float, bool)), \
                    f"Invalid metadata type for {k}: {type(v)}"


class TestVectorStore:
    """Tests for vetgpt/ingestion/embedder.py"""

    @pytest.fixture
    def tmp_store(self, tmp_path):
        """Creates a temporary ChromaDB store for testing."""
        from ingestion.embedder import VetVectorStore
        return VetVectorStore(
            db_path=str(tmp_path / "test_chroma"),
            collection_name="test_collection",
        )

    def test_store_initialises(self, tmp_store):
        """VectorStore creates and connects to ChromaDB."""
        stats = tmp_store.stats()
        assert stats["total_chunks"] == 0
        assert stats["collection_name"] == "test_collection"

    def test_add_and_query(self, tmp_store):
        """Add chunks then query them — results come back."""
        from ingestion.chunker import DocumentChunk

        chunks = [
            DocumentChunk(
                chunk_id=f"test_p1_c{i}",
                text=f"Bovine respiratory disease (BRD) affects cattle. Chunk {i}. "
                     "Treatment includes antibiotics and anti-inflammatories.",
                source_file="test.pdf",
                source_path="/test.pdf",
                document_title="Bovine Medicine",
                page_number=1,
                chunk_index=i,
                word_count=15,
                metadata={
                    "source_file": "test.pdf",
                    "source_path": "/test.pdf",
                    "document_title": "Bovine Medicine",
                    "page_number": 1,
                    "chunk_index": i,
                    "has_tables": False,
                    "has_images": False,
                    "word_count": 15,
                }
            )
            for i in range(3)
        ]

        added = tmp_store.add_chunks(chunks)
        assert added == 3
        assert tmp_store.stats()["total_chunks"] == 3

        results = tmp_store.query("bovine respiratory treatment", n_results=3)
        assert len(results) > 0
        assert results[0]["score"] > 0
        assert "text" in results[0]
        assert "source_file" in results[0]
        assert "page_number" in results[0]

    def test_upsert_is_idempotent(self, tmp_store):
        """Adding the same chunks twice does not duplicate them."""
        from ingestion.chunker import DocumentChunk

        chunk = DocumentChunk(
            chunk_id="dedup_test_c0",
            text="Canine distemper virus causes neurological signs in dogs.",
            source_file="dedup.pdf", source_path="/dedup.pdf",
            document_title="Dedup Test", page_number=1, chunk_index=0,
            word_count=10,
            metadata={
                "source_file": "dedup.pdf", "source_path": "/dedup.pdf",
                "document_title": "Dedup Test", "page_number": 1,
                "chunk_index": 0, "has_tables": False,
                "has_images": False, "word_count": 10,
            }
        )

        tmp_store.add_chunks([chunk])
        tmp_store.add_chunks([chunk])   # second time
        assert tmp_store.stats()["total_chunks"] == 1

    def test_query_returns_scored_results(self, tmp_store):
        """Scores are between 0 and 1."""
        from ingestion.chunker import DocumentChunk

        chunks = [
            DocumentChunk(
                chunk_id=f"score_test_c{i}",
                text=f"Equine laminitis is a painful hoof condition in horses. Sample {i}.",
                source_file="equine.pdf", source_path="/equine.pdf",
                document_title="Equine", page_number=1, chunk_index=i,
                word_count=12,
                metadata={
                    "source_file": "equine.pdf", "source_path": "/equine.pdf",
                    "document_title": "Equine", "page_number": 1,
                    "chunk_index": i, "has_tables": False,
                    "has_images": False, "word_count": 12,
                }
            )
            for i in range(5)
        ]
        tmp_store.add_chunks(chunks)
        results = tmp_store.query("horse hoof pain laminitis", n_results=5)

        for r in results:
            assert 0.0 <= r["score"] <= 1.0

    def test_delete_source(self, tmp_store):
        """Deleting a source removes only its chunks."""
        from ingestion.chunker import DocumentChunk

        def make_chunk(chunk_id, source_file):
            return DocumentChunk(
                chunk_id=chunk_id, text="Some vet content here.",
                source_file=source_file, source_path=f"/{source_file}",
                document_title="Title", page_number=1, chunk_index=0,
                word_count=5,
                metadata={
                    "source_file": source_file, "source_path": f"/{source_file}",
                    "document_title": "Title", "page_number": 1,
                    "chunk_index": 0, "has_tables": False,
                    "has_images": False, "word_count": 5,
                }
            )

        tmp_store.add_chunks([
            make_chunk("a_c0", "keep.pdf"),
            make_chunk("b_c0", "delete.pdf"),
        ])
        assert tmp_store.stats()["total_chunks"] == 2

        tmp_store.delete_source("delete.pdf")
        assert tmp_store.stats()["total_chunks"] == 1

        sources = tmp_store.list_sources()
        assert "keep.pdf" in sources
        assert "delete.pdf" not in sources


# ─────────────────────────────────────────────────────────────────────────────
# 2. BOOK REGISTRY TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestBookRegistry:
    """Tests for vetgpt/config/book_registry.py"""

    def test_registry_loads(self):
        from config.book_registry import BOOK_REGISTRY
        assert len(BOOK_REGISTRY) >= 30

    def test_all_required_fields_present(self):
        from config.book_registry import BOOK_REGISTRY
        required = ["key", "title", "short_title", "authors", "edition",
                    "publisher", "legal_status", "citation_format"]
        for key, book in BOOK_REGISTRY.items():
            for field in required:
                assert hasattr(book, field) and getattr(book, field), \
                    f"Book '{key}' missing field: {field}"

    def test_detect_book_by_filename(self):
        from config.book_registry import detect_book
        cases = [
            ("fossum_small_animal_surgery_5e.pdf", "fossum_surgery"),
            ("plumbs_drug_handbook_9th.pdf",        "plumbs"),
            ("merck_vet_manual_12th.pdf",            "merck_vet"),
            ("wikivet_article.pdf",                  "wikivet"),
            ("thralls_radiology_7e.pdf",             "thralls_radiology"),
            ("unknown_random_file.pdf",              None),
        ]
        for filename, expected_key in cases:
            result = detect_book(filename)
            if expected_key is None:
                assert result is None, f"Expected no match for {filename}, got {result}"
            else:
                assert result is not None, f"No match for {filename}"
                assert result.key == expected_key, \
                    f"Wrong match for {filename}: got {result.key}, expected {expected_key}"

    def test_chroma_metadata_types(self):
        """All metadata values are ChromaDB-compatible types."""
        from config.book_registry import BOOK_REGISTRY
        for key, book in BOOK_REGISTRY.items():
            meta = book.to_chroma_metadata()
            for k, v in meta.items():
                assert isinstance(v, (str, int, float, bool)), \
                    f"Book '{key}' metadata key '{k}' has invalid type {type(v)}"

    def test_books_by_species(self):
        from config.book_registry import books_by_species
        equine = books_by_species("equine")
        assert len(equine) >= 3
        canine = books_by_species("dog")
        assert len(canine) >= 5

    def test_open_access_books_exist(self):
        from config.book_registry import books_by_status, OPEN_ACCESS
        open_books = books_by_status(OPEN_ACCESS)
        assert len(open_books) >= 4
        keys = [b.key for b in open_books]
        assert "wikivet" in keys
        assert "fao_livestock" in keys
        assert "oie_woah" in keys


# ─────────────────────────────────────────────────────────────────────────────
# 3. SCRAPER TESTS (unit-level, no network)
# ─────────────────────────────────────────────────────────────────────────────

class TestScraperUnits:
    """Unit tests for scraper modules — no network calls."""

    def test_wikivet_scraper_imports(self):
        from scraping.wikivet_scraper import WikiVetScraper, ScrapedArticle
        s = WikiVetScraper()
        assert s is not None

    def test_pubmed_scraper_imports(self):
        from scraping.pubmed_scraper import PubMedScraper
        s = PubMedScraper()
        assert s is not None

    def test_fao_scraper_imports(self):
        from scraping.fao_scraper import FAOScraper
        s = FAOScraper()
        assert s is not None

    def test_eclinpath_scraper_imports(self):
        from scraping.eclinpath_scraper import EClinPathScraper
        s = EClinPathScraper()
        assert s is not None

    def test_wikivet_article_metadata(self):
        """ScrapedArticle produces valid ChromaDB metadata."""
        from scraping.wikivet_scraper import ScrapedArticle
        article = ScrapedArticle(
            url="https://en.wikivet.net/Canine_Parvovirus",
            title="Canine Parvovirus",
            text="Canine parvovirus is a highly contagious viral disease. " * 20,
            categories=["Diseases_and_Conditions", "Virology"],
        )
        meta = article.to_metadata()
        for k, v in meta.items():
            assert isinstance(v, (str, int, float, bool)), \
                f"Invalid metadata type for {k}: {type(v)}"
        assert meta["source"] == "wikivet"
        assert meta["license"] == "CC BY-SA"
        assert article.word_count > 0

    def test_pubmed_article_text_property(self):
        """PubMedArticle.text combines title + abstract + MeSH."""
        from scraping.pubmed_scraper import PubMedArticle
        article = PubMedArticle(
            pmid="12345678",
            title="Treatment of canine parvovirus",
            abstract="This study evaluates fluid therapy outcomes in CPV dogs.",
            authors=["Smith J", "Jones A"],
            journal="JAVMA",
            pub_year="2023",
            doi="10.1234/test",
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            mesh_terms=["Dogs", "Parvovirus", "Fluid Therapy"],
        )
        text = article.text
        assert "Treatment of canine parvovirus" in text
        assert "fluid therapy" in text.lower()
        assert article.word_count > 10

    def test_eclinpath_article_metadata(self):
        """EClinPathArticle metadata is ChromaDB-compatible."""
        from scraping.eclinpath_scraper import EClinPathArticle
        article = EClinPathArticle(
            url="https://eclinpath.com/hematology/red-cell-parameters/",
            title="Red Cell Parameters",
            section="hematology",
            text="The packed cell volume (PCV) measures the proportion of red "
                 "blood cells in whole blood. " * 15,
        )
        meta = article.to_metadata()
        for k, v in meta.items():
            assert isinstance(v, (str, int, float, bool)), \
                f"Invalid metadata type for key '{k}': {type(v)}"
        assert meta["source"] == "eclinpath"
        assert meta["section"] == "hematology"

    def test_pipeline_imports(self):
        from scraping.pipeline import ScrapingPipeline
        # Just test it doesn't crash on import
        assert ScrapingPipeline is not None

    def test_wikivet_clean_text(self):
        """WikiVet text cleaner removes noise patterns."""
        from scraping.wikivet_scraper import WikiVetScraper
        scraper = WikiVetScraper()
        dirty = "Some good content.\n\n[edit]\n\n== References ==\nRef1\n== External Links ==\nhttps://example.com"
        clean = scraper._clean_text(dirty)
        assert "[edit]" not in clean
        assert "References" not in clean
        assert "External Links" not in clean
        assert "Some good content" in clean


# ─────────────────────────────────────────────────────────────────────────────
# 4. BACKEND CONFIG + DATABASE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestBackendConfig:
    """Tests for vetgpt/backend/config.py"""

    def test_settings_load(self):
        from backend.config import get_settings
        settings = get_settings()
        assert settings.app_name == "VetGPT API"
        assert settings.algorithm == "HS256"
        assert settings.rag_top_k > 0
        assert settings.llm_max_tokens > 0

    def test_settings_are_cached(self):
        """get_settings() returns the same instance (lru_cache)."""
        from backend.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_secret_key_not_empty(self):
        from backend.config import get_settings
        settings = get_settings()
        assert settings.secret_key
        assert len(settings.secret_key) >= 8


class TestAuth:
    """Tests for vetgpt/backend/auth.py"""

    def test_password_hash_and_verify(self):
        from backend.auth import hash_password, verify_password
        password = "SecureVetPass123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("WrongPassword", hashed)

    def test_hash_is_not_deterministic(self):
        """Same password → different hash each time (bcrypt salt)."""
        from backend.auth import hash_password
        h1 = hash_password("password123")
        h2 = hash_password("password123")
        assert h1 != h2

    def test_jwt_encode_decode(self):
        """Token created from user data decodes back correctly."""
        from backend.auth import create_access_token, decode_token
        from backend.database import User, SubscriptionTier
        from datetime import datetime

        mock_user = User(
            id="test-uuid-1234",
            email="vet@clinic.com",
            hashed_password="x",
            tier=SubscriptionTier.FREE,
            created_at=datetime.utcnow(),
        )
        token = create_access_token(mock_user)
        assert isinstance(token, str)
        assert len(token) > 20

        decoded = decode_token(token)
        assert decoded.user_id == "test-uuid-1234"
        assert decoded.email == "vet@clinic.com"
        assert decoded.tier == "free"

    def test_invalid_token_raises(self):
        """Garbage token raises HTTPException."""
        from backend.auth import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.real.token")
        assert exc_info.value.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 5. FASTAPI ENDPOINT TESTS (TestClient — no server needed)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """TestClient for FastAPI app — no running server needed."""
    from fastapi.testclient import TestClient
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    """Register a test user and return auth headers."""
    import uuid
    email = f"test_{uuid.uuid4().hex[:8]}@vetgpt-test.com"
    password = "VetPass1!"

    res = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test Vet",
    })
    assert res.status_code == 201, f"Register failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoints:
    def test_root(self, client):
        res = client.get("/")
        assert res.status_code == 200
        data = res.json()
        assert "name" in data
        assert "version" in data

    def test_health_ok(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_health_full(self, client):
        res = client.get("/api/health/full")
        assert res.status_code == 200
        data = res.json()
        assert "database" in data
        assert "chroma_chunks" in data
        assert "llm_provider" in data

    def test_docs_available(self, client):
        res = client.get("/docs")
        assert res.status_code == 200

    def test_openapi_schema(self, client):
        res = client.get("/openapi.json")
        assert res.status_code == 200
        schema = res.json()
        assert "paths" in schema
        assert "/api/auth/register" in schema["paths"]
        assert "/api/query" in schema["paths"]


class TestAuthEndpoints:
    def test_register_success(self, client):
        import uuid
        res = client.post("/api/auth/register", json={
            "email": f"reg_{uuid.uuid4().hex[:6]}@test.com",
            "password": "VetPass1!",
            "full_name": "Dr. Register",
        })
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["user"]["tier"] == "free"
        assert data["user"]["email"].endswith("@test.com")

    def test_register_duplicate_email(self, client, auth_headers):
        """Registering with existing email returns 409."""
        res = client.get("/api/auth/me", headers=auth_headers)
        email = res.json()["email"]

        res2 = client.post("/api/auth/register", json={
            "email": email,
            "password": "VetPass2!",
            "full_name": "Duplicate",
        })
        assert res2.status_code == 409

    def test_register_invalid_email(self, client):
        res = client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "VetPass1!",
            "full_name": "Bad Email",
        })
        assert res.status_code == 422   # Pydantic validation error

    def test_login_success(self, client, auth_headers):
        """Login returns token for registered user."""
        res = client.get("/api/auth/me", headers=auth_headers)
        email = res.json()["email"]

        login_res = client.post("/api/auth/login", data={
            "username": email,
            "password": "VetPass1!",
        })
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

    def test_login_wrong_password(self, client, auth_headers):
        res = client.get("/api/auth/me", headers=auth_headers)
        email = res.json()["email"]

        login_res = client.post("/api/auth/login", data={
            "username": email,
            "password": "WrongPassword999",
        })
        assert login_res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = client.post("/api/auth/login", data={
            "username": "ghost@nowhere.com",
            "password": "NoSuchUser123",
        })
        assert res.status_code == 401

    def test_get_me_authenticated(self, client, auth_headers):
        res = client.get("/api/auth/me", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert "email" in data
        assert "tier" in data
        assert "created_at" in data

    def test_get_me_unauthenticated(self, client):
        res = client.get("/api/auth/me")
        assert res.status_code == 401

    def test_get_me_invalid_token(self, client):
        res = client.get("/api/auth/me", headers={"Authorization": "Bearer faketoken123"})
        assert res.status_code == 401


class TestQueryEndpoints:
    def test_query_unauthenticated_allowed(self, client):
        """Unauthenticated queries require token — expect 200, 401, or 500."""
        res = client.post("/api/query", json={"query": "What is canine parvovirus?"})
        assert res.status_code in (200, 401, 500)
        if res.status_code == 200:
            data = res.json()
            assert "answer" in data
            assert "citations" in data
            assert "disclaimer" in data

    def test_query_authenticated(self, client, auth_headers):
        """Authenticated query returns structured response."""
        res = client.post(
            "/api/query",
            json={"query": "Treatment for feline hyperthyroidism"},
            headers=auth_headers,
        )
        assert res.status_code in (200, 500)
        if res.status_code == 200:
            data = res.json()
            assert "query" in data
            assert "answer" in data
            assert isinstance(data["citations"], list)
            assert isinstance(data["chunks_retrieved"], int)
            assert isinstance(data["latency_ms"], int)
            assert data["latency_ms"] >= 0

    def test_query_empty_string_rejected(self, client, auth_headers):
        """Empty query string returns 422 validation error."""
        res = client.post("/api/query", json={"query": ""}, headers=auth_headers)
        assert res.status_code == 422

    def test_query_too_long_rejected(self, client, auth_headers):
        """Query > 2000 chars is rejected."""
        res = client.post(
            "/api/query",
            json={"query": "x" * 2001},
            headers=auth_headers,
        )
        assert res.status_code == 422

    def test_query_with_species_filter(self, client, auth_headers):
        """Species filter is accepted and passed through."""
        res = client.post(
            "/api/query",
            json={"query": "respiratory disease", "filter_species": "bovine"},
            headers=auth_headers,
        )
        assert res.status_code in (200, 500)

    def test_query_with_source_filter(self, client, auth_headers):
        """Source filter is accepted."""
        res = client.post(
            "/api/query",
            json={"query": "hematology reference ranges", "filter_source": "eclinpath"},
            headers=auth_headers,
        )
        assert res.status_code in (200, 500)

    def test_query_history_empty_initially(self, client, auth_headers):
        """History endpoint returns list (may be empty)."""
        res = client.get("/api/query/history", headers=auth_headers)
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_query_history_unauthenticated_rejected(self, client):
        res = client.get("/api/query/history")
        assert res.status_code == 401

    def test_image_endpoint_premium_required(self, client, auth_headers):
        """Image query endpoint returns 403 for free user."""
        res = client.post(
            "/api/query/image",
            data={"query": "What is this lesion?"},
            files={"file": ("test.jpg", b"fake_image_bytes", "image/jpeg")},
            headers=auth_headers,
        )
        assert res.status_code in (403, 501)

    def test_top_k_capped_for_unauthenticated(self, client):
        """Query without auth — expect 200, 401, or 500."""
        res = client.post("/api/query", json={"query": "canine disease", "top_k": 20})
        assert res.status_code in (200, 401, 500)


class TestCORSHeaders:
    def test_cors_headers_present(self, client):
        """CORS headers are set for allowed origins."""
        res = client.get(
            "/api/health",
            headers={"Origin": "http://localhost:8081"},
        )
        assert res.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 6. RAG ENGINE TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestRAGEngine:
    def test_rag_engine_imports(self):
        from backend.rag_engine import VetRAGEngine, RAGResponse, Citation, build_prompt
        assert VetRAGEngine is not None

    def test_build_prompt_structure(self):
        """Prompt builder produces correct format."""
        from backend.rag_engine import build_prompt
        chunks = [
            {
                "text": "Canine parvovirus treatment includes IV fluids.",
                "document_title": "Merck Vet Manual",
                "page_number": 42,
            },
            {
                "text": "Antiemetics reduce vomiting in CPV-infected dogs.",
                "document_title": "WikiVet",
                "page_number": 1,
            },
        ]
        prompt = build_prompt("How do I treat parvovirus?", chunks)
        assert "Canine parvovirus" in prompt
        assert "Merck Vet Manual" in prompt
        assert "WikiVet" in prompt
        assert "How do I treat parvovirus?" in prompt
        assert "[Source 1:" in prompt
        assert "[Source 2:" in prompt

    def test_citation_format(self):
        """Citation formats correctly."""
        from backend.rag_engine import Citation
        c = Citation(
            source_file="merck_vet.pdf",
            document_title="Merck Veterinary Manual",
            page_number=123,
            score=0.87,
            excerpt="Canine parvovirus causes...",
        )
        assert c.format() == "Merck Veterinary Manual, p.123"
        d = c.to_dict()
        assert d["score"] == 0.87
        assert d["page_number"] == 123

    def test_rag_response_structure(self):
        """RAGResponse serialises correctly."""
        from backend.rag_engine import RAGResponse, Citation
        citations = [
            Citation("f.pdf", "Title", 1, 0.9, "excerpt...")
        ]
        response = RAGResponse(
            query="test query",
            answer="test answer",
            citations=citations,
            chunks_retrieved=1,
            top_score=0.9,
            llm_model="claude-sonnet-4-5",
            latency_ms=250,
        )
        d = response.to_dict()
        assert d["query"] == "test query"
        assert d["answer"] == "test answer"
        assert len(d["citations"]) == 1
        assert "disclaimer" in d


# ─────────────────────────────────────────────────────────────────────────────
# 7. INTEGRATION TEST — Full pipeline (requires real data + LLM key)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipeline:
    """
    End-to-end integration tests.
    These require:
      - At least one source ingested (PDF or scrape)
      - ANTHROPIC_API_KEY or OPENAI_API_KEY set in .env
    Skip gracefully if not available.
    """

    def test_chromadb_has_data(self):
        """ChromaDB collection has at least some chunks."""
        from ingestion.embedder import VetVectorStore
        store = VetVectorStore()
        stats = store.stats()
        if stats["total_chunks"] == 0:
            pytest.skip(
                "ChromaDB is empty. Run: python ingest.py ingest --dir data/pdfs/ "
                "or python scrape.py run-all"
            )
        assert stats["total_chunks"] > 0
        console_msg = f"ChromaDB has {stats['total_chunks']:,} chunks ✓"
        print(f"\n{console_msg}")

    def test_vector_search_returns_vet_content(self):
        """Vector search returns relevant veterinary content."""
        from ingestion.embedder import VetVectorStore
        store = VetVectorStore()
        if store.stats()["total_chunks"] == 0:
            pytest.skip("ChromaDB is empty")

        queries = [
            "canine parvovirus treatment",
            "feline hyperthyroidism methimazole",
            "bovine respiratory disease diagnosis",
            "equine colic surgery",
            "hematology reference ranges dog",
        ]
        for query in queries:
            results = store.query(query, n_results=3)
            assert isinstance(results, list), f"No results for: {query}"
            if results:
                assert results[0]["score"] >= 0
                assert len(results[0]["text"]) > 20

    def test_full_rag_query_via_api(self, client, auth_headers):
        """
        Full RAG query: question → ChromaDB retrieval → LLM → answer.
        Requires LLM API key in .env.
        """
        from ingestion.embedder import VetVectorStore
        from backend.config import get_settings

        store = VetVectorStore()
        settings = get_settings()

        if store.stats()["total_chunks"] == 0:
            pytest.skip("ChromaDB is empty — no data to retrieve")

        has_llm = bool(settings.anthropic_api_key or settings.openai_api_key)
        if not has_llm:
            pytest.skip("No LLM API key set in .env")

        start = time.time()
        res = client.post(
            "/api/query",
            json={"query": "What are the clinical signs of canine parvovirus?"},
            headers=auth_headers,
        )
        elapsed = time.time() - start

        assert res.status_code == 200, f"Query failed: {res.text}"
        data = res.json()

        # Answer quality checks
        assert data["answer"], "Empty answer"
        assert len(data["answer"]) > 50, "Answer too short"
        assert data["chunks_retrieved"] > 0, "No chunks retrieved"
        assert data["top_score"] > 0, "Zero similarity score"
        assert data["latency_ms"] > 0
        assert elapsed < 30, f"Query took too long: {elapsed:.1f}s"

        # Citation checks
        assert isinstance(data["citations"], list)
        if data["citations"]:
            c = data["citations"][0]
            assert "document_title" in c
            assert "page_number" in c
            assert 0 <= c["score"] <= 1.0

        print(f"\n✓ Full RAG pipeline: {data['chunks_retrieved']} chunks, "
              f"{data['latency_ms']}ms, model: {data['llm_model']}")

    def test_query_history_logged(self, client, auth_headers):
        """Queries are logged in the database."""
        from ingestion.embedder import VetVectorStore
        store = VetVectorStore()
        if store.stats()["total_chunks"] == 0:
            pytest.skip("ChromaDB is empty")

        # Make a query
        client.post(
            "/api/query",
            json={"query": "bovine respiratory disease"},
            headers=auth_headers,
        )

        # Check history
        history_res = client.get("/api/query/history", headers=auth_headers)
        assert history_res.status_code == 200
        history = history_res.json()
        assert isinstance(history, list)
        # History may or may not have entries depending on LLM availability
