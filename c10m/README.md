# C2-10M freeze-v2 shipping candidate

Identity: **C2-10M freeze-v2 qualified release, SHIP 2026-10-08**
(independent lane-READ10M review, 7/7 gates PASS).
Shipped store pin: `ee06a4e4-83f7-4315-9e23-bd6e5034cccb:0:95436`.
Producer freeze label: `c2-b100m-producer-freeze-002` (89 files, closure 44)
— **89/89 entries recovered byte-exact**, closure 44/44 (architect A36).

Provenance: coordinator channel `provenance/CANDIDATE.md` (READY 2026-10-14T09:50Z)
+ `provenance/REPRO.md` + `producer-recovery/{REPORT.md,RECOVERY.json}`.
Every hash below was re-verified by the packager before copying; verify again
with `sha256sum -c c10m/PINS.sha256` from the repo root.

## Layout

- `producer/` — 85 freeze-v2 producer code files, exact bytes. These bytes
  BUILT the shipped store (ingest/maint/lifecycle/prodstate + corpus/profile/
  cache/encoder). Producer `dossier.py`/`index.py` are the PRE-REPAIR bytes
  (`fe7b0039…`/`8b267be0…`).
- `data/` — the 4 data inputs + derivation maps + portable reconstruction
  tool (`reconstruct_inputs.py`, verified `RECONSTRUCT PASS`: reproduces
  `docs-100m.jsonl` `c098fdac…` and `docs-10m.jsonl` `04bbbb3e…`
  byte-exactly). Dataset-specific licenses/attribution in
  `data/DATA-README.md` (NOT blanket Apache).
- `serving/` — the 7 serving files that ANSWER queries (shipped bytes):
  repaired `dossier.py` (`93871fb3…`) + `index.py` (`b8bc1390…`) + `relserve.py`
  + `serving/generation.py` + `query.py` (`d7756e72…`, ONLY from
  `lane-CAP03/snapshots/pre-176/query.py` — the live tree `a9d4be55…` is
  post-ship CAP03 drift and is NOT shipped) + `relquery.py` + `prodstate.py`.
  The serving overlay stays SEPARATE from the producer tree: apply it on top
  of `producer/` to obtain the runnable query stack (the demo does exactly
  this into a temp dir and verifies hashes first).
- `policy/` — serving policy pins: `CRITERIA.v3.json` (`e7d0139a…`),
  `requirements.v4.json` (`cf63c41a…`), `relations-10m.anchors-v1.json`
  (`9728129b…`). Budgets M80-P100-A40.
- `PINS.sha256` — sha256 manifest of every file under `c10m/`.

## Full pins (sha256)

Serving (what answers):

| file | sha256 |
|---|---|
| tl-sys/tlsys/dossier.py | `93871fb3e7f63e58d9c48c113efecd551a5271c73184968259f8cce3df4e7ac0` |
| tl-sys/tlsys/relquery.py | `0fe79c501cf3582face656ff3da7340534ae871780f4e16c7e0f876f6afb45a8` |
| tl-sys/tlsys/relserve.py | `61b69a84c648717955426e3bbb3ffde7526658483f05a7532f9d145582bc9b71` |
| tl-sys/tlsys/query.py | `d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce` |
| tl-sys/tlsys/index.py | `b8bc139008a9da185f3438823836e03b8a171a10d0677faf7448ed21afcebef0` |
| tl-sys/tlsys/serving/generation.py | `929709390af18e7511197164d399ba71f368c767c2fc2df3680f43254424b22f` |
| tl-sys/tlsys/prodstate.py | `e7a4370c3e6faf122927db34919b2d42838f0b800edc4c8f877b564f405a47b1` |

Also verified unchanged and shipped inside `producer/`: `tlsys/fuse.py`
`53cdd3382746f00b1ad9e7547e7bc4c42d51ba7d3e241173f403493cd71e5fc3`.
Producer build pins (`ingest.py` `5ac506ee…`, `maint.py` `eab79b07…`,
`lifecycle.py` `2d822d23…`, …): full table in `PINS.sha256`; corpus/config
pins (`docs-10m.jsonl` `04bbbb3e…`, anchors `9728129b…`, profile
`c2-100m-producer-001` `351c7e52…`, MiniLM-L6-v2 rev `1110a243…`) in
CANDIDATE.md §2a.

Excluded: live-tree `query.py` `a9d4be55…` (post-ship MMR repair),
freeze-v4 producer drift, campaign-_186 bytes (shipped separately as
evidence WITH original F2 FAIL, never as the build).

## Rebuild inputs: 89/89 recovered (recipe, not bundle)

All four data inputs were recovered byte-exact from the local v3 freeze
dir (no VM fetch needed) and independently re-verified 89/89 against the
freeze manifest:

- `inputs/corpus-manifest-10m.json` (1164 B, `e56ac0a9…`) — shipped in `data/`
- `inputs/prefix-doc-ranges.json` (148231 B, `c255a52f…`) — shipped in `data/`
- `inputs/relations-10m.json` (1281 B, `fef3ec6a…`) — shipped in `data/`
- `inputs/docs-10m.jsonl` (64291035 B, `04bbbb3e…`) — bundled as
  deterministic gzip (`data/bundle/`, `--from-bundle` verified
  `RECONSTRUCT PASS`, byte-identical) and reproducible from pinned
  upstreams + `derivation.json` (upstream path, same exact bytes).

A rebuild consumes `producer/` + `data/` via the documented recipe; no new
10M run was performed for this publication. The runnable surfaces in this
tree are: the primary demo (pinned serving stack on a small synthetic
corpus, `demos/demo_c10m_narrow.py`), the input-reconstruction tool
(`c10m/data/`), and the bench materials (`benchmarks/evidence/`).

## Deployment condition (part of the release)

Persistent serving process + resident MiniLM encoder. Measured warm
1620–2358 ms, storage-cold 3530 ms PASS vs 5 s; fresh-process first
request ~8–10 s recorded as exceeding (voids latency claims outside the
condition; correctness stands). Bench index-attach cost (~2 min/request
on the 10M store) is reported separately in `benchmarks/evidence/`.
