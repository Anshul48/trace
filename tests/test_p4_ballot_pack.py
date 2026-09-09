"""P4 ballot-pack tests: recomputable manifest, complete draft rows, clean scan.

Real temporary files and real subprocesses only; no mocks of domain or
storage. The manifest under docs/program/inbox/p4-ballot-pack/ is a pure
function of the pinned evidence inventory: these tests re-derive it into
tmp dirs and compare byte-for-byte (modulo the creation timestamp).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
GATE_DIR = ROOT_DIR / "docs" / "program" / "inbox" / "p4-ballot-pack"
ASSEMBLER = GATE_DIR / "assemble_ballot_manifest.py"
MANIFEST = GATE_DIR / "evidence_manifest.json"
SCAN_TXT = GATE_DIR / "cert_scan.txt"
DRAFT = GATE_DIR / "ballot_rows_draft.md"

SELF = Path(__file__).resolve()


def _run(*args: str, cwd: Path = ROOT_DIR) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *[str(a) for a in args]],
        cwd=str(cwd), capture_output=True, text=True, timeout=300)


def _load_assembler():
    spec = importlib.util.spec_from_file_location("p4_assembler", ASSEMBLER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_help_lists_all_flags():
    proc = _run(ASSEMBLER, "--help")
    assert proc.returncode == 0, proc.stderr
    for flag in ("--root", "--out", "--scan-out", "--check"):
        assert flag in proc.stdout


def test_manifest_recomputable_into_tmp(tmp_path: Path):
    out = tmp_path / "manifest.json"
    scan = tmp_path / "scan.txt"
    proc = _run(ASSEMBLER, "--out", str(out), "--scan-out", str(scan))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    fresh = json.loads(out.read_text(encoding="utf-8"))
    pinned = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(fresh) == set(pinned)
    for key, value in pinned.items():
        if key == "created_utc":
            continue
        assert fresh[key] == value, key
    assert fresh["cert_scan_verdict"] == "NO-EMISSION-FOUND"
    assert scan.read_text(encoding="utf-8") == SCAN_TXT.read_text(encoding="utf-8")


def test_check_mode_passes_second_party():
    proc = _run(ASSEMBLER, "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BALLOT-CHECK-PASS" in proc.stdout


def test_check_mode_fails_closed_on_tamper(tmp_path: Path):
    tampered = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first_packet = tampered["packets"]["P0"]
    assert first_packet["files"], "P0 inventory must not be empty"
    sha = first_packet["files"][0]["sha256"]
    first_packet["files"][0]["sha256"] = ("0" if sha[0] != "0" else "1") + sha[1:]
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(tampered, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    proc = _run(ASSEMBLER, "--check", "--out", str(bad))
    assert proc.returncode != 0
    assert "BALLOT-CHECK-FAIL" in proc.stdout


def test_check_mode_fails_closed_on_missing_root(tmp_path: Path):
    proc = _run(ASSEMBLER, "--root", str(tmp_path),
                "--out", str(tmp_path / "m.json"),
                "--scan-out", str(tmp_path / "s.txt"))
    assert proc.returncode != 0
    assert "BALLOT-MANIFEST-FAIL" in proc.stdout


def test_manifest_covers_all_packets_with_hashes():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "p4-ballot-manifest/1.0.0"
    assert manifest["base_commit"] == "43ed591732cf1a3649cb241478671b1d37ff489f"
    packets = manifest["packets"]
    assert set(packets) == {"P0", "P1", "P2a", "P2b", "P2c", "P3"}
    assert packets["P0"]["status"] == "HOLD"
    assert packets["P3"]["status"] == "PENDING-CRITIC"
    for pid in ("P1", "P2a", "P2b", "P2c"):
        assert packets[pid]["status"] == "NOT-BUILT"
        assert packets[pid]["files"] == []
        assert packets[pid]["note"], pid
    hashed = [f for p in packets.values() for f in p["files"]]
    assert len(hashed) == 33
    for entry in hashed:
        assert len(entry["sha256"]) == 64
        assert entry["bytes"] > 0


def test_scan_verdict_clean_and_self_exclusion_exact():
    text = SCAN_TXT.read_text(encoding="utf-8")
    assert "verdict: NO-EMISSION-FOUND" in text
    assert "unreviewed hits (0)" in text
    module = _load_assembler()
    assert set(module.SCAN_EXCLUDED) == {
        "docs/program/inbox/h0-1m-corpus-contract/audit/logs/packet.diff",
        "docs/program/inbox/p4-ballot-pack/assemble_ballot_manifest.py",
    }
    assert module.run_scan(ROOT_DIR)["verdict"] == "NO-EMISSION-FOUND"


def test_ballot_rows_complete_and_unsigned():
    text = DRAFT.read_text(encoding="utf-8")
    assert "DRAFT" in text.splitlines()[0]
    assert "06_DECISION_LOG.md" in text
    for gate in ("H0", "CAP-GF", "H2", "Tier-4", "CAP-GG"):
        assert gate in text, gate
    assert text.count("Rollback") >= 5
    assert text.count("Cost/quality") >= 5
    for verdict in ("GO", "NO-GO"):
        assert verdict in text
    assert "PARTIAL" in text
    assert "Signed: <name+date>" not in text
    assert "CERTIFIED" not in text
