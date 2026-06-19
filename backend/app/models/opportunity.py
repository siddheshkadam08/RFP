from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.comment import Comment
    from app.models.document import Document
    from app.models.user import User


class OpportunityCategory(str, Enum):
    SUPTECH = "suptech"
    REGTECH = "regtech"
    ANALYTICS = "analytics"
    RISK = "risk"
    TAXONOMY = "taxonomy"
    REPORTING = "reporting"
    DEPOSIT_INSURANCE = "deposit_insurance"
    DATA_COLLECTION = "data_collection"
    WORKFLOW = "workflow"
    VALIDATION = "validation"


class OpportunityStatus(str, Enum):
    SIGNAL_DETECTED = "signal_detected"
    UNDER_REVIEW = "under_review"
    QUALIFIED = "qualified"
    ACTIVE = "active"
    PURSUING = "pursuing"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
    ARCHIVED = "archived"


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (CheckConstraint("score >= 0 AND score <= 100", name="ck_opportunities_score_range"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[OpportunityCategory] = mapped_column(
        SAEnum(OpportunityCategory, name="opportunity_category"), nullable=False
    )
    standards: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    budget: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[OpportunityStatus] = mapped_column(
        SAEnum(OpportunityStatus, name="opportunity_status"), default=OpportunityStatus.SIGNAL_DETECTED, nullable=False
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    ai_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Semantic-search vector (title + AI summary), null until embedded. Dim must match
    # the embedding model (text-embedding-3-small -> 1536). See app.core.config.EMBEDDING_DIM.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    document: Mapped[Document | None] = relationship(back_populates="opportunities")
    owner: Mapped[User | None] = relationship(back_populates="owned_opportunities")
    comments: Mapped[list[Comment]] = relationship(back_populates="opportunity")
    alerts: Mapped[list[Alert]] = relationship(back_populates="opportunity")
