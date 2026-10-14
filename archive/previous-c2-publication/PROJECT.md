# Project: Project Trace Cognitive Substrate v2 Architectural Research & RFCs

## Architecture Overview
Project Trace Cognitive Substrate v2 elevates Trace into a state-of-the-art, self-organizing hybrid memory architecture that marries bio-inspired cognitive principles with hardware-native systems engineering:
- **Core Spine Lane (CORE)**: Immutable, append-only SQLite WAL event log storing canonical `events`, `nodes`, `node_versions`, and `atom` tables. 100% bit-exact replayability (`CAP-D004`, `CAP-D005`). Synchronous model-free ingestion running at $\ge 800\text{ docs/sec}$ (`CAP-D003`).
- **Cognitive Consolidation Lane (CORTEX)**: Asynchronous background "sleep-phase" dreaming engine operating over bounded changed neighborhoods ($\mathcal{N}_\delta(\Delta V)$, $K_{\max} \le 512$, $O(1)$ complexity). Detects logical, temporal (Allen interval algebra), and factual contradictions ($E^-$ inhibitory edges). Induces Arthur Koestler L1–L3 holarchies and invariant schemas via Formal Concept Analysis and Cobweb Category Utility.
- **Topology & Dynamic Manifolds (TOPOLOGY)**: Hyperspherical embeddings on $S^{d-1}$ updated via online streaming Fréchet centroid accumulators ($O(d)$ extrinsic normalization and intrinsic Riemannian SLERP/iFME). TOC boundary maintenance, fanout limits ($\le 64$), and bisecting spherical 2-means clustering with drift detection.
- **Silicon-Native Sparsity & Hebbian Dynamics (SPARSITY)**: Biologically grounded dynamical energy decay (Ebbinghaus forgetting + Bahrick permastore), activity-dependent synaptogenesis, and Spine-preserving structural apoptosis. Dual-tier LSM-CSR representation and SIMD int8 dot products (AVX-512 VNNI / ARM NEON).
- **Reasoning Retrieval Lane (RETRIEVAL)**: Dual-tier SLA architecture:
  - Tier 1–3 Interactive Hot Path: Sub-50ms P95 latency with BM25 + int8 dense vector search + Push-based Personalized PageRank (Andersen-Chung-Lang algorithm, $O(1/(\alpha\epsilon))$ local complexity) over CSR graphs. $0 cloud API spend (`CAP-D006`).
  - Tier 4 Reasoning-Expanded Path: Local SLM (3B–14B) reasoning adapters executing Hypothetical Document Embeddings (HyDE) and DAG query decomposition ($200\text{ms} - 800\text{ms}$ SLA, $0 external spend). Calibrated abstention ($\ge 99\%$ accuracy) via Split Conformal Prediction and Semantic Entropy over bidirectional NLI equivalence classes.
- **Systems Scale Infrastructure (SYSTEMS)**: 1M–10M document scale on commodity workstation hardware (16GB RAM). SQLite WAL with contentless external FTS5, Windows Epoch-Based Reclamation (EBR) / RCU lock-free concurrency, and separate storage budgets complying with `CAP-D010` (Spine $\le 1.6\times$, Total-Hot $\le 3.0\times$). Rust/SIMD C ABI kernel extraction roadmap.

---

## Feature Inventory
Every feature from the Phase 0 Survey is cataloged below with its assigned milestone and source:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Event Segmentation Theory (EST) Ingestion | Dynamic boundary detection via Riemannian curvature $\kappa(t)$ on $S^{d-1}$ and Bayesian surprise $S_{\text{Bayes}}(t)$ at $>1,200\text{ docs/sec}$ | M1 | R1, Survey-2 |
| 2 | Asynchronous Sleep-Phase Dreaming | Background consolidation over bounded changed neighborhoods $\mathcal{N}_\delta(\Delta V)$ via graph Dirichlet Laplacian diffusion ($O(1)$ bound) | M1 | R1, Survey-2 |
| 3 | Contradiction Detection Engine | Logical, temporal (Allen interval algebra), and factual ($E^-$ inhibitory edges) contradiction detection and resolution | M1 | R1, Survey-2 |
| 4 | L1–L3 Holarchy & Schema Induction | Arthur Koestler holonic model (L0 episodic atoms, L1 holons, L2 TOC partitions, L3 schemas) via Cobweb CU and Formal Concept Analysis | M1 | R1, Survey-2 |
| 5 | Dynamic Fréchet Centroids on $S^{d-1}$ | Streaming $O(d)$ updates ($<100\text{ ns}$ per point) via extrinsic accumulator normalization and intrinsic Riemannian SLERP / iFME | M2 | R1, Survey-2 |
| 6 | TOC Partitioning & Boundary Maintenance | Bisecting spherical 2-means, fanout bounds ($\le 64$), `DIVERSE_OVERFLOW` deadlock isolation, and hyperspherical drift detection | M2 | R1, Survey-2 |
| 7 | Silicon-Native Sparsity & Hebbian Dynamics | Dynamical energy decay (Ebbinghaus forgetting + Bahrick permastore), activity-dependent synaptogenesis, and Spine-preserving structural apoptosis | M2 | R1, Survey-2 |
| 8 | Compressed Sparse Row (CSR) Graph Optimizations | Dual-tier LSM-CSR memory-mapped graph storage, int8 quantized vector representations, and SIMD dot products | M2 | R1, R2, Survey-2 |
| 9 | Tier 4 Reasoning Adapters (HyDE & Decomposition) | Local SLM (3B–14B) query adapters for BRIGHT benchmark, hypothetical document generation, and DAG sub-query decomposition | M3 | R3, Survey-3 |
| 10 | Sub-50ms Multi-Hop Graph Traversal (Push-PPR) | Andersen-Chung-Lang forward push Personalized PageRank on CSR graphs with $O(1/(\alpha\epsilon))$ local complexity (<5ms wall time) | M3 | R3, Survey-3 |
| 11 | Calibrated Abstention & Zero-Hallucination | Split Conformal Prediction + Semantic Entropy over DeBERTa NLI equivalence classes ensuring $\ge 99\%$ abstention accuracy on unanswerable queries | M3 | R3, Survey-3 |
| 12 | SOTA Literature Synthesis & Comparative Analysis | Exhaustive comparative matrices and trade-off deconstructions against GraphRAG, HippoRAG, LightRAG, MemGPT/Letta, BGE-M3, and Cognee | M3 | R4, Survey-3 |
| 13 | 1M–10M Document Storage Architecture | SQLite WAL, single-copy contentless external FTS5, leaf page overflow prevention, and 4-number storage model compliance (`CAP-D010`) | M4 | R2, Survey-1,3 |
| 14 | Windows Epoch RCU Concurrency Model | Epoch-Based Reclamation (EBR) with generation directories, single-row pointer swaps, reader leases, and deferred unlinking for lock-free reads | M4 | R2, Survey-1,3 |
| 15 | Rust/SIMD Kernel Extraction Roadmap | C ABI and Rust FFI extraction plan for AVX-512/NEON int8 dot products, CSR Push-PPR, and Fréchet updates | M4 | R2, Survey-3 |
| 16 | Adversarial Failure Modes & Risk Analysis | Complete risk analyses for topological drift, memory thrashing, hallucinated associations, and write contention across all RFCs | M4 | AC, Survey-1,2,3 |
| 17 | Comprehensive Cross-RFC Review & Forensic Audit | Verification of mathematical completeness, 100% Spine rebuildability, CAP compliance, and zero-violation integrity audit | M5 | AC, Orchestrator |

---

## Milestones

| # | Milestone Name | Scope & Deliverables | Dependencies | Status |
|---|----------------|----------------------|--------------|--------|
| M1 | RFC-001 Cognitive Consolidation | Author `docs/program/research/architecture_v2/RFC-001-COGNITIVE-CONSOLIDATION.md` covering Features 1, 2, 3, 4 | Survey Complete | DELIVERED (1,150 lines, 77.7 KB) |
| M2 | RFC-002 Topology and Sparsity | Author `docs/program/research/architecture_v2/RFC-002-TOPOLOGY-AND-SPARSITY.md` covering Features 5, 6, 7, 8 | Survey Complete | DELIVERED (1,086 lines, 76.8 KB) |
| M3 | RFC-003 Reasoning Retrieval | Author `docs/program/research/architecture_v2/RFC-003-REASONING-RETRIEVAL.md` covering Features 9, 10, 11, 12 | Survey Complete | DELIVERED (1,176 lines, 90.2 KB) |
| M4 | RFC-004 Systems Scale Blueprint | Author `docs/program/research/architecture_v2/RFC-004-SYSTEMS-SCALE-BLUEPRINT.md` covering Features 13, 14, 15, 16 | Survey Complete | DELIVERED (1,102 lines, 75.6 KB) |
| M5 | Final Cross-RFC Verification & Forensic Audit | Full cross-document verification, invariant audit, and completion reporting | M1, M2, M3, M4 | IN_PROGRESS (reviewer_1, reviewer_2, challenger_1, challenger_2, auditor_1) |

---

## Interface Contracts

### 1. Spine (Core) ↔ Cognitive Substrate Projections
- **Canonical Input**: Spine `events` table (event-sourced log) and `atom` table (raw text slices with SHA-256 byte anchors).
- **Projection Contract**: All projections (`holons`, `toc`, `affinity_edges`, `derived_nodes`, `proposals`) must declare `projection_run_id`, `spine_event_watermark`, and reproducibility class.
- **Rebuild Invariant**: Dropping all projection tables and replaying from `events` watermark must reconstruct equivalent topological and semantic state bit-for-bit or within declared stochastic tolerance bounds (`CAP-D004`, `CAP-D005`).

### 2. Cognitive Consolidation (RFC-001) ↔ Topology & Sparsity (RFC-002)
- **Neighborhood Diffusion Contract**: Sleep-phase engine passes bounded changed node set $\Delta V$ ($|\Delta V| \le 512$) to topology manager.
- **Centroid Update Contract**: Streaming updates use extrinsic accumulator $\mathbf{A} \leftarrow \mathbf{A} + \mathbf{v}_{\text{new}} - \mathbf{v}_{\text{old}}$, $\mathbf{c} \leftarrow \mathbf{A} / \|\mathbf{A}\|_2$. If curvature drift $\Delta \theta > \theta_{\text{threshold}}$, trigger local bisecting spherical 2-means split.
- **Inhibitory Edge Injection**: Contradiction detection engine outputs signed directed edges $(u, v, w, \text{sign})$ where $\text{sign} \in \{+1, -1\}$ to CSR adjacency structure.

### 3. Topology & Sparsity (RFC-002) ↔ Reasoning Retrieval (RFC-003)
- **CSR Graph Representation**: Topology compiles into two binary arrays: `row_offsets` (uint32, size $|V|+1$) and `col_indices` / `weights` (uint32 / float16 or int8, size $|E|$).
- **Traversal Invocation**: Retrieval executes Push-PPR over CSR graph using start seeds from lexical/dense stage, residual threshold $\epsilon = 10^{-4}$, and teleport probability $\alpha = 0.15$. Returns activated node IDs and scores in $\le 5\text{ms}$.

### 4. Reasoning Retrieval (RFC-003) ↔ Systems Scale (RFC-004)
- **Tier 4 Adapter Contract**: Retrieval pipeline checks query complexity classifier. If reasoning score $> \tau_{\text{reason}}$, dispatch local SLM HyDE / DAG decomposition within $800\text{ms}$ budget. If score $\le \tau_{\text{reason}}$, execute sub-50ms interactive hot path.
- **Abstention Contract**: If conformal non-conformity score exceeds calibrated threshold $\hat{q}$, return structured `CalibratedAbstentionResult` with confidence interval, avoiding hallucinations (`CAP-D011`).

### 5. Storage & Concurrency (RFC-004) ↔ All Subsystems
- **Epoch RCU Contract**: Reader processes acquire lease in `active_reader_leases` pointing to current `active_generation`. Background indexing writes new generation `gen_{epoch+1}_{timestamp}/`, updates single-row pointer, and defers unlinking old files by 120s grace period.
- **Storage Budget Enforcement**: 
  - Durable Spine: $\le 1.6\times$ raw text.
  - Retrieval-Hot (FTS5): $\le 0.8\times$ raw text.
  - Cortex-Hot (int8 vectors + CSR): $\le 0.6\times$ raw text.
  - Total-Hot multiplier: $\le 3.0\times$ raw text (`CAP-D010`).

---

## Code & Artifact Layout

```
docs/program/research/architecture_v2/
├── RFC-001-COGNITIVE-CONSOLIDATION.md   # Sleep dreaming, contradiction detection, L3 schema induction
├── RFC-002-TOPOLOGY-AND-SPARSITY.md       # Dynamic Fréchet centroids, boundary maintenance, CSR graph
├── RFC-003-REASONING-RETRIEVAL.md         # Tier 4 adapters, HyDE, Push-PPR multi-hop, calibrated abstention
└── RFC-004-SYSTEMS-SCALE-BLUEPRINT.md     # 1M–10M storage models, Epoch RCU, SIMD/Rust kernel extraction
```
