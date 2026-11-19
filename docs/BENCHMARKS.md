# Benchmark Results

Measured results for `arango-entity-resolution` on the standard public
record-linkage benchmarks, so matching quality is **verifiable rather than
asserted**. Every number here is reproducible with one command (see
[Reproducing](#reproducing)).

**Version:** 3.8.0 · **Measured:** 2026-08-02 · **ArangoDB:** 3.12 (single node,
Docker) · **Hardware:** Apple Silicon laptop, single process

## Summary

| Dataset | Records | True pairs | Pair completeness | Reduction ratio | Pairwise F1 | B-cubed F1 |
|---|---|---|---|---|---|---|
| DBLP-ACM | 2,616 + 2,294 | 2,224 | **1.000** | 0.99462 | **0.937** | 0.977 |
| DBLP-Scholar | 2,616 + 64,263 | 5,347 | 0.996 | 0.99960 | 0.840 | **0.987** |
| Abt-Buy | 1,081 + 1,092 | 1,097 | 0.957 | 0.99077 | 0.541 | 0.779 |
| Amazon-Google | 1,363 + 3,226 | 1,300 | 0.890 | 0.99413 | 0.488 | 0.852 |

Full detail:

| Dataset | Candidates | Pairwise P | Pairwise R | Pairwise F1 @ thr | F1 @ 0.8 default | B-cubed P | B-cubed R | Blocking | Scoring |
|---|---|---|---|---|---|---|---|---|---|
| DBLP-ACM | 32,278 | 0.9308 | 0.9433 | 0.9370 @ 0.77 | 0.9352 | 0.9797 | 0.9743 | 7.1s | 0.3s |
| DBLP-Scholar | 68,057 | 0.7851 | 0.9027 | 0.8398 @ 0.50 | 0.6609 | 0.9853 | 0.9888 | 1160s | 0.8s |
| Abt-Buy | 10,895 | 0.5144 | 0.5706 | 0.5411 @ 0.35 | 0.0670 | 0.7732 | 0.7842 | 1.7s | 0.2s |
| Amazon-Google | 25,808 | 0.4618 | 0.5162 | 0.4875 @ 0.34 | 0.0370 | 0.8431 | 0.8610 | 16.2s | 1.0s |

The largest dataset produces the **best** entity-level result (B-cubed 0.987 over
66,879 records): blocking retained 99.6% of true pairs while eliminating 99.96%
of the 168M-pair cross product. It is also by far the slowest — see
[Scale](#scale-limits).

## How to read these numbers

**These are unsupervised results.** No labelled training pairs were used — only
blocking, configured field weights and string similarity. That is the relevant
comparison class for a library used on a new dataset with no ground truth, and
it is why the numbers below sit near classic supervised baselines rather than at
the top of published leaderboards.

**Pair completeness** is the share of true pairs surviving blocking — the ceiling
on achievable recall. **Reduction ratio** is the share of the full cross product
eliminated. Both are reported together because a blocker can always buy recall
with pairs.

**Pairwise F1** is quoted at the best-F1 operating point found by sweeping the
threshold, which is the convention in the literature. The harness also reports F1
at the configured default, and the gap is large (Abt-Buy 0.541 best vs 0.067 at
0.8) — threshold choice matters more than any other single configuration
decision. See [Threshold selection](#threshold-selection).

**B-cubed F1** is the entity-level metric, computed per record over the final
clusters, and it penalises over- and under-merging symmetrically. It is
consistently higher than pairwise F1 here because clustering recovers correct
groupings even where individual pair scores are borderline. Pairwise metrics are
known to be optimistic on large clusters; B-cubed is the stricter entity bar and
is rarely published by comparable tools.

## Context: published results on the same datasets

Approximate figures from the literature, for orientation. **Not run on this
hardware or by this project** — cite them as context, not as head-to-head
measurements.

| Dataset | Magellan (supervised ML) | DeepMatcher (supervised DL) | Ditto (PLM) | GPT-4 (zero-shot) | **This library (unsupervised)** |
|---|---|---|---|---|---|
| DBLP-ACM | ~0.98 | ~0.98 | ~0.99 | — | **0.937** |
| DBLP-Scholar | ~0.89 | ~0.94 | ~0.95 | — | **0.840** |
| Abt-Buy | ~0.43 | ~0.62 | ~0.91 | ~0.96 | **0.541** |
| Amazon-Google | ~0.49 | ~0.69 | ~0.75 | — | **0.488** |

The honest reading:

- **DBLP-ACM** — 0.937 against ~0.98 supervised. Clean, structured
  bibliographic data; the remaining gap is where trained models earn their keep.
- **DBLP-Scholar** — 0.840 against Magellan's supervised ~0.89, again with no
  labels, and B-cubed 0.987 at the entity level.
- **Abt-Buy** — 0.541 exceeds Magellan's supervised ~0.43 with no labels.
- **Amazon-Google** — 0.488 is level with Magellan's supervised ~0.49.
- Against PLM/LLM matchers (Ditto, GPT-4) there is a wide gap on the noisy
  product datasets. Closing it needs a learned or LLM matcher tier, not better
  string similarity. That tier has since been measured — see
  [LLM verification of the ambiguous band](#llm-verification-of-the-ambiguous-band-measured).
  A competent model is worth +0.25 accuracy on the pairs the score cannot settle,
  for a few dollars a run; a small local model makes things worse.

## Method

Both sources are loaded into a single ArangoDB collection carrying a `_source`
marker, and candidate and truth pairs are restricted to cross-source pairs. The
library's blocking strategies are dedup-shaped (one collection against itself),
so this runs linkage through the real pipeline rather than a bespoke path.

1. **Blocking** — `BM25BlockingStrategy` over an ArangoSearch view
   (`text_en` analyzer), token match mode, `bm25_threshold=1.0`,
   `limit_per_entity=20`.
2. **Similarity** — `BatchSimilarityService` with word-based **Jaccard** over
   two fields: `title` (weight 0.7) and `body` (0.3), lower-cased, punctuation
   removed, whitespace collapsed.
3. **Clustering** — connected components over pairs above threshold.
4. **Metrics** — `entity_resolution.services.cluster_metrics`
   (`b_cubed`, `pairwise_closure_metrics`).

Two configuration choices materially affect the outcome and are worth stating:

- **Word-based Jaccard, not Jaro-Winkler.** These are long multi-word texts;
  edit-distance measures are designed for short strings like personal names.
  Scoring Abt-Buy with Jaro-Winkler over the concatenated text gives F1 **0.253**
  versus **0.541** for Jaccard over split fields — a 2.1× difference from the
  similarity function alone.
- **Title and body compared separately.** Concatenating them lets a 200-word
  description drown out the title, which carries most of the discriminating
  signal.

## LLM verification of the ambiguous band: measured

The library can route pairs whose score falls in an uncertain band to a language
model. The tier had shipped unmeasured, which is the gap this section closes.
All figures below are Amazon-Google, the hardest of the four linkage datasets,
where the weighted matcher scores F1 0.4875.

### First: how much is winnable at all

An oracle — a judge that is free, instant and right every time — bounds what any
adjudicator can deliver. If the oracle is worth little, the tier is not worth
building with any model.

| Band | Pairs | Share of all errors | Oracle F1 | Gain |
|---|---|---|---|---|
| **[0.55, 0.80)** *(shipped default)* | 323 | **8.5%** | 0.5097 | +0.0222 |
| [0.40, 0.90) | 962 | 31.9% | 0.5827 | +0.0952 |
| **[0.30, 0.95)** | 1,932 | **61.0%** | 0.7351 | **+0.2476** |
| [0.20, 1.01) | 4,055 | 79.7% | 0.8759 | +0.3885 |
| every candidate | 25,808 | 89.9% | 0.9418 | +0.4543 |

**The shipped band is in the wrong place.** It holds 8.5% of the errors, so a
perfect judge on it is worth +0.022 — true whichever model does the judging.
Widen it to [0.30, 0.95) and the same perfect judge is worth +0.2476. The band
assumes matches cluster high and non-matches low, which is exactly what does not
happen here: the unsupervised threshold selector already *declines* on both
product datasets because the distribution has no valley.

The all-candidates row is a useful consistency check: perfect judgment over every
candidate gives precision 1.0 and recall equal to blocking recall (0.890), hence
F1 0.9418. Blocking is the hard cap, but only once judgment is near-perfect.

This table is free to reproduce, since no model is called, and is checked against
its committed artifact:

```bash
python scripts/measure_review_band.py --dataset amazon-google \
  --port 8529 --password "$ARANGO_ROOT_PASSWORD" \
  --output docs/benchmark_results_review_band.json
```

### Then: what an available judge actually does

200 pairs sampled from [0.30, 0.95), judged through the library's own
`LLMMatchVerifier` — its prompt, its parsing, its fallbacks — not a bespoke
harness.

Every row below is backed by a committed artifact holding all 200 per-pair
verdicts, re-measured on November 16, 2026 against a disposable ArangoDB 3.12
container. The figures first published here (September 19–21) came from a
script outside the repository whose verdicts were lost; the re-run reproduced
them to within 0.005 accuracy. The run sends record content to the provider and
costs about $2.66 for both hosted models, so it is not run automatically:

```bash
python scripts/measure_llm_band.py --dataset amazon-google \
  --port <disposable-db-port> --password "$ARANGO_TEST_PASSWORD" \
  --model openrouter/google/gemini-3.8-flash --band 0.30,0.95 --sample 200 \
  --output docs/benchmark_results_llm_band_gemini.json
# likewise --model ollama/llama3.1:8b (…_llama.json)
# and --model openrouter/anthropic/claude-opus-5 (…_opus.json)
```

| Judge | Accuracy | vs threshold | Significant? | Abstained | $/pair | Median latency |
|---|---|---|---|---|---|---|
| score threshold alone | 0.565 | — | — | — | $0 | — |
| `llama3.1:8b` (local) | 0.510 | −0.055 | no (McNemar p=0.20) | 0% | $0 | 1.6s |
| `gemini-3.8-flash` | **0.810** | **+0.245** | yes (p<0.0001) | 0% | $0.0020 | 3.5s |
| `claude-opus-5` | **0.820** | **+0.255** | yes (p<0.0001) | 0% | $0.0112 | 2.5s |
| oracle | 1.000 | +0.435 | — | — | — | — |

Accuracy, abstentions, significance and latency come straight from the
artifacts. **Cost does not**: the verifier that produced them recorded $0 for
both hosted models, because litellm has no price for them and the verifier
swallowed the pricing error (see the defect note below; it is fixed, so a re-run
records OpenRouter's own charge). The $/pair column is each artifact's token
counts multiplied by OpenRouter's list prices on the day of the run ($0.825 /
$4.125 per million input/output tokens for gemini, $5 / $25 for Opus), which
totals $2.66 against an account spend of $2.61 over the same window.

**The cheap frontier model nearly equals the expensive one**: 0.810 against
0.820, a difference well inside sampling noise on 200 pairs. Opus costs 5.5x
more for nothing measurable. Over the full 1,932-pair band that is **$3.93
against $21.73**.

**A small local model is not merely weaker, it is unusable here.** llama3.1:8b
answered "match" for 87% of pairs when 38% were matches: recall 1.000, precision
0.437. It essentially never says no. The accuracy gap against the plain threshold
is *not* statistically significant (p=0.20), so the honest claim is "no evidence
it helps" rather than "it is worse" — but there is certainly no case for shipping
it.

**Confidence gating does not rescue it.** The usual mitigation is to override the
score only when the model is confident. llama's confidence came back between 0.7
and 0.8 for 195 of 200 pairs, and its 98 false positives all sit between 0.7 and
0.9; above a 0.83 cutoff it touches 3 of 200 pairs. A signal that does not vary
cannot be thresholded. Opus spreads its confidence far wider (26 distinct values
against 4 for llama), but gemini matched Opus's accuracy with 7, so confidence
range alone does not predict performance.

**What improves is recall, not precision.** All three judges over-merge. Opus
says "match" on 55% of pairs where truth is 38%; precision 0.682 against recall
0.987 (gemini: 0.673 and 0.974). If precision is the binding constraint, this
tier is the wrong instrument.

Extrapolating the observed accuracy linearly onto the oracle's +0.2476 puts a
frontier model at roughly **+0.14 F1** on this dataset, for under $4 — the
largest single quality gain available on the dataset where the library is
weakest. That extrapolation is crude and is not quoted as a headline anywhere.

### A defect this exposed

The first gemini run abstained on **28% of pairs**: the verifier capped responses
at 256 tokens, verbose models ran past it mid-JSON, and the truncated verdict was
discarded as unparseable. Raising the cap took parse failures from 57 to 1. Terse
models barely triggered it (Opus lost 5, llama none), so it was invisible until a
verbose model was tried — and any measurement taken through one was silently
computed on whichever subset happened to answer briefly. Fixed in `908b108`;
the budget is now `max_response_tokens`, defaulting to 1024.

The November re-run exposed two more. The reconstructed script counted a reply
the verifier could not parse as a "no_match" verdict, crediting the model with
every non-matching pair it failed to answer; it now counts it as an abstention,
as the original measurement did (`tests/test_measure_llm_band.py`). And the
verifier's cost accounting read prices only from litellm's model map, so for a
model that map does not list it recorded $0 without a warning, and
`max_cost_usd` could never trip for such a model. It now takes the charge the
provider reports (OpenRouter returns one with every response), falls back to
litellm's map, and otherwise reports the cost as unknown (`cost_usd: None`,
counted in `unpriced_calls`), which makes a cost budget stop further calls
(`tests/test_llm_verifier_cost_accounting.py`).

## Blocking: which field to search

`BM25BlockingStrategy` searches one field. The benchmark harness concatenates
title and body into `text` and searches that. On Amazon-Google, searching `title`
alone is strictly better **as blocking**:

| Configuration | Candidate pairs | Pair completeness | Reduction ratio | Time |
|---|---|---|---|---|
| `text` @20 *(default)* | 25,808 | 0.8900 | 0.99413 | 12s |
| **`title` @20** | **19,513** | **0.9815** | **0.99556** | **2s** |
| `text` @20 + `title` @20 | 37,494 | 0.9931 | 0.99147 | — |

+0.092 completeness with 24% *fewer* pairs and 4.7x faster. The cause is the one
already documented for scoring: a long description floods the BM25 term space and
drowns the title. That lesson had been applied to similarity and never to
blocking.

**It does not improve end-to-end quality.** Pairwise F1 goes 0.4875 → 0.4775 and
B-cubed 0.8519 → 0.8472, because precision falls further than recall rises. With
a 0.890 ceiling the matcher was achieving 0.516 recall — using 58% of the
headroom it already had. Raising a ceiling you are nowhere near buys nothing;
the scorer is the binding constraint on this dataset, which is what the LLM
section above is about.

**And it reverses on Abt-Buy** (`text` 0.9572 against `title` 0.9508), so it
cannot be hardcoded. `--blocking-field` exists to make the choice explicit; the
default is unchanged.

## Scoring method: weighted similarity vs Fellegi-Sunter

Both scoring paths were measured on identical candidates. FS training is
unsupervised — EM sees only the candidate pairs, `u` is measured from random
record pairs, and the truth file is never touched.

| Dataset | Weighted F1 | FS F1 | Weighted B-cubed | FS B-cubed |
|---|---|---|---|---|
| DBLP-ACM | **0.937** | 0.868 | **0.977** | 0.942 |
| Abt-Buy | **0.541** | 0.117 | **0.779** | 0.690 |
| Amazon-Google | **0.488** | 0.127 | **0.852** | 0.842 |

**Weighted similarity wins on all three, decisively on the product datasets.**
That is the opposite of what the sophistication of the two methods suggests, and
the reason is specific: **FS binarises each field to agree/disagree at a
threshold, and that destroys the gradation continuous similarity relies on.**

The trained models show it directly. On Abt-Buy, FS learned
`m = {title: 0.822, body: 0.0}` with `lambda = 0.0065`: word-based Jaccard over
long product descriptions essentially never reaches the 0.85 agreement cutoff, so
`body` never agrees even among true matches, almost every comparison vector is
all-zeros, and recall collapses to 0.062. Precision is a perfect 1.000 — FS is
not wrong about what it finds, it just finds almost nothing.

Lowering the agreement cutoff does not rescue it, because it inflates the
inferred match class instead:

| Agreement threshold | DBLP-ACM FS F1 | learned lambda |
|---|---|---|
| 0.85 | **0.868** | 0.118 |
| 0.50 | 0.601 | 0.198 |
| 0.30 | 0.401 | 0.455 |

### Term-frequency adjustment: validated

Ablating TF adjustment inside the FS path isolates its contribution:

| Dataset | FS with TF | FS without TF | Delta |
|---|---|---|---|
| DBLP-ACM | **0.868** | 0.784 | **+0.084** (+10.7% relative) |
| Amazon-Google | 0.127 | 0.127 | 0.000 |

TF adjustment is a **real, measurable gain of +0.084 F1** where records share
identical values (DBLP-ACM titles and author strings repeat exactly across the two
sources), and is **inert rather than harmful** on free text, where no two product
descriptions are byte-identical so the exact-agreement condition never fires. It
lifts precision-recall balance markedly: without TF, FS sits at P 0.953 / R 0.666;
with it, P 0.796 / R 0.955.

### What this means in practice

- **Default to weighted similarity for text-heavy data.** It is the better
  matcher on every dataset here, and it is the configuration all headline numbers
  in this document use.
- **FS earns its place on structured, multi-field records** — identifiers, dates,
  codes, postal fields — where exact agreement is meaningful. This began as a
  conjecture with no evidence behind it, since every dataset above compares two
  free-text fields. It has since been tested on FEBRL person records and holds —
  decisively at the shipped threshold, narrowly at the best swept one, and only
  with comparison levels: see
  [Structured multi-field records](#structured-multi-field-records-where-fellegi-sunter-wins).
- **Multi-level comparisons are the binding constraint, not a refinement.**
  Splink-style levels (exact / fuzzy-close / else, each with its own m/u) let FS
  keep the gradation it otherwise discards. They have since been implemented and
  measured — see [Multi-level comparisons](#multi-level-comparisons-measured).

This is the result the benchmark existed to produce. Three statistical fixes
landed in the FS path — a null comparison level, unbiased `u` from random pairs,
and TF adjustment — and each is correct and unit-tested. Measured end to end,
one of them (TF) delivers a clear gain, and the path as a whole still loses to
the simpler matcher because of a design property none of them addressed. Without
these measurements the reasonable assumption would have been the reverse.

### Multi-level comparisons: measured

Comparison levels replace the single agree/disagree cutoff with ordered bands,
each with its own learned m/u (`similarity.comparison_levels`). This is the fix
the section above named as the binding constraint. It works — substantially —
and it still does not overtake weighted similarity.

| Dataset | Weighted F1 | FS binary | **FS multi-level** | Bands used |
|---|---|---|---|---|
| DBLP-ACM | **0.937** | 0.868 | 0.914 | 0.9 / 0.6 |
| Abt-Buy | **0.541** | 0.117 | 0.505 | 0.6 / 0.35 |
| Amazon-Google | **0.488** | 0.127 | 0.446 | 0.6 / 0.35 *(transferred)* |

B-cubed moves the same way: DBLP-ACM 0.942 → 0.965, Abt-Buy 0.690 → 0.730.

**The collapse is fixed.** On the product datasets FS went from unusable to
competitive — Abt-Buy 4.3x (0.117 → 0.505), Amazon-Google 3.5x (0.127 → 0.446).
The diagnosis was right: binarising at one cutoff was destroying the signal, and
retaining the gradation recovers almost all of it.

**Weighted similarity still wins on all three.** Multi-level closes most of the
gap but never crosses it. The practical recommendation is therefore unchanged —
weighted remains the default, and every headline number in this document uses it.

**Multi-level also makes FS far less sensitive to the decision threshold.** On
DBLP-ACM, F1 at the shipped 0.8 default rose from 0.771 to 0.911, and
unsupervised threshold selection improved from 0.771 to 0.833. A model that
degrades gracefully when the operating point is wrong is worth something
independently of its peak F1, since the peak assumes a threshold the user has to
find.

#### Band placement matters more than having bands

Bands must sit where the similarity distribution actually separates. The same
dataset, four settings:

| Abt-Buy bands | Pairwise F1 |
|---|---|
| 0.9 / 0.6 | 0.388 |
| **0.6 / 0.35** | **0.505** |
| 0.5 / 0.3 / 0.15 | 0.348 |
| 0.4 / 0.2 | 0.423 |

Bands copied from DBLP-ACM (0.9 / 0.6) score 0.388 on Abt-Buy — better than
binary's 0.117, but a quarter below what correctly placed bands achieve. Word-based
Jaccard over long product descriptions rarely exceeds ~0.6 even for true matches,
so a 0.9 band is nearly always empty and the model wastes a level. More bands is
not better either: the four-level 0.5/0.3/0.15 setting is the *worst* of the four.

#### Automatic band placement removes the tuning caveat

The bands above were hand-placed, and for DBLP-ACM and Abt-Buy they were chosen
by looking at benchmark F1 — selection on labels a deployment does not have.
`--comparison-levels auto` infers them per field from the observed similarity
distribution instead, using no labels at all:

| Dataset | Hand-placed F1 | **Auto F1** | Bands inferred |
|---|---|---|---|
| DBLP-ACM | 0.914 | **0.920** | title 0.97 / 0.55, body 0.97 / 0.55 |
| Abt-Buy | 0.505 | **0.506** | title 0.34 / 0.02, body *declined* |
| Amazon-Google | 0.446 | 0.428 | title 0.30, body *declined* |

Automatic placement is **comparable to label-tuned placement** — better on two
datasets, 0.018 below on the third — while requiring nothing a deployment lacks.
Since two of the three hand-placed figures were themselves fitted to the labels,
the honest reading is that the automatic numbers are the ones a user can expect,
and the caveat on the table above no longer applies to them.

Bands are inferred **per field**, which matters: on both product datasets `title`
banded successfully while `body` was declined. That is the same signal the binary
model produced when it learned `m_body = 0.0` — long product descriptions do not
separate matches from non-matches at any cutoff — but here it is reported rather
than silently absorbed, and the field keeps the binary model instead of being
given invented bands.

Placement uses trough detection rather than multi-level Otsu. Otsu is the obvious
generalisation and the wrong objective: between-class variance is maximised by
splitting where mass is concentrated, so with one dominant mode — the normal ER
shape — it subdivides that mode. Measured on a bimodal sample (3,000 non-matches
near 0.10, 600 matches near 0.80), the variance criterion cut at 0.29 and 0.11,
both inside the non-match peak, while the visible valley sat near 0.45.

#### Which population `u` is measured over

`u = P(a field agrees | the pair is NOT a match)`. The binary path measures it on
**random record pairs**, and that correction was worth a lot: joint EM over
candidates alone once produced a match weight of 27.6 nats (e^27 odds) where the
anchored estimate gave 0.727. The reasoning is standard — candidate pairs have all
cleared a similarity gate, so they cannot furnish a representative non-match
sample.

The multi-level path shipped without that correction, and closing the gap made
things **worse**. Both arms measured on identical candidates, DBLP-ACM with bands
0.9/0.6:

| `u` measured over | u[title] | peak F1 | **F1 at the shipped 0.8** | B-cubed |
|---|---|---|---|---|
| candidate pairs (default) | 1.5e-2 | 0.914 | **0.911** | 0.965 |
| random pairs | 5e-4 | 0.914 | **0.672** | 0.865 |

Peak F1 is identical because rescaling every weight preserves pair *ranking*, and
peak F1 only depends on ranking. Everything else degrades. With a denominator ~30x
smaller, each agreeing field contributes ~3.4 extra nats, so scores saturate:
4,363 of 32,278 candidates land above 0.8 and all remaining discrimination is
squeezed into 0.97-1.00. Peak F1 then depends on whether a threshold sweep happens
to hit the right grid point — observed flipping between 0.72 and 0.91 across runs
whose learned parameters agreed to three decimals.

Abt-Buy moves the *opposite* way at the default threshold (0.029 → 0.506),
because its candidate-estimated `u[title] = 0.153` was so high that agreement
carried almost no weight. So neither population is uniformly right.

**The rule that explains both: `u` belongs to the population the model will
actually score.** This pipeline scores blocked candidates, where 0.6+ similarity
is common; among random pairs it is nearly impossible. Measuring on random pairs
answers a question nothing asks, and the resulting overconfidence is not a
calibration nicety — it costs 0.24 F1 at the operating point a user would ship.
The default is therefore `candidates` for multi-level models, with
`--fs-categorical-u random_pairs` available for the case the textbook assumes: a
model scoring an unblocked population, or blocking loose enough that candidates
approximate all pairs.

Two secondary findings from the same work:

- **`u_sample_size` was not delivering the sample it promised.** Pairs were formed
  by splitting one key draw in half, so a 2,173-record collection yielded 1,086
  pairs however large the request — and `u` for a selective level can be of order
  1e-4, where ~1,000 observations expect a count of zero. The estimate then falls
  back to its smoothing floor, and a floor standing in for a measurement inflates
  `log(m/u)` rather than merely being imprecise. Keys are now re-paired at random,
  so the requested pair count is delivered and a shortfall is logged.
- **Raising the sample does not rescue the random-pair arm.** At 100,000 pairs the
  selective levels still measured at or near the floor (u[title] = [3e-4, ~0,
  0.9997]). Chance agreement above 0.6 between random bibliographic records is
  genuinely below the resolution of any practical sample — the quantity is small
  because it is *real*, not because the sample was thin.

## Structured multi-field records: where Fellegi-Sunter wins

Everything above compares **two free-text fields**. That is the regime least able
to separate a matcher that learns per-field weights from one that averages
similarities, so the recommendation "FS earns its place on structured,
multi-field records" was an untested conjecture in this document for as long as it
appeared here.

**FEBRL** (Freely Extensible Biomedical Record Linkage, ANU) is the standard
benchmark for that shape: synthetic person records with generated typos,
transpositions and field swaps, ground truth encoded in the record ids. Ten
fields, and — the reason it settles the question — chance-agreement rates that
span three orders of magnitude:

| Field | Distinct values | Chance agreement |
|---|---|---|
| `state` | 35 | **0.212** |
| `street_number` | 342 | 0.014 |
| `postcode` | 1,273 | 0.0015 |
| `suburb` | 1,706 | 0.0014 |
| `date_of_birth` | 2,089 | 0.0007 |
| `soc_sec_id` | 2,291 | **0.0007** |

Agreement on `state` is worth almost nothing; agreement on `soc_sec_id` is nearly
decisive. That is a 300x spread in evidential value, and a uniform weighted
average has no way to express it. Learning it is precisely what Fellegi-Sunter
does.

Field weights for the weighted baseline are **uniform** — deliberately untuned,
because tuning them against benchmark F1 would select on labels a deployment does
not have, and would confound the comparison being made.

| Dataset | Matcher | Pairwise F1 | F1 at default 0.8 | Entity F1 (B-cubed) |
|---|---|---|---|---|
| febrl1 | weighted | 0.998 | 0.759 | 0.999 |
| febrl1 | **FS binary** | **1.000** | **0.998** | **1.000** |
| febrl1 | FS multi-level | 0.987 | 0.985 | 0.9945 |
| febrl3 | weighted | 0.9936 | 0.547 | 0.9963 |
| febrl3 | FS binary | *0.236 — UNFIT* | *0.190* | *0.0014* |
| febrl3 | **FS multi-level** | **0.9954** | **0.9950** | **0.9989** |
| febrl3-noid | weighted | 0.9813 | 0.443 | 0.9928 |
| febrl3-noid | FS binary | *0.190 — UNFIT* | *0.190* | *0.0014* |
| febrl3-noid | **FS multi-level** | **0.9814** | **0.9798** | **0.9922** |

Every row is reproducible with one command; the three matchers are
`--scoring-method weighted_heuristic`, `--scoring-method fellegi_sunter`, and
`--scoring-method fellegi_sunter --comparison-levels auto` respectively. Bands
are inferred per field from the score distribution, never hand-placed, so nothing
here is tuned against the labels. Each row's command and full output are
committed in [`benchmark_results_febrl.json`](benchmark_results_febrl.json), and
`tests/test_published_results_conformance.py` fails if this table or the README's disagrees with
it.

> **The Fellegi-Sunter rows were not reproducible until September 29, 2026.**
> Three unseeded samples fed training: the term-frequency table broke ties at its
> top-100 cutoff arbitrarily, band inference sliced a Python set whose order
> follows the per-process hash seed, and the EM training sample used AQL
> `RAND()`. Identical runs on the old code gave febrl1 multi-level 0.986 and 0.987.
> All three are now seeded (`--fs-sample-seed`), and repeated runs agree to every
> digit. The rows above are from the deterministic code: the multi-level rows
> moved in the third or fourth decimal, febrl1 binary from 0.999 to 1.000, and
> no conclusion changed except the next paragraph's, where the febrl3-noid
> comparison moved from "weighted fractionally ahead" to a tie. The Leipzig
> [scoring-method table](#scoring-method-weighted-similarity-vs-fellegi-sunter)
> re-measured identically at its printed precision on the seeded code; the
> term-frequency and multi-level Leipzig tables were measured before seeding and
> have not been re-run, so their last digit is not guaranteed.

Blocking recall is 1.000 on all three, so nothing here is capped by candidate
generation. febrl1 is 1,000 records in 500 two-record clusters; febrl3 is 5,000
records over 2,000 entities with clusters of 1-6 **including 835 singletons**,
which punish over-merging in a way uniform two-record clusters cannot.

> **An earlier version of this table was wrong and has been withdrawn.** It
> reported febrl3 FS binary as 0.9995 / 0.9985 / 0.9993 — the row the whole
> section rested on — and both weighted rows' "F1 at default 0.8" as 0.988 and
> 0.965. Re-measurement produced 0.236 / 0.190 / 0.0014 and 0.759 / 0.547. The
> binary figure was a model that had silently collapsed (see below); the weighted
> figures are not reproducible by any configuration found. Five of nine rows
> changed. The conclusion changed with them.

**Fellegi-Sunter still wins on structured records — through comparison levels,
not the binary model.** That is the reverse of what this document previously
claimed.

**And the win is robustness to the operating point, not peak accuracy.** At the
best swept threshold the two matchers are close, and on `febrl3-noid` they are
tied (0.9814 vs 0.9813). At the shipped 0.8 default — the number a
user actually gets without tuning — FS multi-level scores 0.9950 against 0.547 on
febrl3, and 0.980 against 0.443 on febrl3-noid. Uniform weighted averaging over
ten corrupted fields puts true matches around 0.5-0.6, so a 0.8 cutoff discards
most of them; FS posteriors are calibrated and saturate near 1, so the same cutoff
costs almost nothing. The value on offer is a matcher that does not require you to
find the threshold first.

`febrl3-noid` exists because `soc_sec_id` behaves like a primary key, and a
headline claim should not rest on one. Dropping it costs FS multi-level 0.015 F1
at the default and the ordering is unchanged, so the result is not an artifact of
a de facto identifier.

### Binary Fellegi-Sunter is fragile here, and now says so

On febrl3 and febrl3-noid the binary model **collapses**: EM converges to a match
prior of ~0.99, declaring almost every blocked candidate pair a match, which
blocking makes impossible by construction. Four consecutive runs gave 0.991,
0.9914, 0.9905 and 0.9893 — consistently degenerate, not a seed-dependent fluke.
The resulting model scores F1 0.236 with B-cubed 0.0014.

The mechanism is label switching. Binary estimation defaults to `u` measured on
random pairs, and holding `u` fixed removes the usual swap correction as an
escape route, so a `u` that does not describe the pair population surfaces as an
absurd prior instead. It works on febrl1 — 500 clean two-record clusters — and
fails on the harder datasets.

`estimate_mu` now flags any fit whose prior exceeds 0.5, persists it on the model
as `fit_warning`, and the harness prints `!! UNFIT MODEL`. The categorical path
has carried this guard since the failure was first seen there; the binary path
did not, which is exactly how a collapsed model reached a published table. The
parameters are still returned — a caller may genuinely be scoring a match-dense
population — but they are no longer returned silently.

The practical consequence: **prefer comparison levels on structured data.** They
are not merely an alternative to the binary model here, they are the configuration
that reliably fits at all.

### The rule this yields

**FS's value is proportional to the spread in per-field discriminating power, and
that spread is measurable before choosing a matcher.** Compute each field's chance
agreement (the sum of its squared value frequencies — no labels needed):

- **Wide spread** (structured records: identifiers, dates, codes, postal fields)
  → FS with comparison levels. Weighted averaging cannot express what the data is
  telling you, and the binary model does not reliably fit on this shape.
- **Narrow spread** (two or three free-text fields where chance agreement is
  uniformly negligible) → weighted similarity, and reach for comparison levels
  only if you need FS's calibrated posterior or evidence decomposition.

This replaces the earlier flat recommendation of "default to weighted". Weighted
remains the right default for text-heavy data and is still what the Leipzig
headline numbers use — but on structured records it is the weaker choice, by a
margin large enough to matter.

#### When to choose multi-level FS

Weighted similarity is still the default. Choose FS with comparison levels when
you need what it uniquely provides and can afford ~5% F1:

- a **calibrated posterior** rather than an uncalibrated 0-1 score;
- a **per-decision evidence decomposition** (which field contributed what, in
  additive log-odds) for auditability;
- **term-frequency adjustment**, worth +0.084 F1 where records share identical
  values;
- **robustness to a mis-set threshold**, as above.

Place the bands using the observed similarity distribution for your data, not the
values in this table.

## Threshold selection

The best threshold ranges from **0.34 to 0.77** across these four datasets, so no
fixed default can serve all of them. Running the shipped `0.8`:

| Dataset | F1 @ 0.8 | F1 @ best | Best thr | Score valley depth | Auto-selected | F1 auto |
|---|---|---|---|---|---|---|
| DBLP-ACM | 0.935 | 0.937 | 0.77 | **0.978** | 0.523 | **0.912** |
| Abt-Buy | 0.067 | 0.541 | 0.35 | 0.000 | *rejected* → 0.8 | 0.067 |
| Amazon-Google | 0.037 | 0.488 | 0.34 | 0.000 | *rejected* → 0.8 | 0.037 |

`similarity.auto_threshold: true` infers the cutoff from the score distribution
using Otsu's method — the cut maximising between-class variance, which finds the
valley between the non-match and match modes without needing labels. It is
**off by default**, so existing runs are unchanged.

The measured outcome splits cleanly by whether the scores are actually bimodal:

- **DBLP-ACM** has a pronounced valley (depth 0.978) and inference lands at 0.523,
  reaching **0.912 — 97% of the achievable 0.937** with no labels at all.
- **Abt-Buy and Amazon-Google have valley depth 0.000.** Their scores decay
  smoothly from a single low mode with no separate match cluster, so no cut is
  statistically supported. Selection *refuses* to return one and keeps the
  configured threshold with a warning.

That refusal is deliberate and worth explaining, because a looser guard scored
better on these two datasets. An earlier version gated on between-class variance
and did return cuts here — 0.238 and 0.203, worth F1 0.436 and 0.387, a 6.5x and
10.5x improvement over the default. Those numbers were **luck, not method**:
between-class variance cannot detect bimodality at all (splitting any single
Gaussian at its mean yields 2/pi ~= 0.637, so unimodal data scores ~0.64 and
looks confident), and the cuts it produced simply sliced a smooth tail at an
arbitrary point. Shipping that would mean a component that returns
confident-looking thresholds from distributions carrying no information about
where the threshold should be — right on this data, wrong on the next dataset,
with nothing to distinguish the two cases.

**So the honest guidance is:**

1. Use `auto_threshold` when scores are bimodal — it is accurate there and free.
2. When it declines, that is information: the matcher is not separating the
   classes on this data. Improve features or scoring rather than hunting a cutoff.
3. **Whenever labels exist, use them.** `select_threshold_supervised` reached the
   optimum on every dataset here. A few hundred labelled pairs suffice, and
   analyst verdicts accumulating in the review queue are exactly that — which
   makes supervised selection the practical path, not a theoretical one.

## Scale limits

DBLP-Scholar **completes and produces the best entity-level accuracy of the
four**, but blocking takes ~17 minutes for 66,879 documents versus 7 seconds for
DBLP-ACM's 4,910 — a ~13x growth in records costing ~140x the time. Quality
scales; throughput does not.

The cause was structural and is now fixed. `BM25BlockingStrategy` issued **one
monolithic AQL query** containing a per-document subquery, with no batching or
streaming, so the single request exceeded python-arango's default 60-second read
timeout and any direct caller above ~10k records hit that before anything else.

Blocking now executes in **adaptive chunks**: each request covers a bounded slice
of source documents, and the slice size tracks a wall-clock budget measured from
the previous chunk. Verified at 66,879 documents **against the default 60s
timeout**, which previously failed outright: 1,335,613 candidate pairs across 67
chunks, no timeout. Chunk size held at 1,000 (~15s per request), the adaptive
logic correctly declining to grow into the timeout.

Two properties make this safe rather than merely faster. Each source document
searches the entire view independently, so partitioning the outer loop changes
the number of requests and nothing else — chunked and unchunked runs are asserted
to produce identical candidate sets across six chunk sizes. And the query sorts
by `_key` before applying `LIMIT`, without which two chunks could overlap or skip
documents and silently lose pairs.

What remains: every strategy still materialises all candidate pairs into client
memory before deduplication, so peak memory scales with the candidate count.
`iter_candidates()` exposes a streaming path for callers that want to avoid it.
The README once claimed "1M records / ~3min", which was never measured; it now
quotes the four measured rows from the Summary table instead (67k takes ~17
minutes). Published throughput at 100M+ records (as Splink-on-Spark and Senzing
report) remains an open gap.

## What these benchmarks already caught

The first run of this harness found a defect that had survived the entire test
suite: `BM25BlockingStrategy` matched candidates with
`PHRASE(d2.text, d1.text)`, which requires the source text to appear in the
candidate as an **exact consecutive token sequence**. On Abt-Buy it produced
**0 candidate pairs out of 1,097 true pairs** — the strategy documented as
"fuzzy text matching (400× faster than Levenshtein)" was performing near-exact
phrase containment. A unit test asserted the broken query as the expected
contract, so nothing failed.

Switching the default to token-level BM25 matching (`match_mode="tokens"`, with
`"phrase"` retained for compatibility) took Abt-Buy blocking from **0 → 0.957
pair completeness**. This is the argument for benchmarking against public data:
no amount of unit testing surfaces a recall collapse, because every unit still
behaves exactly as written.

## Reproducing

```bash
# Any local ArangoDB; the harness creates and drops its own collections.
python scripts/run_er_benchmarks.py --dataset all \
  --port 8529 --password "$ARANGO_ROOT_PASSWORD" \
  --output docs/benchmark_results.json
```

Datasets download once from the [Leipzig DBS
group](https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution)
into `.benchmark_data/` (gitignored) and are cached, so later runs are offline.

Useful flags:

| Flag | Purpose |
|---|---|
| `--dataset` | `abt-buy`, `amazon-google`, `dblp-acm`, `dblp-scholar`, `all` |
| `--algorithm` | `jaccard` (default), `jaro_winkler`, `levenshtein` |
| `--scoring-method` | `weighted_heuristic` (default) or `fellegi_sunter` |
| `--fs-agreement-threshold` | FS agree/disagree cutoff per field (default 0.85) |
| `--comparison-levels` | Descending band thresholds, e.g. `0.6,0.35`; `auto` to infer per field; omit for the binary model |
| `--auto-band-count` | Bands to infer per field when `--comparison-levels=auto` (default 2) |
| `--blocking-field` | Field BM25 blocking searches: `text` (default), `title`, or `body` — see [Blocking](#blocking-which-field-to-search) |
| `--fs-categorical-u` | Population `u` is measured over for multi-level models: `candidates` (default) or `random_pairs` — see [Which population `u` is measured over](#which-population-u-is-measured-over) |
| `--no-fs-term-frequency` | Disable TF adjustment, to isolate its contribution |
| `--title-weight` | Weight on the title field (default 0.7) |
| `--bm25-threshold`, `--limit-per-entity` | Blocking recall/volume trade-off |
| `--emit-curve` | Include the full threshold sweep in the JSON |
| `--keep` | Leave benchmark collections in place for inspection |

Repeated runs on identical inputs agree to every digit. For the weighted
matcher that was always true; for Fellegi-Sunter it has been true only since the
training samples were seeded (`--fs-sample-seed`, default 20260929) — see the
note under the FEBRL table.

## Caveats

- Single-node ArangoDB on a laptop. Timings are indicative, not throughput
  claims.
- Unsupervised throughout. No labelled pairs and no LLM verification. Headline
  numbers use the weighted-similarity path; the Fellegi-Sunter path (EM-estimated
  parameters with unbiased `u`, null comparison level, term-frequency adjustment
  and multi-level comparisons) is measured separately in
  [Scoring method](#scoring-method-weighted-similarity-vs-fellegi-sunter) and
  [Multi-level comparisons](#multi-level-comparisons-measured). Weighted
  similarity remains the better matcher on all three datasets, so it stays the
  default.
- The hand-placed multi-level bands for DBLP-ACM and Abt-Buy were selected using
  benchmark F1, which is selection on labels a deployment does not have. The
  automatic figures alongside them use no labels and are the ones a user can
  expect to reproduce.
- Comparison figures for other systems come from their respective papers and
  were not reproduced here.
- DBLP-Scholar's blocking stage takes ~19 minutes on this hardware; see
  [Scale limits](#scale-limits).
