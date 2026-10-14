# P-002 Human Decision - Bounded Graph Association and PPR

## Decision

- Status: accepted human decision
- Date: 2026-08-23
- Authority: program owner
- Option: B, Balanced Bounding

## Binding contract

- Skip a term when `df(t) > min(100, 0.10 * N)`.
- Cap soft-affinity candidate partners at 50 per atom/term and stored soft-affinity degree at 50 per atom.
- Preserve source-derived structural evidence edges. Limit query-time structural expansion to 32 edges per node.
- TL2 creates no trusted-semantic edges; reviewed semantic relations remain a separate channel.
- Admit edges using deterministic MI/TF-IDF-weighted ranking, canonical endpoint-pair deduplication, and stable endpoint-ID tie-breaking. Use seed `0` wherever sampling is required.
- Do not apply online learning or decay. Rebuild projections from immutable Spine evidence and configuration after source/configuration changes.
- PPR uses `alpha=0.85`, at most 20 iterations, convergence threshold `epsilon=1e-4`, maximum depth 4, at most 512 activated nodes, at most 2,500 traversed edges per query, and top 100 returned nodes.
- Hard query limits are 35 ms wall time and 64 MiB query working memory. Initial 100K build limits are 512 MiB RSS and 256 MiB projection storage.
- A limit breach returns `bounded_incomplete` with counters and no fallback, unbounded traversal, or silent parameter tuning.
- Behavioral signals are not factual evidence and are not admitted to the trusted semantic channel.
- Acceptance requires the adversarial high-frequency 100K workload and measured edge, latency, memory, disk, overflow, and determinism receipts. These limits are engineering bounds, not a 100K certification claim.

## Scope and claim boundary

This decision authorizes S2 TL2 to implement the bounded Trace-Lite association
policy in its isolated worktree. It does not authorize activation, retrieval
quality certification, Trace adaptation, a SOTA claim, or a 100K promotion.
