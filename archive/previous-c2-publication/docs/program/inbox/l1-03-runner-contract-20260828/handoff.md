# Handoff: Packet L1-03 to L1-04 Implementer

> **Handoff ID:** `l1-03-handoff-20260828`
> **Source:** Scale Architect & Evaluator (L1-03)
> **Destination:** Scale Implementer (L1-04) & Verifier (L1-05)
> **Date:** 2026-08-28T10:47:00Z
> **Status:** **DELIVERED**

---

## 1. Summary of Completed Deliverables

1. **`packet.md`:** Work packet charter establishing authority, scope, and non-negotiable principles under DEC-P-005b and `SCALE_CERTIFICATION_RECOVERY_PLAN.md`.
2. **`evidence/runner_contract_spec.md`:** Rigorous technical specification defining:
   - CLI interfaces and fail-closed preflight manifest checks.
   - Relational SQLite schema with WAL configuration, transactional batching, and `(workspace_id, doc_id, content_hash)` deduplication constraints.
   - True Okapi BM25 ranking algorithm ($k_1 = 1.5, b = 0.75$) and TL2 PPR graph traversal ($\le 50$ degree, $\le 15$ depth, $\le 35\text{ ms}$ latency).
   - Unclamped metrics evaluation for nDCG@10 and Recall@20 (prohibiting artificial floors and static literals).
   - Evaluated abstention protocol against ground-truth judgments.
   - 100% full-event log replay with cryptographic table state-hash parity verification.
   - Sampled 1,000 random byte-slice anchor proofs against original source text.
   - Schemas for all raw telemetry and dossier files.

---

## 2. Implementation Instructions for L1-04

The Implementer for **L1-04** must modify `scripts/run_100k_scale_gate.py` to:
1. Implement the DDL schema specified in Section 3 of `evidence/runner_contract_spec.md`.
2. Ensure batch ingestion populates `events`, `ingestions`, `nodes`, `node_versions`, `source_lifecycle`, and `edge_versions` within single atomic transactions.
3. Compute exact Okapi BM25 scores and exact unclamped nDCG@10 and Recall@20.
4. Replace hardcoded abstention metrics with dynamic evaluation over unanswerable queries.
5. Replace mock replay logic with 100% full-event replay into a fresh database and table-by-table SHA-256 hash comparison.
6. Verify 1,000 byte-slice anchor proofs against the in-memory document text.
7. Support CLI parameters: `--target-docs`, `--data-root`, `--output-dir`, `--diagnostic`, `--quick`.
8. Execute a 1K diagnostic calibration to verify end-to-end functionality.
