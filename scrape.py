"""
vetgpt/scrape.py

CLI entry point for the VetGPT web scraping pipeline.

Usage:
    # Scrape everything (WikiVet + PubMed + FAO)
    python scrape.py run-all

    # Scrape individual sources
    python scrape.py wikivet
    python scrape.py pubmed
    python scrape.py pubmed --api-key YOUR_NCBI_KEY
    python scrape.py fao

    # Re-index from cache (no network calls)
    python scrape.py from-cache

    # Test the DB after scraping
    python scrape.py test-query "canine parvovirus treatment"
    python scrape.py test-query "bovine respiratory disease" --source wikivet
"""

import click
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from scraping import ScrapingPipeline
from ingestion import VetVectorStore

load_dotenv()
console = Console()


@click.group()
def cli():
    """VetGPT Web Scraping Pipeline"""
    console.print(Panel(
        "[bold cyan]VetGPT Web Scraper[/bold cyan]\n"
        "WikiVet (CC BY-SA) + PubMed (Public Domain) + FAO (Open Access)",
        border_style="cyan"
    ))


@cli.command("run-all")
@click.option("--api-key", default=None, help="NCBI API key (optional, increases rate limit)")
@click.option("--cache", is_flag=True, help="Use cached data instead of scraping")
def run_all(api_key, cache):
    """Scrape all sources and index into ChromaDB."""
    pipeline = ScrapingPipeline(
        ncbi_api_key=api_key or os.getenv("NCBI_API_KEY"),
        use_cache=cache,
    )
    pipeline.run_all()


@cli.command()
@click.option("--cache", is_flag=True, help="Load from cache")
def wikivet(cache):
    """Scrape WikiVet veterinary articles."""
    pipeline = ScrapingPipeline(use_cache=cache)
    pipeline.run_wikivet_only()


@cli.command()
@click.option("--api-key", default=None, help="NCBI API key")
@click.option("--cache", is_flag=True, help="Load from cache")
def pubmed(api_key, cache):
    """Fetch PubMed veterinary research abstracts."""
    pipeline = ScrapingPipeline(
        ncbi_api_key=api_key or os.getenv("NCBI_API_KEY"),
        use_cache=cache,
    )
    pipeline.run_pubmed_only()


@cli.command()
@click.option("--cache", is_flag=True, help="Load from cache")
def fao(cache):
    """Download FAO animal health documents."""
    pipeline = ScrapingPipeline(use_cache=cache)
    pipeline.run_fao_only()



@cli.command()
@click.option("--cache", is_flag=True, help="Load from cache")
def eclinpath(cache):
    """Scrape eClinPath (Cornell University) clinical pathology content."""
    pipeline = ScrapingPipeline(use_cache=cache)
    pipeline.run_eclinpath_only()

@cli.command("from-cache")
def from_cache():
    """Re-index all sources from local cache (no network)."""
    pipeline = ScrapingPipeline(use_cache=True)
    pipeline.run_from_cache()


@cli.command("test-query")
@click.argument("query_text")
@click.option("--n", default=5, help="Number of results")
@click.option("--source", default=None, help="Filter: wikivet | pubmed | fao")
def test_query(query_text, n, source):
    """Test the ChromaDB with a query after scraping."""
    store = VetVectorStore()

    # Map source shorthand to actual source_file prefix filter
    where = None
    if source:
        # ChromaDB where filter on metadata
        pass  # handled via source prefix in query

    console.print(f"\n[bold]Query:[/bold] {query_text}\n")
    results = store.query(query_text, n_results=n, filter_source=source)

    if not results:
        console.print("[yellow]No results found. Try a broader query or check that data has been indexed.[/yellow]")
        return

    for i, r in enumerate(results, 1):
        console.print(
            f"[green]{i}.[/green] [{r['score']:.3f}] "
            f"[cyan]{r['source_file']}[/cyan] p.{r['page_number']}\n"
            f"   {r['text'][:200]}...\n"
        )


if __name__ == "__main__":
    cli()
