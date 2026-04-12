"""
vetgpt/backend/vision_pipeline.py

Phase 3 — Premium Vision Pipeline.

Handles:
  - Clinical image analysis (wounds, lesions, parasites, cytology)
  - X-ray / DICOM radiograph analysis
  - OCR (Google Document AI cloud fallback)
  - Multi-modal RAG: image + vector context → LLM answer

Engine routing:
  GPT-4o Vision (primary) → Gemini 2.0 Flash (fallback)

All responses include mandatory clinical disclaimers.
"""

import base64
import time
import io
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
import anthropic

from .config import get_settings
from ingestion.embedder import VetVectorStore

settings = get_settings()


# ─── Image types ─────────────────────────────────────────────────────────────

class ImageType(str, Enum):
    WOUND        = "wound"
    LESION       = "lesion"
    PARASITE     = "parasite"
    CYTOLOGY     = "cytology"
    XRAY         = "xray"
    ULTRASOUND   = "ultrasound"
    GENERAL      = "general"


# ─── Prompts by image type ────────────────────────────────────────────────────

IMAGE_PROMPTS: dict[ImageType, str] = {
    ImageType.WOUND: """You are a veterinary clinical image analysis assistant.
Analyze this wound/injury image and provide:
1. Description of the wound (size estimate, depth appearance, tissue involvement)
2. Wound classification (abrasion, laceration, puncture, avulsion, burn, etc.)
3. Degree of contamination (clean, contaminated, infected signs)
4. Healing stage if applicable (inflammatory, proliferative, remodeling)
5. Recommended immediate management steps
6. Differential diagnoses to consider
7. When to refer to a specialist

Base your analysis on what is visible. Be specific and clinically precise.
ALWAYS end with: This analysis is AI-generated for reference only. Clinical examination by a licensed veterinarian is required for diagnosis and treatment.""",

    ImageType.LESION: """You are a veterinary dermatology image analysis assistant.
Analyze this skin/mucosal lesion image and provide:
1. Lesion description (morphology: macule, papule, pustule, nodule, plaque, ulcer, etc.)
2. Distribution pattern (focal, multifocal, generalized, symmetrical)
3. Surface characteristics (smooth, scaly, crusted, ulcerated, proliferative)
4. Top 3-5 differential diagnoses with likelihood reasoning
5. Recommended diagnostic workup (skin scraping, cytology, culture, biopsy, etc.)
6. Initial management considerations

ALWAYS end with: This analysis is AI-generated for reference only. Definitive diagnosis requires clinicopathological correlation by a licensed veterinarian.""",

    ImageType.PARASITE: """You are a veterinary parasitology image analysis assistant.
Analyze this image for parasite identification and provide:
1. Suspected parasite identification (species if possible, family/genus minimum)
2. Life stage visible (egg, larva, adult, nymph)
3. Host species this parasite typically affects
4. Zoonotic potential (yes/no with explanation)
5. Recommended treatment options
6. Prevention and control measures
7. Public health considerations if applicable

ALWAYS end with: Definitive parasite identification may require microscopy or laboratory analysis. Consult a veterinary parasitologist for confirmation.""",

    ImageType.CYTOLOGY: """You are a veterinary clinical pathology image analysis assistant.
Analyze this cytology/histology image and provide:
1. Sample type assessment (exudate, transudate, FNA, impression smear, etc.)
2. Cell population description (types present, morphology, proportions)
3. Notable cytological features (anisocytosis, anisokaryosis, mitoses, inclusions)
4. Interpretation categories (inflammatory, neoplastic, normal/reactive)
5. If inflammatory: type (suppurative, granulomatous, eosinophilic, mixed)
6. If neoplastic: cell origin and malignancy criteria present
7. Recommended additional tests

ALWAYS end with: Cytological interpretation requires correlation with clinical findings. Definitive diagnosis by a board-certified veterinary pathologist is recommended.""",

    ImageType.XRAY: """You are a veterinary diagnostic radiology image analysis assistant.
Systematically analyze this radiograph using a structured approach:

TECHNICAL QUALITY:
- Positioning, exposure, and contrast assessment

SYSTEMATIC EVALUATION (describe each):
- Bones/joints: density, cortical integrity, joint spaces, growth plates
- Soft tissues: size, opacity, margins, displacement
- Body cavities: fluid, air, mass effects
- Organs: size, shape, position, opacity (if visible)

FINDINGS: List all radiographic abnormalities

INTERPRETATION: Radiographic differential diagnoses in order of likelihood

RECOMMENDATIONS: Additional views or imaging modalities suggested

ALWAYS end with: Radiographic interpretation is AI-assisted and for reference only. Final diagnosis must be made by a board-certified veterinary radiologist or experienced clinician.""",

    ImageType.ULTRASOUND: """You are a veterinary ultrasonography image analysis assistant.
Analyze this ultrasound image and provide:
1. Structure/organ being imaged (if identifiable)
2. Echogenicity assessment (anechoic, hypoechoic, isoechoic, hyperechoic, mixed)
3. Margination and architecture
4. Size estimation if scale is visible
5. Notable findings (fluid, masses, calcifications, vascular flow if Doppler)
6. Differential diagnoses
7. Recommended follow-up imaging or interventions

ALWAYS end with: Ultrasonographic interpretation requires real-time examination by a trained operator. This AI analysis is for reference only.""",

    ImageType.GENERAL: """You are a veterinary clinical image analysis assistant.
Analyze this veterinary clinical image and provide:
1. What is visible in the image (anatomical region, animal species if determinable)
2. Key findings and abnormalities
3. Clinical significance
4. Differential diagnoses to consider
5. Recommended next steps

Be specific and clinically precise. Use proper veterinary terminology.
ALWAYS end with: This AI analysis is for reference only. Clinical examination by a licensed veterinarian is required.""",
}


# ─── Response model ───────────────────────────────────────────────────────────

@dataclass
class VisionResponse:
    image_type: str
    analysis: str
    ocr_text: str                        # extracted text if OCR was run
    rag_context: list[dict]              # supporting chunks from vector DB
    engine_used: str                     # "gpt4o" or "gemini"
    latency_ms: int
    disclaimer: str = (
        "⚠️ CLINICAL DISCLAIMER: This AI-generated analysis is for reference "
        "purposes only. It does not constitute a veterinary diagnosis. Always "
        "consult a licensed veterinarian before making clinical decisions."
    )

    def to_dict(self) -> dict:
        return {
            "image_type": self.image_type,
            "analysis": self.analysis,
            "ocr_text": self.ocr_text,
            "rag_context": self.rag_context,
            "engine_used": self.engine_used,
            "latency_ms": self.latency_ms,
            "disclaimer": self.disclaimer,
        }


# ─── OCR (cloud fallback) ─────────────────────────────────────────────────────

async def cloud_ocr(image_bytes: bytes, mime_type: str) -> str:
    """
    Google Document AI OCR — cloud fallback when ML Kit unavailable.
    Returns extracted text from image.
    Requires GOOGLE_DOCUMENT_AI_PROCESSOR_ID in .env
    """
    try:
        from google.cloud import documentai

        processor_id = os.getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID", "")
        project_id   = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
        location     = os.getenv("GOOGLE_CLOUD_LOCATION", "us")

        if not processor_id or not project_id:
            return ""

        client = documentai.DocumentProcessorServiceClient()
        name   = client.processor_path(project_id, location, processor_id)

        document = documentai.RawDocument(content=image_bytes, mime_type=mime_type)
        request  = documentai.ProcessRequest(name=name, raw_document=document)
        result   = client.process_document(request=request)

        return result.document.text or ""

    except Exception as e:
        print(f"[OCR] Cloud OCR failed: {e}")
        return ""


# ─── DICOM → JPEG conversion ──────────────────────────────────────────────────

def dicom_to_jpeg(dicom_bytes: bytes) -> tuple[bytes, str]:
    """
    Convert DICOM file to JPEG for vision model input.
    Returns (jpeg_bytes, error_message).
    """
    try:
        import pydicom
        import numpy as np
        from PIL import Image

        ds = pydicom.dcmread(io.BytesIO(dicom_bytes))
        pixel_array = ds.pixel_array

        # Normalize to 8-bit
        pixel_min  = pixel_array.min()
        pixel_max  = pixel_array.max()
        if pixel_max > pixel_min:
            normalized = ((pixel_array - pixel_min) / (pixel_max - pixel_min) * 255).astype(np.uint8)
        else:
            normalized = pixel_array.astype(np.uint8)

        # Convert to RGB if grayscale
        if len(normalized.shape) == 2:
            img = Image.fromarray(normalized, mode='L').convert('RGB')
        else:
            img = Image.fromarray(normalized)

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=90)
        return output.getvalue(), ""

    except ImportError:
        return b"", "pydicom or Pillow not installed. Run: pip install pydicom Pillow"
    except Exception as e:
        return b"", f"DICOM conversion failed: {e}"


# ─── Vision Pipeline ──────────────────────────────────────────────────────────

class VisionPipeline:
    """
    Multi-modal veterinary image analysis pipeline.

    Flow:
      1. Preprocess image (DICOM → JPEG if needed)
      2. Run OCR if text extraction requested
      3. Retrieve relevant RAG context from vector DB
      4. Send image + context to vision LLM
      5. Return structured VisionResponse
    """

    def __init__(self):
        self._openai = None
        self._gemini = None
        self._store  = VetVectorStore(
            db_path=settings.chroma_db_path,
            collection_name=settings.chroma_collection_name,
        )
        self._init_clients()

    def _init_clients(self):
        if settings.openai_api_key:
            self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
        if os.getenv("GOOGLE_AI_API_KEY"):
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GOOGLE_AI_API_KEY"))
                self._gemini = genai
            except ImportError:
                pass

    async def analyze(
        self,
        image_bytes: bytes,
        mime_type: str,
        image_type: ImageType,
        user_query: str = "",
        run_ocr: bool = False,
    ) -> VisionResponse:
        """
        Main entry point — analyze a veterinary image.

        Args:
            image_bytes:  Raw image bytes (JPEG, PNG, or DICOM)
            mime_type:    MIME type string
            image_type:   Type of veterinary image (xray, wound, lesion, etc.)
            user_query:   Optional additional question from the vet
            run_ocr:      Whether to extract text from image first
        """
        start = time.time()

        # Step 1: Handle DICOM
        if mime_type == "application/dicom" or mime_type == "":
            image_bytes, err = dicom_to_jpeg(image_bytes)
            if err:
                return VisionResponse(
                    image_type=image_type.value,
                    analysis=f"DICOM conversion failed: {err}",
                    ocr_text="",
                    rag_context=[],
                    engine_used="none",
                    latency_ms=0,
                )
            mime_type = "image/jpeg"

        # Step 2: OCR if requested
        ocr_text = ""
        if run_ocr:
            ocr_text = await cloud_ocr(image_bytes, mime_type)

        # Step 3: RAG context — retrieve relevant vet knowledge
        search_query = f"{image_type.value} {user_query}".strip()
        rag_chunks = self._store.query(search_query, n_results=3)

        # Step 4: Build prompt
        system_prompt = IMAGE_PROMPTS.get(image_type, IMAGE_PROMPTS[ImageType.GENERAL])
        user_content  = self._build_user_content(
            image_bytes, mime_type, user_query, ocr_text, rag_chunks
        )

        # Step 5: Call LLM with fallback
        analysis, engine = await self._generate(system_prompt, user_content)

        return VisionResponse(
            image_type=image_type.value,
            analysis=analysis,
            ocr_text=ocr_text,
            rag_context=rag_chunks[:3],
            engine_used=engine,
            latency_ms=int((time.time() - start) * 1000),
        )

    def _build_user_content(
        self,
        image_bytes: bytes,
        mime_type: str,
        user_query: str,
        ocr_text: str,
        rag_chunks: list[dict],
    ) -> list[dict]:
        """Build the multimodal message content list for OpenAI."""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}", "detail": "high"},
            }
        ]

        # Add RAG context if available
        if rag_chunks:
            context_text = "\n\n".join(
                f"[From {c.get('document_title', 'Vet Manual')}, p.{c.get('page_number', '?')}]\n{c['text']}"
                for c in rag_chunks
            )
            content.append({
                "type": "text",
                "text": f"Relevant veterinary reference material:\n\n{context_text}\n\n"
                        f"---\nPlease analyze the image above.",
            })
        else:
            content.append({"type": "text", "text": "Please analyze the image above."})

        if user_query:
            content.append({"type": "text", "text": f"Specific question: {user_query}"})

        if ocr_text:
            content.append({"type": "text", "text": f"Text extracted from image (OCR):\n{ocr_text}"})

        return content

    async def _generate(
        self, system_prompt: str, user_content: list[dict]
    ) -> tuple[str, str]:
        """Call GPT-4o Vision with Gemini fallback."""

        # Primary: GPT-4o Vision
        if self._openai:
            try:
                response = await self._openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content},
                    ],
                    max_tokens=1500,
                    temperature=0.1,
                )
                return response.choices[0].message.content, "gpt4o"
            except Exception as e:
                print(f"[Vision] GPT-4o failed: {e}, trying Gemini fallback")

        # Fallback: Gemini 2.0 Flash
        if self._gemini:
            try:
                import google.generativeai as genai
                import PIL.Image

                model = genai.GenerativeModel("gemini-2.0-flash-exp")

                # Convert bytes to PIL for Gemini
                pil_image = PIL.Image.open(io.BytesIO(
                    next(
                        p["image_url"]["url"].split(",")[1].encode()
                        for p in user_content
                        if p.get("type") == "image_url"
                    )
                ))
                # Actually decode the base64
                b64_data = next(
                    p["image_url"]["url"].split(",")[1]
                    for p in user_content
                    if p.get("type") == "image_url"
                )
                pil_image = PIL.Image.open(io.BytesIO(base64.b64decode(b64_data)))

                text_parts = [
                    p["text"] for p in user_content if p.get("type") == "text"
                ]
                prompt = system_prompt + "\n\n" + "\n".join(text_parts)

                response = model.generate_content([pil_image, prompt])
                return response.text, "gemini"

            except Exception as e:
                print(f"[Vision] Gemini fallback failed: {e}")

        return (
            "Vision analysis unavailable. Please configure OPENAI_API_KEY or "
            "GOOGLE_AI_API_KEY in your .env file.",
            "none",
        )

    def health(self) -> dict:
        return {
            "gpt4o_ready":  self._openai is not None,
            "gemini_ready": self._gemini is not None,
            "chroma_chunks": self._store.stats()["total_chunks"],
        }


# Singleton
vision_pipeline = VisionPipeline()
