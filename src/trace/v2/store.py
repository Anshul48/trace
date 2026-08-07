"""Append-only Spine and rebuildable SQLite projections used by the V2 runtime.

Production deployments are expected to provide a PostgreSQL implementation of
the same boundary.  The embedded store intentionally keeps the exact event and
projection contracts available for tests, local development, and replay drills.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence

from .models import AppendResult, EventRecord


# New semantic links are deliberately constrained.  Existing historical rows
# remain readable during migrations, but no producer can create an opaque
# catch-all relation that would make graph activation unauditable.
STRUCTURAL_RELATIONS = frozenset({"NEXT", "CHILD_OF", "DERIVED_FROM", "CONTAINS", "alias_of"})
EVIDENCE_RELATIONS = frozenset({"supports", "contradicts", "depends_on", "implements", "example_of"})
ALLOWED_RELATIONS = STRUCTURAL_RELATIONS | EVIDENCE_RELATIONS


class TraceStoreError(RuntimeError):
    pass


class NotFoundError(TraceStoreError):
    pass


class IdempotencyConflict(TraceStoreError):
    pass


class InvariantViolation(TraceStoreError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: str | None, default: Any = None) -> Any:
    return json.loads(value) if value else ({} if default is None else default)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class SqliteEventStore:
    """A transactional, append-only event store with materialized projections.

    SQLite serializes writers, so this adapter is explicitly for embedded mode.
    Its API is aggregate/stream scoped and maps directly to the PostgreSQL
    implementation used in a distributed deployment; callers never access its
    tables directly.
    """

    def __init__(self, path: str | os.PathLike[str] = "trace_v2.db") -> None:
        self.path = str(path)
        self._memory_connection: sqlite3.Connection | None = None
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        else:
            # A normal ``sqlite3.connect(':memory:')`` call creates a new
            # database per connection.  Keeping this single private connection
            # makes the embedded adapter behave correctly in unit tests too.
            self._memory_connection = sqlite3.connect(":memory:", timeout=30, isolation_level=None, check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = self._memory_connection
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if connection is not self._memory_connection:
                    connection.close()

    def close(self) -> None:
        """Release an in-memory connection explicitly when its owner is done."""

        with self._lock:
            if self._memory_connection is not None:
                self._memory_connection.close()
                self._memory_connection = None

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_offset INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    stream_id TEXT NOT NULL,
                    stream_sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    causation_id TEXT,
                    correlation_id TEXT,
                    schema_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE
                );
                CREATE UNIQUE INDEX IF NOT EXISTS events_stream_sequence
                    ON events(stream_id, stream_sequence);
                CREATE INDEX IF NOT EXISTS events_type_offset ON events(event_type, event_offset);

                CREATE TABLE IF NOT EXISTS outbox (
                    event_offset INTEGER PRIMARY KEY REFERENCES events(event_offset),
                    topic TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    available_at TEXT NOT NULL,
                    published_at TEXT,
                    lease_until TEXT
                );

                CREATE TABLE IF NOT EXISTS ingestions (
                    ingestion_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    attachment_id TEXT,
                    accepted_event_offset INTEGER NOT NULL,
                    atom_count INTEGER NOT NULL DEFAULT 0,
                    parsing_status TEXT NOT NULL,
                    indexing_status TEXT NOT NULL,
                    consolidation_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ingestions_workspace ON ingestions(workspace_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS attachments (
                    attachment_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    byte_length INTEGER NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS attachments_workspace ON attachments(workspace_id);

                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    facets_json TEXT NOT NULL,
                    security_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS nodes_workspace ON nodes(workspace_id, created_event_offset);

                CREATE TABLE IF NOT EXISTS node_versions (
                    atom_version_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL REFERENCES nodes(node_id),
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    UNIQUE(node_id, version)
                );
                CREATE INDEX IF NOT EXISTS node_versions_node_event
                    ON node_versions(node_id, created_event_offset DESC);

                CREATE TABLE IF NOT EXISTS edge_versions (
                    edge_version_id TEXT PRIMARY KEY,
                    edge_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    workspace_id TEXT NOT NULL,
                    source_node_id TEXT NOT NULL REFERENCES nodes(node_id),
                    target_node_id TEXT NOT NULL REFERENCES nodes(node_id),
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    valid_from_event INTEGER NOT NULL,
                    valid_to_event INTEGER,
                    model_version TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    UNIQUE(edge_id, version)
                );
                CREATE INDEX IF NOT EXISTS edge_versions_workspace_nodes
                    ON edge_versions(workspace_id, source_node_id, target_node_id);

                CREATE TABLE IF NOT EXISTS evidence_anchors (
                    anchor_id TEXT PRIMARY KEY,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    source_atom_version_id TEXT NOT NULL REFERENCES node_versions(atom_version_id),
                    source_start INTEGER,
                    source_end INTEGER,
                    parser_location TEXT,
                    quote_hash TEXT,
                    created_event_offset INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS anchors_target ON evidence_anchors(target_kind, target_id);
                CREATE INDEX IF NOT EXISTS anchors_source ON evidence_anchors(source_atom_version_id);

                CREATE TABLE IF NOT EXISTS projection_revisions (
                    projection_name TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    last_applied_event INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(projection_name, workspace_id)
                );
                CREATE TABLE IF NOT EXISTS hot_inbox (
                    atom_version_id TEXT PRIMARY KEY REFERENCES node_versions(atom_version_id),
                    node_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    visible_from_event INTEGER NOT NULL,
                    facets_json TEXT NOT NULL,
                    security_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS hot_inbox_workspace ON hot_inbox(workspace_id, visible_from_event);

                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    proposal_type TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    model_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    decided_event_offset INTEGER,
                    decision_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS proposals_workspace_status ON proposals(workspace_id, status);

                CREATE TABLE IF NOT EXISTS evidence_bundles (
                    evidence_bundle_id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    query_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    sufficiency_state TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS retrieval_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    evidence_bundle_id TEXT,
                    atom_version_id TEXT NOT NULL REFERENCES node_versions(atom_version_id),
                    event_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    actor TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS retrieval_feedback_workspace_atom
                    ON retrieval_feedback(workspace_id, atom_version_id, created_event_offset DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS retrieval_feedback_idempotency
                    ON retrieval_feedback(created_event_offset);
                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    benchmark_run_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    benchmark_name TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS benchmark_runs_workspace ON benchmark_runs(workspace_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS dense_vectors (
                    atom_version_id TEXT NOT NULL REFERENCES node_versions(atom_version_id),
                    provider_id TEXT NOT NULL,
                    index_revision TEXT NOT NULL DEFAULT 'embedded-current',
                    vector_json TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(atom_version_id, provider_id, index_revision)
                );
                CREATE INDEX IF NOT EXISTS dense_vectors_provider ON dense_vectors(provider_id);
                CREATE TABLE IF NOT EXISTS saved_queries (
                    saved_query_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    UNIQUE(workspace_id, name)
                );
                CREATE TABLE IF NOT EXISTS frozen_queries (
                    frozen_query_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    atom_version_ids_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    UNIQUE(workspace_id, name)
                );

                CREATE TABLE IF NOT EXISTS index_revisions (
                    index_revision_id TEXT PRIMARY KEY,
                    embedding_model TEXT NOT NULL,
                    vector_namespace TEXT NOT NULL,
                    lexical_revision TEXT NOT NULL,
                    normalization_json TEXT NOT NULL,
                    rollout_state TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_registry (
                    model_registry_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    version TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    UNIQUE(name, provider, purpose, version)
                );
                CREATE TABLE IF NOT EXISTS experiment_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    corpus_snapshot TEXT NOT NULL,
                    code_revision TEXT NOT NULL,
                    model_versions_json TEXT NOT NULL,
                    index_revisions_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    through_event_offset INTEGER NOT NULL,
                    state_hash TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,
                    lease_until TEXT,
                    error_json TEXT,
                    result_json TEXT,
                    request_id TEXT,
                    webhook_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS jobs_workspace_status
                    ON jobs(workspace_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS projection_events (
                    projection_name TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_offset INTEGER NOT NULL,
                    workspace_id TEXT NOT NULL,
                    projection_revision INTEGER NOT NULL,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY(projection_name, event_id)
                );
                CREATE INDEX IF NOT EXISTS projection_events_offset
                    ON projection_events(projection_name, workspace_id, event_offset);

                CREATE TABLE IF NOT EXISTS webhooks (
                    webhook_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    secret_hash TEXT NOT NULL,
                    secret_ciphertext TEXT NOT NULL,
                    event_types_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    rotated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS webhooks_workspace_status
                    ON webhooks(workspace_id, status);

                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    webhook_id TEXT NOT NULL REFERENCES webhooks(webhook_id),
                    workspace_id TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 8,
                    available_at TEXT NOT NULL,
                    lease_until TEXT,
                    last_error TEXT,
                    delivered_at TEXT,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(webhook_id, job_id, event_type)
                );
                CREATE INDEX IF NOT EXISTS webhook_deliveries_available
                    ON webhook_deliveries(status, available_at, created_at);

                CREATE TABLE IF NOT EXISTS api_keys (
                    api_key_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL,
                    visibility_json TEXT NOT NULL,
                    model_permissions_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS api_keys_active_hash
                    ON api_keys(key_hash, status);

                CREATE TABLE IF NOT EXISTS model_call_audits (
                    model_call_audit_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    request_id TEXT,
                    prompt_template_revision TEXT NOT NULL,
                    response_schema_hash TEXT NOT NULL,
                    excerpt_hashes_json TEXT NOT NULL,
                    node_count INTEGER NOT NULL,
                    estimated_tokens INTEGER NOT NULL,
                    cloud_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_event_offset INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS model_call_audits_workspace_created
                    ON model_call_audits(workspace_id, created_at DESC);
                """
            )
            # V2 previews created before leases were introduced remain readable.
            try:
                conn.execute("ALTER TABLE outbox ADD COLUMN lease_until TEXT")
            except sqlite3.OperationalError:
                pass
            # Jobs were initially only a lightweight status table.  Migrate
            # those local databases in place so upgrades do not discard the
            # durable event history or queued work.
            job_columns = {
                "idempotency_key": "TEXT",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "INTEGER NOT NULL DEFAULT 3",
                "available_at": "TEXT NOT NULL DEFAULT ''",
                "lease_until": "TEXT",
                "error_json": "TEXT",
                "result_json": "TEXT",
                "request_id": "TEXT",
                "webhook_id": "TEXT",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "started_at": "TEXT",
                "finished_at": "TEXT",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
            }
            existing_job_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            for column, declaration in job_columns.items():
                if column not in existing_job_columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {declaration}")
            # Old rows use an empty availability timestamp, which would make
            # them invisible to a worker.  They are local preview rows only,
            # so assigning the current time is the safe migration behavior.
            now = _now()
            conn.execute("UPDATE jobs SET available_at=? WHERE available_at=''", (now,))
            conn.execute("UPDATE jobs SET created_at=updated_at WHERE created_at=''", ())
            conn.execute(
                "CREATE INDEX IF NOT EXISTS jobs_available ON jobs(status, available_at, updated_at)"
            )
            dense_columns = {row[1] for row in conn.execute("PRAGMA table_info(dense_vectors)").fetchall()}
            if "index_revision" not in dense_columns:
                conn.execute("ALTER TABLE dense_vectors ADD COLUMN index_revision TEXT NOT NULL DEFAULT 'embedded-current'")

    # ------------------------------------------------------------------ Spine
    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        stream_id: str,
        event_type: str,
        payload: dict[str, Any],
        actor: str = "system",
        causation_id: str | None = None,
        correlation_id: str | None = None,
        schema_version: int = 1,
        idempotency_key: str | None = None,
    ) -> AppendResult:
        payload_hash = _digest(payload)
        if idempotency_key:
            existing = conn.execute(
                "SELECT event_id, event_offset, stream_sequence, payload_hash, event_type "
                "FROM events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash or existing["event_type"] != event_type:
                    raise IdempotencyConflict("idempotency key was reused with a different event")
                return AppendResult(
                    event_id=existing["event_id"],
                    offset=existing["event_offset"],
                    stream_sequence=existing["stream_sequence"],
                    duplicate=True,
                )
        sequence = conn.execute(
            "SELECT COALESCE(MAX(stream_sequence), 0) + 1 FROM events WHERE stream_id = ?",
            (stream_id,),
        ).fetchone()[0]
        event_id = str(uuid.uuid4())
        occurred_at = _now()
        cursor = conn.execute(
            """INSERT INTO events(
                event_id, stream_id, stream_sequence, event_type, occurred_at, actor,
                causation_id, correlation_id, schema_version, payload_json, payload_hash,
                idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                stream_id,
                sequence,
                event_type,
                occurred_at,
                actor,
                causation_id,
                correlation_id,
                schema_version,
                _json(payload),
                payload_hash,
                idempotency_key,
            ),
        )
        offset = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO outbox(event_offset, topic, payload_json, available_at) VALUES (?, ?, ?, ?)",
            (offset, event_type, _json({"event_id": event_id, "offset": offset, "payload": payload}), occurred_at),
        )
        return AppendResult(event_id=event_id, offset=offset, stream_sequence=sequence)

    def append_event(self, **kwargs: Any) -> AppendResult:
        with self.transaction() as conn:
            return self._append_event(conn, **kwargs)

    def events(self, *, after_offset: int = 0, through_offset: int | None = None) -> list[EventRecord]:
        sql = "SELECT * FROM events WHERE event_offset > ?"
        values: list[Any] = [after_offset]
        if through_offset is not None:
            sql += " AND event_offset <= ?"
            values.append(through_offset)
        sql += " ORDER BY event_offset"
        with self._connect() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [
            EventRecord(
                event_id=row["event_id"], offset=row["event_offset"], stream_id=row["stream_id"],
                stream_sequence=row["stream_sequence"], event_type=row["event_type"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]), actor=row["actor"],
                causation_id=row["causation_id"], correlation_id=row["correlation_id"],
                schema_version=row["schema_version"], payload=_decode(row["payload_json"]),
                payload_hash=row["payload_hash"], idempotency_key=row["idempotency_key"],
            )
            for row in rows
        ]

    def replay_report(self, workspace_id: str) -> dict[str, Any]:
        """Prove that Spine events reconstruct the canonical V2 records.

        This does not copy a database file.  It independently folds the event
        stream into a clean in-memory state and compares that state with the
        materialized canonical records.  Projection tables are intentionally not
        part of the comparison because they are rebuildable.
        """

        folded_nodes: dict[str, dict[str, Any]] = {}
        folded_versions: dict[str, dict[str, Any]] = {}
        folded_edges: dict[str, dict[str, Any]] = {}
        folded_attachments: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for event in self.events():
            payload = event.payload
            if event.event_type == "node.created" and payload.get("workspace_id") == workspace_id:
                folded_nodes[payload["node_id"]] = {
                    "facets": payload.get("facets", []), "security": payload.get("security", {}),
                }
            elif event.event_type == "node.versioned" and payload.get("node_id") in folded_nodes:
                required = {"atom_version_id", "version", "content", "properties"}
                if not required <= payload.keys():
                    errors.append(f"event {event.offset} cannot replay node version")
                    continue
                folded_versions[payload["atom_version_id"]] = {
                    "node_id": payload["node_id"], "version": payload["version"], "content": payload["content"],
                    "properties": payload["properties"],
                }
            elif event.event_type == "edge.versioned" and payload.get("workspace_id") == workspace_id:
                required = {"edge_version_id", "edge_id", "source_node_id", "target_node_id", "relation_type", "evidence_atom_version_ids"}
                if not required <= payload.keys():
                    errors.append(f"event {event.offset} cannot replay edge version")
                    continue
                folded_edges[payload["edge_version_id"]] = payload
            elif event.event_type == "attachment.recorded" and payload.get("workspace_id") == workspace_id:
                folded_attachments[payload["attachment_id"]] = payload

        with self._connect() as conn:
            actual_nodes = {
                row["node_id"]: {"facets": _decode(row["facets_json"], []), "security": _decode(row["security_json"])}
                for row in conn.execute("SELECT * FROM nodes WHERE workspace_id=?", (workspace_id,))
            }
            actual_versions = {
                row["atom_version_id"]: {
                    "node_id": row["node_id"], "version": row["version"], "content": row["content"],
                    "properties": _decode(row["properties_json"]),
                }
                for row in conn.execute(
                    """SELECT nv.* FROM node_versions nv JOIN nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=?""", (workspace_id,)
                )
            }
            actual_edges = {
                row["edge_version_id"]: row
                for row in conn.execute("SELECT * FROM edge_versions WHERE workspace_id=?", (workspace_id,))
            }
            actual_attachments = {
                row["attachment_id"]: row
                for row in conn.execute("SELECT * FROM attachments WHERE workspace_id=?", (workspace_id,))
            }
            for version_id, payload in folded_edges.items():
                row = actual_edges.get(version_id)
                if not row:
                    errors.append(f"edge {version_id} exists in the event fold but not in canonical records")
                    continue
                expected = payload["evidence_atom_version_ids"]
                anchored = [
                    anchor[0] for anchor in conn.execute(
                        "SELECT source_atom_version_id FROM evidence_anchors WHERE target_kind='edge_version' AND target_id=? ORDER BY source_atom_version_id",
                        (version_id,),
                    )
                ]
                if sorted(expected) != anchored:
                    errors.append(f"edge {version_id} evidence anchors differ from its event")
                for payload_key, column in (
                    ("edge_id", "edge_id"), ("version", "version"), ("source_node_id", "source_node_id"),
                    ("target_node_id", "target_node_id"), ("relation_type", "relation_type"),
                    ("status", "status"), ("weight", "weight"), ("confidence", "confidence"),
                    ("model_version", "model_version"),
                ):
                    if payload[payload_key] != row[column]:
                        errors.append(f"edge {version_id} field {payload_key} differs from its event")
                if payload.get("properties", {}) != _decode(row["properties_json"]):
                    errors.append(f"edge {version_id} properties differ from its event")
            for version_id, version in folded_versions.items():
                if version["node_id"] not in actual_nodes:
                    errors.append(f"version {version_id} references a missing node")
            for attachment_id, payload in folded_attachments.items():
                row = actual_attachments.get(attachment_id)
                if not row:
                    errors.append(f"attachment {attachment_id} exists in the event fold but not in canonical records")
                    continue
                for payload_key, column in (
                    ("content_hash", "content_hash"), ("object_key", "object_key"), ("media_type", "media_type"),
                    ("byte_length", "byte_length"),
                ):
                    if payload[payload_key] != row[column]:
                        errors.append(f"attachment {attachment_id} field {payload_key} differs from its event")
                if payload.get("metadata", {}) != _decode(row["metadata_json"]):
                    errors.append(f"attachment {attachment_id} metadata differs from its event")
        if folded_nodes != actual_nodes:
            errors.append("folded node identities/facets/security differ from canonical records")
        if folded_versions != actual_versions:
            errors.append("folded node versions differ from canonical records")
        if set(folded_edges) != set(actual_edges):
            errors.append("folded edge versions differ from canonical records")
        if set(folded_attachments) != set(actual_attachments):
            errors.append("folded attachments differ from canonical records")
        return {
            "workspace_id": workspace_id, "valid": not errors, "errors": errors,
            "nodes": len(folded_nodes), "node_versions": len(folded_versions),
            "edge_versions": len(folded_edges), "attachments": len(folded_attachments),
            "through_event_offset": self.last_event_offset(),
        }

    def last_event_offset(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COALESCE(MAX(event_offset), 0) FROM events").fetchone()[0])

    def outbox_status(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status,COUNT(*) AS count FROM outbox GROUP BY status").fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def claim_outbox(self, *, limit: int = 100, lease_seconds: int = 30) -> list[dict[str, Any]]:
        """Lease pending event publications; redelivery is deliberately safe.

        Consumers must use the immutable ``event_id`` as their own idempotency
        key.  A worker crash can therefore cause at-least-once delivery, never a
        silently lost event.
        """

        now = datetime.now(UTC)
        lease_until = datetime.fromtimestamp(now.timestamp() + lease_seconds, UTC).isoformat()
        now_text = now.isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE outbox SET status='pending', lease_until=NULL WHERE status='inflight' AND lease_until < ?",
                (now_text,),
            )
            rows = conn.execute(
                """SELECT o.*,e.event_id FROM outbox o JOIN events e ON e.event_offset=o.event_offset
                    WHERE o.status='pending' AND o.available_at<=? ORDER BY o.event_offset LIMIT ?""",
                (now_text, limit),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                conn.execute(
                    "UPDATE outbox SET status='inflight', attempts=attempts+1, lease_until=? WHERE event_offset=?",
                    (lease_until, row["event_offset"]),
                )
                item = dict(row)
                item["payload"] = _decode(item.pop("payload_json"))
                claimed.append(item)
            return claimed

    def mark_outbox_published(self, event_offset: int) -> None:
        with self.transaction() as conn:
            updated = conn.execute(
                "UPDATE outbox SET status='published', published_at=?, lease_until=NULL WHERE event_offset=? AND status='inflight'",
                (_now(), event_offset),
            ).rowcount
            if not updated:
                raise InvariantViolation(f"outbox event {event_offset} is not leased")

    def release_outbox(self, event_offset: int) -> None:
        with self.transaction() as conn:
            updated = conn.execute(
                "UPDATE outbox SET status='pending', lease_until=NULL WHERE event_offset=? AND status='inflight'",
                (event_offset,),
            ).rowcount
            if not updated:
                raise InvariantViolation(f"outbox event {event_offset} is not leased")

    # ---------------------------------------------------------- write helpers
    def ingest(
        self,
        *,
        workspace_id: str,
        source: dict[str, Any],
        attachment: dict[str, Any],
        atoms: Sequence[dict[str, Any]],
        actor: str,
        visibility: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Append one ingestion envelope, atom versions, and structural chain atomically.

        The method is the embedded equivalent of a PostgreSQL transaction plus
        transactional outbox write. If a later atom or edge fails, the entire
        capture rolls back; if the process dies after commit, the event stream
        and outbox retain enough information for replay and redelivery.
        """

        # Stable IDs are essential: a redelivered HTTP request must resolve to
        # the original ingestion rather than fail because a random ID changed
        # the first event's payload hash.
        stable_seed = f"{workspace_id}:{idempotency_key}" if idempotency_key else None
        ingestion_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        attachment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"attachment:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        correlation_id = ingestion_id
        stream_id = f"workspace:{workspace_id}"
        with self.transaction() as conn:
            accepted = self._append_event(
                conn,
                stream_id=stream_id,
                event_type="ingestion.accepted",
                payload={
                    "ingestion_id": ingestion_id,
                    "workspace_id": workspace_id,
                    "source": source,
                    "content_hash": attachment["content_hash"],
                },
                actor=actor,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            if accepted.duplicate:
                row = conn.execute(
                    "SELECT * FROM ingestions WHERE accepted_event_offset = ?", (accepted.offset,)
                ).fetchone()
                if not row:
                    raise InvariantViolation("duplicate ingestion event has no ingestion projection")
                return self._ingestion_row(row)
            conn.execute(
                """INSERT INTO ingestions(
                    ingestion_id, workspace_id, source_json, attachment_id, accepted_event_offset,
                    atom_count, parsing_status, indexing_status, consolidation_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'running', 'pending', 'pending', ?)""",
                (ingestion_id, workspace_id, _json(source), attachment_id, accepted.offset, len(atoms), _now()),
            )
            attachment_event = self._append_event(
                conn,
                stream_id=stream_id,
                event_type="attachment.recorded",
                payload={
                    "attachment_id": attachment_id, "ingestion_id": ingestion_id, "workspace_id": workspace_id,
                    "content_hash": attachment["content_hash"], "object_key": attachment["object_key"],
                    "media_type": attachment["media_type"], "byte_length": attachment["byte_length"],
                    "metadata": attachment.get("metadata", {}),
                },
                actor=actor,
                causation_id=accepted.event_id,
                correlation_id=correlation_id,
            )
            conn.execute(
                """INSERT INTO attachments(
                    attachment_id, workspace_id, content_hash, object_key, media_type, byte_length,
                    created_event_offset, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attachment_id, workspace_id, attachment["content_hash"], attachment["object_key"],
                    attachment["media_type"], attachment["byte_length"], attachment_event.offset,
                    _json(attachment.get("metadata", {})),
                ),
            )
            created: list[dict[str, Any]] = []
            for atom in atoms:
                ordinal = atom["ordinal"]
                node_id = (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"node:{stable_seed}:{ordinal}"))
                    if stable_seed else str(uuid.uuid4())
                )
                node_event = self._append_event(
                    conn,
                    stream_id=stream_id,
                    event_type="node.created",
                    payload={
                        "node_id": node_id, "workspace_id": workspace_id, "facets": ["atom"],
                        "security": {"visibility": visibility, "origin": source.get("uri"), "actor": actor},
                    },
                    actor=actor,
                    causation_id=accepted.event_id,
                    correlation_id=correlation_id,
                )
                security = {"visibility": visibility, "origin": source.get("uri"), "actor": actor}
                conn.execute(
                    "INSERT INTO nodes(node_id, workspace_id, facets_json, security_json, created_event_offset) VALUES (?, ?, ?, ?, ?)",
                    (node_id, workspace_id, _json(["atom"]), _json(security), node_event.offset),
                )
                version_id = (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"atom-version:{stable_seed}:{ordinal}:1"))
                    if stable_seed else str(uuid.uuid4())
                )
                properties = {
                    "ingestion_id": ingestion_id,
                    "attachment_id": attachment_id,
                    "source_start": atom["start"],
                    "source_end": atom["end"],
                    "ordinal": atom["ordinal"],
                    "parser_location": atom["parser_location"],
                    "source": source,
                }
                version_event = self._append_event(
                    conn,
                    stream_id=f"node:{node_id}",
                    event_type="node.versioned",
                    payload={
                        "node_id": node_id, "atom_version_id": version_id, "version": 1,
                        "content": atom["content"], "properties": properties,
                    },
                    actor=actor,
                    causation_id=node_event.event_id,
                    correlation_id=correlation_id,
                )
                conn.execute(
                    """INSERT INTO node_versions(atom_version_id, node_id, version, content, properties_json,
                       created_event_offset, content_hash) VALUES (?, ?, 1, ?, ?, ?, ?)""",
                    (version_id, node_id, atom["content"], _json(properties), version_event.offset, _digest(atom["content"])),
                )
                conn.execute(
                    """INSERT INTO hot_inbox(atom_version_id, node_id, workspace_id, content,
                        visible_from_event, facets_json, security_json) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (version_id, node_id, workspace_id, atom["content"], version_event.offset, _json(["atom"]), _json(security)),
                )
                created.append({"node_id": node_id, "atom_version_id": version_id, "event_offset": version_event.offset, **properties})
            for previous, following in zip(created, created[1:]):
                self._insert_edge(
                    conn,
                    workspace_id=workspace_id,
                    source_node_id=previous["node_id"],
                    target_node_id=following["node_id"],
                    relation_type="NEXT",
                    evidence_atom_version_ids=[previous["atom_version_id"], following["atom_version_id"]],
                    actor=actor,
                    model_version="structural-v1",
                    confidence=1.0,
                    weight=1.0,
                    status="trusted",
                    properties={"ingestion_id": ingestion_id, "structural": True},
                    causation_id=accepted.event_id,
                    correlation_id=correlation_id,
                )
            finished = self._append_event(
                conn,
                stream_id=stream_id,
                event_type="ingestion.atomized",
                payload={"ingestion_id": ingestion_id, "atom_count": len(created)},
                actor="system",
                causation_id=accepted.event_id,
                correlation_id=correlation_id,
            )
            conn.execute(
                """UPDATE ingestions SET parsing_status='completed', indexing_status='lexical_ready',
                    consolidation_status='pending' WHERE ingestion_id=?""",
                (ingestion_id,),
            )
            self._set_projection(conn, "hot_inbox", workspace_id, finished.offset)
            return {
                "ingestion_id": ingestion_id,
                "workspace_id": workspace_id,
                "atom_count": len(created),
                "accepted_event_offset": accepted.offset,
                "atomized_event_offset": finished.offset,
                "parsing_status": "completed",
                "indexing_status": "lexical_ready",
                "consolidation_status": "pending",
            }

    def _insert_edge(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        evidence_atom_version_ids: list[str],
        actor: str,
        model_version: str,
        confidence: float,
        weight: float,
        status: str,
        properties: dict[str, Any],
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Write one immutable edge version and all of its evidence anchors.

        Structural relations may be created by ingestion, but evidence-bearing
        derived relations must name source atom versions. The workspace checks
        here prevent cross-tenant edges and out-of-scope evidence references.
        """
        if relation_type not in ALLOWED_RELATIONS:
            raise InvariantViolation(
                f"unsupported relation_type {relation_type!r}; use one of {sorted(ALLOWED_RELATIONS)}"
            )
        self._assert_node_workspace(conn, source_node_id, workspace_id)
        self._assert_node_workspace(conn, target_node_id, workspace_id)
        if relation_type not in STRUCTURAL_RELATIONS and not evidence_atom_version_ids:
            raise InvariantViolation("typed evidence edges require at least one evidence anchor")
        for version_id in evidence_atom_version_ids:
            self._assert_atom_version(conn, version_id, workspace_id)
        edge_id = str(uuid.uuid4())
        edge_version_id = str(uuid.uuid4())
        event = self._append_event(
            conn,
            stream_id=f"edge:{edge_id}",
            event_type="edge.versioned",
            payload={
                "edge_id": edge_id, "edge_version_id": edge_version_id, "workspace_id": workspace_id,
                "version": 1, "source_node_id": source_node_id, "target_node_id": target_node_id,
                "relation_type": relation_type, "status": status, "weight": weight, "confidence": confidence,
                "model_version": model_version, "properties": properties,
                "evidence_atom_version_ids": evidence_atom_version_ids,
            },
            actor=actor,
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        conn.execute(
            """INSERT INTO edge_versions(
                edge_version_id, edge_id, version, workspace_id, source_node_id, target_node_id,
                relation_type, weight, confidence, status, valid_from_event, valid_to_event,
                model_version, properties_json, created_event_offset
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (
                edge_version_id, edge_id, workspace_id, source_node_id, target_node_id, relation_type,
                weight, confidence, status, event.offset, model_version, _json(properties), event.offset,
            ),
        )
        for source_version_id in evidence_atom_version_ids:
            anchor_id = str(uuid.uuid4())
            source = conn.execute(
                "SELECT properties_json, content FROM node_versions WHERE atom_version_id=?", (source_version_id,)
            ).fetchone()
            source_properties = _decode(source["properties_json"])
            conn.execute(
                """INSERT INTO evidence_anchors(
                    anchor_id, target_kind, target_id, source_atom_version_id, source_start, source_end,
                    parser_location, quote_hash, created_event_offset
                ) VALUES (?, 'edge_version', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    anchor_id, edge_version_id, source_version_id, source_properties.get("source_start"),
                    source_properties.get("source_end"), source_properties.get("parser_location"),
                    _digest(source["content"]), event.offset,
                ),
            )
        return {"edge_id": edge_id, "edge_version_id": edge_version_id, "event_offset": event.offset}

    def create_edge(self, **kwargs: Any) -> dict[str, Any]:
        with self.transaction() as conn:
            return self._insert_edge(conn, **kwargs)

    def _revise_edge_strength(
        self,
        conn: sqlite3.Connection,
        *,
        edge_version_id: str,
        workspace_id: str,
        weight: float,
        confidence: float,
        evidence_atom_version_ids: list[str],
        actor: str,
        model_version: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Append a successor version of a trusted edge; never overwrite it."""

        current = conn.execute("SELECT * FROM edge_versions WHERE edge_version_id=?", (edge_version_id,)).fetchone()
        if not current or current["workspace_id"] != workspace_id:
            raise NotFoundError(f"edge version {edge_version_id} was not found in this workspace")
        latest = conn.execute(
            "SELECT * FROM edge_versions WHERE edge_id=? ORDER BY version DESC LIMIT 1", (current["edge_id"],)
        ).fetchone()
        if latest["edge_version_id"] != edge_version_id:
            raise InvariantViolation("edge-strength proposal must target the current edge version")
        for atom_version_id in evidence_atom_version_ids:
            self._assert_atom_version(conn, atom_version_id, workspace_id)
        successor_id = str(uuid.uuid4())
        next_version = int(latest["version"]) + 1
        merged_properties = {**_decode(latest["properties_json"]), **properties, "revises_edge_version_id": edge_version_id}
        event = self._append_event(
            conn,
            stream_id=f"edge:{latest['edge_id']}",
            event_type="edge.versioned",
            payload={
                "edge_id": latest["edge_id"], "edge_version_id": successor_id, "workspace_id": workspace_id,
                "version": next_version, "source_node_id": latest["source_node_id"], "target_node_id": latest["target_node_id"],
                "relation_type": latest["relation_type"], "status": "trusted", "weight": weight, "confidence": confidence,
                "model_version": model_version, "properties": merged_properties,
                "evidence_atom_version_ids": evidence_atom_version_ids,
            },
            actor=actor,
        )
        conn.execute("UPDATE edge_versions SET valid_to_event=? WHERE edge_version_id=?", (event.offset, edge_version_id))
        conn.execute(
            """INSERT INTO edge_versions(
                edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,
                confidence,status,valid_from_event,valid_to_event,model_version,properties_json,created_event_offset
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'trusted', ?, NULL, ?, ?, ?)""",
            (
                successor_id, latest["edge_id"], next_version, workspace_id, latest["source_node_id"], latest["target_node_id"],
                latest["relation_type"], weight, confidence, event.offset, model_version, _json(merged_properties), event.offset,
            ),
        )
        for source_version_id in evidence_atom_version_ids:
            source = conn.execute("SELECT properties_json,content FROM node_versions WHERE atom_version_id=?", (source_version_id,)).fetchone()
            source_properties = _decode(source["properties_json"])
            conn.execute(
                """INSERT INTO evidence_anchors VALUES (?, 'edge_version', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), successor_id, source_version_id, source_properties.get("source_start"),
                    source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source["content"]), event.offset,
                ),
            )
        return {"edge_id": latest["edge_id"], "edge_version_id": successor_id, "version": next_version, "event_offset": event.offset}

    def edit_node(
        self,
        *,
        node_id: str,
        content: str,
        properties: dict[str, Any],
        actor: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            node = self._node(conn, node_id)
            if idempotency_key:
                existing = conn.execute(
                    "SELECT event_type,payload_json,event_offset FROM events WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
                if existing:
                    payload = _decode(existing["payload_json"])
                    if (
                        existing["event_type"] != "node.versioned" or payload.get("node_id") != node_id
                        or payload.get("content") != content or payload.get("patch") != properties
                    ):
                        raise IdempotencyConflict("idempotency key was reused with a different node edit")
                    duplicate = conn.execute(
                        "SELECT * FROM node_versions WHERE created_event_offset=?", (existing["event_offset"],)
                    ).fetchone()
                    return self._node_version_row(duplicate, node)
            current = self._current_version(conn, node_id)
            merged_properties = {**_decode(current["properties_json"]), **properties, "predecessor_atom_version_id": current["atom_version_id"]}
            version = current["version"] + 1
            version_id = (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"node-version:{node_id}:{idempotency_key}"))
                if idempotency_key else str(uuid.uuid4())
            )
            event = self._append_event(
                conn,
                stream_id=f"node:{node_id}",
                event_type="node.versioned",
                payload={
                    "node_id": node_id, "atom_version_id": version_id, "version": version,
                    "content": content, "properties": merged_properties, "patch": properties,
                    "predecessor": current["atom_version_id"],
                },
                actor=actor,
                causation_id=None,
                idempotency_key=idempotency_key,
            )
            if event.duplicate:
                duplicate = conn.execute(
                    "SELECT * FROM node_versions WHERE created_event_offset=?", (event.offset,)
                ).fetchone()
                return self._node_version_row(duplicate, node)
            conn.execute(
                """INSERT INTO node_versions(atom_version_id,node_id,version,content,properties_json,created_event_offset,content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (version_id, node_id, version, content, _json(merged_properties), event.offset, _digest(content)),
            )
            # This is a rebuildable index: the old current version is deliberately removed from it,
            # but remains immutable and searchable in historical/replay views.
            conn.execute("DELETE FROM hot_inbox WHERE node_id=?", (node_id,))
            conn.execute(
                "INSERT INTO hot_inbox VALUES (?, ?, ?, ?, ?, ?, ?)",
                (version_id, node_id, node["workspace_id"], content, event.offset, node["facets_json"], node["security_json"]),
            )
            self._set_projection(conn, "hot_inbox", node["workspace_id"], event.offset)
            return self._node_version_row(
                conn.execute("SELECT * FROM node_versions WHERE atom_version_id=?", (version_id,)).fetchone(), node
            )

    def split_node(
        self,
        *,
        node_id: str,
        parts: list[str],
        actor: str,
        idempotency_key: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            parent = self._node(conn, node_id)
            parent_version = self._current_version(conn, node_id)
            # The split's idempotency key belongs to its explicit spine marker; children remain stable.
            marker = self._append_event(
                conn,
                stream_id=f"node:{node_id}",
                event_type="node.split_requested",
                payload={"node_id": node_id, "parts_hash": _digest(parts)},
                actor=actor,
                idempotency_key=idempotency_key,
            )
            if marker.duplicate:
                rows = conn.execute(
                    """SELECT nv.*, n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id
                    WHERE json_extract(nv.properties_json, '$.split_marker_event')=? ORDER BY nv.version""",
                    (marker.offset,),
                ).fetchall()
                return [self._node_version_row(row, row) for row in rows]
            children: list[dict[str, Any]] = []
            for ordinal, part in enumerate(parts):
                child_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
                node_event = self._append_event(
                    conn, stream_id=f"workspace:{parent['workspace_id']}", event_type="node.created",
                    payload={
                        "node_id": child_id, "workspace_id": parent["workspace_id"], "facets": ["atom"],
                        "security": _decode(parent["security_json"]),
                    },
                    actor=actor, causation_id=marker.event_id,
                )
                conn.execute(
                    "INSERT INTO nodes VALUES (?, ?, ?, ?, ?)",
                    (child_id, parent["workspace_id"], _json(["atom"]), parent["security_json"], node_event.offset),
                )
                props = {
                    "split_from_node_id": node_id, "split_from_atom_version_id": parent_version["atom_version_id"],
                    "split_marker_event": marker.offset, "ordinal": ordinal,
                }
                version_event = self._append_event(
                    conn, stream_id=f"node:{child_id}", event_type="node.versioned",
                    payload={
                        "node_id": child_id, "atom_version_id": version_id, "version": 1, "content": part,
                        "properties": props, "split_from": parent_version["atom_version_id"],
                    },
                    actor=actor, causation_id=node_event.event_id,
                )
                conn.execute(
                    "INSERT INTO node_versions VALUES (?, ?, 1, ?, ?, ?, ?)",
                    (version_id, child_id, part, _json(props), version_event.offset, _digest(part)),
                )
                conn.execute(
                    "INSERT INTO hot_inbox VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (version_id, child_id, parent["workspace_id"], part, version_event.offset, _json(["atom"]), parent["security_json"]),
                )
                self._insert_edge(
                    conn, workspace_id=parent["workspace_id"], source_node_id=child_id, target_node_id=node_id,
                    relation_type="CHILD_OF", evidence_atom_version_ids=[parent_version["atom_version_id"]], actor=actor,
                    model_version="lineage-v1", confidence=1.0, weight=1.0, status="trusted",
                    properties={"operation": "split", "marker_event": marker.offset}, causation_id=marker.event_id,
                )
                children.append({"node_id": child_id, "atom_version_id": version_id, "content": part})
            self._set_projection(conn, "hot_inbox", parent["workspace_id"], self.last_event_offset_in(conn))
            return children

    def create_alias(
        self,
        *,
        source_node_id: str,
        target_node_id: str,
        actor: str,
        evidence_atom_version_ids: list[str],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            source = self._node(conn, source_node_id)
            self._assert_node_workspace(conn, target_node_id, source["workspace_id"])
            if not evidence_atom_version_ids:
                evidence_atom_version_ids = [self._current_version(conn, source_node_id)["atom_version_id"]]
            # The edge event itself can be made idempotent by a preceding operation event.
            operation = self._append_event(
                conn, stream_id=f"node:{source_node_id}", event_type="node.aliased",
                payload={"source_node_id": source_node_id, "target_node_id": target_node_id}, actor=actor,
                idempotency_key=idempotency_key,
            )
            if operation.duplicate:
                row = conn.execute(
                    """SELECT * FROM edge_versions WHERE source_node_id=? AND target_node_id=?
                        AND relation_type='alias_of' ORDER BY created_event_offset DESC LIMIT 1""",
                    (source_node_id, target_node_id),
                ).fetchone()
                return self._edge_row(conn, row)
            return self._insert_edge(
                conn, workspace_id=source["workspace_id"], source_node_id=source_node_id,
                target_node_id=target_node_id, relation_type="alias_of", evidence_atom_version_ids=evidence_atom_version_ids,
                actor=actor, model_version="manual", confidence=1.0, weight=1.0, status="trusted",
                properties={"operation_event": operation.offset}, causation_id=operation.event_id,
            )

    # ------------------------------------------------------------ projections
    def _set_projection(self, conn: sqlite3.Connection, name: str, workspace_id: str, offset: int) -> None:
        row = conn.execute(
            "SELECT revision FROM projection_revisions WHERE projection_name=? AND workspace_id=?", (name, workspace_id)
        ).fetchone()
        revision = (row["revision"] + 1) if row else 1
        conn.execute(
            """INSERT INTO projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(projection_name,workspace_id) DO UPDATE SET
                    last_applied_event=excluded.last_applied_event, revision=excluded.revision, updated_at=excluded.updated_at""",
            (name, workspace_id, offset, revision, _now()),
        )

    def reconcile_hot_inbox(self, workspace_id: str | None = None, *, actor: str = "system") -> dict[str, Any]:
        """Rebuild only the lexical projection from immutable node versions.

        This operation is deliberately safe to repeat. It never touches the
        Spine, attachments, edge history, proposals, or archived versions.
        """

        with self.transaction() as conn:
            before = self._append_event(
                conn, stream_id="admin:projections", event_type="projection.reconcile_started",
                payload={"projection": "hot_inbox", "workspace_id": workspace_id}, actor=actor,
            )
            if workspace_id:
                conn.execute("DELETE FROM hot_inbox WHERE workspace_id=?", (workspace_id,))
                workspaces = [workspace_id]
            else:
                conn.execute("DELETE FROM hot_inbox")
                workspaces = [row[0] for row in conn.execute("SELECT DISTINCT workspace_id FROM nodes")]
            inserted = 0
            for workspace in workspaces:
                rows = self._current_atom_rows(conn, workspace_id=workspace, as_of_event=None)
                for row in rows:
                    conn.execute(
                        "INSERT INTO hot_inbox VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["atom_version_id"], row["node_id"], workspace, row["content"],
                            row["created_event_offset"], row["facets_json"], row["security_json"],
                        ),
                    )
                    inserted += 1
                self._set_projection(conn, "hot_inbox", workspace, before.offset)
            completed = self._append_event(
                conn, stream_id="admin:projections", event_type="projection.reconciled",
                payload={"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted}, actor=actor,
                causation_id=before.event_id,
            )
            for workspace in workspaces:
                self._set_projection(conn, "hot_inbox", workspace, completed.offset)
            return {"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted, "event_offset": completed.offset}

    def projection_status(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM projection_revisions"
        args: tuple[Any, ...] = ()
        if workspace_id:
            sql += " WHERE workspace_id=?"
            args = (workspace_id,)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    # --------------------------------------------------------------- reads
    def get_ingestion(self, ingestion_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ingestions WHERE ingestion_id=?", (ingestion_id,)).fetchone()
        if not row:
            raise NotFoundError(f"ingestion {ingestion_id} was not found")
        return self._ingestion_row(row)

    def get_attachment(self, attachment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone()
        if not row:
            raise NotFoundError(f"attachment {attachment_id} was not found")
        result = dict(row)
        result["metadata"] = _decode(result.pop("metadata_json"))
        return result

    @staticmethod
    def _ingestion_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["source"] = _decode(result.pop("source_json"))
        return result

    def node_history(self, node_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            node = self._node(conn, node_id)
            rows = conn.execute("SELECT * FROM node_versions WHERE node_id=? ORDER BY version", (node_id,)).fetchall()
        return [self._node_version_row(row, node) for row in rows]

    def get_node(self, node_id: str, as_of_event: int | None = None) -> dict[str, Any]:
        with self._connect() as conn:
            node = self._node(conn, node_id)
            version = self._current_version(conn, node_id, as_of_event)
        return self._node_version_row(version, node)

    def queryable_atoms(self, workspace_id: str | None, as_of_event: int | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = self._current_atom_rows(conn, workspace_id=workspace_id, as_of_event=as_of_event)
        return [self._node_version_row(row, row) for row in rows]

    def workspace_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT workspace_id FROM nodes ORDER BY workspace_id").fetchall()
        return [row["workspace_id"] for row in rows]

    def current_nodes(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        """Return all current generic nodes, including promoted Holons and claims."""

        with self._connect() as conn:
            event_clause = ""
            args: list[Any] = [workspace_id]
            if as_of_event is not None:
                event_clause = " AND nv2.created_event_offset<=?"
                args.append(as_of_event)
            rows = conn.execute(
                f"""SELECT nv.*,n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id WHERE n.workspace_id=?
                    AND nv.created_event_offset=(
                        SELECT MAX(nv2.created_event_offset) FROM node_versions nv2
                        WHERE nv2.node_id=nv.node_id {event_clause}
                    ) ORDER BY nv.created_event_offset DESC""",
                args,
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                node = self._node_version_row(row, row)
                anchors = conn.execute(
                    "SELECT * FROM evidence_anchors WHERE target_kind='node_version' AND target_id=?",
                    (node["atom_version_id"],),
                ).fetchall()
                node["evidence_anchors"] = [dict(anchor) for anchor in anchors]
                result.append(node)
            return result

    def current_nodes_by_facet(
        self,
        workspace_id: str,
        facet: str,
        *,
        as_of_event: int | None = None,
        limit: int = 256,
    ) -> list[dict[str, Any]]:
        """Return a bounded current-node projection for one facet.

        Query paths use this instead of loading every derived node merely to
        find schemas or hierarchy summaries.  SQLite's JSON support varies by
        distribution, so the indexed workspace selection remains portable and
        the facet predicate is intentionally conservative.
        """

        limit = max(1, min(int(limit), 2_000))
        with self._connect() as conn:
            event_clause = ""
            args: list[Any] = [workspace_id, f'%"{facet}"%', limit]
            if as_of_event is not None:
                event_clause = " AND nv2.created_event_offset<=?"
                # The event clause appears before LIMIT in the SQL.
                args = [workspace_id, f'%"{facet}"%', as_of_event, limit]
            rows = conn.execute(
                f"""SELECT nv.*,n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id
                    WHERE n.workspace_id=? AND n.facets_json LIKE ?
                    AND nv.created_event_offset=(
                        SELECT MAX(nv2.created_event_offset) FROM node_versions nv2
                        WHERE nv2.node_id=nv.node_id {event_clause}
                    ) ORDER BY nv.created_event_offset DESC LIMIT ?""",
                args,
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                node = self._node_version_row(row, row)
                anchors = conn.execute(
                    "SELECT * FROM evidence_anchors WHERE target_kind='node_version' AND target_id=? ORDER BY anchor_id",
                    (node["atom_version_id"],),
                ).fetchall()
                node["evidence_anchors"] = [dict(anchor) for anchor in anchors]
                result.append(node)
            return result

    def current_nodes_by_hierarchy_keys(
        self,
        workspace_id: str,
        hierarchy_keys: Sequence[str],
        *,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Look up known hierarchy materializations without a workspace scan."""

        keys = [str(key) for key in dict.fromkeys(hierarchy_keys) if key]
        if not keys:
            return []
        limit = max(1, min(int(limit), 2_000))
        key_clause = " OR ".join("nv.properties_json LIKE ?" for _ in keys)
        values: list[Any] = [workspace_id, *[f'%"hierarchy_key":"{key}"%' for key in keys], limit]
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT nv.*,n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id
                    WHERE n.workspace_id=? AND ({key_clause})
                      AND nv.created_event_offset=(
                        SELECT MAX(nv2.created_event_offset) FROM node_versions nv2
                        WHERE nv2.node_id=nv.node_id
                    ) ORDER BY nv.created_event_offset DESC LIMIT ?""",
                values,
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                node = self._node_version_row(row, row)
                anchors = conn.execute(
                    "SELECT * FROM evidence_anchors WHERE target_kind='node_version' AND target_id=? ORDER BY anchor_id",
                    (node["atom_version_id"],),
                ).fetchall()
                node["evidence_anchors"] = [dict(anchor) for anchor in anchors]
                result.append(node)
            return result

    def _current_atom_rows(
        self, conn: sqlite3.Connection, *, workspace_id: str | None, as_of_event: int | None
    ) -> list[sqlite3.Row]:
        where = ["n.facets_json LIKE '%\"atom\"%'"]
        args: list[Any] = []
        if workspace_id:
            where.append("n.workspace_id=?")
            args.append(workspace_id)
        event_clause = ""
        if as_of_event is not None:
            event_clause = " AND nv2.created_event_offset <= ?"
            args.append(as_of_event)
        sql = f"""
            SELECT nv.*, n.workspace_id, n.facets_json, n.security_json
            FROM node_versions nv
            JOIN nodes n ON n.node_id=nv.node_id
            WHERE {' AND '.join(where)}
              AND nv.created_event_offset=(
                SELECT MAX(nv2.created_event_offset) FROM node_versions nv2
                WHERE nv2.node_id=nv.node_id {event_clause}
              )
            ORDER BY nv.created_event_offset DESC
        """
        # Parameters are used once for outer workspace and once only inside event clause.
        # The event condition occurs in the subquery after workspace filtering, so its value
        # must follow outer where arguments.
        return conn.execute(sql, args).fetchall()

    @staticmethod
    def _node_version_row(row: sqlite3.Row, node: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["properties"] = _decode(result.pop("properties_json"))
        facets = result.pop("facets_json", None) or node["facets_json"]
        security = result.pop("security_json", None) or node["security_json"]
        result["facets"] = _decode(facets, [])
        result["security"] = _decode(security)
        return result

    def current_edges(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        """Return the latest trusted edge version visible in a workspace/time view."""
        with self._connect() as conn:
            clause = ""
            args: list[Any] = [workspace_id]
            if as_of_event is not None:
                clause = " AND ev2.created_event_offset <= ?"
                args.append(as_of_event)
            rows = conn.execute(
                f"""SELECT ev.* FROM edge_versions ev
                    WHERE ev.workspace_id=? AND ev.created_event_offset=(
                        SELECT MAX(ev2.created_event_offset) FROM edge_versions ev2
                        WHERE ev2.edge_id=ev.edge_id {clause}
                    ) AND ev.status='trusted'""",
                args,
            ).fetchall()
            return [self._edge_row(conn, row) for row in rows]

    def neighbor_edges(
        self,
        workspace_id: str,
        node_ids: Sequence[str],
        *,
        as_of_event: int | None = None,
        limit: int = 512,
    ) -> list[dict[str, Any]]:
        """Return a bounded current edge neighbourhood without a workspace scan."""

        selected = list(dict.fromkeys(str(node_id) for node_id in node_ids if node_id))[:512]
        if not selected:
            return []
        limit = max(1, min(int(limit), 2_000))
        marks = ",".join("?" for _ in selected)
        event_clause = ""
        values: list[Any] = [workspace_id, *selected, *selected]
        if as_of_event is not None:
            event_clause = " AND ev2.created_event_offset<=?"
            values.append(as_of_event)
        values.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT ev.* FROM edge_versions ev
                    WHERE ev.workspace_id=?
                      AND (ev.source_node_id IN ({marks}) OR ev.target_node_id IN ({marks}))
                      AND ev.created_event_offset=(
                        SELECT MAX(ev2.created_event_offset) FROM edge_versions ev2
                        WHERE ev2.edge_id=ev.edge_id {event_clause}
                      )
                      AND ev.status='trusted'
                    ORDER BY ev.created_event_offset DESC,ev.edge_version_id
                    LIMIT ?""",
                values,
            ).fetchall()
            return [self._edge_row(conn, row) for row in rows]

    def _edge_row(self, conn: sqlite3.Connection, row: sqlite3.Row | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("edge was not found")
        result = dict(row)
        result["properties"] = _decode(result.pop("properties_json"))
        anchors = conn.execute(
            "SELECT * FROM evidence_anchors WHERE target_kind='edge_version' AND target_id=? ORDER BY anchor_id",
            (result["edge_version_id"],),
        ).fetchall()
        result["evidence_anchors"] = [dict(anchor) for anchor in anchors]
        return result

    # -------------------------------------------------------------- proposals
    def create_proposal(
        self,
        *,
        workspace_id: str,
        proposal_type: str,
        candidate: dict[str, Any],
        evidence_atom_version_ids: list[str],
        confidence: float,
        model_version: str,
        actor: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            if proposal_type == "edge":
                relation_type = candidate.get("relation_type")
                if relation_type not in ALLOWED_RELATIONS:
                    raise InvariantViolation(
                        f"edge proposals require a conservative relation_type; got {relation_type!r}"
                    )
            for version_id in evidence_atom_version_ids:
                self._assert_atom_version(conn, version_id, workspace_id)
            proposal_id = (
                str(uuid.uuid5(uuid.NAMESPACE_URL, f"proposal:{workspace_id}:{idempotency_key}"))
                if idempotency_key else str(uuid.uuid4())
            )
            event = self._append_event(
                conn, stream_id=f"workspace:{workspace_id}", event_type="proposal.created",
                payload={
                    "proposal_id": proposal_id, "workspace_id": workspace_id, "proposal_type": proposal_type,
                    "candidate": candidate, "evidence_atom_version_ids": evidence_atom_version_ids,
                    "confidence": confidence, "model_version": model_version,
                },
                actor=actor, idempotency_key=idempotency_key,
            )
            if event.duplicate:
                row = conn.execute("SELECT * FROM proposals WHERE created_event_offset=?", (event.offset,)).fetchone()
                return self._proposal_row(row)
            conn.execute(
                "INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL)",
                (proposal_id, workspace_id, proposal_type, _json(candidate), _json(evidence_atom_version_ids), confidence, model_version, event.offset),
            )
            return self._proposal_row(conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone())

    def list_proposals(
        self,
        workspace_id: str,
        *,
        proposal_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["workspace_id=?"]
        args: list[Any] = [workspace_id]
        if proposal_type:
            clauses.append("proposal_type=?")
            args.append(proposal_type)
        if status:
            clauses.append("status=?")
            args.append(status)
        sql = f"SELECT * FROM proposals WHERE {' AND '.join(clauses)} ORDER BY created_event_offset DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._proposal_row(row) for row in rows]

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if not row:
            raise NotFoundError(f"proposal {proposal_id} was not found")
        return self._proposal_row(row)

    @staticmethod
    def _proposal_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("proposal was not found")
        result = dict(row)
        result["candidate"] = _decode(result.pop("candidate_json"))
        result["evidence_atom_version_ids"] = _decode(result.pop("evidence_json"), [])
        return result

    def decide_proposal(
        self, *, proposal_id: str, decision: str, actor: str, reason: str | None, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        if decision not in {"promoted", "rejected"}:
            raise ValueError("decision must be promoted or rejected")
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not row:
                raise NotFoundError(f"proposal {proposal_id} was not found")
            if row["status"] != "pending":
                if row["status"] == decision:
                    return self._proposal_row(row)
                raise InvariantViolation(f"proposal is already {row['status']}")
            event = self._append_event(
                conn, stream_id=f"workspace:{row['workspace_id']}", event_type=f"proposal.{decision}",
                payload={"proposal_id": proposal_id, "reason": reason}, actor=actor, idempotency_key=idempotency_key,
            )
            if event.duplicate:
                return self._proposal_row(conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone())
            conn.execute(
                "UPDATE proposals SET status=?, decided_event_offset=?, decision_reason=? WHERE proposal_id=?",
                (decision, event.offset, reason, proposal_id),
            )
            return self._proposal_row(conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone())

    def promote_proposal(
        self, *, proposal_id: str, actor: str, reason: str | None, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        """Promote a source-backed proposal and materialize its derived object atomically."""

        with self.transaction() as conn:
            if idempotency_key:
                existing = conn.execute(
                    "SELECT event_type,payload_json FROM events WHERE idempotency_key=?", (idempotency_key,)
                ).fetchone()
                if existing:
                    if existing["event_type"] != "proposal.promoted" or _decode(existing["payload_json"]).get("proposal_id") != proposal_id:
                        raise IdempotencyConflict("idempotency key was reused for a different operation")
                    existing_proposal = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
                    if not existing_proposal:
                        raise InvariantViolation("promotion event has no proposal projection")
                    return self._proposal_row(existing_proposal)
            row = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            if not row:
                raise NotFoundError(f"proposal {proposal_id} was not found")
            proposal = self._proposal_row(row)
            if proposal["status"] != "pending":
                if proposal["status"] == "promoted":
                    return proposal
                raise InvariantViolation(f"proposal is already {proposal['status']}")
            materialized: dict[str, Any] | None = None
            candidate = proposal["candidate"]
            evidence = proposal["evidence_atom_version_ids"]
            if proposal["proposal_type"] == "edge":
                required = {"source_node_id", "target_node_id", "relation_type"}
                if not required <= candidate.keys():
                    raise InvariantViolation("edge proposal requires source_node_id, target_node_id, and relation_type")
                materialized = self._insert_edge(
                    conn,
                    workspace_id=proposal["workspace_id"],
                    source_node_id=candidate["source_node_id"], target_node_id=candidate["target_node_id"],
                    relation_type=candidate["relation_type"], evidence_atom_version_ids=evidence, actor=actor,
                    model_version=proposal["model_version"], confidence=proposal["confidence"],
                    weight=float(candidate.get("weight", 1.0)), status="trusted",
                    properties={**candidate.get("properties", {}), "proposal_id": proposal_id},
                )
            elif proposal["proposal_type"] == "edge_strength":
                required = {"edge_version_id", "weight", "confidence"}
                if not required <= candidate.keys():
                    raise InvariantViolation("edge_strength proposal requires edge_version_id, weight, and confidence")
                materialized = self._revise_edge_strength(
                    conn,
                    edge_version_id=str(candidate["edge_version_id"]),
                    workspace_id=proposal["workspace_id"],
                    weight=float(candidate["weight"]),
                    confidence=float(candidate["confidence"]),
                    evidence_atom_version_ids=evidence,
                    actor=actor,
                    model_version=proposal["model_version"],
                    properties={**candidate.get("properties", {}), "proposal_id": proposal_id},
                )
            else:
                content = str(candidate.get("content") or candidate.get("summary") or candidate.get("name") or _json(candidate))
                facet = "claim" if proposal["proposal_type"] == "contradiction_resolution" else proposal["proposal_type"]
                materialized = self._insert_derived_node(
                    conn,
                    workspace_id=proposal["workspace_id"], facets=[facet], content=content,
                    properties={**candidate, "proposal_id": proposal_id, "model_version": proposal["model_version"]},
                    evidence_atom_version_ids=evidence, actor=actor,
                )
            decision = self._append_event(
                conn, stream_id=f"workspace:{proposal['workspace_id']}", event_type="proposal.promoted",
                payload={"proposal_id": proposal_id, "reason": reason, "materialized": materialized},
                actor=actor, idempotency_key=idempotency_key,
            )
            conn.execute(
                "UPDATE proposals SET status='promoted', decided_event_offset=?, decision_reason=? WHERE proposal_id=?",
                (decision.offset, reason, proposal_id),
            )
            promoted = self._proposal_row(conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone())
            promoted["materialized"] = materialized
            return promoted

    def _insert_derived_node(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        facets: list[str],
        content: str,
        properties: dict[str, Any],
        evidence_atom_version_ids: list[str],
        actor: str,
    ) -> dict[str, Any]:
        if not evidence_atom_version_ids:
            raise InvariantViolation("derived nodes require evidence anchors")
        for version_id in evidence_atom_version_ids:
            self._assert_atom_version(conn, version_id, workspace_id)
        node_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        # Allocate anchors before writing the immutable node-version payload so
        # the projection can name its exact evidence anchors without a later
        # in-place update to canonical history.
        anchor_ids = [str(uuid.uuid4()) for _ in evidence_atom_version_ids]
        stored_properties = {
            **properties,
            "evidence_anchor_ids": anchor_ids,
            "evidence_atom_version_ids": list(evidence_atom_version_ids),
        }
        derived_visibility = str(properties.get("visibility", "private"))
        created = self._append_event(
            conn, stream_id=f"workspace:{workspace_id}", event_type="node.created",
            payload={"node_id": node_id, "workspace_id": workspace_id, "facets": facets, "security": {"visibility": derived_visibility, "actor": actor, "derived": True}}, actor=actor,
        )
        security = {"visibility": derived_visibility, "actor": actor, "derived": True}
        conn.execute(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?)",
            (node_id, workspace_id, _json(facets), _json(security), created.offset),
        )
        version_event = self._append_event(
            conn, stream_id=f"node:{node_id}", event_type="node.versioned",
            payload={
                "node_id": node_id, "atom_version_id": version_id, "version": 1, "derived": True,
                "content": content, "properties": stored_properties, "evidence_atom_version_ids": evidence_atom_version_ids,
            },
            actor=actor, causation_id=created.event_id,
        )
        conn.execute(
            "INSERT INTO node_versions VALUES (?, ?, 1, ?, ?, ?, ?)",
            (version_id, node_id, content, _json(stored_properties), version_event.offset, _digest(content)),
        )
        for anchor_id, source_version_id in zip(anchor_ids, evidence_atom_version_ids, strict=True):
            source = conn.execute(
                "SELECT properties_json,content FROM node_versions WHERE atom_version_id=?", (source_version_id,)
            ).fetchone()
            source_properties = _decode(source["properties_json"])
            conn.execute(
                "INSERT INTO evidence_anchors VALUES (?, 'node_version', ?, ?, ?, ?, ?, ?, ?)",
                (
                    anchor_id, version_id, source_version_id, source_properties.get("source_start"),
                    source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source["content"]), version_event.offset,
                ),
            )
        return {
            "node_id": node_id,
            "atom_version_id": version_id,
            "event_offset": version_event.offset,
            "facets": facets,
            "evidence_anchor_ids": anchor_ids,
            "evidence_atom_version_ids": list(evidence_atom_version_ids),
        }

    def create_derived_node(
        self,
        *,
        workspace_id: str,
        facets: list[str],
        content: str,
        properties: dict[str, Any],
        evidence_atom_version_ids: list[str],
        actor: str = "system",
    ) -> dict[str, Any]:
        """Materialize an evidence-backed derived projection atomically.

        This is intentionally narrower than arbitrary node creation: every
        result has immutable source anchors and remains a rebuildable view.
        """

        with self.transaction() as conn:
            return self._insert_derived_node(
                conn,
                workspace_id=workspace_id,
                facets=facets,
                content=content,
                properties=properties,
                evidence_atom_version_ids=evidence_atom_version_ids,
                actor=actor,
            )

    def ingestion_atoms(self, ingestion_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            ingestion = conn.execute("SELECT workspace_id FROM ingestions WHERE ingestion_id=?", (ingestion_id,)).fetchone()
            if not ingestion:
                raise NotFoundError(f"ingestion {ingestion_id} was not found")
            rows = conn.execute(
                """SELECT nv.*,n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id
                    WHERE n.workspace_id=? AND json_extract(nv.properties_json, '$.ingestion_id')=?
                    ORDER BY json_extract(nv.properties_json, '$.ordinal')""",
                (ingestion["workspace_id"], ingestion_id),
            ).fetchall()
        return [self._node_version_row(row, row) for row in rows]

    def set_consolidation_status(self, ingestion_id: str, status: str, *, actor: str = "system") -> None:
        if status not in {"pending", "running", "completed", "failed"}:
            raise ValueError("invalid consolidation status")
        with self.transaction() as conn:
            row = conn.execute("SELECT workspace_id FROM ingestions WHERE ingestion_id=?", (ingestion_id,)).fetchone()
            if not row:
                raise NotFoundError(f"ingestion {ingestion_id} was not found")
            event = self._append_event(
                conn, stream_id=f"workspace:{row['workspace_id']}", event_type=f"consolidation.{status}",
                payload={"ingestion_id": ingestion_id, "status": status}, actor=actor,
            )
            conn.execute("UPDATE ingestions SET consolidation_status=? WHERE ingestion_id=?", (status, ingestion_id))
            self._set_projection(conn, "consolidation", row["workspace_id"], event.offset)

    def semantic_link_exists(self, workspace_id: str, source_node_id: str, target_node_id: str) -> bool:
        relation_marks = ",".join("?" for _ in EVIDENCE_RELATIONS)
        with self._connect() as conn:
            edge = conn.execute(
                """SELECT 1 FROM edge_versions WHERE workspace_id=? AND source_node_id=? AND target_node_id=?
                    AND relation_type IN (""" + relation_marks + ") AND status IN ('trusted','proposed') LIMIT 1",
                [workspace_id, source_node_id, target_node_id, *sorted(EVIDENCE_RELATIONS)],
            ).fetchone()
            if edge:
                return True
            proposal = conn.execute(
                """SELECT 1 FROM proposals WHERE workspace_id=? AND status='pending'
                    AND proposal_type='edge' AND json_extract(candidate_json, '$.source_node_id')=?
                    AND json_extract(candidate_json, '$.target_node_id')=?
                    AND json_extract(candidate_json, '$.relation_type') IN (""" + relation_marks + ") LIMIT 1",
                [workspace_id, source_node_id, target_node_id, *sorted(EVIDENCE_RELATIONS)],
            ).fetchone()
            return bool(proposal)

    # --------------------------------------------------- evidence/query state
    def save_bundle(self, *, workspace_id: str | None, query: dict[str, Any], results: list[dict[str, Any]], sufficiency_state: str) -> dict[str, Any]:
        """Persist a query result snapshot so synthesis remains auditable."""
        with self.transaction() as conn:
            bundle_id = str(uuid.uuid4())
            event = self._append_event(
                conn, stream_id=f"workspace:{workspace_id or 'all'}", event_type="evidence_bundle.created",
                payload={"evidence_bundle_id": bundle_id, "result_count": len(results), "sufficiency_state": sufficiency_state}, actor="system",
            )
            conn.execute(
                "INSERT INTO evidence_bundles VALUES (?, ?, ?, ?, ?, ?, ?)",
                (bundle_id, workspace_id, _json(query), _json(results), sufficiency_state, event.offset, _now()),
            )
            return self.get_bundle(bundle_id, conn=conn)

    def get_bundle(self, bundle_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        if conn is not None:
            row = conn.execute("SELECT * FROM evidence_bundles WHERE evidence_bundle_id=?", (bundle_id,)).fetchone()
        else:
            with self._connect() as local:
                row = local.execute("SELECT * FROM evidence_bundles WHERE evidence_bundle_id=?", (bundle_id,)).fetchone()
        if not row:
            raise NotFoundError(f"evidence bundle {bundle_id} was not found")
        result = dict(row)
        result["query"] = _decode(result.pop("query_json"))
        result["results"] = _decode(result.pop("result_json"), [])
        return result

    def record_feedback(
        self,
        *,
        workspace_id: str,
        atom_version_id: str,
        event_type: str,
        weight: float,
        actor: str,
        evidence_bundle_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Persist auditable retrieval feedback without changing graph state."""

        if event_type not in {"selected", "opened", "cited", "accepted", "rejected"}:
            raise InvariantViolation(f"unsupported feedback event_type {event_type!r}")
        metadata = metadata or {}
        with self.transaction() as conn:
            self._assert_atom_version(conn, atom_version_id, workspace_id)
            if evidence_bundle_id:
                bundle = self.get_bundle(evidence_bundle_id, conn=conn)
                if bundle["workspace_id"] != workspace_id:
                    raise InvariantViolation("feedback bundle belongs to another workspace")
                bundle_atoms = {
                    result.get("atom_version_id")
                    for result in bundle["results"]
                    if result.get("atom_version_id")
                }
                if atom_version_id not in bundle_atoms:
                    raise InvariantViolation("feedback atom was not returned in the named evidence bundle")
            feedback_id = str(uuid.uuid4())
            event = self._append_event(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="retrieval.feedback_recorded",
                payload={
                    "feedback_id": feedback_id,
                    "workspace_id": workspace_id,
                    "evidence_bundle_id": evidence_bundle_id,
                    "atom_version_id": atom_version_id,
                    "event_type": event_type,
                    "weight": weight,
                    "metadata": metadata,
                },
                actor=actor,
                idempotency_key=idempotency_key,
            )
            if event.duplicate:
                row = conn.execute(
                    "SELECT * FROM retrieval_feedback WHERE created_event_offset=?", (event.offset,)
                ).fetchone()
                if not row:
                    raise InvariantViolation("duplicate feedback event has no projection")
                return self._feedback_row(row)
            conn.execute(
                """INSERT INTO retrieval_feedback(
                    feedback_id,workspace_id,evidence_bundle_id,atom_version_id,event_type,weight,actor,
                    metadata_json,created_event_offset,created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id, workspace_id, evidence_bundle_id, atom_version_id, event_type, weight,
                    actor, _json(metadata), event.offset, _now(),
                ),
            )
            row = conn.execute("SELECT * FROM retrieval_feedback WHERE feedback_id=?", (feedback_id,)).fetchone()
            return self._feedback_row(row)

    @staticmethod
    def _feedback_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = _decode(result.pop("metadata_json"))
        return result

    def feedback_scores(self, workspace_id: str, atom_version_ids: Sequence[str]) -> dict[str, float]:
        """Return bounded soft ranking features derived from feedback events."""

        if not atom_version_ids:
            return {}
        weights = {"selected": 0.05, "opened": 0.10, "cited": 0.20, "accepted": 0.15, "rejected": -0.20}
        marks = ",".join("?" for _ in atom_version_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT atom_version_id,event_type,SUM(weight) AS total FROM retrieval_feedback
                    WHERE workspace_id=? AND atom_version_id IN ({marks})
                    GROUP BY atom_version_id,event_type""",
                [workspace_id, *atom_version_ids],
            ).fetchall()
        result: dict[str, float] = {}
        for row in rows:
            signal = weights[row["event_type"]] * float(row["total"])
            result[row["atom_version_id"]] = max(-1.0, min(1.0, result.get(row["atom_version_id"], 0.0) + signal))
        return result

    def save_benchmark_run(
        self,
        *,
        workspace_id: str,
        benchmark_name: str,
        stages: list[str],
        result: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="benchmark.run_completed",
                payload={"benchmark_run_id": identifier, "benchmark_name": benchmark_name, "stages": stages, "result": result},
                actor=actor,
            )
            conn.execute(
                "INSERT INTO benchmark_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, workspace_id, benchmark_name, _json(stages), _json(result), event.offset, _now()),
            )
        return {
            "benchmark_run_id": identifier,
            "workspace_id": workspace_id,
            "benchmark_name": benchmark_name,
            "stages": stages,
            "result": result,
            "created_event_offset": event.offset,
        }

    def dense_vectors(
        self,
        provider_id: str,
        atom_version_ids: Sequence[str],
        *,
        index_revision: str = "embedded-current",
    ) -> dict[str, list[float]]:
        """Read a versioned local dense-index projection for the requested atoms."""

        if not atom_version_ids:
            return {}
        marks = ",".join("?" for _ in atom_version_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT atom_version_id,vector_json FROM dense_vectors WHERE provider_id=? AND index_revision=? AND atom_version_id IN ({marks})",
                [provider_id, index_revision, *atom_version_ids],
            ).fetchall()
        return {row["atom_version_id"]: [float(item) for item in _decode(row["vector_json"], [])] for row in rows}

    def upsert_dense_vectors(
        self,
        *,
        workspace_id: str,
        provider_id: str,
        vectors: dict[str, list[float]],
        actor: str = "system",
        index_revision: str = "embedded-current",
    ) -> int:
        """Update only a rebuildable vector projection; canonical atoms remain untouched."""

        if not vectors:
            return 0
        with self.transaction() as conn:
            for atom_version_id in vectors:
                self._assert_atom_version(conn, atom_version_id, workspace_id)
            event = self._append_event(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="dense_index.updated",
                payload={"provider_id": provider_id, "index_revision": index_revision, "atom_version_ids": sorted(vectors), "count": len(vectors)},
                actor=actor,
            )
            for atom_version_id, vector in vectors.items():
                conn.execute(
                    """INSERT INTO dense_vectors(atom_version_id,provider_id,index_revision,vector_json,dimension,created_event_offset,created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT DO UPDATE SET
                            vector_json=excluded.vector_json,dimension=excluded.dimension,
                            created_event_offset=excluded.created_event_offset,created_at=excluded.created_at""",
                    (atom_version_id, provider_id, index_revision, _json(vector), len(vector), event.offset, _now()),
                )
            self._set_projection(conn, f"dense_vectors:{provider_id}", workspace_id, event.offset)
            return len(vectors)

    def atom_versions(self, atom_version_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Return exact historical atom versions for anchor expansion and citations."""

        if not atom_version_ids:
            return []
        marks = ",".join("?" for _ in atom_version_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT nv.*,n.workspace_id,n.facets_json,n.security_json FROM node_versions nv
                    JOIN nodes n ON n.node_id=nv.node_id
                    WHERE nv.atom_version_id IN ({marks}) AND n.facets_json LIKE '%\"atom\"%'""",
                list(atom_version_ids),
            ).fetchall()
        by_id = {row["atom_version_id"]: self._node_version_row(row, row) for row in rows}
        return [by_id[item] for item in atom_version_ids if item in by_id]

    def save_query(self, *, workspace_id: str, name: str, query: dict[str, Any], frozen_atom_version_ids: list[str] | None, actor: str) -> dict[str, Any]:
        table = "frozen_queries" if frozen_atom_version_ids is not None else "saved_queries"
        primary_key = "frozen_query_id" if frozen_atom_version_ids is not None else "saved_query_id"
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(
                conn, stream_id=f"workspace:{workspace_id}", event_type=f"{table[:-1]}.created",
                payload={"id": identifier, "workspace_id": workspace_id, "name": name}, actor=actor,
            )
            try:
                if frozen_atom_version_ids is None:
                    conn.execute(
                        "INSERT INTO saved_queries VALUES (?, ?, ?, ?, ?)",
                        (identifier, workspace_id, name, _json(query), event.offset),
                    )
                else:
                    conn.execute(
                        "INSERT INTO frozen_queries VALUES (?, ?, ?, ?, ?, ?)",
                        (identifier, workspace_id, name, _json(query), _json(frozen_atom_version_ids), event.offset),
                    )
            except sqlite3.IntegrityError as error:
                raise InvariantViolation(f"a {table[:-1]} named {name!r} already exists in this workspace") from error
        return {primary_key: identifier, "workspace_id": workspace_id, "name": name, "query": query, "created_event_offset": event.offset, "atom_version_ids": frozen_atom_version_ids}

    # ------------------------------------------------ configuration/operations
    def register_index(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(conn, stream_id="admin:indexes", event_type="index_revision.created", payload={"index_revision_id": identifier, **payload}, actor=actor)
            conn.execute(
                "INSERT INTO index_revisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, payload["embedding_model"], payload["vector_namespace"], payload["lexical_revision"], _json(payload["normalization"]), payload["rollout_state"], event.offset),
            )
        return {"index_revision_id": identifier, "created_event_offset": event.offset, **payload}

    def register_model(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(conn, stream_id="admin:models", event_type="model.registered", payload={"model_registry_id": identifier, **payload}, actor=actor)
            try:
                conn.execute(
                    "INSERT INTO model_registry VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (identifier, payload["name"], payload["provider"], payload["purpose"], payload["version"], _json(payload["configuration"]), event.offset),
                )
            except sqlite3.IntegrityError as error:
                raise InvariantViolation("this model configuration is already registered") from error
        return {"model_registry_id": identifier, "created_event_offset": event.offset, **payload}

    def register_manifest(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(conn, stream_id="admin:experiments", event_type="experiment_manifest.created", payload={"manifest_id": identifier, **payload}, actor=actor)
            conn.execute(
                "INSERT INTO experiment_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier, payload["name"], payload["corpus_snapshot"], payload["code_revision"],
                    _json(payload["model_versions"]), _json(payload["index_revisions"]), _json(payload["parameters"]), event.offset,
                ),
            )
        return {"manifest_id": identifier, "created_event_offset": event.offset, **payload}

    def snapshot(self, *, actor: str = "system") -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            through = self.last_event_offset_in(conn)
            event_rows = conn.execute("SELECT event_id,payload_hash FROM events WHERE event_offset<=? ORDER BY event_offset", (through,)).fetchall()
            state_hash = _digest([dict(row) for row in event_rows])
            event = self._append_event(conn, stream_id="admin:snapshots", event_type="snapshot.created", payload={"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash}, actor=actor)
            conn.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)", (identifier, through, state_hash, event.offset, _now()))
        return {"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash, "created_event_offset": event.offset}

    def compact(self, *, actor: str = "system") -> dict[str, Any]:
        """Log a safe compaction pass. Canonical evidence is never compacted here."""

        result = self.append_event(
            stream_id="admin:compaction", event_type="compaction.completed",
            payload={"deleted_spine_events": 0, "deleted_node_versions": 0, "note": "embedded policy retains all derived indexes"}, actor=actor,
        )
        return {"deleted_spine_events": 0, "deleted_node_versions": 0, "event_offset": result.offset}

    # --------------------------------------------------------------- jobs
    @staticmethod
    def _job_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("job was not found")
        result = dict(row)
        result["payload"] = _decode(result.pop("payload_json"), {})
        error_json = result.pop("error_json")
        result_json = result.pop("result_json")
        result["error"] = _decode(error_json) if error_json else None
        result["result"] = _decode(result_json) if result_json else None
        result["cancel_requested"] = bool(result.get("cancel_requested", 0))
        result["retryable"] = result.get("status") not in {"succeeded", "cancelled"} and int(result.get("attempts", 0)) < int(result.get("max_attempts", 3))
        result["retry_after"] = result.get("available_at") if result.get("status") == "queued" and result.get("attempts", 0) else None
        return result

    def create_job(
        self,
        *,
        workspace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
        idempotency_key: str | None = None,
        request_id: str | None = None,
        webhook_id: str | None = None,
        max_attempts: int = 3,
        status: str = "queued",
    ) -> dict[str, Any]:
        """Create durable work state and its audit event atomically.

        A job idempotency key is intentionally stored separately from event
        idempotency keys.  This lets one HTTP operation create a job and still
        append subsequent lifecycle events without colliding with an ingress
        event that happened to use the same client key.
        """

        allowed = {"queued", "running", "succeeded", "failed", "cancelled"}
        if status not in allowed:
            raise InvariantViolation(f"unsupported job status {status!r}")
        if not kind.strip():
            raise InvariantViolation("job kind is required")
        if max_attempts < 1:
            raise InvariantViolation("max_attempts must be positive")
        payload = payload or {}
        with self.transaction() as conn:
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM jobs WHERE idempotency_key=? AND workspace_id=?",
                    (idempotency_key, workspace_id),
                ).fetchone()
                if existing:
                    existing_payload = _decode(existing["payload_json"], {})
                    if existing["kind"] != kind or _digest(existing_payload) != _digest(payload):
                        raise IdempotencyConflict("job idempotency key was reused with a different operation")
                    result = self._job_row(existing)
                    result["duplicate"] = True
                    return result
            job_id = str(uuid.uuid4())
            now = _now()
            event = self._append_event(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="job.created",
                payload={
                    "job_id": job_id,
                    "workspace_id": workspace_id,
                    "kind": kind,
                    "status": status,
                    "payload": payload,
                    "request_id": request_id,
                },
                actor=actor,
                correlation_id=request_id,
                idempotency_key=f"job:{idempotency_key}" if idempotency_key else None,
            )
            conn.execute(
                """INSERT INTO jobs(
                    job_id,workspace_id,kind,status,payload_json,created_event_offset,
                    updated_at,idempotency_key,attempts,max_attempts,available_at,
                    lease_until,error_json,result_json,request_id,webhook_id,created_at,
                    started_at,finished_at,cancel_requested
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, 0)""",
                (
                    job_id, workspace_id, kind, status, _json(payload), event.offset,
                    now, idempotency_key, max_attempts, now, request_id, webhook_id, now,
                ),
            )
            return self._job_row(conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            return self._job_row(conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())

    def list_jobs(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        clauses: list[str] = []
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id=?")
            values.append(workspace_id)
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        if kind is not None:
            clauses.append("kind=?")
            values.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM jobs{where} ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
        return [self._job_row(row) for row in rows]

    def _transition_job(
        self,
        conn: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        status: str,
        actor: str,
        reason: str | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        available_at: str | None = None,
        lease_until: str | None = None,
        cancel_requested: bool | None = None,
    ) -> dict[str, Any]:
        allowed = {"queued", "running", "succeeded", "failed", "cancelled"}
        if status not in allowed:
            raise InvariantViolation(f"unsupported job status {status!r}")
        now = _now()
        event = self._append_event(
            conn,
            stream_id=f"workspace:{row['workspace_id']}",
            event_type="job.status_changed",
            payload={
                "job_id": row["job_id"], "workspace_id": row["workspace_id"],
                "from_status": row["status"], "status": status, "reason": reason,
                "result": result, "error": error,
            },
            actor=actor,
        )
        finished_at = now if status in {"succeeded", "failed", "cancelled"} else None
        started_at = now if status == "running" else row["started_at"]
        conn.execute(
            """UPDATE jobs SET status=?,updated_at=?,available_at=?,lease_until=?,
                error_json=?,result_json=?,started_at=?,finished_at=?,cancel_requested=?
                WHERE job_id=?""",
            (
                status, now, available_at or now, lease_until,
                _json(error) if error is not None else None,
                _json(result) if result is not None else None,
                started_at, finished_at,
                int(cancel_requested if cancel_requested is not None else row["cancel_requested"]),
                row["job_id"],
            ),
        )
        updated = self._job_row(conn.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone())
        updated["status_event_offset"] = event.offset
        return updated

    def claim_jobs(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        kind: str | None = None,
        job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lease queued jobs for a worker with at-least-once semantics."""

        now = datetime.now(UTC)
        now_text = now.isoformat()
        lease_until = datetime.fromtimestamp(now.timestamp() + max(1, lease_seconds), UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                """UPDATE jobs SET status='queued', lease_until=NULL, available_at=?
                   WHERE status='running' AND lease_until IS NOT NULL AND lease_until < ?
                     AND cancel_requested=0""",
                (now_text, now_text),
            )
            clauses = ["status='queued'", "available_at<=?", "cancel_requested=0"]
            values: list[Any] = [now_text]
            if kind:
                clauses.append("kind=?")
                values.append(kind)
            if job_id:
                clauses.append("job_id=?")
                values.append(job_id)
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE {' AND '.join(clauses)} ORDER BY created_at,job_id LIMIT ?",
                [*values, max(1, min(int(limit), 100))],
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                updated = self._transition_job(
                    conn, row=row, status="running", actor="job-worker",
                    lease_until=lease_until, available_at=now_text,
                )
                conn.execute(
                    "UPDATE jobs SET attempts=attempts+1 WHERE job_id=?",
                    (row["job_id"],),
                )
                updated = self._job_row(conn.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone())
                claimed.append(updated)
            return claimed

    def complete_job(self, job_id: str, *, result: dict[str, Any] | None = None, actor: str = "job-worker") -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] == "succeeded":
                return self._job_row(row)
            if row["status"] == "cancelled":
                return self._job_row(row)
            return self._transition_job(conn, row=row, status="succeeded", actor=actor, result=result, lease_until=None)

    def fail_job(
        self,
        job_id: str,
        *,
        error: dict[str, Any],
        actor: str = "job-worker",
        retry: bool = True,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "cancelled"}:
                return self._job_row(row)
            should_retry = retry and int(row["attempts"]) < int(row["max_attempts"]) and not row["cancel_requested"]
            if should_retry:
                # A small deterministic backoff avoids a hot failure loop and
                # keeps retry scheduling reproducible in tests.
                delay = min(300, 2 ** max(0, int(row["attempts"]) - 1))
                available = datetime.fromtimestamp(datetime.now(UTC).timestamp() + delay, UTC).isoformat()
                return self._transition_job(
                    conn, row=row, status="queued", actor=actor, reason="retry_scheduled",
                    error=error, available_at=available, lease_until=None,
                )
            return self._transition_job(conn, row=row, status="failed", actor=actor, error=error, lease_until=None)

    def cancel_job(self, job_id: str, *, actor: str = "system", reason: str | None = None) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                return self._job_row(row)
            return self._transition_job(
                conn, row=row, status="cancelled", actor=actor, reason=reason or "cancelled_by_request",
                lease_until=None, cancel_requested=True,
            )

    def retry_job(self, job_id: str, *, actor: str = "system") -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] == "running":
                raise InvariantViolation("running jobs must expire or be cancelled before retry")
            if row["status"] == "succeeded":
                return self._job_row(row)
            return self._transition_job(
                conn, row=row, status="queued", actor=actor, reason="manual_retry",
                available_at=_now(), lease_until=None, cancel_requested=False,
            )

    # ---------------------------------------------- projection idempotency
    def record_projection_event(
        self,
        *,
        projection_name: str,
        event_id: str,
        event_offset: int,
        workspace_id: str,
        projection_revision: int,
    ) -> bool:
        """Record a consumer application exactly once by immutable event ID."""

        with self.transaction() as conn:
            inserted = conn.execute(
                """INSERT OR IGNORE INTO projection_events(
                    projection_name,event_id,event_offset,workspace_id,projection_revision,applied_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (projection_name, event_id, event_offset, workspace_id, projection_revision, _now()),
            ).rowcount
            if inserted:
                self._set_projection(conn, projection_name, workspace_id, event_offset)
            return bool(inserted)

    def projection_checkpoint(self, projection_name: str, workspace_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projection_revisions WHERE projection_name=? AND workspace_id=?",
                (projection_name, workspace_id),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------- webhooks
    @staticmethod
    def _webhook_row(row: sqlite3.Row | None, *, include_ciphertext: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("webhook was not found")
        result = dict(row)
        result["event_types"] = _decode(result.pop("event_types_json"), [])
        ciphertext = result.pop("secret_ciphertext")
        if include_ciphertext:
            result["secret_ciphertext"] = ciphertext
        # secret_hash is retained for rotation/audit verification; the actual
        # secret is never returned by the repository read path.
        return result

    def create_webhook(
        self,
        *,
        workspace_id: str,
        url: str,
        event_types: list[str],
        secret_hash: str,
        secret_ciphertext: str,
        actor: str,
    ) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.created",
                payload={"webhook_id": identifier, "workspace_id": workspace_id, "url": url, "event_types": event_types, "secret_hash": secret_hash}, actor=actor,
            )
            conn.execute(
                """INSERT INTO webhooks(webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types_json,status,created_event_offset,created_at,rotated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL)""",
                (identifier, workspace_id, url, secret_hash, secret_ciphertext, _json(event_types), event.offset, _now()),
            )
            result = self._webhook_row(conn.execute("SELECT * FROM webhooks WHERE webhook_id=?", (identifier,)).fetchone())
            result["secret_ciphertext"] = secret_ciphertext
            return result

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            return self._webhook_row(conn.execute("SELECT * FROM webhooks WHERE webhook_id=?", (webhook_id,)).fetchone())

    def webhook_secret(self, webhook_id: str, *, cipher: Any) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT secret_ciphertext FROM webhooks WHERE webhook_id=?", (webhook_id,)).fetchone()
        if not row:
            raise NotFoundError(f"webhook {webhook_id} was not found")
        return cipher.decrypt(row["secret_ciphertext"])

    def rotate_webhook(
        self,
        webhook_id: str,
        *,
        secret_hash: str,
        secret_ciphertext: str,
        actor: str,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM webhooks WHERE webhook_id=?", (webhook_id,)).fetchone()
            if not row:
                raise NotFoundError(f"webhook {webhook_id} was not found")
            event = self._append_event(
                conn, stream_id=f"workspace:{row['workspace_id']}", event_type="webhook.rotated",
                payload={"webhook_id": webhook_id, "workspace_id": row["workspace_id"], "secret_hash": secret_hash}, actor=actor,
            )
            conn.execute(
                "UPDATE webhooks SET secret_hash=?,secret_ciphertext=?,rotated_at=? WHERE webhook_id=?",
                (secret_hash, secret_ciphertext, _now(), webhook_id),
            )
            result = self._webhook_row(conn.execute("SELECT * FROM webhooks WHERE webhook_id=?", (webhook_id,)).fetchone())
            result["secret_ciphertext"] = secret_ciphertext
            result["rotation_event_offset"] = event.offset
            return result

    # ----------------------------------------------------- webhook delivery
    @staticmethod
    def _delivery_row(row: sqlite3.Row | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("webhook delivery was not found")
        result = dict(row)
        result["payload"] = _decode(result.pop("payload_json"), {})
        return result

    def enqueue_webhook_delivery(self, job: dict[str, Any], *, max_attempts: int = 8) -> dict[str, Any] | None:
        """Durably enqueue a completion callback exactly once per job/event."""

        webhook_id = job.get("webhook_id")
        if not webhook_id:
            return None
        webhook = self.get_webhook(str(webhook_id))
        event_type = "job." + str(job.get("status"))
        if webhook["status"] != "active" or (webhook.get("event_types") and event_type not in webhook["event_types"]):
            return None
        delivery_id = str(uuid.uuid4())
        payload = {
            "delivery_id": delivery_id,
            "event": event_type,
            "job_id": job["job_id"],
            "workspace_id": job["workspace_id"],
            "kind": job["kind"],
            "status": job["status"],
            "result": job.get("result"),
            "error": job.get("error"),
            "request_id": job.get("request_id"),
        }
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM webhook_deliveries WHERE webhook_id=? AND job_id=? AND event_type=?",
                (webhook_id, job["job_id"], event_type),
            ).fetchone()
            if existing:
                return self._delivery_row(existing)
            event = self._append_event(
                conn,
                stream_id=f"workspace:{job['workspace_id']}",
                event_type="webhook.delivery_queued",
                payload={"delivery_id": delivery_id, "webhook_id": webhook_id, "workspace_id": job["workspace_id"], "job_id": job["job_id"], "event_type": event_type},
                actor="webhook-dispatcher",
                correlation_id=str(job.get("request_id")) if job.get("request_id") else None,
            )
            now = _now()
            conn.execute(
                """INSERT INTO webhook_deliveries(
                    delivery_id,webhook_id,workspace_id,job_id,event_type,payload_json,status,
                    attempts,max_attempts,available_at,lease_until,last_error,delivered_at,
                    created_event_offset,created_at,updated_at
                ) VALUES (?,?,?,?,?,?, 'pending',0,?,?,NULL,NULL,NULL,?,?,?)""",
                (
                    delivery_id, webhook_id, job["workspace_id"], job["job_id"], event_type,
                    _json(payload), max(1, min(int(max_attempts), 32)), now, event.offset, now, now,
                ),
            )
            return self._delivery_row(conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone())

    def claim_webhook_deliveries(
        self,
        *,
        limit: int = 25,
        lease_seconds: int = 30,
        workspace_id: str | None = None,
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        now_value = now.isoformat()
        lease_until = datetime.fromtimestamp(now.timestamp() + max(1, int(lease_seconds)), UTC).isoformat()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE webhook_deliveries SET status='pending',lease_until=NULL,updated_at=? WHERE status='inflight' AND lease_until<?",
                (now_value, now_value),
            )
            clauses = ["status='pending'", "available_at<=?"]
            values: list[Any] = [now_value]
            if workspace_id:
                clauses.append("workspace_id=?")
                values.append(workspace_id)
            values.append(max(1, min(int(limit), 100)))
            rows = conn.execute(
                f"SELECT * FROM webhook_deliveries WHERE {' AND '.join(clauses)} ORDER BY created_at,delivery_id LIMIT ?",
                values,
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                updated = conn.execute(
                    """UPDATE webhook_deliveries SET status='inflight',attempts=attempts+1,lease_until=?,updated_at=?
                       WHERE delivery_id=? AND status='pending'""",
                    (lease_until, now_value, row["delivery_id"]),
                ).rowcount
                if updated:
                    claimed.append(self._delivery_row(conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (row["delivery_id"],)).fetchone()))
            return claimed

    def mark_webhook_delivery_succeeded(self, delivery_id: str) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
            delivery = self._delivery_row(row)
            if delivery["status"] == "succeeded":
                return delivery
            if delivery["status"] != "inflight":
                raise InvariantViolation("webhook delivery is not leased")
            event = self._append_event(
                conn, stream_id=f"workspace:{delivery['workspace_id']}", event_type="webhook.delivery_succeeded",
                payload={"delivery_id": delivery_id, "workspace_id": delivery["workspace_id"], "job_id": delivery["job_id"], "attempts": delivery["attempts"]}, actor="webhook-delivery-worker",
            )
            now = _now()
            conn.execute(
                "UPDATE webhook_deliveries SET status='succeeded',lease_until=NULL,delivered_at=?,updated_at=?,last_error=NULL WHERE delivery_id=?",
                (now, now, delivery_id),
            )
            result = self._delivery_row(conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone())
            result["status_event_offset"] = event.offset
            return result

    def fail_webhook_delivery(self, delivery_id: str, *, error: str, retry_delay_seconds: int | None = None) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
            delivery = self._delivery_row(row)
            if delivery["status"] != "inflight":
                raise InvariantViolation("webhook delivery is not leased")
            dead_letter = int(delivery["attempts"]) >= int(delivery["max_attempts"])
            delay = int(retry_delay_seconds if retry_delay_seconds is not None else min(3_600, 2 ** min(int(delivery["attempts"]), 10)))
            available = datetime.fromtimestamp(datetime.now(UTC).timestamp() + max(1, delay), UTC).isoformat()
            status = "dead_letter" if dead_letter else "pending"
            event = self._append_event(
                conn,
                stream_id=f"workspace:{delivery['workspace_id']}",
                event_type="webhook.delivery_dead_lettered" if dead_letter else "webhook.delivery_retry_scheduled",
                payload={"delivery_id": delivery_id, "workspace_id": delivery["workspace_id"], "job_id": delivery["job_id"], "attempts": delivery["attempts"], "error": error[:500]},
                actor="webhook-delivery-worker",
            )
            conn.execute(
                "UPDATE webhook_deliveries SET status=?,lease_until=NULL,available_at=?,last_error=?,updated_at=? WHERE delivery_id=?",
                (status, available, error[:2_000], _now(), delivery_id),
            )
            result = self._delivery_row(conn.execute("SELECT * FROM webhook_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone())
            result["status_event_offset"] = event.offset
            return result

    def list_webhook_deliveries(self, workspace_id: str, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM webhook_deliveries WHERE workspace_id=?"
        values: list[Any] = [workspace_id]
        if status:
            sql += " AND status=?"
            values.append(status)
        sql += " ORDER BY created_at DESC,delivery_id DESC LIMIT ?"
        values.append(max(1, min(int(limit), 200)))
        with self._connect() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [self._delivery_row(row) for row in rows]

    # ------------------------------------------------------------- API keys
    @staticmethod
    def _api_key_row(row: sqlite3.Row | None, *, include_hash: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("API key was not found")
        result = dict(row)
        result["scopes"] = _decode(result.pop("scopes_json"), [])
        result["allowed_visibility"] = _decode(result.pop("visibility_json"), [])
        result["model_permissions"] = _decode(result.pop("model_permissions_json"), [])
        if not include_hash:
            result.pop("key_hash", None)
        return result

    def create_api_key(
        self,
        *,
        workspace_id: str,
        subject: str,
        key_prefix: str,
        key_hash: str,
        scopes: list[str],
        allowed_visibility: list[str],
        model_permissions: list[str],
        expires_at: str | None,
        actor: str,
    ) -> dict[str, Any]:
        identifier = str(uuid.uuid4())
        with self.transaction() as conn:
            event = self._append_event(
                conn, stream_id=f"workspace:{workspace_id}", event_type="api_key.created",
                payload={"api_key_id": identifier, "workspace_id": workspace_id, "subject": subject, "key_prefix": key_prefix, "scopes": scopes, "allowed_visibility": allowed_visibility, "model_permissions": model_permissions, "expires_at": expires_at}, actor=actor,
            )
            conn.execute(
                """INSERT INTO api_keys(api_key_id,workspace_id,subject,key_prefix,key_hash,scopes_json,visibility_json,model_permissions_json,status,expires_at,created_event_offset,created_at,revoked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, NULL)""",
                (identifier, workspace_id, subject, key_prefix, key_hash, _json(scopes), _json(allowed_visibility), _json(model_permissions), expires_at, event.offset, _now()),
            )
            return self._api_key_row(conn.execute("SELECT * FROM api_keys WHERE api_key_id=?", (identifier,)).fetchone())

    def get_api_key(self, api_key_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            return self._api_key_row(conn.execute("SELECT * FROM api_keys WHERE api_key_id=?", (api_key_id,)).fetchone())

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE key_hash=? AND status='active'", (digest,)).fetchone()
        if not row:
            return None
        if row["expires_at"] and row["expires_at"] <= _now():
            return None
        return self._api_key_row(row, include_hash=True)

    def revoke_api_key(self, api_key_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE api_key_id=?", (api_key_id,)).fetchone()
            if not row:
                raise NotFoundError(f"API key {api_key_id} was not found")
            if row["status"] == "revoked":
                return self._api_key_row(row)
            event = self._append_event(
                conn, stream_id=f"workspace:{row['workspace_id']}", event_type="api_key.revoked",
                payload={"api_key_id": api_key_id, "workspace_id": row["workspace_id"], "reason": reason}, actor=actor,
            )
            conn.execute("UPDATE api_keys SET status='revoked',revoked_at=? WHERE api_key_id=?", (_now(), api_key_id))
            result = self._api_key_row(conn.execute("SELECT * FROM api_keys WHERE api_key_id=?", (api_key_id,)).fetchone())
            result["revocation_event_offset"] = event.offset
            return result

    # ---------------------------------------------------------- model audits
    def record_model_audit(self, audit: dict[str, Any]) -> dict[str, Any]:
        """Persist non-secret model usage/cost provenance in the Spine.

        Prompt text and provider credentials never enter this table.  The
        audit retains only hashes of redacted excerpts plus enough revisions to
        reproduce the bounded proposal workflow.
        """

        workspace_id = str(audit.get("workspace_id") or "")
        if not workspace_id:
            raise InvariantViolation("model audit requires a workspace_id")
        identifier = str(uuid.uuid4())
        payload = {
            "model_call_audit_id": identifier,
            "workspace_id": workspace_id,
            "model_id": str(audit.get("model_id") or "unknown"),
            "purpose": str(audit.get("purpose") or "unknown"),
            "prompt_template_revision": str(audit.get("prompt_template_revision") or "unknown"),
            "response_schema_hash": str(audit.get("response_schema_hash") or ""),
            "excerpt_hashes": list(audit.get("excerpt_hashes") or []),
            "node_count": int(audit.get("node_count") or 0),
            "estimated_tokens": int(audit.get("estimated_tokens") or 0),
            "cloud_tokens": int(audit.get("cloud_tokens") or 0),
            "cost_usd": float(audit.get("cost_usd") or 0.0),
            "status": str(audit.get("status") or "succeeded"),
        }
        with self.transaction() as conn:
            event = self._append_event(
                conn,
                stream_id=f"workspace:{workspace_id}",
                event_type="model.call_audited",
                payload=payload,
                actor=str(audit.get("actor") or "system"),
                correlation_id=str(audit["request_id"]) if audit.get("request_id") else None,
            )
            conn.execute(
                """INSERT INTO model_call_audits(
                    model_call_audit_id,workspace_id,model_id,purpose,actor,request_id,
                    prompt_template_revision,response_schema_hash,excerpt_hashes_json,node_count,
                    estimated_tokens,cloud_tokens,cost_usd,status,created_event_offset,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier, workspace_id, payload["model_id"], payload["purpose"], str(audit.get("actor") or "system"),
                    audit.get("request_id"), payload["prompt_template_revision"], payload["response_schema_hash"],
                    _json(payload["excerpt_hashes"]), payload["node_count"], payload["estimated_tokens"],
                    payload["cloud_tokens"], payload["cost_usd"], payload["status"], event.offset, _now(),
                ),
            )
        return {"model_call_audit_id": identifier, "created_event_offset": event.offset, **payload}

    def model_cost_total(self, workspace_id: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) FROM model_call_audits WHERE workspace_id=? AND status='succeeded'",
                (workspace_id,),
            ).fetchone()
        return float(row[0] or 0.0)

    # -------------------------------------------------------------- internals
    @staticmethod
    def last_event_offset_in(conn: sqlite3.Connection) -> int:
        return int(conn.execute("SELECT COALESCE(MAX(event_offset), 0) FROM events").fetchone()[0])

    @staticmethod
    def _node(conn: sqlite3.Connection, node_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        if not row:
            raise NotFoundError(f"node {node_id} was not found")
        return row

    @staticmethod
    def _current_version(conn: sqlite3.Connection, node_id: str, as_of_event: int | None = None) -> sqlite3.Row:
        sql = "SELECT * FROM node_versions WHERE node_id=?"
        args: list[Any] = [node_id]
        if as_of_event is not None:
            sql += " AND created_event_offset<=?"
            args.append(as_of_event)
        sql += " ORDER BY version DESC LIMIT 1"
        row = conn.execute(sql, args).fetchone()
        if not row:
            raise NotFoundError(f"node {node_id} has no version at requested time")
        return row

    @staticmethod
    def _assert_node_workspace(conn: sqlite3.Connection, node_id: str, workspace_id: str) -> None:
        node = SqliteEventStore._node(conn, node_id)
        if node["workspace_id"] != workspace_id:
            raise InvariantViolation("nodes and relations must stay within one workspace")

    @staticmethod
    def _assert_atom_version(conn: sqlite3.Connection, version_id: str, workspace_id: str) -> None:
        row = conn.execute(
            """SELECT nv.atom_version_id FROM node_versions nv JOIN nodes n ON n.node_id=nv.node_id
                WHERE nv.atom_version_id=? AND n.workspace_id=?""",
            (version_id, workspace_id),
        ).fetchone()
        if not row:
            raise InvariantViolation(f"evidence atom version {version_id} is absent or out of scope")
