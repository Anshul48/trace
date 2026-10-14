"""Trace V2 Studio: One-Click Benchmark Suite and Live Demo Comparator.

Exports key classes, comparison engines, telemetry streaming managers, and FastAPI router.
"""

from __future__ import annotations

from .comparisons import (
    BaseComparativeEngine,
    CustomDbEngine,
    EngineHit,
    EngineQueryResult,
    NaiveRagEngine,
    PureLexicalEngine,
    PureVectorEngine,
    TraceHybridEngine,
    get_engine,
    list_available_engines,
)
from .engine import (
    BenchmarkCoordinator,
    BenchmarkSuiteInfo,
    DatasetCatalog,
    DatasetInfo,
)
from .routes import sanitize_dataset_info, sanitize_path, studio_router
from .telemetry import (
    BenchmarkEvent,
    BenchmarkTelemetryManager,
    CaseExecutionResult,
    MetricSummary,
    calculate_abstention_correctness,
    calculate_citation_precision,
    calculate_evidence_coverage,
    calculate_latency_percentiles,
    calculate_ndcg_at_k,
    calculate_recall_at_k,
    telemetry_manager,
)

__all__ = [
    "studio_router",
    "sanitize_path",
    "sanitize_dataset_info",
    "DatasetCatalog",
    "DatasetInfo",
    "BenchmarkSuiteInfo",
    "BenchmarkCoordinator",
    "BaseComparativeEngine",
    "TraceHybridEngine",
    "PureLexicalEngine",
    "PureVectorEngine",
    "NaiveRagEngine",
    "CustomDbEngine",
    "EngineHit",
    "EngineQueryResult",
    "get_engine",
    "list_available_engines",
    "BenchmarkTelemetryManager",
    "BenchmarkEvent",
    "CaseExecutionResult",
    "MetricSummary",
    "telemetry_manager",
    "calculate_recall_at_k",
    "calculate_ndcg_at_k",
    "calculate_citation_precision",
    "calculate_evidence_coverage",
    "calculate_abstention_correctness",
    "calculate_latency_percentiles",
]
