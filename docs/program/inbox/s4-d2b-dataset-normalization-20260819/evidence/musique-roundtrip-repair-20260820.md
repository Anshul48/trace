# MuSiQue Round-Trip Repair Evidence

## Disposition

The interrupted reviewer finding is **reproduced and repaired**. The original
candidate and all earlier replay roots remain unchanged and retained. A new
versioned output and a separate clean replay were produced under the leased
normalization/verification roots. This is owner-side repair evidence only; it
does not supply the missing named independent D2b receipt.

## Reproduction from retained artifacts

The old candidate, the retained owner replay, and the retained replay named
`independent-replay-20260820` all had the same MuSiQue corpus hash
`371cff5cea0f2daa981e3da6d406389e2010978661bbfac48f3969532df7351c` and the
same round-trip sample hash
`6e73ee8416baed8e4fe2bf5db728dc63b67db61ad5882815115e6dbbc27b3b3c`.
All five samples disagreed with the content hash of their referenced corpus
segment. Four old samples were hashes of paragraph text alone; the fifth also
selected paragraph index 10 while its recorded judgment was paragraph index 5.

| Judgment | Old sample hash | Referenced old corpus hash | Corrected sample hash |
| --- | --- | --- | --- |
| `dev:2hop__460946_294723:paragraph:5` | `ab609ad0a979ddef9d66b614342fd1f212d893694bfb84717bae60468ea38d97` | `eaedf3a4cc72c680f37b3eefaab40af71ccf2ed08568b356d021a52bc5c3e687` | `eaedf3a4cc72c680f37b3eefaab40af71ccf2ed08568b356d021a52bc5c3e687` |
| `dev:2hop__252311_366220:paragraph:6` | `7beff28892b4e9be08e689235ac181eba8043ef64434c2ae6a30bf4700fa1a05` | `9c50c3ff849332d1d04fdf1c19a4adf93ba7d693c51e436eb21173b65e31e0fe` | `9c50c3ff849332d1d04fdf1c19a4adf93ba7d693c51e436eb21173b65e31e0fe` |
| `dev:2hop__701895_752697:paragraph:3` | `7ed57af8af832738f842f8d0b3e730c671d9bbf02f04b972453b26416e5f7eb1` | `aef79c1633a74ce73f8b7b0c5f6acd03aa876eeb1c6248fd115d9d18dd8db782` | `aef79c1633a74ce73f8b7b0c5f6acd03aa876eeb1c6248fd115d9d18dd8db782` |
| `dev:2hop__259228_793698:paragraph:11` | `8c18f0be5bf2cddbcc3af7ad5ad2dc45850491d3a3078d3991042c29eabe5dbf` | `60c3056063a8fb1098c1400160102ab5898c396eea527be8d854bd7d41998ead` | `60c3056063a8fb1098c1400160102ab5898c396eea527be8d854bd7d41998ead` |
| `dev:2hop__481349_302087:paragraph:5` | `07122f79614e5d2ff087b717aab2c34d7c9a9e1e911ef9650af4da2ed4f1de9a` | `b3b9ff6cca345811f5997dc01bfe9cb91854f96d08fc5fa63c2379f7c25ef7e2` | `a3208606dc5dd2c54d38f78d1890973395f9c7bf419a8649b5f7dd860ae34d0f` |

The responsible packet-local defect was in `build_musique`: the sample used a
paragraph-only hash and selected the first segment by lexical segment-ID order.
The repair selects the first source supporting paragraph and uses that
segment's already-recorded corpus content hash (`title + LF + text`).

## Corrected artifacts and exact identities

- Original normalizer, preserved as the prior provenance: SHA-256
  `0000893590ab24bb64a62879047c0a34e1c74d13ba4806cec135b1f08523bd05`.
- Corrected packet-local normalizer:
  `evidence/normalize_d2b.py`, SHA-256
  `f43bd2ab7916c32e39c50b300b798048392d3ba64a4f877f63b7ef707de0f264`.
- Preserved original candidate:
  `C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819`
  with unchanged `checksums.json` SHA-256
  `4c150a7827836c0ec41e02c302720d84ab0e83e859bf24c884a7bafc52907f5d`,
  `run-manifest.json` SHA-256
  `d7401a9624bef59b47c7985248215406175477c7f7b9c4a16970cc1b52a3fd39`, and
  `COMPLETED.json` SHA-256
  `c2d2081ce8bc475a93616975bd2b38281eb746ad9d3a9ab8e41020491d528998`.
- Corrected output:
  `C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819\repair-mq-roundtrip-20260820`
  with 134 checksum-listed files / 4,775,896,122 bytes; `checksums.json`
  SHA-256 `5d4241626cf34d510126c17a27fac8d1f82adc282dbe09c6c70cc93edcdaa559`,
  `run-manifest.json` SHA-256
  `5ae0fbecffcb1f6a2fcc5b74f647cf8dbbc10ab86f616fdba88af7c6b3039806`, and
  `COMPLETED.json` SHA-256
  `7c4e8ee8a5e2bd48256523dbe7740d837fa6af2e9621a75c3835b4f0546ec60f`.
  Its MuSiQue `round-trip-samples.json` SHA-256 is
  `c71cb883636407bc774da147a3cdc394041657e35afbb5f9d04df4b6464ae65b`.
- Clean replay:
  `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\repair-mq-roundtrip-replay-20260820`
  has the same 134-entry checksum map and the same three root-marker hashes.
- Owner verifier receipt:
  `C:\Users\anshu\AppData\Local\trace-bench-data\verification\d2b-20260819\owner-review-mq-repair-20260820.json`,
  SHA-256 `62dc24e7d76ffc0a57a0b1d80b0a8571296d44a5c1969255b74d0b44ce9e00bd`,
  status `pass`, raw failures `0`, output failures `0`.

## Verification result and boundary

The corrected MuSiQue sample-to-segment check is `5/5` matches and
`0` mismatches. The corrected output has 22,355 queries, 53,017 judgments,
22,355 cases, 101,962 corpus records, and 84,459 source-document identity
records; its evaluation label remains
`evaluation_ready_source_segment_level_atom_mapping_deferred`.

The repair proves only deterministic owner-side normalization integrity and
round-trip consistency for the corrected artifacts. It does not establish
independent certification, atom identity, retrieval quality, release
readiness, or P-005 acceptance. The packet therefore remains `needs_review`
until the named independent D2b reviewer issues a receipt and the other listed
gates are resolved.
