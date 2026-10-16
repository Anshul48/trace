<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE — Self-Organizing Retrieval Engine (10M Qualification & Reproducible Stack)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Source Freeze Manifest](https://img.shields.io/badge/Freeze_Manifest-38c66bef_(207_files)-blue.svg)](freeze-src/cand/SOURCEFREEZE.json)
[![Qualification Receipt](https://img.shields.io/badge/Receipt-10M_PASS_(12,973s)-brightgreen.svg)](docs/BENCHMARKS.md)
[![Oracle Replay Receipt](https://img.shields.io/badge/Receipt-Oracle_240%2F240_Exact-brightgreen.svg)](receipts/result.json)
[![Recorded 20k Run](https://img.shields.io/badge/Recording-20k_Run_(27.8s)-blue.svg)](https://anshul48.github.io/trace/recording/)

![TRACE 10M receipt: 10,003,381 tokens, 12,973 s wall, guided recall 0.73 vs flat 0.056 in all-sources mode, 207 frozen files](assets/trace-hero.svg)

> **Terminal Recording**: [Recorded 20K local run with cached vectors (27.8s), separate from historical 10M qualification](https://anshul48.github.io/trace/recording/)

## Purpose, Maturity & Use Case

TRACE is an experimental research retrieval architecture designed for self-organizing, multi-tier directed acyclic graph (DAG) similarity search over streaming token corpora.

* **Primary Use Case**: Continuous ingestion workloads (e.g. streaming documents, append-only memory ledgers) where newly ingested items must become searchable immediately without triggering full-corpus clustering recomputation.
* **Core Innovation**: Hierarchical self-organization inside storage via incremental centroid placement (`decide_leaf` / `decide_parent`), overlapping leaf/parent memberships, and bounded local repair. Guided query routing concentrates compute on high-likelihood branches, delivering **0.73 protocol recall@10** on the qualified probe suite (`leave_source_out: false`) under matched-work budgets where flat scanning yields 0.056 (measured protocol recall agreement against oracle top-10 on staged vectors, not semantic IR relevance, universal latency, or ACID transaction guarantees).
* **Maturity Level**: Research prototype candidate. Verified at scale on GCP VM `trace-build500` over a **10,003,381-token / 13,081-document / 63,441-atom** corpus. Supported environment is Linux x86_64 (Python 3.12 verified baseline; Python &gt;= 3.11 source floor); Windows PowerShell execution script is provided (`install_and_run.ps1`) but unverified until proven on a Windows testbed.
* **Candidate Source Freeze**: Pinned across all 207 candidate files in [`freeze-src/cand/`](freeze-src/cand/SOURCEFREEZE.json) with manifest SHA-256 digest `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54` (manifest digest over immutable candidate tree, not a Git commit SHA; repository base commit is `1874aff`).

---

## Three Ways to Explore TRACE

The three-part visitor offering pairs terminal execution recording, interactive structural DAG exploration, and one-command local reproduction:

### 1. [Watch the Recorded 20k Execution (Terminal Cast)](https://anshul48.github.io/trace/recording/)
* **Recorded Run CTA**: [Recorded 20K local run with cached vectors (27.8s), separate from historical 10M qualification](https://anshul48.github.io/trace/recording/)
* Replays the authentic terminal execution of the frozen candidate harness over the 20k prefix dataset (27.8 s wall time with precomputed vector cache). This is an actual recorded 20k run, separate from the historical 10M qualification run on GCP.

### 2. [Explore the Qualified 10M DAG Hierarchy (Interactive Explorer)](https://anshul48.github.io/trace/explorer/)
Open the zero-dependency interactive browser explorer at [https://anshul48.github.io/trace/explorer/](https://anshul48.github.io/trace/explorer/) (or serve locally via `./install_and_run.sh` from [`docs/explorer/index.html`](docs/explorer/index.html)):
* **Authentic Overlapping DAG**: Progressively inspect the static recorded 10M directed acyclic graph (Unified Entry &rarr; 3,711 Parents &rarr; 9,177 Leaves &rarr; 63,441 Atoms across 13,081 documents). Preserves all **4,370 multi-parent leaves** and **9,540 multi-leaf atoms** (13,547 parent-child edges; 72,981 leaf-atom edges). The membership structure is an overlapping DAG (many-to-many linkages across tiers), not a disjoint tree or unique 2-tier partition.
* **Deterministic Structural Coordinates**: Canvas coordinates represent deterministic hierarchical DAG layout for structural visualization, not semantic embedding distances or vector projections. Raw embedding vectors, full corpus text, and per-query visited route IDs are not exported in the static graph artifact.
* **Real Node Inspector**: Click or search any authentic node ID (`xpar-...`, `xseg-...`, atom ID, or doc ID) to inspect parent linkages, child postings, member counts, and document metadata.
* **Query Routing Replay**: Step through the 5 routing stages (parent scoring scanning all 3,711 `seg_parents` centroids &rarr; branch selection &rarr; DFS child descent &rarr; leaf atom ranking &rarr; evaluation) across the 240 evaluation queries. Historical receipts record aggregate work metrics across both LSO modes (no 10M visited paths or node-level route IDs are recorded in historical receipts).
* **Lifecycle & Resilience Timeline**: Review measured phases, concurrency under ingestion, writer `SIGKILL` crash recovery (exit code -9), and repair to zero debt.
* **Client-Side Static Inspection**: The explorer is a zero-dependency client-side viewer over the static recorded 10M graph and qualification receipts; it runs entirely in the browser with no Python backend or third-party runtime services; browser downloads static artifacts.

### 3. [Run the Frozen 20k Engine Locally](repro-20k/README.md)
Execute the actual frozen candidate harness (`product_pilot.py`) over a portable, verified 20k-token prefix (88 documents, 20,030 tokens, 144 atoms, 51 parents, 81 leaves) in an isolated virtual environment (`.trace-demo-env`) without global package modification:
```bash
./install_and_run.sh
```
The installer discovers `uv` or Python 3.12 (Python &gt;= 3.11 floor), sets up `.trace-demo-env`, verifies the 207 frozen candidate files against the freeze manifest, unpacks and hashes the 20k prefix data, executes the frozen pilot to a `PASS` verdict, exports the run topology, and serves the local explorer over the resulting real run graph at `http://127.0.0.1:8765/`. All prior runs are preserved under `local-runs/` with zero file deletions. This runs the real frozen pilot and local viewer; it is not a 10M rebuild or an arbitrary ad-hoc text search query engine. User exploration pairs live terminal execution of the 20k pilot with static inspection of the 10M qualification receipts and graph artifacts.

---

## Authentic Recorded Evidence & Receipts
Every claim is backed by immutable receipts generated on GCP instance `trace-build500` (2026-10-13):
* [`receipts/result.json`](receipts/result.json): Complete qualification run record (`status: PASS`, wall 12,973.17 s, 166,457 closed ledger commits).
* [`receipts/VM-10M-ACCEPTANCE.json`](receipts/VM-10M-ACCEPTANCE.json): Acceptance gate pass, 121/121 fixtures passing, store manifest match.
* [`receipts/AUDIT-RESULT.json`](receipts/AUDIT-RESULT.json): Independent oracle verification with **240/240 exact matches** (worst absolute score difference: 0.0).
* Retained store digest: `52e884393b2abd66b46ead13d1831238510dbf5f6738e5b398ea9334f0edca38` over 229,927 store files (~2.87 GB).

---

## Core Mechanism & DAG Self-Organization

TRACE implements multi-tier dynamic hierarchical clustering directly inside the storage engine:

```text
[Document Stream] ──> Tokenization (TOK_V1) ──> Atom Chunking (Vectors)
                              │
                              ▼
                        Intake Ledger
                              │
                      [Batched Drain]
                              │
       ┌──────────────────────┴──────────────────────┐
       ▼                                             ▼
Leaf Placement (decide_leaf)           Parent Placement (decide_parent)
- Clustered via centroid similarity    - Groups leaves into parent holons
- Centroids updated incrementally      - Centroids computed by leaf averaging
- Multi-leaf atom assignments          - Multi-parent leaf assignments
       │                                             │
       └──────────────────────┬──────────────────────┘
                              │
                              ▼
               [Hierarchical Overlapping DAG]
                              │
              (Maintenance & Final Convergence)
                              ▼
               [Local Repair & repair_to_zero]
               - Bounded local repair capability preserves cohesion
               - Explicit final repair_to_zero phase drains debt to 0
```

1. **Document Intake & Batched Drain**: Input text is tokenized into word chunks ("atoms") and appended into a journaled intake backlog. During periodic batched drain cycles (`_drain_locked_batched` in [`tlsys/org_service.py`](freeze-src/cand/fork/tl-sys/tlsys/org_service.py)), unindexed atoms are transferred into the hierarchical index.
2. **Centroid Placement & Overlapping Membership**:
   - Atoms attach to leaf clusters via `decide_leaf` in [`tlsys/place.py`](freeze-src/cand/fork/tl-sys/tlsys/place.py), updating leaf centroids incrementally (`join_descriptor`).
   - Leaves attach to parent clusters via `decide_parent` in [`tlsys/place.py`](freeze-src/cand/fork/tl-sys/tlsys/place.py). Leaves may belong to multiple parents (4,370 overlapping leaves in 10M), and atoms may belong to multiple leaves (9,540 overlapping atoms in 10M).
3. **Local Repair Capability & Explicit `repair_to_zero` Phase**: Storage incorporates a bounded local repair capability to maintain cluster cohesion without global recomputation. In qualification, `local_repair=True` was active in `TLStore`. Cluster cohesion similarity floors are enforced via [`tlsys/local_repair.py`](freeze-src/cand/fork/tl-sys/tlsys/local_repair.py) (calibrated thresholds, not guessed skew):
   - `leaf_threshold = 0.55`: Leaf member cohesion similarity floor.
   - `edge_threshold = 0.45`: Parent-child edge similarity floor.
   - `parent_cohesion_threshold = 0.45`: Parent child cohesion similarity floor.
   Rather than running continuous repair across the ingestion hot path, maintenance is bounded; an explicit final `repair_to_zero` phase executed 5 bounded iterations at the end of the run, reducing residual repair debt from 5,314 to 0.
4. **Query Routing (`guided()`)**:
   - **Phase 1 (Parent Scoring)**: Scores the query against all **3,711 seg_parent centroids** in storage (`tlsys/query.py`). The router scans all storage `seg_parents` (storage segment parent holons, rather than traversing a tree of root parents); the membership DAG is an overlapping multi-tier structure with many-to-many linkages, not a disjoint tree or unique 2-tier partition.
   - **Phase 2 (Child Descent)**: Selects top parents (`top_parents = 4`), traverses child edges via DFS stack, and scores candidate leaf partitions.
   - **Phase 3 (Atom Ranking)**: Selects top leaves (`top_children = 8`), scores candidate member atoms against the query, and returns top-k ranked results.

### Query Work: Dynamic Range across 240 Queries
Across the 240 evaluation queries:
* **Both Evaluation Modes Recorded**:
  * **LSO Off (`leave_source_out: false`, 120 probes)**: Guided Recall@10 = **0.7300**, Matched-Flat = **0.0558**, Mean Scoring Rows = **3,865.78**, Guided p50 Latency = **33.19 ms**.
  * **LSO On (`leave_source_out: true`, 120 probes)**: Guided Recall@10 = **0.4758**, Matched-Flat = **0.0483**, Mean Scoring Rows = **3,836.24**, Guided p50 Latency = **33.24 ms**.
* **Tier Work Dynamic Range**:
  * **Parents scored**: Fixed at **3,711** across all queries (full scan of all storage `seg_parents`, `parent_budget=None`).
  * **Children scored**: Varies dynamically from **6 to 54** across evaluation queries (mean: **25.52**).
  * **Atoms scored**: Varies dynamically from **8 to 197** across evaluation queries (mean: **114.49**).
  * **Member visits**: Varies dynamically from **9 to 197** across evaluation queries (mean: **129.26**).
* *Note on Visited Paths*: Historical scalar receipts record aggregate and per-query work counts; no 10M visited paths or node-level route IDs were recorded during the qualification run.

---

## Measured 10M Qualification Benchmarks

All metrics were captured during the 10M qualification execution on GCP VM `trace-build500` (PID 63255, 2026-10-13T01:48:12Z &rarr; 05:24:36Z, CPUs 0–2 solo pinned, `nice 19`, single-threaded BLAS via `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`). Host memory available: 129,638,072 KB (~123.6 GiB) start &rarr; 106,903,248 KB (~101.9 GiB) end; RSS tripwire: 44,643 MiB (43.6 GiB) with observed peak RSS of 22.0 GiB (parent) and 15.3 GiB (child).

### Summary Table

| Metric | Measured Value | Standard / Condition |
|---|---|---|
| **Corpus Scale** | **10,003,381 TOK_V1 tokens** | 13,081 docs / 63,441 atoms, 0 cache misses |
| **Qualification Wall** | **12,973.17 s (~3.6 h)** | Status `PASS`, exit code 0 |
| **Convergence** | **0 pending documents** | `repair_to_zero` debt 5,314 &rarr; 0 (5 iterations) |
| **Closed Ledger** | **166,457 commits** / 166,457 dedup / 0 intake | Derived cap: 669,436 (headroom: 502,979) |
| **DAG Overlap** | **4,370 multi-parent leaves** / 9,540 multi-leaf atoms | 13,547 parent-child edges; 72,981 leaf-atom edges |
| **Host Resources** | **CPUs 0–2 solo, nice 19, 1-thread BLAS** | Memory 123.6 &rarr; 101.9 GiB; peak RSS 22.0 GiB (&lt;43.6 GiB tripwire) |
| **Acceptance Gate** | `VM-10M-ACCEPTANCE.json`: PASS | `manifest_match: true`, fixtures 121/121 |
| **Audit Gate** | `AUDIT-RESULT.json`: VERIFIED | 240 evaluation queries verified |
| **Oracle Replay** | Independent native einsum/argpartition | **240/240 exact matches** (worst diff 0.0) |
| **Final Store Pin** | `e8334c07-731d-4ff9-a292-8329b89c41b9:0:166457` | Digest `52e884393b2abd66...` (229,927 files) |

### Both Recorded Evaluation Modes (Guided vs Matched-Flat Control)

The evaluation harness ran 120 probes in each of two modes:
1. `leave_source_out: false` (LSO off / all sources included).
2. `leave_source_out: true` (LSO on / probe source excluded from index).

The flat baseline arm was constrained to score the **exact same mean number of rows** per query as the guided arm (matched work), ensuring an apples-to-apples comparison:

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

### Full Derived Capacity Limits & Operational Enforcements

Capacity limits enforced during qualification:

| Parameter | Configured / Derived Cap | Headroom / Observed Margin | Details |
|---|---:|---:|---|
| `max_delta_entries` | **669,436** | **502,979 commits** | Derived via atom projection ratio: `ceil(37,117 * (63,441 / 7,035) * 2.0)` ([receipts/result.json](receipts/result.json#L76-L93)) |
| `max_dedup_rows` | **1,000,000** | **833,543 rows** | In-memory dedup window ceiling |
| `max_delta_bytes` | **536,870,912** (512 MiB) | Safely bounded | Memory buffer ceiling |
| `max_intake_backlog` | **10,000** | **10,000** | Finished at 0 intake backlog |
| `max_reservations` | **64** | Bounded | Concurrent lease slots |
| `reserve_deadline_s` | **5.0 s** | Bounded | Timeout before retryable capacity rejection |
| `retirement_headroom_entries` | **1,000** | Enforced | Commit headroom before forced retirement |
| `kill_tripwire_rss` | **44,643 MiB** (43.6 GiB) | **&gt;21 GiB margin** | Parent peak: 22.0 GiB; Child peak: 15.3 GiB |

### F1 Fresh-Frontier Visibility Benchmarks

Freshly appended documents were queried immediately upon ACK return:

| Metric | Measured Value | Standard / Condition |
|---|---|---|
| **Visibility Probes** | **33 / 33 within 5.0 s** | `all_within_5s: true` (100% compliance) |
| **ACK-to-Query p50 Latency** | **118.99 ms** | Measured from ACK return to query completion |
| **ACK-to-Query p95 Latency** | **129.86 ms** | Tail latency under ongoing ingestion |
| **ACK-to-Query Max Latency** | **132.96 ms** | Worst-case visibility latency |
| **Merged Rows** | **50 rows** | Merged committed hierarchy + pending dense fallback |

### Fault Injection & Crash Recovery Gates

| Event / Gate | Injected Condition | Observed Recovery Result |
|---|---|---|
| **Phase 6 Writer SIGKILL** | Unannounced `SIGKILL` (exit code **-9**) | Clean recovery, **0 duplicate recommits**, restart head `e8334c07...136612` |
| **Phase 4 Capacity Rejection** | Backlog limit reached | Explicit `REJECT_CAPACITY(deadline)` error raised and handled safely |
| **Phase 5 Prepare Fault** | Frontier prepare stage failure | Fault caught, fresh frontier generation `f5f6918c...` cleanly isolated |
| **Phase 8 Repair Debt** | End of drain debt: 5,314 | 5 bounded iterations drained debt to **0** |

### Measured Qualification Phase Breakdown

| Phase | Observed Wall (s) | Share | Details |
|---|---:|---:|---|
| **Ingest (Visible + Prepare)** | 917.4 s | 7.1% | Initial backlog population |
| **Initial Drain & Prepare** | 1,780.5 s | 13.7% | 3 drain cycles, initial hierarchy formation |
| **Append Ingest with Readers** | 1,885.0 s | 14.5% | Concurrent ingestion with 2 active reader threads |
| **Source Capacity Rejection** | 1.2 s | &lt;0.1% | Verified capacity limits enforced |
| **Prepare Rejection (Fresh Frontier)** | 496.6 s | 3.8% | Fault injection at uncommitted frontier |
| **Writer Kill & Restart** | 710.1 s | 5.5% | Unannounced `SIGKILL` (exit code -9), 0 duplicate commits |
| **Remaining Drain with Readers** | 4,865.6 s | 37.5% | Final 1 cycle under reader contention |
| **`repair_to_zero`** | 2,234.4 s | 17.2% | 5 bounded repair iterations, debt 5,314 &rarr; 0 |
| **Other/unattributed harness time and rounding** | 82.4 s | 0.6% | Difference between total qualification wall (12,973.17 s) and rounded listed phases (12,890.8 s) |
| **Total Qualification Wall** | **12,973.17 s (~3.6 h)** | 100.0% | Complete run from empty state to final pin |

*Reconciliation Note: The 8 listed workload phases total 12,890.8 s (~99.4%). The remaining 82.4 s reflects the arithmetic difference between the total measured qualification wall (12,973.17 s) and the sum of the rounded phase values (12,890.8 s), representing other/unattributed harness time and rounding; no claim is made as to exact task composition.*

![10M phase walls: remaining drain dominates at 4,866 s](assets/phase-walls.svg)

### Negative Findings & Operational Bottlenecks (Kept Prominent)

The following findings characterize actual empirical measurements over the observed 10M qualification run on GCP VM `trace-build500`, rather than universal theoretical complexity bounds across arbitrary index topologies or hardware:

1. **Drain Scaling Bottleneck (100M Not Qualified)**: Background drain is the primary operational scaling bottleneck toward 100M tokens (100M not qualified). In the measured 10M qualification run, remaining drain under reader traffic consumed **4,865.6 s (37.5% of total qualification wall)** and initial drain consumed **1,780.5 s (13.7%)**.
2. **Substantial Repair Cost**: `repair_to_zero` consumed **2,234.4 seconds (17.2% of total qualification wall)** across 5 bounded iterations to drain residual debt from 5,314 to 0.
3. **Reader Traffic Overhead**: Background publication and drain cycles operated under concurrent reader traffic conditions (2 active reader threads executing 31,625 total queries), incurring substantial synchronization and contention overhead during drain execution.
4. **Cosine Cache Ineffective**: Software cosine caching yielded no measurable throughput improvement under reader traffic conditions; caching did not resolve the background drain scaling bottleneck.

---

## Code Tour & Architecture Documentation

* [**ARCHITECTURE.md**](docs/ARCHITECTURE.md): Structural layout of the 5-fix candidate stack, storage ledger, and reader isolation.
* [**CODE-TOUR.md**](docs/CODE-TOUR.md): File-by-file walkthrough of the 207 frozen files in [`freeze-src/cand/`](freeze-src/cand/).
* [**BENCHMARKS.md**](docs/BENCHMARKS.md): Unabridged benchmark records, gate definitions, and derivation formulas.
* [**REPRO.md**](docs/REPRO.md): Exact reproduction commands, VM environment prerequisites, and pin hashes.
* [**20k Small Reproduction**](repro-20k/README.md): Portable protocol reproduction using 88 real SciFact abstracts and precomputed vector cache.
* [**Licenses & Data Model**](repro-20k/LICENSES-DATA-MODEL.md): Attribution for SciFact (ODC-By 1.0) and all-MiniLM-L6-v2 vector embeddings (Apache-2.0).

---

## Local Development & CI Verification

Prerequisites: Python &gt;= 3.11 (Python 3.12 verified baseline; Linux x86_64 supported; Windows unverified), NumPy, BLAKE3.

```bash
# 1. Verify frozen source bytes (207/207 OK)
python3 tools/verify_freeze.py

# 2. Check staged qualification receipt schemas and gate values
python3 tools/check_receipts.py

# 3. Check documentation links and SVG asset well-formedness
python3 tools/check_links.py

# 4. Run automated Playwright browser test suite and capture screenshots
python3 tools/test_explorer_playwright.py

# 5. Run stack unit test suite (5 of 6 tests runnable outside build host)
bash freeze-src/run_all.sh stack

# 6. Run shipped integration suites (publication, pool reuse, serving pool)
bash freeze-src/run_all.sh existing
```

### In-Memory 120-Probe Demo App (Distinctly Scoped)
The standalone interactive app in [`demo-app/`](demo-app/README.md) (`python3 demo-app/run_demo.py --port 8765`) serves an in-memory sample corpus constructed strictly from the 120 qualification probe vectors. It demonstrates the frozen `HierQuery.guided` and `HierQuery.flat` scoring implementations in isolation. It is distinctly scoped as an educational vector probe viewer, separate from the multi-phase storage engine harness.

---

## Scope & Research Limitations

* **Experimental Derived Caps**: Measurements reflect derived experimental caps (`max_delta_entries: 669,436`), not arbitrary infinite headroom.
* **Harness Agreement vs Semantic IR**: Metrics measure protocol recall agreement against the exact oracle probe protocol on the staged vector corpus. They do **not** represent semantic IR relevance, nDCG, BM25 ranking superiority, or a universal latency guarantee.
* **No Distributed ACID Transactions**: TRACE provides single-writer append-only concurrency with crash recovery to a consistent ledger boundary; it does not implement distributed ACID transactions or cross-shard consensus.
* **Corpus Redistribution**: The full 10M token corpus (`docs-100m.jsonl`) and the 2.87 GB store are retained on the qualification VM; this repository redistributes the verified structural DAG (`docs/explorer/graph_10m.json`), the portable 20k prefix (88 documents, 20,030 tokens, 144 atoms), and full receipts.

---

## License

Apache-2.0 ([LICENSE](LICENSE), SPDX `Apache-2.0`). Corpus text excerpts and vector models retain their respective open-access upstream licenses as documented in [`repro-20k/LICENSES-DATA-MODEL.md`](repro-20k/LICENSES-DATA-MODEL.md).
