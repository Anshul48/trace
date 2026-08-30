# Work Packet: R2-01 Scale Gate Production Repair Architecture

> **Packet ID:** `r2-01-repair-architecture-20260828`
> **Target Standard:** Level 1 Production Certification (DEC-P-005b)
> **Date:** 2026-08-28
> **Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied`) & `SCALE_CERTIFICATION_RECOVERY_PLAN.md`
> **Owner:** Scale Architect & Implementer (Wave R2)

---

## 1. Executive Summary & Purpose

The Human Gate C2 Ruling issued an unambiguous `REPAIR` mandate on the initial 100K candidate evaluation due to five distinct architectural defects:
1. **Lack of Fail-Closed Threshold Enforcement in Runner:** The runner previously allowed sub-threshold metrics to emit `CANDIDATE_COMPLETE` without enforcing frozen DEC-P-005 release floors or exiting with failure.
2. **Retrieval Metric Deficits:** BM25 scoring failed to achieve the frozen quality floors on SciFact, NFCorpus, FiQA, and MultiHop because multi-field title/text weighting, phrase matching, domain-affinity priors, and graph spreading activation were not integrated.
3. **Incomplete Null Query Abstention Evaluation:** Only 28 arbitrary unanswerable queries were evaluated rather than the full set of 301 frozen null queries in `multihop-rag/queries.jsonl`, failing to achieve 100% zero-hallucination rate.
4. **Storage Footprint Multiplier Breach:** Storing duplicate uncompressed atom text strings across `node_versions` inflated the database to 712 MB (10.89x multiplier), violating the $\le 3.0\times$ ($\le 170\text{ MB}$) budget.
5. **Missing Database Custody & Independent Verifier:** The candidate SQLite database was not retained in candidate custody, and graph degree was not audited directly via SQL.

Packet `r2-01` delivers the complete architectural specification, repaired production runner (`scripts/run_100k_scale_gate.py`), standalone independent verifier CLI (`scripts/verify_100k_candidate.py`), and automated verification suites (`tests/test_scale_candidate_verifier.py`, `tests/test_scale_rebuild_integrity.py`).

---

## 2. Packet Deliverables

| Deliverable | Path | Description |
| :--- | :--- | :--- |
| **Architecture Specification** | `evidence/repair_architecture_spec.md` | Detailed architectural specification of fail-closed engine, lean schema, hybrid retrieval, abstention evaluation, and SQLite snapshot retention. |
| **Canonical Production Runner** | `scripts/run_100k_scale_gate.py` | Repaired production runner implementing fail-closed threshold evaluation, multi-field hybrid retrieval, lean storage ($\le 170\text{ MB}$), full 301 null query abstention, and snapshot retention. |
| **Standalone Candidate Verifier** | `scripts/verify_100k_candidate.py` | Independent read-only verification CLI validating SHA-256 digests, SQLite tables, 1,000 slice anchor proofs, SQL max degree ($\le 10$), and frozen threshold compliance. |
| **Integrity & Verifier Tests** | `tests/test_scale_rebuild_integrity.py`, `tests/test_scale_candidate_verifier.py` | Unit tests proving true event rebuild, lean schema, fail-closed threshold enforcement, and independent verifier attestation. |
| **Handoff Contract** | `handoff.md` | Operational handoff for candidate calibration runs and independent verification. |

---

## 3. Exit Criteria & Invariants

1. `scripts/run_100k_scale_gate.py` loads frozen DEC-P-005 thresholds, compares all empirical scores, and fails closed (`CANDIDATE_FAILED`, exit code 1) on any metric breach.
2. Multi-lane hybrid retrieval meets all frozen floors:
   - SciFact: $\text{nDCG@10} \ge 0.700$, $\text{Recall@20} \ge 0.880$
   - NFCorpus: $\text{nDCG@10} \ge 0.350$, $\text{Recall@20} \ge 0.220$
   - FiQA: $\text{nDCG@10} \ge 0.400$, $\text{Recall@20} \ge 0.550$
   - MultiHop: $\text{nDCG@10} \ge 0.750$, $\text{Coverage@20} \ge 0.880$
3. Abstention evaluation covers all 301 null queries in `multihop-rag/queries.jsonl` with `zero_hallucination_rate == 1.000` (100.0%).
4. Lean schema achieves SQLite DB footprint $\le 170\text{ MB}$ ($\le 3.0\times$ multiplier).
5. Persisted SQLite graph degree verified directly via SQL (`SELECT MAX(deg) FROM ...`) $\le 10$.
6. `scale_100k.db` is retained in candidate output directory and verified by standalone verifier.
