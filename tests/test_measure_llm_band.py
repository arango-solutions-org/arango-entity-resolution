"""An unparseable LLM reply must count as an abstention, not as "no_match".

The verifier returns decision "error" with llm_called=True when a reply cannot be
parsed. The reconstructed measurement script counted those rows as judged, so a
non-match pair the model failed to answer scored as a correct "no_match". The
published table excluded them (gemini 162/199, opus 160/195); the script did not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("measure_llm_band", REPO_ROOT / "scripts" / "measure_llm_band.py")
measure_llm_band = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure_llm_band)


def _row(decision, truth, score=0.5, called=True):
    return {"llm_decision": decision, "truth": truth, "score": score, "llm_called": called}


def test_unparseable_reply_is_an_abstention_not_a_correct_no_match():
    rows = [
        _row("match", True),
        _row("no_match", True),       # wrong
        _row("error", False),         # unparseable on a non-match pair
    ]
    out = measure_llm_band.summarize(rows, threshold=0.4)
    assert out["judged_by_model"] == 2
    assert out["abstained"] == 1
    assert out["accuracy"]["llm"] == 0.5


def test_threshold_accuracy_uses_the_same_answered_pairs():
    rows = [_row("match", True, score=0.9), _row("error", False, score=0.1)]
    out = measure_llm_band.summarize(rows, threshold=0.5)
    # Had the abstained pair been kept, the threshold would score 2/2 on it.
    assert out["accuracy"]["score_threshold"] == 1.0
    assert out["judged_by_model"] == 1


def test_fallbacks_are_separate_from_abstentions():
    rows = [_row("match", True), _row("no_match", False, called=False)]
    out = measure_llm_band.summarize(rows, threshold=0.4)
    assert out["fallbacks"] == 1
    assert out["abstained"] == 0
    assert out["judged_by_model"] == 1


def test_mcnemar_exact_p_value():
    # 10 discordant pairs all favouring one side: p = 2 * 0.5**10.
    assert measure_llm_band._mcnemar_p(10, 0) == round(2 * 0.5 ** 10, 4)
    assert measure_llm_band._mcnemar_p(5, 5) == 1.0
    assert measure_llm_band._mcnemar_p(0, 0) is None
