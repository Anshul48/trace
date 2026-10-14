"""W2: the shipped Phase 1 demo runs green against installed code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos" / "demo_phase1_api.py"


def test_demo_script_exists_and_uses_installed_sdk() -> None:
    text = DEMO.read_text(encoding="utf-8")
    assert "from trace_local import Trace" in text
    assert "insufficient_evidence" in text
    assert "verify_integrity" in text


def test_demo_passes_offline(tmp_path) -> None:
    proc = subprocess.run(
        [sys.executable, str(DEMO), "--data-dir", str(tmp_path / "data"), "--quiet"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "DEMO PASS" in proc.stdout


def test_demo_fixture_has_three_records() -> None:
    lines = (
        (ROOT / "demos" / "fixtures" / "demo_docs.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 3
