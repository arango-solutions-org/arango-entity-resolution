# ArangoDB Entity Resolution

A production-ready entity resolution system for ArangoDB that identifies and links records referring to the same real-world entity across multiple data sources. Uses record blocking, graph algorithms, and AI to scale from thousands to millions of records.

**Version 3.10.0** | [Changelog](CHANGELOG.md) | [PyPI](https://pypi.org/project/arango-entity-resolution/)

## Installation

```bash
pip install arango-entity-resolution

# With optional features
pip install "arango-entity-resolution[mcp]"       # MCP server for AI agents
pip install "arango-entity-resolution[llm]"       # LLM match verification
pip install "arango-entity-resolution[ml]"        # Vector embeddings (sentence-transformers)
pip install "arango-entity-resolution[ui]"        # Steward Workbench web UI
pip install "arango-entity-resolution[onnx]"      # ONNX Runtime for faster CPU embeddings
pip install "arango-entity-resolution[sparse]"    # scipy clustering backend for very large graphs
pip install "arango-entity-resolution[mcp,llm,ml,ui,onnx,sparse]"  # Everything
```

## Quick Start

### CLI

```bash
# Run a pipeline from YAML config
arango-er run --config config/er_config.example.yaml

# Inspect clusters
arango-er status --collection companies
arango-er clusters --collection companies --limit 20

# Export results
arango-er export --collection companies --output-dir ./exports
```

### Python

```python
from entity_resolution import ConfigurableERPipeline, ERPipelineConfig

config = ERPipelineConfig.from_yaml("config/er_config.example.yaml")
pipeline = ConfigurableERPipeline(config=config, db=db)
results = pipeline.run()

print(f"Candidates: {results['blocking']['candidate_pairs']}")
print(f"Clusters:   {results['clustering']['clusters_found']}")
```

### MCP Server (AI Agent Integration)

```bash
# stdio for Claude Desktop / Cursor
arango-er-mcp

# SSE for remote clients
arango-er-mcp --transport sse --port 8080
```

Exposes 17 tools and 2 resources for any MCP-compatible AI agent. See [MCP Tools](#mcp-tools) below for the full inventory.

## How It Works

Entity resolution runs as a multi-stage pipeline, each stage narrowing candidates and increasing precision:

```
Data Sources → Blocking → Similarity → Clustering → Golden Records
                 ↓            ↓            ↓
              99%+ pair    Field-level   Graph-based
              reduction    scoring       grouping
```

**Stage 1 — Record Blocking** reduces O(n²) comparisons to O(n) using ArangoSearch full-text indexes, phonetic matching, n-gram overlap, vector similarity, and geographic proximity.

**Stage 2 — Similarity Scoring** computes field-level similarity (Jaro-Winkler, Levenshtein, Jaccard) with configurable weights and a Fellegi-Sunter probabilistic framework.

**Stage 3 — Clustering** groups matched pairs into entity clusters using Weakly Connected Components with pluggable backends (Union-Find, DFS, scipy sparse, AQL graph, or GAE enterprise).

**Stage 4 — Golden Record Generation** fuses cluster members into authoritative master records with source ranking, conflict resolution, and full audit trail.

Optional AI stages can be inserted into the pipeline:

- **LLM Match Verification** — auto-calls an LLM for ambiguous pairs in a configurable confidence band (0.55–0.80 by default; [measured results](docs/BENCHMARKS.md#llm-verification-of-the-ambiguous-band-measured))
- **GraphRAG Entity Extraction** — extracts entities from unstructured documents and links them to the graph
- **Geospatial-Temporal Validation** — confirms or rejects matches based on location and time feasibility

## Key Features

### Blocking Strategies

Six strategies can be selected from pipeline configuration with
`blocking.strategy`; four more are Python classes you construct yourself.

| Strategy | `blocking.strategy` | Use Case |
|----------|---------------------|----------|
| **Exact / COLLECT** | `exact` | High-precision blocking on email, phone, composite keys |
| **BM25** | `bm25` | Token matching ranked by BM25 over an ArangoSearch view; pair completeness 0.890–1.000 on the four [Leipzig benchmarks](docs/BENCHMARKS.md#summary) |
| **ArangoSearch** | `arangosearch` | Alias of `bm25` |
| **Vector / ANN** | `vector` | Semantic similarity via sentence-transformers embeddings; **requires** ArangoDB 3.12+ with a native `APPROX_NEAR_COSINE` vector index (no brute-force fallback) |
| **LSH** | `lsh` | Locality-sensitive hashing for high-dimensional data |
| **Graph embedding** | `graph_embedding` | node2vec embeddings of an existing relationship graph; needs `blocking.edge_collection`; small/medium graphs |
| **Hybrid** | library only: `HybridBlockingStrategy` | BM25 retrieval re-scored with Levenshtein |
| **Geographic** | library only: `GeographicBlockingStrategy` | Proximity-based blocking with coordinate distance |
| **Graph Traversal** | library only: `GraphTraversalBlockingStrategy` | Shared-identifier network analysis |
| **Shard-Parallel** | library only: `ShardParallelBlockingStrategy` | Optimised for sharded ArangoDB clusters |

### Clustering Backends

The default `backend: auto` selects the best available backend based on edge count, optional dependencies, and whether the ArangoDB Graph Analytics Engine is reachable:

| Backend | Best For | Selection |
|---------|----------|-----------|
| `python_union_find` | General purpose | Default when GAE is unavailable |
| `python_dfs` | Reliable DFS traversal | Explicit only |
| `python_sparse` | Very large dense graphs | Auto-selected above 2M edges when scipy installed |
| `aql_graph` | Server-side processing | Explicit only |
| `gae_wcc` | Enterprise-scale (millions of edges) | Auto-selected when GAE is enabled and reachable |

#### GAE Clustering (Enterprise)

For graphs too large for in-process clustering, the `gae_wcc` backend offloads WCC to the [ArangoDB Graph Analytics Engine](https://docs.arangodb.com/stable/data-science/graph-analytics-engine/) — a dedicated compute cluster. The backend manages the full lifecycle: engine deployment, graph loading, WCC execution, result storage, and cleanup.

```yaml
clustering:
  backend: auto
  gae:
    enabled: true
    deployment_mode: self_managed   # or "amp" for ArangoGraph Managed Platform
    graph_name: companies_similarity_graph
    engine_size: e16
    auto_cleanup: true
    timeout_seconds: 3600
```

Supports both self-managed deployments (JWT auth) and ArangoGraph Managed Platform (oasisctl bearer token).

### Embedding & GPU Support

Embedding generation for vector blocking auto-detects the best available hardware:

| Device | Platform | How to use |
|--------|----------|------------|
| **CUDA** | Linux / Windows with NVIDIA GPU | `device: auto` (auto-detected) or `device: cuda` |
| **MPS** | macOS with Apple Silicon | `device: auto` (auto-detected) or `device: mps` |
| **CPU** | Any platform | `device: cpu` (fallback) |

```yaml
embedding:
  model_name: all-MiniLM-L6-v2
  device: auto              # selects CUDA > MPS > CPU at runtime
  max_batch_size: 256       # OOM safety cap for GPU workloads
  runtime: pytorch          # or onnx for faster CPU inference
```

The ONNX Runtime backend (`pip install "arango-entity-resolution[onnx]"`) provides faster CPU inference and supports export from any sentence-transformers model via `OnnxModelExporter`.

### LLM Match Curation

When similarity scoring produces ambiguous pairs (default 0.55–0.80 confidence), the pipeline can auto-delegate them to an LLM for a match/no-match decision, without manual review.

**Measured, on 200 ambiguous Amazon-Google pairs** ([full results](docs/BENCHMARKS.md#llm-verification-of-the-ambiguous-band-measured)) — the model matters, and not in the direction the provider table suggests:

| Judge | Accuracy on those pairs | Cost / 1,000 pairs |
|---|---|---|
| score threshold alone | 0.565 | — |
| `ollama/llama3.1:8b` (local) | **0.510** | $0 |
| `openrouter/google/gemini-3.8-flash` | **0.810** | ~$2.00 |
| `openrouter/anthropic/claude-opus-5` | **0.820** | ~$11.20 |

Two things follow. A competent model is worth a lot — +0.25 accuracy on exactly the pairs the score cannot settle. And **a small local model is not competent at this**: llama3.1:8b answered "match" for 87% of pairs when 38% were matches, and scored below the threshold it was meant to improve on (not a significant difference, but no evidence it helps). Verify on your own data before trusting a local model here.

Note also what improves: these models raise accuracy by recovering **recall**. All three *over-merge* — precision is their weakest dimension (0.67 and 0.68 for the two that work). If precision is your constraint, this tier is not the fix.

The default 0.55–0.80 band is also narrow. On Amazon-Google it contains only 8.5% of the matcher's errors, so verification there has little to work with; a wider band (0.30–0.95) reaches 61%. Tune it to your score distribution rather than accepting the default.

The verifier works with any provider supported by [litellm](https://docs.litellm.ai/), including fully local models that need no API key:

| Provider | Example model string | API key required |
|----------|---------------------|------------------|
| **Ollama** (local) | `ollama/llama3.1:8b`, `ollama/mistral` | No — but see the measurements above |
| **OpenRouter** | `openrouter/google/gemini-2.0-flash` | `OPENROUTER_API_KEY` |
| **OpenAI** | `openai/gpt-4o` | `OPENAI_API_KEY` |
| **Anthropic** | `anthropic/claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |

```yaml
active_learning:
  enabled: true
  llm:
    provider: ollama                # local LLM, no API key needed
    model: llama3.1:8b
    base_url: http://localhost:11434
    timeout_seconds: 120
    healthcheck_on_start: true      # probe the provider when the pipeline starts
  mask_fields: [ssn, email]         # hash these values before they leave the network
  low_threshold: 0.55              # below this → auto no_match
  high_threshold: 0.80             # above this → auto match
  refresh_every: 100               # re-optimize thresholds every N verifications
```

**What leaves the network.** By default the provider receives every field of both
records except those starting with `_`. Fields listed in `mask_fields` are sent
as a stable hash instead, so the model can still see that two values are equal
but never sees the values. Masking costs verdict quality on anything fuzzy, so
reserve it for identifiers. A local `ollama/` model sends nothing off the machine.
`fallback_provider` is not implemented: the config still parses it, but a failed
call is not retried against another provider, and setting it raises a `UserWarning`.

The LLM receives both records, the overall similarity score, and field-level scores, and returns a structured JSON verdict with decision, confidence, and reasoning. When the LLM overrides a score, the system synthesises a new score that pushes the pair above or below the thresholds so downstream clustering reflects the decision.

**Active Learning** wraps the verifier in a feedback loop (`AdaptiveLLMVerifier`). Every verdict is persisted to a feedback store in ArangoDB. Human corrections can be recorded via `record_human_correction()`, and the system periodically re-optimizes the low/high thresholds based on accumulated feedback — reducing LLM calls over time as the thresholds converge on the data distribution.

### MCP Tools

The MCP server exposes 17 tools organized into two groups — core ER operations and an advisory layer that helps an AI agent decide *how* to resolve before running the pipeline.

#### Core ER Tools

| Tool | What it does |
|------|-------------|
| `list_collections` | Discover all document/edge collections with counts |
| `find_duplicates` | Run the full blocking → similarity → clustering pipeline |
| `pipeline_status` | Document count, edge stats, cluster count for a collection |
| `resolve_entity` | Find existing records matching a given record (read-only) |
| `resolve_entity_cross_collection` | Link entities across two collections with field mapping |
| `explain_match` | Field-level similarity breakdown between two records |
| `get_clusters` | Return entity clusters with quality metadata (density, similarity stats) |
| `merge_entities` | Preview a golden record merge ("most_complete", "newest", or "first") |
| `resolve_and_commit` | Resolve one record into the graph: link it to its matches and re-cluster only the affected component (writes, unlike `resolve_entity`) |

#### Advisor Tools

An AI agent can use the advisor tools to analyze a dataset, choose the right strategy (including pre-ingest canonicalization vs post-ingest matching), tune weights, and simulate pipeline variants — all before executing anything.

| Tool | What it does |
|------|-------------|
| `profile_dataset` | Profile fields: null rates, distinct counts, heavy hitters, duplicate/hub risk |
| `profile_fields` | Profile fields (semantic type, completeness, cardinality, sample values); optionally emit a recommended similarity config |
| `recommend_resolution_strategy` | Rank strategy families from a profile and objective constraints |
| `recommend_blocking_candidates` | Rank single-field and composite blocking keys by fit score |
| `evaluate_blocking_plan` | Estimate pair volume, block-size distribution, and risk flags |
| `estimate_feature_weights` | Estimate field weights and threshold from labeled pairs |
| `simulate_pipeline_variants` | Compare multiple pipeline configs (runtime, memory, precision, recall) |
| `export_recommended_config` | Export a recommendation as deployable YAML/JSON with SHA256 hash |

The `recommend_resolution_strategy` tool evaluates five strategy families and ranks them against your data profile and objectives:

| Strategy | When it fits |
|----------|-------------|
| `hybrid_block_then_weighted_match` | General purpose — balanced precision, recall, throughput |
| `pre_ingest_canonicalize_then_match` | Canonicalize addresses/names *before* loading to reduce variant noise |
| `deterministic_rules_then_review` | Auditable rule-based matching with human review |
| `embedding_first_nearest_neighbor` | Semantic recall on noisy text (requires embeddings) |
| `graph_first_collective_resolution` | Multi-hop graph reasoning for complex relationship networks |

For address resolution specifically, there is a dedicated `AddressERPipeline` that handles street/city/state/postal normalization, custom analyzers, and address-specific blocking — usable standalone or as part of the recommended strategy.

#### Resources

| URI | Returns |
|-----|---------|
| `arango://collections/{collection}/summary` | Document count, inferred schema, sample documents |
| `arango://clusters/{collection}/{key}` | Full cluster details with all member documents |

### Other Integrations
- **Canonical-hub resolution** — `entity_resolution.canonical_hub` resolves one record to an existing canonical entity, or abstains or refuses with a stated reason, under an explicit precision and scope policy (read-only; native vector index only)
- **ONNX Runtime** — faster CPU inference for embedding workloads
- **Incremental Resolver** — real-time single-record matching without batch re-run

### Web UI (Optional)

A browser-based interface for analysts and data stewards who need to interact with entity resolution results without writing code.

```bash
pip install "arango-entity-resolution[ui]"
arango-er ui --serve-port 8787 --open    # --port is the ArangoDB port
```

| Screen | What it does |
|--------|-------------|
| **Dashboard** | Operational overview — document counts, cluster stats, pending reviews, pipeline history |
| **Review Queue** | Side-by-side record comparison with field-level similarity scores, LLM reasoning display, and one-click human verdicts (keyboard shortcuts: M/N/S) |
| **Cluster Browser** | Paginated cluster list with quality scores, drill-down to interactive graph visualization (React Flow) |
| **Pipeline Runner** | Configure and execute pipelines with real-time WebSocket progress tracking |
| **Config Builder** | Visual pipeline configuration with advisor tool integration (strategy recommendations, weight estimation, variant simulation) |
| **Entity Resolver** | Interactive single-record resolution for testing |
| **Golden Records** | Field-level provenance, source ranking, and conflict resolution |

The UI calls the same Python services as the CLI and MCP server — no new resolution logic. See [UI Design](docs/architecture/ENTITY_RESOLUTION_UI.md) for architecture details.

## Configuration

Pipelines are driven by YAML (or JSON) configuration:

```yaml
entity_resolution:
  entity_type: company
  collection_name: companies

  blocking:
    strategy: exact
    fields:
      - field: state
      - field: city

  similarity:
    algorithm: jaro_winkler
    threshold: 0.80
    field_weights:
      name: 0.40
      address: 0.30
      phone: 0.20
      email: 0.10

  clustering:
    backend: auto          # picks best available backend
    min_cluster_size: 2
    store_results: true
```

See [`config/er_config.example.yaml`](config/er_config.example.yaml) for a complete example with all options.

## Why ArangoDB?

Entity resolution requires document storage, graph traversal, full-text search, and vector similarity — typically needing 3–4 separate systems. ArangoDB handles all of these natively:

- **Documents** — flexible schema for heterogeneous source records
- **Graphs** — native WCC, traversals, and relationship modeling
- **ArangoSearch** — integrated full-text search with phonetic, n-gram, and BM25 analyzers
- **Vectors** — embedding storage with native vector-index ANN search (`APPROX_NEAR_COSINE`); vector blocking requires ArangoDB 3.12+ (no brute-force fallback)

This eliminates the integration overhead of Elasticsearch + Neo4j + PostgreSQL stacks and keeps blocking, similarity, clustering, and golden records in a single transactional system.

## Benchmark Results

Measured on standard public benchmarks, unsupervised — no labelled training
pairs. **Linkage** tasks (match source A against source B), Leipzig DBS group:

| Dataset | Records | Pair completeness | Pairwise F1 | B-cubed F1 | Magellan (supervised) |
|---------|---------|------------------|-------------|------------|----------------------|
| DBLP-ACM | 4.9K | 1.000 | 0.937 | 0.977 | ~0.98 |
| DBLP-Scholar | 66.9K | 0.996 | 0.840 | 0.987 | ~0.89 |
| Abt-Buy | 2.2K | 0.957 | 0.541 | 0.779 | ~0.43 |
| Amazon-Google | 4.6K | 0.890 | 0.488 | 0.852 | ~0.49 |

**Deduplication** tasks (match a collection against itself), FEBRL person
records — ten structured fields rather than two free-text ones:

| Dataset | Records | Scoring | Pairwise F1 | F1 at default 0.8 | B-cubed F1 |
|---------|---------|---------|-------------|-------------------|------------|
| febrl1 | 1.0K | weighted | 0.998 | 0.759 | 0.999 |
| febrl1 | 1.0K | **Fellegi-Sunter (binary)** | **1.000** | **0.998** | **1.000** |
| febrl3 | 5.0K | weighted | 0.9936 | 0.547 | 0.9963 |
| febrl3 | 5.0K | **Fellegi-Sunter (multi-level)** | **0.9954** | **0.9950** | **0.9989** |

The two tables disagree about which scoring method to use, and that is the
finding: weighted similarity wins on free text, Fellegi-Sunter wins on
structured multi-field records. Which one applies is predictable before you
run anything, from how much your fields differ in how often they agree by
chance — no labels required.

Note the middle column. On structured records the two methods are close at their
best threshold, and the real difference shows at the shipped default: 0.9950
against 0.547 on febrl3. Fellegi-Sunter's posteriors are calibrated, so it does
not require you to find the operating point first.

Binary Fellegi-Sunter fits febrl1 but collapses on febrl3, which is why the
febrl3 row uses comparison levels; the full nine-row comparison is in
[BENCHMARKS.md](docs/BENCHMARKS.md#structured-multi-field-records-where-fellegi-sunter-wins).
Reproduce with `python scripts/run_er_benchmarks.py --dataset all` (linkage), and
for the dedup rows `--dataset febrl1 --scoring-method fellegi_sunter` and
`--dataset febrl3 --scoring-method fellegi_sunter --comparison-levels auto`. Full method, per-dataset detail, scale limits, and
comparison caveats are in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Performance

Blocking turns the quadratic comparison into a short candidate list. Measured on an
Apple Silicon laptop against single-node ArangoDB 3.12 (detail and method in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md)):

| Dataset | Records | Possible pairs | Candidate pairs | Blocking | Scoring |
|---------|---------|----------------|-----------------|----------|---------|
| Abt-Buy | 2,173 | 1.2M | 10,895 | 1.7s | 0.2s |
| Amazon-Google | 4,589 | 4.4M | 25,808 | 16.2s | 1.0s |
| DBLP-ACM | 4,910 | 6.0M | 32,278 | 7.1s | 0.3s |
| DBLP-Scholar | 66,879 | 168M | 68,057 | 1160s | 0.8s |

Blocking time grows faster than the data: DBLP-Scholar has ~13x the records of
DBLP-ACM and takes ~140x as long. Throughput beyond these sizes has not been
measured.

Clustering backends scale from Union-Find (general purpose) through scipy sparse (large dense graphs) to GAE enterprise (millions of edges on dedicated compute).

## Project Structure

```
src/entity_resolution/
├── core/           Entity resolver, configurable pipeline, incremental resolver, orchestrator
├── services/       Blocking, similarity, clustering, embedding, export services
│   └── clustering_backends/   Union-Find, DFS, Sparse, AQL, GAE
├── strategies/     Exact, BM25, vector, geographic, LSH, shard-parallel blocking
├── mcp/            MCP server (17 tools, 2 resources)
├── reasoning/      LLM verifier, GraphRAG, feedback/active learning
├── enrichments/    Type constraints, context resolver, acronym handler, provenance sweeper
├── etl/            Canonical resolver, normalizers, arangoimport integration
├── similarity/     Weighted field similarity, geospatial/temporal validators
├── config/         YAML/JSON pipeline configuration
└── utils/          Database, logging, validation, constants
```

## Documentation

| Resource | Description |
|----------|-------------|
| [Documentation Index](docs/README.md) | Complete navigation |
| [Quick Start](docs/guides/QUICK_START.md) | Get started in 5 minutes |
| [API Reference](docs/api/API_REFERENCE.md) | CLI, MCP, Python, and config reference |
| [Advanced Modules Guide](docs/guides/ADVANCED_MODULES_GUIDE.md) | Orchestrator, GraphRAG, geospatial, feedback, ETL |
| [Performance Guide](docs/guides/PERFORMANCE_GUIDE.md) | Tuning and scaling |
| [Platform Setup](docs/guides/PLATFORM_SETUP.md) | ArangoDB, Docker, and provider setup |
| [Provider Matrix](docs/guides/PROVIDER_MATRIX.md) | LLM and embedding provider comparison |
| [Migration Guide](docs/guides/MIGRATION_GUIDE_V3.md) | Upgrading from v1.x or v2.x |
| [Benchmarks](docs/BENCHMARKS.md) | Measured results on public ER benchmarks |
| [PRD](docs/PRD.md) | Product requirements and roadmap |

## Examples

| Example | Description |
|---------|-------------|
| [`yaml_config_pipeline.py`](examples/yaml_config_pipeline.py) | Config-driven end-to-end pipeline |
| [`clustering_backend_comparison.py`](examples/clustering_backend_comparison.py) | Compare all clustering backends |
| [`multi_strategy_orchestration.py`](examples/multi_strategy_orchestration.py) | Union/intersection blocking modes |
| [`onnx_runtime_embedding.py`](examples/onnx_runtime_embedding.py) | ONNX export and fast inference |
| [`incremental_resolution.py`](examples/incremental_resolution.py) | Real-time streaming resolution |
| [`ollama_llm_verification.py`](examples/ollama_llm_verification.py) | Local LLM match verification |
| [`vector_blocking_example.py`](examples/vector_blocking_example.py) | Semantic similarity blocking |

## Development

```bash
# Install with dev + test deps
pip install -e ".[dev,test,mcp,llm,ml]"

# Or use the Makefile
make install-all
make test          # all tests
make test-unit     # unit tests only
make lint          # flake8
make format        # black
make typecheck     # mypy
make build         # sdist + wheel
```

Pre-commit hooks validate syntax, check for hardcoded credentials, and verify critical imports. Pre-push hooks run the full test suite against a temporary ArangoDB instance.

## Contributing

1. Review the [PRD](docs/PRD.md) and [Documentation Index](docs/README.md)
2. Install git hooks: `./scripts/setup-git-hooks.sh`
3. Follow Python 3.10+ with type hints, DRY principles, and comprehensive docstrings
4. Run `make test` before submitting PRs
5. Update documentation for any user-facing changes

## License

[Apache License 2.0](LICENSE)
