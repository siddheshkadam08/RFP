from __future__ import annotations

"""Reporting endpoints."""

import logging
import os
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, get_current_user
from app.models.report import Report, ReportStatus, ReportType

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

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


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _serialize_report(report: Any) -> Any:
    """Convert a Report ORM row into a JSON-serializable dict the frontend expects.

    Returning a raw SQLAlchemy model from a ``dict[str, Any]`` route makes FastAPI's
    pydantic serializer fail (500); non-ORM values pass through unchanged.
    """
    if not isinstance(report, Report):
        return report
    status_value = _enum(report.status)
    completed = status_value == ReportStatus.COMPLETED.value and bool(report.file_path)
    pdf_path = (os.path.splitext(report.file_path)[0] + ".pdf") if report.file_path else None
    has_pdf = completed and pdf_path is not None and os.path.exists(pdf_path)
    return {
        "id": str(report.id),
        "title": report.title,
        "type": _enum(report.report_type),
        "status": status_value,
        "parameters": report.parameters,
        "summary": report.summary,
        "generated_by": str(report.generated_by_id) if report.generated_by_id else None,
        "file_url": f"/reports/{report.id}/download" if completed else None,
        "pdf_url": f"/reports/{report.id}/download?format=pdf" if has_pdf else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


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
        items = [_serialize_report(item) for item in items]
        return _success_response(items, meta={"page": page, "page_size": page_size, "total": total})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list reports")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list reports") from exc


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_report(payload: ReportGenerateRequest, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Synchronously generate a report (Excel) for the authenticated user and return it."""
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
        return _success_response(_serialize_report(result))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate report")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate report") from exc


@router.get("/{report_id}/download")
async def download_report(
    report_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
    format: str = Query(default="xlsx", pattern="^(xlsx|pdf)$"),
) -> FileResponse:
    """Stream the generated report file (xlsx or pdf) for a completed report."""
    try:
        service = _get_service()
        report = await service.get_report(db=db, report_id=report_id)
        if _enum(report.status) != ReportStatus.COMPLETED.value or not report.file_path:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not ready for download")
        if format == "pdf":
            path = os.path.splitext(report.file_path)[0] + ".pdf"
            media_type, ext = "application/pdf", "pdf"
        else:
            path, media_type, ext = report.file_path, _XLSX_MEDIA_TYPE, "xlsx"
        if not os.path.exists(path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")
        safe_title = (report.title or "report").replace(" ", "_").replace("/", "-")
        return FileResponse(path, filename=f"{safe_title}.{ext}", media_type=media_type)
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
