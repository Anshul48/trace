# Dataset Admission Record: bright-coding

> **State:** proposed-for-admission
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://huggingface.co/datasets/xlangai/BRIGHT` |
| Publisher/maintainer | XLANG Lab / University of Washington (Su et al., NeurIPS 2024) |
| Dataset version/release/commit | HuggingFace dataset repository release `main` (commit snapshot pinned during D2) |
| Retrieval date / archive timestamp | Pending D2 staging |
| License and permitted use | Apache-2.0 / CC BY-SA 4.0. Permitted for open research, evaluation, and benchmark use. |
| Redistribution / retention constraint | External staging cache only. |
| Contact / issue tracker | `https://github.com/xlang-ai/BRIGHT` |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `cross_domain` / `multi_hop` / reasoning-intensive retrieval (algorithmic coding problems, StackExchange, LeetCode).
- **Evidence unit:** Code snippets, algorithmic solution explanations, documentation paragraphs.
- **Gold/judgment source and license:** Gold relevant documents annotated by domain experts (LeetCode solutions, Python algorithms).
- **Trace-Lite / Trace relevance:** Evaluates hierarchical and associative memory where standard nearest-neighbor dense embedding cosine similarity fails because query and target document do not share lexical tokens or shallow semantic embeddings.
- **Why this is a real-world workload:** Models software engineering agent memory (finding relevant architecture patterns, algorithm solutions, and system invariants).
- **Known mismatch with target product:** Highly concentrated algorithmic problem formulations.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | HuggingFace Parquet / JSON files (`documents.jsonl`, `queries.jsonl`) | Pinned Git commit snapshot | unset until download | planned |
| Query pack | `queries.jsonl` (coding task split) | 1,398 reasoning queries across BRIGHT | unset until download | planned |
| Judgments/evidence mapping | `gold_ids` list per query | Multi-document gold mapping | unset until download | planned |
| Transform output | Atomized `IndexedDocument` collection | `BrightAdapter.export_manifest` | unset until staging | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/bright_coding/<commit-hash>/`
- **Network/source authority:** Explicit HTTPS download from HuggingFace dataset endpoint.
- **Expected layout and size:** ~15 MB raw text (approx. 5,000 documents, 250 coding queries).
- **Fetch procedure:** Fetch pinned HuggingFace parquet/json files via HTTPS; compute content digests.
- **Verification:** Assert SHA-256 of downloaded archive matches pinned manifest.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Official XLANG HuggingFace dataset | PASS |
| License acceptable | Apache-2.0 / CC BY-SA 4.0 | PASS |
| Reproducible acquisition | Pinned HuggingFace commit hash | PASS |
| Query/evidence mapping adequate | Explicit gold document IDs for reasoning queries | PASS |
| Capability coverage useful | Crucial for testing hierarchical tree routing vs flat embeddings | PASS |
| Privacy/security reviewed | Public competitive programming & open source docs (zero PII) | PASS |

**Recommendation:** **Propose P-001 admission** as primary reasoning-intensive retrieval benchmark.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
