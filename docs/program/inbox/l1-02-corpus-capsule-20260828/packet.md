# Work Packet L1-02: 100K Real Corpus and Judgment Capsule Freeze

> **Role:** Data Steward & Audit Specialist (Level 1)
> **Session:** Level 1 (100K Scale Requalification)
> **Packet ID:** `l1-02-corpus-capsule-20260828`
> **Date:** 2026-08-28T10:41:26Z
> **Authority Level:** L1 (Corpus Custody & Cryptographic Freezing)
> **Status:** **COMPLETED**
> **Base Commit / Tree:** `f74767e22f9c2d7a5c1f0fe2098cd40748aaffe1` / `82e138d9ac570a017bf42fbd0523ae51493e611b`

---

## 1. Objective

Freeze the canonical 100,000-document real-text corpus capsule ($D = 100,000$) and multi-lane evaluation query suite derived from the normalized datasets in `/mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820/`.

Establish deterministic record selection rules, compute exact byte-for-byte SHA-256 hashes across all corpus files, query files, and judgment evidence maps, catalog open-source licensing metadata, and assemble machine-readable manifests (`corpus_manifest.json` and `queries_manifest.json`) that strictly bind all downstream Level 1 runner and verification work.

---

## 2. Context & Authority

- **Program Authorities:**
  - `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md` (Level 1, Section 4.1, 4.3, 5.2, 5.4)
  - `docs/program/00_GLOBAL_CONTEXT_RECOVERY.md` (Operational Control Context)
  - `docs/program/inbox/l1-01-100k-reconciliation-20260828/` (100K Reconciliation Gap Analysis)
  - `docs/program/06_DECISION_LOG.md` (DEC-004, DEC-P-001, DEC-P-002, DEC-P-005b)
- **Data Source Root:**
  - `/mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820/`

---

## 3. Scope & Selection Declaration

The 100,000 unique source records ($D$) are formed via deterministic zero-indexed offset slicing `[0:N]` over the 5 normalized datasets:

| Dataset | Available Records | Frozen Selected ($D$) | Slicing Rule | Raw Text Bytes | Dataset License |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`musique`** | 101,962 | **80,000** | `corpus.jsonl[0:80000]` | 35,649,302 B | CC BY 4.0 |
| **`beir-fiqa`** | 57,600 | **10,575** | `corpus.jsonl[0:10575]` | 8,141,714 B | CC BY-NC-SA 4.0 |
| **`beir-scifact`** | 5,183 | **5,183** | `corpus.jsonl[0:5183]` | 7,268,200 B | CC BY-NC 4.0 |
| **`beir-nfcorpus`** | 3,633 | **3,633** | `corpus.jsonl[0:3633]` | 5,446,686 B | CC BY-SA 4.0 |
| **`multihop-rag`** | 609 | **609** | `corpus.jsonl[0:609]` | 6,364,234 B | ODC-By v1.0 |
| **TOTAL** | **168,987** | **100,000** | **Exact Deterministic** | **62,870,136 B (59.96 MB)** | **100% License-Audited** |

- **Selection Merkle Root SHA-256:** `5467c64a40e3bb6f801fc5f57413b5c512b0207ff6053617bddd8e8146a7813b`
- **Unique Source Identifiers:** Exactly 100,000 unique `(dataset, native_id)` pairs (0 collisions).

---

## 4. Deliverables Catalog

1. **`evidence/corpus_manifest.json`:** Machine-readable catalog containing exact file paths, record counts, file sizes, SHA-256 digests, license metadata, and selection Merkle root.
2. **`evidence/queries_manifest.json`:** Machine-readable catalog containing all five evaluation query suites (Direct Lookup, Domain Semantic, Semantic QA, Multi-Hop Reasoning, Abstention Suite) with exact query counts, judgment evidence map hashes, and evaluation protocols.
3. **`evidence/corpus_capsule_report.md`:** Comprehensive narrative report on corpus integrity, licensing review, selection rules, deduplication audit, query lane taxonomy, and cryptographic ledger.
4. **`handoff.md`:** Formal custody handoff unblocking L1-03 (Certification Runner Contract) and L1-04 (Runner Repair).

---

## 5. Non-Negotiable Rules Compliance

- [x] Zero synthetic text, zero simulated records, zero in-memory fallbacks used.
- [x] Exactly 100,000 unique source records ($D$) proven by cryptographic hash audit.
- [x] All 5 source datasets verified under recognized open-source / open-data licenses.
- [x] Exact SHA-256 hashes computed and recorded for all corpus files, query files, and judgment maps.
- [x] Abstention suite incorporates 301 frozen unanswerable queries (`null_query`) to ensure fail-closed evaluation.
