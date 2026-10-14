# Trace-Lite Architectural Anchors & Lifecycle Evidence

> **Role:** Trace-Lite Foundation Engineer
> **Packet:** F0c (`f0c-repository-boundary-20260819`)
> **Base Identity:** Git Commit `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main`
> **Date:** 2026-08-19

---

## 1. Architectural Surface Inventory

Trace-Lite Beta operates strictly within the canonical boundary defined by the Program Charter (DEC-001 / DEC-002). The table below anchors all key source modules, their primary roles, line references, and their relationship to the foundation program:

| Surface | File Path | Line Range | Role / Responsibility | Foundation Boundary & Program Implication |
| --- | --- | --- | --- | --- |
| **Spine Models** | [`src/trace_lite/spine/models.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/models.py) | L1–120 | `SourceArtifact`, `Atom`, `AtomLink`, `AtomLocation` data classes. | Canonical immutable truth; exact char offsets and SHA256 hashes. Forbidden to mutate in L1. |
| **Spine Store** | [`src/trace_lite/spine/store.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/store.py) | L1–450 | SQLite tables `source_artifacts`, `atoms`, `atom_links`, FTS5 `atoms_fts`. | Append-only source store and lexical search provider. |
| **Atomizer** | [`src/trace_lite/spine/atomizer.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/atomizer.py) | L1–200 | Deterministic Markdown/code parsing into atomic chunks. | Provenance preservation; guarantees exact character boundary fidelity. |
| **Build Manifest** | [`src/trace_lite/cortex/manifest.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/manifest.py) | L1–52 | `IndexBuildManifest`, `BuildState` (`building`, `validated`, `active`, `failed`, `retained`). | Observable derived build lifecycle state machine. |
| **Forest Index** | [`src/trace_lite/cortex/forest.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/forest.py) | L1–909 | SQLite tables `trees`, `tree_nodes`, `pending_assignments`, `pending_source_atoms`, `index_builds`, `index_state`, `graph_edges`. | Central rebuildable Cortex store. Lifecycle isolation scope for L1. |
| **Vector Store** | [`src/trace_lite/cortex/vector_store.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/vector_store.py) | L1–350 | LanceDB / SQLite vector backends with collection versioning. | Collection-level candidate staging (`begin_build` / `activate_collection`). |
| **Forest Router** | [`src/trace_lite/engines/router.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/router.py) | L1–306 | Side-effect-free staged routing of pending atoms into candidate trees. | LLM-guided tree routing without modifying active Cortex state. |
| **RAPTOR Builder** | [`src/trace_lite/engines/raptor.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/raptor.py) | L1–662 | Multi-level summary tree construction (`RaptorBuild`) with strict quality gates. | In-memory candidate hierarchy builder; summary validation. |
| **Graph Engine** | [`src/trace_lite/engines/graph.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/graph.py) | L1–244 | Personalized PageRank power-iteration and edge generators (`NEXT`, `PREV`, `PARENT_OF`, `CHILD_OF`, `CO_OCCURS`). | Graph generation & PPR activation. Co-occurrence scaling belongs to TL2 / P-002. |
| **LATTICE Query** | [`src/trace_lite/engines/lattice.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/lattice.py) | L1–391 | 4-channel hybrid retrieval: Tree LATTICE + Flat Vector + Lexical BM25 + 3-tier gated PPR Graph Activation. | Primary retrieval query engine. Returns anchored `EvidenceItem` bundles. |
| **DB Orchestrator** | [`src/trace_lite/db.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/db.py) | L1–1821 | `TraceDB` coordinator managing Spine, Forest, VectorStore, and Engines. | `build_index` (L750–920) is the central candidate $\to$ validation $\to$ activation workflow. |
| **In-Repo Benchmark** | [`src/trace_lite/engines/benchmark.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/benchmark.py) | L1–695 | Legacy manifest loader, benchmark runner, and rich console reporter. | Non-certifying; fail-open defaults. Internal regression only under P-008. |

---

## 2. Projection & Candidate/Active Lifecycle Map (L1 Baseline)

To prepare for **L1 (Candidate/Active Lifecycle Foundation)**, each derived projection in Trace-Lite is mapped below across writer, candidate staging, active selector, normal read filter, validation, failure, and rollback:

```text
Spine Input (Pinned Atoms)
          │
          ▼
Candidate Release Created (build_id in index_builds: "building")
          │
          ├─► Vector Store: begin_build(build_id) ──► Collection: cortex_candidate_<build_id>
          ├─► Raptor Builder: in-memory candidate ──► RaptorBuild(tree, nodes, vectors)
          └─► Pending Queues: staging ──────────────► pending_assignments, pending_source_atoms
          │
          ▼
Pre-Activation Validation (_validate_vectors, validate_summary, structural checks)
          │
    ┌─────┴────────────────────────┐
    ▼ (Pass)                       ▼ (Fail)
Atomic Activation Handover       Preserve Prior Active Release
- index_state: active_build_id   - index_builds[build_id].state = "failed"
- Forest: trees / tree_nodes     - Retain prior active_build_id
- VectorStore: activate_coll     - Candidates remain un-queryable
- Retain prior build pointer
```

### Detailed Lifecycle Map

| Structure | Current Writer | Candidate Identity | Active Selector | Normal Read Filter | Validation Mechanism | Failure Handling | Retention & Rollback Behavior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Lexical Index** | `SpineStore.store_atoms()` | None (appended directly to Spine SQLite `atoms_fts`) | N/A | None (indexes all stored atoms) | FTS5 integrity check on write | Write transaction rolls back SQLite commit | Spine is append-only; immutable source truth survives across rebuilds. |
| **Vector Index** | `LanceDBStore` / `db.py:855–874` | `cortex_candidate_<build_id>` collection | `LanceDBStore.activate_collection()` pointer | Queries resolve against active collection name | `_validate_vectors()` checks dimensionality, node count, and NaN/Inf values | Failed candidate collection is discarded or left un-promoted | Prior collection remains active; rollback switches active collection pointer. |
| **Forest Hierarchy (Trees & Nodes)** | `ForestIndex.activate_index_build()` | In-memory `RaptorBuild` / `built_trees` / `built_nodes` | `index_state.active_build_id` | Queries read `trees` and `tree_nodes` tables | `validate_index()` checks summary quality, minimum length, parent-child links | Build aborts before `activate_index_build`; prior rows remain | **Gap for L1:** Activation currently deletes existing table rows; true pointer rollback requires snapshot retention or revision tagging. |
| **Graph Edges** | `ForestIndex.store_edges()` in `db.py:885–887` | None (**unversioned**) | None (reads entire `graph_edges` table) | `get_neighbor_edges()` queries `graph_edges` without filter | None pre-activation | Stale edges survive indefinitely | **Critical Gap for L1:** `graph_edges` lacks `build_id` and is never purged during activation; stale edges from prior builds accumulate. |
| **Index Build Manifest** | `ForestIndex.update_index_build()` | `index_builds.build_id` (state: `building`) | `index_state(key='active_build_id')` | `get_active_build()` | Preflight, summary quality accounting, structural validation | Marked `state='failed'` with error string and failure codes | Prior build marked `state='retained'`; manifest history preserved in `index_builds`. |

---

## 3. Graph Engine & Scaling Constraint Analysis

### Observed Mechanics:
- **Seed Activation & Traversal:** [`src/trace_lite/engines/graph.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/graph.py) implements Personalized PageRank using sparse power iteration (`GraphActivationEngine.personalized_pagerank`, L28–67) with damping factor $\alpha = 0.85$, max 20 iterations, and convergence threshold $\epsilon = 10^{-8}$.
- **Edge Types:**
  1. `NEXT` / `PREV` (sequential document ordering, weight 1.0)
  2. `PARENT_OF` / `CHILD_OF` (hierarchical summary $\leftrightarrow$ atom links, weight 0.8–1.0)
  3. `CO_OCCURS` (shared keyword/entity co-occurrence, weight $\min(1.0, \sum 1/\sqrt{\text{freq}})$)

### Identified Scaling Blocker (Risk R-02):
- In `generate_co_occurrence_edges` (L198–205):
  ```python
  for t, aids in informative_terms.items():
      term_weight = 1.0 / (len(aids) ** 0.5)
      aid_list = sorted(aids)
      for i in range(len(aid_list)):
          for j in range(i + 1, len(aid_list)):
              # All-pairs edge combination O(k^2) per term
  ```
- For frequent terms appearing across hundreds of atoms, this generates an $O(k^2)$ edge explosion, leading to superlinear memory and graph construction times.
- **Program Disposition:** This scaling issue is governed under **Risk R-02** and human decision **P-002**. It must NOT be redesigned in L1. L1 focuses strictly on candidate/active lifecycle isolation; bounded degree/DF caps and graph budgets are assigned to **TL2**.

---

## 4. Benchmark Integration & Harness Ownership (P-008)

### Current Situation:
1. **Legacy In-Repository Benchmark:** [`src/trace_lite/engines/benchmark.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/benchmark.py) and `benchmarks/` directory contain local fixtures, manifest parsers, and runner logic.
2. **External Benchmark Component:** `trace-bench` (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) is the relocated, multi-adapter evaluation suite.

### Resolution under P-008:
- `trace-bench` is the designated canonical multi-adapter certification harness for the program.
- In-repo `src/trace_lite/engines/benchmark.py` and `benchmarks/` are demoted to internal regression and unit testing (e.g. `tests/test_engines.py`).
- Static inspection shows `src/trace_lite/engines/benchmark.py` contains mock defaults, flat fallback modes, and swallowed errors. In accordance with Invariant 4 and DEC-009, these fail-open paths are strictly forbidden for certification purposes.

---

## 5. Test Entry Points and Coverage

The 22 test files in `tests/` provide regression baselines for Trace-Lite:

```text
tests/
├── test_cli_aliases.py
├── test_cli_modernization.py
├── test_cortex.py                 <-- Key: Manifest lifecycle & vector store isolation
├── test_dense_canonical_summary.py
├── test_durable_consolidation.py   <-- Key: Spine durability & crash recovery
├── test_engines.py                <-- Key: Router, RAPTOR, Lattice end-to-end
├── test_fail_closed_indexing.py   <-- Key: Fail-closed build validation
├── test_get_models.py
├── test_graph.py                  <-- Key: Edge generation & PPR power-iteration
├── test_index_hardening.py        <-- Key: Index corruption recovery & reindex
├── test_integration.py
├── test_model_warmup_and_build_api.py
├── test_ollama_preflight.py
├── test_projects.py
├── test_provider_preflight.py
├── test_providers.py
├── test_spine.py                  <-- Key: Atomization, FTS5 lexical search
├── test_trust_boundary.py         <-- Key: Leaf vs summary vector isolation
├── test_tui_selectors.py
├── test_visualizer.py
└── test_watcher_and_api.py
```

---

## 6. Safe Worktree & Isolation Recommendation for L1

- **Base Commit:** `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main`.
- **Worktree Preparation Command:**
  ```powershell
  git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" worktree add -b l1-lifecycle-20260819 ..\trace-lite-l1 fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1
  ```
- **Allowed Mutable Path Scope for L1:**
  - `src/trace_lite/cortex/manifest.py`
  - `src/trace_lite/cortex/forest.py`
  - `src/trace_lite/cortex/vector_store.py`
  - `src/trace_lite/db.py`
  - `src/trace_lite/engines/lattice.py`
  - `tests/test_cortex.py`
  - `tests/test_fail_closed_indexing.py`
  - `tests/test_lifecycle_isolation.py` (new)
- **Forbidden Path Scope:**
  - `src/trace_lite/engines/graph.py` (reserved for TL2 / P-002)
  - `src/trace_lite/spine/` (immutable Spine truth)
  - `benchmarks/protocols/`, `benchmarks/registry/`, `docs/program/` (protected user untracked files)
  - Any files in Trace or trace-bench.
