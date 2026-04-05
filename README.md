# VetGPT — Phase 1: Ingestion Pipeline

## Project Structure

```
vetgpt/
├── ingestion/
│   ├── __init__.py       # Module exports
│   ├── pdf_parser.py     # Step 1: Parse PDFs → text + metadata
│   ├── chunker.py        # Step 2: Split text → chunks with provenance
│   └── embedder.py       # Step 3: Embed chunks → ChromaDB
├── data/
│   ├── pdfs/             # Drop your vet manual PDFs here
│   └── chroma_db/        # Auto-created — ChromaDB storage
├── ingest.py             # CLI entry point
├── requirements.txt
└── .env.example          # Copy to .env and configure
```

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate      # Linux/Mac
venv\Scripts\activate         # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env if needed (defaults work out of the box with local embeddings)

# 4. Add your PDFs
cp /path/to/merck_vet_manual.pdf data/pdfs/
```

## Usage

```bash
# Ingest a single PDF
python ingest.py ingest --pdf data/pdfs/merck_vet_manual.pdf

# Ingest an entire folder of PDFs
python ingest.py ingest --dir data/pdfs/

# Test with a query
python ingest.py query "treatment for canine parvovirus"
python ingest.py query "drug dosage for feline hyperthyroidism" --n 3

# Filter results by source file
python ingest.py query "bovine respiratory disease" --source merck_vet_manual.pdf

# Check what's indexed
python ingest.py stats
python ingest.py list-sources

# Re-index an updated manual
python ingest.py delete merck_vet_manual.pdf
python ingest.py ingest --pdf data/pdfs/merck_vet_manual.pdf
```

## How It Works

```
PDF files
    │
    ▼
VetPDFParser          → Extracts text page by page
    │                   Strips headers/footers/page numbers
    │                   Handles multi-column layouts
    │
    ▼
VetChunker            → Splits text into ~512-char chunks
    │                   64-char overlap between chunks
    │                   Each chunk tagged with source + page number
    │
    ▼
VetVectorStore        → Embeds each chunk (local or OpenAI)
                        Upserts to ChromaDB (deduplication safe)
                        Persisted to disk at data/chroma_db/
```

## Switching to Better Embeddings

The default local model (`all-MiniLM-L6-v2`) is fast and works offline.
For production, use a biomedical embedding model for better vet accuracy:

In `embedder.py`, change:
```python
model_name="all-MiniLM-L6-v2"
# to:
model_name="pritamdeka/S-PubMedBert-MS-MARCO"  # biomedical-tuned
```

Or switch to OpenAI in `.env`:
```
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```



