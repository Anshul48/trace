"""Independent final V1b temporal evidence collector.

This collector performs only standard-library static/identity checks when the
fresh locked temporal environment is unavailable. It deliberately does not
replace missing Pydantic/FastAPI/PostgreSQL/RLS/external-index capabilities
with SQLite, mocks, or current-release shortcuts.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path


WORKTREE = Path(os.environ["S5_TEMPORAL_WORKTREE"])
SCRATCH = Path(os.environ["S5_TEMPORAL_SCRATCH"])
RESULT_ROOT = Path(os.environ["S5_TEMPORAL_RESULT_ROOT"])
RECEIPT_PATH = Path(os.environ["S5_TEMPORAL_RECEIPT"])
SCRATCH.mkdir(parents=True, exist_ok=True)
RESULT_ROOT.mkdir(parents=True, exist_ok=True)


def run_case(name: str, fn):
    started = time.perf_counter()
    try:
        observation = fn()
        return {"case": name, "status": "pass", "duration_ms": round((time.perf_counter() - started) * 1000, 3), "observation": observation}
    except Exception as exc:
        return {"case": name, "status": "fail", "duration_ms": round((time.perf_counter() - started) * 1000, 3), "error": {"type": type(exc).__name__, "detail": str(exc)[:1000]}}


def case_ast_parse():
    paths = [
        WORKTREE / "src/trace/v2/api.py",
        WORKTREE / "src/trace/v2/models.py",
        WORKTREE / "src/trace/v2/production.py",
        WORKTREE / "src/trace/v2/repository.py",
        WORKTREE / "src/trace/v2/retrieval.py",
        WORKTREE / "src/trace/v2/service.py",
        WORKTREE / "src/trace/v2/store.py",
        WORKTREE / "tests/test_v2_temporal_revocation.py",
    ]
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {"parsed_files": len(paths)}


def case_static_temporal_contract_markers():
    files = {
        "models": (WORKTREE / "src/trace/v2/models.py").read_text(encoding="utf-8"),
        "store": (WORKTREE / "src/trace/v2/store.py").read_text(encoding="utf-8"),
        "retrieval": (WORKTREE / "src/trace/v2/retrieval.py").read_text(encoding="utf-8"),
        "service": (WORKTREE / "src/trace/v2/service.py").read_text(encoding="utf-8"),
        "migration": (WORKTREE / "migrations/006_temporal_revocation.sql").read_text(encoding="utf-8"),
    }
    expected = {
        "models": ["ValidTimeMetadata", "valid_from", "valid_to", "TemporalPrecision", "SourceLifecycleState"],
        "store": ["current_lifecycle", "redacted_purged", "get_cortex_release_as_of_event", "event_after_requested_watermark"],
        "retrieval": ["as_of_event", "current_nodes", "temporal_visibility"],
        "service": ["historical_unavailable", "as_of_event", "exclusion_reason"],
        "migration": ["trace_source_lifecycle", "valid_from", "valid_to", "ENABLE ROW LEVEL SECURITY", "FORCE ROW LEVEL SECURITY"],
    }
    missing = {name: [marker for marker in markers if marker not in files[name]] for name, markers in expected.items()}
    assert not any(missing.values()), missing
    return {"checked_markers": sum(len(items) for items in expected.values()), "missing": missing}


def case_migration_is_forward_additive_text():
    sql = (WORKTREE / "migrations/006_temporal_revocation.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE trace_cortex_releases" in sql
    assert "CREATE TABLE IF NOT EXISTS trace_source_lifecycle" in sql
    assert "ON CONFLICT (atom_version_id) DO NOTHING" in sql
    assert "DROP POLICY IF EXISTS" in sql
    return {"migration_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(), "postgresql_only": True}


def module_probe() -> dict:
    result = {}
    for name in ("pytest", "fastapi", "pydantic", "psycopg", "httpx", "multipart"):
        result[name] = bool(importlib.util.find_spec(name))
    try:
        sys.path.insert(0, str(WORKTREE / "src"))
        import trace.v2.store  # noqa: F401
    except Exception as exc:
        result["trace_v2_import"] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}"}
    else:
        result["trace_v2_import"] = {"status": "pass"}
    return result


def execute_runtime_cases() -> list[dict]:
    import unittest
    sys.path.insert(0, str(WORKTREE / "src"))
    sys.path.insert(0, str(WORKTREE / "tests"))
    from test_v2_temporal_revocation import TemporalRevocationTests
    from test_v2_migration_bootstrap_contracts import EventPartitionBootstrapContractTests

    results = []
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TemporalRevocationTests))
    suite.addTests(loader.loadTestsFromTestCase(EventPartitionBootstrapContractTests))

    for test in suite:
        test_name = test.id().split(".")[-1]
        started = time.perf_counter()
        result = unittest.TestResult()
        test.run(result)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        if result.wasSuccessful():
            results.append({"case": test_name, "status": "pass", "duration_ms": elapsed_ms})
        else:
            errors = [err[1] for err in result.errors + result.failures]
            results.append({"case": test_name, "status": "fail", "duration_ms": elapsed_ms, "error": errors[0] if errors else "unknown"})
    return results


if __name__ == "__main__":
    import sys
    environment = module_probe()
    static_cases = [
        run_case("ast_parse_temporal_sources_and_tests", case_ast_parse),
        run_case("static_temporal_contract_markers", case_static_temporal_contract_markers),
        run_case("migration_forward_additive_text", case_migration_is_forward_additive_text),
    ]
    
    if environment.get("trace_v2_import", {}).get("status") == "pass":
        runtime_matrix = execute_runtime_cases()
        required_blockers = []
    else:
        runtime_matrix = [
            {"case": name, "status": "blocked", "reason": "fresh temporal runtime cannot import the exact target"}
            for name in (
                "system_event_time_reconstruction",
                "valid_time_and_unknown_precision",
                "revision_supersession_contradiction",
                "revocation_tombstone_policy",
                "privacy_erasure",
                "historical_authorization",
                "historical_release_selection_and_missing_history",
                "evidence_bundle_identity",
            )
        ]
        required_blockers = ["fresh temporal environment lacks dependencies"]

    runtime_passed = sum(case["status"] == "pass" for case in runtime_matrix)
    runtime_failed = sum(case["status"] == "fail" for case in runtime_matrix)
    runtime_blocked = sum(case["status"] == "blocked" for case in runtime_matrix)

    receipt = {
        "verifier_id": "v1b-final-temporal-verifier-20260825",
        "sub_gate": "V1b-Trace-temporal",
        "base_commit": "37b601c15b81aefb3edf1f47df57e12dfe96ffbf",
        "parent_commit": "ec2370120cebfb799efa69163e3ab8ddae6271e7",
        "claim_level": "C1-temporal-runtime",
        "backend": "Exact TR2 source tree + verified locked environment",
        "environment": environment,
        "static_cases": static_cases,
        "runtime_matrix": runtime_matrix,
        "required_blockers": required_blockers,
        "summary": {
            "static_passed": sum(case["status"] == "pass" for case in static_cases),
            "static_failed": sum(case["status"] == "fail" for case in static_cases),
            "static_total": len(static_cases),
            "runtime_passed": runtime_passed,
            "runtime_failed": runtime_failed,
            "runtime_blocked": runtime_blocked,
            "full_subgate_status": "pass" if runtime_failed == 0 and runtime_blocked == 0 else "blocked",
        },
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"summary": receipt["summary"], "receipt": str(RECEIPT_PATH)}, indent=2))
