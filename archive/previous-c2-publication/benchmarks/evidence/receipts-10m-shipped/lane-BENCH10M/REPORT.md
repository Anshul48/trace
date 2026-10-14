# lane-BENCH10M REPORT (workers 156 + 162, 2026-10-08/09)

## 0. Top finding

The shipped C2-10M serving stack at adopted budgets M80-P100-A40,
run by TB 0.3.0 on fresh Narrow stores (K=100, C=1, MiniLM-L6-v2
rev `1110a243`, CPU), scores slightly BELOW both reference arms
on four of five lanes and is the BEST arm on the fifth
(bright-pony), with zero query failures anywhere (1,061 queries
× arms). On curated/scifact/nfcorpus the recall@20 gap is
significant; the nDCG@10 gap is significant on scifact (vs
bm25) and nfcorpus (vs dense) but not on curated or smoke. On
pony A1 beats dense significantly on nDCG@10/MAP@10/R@20/MRR
and leads bm25 (not significantly) — all arms score low there
(BRIGHT pony is a hard reasoning bench). The A40 emission
cutoff costs nothing measurable vs the A100 diagnostic on any
lane (all-metric Δ=0.000 except trivial MRR rank-swaps).
Deployment-condition probe on the prebuilt 10M store copy at
pin `:0:95436`: 5/5 requests complete, 40/40 entries,
~0.8–1.4 s/query AFTER a ~2-min per-request index attach
(two independent probe runs agree).

Per-benchmark A1 (shipped) numbers:

| lane | n | nDCG@10 | MAP@10 | R@20 | MRR | vs bm25 ΔnDCG | vs dense ΔnDCG |
|---|---|---|---|---|---|---|---|
| smoke | 6 | 0.851 | 0.740 | 1.000 | 0.900 | -0.052 ns | — (no dense arm) |
| curated | 320 | 0.621 | 0.555 | 0.703 | 0.722 | -0.018 ns | -0.030 ns |
| scifact | 300 | 0.617 | 0.580 | 0.765 | 0.594 | -0.047 * | -0.028 ns |
| nfcorpus | 323 | 0.295 | 0.106 | 0.170 | 0.526 | -0.015 ns | -0.021 * |
| pony | 112 | 0.064 | 0.012 | 0.066 | 0.174 | +0.009 ns | +0.031 * |

`*` = p<0.05 paired t-test, 2,000-sample bootstrap CI; `ns` =
not significant. Significance rows use positive queries with
failures at zero; there were no failures. This is measurement
only: no SHIP claims, no criterion changes, no waivers.

## 1. Per-lane detail (conditions in §3)

### smoke — trace-technical-docs-dev, fixture, 6 docs / 6 queries

A1+bm25 only (adapter validation). Both `success`, 0 failures.

| arm | nDCG@10 | MAP@10 | R@20 | MRR | p50 / p95 |
|---|---|---|---|---|---|
| bm25 | 0.903 | 0.833 | 0.933 | 1.000 | 0.1 / 0.2 ms |
| A1 shipped | 0.851 | 0.740 | 1.000 | 0.900 | 14.9 / 17.2 ms |

No significant deltas (n=6; wide CIs). Adapter serves end to
end. RUN: `evidence/smoke-a1/`.

### curated — trace-engineering-curated, fixture, 100 docs / 320 queries

All four arms `success`, 0 failures, 0 empties.

| arm | nDCG@10 | MAP@10 | R@20 | MRR | p50 / p95 | ingest |
|---|---|---|---|---|---|---|
| bm25 | 0.639 | 0.585 | 0.771 | 0.747 | 0.3 / 0.4 ms | 0.0 s |
| dense | 0.651 | 0.586 | 0.798 | 0.698 | 10.4 / 12.8 ms | 6.7 s |
| A1 shipped | 0.621 | 0.555 | 0.703 | 0.722 | 39.4 / 66.8 ms | 4.2 s |
| A2 k100 | 0.621 | 0.555 | 0.703 | 0.722 | 36.6 / 44.9 ms | 4.1 s |

A1 vs bm25: nDCG -0.018 ns (p=0.057), MAP -0.029 *,
R@20 -0.068 *. A1 vs dense: nDCG -0.030 ns, R@20 -0.095 *,
MRR +0.024 ns (A1's MRR exceeds dense here). A1 vs A2:
identical to 3 decimals on every metric except MRR (-0.000,
p=0.026 — a sub-millipoint rank-swap). RUN:
`evidence/curated/`.

### scifact — beir-scifact, test, 5,183 docs / 300 queries

Pinned pull: BeIR/scifact@`b3b53356` corpus+queries parquet +
scifact-qrels@`2938d17d` test.tsv, all bytes+sha verified.
All four arms `success`, 0 failures, 0 empties.

| arm | nDCG@10 | MAP@10 | R@20 | MRR | p50 / p95 | ingest |
|---|---|---|---|---|---|---|
| bm25 | 0.665 | 0.621 | 0.823 | 0.638 | 0.9 / 1.4 ms | 1.6 s |
| dense | 0.645 | 0.596 | 0.837 | 0.611 | 63.5 / 126.8 ms | 133.8 s |
| A1 shipped | 0.617 | 0.580 | 0.765 | 0.594 | 153.0 / 171.4 ms | 1033.8 s |
| A2 k100 | 0.617 | 0.580 | 0.765 | 0.597 | 152.9 / 172.2 ms | 1065.1 s |

A1 vs bm25: nDCG -0.047 *, MAP -0.041 *, R@20 -0.058 *,
MRR -0.044 *. A1 vs dense: nDCG -0.028 ns, R@20 -0.073 *,
MAP/MRR ns. A1 vs A2: Δ=0.000 (p=1.0) on every metric
except MRR (-0.002, p<0.0001 — trivial). RUN:
`evidence/scifact/`.

### nfcorpus — beir-nfcorpus, test, 3,633 docs / 323 queries

Pinned pull: BeIR/nfcorpus@`b5026a0e` corpus+queries parquet +
nfcorpus-qrels@`a451b3b2` test.tsv, all bytes+sha verified.
All four arms `success`, 0 failures. bm25 left 25 queries
empty (recorded empties, not failures, scored at zero per TB).

| arm | nDCG@10 | MAP@10 | R@20 | MRR | p50 / p95 | ingest |
|---|---|---|---|---|---|---|
| bm25 | 0.310 | 0.120 | 0.177 | 0.521 | 0.4 / 0.7 ms | 1.2 s |
| dense | 0.316 | 0.110 | 0.189 | 0.510 | 40.7 / 122.9 ms | 94.7 s |
| A1 shipped | 0.295 | 0.106 | 0.170 | 0.526 | 129.0 / 178.3 ms | 585.8 s |
| A2 k100 | 0.295 | 0.106 | 0.170 | 0.528 | 127.3 / 163.8 ms | 592.7 s |

A1 vs bm25: nDCG -0.015 ns, MAP -0.014 *, R@20 ns, MRR
+0.005 ns (A1's MRR is the highest of the three arms).
A1 vs dense: nDCG -0.021 *, R@20 -0.018 *, MAP/MRR ns.
A1 vs A2: Δ=0.000 (p=1.0) except MRR (-0.001, p=0.0001 —
trivial). RUN: `evidence/nfcorpus/`.

### pony — bright-pony, test, 7,894 docs / 112 queries

Pinned pull: xlangai/BRIGHT@`3066d29c` documents+examples
parquets, bytes+sha verified (recovered from the SCOPE §8
drop — the drop cause was a staging bug, not upstream; see
§6). All four arms `success`, 0 failures, 0 empties. A1 is
the best arm on every headline metric.

| arm | nDCG@10 | MAP@10 | R@20 | MRR | p50 / p95 | ingest |
|---|---|---|---|---|---|---|
| bm25 | 0.055 | 0.011 | 0.064 | 0.123 | 2.1 / 3.6 ms | 0.4 s |
| dense | 0.033 | 0.006 | 0.034 | 0.108 | 90.2 / 138.7 ms | 83.3 s |
| A1 shipped | 0.064 | 0.012 | 0.066 | 0.174 | 146.0 / 190.8 ms | 1355.5 s |
| A2 k100 | 0.064 | 0.012 | 0.066 | 0.176 | 148.8 / 185.2 ms | 1419.9 s |

A1 vs bm25: all deltas positive (nDCG +0.009, MRR +0.052),
none significant (MRR p=0.0501). A1 vs dense: nDCG +0.031 *,
MAP +0.006 *, R@20 +0.032 *, MRR +0.066 *. A1 vs A2:
Δ=0.000 (p=1.0) except MRR (-0.001, p=0.0086 — trivial).
Complete Coverage@10 is 0.000 for every arm (no query fully
covered at 10 — pony gold sets are large). RUN:
`evidence/pony/` (`run_20261009_012143_577818`, 162).

## 2. Adapter inventory (all lane-local; no TB/tlsys edits)

| id | file | sha256 (16) | role |
|---|---|---|---|
| A1 | `adapters/c2_bench10m.py` (`C2Bench10MShipped`) | `0f6e7bc3…` | PRIMARY TB backend: fresh Narrow store, shipped stack, M80-P100-A40 |
| A2 | same module (`C2Bench10MK100`) | same bytes | diagnostic TB backend: identical, MAX_ENTRIES=100 |
| A3 | `adapters/c2_store_probe.py` | `0ceb3670…` | standalone deployment-condition probe (not a TB backend) |
| S1 | `adapters/stage_pinned.py` | `06b279cd…` (162-fix) | pinned pull + hash verify + TB-cache staging |
| R1 | `adapters/c2_rekey.py` | `07606fea…` | lock-identity rekey for the store COPY (guarded to the lane dir) |

162's adoption reverify (compiles + contract checks against
TB 0.3.0 sources) found the adapters sound; the single fix
was S1's same-basename collision (see §6 and
`evidence/pony-collision-162.log`). VM-deployed adapter bytes
are hash-identical to the lane tree (all four verified).

RUN.json `implementation_identity` self-authenticates every
scored run: A1 `arm=shipped-M80-P100-A40`, budgets
M80/P100/A40, `serving_file_sha256` matching the 7 shipped
serving files, `architecture_provenance=$TRACE_ARCHITECTURE_DIR`
(the lane's `tree/` copy), MiniLM rev `1110a243…`,
fresh-store native pins (per-run birth UUIDs).

## 3. Conditions and provenance (applies to all numbers)

- Host: `tl-m2-cpu`, Linux 7.0.0-1013-gcp x86_64, 12 vCPU,
  Python 3.12.3 (per RUN.json `hardware_info`).
- Harness: trace-bench 0.3.0 (venv; torch 2.14.0+cpu,
  sentence-transformers 2.7.0, pyarrow 25.0.1, numpy 2.5.3).
- Weights: `/srv/tl/weights`, `HF_HUB_OFFLINE=1`; MiniLM
  rev `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` for A1/A2
  (raw encode) and dense (unit-normalized).
- Product bytes: lane `tree/` copy; all 7 shipped serving
  shas match `snapshot-before-mutation.md` AND the RUN.json
  `serving_file_sha256` fields. Frozen/live-build dirs
  untouched (lane used only new `/srv/tl/lane-bench10m/`).
- Protocol: `--top-k 100 --concurrency 1`, TB defaults
  otherwise (`warmup 0`, linear nDCG gain, official splits).
  Compares: static mode, paired percentile bootstrap
  (2,000 samples, seed 42), two-sided paired t-test, no
  multiple-comparison correction.
- Corpora: 8 pinned files, all bytes+sha256 verified at
  pull (7/8 `fetched-verified`, 1 `reused-verified` on the
  restage); BEIR parquet→jsonl round-trip identical;
  catalog counts exact; UKP cross-check (156, observed):
  docs+queries byte-identical to UKP zips on both BEIR
  lanes, qrels bytes differ (ordering/bytes; pinned bytes
  authoritative either way).
- No C1 contact; no TB/tlsys/harness/criteria edits; no
  confirmation-campaign resemblance. GCS carried only small
  evidence + code (`m2/lane-bench10m/`).

## 4. A3 deployment-condition probe (prebuilt 10M store copy)

Two independent runs (156's + 162's first-hand re-run, same
A3 bytes) on the GCS-fetched store copy, read-only at pin
`ee06a4e4-83f7-4315-9e23-bd6e5034cccb:0:95436` (matches the
`c2-10m-manifest.json` `final_pin`), persistent process +
resident encoder, query `"take"`, budgets M80-P100-A40.
Copy was byte-verified then lock-rekeyed (meta
lock_dev/ino match the fresh lock; content untouched).

| run | open | enc load | attach/request (5×) | query (5×) | entries | wall |
|---|---|---|---|---|---|---|
| 156 | 2 ms | 6.4 s | 117–122 s | 0.78–1.41 s | 40/40 | 608 s |
| 162 | 2 ms | 6.3 s | 103–117 s | 0.78–1.09 s | 40/40 | 567 s |

Reading: serving a query on the resident 10M store takes
~1 s; (re)attaching the NarrowIndex takes ~2 min and
dominates every cold-attach request. No storage-cold sample
was taken (`drop_caches` not authorized) — page-cache state
is unrecorded, so attach/query walls are warm-cache
observations. Outputs: `evidence/store-probe.json` (156),
`evidence/store-probe-162.json` (162).

## 5. Success criteria (§6 of SCOPE)

1. All runs `success`; zero query failures; bm25's 25
   nfcorpus empties recorded as empty (scored zero), never
   fabricated. PASS.
2. RUN.json + TREC + compare outputs per lane in
   `evidence/` (+ probe outputs, source record, run logs):
   5 lanes (smoke/curated/scifact/nfcorpus/pony), 18
   backend executions + 13 compares + 2 probes. PASS.
3. REPORT.md top-finding-first with per-benchmark numbers,
   conditions, inventory, blockers. This file. PASS.
4. No SHIP claims, criterion changes, waivers. PASS.

## 6. Pony recovery (SCOPE §8 drop cause overturned)

SCOPE §8 dropped bright-pony as upstream-blocked (pinned
corpus file allegedly holding the examples table). 162's
re-verify proved the diagnosis was made on COLLIDED staging
bytes: S1 staged both pony roles under one basename, so the
examples file overwrote the corpus file before the schema
check. The true pinned corpus bytes (same commit
`3066d29c…`, 1,125,040 B, sha `afc23dc0…` verified) hold a
valid 7,894-row `id`/`content` pool. 162 fixed S1 (role
dirs in raw paths), restaged (BEIR bytes provably
unchanged), froze `prepared/bright-pony/test` (112 cases /
7,894 docs), and ran the standard 4-arm pony lane to
completion (`run_20261009_012143_577818`, all `success`,
0 failures; numbers in §0–§1, artifacts in
`evidence/pony/`). No upstream substitution; the
pinned-links requirement holds.
Full account: `evidence/pony-collision-162.log`.

## 7. Blockers / lessons for larger rungs

1. **Stage-then-schema-check every pinned corpus file**
   (row counts + required columns) before setup — the
   check SCOPE §8 recommended would have caught the pony
   collision at staging time. S1 now uses role-qualified
   raw paths (collision class closed).
2. **Index-attach cost dominates cold serving**: ~2 min
   per fresh NarrowIndex attach on the 10M store vs ~1 s
   queries. Larger rungs need pooled/warm attaches (or
   attach-cost amortization) before serving-latency
   claims; measure attach separately from query.
3. **CPU ingest walls scale linearly**: ~1,000 s per
   5k-doc fresh store (MiniLM CPU encode + Narrow
   commits). 100M-tier fresh-store benches need GPU
   encode and/or bulk-ingest paths, or prebuilt-store
   lanes with their own (non-public-qrels) scoring plan.
4. **Qrels byte-parity with UKP is not exact** (content
   equivalent for docs+queries; qrels bytes differ).
   Keep pinned bytes authoritative and record the
   cross-check, as done here.
5. **A40 cutoff is not the binding constraint** at these
   lanes (A1=A2 to 3 decimals; A2 itself emits ~47–70
   docs/query, not 100). Quality gaps vs bm25/dense come
   from ranking/funnel behavior, not the emission cap —
   larger rungs should instrument the funnel, not widen A.
6. **Transport flakes kill long SSH-bound runs** (156's
   death mode). Long VM campaigns must run detached from
   the control connection (or checkpoint); 162's pony run
   survived its control-SSH drop and completed
   unattended. Liveness checks must exclude the
   inspecting command itself (naive `pgrep -f` matches
   the checker's own ssh wrapper — 162's early pony
   "STILL_RUNNING" readings were that self-match);
   verify via log mtime + artifacts, never double-run.

## 8. Evidence map

- `evidence/{smoke-a1,curated,scifact,nfcorpus,pony}/`:
  RUN.json + per-arm TREC + `compare-shipped-vs-{bm25,
  dense,k100}.md` (smoke: bm25 compare only — 2-arm lane).
- `evidence/store-probe.json`, `store-probe-162.json`: A3.
- `evidence/c2-bench10m-source-record.json`: pins, hashes,
  counts (162 restage; BEIR bytes identical to 156's;
  156's UKP cross-check outcomes quoted in §3).
- `evidence/logs/`: `nfcorpus.log` + `run-nfcorpus.sh`
  (156 launch record); `pony-162.log` (162 pony run).
- `evidence/adoption-162.log`, `pony-collision-162.log`:
  succession + fix records.
- GCS mirrors (small evidence + code only):
  `gs://tl-m2-runs-d1995b06/m2/lane-bench10m/`.
- No SHIP claims are made or implied by this report.
