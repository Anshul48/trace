# TL2 execution note

Objective: implement the accepted P-002 Balanced Bounding policy on top of L1
candidate/active lifecycle at commit `7ff40dc46fe3d5e8eef31c485ed0337b8f71602d`.

Allowed mutation is limited to the leased Trace-Lite worktree and the packet-local
handoff/evidence files. The Spine, canonical Trace-Lite checkout, expired L1
worktree, Trace control-plane documents, trace-bench, providers, network, and raw
data are forbidden.

Acceptance requires deterministic high-DF filtering, candidate-partner and stored
degree caps, typed/provenanced graph edges, bounded PPR/query work, explicit
`bounded_incomplete` receipts, candidate isolation, lifecycle rollback safety,
focused tests, and measured adversarial budget receipts. No quality, SOTA, 100K,
activation, or promotion claim is in scope.

No subagents are used; the S2 leased writer owns implementation, measurements,
tests, and the packet handoff.

Stop conditions: any missing/changed P-002 value, source identity drift, mutation
outside the lease, candidate visibility before activation, unbounded traversal,
fallback/mock/provider substitution, destructive public-contract change, or an
acceptance check that cannot produce a structured receipt.
