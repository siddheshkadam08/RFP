from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, literal_column, select

from app.core.database import AsyncSession
from app.core.scoring import SCORE_HIGH_MIN
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.source import Source

logger = logging.getLogger(__name__)


async def get_summary(db: AsyncSession) -> dict[str, float | int]:
    """Return top-level dashboard summary metrics."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    total_opportunities = int(await db.scalar(select(func.count()).select_from(Opportunity)) or 0)
    high_priority = int(
        await db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.score >= SCORE_HIGH_MIN)) or 0
    )
    new_this_week = int(
        await db.scalar(
            select(func.count()).select_from(Opportunity).where(Opportunity.created_at >= week_ago)
        )
        or 0
    )
    active_rfps = int(
        await db.scalar(
            select(func.count())
            .select_from(Opportunity)
            .where(Opportunity.status == OpportunityStatus.ACTIVE)
        )
        or 0
    )
    regions_covered = int(await db.scalar(select(func.count(func.distinct(Opportunity.region)))) or 0)
    crawl_success_rate = float(await db.scalar(select(func.avg(Source.success_rate))) or 0.0)

    return {
        "total_opportunities": total_opportunities,
        "high_priority": high_priority,
        "new_this_week": new_this_week,
        "active_rfps": active_rfps,
        "regions_covered": regions_covered,
        "crawl_success_rate": round(crawl_success_rate, 2),
    }


async def get_trends(db: AsyncSession) -> list[dict[str, int | str]]:
    """Return weekly opportunity creation counts for the last 12 weeks."""
    today = datetime.now(timezone.utc)
    current_week_start = today - timedelta(days=today.weekday())
    start_week = current_week_start - timedelta(weeks=11)

    # Render the truncation unit as a SQL literal (not a bind parameter) and reuse a
    # single expression object. If we passed "week" as a normal argument, SQLAlchemy
    # would emit a distinct bind parameter for each occurrence (SELECT/GROUP BY/ORDER BY),
    # and PostgreSQL cannot prove those parameters are equal -- so it rejects created_at
    # as not grouped ("must appear in the GROUP BY clause"). A literal makes all three
    # render identically as date_trunc('week', opportunities.created_at).
    week = func.date_trunc(literal_column("'week'"), Opportunity.created_at)

    rows = (
        await db.execute(
            select(week, func.count())
            .where(Opportunity.created_at >= start_week)
            .group_by(week)
            .order_by(week)
        )
    ).all()

    counts = {
        period.date().isoformat(): count
        for period, count in rows
        if period is not None
    }

    trends: list[dict[str, int | str]] = []
    for index in range(12):
        week_start = (start_week + timedelta(weeks=index)).date().isoformat()
        trends.append({"period": week_start, "count": int(counts.get(week_start, 0))})
    return trends


async def get_heatmap(db: AsyncSession) -> list[dict[str, int | str]]:
    """Return grouped region and country counts for heatmap visualization."""
    rows = (
        await db.execute(
            select(Opportunity.region, Opportunity.country, func.count())
            .group_by(Opportunity.region, Opportunity.country)
            .order_by(func.count().desc(), Opportunity.region, Opportunity.country)
        )
    ).all()
    return [
        {"region": str(region), "country": str(country), "count": int(count)}
        for region, country, count in rows
    ]
