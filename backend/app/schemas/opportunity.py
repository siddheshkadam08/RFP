from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.common import SchemaBase


class OpportunitySearchRequest(SchemaBase):
    regions: list[str] | None = None
    countries: list[str] | None = None
    categories: list[str] | None = None
    standards: list[str] | None = None
    score_min: int | None = Field(default=None, ge=0, le=100)
    score_max: int | None = Field(default=None, ge=0, le=100)
    status: list[str] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    query: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1)


class OpportunityResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    summary: str | None = None
    ai_summary: str | None = None
    ai_reasoning: str | None = None
    region: str | None = None
    country: str | None = None
    category: str | None = None
    institution: str | None = None
    standards: list[str] = Field(default_factory=list)
    budget: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    status: str
    owner_id: UUID | None = None
    source_id: UUID | None = None
    source_url: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    deadline: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _populate_summary(self) -> "OpportunityResponse":
        """The model stores the AI summary as ``ai_summary``; expose it as ``summary``
        (the name the spec and UI use) so a summary is always available."""
        if not self.summary:
            self.summary = self.ai_summary
        return self


class OpportunityUpdate(SchemaBase):
    status: str | None = None
    owner_id: UUID | None = None
    notes: str | None = None
    tags: list[str] | None = None


class OpportunityListResponse(SchemaBase):
    items: list[OpportunityResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


class CommentCreate(SchemaBase):
    content: str


class CommentUserResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str


class CommentResponse(SchemaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content: str
    user: CommentUserResponse
    created_at: datetime
