// sync-engine/src/index.js
//
// Filesystem  ->  correct content_* table, chosen by MIME type.
//
// Crucially, the mapping MIME -> content table is NOT hard-coded here — it
// comes from `mime_types` in Postgres. Add a new MIME row with a new
// content_* table and sync-engine handles it without a code change.

import chokidar from 'chokidar';
import path from 'node:path';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import pg from 'pg';
import yaml from 'js-yaml';
import matter from 'gray-matter';
import { XMLParser } from 'fast-xml-parser';
import { compare as jsonDiff } from 'fast-json-patch';

const {
  DATABASE_URL,
  WATCH_PATH   = '/data',
  MERGE_POLICY = 'lww',
} = process.env;

const pool = new pg.Pool({ connectionString: DATABASE_URL });

// --------------------------------------------------------------------------
// MIME detection by extension; authoritative mapping MIME -> content table
// lives in Postgres.
// --------------------------------------------------------------------------
const EXT_TO_MIME = {
  '.json': 'application/json',
  '.yaml': 'application/yaml',
  '.yml':  'application/yaml',
  '.xml':  'application/xml',
  '.html': 'text/html',
  '.htm':  'text/html',
  '.md':   'text/markdown',
  '.markdown': 'text/markdown',
  '.txt':  'text/plain',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg':  'image/svg+xml',
  '.pdf':  'application/pdf',
};

// Top-level directory -> entity_type + schema_id. Matches schemas.fs_path_template.
const DIR_TO_ENTITY = {
  devices:   { entity_type: 'device',   schema_id: 'device_v1'   },
  customers: { entity_type: 'customer', schema_id: 'customer_v1' },
  articles:  { entity_type: 'article',  schema_id: 'article_v1'  },
  pages:     { entity_type: 'page',     schema_id: 'page_v1'     },
  scenarios: { entity_type: 'scenario', schema_id: 'scenario_v1' },
  protocols: { entity_type: 'protocol', schema_id: 'protocol_v1' },
  images:    { entity_type: 'image',    schema_id: 'image_v1'    },
};

// --------------------------------------------------------------------------
// MIME registry cache
// --------------------------------------------------------------------------
let mimeRegistry = new Map();

async function loadMimeRegistry() {
  const { rows } = await pool.query(
    `SELECT mime, content_table, storage_mode, category FROM mime_types`);
  mimeRegistry = new Map(rows.map(r => [r.mime, r]));
  console.log(`[sync] loaded ${rows.length} MIME routings from DB`);
}

function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

// --------------------------------------------------------------------------
// Per-MIME parsers. Return what each content_* table needs to be written.
// --------------------------------------------------------------------------
async function parse(mime, buf, filename) {
  switch (mime) {
    case 'application/json': {
      return { kind: 'json', data: JSON.parse(buf.toString('utf8')) };
    }
    case 'application/yaml': {
      return {
        kind: 'yaml',
        raw_text: buf.toString('utf8'),
        parsed:   yaml.load(buf.toString('utf8')) ?? {},
      };
    }
    case 'application/xml': {
      const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_' });
      const parsed = parser.parse(buf.toString('utf8'));
      const root   = Object.keys(parsed).find(k => !k.startsWith('?')) ?? null;
      return { kind: 'xml', raw_text: buf.toString('utf8'), parsed, root_element: root };
    }
    case 'text/html':
    case 'image/svg+xml': {
      const body = buf.toString('utf8');
      return {
        kind: 'html',
        body,
        is_template: /\{\{|\{%/.test(body),       // Twig / Jinja style placeholders
        template_engine: /\{%/.test(body) ? 'twig' : (/\{\{/.test(body) ? 'mustache' : null),
      };
    }
    case 'text/markdown':
    case 'text/plain': {
      const text = buf.toString('utf8');
      const fm   = matter(text);
      return {
        kind: 'markdown',
        body: fm.content,
        front_matter: fm.data ?? {},
        word_count: fm.content.split(/\s+/).filter(Boolean).length,
      };
    }
    case 'image/png':
    case 'image/jpeg':
    case 'application/pdf':
    default: {
      return {
        kind: 'binary',
        bytes: buf,
        size_bytes: buf.length,
        mime,
      };
    }
  }
}

// --------------------------------------------------------------------------
// Upsert an entity + route payload to the correct content_* table
// --------------------------------------------------------------------------
async function upsertEntity({ external_id, entity_type, schema_id, mime }, parsed) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    // Ensure entity row exists (UPSERT by external_id)
    const { rows: eRows } = await client.query(
      `INSERT INTO entities (external_id, entity_type, schema_id, primary_mime)
       VALUES ($1,$2,$3,$4)
       ON CONFLICT (external_id) DO UPDATE SET entity_type=EXCLUDED.entity_type
       RETURNING id, version`,
      [external_id, entity_type, schema_id, mime]);
    const entityId  = eRows[0].id;

    const checksumBase = parsed.body ?? parsed.raw_text ?? JSON.stringify(parsed.data ?? parsed.parsed ?? parsed.bytes?.toString('hex'));
    const checksum = sha256(Buffer.from(checksumBase ?? ''));

    switch (parsed.kind) {
      case 'json':
        await client.query(
          `INSERT INTO content_json (entity_id, data, checksum, source)
           VALUES ($1,$2,$3,'filesystem')
           ON CONFLICT (entity_id) DO UPDATE
             SET data=EXCLUDED.data, checksum=EXCLUDED.checksum, source='filesystem'
             WHERE content_json.checksum <> EXCLUDED.checksum`,
          [entityId, parsed.data, checksum]);
        break;

      case 'yaml':
        await client.query(
          `INSERT INTO content_yaml (entity_id, raw_text, parsed, checksum, source)
           VALUES ($1,$2,$3,$4,'filesystem')
           ON CONFLICT (entity_id) DO UPDATE
             SET raw_text=EXCLUDED.raw_text, parsed=EXCLUDED.parsed,
                 checksum=EXCLUDED.checksum, source='filesystem'
             WHERE content_yaml.checksum <> EXCLUDED.checksum`,
          [entityId, parsed.raw_text, parsed.parsed, checksum]);
        break;

      case 'xml':
        await client.query(
          `INSERT INTO content_xml (entity_id, raw_text, parsed, root_element, checksum, source)
           VALUES ($1,$2,$3,$4,$5,'filesystem')
           ON CONFLICT (entity_id) DO UPDATE
             SET raw_text=EXCLUDED.raw_text, parsed=EXCLUDED.parsed,
                 root_element=EXCLUDED.root_element,
                 checksum=EXCLUDED.checksum, source='filesystem'
             WHERE content_xml.checksum <> EXCLUDED.checksum`,
          [entityId, parsed.raw_text, parsed.parsed, parsed.root_element, checksum]);
        break;

      case 'html':
        // Multiple HTML rows per entity allowed (source + renders), so we
        // dedupe by checksum rather than entity_id.
        await client.query(
          `INSERT INTO content_html (entity_id, body, is_template, template_engine, checksum, source)
           SELECT $1,$2,$3,$4,$5,'filesystem'
           WHERE NOT EXISTS (SELECT 1 FROM content_html WHERE entity_id=$1 AND checksum=$5)`,
          [entityId, parsed.body, parsed.is_template, parsed.template_engine, checksum]);
        break;

      case 'markdown':
        await client.query(
          `INSERT INTO content_markdown (entity_id, body, front_matter, word_count, checksum, source)
           VALUES ($1,$2,$3,$4,$5,'filesystem')
           ON CONFLICT (entity_id) DO UPDATE
             SET body=EXCLUDED.body, front_matter=EXCLUDED.front_matter,
                 word_count=EXCLUDED.word_count,
                 checksum=EXCLUDED.checksum, source='filesystem'
             WHERE content_markdown.checksum <> EXCLUDED.checksum`,
          [entityId, parsed.body, parsed.front_matter, parsed.word_count, checksum]);
        break;

      case 'binary':
        await client.query(
          `INSERT INTO content_binary (entity_id, mime, storage_mode, bytes, size_bytes, checksum, source)
           VALUES ($1,$2,'db',$3,$4,$5,'filesystem')`,
          [entityId, parsed.mime, parsed.bytes, parsed.size_bytes, checksum]);
        break;
    }

    // Audit
    await client.query(
      `INSERT INTO audit_log (content_table, entity_id, source, action)
       VALUES ($1, $2, 'filesystem', 'upsert')`,
      [`content_${parsed.kind === 'markdown' ? 'markdown' : parsed.kind}`, entityId]);

    await client.query('COMMIT');
    console.log(`[sync] ✓ ${external_id} -> content_${parsed.kind}`);
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

// --------------------------------------------------------------------------
// File event handler
// --------------------------------------------------------------------------
async function handleFile(absPath) {
  const rel   = path.relative(WATCH_PATH, absPath);
  const [dir] = rel.split(path.sep);
  const dirMap = DIR_TO_ENTITY[dir];
  if (!dirMap) {
    console.warn(`[sync] ? ignore ${rel} (no entity mapping for '${dir}/')`);
    return;
  }

  const ext  = path.extname(absPath).toLowerCase();
  const mime = EXT_TO_MIME[ext];
  if (!mime) {
    console.warn(`[sync] ? ignore ${rel} (unknown extension ${ext})`);
    return;
  }

  const external_id = path.basename(absPath, ext);

  try {
    const buf    = await fs.readFile(absPath);
    const parsed = await parse(mime, buf, path.basename(absPath));
    await upsertEntity(
      { external_id, entity_type: dirMap.entity_type, schema_id: dirMap.schema_id, mime },
      parsed
    );
  } catch (err) {
    console.error(`[sync] ✗ ${rel}: ${err.message}`);
  }
}

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------
async function main() {
  console.log('[sync] starting');
  console.log(`[sync] watch=${WATCH_PATH} policy=${MERGE_POLICY}`);

  // Wait for schema init
  for (let i = 0; i < 30; i++) {
    try { await pool.query('SELECT 1 FROM mime_types LIMIT 1'); break; }
    catch { console.log('[sync] waiting for DB init…'); await new Promise(r => setTimeout(r, 2000)); }
  }
  await loadMimeRegistry();

  chokidar.watch(WATCH_PATH, {
    ignored: /(^|\/)\..*|node_modules/,
    persistent: true,
    ignoreInitial: false,
    awaitWriteFinish: { stabilityThreshold: 300 },
  })
  .on('add',    handleFile)
  .on('change', handleFile)
  .on('unlink', f => console.log(`[sync] - ${f}  (soft-delete not implemented in demo)`));
}

main().catch(err => { console.error(err); process.exit(1); });
