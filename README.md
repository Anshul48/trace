<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE — a self-organizing memory database (research preview)

[![Status: research preview](https://img.shields.io/badge/Status-research_preview-blue.svg)](#status-and-roadmap)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Source Freeze Manifest](https://img.shields.io/badge/Freeze_Manifest-8d3bbb6b_(253_files)-blue.svg)](freeze-src/cand/SOURCEFREEZE.json)
[![Qualification Receipt](https://img.shields.io/badge/Receipt-10M_PASS_(9494.9s)-brightgreen.svg)](docs/BENCHMARKS.md)
[![Recorded 20k Run](https://img.shields.io/badge/Recording-20k_Run_(27.8s)-blue.svg)](https://anshul48.github.io/trace/recording/)

**TRACE is a self-organizing memory database: a 10-million-token persistent memory for LLMs and agents, filing every arrival into schemas and deltas without rebuilding the index.** In one frozen, receipt-backed run, 10,003,381 tokens across 13,081 documents settled into an overlapping graph of 3,711 parent groups and 9,177 leaf partitions, guided routing put the right answer in the top 10 for roughly three out of four test queries, and a bounded repair pass drained every leftover item to zero.

**New here? [Take the 60-second tour](https://anshul48.github.io/trace/explorer/)** — feed documents in, watch them break into atoms, self-organize into schemas, answer a question, and repair itself, on the real graph.

[Try it](#run-it-in-5-minutes) · [See it](#see-it) · [Proof](#proof-strip-freeze-seam12a-run-o94-scale10m) · [Deep dive](#deep-dive) · [Reproduce](#reproduce-the-10m-benchmark)

| Start here | Pick a path |
|---|---|
| Researchers | [Proof strip](#proof-strip-freeze-seam12a-run-o94-scale10m) · [Benchmarks](docs/BENCHMARKS.md) · [Architecture](docs/ARCHITECTURE.md) |
| Developers | [Run it in 5 minutes](#run-it-in-5-minutes) · [Portable 20k reproduction](repro-20k/README.md) · [Code tour](docs/CODE-TOUR.md) |
| Judges | [60-second tour](https://anshul48.github.io/trace/explorer/) · [Animated demo](https://anshul48.github.io/trace/recording/) · [Raw recorded run](https://anshul48.github.io/trace/recording/#raw-run) |

## What it does for you

**Researchers** — use it to explore long-horizon agent memory on a frozen run you can cite: retrieval-at-scale experiments with guided-versus-flat routing under matched work budgets, crash-recovery gates, fresh-item visibility probes, and cross-domain schema linking through the overlapping parent/leaf graph.

**Developers** — use it to explore persistent memory beyond the context window: ingest once with the Python package and the `product_pilot` CLI, run local-first in an isolated venv with no services or containers, and build on content-addressed storage where every artifact hashes back to the frozen manifest.

Short on time? Read the proof strip, pick one path under See it, and come back for the 5-minute run.

## Proof strip (freeze seam12a, run o94-scale10m)

Every number below is measured and receipt-backed: the frozen `result.json` (claim = `measured`), `rss-hwm.txt`, and `rss-series.tsv` from run `o94-scale10m`.

| What | Measured value |
|---|---|
| Corpus | 10,003,381 tokens / 13,081 docs / 63,441 atoms |
| Commits | 5,353 source commits → 164,195 final commits |
| Frozen source | 253 files, `frozen_ok=true` |
| Wall | 9,494.9 s (~2.6 h) |
| Guided recall@10 | 0.7367 (all) / 0.4883 (leave-source-out) — 120 probes per mode across chunk, noisy, and cross families |
| Self-repair | 6 iterations, debt 5,847 → 0; 0 pending documents |
| Fresh-item visibility | 33/33 queries complete within 5 s (p50 96.8 ms, p95 115.5 ms); append ACK-to-query 0.114 s |
| Reader load | 2 threads, 27,796 requests, p50 74.7 ms |
| Peak RAM | ~8.5 GB (parent-process peak 8,489.1 MiB; child 7,169.2 MiB) |
| Retained store | 2.85 GiB |

Labels: `all` means all-sources mode, `leave-source-out` means the probe's own document was hidden from the index. "Recall@10" here is protocol recall — agreement with an exact oracle top-10 on the staged corpus — not a semantic relevance claim.

---

## See it

- **60-second tour:** [Take the 60-second tour in the explorer](https://anshul48.github.io/trace/explorer/) — documents in, atoms, schemas, retrieval, and self-repair, driven on the real graph.
- **Animated demo:** [recorded 20k terminal run (27.8 s)](https://anshul48.github.io/trace/recording/) — install, frozen-file checks, and an engine run to `PASS`, replayed in the browser.
- **Raw recording:** [unedited terminal capture](https://anshul48.github.io/trace/recording/#raw-run) — the authentic frozen-harness output on the portable 20k prefix, slowest path last.
- Identity note: the live explorer graph data files are the earlier freeze; corpus scale and graph counts match.

---

## Run it in 5 minutes

This is the exact path that was executed and verified on a clean host (WSL2 Ubuntu, Python 3.12.3), re-verified from a fresh tarball extract with the environment created inside the extracted tree. Every command below ran successfully; expected outputs are quoted from those runs.

```bash
# 1. Get the frozen source and verify it (1.2 MB source-only tarball).
sha256sum -c seam12a-fork.tar.gz.sha256
# expect: seam12a-fork.tar.gz: OK
# Extract it; the runnable tree is fix7/cand/ (set CAND to that path).
tar xzf seam12a-fork.tar.gz
CAND=$PWD/fix7/cand
cd "$CAND"

# 2. Environment, created INSIDE the extracted tree (needs uv;
#    without uv: python3 -m venv .venv). The tarball ships no README,
#    setup.py, pyproject.toml, or requirements file, so there is nothing
#    to pip-install from the package itself: create a venv and add the two
#    runtime dependencies (blake3 is hard-required by tlsys/identity.py;
#    verified with numpy 2.5.4; o94 run receipts record numpy 2.5.3).
uv venv .venv --python /usr/bin/python3
uv pip install --python .venv/bin/python "numpy==2.5.4" "blake3==1.0.11"

# 3. Smoke checks (all paths relative to $CAND).
SUP_PYTHON=$CAND/.venv/bin/python bash runtime.sh tools/product_pilot.py --help
# expect: exit 0, full usage printed (all o94 flags present).
PYTHONPATH=$CAND/fork/tl-sys $CAND/.venv/bin/python -B fork/tl-sys/tests/test_o93_repair_columnar.py
# expect: o93 repair-columnar: all groups PASS (221 checks).
# The package integration suite also passes unmodified:
$CAND/.venv/bin/python -B -m unittest tests.test_integration
# expect: Ran 6 tests ... OK (about 3 s).

# 4. Build the synthetic 10K corpus (layout tl-gpu-embcache-v1; corpus
#    synthetic, pipeline 100% genuine). No corpus generator ships in the
#    tarball, so this inline step builds synth-data/ from the shipped
#    chunker (same seeded content as the reference run: 48 docs).
$CAND/.venv/bin/python - <<'EOF'
import hashlib, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, 'fork/tl-sys')
from tlsys.ingest import chunk_text
OUT = Path('synth-data'); CACHE = OUT / 'emb_cache'
RPS, NDOCS = 256, 48
TOPICS = [
    ('sport', ['match', 'team', 'score', 'player', 'coach', 'season', 'league', 'goal', 'field', 'training', 'victory', 'rival', 'trophy']),
    ('harbor', ['tide', 'dock', 'vessel', 'cargo', 'anchor', 'harbor', 'sailor', 'lighthouse', 'storm', 'channel', 'ferry', 'net', 'catch']),
    ('orchard', ['apple', 'harvest', 'soil', 'rain', 'branch', 'blossom', 'farmer', 'basket', 'cider', 'frost', 'seed', 'grove']),
    ('circuit', ['voltage', 'resistor', 'signal', 'wire', 'current', 'board', 'sensor', 'diode', 'ground', 'meter', 'switch', 'relay']),
]
rng = np.random.default_rng(0)
OUT.mkdir(parents=True, exist_ok=True); CACHE.mkdir(parents=True, exist_ok=True)
docs = []
for i in range(NDOCS):
    topic, words = TOPICS[i % len(TOPICS)]
    sents = []
    for s in range(14):
        w = rng.choice(words, size=14, replace=True)
        sents.append('Document %d sentence %d about %s: %s.' % (i, s, topic, ' '.join(w)))
    docs.append({'doc_id': 'synth-doc-%03d' % i, 'text': ' '.join(sents)})
with open(OUT / 'docs-100m.jsonl', 'wb') as f:
    for d in docs:
        f.write((json.dumps(d) + '\n').encode())
config = json.dumps({'normalize_embeddings': False}, separators=(',', ':'))
meta = {'format': 'tl-gpu-embcache-v1', 'dim': 384, 'dtype': 'float32-le',
        'key_config_json': config,
        'config_id': hashlib.sha256(config.encode()).hexdigest()[:16],
        'rows_per_shard': RPS}
(CACHE / 'meta.json').write_text(json.dumps(meta))
prefix = b'tl-gpu-embcache-v1\0' + config.encode() + b'\0'
rows = []
for d in docs:
    chunks = chunk_text(d['text']) or [(0, 0, '', 0, 0)]
    for ch in chunks:
        body = ch[2].encode('utf-8')
        key = hashlib.sha256(prefix + body).hexdigest()
        rows.append((key, hashlib.sha256(body).hexdigest(), len(body)))
vecs = rng.standard_normal((len(rows), 384)).astype(np.float32)
with open(CACHE / 'index.jsonl', 'w') as f:
    for g, (key, csha, blen) in enumerate(rows):
        f.write(json.dumps({'key': key, 'chunk_sha256': csha, 'byte_len': blen,
                            'dim': 384, 'shard': g // RPS, 'row': g}) + '\n')
for sh in range((len(rows) + RPS - 1) // RPS):
    vecs[sh * RPS:(sh + 1) * RPS].astype('<f4').tofile(CACHE / ('shard_%06d.f32' % sh))
print(json.dumps({'docs': len(docs), 'chunks': len(rows), 'shards': (len(rows) + RPS - 1) // RPS}))
EOF
# expect: {"docs": 48, "chunks": 96, "shards": 1}

# 5. A real 10K-token pilot through the genuine entry point.
SUP_PYTHON=$CAND/.venv/bin/python bash runtime.sh tools/product_pilot.py --tokens 10000 --profile local --source-root $CAND --data-dir $CAND/synth-data --out $CAND/out-pilot --drain-attribution --drain-census --holon-descriptor-columnar --overrides-columnar --descriptor-matrix-all --per-view-sharing --cold-scan-chunk 4096 --repair-columnar --candidate-source hnsw --drain-bounded-k 32 --candidate-shadow-audit 8
```

Real output of step 5 (from `out-pilot/result.json`): `claim=measured, status=PASS`; input 10,080 actual tokens, 36 complete documents, 72 atoms, 0 cache misses; guided recall@10 0.40 (all-sources, 120 probes), flat recall@10 1.0; final 72 atoms, 0 pending documents; repair 0 iterations, final debt 0; peak parent 87.1 / peak child 81.2 MiB; retained ~8.1 MB; wall ~26 s (39.8 s in the RUNLOG reference run — host-dependent). No Docker is needed: the run path is `runtime.sh` (PYTHONPATH + env + `exec python`), and everything above completed without a container. Mini-run footprint: ~90 MiB peak RSS, ~8 MB output directory, under a minute wall on 2 cores.

---

## Why it matters

A language model cannot fit thirteen thousand documents into its prompt, so any agent working over a growing corpus needs retrieval: pick the right handful of passages first, then read only those. TRACE is built for that picking step — arrivals become searchable the moment they land, and each question descends only the most promising branches instead of scoring everything. The 10M run measured how often the pick contains the answer under a fixed work budget. That is the whole bet: bounded, repairable memory that grows with the agent instead of a context window that does not.

---

## Deep dive

How it works lives behind these links:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — storage ledger, fix stack, reader isolation.
- [docs/CODE-TOUR.md](docs/CODE-TOUR.md) — file-by-file walkthrough of the frozen tree.
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) — unabridged benchmark records and derivations.
- [docs/REPRO.md](docs/REPRO.md) — reproduction commands, environment, pin hashes.
- [Release seam12a-10m-freeze](https://github.com/Anshul48/trace/releases/tag/seam12a-10m-freeze) — frozen source tarball, measurements, and study record.
- [repro-20k/README.md](repro-20k/README.md) — portable 20k-token reproduction (88 documents, precomputed vector cache).
- [tools/verify_freeze.py](tools/verify_freeze.py) / [tools/check_receipts.py](tools/check_receipts.py) / [tools/check_links.py](tools/check_links.py) — freeze, receipt, and link checks run in CI.

---

## Reproduce the 10M benchmark

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

Receipt-recorded requirements: wall 9,494.9 s (~2.6 h); peak RAM ~8.5 GB (parent-process peak 8,489.1 MiB); 2.85 GiB of retained disk; interpreter from the run receipts with numpy 2.5.3, single-threaded BLAS (`OMP/OPENBLAS/MKL_NUM_THREADS=1`), `nice 19`.

### Corpus format

`--data-dir` must contain `docs-100m.jsonl` (one JSON object per line, fields `doc_id` plus `text`) and an `emb_cache/` directory holding `meta.json` (format `tl-gpu-embcache-v1`, dim 384, float32 little-endian), `index.jsonl` rows (`key`, `chunk_sha256`, `byte_len`, dim 384, `shard`, `row`), and `shard_NNNNNN.f32` FP32 little-endian 384-dim memmaps. Tokenizer is TOK_V1; only complete documents count; cache misses are fatal. No corpus generator ships in the package — the only in-repo reference for the layout is the `cache_fixture` in `tests/test_prefix_shards.py`.


<details>
<summary>Why a full 10M reproduction is blocked (2 blockers, stated honestly)</summary>

### Two blockers, stated honestly

There is no one-click 10M reproduction today. A full run is blocked by both of these:

1. The 10M corpus (`docs-100m.jsonl` plus `emb_cache/`) is external and not shipped — the release tarball is source-only (1.2 MB).
2. `--profile vm` is hostname-gated to `trace-build500` (`tools/product_pilot.py:871-872` exits with "VM profile requires existing trace-build500; local runs capped at 1M TOK"). On your own machine the maximum is 1M tokens via `--profile local`.

Labeling rule: running the command above on your own corpus is a **your-corpus 10M-scale run**. **Reproducing the measured o94 numbers** (the proof strip: 0.7367/0.4883, 9,494.9 s, and the rest) additionally requires the o94 corpus and the build VM, and is not possible today.

</details>

---

## Benchmarks (measured, receipt-backed)

<details>
<summary>Full benchmark table (measured, receipt-backed — click to expand)</summary>

| Area | Measured result | Receipt / condition |
|---|---|---|
| Corpus | 10,003,381 tokens, 13,081 docs, 63,441 atoms, 0 cache misses | `result.json` input block |
| Wall | 9,494.9 s total: ingest 586.9 / drain 999.4 / append 1,163.2 / rejection 1.83 / prepare-rejection 170.3 / kill-restart 516.5 / remaining drain 4,654.4 / repair 1,162.1 s | `result.json` phase walls |
| Recall, all-sources | guided 0.7367 vs flat 0.055 | `result.json` evaluation summary, 120 probes |
| Recall, LSO | guided 0.4883 vs flat 0.0017 | `result.json` evaluation summary, 120 probes |
| Fresh visibility | 33/33 within 5 s; p50 96.8 ms, p95 115.5 ms | `result.json` F1 block, n=33 |
| Append latency | ACK-to-query 0.114 s | `result.json` |
| Reader load | 2 threads, 27,796 requests, p50 74.7 ms | `result.json` |
| Memory | parent-process peak 8,489.1 MiB (~8.5 GB); child 7,169.2 MiB | `rss-hwm.txt` + `rss-series.tsv` (1,899 rows) + `result.json` |
| Store | 2.85 GiB retained (3,058,624,883 B) | `result.json` / study record (VM-side) |
| Repair | 6 iterations, 5,847 → 0 | `result.json` |
| Derived caps | `max_delta_entries` 669,436 (37,117 commits / 7,035 atoms measured, margin 2.0); kill wait 316 s; drain k=32, cold-scan chunk 4,096 | `result.json` |
| Pins | probes `b332d62d…`, harness `9f78479a…` (= freeze entry for `tools/product_pilot.py`), final commits 164,195 | `result.json` source pins |

</details>

---

## Status and roadmap

**Status: research preview.** TRACE is an experimental research prototype, proudly so: one measured 10M run on one VM, receipt-backed and honestly labeled — not a product, and no state-of-the-art claims are made.

- Single-run provenance: the numbers come from one run (`o94-scale10m`) on one VM (`trace-build500`); no independent reproduction of the 10M figures exists yet.
- The 10M corpus and embedding cache are not redistributed; the tarball is source-only (1.2 MB).
- No Python version string appears in the run receipts (the 5-minute path above was verified on Python 3.12.3 with numpy 2.5.4 against receipts recording numpy 2.5.3).
- Retained-disk (2.85 GiB) and corpus-path figures are VM-side and cannot be verified from another host.
- Recall figures measure protocol agreement with an exact oracle on the staged corpus — not semantic relevance, ranking quality in general, or latency guarantees on other hardware.
- TRACE is single-writer append-only with crash recovery to a consistent ledger boundary; it does not implement distributed transactions.

Roadmap:

- Re-export the explorer data files from the o94 run so the live pages show seam12a numbers (until then, the identity note above stands).
- Publish a corpus fetch or prep script so a public 10M reproduction is possible end to end.
- Qualify larger scales (100M–500M+ tokens); this is future work, not a claim.
- Keep the 20k portable path working as the one-command local proof.

---

## Freeze identity

- Freeze: **seam12a**, tarball sha256 `8d3bbb6bf53e1731811065a9de156a9997be740d598cd1dfa0a3d946928dbf64` (verified `sha256sum -c`: OK; manifest: 253 entries, 0 diffs).
- Run: **o94-scale10m**. Pins: probes `b332d62d…`, harness `9f78479a…`, final commits **164195**.
- Manifest: [freeze-src/cand/SOURCEFREEZE.json](freeze-src/cand/SOURCEFREEZE.json). Freeze check: `python3 tools/verify_freeze.py`.

---

## License

Apache-2.0 ([LICENSE](LICENSE)). Corpus text excerpts and vector models keep their upstream licenses; see [repro-20k/LICENSES-DATA-MODEL.md](repro-20k/LICENSES-DATA-MODEL.md).

## Related: ANIMA

[ANIMA](https://github.com/Anshul48/anima) owns agent orchestration; TRACE owns the retrieval overlay. The two are separate systems with no shared runtime — this README covers TRACE only.
