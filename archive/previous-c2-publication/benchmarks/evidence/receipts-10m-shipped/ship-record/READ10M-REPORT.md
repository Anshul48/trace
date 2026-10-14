# C2 10M-readiness INDEPENDENT review — REPORT

Reviewer: C2 lane-READ10M (independent). Date: 2026-10-08. LOCAL ONLY
(no VM contact; bucket objects referenced by recorded shas only).
READ-ONLY on all product/harness/test files — this lane dir is the
sole write area. Method: every verdict below was formed from receipt
bytes I parsed or executed myself; builder REPORT prose was used only
to locate receipts, never as evidence.

## 0. Top finding: SHIP

**SHIP — all seven 10M gate items PASS on their receipts.** No FAIL,
no GAP, no open 10M-scope STOP. Two non-blocking observations are
recorded in §8 (cold-sample thinness, local-tree producer drift owned
by the 100M collision) — neither touches a 10M receipt.

## 1. Verdict table (requirement → receipt → verdict)

| # | Requirement | Receipt (bytes I verified) | Verdict |
|---|---|---|---|
| 1 | C2-10M receipt: BUILD ok, pins, L1/L2/L3 bit-exact + L4-shape + control, preflight 13/13 | `lane-SSCALE/evidence/BUILD-RECEIPT.json` (ok, pin `:0:95436`, keyed/bound/profile); local manifest sha `54c64001…` == `C2-10M-UPLOAD.json` manifest sha + roundtrip 4/4; `DIFF-RECEIPT-L4D-c2.json` PASS (L1 58629 occ, L2 2580, L3 5539/1667, desc 0.0; L4-shape 5/5 + L4-control 5/5); `C2-PREFLIGHT-L4D.json` 13/13 PASS; original L4 FAIL receipts preserved both arms | PASS |
| 2 | Producer closure: freeze v2, P-1→P-2 differential, P-3 fix | `c2-FREEZE-v2.json` (89 files; F1 0 bad; F9 44/44 loaded modules in-freeze — receipt lists exactly 44); `P1P2-DIFF-C/R.json` PASS both arms s1/s2/s3 all aspects; P3 `test-p3-prefail.log` 7 failures → `test-p3-green.log` 0 failures; SF1 pin (`sf1-pin.md`: test `e95f2bab…` re-hashed match, generation `92970939…`) | PASS |
| 3 | Seating re-proof: VM 36/36 + local audit; ruling (a) doc-level verified by me; ruling (b) | VM `lane-SHEP143/evidence/reproof-assessment.json` (36/36 row-level, winner, tiebreak 238096<452175, probes 6/6, V1 green) on recorded fixed bytes (dossier `93871fb3`, generation `92970939`, CRITERIA `e7d0139a` in `quiet-timing-evidence.json`); local `seat-compare.json` + `reproof-prediction-audit.json` PASS; **my own sweep-byte comparison: c3 doc-level 18/18, F-35 missed 18/18, r2 0→2 18/18**; aid-rotation mechanism confirmed in `identity.py` + `ingest.py` source (uuidv7 revision in atom preimage, no import path) — no evidence contradicts ruling (a)/(b) | PASS |
| 4 | S-scale correctness 5/5 (pins `:0:95436`→`:0:95437`, retire→republish→exclusion) | `lane-SSCALE/evidence/sscale-fin5/`: `sscale-evidence.json` checks 5/5 true (`ack_within_5s` false = shared-host non-qual timing, correctly not claimed); pin triple 95436→95437; `sscale-fresh-verify.json`: `retired_docs=[wikipedia:27701]`, 0/10 fresh entries from it, digest `c61661bb…`→`0bc076a8…` changed, 10/10 `text_ok` | PASS |
| 5 | 5 s gate: production clock vs 5 s warm+cold, §4 split, deployment condition, all-in alongside, no PASS by subtraction | `lane-S5S/evidence/`: PROVE-RECORD + `s5s-prove-evidence.json` (fresh warm 1786–2358 ms n=3), `cold-answer.json` (fresh cold 2593.1+937.8=3530.9, 314.5 MB phys read), `s5s-serve-warm.json` (resident warm 1620–2081 n=5), `serve-cold.json` (cold-first 2968); every sample's arithmetic closed by me (production=attach+query exact; e2e parts sum within ~10 ms); `test_prove_clock.py` EXECUTED by me: S5S-CLOCK-PASS; single-attach + digest `0bc076a8…` identical across all modes/runs; 45 blocks verified ON the clock inside attach; encoder/digest fenced per §4 with explicit resident-encoder deployment condition + fresh-including-encoder disclosed as exceeding | PASS |
| 6 | Q adoption (M80-P100-A40: winner evidence + double-host agreement) | Winner @ 20 spans + exact work tiebreak 238096<452175 in BOTH the VM assessment and the local prediction audit; same store + same code shas both hosts; probes 6/6 + V1 re-run green both hosts (local `verdicts`: all_shape_complete, overflow_forced_live, retirement_clean; fork `:0:65070` doc 16881, `served_retired_n=0`); V1-READY flag present (closes Q REPORT §3 pending) | PASS |
| 7 | No open 10M-scope STOPs | G3: anchors-v1 `9728129b…` re-hashed match, V1 adopted; c3-outer/p3/p4/p6 standing classified residuals, V2/V3 honest negatives (no STOP armed); F1/F7: executable bindings fail-closed UNEXECUTED awaiting scale inputs (G6), harness D1–D6/D8 FIXED battery ALL PASS, D7 disposed by coordinator ruling; D1/D2: PAR132 GREEN zero flips + G6 D1 PASS; F4 fixture FAIL is a scale-input gap for confirmation, not a 10M STOP | PASS |

## 2. Item 1 detail — C2-10M receipt

- `BUILD-RECEIPT.json`: `verdict=ok`, arm C2, 3099 docs, 0 misses,
  final pin `ee06a4e4…:0:95436`; keyed-sqlite, profile-bound shared
  session (`session_bound=true`, `c2-100m-producer-001`), one archive
  per prefix (p0/p1/p2) + final boundary archive — the §5.8 item 1
  shape exactly. 44 loaded modules = preflight F9's "44, 0 outside
  freeze".
- Manifest identity: both local copies
  (`lane-SSCALE/snapshots/`, `lane-L4D/evidence/`) hash
  `54c64001d821…f8059d`, equal to `C2-10M-UPLOAD.json`'s manifest
  sha; roundtrip 4/4 true, rsync checksum clean.
- `DIFF-RECEIPT-L4D-c2.json`: verdict PASS. L1 occurrences
  (58629 chunks / 3099 docs), L2 xdoc (2580, desc 0.0), L3 leaves
  (5539) + parents (1667, desc 0.0) bit-exact; L4_shape 5/5 and
  L4_control 5/5 (both atom arms identical picks). Anchors sha
  `9728129b…` matches the pinned v1 file (re-hashed by me).
- `C2-PREFLIGHT-L4D.json`: 13/13 PASS (F1 freeze 89/89, F2×4
  suites, F3 receipt ok, F4 differential, F5 pins, F6 cache binding
  `25989b87…`, F7 quarantine, F8 env, F9 closure, F10 profile).
- Disposition compliance: the original literal-L4 FAIL receipts
  (`lane-RELAUNCH/evidence/c2-DIFF-RECEIPT.json`,
  `ref-DIFF-RECEIPT.json`, both FAIL on `L4_relations`) and the
  12/13 FAIL preflight are PRESERVED, never relabeled.

## 3. Item 2 detail — producer closure

- Freeze v2 (`c2-FREEZE-v2.json`): 89 files incl. corpus/profile/
  cache/encoder/extractor configs; producer five at P-2=final bytes
  (ingest `5ac506ee…`, maint `eab79b07…`, lifecycle `2d822d23…`,
  proj `0ab12db8…`, prodstate `e7a4370c…`); re-verified on the build
  VM (preflight F1/F9).
- P-1→P-2 differential: `P1P2-DIFF-C.json` and `P1P2-DIFF-R.json`
  both `verdict=PASS`, stages s1/s2/s3 all aspects true (shape,
  clocks, docs, seqs, accept rows, retired, statuses, hier), with
  recorded source bytes (p1 vs p2 producer shas differ as expected),
  profiles, and bindings.
- P-3 fix: `test-p3-prefail.log` ends "7 failures" →
  `test-p3-green.log` ends "0 failures". P3 REPORT documents no
  ingest/maint edits needed (hashes = arrived = freeze).
- SF1 (§5.8 item 2 pin): `sf1-pin.md` pins test
  `e95f2bab…` (I re-hashed the file: match), prefail log (F1
  KeyError), fixed `generation.py 92970939…` (matches freeze v2,
  SSCALE/S5S/SHEP code shas, and the local tree). Scale proof was
  queued behind the store — delivered by SSCALE fin5 (§5).

## 4. Item 3 detail — seating re-proof (rulings applied, evidence mine)

- VM side (`reproof-assessment.json` + `quiet-timing-evidence.json`):
  36 diffs = 18 r2 + 18 c3, zero other; baseline byte-identical;
  winner + tiebreak exact; confirm 6/6 incl. live qr1/qc1; V1 fork +
  battery C green; drift classified as predicted. Code shas recorded
  in the evidence: dossier `93871fb3…` (fixed), generation
  `92970939…`, CRITERIA `e7d0139a…` — corroborating the §7
  retraction (correct candidate both hosts).
- Local side: `reproof-prediction-audit.json` PASS (fails [],
  n_diffs 36, a10 144/144, baseline identical, top2 work exact,
  probes 6/6, v1_verdicts green); `reproof-c3-audit.json` 18 rows 0
  fails (spans 1, served10 31715, served19 18077, displaced16
  identical); compare log `diffs=36 … winner=M80-P100-A40`;
  confirm log CONFIRMED.
- MY OWN verification (raw sweep bytes, Q vs S-SEAT, all 18 A≥20
  settings): c3 span_hits identical + served[10]=31715 +
  served[19] 31715→18077 on 18/18; F-35 span missed both sides
  18/18; r2 spans 0→2 on 18/18. Ruling (a)'s doc-level conditions
  hold; ruling (b)'s five conditions (r2 lift, re-selection,
  c3 stable, probes, V1) hold on both hosts.
- Aid-identity caveat: I confirmed the mechanism in source —
  `identity.py` binds `revision_id` (16 bytes) into the blake3 atom
  preimage and documents "no import path"; `ingest.py` mints
  `revision_id = uuidv7()` per new source revision. Cross-birth tap
  identity is unachievable by construction, with zero product-signal
  content (14 non-diff rows show the same vocabulary disjointness
  with identical structure/counts). The coordinator's doc+structural
  discharge is evidence-consistent; nothing I found contradicts
  ruling (a) or (b).

## 5. Item 4 detail — S-scale correctness

From `sscale-fin5/` bytes (not the REPORT summary): open pin
`:0:95436` (58,629 atoms / 12,885 holons, query `take` df 1997 by
the deterministic max-df rule); publish wall 189.63 s, digest
`c61661bb…` (matches predecessors — deterministic); 10/10 fresh
`GenerationView` attaches, `cold_fallback` null; first answer 10/10
grounded, 200/200 spot; retire `wikipedia:27701` (approval
`sscale-001`) → `:0:95437`; republish `status: published`;
fresh verify: retired present in `retired_docs`, 0/10 entries from
it, digest changed to `0bc076a8…`, n_atoms 58595 (34 fewer —
consistent with the retired doc). Checks 5/5 true. The driver's
overall FAIL is solely `ack_within_5s` (154 s shared-host with
132 s cold encoder load), correctly labeled NON-QUALIFICATION.

## 6. Item 5 detail — 5 s gate (accounting verified, no subtraction)

- Measured production clocks (attach+query, GenerationView, 10/10
  grounded, retired present+excluded every sample, quiet VM
  load ≤0.13, no lane procs): fresh warm 1786/1827/2358 ms (n=3);
  fresh storage-cold 3530.9 ms (n=1, drop_caches, 314.5 MB phys
  read at attach); resident warm 1620–2081 ms (n=5); resident
  cold-first 2968 ms (n=1). All < 5000 ms.
- I closed the accounting on every sample: production == attach +
  query to the cent; e2e parts (store_open + attach + digest +
  encoder + query + entry_verify + text_spot) sum within ~10 ms of
  e2e; driver−e2e matches spawn/import. `test_prove_clock.py`
  EXECUTED by me: `S5S-CLOCK-PASS` (production invariant under
  audit-span changes; 150's real double-attach bytes rejected).
- No PASS by subtraction: (i) the removed second attach was a
  harness defect (worker-pool attach + NarrowIndex-internal attach;
  no production caller attaches twice) — repaired with
  failing-first tests, and single-attach is proved by
  `attach==index_build` + `single_attach:true` + identical digest
  `0bc076a8…` across split/verify/prove/cold/serve; (ii) the ~8 s
  canonical digest is audit-only and fenced per §4, while the 45
  block verifications that guard routing/ranking stay ON the clock
  inside attach (`blocks_verified: 45` every sample); (iii) encoder
  load is excluded as one-time per §4 ("reported alongside") with
  the deployment condition EXPLICIT (persistent serving process,
  resident MiniLM, demonstrated by `s5s_serve_demo.py`), and the
  fresh-including-encoder first request (~8–10 s warm, disclosed as
  exceeding) plus full all-in walls (warm driver 17.47–20.86 s,
  cold e2e 25.56 s) are recorded alongside — nothing hidden.
- The 24.53 s fire FAIL is preserved as classified evidence
  (`quiet-timing-evidence.json`, n=30 attach p50 1500.77) and fully
  re-accounted by the split (spawn ~1.3–4.3 + redundant attach 1.73
  + digest ~7.9 + encoder 6.48 + index ~1.7 + query 0.55 + audits).

## 7. Items 6–7 detail — Q adoption, STOP sweep

- Q adoption: winner evidence exists on both hosts with the EXACT
  same tiebreak (238096 < 452175); double-host agreement on the
  same store bytes + same code shas; probes 6/6 and V1 green both
  hosts. `lane-S/V1-READY` (coordinator-accepted) closes Q REPORT
  §3's pending flag; the V1 re-run ran on the current tree
  (dossier `93871fb3`, relquery `0fe79c50`), superseding Q's
  recorded pre-repair shas. Ruling (b) → ADOPTED is supported.
- G3: anchor repair + v1 supplement adopted (sha re-verified);
  c3-outer / p3-tau / p4-evidence / p6-seeding are standing
  CLASSIFIED mechanism limits with per-stage evidence (G3R/G3P/Q);
  V2/V3 honestly negative per §5.4 (no adoption, no waiver, misses
  not declared closed). No STOP armed.
- F1/F7: G6 executable bindings run fail-closed (UNEXECUTED without
  scale endpoints/battery — honest, not hidden); HARNESS repaired
  CONFFIT D1–D6/D8 (battery 17-red → ALL PASS, neighbors green);
  D7 disposed by coordinator ruling (keep abort-on-miss). No STOP
  armed; confirmation inputs (encode/d4 bindings) are queued
  100M-campaign work that refuses by construction.
- D1/D2: PAR132 GREEN (oracle both legs 26/26 + 96/96, 0 tie_flips;
  12 suites green) on the 10M bytes incl. S-SEAT dossier; G6 D1
  PASS. S5S's later additive `stages=None` index change is covered
  by its neighbor PASS receipts (facade_d1/pool/digest_d3).

## 8. Non-blocking observations (no action required for 10M SHIP)

1. Cold-sample thinness: fresh storage-cold production rests on
   n=1 (3530 ms) and resident cold-first on n=1 (2968 ms); the cold
   including-encoder total (~16.8 s from measured components) is
   derivable but not stated in PROVE-RECORD. Adequate for this
   repair gate (full n=124/stratum confirmation re-tests the clock
   at scale); the coordinator may ask for a wider cold series
   during confirmation.
2. Local-tree producer drift (100M scope, already classified): the
   local `ingest/maint/lifecycle.py` (`b3f60e1d…`/`da637f1b…`/
   `8e1d2a1b…`) differ from freeze v2 (`5ac506ee…`/`eab79b07…`/
   `2d822d23…`). Cause identified: the lane-R100M owner collision
   (`lane-R100M/COLLISION-0739Z.md`, Oct 8 ~07:47Z — after every
   10M receipt). Zero 10M impact (all 10M receipts predate it or
   are read-path; freeze v2 + VM fire trees pin the build bytes),
   but PROVE-RECORD §0's "Producer freeze set hash-asserted" line
   means local==VM-fire-tree, not ==freeze-v2 — wording the
   coordinator should read accordingly. Any future LOCAL build
   needs a freeze addendum first.
3. Environment note: two S5S numpy-dependent tests could not be
   re-executed on this host (no numpy in any local interpreter),
   so their PASS lines rest on builder logs; every property they
   assert (single attach, digest equality, attach==index_build) was
   instead verified by me directly from the VM evidence bytes plus
   my own execution of the pure-arithmetic `test_prove_clock.py`.

## 9. Files

- This REPORT (sole write). No product/harness/test file was
  modified. Scratch: none retained (all checks ran from lane bytes
  in place).
