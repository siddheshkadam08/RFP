"""Ingestion orchestrator: fetch a source, run the AI pipeline, persist results.

This is the single shared entry point for turning a configured ``Source`` into a
``Document`` + ``Opportunity``. It is called two ways:
  * synchronously by the ``POST /sources/{id}/crawl`` endpoint (no Redis/Celery), and
  * (later) by the Celery ``crawl_sources`` task for scheduled crawling.

It reuses the existing fetcher (``url_fetcher.fetch_url_content``) and AI pipeline
(``agents.pipeline.run_intelligence_pipeline``) — no new crawling/AI logic here.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urlparse

from sqlalchemy import update
from sqlalchemy.exc import InterfaceError as SAInterfaceError, OperationalError as SAOperationalError

from app.agents.pipeline import PipelineStage, run_intelligence_pipeline
from app.core.config import settings
from app.core.database import AsyncSession, session_context
from app.core.logging_config import get_logger
from app.models.document import Document, DocumentEmbedding, DocumentType, ProcessingStatus
from app.models.opportunity import OpportunityCategory
from app.models.source import CrawlStatus, Source
from app.services import ai_service, alert_service, crawler, document_service, opportunity_service
from app.services.document_service import sanitize_text
from app.services.url_fetcher import FetchedContent, fetch_raw_text, fetch_url_content, render_interactive

logger = get_logger(__name__)

# Cap text sent to the LLM to control token cost (mirrors the analyze endpoint).
_MAX_CONTENT_CHARS = 15_000

_DOC_TYPE_MAP = {
    "html": DocumentType.HTML,
    "pdf": DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "doc": DocumentType.DOCX,  # legacy binary Word -> nearest enum value
    "xlsx": DocumentType.XLSX,
}

# SQLAlchemy / asyncpg errors that indicate a closed or recycled connection — safe to retry.
_TRANSIENT_DB_ERRORS = (SAInterfaceError, SAOperationalError)


async def _db_execute(fn: Any, retries: int = 2) -> Any:
    """Execute an async callable performing DB work, retrying on transient connection errors.

    Each retry re-invokes ``fn`` which should create a fresh ``session_context()`` call,
    guaranteeing a live pooled connection regardless of how long the crawl has been running.
    """
    for attempt in range(retries + 1):
        try:
            return await fn()
        except _TRANSIENT_DB_ERRORS as exc:
            if attempt >= retries:
                raise
            delay = 2.0 ** attempt
            logger.warning(
                "Transient DB error (attempt %s/%s), retrying in %.0fs: %s: %s",
                attempt + 1, retries + 1, delay, type(exc).__name__, exc,
            )
            await asyncio.sleep(delay)


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
    """Parse any deadline representation into a UTC-aware datetime.

    Handles all formats any LLM or source might produce:
    - datetime (aware or naive)
    - date object (no time component)
    - ISO 8601 string with or without timezone (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS, ...Z, ...+HH:MM)
    - Any unrecognised value → None
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):  # date but NOT datetime (subclass check order matters)
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
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


async def _embed_document(document_id: Any, content_text: str) -> int:
    """Chunk, embed, and persist DocumentEmbedding rows using a fresh short-lived session.

    The DB connection is never held during LLM embedding calls (each takes 10-30 s).
    All chunks are embedded first (phase 1), then saved in one short transaction (phase 2).
    Best-effort: any failure is logged and swallowed so it never blocks ingestion.
    """
    content_text = sanitize_text(content_text) or ""
    chunks = _chunk_text(content_text)[:_MAX_CHUNKS]
    if not chunks:
        return 0
    logger.info("🧠 [EMBEDDING] doc_id=%s  chunk_count=%s", document_id, len(chunks))  # type: ignore[attr-defined]

    # Phase 1: embed all chunks — no DB connection held during LLM calls.
    embedded: list[tuple[int, str, list[float]]] = []
    for index, chunk in enumerate(chunks):
        try:
            vector = await ai_service.get_embedding(chunk)
            embedded.append((index, chunk, vector))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chunk embedding skipped (doc %s, chunk %s): %s", document_id, index, exc)

    if not embedded:
        return 0

    # Phase 2: persist all embeddings in one short-lived session.
    async def _save_embeddings() -> None:
        async with session_context() as db:
            for idx, ck, vec in embedded:
                db.add(DocumentEmbedding(
                    document_id=document_id,
                    chunk_index=idx,
                    chunk_text=sanitize_text(ck) or "",
                    embedding=vec,
                ))
            await db.commit()

    try:
        await _db_execute(_save_embeddings)
        logger.success("✅ [EMBEDDING SAVED] doc_id=%s  chunks_saved=%s", document_id, len(embedded))  # type: ignore[attr-defined]
        return len(embedded)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Document embedding DB save failed for doc %s: %s", document_id, exc)
        return 0


async def _process_page(source: Source, fetched: FetchedContent) -> dict[str, Any]:
    """De-dupe, persist a Document, run the AI pipeline, and (if relevant) create an
    Opportunity for a single fetched page/document.

    Each DB operation uses its own short-lived ``session_context()`` so no connection
    is held during LLM pipeline calls (which can take 30-120 s per page).
    Never raises — returns a summary dict.
    """
    page_url = fetched.url

    # Step A: Sanitize — no DB.
    original_len = len(fetched.text or "")
    fetched.text = sanitize_text(fetched.text) or ""
    clean_len = len(fetched.text)
    if original_len != clean_len:
        logger.info(  # type: ignore[attr-defined]
            "🧹 [SANITIZED] url=%s  chars_removed=%s", page_url, original_len - clean_len
        )

    logger.data("📄 [CONTENT PREVIEW] url=%s\n    %s", page_url, fetched.text[:200])  # type: ignore[attr-defined]

    # Step B: Check duplicate — short read, fresh session.
    async def _check_dup() -> Any:
        async with session_context() as db:
            return await document_service.get_document_by_hash(db, fetched.content_hash)

    try:
        existing = await _db_execute(_check_dup)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ [PAGE FAILED] url=%s  error=%s: %s", page_url, type(exc).__name__, exc)  # type: ignore[attr-defined]
        return {"status": "failed", "error": str(exc), "documents_created": 0,
                "opportunities_created": 0, "url": page_url}

    if existing is not None:
        logger.info("⏭️  [SKIPPED] url=%s  reason=duplicate", page_url)  # type: ignore[attr-defined]
        return {"status": "skipped", "reason": "duplicate", "documents_created": 0,
                "opportunities_created": 0, "url": page_url}

    # Step C: Persist document with PROCESSING status — short write, fresh session.
    async def _create_doc() -> Any:
        async with session_context() as db:
            return await document_service.create_document(
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

    document_id = None
    try:
        logger.info("💾 [SAVING DOC] url=%s  title=%r", page_url, (fetched.title or "")[:80])  # type: ignore[attr-defined]
        doc = await _db_execute(_create_doc)
        document_id = doc.id
        logger.success("✅ [DOC SAVED] doc_id=%s  url=%s", document_id, page_url)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ [PAGE FAILED] url=%s  error=%s: %s", page_url, type(exc).__name__, exc)  # type: ignore[attr-defined]
        return {"status": "failed", "error": str(exc), "documents_created": 0,
                "opportunities_created": 0, "url": page_url}

    # Steps D-G: AI pipeline + DB saves.  No session is held during LLM calls.
    is_relevant = False
    confidence = 0.0
    opportunities_created = 0
    opportunity_id: str | None = None
    score = 0
    relevance: dict[str, Any] = {}

    try:
        # Step D: Full AI pipeline — NO DB session held (30-120 s of LLM calls).
        content = fetched.text[:_MAX_CONTENT_CHARS]
        results = await run_intelligence_pipeline(content, {"source_id": str(source.id), "url": page_url})
        by_stage = {result.stage: result.data for result in results}
        relevance = by_stage.get(PipelineStage.RELEVANCE_CHECK, {})
        is_relevant = bool(relevance.get("relevant", False))
        confidence = float(relevance.get("confidence", 0.0) or 0.0)

        if not is_relevant:
            logger.info(  # type: ignore[attr-defined]
                "⏭️  [SKIPPED] url=%s  reason=not_relevant  confidence=%.2f  reason_text=%s",
                page_url, confidence, relevance.get("reason", "")[:120],
            )

        if is_relevant:
            extracted = by_stage.get(PipelineStage.EXTRACTION, {})
            classification = by_stage.get(PipelineStage.CLASSIFICATION, {})
            scoring = by_stage.get(PipelineStage.SCORING, {})
            score = int(scoring.get("score", 0) or 0)
            standards = extracted.get("standards")
            breakdown = scoring.get("breakdown")
            title = _coalesce_title(extracted.get("title"), fetched.title)
            ai_summary = extracted.get("ai_summary") or ""

            # Step E: opportunity embedding — LLM call, no DB session held.
            embedding = None
            try:
                embedding = await ai_service.get_embedding(f"{title}\n{ai_summary}".strip())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Embedding skipped for %s: %s", page_url, exc)

            # Step F: Persist opportunity — short write, fresh session.
            async def _create_opp() -> Any:
                async with session_context() as db:
                    return await opportunity_service.create_opportunity(
                        db,
                        {
                            "document_id": document_id,
                            "title": sanitize_text(title),
                            "institution": sanitize_text((extracted.get("institution") or "Unknown")[:255]),
                            "country": sanitize_text((extracted.get("country") or "Unknown")[:100]),
                            "region": sanitize_text(source.region),
                            "category": _to_category(classification.get("category")),
                            "standards": standards if isinstance(standards, list) else [],
                            "budget": sanitize_text(_to_budget(extracted.get("budget"))),
                            "deadline": _parse_deadline(extracted.get("deadline")),
                            "scope": sanitize_text(extracted.get("scope")),
                            "score": score,
                            "score_breakdown": breakdown if isinstance(breakdown, dict) else {},
                            "ai_summary": sanitize_text(ai_summary),
                            "ai_reasoning": sanitize_text(relevance.get("reason") or ""),
                            "source_url": sanitize_text(page_url),
                            "embedding": embedding,
                        },
                    )

            opp = await _db_execute(_create_opp)
            opportunities_created = 1
            opportunity_id = str(opp.id)
            logger.success(  # type: ignore[attr-defined]
                "✅ [OPPORTUNITY SAVED] opp_id=%s  title=%r  score=%s  url=%s",
                opportunity_id, title[:60], score, page_url,
            )

        # Step G: Mark document COMPLETED — short write, fresh session.
        async def _finish_doc() -> None:
            async with session_context() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(is_relevant=is_relevant, relevance_confidence=confidence,
                            processing_status=ProcessingStatus.COMPLETED)
                )
                await db.commit()

        await _db_execute(_finish_doc)

    except Exception as exc:  # noqa: BLE001 - one bad page must not abort the crawl
        logger.error(  # type: ignore[attr-defined]
            "❌ [PAGE FAILED] url=%s  error=%s: %s", page_url, type(exc).__name__, exc,
        )
        if document_id is not None:
            try:
                async def _fail_doc() -> None:
                    async with session_context() as db:
                        await db.execute(
                            update(Document).where(Document.id == document_id)
                            .values(processing_status=ProcessingStatus.FAILED)
                        )
                        await db.commit()
                await _db_execute(_fail_doc)
            except Exception:  # noqa: BLE001
                pass
        return {"status": "failed", "error": str(exc), "documents_created": 0,
                "opportunities_created": 0, "url": page_url}

    # Step H: Embed document chunks — manages its own sessions internally.
    await _embed_document(document_id, fetched.text)

    # Step I: Emit opportunity alerts — short write, fresh session.
    if opportunity_id:
        try:
            async def _emit_alerts() -> None:
                async with session_context() as db:
                    await alert_service.emit_opportunity_alerts(db, opportunity_id)
            await _db_execute(_emit_alerts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alert emit failed for opp %s: %s", opportunity_id, exc)

    return {"status": "ok", "relevant": is_relevant, "documents_created": 1,
            "opportunities_created": opportunities_created, "opportunity_id": opportunity_id,
            "score": score, "reason": relevance.get("reason", ""), "url": page_url}


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
    logger.info("🌐 [CRAWL START] source_id=%s  url=%s", source_id, source_url)  # type: ignore[attr-defined]

    async def _mark_source(crawl_status: CrawlStatus) -> None:
        async def _do() -> None:
            async with session_context() as db:
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
        try:
            await _db_execute(_do)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to update crawl status for source %s: %s", source_id, exc)

    # 1. Fetch the root (best-effort) ---------------------------------------
    logger.info("🔍 [FETCHING] url=%s", source_url)  # type: ignore[attr-defined]
    try:
        fetched = await fetch_url_content(source_url)
        logger.info(  # type: ignore[attr-defined]
            "✅ [FETCHED] url=%s  type=%s  size=%s chars",
            source_url, fetched.content_type, fetched.content_length,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Crawl fetch failed for source %s (%s): %s", source_id, source_url, exc)
        await _mark_source(CrawlStatus.FAILED)
        try:
            async with session_context() as _alert_db:
                await alert_service.emit_crawl_failure_alert(_alert_db, source_url, exc)
        except Exception:  # noqa: BLE001
            pass
        return {"source_id": str(source_id), "status": "failed", "error": str(exc),
                "documents_created": 0, "opportunities_created": 0}

    # 2. Expand the root into content links + pagination --------------------
    root_links, root_pagination = (
        await _expand_page(source, fetched, allow_fallbacks=True, interactive=True)
        if settings.CRAWL_FOLLOW_LINKS else ([], [])
    )

    # 2b. Leaf/detail root (nothing to follow): process the page itself ------
    if not root_links and not root_pagination:
        result = await _process_page(source, fetched)
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
    logger.info(  # type: ignore[attr-defined]
        "🔗 [LINKS FOUND] url=%s  count=%s  links=%s",
        source_url, len(root_links),
        [c.url for c in root_links[:10]],
    )

    fetches = 0
    while frontier and fetches < settings.CRAWL_MAX_PAGES:
        item = frontier.popleft()
        logger.info("🔍 [FETCHING] url=%s  depth=%s", item.url, item.depth)  # type: ignore[attr-defined]
        try:
            page = await fetch_url_content(item.url)
            logger.info(  # type: ignore[attr-defined]
                "✅ [FETCHED] url=%s  type=%s  size=%s chars",
                item.url, page.content_type, page.content_length,
            )
        except Exception as exc:  # noqa: BLE001 - skip a bad link, keep crawling
            exc_str = str(exc).lower()
            # Downgrade to DEBUG for expected non-errors:
            # - portal/login/session-gated pages that return no extractable body
            # - SSL certificate failures on self-signed government portals (e.g. xbrl.bom.mu)
            # - connection refused / DNS failures on decommissioned links
            _is_ignorable = (
                "no text content" in exc_str
                or "ssl" in exc_str
                or "certificate" in exc_str
                or "connection" in exc_str and "refused" in exc_str
            )
            (logger.debug if _is_ignorable else logger.warning)(
                "Crawl fetch failed (%s): %s", item.url, exc
            )
            continue
        fetches += 1
        if item.process:
            page_results.append(await _process_page(source, page))
        if item.depth < settings.CRAWL_MAX_DEPTH:
            links, pagination = await _expand_page(source, page, allow_fallbacks=False)
            await _enqueue(links, pagination, depth=item.depth)

    logger.info(
        "🏁 [CRAWL DONE] source_id=%s  pages_fetched=%s  pages_processed=%s  "
        "candidates=%s  skipped_irrelevant=%s  depth<=%s",
        source_id, fetches, len(page_results), total_candidates,
        skipped_irrelevant, settings.CRAWL_MAX_DEPTH,
    )
    await _mark_source(CrawlStatus.SUCCESS)
    return {
        "source_id": str(source_id),
        "status": "ok",
        "mode": "crawl",
        "candidates": total_candidates,
        "skipped_irrelevant": skipped_irrelevant,
        "pages_fetched": fetches,
        "pages_followed": len(page_results),
        "max_depth": settings.CRAWL_MAX_DEPTH,
        "documents_created": sum(r.get("documents_created", 0) for r in page_results),
        "opportunities_created": sum(r.get("opportunities_created", 0) for r in page_results),
        "results": page_results,
    }
