"""Single source of truth for opportunity score bands (spec doc04 §14).

Thresholds: ``>=80`` High, ``50-79`` Medium, ``<50`` Low. Everything that buckets a
0-100 score (pipeline, dashboard, reports, Excel export, alerts) imports from here so the
bands never drift apart again.
"""
from __future__ import annotations

SCORE_HIGH_MIN = 80  # score >= this -> "high"
SCORE_MEDIUM_MIN = 50  # score >= this -> "medium" (else "low")


def score_band(score: int | float | None) -> str:
    """Map a 0-100 opportunity score to its band label: 'high' | 'medium' | 'low'."""
    value = int(score or 0)
    if value >= SCORE_HIGH_MIN:
        return "high"
    if value >= SCORE_MEDIUM_MIN:
        return "medium"
    return "low"
