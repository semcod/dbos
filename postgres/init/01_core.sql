-- =============================================================================
-- 01_core.sql  —  Extensions, users, ACL, audit log
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- -----------------------------------------------------------------------------
-- USERS + AUTH
-- -----------------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('admin', 'operator', 'viewer', 'service');

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            user_role NOT NULL DEFAULT 'viewer',
    display_name    TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_email ON users(email);

CREATE TABLE user_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- ACL  (resource can be entity_type, content_table name, schema name, or '*')
-- -----------------------------------------------------------------------------
CREATE TYPE acl_action AS ENUM ('read', 'write', 'delete', 'execute', 'render');

CREATE TABLE acl_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    principal_type  TEXT NOT NULL,         -- 'user' | 'role'
    principal_id    TEXT NOT NULL,
    resource_type   TEXT NOT NULL,         -- entity_type, schema name, or '*'
    resource_id     TEXT,                  -- NULL = any
    action          acl_action NOT NULL,
    allow           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_acl_principal ON acl_rules(principal_type, principal_id);
CREATE INDEX idx_acl_resource  ON acl_rules(resource_type, resource_id);

-- -----------------------------------------------------------------------------
-- AUDIT LOG  (single log for every content table via trigger)
-- -----------------------------------------------------------------------------
CREATE TYPE change_source AS ENUM ('filesystem', 'api', 'command', 'generator', 'system');

CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    content_table   TEXT NOT NULL,          -- 'content_json', 'content_html', …
    entity_id       UUID,
    content_id      UUID,
    source          change_source NOT NULL,
    actor_id        UUID REFERENCES users(id),
    action          TEXT NOT NULL,          -- insert | update | delete
    before_state    JSONB,
    after_state     JSONB,
    diff            JSONB,
    version_before  INTEGER,
    version_after   INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity  ON audit_log(entity_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_table   ON audit_log(content_table);
