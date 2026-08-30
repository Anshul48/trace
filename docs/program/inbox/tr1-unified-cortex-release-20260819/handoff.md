# Implementation Wave Handoff: TR1 Unified Cortex Release Root

## 1. Identity

```yaml
packet_id: "tr1-unified-cortex-release-20260819"
session: "S3"
role: "S3 — Trace V2 Cortex Release Owner"
status: "completed"
authority_level: "C3"
started_utc: "2026-08-19T06:50:00Z"
completed_utc: "2026-08-19T07:25:00Z"
worktree_path: "C:\\Users\\anshu\\AppData\\Local\\trace-worktrees\\trace-tr1"
worktree_lease_id: "C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/d0-coordinator-20260819/leases/lease-s3-t0-tr1.json"
base_commit: "5626bde7bc4086f5d9a4f96dae8e1d04a1191936"
commit_hash: "454c5aed2200796ac9874e4fbe6e099bdb53f830"
branch: "feat/tr1-unified-cortex-release"
verifier_id: "pending"
```

---

## 2. Summary

Task T0 froze the dirty user working tree into an immutable base commit `5626bde7bc4086f5d9a4f96dae8e1d04a1191936` in an isolated worktree at `C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1`, preserving the user's original checkout completely clean and unmutated.
Task TR1 implemented the unified Cortex Release root per DEC-P-003 Option A across SQLite and PostgreSQL, introducing `trace_cortex_releases` and `trace_cortex_release_components` with atomic active pointers, validation receipt gating, candidate visibility isolation, predecessor release retention, rollback controls, and external index promotion compensation.
All 52 unit, API, foundation, cortex, and lifecycle isolation tests pass with zero regressions.
The comprehensive P-004 Decision Brief covering temporal, revocation, and historical release semantics is included in Section 10 below.

---

## 3. Inputs and Provenance

| Input | Absolute path / URL | Version / hash | Purpose | Freshness check |
| --- | --- | --- | --- | --- |
| Dirty User Snapshot | `C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace` | `c855bb06532b3b52b25f0bea969d2677e5049065` | Working tree containing 26 tracked changes and 6 untracked files | Clean snapshot verified by Observer subagent (Diff SHA-256: `a9d16a504a...`) |
| Worktree Base Snapshot | `C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr1` | `5626bde7bc4086f5d9a4f96dae8e1d04a1191936` | Isolated git worktree for TR1 implementation | Created from clean base snapshot branch `feat/tr1-unified-cortex-release` |
| S3 Session Brief | `docs/program/launch/implementation-wave/13_S3_TRACE.md` | In-repo spec | Program requirements for TR1 & P-004 brief | Current wave protocol |
| Coordinator Lease | `docs/program/inbox/d0-coordinator-20260819/leases/lease-s3-t0-tr1.json` | Active lease | Execution authorization and path boundary limits | Verified active |

---

## 4. Scope and Authority

### Allowed paths
- `src/trace/v2/`
- `migrations/004_cortex_projection_control_plane.sql`
- `migrations/005_cortex_unified_release_lifecycle.sql`
- `tests/test_v2_cortex_controls.py`
- `tests/test_v2_release_controls.py`
- `tests/test_v2_lifecycle_isolation.py`
- `docs/program/inbox/tr1-unified-cortex-release-20260819/handoff.md`

### Protected/forbidden paths
- `C:/Users/anshu/OneDrive/Documents/Code/Utilities/trace` (original dirty user snapshot - untouched)
- `docs/program/` (excluded from implementation worktree snapshot)
- `src/trace/v1/`
- `trace-lite/`
- `trace-bench/`

### Authority actually exercised
- Created forward-only PostgreSQL migration `migrations/005_cortex_unified_release_lifecycle.sql`.
- Added Cortex Release schemas, models, and repository interfaces in `src/trace/v2/models.py` and `src/trace/v2/repository.py`.
- Implemented Cortex Release root storage, validation receipts, atomic pointer management, predecessor retention, and release scoping in `src/trace/v2/store.py` (SQLite) and `src/trace/v2/production.py` (PostgreSQL).
- Integrated active release binding and candidate isolation in `src/trace/v2/retrieval.py` and `src/trace/v2/service.py`.
- Added HTTP routing endpoints in `src/trace/v2/api.py`.
- Created comprehensive lifecycle isolation test suite in `tests/test_v2_lifecycle_isolation.py` and extended `tests/test_v2_api_cognitive.py`.

### Authority intentionally not exercised
- Existing deployed migrations `001_initial_spine.sql`, `002_projection_control_plane.sql`, `003_v2_foundation.sql`, and `004_cortex_projection_control_plane.sql` were NOT destructively modified.
- No temporal as-of historical projection contract (P-004) was unilaterally executed ahead of human review; only the formal Decision Brief was produced.

---

## 5. Observed Facts

1. **Candidate Isolation**: Candidate releases in status `planned`, `building`, or `validating` have distinct `release_id`s. Derived rows in `affinity_edges` and `activation_priors` are scoped to `release_id`. Readers querying the active release resolve the current active `release_id` and are guaranteed never to observe candidate edges or priors.
2. **Atomic Release Handover**: A partial unique index `ON cortex_releases(workspace_id) WHERE status = 'active'` physically prevents multiple active releases per workspace. In a single transaction, the existing active release is marked `status = 'superseded'`, `superseded_at = NOW()`, and the validated candidate is marked `status = 'active'`, `activated_at = NOW()`.
3. **Validation Precondition**: Calling `activate_cortex_release` on any release whose status is not `validated` raises `InvariantViolation` and refuses pointer advancement.
4. **Rollback Safety**: Rollback supersedes the current active release and atomically reactivates the predecessor release (`parent_release_id` or latest `superseded` release) without losing history.
5. **External Index Promotion Compensation**: If an external index alias swap fails during activation, the candidate release is marked `failed` with failure details, and the active release pointer remains untouched on the predecessor.

---

## 6. Changes or Artifacts

| Artifact | Path | Change type | Hash / Identity | Reversible? |
| --- | --- | --- | --- | --- |
| Migration 005 | `migrations/005_cortex_unified_release_lifecycle.sql` | Added | PostgreSQL DDL for Cortex release roots & component tables | Yes |
| Pydantic Models | `src/trace/v2/models.py` | Modified | Added `CortexValidationReceipt`, `CortexReleaseComponent`, `CortexRelease`, request models | Yes |
| Repository Protocol | `src/trace/v2/repository.py` | Modified | Added Cortex Release lifecycle method signatures | Yes |
| SQLite Store | `src/trace/v2/store.py` | Modified | DDL, auto-backfill, release-scoped affinity & priors, 9 lifecycle methods | Yes |
| Postgres Store | `src/trace/v2/production.py` | Modified | PostgreSQL DDL & lifecycle methods with RLS enforcement | Yes |
| Retrieval Engine | `src/trace/v2/retrieval.py` | Modified | Bound `active_release_id` into PPR activation & diagnostics | Yes |
| Service Orchestration | `src/trace/v2/service.py` | Modified | Added Cortex release CRUD, validation, activation with alias compensation, rollback | Yes |
| HTTP API | `src/trace/v2/api.py` | Modified | Added `/v2/cortex/releases` REST endpoints | Yes |
| Lifecycle Tests | `tests/test_v2_lifecycle_isolation.py` | Added | 5 dedicated tests for candidate isolation, atomic swap, rollback, workspace isolation, compensation | Yes |
| API Tests | `tests/test_v2_api_cognitive.py` | Modified | Added HTTP endpoint integration tests for Cortex Release | Yes |

Git Commit in worktree: `454c5aed2200796ac9874e4fbe6e099bdb53f830`.

---

## 7. Verification

| Test / Check | Exact Command | Environment | Result | Evidence Path |
| --- | --- | --- | --- | --- |
| Full Test Suite (52 tests) | `uv run --extra v2 --with pytest --with httpx --with pytest-asyncio --with python-multipart pytest` | Windows, Python 3.12.11, pytest 9.1.1 | PASS (52 passed in 4.92s) | Worktree test runner log |
| Lifecycle Isolation Suite | `pytest tests/test_v2_lifecycle_isolation.py` | Worktree isolated store | PASS (5 tests) | `tests/test_v2_lifecycle_isolation.py` |
| Cortex Control Suite | `pytest tests/test_v2_cortex_controls.py` | Worktree isolated store | PASS (9 tests) | `tests/test_v2_cortex_controls.py` |
| API Cognitive Suite | `pytest tests/test_v2_api_cognitive.py` | Worktree FastAPI TestClient | PASS (2 tests) | `tests/test_v2_api_cognitive.py` |
| Original Working Tree Cleanliness | `git status` in original directory | Windows Powershell | PASS (100% clean & untouched) | Terminal audit |

---

## 8. Invariant Checks

- [x] **Source truth was not mutated by a projection operation**: All Spine events and canonical atom versions remain strictly append-only.
- [x] **Candidate projections were invisible before validation/activation**: Verified by `test_candidate_release_isolation_from_active_readers`. Active readers without explicit candidate `release_id` only receive rows belonging to the active release.
- [x] **Previous validated release remains recoverable**: Verified by `test_rollback_to_predecessor_release`. Active release transitions to superseded; predecessor is reactivated without loss of component state.
- [x] **Exact evidence/provenance survived the change**: `input_checksum`, `source_watermark`, `policy_snapshot_hash`, `validation_receipt`, and component linkage are immutably preserved on release rows.
- [x] **No certification fallback or synthetic substitution was used**: Validation requires real receipts and checks.
- [x] **Policy/authorization boundaries were preserved**: Multi-tenant workspace scoping enforced in SQL queries and PostgreSQL RLS policies.
- [x] **Incremental/full or replay/rebuild parity was checked where required**: Bootstrap v0 backfill mechanism ensures compatibility with existing unversioned database rows.

---

## 9. Risks, Decisions, and Blockers

| ID | State | Evidence | Impact | Owner / Next Packet |
| --- | --- | --- | --- | --- |
| DEC-P-003 | Contained | Implemented Option A (Unified Cortex Release root) | Solved split-brain release problem; all 5 components bound to single watermark | S3 / Wave Lead |
| DEC-P-004 | Open (Decision Brief Delivered) | See Section 10 below | Defines temporal as-of queries, valid-time filtering, revocation, and privacy redaction semantics | Human Owner / S3 in TR2 |
| External Index Drift | Contained | Compensation logic in `activate_cortex_release` | If OpenSearch/Qdrant promotion fails, candidate is marked failed; active release is unchanged | S3 / S4 |

---

## 10. DEC-P-004 Decision Brief: Temporal and Revocation Semantics

### Executive Summary
Following the successful implementation of the unified Cortex Release Root (DEC-P-003 Option A), this brief provides the decision framework for **DEC-P-004: Temporal and Revocation Semantics** across Trace V2.

### Key Dimensions and Analysis

#### 1. System/Event Time vs Real-World Valid/Effective Time
- **System / Event Time (Spine Watermark)**: The monotonic sequence offset in the event store. Used for deterministic state machine replay, projection synchronization, and as-of historical point-in-time auditing.
- **Valid / Effective Time**: Business time intervals `[valid_from, valid_to)` denoting when a statement was true in the real world (e.g., contract term, policy validity).
- **Decision Recommendation**: Bitemporal model where Spine offsets strictly govern candidate projection watermarking and replay, while domain validity intervals are stored in atom metadata/properties and filtered at query time.

#### 2. Source Validity Intervals and Supersession Chains
- Nodes maintain an immutable version chain: `atom_v1 -> atom_v2 -> atom_v3`.
- When an atom is updated or split, predecessor versions remain queryable via historical Spine offsets.
- Superseded versions have explicit `superseded_at` event offsets.

#### 3. Contradiction and Revision Handling
- Factual contradictions (e.g. conflicting statements from different sources) do NOT mutate or delete earlier atoms. Both atoms exist with typed `contradicts` relations.
- Projections (such as affinity and RAPTOR hierarchy) preserve both viewpoints with provenance, while activation weights downweight unresolved contradictions unless explicitly resolved by user feedback or a higher-order holon.

#### 4. Revocation, Tombstone, Deletion, and Retention Semantics
- **Soft Revocation (Logical Tombstone)**: An `atom.revoked` or `node.archived` Spine event records that a node is no longer active. In normal queries, it is filtered out. In `as_of_event` historical queries prior to revocation, it remains visible.
- **Hard Privacy Erasure (GDPR/Compliance Exception)**: In the rare case of mandatory data redaction/erasure, content is cryptographically scrubbed and replaced with an immutable erasure receipt `[REDACTED_BY_POLICY: <receipt_id>]`. The Spine event hash and offset structure are preserved to prevent blockchain/log truncation, but plain text is irrevocably purged.

#### 5. Historical Cortex Release Selection for `as_of_event`
- When a query specifies `as_of_event = T`:
  - The engine queries `SELECT release_id FROM cortex_releases WHERE workspace_id = ? AND spine_event_watermark <= T AND (superseded_at IS NULL OR superseded_at > T) AND status IN ('active', 'superseded') ORDER BY spine_event_watermark DESC LIMIT 1`.
  - If a matching historical release exists, that release's hierarchy, affinity, and priors are used.
  - **Rule**: NEVER silently fall back to the current active projection for an historical query! If no historical release exists with watermark $\le T$, the query explicitly runs in degraded direct-evidence mode with clear diagnostics (`"historical_projection_unavailable": true`).

#### 6. Authorization and Policy at Historical Time
- Retrieval enforces **current authorization credentials** against the tenant boundary, but evaluates the **Cognitive Policy active at the historical watermark $T$**.

#### 7. Options for Decision P-004

- **Option A (Strict Bitemporal with Release Watermark Mapping - Recommended)**:
  - Bitemporal separation of Spine event offsets and valid-time metadata.
  - Historical queries select the nearest historical Cortex Release with watermark $\le T$.
  - Unavailable historical projections report explicit diagnostic degradation rather than silent drift.
- **Option B (Event-Time Only with Dynamic Replay)**:
  - Only Spine event offsets supported; valid-time managed by application layers.
- **Option C (Snapshot-Only Temporal Pruning)**:
  - Historical queries beyond the latest $N$ releases are rejected.

**Recommendation**: Adopt **Option A**.

---

### Verification and Sign-off
- Lease ID: `lease-s3-t0-tr1`
- Operator: S3 — Trace V2 Cortex Release Owner
- Status: **COMPLETED & READY FOR S3 TR2 CONDITIONAL TEMPORAL IMPLEMENTATION UPON P-004 SIGN-OFF**
