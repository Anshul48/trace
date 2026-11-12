# RESULT — c-fuse-5: C-FUSE stage 5 / XF2 (PREREG14, two authors on the same 300 fresh passages)

## Verdicts (TEST, literal, first)

X2M (Muse): NEITHER (P1 d_hit +0.023 [0.003,0.044]; d_mrr +0.060 [0.036,0.085]; P2 d_hit +0.013 [-0.004,0.033]; d_mrr +0.053 [0.031,0.076])

X2H (Haiku): BEATS BOTH (P1 d_hit +0.053 [0.019,0.090]; d_mrr +0.075 [0.045,0.106]; P2 d_hit +0.073 [0.043,0.107]; d_mrr +0.054 [0.027,0.083])

On X2M, P1 fails the +0.04 hit bar (+0.023) and P2 fails the +0.03 hit bar
(+0.013, CI crosses 0) — so NEITHER, even though both MRR deltas clear
their bars with CIs above 0. On X2H, P1 clears +0.04/+0.03 and P2 clears
+0.03/+0.02 with all four lower CI bounds > 0 — so BEATS BOTH. G1/G2/G3
pass for both sets; each set scored exactly once (run_X2M.json and
run_X2H.json attempts=1, finished 2026-11-06T03:01:35Z / 03:01:39Z);
gates ran first with labels sealed; no DEV (all rows TEST per prereg).
This is PREREG14 pre-written reading 3: X2H passes P1 and X2M fails — the
stage-3/4 split looks like an author-source effect; the fusion gain
depends on who writes the queries.

## X2M metrics (label = source ordinal; HEADLINE = style macro; n=300, 100/100/100)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.620 | 0.160 | 0.880 | 0.553 | 0.553 |
| Br | 0.610 | 0.150 | 0.930 | 0.563 | 0.563 |
| MMr PRIMARY | 0.630 | 0.150 | 0.950 | 0.577 | 0.577 |
| RRFr | 0.630 | 0.140 | 0.930 | 0.567 | 0.567 |
| global BM25 (context) | 0.600 | 0.150 | 0.940 | 0.563 | 0.563 |
| global dense (context) | 0.620 | 0.160 | 0.880 | 0.553 | 0.553 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.498 | 0.106 | 0.729 | 0.444 | 0.444 |
| Br | 0.470 | 0.120 | 0.763 | 0.451 | 0.451 |
| MMr | 0.541 | 0.117 | 0.855 | 0.504 | 0.504 |
| RRFr | 0.532 | 0.113 | 0.820 | 0.488 | 0.488 |
| global BM25 | 0.469 | 0.120 | 0.765 | 0.451 | 0.451 |
| global dense | 0.498 | 0.105 | 0.729 | 0.444 | 0.444 |

Also (macro): hit@1 Dr 0.383 / Br 0.397 / MMr 0.463 / RRFr 0.443;
hit@5 Dr 0.527 / Br 0.520 / MMr 0.557 / RRFr 0.550;
hit@20 Dr 0.583 / Br 0.570 / MMr 0.600 / RRFr 0.583 (full: metrics.json).
Per-style MMr-Dr hit@10: s0 +0.010, s1 -0.010, s2 +0.070; MMr-Br hit@10:
s0 +0.020, s1 +0.000, s2 +0.020.

## X2H metrics (n=300, 100/100/100)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.680 | 0.360 | 0.900 | 0.647 | 0.647 |
| Br | 0.670 | 0.270 | 0.940 | 0.627 | 0.627 |
| MMr PRIMARY | 0.770 | 0.380 | 0.950 | 0.700 | 0.700 |
| RRFr | 0.750 | 0.360 | 0.940 | 0.683 | 0.683 |
| global BM25 (context) | 0.670 | 0.270 | 0.930 | 0.623 | 0.623 |
| global dense (context) | 0.680 | 0.360 | 0.900 | 0.647 | 0.647 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.546 | 0.205 | 0.801 | 0.517 | 0.517 |
| Br | 0.571 | 0.210 | 0.835 | 0.538 | 0.538 |
| MMr | 0.641 | 0.234 | 0.902 | 0.593 | 0.593 |
| RRFr | 0.591 | 0.206 | 0.865 | 0.554 | 0.554 |
| global BM25 | 0.565 | 0.209 | 0.834 | 0.536 | 0.536 |
| global dense | 0.546 | 0.205 | 0.801 | 0.517 | 0.517 |

Also (macro): hit@1 Dr 0.463 / Br 0.497 / MMr 0.533 / RRFr 0.500;
hit@5 Dr 0.593 / Br 0.597 / MMr 0.673 / RRFr 0.633;
hit@20 Dr 0.710 / Br 0.643 / MMr 0.723 / RRFr 0.723.
Per-style MMr-Dr hit@10: s0 +0.090, s1 +0.020, s2 +0.050; MMr-Br hit@10:
s0 +0.100, s1 +0.110, s2 +0.010 (fusion gains in all styles on X2H).

## Secondary (no gate)

- RRFr vs Dr: X2M d_hit=+0.013 [-0.009,0.035], d_mrr=+0.044 [0.020,0.069]
  (hit CI crosses 0); X2H d_hit=+0.037 [0.001,0.073], d_mrr=+0.037
  [0.007,0.066] (both CIs exclude 0).
- Source outside C: X2M 10 queries, X2H 1 query.
- Global hit@10 (macro): X2M BM25 0.563 / dense 0.553; X2H BM25 0.623 /
  dense 0.647 (MRR in tables above).
- Content-word overlap per set (choices.md G6 SUBSTITUTE — lint.py was
  unavailable on the VM, see Deviations): X2M mean 0.3576 median 0.4444;
  X2H mean 0.4364 median 0.5000 (n=300 each, 0 empty queries). Haiku
  queries share more content words with their source passage.
- Paired contrast d_hit(MMr-Dr) X2H minus X2M on the 300 common passages:
  +0.030 [-0.009,0.071] (dH +0.053, dM +0.023; paired cluster bootstrap
  over doc_id, 10,000/10,000 kept, seed 20261109; descriptive only — the
  CI includes 0, so the author gap itself is not significant by this CI).
- Per-style winners of {Dr,Br} hit@10: BOTH sets s0 Dr, s1 Dr, s2 Br —
  STYLE REVERSAL on both (keyword wins the description style only).
- Bootstrap: 10,000/10,000 kept (0 skipped) for all six primary/
  secondary comparisons, 300 distinct doc_id units per set (= n;
  cluster == query here), seed 20261109. No harm either set
  (no MMr-vs-Dr d <= -0.02). MM degenerate lists: 0 both sets.

## Gates (lists vs lists, no labels; 300 queries/set)

- G1 Br validation: X2M 297/300 = 0.9900 PASS (strict identical, 0 SHORT;
  3 mismatches, all lenF >= 10 score-tie order diffs: X2-0001 lenF=55
  firstdiff=6, X2-0091 lenF=76 firstdiff=5, X2-0181 lenF=99 firstdiff=2);
  X2H 298/300 = 0.9933 PASS (0 SHORT; X2-0061 lenF=58 firstdiff=7,
  X2-0193 lenF=95 firstdiff=6). >= 0.95 both.
- G2 Dr validation: X2M 296/296 = 1.0000 PASS (denom 296: four queries'
  global dense top-10 not fully inside C); X2H 300/300 = 1.0000 PASS.
- G3 row budget: same C for all four arms per set (single load,
  asserted); |C| per query X2M 97,620..117,663 mean 108,681 (13.4% of
  812,545), X2H 98,231..117,638 mean 109,076 (13.4%).
- Order: gates -> score ONCE per set (no DEV exists). Kept.

## Exporter + encoder provenance

- Encoder: x1 x1enc.py/x1common.py imported read-only (no copy, no edit);
  staged all-MiniLM-L6-v2, CPU, normalize+explicit L2, one-by-one.
  Self-test gate (once, before either set): 50 old probes vs h2h embeds,
  min cosine 1.0000000 >= 0.9999 PASS (selftest_x2.json).
  Q_X2M.f32.npy sha256 5b9e0095eb5f853ce2d873d3c7b57c208d2959a906
  baccb82e1c8d12fb9699dd (f64 twin 6a81a30ea84a20ea5a0b5131c679cd2c
  bc75531b7f11d30ee84a34f44b7a0400); Q_X2H.f32.npy sha256 37be280c
  4af909d72aee976f50c8dcbbb4c615429c3ca674b6bc3337d60bd920 (f64 twin
  10ba9dd617b6e69a422d8a836c8b6f56ba5c153c25c280474a6585cc136ff9e2).
- Exporter: c-fuse-4 export_candidates_xg.py copied per set; the ONLY
  changes are parameter-only (export_x2m.diff / export_x2h.diff): LEASE
  path, X2M/X2H query file + Q file, NQ 300, outputs
  candidates_x2m.npz / candidates_x2h.npz + counts; nomination math
  (NP=3000, f64 qnorm, nominate, members, merge, sorted int32) untouched.
  Two npz were required because both frozen files use ids X2-0000..X2-0299
  (namespaces collide). Each export 350 = 300 X2S + 50 old (old-50 =
  regression check, unscored).
- Re-validation per npz (validation_x2m.py / validation_x2h.py,
  validate.py math + C-identity assert, diffs recorded): my 50 old-search
  C arrays bit-identical to filed candidates.npz 50/50 each;
  restricted-vs-live top-10 agree (set+order) 50/50 each; exact-recipe
  50/50 each. Stage-1 validation reproduced on both exports.

## Cost

- Rows scored per query: |C| (above), identical for Dr/Br/MMr/RRFr per set.
- Extra keyword work: nonzero-BM25 rows in C per query X2M 539..115,178
  (mean 67,021), X2H 2,942..114,394 (mean 84,878); BM25 score wall X2M
  1.01 s / X2H 1.46 s total (p50 3.6 / 5.0 ms/q, p90 6.5 / 8.7 ms/q),
  tokenise 0.01 s each, selection 2.10 / 2.54 s; dense-over-C wall
  19.5 / 20.6 s; global BM25 p50 7.7 / p90 ~31 ms/q both; export
  10.8 / 10.7 s; embed p50 12.5 / 13.3 ms/q; validation ~18-19 s each.
- RAM peak: 973 MB (X2M dense), 954 MB (global dense), 573 MB (global
  BM25 X2H), 570 MB (bm25-over-C X2H). Load gates unflagged throughout
  (la1 0.6..1.3 at step starts, limit 2.0, no waits). Wall total << 2 CPU-h.

## Could not observe / deviations

- C_pool (S=1600 2-bit shortlist) unobservable (stage-1 finding); Dr is exact
  dense over C_route, an upper bound on the live 2-bit pool — as preregistered.
- Engine-internal nomination floats/tie rule UNVERIFIED (binary-only),
  inherited from stage 1 (whose 50/50 consequence validation I reproduced on
  both my exports, 50/50 each).
- Encoder rev hash 1110a243… UNVERIFIABLE by hash (no git metadata in the
  staged dir); verified by consequence: same staged dir x1/c-fuse-4 used +
  self-test min cosine 1.0000000 (x1's own position).
- Gap closure n/a (no HIST unrestricted arms exist on X2) — reported, not
  tested. No replay (not in PREREG14).
- DEVIATION 1 (labelled, secondary only): content-word overlap uses the
  choices.md G6 frozen substitute, NOT lint.py's definition — lint.py is not
  on the VM (no lint.py in c-fuse-4 inputs; scratch/wave6/paper/x0/lint.py
  does not exist; bounded find over scratch/wave2 + scratch/wave6 found no
  query lint script). Overlap numbers are therefore NOT lint.py-comparable;
  the substitute is applied identically to both sets.
- DEVIATION 2 (pre-compute): choices.md carries one timestamped amendment
  (2026-11-06T03:12:00Z, before any compute, no number seen): the frozen
  stopword list's hand-count "111" corrected to the true 121 (list itself
  unchanged; code asserts 121), plus a clarification that the contrast
  bootstrap needs numpy like bootstrap_diff. No definition changed after
  seeing numbers.
- NOT DONE (out of scope per task list): the PREREG14 POST-HOC pooled
  analysis of X0/XF/XG/X2M/X2H — the task's secondary list does not ask for
  it. No other deviations from PREREG14 or choices.md (frozen
  2026-11-06T03:05:00Z, before any compute). BM25 walls include cold-mmap
  faults, as measured.

## Integrity

- 58 of 59 input hashes before == after (sha-before.txt/sha-after.txt;
  the single diff is my own choices.md, changed solely by the timestamped
  pre-compute amendment disclosed under Deviations — no number had been
  seen): PREREG14 dc20f5e1…e4c == PREREG14.sha256, X2M queries
  77c620cf…133c == brief/FREEZE-X2M.txt, X2H queries 0bba2a98…b19 ==
  brief/FREEZE-X2H.txt, sources 85fef3e8…9292 == PREREG14.
- Tests: test_cfuse5.py 26/26 OK (venv python, -W error::ResourceWarning,
  foreground, hermetic synthetic) and 19 pass + 7 numpy-skips under
  /usr/bin/python3. Unit file: test.log.
- Live services untouched (no queries sent); originals never edited;
  lease dir 310 MB (<= 3 GB); single process; nice -n 10.

## Files (lease /home/anshul/owner-hub/scratch/wave2/c-fuse-5)

choices.md, lib_cfuse5.py, export_candidates_x2m.py (+export_x2m.diff),
export_candidates_x2h.py (+export_x2h.diff), validation_x2m.py
(+validation_x2m.diff), validation_x2h.py (+validation_x2h.diff),
step_selftest_x2.py, step_embed_x2m.py, step_embed_x2h.py,
step_globalB_x2m.py, step_globalB_x2h.py, step_globalD_x2m.py,
step_globalD_x2h.py, step_dense_x2m.py, step_dense_x2h.py,
step_bm25_x2m.py, step_bm25_x2h.py, step_gates_x2.py, step_score_x2.py,
test_cfuse5.py, pylibs/bm25s (0.3.16 copy), Q_X2M.f32.npy (+Q_X2M.sha256,
f64 twin, qmeta_x2m.jsonl), Q_X2H.f32.npy (+Q_X2H.sha256, f64 twin,
qmeta_x2h.jsonl), candidates_x2m.npz, candidates_x2h.npz,
counts_x2m.jsonl, counts_x2h.jsonl, validation_x2m.json,
validation_x2h.json, selftest_x2.json, raw_B_X2M.jsonl, raw_D_X2M.jsonl,
raw_B_X2H.jsonl, raw_D_X2H.jsonl (global refs), raw_Dr_X2M.jsonl,
raw_Br_X2M.jsonl, raw_Dr_X2H.jsonl, raw_Br_X2H.jsonl,
raw_X2M_{Dr,Br,MMr,RRFr}.jsonl, raw_X2H_{Dr,Br,MMr,RRFr}.jsonl (300 q
each, {id,ret100,arm}), gates.json, metrics.json, run_X2M.json,
run_X2H.json, dense_cost_x2m.json, dense_cost_x2h.json,
bm25_cost_x2m.json, bm25_cost_x2h.json, *.log, test.log,
sha_inputs.lst, sha-before.txt, sha-after.txt, RESULT.md.

## What changed vs c-fuse-4 code (exact)

Copied scratch/wave2/c-fuse-4/*.py to the lease (14 per-set/score/gate/lib
files + test + selftest) and pylibs/. Per-set files (embed/export/
validation/globalB/globalD/dense/bm25 × {x2m,x2h}): ONLY the query file
path, Q/candidates/output names, ids in log tags, NQ 297 -> 300, and
lib_cfuse4 -> lib_cfuse5 (see export/validation .diffs; step diffs are the
same class). lib_cfuse5.py: LEASE/CFUSE4/X2M/X2H path constants + three
marked ADD-cfuse5 additions (verdict5, paired_contrast[+_observed],
STOPWORDS/overlap); all copied math byte-identical. step_selftest_x2.py:
output name only. step_gates_x2.py: c-fuse-4 per-set gate block run once
per set, merged into one gates.json. step_score_x2.py: c-fuse-4 per-set
scoring run once per set with per-set run guards, P1/P2 verdicts via
verdict5, plus the preregistered paired contrast and overlap.
test_cfuse5.py: c-fuse-4 tests + verdict/overlap/contrast tests.
