# Wave R2 Global Context: 100K Scale Gate Production Repair & Strict Gate Enforcement

> **Status:** Operational Control Context for Level 1 Wave R2 Repair Loop.
> **Date:** 2026-08-28
> **Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied. Level 2 / 1M remains unauthorized.`) & `SCALE_CERTIFICATION_RECOVERY_PLAN.md`

---

## 1. Governing Non-Negotiable Requirements (All Subagents Must Obey)

All specialist subagents operating in Wave R2 must strictly enforce and prove these six non-negotiable exit criteria:

1. **Fail-Closed Gate Verification in Runner:**
   - The runner (`scripts/run_100k_scale_gate.py`) must load the frozen DEC-P-005 release thresholds and evaluate every empirical score.
   - If ANY metric fails (e.g. retrieval, storage, abstention, memory, replay), the runner MUST emit `overall_verdict: "CANDIDATE_FAILED"` in `100k_scale_dossier.json` and exit with code 1.
   - Only when ALL metrics strictly satisfy the frozen thresholds can the runner emit `overall_verdict: "PASS_ALL_SCALE_GATE_INVARIANTS"`.

2. **Binding Retrieval Quality Floors Met on All Capability Lanes:**
   - Ingest full document text (`record['text']` and `record['title']`).
   - The multi-lane hybrid retrieval engine must achieve:
     * **SciFact (`beir-scifact`):** $\text{nDCG@10} \ge 0.700$, $\text{Recall@20} \ge 0.880$, $\text{P95} \le 25.0\text{ ms}$.
     * **NFCorpus (`beir-nfcorpus`):** $\text{nDCG@10} \ge 0.350$, $\text{Recall@20} \ge 0.220$, $\text{P95} \le 25.0\text{ ms}$.
     * **FiQA (`beir-fiqa`):** $\text{nDCG@10} \ge 0.400$, $\text{Recall@20} \ge 0.550$, $\text{P95} \le 30.0\text{ ms}$.
     * **MultiHop (`multihop-rag`):** $\text{nDCG@10} \ge 0.750$, $\text{Coverage@20} \ge 0.880$, $\text{P95} \le 45.0\text{ ms}$.

3. **Full 301 Unanswerable Query Evaluation & 100% Zero-Hallucination:**
   - Specifically evaluate all 301 `query_class == 'null_query'` cases from `multihop-rag/queries.jsonl`.
   - Enforce fail-closed abstention: `zero_hallucination_rate == 1.000` (100.0% fail-closed abstention, zero hallucinations on ungrounded claims).

4. **Strict Storage Multiplier Limit ($\le 3.0\times$):**
   - For the $65.45\text{ MB}$ raw corpus, total SQLite database footprint must remain $\le 195\text{ MB}$ (target $\le 170\text{ MB}$, $< 2.65\times$).
   - Implement lean schema (byte span offsets in `node_versions`, minimal ingestion records, vacuumed WAL).

5. **Persisted SQLite Graph Max Degree Measurement:**
   - Max degree must be measured by querying the persisted SQLite table directly:
     ```sql
     SELECT MAX(deg) FROM (SELECT COUNT(*) as deg FROM edge_versions GROUP BY source_id);
     ```
   - Persisted graph degree must be $\le 10$ and PPR P95 latency $\le 35.0\text{ ms}$.

6. **Durable Candidate Custody, DB Snapshot Retention & Standalone Verifier:**
   - Retain the complete SQLite database snapshot at `benchmarks/runs/100k_scale_candidate/scale_100k.db` and bind its SHA-256 in `candidate_manifest.json`.
   - Implement standalone independent verifier CLI in `scripts/verify_100k_candidate.py` to independently audit candidate evidence in separate custody.
   - Retain all JSON/JSONL raw telemetry.

7. **Governance Integrity:**
   - No promotion record or self-approval. Gate C2 remains REPAIR until all requirements are met.

---

## 2. Packet Directory Map (Wave R2)

- **`docs/program/inbox/r2-01-repair-architecture-20260828/`**: Architecture specification and fail-closed runner contract.
- **`scripts/run_100k_scale_gate.py`**: Repaired canonical production runner.
- **`scripts/verify_100k_candidate.py`**: Standalone independent verifier script.
- **`tests/test_scale_candidate_verifier.py`**: Automated verifier and gate-checking unit tests.
- **`benchmarks/runs/100k_scale_candidate/`**: Candidate evidence directory with retained `scale_100k.db`.
- **`docs/program/inbox/l1-07-verifier-attestation-20260828/`**: Verifier attestation receipt.
- **`docs/program/inbox/l1-08-gate-c2-dossier-20260828/`**: Master Gate C2 dossier re-submission.
