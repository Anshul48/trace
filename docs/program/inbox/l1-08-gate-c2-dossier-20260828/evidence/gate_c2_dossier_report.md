# Master Gate C2 Technical Dossier & Evaluation Report: Level 1 100K Scale Gate Production Certification

> **Session:** Wave R1 / Level 1 (100K Scale Gate Production Repair & Re-Certification)
> **Packet ID:** `l1-08-gate-c2-dossier-20260828`
> **Date:** 2026-08-28T13:37:00Z
> **Authority Level:** Coordinator & Master Gate Assembly Authority
> **Governing Standards:** `docs/program/00_GLOBAL_CONTEXT_REPAIR_LOOP.md`, `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`, DEC-P-005b
> **Candidate Commit:** `a2c25e05f31d0ecb81ecaaf4b08bb82739f1c17f` (`a2c25e0`)
> **Candidate Evidence Root:** `benchmarks/runs/100k_scale_candidate/`
> **Independent Verifier Attestation:** `docs/program/inbox/l1-07-verifier-attestation-20260828/evidence/verifier_attestation_receipt.json` (SHA-256: `066f3e94...`)
> **Overall Disposition:** **PASS_ALL_SCALE_GATE_INVARIANTS (READY FOR HUMAN GATE C2 PROMOTION)**

---

## 1. Executive Summary & Gate C2 Purpose

Following the Human Gate C2 decision (`REPAIR — promote_100k denied`), Wave R1 was initiated under [`00_GLOBAL_CONTEXT_REPAIR_LOOP.md`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/00_GLOBAL_CONTEXT_REPAIR_LOOP.md) to eliminate all five defects identified during the initial review:

1. **Clean, Committed Candidate Custody:** Source code committed in `a2c25e0`, lockfiles sealed, and raw telemetry retained.
2. **Real Product Path & Native ID Grounding:** Unified `doc_id = native_id` across 100,000 real documents, producing unfloored empirical retrieval metrics across all capability lanes.
3. **True Event-Driven Rebuild (Zero Cross-DB Table Copies):** The recovery drill reconstructed all derived tables directly from `events.payload_json` with 100.0% row-for-row and SHA-256 state-hash parity.
4. **Capacity Bounds Enforced:** Peak RSS capped at **$1.511\text{ GB} \le 2.0\text{ GB}$** (well under $\le 8.0\text{ GiB}$ host limit); total database size reduced from $6.16\text{ GB}$ down to **$679.89\text{ MB}$**.
5. **Passing Retrieval & Judged Abstention with Independent Verifier Attestation:** Direct Lookup nDCG = 0.3406 / Recall = 0.3558, Abstention Accuracy = **95.50%** (Zero hallucination = 0.0000), audited and signed by the Independent Verifier (`066f3e94...`).

---

## 2. Comprehensive Compliance & Verification Scorecard

| Invariant / Operational Domain | Contract / Baseline Standard | Candidate Observed Result | Independent Verifier Finding | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Document Scale ($D$)** | $D = 100,000$ unique real documents | 100,000 documents ingested across 5 corpora | Verified 100,000 records; 0 duplicate collisions | **PASS** |
| **Active Atom Storage ($N$)** | $N \ge 100,000$ active atoms | 228,328 active atom versions; 0 orphans | Verified 228,328 atoms; 1.0 retention rate | **PASS** |
| **Durability Anchor Recovery** | 1,000 sampled byte-slice proofs | 1,000 / 1,000 exact string matches against text | Verified 100.0% exact string recovery; 0.0% drift | **PASS** |
| **Repeat Erasure Idempotency** | $\Delta = 0$ writes on repeated purge | $\Delta = 0$ additional database writes | Verified exact idempotency; $\Delta = 0$ writes | **PASS** |
| **Bounded Graph Traversal** | Max degree $\le 10$, P95 $\le 35.0\text{ ms}$ | Max degree $= 10$, P50 $= 0.978\text{ ms}$, P95 $= 1.959\text{ ms}$ | Verified bounded degree and $1.959\text{ ms}$ P95 latency | **PASS** |
| **True Event-Driven Rebuild** | Reconstruct all tables from events; 0 table copies | 100,000 events replayed; 6-table SHA-256 match | Verified 100.0% parity across all 6 tables | **PASS** |
| **Spine Replay Throughput** | $\ge 1,000\text{ events/sec}$ | $1,376.4\text{ events/sec}$ ($72.65\text{ s}$ total) | Verified 1,376.4 events/sec replay rate | **PASS** |
| **Direct Lookup Retrieval** | Empirical unfloored (SciFact) | nDCG@10 $= 0.3406$, Recall@20 $= 0.3558$ | Verified positive empirical retrieval quality | **PASS** |
| **Multi-Hop Retrieval** | Empirical unfloored (MultiHop-RAG) | nDCG@10 $= 0.1206$, Recall@20 $= 0.1567$ | Verified positive empirical retrieval quality | **PASS** |
| **Judged Abstention Lane** | $\ge 85.0\%$ accuracy on unanswerable | Abstention Accuracy $= 95.50\%$, Zero Hallucination $= 0.0\%$ | Verified 95.50% accuracy on null queries | **PASS** |
| **Peak Host Memory (RSS)** | Single-process RSS $\le 2.0\text{ GB}$ ($\le 8.0\text{ GiB}$ host) | Peak RSS $= 1,547.61\text{ MB} = 1.511\text{ GB}$ | Verified peak RSS well within budget | **PASS** |
| **Database Storage Footprint** | Compact schema layout | Total SQLite DB size $= 679.89\text{ MB}$ ($89\%$ reduction) | Verified compact storage layout | **PASS** |
| **Automated Integrity Tests** | Unit tests passing under `pytest` | `tests/test_scale_rebuild_integrity.py` passing 4/4 | Verified 4/4 tests passing in 5.16s | **PASS** |

---

## 3. Cryptographic Table State-Hash Parity Verification (All 6 Tables Match)

The Independent Verifier confirmed row-for-row and cryptographic SHA-256 table digest matching across all 6 SQLite tables between the primary candidate database and the fresh rebuild database:

| Relational Table | Source Count | Replay Count | SHA-256 Table State-Hash | Parity Status |
| :--- | :--- | :--- | :--- | :--- |
| **`events`** | 100,000 | 100,000 | `1eae697844f2af2965144afcfbf1248dd5be79224ef25a1ae09c76d5ec7c7d5b` | **MATCH (100.0%)** |
| **`ingestions`** | 100,000 | 100,000 | `623df9d92d7be70c12ca7585ce709f7af9dd9d455a2cf5e3611606a064c2390f` | **MATCH (100.0%)** |
| **`nodes`** | 228,328 | 228,328 | `6d963e89a1564bef8fd5c87901e2ca0fc092781b3ab46057545355121ddc9631` | **MATCH (100.0%)** |
| **`node_versions`** | 228,328 | 228,328 | `70ad6d15ac71aba8a2a01df47d8de4f585bd8e675c557707ae67e11c1cd7fc20` | **MATCH (100.0%)** |
| **`edge_versions`** | 824,743 | 824,743 | `3203f5cc2e3542961f2f3e555031e7eb087fe856557d67158895d5b56001180b` | **MATCH (100.0%)** |
| **`source_lifecycle`** | 228,328 | 228,328 | `2531c46cae5bdfe1e7ec9852dfc7049c988337b3c0ef26235663c6e676fb53b7` | **MATCH (100.0%)** |

---

## 4. Master Dossier Deliverables Manifest

1. **`packet.md`:** Master Gate C2 declaration and coordination charter.
2. **`evidence/gate_c2_dossier.json`:** Cryptographically sealed JSON dossier summarizing all metrics, scale vectors, and verification receipts.
3. **`evidence/gate_c2_dossier_report.md`:** Complete technical evaluation and compliance report.
4. **`handoff.md`:** Formal submission handoff to the Human Owner.
5. **Supporting Independent Evidence Packets:**
   - [`r1-01-repair-architecture-20260828`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/r1-01-repair-architecture-20260828/) (Architecture & True Rebuild Specification)
   - [`l1-02-corpus-capsule-20260828`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/l1-02-corpus-capsule-20260828/) (100K Corpus Manifest & Merkle Root)
   - [`l1-07-verifier-attestation-20260828`](file:///mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/trace/docs/program/inbox/l1-07-verifier-attestation-20260828/) (Independent Verifier Attestation Receipt `066f3e94...`)

---

## 5. Coordinator Recommendation for Human Gate C2 Decision

The Level 1 100K Scale Gate Production Repair has satisfied every non-negotiable exit criterion and technical invariant under DEC-P-005b.

The Coordinator recommends:
- **Decision:** **`promote_100k` (APPROVED)**
- **Next Permitted Action:** Advance to **Level 2 (1,000,000 Document True Scale Pilot Planning & Gate D Submission)**.
