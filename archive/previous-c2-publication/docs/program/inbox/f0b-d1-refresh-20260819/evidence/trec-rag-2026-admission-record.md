# Dataset Admission Record: trec-rag-2026

> **State:** rejected-for-initial-baseline (deferred to restricted pilot)
> **Decision authority:** P-001. This record does not authorize download, use, or certification by itself.

## 1. Identity and Source

| Field | Value |
| --- | --- |
| Canonical source URL/distribution ID | `https://trec.nist.gov/` / NIST TREC 2026 RAG Track (ClimbMix dataset) |
| Publisher/maintainer | National Institute of Standards and Technology (NIST) / TREC organizers |
| Dataset version/release/commit | TREC 2026 Track Data (ClimbMix segmented collection) |
| Retrieval date / archive timestamp | Pending official track release |
| License and permitted use | Restricted to registered TREC participants under organizational data user agreements. |
| Redistribution / retention constraint | Strict redistribution prohibitions; non-public redistribution. |
| Contact / issue tracker | NIST TREC Program Chairs |

## 2. Intended Program Role

- **Query/retrieval capability classes:** `global_context` / deep segmented narrative retrieval.
- **Evidence unit:** Large-scale segmented narrative collections.
- **Gold/judgment source and license:** NIST assessor pooled relevance judgments.
- **Trace-Lite / Trace relevance:** Large-scale deep retrieval evaluation over long narrative queries.
- **Why this is a real-world workload:** Standardized international evaluation for information retrieval research.
- **Known mismatch with target product:** Data access is legally restricted to TREC participants; currently represented in `TrecRagAdapter` by a 3-document synthetic sample.

## 3. Provenance and Integrity

| Artifact | Expected layout | Version evidence | SHA-256 after acquisition | Status |
| --- | --- | --- | --- | --- |
| Raw distribution | NIST password-protected archive / ClimbMix corpus | NIST signed release | unset | planned |
| Query pack | `queries.jsonl` | TREC track topics | unset | planned |
| Judgments/evidence mapping | NIST qrels | Assessor qrels | unset | planned |
| Transform output | Atomized `IndexedDocument` collection | `TrecRagAdapter.export_manifest` | unset | planned |

## 4. Staging Plan

- **Authorized packet:** Deferred (requires human credential/participant authority).
- **Non-Git staging root:** `<benchmark-data-root>/restricted/trec_rag_2026/`
- **Network/source authority:** Authorized NIST portal download with credentials.
- **Expected layout and size:** 100K+ segments, multi-GB archive.
- **Retention/deletion policy:** Secure offline staging compliant with NIST Data User Agreement.

## 5. Admission Recommendation

| Criterion | Evidence | Result |
| --- | --- | --- |
| Source identity stable | NIST official benchmark | PASS |
| License acceptable | Restricted participant license (not open/public) | **FAIL (Open Access)** |
| Reproducible acquisition | Requires active participant credentials | **FAIL (Autonomous Fetch)** |
| Query/evidence mapping adequate | NIST standard qrels | PASS |
| Capability coverage useful | High-prestige evaluation | PASS |
| Privacy/security reviewed | Restricted terms | PASS |

**Recommendation:** **REJECT for initial open baseline**; defer to a later human-authorized restricted pilot lane. Prohibit synthetic sample in certification mode.

## 6. Claim Boundary

This record documents candidate data. It does not prove retrieval quality, scale behavior, organization quality, or certification.
