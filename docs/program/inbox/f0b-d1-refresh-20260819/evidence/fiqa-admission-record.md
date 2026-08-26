# Dataset Admission Record: beir-fiqa

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/fiqa.zip` |
| Publisher/maintainer | UKP Lab, TU Darmstadt / Maia et al. (Financial Opinion Mining and Question Answering) |
| Dataset version/release/commit | BEIR v1.0.0 (FiQA 2018) |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | CC BY-SA 3.0. Permitted for research and benchmarking. |
| Redistribution / retention constraint | ShareAlike license; external staging only. |
| Contact / issue tracker | `https://github.com/beir-cellar/beir` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `direct_lookup` / `semantic` (financial question answering).
- **Evidence unit:** Financial web forum posts and news paragraphs.
- **Gold/judgment source and license:** Relevance judgments in `qrels/test.tsv`.
- **Trace-Lite / Trace relevance:** Medium-scale corpus (~57K passages) testing retrieval precision in an information-dense domain.
- **Why this is a real-world workload:** Tests financial and economic reasoning queries where subtle contextual cues determine relevance.
- **Known mismatch with target product:** Financial discussion forum format rather than structured markdown specs.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `fiqa.zip` (`corpus.jsonl`, `queries.jsonl`, `qrels/test.tsv`) | BEIR v1.0.0 | unset until download | planned |
| Query pack | `queries.jsonl` (648 test queries) | `qrels/test.tsv` split | unset until download | planned |
| Judgments/evidence mapping | `qrels/test.tsv` | Binary qrels | unset until download | planned |
| Transform output | Atomized `IndexedDocument` collection | `BeirAdapter.export_manifest` | unset until staging | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/fiqa/1.0.0/`
- **Network/source authority:** Explicit HTTP GET from `public.ukp.informatik.tu-darmstadt.de`. Strict TLS required.
- **Expected layout and size:** Compressed zip ~12 MB; uncompressed ~45 MB (57,638 corpus docs, 648 test queries).
- **Fetch procedure:** `download_file` with strict TLS verification (`verify=True`) followed by SHA-256 verification.
- **Verification:** Compute SHA-256 of downloaded zip; verify line counts and JSONL schema.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | UKP Darmstadt authoritative repository | PASS |
| License acceptable | CC BY-SA 3.0 | PASS |
| Reproducible acquisition | Deterministic HTTP zip endpoint | PASS |
| Query/evidence mapping adequate | Standard BEIR qrels format | PASS |
| Capability coverage useful | Dense domain terminology retrieval | PASS |
| Privacy/security reviewed | Public financial QA corpus | PASS |

**Recommendation:** **Propose P-001 admission** for public domain generalization lane.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
