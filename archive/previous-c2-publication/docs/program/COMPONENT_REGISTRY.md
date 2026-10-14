# Component Registry and Boundary Contract

> **Status:** Current-state registry, refreshed by S0 R1 at
> `2026-08-19T12:40:55Z`. It records implementation identities separately from
> verifier readiness and does not claim a release or gate acceptance.

## 1. Component identities

| Component | Canonical root | Identity at refresh | Boundary status | Ownership |
| --- | --- | --- | --- | --- |
| Trace-Lite | C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace-lite | User main `fe66a9eefc8372f7cc021c864d26e62a9d6cc9c1`; clean tracked tree with protected untracked paths. L1 implementation worktree is clean at `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d`. | User checkout protected; verifier must use a separate worktree from L1. Independent V1b lifecycle evidence is pending. | Trace-Lite lane (S2) |
| Trace | C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace | User main `c855bb06532b3b52b25f0bea969d2677e5049065`; protected dirty snapshot with 26 tracked modifications and 5 untracked surfaces. TR1 worktree is clean at `454c5aed2200796ac9874e4fbe6e099bdb53f830`. | User checkout strictly protected; verifier must use a separate worktree from TR1. Release verification is pending; temporal remains P-004-blocked. | Trace lane (S3) |
| trace-bench | C:\\Users\\anshu\\OneDrive\\Documents\\Code\\Utilities\\trace-bench | Git main `0b01de5e49dcb18d43876b0b6004da58b35b72aa`; source manifest `7603803ffc6537b84e67daa1b8d526a04cd173dc6c081089d947b0a3f93bc075`; tracked clean except untracked `uv.lock` (`fd4bbc...`). B1 handoff's full `0b01de5c...` does not exist. | Dedicated Git source and sole certification runner by P-007/P-008, but V1a identity is blocked until B1.1 publishes a clean superseding source/dependency identity. | Benchmark lane (S1) |
| Raw Data | C:\\Users\\anshu\\AppData\\Local\\trace-bench-data | Seven D2a roots, 85 files, 1,523,873,466 bytes; portfolio manifest `4e594992...`; metadata root `872102e2...`; live metadata matches manifest. | External staging outside Git/OneDrive; raw data remains immutable. D2a independent verifier receipt is absent; D2b waits for B1.1 schema. | Data lane (S4) |
| Program control plane | Trace docs/program | R1 pre-write tree: 213 files, `1213c046...`; R1 packet `s0-r1-reconciliation-20260819` is the current reconciliation record. | S0 sole coordinator writer; packet-local evidence writable only under its lease. Previous D0 lease set is expired. | Coordinator (S0) |

The registry does not decide whether dirty changes are good or bad. It records
that they exist and must not be overwritten.

## 2. Trace-Lite boundary

| Surface | Responsibility | Certification implication |
| --- | --- | --- |
| src/trace_lite/engines/graph.py | Co-occurrence/graph construction. | Observed all-pairs shared-term construction is a scale blocker; belongs to decision-gated TL2 after P-002. |
| src/trace_lite/engines/benchmark.py | Legacy/internal benchmark behavior. | Retained for regression/development only per P-008; cannot certify release gates. |
| benchmarks/ | Legacy in-repo benchmark material and protocol paths. | Regression/development only per P-008. |
| tests/ | Unit/integration evidence. | Regression evidence; non-certifying without frozen real data and independent verifier. |

Protect all current untracked program and benchmark protocol/registry paths.
Do not use the existing checkout as a mutable base simply because it has a Git
commit.

## 3. Trace boundary

| Surface | Responsibility | Foundation concern |
| --- | --- | --- |
| migrations/004_cortex_projection_control_plane.sql | Proposed Cortex controls. | Additive forward-only migrations under TR1 per P-003. |
| src/trace/v2/cortex.py and tests/test_v2_cortex_controls.py | Current V2 work. | Included in T0 frozen snapshot for TR1. |
| src/trace/v2/store.py, service.py, retrieval.py, models.py | Projection write/read and temporal behavior. | TR1 implements unified release root (P-003); TR2 implements temporal (P-004). |
| migrations/001_trace_production.sql | Existing event/version fields. | Event ranges are not automatically real-world valid time. |
| docs/program/ | Control-plane assets. | S0 coordinator writes only; protected against product code changes. |

Observed source-level constraints:

- hierarchy has run-scoped state and active-run reads;
- candidate affinity edges are written active and can be query-visible before
  candidate activation;
- activation priors lack release/run identity and can escape candidate
  isolation;
- lexical/dense revisions activate per adapter, not as atomic Cortex bundle;
- as_of_event covers part of the Spine but not historical
  hierarchy/affinity/activation release selection; valid time and
  source-content revocation are not first-class contracts.

These are addressed in TR1 (P-003) and TR2 (P-004).

## 4. trace-bench boundary

Per human decisions **P-007** and **P-008**:

- `trace-bench` is initialized in place as an independent Git repository under packet B0;
- Caches, pycache, egg-info, local results, and downloaded data are excluded via `.gitignore`;
- An annotated local baseline tag is created on the initial commit;
- Designated as the **sole canonical certification runner**;
- B1 implements fail-closed certification behavior, explicit modes, structured error receipts, and pinned artifact validation;
- B1.1 must resolve the live full commit/dependency-lock identity before V1a receives a verifier base;
- Legacy Trace-Lite benchmark surfaces remain non-certifying regression tools.

## 5. Integration ownership

| Interface | Producer | Consumer | Required control |
| --- | --- | --- | --- |
| TL retrieval adapter | Trace-Lite | trace-bench | Declared package/version/commit; no dynamic unpinned import in certification mode. |
| Trace retrieval adapter | Trace | trace-bench | Declared package/version/commit; certification mode never mock-injects. |
| Evidence bundle | TL or Trace | Reflex/Entorhinal later | Versioned semantics, opaque IDs, policy/temporal status, active release identity. |
| Program packet | Coordinator | All sessions | Input manifest/content hash; source state rechecked on assignment. |

## 6. F0c record requirements

F0c creates a record for each component with:

- absolute root, identity, branch and commit if available;
- timestamp and commands used;
- tracked/untracked/ignored path classification;
- dirty diff/untracked-list fingerprints where possible;
- integration/import/config paths;
- generated/cache/results exclusions;
- protected user-owned paths;
- safe clean worktree base or reason none exists;
- stale packet references caused by boundary change.

Use [templates/REPOSITORY_STATE_TEMPLATE.json](templates/REPOSITORY_STATE_TEMPLATE.json).
