"""Measured Phase 1 pilot evidence evaluation.

The evaluator deliberately consumes recorded measurements. It does not invent
latency, quality, token, or hardware claims from the contents of a source
corpus.

It is published through the collision-free trace_local SDK namespace.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math
from pathlib import Path
import json
from typing import Any


QUERY_CLASSES = frozenset(
    {
        "direct_lookup",
        "dependency",
        "contradiction",
        "chronology",
        "navigation",
        "out_of_scope",
    }
)


class PilotEvidenceError(ValueError):
    """A pilot report is missing a required measured evidence field."""


def _number(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise PilotEvidenceError(f"{field} must be numeric") from error
    if not math.isfinite(result):
        raise PilotEvidenceError(f"{field} must be finite")
    return result


def _ids(value: Any, *, field: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise PilotEvidenceError(f"{field} must be a list of non-empty IDs")
    return set(value)


def _has_hardware_profile(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return bool(value.get("name") or value.get("cpu") or value.get("platform")) and bool(
        value.get("memory_bytes") or value.get("ram_gb") or value.get("storage")
    )


def evaluate_pilot(report: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate Phase 1 gates from a frozen judged-query report.

    Required report fields:

    - hardware_profile: declared test hardware;
    - source_atoms, average_tokens_per_atom, immutable_version_growth;
    - judged_queries: at least 100 entries covering all six query classes;
    - navigation_summary_reviews;
    - latency_by_class: p95 by class on that hardware;
    - critical_defects: measured issue records.
    """

    if not isinstance(report, Mapping):
        raise PilotEvidenceError("pilot report must be an object")
    errors: list[str] = []
    checks: dict[str, bool] = {}
    hardware = report.get("hardware_profile")
    checks["hardware_profile_declared"] = _has_hardware_profile(hardware)
    if not checks["hardware_profile_declared"]:
        errors.append("hardware_profile must declare a machine and memory or storage")
    source_atoms = _number(report.get("source_atoms"), field="source_atoms")
    average_tokens = _number(report.get("average_tokens_per_atom"), field="average_tokens_per_atom")
    immutable_growth = report.get("immutable_version_growth")
    checks["source_measurements_declared"] = source_atoms >= 0 and average_tokens > 0 and isinstance(immutable_growth, Mapping)
    if not checks["source_measurements_declared"]:
        errors.append("source atom, token, and immutable-version growth measurements are required")

    judgments = report.get("judged_queries")
    if not isinstance(judgments, list):
        raise PilotEvidenceError("judged_queries must be a list")
    classes: set[str] = set()
    complete_count = 0
    cited = 0
    precise_citations = 0
    malformed_judgments = 0
    for index, judgment in enumerate(judgments):
        if not isinstance(judgment, Mapping):
            malformed_judgments += 1
            continue
        query_class = judgment.get("query_class")
        if not isinstance(query_class, str):
            malformed_judgments += 1
            continue
        classes.add(query_class)
        try:
            gold = _ids(judgment.get("gold_evidence_atom_ids"), field=f"judged_queries[{index}].gold_evidence_atom_ids")
            retrieved = _ids(judgment.get("retrieved_atom_ids"), field=f"judged_queries[{index}].retrieved_atom_ids")
            selected = _ids(
                judgment.get("selected_citation_atom_ids", judgment.get("retrieved_atom_ids")),
                field=f"judged_queries[{index}].selected_citation_atom_ids",
            )
        except PilotEvidenceError:
            malformed_judgments += 1
            continue
        if gold.issubset(retrieved):
            complete_count += 1
        cited += len(selected)
        precise_citations += len(selected & gold)
    total_judgments = len(judgments)
    coverage = complete_count / total_judgments if total_judgments else 0.0
    citation_precision = precise_citations / cited if cited else 0.0
    checks["frozen_query_count"] = total_judgments >= 100 and malformed_judgments == 0
    checks["query_class_coverage"] = QUERY_CLASSES.issubset(classes)
    checks["complete_gold_evidence_coverage"] = coverage >= 0.80
    checks["citation_precision"] = citation_precision >= 0.90
    if not checks["frozen_query_count"]:
        errors.append("at least 100 valid frozen judged queries are required")
    if not checks["query_class_coverage"]:
        errors.append("frozen judged queries must cover every required query class")
    if not checks["complete_gold_evidence_coverage"]:
        errors.append("complete-gold-evidence coverage is below 80 percent")
    if not checks["citation_precision"]:
        errors.append("citation precision is below 90 percent")

    reviews = report.get("navigation_summary_reviews")
    if not isinstance(reviews, list) or not reviews:
        review_approval = 0.0
        valid_reviews = False
    else:
        valid_reviews = all(isinstance(review, Mapping) and isinstance(review.get("decision"), str) for review in reviews)
        approved = sum(1 for review in reviews if isinstance(review, Mapping) and review.get("decision") == "approved")
        review_approval = approved / len(reviews)
    checks["navigation_review_evidence"] = valid_reviews
    checks["navigation_reviewer_approval"] = review_approval >= 0.70
    if not checks["navigation_review_evidence"]:
        errors.append("navigation summary reviewer decisions are required")
    if not checks["navigation_reviewer_approval"]:
        errors.append("navigation summary reviewer approval is below 70 percent")

    latency = report.get("latency_by_class")
    if not isinstance(latency, Mapping):
        checks["latency_reported"] = False
        errors.append("p95 latency must be reported by query class")
    else:
        reported_classes = set()
        valid_latency = True
        for query_class, measurement in latency.items():
            if not isinstance(measurement, Mapping):
                valid_latency = False
                continue
            value = measurement.get("p95_ms", measurement.get("p95_seconds"))
            try:
                measured = _number(value, field=f"latency_by_class.{query_class}")
            except PilotEvidenceError:
                valid_latency = False
                continue
            if measured < 0:
                valid_latency = False
            else:
                reported_classes.add(str(query_class))
        checks["latency_reported"] = valid_latency and QUERY_CLASSES.issubset(reported_classes)
        if not checks["latency_reported"]:
            errors.append("p95 latency must be a non-negative measurement for every query class")

    defects = report.get("critical_defects")
    if not isinstance(defects, list):
        raise PilotEvidenceError("critical_defects must be a list")
    critical = [
        defect
        for defect in defects
        if isinstance(defect, Mapping) and str(defect.get("severity", "")).lower() == "critical"
    ]
    checks["zero_critical_defects"] = not critical
    if critical:
        errors.append("critical provenance, privacy, or destructive-data defects remain")

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "judged_queries": total_judgments,
            "malformed_judgments": malformed_judgments,
            "query_classes": sorted(classes),
            "complete_gold_evidence_coverage": coverage,
            "citation_precision": citation_precision,
            "navigation_reviewer_approval": review_approval,
            "source_atoms": int(source_atoms),
            "average_tokens_per_atom": average_tokens,
            "critical_defect_count": len(critical),
        },
        "errors": errors,
    }


def run_public_fixture(
    trace: Any,
    *,
    corpus_path: str | Path,
    judgments_path: str | Path,
    limit: int = 10,
    actor: str = "fixture-runner",
) -> dict[str, Any]:
    """Ingest and execute a public JSONL fixture against a local Trace store.

    The function returns measured query evidence. It intentionally does not
    fabricate a hardware profile or mark a release as passed; callers add
    those operator-measured fields before passing the report to evaluate_pilot.
    """

    corpus = Path(corpus_path)
    judgments_file = Path(judgments_path)
    try:
        records = [
            json.loads(line)
            for line in corpus.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        judgment_envelope = json.loads(judgments_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise PilotEvidenceError(f"cannot read public fixture: {error}") from error
    if any(not isinstance(record, Mapping) for record in records):
        raise PilotEvidenceError("public corpus must contain JSON objects")
    judgments = judgment_envelope.get("judged_queries") if isinstance(judgment_envelope, Mapping) else None
    if not isinstance(judgments, list):
        raise PilotEvidenceError("public judgments must contain judged_queries")
    stored = trace.ingest_many(records, actor=actor)
    record_atoms = {
        str(record["record_id"]): result["atom_id"]
        for record, result in zip(records, stored, strict=True)
        if isinstance(record.get("record_id"), str)
    }
    measured: list[dict[str, Any]] = []
    latencies: dict[str, list[float]] = defaultdict(list)
    for judgment in judgments:
        if not isinstance(judgment, Mapping):
            raise PilotEvidenceError("public judgments must be JSON objects")
        query = judgment.get("query")
        query_class = judgment.get("query_class")
        gold_record_ids = judgment.get("gold_record_ids")
        if not isinstance(query, str) or not isinstance(query_class, str) or not isinstance(gold_record_ids, list):
            raise PilotEvidenceError("public judgment lacks query, query_class, or gold_record_ids")
        try:
            gold = [record_atoms[str(record_id)] for record_id in gold_record_ids]
        except KeyError as error:
            raise PilotEvidenceError(f"public judgment references unknown record ID: {error.args[0]}") from error
        result = trace.query(query, limit=limit)
        retrieved = [item["atom_id"] for item in result["results"]]
        latencies[query_class].append(float(result["elapsed_ms"]))
        measured.append(
            {
                "id": judgment.get("id"),
                "query": query,
                "query_class": query_class,
                "gold_evidence_atom_ids": gold,
                "retrieved_atom_ids": retrieved,
                "selected_citation_atom_ids": retrieved,
                "sufficiency_state": result["sufficiency_state"],
                "elapsed_ms": result["elapsed_ms"],
            }
        )
    return {
        "fixture_schema_version": judgment_envelope.get("schema_version"),
        "source_atoms": len(stored),
        "judged_queries": measured,
        "latency_by_class": {
            query_class: {"p95_ms": _p95(values), "samples": len(values)}
            for query_class, values in sorted(latencies.items())
        },
        "integrity": trace.verify_integrity(),
    }


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, max(0, round((len(ordered) - 1) * 0.95)))])


__all__ = [
    "PilotEvidenceError",
    "QUERY_CLASSES",
    "evaluate_pilot",
    "run_public_fixture",
]
