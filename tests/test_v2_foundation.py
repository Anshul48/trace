from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trace.v2.models import IngestionRequest, NodeEditRequest, ProposalCreateRequest, QueryRequest, RetrievalBudget
from trace.v2.service import TraceService
from trace.v2.store import SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str):
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(), "object_key": "test/source",
            "media_type": media_type, "byte_length": len(raw), "metadata": {"storage": "test"},
        }

    def put_text(self, text: str, media_type: str):
        return self.put_bytes(text.encode("utf-8"), media_type)


class TraceV2FoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())

    def tearDown(self) -> None:
        self.service.store.close()

    def test_ingestion_is_idempotent_and_structural_history_is_replayable(self) -> None:
        request = IngestionRequest(
            workspace_id="alpha",
            text="First paragraph explains PostgreSQL events.\n\n- Second bullet is independently atomic.\n- Third bullet follows it.",
            source={"title": "notes.md", "uri": "memory://notes.md", "media_type": "text/markdown"},
            idempotency_key="notes-v1",
        )

        first = self.service.ingest(request)
        second = self.service.ingest(request)

        self.assertEqual(first["ingestion_id"], second["ingestion_id"])
        self.assertEqual(first["atom_count"], 3)
        atoms = self.service.store.ingestion_atoms(first["ingestion_id"])
        self.assertEqual(
            [atom["content"] for atom in atoms],
            [
                "First paragraph explains PostgreSQL events.",
                "- Second bullet is independently atomic.",
                "- Third bullet follows it.",
            ],
        )
        edges = self.service.store.current_edges("alpha")
        self.assertEqual(len([edge for edge in edges if edge["relation_type"] == "NEXT"]), 2)
        self.assertTrue(all(edge["evidence_anchors"] for edge in edges))
        replay = self.service.store.replay_report("alpha")
        self.assertTrue(replay["valid"], replay["errors"])

    def test_versions_proposals_and_reconciliation_preserve_evidence(self) -> None:
        ingestion = self.service.ingest(
            IngestionRequest(workspace_id="alpha", text="PostgreSQL stores the event spine.\n\nQdrant stores versioned vectors.")
        )
        atoms = self.service.store.ingestion_atoms(ingestion["ingestion_id"])
        original = atoms[0]
        updated = self.service.edit_node(
            original["node_id"], NodeEditRequest(content="PostgreSQL stores an immutable event spine.", idempotency_key="edit-1")
        )
        self.assertEqual(updated["version"], 2)
        self.assertEqual(
            self.service.store.get_node(original["node_id"], original["created_event_offset"])["content"], original["content"]
        )
        self.assertEqual(len(self.service.store.node_history(original["node_id"])), 2)

        proposal = self.service.create_proposal(
            ProposalCreateRequest(
                workspace_id="alpha", proposal_type="edge", confidence=0.9,
                candidate={"source_node_id": atoms[0]["node_id"], "target_node_id": atoms[1]["node_id"], "relation_type": "supports"},
                evidence_atom_version_ids=[updated["atom_version_id"], atoms[1]["atom_version_id"]],
            )
        )
        promoted = self.service.promote_proposal(proposal["proposal_id"], actor="reviewer", reason="source-backed", idempotency_key=None)
        self.assertEqual(promoted["status"], "promoted")
        self.assertTrue(promoted["materialized"]["edge_version_id"])
        self.assertTrue(self.service.store.current_edges("alpha")[-1]["evidence_anchors"])
        replay = self.service.store.replay_report("alpha")
        self.assertTrue(replay["valid"], replay["errors"])

        before = len(self.service.store.queryable_atoms("alpha"))
        reconciliation = self.service.replay(workspace_id="alpha")
        self.assertEqual(reconciliation["inserted"], before)
        self.assertEqual(len(self.service.store.queryable_atoms("alpha")), before)

    def test_query_returns_auditable_bundle_and_abstains(self) -> None:
        self.service.ingest(IngestionRequest(workspace_id="alpha", text="Trace uses an append-only Atom Event Spine."))

        answerable = self.service.query(QueryRequest(workspace_id="alpha", query="Atom Spine"))
        self.assertEqual(answerable["sufficiency_state"], "answerable")
        self.assertTrue(answerable["results"][0]["source_location"]["attachment_id"])
        self.assertTrue(answerable["results"][0]["atom_version_id"])

        absent = self.service.query(QueryRequest(workspace_id="alpha", query="unrelated quantum orchard"))
        self.assertEqual(absent["sufficiency_state"], "insufficient_evidence")
        self.assertEqual(absent["results"], [])

    def test_html_adapter_keeps_raw_attachment_but_atomizes_text(self) -> None:
        result = self.service.ingest(
            IngestionRequest(
                workspace_id="alpha", text="<h1>Trace</h1><script>discard()</script><p>Evidence survives.</p>",
                source={"adapter": "html", "media_type": "text/html"},
            )
        )
        content = " ".join(atom["content"] for atom in self.service.store.ingestion_atoms(result["ingestion_id"]))
        self.assertIn("Trace", content)
        self.assertIn("Evidence survives.", content)
        self.assertNotIn("discard", content)

    def test_file_adapter_retains_a_binary_content_hash(self) -> None:
        raw = b"<p>HTML file evidence.</p>"
        result = self.service.ingest_bytes(
            workspace_id="alpha", raw=raw,
            source={"title": "evidence.html", "media_type": "text/html", "adapter": "html"},
        )
        attachment = self.service.ingestion_status(result["ingestion_id"])["attachment"]
        self.assertEqual(attachment["content_hash"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.service.store.ingestion_atoms(result["ingestion_id"])[0]["content"], "HTML file evidence.")

    def test_hybrid_ladder_exposes_channels_and_graph_activation(self) -> None:
        result = self.service.ingest(IngestionRequest(workspace_id="alpha", text="PostgreSQL stores events.\n\nQdrant stores vectors."))
        atoms = self.service.store.ingestion_atoms(result["ingestion_id"])
        response = self.service.query(QueryRequest(workspace_id="alpha", query="PostgreSQL events", retrieval_budget=RetrievalBudget(mode="graph", candidate_limit=5)))
        self.assertTrue(response["results"])
        channels = response["results"][0]["channel_scores"]
        self.assertGreater(channels["dense"], 0.0)
        self.assertIn("rrf", channels)
        # Structural edges are trusted, but the expanded neighbor remains a
        # raw atom and therefore keeps its own citation identity.
        self.assertTrue(any(item["atom_version_id"] == atoms[1]["atom_version_id"] for item in response["results"]))

    def test_anchored_hierarchy_and_soft_schema_labels(self) -> None:
        result = self.service.ingest(IngestionRequest(workspace_id="alpha", text="PostgreSQL stores the event spine."))
        atom = self.service.store.ingestion_atoms(result["ingestion_id"])[0]
        summary = self.service.create_proposal(ProposalCreateRequest(
            workspace_id="alpha", proposal_type="holon", confidence=0.9,
            candidate={"summary": "PostgreSQL event spine architecture", "model_version": "test"},
            evidence_atom_version_ids=[atom["atom_version_id"]], model_version="test",
        ))
        self.service.promote_proposal(summary["proposal_id"], actor="reviewer", reason="anchored", idempotency_key=None)
        schema = self.service.create_proposal(ProposalCreateRequest(
            workspace_id="alpha", proposal_type="schema", confidence=0.9,
            candidate={"label": "event-storage", "definition": "PostgreSQL event spine", "exclusions": ["unrelated"]},
            evidence_atom_version_ids=[atom["atom_version_id"]], model_version="schema-v1",
        ))
        self.service.promote_proposal(schema["proposal_id"], actor="reviewer", reason="reviewed", idempotency_key=None)
        response = self.service.query(QueryRequest(workspace_id="alpha", query="event spine", retrieval_budget=RetrievalBudget(mode="hierarchy", candidate_limit=5)))
        self.assertTrue(any(item["channel_scores"].get("hierarchy") for item in response["results"]))
        labels = self.service.classify_atoms("alpha")
        self.assertEqual(labels[0]["labels"][0]["label"], "event-storage")


if __name__ == "__main__":
    unittest.main()
