"""
vetgpt/backend/upload_routes.py

PDF upload endpoint — allows authenticated users to upload vet manuals
directly from the mobile app for indexing into ChromaDB.

Route:
  POST /api/manuals/upload   — upload PDF, trigger ingestion
  GET  /api/manuals/list     — list user-uploaded sources
  DELETE /api/manuals/{key}  — remove an indexed source
"""

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from .auth import get_current_user
from .database import User
from .config import get_settings
from ingestion.pdf_parser import VetPDFParser
from ingestion.chunker import VetChunker
from ingestion.embedder import VetVectorStore
from config.book_registry import detect_book

settings = get_settings()
upload_router = APIRouter(prefix="/api/manuals", tags=["manuals"])

MAX_PDF_BYTES = 100 * 1024 * 1024   # 100 MB
UPLOAD_DIR    = Path("./data/pdfs/uploaded")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename: str) -> str:
    """Sanitise filename — keep only safe characters."""
    import re
    name = Path(filename).stem
    ext  = Path(filename).suffix.lower()
    safe = re.sub(r'[^a-z0-9._\-]', '_', name.lower())
    return f"{safe}{ext}"


async def _ingest_pdf(pdf_path: Path, user_id: str):
    """Background task: parse → chunk → embed → store."""
    try:
        parser  = VetPDFParser()
        chunker = VetChunker()
        store   = VetVectorStore()

        doc    = parser.parse(pdf_path)
        chunks = chunker.chunk_document(doc)

        # Tag chunks with uploader info
        for chunk in chunks:
            chunk.metadata["uploaded_by"] = user_id
            chunk.metadata["upload_source"] = "mobile_upload"

        store.add_chunks(chunks)
        print(f"[Upload] Indexed {len(chunks)} chunks from {pdf_path.name}")
    except Exception as e:
        print(f"[Upload] Ingestion failed for {pdf_path.name}: {e}")


@upload_router.post("/upload")
async def upload_manual(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload a PDF veterinary manual for indexing.
    Ingestion runs in the background — the endpoint returns immediately.
    """
    # Validate
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted.")

    content = await file.read()

    if len(content) < 100:
        raise HTTPException(status_code=400, detail="File appears to be empty.")

    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) // 1024 // 1024} MB). Maximum is 100 MB."
        )

    # Save to upload directory
    safe_name = _safe_filename(file.filename)
    dest_path = UPLOAD_DIR / safe_name

    with open(dest_path, "wb") as f:
        f.write(content)

    # Detect book from filename for richer metadata
    book = detect_book(safe_name)
    book_info = {
        "detected_title": book.title if book else safe_name,
        "publisher":      book.publisher if book else "Unknown",
        "legal_status":   book.legal_status if book else "unknown",
    } if book else {}

    # Trigger background ingestion
    background_tasks.add_task(_ingest_pdf, dest_path, user.id)

    return {
        "filename":    safe_name,
        "size_mb":     round(len(content) / 1024 / 1024, 2),
        "status":      "uploaded",
        "message":     "PDF received. Indexing in background — this takes 1-5 minutes.",
        "book_info":   book_info,
    }


@upload_router.get("/list")
async def list_uploaded(user: User = Depends(get_current_user)):
    """List all indexed sources (uploaded + scraped)."""
    store   = VetVectorStore()
    sources = store.list_sources()
    return {"sources": sources, "total": len(sources)}


@upload_router.delete("/{source_key}")
async def delete_source(
    source_key: str,
    user: User = Depends(get_current_user),
):
    """Remove all chunks from a source. Only the uploader or admin can delete."""
    store   = VetVectorStore()
    deleted = store.delete_source(source_key)
    return {"source": source_key, "chunks_deleted": deleted}
