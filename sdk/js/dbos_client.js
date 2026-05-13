/**
 * Platform OS SDK — JavaScript/Node client.
 *
 * Usage:
 *   const { DBOSClient } = require('./dbos_client');
 *   const db = new DBOSClient('http://localhost:3000');
 *   await db.login('admin@platform.local', 'demo1234');
 *   const entities = await db.listEntities();
 *   await db.createServiceMapping('imap-to-email', 'vfs-imap', 'filesystem-email', {entity_type:'mail'});
 */

class DBOSClient {
  constructor(baseURL) {
    this.base = baseURL.replace(/\/$/, '');
    this.token = null;
  }

  async _req(method, path, body) {
    const url = this.base + path;
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (this.token) opts.headers.Authorization = `Bearer ${this.token}`;
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new DBOSAPIError(res.status, data);
    return data;
  }

  // auth
  async login(email, password) {
    const r = await this._req('POST', '/auth/login', { email, password });
    this.token = r.token;
    return r;
  }

  // entities
  async listEntities(entityType, limit = 100) {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (entityType) qs.set('entity_type', entityType);
    return this._req('GET', `/api/entities?${qs}`);
  }

  async getEntity(externalId) {
    return this._req('GET', `/api/entity?external_id=${encodeURIComponent(externalId)}`);
  }

  async createEntity(external_id, entity_type, schema_id, content, metadata = {}) {
    return this._req('POST', '/api/entities', { external_id, entity_type, schema_id, content, metadata });
  }

  async updateEntity(external_id, content) {
    return this._req('PATCH', `/api/entity?external_id=${encodeURIComponent(external_id)}`, { content });
  }

  async deleteEntity(external_id) {
    return this._req('DELETE', `/api/entity?external_id=${encodeURIComponent(external_id)}`);
  }

  // registry
  async listStorageBackends() { return this._req('GET', '/api/storage-backends'); }
  async listProtocolGateways() { return this._req('GET', '/api/protocol-gateways'); }
  async listInboundSources()   { return this._req('GET', '/api/inbound-sources'); }
  async listServiceMappings()  { return this._req('GET', '/api/service-mappings'); }

  async createServiceMapping(id, source_service, target_service, filter = {}, transform = {}, enabled = true) {
    return this._req('POST', '/api/service-mappings', { id, source_service, target_service, filter, transform, enabled });
  }

  // config
  async getConfig() { return this._req('GET', '/api/config'); }
  async setConfig(key, value) { return this._req('PATCH', '/api/config', { [key]: value }); }
}

class DBOSAPIError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}: ${JSON.stringify(body)}`);
    this.status = status;
    this.body = body;
  }
}

module.exports = { DBOSClient, DBOSAPIError };
