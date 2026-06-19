from __future__ import annotations

"""Application configuration loaded from environment variables."""

import json
from functools import lru_cache
from typing import Any

from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "AI-Powered Global RFP & Opportunity Intelligence System"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres@localhost:5432/rfp"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None

    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-large"
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    # Embeddings may live on a SEPARATE Azure OpenAI resource (different endpoint/key/
    # version) than chat. Blank values fall back to the chat resource above.
    AZURE_OPENAI_EMBEDDING_ENDPOINT: str = ""
    AZURE_OPENAI_EMBEDDING_API_KEY: str = ""
    AZURE_OPENAI_EMBEDDING_API_VERSION: str = ""
    EMBEDDING_DIM: int = 1536

    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: EmailStr = "noreply@example.com"
    SMTP_FROM_NAME: str = "RFP Intelligence System"
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Support JSON arrays and comma-separated CORS origin values."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            raw_value = value.strip()
            if not raw_value:
                return []
            if raw_value.startswith("["):
                parsed = json.loads(raw_value)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON value must be a list")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw_value.split(",") if item.strip()]
        raise TypeError("Unsupported CORS_ORIGINS value")

    @model_validator(mode="after")
    def apply_derived_defaults(self) -> Settings:
        """Populate settings whose defaults depend on other values."""
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        # Embedding resource falls back to the chat resource when not set separately.
        if not self.AZURE_OPENAI_EMBEDDING_ENDPOINT:
            self.AZURE_OPENAI_EMBEDDING_ENDPOINT = self.AZURE_OPENAI_ENDPOINT
        if not self.AZURE_OPENAI_EMBEDDING_API_KEY:
            self.AZURE_OPENAI_EMBEDDING_API_KEY = self.AZURE_OPENAI_API_KEY
        if not self.AZURE_OPENAI_EMBEDDING_API_VERSION:
            self.AZURE_OPENAI_EMBEDDING_API_VERSION = self.AZURE_OPENAI_API_VERSION
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object."""
    return Settings()


settings = get_settings()
