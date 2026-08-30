"""Automated Negative Integrity Verification Tests for Scale Recovery Quarantine.

Wave R0: R0-02 (Narrow Quarantine for Unsound Scripts) & R0-06 (Negative Integrity Test Fixtures).
References:
- docs/program/SCALE_CERTIFICATION_RECOVERY_PLAN.md
- docs/program/00_GLOBAL_CONTEXT_RECOVERY.md
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"

QUARANTINED_SCRIPTS = [
    SCRIPTS_DIR / "run_1m_scale_gate.py",
    SCRIPTS_DIR / "benchmark_1m_hybrid_comprehensive.py",
]


def test_quarantined_scripts_exist() -> None:
    """Verify all quarantined script files exist in the repository."""
    for script_path in QUARANTINED_SCRIPTS:
        assert script_path.exists(), f"Expected quarantined script {script_path} to exist"


@pytest.mark.parametrize(
    "script_name",
    [
        "run_1m_scale_gate.py",
        "benchmark_1m_hybrid_comprehensive.py",
    ],
)
def test_script_fails_without_diagnostic_flag(script_name: str) -> None:
    """Every quarantined script must exit with code 1 when invoked without --diagnostic."""
    script_path = SCRIPTS_DIR / script_name
    env = dict(os.environ)
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = str(ROOT_DIR / "src")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )


    assert result.returncode == 1, f"{script_name} must exit with code 1 without --diagnostic"
    combined_output = result.stdout + result.stderr
    assert "QUARANTINED" in combined_output, f"{script_name} must display quarantine banner/notice"
    assert "--diagnostic" in combined_output, f"{script_name} must mention required --diagnostic flag"


def test_benchmark_1m_hybrid_fails_closed_when_master_db_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """benchmark_1m_hybrid_comprehensive.py must NOT fall back to :memory:; must fail closed."""
    import importlib.util

    script_path = SCRIPTS_DIR / "benchmark_1m_hybrid_comprehensive.py"
    spec = importlib.util.spec_from_file_location("benchmark_1m_hybrid", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Point MASTER_DB to a non-existent path
    non_existent_db = tmp_path / "non_existent_spine.db"
    monkeypatch.setattr(mod, "MASTER_DB", non_existent_db)

    with pytest.raises(FileNotFoundError) as excinfo:
        mod.run_comprehensive_1m_hybrid_benchmark()

    assert "FAIL-CLOSED" in str(excinfo.value)
    assert "In-memory fallback is strictly prohibited" in str(excinfo.value)


def test_run_1m_scale_gate_fails_closed_when_sources_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_1m_scale_gate.py must fail closed if source corpus files and database are missing."""
    import importlib.util

    script_path = SCRIPTS_DIR / "run_1m_scale_gate.py"
    spec = importlib.util.spec_from_file_location("run_1m_scale_gate", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Point scale data dir to empty tmp dir
    empty_dir = tmp_path / "empty_scale_dir"
    empty_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "SCALE_DATA_DIR", empty_dir)
    monkeypatch.setattr(mod, "CAPSULE_DIR", empty_dir)

    runner = mod.OneMillionScaleRunner(target_docs=100, output_dir=tmp_path / "diag_out")

    # validate_preflight must fail closed
    with pytest.raises(RuntimeError) as excinfo:
        runner.validate_preflight()
    assert "FAIL-CLOSED" in str(excinfo.value)

    # stream_corpus_records must fail closed (no synthetic fallback)
    with pytest.raises(RuntimeError) as excinfo_stream:
        list(runner.stream_corpus_records())
    assert "FAIL-CLOSED" in str(excinfo_stream.value)
    assert "Synthetic generation fallback is strictly prohibited" in str(excinfo_stream.value)


def test_quarantined_scripts_contain_quarantine_banners() -> None:
    """Verify that all quarantined scripts have quarantine docstrings and banner constants."""
    for script_path in QUARANTINED_SCRIPTS:
        content = script_path.read_text(encoding="utf-8")
        assert "QUARANTINED - NON-CERTIFYING DIAGNOSTIC SCRIPT ONLY" in content, (
            f"Expected quarantine banner in {script_path.name}"
        )
        assert "QUARANTINE_BANNER" in content, (
            f"Expected QUARANTINE_BANNER definition in {script_path.name}"
        )


def test_no_script_contains_pass_and_certified() -> None:
    """Verify that no quarantined script emits or contains PASS_AND_CERTIFIED."""
    for script_path in QUARANTINED_SCRIPTS:
        content = script_path.read_text(encoding="utf-8")
        assert "PASS_AND_CERTIFIED" not in content, (
            f"Found forbidden PASS_AND_CERTIFIED in {script_path.name}"
        )
        # Ensure status assignments are DIAGNOSTIC_NON_CERTIFYING and not PASS
        assert '"status": "PASS"' not in content, (
            f'Found forbidden \'"status": "PASS"\' in {script_path.name}'
        )
        assert '"overall_verdict": "PASS"' not in content, (
            f'Found forbidden \'"overall_verdict": "PASS"\' in {script_path.name}'
        )


def test_quarantined_scripts_do_not_target_canonical_result_paths(tmp_path: Path) -> None:
    """Verify that runners redirect/isolate outputs to diagnostic directories."""
    import importlib.util

    # 1. Check 1M Runner output isolation
    spec_1m = importlib.util.spec_from_file_location("run_1m_scale_gate", SCRIPTS_DIR / "run_1m_scale_gate.py")
    assert spec_1m is not None and spec_1m.loader is not None
    mod_1m = importlib.util.module_from_spec(spec_1m)
    spec_1m.loader.exec_module(mod_1m)

    runner_1m = mod_1m.OneMillionScaleRunner(target_docs=100, output_dir=None)
    assert "diagnostic" in str(runner_1m.output_dir)
    assert str(runner_1m.output_dir) != str(ROOT_DIR / "benchmarks" / "runs" / "1m_scale")

    # 2. Check 100K Runner diagnostic output isolation
    spec_100k = importlib.util.spec_from_file_location("run_100k_scale_gate", SCRIPTS_DIR / "run_100k_scale_gate.py")
    assert spec_100k is not None and spec_100k.loader is not None
    mod_100k = importlib.util.module_from_spec(spec_100k)
    spec_100k.loader.exec_module(mod_100k)

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"manifest_title": "Test Manifest", "total_unique_documents": 10}), encoding="utf-8")

    runner_100k = mod_100k.Scale100KRunner(
        manifest_path=manifest_file,
        data_root=tmp_path / "data",
        mode="diagnostic",
        output_dir=None,
        target_count=10,
        force_overwrite=True,
        allow_unlocked_policy=True,
    )
    assert "diagnostic" in str(runner_100k.output_dir)
    assert "100k_scale" in str(runner_100k.output_dir)
