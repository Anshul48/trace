# lane-BENCH10M snapshot-before-mutation (2026-10-08)

Taken before any lane writes (this lane creates NEW files only; no
product/harness/criteria edits per the delegation).

## Pre-existing state (read-only observations)

- trace-architecture: NOT a git checkout (no .git; `git rev-parse`
  fails at filesystem boundary). No VCS baseline available; file
  shas below are the baseline.
- trace-bench: sibling checkout `../trace-bench`, wheel
  `dist/trace_bench-0.3.0-py3-none-any.whl` (440,383 B,
  sha256 `3c11d3ed…b759`), built 2026-10-07 16:10.
- Lane dir did not exist before this run (`ls lane-BENCH10M` →
  no such directory); created 2026-10-08.

## Serving-byte baseline (local tree, sha256 8-char)

| file | observed | shipped (c2-10m-package-draft) | match |
|---|---|---|---|
| tl-sys/tlsys/dossier.py | 93871fb3 | 93871fb3 | yes |
| tl-sys/tlsys/relquery.py | 0fe79c50 | 0fe79c50 | yes |
| tl-sys/tlsys/relserve.py | 61b69a84 | 61b69a84 | yes |
| tl-sys/tlsys/query.py | d7756e72 | d7756e72 | yes |
| tl-sys/tlsys/index.py | b8bc1390 | b8bc1390 | yes |
| tl-sys/tlsys/serving/generation.py | 92970939 | 92970939 | yes |
| tl-sys/tlsys/prodstate.py | e7a4370c | e7a4370c | yes |

All 7 shipped serving files match the local tree. Known drift is
isolated to producer paths (maint.py freeze v4, R100M scope —
zero 10M serving impact per lane-READ10M §8.2).

## Corpus-manifest baseline

- `../trace-bench/docs/corpora/upstream-links.json`: 51 files,
  tiers 10m/100m/500m/1b; 10M source order: bright-pony,
  beir-scifact, beir-nfcorpus, multihop-rag, musique.
- `../trace-bench/docs/CORPORA.md`: 51/51 pinned resolvers,
  zero metadata discrepancies (coordinator-verified 2026-10-07).
