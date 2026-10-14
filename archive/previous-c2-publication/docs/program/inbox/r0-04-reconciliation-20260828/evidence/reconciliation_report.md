# R0-04 Reconciliation Report: Scale Governance & Forensic Alignment

> **Date:** 2026-08-28
> **Authority:** `docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md`
> **Status:** Reconciled

---

## 1. Context and Objective

Following the lead auditor findings, Wave R0 was dispatched to contain unsound runners, inventory all scale claims, and forensically inspect external databases. This report documents the complete reconciliation between claimed milestone achievements and measured physical reality.

---

## 2. Cross-Document Governance Contradictions and Resolutions

| Area | Prior Documented State | Forensic Reality (R0-01 & R0-03) | Reconciled Governance Status |
|---|---|---|---|
| **1M Master Spine** | Claimed 1,000,000 documents durably ingested into SQLite WAL (`b9b03f3`) | DB size is 700 KB with 45 events, 9 nodes, 0 1M docs. Loop executed 0 SQL inserts. | **REVOKED_FABRICATED** (`DEC-1M-SCALE-REVOKED`) |
| **1M Unique Corpus** | Claimed 1M unique incremental documents | Staged corpora contain 63,071 unique texts (93.69% duplicate iterations). | **REVOKED_FABRICATED** (`DEC-1M-SCALE-REVOKED`) |
| **1M Hybrid Cognitive** | Claimed `PASS_AND_CERTIFIED` across 6 reasoning lanes (`30912f3`) | Evaluated 6 self-authored landmark questions on `:memory:` fallback with substring matching. | **REVOKED_FABRICATED** (`DEC-1M-SCALE-REVOKED`) |
| **100K Human Gate C2** | Recorded as `APPROVED / PASSED` (`DEC-GATE-C2-PASS-REMEDIATED`) | `scripts/run_100k_scale_gate.py` has score floors (lines 900-901), literal abstention scores, incomplete replay, and mutated dossier SHA (`bc5ea63`). | **UNCONFIRMED_DEFECTIVE** (`DEC-100K-GATE-C2-UNCONFIRMED`) |
| **Runner Status** | Scripts executable as canonical certification tools | Unsound runners emit ungrounded claims. | **CONTAINED_QUARANTINED** (`R0-02 / R0-06`) |

---

## 3. Governance Document Updates

1. **`06_DECISION_LOG.md`**:
   - Added `DEC-1M-SCALE-REVOKED`: Invalidation of commits `b9b03f3`, `4a4a7b9`, `30912f3` and revocation of 1M claims.
   - Added `DEC-100K-GATE-C2-UNCONFIRMED`: Reclassification of Gate C2 to `UNCONFIRMED` pending Level 1 requalification.
2. **`FOUNDATION_STATUS.md`**:
   - Program State updated to `scale_certification_recovery_wave (Wave R0 Complete)`.
   - Replaced unconfirmed 100K/1M active boards with Wave R0 and Level 1 task registers.
3. **`CONTROL_PLANE_LOCK.json`**:
   - Updated lock hashes and status registers to reflect R0 containment.

---

## 4. Verification and Next Steps

- **Quarantine Verification:** R0-06 test suite (`tests/test_scale_recovery_quarantine.py`) passed 9/9 tests cleanly.
- **Next Authorized Wave:** Level 1 Requalification (`L1-01` through `L1-08`) under `SCALE_CERTIFICATION_RECOVERY_PLAN.md`.
