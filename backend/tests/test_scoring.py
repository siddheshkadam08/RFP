"""Opportunity scoring: the model's breakdown must actually drive the score.

Regression for the prompt/parser key mismatch where the scoring prompt emitted
descriptive keys (``strategic_relevance`` ...) but the parser read short keys
(``strategic`` ...), silently discarding 4 of the 5 LLM components and falling
back to the keyword heuristic.
"""
from app.services import ai_service as A


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
