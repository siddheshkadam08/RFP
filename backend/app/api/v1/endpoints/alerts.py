from __future__ import annotations

"""Alert endpoints."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, get_current_user
from app.models.alert import Alert

_ALERT_TITLES = {
    "new_opportunity": "New opportunity",
    "high_priority": "High-priority opportunity",
    "deadline_approaching": "Deadline approaching",
    "region_trend": "Regional trend",
    "score_spike": "Score spike",
    "crawl_failure": "Crawl failure",
}

try:
    from app.schemas.alert import AlertUpdate as AlertStatusUpdateRequest
except ImportError:
    class AlertStatusUpdateRequest(BaseModel):
        """Fallback alert status schema until app.schemas.alert is available."""

        model_config = ConfigDict(extra="allow")

        is_read: bool

try:
    from app.services import alert_service
except ImportError:
    alert_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _get_service() -> Any:
    """Return the alert service or raise a service unavailable error."""
    if alert_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Alert service is not available",
        )
    return alert_service


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _serialize_alert(alert: Any) -> Any:
    """Convert an Alert ORM row into the dict the frontend expects (and avoid the
    raw-ORM Pydantic 500). Non-ORM values pass through unchanged."""
    if not isinstance(alert, Alert):
        return alert
    alert_type = _enum(alert.alert_type)
    return {
        "id": str(alert.id),
        "type": alert_type,
        "title": _ALERT_TITLES.get(alert_type, str(alert_type).replace("_", " ").title()),
        "message": alert.message,
        "severity": _enum(alert.severity),
        "opportunity_id": str(alert.opportunity_id) if alert.opportunity_id else None,
        "is_read": alert.is_read,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


@router.get("/", status_code=status.HTTP_200_OK)
async def list_alerts(
    current_user: CurrentUser,
    db: DBSession,
    unread: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List alerts for the authenticated user with optional unread filtering."""
    try:
        service = _get_service()
        try:
            result = await service.list_user_alerts(
                db=db,
                user_id=current_user.sub,
                unread=unread,
                page=page,
                page_size=page_size,
            )
        except (AttributeError, TypeError):
            result = await service.list_alerts(
                db=db,
                user_id=current_user.sub,
                unread_only=bool(unread),
                page=page,
                page_size=page_size,
            )
        items, total = result if isinstance(result, tuple) else (result, None)
        items = [_serialize_alert(item) for item in items]
        return _success_response(items, meta={"page": page, "page_size": page_size, "unread": unread, "total": total})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list alerts")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list alerts") from exc


@router.get("/unread-count", status_code=status.HTTP_200_OK)
async def unread_count(current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return the count of unread alerts for the sidebar badge."""
    try:
        service = _get_service()
        count = await service.unread_count(db=db, user_id=current_user.sub)
        return _success_response({"count": int(count)})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to count unread alerts")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to count unread alerts") from exc


@router.patch("/{alert_id}", status_code=status.HTTP_200_OK)
async def update_alert(
    alert_id: UUID,
    payload: AlertStatusUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> dict[str, Any]:
    """Mark a single alert as read or unread."""
    try:
        service = _get_service()
        try:
            result = await service.update_alert_status(
                db=db,
                alert_id=alert_id,
                user_id=current_user.sub,
                is_read=payload.is_read,
            )
        except (AttributeError, TypeError):
            result = await service.mark_alert_read(db=db, alert_id=alert_id, is_read=payload.is_read)
        return _success_response(_serialize_alert(result))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update alert %s", alert_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update alert") from exc


@router.post("/mark-all-read", status_code=status.HTTP_200_OK)
async def mark_all_read(current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Mark all alerts for the authenticated user as read."""
    try:
        service = _get_service()
        try:
            result = await service.mark_all_alerts_read(db=db, user_id=current_user.sub)
        except (AttributeError, TypeError):
            result = await service.mark_all_read(db=db, user_id=current_user.sub)
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to mark all alerts as read")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark all alerts as read",
        ) from exc
