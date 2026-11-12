# FINDING: TRACE parents/path vs flat ids (hierarchy lift), 100M sealed store — claude-sci 2026-11-05
Tags: OBSERVED (VM hand, my own recompute agrees). Scope: 812,545 units, 50 probes (10 s8 literal fragments + 40 authored), one VM; owner batch only, no public text. Preregistered: h2h/PREREG2.md sha 30bf2aa97c82b9e7c41f344d8f8aa060c33b894e4e2efc596d1a8496a0eafc8c.
Hand: trace-100m-hier-lift-20261105T130354Z (VM). Result: VM ~/owner-hub/scratch/wave2/trace-100m-hier-lift/RESULT.md (copy: scratch/wave6/claude-sci/hier/RESULT.md).

## Results
- Step-1 gate: service parents/path == assign-array parents on 500/500 passages (gate 480). Store shas unchanged (13/13).
- H-line: parent expansion E(hnsw) 31/50 vs flat top-K at the SAME context size 34/50 (diff -3, one-sided p 1.0; 0 E-only / 3 flat-only). => NO HIERARCHY LIFT: flat ids at equal budget do as well or better. Exact flat top-K 35/50.
- Same for BM25: E 44/50 vs flat top-K 48/50 (0 E-only / 4 flat-only, p 0.125 two-sided).
- vs flat top-10 (UNMATCHED context, 10 vs ~81 units) E gains +5 (hnsw) / +3 (bm25): that gain is a context-size effect, not a hierarchy effect. P-diagnostic: parent hit == E hit on all arms (parents are real signal, ~1000x chance, but a larger flat list captures the same source).
- B-line: E(hnsw) reaches 0.62, below 0.80. BM25 stays the best arm (0.82 / 0.96 with a big matched list).
- Hybrids (fixed configs, untuned): RRF k=60 38/50, 0.5/0.5 min-max 40/50, BM25 alone 41/50 => NO HYBRID GAIN OVER BM25 on this set.

## My independent check (verify_hier.py, own code, hand's ranked lists as input)
Rebuilt parent members from assign arrays: E context == top-10 + parent members for all non-truncated queries; truncated (hnsw 20/50, bm25 34/50) have K=100 and keep the top-10; Fk == top-K of R; E/Fk/F10 hit counts and discordants identical (31/26/34; 44/41/48); RRF recomputed and equal 50/50. H2 hit count taken from hand (40).

## Caveats
- Parent expansion here is cosine-ordered and cap-100 truncated; truncation hits the largest-K cases. A different expansion policy (e.g. smaller cap, rerank by parent score) was NOT tested.
- R_tr has no matched K>10 control (top-10 only recorded).
- 50 probes incl. 10 literal fragments advantaging BM25; no test of answer-level quality or of using `path` as structure by a reader.
- This tests lift in source-hit at matched context budget only. It does not test a reader that benefits from grouped context.
