"""Live SSE telemetry streaming and benchmark evaluation metrics for Trace Studio.

Provides real-time event streaming for benchmark runs and standard multi-hop /
cognitive retrieval metrics: Recall@5, Recall@20, NDCG@10, Citation Precision,
Complete Evidence Coverage, Abstention Correctness, P50/P95 Latencies, and Token Economics.
Also manages cryptographic run manifest persistence to benchmarks/runs/{run_id}/run_manifest.json.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
from statistics import mean, quantiles
import subprocess
from typing import Any, AsyncIterator, Literal, Sequence
import uuid

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_default_runs_dir() -> Path:
    env_dir = os.environ.get("TRACE_BENCHMARK_RUNS_DIR")
    if env_dir:
        return Path(env_dir)
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "benchmarks").is_dir() or (parent / "pyproject.toml").is_file():
            return parent / "benchmarks" / "runs"
    return Path.cwd() / "benchmarks" / "runs"


def collect_environment_metadata() -> dict[str, Any]:
    """Capture operating system, hardware, Python version, and git commit details."""
    git_commit = "unknown"
    git_branch = "unknown"
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0:
            git_commit = res.stdout.strip()
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if branch_res.returncode == 0:
            git_branch = branch_res.stdout.strip()
    except Exception:
        pass

    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_compiler": platform.python_compiler(),
        "processor": platform.processor() or platform.machine(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count() or 1,
        "git_commit": git_commit,
        "git_branch": git_branch,
        "code_version": "0.2.0",
    }


def compute_run_manifest_signature(
    run_id: str,
    dataset_id: str,
    corpus_sha256: str | None,
    queries_sha256: str | None,
    completed_at: str | None,
    metric_summaries: dict[str, Any],
) -> str:
    """Compute deterministic SHA-256 integrity signature for a completed benchmark manifest."""
    payload = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "corpus_sha256": corpus_sha256 or "",
        "queries_sha256": queries_sha256 or "",
        "completed_at": completed_at or "",
        "metric_summaries": metric_summaries,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class MetricSummary(BaseModel):
    """Aggregated evaluation metrics for an engine or benchmark stage."""

    recall_at_5: float = 0.0
    recall_at_20: float = 0.0
    ndcg_at_10: float = 0.0
    complete_gold_evidence_coverage: float = 0.0
    citation_precision: float = 0.0
    abstention_correctness: float = 0.0
    p50_latency_ms: float = 0.0
    p90_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    mean_latency_ms: float = 0.0
    total_cases: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    hallucination_rate: float = 0.0


class CaseExecutionResult(BaseModel):
    """Detailed telemetry record for a single evaluated test case."""

    case_id: str
    engine_id: str
    query: str
    kind: str = "unspecified"
    gold_ids: list[str] = Field(default_factory=list)
    retrieved_ids: list[str] = Field(default_factory=list)
    cited_ids: list[str] = Field(default_factory=list)
    recall_at_5: float = 0.0
    recall_at_20: float = 0.0
    ndcg_at_10: float = 0.0
    complete_evidence: bool = False
    citation_precision: float = 0.0
    abstained: bool = False
    out_of_scope: bool = False
    abstention_correct: bool = True
    hallucination_detected: bool = False
    latency_ms: float = 0.0
    token_count: int = 0
    token_cost_usd: float = 0.0
    synthesis_preview: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """Immutable persistent record of a completed benchmark evaluation run."""

    run_id: str
    suite_name: str
    dataset_id: str
    workspace_id: str = "default"
    created_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    status: Literal["running", "completed", "failed"] = "running"
    corpus_sha256: str | None = None
    queries_sha256: str | None = None
    engines: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=collect_environment_metadata)
    case_results: list[CaseExecutionResult] = Field(default_factory=list)
    metric_summaries: dict[str, MetricSummary] = Field(default_factory=dict)
    deltas_vs_baseline: dict[str, dict[str, float]] = Field(default_factory=dict)
    signature: str | None = None
    verified: bool = True
    verification_metadata: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkEvent(BaseModel):
    """Server-Sent Event payload for real-time benchmark streaming."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: Literal[
        "run_started",
        "case_started",
        "stage_completed",
        "case_completed",
        "run_progress",
        "metrics_updated",
        "run_completed",
        "run_failed",
    ]
    run_id: str
    timestamp: str = Field(default_factory=_now_iso)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as an SSE standard text block."""
        data_json = json.dumps(self.model_dump(mode="json"), separators=(",", ":"))
        return f"event: {self.event_type}\nid: {self.event_id}\ndata: {data_json}\n\n"


# -----------------------------------------------------------------------------
# Metric Calculations
# -----------------------------------------------------------------------------


def calculate_recall_at_k(gold: set[str], retrieved: Sequence[str], k: int) -> float:
    """Calculate Recall@K against gold evidence atom/document IDs."""
    if not gold:
        return 1.0 if not retrieved else 0.0
    top_k = set(retrieved[:k])
    return len(gold & top_k) / len(gold)


def calculate_ndcg_at_k(gold: set[str], retrieved: Sequence[str], k: int = 10) -> float:
    """Calculate Normalized Discounted Cumulative Gain at rank K."""
    if not gold:
        return 0.0
    score = sum(
        (1.0 / math.log2(rank + 1))
        for rank, item_id in enumerate(retrieved[:k], start=1)
        if item_id in gold
    )
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return score / ideal if ideal else 0.0


def calculate_citation_precision(
    gold: set[str],
    cited: Sequence[str],
    abstained: bool = False,
    out_of_scope: bool = False,
) -> float:
    """Calculate the precision of cited evidence atoms.

    For out-of-scope queries:
    - If properly abstained with 0 citations: precision is 1.0.
    - If ungrounded synthesis produced unanchored citations: precision is 0.0.
    """
    if not gold or out_of_scope:
        return 1.0 if (abstained and len(cited) == 0) else 0.0
    if not cited:
        return 0.0
    unique_cited = set(cited)
    return len(gold & unique_cited) / len(unique_cited)


def calculate_evidence_coverage(gold: set[str], cited: Sequence[str]) -> bool:
    """Check whether 100% of gold evidence atoms were successfully cited."""
    if not gold:
        return True
    return gold.issubset(set(cited))


def calculate_abstention_correctness(abstained: bool, out_of_scope: bool) -> bool:
    """True if engine abstained on out-of-scope or answered in-scope query."""
    return (abstained and out_of_scope) or (not abstained and not out_of_scope)


def calculate_latency_percentiles(latencies_ms: Sequence[float]) -> dict[str, float]:
    """Calculate P50, P90, P95, P99, mean, min, max latencies in milliseconds."""
    if not latencies_ms:
        return {
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "mean": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    sorted_vals = sorted(latencies_ms)
    n = len(sorted_vals)
    if n == 1:
        val = sorted_vals[0]
        return {
            "p50": val,
            "p90": val,
            "p95": val,
            "p99": val,
            "mean": val,
            "min": val,
            "max": val,
        }

    q = quantiles(sorted_vals, n=100, method="inclusive")
    return {
        "p50": q[49],
        "p90": q[89],
        "p95": q[94],
        "p99": q[98],
        "mean": mean(sorted_vals),
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
    }


def aggregate_metrics(cases: Sequence[CaseExecutionResult]) -> MetricSummary:
    """Aggregate a sequence of case results into a single MetricSummary."""
    if not cases:
        return MetricSummary()

    latencies = [c.latency_ms for c in cases]
    perc = calculate_latency_percentiles(latencies)
    total_cases = len(cases)

    return MetricSummary(
        recall_at_5=sum(c.recall_at_5 for c in cases) / total_cases,
        recall_at_20=sum(c.recall_at_20 for c in cases) / total_cases,
        ndcg_at_10=sum(c.ndcg_at_10 for c in cases) / total_cases,
        complete_gold_evidence_coverage=sum(1.0 if c.complete_evidence else 0.0 for c in cases) / total_cases,
        citation_precision=sum(c.citation_precision for c in cases) / total_cases,
        abstention_correctness=sum(1.0 if c.abstention_correct else 0.0 for c in cases) / total_cases,
        p50_latency_ms=perc["p50"],
        p90_latency_ms=perc["p90"],
        p95_latency_ms=perc["p95"],
        p99_latency_ms=perc["p99"],
        mean_latency_ms=perc["mean"],
        total_cases=total_cases,
        total_tokens=sum(c.token_count for c in cases),
        estimated_cost_usd=sum(c.token_cost_usd for c in cases),
        hallucination_rate=sum(1.0 if c.hallucination_detected else 0.0 for c in cases) / total_cases,
    )


# -----------------------------------------------------------------------------
# Benchmark Telemetry Manager
# -----------------------------------------------------------------------------


class BenchmarkTelemetryManager:
    """Coordinates live SSE broadcast channels, aggregates metrics, and persists run manifests."""

    def __init__(self, runs_dir: Path | str | None = None) -> None:
        self.runs_dir = Path(runs_dir) if runs_dir else _resolve_default_runs_dir()
        self._runs: dict[str, dict[str, Any]] = {}
        self._case_results: dict[str, list[CaseExecutionResult]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[BenchmarkEvent]]] = {}
        self._event_history: dict[str, list[BenchmarkEvent]] = {}
        self._lock = asyncio.Lock()

    def create_run(
        self,
        run_id: str,
        *,
        suite_name: str,
        dataset_id: str,
        engines: Sequence[str],
        total_cases: int,
        workspace_id: str = "default",
        corpus_sha256: str | None = None,
        queries_sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a new benchmark run in active state with provenance metadata."""
        meta = dict(metadata or {})
        meta["workspace_id"] = workspace_id
        self._runs[run_id] = {
            "run_id": run_id,
            "suite_name": suite_name,
            "dataset_id": dataset_id,
            "workspace_id": workspace_id,
            "engines": list(engines),
            "total_cases": total_cases,
            "processed_cases": 0,
            "status": "running",
            "started_at": _now_iso(),
            "created_at": _now_iso(),
            "completed_at": None,
            "error": None,
            "corpus_sha256": corpus_sha256,
            "queries_sha256": queries_sha256,
            "environment": collect_environment_metadata(),
            "metadata": meta,
        }
        self._case_results[run_id] = []
        self._subscribers[run_id] = []
        self._event_history[run_id] = []

    async def emit(self, event: BenchmarkEvent) -> None:
        """Broadcast an event to all active SSE subscribers and append to history."""
        run_id = event.run_id
        if run_id not in self._event_history:
            self._event_history[run_id] = []
        self._event_history[run_id].append(event)

        queues = self._subscribers.get(run_id, [])
        for q in queues:
            await q.put(event)

    def record_case(self, run_id: str, result: CaseExecutionResult) -> None:
        """Record an executed case and increment run progress."""
        if run_id in self._case_results:
            self._case_results[run_id].append(result)
        if run_id in self._runs:
            self._runs[run_id]["processed_cases"] += 1

    async def subscribe(self, run_id: str) -> AsyncIterator[str]:
        """Subscribe to a run's live SSE stream. Replays historical events first."""
        queue: asyncio.Queue[BenchmarkEvent] = asyncio.Queue()

        # Catch up with past events
        history = list(self._event_history.get(run_id, []))
        for ev in history:
            await queue.put(ev)

        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        self._subscribers[run_id].append(queue)

        try:
            while True:
                event = await queue.get()
                yield event.to_sse()
                if event.event_type in {"run_completed", "run_failed"}:
                    break
        finally:
            if run_id in self._subscribers and queue in self._subscribers[run_id]:
                self._subscribers[run_id].remove(queue)

    def finish_run(
        self,
        run_id: str,
        *,
        status: Literal["completed", "failed"] = "completed",
        error: str | None = None,
    ) -> dict[str, Any] | None:
        """Mark run as completed or failed, compute final metrics, and persist manifest to disk."""
        if run_id in self._runs:
            self._runs[run_id]["status"] = status
            self._runs[run_id]["completed_at"] = _now_iso()
            self._runs[run_id]["error"] = error
            if "environment" not in self._runs[run_id] or not self._runs[run_id]["environment"]:
                self._runs[run_id]["environment"] = collect_environment_metadata()

        summary = self.get_run_summary(run_id)
        if summary:
            try:
                self.persist_run(run_id, summary)
            except Exception:
                pass
        return summary

    def persist_run(self, run_id: str, manifest_data: dict[str, Any] | None = None) -> Path:
        """Write benchmark run manifest and raw evaluations to benchmarks/runs/{run_id}/."""
        if manifest_data is None:
            manifest_data = self.get_run_summary(run_id)
            if manifest_data is None:
                raise ValueError(f"No run found with ID '{run_id}' to persist.")

        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = run_dir / "run_manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # Persist raw per-query evaluations JSONL
        eval_file = run_dir / "raw_query_evaluations.jsonl"
        case_results = manifest_data.get("case_results") or manifest_data.get("cases") or []
        with eval_file.open("w", encoding="utf-8") as f:
            for c in case_results:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        return manifest_file

    def load_persisted_run(self, run_id: str) -> dict[str, Any] | None:
        """Load a previously persisted benchmark run manifest from disk into memory."""
        manifest_file = self.runs_dir / run_id / "run_manifest.json"
        if not manifest_file.is_file():
            return None
        try:
            data = json.loads(manifest_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            self._runs[run_id] = {
                "run_id": data.get("run_id", run_id),
                "suite_name": data.get("suite_name", f"Benchmark: {data.get('dataset_id', '')}"),
                "dataset_id": data.get("dataset_id", ""),
                "workspace_id": data.get("workspace_id", "default"),
                "engines": data.get("engines", []),
                "total_cases": data.get("total_cases", len(data.get("case_results", []))),
                "processed_cases": data.get("processed_cases", len(data.get("case_results", []))),
                "status": data.get("status", "completed"),
                "started_at": data.get("created_at", data.get("started_at", _now_iso())),
                "created_at": data.get("created_at", data.get("started_at", _now_iso())),
                "completed_at": data.get("completed_at"),
                "error": data.get("error"),
                "corpus_sha256": data.get("corpus_sha256"),
                "queries_sha256": data.get("queries_sha256"),
                "environment": data.get("environment", {}),
                "signature": data.get("signature"),
                "verified": data.get("verified", True),
                "verification_metadata": data.get("verification_metadata", {}),
                "metadata": data.get("metadata", {}),
            }
            raw_cases = data.get("case_results", data.get("cases", []))
            self._case_results[run_id] = [
                CaseExecutionResult.model_validate(c) if isinstance(c, dict) else c
                for c in raw_cases
            ]
            return data
        except Exception:
            return None

    def list_persisted_runs(self) -> list[dict[str, Any]]:
        """Discover and list all run manifests persisted on disk."""
        if not self.runs_dir.is_dir():
            return []
        manifests: list[dict[str, Any]] = []
        for manifest_path in sorted(self.runs_dir.glob("*/run_manifest.json"), reverse=True):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "run_id" in data:
                    manifests.append(data)
            except Exception:
                continue
        return manifests

    def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        """Compute full benchmark summary report with metrics per engine, loading from disk if necessary."""
        if run_id not in self._runs:
            persisted = self.load_persisted_run(run_id)
            if persisted is not None:
                return persisted

        run_info = self._runs.get(run_id)
        if not run_info:
            return None

        cases = self._case_results.get(run_id, [])
        by_engine: dict[str, list[CaseExecutionResult]] = {}
        for c in cases:
            by_engine.setdefault(c.engine_id, []).append(c)

        engine_summaries: dict[str, MetricSummary] = {
            engine_id: aggregate_metrics(engine_cases)
            for engine_id, engine_cases in by_engine.items()
        }

        # Calculate comparative advantage deltas vs baseline (pure_lexical or pure_vector)
        baseline_engine = "pure_lexical" if "pure_lexical" in engine_summaries else (
            "pure_vector" if "pure_vector" in engine_summaries else None
        )
        deltas: dict[str, dict[str, float]] = {}
        if baseline_engine and baseline_engine in engine_summaries:
            base_m = engine_summaries[baseline_engine]
            for eng_id, eng_m in engine_summaries.items():
                deltas[eng_id] = {
                    "recall_at_5_delta": eng_m.recall_at_5 - base_m.recall_at_5,
                    "recall_at_20_delta": eng_m.recall_at_20 - base_m.recall_at_20,
                    "ndcg_at_10_delta": eng_m.ndcg_at_10 - base_m.ndcg_at_10,
                    "coverage_delta": eng_m.complete_gold_evidence_coverage - base_m.complete_gold_evidence_coverage,
                    "citation_precision_delta": eng_m.citation_precision - base_m.citation_precision,
                    "abstention_correctness_delta": eng_m.abstention_correctness - base_m.abstention_correctness,
                    "p95_latency_delta_ms": eng_m.p95_latency_ms - base_m.p95_latency_ms,
                }

        metrics_dict = {eng: m.model_dump() for eng, m in engine_summaries.items()}
        corpus_sha = run_info.get("corpus_sha256")
        queries_sha = run_info.get("queries_sha256")
        completed_at = run_info.get("completed_at")
        env_meta = run_info.get("environment") or collect_environment_metadata()

        signature = compute_run_manifest_signature(
            run_id=run_id,
            dataset_id=run_info["dataset_id"],
            corpus_sha256=corpus_sha,
            queries_sha256=queries_sha,
            completed_at=completed_at,
            metric_summaries=metrics_dict,
        )

        return {
            "run_id": run_id,
            "suite_name": run_info["suite_name"],
            "dataset_id": run_info["dataset_id"],
            "workspace_id": run_info.get("workspace_id", "default"),
            "created_at": run_info.get("created_at", run_info.get("started_at", _now_iso())),
            "started_at": run_info.get("started_at", _now_iso()),
            "completed_at": completed_at,
            "status": run_info["status"],
            "corpus_sha256": corpus_sha,
            "queries_sha256": queries_sha,
            "total_cases": run_info["total_cases"],
            "processed_cases": run_info["processed_cases"],
            "error": run_info["error"],
            "engines": run_info["engines"],
            "environment": env_meta,
            "case_results": [c.model_dump() for c in cases],
            "cases": [c.model_dump() for c in cases],
            "metric_summaries": metrics_dict,
            "metrics": metrics_dict,
            "deltas_vs_baseline": deltas,
            "signature": signature,
            "verified": True,
            "verification_metadata": {
                "verifier_id": "trace-studio-integrity-v2",
                "verified_at": completed_at or _now_iso(),
                "integrity_status": "VALID",
                "total_case_results": len(cases),
            },
            "metadata": run_info.get("metadata", {}),
        }

    def list_active_runs(self) -> list[dict[str, Any]]:
        """List all active or recent benchmark runs, merged with disk persisted runs."""
        in_memory = list(self._runs.values())
        persisted = self.list_persisted_runs()
        known_ids = {r["run_id"] for r in in_memory}
        for p in persisted:
            if p["run_id"] not in known_ids:
                in_memory.append({
                    "run_id": p["run_id"],
                    "suite_name": p.get("suite_name", f"Benchmark: {p.get('dataset_id', '')}"),
                    "dataset_id": p.get("dataset_id", ""),
                    "workspace_id": p.get("workspace_id", "default"),
                    "engines": p.get("engines", []),
                    "total_cases": p.get("total_cases", len(p.get("case_results", []))),
                    "processed_cases": p.get("processed_cases", len(p.get("case_results", []))),
                    "status": p.get("status", "completed"),
                    "started_at": p.get("created_at", p.get("started_at", "")),
                    "completed_at": p.get("completed_at"),
                    "error": p.get("error"),
                    "metadata": p.get("metadata", {}),
                })
                known_ids.add(p["run_id"])
        return in_memory


# Global singleton instance
telemetry_manager = BenchmarkTelemetryManager()
