from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from trace.v2.api import create_app
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


class TraceV2CognitiveApiTests(unittest.TestCase):
    def test_cognitive_routes_preserve_evidence_contracts(self) -> None:
        service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())
        with TestClient(create_app(service)) as client:
            ingestion = client.post("/v2/ingestions", json={
                "workspace_id": "api", "text": "The retriever stores citations.\n\nThe graph expands trusted relations.",
            })
            self.assertEqual(ingestion.status_code, 202)
            hierarchy = client.post("/v2/hierarchy/build", json={"workspace_id": "api", "section_size": 2})
            self.assertEqual(hierarchy.status_code, 200)
            query = client.post("/v2/queries", json={
                "workspace_id": "api", "query": "stores citations", "retrieval_profile": "rerank",
            })
            self.assertEqual(query.status_code, 200)
            body = query.json()
            self.assertEqual(body["sufficiency_state"], "answerable")
            atom = next(item for item in body["results"] if item["candidate_kind"] == "atom")
            feedback = client.post("/v2/retrieval-feedback", json={
                "workspace_id": "api", "evidence_bundle_id": body["evidence_bundle_id"],
                "atom_version_id": atom["atom_version_id"], "event_type": "opened",
            })
            self.assertEqual(feedback.status_code, 200)
            self.assertEqual(feedback.json()["event_type"], "opened")
        service.store.close()


if __name__ == "__main__":
    unittest.main()
