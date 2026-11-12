# RESULT — c-fuse-6: C-FUSE stage 6 / X3 (PREREG15, overlap-controlled test: one author, two overlap conditions on the same 300 fresh passages)

## Primary verdict (first)

OVERLAP NOT SUPPORTED (D +0.000 [-0.050,0.050]; Dm +0.123 [0.076,0.170]; manip +0.561; dH +0.033 dL +0.033)

The manipulation check passes (mean lint overlap H minus L on the 300
common passages +0.561 >= 0.20), G1/G2/G3 pass for both sets, and each set
was scored exactly once — but the paired hit contrast D = d_hit(MMr-Dr|X3H)
minus d_hit(MMr-Dr|X3L) is +0.000 with CI [-0.050,0.050], so it meets
neither the D >= +0.03 bar nor the lower-CI-above-0 rule. Both conditions
show the identical observed fusion gain over routed dense on hit@10
(dH = dL = +0.0333: X3L per-style +0.010/+0.010/+0.080, X3H
+0.030/+0.040/+0.030 — a genuine coincidence, verified from the tables).
The same paired contrast on MRR is +0.123 [0.076,0.170] (CI excludes 0),
but PREREG15 defines the PRIMARY on d_hit, so the verdict stands; the mrr
contrast is reported alongside per the brief. This is PREREG15 pre-written
reading 3: NOT SUPPORTED with both conditions failing P1 — the earlier
passes are not reproduced by raising overlap with this author; overlap is
withdrawn as an explanation and the five-set pattern is reported as
unexplained.

## Per-set verdicts (PREREG14 style, literal)

X3L (low overlap): NEITHER (P1 d_hit +0.033 [-0.011,0.078]; d_mrr +0.002 [-0.036,0.042]; P2 d_hit +0.243 [0.189,0.299]; d_mrr +0.127 [0.097,0.158])

X3H (high overlap): NEITHER (P1 d_hit +0.033 [0.014,0.055]; d_mrr +0.125 [0.097,0.155]; P2 d_hit +0.000 [0.000,0.000]; d_mrr +0.000 [-0.021,0.020])

On X3L, P1 fails the +0.04 hit bar (+0.033) with both CIs crossing 0, while
P2 passes by a wide margin (keyword-only is far below fusion at low
overlap). On X3H, P1 fails the +0.04 hit bar (+0.033) even though both of
its CIs exclude 0, and P2 fails because MMr and Br tie exactly on hit@10
(macro 0.990 both, d_hit +0.000 [0.000,0.000]). Gates ran first with labels
sealed; run_X3L.json and run_X3H.json attempts=1 (finished
2026-11-06T05:10:21Z / 05:10:25Z); no DEV (all rows TEST per prereg).

## X3L metrics (label = source ordinal; HEADLINE = style macro; n=300, 100/100/100)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.500 | 0.510 | 0.470 | 0.493 | 0.493 |
| Br | 0.230 | 0.250 | 0.370 | 0.283 | 0.283 |
| MMr PRIMARY | 0.510 | 0.520 | 0.550 | 0.527 | 0.527 |
| RRFr | 0.490 | 0.500 | 0.520 | 0.503 | 0.503 |
| global BM25 (context) | 0.210 | 0.240 | 0.380 | 0.277 | 0.277 |
| global dense (context) | 0.500 | 0.510 | 0.480 | 0.497 | 0.497 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.278 | 0.258 | 0.305 | 0.281 | 0.281 |
| Br | 0.125 | 0.118 | 0.225 | 0.156 | 0.156 |
| MMr | 0.284 | 0.220 | 0.346 | 0.283 | 0.283 |
| RRFr | 0.263 | 0.210 | 0.319 | 0.264 | 0.264 |
| global BM25 | 0.118 | 0.115 | 0.231 | 0.154 | 0.154 |
| global dense | 0.278 | 0.258 | 0.307 | 0.281 | 0.281 |

Also (macro): hit@1 Dr 0.190 / Br 0.107 / MMr 0.193 / RRFr 0.170;
hit@5 Dr 0.400 / Br 0.217 / MMr 0.423 / RRFr 0.380;
hit@20 Dr 0.577 / Br 0.363 / MMr 0.620 / RRFr 0.623 (full: metrics.json).
Per-style MMr-Dr hit@10: s0 +0.010, s1 +0.010, s2 +0.080; MMr-Br hit@10:
s0 +0.280, s1 +0.270, s2 +0.180.

## X3H metrics (n=300, 100/100/100)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.960 | 0.950 | 0.960 | 0.957 | 0.957 |
| Br | 0.990 | 0.990 | 0.990 | 0.990 | 0.990 |
| MMr PRIMARY | 0.990 | 0.990 | 0.990 | 0.990 | 0.990 |
| RRFr | 0.980 | 0.990 | 0.990 | 0.987 | 0.987 |
| global BM25 (context) | 1.000 | 1.000 | 0.990 | 0.997 | 0.997 |
| global dense (context) | 0.960 | 0.950 | 0.960 | 0.957 | 0.957 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.784 | 0.801 | 0.869 | 0.818 | 0.818 |
| Br | 0.903 | 0.965 | 0.962 | 0.943 | 0.943 |
| MMr | 0.912 | 0.932 | 0.985 | 0.943 | 0.943 |
| RRFr | 0.877 | 0.897 | 0.946 | 0.907 | 0.907 |
| global BM25 | 0.913 | 0.975 | 0.962 | 0.950 | 0.950 |
| global dense | 0.784 | 0.801 | 0.869 | 0.818 | 0.818 |

Also (macro): hit@1 Dr 0.737 / Br 0.913 / MMr 0.910 / RRFr 0.850;
hit@5 Dr 0.923 / Br 0.987 / MMr 0.990 / RRFr 0.967;
hit@20 Dr 0.963 / Br 0.990 / MMr 0.990 / RRFr 0.987.
Per-style MMr-Dr hit@10: s0 +0.030, s1 +0.040, s2 +0.030; MMr-Br hit@10:
s0 +0.000, s1 +0.000, s2 +0.000 (exact tie in every style).

## Secondary (no gate)

- RRFr vs Dr: X3L d_hit=+0.010 [-0.047,0.068], d_mrr=-0.016 [-0.061,0.029]
  (both CIs cross 0); X3H d_hit=+0.030 [0.013,0.051], d_mrr=+0.089
  [0.065,0.114] (both CIs exclude 0).
- Source outside C: X3L 3 queries, X3H 2 queries.
- Global hit@10 (macro): X3L BM25 0.277 / dense 0.497; X3H BM25 0.997 /
  dense 0.957 (MRR in tables above).
- Lint overlap per set (inputs/lint.py check()[1], computed BEFORE any
  retrieval in step_overlap_x3.py): X3L mean 0.2162 median 0.2000; X3H mean
  0.7770 median 0.7778 (n=300 each, 300/300 common passages). Manipulation
  gap +0.5609 >= 0.20 PASS.
- Paired mrr contrast (reported per brief, not part of the PRIMARY rule):
  Dm = +0.123 [0.076,0.170] (dH +0.125, dL +0.002; paired cluster bootstrap
  over doc_id, 10,000/10,000 kept, seed 20261109).
- Per-style winners of {Dr,Br} hit@10: X3L s0/s1/s2 all Dr; X3H s0/s1/s2
  all Br — NO STYLE REVERSAL on either set.
- Bootstrap: 10,000/10,000 kept (0 skipped) for all primary/secondary
  comparisons and both paired contrasts, 300 distinct doc_id units per set
  (= n; cluster == query here), seed 20261109. No harm either set
  (no MMr-vs-Dr d <= -0.02). MM degenerate lists: 0 both sets.

## Gates (lists vs lists, no labels; 300 queries/set)

- G1 Br validation: X3L 297/300 = 0.9900 PASS (strict identical, 0 SHORT;
  3 mismatches, all lenF >= 10 score-tie order diffs: X3-0109 lenF=77
  firstdiff=7, X3-0277 lenF=52 firstdiff=5, X3-0292 lenF=79 firstdiff=2);
  X3H 299/300 = 0.9967 PASS (0 SHORT; X3-0239 lenF=99 firstdiff=5).
  >= 0.95 both.
- G2 Dr validation: X3L 298/298 = 1.0000 PASS (denom 298: two queries'
  global dense top-10 not fully inside C); X3H 300/300 = 1.0000 PASS.
- G3 row budget: same C for all four arms per set (single load,
  asserted); |C| per query X3L 98,672..116,694 mean 108,664 (13.4% of
  812,545), X3H 99,771..117,562 mean 109,001 (13.4%).
- Order: gates -> score ONCE per set (no DEV exists). Kept.

## Exporter + encoder provenance

- Encoder: x1 x1enc.py/x1common.py imported read-only (no copy, no edit);
  staged all-MiniLM-L6-v2, CPU, normalize+explicit L2, one-by-one.
  Self-test gate (once, before either set): 50 old probes vs h2h embeds,
  min cosine 1.0000000 >= 0.9999 PASS (selftest_x3.json).
  Q_X3L.f32.npy sha256 0f37078c7032167de533284eabddeefa68662a094684bac8
  93ead2539f9b7d00 (f64 twin ad61c90210eaaba185ba5c290e9c20e016b8b4e0
  caec8bf7d7c3abc10d44e15b); Q_X3H.f32.npy sha256 330eb1aae7a16d17a410
  b6696eb8bfb234d8a20b6736df963405ca9defecb8a6 (f64 twin 7d13a37989
  850364f02fccc2b642cf491a2893e1e66d9169cf611a07ded64a6b).
- Exporter: c-fuse-5 export_candidates_x2m/x2h.py copied per set; the ONLY
  changes are parameter-only (export_x3l.diff / export_x3h.diff): LEASE
  path, X3L/X3H query file + Q file, outputs candidates_x3l.npz /
  candidates_x3h.npz + counts; nomination math (NP=3000, f64 qnorm,
  nominate, members, merge, sorted int32) untouched. Two npz were required
  because both frozen files use ids X3-0000..X3-0299 (namespaces collide).
  Each export 350 = 300 X3S + 50 old (old-50 = regression check, unscored).
- Re-validation per npz (validation_x3l.py / validation_x3h.py,
  validate.py math + C-identity assert, diffs recorded): my 50 old-search
  C arrays bit-identical to filed candidates.npz 50/50 each;
  restricted-vs-live top-10 agree (set+order) 50/50 each; exact-recipe
  50/50 each. Stage-1 validation reproduced on both exports.

## Cost

- Rows scored per query: |C| (above), identical for Dr/Br/MMr/RRFr per set.
- Extra keyword work: nonzero-BM25 rows in C per query X3L 711..114,143
  (mean 61,249), X3H 1,241..111,213 (mean 65,167); BM25 score wall X3L
  0.73 s / X3H 0.87 s total (p50 2.4 / 2.9 ms/q, p90 4.9 / 5.6 ms/q),
  tokenise 0.01 s each, selection 1.96 / 2.05 s; dense-over-C wall
  20.3 / 19.6 s; global BM25 p50 7.2 / 7.9 ms/q, p90 33.6 / 33.1 ms/q;
  export 27.0 / 41.8 s; embed p50 12.9 / 13.4 ms/q; validation ~21 s each.
- RAM peak: 973 MB (X3H dense), 969 MB (X3L dense), 956 MB (global dense),
  551 MB (global BM25 X3L). Load gates unflagged throughout (several steps
  waited out la1 2.0..2.7 at start, all ran with flagged=False). Wall
  total << 2 CPU-h. bm25_cost/dense_cost JSONs carry per-query rows.

## Could not observe / deviations

- C_pool (S=1600 2-bit shortlist) unobservable (stage-1 finding); Dr is exact
  dense over C_route, an upper bound on the live 2-bit pool — as preregistered.
- Engine-internal nomination floats/tie rule UNVERIFIED (binary-only),
  inherited from stage 1 (whose 50/50 consequence validation I reproduced on
  both my exports, 50/50 each).
- Encoder rev hash 1110a243… UNVERIFIABLE by hash (no git metadata in the
  staged dir); verified by consequence: same staged dir x1/c-fuse-5 used +
  self-test min cosine 1.0000000 (x1's own position).
- Gap closure n/a (no HIST unrestricted arms exist on X3) — reported, not
  tested. No replay (not in PREREG15). Manual naturalness sample of 20 per
  condition (PREREG15 secondary) is the lead's, not the hand's — NOT DONE
  here. The 50-probe self-test is the c-fuse-5 50 old-search self-test
  (same probes), min cosine gate as specified.
- No deviations from PREREG15 or choices.md (frozen 2026-11-06T04:57:00Z,
  before any compute): overlap uses the lint.py definition as preregistered
  (step_overlap_x3.py ran before any retrieval; no substitute needed this
  stage). BM25 walls include cold-mmap faults, as measured.

## Integrity

- 61 of 61 input hashes before == after (sha-before.txt/sha-after.txt):
  PREREG15 46c489c6…cc740 == PREREG15.sha256, X3L queries 705bc7e0…b81e ==
  brief/FREEZE-X3L.txt, X3H queries c2e84d3c…3d89 == brief/FREEZE-X3H.txt,
  sources db36f071…be0e7 == PREREG15, lint.py unchanged.
- Tests: test_cfuse6.py 31/31 OK (venv python, -W error::ResourceWarning,
  foreground, hermetic synthetic) and 24 pass + 7 numpy-skips under
  /usr/bin/python3. Unit file: test.log.
- Live services untouched (no queries sent); originals never edited;
  lease dir 310 MB (<= 3 GB); single process; nice -n 10.

## Files (lease /home/anshul/owner-hub/scratch/wave2/c-fuse-6)

choices.md, lib_cfuse6.py, export_candidates_x3l.py (+export_x3l.diff),
export_candidates_x3h.py (+export_x3h.diff), validation_x3l.py
(+validation_x3l.diff), validation_x3h.py (+validation_x3h.diff),
step_selftest_x3.py, step_embed_x3l.py, step_embed_x3h.py,
step_overlap_x3.py, step_globalB_x3l.py, step_globalB_x3h.py,
step_globalD_x3l.py, step_globalD_x3h.py, step_dense_x3l.py,
step_dense_x3h.py, step_bm25_x3l.py, step_bm25_x3h.py, step_gates_x3.py,
step_score_x3.py, test_cfuse6.py, pylibs/bm25s (0.3.16 copy),
Q_X3L.f32.npy (+Q_X3L.sha256, f64 twin, qmeta_x3l.jsonl), Q_X3H.f32.npy
(+Q_X3H.sha256, f64 twin, qmeta_x3h.jsonl), candidates_x3l.npz,
candidates_x3h.npz, counts_x3l.jsonl, counts_x3h.jsonl,
validation_x3l.json, validation_x3h.json, selftest_x3.json,
overlap_x3.json, raw_B_X3L.jsonl, raw_D_X3L.jsonl, raw_B_X3H.jsonl,
raw_D_X3H.jsonl (global refs), raw_Dr_X3L.jsonl, raw_Br_X3L.jsonl,
raw_Dr_X3H.jsonl, raw_Br_X3H.jsonl, raw_X3L_{Dr,Br,MMr,RRFr}.jsonl,
raw_X3H_{Dr,Br,MMr,RRFr}.jsonl (300 q each, {id,ret100,arm}), gates.json,
metrics.json, run_X3L.json, run_X3H.json, dense_cost_x3l.json,
dense_cost_x3h.json, bm25_cost_x3l.json, bm25_cost_x3h.json, *.log,
test.log, sha_inputs.lst, sha-before.txt, sha-after.txt, RESULT.md.

## What changed vs c-fuse-5 code (exact)

Copied scratch/wave2/c-fuse-5/*.py to the lease (17 files) and pylibs/.
Per-set files (embed/export/validation/globalB/globalD/dense/bm25 ×
{x3l,x3h}): ONLY the query file path, Q/candidates/output names, ids in
log tags, and lib_cfuse5 -> lib_cfuse6 (see export/validation .diffs;
step diffs are the same class). lib_cfuse6.py: LEASE/CFUSE5/X3L/X3H path
constants + two marked ADD-cfuse6 additions (verdict6, manip_check); all
copied math byte-identical (verdict5, paired_contrast, overlap/STOPWORDS
carried over; paired_contrast reused unchanged for both the hit and the
mrr contrast; the overlap substitute is carried code only, unused for any
stage-6 number). step_selftest_x3.py: output name only. step_gates_x3.py:
c-fuse-5 per-set gate block run once per set, merged into one gates.json.
step_score_x3.py: c-fuse-5 per-set scoring run once per set with per-set
run guards and verdict5 per-set lines, plus the preregistered PRIMARY
(hit contrast + mrr contrast + verdict6) and overlap READ from
overlap_x3.json instead of recomputed. step_overlap_x3.py: NEW small
pre-retrieval step (lint.py check()[1] per query, manip gap, means/
medians) — required by PREREG15 G6b since lint.py is available this stage.
test_cfuse6.py: c-fuse-5 tests + verdict6/manip tests.
