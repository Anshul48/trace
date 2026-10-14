"""W2c: the primary C2-10M demo runs green on pinned bytes, offline."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("blake3")

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demos" / "demo_c10m_narrow.py"
PINS = ROOT / "c10m" / "PINS.sha256"

SHIPPED_QUERY_SHA = (
    "d7756e72e2de65814103e216edfc7d53650cc0fada34cefe7cf41411f03414ce"
)


def test_demo_script_uses_pinned_serving_stack() -> None:
    text = DEMO.read_text(encoding="utf-8")
    assert "c10m/serving" in text or 'C10M / "serving"' in text
    assert "NarrowQuery" in text
    assert SHIPPED_QUERY_SHA in text  # runtime byte-identity guard
    assert "sha256" in text  # stand-in encoder is disclosed, not hidden


def test_pins_manifest_covers_tree() -> None:
    lines = [ln for ln in PINS.read_text().splitlines() if ln.strip()]
    assert len(lines) == 110  # 85 producer + 7 serving + 3 policy + README + 14 data
    for line in lines:
        want, _, rel = line.partition("  ")
        data = (ROOT / "c10m" / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == want, rel


def test_demo_passes_offline(tmp_path) -> None:
    proc = subprocess.run(
        [sys.executable, str(DEMO), "--data-dir", str(tmp_path / "data"),
         "--quiet", "--out", str(tmp_path / "results.json")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "DEMO PASS" in proc.stdout
    assert "pinned C2-10M serving stack ran offline" in proc.stdout


def test_demo_fixture_has_six_records() -> None:
    lines = (
        (ROOT / "demos" / "fixtures" / "c10m_synth_docs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(lines) == 6
