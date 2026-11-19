"""Published benchmark figures must equal the committed artifacts they came from.

A FEBRL table in docs/BENCHMARKS.md once had five of nine rows wrong, including
its headline, and the same wrong figures were restated in the README and both
scorecards. Nothing tied a published number to the run that produced it, so the
only way to find the error was to re-measure everything by hand.

Each table checked here now has a committed JSON artifact, written by the
command the document names. A cell is compared at the precision it is printed
at, so the check fails on a changed figure and never on formatting.

The LLM-judge table was absent until November 2026: its first per-pair verdicts
were lost. It was re-measured with every verdict kept, and is checked below,
except for its $/pair column, which the verifier could not record (the section
says so and how the figure was derived instead).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS = (REPO_ROOT / "docs" / "BENCHMARKS.md").read_text(encoding="utf-8")
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _artifact(name: str):
    return json.loads((REPO_ROOT / "docs" / name).read_text(encoding="utf-8"))


def _number(cell: str) -> str:
    """The first number in a table cell, as printed ('**0.9954**', '*0.236 — UNFIT*')."""
    match = re.search(r"[+-]?\d[\d,]*(?:\.\d+)?", cell)
    assert match, f"no number in cell {cell!r}"
    return match.group(0).replace(",", "")


def _agrees(printed: str, value: float) -> bool:
    """True when ``printed`` is ``value`` rounded to the digits shown.

    Half a unit in the last place, not ``round()``: 0.4875 is printed 0.488 by
    half-up rounding and is 0.487 under Python's float round().
    """
    decimals = len(printed.split(".")[1]) if "." in printed else 0
    return abs(float(printed) - value) <= 0.5 * 10 ** -decimals + 1e-9


def _table_after(text: str, heading: str, header_prefix: str) -> List[List[str]]:
    section = text.split(heading, 1)[1]
    lines = section.split(header_prefix, 1)[1].splitlines()[2:]  # skip header remainder + rule
    rows = []
    for line in lines:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    assert rows, f"no table under {heading!r}"
    return rows


# ---------------------------------------------------------------- FEBRL

_FEBRL = {(r["dataset"], r["matcher"]): r for r in _artifact("benchmark_results_febrl.json")["rows"]}


def test_febrl_artifact_has_every_row() -> None:
    assert len(_FEBRL) == 9
    assert all(r["command"].startswith("python scripts/run_er_benchmarks.py") for r in _FEBRL.values())


def test_results_doc_febrl_table_matches_artifact() -> None:
    rows = _table_after(BENCHMARKS, "## Structured multi-field records", "| Dataset | Matcher |")
    assert len(rows) == len(_FEBRL)
    for dataset, matcher, pairwise, at_default, b_cubed in rows:
        record = _FEBRL[(dataset, matcher.strip("*"))]
        for printed, key in ((pairwise, "pairwise_f1"), (at_default, "f1_at_default_0_8"), (b_cubed, "b_cubed_f1")):
            assert _agrees(_number(printed), record[key]), (dataset, matcher, key, printed, record[key])
        # A row the model flagged as unfit must say so in the table.
        assert ("UNFIT" in pairwise) == bool(record["fit_warning"]), (dataset, matcher)


def test_readme_febrl_table_matches_artifact() -> None:
    rows = _table_after(README, "**Deduplication** tasks", "| Dataset | Records | Scoring |")
    label = {"weighted": "weighted", "Fellegi-Sunter (binary)": "FS binary",
             "Fellegi-Sunter (multi-level)": "FS multi-level"}
    for dataset, _records, scoring, pairwise, at_default, b_cubed in rows:
        record = _FEBRL[(dataset, label[scoring.strip("*")])]
        for printed, key in ((pairwise, "pairwise_f1"), (at_default, "f1_at_default_0_8"), (b_cubed, "b_cubed_f1")):
            assert _agrees(_number(printed), record[key]), (dataset, scoring, key, printed, record[key])


# ---------------------------------------------------------------- Leipzig summary

_LINKAGE: Dict[str, dict] = {r["dataset"]: r for r in _artifact("benchmark_results.json")}
_NAME = {"DBLP-ACM": "dblp-acm", "DBLP-Scholar": "dblp-scholar", "Abt-Buy": "abt-buy", "Amazon-Google": "amazon-google"}


def test_results_doc_summary_table_matches_artifact() -> None:
    rows = _table_after(BENCHMARKS, "## Summary", "| Dataset | Records |")
    assert {r[0] for r in rows} == set(_NAME)
    for name, _records, _true, completeness, reduction, pairwise, b_cubed in rows:
        r = _LINKAGE[_NAME[name]]
        checks = (
            (completeness, r["blocking"]["pair_completeness"]),
            (reduction, r["blocking"]["reduction_ratio"]),
            (pairwise, r["matching"]["best_f1"]["f1"]),
            (b_cubed, r["clustering"]["b_cubed"]["f1"]),
        )
        for printed, value in checks:
            assert _agrees(_number(printed), value), (name, printed, value)


def test_readme_linkage_table_matches_artifact() -> None:
    rows = _table_after(README, "**Linkage** tasks", "| Dataset | Records |")
    for name, _records, completeness, pairwise, b_cubed, _magellan in rows:
        r = _LINKAGE[_NAME[name]]
        for printed, value in (
            (completeness, r["blocking"]["pair_completeness"]),
            (pairwise, r["matching"]["best_f1"]["f1"]),
            (b_cubed, r["clustering"]["b_cubed"]["f1"]),
        ):
            assert _agrees(_number(printed), value), (name, printed, value)


# ---------------------------------------------------------------- review-band oracle

def test_oracle_band_table_matches_artifact() -> None:
    artifact = _artifact("benchmark_results_review_band.json")
    assert artifact["dataset"] == "amazon-google"
    rows = _table_after(BENCHMARKS, "### First: how much is winnable at all", "| Band | Pairs |")
    assert len(rows) == len(artifact["bands"])
    for (band, pairs, share, oracle_f1, gain), measured in zip(rows, artifact["bands"]):
        assert int(_number(pairs)) == measured["pairs"], band
        assert _agrees(_number(share), measured["error_share"] * 100), band
        assert _agrees(_number(oracle_f1), measured["oracle_f1"]), band
        assert _agrees(_number(gain), measured["oracle_delta_f1"]), band
    assert f"F1 {artifact['baseline']['f1']}" in BENCHMARKS.split("### First")[0]


# ---------------------------------------------------------------- LLM judges on the band

_JUDGES = {"`llama3.1:8b` (local)": "llama", "`gemini-3.8-flash`": "gemini", "`claude-opus-5`": "opus"}
_LLM = {name: _artifact(f"benchmark_results_llm_band_{name}.json") for name in _JUDGES.values()}


def _signed(cell: str) -> str:
    return _number(cell.replace("\u2212", "-"))  # the table prints a typographic minus


def test_llm_artifacts_judge_the_same_sample() -> None:
    first = next(iter(_LLM.values()))
    for name, artifact in _LLM.items():
        assert artifact["dataset"] == "amazon-google", name
        assert artifact["sampled"] == 200 and len(artifact["rows"]) == 200, name
        assert [r["pair"] for r in artifact["rows"]] == [r["pair"] for r in first["rows"]], name
        assert artifact["accuracy"]["score_threshold"] == first["accuracy"]["score_threshold"], name


def test_llm_judge_table_matches_artifacts() -> None:
    rows = _table_after(BENCHMARKS, "### Then: what an available judge actually does", "| Judge | Accuracy |")
    threshold = next(iter(_LLM.values()))["accuracy"]["score_threshold"]
    by_label = {r[0]: r for r in rows}
    assert _agrees(_number(by_label["score threshold alone"][1]), threshold)
    assert _agrees(_signed(by_label["oracle"][2]), 1 - threshold)
    for label, name in _JUDGES.items():
        _, accuracy, delta, significant, abstained, _cost, latency = by_label[label]
        a = _LLM[name]
        assert _agrees(_number(accuracy), a["accuracy"]["llm"]), (name, accuracy)
        assert _agrees(_signed(delta), a["accuracy"]["llm"] - threshold), (name, delta)
        assert _agrees(_number(abstained), 100 * a["abstained"] / a["sampled"]), (name, abstained)
        assert _agrees(_number(latency), a["median_seconds"]), (name, latency)
        p = a["mcnemar"]["p"]
        if "p<0.0001" in significant:
            assert p < 0.0001 and significant.startswith("yes"), (name, significant, p)
        else:
            assert _agrees(_number(significant.split("p=")[1]), p), (name, significant, p)
            assert significant.startswith("yes") == (p < 0.05), (name, significant, p)
    # $/pair is not in the artifacts (the verifier recorded $0); the section must say so.
    assert "**Cost does not**" in BENCHMARKS


def test_readme_llm_table_matches_artifacts() -> None:
    rows = _table_after(README, "### LLM Match Curation", "| Judge | Accuracy on those pairs |")
    label = {"`ollama/llama3.1:8b` (local)": "llama", "`openrouter/google/gemini-3.8-flash`": "gemini",
             "`openrouter/anthropic/claude-opus-5`": "opus"}
    threshold = next(iter(_LLM.values()))["accuracy"]["score_threshold"]
    for judge, accuracy, _cost in rows:
        expected = threshold if judge == "score threshold alone" else _LLM[label[judge]]["accuracy"]["llm"]
        assert _agrees(_number(accuracy), expected), (judge, accuracy, expected)


# ---------------------------------------------------------------- README performance table

def test_readme_performance_table_matches_artifact() -> None:
    rows = _table_after(README, "## Performance", "| Dataset | Records |")
    assert {r[0] for r in rows} == set(_NAME)
    for name, records, possible, candidates, blocking, scoring in rows:
        r = _LINKAGE[_NAME[name]]
        assert int(_number(records)) == r["records_a"] + r["records_b"], name
        assert possible.endswith("M") and _agrees(_number(possible), r["records_a"] * r["records_b"] / 1e6), name
        assert int(_number(candidates)) == r["blocking"]["candidate_pairs"], name
        assert _agrees(_number(blocking), r["blocking"]["runtime_seconds"]), (name, blocking)
        assert _agrees(_number(scoring), r["matching"]["runtime_seconds"]), (name, scoring)
