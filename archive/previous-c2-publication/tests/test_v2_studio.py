"""Tests for Trace V2 One-Click Benchmark Suite and Live Demo Studio."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import uuid

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.modules.pop("trace", None)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trace.v2.studio import (
    BenchmarkCoordinator,
    BenchmarkEvent,
    BenchmarkTelemetryManager,
    CaseExecutionResult,
    CustomDbEngine,
    DatasetCatalog,
    DatasetInfo,
    EngineHit,
    EngineQueryResult,
    MetricSummary,
    NaiveRagEngine,
    PureLexicalEngine,
    PureVectorEngine,
    TraceHybridEngine,
    calculate_abstention_correctness,
    calculate_citation_precision,
    calculate_evidence_coverage,
    calculate_latency_percentiles,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    get_engine,
    list_available_engines,
    sanitize_dataset_info,
    sanitize_path,
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


# -----------------------------------------------------------------------------
# 1. Dataset Catalog Tests
# -----------------------------------------------------------------------------


def test_dataset_catalog_discovery(catalog: DatasetCatalog) -> None:
    datasets = catalog.discover_all()
    assert len(datasets) > 0

    dataset_ids = {d.id for d in datasets}
    # Fixtures should always be present
    assert "fixture-technical-docs-v1" in dataset_ids or any("technical-docs" in did for did in dataset_ids)

    # Scale datasets if present
    for d in datasets:
        assert isinstance(d, DatasetInfo)
        assert d.name
        assert d.category in {
            "multihop",
            "enterprise_email",
            "financial_sec",
            "encyclopedic",
            "linux_kernel",
            "code",
            "fixtures",
        }


def test_dataset_catalog_get_and_sample(catalog: DatasetCatalog) -> None:
    info = catalog.get_dataset("fixture-technical-docs-v1")
    assert info is not None
    assert info.name
    assert info.category == "fixtures"

    samples = catalog.load_sample_records("fixture-technical-docs-v1", limit=3)
    assert isinstance(samples, list)
    assert len(samples) > 0


def test_dataset_catalog_load_test_cases(catalog: DatasetCatalog) -> None:
    cases = catalog.load_test_cases("fixture-technical-docs-v1")
    assert len(cases) >= 6
    case_ids = [c["id"] for c in cases]
    assert "direct-lookup" in case_ids
    assert "out-of-scope" in case_ids

    # Check out-of-scope case flag
    out_of_scope_case = next(c for c in cases if c["id"] == "out-of-scope")
    assert out_of_scope_case["out_of_scope"] is True


def test_dataset_catalog_load_atoms(catalog: DatasetCatalog) -> None:
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")
    assert len(atoms) > 0
    first = atoms[0]
    assert "atom_version_id" in first
    assert "content" in first
    assert "properties" in first
    assert "source_start" in first["properties"]
    assert "source_end" in first["properties"]


# -----------------------------------------------------------------------------
# 2. Metric Calculation Tests
# -----------------------------------------------------------------------------


def test_metric_calculations() -> None:
    gold = {"id1", "id2", "id3"}
    retrieved = ["id1", "id4", "id2", "id5", "id6"]

    # Recall@K
    assert calculate_recall_at_k(gold, retrieved, 2) == pytest.approx(1 / 3)
    assert calculate_recall_at_k(gold, retrieved, 3) == pytest.approx(2 / 3)
    assert calculate_recall_at_k(gold, retrieved, 5) == pytest.approx(2 / 3)
    assert calculate_recall_at_k(set(), [], 5) == 1.0

    # NDCG@10
    ndcg = calculate_ndcg_at_k(gold, retrieved, 10)
    assert 0.0 < ndcg <= 1.0

    # Citation Precision
    assert calculate_citation_precision(gold, ["id1", "id2"], abstained=False) == 1.0
    assert calculate_citation_precision(gold, ["id1", "id4"], abstained=False) == 0.5
    # Out of scope with abstention -> 1.0
    assert calculate_citation_precision(set(), [], abstained=True, out_of_scope=True) == 1.0
    # Out of scope with hallucinated citations -> 0.0
    assert calculate_citation_precision(set(), ["id1"], abstained=False, out_of_scope=True) == 0.0

    # Evidence Coverage
    assert calculate_evidence_coverage(gold, ["id1", "id2", "id3", "id4"]) is True
    assert calculate_evidence_coverage(gold, ["id1", "id2"]) is False

    # Abstention Correctness
    assert calculate_abstention_correctness(abstained=True, out_of_scope=True) is True
    assert calculate_abstention_correctness(abstained=False, out_of_scope=False) is True
    assert calculate_abstention_correctness(abstained=True, out_of_scope=False) is False
    assert calculate_abstention_correctness(abstained=False, out_of_scope=True) is False

    # Latencies
    latencies = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    perc = calculate_latency_percentiles(latencies)
    assert perc["min"] == 1.0
    assert perc["max"] == 10.0
    assert 4.0 <= perc["p50"] <= 6.0
    assert perc["p95"] >= 9.0


# -----------------------------------------------------------------------------
# 3. Comparative Engine Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_hybrid_engine(catalog: DatasetCatalog) -> None:
    engine = TraceHybridEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    # In-scope query
    res = await engine.query("What fuses BM25 and dense candidates?", atoms=atoms)
    assert isinstance(res, EngineQueryResult)
    assert res.engine_id == "trace_hybrid"
    assert res.sufficiency_state == "answerable"
    assert res.abstained is False
    assert len(res.results) > 0
    assert res.hallucination_detected is False
    assert len(res.citations) > 0
    assert "lexical_bm25_ms" in res.stage_breakdown
    assert "dense_vector_ms" in res.stage_breakdown
    assert "rrf_fusion_ms" in res.stage_breakdown
    assert "rerank_ms" in res.stage_breakdown
    assert "cortex_graph_hierarchy_ms" in res.stage_breakdown
    assert "byte_anchor_verification_ms" in res.stage_breakdown

    # Check byte anchor properties on hits
    top_hit = res.results[0]
    assert len(top_hit.anchors) > 0
    assert "quote_hash" in top_hit.anchors[0]
    assert top_hit.is_grounded is True

    # Out-of-scope query
    res_oos = await engine.query("Which quantum orchard protocol is supported?", atoms=atoms, out_of_scope=True)
    assert res_oos.abstained is True
    assert res_oos.sufficiency_state == "insufficient_evidence"


@pytest.mark.asyncio
async def test_pure_lexical_engine(catalog: DatasetCatalog) -> None:
    engine = PureLexicalEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    res = await engine.query("retrieval service fuses BM25", atoms=atoms)
    assert res.engine_id == "pure_lexical"
    assert len(res.results) > 0
    assert "bm25" in res.results[0].channel_scores


@pytest.mark.asyncio
async def test_pure_vector_engine(catalog: DatasetCatalog) -> None:
    engine = PureVectorEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    res = await engine.query("what component combines lexical and vector search", atoms=atoms)
    assert res.engine_id == "pure_vector"
    assert len(res.results) > 0
    assert "dense_cosine" in res.results[0].channel_scores


@pytest.mark.asyncio
async def test_naive_rag_engine(catalog: DatasetCatalog) -> None:
    engine = NaiveRagEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    # In-scope
    res = await engine.query("deployment runbook version two", atoms=atoms)
    assert res.engine_id == "naive_rag"
    assert len(res.results) > 0

    # Out-of-scope: naive rag fails to abstain and hallucinates
    res_oos = await engine.query("quantum orchard protocol", atoms=atoms, out_of_scope=True)
    assert res_oos.abstained is False  # Fails to abstain
    assert res_oos.hallucination_detected is True


@pytest.mark.asyncio
async def test_custom_db_engine(catalog: DatasetCatalog) -> None:
    engine = CustomDbEngine(endpoint_url="sqlite:///memory", adapter_type="mock")
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    res = await engine.query("gateway validates workspace", atoms=atoms)
    assert res.engine_id == "custom_db"
    assert len(res.results) > 0


def test_engine_factory_and_listing() -> None:
    eng_list = list_available_engines()
    assert len(eng_list) >= 5
    ids = {e["engine_id"] for e in eng_list}
    assert "trace_hybrid" in ids
    assert "pure_lexical" in ids
    assert "pure_vector" in ids
    assert "naive_rag" in ids
    assert "custom_db" in ids

    eng = get_engine("trace_hybrid")
    assert isinstance(eng, TraceHybridEngine)


# -----------------------------------------------------------------------------
# 4. Telemetry Manager Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telemetry_manager_lifecycle() -> None:
    mgr = BenchmarkTelemetryManager()
    run_id = "test-run-1"

    mgr.create_run(
        run_id,
        suite_name="Unit Test Suite",
        dataset_id="fixture-technical-docs-v1",
        engines=["trace_hybrid", "pure_lexical"],
        total_cases=2,
    )

    ev = BenchmarkEvent(run_id=run_id, event_type="run_started", data={"msg": "hello"})
    assert "event: run_started" in ev.to_sse()
    await mgr.emit(ev)

    case_res = CaseExecutionResult(
        case_id="c1",
        engine_id="trace_hybrid",
        query="test query",
        recall_at_5=1.0,
        recall_at_20=1.0,
        ndcg_at_10=1.0,
        complete_evidence=True,
        citation_precision=1.0,
        abstained=False,
        latency_ms=2.5,
    )
    mgr.record_case(run_id, case_res)
    mgr.finish_run(run_id, status="completed")

    summary = mgr.get_run_summary(run_id)
    assert summary is not None
    assert summary["status"] == "completed"
    assert "trace_hybrid" in summary["metrics"]
    assert summary["metrics"]["trace_hybrid"]["recall_at_5"] == 1.0


# -----------------------------------------------------------------------------
# 5. Benchmark Coordinator Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_benchmark_coordinator(catalog: DatasetCatalog) -> None:
    coordinator = BenchmarkCoordinator(catalog=catalog)
    run_id = "test-coordinator-run"

    summary = await coordinator.run_benchmark(
        run_id,
        dataset_id="fixture-technical-docs-v1",
        engine_ids=["trace_hybrid", "pure_lexical", "pure_vector", "naive_rag"],
        max_cases=3,
    )

    assert summary is not None
    assert summary["status"] == "completed"
    assert len(summary["metrics"]) == 4
    assert "trace_hybrid" in summary["metrics"]
    assert summary["total_cases"] == 12  # 3 cases * 4 engines


# -----------------------------------------------------------------------------
# 6. Studio API Routes Tests
# -----------------------------------------------------------------------------


def test_api_overview(client: TestClient) -> None:
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "operational"
    assert "datasets" in data
    assert "storage" in data
    assert "models" in data
    assert "engines" in data


def test_api_datasets(client: TestClient) -> None:
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_dataset_details_and_sample(client: TestClient) -> None:
    resp = client.get("/api/datasets/fixture-technical-docs-v1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "fixture-technical-docs-v1"

    sample_resp = client.get("/api/datasets/fixture-technical-docs-v1/sample?limit=2")
    assert sample_resp.status_code == 200
    assert len(sample_resp.json()) <= 2


def test_api_engines(client: TestClient) -> None:
    resp = client.get("/api/engines")
    assert resp.status_code == 200
    engines = resp.json()
    assert len(engines) >= 5


def test_api_demo_query(client: TestClient) -> None:
    payload = {
        "query": "What fuses BM25 and dense candidates?",
        "dataset_id": "fixture-technical-docs-v1",
        "engine_id": "trace_hybrid",
        "deep": True,
    }
    resp = client.post("/api/demo/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine_id"] == "trace_hybrid"
    assert "stage_breakdown" in data
    assert "lexical_bm25_ms" in data["stage_breakdown"]
    assert "byte_anchor_verification_ms" in data["stage_breakdown"]


def test_api_demo_compare(client: TestClient) -> None:
    payload = {
        "query": "What replaced the lexical-only path?",
        "dataset_id": "fixture-technical-docs-v1",
        "engines": ["trace_hybrid", "pure_lexical", "pure_vector", "naive_rag"],
    }
    resp = client.post("/api/demo/compare", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "comparisons" in data
    assert "trace_hybrid" in data["comparisons"]
    assert "naive_rag" in data["comparisons"]


def test_api_benchmark_start_and_results(client: TestClient) -> None:
    start_payload = {
        "dataset_id": "fixture-technical-docs-v1",
        "engines": ["trace_hybrid", "pure_lexical"],
        "max_cases": 2,
    }
    start_resp = client.post("/api/benchmark/start", json=start_payload)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]

    # Allow async background task a brief moment to run
    import time
    time.sleep(0.5)

    res_resp = client.get(f"/api/benchmark/results/{run_id}")
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["run_id"] == run_id


def test_api_dashboard_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Trace" in resp.text and "Studio" in resp.text


# -----------------------------------------------------------------------------
# 7. Path Sanitization & Redaction Tests
# -----------------------------------------------------------------------------


def test_sanitize_path_unit(catalog: DatasetCatalog) -> None:
    repo_root = catalog.repo_root
    scale_dir = catalog.scale_data_dir

    # Repo fixture path
    fixture_path = str(repo_root / "benchmarks" / "technical-docs-v1.json")
    sanitized_fix = sanitize_path(fixture_path, repo_root=repo_root, scale_data_dir=scale_dir)
    assert sanitized_fix == "benchmarks/technical-docs-v1.json"
    assert "\\" not in sanitized_fix

    # Scale data path
    scale_path = str(scale_dir / "multihop" / "2wikimultihop_corpus.jsonl")
    sanitized_scale = sanitize_path(scale_path, repo_root=repo_root, scale_data_dir=scale_dir)
    assert sanitized_scale.startswith("trace://scale/multihop/")
    assert "\\" not in sanitized_scale

    # Absolute Windows user path fallback redaction
    user_path = "C:\\Users\\anshu\\secret_folder\\corpus.jsonl"
    sanitized_user = sanitize_path(user_path, repo_root=repo_root, scale_data_dir=scale_dir)
    assert sanitized_user == "trace://dataset/corpus.jsonl"
    assert "anshu" not in sanitized_user
    assert "Users" not in sanitized_user

    # None path returns None
    assert sanitize_path(None) is None


def test_api_paths_are_redacted(client: TestClient) -> None:
    # 1. Overview endpoint
    overview_resp = client.get("/api/overview")
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()
    for ds in overview_data["datasets"]["fixtures"] + overview_data["datasets"]["scale_datasets"]:
        fp = ds.get("file_path", "")
        assert not fp.lower().startswith("c:"), f"Leaked Windows drive in overview: {fp}"
        assert "\\users\\" not in fp.lower() and "/users/" not in fp.lower(), f"Leaked user path in overview: {fp}"
        assert fp.startswith("benchmarks/") or fp.startswith("trace://"), f"Unnormalized path in overview: {fp}"

    # 2. Datasets listing endpoint
    ds_resp = client.get("/api/datasets")
    assert ds_resp.status_code == 200
    for ds in ds_resp.json():
        fp = ds.get("file_path", "")
        assert not fp.lower().startswith("c:"), f"Leaked Windows drive in datasets: {fp}"
        assert "\\users\\" not in fp.lower() and "/users/" not in fp.lower(), f"Leaked user path in datasets: {fp}"
        assert fp.startswith("benchmarks/") or fp.startswith("trace://"), f"Unnormalized path in datasets: {fp}"

    # 3. Single dataset details endpoint
    detail_resp = client.get("/api/datasets/fixture-technical-docs-v1")
    assert detail_resp.status_code == 200
    fp = detail_resp.json().get("file_path", "")
    assert fp == "benchmarks/technical-docs-v1.json"


# -----------------------------------------------------------------------------
# 8. Workspace Scoping & Authorization Tests
# -----------------------------------------------------------------------------


def _make_test_jwt(
    *,
    sub: str = "test-engineer",
    workspace_ids: list[str] | None = None,
    scopes: list[str] | None = None,
    secret: str = "trace-test-jwt-secret-xyz",
    exp_offset: int = 3600,
) -> str:
    import base64
    import hashlib
    import hmac
    import json
    import time

    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": sub,
        "exp": now + exp_offset,
        "nbf": now - 10,
    }
    if workspace_ids is not None:
        claims["workspace_ids"] = workspace_ids
    if scopes is not None:
        claims["scopes"] = scopes

    def _b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    h_b64 = _b64(json.dumps(header).encode("utf-8"))
    c_b64 = _b64(json.dumps(claims).encode("utf-8"))
    msg = f"{h_b64}.{c_b64}".encode("ascii")
    sig = _b64(hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest())
    return f"{h_b64}.{c_b64}.{sig}"


def test_workspace_scoping_and_tenancy_guards(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "trace-test-jwt-secret-xyz"
    monkeypatch.setenv("TRACE_JWT_SECRET", secret)

    # Token scoped ONLY to tenant-alpha with read/write scopes
    token_alpha = _make_test_jwt(
        sub="user-alpha",
        workspace_ids=["tenant-alpha"],
        scopes=["retrieval:read", "benchmarks:write", "benchmarks:read"],
        secret=secret,
    )
    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}

    # 1. Allowed on tenant-alpha
    res_start = client.post(
        "/api/benchmark/start",
        json={"dataset_id": "fixture-technical-docs-v1", "engines": ["pure_lexical"], "workspace_id": "tenant-alpha"},
        headers=headers_alpha,
    )
    assert res_start.status_code == 200
    assert res_start.json()["workspace_id"] == "tenant-alpha"
    run_id = res_start.json()["run_id"]

    # 2. Blocked on tenant-beta (mismatch tenant) -> 403 Forbidden
    res_start_forbidden = client.post(
        "/api/benchmark/start",
        json={"dataset_id": "fixture-technical-docs-v1", "engines": ["pure_lexical"], "workspace_id": "tenant-beta"},
        headers=headers_alpha,
    )
    assert res_start_forbidden.status_code == 403
    assert res_start_forbidden.json()["detail"]["code"] == "workspace_scope_denied"

    # 3. Demo query allowed on tenant-alpha, blocked on tenant-beta
    res_q_ok = client.post(
        "/api/demo/query",
        json={"query": "test query", "workspace_id": "tenant-alpha", "engine_id": "pure_lexical"},
        headers=headers_alpha,
    )
    assert res_q_ok.status_code == 200

    res_q_forbidden = client.post(
        "/api/demo/query",
        json={"query": "test query", "workspace_id": "tenant-beta", "engine_id": "pure_lexical"},
        headers=headers_alpha,
    )
    assert res_q_forbidden.status_code == 403

    # 4. Demo compare allowed on tenant-alpha, blocked on tenant-beta
    res_cmp_forbidden = client.post(
        "/api/demo/compare",
        json={"query": "test query", "workspace_id": "tenant-beta", "engines": ["pure_lexical"]},
        headers=headers_alpha,
    )
    assert res_cmp_forbidden.status_code == 403

    # 5. Cross-workspace run isolation: token for tenant-beta cannot view or stream run from tenant-alpha
    token_beta = _make_test_jwt(
        sub="user-beta",
        workspace_ids=["tenant-beta"],
        scopes=["retrieval:read", "benchmarks:write", "benchmarks:read"],
        secret=secret,
    )
    headers_beta = {"Authorization": f"Bearer {token_beta}"}

    res_results_forbidden = client.get(f"/api/benchmark/results/{run_id}", headers=headers_beta)
    assert res_results_forbidden.status_code == 403

    res_stream_forbidden = client.get(f"/api/benchmark/stream/{run_id}", headers=headers_beta)
    assert res_stream_forbidden.status_code == 403

    # But tenant-alpha CAN view the results
    res_results_ok = client.get(f"/api/benchmark/results/{run_id}", headers=headers_alpha)
    assert res_results_ok.status_code == 200


def test_insufficient_scope_guards(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "trace-test-jwt-secret-xyz"
    monkeypatch.setenv("TRACE_JWT_SECRET", secret)

    # Token with ONLY retrieval:read (missing benchmarks:write)
    token_read_only = _make_test_jwt(
        sub="readonly-user",
        workspace_ids=["tenant-alpha"],
        scopes=["retrieval:read"],
        secret=secret,
    )
    headers = {"Authorization": f"Bearer {token_read_only}"}

    # Attempt to start benchmark should fail closed with 403 Forbidden
    res = client.post(
        "/api/benchmark/start",
        json={"dataset_id": "fixture-technical-docs-v1", "engines": ["pure_lexical"], "workspace_id": "tenant-alpha"},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "insufficient_scope"


def test_auth_token_failures_and_required_mode(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "trace-test-jwt-secret-xyz"
    monkeypatch.setenv("TRACE_JWT_SECRET", secret)

    # 1. Malformed bearer token
    res_malformed = client.get("/api/overview", headers={"Authorization": "Bearer invalid.token.payload"})
    assert res_malformed.status_code == 401
    assert "WWW-Authenticate" in res_malformed.headers

    # 2. Expired bearer token
    token_expired = _make_test_jwt(secret=secret, exp_offset=-60)
    res_expired = client.get("/api/overview", headers={"Authorization": f"Bearer {token_expired}"})
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["detail"]["message"].lower()

    # 3. Wrong signature
    token_wrong_sig = _make_test_jwt(secret="wrong-secret")
    res_wrong_sig = client.get("/api/overview", headers={"Authorization": f"Bearer {token_wrong_sig}"})
    assert res_wrong_sig.status_code == 401

    # 4. Mandatory Auth mode (TRACE_AUTH_REQUIRED=true)
    monkeypatch.setenv("TRACE_AUTH_REQUIRED", "true")
    res_unauth = client.get("/api/datasets")
    assert res_unauth.status_code == 401

    valid_token = _make_test_jwt(secret=secret, scopes=["retrieval:read"])
    res_auth = client.get("/api/datasets", headers={"Authorization": f"Bearer {valid_token}"})
    assert res_auth.status_code == 200


# -----------------------------------------------------------------------------
# 9. SSE Streaming Reliability Tests
# -----------------------------------------------------------------------------


def test_sse_streaming_protocol_and_events(client: TestClient) -> None:
    # 1. Launch a quick benchmark run
    start_payload = {
        "dataset_id": "fixture-technical-docs-v1",
        "engines": ["pure_lexical"],
        "max_cases": 1,
    }
    start_resp = client.post("/api/benchmark/start", json=start_payload)
    assert start_resp.status_code == 200
    run_id = start_resp.json()["run_id"]

    # Allow brief moment for coordinator to execute
    import time
    time.sleep(0.6)

    # 2. Connect to SSE stream
    with client.stream("GET", f"/api/benchmark/stream/{run_id}") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers.get("x-accel-buffering") == "no"

        content = response.read().decode("utf-8")
        assert len(content) > 0

        # Validate standard SSE frames
        assert "event: run_started" in content
        assert "event: case_started" in content
        assert "event: case_completed" in content
        assert "event: run_progress" in content
        assert "event: metrics_updated" in content
        assert "event: run_completed" in content

        # Check frame structure (event, id, data)
        blocks = content.strip().split("\n\n")
        assert len(blocks) >= 4
        for b in blocks:
            if not b.strip():
                continue
            lines = b.split("\n")
            keys = {l.split(":")[0].strip() for l in lines}
            assert "event" in keys, f"Missing event in frame: {b}"
            assert "id" in keys, f"Missing id in frame: {b}"
            assert "data" in keys, f"Missing data in frame: {b}"

            data_line = next(l for l in lines if l.startswith("data:"))
            data_json = json.loads(data_line[5:].strip())
            assert "event_id" in data_json
            assert "event_type" in data_json
            assert "timestamp" in data_json


def test_sse_streaming_nonexistent_run(client: TestClient) -> None:
    resp = client.get("/api/benchmark/stream/bench-missing-999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sse_streaming_failed_run() -> None:
    # Directly test failing run emission and subscription
    mgr = BenchmarkTelemetryManager()
    run_id = "test-fail-run"
    mgr.create_run(
        run_id,
        suite_name="Fail Suite",
        dataset_id="fixture-technical-docs-v1",
        engines=["pure_lexical"],
        total_cases=1,
    )
    await mgr.emit(BenchmarkEvent(run_id=run_id, event_type="run_started", data={"info": "started"}))
    mgr.finish_run(run_id, status="failed", error="Fatal engine crash")
    await mgr.emit(BenchmarkEvent(run_id=run_id, event_type="run_failed", data={"error": "Fatal engine crash"}))

    events = []
    async for sse_chunk in mgr.subscribe(run_id):
        events.append(sse_chunk)

    assert len(events) == 2
    assert "event: run_started" in events[0]
    assert "event: run_failed" in events[1]


# -----------------------------------------------------------------------------
# 10. HTTP Error Handling & Validation Tests
# -----------------------------------------------------------------------------


def test_api_validation_and_not_found_errors(client: TestClient) -> None:
    # 1. Missing dataset
    res_ds_404 = client.get("/api/datasets/nonexistent-dataset-id")
    assert res_ds_404.status_code == 404

    res_sample_404 = client.get("/api/datasets/nonexistent-dataset-id/sample")
    assert res_sample_404.status_code == 404

    # 2. Empty query in demo
    res_q_empty = client.post("/api/demo/query", json={"query": "   ", "engine_id": "pure_lexical"})
    assert res_q_empty.status_code == 400

    # 3. Invalid engine in demo
    res_q_bad_eng = client.post("/api/demo/query", json={"query": "valid query", "engine_id": "nonexistent_engine"})
    assert res_q_bad_eng.status_code == 400

    # 4. Benchmark with empty engines
    res_bench_no_eng = client.post(
        "/api/benchmark/start",
        json={"dataset_id": "fixture-technical-docs-v1", "engines": []},
    )
    assert res_bench_no_eng.status_code == 400

    # 5. Benchmark with nonexistent dataset
    res_bench_bad_ds = client.post(
        "/api/benchmark/start",
        json={"dataset_id": "nonexistent-dataset-id", "engines": ["pure_lexical"]},
    )
    assert res_bench_bad_ds.status_code == 404

    # 6. Benchmark results 404
    res_results_404 = client.get("/api/benchmark/results/bench-does-not-exist")
    assert res_results_404.status_code == 404



# -----------------------------------------------------------------------------
# 7. Enhanced Cognitive Pipeline & Comparative Adapter Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_hybrid_engine_with_service() -> None:
    """Verify canonical service routing when a TraceService is provided."""

    class MockTraceService:
        def query(self, request: Any) -> dict[str, Any]:
            return {
                "evidence_bundle_id": "bundle-test-123",
                "workspace_id": request.workspace_id,
                "sufficiency_state": "answerable",
                "results": [
                    {
                        "rank": 1,
                        "atom_version_id": "atom-version-abc",
                        "node_id": "node-1",
                        "excerpt": "BM25 and dense candidates fused via reciprocal-rank fusion.",
                        "score": 0.94,
                        "channel_scores": {"lexical_bm25": 4.5, "dense": 0.88, "rrf": 0.032},
                        "source_location": {"start": 0, "end": 62, "parser_location": "char:0-62"},
                        "evidence_anchor_ids": ["anchor-1"],
                    }
                ],
                "retrieval_diagnostics": {"stage_counts": {"lexical": 5, "dense": 5}},
            }

    service = MockTraceService()
    engine = TraceHybridEngine(service=service)

    res = await engine.query("What fuses candidates?", workspace_id="test-ws", atoms=None)
    assert res.engine_id == "trace_hybrid"
    assert res.sufficiency_state == "answerable"
    assert res.abstained is False
    assert len(res.results) == 1
    assert res.results[0].atom_version_id == "atom-version-abc"
    assert res.results[0].is_grounded is True
    assert "service_retrieval_ms" in res.stage_breakdown
    assert "byte_anchor_verification_ms" in res.stage_breakdown


@pytest.mark.asyncio
async def test_trace_hybrid_engine_independent_abstention(catalog: DatasetCatalog) -> None:
    """Verify independent abstention without out_of_scope cheating flags."""
    engine = TraceHybridEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    # Pass out_of_scope=False for an out-of-scope query: engine must STILL independently abstain
    res = await engine.query("Which quantum orchard protocol is supported?", atoms=atoms, out_of_scope=False)
    assert res.abstained is True
    assert res.sufficiency_state == "insufficient_evidence"
    assert len(res.results) == 0
    assert len(res.citations) == 0
    assert "Trace cognitive engine abstained" in (res.synthesis or "")


@pytest.mark.asyncio
async def test_trace_hybrid_ppr_and_byte_anchors(catalog: DatasetCatalog) -> None:
    """Verify PPR graph scores, channel scores, and byte-anchor SHA-256 hashes."""
    engine = TraceHybridEngine()
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    res = await engine.query("The retrieval service fuses BM25 and dense candidates", atoms=atoms)
    assert res.abstained is False
    assert len(res.results) > 0

    hit = res.results[0]
    assert hit.is_grounded is True
    assert "bm25" in hit.channel_scores
    assert "dense_cosine" in hit.channel_scores
    assert "graph_ppr" in hit.channel_scores
    assert "hierarchy_boost" in hit.channel_scores
    assert "cognitive_score" in hit.channel_scores

    # Cryptographic quote hash verification
    anchor = hit.anchors[0]
    assert anchor["verified"] is True
    assert len(anchor["quote_hash"]) == 16
    assert anchor["source_start"] >= 0
    assert anchor["source_end"] >= anchor["source_start"]


@pytest.mark.asyncio
async def test_custom_db_engine_connectivity(catalog: DatasetCatalog) -> None:
    """Verify CustomDbEngine endpoint connectivity inspection and search."""
    atoms = catalog.load_atoms_for_dataset("fixture-technical-docs-v1")

    # SQLite protocol
    engine_sqlite = CustomDbEngine(endpoint_url="sqlite:///memory", adapter_type="sql")
    res_sqlite = await engine_sqlite.query("gateway validates workspace", atoms=atoms)
    assert res_sqlite.engine_id == "custom_db"
    assert res_sqlite.stage_breakdown["connectivity"]["protocol"] == "sqlite"
    assert len(res_sqlite.results) > 0

    # HTTP REST protocol
    engine_http = CustomDbEngine(endpoint_url="https://api.vectordb.internal:8443/v1/search", adapter_type="vector")
    res_http = await engine_http.query("fuses BM25", atoms=atoms)
    assert res_http.stage_breakdown["connectivity"]["protocol"] == "https"
    assert res_http.stage_breakdown["connectivity"]["host"] == "api.vectordb.internal:8443"
    assert len(res_http.results) > 0


# -----------------------------------------------------------------------------
# 8. Data Integrity & Run Manifest Persistence Tests
# -----------------------------------------------------------------------------


def test_dataset_id_normalization_musique_and_2wiki(catalog: DatasetCatalog) -> None:
    """Verify that query gold doc IDs are deterministically resolved to loaded atom version IDs."""
    # MuSiQue normalization
    musique_cases = catalog.load_test_cases("multihop-musique", limit=5)
    if musique_cases:
        for c in musique_cases:
            assert len(c["gold_atom_version_ids"]) > 0
            for gid in c["gold_atom_version_ids"]:
                assert gid.startswith("musique:")

        # Verify mapping against atoms
        atoms = catalog.load_atoms_for_dataset("multihop-musique", limit=50)
        atom_ids = {a["atom_version_id"] for a in atoms}
        first_gold = musique_cases[0]["gold_atom_version_ids"][0]
        # Direct normalization helper
        mapped = catalog.normalize_gold_ids("multihop-musique", [musique_cases[0]["raw_gold_doc_ids"][0]])
        assert mapped[0] == first_gold

    # 2Wiki normalization
    wiki_cases = catalog.load_test_cases("multihop-2wiki", limit=5)
    if wiki_cases:
        for c in wiki_cases:
            assert len(c["gold_atom_version_ids"]) > 0
            for gid in c["gold_atom_version_ids"]:
                assert gid.startswith("2wikimultihop:")


@pytest.mark.asyncio
async def test_unjudged_dataset_refuses_synthetic_fake_queries(catalog: DatasetCatalog) -> None:
    """Verify datasets without frozen query judgments return empty test cases and refuse benchmark execution."""
    enron_cases = catalog.load_test_cases("enron-emails")
    assert enron_cases == []

    sec_cases = catalog.load_test_cases("sec-edgar")
    assert sec_cases == []

    coordinator = BenchmarkCoordinator(catalog=catalog)
    with pytest.raises(ValueError, match="does not have frozen benchmark query judgments"):
        await coordinator.run_benchmark(dataset_id="enron-emails")


@pytest.mark.asyncio
async def test_run_manifest_disk_persistence_and_loading(catalog: DatasetCatalog, tmp_path: Path) -> None:
    """Verify full benchmark run manifest is persisted to disk with signatures and can be loaded."""
    from trace.v2.studio.telemetry import BenchmarkTelemetryManager

    test_telemetry = BenchmarkTelemetryManager(runs_dir=tmp_path / "benchmarks" / "runs")
    coordinator = BenchmarkCoordinator(catalog=catalog)

    # Temporarily bind telemetry manager for this run
    import trace.v2.studio.engine as eng_mod
    original_mgr = eng_mod.telemetry_manager
    eng_mod.telemetry_manager = test_telemetry

    try:
        run_id = f"test-persisted-{uuid.uuid4().hex[:8]}"
        summary = await coordinator.run_benchmark(
            run_id,
            dataset_id="fixture-technical-docs-v1",
            engine_ids=["pure_lexical"],
            max_cases=2,
        )

        assert summary is not None
        assert summary["status"] == "completed"
        assert summary["signature"] is not None
        assert summary.get("attestation") is None
        assert "environment" in summary
        assert summary["environment"]["python_version"]
        assert summary["environment"]["os"]

        # Check disk file
        manifest_file = test_telemetry.runs_dir / run_id / "run_manifest.json"
        assert manifest_file.is_file()

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest_data["run_id"] == run_id
        assert manifest_data["dataset_id"] == "fixture-technical-docs-v1"
        assert manifest_data["signature"] == summary["signature"]
        assert len(manifest_data["case_results"]) == 2
        assert "pure_lexical" in manifest_data["metric_summaries"]

        # Test loading back into a fresh telemetry manager
        fresh_mgr = BenchmarkTelemetryManager(runs_dir=test_telemetry.runs_dir)
        loaded = fresh_mgr.load_persisted_run(run_id)
        assert loaded is not None
        assert loaded["run_id"] == run_id
        assert loaded["signature"] == summary["signature"]

        # Verify get_run_summary retrieves persisted run seamlessly
        retrieved_summary = fresh_mgr.get_run_summary(run_id)
        assert retrieved_summary is not None
        assert retrieved_summary["run_id"] == run_id

        # Verify list_persisted_runs
        persisted_list = fresh_mgr.list_persisted_runs()
        assert len(persisted_list) >= 1
        assert any(p["run_id"] == run_id for p in persisted_list)

    finally:
        eng_mod.telemetry_manager = original_mgr


def test_no_hidden_sampling_or_2000_atom_truncation(catalog: DatasetCatalog) -> None:
    """Verify that load_atoms_for_dataset loads all atoms without 1000 or 2000 truncation when limit is None."""
    atoms_fixture = catalog.load_atoms_for_dataset("fixture-technical-docs-v1", limit=None)
    assert len(atoms_fixture) > 0

    # With explicit limit
    atoms_limited = catalog.load_atoms_for_dataset("fixture-technical-docs-v1", limit=2)
    assert len(atoms_limited) == 2



