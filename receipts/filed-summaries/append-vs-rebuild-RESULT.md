7017 RESULT.md
# RESULT — trace-append-100k (PREREG5, run 2026-11-05, attempts 1+2)

Protocol: `PREREG5.md`, sha256 `d3c16fc8a2584345e1964a824a5cf7411b61f2ef678287bd416a61053e6110a9` — verified before running, never edited. Run literally; deviations/errata below. No tuning after seeing numbers.

## Headline: recall@10 (mean; QN n=2000, QB n=1000; GT = exact f32 cosine over BASE u NEW)

| arm | QN s200/ef128 | QB s200/ef128 | QN exact | QB exact | fresh-QN* |
|---|---|---|---|---|---|
| T-APP (mean r1=r2) | 0.9917 | 0.9970 | 1.0000 | 1.0000 | 0.9896 |
| T-SEG | 0.9980 | 0.9986 | 1.0000 | 1.0000 | 0.9980 |
| T-REB | 0.9927 | 0.9966 | 1.0000 | 1.0000 | 0.9921 |
| H-ADD (mean r1=r2) | 0.9941 | 0.9967 | — | — | 0.9919 |
| H-REB | 0.9950 | 0.9971 | — | — | 0.9948 |

GT NEW-share: QN 0.5386 (1971/2000 queries contain NEW), QB 0.1495 (596/1000). HNSW ef256: H-ADD QN 0.9978/QB 0.9980, H-REB QN 0.9980/QB 0.9982. Source: `summary.json` ← `raw_<arm>_<key>.jsonl` (28 files, 42000 lines) ← `ret_*.jsonl` + `gt_qn.jsonl`/`gt_qb.jsonl`.
\*fresh = recall restricted to NEW entries of GT, QN only.

## Headline: cost (wall s; full per-op CPU/RSS/bytes/threads/load in `timings.json`, commands in `cmds.log`)

| arm | wall breakdown (s) | total |
|---|---|---|
| T-APP r1 | ingest 17.2 + compact 1.7 | 18.9 |
| T-APP r2 | ingest 16.1 + compact 1.5 | 17.6 |
| T-SEG | kmeans 23.3 + create 0.0 + ingest 14.0 + compact 0.9 | 38.3 |
| T-REB | kmeans 243.2 + create 0.0 + ingest 45.0 + compact 2.8 | 291.1 |
| H-ADD r1 | base-build 147.5 + add 84.8 + write 0.2 | add+write 85.0 |
| H-ADD r2 | base-build 148.6 + add 85.2 + write 0.2 | add+write 85.4 |
| H-REB | build 249.1 + write 0.2 | 249.3 |

Peak RSS: TRACE ingest ~156 MB, compact ≤959 MB, kmeans ≤860 MB; HNSW process 1914 MB (all-index cumulative max). All timed ops 1 thread except kmeans (numpy-default). Bytes (du of outputs): T-APP store 711 MB compacted; HNSW index file 548 MB.

## Verdicts (literal, PREREG5 §Pass lines)

- Q T-APP vs T-REB: QN 0.9917 vs 0.9927 | QB 0.9970 vs 0.9966 => APPEND QUALITY NON-INFERIOR TO REBUILD (margin 0.02)
- Q T-SEG vs T-REB: QN 0.9980 vs 0.9927 | QB 0.9986 vs 0.9966 => APPEND QUALITY NON-INFERIOR TO REBUILD (margin 0.02)
- Q H-ADD vs H-REB (HNSW): QN 0.9941 vs 0.9950 | QB 0.9967 vs 0.9971 => APPEND QUALITY NON-INFERIOR TO REBUILD (margin 0.02)
- C(a) tapp1=18.9 tapp2=17.6 treb=291.1 spread=0.07 => TRACE APPEND MATERIALLY CHEAPER THAN TRACE REBUILD
- C(b) tapp=18.3 hadd=85.2 => TRACE APPEND NOT SLOWER THAN HNSW ADD
- D: CRASH-SAFE APPEND 3/3 (kill1: 100 lines/20000 rows/count 20200; kill2: 251 lines/50200/50200; kill3: 400 lines/80000/80200; all verify bad=0, digest stable; details `kill_results.json` + `kill{1,2,3}.ack`)

Overall: TRACE append is the better operational append on this store — ~4.7x faster than HNSW add (18.3 s vs 85.2 s) at non-inferior recall, and crash-safe 3/3.

## Scope statement (PREREG5, verbatim)

One VM (4 vCPU shared), one run, one shard-sized base (203,137 units, NEW = 49% of BASE: a larger relative append than 100k/812k = 12%), real vectors with a shard-to-shard distribution shift, cand_serve at the S200 config only. Not claimed: behaviour at 812k, multi-writer, disk-cold latency, quality on text queries.

## Sealed originals

`sha-before.txt` vs `sha-after.txt` (26 files: estore-shard0 files, rows/assign/parents shard0, rows shards 1–3, SEAL jsons, units file): identical — `diff` empty, SEALED-UNCHANGED.

## Deviations / errata (every one)

1. ERRATUM-SUGGESTION (PREREG5 §Fixed design): pool is 609408 rows (203136×3; ordinals 203137..812544 inclusive = 609408), not 609409. Ran with 609408; receipts in `sample_receipt.json`. Disjointness NEW∩QN=∅ checked; id lists `new_ids.txt`/`qn_ids.txt`/`qb_ids.txt` in lease dir.
2. Attempt 1 ended by session SIGTERM during the T-REB QB-exact serve. Attempt-1 foreground stdout for the TRACE arms is missing from `run.log`; every op's exact command + rc + wall/cpu/rss/bytes/load survives in `cmds.log`. T-REB build recs were recovered from `cmds.log` (flagged `recovered_from_cmds_log` in `timings.json`); QB-exact was served in attempt 2 (`s4b_treb_finish.py`); QB-s200 was re-served to a temp prefix for the selfhit diagnostic only — identical=True to the committed file, committed file kept.
3. `ack_treb.ack` was already absent at the s4b cleanup (present at session-start listing). Cause UNVERIFIED — no stray process found afterward, no phantom serve TAG in `cmds.log` (byte-count consistent with logged serves only). End-state equals the protocol scratch-removed state; all primary artifacts verified (digest count 303137, verify-rows bad=0, 1000-line ret file).
4. `s6_kill.py` ack parser first assumed 0-based starts; engine acks carry global ordinals (first line `ACK 203137 200`). Fixed, all three trials re-run fresh. kill1's crashed first attempt left a store that the re-run deleted before starting.
5. `s7_report.py` C(b) first matched tag suffix `split("-")[-1]`, silently dropping `add-new` (reported hadd=write-only, absurd 99.02x). Caught before reporting, fixed to endswith match with an assert; corrected verdict above. The wrong intermediate line exists only in `run.log` history, not in any committed number.
6. Step-0 probe: first two probe attempts failed on my `verify-rows` usage (`--count` semantics), third with correct usage passed: SUPPORTED (digest stable across compact, verify bad=0, serves OK both modes; `probe_result.json`). Usage learning, not a protocol deviation.
7. HNSW timings are in-process: `cpu_s` = user+sys combined (no split), `peak_rss_bytes` = cumulative process max (1914 MB), `bytes_out`=0 for build/add (in-memory; `write_index` bytes recorded: 548115438). All 1 thread (`faiss.omp_get_max_threads()=1`, OMP/MKL/OpenBLAS pinned 1).
8. Load gate: two T-REB serves found 1-min load > 2.0, waited ≤5 min per protocol, proceeded ok-after-wait (logged in `run.log`/`cmds.log`). RAM gate never tripped (avail ≥27 GB).
9. kill2 overshot to 251 ack lines (50200 rows) — within the protocol's ±one-batch tolerance of 50k.

## Receipts (every number traces)

Recall/fresh/share ← `raw_*.jsonl` (per-query qid/ret/recall/fresh) ← `ret_*.jsonl` + `gt_*.jsonl`; means+verdicts in `summary.json` (printed by `s7_report.py`, tail in `run.log`). Cost ← `timings.json` ← `cmds.log` (exact commands + rc). Kills ← `kill_results.json` + `kill{1,2,3}.ack`. Sampling ← `sample_receipt.json` + id lists. Seals ← `sha-before/after.txt`.

## Removals (scratch inside lease dir only)

During arms (each logged): `est_tapp-r1`, `est_tapp-r2`, `est_tseg_new`, `est_tseg_base`, `est_treb`, `seg_new/`, `reb/`, `ack_tapp-r1.ack`, `ack_tapp-r2.ack`, `ack_tseg.ack`, `ack_treb.ack` (see dev. 3), `est_kill{1,2,3}` + `kill{1,2,3}.ingest.out`, `index_{hadd-r1,hadd-r2,hreb}.faiss`, all `sv_*` serve outputs. At end: `__pycache__/`. Kept: npy inputs-derived (~620 MB), `ret_`/`raw_`/`gt_` JSONL, `kill{1,2,3}.ack`, scripts, logs. Lease total ≈ 1.3 GB (≤12 GB).
