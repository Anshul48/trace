# Dataset Admission Record: mteb-scifact

> **State:** proposed-for-admission (subordinate to BEIR SciFact)
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://huggingface.co/datasets/mteb/scifact` / HuggingFace MTEB |
| Publisher/maintainer | Massive Text Embedding Benchmark (MTEB) Consortium (Muennighoff et al.) |
| Dataset version/release/commit | MTEB Benchmark Release v1.0 |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | CC BY-NC 4.0 / Apache-2.0. Permitted for non-commercial research & embedding evaluation. |
| Redistribution / retention constraint | External staging cache only. |
| Contact / issue tracker | `https://github.com/embeddings-benchmark/mteb` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** Raw bi-encoder embedding layer validation (dense baseline comparison).
- **Evidence unit:** Scientific abstract sentences.
- **Gold/judgment source and license:** MTEB standard qrels.
- **Trace-Lite / Trace relevance:** Validates embedding model performance (`all-MiniLM-L6-v2`, `bge-large-en-v1.5`) independently of hierarchical tree or graph structures.
- **Why this is a real-world workload:** Standardized baseline calibration.
- **Known mismatch with target product:** Redundant with BEIR SciFact; currently represented in `MtebAdapter` by a 2-doc synthetic sample.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | HuggingFace Parquet / JSON | Pinned HF commit | unset | planned |
| Query pack | `queries.jsonl` | Standard test split | unset | planned |
| Judgments/evidence mapping | MTEB qrels | Binary qrels | unset | planned |
| Transform output | Atomized `IndexedDocument` collection | `MtebAdapter.export_manifest` | unset | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/mteb_scifact/`
- **Fetch procedure:** Fetch via HuggingFace datasets library; verify checksums. Remove synthetic fallback from adapter.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Official MTEB repository | PASS |
| License acceptable | CC BY-NC 4.0 / Apache-2.0 | PASS |
| Reproducible acquisition | Pinned HuggingFace release | PASS |
| Query/evidence mapping adequate | MTEB standard format | PASS |
| Capability coverage useful | Embedding layer baseline calibration | PASS |
| Privacy/security reviewed | Public scientific claims | PASS |

**Recommendation:** **Propose P-001 admission** (subsumed under or paired with BEIR SciFact). Prohibit synthetic sample fallback.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
