-- Forward-only runtime authentication and worker scope hardening.
--
-- API-key authentication precedes a known workspace.  It is the single
-- legitimate exception to normal tenant lookup, and is restricted to an
-- equality lookup of a SHA-256 key hash supplied by trusted application code.
-- It neither grants a wildcard workspace nor exposes rows without knowing a
-- valid opaque credential hash.

DROP POLICY IF EXISTS trace_api_keys_tenant ON trace_api_keys;
CREATE POLICY trace_api_keys_tenant ON trace_api_keys
    USING (
        workspace_id = current_setting('trace.workspace_id', true)
        OR (
            current_setting('trace.auth_lookup', true) = 'api_key'
            AND key_hash = current_setting('trace.api_key_hash', true)
        )
    )
    WITH CHECK (workspace_id = current_setting('trace.workspace_id', true));

-- Every outbox record is workspace keyed after 002.  Keeping this index makes
-- per-workspace publisher workers bounded and avoids a privileged global
-- queue scan under forced RLS.
CREATE INDEX IF NOT EXISTS trace_outbox_workspace_lease
    ON trace_outbox(workspace_id, status, available_at, event_offset);
