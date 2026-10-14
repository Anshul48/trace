"""H0 seal-pipeline repair tests: atomic producer + independent checker.

Real temporary files and real subprocesses only; no mocks of domain or
storage. The full-corpus seal is exercised by scripts/seal_1m_manifest.py at
gate time; these tests pin the fail-closed mechanics on small fixtures plus
the fault-independence of the two recompute paths.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from trace.v2.atomizer import normalize_text

ROOT_DIR = Path(__file__).resolve().parents[1]
PRODUCER = ROOT_DIR / "scripts" / "seal_1m_manifest.py"
CHECKER = ROOT_DIR / "benchmarks" / "verify_1m_independent.py"
PATH1 = ROOT_DIR / "benchmarks" / "verify_1m_checksums.py"
SELECTION_RECORD = ROOT_DIR / "docs" / "program" / "inbox" / "h0-1m-corpus-contract" / "selection_record.json"
RECONCILIATION_MD = ROOT_DIR / "docs" / "program" / "inbox" / "h0-1m-corpus-contract" / "selection_reconciliation.md"
RECONCILIATION_JSON = ROOT_DIR / "docs" / "program" / "inbox" / "h0-1m-corpus-contract" / "selection_reconciliation.json"

SELF = Path(__file__).resolve()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content(title: str, text: str) -> str:
    joined = ("%s\n\n%s" % (title, text)).strip() if title else text.strip()
    return normalize_text(joined)


def _leaf(title: str, text: str) -> str:
    return _sha_bytes(_content(title, text).encode("utf-8"))


def _merkle(leaves: list[str]) -> str:
    if not leaves:
        return _sha_bytes(b"")
    level = [bytes.fromhex(h) for h in sorted(leaves)]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            nxt.append(hashlib.sha256(left + right).digest())
        level = nxt
    return level[0].hex()


def _write_shard(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _load_path1():
    spec = importlib.util.spec_from_file_location("h0_path1_recompute", PATH1)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_checker():
    spec = importlib.util.spec_from_file_location("h0_path2_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mini_selection(tmp_path: Path):
    """Four-shard selection covering generic, enron, and wiki semantics plus dedup."""
    base_recs = [{"id": "k%d" % i, "title": "Base %d" % i, "text": "base body %d" % i}
                 for i in range(5)]
    enron_recs = [{"email_id": "m%d" % i, "subject": "Sub %d" % i, "body": "mail %d" % i}
                  for i in range(3)]
    wiki_recs = [{"doc_id": "w%d" % i, "title": "Wiki %d" % i, "text": "article %d" % i}
                 for i in range(2)]
    dup_recs = ([{"native_id": "d%d" % i, "title": "Delta %d" % i,
                  "content": "delta text %d" % i} for i in range(3)]
                + [{"native_id": "d1", "title": "Delta 1", "content": "delta text 1"}])
    paths = {}
    for name, recs in (("base", base_recs), ("enron", enron_recs),
                       ("wiki", wiki_recs), ("dup", dup_recs)):
        p = tmp_path / ("%s.jsonl" % name)
        _write_shard(p, recs)
        paths[name] = p
    shards = [
        {"dataset_name": "probe-base", "partition": "base_100k",
         "license": "MIT", "license_url": "https://example.com/a",
         "source_file": str(paths["base"]),
         "source_file_sha256": _sha_bytes(paths["base"].read_bytes()),
         "selection_range": "[0, 5)"},
        {"dataset_name": "enron_delta", "partition": "delta_900k",
         "license": "MIT", "license_url": "https://example.com/b",
         "source_file": str(paths["enron"]),
         "source_file_sha256": _sha_bytes(paths["enron"].read_bytes()),
         "selection_range": "[0, 3)"},
        {"dataset_name": "wikipedia_delta", "partition": "delta_900k",
         "license": "MIT", "license_url": "https://example.com/c",
         "source_file": str(paths["wiki"]),
         "source_file_sha256": _sha_bytes(paths["wiki"].read_bytes()),
         "selection_range": "[0, 2)"},
        {"dataset_name": "probe_delta", "partition": "delta_900k",
         "license": "MIT", "license_url": "https://example.com/d",
         "source_file": str(paths["dup"]),
         "source_file_sha256": _sha_bytes(paths["dup"].read_bytes()),
         "selection_range": "[0, 4)"},
    ]
    base_leaves = [_leaf("Base %d" % i, "base body %d" % i) for i in range(5)]
    enron_leaves = [_leaf("Sub %d" % i, "mail %d" % i) for i in range(3)]
    wiki_leaves = [_leaf("Wiki %d" % i, "article %d" % i) for i in range(2)]
    dup_leaves = [_leaf("Delta %d" % i, "delta text %d" % i) for i in range(3)]
    base_bytes = sum(len(_content("Base %d" % i, "base body %d" % i).encode())
                     for i in range(5))
    enron_bytes = sum(len(_content("Sub %d" % i, "mail %d" % i).encode())
                      for i in range(3))
    wiki_bytes = sum(len(_content("Wiki %d" % i, "article %d" % i).encode())
                     for i in range(2))
    dup_bytes = sum(len(_content("Delta %d" % i, "delta text %d" % i).encode())
                    for i in range(3))
    oracle = {
        "probe-base": (5, base_bytes, base_leaves),
        "enron_delta": (3, enron_bytes, enron_leaves),
        "wikipedia_delta": (2, wiki_bytes, wiki_leaves),
        "probe_delta": (3, dup_bytes, dup_leaves),
    }
    record = {"record_id": "TEST-SEL-01", "status": "PROPOSED-UNADOPTED",
              "provenance": {"note": "fixture"}, "shards": shards}
    sel_path = tmp_path / "selection.json"
    sel_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return sel_path, record, oracle


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def _seal(tmp_path: Path, sel_path: Path, output_name: str = "prov.json",
          extra: list[str] | None = None) -> tuple[subprocess.CompletedProcess, Path]:
    gate_dir = tmp_path / "gate"
    cmd = [sys.executable, str(PRODUCER), "--selection", str(sel_path),
           "--gate-dir", str(gate_dir), "--output-name", output_name] + (extra or [])
    return _run(cmd), gate_dir / output_name


def _expect_for(oracle: dict, sel_path: Path) -> Path:
    base_docs = oracle["probe-base"][0]
    delta_docs = (oracle["enron_delta"][0] + oracle["wikipedia_delta"][0]
                  + oracle["probe_delta"][0])
    base_bytes = oracle["probe-base"][1]
    delta_bytes = (oracle["enron_delta"][1] + oracle["wikipedia_delta"][1]
                   + oracle["probe_delta"][1])
    base_root = _merkle(oracle["probe-base"][2])
    delta_leaves = (oracle["enron_delta"][2] + oracle["wikipedia_delta"][2]
                    + oracle["probe_delta"][2])
    delta_root = _merkle(delta_leaves)
    union_root = _merkle(oracle["probe-base"][2] + delta_leaves)
    expect = {
        "target_unique_documents_d": base_docs + delta_docs,
        "base_100k_documents_count": base_docs,
        "delta_900k_documents_count": delta_docs,
        "base_intersect_delta_count": 0,
        "total_raw_text_bytes": base_bytes + delta_bytes,
        "base_raw_text_bytes": base_bytes,
        "delta_raw_text_bytes": delta_bytes,
        "base_merkle_root_sha256": base_root,
        "delta_merkle_root_sha256": delta_root,
        "union_merkle_root_sha256": union_root,
    }
    for name, (count, nbytes, _leaves) in oracle.items():
        expect["%s::selected_records_d" % name] = count
        expect["%s::selected_text_bytes" % name] = nbytes
    out = sel_path.parent / "expect.json"
    out.write_text(json.dumps(expect, indent=2), encoding="utf-8")
    return out


def test_producer_publishes_provisional_on_coherent_selection(tmp_path, mini_selection):
    sel_path, record, oracle = mini_selection
    proc, prov_path = _seal(tmp_path, sel_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[SEAL-PUBLISH]" in proc.stdout
    assert prov_path.exists()
    assert not (prov_path.parent / (prov_path.name + ".seal-tmp")).exists()
    provisional = json.loads(prov_path.read_text(encoding="utf-8"))
    assert provisional["artifact"] == "h0-provisional-1m-manifest"
    assert provisional["status"] == "PROVISIONAL-UNADOPTED"
    assert provisional["signature"] is None
    assert provisional["co_signature"]["status"] == "PENDING_HUMAN_BALLOT"
    assert provisional["producer"]["script"] == "scripts/seal_1m_manifest.py"
    assert provisional["producer"]["script_sha256"] == _sha_bytes(PRODUCER.read_bytes())
    assert provisional["producer"]["selection_sha256"] == _sha_bytes(sel_path.read_bytes())
    claims = provisional["claims"]
    for name, (count, nbytes, _leaves) in oracle.items():
        row = next(s for s in claims["shards"] if s["dataset_name"] == name)
        assert row["selected_records_d"] == count
        assert row["selected_text_bytes"] == nbytes
    expect_path = _expect_for(oracle, sel_path)
    expect = json.loads(expect_path.read_text(encoding="utf-8"))
    for key, wanted in expect.items():
        if "::" in key:
            shard_name, field = key.split("::", 1)
            seen = next(s for s in claims["shards"]
                        if s["dataset_name"] == shard_name)[field]
        else:
            seen = claims[key]
        assert seen == wanted, key


def test_producer_accepts_matching_expect_file(tmp_path, mini_selection):
    sel_path, _record, oracle = mini_selection
    expect_path = _expect_for(oracle, sel_path)
    proc, prov_path = _seal(tmp_path, sel_path, extra=["--expect", str(expect_path)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert prov_path.exists()


# --- producer: refusal modes --------------------------------------------------

def test_producer_refuses_changed_ranges_with_stale_roots(tmp_path, mini_selection):
    sel_path, record, oracle = mini_selection
    record["shards"][3]["selection_range"] = "[0, 2)"
    sel_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    expect_path = _expect_for(oracle, sel_path)  # stale: pinned to the [0, 4) truth
    proc, prov_path = _seal(tmp_path, sel_path, extra=["--expect", str(expect_path)])
    assert proc.returncode != 0
    assert "SEAL-REFUSE" in proc.stdout
    assert "expect-mismatch" in proc.stdout
    assert not prov_path.exists()
    assert not (prov_path.parent / (prov_path.name + ".seal-tmp")).exists()


def test_producer_refuses_replaced_shard_file(tmp_path, mini_selection):
    sel_path, _record, oracle = mini_selection
    victim = Path(json.loads(sel_path.read_text(encoding="utf-8"))["shards"][0]["source_file"])
    with open(victim, "a", encoding="utf-8") as handle:
        handle.write('{"id": "intruder", "title": "X", "text": "replaced"}\n')
    expect_path = _expect_for(oracle, sel_path)
    proc, prov_path = _seal(tmp_path, sel_path, extra=["--expect", str(expect_path)])
    assert proc.returncode != 0
    assert "source-sha-drift" in proc.stdout
    assert not prov_path.exists()


def test_producer_refuses_inconsistent_totals(tmp_path, mini_selection):
    sel_path, _record, oracle = mini_selection
    expect_path = _expect_for(oracle, sel_path)
    expect = json.loads(expect_path.read_text(encoding="utf-8"))
    expect["total_raw_text_bytes"] = expect["total_raw_text_bytes"] + 1
    expect["union_merkle_root_sha256"] = "00" * 32
    expect_path.write_text(json.dumps(expect), encoding="utf-8")
    proc, prov_path = _seal(tmp_path, sel_path, extra=["--expect", str(expect_path)])
    assert proc.returncode != 0
    assert "expect-mismatch" in proc.stdout
    assert not prov_path.exists()


def test_kill9_mid_write_leaves_no_publishable_manifest(tmp_path, mini_selection):
    sel_path, _record, _oracle = mini_selection
    gate_dir = tmp_path / "gate"
    prov_path = gate_dir / "prov.json"
    tmp_path_ = gate_dir / "prov.json.seal-tmp"
    proc = subprocess.Popen(
        [sys.executable, str(PRODUCER), "--selection", str(sel_path),
         "--gate-dir", str(gate_dir), "--output-name", "prov.json",
         "--stall-before-publish", "30"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if tmp_path_.exists():
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert tmp_path_.exists(), "producer never reached the pre-publish stall"
        proc.kill()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    assert proc.returncode == -signal.SIGKILL
    assert not prov_path.exists()
    # A later clean run publishes normally; the stale tmp is never adopted.
    proc2, _ = _seal(tmp_path, sel_path, output_name="prov2.json")
    assert proc2.returncode == 0
    assert (gate_dir / "prov2.json").exists()


# --- checker: agreement + planted-bug capture ---------------------------------

def test_checker_passes_on_producer_output(tmp_path, mini_selection):
    sel_path, _record, _oracle = mini_selection
    proc, prov_path = _seal(tmp_path, sel_path)
    assert proc.returncode == 0
    check = _run([sys.executable, str(CHECKER), "--manifest", str(prov_path)])
    assert check.returncode == 0, check.stdout + check.stderr
    assert "[INDEPENDENT-PASS]" in check.stdout
    assert "UNADOPTED" in check.stdout


def test_checker_catches_planted_count_bug(tmp_path, mini_selection):
    sel_path, _record, _oracle = mini_selection
    proc, prov_path = _seal(tmp_path, sel_path)
    assert proc.returncode == 0
    provisional = json.loads(prov_path.read_text(encoding="utf-8"))
    victim = next(s for s in provisional["claims"]["shards"]
                  if s["dataset_name"] == "probe_delta")
    victim["selected_records_d"] = victim["selected_records_d"] - 1  # planted miscount
    bad_path = tmp_path / "planted.json"
    bad_path.write_text(json.dumps(provisional, indent=2), encoding="utf-8")
    check = _run([sys.executable, str(CHECKER), "--manifest", str(bad_path)])
    assert check.returncode != 0
    assert "INDEPENDENT-FAIL" in check.stdout
    assert "shard-count-mismatch" in check.stdout
    assert "probe_delta" in check.stdout


def test_checker_rejects_flipped_co_signature(tmp_path, mini_selection):
    sel_path, _record, _oracle = mini_selection
    proc, prov_path = _seal(tmp_path, sel_path)
    assert proc.returncode == 0
    provisional = json.loads(prov_path.read_text(encoding="utf-8"))
    provisional["co_signature"]["status"] = "HUMAN_SIGNED"
    flipped = tmp_path / "flipped.json"
    flipped.write_text(json.dumps(provisional, indent=2), encoding="utf-8")
    check = _run([sys.executable, str(CHECKER), "--manifest", str(flipped)])
    assert check.returncode != 0
    assert "co-signature-not-pending" in check.stdout


# --- fault-independence of the two paths --------------------------------------

def test_paths_agree_on_fixture_and_diverge_with_cause(tmp_path, mini_selection):
    sel_path, record, oracle = mini_selection
    path1 = _load_path1()
    path2 = _load_checker()
    pseudo = [{"dataset_name": e["dataset_name"], "partition": e["partition"],
               "source_file": e["source_file"], "selection_range": e["selection_range"]}
              for e in record["shards"]]
    resolved = {e["source_file"]: Path(e["source_file"]) for e in record["shards"]}
    rows, base_leaves, delta_leaves, base_bytes, delta_bytes = path1.run_selection(
        pseudo, resolved, set(), set())
    scanner = path2._ShardScanner()
    releaves_base, releaves_delta = [], []
    re_base_bytes = re_delta_bytes = 0
    ordered = ([e for e in record["shards"] if e["partition"] == "base_100k"]
               + [e for e in record["shards"] if e["partition"] == "delta_900k"])
    per_shard = {}
    for entry in ordered:
        start, end = path2._split_range(entry["selection_range"])
        found, num_bytes, leaves = scanner.scan(
            entry["dataset_name"], Path(entry["source_file"]), start, end)
        per_shard[entry["dataset_name"]] = (found, num_bytes)
        if entry["partition"] == "base_100k":
            releaves_base.extend(leaves)
            re_base_bytes += num_bytes
        else:
            releaves_delta.extend(leaves)
            re_delta_bytes += num_bytes
    for row in rows:
        assert per_shard[row["dataset_name"]] == (row["recomputed_docs"],
                                                  row["recomputed_bytes"])
    assert (base_bytes, delta_bytes) == (re_base_bytes, re_delta_bytes)
    assert path1.compute_merkle_root(base_leaves) == path2._root_for(releaves_base)
    assert path1.compute_merkle_root(delta_leaves) == path2._root_for(releaves_delta)
    assert path1.compute_merkle_root(base_leaves + delta_leaves) == \
        path2._root_for(releaves_base + releaves_delta)
    # Static independence: the checker shares no claim-calculation imports.
    checker_src = CHECKER.read_text(encoding="utf-8").splitlines()
    for line in checker_src:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            assert "verify_1m_checksums" not in stripped
            assert "seal_1m_manifest" not in stripped
    # Diverges with cause on a mutated claim (function-level, real tmp file).
    proc, prov_path = _seal(tmp_path, sel_path)
    assert proc.returncode == 0
    passed, failures, _detail = path2.check_provisional(prov_path)
    assert passed, failures
    provisional = json.loads(prov_path.read_text(encoding="utf-8"))
    provisional["claims"]["delta_raw_text_bytes"] += 7
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(provisional), encoding="utf-8")
    passed2, failures2, _d2 = path2.check_provisional(mutated)
    assert not passed2
    assert any("total-mismatch" in f and "delta_raw_text_bytes" in f for f in failures2)


# --- entry points and hygiene ---------------------------------------------------

def test_help_entry_points():
    for cmd in ([sys.executable, str(PRODUCER), "--help"],
                [sys.executable, str(CHECKER), "--help"]):
        proc = _run(cmd)
        assert proc.returncode == 0
        assert "usage:" in proc.stdout


def test_new_files_have_no_phantom_tooling_or_self_certification():
    phantom_head = "trace" + "-" + "bench"
    router = "Activation" + "Router"
    store_mod = "spine" + "."
    cert_token = "CERTI" + "FIED"
    appr_token = "APPRO" + "VED"
    # Data-bearing records pin byte-exact on-disk source paths (which live
    # under a staging directory whose name contains the phantom prefix), so
    # the phantom-tooling scan covers code only; the self-certification scan
    # covers every packet file.
    code_targets = [PRODUCER, CHECKER, SELF]
    all_targets = code_targets + [SELECTION_RECORD, RECONCILIATION_MD, RECONCILIATION_JSON]
    for path in all_targets:
        assert path.exists(), "missing packet file %s" % path
    for path in code_targets:
        text = path.read_text(encoding="utf-8")
        for token in (phantom_head, router, store_mod):
            assert token not in text, "banned token %r in %s" % (token, path)
    for path in all_targets:
        text = path.read_text(encoding="utf-8")
        for token in (cert_token, appr_token):
            assert token not in text, "banned token %r in %s" % (token, path)

