-- Forward-only migration 005: Unified Trace Cortex Release Lifecycle.
--
-- Introduces candidate-scoped derived projections, release manifests,
-- and atomic multi-component activation/rollback while isolating candidate
-- affinity edges and activation priors from ordinary queries.

-- ============================================================================
-- 1. Create trace_cortex_releases (Release Root)
-- ============================================================================
CREATE TABLE IF NOT EXISTS trace_cortex_releases (
    release_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    parent_release_id UUID REFERENCES trace_cortex_releases(release_id),
    spine_event_watermark BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned','building','validating','validated','active','superseded','retired','failed')),
    policy_revision TEXT NOT NULL,
    policy_snapshot_hash CHAR(64) NOT NULL,
    code_revision TEXT NOT NULL,
    validation_receipt JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    failure_detail TEXT
);

-- Partial unique index ensuring at most ONE active release per workspace
CREATE UNIQUE INDEX IF NOT EXISTS trace_cortex_releases_active
    ON trace_cortex_releases(workspace_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS trace_cortex_releases_workspace_status
    ON trace_cortex_releases(workspace_id, status, activated_at DESC);

CREATE INDEX IF NOT EXISTS trace_cortex_releases_parent
    ON trace_cortex_releases(parent_release_id) WHERE parent_release_id IS NOT NULL;

-- ============================================================================
-- 2. Create trace_cortex_release_components (Component Manifest)
-- ============================================================================
CREATE TABLE IF NOT EXISTS trace_cortex_release_components (
    release_id UUID NOT NULL REFERENCES trace_cortex_releases(release_id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL,
    component_kind TEXT NOT NULL CHECK (component_kind IN ('hierarchy', 'affinity', 'activation_priors', 'lexical_index', 'dense_index')),
    component_revision TEXT NOT NULL,
    input_checksum CHAR(64) NOT NULL,
    source_watermark BIGINT NOT NULL,
    carried_forward_from_release_id UUID REFERENCES trace_cortex_releases(release_id),
    validation_status TEXT NOT NULL CHECK (validation_status IN ('pending', 'validated', 'failed')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (release_id, component_kind)
);

CREATE INDEX IF NOT EXISTS trace_cortex_release_components_workspace
    ON trace_cortex_release_components(workspace_id, component_kind, validation_status);

CREATE INDEX IF NOT EXISTS trace_cortex_release_components_carried
    ON trace_cortex_release_components(carried_forward_from_release_id)
    WHERE carried_forward_from_release_id IS NOT NULL;

-- ============================================================================
-- 3. Add release_id to trace_affinity_edges & trace_activation_priors
-- ============================================================================
ALTER TABLE trace_affinity_edges
    ADD COLUMN IF NOT EXISTS release_id UUID REFERENCES trace_cortex_releases(release_id);

ALTER TABLE trace_activation_priors
    ADD COLUMN IF NOT EXISTS release_id UUID REFERENCES trace_cortex_releases(release_id);

-- ============================================================================
-- 4. Bootstrap-v0 Backfill for Existing Workspaces
-- ============================================================================
-- A. Create bootstrap-v0 release for each workspace with existing data
INSERT INTO trace_cortex_releases (
    release_id,
    workspace_id,
    parent_release_id,
    spine_event_watermark,
    status,
    policy_revision,
    policy_snapshot_hash,
    code_revision,
    validation_receipt,
    created_at,
    activated_at
)
SELECT
    gen_random_uuid(),
    w.workspace_id,
    NULL,
    COALESCE((SELECT MAX(event_offset) FROM trace_events e WHERE e.workspace_id = w.workspace_id), 0),
    'active',
    'bootstrap-v0',
    '0000000000000000000000000000000000000000000000000000000000000000',
    'bootstrap-v0',
    '{"bootstrap": true, "note": "Backfilled legacy un-scoped rows"}'::jsonb,
    NOW(),
    NOW()
FROM (
    SELECT DISTINCT workspace_id FROM trace_affinity_edges WHERE release_id IS NULL
    UNION
    SELECT DISTINCT workspace_id FROM trace_activation_priors WHERE release_id IS NULL
    UNION
    SELECT DISTINCT workspace_id FROM trace_nodes
) w
WHERE NOT EXISTS (
    SELECT 1 FROM trace_cortex_releases r
    WHERE r.workspace_id = w.workspace_id AND r.status = 'active'
);

-- B. Create component manifests for the bootstrap-v0 releases
INSERT INTO trace_cortex_release_components (
    release_id,
    workspace_id,
    component_kind,
    component_revision,
    input_checksum,
    source_watermark,
    carried_forward_from_release_id,
    validation_status,
    metadata,
    created_at
)
SELECT
    r.release_id,
    r.workspace_id,
    k.component_kind,
    'bootstrap-v0',
    '0000000000000000000000000000000000000000000000000000000000000000',
    r.spine_event_watermark,
    NULL,
    'validated',
    '{"bootstrap": true}'::jsonb,
    r.created_at
FROM trace_cortex_releases r
CROSS JOIN (
    VALUES ('hierarchy'), ('affinity'), ('activation_priors'), ('lexical_index'), ('dense_index')
) AS k(component_kind)
WHERE r.policy_revision = 'bootstrap-v0'
ON CONFLICT (release_id, component_kind) DO NOTHING;

-- C. Backfill release_id on existing rows
UPDATE trace_affinity_edges a
   SET release_id = r.release_id
  FROM trace_cortex_releases r
 WHERE a.workspace_id = r.workspace_id
   AND r.status = 'active'
   AND a.release_id IS NULL;

UPDATE trace_activation_priors p
   SET release_id = r.release_id
  FROM trace_cortex_releases r
 WHERE p.workspace_id = r.workspace_id
   AND r.status = 'active'
   AND p.release_id IS NULL;

-- D. Enforce NOT NULL on release_id
ALTER TABLE trace_affinity_edges ALTER COLUMN release_id SET NOT NULL;
ALTER TABLE trace_activation_priors ALTER COLUMN release_id SET NOT NULL;

-- ============================================================================
-- 5. Update Constraints and Indexes for Candidate Scoping
-- ============================================================================
-- Update trace_affinity_edges unique constraint to include release_id
ALTER TABLE trace_affinity_edges
    DROP CONSTRAINT IF EXISTS trace_affinity_edges_workspace_id_pair_key_key;

ALTER TABLE trace_affinity_edges
    ADD CONSTRAINT trace_affinity_edges_workspace_release_pair
    UNIQUE (workspace_id, release_id, pair_key);

DROP INDEX IF EXISTS trace_affinity_edges_lookup;
CREATE INDEX IF NOT EXISTS trace_affinity_edges_release_lookup
    ON trace_affinity_edges(workspace_id, release_id, left_atom_version_id, right_atom_version_id, status, expires_at);

-- Update trace_activation_priors unique constraint to include release_id
ALTER TABLE trace_activation_priors
    DROP CONSTRAINT IF EXISTS trace_activation_priors_workspace_id_atom_version_id_prior_kind_key;

ALTER TABLE trace_activation_priors
    ADD CONSTRAINT trace_activation_priors_workspace_release_prior
    UNIQUE (workspace_id, release_id, atom_version_id, prior_kind);

DROP INDEX IF EXISTS trace_activation_priors_lookup;
CREATE INDEX IF NOT EXISTS trace_activation_priors_release_lookup
    ON trace_activation_priors(workspace_id, release_id, atom_version_id, expires_at);

-- ============================================================================
-- 6. Row-Level Security (RLS) Policies
-- ============================================================================
ALTER TABLE trace_cortex_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_cortex_releases FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_cortex_releases_tenant ON trace_cortex_releases;
CREATE POLICY trace_cortex_releases_tenant ON trace_cortex_releases
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));

ALTER TABLE trace_cortex_release_components ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_cortex_release_components FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS trace_cortex_release_components_tenant ON trace_cortex_release_components;
CREATE POLICY trace_cortex_release_components_tenant ON trace_cortex_release_components
    USING (workspace_id = current_setting('trace.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));
