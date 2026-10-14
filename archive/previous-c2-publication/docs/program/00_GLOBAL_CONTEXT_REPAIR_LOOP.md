# Wave R1 Global Context: 100K Scale Gate Production Repair & Re-Certification Loop

> **Status:** Operational Control Context for Level 1 Repair Loop.
> **Date:** 2026-08-28
> **Authority:** Human Gate C2 Decision (`REPAIR — promote_100k denied`) & `SCALE_CERTIFICATION_RECOVERY_PLAN.md`

---

## 1. Governing Exit Criteria for All Agents

All specialist subagents operating in this repair loop must strictly adhere to and prove these five non-negotiable exit criteria:

1. **Clean, Committed Candidate Custody:**
   - Source code, manifests, and test fixtures must be committed to Git.
   - All evaluation outputs must be sealed in `benchmarks/runs/100k_scale_candidate/` and bound to exact commit SHA, tree hash, lockfile SHA-256, corpus selection Merkle root, and DB snapshot SHA-256.
2. **Real Ingestion / Retrieval / Graph Product Path:**
   - Ingest real text from the frozen 100,000 document corpus capsule (`musique`, `beir-fiqa`, `beir-scifact`, `beir-nfcorpus`, `multihop-rag`).
   - Align `doc_id = native_id` so that Okapi BM25 and TL2 Personalized PageRank (PPR) evaluate against the frozen qrels ground-truth without zero-overlap string mismatches.
   - Prohibit artificial score floors, clamping (`max(min + 0.012)`), and synthetic GPU inputs.
3. **True Event-Driven Rebuild (Zero Cross-DB Table Copies):**
   - In `run_crash_recovery_drill`, rebuild every derived table (`ingestions`, `nodes`, `node_versions`, `edge_versions`, `source_lifecycle`) solely from the `events` payload stream through deterministic projection transformations.
   - Strictly prohibit querying `SELECT * FROM table` from the source DB and copying rows into the rebuild DB.
   - Prove 100.0% row-for-row and SHA-256 table state-hash parity between the source and rebuilt databases.
4. **Strict Capacity Limits ($\le 3.0\times$ Storage & $\le 8.0\text{ GiB}$ RSS):**
   - **Storage Multiplier $\le 3.0\times$:** Final SQLite database footprint must not exceed $140\text{ MB}$ for the $46.56\text{ MB}$ raw corpus. Bound graph edges to $k \le 10$ neighbors per atom and execute `PRAGMA wal_checkpoint(TRUNCATE);` and `VACUUM;`.
   - **Peak Host Memory $\le 8.0\text{ GiB}$:** Use chunked streaming for row hashing (`fetchmany(10000)`) and disk-backed retrieval structures to maintain peak RSS $\le 2.0\text{ GB}$.
5. **Passing Retrieval & Judged Abstention with Independent Verifier Attestation:**
   - Meet DEC-P-005 / DEC-P-005b quality thresholds across all lanes.
   - A fresh, independent verifier in a detached context must audit all raw telemetry, reproduce metrics, test the true event rebuild, and sign the final attestation receipt.

---

## 2. Active Packet Directory Map (Wave R1)

- **`docs/program/inbox/r1-01-repair-architecture-20260828/`**: True event rebuilder specification, compact graph schemas, and native ID mapping contract.
- **`scripts/run_100k_scale_gate.py`**: Production-grade canonical runner.
- **`tests/test_scale_rebuild_integrity.py`**: Negative integrity and true event rebuild unit tests.
- **`benchmarks/runs/100k_scale_candidate/`**: Isolated candidate execution root.
- **`docs/program/inbox/l1-07-verifier-attestation-20260828/`**: Independent verification attestation.
- **`docs/program/inbox/l1-08-gate-c2-dossier-20260828/`**: Re-submitted Gate C2 Dossier.
