// api-gateway/src/index.js
//
// Generic entity API built on top of the MIME-typed tables.
//
//   GET  /api/entities                    list
//   GET  /api/entities/:external_id       fetch entity + its primary content
//   POST /api/entities                    create entity + content row
//   GET  /api/entities/:external_id/html  fetch rendered HTML (if any)
//
// Plus:
//   POST /auth/login
//   GET  /schemas, /schemas/:id
//   GET  /mime-types
//   POST /commands/:name
//   GET  /audit
//
// One generic handler covers every entity_type because routing is driven
// by `entities.primary_mime` -> `mime_types.content_table`.

import express from 'express';
import cors from 'cors';
import pg from 'pg';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import jwt from 'jsonwebtoken';
import crypto from 'node:crypto';

const { DATABASE_URL, JWT_SECRET, COMMAND_BUS_URL } = process.env;
const pool = new pg.Pool({ connectionString: DATABASE_URL });

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

// ----------------------------------------------------------------------------
// Caches refreshed at startup (small datasets — reload on demand in production)
// ----------------------------------------------------------------------------
const schemaCache = new Map();    // schema_id -> definition
const mimeCache   = new Map();    // mime -> { content_table, ... }

async function loadCaches() {
  const s = await pool.query(`SELECT id, definition FROM schemas`);
  for (const r of s.rows) schemaCache.set(r.id, r.definition);

  const m = await pool.query(`SELECT * FROM mime_types`);
  for (const r of m.rows) mimeCache.set(r.mime, r);

  console.log(`[api] loaded ${s.rows.length} schemas, ${m.rows.length} MIME routings`);
}

function validate(schemaId, payload) {
  const def = schemaCache.get(schemaId);
  if (!def) return { ok: false, errors: [`no schema ${schemaId}`] };
  const check = ajv.compile(def);
  return { ok: check(payload), errors: check.errors };
}

// ----------------------------------------------------------------------------
// ACL
// ----------------------------------------------------------------------------
async function canAccess(user, resourceType, action, resourceId = null) {
  if (!user) return false;
  const { rows } = await pool.query(
    `SELECT allow FROM acl_rules
      WHERE action = $1
        AND (resource_type = $2 OR resource_type = '*')
        AND (resource_id IS NULL OR resource_id = $3)
        AND (
          (principal_type = 'user' AND principal_id = $4) OR
          (principal_type = 'role' AND principal_id = $5)
        )
      ORDER BY
        CASE WHEN resource_type = '*' THEN 1 ELSE 0 END,
        CASE WHEN resource_id IS NULL THEN 1 ELSE 0 END
      LIMIT 1`,
    [action, resourceType, resourceId, user.id, user.role]);
  return rows.length > 0 && rows[0].allow;
}

function auth(req, res, next) {
  const h = req.headers.authorization;
  if (!h?.startsWith('Bearer ')) return res.status(401).json({ error: 'unauthorized' });
  try { req.user = jwt.verify(h.slice(7), JWT_SECRET); next(); }
  catch { res.status(401).json({ error: 'invalid token' }); }
}

// ----------------------------------------------------------------------------
// Entity loader — reads entity row + joins the right content_* table
// based on primary_mime.
// ----------------------------------------------------------------------------
async function loadEntity(externalId) {
  const { rows } = await pool.query(
    `SELECT e.*, s.name AS schema_name, s.kind AS schema_kind
       FROM entities e
       JOIN schemas s ON s.id = e.schema_id
      WHERE e.external_id = $1 OR e.id::text = $1`,
    [externalId]);
  if (rows.length === 0) return null;

  const e    = rows[0];
  const mime = mimeCache.get(e.primary_mime);
  if (!mime) return { entity: e, content: null };

  const contentTable = mime.content_table;
  const { rows: cRows } = await pool.query(
    `SELECT * FROM ${contentTable}
      WHERE entity_id = $1
      ORDER BY updated_at DESC LIMIT 1`, [e.id]);
  const content = cRows[0] ?? null;

  // Binary: base64-encode the bytes so JSON response is safe
  if (content?.bytes) content.bytes = Buffer.from(content.bytes).toString('base64');

  return { entity: e, content, content_table: contentTable };
}

// ----------------------------------------------------------------------------
// App
// ----------------------------------------------------------------------------
const app = express();
app.use(express.json({ limit: '10mb' }));
app.use(cors());

app.get('/health', (_req, res) => res.json({ ok: true, service: 'api-gateway' }));

// ---------- AUTH ----------
app.post('/auth/login', async (req, res) => {
  const { email, password } = req.body ?? {};
  const { rows } = await pool.query(
    `SELECT id, email, password_hash, role, display_name FROM users WHERE email=$1`, [email]);
  if (rows.length === 0) return res.status(401).json({ error: 'invalid credentials' });
  const u = rows[0];

  // demo passwords are bcrypt via pgcrypto's crypt()
  const { rows: chk } = await pool.query(
    `SELECT ($1 = crypt($2, $1)) AS ok`, [u.password_hash, password]);
  if (!chk[0].ok) return res.status(401).json({ error: 'invalid credentials' });

  const token = jwt.sign({ id: u.id, email: u.email, role: u.role }, JWT_SECRET, { expiresIn: '8h' });
  res.json({ token, user: { id: u.id, email: u.email, role: u.role, display_name: u.display_name } });
});

// ---------- SCHEMA / MIME INTROSPECTION (public) ----------
app.get('/schemas', async (_req, res) => {
  const { rows } = await pool.query(
    `SELECT id, name, version, kind, mime_type, renderers FROM schemas ORDER BY kind, id`);
  res.json(rows);
});
app.get('/schemas/:id', async (req, res) => {
  const { rows } = await pool.query(
    `SELECT * FROM schemas WHERE id = $1`, [req.params.id]);
  if (rows.length === 0) return res.status(404).json({ error: 'not found' });
  res.json(rows[0]);
});
app.get('/mime-types', async (_req, res) => {
  const { rows } = await pool.query(`SELECT * FROM mime_types ORDER BY mime`);
  res.json(rows);
});

// ---------- ENTITIES (generic) ----------
app.get('/api/entities', auth, async (req, res) => {
  if (!(await canAccess(req.user, '*', 'read')))
    return res.status(403).json({ error: 'forbidden' });

  const where  = [];
  const params = [];
  if (req.query.entity_type) { params.push(req.query.entity_type); where.push(`entity_type = $${params.length}`); }
  if (req.query.schema_id)   { params.push(req.query.schema_id);   where.push(`schema_id   = $${params.length}`); }

  const limit  = Math.min(parseInt(req.query.limit)  || 50, 200);
  const offset = parseInt(req.query.offset) || 0;
  params.push(limit, offset);
  const sql = `
    SELECT id, external_id, entity_type, schema_id, primary_mime, status, version, updated_at
      FROM entities
      ${where.length ? 'WHERE ' + where.join(' AND ') : ''}
      ORDER BY updated_at DESC
      LIMIT $${params.length - 1} OFFSET $${params.length}`;
  const { rows } = await pool.query(sql, params);
  res.json({ data: rows, limit, offset });
});

app.get('/api/entities/:externalId', auth, async (req, res) => {
  const loaded = await loadEntity(req.params.externalId);
  if (!loaded) return res.status(404).json({ error: 'not found' });
  if (!(await canAccess(req.user, loaded.entity.entity_type, 'read', loaded.entity.id)))
    return res.status(403).json({ error: 'forbidden' });
  res.json(loaded);
});

// Fetch the latest rendered HTML for an entity (from any generator).
app.get('/api/entities/:externalId/html', auth, async (req, res) => {
  const { rows } = await pool.query(
    `SELECT ch.body, ch.source, ch.updated_at
       FROM entities e
       JOIN content_html ch ON ch.entity_id = e.id
      WHERE (e.external_id = $1 OR e.id::text = $1)
        AND ch.is_template = FALSE
      ORDER BY ch.updated_at DESC LIMIT 1`, [req.params.externalId]);
  if (rows.length === 0) return res.status(404).json({ error: 'no rendered html' });
  res.type('html').send(rows[0].body);
});

// Create an entity + its content row. The client supplies entity_type,
// external_id, schema_id, and a `content` object matching the primary_mime.
app.post('/api/entities', auth, async (req, res) => {
  const { external_id, entity_type, schema_id, content, metadata } = req.body ?? {};
  if (!external_id || !entity_type || !schema_id || !content)
    return res.status(400).json({ error: 'external_id, entity_type, schema_id, content required' });

  if (!(await canAccess(req.user, entity_type, 'write')))
    return res.status(403).json({ error: 'forbidden' });

  // Find the MIME + content table from the schema's primary MIME
  const { rows: sRows } = await pool.query(
    `SELECT mime_type FROM schemas WHERE id = $1`, [schema_id]);
  if (sRows.length === 0) return res.status(400).json({ error: `unknown schema ${schema_id}` });
  const mime  = sRows[0].mime_type;
  const table = mimeCache.get(mime)?.content_table;
  if (!table) return res.status(500).json({ error: `no routing for mime ${mime}` });

  // Validate `content.data` (or whatever the schema expects) against schema
  const v = validate(schema_id, content.data ?? content.parsed ?? content);
  if (!v.ok) return res.status(400).json({ error: 'validation failed', details: v.errors });

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const { rows: eRows } = await client.query(
      `INSERT INTO entities (external_id, entity_type, schema_id, primary_mime, metadata)
       VALUES ($1, $2, $3, $4, $5) RETURNING id`,
      [external_id, entity_type, schema_id, mime, metadata ?? {}]);
    const entityId = eRows[0].id;

    const checksum = crypto
      .createHash('sha256').update(JSON.stringify(content)).digest('hex');

    // Insert into the right content_* table by MIME
    const insertByTable = {
      content_json:
        [`INSERT INTO content_json (entity_id, data, checksum, source) VALUES ($1,$2,$3,'api')`,
         [entityId, content.data ?? content, checksum]],
      content_yaml:
        [`INSERT INTO content_yaml (entity_id, raw_text, parsed, checksum, source)
          VALUES ($1,$2,$3,$4,'api')`,
         [entityId, content.raw_text ?? '', content.parsed ?? {}, checksum]],
      content_xml:
        [`INSERT INTO content_xml (entity_id, raw_text, parsed, checksum, source)
          VALUES ($1,$2,$3,$4,'api')`,
         [entityId, content.raw_text ?? '', content.parsed ?? {}, checksum]],
      content_html:
        [`INSERT INTO content_html (entity_id, body, is_template, checksum, source)
          VALUES ($1,$2,$3,$4,'api')`,
         [entityId, content.body ?? '', !!content.is_template, checksum]],
      content_markdown:
        [`INSERT INTO content_markdown (entity_id, body, front_matter, checksum, source)
          VALUES ($1,$2,$3,$4,'api')`,
         [entityId, content.body ?? '', content.front_matter ?? {}, checksum]],
      content_binary:
        [`INSERT INTO content_binary (entity_id, mime, storage_mode, bytes, size_bytes, checksum, source)
          VALUES ($1,$2,'db',$3,$4,$5,'api')`,
         [entityId, mime, Buffer.from(content.bytes_base64 ?? '', 'base64'),
          (content.bytes_base64 ?? '').length * 3 / 4, checksum]],
    };
    const spec = insertByTable[table];
    if (!spec) throw new Error(`no insert handler for ${table}`);
    await client.query(spec[0], spec[1]);

    await client.query('COMMIT');
    res.status(201).json({ id: entityId, external_id, entity_type, schema_id, primary_mime: mime });
  } catch (err) {
    await client.query('ROLLBACK');
    res.status(500).json({ error: err.message });
  } finally {
    client.release();
  }
});

// ---------- COMMANDS (forward to bus) ----------
app.post('/commands/:name', auth, async (req, res) => {
  if (!(await canAccess(req.user, 'command', 'execute')))
    return res.status(403).json({ error: 'forbidden' });
  const r = await fetch(`${COMMAND_BUS_URL}/execute`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ command_name: req.params.name, payload: req.body, actor_id: req.user.id }),
  });
  const body = await r.json();
  res.status(r.status).json(body);
});

// ---------- AUDIT ----------
app.get('/audit', auth, async (req, res) => {
  if (req.user.role !== 'admin') return res.status(403).json({ error: 'admin only' });
  const { rows } = await pool.query(
    `SELECT id, content_table, entity_id, source, action, created_at
       FROM audit_log ORDER BY created_at DESC LIMIT 100`);
  res.json(rows);
});

// ---------- START ----------
await loadCaches();
app.listen(3000, () => console.log('api-gateway listening on :3000'));
