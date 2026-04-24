-- =============================================================================
-- 06_connectors.sql  —  Uniform registry for protocols, storage backends,
--                       and inbound sources.

-- Extend change_source ENUM so every gateway/connector can label its writes
-- without having to pretend to be 'system'. Each value added individually
-- because IF NOT EXISTS on ADD VALUE is required in older PG (≥ 9.6 has it).
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'gateway';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'ftp';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'imap';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'pop3';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'smtp';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'webdav';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'ftp-pull';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'imap-pull';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'sql-mirror';
ALTER TYPE change_source ADD VALUE IF NOT EXISTS 'mirror';
--
-- Every service that EXPOSES platform data on a protocol (WebDAV, FUSE, FTP,
-- IMAP, POP3, SMTP, HTTP …) declares itself here. Every alternative storage
-- backend (Postgres, SQLite, MySQL, Mongo, Redis, file bucket …) declares
-- itself here. Every inbound puller (filesystem watch, IMAP poll, FTP poll,
-- external SQL mirror …) declares itself here.
--
-- All three categories are treated symmetrically: `kind` + `driver` +
-- `endpoint` + `config`. Services read these tables at boot and configure
-- themselves. Add a row, restart a service — no code change.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- STORAGE_BACKENDS  (where content_* rows live — or get mirrored to)
-- -----------------------------------------------------------------------------
CREATE TABLE storage_backends (
    id               TEXT PRIMARY KEY,          -- 'pg-primary', 'sqlite-mirror', …
    driver           TEXT NOT NULL,             -- 'postgres' | 'sqlite' | 'mysql' | 'mongo' | 'redis' | 's3'
    role             TEXT NOT NULL DEFAULT 'primary', -- 'primary' | 'mirror' | 'cache' | 'archive'
    dsn              TEXT,                      -- connection string (may reference env vars as ${VAR})
    config           JSONB NOT NULL DEFAULT '{}', -- driver-specific options
    mime_filter      TEXT[] NOT NULL DEFAULT '{}', -- empty = all mimes; else only listed mimes mirrored
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_storage_role ON storage_backends(role);

-- -----------------------------------------------------------------------------
-- PROTOCOL_GATEWAYS  (outbound surfaces: how clients read/write platform data)
-- -----------------------------------------------------------------------------
CREATE TABLE protocol_gateways (
    id               TEXT PRIMARY KEY,          -- 'vfs-webdav','vfs-ftp','vfs-imap', …
    protocol         TEXT NOT NULL,             -- 'webdav','fuse','ftp','sftp','imap','pop3','smtp','http'
    service_name     TEXT NOT NULL,             -- docker service / host
    endpoint         TEXT,                      -- e.g. 'tcp://0.0.0.0:2121'
    read_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    write_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    auth_mode        TEXT NOT NULL DEFAULT 'basic',    -- 'basic' | 'anonymous' | 'jwt' | 'none'
    storage_backend  TEXT REFERENCES storage_backends(id) ON DELETE SET NULL,
    layout_strategy  TEXT NOT NULL DEFAULT 'by_schema', -- 'by_schema' | 'by_mime' | 'flat' | 'custom'
    config           JSONB NOT NULL DEFAULT '{}',
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_gateways_proto ON protocol_gateways(protocol);

-- -----------------------------------------------------------------------------
-- INBOUND_SOURCES  (pullers: where new entities come from besides sync-engine)
-- -----------------------------------------------------------------------------
CREATE TABLE inbound_sources (
    id               TEXT PRIMARY KEY,          -- 'imap-support-mailbox', 'ftp-partner-drop', …
    driver           TEXT NOT NULL,             -- 'filesystem' | 'ftp' | 'imap' | 'pop3' | 'sql' | 'webhook'
    endpoint         TEXT,                      -- 'imaps://mail.example.com:993'
    credentials_ref  TEXT,                      -- secret key name in env/secret store
    poll_seconds     INTEGER NOT NULL DEFAULT 60,
    target_schema    TEXT REFERENCES schemas(id),     -- entities synthesised here get this schema
    target_mime      TEXT REFERENCES mime_types(mime),
    id_template      TEXT NOT NULL DEFAULT '{source_id}/{remote_id}', -- external_id pattern
    config           JSONB NOT NULL DEFAULT '{}',
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at      TIMESTAMPTZ,
    last_status      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inbound_driver ON inbound_sources(driver);

-- -----------------------------------------------------------------------------
-- Seed: declare every currently-present service so the registry reflects reality
-- -----------------------------------------------------------------------------
INSERT INTO storage_backends (id, driver, role, dsn, config) VALUES
('pg-primary', 'postgres', 'primary', 'postgres://platform:platform@postgres:5432/platform', '{}');

INSERT INTO protocol_gateways (id, protocol, service_name, endpoint, storage_backend, config) VALUES
('vfs-webdav',    'webdav', 'vfs-webdav',    'tcp://0.0.0.0:8090', 'pg-primary', '{}'),
('vfs-fuse',      'fuse',   'vfs-fuse',      'unix:///mnt/vfs',    'pg-primary', '{}'),
('vfs-ftp',       'ftp',    'vfs-ftp',       'tcp://0.0.0.0:2121', 'pg-primary', '{}'),
('vfs-imap',      'imap',   'vfs-imap',      'tcp://0.0.0.0:1143', 'pg-primary', '{}'),
('vfs-pop3',      'pop3',   'vfs-pop3',      'tcp://0.0.0.0:1110', 'pg-primary', '{}'),
('vfs-smtp',      'smtp',   'vfs-smtp',      'tcp://0.0.0.0:2525', 'pg-primary', '{}'),
('api-gateway',   'http',   'api-gateway',   'tcp://0.0.0.0:3000', 'pg-primary', '{"mode":"rest"}');

-- sync-engine is our first inbound source; others (IMAP/FTP pullers) are added at runtime.
INSERT INTO inbound_sources (id, driver, endpoint, poll_seconds, config) VALUES
('filesystem-data', 'filesystem', 'file:///data', 1, '{"recursive": true}');
