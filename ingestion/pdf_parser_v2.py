"""
vetgpt/ingestion/pdf_parser_v2.py

Drop-in upgrade for pdf_parser.py that auto-detects book metadata
from the registry and enriches ChromaDB metadata with full citation info.

Replace your VetPDFParser import with VetPDFParserV2.
"""

from pathlib import Path
from .pdf_parser import VetPDFParser, ParsedDocument
from config.book_registry import detect_book, BOOK_REGISTRY, BookMeta
from rich.console import Console

console = Console()


class VetPDFParserV2(VetPDFParser):
    """
    Extended PDF parser with book registry integration.

    Auto-detects which book a PDF is from its filename,
    enriches metadata with publisher, citation, legal status, etc.
    Falls back to generic metadata if book is not in registry.
    """

    def parse(self, pdf_path: str | Path) -> ParsedDocument:
        """Parse PDF and enrich with registry metadata."""
        doc = super().parse(pdf_path)

        # Try to detect book from filename
        book: BookMeta | None = detect_book(Path(pdf_path).name)

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
