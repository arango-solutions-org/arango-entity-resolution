---
name: pr-review
description: Review one pull request on arango-entity-resolution (arango-solutions/… or the ArthurKeen fork) by verification — run every claim the PR makes rather than reading it, apply this repo's own rules (mock only at external boundaries, entry points constructed for real, strict-xfail ledger, sibling-path guards, docs and published-results conformance, committed benchmark artifacts, UI contract regeneration, PRD changes only through accepted patches, public-repo and PyPI hygiene), and produce a draft review for the user to approve before anything is posted. Use when asked to review a PR, check whether a PR can merge, or re-check a PR after its author pushed fixes. NOT the whole-repo audit — that is `/code-quality-review`.
---

# PR Review

One pull request, reviewed by verification. The built-in `/code-review` reads a
diff and finds bugs; this runs the repo's checks against the branch, in a
separate checkout, and drafts a review that says which claims were executed and
which remain read.

## Invocation

`/pr-review 5` — full review, draft only.
`/pr-review 5 recheck` — the author pushed after review: re-run each finding's
reproduction on the new head, nothing else.
`/pr-review 5 post` — post the approved draft (only after the user has seen it).

The number alone is ambiguous here: PRs live on two repositories (see below).
Resolve which one before doing anything else, and name it in the draft.

## The two rules that make it worth running

**Nothing is posted until the user has read the draft and said so.** Write the
draft in the reply, offer to post it in one line, and post it verbatim when told.

**Verify, don't opine.** Every finding names the command that produced it or
says "read, not executed". Each failure below passed CI, a green test suite, or
a reading of the code — most of them all three.

- **Seen in this repo.**
  - The Workbench's pipeline-run route created `_er_pipeline_runs`. ArangoDB
    reserves a leading underscore, so the route failed (ERR 1208) on its first
    call in every database, taking run history and progress streaming with it.
    Its route test used a `MagicMock` database, which accepts any name.
  - A steward's golden-record edit landed in a second, unlinked document: the
    apply route and `GoldenRecordPersistenceService` computed the key
    differently. The test that claimed "overrides survive a rerun" wrote the
    override straight into the database at the service's key, so it never went
    through the route whose behaviour was in question.
  - `test_resolve_reviewer_header_wins` asserted that any caller could set their
    own audit identity; an export-route test posted `output_dir` and asserted 200,
    enshrining an arbitrary file write. **A test can assert the bug.** Read what
    each changed test asserts, not just that it passes.
  - `scripts/calibrate_runtime_quality_policy.py` called a method that does not
    exist. The service it wrapped had unit tests and passed all of them; nothing
    ran the script.
  - A published benchmark table had five of nine rows wrong, including the
    headline, for four weeks. The degenerate-fit guard that would have caught it
    existed on one of the two EM paths. **When a PR adds a guard, ask which sibling
    paths share the failure mode** — that question has the best hit rate here.
  - CI ("Python Library") failed at test collection on every run from August 7
    to September 29: `mcp` 2.x removed a module and the extra had no upper bound.
    Every doc said CI ran the gates. **A red pipeline hides new reds**; compare
    the PR's checks step by step against `main`'s last run.
  - Statistics fakes dispatched on the exact text of a wrong AQL query and
    returned the total that query never produced on a real server. A fake keyed
    on query text certifies the query, right or wrong.
  - A test file or function with "benchmark" in its name is marked `performance`
    by `conftest.py` and silently excluded from `-m unit`, so it never gates.
  - The same commit (`ac6bbd8`) is green on the fork and red on arango-solutions:
    a later re-run (attempt 2) failed collecting `tests/test_test_environment_safety.py`,
    whose `from tests.conftest import …` works only when another test module has
    already put the repo root on `sys.path`. **Both repos run CI on every push,
    and a re-run is a new experiment.** A PR's red check may be `main`'s red.
- **Seen in the user's other repos.**
  - About 3,000 green tests patched the one function that was wrong. A stubbed
    seam proves nothing about the seam.
  - "Tenant A sees none of B's rows" passed because B had no rows. Every negative
    assertion needs a positive control.
  - A failed CI step skips every later step in its job; a red "lint" job had
    hidden six other gates for months.

Re-run every finding before you post it.

## This repo's shape — read before anything

- **Two repositories, both public, both on PyPI's path.**
  `arango-solutions/arango-entity-resolution` is primary; the
  `ArthurKeen/arango-entity-resolution` fork holds most PR history (#23–#30) and
  the issues. Pass `--repo` to every `gh` call. Security findings stay out of the
  public draft and go to the user separately.
- **One `git push` publishes to both.** `origin` has two push URLs. There is no
  pushing to just one, so every merge is a publish to the org repo.
- **Merging is local, not `gh pr merge`.** The user's workflow is: merge into
  `main` locally (fast-forward where possible; PR #26 went in as a local merge
  commit), let the pre-push hook run the tests, push once. GitHub marks the PR
  merged when its commits reach `main`. A GitHub-side merge on one remote leaves
  the other behind and, if squashed, rewrites the commit IDs the review quoted.
  Merging is the user's decision; the review only recommends.
- **No branch protection, no required reviews.** Nothing stops a merge on red CI.
  The review is the gate.
- **Who opens PRs.** The user mostly pushes straight to `main`. A PR here is
  either something they chose to put up for review (often docs or rules, like
  #5) or a contributor's work. GitHub refuses `--approve`/`--request-changes` on
  your own PR, so for the user's PRs post with `--comment`.
- **Releases are not part of a PR.** The version is stated in six places that
  `scripts/check_version_consistency.py` holds equal (`constants.__version__`,
  CHANGELOG, PRD, README, `docs/README.md`, `ui/openapi.json`). It moves only at
  release, and `publish.yml` publishes to PyPI on a GitHub release. Never create
  a tag or release during a review.
- **The main checkout's `.env` holds live credentials and a remote
  `ARANGO_ENDPOINT`.** litellm calls `load_dotenv()` on import, which searches
  *upward* from the working directory. Never run a PR's code from the main
  checkout, and put the worktree **outside** the repository (the scratchpad), so
  no `.env` is found above it.
- **Port 8529 is another project's live database** (`cmf-arangodb`). Never point
  `ARANGO_TEST_*` at it. Use a disposable container (below).
- **The rules are in gitignored or untracked files.** `CLAUDE.md` is gitignored
  and `AGENTS.md` is untracked, so a contributor's clone has neither. Quote the
  rule in the review rather than citing the file.

## Method

### 0. Load the context before reading the diff

```sh
R=arango-solutions/arango-entity-resolution      # or ArthurKeen/arango-entity-resolution
gh pr view N --repo $R \
  --json title,author,headRefName,baseRefName,headRefOid,isDraft,mergeStateStatus,files,body,reviews,comments
gh pr checks N --repo $R
# step-level failures and skips, for the PR's latest run and for main's (repeat with --branch main)
ID=$(gh run list --repo $R --branch <headRefName> --workflow "Python Library" --limit 1 --json databaseId -q '.[0].databaseId')
gh run view $ID --repo $R --json jobs \
  -q '.jobs[] | .name as $j | .steps[] | select(.conclusion=="failure" or .conclusion=="skipped") | "\($j): \(.name) \(.conclusion)"'
gh issue list --repo ArthurKeen/arango-entity-resolution --state open
git fetch https://github.com/$R.git "pull/N/head:refs/remotes/pr/N" && H=pr/N   # works for fork PRs too
git log --oneline origin/main..$H && git diff origin/main...$H --stat
git log --format=%h "$H" -- .env                      # must print nothing
```

`origin` fetches from arango-solutions, so a PR on the fork must be fetched by
URL as above. Read the existing reviews first; if one already asked for changes,
the job is `recheck`. If the base is not `main`, review only what this PR adds
on top of its base, and say so. Then read the whole diff and every new file in
full.

**A contributor's PR runs on this machine when you test it.** Before running
anything, read its changes to `tests/conftest.py`, `scripts/`, the `Makefile`,
`pyproject.toml`, `.githooks/`, `.github/workflows/`, `ui/package.json` scripts,
and `.claude/`.

### 1. Does it merge, really

`mergeStateStatus` lags, so do the merge yourself:

```sh
W=$SCRATCH/wt-merge && git worktree add -q --detach $W origin/main && cd $W \
  && (git merge -q --no-edit $H && echo clean || { git diff --name-only --diff-filter=U; git merge --abort; }) \
  ; cd - && git worktree remove --force $W
```

Also say whether it fast-forwards (`git merge-base --is-ancestor origin/main $H`),
because that decides how the user merges it.

### 2. Run what CI runs, in a worktree

The package is an **editable install**: the venv imports the main checkout's
`src/` unless told otherwise, and `pytest.ini` sets no `pythonpath`. Without
`PYTHONPATH=$W/src` the review silently tests `main` and reports it as the PR.

```sh
REPO=$(git rev-parse --show-toplevel); V=$REPO/.venv/bin
W=$SCRATCH/pr-N && git worktree add -q --detach $W $H && cd $W
export PYTHONPATH=$W/src USE_DEFAULT_PASSWORD=true
$V/python -c 'import entity_resolution; print(entity_resolution.__file__)'   # must be under $W

# run every gate and report each result; never chain with && (a failure would hide the rest)
$V/flake8 --select=E9,F63,F7,F82 --show-source src/ tests/
$V/python scripts/scan_secrets.py --committed-only
$V/python scripts/check_version_consistency.py
$V/python -m pytest -m unit -q -p no:cacheprovider \
  --cov=src/entity_resolution --cov-report=term-missing:skip-covered --cov-fail-under=72
$V/python scripts/check_scorecard.py               # exit 1 = arithmetic (blocking); 2 = advisory
```

Compare passed/skipped/deselected counts with the PR description and with
`main`. A rise in **deselected** usually means a new test name contains
"benchmark" or "integration" and is not gating (see rule list).

Run these as well, depending on what the PR touches:

- **`src/entity_resolution/ui/`, schemas, or `ui/`** — the UI Contract job:
  ```sh
  $V/python scripts/export_openapi.py && (cd ui && npm run gen:types)
  git diff --exit-code -- ui/openapi.json ui/src/api/schema.ts
  ```
  Borrow `node_modules` only if `ui/package-lock.json` is unchanged
  (`ln -s $REPO/ui/node_modules $W/ui/node_modules`), else `npm ci`. Then
  `(cd ui && npm run typecheck && npm run test)`. A route registered only when
  `ui/static` exists must stay `include_in_schema=False`, or the contract
  depends on whether the generating machine built the frontend.
- **AQL, persistence, strategies, clustering, or anything whose correctness is
  what the database does** — integration tests on a disposable server, never
  port 8529:
  ```sh
  docker run -d --rm --name er-pr-N -p 127.0.0.1:18529:8529 -e ARANGO_NO_AUTH=1 arangodb:3.12.11
  ARANGO_TEST_HOST=127.0.0.1 ARANGO_TEST_PORT=18529 ARANGO_TEST_PASSWORD=unused \
    $V/python -m pytest -m integration -q -p no:cacheprovider <relevant test files>
  docker stop er-pr-N
  ```
  CI does not run integration tests, so this is the only evidence they pass.
- **Matching, learning, blocking, or `docs/BENCHMARKS.md`** — re-run the affected
  rows and compare with the committed artifacts. FS training is seeded, so the
  match must be **digit-exact**:
  ```sh
  $V/python scripts/run_er_benchmarks.py --dataset febrl3 --scoring-method fellegi_sunter \
    --comparison-levels auto --host 127.0.0.1 --port 18529 --password unused \
    --data-dir $REPO/.benchmark_data --output $SCRATCH/febrl3-fsml.json
  ```
  Each row's exact command is in `docs/benchmark_results_febrl.json`. The
  review-band oracle is free: `scripts/measure_review_band.py`.
  `scripts/measure_llm_band.py` **spends money and sends records to a provider**
  unless the model is `ollama/…`; never run it against a paid model without the
  user's yes.
- **`pyproject.toml` or new top-level files** — build and list the sdist, which
  is an explicit allowlist: `$V/python -m build --sdist -o $SCRATCH/dist && tar tzf $SCRATCH/dist/*.tar.gz`.
  Check that a new dependency's optional extra has an upper bound on its major
  version (`mcp>=1,<2` exists because one did not).
- **`.github/workflows/`** — a workflow that fails validation runs no jobs and
  shows no red. Confirm the changed workflow actually produced a run.

Remove the worktree when done: `git worktree remove --force $W`.

### 3. Verify every claim that can be verified

| The PR says | Run |
|---|---|
| "fixes X" / "adds a regression test" | revert the fix in the worktree (`git show origin/main:<file> > <file>`), run the test, confirm it fails, then restore. A fix with no test that fails without it is a finding |
| "removing Y breaks test Z" (a mutation claim) | apply the mutation and run Z. Say which mutations held |
| a known bug left in place | it must be pinned `xfail(strict=True, reason="KNOWN BUG: …")`; run with `--runxfail` and confirm it fails on the stated defect, not on an unrelated error |
| "tested end to end" | does any test patch, `MagicMock`, or hand-fake the function or seam whose behaviour is in question? Does a test construct one side of a cross-layer identity (a key, a collection name, a hash) by hand instead of going through both real entry points? |
| new class, strategy, backend, CLI command or route | constructed for real in a test with the arguments `inspect.signature` reports; the conformance suite covers a new strategy; a route is hit through `create_app`, not the handler |
| a new guard or validation | name the sibling paths with the same failure mode (binary and categorical EM; `compute` and `compute_detailed`; bm25 and hybrid blocking; pipeline and `from_provider_config`) and check each has it |
| a config key | it round-trips through `from_dict`/`to_dict`, `validate()` covers it, and it reaches the code that uses it — the loader drops unknown keys silently, and the pipeline once dropped a whole parsed `llm:` block |
| a README, BENCHMARKS or scorecard number | `tests/test_docs_conformance.py`, `tests/test_published_results_conformance.py` and `scripts/check_scorecard.py` pass; recompute anything they do not cover |
| "see `path`" / a cited commit | `git cat-file -e "${H}:path"`; for a commit, `git merge-base --is-ancestor <id> origin/main` |
| "proposed as a PRD patch" / "accepted" | query `prd_patches` for `project_id == "arango-entity-resolution"` through the memory MCP; confirm the record exists and its `review_state`. If the memory MCP is down, say "not executed" |
| "closes #N" | read the issue on the fork; say which acceptance criteria the PR does and does not meet |

### 4. The repository's own rules

From `CLAUDE.md` (gitignored) and `AGENTS.md` (untracked) — quote them, since
the author may not have them:

- **Mock only at external boundaries.** The database wire, an LLM API, the
  network and the clock may be faked. Never mock a class you own inside its own
  test, never patch a method of the object under test. Prefer the strict
  `FakeDatabase` in `tests/test_wiring_conformance.py`, which enforces ArangoDB's
  collection-naming rule; a `MagicMock` database accepts anything.
- **Every public entry point is constructed for real** in at least one test,
  with arguments verified by `inspect.signature`.
- **Known defects are pinned, not tolerated** — strict xfail, tight assertion.
- **Ratchets move up only.** The 72% coverage floor and the F1 floors in the
  matching-quality gate are raised in the commit that earns it, never lowered.
- **Published figures reproduce from committed artifacts.** A changed benchmark
  figure changes its JSON artifact in the same PR, recorded with its command.
- **PRD changes go through accepted patches.** A PR that edits `docs/PRD.md`
  must correspond to `prd_patches` records the user accepted; anything else is a
  decision for the user, not a finding to fix. A behaviour change with no
  requirement behind it should arrive with a proposed patch.
- **Generated files are regenerated, not hand-edited**: `ui/openapi.json` and
  `ui/src/api/schema.ts` together.
- **Secrets and hygiene.** The repo and its sdist are public. No `.env`, keys,
  internal hostnames or customer names anywhere. The `scan-secrets: allow`
  pragma is only for a deliberate example; a new one on anything else is a
  finding.
- **Size limits.** Source 1500 lines, tests 2000, config 500, docs 1000.
- **Honest prose.** No unmeasured performance or accuracy claims; a retracted
  figure is named, not silently replaced.

### 5. Flag for the next code-quality-review

`code-quality-review` is this repo's periodic whole-tree audit (duplication,
hardwired values, security, docs drift, docs duplication, PRD quality) — run
every few weeks across six parallel agents, not scoped to one diff. Don't
invoke it here. But if this PR's diff introduces or reveals a duplication, a
value that should flow through env but is baked in instead, or a pattern one
of its six dimensions would flag, say so explicitly in the report — that's
what lets the next periodic run skip ground this review already covered,
instead of rediscovering it cold. If `code-quality-review`'s own file has a
"Known clean" section, check it first: don't re-raise something already
verified there unless the code it covers has moved.

### 6. `recheck` — after the author pushes

Re-fetch `pull/N/head`. For each finding, re-run its reproduction on the new
head and report pass or fail. If the review gave no reproduction, build one
before judging, and say so. Then compare the checks with `main`'s again.

## Output

Draft the review in the reply. Say in one line who it is written for, then give
the review, ready to paste:

1. **Verdict in one sentence**: merge, merge after X, or don't merge yet, and why.
2. **Verified**: what was run and passed. Lead with this.
3. **Must fix before merge**, numbered, each with its command or `file:line`.
4. **Should fix** and **Minor**.
5. **Answers to the author's own open questions**, if any.
6. **Decisions for the user**, kept separate and never buried among findings: a
   PRD patch to accept, a merge route, a release, a disclosure.

Write in plain language, and give each finding as **Context / Action / Result**.
No generic praise and no first person ("X does not hold: Y", not "I checked X").
No internal code names a reader cannot look up. **Both repos are public:** keep
security findings out of the draft and give them to the user separately.

Post with `gh pr review N --repo $R --comment|--request-changes|--approve --body-file -`,
using `--comment` on the user's own PRs.

## Known gotchas

- `git fetch origin pull/N/head` only reaches arango-solutions. Fetch a fork PR
  by URL: `git fetch https://github.com/ArthurKeen/arango-entity-resolution.git "pull/N/head:refs/remotes/pr/N"`.
- zsh: write `"${H}:path"`, never `$H:path` (`:r` and `:t` are modifiers). An
  unquoted `$VAR` holding several words is **one** argument; use an array, e.g.
  `E=(env A=1 B=2); "${E[@]}" cmd`.
- Without `PYTHONPATH=$W/src`, everything imports the main checkout. Check
  `entity_resolution.__file__` every time.
- A worktree under the repo directory still finds the main `.env` via litellm's
  upward `load_dotenv()`. Keep worktrees in the scratchpad.
- `docker run --rm` containers vanish on `docker stop`; `docker start` cannot
  revive them.
- `rm` on a `$VAR/*` path is blocked by a safety check; write `"${VAR:?}"/*`.
- `mypy` is not in the dev venv; CI's typecheck is advisory, so say "not
  executed" rather than installing it into the shared venv.
- `gh pr checks --watch` can exit while a job is still pending. Loop on
  pending/queued/in_progress instead.
- Every `gh run …` call needs `--repo`: there is no `gh` default repo here, and
  the two repos' runs for one commit can disagree. Check `attempt` too.
- The memory MCP (for `prd_patches`) is sometimes disconnected. A claim that
  needs it is "not executed", not "verified".
- macOS has no `timeout`. Run mutations one at a time, restore with
  `git checkout -- <file>` only for files the PR did not change (otherwise
  `git show $H:<file> > <file>`), and check `git status` is clean before removing
  the worktree.
