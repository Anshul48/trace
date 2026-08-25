from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from trace.v2.api import create_app
from trace.v2.model_gateway import ModelGatewayPolicy, ModelPolicy
from trace.v2.models import CortexReleaseCreateRequest, IngestionRequest, JobSubmitRequest
from trace.v2.pagination import PaginationError, decode_page_token, encode_page_token
from trace.v2.production import NatsJetStreamPublisher, OpenSearchLexicalIndex, PostgresEventStore, QdrantDenseIndex
from trace.v2.service import TraceService
from trace.v2.store import InvariantViolation, SqliteEventStore


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


class RecordingNatsClient:
    def __init__(self) -> None:
        self.is_closed = False
        self.messages: list[tuple[str, bytes]] = []
        self.drained = False

    def jetstream(self):  # type: ignore[no-untyped-def]
        return self

    async def publish(self, subject: str, body: bytes) -> None:
        self.messages.append((subject, body))

    async def drain(self) -> None:
        self.drained = True
        self.is_closed = True


class RecordingOpenSearchIndices:
    def __init__(self) -> None:
        self.created: list[str] = []

    def exists(self, *, index: str) -> bool:
        return index in self.created

    def create(self, *, index: str, body: dict) -> None:  # type: ignore[no-untyped-def]
        del body
        self.created.append(index)


class RecordingOpenSearchClient:
    def __init__(self) -> None:
        self.indices = RecordingOpenSearchIndices()
        self.bulk_calls: list[list[dict]] = []
        self.search_calls: list[tuple[str, dict]] = []

    def bulk(self, *, body: list[dict], refresh: bool) -> dict[str, object]:
        self.bulk_calls.append(body)
        self.asserted_refresh = refresh
        return {"errors": False}

    def search(self, *, index: str, body: dict) -> dict[str, object]:
        self.search_calls.append((index, body))
        return {"hits": {"hits": []}}


class RecordingQdrantClient:
    def __init__(self) -> None:
        self.collections: list[str] = []
        self.payload_indexes: list[str] = []
        self.upsert_batches: list[list[object]] = []
        self.search_calls: list[tuple[str, object]] = []
        self.delete_calls: list[tuple[str, object]] = []

    def collection_exists(self, collection: str) -> bool:
        return collection in self.collections

    def create_collection(self, *, collection_name: str, vectors_config: object) -> None:
        del vectors_config
        self.collections.append(collection_name)

    def create_payload_index(self, *, collection_name: str, field_name: str, field_schema: object, wait: bool) -> None:
        del collection_name, field_schema, wait
        self.payload_indexes.append(field_name)

    def upsert(self, *, collection_name: str, points: list[object], wait: bool) -> None:
        del collection_name, wait
        self.upsert_batches.append(points)

    def query_points(self, *, collection_name: str, query: list[float], query_filter: object, limit: int, with_payload: bool) -> dict[str, object]:
        del query, limit, with_payload
        self.search_calls.append((collection_name, query_filter))
        return {"points": []}

    def delete(self, *, collection_name: str, points_selector: object, wait: bool) -> None:
        del wait
        self.delete_calls.append((collection_name, points_selector))


class RecordingPgCursor:
    def __init__(self, name: str | None) -> None:
        self.name = name
        self.executions: list[tuple[str, object]] = []

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.executions.append((query, params))

    def fetchmany(self, size: int) -> list[object]:
        del size
        return []


class RecordingPgConnection:
    def __init__(self) -> None:
        self.cursors: list[RecordingPgCursor] = []

    def cursor(self, name: str | None = None) -> RecordingPgCursor:
        cursor = RecordingPgCursor(name)
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


class ProductionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = TraceService(SqliteEventStore(":memory:"), MemoryObjectStore())

    def tearDown(self) -> None:
        self.service.store.close()

    def test_postgres_streaming_iterators_bind_rls_before_named_cursor(self) -> None:
        connection = RecordingPgConnection()
        store = PostgresEventStore(connection_factory=lambda: connection)

        self.assertEqual(list(store.iter_indexable_atom_versions("alpha")), [])
        self.assertEqual(list(store.iter_queryable_atoms("alpha")), [])

        self.assertEqual(
            [cursor.name for cursor in connection.cursors],
            [None, "trace_indexable_atom_versions", None, "trace_current_atoms"],
        )
        for regular in (connection.cursors[0], connection.cursors[2]):
            self.assertIn("set_config('trace.workspace_id'", regular.executions[0][0])
            self.assertEqual(regular.executions[0][1], ("alpha",))
        for named in (connection.cursors[1], connection.cursors[3]):
            self.assertNotIn("set_config", named.executions[0][0])

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

    def test_nats_publisher_reuses_and_drains_its_connection(self) -> None:
        client = RecordingNatsClient()
        publisher = NatsJetStreamPublisher(client=client, stream="TRACE_EVENTS")

        async def exercise() -> None:
            await publisher.publish("ingestion.accepted", {"event_id": "one"})
            await publisher.publish("ingestion.accepted", {"event_id": "two"})
            await publisher.drain()

        asyncio.run(exercise())
        self.assertEqual([subject for subject, _ in client.messages], [
            "trace_events.ingestion_accepted", "trace_events.ingestion_accepted",
        ])
        self.assertTrue(client.drained)
        self.assertIsNone(publisher.client)

    def test_external_delta_adapters_use_idempotent_bounded_batches(self) -> None:
        lexical_client = RecordingOpenSearchClient()
        lexical = OpenSearchLexicalIndex("trace", client=lexical_client)
        count = lexical.upsert([
            {"atom_version_id": "atom-1", "workspace_id": "alpha", "content": "one"},
            {"atom_version_id": "atom-2", "workspace_id": "alpha", "content": "two"},
        ], revision="current")
        self.assertEqual(count, 2)
        self.assertEqual(len(lexical_client.bulk_calls), 1)
        self.assertEqual(lexical_client.bulk_calls[0][0]["index"]["_id"], "atom-1")

        dense_client = RecordingQdrantClient()
        dense = QdrantDenseIndex("trace", client=dense_client)
        with patch.dict(os.environ, {"TRACE_QDRANT_BATCH_SIZE": "1"}):
            count = dense.upsert([
                {"atom_version_id": "atom-1", "workspace_id": "alpha", "vector": [0.1, 0.2]},
                {"atom_version_id": "atom-2", "workspace_id": "alpha", "vector": [0.2, 0.1]},
            ], revision="current")
        self.assertEqual(count, 2)
        self.assertEqual(len(dense_client.upsert_batches), 2)

    def test_revision_aware_search_targets_historical_physical_indexes(self) -> None:
        lexical_client = RecordingOpenSearchClient()
        lexical = OpenSearchLexicalIndex("trace", client=lexical_client)
        lexical.search(
            workspace_id="alpha",
            query="historical",
            limit=10,
            as_of_event=42,
            index_revision="history-v1",
        )
        self.assertEqual(lexical_client.search_calls[0][0], "trace--rev-history-v1")
        lexical_filters = lexical_client.search_calls[0][1]["query"]["bool"]["filter"]
        self.assertIn({"term": {"index_revision": "history-v1"}}, lexical_filters)
        self.assertIn({"range": {"created_event_offset": {"lte": 42}}}, lexical_filters)

        dense_client = RecordingQdrantClient()
        dense = QdrantDenseIndex("trace", client=dense_client)
        dense.search(
            workspace_id="alpha",
            vector=[0.1, 0.2],
            limit=10,
            as_of_event=42,
            index_revision="history-v1",
        )
        self.assertEqual(dense_client.search_calls[0][0], "trace--rev-history-v1")
        dense_filter = dense_client.search_calls[0][1]
        self.assertIn(
            {"key": "index_revision", "match": {"value": "history-v1"}},
            dense_filter["must"],
        )
        dense.delete_atom("atom-1", revision="history-v1")
        delete_collection, selector = dense_client.delete_calls[0]
        selector_ids = getattr(selector, "points", selector)
        self.assertEqual(delete_collection, "trace--rev-history-v1")
        self.assertEqual(
            list(selector_ids),
            [str(uuid.uuid5(uuid.NAMESPACE_URL, "trace:qdrant:atom-1:history-v1"))],
        )
        with self.assertRaisesRegex(ValueError, "logical component revision"):
            lexical.search(
                workspace_id="alpha",
                query="ambiguous",
                limit=1,
                index_revision="trace--rev-history-v1",
            )
        with self.assertRaisesRegex(ValueError, "logical component revision"):
            dense.search(
                workspace_id="alpha",
                vector=[0.1, 0.2],
                limit=1,
                index_revision="trace--rev-history-v1",
            )
        with self.assertRaisesRegex(ValueError, "logical component revision"):
            dense.delete_atom("atom-1", revision="trace--rev-history-v1")
        with self.assertRaises(InvariantViolation):
            self.service.create_cortex_release(
                CortexReleaseCreateRequest(
                    workspace_id="alpha",
                    components=[{
                        "component_kind": "dense_index",
                        "component_revision": "trace--rev-history-v1",
                    }],
                )
            )
        logical_release = self.service.create_cortex_release(
            CortexReleaseCreateRequest(
                workspace_id="alpha",
                components=[{
                    "component_kind": "dense_index",
                    "component_revision": "history-v1",
                }],
            )
        )
        dense_component = next(
            item for item in logical_release["components"]
            if item["component_kind"] == "dense_index"
        )
        self.assertEqual(dense_component["component_revision"], "history-v1")


if __name__ == "__main__":
    unittest.main()
