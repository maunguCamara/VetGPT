"""
vetgpt/ingestion/chunker.py

Splits parsed veterinary documents into chunks suitable for embedding.
Uses a recursive character splitter with vet-aware separators.
"""

from dataclasses import dataclass, field
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .pdf_parser import ParsedDocument
from rich.console import Console

console = Console()


@dataclass
class DocumentChunk:
    """
    A single chunk ready for embedding and storage in ChromaDB.

    Each chunk carries full provenance so you can always trace
    an answer back to the exact source page.
    """
    chunk_id: str           # unique: "{filename}_{page}_{idx}"
    text: str               # the actual text content
    source_file: str        # original PDF filename
    source_path: str        # full path to the PDF
    document_title: str     # PDF title
    page_number: int        # page this chunk came from
    chunk_index: int        # position within this page's chunks
    word_count: int         # word count of this chunk
    metadata: dict = field(default_factory=dict)  # extra fields for ChromaDB


class VetChunker:
    """
    Chunks parsed vet documents using a recursive splitter.

    Strategy:
    - Split on paragraph breaks first, then sentences, then words
    - Use vet-specific separators (numbered lists, drug headings, etc.)
    - Each chunk retains page-level provenance
    - Overlapping chunks reduce context loss at boundaries
    """

    # Separators tried in order (most preferred → least preferred)
    # These match common vet manual formatting patterns
    VET_SEPARATORS = [
        "\n\n",          # paragraph break
        "\n",            # line break
        ". ",            # sentence boundary
        "? ",            # question boundary
        "! ",            # exclamation boundary
        "; ",            # semicolon (common in drug lists)
        ", ",            # comma
        " ",             # word boundary (last resort)
        "",              # character boundary (absolute last resort)
    ]

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        """
        Args:
            chunk_size:    Target chunk size in characters.
                           512 chars ≈ 128 tokens, good for most embedding models.
            chunk_overlap: Characters of overlap between adjacent chunks.
                           Prevents answers being split across chunk boundaries.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=self.VET_SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk_document(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """
        Chunk a single ParsedDocument into a flat list of DocumentChunks.

        Args:
            doc: A ParsedDocument from VetPDFParser.

        Returns:
            List of DocumentChunks ready for embedding.
        """
        all_chunks: list[DocumentChunk] = []

        for page in doc.pages:
            if not page.text.strip():
                continue

            # Split the page text into chunks
            raw_chunks = self._splitter.split_text(page.text)

            for idx, chunk_text in enumerate(raw_chunks):
                chunk_text = chunk_text.strip()
                if not chunk_text or len(chunk_text) < 30:
                    # Skip very short chunks — usually noise
                    continue

                chunk_id = f"{doc.filename}_p{page.page_number}_c{idx}"

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    source_file=doc.filename,
                    source_path=doc.source_path,
                    document_title=doc.title,
                    page_number=page.page_number,
                    chunk_index=idx,
                    word_count=len(chunk_text.split()),
                    metadata={
                        # ChromaDB metadata must be str/int/float/bool only
                        "source_file": doc.filename,
                        "source_path": doc.source_path,
                        "document_title": doc.title,
                        "page_number": page.page_number,
                        "chunk_index": idx,
                        "has_tables": page.has_tables,
                        "has_images": page.has_images,
                        "word_count": len(chunk_text.split()),
                    }
                )
                all_chunks.append(chunk)

        return all_chunks

    def chunk_documents(self, docs: list[ParsedDocument]) -> list[DocumentChunk]:
        """
        Chunk multiple ParsedDocuments.

        Args:
            docs: List of ParsedDocuments.

        Returns:
            Flat list of all DocumentChunks across all documents.
        """
        all_chunks: list[DocumentChunk] = []

        for doc in docs:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
            console.print(
                f"[cyan]Chunked:[/cyan] {doc.filename} → "
                f"{len(chunks)} chunks "
                f"(avg {sum(c.word_count for c in chunks) // max(len(chunks), 1)} words/chunk)"
            )

        console.print(
            f"\n[bold green]Total chunks:[/bold green] "
            f"{len(all_chunks):,} across {len(docs)} documents"
        )
        return all_chunks
