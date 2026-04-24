-- =============================================================================
-- 03_content_tables.sql
--
--   entities        -> abstract logical record (the "meaning")
--   content_json    -> application/json payloads
--   content_yaml    -> application/yaml payloads  (preserves original text)
--   content_xml     -> application/xml payloads   (preserves original text)
--   content_html    -> text/html documents
--   content_markdown-> text/markdown documents with optional front matter
--   content_binary  -> blobs (PNG, PDF, arbitrary)
--
-- One entity can have multiple content rows (e.g. article as markdown source
-- + rendered HTML). This is what the generator services produce.
-- Each content_* table can be exported on its own and imported into another
-- project without dragging the rest of the schema along.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- ENTITIES  (logical layer — no payload, just the handle + pointer to schema)
-- -----------------------------------------------------------------------------
CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id     TEXT UNIQUE,                  -- filesystem key
    entity_type     TEXT NOT NULL,                -- 'device','article','customer',…
    schema_id       TEXT NOT NULL REFERENCES schemas(id),
    primary_mime    TEXT NOT NULL REFERENCES mime_types(mime),
    status          TEXT NOT NULL DEFAULT 'active',
    version         INTEGER NOT NULL DEFAULT 1,
    metadata        JSONB NOT NULL DEFAULT '{}',  -- runtime metadata (tags, etc.)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_entities_type   ON entities(entity_type);
CREATE INDEX idx_entities_schema ON entities(schema_id);
CREATE INDEX idx_entities_meta   ON entities USING GIN (metadata);

-- -----------------------------------------------------------------------------
-- content_json  —  application/json
-- Structured payload; can be queried directly with JSONB operators.
-- -----------------------------------------------------------------------------
CREATE TABLE content_json (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    data            JSONB NOT NULL,
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id)
);
CREATE INDEX idx_cjson_data ON content_json USING GIN (data);

-- -----------------------------------------------------------------------------
-- content_yaml  —  application/yaml
-- Keeps original text so comments/ordering survive round-trips.
-- -----------------------------------------------------------------------------
CREATE TABLE content_yaml (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    raw_text        TEXT NOT NULL,
    parsed          JSONB NOT NULL,               -- parsed view for querying
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id)
);
CREATE INDEX idx_cyaml_parsed ON content_yaml USING GIN (parsed);

-- -----------------------------------------------------------------------------
-- content_xml  —  application/xml
-- -----------------------------------------------------------------------------
CREATE TABLE content_xml (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    raw_text        TEXT NOT NULL,
    parsed          JSONB NOT NULL,               -- fast-xml-parser output
    root_element    TEXT,
    namespaces      JSONB DEFAULT '{}',
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id)
);
CREATE INDEX idx_cxml_root ON content_xml(root_element);

-- -----------------------------------------------------------------------------
-- content_html  —  text/html  (layouts, page fragments, rendered output)
-- -----------------------------------------------------------------------------
CREATE TABLE content_html (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    is_template     BOOLEAN NOT NULL DEFAULT FALSE,  -- true = has {{placeholders}}
    template_engine TEXT,                            -- 'mustache','twig','jinja','handlebars'
    variables       JSONB DEFAULT '[]',              -- declared template variables
    rendered_from   UUID REFERENCES entities(id),    -- if this IS a render output
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chtml_entity   ON content_html(entity_id);
CREATE INDEX idx_chtml_template ON content_html(is_template);

-- -----------------------------------------------------------------------------
-- content_markdown  —  text/markdown  (articles, docs)
-- -----------------------------------------------------------------------------
CREATE TABLE content_markdown (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    front_matter    JSONB DEFAULT '{}',            -- YAML front matter parsed
    toc             JSONB DEFAULT '[]',            -- generated table of contents
    word_count      INTEGER,
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(entity_id)
);
CREATE INDEX idx_cmd_fm   ON content_markdown USING GIN (front_matter);
CREATE INDEX idx_cmd_body ON content_markdown USING GIN (to_tsvector('english', body));

-- -----------------------------------------------------------------------------
-- content_binary  —  image/*, application/pdf, arbitrary blobs
-- -----------------------------------------------------------------------------
CREATE TABLE content_binary (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id       UUID REFERENCES entities(id) ON DELETE CASCADE,
    mime            TEXT NOT NULL REFERENCES mime_types(mime),
    storage_mode    TEXT NOT NULL DEFAULT 'db',    -- db | object_store
    bytes           BYTEA,                         -- when storage_mode='db'
    storage_path    TEXT,                          -- when storage_mode='object_store'
    size_bytes      BIGINT,
    width           INTEGER,
    height          INTEGER,
    checksum        TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source          change_source NOT NULL DEFAULT 'system',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_cbin_entity ON content_binary(entity_id);
CREATE INDEX idx_cbin_mime   ON content_binary(mime);

-- -----------------------------------------------------------------------------
-- COMMAND QUEUE + EVENTS (unchanged — these are orthogonal to content tables)
-- -----------------------------------------------------------------------------
CREATE TYPE command_status AS ENUM ('pending', 'routing', 'running', 'done', 'failed');

CREATE TABLE commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    command_name    TEXT NOT NULL,
    schema_version  INTEGER NOT NULL DEFAULT 1,
    target_runtime  TEXT NOT NULL,
    payload         JSONB NOT NULL,
    status          command_status NOT NULL DEFAULT 'pending',
    result          JSONB,
    error           TEXT,
    actor_id        UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_commands_status ON commands(status);

CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_name      TEXT NOT NULL,
    aggregate_type  TEXT NOT NULL,
    aggregate_id    UUID NOT NULL,
    payload         JSONB NOT NULL,
    version         INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_aggregate ON events(aggregate_type, aggregate_id);

-- -----------------------------------------------------------------------------
-- Generic touch trigger + audit trigger factory
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    NEW.version    = COALESCE(OLD.version, 0) + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entities_touch    BEFORE UPDATE ON entities    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_cjson_touch       BEFORE UPDATE ON content_json       FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_cyaml_touch       BEFORE UPDATE ON content_yaml       FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_cxml_touch        BEFORE UPDATE ON content_xml        FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_chtml_touch       BEFORE UPDATE ON content_html       FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER trg_cmd_touch         BEFORE UPDATE ON content_markdown   FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- -----------------------------------------------------------------------------
-- Unified view: everything as rows of (entity, content_table, payload_ref)
-- Services can query this view when they don't care which MIME the data is in.
-- -----------------------------------------------------------------------------
CREATE VIEW v_entity_contents AS
SELECT e.id AS entity_id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_json'::text AS content_table, cj.id AS content_id, cj.version, cj.updated_at
  FROM entities e JOIN content_json cj ON cj.entity_id = e.id
UNION ALL
SELECT e.id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_yaml', cy.id, cy.version, cy.updated_at
  FROM entities e JOIN content_yaml cy ON cy.entity_id = e.id
UNION ALL
SELECT e.id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_xml', cx.id, cx.version, cx.updated_at
  FROM entities e JOIN content_xml cx ON cx.entity_id = e.id
UNION ALL
SELECT e.id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_html', ch.id, ch.version, ch.updated_at
  FROM entities e JOIN content_html ch ON ch.entity_id = e.id
UNION ALL
SELECT e.id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_markdown', cm.id, cm.version, cm.updated_at
  FROM entities e JOIN content_markdown cm ON cm.entity_id = e.id
UNION ALL
SELECT e.id, e.external_id, e.entity_type, e.schema_id, e.primary_mime,
       'content_binary', cb.id, cb.version, cb.created_at
  FROM entities e JOIN content_binary cb ON cb.entity_id = e.id;

-- -----------------------------------------------------------------------------
-- Thumbnails table for storing 64px preview images
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS thumbnails (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  content_id      UUID,
  size            VARCHAR(16) NOT NULL, -- '64px', '128px', '256px', etc.
  mime_type       VARCHAR(100) NOT NULL,
  data            BYTEA NOT NULL,
  checksum        VARCHAR(64),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_thumbnails_entity_size ON thumbnails(entity_id, size);
CREATE INDEX idx_thumbnails_content ON thumbnails(content_id);
