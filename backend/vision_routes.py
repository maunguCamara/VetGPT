"""
vetgpt/backend/vision_routes.py

Phase 3 Premium Vision API endpoints.

All endpoints require premium or clinic tier.
Images are processed in memory — never stored to disk.

Routes:
  POST /api/vision/analyze      — general image analysis
  POST /api/vision/xray         — X-ray / DICOM analysis
  POST /api/vision/ocr          — text extraction from image
  POST /api/vision/wound        — wound assessment
  POST /api/vision/lesion       — skin/mucosal lesion
  POST /api/vision/parasite     — parasite identification
  POST /api/vision/cytology     — cytology/histology slide
  GET  /api/vision/health       — vision pipeline status
"""

import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from .auth import require_premium, get_current_user
from .database import User
from .vision_pipeline import (
    VisionPipeline, VisionResponse, ImageType,
    vision_pipeline, cloud_ocr,
)
from .config import get_settings

settings = get_settings()
vision_router = APIRouter(prefix="/api/vision", tags=["vision (premium)"])

# Allowed MIME types
ALLOWED_IMAGES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/tiff",
    "application/dicom",      # X-ray DICOM
}

MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 20 MB


# ─── Shared helpers ───────────────────────────────────────────────────────────

async def read_and_validate_image(file: UploadFile) -> tuple[bytes, str]:
    """Read uploaded file, validate type and size."""
    content_type = file.content_type or "image/jpeg"

    # Accept DICOM by extension if MIME not set correctly
    if file.filename and file.filename.lower().endswith(".dcm"):
        content_type = "application/dicom"

    if content_type not in ALLOWED_IMAGES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {content_type}. "
                   f"Allowed: JPEG, PNG, WebP, TIFF, DICOM (.dcm)"
        )

    image_bytes = await file.read()

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({len(image_bytes) // 1024 // 1024} MB). Maximum is 20 MB."
        )

    if len(image_bytes) < 100:
        raise HTTPException(status_code=400, detail="Image file appears to be empty or corrupt.")

    return image_bytes, content_type


# ─── Response schema ──────────────────────────────────────────────────────────

class VisionAnalysisResponse(BaseModel):
    image_type: str
    analysis: str
    ocr_text: str
    rag_context: list[dict]
    engine_used: str
    latency_ms: int
    disclaimer: str


# ─── Generic analysis endpoint ────────────────────────────────────────────────

@vision_router.post("/analyze", response_model=VisionAnalysisResponse)
async def analyze_image(
    file: UploadFile = File(..., description="Clinical image (JPEG, PNG, DICOM)"),
    image_type: str  = Form(default="general", description="wound|lesion|parasite|cytology|xray|ultrasound|general"),
    query: str       = Form(default="", description="Optional specific question"),
    run_ocr: bool    = Form(default=False, description="Extract text from image"),
    user: User       = Depends(require_premium),
):
    """
    **Premium** — Analyze any veterinary clinical image.
    Supports wounds, lesions, parasites, cytology, X-rays, ultrasound.
    """
    image_bytes, mime_type = await read_and_validate_image(file)

    try:
        img_type = ImageType(image_type)
    except ValueError:
        img_type = ImageType.GENERAL

    result = await vision_pipeline.analyze(
        image_bytes=image_bytes,
        mime_type=mime_type,
        image_type=img_type,
        user_query=query,
        run_ocr=run_ocr,
    )
    return VisionAnalysisResponse(**result.to_dict())


# ─── Specialised endpoints ────────────────────────────────────────────────────

@vision_router.post("/xray", response_model=VisionAnalysisResponse)
async def analyze_xray(
    file: UploadFile = File(..., description="Radiograph — JPEG, PNG, or DICOM (.dcm)"),
    query: str       = Form(default="", description="Specific radiographic question"),
    user: User       = Depends(require_premium),
):
    """
    **Premium** — Veterinary radiograph / X-ray analysis.
    Accepts standard JPEG/PNG radiographs and DICOM files.
    Provides systematic radiographic assessment with differentials.
    """
    image_bytes, mime_type = await read_and_validate_image(file)
    result = await vision_pipeline.analyze(
        image_bytes=image_bytes,
        mime_type=mime_type,
        image_type=ImageType.XRAY,
        user_query=query,
    )
    return VisionAnalysisResponse(**result.to_dict())


@vision_router.post("/wound", response_model=VisionAnalysisResponse)
async def analyze_wound(
    file: UploadFile = File(...),
    query: str       = Form(default=""),
    user: User       = Depends(require_premium),
):
    """**Premium** — Wound assessment with classification and management recommendations."""
    image_bytes, mime_type = await read_and_validate_image(file)
    result = await vision_pipeline.analyze(image_bytes, mime_type, ImageType.WOUND, query)
    return VisionAnalysisResponse(**result.to_dict())


@vision_router.post("/lesion", response_model=VisionAnalysisResponse)
async def analyze_lesion(
    file: UploadFile = File(...),
    query: str       = Form(default=""),
    user: User       = Depends(require_premium),
):
    """**Premium** — Skin/mucosal lesion analysis with dermatological differentials."""
    image_bytes, mime_type = await read_and_validate_image(file)
    result = await vision_pipeline.analyze(image_bytes, mime_type, ImageType.LESION, query)
    return VisionAnalysisResponse(**result.to_dict())


@vision_router.post("/parasite", response_model=VisionAnalysisResponse)
async def analyze_parasite(
    file: UploadFile = File(...),
    query: str       = Form(default=""),
    user: User       = Depends(require_premium),
):
    """**Premium** — Parasite identification with species, lifecycle stage, and treatment."""
    image_bytes, mime_type = await read_and_validate_image(file)
    result = await vision_pipeline.analyze(image_bytes, mime_type, ImageType.PARASITE, query)
    return VisionAnalysisResponse(**result.to_dict())


@vision_router.post("/cytology", response_model=VisionAnalysisResponse)
async def analyze_cytology(
    file: UploadFile = File(...),
    query: str       = Form(default=""),
    user: User       = Depends(require_premium),
):
    """**Premium** — Cytology/histology slide interpretation with morphological assessment."""
    image_bytes, mime_type = await read_and_validate_image(file)
    result = await vision_pipeline.analyze(image_bytes, mime_type, ImageType.CYTOLOGY, query)
    return VisionAnalysisResponse(**result.to_dict())


@vision_router.post("/ocr", response_model=dict)
async def extract_text(
    file: UploadFile = File(..., description="Image containing text (prescription, lab report, handwritten notes)"),
    user: User       = Depends(require_premium),
):
    """
    **Premium** — Extract text from clinical images.
    Uses Google Document AI for high-accuracy OCR of prescriptions,
    lab reports, handwritten notes, and printed forms.
    """
    image_bytes, mime_type = await read_and_validate_image(file)
    text = await cloud_ocr(image_bytes, mime_type)

    if not text:
        return {
            "text": "",
            "message": "No text detected in image, or OCR service not configured. "
                       "Set GOOGLE_DOCUMENT_AI_PROCESSOR_ID in .env",
            "configured": bool(
                __import__('os').getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID")
            ),
        }

    return {
        "text": text,
        "word_count": len(text.split()),
        "message": "Text extracted successfully.",
        "configured": True,
    }


# ─── Health ───────────────────────────────────────────────────────────────────

@vision_router.get("/health")
async def vision_health(user: User = Depends(get_current_user)):
    """Vision pipeline status — authenticated users only."""
    return vision_pipeline.health()
