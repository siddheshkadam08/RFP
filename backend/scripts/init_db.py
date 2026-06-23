from __future__ import annotations

"""Phase 1 bootstrap: create database tables from the models and seed an admin user.

Run from the ``backend/`` directory with the virtualenv active::

    python -m scripts.init_db

Phase 1 deliberately skips Alembic (deferred to Phase 2). Instead of migrations, this
script creates the schema directly from the SQLAlchemy models' metadata via
``Base.metadata.create_all`` and seeds the first admin user so login is possible.

It is safe to re-run:
* ``create_all`` only creates tables that are missing.
* The admin user is created only if one with the same email does not already exist.

Admin credentials are read from the environment (loaded from ``backend/.env``):
``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` / ``ADMIN_NAME``. Defaults are used if unset.
"""

import asyncio
import logging
import os

# Load backend/.env BEFORE importing app modules so both pydantic Settings and the
# plain ADMIN_* lookups below see the configured values.
from dotenv import load_dotenv

load_dotenv()

import app.models  # noqa: E402, F401 - importing registers every table on Base.metadata
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.services import auth_service  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("init_db")

DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"
DEFAULT_ADMIN_NAME = "Administrator"


async def create_tables() -> None:
    """Create any missing tables directly from the model metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables are ready (created any that were missing).")


async def patch_schema() -> None:
    """Apply idempotent column tweaks that ``create_all`` cannot do on its own.

    ``Base.metadata.create_all`` only creates *missing* tables; it never alters an
    existing one. These statements bring an already-created ``sources`` table up to
    date (add ``domain``, allow a null ``country``) and are safe to re-run.
    """
    from sqlalchemy import text

    from app.core.config import settings

    statements = (
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS domain VARCHAR(100)",
        "ALTER TABLE sources ALTER COLUMN country DROP NOT NULL",
        # pgvector: enable the extension, then add the opportunity embedding column.
        "CREATE EXTENSION IF NOT EXISTS vector",
        f"ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS embedding vector({settings.EMBEDDING_DIM})",
        # pg_trgm: fuzzy/ranked keyword search (FR-SEARCH-001).
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS idx_opp_title_trgm ON opportunities USING gin (title gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_opp_summary_trgm ON opportunities USING gin (ai_summary gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_opp_inst_trgm ON opportunities USING gin (institution gin_trgm_ops)",
        # HNSW cosine index for document-chunk semantic search (table made by create_all).
        "CREATE INDEX IF NOT EXISTS idx_docemb_hnsw ON document_embeddings USING hnsw (embedding vector_cosine_ops)",
        # New alert type for crawl-failure notifications (DB enum stores member names).
        "ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'CRAWL_FAILURE'",
    )
    # Each statement gets its own transaction: a failure on Postgres aborts the
    # whole transaction, which would otherwise cascade to the next statement.
    for statement in statements:
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(statement)
        except Exception as exc:  # noqa: BLE001 - best-effort, idempotent patch
            logger.warning("Schema patch skipped (%s): %s", statement, exc)
    logger.info("Schema patches applied (domain column, nullable country).")


async def seed_admin() -> None:
    """Create the first admin user if one does not already exist."""
    email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower()
    password = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    full_name = os.getenv("ADMIN_NAME", DEFAULT_ADMIN_NAME)

    async with AsyncSessionLocal() as db:
        existing = await auth_service.get_user_by_email(db, email)
        if existing is not None:
            logger.info("Admin user already exists (%s); skipping creation.", email)
            return

        await auth_service.create_user(
            db,
            {
                "email": email,
                "full_name": full_name,
                "password": password,
                "role": UserRole.ADMIN,
                "is_active": True,
            },
        )
        logger.info("Created admin user: %s (role=admin)", email)


async def main() -> None:
    try:
        await create_tables()
        await patch_schema()
        await seed_admin()
    finally:
        await engine.dispose()
    logger.info("Bootstrap complete. You can now start the API and log in.")


if __name__ == "__main__":
    asyncio.run(main())
