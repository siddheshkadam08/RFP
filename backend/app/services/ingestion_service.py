"""Ingestion orchestrator: fetch a source, run the AI pipeline, persist results.

This is the single shared entry point for turning a configured ``Source`` into a
``Document`` + ``Opportunity``. It is called two ways:
  * synchronously by the ``POST /sources/{id}/crawl`` endpoint (no Redis/Celery), and
  * (later) by the Celery ``crawl_sources`` task for scheduled crawling.

It reuses the existing fetcher (``url_fetcher.fetch_url_content``) and AI pipeline
(``agents.pipeline.run_intelligence_pipeline``) — no new crawling/AI logic here.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urlparse

from sqlalchemy import update

from app.agents.pipeline import PipelineStage, run_intelligence_pipeline
from app.core.config import settings
from app.core.database import AsyncSession
from app.models.document import Document, DocumentEmbedding, DocumentType, ProcessingStatus
from app.models.opportunity import OpportunityCategory
from app.models.source import CrawlStatus, Source
from app.services import ai_service, alert_service, crawler, document_service, opportunity_service
from app.services.robots import RobotsGate
from app.services.url_fetcher import FetchedContent, fetch_raw_text, fetch_url_content, render_interactive

logger = logging.getLogger(__name__)

# Cap text sent to the LLM to control token cost (mirrors the analyze endpoint).
_MAX_CONTENT_CHARS = 15_000

_DOC_TYPE_MAP = {
    "html": DocumentType.HTML,
    "pdf": DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "doc": DocumentType.DOCX,  # legacy binary Word -> nearest enum value
    "xlsx": DocumentType.XLSX,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_document_type(content_type: str) -> DocumentType:
    return _DOC_TYPE_MAP.get((content_type or "").lower(), DocumentType.HTML)


def _to_category(value: Any) -> OpportunityCategory:
    """Map the classifier's string (e.g. 'suptech') to the enum; default SUPTECH.

    The pipeline may emit 'other' on a classification failure, which is not a valid
    category — fall back rather than raising.
    """
    try:
        return OpportunityCategory(str(value).strip().lower())
    except (ValueError, AttributeError):
        return OpportunityCategory.SUPTECH


def _parse_deadline(value: Any) -> datetime | None:
    """The extractor returns a string (or None); the column is a datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _to_budget(value: Any) -> str | None:
    """Budget column is String(255); extractor may return a number, string, or None."""
    if value is None:
        return None
    return str(value)[:255]


def _coalesce_title(extracted_title: Any, fetched_title: str) -> str:
    title = (extracted_title or "").strip() if isinstance(extracted_title, str) else ""
    if not title or title.lower() == "untitled opportunity":
        title = (fetched_title or "").strip() or "Untitled"
    return title[:500]


# Document-chunk embedding (semantic doc-corpus search, FR-SEARCH-002). Best-effort.
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 150
_MAX_CHUNKS = 20


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping ~``size``-char chunks for embedding."""
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


async def _embed_document(db: AsyncSession, document_id: Any, content_text: str) -> int:
    """Chunk a document's text, embed each chunk, and persist ``DocumentEmbedding`` rows.

    Best-effort: any failure is logged and swallowed so it never blocks ingestion.
    """
    chunks = _chunk_text(content_text)[:_MAX_CHUNKS]
    if not chunks:
        return 0
    created = 0
    try:
        for index, chunk in enumerate(chunks):
            try:
                vector = await ai_service.get_embedding(chunk)
            except Exception as exc:  # noqa: BLE001 - skip a single bad chunk
                logger.warning("Chunk embedding skipped (doc %s, chunk %s): %s", document_id, index, exc)
                continue
            db.add(
                DocumentEmbedding(
                    document_id=document_id,
                    chunk_index=index,
                    chunk_text=chunk,
                    embedding=vector,
                )
            )
            created += 1
        if created:
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - never block ingest
        logger.warning("Document embedding failed for doc %s: %s", document_id, exc)
        await db.rollback()
        return 0
    return created


async def _process_page(db: AsyncSession, source: Source, fetched: FetchedContent) -> dict[str, Any]:
    """De-dupe, persist a Document, run the AI pipeline, and (if relevant) create an
    Opportunity for a single fetched page/document. Never raises — returns a summary dict."""
    page_url = fetched.url

    existing = await document_service.get_document_by_hash(db, fetched.content_hash)
    if existing is not None:
        return {"status": "skipped", "reason": "duplicate", "documents_created": 0,
                "opportunities_created": 0, "url": page_url}

    document_id = None
    try:
        document = await document_service.create_document(
            db,
            {
                "source_id": source.id,
                "url": page_url,
                "title": fetched.title,
                "content_text": fetched.text,
                "content_hash": fetched.content_hash,
                "document_type": _to_document_type(fetched.content_type),
                "language": "en",
                "processing_status": ProcessingStatus.PROCESSING,
                "metadata_json": {"content_type": fetched.content_type, "content_length": fetched.content_length},
            },
        )
        document_id = document.id

        content = fetched.text[:_MAX_CONTENT_CHARS]
        results = await run_intelligence_pipeline(content, {"source_id": str(source.id), "url": page_url})
        by_stage = {result.stage: result.data for result in results}
        relevance = by_stage.get(PipelineStage.RELEVANCE_CHECK, {})
        is_relevant = bool(relevance.get("relevant", False))
        confidence = float(relevance.get("confidence", 0.0) or 0.0)

        opportunities_created = 0
        opportunity_id = None
        score = 0

        if is_relevant:
            extracted = by_stage.get(PipelineStage.EXTRACTION, {})
            classification = by_stage.get(PipelineStage.CLASSIFICATION, {})
            scoring = by_stage.get(PipelineStage.SCORING, {})
            score = int(scoring.get("score", 0) or 0)
            standards = extracted.get("standards")
            breakdown = scoring.get("breakdown")
            title = _coalesce_title(extracted.get("title"), fetched.title)
            ai_summary = extracted.get("ai_summary") or ""

            embedding = None
            try:
                embedding = await ai_service.get_embedding(f"{title}\n{ai_summary}".strip())
            except Exception as exc:  # noqa: BLE001 - embedding is optional
                logger.warning("Embedding skipped for %s: %s", page_url, exc)

            opportunity = await opportunity_service.create_opportunity(
                db,
                {
                    "document_id": document_id,
                    "title": title,
                    "institution": (extracted.get("institution") or "Unknown")[:255],
                    "country": (extracted.get("country") or "Unknown")[:100],
                    "region": source.region,  # pipeline has no region; use the source's
                    "category": _to_category(classification.get("category")),
                    "standards": standards if isinstance(standards, list) else [],
                    "budget": _to_budget(extracted.get("budget")),
                    "deadline": _parse_deadline(extracted.get("deadline")),
                    "scope": extracted.get("scope"),
                    "score": score,
                    "score_breakdown": breakdown if isinstance(breakdown, dict) else {},
                    "ai_summary": ai_summary,
                    "ai_reasoning": relevance.get("reason") or "",
                    "source_url": page_url,  # link the opportunity to its own page, not the listing
                    "embedding": embedding,
                },
            )
            opportunities_created = 1
            opportunity_id = str(opportunity.id)

        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(is_relevant=is_relevant, relevance_confidence=confidence,
                    processing_status=ProcessingStatus.COMPLETED)
        )
        await db.commit()

        await _embed_document(db, document_id, fetched.text)
        if opportunity_id:
            await alert_service.emit_opportunity_alerts(db, opportunity_id)

        return {"status": "ok", "relevant": is_relevant, "documents_created": 1,
                "opportunities_created": opportunities_created, "opportunity_id": opportunity_id,
                "score": score, "reason": relevance.get("reason", ""), "url": page_url}

    except Exception as exc:  # noqa: BLE001 - one bad page must not abort the crawl
        await db.rollback()
        logger.exception("Page processing failed for %s", page_url)
        if document_id is not None:
            try:
                await db.execute(
                    update(Document).where(Document.id == document_id).values(processing_status=ProcessingStatus.FAILED)
                )
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
        return {"status": "failed", "error": str(exc), "documents_created": 0,
                "opportunities_created": 0, "url": page_url}


async def _sitemap_candidates(base_url: str) -> list:
    """Discover candidates from robots.txt `Sitemap:` entries / `/sitemap.xml` (1 index level)."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    sitemap_urls: list[str] = []
    robots = await fetch_raw_text(f"{origin}/robots.txt")
    if robots:
        sitemap_urls.extend(crawler.sitemaps_from_robots(robots))
    sitemap_urls.append(f"{origin}/sitemap.xml")

    for sitemap_url in sitemap_urls[:3]:
        xml = await fetch_raw_text(sitemap_url)
        if not xml:
            continue
        is_index, locs = crawler.parse_sitemap(xml)
        if is_index and locs:  # sitemap-index -> resolve the first child sitemap
            child = await fetch_raw_text(locs[0])
            if child:
                _, locs = crawler.parse_sitemap(child)
        candidates = crawler.candidates_from_locs(locs, base_url)
        if candidates:
            return candidates
    return []


async def _discover_candidates(source: Source, fetched: FetchedContent) -> list:
    """Pick crawl candidates: on-page links / feed entries, with feed- and sitemap-discovery fallbacks."""
    candidates = crawler.select_candidates(source, fetched)
    if not candidates and fetched.content_type == "html" and fetched.raw_html:
        feed_url = crawler.discover_feed(fetched.url, fetched.raw_html)
        if feed_url:
            try:
                feed_fetched = await fetch_url_content(feed_url)
                candidates = crawler.parse_feed(feed_fetched.raw_html or feed_fetched.text)
            except Exception as exc:  # noqa: BLE001 - feed fallback is best-effort
                logger.warning("Feed fetch failed (%s): %s", feed_url, exc)
    if not candidates and fetched.content_type == "html":
        candidates = await _sitemap_candidates(fetched.url)
    return candidates


def _norm_url(url: str) -> str:
    """Canonical key for de-duping the crawl frontier (drop fragment, lower host, trim slash)."""
    parsed = urlparse(urldefrag(url)[0])
    base = f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"
    return f"{base}?{parsed.query}" if parsed.query else base


@dataclass
class _FrontierItem:
    url: str
    title: str
    depth: int
    process: bool  # True -> turn the page into a Document; False -> expand-only (listing/pagination)


async def _gate_candidates(candidates: list) -> list:
    """Relevance-gate candidate titles before fetching; on gate failure, keep all."""
    if not candidates:
        return []
    titles = [c.title for c in candidates]
    try:
        mask = await ai_service.filter_relevant_titles(titles)
    except Exception as exc:  # noqa: BLE001 - if the gate fails, don't drop everything
        logger.warning("Title gate failed, following all candidates: %s", exc)
        mask = [True] * len(titles)
    return [c for c, keep in zip(candidates, mask) if keep]


async def _expand_page(
    source: Source, fetched: FetchedContent, *, allow_fallbacks: bool, interactive: bool = False
) -> tuple[list, list]:
    """Return ``(content_links, pagination_urls)`` for a fetched page.

    ``allow_fallbacks`` enables the feed/sitemap discovery fallbacks (root only). ``interactive``
    (root only) allows one JS-interaction re-render (Load-More / infinite-scroll / pager) when the
    listing yields too few static candidates — gated to the root so detail pages, which naturally
    have few links, don't each spawn a browser.
    """
    candidates = await _discover_candidates(source, fetched) if allow_fallbacks else crawler.select_candidates(source, fetched)

    needs_render = (
        interactive
        and fetched.content_type == "html" and fetched.raw_html
        and len(candidates) < settings.CRAWL_MIN_CANDIDATES_BEFORE_RENDER
        and settings.CRAWL_RENDER_JS and settings.CRAWL_INTERACT_JS
    )
    if needs_render:
        try:
            rendered = await render_interactive(fetched.url)
        except Exception as exc:  # noqa: BLE001 - interactive render is best-effort
            logger.warning("Interactive render failed (%s): %s", fetched.url, exc)
            rendered = None
        if rendered:
            known = {c.url for c in candidates}
            candidates += [c for c in crawler.extract_links(fetched.url, rendered) if c.url not in known]

    pagination: list = []
    if fetched.content_type == "html" and fetched.raw_html:
        pagination = crawler.discover_pagination(fetched.url, fetched.raw_html)
    return candidates, pagination


async def ingest_source(db: AsyncSession, source: Source) -> dict[str, Any]:
    """Crawl one source breadth-first: fetch the root, follow relevance-gated child links to
    ``CRAWL_MAX_DEPTH`` (with pagination), process leaf/detail pages, all under a global
    ``CRAWL_MAX_PAGES`` fetch budget. Never raises."""
    source_id = source.id
    source_url = source.url
    gate = RobotsGate()  # robots.txt allow-checks + per-origin rate limiting (FR-CRAWL-005)

    async def _mark_source(crawl_status: CrawlStatus) -> None:
        await db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                last_crawl_at=_now(),
                last_crawl_status=crawl_status,
                success_rate=100.0 if crawl_status == CrawlStatus.SUCCESS else 0.0,
            )
        )
        await db.commit()

    # 1. Fetch the root (best-effort) ---------------------------------------
    if not await gate.allowed(source_url):
        logger.info("robots.txt disallows root %s; skipping source %s", source_url, source_id)
        await _mark_source(CrawlStatus.SUCCESS)  # ran cleanly — the site just opts out
        return {"source_id": str(source_id), "status": "skipped", "reason": "robots_disallow",
                "documents_created": 0, "opportunities_created": 0}
    await gate.throttle(source_url)
    try:
        fetched = await fetch_url_content(source_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Crawl fetch failed for source %s (%s): %s", source_id, source_url, exc)
        await _mark_source(CrawlStatus.FAILED)
        await alert_service.emit_crawl_failure_alert(db, source_url, exc)
        return {"source_id": str(source_id), "status": "failed", "error": str(exc),
                "documents_created": 0, "opportunities_created": 0}

    # 2. Expand the root into content links + pagination --------------------
    root_links, root_pagination = (
        await _expand_page(source, fetched, allow_fallbacks=True, interactive=True)
        if settings.CRAWL_FOLLOW_LINKS else ([], [])
    )

    # 2b. Leaf/detail root (nothing to follow): process the page itself ------
    if not root_links and not root_pagination:
        result = await _process_page(db, source, fetched)
        await _mark_source(CrawlStatus.SUCCESS if result.get("status") != "failed" else CrawlStatus.FAILED)
        result["source_id"] = str(source_id)
        result.setdefault("mode", "single")
        return result

    # 3. Breadth-first crawl ------------------------------------------------
    visited: set[str] = {_norm_url(source_url)}
    frontier: deque[_FrontierItem] = deque()
    page_results: list[dict[str, Any]] = []
    total_candidates = 0
    skipped_irrelevant = 0
    skipped_disallowed = 0

    async def _enqueue(content_links: list, pagination_urls: list, depth: int) -> None:
        """Gate content links (-> depth+1, processed) and enqueue pagination (-> same depth, expand-only)."""
        nonlocal total_candidates, skipped_irrelevant
        total_candidates += len(content_links)
        gated = await _gate_candidates(content_links)
        skipped_irrelevant += len(content_links) - len(gated)
        for candidate in gated:
            key = _norm_url(candidate.url)
            if key not in visited:
                visited.add(key)
                frontier.append(_FrontierItem(candidate.url, candidate.title, depth + 1, process=True))
        for page_url in pagination_urls:
            key = _norm_url(page_url)
            if key not in visited:
                visited.add(key)
                frontier.append(_FrontierItem(page_url, "", depth, process=False))

    await _enqueue(root_links, root_pagination, depth=0)

    fetches = 0
    while frontier and fetches < settings.CRAWL_MAX_PAGES:
        item = frontier.popleft()
        if not await gate.allowed(item.url):
            skipped_disallowed += 1
            continue
        await gate.throttle(item.url)  # honor crawl-delay / per-origin rate limit
        try:
            page = await fetch_url_content(item.url)
        except Exception as exc:  # noqa: BLE001 - skip a bad link, keep crawling
            logger.warning("Crawl fetch failed (%s): %s", item.url, exc)
            continue
        fetches += 1
        if item.process:
            page_results.append(await _process_page(db, source, page))
        if item.depth < settings.CRAWL_MAX_DEPTH:
            links, pagination = await _expand_page(source, page, allow_fallbacks=False)
            await _enqueue(links, pagination, depth=item.depth)

    logger.info(
        "Source %s crawl: %s fetched, %s processed, %s candidates "
        "(skipped %s irrelevant, %s robots-disallowed), depth<=%s",
        source_id, fetches, len(page_results), total_candidates,
        skipped_irrelevant, skipped_disallowed, settings.CRAWL_MAX_DEPTH,
    )
    await _mark_source(CrawlStatus.SUCCESS)
    return {
        "source_id": str(source_id),
        "status": "ok",
        "mode": "crawl",
        "candidates": total_candidates,
        "skipped_irrelevant": skipped_irrelevant,
        "skipped_disallowed": skipped_disallowed,
        "pages_fetched": fetches,
        "pages_followed": len(page_results),
        "max_depth": settings.CRAWL_MAX_DEPTH,
        "documents_created": sum(r.get("documents_created", 0) for r in page_results),
        "opportunities_created": sum(r.get("opportunities_created", 0) for r in page_results),
        "results": page_results,
    }
