"""
vetgpt/tests/test_phase3_e2e.py

Phase 3 End-to-End Test Suite — Vision AI.

Covers:
  - Vision pipeline (all 7 image types)
  - DICOM conversion
  - OCR (cloud fallback)
  - All 7 vision API endpoints
  - Premium gate enforcement
  - Image validation (size, type, content)
  - RAG context injection into vision prompts
  - Billing routes (/api/billing/*)
  - Fine-tuning export (/api/admin/finetune/*)

Run:
    pytest tests/test_phase3_e2e.py -v --tb=short
"""

import sys
import json
import io
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
def free_headers(client):
    import uuid
    email    = f"p3free_{uuid.uuid4().hex[:6]}@phase3.test"
    password = "Phase3Pass1!"
    res = client.post("/api/auth/register", json={
        "email": email, "password": password, "full_name": "Free Vet"
    })
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _jpeg(size: int = 1024) -> bytes:
    """Minimal valid JPEG bytes."""
    # JPEG header + footer — enough to pass MIME detection
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        + b'\x00' * max(0, size - 20)
        + b'\xff\xd9'
    )


def _png(size: int = 1024) -> bytes:
    """Minimal valid PNG bytes."""
    return (
        b'\x89PNG\r\n\x1a\n'
        + b'\x00' * max(0, size - 8)
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. VISION PIPELINE UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionPipelineUnit:

    def test_all_image_types_defined(self):
        from backend.vision_pipeline import ImageType
        expected = {"wound", "lesion", "parasite", "cytology", "xray", "ultrasound", "general"}
        assert {t.value for t in ImageType} == expected

    def test_every_type_has_unique_prompt(self):
        from backend.vision_pipeline import ImageType, IMAGE_PROMPTS
        prompts = list(IMAGE_PROMPTS.values())
        assert len(prompts) == len(set(prompts)), "Duplicate prompts found across image types"

    def test_all_prompts_contain_disclaimer(self):
        from backend.vision_pipeline import IMAGE_PROMPTS
        for img_type, prompt in IMAGE_PROMPTS.items():
            assert "ALWAYS end with" in prompt, \
                f"{img_type}: prompt missing 'ALWAYS end with' disclaimer instruction"

    def test_xray_prompt_is_systematic(self):
        from backend.vision_pipeline import ImageType, IMAGE_PROMPTS
        prompt = IMAGE_PROMPTS[ImageType.XRAY]
        for section in ["TECHNICAL QUALITY", "FINDINGS", "INTERPRETATION", "RECOMMENDATIONS"]:
            assert section in prompt, f"X-ray prompt missing section: {section}"

    def test_cytology_prompt_covers_malignancy(self):
        from backend.vision_pipeline import ImageType, IMAGE_PROMPTS
        prompt = IMAGE_PROMPTS[ImageType.CYTOLOGY]
        assert "malignancy" in prompt.lower() or "neoplastic" in prompt.lower()

    def test_parasite_prompt_covers_zoonosis(self):
        from backend.vision_pipeline import ImageType, IMAGE_PROMPTS
        prompt = IMAGE_PROMPTS[ImageType.PARASITE]
        assert "zoonotic" in prompt.lower() or "public health" in prompt.lower()

    def test_vision_response_disclaimer_present(self):
        from backend.vision_pipeline import VisionResponse
        r = VisionResponse(
            image_type="xray", analysis="Normal radiograph",
            ocr_text="", rag_context=[], engine_used="gpt4o", latency_ms=800,
        )
        assert r.disclaimer
        assert len(r.disclaimer) > 30
        d = r.to_dict()
        assert "disclaimer" in d
        assert d["image_type"]   == "xray"
        assert d["engine_used"]  == "gpt4o"
        assert d["latency_ms"]   == 800

    def test_dicom_to_jpeg_bad_bytes(self):
        """DICOM converter handles corrupt/non-DICOM bytes gracefully."""
        from backend.vision_pipeline import dicom_to_jpeg
        result, error = dicom_to_jpeg(b"not a dicom file at all " * 10)
        # Either returns error string or empty bytes — must not raise
        assert isinstance(result, bytes)
        assert isinstance(error,  str)

    def test_dicom_to_jpeg_empty(self):
        from backend.vision_pipeline import dicom_to_jpeg
        result, error = dicom_to_jpeg(b"")
        assert isinstance(result, bytes)

    def test_build_user_content_includes_rag(self):
        from backend.vision_pipeline import VisionPipeline
        pipeline = VisionPipeline.__new__(VisionPipeline)
        pipeline._store = MagicMock()

        rag_chunks = [
            {"text": "Laminitis in horses presents with digital pulse.", "document_title": "Merck", "page_number": 88},
        ]
        content = pipeline._build_user_content(
            image_bytes=_jpeg(),
            mime_type="image/jpeg",
            user_query="What is visible?",
            ocr_text="",
            rag_chunks=rag_chunks,
        )
        all_text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        assert "Laminitis"  in all_text
        assert "Merck"      in all_text
        assert "What is visible?" in all_text

    def test_build_user_content_with_ocr(self):
        from backend.vision_pipeline import VisionPipeline
        pipeline = VisionPipeline.__new__(VisionPipeline)
        content = pipeline._build_user_content(
            image_bytes=_jpeg(),
            mime_type="image/jpeg",
            user_query="",
            ocr_text="PRESCRIPTION: Amoxicillin 250mg q8h x5 days",
            rag_chunks=[],
        )
        all_text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        assert "Amoxicillin" in all_text

    def test_vision_pipeline_health_structure(self):
        from backend.vision_pipeline import VisionPipeline
        pipeline = VisionPipeline.__new__(VisionPipeline)
        pipeline._openai = None
        pipeline._gemini = None
        pipeline._store  = MagicMock()
        pipeline._store.stats.return_value = {"total_chunks": 150}

        health = pipeline.health()
        assert health["gpt4o_ready"]   is False
        assert health["gemini_ready"]  is False
        assert health["chroma_chunks"] == 150

    def test_vision_singleton_is_reused(self):
        from backend.vision_pipeline import vision_pipeline
        from backend.vision_pipeline import vision_pipeline as vp2
        assert vision_pipeline is vp2


# ─────────────────────────────────────────────────────────────────────────────
# 2. VISION API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class TestVisionAPIEndpoints:

    VISION_ENDPOINTS = [
        "/api/vision/analyze",
        "/api/vision/xray",
        "/api/vision/wound",
        "/api/vision/lesion",
        "/api/vision/parasite",
        "/api/vision/cytology",
        "/api/vision/ocr",
    ]

    def test_all_vision_endpoints_in_schema(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for ep in self.VISION_ENDPOINTS:
            assert ep in paths, f"Missing vision endpoint: {ep}"

    def test_vision_endpoints_require_auth(self, client):
        for ep in self.VISION_ENDPOINTS:
            res = client.post(ep, files=[("file", ("t.jpg", _jpeg(), "image/jpeg"))])
            assert res.status_code == 401, f"{ep} should require auth (got {res.status_code})"

    def test_vision_health_requires_auth(self, client):
        res = client.get("/api/vision/health")
        assert res.status_code == 401

    def test_vision_health_returns_structure(self, client, free_headers):
        res = client.get("/api/vision/health", headers=free_headers)
        assert res.status_code == 200
        data = res.json()
        assert "gpt4o_ready"   in data
        assert "gemini_ready"  in data
        assert "chroma_chunks" in data

    def test_free_user_gets_403_on_vision(self, client, free_headers):
        """All vision endpoints return 403 for free-tier users."""
        for ep in self.VISION_ENDPOINTS:
            res = client.post(
                ep,
                files=[("file", ("t.jpg", _jpeg(2000), "image/jpeg"))],
                headers=free_headers,
            )
            assert res.status_code == 403, \
                f"{ep} should return 403 for free user (got {res.status_code})"

    def test_rejects_oversized_file(self, client, free_headers):
        """Files > 20 MB are rejected before premium check."""
        huge = b"x" * (21 * 1024 * 1024)
        res  = client.post(
            "/api/vision/analyze",
            files=[("file", ("big.jpg", huge, "image/jpeg"))],
            headers=free_headers,
        )
        assert res.status_code in (403, 413)

    def test_rejects_wrong_mime_type(self, client, free_headers):
        res = client.post(
            "/api/vision/wound",
            files=[("file", ("notes.txt", b"clinical notes here", "text/plain"))],
            headers=free_headers,
        )
        assert res.status_code in (403, 415)

    def test_rejects_empty_file(self, client, free_headers):
        res = client.post(
            "/api/vision/lesion",
            files=[("file", ("empty.jpg", b"", "image/jpeg"))],
            headers=free_headers,
        )
        assert res.status_code in (400, 403)

    def test_dcm_extension_accepted_for_xray(self, client, free_headers):
        """DICOM files (.dcm) are recognised for the xray endpoint."""
        dicom_bytes = b"DICM" + b"\x00" * 100
        res = client.post(
            "/api/vision/xray",
            files=[("file", ("scan.dcm", dicom_bytes, "application/dicom"))],
            headers=free_headers,
        )
        # 403 = premium required (expected for free user)
        # 400 = invalid dicom content (acceptable)
        assert res.status_code in (400, 403)

    def test_vision_analyze_accepts_image_type_form_field(self, client, free_headers):
        """image_type form field is accepted."""
        res = client.post(
            "/api/vision/analyze",
            files=[("file", ("img.jpg", _jpeg(2000), "image/jpeg"))],
            data={"image_type": "wound", "query": "Is this infected?"},
            headers=free_headers,
        )
        assert res.status_code in (403, 422)   # 403 = free user


# ─────────────────────────────────────────────────────────────────────────────
# 3. BILLING ROUTES
# ─────────────────────────────────────────────────────────────────────────────

class TestBillingRoutes:

    def test_billing_routes_registered(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/billing/checkout"     in paths
        assert "/api/billing/portal"       in paths
        assert "/api/billing/subscription" in paths
        assert "/api/billing/webhook"      in paths

    def test_billing_checkout_requires_auth(self, client):
        res = client.post("/api/billing/checkout", json={"tier": "premium"})
        assert res.status_code == 401

    def test_billing_portal_requires_auth(self, client):
        res = client.post("/api/billing/portal")
        assert res.status_code == 401

    def test_billing_subscription_requires_auth(self, client):
        res = client.get("/api/billing/subscription")
        assert res.status_code == 401

    def test_billing_subscription_authenticated(self, client, free_headers):
        res = client.get("/api/billing/subscription", headers=free_headers)
        assert res.status_code == 200
        data = res.json()
        assert "tier"             in data
        assert "has_subscription" in data
        assert "status"           in data
        assert data["tier"] == "free"

    def test_billing_checkout_invalid_tier(self, client, free_headers):
        res = client.post(
            "/api/billing/checkout",
            json={"tier": "gold_elite"},
            headers=free_headers,
        )
        assert res.status_code == 422

    def test_billing_checkout_valid_tier_without_stripe_key(self, client, free_headers):
        """Without STRIPE_SECRET_KEY configured, checkout returns 503."""
        res = client.post(
            "/api/billing/checkout",
            json={"tier": "premium"},
            headers=free_headers,
        )
        # 503 = Stripe not configured, 200 = Stripe configured and working
        assert res.status_code in (200, 503)

    def test_billing_portal_without_subscription(self, client, free_headers):
        """Users without subscription get 404 when opening portal."""
        res = client.post("/api/billing/portal", headers=free_headers)
        # 404 = no subscription, 503 = Stripe not configured
        assert res.status_code in (404, 503)


# ─────────────────────────────────────────────────────────────────────────────
# 4. FINE-TUNING EXPORT
# ─────────────────────────────────────────────────────────────────────────────

class TestFinetuneExport:

    def test_finetune_routes_registered(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/admin/finetune/export" in paths
        assert "/api/admin/finetune/stats"  in paths

    def test_finetune_export_requires_admin(self, client, free_headers):
        res = client.get("/api/admin/finetune/export", headers=free_headers)
        assert res.status_code in (403, 404)

    def test_finetune_stats_requires_admin(self, client, free_headers):
        res = client.get("/api/admin/finetune/stats", headers=free_headers)
        assert res.status_code in (403, 404)

    def test_finetune_alpaca_format_structure(self):
        from backend.finetune import _to_alpaca, SYSTEM_PROMPT
        mock_log = MagicMock()
        mock_log.query_text  = "What causes BRD?"
        mock_log.answer_text = "Bovine respiratory disease is caused by..."
        records = _to_alpaca([mock_log])
        assert len(records) == 1
        r = records[0]
        assert "instruction" in r
        assert "input"       in r
        assert "output"      in r
        assert r["instruction"] == SYSTEM_PROMPT
        assert r["input"]       == "What causes BRD?"
        assert "Bovine" in r["output"]

    def test_finetune_sharegpt_format_structure(self):
        from backend.finetune import _to_sharegpt
        mock_log = MagicMock()
        mock_log.query_text  = "CPV symptoms?"
        mock_log.answer_text = "Canine parvovirus causes..."
        records = _to_sharegpt([mock_log])
        assert len(records) == 1
        convs = records[0]["conversations"]
        roles = [c["from"] for c in convs]
        assert "system" in roles
        assert "human"  in roles
        assert "gpt"    in roles

    def test_finetune_jsonl_format_structure(self):
        from backend.finetune import _to_jsonl_record
        from datetime import datetime
        mock_log = MagicMock()
        mock_log.query_text       = "Laminitis treatment?"
        mock_log.answer_text      = "Laminitis is treated with..."
        mock_log.sources_used     = "[]"
        mock_log.top_score        = 0.87
        mock_log.chunks_retrieved = 4
        mock_log.llm_model        = "claude-sonnet"
        mock_log.latency_ms       = 1200
        mock_log.created_at       = datetime.utcnow()

        record = _to_jsonl_record(mock_log)
        assert "query"      in record
        assert "answer"     in record
        assert "rag_score"  in record
        assert "sources"    in record
        assert record["rag_score"] == 0.87

    def test_finetune_skips_empty_records(self):
        from backend.finetune import _to_alpaca
        mock_empty = MagicMock()
        mock_empty.query_text  = ""
        mock_empty.answer_text = ""
        records = _to_alpaca([mock_empty])
        assert len(records) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. CLOUD OCR (unit — mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestCloudOCR:

    def test_cloud_ocr_missing_config_returns_empty(self):
        """Without Google Cloud credentials, OCR returns empty string gracefully."""
        import asyncio
        from backend.vision_pipeline import cloud_ocr

        async def run():
            with patch.dict("os.environ", {
                "GOOGLE_DOCUMENT_AI_PROCESSOR_ID": "",
                "GOOGLE_CLOUD_PROJECT_ID": "",
            }):
                result = await cloud_ocr(_jpeg(5000), "image/jpeg")
                assert result == ""

        asyncio.run(run())

    def test_cloud_ocr_import_gracefully_handled(self):
        """OCR fails gracefully if google-cloud-documentai not installed."""
        import asyncio
        from backend.vision_pipeline import cloud_ocr
        import sys

        async def run():
            with patch.dict(sys.modules, {"google.cloud.documentai": None}):
                result = await cloud_ocr(b"image bytes", "image/jpeg")
                assert result == ""   # empty, not an exception

        asyncio.run(run())


# ─────────────────────────────────────────────────────────────────────────────
# 6. PHASE 3 INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase3Integration:

    def test_all_phase3_routers_in_app(self, client):
        paths = set(client.get("/openapi.json").json()["paths"].keys())
        required = {
            "/api/vision/analyze", "/api/vision/xray", "/api/vision/wound",
            "/api/vision/lesion",  "/api/vision/parasite", "/api/vision/cytology",
            "/api/vision/ocr",     "/api/vision/health",
            "/api/billing/checkout", "/api/billing/subscription",
            "/api/admin/finetune/export", "/api/admin/finetune/stats",
        }
        missing = required - paths
        assert not missing, f"Missing Phase 3 routes: {missing}"

    def test_vision_tags_present(self, client):
        """Vision endpoints are tagged correctly for Swagger grouping."""
        paths = client.get("/openapi.json").json()["paths"]
        for ep in ["/api/vision/xray", "/api/vision/wound"]:
            if ep in paths:
                for method_data in paths[ep].values():
                    tags = method_data.get("tags", [])
                    assert any("vision" in t.lower() or "premium" in t.lower() for t in tags), \
                        f"{ep} missing vision/premium tag"

    def test_billing_tags_present(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        if "/api/billing/checkout" in paths:
            for method_data in paths["/api/billing/checkout"].values():
                tags = method_data.get("tags", [])
                assert any("billing" in t.lower() for t in tags)

    def test_vision_pipeline_and_billing_coexist(self, client, free_headers):
        """Vision health and billing subscription can both be called."""
        r1 = client.get("/api/vision/health",       headers=free_headers)
        r2 = client.get("/api/billing/subscription", headers=free_headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
