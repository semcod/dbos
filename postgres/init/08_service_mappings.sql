-- =============================================================================
-- 08_service_mappings.sql  —  Dynamic data-flow routing between services.
--
-- A mapping declares: "whenever an entity matching FILTER is written to
-- SOURCE, replicate it to TARGET".  Both source and target are service IDs
-- from protocol_gateways, storage_backends, or inbound_sources.
--
-- Example: remote IMAP mailbox -> local ./email/ folder
--   source_service = 'vfs-imap'
--   target_service = 'filesystem-email'
--   filter         = '{"entity_type":"mail"}'
--
-- The outbound-sync daemon consumes audit_log and pushes matching entities
-- to the declared targets.  Adding a row creates a new pipeline without code.
-- =============================================================================

CREATE TABLE IF NOT EXISTS service_mappings (
    id              TEXT PRIMARY KEY,
    source_service  TEXT NOT NULL,             -- 'vfs-imap', 'pg-primary', 'filesystem-data', ...
    target_service  TEXT NOT NULL,             -- 'filesystem-email', 'vfs-smtp', 'sqlite-mirror', ...
    filter          JSONB NOT NULL DEFAULT '{}',  -- {"entity_type":"mail"} or {"schema_id":"mail_v1"}
    transform       JSONB NOT NULL DEFAULT '{}',  -- {"strip_front_matter":true, "wrap_rfc5322":false}
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at     TIMESTAMPTZ,
    last_status     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_service_mappings_src ON service_mappings(source_service);
CREATE INDEX idx_service_mappings_tgt ON service_mappings(target_service);

-- Seed: expose mail entities as files in ./email/ (readable via IMAP, writable via sync)
INSERT INTO service_mappings (id, source_service, target_service, filter, transform) VALUES
('imap-to-email-folder', 'pg-primary', 'filesystem-email', '{"entity_type":"mail"}', '{"format":"rfc5322","extension":".eml"}')
ON CONFLICT (id) DO NOTHING;
