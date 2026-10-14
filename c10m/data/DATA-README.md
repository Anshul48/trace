# C2-10M build-input data package

Reconstruction kit for the exact C2-10M freeze-v2 corpus inputs
(`c2-b100m-producer-freeze-002`). With `c10m/producer/` (85 code files) and
the maps below, the full 89-entry frozen manifest is now reproducible:
89/89 entries recovered and independently hash-verified (architect A36).

The 64 MB `docs-10m.jsonl` build input ships here as a deterministic
gzip bundle (`bundle/`, 21787645 B) AND is reproducible from pinned
upstreams via the selection/derivation maps, metadata, checksums, one
vendored upstream, and the portable tool — both paths are hash-verified
to the same exact bytes. Dataset-specific license and attribution terms
are in §5 below — they govern the bundled/reconstructed texts, NOT the
repository's blanket Apache-2.0 grant.

## 1. Contents

| path | bytes | sha256 | role |
|---|---|---|---|
| `inputs/corpus-manifest-10m.json` | 1164 | `e56ac0a9…` | frozen slice manifest (pins, counts, chunker) |
| `inputs/prefix-doc-ranges.json` | 148231 | `c255a52f…` | frozen prefix geometry map |
| `inputs/relations-10m.json` | 1281 | `fef3ec6a…` | analyst-supplied typed relations (scope note inside) |
| `inputs/derivation.json` | 389409 | `1343550c…` | per-row parent ordinals (0-based) + geometry |
| `inputs/preflight-100m.json` | 3339 | `6bddf685…` | upstream pins + `selection_formula` (PASS verdict) |
| `inputs/INPUTS-REPORT.md` | 17795 | `c3002a40…` | verbatim freeze-lane report (provenance) |
| `upstream/trace_engineering_curated.json` | 182169 | `210a20a4…` | vendored exact upstream (Apache-2.0 fixture) |
| `bundle/docs-10m.jsonl.gz` | 21787645 | `31002b8c…` | deterministic gzip (`gzip -n -9`) of exact `docs-10m.jsonl` |
| `bundle/verify_docs_10m.py` | — | (pinned in `../PINS.sha256`) | corrected standalone bundle verifier (A52; stdlib only, alias guards + atomic extraction) |
| `bundle/{LICENSE-DATA,ATTRIBUTION}.md` | — | (pinned) | asset-level license + per-article attribution notices |
| `bundle/provenance.json` | — | (pinned) | machine-readable bundle provenance (pins, mix, method) |
| `reconstruct_inputs.py` | — | (pinned in `../PINS.sha256`) | fetch/reconstruct/verify tool (stdlib only) |

Full hashes: `../PINS.sha256` (+ tool §`PINS` table, same values).

## 2. Recipe (bundle first, upstream recipe second)

Guaranteed path — no 1.4 GB delta or 100M parent needed:

```bash
python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs --from-bundle
# RECONSTRUCT PASS (--from-bundle): 3099 rows, 64291035 B, 04bbbb3e… exact
```

The tool hash-gates the bundle (`31002b8c…`), then delegates
extraction+verification to the corrected `bundle/verify_docs_10m.py`
(A50/A52: asset/out alias guards, sibling-temp atomic extraction,
existing output and asset preserved on every failure; `VERIFY PASS`
checks gz bytes/sha, gzip mtime 0, raw sha/bytes/rows, JSONL keys) —
failing closed on any mismatch. Standalone equivalent (adopted from
the channel data packager, A47 + corrected A52):
`python bundle/verify_docs_10m.py --out FILE`. `python
bundle/verify_docs_10m.py --self-test` runs the 7 bounded
alias/corruption checks.
Manual equivalent: `gunzip -c bundle/docs-10m.jsonl.gz | sha256sum`
must print `04bbbb3e…` (64291035 bytes).

Provenance/audit path — rebuild from pinned upstreams (also verifies
the 100M parent the slice derives from):

```bash
python c10m/data/reconstruct_inputs.py --out-dir /tmp/c10m-inputs \
    --scifact /path/to/scifact-corpus.jsonl \
    --delta   /path/to/wikipedia_delta.jsonl
# curated defaults to upstream/trace_engineering_curated.json
# holders of the exact bytes: --check-only --docs-100m A --docs-10m B
```

The tool hash-gates every input BEFORE use and fails closed naming the
expected pin. It assembles `docs-100m.jsonl` (30927 rows, 622471790 B,
`c098fdac…`) per `selection_formula`, then slices `docs-10m.jsonl`
(3099 rows, 64291035 B, `04bbbb3e…`) via `derivation.json` ordinals.

Upstream acquisition:

- curated — vendored above; no fetch needed (`210a20a4…`, 182169 B).
- scifact `corpus.jsonl` (5183 rows, BeIR `{_id,title,text,…}` format,
  `cf30fea2…`, 8111749 B) — obtain the BeIR-format SciFact corpus and let
  the hash gate accept it. Recorded distribution: the BEIR project
  (`https://github.com/beir-cellar/beir`, per trace-bench `catalog.json`
  `beir-scifact` entry) and its mirrors. The `cf30fea2…` pin is the
  acceptance test; any byte-differing file fails closed.
- `wikipedia_delta.jsonl` (`ffe48544…`, 1425430486 B, 137360 rows; only
  the first 25644 rows in file order are consumed) — machine-local
  derived file (enwiki XML chunks → JSONL). No public fetch URL for
  these exact bytes was recorded in the scoped sources, so this recipe
  documents a provenance gap honestly (see §6) instead of inventing one.
  Identify any candidate copy by hash + size + row count + first-row
  `doc_id` `wikipedia:004a39dde9deafe0`.

## 3. Verification evidence (packager runs, 2026-10-14)

Bundle path (`--from-bundle`, via the corrected verifier):

```text
small inputs: 3/3 hash-verified
gz OK: 21787645 bytes, sha256 31002b8c…760a, mtime 0
raw OK: 64291035 bytes, sha256 04bbbb3e…ce3fd, 3099 rows, keys {doc_id,text}
VERIFY PASS
docs-10m: 3099 rows, 64291035 bytes, sha 04bbbb3ea3425a49… exact (from bundle)
RECONSTRUCT PASS (--from-bundle)
```

plus `cmp` byte-identical against the independently recovered exact
bytes and `gzip -dc`, and gzip determinism confirmed (re-compression
reproduces `31002b8c…`). Alias/truncate negatives (same-path,
symlink, hardlink, truncated asset) all exit 1 with asset + existing
output preserved and no temp leftovers (see TEST-REPORT.md C3 §).

Upstream path (against the pinned local upstreams):

```text
small inputs: 3/3 hash-verified
upstreams: 3/3 hash-verified
docs-100m: 30927 rows, 622471790 bytes, sha c098fdace3a73efc… exact
docs-10m: 3099 rows, 64291035 bytes, sha 04bbbb3ea3425a49… exact
RECONSTRUCT PASS
```

Supporting checks: parent line serialization
(`separators=(",",":")`, `ensure_ascii=False`) reproduced on 3195 sampled
rows with 0 mismatches; curated paragraphs 100/100; scifact head rows
conform to `(title + "\n" + text).strip()`; derivation ordinals are 0-based
(12..30919) and every slice `doc_id` matches its mapped parent row. The
naive contiguous-prefix hypothesis was tested and refuted (ordinals are
non-contiguous). Full-file hashes above are the acceptance criterion.

## 4. Chain summary

```text
scifact corpus.jsonl (5183, cf30fea2) ─┐
curated fixture (100, 210a20a4) ───────┼─► docs-100m.jsonl (30927, c098fdac)
wikipedia_delta prefix (25644, ffe48544)┘         │
                        derivation.json ordinals  ▼
                                    docs-10m.jsonl (3099, 04bbbb3e)
```

## 5. Licenses and attribution (dataset-specific terms)

These terms govern the bundled and reconstructed corpus texts. They are
recorded from the cited license records — no new grants are invented
here, and the repository's Apache-2.0 files do not extend over
third-party texts. Asset-level notices travel with the bundle itself:
`bundle/LICENSE-DATA.md` + `bundle/ATTRIBUTION.md` (row mix 2605
Wikipedia / 486 SciFact / 8 curated; per-article URL rule with worked
examples; machine-readable `bundle/provenance.json`). This section is
the package-level record; the bundle files govern the asset bytes.

- SciFact abstracts (the 5183 scifact rows; the historical 10M input uses
  corpus abstracts, not claim annotations): **ODC-By-1.0**, per the
  original record `https://github.com/allenai/scifact/blob/master/LICENSE.md`
  (claims/evidence annotations CC-BY-4.0, `corpus.jsonl` abstracts
  ODC-By-1.0, code Apache-2.0). Attribution: Wadden et al., SciFact,
  EMNLP 2020 (findings); abstracts via S2ORC; BeIR distribution format
  per Thakur et al., BEIR, NeurIPS 2021.
  Recorded downstream label differences (not adopted as governing terms
  for the abstracts): the BeIR HuggingFace mirror dataset card labels
  CC-BY-SA-4.0, and trace-bench `catalog.json` labels the SciFact entry
  "CC BY-NC 4.0 (SciFact) / Apache 2.0 (BEIR Benchmark)". Both are
  downstream labels; the original allenai record above governs here.
  No non-commercial restriction is asserted beyond what the cited
  original record states.
- English Wikipedia text (the wikipedia_delta rows, bundled and
  reconstructed): **CC BY-SA**, with attribution per the Wikimedia
  Terms of Use (`https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use`
  §7). Per-row article title metadata is preserved in every row
  (`(title + "\n" + text)` form; titles also head each text), which
  enables per-article attribution: titles have the mechanical form
  `wikipedia/Title_With_Underscores`, resolving to
  `https://en.wikipedia.org/wiki/Title_With_Underscores` (mapping rule
  stated, not fetched). Underlying source form: enwiki XML dump chunks
  (exact dump date/URL unrecorded in the scoped sources — stated in §6).
- `trace_engineering_curated.json` (vendored): **Apache-2.0**
  trace-bench fixture ("Generated 320-query technical regression
  fixture; not an independently reviewed quality benchmark").
- `relations-10m.json`: analyst-supplied typed relations (3 links + 2
  qual signals); no automatic-extraction claim (per the file's analyst
  note, preserved verbatim).
- Freeze records (`corpus-manifest-10m.json`, `prefix-doc-ranges.json`,
  `derivation.json`, `preflight-100m.json`, `INPUTS-REPORT.md`):
  project-authored build metadata.

## 6. Known provenance gaps (stated, not hidden)

1. `wikipedia_delta.jsonl` (the 1.4 GB upstream) has no recorded public
   fetch URL in the scoped sources; it is identified by
   hash/size/rows/first-row id (§2). This no longer blocks public
   reproduction of `docs-10m.jsonl`: the deterministic bundle (§2,
   first path) carries the exact bytes with full attribution (§5).
   The upstream recipe remains as the provenance/audit path.
2. The exact enwiki dump date/URL behind the delta chunks is unrecorded
   in the scoped sources; per-row CC BY-SA attribution travels with the
   bundled and reconstructed texts (§5).
