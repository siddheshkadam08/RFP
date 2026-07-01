"""Grounded RAG copilot: retrieve from the corpus, answer with citations, persist sessions.

Implements the spec's copilot graph (Skills/04 §13.2) as a plain async pipeline:
    rewrite_query -> semantic_retrieve -> generate_grounded_answer -> attach_citations,
    refusing when the top similarity doesn't clear the grounding threshold.

Retrieval uses ``search_service.semantic_search`` (merged opportunity + document-chunk
vectors) rather than ``hybrid_search``: hybrid returns an RRF-*normalized* score (top is
always 1.0), which cannot gate grounding or drive a real confidence; the semantic path
returns a true cosine similarity (1 - distance) that does both. ``ai_service.chat_completion``
(Azure gpt-4.1) powers the rewrite + generation.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.core.database import AsyncSession
from app.models.chat_session import ChatMessage, ChatRole, ChatSession
from app.services import ai_service, search_service

logger = logging.getLogger(__name__)

_RETRIEVE_K = 8
_HISTORY_LIMIT = 10
# Minimum top cosine similarity (1 - distance) for an answer to be considered grounded.
# 0.35 = vectors share meaningful directional similarity; in-corpus questions score 0.5-0.62.
_GROUNDING_THRESHOLD = 0.35

_SYSTEM_PROMPT = (
    "You are the IRIS SupTech & RegTech Opportunity Intelligence Copilot.\n"
    "\n"
    "Your task is to answer the user's question using ONLY the numbered Context items "
    "provided below. Do not use facts, figures, deadlines, budgets, or institution details "
    "from your training data or from prior conversation turns.\n"
    "\n"
    "Rules:\n"
    "1. Every factual claim must be immediately followed by a citation: [1], [2][3], etc.\n"
    "2. If a specific fact (deadline, budget, institution name, country, standard) is not "
    "present in the Context, say exactly: 'This information is not available in the indexed corpus.'\n"
    "3. Do not infer, estimate, or approximate missing values.\n"
    "4. For list questions, include all relevant Context items — do not truncate for brevity.\n"
    "5. For single-fact questions, be concise: one or two sentences with citations.\n"
    "6. You may use general domain knowledge only to define a term (e.g. 'XBRL is...') — "
    "label such statements as [general knowledge] and never apply them as evidence for specific claims.\n"
    "7. If no Context item is sufficiently relevant, respond: "
    "'I could not find supporting evidence in the indexed opportunity corpus for that question.'\n"
    "\n"
    "Domain context: The corpus contains procurement opportunities, tenders, RFPs, strategic plans, "
    "and announcements from central banks, financial regulators, deposit insurance agencies, and "
    "standards bodies. Key fields per opportunity: institution, country, region, category, deadline, "
    "budget, standards (XBRL/SDMX/ISO 20022/DPM/LEI), and scope."
)

_REWRITE_SYSTEM = (
    "You are a query reformulation assistant for a SupTech and RegTech opportunity intelligence system.\n"
    "\n"
    "Rewrite the user's latest message into a single, self-contained search query that can be "
    "understood without any prior conversation context. Resolve all pronouns, references "
    "(e.g. 'those', 'that', 'it', 'them'), and elliptical references using the conversation history.\n"
    "\n"
    "Rules:\n"
    "- Preserve all technical terms, acronyms, institution names, country names, and standard names "
    "exactly as stated (e.g. XBRL, SDMX, ISO 20022, ECB, BIS, DPM, LEI).\n"
    "- Output one query sentence only, maximum 25 words.\n"
    "- Do not add explanations, quotes, labels, or prefixes.\n"
    "- If the message is a greeting, off-topic statement, or not a searchable question, "
    "return the message unchanged."
)


def _coerce_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _role_value(role: Any) -> str:
    return role.value if hasattr(role, "value") else str(role)


def _title_from(message: str) -> str:
    text = " ".join((message or "").split())
    if not text:
        return "New chat"
    return text[:57] + "…" if len(text) > 60 else text


async def _get_or_create_session(
    db: AsyncSession, user_uuid: UUID, session_id: UUID | None, first_message: str
) -> ChatSession:
    if session_id is not None:
        existing = (
            await db.execute(
                select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_uuid)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    session = ChatSession(user_id=user_uuid, title=_title_from(first_message), context={})
    db.add(session)
    await db.flush()  # assigns session.id
    return session


async def _load_history(db: AsyncSession, session_id: UUID) -> list[ChatMessage]:
    rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(_HISTORY_LIMIT)
        )
    ).scalars().all()
    return list(reversed(rows))


async def _rewrite_query(message: str, history: list[ChatMessage]) -> str:
    """Condense the latest message + recent turns into a standalone retrieval query."""
    if not history:
        return message
    try:
        convo = "\n".join(f"{_role_value(m.role)}: {m.content}" for m in history[-4:])
        rewritten = await ai_service.chat_completion(
            [
                {"role": "system", "content": _REWRITE_SYSTEM},
                {
                    "role": "user",
                    "content": f"Conversation so far:\n{convo}\n\nLatest message: {message}\n\nRewritten query:",
                },
            ],
            model="small",
        )
        # Strip any prefix the model echoed (e.g. "Rewritten query: ...") and surrounding quotes
        rewritten = (rewritten or "").strip()
        for prefix in ("Rewritten query:", "Standalone search query:", "Query:"):
            if rewritten.lower().startswith(prefix.lower()):
                rewritten = rewritten[len(prefix):].strip()
        rewritten = rewritten.strip('"\'')
        return rewritten or message
    except Exception as exc:  # noqa: BLE001 - rewrite is best-effort
        logger.warning("Copilot query rewrite failed, using raw message: %s", exc)
        return message


def _context_block(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, item in enumerate(items, start=1):
        title = item.get("title") or "Untitled"
        body = item.get("snippet") or item.get("ai_summary") or item.get("summary") or ""
        # Include key structured fields so the LLM can answer deadline/budget/institution questions
        meta_parts: list[str] = []
        if item.get("institution"):
            meta_parts.append(f"Institution: {item['institution']}")
        if item.get("country"):
            meta_parts.append(f"Country: {item['country']}")
        if item.get("region"):
            meta_parts.append(f"Region: {item['region']}")
        if item.get("deadline"):
            meta_parts.append(f"Deadline: {item['deadline']}")
        if item.get("budget") or item.get("score"):
            budget = item.get("budget") or ""
            score = item.get("score") or ""
            if budget:
                meta_parts.append(f"Budget: {budget}")
            if score:
                meta_parts.append(f"Score: {score}/100")
        if item.get("source_url"):
            meta_parts.append(f"Source: {item['source_url']}")
        block = f"[{index}] {title}\n{body}"
        if meta_parts:
            block += "\n" + " | ".join(meta_parts)
        parts.append(block)
    return "\n\n".join(parts)


def _citations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": item.get("title"),
            "snippet": item.get("snippet") or item.get("ai_summary"),
            "opportunity_id": item.get("opportunity_id") or item.get("id"),
            "source_url": item.get("source_url"),
        }
        for item in items
    ]


def _confidence(items: list[dict[str, Any]]) -> float:
    scores = [float(i["relevance_score"]) for i in items[:3] if i.get("relevance_score") is not None]
    if not scores:
        return 0.3
    return round(min(1.0, max(0.0, sum(scores) / len(scores))), 4)


def _serialize_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": _role_value(message.role),
        "content": message.content,
        "citations": message.citations or [],
        "confidence": message.confidence,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def chat(db: AsyncSession, user_id: Any, chat_request: Any) -> dict[str, Any]:
    """Run one grounded RAG turn and persist both messages. Returns the chat response dict."""
    user_uuid = _coerce_uuid(user_id)
    message = (chat_request.message or "").strip()

    session = await _get_or_create_session(db, user_uuid, getattr(chat_request, "session_id", None), message)
    session_id = session.id
    # Lock the session row in before retrieval (the keyword path may roll back on a rare
    # pg_trgm error, which would otherwise discard a freshly-flushed session).
    await db.commit()

    history = await _load_history(db, session_id)
    rewritten = await _rewrite_query(message, history)

    try:
        items, _ = await search_service.semantic_search(db, rewritten, page=1, page_size=_RETRIEVE_K)
    except Exception as exc:  # noqa: BLE001 - degrade to "no evidence"
        logger.warning("Copilot retrieval failed: %s", exc)
        items = []

    top_score = max(
        (float(i["relevance_score"]) for i in items if i.get("relevance_score") is not None), default=0.0
    )
    grounded = bool(items) and top_score >= _GROUNDING_THRESHOLD

    if not grounded:
        answer = (
            "I couldn't find supporting evidence in the indexed opportunity corpus for that question. "
            "Try rephrasing, or ask about regions, regulators, standards, or specific opportunities that have been crawled."
        )
        citations: list[dict[str, Any]] = []
        confidence = 0.2
    else:
        # Context before history: prevents the "lost in the middle" attention dilution
        # where long history causes the model to underweight the retrieval evidence.
        prompt_messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            # Inject context as the first user turn so it receives highest attention weight.
            {"role": "user", "content": f"Context:\n{_context_block(items)}"},
            {"role": "assistant", "content": "Understood. I will answer only from the provided context items above."},
        ]
        # Append recent history (capped at 6 turns to bound token usage and attention dilution).
        for msg in history[-6:]:
            prompt_messages.append({"role": _role_value(msg.role), "content": msg.content})
        prompt_messages.append({"role": "user", "content": message})
        try:
            answer = await ai_service.chat_completion(prompt_messages, model="large")
        except Exception as exc:  # noqa: BLE001 - surface a graceful message, still persist
            logger.warning("Copilot generation failed: %s", exc)
            answer = "The AI service is temporarily unavailable. Please retry in a moment."
        citations = _citations(items)
        confidence = _confidence(items)

    db.add(ChatMessage(session_id=session_id, role=ChatRole.USER, content=message, citations=[], confidence=None))
    db.add(
        ChatMessage(
            session_id=session_id,
            role=ChatRole.ASSISTANT,
            content=answer,
            citations=citations,
            confidence=confidence,
        )
    )
    await db.commit()

    return {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "session_id": str(session_id),
    }


async def list_sessions(db: AsyncSession, user_id: Any) -> list[dict[str, Any]]:
    """Return the user's chat sessions (most-recently-updated first) with message counts."""
    user_uuid = _coerce_uuid(user_id)
    counts = (
        select(ChatMessage.session_id, func.count().label("n"))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(ChatSession, counts.c.n)
            .outerjoin(counts, counts.c.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_uuid)
            .order_by(ChatSession.updated_at.desc())
        )
    ).all()
    return [
        {
            "id": str(session.id),
            "title": session.title,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "message_count": int(count or 0),
        }
        for session, count in rows
    ]


async def get_session(db: AsyncSession, user_id: Any, session_id: Any) -> dict[str, Any] | None:
    """Return a session with its full ordered transcript, or None if not owned by the user."""
    user_uuid = _coerce_uuid(user_id)
    session = (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == _coerce_uuid(session_id), ChatSession.user_id == user_uuid
            )
        )
    ).scalar_one_or_none()
    if session is None:
        return None
    messages = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()
    return {
        "id": str(session.id),
        "title": session.title,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "messages": [_serialize_message(message) for message in messages],
    }
