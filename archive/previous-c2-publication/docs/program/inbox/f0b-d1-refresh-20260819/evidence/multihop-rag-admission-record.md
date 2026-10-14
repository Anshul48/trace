# Dataset Admission Record: multihop-rag

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://github.com/yixuantt/MultiHop-RAG` / HuggingFace `yixuantt/MultiHop-RAG` |
| Publisher/maintainer | Tang et al. (MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries) |
| Dataset version/release/commit | Release v1.0 (2024) |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | Apache-2.0. Permitted for academic and commercial benchmarking. |
| Redistribution / retention constraint | External staging cache only. |
| Contact / issue tracker | `https://github.com/yixuantt/MultiHop-RAG/issues` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `multi_hop` (2-hop, 3-hop, and 4-hop multi-document inference queries, plus null queries for abstention testing).
- **Evidence unit:** News and Wikipedia articles across multiple domains.
- **Gold/judgment source and license:** Gold evidence lists linking query to 2 to 4 supporting document IDs with explicit reasoning chains.
- **Trace-Lite / Trace relevance:** Evaluates whether graph activation (LATTICE / PPR / Co-occurrence) and hierarchical navigation successfully recover ALL hops needed to answer a multi-step query.
- **Why this is a real-world workload:** Core capability for autonomous agent memory where facts are scattered across different meetings, files, and events.
- **Known mismatch with target product:** News articles rather than codebase ASTs.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `MultiHopRAG.json` (2,556 queries, 10,000+ corpus passages) | v1.0 GitHub release tag | unset until download | planned |
| Query pack | `queries.json` (categorized by hop count: 2, 3, 4 hops and null queries) | Explicit hop metadata | unset until download | planned |
| Judgments/evidence mapping | `evidence_doc_ids` list per query | Multi-document gold mapping | unset until download | planned |
| Transform output | Atomized `IndexedDocument` collection | `MultiHopAdapter.export_manifest` | unset until staging | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/multihop_rag/v1.0/`
- **Network/source authority:** Explicit HTTPS fetch from official GitHub raw / HuggingFace repository.
- **Expected layout and size:** JSON file ~20 MB (2,556 queries, ~10,000 documents).
- **Fetch procedure:** Download pinned release tag via HTTPS; verify SHA-256 hash.
- **Verification:** Compute SHA-256; verify that all `evidence_doc_ids` exist in the loaded corpus.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Official GitHub / HuggingFace release | PASS |
| License acceptable | Apache-2.0 | PASS |
| Reproducible acquisition | Pinned GitHub tag / commit | PASS |
| Query/evidence mapping adequate | Explicit multi-hop evidence IDs per query | PASS |
| Capability coverage useful | Direct multi-hop coverage benchmark | PASS |
| Privacy/security reviewed | Public news/facts (zero PII) | PASS |

**Recommendation:** **Propose P-001 admission** for multi-hop retrieval evaluation lane.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
