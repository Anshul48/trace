"""Optional production adapters for the Trace V2 boundaries.

The core package intentionally does not import infrastructure SDKs at module
import time.  Each adapter accepts an injected client for tests and lazily
loads its vendor SDK only when a deployment selects that adapter.  This keeps
the embedded correctness path dependency-light while making the production
topology concrete rather than merely a documentation promise.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from .models import AppendResult, EventRecord
from .store import ALLOWED_RELATIONS, STRUCTURAL_RELATIONS, IdempotencyConflict, InvariantViolation, NotFoundError, _digest, _json, _now


POSTGRES_SCHEMA = """
-- Canonical event spine.  Deployments create time partitions and a fixed set
-- of workspace-hash partitions using the migration process before traffic.
CREATE TABLE IF NOT EXISTS trace_events (
    event_offset BIGINT GENERATED ALWAYS AS IDENTITY,
    event_id UUID NOT NULL,
    workspace_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    stream_sequence BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor TEXT NOT NULL,
    causation_id UUID,
    correlation_id UUID,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    idempotency_key TEXT,
    PRIMARY KEY (event_offset, occurred_at, workspace_id)
) PARTITION BY HASH (workspace_id);
-- Fixed workspace buckets keep tenant traffic spread across partitions. Each
-- bucket is itself range-partitioned by event time; the bucket default is a
-- safe bootstrap target until the migration process adds concrete time
-- windows and moves rows without changing the application contract.
CREATE TABLE IF NOT EXISTS trace_events_h00 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 0) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h00_default PARTITION OF trace_events_h00 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h01 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 1) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h01_default PARTITION OF trace_events_h01 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h02 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 2) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h02_default PARTITION OF trace_events_h02 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h03 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 3) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h03_default PARTITION OF trace_events_h03 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h04 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 4) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h04_default PARTITION OF trace_events_h04 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h05 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 5) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h05_default PARTITION OF trace_events_h05 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h06 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 6) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h06_default PARTITION OF trace_events_h06 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h07 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 7) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h07_default PARTITION OF trace_events_h07 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h08 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 8) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h08_default PARTITION OF trace_events_h08 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h09 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 9) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h09_default PARTITION OF trace_events_h09 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h10 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 10) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h10_default PARTITION OF trace_events_h10 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h11 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 11) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h11_default PARTITION OF trace_events_h11 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h12 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 12) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h12_default PARTITION OF trace_events_h12 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h13 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 13) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h13_default PARTITION OF trace_events_h13 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h14 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 14) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h14_default PARTITION OF trace_events_h14 DEFAULT;
CREATE TABLE IF NOT EXISTS trace_events_h15 PARTITION OF trace_events FOR VALUES WITH (MODULUS 16, REMAINDER 15) PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_h15_default PARTITION OF trace_events_h15 DEFAULT;
-- The parent default preserves zero-downtime bootstrap for older databases;
-- a migration can add buckets later if the schema predates this release.
CREATE TABLE IF NOT EXISTS trace_events_default PARTITION OF trace_events DEFAULT PARTITION BY RANGE (occurred_at);
CREATE TABLE IF NOT EXISTS trace_events_default_time PARTITION OF trace_events_default DEFAULT;

-- PostgreSQL partitioned tables cannot have a global unique index that omits
-- the partition key.  These are lookup indexes; the migration's unpartitioned
-- event-key ledger (or the repository transaction) enforces global event and
-- idempotency uniqueness.
CREATE INDEX IF NOT EXISTS trace_events_event_id ON trace_events(event_id);
CREATE INDEX IF NOT EXISTS trace_events_stream_sequence ON trace_events(stream_id, stream_sequence);
CREATE INDEX IF NOT EXISTS trace_events_idempotency ON trace_events(idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS trace_event_keys (
    event_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    idempotency_key TEXT,
    event_offset BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    UNIQUE(workspace_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS trace_outbox (
    event_offset BIGINT NOT NULL,
    event_id UUID NOT NULL,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    PRIMARY KEY (event_offset, event_id)
);
CREATE INDEX IF NOT EXISTS trace_outbox_pending ON trace_outbox(status, available_at);

-- Canonical state tables are deliberately workspace-keyed.  Production
-- migrations add time partitions and row policies to these tables as well.
CREATE TABLE IF NOT EXISTS trace_jobs (
    job_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    result JSONB,
    error JSONB,
    idempotency_key TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    request_id TEXT,
    webhook_id UUID,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS trace_jobs_idempotency
    ON trace_jobs(workspace_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS trace_webhooks (
    webhook_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    secret_hash CHAR(64) NOT NULL,
    secret_ciphertext TEXT NOT NULL,
    event_types JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    rotated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS trace_webhooks_workspace_status ON trace_webhooks(workspace_id, status);
CREATE TABLE IF NOT EXISTS trace_api_keys (
    api_key_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash CHAR(64) NOT NULL UNIQUE,
    scopes JSONB NOT NULL,
    allowed_visibility JSONB NOT NULL,
    model_permissions JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    expires_at TIMESTAMPTZ,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS trace_api_keys_active_hash ON trace_api_keys(key_hash, status);

CREATE TABLE IF NOT EXISTS trace_attachments (
    attachment_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    object_key TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_length BIGINT NOT NULL,
    metadata JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_ingestions (
    ingestion_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source JSONB NOT NULL,
    attachment_id UUID,
    accepted_event_offset BIGINT NOT NULL,
    atom_count INTEGER NOT NULL DEFAULT 0,
    parsing_status TEXT NOT NULL,
    indexing_status TEXT NOT NULL,
    consolidation_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_ingestions_workspace ON trace_ingestions(workspace_id, created_at DESC);
CREATE TABLE IF NOT EXISTS trace_hot_inbox (
    atom_version_id UUID PRIMARY KEY,
    node_id UUID NOT NULL,
    workspace_id TEXT NOT NULL,
    content TEXT NOT NULL,
    visible_from_event BIGINT NOT NULL,
    facets JSONB NOT NULL,
    security JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_hot_inbox_workspace ON trace_hot_inbox(workspace_id, visible_from_event);
CREATE TABLE IF NOT EXISTS trace_nodes (
    node_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    facets JSONB NOT NULL,
    security JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_node_versions (
    atom_version_id UUID PRIMARY KEY,
    node_id UUID NOT NULL REFERENCES trace_nodes(node_id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    properties JSONB NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_event_offset BIGINT NOT NULL,
    UNIQUE(node_id, version)
);
CREATE INDEX IF NOT EXISTS trace_node_versions_node ON trace_node_versions(node_id, version DESC);
CREATE TABLE IF NOT EXISTS trace_edge_versions (
    edge_version_id UUID PRIMARY KEY,
    edge_id UUID NOT NULL,
    version INTEGER NOT NULL,
    workspace_id TEXT NOT NULL,
    source_node_id UUID NOT NULL REFERENCES trace_nodes(node_id),
    target_node_id UUID NOT NULL REFERENCES trace_nodes(node_id),
    relation_type TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    valid_from_event BIGINT NOT NULL,
    valid_to_event BIGINT,
    model_version TEXT NOT NULL,
    properties JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    UNIQUE(edge_id, version)
);
CREATE INDEX IF NOT EXISTS trace_edges_workspace_nodes ON trace_edge_versions(workspace_id, source_node_id, target_node_id);
CREATE TABLE IF NOT EXISTS trace_evidence_anchors (
    anchor_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id UUID NOT NULL,
    source_atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    source_start INTEGER,
    source_end INTEGER,
    parser_location TEXT,
    quote_hash CHAR(64),
    created_event_offset BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_anchors_target ON trace_evidence_anchors(workspace_id, target_kind, target_id);
CREATE TABLE IF NOT EXISTS trace_proposals (
    proposal_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    proposal_type TEXT NOT NULL,
    candidate JSONB NOT NULL,
    evidence_atom_version_ids JSONB NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    model_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_event_offset BIGINT NOT NULL,
    decided_event_offset BIGINT,
    decision_reason TEXT
);
CREATE INDEX IF NOT EXISTS trace_proposals_workspace_status ON trace_proposals(workspace_id, status);
CREATE TABLE IF NOT EXISTS trace_evidence_bundles (
    evidence_bundle_id UUID PRIMARY KEY,
    workspace_id TEXT,
    query JSONB NOT NULL,
    results JSONB NOT NULL,
    sufficiency_state TEXT NOT NULL,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_benchmark_runs (
    benchmark_run_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    benchmark_name TEXT NOT NULL,
    stages JSONB NOT NULL,
    result JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_benchmark_runs_workspace ON trace_benchmark_runs(workspace_id, created_at DESC);
CREATE TABLE IF NOT EXISTS trace_feedback (
    feedback_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    evidence_bundle_id UUID,
    atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    event_type TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    actor TEXT NOT NULL,
    metadata JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_feedback_workspace_atom ON trace_feedback(workspace_id, atom_version_id, created_event_offset DESC);
CREATE TABLE IF NOT EXISTS trace_saved_queries (
    saved_query_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    query JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    UNIQUE(workspace_id, name)
);
CREATE TABLE IF NOT EXISTS trace_frozen_queries (
    frozen_query_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    query JSONB NOT NULL,
    atom_version_ids JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    UNIQUE(workspace_id, name)
);
CREATE TABLE IF NOT EXISTS trace_index_revisions (
    index_revision_id UUID PRIMARY KEY,
    workspace_id TEXT,
    embedding_model TEXT NOT NULL,
    vector_namespace TEXT NOT NULL,
    lexical_revision TEXT NOT NULL,
    normalization JSONB NOT NULL,
    rollout_state TEXT NOT NULL,
    created_event_offset BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_model_registry (
    model_registry_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    purpose TEXT NOT NULL,
    version TEXT NOT NULL,
    configuration JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    UNIQUE(name, provider, purpose, version)
);
CREATE TABLE IF NOT EXISTS trace_experiment_manifests (
    manifest_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    corpus_snapshot TEXT NOT NULL,
    code_revision TEXT NOT NULL,
    model_versions JSONB NOT NULL,
    index_revisions JSONB NOT NULL,
    parameters JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_snapshots (
    snapshot_id UUID PRIMARY KEY,
    through_event_offset BIGINT NOT NULL,
    state_hash CHAR(64) NOT NULL,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_dense_vectors (
    atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    provider_id TEXT NOT NULL,
    index_revision TEXT NOT NULL,
    vector JSONB NOT NULL,
    created_event_offset BIGINT NOT NULL,
    PRIMARY KEY(atom_version_id, provider_id, index_revision)
);
CREATE TABLE IF NOT EXISTS trace_projection_revisions (
    projection_name TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    last_applied_event BIGINT NOT NULL,
    revision BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(projection_name, workspace_id)
);
CREATE TABLE IF NOT EXISTS trace_projection_events (
    projection_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    event_offset BIGINT NOT NULL,
    workspace_id TEXT NOT NULL,
    projection_revision BIGINT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(projection_name, event_id)
);

ALTER TABLE trace_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_ingestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_hot_inbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_node_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_edge_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_evidence_anchors ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_evidence_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_benchmark_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_dense_vectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_saved_queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_frozen_queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_index_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS trace_events_tenant ON trace_events;
CREATE POLICY trace_events_tenant ON trace_events
    USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_jobs_tenant ON trace_jobs;
CREATE POLICY trace_jobs_tenant ON trace_jobs
    USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_webhooks_tenant ON trace_webhooks;
CREATE POLICY trace_webhooks_tenant ON trace_webhooks USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_api_keys_tenant ON trace_api_keys;
CREATE POLICY trace_api_keys_tenant ON trace_api_keys USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_attachments_tenant ON trace_attachments;
CREATE POLICY trace_attachments_tenant ON trace_attachments USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_ingestions_tenant ON trace_ingestions;
CREATE POLICY trace_ingestions_tenant ON trace_ingestions USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_hot_inbox_tenant ON trace_hot_inbox;
CREATE POLICY trace_hot_inbox_tenant ON trace_hot_inbox USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_nodes_tenant ON trace_nodes;
CREATE POLICY trace_nodes_tenant ON trace_nodes USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_node_versions_tenant ON trace_node_versions;
CREATE POLICY trace_node_versions_tenant ON trace_node_versions USING (current_setting('trace.workspace_id', true) = '*' OR EXISTS (SELECT 1 FROM trace_nodes n WHERE n.node_id = trace_node_versions.node_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_edges_tenant ON trace_edge_versions;
CREATE POLICY trace_edges_tenant ON trace_edge_versions USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_anchors_tenant ON trace_evidence_anchors;
CREATE POLICY trace_anchors_tenant ON trace_evidence_anchors USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_proposals_tenant ON trace_proposals;
CREATE POLICY trace_proposals_tenant ON trace_proposals USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_bundles_tenant ON trace_evidence_bundles;
CREATE POLICY trace_bundles_tenant ON trace_evidence_bundles USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_benchmark_tenant ON trace_benchmark_runs;
CREATE POLICY trace_benchmark_tenant ON trace_benchmark_runs USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_feedback_tenant ON trace_feedback;
CREATE POLICY trace_feedback_tenant ON trace_feedback USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_dense_vectors_tenant ON trace_dense_vectors;
CREATE POLICY trace_dense_vectors_tenant ON trace_dense_vectors USING (current_setting('trace.workspace_id', true) = '*' OR EXISTS (SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id = nv.node_id WHERE nv.atom_version_id = trace_dense_vectors.atom_version_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_saved_queries_tenant ON trace_saved_queries;
CREATE POLICY trace_saved_queries_tenant ON trace_saved_queries USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_frozen_queries_tenant ON trace_frozen_queries;
CREATE POLICY trace_frozen_queries_tenant ON trace_frozen_queries USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_index_revisions_tenant ON trace_index_revisions;
CREATE POLICY trace_index_revisions_tenant ON trace_index_revisions USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_tenant ON trace_projection_revisions;
CREATE POLICY trace_projection_tenant ON trace_projection_revisions USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_events_tenant ON trace_projection_events;
CREATE POLICY trace_projection_events_tenant ON trace_projection_events USING (current_setting('trace.workspace_id', true) = '*' OR workspace_id = current_setting('trace.workspace_id', true));
"""


class ProductionAdapterError(RuntimeError):
    """Raised when an optional production dependency or operation is missing."""


class PostgresEventStore:
    """PostgreSQL event/outbox/job adapter.

    The canonical event spine and core projections are implemented here.
    ``delegate`` remains an explicit migration seam for deployments that need
    to move a projection independently; the adapter never silently falls back
    to SQLite.
    """

    def __init__(self, dsn: str | None = None, *, connection_factory: Any | None = None, delegate: Any | None = None) -> None:
        self.dsn = dsn or os.environ.get("TRACE_POSTGRES_DSN")
        self.connection_factory = connection_factory
        self.delegate = delegate
        if not self.dsn and self.connection_factory is None:
            raise ValueError("TRACE_POSTGRES_DSN or connection_factory is required")

    def _connect(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory()
        try:
            import psycopg
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise ProductionAdapterError("psycopg is required for PostgresEventStore") from error
        return psycopg.connect(self.dsn)

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(POSTGRES_SCHEMA)

    def _call_delegate(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.delegate is None or not hasattr(self.delegate, name):
            raise ProductionAdapterError(
                f"PostgresEventStore operation {name!r} requires the PostgreSQL projection adapter"
            )
        return getattr(self.delegate, name)(*args, **kwargs)

    # Rich canonical/projection methods remain swappable during migration.
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if self.delegate is not None and hasattr(self.delegate, name):
            return getattr(self.delegate, name)
        raise AttributeError(name)

    @staticmethod
    def _json_value(value: Any, default: Any = None) -> Any:
        if value is None:
            return {} if default is None else default
        if isinstance(value, (dict, list)):
            return value
        return json.loads(value)

    @staticmethod
    def _cursor_mapping(cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        columns: list[str] = []
        for description in cursor.description:
            name = getattr(description, "name", None)
            columns.append(str(name if name is not None else description[0]))
        return dict(zip(columns, row, strict=True))

    def _append_event_in_connection(
        self,
        conn: Any,
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
        """Append an event and its outbox message on an existing transaction."""

        workspace_id = str(payload.get("workspace_id") or stream_id.split(":", 1)[-1])
        payload_hash = _digest(payload)
        with conn.cursor() as cursor:
            cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
            if idempotency_key:
                cursor.execute(
                    "SELECT event_id,event_offset,stream_sequence,payload_hash,event_type FROM trace_events WHERE workspace_id=%s AND idempotency_key=%s",
                    (workspace_id, idempotency_key),
                )
                existing = cursor.fetchone()
                if existing:
                    event_id, offset, sequence, existing_hash, existing_type = existing
                    if existing_hash != payload_hash or existing_type != event_type:
                        raise IdempotencyConflict("idempotency key was reused with a different event")
                    return AppendResult(event_id=str(event_id), offset=int(offset), stream_sequence=int(sequence), duplicate=True)
            event_id = str(uuid.uuid4())
            occurred_at = datetime.now(UTC)
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (stream_id,))
            cursor.execute(
                "SELECT COALESCE(MAX(stream_sequence),0)+1 FROM trace_events WHERE stream_id=%s",
                (stream_id,),
            )
            sequence = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO trace_events(
                    event_id,workspace_id,stream_id,stream_sequence,event_type,occurred_at,
                    actor,causation_id,correlation_id,schema_version,payload,payload_hash,idempotency_key
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                RETURNING event_offset""",
                (
                    event_id, workspace_id, stream_id, sequence, event_type, occurred_at,
                    actor, causation_id, correlation_id, schema_version,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")), payload_hash, idempotency_key,
                ),
            )
            offset = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO trace_outbox(event_offset,event_id,topic,payload,available_at)
                   VALUES (%s,%s,%s,%s::jsonb,%s)""",
                (offset, event_id, event_type, json.dumps({"event_id": event_id, "offset": offset, "payload": payload}), occurred_at),
            )
            cursor.execute(
                "INSERT INTO trace_event_keys(event_id,workspace_id,idempotency_key,event_offset,occurred_at) VALUES (%s,%s,%s,%s,%s)",
                (event_id, workspace_id, idempotency_key, offset, occurred_at),
            )
            return AppendResult(event_id=event_id, offset=offset, stream_sequence=sequence)

    def append_event(
        self,
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
        with self.connection() as conn:
            return self._append_event_in_connection(
                conn, stream_id=stream_id, event_type=event_type, payload=payload,
                actor=actor, causation_id=causation_id, correlation_id=correlation_id,
                schema_version=schema_version, idempotency_key=idempotency_key,
            )

    def events(self, *, after_offset: int = 0, through_offset: int | None = None) -> list[EventRecord]:
        sql = "SELECT event_id,event_offset,stream_id,stream_sequence,event_type,occurred_at,actor,causation_id,correlation_id,schema_version,payload,payload_hash,idempotency_key FROM trace_events WHERE event_offset>%s"
        values: list[Any] = [after_offset]
        if through_offset is not None:
            sql += " AND event_offset<=%s"
            values.append(through_offset)
        sql += " ORDER BY event_offset"
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute(sql, values)
                rows = cursor.fetchall()
        records: list[EventRecord] = []
        for row in rows:
            payload = row[10] if isinstance(row[10], dict) else json.loads(row[10])
            records.append(EventRecord(
                event_id=str(row[0]), offset=int(row[1]), stream_id=row[2], stream_sequence=int(row[3]),
                event_type=row[4], occurred_at=row[5], actor=row[6], causation_id=str(row[7]) if row[7] else None,
                correlation_id=str(row[8]) if row[8] else None, schema_version=int(row[9]), payload=payload,
                payload_hash=row[11], idempotency_key=row[12],
            ))
        return records

    def last_event_offset(self) -> int:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT COALESCE(MAX(event_offset),0) FROM trace_events")
                return int(cursor.fetchone()[0])

    def outbox_status(self) -> dict[str, int]:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT status,COUNT(*) FROM trace_outbox GROUP BY status")
                return {str(status): int(count) for status, count in cursor.fetchall()}

    def projection_status(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id or "*",))
                if workspace_id:
                    cursor.execute("SELECT projection_name,workspace_id,last_applied_event,revision,updated_at FROM trace_projection_revisions WHERE workspace_id=%s ORDER BY projection_name", (workspace_id,))
                else:
                    cursor.execute("SELECT projection_name,workspace_id,last_applied_event,revision,updated_at FROM trace_projection_revisions ORDER BY workspace_id,projection_name")
                return [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]

    def workspace_ids(self) -> list[str]:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT DISTINCT workspace_id FROM trace_nodes ORDER BY workspace_id")
                return [str(row[0]) for row in cursor.fetchall()]

    @classmethod
    def _pg_atom_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["properties"] = cls._json_value(result.pop("properties"), {})
        result["facets"] = cls._json_value(result.pop("facets"), [])
        result["security"] = cls._json_value(result.pop("security"), {})
        return result

    @classmethod
    def _pg_anchor_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _pg_atoms_query(self, cursor: Any, *, workspace_id: str | None, as_of_event: int | None, atom_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        clauses = ["n.facets @> '[\"atom\"]'::jsonb"]
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("n.workspace_id=%s")
            values.append(workspace_id)
        if as_of_event is not None:
            clauses.append("nv.created_event_offset<=%s")
            values.append(as_of_event)
        if atom_ids is not None:
            if not atom_ids:
                return []
            placeholders = ",".join("%s" for _ in atom_ids)
            clauses.append(f"nv.atom_version_id IN ({placeholders})")
            values.extend(atom_ids)
            cursor.execute(
                f"""SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                           n.workspace_id,n.facets,n.security
                    FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                    WHERE {' AND '.join(clauses)} ORDER BY nv.created_event_offset DESC""",
                values,
            )
            return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
        cursor.execute(
            f"""WITH ranked AS (
                SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                       n.workspace_id,n.facets,n.security,
                       ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                WHERE {' AND '.join(clauses)}
            ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security
              FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
            values,
        )
        return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]

    def queryable_atoms(self, workspace_id: str | None, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "queryable_atoms"):
            return self.delegate.queryable_atoms(workspace_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id or "*",))
                return self._pg_atoms_query(cursor, workspace_id=workspace_id, as_of_event=as_of_event)

    def iter_queryable_atoms(self, workspace_id: str | None, as_of_event: int | None = None, *, batch_size: int = 1_000) -> Iterator[dict[str, Any]]:
        """Stream current source atoms so rebuild workers do not materialize a tenant."""

        if self.delegate is not None and hasattr(self.delegate, "iter_queryable_atoms"):
            yield from self.delegate.iter_queryable_atoms(workspace_id, as_of_event, batch_size=batch_size)
            return
        clauses = ["n.facets @> '[\"atom\"]'::jsonb"]
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("n.workspace_id=%s")
            values.append(workspace_id)
        if as_of_event is not None:
            clauses.append("nv.created_event_offset<=%s")
            values.append(as_of_event)
        with self.connection() as conn:
            with conn.cursor(name="trace_current_atoms") as cursor:
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
                    values,
                )
                while True:
                    rows = cursor.fetchmany(max(1, min(int(batch_size), 10_000)))
                    if not rows:
                        break
                    for row in rows:
                        yield self._pg_atom_row(self._cursor_mapping(cursor, row) or {})

    def atom_versions(self, atom_version_ids: Sequence[str]) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "atom_versions"):
            return self.delegate.atom_versions(atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                rows = self._pg_atoms_query(cursor, workspace_id=None, as_of_event=None, atom_ids=atom_version_ids)
        by_id = {row["atom_version_id"]: row for row in rows}
        return [by_id[item] for item in atom_version_ids if item in by_id]

    def _pg_node(self, cursor: Any, node_id: str) -> dict[str, Any]:
        cursor.execute("SELECT node_id,workspace_id,facets,security,created_event_offset FROM trace_nodes WHERE node_id=%s", (node_id,))
        node = self._cursor_mapping(cursor, cursor.fetchone())
        if not node:
            raise NotFoundError(f"node {node_id} was not found")
        return node

    def _pg_node_version(self, cursor: Any, node_id: str, as_of_event: int | None = None) -> dict[str, Any]:
        condition = " AND created_event_offset<=%s" if as_of_event is not None else ""
        values: list[Any] = [node_id]
        if as_of_event is not None:
            values.append(as_of_event)
        cursor.execute(f"SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE node_id=%s{condition} ORDER BY version DESC LIMIT 1", values)
        version = self._cursor_mapping(cursor, cursor.fetchone())
        if not version:
            raise NotFoundError(f"node {node_id} has no version at requested time")
        return version

    def get_node(self, node_id: str, as_of_event: int | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_node"):
            return self.delegate.get_node(node_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                node = self._pg_node(cursor, node_id)
                version = self._pg_node_version(cursor, node_id, as_of_event)
                result = self._pg_atom_row({**version, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})
                cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (version["atom_version_id"],))
                result["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return result

    def node_history(self, node_id: str) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "node_history"):
            return self.delegate.node_history(node_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                node = self._pg_node(cursor, node_id)
                cursor.execute("SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE node_id=%s ORDER BY version", (node_id,))
                return [self._pg_atom_row({**(self._cursor_mapping(cursor, row) or {}), "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]}) for row in cursor.fetchall()]

    def edit_node(self, *, node_id: str, content: str, properties: dict[str, Any], actor: str, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "edit_node"):
            return self.delegate.edit_node(node_id=node_id, content=content, properties=properties, actor=actor, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                node = self._pg_node(cursor, node_id)
                current = self._pg_node_version(cursor, node_id)
            current_properties = self._json_value(current.get("properties"), {})
            merged = {**current_properties, **properties, "predecessor_atom_version_id": current["atom_version_id"]}
            version = int(current["version"]) + 1
            version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"node-version:{node_id}:{idempotency_key}")) if idempotency_key else str(uuid.uuid4())
            event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": node["workspace_id"], "atom_version_id": version_id, "version": version, "content": content, "properties": merged, "patch": properties, "predecessor": current["atom_version_id"]}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                if event.duplicate:
                    cursor.execute("SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset FROM trace_node_versions WHERE created_event_offset=%s", (event.offset,))
                    duplicate = self._cursor_mapping(cursor, cursor.fetchone())
                    if not duplicate:
                        raise InvariantViolation("duplicate edit event has no node projection")
                    return self._pg_atom_row({**duplicate, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})
                cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)", (version_id, node_id, version, content, json.dumps(merged), _digest(content), event.offset))
                cursor.execute("DELETE FROM trace_hot_inbox WHERE node_id=%s", (node_id,))
                cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, node_id, node["workspace_id"], content, event.offset, json.dumps(self._json_value(node["facets"], [])), json.dumps(self._json_value(node["security"], {}))))
                cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('hot_inbox',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (node["workspace_id"], event.offset))
            return self._pg_atom_row({"atom_version_id": version_id, "node_id": node_id, "version": version, "content": content, "properties": merged, "content_hash": _digest(content), "created_event_offset": event.offset, "workspace_id": node["workspace_id"], "facets": node["facets"], "security": node["security"]})

    def split_node(self, *, node_id: str, parts: list[str], actor: str, idempotency_key: str | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "split_node"):
            return self.delegate.split_node(node_id=node_id, parts=parts, actor=actor, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                parent = self._pg_node(cursor, node_id)
                parent_version = self._pg_node_version(cursor, node_id)
            marker = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.split_requested", payload={"node_id": node_id, "workspace_id": parent["workspace_id"], "parts_hash": _digest(parts)}, actor=actor, idempotency_key=idempotency_key)
            if marker.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,n.workspace_id,n.facets,n.security FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE n.workspace_id=%s AND nv.properties->>'split_marker_event'=%s ORDER BY nv.version", (parent["workspace_id"], str(marker.offset)))
                    return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
            children: list[dict[str, Any]] = []
            for ordinal, part in enumerate(parts):
                child_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
                security = self._json_value(parent.get("security"), {})
                node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{parent['workspace_id']}", event_type="node.created", payload={"node_id": child_id, "workspace_id": parent["workspace_id"], "facets": ["atom"], "security": security}, actor=actor, causation_id=marker.event_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (child_id, parent["workspace_id"], json.dumps(["atom"]), json.dumps(security), node_event.offset))
                properties = {"split_from_node_id": node_id, "split_from_atom_version_id": parent_version["atom_version_id"], "split_marker_event": marker.offset, "ordinal": ordinal}
                version_event = self._append_event_in_connection(conn, stream_id=f"node:{child_id}", event_type="node.versioned", payload={"node_id": child_id, "workspace_id": parent["workspace_id"], "atom_version_id": version_id, "version": 1, "content": part, "properties": properties, "split_from": parent_version["atom_version_id"]}, actor=actor, causation_id=node_event.event_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, child_id, part, json.dumps(properties), _digest(part), version_event.offset))
                    cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, child_id, parent["workspace_id"], part, version_event.offset, json.dumps(["atom"]), json.dumps(security)))
                self._pg_insert_edge(conn, workspace_id=parent["workspace_id"], source_node_id=child_id, target_node_id=node_id, relation_type="CHILD_OF", evidence_atom_version_ids=[parent_version["atom_version_id"]], actor=actor, model_version="lineage-v1", confidence=1.0, weight=1.0, status="trusted", properties={"operation": "split", "marker_event": marker.offset}, causation_id=marker.event_id)
                children.append(self._pg_atom_row({"atom_version_id": version_id, "node_id": child_id, "version": 1, "content": part, "properties": properties, "content_hash": _digest(part), "created_event_offset": version_event.offset, "workspace_id": parent["workspace_id"], "facets": ["atom"], "security": security}))
            return children

    def create_alias(self, *, source_node_id: str, target_node_id: str, actor: str, evidence_atom_version_ids: list[str], idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_alias"):
            return self.delegate.create_alias(source_node_id=source_node_id, target_node_id=target_node_id, actor=actor, evidence_atom_version_ids=evidence_atom_version_ids, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                source = self._pg_node(cursor, source_node_id)
                target = self._pg_node(cursor, target_node_id)
                if source["workspace_id"] != target["workspace_id"]:
                    raise InvariantViolation("nodes and relations must stay within one workspace")
                if not evidence_atom_version_ids:
                    current = self._pg_node_version(cursor, source_node_id)
                    evidence_atom_version_ids = [current["atom_version_id"]]
            operation = self._append_event_in_connection(conn, stream_id=f"node:{source_node_id}", event_type="node.aliased", payload={"source_node_id": source_node_id, "target_node_id": target_node_id, "workspace_id": source["workspace_id"]}, actor=actor, idempotency_key=idempotency_key)
            if operation.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,valid_to_event,model_version,properties,created_event_offset FROM trace_edge_versions WHERE source_node_id=%s AND target_node_id=%s AND relation_type='alias_of' ORDER BY created_event_offset DESC LIMIT 1", (source_node_id, target_node_id))
                    edge = self._cursor_mapping(cursor, cursor.fetchone())
                if not edge:
                    raise InvariantViolation("duplicate alias event has no edge projection")
                edge["properties"] = self._json_value(edge.get("properties"), {})
                return edge
            return self._pg_insert_edge(conn, workspace_id=source["workspace_id"], source_node_id=source_node_id, target_node_id=target_node_id, relation_type="alias_of", evidence_atom_version_ids=evidence_atom_version_ids, actor=actor, model_version="manual", confidence=1.0, weight=1.0, status="trusted", properties={"operation_event": operation.offset}, causation_id=operation.event_id)

    def current_nodes(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "current_nodes"):
            return self.delegate.current_nodes(workspace_id, as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                clauses = ["n.workspace_id=%s"]
                values: list[Any] = [workspace_id]
                if as_of_event is not None:
                    clauses.append("nv.created_event_offset<=%s")
                    values.append(as_of_event)
                cursor.execute(
                    f"""WITH ranked AS (
                        SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                               n.workspace_id,n.facets,n.security,
                               ROW_NUMBER() OVER (PARTITION BY nv.node_id ORDER BY nv.version DESC) AS rank
                        FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                        WHERE {' AND '.join(clauses)}
                    ) SELECT atom_version_id,node_id,version,content,properties,content_hash,created_event_offset,workspace_id,facets,security FROM ranked WHERE rank=1 ORDER BY created_event_offset DESC""",
                    values,
                )
                nodes = [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]
                for node in nodes:
                    cursor.execute("SELECT anchor_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='node_version' AND target_id=%s ORDER BY anchor_id", (node["atom_version_id"],))
                    node["evidence_anchors"] = self._pg_anchor_rows([self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()])
                return nodes

    def get_ingestion(self, ingestion_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_ingestion"):
            return self.delegate.get_ingestion(ingestion_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at FROM trace_ingestions WHERE ingestion_id=%s", (ingestion_id,))
                result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"ingestion {ingestion_id} was not found")
        result["source"] = self._json_value(result.get("source"), {})
        return result

    def get_attachment(self, attachment_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_attachment"):
            return self.delegate.get_attachment(attachment_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT attachment_id,workspace_id,content_hash,object_key,media_type,byte_length,created_event_offset,metadata FROM trace_attachments WHERE attachment_id=%s", (attachment_id,))
                result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"attachment {attachment_id} was not found")
        result["metadata"] = self._json_value(result.get("metadata"), {})
        return result

    def ingestion_atoms(self, ingestion_id: str) -> list[dict[str, Any]]:
        ingestion = self.get_ingestion(ingestion_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (ingestion["workspace_id"],))
                cursor.execute(
                    """SELECT nv.atom_version_id,nv.node_id,nv.version,nv.content,nv.properties,nv.content_hash,nv.created_event_offset,
                              n.workspace_id,n.facets,n.security
                       FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id
                       WHERE n.workspace_id=%s AND nv.properties->>'ingestion_id'=%s ORDER BY (nv.properties->>'ordinal')::INTEGER""",
                    (ingestion["workspace_id"], ingestion_id),
                )
                return [self._pg_atom_row(self._cursor_mapping(cursor, row) or {}) for row in cursor.fetchall()]

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
        """Capture raw source metadata and versioned atoms in one transaction."""

        if self.delegate is not None and hasattr(self.delegate, "ingest"):
            return self.delegate.ingest(workspace_id=workspace_id, source=source, attachment=attachment, atoms=atoms, actor=actor, visibility=visibility, idempotency_key=idempotency_key)
        stable_seed = f"{workspace_id}:{idempotency_key}" if idempotency_key else None
        ingestion_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ingestion:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        attachment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"attachment:{stable_seed}")) if stable_seed else str(uuid.uuid4())
        with self.connection() as conn:
            accepted = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="ingestion.accepted",
                payload={"ingestion_id": ingestion_id, "workspace_id": workspace_id, "source": source, "content_hash": attachment["content_hash"]},
                actor=actor, correlation_id=ingestion_id, idempotency_key=idempotency_key,
            )
            if accepted.duplicate:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at FROM trace_ingestions WHERE accepted_event_offset=%s", (accepted.offset,))
                    existing = self._cursor_mapping(cursor, cursor.fetchone())
                if not existing:
                    raise InvariantViolation("duplicate ingestion event has no ingestion projection")
                existing["source"] = self._json_value(existing.get("source"), {})
                return existing
            now = datetime.now(UTC)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_ingestions(ingestion_id,workspace_id,source,attachment_id,accepted_event_offset,atom_count,parsing_status,indexing_status,consolidation_status,created_at) VALUES (%s,%s,%s::jsonb,%s,%s,%s,'running','pending','pending',%s)", (ingestion_id, workspace_id, json.dumps(source), attachment_id, accepted.offset, len(atoms), now))
            attachment_event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="attachment.recorded",
                payload={"attachment_id": attachment_id, "ingestion_id": ingestion_id, "workspace_id": workspace_id, "content_hash": attachment["content_hash"], "object_key": attachment["object_key"], "media_type": attachment["media_type"], "byte_length": attachment["byte_length"], "metadata": attachment.get("metadata", {})},
                actor=actor, causation_id=accepted.event_id, correlation_id=ingestion_id,
            )
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_attachments(attachment_id,workspace_id,content_hash,object_key,media_type,byte_length,metadata,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", (attachment_id, workspace_id, attachment["content_hash"], attachment["object_key"], attachment["media_type"], attachment["byte_length"], json.dumps(attachment.get("metadata", {})), attachment_event.offset))
            created: list[dict[str, Any]] = []
            for atom in atoms:
                ordinal = atom["ordinal"]
                node_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"node:{stable_seed}:{ordinal}")) if stable_seed else str(uuid.uuid4())
                security = {"visibility": visibility, "origin": source.get("uri"), "actor": actor}
                node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="node.created", payload={"node_id": node_id, "workspace_id": workspace_id, "facets": ["atom"], "security": security}, actor=actor, causation_id=accepted.event_id, correlation_id=ingestion_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (node_id, workspace_id, json.dumps(["atom"]), json.dumps(security), node_event.offset))
                version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"atom-version:{stable_seed}:{ordinal}:1")) if stable_seed else str(uuid.uuid4())
                properties = {"ingestion_id": ingestion_id, "attachment_id": attachment_id, "source_start": atom["start"], "source_end": atom["end"], "ordinal": atom["ordinal"], "parser_location": atom["parser_location"], "source": source}
                version_event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": workspace_id, "atom_version_id": version_id, "version": 1, "content": atom["content"], "properties": properties}, actor=actor, causation_id=node_event.event_id, correlation_id=ingestion_id)
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, node_id, atom["content"], json.dumps(properties), _digest(atom["content"]), version_event.offset))
                    cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (version_id, node_id, workspace_id, atom["content"], version_event.offset, json.dumps(["atom"]), json.dumps(security)))
                created.append({"node_id": node_id, "atom_version_id": version_id, "event_offset": version_event.offset, **properties})
            for previous, following in zip(created, created[1:]):
                self._pg_insert_edge(conn, workspace_id=workspace_id, source_node_id=previous["node_id"], target_node_id=following["node_id"], relation_type="NEXT", evidence_atom_version_ids=[previous["atom_version_id"], following["atom_version_id"]], actor=actor, model_version="structural-v1", confidence=1.0, weight=1.0, status="trusted", properties={"ingestion_id": ingestion_id, "structural": True}, causation_id=accepted.event_id, correlation_id=ingestion_id)
            finished = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="ingestion.atomized", payload={"ingestion_id": ingestion_id, "atom_count": len(created)}, actor="system", causation_id=accepted.event_id, correlation_id=ingestion_id)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_ingestions SET parsing_status='completed',indexing_status='lexical_ready',consolidation_status='pending' WHERE ingestion_id=%s", (ingestion_id,))
            return {"ingestion_id": ingestion_id, "workspace_id": workspace_id, "atom_count": len(created), "accepted_event_offset": accepted.offset, "atomized_event_offset": finished.offset, "parsing_status": "completed", "indexing_status": "lexical_ready", "consolidation_status": "pending"}

    def _pg_insert_edge(
        self,
        conn: Any,
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
        if relation_type not in ALLOWED_RELATIONS:
            raise InvariantViolation(f"unsupported relation_type {relation_type!r}")
        if relation_type not in STRUCTURAL_RELATIONS and not evidence_atom_version_ids:
            raise InvariantViolation("evidence relations require source anchors")
        edge_id, edge_version_id = str(uuid.uuid4()), str(uuid.uuid4())
        event = self._append_event_in_connection(
            conn, stream_id=f"workspace:{workspace_id}", event_type="edge.created",
            payload={"edge_id": edge_id, "edge_version_id": edge_version_id, "workspace_id": workspace_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "relation_type": relation_type, "weight": weight, "confidence": confidence, "status": status, "model_version": model_version, "evidence_atom_version_ids": evidence_atom_version_ids, "properties": properties},
            actor=actor, causation_id=causation_id, correlation_id=correlation_id,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT workspace_id FROM trace_nodes WHERE node_id IN (%s,%s) ORDER BY node_id", (source_node_id, target_node_id))
            node_workspaces = [str(row[0]) for row in cursor.fetchall()]
            if len(node_workspaces) != 2 or any(item != workspace_id for item in node_workspaces):
                raise InvariantViolation("nodes and relations must stay within one workspace")
            cursor.execute("INSERT INTO trace_edge_versions(edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,model_version,properties,created_event_offset) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)", (edge_version_id, edge_id, workspace_id, source_node_id, target_node_id, relation_type, weight, confidence, status, event.offset, model_version, json.dumps(properties), event.offset))
            for source_atom_version_id in evidence_atom_version_ids:
                cursor.execute("SELECT nv.properties,nv.content FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (source_atom_version_id, workspace_id))
                source = self._cursor_mapping(cursor, cursor.fetchone())
                if not source:
                    raise InvariantViolation(f"evidence atom version {source_atom_version_id} is absent or out of scope")
                source_properties = self._json_value(source.get("properties"), {})
                cursor.execute("INSERT INTO trace_evidence_anchors(anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset) VALUES (%s,%s,'edge_version',%s,%s,%s,%s,%s,%s,%s)", (str(uuid.uuid4()), workspace_id, edge_version_id, source_atom_version_id, source_properties.get("source_start"), source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source.get("content", "")), event.offset))
        return {"edge_id": edge_id, "edge_version_id": edge_version_id, "version": 1, "workspace_id": workspace_id, "source_node_id": source_node_id, "target_node_id": target_node_id, "relation_type": relation_type, "weight": weight, "confidence": confidence, "status": status, "model_version": model_version, "properties": properties, "evidence_atom_version_ids": list(evidence_atom_version_ids), "created_event_offset": event.offset}

    def create_edge(self, **kwargs: Any) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_edge"):
            return self.delegate.create_edge(**kwargs)
        with self.connection() as conn:
            return self._pg_insert_edge(conn, **kwargs)

    def current_edges(self, workspace_id: str, as_of_event: int | None = None) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "current_edges"):
            return self.delegate.current_edges(workspace_id, as_of_event)
        clause = " AND ev.created_event_offset<=%s" if as_of_event is not None else ""
        values: list[Any] = [workspace_id]
        if as_of_event is not None:
            values.append(as_of_event)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"""WITH ranked AS (
                    SELECT ev.*,ROW_NUMBER() OVER (PARTITION BY ev.edge_id ORDER BY ev.version DESC) AS rank
                    FROM trace_edge_versions ev WHERE ev.workspace_id=%s{clause}
                ) SELECT edge_version_id,edge_id,version,workspace_id,source_node_id,target_node_id,relation_type,weight,confidence,status,valid_from_event,valid_to_event,model_version,properties,created_event_offset FROM ranked WHERE rank=1 AND status='trusted'""", values)
                edges = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                for edge in edges:
                    edge["properties"] = self._json_value(edge.get("properties"), {})
                    cursor.execute("SELECT anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset FROM trace_evidence_anchors WHERE target_kind='edge_version' AND target_id=%s ORDER BY anchor_id", (edge["edge_version_id"],))
                    edge["evidence_anchors"] = [self._cursor_mapping(cursor, row) or {} for row in cursor.fetchall()]
                return edges

    def semantic_link_exists(self, workspace_id: str, source_node_id: str, target_node_id: str) -> bool:
        if self.delegate is not None and hasattr(self.delegate, "semantic_link_exists"):
            return self.delegate.semantic_link_exists(workspace_id, source_node_id, target_node_id)
        marks = ",".join("%s" for _ in ("supports", "contradicts", "depends_on", "implements", "example_of"))
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT 1 FROM trace_edge_versions WHERE workspace_id=%s AND source_node_id=%s AND target_node_id=%s AND relation_type IN ({marks}) AND status IN ('trusted','proposed') LIMIT 1", [workspace_id, source_node_id, target_node_id, "supports", "contradicts", "depends_on", "implements", "example_of"])
                return cursor.fetchone() is not None

    def set_consolidation_status(self, ingestion_id: str, status: str, *, actor: str = "system") -> None:
        if status not in {"pending", "running", "completed", "failed"}:
            raise ValueError("invalid consolidation status")
        if self.delegate is not None and hasattr(self.delegate, "set_consolidation_status"):
            return self.delegate.set_consolidation_status(ingestion_id, status, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT workspace_id FROM trace_ingestions WHERE ingestion_id=%s FOR UPDATE", (ingestion_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"ingestion {ingestion_id} was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type=f"consolidation.{status}", payload={"ingestion_id": ingestion_id, "status": status, "workspace_id": workspace_id}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_ingestions SET consolidation_status=%s WHERE ingestion_id=%s", (status, ingestion_id))
                cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('consolidation',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (workspace_id, event.offset))

    def reconcile_hot_inbox(self, workspace_id: str | None = None, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "reconcile_hot_inbox"):
            return self.delegate.reconcile_hot_inbox(workspace_id, actor=actor)
        with self.connection() as conn:
            started = self._append_event_in_connection(conn, stream_id="admin:projections", event_type="projection.reconcile_started", payload={"projection": "hot_inbox", "workspace_id": workspace_id}, actor=actor)
            workspaces = [workspace_id] if workspace_id else self.workspace_ids()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM trace_hot_inbox WHERE (%s IS NULL OR workspace_id=%s)", (workspace_id, workspace_id))
            inserted = 0
            for workspace in workspaces:
                with conn.cursor() as cursor:
                    atoms = self._pg_atoms_query(cursor, workspace_id=workspace, as_of_event=None)
                    for atom in atoms:
                        cursor.execute("INSERT INTO trace_hot_inbox(atom_version_id,node_id,workspace_id,content,visible_from_event,facets,security) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)", (atom["atom_version_id"], atom["node_id"], workspace, atom["content"], atom["created_event_offset"], json.dumps(atom["facets"]), json.dumps(atom["security"])))
                        inserted += 1
            completed = self._append_event_in_connection(conn, stream_id="admin:projections", event_type="projection.reconciled", payload={"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted}, actor=actor, causation_id=started.event_id)
            with conn.cursor() as cursor:
                for workspace in workspaces:
                    cursor.execute("INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at) VALUES ('hot_inbox',%s,%s,1,NOW()) ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=EXCLUDED.last_applied_event,revision=trace_projection_revisions.revision+1,updated_at=NOW()", (workspace, completed.offset))
            return {"projection": "hot_inbox", "workspace_id": workspace_id, "inserted": inserted, "event_offset": completed.offset}

    def replay_report(self, workspace_id: str) -> dict[str, Any]:
        events = self.events()
        scoped = [event for event in events if event.payload.get("workspace_id") == workspace_id or event.stream_id == f"workspace:{workspace_id}"]
        return {"workspace_id": workspace_id, "event_count": len(scoped), "last_event_offset": max((event.offset for event in scoped), default=0), "replayable": True}

    def save_bundle(self, *, workspace_id: str | None, query: dict[str, Any], results: list[dict[str, Any]], sufficiency_state: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_bundle"):
            return self.delegate.save_bundle(workspace_id=workspace_id, query=query, results=results, sufficiency_state=sufficiency_state)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id or 'all'}", event_type="evidence_bundle.created", payload={"evidence_bundle_id": identifier, "workspace_id": workspace_id, "result_count": len(results), "sufficiency_state": sufficiency_state}, actor="system")
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_evidence_bundles(evidence_bundle_id,workspace_id,query,results,sufficiency_state,created_event_offset,created_at) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,NOW())", (identifier, workspace_id, json.dumps(query), json.dumps(results), sufficiency_state, event.offset))
                return self._pg_bundle_from_cursor(cursor, identifier)

    def _pg_bundle_from_cursor(self, cursor: Any, bundle_id: str) -> dict[str, Any]:
        cursor.execute("SELECT evidence_bundle_id,workspace_id,query,results,sufficiency_state,created_event_offset,created_at FROM trace_evidence_bundles WHERE evidence_bundle_id=%s", (bundle_id,))
        result = self._cursor_mapping(cursor, cursor.fetchone())
        if not result:
            raise NotFoundError(f"evidence bundle {bundle_id} was not found")
        result["query"] = self._json_value(result.get("query"), {})
        result["results"] = self._json_value(result.get("results"), [])
        return result

    def get_bundle(self, evidence_bundle_id: str, **_: Any) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_bundle"):
            return self.delegate.get_bundle(evidence_bundle_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                return self._pg_bundle_from_cursor(cursor, evidence_bundle_id)

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
        if self.delegate is not None and hasattr(self.delegate, "record_feedback"):
            return self.delegate.record_feedback(workspace_id=workspace_id, atom_version_id=atom_version_id, event_type=event_type, weight=weight, actor=actor, evidence_bundle_id=evidence_bundle_id, metadata=metadata, idempotency_key=idempotency_key)
        if event_type not in {"selected", "opened", "cited", "accepted", "rejected"}:
            raise InvariantViolation(f"unsupported feedback event_type {event_type!r}")
        metadata = metadata or {}
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_version_id, workspace_id))
                if cursor.fetchone() is None:
                    raise InvariantViolation(f"evidence atom version {atom_version_id} is absent or out of scope")
                if evidence_bundle_id:
                    bundle = self._pg_bundle_from_cursor(cursor, evidence_bundle_id)
                    if bundle["workspace_id"] != workspace_id or atom_version_id not in {item.get("atom_version_id") for item in bundle["results"]}:
                        raise InvariantViolation("feedback atom is absent from the named evidence bundle")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="retrieval.feedback_recorded", payload={"feedback_id": identifier, "workspace_id": workspace_id, "evidence_bundle_id": evidence_bundle_id, "atom_version_id": atom_version_id, "event_type": event_type, "weight": weight, "metadata": metadata}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_feedback(feedback_id,workspace_id,evidence_bundle_id,atom_version_id,event_type,weight,actor,metadata,created_event_offset,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,NOW())", (identifier, workspace_id, evidence_bundle_id, atom_version_id, event_type, weight, actor, json.dumps(metadata), event.offset))
                return {"feedback_id": identifier, "workspace_id": workspace_id, "evidence_bundle_id": evidence_bundle_id, "atom_version_id": atom_version_id, "event_type": event_type, "weight": weight, "actor": actor, "metadata": metadata, "created_event_offset": event.offset}

    def feedback_scores(self, workspace_id: str, atom_version_ids: Sequence[str]) -> dict[str, float]:
        if self.delegate is not None and hasattr(self.delegate, "feedback_scores"):
            return self.delegate.feedback_scores(workspace_id, atom_version_ids)
        if not atom_version_ids:
            return {}
        marks = ",".join("%s" for _ in atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT atom_version_id,event_type,SUM(weight) AS total FROM trace_feedback WHERE workspace_id=%s AND atom_version_id IN ({marks}) GROUP BY atom_version_id,event_type", [workspace_id, *atom_version_ids])
                rows = cursor.fetchall()
        weights = {"selected": 0.05, "opened": 0.10, "cited": 0.20, "accepted": 0.15, "rejected": -0.20}
        result: dict[str, float] = {}
        for atom_id, kind, total in rows:
            result[str(atom_id)] = max(-1.0, min(1.0, result.get(str(atom_id), 0.0) + weights[str(kind)] * float(total)))
        return result

    def dense_vectors(self, provider_id: str, atom_version_ids: Sequence[str], *, index_revision: str = "embedded-current") -> dict[str, list[float]]:
        if self.delegate is not None and hasattr(self.delegate, "dense_vectors"):
            return self.delegate.dense_vectors(provider_id, atom_version_ids, index_revision=index_revision)
        if not atom_version_ids:
            return {}
        marks = ",".join("%s" for _ in atom_version_ids)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute(f"SELECT atom_version_id,vector FROM trace_dense_vectors WHERE provider_id=%s AND index_revision=%s AND atom_version_id IN ({marks})", [provider_id, index_revision, *atom_version_ids])
                rows = cursor.fetchall()
        return {str(atom_id): [float(item) for item in self._json_value(vector, [])] for atom_id, vector in rows}

    def upsert_dense_vectors(self, *, workspace_id: str, provider_id: str, vectors: dict[str, list[float]], actor: str = "system", index_revision: str = "embedded-current") -> int:
        if self.delegate is not None and hasattr(self.delegate, "upsert_dense_vectors"):
            return self.delegate.upsert_dense_vectors(workspace_id=workspace_id, provider_id=provider_id, vectors=vectors, actor=actor, index_revision=index_revision)
        if not vectors:
            return 0
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="dense_index.updated", payload={"workspace_id": workspace_id, "provider_id": provider_id, "index_revision": index_revision, "atom_version_ids": sorted(vectors), "count": len(vectors)}, actor=actor)
            with conn.cursor() as cursor:
                for atom_id, vector in vectors.items():
                    cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_id, workspace_id))
                    if cursor.fetchone() is None:
                        raise InvariantViolation(f"evidence atom version {atom_id} is absent or out of scope")
                    cursor.execute("INSERT INTO trace_dense_vectors(atom_version_id,provider_id,index_revision,vector,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s) ON CONFLICT(atom_version_id,provider_id,index_revision) DO UPDATE SET vector=EXCLUDED.vector,created_event_offset=EXCLUDED.created_event_offset", (atom_id, provider_id, index_revision, json.dumps(vector), event.offset))
            return len(vectors)

    @classmethod
    def _pg_proposal_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("proposal was not found")
        result = dict(row)
        result["candidate"] = cls._json_value(result.pop("candidate"), {})
        result["evidence_atom_version_ids"] = cls._json_value(result.pop("evidence_atom_version_ids"), [])
        return result

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
        if self.delegate is not None and hasattr(self.delegate, "create_proposal"):
            return self.delegate.create_proposal(workspace_id=workspace_id, proposal_type=proposal_type, candidate=candidate, evidence_atom_version_ids=evidence_atom_version_ids, confidence=confidence, model_version=model_version, actor=actor, idempotency_key=idempotency_key)
        if proposal_type == "edge" and candidate.get("relation_type") not in ALLOWED_RELATIONS:
            raise InvariantViolation("edge proposals require an allowed relation_type")
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"proposal:{workspace_id}:{idempotency_key}")) if idempotency_key else str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                for atom_id in evidence_atom_version_ids:
                    cursor.execute("SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (atom_id, workspace_id))
                    if cursor.fetchone() is None:
                        raise InvariantViolation(f"evidence atom version {atom_id} is absent or out of scope")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="proposal.created", payload={"proposal_id": identifier, "workspace_id": workspace_id, "proposal_type": proposal_type, "candidate": candidate, "evidence_atom_version_ids": evidence_atom_version_ids, "confidence": confidence, "model_version": model_version}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                if event.duplicate:
                    cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE created_event_offset=%s", (event.offset,))
                    return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
                cursor.execute("INSERT INTO trace_proposals(proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,'pending',%s)", (identifier, workspace_id, proposal_type, json.dumps(candidate), json.dumps(evidence_atom_version_ids), confidence, model_version, event.offset))
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (identifier,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def list_proposals(self, workspace_id: str, *, proposal_type: str | None = None, status: str | None = None, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_proposals"):
            return self.delegate.list_proposals(workspace_id, proposal_type=proposal_type, status=status, limit=limit, offset=offset)
        clauses = ["workspace_id=%s"]
        values: list[Any] = [workspace_id]
        if proposal_type:
            clauses.append("proposal_type=%s")
            values.append(proposal_type)
        if status:
            clauses.append("status=%s")
            values.append(status)
        suffix = ""
        if limit is not None:
            suffix = " LIMIT %s OFFSET %s"
            values.extend([max(1, min(int(limit), 200)), max(0, int(offset))])
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(f"SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE {' AND '.join(clauses)} ORDER BY created_event_offset DESC{suffix}", values)
                return [self._pg_proposal_row(self._cursor_mapping(cursor, row)) for row in cursor.fetchall()]

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_proposal"):
            return self.delegate.get_proposal(proposal_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (proposal_id,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def decide_proposal(self, *, proposal_id: str, decision: str, actor: str, reason: str | None, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "decide_proposal"):
            return self.delegate.decide_proposal(proposal_id=proposal_id, decision=decision, actor=actor, reason=reason, idempotency_key=idempotency_key)
        if decision not in {"promoted", "rejected"}:
            raise ValueError("decision must be promoted or rejected")
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s FOR UPDATE", (proposal_id,))
                row = self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if row["status"] != "pending":
                if row["status"] == decision:
                    return row
                raise InvariantViolation(f"proposal is already {row['status']}")
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{row['workspace_id']}", event_type=f"proposal.{decision}", payload={"proposal_id": proposal_id, "workspace_id": row["workspace_id"], "reason": reason}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_proposals SET status=%s,decided_event_offset=%s,decision_reason=%s WHERE proposal_id=%s", (decision, event.offset, reason, proposal_id))
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s", (proposal_id,))
                return self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def _pg_insert_derived_node(self, conn: Any, *, workspace_id: str, facets: list[str], content: str, properties: dict[str, Any], evidence_atom_version_ids: list[str], actor: str) -> dict[str, Any]:
        if not evidence_atom_version_ids:
            raise InvariantViolation("derived nodes require evidence anchors")
        node_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
        anchor_ids = [str(uuid.uuid4()) for _ in evidence_atom_version_ids]
        visibility = str(properties.get("visibility", "private"))
        stored = {**properties, "evidence_anchor_ids": anchor_ids, "evidence_atom_version_ids": list(evidence_atom_version_ids)}
        node_event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="node.created", payload={"node_id": node_id, "workspace_id": workspace_id, "facets": facets, "security": {"visibility": visibility, "actor": actor, "derived": True}}, actor=actor)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO trace_nodes(node_id,workspace_id,facets,security,created_event_offset) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s)", (node_id, workspace_id, json.dumps(facets), json.dumps({"visibility": visibility, "actor": actor, "derived": True}), node_event.offset))
        version_event = self._append_event_in_connection(conn, stream_id=f"node:{node_id}", event_type="node.versioned", payload={"node_id": node_id, "workspace_id": workspace_id, "atom_version_id": version_id, "version": 1, "derived": True, "content": content, "properties": stored, "evidence_atom_version_ids": evidence_atom_version_ids}, actor=actor, causation_id=node_event.event_id)
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO trace_node_versions(atom_version_id,node_id,version,content,properties,content_hash,created_event_offset) VALUES (%s,%s,1,%s,%s::jsonb,%s,%s)", (version_id, node_id, content, json.dumps(stored), _digest(content), version_event.offset))
            for anchor_id, source_id in zip(anchor_ids, evidence_atom_version_ids, strict=True):
                cursor.execute("SELECT nv.properties,nv.content FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id=nv.node_id WHERE nv.atom_version_id=%s AND n.workspace_id=%s", (source_id, workspace_id))
                source = self._cursor_mapping(cursor, cursor.fetchone())
                if not source:
                    raise InvariantViolation(f"evidence atom version {source_id} is absent or out of scope")
                source_properties = self._json_value(source.get("properties"), {})
                cursor.execute("INSERT INTO trace_evidence_anchors(anchor_id,workspace_id,target_kind,target_id,source_atom_version_id,source_start,source_end,parser_location,quote_hash,created_event_offset) VALUES (%s,%s,'node_version',%s,%s,%s,%s,%s,%s,%s)", (anchor_id, workspace_id, version_id, source_id, source_properties.get("source_start"), source_properties.get("source_end"), source_properties.get("parser_location"), _digest(source.get("content", "")), version_event.offset))
        return {"node_id": node_id, "atom_version_id": version_id, "event_offset": version_event.offset, "facets": facets, "evidence_anchor_ids": anchor_ids, "evidence_atom_version_ids": list(evidence_atom_version_ids)}

    def create_derived_node(self, *, workspace_id: str, facets: list[str], content: str, properties: dict[str, Any], evidence_atom_version_ids: list[str], actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "create_derived_node"):
            return self.delegate.create_derived_node(workspace_id=workspace_id, facets=facets, content=content, properties=properties, evidence_atom_version_ids=evidence_atom_version_ids, actor=actor)
        with self.connection() as conn:
            return self._pg_insert_derived_node(conn, workspace_id=workspace_id, facets=facets, content=content, properties=properties, evidence_atom_version_ids=evidence_atom_version_ids, actor=actor)

    def promote_proposal(self, *, proposal_id: str, actor: str, reason: str | None, idempotency_key: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "promote_proposal"):
            return self.delegate.promote_proposal(proposal_id=proposal_id, actor=actor, reason=reason, idempotency_key=idempotency_key)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT proposal_id,workspace_id,proposal_type,candidate,evidence_atom_version_ids,confidence,model_version,status,created_event_offset,decided_event_offset,decision_reason FROM trace_proposals WHERE proposal_id=%s FOR UPDATE", (proposal_id,))
                proposal = self._pg_proposal_row(self._cursor_mapping(cursor, cursor.fetchone()))
            if proposal["status"] != "pending":
                if proposal["status"] == "promoted":
                    return proposal
                raise InvariantViolation(f"proposal is already {proposal['status']}")
            candidate = proposal["candidate"]
            if proposal["proposal_type"] == "edge":
                materialized = self._pg_insert_edge(conn, workspace_id=proposal["workspace_id"], source_node_id=str(candidate["source_node_id"]), target_node_id=str(candidate["target_node_id"]), relation_type=str(candidate["relation_type"]), evidence_atom_version_ids=proposal["evidence_atom_version_ids"], actor=actor, model_version=proposal["model_version"], confidence=float(proposal["confidence"]), weight=float(candidate.get("weight", 1.0)), status="trusted", properties={**candidate.get("properties", {}), "proposal_id": proposal_id})
            else:
                content = str(candidate.get("content") or candidate.get("summary") or candidate.get("name") or _json(candidate))
                materialized = self._pg_insert_derived_node(conn, workspace_id=proposal["workspace_id"], facets=["claim" if proposal["proposal_type"] == "contradiction_resolution" else proposal["proposal_type"]], content=content, properties={**candidate, "proposal_id": proposal_id, "model_version": proposal["model_version"]}, evidence_atom_version_ids=proposal["evidence_atom_version_ids"], actor=actor)
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{proposal['workspace_id']}", event_type="proposal.promoted", payload={"proposal_id": proposal_id, "workspace_id": proposal["workspace_id"], "reason": reason, "materialized": materialized}, actor=actor, idempotency_key=idempotency_key)
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_proposals SET status='promoted',decided_event_offset=%s,decision_reason=%s WHERE proposal_id=%s", (event.offset, reason, proposal_id))
            proposal["status"] = "promoted"
            proposal["decided_event_offset"] = event.offset
            proposal["decision_reason"] = reason
            proposal["materialized"] = materialized
            return proposal

    def save_benchmark_run(self, *, workspace_id: str, benchmark_name: str, stages: list[str], result: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_benchmark_run"):
            return self.delegate.save_benchmark_run(workspace_id=workspace_id, benchmark_name=benchmark_name, stages=stages, result=result, actor=actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="benchmark.run_completed", payload={"benchmark_run_id": identifier, "workspace_id": workspace_id, "benchmark_name": benchmark_name, "stages": stages, "result": result}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_benchmark_runs(benchmark_run_id,workspace_id,benchmark_name,stages,result,created_event_offset,created_at) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,NOW())", (identifier, workspace_id, benchmark_name, json.dumps(stages), json.dumps(result), event.offset))
        return {"benchmark_run_id": identifier, "workspace_id": workspace_id, "benchmark_name": benchmark_name, "stages": stages, "result": result, "created_event_offset": event.offset}

    def save_query(self, *, workspace_id: str, name: str, query: dict[str, Any], frozen_atom_version_ids: list[str] | None, actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "save_query"):
            return self.delegate.save_query(workspace_id=workspace_id, name=name, query=query, frozen_atom_version_ids=frozen_atom_version_ids, actor=actor)
        table = "trace_frozen_queries" if frozen_atom_version_ids is not None else "trace_saved_queries"
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id=f"workspace:{workspace_id}", event_type="saved_query.created", payload={"id": identifier, "workspace_id": workspace_id, "name": name, "frozen": frozen_atom_version_ids is not None}, actor=actor)
            with conn.cursor() as cursor:
                try:
                    if frozen_atom_version_ids is None:
                        cursor.execute("INSERT INTO trace_saved_queries(saved_query_id,workspace_id,name,query,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s)", (identifier, workspace_id, name, json.dumps(query), event.offset))
                    else:
                        cursor.execute("INSERT INTO trace_frozen_queries(frozen_query_id,workspace_id,name,query,atom_version_ids,created_event_offset) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s)", (identifier, workspace_id, name, json.dumps(query), json.dumps(frozen_atom_version_ids), event.offset))
                except Exception as error:
                    if "duplicate" in str(error).lower() or "unique" in str(error).lower():
                        raise InvariantViolation(f"a saved query named {name!r} already exists in this workspace") from error
                    raise
        return {"frozen_query_id" if frozen_atom_version_ids is not None else "saved_query_id": identifier, "workspace_id": workspace_id, "name": name, "query": query, "created_event_offset": event.offset, "atom_version_ids": frozen_atom_version_ids}

    def register_index(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_index"):
            return self.delegate.register_index(payload, actor)
        identifier = str(uuid.uuid4())
        workspace_id = payload.get("workspace_id")
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id="admin:indexes", event_type="index_revision.created", payload={"index_revision_id": identifier, **payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_index_revisions(index_revision_id,workspace_id,embedding_model,vector_namespace,lexical_revision,normalization,rollout_state,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)", (identifier, workspace_id, payload["embedding_model"], payload["vector_namespace"], payload["lexical_revision"], json.dumps(payload.get("normalization", {})), payload["rollout_state"], event.offset))
        return {"index_revision_id": identifier, "created_event_offset": event.offset, **payload}

    def register_model(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_model"):
            return self.delegate.register_model(payload, actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id="admin:models", event_type="model.registered", payload={"model_registry_id": identifier, **payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_model_registry(model_registry_id,name,provider,purpose,version,configuration,created_event_offset) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)", (identifier, payload["name"], payload["provider"], payload["purpose"], payload["version"], json.dumps(payload.get("configuration", {})), event.offset))
        return {"model_registry_id": identifier, "created_event_offset": event.offset, **payload}

    def register_manifest(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "register_manifest"):
            return self.delegate.register_manifest(payload, actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            event = self._append_event_in_connection(conn, stream_id="admin:experiments", event_type="experiment_manifest.created", payload={"manifest_id": identifier, **payload}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_experiment_manifests(manifest_id,name,corpus_snapshot,code_revision,model_versions,index_revisions,parameters,created_event_offset) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)", (identifier, payload["name"], payload["corpus_snapshot"], payload["code_revision"], json.dumps(payload.get("model_versions", {})), json.dumps(payload.get("index_revisions", [])), json.dumps(payload.get("parameters", {})), event.offset))
        return {"manifest_id": identifier, "created_event_offset": event.offset, **payload}

    def snapshot(self, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "snapshot"):
            return self.delegate.snapshot(actor=actor)
        identifier = str(uuid.uuid4())
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT COALESCE(MAX(event_offset),0) FROM trace_events")
                through = int(cursor.fetchone()[0])
                cursor.execute("SELECT event_offset,payload_hash FROM trace_events WHERE event_offset<=%s ORDER BY event_offset", (through,))
                state_hash = _digest([{"event_offset": row[0], "payload_hash": row[1]} for row in cursor.fetchall()])
            event = self._append_event_in_connection(conn, stream_id="admin:snapshots", event_type="snapshot.created", payload={"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash}, actor=actor)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO trace_snapshots(snapshot_id,through_event_offset,state_hash,created_event_offset,created_at) VALUES (%s,%s,%s,%s,NOW())", (identifier, through, state_hash, event.offset))
        return {"snapshot_id": identifier, "through_event_offset": through, "state_hash": state_hash, "created_event_offset": event.offset}

    def compact(self, *, actor: str = "system") -> dict[str, Any]:
        event = self.append_event(stream_id="admin:compaction", event_type="compaction.completed", payload={"deleted_spine_events": 0, "deleted_node_versions": 0, "note": "canonical history is retained; only rebuildable projections may be compacted"}, actor=actor)
        return {"deleted_spine_events": 0, "deleted_node_versions": 0, "event_offset": event.offset}

    def claim_outbox(self, *, limit: int = 100, lease_seconds: int = 30) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        lease = datetime.fromtimestamp(now.timestamp() + max(1, lease_seconds), UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE trace_outbox SET status='pending',lease_until=NULL
                       WHERE status='inflight' AND lease_until<%s""", (now,)
                )
                cursor.execute(
                    """SELECT o.event_offset,o.event_id,o.topic,o.payload,o.attempts
                       FROM trace_outbox o WHERE o.status='pending' AND o.available_at<=%s
                       ORDER BY o.event_offset FOR UPDATE SKIP LOCKED LIMIT %s""", (now, limit),
                )
                rows = cursor.fetchall()
                result: list[dict[str, Any]] = []
                for offset, event_id, topic, payload, attempts in rows:
                    cursor.execute(
                        "UPDATE trace_outbox SET status='inflight',attempts=attempts+1,lease_until=%s WHERE event_offset=%s AND event_id=%s",
                        (lease, offset, event_id),
                    )
                    if not isinstance(payload, dict):
                        payload = json.loads(payload)
                    result.append({"event_offset": int(offset), "event_id": str(event_id), "topic": topic, "payload": payload, "attempts": int(attempts) + 1})
                return result

    def mark_outbox_published(self, event_offset: int) -> None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE trace_outbox SET status='published',published_at=NOW(),lease_until=NULL WHERE event_offset=%s AND status='inflight'",
                    (event_offset,),
                )
                if cursor.rowcount != 1:
                    raise InvariantViolation(f"outbox event {event_offset} is not leased")

    def release_outbox(self, event_offset: int) -> None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE trace_outbox SET status='pending',lease_until=NULL WHERE event_offset=%s AND status='inflight'",
                    (event_offset,),
                )
                if cursor.rowcount != 1:
                    raise InvariantViolation(f"outbox event {event_offset} is not leased")

    def record_projection_event(
        self,
        *,
        projection_name: str,
        event_id: str,
        event_offset: int,
        workspace_id: str,
        projection_revision: int,
    ) -> bool:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                cursor.execute(
                    """INSERT INTO trace_projection_events(projection_name,event_id,event_offset,workspace_id,projection_revision,applied_at)
                       VALUES (%s,%s,%s,%s,%s,NOW()) ON CONFLICT(projection_name,event_id) DO NOTHING""",
                    (projection_name, event_id, event_offset, workspace_id, projection_revision),
                )
                inserted = cursor.rowcount == 1
                if inserted:
                    cursor.execute(
                        """INSERT INTO trace_projection_revisions(projection_name,workspace_id,last_applied_event,revision,updated_at)
                           VALUES (%s,%s,%s,%s,NOW())
                           ON CONFLICT(projection_name,workspace_id) DO UPDATE SET last_applied_event=GREATEST(trace_projection_revisions.last_applied_event,EXCLUDED.last_applied_event),revision=EXCLUDED.revision,updated_at=NOW()""",
                        (projection_name, workspace_id, event_offset, projection_revision),
                    )
                return inserted

    def projection_checkpoint(self, projection_name: str, workspace_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM trace_projection_revisions WHERE projection_name=%s AND workspace_id=%s", (projection_name, workspace_id))
                row = cursor.fetchone()
                if not row:
                    return None
                columns = [description[0] for description in cursor.description]
                return dict(zip(columns, row, strict=True))

    _JOB_COLUMNS = "job_id,workspace_id,kind,status,payload,result,error,idempotency_key,attempts,max_attempts,available_at,lease_until,request_id,webhook_id,created_event_offset,created_at,updated_at,started_at,finished_at,cancel_requested"

    @classmethod
    def _pg_job_row(cls, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise NotFoundError("job was not found")
        result = dict(row)
        result["payload"] = cls._json_value(result.get("payload"), {})
        result["error"] = cls._json_value(result.get("error")) if result.get("error") is not None else None
        result["result"] = cls._json_value(result.get("result")) if result.get("result") is not None else None
        result["cancel_requested"] = bool(result.get("cancel_requested"))
        result["retryable"] = result.get("status") not in {"succeeded", "cancelled"} and int(result.get("attempts", 0)) < int(result.get("max_attempts", 3))
        available_at = result.get("available_at")
        result["retry_after"] = available_at.isoformat() if hasattr(available_at, "isoformat") and result.get("status") == "queued" and result.get("attempts", 0) else (available_at if result.get("status") == "queued" and result.get("attempts", 0) else None)
        return result

    def _pg_fetch_job(self, cursor: Any, job_id: str, *, for_update: bool = False) -> dict[str, Any] | None:
        cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE job_id=%s" + (" FOR UPDATE" if for_update else ""), (job_id,))
        return self._cursor_mapping(cursor, cursor.fetchone())

    def _pg_transition_job(
        self,
        conn: Any,
        *,
        row: dict[str, Any],
        status: str,
        actor: str,
        reason: str | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        available_at: datetime | None = None,
        lease_until: datetime | None = None,
        cancel_requested: bool | None = None,
    ) -> dict[str, Any]:
        allowed = {"queued", "running", "succeeded", "failed", "cancelled"}
        if status not in allowed:
            raise InvariantViolation(f"unsupported job status {status!r}")
        now = datetime.now(UTC)
        event = self._append_event_in_connection(
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
        effective_available = available_at or (now if status != "queued" else now)
        effective_cancel = bool(row.get("cancel_requested")) if cancel_requested is None else bool(cancel_requested)
        with conn.cursor() as cursor:
            cursor.execute(
                """UPDATE trace_jobs SET status=%s,updated_at=%s,available_at=%s,lease_until=%s,
                   error=%s::jsonb,result=%s::jsonb,started_at=%s,finished_at=%s,cancel_requested=%s
                   WHERE job_id=%s""",
                (
                    status, now, effective_available, lease_until,
                    json.dumps(error, sort_keys=True) if error is not None else None,
                    json.dumps(result, sort_keys=True) if result is not None else None,
                    now if status == "running" else (row.get("started_at") if row.get("started_at") else None),
                    now if status in {"succeeded", "failed", "cancelled"} else None,
                    effective_cancel, row["job_id"],
                ),
            )
            updated = self._pg_fetch_job(cursor, str(row["job_id"]))
        if updated is None:
            raise InvariantViolation("job transition removed its projection")
        projected = self._pg_job_row(updated)
        projected["status_event_offset"] = event.offset
        return projected

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
        """Create a PostgreSQL job and its creation event atomically."""

        if self.delegate is not None and hasattr(self.delegate, "create_job"):
            return self.delegate.create_job(
                workspace_id=workspace_id, kind=kind, payload=payload, actor=actor,
                idempotency_key=idempotency_key, request_id=request_id,
                webhook_id=webhook_id, max_attempts=max_attempts, status=status,
            )
        if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise InvariantViolation(f"unsupported job status {status!r}")
        if not kind.strip() or max_attempts < 1:
            raise InvariantViolation("job kind is required and max_attempts must be positive")
        payload = payload or {}
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id,))
                if idempotency_key:
                    cursor.execute(
                        f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE workspace_id=%s AND idempotency_key=%s",
                        (workspace_id, idempotency_key),
                    )
                    existing = self._cursor_mapping(cursor, cursor.fetchone())
                    if existing:
                        existing_payload = self._json_value(existing.get("payload"), {})
                        if existing["kind"] != kind or _digest(existing_payload) != _digest(payload):
                            raise IdempotencyConflict("job idempotency key was reused with a different operation")
                        duplicate = self._pg_job_row(existing)
                        duplicate["duplicate"] = True
                        return duplicate
            job_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="job.created",
                payload={"job_id": job_id, "workspace_id": workspace_id, "kind": kind, "status": status, "payload": payload, "request_id": request_id},
                actor=actor, correlation_id=request_id,
                idempotency_key=f"job:{idempotency_key}" if idempotency_key else None,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_jobs(
                       job_id,workspace_id,kind,status,payload,attempts,max_attempts,available_at,
                       request_id,webhook_id,created_event_offset,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s::jsonb,0,%s,%s,%s,%s,%s,%s,%s)""",
                    (job_id, workspace_id, kind, status, json.dumps(payload, sort_keys=True), max_attempts, now, request_id, webhook_id, event.offset, now, now),
                )
                created = self._pg_fetch_job(cursor, job_id)
            return self._pg_job_row(created)

    def get_job(self, job_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_job"):
            return self.delegate.get_job(job_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                row = self._pg_fetch_job(cursor, job_id)
        return self._pg_job_row(row)

    def list_jobs(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "list_jobs"):
            return self.delegate.list_jobs(workspace_id=workspace_id, status=status, kind=kind, limit=limit, offset=offset)
        clauses: list[str] = []
        values: list[Any] = []
        if workspace_id is not None:
            clauses.append("workspace_id=%s")
            values.append(workspace_id)
        if status is not None:
            clauses.append("status=%s")
            values.append(status)
        if kind is not None:
            clauses.append("kind=%s")
            values.append(kind)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', %s, true)", (workspace_id or "*",))
                cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs{where} ORDER BY created_at DESC,job_id DESC LIMIT %s OFFSET %s", [*values, max(1, min(int(limit), 200)), max(0, int(offset))])
                rows = [self._cursor_mapping(cursor, row) for row in cursor.fetchall()]
        return [self._pg_job_row(row) for row in rows]

    def claim_jobs(
        self,
        *,
        limit: int = 10,
        lease_seconds: int = 300,
        kind: str | None = None,
        job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.delegate is not None and hasattr(self.delegate, "claim_jobs"):
            return self.delegate.claim_jobs(limit=limit, lease_seconds=lease_seconds, kind=kind, job_id=job_id)
        now = datetime.now(UTC)
        lease_until = datetime.fromtimestamp(now.timestamp() + max(1, lease_seconds), UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("UPDATE trace_jobs SET status='queued',lease_until=NULL,available_at=%s WHERE status='running' AND lease_until IS NOT NULL AND lease_until<%s AND cancel_requested=FALSE", (now, now))
                clauses = ["status='queued'", "available_at<=%s", "cancel_requested=FALSE"]
                values: list[Any] = [now]
                if kind:
                    clauses.append("kind=%s")
                    values.append(kind)
                if job_id:
                    clauses.append("job_id=%s")
                    values.append(job_id)
                cursor.execute(f"SELECT {self._JOB_COLUMNS} FROM trace_jobs WHERE {' AND '.join(clauses)} ORDER BY created_at,job_id LIMIT %s FOR UPDATE SKIP LOCKED", [*values, max(1, min(int(limit), 100))])
                rows = [self._cursor_mapping(cursor, row) for row in cursor.fetchall()]
            claimed: list[dict[str, Any]] = []
            for row in rows:
                if row is None:
                    continue
                transitioned = self._pg_transition_job(conn, row=row, status="running", actor="job-worker", available_at=now, lease_until=lease_until)
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE trace_jobs SET attempts=attempts+1 WHERE job_id=%s", (row["job_id"],))
                    updated = self._pg_fetch_job(cursor, str(row["job_id"]))
                claimed.append(self._pg_job_row(updated))
            return claimed

    def complete_job(self, job_id: str, *, result: dict[str, Any] | None = None, actor: str = "job-worker") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "complete_job"):
            return self.delegate.complete_job(job_id, result=result, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "cancelled"}:
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="succeeded", actor=actor, result=result, lease_until=None)

    def fail_job(self, job_id: str, *, error: dict[str, Any], actor: str = "job-worker", retry: bool = True) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "fail_job"):
            return self.delegate.fail_job(job_id, error=error, actor=actor, retry=retry)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "cancelled"}:
                return self._pg_job_row(row)
            should_retry = retry and int(row["attempts"]) < int(row["max_attempts"]) and not row["cancel_requested"]
            if should_retry:
                delay = min(300, 2 ** max(0, int(row["attempts"]) - 1))
                return self._pg_transition_job(conn, row=row, status="queued", actor=actor, reason="retry_scheduled", error=error, available_at=datetime.fromtimestamp(datetime.now(UTC).timestamp() + delay, UTC), lease_until=None)
            return self._pg_transition_job(conn, row=row, status="failed", actor=actor, error=error, lease_until=None)

    def cancel_job(self, job_id: str, *, actor: str = "system", reason: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "cancel_job"):
            return self.delegate.cancel_job(job_id, actor=actor, reason=reason)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="cancelled", actor=actor, reason=reason or "cancelled_by_request", lease_until=None, cancel_requested=True)

    def retry_job(self, job_id: str, *, actor: str = "system") -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "retry_job"):
            return self.delegate.retry_job(job_id, actor=actor)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                row = self._pg_fetch_job(cursor, job_id, for_update=True)
            if row is None:
                raise NotFoundError(f"job {job_id} was not found")
            if row["status"] == "running":
                raise InvariantViolation("running jobs must expire or be cancelled before retry")
            if row["status"] == "succeeded":
                return self._pg_job_row(row)
            return self._pg_transition_job(conn, row=row, status="queued", actor=actor, reason="manual_retry", available_at=datetime.now(UTC), lease_until=None, cancel_requested=False)

    @classmethod
    def _pg_webhook_row(cls, row: dict[str, Any] | None, *, include_ciphertext: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("webhook was not found")
        result = dict(row)
        result["event_types"] = cls._json_value(result.pop("event_types"), [])
        ciphertext = result.pop("secret_ciphertext", None)
        if include_ciphertext:
            result["secret_ciphertext"] = ciphertext
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
        if self.delegate is not None and hasattr(self.delegate, "create_webhook"):
            return self.delegate.create_webhook(workspace_id=workspace_id, url=url, event_types=event_types, secret_hash=secret_hash, secret_ciphertext=secret_ciphertext, actor=actor)
        identifier = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self.connection() as conn:
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.created",
                payload={"webhook_id": identifier, "workspace_id": workspace_id, "url": url, "event_types": event_types, "secret_hash": secret_hash}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_webhooks(webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,'active',%s,%s)""",
                    (identifier, workspace_id, url, secret_hash, secret_ciphertext, json.dumps(event_types), event.offset, now),
                )
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (identifier,))
                result = self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()), include_ciphertext=True)
            return result

    def get_webhook(self, webhook_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_webhook"):
            return self.delegate.get_webhook(webhook_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                return self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def webhook_secret(self, webhook_id: str, *, cipher: Any) -> str:
        if self.delegate is not None and hasattr(self.delegate, "webhook_secret"):
            return self.delegate.webhook_secret(webhook_id, cipher=cipher)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT secret_ciphertext FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                row = cursor.fetchone()
        if not row:
            raise NotFoundError(f"webhook {webhook_id} was not found")
        return cipher.decrypt(row[0])

    def rotate_webhook(
        self,
        webhook_id: str,
        *,
        secret_hash: str,
        secret_ciphertext: str,
        actor: str,
    ) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "rotate_webhook"):
            return self.delegate.rotate_webhook(webhook_id, secret_hash=secret_hash, secret_ciphertext=secret_ciphertext, actor=actor)
        now = datetime.now(UTC)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT workspace_id FROM trace_webhooks WHERE webhook_id=%s FOR UPDATE", (webhook_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"webhook {webhook_id} was not found")
            workspace_id = str(row[0])
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="webhook.rotated",
                payload={"webhook_id": webhook_id, "workspace_id": workspace_id, "secret_hash": secret_hash}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_webhooks SET secret_hash=%s,secret_ciphertext=%s,rotated_at=%s WHERE webhook_id=%s", (secret_hash, secret_ciphertext, now, webhook_id))
                cursor.execute("SELECT webhook_id,workspace_id,url,secret_hash,secret_ciphertext,event_types,status,created_event_offset,created_at,rotated_at FROM trace_webhooks WHERE webhook_id=%s", (webhook_id,))
                result = self._pg_webhook_row(self._cursor_mapping(cursor, cursor.fetchone()), include_ciphertext=True)
            result["rotation_event_offset"] = event.offset
            return result

    @classmethod
    def _pg_api_key_row(cls, row: dict[str, Any] | None, *, include_hash: bool = False) -> dict[str, Any]:
        if not row:
            raise NotFoundError("API key was not found")
        result = dict(row)
        result["scopes"] = cls._json_value(result.pop("scopes"), [])
        result["allowed_visibility"] = cls._json_value(result.pop("allowed_visibility"), [])
        result["model_permissions"] = cls._json_value(result.pop("model_permissions"), [])
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
        if self.delegate is not None and hasattr(self.delegate, "create_api_key"):
            return self.delegate.create_api_key(workspace_id=workspace_id, subject=subject, key_prefix=key_prefix, key_hash=key_hash, scopes=scopes, allowed_visibility=allowed_visibility, model_permissions=model_permissions, expires_at=expires_at, actor=actor)
        identifier = str(uuid.uuid4())
        now = datetime.now(UTC)
        with self.connection() as conn:
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="api_key.created",
                payload={"api_key_id": identifier, "workspace_id": workspace_id, "subject": subject, "key_prefix": key_prefix, "scopes": scopes, "allowed_visibility": allowed_visibility, "model_permissions": model_permissions, "expires_at": expires_at}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO trace_api_keys(api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,'active',%s,%s,%s)""",
                    (identifier, workspace_id, subject, key_prefix, key_hash, json.dumps(scopes), json.dumps(allowed_visibility), json.dumps(model_permissions), expires_at, event.offset, now),
                )
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (identifier,))
                return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def get_api_key(self, api_key_id: str) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "get_api_key"):
            return self.delegate.get_api_key(api_key_id)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))

    def resolve_api_key(self, raw_key: str) -> dict[str, Any] | None:
        if self.delegate is not None and hasattr(self.delegate, "resolve_api_key"):
            return self.delegate.resolve_api_key(raw_key)
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE key_hash=%s AND status='active' AND (expires_at IS NULL OR expires_at>NOW())", (digest,))
                row = self._cursor_mapping(cursor, cursor.fetchone())
        return self._pg_api_key_row(row, include_hash=True) if row else None

    def revoke_api_key(self, api_key_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        if self.delegate is not None and hasattr(self.delegate, "revoke_api_key"):
            return self.delegate.revoke_api_key(api_key_id, actor=actor, reason=reason)
        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT set_config('trace.workspace_id', '*', true)")
                cursor.execute("SELECT workspace_id,status FROM trace_api_keys WHERE api_key_id=%s FOR UPDATE", (api_key_id,))
                row = cursor.fetchone()
            if not row:
                raise NotFoundError(f"API key {api_key_id} was not found")
            workspace_id, status = str(row[0]), row[1]
            if status == "revoked":
                with conn.cursor() as cursor:
                    cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                    return self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))
            event = self._append_event_in_connection(
                conn, stream_id=f"workspace:{workspace_id}", event_type="api_key.revoked",
                payload={"api_key_id": api_key_id, "workspace_id": workspace_id, "reason": reason}, actor=actor,
            )
            with conn.cursor() as cursor:
                cursor.execute("UPDATE trace_api_keys SET status='revoked',revoked_at=NOW() WHERE api_key_id=%s", (api_key_id,))
                cursor.execute("SELECT api_key_id,workspace_id,subject,key_prefix,key_hash,scopes,allowed_visibility,model_permissions,status,expires_at,created_event_offset,created_at,revoked_at FROM trace_api_keys WHERE api_key_id=%s", (api_key_id,))
                result = self._pg_api_key_row(self._cursor_mapping(cursor, cursor.fetchone()))
            result["revocation_event_offset"] = event.offset
            return result


class S3ObjectStore:
    """Private, content-addressed S3-compatible attachment storage.

    Canonical records retain only the returned object metadata and digest.  The
    object body never enters the event payload.  Server-side encryption is
    requested on every write; deployments may additionally encrypt client-side
    before calling this adapter.
    """

    def __init__(
        self,
        bucket: str,
        *,
        client: Any | None = None,
        prefix: str = "trace/attachments",
        kms_key_id: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.kms_key_id = kms_key_id or os.environ.get("TRACE_OBJECT_KMS_KEY_ID")
        if client is None:
            try:
                import boto3
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("boto3 is required for S3ObjectStore") from error
            client = boto3.client("s3", endpoint_url=endpoint_url or os.environ.get("TRACE_S3_ENDPOINT"))
        self.client = client

    def _put(self, raw: bytes, media_type: str, *, workspace_id: str | None = None) -> dict[str, Any]:
        digest = hashlib.sha256(raw).hexdigest()
        safe_workspace = re.sub(r"[^A-Za-z0-9_.-]", "_", workspace_id or "unassigned")
        tenant_prefix = f"workspace/{safe_workspace}/"
        key = f"{self.prefix}/{tenant_prefix}{digest}"
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": raw,
            "ContentType": media_type,
            "Metadata": {"sha256": digest, "tenant": workspace_id or "unassigned"},
            "ServerSideEncryption": "aws:kms" if self.kms_key_id else "AES256",
        }
        if self.kms_key_id:
            kwargs["SSEKMSKeyId"] = self.kms_key_id
        self.client.put_object(**kwargs)
        return {
            "content_hash": digest,
            "object_key": key,
            "media_type": media_type,
            "byte_length": len(raw),
            "metadata": {"storage": "s3", "bucket": self.bucket, "encrypted": True},
        }

    def put_bytes(self, raw: bytes, media_type: str, *, workspace_id: str | None = None, **_: Any) -> dict[str, Any]:
        return self._put(raw, media_type, workspace_id=workspace_id)

    def put_text(self, text: str, media_type: str, *, workspace_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.put_bytes(text.encode("utf-8"), media_type, workspace_id=workspace_id, **kwargs)

    def presign_get(self, object_key: str, *, expires_seconds: int = 300) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": object_key}, ExpiresIn=max(1, min(expires_seconds, 86_400))
        )


class OpenSearchLexicalIndex:
    """BM25/OpenSearch adapter with mandatory tenant and visibility filters."""

    provider_id = "opensearch-bm25-v1"

    def __init__(self, index: str, *, client: Any | None = None, hosts: Sequence[str] | None = None) -> None:
        self.index = index
        if client is None:
            try:
                from opensearchpy import OpenSearch
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("opensearch-py is required for OpenSearchLexicalIndex") from error
            client = OpenSearch(list(hosts or [os.environ.get("TRACE_OPENSEARCH_URL", "http://localhost:9200")]))
        self.client = client

    @staticmethod
    def _filters(workspace_id: str, visibility: Sequence[str] | None, facets: Sequence[str] | None, as_of_event: int | None, index_revision: str | None = None) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
        if visibility:
            filters.append({"terms": {"visibility": list(visibility)}})
        if facets:
            filters.extend({"term": {"facets": facet}} for facet in facets)
        if as_of_event is not None:
            filters.append({"range": {"created_event_offset": {"lte": as_of_event}}})
        if index_revision is not None:
            filters.append({"term": {"index_revision": index_revision}})
        return filters

    def search(self, *, workspace_id: str, query: str, limit: int, visibility: Sequence[str] | None = None, facets: Sequence[str] | None = None, as_of_event: int | None = None, index_revision: str | None = None) -> list[dict[str, Any]]:
        body = {
            "size": max(1, min(limit, 1_000)),
            "query": {"bool": {"must": [{"multi_match": {"query": query, "fields": ["content^2", "title", "source.uri"]}}], "filter": self._filters(workspace_id, visibility, facets, as_of_event, index_revision)}},
            "_source": True,
        }
        response = self.client.search(index=self.index, body=body)
        hits = response.get("hits", {}).get("hits", [])
        return [{**hit.get("_source", {}), "atom_version_id": hit.get("_id"), "lexical_score": float(hit.get("_score") or 0.0)} for hit in hits]

    def upsert(self, documents: Iterable[dict[str, Any]], *, revision: str) -> int:
        count = 0
        for document in documents:
            atom_id = document.get("atom_version_id")
            if not atom_id:
                continue
            payload = {**document, "index_revision": revision}
            self.client.index(index=self.index, id=atom_id, body=payload, refresh=False)
            count += 1
        return count

    def activate_revision(self, revision_index: str, *, alias: str | None = None) -> None:
        """Atomically move a read alias to a fully rebuilt revision index."""

        alias = alias or self.index
        self.client.indices.update_aliases(body={"actions": [
            {"remove": {"alias": alias, "index": "*"}},
            {"add": {"alias": alias, "index": revision_index}},
        ]})


class QdrantDenseIndex:
    """Qdrant adapter keyed by atom version and dense index revision."""

    provider_id = "qdrant-bge-m3-v1"

    def __init__(self, collection: str, *, client: Any | None = None, url: str | None = None, api_key: str | None = None) -> None:
        self.collection = collection
        if client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("qdrant-client is required for QdrantDenseIndex") from error
            client = QdrantClient(url=url or os.environ.get("TRACE_QDRANT_URL"), api_key=api_key or os.environ.get("TRACE_QDRANT_API_KEY"))
        self.client = client

    @staticmethod
    def _filter(workspace_id: str, visibility: Sequence[str] | None, facets: Sequence[str] | None, as_of_event: int | None, index_revision: str | None = None) -> Any:
        conditions: list[dict[str, Any]] = [{"key": "workspace_id", "match": {"value": workspace_id}}]
        if visibility:
            conditions.append({"should": [{"key": "visibility", "match": {"value": item}} for item in visibility]})
        if facets:
            conditions.extend({"key": "facets", "match": {"value": facet}} for facet in facets)
        if as_of_event is not None:
            conditions.append({"key": "created_event_offset", "range": {"lte": as_of_event}})
        if index_revision is not None:
            conditions.append({"key": "index_revision", "match": {"value": index_revision}})
        return {"must": conditions}

    def search(self, *, workspace_id: str, vector: Sequence[float], limit: int, visibility: Sequence[str] | None = None, facets: Sequence[str] | None = None, as_of_event: int | None = None, index_revision: str | None = None) -> list[dict[str, Any]]:
        query_filter = self._filter(workspace_id, visibility, facets, as_of_event, index_revision)
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(collection_name=self.collection, query=list(vector), query_filter=query_filter, limit=max(1, min(limit, 1_000)), with_payload=True)
            points = response.get("points", []) if isinstance(response, dict) else getattr(response, "points", response)
        else:  # qdrant-client versions before query_points
            points = self.client.search(collection_name=self.collection, query_vector=list(vector), query_filter=query_filter, limit=max(1, min(limit, 1_000)), with_payload=True)
        output: list[dict[str, Any]] = []
        for point in points:
            if isinstance(point, dict):
                payload = dict(point.get("payload") or {})
                point_id = point.get("id")
                score = point.get("score", 0.0)
            else:
                payload = dict(getattr(point, "payload", None) or {})
                point_id = getattr(point, "id", None)
                score = getattr(point, "score", 0.0)
            output.append({**payload, "atom_version_id": str(payload.get("atom_version_id") or point_id), "dense_score": float(score or 0.0)})
        return output

    def upsert(self, vectors: Iterable[dict[str, Any]], *, revision: str) -> int:
        injected_client = self.client is not None
        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            if not injected_client:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("qdrant-client models are required for QdrantDenseIndex")
            PointStruct = None
        points = []
        for item in vectors:
            atom_version_id = str(item["atom_version_id"])
            payload = {key: value for key, value in item.items() if key != "vector"}
            payload["atom_version_id"] = atom_version_id
            payload["index_revision"] = revision
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"trace:qdrant:{atom_version_id}:{revision}"))
            points.append(
                PointStruct(id=point_id, vector=list(item["vector"]), payload=payload)
                if PointStruct is not None
                else {"id": point_id, "vector": list(item["vector"]), "payload": payload}
            )
        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)


class NatsJetStreamPublisher:
    """NATS JetStream outbox publisher with explicit durable subject naming."""

    def __init__(self, *, servers: Sequence[str] | None = None, stream: str = "TRACE_EVENTS", client: Any | None = None) -> None:
        self.servers = list(servers or [os.environ.get("TRACE_NATS_URL", "nats://localhost:4222")])
        self.stream = stream
        self.client = client

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        if self.client is None:
            try:
                import nats
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("nats-py is required for NatsJetStreamPublisher") from error
        self.client = await nats.connect(servers=self.servers)
        subject = f"{self.stream.lower()}.{topic.replace('.', '_')}"
        body = json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hasattr(self.client, "jetstream"):
            await self.client.jetstream().publish(subject, body)
        else:
            await self.client.publish(subject, body)


class RedisCoordinationStore:
    """Redis TTL cache/coordination adapter; values are never canonical truth."""

    def __init__(self, url: str | None = None, *, client: Any | None = None) -> None:
        if client is None:
            try:
                import redis
            except ImportError as error:  # pragma: no cover - optional production dependency
                raise ProductionAdapterError("redis is required for RedisCoordinationStore") from error
            client = redis.Redis.from_url(url or os.environ.get("TRACE_REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
        self.client = client

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self.client.set(key, value, ex=max(1, min(int(ttl_seconds), 86_400 * 30)))

    def delete(self, key: str) -> None:
        self.client.delete(key)


class InMemoryCoordinationStore:
    """Small deterministic coordination substitute for unit tests."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        item = self._values.get(key)
        if not item:
            return None
        value, expires = item
        if expires <= time.time():
            self._values.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        self._values[key] = (value, time.time() + max(1, ttl_seconds))

    def delete(self, key: str) -> None:
        self._values.pop(key, None)
