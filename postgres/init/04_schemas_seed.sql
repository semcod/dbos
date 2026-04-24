-- =============================================================================
-- 04_schemas_seed.sql  —  Seed schema registry
--
-- `renderers` on each schema says which generator services can consume it.
-- This is what lets services advertise compatibility without coupling.
-- =============================================================================

INSERT INTO schemas (id, name, version, kind, mime_type, renderers, fs_path_template, definition) VALUES

-- ========== ENTITY SCHEMAS ==========

('device_v1', 'device', 1, 'entity', 'application/json',
 ARRAY['api-gateway','gen-handlebars'],
 'devices/{external_id}.json',
'{
  "type":"object",
  "required":["name","device_type"],
  "properties":{
    "name":         {"type":"string","minLength":1},
    "device_type":  {"type":"string","enum":["sensor","actuator","gateway","controller","analyzer"]},
    "status":       {"type":"string","enum":["active","inactive","maintenance","retired","error"]},
    "serial_number":{"type":"string"},
    "firmware":     {"type":"string"},
    "customer_id":  {"type":"string","format":"uuid"},
    "location":     {"type":"object"},
    "tags":         {"type":"array","items":{"type":"string"}}
  }
}'::jsonb),

('customer_v1', 'customer', 1, 'entity', 'application/json',
 ARRAY['api-gateway','gen-handlebars'],
 'customers/{external_id}.json',
'{
  "type":"object",
  "required":["name"],
  "properties":{
    "name":          {"type":"string"},
    "email":         {"type":"string","format":"email"},
    "customer_type": {"type":"string","enum":["individual","business","government","partner"]},
    "status":        {"type":"string","enum":["active","inactive","suspended","pending"]}
  }
}'::jsonb),

('article_v1', 'article', 1, 'entity', 'text/markdown',
 ARRAY['gen-jinja','gen-handlebars'],
 'articles/{external_id}.md',
'{
  "type":"object",
  "required":["title","body"],
  "properties":{
    "title":   {"type":"string"},
    "slug":    {"type":"string","pattern":"^[a-z0-9-]+$"},
    "author":  {"type":"string"},
    "tags":    {"type":"array","items":{"type":"string"}},
    "body":    {"type":"string"}
  }
}'::jsonb),

('page_v1', 'page', 1, 'entity', 'text/html',
 ARRAY['gen-twig','nginx-cdn'],
 'pages/{external_id}.html',
'{
  "type":"object",
  "required":["title","body"],
  "properties":{
    "title":    {"type":"string"},
    "layout":   {"type":"string"},
    "body":     {"type":"string"},
    "css":      {"type":"string"}
  }
}'::jsonb),

('scenario_v1', 'scenario', 1, 'entity', 'application/yaml',
 ARRAY['worker-python','api-gateway'],
 'scenarios/{external_id}.yaml',
'{
  "type":"object",
  "required":["name","steps"],
  "properties":{
    "name":   {"type":"string"},
    "status": {"type":"string","enum":["draft","active","completed","archived"]},
    "steps":  {"type":"array"}
  }
}'::jsonb),

('protocol_v1', 'protocol', 1, 'entity', 'application/xml',
 ARRAY['worker-python'],
 'protocols/{external_id}.xml',
'{
  "type":"object",
  "required":["name"],
  "properties":{
    "name":          {"type":"string"},
    "protocol_type": {"type":"string","enum":["calibration","measurement","validation","diagnostic"]},
    "status":        {"type":"string"}
  }
}'::jsonb),

('image_v1', 'image', 1, 'entity', 'image/png',
 ARRAY['nginx-cdn'],
 'images/{external_id}.png',
'{
  "type":"object",
  "properties":{
    "alt":     {"type":"string"},
    "caption": {"type":"string"}
  }
}'::jsonb),

-- ========== TEMPLATE SCHEMAS ==========

('template_twig_v1', 'template_twig', 1, 'template', 'text/html',
 ARRAY['gen-twig'],
 'templates/twig/{external_id}.html.twig',
'{
  "type":"object",
  "properties":{
    "engine":    {"const":"twig"},
    "layout":    {"type":"string"},
    "variables": {"type":"array","items":{"type":"string"}}
  }
}'::jsonb),

('template_jinja_v1', 'template_jinja', 1, 'template', 'text/html',
 ARRAY['gen-jinja'],
 'templates/jinja/{external_id}.html.j2',
'{
  "type":"object",
  "properties":{
    "engine":    {"const":"jinja2"},
    "variables": {"type":"array","items":{"type":"string"}}
  }
}'::jsonb),

('template_handlebars_v1', 'template_handlebars', 1, 'template', 'text/html',
 ARRAY['gen-handlebars'],
 'templates/handlebars/{external_id}.hbs',
'{
  "type":"object",
  "properties":{
    "engine":    {"const":"handlebars"},
    "variables": {"type":"array","items":{"type":"string"}}
  }
}'::jsonb),

-- ========== COMMAND SCHEMAS ==========

('cmd_create_device_v1', 'create_device', 1, 'command', 'application/json',
 ARRAY['worker-python'],
 NULL,
'{
  "type":"object",
  "required":["name","device_type"],
  "properties":{
    "name":{"type":"string"},"device_type":{"type":"string"},
    "customer_id":{"type":"string","format":"uuid"}
  },
  "target_runtime":"python"
}'::jsonb),

('cmd_render_article_v1', 'render_article', 1, 'command', 'application/json',
 ARRAY['gen-jinja','gen-handlebars'],
 NULL,
'{
  "type":"object",
  "required":["article_id"],
  "properties":{
    "article_id": {"type":"string","format":"uuid"},
    "template_id":{"type":"string"},
    "engine":     {"type":"string","enum":["jinja2","handlebars","twig"]}
  },
  "target_runtime":"python"
}'::jsonb),

('cmd_render_page_v1', 'render_page', 1, 'command', 'application/json',
 ARRAY['gen-twig'],
 NULL,
'{
  "type":"object",
  "required":["page_id"],
  "properties":{
    "page_id":    {"type":"string","format":"uuid"},
    "template_id":{"type":"string"}
  },
  "target_runtime":"php"
}'::jsonb);

-- FS path mapping -----------------------------------------------------------
INSERT INTO schema_paths (schema_id, path_template, fs_strategy)
SELECT id, fs_path_template, 'flat' FROM schemas WHERE fs_path_template IS NOT NULL;

-- Associate MIME metadata schemas ------------------------------------------
UPDATE mime_types SET metadata_schema = 'image_v1' WHERE mime IN ('image/png','image/jpeg');
