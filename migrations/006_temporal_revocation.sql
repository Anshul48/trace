-- Forward-only migration 006: temporal validity, source lifecycle, and
-- historical release watermarks.
--
-- The migration is additive. Existing event payloads and prior migration files
-- are immutable; legacy node versions receive an explicit active/unknown
-- lifecycle row so replay does not invent valid-time boundaries. Compliance
-- erasure is performed by the repository transaction, not by this migration.

ALTER TABLE trace_cortex_releases
    ADD COLUMN IF NOT EXISTS activated_event_offset BIGINT;

ALTER TABLE trace_cortex_releases
    ADD COLUMN IF NOT EXISTS superseded_event_offset BIGINT;

-- A release's first activation is the historical pointer used by the resolver.
-- Legacy rows have no activation event, so their spine watermark is the only
-- conservative migration identity available until a new release is activated.
UPDATE trace_cortex_releases
   SET activated_event_offset = COALESCE(activated_event_offset, spine_event_watermark)
 WHERE status IN ('active', 'superseded', 'retired');

CREATE INDEX IF NOT EXISTS trace_cortex_releases_event_window
    ON trace_cortex_releases(workspace_id, activated_event_offset, superseded_event_offset);

CREATE TABLE IF NOT EXISTS trace_source_lifecycle (
    atom_version_id UUID PRIMARY KEY REFERENCES trace_node_versions(atom_version_id),
    workspace_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active','superseded','revoked','tombstoned','conflicted','redacted_purged')),
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    valid_precision TEXT NOT NULL DEFAULT 'unknown',
    valid_confidence TEXT NOT NULL DEFAULT 'unknown',
    valid_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    predecessor_atom_version_id UUID REFERENCES trace_node_versions(atom_version_id),
    superseded_by_atom_version_id UUID REFERENCES trace_node_versions(atom_version_id),
    changed_event_offset BIGINT NOT NULL,
    erasure_receipt JSONB,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS trace_source_lifecycle_workspace_state
    ON trace_source_lifecycle(workspace_id, state, changed_event_offset);

-- Existing rows are explicit about what is known: active lifecycle, unknown
-- valid time, and the version's immutable creation offset. No date inference
-- is performed from ingestion timestamps or source metadata.
INSERT INTO trace_source_lifecycle (
    atom_version_id, workspace_id, state, valid_from, valid_to,
    valid_precision, valid_confidence, valid_provenance,
    changed_event_offset, created_at
)
SELECT nv.atom_version_id, n.workspace_id, 'active', NULL, NULL,
       'unknown', 'unknown', '{}'::jsonb, nv.created_event_offset, NOW()
  FROM trace_node_versions nv
  JOIN trace_nodes n ON n.node_id = nv.node_id
 ON CONFLICT (atom_version_id) DO NOTHING;

ALTER TABLE trace_source_lifecycle ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_source_lifecycle FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_source_lifecycle_tenant ON trace_source_lifecycle;
CREATE POLICY trace_source_lifecycle_tenant ON trace_source_lifecycle
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));

