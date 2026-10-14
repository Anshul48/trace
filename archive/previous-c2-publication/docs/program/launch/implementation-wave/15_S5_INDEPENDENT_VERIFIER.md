# S5 — Independent Verifier and Integration Reviewer

## Mission

Independently attack the implementation lanes. S5 never repairs, edits, merges,
or promotes the candidate it verifies. It receives a clean verifier worktree,
the implementation handoff, exact input manifest, and a separate scratch/data
root.

## Independence requirements

- Start from the implementation commit named by the handoff, not the author's
  dirty worktree.
- Use a separate worktree and external scratch directory.
- Record verifier source identity and environment before testing.
- Do not use the implementation agent's database, result directory, or cached
  provider state.
- Treat unrun, unavailable, or flaky tests as `blocked`, not pass.

## V1a — benchmark integrity

Run a frozen negative matrix against B1. At minimum cover:

1. missing source identity;
2. unpinned/editable Trace-Lite import;
3. mock provider in certification mode;
4. unavailable provider/model;
5. missing or unadmitted dataset;
6. archive/checksum mismatch;
7. synthetic substitution;
8. insecure TLS path;
9. indexing exception swallowing;
10. query exception swallowing;
11. forced flat-search fallback;
12. empty positive retrieval treated as abstention;
13. expected-abstention metric inflation;
14. missing evidence mapping;
15. fabricated organization/source coverage;
16. unstable query-ID pairing;
17. malformed/missing manifest or result receipt.

Every negative case must block or fail closed, emit the expected error code and
receipt, and have `certification_eligible: false`. A test that merely observes
an exception without proving no fallback occurred is incomplete.

## V1b-TL — Trace-Lite lifecycle

After L1/TL2 handoffs, independently test:

- candidate invisibility;
- pre-write, mid-build, validation, and activation crash recovery;
- active-pointer atomicity;
- predecessor retention and rollback;
- stale graph-row exclusion;
- graph high-DF degree/work cap behavior after P-002;
- PPR work/node/depth budget enforcement;
- concurrent source arrival and replay/idempotency;
- incremental/full rebuild parity.

Use adversarial fixtures and inspect actual read selectors, not just table
contents. Report SQLite/local evidence separately from any external-index or
distributed claim.

## V1b-Trace — Trace release and temporal checks

After TR1, test candidate affinity and activation-prior isolation, unified
multi-component handover, external alias failure/rollback, workspace isolation,
and historical release resolution. After TR2 and P-004, add valid-time,
supersession, revocation, tombstone, historical policy, and privacy/erasure
cases.

Never let a current projection satisfy an historical query silently. Verify
that every evidence bundle names the release and source revision used.

## Verifier outputs

- independent input manifest;
- test matrix with exact commands and expected/actual receipts;
- negative results and unexpected pass/fail analysis;
- source/test coverage limitations;
- V1a/V1b handoff using the shared template;
- recommendation to accept, reject, or keep blocked at the applicable claim
  level.

The verifier cannot close P-002, P-004, or P-005. It can identify missing
evidence and recommend a decision packet.

## Stop conditions

Stop if the implementation commit changes after verification begins, the
verifier shares mutable state with the implementer, a required external
capability is unavailable, or the parent asks the verifier to repair code.
