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
_ALLOWED_DOC_EXT = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".rtf")
_BLOCKED_EXT = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".zip", ".mp4", ".mp3", ".webp",
)

# Embedded-document carriers (besides <a href>): these often hold the real PDF/viewer URL.
_EMBED_SOURCES = (("iframe", "src"), ("embed", "src"), ("object", "data"))

# Two-label public suffixes we must keep an extra label for when computing the registrable
# domain (e.g. rbi.org.in from rbidocs.rbi.org.in). Covers the regions this system crawls.
_MULTI_PART_SUFFIXES = frozenset((
    "org.in", "gov.in", "nic.in", "co.in", "ac.in", "net.in", "res.in", "gen.in", "ind.in",
    "co.uk", "gov.uk", "org.uk", "ac.uk", "me.uk", "ltd.uk", "plc.uk",
    "com.au", "gov.au", "org.au", "net.au", "edu.au",
    "com.sg", "gov.sg", "org.sg", "edu.sg", "com.my", "gov.my", "org.my",
    "co.za", "org.za", "gov.za", "co.jp", "go.jp", "or.jp", "ne.jp",
    "com.br", "gov.br", "org.br", "com.cn", "gov.cn", "org.cn", "edu.cn",
    "com.hk", "gov.hk", "org.hk", "com.ph", "gov.ph", "com.ng", "gov.ng",
))

# Anchor text/aria that marks a "next page" / "load more" pagination control.
_NEXT_TEXT_TOKENS = (
    "next", "older", "load more", "show more", "view more", "more results",
    "›", "»", "→", ">>", "next page",
)


@dataclass
class LinkCandidate:
    url: str
    title: str


def registrable_domain(host: str) -> str:
    """Best-effort eTLD+1 (registrable domain) without external deps.

    ``rbidocs.rbi.org.in`` and ``www.rbi.org.in`` both reduce to ``rbi.org.in`` so a
    document hosted on a sibling subdomain still counts as same-site. Falls back to the
    last two labels for unknown suffixes.
    """
    host = (host or "").lower().strip().rstrip(".")
    if not host or host.replace(".", "").isdigit():  # empty or bare IP
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _MULTI_PART_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _same_site(host_a: str, host_b: str) -> bool:
    rd_a, rd_b = registrable_domain(host_a), registrable_domain(host_b)
    return bool(rd_a) and rd_a == rd_b


def _accept_url(absolute: str, base_host: str) -> str | None:
    """Classify a discovered URL: 'doc', 'page', or None (skip).

    Honors the cross-domain policy — HTML pages must share the base's registrable domain,
    while document links (PDF/Word/Excel) may live on a separate host/CDN.
    """
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    if any(host in parsed.netloc for host in _NOISE_HOSTS):
        return None
    path_lower = parsed.path.lower()
    if path_lower.endswith(_BLOCKED_EXT):
        return None
    same_site = parsed.netloc == base_host or (
        settings.CRAWL_ALLOW_CROSS_DOMAIN and _same_site(parsed.netloc, base_host)
    )
    if path_lower.endswith(_ALLOWED_DOC_EXT):
        # Documents may be hosted off-domain; allow when cross-domain is enabled.
        return "doc" if (same_site or settings.CRAWL_ALLOW_CROSS_DOMAIN) else None
    if not same_site:
        return None
    if any(token in path_lower for token in _NOISE_PATH_TOKENS):
        return None
    return "page"


def slug_title(url: str) -> str:
    """A human-ish title derived from a URL's last path segment (for link-less candidates)."""
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    return slug.replace("-", " ").replace("_", " ").strip() or url


def extract_links(base_url: str, raw_html: str) -> list[LinkCandidate]:
    """De-noised, deduped content + document links (+ their best-available title).

    Follows same-registrable-domain HTML pages and (cross-domain) document links, and also
    mines ``<iframe>/<embed>/<object>`` carriers so embedded PDFs/viewers are not missed.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    base_host = urlparse(base_url).netloc
    base_norm = base_url.rstrip("/")
    seen: set[str] = set()
    candidates: list[LinkCandidate] = []

    def _add(href: str, title_hint: str) -> bool:
        """Append a candidate; return False once the per-page cap is hit."""
        if len(candidates) >= settings.CRAWL_MAX_LINK_CANDIDATES:
            return False
        href = (href or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            return True
        absolute = urldefrag(urljoin(base_url, href))[0]
        if _accept_url(absolute, base_host) is None:
            return True
        if absolute.rstrip("/") == base_norm or absolute in seen:
            return True
        seen.add(absolute)
        title = (title_hint or "").strip() or slug_title(absolute)
        candidates.append(LinkCandidate(url=absolute, title=title[:300]))
        return True

    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(strip=True) or (anchor.get("title") or "")
        if not _add(anchor["href"], title):
            return candidates
    for tag_name, attr in _EMBED_SOURCES:
        for element in soup.find_all(tag_name):
            if not _add(element.get(attr) or "", element.get("title") or ""):
                return candidates
    return candidates


def discover_pagination(base_url: str, raw_html: str) -> list[str]:
    """Same-host 'next page' URLs for a listing (``rel=next`` + next/load-more anchors).

    Returns GET-followable URLs only; ``__doPostBack`` pagers (no real href) are left to the
    interactive Playwright path. Capped by ``CRAWL_MAX_PAGINATION``.
    """
    soup = BeautifulSoup(raw_html, "html.parser")
    base_host = urlparse(base_url).netloc
    base_norm = urldefrag(base_url)[0].rstrip("/")
    seen: set[str] = set()
    out: list[str] = []

    def _add(href: str) -> None:
        href = (href or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            return
        absolute = urldefrag(urljoin(base_url, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or parsed.netloc != base_host:
            return
        if absolute.rstrip("/") == base_norm or absolute in seen:
            return
        seen.add(absolute)
        out.append(absolute)

    for link in soup.find_all(["a", "link"], href=True):
        if "next" in " ".join(link.get("rel") or []).lower():
            _add(link["href"])
    for anchor in soup.find_all("a", href=True):
        label = (anchor.get_text(strip=True) or anchor.get("aria-label") or anchor.get("title") or "").lower()
        if label and len(label) <= 20 and any(token in label for token in _NEXT_TEXT_TOKENS):
            _add(anchor["href"])
    return out[: settings.CRAWL_MAX_PAGINATION]


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
        if _accept_url(url, base_host) is None:
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

    if source_type == SourceType.PDF.value or fetched.content_type in ("pdf", "docx", "doc", "xlsx"):
        return []
    if source_type == SourceType.RSS_FEED.value or _looks_like_feed(fetched):
        return parse_feed(fetched.raw_html or fetched.text)
    if fetched.content_type == "html" and fetched.raw_html:
        return extract_links(fetched.url, fetched.raw_html)
    return []
