from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.core.database import AsyncSession
from app.core.exceptions import NotFoundException
from app.models.source import CrawlFrequency, Source

logger = logging.getLogger(__name__)

# How long a source of each frequency tier stays "fresh" before it is due again.
_FREQUENCY_INTERVAL = {
    CrawlFrequency.HOURLY: timedelta(hours=1),
    CrawlFrequency.DAILY: timedelta(days=1),
    CrawlFrequency.WEEKLY: timedelta(weeks=1),
    CrawlFrequency.MONTHLY: timedelta(days=30),
}
# Crawl once ~90% of the interval has elapsed, so a beat that fires a little early
# (scheduler jitter) still picks the source up instead of skipping a whole cycle.
_DUE_TOLERANCE = 0.9


def _is_due(last_crawl_at: datetime | None, frequency: CrawlFrequency, now: datetime) -> bool:
    """True if a source of ``frequency`` last crawled at ``last_crawl_at`` should re-crawl."""
    interval = _FREQUENCY_INTERVAL.get(frequency)
    if interval is None or last_crawl_at is None:
        return True
    if last_crawl_at.tzinfo is None:  # stored naive -> treat as UTC (mirrors the scoring fix)
        last_crawl_at = last_crawl_at.replace(tzinfo=timezone.utc)
    return (now - last_crawl_at) >= interval * _DUE_TOLERANCE


async def list_sources(db: AsyncSession, page: int, page_size: int) -> tuple[list[Source], int]:
    """Return paginated sources and total count."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    total = await db.scalar(select(func.count()).select_from(Source))
    result = await db.execute(select(Source).order_by(Source.created_at.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total or 0)


async def list_due_sources(
    db: AsyncSession, frequency: str, *, now: datetime | None = None
) -> list[Source]:
    """Active sources of the given frequency tier that are due for a re-crawl.

    Used by the scheduled ``crawl_sources`` Celery task so each tier honors its own
    cadence (FR-SOURCE-002 / FR-CRAWL-001). Returns an empty list for an unknown tier.
    """
    try:
        freq = CrawlFrequency(frequency)
    except ValueError:
        logger.warning("Unknown crawl frequency %r; nothing to crawl", frequency)
        return []
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(Source).where(Source.is_active.is_(True), Source.frequency == freq)
    )
    return [s for s in result.scalars().all() if _is_due(s.last_crawl_at, freq, now)]


async def create_source(db: AsyncSession, source_data: dict[str, Any]) -> Source:
    """Create a source record."""
    source = Source(**dict(source_data))
    try:
        db.add(source)
        await db.commit()
        await db.refresh(source)
        return source
    except Exception:
        await db.rollback()
        logger.exception("Failed to create source")
        raise


async def get_source(db: AsyncSession, source_id: Any) -> Source:
    """Return a source by identifier."""
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise NotFoundException("Source not found")
    return source


async def update_source(db: AsyncSession, source_id: Any, update_data: dict[str, Any]) -> Source:
    """Update a source record."""
    source = await get_source(db, source_id)
    for field, value in dict(update_data).items():
        if hasattr(source, field):
            setattr(source, field, value)

    try:
        await db.commit()
        await db.refresh(source)
        return source
    except Exception:
        await db.rollback()
        logger.exception("Failed to update source", extra={"source_id": str(source_id)})
        raise
