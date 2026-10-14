# Global Context: Wave R2.2 Measurement Integrity Audit Remediation (Phase 2 - Full Closure)

> **Context Version:** `2.2.2`
> **Session State:** ACTIVE SYSTEMATIC REPAIR
> **Target Scale:** $D = 100,000$ unique documents (Level 1)
> **Target Standard:** `DEC-P-005b-LEVEL1-R2.2`
> **Governance Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied; 1M unauthorized`)
> **Parent Coordinator:** Antigravity Coordinator
> **Date:** 2026-08-29

---

## 1. Governance & Execution Status Ledger

```yaml
c2_pol_01: REMEDIATED_AND_VERIFIED
r2_2_01_06: COMPLETE_AND_VERIFIED
measurement_protocol: MEASUREMENT_PROTOCOL_VERIFIED (153/153 PASS)
r2_2_07: COMPLETE_AND_VERIFIED (100K candidate executed with full telemetry)
r2_2_08: COMPLETE_AND_VERIFIED (independent verifier attestation receipt written)
candidate_status: MEASUREMENT_PROTOCOL_VERIFIED_CANDIDATE_COMPLETED
gate_c2: READY_FOR_HUMAN_RULING_AND_WAVE_R3_DISPATCH
wave_r3: READY_FOR_ENGINEERING_DISPATCH (R3A Retrieval + R3B Storage)
level_2_1m: PENDING_GATE_C2_AND_GATE_D
```

---

## 2. The 10 Material Blockers Remediation Plan

### Blocker 1: Worktree Sealing & Accurate Defect Report
- Reconcile modified/untracked files; clean historical overlays.
- Update `docs/program/inbox/r2-02-measurement-integrity-20260829/evidence/wave_r2_2_measurement_integrity_report.md` to accurately document all 10 blockers and exact relative paths.

### Blocker 2: Governance Records Reconciliation
- Update `docs/program/inbox/r2-02-measurement-integrity-20260829/handoff.md` and `packet.md`.
- Replace stale policy hashes with the new canonical policy lock digest.
- Mark governance status as `PROPOSED_REPAIR_IN_PROGRESS`.

### Blocker 3: Runner & Verifier Null-Query Telemetry Contract
- Fix `scripts/run_100k_scale_gate.py` and `scripts/verify_100k_candidate.py` so null queries are written and indexed without duplicate record collisions.
- Author an end-to-end integration test that executes `run_100k_scale_gate.py` and immediately verifies the output directory with `verify_100k_candidate.py`.

### Blocker 4: Retrieval Metric Integrity & Duplicate Candidate Prevention
- Remove `gold_ids.update(record_golds)` in `scripts/verify_100k_candidate.py`. Gold IDs must come 100% from frozen `queries_manifest.json`.
- Enforce that `ranked_candidates` contains exactly 20 **unique** document IDs; reject duplicates.
- Ensure hit calculation is mathematically sound and un-spoofable.

### Blocker 5: MultiHop Coverage Metric Contract
- Enforce strict binary all-gold coverage for MultiHop-RAG: query coverage is 1.0 iff all gold IDs are in top-20; 0.0 otherwise.
- Fix `scripts/run_100k_scale_gate.py` to compute and report true binary coverage.
- Fix `scripts/verify_100k_candidate.py` to enforce `mean_cov >= min_cov` without `mean_rec` bypass.

### Blocker 6: Mandatory Evidence Allowlist & Remove Dossier Fallbacks
- In `scripts/verify_100k_candidate.py`, define a mandatory list of evidence files.
- Fail closed if ANY mandatory file is missing from disk or `checksums.json`.
- Remove all fallback code reading replay parity or durability from dossier literals.

### Blocker 7: Independent Reproduction Clarity
- Clearly document in verifier and receipts what state is SQLite-persisted vs memory-resident.
- Ensure all SQLite-persisted checks (integrity, table counts, degree bound, byte-offset anchor proofs) are audited directly.

### Blocker 8: Corpus Manifest Pinned & Remove CLI Path Fallbacks
- Remove all `AppData` and `ltr-02` fallback paths from `scripts/run_100k_scale_gate.py`.
- Require explicit valid paths; fail closed on missing paths.
- Pin canonical corpus manifest SHA-256 constant.

### Blocker 9: Policy Deduplication, Schema Strictness & Dependencies
- Remove duplicate `"statistical_method"` block from `benchmarks/policies/scale_policy.lock.json`.
- Update `pyproject.toml` to declare `jsonschema` and `psutil` dependencies.
- Update `scale_policy.schema.json` and recompute canonical policy digest.

### Blocker 10: Safe Verifier Receipt Custody
- Change default receipt path in `scripts/verify_100k_candidate.py` to `<candidate_dir>/verifier_attestation_receipt.json`.
- Restore modified historical `docs/program/inbox/l1-07-verifier-attestation-20260828/` files.
- Label attestation token exclusively as `merkle_digest_token`.
