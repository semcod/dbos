// command-bus/src/index.js
// Routes commands to the correct runtime worker based on the schema's
// `target_runtime` property. Persists every command for audit / retry.

import express from 'express';
import pg from 'pg';

const {
  DATABASE_URL,
  WORKER_PYTHON_URL,
  WORKER_PHP_URL,
} = process.env;

const pool = new pg.Pool({ connectionString: DATABASE_URL });

// Resolve the target runtime by reading the command's schema definition.
async function resolveRuntime(commandName, version = 'v1') {
  const { rows } = await pool.query(
    `SELECT definition FROM schema_registry
      WHERE kind='command' AND name=$1 AND version=$2`,
    [commandName, version]);
  if (rows.length === 0) return null;
  return rows[0].definition.target_runtime ?? 'python';
}

function runtimeUrl(runtime) {
  return {
    python: WORKER_PYTHON_URL,
    php:    WORKER_PHP_URL,
  }[runtime];
}

const app = express();
app.use(express.json({ limit: '5mb' }));

app.get('/health', (_req, res) => res.json({ ok: true, service: 'command-bus' }));

app.post('/execute', async (req, res) => {
  const { command_name, payload, actor_id } = req.body;
  if (!command_name) return res.status(400).json({ error: 'command_name required' });

  const runtime = await resolveRuntime(command_name);
  if (!runtime) return res.status(404).json({ error: `unknown command: ${command_name}` });

  // Persist the command record first (status=pending).
  const { rows } = await pool.query(
    `INSERT INTO commands (command_name, target_runtime, payload, status, actor_id)
     VALUES ($1, $2, $3, 'routing', $4) RETURNING id`,
    [command_name, runtime, payload, actor_id ?? null]);
  const commandId = rows[0].id;

  const targetUrl = runtimeUrl(runtime);
  if (!targetUrl) {
    await pool.query(
      `UPDATE commands SET status='failed', error=$2, completed_at=now() WHERE id=$1`,
      [commandId, `no worker for runtime=${runtime}`]);
    return res.status(502).json({ error: `no worker for runtime ${runtime}` });
  }

  try {
    await pool.query(
      `UPDATE commands SET status='running', started_at=now() WHERE id=$1`, [commandId]);

    const workerResp = await fetch(`${targetUrl}/execute`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ command_id: commandId, command_name, payload }),
    });
    const result = await workerResp.json();

    await pool.query(
      `UPDATE commands SET status=$2, result=$3, completed_at=now() WHERE id=$1`,
      [commandId, workerResp.ok ? 'done' : 'failed', result]);

    res.status(workerResp.status).json({ command_id: commandId, runtime, result });
  } catch (err) {
    await pool.query(
      `UPDATE commands SET status='failed', error=$2, completed_at=now() WHERE id=$1`,
      [commandId, err.message]);
    res.status(500).json({ error: err.message, command_id: commandId });
  }
});

app.get('/commands/:id', async (req, res) => {
  const { rows } = await pool.query(`SELECT * FROM commands WHERE id=$1`, [req.params.id]);
  if (rows.length === 0) return res.status(404).json({ error: 'not found' });
  res.json(rows[0]);
});

app.listen(4000, () => console.log('command-bus listening on :4000'));
