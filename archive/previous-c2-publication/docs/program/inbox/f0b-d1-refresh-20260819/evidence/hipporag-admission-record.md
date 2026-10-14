# Dataset Admission Record: hipporag-musique

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://github.com/OSU-NLP-Group/HippoRAG` / HuggingFace `MuSiQue` |
| Publisher/maintainer | OSU NLP Group (Bernal et al., HippoRAG 2, 2024) / Trivedi et al. (MuSiQue, 2022) |
| Dataset version/release/commit | HippoRAG v2 Release (MuSiQue 2-4 hop subset) |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | CC BY 4.0 (MuSiQue) / Apache-2.0 (HippoRAG). Permitted for open research & evaluation. |
| Redistribution / retention constraint | Attribution required; external staging cache only. |
| Contact / issue tracker | `https://github.com/OSU-NLP-Group/HippoRAG/issues` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `multi_hop` / associative knowledge graph traversal (Personalized PageRank vs. LATTICE).
- **Evidence unit:** Multi-hop reasoning paragraphs with disconnected entity links.
- **Gold/judgment source and license:** Gold reasoning chains annotated by human experts.
- **Trace-Lite / Trace relevance:** Direct comparative benchmark for graph/associative retrieval mechanisms.
- **Why this is a real-world workload:** Tests whether associative graph retrieval outperforms dense embeddings on multi-step reasoning.
- **Known mismatch with target product:** General knowledge entities rather than codebase components.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `dataset.json` (MuSiQue full multi-hop split) | Pinned GitHub/HF commit | unset | planned |
| Query pack | `queries.json` (1,000+ multi-hop questions) | MuSiQue test/dev split | unset | planned |
| Judgments/evidence mapping | `gold_paragraphs` | Paragraph-level entity links | unset | planned |
| Transform output | Atomized `IndexedDocument` collection | `HippoRagAdapter.export_manifest` | unset | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/hipporag_musique/`
- **Network/source authority:** Explicit HTTPS fetch of full MuSiQue split from official OSU NLP repository.
- **Expected layout and size:** ~25 MB JSON (approx. 20,000 paragraphs, 1,000 queries).
- **Fetch procedure:** Fetch complete dataset; verify SHA-256 digest. Remove 2-question synthetic sample fallback.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Official OSU NLP / MuSiQue repository | PASS |
| License acceptable | CC BY 4.0 / Apache-2.0 | PASS |
| Reproducible acquisition | Pinned GitHub / HuggingFace release | PASS |
| Query/evidence mapping adequate | Detailed gold paragraph chains | PASS |
| Capability coverage useful | Essential for comparative graph evaluation | PASS |
| Privacy/security reviewed | Public Wikipedia entities (zero PII) | PASS |

**Recommendation:** **Propose P-001 admission** for MuSiQue multi-hop graph evaluation lane. Prohibit synthetic sample fallback.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
