from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.common import SchemaBase


class KeywordSearchRequest(SchemaBase):
    query: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    # Optional filters applied to the search results.
    regions: list[str] | None = None
    categories: list[str] | None = None
    status: list[str] | None = None


class SemanticSearchRequest(SchemaBase):
    query: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    regions: list[str] | None = None
    categories: list[str] | None = None
    status: list[str] | None = None


class HybridSearchRequest(SchemaBase):
    query: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    regions: list[str] | None = None
    categories: list[str] | None = None
    status: list[str] | None = None


class SearchResult(SchemaBase):
    opportunity_id: UUID
    title: str
    score: int | None = None
    relevance_score: float
    snippet: str | None = None
    country: str | None = None
    region: str | None = None
    category: str | None = None
