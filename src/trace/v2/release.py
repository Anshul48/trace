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
    mix = dict(load.get("mix") or {})
    checks = {
        "load_10m_500qps": {
            "passed": int(load.get("atoms", 0)) >= 10_000_000 and float(load.get("non_deep_qps", 0)) >= 500,
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
            "passed": bool(security.get("tenant_leak_test_passed")) and bool(security.get("rls_visibility_test_passed")) and bool(security.get("provider_redaction_test_passed")),
        },
        "quality": {
            "passed": float(quality.get("complete_gold_evidence_delta", float("-inf"))) >= .02 and float(quality.get("citation_precision_delta", float("-inf"))) >= -.005,
        },
        "shadow_rollout": {
            "passed": bool(shadow.get("passed")) and list(shadow.get("stages") or []) == [5, 25, 50, 100] and not bool(shadow.get("automatic_rollback_triggered")),
        },
    }
    return ReleaseGateResult(passed=all(check["passed"] for check in checks.values()), checks=checks)
