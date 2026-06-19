from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, Float, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.geo import SOURCE_REGIONS  # noqa: F401 - re-exported for the sources endpoint

if TYPE_CHECKING:
    from app.models.document import Document


class SourceType(str, Enum):
    REGULATOR_WEBSITE = "regulator_website"
    TENDER_PORTAL = "tender_portal"
    PROCUREMENT_SYSTEM = "procurement_system"
    GOVERNMENT_WEBSITE = "government_website"
    PRESS_RELEASE = "press_release"
    RSS_FEED = "rss_feed"
    PDF = "pdf"
    ANNUAL_REPORT = "annual_report"
    NEWS_FEED = "news_feed"
    FUNDING_PORTAL = "funding_portal"
    OTHER = "other"


class CrawlFrequency(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SourceDomain(str, Enum):
    """Business domain a source covers, aligned with the regulator-type taxonomy."""

    CENTRAL_BANK = "central_bank"
    DEPOSIT_INSURER = "deposit_insurer"
    BUSINESS_REGISTRY = "business_registry"
    CAPITAL_MARKET = "capital_market"
    STOCK_EXCHANGE = "stock_exchange"
    TAX_AUTHORITY = "tax_authority"
    STATISTICAL_BODY = "statistical_body"
    LOCAL_GOVERNMENT = "local_government"
    OTHER = "other"


# SOURCE_REGIONS now lives in app.core.geo (alongside the country<->region data)
# and is imported above so existing ``from app.models.source import SOURCE_REGIONS``
# call sites keep working.


class CrawlStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type"), nullable=False)
    frequency: Mapped[CrawlFrequency] = mapped_column(SAEnum(CrawlFrequency, name="crawl_frequency"), nullable=False)
    # Stored as a plain string (validated against SourceDomain at the API boundary)
    # to avoid a Postgres enum-type migration; nullable for backwards compatibility.
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_crawl_status: Mapped[CrawlStatus] = mapped_column(
        SAEnum(CrawlStatus, name="crawl_status"), default=CrawlStatus.PENDING, nullable=False
    )
    success_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    documents: Mapped[list[Document]] = relationship(back_populates="source")
