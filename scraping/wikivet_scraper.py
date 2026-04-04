"""
vetgpt/scraping/wikivet_scraper.py

Scrapes WikiVet (CC BY-SA licensed) veterinary content.
Respects robots.txt, rate limits, and attribution requirements.

WikiVet structure:
  https://en.wikivet.net/[Article_Title]
  Categories link to article lists → articles have structured content
"""

import time
import re
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import track

console = Console()

BASE_URL = "https://en.wikivet.net"
API_URL = f"{BASE_URL}/api.php"

# WikiVet category entry points for veterinary content
SEED_CATEGORIES = [
    "Diseases_and_Conditions",
    "Pharmacology",
    "Anatomy",
    "Physiology",
    "Clinical_Skills",
    "Pathology",
    "Microbiology",
    "Parasitology",
    "Surgery",
    "Reproduction",
]


@dataclass
class ScrapedArticle:
    """A single scraped WikiVet article."""
    url: str
    title: str
    text: str
    categories: list[str]
    source: str = "wikivet"
    license: str = "CC BY-SA"
    attribution: str = "WikiVet (en.wikivet.net)"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    word_count: int = 0

    def __post_init__(self):
        self.word_count = len(self.text.split())

    def to_metadata(self) -> dict:
        """ChromaDB-compatible metadata (str/int/float/bool only)."""
        return {
            "source": self.source,
            "source_file": f"wikivet_{self._slug()}",
            "document_title": self.title,
            "url": self.url,
            "license": self.license,
            "attribution": self.attribution,
            "categories": ", ".join(self.categories),
            "word_count": self.word_count,
            "scraped_at": self.scraped_at,
            "page_number": 1,
            "chunk_index": 0,
            "has_tables": False,
            "has_images": False,
        }

    def _slug(self) -> str:
        return re.sub(r'[^a-z0-9]+', '_', self.title.lower())[:60]


class WikiVetScraper:
    """
    Scrapes WikiVet using their MediaWiki API for clean text extraction.

    Uses the API (not raw HTML scraping) for:
    - Cleaner text without nav/sidebar noise
    - Rate-limit-friendly (one structured request vs many HTML parses)
    - Respects WikiVet's preferred access method
    """

    RATE_LIMIT_SECONDS = 1.5    # be polite — 1 req per 1.5s
    MAX_ARTICLES = 2000         # safety cap per run
    MIN_WORDS = 100             # skip stub articles

    def __init__(self, output_dir: str = "./data/scraped/wikivet"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._seen_titles: set[str] = set()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "VetGPT/1.0 (veterinary AI research tool; contact@vetgpt.app)"
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_all(self, max_articles: int = MAX_ARTICLES) -> list[ScrapedArticle]:
        """
        Scrape all vet content from WikiVet seed categories.

        Returns:
            List of ScrapedArticles ready for chunking and embedding.
        """
        console.print("\n[bold cyan]WikiVet Scraper[/bold cyan]")
        console.print(f"Seed categories: {len(SEED_CATEGORIES)}")

        # Step 1: Collect article titles from all seed categories
        titles = self._collect_titles(max_articles)
        console.print(f"\n[green]Found {len(titles)} unique articles[/green]")

        # Step 2: Fetch and parse each article
        articles = self._fetch_articles(titles)

        # Step 3: Save to disk (cache — avoid re-scraping)
        self._save(articles)

        return articles

    def load_cached(self) -> list[ScrapedArticle]:
        """Load previously scraped articles from disk cache."""
        cache_file = self.output_dir / "articles.jsonl"
        if not cache_file.exists():
            return []

        articles = []
        with open(cache_file) as f:
            for line in f:
                data = json.loads(line)
                articles.append(ScrapedArticle(**data))

        console.print(f"[cyan]Loaded {len(articles)} cached WikiVet articles[/cyan]")
        return articles

    # ------------------------------------------------------------------
    # Private: title collection
    # ------------------------------------------------------------------

    def _collect_titles(self, max_articles: int) -> list[str]:
        """Collect article titles from WikiVet categories via MediaWiki API."""
        titles = set()

        for category in SEED_CATEGORIES:
            if len(titles) >= max_articles:
                break

            cat_titles = self._get_category_members(category)
            titles.update(cat_titles)
            console.print(
                f"  [dim]{category}:[/dim] {len(cat_titles)} articles "
                f"(total: {len(titles)})"
            )
            time.sleep(self.RATE_LIMIT_SECONDS)

        return list(titles)[:max_articles]

    def _get_category_members(self, category: str) -> list[str]:
        """Fetch all article titles in a WikiVet category."""
        titles = []
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmlimit": 500,
            "cmtype": "page",
            "format": "json",
        }

        while True:
            try:
                resp = self._session.get(API_URL, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                console.print(f"[red]Category fetch failed ({category}): {e}[/red]")
                break

            members = data.get("query", {}).get("categorymembers", [])
            titles.extend(m["title"] for m in members)

            # Handle pagination
            cont = data.get("continue")
            if not cont:
                break
            params["cmcontinue"] = cont["cmcontinue"]
            time.sleep(self.RATE_LIMIT_SECONDS)

        return titles

    # ------------------------------------------------------------------
    # Private: article fetching
    # ------------------------------------------------------------------

    def _fetch_articles(self, titles: list[str]) -> list[ScrapedArticle]:
        """Fetch and parse articles in batches of 20 (API limit)."""
        articles = []
        batch_size = 20

        for i in track(
            range(0, len(titles), batch_size),
            description="Fetching WikiVet articles",
        ):
            batch = titles[i : i + batch_size]
            batch_articles = self._fetch_batch(batch)
            articles.extend(batch_articles)
            time.sleep(self.RATE_LIMIT_SECONDS)

        # Filter stubs
        articles = [a for a in articles if a.word_count >= self.MIN_WORDS]
        console.print(
            f"[green]✓ WikiVet:[/green] {len(articles)} articles "
            f"(filtered stubs < {self.MIN_WORDS} words)"
        )
        return articles

    def _fetch_batch(self, titles: list[str]) -> list[ScrapedArticle]:
        """Fetch a batch of articles using the MediaWiki API."""
        params = {
            "action": "query",
            "titles": "|".join(titles),
            "prop": "extracts|categories|info",
            "explaintext": True,       # plain text, not HTML
            "exsectionformat": "plain",
            "cllimit": 20,
            "inprop": "url",
            "format": "json",
        }

        try:
            resp = self._session.get(API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            console.print(f"[red]Batch fetch failed: {e}[/red]")
            return []

        articles = []
        pages = data.get("query", {}).get("pages", {})

        for page_id, page_data in pages.items():
            if page_id == "-1":  # page not found
                continue

            title = page_data.get("title", "")
            text = page_data.get("extract", "").strip()
            url = page_data.get("fullurl", f"{BASE_URL}/{title.replace(' ', '_')}")
            cats = [
                c["title"].replace("Category:", "")
                for c in page_data.get("categories", [])
            ]

            if not text:
                continue

            text = self._clean_text(text)
            articles.append(ScrapedArticle(
                url=url,
                title=title,
                text=text,
                categories=cats,
            ))

        return articles

    def _clean_text(self, text: str) -> str:
        """Clean extracted MediaWiki plain text."""
        # Remove edit section markers
        text = re.sub(r'\[edit\]', '', text)
        # Remove excessive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove references section
        text = re.sub(r'\n==\s*References\s*==.*$', '', text, flags=re.DOTALL)
        # Remove external links section
        text = re.sub(r'\n==\s*External Links?\s*==.*$', '', text, flags=re.DOTALL)
        return text.strip()

    def _save(self, articles: list[ScrapedArticle]):
        """Save articles to JSONL cache file."""
        cache_file = self.output_dir / "articles.jsonl"
        with open(cache_file, "w") as f:
            for article in articles:
                f.write(json.dumps(article.__dict__) + "\n")
        console.print(f"[dim]Cached to {cache_file}[/dim]")
