"""
vetgpt/ingest.py

CLI entry point for the VetGPT ingestion pipeline.

Usage:
    # Ingest a single PDF
    python ingest.py --pdf ./data/pdfs/merck_vet_manual.pdf

    # Ingest all PDFs in a folder
    python ingest.py --dir ./data/pdfs/

    # Query the DB to test results
    python ingest.py --query "treatment for canine parvovirus"

    # Show collection stats
    python ingest.py --stats

    # List all indexed sources
    python ingest.py --list-sources

    # Delete and re-index a specific file
    python ingest.py --delete merck_vet_manual.pdf --pdf ./data/pdfs/merck_vet_manual.pdf
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from ingestion import VetPDFParser, VetChunker, VetVectorStore

console = Console()


def get_pipeline():
    """Initialise the three pipeline components."""
    parser = VetPDFParser(min_page_words=20)
    chunker = VetChunker(chunk_size=512, chunk_overlap=64)
    store = VetVectorStore()
    return parser, chunker, store


@click.group()
def cli():
    """VetGPT Ingestion Pipeline"""
    console.print(Panel(
        "[bold cyan]VetGPT Ingestion Pipeline[/bold cyan]\n"
        "Parse → Chunk → Embed → Store",
        border_style="cyan"
    ))


@cli.command()
@click.option("--pdf", type=click.Path(exists=True), help="Path to a single PDF file")
@click.option("--dir", "directory", type=click.Path(exists=True), help="Directory of PDFs")
def ingest(pdf, directory):
    """Parse PDFs and store chunks in ChromaDB."""
    if not pdf and not directory:
        console.print("[red]Provide --pdf or --dir[/red]")
        return

    parser, chunker, store = get_pipeline()

    # Step 1: Parse
    if pdf:
        docs = [parser.parse(pdf)]
    else:
        docs = parser.parse_directory(directory)

    if not docs:
        console.print("[red]No documents parsed.[/red]")
        return

    # Step 2: Chunk
    console.print("\n[bold]Chunking documents...[/bold]")
    chunks = chunker.chunk_documents(docs)

    if not chunks:
        console.print("[red]No chunks generated.[/red]")
        return

    # Step 3: Embed + Store
    added = store.add_chunks(chunks)
    console.print(f"\n[bold green]Pipeline complete:[/bold green] {added:,} chunks indexed.")


@cli.command()
@click.argument("query_text")
@click.option("--n", default=5, help="Number of results to return")
@click.option("--source", default=None, help="Filter by source filename")
def query(query_text, n, source):
    """Test the vector DB with a natural language query."""
    _, _, store = get_pipeline()

    console.print(f"\n[bold]Query:[/bold] {query_text}\n")
    results = store.query(query_text, n_results=n, filter_source=source)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    for i, r in enumerate(results, 1):
        console.print(Panel(
            f"[bold]Score:[/bold] {r['score']:.4f}  |  "
            f"[bold]Source:[/bold] {r['source_file']}  |  "
            f"[bold]Page:[/bold] {r['page_number']}\n\n"
            f"{r['text'][:400]}{'...' if len(r['text']) > 400 else ''}",
            title=f"Result {i}: {r['document_title']}",
            border_style="green" if r['score'] > 0.7 else "yellow",
        ))


@cli.command()
def stats():
    """Show ChromaDB collection statistics."""
    _, _, store = get_pipeline()
    s = store.stats()

    table = Table(title="VetGPT Vector Store Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total chunks", f"{s['total_chunks']:,}")
    table.add_row("Collection name", s['collection_name'])
    console.print(table)


@cli.command("list-sources")
def list_sources():
    """List all indexed source documents."""
    _, _, store = get_pipeline()
    sources = store.list_sources()

    if not sources:
        console.print("[yellow]No sources indexed yet.[/yellow]")
        return

    table = Table(title=f"Indexed Sources ({len(sources)} files)")
    table.add_column("#", style="dim")
    table.add_column("Filename", style="cyan")
    for i, s in enumerate(sources, 1):
        table.add_row(str(i), s)
    console.print(table)


@cli.command()
@click.argument("source_file")
def delete(source_file):
    """Remove all chunks from a specific source file."""
    _, _, store = get_pipeline()
    n = store.delete_source(source_file)
    console.print(f"[green]Deleted {n} chunks from {source_file}[/green]")


if __name__ == "__main__":
    cli()
