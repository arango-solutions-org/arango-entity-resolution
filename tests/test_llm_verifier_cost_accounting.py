"""A call to a model litellm cannot price must not be reported as free.

LLMMatchVerifier used to ask only ``litellm.completion_cost`` for the price and
swallow the exception it raises for a model missing from litellm's map. The
November 2026 re-measurement of the LLM band ran gemini-3.8-flash and
claude-opus-5 through OpenRouter for $2.61 of real spend, and the verifier
recorded $0.00 for both; ``max_cost_usd`` read the same counter, so a budget could
never trip for such a model.

The verifier now takes the provider's reported charge first (OpenRouter returns
it; litellm stores it on the response), falls back to litellm's map, and reports
the cost as unknown when neither can say. An unknown cost makes a cost budget
fail closed.

Only the network call is replaced: ``litellm.completion`` returns a real
``litellm.ModelResponse``, and the real ``completion_cost`` runs on it. The
existing verifier tests mock the whole ``litellm`` module, which is why none of
them could see this.
"""

from __future__ import annotations

import json

import litellm
import pytest

from entity_resolution.reasoning import llm_verifier
from entity_resolution.reasoning.llm_verifier import LLMMatchVerifier

pytestmark = pytest.mark.unit

UNPRICED_MODEL = "openrouter/anthropic/claude-opus-5"
LOCAL_MODEL = "ollama/llama3.1:8b"
USAGE = {"prompt_tokens": 1600, "completion_tokens": 120, "total_tokens": 1720}


def _response(model=UNPRICED_MODEL, usage_cost=None, header_cost=None) -> litellm.ModelResponse:
    verdict = json.dumps({"decision": "match", "confidence": 0.9, "reasoning": "same product"})
    usage = dict(USAGE)
    if usage_cost is not None:
        usage["cost"] = usage_cost
    response = litellm.ModelResponse(
        model=model,
        choices=[{"index": 0, "finish_reason": "stop",
                  "message": {"role": "assistant", "content": verdict}}],
        usage=usage,
    )
    if header_cost is not None:
        # Where litellm's OpenRouter transform puts the charge it reads from usage.cost.
        response._hidden_params = {
            "additional_headers": {"llm_provider-x-litellm-response-cost": header_cost}}
    return response


def _verifier(monkeypatch, response, model=UNPRICED_MODEL, max_cost_usd=0.001):
    monkeypatch.setattr(llm_verifier.litellm, "completion", lambda **kwargs: response)
    return LLMMatchVerifier(model=model, api_key="test-key", low_threshold=0.3,
                            high_threshold=0.95, max_cost_usd=max_cost_usd)


@pytest.fixture
def verifier(monkeypatch):
    # OpenRouter reports what it charged in usage.cost.
    return _verifier(monkeypatch, _response(usage_cost=0.011))


def test_the_model_really_is_missing_from_litellms_price_map():
    # Guards the premise: if litellm learns this model's price, pick another one.
    with pytest.raises(Exception, match="isn't mapped"):
        litellm.cost_per_token(model=UNPRICED_MODEL, prompt_tokens=1, completion_tokens=1)


def test_the_call_itself_is_accounted(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)
    stats = verifier.stats()
    assert stats["calls"] == 1
    assert stats["tokens_in"] == 1600


def test_unpriced_call_is_not_reported_as_free(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)
    stats = verifier.stats()
    assert stats["cost_usd"] == pytest.approx(0.011)
    assert stats["unpriced_calls"] == 0


def test_budget_trips_for_an_unpriced_model(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)  # one $0.011 call against a $0.001 cap
    assert verifier.budget_exceeded()


def test_cost_litellm_copied_from_the_provider_is_used(monkeypatch):
    v = _verifier(monkeypatch, _response(header_cost=0.0112))
    v.verify({"name": "a"}, {"name": "b"}, 0.5)
    assert v.stats()["cost_usd"] == pytest.approx(0.0112)


def test_cost_nobody_reports_is_unknown_not_zero(monkeypatch):
    v = _verifier(monkeypatch, _response(), max_cost_usd=None)
    v.verify({"name": "a"}, {"name": "b"}, 0.5)
    v.verify({"name": "a"}, {"name": "b"}, 0.5)
    stats = v.stats()
    assert stats["calls"] == 2  # no budget set, so the run carries on
    assert stats["cost_usd"] is None
    assert stats["cost_usd_known"] == 0.0
    assert stats["unpriced_calls"] == 2


def test_cost_budget_fails_closed_when_the_cost_is_unknown(monkeypatch):
    v = _verifier(monkeypatch, _response(), max_cost_usd=100.0)
    v.verify({"name": "a"}, {"name": "b"}, 0.5)
    assert v.budget_exceeded()
    second = v.verify({"name": "a"}, {"name": "b"}, 0.5)
    assert second["decision"] == "pending_review"
    assert v.stats()["calls"] == 1


def test_a_model_litellm_prices_at_zero_is_free_not_unknown(monkeypatch):
    # Local models are in litellm's map at $0; they must not trip a cost budget.
    v = _verifier(monkeypatch, _response(model=LOCAL_MODEL), model=LOCAL_MODEL, max_cost_usd=0.001)
    v.verify({"name": "a"}, {"name": "b"}, 0.5)
    stats = v.stats()
    assert stats["cost_usd"] == 0.0
    assert stats["unpriced_calls"] == 0
    assert not v.budget_exceeded()
