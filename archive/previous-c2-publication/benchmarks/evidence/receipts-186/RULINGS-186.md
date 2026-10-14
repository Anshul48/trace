# RULINGS-186: 10M confirm campaign rerun (architect rulings under owner delegation)

Author: Claude (architect, Sonnet 5.5). UTC: 2026-10-10T06:55Z. Status: RULED, effective now; reversible by the owner before step (d) fires. Not written into any lane directory.
Labels: observed = I ran/read it in this session; reported = another actor's record; predicted = inference; UNKNOWN = no evidence.

## Authority (owner words, 2026-10-10, genuine user messages)
- "wts wrong with firing the 10m. ive instructed the backup thing to ignore wsl and trace-arch. ill wait it out for how long it takes."
- "ofc do the path drivers" (repair the `_183`/`_185` drivers); "gcloud auth login done on A"; "q5. sure." (run root default); "q3. can u ans urself." (release successor); "q2. u decide. id lean towards cap03 fixed. or something with the best of both worlds."
- Standing: "u decide everythn and get it done". Owner veto: any owner message saying hold/stop halts step (d).
These rulings do NOT change F2 criteria, the 5 s ceiling, the campaign design (31 chunks x 4 reps, 992 edits, 64 receipts/chunk), seeds, or measured code paths.

## R1 TREE: serving tree = cap03 (query.py a9d4be554322fcfc9d9ef3b250e381f0ad2afc565fd367303b8f60a711e4ccc6)
Evidence for:
- observed 06:45Z, VM tl-m2-cpu RUNNING; `/srv/tl/lane-cap03/green.log` (sha256 334f0906...71eea, copy in `vm-green/`): tree query.py=a9d4be554322; REFIRE (fixed harness ffc3a839) 16:13:59Z; `wrote cap03-battery-green.json verdict=PASS` (json sha256 541bdcba...e28e8d); every gate listed PASS in all four lanes incl. `default==cap03`, `determinism`, `trace-refusal`, `tree-sha`; no FAIL after the first run's AssertionError (that crash was the pre-fix harness; observed lines 27-37).
- observed per-lane R@20 A0ref -> default: curated 0.703 -> 0.7435; scifact 0.7646 -> 0.7721; nfcorpus 0.1705 -> 0.1761; pony 0.0664 -> 0.0674.
- observed diff (codex2 draft, text-diffed): the only difference vs the pre-cap03 anchor d7756e72 is `MMR_SIM_CAP = 0.3` (was None); explicit `MMR_SIM_CAP=None` restores exact MMR.
Disclosed tradeoffs (cannot be averaged away): reported local curated multihop 0.3083 -> 0.2917 (two cases 25/40, each 0.667 -> 0.333); contradiction rescue is 24/40, 16/40 remain scoring losses. UNKNOWN: pony A1-lead obligation (comparator/metric not specified).
"Best of both worlds" = (i) campaign runs cap03 default; (ii) historical oracle stays reproducible through explicit `MMR_SIM_CAP=None` and the battery's A0ref arms, so every comparison with pre-cap03 results uses those arms; (iii) recovering the multihop dip and the 16/40 is a SEPARATE candidate search (MMR_DENSE_EXEMPT_D / dw tuning, Praxist) and is not part of this campaign.
Does not establish: 100M, the fresh-reader F2 contract, or historical-comparability of campaign receipts with pre-cap03 serving identity.
Repin: ONE pin changes, `tl-sys/tlsys/query.py` -> a9d4be55...; the original pin file `lane-HARNESS3/evidence/byte-pins-post-integration-164.txt` stays untouched (observed 16/17 OK, query.py FAILED, `pins-check-pre-20261010.txt`). The successor pin file `pins-186.sha256` (original with that one line replaced) is created by the OWNER (the agent harness blocked an agent-created repin); `_186` launcher refuses unless 17/17 OK against it and logs the file sha256.
Consumers needing repin: the `_186` launcher/verdict only. Others UNKNOWN (gate_runner / tests that pin query.py are not touched; no consumer is edited).

## R2 WINDOW successor
`C/evidence/WINDOW-RELEASED-181.md` will never exist (181 cancelled). Replacement: `/home/anshul/trace-ops/campaign-186/WINDOW-RELEASED-186.md`, created by the architect only when ALL fire conditions below are met; the `_186` launcher takes its sha256 as an argument and refuses otherwise. No marker is ever written into lane L.

## R3 RUN ROOT
`/home/anshul/trace-data/campaign-186` (ext4, observed 907 GB free at 06:44Z; outside /tmp; `/tmp` purge is the recorded loss cause class). Footprint bounded ~30-40 GB with the ruled per-chunk `blocks/` cleanup. Per-chunk `sample-summary.json` + `sample-receipts.json` are copied (never overwritten, sha256 ledger) to `/home/anshul/trace-ops/campaign-186/receipts/` before the next chunk. Survives a WSL restart (predicted), NOT an OS replacement (UNKNOWN): receipts go to the git ops branch/transfer package before the dual boot. Host risk: the WSL disk image lives on C: (guest sees 907 GB, host C: free was ~85-98 GB): launcher aborts a chunk if C: free < 25 GB; owner keeps >= 60 GB free on C: during the run.

## R4 QUIET POLICY and contamination ledger
During (c) and (d): only API-bound agent work and light reads (`nice -n 19 ionice -c3`); no pytest/numpy/benchmarks/sha256 sweeps on A-WSL (heavy experiments go to machine B or wait for `heavy_ok.sh` gaps). Launcher records loadavg and the top-10 CPU/RSS processes before and after each chunk in the run ledger. Owner's own Windows-side activity is untouched and is flagged as a contaminant, not controlled.

## R5 Result label
Timings from this run are A-WSL2, shared host, non-authoritative; they are labelled so in the verdict. `COMPLETE-10M` means completion, not F2 PASS. Native-Ubuntu reruns cover only timed cells if qualification requires.

## R6 Superseded / retained
Supersedes runbook-185 run-root (`/tmp/confirm-campaign-183`), the `WINDOW-RELEASED-181` gate, the unlocated "REPORT section 11" override citation (no backfill; absence recorded), and the 16/17 pin note. `_183`/`_185` drivers and runbooks stay intact as audit record; successor drivers are `_186` in `/home/anshul/trace-ops/j33-drivers/`.

## FIRE CONDITIONS for (d) (all required; staging (a)(b) may start now)
1. `_186` drivers audited by a different agent (codex1) from the defect list + candidate files before any builder summary: PASS or only recorded non-blocking notes.
2. `pins-186.sha256` exists and 17/17 OK from the workspace root.
3. (a) pristine `ok=154074 bad=0 missing=0`; (b) emb_cache bytes equal 1021355564 and `row_count= 569328`; (c) pre-encode 992 edits, `PREENCODE DONE`, 32/32 overlap rows match.
4. host: load quiet (< 2 for 10 min), ext4 free >= 100 GB, C: free >= 60 GB, no foreign heavy jobs from my side.
5. No owner hold message.

## Still open (not blocking this run)
Detection time (eager attach vs verify-before-first-use); J22 input; cap03 pony A1-lead obligation; missing root-override record; poller 184/185 cancel decision (pollers left idle, not deleted).
