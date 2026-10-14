# Dataset Admission Record: beir-scifact

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip` |
| Publisher/maintainer | UKP Lab, TU Darmstadt (Thakur et al., BEIR benchmark) / Allen Institute for AI (Wadden et al.) |
| Dataset version/release/commit | BEIR v1.0.0 (SciFact release 2020) |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | CC BY-NC 4.0 (for SciFact data) / Apache-2.0 (for BEIR benchmark code). Permitted for non-commercial research & benchmarking. |
| Redistribution / retention constraint | Attribution required; non-commercial distribution. Raw archive stored in external benchmark cache. |
| Contact / issue tracker | `https://github.com/beir-cellar/beir` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `direct_lookup` (verifiable scientific claim retrieval).
- **Evidence unit:** Scientific abstract passages / sentences.
- **Gold/judgment source and license:** Expert biomedical annotator judgments in `qrels/test.tsv`.
- **Trace-Lite / Trace relevance:** Tests precision of dense, lexical, and hybrid search on specialized domain terminology.
- **Why this is a real-world workload:** Models technical literature search where exact evidence atoms must substantiate complex claims.
- **Known mismatch with target product:** Shorter document length than typical multi-page technical RFCs.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `scifact.zip` (containing `corpus.jsonl`, `queries.jsonl`, `qrels/test.tsv`) | BEIR v1.0.0 release | unset until download | planned |
| Query pack | `queries.jsonl` (300 test queries) | `qrels/test.tsv` split | unset until download | planned |
| Judgments/evidence mapping | `qrels/test.tsv` (query_id -> corpus_id relevance scores) | Binary/graded qrels | unset until download | planned |
| Transform output | Atomized `IndexedDocument` collection | `BeirAdapter.export_manifest` | unset until staging | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/scifact/1.0.0/`
- **Network/source authority:** Explicit HTTP GET from `public.ukp.informatik.tu-darmstadt.de`. Strict TLS required.
- **Expected layout and size:** Compressed zip ~2.5 MB; uncompressed ~10 MB (5,183 corpus docs, 300 test queries).
- **Fetch procedure:** `download_file` with strict TLS verification (`verify=True`) followed by SHA-256 checksum verification.
- **Verification:** Compute SHA-256 of downloaded zip; verify line counts and JSONL schema.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | UKP Darmstadt authoritative repository | PASS |
| License acceptable | CC BY-NC 4.0 (research/benchmark use permitted) | PASS (with non-commercial restriction note) |
| Reproducible acquisition | Deterministic HTTP zip endpoint | PASS |
| Query/evidence mapping adequate | Standard BEIR qrels format | PASS |
| Capability coverage useful | Scientific direct lookup verification | PASS |
| Privacy/security reviewed | Public scientific claims (zero PII) | PASS |

**Recommendation:** **Propose P-001 admission** for public non-commercial retrieval certification lane.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
