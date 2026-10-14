# Data licences — docs-10m.jsonl (dataset-specific terms)

These terms govern the **corpus texts** in `docs-10m.jsonl(.gz)`.
They are distinct from any repository code licence; no blanket
Apache-2.0 grant extends over third-party texts. No new grants are
invented here.

1. **English Wikipedia text (2605 rows): CC BY-SA 4.0.**
   Attribute per article URL/history (see `ATTRIBUTION.md`) under
   Wikimedia Terms of Use §7
   (<https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use>).
   Share adaptations under the same licence.

2. **SciFact `corpus.jsonl` abstracts (486 rows): ODC-By 1.0**
   (<https://opendatacommons.org/licenses/by/1-0/>),
   via S2ORC. Provide attribution to SciFact / S2ORC as in
   `ATTRIBUTION.md`. Source licence record:
   <https://raw.githubusercontent.com/allenai/scifact/master/LICENSE.md>
   Distinct terms in that record (not this asset's rows):
   `claims_*.jsonl` CC-BY-4.0, code Apache-2.0.

3. **Project curated fixture (8 `para-*` rows): Apache-2.0**
   (`trace_engineering_curated.json` v1.0.0).

4. **Freeze/build metadata** (`corpus-manifest-10m.json`,
   `derivation.json`, `prefix-doc-ranges.json`, `relations-10m.json`,
   preflight/report): project-authored; see the release tree's own
   data README for its terms.

Genuine restrictions: CC BY-SA share-alike on Wikipedia rows and
ODC-By attribution on SciFact rows travel with redistribution; keep
`ATTRIBUTION.md` + this file alongside the asset. No additional
non-commercial restriction is asserted (see downstream-label note in
`ATTRIBUTION.md`). No credentials, personal data, or operational logs
are included.
