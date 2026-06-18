from __future__ import annotations

"""Analyze URL endpoint — fetch a URL, run AI pipeline, return structured results."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.core.security import TokenPayload, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])

CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]

# ── Limit extracted text sent to LLM to control token costs ──
_MAX_CONTENT_CHARS = 15_000


class AnalyzeURLRequest(BaseModel):
    """Request body for the analyze-url endpoint."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl = Field(..., description="The URL to fetch and analyze (HTML or PDF)")


class AnalyzeURLResponse(BaseModel):
    """Structured response from the analyze-url endpoint."""

    model_config = ConfigDict(extra="allow")

    success: bool
    data: dict[str, Any]


@router.post("/url", status_code=status.HTTP_200_OK, response_model=AnalyzeURLResponse)
async def analyze_url(payload: AnalyzeURLRequest, current_user: CurrentUser) -> AnalyzeURLResponse:
    """Fetch a URL, determine SupTech/RegTech relevance, and extract opportunity data.

    Flow:
    1. Fetch HTML or PDF content from the URL.
    2. Run AI relevance check — is this about SupTech / RegTech?
    3. If relevant: extract opportunity fields, classify, summarize, and score.
    4. Return everything as structured JSON.
    """
    url_str = str(payload.url)

    # ── Step 1: Fetch URL content ──────────────────────────────
    try:
        from app.services.url_fetcher import fetch_url_content

        fetched = await fetch_url_content(url_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not extract content: {exc}",
        )
    except Exception as exc:
        logger.exception("Failed to fetch URL: %s", url_str)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch URL: {exc}",
        )

    # Truncate content to keep LLM costs reasonable
    content = fetched.text[:_MAX_CONTENT_CHARS]

    # ── Step 2: AI Relevance Check ─────────────────────────────
    try:
        from app.services.ai_service import check_relevance

        relevance = await check_relevance(content)
    except Exception as exc:
        logger.exception("Relevance check failed for %s", url_str)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI relevance check failed: {exc}",
        )

    result: dict[str, Any] = {
        "url": url_str,
        "fetched_title": fetched.title,
        "content_type": fetched.content_type,
        "content_length": fetched.content_length,
        "content_hash": fetched.content_hash,
        "relevant": relevance.get("relevant", False),
        "relevance_confidence": relevance.get("confidence", 0.0),
        "relevance_reason": relevance.get("reason", ""),
    }

    # If not relevant, return early — no need to spend more LLM calls
    if not relevance.get("relevant", False):
        return AnalyzeURLResponse(success=True, data=result)

    # ── Step 3: Extract opportunity data ───────────────────────
    try:
        from app.services.ai_service import extract_opportunity

        extracted = await extract_opportunity(content)
        result["extracted"] = extracted
    except Exception as exc:
        logger.warning("Extraction failed for %s: %s", url_str, exc)
        result["extracted"] = None
        result["extraction_error"] = str(exc)

    # ── Step 4: Classify ───────────────────────────────────────
    try:
        from app.services.ai_service import classify_opportunity

        category = await classify_opportunity(content)
        result["category"] = category
    except Exception as exc:
        logger.warning("Classification failed for %s: %s", url_str, exc)
        result["category"] = "unknown"

    # ── Step 5: Summarize ──────────────────────────────────────
    try:
        from app.services.ai_service import summarize_document

        summary = await summarize_document(content)
        result["ai_summary"] = summary
    except Exception as exc:
        logger.warning("Summarization failed for %s: %s", url_str, exc)
        result["ai_summary"] = ""

    # ── Step 6: Score ──────────────────────────────────────────
    try:
        from app.services.ai_service import score_opportunity

        score_input = extracted if extracted else {"scope": content[:1000]}
        score_result = await score_opportunity(score_input)
        result["score"] = score_result.get("score", 0)
        result["score_breakdown"] = score_result.get("breakdown", {})
    except Exception as exc:
        logger.warning("Scoring failed for %s: %s", url_str, exc)
        result["score"] = 0
        result["score_breakdown"] = {}

    return AnalyzeURLResponse(success=True, data=result)
