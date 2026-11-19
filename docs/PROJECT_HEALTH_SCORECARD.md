# Project Health Scorecard

**Evaluated:** November 19, 2026  
**Release baseline:** `v3.10.1`  
**Assessment scope:** released code plus committed, gate-passing work on `main`  
**Overall health:** **7.8/10 — B**

This is the current operational scorecard. The June 2026 reviews remain useful
as historical baselines, but their security, matching, UI, and graph-feature
findings no longer describe the current system.

The November 19 re-evaluation holds the score at **7.8**, with one dimension up
and one down. Matching evidence rose: the LLM-judge table, the one published
table that was not artifact-backed, was re-measured with every per-pair verdict
committed and reproduced the September figures to within 0.005 accuracy, and it
is now test-checked. Documentation and release discipline fell. The README's
Python quick start raised `KeyError` and its Performance table quoted a
1M-records figure nobody had measured, both in the README the previous
evaluation called gated against the code; `docs/BENCHMARKS.md` gave two
different timings for its own largest run; and `v3.10.1` was tagged on a commit
whose CI had been red for three pushes. The publish workflow's own test step
stopped that release, so nothing broken reached PyPI, but the risk this
scorecard named in September (red CI nobody reads) recurred. Correctness holds:
five shipped defects were fixed with regressions, including an `AsyncERPipeline`
that could not complete a run and a cost budget that could never trip for a
model litellm cannot price, and again a review found them rather than a gate.

The September 29 re-evaluation moved the score **up** 0.1, and most of that
movement is repair rather than new capability. A whole-repo quality review found,
and this cycle fixed with mutation-checked regressions, a set of defects the
previous scorecard had rated without knowing about. Two were exploitable: an
arbitrary file write through the export route, and reviewer attribution that any
token holder could spoof. The Workbench's pipeline-run route failed on its first
call in every database, and the pipeline dropped the documented `llm:` config
block. The Python CI workflow had run none of its gates since August 7. The
current code is materially sounder than the September 22 code. The fact that the
earlier grades did not know what they were grading is recorded under
documentation discipline, which holds rather than rises.

The September 22 re-evaluation moved the score **down** 0.1, and that was the
scorecard working as intended. A published benchmark table was found to have five
of nine rows wrong, including the headline, and the README carried a quality claim
that measurement contradicts. Both were corrected properly — the withdrawn figures
are named in the documents — but the lapse is a documentation-discipline fact and
is scored as one. Correctness improved in the same period: two real defects were
found by measurement and fixed with mutation-tested regressions.

## Scoring method

Scores use a 0–10 scale: 9–10 leading, 8–8.9 strong, 7–7.9 healthy with
material gaps, 5–6.9 usable but constrained, and below 5 high risk. The overall
score is weighted by impact on correctness, trust, and production use.

| Dimension | Weight | Score | Current evidence |
|---|---:|---:|---|
| Architecture and core design | 12% | **9.0** | Config-driven pipeline, pluggable blocking and clustering, shared services behind CLI/MCP/UI, native ArangoDB graph/vector paths |
| Correctness and reliability | 12% | **8.8** | Binding human verdicts, null-safe scoring, configuration-hashed model loading, strict known-defect and conformance gates, degenerate-fit detection on both EM paths. This cycle fixed ten shipped defects, each with a mutation-checked regression. Among them: missing email/phone scored as disagreement; `compute` and `compute_detailed` diverged; EM accepted non-indicator input; hybrid blocking used near-exact PHRASE retrieval; the cascade treated suppressed edges as links; pipeline statistics reported 0 clustered entities; seeded FS training was not reproducible. Held, not raised: the review found them rather than a gate, and the same class remains (config silently ignores unknown keys; `load_latest` is hashless). Held again on November 19: five more shipped defects fixed with regressions (`AsyncERPipeline` could not complete a run; golden-record writers used different keys; BM25 silently turned a second `blocking.fields` entry into an exact-match filter; profiler-emitted algorithms did not take effect; `LLMMatchVerifier` recorded $0 for models litellm cannot price, so `max_cost_usd` never tripped, now priced from the provider's charge and failing closed, verified live). `fallback_provider` now warns that nothing acts on it |
| Tests and mechanical verification | 12% | **8.8** | `make verify`: 1,983 passed, 8 skipped, 76.65% coverage against a 72% floor. New gates this cycle: README config, CLI, tool, backend and strategy tables checked against the objects that define them; published benchmark tables checked against committed artifacts; the secret scanner tested; strict fakes that enforce ArangoDB's naming rule. Up 0.1 because CI now actually runs these gates: it had failed at collection on every run from August 7 until 0b5212a. Held below 9 because the integration tests that prove recall and AQL semantics are not in CI, and nothing watched CI's own health for seven weeks. Held on November 19: the cost-accounting tests now run the real `litellm` pricing path instead of mocking the module, and the LLM and README Performance tables joined the conformance gate; against that, four tests passed locally and failed in CI for three pushes because they depended on the installed pytest and litellm versions, and nothing surfaced the red branch until a release failed |
| Security and privacy | 12% | **7.4** | Optional API/WebSocket auth and rate limiting, AQL hardening, SPA containment. Fixed this cycle: arbitrary file write and temp-file read through the export routes; reviewer attribution spoofable by header; reviewer tokens unable to authenticate; the API key unscrubbed in provider error text; scanner blind spots over shipped directories; an sdist that shipped untracked worktree files. LLM masking is now configurable from the pipeline. Secure deployment still depends on configuration; the export fix shipped in 3.9.0 |
| Matching quality and evaluation | 12% | **8.6** | Two public benchmark families covering both task shapes, B-cubed metrics, multi-level Fellegi–Sunter learned end to end, an explicit reference population for `u`, a measurable rule for choosing a scorer, and an oracle-bounded measurement of the LLM tier. Up 0.1 on September 29: the FEBRL and review-band tables became committed artifacts that reproduce to every digit and are test-checked against the docs. **Up 0.1 again (8.5 → 8.6) on November 19:** the LLM-judge table, the remaining exception, is now backed by all 200 per-pair verdicts per model, reproduced the September figures to within 0.005, and is test-checked; the reconstructed measurement script's abstention bug was found and fixed with tests. Two Leipzig FS tables still predate seeding |
| Steward Workbench and API UX | 10% | **7.3** | Binding edits, audit, threshold tuning, profiling, survivorship overrides, auth UX, and dark mode. Two advertised features never worked and now do: pipeline runs (the reserved `_er_pipeline_runs` name failed ERR 1208 in every database, taking run history and WebSocket progress with it) and export download. Up only 0.1, because MagicMock-based route tests passed throughout, and frontend and enterprise workflow coverage remain thin. Held on November 19: steward golden-record overrides, claimed implemented and tested, failed to survive a rebuild through the Workbench until ac6bbd8 unified the golden-record key |
| Maintainability and debt | 10% | **6.5** | Good layering and deprecation discipline, offset by legacy exports, unwired strategies, oversized modules, 4,056 advisory flake8 findings (flat since August 6), and no clean mypy baseline. Held on November 19: `AsyncERPipeline` now wraps the sync pipeline instead of duplicating it, retiring one legacy path |
| Documentation and release discipline | 8% | **7.8** | Gains: the README is now gated against the code, and its main config example, which silently resolved the wrong collection, is fixed. Twenty broken links fixed; fabricated demo figures (99.5% precision, 250K records/s, a 50M-record deployment) replaced with measured ones; Foxx-era docs archived; nine PRD patches proposed. Held, not raised, because of lapses in the same period: CI red for seven weeks while docs said it ran the gates, the published 3.8.0 `[mcp]` extra broken by an unbounded dependency, and the September 22 scorecard grading code with live defects it had not looked for. **Down 0.2 (8.0 → 7.8) on November 19.** Gains: three releases (3.9.0, 3.10.0, 3.10.1) through the version gate, the remaining PRD patch accepted, the LLM table artifact-backed, the README Performance table gated, a diagram label from the retracted BM25 claim removed. Lapses: the gated README still shipped a Python quick start that raised `KeyError` and an unmeasured "1M records / ~3min" row; the README opened with "production-ready ... millions of records"; BENCHMARKS gave both ~17 and ~19 minutes for one run (the artifact says 1,160 s); and `v3.10.1` was tagged on a red commit, so the published package was built from a later commit (819295d, two test files different) than its tag |
| Performance and scalability | 7% | **6.5** | GAE and local backend choices are strong; BM25 candidate generation is now adaptively chunked against a wall-clock budget and verified at 66,879 records against the default client timeout it previously exceeded, with a streaming `iter_candidates()` path; strategies still materialise all pairs client-side before deduplication, and nothing above ~67k is evidenced |
| Operations and deployment | 5% | **5.0** | Health endpoints, migrations, and runtime-provider gates exist, but there is no service image/Kubernetes package or standard Prometheus/OpenTelemetry stack |

**Weighted total:** 7.8/10 (7.821).

## Verification snapshot

- Python correctness gate: **pass** — 1,983 tests passed; critical lint, secret
  scan, version consistency, wiring conformance, docs and published-results
  conformance, statistical quality floors, and the 72% coverage floor all passed
  on November 19, locally and in CI on 819295d (CI had been red from a7a16b1 to
  e306a1e; see risk 8).
- Python coverage: **76.65%**.
- UI unit tests: not re-run locally this cycle; the UI contract and Playwright
  workflows passed in CI on 819295d. Last local count: 7 tests across 3 files.
- UI production build: **pass**. Vite reports a large main bundle
  (~1.02 MB minified / ~292 KB gzip), so code splitting remains worthwhile.
- Playwright smoke tests exist and CI installs Chromium. The local rerun was
  environment-blocked because the Playwright browser binary was not installed,
  not because an application assertion failed.
- Full flake8 remains advisory and currently reports **4,056 findings** (`make
  lint`, line length 120), mostly formatting plus some unused imports — flat
  against August 6, so the debt is stable rather than growing. The blocking
  syntax/undefined-name subset passes.
- Local `make typecheck` is not self-contained because `mypy` is absent from the
  active development environment; CI installs it but treats findings as advisory.

## Material improvement since June 2026

The project moved from a strong core with risky surfaces to a substantially more
complete product:

- Web/MCP exposure is authenticated and rate-limited; AQL interpolation paths,
  SPA file serving, reviewer attribution, and golden-record metadata are
  hardened.
- Human verdicts now affect edges and clusters, with auditability and backend
  conformance checks.
- Fellegi–Sunter now has EM estimation, unbiased `u`, null semantics,
  term-frequency adjustment, calibrated posterior scoring, and config-specific
  model persistence.
- Public benchmark and quality-gate workflows replaced unverified performance
  and accuracy claims.
- The Workbench gained threshold tuning, cluster curation, profiling, golden
  record editing, dark mode, component tests, and Playwright smoke coverage.
- Graph-context scoring, collective resolution, incremental maintenance, and
  graph-embedding blocking now make the ArangoDB integration substantive rather
  than merely a storage choice.

Since the August 6 evaluation:

- Multi-level Fellegi–Sunter is complete end to end — categorical EM, learned
  per-level persistence, production wiring, and published benchmarks — with
  bands inferable per field from the observed score distribution rather than
  hand-placed against labels.
- A second benchmark family (FEBRL deduplication) settled a claim the docs had
  been asserting without evidence: the probabilistic matcher wins decisively on
  structured multi-field records — decisively at the shipped threshold (febrl3
  0.9950 vs 0.547), narrowly at the best swept one — the reverse of its result on
  text. Which matcher applies is now predictable in advance from the spread in
  per-field chance agreement, without labels. The first published version of that
  table was wrong and has been withdrawn; see docs/BENCHMARKS.md.
- Candidate generation is adaptively chunked, closing the P0 scale constraint at
  the 67k scale that previously failed outright.
- Two correctness properties were discovered by measurement and made explicit:
  parameter estimation now names and records the population `u` is measured over
  (taking it from the wrong population cost 0.24 F1 at the shipped threshold
  while leaving peak F1 unchanged), and a degenerate fit is flagged rather than
  returned silently.

Since the September 29 evaluation:

- The LLM verification tier is artifact-backed: all 600 per-pair verdicts from
  the November 16 re-run are committed, the measurement excludes abstentions and
  reports McNemar significance, and the cost accounting that recorded $0 for
  unpriced models now uses the provider's reported charge.
- The canonical-hub resolver has a public import path and publishes its request
  checks, oracle keys and reason vocabulary (`check_request`), so consumers stop
  keeping drifting copies.
- `AsyncERPipeline` runs the sync pipeline instead of a broken reimplementation.

## Current risk register

Three risks from the August 6 register are closed. They are listed under
[Closed since August 6](#closed-since-august-6) rather than deleted, so the
register can be read as a history rather than only a snapshot.

1. **Operational packaging — P1 adoption constraint.** Add a supported service
   container, deployment example, structured logs, metrics, and tracing.
2. **Wiring completeness — P1 product constraint.** Geographic, hybrid, and
   graph-traversal strategies are exported and tested but are not selectable
   through `ConfigurableERPipeline.run_blocking()`, which reaches five of them
   (`exact`, `bm25`/`arangosearch`, `vector`, `lsh`, `graph_embedding`). The
   README now labels the other four library-only, and a test holds that table to
   `BlockingConfig.VALID_STRATEGIES`. Wiring them into the pipeline is still
   open.
3. **Maintainability — P1 engineering constraint.** Establish a ratcheted
   full-lint baseline, make local type checking reproducible (`mypy` is still
   absent from the development environment), reduce oversized modules, and
   finish retiring duplicate legacy paths.
4. **Candidate-generation scale beyond 67k — P2 product constraint.** Adaptive
   chunking closed the immediate failure, but every strategy still materialises
   all candidate pairs in client memory before deduplication, and no run above
   66,879 records has been measured. `iter_candidates()` exists for callers that
   want to avoid the materialisation; the batch path does not yet use it.
5. **Governance — P2 enterprise constraint.** Shared-token authentication is
   appropriate for the current embedded scope, but RBAC, tenant isolation,
   immutable audit guarantees, erasure propagation, and default-on LLM masking
   remain v4 work.
6. **Prose is partly gated — P2 trust constraint** *(was P1)*. The README's
   config examples, CLI lines, tool, backend and strategy tables, and its
   benchmark tables are now checked against code and committed artifacts, and so
   are the BENCHMARKS FEBRL, summary and oracle tables, the scorecards'
   internal agreement, and relative links. Since November 19 the LLM-judge
   table and the README Performance table are gated too. Still ungated: the
   README's Python quick-start snippet (it raised `KeyError` until a7a16b1, and
   nothing would have caught it), prose figures in BENCHMARKS outside its tables
   (it quoted ~17 and ~19 minutes for one run), prose outside the README (guides,
   demo scripts, which still say "millions of records"), and the Leipzig TF and
   multi-level tables, which predate seeded training.
7. **Verification-tier defaults — P2 product constraint.** The LLM tier works
   with a competent model, and the provider docs now say that the local model
   does not. The shipped 0.55–0.80 band still holds only 8.5% of errors; derive
   it from the error distribution (PRD requirement REQ-L05, open drift alert).
   `fallback_provider` left the shipped scope; the config still parses it and
   warns that it has no effect. Cost budgets now work for every model: a call
   nobody can price is reported as unknown and stops a `max_cost_usd` run.
8. **CI health is unmonitored — P1 process constraint, recurred.** The Python CI workflow
   failed on every run for seven weeks, and nobody noticed, because a gate that
   is always red is not read. It recurred on November 18-19: four tests passed in
   the development venv (pytest 9.0.3, litellm 1.86.2) and failed in CI (9.2.0,
   1.110.1) for three pushes, and `v3.10.1` was tagged on one of them; only the
   publish workflow's test step stopped the release. Check CI on the release
   commit before tagging. Add a check that surfaces a red default branch at
   session start, and run the integration tests in CI against an ArangoDB
   service container. They currently prove recall and AQL semantics locally
   only.
9. **Silent config defaults — P2 correctness constraint.** Every config section
   drops unknown keys without a word, so a misspelt key runs the default. This is
   how the README's main example resolved the wrong collection. Warn on or reject
   unknown keys.

### Closed since September 29

- **LLM-judge table not artifact-backed.** Re-measured on November 16 with every
  per-pair verdict committed, reproduced within 0.005, and test-checked.
- **Cost budgets inert for unpriced models.** Fixed in 780628d with tests on the
  real pricing path, and verified with one live OpenRouter call.
- **`AsyncERPipeline` unusable.** Fixed in a49f42d by wrapping the sync pipeline.

### Closed since September 22

- **Security defects in the Workbench and packaging.** Export path confinement,
  token-bound reviewer identity, API-key scrubbing, scanner recall, and an
  allowlisted sdist, each with tests that fail on the old code.
- **CI not running.** mcp is capped below 2, and the SPA route is excluded from
  the schema. All three workflows are green.
- **Non-reproducible FS benchmarks.** All three sampling sources are seeded,
  and the published tables are artifact-backed and test-checked.

### Closed since August 6

- **Release hygiene** *(was risk 1, immediate)*. The 76 uncommitted paths have
  been split, reviewed, and committed. The tree now carries two untracked files,
  both documentation or history, and `make verify` passes from it.
- **Candidate-generation scale** *(was risk 2, P0)*. BM25 now executes in
  adaptive chunks sized against a wall-clock budget, verified at 66,879 records
  against the default 60-second client timeout that previously failed outright.
  Chunked and unchunked runs are asserted to produce identical candidate sets.
  The residual concern is narrower and tracked as risk 4 above.
- **Multi-level probabilistic learning** *(was risk 3, P1)*. Categorical EM,
  learned-level persistence, automatic band configuration, production wiring,
  and benchmark ratchets are all shipped and measured. The accompanying claim
  that "binary FS remains materially worse than weighted similarity" was true
  only of text-heavy data and is now stated conditionally: on structured
  multi-field records the ordering reverses. The winning configuration there is
  FS with comparison levels, not the binary model, which collapses to an unfit
  solution on two of the three FEBRL datasets.

## Release-readiness decision

**3.9.0 was released on 2026-10-20** from a commit green on all three CI
workflows in both repositories. It ships the fixes for the two defects that
made a release necessary: an arbitrary-file-write path through the 3.8.0
Workbench export route, and a 3.8.0 `[mcp]` extra that installed mcp 2.x and broke the MCP
server on import. A fresh install from PyPI was checked: `[mcp]` resolves to
mcp 1.30.0, the MCP server imports, and `entity_resolution.canonical_hub`
imports from the installed package.

**3.10.0 followed on 2026-10-21**, adding the shared canonical-hub checks
(issue #4). The deprecated `_wp13` import paths it was to remove stay until
3.11.0, because a known consumer has not yet migrated.

**3.10.1 followed on 2026-11-19**, a fix release (cost accounting, async
pipeline, README). Its first publish failed at the workflow's test step, because
CI on `main` had been red since a7a16b1 on dependency-version-sensitive tests.
They were fixed in 819295d, CI went green on Python 3.10-3.12, and the package
was published from 819295d by workflow dispatch. The `v3.10.1` tag points at
e306a1e, which differs only in those two test files; it was left in place rather
than moved after publication.

The fourteen PRD patches proposed through 3.9.0 were accepted and applied on
2026-10-20, and the shared-checks patch (REQ-CANONICAL-HUB-CHECKS) on 2026-10-21.
One PRD line is now known stale: PRD.md:277 quotes "~17 minutes" for the
DBLP-Scholar run whose artifact records 1,160 s; a patch is proposed rather than
an edit.

## Evidence

- [Product requirements and shipped/open scope](PRD.md)
- [Public benchmark results and scale limits](BENCHMARKS.md)
- [Python CI gates](../.github/workflows/python-package.yml)
- [UI contract/unit workflow](../.github/workflows/ui-contract.yml)
- [UI Playwright workflow](../.github/workflows/ui-e2e.yml)
- [Security posture](../SECURITY.md)
- [June 2026 technical review](PROJECT_REVIEW_2026-06.md)
