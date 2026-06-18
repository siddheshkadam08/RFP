from __future__ import annotations

"""Authentication endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException, UnauthorizedException
from app.core.security import TokenPayload, create_access_token, get_current_user, role_required
from app.models.user import UserRole

try:
    from app.schemas.auth import LoginRequest, UserCreate as UserCreateRequest
except ImportError:
    class LoginRequest(BaseModel):
        """Fallback login schema until app.schemas.auth is available."""

        model_config = ConfigDict(extra="allow")

        email: EmailStr
        password: str = Field(min_length=8)

    class UserCreateRequest(BaseModel):
        """Fallback user creation schema until app.schemas.auth is available."""

        model_config = ConfigDict(extra="allow", use_enum_values=True)

        email: EmailStr
        full_name: str = Field(min_length=1, max_length=255)
        password: str = Field(min_length=8)
        role: UserRole = UserRole.VIEWER
        is_active: bool = True

try:
    from app.services import auth_service
except ImportError:
    auth_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]
AdminUser = Annotated[TokenPayload, Depends(role_required([UserRole.ADMIN.value]))]


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _get_service() -> Any:
    """Return the auth service or raise a service unavailable error."""
    if auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not available",
        )
    return auth_service


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
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, db: DBSession) -> dict[str, Any]:
    """Authenticate a user with email and password and return a JWT."""
    try:
        service = _get_service()
        if hasattr(service, "login_user"):
            result = await service.login_user(db=db, login_data=payload)
            return _success_response(result)

        credentials = _model_dump(payload)
        user = await service.authenticate_user(db, credentials["email"], credentials["password"])
        if user is None:
            raise UnauthorizedException("Invalid email or password")

        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        token = create_access_token(subject=str(user.id), email=user.email, roles=[role])
        return _success_response({"token": token, "user": _serialize_user(user)})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to login user")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to login user") from exc


@router.post("/token", status_code=status.HTTP_200_OK)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
) -> dict[str, Any]:
    """OAuth2 password-flow token endpoint.

    This exists for the Swagger "Authorize" button (and any standard OAuth2 client):
    it accepts form-encoded ``username`` (use the email) and ``password`` and returns
    a bearer token in the OAuth2 shape ``{access_token, token_type}``. The web app
    keeps using the JSON ``/auth/login`` endpoint above.
    """
    try:
        service = _get_service()
        user = await service.authenticate_user(db, form_data.username, form_data.password)
        if user is None:
            raise UnauthorizedException("Invalid email or password")
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        token = create_access_token(subject=str(user.id), email=user.email, roles=[role])
        return {"access_token": token, "token_type": "bearer"}
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to issue access token")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to issue access token",
        ) from exc


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return the current authenticated user's profile."""
    try:
        service = _get_service()
        if hasattr(service, "get_current_user_profile"):
            result = await service.get_current_user_profile(db=db, user_id=current_user.sub)
            return _success_response(result)

        user = await service.get_user_by_id(db=db, user_id=current_user.sub)
        if user is None:
            raise UnauthorizedException("Authenticated user could not be found")
        return _success_response(_serialize_user(user))
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load current user profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load current user profile",
        ) from exc


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreateRequest, db: DBSession, current_user: AdminUser) -> dict[str, Any]:
    """Create a new user account as an administrator."""
    try:
        service = _get_service()
        user_data = _model_dump(payload)
        try:
            result = await service.create_user(db=db, user_data=user_data, created_by=current_user.sub)
        except TypeError:
            result = await service.create_user(db=db, user_data=user_data)
        return _success_response(_serialize_user(result) if hasattr(result, "id") else result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to register user")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to register user") from exc
