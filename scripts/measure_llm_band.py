#!/usr/bin/env python3
"""What does an actual LLM judge do on a clerical-review score band?

``measure_review_band.py`` bounds what ANY adjudicator could win on a band. This
measures what a real one does. It runs the project's own ``LLMMatchVerifier``,
not a bespoke prompt, so the result describes what would ship: prompt, parsing,
fallback behaviour and cost accounting included.

A sample of pairs is drawn from the band with a fixed seed, and each is judged
by the model. It is scored on:

* ACCURACY against the best score threshold's accuracy on the same pairs. A
  judge that cannot beat the threshold is worse than no judge.
* COST and LATENCY per pair, from the verifier's own accounting.

When the LLM errors or its reply fails to parse, the verifier answers from the
raw score. Those fallbacks are counted separately and never credited to the
model.

THIS SCRIPT SPENDS MONEY on a hosted provider (about $0.40 per 200 pairs for
gemini-3.8-flash, and $2.40 for claude-opus-5, as measured in September 2026),
and it sends record content to that provider. A local ``ollama/...`` model
costs nothing.

Usage::

    python scripts/measure_llm_band.py --dataset amazon-google \\
        --port 8529 --password "$ARANGO_ROOT_PASSWORD" \\
        --model openrouter/google/gemini-3.8-flash --band 0.30,0.95 --sample 200 \\
        --output docs/benchmark_results_llm_band_gemini.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

_spec = importlib.util.spec_from_file_location("bench", REPO / "scripts" / "run_er_benchmarks.py")
bench = importlib.util.module_from_spec(_spec)
sys.modules["bench"] = bench
_spec.loader.exec_module(bench)

from entity_resolution.reasoning.llm_verifier import LLMMatchVerifier  # noqa: E402


def _extra_args(argv):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--model", default="ollama/llama3.1:8b")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--band", default="0.30,0.95")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--sample-seed", type=int, default=20260919)
    ap.add_argument("--entity-type", default="product")
    return ap.parse_known_args(argv)


def _mcnemar_p(b: int, c: int) -> float | None:
    """Exact two-sided McNemar p-value from the two discordant counts."""
    n = b + c
    if n == 0:
        return None
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def summarize(rows, threshold):
    """Score the judge against the threshold on the pairs the model answered.

    A reply the verifier could not parse comes back as decision "error" with
    llm_called=True. It is an abstention, not a "no_match": counting it would
    credit the model with every non-matching pair it failed to answer. Both
    accuracies are computed on the same answered pairs so they stay comparable.
    """
    answered = [r for r in rows if r["llm_called"] and r["llm_decision"] in ("match", "no_match")]
    abstained = sum(1 for r in rows if r["llm_called"]) - len(answered)

    def _acc(pred):
        return round(sum(pred(r) == r["truth"] for r in answered) / len(answered), 4) if answered else None

    llm_right = [(r["llm_decision"] == "match") == r["truth"] for r in answered]
    thr_right = [(r["score"] >= threshold) == r["truth"] for r in answered]
    b = sum(1 for m, t in zip(llm_right, thr_right) if m and not t)
    c = sum(1 for m, t in zip(llm_right, thr_right) if t and not m)
    return {
        "judged_by_model": len(answered),
        "abstained": abstained,
        "fallbacks": len(rows) - sum(1 for r in rows if r["llm_called"]),
        "accuracy": {
            "llm": _acc(lambda r: r["llm_decision"] == "match"),
            "score_threshold": _acc(lambda r: r["score"] >= threshold),
            "always_match": _acc(lambda r: True),
        },
        "mcnemar": {"llm_only_right": b, "threshold_only_right": c, "p": _mcnemar_p(b, c)},
    }


def main() -> int:
    extra, rest = _extra_args(sys.argv[1:])
    args = bench.build_parser().parse_args(rest)
    if args.dataset not in bench.ALL_SPECS:
        raise SystemExit("--dataset must name one dataset, not a group")
    lo, hi = (float(x) for x in extra.band.split(","))

    spec = bench.ALL_SPECS[args.dataset]
    records, truth = bench.load_dataset(spec, Path(args.data_dir))
    by_key = {r["_key"]: r for r in records}
    db = bench._connect(args)
    collection = f"llmband_{args.dataset.replace('-', '_')}"
    view = f"{collection}_view"
    bench._load_records(db, collection, records)
    bench._create_view(db, view, collection, analyzer=args.analyzer)
    try:
        candidates = bench.generate_candidates(db, collection, view, args, is_dedup=spec.is_dedup)
        scored, _ = bench.score_pairs(db, collection, candidates, args, spec=spec)
    finally:
        if not args.keep:
            if any(v["name"] == view for v in db.views()):
                db.delete_view(view)
            if db.has_collection(collection):
                db.delete_collection(collection)

    by_pair = {(a, b) if a < b else (b, a): s for a, b, s in scored}
    best, _ = bench.sweep_thresholds(scored, truth)
    thr = best["threshold"]
    band = sorted(p for p, s in by_pair.items() if lo <= s < hi)
    sample = random.Random(extra.sample_seed).sample(band, min(extra.sample, len(band)))

    # The verifier's own band must be the band under test, or verify() takes
    # its fast path and never calls the model.
    verifier = LLMMatchVerifier(
        model=extra.model, base_url=extra.base_url,
        low_threshold=lo, high_threshold=hi,
        entity_type=extra.entity_type, timeout_seconds=120,
    )
    print(f"{args.dataset}: band [{lo},{hi}) holds {len(band):,} pairs; judging "
          f"{len(sample)} with {extra.model}")

    rows = []
    for i, (a, b) in enumerate(sample, 1):
        t0 = time.time()
        res = verifier.verify(by_key[a], by_key[b], by_pair[(a, b)])
        rows.append({
            "pair": [a, b], "score": by_pair[(a, b)], "truth": (a, b) in truth,
            "llm_decision": res.get("decision"), "llm_confidence": res.get("confidence"),
            "llm_called": bool(res.get("llm_called")), "seconds": round(time.time() - t0, 3),
        })
        if i % 25 == 0 or i == len(sample):
            print(f"  {i}/{len(sample)}", flush=True)

    stats = verifier.stats()
    result = {
        "dataset": args.dataset, "model": extra.model, "band": [lo, hi],
        "band_pairs": len(band), "sampled": len(sample), "sample_seed": extra.sample_seed,
        "best_threshold": thr,
        **summarize(rows, thr),
        "median_seconds": round(statistics.median(r["seconds"] for r in rows), 3) if rows else None,
        "provider_stats": {k: stats.get(k) for k in ("calls", "tokens_in", "tokens_out", "cost_usd", "parse_failures")},
        "rows": rows,
    }
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
