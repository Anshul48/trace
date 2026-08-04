from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from trace.v2.api import create_app
from trace.v2.model_gateway import ModelGatewayPolicy, ModelPolicy
from trace.v2.models import IngestionRequest, JobSubmitRequest
from trace.v2.pagination import PaginationError, decode_page_token, encode_page_token
from trace.v2.service import TraceService
from trace.v2.store import SqliteEventStore


class MemoryObjectStore:
    def put_bytes(self, raw: bytes, media_type: str):
        return {
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "object_key": "test/source",
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {},
        }

    def put_text(self, text: str, media_type: str):
        return self.put_bytes(text.encode("utf-8"), media_type)


class ProductionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())

    def tearDown(self) -> None:
        self.service.store.close()

    def test_jobs_are_idempotent_and_retryable(self) -> None:
        first = self.service.submit_job(JobSubmitRequest(
            workspace_id="alpha", kind="reprocess", payload={"workspace_id": "alpha"}, idempotency_key="reprocess-1",
        ))
        duplicate = self.service.submit_job(JobSubmitRequest(
            workspace_id="alpha", kind="reprocess", payload={"workspace_id": "alpha"}, idempotency_key="reprocess-1",
        ))
        self.assertEqual(first["job_id"], duplicate["job_id"])
        failed = self.service.store.fail_job(first["job_id"], error={"type": "temporary"}, retry=False)
        self.assertEqual(failed["status"], "failed")
        retried = self.service.retry_job(first["job_id"], actor="reviewer")
        self.assertEqual(retried["status"], "queued")
        completed = self.service.jobs.execute(first["job_id"])
        self.assertEqual(completed["status"], "succeeded")

    def test_api_key_scope_and_opaque_page_cursor(self) -> None:
        with TestClient(create_app(self.service)) as client:
            self.assertEqual(client.post("/v2/ingestions", json={"workspace_id": "alpha", "text": "private evidence"}).status_code, 202)
            created = client.post("/v2/api-keys", json={
                "workspace_id": "alpha", "subject": "reader", "scopes": ["retrieval:read"],
            })
            self.assertEqual(created.status_code, 201)
            key = created.json()["api_key"]
            self.assertEqual(client.post("/v2/queries", headers={"X-API-Key": key}, json={"workspace_id": "alpha", "query": "evidence"}).status_code, 200)
            self.assertEqual(client.post("/v2/ingestions", headers={"X-API-Key": key}, json={"workspace_id": "alpha", "text": "denied"}).status_code, 403)
        token = encode_page_token(scope="jobs:alpha", position=4, limit=5)
        self.assertEqual(decode_page_token(token, scope="jobs:alpha").position, 4)
        with self.assertRaises(PaginationError):
            decode_page_token(token[:-1] + ("A" if token[-1] != "A" else "B"), scope="jobs:alpha")

    def test_model_gateway_redacts_before_cloud_policy_boundary(self) -> None:
        policy = ModelGatewayPolicy(ModelPolicy(allow_cloud=True))
        query, candidates, audit = policy.prepare(
            provider="test", purpose="deep", query="contact a.person@example.com",
            candidates=[{"atom_version_id": "atom-1", "content": "token sk_abcdefghijklmnop"}],
            max_nodes=2, token_budget=100, cloud=True,
        )
        self.assertNotIn("a.person@example.com", query)
        self.assertNotIn("sk_abcdefghijklmnop", candidates[0]["content"])
        self.assertEqual(audit.node_count, 1)


if __name__ == "__main__":
    unittest.main()

