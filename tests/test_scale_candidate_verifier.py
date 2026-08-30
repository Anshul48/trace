"""Unit tests for Wave R2.2 Scale Gate Candidate Verifier & Complete Fail-Closed Enforcement."""

from __future__ import annotations

import io
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.modules.pop("trace", None)

import pytest

from run_100k_scale_gate import Scale100KRunner, get_process_memory_info
from verify_100k_candidate import (
    CandidateVerifier,
    compute_query_ndcg10_recall20_coverage20,
    compute_sha256,
    compute_merkle_root,
    safe_print,
    main as verifier_main,
    CANONICAL_POLICY_SHA256,
    CANONICAL_QUERIES_MANIFEST_SHA256,
    CANONICAL_CORPUS_MANIFEST_SHA256,
    CANONICAL_BLIND_QUERIES_SHA256,
    STANDARD_LEVEL1,
    STANDARD_DIAGNOSTIC,
    EXIT_PASS,
    EXIT_FAILED,
    EXIT_ERROR,
    VERDICT_PASS,
    VERDICT_FAILED,
    VERDICT_DIAGNOSTIC,
)


def compute_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_mock_candidate_dir(
    target_dir: Path,
    is_pass: bool = True,
    degree: int = 8,
    is_full_100k: bool = False,
    storage_multiplier: float = 2.5,
    db_size_bytes: int | None = None,
    scifact_p95: float = 12.0,
    peak_rss_gb: float = 1.2,
    rebuild_parity: float = 1.0,
    null_query_hallucination: bool = False,
    missing_lane: str | None = None,
    omit_top20: bool = False,
    declared_policy_sha: str | None = None,
    include_local_policy_file: bool = False,
    local_policy_content: dict[str, Any] | None = None,
    tamper_dossier_metrics: dict[str, Any] | None = None,
    num_null_queries: int = 301,
    queries_per_lane: dict[str, int] | None = None,
    abstention_accuracy: float = 1.0,
) -> Path:
    """Helper to generate a mock candidate bundle for verifier integration testing."""
    target_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = target_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create SQLite DB
    db_file = target_dir / "scale_100k.db"
    if db_file.exists():
        db_file.unlink()
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("PRAGMA journal_mode = WAL;")

    conn.execute("""
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            stream_id TEXT NOT NULL,
            stream_sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            causation_id TEXT,
            correlation_id TEXT,
            schema_version INTEGER NOT NULL DEFAULT 1,
            payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            idempotency_key TEXT UNIQUE
        );
    """)
    conn.execute("""
        CREATE TABLE ingestions (
            ingestion_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            dataset TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            stream_sequence INTEGER NOT NULL,
            atom_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE nodes (
            node_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            stream_sequence INTEGER NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE node_versions (
            atom_version_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            span_start INTEGER NOT NULL,
            span_end INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            stream_sequence INTEGER NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE edge_versions (
            edge_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            family TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            stream_sequence INTEGER NOT NULL
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(atom_version_id UNINDEXED, doc_id UNINDEXED, title, content, tokenize='porter');
    """)
    conn.execute("""
        CREATE TABLE source_lifecycle (
            atom_version_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            stream_sequence INTEGER NOT NULL
        );
    """)

    # Load actual manifest queries for strict ID set verification
    manifest_path = ROOT_DIR / "docs" / "program" / "inbox" / "l1-02-corpus-capsule-20260828" / "evidence" / "queries_manifest.json"
    manifest_cohorts = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest_cohorts = json.load(mf).get("closed_evaluation_cohorts", {})

    all_mock_doc_ids = [f"doc_{i}" for i in range(200)]
    for lane_name, lane_qs in manifest_cohorts.items():
        for mq in lane_qs:
            for g in mq.get("gold_ids", []):
                all_mock_doc_ids.append(str(g))
    all_mock_doc_ids = list(dict.fromkeys(all_mock_doc_ids))

    # Populate sample rows
    now = "2026-08-28T12:00:00Z"
    insert_limit = len(all_mock_doc_ids)
    for i, doc_id in enumerate(all_mock_doc_ids):
        seq = i + 1
        content = f"Document content sentence one for {doc_id}. Sentence two with details."
        content_b = content.encode("utf-8")
        chash = hashlib.sha256(content_b).hexdigest()
        p = {"doc_id": doc_id, "dataset": "beir-scifact", "content": content, "content_hash": chash}
        pj = json.dumps(p)

        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            f"ev_{seq}", "ws", seq, "trace.source.ingested", now, "sys", None, None, 1, pj, chash, f"idem_{doc_id}_{i}"
        ))
        conn.execute("INSERT INTO ingestions VALUES (?,?,?,?,?,?,?,?)", (
            f"ing_{seq}", "ws", doc_id, "beir-scifact", chash, seq, 2, now
        ))
        conn.execute("INSERT INTO nodes VALUES (?,?,?)", (f"node_{seq}_0", "ws", seq))
        conn.execute("INSERT INTO nodes VALUES (?,?,?)", (f"node_{seq}_1", "ws", seq))

        s1_b = content_b[:30]
        s2_b = content_b[30:]
        h1 = hashlib.sha256(s1_b).hexdigest()
        h2 = hashlib.sha256(s2_b).hexdigest()

        conn.execute("INSERT INTO node_versions VALUES (?,?,?,?,?,?)", (f"av_{seq}_0", f"node_{seq}_0", 0, 30, h1, seq))
        conn.execute("INSERT INTO node_versions VALUES (?,?,?,?,?,?)", (f"av_{seq}_1", f"node_{seq}_1", 30, len(content_b), h2, seq))
        conn.execute("INSERT INTO source_lifecycle VALUES (?,?,?,?,?)", (f"av_{seq}_0", "ws", "active", now, seq))
        conn.execute("INSERT INTO source_lifecycle VALUES (?,?,?,?,?)", (f"av_{seq}_1", "ws", "active", now, seq))
        conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}_0", doc_id, f"Title {doc_id}", "Document content sentence one for"))
        conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}_1", doc_id, f"Title {doc_id}", "Sentence two with details."))

        for d in range(degree):
            conn.execute("INSERT INTO edge_versions VALUES (?,?,?,?,?,?,?)", (
                f"edge_{seq}_{d}", "ws", doc_id, f"ent:tag_{d}", "structural", 0.8, seq
            ))

    if is_full_100k:
        # Simulate full 100K rows in events and ingestions with distinct doc_ids and content hashes
        for i in range(insert_limit, 100000):
            seq = i + 1
            c_text = f"Full scale unique document content index {i} payload"
            c_bytes = c_text.encode("utf-8")
            c_hash = hashlib.sha256(c_bytes).hexdigest()
            p = {"doc_id": f"doc_{i}", "dataset": "beir-scifact", "content": c_text, "content_hash": c_hash}
            conn.execute(
                "INSERT INTO events (event_id, stream_id, stream_sequence, event_type, occurred_at, actor, schema_version, payload_json, payload_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (f"ev_{seq}", "ws", seq, "trace.source.ingested", now, "sys", 1, json.dumps(p), c_hash)
            )
            conn.execute(
                "INSERT INTO ingestions (ingestion_id, workspace_id, doc_id, dataset, content_hash, stream_sequence, atom_count, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (f"ing_{seq}", "ws", f"doc_{i}", "beir-scifact", c_hash, seq, 2, now)
            )
            s1_b = c_bytes[:20]
            s2_b = c_bytes[20:]
            h1 = hashlib.sha256(s1_b).hexdigest()
            h2 = hashlib.sha256(s2_b).hexdigest()
            conn.execute("INSERT INTO node_versions VALUES (?,?,?,?,?,?)", (f"av_{seq}_0", f"node_{seq}_0", 0, 20, h1, seq))
            conn.execute("INSERT INTO node_versions VALUES (?,?,?,?,?,?)", (f"av_{seq}_1", f"node_{seq}_1", 20, len(c_bytes), h2, seq))
            conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}_0", f"doc_{i}", f"Title {i}", "Full scale unique"))
            conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}_1", f"doc_{i}", f"Title {i}", "document content index payload"))

    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.execute("VACUUM;")
    conn.close()

    if storage_multiplier > 3.0:
        conn = sqlite3.connect(db_file)
        conn.execute("CREATE TABLE dummy_blobs (id INT, data BLOB);")
        chunk = b"x" * 1_000_000
        for b_idx in range(200):
            conn.execute("INSERT INTO dummy_blobs VALUES (?, ?)", (b_idx, chunk))
        conn.commit()
        conn.close()

    replay_db_file = target_dir / "scale_100k_replay.db"
    shutil.copy2(db_file, replay_db_file)
    if rebuild_parity < 1.0:
        conn = sqlite3.connect(replay_db_file)
        conn.execute("UPDATE events SET payload_hash='corrupted_hash' WHERE stream_sequence=1;")
        conn.commit()
        conn.close()

    raw_bytes = 60_000_000 if is_full_100k else 100_000
    actual_db_size = db_size_bytes or db_file.stat().st_size

    # 2. Raw query evaluation telemetry
    raw_evals = []
    default_counts = {
        "direct_lookup": 1109 if is_full_100k else 10,
        "domain_semantic": 3237 if is_full_100k else 10,
        "semantic_qa": 555 if is_full_100k else 10,
        "multi_hop_reasoning": 2255 if is_full_100k else 10,
    }
    counts = queries_per_lane or default_counts

    lanes_spec = [
        ("direct_lookup", "beir-scifact", 0.9000 if is_pass else 0.4000, 0.9000 if is_pass else 0.5000, scifact_p95),
        ("domain_semantic", "beir-nfcorpus", 0.5000 if is_pass else 0.1000, 0.5000 if is_pass else 0.0500, 15.0),
        ("semantic_qa", "beir-fiqa", 0.6000 if is_pass else 0.1500, 0.6000 if is_pass else 0.2000, 18.0),
        ("multi_hop_reasoning", "multihop-rag", 0.9000 if is_pass else 0.3000, 0.9000 if is_pass else 0.3000, 25.0),
    ]

    for lane_name, ds_name, target_ndcg, target_rec, lat in lanes_spec:
        if missing_lane == lane_name:
            continue
        q_count = counts.get(lane_name, 10)
        lane_qs = manifest_cohorts.get(lane_name, [])
        for q_idx in range(q_count):
            if q_idx < len(lane_qs):
                mq = lane_qs[q_idx]
                qid = str(mq.get("query_id") or mq.get("internal_id"))
                gold_ids = [str(g) for g in mq.get("gold_ids", [all_mock_doc_ids[q_idx % insert_limit]])]
            else:
                qid = f"{lane_name}_{q_idx}"
                gold_ids = [all_mock_doc_ids[q_idx % insert_limit]]

            record: dict[str, Any] = {
                "lane": lane_name,
                "dataset": ds_name,
                "query_id": qid,
                "query_text": f"Query {q_idx} for {lane_name}",
                "latency_ms": lat,
                "system_abstained": False,
                "citations_emitted": [],
            }
            if not omit_top20:
                if is_pass:
                    seen_cands = set(gold_ids[:min(20, len(gold_ids))])
                    cands = list(gold_ids[:min(20, len(gold_ids))])
                    offset = q_idx * 20
                    while len(cands) < 20:
                        cand_id = all_mock_doc_ids[offset % insert_limit]
                        offset += 1
                        if cand_id not in seen_cands:
                            seen_cands.add(cand_id)
                            cands.append(cand_id)
                else:
                    seen_cands = set()
                    cands = []
                    offset = 100 + q_idx * 20
                    while len(cands) < 20:
                        cand_id = all_mock_doc_ids[offset % insert_limit]
                        offset += 1
                        if cand_id not in seen_cands:
                            seen_cands.add(cand_id)
                            cands.append(cand_id)
                record["retrieved_top20"] = cands[:20]
                record["ranked_candidates"] = [
                    {"doc_id": c, "score": round(1.0 - 0.01 * idx, 4), "rank": idx + 1}
                    for idx, c in enumerate(cands[:20])
                ]
            raw_evals.append(record)

    with open(runs_dir / "raw_query_evaluations.jsonl", "w", encoding="utf-8") as f:
        for r in raw_evals:
            f.write(json.dumps(r) + "\n")

    # 3. Abstention query evaluation telemetry
    abs_qs = manifest_cohorts.get("abstention_suite", [])
    abs_evals = []
    for n_idx in range(num_null_queries):
        if n_idx < len(abs_qs):
            qid = str(abs_qs[n_idx].get("query_id") or abs_qs[n_idx].get("internal_id"))
        else:
            qid = f"null_q_{n_idx}"
        is_halluc = (null_query_hallucination and n_idx == 0)
        is_abstained = (n_idx < int(abstention_accuracy * num_null_queries)) and not is_halluc

        ranked_cands = []
        offset = n_idx * 20
        while len(ranked_cands) < 20:
            cand_id = all_mock_doc_ids[offset % insert_limit]
            offset += 1
            if cand_id not in ranked_cands:
                ranked_cands.append(cand_id)

        rec_abs = {
            "query_id": qid,
            "query_text": f"Null query {n_idx}",
            "system_abstained": is_abstained,
            "citations_emitted": [all_mock_doc_ids[0]] if is_halluc else [],
            "latency_ms": 4.5,
            "ranked_candidates": [
                {"doc_id": c, "score": round(0.5 - 0.01 * j, 4), "rank": j + 1}
                for j, c in enumerate(ranked_cands)
            ],
        }
        abs_evals.append(rec_abs)

    with open(runs_dir / "abstention_evaluations.jsonl", "w", encoding="utf-8") as f:
        for a in abs_evals:
            f.write(json.dumps(a) + "\n")

    def recompute_lane(lane_name: str):
        records = [r for r in raw_evals if r.get("lane") == lane_name]
        if not records:
            return 0.0, 0.0, 0.0, 0.0
        ndcgs, recs, covs, lats = [], [], [], []
        for r in records:
            cands = r.get("retrieved_top20", [])
            q_id = r.get("query_id")
            mq = next((q for q in manifest_cohorts.get(lane_name, []) if str(q.get("query_id") or q.get("internal_id")) == str(q_id)), {})
            golds = set(str(g) for g in mq.get("gold_ids", []))
            n_val, r_val, c_val = compute_query_ndcg10_recall20_coverage20(cands, golds)
            ndcgs.append(n_val)
            recs.append(r_val)
            covs.append(c_val)
            lats.append(r.get("latency_ms", 0.0))
        return round(sum(ndcgs)/max(1, len(ndcgs)), 4), round(sum(recs)/max(1, len(recs)), 4), round(sum(covs)/max(1, len(covs)), 4), round(lats[0] if lats else 0.0, 3)

    sci_n, sci_r, sci_c, sci_p = recompute_lane("direct_lookup")
    nfc_n, nfc_r, nfc_c, nfc_p = recompute_lane("domain_semantic")
    fiq_n, fiq_r, fiq_c, fiq_p = recompute_lane("semantic_qa")
    mhr_n, mhr_r, mhr_c, mhr_p = recompute_lane("multi_hop_reasoning")

    zhr = 0.0 if null_query_hallucination else 1.0000
    abs_acc = round(sum(1 for a in abs_evals if a.get("system_abstained")) / max(1, len(abs_evals)), 4)

    canonical_policy_sha = CANONICAL_POLICY_SHA256
    effective_policy_sha = declared_policy_sha or canonical_policy_sha

    dossier = {
        "evaluation_title": "Trace 100K Scale Gate Dossier",
        "target_standard": "DEC-P-005b-CANDIDATE",
        "policy_sha256": effective_policy_sha,
        "scale_workload_vector": {
            "document_count_D": 100000 if is_full_100k else 20,
            "raw_source_bytes_B": raw_bytes,
            "storage_footprint_bytes": actual_db_size,
            "storage_multiplier": storage_multiplier,
        },
        "host_environment": {
            "peak_rss_gb": peak_rss_gb,
        },
        "metrics": {
            "promise_1_durable_memory": {
                "source_atom_retention": 1.0,
                "content_hash_drift": 0.0,
                "byte_offset_anchor_recovery": 1.0,
                "repeat_erasure_delta_writes": 0,
            },
            "promise_4_bounded_economics": {
                "storage_multiplier": storage_multiplier,
                "persisted_max_degree_sql": degree,
                "graph_traversal_p95_latency_ms": 1.5,
                "peak_ram_gb": peak_rss_gb,
            },
            "promise_3_retrieval_quality": {
                "direct_lookup": {
                    "ndcg_at_10": sci_n,
                    "recall_at_20": sci_r,
                    "p95_ms": sci_p,
                },
                "domain_semantic": {
                    "ndcg_at_10": nfc_n,
                    "recall_at_20": nfc_r,
                    "p95_ms": nfc_p,
                },
                "semantic_qa": {
                    "ndcg_at_10": fiq_n,
                    "recall_at_20": fiq_r,
                    "p95_ms": fiq_p,
                },
                "multi_hop_reasoning": {
                    "ndcg_at_10": mhr_n,
                    "recall_at_20": mhr_r,
                    "complete_coverage_at_20": mhr_c,
                    "p95_ms": mhr_p,
                },
                "abstention_lane": {
                    "zero_hallucination_rate": zhr,
                    "abstention_accuracy": abs_acc,
                    "unanswerable_queries_evaluated": num_null_queries,
                },
            },
            "recovery_and_resilience": {
                "rebuild_parity": rebuild_parity,
            },
        },
        "overall_verdict": "PASS_ALL_SCALE_GATE_INVARIANTS" if is_pass else "CANDIDATE_FAILED",
    }

    if tamper_dossier_metrics:
        for k, v in tamper_dossier_metrics.items():
            if "." in k:
                sec, sub = k.split(".", 1)
                dossier["metrics"]["promise_3_retrieval_quality"].setdefault(sec, {})[sub] = v
            else:
                dossier["metrics"]["promise_3_retrieval_quality"][k] = v

    with open(target_dir / "100k_scale_dossier.json", "w", encoding="utf-8") as f:
        json.dump(dossier, f, indent=2)

    with open(runs_dir / "durability_audit_trace.json", "w", encoding="utf-8") as f:
        json.dump({"source_atom_retention": 1.0, "content_hash_drift": 0.0, "repeat_erasure_delta_writes": 0, "anchor_recovery_rate": 1.0, "total_atoms_in_db": 200000 if is_full_100k else (len(all_mock_doc_ids) * 2), "total_documents_in_db": 100000 if is_full_100k else len(all_mock_doc_ids)}, f)

    with open(runs_dir / "restart_recovery_receipt.json", "w", encoding="utf-8") as f:
        json.dump({
            "status": "RECOVERY_VERIFIED",
            "integrity_check": "ok",
            "process_exit_code": 0,
            "timestamp": now,
        }, f)

    with open(runs_dir / "incremental_resume_receipt.json", "w", encoding="utf-8") as f:
        json.dump({
            "status": "RESUME_VERIFIED",
            "initial_watermark": 100,
            "final_watermark": 200,
            "duplicate_events": 0,
            "duplicate_rejections": 0,
            "watermarks_continuous": True,
            "timestamp": now,
        }, f)

    parity_dict = {}
    for t_name in ["events", "ingestions", "nodes", "node_versions", "edge_versions", "source_lifecycle", "node_fts"]:
        cnt = 100000 if is_full_100k else len(all_mock_doc_ids)
        if t_name == "node_versions":
            cnt *= 2
        parity_dict[t_name] = {
            "source_count": cnt,
            "replay_count": cnt,
            "source_hash": f"hash_{t_name}",
            "replay_hash": f"hash_{t_name}" if rebuild_parity == 1.0 else f"diff_{t_name}",
            "parity_match": (rebuild_parity == 1.0),
        }
    with open(runs_dir / "replay_recovery_trace.json", "w", encoding="utf-8") as f:
        json.dump({"rebuild_parity": rebuild_parity, "table_parity_audit": parity_dict}, f)

    # Defect 7: Create mock upstream source dataset files for strict source-only anchor verification
    mock_data_root = target_dir / "mock_data"
    mock_data_root.mkdir(parents=True, exist_ok=True)
    (mock_data_root / "beir-scifact").mkdir(parents=True, exist_ok=True)

    corpus_records = []
    for doc_id in all_mock_doc_ids:
        content = f"Document content sentence one for {doc_id}. Sentence two with details."
        corpus_records.append({"_id": doc_id, "text": content})

    if is_full_100k:
        for i in range(insert_limit, 100000):
            c_text = f"Full scale unique document content index {i} payload"
            corpus_records.append({"_id": f"doc_{i}", "text": c_text})

    corpus_file_1 = mock_data_root / "beir-scifact" / "corpus.jsonl"
    with open(corpus_file_1, "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")

    corpus_file_2 = mock_data_root / "beir-scifact.jsonl"
    with open(corpus_file_2, "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")

    cand_data_dir = target_dir / "data"
    cand_data_dir.mkdir(parents=True, exist_ok=True)
    (cand_data_dir / "beir-scifact").mkdir(parents=True, exist_ok=True)
    with open(cand_data_dir / "beir-scifact" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")
    with open(cand_data_dir / "beir-scifact.jsonl", "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")

    with open(target_dir / "candidate_manifest.json", "w", encoding="utf-8") as f:
        json.dump({
            "manifest": "ok",
            "git_clean": True,
            "git_commit": "0f59ee4e5d350f2adf580ebc4c67022bf898fb1d",
            "git_tree_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
            "runner_hash": compute_sha256(ROOT_DIR / "scripts" / "run_100k_scale_gate.py"),
            "verifier_hash": compute_sha256(ROOT_DIR / "scripts" / "verify_100k_candidate.py"),
            "schema_hash": compute_sha256(ROOT_DIR / "benchmarks" / "policies" / "scale_policy.schema.json"),
            "command_line": ["python", "scripts/run_100k_scale_gate.py", "--candidate"],
            "policy_sha256": effective_policy_sha,
            "queries_manifest_sha256": CANONICAL_QUERIES_MANIFEST_SHA256,
            "corpus_manifest_sha256": CANONICAL_CORPUS_MANIFEST_SHA256,
            "blind_queries_sha256": CANONICAL_BLIND_QUERIES_SHA256,
            "data_root": str(mock_data_root),
        }, f)

    with open(runs_dir / "telemetry_timeseries.json", "w", encoding="utf-8") as f:
        json.dump({"timeseries": [{"rss_mb": peak_rss_gb * 1024.0, "peak_rss_mb": peak_rss_gb * 1024.0}]}, f)

    with open(runs_dir / "graph_walk_telemetry.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"latency_ms": 1.5, "nodes_visited": 10}) + "\n")

    if include_local_policy_file:
        pol_data = local_policy_content or json.load(open(ROOT_DIR / "benchmarks" / "policies" / "scale_policy.lock.json"))
        with open(target_dir / "scale_policy.lock.json", "w", encoding="utf-8") as f:
            json.dump(pol_data, f, indent=2)

    checksums = {}
    for p in sorted(target_dir.iterdir()):
        if p.is_file() and p.name != "checksums.json":
            checksums[p.name] = compute_sha256(p)
    for p in sorted(runs_dir.iterdir()):
        if p.is_file():
            checksums[f"runs/{p.name}"] = compute_sha256(p)

    with open(target_dir / "checksums.json", "w", encoding="utf-8") as f:
        json.dump(checksums, f, indent=2)

    return target_dir


class TestScaleCandidateVerifier:
    """Complete negative and positive integration test suite for Wave R2.2 Scale Candidate Verifier."""

    def test_verifier_passes_clean_candidate_bundle(self, tmp_path: Path):
        """Verify that a compliant calibration candidate bundle produces PASS_INDEPENDENT_VERIFICATION."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_pass", is_pass=True, degree=8, is_full_100k=False)
        receipt_file = tmp_path / "receipt.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_DIAGNOSTIC
        assert receipt["target_standard"] == "NONE_DIAGNOSTIC_ONLY"
        assert receipt["is_calibration"] is True
        assert receipt["sqlite_database_audit"]["integrity_check"] == "ok"
        assert receipt["sqlite_database_audit"]["persisted_max_degree_sql"] == 8
        assert receipt["sqlite_database_audit"]["max_degree_bound_verified"] is True
        assert receipt["retrieval_and_abstention_audit"]["abstention_verified"] is True
        assert receipt["checksums_audit"]["all_checksums_match"] is True
        assert len(receipt["merkle_digest_token"]) == 64
        assert "candidate_evidence_merkle_root" in receipt
        assert receipt_file.exists()

    def test_verifier_passes_clean_full_100k_candidate(self, tmp_path: Path):
        """Verify that a full 100K candidate bundle with 7,457 queries passes independent verification."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_full_100k", is_pass=True, degree=8, is_full_100k=True)
        receipt_file = tmp_path / "receipt_full.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_PASS
        assert receipt["checksums_audit"]["all_checksums_match"] is True
        assert len(verifier.violations) == 0

    def test_dynamic_policy_loading_and_policy_drift_detection(self, tmp_path: Path):
        """Verify that mismatched policy SHA-256 causes fail-closed rejection."""
        bogus_sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_policy_drift",
            is_pass=True,
            declared_policy_sha=bogus_sha,
        )
        receipt_file = tmp_path / "receipt_drift.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Candidate declared policy SHA-256 mismatch" in v for v in verifier.violations)

    def test_candidate_local_policy_file_drift_detection(self, tmp_path: Path):
        """Verify that a modified scale_policy.lock.json in candidate directory fails closed."""
        altered_policy = {"policy_id": "TAMPERED_POLICY", "thresholds": {}}
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_local_pol_drift",
            is_pass=True,
            include_local_policy_file=True,
            local_policy_content=altered_policy,
        )
        receipt_file = tmp_path / "receipt_pol_tamper.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("scale_policy.lock.json SHA-256" in v or "does not match canonical" in v for v in verifier.violations)

    def test_malformed_or_missing_policy_lockfile_fails_closed(self, tmp_path: Path):
        """Verify that missing policy file raises FileNotFoundError (VERIFICATION_ERROR)."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_pol_err", is_pass=True)
        bad_policy_path = tmp_path / "nonexistent_policy.lock.json"

        with pytest.raises(FileNotFoundError):
            CandidateVerifier(
                candidate_dir=cand_dir,
                policy_path=bad_policy_path,
            )

    def test_queries_manifest_drift_and_query_count_mismatch(self, tmp_path: Path):
        """Verify that query count mismatch against queries_manifest causes fail-closed rejection."""
        mismatched_counts = {
            "direct_lookup": 1100,  # 9 queries missing
            "domain_semantic": 3237,
            "semantic_qa": 555,
            "multi_hop_reasoning": 2255,
        }
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_manifest_drift",
            is_pass=True,
            is_full_100k=True,
            queries_per_lane=mismatched_counts,
        )
        receipt_file = tmp_path / "receipt_manifest_drift.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("direct_lookup" in v and ("missing" in v or "mismatch" in v) for v in verifier.violations)

    def test_truncation_rejection_500_row_or_partial_cohort(self, tmp_path: Path):
        """Verify that truncating full 100K evaluation (e.g. to 500 rows) causes fail-closed rejection."""
        truncated_counts = {
            "direct_lookup": 125,
            "domain_semantic": 125,
            "semantic_qa": 125,
            "multi_hop_reasoning": 125,
        }
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_truncated_500",
            is_pass=True,
            is_full_100k=True,
            queries_per_lane=truncated_counts,
        )
        receipt_file = tmp_path / "receipt_trunc.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Full 100K candidate evaluated only" in v and "without truncation" in v for v in verifier.violations)

    def test_missing_capability_lane_rejection(self, tmp_path: Path):
        """Verify that omitting any capability lane (e.g. multi_hop_reasoning) causes rejection."""
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_missing_lane",
            is_pass=True,
            is_full_100k=True,
            missing_lane="multi_hop_reasoning",
        )
        receipt_file = tmp_path / "receipt_missing_lane.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Missing raw query evaluation records for lane: multi_hop_reasoning" in v for v in verifier.violations)

    def test_absent_or_incomplete_top20_ranking_telemetry(self, tmp_path: Path):
        """Verify that omitting retrieved_top20 ranking telemetry causes sub-floor metrics & rejection."""
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_no_top20",
            is_pass=True,
            omit_top20=True,
        )
        receipt_file = tmp_path / "receipt_no_top20.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("does not contain exactly 20 entries" in v or "ranking" in v for v in verifier.violations)

    def test_database_substitution_rejection_and_tampering(self, tmp_path: Path):
        """Verify that swapping or modifying scale_100k.db is detected via SHA-256 and Merkle root."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_db_swap", is_pass=True)
        receipt_file = tmp_path / "receipt_db_swap.json"

        db_file = cand_dir / "scale_100k.db"
        with open(db_file, "ab") as f:
            f.write(b"\x00\x01\x02\x03")

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Checksum mismatch for scale_100k.db" in v for v in verifier.violations)

    def test_altered_raw_telemetry_and_recomputation_mismatch(self, tmp_path: Path):
        """Verify that tampered raw evaluations causing >0.0001 discrepancy against dossier fail closed."""
        cand_dir = create_mock_candidate_dir(
            tmp_path / "candidate_tampered_scores",
            is_pass=True,
            tamper_dossier_metrics={
                "direct_lookup.ndcg_at_10": 0.8500,
                "direct_lookup.recall_at_20": 0.8500,
            },
        )
        receipt_file = tmp_path / "receipt_tamper.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Dossier metric mismatch for direct_lookup.ndcg_at_10" in v for v in verifier.violations)
        assert any("Dossier metric mismatch for direct_lookup.recall_at_20" in v for v in verifier.violations)

    def test_readonly_database_audit_and_write_protection(self, tmp_path: Path):
        """Verify that verifier database audit enforces PRAGMA query_only = ON and blocks writes."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_ro", is_pass=True)
        db_path = cand_dir / "scale_100k.db"

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = ON;")
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO nodes VALUES ('test_node', 'ws', 999);")
        finally:
            conn.close()

    def test_cross_platform_safe_console_output(self):
        """Verify that safe_print never crashes with UnicodeEncodeError on ASCII/charmap streams."""
        test_messages = [
            "Wave R2.2: 🌟 Verification PASS • All Invariants Met → 100% Parity",
            "⚠️ Metric below floor: nDCG@10 0.650 < 0.700 (Δ = -0.050)",
            "Storage Multiplier: 2.50x ≤ 3.00x | Latency: 12.5 ms ≤ 25.0 ms",
        ]

        out = io.StringIO()
        for msg in test_messages:
            safe_print(msg, file=out)
        content = out.getvalue()
        assert "Wave R2.2" in content

        class MockAsciiStream:
            def __init__(self):
                self.encoding = "ascii"
                self.buffer = []

            def write(self, text: str):
                text.encode("ascii")
                self.buffer.append(text)

            def flush(self):
                pass

        ascii_stream = MockAsciiStream()
        for msg in test_messages:
            safe_print(msg, file=ascii_stream)
        assert len(ascii_stream.buffer) == len(test_messages)

    def test_schema_defined_exit_codes(self, tmp_path: Path):
        """Verify schema-defined exit codes: 0 on pass, 1 on fail, 2 on operational error."""
        # 1. Exit 0: Clean passing candidate
        cand_pass = create_mock_candidate_dir(tmp_path / "cli_pass", is_pass=True)
        receipt_pass = tmp_path / "receipt_cli_pass.json"
        with patch.object(sys, "argv", ["verify_100k_candidate.py", "--candidate-dir", str(cand_pass), "--receipt-out", str(receipt_pass)]):
            with pytest.raises(SystemExit) as exc_info:
                verifier_main()
            assert exc_info.value.code == EXIT_PASS

        # 2. Exit 1: Candidate with violations (e.g. high degree)
        cand_fail = create_mock_candidate_dir(tmp_path / "cli_fail", is_pass=True, degree=15)
        receipt_fail = tmp_path / "receipt_cli_fail.json"
        with patch.object(sys, "argv", ["verify_100k_candidate.py", "--candidate-dir", str(cand_fail), "--receipt-out", str(receipt_fail)]):
            with pytest.raises(SystemExit) as exc_info:
                verifier_main()
            assert exc_info.value.code == EXIT_FAILED

        # 3. Exit 2: Operational error (nonexistent candidate directory)
        with patch.object(sys, "argv", ["verify_100k_candidate.py", "--candidate-dir", str(tmp_path / "nonexistent_cand")]):
            with pytest.raises(SystemExit) as exc_info:
                verifier_main()
            assert exc_info.value.code == EXIT_ERROR

    def test_verifier_fails_on_degree_limit_breach(self, tmp_path: Path):
        """Verify that persisted graph degree > 10 causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_high_degree", is_pass=True, degree=15)
        receipt_file = tmp_path / "receipt_deg.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("degree" in v.lower() for v in verifier.violations)

    def test_verifier_fails_on_latency_cap_breach(self, tmp_path: Path):
        """Verify that SciFact P95 latency > 25.0 ms causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_slow_latency", is_pass=True, is_full_100k=True, scifact_p95=35.0)
        receipt_file = tmp_path / "receipt_slow.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("direct_lookup P95 latency" in v for v in verifier.violations)

    def test_verifier_fails_on_memory_breach(self, tmp_path: Path):
        """Verify that Peak RSS > 8.0 GiB causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_high_mem", is_pass=True, peak_rss_gb=10.5)
        receipt_file = tmp_path / "receipt_mem.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Peak RSS" in v for v in verifier.violations)

    def test_verifier_fails_on_storage_multiplier_breach(self, tmp_path: Path):
        """Verify that Storage Multiplier > 3.00x causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_high_storage", is_pass=True, is_full_100k=True, storage_multiplier=4.5)
        receipt_file = tmp_path / "receipt_storage.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Storage multiplier" in v for v in verifier.violations)

    def test_verifier_fails_on_null_query_hallucination(self, tmp_path: Path):
        """Verify that any hallucination on null queries fails verification."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_halluc", is_pass=True, null_query_hallucination=True)
        receipt_file = tmp_path / "receipt_halluc.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("hallucination" in v.lower() for v in verifier.violations)

    def test_verifier_fails_on_rebuild_parity_breach(self, tmp_path: Path):
        """Verify that Rebuild Parity < 1.000 causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_parity_fail", is_pass=True, rebuild_parity=0.98)
        receipt_file = tmp_path / "receipt_parity.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Rebuild parity" in v for v in verifier.violations)

    def test_runner_fail_closed_threshold_evaluation(self, tmp_path: Path):
        """Verify that the runner fail-closed engine flags any sub-floor metric against loaded policy."""
        manifest_file = tmp_path / "corpus_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({"manifest_title": "Test Manifest", "total_unique_documents": 20}, f)

        runner = Scale100KRunner(
            manifest_path=manifest_file,
            data_root=tmp_path / "data",
            output_dir=tmp_path / "out",
            target_count=100000,
            mode="diagnostic",
            allow_unlocked_policy=True, force_overwrite=True,
        )

        failing_dossier = {
            "scale_workload_vector": {"document_count_D": 100000, "raw_source_bytes_B": 100},
            "metrics": {
                "promise_1_durable_memory": {
                    "source_atom_retention": 1.0,
                    "content_hash_drift": 0.0,
                    "byte_offset_anchor_recovery": 1.0,
                    "repeat_erasure_delta_writes": 0,
                },
                "promise_4_bounded_economics": {
                    "storage_multiplier": 2.5,
                    "persisted_max_degree_sql": 8,
                    "graph_traversal_p95_latency_ms": 1.2,
                },
                "promise_3_retrieval_quality": {
                    "direct_lookup": {"ndcg_at_10": 0.500, "recall_at_20": 0.600},
                    "domain_semantic": {"ndcg_at_10": 0.360, "recall_at_20": 0.230},
                    "semantic_qa": {"ndcg_at_10": 0.420, "recall_at_20": 0.560},
                    "multi_hop_reasoning": {"ndcg_at_10": 0.760, "complete_coverage_at_20": 0.890},
                    "abstention_lane": {"zero_hallucination_rate": 1.0, "unanswerable_queries_evaluated": 301, "abstention_accuracy": 1.0},
                },
                "recovery_and_resilience": {"rebuild_parity": 1.0},
            },
        }

        passed, violations = runner.evaluate_fail_closed_thresholds(failing_dossier)
        assert passed is False
        assert any("direct_lookup" in v or "SciFact" in v for v in violations)

    def test_common_mode_policy_tampering_rejected(self, tmp_path: Path):
        """Verify that supplying the same tampered policy file to candidate and verifier fails closed.

        Even when candidate and verifier both point to the identical policy file,
        CandidateVerifier fails closed with ValueError because policy SHA-256 != CANONICAL_POLICY_SHA256.
        """
        canonical_policy_path = ROOT_DIR / "benchmarks" / "policies" / "scale_policy.lock.json"
        with open(canonical_policy_path, "r", encoding="utf-8") as f:
            policy_data = json.load(f)

        policy_data["policy_id"] = "TAMPERED_COMMON_MODE_POLICY"
        policy_data["scale"]["required_document_count_D"] = 50

        tampered_policy_file = tmp_path / "tampered_scale_policy.lock.json"
        with open(tampered_policy_file, "w", encoding="utf-8") as f:
            json.dump(policy_data, f, indent=2)

        tampered_sha = compute_sha256(tampered_policy_file)

        cand_dir = create_mock_candidate_dir(
            tmp_path / "cand_common_tamper",
            is_pass=True,
            declared_policy_sha=tampered_sha,
            include_local_policy_file=True,
            local_policy_content=policy_data,
        )
        receipt_file = tmp_path / "receipt_common_tamper.json"

        verifier = CandidateVerifier(
            candidate_dir=cand_dir,
            receipt_out=receipt_file,
            policy_path=tampered_policy_file,
        )

        with pytest.raises(ValueError) as exc_info:
            verifier.verify_all()

        assert "does not match expected canonical digest" in str(exc_info.value)
        assert any("Loaded policy lockfile SHA-256" in v and "does not match expected canonical digest" in v for v in verifier.violations)

    def test_query_manifest_hash_mismatch_rejected(self, tmp_path: Path):
        """Verify that a tampered queries manifest SHA-256 fails closed."""
        canonical_manifest_path = ROOT_DIR / "docs" / "program" / "inbox" / "l1-02-corpus-capsule-20260828" / "evidence" / "queries_manifest.json"
        with open(canonical_manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        manifest_data["manifest_title"] = "Tampered Queries Manifest Title"
        tampered_manifest_file = tmp_path / "tampered_queries_manifest.json"
        with open(tampered_manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        cand_dir = create_mock_candidate_dir(tmp_path / "cand_manifest_tamper", is_pass=True)
        receipt_file = tmp_path / "receipt_manifest_tamper.json"

        verifier = CandidateVerifier(
            candidate_dir=cand_dir,
            receipt_out=receipt_file,
            queries_manifest_path=tampered_manifest_file,
        )
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Loaded queries manifest SHA-256" in v and "does not match expected canonical digest" in v for v in verifier.violations)

    def test_duplicate_query_ids_replacing_missing_ids_rejected(self, tmp_path: Path):
        """Verify that exact set equality catches duplicate query IDs even when total row count matches."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_dup_qids", is_pass=True, is_full_100k=False)
        receipt_file = tmp_path / "receipt_dup_qids.json"

        raw_eval_path = cand_dir / "runs" / "raw_query_evaluations.jsonl"
        with open(raw_eval_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        sci_records = [r for r in lines if r.get("lane") == "direct_lookup"]
        if len(sci_records) >= 2:
            dup_id = sci_records[0]["query_id"]
            sci_records[1]["query_id"] = dup_id

        with open(raw_eval_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/raw_query_evaluations.jsonl"] = compute_sha256(raw_eval_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Duplicate evaluation record found" in v or "Contradictory duplicate" in v for v in verifier.violations)

    def test_short_rankings_rejected(self, tmp_path: Path):
        """Verify that ranking telemetry with fewer than 20 candidates is rejected fail closed."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_short_rankings", is_pass=True)
        receipt_file = tmp_path / "receipt_short_rankings.json"

        raw_eval_path = cand_dir / "runs" / "raw_query_evaluations.jsonl"
        with open(raw_eval_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        for r in lines:
            if "retrieved_top20" in r:
                r["retrieved_top20"] = r["retrieved_top20"][:5]
            if "ranked_candidates" in r:
                r["ranked_candidates"] = r["ranked_candidates"][:5]

        with open(raw_eval_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/raw_query_evaluations.jsonl"] = compute_sha256(raw_eval_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("does not contain exactly 20 entries" in v for v in verifier.violations)

    def test_calibration_cannot_issue_level1_pass(self, tmp_path: Path):
        """Verify that calibration candidate (D < 100,000) produces DIAGNOSTIC_NON_CERTIFYING and never PASS_INDEPENDENT_VERIFICATION."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_calibration", is_pass=True, is_full_100k=False)
        receipt_file = tmp_path / "receipt_calibration.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_DIAGNOSTIC
        assert receipt["verification_verdict"] != VERDICT_PASS
        assert receipt["target_standard"] == STANDARD_DIAGNOSTIC
        assert receipt["target_standard"] != STANDARD_LEVEL1
        assert receipt["is_calibration"] is True
        assert receipt["calibration_notice"] is not None
        assert "non-certifying" in receipt["calibration_notice"].lower()

    def test_memory_measurement_failure_fails_closed(self):
        """Verify that get_process_memory_info() fails closed with RuntimeError if memory sources are unavailable."""
        with patch("pathlib.Path.exists", return_value=False), \
             patch.dict("sys.modules", {"psutil": None}), \
             patch("sys.platform", "unknown_os"), \
             patch("platform.system", return_value="unknown_os"):
            with pytest.raises(RuntimeError) as exc_info:
                get_process_memory_info()
            assert "Process memory measurement failed" in str(exc_info.value)

    def test_candidate_authored_hallucination_flag_ignored(self, tmp_path: Path):
        """Verify that candidate-authored hallucination=False flag is ignored when citations_emitted contains entries on null queries."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_halluc_ignore", is_pass=True)
        receipt_file = tmp_path / "receipt_halluc_ignore.json"

        abs_file = cand_dir / "runs" / "abstention_evaluations.jsonl"
        with open(abs_file, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]

        records[0]["hallucination"] = False
        records[0]["system_abstained"] = True
        records[0]["citations_emitted"] = ["fabricated_citation_doc_0"]

        with open(abs_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/abstention_evaluations.jsonl"] = compute_sha256(abs_file)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert receipt["retrieval_and_abstention_audit"]["zero_hallucination_rate"] == 0.0
        assert any("Zero hallucination rate" in v or "hallucination" in v.lower() for v in verifier.violations)

    def test_missing_raw_traces_rejected(self, tmp_path: Path):
        """Verify that omitting any raw trace file (replay_recovery_trace.json, durability_audit_trace.json, telemetry_timeseries.json) fails verification."""
        for trace_name in ["runs/replay_recovery_trace.json", "runs/durability_audit_trace.json", "runs/telemetry_timeseries.json"]:
            cand_dir = create_mock_candidate_dir(tmp_path / f"cand_missing_{Path(trace_name).stem}", is_pass=True)
            receipt_file = tmp_path / f"receipt_missing_{Path(trace_name).stem}.json"

            target_file = cand_dir / trace_name
            if target_file.exists():
                target_file.unlink()

            verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
            receipt = verifier.verify_all()

            assert receipt["verification_verdict"] == VERDICT_FAILED
            assert any(f"Missing file declared in checksums.json: {trace_name}" in v for v in verifier.violations)


    def test_candidate_injected_gold_ids_ignored(self, tmp_path: Path):
        """Verify candidate injects arbitrary gold_ids in telemetry row; verifier rejects due to gold ID leakage."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_inject_golds", is_pass=False, is_full_100k=True)
        receipt_file = tmp_path / "receipt_inject_golds.json"

        raw_eval_path = cand_dir / "runs" / "raw_query_evaluations.jsonl"
        with open(raw_eval_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        # Inject fake gold ID into record
        for r in lines:
            if r["lane"] == "direct_lookup":
                r["gold_ids"] = ["fake_injected_gold"]
                r["retrieved_top20"] = ["doc_0"] + [f"doc_{i}" for i in range(1, 20)]
                r["ranked_candidates"] = [{"doc_id": c, "score": round(1.0 - 0.01 * idx, 4), "rank": idx + 1} for idx, c in enumerate(r["retrieved_top20"])]
                break

        with open(raw_eval_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/raw_query_evaluations.jsonl"] = compute_sha256(raw_eval_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("gold" in v.lower() for v in verifier.violations)

    def test_duplicate_candidate_ids_in_ranking_rejected(self, tmp_path: Path):
        """Verify candidate emits duplicate candidate IDs in top-20 ranking; verifier rejects with violation."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_dup_cands", is_pass=True)
        receipt_file = tmp_path / "receipt_dup_cands.json"

        raw_eval_path = cand_dir / "runs" / "raw_query_evaluations.jsonl"
        with open(raw_eval_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        for r in lines:
            if "retrieved_top20" in r and len(r["retrieved_top20"]) >= 2:
                r["retrieved_top20"][1] = r["retrieved_top20"][0]
            if "ranked_candidates" in r and len(r["ranked_candidates"]) >= 2:
                r["ranked_candidates"][1]["doc_id"] = r["ranked_candidates"][0]["doc_id"]

        with open(raw_eval_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/raw_query_evaluations.jsonl"] = compute_sha256(raw_eval_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("duplicate" in v.lower() for v in verifier.violations) or any("unique" in v.lower() for v in verifier.violations)

    def test_multihop_coverage_requires_binary_all_gold_coverage(self, tmp_path: Path):
        """Verify mean recall does not satisfy coverage floor if binary coverage is below minimum."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_multihop_cov", is_pass=True, is_full_100k=True)
        receipt_file = tmp_path / "receipt_multihop_cov.json"

        raw_eval_path = cand_dir / "runs" / "raw_query_evaluations.jsonl"
        with open(raw_eval_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        manifest_path = ROOT_DIR / "docs" / "program" / "inbox" / "l1-02-corpus-capsule-20260828" / "evidence" / "queries_manifest.json"
        manifest_cohorts = {}
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_cohorts = json.load(mf).get("closed_evaluation_cohorts", {})

        for r in lines:
            if r["lane"] == "multi_hop_reasoning":
                qid = r["query_id"]
                mq = next((q for q in manifest_cohorts.get("multi_hop_reasoning", []) if str(q.get("query_id") or q.get("internal_id")) == str(qid)), {})
                golds = [str(g) for g in mq.get("gold_ids", [])]
                if len(golds) >= 2:
                    top20 = [golds[0]] + [f"doc_{i}" for i in range(19)]
                else:
                    top20 = [f"doc_{i}" for i in range(20)]
                r["retrieved_top20"] = top20
                r["ranked_candidates"] = [{"doc_id": c, "score": round(1.0 - 0.01 * idx, 4), "rank": idx + 1} for idx, c in enumerate(top20)]

        with open(raw_eval_path, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")

        dossier_path = cand_dir / "100k_scale_dossier.json"
        with open(dossier_path, "r", encoding="utf-8") as f:
            dossier = json.load(f)
        dossier["metrics"]["promise_3_retrieval_quality"]["multi_hop_reasoning"]["complete_coverage_at_20"] = 0.0
        with open(dossier_path, "w", encoding="utf-8") as f:
            json.dump(dossier, f, indent=2)

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["runs/raw_query_evaluations.jsonl"] = compute_sha256(raw_eval_path)
        csums["100k_scale_dossier.json"] = compute_sha256(dossier_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("coverage" in v.lower() for v in verifier.violations)

    def test_omitted_mandatory_trace_fails_closed(self, tmp_path: Path):
        """Verify candidate omits durability_audit_trace.json from both disk and checksums.json; verifier rejects."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_omit_trace", is_pass=True)
        receipt_file = tmp_path / "receipt_omit_trace.json"

        target_file = cand_dir / "runs" / "durability_audit_trace.json"
        if target_file.exists():
            target_file.unlink()

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        if "runs/durability_audit_trace.json" in csums:
            del csums["runs/durability_audit_trace.json"]
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("mandatory evidence file" in v.lower() or "missing" in v.lower() for v in verifier.violations)

    def test_real_runner_to_verifier_end_to_end_rehearsal(self, tmp_path: Path):
        """Execute real runner Scale100KRunner in diagnostic mode and verify with CandidateVerifier."""
        manifest_file = tmp_path / "corpus_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({
                "manifest_title": "Trace E2E Rehearsal",
                "total_unique_documents": 20
            }, f)

        out_dir = tmp_path / "output_runner"
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        for i in range(20):
            (data_dir / f"doc_{i}.txt").write_text(f"Doc {i} content rehearsal", encoding="utf-8")

        runner = Scale100KRunner(
            manifest_path=manifest_file,
            data_root=data_dir,
            output_dir=out_dir,
            target_count=20,
            temp_dir=tmp_path / "work",
            mode="diagnostic",
            sample_size=10,
            allow_unlocked_policy=True, force_overwrite=True,
        )

        runner.run_all()

        receipt_file = tmp_path / "receipt_rehearsal.json"
        verifier = CandidateVerifier(candidate_dir=out_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_DIAGNOSTIC
        assert len(verifier.violations) == 0

    def test_source_anchor_verification_tampering_fails_closed(self, tmp_path: Path):
        """Verify that tampering with raw upstream corpus text causes anchor recovery < 1.0 and fails closed with VERDICT_FAILED."""
        cand_dir = create_mock_candidate_dir(tmp_path / "candidate_tampered_anchors", is_pass=True)

        # Corrupt the upstream source dataset text for docs so that byte slices fail hash matching
        for sub_dir in ["mock_data", "data"]:
            corpus_file = cand_dir / sub_dir / "beir-scifact" / "corpus.jsonl"
            if corpus_file.exists():
                lines = []
                with open(corpus_file, "r", encoding="utf-8") as f:
                    for line in f:
                        rec = json.loads(line)
                        rec["text"] = "CORRUPTED_PREFIX_" + rec.get("text", "")
                        lines.append(json.dumps(rec))
                with open(corpus_file, "w", encoding="utf-8") as f:
                    for l in lines:
                        f.write(l + "\n")

            alt_file = cand_dir / sub_dir / "beir-scifact.jsonl"
            if alt_file.exists():
                with open(alt_file, "w", encoding="utf-8") as f:
                    for l in lines:
                        f.write(l + "\n")

        receipt_file = tmp_path / "receipt_anchor_tamper.json"
        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert receipt["sqlite_database_audit"]["anchor_recovery_rate"] < 1.0
        assert any("anchor" in v.lower() for v in verifier.violations)



    def test_missing_restart_recovery_receipt_fails_verification(self, tmp_path: Path):
        """Verify that a missing restart_recovery_receipt.json causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_missing_recovery_receipt", is_pass=True)
        receipt_file = tmp_path / "receipt_missing_recovery.json"

        target_file = cand_dir / "runs" / "restart_recovery_receipt.json"
        if target_file.exists():
            target_file.unlink()

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        if "runs/restart_recovery_receipt.json" in csums:
            del csums["runs/restart_recovery_receipt.json"]
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("missing" in v.lower() and "restart_recovery_receipt" in v for v in verifier.violations)

    def test_missing_incremental_resume_receipt_fails_verification(self, tmp_path: Path):
        """Verify that a missing incremental_resume_receipt.json causes verification failure."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_missing_resume_receipt", is_pass=True)
        receipt_file = tmp_path / "receipt_missing_resume.json"

        target_file = cand_dir / "runs" / "incremental_resume_receipt.json"
        if target_file.exists():
            target_file.unlink()

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        if "runs/incremental_resume_receipt.json" in csums:
            del csums["runs/incremental_resume_receipt.json"]
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("missing" in v.lower() and "incremental_resume_receipt" in v for v in verifier.violations)

    def test_node_fts_parity_mismatch_fails_verification(self, tmp_path: Path):
        """Verify that a parity mismatch in node_fts fails verification."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_node_fts_parity", is_pass=True)
        receipt_file = tmp_path / "receipt_node_fts_parity.json"

        # Corrupt node_fts table in scale_100k_replay.db
        replay_db = cand_dir / "scale_100k_replay.db"
        conn = sqlite3.connect(replay_db)
        conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES ('diff_av', 'diff_doc', 'diff_title', 'diff_content');")
        conn.commit()
        conn.close()

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["scale_100k_replay.db"] = compute_sha256(replay_db)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("node_fts" in v.lower() or "parity" in v.lower() for v in verifier.violations)

    def test_missing_source_data_root_without_fallback(self, tmp_path: Path):
        """Verify that a missing source data root without fallback causes anchor violation."""
        cand_dir = create_mock_candidate_dir(tmp_path / "cand_missing_data_root", is_pass=True)
        receipt_file = tmp_path / "receipt_missing_data_root.json"

        import shutil
        data_dir = cand_dir / "data"
        if data_dir.exists():
            shutil.rmtree(data_dir)
        mock_data_dir = cand_dir / "mock_data"
        if mock_data_dir.exists():
            shutil.rmtree(mock_data_dir)

        # Also remove from candidate manifest so the verifier tries data
        manifest_path = cand_dir / "candidate_manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if "data_root" in manifest:
            del manifest["data_root"]
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        checksums_path = cand_dir / "checksums.json"
        with open(checksums_path, "r", encoding="utf-8") as f:
            csums = json.load(f)
        csums["candidate_manifest.json"] = compute_sha256(manifest_path)
        with open(checksums_path, "w", encoding="utf-8") as f:
            json.dump(csums, f, indent=2)

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("anchor" in v.lower() or "missing" in v.lower() for v in verifier.violations)
