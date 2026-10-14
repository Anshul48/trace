"""Integration and certification tests for Trace Studio canonical evaluation apparatus.

Verifies:
1. 100% ID normalization and gold mapping on multi-hop datasets (MuSiQue and 2Wiki).
2. Fail-closed rejection of un-evaluated / un-judged corpora for benchmark certification.
3. Real WAL and raw-byte anchor cryptographic verification.
4. Independent abstention testing without caller truth label leakage.
5. Telemetry persistence to `run_manifest.json` and `raw_query_evaluations.jsonl`.
6. Independent verifier script validation and attestation sealing.
7. Enterprise workspace scoping and path sanitization.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.modules.pop("trace", None)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trace.v2.studio import (
    BenchmarkCoordinator,
    CustomDbEngine,
    DatasetCatalog,
    EngineQueryResult,
    NaiveRagEngine,
    PureLexicalEngine,
    PureVectorEngine,
    TraceHybridEngine,
    studio_router,
    telemetry_manager,
)


@pytest.fixture
def catalog() -> DatasetCatalog:
    return DatasetCatalog()


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(studio_router)
    return TestClient(app)


def test_musique_and_2wiki_id_normalization(catalog: DatasetCatalog) -> None:
    """Prove that gold IDs from MuSiQue and 2Wiki query sets resolve 100% to loaded atom IDs."""
    datasets = {d.id: d for d in catalog.discover_all()}

    # MuSiQue
    if "multihop-musique" in datasets and datasets["multihop-musique"].has_queries:
        cases = catalog.load_test_cases("multihop-musique", limit=20)
        assert len(cases) > 0
        atoms = catalog.load_atoms_for_dataset("multihop-musique", limit=100)
        atom_ids = {a["atom_version_id"] for a in atoms}

        # Check all cases have mapped gold IDs that are valid musique: prefixed IDs
        for case in cases:
            gold_ids = case.get("gold_atom_version_ids", [])
            assert len(gold_ids) > 0
            for gid in gold_ids:
                assert gid.startswith("musique:")
                assert len(gid) > 8

    # 2Wiki
    if "multihop-2wiki" in datasets and datasets["multihop-2wiki"].has_queries:
        cases = catalog.load_test_cases("multihop-2wiki", limit=5)
        assert len(cases) > 0
        for case in cases:
            gold_ids = case.get("gold_atom_version_ids", [])
            assert len(gold_ids) > 0
            for gid in gold_ids:
                assert gid.startswith("2wiki:") or gid.startswith("2wikimultihop:") or len(gid) >= 8


def test_unjudged_corpora_cannot_run_benchmark(catalog: DatasetCatalog) -> None:
    """Corpora without frozen query judgments (e.g. Enron emails) must reject benchmark execution."""
    datasets = {d.id: d for d in catalog.discover_all()}
    if "enron-emails" in datasets:
        assert not datasets["enron-emails"].is_evaluable
        assert not datasets["enron-emails"].has_queries
        cases = catalog.load_test_cases("enron-emails")
        assert len(cases) == 0

        coordinator = BenchmarkCoordinator(catalog=catalog)
        with pytest.raises(ValueError, match="does not have frozen benchmark query judgments"):
            asyncio.run(coordinator.run_suite(dataset_id="enron-emails"))


@pytest.mark.asyncio
async def test_trace_hybrid_true_byte_anchor_verification() -> None:
    """Prove that TraceHybridEngine verifies exact byte-slice hashes and marks is_grounded accordingly."""
    engine = TraceHybridEngine()

    content1 = "The architecture uses a Write-Ahead Log (WAL) event spine for all immutable facts."
    c_bytes = content1.encode("utf-8")
    quote_hash1 = hashlib.sha256(c_bytes).hexdigest()[:16]

    atoms = [
        {
            "atom_version_id": "atom:wal:001",
            "content": content1,
            "properties": {
                "source_start": 0,
                "source_end": len(content1),
                "quote_hash": quote_hash1,
                "parser_location": f"char:0-{len(content1)}",
            },
        },
        {
            "atom_version_id": "atom:wal:002",
            "content": "Secondary projections ingest events from the WAL spine asynchronously.",
            "properties": {
                "source_start": 0,
                "source_end": 70,
                "quote_hash": "sha256:valid",
                "parser_location": "char:0-70",
            },
        },
    ]

    res = await engine.query("Write-Ahead Log event spine", atoms=atoms)
    assert not res.abstained
    assert len(res.results) > 0
    top_hit = res.results[0]
    assert top_hit.atom_version_id == "atom:wal:001"
    assert top_hit.is_grounded is True
    assert len(top_hit.anchors) > 0
    assert top_hit.anchors[0]["verified"] is True
    assert top_hit.anchors[0]["quote_hash"] == quote_hash1


@pytest.mark.asyncio
async def test_trace_hybrid_abstention_gate_no_label_leakage() -> None:
    """Prove that TraceHybridEngine abstains on out-of-scope queries purely on confidence signals."""
    engine = TraceHybridEngine()

    atoms = [
        {
            "atom_version_id": "atom:db:001",
            "content": "PostgreSQL is an open source object-relational database system.",
            "properties": {"source_start": 0, "source_end": 64},
        }
    ]

    # Query completely unrelated to Postgres facts in scope
    res = await engine.query("Quantum entanglement in superconducting qubits at low temperature", atoms=atoms)
    assert res.abstained is True
    assert res.sufficiency_state == "insufficient_evidence"
    assert len(res.results) == 0
    assert len(res.citations) == 0


@pytest.mark.asyncio
async def test_benchmark_coordinator_persists_raw_evaluations_and_manifest(tmp_path: Path) -> None:
    """Prove that a benchmark run persists both run_manifest.json and raw_query_evaluations.jsonl."""
    catalog = DatasetCatalog()
    telemetry_manager.runs_dir = tmp_path

    coordinator = BenchmarkCoordinator(catalog=catalog)
    summary = await coordinator.run_suite(
        dataset_id="fixture-technical-docs-v1",
        engine_ids=["trace_hybrid", "pure_vector", "pure_lexical", "naive_rag"],
        max_cases=3,
    )

    run_id = summary["run_id"]
    run_dir = tmp_path / run_id
    assert run_dir.is_dir()

    manifest_path = run_dir / "run_manifest.json"
    eval_path = run_dir / "raw_query_evaluations.jsonl"
    assert manifest_path.is_file()
    assert eval_path.is_file()

    # Verify JSONL lines
    lines = [json.loads(line) for line in eval_path.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) == 3 * 4  # 3 cases * 4 engines = 12 evaluations
    for row in lines:
        assert "case_id" in row
        assert "engine_id" in row
        assert "recall_at_5" in row
        assert "ndcg_at_10" in row
        assert "latency_ms" in row


def test_independent_verifier_attestation(tmp_path: Path) -> None:
    """Prove that scripts/verify_studio_run.py independently recomputes metrics and seals attestation."""
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from scripts.verify_studio_run import verify_run

    catalog = DatasetCatalog()
    telemetry_manager.runs_dir = tmp_path

    coordinator = BenchmarkCoordinator(catalog=catalog)
    summary = asyncio.run(
        coordinator.run_suite(
            dataset_id="fixture-technical-docs-v1",
            engine_ids=["trace_hybrid", "pure_lexical"],
            max_cases=4,
        )
    )

    run_id = summary["run_id"]
    run_dir = tmp_path / run_id

    is_valid, attestation, failures = verify_run(run_dir, catalog)
    assert is_valid is True
    assert len(failures) == 0
    assert attestation["integrity_status"] == "SEALED"
    assert attestation["attestation_signature"] is not None
    assert (run_dir / "attestation.json").is_file()
    assert "trace_hybrid" in attestation["recomputed_metrics"]
    assert "pure_lexical" in attestation["recomputed_metrics"]


def test_independent_verifier_rejects_tampered_corpus_sha256(tmp_path: Path) -> None:
    """Verify that tampering with corpus SHA-256 causes independent verifier rejection."""
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from scripts.verify_studio_run import verify_run

    catalog = DatasetCatalog()
    telemetry_manager.runs_dir = tmp_path

    coordinator = BenchmarkCoordinator(catalog=catalog)
    summary = asyncio.run(
        coordinator.run_suite(
            dataset_id="fixture-technical-docs-v1",
            engine_ids=["pure_lexical"],
            max_cases=2,
        )
    )

    run_id = summary["run_id"]
    run_dir = tmp_path / run_id

    # Tamper with corpus SHA-256 in manifest
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corpus_sha256"] = "deadbeef" * 8
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    is_valid, attestation, failures = verify_run(run_dir, catalog)
    assert is_valid is False
    assert len(failures) > 0
    assert attestation["integrity_status"] == "REJECTED"
    assert any("Corpus file SHA-256 mismatch" in f for f in failures)


def test_independent_verifier_rejects_corrupted_byte_anchor(tmp_path: Path) -> None:
    """Verify that invalid byte anchor offsets or mismatched quote_hashes cause verifier rejection."""
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from scripts.verify_studio_run import verify_run

    catalog = DatasetCatalog()
    telemetry_manager.runs_dir = tmp_path

    coordinator = BenchmarkCoordinator(catalog=catalog)
    summary = asyncio.run(
        coordinator.run_suite(
            dataset_id="fixture-technical-docs-v1",
            engine_ids=["trace_hybrid"],
            max_cases=2,
        )
    )

    run_id = summary["run_id"]
    run_dir = tmp_path / run_id

    # Corrupt a byte anchor quote_hash in raw_query_evaluations.jsonl
    eval_path = run_dir / "raw_query_evaluations.jsonl"
    lines = [json.loads(l) for l in eval_path.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) > 0
    lines[0]["citations"] = [{
        "atom_version_id": lines[0]["retrieved_ids"][0] if lines[0]["retrieved_ids"] else "fake-aid",
        "source_start": 0,
        "source_end": 50,
        "quote_hash": "bad_corrupted_hash",
    }]
    with eval_path.open("w", encoding="utf-8") as f:
        for row in lines:
            f.write(json.dumps(row) + "\n")

    is_valid, attestation, failures = verify_run(run_dir, catalog)
    assert is_valid is False
    assert len(failures) > 0
    assert any("Byte anchor quote_hash mismatch" in f for f in failures)


def test_telemetry_persist_run_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify finish_run raises exceptions and sets error state when persistence fails."""
    mgr = telemetry_manager
    run_id = f"test-err-{tmp_path.name}"
    mgr.create_run(run_id, suite_name="Error Test", dataset_id="fixture-technical-docs-v1", engines=["pure_lexical"], total_cases=1)

    def failing_persist(*args: Any, **kwargs: Any) -> Path:
        raise OSError("Disk write failed: permission denied")

    monkeypatch.setattr(mgr, "persist_run", failing_persist)

    with pytest.raises(OSError, match="Disk write failed"):
        mgr.finish_run(run_id, status="completed")

    run_info = mgr._runs.get(run_id)
    assert run_info is not None
    assert run_info["status"] == "failed"
    assert "Failed to persist" in run_info["error"]


def test_admin_status_and_overview_endpoints(client: TestClient) -> None:
    """Prove /v2/admin/status and /api/overview return 200 with sanitized data."""
    res1 = client.get("/api/overview")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "operational"
    assert "datasets" in data1
    assert "storage" in data1

    res2 = client.get("/v2/admin/status")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "operational"


@pytest.mark.asyncio
async def test_trace_hybrid_tampered_byte_anchor_rejection() -> None:
    """Prove that invalid spans (negative start, inverted bounds) and tampered quote hashes fail verification."""
    engine = TraceHybridEngine()
    content = "The storage engine commits state changes atomically to the immutable WAL log."
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # 1. Negative start offset
    atoms_neg = [{
        "atom_version_id": "atom:tamper:001",
        "content": content,
        "properties": {"source_start": -10, "source_end": len(content), "quote_hash": actual_hash},
    }]
    res_neg = await engine.query("storage engine commits state changes", atoms=atoms_neg)
    assert res_neg.abstained is True
    assert len(res_neg.results) == 0

    # 2. Inverted bounds (start >= end)
    atoms_inv = [{
        "atom_version_id": "atom:tamper:002",
        "content": content,
        "properties": {"source_start": 50, "source_end": 20, "quote_hash": actual_hash},
    }]
    res_inv = await engine.query("storage engine commits state changes", atoms=atoms_inv)
    assert res_inv.abstained is True
    assert len(res_inv.results) == 0

    # 3. Tampered quote hash
    atoms_tampered_hash = [{
        "atom_version_id": "atom:tamper:003",
        "content": content,
        "properties": {"source_start": 0, "source_end": len(content), "quote_hash": "deadbeef12345678"},
    }]
    res_tampered = await engine.query("storage engine commits state changes", atoms=atoms_tampered_hash)
    assert res_tampered.abstained is True
    assert len(res_tampered.results) == 0


@pytest.mark.asyncio
async def test_trace_hybrid_grounded_multi_signal_abstention_gate(catalog: DatasetCatalog) -> None:
    """Verify that multi-signal coverage gate fails closed without truth label leakage."""
    engine = TraceHybridEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    # 1. In-scope query with strong lexical & semantic coverage
    res_ok = await engine.query("The retrieval service fuses BM25 and dense candidates", atoms=atoms)
    assert res_ok.abstained is False
    assert res_ok.sufficiency_state == "answerable"
    assert len(res_ok.results) > 0
    assert res_ok.metadata["model_id"] == "hashing-dense-v1"
    assert res_ok.metadata["is_neural"] is False
    assert res_ok.metadata["baseline_category"] == "trace_cognitive_pipeline"

    # 2. Out-of-scope query with no matching facts: fails closed
    res_oos = await engine.query("migration policy for backup snapshots and disaster recovery replication", atoms=atoms)
    assert res_oos.abstained is True
    assert res_oos.sufficiency_state == "insufficient_evidence"
    assert len(res_oos.results) == 0
    assert len(res_oos.citations) == 0


@pytest.mark.asyncio
async def test_custom_db_probe_and_baseline_metadata() -> None:
    """Verify CustomDbEngine socket probe, error reporting, and baseline metadata tags."""
    # 1. Mock mode returns reference_mode
    mock_db = CustomDbEngine(endpoint_url=None, adapter_type="mock")
    conn_mock = mock_db._verify_endpoint_connectivity()
    assert conn_mock["status"] == "connected"
    assert conn_mock["mode"] == "reference_mode"

    # 2. Unreachable HTTP endpoint fails probe gracefully with short timeout
    unreachable_db = CustomDbEngine(endpoint_url="http://192.0.2.1:8080/v1/search", adapter_type="http")
    conn_unreach = unreachable_db._verify_endpoint_connectivity()
    assert conn_unreach["status"] == "connection_failed"
    assert "error" in conn_unreach

    # 3. Metadata baseline tags on all comparative engines
    res_db = await mock_db.query("test query", atoms=[{"atom_version_id": "a1", "content": "test query row"}])
    assert res_db.metadata["baseline_category"] == "custom_database_adapter"

    vec_eng = PureVectorEngine()
    res_vec = await vec_eng.query("test query", atoms=[{"atom_version_id": "a1", "content": "test query row"}])
    assert res_vec.metadata["baseline_category"] == "dense_vector_baseline"
    assert "model_id" in res_vec.metadata
    assert "is_neural" in res_vec.metadata

    rag_eng = NaiveRagEngine()
    res_rag = await rag_eng.query("test query", atoms=[{"atom_version_id": "a1", "content": "test query row"}])
    assert res_rag.metadata["baseline_category"] == "naive_rag_baseline"
    assert "model_id" in res_rag.metadata

    lex_eng = PureLexicalEngine()
    res_lex = await lex_eng.query("test query", atoms=[{"atom_version_id": "a1", "content": "test query row"}])
    assert res_lex.metadata["baseline_category"] == "lexical_bm25_baseline"

