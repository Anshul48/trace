# RESULT — c-fuse-2: C-FUSE stage 2 (PREREG11, fixed 0.5/0.5 MM fusion over C)

## Verdict (TEST, literal)

FUSION RETAINED (d_hit +0.055 [0.031,0.081]; d_mrr +0.071 [0.041,0.102])

Primary MMr vs Dr on 388 TEST queries: d_mrr=+0.071 >= +0.03 AND
d_hit=+0.055 >= +0.04 AND both CI lower bounds > 0 AND G1/G2 pass AND same C.
No harm (both d > -0.02). TEST ran exactly once (test_run.json attempts=1,
completed 2026-11-05T22:02:53Z); DEV smoke first with no verdict.

## TEST metrics (label = source ordinal; HEADLINE = style macro)

hit@10:

| arm | s0 quest | s1 keywd | s2 descr | micro | MACRO |
|-----|----------|----------|----------|-------|-------|
| Dr (baseline) | 0.855 | 0.511 | 0.839 | 0.727 | 0.735 |
| Br | 0.763 | 0.374 | 0.881 | 0.660 | 0.673 |
| MMr PRIMARY | 0.885 | 0.561 | 0.924 | 0.781 | 0.790 |
| RRFr | 0.878 | 0.561 | 0.941 | 0.784 | 0.793 |
| HIST B (unrestr.) | 0.756 | 0.367 | 0.890 | 0.657 | 0.671 |
| HIST D (unrestr.) | 0.855 | 0.511 | 0.839 | 0.727 | 0.735 |
| HIST MM (unrestr.) | 0.885 | 0.554 | 0.932 | 0.781 | 0.791 |

MRR@10:

| arm | s0 | s1 | s2 | micro | MACRO |
|-----|----|----|----|-------|-------|
| Dr | 0.671 | 0.349 | 0.680 | 0.558 | 0.567 |
| Br | 0.618 | 0.260 | 0.753 | 0.531 | 0.544 |
| MMr | 0.738 | 0.373 | 0.801 | 0.627 | 0.638 |
| RRFr | 0.692 | 0.353 | 0.760 | 0.591 | 0.602 |
| HIST B | 0.617 | 0.259 | 0.757 | 0.531 | 0.544 |
| HIST D | 0.671 | 0.349 | 0.680 | 0.558 | 0.567 |
| HIST MM | 0.738 | 0.371 | 0.800 | 0.625 | 0.636 |

Also: hit@1 macro Dr 0.479 / Br 0.487 / MMr 0.560 / RRFr 0.507;
hit@5 macro Dr 0.684 / Br 0.626 / MMr 0.752 / RRFr 0.722;
hit@20 macro Dr 0.796 / Br 0.706 / MMr 0.823 / RRFr 0.823 (full: metrics.json).

Secondary: RRFr vs Dr d_hit=+0.058 [0.027,0.092], d_mrr=+0.035 [0.004,0.066].
MMr vs Br (point macro diffs, no CI per frozen choices): hit@10 +0.117,
MRR@10 +0.094. Gap closure (MMr-Dr)/(HIST MM-Dr) on macro hit@10 = 0.992
(described, not tested). Ceiling: source outside C on TEST = 2 queries.
STYLE REVERSAL — per-style TEST hit@10 winners of {Dr,Br}: s0 Dr, s1 Dr,
s2 Br (s1 differs from s2). MM degenerate lists: 0. Bootstrap: 10,000/10,000
kept (0 skipped), 388 distinct doc_id units (= n TEST; cluster == query here).

## Gates (lists vs lists, no labels; DEV+TEST X0)

- G1 Br validation: 551/555 = 0.9928 >= 0.95 PASS (strict rate identical;
  0 SHORT queries). 4 diffs (X0-0193, X0-0226, X0-0370, X0-0456), ALL same-set
  order-only with exactly tied BM25 scores at the differing positions —
  the anticipated bm25s-quicksort vs ascending-ordinal tie-break artifact
  (choices.md C1). Scorer validated.
- G2 Dr validation: 553/553 = 1.0000 >= 0.95 PASS (denominator 553: 2 queries'
  global dense top-10 not fully inside C).
- G3 row budget: same C for all four arms (single load, asserted); |C| per
  query 97,565..118,741, mean 109,090 (13.4% of 812,545).
- G4 order: DEV smoke -> dev_done.json (no verdict), then TEST once. Kept.

DEV smoke (167, no verdict): hit@10 macro Dr 0.727 / Br 0.690 / MMr 0.786 /
RRFr 0.753; per-style s0/s1/s2: Dr .824/.489/.870, Br .745/.383/.942,
MMr .882/.489/.986, RRFr .863/.426/.971. MRR@10 macro: Dr 0.534 / Br 0.556 /
MMr 0.627 / RRFr 0.584. Full table: dev_done.json.

## Old-50 replay (EXPLORATORY, label = source ordinal, no verdict)

Dr 26/50 (mrr 0.384), Br 38/50 (mrr 0.655), MMr 37/50 (mrr 0.597);
beside HIST live final top-10 26/50 and keyword 41/50 (copied).
Failure split: all three arms miss exactly the same 5 outside-C queries
(q13 q23 s8-100 s8-180 s8-80, the stage-1 admission misses); in-C misses:
Dr 19 (= c-fuse-1 split exactly), Br 7, MMr 8.

## Cost

- Rows scored per query: |C| (above), identical for Dr/Br/MMr/RRFr.
- Extra keyword work: nonzero-BM25 rows in C per query 938..114,710
  (mean 68,865); BM25 score wall 2.06 s total (p50 3.7 ms/q, p90 6.6 ms/q),
  tokenise 0.02 s, selection 4.51 s; dense wall 40.5 s (605 queries).
- RAM peak: 975 MB (dense), 632 MB (bm25). Load gates unflagged throughout
  (la1 1.3..1.7 at step starts, limit 2.0, no waits). Wall total << 2 CPU-h.

## Could not observe / deviations

- C_pool (S=1600 2-bit shortlist) unobservable (stage-1 finding); Dr is exact
  dense over C_route, an upper bound on the live 2-bit pool — as preregistered.
- Engine-internal nomination floats/tie rule UNVERIFIED (binary-only),
  inherited from stage 1 (whose 50/50 consequence validation stands).
- No deviations from PREREG11 or choices.md (frozen 2026-11-05T21:57:49Z,
  before any compute). BM25 wall includes cold-mmap faults, as measured.

## Integrity

- 32 input hashes before == after (sha-before.txt/sha-after.txt, all OK):
  candidates.npz 1e87fedb…ded2ef5c, queries_frozen fab1d5e8…a28b71 (both ==
  prereg), PREREG11 063f4b86…b67 == PREREG11.sha256.
- Tests: test_cfuse2.py 15/15 OK (venv python, -W error::ResourceWarning,
  foreground, hermetic synthetic). Unit file: test.log.
- Live services untouched (no queries sent); originals never edited;
  lease dir 9 MB (<= 3 GB); single process; nice -n 10.

## Files (lease /home/anshul/owner-hub/scratch/wave2/c-fuse-2)

choices.md, lib_cfuse2.py, step_dense.py, step_bm25.py, step_gates.py,
step_dev.py, step_test.py, step_replay.py, test_cfuse2.py, pylibs/bm25s
(0.3.16 copy + dist-info), raw_Dr.jsonl, raw_Br.jsonl (605 q),
raw_TEST_{Dr,Br,MMr,RRFr}.jsonl (388 q, {id,ret100,arm}), gates.json,
dev_done.json, metrics.json, replay.json, dense_cost.json, bm25_cost.json,
test_run.json, *.log, test.log, sha-before.txt, sha-after.txt, RESULT.md.
