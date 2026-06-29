from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSession
from app.core.exceptions import NotFoundException
from app.core.scoring import SCORE_HIGH_MIN
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.report import Report, ReportStatus, ReportType
from app.services import ai_service, export_service

logger = logging.getLogger(__name__)

_CLOSED_STATUSES = {OpportunityStatus.CLOSED_WON, OpportunityStatus.CLOSED_LOST, OpportunityStatus.ARCHIVED}
_STANDARDS = ["XBRL", "SDMX", "ISO 20022", "DPM"]


def _serialize_opportunity(opportunity: Opportunity) -> dict[str, Any]:
    return {
        "id": str(opportunity.id),
        "title": opportunity.title,
        "institution": opportunity.institution,
        "country": opportunity.country,
        "region": opportunity.region,
        "score": opportunity.score,
        "status": opportunity.status.value if hasattr(opportunity.status, "value") else str(opportunity.status),
        "updated_at": opportunity.updated_at.isoformat() if opportunity.updated_at else None,
    }


async def list_reports(db: AsyncSession, page: int, page_size: int) -> tuple[list[Report], int]:
    """Return paginated report records."""
    page = max(page, 1)
    page_size = max(page_size, 1)
    offset = (page - 1) * page_size

    total = await db.scalar(select(func.count()).select_from(Report))
    result = await db.execute(select(Report).order_by(Report.created_at.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), int(total or 0)


async def get_report(db: AsyncSession, report_id: Any) -> Report:
    """Return a report by identifier."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundException("Report not found")
    return report


# --------------------------------------------------------------------------- #
# Synchronous report generation (FR-REPORT-001/002/003/004)
# --------------------------------------------------------------------------- #
def _coerce_report_type(value: Any) -> ReportType:
    try:
        return ReportType(str(getattr(value, "value", value)).lower())
    except ValueError:
        return ReportType.CUSTOM


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _window_start(report_type: ReportType) -> datetime:
    days = 30 if report_type == ReportType.MONTHLY else 7
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _query_opportunities(db: AsyncSession, parameters: dict[str, Any]) -> list[Opportunity]:
    """Base opportunity set, applying optional custom filters (region/category/score/date)."""
    stmt = select(Opportunity)
    regions = parameters.get("regions") or []
    categories = parameters.get("categories") or []
    regulators = parameters.get("regulators") or []
    score_min = parameters.get("score_min")
    if regions:
        stmt = stmt.where(Opportunity.region.in_(regions))
    if categories:
        stmt = stmt.where(Opportunity.category.in_(categories))
    if regulators:
        stmt = stmt.where(Opportunity.institution.in_(regulators))
    if score_min is not None:
        try:
            stmt = stmt.where(Opportunity.score >= int(score_min))
        except (TypeError, ValueError):
            pass
    date_from = _parse_dt(parameters.get("date_from"))
    date_to = _parse_dt(parameters.get("date_to"))
    if date_from:
        stmt = stmt.where(Opportunity.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Opportunity.created_at <= date_to)
    stmt = stmt.order_by(Opportunity.score.desc(), Opportunity.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


def _regional_summary(opportunities: list[Opportunity]) -> list[dict[str, Any]]:
    buckets: dict[str, list[int]] = {}
    for opp in opportunities:
        buckets.setdefault(opp.region or "Unknown", []).append(opp.score or 0)
    rows = [
        {"region": region, "count": len(scores), "avg_score": round(sum(scores) / len(scores), 1) if scores else 0}
        for region, scores in buckets.items()
    ]
    return sorted(rows, key=lambda r: r["count"], reverse=True)


def _pivot_counts(opportunities: list[Opportunity], attr: str) -> list[dict[str, Any]]:
    """Group opportunities by an attribute (e.g. category/status) into {key, count} rows."""
    buckets: dict[str, int] = {}
    for opp in opportunities:
        value = getattr(opp, attr, None)
        key = value.value if hasattr(value, "value") else str(value)
        buckets[key] = buckets.get(key, 0) + 1
    return sorted(({"key": k, "count": v} for k, v in buckets.items()), key=lambda r: r["count"], reverse=True)


def _standards_summary(opportunities: list[Opportunity]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for standard in _STANDARDS:
        needle = standard.lower().replace(" ", "")
        mentions = 0
        for opp in opportunities:
            haystack = " ".join(
                [
                    " ".join(opp.standards or []) if isinstance(opp.standards, list) else str(opp.standards or ""),
                    opp.ai_summary or "",
                    opp.title or "",
                ]
            ).lower().replace(" ", "")
            if needle in haystack:
                mentions += 1
        rows.append({"standard": standard, "mentions": mentions})
    return rows


async def _executive_summary(report_type: ReportType, kpis: dict[str, Any], top: list[Opportunity]) -> str:
    """AI narrative over the KPI digest; best-effort with a templated fallback."""
    kpi_text = "; ".join(f"{k}: {v}" for k, v in kpis.items())
    highlights = "\n".join(f"- {o.title} ({o.region}, score {o.score})" for o in top[:8])
    fallback = (
        f"{report_type.value.title()} intelligence report. {kpi_text}. "
        f"Top opportunities:\n{highlights}" if highlights else f"{report_type.value.title()} intelligence report. {kpi_text}."
    )
    try:
        answer = await ai_service.chat_completion(
            [
                {
                    "role": "system",
                    "content": "You are an RFP intelligence analyst. Write a concise (3-5 sentence) executive "
                    "summary for a leadership report from the supplied metrics and top opportunities. No preamble.",
                },
                {"role": "user", "content": f"Metrics: {kpi_text}\n\nTop opportunities:\n{highlights}"},
            ],
            model="large",
        )
        return answer.strip() or fallback
    except Exception as exc:  # noqa: BLE001 - never fail generation on the AI call
        logger.warning("Report executive summary fell back to template: %s", exc)
        return fallback


async def _assemble(
    db: AsyncSession, report_type: ReportType, parameters: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[Opportunity]]:
    """Build the report ``sections`` + ``kpis`` from the data; returns ``(sections, kpis, base)``."""
    base = await _query_opportunities(db, parameters)
    window_start = _window_start(report_type)
    new_items = [o for o in base if o.created_at and o.created_at >= window_start]
    closed = [o for o in base if o.status in _CLOSED_STATUSES]
    active = [o for o in base if o.status not in _CLOSED_STATUSES]

    kpis = {
        "Generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "Total opportunities": len(base),
        f"New ({'30d' if report_type == ReportType.MONTHLY else '7d'})": len(new_items),
        "Active": len(active),
        "Closed": len(closed),
        f"High priority (score >= {SCORE_HIGH_MIN})": sum(1 for o in base if (o.score or 0) >= SCORE_HIGH_MIN),
        "Regions covered": len({o.region for o in base}),
    }
    sections = {
        "new": new_items,
        "active": active,
        "closed": closed,
        "regional": _regional_summary(base),
        "standards": _standards_summary(base),
        "by_category": _pivot_counts(base, "category"),
        "by_status": _pivot_counts(base, "status"),
    }
    return sections, kpis, base


async def generate_report(
    db: AsyncSession,
    report_type: Any,
    parameters: dict[str, Any],
    user_id: Any,
) -> Report:
    """Synchronously build a multi-sheet Excel report, persist the file, and update status.

    Never raises: on any error the report row is marked FAILED so the request still returns 200.
    """
    parameters = dict(parameters or {})
    rtype = _coerce_report_type(report_type)
    try:
        owner = UUID(str(user_id)) if user_id else None
    except (TypeError, ValueError):
        owner = None

    title = f"{rtype.value.replace('_', ' ').title()} Report"
    report = Report(
        title=title,
        report_type=rtype,
        status=ReportStatus.GENERATING,
        generated_by_id=owner,
        parameters=parameters,
        summary="Generating…",
    )
    db.add(report)
    await db.commit()  # persist the GENERATING row so a later failure still leaves a record
    await db.refresh(report)
    report_id = report.id

    try:
        sections, kpis, base = await _assemble(db, rtype, parameters)
        summary = await _executive_summary(rtype, kpis, base)
        workbook_bytes = export_service.build_report_workbook(rtype, sections, summary, kpis)
        pdf_bytes = export_service.build_report_pdf(rtype, sections, summary, kpis)

        reports_dir = Path(settings.REPORTS_DIR)
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = str((reports_dir / f"{report_id}.xlsx").resolve())
        pdf_path = str((reports_dir / f"{report_id}.pdf").resolve())
        with open(file_path, "wb") as handle:
            handle.write(workbook_bytes)
        with open(pdf_path, "wb") as handle:
            handle.write(pdf_bytes)

        report.status = ReportStatus.COMPLETED
        report.file_path = file_path
        report.summary = summary
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - mark FAILED, never crash the request
        logger.exception("Report generation failed for %s", report_id)
        await db.rollback()
        report = await get_report(db, report_id)
        report.status = ReportStatus.FAILED
        report.summary = f"Generation failed: {exc}"[:500]
        await db.commit()

    await db.refresh(report)
    return report
