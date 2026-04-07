"""
vetgpt/scraping/eclinpath_scraper.py

Scrapes eClinPath — Cornell University's free online veterinary
clinical pathology textbook (https://eclinpath.com).

License: Free educational resource, Cornell CVM.
         No explicit scraping restriction. We scrape respectfully
         with rate limiting and proper User-Agent attribution.

Coverage:
  - Hematology (RBC, WBC, platelets)
  - Clinical chemistry (liver, kidney, electrolytes, etc.)
  - Urinalysis
  - Cytology
  - Coagulation
  - Blood gases
  - Special topics (bone marrow, effusions, CSF)
"""

import time
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import track

console = Console()

BASE_URL   = "https://eclinpath.com"
START_URL  = "https://eclinpath.com"

# eClinPath top-level sections — all contain clinical pathology content
SECTION_URLS = [
    "https://eclinpath.com/hematology/",
    "https://eclinpath.com/chemistry/",
    "https://eclinpath.com/urinalysis/",
    "https://eclinpath.com/cytology/",
    "https://eclinpath.com/coagulation/",
    "https://eclinpath.com/blood-gases/",
    "https://eclinpath.com/bone-marrow/",
    "https://eclinpath.com/effusions/",
    "https://eclinpath.com/csf/",
    "https://eclinpath.com/synovial-fluid/",
    "https://eclinpath.com/miscellaneous/",
]


@dataclass
class EClinPathArticle:
    """A single eClinPath page."""
    url: str
    title: str
    section: str        # e.g. "hematology", "chemistry"
    text: str
    source: str = "eclinpath"
    license: str = "Free Educational Resource — Cornell University CVM"
    attribution: str = "eClinPath — Cornell University College of Veterinary Medicine"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_metadata(self) -> dict:
        slug = re.sub(r'[^a-z0-9]+', '_', self.title.lower())[:60]
        return {
            "source": self.source,
            "source_file": f"eclinpath_{slug}",
            "document_title": self.title,
            "url": self.url,
            "section": self.section,
            "license": self.license,
            "attribution": self.attribution,
            "word_count": self.word_count,
            "scraped_at": self.scraped_at,
            "page_number": 1,
            "chunk_index": 0,
            "has_tables": False,
            "has_images": False,
        }


class EClinPathScraper:
    """
    Crawls eClinPath section by section, extracts article text.

    Strategy:
    - Start from each section URL
    - Collect all internal article links
    - Fetch each article, extract main content
    - Strip nav, sidebar, ads, footer
    - Cache to JSONL for re-use
    """

    RATE_LIMIT  = 2.0       # seconds between requests — be polite to Cornell servers
    MIN_WORDS   = 80        # skip stub/redirect pages
    MAX_PAGES   = 500       # safety cap

    def __init__(self, output_dir: str = "./data/scraped/eclinpath"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "VetGPT/1.0 (veterinary AI reference tool; educational use; "
                "contact@vetgpt.app)"
            ),
            "Accept": "text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._visited: set[str] = set()

    # ── Public API ────────────────────────────────────────────────────────────

    def scrape_all(self) -> list[EClinPathArticle]:
        """
        Scrape all eClinPath sections.

        Returns:
            List of EClinPathArticles ready for chunking + embedding.
        """
        console.print("\n[bold cyan]eClinPath Scraper[/bold cyan]")
        console.print(f"Sections: {len(SECTION_URLS)}")

        all_urls   = self._collect_urls()
        articles   = self._fetch_articles(all_urls)
        articles   = [a for a in articles if a.word_count >= self.MIN_WORDS]

        self._save(articles)

        console.print(
            f"\n[bold green]✓ eClinPath:[/bold green] "
            f"{len(articles)} articles scraped"
        )
        return articles

    def load_cached(self) -> list[EClinPathArticle]:
        """Load from disk cache — no network calls."""
        cache_file = self.output_dir / "articles.jsonl"
        if not cache_file.exists():
            return []
        articles = []
        with open(cache_file) as f:
            for line in f:
                d = json.loads(line)
                articles.append(EClinPathArticle(**d))
        console.print(f"[cyan]Loaded {len(articles)} cached eClinPath articles[/cyan]")
        return articles

    # ── URL collection ────────────────────────────────────────────────────────

    def _collect_urls(self) -> list[tuple[str, str]]:
        """
        Crawl each section page and collect article links.

        Returns:
            List of (url, section_name) tuples.
        """
        url_pairs: list[tuple[str, str]] = []

        for section_url in SECTION_URLS:
            section_name = urlparse(section_url).path.strip("/").split("/")[0]
            console.print(f"\n[dim]Collecting:[/dim] {section_name}")

            try:
                resp = self._session.get(section_url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                console.print(f"[red]Section fetch failed ({section_name}): {e}[/red]")
                time.sleep(self.RATE_LIMIT)
                continue

            # Add section page itself
            if section_url not in self._visited:
                url_pairs.append((section_url, section_name))
                self._visited.add(section_url)

            # Find all internal article links in the section
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(BASE_URL, href)

                # Only eClinPath URLs, skip anchors / external
                if not full_url.startswith(BASE_URL):
                    continue
                if "#" in full_url:
                    full_url = full_url.split("#")[0]
                if full_url in self._visited:
                    continue
                if full_url == BASE_URL or full_url == BASE_URL + "/":
                    continue

                # Only keep article-like paths (not wp-admin, feed, etc.)
                path = urlparse(full_url).path
                if any(skip in path for skip in [
                    "wp-admin", "wp-content", "feed", "tag/",
                    "category/", "author/", "page/", "login",
                ]):
                    continue

                self._visited.add(full_url)
                url_pairs.append((full_url, section_name))

            console.print(
                f"  [green]+{len([u for u in url_pairs if u[1] == section_name])}[/green] "
                f"URLs in {section_name}"
            )
            time.sleep(self.RATE_LIMIT)

        # Cap to MAX_PAGES
        url_pairs = url_pairs[:self.MAX_PAGES]
        console.print(f"\n[green]Total URLs to fetch: {len(url_pairs)}[/green]")
        return url_pairs

    # ── Article fetching ──────────────────────────────────────────────────────

    def _fetch_articles(
        self, url_pairs: list[tuple[str, str]]
    ) -> list[EClinPathArticle]:
        """Fetch and parse each article URL."""
        articles = []

        for url, section in track(url_pairs, description="Fetching eClinPath pages"):
            article = self._fetch_article(url, section)
            if article:
                articles.append(article)
            time.sleep(self.RATE_LIMIT)

        return articles

    def _fetch_article(self, url: str, section: str) -> EClinPathArticle | None:
        """Fetch a single article page and extract its content."""
        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            console.print(f"[red]Fetch failed ({url}): {e}[/red]")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._extract_title(soup, url)
        text  = self._extract_text(soup)

        if not text.strip():
            return None

        return EClinPathArticle(
            url=url,
            title=title,
            section=section,
            text=text,
        )

    # ── Text extraction ───────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        """Extract page title."""
        # Try H1 first (most reliable on eClinPath)
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(" ", strip=True)

        # Fall back to <title> tag
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(" ", strip=True)
            # Strip " | eClinPath" suffix
            title = re.sub(r'\s*[|\-–]\s*eClinPath.*$', '', title)
            return title.strip()

        # Last resort: derive from URL
        path = urlparse(url).path.strip("/")
        return path.replace("-", " ").replace("/", " — ").title()

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """
        Extract main article text from eClinPath.

        eClinPath uses WordPress. Main content is typically in:
          - <article> tag
          - .entry-content
          - .post-content
          - main#main
        """
        # Remove noise elements first
        for tag in soup.find_all([
            "nav", "header", "footer", "aside",
            "script", "style", "noscript",
            ".wp-block-table",   # keep table text but strip complex markup
        ]):
            tag.decompose()

        # Also remove sidebars and navigation widgets
        for cls in ["sidebar", "widget", "menu", "breadcrumb",
                    "post-navigation", "site-footer", "comments"]:
            for el in soup.find_all(class_=re.compile(cls, re.I)):
                el.decompose()

        # Find main content container
        content = (
            soup.find("article")
            or soup.find(class_=re.compile(r"entry.content|post.content", re.I))
            or soup.find("main")
            or soup.find("div", id=re.compile(r"main|content", re.I))
            or soup.find("body")
        )

        if not content:
            return ""

        # Extract text from meaningful elements
        parts = []
        for el in content.find_all([
            "h1", "h2", "h3", "h4", "h5",
            "p", "li", "td", "th",
            "figcaption",
        ]):
            text = el.get_text(" ", strip=True)
            if text and len(text) > 15:
                # Add heading markers for context
                if el.name in ("h1", "h2", "h3", "h4"):
                    parts.append(f"\n## {text}")
                else:
                    parts.append(text)

        raw = "\n".join(parts)
        return self._clean_text(raw)

    def _clean_text(self, text: str) -> str:
        """Final text cleanup."""
        # Fix hyphenated breaks
        text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)
        # Collapse excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        # Remove "Share this:" / social media noise
        text = re.sub(r'Share this:.*', '', text, flags=re.DOTALL)
        return text.strip()

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _save(self, articles: list[EClinPathArticle]) -> None:
        """Save scraped articles to JSONL cache."""
        cache_file = self.output_dir / "articles.jsonl"
        with open(cache_file, "w") as f:
            for a in articles:
                f.write(json.dumps(a.__dict__) + "\n")
        console.print(f"[dim]Cached to {cache_file}[/dim]")
