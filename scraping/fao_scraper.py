"""
vetgpt/scraping/fao_scraper.py

Downloads open-access veterinary and animal health documents from FAO
(Food and Agriculture Organization of the United Nations).

All FAO content is open access under FAO's open data license.
Source: https://www.fao.org/animal-health/en/

Strategy:
- Target FAO's animal health and veterinary publications API
- Download PDFs where available (feeds into existing PDF pipeline)
- Also scrape HTML pages for quick-access content
"""

import time
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import track

console = Console()

FAO_BASE = "https://www.fao.org"

# FAO animal health topic pages — all open access
FAO_SEED_URLS = [
    "https://www.fao.org/animal-health/en/",
    "https://www.fao.org/ag/againfo/themes/en/animal_diseases.html",
    "https://www.fao.org/publications/en/#archive",
]

# FAO AGRIS API — agricultural and animal health publications database
AGRIS_API = "https://agris.fao.org/agris-search/searchIndex.do"

# Direct FAO publication search for animal health
FAO_PUBLICATIONS_API = "https://www.fao.org/publications/api/v1/products"

# Known FAO animal health PDF collections (stable URLs)
FAO_MANUAL_URLS = [
    {
        "url": "https://www.fao.org/3/i3441e/i3441e.pdf",
        "title": "FAO Animal Health Manual - Good Practices for Biosecurity",
        "category": "biosecurity",
    },
    {
        "url": "https://www.fao.org/3/a0236e/a0236e.pdf",
        "title": "FAO Manual on Livestock Disease Surveillance",
        "category": "disease_surveillance",
    },
    {
        "url": "https://www.fao.org/3/y4982e/y4982e.pdf",
        "title": "FAO Guidelines for Animal Disease Control",
        "category": "disease_control",
    },
    {
        "url": "https://www.fao.org/3/i3871e/i3871e.pdf",
        "title": "FAO Recognizing African Swine Fever",
        "category": "swine_diseases",
    },
    {
        "url": "https://www.fao.org/3/ca2906en/ca2906en.pdf",
        "title": "FAO Antimicrobial Resistance in Food and Agriculture",
        "category": "antimicrobial_resistance",
    },
    {
        "url": "https://www.fao.org/3/i9692en/I9692EN.pdf",
        "title": "FAO Assessment of Foot-and-Mouth Disease",
        "category": "livestock_diseases",
    },
    {
        "url": "https://www.fao.org/3/cb2992en/cb2992en.pdf",
        "title": "FAO One Health Framework for Animal Health",
        "category": "one_health",
    },
]


@dataclass
class FAODocument:
    """A single FAO document (PDF download or HTML page)."""
    url: str
    title: str
    text: str
    category: str
    doc_type: str           # "pdf" or "html"
    source: str = "fao"
    license: str = "FAO Open Access"
    attribution: str = "Food and Agriculture Organization of the United Nations (FAO)"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_metadata(self) -> dict:
        slug = re.sub(r'[^a-z0-9]+', '_', self.title.lower())[:60]
        return {
            "source": self.source,
            "source_file": f"fao_{slug}",
            "document_title": self.title,
            "url": self.url,
            "license": self.license,
            "attribution": self.attribution,
            "category": self.category,
            "doc_type": self.doc_type,
            "word_count": self.word_count,
            "scraped_at": self.scraped_at,
            "page_number": 1,
            "chunk_index": 0,
            "has_tables": False,
            "has_images": False,
        }


class FAOScraper:
    """
    Downloads and extracts FAO animal health documents.

    Two modes:
    1. PDF download → saved to data/pdfs/fao/ → processed by existing VetPDFParser
    2. HTML scrape → extracted inline → fed directly to chunker/embedder
    """

    RATE_LIMIT = 2.0        # polite: 1 req per 2s for FAO servers
    MIN_WORDS = 100

    def __init__(
        self,
        output_dir: str = "./data/scraped/fao",
        pdf_dir: str = "./data/pdfs/fao",
    ):
        self.output_dir = Path(output_dir)
        self.pdf_dir = Path(pdf_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "VetGPT/1.0 (veterinary AI research; contact@vetgpt.app)",
            "Accept": "text/html,application/pdf,*/*",
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_all(self) -> list[FAODocument]:
        """
        Download all known FAO animal health PDFs and HTML pages.

        Returns:
            List of FAODocuments with extracted text.
            PDFs are also saved to pdf_dir for the existing PDF pipeline.
        """
        console.print("\n[bold cyan]FAO Scraper[/bold cyan]")

        documents = []

        # Download known PDFs
        console.print(f"\n[bold]Downloading {len(FAO_MANUAL_URLS)} FAO PDFs...[/bold]")
        for item in track(FAO_MANUAL_URLS, description="FAO PDFs"):
            doc = self._download_pdf(item["url"], item["title"], item["category"])
            if doc:
                documents.append(doc)
            time.sleep(self.RATE_LIMIT)

        # Scrape HTML animal health pages
        console.print(f"\n[bold]Scraping FAO animal health pages...[/bold]")
        html_docs = self._scrape_html_pages()
        documents.extend(html_docs)

        # Filter short docs
        documents = [d for d in documents if d.word_count >= self.MIN_WORDS]

        self._save(documents)
        console.print(
            f"\n[bold green]✓ FAO:[/bold green] "
            f"{len(documents)} documents processed "
            f"({sum(1 for d in documents if d.doc_type == 'pdf')} PDFs, "
            f"{sum(1 for d in documents if d.doc_type == 'html')} HTML pages)"
        )
        return documents

    def load_cached(self) -> list[FAODocument]:
        """Load previously scraped FAO documents from cache."""
        cache_file = self.output_dir / "documents.jsonl"
        if not cache_file.exists():
            return []
        docs = []
        with open(cache_file) as f:
            for line in f:
                data = json.loads(line)
                docs.append(FAODocument(**data))
        console.print(f"[cyan]Loaded {len(docs)} cached FAO documents[/cyan]")
        return docs

    # ------------------------------------------------------------------
    # Private: PDF download
    # ------------------------------------------------------------------

    def _download_pdf(
        self, url: str, title: str, category: str
    ) -> FAODocument | None:
        """
        Download a FAO PDF, save it to disk, and extract its text.
        The saved PDF can also be processed by VetPDFParser for richer extraction.
        """
        filename = url.split("/")[-1]
        pdf_path = self.pdf_dir / filename

        # Download if not cached
        if not pdf_path.exists():
            try:
                resp = self._session.get(url, timeout=60, stream=True)
                resp.raise_for_status()

                with open(pdf_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

            except Exception as e:
                console.print(f"[red]PDF download failed ({filename}): {e}[/red]")
                return None

        # Extract text using PyMuPDF
        try:
            import fitz
            doc = fitz.open(str(pdf_path))
            pages_text = []
            for page in doc:
                text = page.get_text("text").strip()
                if text:
                    pages_text.append(text)
            doc.close()
            full_text = "\n\n".join(pages_text)

            if not full_text.strip():
                return None

            return FAODocument(
                url=url,
                title=title,
                text=full_text,
                category=category,
                doc_type="pdf",
            )
        except Exception as e:
            console.print(f"[yellow]Text extraction failed ({filename}): {e}[/yellow]")
            # Return minimal doc — PDF is still saved for VetPDFParser
            return FAODocument(
                url=url,
                title=title,
                text=f"[PDF saved at {pdf_path} — process with VetPDFParser]",
                category=category,
                doc_type="pdf",
            )

    # ------------------------------------------------------------------
    # Private: HTML scraping
    # ------------------------------------------------------------------

    def _scrape_html_pages(self) -> list[FAODocument]:
        """Scrape FAO animal health HTML pages."""
        documents = []

        for seed_url in FAO_SEED_URLS:
            try:
                resp = self._session.get(seed_url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                text = self._extract_html_text(soup)
                title = soup.find("title")
                title_text = title.get_text().strip() if title else seed_url

                if len(text.split()) >= self.MIN_WORDS:
                    documents.append(FAODocument(
                        url=seed_url,
                        title=title_text,
                        text=text,
                        category="animal_health",
                        doc_type="html",
                    ))

                time.sleep(self.RATE_LIMIT)

            except Exception as e:
                console.print(f"[red]HTML scrape failed ({seed_url}): {e}[/red]")

        return documents

    def _extract_html_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text from FAO HTML page."""
        # Remove nav, footer, scripts, styles
        for tag in soup(["nav", "footer", "script", "style", "header", "aside"]):
            tag.decompose()

        # Get main content area
        main = (
            soup.find("main")
            or soup.find("div", class_=re.compile(r"content|article|main", re.I))
            or soup.find("body")
        )

        if not main:
            return ""

        # Extract paragraphs and headings
        lines = []
        for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            text = el.get_text(" ", strip=True)
            if text and len(text) > 20:
                lines.append(text)

        return "\n\n".join(lines)

    def _save(self, documents: list[FAODocument]):
        """Save to JSONL cache."""
        cache_file = self.output_dir / "documents.jsonl"
        with open(cache_file, "w") as f:
            for doc in documents:
                f.write(json.dumps(doc.__dict__) + "\n")
        console.print(f"[dim]Cached to {cache_file}[/dim]")
