# Product Requirements and Roadmap

This document captures the shipped baseline through `v3.9.0` and the forward-looking product roadmap.

---

## Product Overview

**Product**: ArangoDB Entity Resolution System
**Current Release**: `3.10.0`
**Status**: Published, tested, and production-ready for the currently shipped scope

### Goal

Provide a practical, ArangoDB-native entity-resolution toolkit that supports:
- batch entity-resolution pipelines with pluggable clustering backends
- interactive inspection and analyst workflows
- AI-agent access via MCP
- optional LLM-assisted review for ambiguous matches
- export/reporting and evaluator-ready benchmark workflows
- enterprise-scale clustering via ArangoDB Graph Analytics Engine (GAE)
- cross-platform embedding execution with GPU-readiness infrastructure

## Stakeholders

- Product and platform engineers
- Data engineers
- Data analysts and reviewers
- AI-agent / tool-integration consumers
- Business owners who need trustworthy deduplication outputs

---

## Shipped Scope Through 3.9.0

### Core Resolution Workflow

- Candidate generation through exact/COLLECT, BM25, vector, LSH, geographic, and graph-traversal blocking paths
- **BM25 text blocking** defaults to disjunctive token match (`match_mode: tokens`), ranked by BM25 score. Legacy phrase match (`match_mode: phrase`) remains for backward compatibility but is near-exact and unsuitable for noisy product text. BM25 searches one field and filters on at most one. It reads `blocking.search_field` (falling back, with a warning, to the first entry of `blocking.fields`) and takes an equality filter only from an explicit `blocking.blocking_field`; other `fields` entries are ignored with a warning. A computed field cannot be the search or filter field, since the view indexes stored attributes. Zero candidates from a non-empty collection are reported as a likely misconfiguration, never as a clean result.
- Weighted similarity scoring with configurable field weights
- Config-driven pipelines via `ERPipelineConfig` and `ConfigurableERPipeline`
- Similarity edge creation and WCC clustering with pluggable backends
- Golden-record persistence support

### Clustering Backend Abstraction (3.3.0–3.5.0)

- Five pluggable WCC backends (`python_dfs`, `python_union_find`, `python_sparse`, `aql_graph`, `gae_wcc`), plus an `auto` selector that chooses among them
- Automatic backend selection (`backend='auto'`, default since 3.5.0) based on edge count, optional dependency availability, and GAE status
- Union-Find backend with path compression and union by rank
- Sparse backend via `scipy.sparse.csgraph` for large dense graphs (optional dependency)
- GAE backend managing full engine lifecycle (deploy, load, WCC, store results, cleanup)
- Dual-mode GAE connection layer for self-managed (JWT) and ArangoGraph Managed Platform (oasisctl) deployments

### Embedding Runtime Expansion (3.3.0–3.4.0)

- Device auto-detection: `device='auto'` (default since 3.4.0) resolves to CUDA, MPS, or CPU
- ONNX Runtime backend scaffold with provider resolution and CPU fallback
- Runtime health CLI commands: baseline, compare, and CI gate workflows
- Explicit `batch_size` and `max_batch_size` (OOM safety) for embedding workloads
- `runtime` config field for future ONNX Runtime promotion

### LLM Provider Configuration (3.3.0–3.4.0)

- `LLMProviderConfig` for structured Ollama, OpenRouter, OpenAI, and Anthropic settings
- `LLMMatchVerifier.healthcheck()` for provider reachability validation
- `healthcheck_on_start`: the pipeline probes the provider when it builds the verifier, and reports the result in the run's statistics without aborting

### Trust and Review Features

- Cluster quality metadata (`edge_count`, `average_similarity`, `density`, `quality_score`)
- `merge_entities` preview in the MCP path
- Active-learning configuration for uncertain-pair review
- LLM-assisted verification through `LLMMatchVerifier` / `AdaptiveLLMVerifier`

### User-Facing Interfaces

- `arango-er` CLI, by family: pipeline (`run`, `status`, `clusters`, `export`, `watch`, `repair-clusters`, `migrate`); data preparation (`profile`, `estimate`, `canonicalize`, `address-resolve`); the Workbench (`ui`); embeddings (`embedding-benchmark`, `onnx-export`); evaluation (`benchmark`); runtime health and quality gates (`runtime-health*`, `runtime-quality*`, `runtime-activation-summary`). `arango-er --help` is the authoritative list.
- `arango-er-mcp` MCP server: 17 tools, 2 resources
- `arango-er-demo`

### Reporting and Evaluation

- JSON/CSV cluster export artifacts
- Cluster and pipeline statistics for downstream reporting
- Exact-vs-BM25 blocking benchmark workflow built on `ABEvaluationHarness`
- Runtime health comparison artifacts (JSON, Markdown, CSV)
- **LLM verification accounting**: the optional LLM tier is measured rather than assumed - accuracy against the plain score threshold, cost per pair, and latency, on a sampled band of a public benchmark, with an oracle bound establishing what any adjudicator could deliver before one is chosen.

### Matching Quality Improvements

- Config-driven similarity field transformers for phone, state, street suffix, and company suffix normalization, plus `missing_sentinels` to map placeholders such as `NULL`, `UNKNOWN`, and `N/A` to absent values so they follow null-comparison semantics
- Fellegi-Sunter probabilistic scoring with unsupervised EM parameter estimation (m/u probabilities, log-likelihood weights, versioned model persistence keyed by config hash), selectable alongside weighted-heuristic scoring; field profiling that classifies each field's semantic type (including numeric vectors and multi-word phrases), completeness and cardinality, and emits a similarity configuration whose per-field comparator choices take effect through `similarity.field_algorithms`; fields it cannot compare with a string measure are listed with the reason they were left out
- **Null comparison level**: unobserved fields contribute zero evidence, distinct from an observed mismatch which takes the full disagreement weight. Training and scoring share this definition, so per-field m/u are estimated only over the pairs where that field was actually compared
- **Two-population parameter estimation**: `m` from blocked candidate pairs (where true matches concentrate) and `u` from the population the model will actually score, named explicitly per model. For the binary path that is a random sample of record pairs, measured directly rather than inferred jointly, because candidate pairs have already passed a similarity gate and cannot furnish a representative non-match sample. For the multi-level path the default is the blocked candidate population, because taking `u` from random pairs there measured *worse* at the shipped operating point — a `u` estimated over a population the model never scores makes it overconfident. Each persisted model records which regime produced it
- **Term-frequency-adjusted agreement weight**: when two records share an identical value, the match weight is computed from that value's observed frequency rather than the field's average chance-agreement rate, so agreeing on a rare value counts as stronger evidence than agreeing on a common one. Values absent from the maintained per-field table fall back to the field average rather than being guessed
- **Multi-level comparison bands**: a field may be compared at several ordered levels (for example exact / close / else) rather than one agree/disagree cutoff, with per-level m/u learned by EM. Only the band structure is configured; the probabilities are estimated, so a configured table cannot assert values that contradict the data. The band structure forms part of a model's identity, so changing it invalidates a previously trained model rather than silently reusing parameters learned under different bands. Bands may also be inferred per field from the observed score distribution, and inference declines rather than guessing when a field shows no separation. Weighted similarity remains the default for text-heavy data because it measured better there — not because the path is unwired; on structured multi-field records the probabilistic path measures better (`docs/BENCHMARKS.md`)
- **Data-driven threshold selection** (`similarity.auto_threshold`, off by default): unsupervised inference from the score distribution via Otsu's method, plus supervised selection from labelled pairs. Inference is refused when the scores are not meaningfully bimodal, so the configured threshold is never replaced by an unsupported guess

### Graph-Aware and Incremental Resolution (Phase 3.1–3.4)

- Graph-context relationship features contributed to Fellegi-Sunter scoring as ordinary learned fields
- Collective / iterative resolution with fixpoint and cycle detection, reachable from `ConfigurableERPipeline.run()` via `collective.enabled`
- Incremental cluster maintenance: single-record resolve-and-commit with verdict-preserving, idempotent re-clustering. Handles merges and human-verdict splits; data-driven splits from record *updates* are not yet retracted
- Graph-embedding blocking over node2vec-style embeddings (prototype; unweighted random walks with count-SVD, hard-capped node count)
- Shard-parallel blocking for sharded clusters (note: pairs whose members live on different shards are only found when the blocking fields match the collection's shard keys)
- Hybrid blocking combining BM25 and Levenshtein candidate generation
- `AddressERPipeline` for street/city/state/postal resolution
- Cross-collection matching for linking entities across two collections
- MCP canonical `options`-based request shape with legacy reconciliation and deprecation warnings

### Canonical-Hub Resolution

- Precision-first, read-only resolution of one incoming record to an existing canonical entity (`entity_resolution.canonical_hub.SemanticCanonicalHubResolver`): it resolves, abstains, or refuses with a stated reason under an explicit precision, scope and observable-field policy, with embedding, candidate retrieval and verification injected.
- The ArangoDB candidate provider uses the native vector index only, with no exact or Python fallback.
- The request-side checks (account scope, deadline, oracle identifiers, observable fields, usable values) are a public, pure function that the resolver itself calls, so a consumer that guards the resolver independently applies the same rules without copying them; the reason vocabulary and oracle-key set are public. Whether an observable field that is present but unusable is ignored or refuses the request is a profile setting.

### Evaluation and Verifiability

- Cluster-level metrics: B-cubed precision/recall/F1 and pairwise metrics over the transitive closure of produced clusters
- Published, reproducible results on public record-linkage benchmarks — the Leipzig linkage datasets and the FEBRL deduplication datasets (`scripts/run_er_benchmarks.py`, `docs/BENCHMARKS.md`)
- Per-decision match-weight decomposition (additive log-odds waterfall) exposed through `explain_match`
- Mechanical quality gates in CI: blocking lint, secret scanning, version consistency, wiring/contract conformance, matching-quality F1 floors, coverage floor

### Steward Workbench UI (3.8.0)

- Optional browser-based curation UI (`pip install "arango-entity-resolution[ui]"`, `arango-er ui`): dashboard, review queue with verdict capture, cluster browse/edit with audit trail, threshold tuning, golden-record survivorship editing, data profiling, and pipeline execution with progress streaming
- All UI operations route through existing services (`FeedbackApplicationService`, `GoldenRecordPersistenceService`); no parallel resolution logic
- Manual golden-record field edits are stored as `fieldOverrides` and survive subsequent pipeline rebuilds: recomputed machine-derived values may change, but a steward override takes precedence until explicitly removed. Golden-record control metadata (`clusterId`, `clusterSize`, `memberIds`, `sourceClusterHash`, `stale`, `method`, `fieldOverrides`, and related fields) is protected from both source-document columns and steward edits

---

## Current Functional Requirements

### FR-1. Pipeline Execution

The product must allow users to run ER pipelines from configuration without writing orchestration glue code.

Similarity supports a per-field algorithm, so short names can use an edit-distance measure while phrases and titles use a token measure in the same run.

### FR-2. Result Inspection

The product must expose cluster summaries, cluster quality signals, and collection-level status in both CLI and MCP-facing workflows.

**Cluster output must be validated for structural integrity, not only produced.**
Validation must detect entities appearing in more than one cluster, clusters
below the configured minimum size, and clusters above a configured maximum — the
last because connected-component clustering takes the transitive closure, so a
single spurious edge can silently merge unrelated entities while the run reports
success. Suspect clusters are flagged for review, never discarded: removing them
deletes the evidence of the defect along with the data.

### FR-3. Review and Adjudication

The product must support optional active-learning and LLM-assisted review for ambiguous pairs without forcing those dependencies into the default runtime path.

**Adjudication decisions are binding on every execution path.** A pair recorded as
`no_match` must not appear in the same cluster under ANY clustering backend, and a
confirmed pair must survive a full rebuild. Backends that cannot express this
filter natively must achieve it by other means rather than ignoring it.
Parametrized conformance tests verify suppressed-edge exclusion across every WCC
backend, including GAE's active-edge projection. Confirmed-pair survival is
integration-tested, but per-backend parametrized confirmation coverage remains
to be added.

**Every irreversible curation action is audited.** A cluster merge or split, a
golden-record edit, an adjudication verdict and a threshold change must each
append an attributed entry to the audit trail. Auditing must never block the
action it records, but a failed audit write must be reported rather than
discarded: an action whose accountability record was lost silently is
indistinguishable from one that was never audited. Per-entity history must remain
retrievable at a cost that does not grow with the age of the log.

**Steward corrections survive recomputation.** A manually corrected golden-record
field must not be reverted by a subsequent pipeline run. Manual values are
recorded as overrides and re-applied after recomputation, with provenance
identifying them as human rather than machine choices.

**Resolution reflects the current clusters.** After a persistence run, every
source record resolves to at most one golden record: the one built from its
current cluster. A golden record that no current cluster produced must be
flagged stale, with the reason and time, and must not be silently deleted, so
that steward overrides and history on it remain reviewable. A cluster change does
not carry overrides to the new golden record automatically; the stale record
surfaces them for a steward.

### FR-4. Portability

The product must allow users to export results in JSON and CSV for analyst and downstream-system consumption.

### FR-5. Evaluation

The product must provide one supported benchmark workflow that compares blocking strategies using a simple ground-truth input format.

**Cluster-level quality.** The product must measure final cluster quality with
entity-centric metrics (B-cubed precision/recall/F1) alongside pairwise metrics
computed over the transitive closure of the produced clusters, so that
over-merging and under-merging are penalised symmetrically and the precision cost
of chain merges is measurable against ground truth.

**Public benchmarks.** The product must be measurable against public, third-party
entity-resolution benchmarks, reporting blocking pair completeness and reduction
ratio, pairwise precision/recall/F1, and entity-level B-cubed
precision/recall/F1, together with the configuration that produced them. Results
must be reproducible by a single documented command and published with the
release, so matching-quality claims are falsifiable rather than asserted.

**Evidence before recommendation.** A scoring method must not be presented as a
recommended default until benchmark evidence shows it competitive on the
published datasets. This project shipped a statistically more sophisticated
matcher that measured *worse* than the simple one on every text-heavy dataset,
and *better* on every structured multi-field dataset; only measurement revealed
either. A scoring method's recommendation is therefore conditional on data shape,
and the condition is measurable in advance: Fellegi-Sunter's advantage tracks the
spread in per-field chance agreement (the sum of each field's squared value
frequencies), which needs no labels.

**Parameter estimation must name its reference population.** `u` = P(field
agrees | non-match) is only meaningful relative to a population, and the choice
materially changes calibration: measured on DBLP-ACM, taking `u` from random
record pairs rather than from the blocked candidates the model actually scores
moved F1 at the shipped threshold from 0.911 to 0.672, while leaving peak F1
identical. The product must therefore make the population explicit and record it
on the persisted model.

**A degenerate fit must be reported, not returned silently.** Where estimation
can converge to a solution that is unusable on its face — such as a match prior
above 0.5 over blocked candidate pairs, which blocking makes impossible by
construction — the product must flag it on the model and surface it to the
caller. A model whose parameters are unfit must not be indistinguishable from one
that is.

**A review band must be justified against the error distribution, not
assumed.** Routing pairs to human or model adjudication is only worth its cost if
the band actually contains the errors. The product must be able to report what
share of its errors fall inside a candidate band, and must not present a fixed
default as suitable without that evidence: measured on Amazon-Google, the shipped
0.55-0.80 band held 8.5% of errors against 61% for 0.30-0.95, a difference
between a tier worth +0.02 F1 and one worth +0.25.

**A published figure must reproduce from a committed artifact.** Every benchmark
table the project publishes must be backed by a committed result file recording
the command that produced each row, and a test must fail when the published
figure and the artifact disagree. Training must be reproducible given a seed:
two runs of the same configuration and seed must produce the same model and the
same metrics. A figure that is not artifact-backed, for example one whose raw
results were lost or whose re-measurement costs money, must say so where it is
published.

**Threshold selection.** The product must be able to choose a decision threshold
from data rather than requiring a hand-set constant. Benchmarking established
that a single fixed default is unsafe: the best-F1 threshold varies by more than
2x across datasets, and running the shipped 0.8 default on noisy product data
yielded roughly a tenth of the achievable F1. Threshold selection must therefore
be derivable from a labelled sample or from the score distribution, and the
chosen operating point must be reported with the score.

### FR-6. Integration

The product must support both human-operated CLI workflows and AI-agent workflows via MCP.

**A consumed API has a stable, versioned path.** Code that another product
depends on is exported from a public module with its public names stated, ships
in a tagged release, and is changed incompatibly only after a deprecation that
names the replacement and the removal release.

### FR-7. Enterprise Scalability

The product must support optional GAE clustering for enterprise-scale graphs, with graceful fallback to local backends when GAE is unavailable.

**Measured status (2026-08-16):** blocking now executes in adaptive chunks whose
size tracks a wall-clock budget, so no single request approaches the client read
timeout. Verified at 66,879 records against the default 60-second timeout, which
previously failed outright. Chunked and unchunked runs are asserted to produce
identical candidate sets, and the query sorts by `_key` before `LIMIT` so chunks
cannot overlap or skip documents.

Throughput is still modest: ~17 minutes for 66,879 records against ~7 seconds
for 4,910. Candidate pairs are also still materialised in client memory before
deduplication, though `iter_candidates()` offers a streaming path. The README's
1M-records figure remains unsubstantiated and claims above roughly 50k records
should cite measurements. See `docs/BENCHMARKS.md#scale-limits`.

### FR-8. Steward Workbench UI

The product must provide an optional browser-based curation UI (pip extra `[ui]`,
`arango-er ui`) exposing dashboard, review queue with verdict capture, cluster
browse/edit with audit trail, threshold tuning, golden-record survivorship
editing, data profiling, and pipeline execution with progress streaming. All UI
operations route through existing services; no parallel resolution logic.

**Override survival.** Manual golden-record field edits made through the
Workbench (stored as `fieldOverrides`) must survive subsequent pipeline rebuilds.
Consolidation may recompute machine-derived values, but steward overrides take
precedence and must not be silently reverted.

**Metadata integrity.** Consolidation writes domain fields first and control
metadata last, so a source column or steward edit named like `method`,
`clusterSize`, `stale`, or `fieldOverrides` cannot corrupt golden-record state.

**Authentication UX.** When `ER_UI_AUTH_TOKEN` is configured, the health
endpoint reports that authentication is required without exposing the secret.
The SPA keeps the supplied token in tab-scoped `sessionStorage`, sends it as a
bearer credential on API calls, and authenticates pipeline WebSocket
connections. When `ER_UI_REVIEWERS` maps tokens to display names, each mapped
token is a credential in its own right and the reviewer identity is taken from
the token alone: the free-text `X-Reviewer` header is ignored, and a caller whose
token is not mapped is attributed as anonymous. Without a reviewer map,
`X-Reviewer` is a self-asserted session name used for attribution only, never for
authorization.

**Filesystem confinement.** The UI must never let a request choose a server
filesystem path. Exports are written to a directory the server owns, requests
name files only by bare generated names, and the download route serves only files
that directory contains. Unknown request fields are rejected rather than ignored.

---

## Non-Functional Requirements

- **Scalability**: Handle large datasets through blocking, set-based ArangoDB operations, and optional GAE for enterprise-scale graphs
- **Security**: Prevent AQL injection through validated identifiers, numeric coercion, and bind-variable usage across config-driven query paths. Static SPA routes must not serve files outside the packaged UI root, authenticated Workbench API and WebSocket traffic must be supported end to end, and user-controlled fields must not replace system-owned golden-record metadata
- **Maintainability**: Keep new capabilities configuration-driven and layered on existing services
- **Explainability**: Surface quality signals, backend selection rationale, structured benchmark outputs, and a per-decision evidence decomposition. For any candidate pair the system must be able to state which fields contributed to the decision and by how much, as additive log-odds summing to the final score, including the effect of value rarity. This decomposition is derived from the model itself rather than narrated after the fact
- **Verifiability**: quality intentions must be mechanically enforced, not documented only. CI blocks on syntax/undefined-name lint, committed-secret scanning, version consistency across all declared sources, wiring/contract conformance for every public entry point, matching-quality F1 floors, and a unit-test coverage floor. Current ratchet floors are **72% coverage**, **0.80 pairwise F1**, and **0.85 B-cubed F1** on the labeled regression fixture; floors rise with measured performance. Known defects are pinned with strict `xfail` markers so a fix cannot land without updating the ledger. Tests refuse to run against a non-local database
- **Extensibility**: Preserve room for future GraphRAG, geospatial, and graph-learning additions
- **Performance Portability**: Support cross-platform GPU acceleration for embedding-heavy workloads on Apple Silicon and Linux with deterministic CPU fallback behavior
- **Python Runtime**: Supported and CI-tested on Python **3.10–3.12** (`requires-python >= 3.10`)
- **Platform Baseline**: ArangoDB **3.12+** is the supported baseline. Vector / ANN blocking **requires** the native 3.12 vector index (`APPROX_NEAR_COSINE`); brute-force vector search is intentionally not supported, so vector features are unavailable on ArangoDB 3.11 and earlier. Non-vector capabilities (exact/BM25/LSH/graph blocking, similarity, clustering, golden records) do not require 3.12.

---

## Roadmap Beyond 3.9.0

These items remain forward-looking and are not part of the currently shipped `3.9.0` baseline.

### Centralized Enterprise ER Service (v4.x)

The highest-priority roadmap initiative is evolving the toolkit into a **centralized entity resolution service** — a shared enterprise infrastructure component where multiple business units submit records and receive resolved entities with global identifiers, golden records, relationship context, and enrichment signals from a continuously updated knowledge graph.

See [Centralized ER Service Design](architecture/CENTRALIZED_ER_SERVICE.md) for the full architecture and implementation plan.

#### Phase 1: Foundation (v4.0)

| Requirement | Description |
|-------------|-------------|
| **V4-FR-1: Submit-and-Resolve API** | REST endpoint that accepts a single record, resolves it against the knowledge graph, and returns the matched entity with golden record and global identifiers. Synchronous, sub-500ms p95 latency. |
| **V4-FR-2: Schema Registry** | Configurable field mapping per source/tenant, translating business-unit-specific field names to the canonical entity model. |
| **V4-FR-3: Global ID Allocation** | Stable internal entity identifiers with cross-reference index to external IDs (LEI, DUNS, IMO, Tax ID, etc.). Entity IDs must not change after initial assignment except in explicit merge operations. |
| **V4-FR-4: Source Provenance** | Every contributed record is preserved with full lineage: source identifier, ingestion timestamp, match confidence, and original payload. |
| **V4-FR-5: Tenant Access Control** | Multi-tenant read/write permissions defining which entity types, fields, and operations each business unit can access. Authority ranking for survivorship decisions. |

#### Phase 2: Knowledge Graph (v4.1)

| Requirement | Description |
|-------------|-------------|
| **V4-FR-6: Multi-Entity-Type Graph** | Support for company, person, vessel, and address entity types within the same knowledge graph, with typed relationship edges (subsidiary_of, beneficial_owner, operates_vessel, registered_at, same_as). |
| **V4-FR-7: Authority-Ranked Survivorship** | Golden record field values determined by source authority rank, completeness, and freshness. Conflicts flagged for review when sources disagree beyond a configurable threshold. |
| **V4-FR-8: External Feed Integration** | Scheduled ETL for authoritative external sources (GLEIF LEI registry, sanctions lists, vessel registries, company house filings). Resolved against the knowledge graph like any other source. |
| **V4-FR-9: Graph Traversal API** | Query endpoint for walking the knowledge graph from an entity — following relationship edges with configurable depth, direction, and edge-type filters. |

#### Phase 3: Continuous Operation (v4.2)

| Requirement | Description |
|-------------|-------------|
| **V4-FR-10: Entity Subscriptions** | Business units subscribe to entity change events (golden record updates, new relationships, sanctions flag changes) via webhooks or event bus. |
| **V4-FR-11: Streaming Ingest** | Kafka/CDC connector for real-time record ingestion in addition to REST and batch modes. |
| **V4-FR-12: Audit Trail** | Immutable log of every resolution decision — match/no-match verdicts, golden record field changes, merge operations, and human overrides — with full source provenance. |
| **V4-FR-13: Batch Backfill** | When a new business unit onboards, its historical data is bulk-ingested via `ConfigurableERPipeline` and spliced into the live knowledge graph without downtime. Target: 1M records within 1 hour. |

#### Phase 4: Intelligence Layer (v4.3)

| Requirement | Description |
|-------------|-------------|
| **V4-FR-14: AI Data Steward** | MCP-based workflow where an AI agent acts as a data steward — submitting records, reviewing ambiguous matches, querying relationships, and monitoring entity changes through natural language. |
| **V4-FR-15: Automated Anomaly Detection** | Alerts for new sanctions matches, ownership structure changes, dormant entities becoming active, and data quality degradation. |
| **V4-FR-16: Network Analysis** | Hidden relationship discovery through multi-hop graph analysis — identifying shared beneficial owners, circular ownership, and sanctions-adjacent entities. |

#### Non-Functional Requirements (Centralized Service)

| Requirement | Target |
|-------------|--------|
| **NFR-8: Synchronous resolution latency** | < 500ms p95 |
| **NFR-9: Batch backfill throughput** | 1M records/hour |
| **NFR-10: Entity ID stability** | < 0.1% reassignment rate |
| **NFR-11: Subscription delivery latency** | < 60 seconds from resolution to notification |
| **NFR-12: Audit coverage** | 100% of resolution decisions logged |
| **NFR-13: Multi-tenancy isolation** | Tenant data access enforced at query and API layer |

### Other Future Investigation Areas

Shipped since this list was written and therefore removed from it: shard-parallel
blocking, `AddressERPipeline` as a first-class class, graph-context / collective
matching, richer evaluator reports and public benchmark datasets, and the MCP
canonical `options` migration. See Shipped Scope above.

Still open:

- ONNX Runtime GPU provider promotion (CoreML on Apple Silicon, CUDA/TensorRT on Linux) after parity and quality gates pass
- Richer GraphRAG and document-entity extraction flows
- Geospatial-temporal validation as Fellegi-Sunter evidence rather than a binary pre-filter
- Graph-neural matching (the current graph-embedding blocker is an unweighted-DeepWalk prototype; GraphSAGE / ArangoGraphML is the scale path)
- Stricter anti-merge constraints and policy controls (minimum-evidence floor, conflicting-hard-identifier veto)
- **End-to-end streaming candidate generation**: chunked blocking and a streaming `iter_candidates()` path have shipped (FR-7); what remains is consuming candidates without materialising them client-side before deduplication, which is required before any throughput claim above ~67k records.
- **Active learning**: uncertainty-sampled pair selection for labelling, so a useful model needs tens rather than thousands of labels
- **Embeddings as a scoring feature**, not blocking-only
- Retraction in incremental maintenance, so a record *update* can split a cluster rather than only a human verdict

> The original library enhancement plan (Phases 0–4) is complete and archived at
> [docs/archive/completed-work/LIBRARY_ENHANCEMENT_PLAN.md](archive/completed-work/LIBRARY_ENHANCEMENT_PLAN.md);
> its still-open follow-ups are captured in this section.

### Roadmap Principle

Future additions should extend the current pipeline, CLI, MCP, and reporting surfaces rather than creating parallel systems. The centralized service specifically builds on `IncrementalResolver`, `ConfigurableERPipeline`, the MCP server, and the advisor tools rather than introducing parallel resolution paths.

---

## Success Criteria for the Current Product

The current product is successful when users can:

- configure and run a pipeline with automatic backend selection
- inspect clusters and trust signals
- export portable result artifacts
- benchmark blocking strategies with repeatable inputs
- optionally use MCP and LLM-assisted review without changing the core deployment path
- optionally leverage GAE for enterprise-scale clustering workloads

---

## Related Docs

- [README](../README.md)
- [Centralized ER Service Design](architecture/CENTRALIZED_ER_SERVICE.md)
- [System Design](architecture/DESIGN.md)
- [Quick Start Guide](guides/QUICK_START.md)
- [API Reference](api/API_REFERENCE.md)
- [Blocking Benchmarks](development/BLOCKING_BENCHMARKS.md)
- [Release Checklist](development/RELEASE_CHECKLIST.md)
- [GAE Enhancement Path](development/GAE_ENHANCEMENT_PATH.md)

---

**Last Updated:** October 21, 2026
