-- Additive Trace V2 Cortex projection control plane.
--
-- These tables are intentionally outside the canonical node/edge truth
-- tables. Dropping and rebuilding this layer must leave Spine events,
-- attachments, atom versions, trusted edge versions, and evidence anchors
-- unchanged.

CREATE TABLE IF NOT EXISTS trace_attachment_staging (
    staging_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    content_hash CHAR(64) NOT NULL,
    object_key TEXT NOT NULL,
    attachment JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged','committed','cleanup_required')),
    ingestion_id UUID,
    canonical_event_offset BIGINT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_attachment_staging_reconcile
    ON trace_attachment_staging(status, workspace_id, created_at);

CREATE TABLE IF NOT EXISTS trace_ingestion_index_state (
    ingestion_id UUID NOT NULL REFERENCES trace_ingestions(ingestion_id),
    workspace_id TEXT NOT NULL,
    component TEXT NOT NULL CHECK (component IN ('hot','lexical','dense')),
    status TEXT NOT NULL CHECK (status IN ('hot_ready','lexical_ready','dense_pending','dense_ready','failed','stale','pending')),
    index_revision TEXT,
    job_id UUID,
    run_id UUID,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_event_offset BIGINT,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(ingestion_id, component)
);
CREATE INDEX IF NOT EXISTS trace_ingestion_index_state_workspace
    ON trace_ingestion_index_state(workspace_id, status, updated_at);

CREATE TABLE IF NOT EXISTS trace_cognitive_policy_versions (
    cognitive_policy_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    policy_revision TEXT NOT NULL,
    policy JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    actor TEXT NOT NULL,
    UNIQUE(workspace_id, policy_revision)
);
CREATE UNIQUE INDEX IF NOT EXISTS trace_cognitive_policy_active
    ON trace_cognitive_policy_versions(workspace_id) WHERE active;

CREATE TABLE IF NOT EXISTS trace_projection_runs (
    projection_run_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    projection_kind TEXT NOT NULL CHECK (projection_kind IN ('hierarchy','affinity','activation')),
    revision TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','superseded','active')),
    input_from_event BIGINT,
    input_through_event BIGINT,
    input_checksum CHAR(64) NOT NULL,
    output_statistics JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_revision TEXT,
    index_revision TEXT,
    prompt_revision TEXT,
    policy_revision TEXT NOT NULL,
    prior_projection_run_id UUID REFERENCES trace_projection_runs(projection_run_id),
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    failure_detail TEXT,
    created_event_offset BIGINT NOT NULL,
    activated_event_offset BIGINT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(workspace_id, projection_kind, revision)
);
CREATE INDEX IF NOT EXISTS trace_projection_runs_workspace_kind
    ON trace_projection_runs(workspace_id, projection_kind, status, created_at DESC);

CREATE TABLE IF NOT EXISTS trace_projection_objects (
    projection_object_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    projection_run_id UUID NOT NULL REFERENCES trace_projection_runs(projection_run_id),
    object_kind TEXT NOT NULL,
    logical_key TEXT NOT NULL,
    content TEXT NOT NULL,
    source_atom_version_ids JSONB NOT NULL,
    properties JSONB NOT NULL,
    content_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(projection_run_id, logical_key)
);
CREATE INDEX IF NOT EXISTS trace_projection_objects_frontier
    ON trace_projection_objects(workspace_id, projection_run_id, object_kind, logical_key);

CREATE TABLE IF NOT EXISTS trace_projection_memberships (
    projection_membership_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    projection_run_id UUID NOT NULL REFERENCES trace_projection_runs(projection_run_id),
    parent_projection_object_id UUID NOT NULL REFERENCES trace_projection_objects(projection_object_id),
    child_kind TEXT NOT NULL CHECK (child_kind IN ('projection_object','atom_version')),
    child_id UUID NOT NULL,
    ordinal INTEGER NOT NULL DEFAULT 0,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(projection_run_id, parent_projection_object_id, child_kind, child_id)
);
CREATE INDEX IF NOT EXISTS trace_projection_memberships_parent
    ON trace_projection_memberships(workspace_id, projection_run_id, parent_projection_object_id, ordinal);

CREATE TABLE IF NOT EXISTS trace_affinity_edges (
    affinity_edge_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    left_atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    right_atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    pair_key TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL CHECK (score >= 0 AND score <= 1),
    signal JSONB NOT NULL,
    index_revision TEXT,
    embedding_revision TEXT,
    projection_run_id UUID REFERENCES trace_projection_runs(projection_run_id),
    status TEXT NOT NULL CHECK (status IN ('active','stale','rejected','expired')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_event_offset BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(workspace_id, pair_key),
    CHECK (left_atom_version_id <> right_atom_version_id)
);
CREATE INDEX IF NOT EXISTS trace_affinity_edges_lookup
    ON trace_affinity_edges(workspace_id, left_atom_version_id, right_atom_version_id, status, expires_at);

CREATE TABLE IF NOT EXISTS trace_affinity_rejections (
    affinity_rejection_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    pair_key TEXT NOT NULL,
    left_atom_version_id UUID NOT NULL,
    right_atom_version_id UUID NOT NULL,
    reason TEXT,
    actor TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(workspace_id, pair_key),
    CHECK (left_atom_version_id <> right_atom_version_id)
);
CREATE INDEX IF NOT EXISTS trace_affinity_rejections_lookup
    ON trace_affinity_rejections(workspace_id, pair_key, expires_at);

CREATE TABLE IF NOT EXISTS trace_activation_priors (
    activation_prior_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    atom_version_id UUID NOT NULL REFERENCES trace_node_versions(atom_version_id),
    prior_kind TEXT NOT NULL CHECK (prior_kind IN ('pin','recency','feedback','suppression','co_retrieval')),
    score DOUBLE PRECISION NOT NULL CHECK (score >= -1 AND score <= 1),
    provenance JSONB NOT NULL,
    expires_at TIMESTAMPTZ,
    created_event_offset BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(workspace_id, atom_version_id, prior_kind)
);
CREATE INDEX IF NOT EXISTS trace_activation_priors_lookup
    ON trace_activation_priors(workspace_id, atom_version_id, expires_at);

ALTER TABLE trace_attachment_staging ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_attachment_staging FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_ingestion_index_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_ingestion_index_state FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_cognitive_policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_cognitive_policy_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_objects FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_affinity_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_affinity_edges FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_affinity_rejections ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_affinity_rejections FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_activation_priors ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_activation_priors FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_attachment_staging_tenant ON trace_attachment_staging;
CREATE POLICY trace_attachment_staging_tenant ON trace_attachment_staging
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_ingestion_index_state_tenant ON trace_ingestion_index_state;
CREATE POLICY trace_ingestion_index_state_tenant ON trace_ingestion_index_state
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_cognitive_policy_versions_tenant ON trace_cognitive_policy_versions;
CREATE POLICY trace_cognitive_policy_versions_tenant ON trace_cognitive_policy_versions
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_runs_tenant ON trace_projection_runs;
CREATE POLICY trace_projection_runs_tenant ON trace_projection_runs
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_objects_tenant ON trace_projection_objects;
CREATE POLICY trace_projection_objects_tenant ON trace_projection_objects
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_memberships_tenant ON trace_projection_memberships;
CREATE POLICY trace_projection_memberships_tenant ON trace_projection_memberships
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_affinity_edges_tenant ON trace_affinity_edges;
CREATE POLICY trace_affinity_edges_tenant ON trace_affinity_edges
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_affinity_rejections_tenant ON trace_affinity_rejections;
CREATE POLICY trace_affinity_rejections_tenant ON trace_affinity_rejections
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_activation_priors_tenant ON trace_activation_priors;
CREATE POLICY trace_activation_priors_tenant ON trace_activation_priors
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
