"""Machine-readable evaluation of Trace's production release evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ReleaseGateResult:
    passed: bool
    checks: dict[str, dict[str, Any]]

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_release_evidence(evidence: Mapping[str, Any]) -> ReleaseGateResult:
    """Evaluate supplied, measured release evidence without inventing results.

    ``evidence`` is expected to come from the load harness, restore drill,
    security suite, and shadow rollout recorder.  Missing data fails closed.
    """

    load = dict(evidence.get("load") or {})
    restore = dict(evidence.get("restore") or {})
    security = dict(evidence.get("security") or {})
    shadow = dict(evidence.get("shadow") or {})
    quality = dict(evidence.get("quality") or {})
    replay = dict(evidence.get("replay") or {})
    freshness = dict(evidence.get("freshness") or {})
    operations = dict(evidence.get("operations") or {})
    mix = dict(load.get("mix") or {})
    checks = {
        "load_1m": {
            "passed": int(load.get("atoms", 0)) >= 1_000_000,
            "atoms": int(load.get("atoms", 0)), "non_deep_qps": float(load.get("non_deep_qps", 0)),
        },
        "load_mix": {
            "passed": all(abs(float(mix.get(key, 0)) - value) <= 0.01 for key, value in {"fast": .70, "standard": .20, "graph": .05, "hierarchy": .05}.items()),
            "mix": mix,
        },
        "latency": {
            "passed": float(load.get("fast_p95_seconds", float("inf"))) <= 2 and float(load.get("standard_p95_seconds", float("inf"))) <= 5 and float(load.get("graph_p95_seconds", float("inf"))) <= 5 and float(load.get("hierarchy_p95_seconds", float("inf"))) <= 5 and float(load.get("deep_p95_seconds", float("inf"))) <= 90,
        },
        "restore": {
            "passed": bool(restore.get("passed")) and float(restore.get("rpo_hours", float("inf"))) <= 24 and float(restore.get("rto_hours", float("inf"))) <= 24,
            "rpo_hours": restore.get("rpo_hours"), "rto_hours": restore.get("rto_hours"),
        },
        "security": {
            "passed": (
                bool(security.get("tenant_leak_test_passed"))
                and bool(security.get("rls_visibility_test_passed"))
                and bool(security.get("provider_redaction_test_passed"))
                and security.get("critical_privacy_defect") is False
                and security.get("critical_destructive_data_defect") is False
            ),
        },
        "replay": {
            "passed": bool(replay.get("passed")) and replay.get("critical_replay_defect") is False,
        },
        "quality": {
            "passed": (
                int(quality.get("reviewed_query_count", 0)) >= 300
                and float(quality.get("complete_gold_evidence_coverage", float("-inf"))) >= .80
                and float(quality.get("citation_precision", float("-inf"))) >= .90
                and abs(float(quality.get("quality_delta_from_100k", float("inf")))) <= .02
            ),
        },
        "freshness": {
            "passed": bool(freshness.get("zero_hot_data_blind_spots")),
        },
        "operational_bounds": {
            "passed": (
                float(operations.get("max_queue_age_seconds", float("inf"))) <= float(operations.get("queue_age_budget_seconds", 300))
                and float(operations.get("max_index_lag_seconds", float("inf"))) <= float(operations.get("index_lag_budget_seconds", 300))
                and int(operations.get("max_graph_degree", 2**31 - 1)) <= int(operations.get("graph_degree_cap", 128))
                and float(operations.get("model_cost_usd", float("inf"))) <= float(operations.get("model_cost_budget_usd", 0))
                and int(operations.get("stale_projection_count", 2**31 - 1)) <= int(operations.get("stale_projection_budget", 0))
            ),
        },
        "shadow_rollout": {
            "passed": bool(shadow.get("passed")) and list(shadow.get("stages") or []) == [5, 25, 50, 100] and not bool(shadow.get("automatic_rollback_triggered")),
        },
    }
    return ReleaseGateResult(passed=all(check["passed"] for check in checks.values()), checks=checks)
