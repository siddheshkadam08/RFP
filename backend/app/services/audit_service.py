from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select

from app.core.database import AsyncSession
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    user_id: Any,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, Any] | None,
    ip_address: str | None,
) -> AuditLog:
    """Create an audit log entry."""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    try:
        db.add(audit_log)
        await db.commit()
        await db.refresh(audit_log)
        return audit_log
    except Exception:
        await db.rollback()
        logger.exception("Failed to write audit log", extra={"action": action, "resource_type": resource_type})
        raise


async def log_action_safe(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    user_id: Any | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Best-effort audit write (FR-AUTH-005): never raises, so it can't break the audited request.

    Call this *after* the audited mutation has committed — it runs as its own transaction, so a
    failed audit insert rolls back only itself and is downgraded to a warning.
    """
    try:
        await log_action(db, user_id, action, resource_type, resource_id, details, ip_address)
    except Exception:  # noqa: BLE001 - auditing must not break the main flow
        logger.warning("Audit log write failed (action=%s resource=%s)", action, resource_type)


def client_ip(request: Any) -> str | None:
    """Best-effort client IP from a FastAPI/Starlette request, for audit records."""
    client = getattr(request, "client", None)
    return getattr(client, "host", None) if client is not None else None


async def list_audit_logs(
    db: AsyncSession,
    page: int,
    page_size: int,
    user_id: Any | None = None,
    action: str | None = None,
) -> tuple[list[AuditLog], int]:
    """Return paginated audit logs with optional filters."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)

    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    result = await db.execute(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total or 0)
