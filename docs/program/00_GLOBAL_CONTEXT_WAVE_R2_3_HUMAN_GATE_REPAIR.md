# Global Context: Wave R2.3 Human Gate Defect Remediation & Truth Recovery

> **Context Version:** `2.3.0`
> **Session State:** ACTIVE PROTOCOL REPAIR
> **Target Scale:** $D = 100,000$ unique documents (Level 1)
> **Target Standard:** `DEC-P-005b-LEVEL1-R2.3`
> **Governance Authority:** Human Gate C2 Ruling (`REPAIR — promote_100k denied; 1M unauthorized`)
> **Parent Coordinator:** Antigravity Coordinator
> **Date:** 2026-08-29

---

## 1. Executive Summary & Gate Decision Context

On 2026-08-29, the Human Gate evaluated the Wave R2.2 100K candidate and issued a formal **REPAIR** ruling (`promote_100k: DENIED`, `formal_wave_r3_dispatch: DENIED`, `level_2_1m: UNAUTHORIZED`).

While verifying that a genuine 100K baseline run occurred (SQLite integrity ok, 100,000 events, 228,328 atoms, 824,229 edges, 7,457 queries, 153 tests passing), the audit revealed **8 gate-stopping protocol integrity defects** that must be resolved prior to any promotion.

---

## 2. The 8 Gate-Stopping Defects and Required Remediation Matrix

| # | Defect Identified by Human Gate | Root Cause in Codebase | Concrete Remediation Plan |
|---|---|---|---|
| **1** | **“100,000 unique text documents” is not established.**<br>DB has 100,000 `(dataset, doc_id)` records, 99,995 unqualified `doc_id`s, and 99,958 distinct content hashes (5 ID collisions, 42 content duplicates). Verifier merely counted rows. | `run_100k_scale_gate.py:1169` deduplicated only on `(doc_id, content_hash)`. `verify_100k_candidate.py:632` counted rows without checking `COUNT(DISTINCT content_hash)` and `COUNT(DISTINCT doc_id)`. | Enforce global uniqueness: runner deduplicates strictly on `content_hash` and `doc_id` across all datasets. Verifier queries SQLite: `COUNT(*) == 100,000`, `COUNT(DISTINCT doc_id) == 100,000`, `COUNT(DISTINCT content_hash) == 100,000`. |
| **2** | **5,567 ranked candidates are not persisted documents.**<br>Across 149,140 Top-20 entries, 5,567 entries affecting 594 queries refer to 13 alias/raw-text identifiers absent from DB. | `run_100k_scale_gate.py:1681` iterated over `self.doc_index` for padding, which contained alias keys and source-text strings. `verify_100k_candidate.py:829` verified list length and rank ordering but never checked SQLite DB document existence. | Runner index `doc_index` contains ONLY canonical persisted `doc_id`s. Padding selects only from genuine persisted `doc_id`s. Verifier loads all persisted document IDs from SQLite and asserts every candidate in `ranked_candidates` exists in DB. |
| **3** | **Qrels were not verifier-only.**<br>Runner loaded `gold_ids`, branched on null/expected-abstention labels, computed metrics, and wrote gold IDs into raw candidate telemetry. | `run_100k_scale_gate.py:1811, 1860` had candidate access to gold labels. | Strict separation of concerns: runner operates **blindly** on un-labeled query inputs (`query_id`, `query_text`, `lane`, `dataset`), emits `ranked_candidates` (20 items with `doc_id`, `score`, `rank`), system abstention decision, and latency. Runner NEVER reads `gold_ids` or emits precalculated metrics. Verifier holds `queries_manifest.json` qrels and computes all metrics from first principles. |
| **4** | **Custody and independence requirements not followed.**<br>HEAD older commit, worktree dirty, policy `PROPOSED_AWAITING_HUMAN_GATE`, candidate manifest bound no Git commit/runner hash/schema hash/command line/environment lock. Missing named reports. | Candidate manifest and verifier receipts lacked full cryptographic identity bindings. Policy state was not locked to ratified state. | Candidate manifest binds `git_commit`, `git_tree_hash`, `runner_hash`, `verifier_hash`, `schema_hash`, `policy_hash`, `command_line`, and environment lock. Verifier binds candidate manifest hash, DB SHA-256, evidence hashes, and merkle root. Reconcile policy lockfile and documentation. |
| **5** | **Verification was not “from first principles.”**<br>Metrics recomputed from candidate rankings; retrieval not rerun; replay DB was not retained; graph P95 came from dossier rather than graph telemetry. | Replay database was ephemeral; graph P95 was read from dossier JSON rather than telemetry file. | Runner retains replay database `scale_100k_replay.db` alongside `scale_100k.db`. Verifier independently inspects `scale_100k_replay.db` tables and cryptographic table hashes against `scale_100k.db`. Verifier computes Graph P95 directly from `graph_walk_telemetry.jsonl` stream. |
| **6** | **Storage and memory misreported.**<br>Frozen denominator: 62,870,136 bytes; DB: 450,785,280 bytes (7.17× multiplier, not 6.89×). Verifier substituted candidate dossier's larger denominator. Memory was sampled current RSS, not peak RSS. | `verify_100k_candidate.py:678` used `dossier.get("scale_workload_vector", {}).get("raw_source_bytes_B")` over policy denominator. Runner/dossier mislabeled VmRSS as peak. | Verifier enforces `db_size_bytes / frozen_policy_raw_text_denominator_bytes`. Accurately report and verify Peak RSS (`VmHWM` / Peak Working Set) and Current RSS (`VmRSS`) against policy ceiling. |
| **7** | **“Byte-offset proofs” were character-slice self-consistency checks.**<br>Verification sliced decoded Python strings in event payloads rather than resolving byte offsets against frozen original source bytes. | `verify_100k_candidate.py:662` performed string slicing on `payload["content"]` rather than UTF-8 byte span verification. | `node_versions` stores exact UTF-8 byte spans (`span_start`, `span_end`). Verifier encodes content to UTF-8 and slices raw bytes `content.encode("utf-8")[s_start:s_end]` to verify against `content_hash`. |
| **8** | **Production runner cannot start from clean base installation.**<br>`jsonschema` and `psutil` were placed only in `test` extra while runner imported `jsonschema` unconditionally. `uv run --isolated python scripts/run_100k_scale_gate.py --help` failed with `ModuleNotFoundError`. | `pyproject.toml` base `dependencies` list was empty (`dependencies = []`). | Add `jsonschema>=4.20` and `psutil>=5.9` to `dependencies` in `pyproject.toml` so isolated execution starts cleanly. |

---

## 3. Execution Plan & Specialist Assignment

1. **Subagent 1: Runner Repair Specialist** (`run_100k_scale_gate.py`)
   - Implement strict deduplication (content hash + doc_id).
   - Enforce blind query evaluation (no gold_ids, no precomputed metrics in runner).
   - Ensure `doc_index` and padding only contain canonical persisted document IDs.
   - Retain `scale_100k_replay.db` for verifier audit.
   - Accurately track Peak RSS (`VmHWM`) and Current RSS (`VmRSS`).
   - Bind full execution identity in `candidate_manifest.json`.

2. **Subagent 2: Verifier Repair Specialist** (`verify_100k_candidate.py`)
   - Implement first-principles metric evaluation from raw candidate rankings and verifier-held qrels.
   - Check SQLite DB membership for 100% of candidate doc IDs in `ranked_candidates`.
   - Verify SQLite table counts, distinct doc IDs ($100,000$), distinct content hashes ($100,000$).
   - Verify UTF-8 byte offset spans against content hashes.
   - Verify `scale_100k_replay.db` directly.
   - Verify storage multiplier strictly against frozen policy denominator.
   - Compute graph P95 directly from `graph_walk_telemetry.jsonl`.

3. **Subagent 3: Policy, Test & Calibration Specialist**
   - Update `pyproject.toml` dependencies and lockfile.
   - Update `scale_policy.lock.json` and schema.
   - Update unit and negative tests in `tests/test_scale_candidate_verifier.py` and `tests/test_scale_rebuild_integrity.py`.
   - Run diagnostic calibration suite to validate end-to-end correctness.
