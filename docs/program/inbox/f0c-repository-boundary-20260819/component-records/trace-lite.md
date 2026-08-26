# F0c Trace-Lite Component Record

> **Status:** Current observed record as of 2026-08-19.  
> **Captured by:** Trace-Lite Foundation Engineer (read-only boundary capture).  
> **Component:** Trace-Lite Beta Reference Implementation  
> **Canonical Root:** `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite`  

---

## 1. Repository & Git Identity

- **Canonical Root:** `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite`
- **Git Commit:** `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`
- **Branch:** `main` (up to date with `origin/main`)
- **Remote:** `origin git@github.com:Anshul48/trace-lite.git`
- **Commit Subject:** `refactor: clean up architecture docs, lattice fusion, and forest pending queues`
- **Commit Date:** 2026-08-19
- **Working Tree Cleanliness:** Clean of tracked modifications (0 tracked modified files). 11 untracked documentation and protocol files present.
- **Stale Base Disposition:** Any prior handoffs citing older Trace-Lite base `63bb3cb` are formally marked **STALE** and must be re-anchored to `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`.

---

## 2. Working State & Protected User Paths

### Tracked Modifications
- **Count:** 0 files
- **Diff:** None (`git diff --stat` returns empty)

### Untracked Path Inventory (11 files — All Protected)
All untracked files in the Trace-Lite workspace represent valid local documentation, protocol templates, and registry definitions:

| Path | Classification | State | Protection Rationale |
| --- | --- | --- | --- |
| `benchmarks/protocols/README.md` | `documentation` | untracked | Benchmark protocol documentation. |
| `benchmarks/protocols/templates/GATE_100K_REPORT_TEMPLATE.md` | `documentation` | untracked | 100K gate report protocol template. |
| `benchmarks/protocols/templates/QUERY_CLASS_PROTOCOL_TEMPLATE.md` | `documentation` | untracked | Query class protocol template. |
| `benchmarks/protocols/templates/RELEASE_MANIFEST_TEMPLATE.yaml` | `documentation` | untracked | Release manifest schema template. |
| `benchmarks/registry/README.md` | `documentation` | untracked | Benchmark dataset registry overview. |
| `benchmarks/registry/templates/DATASET_MANIFEST_TEMPLATE.json` | `documentation` | untracked | Dataset manifest template. |
| `benchmarks/registry/templates/DATASET_RECORD_TEMPLATE.md` | `documentation` | untracked | Dataset admission record template. |
| `docs/program/AGENT_CONTEXT_MAP.md` | `documentation` | untracked | Local agent context map referencing canonical program pack. |
| `docs/program/BETA_WORKSTREAM.md` | `documentation` | untracked | Trace-Lite Beta workstream brief. |
| `docs/program/PROGRAM_REFERENCE.md` | `documentation` | untracked | Local pointer to canonical Trace program pack. |
| `docs/program/README.md` | `documentation` | untracked | Trace-Lite local program documentation index. |

- **Untracked File List SHA256:** `793075dc20d2660da284b606fa8acffb50e59acb921e2f28652dc13b302eec04`

### Protection Policy
These 11 untracked files are protected user assets. They must never be deleted, cleaned, stashed, reset, overwritten, or committed during program operations.

---

## 3. Projection, Query, and Graph Anchors

Trace-Lite Beta separates canonical Spine truth from rebuildable Cortex projections. The key code surfaces and architectural anchors are:

### A. Canonical Spine (Truth & Durability)
- **Data Models:** [`src/trace_lite/spine/models.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/models.py)
  - `SourceArtifact`: Immutable original document metadata, raw text, and hash.
  - `Atom`: Atomic, immutable chunk with exact `char_start`, `char_end` offsets, `content_hash`, and sequential index.
  - `AtomLink`: Explicit relationships between atoms (e.g. sequence, citation).
- **Spine Store:** [`src/trace_lite/spine/store.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/store.py)
  - SQLite tables: `source_artifacts`, `atoms`, `atom_links`, and FTS5 full-text index `atoms_fts`.
- **Atomizer:** [`src/trace_lite/spine/atomizer.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/spine/atomizer.py)
  - Deterministic Markdown and code atomization preserving exact character boundaries.
- **Pending Capture Queue:** [`src/trace_lite/cortex/forest.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/forest.py#L133-L142)
  - Table `pending_source_atoms`: Ensures raw captures are durably persisted in SQLite before any LLM routing or indexing attempt.

### B. Cortex Projections (Derived & Rebuildable Structures)
- **Build Manifest:** [`src/trace_lite/cortex/manifest.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/manifest.py)
  - `IndexBuildManifest`: Tracks `build_id`, `state` (`building`, `validated`, `active`, `failed`, `retained`), `source_atom_count`, `tree_count`, `node_count`, `vector_count`, and summary quality metrics (`valid`, `fallback`, `retry`, `passthrough`).
- **Forest Index Store:** [`src/trace_lite/cortex/forest.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/forest.py)
  - Backed by `cortex.sqlite3`.
  - Tables: `trees`, `tree_nodes`, `pending_assignments`, `pending_source_atoms`, `index_builds`, `index_state`, and `graph_edges`.
  - Manifest management: `get_index_build()`, `get_active_build()`, `update_index_build()`, `activate_index_build()`.
- **Vector Store:** [`src/trace_lite/cortex/vector_store.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/vector_store.py)
  - Supports LanceDB (`LanceDBStore`) with versioned collection builds (`begin_build`, `activate_collection`) and fallback SQLite vector storage.
- **Clustering & Energy:** [`src/trace_lite/cortex/clustering.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/clustering.py) & [`src/trace_lite/cortex/energy.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/cortex/energy.py)
  - Gaussian Mixture Model / spherical k-means clustering and hierarchical energy-based thresholding.

### C. Build & Routing Engines
- **Forest Router:** [`src/trace_lite/engines/router.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/router.py)
  - Side-effect-free staged routing: Assigns pending atoms to candidate trees without modifying active Cortex state.
- **RAPTOR Hierarchy Builder:** [`src/trace_lite/engines/raptor.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/raptor.py)
  - Builds multi-level summary trees (`RaptorBuild`) with LLM summary generation, enforcing strict summary validation rules (`valid`, `retry`, `fallback`, `passthrough`).
- **Database Orchestrator:** [`src/trace_lite/db.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/db.py#L750-L920)
  - `TraceDB.build_index()`: Coordinates the complete build lifecycle: pending atom staging $\to$ clustering $\to$ summary generation $\to$ vector construction $\to$ pre-activation validation $\to$ atomic handover.

### D. Graph & Query Engines
- **Graph Engine:** [`src/trace_lite/engines/graph.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/graph.py)
  - `GraphActivationEngine`: Computes Personalized PageRank (PPR) power-iteration over query-activated seed nodes.
  - Edge generators: `generate_sequential_edges` (`NEXT`/`PREV`), `generate_hierarchical_edges` (`PARENT_OF`/`CHILD_OF`), `generate_co_occurrence_edges` (`CO_OCCURS`).
  - *Observed Scaling Constraint:* `generate_co_occurrence_edges` (lines 198–205) performs an all-pairs combination for shared terms. High-degree scaling and budget policies belong to decision-gated packet **TL2** (under **P-002**).
- **LATTICE Traversal & Hybrid Query:** [`src/trace_lite/engines/lattice.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/lattice.py)
  - Dynamic Quad-Channel retrieval:
    1. *Path A:* Top-down LLM-guided tree navigation (LATTICE).
    2. *Path B:* Flat dense vector search over leaf nodes (`filter_expr="node_type = 'leaf'"`).
    3. *Path C:* BM25 lexical search over Spine FTS5 (`search_lexical`).
    4. *Path D:* 3-Tier Gated PPR Graph Activation spreading energy from seed hits across `graph_edges`.
  - Output: [`QueryResult`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/lattice.py#L27-L35) containing anchored [`EvidenceItem`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/lattice.py#L15-L24) records with exact char offsets, content hashes, and channel scores.

---

## 4. Current Lifecycle Observations & Gaps for L1 Preparation

Static audit of the current Trace-Lite codebase reveals the following candidate/active lifecycle state:

| Structure | Current Writer | Candidate Isolation State | Active Selector | Normal Read Filter | Observed Lifecycle Gaps for L1 |
| --- | --- | --- | --- | --- | --- |
| **Lexical Index** | `SpineStore` | N/A (Spine is append-only source) | N/A | None (indexes all atoms) | Lexical index is on Spine atoms; no build scoping. |
| **Vector Index** | `LanceDBStore` | `begin_build(build_id)` stages to `cortex_candidate_<build_id>` | `activate_collection` pointer | Queries target active collection | Isolated during build; fallback SQLite vector store lacks full multi-collection support. |
| **Forest Trees & Nodes** | `ForestIndex` | In-memory `RaptorBuild` before activation | `activate_index_build` deletes old rows and bulk-inserts new | Reads from `trees` and `tree_nodes` | In-memory candidate isolation works, but destructive replacement prevents instant pointer rollback. |
| **Graph Edges** | `ForestIndex` / `db.py` | Written via `store_edges` during activation | None (unversioned table) | `get_neighbor_edges` queries all rows | **Critical Gap:** `graph_edges` table has no `build_id` column; stale edges from prior builds survive indefinitely. |
| **Build Manifest** | `ForestIndex` | `index_builds` row (`building` $\to$ `validated`) | `index_state.active_build_id` | `get_active_build()` | Manifest state machine is well-defined; needs fail-closed binding to query engine. |

### Specific Tasks for L1 Preparation:
1. **Graph Edge Release Scoping:** Add release/build identity to `graph_edges` or ensure atomic replacement/pruning of stale edges during activation.
2. **Non-Destructive Active Selection / Rollback:** Ensure prior validated releases can be rolled back to by pointer without data loss.
3. **Query Engine Release Binding:** Ensure `LatticeEngine` verifies active release health and fails closed when active build is missing or unvalidated.

---

## 5. Benchmark Integration & Boundary Policy

### In-Repository Surfaces:
- [`src/trace_lite/engines/benchmark.py`](file:///C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace-lite/src/trace_lite/engines/benchmark.py): Internal benchmark execution engine and manifest loader.
- `benchmarks/` directory: Internal benchmark adapters, baselines, and test fixtures.

### Boundary with Moved `trace-bench`:
- `trace-bench` (`C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench`) is the moved, multi-adapter evaluation suite.
- Under **P-008**, `trace-bench` is designated as the sole canonical certification runner.
- The in-repo `src/trace_lite/engines/benchmark.py` and `benchmarks/` are retained strictly for internal unit/regression testing (e.g. `tests/test_engines.py`).
- Static inspection shows `src/trace_lite/engines/benchmark.py` contains mock defaults and fail-open paths. These are strictly forbidden for certification runs.

---

## 6. Test Suite & Entry Points

The Trace-Lite test suite consists of 22 test files under `tests/`:

- **Lifecycle & Build Hardening:**
  - `tests/test_cortex.py`: Build manifest lifecycle, vector store isolation, summary quality accounting.
  - `tests/test_fail_closed_indexing.py`: Preflight failure handling, missing provider fail-closed validation.
  - `tests/test_index_hardening.py`: Re-indexing, corrupted index recovery, and validation checks.
  - `tests/test_durable_consolidation.py`: Spine persistence, pending queue durability across crashes.
- **Graph & Retrieval Tests:**
  - `tests/test_graph.py`: Sequential, hierarchical, and co-occurrence edge generation; PPR power-iteration convergence.
  - `tests/test_trust_boundary.py`: Leaf vs. summary vector isolation; insufficient evidence gating.
  - `tests/test_engines.py`: Router, RAPTOR, and Lattice engine end-to-end integration.
- **Unit & Preflight Tests:**
  - `tests/test_spine.py`, `tests/test_providers.py`, `tests/test_provider_preflight.py`, `tests/test_ollama_preflight.py`, `tests/test_projects.py`, `tests/test_cli_modernization.py`, `tests/test_visualizer.py`.

---

## 7. Safe Worktree-Base Recommendation

### Safe Base:
- **Base Commit:** `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1` on `main`.
- **Reason:** The repository is clean of tracked modifications. The 11 untracked documentation files remain protected in the working tree.

### Worktree Creation Command for Mutable Tasks (L1):
```powershell
git -C "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite" worktree add -b l1-lifecycle-20260819 ..\trace-lite-l1 fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1
```

### Allowed Path Scope for L1:
- `src/trace_lite/cortex/manifest.py`
- `src/trace_lite/cortex/forest.py`
- `src/trace_lite/cortex/vector_store.py`
- `src/trace_lite/db.py`
- `src/trace_lite/engines/lattice.py`
- `tests/test_cortex.py`
- `tests/test_fail_closed_indexing.py`
- `tests/test_lifecycle_isolation.py` (new)

### Strictly Forbidden in L1:
- Any modification to `src/trace_lite/engines/graph.py` graph scoring or co-occurrence heuristics (belongs to **TL2** / **P-002**).
- Any revival of Alpha runtime paths (DEC-001).
- Any modifications to canonical Spine models (`src/trace_lite/spine/models.py`).
- Any modifications to Trace or trace-bench codebases.
- Any direct mutation of the user working tree `C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-lite`.
