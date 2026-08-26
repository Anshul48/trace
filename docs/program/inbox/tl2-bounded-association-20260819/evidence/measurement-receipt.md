# TL2 measurement receipt

Raw receipt: `C:\Users\anshu\AppData\Local\Temp\trace-s2-tl2-100k-receipt-final-v2.json`

Raw receipt SHA-256: `c4f99b0ef4fae3a4de8990632fb8ae7fad9d42701df71c012215f83ecf012fb3`

Command: `uv run --project . --extra dev python scripts/measure_tl2_bounded_graph.py --output "$env:TEMP\\trace-s2-tl2-100k-receipt-final-v2.json"`

This is C1 engineering evidence from a deterministic generated adversarial
fixture, not public retrieval, SOTA, 100K certification, or promotion evidence.

## Policy identity

- P-002 decision SHA-256: `ed4e8bb93e614169279f568eab5690280168de7b4339dc21f7638cc2acc8a129`
- Graph policy SHA-256: `5cb3ac89fefa03f6e3c015aa76b14cd4f60457b2a5f82b89cd9d032cd41fc4c1`
- Default combined configuration fingerprint: `43b640943d1fb3ce1e7042b53ce6ce6a590a979190a212e4304c69222f5ac1c2`

## Adversarial 100K receipt

- Fixture: 100,000 atoms; `boilerplate` df=100,000; `bounded-group` df=100.
- Theoretical unbounded pair candidates: 4,999,954,950, including
  4,999,950,000 from the boilerplate term.
- Bounded edges: 202,548 total: 199,998 structural and 2,550 soft-affinity.
- Soft degree: max 50, mean 50, p95 50; candidate-partner cap hits 100;
  degree-cap drops 2,450; high-DF terms skipped 1.
- Build elapsed: 4,490.487 ms; observed post-build RSS 256,520,192 bytes;
  enforcement RSS delta 84,221,952 bytes against 536,870,912; tracemalloc
  peak delta 118,615,309 bytes.
- Serialized projection estimate: 58,838,370 bytes against 268,435,456.
- Fixed-input soft projection replay: deterministic `true`; stable edge digest
  `6f9e9a8df6ca539400f0d078dd0c890774b90dc467d8a6afa31176531e6df46`.

## Query receipts

- Complete chain: 1.683 ms, 4 traversed edges, 5 activated/returned nodes,
  depth 4, 5 PPR iterations, 4,408 measured working bytes, no overflow.
- Structural overflow fixture: 1.152 ms, 32 traversed edges, 33 activated
  nodes, 11,832 measured working bytes, status `bounded_incomplete`, overflow
  `structural_edges_per_node`, no fallback traversal.
