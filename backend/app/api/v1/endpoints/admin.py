from __future__ import annotations

"""Administrative endpoints."""

import logging
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, role_required
from app.models.user import UserRole

try:
    from app.services import admin_service
except ImportError:
    admin_service = None

try:
    from app.services import auth_service, audit_service
except ImportError:
    auth_service = None
    audit_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[TokenPayload, Depends(role_required([UserRole.ADMIN.value]))]


class AdminUserCreateRequest(BaseModel):
    """Fallback admin user creation schema."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class AdminUserUpdateRequest(BaseModel):
    """Fallback admin user update schema."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _model_dump(payload: Any) -> dict[str, Any]:
    """Return a dictionary representation of a request payload."""
    return payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)


def _serialize_user(user: Any) -> dict[str, Any]:
    """Serialize a user model into a JSON-safe payload."""
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": role,
        "is_active": user.is_active,
        "last_login": user.last_login.isoformat() if getattr(user, "last_login", None) else None,
        "created_at": user.created_at.isoformat() if getattr(user, "created_at", None) else None,
    }


@router.get("/users", status_code=status.HTTP_200_OK)
async def list_users(
    current_user: AdminUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict[str, Any]:
    """List users with optional filtering and pagination."""
    try:
        if admin_service is not None and hasattr(admin_service, "list_users"):
            result = await admin_service.list_users(
                db=db,
                page=page,
                page_size=page_size,
                role=role,
                is_active=is_active,
                search=search,
                requested_by=current_user.sub,
            )
            return _success_response(result, meta={"page": page, "page_size": page_size})

        if auth_service is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin service is not available")

        users, total = await auth_service.list_users(db=db, page=page, page_size=page_size)
        filtered_users = []
        for user in users:
            user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
            if role and user_role != role.value:
                continue
            if is_active is not None and user.is_active != is_active:
                continue
            if search and search.lower() not in f"{user.full_name} {user.email}".lower():
                continue
            filtered_users.append(_serialize_user(user))
        return _success_response(filtered_users, meta={"page": page, "page_size": page_size, "total": total})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list users")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list users") from exc


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: AdminUserCreateRequest, db: DBSession, current_user: AdminUser) -> dict[str, Any]:
    """Create a new user account from the admin console."""
    try:
        user_data = _model_dump(payload)
        if admin_service is not None and hasattr(admin_service, "create_user"):
            result = await admin_service.create_user(db=db, user_data=user_data, created_by=current_user.sub)
        elif auth_service is not None:
            result = await auth_service.create_user(db=db, user_data=user_data)
        else:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin service is not available")
        return _success_response(_serialize_user(result) if hasattr(result, "id") else result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create user")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user") from exc


@router.patch("/users/{user_id}", status_code=status.HTTP_200_OK)
async def update_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    db: DBSession,
    current_user: AdminUser,
) -> dict[str, Any]:
    """Update a user account from the admin console."""
    try:
        update_data = _model_dump(payload)
        if admin_service is not None and hasattr(admin_service, "update_user"):
            result = await admin_service.update_user(
                db=db,
                user_id=user_id,
                update_data=update_data,
                updated_by=current_user.sub,
            )
        elif auth_service is not None:
            result = await auth_service.update_user(db=db, user_id=user_id, update_data=update_data)
        else:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin service is not available")
        return _success_response(_serialize_user(result) if hasattr(result, "id") else result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update user %s", user_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update user") from exc


@router.get("/ai-costs", status_code=status.HTTP_200_OK)
async def get_ai_costs(
    current_user: AdminUser,
    db: DBSession,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict[str, Any]:
    """Return aggregated AI usage and cost metrics."""
    try:
        if admin_service is not None and hasattr(admin_service, "get_ai_cost_summary"):
            result = await admin_service.get_ai_cost_summary(
                db=db,
                start_date=start_date,
                end_date=end_date,
                requested_by=current_user.sub,
            )
        else:
            result = {
                "total_cost": 0.0,
                "currency": "USD",
                "usage": [],
                "note": "AI cost tracking service is not implemented yet.",
            }
        return _success_response(result, meta={"start_date": start_date, "end_date": end_date})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch AI cost summary")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch AI cost summary",
        ) from exc


@router.get("/audit-logs", status_code=status.HTTP_200_OK)
async def list_audit_logs(
    current_user: AdminUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
) -> dict[str, Any]:
    """List audit logs with pagination and optional filters."""
    try:
        if admin_service is not None and hasattr(admin_service, "list_audit_logs"):
            result = await admin_service.list_audit_logs(
                db=db,
                page=page,
                page_size=page_size,
                action=action,
                resource_type=resource_type,
                user_id=user_id,
                requested_by=current_user.sub,
            )
        elif audit_service is not None:
            result = await audit_service.list_audit_logs(db=db, page=page, page_size=page_size, user_id=user_id, action=action)
        else:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin service is not available")
        items, total = result if isinstance(result, tuple) else (result, None)
        return _success_response(
            items,
            meta={
                "page": page,
                "page_size": page_size,
                "action": action,
                "resource_type": resource_type,
                "user_id": user_id,
                "total": total,
            },
        )
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list audit logs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list audit logs",
        ) from exc
