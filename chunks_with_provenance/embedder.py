"""
vetgpt/ingestion/embedder.py

Embeds document chunks and stores them in ChromaDB.
Uses local sentence-transformers by default (no API key required).
Swap EMBEDDING_PROVIDER=openai in .env for production quality.
"""

import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from .chunker import DocumentChunk
import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console
from rich.progress import track

load_dotenv()
console = Console()


def get_embedding_function():
    """
    Return the appropriate ChromaDB embedding function based on config.

    local   → sentence-transformers/all-MiniLM-L6-v2 (free, offline-capable)
    openai  → text-embedding-3-small (better quality, needs API key)
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "local").lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        console.print("[cyan]Using:[/cyan] OpenAI text-embedding-3-small")
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name="text-embedding-3-small",
        )
    else:
        console.print("[cyan]Using:[/cyan] Local sentence-transformers (all-MiniLM-L6-v2)")
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
            # For better vet accuracy, swap to:
            # "pritamdeka/S-PubMedBert-MS-MARCO" (biomedical-tuned)
        )


class VetVectorStore:
    """
    Manages the ChromaDB collection for vet manual chunks.

    Handles:
    - Creating / connecting to a persistent ChromaDB collection
    - Batch embedding and upsert (safe to re-run — deduplicates by chunk_id)
    - Similarity search with metadata filtering
    - Collection stats
    """

    BATCH_SIZE = 100  # ChromaDB performs best with batches of ~100

    def __init__(
        self,
        db_path: str | None = None,
        collection_name: str | None = None,
    ):
        db_path = db_path or os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
        collection_name = collection_name or os.getenv(
            "CHROMA_COLLECTION_NAME", "vet_manuals"
        )

        Path(db_path).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=db_path)
        self._ef = get_embedding_function()

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={
                "hnsw:space": "cosine",   # cosine similarity (best for text)
                "description": "VetGPT veterinary manual chunks",
            }
        )

        console.print(
            f"[green]✓[/green] ChromaDB ready: [bold]{collection_name}[/bold] "
            f"({self._collection.count():,} existing chunks)"
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_chunks(self, chunks: list[DocumentChunk]) -> int:
        """
        Embed and upsert chunks into ChromaDB.
        Safe to call multiple times — uses chunk_id to deduplicate.

        Args:
            chunks: List of DocumentChunks from VetChunker.

        Returns:
            Number of chunks successfully added.
        """
        if not chunks:
            console.print("[yellow]No chunks to add.[/yellow]")
            return 0

        console.print(f"\n[bold]Embedding {len(chunks):,} chunks...[/bold]")
        added = 0

        # Process in batches to avoid memory issues with large collections
        for i in track(
            range(0, len(chunks), self.BATCH_SIZE),
            description="Embedding batches",
        ):
            batch = chunks[i : i + self.BATCH_SIZE]

            ids = [c.chunk_id for c in batch]
            documents = [c.text for c in batch]
            metadatas = [c.metadata for c in batch]

            # upsert = insert if new, update if exists (idempotent)
            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            added += len(batch)

        console.print(
            f"[bold green]✓ Done:[/bold green] "
            f"{added:,} chunks stored. "
            f"Collection total: {self._collection.count():,}"
        )
        return added

    # ------------------------------------------------------------------
    # Querying (used by FastAPI RAG endpoint in Phase 2)
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        filter_source: str | None = None,
    ) -> list[dict]:
        """
        Retrieve the most relevant chunks for a query.

        Args:
            query_text:    The user's question.
            n_results:     Number of chunks to return.
            filter_source: Optional — filter by source filename.

        Returns:
            List of dicts with keys: text, score, source_file, page_number,
            document_title, chunk_id.
        """
        where = {"source_file": filter_source} if filter_source else None

        results = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "text": doc,
                "score": round(1 - dist, 4),  # convert distance → similarity
                "source_file": meta.get("source_file"),
                "page_number": meta.get("page_number"),
                "document_title": meta.get("document_title"),
                "chunk_id": results["ids"][0][len(output)],
            })

        return output

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return collection statistics."""
        count = self._collection.count()
        return {
            "total_chunks": count,
            "collection_name": self._collection.name,
        }

    def delete_source(self, source_file: str) -> int:
        """
        Remove all chunks from a specific source file.
        Useful when re-indexing an updated manual.
        """
        results = self._collection.get(
            where={"source_file": source_file},
            include=[],
        )
        ids = results["ids"]
        if ids:
            self._collection.delete(ids=ids)
            console.print(
                f"[yellow]Deleted[/yellow] {len(ids)} chunks from {source_file}"
            )
        return len(ids)

    def list_sources(self) -> list[str]:
        """List all indexed source files."""
        results = self._collection.get(include=["metadatas"])
        sources = {m.get("source_file") for m in results["metadatas"]}
        return sorted(s for s in sources if s)
