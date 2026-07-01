from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSession
from app.models.document import Document

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Text sanitisation (BUG-1: null bytes crash PostgreSQL TIMESTAMPTZ inserts)
# --------------------------------------------------------------------------- #
_CONTROL_CHARS_TABLE = dict.fromkeys(range(0x20), None)  # strip C0 control chars
_CONTROL_CHARS_TABLE[0x00] = None  # explicit null-byte guard (PostgreSQL UTF-8 rejects 0x00)
# Keep TAB (0x09), LF (0x0A), CR (0x0D) — they are valid in text columns
for _keep in (0x09, 0x0A, 0x0D):
    _CONTROL_CHARS_TABLE.pop(_keep, None)


def sanitize_text(value: str | None) -> str | None:
    """Remove null bytes and non-printable control characters from a string.

    PostgreSQL rejects U+0000 (null byte) in all text/varchar columns, raising
    ``CharacterNotInRepertoireError: invalid byte sequence UTF8: 0x00``.  This
    helper must be applied to every user-supplied or LLM-generated string before
    any DB INSERT or UPDATE.

    Returns ``None`` unchanged so callers do not need to guard for ``None``.
    """
    if value is None:
        return None
    # Fast-path: skip the translate() overhead when no control chars are present
    if "\x00" not in value and not any(ch < "\x20" and ch not in "\t\n\r" for ch in value):
        return value
    return value.translate(_CONTROL_CHARS_TABLE)


async def create_document(db: AsyncSession, document_data: dict[str, Any]) -> Document:
    """Create a document record, sanitising all text fields to strip null bytes."""
    safe: dict[str, Any] = dict(document_data)
    for field in ("title", "content_text", "url"):
        if field in safe:
            safe[field] = sanitize_text(safe[field])
    document = Document(**safe)
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
