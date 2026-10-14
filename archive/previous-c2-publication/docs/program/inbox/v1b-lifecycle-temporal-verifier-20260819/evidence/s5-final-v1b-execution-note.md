# S5 Final V1b Execution Note - Graph and Temporal

## Objective

Independently verify the accepted P-002 TL2 graph contract and accepted P-004
TR2 temporal/revocation contract from exact immutable implementation commits.
Run graph and temporal sub-gates in disjoint verifier worktrees, environments,
databases, caches, scratch roots, result roots, and manifests. Do not repair
candidate code or reuse the initial V1b verifier state.

## Pinned inputs

- TL2 handoff: `docs/program/inbox/tl2-bounded-association-20260819/evidence/handoff.md`
- TL2 head: `3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c`
- TL2 input manifest: `8da0074be85dedf6c371b681a94847c5921d33310cfb6e0069750a1bd7463b29`
- P-002 decision: `ed4e8bb93e614169279f568eab5690280168de7b4339dc21f7638cc2acc8a129`
- TR2 handoff: `docs/program/inbox/tr2-temporal-revocation-20260819/handoff.md`
- TR2 requested head: `0a91b278a414756da260b15c5cb9daddb5e9aac2`
- TR2 V1b input manifest: `65c8ac4df07244a8ba0ad25dabeeb47054d0181d9fce3e861cf201287fe4eb79`
- P-004 decision: `d4ea0969d4af2e698f5838de0598e17aa40a66a6d1712c0b47496811b527333c`
- TR2 identity note: the named implementation worktree currently resolves to
  `0cd7ca8a4d269f0f412527b14718a9ec47e09e9e`; that drift is outside the
  verifier lease. The requested `0a91b278...` object exists with parent
  `454c5aed2200796ac9874e4fbe6e099bdb53f830` and will be used directly.

## Planned isolated resources

| Sub-gate | Verifier worktree | Environment | Scratch/database/cache | Result root |
| --- | --- | --- | --- | --- |
| Graph | `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-graph-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-envs\v1b-final-graph-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-final-graph-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-results\v1b-final-graph-20260823` |
| Temporal | `C:\Users\anshu\AppData\Local\trace-verifier-worktrees\v1b-final-temporal-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-envs\v1b-final-temporal-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-scratch\v1b-final-temporal-20260823` | `C:\Users\anshu\AppData\Local\trace-verifier-results\v1b-final-temporal-20260823` |

Each sub-gate gets its own verifier lease receipt, input manifest, result
manifest, raw receipt, and command record. Network, providers, PostgreSQL/RLS,
external indexes, deployment, and object-store infrastructure are not
substituted with SQLite, mocks, or synthetic certification claims.

## Graph acceptance matrix

Verify common-term filtering, high-DF behavior, partner/degree caps,
deterministic selection, deduplication, graph identity scoping, PPR node/edge/
depth/work limits, timeout/cancellation, overflow diagnostics, replay,
incremental/full parity, candidate visibility, and resource telemetry. Edge
counts alone are insufficient.

## Temporal acceptance matrix

Verify system/event-time reconstruction, explicit valid-time intervals and
unknown precision, revision/supersession, contradiction retention, revocation,
tombstones, privacy erasure, historical authorization, historical release
selection, missing historical projection, and evidence-bundle release/source
revision identity. Confirm current projections cannot satisfy historical reads.

## Stop conditions

- Any source/commit/lease/path drift affecting the exact input.
- Any need to modify candidate code, implementation tests, decision records,
  thresholds, global control-plane files, or expected outcomes.
- Missing dependency/environment or unavailable PostgreSQL/RLS/external-index/
  deployment capability; record only the affected claim as blocked.
- Any fallback, hidden error, synthetic substitution, or shared mutable state.

## Outputs

Packet-local final graph/temporal receipts, separate manifests and hashes,
updated final handoff, and an exact next dependency. Initial V1b lifecycle and
release receipts remain historical supporting evidence and are not merged into
the graph or temporal counts.
