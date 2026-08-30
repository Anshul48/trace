# Formal Policy Reconciliation Brief: Wave R2.2 Level 1 Scale Certification Standard

> **Packet ID:** `c2-pol-01-policy-reconciliation-20260829`
> **Standard ID:** `DEC-P-005b-LEVEL1-R2.2`
> **Schema Version:** `2.2.0`
> **Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied; 1M unauthorized`) & Wave R2.2 Charter
> **Policy Lockfile SHA-256:** `a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda`
> **Policy Schema SHA-256:** `ec0d71b3d2e4ddff19e94d2549ff6811e2eecf9c767cdbad7b0193b6ec86e11c`
> **Date:** 2026-08-29T03:51:10Z
> **Status:** **PROPOSED_POLICY_REPAIR_REQUIRED (PROPOSED_AWAITING_HUMAN_GATE)**

---

## 1. Executive Summary & Regulatory Authority

This policy reconciliation brief establishes the canonical, schema-validated scale certification policy lockfile (`benchmarks/policies/scale_policy.lock.json`), its formal JSON validation schema (`benchmarks/policies/scale_policy.schema.json`), and formal decision framework for **Trace Wave R2.2 (Measurement Integrity Execution Closure)** addressing Audit Remediation Defects #3, #4, and #5.

Following the Human Gate C2 ruling of 2026-08-28 denying `promote_100k` and ordering strict repair, the Trace program operates under a fail-closed measurement integrity mandate. Prior runs suffered from policy ambiguity: numerical thresholds declared in the foundation-level decision `DEC-P-005` diverged from the early-scale hardware profile in `DEC-P-005b`, while runner and verifier implementations relied on hardcoded, duplicated Python dictionary literals.

Under **DEC-P-005b-LEVEL1-R2.2**, all numerical thresholds, retrieval capability floors, latency budgets, storage multiplier accounting rules, memory bounds, durability contracts, and statistical protocols are prospectively unified into a single immutable, content-addressed lockfile validated strictly against `scale_policy.schema.json`. Embedded copies in Python source are strictly prohibited; both runner (`scripts/run_100k_scale_gate.py`) and independent verifier (`scripts/verify_100k_candidate.py`) must load the policy lockfile dynamically and bind it by its cryptographic SHA-256 digest (`a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda`).

---

## 2. Forensic Context & Historical Policy Divergence Analysis

### 2.1 Policy Evolution Timeline

1. **DEC-P-005 (Foundation Gate, 2026-08-26):**
   - Established initial numerical release thresholds across all 5 Release Gates.
   - Formulated aspirational multi-tenant distributed production latency targets (SciFact $\le 10\text{ ms}$, NFCorpus $\le 15\text{ ms}$, FiQA $\le 25\text{ ms}$, MultiHop $\le 20\text{ ms}$).
   - Set memory at $\le 2.0\text{ GB}$ peak and storage multiplier at $\le 3.0\times$.
   - Defined 95% Bootstrap Confidence Intervals ($B=10,000$, $\alpha=0.01$).

2. **DEC-P-005b (Large-Token Retrieval Plan, 2026-08-26):**
   - Amended hardware-accounting clauses to introduce the **Reference-Capacity Host Profile (R16)**: a 16 GiB host-RAM reference machine with a peak process-tree RSS limit of $\le 8.0\text{ GiB}$ for the 100K corpus.
   - Mandated primary reporting of source tokens ($T$), active atoms ($N$), raw bytes ($B$), and storage amplification ($\le 3.0\times$).
   - Retained 100% atom retention, 0.0% drift, 100% anchor recovery, $\Delta = 0$ repeat erasure, and 100% rebuild parity.

3. **Gate C2 Invalidation & Audit Findings (2026-08-26 to 2026-08-28):**
   - Forensic audits revealed artificial score clamping (`max(min_ndcg + 0.012, ...)`), hardcoded abstention accuracy (`0.892`), 10K partial replays into throwaway tables, and uncommitted runner state.
   - Reclassified historical results as `UNCONFIRMED_DEFECTIVE`.

4. **Wave R2.1 Measuring System Construction (2026-08-29):**
   - Established qrels-closed evaluation query cohorts (7,457 total queries).
   - Aligned Python single-node SQLite WAL latency thresholds with measured R16 execution profiles (SciFact $\le 25\text{ ms}$, NFCorpus $\le 25\text{ ms}$, FiQA $\le 30\text{ ms}$, MultiHop $\le 45\text{ ms}$).
   - **Identified Defect:** Thresholds remained hardcoded in Python dictionaries inside `scripts/run_100k_scale_gate.py` and `scripts/verify_100k_candidate.py`, lacking a formal, content-addressed lockfile.

5. **Wave R2.2 Prospective Reconciliation Mandate (Packet C2-POL-01):**
   - Formally codifies all thresholds into `benchmarks/policies/scale_policy.lock.json`.
   - Binds runner, verifier, and governance dossiers by SHA-256 digest.

---

## 3. Retrieval Quality Floors & Latency Budget Reconciliation

### 3.1 Capability Lanes & Threshold Matrix

The evaluation suite evaluates 100% of the frozen, qrels-closed query cohort consisting of **7,457 queries** across four capability lanes and one unanswerable lane:

| Capability Lane | Admitted Dataset | Evaluated Queries | Primary Metric Bar | Secondary Metric Bar | Latency Budget (P95) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Direct Lookup** | `beir-scifact` | 1,109 | $\text{nDCG@10} \ge 0.700$ | $\text{Recall@20} \ge 0.880$ | $\le 25.0\text{ ms}$ |
| **Domain Semantic** | `beir-nfcorpus` | 3,237 | $\text{nDCG@10} \ge 0.350$ | $\text{Recall@20} \ge 0.220$ | $\le 25.0\text{ ms}$ |
| **Semantic QA** | `beir-fiqa` | 555 | $\text{nDCG@10} \ge 0.400$ | $\text{Recall@20} \ge 0.550$ | $\le 30.0\text{ ms}$ |
| **Multi-Hop Reasoning** | `multihop-rag` | 2,255 | $\text{nDCG@10} \ge 0.750$ | $\text{Coverage@20} \ge 0.880$ | $\le 45.0\text{ ms}$ |
| **Abstention Lane** | `null_queries` | 301 | $\text{Zero-Hallucination} = 1.000$ | $\text{Abstention Accuracy} \ge 0.900$ | $\le 25.0\text{ ms}$ |

### 3.2 Non-Negotiable Quality Preservation

- **No Retrospective Relaxation:** Quality floors are strictly frozen. No metric is lowered to accommodate a candidate deficit.
- **Unclamped Unfloored Scoring:** Scores are computed directly from raw top-20 ranking candidate IDs against frozen qrels. Any score flooring, clipping, or heuristic artificial boosting triggers immediate `CANDIDATE_FAILED` / `VERIFICATION_FAILED`.
- **Full Cohort Evaluation:** 100% of the 7,457 queries must be evaluated. Arbitrary slicing (`[:200]`) or top-$k$ truncation is strictly prohibited.

### 3.3 Single-Node R16 Latency Budget Rationale

The latency budgets reconcile early distributed multi-tenant aspirations with single-node Python + SQLite WAL FTS5 execution reality under the R16 reference profile:
- Direct lookup (`beir-scifact`) and Domain Semantic (`beir-nfcorpus`) budgets are set to **25.0 ms P95**, providing ample margin over bare BM25 index lookups (~1.5–5.0 ms) while bounding full result ranking and object serialization.
- Semantic QA (`beir-fiqa`) is allocated **30.0 ms P95** to accommodate financial tokenization, term expansion, and larger passage retrieval sets.
- Multi-Hop Reasoning (`multihop-rag`) is allocated **45.0 ms P95** to accommodate multi-clause boolean scoring, cross-document graph neighbor aggregation, and candidate re-ranking.

---

## 4. Real Un-Labeled Abstention & Anti-Leakage Protocol

### 4.1 Anti-Leakage Architecture

In prior defective runs, null queries bypassed the retrieval engine via explicit control-flow flags (`system_abstained = True`) or label presence in the runner input.

Under `DEC-P-005b-LEVEL1-R2.2`:
1. **Unlabeled Path Mandate:** Null queries are delivered to the retrieval pipeline without labels, category hints, or expected answers.
2. **Unified Retrieval & Citation Filter:** The candidate engine must execute full index querying, score candidate documents, apply its internal confidence/citation threshold, and produce an answer decision.
3. **Custody Separation:** Expected null labels remain exclusively in independent verifier custody.
4. **Binding Abstention Metrics:**
   - **Zero Hallucination Rate:** $\text{ZHR} = 1.000$ ($100.0\%$). Zero unsupported citations or factual claims permitted on unanswerable queries.
   - **Abstention Accuracy:** $\ge 0.900$ ($90.0\%$) correct abstentions over the 301 null queries.

---

## 5. Storage Architecture & Multiplier Accounting Model

### 5.1 Storage Budget Specifications

- **Raw Text Corpus Denominator ($B_{raw}$):** $62,870,136\text{ bytes}$ ($62.87\text{ MB}$) across the 100,000 unique records in `musique` (80K), `beir-fiqa` (10.575K), `beir-scifact` (5.183K), `beir-nfcorpus` (3.633K), and `multihop-rag` (0.609K). Baseline reference corpus text: $59,960,000\text{ bytes}$.
- **Storage Amplification Multiplier:** $\le 3.00\times$.
- **Storage Footprint Limits:**
  - Strict Maximum: $\le 188,610,408\text{ bytes}$ ($188.61\text{ MB}$).
  - Canonical Multiplier Bound: $3.00 \times 62,870,136\text{ bytes} = 188,610,408\text{ bytes}$ ($188.61\text{ MB}$).
  - Target Operational Capacity: $\le 170,000,000\text{ bytes}$ ($170.0\text{ MB}$).

### 5.2 Accounting Scope: Total Hot State vs Durable Spine

```text
+-----------------------------------------------------------------------+
| TOTAL HOT DATABASE CAPSULE FOOTPRINT (<= 188.61 MB / <= 3.00x)        |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  | DURABLE SPINE (Immutable, bit-exact source of truth)             |  |
|  |  - `events` table (raw ingestion/modification stream)           |  |
|  |  - `ingestions` table (batch metadata & Merkle roots)           |  |
|  |  - `source_lifecycle` table (provenance & state tracking)       |  |
|  |  - `node_versions` table (raw text atom chunks & hashes)        |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  | DERIVED PROJECTIONS (100% rebuildable from Spine events)         |  |
|  |  - `trace_fts` (SQLite FTS5 inverted lexical index)             |  |
|  |  - `nodes` & `edge_versions` (Cortex association graph)         |  |
|  |  - B-tree and covering secondary indexes                       |  |
|  +-----------------------------------------------------------------+  |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  | ACTIVE WAL & SHARED MEMORY STATE AT REST                        |  |
|  |  - `scale_100k.db-wal` (uncheckpointed WAL log frames)          |  |
|  |  - `scale_100k.db-shm` (shared memory coordination index)       |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
```

### 5.3 Accounting Inclusion & Exclusion Rules

1. **Included Artifacts (Hot State Footprint):**
   - Primary database file: `scale_100k.db`
   - Active Write-Ahead Log: `scale_100k.db-wal`
   - Shared memory index: `scale_100k.db-shm`
2. **Excluded Artifacts (Offline / Ephemeral):**
   - Upstream raw JSONL download archives in user cache (`~/.cache` or `%LOCALAPPDATA%`).
   - Ephemeral in-memory staging queues discarded after ingestion commit.
   - Retained offline backup snapshots or diagnostic trace logs.

---

## 6. Memory RSS & Host Reference Profile R16

### 6.1 Reference Profile R16 Mandate

- **Host Specification:** 16 GiB host RAM reference environment.
- **Process-Tree RSS Limit:** Peak memory $\le 8.0\text{ GiB}$ across all child worker threads and subprocesses.
- **Measurement Method:** Kernel-level high-water mark resident set size via `/proc/self/status` (`VmHWM`) sampled continuously throughout ingestion, index construction, query evaluation, and crash recovery.
- **Zero OOM Policy:** Zero out-of-memory kernel kills, zero memory allocator retry loops, and zero active swap thrashing during qualifying certification phases.

---

## 7. Graph Topology & Traversal Bounds

- **Max Stored Degree:** $\le 10$ out-degree per atom node.
- **Traversal Algorithm:** Personalized PageRank (PPR) / Spreading Activation with depth $\le 15$ steps.
- **Traversal Latency:** P95 traversal time $\le 35.0\text{ ms}$ over 1,000 sampled seed nodes.
- **Mandatory Telemetry:** Full per-walk metrics (seed ID, depth, visited nodes, traversed edges, execution time ms) emitted to `graph_walk_telemetry.jsonl`.

---

## 8. Durability, Provenance & Replay Parity

| Durability Attribute | Binding Policy Bar | Verification Method |
| :--- | :--- | :--- |
| **Source Atom Retention** | $1.000$ ($100.0\%$) | Verification of all 100,000 documents and $\ge 200,000$ atom versions. |
| **Content Hash Drift** | $0.000$ ($0.0\%$) | SHA-256 recomputation of stored atom text against staged source records. |
| **Anchor Recovery** | $1.000$ ($100.0\%$) | Direct byte-offset slice verification across 1,000 sampled source proofs. |
| **Repeat-Erasure Delta** | $\Delta = 0$ writes | Idempotent tombstoning; zero database writes on duplicate erasure requests. |
| **Full Event Replay Parity** | $1.000$ ($100.0\%$) | 100% full event replay into a blank DB; exact 6-table SHA-256 state match. |

---

## 9. Statistical Protocol & Decision Rules

### 9.1 Hypothesis Testing & Bootstrap Framework

1. **Bootstrap Confidence Intervals:** 95% two-sided bootstrap confidence intervals computed over $B = 10,000$ resamples with fixed seed (`seed = 42`).
2. **Statistical Significance Floor:** $\alpha = 0.01$ under paired Wilcoxon signed-rank and paired Student's $t$-tests.
3. **Practical Effect Size Floor:** Meaningful performance delta requires $\Delta \ge +0.030$ nDCG@10 or Cohen's $d \ge 0.20$.
4. **Denominator Integrity:** Queries with zero returned candidates or engine timeouts are scored strictly as $0.0$ and included in the mean. Slicing or dropping failing queries is prohibited.

---

## 10. Operational Integration & Cryptographic Binding

### 10.1 Lockfile Content-Addressing

Both runner (`scripts/run_100k_scale_gate.py`) and verifier (`scripts/verify_100k_candidate.py`) must implement dynamic loading of `scale_policy.lock.json` and verify its cryptographic digest:

```python
import hashlib, json
from pathlib import Path

POLICY_PATH = Path("benchmarks/policies/scale_policy.lock.json")
EXPECTED_POLICY_SHA256 = "a3d9ecdcc715d0f99b5d18156d98deaf2e9a319ce52b34564c4757c28902bbda"

def load_canonical_scale_policy(path: Path = POLICY_PATH) -> dict:
    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if digest != EXPECTED_POLICY_SHA256:
        raise ValueError(f"Policy lockfile SHA-256 mismatch! Expected {EXPECTED_POLICY_SHA256}, got {digest}")
    return json.loads(raw_bytes.decode("utf-8"))
```

### 10.2 Downstream Dispatch Directives

- **Unblocks Task R2.2-02:** Binding of `scale_policy.lock.json` and `queries_manifest.json` across runner and verifier.
- **Unblocks Task R2.2-03:** Runner contract execution with full 7,457 queries cohort and top-20 telemetry.
- **Unblocks Task R2.2-05:** Standalone independent verifier loading policy lock by digest and recomputing all metrics.
- **Unblocks Task R2.2-06:** Negative integration test suite verifying fail-closed rejection on policy tampering or drift.

---
