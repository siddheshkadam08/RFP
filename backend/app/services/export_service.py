"""Build Excel (.xlsx) exports for opportunities using openpyxl."""
from __future__ import annotations

import io
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_HEADERS = [
    "ID", "Title", "Country", "Region", "Institution",
    "Category", "Score", "Status", "Budget", "Deadline",
]
_WIDTHS = [38, 48, 16, 22, 28, 18, 8, 16, 16, 14]

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
# Score band fills: >=71 green, 41-70 amber, <41 grey (matches getScoreVariant / dashboard).
_GREEN = PatternFill("solid", fgColor="C6EFCE")
_AMBER = PatternFill("solid", fgColor="FFEB9C")
_GREY = PatternFill("solid", fgColor="E7E6E6")


def _enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _score_fill(score: Any) -> PatternFill | None:
    if score is None:
        return None
    if score >= 71:
        return _GREEN
    if score >= 41:
        return _AMBER
    return _GREY


def build_opportunities_workbook(opportunities: Iterable[Any]) -> bytes:
    """Return an .xlsx (bytes) of the given opportunities, formatted per the spec."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Opportunities"

    sheet.append(_HEADERS)
    for col in range(1, len(_HEADERS) + 1):
        cell = sheet.cell(row=1, column=col)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(vertical="center")

    for opp in opportunities:
        deadline = opp.deadline.strftime("%Y-%m-%d") if getattr(opp, "deadline", None) else ""
        score = opp.score if opp.score is not None else ""
        sheet.append([
            str(opp.id),
            opp.title,
            opp.country or "",
            opp.region or "",
            opp.institution or "",
            _enum(opp.category),
            score,
            _enum(opp.status),
            opp.budget or "",
            deadline,
        ])
        fill = _score_fill(opp.score)
        if fill is not None:
            sheet.cell(row=sheet.max_row, column=7).fill = fill

    for index, width in enumerate(_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(_HEADERS))}{sheet.max_row}"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
