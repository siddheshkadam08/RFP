from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.user import User


class AlertType(str, Enum):
    NEW_OPPORTUNITY = "new_opportunity"
    HIGH_PRIORITY = "high_priority"
    DEADLINE_APPROACHING = "deadline_approaching"
    REGION_TREND = "region_trend"
    SCORE_SPIKE = "score_spike"
    CRAWL_FAILURE = "crawl_failure"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    alert_type: Mapped[AlertType] = mapped_column(SAEnum(AlertType, name="alert_type"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(SAEnum(AlertSeverity, name="alert_severity"), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="alerts")
    opportunity: Mapped[Opportunity | None] = relationship(back_populates="alerts")
