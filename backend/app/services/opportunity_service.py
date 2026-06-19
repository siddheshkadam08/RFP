from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, func, or_, select

from app.core.database import AsyncSession
from app.core.exceptions import NotFoundException, ValidationException
from app.models.comment import Comment
from app.models.opportunity import Opportunity
from app.models.user import User

logger = logging.getLogger(__name__)


def _apply_filters(stmt, filters: dict[str, Any]):
    regions = filters.get("regions") or []
    countries = filters.get("countries") or []
    categories = filters.get("categories") or []
    standards = filters.get("standards") or []
    status = filters.get("status")
    text_query = (filters.get("query") or filters.get("text_query") or "").strip()

    if regions:
        stmt = stmt.where(Opportunity.region.in_(regions))
    if countries:
        stmt = stmt.where(Opportunity.country.in_(countries))
    if categories:
        stmt = stmt.where(Opportunity.category.in_(categories))
    if standards:
        for standard in standards:
            stmt = stmt.where(Opportunity.standards.contains([standard]))
    if filters.get("score_min") is not None:
        stmt = stmt.where(Opportunity.score >= filters["score_min"])
    if filters.get("score_max") is not None:
        stmt = stmt.where(Opportunity.score <= filters["score_max"])
    if status:
        if isinstance(status, (list, tuple, set)):
            stmt = stmt.where(Opportunity.status.in_(list(status)))
        else:
            stmt = stmt.where(Opportunity.status == status)

    deadline_from = filters.get("deadline_from") or filters.get("date_from")
    deadline_to = filters.get("deadline_to") or filters.get("date_to")
    created_from = filters.get("created_from")
    created_to = filters.get("created_to")

    if deadline_from is not None:
        stmt = stmt.where(Opportunity.deadline >= deadline_from)
    if deadline_to is not None:
        stmt = stmt.where(Opportunity.deadline <= deadline_to)
    if created_from is not None:
        stmt = stmt.where(Opportunity.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Opportunity.created_at <= created_to)
    if text_query:
        stmt = stmt.where(Opportunity.title.ilike(f"%{text_query}%"))

    return stmt


_SORT_COLUMNS = {
    "title": Opportunity.title,
    "country": Opportunity.country,
    "region": Opportunity.region,
    "institution": Opportunity.institution,
    "category": Opportunity.category,
    "score": Opportunity.score,
    "status": Opportunity.status,
    "created_at": Opportunity.created_at,
    "updated_at": Opportunity.updated_at,
    "deadline": Opportunity.deadline,
}


async def search_opportunities(db: AsyncSession, filters: dict[str, Any]) -> tuple[list[Opportunity], int]:
    """Search opportunities with filtering, sorting, and pagination."""
    page = max(int(filters.get("page", 1)), 1)
    page_size = max(int(filters.get("page_size", 20)), 1)
    offset = (page - 1) * page_size

    base_stmt = _apply_filters(select(Opportunity), filters)
    total_stmt = select(func.count()).select_from(base_stmt.order_by(None).subquery())
    total = await db.scalar(total_stmt)

    column = _SORT_COLUMNS.get(str(filters.get("sort_by") or "created_at"), Opportunity.created_at)
    order = column.asc() if str(filters.get("sort_dir") or "desc").lower() == "asc" else column.desc()

    result = await db.execute(base_stmt.order_by(order).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total or 0)


async def create_opportunity(db: AsyncSession, opportunity_data: dict[str, Any]) -> Opportunity:
    """Create an opportunity record."""
    opportunity = Opportunity(**dict(opportunity_data))
    try:
        db.add(opportunity)
        await db.commit()
        await db.refresh(opportunity)
        return opportunity
    except Exception:
        await db.rollback()
        logger.exception("Failed to create opportunity")
        raise


async def get_opportunity(db: AsyncSession, opp_id: Any) -> Opportunity:
    """Return a single opportunity or raise if missing."""
    result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise NotFoundException("Opportunity not found")
    return opportunity


async def update_opportunity(db: AsyncSession, opp_id: Any, update_data: dict[str, Any]) -> Opportunity:
    """Update an opportunity record."""
    opportunity = await get_opportunity(db, opp_id)
    for field, value in dict(update_data).items():
        if hasattr(opportunity, field):
            setattr(opportunity, field, value)

    try:
        await db.commit()
        await db.refresh(opportunity)
        return opportunity
    except Exception:
        await db.rollback()
        logger.exception("Failed to update opportunity", extra={"opportunity_id": str(opp_id)})
        raise


async def add_comment(db: AsyncSession, opp_id: Any, user_id: Any, content: str) -> Comment:
    """Add a user comment to an opportunity."""
    if not content or not content.strip():
        raise ValidationException("Comment content is required")

    await get_opportunity(db, opp_id)
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise NotFoundException("User not found")

    comment = Comment(opportunity_id=opp_id, user_id=user_id, content=content.strip())
    try:
        db.add(comment)
        await db.commit()
        await db.refresh(comment)
        return comment
    except Exception:
        await db.rollback()
        logger.exception(
            "Failed to add opportunity comment",
            extra={"opportunity_id": str(opp_id), "user_id": str(user_id)},
        )
        raise


async def get_comments(db: AsyncSession, opp_id: Any) -> list[Comment]:
    """Return opportunity comments in chronological order."""
    result = await db.execute(
        select(Comment).where(Comment.opportunity_id == opp_id).order_by(Comment.created_at.asc())
    )
    return list(result.scalars().all())


async def get_opportunity_stats(db: AsyncSession) -> dict[str, Any]:
    """Return aggregate opportunity metrics."""
    total = int(await db.scalar(select(func.count()).select_from(Opportunity)) or 0)

    status_rows = (
        await db.execute(select(Opportunity.status, func.count()).group_by(Opportunity.status))
    ).all()
    region_rows = (
        await db.execute(select(Opportunity.region, func.count()).group_by(Opportunity.region))
    ).all()
    category_rows = (
        await db.execute(select(Opportunity.category, func.count()).group_by(Opportunity.category))
    ).all()

    return {
        "total": total,
        "by_status": {
            (key.value if hasattr(key, "value") else str(key)): count for key, count in status_rows
        },
        "by_region": {str(key): count for key, count in region_rows},
        "by_category": {
            (key.value if hasattr(key, "value") else str(key)): count for key, count in category_rows
        },
    }
