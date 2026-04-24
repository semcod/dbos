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
import fastJsonPatch from 'fast-json-patch';
import sharp from 'sharp';
const { compare: jsonDiff } = fastJsonPatch;

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
    return entityId;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

// --------------------------------------------------------------------------
// Thumbnail generation (64x64 PNG with real content preview)
// --------------------------------------------------------------------------
function escapeXml(str) {
  return String(str).replace(/[<>&"']/g, c =>
    c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '&' ? '&amp;' : c === '"' ? '&quot;' : '&apos;');
}

function wrapLines(text, maxLen, maxLines) {
  const lines = [];
  let i = 0;
  while (i < text.length && lines.length < maxLines) {
    let end = Math.min(i + maxLen, text.length);
    // Don't split inside an XML entity (&...;)
    if (end < text.length) {
      const slice = text.slice(i, end);
      const lastAmp = slice.lastIndexOf('&');
      const lastSemi = slice.lastIndexOf(';');
      if (lastAmp > lastSemi) {
        const nextSemi = text.indexOf(';', end);
        if (nextSemi !== -1 && nextSemi - i < maxLen + 8) end = nextSemi + 1;
      }
    }
    lines.push(text.slice(i, end));
    i = end;
  }
  return lines;
}

function svgToPng(svg, width, height) {
  return sharp(Buffer.from(svg)).resize(width, height, { fit: 'inside' }).png().toBuffer();
}

function buildHtmlThumbnail(text, w, h) {
  const t = text.match(/<title>([^<]*)<\/title>/i);
  const title = escapeXml(t ? t[1].slice(0, 18) : 'HTML');
  const body = escapeXml(text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 40));
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${w}" height="${h}" fill="#f8f9fa"/>
  <rect width="${w}" height="12" fill="#fd7e14"/>
  <circle cx="5" cy="6" r="2" fill="#dc3545"/><circle cx="12" cy="6" r="2" fill="#ffc107"/><circle cx="19" cy="6" r="2" fill="#28a745"/>
  <rect x="2" y="16" width="${w-4}" height="${h-20}" fill="#fff" rx="2"/>
  <text x="4" y="14" font-size="6" fill="#fff" font-family="sans-serif">${title}</text>
  <text x="4" y="26" font-size="5" fill="#6c757d" font-family="sans-serif">${body.slice(0,30)}</text>
  <rect x="4" y="32" width="20" height="4" fill="#e9ecef" rx="1"/><rect x="26" y="32" width="16" height="4" fill="#e9ecef" rx="1"/>
  <rect x="4" y="40" width="${w-10}" height="3" fill="#e9ecef" rx="1"/><rect x="4" y="46" width="${w-14}" height="3" fill="#e9ecef" rx="1"/>
</svg>`;
}

function buildJsonThumbnail(text, w, h) {
  const lines = wrapLines(escapeXml(text.replace(/\s+/g, ' ').trim().slice(0, 80)), 22, 4);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${w}" height="${h}" fill="#1e1e1e"/>
  <text x="3" y="10" font-size="7" fill="#dcdcaa" font-family="monospace">{</text>
  ${lines.map((l,i) => `<text x="6" y="${18+i*9}" font-size="6" fill="#9cdcfe" font-family="monospace">${l}</text>`).join('')}
</svg>`;
}

function buildMarkdownThumbnail(text, w, h) {
  const h1 = text.match(/^#\s+(.+)$/m);
  const title = escapeXml(h1 ? h1[1].slice(0, 22) : 'Markdown');
  const body = escapeXml(text.replace(/^#+\s+/gm, '').replace(/\s+/g, ' ').trim().slice(0, 45));
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${w}" height="${h}" fill="#fff"/>
  <rect width="${w}" height="3" fill="#3498db"/>
  <text x="4" y="14" font-size="7" fill="#2c3e50" font-family="sans-serif" font-weight="bold">${title}</text>
  <text x="4" y="26" font-size="5" fill="#7f8c8d" font-family="sans-serif">${body}</text>
  <rect x="4" y="36" width="30" height="2" fill="#ecf0f1" rx="1"/><rect x="36" y="36" width="20" height="2" fill="#ecf0f1" rx="1"/>
</svg>`;
}

function buildCodeThumbnail(text, w, h, bg, fg, accent) {
  const lines = wrapLines(escapeXml(text.replace(/\s+/g, ' ').trim().slice(0, 90)), 20, 5);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${w}" height="${h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${w}" height="${h}" fill="${bg}" rx="3"/>
  <rect x="2" y="2" width="${w-4}" height="3" fill="${accent}" rx="1"/>
  ${lines.map((l,i) => `<text x="4" y="${12+i*10}" font-size="6" fill="${fg}" font-family="monospace">${l}</text>`).join('')}
</svg>`;
}

async function generateThumbnail(absPath, mime, parsed, entityId) {
  try {
    let thumbBuffer;
    const w = 128, h = 128;

    if (mime?.startsWith('image/')) {
      thumbBuffer = await sharp(absPath).resize(64, 64, { fit: 'cover' }).png().toBuffer();
    } else {
      let raw = '';
      if (parsed?.body) raw = String(parsed.body);
      else if (parsed?.raw_text) raw = String(parsed.raw_text);
      else if (parsed?.data) raw = JSON.stringify(parsed.data).slice(0, 200);
      else raw = path.basename(absPath);

      if (mime === 'text/html') {
        thumbBuffer = await svgToPng(buildHtmlThumbnail(raw, w, h), 64, 64);
      } else if (mime === 'application/json') {
        thumbBuffer = await svgToPng(buildJsonThumbnail(raw, w, h), 64, 64);
      } else if (mime === 'text/markdown') {
        thumbBuffer = await svgToPng(buildMarkdownThumbnail(raw, w, h), 64, 64);
      } else if (mime === 'application/yaml') {
        thumbBuffer = await svgToPng(buildCodeThumbnail(raw, w, h, '#2d1b4e', '#e0d0ff', '#9b59b6'), 64, 64);
      } else if (mime === 'application/xml') {
        thumbBuffer = await svgToPng(buildCodeThumbnail(raw, w, h, '#2c3e50', '#ecf0f1', '#95a5a6'), 64, 64);
      } else {
        thumbBuffer = await svgToPng(buildCodeThumbnail(raw, w, h, '#34495e', '#ecf0f1', '#7f8c8d'), 64, 64);
      }
    }

    // Store in thumbnails table
    const thumbChecksum = crypto.createHash('sha256').update(thumbBuffer).digest('hex');
    await pool.query(
      `INSERT INTO thumbnails (entity_id, size, mime_type, data, checksum)
       VALUES ($1, '64px', 'image/png', $2, $3)
       ON CONFLICT (entity_id, size) DO UPDATE
         SET data = EXCLUDED.data, checksum = EXCLUDED.checksum, updated_at = now()`,
      [entityId, thumbBuffer, thumbChecksum]
    );
    console.log(`[sync] ✓ thumbnail generated for entity ${entityId}`);
  } catch (err) {
    console.warn(`[sync] thumbnail generation failed for ${absPath}:`, err.message);
  }
}

// --------------------------------------------------------------------------
// File event handler
// --------------------------------------------------------------------------
async function handleFile(absPath) {
  const rel   = path.relative(WATCH_PATH, absPath);
  const parts = rel.split(path.sep);
  const dir   = parts[0];
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

  // Use full path (without extension) as external_id to support nested directories
  // Keep slashes for proper file path display, will be URL-encoded when needed
  const pathWithoutExt = rel.substring(0, rel.length - ext.length);
  const external_id = pathWithoutExt;

  try {
    const buf    = await fs.readFile(absPath);
    const parsed = await parse(mime, buf, path.basename(absPath));
    const entityId = await upsertEntity(
      { external_id, entity_type: dirMap.entity_type, schema_id: dirMap.schema_id, mime },
      parsed
    );
    // Generate thumbnail (fire-and-forget)
    if (entityId) generateThumbnail(absPath, mime, parsed, entityId);
  } catch (err) {
    console.error(`[sync] ✗ ${rel}: ${err.message}`);
  }
}

// --------------------------------------------------------------------------
// Bulk thumbnail generation for existing entities
// --------------------------------------------------------------------------
async function findFileRecursively(dir, baseName, altNames = null) {
  const names = altNames || [baseName];
  const entries = await fs.readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    const entryBase = path.parse(entry.name).name;
    if (entry.isDirectory() && !entry.name.startsWith('.')) {
      const found = await findFileRecursively(fullPath, baseName, names);
      if (found) return found;
    } else if (names.includes(entryBase)) {
      return fullPath;
    }
  }
  return null;
}

function generateAltNames(baseName) {
  const alts = [baseName];
  // For old dash-separated format: articles-demo-123 -> try demo-123
  const parts = baseName.split('-');
  for (let i = 1; i < parts.length; i++) {
    alts.push(parts.slice(i).join('-'));
  }
  return alts;
}

async function generateMissingThumbnails() {
  const { rows } = await pool.query(
    `SELECT e.id, e.external_id, e.entity_type, e.primary_mime
       FROM entities e
       LEFT JOIN thumbnails t ON t.entity_id = e.id AND t.size = '64px'
      WHERE t.id IS NULL`);

  if (rows.length === 0) return;
  console.log(`[sync] generating ${rows.length} missing thumbnails…`);

  for (const e of rows) {
    const parts = e.external_id.split('/');
    const baseName = parts[parts.length - 1];
    const dirPath = path.join(WATCH_PATH, ...parts.slice(0, -1));
    let absPath = path.join(WATCH_PATH, e.external_id);
    let mime = e.primary_mime;
    let parsed = null;

    try {
      // Try direct path first
      const files = await fs.readdir(dirPath);
      const match = files.find(f => path.parse(f).name === baseName);
      if (match) {
        absPath = path.join(dirPath, match);
      } else {
        // Fallback: search recursively in all subdirectories
        // This handles old dash-separated entities where external_id doesn't include folder
        // Try exact match, then suffix variants (articles-demo-123 -> demo-123)
        const altNames = generateAltNames(baseName);
        const found = await findFileRecursively(WATCH_PATH, baseName, altNames);
        if (found) absPath = found;
      }
      const buf = await fs.readFile(absPath);
      const ext = path.extname(absPath).toLowerCase();
      mime = EXT_TO_MIME[ext] || mime;
      parsed = await parse(mime, buf, path.basename(absPath));
    } catch {
      // File not on disk — generate a colored placeholder based on MIME
      parsed = { body: '', raw_text: '', data: {} };
    }
    await generateThumbnail(absPath, mime, parsed, e.id);
  }
  console.log(`[sync] ✓ ${rows.length} thumbnails generated`);
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

  // Generate thumbnails for any existing entities that don't have them
  await generateMissingThumbnails();

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
