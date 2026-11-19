# State-of-the-Art and Competitive Scorecard

**Evaluated:** September 29, 2026  
**Release baseline:** `v3.10.1`  
**Overall competitive score:** **6.3/10 — differentiated mid-tier contender**

The project now has one of the broadest **open, graph-native ER toolkits** rather
than merely hosting a generic matcher in a graph database. Its overall score is
held below the leaders because this scorecard counts only shipped, wired
behavior: Splink remains ahead in probabilistic *tooling* — interactive model
diagnostics and proven scale — though the modeling itself is now near parity;
Zingg leads in learned blocking and active learning; and Senzing/AWS/commercial
MDM platforms lead in entity-centric operation, scale, and governance.

## Capability scorecard

Scores use a 0–10 scale and compare usable, verified capability rather than
roadmap intent.

| Capability | Weight | Score | Position | Assessment |
|---|---:|---:|---|---|
| Probabilistic modeling / EM / TF | 9% | **8** | Near parity with Splink on modeling | Binary and categorical multi-level EM, posterior scoring, null semantics, TF adjustment, config-hashed persistence, bands inferred from the score distribution, an explicit and recorded reference population for `u`, and degenerate-fit detection on both estimation paths are shipped and benchmarked. FS loses to weighted scoring on text and wins on structured records via comparison levels — the binary model collapses there and is now flagged as unfit. FS's measured advantage is calibration: it holds at the shipped threshold where the weighted score does not. Splink still leads on interactive diagnostics and proven scale |
| Blocking breadth and ANN | 8% | **8** | Leader in breadth | Nine exported strategies include native vector ANN and graph embeddings; six are selectable from pipeline config and four are library-only, now stated as such. Hybrid blocking no longer uses near-exact PHRASE retrieval. Rules are not learned |
| Active learning | 5% | **5** | Behind Zingg | Verdicts mutate edges/clusters and tune LLM thresholds, but there is no uncertainty-sampled iterative matcher or blocker training loop |
| Threshold tuning | 6% | **7** | Partial parity | Supervised selection and guarded unsupervised selection are wired, and comparison bands are placed automatically per field by trough detection, matching label-tuned placement without labels; the UI still lacks a labelled precision/recall/F1 operating curve, and selection correctly declines on unimodal product scores |
| Cluster QA and repair | 6% | **6** | Partial parity | B-cubed, coherence/bridge analysis, suspect clusters, and repair operations exist; the graph-metric and policy suite is narrower than leaders |
| Steward Workbench | 7% | **6** | OSS parity; behind MDM | Merge/split/remove, batch verdicts, audit, profiling, thresholds, and survivorship exist; workflow assignment, RBAC, and tenancy do not |
| Explainability | 5% | **6** | Partial parity | FS waterfall, field evidence, TF effects, and optional graph evidence exist; explanations are not uniformly tied to the production scorer and structured why-not/history is incomplete |
| Incremental resolution | 6% | **6** | Partial parity | Resolve-and-commit and sequence-neutral maintenance are shipped; blocking is narrower than the batch stack and update-driven cluster retraction is open |
| Entity-centric resolution / golden records | 7% | **5** | Behind Senzing/Quantexa | Survivorship and persistent golden records are useful, but the resolution model remains fundamentally record-pairwise |
| Graph-context / collective matching | 7% | **5** | OSS niche leader | Shared-neighbor/path evidence and collective fixpoint resolution are wired but opt-in and not proven at Senzing-class maturity or scale |
| Graph embeddings | 4% | **4** | Prototype | Graph-embedding blocking exists, but the current DeepWalk/count-SVD implementation is bounded and not a production GraphSAGE/GNN path |
| Enterprise clustering | 6% | **7** | Near parity architecture | GAE WCC plus multiple local backends and automatic selection are strong; default clustering remains WCC-centric |
| LLM matcher tier | 5% | **7** | Partial parity, now measured | Uncertain-band verification, retries, budgets, and provider abstraction exist and are benchmarked: a competent frontier model is worth +0.25 accuracy on the ambiguous band for ~$4 per dataset, and the cheap tier equals the expensive one. The shipped 0.55–0.80 band still holds only 8.5% of errors; the provider docs now say the local model does not work here. The pipeline previously dropped the structured `llm:` config block and could not enable masking; both are now wired. Precision is the weak side — every model over-merges |
| Privacy and governance | 5% | **5** | Behind | Masking is now configurable from the pipeline, reviewer attribution is bound to tokens, and exports are confined to a server-owned directory; all remain optional, and there is no default PII policy, erasure propagation, RBAC, or tenant isolation |
| Benchmarks and regression evidence | 6% | **8** | Strong | Two public dataset families covering both task shapes, machine-readable artifacts, B-cubed, quality floors, an oracle-bounded LLM tier, and published negative results. The FEBRL and review-band tables are committed artifacts that reproduce to every digit (seeded training) and are test-checked against the docs; a table once had five of nine rows wrong, and a retraction note names the withdrawn figures. Held at 8: the LLM-judge table is not artifact-backed, and two Leipzig tables predate seeding |
| Candidate-generation scale | 10% | **6** | Behind | BM25 executes in adaptive chunks sized to a wall-clock budget, verified at 66,879 records against the default client timeout it previously exceeded, with a streaming `iter_candidates()` path available; the batch path still materializes pairs client-side, and nothing above ~67k is evidenced against Splink's 100M+ Spark/Athena claims |

**Weighted total:** 6.3/10, normalized across 102% of stated weights.

## Competitive position by product

| Comparator | Where this project wins | Where the comparator leads |
|---|---|---|
| [Splink](https://moj-analytical-services.github.io/splink/) | Graph context, collective and incremental resolution, native vector/graph execution, steward write workflows, MCP/LLM integration, automatic band placement without labels, and published evidence on both linkage and deduplication task shapes | EM/TF controls and diagnostics, interactive model charts, proven million-record laptop and 100M+ Spark/Athena scale |
| [Zingg](https://github.com/zinggAI/zingg) | No-label weighted baseline, graph-native evidence, richer analyst UI, transparent benchmark harness, MCP | Learned blocking, uncertainty-driven active learning, Spark-scale matching; incremental production flow is stronger in Enterprise |
| [Senzing](https://senzing.com/) | Open Python implementation, configurable algorithms, ArangoDB-native deployment and analytics, reproducibility | Real-time entity-centric learning, global identity/relationship intelligence, why/why-not/how explanations, multilingual matching, operational scale into billions |
| AWS Entity Resolution | Deployment control, transparent scoring, graph context, richer explainability and curation, no managed-service lock-in | Managed real-time rules, incremental ML processing at enterprise scale, operational SLAs and AWS data-plane integration |
| Quantexa / Tamr / Reltio-class MDM | Developer accessibility, open algorithms, embeddability, graph/LLM experimentation, cost control | Governance, source connectors, stewardship assignment, survivorship policy, RBAC/multi-tenancy, observability, support and deployment maturity |

## Measured quality position

The benchmarks demonstrate credible but **uneven and shape-dependent** matching
quality. On **linkage** tasks over free text (Leipzig), unsupervised:

- **DBLP-ACM:** pairwise F1 **0.937**, B-cubed F1 **0.977**.
- **DBLP-Scholar:** pairwise F1 **0.840**, B-cubed F1 **0.987** over
  66,879 records.
- **Abt-Buy:** pairwise F1 **0.541**, ahead of the cited Magellan supervised
  baseline but well behind PLM/LLM matchers.
- **Amazon-Google:** pairwise F1 **0.488**, approximately level with the cited
  Magellan supervised baseline and behind deep/PLM approaches.

On **deduplication** tasks over structured person records (FEBRL), unsupervised:

- **febrl1** (1,000 records): Fellegi–Sunter pairwise F1 **1.000**, B-cubed
  **1.000**, against weighted similarity's 0.998 / 0.999.
- **febrl3** (5,000 records, clusters of 1–6 including 835 singletons):
  Fellegi–Sunter pairwise F1 **0.9954**, B-cubed **0.9989**, against weighted
  similarity's 0.9936 / 0.9963. Close at the best threshold — the decisive gap is
  at the shipped default, **0.9950 against 0.547**, because FS posteriors are
  calibrated and a uniform weighted average over ten corrupted fields is not. The
  result holds with the identifier field dropped (0.980 vs 0.443 at that default),
  so it is not an artifact of one giveaway column.
- Both figures are from FS with **comparison levels**. The binary model collapses
  on these two datasets to an unfit solution and is now flagged as such. An
  earlier version of this section cited the binary row at 0.9995; that number was
  wrong and has been withdrawn.

The honest conclusion has changed since August 6, and in the project's favour.
The earlier version of this section stated that "the current FS implementation is
also not yet the answer", citing 0.868 / 0.117 / 0.127 on the text datasets, and
named learned multi-level categories as the binding improvement. Those categories
have since been built, benchmarked, and — on text — found to close most of the
gap without crossing it. The larger finding came from adding a second task shape:

**Neither scoring method is the answer; the data shape decides, and it is
knowable in advance.** Weighted similarity wins on free text, Fellegi–Sunter wins
on structured multi-field records (decisively at the shipped threshold, and
roughly level at the best swept one), and the deciding variable is the
spread in per-field chance agreement — the sum of each field's squared value
frequencies — which requires no labels to compute. Publishing a rule for choosing
a matcher, rather than a single recommended matcher, is a position few
comparators state at all.

Two caveats hold this short of a SOTA claim. The project is still not a SOTA
product matcher on noisy e-commerce text. And neither FS variant is uniformly
better: binary FS edges out multi-level on the small, clean febrl1 set (1.000
against 0.987) but collapses to an unfit model on both febrl3 sets, where only
comparison levels fit. The library flags the collapse but cannot yet
auto-select between the two.

## SOTA claims the project can defend

1. **Unusually integrated graph-native OSS ER.** Candidate generation, match
   evidence, collective refinement, clustering, persistence, and analytics can
   run in one ArangoDB-centered system.
2. **Strong open-source steward workflow.** Most OSS ER libraries stop at model
   diagnostics or exported clusters; this project supports binding cluster
   edits, audit, golden-record survivorship, profiling, and threshold tuning.
3. **First-class agent interface.** The 17-tool MCP surface supports
   authentication, model-derived explanations, and budgeted/masked LLM
   verification.
4. **Unusually honest quality evidence.** The benchmark publishes poor as well
   as strong results, reports blocking recall and entity-level metrics, and
   documents its own failures and reversals: the scaling failure and its fix, a
   statistically superior matcher losing to a simpler one on text, and a
   theoretically correct parameter change that had to be rejected because it
   measured worse at the shipped operating point.
5. **A published rule for choosing a matcher, not just a matcher.** The
   condition under which the probabilistic path beats the weighted one is stated
   as a measurable property of the data and validated on both task shapes.
   Comparators generally ship a default and leave the question unaddressed.

## Claims the project should not make yet

- Overall best-in-class or SOTA matching accuracy, particularly on noisy
  e-commerce text.
- Splink-equivalent probabilistic **tooling**. The modeling is now comparable —
  categorical multi-level EM is trained, persisted, wired, and benchmarked — but
  Splink's interactive diagnostics and its demonstrated scale are not matched.
- Million-record or real-time candidate-generation scale. Adaptive chunking is
  verified to 66,879 records; beyond that there is no evidence, and the batch
  path still materializes pairs client-side.
- Automatic selection between scoring methods or between binary and multi-level
  comparisons. The *rule* for choosing is now measured and documented, but the
  library does not yet apply it for the user.
- That a local model is adequate for the verification tier. `llama3.1:8b`
  answered "match" for 88% of ambiguous pairs when 38% were matches — no evidence
  it beats the plain score threshold. Local inference remains the right answer
  where data cannot leave the network, but only after verifying on your own data.
- That the shipped 0.55–0.80 verification band is suitable as a default. On the
  one dataset measured it contains 8.5% of the matcher's errors; a wider band
  reaches 61%. The band should be placed from the error distribution, not
  assumed.
- Enterprise MDM readiness before RBAC, tenant isolation, immutable audit,
  deployment packaging, telemetry, and lifecycle operations exist.
- Production GraphSAGE/GNN matching; current graph embeddings are a bounded
  DeepWalk/count-SVD prototype.

## Highest-leverage moves

The August 6 list led with finishing multi-level Fellegi–Sunter and streaming
candidate generation. Both are done, which is what moved this scorecard from 5.8
to 6.3. The remaining list is reordered accordingly.

1. **Auto-select the scoring configuration.** The rule is measured — per-field
   chance-agreement spread predicts whether Fellegi–Sunter or weighted
   similarity wins, and on structured data comparison levels are the
   configuration that reliably fits (the binary model collapses). Profile the
   collection and recommend (or default to) the right configuration instead of
   leaving it to the user to read a benchmark document.
2. **Close the active-learning loop:** select uncertain/diverse pairs, train
   from adjudications, compare lift per label, and expose the loop in the
   Workbench. This is the largest remaining gap against Zingg.
3. **Push candidate generation past 67k:** consume the streaming iterator in the
   batch path so pairs are not materialised client-side, then add memory and
   throughput gates at 100k–1M records.
4. **Productize operations and governance:** container, telemetry, RBAC,
   tenant/source policies, immutable audit, and erasure propagation. This is now
   the single largest weighted drag on the score.
5. **Broaden automatic cluster repair:** build on the existing coherence and
   bridge-edge repair path with hard-identifier vetoes and benchmarked policies.
6. **Derive the verification band from the error distribution.** The cascade is
   now benchmarked; what it showed is that the fixed default band is nearly
   inert. Place it the way thresholds are already placed — from the data — and
   report what share of errors a band contains before routing anything to it.
7. **Express hard identifiers in scoring.** There is no way to say "two records
   grounding to different canonical IDs cannot merge." That conflicting-identifier
   veto is worth more than any positive grounding bonus, and it is the missing
   piece for ontology-grounded resolution.
8. **Gate prose claims.** A README quality claim and a benchmark table were both
   wrong for weeks because no gate reads documentation. Numbers in docs should be
   checked against the artifacts they cite; the scorecards now carry a staleness
   check for the same reason.
9. **Add interactive model diagnostics** to close the remaining Splink gap now
   that the underlying modeling is comparable.

## Sources and comparison boundary

Project evidence:

- [Public benchmark results](BENCHMARKS.md)
- [Current shipped and open scope](PRD.md)
- [June 2026 gap analysis](PROJECT_REVIEW_2026-06.md)

Competitor capabilities were checked against current public material:

- [Splink overview](https://moj-analytical-services.github.io/splink/) and
  [Cluster Studio](https://moj-analytical-services.github.io/splink/charts/cluster_studio_dashboard.html)
- [Zingg repository and feature summary](https://github.com/zinggAI/zingg)
- [Senzing explainability](https://senzing.com/explainability/)
- [AWS Entity Resolution workflows](https://docs.aws.amazon.com/entityresolution/latest/userguide/create-matching-workflow.html),
  [incremental ML announcement](https://aws.amazon.com/about-aws/whats-new/2026/05/aws-entity-resolution-ml/),
  and [advanced real-time matching](https://aws.amazon.com/about-aws/whats-new/2026/07/aws-entity-resolution/)

Commercial claims are not treated as independently reproduced benchmarks. This
scorecard compares documented capability and this project's measured evidence;
it is not a controlled head-to-head product evaluation.
