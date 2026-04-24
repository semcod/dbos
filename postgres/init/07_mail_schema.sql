-- =============================================================================
-- 07_mail_schema.sql  —  Schema seed for inbound/outbound mail entities
-- =============================================================================

INSERT INTO schemas (id, name, version, kind, mime_type, renderers, fs_path_template, definition)
VALUES (
  'mail_v1', 'mail', 1, 'entity', 'text/markdown',
  ARRAY['vfs-smtp','vfs-imap','vfs-pop3','api-gateway'],
  'mail/{external_id}.md',
  '{
    "type":"object",
    "required":["title","body"],
    "properties":{
      "title":{"type":"string"},
      "body":{"type":"string"},
      "from":{"type":"string"},
      "subject":{"type":"string"},
      "message_id":{"type":"string"},
      "date":{"type":"string"}
    }
  }'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_paths (schema_id, path_template, fs_strategy)
VALUES ('mail_v1', 'mail/{external_id}.md', 'flat')
ON CONFLICT (schema_id) DO NOTHING;
