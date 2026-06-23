from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, update

from app.core.database import AsyncSession
from app.core.exceptions import NotFoundException
from app.models.alert import Alert, AlertSeverity, AlertType
from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)

_HIGH_SCORE = 80  # spec scoring threshold: >=80 High
_DEADLINE_WINDOW_DAYS = 14  # spec deadline alert windows: 14 / 7 / 1 days


def _coerce_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _visible(user_uuid: UUID):
    """Alerts a user can see: their own + system-wide (user_id IS NULL) alerts."""
    return or_(Alert.user_id == user_uuid, Alert.user_id.is_(None))


def _severity_for_score(score: int) -> AlertSeverity:
    if score >= _HIGH_SCORE:
        return AlertSeverity.HIGH
    if score >= 50:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def _severity_for_deadline(days: int) -> AlertSeverity:
    if days <= 1:
        return AlertSeverity.CRITICAL
    if days <= 7:
        return AlertSeverity.HIGH
    return AlertSeverity.MEDIUM


def _days_until(deadline: datetime | None) -> int | None:
    if deadline is None:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - datetime.now(timezone.utc)).days


async def list_alerts(
    db: AsyncSession,
    user_id: Any,
    unread_only: bool,
    page: int,
    page_size: int,
) -> tuple[list[Alert], int]:
    """Return paginated alerts visible to a user (their own + system-wide)."""
    user_uuid = _coerce_uuid(user_id)
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    stmt = select(Alert).where(_visible(user_uuid))
    if unread_only:
        stmt = stmt.where(Alert.is_read.is_(False))

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    result = await db.execute(stmt.order_by(Alert.created_at.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total or 0)


async def unread_count(db: AsyncSession, user_id: Any) -> int:
    """Number of unread alerts visible to a user (for the sidebar badge)."""
    user_uuid = _coerce_uuid(user_id)
    stmt = select(func.count()).select_from(Alert).where(_visible(user_uuid), Alert.is_read.is_(False))
    return int(await db.scalar(stmt) or 0)


async def mark_alert_read(db: AsyncSession, alert_id: Any, is_read: bool) -> Alert:
    """Mark a single alert read or unread."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundException("Alert not found")

    alert.is_read = is_read
    await db.commit()
    await db.refresh(alert)
    return alert


async def mark_all_read(db: AsyncSession, user_id: Any) -> int:
    """Mark all unread alerts visible to a user as read."""
    user_uuid = _coerce_uuid(user_id)
    result = await db.execute(
        update(Alert).where(_visible(user_uuid), Alert.is_read.is_(False)).values(is_read=True)
    )
    await db.commit()
    return int(result.rowcount or 0)


async def create_alert(db: AsyncSession, alert_data: dict[str, Any]) -> Alert:
    """Create a new alert record."""
    alert = Alert(**dict(alert_data))
    try:
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
        return alert
    except Exception:
        await db.rollback()
        logger.exception("Failed to create alert")
        raise


# --------------------------------------------------------------------------- #
# Alert emission (the ingestion graph's emit_alerts step + crawl failures).
# All emitters are best-effort: a failure here must never break ingestion.
# --------------------------------------------------------------------------- #
async def _alert_exists(db: AsyncSession, opportunity_id: Any, alert_type: AlertType) -> bool:
    stmt = select(func.count()).select_from(Alert).where(
        Alert.opportunity_id == opportunity_id, Alert.alert_type == alert_type
    )
    return int(await db.scalar(stmt) or 0) > 0


async def emit_opportunity_alerts(db: AsyncSession, opportunity_id: Any) -> int:
    """Create new-opportunity / high-priority / deadline alerts for an opportunity (deduped)."""
    try:
        opportunity_id = _coerce_uuid(opportunity_id)
        opp = (
            await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
        ).scalar_one_or_none()
        if opp is None:
            return 0

        score = opp.score or 0
        title = opp.title or "Opportunity"
        region = opp.region or "Unknown region"
        created = 0

        if not await _alert_exists(db, opportunity_id, AlertType.NEW_OPPORTUNITY):
            db.add(Alert(
                opportunity_id=opportunity_id,
                alert_type=AlertType.NEW_OPPORTUNITY,
                severity=_severity_for_score(score),
                message=f"New opportunity detected: {title} ({region}, score {score}).",
                is_read=False,
            ))
            created += 1

        if score >= _HIGH_SCORE and not await _alert_exists(db, opportunity_id, AlertType.HIGH_PRIORITY):
            db.add(Alert(
                opportunity_id=opportunity_id,
                alert_type=AlertType.HIGH_PRIORITY,
                severity=AlertSeverity.HIGH,
                message=f"High-priority opportunity (score {score}): {title}.",
                is_read=False,
            ))
            created += 1

        days = _days_until(opp.deadline)
        if days is not None and 0 <= days <= _DEADLINE_WINDOW_DAYS and not await _alert_exists(
            db, opportunity_id, AlertType.DEADLINE_APPROACHING
        ):
            db.add(Alert(
                opportunity_id=opportunity_id,
                alert_type=AlertType.DEADLINE_APPROACHING,
                severity=_severity_for_deadline(days),
                message=f"Deadline in {days} day(s): {title}.",
                is_read=False,
            ))
            created += 1

        if created:
            await db.commit()
        return created
    except Exception as exc:  # noqa: BLE001 - never break ingestion
        logger.warning("emit_opportunity_alerts failed for %s: %s", opportunity_id, exc)
        await db.rollback()
        return 0


async def emit_crawl_failure_alert(db: AsyncSession, url: str, error: Any) -> bool:
    """Create a system-wide crawl-failure alert (FR-NOTIFY-002)."""
    try:
        db.add(Alert(
            alert_type=AlertType.CRAWL_FAILURE,
            severity=AlertSeverity.HIGH,
            message=f"Crawl failed for {url}: {str(error)[:180]}",
            is_read=False,
        ))
        await db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("emit_crawl_failure_alert failed: %s", exc)
        await db.rollback()
        return False
