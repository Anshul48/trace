# Attribution — docs-10m.jsonl (C2-10M freeze-v2 input)

Asset: `docs-10m.jsonl.gz` → `docs-10m.jsonl`
(3099 rows, 64291035 B,
SHA256 `04bbbb3ea3425a49491559173b20280fb286edeeef49c8293aebc0b92bcce3fd`).
Each row: `{"doc_id": ..., "text": ...}`; `text` opens with the source
title line. Row mix inspected from exact bytes:

- `wikipedia:*` — 2605 rows (1934 plain titles, 671 `wikipedia/<slug>` titles)
- numeric (SciFact abstracts) — 486 rows
- `para-*` (project curated) — 8 rows

## Wikipedia (2605 rows) — CC BY-SA 4.0

Per-row title metadata is preserved as the first line of `text`.
Article URL: strip a leading `wikipedia/` if present, replace spaces with
underscores, URL-encode, prefix `https://en.wikipedia.org/wiki/`.
History: append `?action=history` via
`https://en.wikipedia.org/w/index.php?title=<Title>&action=history`.

Examples observed in this file:

- `Tower of London` → <https://en.wikipedia.org/wiki/Tower_of_London>
- `Stockholm University` → <https://en.wikipedia.org/wiki/Stockholm_University>
- `Audi` → <https://en.wikipedia.org/wiki/Audi>
- `146 BC` → <https://en.wikipedia.org/wiki/146_BC>
- `wikipedia/Hong_(rainbow-dragon)` → <https://en.wikipedia.org/wiki/Hong_(rainbow-dragon)>
- `wikipedia/List_of_Nepalese_films_of_2016` → <https://en.wikipedia.org/wiki/List_of_Nepalese_films_of_2016>

Python:

```python
from urllib.parse import quote
def wiki_url(first_line):
    t = first_line.removeprefix("wikipedia/").replace(" ", "_")
    return "https://en.wikipedia.org/wiki/" + quote(t, safe="()_,:;@!$&'*+-./")
```

Attribution per Wikimedia Terms of Use §7
(<https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use>):
link each reused article (or its history) as above; share adaptations
under the same licence. Underlying enwiki dump date/URL is unrecorded in
the freeze sources, so per-row title links are the attribution carrier.
No endorsement by Wikipedia editors is claimed.

## SciFact abstracts (486 rows) — ODC-By 1.0

Numeric `doc_id`s with biomedical paper-title first lines, e.g.
`9784254` / `LXR-Dependent Gene Expression Is Important for Macrophage
Survival and the Innate Immune Response`.
These are `corpus.jsonl` abstracts (S2ORC texts), **not** claim annotations.

- Licence: **ODC-By 1.0** for abstracts.
- Different files, different terms (not in this asset):
  `claims_*.jsonl` annotations CC-BY-4.0, code Apache-2.0.
- Source record (verified 2026-10-14):
  <https://raw.githubusercontent.com/allenai/scifact/master/LICENSE.md>
- Cite: Wadden et al., SciFact, EMNLP 2020 (findings); abstracts via
  S2ORC; BeIR-format distribution per Thakur et al., BEIR, NeurIPS 2021.
- Downstream label differences (recorded, not adopted as governing):
  BeIR HuggingFace mirror card says CC-BY-SA-4.0; trace-bench
  `catalog.json` says "CC BY-NC 4.0 (SciFact) / Apache 2.0 (BEIR
  Benchmark)". The original allenai record above governs the abstracts.
  No non-commercial restriction is asserted beyond that record.

## Project curated (8 rows) — Apache-2.0

`para-0, para-3, para-12, para-16, para-25, para-41, para-68, para-69`
from `trace_engineering_curated.json` v1.0.0
("Generated 320-query technical regression fixture; not an independently
reviewed quality benchmark"). Single-sentence Raft/systems statements,
e.g. `para-0` / `Consensus Protocol: Raft leader election occurs …`.
Licence: Apache-2.0 fixture. Upstream SHA
`210a20a4…` (182169 B), vendored in `c10m/data/upstream/`.

## Changes / derivation notice

- Parent: `docs-100m.jsonl` (30927 rows, 622471790 B,
  `c098fdac…`) assembled from SciFact corpus + curated fixture +
  `wikipedia_delta.jsonl` prefix per `selection_formula`
  (`c10m/data/inputs/preflight-100m.json`).
- This file: 3099-row slice via `derivation.json` 0-based parent
  ordinals 12..30919, **non-contiguous** (contiguous-prefix hypothesis
  tested and refuted). Every slice row is byte-identical
  (`doc_id` + `text` SHA) to its mapped parent row
  (`corpus-manifest-10m.json`).
- Packaging: title-headed `text` (`(title + "\n" + body).strip()` form),
  JSONL `{"doc_id","text"}` only. No text edits, no reordering beyond the
  recorded slice order. Chunker/tokenizer (`TOK-v1`, 200/50) in the
  manifest describe downstream ingestion, not this file's bytes.
- Producer mode `10m` consumes this file only; it does not require the
  machine-local 1.4 GB delta or the 100M parent at build time.
