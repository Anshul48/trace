from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.models import (
    BenchmarkRunRequest,
    EvidenceFeedbackRequest,
    FeedbackEdgeProposalRequest,
    HierarchyBuildRequest,
    IngestionRequest,
    ProposalCreateRequest,
    QueryRequest,
    RetrievalBudget,
    SchemaProposalRequest,
)
from trace.v2.service import TraceService
from trace.v2.store import InvariantViolation, SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str):
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(), "object_key": "test/source",
            "media_type": media_type, "byte_length": len(raw), "metadata": {"storage": "test"},
        }

    def put_text(self, text: str, media_type: str):
        return self.put_bytes(text.encode("utf-8"), media_type)


class TraceV2CognitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())

    def tearDown(self) -> None:
        self.service.store.close()

    def ingest(self, text: str) -> list[dict]:
        result = self.service.ingest(IngestionRequest(workspace_id="alpha", text=text))
        return self.service.store.ingestion_atoms(result["ingestion_id"])

    def test_hierarchy_is_anchored_versioned_and_idempotent(self) -> None:
        atoms = self.ingest("Database writes events.\n\nIndexer stores embeddings.\n\nQueries rerank evidence.\n\nFeedback improves ranking.")
        first = self.service.build_hierarchy(HierarchyBuildRequest(workspace_id="alpha", section_size=2))
        self.assertGreaterEqual(len(first["section_summaries"]), 2)
        section = first["section_summaries"][0]
        self.assertEqual(len(section["evidence_atom_version_ids"]), 2)
        node = self.service.store.get_node(section["node_id"])
        self.assertEqual(node["properties"]["coverage"]["covered_atom_count"], 2)
        self.assertEqual(node["properties"]["evidence_anchor_ids"], section["evidence_anchor_ids"])
        self.assertTrue(any(edge["relation_type"] == "CONTAINS" for edge in self.service.store.current_edges("alpha")))
        second = self.service.build_hierarchy(HierarchyBuildRequest(workspace_id="alpha", section_size=2))
        self.assertTrue(all(item["reused"] for item in second["section_summaries"]))
        hierarchy = self.service.query(QueryRequest(
            workspace_id="alpha", query="rerank evidence", retrieval_profile="hierarchy",
            retrieval_budget=RetrievalBudget(mode="hierarchy", candidate_limit=10),
        ))
        derived = [item for item in hierarchy["results"] if item["candidate_kind"] == "derived"]
        self.assertTrue(derived)
        self.assertTrue(derived[0]["source_atom_version_ids"])
        self.assertIsNone(derived[0]["source_revision"])
        self.assertEqual(derived[0]["source_revisions"], derived[0]["source_atom_version_ids"])
        self.assertTrue(any(item["atom_version_id"] == atoms[2]["atom_version_id"] for item in hierarchy["results"]))

    def test_graph_ppr_uses_typed_evidence_edges(self) -> None:
        atoms = self.ingest("Gateway receives requests.\n\nWorker emits deployment artifacts.")
        proposal = self.service.create_proposal(ProposalCreateRequest(
            workspace_id="alpha", proposal_type="edge", confidence=0.95,
            candidate={"source_node_id": atoms[0]["node_id"], "target_node_id": atoms[1]["node_id"], "relation_type": "depends_on", "weight": 1.0},
            evidence_atom_version_ids=[atoms[0]["atom_version_id"], atoms[1]["atom_version_id"]],
            model_version="reviewed-v1",
        ))
        self.service.promote_proposal(proposal["proposal_id"], actor="reviewer", reason="documented", idempotency_key=None)
        response = self.service.query(QueryRequest(
            workspace_id="alpha", query="Gateway requests", retrieval_profile="graph",
            retrieval_budget=RetrievalBudget(mode="graph", candidate_limit=10),
        ))
        worker = next(item for item in response["results"] if item["atom_version_id"] == atoms[1]["atom_version_id"])
        self.assertGreater(worker["channel_scores"]["graph_ppr"], 0)
        self.assertTrue(any(path["relation_type"] == "depends_on" for path in worker["graph_paths"]))
        with self.assertRaises(InvariantViolation):
            self.service.create_proposal(ProposalCreateRequest(
                workspace_id="alpha", proposal_type="edge", confidence=0.5,
                candidate={"source_node_id": atoms[0]["node_id"], "target_node_id": atoms[1]["node_id"], "relation_type": "semantic"},
                evidence_atom_version_ids=[atoms[0]["atom_version_id"]],
            ))

    def test_feedback_is_persisted_as_a_soft_feature(self) -> None:
        atom = self.ingest("Trace keeps citations precise.")[0]
        response = self.service.query(QueryRequest(workspace_id="alpha", query="citations precise", retrieval_profile="rerank"))
        feedback = self.service.record_feedback(EvidenceFeedbackRequest(
            workspace_id="alpha", evidence_bundle_id=response["evidence_bundle_id"], atom_version_id=atom["atom_version_id"], event_type="cited",
        ))
        self.assertEqual(feedback["event_type"], "cited")
        updated = self.service.query(QueryRequest(workspace_id="alpha", query="citations precise", retrieval_profile="rerank"))
        selected = next(item for item in updated["results"] if item["atom_version_id"] == atom["atom_version_id"])
        self.assertGreater(selected["channel_scores"]["feedback"], 0)

    def test_feedback_can_only_propose_a_reviewed_edge_strength_revision(self) -> None:
        atoms = self.ingest("Service depends on index.\n\nIndex stores evidence.")
        edge = self.service.create_proposal(ProposalCreateRequest(
            workspace_id="alpha", proposal_type="edge", confidence=0.8,
            candidate={"source_node_id": atoms[0]["node_id"], "target_node_id": atoms[1]["node_id"], "relation_type": "depends_on"},
            evidence_atom_version_ids=[atoms[0]["atom_version_id"], atoms[1]["atom_version_id"]],
        ))
        promoted = self.service.promote_proposal(edge["proposal_id"], actor="reviewer", reason="reviewed", idempotency_key=None)
        query = self.service.query(QueryRequest(workspace_id="alpha", query="service index", retrieval_profile="rerank"))
        self.service.record_feedback(EvidenceFeedbackRequest(
            workspace_id="alpha", evidence_bundle_id=query["evidence_bundle_id"], atom_version_id=atoms[0]["atom_version_id"], event_type="cited", weight=2,
        ))
        proposed = self.service.propose_feedback_edge_strengths(FeedbackEdgeProposalRequest(workspace_id="alpha", minimum_signal=0.01))
        self.assertEqual(len(proposed["proposals"]), 1)
        strength = proposed["proposals"][0]
        self.assertEqual(strength["status"], "pending")
        revised = self.service.promote_proposal(strength["proposal_id"], actor="reviewer", reason="feedback reviewed", idempotency_key=None)
        self.assertEqual(revised["materialized"]["version"], 2)
        self.assertNotEqual(revised["materialized"]["edge_version_id"], promoted["materialized"]["edge_version_id"])
        replay = self.service.store.replay_report("alpha")
        self.assertTrue(replay["valid"], replay["errors"])

    def test_schema_proposals_require_review_and_remain_soft(self) -> None:
        self.ingest("PostgreSQL event store persists audit history.\n\nPostgreSQL event store supports replay.")
        proposals = self.service.propose_schemas(SchemaProposalRequest(workspace_id="alpha", max_schemas=3))
        self.assertTrue(proposals["proposals"])
        schema = proposals["proposals"][0]
        self.assertEqual(schema["status"], "pending")
        self.service.promote_proposal(schema["proposal_id"], actor="reviewer", reason="examples reviewed", idempotency_key=None)
        labels = self.service.classify_atoms("alpha")
        self.assertTrue(any(item["labels"] for item in labels))
        # A nonmatching facet remains retrievable; schemas do not filter atoms.
        response = self.service.query(QueryRequest(workspace_id="alpha", query="replay", retrieval_profile="rerank"))
        self.assertEqual(response["sufficiency_state"], "answerable")

    def test_deep_mode_expands_selected_hierarchy_to_raw_evidence(self) -> None:
        atoms = self.ingest("Compiler emits an intermediate representation.\n\nOptimizer consumes the intermediate representation.\n\nCode generator emits machine code.")
        self.service.build_hierarchy(HierarchyBuildRequest(workspace_id="alpha", section_size=2))
        response = self.service.query(QueryRequest(
            workspace_id="alpha", query="what consumes intermediate representation", retrieval_profile="deep",
            retrieval_budget=RetrievalBudget(mode="deep", candidate_limit=10, deep_max_nodes=3),
        ))
        self.assertTrue(response["retrieval_diagnostics"]["deep_applied"])
        self.assertTrue(any(item["candidate_kind"] == "atom" and item["atom_version_id"] == atoms[1]["atom_version_id"] for item in response["results"]))

    def test_benchmark_reports_all_evidence_metrics(self) -> None:
        atom = self.ingest("The deployment guide requires a migration before rollout.")[0]
        benchmark = {"name": "technical-docs-test", "cases": [
                {"id": "direct", "kind": "direct_lookup", "query": "migration before rollout", "gold_atom_version_ids": [atom["atom_version_id"]]},
                {"id": "outside", "kind": "out_of_scope", "query": "quantum orchard", "gold_atom_version_ids": [], "out_of_scope": True},
            ]}
        with patch("trace.v2.service.load_benchmark", return_value=benchmark):
            run = self.service.run_benchmark(BenchmarkRunRequest(
                workspace_id="alpha", benchmark_path="frozen.json", stages=["lexical", "hybrid", "rerank"],
            ))
        metrics = run["result"]["stages"]["rerank"]["metrics"]
        self.assertIn("recall_at_5", metrics)
        self.assertIn("citation_precision", metrics)
        self.assertIn("p95_latency_ms", metrics)
        self.assertEqual(run["benchmark_name"], "technical-docs-test")

    def test_frozen_technical_docs_fixture_bootstraps_reproducibly(self) -> None:
        benchmark_path = Path(__file__).resolve().parents[1] / "benchmarks" / "technical-docs-v1.json"
        run = self.service.run_benchmark(BenchmarkRunRequest(
            workspace_id="benchmark-alpha", benchmark_path=str(benchmark_path), stages=["lexical", "graph", "deep"], bootstrap_fixture=True,
        ))
        self.assertEqual(run["result"]["case_count"], 6)
        self.assertGreater(run["result"]["stages"]["graph"]["metrics"]["recall_at_5"], 0)


if __name__ == "__main__":
    unittest.main()
