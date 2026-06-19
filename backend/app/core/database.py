from __future__ import annotations

"""Database configuration and session management."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""


def _build_async_database_url(database_url: str) -> str:
    """Ensure PostgreSQL URLs use the asyncpg driver."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


DATABASE_URL = _build_async_database_url(settings.DATABASE_URL)

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Note: pgvector's SQLAlchemy ``Vector`` type handles asyncpg serialization on its own
# (as text). Do NOT also call pgvector.asyncpg.register_vector — its binary codec
# conflicts with the type's string bind processor.


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for request-scoped dependencies."""
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        logger.exception("Database session failed; rolling back transaction")
        await session.rollback()
        raise
    finally:
        await session.close()
