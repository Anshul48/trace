# RESULT — trace-100m-faiss-h2h: same-store FAISS vs TRACE guided head-to-head

PREREG sha256 verified `42bc334d3dd26a54e593e585e96eef2773e18e07b0fc82bb4c003052d1cb2ab1` before any work; PREREG.md not edited. All FAISS numbers below were measured on the VM in this run. Receipt tags: BUILT-measured-on-VM.

Scope: 812,545-unit sealed store (99.9M tok_v1 tokens, dim 384), 50 probes (10 s8-probe + 40 authored), one shared 4-vCPU Azure VM (another hand was active at low CPU; live query service also running). This is NOT a 100M-vector or 1B claim. Dense retrieval on these probes is capped at M-src 0.52 by the embedding/probe design (BM25 reaches 0.82), so ANN tuning cannot raise M-src; stated per PREREG, not a TRACE defect.

## Headline table (threads=1; quality = pass-0 ids vs S3 exact top-10, filed metrics.py)

| arm | config | recall@10 vs exact | hit@10 | nDCG@10 | p50 ms | p90 ms | p99 ms | RSS MB | index bytes |
|---|---|---|---|---|---|---|---|---|---|
| A0 Flat IP | flat | 1.0000 | 0.5200 (26/50) | 0.4177 | 93.52 | 95.41 | 97.66 | 3617.8 | 1248069165 |
| A1 HNSW M32 efC200 | efSearch=64 | 0.9680 | 0.5200 (26/50) | 0.4177 | 0.37 | 0.49 | 0.60 | 1444.1 | 1469189102 |
| A1 HNSW M32 efC200 | efSearch=128 | 0.9920 | 0.5200 (26/50) | 0.4177 | 0.66 | 0.86 | 0.94 | 1444.1 | 1469189102 |
| A1 HNSW M32 efC200 | efSearch=256 | 0.9960 | 0.5200 (26/50) | 0.4177 | 1.20 | 1.60 | 1.84 | 1444.1 | 1469189102 |
| A2 IVF2048 SQ8 | nprobe=8 | 0.7940 | 0.4600 (23/50) | 0.3775 | 0.35 | 0.41 | 0.58 | 349.9 | 321683008 |
| A2 IVF2048 SQ8 | nprobe=32 | 0.9160 | 0.5200 (26/50) | 0.4057 | 1.01 | 1.20 | 1.55 | 349.9 | 321683008 |
| A2 IVF2048 SQ8 | nprobe=128 | 0.9600 | 0.5200 (26/50) | 0.4177 | 3.65 | 4.05 | 4.45 | 349.9 | 321683008 |
| A3 IVF2048 PQ48 + rerank100 | nprobe=32 | 0.9100 | 0.5000 (25/50) | 0.3885 | 0.87 | 1.16 | 1.87 | 3665.7 | 49058028 |
| A3 IVF2048 PQ48 + rerank100 | nprobe=128 | 0.9500 | 0.5200 (26/50) | 0.4151 | 2.92 | 3.76 | 3.96 | 3665.7 | 49058028 |
| L live guided service | end-to-end | 1.0000 | 0.5200 (26/50) | 0.4177 | 1236.16 | 1264.76 | 1369.41 | n/a (service-owned) | n/a |

Exact (unrounded) key values: A1 ef128 t1 p50=0.6563; L p50=1236.1616; L mean=1239.6156; embed p50=13.7584 (n=50, embeds.jsonl). threads=4 latencies differ by <8% on every config (full numbers in summary_A0..A3.json); quality identical across thread counts. RSS = peak ru_maxrss of the per-arm timing process (A0/A3 peaks include a transient 2x matrix during load/add; steady state is ~1.3 GB each). TRACE serving reference 2.279 GB and f32 1.248 GB per PREREG (not re-measured; service process not touched).

Every number traces to: raw_A0|1|2|3_*_t1|t4.jsonl and raw_L_guided.jsonl (150 lines each = 3 passes x 50 queries, per-query ms + ids), summary_A0.json, summary_A1.json, summary_A2.json, summary_A3.json, summary_L.json (latency percentiles + filed-metrics quality), embeds.jsonl + embeds.f64.npy (per-probe embed ms), run.log (raw foreground output), build.log (index build, background under nice).

## Verdicts (PREREG lines, literally, with the numbers, no softening)

- Q-line (quality parity: M-fid recall@10 >= 0.99 AND M-src hit@10 within +-0.02 of 0.52, i.e. 25..27 of 50 hits): configs meeting the Q-line are A0 flat (1.0000, 26/50), A1 efSearch=128 (0.9920, 26/50), A1 efSearch=256 (0.9960, 26/50). NOT meeting: A1 efSearch=64 (0.9680), all A2 configs (0.7940/0.9160/0.9600; nprobe=8 also fails hit with 23/50), all A3 configs (0.9100/0.9500).
- S-line (among Q-line configs, lowest p50 search-only ms at threads=1; R = TRACE service p50 / that p50): best Q-line config is A1 efSearch=128 at 0.6563 ms; R = 1236.1616 / 0.6563 = 1883.53. R >= 10, therefore: "TRACE guided search is DOMINATED by a standard index on this store". R_end2end (FAISS search + measured embed ms vs TRACE service p50) = 1236.1616 / (0.6563 + 13.7584) = 85.76.
- M-line (no memory penalty iff best Q-line config RSS <= 1.5 GB): best Q-line config A1 efSearch=128 RSS = 1444.1 MB <= 1536 MB -> PASS, no memory penalty. Per-arm RSS / index bytes: A0 3617.8 MB / 1248069165 B; A1 1444.1 MB / 1469189102 B; A2 349.9 MB / 321683008 B; A3 3665.7 MB / 49058028 B; vs TRACE serving 2.279 GB and f32 1.248 GB (PREREG references).
- N-line (if no FAISS config meets the Q-line, say so and report all configs; do not pick silently): the condition does not trigger — three configs meet the Q-line (listed under Q-line); all configs' recall/latency are reported in the headline table regardless.

## A0 integrity check (PREREG gate: reproduce S3 global top-10 on >= 49/50 probes, ties allowed)

PASS without STOP: A0 Flat IP vs S3_exact_top10 from dense_queries.jsonl is 50/50 set-identical (M-fid 1.0000, every query recall 1.0) and 47/50 order-identical; the 3 order differences (s8-80, s8-160, s8-180) are swaps of items with bit-identical f64 cosine scores (exact ties, verified to 12 decimals), which the "(ties allowed)" clause covers. A0 M-src 0.520/0.4177 reproduces the filed S3 reference (0.52/0.418) exactly. Global matrix: 4 rows files concatenated in shard order, ordinals SHARD_LO+row, L2-normalized f32, mmap-read only.

## Load averages (before -> after each arm; 1-min gate 2.0, no waits, no flags)

- embed: 0.47 -> 0.55; A0: 0.65 -> 1.61; A1: 1.23 -> 1.21; A2: 1.11 -> 1.11; A3: 1.11 -> 1.10; L: 1.24 -> 1.53 (full `uptime` triples + ps snapshots in summary_*.json `loadavg_before/after`, `ps_before/after`). Index build ran detached under `nice -n 10` (build.log); all timed passes ran in the foreground at normal priority.

## Seal receipts

- sha-before.txt (2026-11-05T12:28:50Z) vs sha-after.txt (2026-11-05T12:53:30Z): all 9 sha256 (4 rows f32 + 4 SEAL json + units-812545.jsonl) UNCHANGED; sizes/mtimes UNCHANGED. Store row counts/dims re-verified on load (203137/203136/203136/203136 x 384).
- `free -g` at start: 31 GB total, 28 GB available (build needed ~3.6 GB peak; gate was available >= need + 4 GB: passed).

## Run notes (honest, including the wobble)

- Arm L first attempt queried the service 200x (pass p50s 1240.9/1241.8/1237.3 ms, consistent with the accepted run) then crashed BEFORE writing raw output on an empty-list bug in run_live.py (all_ms never appended; traceback in run.log). Fixed in one line, reran the full arm (fresh warm-up + 3 passes); only the rerun's raw_L_guided.jsonl is used. No service restart/reconfigure at any point (sequential single client throughout).
- threads=4 buys nothing here (single-query latency is memory-latency-bound); reported for the record, verdict uses threads=1 per PREREG.
- A2 nprobe=8 is the only config whose M-src hit (23/50) falls outside the Q-line hit band; every other config reproduces M-src 0.52 exactly (A3 nprobe=32: 25/50, inside the band but fails M-fid).

## Files (run directory on our server, 1.8 GB total)

RESULT.md, PREREG.md (+ PREREG.sha256), sha-before.txt, sha-after.txt, run.log, build.log, lib_h2h.py, step_embed.py, build_indexes.py, run_faiss.py, run_live.py, test_h2h.py, embeds.jsonl, embeds.f64.npy, index_A1_HNSW.faiss, index_A2_IVFSQ8.faiss, index_A3_IVFPQ48.faiss, raw_*.jsonl (19 files), summary_A0/A1/A2/A3/L.json.
