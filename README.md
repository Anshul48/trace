<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE — Self-Organizing Retrieval Engine (10M scale, seam12a freeze)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Source Freeze Manifest](https://img.shields.io/badge/Freeze_Manifest-8d3bbb6b_(253_files)-blue.svg)](freeze-src/cand/SOURCEFREEZE.json)
[![Qualification Receipt](https://img.shields.io/badge/Receipt-10M_PASS_(9494.9s)-brightgreen.svg)](docs/BENCHMARKS.md)
[![Recorded 20k Run](https://img.shields.io/badge/Recording-20k_Run_(27.8s)-blue.svg)](https://anshul48.github.io/trace/recording/)

TRACE organizes a continuous stream of documents into an overlapping multi-tier graph, so newly ingested items become searchable immediately without rebuilding the whole index. In one measured 10-million-token run, about thirteen thousand documents were organized into 3,711 parent groups and 9,177 leaf partitions, every leftover repair item was drained to zero, and guided routing put the right answer in the top 10 for roughly three out of four test queries.

## Measured 10M stat strip (freeze seam12a, run o94-scale10m)

Every number below is measured and receipt-backed. Sources: the frozen `result.json` (claim = `measured`), `rss-hwm.txt`, and `rss-series.tsv` from run `o94-scale10m`.

| What | Measured value |
|---|---|
| Corpus | 10,003,381 tokens / 13,081 docs / 63,441 atoms |
| Commits | 5,353 source commits → 164,195 final commits |
| Frozen source | 253 files, `frozen_ok=true` |
| Wall | 9,494.9 s (~2.6 h) |
| Guided recall@10 | 0.7367 (all) / 0.4883 (LSO) — 120 probes per mode across chunk, noisy, and cross families |
| Matched flat recall@10 | 0.055 / 0.0017 |
| Repair | 6 iterations, debt 5,847 → 0; 0 pending documents |
| Fresh-item visibility | 33/33 queries complete within 5 s (p50 96.8 ms, p95 115.5 ms); append ACK-to-query 0.114 s |
| Reader load | 2 threads, 27,796 requests, p50 74.7 ms |
| Memory peaks | tree 9,700.9 MiB (@t=3,097 s) / parent 8,489.1 / child 7,169.2 MiB |
| Retained store | 2.85 GiB |

Labels used above are the receipt labels: `all` means all-sources mode, `LSO` means leave-source-out (probe source excluded from the index). The flat arm scored the same mean row budget per query as the guided arm. "Recall@10" here is protocol recall — agreement with an exact oracle top-10 on the staged corpus — not a semantic relevance claim (see Limitations).

---

## Run it in 5 minutes

This is the exact path that was executed and verified on a clean host (WSL2 Ubuntu, Python 3.12.3). Every command below ran successfully; expected outputs are quoted from that run.

```bash
# 1. Get the frozen source and verify it (1.2 MB source-only tarball).
sha256sum -c seam12a-fork.tar.gz.sha256
# expect: seam12a-fork.tar.gz: OK
# Extract it; the runnable tree is cand/ (set CAND to that path).

# 2. Environment. The tarball ships no README, setup.py, pyproject.toml,
#    or requirements file, so there is nothing to pip-install from the
#    package itself: create a venv and add the two runtime dependencies
#    (blake3 is hard-required by tlsys/identity.py; receipts pin numpy 2.5.3).
uv venv /tmp/seam12a/run-test/venv --python /usr/bin/python3
uv pip install --python /tmp/seam12a/run-test/venv/bin/python numpy blake3
cd /tmp/seam12a/fix7/cand

# 3. Smoke checks.
SUP_PYTHON=/tmp/seam12a/run-test/venv/bin/python bash runtime.sh tools/product_pilot.py --help
# expect: exit 0, full usage printed (all o94 flags present).
PYTHONPATH=/tmp/seam12a/fix7/cand/fork/tl-sys /tmp/seam12a/run-test/venv/bin/python -B fork/tl-sys/tests/test_o93_repair_columnar.py
# expect: o93 repair-columnar: all groups PASS (221 checks).
# The package integration suite also passes unmodified:
/tmp/seam12a/run-test/venv/bin/python -B -m unittest tests.test_integration
# expect: Ran 6 tests ... OK (about 8 s).

# 4. A real 10K-token pilot through the genuine entry point
#    (synthetic corpus built in the tl-gpu-embcache-v1 layout;
#    corpus synthetic, pipeline 100% genuine).
SUP_PYTHON=/tmp/seam12a/run-test/venv/bin/python bash runtime.sh tools/product_pilot.py --tokens 10000 --profile local --source-root /tmp/seam12a/fix7/cand --data-dir /tmp/seam12a/run-test/synth-data --out /tmp/seam12a/run-test/out-pilot --drain-attribution --drain-census --holon-descriptor-columnar --overrides-columnar --descriptor-matrix-all --per-view-sharing --cold-scan-chunk 4096 --repair-columnar --candidate-source hnsw --drain-bounded-k 32 --candidate-shadow-audit 8
```

Real output of step 4 (from `out-pilot/result.json`): `claim=measured, status=PASS`; input 10,080 actual tokens, 36 complete documents, 72 atoms, 0 cache misses; guided recall@10 0.40 (all-sources, 120 probes), flat recall@10 1.0; final 72 atoms, 0 pending documents; repair 0 iterations, final debt 0; peak parent 87.3 / peak child 81.3 MiB; retained 8,098,072 bytes; wall 39.8 s. No Docker is needed: the run path is `runtime.sh` (PYTHONPATH + env + `exec python`), and everything above completed without a container. Mini-run footprint: ~90 MiB peak RSS, ~7 MB output directory, ~40 s wall on 2 cores.

---

## Run the full 10M

### The exact o94 command

```bash
SUP_REUSE_VIEW_POOL=1 taskset -c 0,1 bash runtime.sh tools/product_pilot.py \
  --tokens 10000000 --profile vm \
  --source-root <path-to>/fix7/cand \
  --data-dir /home/anshul/beam/pkg/data \
  --out <path-to>/runs/SCALE10M \
  --drain-attribution --drain-census \
  --holon-descriptor-columnar --overrides-columnar \
  --descriptor-matrix-all --per-view-sharing \
  --cold-scan-chunk 4096 --repair-columnar \
  --candidate-source hnsw --drain-bounded-k 32 \
  --candidate-shadow-audit 8
```

Receipt-recorded requirements: wall 9,494.9 s (~2.6 h); about 10 GB or more of RAM (peaks in the stat strip); 2.85 GiB of retained disk; interpreter from the run receipts with numpy 2.5.3, single-threaded BLAS (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), `nice 19`.

### Corpus format

`--data-dir` must contain `docs-100m.jsonl` (one JSON object per line, fields `doc_id` plus `text`) and an `emb_cache/` directory holding `meta.json` (format `tl-gpu-embcache-v1`, dim 384, float32 little-endian), `index.jsonl` rows (`key`, `chunk_sha256`, `byte_len`, dim 384, `shard`, `row`), and `shard_NNNNNN.f32` FP32 little-endian 384-dim memmaps. Tokenizer is TOK_V1; only complete documents count; cache misses are fatal. No corpus generator ships in the package — the only in-repo reference for the layout is the `cache_fixture` in `tests/test_prefix_shards.py`.

### Two blockers, stated honestly

There is no one-click 10M reproduction today. A full run is blocked by both of these:

1. The 10M corpus (`docs-100m.jsonl` plus `emb_cache/`) is external and not shipped — the release tarball is source-only (1.2 MB).
2. `--profile vm` is hostname-gated to `trace-build500` (`tools/product_pilot.py:871-872` exits with "VM profile requires existing trace-build500; local runs capped at 1M TOK"). On your own machine the maximum is 1M tokens via `--profile local`.

Labeling rule: running the command above on your own corpus is a **your-corpus 10M-scale run**. **Reproducing the measured o94 numbers** (the stat strip: 0.7367/0.4883, 9,494.9 s, and the rest) additionally requires the o94 corpus and the build VM, and is not possible today.

---

## See it first

- Interactive explorer: [https://anshul48.github.io/trace/explorer/](https://anshul48.github.io/trace/explorer/) (source: [docs/explorer/index.html](docs/explorer/index.html)) — structural DAG view, node inspector, and query-routing replay.
- Guided demo recording: [https://anshul48.github.io/trace/recording/](https://anshul48.github.io/trace/recording/) (source: [docs/recording/index.html](docs/recording/index.html)) — authentic terminal capture of a local 20k run (27.8 s), separate from the 10M qualification.

Identity notice, please read before comparing numbers: the live explorer currently shows the **earlier** freeze, not seam12a/o94 — head `e8334c07` with 166,457 commits, 207 frozen files (manifest `38c66bef`), harness `9f516288`, guided recall 0.73 / 0.4758, wall 12,973 s. It is the same corpus scale (tokens, docs, atoms, leaves, and parents match), but a different, earlier run. The o94/seam12a numbers in this README must not be pasted onto those pages until the explorer data files are re-exported from the o94 run.

---

## What the 10M result means in real-world terms

Think of thirteen thousand documents arriving as a stream — support tickets, research notes, a growing team wiki. TRACE files each one into parent groups (broad topics) and leaf partitions (tight clusters), letting an item belong to more than one group where it genuinely fits, instead of recomputing the whole filing system on every arrival.

Self-repair going from 5,847 to 0 means this: after the stream finished, about six thousand items were sitting in slightly-off groups, and a bounded cleanup pass moved every one of them home, leaving zero stragglers and zero documents still waiting to be filed.

Recall@10 is a simple scorecard. For each test question, look at the ten answers the system returns and ask: is the right answer among them? Guided routing — score the parent groups first, then search only the most promising branches — found it about 74% of the time in all-sources mode (about 49% when the question's own document was hidden from the index). Scanning the same number of rows without guidance found it about 6% of the time. Same budget, different strategy.

Why this attacks context-window limits: a language model cannot fit thirteen thousand documents into its prompt. The practical alternative is retrieval — pick the right handful of documents first, then read only those. Bounded branch descent is exactly that picking step, and the 10M run measured how often the pick contains the answer under a fixed work budget.

---

## How it works

1. **Intake.** Text is tokenized (TOK_V1) into word chunks called atoms and appended to a journaled intake backlog.
2. **Placement.** During batched drains, atoms attach to leaf clusters (`decide_leaf`) and leaves attach to parent clusters (`decide_parent`), updating centroids incrementally. Membership is many-to-many: leaves may belong to several parents and atoms to several leaves.
3. **Repair.** A bounded local repair pass enforces cohesion floors, and an explicit final `repair_to_zero` phase drains residual debt to 0 without global recomputation.
4. **Guided routing.** A query is scored against all parent centroids, the top parents are selected, child edges are descended, and member atoms are ranked to produce the top 10.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/CODE-TOUR.md](docs/CODE-TOUR.md), [docs/BENCHMARKS.md](docs/BENCHMARKS.md), [docs/REPRO.md](docs/REPRO.md).

---

## Benchmarks (measured, receipt-backed)

| Area | Measured result | Receipt / condition |
|---|---|---|
| Corpus | 10,003,381 tokens, 13,081 docs, 63,441 atoms, 0 cache misses | `result.json` input block |
| Wall | 9,494.9 s total: ingest 586.9 / drain 999.4 / append 1,163.2 / rejection 1.83 / prepare-rejection 170.3 / kill-restart 516.5 / remaining drain 4,654.4 / repair 1,162.1 s | `result.json` phase walls |
| Recall, all-sources | guided 0.7367 vs flat 0.055 | `result.json` evaluation summary, 120 probes |
| Recall, LSO | guided 0.4883 vs flat 0.0017 | `result.json` evaluation summary, 120 probes |
| Fresh visibility | 33/33 within 5 s; p50 96.8 ms, p95 115.5 ms | `result.json` F1 block, n=33 |
| Append latency | ACK-to-query 0.114 s | `result.json` |
| Reader load | 2 threads, 27,796 requests, p50 74.7 ms | `result.json` |
| Memory | tree 9,700.9 MiB @t=3,097 s; parent 8,489.1; child 7,169.2 MiB | `rss-hwm.txt` + `rss-series.tsv` (1,899 rows) + `result.json` |
| Store | 2.85 GiB retained (3,058,624,883 B) | `result.json` / study record (VM-side) |
| Repair | 6 iterations, 5,847 → 0 | `result.json` |
| Derived caps | `max_delta_entries` 669,436 (37,117 commits / 7,035 atoms measured, margin 2.0); kill wait 316 s; drain k=32, cold-scan chunk 4,096 | `result.json` |
| Pins | probes `b332d62d…`, harness `9f78479a…` (= freeze entry for `tools/product_pilot.py`), final commits 164,195 | `result.json` source pins |

---

## Limitations

- Single-run provenance: the numbers come from one run (`o94-scale10m`) on one VM (`trace-build500`); no independent reproduction of the 10M figures exists yet.
- The 10M corpus and embedding cache are not redistributed; the tarball is source-only.
- No Python version string appears in the run receipts (the 5-minute path above was verified on Python 3.12.3 with numpy 2.5.4 against receipts recording numpy 2.5.3).
- Retained-disk (2.85 GiB) and corpus-path figures are VM-side and cannot be verified from another host.
- Recall figures measure protocol agreement with an exact oracle on the staged corpus — not semantic relevance, ranking quality in general, or latency guarantees on other hardware.
- TRACE is single-writer append-only with crash recovery to a consistent ledger boundary; it does not implement distributed transactions.
- 100M tokens and beyond are not qualified; the drain phase is the known scaling bottleneck (see Roadmap). No state-of-the-art claims are made.

---

## Roadmap

- Re-export the explorer data files from the o94 run so the live pages show seam12a numbers (until then, the identity notice above stands).
- Publish a corpus fetch or prep script so a public 10M reproduction is possible end to end.
- Qualify larger scales (100M–500M+ tokens); this is roadmap, not a claim.
- Keep the 20k portable path working as the one-command local proof.

---

## Freeze identity

- Freeze: **seam12a**, tarball sha256 `8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64` (verified `sha256sum -c`: OK; manifest: 253 entries, 0 diffs).
- Run: **o94-scale10m**. Pins: probes `b332d62d…`, harness `9f78479a…`, final commits **164195**.
- Manifest: [freeze-src/cand/SOURCEFREEZE.json](freeze-src/cand/SOURCEFREEZE.json). Freeze check: `python3 tools/verify_freeze.py`.

---

## Repo map

- [docs/explorer/index.html](docs/explorer/index.html) — interactive 10M DAG explorer (static viewer, no backend).
- [docs/recording/index.html](docs/recording/index.html) — terminal-cast player for the recorded 20k run.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — storage ledger, fix stack, reader isolation.
- [docs/CODE-TOUR.md](docs/CODE-TOUR.md) — file-by-file walkthrough of the frozen tree.
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — unabridged benchmark records and derivations.
- [docs/REPRO.md](docs/REPRO.md) — reproduction commands, environment, pin hashes.
- [repro-20k/README.md](repro-20k/README.md) — portable 20k-token reproduction (88 documents, precomputed vector cache).
- [repro-20k/LICENSES-DATA-MODEL.md](repro-20k/LICENSES-DATA-MODEL.md) — upstream data and model attribution.
- [demo-app/](demo-app/README.md) — in-memory 120-probe viewer demonstrating the frozen guided/flat scoring in isolation (educational, separate from the storage harness).
- [tools/verify_freeze.py](tools/verify_freeze.py) / [tools/check_receipts.py](tools/check_receipts.py) / [tools/check_links.py](tools/check_links.py) — freeze, receipt, and link checks run in CI.

---

## License

Apache-2.0 ([LICENSE](LICENSE)). Corpus text excerpts and vector models keep their upstream licenses; see [repro-20k/LICENSES-DATA-MODEL.md](repro-20k/LICENSES-DATA-MODEL.md).

## Related: ANIMA

[ANIMA](https://github.com/Anshul48/anima) owns agent orchestration; TRACE owns the retrieval overlay. The two are separate systems with no shared runtime — this README covers TRACE only.
