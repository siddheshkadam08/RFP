from __future__ import annotations

"""Source management endpoints."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, get_current_user, role_required
from app.models.source import SOURCE_REGIONS, CrawlFrequency, CrawlStatus, Source, SourceDomain, SourceType
from app.models.user import UserRole

try:
    from app.schemas.source import SourceCreateRequest, SourceUpdateRequest
except ImportError:
    class SourceCreateRequest(BaseModel):
        """Fallback source creation schema until app.schemas.source is available."""

        model_config = ConfigDict(extra="allow", use_enum_values=True)

        name: str = Field(min_length=1, max_length=255)
        url: str = Field(min_length=1, max_length=2048)
        source_type: SourceType
        frequency: CrawlFrequency
        domain: SourceDomain | None = None
        country: str | None = Field(default=None, max_length=100)
        region: str = Field(min_length=1, max_length=100)
        tags: list[str] = Field(default_factory=list)
        is_active: bool = True

    class SourceUpdateRequest(BaseModel):
        """Fallback source update schema until app.schemas.source is available."""

        model_config = ConfigDict(extra="allow", use_enum_values=True)

        name: str | None = Field(default=None, min_length=1, max_length=255)
        url: str | None = Field(default=None, min_length=1, max_length=2048)
        source_type: SourceType | None = None
        frequency: CrawlFrequency | None = None
        domain: SourceDomain | None = None
        country: str | None = Field(default=None, min_length=1, max_length=100)
        region: str | None = Field(default=None, min_length=1, max_length=100)
        tags: list[str] | None = None
        is_active: bool | None = None
        last_crawl_status: CrawlStatus | None = None

try:
    from app.services import source_service
except ImportError:
    source_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["sources"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]
AdminUser = Annotated[TokenPayload, Depends(role_required([UserRole.ADMIN.value]))]


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _enum_value(value: Any) -> Any:
    """Return an enum's ``.value`` (so JSON gets the string), else the value as-is."""
    return value.value if hasattr(value, "value") else value


def _serialize_source(source: Any) -> Any:
    """Serialize a Source ORM model into a JSON-safe dict.

    The route handlers are annotated ``-> dict[str, Any]``, so FastAPI serializes
    the response with pydantic, which cannot handle a raw SQLAlchemy model. Convert
    it to plain data here (mirrors ``_serialize_user`` in the auth endpoints).
    Non-Source values pass through unchanged.
    """
    if not isinstance(source, Source):
        return source
    return {
        "id": str(source.id),
        "name": source.name,
        "url": source.url,
        "source_type": _enum_value(source.source_type),
        "frequency": _enum_value(source.frequency),
        "domain": source.domain,
        "country": source.country,
        "region": source.region,
        "tags": list(source.tags or []),
        "is_active": source.is_active,
        "last_crawled_at": source.last_crawl_at.isoformat() if source.last_crawl_at else None,
        "last_crawl_status": _enum_value(source.last_crawl_status),
        "success_rate": source.success_rate,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


def _get_service() -> Any:
    """Return the source service or raise a service unavailable error."""
    if source_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Source service is not available",
        )
    return source_service


@router.get("/", status_code=status.HTTP_200_OK)
async def list_sources(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List configured crawl sources with pagination."""
    try:
        service = _get_service()
        try:
            result = await service.list_sources(db=db, page=page, page_size=page_size, user_id=current_user.sub)
        except TypeError:
            result = await service.list_sources(db=db, page=page, page_size=page_size)
        items, total = result if isinstance(result, tuple) else (result, None)
        serialized = [_serialize_source(item) for item in items]
        return _success_response(serialized, meta={"page": page, "page_size": page_size, "total": total})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list sources")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list sources") from exc


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_source(payload: SourceCreateRequest, db: DBSession, current_user: AdminUser) -> dict[str, Any]:
    """Create a new crawl source as an administrator."""
    try:
        service = _get_service()
        source_data = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)
        try:
            result = await service.create_source(db=db, source_data=source_data, created_by=current_user.sub)
        except TypeError:
            result = await service.create_source(db=db, source_data=source_data)
        return _success_response(_serialize_source(result))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create source")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create source") from exc


@router.get("/options", status_code=status.HTTP_200_OK)
async def list_source_options(current_user: CurrentUser) -> dict[str, Any]:
    """Return the allowed values for the source form dropdowns.

    Bound by the frontend so Type, Frequency, Domain, and Region stay in sync
    with the backend enums and the curated region list (no reference table yet).
    """
    return _success_response(
        {
            "source_types": [item.value for item in SourceType],
            "frequencies": [item.value for item in CrawlFrequency],
            "domains": [item.value for item in SourceDomain],
            "regions": list(SOURCE_REGIONS),
        }
    )


@router.get("/{source_id}", status_code=status.HTTP_200_OK)
async def get_source(source_id: UUID, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return details for a single source."""
    try:
        service = _get_service()
        if hasattr(service, "get_source_by_id"):
            result = await service.get_source_by_id(db=db, source_id=source_id, user_id=current_user.sub)
        else:
            result = await service.get_source(db=db, source_id=source_id)
        return _success_response(_serialize_source(result))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch source %s", source_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch source") from exc


@router.patch("/{source_id}", status_code=status.HTTP_200_OK)
async def update_source(
    source_id: UUID,
    payload: SourceUpdateRequest,
    db: DBSession,
    current_user: AdminUser,
) -> dict[str, Any]:
    """Update an existing crawl source as an administrator."""
    try:
        service = _get_service()
        update_data = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)
        try:
            result = await service.update_source(
                db=db,
                source_id=source_id,
                update_data=update_data,
                updated_by=current_user.sub,
            )
        except TypeError:
            result = await service.update_source(db=db, source_id=source_id, update_data=update_data)
        return _success_response(_serialize_source(result))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update source %s", source_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update source") from exc
