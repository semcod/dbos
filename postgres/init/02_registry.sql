-- =============================================================================
-- 02_registry.sql  —  Schema registry + MIME registry + FS mapping
--
-- These four tables are the *contract layer*. They are fully self-contained
-- and portable: copy them (plus any needed content_* tables) into another
-- PostgreSQL database and the services work unchanged.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- SCHEMAS  (what a piece of data MEANS — entity schemas, command schemas, etc.)
-- -----------------------------------------------------------------------------
CREATE TABLE schemas (
    id              TEXT PRIMARY KEY,           -- e.g. 'device_v3', 'article_v1'
    name            TEXT NOT NULL,
    version         INTEGER NOT NULL,
    kind            TEXT NOT NULL,              -- entity | command | ui | event | template
    mime_type       TEXT NOT NULL,              -- primary MIME of the content
    definition      JSONB NOT NULL,             -- JSON Schema draft-07
    renderers       TEXT[] NOT NULL DEFAULT '{}', -- which generator services can render this
    fs_path_template TEXT,                      -- e.g. 'articles/{slug}.md'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, version)
);
CREATE INDEX idx_schemas_kind     ON schemas(kind);
CREATE INDEX idx_schemas_mime     ON schemas(mime_type);
CREATE INDEX idx_schemas_renderers ON schemas USING GIN (renderers);

-- -----------------------------------------------------------------------------
-- MIME_TYPES  (how a MIME is handled: which table, which service, storage mode)
-- This is the table each service inspects to find out where its data lives.
-- -----------------------------------------------------------------------------
CREATE TABLE mime_types (
    mime             TEXT PRIMARY KEY,          -- 'application/json', 'text/html', …
    category         TEXT NOT NULL,             -- structured | document | binary
    content_table    TEXT NOT NULL,             -- which content_* table holds payloads
    default_handler  TEXT,                      -- preferred service name
    storage_mode     TEXT NOT NULL DEFAULT 'db', -- db | object_store | hybrid
    indexing_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_schema  TEXT REFERENCES schemas(id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- SCHEMA_PATHS  (filesystem projection template per schema)
-- -----------------------------------------------------------------------------
CREATE TABLE schema_paths (
    schema_id        TEXT NOT NULL REFERENCES schemas(id) ON DELETE CASCADE,
    path_template    TEXT NOT NULL,             -- 'customers/{customer_id}/devices/{id}'
    fs_strategy      TEXT NOT NULL DEFAULT 'flat',  -- flat | nested | hybrid
    PRIMARY KEY (schema_id)
);

-- -----------------------------------------------------------------------------
-- FILESYSTEM_MAP  (resolved paths per entity — what sync-engine actually sees)
-- -----------------------------------------------------------------------------
CREATE TABLE filesystem_map (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id        UUID NOT NULL,
    content_table    TEXT NOT NULL,
    resolved_path    TEXT NOT NULL UNIQUE,
    is_virtual       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_fsmap_entity ON filesystem_map(entity_id);
CREATE INDEX idx_fsmap_path   ON filesystem_map(resolved_path);

-- -----------------------------------------------------------------------------
-- Seed the MIME registry. This is what tells every service where its data is.
-- -----------------------------------------------------------------------------
INSERT INTO mime_types (mime, category, content_table, default_handler, storage_mode) VALUES
('application/json',     'structured', 'content_json',     'api-gateway',    'db'),
('application/yaml',     'structured', 'content_yaml',     'sync-engine',    'db'),
('application/xml',      'structured', 'content_xml',      'worker-python',  'db'),
('text/html',            'document',   'content_html',     'gen-twig',       'db'),
('text/markdown',        'document',   'content_markdown', 'gen-jinja',      'db'),
('text/plain',           'document',   'content_markdown', 'gen-jinja',      'db'),
('image/png',            'binary',     'content_binary',   'nginx-cdn',      'object_store'),
('image/jpeg',           'binary',     'content_binary',   'nginx-cdn',      'object_store'),
('image/svg+xml',        'document',   'content_html',     'gen-twig',       'db'),
('application/pdf',      'binary',     'content_binary',   'worker-php',     'object_store'),
('application/octet-stream','binary',  'content_binary',   'sync-engine',    'object_store');
