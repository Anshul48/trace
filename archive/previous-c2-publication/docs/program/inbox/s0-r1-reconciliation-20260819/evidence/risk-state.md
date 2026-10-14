# R1 Risk Reconciliation

**Reconciled at:** 2026-08-19T12:40:55.1070524Z

| Risk | R1 state | Direct evidence | Containment / next action |
| --- | --- | --- | --- |
| R-01 Candidate projection leakage | Open in implementation; pending independent verification | L1/TR1 handoffs report candidate isolation, but no V1b receipt exists | Run separate V1b-TL lifecycle and V1b-Trace release sub-gates; retain predecessor state |
| R-02 Unbounded graph growth | Open and decision-blocked | L1 prepared P-002 measurement brief; TL2 packet remains blocked | Human P-002, then TL2; do not set caps in R1 |
| R-03 Benchmark fail-open behavior | Contained in B1 implementation; open for certification identity/verification | B1 handoff reports 26/26 tests, but live full commit differs and `uv.lock` is untracked | B1.1 resolves source/dependency identity; V1a then verifies the frozen negative matrix |
| R-04 Weak external evidence | Contained for D2a staging; open for normalized evidence mappings | Seven D2a metadata sets match live files; no D2b normalization or independent D2a verifier packet | D2b only after B1.1 contract; preserve raw data |
| R-05 Source/projection confusion | Open at claim boundary | L1/TR1 implementation evidence is not an independent release claim | Keep program label at implementation complete / independent verification pending |
| R-06 Temporal/revocation gaps | Open and decision-blocked | TR1 delivered a P-004 brief; TR2 packet and temporal V1b sub-gate are blocked | Human P-004, then TR2 and final V1b temporal verification |
| R-07 Agent-context/source drift | Open in inherited records; contained for this R1 packet | B1 handoff full hash is nonexistent; D0 leases expired; control-plane lock is stale at 103 files | Use R1 hashes, fresh leases, and post-write lock snapshot; do not reuse D0 assignments |
| R-08 Verification conflict | Contained by fresh assignment boundaries; not yet verified | Separate V1b worktree/scratch paths are reserved; V1a remains blocked | S5 owns verifier paths and may not repair candidates |
| R-09 Uncontrolled scale claims | Contained | Scale nodes remain blocked behind Foundation Gate | Keep 100K/1M rows blocked and P-005 deferred |
| R-14 Windows/OneDrive test-root conflicts | Contained for next sessions | All new verifier scratch roots are outside OneDrive and currently absent | Create them only inside their leases; record cleanup outcome |
| R-15 Documentation overclaim | Open until global status is refreshed | Existing status says Wave 1 complete/unblocked and implementation packets completed without independent acceptance | Update status/risk/registry and preserve packet-local historical claims |

## Human-owned decisions preserved

- **P-002:** graph degree, term-frequency, PPR, and query work budgets remain
  deferred.
- **P-004:** valid-time, supersession, revocation, tombstone, deletion,
  historical-policy, and compliance-erasure semantics remain deferred.
- **P-005:** numerical release thresholds and significance method remain
  deferred.

R1 records no acceptance, rejection, or numeric choice for these decisions.
