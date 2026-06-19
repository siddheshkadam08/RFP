from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSession
from app.models.document import Document

logger = logging.getLogger(__name__)


async def create_document(db: AsyncSession, document_data: dict[str, Any]) -> Document:
    """Create a document record."""
    document = Document(**dict(document_data))
    try:
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document
    except Exception:
        await db.rollback()
        logger.exception("Failed to create document")
        raise


async def get_document_by_hash(db: AsyncSession, content_hash: str) -> Document | None:
    """Return a document with the given content hash, if one already exists.

    Used for crawl de-duplication: identical page text yields the same SHA-256
    hash, so we skip re-processing content we have already ingested.
    """
    result = await db.execute(select(Document).where(Document.content_hash == content_hash))
    return result.scalar_one_or_none()


async def get_document(db: AsyncSession, document_id: Any) -> Document | None:
    """Return a document by identifier, or None if missing."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()
