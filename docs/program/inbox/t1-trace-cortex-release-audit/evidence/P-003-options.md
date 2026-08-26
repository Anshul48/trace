# P-003 Options — Unified Trace Cortex Release Schema and Lifecycle

> **Task ID:** T1  
> **Topic:** Decision P-003 Architectural Options  
> **Status:** Design Alternatives for Human Decision (Do NOT unilaterally choose)  
> **Governing Invariants:** Invariant 2 (Candidate Isolation), Invariant 3 (Evidence and Provenance), Invariant 12 (Compatibility and Migration)

---

## 1. Problem Statement & Background

The T1 audit observed that Trace V2 components (hierarchy runs, affinity edges, activation priors, lexical indexes, dense vector collections) currently activate **independently and asynchronously**:
1. `trace_projection_runs` has its own status machine (`queued -> running -> succeeded -> active -> superseded`).
2. `trace_affinity_edges` is written directly with `status='active'` under a global `(workspace_id, pair_key)` unique constraint, leaking un-validated edges to normal queries.
3. `trace_activation_priors` lacks any release or run identity, mutating in place globally.
4. `RevisionedProjectionController` prepares and activates OpenSearch and Qdrant index aliases independently per adapter.

This fragmented lifecycle violates Invariant 2 (Candidate Isolation) and prevents clean single-pointer atomic rollback across the full retrieval stack.

The target architectural contract is:
```text
workspace -> active Cortex Release -> named component revisions -> derived projection rows
```

---

## 2. Architectural Alternatives

### Alternative 1: Full Monolithic Rebuilt Release Bundle

In this model, every Cortex Release is an entirely self-contained, monolithic bundle. Every release rebuilds all derived components from scratch for the given Spine revision watermark.

#### Data Model
- `trace_cortex_releases`: `(release_id PK, workspace_id, spine_event_watermark, status, policy_revision, validation_receipt, created_at, activated_at, superseded_at)`
- All derived tables have `release_id UUID NOT NULL REFERENCES trace_cortex_releases(release_id)`:
  - `trace_projection_objects(projection_object_id PK, release_id FK, ...)`
  - `trace_projection_memberships(projection_membership_id PK, release_id FK, ...)`
  - `trace_affinity_edges(affinity_edge_id PK, workspace_id, release_id FK, left_id, right_id, pair_key, score, ..., UNIQUE(workspace_id, release_id, pair_key))`
  - `trace_activation_priors(activation_prior_id PK, workspace_id, release_id FK, atom_version_id, prior_kind, score, ..., UNIQUE(workspace_id, release_id, atom_version_id, prior_kind))`
  - Dedicated OpenSearch index `atoms_<workspace>_<release_id>` and Qdrant collection `vectors_<workspace>_<release_id>`.

---

### Alternative 2: Release Root with Immutable Component Membership (Carried-Forward Manifest)

In this model, a release root (`trace_cortex_releases`) owns a versioned, immutable manifest of component revisions (`trace_cortex_release_components`). Each component (hierarchy partition, affinity subgraph, prior snapshot, lexical revision, dense revision) is an immutable artifact with its own input checksum, policy fingerprint, and validation status. A new release can carry forward validated components from predecessor releases whose Spine snapshot inputs remain unchanged.

#### Data Model
```sql
-- Release Root
CREATE TABLE trace_cortex_releases (
    release_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    parent_release_id UUID REFERENCES trace_cortex_releases(release_id),
    spine_event_watermark BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned','building','validating','validated','active','superseded','retired','failed')),
    policy_revision TEXT NOT NULL,
    policy_snapshot_hash CHAR(64) NOT NULL,
    code_revision TEXT NOT NULL,
    validation_receipt JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    failure_detail TEXT
);
CREATE INDEX trace_cortex_releases_active 
    ON trace_cortex_releases(workspace_id, status, activated_at DESC);

-- Component Membership Manifest
CREATE TABLE trace_cortex_release_components (
    release_id UUID NOT NULL REFERENCES trace_cortex_releases(release_id) ON DELETE CASCADE,
    component_kind TEXT NOT NULL CHECK (component_kind IN ('hierarchy', 'affinity', 'activation_priors', 'lexical_index', 'dense_index')),
    component_revision TEXT NOT NULL,
    input_checksum CHAR(64) NOT NULL,
    source_watermark BIGINT NOT NULL,
    carried_forward_from_release_id UUID REFERENCES trace_cortex_releases(release_id),
    validation_status TEXT NOT NULL CHECK (validation_status IN ('pending', 'validated', 'failed')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (release_id, component_kind)
);

-- Release-Scoped Derived Tables
-- Affinity: Scoped by release_id (or component_revision)
ALTER TABLE trace_affinity_edges ADD COLUMN release_id UUID REFERENCES trace_cortex_releases(release_id);
-- Unique per (workspace, release, pair)
CREATE UNIQUE INDEX trace_affinity_edges_release_pair 
    ON trace_affinity_edges(workspace_id, release_id, pair_key);

-- Activation Priors: Scoped by release_id
ALTER TABLE trace_activation_priors ADD COLUMN release_id UUID REFERENCES trace_cortex_releases(release_id);
CREATE UNIQUE INDEX trace_activation_priors_release_kind 
    ON trace_activation_priors(workspace_id, release_id, atom_version_id, prior_kind);
```

---

## 3. Tradeoff Comparison Matrix

| Evaluation Dimension | Alternative 1: Full Monolithic Rebuild | Alternative 2: Release Root with Carried-Forward Components |
| :--- | :--- | :--- |
| **1. Multi-Component Atomicity** | **High:** Entire release is constructed in isolation and activated in one SQL transaction. | **High:** Release root activation atomically switches all component pointers in a single transaction. |
| **2. Incremental Build Cost / Latency** | **Prohibitive at Scale:** Rebuilding vectors, full hierarchy, and all affinity pairs for 100K+ atoms on minor edits takes minutes to hours. | **Optimal:** Incremental delta builds only compute modified partitions and carry forward immutable validated components. |
| **3. Rollback Behavior** | **Simple:** Point workspace active release to `prior_release_id`. | **Clean & Flexible:** Point workspace active release to any prior validated release root; external index aliases re-pointed synchronously. |
| **4. External Index Compensation** | Must re-index full corpus into new OpenSearch/Qdrant indices on every release. | Re-uses existing immutable index revisions if document sets are unchanged; creates new index revision only on reindex/schema change. |
| **5. Policy Snapshot Binding** | Bound to monolithic build. | Explicitly checks that carried-forward components match current active `policy_revision` and `policy_snapshot_hash`. |
| **6. Source Watermark Lineage** | Single watermark per release. | Precise component-level watermarks + overall release Spine watermark. |
| **7. Crash & Replay Recovery** | Simple replay from scratch. | Structured replay: rebuilds only missing component deltas. |
| **8. Retention & Pruning** | Bulky: deleting a release deletes all rows; high disk consumption during retention. | Granular: shared component rows can be retained until all referencing releases are retired. |
| **9. Migration Complexity** | Moderate schema change, but high operational cost. | Moderate additive SQL migration; requires backfill to generate initial `bootstrap-v1` release root. |
| **10. Verifier Observability** | Trivial: check `release_id` equality. | Clear: inspect `trace_cortex_release_components` and durable validation receipts. |

---

## 4. Additive Migration Considerations for TR1

To implement the chosen model in TR1 safely without breaking existing data or dirty user snapshots:
1. **Additive Forward-Only Migration (`005_cortex_unified_release_lifecycle.sql`):**
   - Create `trace_cortex_releases` and `trace_cortex_release_components`.
   - Add `release_id UUID` columns to `trace_affinity_edges` and `trace_activation_priors`.
   - Update unique constraints to include `release_id`.
2. **Legacy Backfill Strategy:**
   - Automatically insert a baseline `bootstrap-v0` record in `trace_cortex_releases` with `status='active'`.
   - Backfill existing un-scoped `trace_affinity_edges` and `trace_activation_priors` to reference `bootstrap-v0`.
3. **Active-Read Selector Protocol:**
   - All retrieval operations (`hierarchy_frontier`, `affinity_neighbors`, `activation_priors`, `_lexical_scores`, `_dense_scores`) resolve the active `release_id` via:
     ```sql
     SELECT release_id FROM trace_cortex_releases 
     WHERE workspace_id = :workspace_id AND status = 'active' 
     ORDER BY activated_at DESC LIMIT 1
     ```
   - Queries pass `release_id = :active_release_id` in their `WHERE` clauses.
4. **Durable Validation Receipt Contract:**
   - Before transitioning from `validating` to `validated` (and then `active`), a release must record a structured validation receipt in JSONB:
     ```json
     {
       "structural": {"passed": true, "acyclic": true, "source_coverage_pct": 100.0},
       "provenance": {"passed": true, "unanchored_objects": 0},
       "policy": {"passed": true, "policy_revision": "cognitive-policy-v1", "hash_match": true},
       "parity": {"passed": true, "lexical_parity": true, "dense_parity": true},
       "evaluator_manifest_id": null
     }
     ```
5. **External Index Alias Compensation:**
   - In reindex workflows, index alias swaps must be orchestrated alongside the database release transition:
     `Stage Index -> Verify Parity -> DB Begin -> Update Release Status='active' -> Swap Index Aliases -> DB Commit`.
   - On error or rollback, index aliases are reverted to the prior active release's index revisions.
