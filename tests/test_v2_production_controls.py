from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from trace.v2.api import create_app
from trace.v2.model_gateway import ModelGatewayPolicy, ModelPolicy
from trace.v2.models import (
    CortexReleaseCreateRequest,
    IngestionRequest,
    JobSubmitRequest,
    QueryRequest,
    SourceLifecycleRequest,
)
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
        self.creation_bodies: list[dict] = []

    def exists(self, *, index: str) -> bool:
        return index in self.created

    def create(self, *, index: str, body: dict) -> None:  # type: ignore[no-untyped-def]
        self.created.append(index)
        self.creation_bodies.append(body)


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
        self.description: list[tuple[str]] = []
        self.fetchone_result: object = None

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: object = None) -> None:
        self.executions.append((query, params))

    def fetchmany(self, size: int) -> list[object]:
        del size
        return []

    def fetchone(self) -> object:
        return self.fetchone_result


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

    def test_postgres_node_boundaries_normalize_uuid_identifiers(self) -> None:
        store = PostgresEventStore(connection_factory=lambda: RecordingPgConnection())
        node_id = uuid.uuid4()
        atom_version_id = uuid.uuid4()

        node_cursor = RecordingPgCursor(None)
        node_cursor.description = [
            ("node_id",), ("workspace_id",), ("facets",), ("security",), ("created_event_offset",),
        ]
        node_cursor.fetchone_result = (node_id, "alpha", ["atom"], {"visibility": "private"}, 1)
        node = store._pg_node(node_cursor, str(node_id))

        version_cursor = RecordingPgCursor(None)
        version_cursor.description = [
            ("atom_version_id",), ("node_id",), ("version",), ("content",),
            ("properties",), ("content_hash",), ("created_event_offset",),
        ]
        version_cursor.fetchone_result = (atom_version_id, node_id, 1, "content", {}, "hash", 2)
        version = store._pg_node_version(version_cursor, str(node_id))

        self.assertEqual(node["node_id"], str(node_id))
        self.assertEqual(version["node_id"], str(node_id))
        self.assertEqual(version["atom_version_id"], str(atom_version_id))

    def test_postgres_cortex_release_boundaries_are_bundle_json_serializable(self) -> None:
        release_id = uuid.uuid4()
        parent_release_id = uuid.uuid4()
        created_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
        activated_at = datetime(2024, 1, 2, 4, 5, 6, tzinfo=UTC)
        superseded_at = datetime(2024, 1, 3, 5, 6, 7, tzinfo=UTC)
        retired_at = datetime(2024, 1, 4, 6, 7, 8, tzinfo=UTC)
        component = PostgresEventStore._pg_cortex_component_row({
            "release_id": release_id,
            "component_kind": "lexical_index",
            "component_revision": "temporal-r1",
            "carried_forward_from_release_id": parent_release_id,
            "metadata": {"source": "postgres"},
            "created_at": created_at,
        })
        release = PostgresEventStore._pg_cortex_release_row({
            "release_id": release_id,
            "workspace_id": "alpha",
            "parent_release_id": parent_release_id,
            "validation_receipt": {"passed": True},
            "created_at": created_at,
            "activated_at": activated_at,
            "superseded_at": superseded_at,
            "retired_at": retired_at,
        }, components=[component])

        self.assertEqual(release["release_id"], str(release_id))
        self.assertEqual(release["parent_release_id"], str(parent_release_id))
        self.assertEqual(release["created_at"], created_at.isoformat())
        self.assertEqual(release["activated_at"], activated_at.isoformat())
        self.assertEqual(release["superseded_at"], superseded_at.isoformat())
        self.assertEqual(release["retired_at"], retired_at.isoformat())
        self.assertEqual(component["release_id"], str(release_id))
        self.assertEqual(component["carried_forward_from_release_id"], str(parent_release_id))
        self.assertEqual(component["created_at"], created_at.isoformat())
        json.dumps({
            "results": [{"temporal": {"release_id": release["release_id"]}}],
            "retrieval_diagnostics": {"release": release},
        })

        self.service.ingest(IngestionRequest(workspace_id="alpha", text="postgres release bundle evidence"))
        with (
            patch.object(self.service.store, "get_active_cortex_release", return_value=release),
            patch.object(self.service.store, "get_cortex_release", return_value=release),
        ):
            response = self.service.query(QueryRequest(
                workspace_id="alpha",
                query="postgres release bundle evidence",
            ))
        self.assertTrue(response["results"])
        self.assertEqual(response["results"][0]["temporal"]["release_id"], str(release_id))
        json.dumps(response)

    def test_postgres_lifecycle_boundaries_are_service_and_api_json_serializable(self) -> None:
        atom_version_id = uuid.uuid4()
        predecessor_atom_version_id = uuid.uuid4()
        successor_atom_version_id = uuid.uuid4()
        changed_at = datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC)
        lifecycle = PostgresEventStore._pg_lifecycle_row({
            "atom_version_id": atom_version_id,
            "workspace_id": "alpha",
            "state": "superseded",
            "valid_from": changed_at,
            "valid_to": None,
            "valid_precision": "day",
            "valid_confidence": "explicit",
            "valid_provenance": {"source": "postgres"},
            "predecessor_atom_version_id": predecessor_atom_version_id,
            "superseded_by_atom_version_id": successor_atom_version_id,
            "changed_event_offset": 11,
            "erasure_receipt": None,
            "created_at": changed_at,
        })
        assert lifecycle is not None

        self.assertEqual(lifecycle["atom_version_id"], str(atom_version_id))
        self.assertEqual(
            lifecycle["predecessor_atom_version_id"], str(predecessor_atom_version_id)
        )
        self.assertEqual(
            lifecycle["superseded_by_atom_version_id"], str(successor_atom_version_id)
        )
        json.dumps(lifecycle)

        request = SourceLifecycleRequest(
            state="conflicted",
            actor="reviewer",
        )
        with patch.object(
            self.service.store,
            "transition_source_lifecycle",
            return_value=lifecycle,
        ), patch.object(
            self.service.store,
            "atom_versions",
            return_value=[{"workspace_id": "alpha"}],
        ):
            service_result = self.service.transition_source_lifecycle(str(atom_version_id), request)
            self.assertEqual(
                service_result["superseded_by_atom_version_id"], str(successor_atom_version_id)
            )
            json.dumps(service_result)
            with TestClient(create_app(self.service)) as client:
                response = client.post(
                    f"/v2/atom-versions/{atom_version_id}/lifecycle",
                    json=request.model_dump(mode="json"),
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["superseded_by_atom_version_id"], str(successor_atom_version_id)
        )

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
        source_mapping = lexical_client.indices.creation_bodies[0]["mappings"]["properties"]["source"]
        self.assertFalse(source_mapping["dynamic"])
        self.assertEqual(
            set(source_mapping["properties"]),
            {"title", "uri", "media_type", "adapter", "metadata"},
        )
        self.assertFalse(source_mapping["properties"]["metadata"]["enabled"])

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
