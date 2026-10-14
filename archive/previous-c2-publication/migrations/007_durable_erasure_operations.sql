-- Forward-only migration 007: durable fail-closed erasure state machine
--
-- Tracks multi-phase compliance erasure operations across storage engines,
-- external vector/lexical index revisions, and database state.
--
-- Lifecycle states:
--   - pending: operation initiated, read-denial hold active
--   - external_absence_verified: object storage and external index revisions verified absent
--   - completed: database finalization complete, signed receipt issued
--   - retryable_failure: transient failure encountered, retryable from recorded targets

CREATE TABLE IF NOT EXISTS trace_erasure_operations (
    operation_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    atom_version_id UUID NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'external_absence_verified', 'completed', 'retryable_failure')),
    object_key TEXT,
    external_targets JSONB NOT NULL DEFAULT '[]'::jsonb,
    erasure_receipt JSONB,
    event_offset BIGINT,
    failure_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workspace_id, atom_version_id)
);

CREATE INDEX IF NOT EXISTS trace_erasure_operations_lookup
    ON trace_erasure_operations(workspace_id, atom_version_id, state);

ALTER TABLE trace_erasure_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_erasure_operations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_erasure_operations_tenant ON trace_erasure_operations;
CREATE POLICY trace_erasure_operations_tenant ON trace_erasure_operations
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
