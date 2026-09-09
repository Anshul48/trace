# H0 1M selection reconciliation (attempt-2 seal-pipeline repair)

Status: `HOLD-UNADOPTED` — evidence for a human ballot, not an adoption.
Machine-readable sibling: `selection_reconciliation.json` (same directory).
Successor selection: `selection_record.json`.
Provisional manifest (UNADOPTED): `provisional_1m_manifest.json`.

Method (all from staged bytes, this session): strict recompute of the
HEAD-recorded ranges with `benchmarks/verify_1m_checksums.py` (9 errors);
pre-reseal forensic recompute with the same tool under
`--forensic-overrides '{"bright_delta": "[0, 928750)", "wikipedia_delta": "[0, 96639)"}'`
(all 9 claim fields match); atomic seal of the successor selection with
`scripts/seal_1m_manifest.py` (published provisional, rc=0); second-path
check of that provisional with `benchmarks/verify_1m_independent.py`
(INDEPENDENT-PASS, rc=0). All 8 staged files hash-match their fingerprints,
so the defect is in recorded selection fields, not in staged bytes.

## 1. Per-shard reconciliation

Columns: (i) `d14f1a2` original seal, (ii) HEAD current record, (iii) strict
recompute from staged bytes using the HEAD-recorded range. File SHAs are
short (12 hex); paths are short names (full Windows-absolute paths plus full
SHAs live in the JSON sibling and in `selection_record.json`).

| Shard | (i) d14f1a2 range / docs / bytes | (ii) HEAD range / docs / bytes | (iii) strict recompute docs / bytes |
|---|---|---|---|
| musique (base) | [0, 80047) / 80047 / 37343384 | identical | 80047 / 37343384 match |
| beir-fiqa (base) | [0, 10575) / 10575 / 8141714 | identical | 10575 / 8141714 match |
| beir-scifact (base) | [0, 5183) / 5178 / 7777523 | identical | 5178 / 7777523 match |
| beir-nfcorpus (base) | [0, 3633) / 3591 / 5718118 | identical | 3591 / 5718118 match |
| multihop-rag (base) | [0, 609) / 609 / 6414182 | identical | 609 / 6414182 match |
| musique_delta | [80047, 101962) / 21915 / 10138960 | identical | 21915 / 10138960 match |
| beir-fiqa_delta | [10575, 57600) / 47015 / 36130851 | identical | 47015 / 36130851 match |
| bright_delta | [0, 684431) / 684431 / 678354057 | [0, 643710) / 643710 / 678354057 (same file `…/bright/corpus.jsonl`, sha `0ac9088e4dca`) | [0, 643710) -> 618306 / 603263678 DIFFER |
| enron_delta | [0, 50000) / 50000 / 124668874 | identical | 50000 / 124668874 match |
| wikipedia_delta | [0, 96639) / 96639 / 1099778081 (file sha `a5acb6a96d32`) | [0, 137360) / 137360 / 1425430486 (DIFFERENT file, sha `ffe485442095`) | [0, 137360) -> 137360 / 1361116951 count matches, bytes DIFFER |

Totals and roots:

| Field | Claim (both generations, carried over) | Strict recompute (HEAD ranges) |
|---|---|---|
| docs | 100000 + 900000 = 1000000 | 100000 + 874596 = 974596 DIFFER |
| bytes | 65394921 + 1949070823 = 2014465744 | 65394921 + 2135319314 = 2200714235 DIFFER |
| base root | `23b99dfe…2e57e6e5b` | match |
| delta root | `9385407a…10dc30` | `f14b18b9…38c31477` DIFFER |
| union root | `5039acef…f7a79a5f5` | `88768eac…a4ebca17f7cff1` DIFFER |

## 2. What the reseal did (12-line diff, `d14f1a2` -> `34a0df1`)

- `bright_delta`: count/range rewritten 684431 -> 643710 while claimed
  bytes stayed 678354057 and the staged file (same SHA) stayed untouched.
  The staging code iterates the whole bright file (928750 lines, no index
  slice) and deduplicates to 684431, so neither recorded range reproduces
  the claim; the full-file iteration does.
- `wikipedia_delta`: range/count/bytes rewritten and a different staged
  file pinned. The new byte figure 1425430486 equals the new file's
  on-disk size (`stat().st_size`), not the normalized content bytes
  (1361116951) — the reseal script took file size for content bytes, which
  is why the count matches but the bytes and both roots do not.
- Delta/union roots and all totals were carried over unchanged.

## 3. Verdict

- NO selection matching the HEAD-recorded ranges reproduces
  1M / 2,014,465,744 / `5039acef…` (9 delta-side errors, both root
  mismatches). HEAD-as-recorded is unreproducible: HOLD stands.
- Exactly ONE selection reproducible from staged bytes reproduces all 9
  claim fields (docs, bytes, trio, totals): the pre-reseal selection —
  bright full-file `[0, 928750)` (-> 684431 / 678354057) plus wikipedia
  prefix `[0, 96639)` of the current staged file (-> 96639 /
  1099778081), everything else as recorded. Verified twice this session
  through two independent code paths (producer seal + independent
  checker agree: 1000000 / 2014465744 / `5039acef…`).
- The current wikipedia file's first 96639 lines reproducing the original
  bytes/count/leaves exactly is consistent with an append-only extension
  (96639 + 40721 = 137360 lines), but only the recomputed equality is
  claimed here.

## 4. Successor contract proposal (FOR HUMAN BALLOT — not adopted)

- Selection: `selection_record.json`
  (`H0-1M-SUCCESSOR-SEL-01`, status PROPOSED-UNADOPTED).
- Provisional manifest: `provisional_1m_manifest.json`
  (sha256 `4f4deb50446f8325f676c3ee2618dfc3059eb78b5551e4855aef932bfe3c8c3d`,
  status PROVISIONAL-UNADOPTED, co-signature PENDING_HUMAN_BALLOT,
  signature null; signing binds the complete file bytes at adoption).
- Claims it carries (derived, both paths agree): 100000 + 900000 =
  1000000 docs; 65394921 + 1949070823 = 2014465744 bytes; base
  `23b99dfe…2e57e6e5b`, delta `9385407a…10dc30`, union
  `5039acef…f7a79a5f5`.
- Suggested ballot line for `06_DECISION_LOG.md`: `H0
  H0-1M-CORPUS-CONTRACT successor: <PASS|HOLD|ABORT> — selection
  H0-1M-SUCCESSOR-SEL-01, provisional <sha above>, verifier exits
  <rc>. Signed: <name+date>.`
- Until that ballot passes, P0 stays quarantined: HOLD.
