"""A call to a model litellm cannot price must not be reported as free.

LLMMatchVerifier._account asks ``litellm.completion_cost`` for the price and
swallows the exception it raises for a model missing from litellm's map. The
November 2026 re-measurement of the LLM band ran gemini-3.8-flash and
claude-opus-5 through OpenRouter for $2.61 of real spend, and the verifier
recorded $0.00 for both. ``max_cost_usd`` reads the same counter, so a budget set
by the user can never trip for such a model.

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


def _response() -> litellm.ModelResponse:
    verdict = json.dumps({"decision": "match", "confidence": 0.9, "reasoning": "same product"})
    return litellm.ModelResponse(
        model=UNPRICED_MODEL,
        choices=[{"index": 0, "finish_reason": "stop",
                  "message": {"role": "assistant", "content": verdict}}],
        # OpenRouter reports what it charged in usage.cost; a fix may read it.
        usage={"prompt_tokens": 1600, "completion_tokens": 120, "total_tokens": 1720, "cost": 0.011},
    )


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.setattr(llm_verifier.litellm, "completion", lambda **kwargs: _response())
    return LLMMatchVerifier(model=UNPRICED_MODEL, api_key="test-key",
                            low_threshold=0.3, high_threshold=0.95, max_cost_usd=0.001)


def test_the_model_really_is_missing_from_litellms_price_map():
    # Guards the premise: if litellm learns this model's price, pick another one.
    with pytest.raises(Exception, match="isn't mapped"):
        litellm.cost_per_token(model=UNPRICED_MODEL, prompt_tokens=1, completion_tokens=1)


def test_the_call_itself_is_accounted(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)
    stats = verifier.stats()
    assert stats["calls"] == 1
    assert stats["tokens_in"] == 1600


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN BUG: LLMMatchVerifier records $0 for a model litellm cannot price, so "
    "stats() reports a paid call as free and max_cost_usd never trips. Remove when "
    "the verifier uses the provider's reported cost or reports the cost as unknown."))
def test_unpriced_call_is_not_reported_as_free(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)
    assert verifier.stats()["cost_usd"] != 0.0


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN BUG: max_cost_usd reads the same zeroed counter, so a budget can never "
    "stop an unpriced model. Remove with the cost-accounting fix."))
def test_budget_trips_for_an_unpriced_model(verifier):
    verifier.verify({"name": "a"}, {"name": "b"}, 0.5)  # one $0.011 call against a $0.001 cap
    assert verifier.budget_exceeded()
