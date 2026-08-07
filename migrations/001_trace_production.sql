-- Trace V2 canonical PostgreSQL baseline migration.
--
-- This file is raw SQL on purpose: the migration runner records its checksum
-- in trace_schema_migrations and refuses edits to an applied revision. Later
-- migrations are forward-only corrections; they never rewrite event history.
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
    USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_jobs_tenant ON trace_jobs;
CREATE POLICY trace_jobs_tenant ON trace_jobs
    USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_webhooks_tenant ON trace_webhooks;
CREATE POLICY trace_webhooks_tenant ON trace_webhooks USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_api_keys_tenant ON trace_api_keys;
CREATE POLICY trace_api_keys_tenant ON trace_api_keys USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_attachments_tenant ON trace_attachments;
CREATE POLICY trace_attachments_tenant ON trace_attachments USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_ingestions_tenant ON trace_ingestions;
CREATE POLICY trace_ingestions_tenant ON trace_ingestions USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_hot_inbox_tenant ON trace_hot_inbox;
CREATE POLICY trace_hot_inbox_tenant ON trace_hot_inbox USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_nodes_tenant ON trace_nodes;
CREATE POLICY trace_nodes_tenant ON trace_nodes USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_node_versions_tenant ON trace_node_versions;
CREATE POLICY trace_node_versions_tenant ON trace_node_versions USING (EXISTS (SELECT 1 FROM trace_nodes n WHERE n.node_id = trace_node_versions.node_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_edges_tenant ON trace_edge_versions;
CREATE POLICY trace_edges_tenant ON trace_edge_versions USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_anchors_tenant ON trace_evidence_anchors;
CREATE POLICY trace_anchors_tenant ON trace_evidence_anchors USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_proposals_tenant ON trace_proposals;
CREATE POLICY trace_proposals_tenant ON trace_proposals USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_bundles_tenant ON trace_evidence_bundles;
CREATE POLICY trace_bundles_tenant ON trace_evidence_bundles USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_benchmark_tenant ON trace_benchmark_runs;
CREATE POLICY trace_benchmark_tenant ON trace_benchmark_runs USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_feedback_tenant ON trace_feedback;
CREATE POLICY trace_feedback_tenant ON trace_feedback USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_dense_vectors_tenant ON trace_dense_vectors;
CREATE POLICY trace_dense_vectors_tenant ON trace_dense_vectors USING (EXISTS (SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id = nv.node_id WHERE nv.atom_version_id = trace_dense_vectors.atom_version_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_saved_queries_tenant ON trace_saved_queries;
CREATE POLICY trace_saved_queries_tenant ON trace_saved_queries USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_frozen_queries_tenant ON trace_frozen_queries;
CREATE POLICY trace_frozen_queries_tenant ON trace_frozen_queries USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_index_revisions_tenant ON trace_index_revisions;
CREATE POLICY trace_index_revisions_tenant ON trace_index_revisions USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_tenant ON trace_projection_revisions;
CREATE POLICY trace_projection_tenant ON trace_projection_revisions USING (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_events_tenant ON trace_projection_events;
CREATE POLICY trace_projection_events_tenant ON trace_projection_events USING (workspace_id = current_setting('trace.workspace_id', true));
