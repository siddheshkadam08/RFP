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
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import update

from app.agents.pipeline import PipelineStage, run_intelligence_pipeline
from app.core.database import AsyncSession
from app.models.document import Document, DocumentEmbedding, DocumentType, ProcessingStatus
from app.models.opportunity import OpportunityCategory
from app.models.source import CrawlStatus, Source
from app.services import ai_service, document_service, opportunity_service
from app.services.url_fetcher import fetch_url_content

logger = logging.getLogger(__name__)

# Cap text sent to the LLM to control token cost (mirrors the analyze endpoint).
_MAX_CONTENT_CHARS = 15_000

_DOC_TYPE_MAP = {"html": DocumentType.HTML, "pdf": DocumentType.PDF}


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


async def ingest_source(db: AsyncSession, source: Source) -> dict[str, Any]:
    """Fetch one source, run the AI pipeline, and persist a Document + Opportunity.

    Returns a summary dict (never raises): a single bad source must not abort a batch.
    """
    source_id = source.id
    source_url = source.url
    source_region = source.region

    async def _mark_source(crawl_status: CrawlStatus) -> None:
        await db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                last_crawl_at=_now(),
                last_crawl_status=crawl_status,
                # Reflect the latest crawl outcome so the dashboard's avg success rate is real.
                success_rate=100.0 if crawl_status == CrawlStatus.SUCCESS else 0.0,
            )
        )
        await db.commit()

    # 1. Fetch ---------------------------------------------------------------
    try:
        fetched = await fetch_url_content(source_url)
    except Exception as exc:  # noqa: BLE001 - report, do not crash the batch
        logger.warning("Crawl fetch failed for source %s (%s): %s", source_id, source_url, exc)
        await _mark_source(CrawlStatus.FAILED)
        return {
            "source_id": str(source_id),
            "status": "failed",
            "error": str(exc),
            "documents_created": 0,
            "opportunities_created": 0,
        }

    # 2. De-dupe by content hash --------------------------------------------
    existing = await document_service.get_document_by_hash(db, fetched.content_hash)
    if existing is not None:
        await _mark_source(CrawlStatus.SUCCESS)
        return {
            "source_id": str(source_id),
            "status": "skipped",
            "reason": "duplicate",
            "documents_created": 0,
            "opportunities_created": 0,
        }

    document_id = None
    try:
        # 3. Persist the raw document (PROCESSING) --------------------------
        document = await document_service.create_document(
            db,
            {
                "source_id": source_id,
                "url": source_url,
                "title": fetched.title,
                "content_text": fetched.text,
                "content_hash": fetched.content_hash,
                "document_type": _to_document_type(fetched.content_type),
                "language": "en",
                "processing_status": ProcessingStatus.PROCESSING,
                "metadata_json": {
                    "content_type": fetched.content_type,
                    "content_length": fetched.content_length,
                },
            },
        )
        document_id = document.id

        # 4. Run the AI pipeline -------------------------------------------
        content = fetched.text[:_MAX_CONTENT_CHARS]
        results = await run_intelligence_pipeline(
            content, {"source_id": str(source_id), "url": source_url}
        )
        by_stage = {result.stage: result.data for result in results}
        relevance = by_stage.get(PipelineStage.RELEVANCE_CHECK, {})
        is_relevant = bool(relevance.get("relevant", False))
        confidence = float(relevance.get("confidence", 0.0) or 0.0)

        opportunities_created = 0
        opportunity_id = None
        score = 0

        # 5. If relevant, build + persist the opportunity ------------------
        if is_relevant:
            extracted = by_stage.get(PipelineStage.EXTRACTION, {})
            classification = by_stage.get(PipelineStage.CLASSIFICATION, {})
            scoring = by_stage.get(PipelineStage.SCORING, {})
            score = int(scoring.get("score", 0) or 0)
            standards = extracted.get("standards")
            breakdown = scoring.get("breakdown")
            title = _coalesce_title(extracted.get("title"), fetched.title)
            # ai_summary is injected into the extraction dict by the pipeline.
            ai_summary = extracted.get("ai_summary") or ""

            # Semantic-search embedding (best-effort; null if the resource is unavailable).
            embedding = None
            try:
                embedding = await ai_service.get_embedding(f"{title}\n{ai_summary}".strip())
            except Exception as exc:  # noqa: BLE001 - embedding is optional
                logger.warning("Embedding skipped for source %s: %s", source_id, exc)

            opportunity = await opportunity_service.create_opportunity(
                db,
                {
                    "document_id": document_id,
                    "title": title,
                    "institution": (extracted.get("institution") or "Unknown")[:255],
                    "country": (extracted.get("country") or "Unknown")[:100],
                    "region": source_region,  # pipeline has no region; use the source's
                    "category": _to_category(classification.get("category")),
                    "standards": standards if isinstance(standards, list) else [],
                    "budget": _to_budget(extracted.get("budget")),
                    "deadline": _parse_deadline(extracted.get("deadline")),
                    "scope": extracted.get("scope"),
                    "score": score,
                    "score_breakdown": breakdown if isinstance(breakdown, dict) else {},
                    "ai_summary": ai_summary,
                    # No reasoning field in the pipeline; use the relevance reason.
                    "ai_reasoning": relevance.get("reason") or "",
                    "source_url": source_url,
                    "embedding": embedding,
                },
            )
            opportunities_created = 1
            opportunity_id = str(opportunity.id)

        # 6. Finalize the document + source --------------------------------
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                is_relevant=is_relevant,
                relevance_confidence=confidence,
                processing_status=ProcessingStatus.COMPLETED,
            )
        )
        await db.commit()
        await _mark_source(CrawlStatus.SUCCESS)

        # 7. Embed the document body into chunks for semantic doc-corpus search.
        await _embed_document(db, document_id, fetched.text)

        return {
            "source_id": str(source_id),
            "status": "ok",
            "relevant": is_relevant,
            "documents_created": 1,
            "opportunities_created": opportunities_created,
            "opportunity_id": opportunity_id,
            "score": score,
            "reason": relevance.get("reason", ""),
        }

    except Exception as exc:  # noqa: BLE001 - report, do not crash the batch
        await db.rollback()
        logger.exception("Crawl processing failed for source %s", source_id)
        if document_id is not None:
            try:
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(processing_status=ProcessingStatus.FAILED)
                )
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
        await _mark_source(CrawlStatus.FAILED)
        return {
            "source_id": str(source_id),
            "status": "failed",
            "error": str(exc),
            "documents_created": 0,
            "opportunities_created": 0,
        }
