from __future__ import annotations

"""Authentication and authorization helpers."""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.core.exceptions import ForbiddenException, UnauthorizedException

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token", auto_error=False)


class TokenPayload(BaseModel):
    """Normalized JWT payload for authenticated users."""

    model_config = ConfigDict(extra="allow")

    sub: str
    email: str | None = None
    roles: list[str] = Field(default_factory=list)
    exp: int | None = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password for storage."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str,
    *,
    email: str | None = None,
    roles: Sequence[str] | None = None,
    expires_delta: timedelta | None = None,
    additional_claims: Mapping[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "email": email,
        "roles": list(roles or []),
        "exp": expire,
    }
    if additional_claims:
        payload.update(dict(additional_claims))
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token."""
    try:
        raw_payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if "roles" not in raw_payload and isinstance(raw_payload.get("role"), str):
            raw_payload["roles"] = [raw_payload["role"]]
        return TokenPayload.model_validate(raw_payload)
    except (JWTError, ValidationError) as exc:
        logger.warning("Failed to decode access token: %s", exc)
        raise UnauthorizedException("Could not validate credentials") from exc


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> TokenPayload:
    """Return the currently authenticated user payload from the access token."""
    if not token:
        raise UnauthorizedException("Authentication credentials were not provided")
    return decode_access_token(token)


def role_required(allowed_roles: Sequence[str]):
    """Create a dependency that restricts access to users with required roles."""
    normalized_roles = {role.strip().lower() for role in allowed_roles if role.strip()}

    async def dependency(
        current_user: Annotated[TokenPayload, Depends(get_current_user)],
    ) -> TokenPayload:
        user_roles = {role.strip().lower() for role in current_user.roles if role.strip()}
        if normalized_roles and normalized_roles.isdisjoint(user_roles):
            raise ForbiddenException(
                "Insufficient permissions",
                details={"required_roles": sorted(normalized_roles)},
            )
        return current_user

    return dependency
