# Dataset Admission Record: longmemeval

> **State:** documented (deferred pending source URL resolution)
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://github.com/MemoryAgentBench/LongMemEval` (To be pinned during D2) |
| Publisher/maintainer | LongMemEval / MemoryAgentBench Authors (2024) |
| Dataset version/release/commit | Release 2024 (unpinned in current adapter) |
| Retrieval date / archive timestamp | Pending source repository verification |
| License and permitted use | MIT / Apache-2.0 open source. |
| Redistribution / retention constraint | External staging cache only. |
| Contact / issue tracker | Academic GitHub repository |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `historical` / `contradiction` / temporal update tracking / selective forgetting.
- **Evidence unit:** Multi-session conversation logs and timestamped knowledge updates.
- **Gold/judgment source and license:** Gold target session IDs associated with historical states versus updated states.
- **Trace-Lite / Trace relevance:** Evaluates temporal truth, valid-time query semantics, and contradiction resolution.
- **Why this is a real-world workload:** Autonomous agents require memory that updates beliefs over time while retaining historical records.
- **Known mismatch with target product:** Currently represented by a 2-session synthetic fallback in `LongMemEvalAdapter`.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | `sessions.jsonl` (with timestamps), `eval_questions.jsonl` | Pinned git commit | unset | planned |
| Query pack | `eval_questions.jsonl` (500 temporal questions) | Categorized by task type | unset | planned |
| Judgments/evidence mapping | `gold_session_ids` | Timestamped session IDs | unset | planned |
| Transform output | Atomized `IndexedDocument` collection | `LongMemEvalAdapter.export_manifest` | unset | planned |

## 4. Staging Plan

- **Authorized packet:** D2 (subject to source resolution and P-001 acceptance).
- **Non-Git staging root:** `<benchmark-data-root>/downloads/longmemeval/`
- **Network/source authority:** Explicit HTTPS fetch from pinned repository.
- **Expected layout and size:** ~500 multi-session conversations.
- **Fetch procedure:** Download official dataset release; verify checksums. Remove synthetic fallback from adapter.
- **Retention/deletion policy:** Retained in local offline cache outside Git repository.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | Missing official endpoint in current adapter (currently synthetic) | **BLOCKED** |
| License acceptable | MIT / Apache-2.0 | PASS |
| Reproducible acquisition | Requires pinned release archive | PENDING |
| Query/evidence mapping adequate | Multi-session temporal mapping | PENDING |
| Capability coverage useful | Critical for temporal and contradiction testing | PASS |
| Privacy/security reviewed | Public synthetic/human evaluation conversations | PASS |

**Recommendation:** **DEFER** admission until the official source repository is pinned in D2. Prohibit synthetic sample in certification mode.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
