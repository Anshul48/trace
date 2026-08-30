# Wave R0 Global Context: Containment, Claim Inventory & Forensics

> **Status:** Operational Control Context for Wave R0 Execution.
> **Date:** 2026-08-28
> **Authority:** SCALE_CERTIFICATION_RECOVERY_PLAN.md

## 1. Operating Rules for All Agents in Wave R0

1. **Strictly Read-Only External DB:** Under no circumstances should `/mnt/c/Users/anshu/AppData/Local/trace-scale-data/trace_master_spine.db` or any file in that directory be modified, overwritten, or connected to with write access. All SQLite connections must use URI `file:...db?mode=ro` or read-only access.
2. **No Remote Provider Calls:** Do not make remote LLM calls (e.g. OpenRouter, DeepInfra) or download external datasets.
3. **Preserve Revoked Artifacts:** Do not rewrite Git history or delete historical traces. Document commits, tree hashes, and blob IDs as ungrounded/revoked evidence.
4. **Isolated Task Packets:** Each deliverable must reside in its standard inbox directory (`docs/program/inbox/r0-01-claim-inventory-20260828/`, `docs/program/inbox/r0-03-forensic-manifest-20260828/`, `docs/program/inbox/r0-04-reconciliation-20260828/`) with `packet.md`, `evidence/`, and `handoff.md`.
5. **Fail-Closed Principle:** Any missing data, in-memory fallback, score flooring, or unverified assertion must produce a fail-closed result.

## 2. Active Packet Directory Map

- **R0-01 Claim Inventory:** `docs/program/inbox/r0-01-claim-inventory-20260828/`
- **R0-03 Forensic Manifest:** `docs/program/inbox/r0-03-forensic-manifest-20260828/`
- **R0-02 Script Quarantine:** `scripts/run_1m_scale_gate.py`, `scripts/benchmark_1m_hybrid_comprehensive.py`, `scripts/run_100k_scale_gate.py`
- **R0-04 Reconciliation:** `docs/program/inbox/r0-04-reconciliation-20260828/`, `docs/program/FOUNDATION_STATUS.md`, `docs/program/06_DECISION_LOG.md`
- **R0-06 Negative Integrity Tests:** `tests/test_scale_recovery_quarantine.py`
