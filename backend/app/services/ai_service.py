from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.agents.prompts import (
    CLASSIFICATION_PROMPT,
    EXTRACTION_PROMPT,
    RELEVANCE_PROMPT,
    SCORING_PROMPT,
    SUMMARIZE_PROMPT,
)
from app.core.config import settings
from app.core.exceptions import AIServiceException

logger = logging.getLogger(__name__)


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages:
        normalized.append(
            {
                "role": str(message.get("role", "user")),
                "content": str(message.get("content", "")),
            }
        )
    return normalized


def _chat_deployment(model: str) -> str:
    if model == "large":
        return getattr(settings, "AZURE_OPENAI_LARGE_DEPLOYMENT", "") or settings.AZURE_OPENAI_DEPLOYMENT
    return getattr(settings, "AZURE_OPENAI_SMALL_DEPLOYMENT", "") or settings.AZURE_OPENAI_DEPLOYMENT


def _ensure_configured() -> None:
    if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
        raise AIServiceException("Azure OpenAI configuration is incomplete")


def _build_url(deployment: str, operation: str) -> str:
    endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip("/")
    return (
        f"{endpoint}/openai/deployments/{deployment}/{operation}"
        f"?api-version={settings.AZURE_OPENAI_API_VERSION}"
    )


def _headers() -> dict[str, str]:
    return {"api-key": settings.AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise AIServiceException("AI response did not contain any choices")

    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    return str(content).strip()


async def chat_completion(messages: list[dict[str, Any]], model: str = "small") -> str:
    """Call Azure OpenAI chat completions with retries."""
    _ensure_configured()
    deployment = _chat_deployment(model)
    normalized_messages = _normalize_messages(messages)

    payload = {
        "messages": normalized_messages,
        "temperature": 0.2 if model == "small" else 0.4,
        "max_tokens": 800 if model == "small" else 1600,
    }

    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(_build_url(deployment, "chat/completions"), headers=_headers(), json=payload)
                response.raise_for_status()
                return _extract_chat_text(response.json())
        except (httpx.HTTPError, ValueError, KeyError, AIServiceException) as exc:
            logger.warning("Chat completion attempt %s failed: %s", attempt, exc)
            if attempt == 3:
                raise AIServiceException(
                    "Chat completion failed",
                    details={"model": model, "attempts": attempt},
                ) from exc
            await asyncio.sleep(2 ** (attempt - 1))

    raise AIServiceException("Chat completion failed")


async def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector for the provided text."""
    _ensure_configured()
    deployment = settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    payload = {"input": text}

    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = await client.post(_build_url(deployment, "embeddings"), headers=_headers(), json=payload)
                response.raise_for_status()
                data = response.json().get("data") or []
                if not data or "embedding" not in data[0]:
                    raise AIServiceException("Embedding response did not contain a vector")
                return [float(value) for value in data[0]["embedding"]]
        except (httpx.HTTPError, ValueError, KeyError, AIServiceException) as exc:
            logger.warning("Embedding attempt %s failed: %s", attempt, exc)
            if attempt == 3:
                raise AIServiceException("Embedding generation failed", details={"attempts": attempt}) from exc
            await asyncio.sleep(2 ** (attempt - 1))

    raise AIServiceException("Embedding generation failed")


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


async def _json_completion(messages: list[dict[str, Any]], model: str = "small") -> dict[str, Any]:
    text = await chat_completion(messages, model=model)
    return _extract_json(text)


def _heuristic_category(content: str) -> str:
    lowered = content.lower()
    if any(keyword in lowered for keyword in ["regtech", "compliance", "aml", "kyc"]):
        return "regtech"
    if any(keyword in lowered for keyword in ["risk", "stress test", "prudential"]):
        return "risk"
    if any(keyword in lowered for keyword in ["reporting", "xbrl", "disclosure"]):
        return "reporting"
    if any(keyword in lowered for keyword in ["data", "analytics", "dashboard", "visualization"]):
        return "analytics"
    return "suptech"


def _extract_budget_value(budget: Any) -> float | None:
    if budget is None:
        return None
    if isinstance(budget, (int, float)):
        return float(budget)

    text = str(budget).lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(m|million|k|thousand)?", text)
    if not match:
        return None

    value = float(match.group(1))
    suffix = match.group(2)
    if suffix in {"m", "million"}:
        value *= 1_000_000
    elif suffix in {"k", "thousand"}:
        value *= 1_000
    return value


def _default_score_breakdown(opportunity_data: dict[str, Any]) -> dict[str, int]:
    content_blob = json.dumps(opportunity_data).lower()
    strategic = 85 if any(word in content_blob for word in ["central bank", "regulator", "supervision", "suptech"]) else 60

    budget_value = _extract_budget_value(opportunity_data.get("budget"))
    if budget_value is None:
        budget_score = 50
    elif budget_value >= 1_000_000:
        budget_score = 90
    elif budget_value >= 250_000:
        budget_score = 75
    else:
        budget_score = 55

    deadline = opportunity_data.get("deadline")
    if isinstance(deadline, str):
        try:
            deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except ValueError:
            deadline = None
    if isinstance(deadline, datetime):
        days_remaining = (deadline - datetime.now(timezone.utc)).days
        if days_remaining >= 90:
            timeline = 85
        elif days_remaining >= 30:
            timeline = 65
        elif days_remaining >= 0:
            timeline = 40
        else:
            timeline = 20
    else:
        timeline = 55

    standards = opportunity_data.get("standards") or []
    scope_text = str(opportunity_data.get("scope") or "").lower()
    technology = 80 if standards or any(word in scope_text for word in ["api", "ai", "analytics", "xbrl", "cloud"]) else 55
    competition = 70 if any(word in scope_text for word in ["specialized", "supervisory", "regulatory"]) else 55

    return {
        "strategic": strategic,
        "budget": budget_score,
        "timeline": timeline,
        "technology": technology,
        "competition": competition,
    }


def _weighted_score(breakdown: dict[str, Any]) -> int:
    strategic = float(breakdown.get("strategic", 0))
    budget = float(breakdown.get("budget", 0))
    timeline = float(breakdown.get("timeline", 0))
    technology = float(breakdown.get("technology", 0))
    competition = float(breakdown.get("competition", 0))
    score = 0.30 * strategic + 0.25 * budget + 0.20 * timeline + 0.15 * technology + 0.10 * competition
    return max(0, min(100, round(score)))


async def check_relevance(content: str) -> dict[str, Any]:
    """Determine whether content is relevant to SupTech/RegTech opportunities."""
    default = {"relevant": False, "confidence": 0.0, "reason": "AI service unavailable"}
    try:
        result = await _json_completion(
            [
                {
                    "role": "system",
                    "content": RELEVANCE_PROMPT.replace("{content}", "").strip(),
                },
                {"role": "user", "content": content},
            ]
        )
        return {
            "relevant": bool(result.get("relevant", False)),
            "confidence": float(result.get("confidence", 0.0)),
            "reason": str(result.get("reason", "")),
        }
    except Exception as exc:
        logger.warning("Relevance check fallback used: %s", exc)
        lowered = content.lower()
        default["relevant"] = any(word in lowered for word in ["suptech", "regtech", "supervision", "regulator", "compliance"])
        default["confidence"] = 0.55 if default["relevant"] else 0.15
        default["reason"] = "Heuristic classification used"
        return default


async def extract_opportunity(content: str) -> dict[str, Any]:
    """Extract structured opportunity data from free-form content."""
    default = {
        "title": "Untitled opportunity",
        "country": "Unknown",
        "institution": "Unknown",
        "standards": [],
        "budget": None,
        "deadline": None,
        "scope": content[:1000],
    }
    try:
        result = await _json_completion(
            [
                {
                    "role": "system",
                    "content": EXTRACTION_PROMPT.replace("{content}", "").strip(),
                },
                {"role": "user", "content": content},
            ]
        )
        default.update(result)
        if not isinstance(default.get("standards"), list):
            default["standards"] = []
        return default
    except Exception as exc:
        logger.warning("Opportunity extraction fallback used: %s", exc)
        return default


async def classify_opportunity(content: str) -> str:
    """Classify an opportunity into a domain category."""
    valid_categories = {
        "suptech",
        "regtech",
        "analytics",
        "risk",
        "taxonomy",
        "reporting",
        "deposit_insurance",
        "data_collection",
        "workflow",
        "validation",
    }
    try:
        response = await chat_completion(
            [
                {
                    "role": "system",
                    "content": CLASSIFICATION_PROMPT.replace("{content}", "").strip(),
                },
                {"role": "user", "content": content},
            ]
        )
        category = response.strip().split()[0].strip('"').lower()
        return category if category in valid_categories else _heuristic_category(content)
    except Exception as exc:
        logger.warning("Opportunity classification fallback used: %s", exc)
        return _heuristic_category(content)


async def score_opportunity(opportunity_data: dict[str, Any]) -> dict[str, Any]:
    """Score an opportunity using weighted criteria."""
    fallback_breakdown = _default_score_breakdown(opportunity_data)
    fallback = {"score": _weighted_score(fallback_breakdown), "breakdown": fallback_breakdown}
    try:
        result = await _json_completion(
            [
                {
                    "role": "system",
                    "content": SCORING_PROMPT.replace("{opportunity_data}", "").strip(),
                },
                {"role": "user", "content": json.dumps(opportunity_data, default=str)},
            ]
        )
        breakdown = result.get("breakdown") if isinstance(result.get("breakdown"), dict) else result
        normalized = {
            "strategic": int(float(breakdown.get("strategic", fallback_breakdown["strategic"]))),
            "budget": int(float(breakdown.get("budget", fallback_breakdown["budget"]))),
            "timeline": int(float(breakdown.get("timeline", fallback_breakdown["timeline"]))),
            "technology": int(float(breakdown.get("technology", fallback_breakdown["technology"]))),
            "competition": int(float(breakdown.get("competition", fallback_breakdown["competition"]))),
        }
        return {"score": _weighted_score(normalized), "breakdown": normalized}
    except Exception as exc:
        logger.warning("Opportunity scoring fallback used: %s", exc)
        return fallback


def _context_citations(context: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in context or []:
        citations.append(
            {
                "title": item.get("title") or item.get("name") or "Context document",
                "source": item.get("source_url") or item.get("source") or item.get("id"),
            }
        )
    return citations[:5]


def _context_text(context: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for index, item in enumerate(context or [], start=1):
        title = item.get("title") or item.get("name") or f"Document {index}"
        body = item.get("content") or item.get("ai_summary") or item.get("summary") or ""
        parts.append(f"[{index}] {title}\n{body}")
    return "\n\n".join(parts)


async def copilot_chat(
    message: str,
    context: list[dict[str, Any]] | None,
    history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Answer a user question using provided context and conversation history."""
    citations = _context_citations(context)
    try:
        prompt_messages = [
            {
                "role": "system",
                "content": "You are an RFP intelligence copilot. Use the supplied context, cite the supporting documents, and be concise.",
            }
        ]
        for item in history or []:
            prompt_messages.append({"role": item.get("role", "user"), "content": str(item.get("content", ""))})
        prompt_messages.append(
            {
                "role": "user",
                "content": f"Context:\n{_context_text(context)}\n\nQuestion: {message}",
            }
        )
        answer = await chat_completion(prompt_messages, model="large")
        return {"answer": answer, "citations": citations, "confidence": 0.8 if citations else 0.6}
    except Exception as exc:
        logger.warning("Copilot chat fallback used: %s", exc)
        fallback_answer = (
            "AI service is currently unavailable. Based on available context, review the cited opportunities for the most relevant details."
        )
        if context:
            snippets = [str(item.get("ai_summary") or item.get("summary") or item.get("content") or "")[:200] for item in context[:2]]
            fallback_answer = "\n\n".join([fallback_answer, *[snippet for snippet in snippets if snippet]])
        return {"answer": fallback_answer, "citations": citations, "confidence": 0.25}


async def summarize_document(content: str) -> str:
    """Summarize a document using the configured AI provider."""
    try:
        return await chat_completion(
            [
                {"role": "system", "content": SUMMARIZE_PROMPT.replace("{content}", "").strip()},
                {"role": "user", "content": content},
            ]
        )
    except Exception as exc:
        logger.warning("Document summarization fallback used: %s", exc)
        clean_content = " ".join(content.split())
        return clean_content[:497] + "..." if len(clean_content) > 500 else clean_content
