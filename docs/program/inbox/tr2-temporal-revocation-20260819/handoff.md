# S3 TR2 Temporal and Revocation Handoff

## 1. Identity

```yaml
packet_id: tr2-temporal-revocation-20260819
session: S3 / Codex Session 7
role: bounded P-004 implementation worker
status: needs_review
authority_level: C1
started_utc: 2026-08-23T08:03:58Z
completed_utc: 2026-08-23T08:58:24.2327937Z
worktree_path: C:\Users\anshu\AppData\Local\trace-worktrees\trace-tr2-s3-20260823
worktree_lease_id: lease-s3-tr2-temporal-revocation-20260823
base_commit: 454c5aed2200796ac9874e4fbe6e099bdb53f830
verifier_id: pending-coordinator-fresh-v1b-trace-temporal
```

## 2. Summary

The accepted P-004 Option A contract was implemented in the fresh exclusive
TR2 worktree and committed as `0a91b278a414756da260b15c5cb9daddb5e9aac2`,
whose parent is the pinned TR1 head `454c5aed2200796ac9874e4fbe6e099bdb53f830`.
The change is additive: explicit valid-time metadata, source lifecycle and
erasure handling, historical Cortex release selection, temporal policy
diagnostics, and revision-aware retrieval were added without rewriting
migrations 001-005. The focused six-case temporal matrix and the full V2 suite
pass locally (47 tests); this is implementation evidence only. PostgreSQL/RLS,
external-index, object-store erasure, deployment, and scale claims remain
unverified, so the packet is `needs_review` pending the fresh V1b verifier.

## 3. Inputs and provenance

| Input | Hash/identity | Purpose |
| --- | --- | --- |
| Human P-004 decision | `decision.md` SHA-256 `d4ea0969d4af2e698f5838de0598e17aa40a66a6d1712c0b47496811b527333c` | Binding contract |
| TR2 packet | SHA-256 `5d53abc5a90abf8716e3a492a0c803c608e70d6ae23f7f342e6994e9ad1ce4bb` | Scope and exit |
| TR1 handoff | SHA-256 `26aa4f01c4665d28ddc00066a27fa7ad23ad28f55444ff0274c0fff762200481` | Base dependency |
| Base source identity | `a8e9edf50b1c1567c307ec8261e5b6f7d0711f064488fa63831ecb12e4fed7e2` | Pinned TR1 source manifest |
| Dependency lock | `uv.lock` SHA-256 `8e17ba533ea59c3695105925835fe87b38c7ad088d59e7d28812f6093f81a7d9` | Runtime identity |
| Runtime | Python 3.12.11, uv 0.12.2 | Local checks |

The protected main checkout was dirty before this session and remained outside
the lease. The expired TR1 worktree and prior verifier worktree were preserved;
global control-plane files were not edited. No external dataset, provider,
network, or model service was used.

## 4. Scope and authority

Allowed implementation paths were the seven `src/trace/v2` files in the lease,
`migrations/006_temporal_revocation.sql`, and
`tests/test_v2_temporal_revocation.py`; packet-local evidence was written only
under this packet directory. Authority exercised was code/test mutation in the
fresh lease and local SQLite observation. Authority intentionally not exercised
was production activation, PostgreSQL/RLS execution, external-index access,
object-store deletion, deployment, or any scale/certification gate.

## 5. Observed facts

- `ValidTimeMetadata` and request validation are in `src/trace/v2/models.py:24`.
- SQLite temporal visibility and lifecycle transitions are in
  `src/trace/v2/store.py:1253` and `:1369`; erasure is at `:1395`.
- PostgreSQL adapter parity is implemented in `src/trace/v2/production.py:418`
  onward, but only import/static checks ran.
- Historical release resolution is in `store.py:3211` and
  `production.py:3373`; missing history returns `historical_unavailable` in
  `service.py:2179` without current-release fallback.
- A live SQLite sample is retained at
  `evidence/sqlite-evidence-sample.json` and records half-open boundary
  exclusion, current revocation denying an old watermark, release/component
  identity, and redacted content.

## 6. Changes or artifacts

| Artifact | Path | Identity | Reversible? |
| --- | --- | --- | --- |
| Implementation commit | fresh TR2 branch | `0a91b278a414756da260b15c5cb9daddb5e9aac2`; tree `0a492ca4c3f2310a123577cfa96cc72bdc2c0257` | Yes, candidate remains unactivated |
| Additive migration | `migrations/006_temporal_revocation.sql` | SHA-256 `018de7e501009799ba249679dc6c3e027a230efd01fafe17de2bb56d01f7270c` | Forward-only; rollback is release/code rollback, not destructive migration rewrite |
| Focused test matrix | `tests/test_v2_temporal_revocation.py` | SHA-256 `0a2c72d7dd65e02cd3c4fbf41c7b1d8277c909a866cdacb7355d6dbd74efd56e` | Yes |
| V1b input manifest | `evidence/v1b-input-manifest.json` | Companion hash in `evidence/checksums.json` | Yes |

Changed paths in the implementation commit: `src/trace/v2/api.py`,
`src/trace/v2/models.py`, `src/trace/v2/production.py`,
`src/trace/v2/repository.py`, `src/trace/v2/retrieval.py`,
`src/trace/v2/service.py`, `src/trace/v2/store.py`,
`migrations/006_temporal_revocation.sql`, and
`tests/test_v2_temporal_revocation.py`.

## 7. Verification and temporal matrix

| Test/check | Result | Evidence |
| --- | --- | --- |
| Clean-base V2 discovery | 41 passed | `commands.md` baseline row |
| Focused P-004 matrix | 6 passed | `commands.md`, focused test file |
| Full V2 discovery after TR2 | 47 passed in 1.791s | `commands.md` |
| AST parse | `ast-ok:44` | `commands.md` |
| Production adapter import | Passed; no DB connection | `commands.md` |
| `git diff --check` | Passed | `commands.md` |
| Pytest | Blocked: module unavailable | `commands.md` |
| Docker daemon | Blocked: Docker API npipe permission denied | `commands.md` |

The focused matrix covers: explicit `[from,to)` and unknown-time exclusion;
immutable edit lineage with historical/current selection; contradiction to
`conflicted` without hiding assertions; revocation and tombstone filtering
with current policy dominating an old watermark; signed erasure with blank
canonical content and deleted projection coverage; and release/source identity
plus missing-history fail-closed behavior.

## 8. Invariant checks

- [x] Canonical Spine rows remain append-only; projection erasure removes
  readable derived objects while retaining a signed non-content receipt.
- [x] Candidate release rows remain isolated until validation/activation; prior
  release behavior remains covered by the full V2 suite.
- [x] Source, valid-time, lifecycle, policy, and release evidence survive in
  local result/diagnostic paths and the live sample.
- [x] No certification fallback, provider, network, or synthetic benchmark
  substitution was used.
- [x] Revocation/tombstone/redaction are fail-closed for ordinary and
  historical visibility; contradiction remains readable but explicit.
- [ ] PostgreSQL/RLS and external-channel replay parity is not checked here;
  it is a V1b dependency.

## 9. Risks, decisions, and blockers

| ID | State | Evidence | Impact | Owner/next packet |
| --- | --- | --- | --- | --- |
| TR2-V1B | needs_review | `verifier_id` is pending; no independent worktree receipt | No promotion/certification claim | Coordinator / V1b-Trace-temporal |
| TR2-PG | blocked | Docker daemon API denied; no PostgreSQL DSN/runtime receipt | Migration, RLS, replay, and production adapter behavior unverified | V1b verifier |
| TR2-EXT | blocked | No OpenSearch/Qdrant/provider access by lease | Historical external-channel revision selection unverified | V1b verifier |
| TR2-ERASURE | needs_review | Repository payload/projection erasure is tested; raw object-store deletion and erasure idempotency were not exercised | Human/coordinator must review before promotion | V1b privacy/policy review |
| TR2-PYTEST | blocked | `pytest` is not installed | unittest/AST evidence used; pytest-specific checks not run | Environment owner |

## 10. Claim boundary

This handoff proves a committed, locally tested implementation candidate and a
live SQLite evidence sample at C1. It does not prove PostgreSQL schema
application, RLS isolation, external-index parity, raw object-store erasure,
deployment readiness, historical completeness, 100K scale, or certification.

## 11. Next dependency

```yaml
next_packet: V1b-Trace-temporal
hard_dependencies:
  - fresh independent verifier lease/worktree based on 0a91b278a414756da260b15c5cb9daddb5e9aac2
  - evidence/v1b-input-manifest.json and its companion checksum
  - independent SQLite replay and temporal evidence verification
  - PostgreSQL/RLS/external-index capability receipt, or explicit blocked receipt
  - privacy/policy review of object-store erasure and erasure idempotency
recommended_action: Dispatch the fresh V1b temporal verifier without repairing this candidate in place.
safe_default: Keep the previously verified TR1 state and active release unchanged; do not promote TR2.
```

## 12. Handoff integrity

```text
Handoff writer: Codex Session 7
Handoff file hash: recorded in evidence/checksums.json after packet write
Input-manifest hash: recorded in evidence/checksums.json
Commands log path: docs/program/inbox/tr2-temporal-revocation-20260819/commands.md
Verifier receipt path: pending-coordinator-fresh-v1b-trace-temporal
Coordinator review state: needs_review / independent verification pending
```
