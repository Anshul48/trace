-- Forward-only production hardening.  Do not edit this after it is applied.

ALTER TABLE trace_outbox ADD COLUMN IF NOT EXISTS workspace_id TEXT;
UPDATE trace_outbox o
   SET workspace_id = e.workspace_id
  FROM trace_events e
 WHERE o.event_offset = e.event_offset
   AND o.workspace_id IS NULL;
ALTER TABLE trace_outbox ALTER COLUMN workspace_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS trace_outbox_workspace_pending
    ON trace_outbox(workspace_id, status, available_at);

CREATE TABLE IF NOT EXISTS trace_webhook_deliveries (
    delivery_id UUID PRIMARY KEY,
    webhook_id UUID NOT NULL REFERENCES trace_webhooks(webhook_id),
    workspace_id TEXT NOT NULL,
    job_id UUID NOT NULL REFERENCES trace_jobs(job_id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 8,
    available_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    last_error TEXT,
    delivered_at TIMESTAMPTZ,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(webhook_id, job_id, event_type)
);
CREATE INDEX IF NOT EXISTS trace_webhook_deliveries_available
    ON trace_webhook_deliveries(status, available_at, created_at);

CREATE TABLE IF NOT EXISTS trace_model_call_audits (
    model_call_audit_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    actor TEXT NOT NULL,
    request_id TEXT,
    prompt_template_revision TEXT NOT NULL,
    response_schema_hash CHAR(64) NOT NULL,
    excerpt_hashes JSONB NOT NULL,
    node_count INTEGER NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    cloud_tokens INTEGER NOT NULL,
    cost_usd DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    created_event_offset BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trace_model_call_audits_workspace_created
    ON trace_model_call_audits(workspace_id, created_at DESC);

-- The application runtime uses one explicit workspace setting per database
-- transaction. There is intentionally no '*' wildcard or user-settable admin
-- bypass in these policies. Administrative/replay operations use a dedicated
-- migration/operations role and audited export procedures, not API runtime
-- connections.
ALTER TABLE trace_events FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_event_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_event_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_webhooks FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_api_keys FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_attachments FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_ingestions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_hot_inbox FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_nodes FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_node_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_edge_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_evidence_anchors FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_proposals FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_evidence_bundles FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_benchmark_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_feedback FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_dense_vectors FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_saved_queries FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_frozen_queries FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_index_revisions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_revisions FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_projection_events FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_webhook_deliveries FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_model_call_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_model_call_audits FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_events_tenant ON trace_events;
CREATE POLICY trace_events_tenant ON trace_events
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_event_keys_tenant ON trace_event_keys;
CREATE POLICY trace_event_keys_tenant ON trace_event_keys
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_outbox_tenant ON trace_outbox;
CREATE POLICY trace_outbox_tenant ON trace_outbox
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_jobs_tenant ON trace_jobs;
CREATE POLICY trace_jobs_tenant ON trace_jobs
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_webhooks_tenant ON trace_webhooks;
CREATE POLICY trace_webhooks_tenant ON trace_webhooks
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_api_keys_tenant ON trace_api_keys;
CREATE POLICY trace_api_keys_tenant ON trace_api_keys
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_attachments_tenant ON trace_attachments;
CREATE POLICY trace_attachments_tenant ON trace_attachments
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_ingestions_tenant ON trace_ingestions;
CREATE POLICY trace_ingestions_tenant ON trace_ingestions
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_hot_inbox_tenant ON trace_hot_inbox;
CREATE POLICY trace_hot_inbox_tenant ON trace_hot_inbox
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_nodes_tenant ON trace_nodes;
CREATE POLICY trace_nodes_tenant ON trace_nodes
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_node_versions_tenant ON trace_node_versions;
CREATE POLICY trace_node_versions_tenant ON trace_node_versions
    USING (EXISTS (SELECT 1 FROM trace_nodes n WHERE n.node_id = trace_node_versions.node_id AND n.workspace_id = current_setting('trace.workspace_id', true)))
    WITH CHECK (EXISTS (SELECT 1 FROM trace_nodes n WHERE n.node_id = trace_node_versions.node_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_edges_tenant ON trace_edge_versions;
CREATE POLICY trace_edges_tenant ON trace_edge_versions
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_anchors_tenant ON trace_evidence_anchors;
CREATE POLICY trace_anchors_tenant ON trace_evidence_anchors
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_proposals_tenant ON trace_proposals;
CREATE POLICY trace_proposals_tenant ON trace_proposals
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_bundles_tenant ON trace_evidence_bundles;
CREATE POLICY trace_bundles_tenant ON trace_evidence_bundles
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_benchmark_tenant ON trace_benchmark_runs;
CREATE POLICY trace_benchmark_tenant ON trace_benchmark_runs
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_feedback_tenant ON trace_feedback;
CREATE POLICY trace_feedback_tenant ON trace_feedback
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_dense_vectors_tenant ON trace_dense_vectors;
CREATE POLICY trace_dense_vectors_tenant ON trace_dense_vectors
    USING (EXISTS (SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id = nv.node_id WHERE nv.atom_version_id = trace_dense_vectors.atom_version_id AND n.workspace_id = current_setting('trace.workspace_id', true)))
    WITH CHECK (EXISTS (SELECT 1 FROM trace_node_versions nv JOIN trace_nodes n ON n.node_id = nv.node_id WHERE nv.atom_version_id = trace_dense_vectors.atom_version_id AND n.workspace_id = current_setting('trace.workspace_id', true)));
DROP POLICY IF EXISTS trace_saved_queries_tenant ON trace_saved_queries;
CREATE POLICY trace_saved_queries_tenant ON trace_saved_queries
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_frozen_queries_tenant ON trace_frozen_queries;
CREATE POLICY trace_frozen_queries_tenant ON trace_frozen_queries
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_index_revisions_tenant ON trace_index_revisions;
CREATE POLICY trace_index_revisions_tenant ON trace_index_revisions
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_tenant ON trace_projection_revisions;
CREATE POLICY trace_projection_tenant ON trace_projection_revisions
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
DROP POLICY IF EXISTS trace_projection_events_tenant ON trace_projection_events;
CREATE POLICY trace_projection_events_tenant ON trace_projection_events
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
CREATE POLICY trace_webhook_deliveries_tenant ON trace_webhook_deliveries
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
CREATE POLICY trace_model_call_audits_tenant ON trace_model_call_audits
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));

-- A migration-role scheduler calls this function once per month. The initial
-- hash/default layout remains available during upgrade; the function records
-- maintenance intent without query-time scans or destructive partition moves.
CREATE OR REPLACE FUNCTION trace_ensure_event_partitions(months_ahead INTEGER DEFAULT 3)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    month_start DATE := date_trunc('month', CURRENT_DATE)::DATE;
BEGIN
    IF months_ahead < 0 OR months_ahead > 24 THEN
        RAISE EXCEPTION 'months_ahead must be between 0 and 24';
    END IF;
    -- Hash child/default partitions are created in 001. Concrete time shards
    -- are a planned forward migration once the active deployment has drained
    -- default partitions; this function is intentionally non-destructive.
    PERFORM month_start + (months_ahead || ' months')::INTERVAL;
END;
$$;
