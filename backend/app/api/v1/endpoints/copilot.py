from __future__ import annotations

"""AI copilot endpoints."""

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import TokenPayload, get_current_user
from app.models.document import Document

try:
    from app.schemas.copilot import ChatRequest, QnARequest as DocumentQnARequest, SummarizeRequest
except ImportError:
    class ChatRequest(BaseModel):
        """Fallback chat schema until app.schemas.copilot is available."""

        model_config = ConfigDict(extra="allow")

        message: str = Field(min_length=1)
        session_id: UUID | None = None
        context: dict[str, Any] = Field(default_factory=dict)

    class SummarizeRequest(BaseModel):
        """Fallback summarize schema until app.schemas.copilot is available."""

        model_config = ConfigDict(extra="allow")

        document_id: UUID | None = None
        text: str | None = None
        max_length: int | None = Field(default=None, ge=1)

    class DocumentQnARequest(BaseModel):
        """Fallback Q&A schema until app.schemas.copilot is available."""

        model_config = ConfigDict(extra="allow")

        question: str = Field(min_length=1)
        context_ids: list[UUID] | None = None
        document_id: UUID | None = None
        context: dict[str, Any] = Field(default_factory=dict)

try:
    from app.services import ai_service
except ImportError:
    ai_service = None

try:
    from app.services import copilot_service
except ImportError:
    copilot_service = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def _success_response(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the standard API success envelope."""
    return {"success": True, "data": data, "meta": meta or {}}


def _get_service() -> Any:
    """Return the AI service or raise a service unavailable error."""
    if ai_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI copilot service is not available",
        )
    return ai_service


def _get_copilot_service() -> Any:
    """Return the grounded copilot service or raise a service unavailable error."""
    if copilot_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI copilot service is not available",
        )
    return copilot_service


async def _load_document_context(db: AsyncSession, document_ids: list[UUID]) -> list[dict[str, Any]]:
    """Load document snippets for AI context."""
    if not document_ids:
        return []
    result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
    documents = result.scalars().all()
    return [
        {
            "id": str(document.id),
            "title": document.title,
            "content": document.content_text,
            "source": document.url,
        }
        for document in documents
    ]


@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat(payload: ChatRequest, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Grounded RAG chat: retrieve from the corpus, answer with citations, persist the session."""
    try:
        service = _get_copilot_service()
        result = await service.chat(db=db, user_id=current_user.sub, chat_request=payload)
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI chat request failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI chat request failed") from exc


@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """List the current user's chat sessions for the copilot history sidebar."""
    try:
        service = _get_copilot_service()
        result = await service.list_sessions(db=db, user_id=current_user.sub)
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Listing chat sessions failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Listing chat sessions failed") from exc


@router.get("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def get_session(session_id: UUID, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Return one chat session's full transcript (replayed in the UI)."""
    try:
        service = _get_copilot_service()
        result = await service.get_session(db=db, user_id=current_user.sub, session_id=session_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Fetching chat session failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Fetching chat session failed") from exc


@router.post("/summarize", status_code=status.HTTP_200_OK)
async def summarize(payload: SummarizeRequest, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Summarize a supplied document or text input."""
    try:
        service = _get_service()
        summarize_code = getattr(getattr(service, "summarize_document", None), "__code__", None)
        if summarize_code is not None and "db" in summarize_code.co_varnames:
            result = await service.summarize_document(db=db, user_id=current_user.sub, summary_request=payload)
            return _success_response(result)

        content = getattr(payload, "text", None)
        document_id = getattr(payload, "document_id", None)
        if not content and document_id:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
            content = document.content_text
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No document content was provided")
        summary = await service.summarize_document(content)
        return _success_response({"summary": summary})
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI summarize request failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI summarize request failed") from exc


@router.post("/qna", status_code=status.HTTP_200_OK)
async def question_answering(payload: DocumentQnARequest, current_user: CurrentUser, db: DBSession) -> dict[str, Any]:
    """Answer a question against stored opportunity context or documents."""
    try:
        service = _get_service()
        if hasattr(service, "answer_question"):
            result = await service.answer_question(db=db, user_id=current_user.sub, qna_request=payload)
        else:
            document_ids = list(getattr(payload, "context_ids", []) or [])
            if getattr(payload, "document_id", None):
                document_ids.append(payload.document_id)
            context = await _load_document_context(db, document_ids)
            result = await service.copilot_chat(message=payload.question, context=context, history=[])
        return _success_response(result)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AI Q&A request failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="AI Q&A request failed") from exc
