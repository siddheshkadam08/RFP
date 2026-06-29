"""AI Agent pipeline orchestrator.

Coordinates the flow of documents through the AI processing pipeline:
Input Source → Discovery → Crawl → Document → Relevance → Extraction → Classification → Scoring → Store
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.core.scoring import score_band
from app.services.ai_service import (
    check_relevance,
    classify_opportunity,
    extract_opportunity,
    score_opportunity,
    summarize_document,
)

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    """Stages in the AI processing pipeline."""
    DISCOVERY = "discovery"
    CRAWL = "crawl"
    DOCUMENT_PROCESSING = "document_processing"
    RELEVANCE_CHECK = "relevance_check"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    SCORING = "scoring"
    STORAGE = "storage"


@dataclass
class PipelineResult:
    """Result from a pipeline stage."""
    stage: PipelineStage
    success: bool
    data: dict[str, Any]
    error: str | None = None


async def run_intelligence_pipeline(content: str, metadata: dict[str, Any] | None = None) -> list[PipelineResult]:
    """Run the full AI intelligence pipeline on a document.

    Args:
        content: The document text content.
        metadata: Optional metadata about the document source.

    Returns:
        List of results from each pipeline stage.
    """
    results: list[PipelineResult] = []
    metadata = metadata or {}

    # Stage 1: Relevance Check
    try:
        relevance = await check_relevance(content)
        results.append(PipelineResult(
            stage=PipelineStage.RELEVANCE_CHECK,
            success=True,
            data=relevance,
        ))

        if not relevance.get("relevant", False):
            logger.info("Document not relevant (confidence: %.2f)", relevance.get("confidence", 0))
            return results
    except Exception as e:
        logger.error("Relevance check failed: %s", e)
        results.append(PipelineResult(
            stage=PipelineStage.RELEVANCE_CHECK,
            success=False,
            data={},
            error=str(e),
        ))
        return results

    # Stage 2: Extraction
    try:
        extracted = await extract_opportunity(content)
        results.append(PipelineResult(
            stage=PipelineStage.EXTRACTION,
            success=True,
            data=extracted,
        ))
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        results.append(PipelineResult(
            stage=PipelineStage.EXTRACTION,
            success=False,
            data={},
            error=str(e),
        ))
        return results

    # Stage 3: Classification
    try:
        category = await classify_opportunity(content)
        results.append(PipelineResult(
            stage=PipelineStage.CLASSIFICATION,
            success=True,
            data={"category": category},
        ))
    except Exception as e:
        logger.error("Classification failed: %s", e)
        results.append(PipelineResult(
            stage=PipelineStage.CLASSIFICATION,
            success=False,
            data={"category": "other"},
            error=str(e),
        ))

    # Stage 4: Summarization
    try:
        summary = await summarize_document(content)
        extracted["ai_summary"] = summary
    except Exception as e:
        logger.warning("Summarization failed: %s", e)
        extracted["ai_summary"] = ""

    # Stage 5: Scoring
    try:
        score_result = await score_opportunity(extracted)
        results.append(PipelineResult(
            stage=PipelineStage.SCORING,
            success=True,
            data=score_result,
        ))
    except Exception as e:
        logger.error("Scoring failed: %s", e)
        results.append(PipelineResult(
            stage=PipelineStage.SCORING,
            success=False,
            data={"score": 50, "breakdown": {}},
            error=str(e),
        ))

    return results


def get_score_band(score: int) -> str:
    """Get the score band label.

    Args:
        score: Opportunity score (0-100).

    Returns:
        Score band: 'low', 'medium', or 'high'.
    """
    return score_band(score)
