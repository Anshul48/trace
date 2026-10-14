"""Independent low-level graph evidence for the final V1b graph sub-gate.

The full Trace-Lite runtime is intentionally not replaced when its locked
dependencies are unavailable. This script exercises only the standard-library
graph/ForestIndex portions from the exact verifier checkout and records the
full-subgate dependency blocker separately.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import tracemalloc
import types
from pathlib import Path
from types import SimpleNamespace


WORKTREE = Path(os.environ["S5_GRAPH_WORKTREE"])
SCRATCH = Path(os.environ["S5_GRAPH_SCRATCH"])
RESULT_ROOT = Path(os.environ["S5_GRAPH_RESULT_ROOT"])
RECEIPT_PATH = Path(os.environ["S5_GRAPH_RECEIPT"])
SCRATCH.mkdir(parents=True, exist_ok=True)
RESULT_ROOT.mkdir(parents=True, exist_ok=True)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load target module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


graph = load_module("v1b_target_graph", WORKTREE / "src/trace_lite/engines/graph.py")
trace_pkg = types.ModuleType("trace_lite")
trace_pkg.__path__ = [str(WORKTREE / "src/trace_lite")]
cortex_pkg = types.ModuleType("trace_lite.cortex")
cortex_pkg.__path__ = [str(WORKTREE / "src/trace_lite/cortex")]
sys.modules.setdefault("trace_lite", trace_pkg)
sys.modules.setdefault("trace_lite.cortex", cortex_pkg)
load_module("trace_lite.cortex.manifest", WORKTREE / "src/trace_lite/cortex/manifest.py")
forest = load_module("trace_lite.cortex.forest", WORKTREE / "src/trace_lite/cortex/forest.py")


def atom(atom_id: str, content: str, artifact: str = "artifact-0", sequence: int = 0):
    return SimpleNamespace(
        atom_id=atom_id,
        content=content,
        source_artifact_id=artifact,
        sequence_index=sequence,
    )


def stable_edges(edges: list[dict]) -> list[tuple]:
    return sorted(
        (
            item["source_atom_id"],
            item["target_atom_id"],
            item["relation_type"],
            round(float(item["weight"]), 12),
            tuple(item.get("witness_terms", [])),
            item.get("provenance"),
            item.get("channel"),
        )
        for item in edges
    )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def run_case(name: str, fn):
    started = time.perf_counter()
    try:
        observation = fn()
        return {
            "case": name,
            "status": "pass",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "observation": observation,
        }
    except Exception as exc:  # preserve unexpected verifier failures
        return {
            "case": name,
            "status": "fail",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": {"type": type(exc).__name__, "detail": str(exc)[:1000]},
        }


def case_policy_identity_and_immutability():
    policy = graph.DEFAULT_GRAPH_POLICY
    assert policy.high_df_absolute_cutoff == 100
    assert policy.high_df_ratio_cutoff == 0.10
    assert policy.max_candidate_partners_per_atom_term == 50
    assert policy.max_soft_affinity_degree == 50
    assert policy.max_structural_edges_per_node == 32
    assert policy.ppr_alpha == 0.85
    assert policy.ppr_max_iterations == 20
    assert policy.ppr_epsilon == 1e-4
    assert policy.ppr_max_depth == 4
    assert policy.ppr_max_activated_nodes == 512
    assert policy.ppr_max_traversed_edges == 2500
    assert policy.ppr_top_k == 100
    assert policy.query_wall_time_ms == 35.0
    assert policy.query_memory_bytes == 64 * 1024 * 1024
    assert policy.build_rss_bytes == 512 * 1024 * 1024
    assert policy.projection_storage_bytes == 256 * 1024 * 1024
    atoms = [atom("a", "alpha beta", sequence=0), atom("b", "alpha beta", sequence=1)]
    try:
        graph.generate_co_occurrence_edges(atoms, max_atom_frequency_ratio=0.4)
    except ValueError as exc:
        assert "no longer tunable" in str(exc)
    else:
        raise AssertionError("legacy tunable cutoff was accepted")
    try:
        graph.generate_co_occurrence_edges(
            atoms, policy=graph.GraphPolicy(max_soft_affinity_degree=49)
        )
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("alternate graph policy was accepted")
    return {"policy_hash": graph.GRAPH_POLICY_CONFIG_HASH}


def case_high_df_filter_and_boundary():
    atoms = []
    for index in range(100):
        terms = []
        if index < 10:
            terms.append("boundaryterm")
        if index < 11:
            terms.append("highterm")
        if index < 2:
            terms.append("pairterm")
        terms.append(f"unique-{index:03d}")
        atoms.append(atom(f"atom-{index:03d}", " ".join(terms), sequence=index))
    telemetry: dict = {}
    edges = graph.generate_co_occurrence_edges(atoms, telemetry=telemetry)
    witnesses = {term for edge in edges for term in edge["witness_terms"]}
    assert telemetry["high_df_cutoff"] == 10.0
    assert telemetry["skipped_high_df_terms"] >= 1
    assert "highterm" not in witnesses
    assert "boundaryterm" in witnesses
    assert "pairterm" in witnesses
    return {
        "atom_count": len(atoms),
        "cutoff": telemetry["high_df_cutoff"],
        "skipped_high_df_terms": telemetry["skipped_high_df_terms"],
        "edge_count": len(edges),
        "witness_terms": sorted(witnesses),
    }


def case_dedup_and_witness_provenance():
    atoms = [atom(f"atom-{index:02d}", "rareone raretwo" if index < 2 else f"unique-{index}") for index in range(20)]
    telemetry: dict = {}
    edges = graph.generate_co_occurrence_edges(atoms, telemetry=telemetry)
    assert len(edges) == 2
    assert telemetry["duplicate_pairs_dropped"] >= 1
    assert all(edge["witness_terms"] == ["rareone", "raretwo"] for edge in edges)
    assert all(edge["provenance"] == "spine:term-co-occurrence" for edge in edges)
    assert all(edge["channel"] == "soft_affinity" for edge in edges)
    return {
        "edge_count": len(edges),
        "duplicate_pairs_dropped": telemetry["duplicate_pairs_dropped"],
        "edges_digest": digest(stable_edges(edges)),
    }


def case_partner_and_degree_caps():
    atoms = [
        atom(
            f"atom-{index:04d}",
            "boundedcluster" if index < 52 else f"unique-{index:04d}",
            sequence=index,
        )
        for index in range(600)
    ]
    first_telemetry: dict = {}
    second_telemetry: dict = {}
    first = graph.generate_co_occurrence_edges(atoms, telemetry=first_telemetry)
    second = graph.generate_co_occurrence_edges(atoms, telemetry=second_telemetry)
    degree: dict[str, int] = {}
    for edge in first:
        degree[edge["source_atom_id"]] = degree.get(edge["source_atom_id"], 0) + 1
    assert first_telemetry["candidate_partner_cap_hits"] > 0
    assert first_telemetry["degree_cap_drops"] > 0
    assert first_telemetry["max_soft_degree"] <= 50
    assert max(degree.values(), default=0) <= 50
    assert stable_edges(first) == stable_edges(second)
    assert first_telemetry["soft_affinity_edges_admitted"] == len(first)
    return {
        "edge_count": len(first),
        "candidate_partner_cap_hits": first_telemetry["candidate_partner_cap_hits"],
        "degree_cap_drops": first_telemetry["degree_cap_drops"],
        "max_soft_degree": first_telemetry["max_soft_degree"],
        "edges_digest": digest(stable_edges(first)),
    }


def case_adversarial_100k_high_df():
    atoms = [
        atom(
            f"atom-{index:06d}",
            "boilerplate boundedgroup" if index < 100 else "boilerplate",
            sequence=index,
        )
        for index in range(100_000)
    ]
    before_rss = graph.current_process_rss_bytes()
    telemetry: dict = {}
    started = time.perf_counter()
    edges = graph.generate_co_occurrence_edges(atoms, telemetry=telemetry)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    after_rss = graph.current_process_rss_bytes()
    witnesses = {term for edge in edges for term in edge["witness_terms"]}
    assert telemetry["atom_count"] == 100_000
    assert telemetry["skipped_high_df_terms"] >= 1
    assert "boilerplate" not in witnesses
    assert telemetry["max_soft_degree"] <= 50
    assert len(edges) <= 5_100
    return {
        "atom_count": 100_000,
        "elapsed_ms": elapsed_ms,
        "rss_before_bytes": before_rss,
        "rss_after_bytes": after_rss,
        "rss_delta_bytes": (max(0, after_rss - before_rss) if before_rss is not None and after_rss is not None else None),
        "theoretical_unbounded_pair_candidates": 4_999_954_950,
        "edge_count": len(edges),
        "skipped_high_df_terms": telemetry["skipped_high_df_terms"],
        "candidate_partner_cap_hits": telemetry["candidate_partner_cap_hits"],
        "degree_cap_drops": telemetry["degree_cap_drops"],
        "max_soft_degree": telemetry["max_soft_degree"],
        "witness_terms": sorted(witnesses),
        "telemetry_digest": digest(telemetry),
    }


def case_ppr_core_determinism():
    adjacency = {
        "seed": [("b", 1.0), ("a", 0.5)],
        "a": [("seed", 1.0)],
        "b": [("seed", 1.0)],
    }
    first_telemetry: dict = {}
    second_telemetry: dict = {}
    engine = graph.GraphActivationEngine()
    first = engine.personalized_pagerank({"seed": 1.0}, adjacency, telemetry=first_telemetry)
    second = engine.personalized_pagerank({"seed": 1.0}, adjacency, telemetry=second_telemetry)
    assert first == second
    assert first_telemetry == second_telemetry
    assert first_telemetry["ppr_iterations"] <= graph.DEFAULT_GRAPH_POLICY.ppr_max_iterations
    return {"scores": first, "telemetry": first_telemetry}


def case_build_overflow_receipt():
    receipt = {
        "rss_baseline_bytes": 0,
        "projection_storage_bytes": graph.DEFAULT_GRAPH_POLICY.projection_storage_bytes + 1,
    }
    try:
        graph.enforce_graph_build_limits(receipt)
    except graph.GraphBuildBudgetExceeded as exc:
        assert "projection_storage_bytes" in exc.receipt["build_limit_breaches"]
        assert exc.receipt["build_within_limits"] is False
        return {"breaches": exc.receipt["build_limit_breaches"], "receipt": exc.receipt}
    raise AssertionError("projection overflow did not fail closed")


def case_candidate_graph_identity_scoping():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db_path = Path(raw) / "cortex.sqlite3"
        index = forest.ForestIndex(db_path)
        index.create_index_build({"build_id": "active", "state": "building"})
        active_edge = {
            "edge_id": "active-edge",
            "source_atom_id": "active-a",
            "target_atom_id": "active-b",
            "relation_type": "NEXT",
            "weight": 1.0,
            "confidence": 1.0,
            "provenance": "spine:artifact-sequence",
            "channel": "structural",
        }
        index.activate_index_build("active", graph_edges=[active_edge])
        index.create_index_build({"build_id": "candidate", "state": "building"})
        candidate_edge = {**active_edge, "edge_id": "candidate-edge", "source_atom_id": "candidate-a", "target_atom_id": "candidate-b"}
        index.store_edges([candidate_edge], build_id="candidate")
        ordinary = {edge["edge_id"] for edge in index.get_all_edges()}
        candidate = {edge["edge_id"] for edge in index.get_all_edges(build_id="candidate")}
        assert ordinary == {"active-edge"}
        assert candidate == {"candidate-edge"}
        return {"ordinary_edges": sorted(ordinary), "candidate_edges": sorted(candidate), "db_bytes": index.projection_storage_bytes()}


CASES = [
    ("policy_identity_and_immutability", case_policy_identity_and_immutability),
    ("high_df_filter_and_boundary", case_high_df_filter_and_boundary),
    ("dedup_and_witness_provenance", case_dedup_and_witness_provenance),
    ("partner_and_degree_caps", case_partner_and_degree_caps),
    ("adversarial_100k_high_df", case_adversarial_100k_high_df),
    ("ppr_core_determinism", case_ppr_core_determinism),
    ("build_overflow_receipt", case_build_overflow_receipt),
    ("candidate_graph_identity_scoping", case_candidate_graph_identity_scoping),
]


def module_probe() -> dict:
    import importlib.util

    result = {}
    for name in ("pytest", "numpy", "lancedb"):
        result[name] = bool(importlib.util.find_spec(name))
    try:
        import trace_lite  # noqa: F401
    except Exception as exc:
        result["trace_lite_import"] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}"}
    else:
        result["trace_lite_import"] = {"status": "pass"}
    return result


if __name__ == "__main__":
    environment = module_probe()
    cases = [run_case(name, fn) for name, fn in CASES]
    required_blockers = []
    if not environment["numpy"]:
        required_blockers.append("fresh graph environment lacks numpy; full Trace-Lite/Lattice import unavailable")
    if not environment["lancedb"]:
        required_blockers.append("fresh graph environment lacks lancedb; persistent vector backend unavailable")
    if not environment["pytest"]:
        required_blockers.append("fresh graph environment lacks pytest; implementation test matrix not executable")
    receipt = {
        "verifier_id": "v1b-final-graph-verifier-20260823",
        "sub_gate": "V1b-TL-graph",
        "base_commit": "3e7e9f0ee460e3af75f3935343f6d6f2089f9f7c",
        "claim_level": "C1-low-level-partial",
        "backend": "Exact TL2 graph.py and ForestIndex modules loaded from fresh verifier checkout; no host package fallback",
        "environment": environment,
        "cases": cases,
        "required_full_subgate_blockers": required_blockers,
        "summary": {
            "low_level_passed": sum(case["status"] == "pass" for case in cases),
            "low_level_failed": sum(case["status"] == "fail" for case in cases),
            "low_level_total": len(cases),
            "required_blocked": len(required_blockers),
            "full_subgate_status": "blocked" if required_blockers else "pass",
        },
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"summary": receipt["summary"], "receipt": str(RECEIPT_PATH)}, indent=2))
