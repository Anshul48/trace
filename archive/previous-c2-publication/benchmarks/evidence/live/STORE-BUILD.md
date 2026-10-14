# 10M store-build recipe (true inputs; no new 10M run performed)

`reconstruct_inputs.py --out-dir /tmp/c10m-inputs --from-bundle`
extracts the EXACT `docs-10m.jsonl` bytes — it does NOT rebuild the
10M store, and extraction alone satisfies NONE of the builder's root
contract below. This recipe documents the true build inputs and the
portable embedding-cache acquisition path. No 10M build was executed
for this release (prohibited); the recipe's control flow is verified
on a tiny fixture, and every refusal below is quoted from the actual
builder code (`c10m/producer/lane-RELAUNCH/b100m_build_c2.py`).

## 1. Builder contract (`--mode 10m`)

```
PYTHONHASHSEED=0 HF_HUB_OFFLINE=1 python lane-RELAUNCH/b100m_build_c2.py --mode 10m \
  --root <ROOT> --out <OUT> --profile <ROOT>/inputs/c2-profile-100m.json \
  --cache-dir <EMB-CACHE>
```

| input | required content | source in this tree |
|---|---|---|
| `<ROOT>/tl-sys`, `<ROOT>/tl-eval`, `<ROOT>/tl-candidate-batch`, `<ROOT>/coordination` | producer code tree (store/ingest/index + `gpu_encode` + `gate_runner` + candidate committer/store + lane-G profile) | `c10m/producer/` (89/89 frozen bytes) |
| `<ROOT>/inputs/docs-10m.jsonl` | exact corpus, sha `04bbbb3e…ce3fd`, 64291035 B, 3099 rows | `c10m/data/DATA-README.md` §2 (bundle or upstream path) |
| `<ROOT>/inputs/relations-10m.anchors-v1.json` | anchors, sha `9728129b…` | `c10m/producer/inputs/` (ships) |
| `<ROOT>/inputs/prefix-doc-ranges.json` | frozen prefix geometry | `c10m/data/inputs/` (ships) |
| `<ROOT>/inputs/c2-profile-100m.json` | validated catalog-enabled profile | `c10m/producer/inputs/` (ships) |
| `<EMB-CACHE>` | `tl-gpu-embcache-v1` cache covering EVERY chunk, `config_id` == builder's pinned config | §2 below (prepare; the historical machine-local cache is NOT portable) |
| `<OUT>` | fresh lane dir whose path contains `lane-relaunch` (guard), with `lane-relaunch` in the name | create per run |

Refusals, verbatim behavior: `--out` not under a `lane-relaunch`
path → `refusing: --out is not under lane-relaunch` (rc=2); docs
hash mismatch → `refusing: docs hash ... != pin` (rc=2); anchors
mismatch → `refusing: anchors hash ... != pin` (rc=2); cache
`config_id` mismatch → `refusing: cache config ... != ...` (rc=2);
any chunk missing from the cache → `StrictCacheMiss` (strict, no
fallback — the build aborts rather than mix encoders silently).

## 2. Embedding-cache preparation (portable path)

The historical cache is machine-local (`/srv/tl/stores/...`) and is
NOT a public input. Regenerate an equivalent cache with the pinned
model and the PRODUCT chunker/codec (no reimplementation):

```bash
# 0. exact input + weights (see DATA-README §2 and live/README §1)
python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs --from-bundle
HF_HOME=/tmp/c2-weights python benchmarks/evidence/live/fetch_weights.py

# 1. prepare the cache (long CPU encode at 10M-chunk scale; resumable)
HF_HOME=/tmp/c2-weights HF_HUB_OFFLINE=1 \
  python benchmarks/evidence/live/prepare_emb_cache.py \
  --docs /tmp/c10m-inputs/docs-10m.jsonl --cache-dir /tmp/c2-emb-cache
# EMB-CACHE READY: /tmp/c2-emb-cache rows=<n> config_id=<id>
```

The wrapper hash-gates `--docs` to the 10M pin, chunks with the
product `tlsys.ingest._supplied_chunks`, encodes with pinned MiniLM
(`normalize_embeddings=False`, the pinned CPU convention), writes via
the product `gpu_encode.cache.CacheWriter` (recording `produced_by`
stack versions), then re-locates EVERY chunk key and fails closed on
any miss. `--max-docs N` / `--no-pin-check` are PARTIAL wrapper-
validation modes only (the script says `EMB-CACHE PARTIAL`, never
build-serving).

## 3. Staging the disposable build root (shape)

```bash
ROOT=/tmp/lane-relaunch-build/work   # any path; OUT must contain "lane-relaunch"
mkdir -p $ROOT/inputs
cp -r c10m/producer/tl-sys c10m/producer/tl-eval c10m/producer/tl-candidate-batch c10m/producer/coordination $ROOT/
# serving overlay (same assembly as the bench runtime): the only bytes
# that differ from producer are dossier.py (query assembly; the builder
# never imports it) and index.py (additive stages=None default; the
# builder never passes stages), so the build is byte-identical with or
# without the overlay — apply it to keep one shipped family.
cp c10m/serving/tl-sys/tlsys/dossier.py c10m/serving/tl-sys/tlsys/index.py \
   c10m/serving/tl-sys/tlsys/query.py c10m/serving/tl-sys/tlsys/relquery.py \
   c10m/serving/tl-sys/tlsys/relserve.py c10m/serving/tl-sys/tlsys/prodstate.py \
   $ROOT/tl-sys/tlsys/
cp c10m/serving/tl-sys/tlsys/serving/generation.py $ROOT/tl-sys/tlsys/serving/
cp c10m/producer/inputs/c2-profile-100m.json \
   c10m/producer/inputs/relations-10m.anchors-v1.json \
   c10m/data/inputs/prefix-doc-ranges.json $ROOT/inputs/
cp /tmp/c10m-inputs/docs-10m.jsonl $ROOT/inputs/
PYTHONHASHSEED=0 HF_HUB_OFFLINE=1 python c10m/producer/lane-RELAUNCH/b100m_build_c2.py \
  --mode 10m --root $ROOT --out /tmp/lane-relaunch-build/build-10m-c2 \
  --profile $ROOT/inputs/c2-profile-100m.json --cache-dir /tmp/c2-emb-cache
```

## 4. Honest limits

- The recipe above was NOT executed end to end (no new 10M run); what
  is verified: exact-input extraction (`RECONSTRUCT PASS`), wrapper
  control flow + strict coverage check on a tiny fixture (see
  TEST-REPORT.md C4 §), and every quoted refusal against builder
  source.
- A full cache prepare + build is hours of CPU encode plus store
  ingest/drain/organize; cost is unmeasured here.
- Store BYTE-identity with the historical `:0:95436` pin is NOT
  claimed: birth UUIDs and revision-dependent identities vary per
  fresh build by design (same caveat the demo documents).
