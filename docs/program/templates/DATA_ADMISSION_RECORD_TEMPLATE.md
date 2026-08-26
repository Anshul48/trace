# Dataset Admission Record: <dataset-id>

> **State:** candidate | documented | proposed-for-admission | admitted |
> staged | frozen-for-run | rejected
>
> **Decision authority:** P-001. This record does not authorize download, use,
> or certification by itself.

## 1. Identity and source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | <...> |
| Publisher/maintainer | <...> |
| Dataset version/release/commit | <...> |
| Retrieval date / archive timestamp | <...> |
| License and permitted use | <exact license and analysis> |
| Redistribution / retention constraint | <...> |
| Contact / issue tracker | <...> |

## 2. Intended program role

- Query/retrieval capability classes: <direct, semantic, multi-hop, temporal>.
- Evidence unit: <document, section, atom, entity relation>.
- Gold/judgment source and license: <...>.
- Trace-Lite / Trace relevance: <...>.
- Why this is a real-world workload: <...>.
- Known mismatch with target product: <...>.

## 3. Provenance and integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | <...> | <...> | unset until download | planned |
| Query pack | <...> | <...> | <...> | planned |
| Judgments/evidence mapping | <...> | <...> | <...> | planned |
| Transform output | <...> | transform manifest | <...> | planned |

Do not invent an expected checksum. If a publisher supplies none, record the
acquired artifact digest plus immutable source version separately.

## 4. Staging plan

- Authorized packet: <D2 packet ID or none>.
- Non-Git staging root: <approved external path>.
- Network/source authority: <explicit authorization>.
- Expected layout and size: <...>.
- Fetch procedure: <not executed>.
- Verification: <checksum, signature, layout, license receipt>.
- Transform/segmentation code digest: <...>.
- Source-to-atom and query-to-evidence mapping: <...>.
- Retention/deletion policy: <...>.

If acquisition fails, license is unclear, checksum/layout differs, or judgments
cannot map to frozen evidence IDs, record failure and stop. Never substitute
mock, synthetic, or close-enough data.

## 5. Admission recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | <...> | pending |
| License acceptable | <...> | pending |
| Reproducible acquisition | <...> | pending |
| Query/evidence mapping adequate | <...> | pending |
| Capability coverage useful | <...> | pending |
| Privacy/security reviewed | <...> | pending |

**Recommendation:** defer | propose P-001 admission | reject.

## 6. Claim boundary

This record documents candidate/admitted data. It does not prove retrieval
quality, scale behavior, organization quality, or certification.
