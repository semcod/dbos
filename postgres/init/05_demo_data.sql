-- =============================================================================
-- 05_demo_data.sql  —  First demo rows across every content table.
-- Password for every demo user: demo1234
-- =============================================================================

-- USERS ----------------------------------------------------------------------
INSERT INTO users (id, email, password_hash, role, display_name) VALUES
('11111111-1111-1111-1111-111111111111', 'admin@platform.local',    crypt('demo1234', gen_salt('bf')), 'admin',    'Admin'),
('22222222-2222-2222-2222-222222222222', 'operator@platform.local', crypt('demo1234', gen_salt('bf')), 'operator', 'Operator'),
('33333333-3333-3333-3333-333333333333', 'viewer@platform.local',   crypt('demo1234', gen_salt('bf')), 'viewer',   'Viewer'),
('44444444-4444-4444-4444-444444444444', 'service@platform.local',  crypt('demo1234', gen_salt('bf')), 'service',  'System Service');

-- ACL ------------------------------------------------------------------------
INSERT INTO acl_rules (principal_type, principal_id, resource_type, action, allow) VALUES
('role','admin',    '*',        'read',    TRUE),
('role','admin',    '*',        'write',   TRUE),
('role','admin',    '*',        'delete',  TRUE),
('role','admin',    '*',        'execute', TRUE),
('role','admin',    '*',        'render',  TRUE),
('role','operator', 'device',   'read',    TRUE),
('role','operator', 'device',   'write',   TRUE),
('role','operator', 'article',  'read',    TRUE),
('role','operator', 'article',  'write',   TRUE),
('role','operator', 'page',     'render',  TRUE),
('role','operator', 'command',  'execute', TRUE),
('role','viewer',   '*',        'read',    TRUE);

-- =============================================================================
-- ENTITIES + CONTENT  (one of each MIME type, showing the pattern)
-- =============================================================================

-- ---------- 1) JSON: device ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e1111111-0000-0000-0000-000000000001', 'device_001', 'device', 'device_v1', 'application/json',
 '{"tags":["temperature","warsaw","iot"]}');

INSERT INTO content_json (entity_id, data, checksum) VALUES
('e1111111-0000-0000-0000-000000000001',
 '{"name":"TempSensor-A1","device_type":"sensor","status":"active","serial_number":"SN-A1-0001","firmware":"2.4.1","location":{"site":"Warsaw-Lab","rack":"R-03","lat":52.2297,"lng":21.0122},"tags":["temperature","indoor","iot"]}'::jsonb,
 encode(digest('device_001','sha256'),'hex'));

INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e1111111-0000-0000-0000-000000000002', 'device_002', 'device', 'device_v1', 'application/json', '{}');

INSERT INTO content_json (entity_id, data, checksum) VALUES
('e1111111-0000-0000-0000-000000000002',
 '{"name":"Gateway-GW-07","device_type":"gateway","status":"active","serial_number":"GW-07-2024","firmware":"1.8.0"}'::jsonb,
 encode(digest('device_002','sha256'),'hex'));

-- ---------- 2) JSON: customer ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e2222222-0000-0000-0000-000000000001', 'customer_001', 'customer', 'customer_v1', 'application/json', '{}');

INSERT INTO content_json (entity_id, data, checksum) VALUES
('e2222222-0000-0000-0000-000000000001',
 '{"name":"Acme Labs","email":"contact@acme-labs.example","customer_type":"business","status":"active","contact":{"phone":"+48 22 000 0001","address":"Warszawa, PL"}}'::jsonb,
 encode(digest('customer_001','sha256'),'hex'));

-- ---------- 3) MARKDOWN: article ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e3333333-0000-0000-0000-000000000001', 'hello-platform', 'article', 'article_v1', 'text/markdown',
 '{"published":true}');

INSERT INTO content_markdown (entity_id, body, front_matter, word_count, checksum) VALUES
('e3333333-0000-0000-0000-000000000001',
E'# Hello, Platform\n\nThis article lives in the **content_markdown** table.\n\n## How it got here\n\nEither it was dropped into `data/articles/hello-platform.md` and picked up by the sync-engine, or it was POSTed to the API gateway.\n\n## Who can render it\n\nAny service that declares `gen-jinja` or `gen-handlebars` in its `renderers` array for the `article_v1` schema.\n\n```python\n# Example: render via Jinja2\ncurl -X POST http://localhost:8080/render/gen-jinja/hello-platform\n```\n',
 '{"title":"Hello, Platform","author":"Admin","tags":["intro","docs"],"slug":"hello-platform"}'::jsonb,
 42,
 encode(digest('hello-platform','sha256'),'hex'));

INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e3333333-0000-0000-0000-000000000002', 'mime-typed-storage', 'article', 'article_v1', 'text/markdown',
 '{"published":true}');

INSERT INTO content_markdown (entity_id, body, front_matter, word_count, checksum) VALUES
('e3333333-0000-0000-0000-000000000002',
E'# Why MIME-typed tables?\n\nStoring every content type in its own table means:\n\n- You can **export one table** and take it to a different project\n- Services read from **one place** and never care about other content kinds\n- Migration is a `pg_dump -t content_markdown` away\n- New MIME types arrive as **new tables**, not migrations of existing ones\n',
 '{"title":"Why MIME-typed tables?","author":"Admin","tags":["architecture"],"slug":"mime-typed-storage"}'::jsonb,
 58,
 encode(digest('mime-typed-storage','sha256'),'hex'));

-- ---------- 4) HTML: page (with Twig-style placeholders) ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e4444444-0000-0000-0000-000000000001', 'landing', 'page', 'page_v1', 'text/html', '{}');

INSERT INTO content_html (entity_id, body, is_template, template_engine, variables, checksum) VALUES
('e4444444-0000-0000-0000-000000000001',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{{ title }}</title></head>
<body>
  <header><h1>{{ title }}</h1></header>
  <main>{{ body|raw }}</main>
  <footer>Rendered by {{ renderer }} at {{ rendered_at }}</footer>
</body>
</html>',
 TRUE, 'twig',
 '["title","body","renderer","rendered_at"]'::jsonb,
 encode(digest('landing','sha256'),'hex'));

-- ---------- 5) YAML: scenario ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e5555555-0000-0000-0000-000000000001', 'nightly-calibration', 'scenario', 'scenario_v1', 'application/yaml', '{}');

INSERT INTO content_yaml (entity_id, raw_text, parsed, checksum) VALUES
('e5555555-0000-0000-0000-000000000001',
E'name: Nightly calibration sweep\nstatus: active\n# This runs at 02:00 UTC every day\nsteps:\n  - id: S1\n    type: setup\n    params:\n      filter:\n        status: active\n        device_type: sensor\n  - id: S2\n    type: action\n    params:\n      command: run_calibration\n  - id: S3\n    type: assert\n    params:\n      expect: completed\n',
 '{"name":"Nightly calibration sweep","status":"active","steps":[{"id":"S1","type":"setup","params":{"filter":{"status":"active","device_type":"sensor"}}},{"id":"S2","type":"action","params":{"command":"run_calibration"}},{"id":"S3","type":"assert","params":{"expect":"completed"}}]}'::jsonb,
 encode(digest('nightly-calibration','sha256'),'hex'));

-- ---------- 6) XML: protocol ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e6666666-0000-0000-0000-000000000001', 'cal-report-2026-q2', 'protocol', 'protocol_v1', 'application/xml', '{}');

INSERT INTO content_xml (entity_id, raw_text, parsed, root_element, checksum) VALUES
('e6666666-0000-0000-0000-000000000001',
'<?xml version="1.0" encoding="UTF-8"?>
<protocol xmlns="https://platform.local/schemas/protocol/v1">
  <meta><device ref="device_001"/><operator ref="operator@platform.local"/></meta>
  <measurements>
    <m parameter="temperature" value="20.01" unit="C" ts="2026-03-15T10:05:00Z"/>
    <m parameter="temperature" value="25.03" unit="C" ts="2026-03-15T10:10:00Z"/>
    <m parameter="temperature" value="37.52" unit="C" ts="2026-03-15T10:15:00Z"/>
  </measurements>
</protocol>',
 '{"protocol":{"meta":{"device":{"@_ref":"device_001"},"operator":{"@_ref":"operator@platform.local"}},"measurements":{"m":[{"@_parameter":"temperature","@_value":"20.01","@_unit":"C","@_ts":"2026-03-15T10:05:00Z"},{"@_parameter":"temperature","@_value":"25.03","@_unit":"C","@_ts":"2026-03-15T10:10:00Z"},{"@_parameter":"temperature","@_value":"37.52","@_unit":"C","@_ts":"2026-03-15T10:15:00Z"}]}}}'::jsonb,
 'protocol',
 encode(digest('cal-report','sha256'),'hex'));

-- ---------- 7) BINARY: a tiny PNG (1x1 transparent pixel) ----------
INSERT INTO entities (id, external_id, entity_type, schema_id, primary_mime, metadata) VALUES
('e7777777-0000-0000-0000-000000000001', 'pixel', 'image', 'image_v1', 'image/png',
 '{"alt":"transparent pixel","caption":"demo blob"}');

INSERT INTO content_binary (entity_id, mime, storage_mode, bytes, size_bytes, width, height, checksum) VALUES
('e7777777-0000-0000-0000-000000000001', 'image/png', 'db',
 decode('89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C626001000000050001AA36A44500000000049454E44AE426082','hex'),
 70, 1, 1,
 encode(digest('pixel-demo','sha256'),'hex'));

-- ---------- filesystem_map: precompute resolved paths ----------
INSERT INTO filesystem_map (entity_id, content_table, resolved_path)
SELECT e.id, mt.content_table,
       replace(sp.path_template, '{external_id}', e.external_id)
  FROM entities e
  JOIN schemas s        ON s.id = e.schema_id
  JOIN mime_types mt    ON mt.mime = e.primary_mime
  JOIN schema_paths sp  ON sp.schema_id = s.id;

-- ---------- events (so UI has something to display immediately) ----------
INSERT INTO events (event_name, aggregate_type, aggregate_id, payload, version) VALUES
('EntityCreated', 'article', 'e3333333-0000-0000-0000-000000000001',
 '{"entity_id":"e3333333-0000-0000-0000-000000000001","title":"Hello, Platform"}'::jsonb, 1),
('DeviceCreated', 'device',  'e1111111-0000-0000-0000-000000000001',
 '{"entity_id":"e1111111-0000-0000-0000-000000000001","name":"TempSensor-A1"}'::jsonb, 1);
