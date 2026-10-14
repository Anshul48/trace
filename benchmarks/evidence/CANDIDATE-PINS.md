# CANDIDATE-PINS.md — source family + byte hashes + receipt identities

The benchmarked code is the **C2-10M freeze-v2 qualified release**
(SHIP 2026-10-08, store pin
`ee06a4e4-83f7-4315-9e23-bd6e5034cccb:0:95436`). Every hash below was
re-verified by the packager before copying (see `ARTIFACT-INVENTORY.md`
for the full file×hash table).

## Serving bytes (what was benchmarked)

| file | sha256 |
|---|---|
| `tl-sys/tlsys/dossier.py` | `93871fb3e7f63e58d9c48c113efecd551a5271c73184968259f8cce3df4e7ac0` |
| `tl-sys/tlsys/relquery.py` | `0fe79c501cf3582face656ff3da7340534ae871780f4e16c7e0f876f6afb45a8` |
| `tl-sys/tlsys/relserve.py` | `61b69a84c648717955426e3bbb3ffde7526658483f05a7532f9d145582bc9b71` |
| `tl-sys/tlsys/query.py` (pre-176 only) | `d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce` |
| `tl-sys/tlsys/index.py` | `b8bc139008a9da185f3438823836e03b8a171a10d0677faf7448ed21afcebef0` |
| `tl-sys/tlsys/serving/generation.py` | `929709390af18e7511197164d399ba71f368c767c2fc2df3680f43254424b22f` |
| `tl-sys/tlsys/prodstate.py` | `e7a4370c3e6faf122927db34919b2d42838f0b800edc4c8f877b564f405a47b1` |

Bytes live in `c10m/` (`c10m/PINS.sha256`, 110 entries). The RUN.json
`implementation_identity` blocks in the original runs self-authenticate
these same serving shas per scored run.

## Bench harness pins

| artifact | sha256 | bytes |
|---|---|---|
| `trace_bench-0.3.0-py3-none-any.whl` | `3c11d3ed2ae8e27b23c7939c23f6871cbd04c6b806f924399dd3abb0c5abb759` | 440383 |
| `c2_bench10m.py` (A1 primary + A2 k100) | `0f6e7bc3181f9702a453fd5b7fc0c7a1121cf8543d73af1d0a92d2a1b103fc71` | 11088 |
| `c2_rekey.py` (R1) | `07606feaa19131c11458161a8463a528a72736a400a074b1daf54e7fdf84e56a` | 2538 |
| `c2_store_probe.py` (A3) | `0ceb3670e905a9b82a01978e8243e2fa360043fb30437b44efbd1e2d5df0602a` | 3800 |
| `stage_pinned.py` (S1, 162-fix) | `06b279cdd32accaa144cf0cb5fcd64c58696b55a7bdd161f01b8d255ff5738b1` | 12877 |
| `upstream-links.json` | `e5fb424a37d02681a324b477d318fbeb07ae9d3acee7431344994f40f7e9d53c` | — |

Bytes live in `harness/`. Note: the vendored `SHA256SUMS` staging record
names the pre-fix S1 (`dfa113b8…`); the shipped `stage_pinned.py` is the
lane-final 162-fix byte (`06b279cd…`, role-qualified raw paths closing the
pony staging collision). Both facts are preserved, not reconciled away.

## Policy pins

Budgets M80-P100-A40. `CRITERIA.v3.json` `e7d0139a…`, `requirements.v4.json`
`cf63c41a…`, `relations-10m.anchors-v1.json` `9728129b…` (bytes in
`c10m/policy/`; full shas in `c10m/README.md`).

## Receipt identities

- Ship record: `receipts-10m-shipped/ship-record/` (`c2-10m-SHIPPED.md`
  `c092ff7b…`, `READ10M-REPORT.md` `2518a520…`, `BUILD-RECEIPT.json`
  `a8b00b0b…`, `C2-10M-UPLOAD.json` `64c0b8e0…`).
- BENCH10M: `receipts-10m-shipped/lane-BENCH10M/` (REPORT + SCOPE +
  per-lane compares + probes + logs; big RUN.json/TREC files are
  hash-inventoried in `ARTIFACT-INVENTORY.md`, not bundled, except the
  full smoke lane).
- Frozen 10M rung: `receipts-10m-shipped/scale10m/` (`metrics.json`
  `679575e4…`, `rows.jsonl` `c08b2b77…`, 48 MB queries file
  `5222b2e5…` by hash record only).
- Campaign-186 (later, failed-gate evidence): `receipts-186/` (verdict
  `febc3010…`, 214953 B; `pins-186.sha256` `6ae0df4b…`, 17/17 OK
  re-verified at source; 31 receipt dirs inventoried, not bundled).
- 10M gate eval protocol: `provenance/queries-10m.json` (`77336d62…`),
  `provenance/CONFIRM-INPUTS.v3-10m.json` (`ece682c7…`).
