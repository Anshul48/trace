# Dataset Admission Record: hichunk-benchmark

> **State:** documented (deferred pending official URL resolution)
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://github.com/HiChunk/HiCBench` (Repository to be pinned during D2) |
| Publisher/maintainer | HiChunk Authors (Hierarchical Chunking and Multi-Level Retrieval Benchmark, 2024) |
| Dataset version/release/commit | Release 2024 (unpinned in current adapter) |
| Retrieval date / archive timestamp | Pending source repository verification |
| License and permitted use | Open research license (subject to formal review upon repository pinning). |
| Redistribution / retention constraint | External staging cache only. |
| Contact / issue tracker | Academic authors |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `global_context` / hierarchical document organization / atom boundary evaluation.
- **Evidence unit:** Multi-level hierarchical sections, subsections, and paragraphs.
- **Gold/judgment source and license:** Annotated hierarchical chunk boundaries and multi-level query targets.
- **Trace-Lite / Trace relevance:** Evaluates RAPTOR / LATTICE tree construction against true document section hierarchies.
- **Why this is a real-world workload:** Tests hierarchical summarization and top-down traversal on structured long documents.
- **Known mismatch with target product:** Currently represented by a 4-chunk synthetic fallback in `HiChunkAdapter`.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `corpus.jsonl` (with `hierarchy_level`, `parent_id`), `queries.jsonl` | Pinned git commit | unset | planned |
| Query pack | `queries.jsonl` | Queries targeting sections vs leaves | unset | planned |
| Judgments/evidence mapping | `gold_chunk_ids` | Section/atom IDs | unset | planned |
| Transform output | Atomized `IndexedDocument` collection | `HiChunkAdapter.export_manifest` | unset | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to source resolution and P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/hichunk/`
- **Network/source authority:** Explicit HTTPS git clone / release download.
- **Expected layout and size:** ~5,000 document sections, 500 queries.
- **Fetch procedure:** Download official dataset release; verify checksums. Remove synthetic fallback from adapter.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Missing official endpoint in current adapter (currently synthetic) | **BLOCKED** |
| License acceptable | Requires formal repository license review | PENDING |
| Reproducible acquisition | Requires pinned release archive | PENDING |
| Query/evidence mapping adequate | Multi-level section mapping | PENDING |
| Capability coverage useful | High value for hierarchical index evaluation | PASS |
| Privacy/security reviewed | Public documentation | PASS |

**Recommendation:** **DEFER** admission until the official source repository and license are pinned in a D2 preparation packet. Prohibit synthetic sample in certification mode.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
