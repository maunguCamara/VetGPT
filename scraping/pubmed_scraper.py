"""
vetgpt/scraping/pubmed_scraper.py

Fetches veterinary research from PubMed/NCBI (public domain).
Uses the official NCBI E-utilities API — no scraping, fully legal.

Free API: 3 requests/sec without key, 10/sec with NCBI API key.
Get a free key at: https://www.ncbi.nlm.nih.gov/account/
"""

import time
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

import requests
from rich.console import Console
from rich.progress import track

console = Console()

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Focused veterinary search queries
VET_QUERIES = [
    "veterinary clinical treatment dogs cats",
    "canine feline disease diagnosis treatment",
    "bovine equine disease management",
    "veterinary pharmacology drug dosage animals",
    "veterinary surgery procedures techniques",
    "animal infectious disease pathogen",
    "livestock disease prevention control",
    "veterinary emergency critical care",
    "companion animal internal medicine",
    "exotic animal veterinary medicine",
]


@dataclass
class PubMedArticle:
    """A single PubMed article (abstract + metadata)."""
    pmid: str
    title: str
    abstract: str
    authors: list[str]
    journal: str
    pub_year: str
    doi: str
    url: str
    mesh_terms: list[str]
    source: str = "pubmed"
    license: str = "Public Domain / Open Access"
    attribution: str = "PubMed (NCBI)"
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def text(self) -> str:
        """Full text for embedding: title + abstract."""
        parts = [f"Title: {self.title}"]
        if self.abstract:
            parts.append(f"Abstract: {self.abstract}")
        if self.mesh_terms:
            parts.append(f"MeSH Terms: {', '.join(self.mesh_terms)}")
        return "\n\n".join(parts)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_metadata(self) -> dict:
        return {
            "source": self.source,
            "source_file": f"pubmed_{self.pmid}",
            "document_title": self.title,
            "url": self.url,
            "license": self.license,
            "attribution": self.attribution,
            "journal": self.journal,
            "pub_year": self.pub_year,
            "doi": self.doi,
            "authors": ", ".join(self.authors[:3]),  # first 3 authors
            "mesh_terms": ", ".join(self.mesh_terms[:10]),
            "word_count": self.word_count,
            "scraped_at": self.scraped_at,
            "page_number": 1,
            "chunk_index": 0,
            "has_tables": False,
            "has_images": False,
        }


class PubMedScraper:
    """
    Fetches veterinary abstracts from PubMed via NCBI E-utilities API.

    Strategy:
    - Search for vet-specific queries
    - Fetch abstracts (always free) + full text where open access
    - Focus on last 10 years for clinical relevance
    - Filter to abstracts with >50 words (exclude short/empty abstracts)
    """

    RATE_LIMIT = 0.34       # 3 req/sec without API key
    MAX_PER_QUERY = 200     # articles per search query
    MIN_ABSTRACT_WORDS = 50

    def __init__(
        self,
        output_dir: str = "./data/scraped/pubmed",
        ncbi_api_key: str | None = None,
        years_back: int = 10,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = ncbi_api_key
        self.years_back = years_back

        if ncbi_api_key:
            self.RATE_LIMIT = 0.1   # 10 req/sec with API key
            console.print("[green]NCBI API key loaded — using 10 req/sec[/green]")

        self._session = requests.Session()
        self._seen_pmids: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_all(self, max_per_query: int = MAX_PER_QUERY) -> list[PubMedArticle]:
        """
        Fetch vet articles for all predefined queries.

        Returns:
            Deduplicated list of PubMedArticles.
        """
        console.print("\n[bold cyan]PubMed Scraper[/bold cyan]")
        console.print(f"Queries: {len(VET_QUERIES)} | Max per query: {max_per_query}")

        all_articles = []

        for query in VET_QUERIES:
            console.print(f"\n[dim]Searching:[/dim] {query}")
            pmids = self._search(query, max_per_query)

            # Filter already seen
            new_pmids = [p for p in pmids if p not in self._seen_pmids]
            self._seen_pmids.update(new_pmids)

            if not new_pmids:
                continue

            articles = self._fetch_articles(new_pmids)
            all_articles.extend(articles)
            console.print(f"  [green]+{len(articles)} articles[/green] (total: {len(all_articles)})")

        # Filter short abstracts
        all_articles = [
            a for a in all_articles
            if a.word_count >= self.MIN_ABSTRACT_WORDS
        ]

        self._save(all_articles)
        console.print(
            f"\n[bold green]✓ PubMed:[/bold green] "
            f"{len(all_articles)} articles fetched"
        )
        return all_articles

    def load_cached(self) -> list[PubMedArticle]:
        """Load previously fetched articles from disk cache."""
        cache_file = self.output_dir / "articles.jsonl"
        if not cache_file.exists():
            return []
        articles = []
        with open(cache_file) as f:
            for line in f:
                data = json.loads(line)
                # Reconstruct dataclass
                articles.append(PubMedArticle(
                    pmid=data["pmid"],
                    title=data["title"],
                    abstract=data["abstract"],
                    authors=data["authors"],
                    journal=data["journal"],
                    pub_year=data["pub_year"],
                    doi=data["doi"],
                    url=data["url"],
                    mesh_terms=data["mesh_terms"],
                ))
        console.print(f"[cyan]Loaded {len(articles)} cached PubMed articles[/cyan]")
        return articles

    # ------------------------------------------------------------------
    # Private: search + fetch
    # ------------------------------------------------------------------

    def _search(self, query: str, max_results: int) -> list[str]:
        """Search PubMed and return list of PMIDs."""
        from datetime import datetime
        min_year = datetime.now().year - self.years_back

        params = {
            "db": "pubmed",
            "term": f"{query} AND ({min_year}:{datetime.now().year}[pdat]) AND (veterinary[MeSH])",
            "retmax": max_results,
            "retmode": "json",
            "usehistory": "n",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            resp = self._session.get(
                f"{NCBI_BASE}/esearch.fcgi",
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            time.sleep(self.RATE_LIMIT)
            return pmids
        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            return []

    def _fetch_articles(self, pmids: list[str]) -> list[PubMedArticle]:
        """Fetch full article metadata for a list of PMIDs."""
        articles = []
        batch_size = 100  # NCBI efetch handles up to 200

        for i in track(
            range(0, len(pmids), batch_size),
            description="Fetching PubMed articles",
            transient=True,
        ):
            batch = pmids[i : i + batch_size]
            batch_articles = self._fetch_batch(batch)
            articles.extend(batch_articles)
            time.sleep(self.RATE_LIMIT)

        return articles

    def _fetch_batch(self, pmids: list[str]) -> list[PubMedArticle]:
        """Fetch a batch of articles via efetch."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            resp = self._session.get(
                f"{NCBI_BASE}/efetch.fcgi",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_xml(resp.text)
        except Exception as e:
            console.print(f"[red]Fetch batch failed: {e}[/red]")
            return []

    def _parse_xml(self, xml_text: str) -> list[PubMedArticle]:
        """Parse PubMed XML response into PubMedArticles."""
        from xml.etree import ElementTree as ET

        articles = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        for article_el in root.findall(".//PubmedArticle"):
            try:
                pmid = article_el.findtext(".//PMID", "")
                title = article_el.findtext(".//ArticleTitle", "").strip()

                # Abstract — may have multiple sections
                abstract_parts = article_el.findall(".//AbstractText")
                abstract = " ".join(
                    (el.get("Label", "") + ": " if el.get("Label") else "") + (el.text or "")
                    for el in abstract_parts
                ).strip()

                # Authors
                authors = [
                    f"{a.findtext('LastName', '')} {a.findtext('ForeName', '')}".strip()
                    for a in article_el.findall(".//Author")
                    if a.findtext("LastName")
                ]

                journal = article_el.findtext(".//Journal/Title", "")
                pub_year = article_el.findtext(".//PubDate/Year", "")

                # DOI
                doi = ""
                for id_el in article_el.findall(".//ArticleId"):
                    if id_el.get("IdType") == "doi":
                        doi = id_el.text or ""
                        break

                # MeSH terms
                mesh_terms = [
                    el.findtext("DescriptorName", "")
                    for el in article_el.findall(".//MeshHeading")
                ]

                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

                if not title or not abstract:
                    continue

                articles.append(PubMedArticle(
                    pmid=pmid,
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    journal=journal,
                    pub_year=pub_year,
                    doi=doi,
                    url=url,
                    mesh_terms=[m for m in mesh_terms if m],
                ))
            except Exception:
                continue  # skip malformed entries

        return articles

    def _save(self, articles: list[PubMedArticle]):
        """Save to JSONL cache."""
        cache_file = self.output_dir / "articles.jsonl"
        with open(cache_file, "w") as f:
            for a in articles:
                f.write(json.dumps(a.__dict__) + "\n")
        console.print(f"[dim]Cached to {cache_file}[/dim]")
