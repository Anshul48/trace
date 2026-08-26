# Evaluation Protocol

> **Status:** Draft broad-stroke protocol. It defines the proof boundary to be
> implemented and reviewed; it is not a completed benchmark result.

## 1. Purpose

Evaluation distinguishes engineering regression evidence from externally
credible capability, scale, and operational evidence. It prevents a local
fixture, smoke run, mock provider, or visualized graph from becoming a broad
quality claim.

## 2. Evidence lanes

| Lane | Purpose | Certification role |
| --- | --- | --- |
| Internal regression | Detect regressions in known Beta behavior. | Necessary, never sufficient. |
| Public benchmark | Compare reproducibly on real downloadable data. | External retrieval evidence. |
| Held-out downstream | Test realistic Reflex/Entorhinal task classes. | Product-fit evidence. |
| Recovery/fault | Test crash, replay, invalid build, and rollback. | Durability evidence. |
| Scale/load | Measure resource, latency, and cost at 100K then 1M. | Operational evidence. |

## 3. Dataset requirements

Every certification dataset needs a record containing its source, license,
version, content hash, expected local location, transform identity,
segmentation mapping, and known limitations. Required data must be present;
missing data fails the run.

Development fixtures and synthetic data may be used for deterministic fault
injection or quick tests, but never as a hidden replacement for a required
real-data lane.

## 4. Release-run behavior

The future release runner should:

1. resolve the exact manifest,
2. verify data and configuration identity,
3. assert that prohibited fallbacks are disabled,
4. run fixed baselines and candidate configurations,
5. emit query-level and aggregate evidence,
6. record cold/warm timing, resources, and failures,
7. refuse certification when a required stage is unavailable.

## 5. Required result metadata

- dataset and judgment-pack hashes,
- code revision and dirty-worktree status,
- environment and hardware summary,
- configuration, embedding, provider/model identifiers,
- active projection/release identity,
- baseline and ablation identity,
- query-class breakdown,
- raw failure and exclusion counts.

## 6. Gate structure

The five release-quality gates are:

1. durable headless memory,
2. self-organization correctness,
3. accurate retrieval,
4. bounded retrieval latency and resources,
5. real-corpus scale/recovery proof.

The initial scale gate is 100K real source atoms. A 1M pilot is planned only
after the 100K evidence has been reviewed.

## 7. Evaluation hierarchy and claim boundary

The evaluator reports separate lanes rather than collapsing them into one
number:

| Lane | Question answered | Does not establish |
| --- | --- | --- |
| Unit/integration | Does the implementation satisfy a local contract? | External retrieval quality or scale. |
| Frozen internal fixture | Did known behavior regress relative to a fixed baseline? | Broad-domain superiority. |
| Public benchmark | Does it improve under a reproducible external protocol? | Downstream task fit or production operations. |
| Held-out downstream | Does it help realistic consumer queries with evidence? | General public benchmark rank. |
| Fault/recovery | Does source truth and active state survive failures? | Retrieval superiority. |
| Real 100K load | Is the architecture bounded and recoverable at the first target scale? | 1M or distributed readiness. |

Every report states its lane, applicable claim level from the charter, and
unmet requirements.

## 8. Dataset admission checklist

Before a dataset enters a release or scale manifest, confirm:

1. Official source and maintainable acquisition path.
2. License and redistribution constraints.
3. Version, archive/content checksum, and download timestamp.
4. Corpus/query/judgment relationship and query identifiers.
5. Expected source-document and source-atom counts after declared transforms.
6. Segmentation and source-anchor mapping method.
7. Privacy, PII, retention, and access constraints.
8. Whether judgments support the target metric and query class.
9. Whether the dataset is a development fixture, a public certification lane,
   a private held-out lane, or scale-only material.
10. Explicit absence of synthetic or sample fallback authority.

## 9. Release-manifest outline

~~~yaml
manifest_version: "1.x"
run_id: generated-at-run-time
purpose: regression|public|held_out|fault|scale
certification: false
datasets:
  - dataset_record_id: dataset-id@version
    archive_sha256: required
    transform_id: required
    query_pack_id: required
    judgment_pack_id: required-or-not-applicable
systems:
  - system: trace-lite|trace|baseline
    code_revision: required
    configuration_hash: required
    model_fingerprints: []
retrieval:
  profiles: []
  required_channels: []
  prohibited_fallbacks:
    - mock_llm
    - synthetic_dataset
    - force_flat_search
    - missing_judgments
environment:
  hardware_capture: required
  warmup_policy: explicit
  concurrency: explicit
outputs:
  query_level_results: required
  aggregate_metrics: required
  error_report: required
  evidence_bundle_sample: required
~~~

The actual schema should be machine-validated before the runner begins work.

## 10. Query-class protocol

Use mutually understood labels and report each separately:

| Query class | Primary evidence need | Typical retrieval path | Key failure to expose |
| --- | --- | --- | --- |
| Direct / needle | One exact or near-exact atom. | Lexical/direct dense short-circuit. | Unnecessary expensive traversal. |
| Semantic lookup | Paraphrased local evidence. | Dense plus lexical fusion. | Semantic false positive. |
| Broad thematic | Distributed topical context. | Hierarchy/routing plus evidence expansion. | Peripheral evidence loss. |
| Multi-hop | Several linked evidence items. | Bounded typed activation. | Missing intermediate support. |
| Temporal/revision | Historical and current validity. | Version/as-of aware path. | Superseded or revoked result treated as current. |
| Contradiction | Competing source-backed claims. | Trusted evidence + temporal path. | Affinity mistaken for support. |
| Abstention | No adequate evidence exists. | Early sufficiency gate. | Confident unsupported answer. |
| Consumer task | Task-specific evidence bundle. | Profile chosen by contract. | Wrong authority or missing provenance. |

## 11. Metric families

The evaluator should preserve query-level values before computing aggregates.

### Retrieval and evidence

- Recall@K and Complete Gold Coverage@K for candidate inclusion.
- nDCG@K when judgment relevance grades exist.
- Precision@K and evidence/citation precision when returned anchors matter.
- MRR or rank statistics only when the task has a single intended primary item.

### Organization

- source/atom coverage and orphan count;
- structural/topology validity;
- summary faithfulness and source-term/anchor coverage;
- incremental-versus-full rebuild parity;
- stability after a small controlled corpus update;
- routing benefit versus a flat or lexical baseline.

### Reliability and safety

- idempotent ingestion/replay result parity;
- failed-build non-leakage and active-release preservation;
- rollback success and source/release identity;
- policy/denial/redaction correctness;
- explicit abstention accuracy and untrusted-state behavior.

### Performance and economics

- cold and warm p50/p95/p99 by query class;
- QPS/concurrency and queue/backpressure behavior;
- graph nodes/edges/work examined per query;
- build/rebuild duration, memory, disk, and bytes per source atom;
- provider/model, storage, and compute cost attribution.

## 12. Baseline and ablation policy

Every proposed mechanism is compared with:

1. a simple defensible baseline appropriate to the query class;
2. the prior active architecture under the same corpus and configuration;
3. an ablation that removes only the proposed mechanism;
4. any required safety or resource control.

Freeze corpus, query/judgment IDs, segmentation, embedding configuration, and
measurement environment for a paired comparison. If any of these differ, label
the comparison exploratory rather than causal.

## 13. Statistical and reporting discipline

- Prefer paired per-query comparisons and report confidence intervals or
  uncertainty appropriate to the protocol.
- Report exclusions, failed queries, unavailable providers, and fallback
  assertions explicitly.
- Slice results by query class and relevant corpus strata; do not conceal a
  weak temporal or multi-hop class with a strong direct-lookup average.
- Retain raw run metadata and query-level artifacts necessary to reproduce a
  summarized claim.

## 14. 100K gate protocol

The first real-corpus scale gate requires:

1. a reviewed source manifest with at least 100K source atoms after the stated
   transform;
2. ingestion/replay/rebuild and crash-recovery drills;
3. a candidate-to-active lifecycle test under load;
4. measured query classes with cold and warm latency;
5. graph/index size and bounded-work measurements;
6. source coverage, orphan, and provenance validation;
7. storage, memory, build/rebuild duration, and cost report;
8. an independent verification report identifying residual limitations.

Synthetic scale fixtures may stress a known adversarial condition, but they are
not a substitute for this gate.

## 15. Release failure taxonomy

| Failure | Required classification |
| --- | --- |
| Dataset absent/checksum mismatch | data_prerequisite_failed |
| License or access unresolved | data_not_admitted |
| Mock/synthetic/fallback selected | prohibited_fallback |
| Provider/model unavailable | provider_prerequisite_failed |
| Candidate activation invalid | release_validation_failed |
| Query or judgment mapping invalid | evaluation_integrity_failed |
| Resource budget exceeded | operational_budget_failed |
| Unsupported claim requested | claim_boundary_failed |

A certification run fails closed on any required failure. It may still produce a
diagnostic developer report clearly marked non-certifying.
