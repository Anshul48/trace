<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE — Self-Organizing Retrieval Engine (10M Qualification & Reproducible Stack)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Source Freeze SHA-256](https://img.shields.io/badge/SOURCEFREEZE-38c66bef-success.svg)](freeze-src/cand/SOURCEFREEZE.json)
[![Qualification Status](https://img.shields.io/badge/10M_Qualification-PASS_(12,973s)-brightgreen.svg)](docs/BENCHMARKS.md)
[![Oracle Replay](https://img.shields.io/badge/Oracle_Replay-240%2F240_Exact-brightgreen.svg)](receipts/result.json)

![TRACE 10M receipt: 10,003,381 tokens, 12,973 s wall, guided recall 0.73 vs flat 0.056 in all-sources mode, 207 frozen files](assets/trace-hero.svg)

TRACE is an experimental research retrieval engine designed for self-organizing, hierarchical similarity search over dense token corpora. It ingests document streams, groups vector representations into a two-level hierarchical index via centroid averaging and adaptive leaf/parent placement, bounds partition skew with local repair, and serves both hierarchy-routed (**guided**) and brute-force (**flat**) queries over identical vector sets.

This repository publishes one exact, immutable candidate — the stack-fork in [`freeze-src/cand/`](freeze-src/cand/SOURCEFREEZE.json) — together with raw qualification receipts documenting a complete **10,003,381-token / 13,081-document / 63,441-atom** run executed on GCP VM `trace-build500`. Every headline metric reported below is derived verbatim from staged JSON records.

> **Identity & Source Integrity:** `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54` is the SHA-256 digest of the [`SOURCEFREEZE.json`](freeze-src/cand/SOURCEFREEZE.json) manifest across all 207 pinned candidate source files. It is an immutable source freeze, not a Git commit. Run `python3 tools/verify_freeze.py` to rehash all 207 files locally.

---

## Three Ways to Explore TRACE

### 1. [Explore the Qualified 10M Run (Browser Explorer)](docs/explorer/index.html)
Launch the zero-dependency interactive explorer in [`docs/explorer/`](docs/explorer/index.html) (or via GitHub Pages):
* **Deterministic Structural Hierarchy**: Progressively inspect the qualified 2-tier tree (Root &rarr; 3,711 Parents &rarr; 9,177 Leaves &rarr; 63,441 Atoms). Coordinates represent structural topology, not dimensionality reduction or embedding distance.
* **Per-Query Work & Routing Replay**: Step through algorithm routing stages (parent scoring &rarr; top-parent selection &rarr; DFS child descent &rarr; leaf atom ranking) with work distributions across 240 evaluation queries.
* **Lifecycle & Resilience Timeline**: Trace the 9 qualification phases, reader concurrency under ingestion, SIGKILL crash recovery (exit code -9), and repair to zero debt.
* *Note on 10M Topology Export*: When read-only VM export is pending, the explorer displays full qualification telemetry, per-query distributions, and the verified local 20k execution artifact with clear status demarcation.

### 2. [Inspect Authentic Recorded Evidence & Receipts](receipts/result.json)
Every claim is backed by immutable receipts generated on GCP instance `trace-build500` (2026-10-13):
* [`receipts/result.json`](receipts/result.json): Complete qualification run record (`status: PASS`, wall 12,973.17 s, 166,457 closed ledger commits).
* [`receipts/VM-10M-ACCEPTANCE.json`](receipts/VM-10M-ACCEPTANCE.json): Acceptance gate pass, 121/121 fixtures passing, store manifest match.
* [`receipts/AUDIT-RESULT.json`](receipts/AUDIT-RESULT.json): Independent oracle verification with **240/240 exact matches** (worst absolute score difference: 0.0).
* Retained store digest: `52e884393b2abd66b46ead13d1831238510dbf5f6738e5b398ea9334f0edca38` over 229,927 store files (~2.87 GB).

### 3. [Run the Frozen 20k Engine Locally](repro-20k/README.md)
Execute the actual frozen candidate harness (`product_pilot.py`) over a portable, verified 20k-token prefix (88 documents, 144 atoms) in an isolated environment without global package modification:
```bash
./install_and_run.sh
```
The installer automatically discovers `uv` or Python 3.12, sets up `.trace-demo-env`, verifies the 207 frozen files, unpacks and hashes the 20k prefix data, executes the frozen pilot to a `PASS` verdict, exports the run topology, and serves the local explorer at `http://127.0.0.1:8765/`. All prior runs are preserved under `local-runs/` with zero file deletions.

---

## Core Mechanism & Self-Organization

TRACE implements two-level dynamic hierarchical clustering directly inside the storage engine:

```text
[Document Stream] ──> Tokenization (TOK_V1) ──> Atom Chunking (Vectors)
                              │
                              ▼
                       Intake Ledger
                              │
                      [Batched Drain]
                              │
      ┌───────────────────────┴───────────────────────┐
      ▼                                               ▼
Leaf Placement (decide_leaf)            Parent Placement (decide_parent)
- Clustered via centroid similarity     - Groups leaves into parent holons
- Centroids updated incrementally       - Centroids computed by leaf averaging
      │                                               │
      └───────────────────────┬───────────────────────┘
                              ▼
                    [Local Repair Hook]
                    - Rebalances skewed leaves (threshold 0.55)
                    - Rebalances parent edges (threshold 0.45)
                    - repair_to_zero drains residual debt to 0
```

1. **Document Intake & Batched Drain**: Input text is tokenized into word chunks ("atoms") and appended into a journaled intake backlog. During periodic batched drain cycles (`_drain_locked_batched` in [`tlsys/org_service.py`](freeze-src/cand/fork/tl-sys/tlsys/org_service.py)), unindexed atoms are transferred into the hierarchical index.
2. **Centroid Placement & Adaptive Membership**:
   - Atoms are assigned to leaf clusters via `decide_leaf` in [`tlsys/place.py`](freeze-src/cand/fork/tl-sys/tlsys/place.py), updating leaf centroids incrementally (`join_descriptor`).
   - Leaves are clustered into parents via `decide_parent` in [`tlsys/place.py`](freeze-src/cand/fork/tl-sys/tlsys/place.py), maintaining parent centroids as member averages.
3. **Local Repair**: Skewed clusters are rebalanced via [`tlsys/local_repair.py`](freeze-src/cand/fork/tl-sys/tlsys/local_repair.py). In qualification, `repair_to_zero` executed 5 iterations, reducing initial repair debt from 5,314 to 0.
4. **Query Routing (`guided()`)**:
   - **Phase 1 (Parent Scoring)**: With `parent_budget=None`, scores the query against all **3,711 root parent centroids** in [`tlsys/query.py`](freeze-src/cand/fork/tl-sys/tlsys/query.py).
   - **Phase 2 (Child Descent)**: Selects top parents (`top_parents=4`), traverses child edges via DFS stack, and scores candidate leaf partitions.
   - **Phase 3 (Atom Ranking)**: Selects top leaves (`top_children=8`), scores candidate member atoms against the query, and returns the top-k ranked results.

### Query Work: Clarifying the 3,711 &rarr; 18 &rarr; 145 Smoke Probe
Previous summaries cited "3,711 parents &rarr; 18 children &rarr; 145 atoms" as universal query work. As verified in [`tools/product_pilot.py:967`](freeze-src/cand/tools/product_pilot.py) and [`SOURCE-CONTRACT.md`](/tmp/trace-source-audit-agy2-20261015/SOURCE-CONTRACT.md), **18/145 was a single post-drain smoke probe**, not the invariant for all queries:
* **Parents scored**: Fixed at **3,711** across all 240 evaluation queries (full parent scoring).
* **Children scored**: **Varies dynamically from 6 to 54** across evaluation queries (mean: **25.52**).
* **Atoms scored**: **Varies dynamically from 8 to 197** across evaluation queries (mean: **114.49**).
* **Member visits**: **Varies dynamically from 9 to 197** across evaluation queries (mean: **129.26**).

---

## Measured 10M Qualification Benchmarks

All metrics were captured during the 10M qualification execution on GCP VM `trace-build500` (PID 63255, 2026-10-13T01:48:12Z &rarr; 05:24:36Z, CPUs 0–2 solo, `nice 19`, single-threaded BLAS).

### Summary Table

| Metric | Measured Value | Standard / Condition |
|---|---|---|
| **Corpus Scale** | **10,003,381 TOK_V1 tokens** | 13,081 docs / 63,441 atoms, 0 cache misses |
| **Qualification Wall** | **12,973.17 s (~3.6 h)** | Status `PASS`, exit code 0 |
| **Convergence** | **0 pending documents** | `repair_to_zero` debt 5,314 &rarr; 0 (5 iterations) |
| **Closed Ledger** | **166,457 commits** / 166,457 dedup / 0 intake | Derived cap: 669,436 (headroom: 502,979) |
| **Acceptance Gate** | `VM-10M-ACCEPTANCE.json`: PASS | `manifest_match: true`, fixtures 121/121 |
| **Audit Gate** | `AUDIT-RESULT.json`: VERIFIED | 240 evaluation queries verified |
| **Oracle Replay** | Independent native einsum/argpartition | **240/240 exact matches** (worst diff 0.0) |
| **Final Store Pin** | `e8334c07-731d-4ff9-a292-8329b89c41b9:0:166457` | Digest `52e884393b2abd66...` (229,927 files) |

### Both Recorded Evaluation Modes (Guided vs Matched-Flat Control)

The evaluation harness ran 120 probes in each of two modes:
1. `leave_source_out: false` (LSO off / all sources included).
2. `leave_source_out: true` (LSO on / probe source excluded from index).

Crucially, the flat baseline arm was constrained to score the **exact same mean number of rows** per query as the guided arm (matched work), ensuring an apples-to-apples comparison:

| Mode | Guided Recall@10 | Matched-Flat Recall@10 | Mean Scoring Rows (Guided = Flat) | Guided p50 Latency |
|---|---:|---:|---:|---:|
| `leave_source_out: false` (All Sources) | **0.7300** | 0.0558 | 3,865.78 rows | 33.19 ms |
| `leave_source_out: true` (Source Excluded) | **0.4758** | 0.0483 | 3,836.24 rows | 33.24 ms |

| Probe Family | `leave_source_out: false` (Guided / Flat) | `leave_source_out: true` (Guided / Flat) |
|---|---|---|
| **chunk** (in-domain text chunk) | 0.8100 / 0.0575 | 0.5775 / 0.0400 |
| **noisy** (perturbed text chunk) | 0.7500 / 0.0500 | 0.5125 / 0.0350 |
| **cross** (cross-document query) | 0.6300 / 0.0600 | 0.3375 / 0.0700 |

![Recall at 10 for both recorded modes, guided versus matched flat](assets/recall.svg)

### Measured Qualification Phase Breakdown

| Phase | Observed Wall (s) | Share | Details |
|---|---:|---:|---|
| **Ingest (Visible + Prepare)** | 917.4 s | 7.1% | Initial backlog population |
| **Initial Drain & Prepare** | 1,780.5 s | 13.7% | 3 drain cycles, initial hierarchy formation |
| **Append Ingest with Readers** | 1,885.0 s | 14.5% | Concurrent ingestion with 2 active reader threads |
| **Source Capacity Rejection** | 1.2 s | <0.1% | Verified capacity limits enforced |
| **Prepare Rejection (Fresh Frontier)** | 496.6 s | 3.8% | Fault injection at uncommitted frontier |
| **Writer Kill & Restart** | 710.1 s | 5.5% | Unannounced `SIGKILL` (exit code -9), 0 duplicate commits |
| **Remaining Drain with Readers** | 4,865.6 s | 37.5% | Final 1 cycle under reader contention |
| **`repair_to_zero`** | 2,234.4 s | 17.2% | 5 bounded repair iterations, debt 5,314 &rarr; 0 |
| **Total Qualification Wall** | **12,973.17 s (~3.6 h)** | 100.0% | Complete run from empty state to final pin |

![10M phase walls: remaining drain dominates at 4,866 s](assets/phase-walls.svg)

### Hardware, Resources & Caps

* **Hardware Environment**: GCP `n2-highmem-16` (16 vCPUs, ~125 GiB RAM). Execution pinned solo to CPUs 0–2 at `nice 19` with single-threaded BLAS (`OPENBLAS_NUM_THREADS=1`).
* **Memory Watermarks**: Parent process peak RSS: **22,566 MiB** (22.0 GiB); Child process peak RSS: **15,669 MiB** (15.3 GiB). Both remained safely below the 43.6 GiB tripwire ceiling (>21 GiB margin).
* **Storage Footprint**: Total retained disk footprint: **2,868,578,536 bytes (~2.87 GB)** across 229,927 files.
* **Reader Concurrency**: 2 concurrent reader threads executed 15,813 + 15,812 requests (31,625 total) with 0 errors (p50: 116 ms, p95: 381 ms).

### Negative Findings & Operational Bottlenecks (Kept Prominent)

1. **Superlinear Drain Scaling**: Drain cost per document scales approximately **$O(N^{1.5})$** (the final drain phase required ~1.49 s/doc). Drain compute represents >85% of total wall time and constitutes the primary scaling bottleneck toward 100M tokens.
2. **Substantial Repair Cost**: `repair_to_zero` consumed **2,234 seconds (~17.2% of total wall time)** even with local repair disabled in the default path.
3. **Reader Contention Overhead**: Concurrent read traffic roughly **halves drain throughput (~2&times; penalty)** during background publication cycles.
4. **Ineffective Cosine Cache**: Staged cosine caching yielded no measurable throughput gain under concurrent readers; constant-factor software caches do not bend the $O(N^{1.5})$ drain curve.

---

## Code Tour & Deep Architecture Links

* [**ARCHITECTURE.md**](docs/ARCHITECTURE.md): Structural layout of the 5-fix candidate stack, storage ledger, and reader isolation.
* [**CODE-TOUR.md**](docs/CODE-TOUR.md): File-by-file walkthrough of the 207 frozen files in [`freeze-src/cand/`](freeze-src/cand/).
* [**BENCHMARKS.md**](docs/BENCHMARKS.md): Unabridged benchmark records, gate definitions, and derivation formulas.
* [**REPRO.md**](docs/REPRO.md): Exact reproduction commands, VM environment prerequisites, and pin hashes.
* [**20k Small Reproduction**](repro-20k/README.md): Portable protocol reproduction using 88 real SciFact abstracts and precomputed vector cache.
* [**Licenses & Data Model**](repro-20k/LICENSES-DATA-MODEL.md): Attribution for SciFact (ODC-By 1.0) and all-MiniLM-L6-v2 vector embeddings (Apache-2.0).

---

## Local Development & CI Verification

```bash
# 1. Verify frozen source bytes (207/207 OK)
python3 tools/verify_freeze.py

# 2. Check staged qualification receipt schemas and gate values
python3 tools/check_receipts.py

# 3. Check documentation links and SVG asset well-formedness
python3 tools/check_links.py

# 4. Run small-scale 20k prefix verification (NumPy required)
python3 repro-20k/prep_small_prefix.py verify --tokens 20000 --cand freeze-src/cand --data-dir repro-20k/data-20k

# 5. Run stack unit test suite (5 of 6 tests runnable outside build host)
bash freeze-src/run_all.sh stack

# 6. Run shipped integration suites (publication, pool reuse, serving pool)
bash freeze-src/run_all.sh existing
```

### In-Memory 120-Probe Demo App (Distinctly Scoped)
The standalone interactive app in [`demo-app/`](demo-app/README.md) (`python3 demo-app/run_demo.py --port 8765`) serves an in-memory sample corpus constructed strictly from the 120 qualification probe vectors. It demonstrates the frozen `HierQuery.guided` and `HierQuery.flat` scoring implementations in isolation. It is distinctly scoped as an educational vector probe viewer, separate from the multi-phase storage engine harness.

---

## Precise Scope & Research Limitations

* **Experimental Derived Caps**: Measurements reflect derived experimental caps (`max_delta_entries: 669,436`), not arbitrary infinite headroom.
* **Harness Agreement vs Semantic IR**: Metrics measure recall agreement against the exact oracle probe protocol on the staged vector corpus. They do **not** represent semantic IR relevance, nDCG, BM25 ranking superiority, or a universal latency guarantee.
* **Corpus Redistribution**: The full 10M token corpus (`docs-100m.jsonl`) and the 2.87 GB store are retained on the qualification VM; this repository redistributes only the portable 20k prefix (88 documents) and full receipts.
* **No Public Remote Writes**: All actions, tests, and verifications in this release operate strictly in local read-only and local execution modes.

---

## License

Apache-2.0 ([LICENSE](LICENSE), SPDX `Apache-2.0`). Corpus text excerpts and vector models retain their respective open-access upstream licenses as documented in [`repro-20k/LICENSES-DATA-MODEL.md`](repro-20k/LICENSES-DATA-MODEL.md).
