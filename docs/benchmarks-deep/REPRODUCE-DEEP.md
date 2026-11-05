# REPRODUCE-DEEP — re-run the in-depth benchmark numbers

Scope: the NEW 20k-prefix numbers behind
[BENCHMARKS-DEEP.md](../BENCHMARKS-DEEP.md) (sections 5-7) and the section-3
replay aggregation. Environment: CPython 3, stdlib only, Linux/WSL (tested
scope; native Windows and macOS are untested). Run every
command from the repo root in a Unix shell. Observed on a laptop CPU: `run_20k.py` wall
~6.4 s with peak resident set ~23.3 MB; the other two scripts finish in
under a second. Platform note: `run_20k.py` imports the Unix-only
`resource` module unconditionally and reads `ru_maxrss` as KiB
(`results/run_20k.py:4`, `results/run_20k.py:219`), so other platforms
would need platform-specific handling that is not shipped here.

## Commands (in order)

```bash
python3 docs/benchmarks-deep/results/run_20k.py > /tmp/run_20k.check.json
# observed: exit 0

python3 docs/benchmarks-deep/results/agg_replay.py > /tmp/replay_agg.check.json
# observed: exit 0

python3 docs/benchmarks-deep/figures/gen_figures.py
# observed: exit 0, prints "wrote 5 SVGs" (rewrites the SVGs in place)
```

## Checks the re-run must pass (all held)

Replay aggregation output is byte-identical to the shipped JSON:

```bash
cmp /tmp/replay_agg.check.json docs/benchmarks-deep/results/replay_agg.json
```

The 20k output is identical except wall-clock and RSS fields (`timings_s`,
`peak_rss_mib`, per-budget `per_query_wall_mean_s`):

```bash
python3 - docs/benchmarks-deep/results/run_20k.json /tmp/run_20k.check.json <<'EOF'
import json, sys
DROP = {"timings_s", "peak_rss_mib", "per_query_wall_mean_s"}
def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in DROP}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o
a = [strip(json.load(open(p))) for p in sys.argv[1:3]]
print("IDENTICAL" if a[0] == a[1] else "DIFFER")
EOF
```

Regenerated SVGs are byte-identical to the shipped ones:

```bash
(cd docs/benchmarks-deep/figures && sha256sum *.svg > /tmp/figs.sha)
python3 docs/benchmarks-deep/figures/gen_figures.py
(cd docs/benchmarks-deep/figures && sha256sum -c /tmp/figs.sha)
```

Shipped receipts match their hashes:

```bash
(cd receipts/benchmarks-deep && sha256sum -c SHA256SUMS)
```

Sanity facts that must hold in `results/run_20k.json` (all held): full-open
budgets equal exact (leaf_L81 and parent_L51 recall@10, recall@100,
self-nDCG@10, fidelity-nDCG@10 all 1.0000); no nDCG above 1.0;
`replay_agg.json` holds 144 questions with fields g/f/tg/tf present.

## Seeds and fixed choices

- Noise queries for abstention: seed 7, `random.gauss(0,1)`, dim 384,
  normalized (48 queries). Only randomness in the job.
- Tie rule (preregistered): equal scores break by atom id ascending.
- Atom->vector join: `sha256(doc_bytes[byte_span[0]:byte_span[1]])` matched
  against `emb_cache/index.jsonl` `chunk_sha256`; script asserts 144/144
  distinct rows or aborts.
- Centroids: mean of member vectors, L2-normalized; cosine everywhere.
- The `.png` files next to the SVGs are prebuilt renderings of the SVGs
  (previews); the SVGs are the receipt figures.

## What is NOT reproducible from here

- The 50-search sealed-library run (needs the sealed 100M store; its
  records are shipped in `../../receipts/benchmarks-deep/`).
- The 504.5M/310.5M builds and the 1.53B side test (machines gone).
- The BEIR stand-in tables (its data is gone; its own scripts need network).
