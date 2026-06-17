from __future__ import annotations

"""Reporting endpoints."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, get_current_user
from app.models.report import ReportType

try:
    from app.schemas.report import ReportGenerateRequest
except ImportError:
    class ReportGenerateRequest(BaseModel):
        """Fallback report generation schema until app.schemas.report is available."""

        model_config = ConfigDict(extra="allow", use_enum_values=True)

        title: str = Field(min_length=1, max_length=255)
        report_type: ReportType
        parameters: dict[str, Any] = Field(default_factory=dict)

try:
    from app.services import report_service
except ImportError:
    report_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _get_service() -> Any:
    """Return the report service or raise a service unavailable error."""
    if report_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report service is not available",
        )
    return report_service


@router.get("/", status_code=status.HTTP_200_OK)
async def list_reports(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List generated reports with pagination."""
    try:
        service = _get_service()
        try:
            result = await service.list_reports(db=db, user_id=current_user.sub, page=page, page_size=page_size)
        except TypeError:
            result = await service.list_reports(db=db, page=page, page_size=page_size)
        items, total = result if isinstance(result, tuple) else (result, None)
        return _success_response(items, meta={"page": page, "page_size": page_size, "total": total})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list reports")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list reports") from exc


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_report(payload: ReportGenerateRequest, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Queue or generate a report for the authenticated user."""
    try:
        service = _get_service()
        payload_data = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)
        if hasattr(service, "generate_report"):
            try:
                result = await service.generate_report(db=db, report_data=payload, requested_by=current_user.sub)
            except TypeError:
                report_type = payload_data.get("report_type") or payload_data.get("type")
                parameters = payload_data.get("parameters") or {}
                result = await service.generate_report(
                    db=db,
                    report_type=report_type,
                    parameters=parameters,
                    user_id=current_user.sub,
                )
        else:
            result = payload_data
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate report")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate report") from exc


@router.get("/{report_id}/download", status_code=status.HTTP_200_OK)
async def download_report(report_id: UUID, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return download information for a generated report file."""
    try:
        service = _get_service()
        if hasattr(service, "get_report_download"):
            result = await service.get_report_download(db=db, report_id=report_id, requested_by=current_user.sub)
        else:
            report = await service.get_report(db=db, report_id=report_id)
            result = {
                "report_id": str(report.id),
                "title": report.title,
                "status": report.status.value if hasattr(report.status, "value") else str(report.status),
                "file_path": report.file_path,
            }
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch download for report %s", report_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch report download",
        ) from exc
