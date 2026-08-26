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

    def test_cortex_release_http_endpoints(self) -> None:
        service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())
        with TestClient(create_app(service)) as client:
            client.post("/v2/ingestions", json={"workspace_id": "cortex-api", "text": "node alpha\n\nnode beta"})

            # Create initial release
            r0_res = client.post("/v2/cortex/releases", json={
                "workspace_id": "cortex-api",
                "policy_revision": "cortex-v0",
            })
            self.assertEqual(r0_res.status_code, 201)
            r0_id = r0_res.json()["release_id"]
            client.post(f"/v2/cortex/releases/{r0_id}/validate", json={"validation_receipt": {"passed": True}})
            client.post(f"/v2/cortex/releases/{r0_id}/activate")

            # List releases
            list_res = client.get("/v2/cortex/releases?workspace_id=cortex-api")
            self.assertEqual(list_res.status_code, 200)
            initial_releases = list_res.json()
            self.assertGreaterEqual(len(initial_releases), 1)

            # Get active release
            active_res = client.get("/v2/cortex/releases/active?workspace_id=cortex-api")
            self.assertEqual(active_res.status_code, 200)
            active_rel = active_res.json()
            self.assertEqual(active_rel["status"], "active")
            self.assertEqual(active_rel["release_id"], r0_id)

            # Create candidate release
            create_res = client.post("/v2/cortex/releases", json={
                "workspace_id": "cortex-api",
                "policy_revision": "cortex-api-v1",
            })
            self.assertEqual(create_res.status_code, 201)
            cand = create_res.json()
            cand_id = cand["release_id"]
            self.assertEqual(cand["status"], "building")

            # Validate candidate
            val_res = client.post(f"/v2/cortex/releases/{cand_id}/validate", json={
                "validation_receipt": {"passed": True, "rationale": "all tests pass"}
            })
            self.assertEqual(val_res.status_code, 200)
            self.assertEqual(val_res.json()["status"], "validated")

            # Activate candidate
            act_res = client.post(f"/v2/cortex/releases/{cand_id}/activate")
            self.assertEqual(act_res.status_code, 200)
            self.assertEqual(act_res.json()["status"], "active")

            # Check active is now candidate
            active_res2 = client.get("/v2/cortex/releases/active?workspace_id=cortex-api")
            self.assertEqual(active_res2.status_code, 200)
            self.assertEqual(active_res2.json()["release_id"], cand_id)

            # Rollback
            rb_res = client.post("/v2/cortex/releases/rollback", json={
                "workspace_id": "cortex-api",
                "reason": "testing rollback api",
            })
            self.assertEqual(rb_res.status_code, 200)
            self.assertEqual(rb_res.json()["release_id"], r0_id)
        service.store.close()



if __name__ == "__main__":
    unittest.main()
