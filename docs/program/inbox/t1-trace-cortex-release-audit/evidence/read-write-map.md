# Read/Write Map — Trace Cortex Projections, Lifecycle, and Temporal Truth

> **Task ID:** T1  
> **Component:** Trace V2  
> **Status:** Static Code & Schema Audit Finding (Read-Only)  
> **Governing Invariants:** Invariant 1 (Truth vs Projection), Invariant 2 (Candidate Isolation), Invariant 5 (Graph/Semantic Boundaries)

---

## 1. Executive Summary

This audit maps every derived projection and storage structure in the Trace V2 codebase across SQLite (`SqliteEventStore`) and PostgreSQL (`PostgresEventStore`), documenting write paths, read paths, candidate scoping, active selection, historical time handling, failure behavior, retention, and observed isolation gaps.

### Core Architectural Principle
- **Canonical Spine Truth:** `trace_events`, `trace_nodes`, `trace_node_versions`, `trace_edge_versions` (structural & trusted evidence), `trace_evidence_anchors`, `trace_attachments`, `trace_ingestions`.
- **Rebuildable Cortex Projections:** Hierarchy summaries (`trace_projection_objects`), hierarchy topology (`trace_projection_memberships`), non-factual soft bridges (`trace_affinity_edges`), query energy biases (`trace_activation_priors`), vector embeddings (`trace_dense_vectors`, Qdrant), lexical indices (OpenSearch).

---

## 2. Comprehensive Read/Write Matrix

| Structure | Storage / Adapter | Candidate ID | Active Selector | Policy Selector | Historical Selector (`as_of`) | Failure Behavior | Retention / Lifecycle | Verifier Test Needed |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Hierarchy** | `trace_projection_runs`<br>`trace_projection_objects`<br>`trace_projection_memberships` | `projection_run_id` (UUID) in `queued`/`running` status | `effective_projection_run(workspace_id, 'hierarchy')` -> selects latest `status='active'` | Pinned `policy_revision` from active `trace_cognitive_policy_versions` | **Gap:** `as_of_event` parameter in `hierarchy_frontier` is ignored; resolves only against latest active run | Status transitions to `failed` with `failure_detail`; objects remain un-activated | Superseded runs set to `status='superseded'`; `prior_projection_run_id` links delta snapshot lineage | Candidate isolation check; historical run resolution check |
| **Affinity** | `trace_affinity_edges`<br>`trace_affinity_rejections` | **Gap:** None in primary key. `UNIQUE(workspace_id, pair_key)`. `projection_run_id` is optional column | **Gap:** `affinity_neighbors` selects `status='active' AND expires_at > NOW()`. Does **not** filter by active release or run | Degree cap per endpoint (`degree_cap` default 16); TTL expiry; rejection ledger blocks upsert | **Gap:** None. Ignores `as_of_event`; filters by wall-clock `expires_at > NOW()` | **Gap:** Un-isolated. Edges written during candidate build remain `status='active'` if run fails | Mutations overwrite in-place; invalidation sets `status='stale'`; rejections set `status='rejected'` | **R-01 Leakage Check:** Candidate affinity edge visibility before release activation |
| **Activation Priors** | `trace_activation_priors` | **Gap:** None. `UNIQUE(workspace_id, atom_version_id, prior_kind)` | **Gap:** `activation_priors` selects all non-expired priors for workspace | Score clamp `[-1.0, 1.0]`; allowed kinds `pin`, `recency`, `feedback`, `suppression`, `co_retrieval` | **Gap:** None. Ignores `as_of_event` | **Gap:** Un-isolated. Immediate in-place upsert | Expiry via `expires_at`; in-place overwrite on conflict | **R-01 Leakage Check:** Prior modification visible immediately to ongoing queries |
| **Lexical Index** | OpenSearch (`OpenSearchLexicalIndex`) / BM25 fallback | Target `index_revision` string (e.g. `rev-20260819-01`) | Active OpenSearch alias / `TRACE_INDEX_REVISION` | Rollout state in `trace_index_revisions` | Passes `as_of_event` to search filter on `created_event_offset <= as_of_event` | Parity verification failure raises `ProjectionRevisionError`; alias not switched | Old physical indices retained until explicit retirement | Parity verification & alias switch atomicity test |
| **Dense Vectors** | Qdrant (`QdrantDenseIndex`) / `trace_dense_vectors` | Target `index_revision` string / collection | Active collection alias / `TRACE_INDEX_REVISION` | Embedding model version & dimension recorded in registry | Passes `as_of_event` to search filter | Parity check failure aborts activation; candidate collection unaliased | Historical vector rows / collections retained | Dimension & count parity verification test |
| **Hot Inbox** | `trace_hot_inbox` | `atom_version_id` with `visible_from_event` offset | Filtered by `visible_from_event <= as_of_event` & unindexed state | Visibility scope & facet match | Filtered by `visible_from_event <= as_of_event` | Ingestion failure halts atom creation; hot row not committed | Pruned during `reconcile_hot_inbox` once external indexing is confirmed | Zero-lag hot read & post-indexing drain verification |
| **Legacy Hierarchy** | `trace_nodes` (facet `'hierarchy'`)<br>`trace_edge_versions` (`CHILD_OF`, `CONTAINS`) | Canonical `node_id` & `edge_id` | Read as fallback when Cortex projection run is absent | Global relation rules in `ALLOWED_RELATIONS` | Filtered by `ev.created_event_offset <= as_of_event` | Event append failure rolls back transaction | Immutable Spine event history | Migration / deprecation check: ensure Cortex active runs supersede legacy |
| **Evidence Bundle** | `trace_evidence_bundles` | `evidence_bundle_id` (UUID) | Direct lookup by bundle ID | Tenant RLS & visibility policy | Records `temporal_status: "as_of" \| "current"` | Read failure returns insufficient evidence | Persisted indefinitely as audit evidence | Evidence anchor recovery & active release ID attribution test |

---

## 3. Subsystem Breakdown & Observed Gaps

### 3.1 Hierarchy Projection Subsystem
- **Current Writer Flow:**
  1. `create_projection_run(workspace_id, projection_kind='hierarchy', revision=...)` inserts a run with `status='queued'` into `trace_projection_runs`.
  2. `write_projection_objects(projection_run_id, objects, memberships)` asserts acyclicity of containment memberships, validates source atom coverage, and inserts into `trace_projection_objects` and `trace_projection_memberships`.
  3. `activate_projection_run(projection_run_id)` sets prior active runs to `status='superseded'` and marks the target run `status='active'`.
- **Observed Strengths:** Strong structural validation (containment acyclicity check), clean candidate staging of objects/memberships, delta snapshot carry-forward mechanism (`test_hierarchy_delta_carries_forward_the_active_snapshot`).
- **Observed Gap:** In `hierarchy_frontier(workspace_id, query, as_of_event=...)`, the active run is resolved via `effective_projection_run(workspace_id, 'hierarchy')` which selects `status='active' ORDER BY activated_event_offset DESC LIMIT 1`. The `as_of_event` parameter is not used to select the historically active run, so historical queries see current hierarchy objects.

### 3.2 Affinity Graph Subsystem
- **Current Writer Flow:**
  - `put_affinity_edge(workspace_id, source_atom_version_id, target_atom_version_id, score, signal, expires_at, projection_run_id, degree_cap)` enforces canonical pair ordering (`left < right`), endpoint validation, rejection checking, degree capping, and executes an `INSERT ... ON CONFLICT(workspace_id, pair_key) DO UPDATE SET status='active'`.
- **Observed Critical Gap (Risk R-01):**
  - Table constraint is `UNIQUE(workspace_id, pair_key)`.
  - When a background job or candidate build writes an affinity edge, it is immediately written with `status='active'`.
  - `affinity_neighbors(workspace_id, atom_version_ids)` queries `WHERE workspace_id=%s AND status='active' AND expires_at > NOW()`. It does **not** filter on `projection_run_id` or active Cortex Release.
  - **Result:** Candidate affinity edges leak into ordinary retrieval queries before candidate validation or release activation. Overwriting an edge modifies active release behavior in flight.

### 3.3 Activation Priors Subsystem
- **Current Writer Flow:**
  - `upsert_activation_prior(workspace_id, atom_version_id, prior_kind, score, provenance, expires_at)` checks score bounds `[-1, 1]`, allowed kind, and executes `INSERT ... ON CONFLICT(workspace_id, atom_version_id, prior_kind) DO UPDATE`.
- **Observed Critical Gap (Risk R-01):**
  - Table has no release or run scoping (`UNIQUE(workspace_id, atom_version_id, prior_kind)`).
  - Priors are updated live. Any query reading priors immediately consumes un-validated changes.

### 3.4 Lexical and Dense Index Projection Subsystem
- **Current Writer Flow:**
  - Controlled by `RevisionedProjectionController`.
  - Reindex jobs prepare an immutable revision target (`prepare`), populate index rows, verify document count parity (`verify`), and switch aliases (`activate`).
- **Observed Gap:**
  - Lexical and Dense index revisions activate independently of Cortex hierarchy and affinity runs. There is no single atomic Cortex Release transaction spanning both vector/lexical indexes and relational projection tables.

### 3.5 Evidence Bundle Attribution
- **Current Structure:**
  - Bundles record query parameters, results, channel scores (`lexical_bm25`, `dense`, `rrf`, `rerank`, `graph_ppr`, `hierarchy`, `affinity`, `activation`, `schema`), graph paths, and evidence anchor IDs.
- **Observed Gap:**
  - The evidence bundle does not record `active_cortex_release_id`, component revision digests, or policy snapshot hashes in the bundle record, limiting downstream auditability.

---

## 4. Required Verifier Test Matrix (Input for V1b)

1. **Test T1-V-01 (Candidate Affinity Leakage):** Write candidate affinity edges in an un-activated projection run; verify they are completely invisible to `affinity_neighbors` and `HybridRetrievalEngine._activation_scores` until release activation.
2. **Test T1-V-02 (Candidate Prior Isolation):** Write candidate activation priors; verify normal queries cannot observe or apply them.
3. **Test T1-V-03 (Failed Candidate Containment):** Simulate a failed candidate build; verify zero orphaned or leaked rows appear in active retrieval.
4. **Test T1-V-04 (Atomic Multi-Component Rollback):** Activate Release R2, then roll back to Release R1; verify that hierarchy, affinity, priors, lexical alias, and dense alias revert simultaneously.
5. **Test T1-V-05 (Historical Projection as-of Resolution):** Query with `as_of_event = E`; verify that retrieval resolves the Cortex Release active at event offset `E`, not the current release.
