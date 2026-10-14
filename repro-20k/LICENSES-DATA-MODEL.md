# Data and model licences — repro-20k assets

No blanket licence is asserted over third-party material. Keep this file
with `small-prefix-20k.tar.gz` / `data-20k/` on any redistribution.

## Documents in the 20k export (88 rows, inspected from exact bytes)

All 88 documents in the committed small prefix have numeric `doc_id`s
(`4983` … `461550`) — SciFact `corpus.jsonl` abstracts (S2ORC texts),
**not** claim annotations. No Wikipedia rows and no project-curated rows
fall inside this particular prefix.

- **SciFact abstracts: ODC-By 1.0** (attribution required).
  Source licence record: <https://raw.githubusercontent.com/allenai/scifact/master/LICENSE.md>
  Terms: <https://opendatacommons.org/licenses/by/1-0/>
  Distinct terms in that record (not present in this export):
  `claims_*.jsonl` annotations CC-BY-4.0; SciFact code Apache-2.0.
  Cite: Wadden et al., *Fact or Fiction: Verifying Scientific Claims*
  (SciFact), EMNLP 2020; abstracts via S2ORC (Lo et al., 2020).
  Downstream mirrors label these abstracts differently (e.g. BEIR
  HuggingFace card CC-BY-SA-4.0); the original allenai record above is
  the governing one relied on here. No non-commercial restriction is
  asserted beyond that record.

## The full corpus this prefix is taken from (not redistributed here)

`docs-100m.jsonl` (30,927 rows) additionally contains English Wikipedia
text (**CC BY-SA 4.0**, attribute per article URL/history under Wikimedia
Terms of Use §7, share adaptations alike) and 8 project-curated `para-*`
rows (**Apache-2.0**, `trace_engineering_curated.json` v1.0.0). Any larger
prefix exported with `prep_small_prefix.py --tokens N` must be re-inspected
row-family by row-family and carry the corresponding terms; the script
does not change any document bytes.

## Embedding model (vectors in `emb_cache/`)

Per the verbatim `emb_cache/meta.json` (`config_id 25989b870b5ccfee`):
`sentence-transformers/all-MiniLM-L6-v2`, revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, mean pooling, fp32,
unnormalized, produced with sentence-transformers 2.7.0 / torch
2.14.0+cu130 on an NVIDIA GeForce RTX 5050 Laptop GPU.
The upstream model is distributed by its authors under **Apache-2.0**
(model card: <https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2>).
Only derived FP32 vectors for the 144 chunks of this prefix are included;
no model weights are redistributed here.

## Project-authored material

`prep_small_prefix.py`, `README.md`, `PROTOCOL.md`, `MANIFEST.json`, the
exporter's repacking (renumbered index rows), and the local pilot outputs
are project-authored and follow the repository's Apache-2.0 terms.
Receipts under `../receipts/` are project records quoted by hash in `MANIFEST.json`.
