from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_, select

from app.core.database import AsyncSession
from app.models.document import DocumentEmbedding
from app.models.opportunity import Opportunity
from app.services.ai_service import get_embedding

logger = logging.getLogger(__name__)

# Candidate pool size fetched before merge/fusion + pagination.
_POOL = 100


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _make_snippet(opportunity: Opportunity, query: str) -> str:
    """A short, query-centered excerpt of the summary (or title) for the result card."""
    text = (opportunity.ai_summary or opportunity.title or "").strip()
    if not text:
        return ""
    needle = (query or "").strip().lower()
    idx = text.lower().find(needle) if needle else -1
    if idx == -1:
        return text[:200] + ("…" if len(text) > 200 else "")
    start = max(0, idx - 60)
    end = min(len(text), idx + len(needle) + 140)
    return f"{'…' if start else ''}{text[start:end]}{'…' if end < len(text) else ''}"


def _serialize_result(opportunity: Opportunity, query: str = "", relevance: float | None = None) -> dict[str, Any]:
    return {
        "id": str(opportunity.id),
        "opportunity_id": str(opportunity.id),
        "title": opportunity.title,
        "institution": opportunity.institution,
        "country": opportunity.country,
        "region": opportunity.region,
        "category": _enum(opportunity.category),
        "score": opportunity.score,
        "status": _enum(opportunity.status),
        "summary": opportunity.ai_summary,
        "ai_summary": opportunity.ai_summary,
        "snippet": _make_snippet(opportunity, query),
        "relevance_score": round(relevance, 4) if relevance is not None else None,
        "deadline": opportunity.deadline.isoformat() if opportunity.deadline else None,
        "source_url": opportunity.source_url,
    }


def _keyword_relevance(opportunity: Opportunity, query: str) -> float:
    """Cheap relevance heuristic for the ILIKE fallback path."""
    needle = (query or "").strip().lower()
    if not needle:
        return 0.7
    if needle in (opportunity.title or "").lower():
        return 1.0
    if needle in (opportunity.institution or "").lower():
        return 0.85
    return 0.7


def _apply_search_filters(stmt, filters: dict[str, Any] | None):
    """Apply optional region/category/status filters to a search query."""
    if not filters:
        return stmt
    regions = filters.get("regions") or []
    categories = filters.get("categories") or []
    status = filters.get("status") or []
    if regions:
        stmt = stmt.where(Opportunity.region.in_(regions))
    if categories:
        stmt = stmt.where(Opportunity.category.in_(categories))
    if status:
        status = status if isinstance(status, (list, tuple, set)) else [status]
        stmt = stmt.where(Opportunity.status.in_(list(status)))
    return stmt


# --------------------------------------------------------------------------- #
# Keyword search (pg_trgm word_similarity ranking, ILIKE fallback)
# --------------------------------------------------------------------------- #
async def keyword_search(
    db: AsyncSession, query: str, page: int, page_size: int, filters: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Trigram fuzzy + ranked keyword search; falls back to ILIKE if pg_trgm is missing."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size
    q = (query or "").strip()
    like = f"%{q}%"

    try:
        rank = func.greatest(
            func.word_similarity(q, Opportunity.title),
            func.word_similarity(q, func.coalesce(Opportunity.ai_summary, "")),
            func.word_similarity(q, func.coalesce(Opportunity.institution, "")),
        )
        stmt = select(Opportunity, rank.label("rank")).where(
            or_(
                Opportunity.title.ilike(like),
                Opportunity.institution.ilike(like),
                Opportunity.ai_summary.ilike(like),
                rank > 0.2,
            )
        )
        stmt = _apply_search_filters(stmt, filters)
        total = int(await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
        rows = (
            await db.execute(stmt.order_by(rank.desc(), Opportunity.score.desc()).offset(offset).limit(page_size))
        ).all()
        items = [_serialize_result(opp, query, float(r) if r is not None else None) for opp, r in rows]
        return items, total
    except Exception as exc:  # noqa: BLE001 - pg_trgm unavailable -> ILIKE fallback
        logger.warning("pg_trgm keyword search failed, falling back to ILIKE: %s", exc)
        await db.rollback()
        return await _keyword_ilike(db, query, page, page_size, filters)


async def _keyword_ilike(
    db: AsyncSession, query: str, page: int, page_size: int, filters: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], int]:
    offset = (max(page, 1) - 1) * max(page_size, 1)
    like = f"%{query.strip()}%"
    base = select(Opportunity).where(
        or_(
            Opportunity.title.ilike(like),
            Opportunity.institution.ilike(like),
            Opportunity.ai_summary.ilike(like),
        )
    )
    base = _apply_search_filters(base, filters)
    total = int(await db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0)
    rows = (
        await db.execute(base.order_by(Opportunity.score.desc(), Opportunity.created_at.desc()).offset(offset).limit(max(page_size, 1)))
    ).scalars().all()
    items = [_serialize_result(o, query, _keyword_relevance(o, query)) for o in rows]
    return items, total


# --------------------------------------------------------------------------- #
# Semantic search (opportunity vectors + document-chunk vectors, merged)
# --------------------------------------------------------------------------- #
async def _opportunity_semantic(db, query_vector, filters, limit) -> dict[str, tuple[Opportunity, float]]:
    distance = Opportunity.embedding.cosine_distance(query_vector)
    stmt = select(Opportunity, distance.label("d")).where(Opportunity.embedding.isnot(None))
    stmt = _apply_search_filters(stmt, filters)
    rows = (await db.execute(stmt.order_by(distance).limit(limit))).all()
    return {str(opp.id): (opp, max(0.0, 1.0 - float(d))) for opp, d in rows}


async def _document_semantic(db, query_vector, filters, limit) -> dict[str, tuple[Opportunity, float]]:
    """Find opportunities whose source-document chunks are similar to the query."""
    min_dist = func.min(DocumentEmbedding.embedding.cosine_distance(query_vector))
    sub = (
        select(DocumentEmbedding.document_id, min_dist.label("dist"))
        .where(DocumentEmbedding.embedding.isnot(None))
        .group_by(DocumentEmbedding.document_id)
        .order_by(min_dist)
        .limit(limit)
    )
    rows = (await db.execute(sub)).all()
    if not rows:
        return {}
    dist_by_doc = {doc_id: float(dist) for doc_id, dist in rows}

    stmt = select(Opportunity).where(Opportunity.document_id.in_(list(dist_by_doc.keys())))
    stmt = _apply_search_filters(stmt, filters)
    opps = (await db.execute(stmt)).scalars().all()
    out: dict[str, tuple[Opportunity, float]] = {}
    for opp in opps:
        dist = dist_by_doc.get(opp.document_id)
        if dist is not None:
            out[str(opp.id)] = (opp, max(0.0, 1.0 - dist))
    return out


async def semantic_search(
    db: AsyncSession, query: str, page: int, page_size: int, filters: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Vector search over opportunity embeddings AND document-chunk embeddings (merged).

    Falls back to keyword search if the embedding resource is unavailable or nothing is embedded.
    """
    page = max(page, 1)
    page_size = max(page_size, 1)

    try:
        query_vector = await get_embedding(query.strip())
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        logger.warning("Semantic search falling back to keyword (embedding unavailable): %s", exc)
        return await keyword_search(db, query, page, page_size, filters)

    opp_map = await _opportunity_semantic(db, query_vector, filters, _POOL)
    doc_map = await _document_semantic(db, query_vector, filters, _POOL)

    merged: dict[str, tuple[Opportunity, float]] = dict(opp_map)
    for oid, (opp, rel) in doc_map.items():
        if oid in merged:
            merged[oid] = (merged[oid][0], max(merged[oid][1], rel))
        else:
            merged[oid] = (opp, rel)

    if not merged:
        return await keyword_search(db, query, page, page_size, filters)

    ordered = sorted(merged.values(), key=lambda pair: pair[1], reverse=True)
    total = len(ordered)
    offset = (page - 1) * page_size
    items = [_serialize_result(opp, query, rel) for opp, rel in ordered[offset:offset + page_size]]
    return items, total


# --------------------------------------------------------------------------- #
# Hybrid search (reciprocal-rank fusion of keyword + semantic)
# --------------------------------------------------------------------------- #
async def hybrid_search(
    db: AsyncSession, query: str, page: int, page_size: int, filters: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], int]:
    page = max(page, 1)
    page_size = max(page_size, 1)

    keyword_hits, _ = await keyword_search(db, query, 1, _POOL // 2, filters)
    semantic_hits, _ = await semantic_search(db, query, 1, _POOL // 2, filters)

    k = 60  # RRF constant
    scores: dict[str, float] = {}
    pool: dict[str, dict[str, Any]] = {}
    for ranking in (keyword_hits, semantic_hits):
        for rank, item in enumerate(ranking):
            key = item["id"]
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            pool.setdefault(key, item)

    if not pool:
        return [], 0

    ordered = sorted(pool.values(), key=lambda item: scores[item["id"]], reverse=True)
    total = len(ordered)
    top = max(scores.values())
    offset = (page - 1) * page_size
    results: list[dict[str, Any]] = []
    for item in ordered[offset:offset + page_size]:
        merged_item = dict(item)
        merged_item["relevance_score"] = round(scores[item["id"]] / top, 4) if top else None
        results.append(merged_item)
    return results, total
