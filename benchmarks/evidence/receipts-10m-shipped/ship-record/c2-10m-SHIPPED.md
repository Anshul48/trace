# C2-10M SHIPPED (2026-10-08)

## Verdict

SHIP — independent readiness review (lane-READ10M) PASS on all
seven gate items, each formed from receipt bytes the reviewer
parsed or executed itself. Coordinator spot-verified (preflight,
clock tests, prove samples, fin5 bundle) and concurs.

## What shipped

- Store: `gs://tl-m2-runs-d1995b06/m2/c2-10m/` (verdict ok,
  pin `:0:95436`, 1.89 GB snapshots byte-exact vs receipt).
- Serving/query bytes + policy + criteria: see
  `c2-10m-package-draft.md` (FINAL), shas pinned; build bytes
  (freeze v2) distinguished from later freeze-v4 producer
  changes (100M scope, zero 10M impact per review §8.2).
- Query budgets M80-P100-A40 (adopted, doubly host-evidenced).
- Production clock: 1620–2358 ms warm / 3530 ms storage-cold —
  PASS vs 5 s with the deployment condition below.

## Deployment condition (part of the release)

Persistent serving process + resident MiniLM encoder
(demonstrated). Fresh-process first-request including encoder
load (~8–10 s warm) exceeds 5 s and is recorded, not hidden.
Operating outside this condition voids the latency claim;
correctness claims stand regardless.

## Recorded non-blockers (review §8)

1. Cold-sample thinness (n=1 each) — confirmation re-tests
   the clock at scale; wider cold series may be asked then.
2. Local-tree producer drift vs freeze v2 (100M collision,
   postdates all 10M receipts) — any future LOCAL build needs
   a freeze addendum first.
3. Two numpy-dependent tests re-verified from evidence bytes +
   pure-arithmetic test execution (no numpy on review host).

## Pending (not 10M)

100M confirmation (D11 repair → fit re-fire → campaign),
100M qualification, independent acceptance, bench, publication
of the 100M release. Growth endpoints were never 10M gates.
