# Small-scale reproduction — TRACE stack-fork `38c66bef` (20k exact prefix)

This directory closes the clean-checkout reproduction gap for the frozen
stack-fork candidate. The recorded 10M qualification ran on VM-only data
(`~/beam/pkg/data`); nothing here pretends those assets are in a checkout.
Instead, a verified preparation script exports a **small exact prefix**
(actual documents + actual cached FP32 vectors, read-only from the VM)
that the **actual frozen harness** consumes locally, end to end.

Scope honesty: the small run reproduces the *protocol* at 20k tokens with
the frozen engine. Its numbers are **not** the 10M qualification numbers;
the 10M record remains the receipts summarized in [PROTOCOL.md](PROTOCOL.md).

## What is here

| Path | What |
|---|---|
| `prep_small_prefix.py` | Prep + verify script (stdlib; `verify` needs NumPy). SHA256 in `MANIFEST.json`. |
| `small-prefix-20k.tar.gz` | Exported portable data dir (270,494 B): exact 88-document prefix of `docs-100m.jsonl` (20,030 TOK_V1 tokens), verbatim `emb_cache/meta.json`, repacked subset `emb_cache` (144 vectors), `exporter-receipt.json`. |
| `data-20k/` | The same tarball, unpacked and verified. |
| `pilot-20k-out2/` | Local small-scale pilot JSON output (`result.json` status **PASS**, wall 41.9 s). First attempt failed closed on missing `blake3` (harness refuses silent hash swaps); installing `blake3` fixed it. |
| `PROTOCOL.md` | The recorded 10M protocol, gates, both LSO modes, caps, hardware, negatives. |
| `LICENSES-DATA-MODEL.md` | Data/model licences and attribution for everything redistributed here. |
| `MANIFEST.json` | Hashes of script, export, receipts relied on, and verification results. |

## Reproduce it yourself (clean checkout)

Prerequisites: the frozen candidate tree (`../freeze-src/cand`,
SOURCEFREEZE `38c66bef71fbc8768a2887024fecf1bf58ff90f3feaf3a922d4c8b51a43a0d54`),
Python 3.12 with `numpy` and `blake3`, and — only for re-export — existing
`gcloud` SSH auth to `trace-build500` (read-only; no VM writes, no new runs).

```bash
# 1. Verify the frozen source (207/207 + harness pin 9f516288…)
python3 prep_small_prefix.py verify-freeze --cand ../freeze-src/cand

# 2a. Use the committed export …
python3 prep_small_prefix.py unpack --tar small-prefix-20k.tar.gz --data-dir data-20k
# 2b. … or re-export the same prefix read-only from the VM
python3 prep_small_prefix.py export-vm --tokens 20000 --out small-prefix-20k.tar.gz

# 3. Verify: frozen RealPrefix over the portable dir must reproduce the
#    exporter's full-cache receipt (prefix + used-vector hashes exact, 0 misses)
python3 prep_small_prefix.py verify --tokens 20000 --cand ../freeze-src/cand --data-dir data-20k

# 4. Run the actual small-scale protocol with the frozen harness
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=../freeze-src/cand/fork/tl-sys:../freeze-src/cand/fork/tl-candidate-batch/candidate:../freeze-src/cand/tools \
python -B ../freeze-src/cand/tools/product_pilot.py --tokens 20000 --profile local \
    --out ./pilot-20k-out2 --source-root ../freeze-src/cand --data-dir ./data-20k
```

Expected step-3 result (observed 2026-10-14): `VERIFY PASS` — actual_tokens
20030, complete_documents 88, atoms/distinct_chunks 144, cache_misses 0,
`prefix_raw_sha256 530e51c7…f4ed119`, `used_vector_sha256 94f24eca…c6fbbf`
(both identical to the full-cache receipt computed on the VM), verbatim
meta hash `e5f9c706…`. The subset `cache_index_sha256` (`a3428523…`) differs
from the full-cache value (`885d31c0…`) by construction: it hashes the
subset index file. Row numbers in the subset index are renumbered `0..143`
in `shard_000000.f32`; keys, chunk hashes, and vector bytes are unchanged.

Expected step-4 result (observed): exit 0, `result.json` `"status": "PASS"`,
wall 41.9 s, 120 probes evaluated all-sources + leave-source-out. The 20k
recall values in that file describe this 88-document prefix only.

## What this does NOT do

- No full 10M run, no multi-gigabyte corpus/cache copy (the export is 264 KiB).
- No VM writes: the exporter runs from stdin and emits a tar stream on
  stdout; VM data files are mode `r--r--r--` and were only read.
- No synthetic substitute data or encoder: documents and vectors are the
  qualification cache's own bytes for this prefix.
- Larger local prefixes work the same way (`--tokens 1000000`, profile
  `local` hard cap), but only the 20k export is committed here.
