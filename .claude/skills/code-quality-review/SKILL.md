---
name: code-quality-review
description: Run the periodic repo-wide quality audit — duplicate code, hardwired values, security risks, documentation drift from code, duplicated content across documents, and PRD quality (readability, bloat, requirement traceability) — across the whole tree rather than one diff. Produces a ranked report plus a remediation plan grouped into PR-sized units. Use when asked for a code quality review, a codebase audit, a security review, a documentation audit, a PRD review, or a check for drift/duplication/hardcoded values/doc redundancy; and at sprint boundaries. NOT for reviewing a single PR or diff — that is the built-in `/code-review`.
---

# Code Quality Review

The periodic whole-repo audit. `/code-review` looks at a diff; this looks at the
codebase, in six dimensions, and is meant to be run every few weeks rather than
per PR.

## Invocation

`/code-quality-review` — all six dimensions.
`/code-quality-review security` (or `duplication`, `hardwired`, `docs`,
`docs-duplication`, `prd`) — one.

## The rule that makes it worth running

**Verify every finding against the source before reporting it, and say which
ones you executed.** A review that reports plausible findings is worse than no
review: it costs a maintainer the afternoon it takes to discover the claim was
inferred. Quote `file:line` you have actually opened. Where a claim is
reproducible, reproduce it and paste the output. Where it is not, say what you
read and what remains assumption.

This repository has unusually good evidence that the rule is the whole game,
because the four defects found here in September 2026 were each found by running
something, and **none of them would have surfaced from reading**:

- `docs/BENCHMARKS.md` published a FEBRL table in which **five of nine rows were
  wrong**, including the headline the section's entire argument rested on
  (`0.9995` against a measured `0.236`). It was caught only because a re-run was
  done to confirm an unrelated change was behaviour-neutral.
- The row was wrong because binary EM converges to a match prior of ~0.99 on that
  data — a collapsed model — and the guard that catches exactly this existed on
  the categorical path and **not** the binary one. `EMResult` had no `warning`
  field at all.
- `LLMMatchVerifier` capped responses at 256 tokens, so a verbose model's JSON
  truncated mid-string and its verdict was discarded as unparseable. One model
  lost 28% of its verdicts. Terse models never triggered it, so every measurement
  taken through a verbose model was silently computed on whichever subset
  happened to answer briefly.
- `scripts/calibrate_runtime_quality_policy.py` called a method that does not
  exist on the class it imported. It raised `AttributeError` on the first line of
  real work. **The service it wrapped had unit tests and passed all of them.**

The pattern across all four: green tests, plausible prose, and nobody had run the
thing end to end. Read what runs, not what is claimed.

## Method

Fan out one subagent per dimension in parallel, then verify their headline claims
yourself before any of it reaches the user. The tree is ~44k lines of Python
across 145 modules under `src/entity_resolution`, ~35k lines across 130 test
files, a React workspace UI under `ui/src`, and a large `docs/` tree; doing this
serially in the main thread does not fit.

Give each agent the repo context below, and tell it explicitly: rank by
consequence, distinguish deliberate design from drift, skip trivia, and state
what came up clean so the next run can skip it.

### Do not re-run what is already mechanized

This repo has more gates than most, and a finding a gate already covers is noise.
Before reporting, check whether one of these owns it:

| Already covered by | Do not hand-audit |
|---|---|
| `make verify` | syntax/undefined names, version consistency, committed secrets, coverage floor, wiring conformance, matching-quality F1 floors |
| `/verify-wiring` | unreachable code, tests that mock the seam under test |
| `/prd-sync` | PRD-vs-code traceability in both directions (dimension 6 judges the *document*, not its agreement with code) |
| `make check-scorecards` | scorecard arithmetic, staleness, and quoted facts |
| `drift_alerts` in shared memory | known open gaps — a tracked gap is not a new finding |

The value of this audit is the six dimensions below, which **no gate reads**.

### 1. Duplicate code
Copy-paste families, and above all **copies that have already drifted** — a guard
present in one and missing in its twin. Deliberate parallel structure is not a
finding unless it has diverged; here that means the nine concrete blocking
strategies under `strategies/`, the clustering backends under
`services/clustering_backends/`, and the MCP tool modules under `mcp/tools/`.
Name the seam any consolidation should live in. (Settled 2026-09-29: there are
**five** concrete backends, and README is right. `docs/PRD.md:47` says "six" by
counting `auto` — a selector in `ClusteringConfig.VALID_BACKENDS`, not a module.
An earlier draft of this skill asserted the README was wrong; it was not. Recorded
as a caution: a number you remember is not a number you checked.)

The sharpest version in this repo is **a guard that exists on one of two parallel
paths**, and it has bitten twice. The degenerate-fit warning lived on
`estimate_categorical_mu` and not `estimate_mu`, so collapsed binary models
reached a published benchmark table. Earlier, "a suppressed edge must split the
cluster" was hand-copied into five of six clustering backends and simply absent
from the sixth. When you find a guard, **ask which sibling paths share its
failure mode** — that question has a better hit rate here than searching for
identical text.

### 2. Hardwired values
Hosts, ports, database and collection names, magic numbers, paths, model names,
thresholds.

Unlike sibling repos, **this one has no single configuration owner**, and that is
itself the thing to assess rather than assume. `config/er_config.py` exists and
is 1,554 lines, `utils/config.py` and `utils/config_utils.py` also exist, and
`os.getenv`/`os.environ` appears **73 times across 12 modules** including
`cli.py`, `mcp/server.py`, `reasoning/llm_verifier.py` and two clustering
backends. The useful question is not "is there a violation" — it is whether those
73 reads have a coherent story, and which of them duplicate a value `er_config`
already declares. A threshold baked into a service that config also declares is
the drift that bites the day someone changes the knob.

Two specifics worth their own sweep. **Score thresholds** are load-bearing and
have been measured to matter enormously: the shipped `0.8` default, the
`0.55`/`0.80` verification band (which holds 8.5% of errors on one benchmark),
and the agreement/band thresholds in the learning path. **Collection names** are
strings appearing in AQL, migrations and services; a rename that misses one copy
fails only at runtime and only on that path.

### 3. Security
**This repository is public on both remotes** (`arango-solutions` primary,
`ArthurKeen` secondary) and is published to PyPI, so the blast radius of a
committed secret is maximal and the supply chain is a real attack surface rather
than a theoretical one. Priorities, in order:

- **Secret handling.** `.env` holds 23 variables including a live PyPI token and
  LLM API keys. It is gitignored and untracked — verify that remains true, and
  that nothing logs, persists or serialises those values. `make scan-secrets` is
  blocking for committed files but **advisory for worktree findings**, which is
  precisely the gap where a key reaches a log or an artifact.
- **AQL injection** across ~118 `aql.execute` call sites. Bind variables are the
  convention and `utils/validation.py` provides name validators; find the
  exceptions, especially where a collection or field name is interpolated rather
  than bound, since those cannot be bound and must be validated instead.
- **The Steward Workbench UI**, which performs binding writes — cluster merges,
  golden-record edits, verdicts. Auth is a shared token (`ui/auth.py`). Confirm
  every mutating route enforces it, and that the audit trail attributing those
  actions cannot be spoofed by a header.
- **The MCP surface**, which exposes the platform to an agent with the same reach
  as the UI. Check it enforces the same authorization, not a parallel weaker copy.
- **LLM egress.** Optional verification sends record content to a provider.
  Masking exists but is optional; say plainly which fields leave the network
  under default configuration.
- Dependency and CI supply chain, including the PyPI publish workflow.

Demand a concrete exploit path — who the attacker is, what they control, what
they get — and label anything without one as hardening rather than a
vulnerability.

### 4. Documentation consistency
**No gate reads prose in this repo, and that is a known, scored risk** (risk 6 on
the health scorecard). It is the highest-value dimension here, not the
afterthought it is in repos with a docs test.

The evidence is recent and severe. `README.md` claimed LLM verification
"dramatically improves precision" — never measured, and when measured, precision
turned out to be the dimension every model was *worst* at, while the local model
the README recommended in its own provider table scored below the plain score
threshold. Separately, five of nine rows in a published benchmark table did not
reproduce. Both survived weeks of green gates.

So: **prefer numbers over claims as your audit unit.** Any figure in `README.md`,
`docs/BENCHMARKS.md`, the two scorecards or `docs/PRD.md` should either be
reproducible by a documented command or be marked as not. Specific things that
rot here: the install/quick-start sequence, the capability table's claims, the
MCP tool count, benchmark figures, and any statement about what a default
configuration achieves.

### 5. Duplicate content across documents
Dimension 1 is code; dimension 4 is docs disagreeing with code. This is docs
repeating *each other*, which is the state that produces dimension 4 a month
later.

The unit is a **fact**: a number, a command, a path, an env var, a benchmark
result. Every place it is written is a place it can rot independently, and the
copy nobody remembers to update is the one a newcomer reads.

This repo concentrates it in two places. First, the **benchmark fact-surface**:
`docs/BENCHMARKS.md` is canonical, but `README.md`, both scorecards and `PRD.md`
restate its figures for different audiences. When the FEBRL table was corrected,
the same wrong numbers had to be chased through four documents and a shared-memory
pattern — treat that set as one surface with several renderings. Second, the
**onboarding set**: `README.md`, `AGENTS.md` and `CLAUDE.md` overlap by design,
and their git status differs in a way that matters. `CLAUDE.md` is **gitignored**,
so a rule stated only there never reaches a fresh clone. `AGENTS.md` is not
ignored but is **untracked** — committable, and simply never committed. A rule in
both is fine; one only in `CLAUDE.md` is unreachable, and one only in `AGENTS.md`
is a single commit away from being reachable.

For each real finding, name which copy should be canonical and what the others
become: a link, a pointer, or nothing.

### 6. PRD quality
Scope is `docs/PRD.md`. This dimension judges the document itself — `/prd-sync`
reconciles it against the code, so do not re-run that here.

- **Readability.** Can a newcomer find the requirement governing one behaviour
  without reading the file end to end? Requirements should be atomic and citable,
  because code and commit messages cite them. A requirement that is really three
  cannot be cited, implemented or closed independently, so it never gets closed.
- **Bloat is not this repo's problem.** `PRD.md` is ~400 lines against the
  1,000-line limit `AGENTS.md` sets — comfortably inside it, unlike sibling
  repos. Do not import their split-the-PRD finding. The oversized documents here
  are elsewhere: `docs/development/NEXT_RELEASE_IMPLEMENTATION_BRIEF.md` (1,939),
  `docs/architecture/DESIGN.md` (1,067), `docs/development/UI_IMPLEMENTATION_PLAN.md`
  (1,035), and in source `cli.py` (1,636) and `config/er_config.py` (1,554)
  against a 1,500-line limit.
- **Requirement debt.** Every requirement should be implemented, tracked as an
  open drift alert, or explicitly deferred — a requirement in none of those three
  states is one nobody owns. Check `prd_patches` for `proposed` patches that have
  been sitting: an unreviewed patch is a decision nobody has made.

## Prefer a test over a finding

The most useful output of a review is often a test, not a paragraph. A finding
becomes an assertion that fails in CI for everyone, instead of a finding someone
has to rediscover.

This repo has no calibration run yet, so the table below is **candidates, not
history** — do not cite them as past results:

| Candidate assertion | Catches |
|---|---|
| Every numeric claim in `README.md` appears in `docs/BENCHMARKS.md` | The class that produced the FEBRL retraction |
| Every benchmark table row records the command that produces it | A table that cannot be debugged, only re-measured wholesale |
| Every `Makefile`/CI target's script path is tracked by git | A target dead on a fresh clone (`.claude/` is gitignored) |
| Every guard on one EM path has a counterpart on the other | The degenerate-fit and suppressed-edge class |
| No `os.getenv` outside the config modules | Whether the 73 scattered reads have an owner |

When you write one, **verify it fails without its fix** — a guard nobody has
watched fail is not yet a guard. This repo's own history is emphatic on that
point: a test written to close a wiring gap here passed while a mutation disabled
the write it was asserting, because it checked a report field that merely echoed
a CLI flag. Reserve prose findings for what no assertion can catch: drifted
duplication, governance holes, exploit paths, judgment.

## Repo context to hand each agent

- Python entity-resolution library, ArangoDB as the single multi-model store
  (documents, graph, vectors, ArangoSearch). `src/entity_resolution/**` is the
  engine (145 modules, ~44k lines), `ui/src/**` a React workspace UI served by
  `src/entity_resolution/ui/`, `scripts/**` the harnesses and gates, `docs/**`
  the doc tree, `docs/PRD.md` the spec.
- **Public on both remotes and published to PyPI.** `origin` is
  `arango-solutions` (primary) and dual-pushes to the personal fork — one `git
  push` publishes to both.
- Engineering rules live in `AGENTS.md` and `CLAUDE.md`. `CLAUDE.md` is
  gitignored as per-user harness config; `AGENTS.md` is merely untracked. Note
  `/prd-sync` reads its identity block from `AGENTS.md` first, and `AGENTS.md`
  currently has none, so the sync silently falls back to `CLAUDE.md`. Size limits: source 1500 lines, tests 2000, config 500,
  docs 1000. The rules with teeth for this audit: mock only at external
  boundaries, every public entry point constructed for real in at least one test,
  and known defects pinned with `xfail(strict=True)` rather than tolerated.
- Spec-driven with enforcement: `/prd-sync` audits code against `docs/PRD.md` in
  both directions, `drift_alerts` holds open gaps, `prd_patches` holds proposed
  PRD changes, and PRD edits require acceptance rather than happening silently.
- The repository's signature defect class, found by its own July 2026 review and
  repeatedly since: **something built but never wired into anything that
  exercises or enforces it.** It recurs inside fixes, not just features — a guard
  added to one of two paths, a Makefile target pointing at an ignored directory,
  a CLI whose service was tested but which itself never ran.
- Benchmarks are the project's evidence base and its most load-bearing prose.
  `python scripts/run_er_benchmarks.py --dataset all` reproduces them; a figure
  that does not reproduce is a defect of the same severity as a code bug.

## Known clean as of 2026-09-29 (first run)

Re-check only if the named code moved. Everything here was verified by execution.

**Duplication.** Suppressed-edge filtering is correct in all five clustering
backends plus `wcc_clustering_service.py:503` and
`feedback_application_service.py:172` — the 2026-07 defect is fully closed.
Degenerate-fit warning parity is present on both `estimate_mu` and
`estimate_categorical_mu`, persisted type-agnostically. `preserve_missing=True`
parity holds in both EM sampling paths. `validate_field_name(analyzer)` is in both
BM25 and hybrid. `_normalize_pairs` covers all nine strategies (graph-embedding
delegates to vector, deliberately). `explain()` re-derives through the same helpers
`score()` sums, so the waterfall cannot drift from the total.

**Security.** No secret is in git in any of 350 commits, on any ref — all 14
secret-shaped `.env` values grepped against every tracked blob. `.env` is ignored
at `.gitignore:17`. AQL injection is broadly clean: all 88 interpolated-AQL sites
AST-parsed, bind variables used correctly, unbindable identifiers validated at the
constructor; only `pipeline_utils.get_pipeline_statistics` lacks its siblings'
validation, and its sole caller validates first. UI `require_auth` is global over
`/api/*` with only health and OPTIONS exempt; `readonly` is enforced at all nine
mutating handlers. Config endpoints never serialise connection parameters. MCP
transport auth uses constant-time compare with a loopback guard.

**Docs.** `docs/benchmark_results.json` agrees with the `BENCHMARKS.md` summary
tables cell for cell, and README/SOTA restate those four headline figures
correctly. Version consistency holds across the four gated sources. Scorecard
arithmetic computes correctly from its own columns. MCP resource count (2) is
right everywhere. Record counts agree with the JSON throughout. `docs/archive/**`
duplication is expected — do not re-report.

**Counts settled.** 17 MCP tools (`@mcp.tool()` decorators) — every stated count is
correct. Five clustering backends; PRD's "six" counts `auto`.

## What the first run found that is NOT yet fixed

Do not treat as clean: the `scan_secrets.py` allowlist and placeholder gaps, the
`_er_pipeline_runs` reserved name, `u` unclamped at 1.0, `hybrid_blocking`'s
`_key <` filter under a per-entity LIMIT, `similarity_service`'s email/phone null
handling, `mask_fields` being unwired, the export route's unvalidated paths, and
the retracted accuracy claim surviving in `demo/`.

## Output

Two parts, and the second is the one that gets acted on: **the report** is what
you found, **the plan** is what someone does with Monday morning.

### The report

Ranked by consequence, most severe first, leading with the single thing to fix
today. Say what is healthy before what is broken — it is load-bearing context for
how much the findings mean, and a review that opens on a wall of defects reads as
noise even when every item is real.

For each finding: `file:line`, the defect in one sentence, the scenario in which
it bites, the fix, and **whether you verified it by execution or it remains
inference**. Never blur those two — the whole value of this audit is that its
claims were checked, and one unmarked guess costs the reader their trust in the
rest.

### The plan

Group the findings into PR-sized units of one concern each — a unit a reviewer
can hold in their head in five minutes and roll back on its own. Then:

- **Order them**, and say why that order: which must land first because another
  reads its output or edits the same lines, and which are independent and can go
  in parallel.
- **For each unit, say whether it becomes a test or stays a prose finding.**
- **Separate the mechanizable from the judgment calls**, because they need
  different people and different amounts of time. "No `getenv` outside config" is
  an afternoon; "these 73 env reads need an owner" is a decision someone owns.
- **Say what you are deliberately not proposing**, and why. A finding left
  unfixed on purpose is a decision; a finding left out silently is a gap.

Then offer to open them as separate branches.
