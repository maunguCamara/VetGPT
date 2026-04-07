"""
vetgpt/scraping/pipeline.py

Unified scraping pipeline — runs all scrapers and feeds results
directly into the existing ChromaDB ingestion pipeline.

Converts scraped articles/documents into DocumentChunks
using the same VetChunker and VetVectorStore as the PDF pipeline.
"""

from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ingestion.chunker import VetChunker, DocumentChunk
from ingestion.embedder import VetVectorStore
from .wikivet_scraper import WikiVetScraper, ScrapedArticle
from .pubmed_scraper import PubMedScraper, PubMedArticle
from .fao_scraper import FAOScraper, FAODocument
from .eclinpath_scraper import EClinPathScraper, EClinPathArticle

console = Console()


def article_to_chunks(
    article,
    chunker: VetChunker,
) -> list[DocumentChunk]:
    """
    Convert any scraped article/document into DocumentChunks.
    Works with ScrapedArticle, PubMedArticle, and FAODocument.
    """
    text = article.text
    metadata = article.to_metadata()

    if not text.strip():
        return []

    raw_chunks = chunker._splitter.split_text(text)
    chunks = []

    for idx, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text or len(chunk_text) < 30:
            continue

        source_file = metadata.get("source_file", "unknown")
        chunk_id = f"{source_file}_c{idx}"

        # Update chunk-level metadata
        chunk_metadata = {**metadata, "chunk_index": idx}

        chunks.append(DocumentChunk(
            chunk_id=chunk_id,
            text=chunk_text,
            source_file=source_file,
            source_path=article.url,
            document_title=metadata.get("document_title", ""),
            page_number=metadata.get("page_number", 1),
            chunk_index=idx,
            word_count=len(chunk_text.split()),
            metadata=chunk_metadata,
        ))

    return chunks


class ScrapingPipeline:
    """
    Orchestrates all scrapers and feeds content into ChromaDB.

    Usage:
        pipeline = ScrapingPipeline()
        pipeline.run_all()              # scrape everything fresh
        pipeline.run_wikivet_only()     # just WikiVet
        pipeline.run_from_cache()       # use cached data, skip network
    """

    def __init__(
        self,
        ncbi_api_key: str | None = None,
        use_cache: bool = False,
    ):
        self.chunker = VetChunker(chunk_size=512, chunk_overlap=64)
        self.store = VetVectorStore()
        self.use_cache = use_cache

        # Initialise scrapers
        self.wikivet = WikiVetScraper()
        self.pubmed = PubMedScraper(ncbi_api_key=ncbi_api_key)
        self.fao = FAOScraper()
        self.eclinpath = EClinPathScraper()

    # ------------------------------------------------------------------
    # Public runners
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """Run all three scrapers and index everything."""
        console.print(Panel(
            "[bold cyan]VetGPT Web Scraping Pipeline[/bold cyan]\n"
            "WikiVet + PubMed + FAO → ChromaDB",
            border_style="cyan"
        ))

        stats = {}

        stats["wikivet"]   = self._run_wikivet()
        stats["pubmed"]    = self._run_pubmed()
        stats["fao"]       = self._run_fao()
        stats["eclinpath"] = self._run_eclinpath()

        self._print_summary(stats)
        return stats

    def run_wikivet_only(self) -> int:
        return self._run_wikivet()

    def run_pubmed_only(self) -> int:
        return self._run_pubmed()

    def run_fao_only(self) -> int:
        return self._run_fao()

    def run_eclinpath_only(self) -> int:
        return self._run_eclinpath()

    def run_from_cache(self) -> dict:
        """Load all scrapers from cache and re-index (no network calls)."""
        console.print("[bold]Loading from cache...[/bold]")
        stats = {}

        wikivet_articles = self.wikivet.load_cached()
        stats["wikivet"] = self._index_articles(wikivet_articles, "WikiVet")

        pubmed_articles = self.pubmed.load_cached()
        stats["pubmed"] = self._index_articles(pubmed_articles, "PubMed")

        fao_docs = self.fao.load_cached()
        stats["fao"] = self._index_articles(fao_docs, "FAO")

        eclinpath_articles = self.eclinpath.load_cached()
        stats["eclinpath"] = self._index_articles(eclinpath_articles, "eClinPath")

        self._print_summary(stats)
        return stats

    # ------------------------------------------------------------------
    # Private runners
    # ------------------------------------------------------------------

    def _run_wikivet(self) -> int:
        if self.use_cache:
            articles = self.wikivet.load_cached()
        else:
            articles = self.wikivet.scrape_all()
        return self._index_articles(articles, "WikiVet")

    def _run_pubmed(self) -> int:
        if self.use_cache:
            articles = self.pubmed.load_cached()
        else:
            articles = self.pubmed.scrape_all()
        return self._index_articles(articles, "PubMed")

    def _run_fao(self) -> int:
        if self.use_cache:
            docs = self.fao.load_cached()
        else:
            docs = self.fao.scrape_all()
        return self._index_articles(docs, "FAO")

    def _run_eclinpath(self) -> int:
        if self.use_cache:
            articles = self.eclinpath.load_cached()
        else:
            articles = self.eclinpath.scrape_all()
        return self._index_articles(articles, "eClinPath")

    def _index_articles(self, articles: list, source_name: str) -> int:
        """Convert articles to chunks and upsert into ChromaDB."""
        if not articles:
            console.print(f"[yellow]No {source_name} articles to index.[/yellow]")
            return 0

        console.print(f"\n[bold]Chunking {len(articles)} {source_name} articles...[/bold]")

        all_chunks = []
        for article in articles:
            chunks = article_to_chunks(article, self.chunker)
            all_chunks.extend(chunks)

        console.print(
            f"[cyan]{source_name}:[/cyan] {len(articles)} articles → "
            f"{len(all_chunks)} chunks"
        )

        added = self.store.add_chunks(all_chunks)
        return added

    def _print_summary(self, stats: dict):
        """Print a summary table of what was indexed."""
        table = Table(title="Scraping Pipeline Summary")
        table.add_column("Source", style="cyan")
        table.add_column("Chunks indexed", style="green", justify="right")

        total = 0
        for source, count in stats.items():
            table.add_row(source.capitalize(), f"{count:,}")
            total += count

        table.add_row("[bold]Total[/bold]", f"[bold]{total:,}[/bold]")
        console.print(table)

        # Show overall DB stats
        db_stats = self.store.stats()
        console.print(
            f"\n[bold green]ChromaDB total:[/bold green] "
            f"{db_stats['total_chunks']:,} chunks across all sources"
        )
