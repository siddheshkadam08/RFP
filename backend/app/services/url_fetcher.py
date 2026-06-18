"""Fetch and extract text content from a URL (HTML or PDF)."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_USER_AGENT = "RFPIntelligenceBot/1.0 (opportunity-scanner)"


@dataclass
class FetchedContent:
    """Result of fetching and extracting content from a URL."""

    url: str
    title: str
    text: str
    content_type: str  # "html" or "pdf"
    content_hash: str
    content_length: int


def _extract_text_from_html(raw_html: str) -> tuple[str, str]:
    """Return (title, cleaned text) from raw HTML."""
    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    # Try common main-content selectors first
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"role": "main"})
        or soup.find("div", id="content")
        or soup.find("div", class_="content")
    )
    container = main or soup.body or soup
    text = container.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return title, "\n".join(lines)


def _extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """Return (title, extracted text) from PDF bytes."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise RuntimeError("PyPDF2 is required for PDF extraction. Install it with: pip install PyPDF2")

    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            pages_text.append(page_text)

    full_text = "\n".join(pages_text)

    # Try to get title from PDF metadata
    title = ""
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title

    # Fallback: use first non-empty line as title
    if not title:
        for line in full_text.splitlines():
            stripped = line.strip()
            if stripped:
                title = stripped[:200]
                break

    return title, full_text


async def fetch_url_content(url: str, timeout: float = 30.0) -> FetchedContent:
    """Fetch a URL and extract its text content.

    Supports HTML pages and PDF documents. Detects content type
    from the response Content-Type header.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        FetchedContent with extracted text, title, and metadata.

    Raises:
        httpx.HTTPStatusError: If the server returns an error status code.
        ValueError: If the content type is unsupported.
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/pdf,*/*"}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0),
        follow_redirects=True,
        max_redirects=5,
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    raw_content_type = response.headers.get("content-type", "").lower()

    if "application/pdf" in raw_content_type or url.lower().endswith(".pdf"):
        title, text = _extract_text_from_pdf(response.content)
        content_type = "pdf"
    elif "text/html" in raw_content_type or "text/plain" in raw_content_type:
        title, text = _extract_text_from_html(response.text)
        content_type = "html"
    else:
        raise ValueError(
            f"Unsupported content type: {raw_content_type}. "
            "Only HTML and PDF are supported."
        )

    if not text.strip():
        raise ValueError("No text content could be extracted from the URL.")

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return FetchedContent(
        url=url,
        title=title or "Untitled",
        text=text,
        content_type=content_type,
        content_hash=content_hash,
        content_length=len(text),
    )
