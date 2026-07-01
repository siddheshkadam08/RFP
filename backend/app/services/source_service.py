from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSession
from app.core.exceptions import NotFoundException
from app.models.source import Source

logger = logging.getLogger(__name__)


def _source_query() -> Any:
    """Base SELECT for Source with all relationships eagerly loaded.

    ``source_type`` is a plain mapped column (not a relationship) so it is
    always loaded.  The ``documents`` relationship IS lazy by default — eager
    loading it here prevents MissingGreenlet errors when the ORM object is used
    after the session that fetched it has committed or been closed.
    """
    return select(Source).options(selectinload(Source.documents))


async def list_sources(db: AsyncSession, page: int, page_size: int) -> tuple[list[Source], int]:
    """Return paginated sources and total count."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    total = await db.scalar(select(func.count()).select_from(Source))
    result = await db.execute(
        _source_query().order_by(Source.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(result.scalars().all()), int(total or 0)


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
    """Return a source by identifier, with relationships eagerly loaded."""
    result = await db.execute(_source_query().where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise NotFoundException("Source not found")
    return source


async def update_source(db: AsyncSession, source_id: Any, update_data: dict[str, Any]) -> Source:
    """Update a source record, returning the refreshed object with eager-loaded relationships."""
    source = await get_source(db, source_id)
    for field, value in dict(update_data).items():
        if hasattr(source, field):
            setattr(source, field, value)

    try:
        await db.commit()
        # Re-fetch with eager loads — db.refresh() does not re-apply selectinload options
        return await get_source(db, source_id)
    except Exception:
        await db.rollback()
        logger.exception("Failed to update source", extra={"source_id": str(source_id)})
        raise
