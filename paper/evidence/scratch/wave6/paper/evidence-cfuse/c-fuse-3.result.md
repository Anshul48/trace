# RESULT — c-fuse-3: C-FUSE stage 3 (PREREG12 fresh-set confirmation on XF)

## Verdict (XF TEST, literal, first)

NOT CONFIRMED (d_hit +0.033 [0.001,0.066]; d_mrr +0.037 [0.005,0.069])

Primary MMr vs Dr on 300 XF queries (all TEST, 100/style): d_hit=+0.033
misses the preregistered +0.04 bar (d_mrr=+0.037 clears +0.03; both CI lower
bounds > 0; G1/G2/G3 pass). Directionally the stage-2 effect replicates —
fusion gains on both metrics with CIs excluding 0 — but the hit@10 margin is
below the confirmation threshold, so per PREREG12 the verdict is NOT
CONFIRMED. No harm (both d > -0.02). XF scored exactly once (xf_run.json
attempts=1, completed 2026-11-05T22:56:22Z); gates ran first with labels
sealed; no DEV (all XF rows are TEST per prereg).

## XF metrics (label = source ordinal; HEADLINE = style macro)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.790 | 0.370 | 0.830 | 0.663 | 0.663 |
| Br | 0.740 | 0.200 | 0.750 | 0.563 | 0.563 |
| MMr PRIMARY | 0.830 | 0.370 | 0.890 | 0.697 | 0.697 |
| RRFr | 0.820 | 0.270 | 0.850 | 0.647 | 0.647 |
| global BM25 (context) | 0.720 | 0.200 | 0.740 | 0.553 | 0.553 |
| global dense (context) | 0.790 | 0.370 | 0.830 | 0.663 | 0.663 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.595 | 0.252 | 0.621 | 0.490 | 0.490 |
| Br | 0.593 | 0.140 | 0.504 | 0.412 | 0.412 |
| MMr | 0.698 | 0.210 | 0.672 | 0.527 | 0.527 |
| RRFr | 0.673 | 0.168 | 0.644 | 0.495 | 0.495 |
| global BM25 | 0.586 | 0.140 | 0.498 | 0.408 | 0.408 |
| global dense | 0.595 | 0.252 | 0.621 | 0.490 | 0.490 |

Also: hit@1 macro Dr 0.390 / Br 0.333 / MMr 0.443 / RRFr 0.417;
hit@5 macro Dr 0.627 / Br 0.520 / MMr 0.637 / RRFr 0.587;
hit@20 macro Dr 0.720 / Br 0.593 / MMr 0.740 / RRFr 0.720 (full: metrics.json).
Per-style MMr-Dr hit@10: s0 +0.040, s1 +0.000, s2 +0.060 (no gain on keyword
queries, where Br collapses to 0.200).

Secondary: RRFr vs Dr d_hit=-0.017 [-0.059,0.024], d_mrr=+0.005
[-0.031,0.042] (null: CIs cross 0; RRF sensitivity does not replicate).
MMr vs Br (inside C, with CI): d_hit=+0.133 [0.095,0.174],
d_mrr=+0.114 [0.082,0.147] — on XF, fusion beats keyword-inside-C decisively
(and global BM25 0.553 < MMr 0.697). Ceiling: source outside C on XF = 1
query. NO STYLE REVERSAL — per-style hit@10 winners of {Dr,Br}: s0 Dr, s1
Dr, s2 Dr. MM degenerate lists: 0. Bootstrap: 10,000/10,000 kept (0 skipped),
300 distinct doc_id units (= n XF; cluster == query here), seed 20261109.

## Gates (lists vs lists, no labels; 300 XF)

- G1 Br validation: 296/300 = 0.9867 >= 0.95 PASS (strict rate identical;
  0 SHORT queries). 4 diffs (XF-0021, XF-0155, XF-0262, XF-0289): three are
  same-set adjacent swaps; XF-0262 admits ordinal 396001 over 661822 at
  EXACTLY equal BM25 scores (6.762958526611328) — my ascending-ordinal tie
  rule vs bm25s-quicksort's arbitrary tie-break, the anticipated artifact
  (choices.md C1). Scorer validated.
- G2 Dr validation: 300/300 = 1.0000 >= 0.95 PASS (denominator 300: every XF
  query's global dense top-10 lies fully inside C).
- G3 row budget: same C for all four arms (single load, asserted); |C| per
  query 98,057..116,631, mean 108,733 (13.4% of 812,545).
- Order: gates -> score ONCE (no DEV exists). Kept. xf_run.json attempts=1.

## Exporter + encoder provenance

- Encoder: x1 x1enc.py/x1common.py imported read-only (no copy, no edit);
  staged all-MiniLM-L6-v2, CPU, normalize+explicit L2, one-by-one. Self-test
  gate: 50 old probes vs h2h embeds, min cosine 1.0000000 >= 0.9999 PASS
  (selftest_xf.json). Q_xf.f32.npy sha256
  3ba284a5425a862d42abc562e180e68950f3734e02c20616635cb49d0e4ccc2d
  (f64 twin 4653ccc95955f19e9725daf6a8753e2e3a886cb34eb8579be238f97857b585ad).
- Exporter: export_candidates.py copied to lease; the ONLY changes are
  parameter-only (export.diff): LEASE path, XF query file + Q_xf.f32.npy for
  X0 inputs, outputs candidates_xf.npz/counts_xf.jsonl; nomination math
  (NP=3000, f64 qnorm, nominate, members, merge, sorted int32) untouched.
  Exported 350 = 300 XF + 50 old (old-50 = regression check, unscored).
- Re-validation of the parameterised exporter (validation_xf.py, validate.py
  math + C-identity assert): my 50 old-search C arrays bit-identical to
  filed candidates.npz 50/50; restricted-vs-live top-10 agree (set+order)
  50/50; exact-recipe 50/50. Stage-1 validation reproduced.

## Cost

- Rows scored per query: |C| (above), identical for Dr/Br/MMr/RRFr.
- Extra keyword work: nonzero-BM25 rows in C per query 1,252..113,260
  (mean 64,693); BM25 score wall 0.90 s total (p50 2.9 ms/q, p90 6.0 ms/q),
  tokenise 0.01 s, selection 2.05 s; dense-over-C wall 20.5 s (300 queries);
  global BM25 p50 8.1 / p90 33.0 ms/q; export 10.9 s; embed p50 12.3 ms/q.
- RAM peak: 972 MB (dense), 954 MB (global dense), 550 MB (global BM25),
  537 MB (bm25-over-C). Load gates unflagged throughout (la1 0.3..0.9 at
  step starts, limit 2.0, no waits). Wall total << 2 CPU-h.

## Could not observe / deviations

- C_pool (S=1600 2-bit shortlist) unobservable (stage-1 finding); Dr is exact
  dense over C_route, an upper bound on the live 2-bit pool — as preregistered.
- Engine-internal nomination floats/tie rule UNVERIFIED (binary-only),
  inherited from stage 1 (whose 50/50 consequence validation I reproduced on
  my export 50/50).
- Encoder rev hash 1110a243… UNVERIFIABLE by hash (no git metadata in the
  staged dir); verified by consequence: same staged dir x1 used + self-test
  min cosine 1.0000000 (x1's own position).
- Gap closure n/a (no HIST unrestricted arms exist on XF) — reported, not
  tested. No replay (not in PREREG12).
- No deviations from PREREG12 or choices.md (frozen 2026-11-05T22:50:11Z,
  before any compute). BM25 walls include cold-mmap faults, as measured.

## Integrity

- 48 input hashes before == after (sha-before.txt/sha-after.txt, all OK):
  PREREG12 ea13f566…5016 == PREREG12.sha256, XF queries f42d9d06…f32df ==
  brief, candidates.npz 1e87fedb…ded2ef5c == prereg.
- Tests: test_cfuse3.py 16/16 OK (venv python, -W error::ResourceWarning,
  foreground, hermetic synthetic) and 11 pass + 5 numpy-skips under
  /usr/bin/python3. Unit file: test.log.
- Live services untouched (no queries sent); originals never edited;
  lease dir 155 MB (<= 3 GB); single process; nice -n 10.

## Files (lease /home/anshul/owner-hub/scratch/wave2/c-fuse-3)

choices.md, lib_cfuse3.py, export_candidates_xf.py (+export.diff),
validation_xf.py (+validation.diff), step_selftest_xf.py, step_embed_xf.py,
step_globalB_xf.py, step_globalD_xf.py, step_dense_xf.py, step_bm25_xf.py,
step_gates_xf.py, step_score_xf.py, test_cfuse3.py, pylibs/bm25s (0.3.16
copy), Q_xf.f32.npy (+Q_xf.sha256, f64 twin, qmeta_xf.jsonl),
candidates_xf.npz, counts_xf.jsonl, validation_xf.json, selftest_xf.json,
raw_B_XF.jsonl, raw_D_XF.jsonl (global refs), raw_Dr_XF.jsonl,
raw_Br_XF.jsonl, raw_XF_{Dr,Br,MMr,RRFr}.jsonl (300 q, {id,ret100,arm}),
gates.json, metrics.json, xf_run.json, dense_cost_xf.json,
bm25_cost_xf.json, *.log, test.log, sha-before.txt, sha-after.txt, RESULT.md.
