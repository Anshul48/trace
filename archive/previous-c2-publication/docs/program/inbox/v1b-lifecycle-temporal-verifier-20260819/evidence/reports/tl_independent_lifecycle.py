"""Independent S5 V1b-TL lifecycle checks.

This file is packet evidence, not a product test.  It imports the verifier
worktree through PYTHONPATH, uses only injected deterministic local adapters,
and writes no state outside the caller-provided scratch root.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

from trace_lite import TraceLite
from trace_lite.adapters import MockEmbedder, MockLLMAdapter
from trace_lite.cortex import MockVectorStore, Tree, TreeNode
from trace_lite.db import IndexValidationError, QueryBlockedError
from trace_lite.engines.raptor import RaptorBuild


SCRATCH = Path(os.environ["S5_SCRATCH"])
SCRATCH.mkdir(parents=True, exist_ok=True)


def make_db(root: Path) -> TraceLite:
    return TraceLite(
        root,
        embedder=MockEmbedder(dim=16),
        llm=MockLLMAdapter(),
        vector_store=MockVectorStore(),
    )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def source_fingerprint(db: TraceLite) -> str:
    rows = []
    for atom in db.spine.list_atoms():
        rows.append(
            {
                "atom_id": atom.atom_id,
                "content": atom.content,
                "content_hash": getattr(atom, "content_hash", None),
            }
        )
    return digest(sorted(rows, key=lambda row: row["atom_id"]))


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
    except Exception as exc:  # receipt must preserve unexpected failures
        return {
            "case": name,
            "status": "fail",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": {"type": type(exc).__name__, "detail": str(exc)[:500]},
        }


def case_candidate_visibility():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Durable paragraph A on memory safety.", document_name="doc_a")
        active = db.reindex_all()
        candidate_id = "build-candidate-staged"
        db.ingest("Durable paragraph B on distributed consensus.", document_name="doc_b")
        db.forest.create_index_build(
            {
                "build_id": candidate_id,
                "source_atom_count": 2,
                "state": "building",
                "supersedes_build_id": active.build_id,
            }
        )
        tree = Tree("tree-cand", "Candidate Tree", "candidate", "node-cand", 1, 1)
        node = TreeNode("node-cand", "tree-cand", 0, "leaf", ["atom-b"], None)
        db.forest.store_candidate_trees_and_nodes(candidate_id, [tree], [node])
        normal_tree_ids = [item.tree_id for item in db.trees()]
        normal_node = db.forest.get_node("node-cand")
        explicit_node = db.forest.get_node("node-cand", build_id=candidate_id)
        manifest = db.index_manifest()
        assert normal_node is None
        assert explicit_node is not None
        assert "tree-cand" not in normal_tree_ids
        assert manifest["build_id"] == active.build_id
        return {
            "active_build_id": active.build_id,
            "candidate_build_id": candidate_id,
            "normal_tree_ids": normal_tree_ids,
            "normal_candidate_node": normal_node,
            "explicit_candidate_node": explicit_node.node_id,
            "source_hash": source_fingerprint(db),
        }


def case_validation_failure_retains_active():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Paragraph 1 on compiler architecture.", document_name="compiler")
        first = db.reindex_all()
        db.ingest("Paragraph 2 on optimization passes.", document_name="opt")
        original = db.raptor.build_tree

        def faulty_build_tree(*args, **kwargs):
            result = original(*args, **kwargs)
            candidate = db.raptor.last_build
            if candidate and candidate.nodes:
                corrupted = [
                    TreeNode(
                        node_id=node.node_id,
                        tree_id=node.tree_id,
                        level=node.level,
                        node_type=node.node_type,
                        atom_ids=["nonexistent-atom-xyz"],
                        summary_text=node.summary_text,
                        parent_id=node.parent_id,
                        children_ids=node.children_ids,
                    )
                    for node in candidate.nodes
                ]
                db.raptor.last_build = RaptorBuild(
                    tree=candidate.tree, nodes=corrupted, vectors=candidate.vectors
                )
            return result

        db.raptor.build_tree = faulty_build_tree
        try:
            db.reindex_all()
        except IndexValidationError as exc:
            expected_error = str(exc)[:300]
        else:
            raise AssertionError("corrupt candidate activated")
        latest = db.forest.get_latest_index_build()
        assert db.forest.get_active_build_id() == first.build_id
        assert latest["state"] == "failed"
        return {
            "active_build_id": first.build_id,
            "failed_candidate_id": latest["build_id"],
            "failure_receipt": expected_error,
            "active_manifest": db.index_manifest()["build_id"],
            "source_hash": source_fingerprint(db),
        }


def case_crash_before_candidate_writes():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Initial durable atom.", document_name="init")
        first = db.reindex_all()
        db.ingest("Second durable atom.", document_name="second")
        original = db.forest.store_edges

        def crash(*args, **kwargs):
            raise KeyboardInterrupt("independent simulated power loss before graph write")

        db.forest.store_edges = crash
        try:
            db.reindex_all()
        except KeyboardInterrupt as exc:
            expected_error = str(exc)
        else:
            raise AssertionError("interrupted build did not surface")
        db.forest.store_edges = original
        assert db.forest.get_active_build_id() == first.build_id
        assert db.index_manifest()["build_id"] == first.build_id
        return {
            "fault_point": "before_candidate_graph_write",
            "active_build_id": first.build_id,
            "exception": expected_error,
            "latest_build": db.forest.get_latest_index_build(),
            "validation_trusted": db.validate_index()["trusted"],
        }


def case_crash_after_partial_hierarchy():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Initial durable atom.", document_name="init")
        first = db.reindex_all()
        db.ingest("Second durable atom.", document_name="second")
        original = db.forest.store_candidate_trees_and_nodes
        holder = {}

        def partial(*args, **kwargs):
            holder["candidate_id"] = args[0]
            result = original(*args, **kwargs)
            raise KeyboardInterrupt("independent simulated power loss after hierarchy writes")

        db.forest.store_candidate_trees_and_nodes = partial
        try:
            db.reindex_all()
        except KeyboardInterrupt as exc:
            expected_error = str(exc)
        else:
            raise AssertionError("partial hierarchy interruption did not surface")
        db.forest.store_candidate_trees_and_nodes = original
        candidate_id = holder["candidate_id"]
        candidate_nodes = db.forest.get_tree_nodes(
            db.forest.list_trees(build_id=candidate_id)[0].tree_id,
            build_id=candidate_id,
        )
        assert db.forest.get_active_build_id() == first.build_id
        assert candidate_nodes
        return {
            "fault_point": "after_candidate_hierarchy_writes",
            "active_build_id": first.build_id,
            "candidate_build_id": candidate_id,
            "candidate_node_count": len(candidate_nodes),
            "exception": expected_error,
            "normal_tree_ids": [tree.tree_id for tree in db.trees()],
        }


def case_crash_after_partial_graph():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Initial durable atom.", document_name="init")
        first = db.reindex_all()
        db.ingest("Second durable atom.", document_name="second")
        original = db.forest.store_edges
        holder = {}

        def partial(edges, *args, **kwargs):
            holder["candidate_id"] = kwargs.get("build_id")
            result = original(edges, *args, **kwargs)
            raise KeyboardInterrupt("independent simulated power loss after graph writes")

        db.forest.store_edges = partial
        try:
            db.reindex_all()
        except KeyboardInterrupt as exc:
            expected_error = str(exc)
        else:
            raise AssertionError("partial graph interruption did not surface")
        db.forest.store_edges = original
        candidate_id = holder["candidate_id"]
        assert db.forest.get_active_build_id() == first.build_id
        assert db.forest.get_all_edges() == db.forest.get_all_edges(build_id=first.build_id)
        return {
            "fault_point": "after_candidate_graph_writes",
            "active_build_id": first.build_id,
            "candidate_build_id": candidate_id,
            "candidate_edge_count": len(db.forest.get_all_edges(build_id=candidate_id)),
            "active_edge_count": len(db.forest.get_all_edges()),
            "exception": expected_error,
        }


def case_pointer_rollback():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Alpha document content.", document_name="doc_alpha")
        first = db.reindex_all()
        first_tree_ids = {tree.tree_id for tree in db.trees()}
        db.ingest("Beta document content.", document_name="doc_beta")
        second = db.reindex_all()
        second_tree_ids = {tree.tree_id for tree in db.trees()}
        assert db.index_manifest()["build_id"] == second.build_id
        predecessor = db.forest.get_index_build(first.build_id)
        assert predecessor["state"] == "retained"
        rollback = db.rollback()
        assert rollback["active_build_id"] == first.build_id
        assert {tree.tree_id for tree in db.trees()} == first_tree_ids
        assert second_tree_ids != first_tree_ids
        assert db.validate_index()["active_build_id"] == first.build_id
        return {
            "predecessor_build_id": first.build_id,
            "successor_build_id": second.build_id,
            "rollback": rollback,
            "active_read_build_id": db.validate_index()["active_build_id"],
            "predecessor_tree_ids": sorted(first_tree_ids),
            "successor_tree_ids": sorted(second_tree_ids),
        }


def case_stale_graph_and_vector_isolation():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("First graph source atom.\n\nFirst graph second atom.", document_name="g1")
        first = db.reindex_all()
        first_edges = db.forest.get_all_edges()
        db.ingest("Second graph source atom.\n\nSecond graph different linkage.", document_name="g2")
        second = db.reindex_all()
        active_edges = db.forest.get_all_edges()
        old_edges = db.forest.get_all_edges(build_id=first.build_id)
        candidate = db.vector_store.begin_build("candidate-vector")
        candidate.upsert("candidate-node", np.ones(16, dtype=np.float32), {"tree_id": "candidate"})
        active_vector_ids = [row.node_id for row in db.vector_store.search(np.ones(16, dtype=np.float32))]
        assert db.forest.get_active_build_id() == second.build_id
        assert len(old_edges) == len(first_edges)
        assert "candidate-node" not in active_vector_ids
        return {
            "first_build_id": first.build_id,
            "active_build_id": second.build_id,
            "active_edge_count": len(active_edges),
            "retained_edge_count": len(old_edges),
            "active_vector_ids": active_vector_ids,
            "candidate_vector_visible": "candidate-node" in active_vector_ids,
        }


def case_orphan_validation():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Legitimate atom.", document_name="legit")
        db.reindex_all()
        trees = db.forest.list_trees()
        orphan = TreeNode("orphan-leaf", trees[0].tree_id, 0, "leaf", [], None)
        nodes = db.forest.get_tree_nodes(trees[0].tree_id) + [orphan]
        validation = db._validate_candidate(
            trees,
            nodes,
            list(db.vector_store.iter_vectors()),
            source_atom_ids={atom.atom_id for atom in db.spine.list_atoms()},
            expected_dimension=16,
        )
        assert validation["healthy"] is False
        return {"healthy": validation["healthy"], "errors": validation["errors"]}


def case_replay_idempotency():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Durable invariant sentence one.\n\nDurable invariant sentence two.", document_name="replay")
        db.reindex_all()
        first_atoms = sorted(atom.atom_id for atom in db.spine.list_atoms())
        first_hash = source_fingerprint(db)
        organized = db.organize()
        db.reindex_all()
        second_atoms = sorted(atom.atom_id for atom in db.spine.list_atoms())
        assert organized.trees_updated == 0
        assert first_atoms == second_atoms
        assert first_hash == source_fingerprint(db)
        assert db.validate_index()["trusted"] is True
        return {"atom_ids": first_atoms, "source_hash": first_hash, "organize_trees_updated": organized.trees_updated}


def case_source_arrival_during_build():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        db = make_db(Path(raw) / "db")
        db.ingest("Initial source atom.", document_name="initial")
        first = db.reindex_all()
        original = db.forest.store_candidate_trees_and_nodes
        arrived = {"done": False}

        def stage_then_arrive(*args, **kwargs):
            if not arrived["done"]:
                arrived["done"] = True
                db.ingest("Source arrival during active build.", document_name="during-build")
            return original(*args, **kwargs)

        db.forest.store_candidate_trees_and_nodes = stage_then_arrive
        result = db.reindex_all()
        db.forest.store_candidate_trees_and_nodes = original
        assert result.state == "active"
        assert db.forest.get_active_build_id() == result.build_id
        assert db.forest.has_pending_source_atoms() is True
        try:
            db.query("initial source", force=False)
        except QueryBlockedError as exc:
            query_error = str(exc)
        else:
            raise AssertionError("ordinary query exposed source arriving during build")
        return {
            "predecessor_build_id": first.build_id,
            "active_build_id": result.build_id,
            "pending_source_atoms": sorted(db.forest.get_pending_source_atom_ids()),
            "normal_query_blocked_by_pending": True,
            "query_error": query_error,
        }


def case_incremental_full_parity():
    with tempfile.TemporaryDirectory(dir=SCRATCH) as raw:
        root = Path(raw)
        inc = make_db(root / "incremental")
        full = make_db(root / "full")
        text1 = "Alpha topic analysis and structural indexing."
        text2 = "Beta topic categorization and retrieval mechanics."
        inc.ingest(text1, document_name="doc1")
        inc.reindex_all()
        inc.ingest(text2, document_name="doc2")
        inc.organize()
        full.ingest(text1, document_name="doc1")
        full.ingest(text2, document_name="doc2")
        full.reindex_all()
        inc_contents = sorted(atom.content for atom in inc.spine.list_atoms())
        full_contents = sorted(atom.content for atom in full.spine.list_atoms())
        assert inc_contents == full_contents
        assert inc.validate_index()["trusted"] is True
        assert full.validate_index()["trusted"] is True
        return {
            "incremental_source_hash": source_fingerprint(inc),
            "full_source_hash": source_fingerprint(full),
            "incremental_indexed_atoms": len(inc.forest.get_indexed_atom_ids()),
            "full_indexed_atoms": len(full.forest.get_indexed_atom_ids()),
        }


CASES = [
    ("candidate_visibility", case_candidate_visibility),
    ("validation_failure_retains_active", case_validation_failure_retains_active),
    ("crash_before_candidate_writes", case_crash_before_candidate_writes),
    ("crash_after_partial_hierarchy", case_crash_after_partial_hierarchy),
    ("crash_after_partial_graph", case_crash_after_partial_graph),
    ("pointer_rollback", case_pointer_rollback),
    ("stale_graph_and_vector_isolation", case_stale_graph_and_vector_isolation),
    ("orphan_validation", case_orphan_validation),
    ("replay_idempotency", case_replay_idempotency),
    ("source_arrival_during_build", case_source_arrival_during_build),
    ("incremental_full_parity", case_incremental_full_parity),
]


if __name__ == "__main__":
    receipt = {
        "verifier_id": "v1b-tl-lifecycle-verifier-20260819",
        "base_commit": "7ff40dc46fe3d5e8eef31c485ed0337b8f71602d",
        "claim_level": "C1",
        "backend": "Trace-Lite SQLite + MockVectorStore + injected deterministic Mock adapters",
        "cases": [run_case(name, fn) for name, fn in CASES],
    }
    receipt["summary"] = {
        "passed": sum(case["status"] == "pass" for case in receipt["cases"]),
        "failed": sum(case["status"] == "fail" for case in receipt["cases"]),
        "total": len(receipt["cases"]),
    }
    serialized = json.dumps(receipt, sort_keys=True, indent=2, default=str)
    receipt_path = os.environ.get("S5_RECEIPT")
    if receipt_path:
        Path(receipt_path).write_text(serialized + "\n", encoding="utf-8")
        print(json.dumps({"summary": receipt["summary"], "receipt_path": receipt_path}, indent=2))
    else:
        print(serialized)
