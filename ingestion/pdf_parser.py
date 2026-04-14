"""
vetgpt/ingestion/pdf_parser.py

Extracts clean text from veterinary PDF manuals using PyMuPDF.
Handles multi-column layouts, headers/footers, and table detection.
"""

import fitz  # PyMuPDF
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console


console = Console()


@dataclass
class ParsedPage:
    """Represents a single parsed page from a PDF."""
    page_number: int
    text: str
    word_count: int
    has_tables: bool = False
    has_images: bool = False


@dataclass
class ParsedDocument:
    """Represents a fully parsed PDF document."""
    source_path: str
    filename: str
    title: str
    total_pages: int
    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())

    @property
    def total_words(self) -> int:
        return sum(p.word_count for p in self.pages)


class VetPDFParser:

    """
    Parses veterinary PDF manuals with clean text extraction.

    Handles:
    - Multi-column layouts (common in Merck Vet Manual style PDFs)
    - Header/footer removal (page numbers, chapter titles)
    - Basic table detection
    - Metadata extraction (title, author, subject)
    """

    # Patterns to strip from extracted text
    NOISE_PATTERNS = [
        r'^\d+\s*$',                          # lone page numbers
        r'^(merck|msd)\s+veterinary.*$',       # publisher headers
        r'^\s*copyright.*$',                   # copyright lines
        r'^\s*all rights reserved.*$',
        r'www\.[a-z]+\.[a-z]+',               # URLs
        r'^\s*table of contents\s*$',
    ]

    def __init__(self, min_page_words: int = 20):
        """
        Args:
            min_page_words: Skip pages with fewer words than this
                           (catches blank pages, image-only pages).
        """
        self.min_page_words = min_page_words
        self._noise_re = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.NOISE_PATTERNS
        ]

    def parse(self, pdf_path: str | Path) -> ParsedDocument:
        """
        Parse a single PDF file into a ParsedDocument.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParsedDocument with all extracted pages and metadata.

        Raises:
            FileNotFoundError: If the PDF doesn't exist.
            ValueError: If the file isn't a valid PDF.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        console.print(f"[cyan]Parsing:[/cyan] {pdf_path.name}")

        # Use context manager — guarantees doc is closed even on error,
        # and all data is extracted BEFORE the document is closed.
        with fitz.open(str(pdf_path)) as doc:
            metadata    = self._extract_metadata(doc, pdf_path)
            total_pages = len(doc)          # must be read while doc is open
            pages       = []

            for page_num in range(total_pages):
                page   = doc[page_num]
                parsed = self._parse_page(page, page_num + 1)
                if parsed.word_count >= self.min_page_words:
                    pages.append(parsed)
            doc.close()

        parsed_doc = ParsedDocument(
            source_path=str(pdf_path.resolve()),
            filename=pdf_path.name,
            title=metadata.get("title", pdf_path.stem),
            total_pages=total_pages,
            pages=pages,
            metadata=metadata,
        )

        console.print(
            f"[green]✓[/green] {pdf_path.name}: "
            f"{len(pages)} usable pages, "
            f"{parsed_doc.total_words:,} words"
        )
        return parsed_doc

    def parse_directory(self, directory: str | Path) -> list[ParsedDocument]:
        """
        Parse all PDFs in a directory recursively.

        Args:
            directory: Path to folder containing vet manual PDFs.

        Returns:
            List of ParsedDocuments, one per PDF.
        """
        directory = Path(directory)
        pdf_files = sorted(directory.rglob("*.pdf"))

        if not pdf_files:
            console.print(f"[yellow]No PDFs found in {directory}[/yellow]")
            return []

        console.print(f"\n[bold]Found {len(pdf_files)} PDFs to parse[/bold]\n")
        documents = []

        for pdf_path in pdf_files:
            try:
                doc = self.parse(pdf_path)
                documents.append(doc)
            except Exception as e:
                console.print(f"[red]✗ Failed:[/red] {pdf_path.name} — {e}")

        console.print(
            f"\n[bold green]Parsing complete:[/bold green] "
            f"{len(documents)}/{len(pdf_files)} PDFs parsed successfully"
        )
        return documents

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_page(self, page: fitz.Page, page_number: int) -> ParsedPage:
        """Extract and clean text from a single PDF page."""

        # Sort text blocks by vertical position for correct reading order
        # This handles multi-column layouts better than raw text extraction
        blocks = page.get_text("blocks", sort=True)

        lines = []
        for block in blocks:
            # block = (x0, y0, x1, y1, text, block_no, block_type)
            if block[6] == 0:  # type 0 = text block (type 1 = image)
                text = block[4].strip()
                if text:
                    lines.append(text)

        raw_text = "\n".join(lines)
        cleaned = self._clean_text(raw_text)
        word_count = len(cleaned.split())

        # Detect tables (simple heuristic: many short tab-separated lines)
        has_tables = self._detect_tables(page)
        has_images = len(page.get_images()) > 0

        return ParsedPage(
            page_number=page_number,
            text=cleaned,
            word_count=word_count,
            has_tables=has_tables,
            has_images=has_images,
        )

    def _clean_text(self, text: str) -> str:
        """Remove noise, fix spacing, normalize whitespace."""

        # Remove noise patterns line by line
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if any(r.match(stripped) for r in self._noise_re):
                continue
            clean_lines.append(stripped)

        text = " ".join(clean_lines)

        # Fix hyphenated line breaks (common in PDFs): "diag-\nnosis" → "diagnosis"
        text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _detect_tables(self, page: fitz.Page) -> bool:
        """Heuristic: detect if a page likely contains a table."""
        # Pages with many small horizontal lines often have tables
        drawings = page.get_drawings()
        horizontal_lines = [
            d for d in drawings
            if abs(d["rect"].y1 - d["rect"].y0) < 3  # nearly horizontal
            and d["rect"].width > 50
        ]
        return len(horizontal_lines) > 5

    def _extract_metadata(self, doc: fitz.Document, path: Path) -> dict:
        """Extract PDF metadata (title, author, etc.)."""
        raw_meta = doc.metadata or {}
        return {
            "title": raw_meta.get("title") or path.stem,
            "author": raw_meta.get("author", ""),
            "subject": raw_meta.get("subject", ""),
            "keywords": raw_meta.get("keywords", ""),
            "page_count": len(doc),
            "filename": path.name,
            "source": "pdf",
        }

class VetPDFParserWithRegistry(VetPDFParser):
    """
    Extended PDF parser with book registry integration.
    
    Auto-detects which book a PDF is from its filename,
    enriches metadata with publisher, citation, legal status, etc.
    Falls back to generic metadata if book is not in registry.
    """
    
    def parse(self, pdf_path: str | Path) -> ParsedDocument:
        """Parse PDF and enrich with registry metadata."""
        # First, parse using parent class method
        doc = super().parse(pdf_path)
        
        # Try to detect book from filename
        from config.book_registry import detect_book
        book = detect_book(Path(pdf_path).name)
        
        if book:
            console.print(
                f"  [green]✓ Detected:[/green] {book.short_title} "
                f"[dim]({book.legal_status})[/dim]"
            )
            # Enrich document metadata
            doc.metadata.update({
                "book_key": book.key,
                "short_title": book.short_title,
                "authors": ", ".join(book.authors[:3]),
                "edition": book.edition,
                "year": book.year,
                "publisher": book.publisher,
                "publisher_short": book.publisher_short,
                "legal_status": book.legal_status,
                "citation": book.citation_format,
                "subject_tags": ", ".join(book.subject_tags),
                "species_tags": ", ".join(book.species_tags),
                "content_type": book.content_type,
                "isbn": book.isbn,
            })
            # Use canonical title from registry
            doc.title = book.title
        else:
            console.print(
                f"  [yellow]⚠ Unknown book:[/yellow] {Path(pdf_path).name} "
                f"[dim](add to book_registry.py for full metadata)[/dim]"
            )
        
        return doc