# NEGATIVE-RESULTS.md — campaign-186 (later evidence, original verdicts kept)

Campaign-186 (run `7b40af139e59488c8b2ebf195a132d48`, 2026-10-11) ran
later than the shipped freeze-v2 build, on the cap03-era tree. It
COMPLETED all 31 chunks / 1984 receipts (status `COMPLETE-10M`) but
carries an **ORIGINAL F2 overall FAIL** under the campaign's own
unchanged criteria. It ships here as further stress/evaluation evidence
WITH its failures — never as the build, never re-labelled.

## F2_10M_overall = FAIL (verbatim from RESULT-10M-186.md)

- Fresh-reader-process: EVERY stratum 124/124 exceed; p50 11.6–12.1 s,
  p95 13.3–13.9 s, max 14.3–15.9 s.
- Same-process add: p50 2.7–3.6 s, p95 14.7–16.2 s, 31–32/124 exceed
  (max 16.3–18.2 s); exceedances track the first add after a reader switch.
- Same-process correction: PASS in all four D-levels (p95 3.0–4.0 s,
  0 exceed).
- F1_10M: no overall flag in the file (F1_growth PENDING 100M, F3
  PENDING); acceptance p95 D1/add 4.996 s, D1/corr 1.47, D2/add 1.52,
  D2/corr 1.64, D3/add 7.05, D3/corr 3.20, D4/add 6.32, D4/corr 5.92;
  absolute p95 D1/add 5.392, D3/add 11.73, D4/add 14.26. Which metric is
  the F1 gate is a lane-owner/user reading, not decided here.
- Host labelled "A-WSL2 shared-host non-authoritative" by the harness
  itself; chunk-17 timing perturbed (see DISTURBANCES-ARCHITECT-SIDE.md).
- Qualification string in affected_analysis: "UNKNOWN: filtered coverage
  does not implement the 124/<=2 design" (about the affected-chunk
  subset analysis, not the 31-chunk verdict).

## Other preserved negatives (this publication)

- Fresh-store lanes (§1 of DATASETS.md): A1 trails bm25/dense on 4 of 5
  lanes with significant gaps (curated/scifact/nfcorpus recall@20;
  scifact nDCG vs bm25; nfcorpus nDCG vs dense) — all arms and misses in
  the per-lane `compare-*.md` files.
- Frozen rung: provisional latency MISS → specified FINDING
  "superlinear latency regime" (PHASE2-REPORT.md §4c).
- Attach wall: ~2 min NarrowIndex (re)attach per cold request (A3 probes).
- Fresh-process first request ~8–10 s exceeds 5 s (deployment condition).
- _186 release bytes NOT adopted: `release-sha256.txt`
  (`63ae6662…`) names no identifiable local artifact (absent from
  verdict/drivers/mirror; no tarball at RUN_ROOT) — recorded, unresolved.
- R9 10M RelIndex verification FAILED (OOM mid-oracle); under-2GB claim
  withdrawn. CONFIRM Phase-2 10M: launched, NO verdicts at hand-off
  (superseded by _186). Post-M2 snapshot full hash unrecorded (prefix
  `04cc6711…` only).
- Pony SCOPE §8 drop cause overturned: the corpus file was fine; the
  staging collision (fixed by 162) had hidden it — full account in
  `pony-collision-162.log`, not silently rewritten.

## Bundled _186 records (verbatim)

`RESULT-10M-186.md`, `RULINGS-186.md`, `RULINGS-186-ADDENDUM-1.md`,
`WINDOW-RELEASED-186.md`, `DISTURBANCES-ARCHITECT-SIDE.md`,
`pins-186.sha256` (`6ae0df4b…`, 17/17 OK re-verified at source),
`release-sha256.txt`, and the machine verdict
`verdict-7b40af13…022927.json` (`febc3010…`, 214953 B; parsed status
COMPLETE-10M, F2_10M_overall FAIL). The 31 receipt dirs
(`r000-004` … `r120-124`) and `vm-green/` (`green.log`, battery shas)
are inventoried in `ARTIFACT-INVENTORY.md`, not bundled.
