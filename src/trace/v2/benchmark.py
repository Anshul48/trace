"""Frozen evidence-retrieval benchmark runner and ablation metrics."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from statistics import quantiles
from typing import Any, Sequence

from .models import QueryRequest, RetrievalBudget


class BenchmarkFormatError(ValueError):
    pass


class ReleaseCorpusError(BenchmarkFormatError):
    """A corpus is useful for development but cannot authorize a release."""


_RELEASE_KIND_GROUPS = {
    "direct_lookup": {"direct_lookup", "direct"},
    "multi_hop": {"multi_hop", "multi_hop_architecture", "multi_hop_dependency"},
    "dependency": {"dependency", "dependency_chain"},
    "contradiction": {"contradiction", "contradiction_update"},
    "order": {"order", "source_order", "temporal_order"},
    "out_of_scope": {"out_of_scope"},
}


def load_benchmark(path: str | Path) -> dict[str, Any]:
    benchmark_path = Path(path)
    try:
        value = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkFormatError(f"cannot read frozen benchmark {benchmark_path}: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list) or not value.get("name"):
        raise BenchmarkFormatError("benchmark requires a name and a cases list")
    for case in value["cases"]:
        if not case.get("id") or not case.get("query"):
            raise BenchmarkFormatError("each benchmark case requires id and query")
        if "gold_atom_version_ids" not in case:
            raise BenchmarkFormatError(f"case {case['id']!r} lacks frozen gold_atom_version_ids")
        if not isinstance(case["gold_atom_version_ids"], list):
            raise BenchmarkFormatError(f"case {case['id']!r} has invalid gold_atom_version_ids")
    return value


def validate_release_corpus(benchmark: dict[str, Any]) -> dict[str, Any]:
    """Prove that a frozen corpus is large and reviewed enough for release.

    This deliberately rejects small developer fixtures.  It is safer to block
    a release than to label six illustrative cases as a 300-case reviewed
    corpus.  BRIGHT-derived cases remain separately reported and require their
    own licence metadata rather than being silently mixed into the in-domain
    quality result.
    """

    failures: list[str] = []
    if benchmark.get("release_authority") is not True:
        failures.append("release_authority must be true")
    if benchmark.get("review_status") != "reviewed":
        failures.append("review_status must be reviewed")
    if not benchmark.get("corpus_snapshot"):
        failures.append("corpus_snapshot is required")
    cases = list(benchmark.get("cases") or [])
    if len(cases) < 300:
        failures.append("at least 300 in-domain reviewed cases are required")
    observed = {str(case.get("kind", "")) for case in cases}
    missing = sorted(group for group, aliases in _RELEASE_KIND_GROUPS.items() if not observed.intersection(aliases))
    if missing:
        failures.append("missing required case kinds: " + ", ".join(missing))
    unreviewed = [str(case.get("id", "unknown")) for case in cases if case.get("review_status") not in {None, "reviewed"}]
    if unreviewed:
        failures.append("contains non-reviewed cases")
    if failures:
        raise ReleaseCorpusError("release corpus rejected: " + "; ".join(failures))
    return {
        "approved": True,
        "case_count": len(cases),
        "kind_coverage": sorted(_RELEASE_KIND_GROUPS),
        "corpus_snapshot": benchmark["corpus_snapshot"],
    }


def _ndcg(relevant: set[str], returned: Sequence[str], cutoff: int) -> float:
    if not relevant:
        return 0.0
    score = sum((1.0 / math.log2(rank + 1)) for rank, atom_id in enumerate(returned[:cutoff], start=1) if atom_id in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), cutoff) + 1))
    return score / ideal if ideal else 0.0


def _percentile95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[94]


class BenchmarkRunner:
    """Runs fixed questions through explicitly selected retrieval ablations."""

    def __init__(self, service: Any) -> None:
        self.service = service

    def run(self, *, workspace_id: str, benchmark: dict[str, Any], stages: Sequence[str]) -> dict[str, Any]:
        report: dict[str, Any] = {
            "benchmark_name": benchmark["name"],
            "benchmark_suite": benchmark.get("suite", "in_domain"),
            "case_count": len(benchmark["cases"]),
            "stages": {},
        }
        for stage in stages:
            case_reports: list[dict[str, Any]] = []
            latencies: list[float] = []
            for case in benchmark["cases"]:
                started = time.perf_counter()
                response = self.service.query(QueryRequest(
                    workspace_id=workspace_id,
                    query=case["query"],
                    retrieval_profile=stage,
                    retrieval_budget=RetrievalBudget(
                        mode="deep" if stage == "deep" else ("graph" if stage == "graph" else ("hierarchy" if stage == "hierarchy" else "standard")),
                        allow_deep_escalation=False,
                    ),
                ))
                elapsed_ms = (time.perf_counter() - started) * 1_000
                latencies.append(elapsed_ms)
                gold = set(case["gold_atom_version_ids"])
                returned: list[str] = []
                cited: list[str] = []
                for result in response["results"]:
                    if result.get("candidate_kind") == "atom":
                        returned.append(result["atom_version_id"])
                        cited.append(result["atom_version_id"])
                    cited.extend(result.get("source_atom_version_ids", []))
                cited = list(dict.fromkeys(cited))
                out_of_scope = bool(case.get("out_of_scope", False))
                abstained = response["sufficiency_state"] == "insufficient_evidence"
                diagnostics = response.get("retrieval_diagnostics", {})
                deep_trace = diagnostics.get("deep_trace") or {}
                cloud_cost = float(deep_trace.get("cloud_token_cost_usd", 0.0))
                case_reports.append({
                    "id": case["id"],
                    "kind": case.get("kind", "unspecified"),
                    "gold_atom_version_ids": sorted(gold),
                    "returned_atom_version_ids": returned,
                    "recall_at_5": len(gold & set(returned[:5])) / max(1, len(gold)),
                    "recall_at_20": len(gold & set(returned[:20])) / max(1, len(gold)),
                    "ndcg_at_10": _ndcg(gold, returned, 10),
                    "complete_gold_evidence": gold <= set(cited),
                    "citation_precision": len(gold & set(cited)) / max(1, len(cited)) if gold else float(abstained),
                    "abstention_correct": abstained if out_of_scope else not abstained,
                    "latency_ms": elapsed_ms,
                    "local_compute_ms": elapsed_ms,
                    "cloud_token_cost": cloud_cost,
                    "diagnostics": diagnostics,
                })
            report["stages"][stage] = {
                "cases": case_reports,
                "metrics": {
                    "recall_at_5": sum(item["recall_at_5"] for item in case_reports) / max(1, len(case_reports)),
                    "recall_at_20": sum(item["recall_at_20"] for item in case_reports) / max(1, len(case_reports)),
                    "ndcg_at_10": sum(item["ndcg_at_10"] for item in case_reports) / max(1, len(case_reports)),
                    "complete_gold_evidence_coverage": sum(bool(item["complete_gold_evidence"]) for item in case_reports) / max(1, len(case_reports)),
                    "citation_precision": sum(item["citation_precision"] for item in case_reports) / max(1, len(case_reports)),
                    "abstention_correctness": sum(bool(item["abstention_correct"]) for item in case_reports) / max(1, len(case_reports)),
                    "p95_latency_ms": _percentile95(latencies),
                    "local_compute_ms": sum(latencies),
                    "cloud_token_cost": sum(item["cloud_token_cost"] for item in case_reports),
                },
            }
        baseline = report["stages"].get("lexical", {}).get("metrics")
        budgets_ms = {"lexical": 2_000, "hybrid": 5_000, "rerank": 5_000, "hierarchy": 5_000, "graph": 5_000, "deep": 90_000}
        decisions: dict[str, dict[str, Any]] = {}
        for stage, stage_report in report["stages"].items():
            metrics = stage_report["metrics"]
            if not baseline or stage == "lexical":
                decisions[stage] = {"retain": True, "reason": "baseline"}
                continue
            coverage_delta = metrics["complete_gold_evidence_coverage"] - baseline["complete_gold_evidence_coverage"]
            precision_delta = metrics["citation_precision"] - baseline["citation_precision"]
            improves_coverage = coverage_delta >= 0.02
            preserves_precision = precision_delta >= -0.005
            within_budget = metrics["p95_latency_ms"] <= budgets_ms[stage]
            decisions[stage] = {
                "retain": improves_coverage and preserves_precision and within_budget,
                "improves_coverage": improves_coverage,
                "complete_gold_coverage_delta": coverage_delta,
                "preserves_citation_precision": preserves_precision,
                "citation_precision_delta": precision_delta,
                "within_latency_budget": within_budget,
            }
        report["retention_decisions"] = decisions
        suites: dict[str, dict[str, Any]] = {}
        for case in benchmark["cases"]:
            suite = str(case.get("suite", benchmark.get("suite", "in_domain")))
            suites.setdefault(suite, {"case_count": 0})["case_count"] += 1
        if len(suites) > 1:
            report["suites"] = suites
        return report
