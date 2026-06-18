from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, ConfigDict, Field

from app.schemas.common import SchemaBase


class SourceCreate(SchemaBase):
    name: str
    url: AnyHttpUrl
    source_type: str
    frequency: str
    domain: str | None = None
    country: str | None = None
    region: str | None = None
    tags: list[str] | None = None


class SourceUpdate(SchemaBase):
    name: str | None = None
    url: AnyHttpUrl | None = None
    frequency: str | None = None
    domain: str | None = None
    region: str | None = None
    is_active: bool | None = None
    tags: list[str] | None = None


class SourceResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    url: AnyHttpUrl
    source_type: str
    frequency: str
    domain: str | None = None
    country: str | None = None
    region: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool
    last_crawled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
