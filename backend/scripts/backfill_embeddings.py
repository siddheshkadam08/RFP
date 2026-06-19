"""Backfill semantic-search embeddings.

Embeds (1) opportunities that have no vector yet, and (2) document bodies that have
no ``document_embeddings`` chunks yet (for document-corpus semantic search).

Run from the backend/ directory with the venv active::

    python -m scripts.backfill_embeddings
"""
from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.document import Document, DocumentEmbedding  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402
from app.services.ai_service import get_embedding  # noqa: E402
from app.services.ingestion_service import _MAX_CHUNKS, _chunk_text  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_embeddings")


async def backfill_opportunities(db) -> None:
    rows = (await db.execute(select(Opportunity).where(Opportunity.embedding.is_(None)))).scalars().all()
    logger.info("Opportunities needing embeddings: %s", len(rows))
    done = 0
    for opp in rows:
        text = f"{opp.title}\n{opp.ai_summary or ''}".strip()
        try:
            opp.embedding = await get_embedding(text)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding failed for %s: %s", opp.id, exc)
    await db.commit()
    logger.info("Embedded %s/%s opportunities", done, len(rows))


async def backfill_documents(db) -> None:
    embedded_doc_ids = select(DocumentEmbedding.document_id).distinct().scalar_subquery()
    docs = (await db.execute(select(Document).where(Document.id.not_in(embedded_doc_ids)))).scalars().all()
    logger.info("Documents needing chunk embeddings: %s", len(docs))
    total_chunks = 0
    for doc in docs:
        chunks = _chunk_text(doc.content_text)[:_MAX_CHUNKS]
        for index, chunk in enumerate(chunks):
            try:
                vector = await get_embedding(chunk)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chunk embedding failed (doc %s, chunk %s): %s", doc.id, index, exc)
                continue
            db.add(
                DocumentEmbedding(document_id=doc.id, chunk_index=index, chunk_text=chunk, embedding=vector)
            )
            total_chunks += 1
        await db.commit()
    logger.info("Embedded %s chunks across %s documents", total_chunks, len(docs))


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await backfill_opportunities(db)
        await backfill_documents(db)


if __name__ == "__main__":
    asyncio.run(main())
