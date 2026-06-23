"""Fetch and extract text from a URL (HTML, PDF, DOCX, XLSX), with a Playwright fallback
for thin / JS-rendered / blocked pages."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from io import BytesIO

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings

logger = logging.getLogger(__name__)

# Declared bot UA with contact — required by SEC.gov's fair-access policy (a generic
# browser UA gets 403 from SEC). Browser-like spoofing helps a few sites but breaks more.
_USER_AGENT = "RFPIntelligenceBot/1.0 (+mailto:admin@example.com)"
_MAX_XLSX_ROWS = 2000

# Lazily-launched, process-wide headless browser (reused across renders).
_playwright = None
_browser = None


@dataclass
class FetchedContent:
    """Result of fetching and extracting content from a URL."""

    url: str
    title: str
    text: str
    content_type: str  # "html" | "pdf" | "docx" | "xlsx"
    content_hash: str
    content_length: int
    raw_html: str | None = None  # set for HTML pages, for link/feed extraction


def _extract_text_from_html(raw_html: str) -> tuple[str, str]:
    """Return (title, cleaned text) from raw HTML."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    def _clean(node) -> str:
        raw = node.get_text(separator="\n", strip=True)
        return "\n".join(line.strip() for line in raw.splitlines() if line.strip())

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"role": "main"})
        or soup.find("div", id="content")
        or soup.find("div", class_="content")
    )
    text = _clean(main) if main else ""
    body_text = _clean(soup.body or soup)
    if len(text) < 200 and len(body_text) > len(text):
        text = body_text
    return title, text


def _extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """Return (title, extracted text) from PDF bytes."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise RuntimeError("PyPDF2 is required for PDF extraction.")

    reader = PdfReader(BytesIO(pdf_bytes))
    pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
    full_text = "\n".join(pages_text)

    title = ""
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title
    if not title:
        for line in full_text.splitlines():
            if line.strip():
                title = line.strip()[:200]
                break
    return title, full_text


def _extract_text_from_docx(data: bytes) -> tuple[str, str]:
    """Return (title, text) from .docx bytes (paragraphs + table cells)."""
    try:
        from docx import Document as DocxDocument
    except ImportError:
        raise RuntimeError("python-docx is required for DOCX extraction.")

    doc = DocxDocument(BytesIO(data))
    parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    text = "\n".join(parts)
    title = parts[0][:200] if parts else "Document"
    return title, text


def _extract_text_from_xlsx(data: bytes) -> tuple[str, str]:
    """Return (title, text) from .xlsx bytes (sheets -> rows -> tab-joined cells)."""
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for sheet in workbook.worksheets:
            lines.append(f"# {sheet.title}")
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if index >= _MAX_XLSX_ROWS:
                    break
                cells = [str(cell) for cell in row if cell is not None]
                if cells:
                    lines.append(" | ".join(cells))
    finally:
        workbook.close()
    return "Spreadsheet", "\n".join(lines)


async def _get_browser():
    """Lazily launch a process-wide headless Chromium (reused across renders)."""
    global _playwright, _browser
    if _browser is not None:
        return _browser
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("Playwright not installed; skipping JS rendering.")
        return None
    try:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        return _browser
    except Exception as exc:  # noqa: BLE001 - degrade to httpx-only
        logger.warning("Playwright launch failed (JS rendering disabled): %s", exc)
        _playwright = None
        _browser = None
        return None


async def _render_with_playwright(url: str, timeout: float = 30.0) -> str | None:
    """Render a page with a real browser and return its HTML, or None on failure."""
    browser = await _get_browser()
    if browser is None:
        return None
    page = None
    try:
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001 - networkidle is best-effort
            pass
        return await page.content()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Playwright render failed for %s: %s", url, exc)
        return None
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass


async def shutdown_browser() -> None:
    """Close the shared browser (call on app shutdown if desired)."""
    global _playwright, _browser
    try:
        if _browser is not None:
            await _browser.close()
        if _playwright is not None:
            await _playwright.stop()
    except Exception:  # noqa: BLE001
        pass
    finally:
        _browser = None
        _playwright = None


async def _http_get(url: str, timeout: float) -> httpx.Response:
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/pdf,application/rss+xml,*/*"}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=10.0), follow_redirects=True, max_redirects=5
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.CRAWL_MAX_BYTES:
        raise ValueError(f"Response too large ({declared} bytes)")
    if len(response.content) > settings.CRAWL_MAX_BYTES:
        raise ValueError("Response exceeds size limit")
    return response


async def fetch_raw_text(url: str, timeout: float = 20.0) -> str | None:
    """Best-effort raw GET returning the response text (for robots.txt / sitemap.xml).

    Skips the JS-render heuristic and returns None on any failure.
    """
    try:
        response = await _http_get(url, timeout)
        return response.text
    except Exception as exc:  # noqa: BLE001 - best-effort discovery
        logger.info("Raw fetch failed (%s): %s", url, exc)
        return None


def _build(url: str, title: str, text: str, content_type: str, raw_html: str | None) -> FetchedContent:
    if not text.strip():
        raise ValueError("No text content could be extracted from the URL.")
    return FetchedContent(
        url=url,
        title=title or "Untitled",
        text=text,
        content_type=content_type,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        content_length=len(text),
        raw_html=raw_html,
    )


async def fetch_url_content(url: str, timeout: float = 30.0) -> FetchedContent:
    """Fetch a URL and extract its text. Supports HTML/PDF/DOCX/XLSX; renders JS-only or
    blocked pages with Playwright when enabled."""
    try:
        response = await _http_get(url, timeout)
    except httpx.HTTPStatusError as exc:
        # Blocked (e.g. 403/429) — a real browser may get through.
        status_code = exc.response.status_code if exc.response is not None else 0
        if settings.CRAWL_RENDER_JS and status_code in (401, 403, 429):
            rendered = await _render_with_playwright(url, timeout)
            if rendered:
                title, text = _extract_text_from_html(rendered)
                return _build(url, title, text, "html", rendered)
        raise

    content_type = response.headers.get("content-type", "").lower()
    lower_url = url.lower()

    if "application/pdf" in content_type or lower_url.endswith(".pdf"):
        title, text = _extract_text_from_pdf(response.content)
        return _build(url, title, text, "pdf", None)

    if "wordprocessingml" in content_type or lower_url.endswith(".docx"):
        title, text = _extract_text_from_docx(response.content)
        return _build(url, title, text, "docx", None)

    if "spreadsheetml" in content_type or lower_url.endswith(".xlsx"):
        title, text = _extract_text_from_xlsx(response.content)
        return _build(url, title, text, "xlsx", None)

    if "text/html" in content_type or "text/plain" in content_type or "xml" in content_type:
        raw_html = response.text
        title, text = _extract_text_from_html(raw_html)
        # Thin page (likely JS-rendered) — try a real browser render.
        if settings.CRAWL_RENDER_JS and len(text) < settings.CRAWL_THIN_TEXT_THRESHOLD:
            rendered = await _render_with_playwright(url, timeout)
            if rendered:
                r_title, r_text = _extract_text_from_html(rendered)
                if len(r_text) > len(text):
                    raw_html, title, text = rendered, (r_title or title), r_text
        return _build(url, title, text, "html", raw_html)

    raise ValueError(f"Unsupported content type: {content_type}. Only HTML, PDF, DOCX, XLSX are supported.")
