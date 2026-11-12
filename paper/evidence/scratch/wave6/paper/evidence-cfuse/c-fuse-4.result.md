# RESULT — c-fuse-4: C-FUSE stage 4 (PREREG13 second-author-family confirmation on XG)

## Verdict (XG TEST, literal, first)

CONFIRMED-2F (d_hit +0.087 [0.050,0.125]; d_mrr +0.120 [0.084,0.156])

Primary MMr vs Dr on 297 XG queries (all TEST, styles 99/98/100):
d_hit=+0.087 clears the preregistered +0.04 bar, d_mrr=+0.120 clears +0.03,
both CI lower bounds > 0, and G1/G2/G3 pass — so per PREREG13 the verdict is
CONFIRMED-2F. No harm (both d > -0.02). XG scored exactly once (xg_run.json
attempts=1, completed 2026-11-06T02:04:39Z); gates ran first with labels
sealed; no DEV (all XG rows are TEST per prereg).

## XG metrics (label = source ordinal; HEADLINE = style macro)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.778 | 0.408 | 0.850 | 0.680 | 0.679 |
| Br | 0.869 | 0.357 | 0.930 | 0.721 | 0.719 |
| MMr PRIMARY | 0.889 | 0.459 | 0.950 | 0.768 | 0.766 |
| RRFr | 0.899 | 0.449 | 0.950 | 0.768 | 0.766 |
| global BM25 (context) | 0.869 | 0.357 | 0.930 | 0.721 | 0.719 |
| global dense (context) | 0.778 | 0.408 | 0.850 | 0.680 | 0.679 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.610 | 0.244 | 0.699 | 0.519 | 0.517 |
| Br | 0.734 | 0.247 | 0.825 | 0.604 | 0.602 |
| MMr | 0.784 | 0.290 | 0.838 | 0.639 | 0.637 |
| RRFr | 0.736 | 0.287 | 0.793 | 0.607 | 0.605 |
| global BM25 | 0.733 | 0.245 | 0.825 | 0.603 | 0.601 |
| global dense | 0.610 | 0.244 | 0.699 | 0.519 | 0.517 |

Also: hit@1 macro Dr 0.440 / Br 0.540 / MMr 0.567 / RRFr 0.517;
hit@5 macro Dr 0.628 / Br 0.678 / MMr 0.742 / RRFr 0.712;
hit@20 macro Dr 0.749 / Br 0.763 / MMr 0.817 / RRFr 0.813 (full: metrics.json).
Per-style MMr-Dr hit@10: s0 +0.111, s1 +0.051, s2 +0.100 (fusion gains in all
three styles, largest on the prose styles).

Secondary: RRFr vs Dr d_hit=+0.087 [0.047,0.128], d_mrr=+0.088
[0.054,0.121] (both CIs exclude 0; the RRF sensitivity is also positive
here, unlike on XF). MMr vs Br (inside C, with CI): d_hit=+0.047
[0.017,0.080], d_mrr=+0.035 [0.006,0.067] — on XG, fusion beats
keyword-inside-C (and global BM25 0.719 < MMr 0.766); not part of this
verdict. Ceiling: source outside C on XG = 2 queries. STYLE REVERSAL —
per-style hit@10 winners of {Dr,Br}: s0 Br, s1 Dr, s2 Br (keyword wins the
prose styles, dense wins the keyword style). MM degenerate lists: 0.
Bootstrap: 10,000/10,000 kept (0 skipped), 297 distinct doc_id units
(= n XG; cluster == query here), seed 20261109.

Family contrast (descriptive, copied from the filed RESULTs, no cross-set
test): X0 TEST (Muse-authored) "FUSION RETAINED (d_hit +0.055
[0.031,0.081]; d_mrr +0.071 [0.041,0.102])", winners s0 Dr, s1 Dr, s2 Br
(STYLE REVERSAL); XF (Muse-authored, fresh passages) "NOT CONFIRMED (d_hit
+0.033 [0.001,0.066]; d_mrr +0.037 [0.005,0.069])", winners all Dr (NO STYLE
REVERSAL); XG (Haiku-authored, fresh passages) CONFIRMED-2F as above,
winners s0 Br, s1 Dr, s2 Br (STYLE REVERSAL). The XG effect is the largest
of the three; the Br-vs-Dr pattern also differs by set (Br wins prose
styles only on XG).

## Gates (lists vs lists, no labels; 297 XG)

- G1 Br validation: 297/297 = 1.0000 >= 0.95 PASS (strict rate identical;
  0 SHORT queries, 0 mismatches). Scorer validated with no tie-break
  diffs on this set.
- G2 Dr validation: 296/296 = 1.0000 >= 0.95 PASS (denominator 296: one
  query's global dense top-10 is not fully inside C).
- G3 row budget: same C for all four arms (single load, asserted); |C| per
  query 99,858..116,930, mean 108,592 (13.4% of 812,545).
- Order: gates -> score ONCE (no DEV exists). Kept. xg_run.json attempts=1.

## Exporter + encoder provenance

- Encoder: x1 x1enc.py/x1common.py imported read-only (no copy, no edit);
  staged all-MiniLM-L6-v2, CPU, normalize+explicit L2, one-by-one. Self-test
  gate: 50 old probes vs h2h embeds, min cosine 1.0000000 >= 0.9999 PASS
  (selftest_xg.json). Q_xg.f32.npy sha256
  1f429fbfbb6dc78b28eeb46598b8dcf133bf214d9b8d288e5bf1b265a74c870f
  (f64 twin 0c72f60185c93862fa0cfdfc32ddba98f04091f233c97ebc00b26a40e9ef295c).
- Exporter: export_candidates.py copied to lease; the ONLY changes are
  parameter-only (export.diff): LEASE path, XG query file + Q_xg.f32.npy for
  X0 inputs, outputs candidates_xg.npz/counts_xg.jsonl; nomination math
  (NP=3000, f64 qnorm, nominate, members, merge, sorted int32) untouched.
  Exported 347 = 297 XG + 50 old (old-50 = regression check, unscored).
- Re-validation of the parameterised exporter (validation_xg.py, validate.py
  math + C-identity assert): my 50 old-search C arrays bit-identical to
  filed candidates.npz 50/50; restricted-vs-live top-10 agree (set+order)
  50/50; exact-recipe 50/50. Stage-1 validation reproduced.

## Cost

- Rows scored per query: |C| (above), identical for Dr/Br/MMr/RRFr.
- Extra keyword work: nonzero-BM25 rows in C per query 2,801..115,110
  (mean 85,191); BM25 score wall 1.32 s total (p50 4.4 ms/q, p90 7.9 ms/q),
  tokenise 0.01 s, selection 2.46 s; dense-over-C wall 19.7 s (297 queries);
  global BM25 p50 7.6 / p90 29.7 ms/q; export 10.4 s; embed p50 13.1 ms/q.
- RAM peak: 969 MB (dense), 952 MB (global dense), 586 MB (global BM25),
  574 MB (bm25-over-C). Load gates unflagged throughout (la1 0.2..1.0 at
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
- Gap closure n/a (no HIST unrestricted arms exist on XG) — reported, not
  tested. No replay (not in PREREG13).
- No deviations from PREREG13 or choices.md (frozen 2026-11-06T01:59:37Z,
  before any compute). The exporter WAS hard-wired to X0 files, so the
  prereg-allowed parameter-only change was made (export.diff, stated above)
  and its 50-old-search validation re-run: 50/50 still agrees. BM25 walls
  include cold-mmap faults, as measured.

## Integrity

- 55 input hashes before == after (sha-before.txt/sha-after.txt, all OK):
  PREREG13 9f027355…0d4f5 == PREREG13.sha256, XG queries ac87309c…6b4 ==
  brief/FREEZE-XG.txt, PREREG11 063f4b86… == the c-fuse-2/3 recorded value.
- Tests: test_cfuse4.py 16/16 OK (venv python, -W error::ResourceWarning,
  foreground, hermetic synthetic) and 11 pass + 5 numpy-skips under
  /usr/bin/python3. Unit file: test.log.
- Live services untouched (no queries sent); originals never edited;
  lease dir 154 MB (<= 3 GB); single process; nice -n 10.

## Files (lease /home/anshul/owner-hub/scratch/wave2/c-fuse-4)

choices.md, lib_cfuse4.py, export_candidates_xg.py (+export.diff),
validation_xg.py (+validation.diff), step_selftest_xg.py, step_embed_xg.py,
step_globalB_xg.py, step_globalD_xg.py, step_dense_xg.py, step_bm25_xg.py,
step_gates_xg.py, step_score_xg.py, test_cfuse4.py, pylibs/bm25s (0.3.16
copy), Q_xg.f32.npy (+Q_xg.sha256, f64 twin, qmeta_xg.jsonl),
candidates_xg.npz, counts_xg.jsonl, validation_xg.json, selftest_xg.json,
raw_B_XG.jsonl, raw_D_XG.jsonl (global refs), raw_Dr_XG.jsonl,
raw_Br_XG.jsonl, raw_XG_{Dr,Br,MMr,RRFr}.jsonl (297 q, {id,ret100,arm}),
gates.json, metrics.json, xg_run.json, dense_cost_xg.json,
bm25_cost_xg.json, *.log, test.log, sha-before.txt, sha-after.txt, RESULT.md.
