"""Crawl-frontier helpers: discover candidate links / feed entries from a fetched page.

Pure functions — no network, no DB, no LLM. The orchestrator (ingestion_service) decides
which candidates to actually fetch (after the title-relevance gate).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.config import settings
from app.models.source import Source, SourceType
from app.services.url_fetcher import FetchedContent

logger = logging.getLogger(__name__)

_NOISE_PATH_TOKENS = (
    "/login", "/user", "/search", "/about", "/contact", "/cookie", "/privacy", "/careers",
    "/subscribe", "/newsletter", "/accessibility", "/terms", "/legal", "/disclaimer",
    "/feedback", "/help", "/sitemap",
)
_NOISE_HOSTS = ("twitter.com", "x.com", "facebook.com", "linkedin.com", "youtube.com", "instagram.com", "t.me")
_ALLOWED_DOC_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".xls")
_BLOCKED_EXT = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".zip", ".mp4", ".mp3", ".webp",
)


@dataclass
class LinkCandidate:
    url: str
    title: str


def slug_title(url: str) -> str:
    """A human-ish title derived from a URL's last path segment (for link-less candidates)."""
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    return slug.replace("-", " ").replace("_", " ").strip() or url


def extract_links(base_url: str, raw_html: str) -> list[LinkCandidate]:
    """Same-domain, de-noised, deduped content links (+ their best-available title)."""
    soup = BeautifulSoup(raw_html, "html.parser")
    base_host = urlparse(base_url).netloc
    base_norm = base_url.rstrip("/")
    seen: set[str] = set()
    candidates: list[LinkCandidate] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urldefrag(urljoin(base_url, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_host:
            continue  # same-domain only
        if any(host in parsed.netloc for host in _NOISE_HOSTS):
            continue
        lower = absolute.lower()
        if lower.endswith(_BLOCKED_EXT):
            continue
        is_doc = lower.endswith(_ALLOWED_DOC_EXT)
        if not is_doc and any(token in parsed.path.lower() for token in _NOISE_PATH_TOKENS):
            continue
        if absolute.rstrip("/") == base_norm or absolute in seen:
            continue  # don't follow self / duplicates
        seen.add(absolute)
        title = anchor.get_text(strip=True) or (anchor.get("title") or "").strip() or slug_title(absolute)
        candidates.append(LinkCandidate(url=absolute, title=title[:300]))
        if len(candidates) >= settings.CRAWL_MAX_LINK_CANDIDATES:
            break
    return candidates


def discover_feed(base_url: str, raw_html: str) -> str | None:
    """Return an RSS/Atom feed URL declared by the page (<link rel=alternate ...>), if any."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel") or []).lower()
        type_attr = (link.get("type") or "").lower()
        if "alternate" in rel and ("rss" in type_attr or "atom" in type_attr):
            return urljoin(base_url, link["href"])
    return None


def parse_feed(feed_text: str) -> list[LinkCandidate]:
    """Parse RSS/Atom feed text into (link, title) candidates."""
    try:
        import feedparser
    except ImportError:
        logger.info("feedparser not installed; cannot parse feeds.")
        return []
    parsed = feedparser.parse(feed_text)
    candidates: list[LinkCandidate] = []
    for entry in parsed.entries[: settings.CRAWL_MAX_LINK_CANDIDATES]:
        link = entry.get("link")
        if link:
            candidates.append(LinkCandidate(url=link, title=str(entry.get("title") or link)[:300]))
    return candidates


def sitemaps_from_robots(robots_text: str) -> list[str]:
    """Extract `Sitemap:` URLs declared in a robots.txt."""
    urls: list[str] = []
    for line in (robots_text or "").splitlines():
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if url:
                urls.append(url)
    return urls


def parse_sitemap(xml_text: str) -> tuple[bool, list[str]]:
    """Parse a sitemap (or sitemap-index) into ``(is_index, [<loc> urls])``."""
    soup = BeautifulSoup(xml_text or "", "html.parser")
    is_index = soup.find("sitemapindex") is not None
    locs = [loc.get_text(strip=True) for loc in soup.find_all("loc") if loc.get_text(strip=True)]
    return is_index, locs


def candidates_from_locs(locs: list[str], base_url: str) -> list[LinkCandidate]:
    """Same-domain, de-noised, deduped candidates from sitemap <loc> URLs (slug titles)."""
    base_host = urlparse(base_url).netloc
    base_norm = base_url.rstrip("/")
    seen: set[str] = set()
    candidates: list[LinkCandidate] = []
    for url in locs:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_host:
            continue
        lower = url.lower()
        if lower.endswith(_BLOCKED_EXT):
            continue
        if url.rstrip("/") == base_norm or url in seen:
            continue
        seen.add(url)
        candidates.append(LinkCandidate(url=url, title=slug_title(url)))
        if len(candidates) >= settings.CRAWL_MAX_LINK_CANDIDATES:
            break
    return candidates


def _looks_like_feed(fetched: FetchedContent) -> bool:
    sample = (fetched.raw_html or fetched.text or "").lstrip()[:300].lower()
    return sample.startswith("<?xml") and ("rss" in sample or "atom" in sample) or "<rss" in sample or "<feed" in sample


def select_candidates(source: Source, fetched: FetchedContent) -> list[LinkCandidate]:
    """Choose crawl candidates: feed entries if it's a feed, else same-domain page links.

    A configured PDF/document source (or a fetched document) yields no candidates — it is
    processed directly as a single document.
    """
    source_type = getattr(source.source_type, "value", source.source_type)

    if source_type == SourceType.PDF.value or fetched.content_type in ("pdf", "docx", "xlsx"):
        return []
    if source_type == SourceType.RSS_FEED.value or _looks_like_feed(fetched):
        return parse_feed(fetched.raw_html or fetched.text)
    if fetched.content_type == "html" and fetched.raw_html:
        return extract_links(fetched.url, fetched.raw_html)
    return []
