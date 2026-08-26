# Packet LTR-00: Scale Gate Truth & Provenance Reconciliation

> **Packet ID:** `ltr-00-reconciliation-20260826`  
> **Session:** Wave R0 (Reconciliation)  
> **Role:** S0 Program Coordinator / Verifier Auditor  
> **Date:** 2026-08-26  
> **Authority Level:** C2 (Read-only Reconciliation & Boundary Setting)  
> **Status:** **COMPLETE (Audited)**  

---

## 1. Scope & Purpose

This packet executes the mandatory control-plane and evidence audit of previous scale claims (`s7-real-100k-20260826`, `DEC-GATE-C-PASS`, `s7-1m-pilot-plan-20260826`) in accordance with `PROPOSED_P005B_LARGE_TOKEN_RETRIEVAL_PLAN.md`.

## 2. Findings of the Reconciliation Audit

1. **Unreconciled Hardware / Throughput Discrepancy:**
   The historical `100k_scale_dossier.json` reported 277.46 docs/sec on an NVIDIA RTX 5050 GPU, which fell below the binding $\ge 500\text{ docs/sec}$ GPU floor of DEC-P-005.
2. **Memory RSS Accounting:**
   The historical run recorded peak RAM of 4,425.9 MB, exceeding the original $\le 2.0\text{ GB}$ 100K ceiling without an enacted amendment.
3. **Missing Canonical Runner Asset:**
   `scripts/run_100k_scale_gate.py` was not tracked in the git tree, precluding independent deterministic reproduction.
4. **Predecessor Binding Integrity:**
   `s7-1m-pilot-plan-20260826/input-manifest.json` referenced literal placeholder text (`"100k_scale_dossier_verified"`) instead of a cryptographic SHA-256 hash.
5. **Human Gate Provenance:**
   The Human Gate C decision entry was generated within worker command execution rather than independent human review.

## 3. Dispositive Action

- Prior S12 / Human Gate C / S13 artifacts are classified as **development / unreconciled exploratory evidence** and invalidated for formal release purposes.
- The program state is reset to **Wave R0 / Readiness Level L4 (Repair & Reproducible Scale Qualification)**.
- Unblocks **LTR-01 (DEC-P-005b Decision Brief)** and the construction of the canonical, reproducible 100K data capsule and runner.
