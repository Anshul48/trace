# Dataset Admission Record: beir-nfcorpus

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip` |
| Publisher/maintainer | UKP Lab, TU Darmstadt / Bendersky et al. (NutritionFacts.org dataset) |
| Dataset version/release/commit | BEIR v1.0.0 |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | CC BY-SA 4.0. Permitted for academic, research, and benchmarking use with attribution. |
| Redistribution / retention constraint | ShareAlike license; external staging only. |
| Contact / issue tracker | `https://github.com/beir-cellar/beir` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `direct_lookup` / `semantic` (medical and dietary claim matching).
- **Evidence unit:** Nutrition and biomedical article abstracts.
- **Gold/judgment source and license:** Graded relevance judgments (0, 1, 2) in `qrels/test.tsv`.
- **Trace-Lite / Trace relevance:** Tests domain vocabulary mismatch (layperson natural language query vs. medical document text).
- **Why this is a real-world workload:** Tests natural language retrieval where user queries do not share exact keywords with technical source atoms.
- **Known mismatch with target product:** Medical focus rather than developer/systems engineering.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `nfcorpus.zip` (`corpus.jsonl`, `queries.jsonl`, `qrels/test.tsv`) | BEIR v1.0.0 | unset until download | planned |
| Query pack | `queries.jsonl` (323 test queries) | `qrels/test.tsv` split | unset until download | planned |
| Judgments/evidence mapping | `qrels/test.tsv` | Graded qrels (1-2) | unset until download | planned |
| Transform output | Atomized `IndexedDocument` collection | `BeirAdapter.export_manifest` | unset until staging | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/nfcorpus/1.0.0/`
- **Network/source authority:** Explicit HTTP GET from `public.ukp.informatik.tu-darmstadt.de`. Strict TLS required.
- **Expected layout and size:** Compressed zip ~1.8 MB; uncompressed ~8 MB (3,633 corpus docs, 323 test queries).
- **Fetch procedure:** `download_file` with strict TLS verification (`verify=True`) followed by SHA-256 verification.
- **Verification:** Compute SHA-256 of downloaded zip; verify line counts and JSONL schema.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | UKP Darmstadt authoritative repository | PASS |
| License acceptable | CC BY-SA 4.0 (attribution and sharealike) | PASS |
| Reproducible acquisition | Deterministic HTTP zip endpoint | PASS |
| Query/evidence mapping adequate | Standard BEIR graded qrels format | PASS |
| Capability coverage useful | Non-exact keyword semantic retrieval | PASS |
| Privacy/security reviewed | Public biomedical summaries (zero PII) | PASS |

**Recommendation:** **Propose P-001 admission** for public domain generalization lane.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
