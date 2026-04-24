// gen-handlebars/src/index.js
//
// Third renderer, different engine/language. Reads content_json (structured
// data, e.g. devices, customers) and renders Handlebars templates against it,
// writing the output to content_html.
//
// Exact same DB contract as gen-jinja (Python) and gen-twig (PHP).

import express from 'express';
import pg from 'pg';
import Handlebars from 'handlebars';
import crypto from 'node:crypto';

const {
  DATABASE_URL,
  RENDERER_NAME = 'gen-handlebars',
} = process.env;

const pool = new pg.Pool({ connectionString: DATABASE_URL });

// ---- default template ----
const DEFAULT_TPL = `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{{name}}</title></head>
<body>
  <article>
    <h1>{{name}}</h1>
    <dl>
      {{#each this}}
        {{#unless (isObject this)}}
          <dt>{{@key}}</dt><dd>{{this}}</dd>
        {{/unless}}
      {{/each}}
    </dl>
    <footer><small>rendered by {{@root.renderer}} at {{@root.rendered_at}}</small></footer>
  </article>
</body>
</html>`;

// Handlebars helpers
Handlebars.registerHelper('isObject', v =>
  typeof v === 'object' && v !== null && !Array.isArray(v));

// ---- app ----
const app = express();
app.use(express.json());

app.get('/health', (_req, res) =>
  res.json({ ok: true, service: RENDERER_NAME }));

app.get('/capabilities', async (_req, res) => {
  const { rows } = await pool.query(
    `SELECT id FROM schemas WHERE $1 = ANY(renderers) ORDER BY id`,
    [RENDERER_NAME]);
  res.json({ renderer: RENDERER_NAME, supports_schemas: rows.map(r => r.id) });
});

app.post('/render/:externalId', async (req, res) => {
  const { externalId } = req.params;
  const client = await pool.connect();
  try {
    // Pull the JSON payload for this entity
    const { rows } = await client.query(
      `SELECT e.id, cj.data
         FROM entities e
         JOIN content_json cj ON cj.entity_id = e.id
        WHERE e.external_id = $1`,
      [externalId]);
    if (rows.length === 0) return res.status(404).json({ error: 'not found' });
    const { id: entityId, data } = rows[0];

    // Allow caller to pass a template_external_id, else use default
    let templateSrc = DEFAULT_TPL;
    if (req.body?.template_external_id) {
      const { rows: tRows } = await client.query(
        `SELECT ch.body FROM entities e
           JOIN content_html ch ON ch.entity_id = e.id
          WHERE e.external_id = $1 AND ch.is_template = TRUE
          ORDER BY ch.updated_at DESC LIMIT 1`,
        [req.body.template_external_id]);
      if (tRows.length) templateSrc = tRows[0].body;
    }

    const template = Handlebars.compile(templateSrc);
    const rendered = template(data, {
      data: { root: { renderer: RENDERER_NAME, rendered_at: new Date().toISOString() } },
    });

    const checksum = crypto.createHash('sha256').update(rendered).digest('hex');

    const { rows: ins } = await client.query(
      `INSERT INTO content_html
         (entity_id, body, is_template, rendered_from, checksum, source)
       VALUES ($1,$2,FALSE,$1,$3,'generator')
       RETURNING id`,
      [entityId, rendered, checksum]);

    await client.query(
      `INSERT INTO audit_log (content_table, entity_id, content_id, source, action, after_state)
       VALUES ('content_html', $1, $2, 'generator', 'render',
               jsonb_build_object('renderer', $3::text, 'bytes', $4::int))`,
      [entityId, ins[0].id, RENDERER_NAME, rendered.length]);

    res.json({
      renderer: RENDERER_NAME,
      entity_id: entityId,
      content_html_id: ins[0].id,
      bytes: rendered.length,
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    client.release();
  }
});

app.get('/preview/:externalId', async (req, res) => {
  const { rows } = await pool.query(
    `SELECT cj.data FROM entities e
       JOIN content_json cj ON cj.entity_id = e.id
      WHERE e.external_id = $1`, [req.params.externalId]);
  if (rows.length === 0) return res.status(404).send('not found');
  const html = Handlebars.compile(DEFAULT_TPL)(rows[0].data, {
    data: { root: { renderer: RENDERER_NAME, rendered_at: new Date().toISOString() } },
  });
  res.type('html').send(html);
});

app.listen(6003, () => console.log(`${RENDERER_NAME} listening on :6003`));
