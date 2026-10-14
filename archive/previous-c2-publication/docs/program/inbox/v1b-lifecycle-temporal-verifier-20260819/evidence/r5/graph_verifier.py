from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(worktree: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(worktree), *args], text=True).strip()


def run_command(command: list[str], cwd: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    started = datetime.now(UTC)
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    finished = datetime.now(UTC)
    return {
        "command": command,
        "cwd": str(cwd),
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "exit_code": proc.returncode,
        "stdout": stdout_path.as_posix(),
        "stderr": stderr_path.as_posix(),
    }


class EdgeForest:
    def __init__(self, edges: list[dict[str, Any]]):
        self.edges = edges

    def get_neighbor_edges(self, node_ids: list[str], limit: int = 2000):
        wanted = set(node_ids)
        rows = [
            edge
            for edge in self.edges
            if edge["source_atom_id"] in wanted or edge["target_atom_id"] in wanted
        ]
        return rows[:limit]


class SlowForest:
    def get_neighbor_edges(self, node_ids: list[str], limit: int = 2000):
        time.sleep(0.045)
        return []


class MemoryForest:
    def __init__(self):
        self.retained: bytearray | None = None

    def get_neighbor_edges(self, node_ids: list[str], limit: int = 2000):
        self.retained = bytearray(72 * 1024 * 1024)
        return []


def edge(edge_id: str, source: str, target: str, relation: str = "NEXT") -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "source_atom_id": source,
        "target_atom_id": target,
        "relation_type": relation,
        "weight": 1.0,
        "confidence": 1.0,
    }


def bounded_case(forest: Any, seeds: dict[str, float]):
    from trace_lite.engines.lattice import LatticeEngine

    engine = LatticeEngine(
        llm=None,
        embedder=None,
        vector_store=None,
        forest=forest,
        spine=None,
    )
    return engine._bounded_graph_activation(seeds, time.perf_counter())


def run_product_matrix(scratch: Path) -> dict[str, Any]:
    from trace_lite.cortex import ForestIndex
    from trace_lite.engines.graph import DEFAULT_GRAPH_POLICY, generate_co_occurrence_edges
    from trace_lite.spine import Atom

    receipts: dict[str, Any] = {}

    scores, receipt = bounded_case(SlowForest(), {"seed": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "query_wall_time_ms" in receipt["overflow_codes"]
    assert receipt["elapsed_ms"] >= DEFAULT_GRAPH_POLICY.query_wall_time_ms
    receipts["wall_time"] = receipt

    memory_forest = MemoryForest()
    scores, receipt = bounded_case(memory_forest, {"seed": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "query_working_memory_bytes" in receipt["overflow_codes"]
    assert receipt["peak_working_memory_bytes"] > DEFAULT_GRAPH_POLICY.query_memory_bytes
    receipts["working_memory"] = receipt
    memory_forest.retained = None

    seeds = {f"seed-{index:03d}": 1.0 for index in range(DEFAULT_GRAPH_POLICY.ppr_max_activated_nodes + 1)}
    scores, receipt = bounded_case(EdgeForest([]), seeds)
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "activated_nodes" in receipt["overflow_codes"]
    assert receipt["activated_nodes"] == DEFAULT_GRAPH_POLICY.ppr_max_activated_nodes + 1
    receipts["activated_nodes"] = receipt

    edges = [edge(f"edge-{index:04d}", "seed", f"node-{index:04d}") for index in range(2501)]
    scores, receipt = bounded_case(EdgeForest(edges), {"seed": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "traversed_edges" in receipt["overflow_codes"]
    assert receipt["traversed_edges"] <= DEFAULT_GRAPH_POLICY.ppr_max_traversed_edges
    receipts["traversed_edges"] = receipt

    structural = [edge(f"struct-{index:02d}", "seed", f"node-{index:02d}") for index in range(33)]
    scores, receipt = bounded_case(EdgeForest(structural), {"seed": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "structural_edges_per_node" in receipt["overflow_codes"]
    assert receipt["structural_edges_capped"] > 0
    receipts["structural_cap"] = receipt

    soft = [edge(f"soft-{index:02d}", "seed", f"node-{index:02d}", "CO_OCCURS") for index in range(51)]
    scores, receipt = bounded_case(EdgeForest(soft), {"seed": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "soft_affinity_degree" in receipt["overflow_codes"]
    assert receipt["soft_affinity_edges_capped"] > 0
    receipts["soft_degree_cap"] = receipt

    chain = [edge(f"chain-{index}", f"node-{index}", f"node-{index + 1}") for index in range(6)]
    scores, receipt = bounded_case(EdgeForest(chain), {"node-0": 1.0})
    assert scores == {}
    assert receipt["status"] == "bounded_incomplete"
    assert "max_depth" in receipt["overflow_codes"]
    receipts["max_depth"] = receipt

    exact = chain[:4]
    scores, receipt = bounded_case(EdgeForest(exact), {"node-0": 1.0})
    assert receipt["status"] == "complete"
    assert "max_depth" not in receipt["overflow_codes"]
    assert set(scores) == {f"node-{index}" for index in range(5)}
    receipts["exact_depth_leaf"] = receipt

    ranking_edges = [edge(f"rank-{index:03d}", f"seed-{index:03d}", f"ranked-{index:03d}") for index in range(100)]
    ranking_seeds = {f"seed-{index:03d}": float(101 - index) for index in range(100)}
    first_scores, receipt = bounded_case(EdgeForest(ranking_edges), ranking_seeds)
    second_scores, repeat = bounded_case(EdgeForest(ranking_edges), ranking_seeds)
    assert receipt["status"] == "complete"
    assert len(first_scores) == DEFAULT_GRAPH_POLICY.ppr_top_k
    assert receipt["ppr_returned_nodes"] == DEFAULT_GRAPH_POLICY.ppr_top_k
    assert first_scores == second_scores
    assert receipt["ppr_iterations"] <= DEFAULT_GRAPH_POLICY.ppr_max_iterations
    receipts["top_k_and_repeatability"] = {"first": receipt, "second": repeat}

    atoms = [
        Atom.create(
            f"atom-{index:03d}",
            "boilerplate boundedcluster" if index < 52 else f"boilerplate unique-{index:03d}",
            "fixture",
            index,
            index * 10,
            index * 10 + 10,
            created_at="2026-01-01T00:00:00+00:00",
        )
        for index in range(600)
    ]
    first_telemetry: dict[str, Any] = {}
    second_telemetry: dict[str, Any] = {}
    first_edges = generate_co_occurrence_edges(atoms, telemetry=first_telemetry)
    second_edges = generate_co_occurrence_edges(atoms, telemetry=second_telemetry)
    stable = lambda rows: [
        (item["source_atom_id"], item["target_atom_id"], item["relation_type"], item.get("witness_terms"))
        for item in rows
    ]
    assert first_telemetry["skipped_high_df_terms"] > 0
    assert first_telemetry["candidate_partner_cap_hits"] > 0
    assert first_telemetry["degree_cap_drops"] > 0
    assert first_telemetry["max_soft_degree"] <= DEFAULT_GRAPH_POLICY.max_soft_affinity_degree
    assert stable(first_edges) == stable(second_edges)
    receipts["association_build"] = first_telemetry

    db_path = scratch / "candidate-invisibility.sqlite3"
    forest = ForestIndex(db_path)
    active_edge = edge("active-edge", "a", "b")
    candidate_edge = edge("candidate-edge", "candidate-a", "candidate-b")
    forest.create_index_build({"build_id": "active", "state": "building"})
    forest.activate_index_build("active", graph_edges=[active_edge])
    forest.create_index_build({"build_id": "candidate", "state": "building"})
    forest.store_edges([candidate_edge], build_id="candidate")
    active_ids = [item["edge_id"] for item in forest.get_all_edges()]
    candidate_ids = [item["edge_id"] for item in forest.get_all_edges(build_id="candidate")]
    assert active_ids == ["active-edge"]
    assert candidate_ids == ["candidate-edge"]
    receipts["candidate_invisibility"] = {"active_edge_ids": active_ids, "candidate_edge_ids": candidate_ids}

    return receipts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lease", type=Path, required=True)
    args = parser.parse_args()
    lease = json.loads(args.lease.read_text(encoding="utf-8"))
    worktree = Path(lease["worktree"]["path"]).resolve()
    result = Path(lease["worktree"]["result_path"]).resolve()
    scratch = Path(lease["worktree"]["scratch_path"]).resolve()
    provision = Path(lease["worktree"]["provision_path"]).resolve()
    assert sha256(Path(__file__).resolve()) == lease["verifier_asset"]["sha256"]
    result.mkdir(parents=True, exist_ok=False)
    scratch.mkdir(parents=True, exist_ok=True)

    provision_manifest = json.loads((provision / "provision_manifest.json").read_text(encoding="utf-8"))
    for relative, expected in provision_manifest.items():
        source = provision / relative
        assert sha256(source) == expected
        target = result / "environment" / "provision" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    provision_receipt = json.loads((provision / "provision_receipt.json").read_text(encoding="utf-8"))
    assert provision_receipt["exit_code"] == 0
    assert provision_receipt["environment_created_fresh"] is True
    assert provision_receipt["system_site_packages_disabled"] is True
    assert provision_receipt["candidate_commit"] == lease["candidate"]["commit"]
    assert provision_receipt["candidate_tree"] == lease["candidate"]["tree"]
    (result / "authority").mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.lease, result / "authority" / "lease.json")

    expires = datetime.fromisoformat(lease["expires_at_utc"].replace("Z", "+00:00"))
    assert datetime.now(UTC) < expires
    assert Path.cwd().resolve() == worktree
    assert Path(sys.executable).resolve() == Path(lease["worktree"]["venv_executable"]).resolve()
    assert git(worktree, "rev-parse", "HEAD") == lease["candidate"]["commit"]
    assert git(worktree, "rev-parse", "HEAD^{tree}") == lease["candidate"]["tree"]
    assert git(worktree, "status", "--porcelain") == ""
    lock_path = worktree / "uv.lock"
    assert sha256(lock_path) == lease["candidate"]["lock_sha256"]
    shutil.copy2(lock_path, result / "authority" / "uv.lock")

    commands: list[dict[str, Any]] = []
    sync = run_command(
        ["uv", "sync", "--frozen", "--offline", "--extra", "dev", "--cache-dir", lease["worktree"]["cache_path"]],
        worktree,
        result / "environment" / "uv_sync.stdout.log",
        result / "environment" / "uv_sync.stderr.log",
    )
    commands.append(sync)
    assert sync["exit_code"] == 0
    assert git(worktree, "status", "--porcelain") == ""

    packages = sorted(
        ({"name": dist.metadata.get("Name", ""), "version": dist.version} for dist in importlib.metadata.distributions()),
        key=lambda item: (item["name"].lower(), item["version"]),
    )
    required = {item["name"].lower(): item["version"] for item in packages}
    assert required["torch"].split("+")[0] == "2.13.0"
    assert "numpy" in required and "lancedb" in required and "pytest" in required
    write_json(result / "environment" / "installed_packages.json", packages)
    write_json(
        result / "environment" / "identity.json",
        {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "uv_version": subprocess.check_output(["uv", "--version"], text=True).strip(),
            "lock_sha256": sha256(lock_path),
            "candidate": lease["candidate"],
            "git_status": "clean",
        },
    )

    product_matrix = run_product_matrix(scratch)
    write_json(result / "receipts" / "product_path_limits.json", product_matrix)

    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(scratch / "pytest"),
        "tests/test_tl2_bounded_graph.py",
        "tests/test_graph.py",
        "tests/test_cortex_lifecycle.py",
        "tests/test_lifecycle.py",
        "tests/test_engines.py",
    ]
    pytest_run = run_command(
        pytest_command,
        worktree,
        result / "raw" / "pytest.stdout.log",
        result / "raw" / "pytest.stderr.log",
    )
    commands.append(pytest_run)
    assert pytest_run["exit_code"] == 0

    measurement_output = result / "receipts" / "adversarial_100k.json"
    measurement_run = run_command(
        [sys.executable, "scripts/measure_tl2_bounded_graph.py", "--output", str(measurement_output)],
        worktree,
        result / "raw" / "adversarial_100k.stdout.log",
        result / "raw" / "adversarial_100k.stderr.log",
    )
    commands.append(measurement_run)
    assert measurement_run["exit_code"] == 0
    measurement = json.loads(measurement_output.read_text(encoding="utf-8"))
    assert measurement["corpus"]["atom_count"] == 100_000
    after = measurement["after_bounded_projection"]
    telemetry = after["telemetry"]
    assert after["build_limit_error"] is None
    assert after["deterministic_soft_projection"] is True
    assert telemetry["max_soft_degree"] <= 50
    assert telemetry["skipped_high_df_terms"] > 0
    assert telemetry["degree_cap_drops"] > 0
    assert measurement["query_receipts"]["overflow"]["receipt"]["status"] == "bounded_incomplete"
    assert "Synthetic adversarial budget evidence only" in measurement["claim_boundary"]

    write_json(result / "commands.json", commands)
    write_json(
        result / "result_manifest.json",
        {
            "gate": "V1b-TL-graph",
            "outcome": "needs_review",
            "candidate": lease["candidate"],
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "claim_boundary": "Local installed graph behavior and synthetic adversarial engineering bounds only; no retrieval-quality, public-data, scale-certification, SOTA, or promotion claim.",
        },
    )
    manifest: dict[str, str] = {}
    for path in sorted(result.rglob("*")):
        if path.is_file() and path.name != "evidence_manifest.json":
            manifest[path.relative_to(result).as_posix()] = sha256(path)
    write_json(result / "evidence_manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
