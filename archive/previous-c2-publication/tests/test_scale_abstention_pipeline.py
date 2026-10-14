"""Unit tests for Wave R2.2 Scale Gate Abstention Pipeline, Telemetry Integrity, and Metric Recomputation."""

from __future__ import annotations

import hashlib
import inspect
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.modules.pop("trace", None)

import pytest

from run_100k_scale_gate import Scale100KRunner, extract_keywords
from verify_100k_candidate import (
    CandidateVerifier,
    compute_query_ndcg10_recall20_coverage20,
    compute_query_ndcg10_recall20,
    compute_merkle_root,
    VERDICT_PASS,
    VERDICT_FAILED,
    VERDICT_DIAGNOSTIC,
    CANONICAL_POLICY_SHA256,
    CANONICAL_QUERIES_MANIFEST_SHA256,
    CANONICAL_CORPUS_MANIFEST_SHA256,
    CANONICAL_BLIND_QUERIES_SHA256,
)


def compute_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def setup_mock_runner(tmp_path: Path) -> Scale100KRunner:
    """Initialize a Scale100KRunner with indexed mock documents for testing."""
    manifest_file = tmp_path / "corpus_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump({"manifest_title": "Test Manifest", "total_unique_documents": 20}, f)

    out_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    runner = Scale100KRunner(
        manifest_path=manifest_file,
        data_root=data_dir,
        output_dir=out_dir,
        target_count=20,
        temp_dir=tmp_path / "work",
        mode="diagnostic",
        allow_unlocked_policy=True,
    )

    # Index sample documents into runner memory structures
    docs = [
        {"id": "doc_sci_1", "dataset": "beir-scifact", "title": "CRISPR gene editing", "content": "CRISPR Cas9 is used for precise genome editing in human cell lines."},
        {"id": "doc_sci_2", "dataset": "beir-scifact", "title": "Telomerase activation", "content": "Telomerase reverse transcriptase stabilizes telomeres during cell division."},
        {"id": "doc_med_1", "dataset": "beir-nfcorpus", "title": "Cardiovascular risk", "content": "Dietary fiber and physical exercise decrease cardiovascular mortality risk."},
        {"id": "doc_fiq_1", "dataset": "beir-fiqa", "title": "Bond yield spread", "content": "Yield curve inversion indicates increased risk of recession and credit tightening."},
        {"id": "doc_mhr_1", "dataset": "multihop-rag", "title": "Apollo program", "content": "The Apollo program was conceived during Dwight D. Eisenhower administration."},
    ]

    for d in docs:
        doc_id = d["id"]
        content = d["content"]
        title = d["title"]
        ds = d["dataset"]

        runner.doc_index[doc_id] = {"content": content, "title": title, "dataset": ds}
        runner.doc_datasets[doc_id] = ds
        runner.doc_lengths[doc_id] = len(content.split())

        terms = extract_keywords(content)
        for t in terms:
            runner.inverted_index[t].append((doc_id, 1))

        t_terms = extract_keywords(title)
        for t in t_terms:
            runner.title_inverted_index[t].append((doc_id, 1))

    runner.avg_doc_len = sum(runner.doc_lengths.values()) / max(1, len(runner.doc_lengths))
    return runner


def create_mock_candidate_with_telemetry(
    target_dir: Path,
    tamper_dossier: bool = False,
    num_null_queries: int = 301,
    abstention_accuracy: float = 1.0,
    null_query_hallucination: bool = False,
    missing_citations: bool = False,
    forced_abstention: bool = False,
    is_full_100k: bool = False,
) -> Path:
    """Create a complete mock candidate bundle with raw evaluations and checksums."""
    target_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = target_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

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

    # 1. Create SQLite DB
    db_file = target_dir / "scale_100k.db"
    if db_file.exists():
        db_file.unlink()
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("""
        CREATE TABLE events (event_id TEXT PRIMARY KEY, stream_id TEXT, stream_sequence INTEGER, event_type TEXT, occurred_at TEXT, actor TEXT, causation_id TEXT, correlation_id TEXT, schema_version INTEGER DEFAULT 1, payload_json TEXT, payload_hash TEXT, idempotency_key TEXT UNIQUE);
    """)
    conn.execute("""
        CREATE TABLE ingestions (ingestion_id TEXT PRIMARY KEY, workspace_id TEXT, doc_id TEXT, dataset TEXT, content_hash TEXT, stream_sequence INTEGER, atom_count INTEGER, created_at TEXT);
    """)
    conn.execute("""
        CREATE TABLE nodes (node_id TEXT PRIMARY KEY, workspace_id TEXT, stream_sequence INTEGER);
    """)
    conn.execute("""
        CREATE TABLE node_versions (atom_version_id TEXT PRIMARY KEY, node_id TEXT, span_start INTEGER, span_end INTEGER, content_hash TEXT, stream_sequence INTEGER);
    """)
    conn.execute("""
        CREATE TABLE edge_versions (edge_id TEXT PRIMARY KEY, workspace_id TEXT, source_id TEXT, target_id TEXT, family TEXT, weight REAL DEFAULT 1.0, stream_sequence INTEGER);
    """)
    conn.execute("""
        CREATE TABLE source_lifecycle (atom_version_id TEXT PRIMARY KEY, workspace_id TEXT, state TEXT, created_at TEXT, stream_sequence INTEGER);
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE node_fts USING fts5(atom_version_id UNINDEXED, doc_id UNINDEXED, title, content, tokenize='porter');
    """)

    insert_limit = len(all_mock_doc_ids)
    for i, doc_id in enumerate(all_mock_doc_ids):
        seq = i + 1
        content = f"Document content test paragraph {doc_id}."
        content_b = content.encode("utf-8")
        chash = hashlib.sha256(content_b).hexdigest()
        pj = json.dumps({"doc_id": doc_id, "dataset": "beir-scifact", "content": content, "content_hash": chash})
        conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (f"ev_{seq}", "ws", seq, "trace.source.ingested", "now", "sys", None, None, 1, pj, chash, f"idem_{doc_id}_{i}"))
        conn.execute("INSERT INTO ingestions VALUES (?,?,?,?,?,?,?,?)", (f"ing_{seq}", "ws", doc_id, "beir-scifact", chash, seq, 1, "now"))
        conn.execute("INSERT INTO nodes VALUES (?,?,?)", (f"node_{seq}", "ws", seq))
        conn.execute("INSERT INTO node_versions VALUES (?,?,?,?,?,?)", (f"av_{seq}", f"node_{seq}", 0, len(content_b), chash, seq))
        conn.execute("INSERT INTO source_lifecycle VALUES (?,?,?,?,?)", (f"av_{seq}", "ws", "active", "now", seq))
        conn.execute("INSERT INTO edge_versions VALUES (?,?,?,?,?,?,?)", (f"edge_{seq}", "ws", doc_id, f"ent:tag_{i % 5}", "structural", 1.0, seq))
        conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}", doc_id, f"Title {doc_id}", content))

    if is_full_100k:
        for i in range(insert_limit, 100000):
            seq = i + 1
            c_text = f"Full scale unique document content index {i} payload"
            c_hash = hashlib.sha256(c_text.encode("utf-8")).hexdigest()
            conn.execute("INSERT INTO events (event_id, stream_id, stream_sequence, event_type, occurred_at, actor, schema_version, payload_json, payload_hash) VALUES (?,?,?,?,?,?,?,?,?)", (f"ev_{seq}", "ws", seq, "trace.source.ingested", "now", "sys", 1, json.dumps({"doc_id": f"doc_{i}", "content": c_text}), c_hash))
            conn.execute("INSERT INTO ingestions (ingestion_id, workspace_id, doc_id, dataset, content_hash, stream_sequence, atom_count, created_at) VALUES (?,?,?,?,?,?,?,?)", (f"ing_{seq}", "ws", f"doc_{i}", "beir-scifact", c_hash, seq, 1, "now"))
            conn.execute("INSERT INTO node_fts (atom_version_id, doc_id, title, content) VALUES (?,?,?,?)", (f"av_{seq}", f"doc_{i}", f"Title {i}", c_text))

    conn.commit()
    conn.close()

    replay_db_file = target_dir / "scale_100k_replay.db"
    shutil.copy2(db_file, replay_db_file)

    # 2. Emit raw query evaluations
    raw_evals = []
    lanes = [
        ("direct_lookup", "beir-scifact", 12.5),
        ("domain_semantic", "beir-nfcorpus", 14.0),
        ("semantic_qa", "beir-fiqa", 16.0),
        ("multi_hop_reasoning", "multihop-rag", 22.0),
    ]

    for lane_name, ds_name, lat in lanes:
        lane_qs = manifest_cohorts.get(lane_name, [])
        for q_idx in range(10):
            if q_idx < len(lane_qs):
                mq = lane_qs[q_idx]
                qid = str(mq.get("query_id") or mq.get("internal_id"))
                gold_ids = [str(g) for g in mq.get("gold_ids", [f"doc_{q_idx}"])]
            else:
                qid = f"{lane_name}_{q_idx}"
                gold_ids = [f"doc_{q_idx}"]

            if missing_citations or forced_abstention:
                cands = [f"doc_{(100 + j) % insert_limit}" for j in range(20)]
            else:
                cands = list(gold_ids[:min(20, len(gold_ids))])
                cands += [f"doc_{(q_idx * 20 + j) % insert_limit}" for j in range(20 - len(cands))]

            raw_evals.append({
                "lane": lane_name,
                "dataset": ds_name,
                "query_id": qid,
                "query_text": f"Query text for {lane_name} {q_idx}",
                "retrieved_top20": cands[:20],
                "ranked_candidates": [
                    {"doc_id": c, "score": round(1.0 - 0.01 * idx, 4), "rank": idx + 1}
                    for idx, c in enumerate(cands[:20])
                ],
                "latency_ms": lat,
                "system_abstained": forced_abstention,
                "citations_emitted": [],
            })

    with open(runs_dir / "raw_query_evaluations.jsonl", "w", encoding="utf-8") as f:
        for r in raw_evals:
            f.write(json.dumps(r) + "\n")

    # 3. Emit abstention evaluations
    abs_qs = manifest_cohorts.get("abstention_suite", [])
    abs_evals = []
    for n_idx in range(num_null_queries):
        if n_idx < len(abs_qs):
            qid = str(abs_qs[n_idx].get("query_id") or abs_qs[n_idx].get("internal_id"))
        else:
            qid = f"null_q_{n_idx}"
        is_halluc = (null_query_hallucination and n_idx == 0)
        is_abstained = (n_idx < int(abstention_accuracy * num_null_queries)) and not is_halluc
        rec_abs = {
            "query_id": qid,
            "query_text": f"Null query {n_idx}",
            "system_abstained": is_abstained,
            "citations_emitted": ["doc_0"] if is_halluc else [],
            "latency_ms": 5.2,
            "ranked_candidates": [
                {"doc_id": f"doc_{j}", "score": round(0.5 - 0.01 * j, 4), "rank": j + 1}
                for j in range(20)
            ],
        }
        abs_evals.append(rec_abs)

    with open(runs_dir / "abstention_evaluations.jsonl", "w", encoding="utf-8") as f:
        for a in abs_evals:
            f.write(json.dumps(a) + "\n")

    with open(runs_dir / "durability_audit_trace.json", "w", encoding="utf-8") as f:
        json.dump({"source_atom_retention": 1.0, "content_hash_drift": 0.0, "repeat_erasure_delta_writes": 0, "anchor_recovery_rate": 1.0, "total_atoms_in_db": 200000 if is_full_100k else len(all_mock_doc_ids), "total_documents_in_db": 100000 if is_full_100k else len(all_mock_doc_ids)}, f)

    with open(runs_dir / "restart_recovery_receipt.json", "w", encoding="utf-8") as f:
        json.dump({"status": "RECOVERY_VERIFIED", "integrity_check": "ok", "process_exit_code": 0, "timestamp": "now"}, f)

    with open(runs_dir / "incremental_resume_receipt.json", "w", encoding="utf-8") as f:
        json.dump({"status": "RESUME_VERIFIED", "initial_watermark": 100, "final_watermark": 200, "duplicate_events": 0, "duplicate_rejections": 0, "watermarks_continuous": True, "timestamp": "now"}, f)

    parity_dict = {}
    for t_name in ["events", "ingestions", "nodes", "node_versions", "edge_versions", "source_lifecycle", "node_fts"]:
        cnt = 100000 if is_full_100k else len(all_mock_doc_ids)
        parity_dict[t_name] = {
            "source_count": cnt,
            "replay_count": cnt,
            "source_hash": f"hash_{t_name}",
            "replay_hash": f"hash_{t_name}",
            "parity_match": True,
        }
    with open(runs_dir / "replay_recovery_trace.json", "w", encoding="utf-8") as f:
        json.dump({"rebuild_parity": 1.0, "table_parity_audit": parity_dict}, f)

    with open(runs_dir / "telemetry_timeseries.json", "w", encoding="utf-8") as f:
        json.dump({"timeseries": [{"rss_mb": 1.2 * 1024.0, "peak_rss_mb": 1.2 * 1024.0}]}, f)

    with open(runs_dir / "graph_walk_telemetry.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"latency_ms": 1.5, "nodes_visited": 10}) + "\n")

    # Create mock upstream source dataset files for strict source-only anchor verification
    mock_data_root = target_dir / "mock_data"
    mock_data_root.mkdir(parents=True, exist_ok=True)
    (mock_data_root / "beir-scifact").mkdir(parents=True, exist_ok=True)

    corpus_records = []
    for doc_id in all_mock_doc_ids:
        content = f"Document content test paragraph {doc_id}."
        corpus_records.append({"_id": doc_id, "text": content})

    if is_full_100k:
        for i in range(insert_limit, 100000):
            c_text = f"Full scale unique document content index {i} payload"
            corpus_records.append({"_id": f"doc_{i}", "text": c_text})

    with open(mock_data_root / "beir-scifact" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")

    cand_data_dir = target_dir / "data"
    cand_data_dir.mkdir(parents=True, exist_ok=True)
    (cand_data_dir / "beir-scifact").mkdir(parents=True, exist_ok=True)
    with open(cand_data_dir / "beir-scifact" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for cr in corpus_records:
            f.write(json.dumps(cr) + "\n")

    # 4. Dossier metrics calculation using exact verifier calculation
    def calc_lane_metrics(l_name: str):
        recs = [r for r in raw_evals if r.get("lane") == l_name]
        if not recs:
            return 0.0, 0.0
        n_list, r_list = [], []
        for r in recs:
            # Look up gold_ids from manifest
            q_id = r.get("query_id")
            mq = next((q for q in manifest_cohorts.get(l_name, []) if str(q.get("query_id") or q.get("internal_id")) == str(q_id)), {})
            golds = set(str(g) for g in mq.get("gold_ids", []))
            nv, rv, _ = compute_query_ndcg10_recall20_coverage20(r.get("retrieved_top20", []), golds)
            n_list.append(nv)
            r_list.append(rv)
        return round(sum(n_list)/max(1, len(n_list)), 4), round(sum(r_list)/max(1, len(r_list)), 4)

    sci_n, sci_r = calc_lane_metrics("direct_lookup")
    nfc_n, nfc_r = calc_lane_metrics("domain_semantic")
    fiq_n, fiq_r = calc_lane_metrics("semantic_qa")
    mhr_n, mhr_r = calc_lane_metrics("multi_hop_reasoning")

    reported_scifact_ndcg = 0.9999 if tamper_dossier else sci_n
    reported_scifact_recall = 0.5000 if tamper_dossier else sci_r

    zhr = 0.0 if null_query_hallucination else 1.0000
    computed_abs_acc = round(sum(1 for a in abs_evals if a.get("system_abstained")) / max(1, len(abs_evals)), 4)

    canonical_policy_sha = CANONICAL_POLICY_SHA256

    dossier = {
        "evaluation_title": "Trace 100K Scale Gate Dossier",
        "target_standard": "DEC-P-005b-CANDIDATE",
        "policy_sha256": canonical_policy_sha,
        "scale_workload_vector": {
            "document_count_D": 100000 if is_full_100k else 20,
            "raw_source_bytes_B": 100_000,
            "storage_footprint_bytes": db_file.stat().st_size,
            "storage_multiplier": 1.5,
        },
        "host_environment": {
            "peak_rss_gb": 1.2,
        },
        "metrics": {
            "promise_1_durable_memory": {
                "source_atom_retention": 1.0,
                "content_hash_drift": 0.0,
                "byte_offset_anchor_recovery": 1.0,
                "repeat_erasure_delta_writes": 0,
            },
            "promise_4_bounded_economics": {
                "storage_multiplier": 1.5,
                "persisted_max_degree_sql": 1,
                "graph_traversal_p95_latency_ms": 1.5,
                "peak_ram_gb": 1.2,
            },
            "promise_3_retrieval_quality": {
                "direct_lookup": {
                    "ndcg_at_10": reported_scifact_ndcg,
                    "recall_at_20": reported_scifact_recall,
                    "p95_ms": 12.5,
                },
                "domain_semantic": {
                    "ndcg_at_10": nfc_n,
                    "recall_at_20": nfc_r,
                    "p95_ms": 14.0,
                },
                "semantic_qa": {
                    "ndcg_at_10": fiq_n,
                    "recall_at_20": fiq_r,
                    "p95_ms": 16.0,
                },
                "multi_hop_reasoning": {
                    "ndcg_at_10": mhr_n,
                    "recall_at_20": mhr_r,
                    "complete_coverage_at_20": mhr_r,
                    "p95_ms": 22.0,
                },
                "abstention_lane": {
                    "zero_hallucination_rate": zhr,
                    "abstention_accuracy": computed_abs_acc,
                    "unanswerable_queries_evaluated": num_null_queries,
                },
            },
            "recovery_and_resilience": {
                "rebuild_parity": 1.0,
            },
        },
        "overall_verdict": "PASS_ALL_SCALE_GATE_INVARIANTS",
    }

    with open(target_dir / "100k_scale_dossier.json", "w", encoding="utf-8") as f:
        json.dump(dossier, f, indent=2)

    # Defect 7: Create mock upstream source dataset files for strict source-only anchor verification
    mock_data_root = target_dir / "mock_data"
    mock_data_root.mkdir(parents=True, exist_ok=True)
    (mock_data_root / "beir-scifact").mkdir(parents=True, exist_ok=True)

    corpus_records = []
    for doc_id in all_mock_doc_ids:
        content = f"Document content test paragraph {doc_id}."
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
            "policy_sha256": canonical_policy_sha,
            "queries_manifest_sha256": CANONICAL_QUERIES_MANIFEST_SHA256,
            "corpus_manifest_sha256": CANONICAL_CORPUS_MANIFEST_SHA256,
            "blind_queries_sha256": CANONICAL_BLIND_QUERIES_SHA256,
            "data_root": str(mock_data_root),
        }, f)

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


class TestScaleAbstentionPipeline:
    """Test suite for Wave R2.2 un-labeled abstention, telemetry integrity, and metric recomputation."""

    def test_unlabeled_null_queries_genuinely_filtered_by_pipeline(self, tmp_path: Path):
        """Test that un-labeled null queries without grounding citations are genuinely filtered by score_query."""
        runner = setup_mock_runner(tmp_path)

        # 1. Unanswerable query containing zero keywords matching any document
        unanswerable_query = "quantum teleportation of gravitational dark matter warp drive"
        top_ranked, scores, system_abstained, q_lat = runner.score_query(unanswerable_query, dataset_hint="multihop-rag")

        assert system_abstained is True, "Pipeline must genuinely abstain on unanswerable queries without matches"
        assert len(top_ranked) == 0 or max(scores) < 0.1, "Candidate scores must be sub-threshold for ungrounded query"
        assert q_lat >= 0.0

        # 2. Answerable query matching known indexed facts
        answerable_query = "CRISPR Cas9 genome editing human cell lines"
        top_ranked_ans, scores_ans, system_abstained_ans, _ = runner.score_query(answerable_query, dataset_hint="beir-scifact")

        assert system_abstained_ans is False, "Pipeline must NOT abstain when relevant grounded documents exist"
        assert len(top_ranked_ans) > 0
        assert "doc_sci_1" in top_ranked_ans

    def test_query_labels_not_present_in_runtime_score_query_input(self, tmp_path: Path):
        """Test that query labels (gold_ids, query_class, expected_abstention) are not present in score_query input."""
        runner = setup_mock_runner(tmp_path)

        # Inspect score_query signature
        sig = inspect.signature(runner.score_query)
        param_names = list(sig.parameters.keys())

        # score_query must only accept query_text and optional dataset_hint (NO query_class, gold_ids, or labels)
        forbidden_params = {"gold_ids", "query_class", "expected_abstention", "ground_truth", "native_gold_doc_ids"}
        for p in param_names:
            assert p not in forbidden_params, f"Runtime score_query must not accept label parameter: {p}"

        assert "query_text" in param_names
        assert len(param_names) == 2  # (self), query_text, dataset_hint

        # Verify score_query operates purely on the query text string without label metadata
        top_ranked, scores, abstained, lat = runner.score_query("bond yield inversion recession risk", dataset_hint="beir-fiqa")
        assert "doc_fiq_1" in top_ranked
        assert abstained is False

    def test_forced_abstention_rejection_and_unlabeled_pipeline_evaluation(self, tmp_path: Path):
        """Verify that hardcoding system_abstained=True collapses retrieval quality and is rejected."""
        cand_dir = create_mock_candidate_with_telemetry(
            tmp_path / "cand_forced_abstain",
            forced_abstention=True,
            is_full_100k=True,
        )
        receipt_file = tmp_path / "receipt_forced.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("direct_lookup nDCG@10" in v or "direct_lookup Recall@20" in v for v in verifier.violations)

    def test_missing_citations_on_answered_claims_fails_closed(self, tmp_path: Path):
        """Verify that answered queries lacking gold document citations fail quality floors."""
        cand_dir = create_mock_candidate_with_telemetry(
            tmp_path / "cand_missing_citations",
            missing_citations=True,
            is_full_100k=True,
        )
        receipt_file = tmp_path / "receipt_no_cit.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("nDCG@10 0.0000" in v for v in verifier.violations)

    def test_ungrounded_citations_on_unanswerable_null_queries_fails_closed(self, tmp_path: Path):
        """Verify that hallucinating citations on null queries causes zero hallucination rate failure."""
        cand_dir = create_mock_candidate_with_telemetry(
            tmp_path / "cand_halluc",
            null_query_hallucination=True,
        )
        receipt_file = tmp_path / "receipt_halluc.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Zero hallucination rate" in v for v in verifier.violations)

    def test_abstention_accuracy_threshold_enforcement(self, tmp_path: Path):
        """Verify that abstention accuracy < 0.900 triggers fail-closed rejection."""
        cand_dir = create_mock_candidate_with_telemetry(
            tmp_path / "cand_low_acc",
            abstention_accuracy=0.75,  # Sub-floor
        )
        receipt_file = tmp_path / "receipt_low_acc.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Abstention accuracy" in v for v in verifier.violations)

    def test_unanswerable_null_query_count_threshold_enforcement(self, tmp_path: Path):
        """Verify that full candidate evaluating fewer than 301 null queries is rejected."""
        cand_dir = create_mock_candidate_with_telemetry(
            tmp_path / "cand_few_null",
            is_full_100k=True,
            num_null_queries=200,  # < 301
        )
        receipt_file = tmp_path / "receipt_few_null.json"

        verifier = CandidateVerifier(candidate_dir=cand_dir, receipt_out=receipt_file)
        receipt = verifier.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Unanswerable null queries evaluated 200 < 301" in v or "evaluated only" in v for v in verifier.violations)

    def test_complete_top20_rankings_emitted_without_500_truncation(self, tmp_path: Path):
        """Test that complete top-20 rankings are emitted in telemetry without any 500-record truncation."""
        runner = setup_mock_runner(tmp_path)
        data_dir = tmp_path / "data"

        # Create a synthetic dataset with 600 query cases (> 500)
        ds_name = "beir-scifact"
        ds_dir = data_dir / ds_name
        ds_dir.mkdir(parents=True, exist_ok=True)

        queries_600 = []
        for i in range(600):
            queries_600.append({
                "native_query_id": f"q_{i}",
                "query": f"CRISPR gene editing research query number {i}",
                "gold_document_ids": ["doc_sci_1"],
            })

        with open(ds_dir / "queries.jsonl", "w", encoding="utf-8") as f:
            for q in queries_600:
                f.write(json.dumps(q) + "\n")

        mhr_dir = data_dir / "multihop-rag"
        mhr_dir.mkdir(parents=True, exist_ok=True)
        with open(mhr_dir / "queries.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"query_class": "null_query", "query": "null query xyz", "native_query_id": "null_1"}) + "\n")

        runner.evaluate_retrieval_lanes()

        raw_eval_file = runner.runs_dir / "raw_query_evaluations.jsonl"
        assert raw_eval_file.exists()

        records = [json.loads(line) for line in open(raw_eval_file, "r", encoding="utf-8") if line.strip()]
        sci_records = [r for r in records if r.get("lane") == "direct_lookup"]
        assert len(sci_records) == 1109, f"Expected 1109 evaluated queries in slice, got {len(sci_records)}"

        for r in sci_records:
            assert "retrieved_top20" in r, "Evaluation records must contain retrieved_top20 rankings array"
            assert isinstance(r["retrieved_top20"], list)
            assert "ranked_candidates" in r, "Evaluation records must contain ranked_candidates list"
            assert "gold_ids" not in r, "Candidate runner must operate blindly without leaking gold_ids"

    def test_standalone_verifier_recomputes_metrics_and_detects_tampering(self, tmp_path: Path):
        """Test that the standalone verifier correctly recomputes nDCG@10 and Recall@20 and catches tampered scores."""
        # 1. Test Clean Candidate: Recomputed metrics match dossier perfectly
        clean_dir = create_mock_candidate_with_telemetry(tmp_path / "clean_candidate", tamper_dossier=False)
        receipt_clean = tmp_path / "receipt_clean.json"

        verifier_clean = CandidateVerifier(candidate_dir=clean_dir, receipt_out=receipt_clean)
        receipt = verifier_clean.verify_all()

        assert receipt["verification_verdict"] == VERDICT_DIAGNOSTIC
        assert receipt["recomputed_metrics_audit"]["all_metrics_match_dossier"] is True
        recomputed = receipt["recomputed_metrics_audit"]["recomputed_metrics"]
        assert recomputed["direct_lookup"]["ndcg_at_10"] == 1.0000
        assert recomputed["direct_lookup"]["recall_at_20"] == 1.0000
        assert receipt_clean.exists()

        # 2. Test Tampered Dossier: Dossier claims fake numbers not supported by raw rankings
        tampered_dir = create_mock_candidate_with_telemetry(tmp_path / "tampered_candidate", tamper_dossier=True)
        receipt_tamper = tmp_path / "receipt_tamper.json"

        verifier_tamper = CandidateVerifier(candidate_dir=tampered_dir, receipt_out=receipt_tamper)
        receipt = verifier_tamper.verify_all()

        assert receipt["verification_verdict"] == VERDICT_FAILED
        assert any("Dossier metric mismatch" in v for v in verifier_tamper.violations)
        assert any("direct_lookup.recall_at_20" in v or "direct_lookup.ndcg_at_10" in v for v in verifier_tamper.violations)

    def test_merkle_root_cryptographic_evidence_binding(self, tmp_path: Path):
        """Test that candidate files produce a deterministic SHA-256 Merkle root binding."""
        hashes = [
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
        ]
        root1 = compute_merkle_root(hashes)
        root2 = compute_merkle_root(hashes)
        assert root1 == root2
        assert len(root1) == 64

        # Changing one hash changes the root
        hashes_tampered = [
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "e" * 64,
        ]
        root_tampered = compute_merkle_root(hashes_tampered)
        assert root1 != root_tampered

    def test_compute_query_ndcg10_recall20_coverage20_exact_calculations(self):
        """Unit test for unfloored nDCG@10, Recall@20, and Complete Coverage@20 calculation logic."""
        # 1. Perfect hit at rank 0
        cands_0 = ["doc_gold_1", "doc_other_2", "doc_other_3"]
        golds_0 = {"doc_gold_1"}
        ndcg, rec, cov = compute_query_ndcg10_recall20_coverage20(cands_0, golds_0)
        assert ndcg == 1.0
        assert rec == 1.0
        assert cov == 1.0

        # 2. Hit at rank 9 (index 9)
        cands_9 = [f"other_{i}" for i in range(9)] + ["doc_gold_1"] + [f"other_{i}" for i in range(10, 20)]
        ndcg_9, rec_9, cov_9 = compute_query_ndcg10_recall20_coverage20(cands_9, golds_0)
        assert rec_9 == 1.0
        assert cov_9 == 1.0
        assert 0.28 < ndcg_9 < 0.31  # 1 / log2(11) ≈ 0.289

        # 3. Hit at rank 15 (in top-20 but outside top-10)
        cands_15 = [f"other_{i}" for i in range(15)] + ["doc_gold_1"] + [f"other_{i}" for i in range(16, 20)]
        ndcg_15, rec_15, cov_15 = compute_query_ndcg10_recall20_coverage20(cands_15, golds_0)
        assert rec_15 == 1.0
        assert cov_15 == 1.0
        assert ndcg_15 == 0.0  # Outside top 10

        # 4. Multi-hop: 2 gold documents, only 1 retrieved in top-20
        golds_multi = {"doc_g1", "doc_g2"}
        cands_partial = ["doc_g1"] + [f"other_{i}" for i in range(19)]
        ndcg_m, rec_m, cov_m = compute_query_ndcg10_recall20_coverage20(cands_partial, golds_multi)
        assert rec_m == 0.5
        assert cov_m == 0.0  # Partial coverage is 0.0 complete coverage

    def test_short_rankings_rejected(self, tmp_path: Path):
        """Verify that ranking telemetry with fewer than 20 candidates fails verification closed."""
        cand_dir = create_mock_candidate_with_telemetry(tmp_path / "cand_short_rankings")
        receipt_file = tmp_path / "receipt_short.json"

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

        # Update checksums
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

    def test_candidate_authored_hallucination_flag_ignored(self, tmp_path: Path):
        """Verify that candidate marking hallucination=False is ignored when citations are emitted on null queries."""
        cand_dir = create_mock_candidate_with_telemetry(tmp_path / "cand_halluc_ignore")
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

    def test_duplicate_query_ids_replacing_missing_ids_rejected(self, tmp_path: Path):
        """Verify that duplicate query IDs replacing missing IDs fail exact set equality checks."""
        cand_dir = create_mock_candidate_with_telemetry(tmp_path / "cand_dup_qids")
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


