"""Opportunity scoring: the model's breakdown must actually drive the score.

Regression for the prompt/parser key mismatch where the scoring prompt emitted
descriptive keys (``strategic_relevance`` ...) but the parser read short keys
(``strategic`` ...), silently discarding 4 of the 5 LLM components and falling
back to the keyword heuristic.
"""
import json

import pytest

from app.core.scoring import SCORE_HIGH_MIN, SCORE_MEDIUM_MIN, score_band
from app.services import ai_service as A


# --- score_band: spec thresholds (doc04 §14) >=80 High / 50-79 Medium / <50 Low ----

def test_score_band_matches_spec_thresholds():
    assert SCORE_HIGH_MIN == 80 and SCORE_MEDIUM_MIN == 50
    assert score_band(100) == "high"
    assert score_band(80) == "high"      # lower edge of High
    assert score_band(79) == "medium"
    assert score_band(50) == "medium"    # lower edge of Medium
    assert score_band(49) == "low"
    assert score_band(0) == "low"


def test_score_band_handles_none():
    assert score_band(None) == "low"


# --- _pick_component: alias resolution + clamping ----------------------------

def test_pick_component_prefers_prompt_alias_then_short():
    bd = {"strategic_relevance": 92, "budget": 40}
    assert A._pick_component(bd, "strategic", default=10) == 92   # prompt's long key
    assert A._pick_component(bd, "budget", default=10) == 40      # short key fallback alias
    assert A._pick_component(bd, "timeline", default=33) == 33    # absent -> heuristic default


def test_pick_component_clamps_and_tolerates_bad_values():
    assert A._pick_component({"competition": 150}, "competition", default=0) == 100
    assert A._pick_component({"competition": -5}, "competition", default=0) == 0
    assert A._pick_component({"strategic_relevance": "oops"}, "strategic", default=42) == 42
    assert A._pick_component({"strategic_relevance": None}, "strategic", default=42) == 42


# --- _extract_budget_value: unit suffixes (incl. billion) --------------------

def test_extract_budget_value_units():
    assert A._extract_budget_value("EUR 1.2 billion") == 1_200_000_000
    assert A._extract_budget_value("1.5bn") == 1_500_000_000
    assert A._extract_budget_value("$5m") == 5_000_000
    assert A._extract_budget_value("250k") == 250_000
    assert A._extract_budget_value("approx 750000") == 750_000
    assert A._extract_budget_value(None) is None


# --- score_opportunity: end-to-end key alignment -----------------------------

async def test_score_opportunity_uses_model_breakdown(monkeypatch):
    async def fake_json_completion(messages, model="small"):
        return {
            "score": 99,  # the LLM's free-form total is intentionally ignored
            "breakdown": {
                "strategic_relevance": 90,
                "budget_potential": 80,
                "timeline_urgency": 70,
                "technology_match": 60,
                "competition": 50,
            },
            "reasoning": "strong strategic fit",
        }

    monkeypatch.setattr(A, "_json_completion", fake_json_completion)
    result = await A.score_opportunity({"title": "x", "scope": "y"})

    # Every component comes from the model, mapped onto the stored short keys.
    assert result["breakdown"] == {
        "strategic": 90, "budget": 80, "timeline": 70, "technology": 60, "competition": 50,
    }
    # Deterministic weighting: .30*90 + .25*80 + .20*70 + .15*60 + .10*50 = 75
    assert result["score"] == 75
    assert result["reasoning"] == "strong strategic fit"


async def test_score_opportunity_falls_back_on_model_failure(monkeypatch):
    async def boom(messages, model="small"):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(A, "_json_completion", boom)
    result = await A.score_opportunity({"title": "Central bank suptech", "budget": "2 million"})

    # Heuristic fallback still produces a valid score and a full breakdown (no crash).
    assert 0 <= result["score"] <= 100
    assert set(result["breakdown"]) == {"strategic", "budget", "timeline", "technology", "competition"}


# --- _default_score_breakdown: naive vs aware deadline (regression) ----------
# Regression for "Scoring failed: can't subtract offset-naive and offset-aware
# datetimes": a deadline string without a timezone parsed to a naive datetime,
# which crashed when subtracted from the aware ``datetime.now(timezone.utc)``.

def test_default_breakdown_treats_naive_deadline_as_utc():
    naive = A._default_score_breakdown({"deadline": "2999-01-01"})           # no tz -> was a crash
    aware = A._default_score_breakdown({"deadline": "2999-01-01T00:00:00Z"})  # explicit UTC
    assert naive["timeline"] == aware["timeline"]   # naive is treated as UTC
    assert naive["timeline"] == 85                  # far-future -> most relaxed band
    assert set(naive) == {"strategic", "budget", "timeline", "technology", "competition"}


def test_default_breakdown_past_naive_deadline_does_not_crash():
    bd = A._default_score_breakdown({"deadline": "1900-01-01"})
    assert bd["timeline"] == 20                      # long past -> tightest band


async def test_score_opportunity_fallback_survives_naive_deadline(monkeypatch):
    """The fallback breakdown is built outside the try, so a naive deadline used
    to escape score_opportunity entirely and surface as 'Scoring failed'."""
    async def boom(messages, model="small"):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(A, "_json_completion", boom)
    result = await A.score_opportunity({"title": "x", "deadline": "2999-01-01"})
    assert 0 <= result["score"] <= 100
    assert result["breakdown"]["timeline"] == 85


# --- _extract_json: tolerate fenced / trailing-comma / preamble JSON ---------
# Regression for "Title relevance gate fell back to keywords: Expecting value":
# models wrap JSON in ```json fences or emit trailing commas, which the parser
# could not recover, silently degrading every _json_completion caller.

def test_extract_json_plain():
    assert A._extract_json('{"relevant_indices": [0, 1, 2]}') == {"relevant_indices": [0, 1, 2]}


def test_extract_json_strips_code_fences():
    assert A._extract_json('```json\n{"relevant_indices": [0, 1]}\n```') == {"relevant_indices": [0, 1]}


def test_extract_json_drops_trailing_commas():
    assert A._extract_json('{"relevant_indices": [0, 1, 2,],}') == {"relevant_indices": [0, 1, 2]}


def test_extract_json_ignores_preamble():
    assert A._extract_json('Here you go:\n{"relevant_indices": [3]}') == {"relevant_indices": [3]}


def test_extract_json_raises_when_no_json():
    with pytest.raises(json.JSONDecodeError):
        A._extract_json("no json here at all")
