"""H0 packet tests: 1M corpus-contract adoption (fail-closed, no domain mocks).

Uses real temporary files and real subprocesses only. The full 1M
recompute is exercised by scripts/sign_gate_manifest.py at gate time;
these tests pin the verifier/signer mechanics on small fixtures plus
byte-exact guards on frozen semantics.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
VERIFIER = ROOT_DIR / "benchmarks" / "verify_1m_checksums.py"
SIGNER = ROOT_DIR / "scripts" / "sign_gate_manifest.py"
FROZEN_VERIFIER = ROOT_DIR / "benchmarks" / "verify_dataset_checksums.py"


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("verify_1m_checksums", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_shard(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def leaf_of(title: str, text: str) -> str:
    full = f"{title}\n\n{text}".strip() if title else text.strip()
    return sha_bytes(full.encode("utf-8"))


def merkle(leaves: list[str]) -> str:
    level = [bytes.fromhex(h) for h in sorted(leaves)]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            nxt.append(hashlib.sha256(left + right).digest())
        level = nxt
    return level[0].hex()


@pytest.fixture()
def mini_capsule(tmp_path: Path):
    """Two-shard capsule whose per-shard figures are exactly right.

    Header totals intentionally use the real 1M contract constants, so the
    strict verdict FAILs on totals only — proving fail-closed while letting
    the recompute mechanics be asserted exactly via --emit-json.
    """
    recs_a = [
        {"id": f"a{i}", "title": f"T{i}", "text": f"alpha body {i}"}
        for i in range(5)
    ]
    recs_b = [
        {"doc_id": f"b{i}", "title": "", "content": f"beta content {i}"}
        for i in range(3)
    ]
    pa = tmp_path / "a.jsonl"
    pb = tmp_path / "b.jsonl"
    write_shard(pa, recs_a)
    write_shard(pb, recs_b)
    leaves_a = [leaf_of(f"T{i}", f"alpha body {i}") for i in range(5)]
    leaves_b = [leaf_of("", f"beta content {i}") for i in range(3)]
    ba = sum(len(f"T{i}\n\nalpha body {i}".encode()) for i in range(5))
    bb = sum(len(f"beta content {i}".encode()) for i in range(3))
    manifest = {
        "contract_version": "2.0.0",
        "target_unique_documents_d": 1000000,
        "base_100k_documents_count": 100000,
        "delta_900k_documents_count": 900000,
        "base_intersect_delta_count": 0,
        "total_raw_text_bytes": ba + bb,
        "base_raw_text_bytes": ba,
        "delta_raw_text_bytes": bb,
        "base_merkle_root_sha256": merkle(leaves_a),
        "delta_merkle_root_sha256": merkle(leaves_b),
        "union_merkle_root_sha256": merkle(leaves_a + leaves_b),
        "synthetic_data_used": False,
        "in_memory_fallback_used": False,
        "datasets_base": [{
            "dataset_name": "probe-a", "partition": "base_100k",
            "license": "MIT", "license_url": "https://example.com",
            "selected_records_d": 5, "selection_range": "[0, 5)",
            "selected_text_bytes": ba, "source_file": str(pa),
            "source_file_sha256": sha_bytes(pa.read_bytes()),
        }],
        "datasets_delta": [{
            "dataset_name": "probe-b", "partition": "delta_900k",
            "license": "MIT", "license_url": "https://example.com",
            "selected_records_d": 3, "selection_range": "[0, 3)",
            "selected_text_bytes": bb, "source_file": str(pb),
            "source_file_sha256": sha_bytes(pb.read_bytes()),
        }],
    }
    mp = tmp_path / "mini_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return mp, manifest, {"a": (ba, leaves_a), "b": (bb, leaves_b)}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# --- unit: Merkle construction vectors -------------------------------------

def test_merkle_empty_is_sha256_of_empty():
    v = load_verifier_module()
    assert v.compute_merkle_root([]) == sha_bytes(b"")


def test_merkle_singleton_is_leaf():
    v = load_verifier_module()
    assert v.compute_merkle_root(["ab" * 32]) == "ab" * 32


def test_merkle_odd_duplicates_last_and_sorts():
    v = load_verifier_module()
    leaves = ["cc" * 32, "aa" * 32, "bb" * 32]
    level = [bytes.fromhex(h) for h in sorted(leaves)]
    left = hashlib.sha256(level[0] + level[1]).digest()
    right = hashlib.sha256(level[2] + level[2]).digest()
    expected = hashlib.sha256(left + right).hexdigest()
    assert v.compute_merkle_root(leaves) == expected
    assert v.compute_merkle_root(list(reversed(leaves))) == expected


def test_content_hash_primitive_is_atomizer_normalize():
    v = load_verifier_module()
    from trace.v2.atomizer import normalize_text
    assert v.normalize_text is normalize_text


# --- fail-closed subprocess probes ------------------------------------------

def test_fail_closed_missing_source(tmp_path: Path, mini_capsule):
    mp, manifest, _ = mini_capsule
    manifest["datasets_base"][0]["source_file"] = str(tmp_path / "absent.jsonl")
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    proc = run([sys.executable, str(VERIFIER), "--manifest", str(mp)])
    assert proc.returncode != 0
    assert "Unresolvable source_file" in proc.stdout


def test_fail_closed_sha_drift(tmp_path: Path, mini_capsule):
    mp, manifest, _ = mini_capsule
    pa = Path(manifest["datasets_base"][0]["source_file"])
    with open(pa, "a", encoding="utf-8") as f:
        f.write('{"id": "evil", "text": "tampered"}\n')
    proc = run([sys.executable, str(VERIFIER), "--manifest", str(mp)])
    assert proc.returncode != 0
    assert "SHA-256 mismatch" in proc.stdout


def test_fail_closed_count_drift(mini_capsule):
    mp, manifest, _ = mini_capsule
    manifest["datasets_base"][0]["selected_records_d"] = 4
    mp.write_text(json.dumps(manifest), encoding="utf-8")
    proc = run([sys.executable, str(VERIFIER), "--manifest", str(mp)])
    assert proc.returncode != 0
    assert "doc count mismatch" in proc.stdout


def test_recompute_exact_on_mini_fixture(tmp_path: Path, mini_capsule):
    mp, manifest, expect = mini_capsule
    out = tmp_path / "summary.json"
    proc = run([sys.executable, str(VERIFIER), "--manifest", str(mp),
                "--emit-json", str(out)])
    assert proc.returncode != 0  # totals gate holds: 8 docs != 1M contract
    assert "Base doc total mismatch" in proc.stdout
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["passed"] is False
    assert {e.split(":")[0] for e in summary["errors"]} == {
        "Base doc total mismatch",
        "Delta doc total mismatch",
        "Union uniqueness mismatch",
    }
    rows = {r["dataset_name"]: r for r in summary["summary"]["shards"]}
    assert rows["probe-a"]["recomputed_docs"] == 5
    assert rows["probe-a"]["recomputed_bytes"] == expect["a"][0]
    assert rows["probe-b"]["recomputed_docs"] == 3
    assert rows["probe-b"]["recomputed_bytes"] == expect["b"][0]
    assert summary["summary"]["recomputed_base_merkle"] == manifest["base_merkle_root_sha256"]
    assert summary["summary"]["recomputed_delta_merkle"] == manifest["delta_merkle_root_sha256"]
    assert summary["summary"]["recomputed_union_merkle"] == manifest["union_merkle_root_sha256"]


def test_forensic_pass_never_changes_strict_verdict(tmp_path: Path, mini_capsule):
    mp, manifest, _ = mini_capsule
    out = tmp_path / "summary.json"
    proc = run([sys.executable, str(VERIFIER), "--manifest", str(mp),
                "--emit-json", str(out),
                "--forensic-overrides", json.dumps({"probe-a": "[0, 2)"})])
    assert proc.returncode != 0
    assert "FORENSIC-NON-CERTIFYING" in proc.stdout
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["passed"] is False
    forensic = summary["forensic_non_certifying"]
    assert forensic["certifying"] is False
    assert forensic["range_overrides"] == {"probe-a": "[0, 2)"}
    row = next(r for r in forensic["shards"] if r["dataset_name"] == "probe-a")
    assert row["recomputed_docs"] == 2  # override applied in analysis only
    strict_row = next(r for r in summary["summary"]["shards"]
                      if r["dataset_name"] == "probe-a")
    assert strict_row["recomputed_docs"] == 5  # strict unaffected


# --- signer HOLD path --------------------------------------------------------

def test_signer_hold_manifest_on_strict_fail(tmp_path: Path, mini_capsule):
    mp, manifest, _ = mini_capsule
    gate_dir = tmp_path / "gate"
    proc = run([sys.executable, str(SIGNER), "--manifest", str(mp),
                "--gate-dir", str(gate_dir), "--gate-id", "H0-TEST",
                "--forensic-overrides", "{}"])
    assert proc.returncode != 0
    assert "HOLD" in proc.stdout
    gate = json.loads((gate_dir / "gate_manifest.json").read_text(encoding="utf-8"))
    assert gate["gate_id"] == "H0-TEST"
    assert gate["verdict"] == "HOLD"
    assert gate["signed"] is False
    assert gate["verification"]["strict_passed"] is False
    assert len(gate["verification"]["strict_errors"]) == 3
    assert set(gate["path_map"]) == {
        manifest["datasets_base"][0]["source_file"],
        manifest["datasets_delta"][0]["source_file"],
    }
    assert [s["dataset_name"] for s in gate["sources"]] == ["probe-a", "probe-b"]
    assert all("license" in s and "source_file_sha256" in s for s in gate["sources"])
    assert gate["tokenizer_identity"]["module"] == "trace.v2.atomizer"
    assert gate["frozen_workload_vector"]["target_standard"] == "DEC-P-005b-LEVEL2"
    base_commit = gate["revision_scope"]["packet_base_commit"]
    assert base_commit == "0150fbc19cc25bf2cb080bb797b535c3f4f5499d"
    assert gate["co_signature"]["status"] == "PENDING_HUMAN_BALLOT"


# --- frozen-semantics guards ---------------------------------------------------

def test_frozen_beir_manifest_id_check_byte_identical():
    lines = FROZEN_VERIFIER.read_text(encoding="utf-8").splitlines()
    assert lines[55] == '    if manifest.get("manifest_id") != "beir_musique_frozen_v1":'


def test_new_packet_files_have_no_phantom_tooling():
    phantom = ["trace" + "-bench", "Activation" + "Router", "spine" + "."]
    for path in (VERIFIER, SIGNER):
        text = path.read_text(encoding="utf-8")
        for token in phantom:
            assert token not in text, f"phantom tooling {token!r} in {path}"
        for token in ('"CERTIFIED', "'CERTIFIED", '"APPROVED', "'APPROVED"):
            assert token not in text, f"self-certification string {token!r} in {path}"


def test_help_entry_points():
    for cmd in ([sys.executable, str(VERIFIER), "--help"],
                [sys.executable, str(SIGNER), "--help"]):
        proc = run(cmd)
        assert proc.returncode == 0
        assert "usage:" in proc.stdout
