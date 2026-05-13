"""Platform OS SDK — Python client.

All data operations (entities, registry, settings) through the REST API.
Usage:
    from dbos_client import DBOSClient
    db = DBOSClient('http://localhost:3000')
    db.login('admin@platform.local', 'demo1234')
    db.create_entity(external_id='article/hello', entity_type='article', ...)
    db.list_protocol_gateways()
    db.set_config('FTP_USER', 'newuser')
"""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class DBOSClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip('/')
        self.token = None

    # ---------- auth ----------
    def login(self, email: str, password: str):
        r = self._post('/auth/login', body={'email': email, 'password': password})
        self.token = r['token']
        return r

    # ---------- entities ----------
    def list_entities(self, entity_type=None, limit=100):
        qs = f"?limit={limit}"
        if entity_type:
            qs += f"&entity_type={entity_type}"
        return self._get(f'/api/entities{qs}')

    def get_entity(self, external_id: str):
        return self._get(f'/api/entity?external_id={external_id}')

    def create_entity(self, external_id: str, entity_type: str, schema_id: str, content: dict, metadata=None):
        return self._post('/api/entities', body={
            'external_id': external_id,
            'entity_type': entity_type,
            'schema_id': schema_id,
            'content': content,
            'metadata': metadata or {},
        })

    def update_entity(self, external_id: str, content: dict):
        return self._patch(f'/api/entity?external_id={external_id}', body={'content': content})

    def delete_entity(self, external_id: str):
        return self._delete(f'/api/entity?external_id={external_id}')

    # ---------- registry ----------
    def list_storage_backends(self):
        return self._get('/api/storage-backends')

    def list_protocol_gateways(self):
        return self._get('/api/protocol-gateways')

    def list_inbound_sources(self):
        return self._get('/api/inbound-sources')

    def list_service_mappings(self):
        return self._get('/api/service-mappings')

    def create_service_mapping(self, id: str, source_service: str, target_service: str,
                               filter=None, transform=None, enabled=True):
        return self._post('/api/service-mappings', body={
            'id': id,
            'source_service': source_service,
            'target_service': target_service,
            'filter': filter or {},
            'transform': transform or {},
            'enabled': enabled,
        })

    # ---------- config ----------
    def get_config(self):
        return self._get('/api/config')

    def set_config(self, key: str, value: str):
        return self._patch('/api/config', body={key: value})

    # ---------- helpers ----------
    def _req(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, method=method,
                      headers={'Content-Type': 'application/json'})
        if self.token:
            req.add_header('Authorization', f'Bearer {self.token}')
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            text = e.read().decode()
            try:
                err = json.loads(text)
            except json.JSONDecodeError:
                err = {'error': text}
            raise DBOSAPIError(e.code, err)

    def _get(self, path): return self._req('GET', path)
    def _post(self, path, body): return self._req('POST', path, body)
    def _patch(self, path, body): return self._req('PATCH', path, body)
    def _delete(self, path): return self._req('DELETE', path)


class DBOSAPIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


if __name__ == '__main__':
    import sys
    db = DBOSClient(sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:3000')
    db.login('admin@platform.local', 'demo1234')
    print('entities:', len(db.list_entities()['data']))
    print('gateways:', len(db.list_protocol_gateways()['data']))
