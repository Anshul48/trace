# RESULT: paper-fault-challenge-v0 — what the receipt checker catches and misses

Date: 2026-11-05. Worker lease dir: /home/anshul/owner-hub/scratch/wave2/paper-fault-challenge-v0.
Inputs (read-only): inputs/check_receipts.py, inputs/banned.txt, inputs/receipts.json
(104 entries), inputs/draft-v1.html, inputs/corrections.md. No original was edited;
all faults were applied to per-case copies.

## Headline
- Seeded faults: 18 (2 per required class a..i). Checker caught 10, missed 8.
- Controls: 6/6 pass (rc=0), as predicted.
- Baseline (unmodified draft + receipts): rc=0, "85 receipted spans, 276 text segments clean".
- Frozen predictions of checker outcome: 18/18 correct. The one frozen
  single-reader prediction that was wrong: F-i1 was predicted 'neither' but the
  cited H-line names both arms, so the second-pass verdict is 'yes'.
- selected seeded faults; no population error rate; no claim about human reviewers.

## Counts by class (checker caught / seeded)
| class | meaning | caught | missed |
| a | bare digit-form number, no receipt span | 2 (rule iv) | 0 |
| b | span id missing from receipts.json | 2 (rule i) | 0 |
| c | pinned file changed after hashing (copy, old sha) | 2 (rule ii) | 0 |
| d | span text differs from receipted value | 2 (rule iii) | 0 |
| e | correct numeral, wrong arm/unit/denominator | 0 | 2 |
| f | spelled-out number contradicting receipted digit | 0 | 2 |
| g | unsupported prospective-registration claim ('none attested') | 0 | 2 |
| h | banned phrase from banned.txt | 2 (banned) | 0 |
| i | receipt id reused for a different quantity | 0 | 2 |
| control | harmless edits, must pass | 6 pass | 0 |

## Every miss (checker rc=0; all marked 'manual review needed' in matrix.tsv)
- F-e1 (e): arm swap — sentence claims keyword 26/50, dense 41/50; spans intact.
- F-e2 (e): denominator swap — 0.9985 'of all rows' instead of 'of the exact top 10'.
- F-f1 (f): 'sixty test searches' in words beside receipted 50.
- F-f2 (f): 'four hundred' held out in words; 167+400=567 vs receipted 555.
- F-g1 (g): 'Study E1 was prospectively frozen' vs table row E1 'none attested'.
- F-g2 (g): 'Study E6 was prospectively registered' vs table row E6 'none attested'.
- F-i1 (i): flat arm reported as 31/50 citing the expansion-arm receipt.
- F-i2 (i): dense arm reported as 41/50 citing the keyword-arm receipt.

## Every catch (rc=1, exactly 1 failure line each)
- F-a1: `UNRECEIPTED NUMBER '77' (int)` rule (iv).
- F-a2: `UNRECEIPTED NUMBER '0.79' (decimal)` rule (iv).
- F-b1: `UNKNOWN RECEIPT 'no-such-receipt'` rule (i).
- F-b2: `UNKNOWN RECEIPT 'x1-gap-TYPO'` rule (i).
- F-c1: `RECEIPT e2a-hit-26-50: sha256 mismatch` rule (ii).
- F-c2: `RECEIPT x0-n: sha256 mismatch` rule (ii).
- F-d1: `SPAN/VALUE MISMATCH e2d-bm25-41-50: span '42/50' != value '41/50'` rule (iii).
- F-d2: `SPAN/VALUE MISMATCH e1a-recall-09985: span '0.9986' != value '0.9985'` rule (iii).
- F-h1: `BANNED WORD 'breakthrough'` (banned).
- F-h2: `BANNED WORD 'beats HNSW'` (banned).

## Controls outcomes (all rc=0)
C1 abstract reword; C2 year 2026 (allow-listed); C3 citation [12] (allow-listed);
C4 Section 4 ref (allow-listed); C5 single digit 3; C6 equation label (12)
(allow-listed). No false positives.

## Second pass: single-reader verdicts (sentence + cited receipt line only)
Labelled single-reader judgment by the worker, not a measurement of human accuracy.
- yes (16): F-a1, F-a2, F-b1, F-b2, F-d1, F-d2, F-e1, F-e2, F-f1, F-f2, F-g1,
  F-g2, F-h1, F-h2, F-i1, F-i2 (one line each in matrix.tsv).
- needs more context (2): F-c1, F-c2 — the cited receipt lines are intact in the
  tampered copies; the appended tamper line is invisible to a read of the cited
  line and shows only via hash recomputation (which is exactly what the checker
  automates).
- no (0).

## How to reproduce
`cd` to the lease dir and run `nice -n 10 python3 run_challenge.py` (stdlib only).
It rebuilds cases/*/fault.html + receipts copies, reruns the checker (25 runs:
1 baseline + 18 faults + 6 controls), rewrites runs.tsv, and re-merges
matrix.tsv from runs.tsv + verdicts.tsv. Per-case checker output is kept in
cases/<ID>/checker.out and baseline.out. Fault specs in run_challenge.py match
faults.md (frozen 2026-11-05T22:11Z, before any checker run); anchors are
asserted (F-b1: 3 occurrences, first used; F-b2: 2 occurrences, first used;
all others unique).

## Files
- faults.md (frozen fault + control specs with pre-run predictions)
- run_challenge.py (stdlib runner)
- runs.tsv (id, class, predicted, rc, caught, rule, nfail)
- verdicts.tsv (step-3 one-line manual verdicts)
- matrix.tsv (fault id, class, predicted, checker caught Y/N, rule, manual verdict)
- cases/<ID>/{fault.html,receipts.json,checker.out} (18 faults + 6 controls)
- pinned_F-c1.md, pinned_F-c2.md (tampered pinned-file copies), baseline.out
- RESULT.md (this file)
