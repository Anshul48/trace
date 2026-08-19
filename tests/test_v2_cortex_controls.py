from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError

from trace.v2.cortex import ActivationEdge, ActivationEngine
from trace.v2.models import (
    BenchmarkRunRequest,
    CognitivePolicy,
    DeepNavigationPlan,
    IngestionRequest,
    NodeEditRequest,
    ProjectionRebuildRequest,
)
from trace.v2.retrieval import HybridRetrievalEngine
from trace.v2.service import TraceService
from trace.v2.store import InvariantViolation, SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str, **_: object) -> dict[str, object]:
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "object_key": "test/source",
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {"storage": "test"},
        }

    def put_text(self, text: str, media_type: str, **kwargs: object) -> dict[str, object]:
        return self.put_bytes(text.encode("utf-8"), media_type, **kwargs)


class RecordingLexicalIndex:
    provider_id = "recording-lexical"

    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    def upsert(self, documents, *, revision: str) -> int:  # type: ignore[no-untyped-def]
        rows = list(documents)
        self.upserts.extend(rows)
        return len(rows)

    def search(self, **_: object) -> list[dict[str, object]]:
        return []


class RecordingDenseIndex:
    provider_id = "recording-dense"

    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    def upsert(self, vectors, *, revision: str) -> int:  # type: ignore[no-untyped-def]
        rows = list(vectors)
        self.upserts.extend(rows)
        return len(rows)

    def search(self, **_: object) -> list[dict[str, object]]:
        return []


class CortexControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SqliteEventStore(":memory:")
        self.lexical = RecordingLexicalIndex()
        self.dense = RecordingDenseIndex()
        self.service = TraceService(
            self.store,
            MemoryObjectStore(),
            retrieval_engine=HybridRetrievalEngine(lexical_index=self.lexical, dense_index=self.dense),
        )

    def tearDown(self) -> None:
        self.store.close()

    def _ingest(self, text: str) -> tuple[dict, list[dict]]:
        ingestion = self.service.ingest(IngestionRequest(workspace_id="alpha", text=text))
        return ingestion, self.store.ingestion_atoms(ingestion["ingestion_id"])

    def test_edit_invalidates_affinity_and_queues_only_changed_version(self) -> None:
        ingestion, atoms = self._ingest("alpha bridge source\n\nalpha bridge target\n\nseparate evidence")
        edge = self.store.put_affinity_edge(
            workspace_id="alpha",
            source_atom_version_id=atoms[0]["atom_version_id"],
            target_atom_version_id=atoms[1]["atom_version_id"],
            score=0.7,
            signal={"provider": "test"},
            expires_at="2999-01-01T00:00:00+00:00",
        )
        self.assertIsNotNone(edge)
        with patch.object(self.service, "rebuild_dense_index", side_effect=AssertionError("workspace rebuild is forbidden")):
            updated = self.service.edit_node(
                atoms[0]["node_id"],
                NodeEditRequest(content="alpha bridge revised", idempotency_key="edit-delta"),
            )
            completed = self.service.jobs.execute(updated["index_job"]["job_id"])
        self.assertEqual(completed["status"], "succeeded")
        payload = completed["payload"]
        self.assertEqual(payload["atom_version_ids"], [updated["atom_version_id"]])
        self.assertEqual(self.store.affinity_neighbors("alpha", [atoms[1]["atom_version_id"]]), [])
        self.assertEqual(self.store.ingestion_index_state(ingestion["ingestion_id"])["lexical"]["status"], "lexical_ready")
        self.assertTrue(any(row["atom_version_id"] == updated["atom_version_id"] for row in self.lexical.upserts))
        self.assertTrue(any(row["atom_version_id"] == updated["atom_version_id"] for row in self.dense.upserts))

    def test_affinity_rejection_and_per_endpoint_degree_cap_are_enforced(self) -> None:
        _, atoms = self._ingest("common alpha one\n\ncommon alpha two\n\ncommon alpha three")
        first = self.store.put_affinity_edge(
            workspace_id="alpha", source_atom_version_id=atoms[0]["atom_version_id"],
            target_atom_version_id=atoms[1]["atom_version_id"], score=0.8, signal={},
            expires_at="2999-01-01T00:00:00+00:00", degree_cap=1,
        )
        self.assertIsNotNone(first)
        capped = self.store.put_affinity_edge(
            workspace_id="alpha", source_atom_version_id=atoms[0]["atom_version_id"],
            target_atom_version_id=atoms[2]["atom_version_id"], score=0.8, signal={},
            expires_at="2999-01-01T00:00:00+00:00", degree_cap=1,
        )
        self.assertIsNone(capped)
        self.store.reject_affinity(
            workspace_id="alpha", source_atom_version_id=atoms[0]["atom_version_id"],
            target_atom_version_id=atoms[1]["atom_version_id"], reason="not useful",
        )
        rejected = self.store.put_affinity_edge(
            workspace_id="alpha", source_atom_version_id=atoms[0]["atom_version_id"],
            target_atom_version_id=atoms[1]["atom_version_id"], score=0.9, signal={},
            expires_at="2999-01-01T00:00:00+00:00",
        )
        self.assertIsNone(rejected)

    def test_cortex_reset_preserves_canonical_spine(self) -> None:
        _, atoms = self._ingest("source one\n\nsource two\n\nsource three\n\nsource four")
        before = {
            "atoms": [(atom["atom_version_id"], atom["content_hash"]) for atom in self.store.queryable_atoms("alpha")],
            "edges": [(edge["edge_version_id"], edge["relation_type"]) for edge in self.store.current_edges("alpha")],
        }
        rebuilt = self.service.rebuild_projection(ProjectionRebuildRequest(
            workspace_id="alpha", projection_kind="hierarchy", atom_version_ids=[atom["atom_version_id"] for atom in atoms],
        ))
        self.assertEqual(rebuilt["status"], "active")
        cleared = self.store.clear_cortex_projections("alpha")
        self.assertGreater(cleared["runs"], 0)
        after = {
            "atoms": [(atom["atom_version_id"], atom["content_hash"]) for atom in self.store.queryable_atoms("alpha")],
            "edges": [(edge["edge_version_id"], edge["relation_type"]) for edge in self.store.current_edges("alpha")],
        }
        self.assertEqual(before, after)

    def test_hierarchy_delta_carries_forward_the_active_snapshot(self) -> None:
        _, atoms = self._ingest("\n\n".join(f"source {index}" for index in range(10)))
        first = self.service.rebuild_projection(ProjectionRebuildRequest(
            workspace_id="alpha", projection_kind="hierarchy",
            atom_version_ids=[atom["atom_version_id"] for atom in atoms],
        ))
        initial_run = self.store.effective_projection_run("alpha", "hierarchy")
        self.assertIsNotNone(initial_run)
        initial_sources = {
            source_id
            for row in self.store.projection_objects(first["projection_run_id"])
            if row["object_kind"] == "source_section"
            for source_id in row["source_atom_version_ids"]
        }
        updated = self.service.edit_node(
            atoms[1]["node_id"], NodeEditRequest(content="source two revised", idempotency_key="hierarchy-delta"),
        )
        second = self.service.rebuild_projection(ProjectionRebuildRequest(
            workspace_id="alpha", projection_kind="hierarchy",
            atom_version_ids=[updated["atom_version_id"]],
        ))
        active = self.store.effective_projection_run("alpha", "hierarchy")
        self.assertEqual(second["status"], "active")
        self.assertIsNotNone(active)
        self.assertEqual(active["prior_projection_run_id"], initial_run["projection_run_id"])
        carried_sources = {
            source_id
            for row in self.store.projection_objects(second["projection_run_id"])
            if row["object_kind"] == "source_section"
            for source_id in row["source_atom_version_ids"]
        }
        self.assertIn(updated["atom_version_id"], carried_sources)
        self.assertNotIn(atoms[1]["atom_version_id"], carried_sources)
        self.assertTrue(initial_sources - {atoms[1]["atom_version_id"]} <= carried_sources)
        self.assertGreater(active["output_statistics"]["carried_forward_section_count"], 0)

    def test_hierarchy_delta_adds_new_ingestion_without_dropping_snapshot(self) -> None:
        _, original_atoms = self._ingest("\n\n".join(f"original {index}" for index in range(10)))
        initial = self.service.rebuild_projection(ProjectionRebuildRequest(
            workspace_id="alpha", projection_kind="hierarchy",
            atom_version_ids=[atom["atom_version_id"] for atom in original_atoms],
        ))
        _, added_atoms = self._ingest("new evidence one\n\nnew evidence two")
        updated = self.service.rebuild_projection(ProjectionRebuildRequest(
            workspace_id="alpha", projection_kind="hierarchy",
            atom_version_ids=[atom["atom_version_id"] for atom in added_atoms],
        ))
        initial_sources = {
            source_id
            for row in self.store.projection_objects(initial["projection_run_id"])
            if row["object_kind"] == "source_section"
            for source_id in row["source_atom_version_ids"]
        }
        updated_sources = {
            source_id
            for row in self.store.projection_objects(updated["projection_run_id"])
            if row["object_kind"] == "source_section"
            for source_id in row["source_atom_version_ids"]
        }
        self.assertTrue(initial_sources <= updated_sources)
        self.assertTrue({atom["atom_version_id"] for atom in added_atoms} <= updated_sources)

    def test_policy_plan_and_activation_are_bounded_and_replayable(self) -> None:
        with self.assertRaises(ValidationError):
            CognitivePolicy(auto_promote_trusted_evidence=True)
        with self.assertRaises(ValueError):
            DeepNavigationPlan(bridge_seed_ids=["outside"]).validated_against({"summary"}, branch_width=1)
        plan = DeepNavigationPlan(
            frontier_ids=["summary"], selected_ids=["summary"], bridge_seed_ids=["atom"], stop_reason="sufficient",
        ).validated_against({"summary"}, allowed_bridge_ids={"atom"}, branch_width=1)
        self.assertEqual(plan.bridge_seed_ids, ["atom"])
        engine = ActivationEngine({"structural": 0.7, "trusted_evidence": 0.3, "affinity": 0.0, "behavioral": 0.0, "iterations": 8})
        edges = [ActivationEdge("a", "b", "structural", edge_id="e1"), ActivationEdge("b", "a", "structural", edge_id="e1")]
        first = engine.activate(seed_scores={"a": 1.0}, edges=edges)
        second = engine.activate(seed_scores={"a": 1.0}, edges=edges)
        self.assertEqual(first.scores, second.scores)
        self.assertLessEqual(sum(first.scores.values()), 1.000001)

    def test_stale_policy_job_fails_closed_before_projection_handover(self) -> None:
        _, atoms = self._ingest("policy controlled source")
        active = self.service.put_cognitive_policy(
            "alpha", CognitivePolicy(policy_revision="policy-2026-08-07"), actor="admin",
        )
        self.assertEqual(active["policy_revision"], "policy-2026-08-07")
        with self.assertRaises(InvariantViolation):
            self.service.rebuild_projection(ProjectionRebuildRequest(
                workspace_id="alpha", projection_kind="hierarchy",
                atom_version_ids=[atoms[0]["atom_version_id"]], policy_revision="policy-before-change",
            ))
        self.assertIsNone(self.store.effective_projection_run("alpha", "hierarchy"))

    def test_attachment_staging_cleanup_is_recoverable_and_workspace_scoped(self) -> None:
        attachment = {
            "content_hash": "a" * 64,
            "object_key": "test/orphan-object",
            "media_type": "text/plain",
            "byte_length": 12,
            "metadata": {"storage": "test"},
        }
        staged = self.store.stage_attachment(workspace_id="alpha", attachment=attachment)
        self.store.fail_attachment_staging(
            staged["staging_id"], workspace_id="alpha", error="simulated canonical failure",
        )
        reconciliation = self.service.reconcile_attachment_staging("alpha")
        self.assertEqual(reconciliation["workspace_id"], "alpha")
        self.assertEqual(reconciliation["committed"], 0)
        self.assertEqual(reconciliation["cleanup_required"][0]["staging_id"], staged["staging_id"])

    def test_benchmark_persists_reproducible_baseline_identity(self) -> None:
        _, atoms = self._ingest("deployment migration is required before rollout")
        benchmark = {
            "name": "identity-test",
            "cases": [{
                "id": "lookup", "kind": "direct_lookup", "query": "migration rollout",
                "gold_atom_version_ids": [atoms[0]["atom_version_id"]],
            }],
        }
        with patch("trace.v2.service.load_benchmark", return_value=benchmark):
            run = self.service.run_benchmark(BenchmarkRunRequest(
                workspace_id="alpha", benchmark_path="identity.json", stages=["lexical"],
            ))
        identity = run["result"]["baseline_identity"]
        self.assertEqual(identity["corpus_atom_count"], 1)
        self.assertEqual(identity["policy_revision"], "cognitive-policy-v1")
        self.assertIn("model_revisions", identity)
        self.assertIn("active_projections", identity)


if __name__ == "__main__":
    unittest.main()
