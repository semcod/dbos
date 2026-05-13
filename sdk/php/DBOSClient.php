<?php
/**
 * Platform OS SDK — PHP client.
 *
 * Usage:
 *   $db = new DBOSClient('http://localhost:3000');
 *   $db->login('admin@platform.local', 'demo1234');
 *   $entities = $db->listEntities();
 *   $db->createServiceMapping('imap-to-email', 'vfs-imap', 'filesystem-email', ['entity_type'=>'mail']);
 */
class DBOSClient {
    private string $base;
    private ?string $token = null;

    public function __construct(string $baseURL) {
        $this->base = rtrim($baseURL, '/');
    }

    public function login(string $email, string $password): array {
        $r = $this->post('/auth/login', ['email' => $email, 'password' => $password]);
        $this->token = $r['token'] ?? null;
        return $r;
    }

    public function listEntities(?string $entityType = null, int $limit = 100): array {
        $qs = http_build_query(array_filter(['entity_type' => $entityType, 'limit' => $limit]));
        return $this->get('/api/entities?' . $qs);
    }

    public function getEntity(string $externalId): array {
        return $this->get('/api/entity?external_id=' . urlencode($externalId));
    }

    public function createEntity(string $external_id, string $entity_type, string $schema_id, array $content, array $metadata = []): array {
        return $this->post('/api/entities', [
            'external_id' => $external_id,
            'entity_type' => $entity_type,
            'schema_id' => $schema_id,
            'content' => $content,
            'metadata' => $metadata,
        ]);
    }

    public function updateEntity(string $external_id, array $content): array {
        return $this->patch('/api/entity?external_id=' . urlencode($external_id), ['content' => $content]);
    }

    public function deleteEntity(string $external_id): array {
        return $this->req('DELETE', '/api/entity?external_id=' . urlencode($external_id));
    }

    public function listStorageBackends(): array { return $this->get('/api/storage-backends'); }
    public function listProtocolGateways(): array { return $this->get('/api/protocol-gateways'); }
    public function listInboundSources(): array   { return $this->get('/api/inbound-sources'); }
    public function listServiceMappings(): array   { return $this->get('/api/service-mappings'); }

    public function createServiceMapping(string $id, string $source_service, string $target_service, array $filter = [], array $transform = [], bool $enabled = true): array {
        return $this->post('/api/service-mappings', [
            'id' => $id,
            'source_service' => $source_service,
            'target_service' => $target_service,
            'filter' => $filter,
            'transform' => $transform,
            'enabled' => $enabled,
        ]);
    }

    public function getConfig(): array { return $this->get('/api/config'); }
    public function setConfig(string $key, string $value): array { return $this->patch('/api/config', [$key => $value]); }

    private function req(string $method, string $path, ?array $body = null): array {
        $url = $this->base . $path;
        $opts = [
            'http' => [
                'method' => $method,
                'header' => "Content-Type: application/json\r\n",
                'ignore_errors' => true,
            ]
        ];
        if ($this->token) {
            $opts['http']['header'] .= "Authorization: Bearer {$this->token}\r\n";
        }
        if ($body !== null) {
            $opts['http']['content'] = json_encode($body);
        }
        $ctx = stream_context_create($opts);
        $res = file_get_contents($url, false, $ctx);
        if ($res === false) {
            throw new DBOSAPIError(0, ['error' => 'request failed']);
        }
        $data = json_decode($res, true) ?? [];
        // extract status from response headers
        $status = 200;
        if (isset($http_response_header[0]) && preg_match('/HTTP\/\d\.\d (\d+)/', $http_response_header[0], $m)) {
            $status = (int)$m[1];
        }
        if ($status >= 400) {
            throw new DBOSAPIError($status, $data);
        }
        return $data;
    }

    private function get(string $path): array   { return $this->req('GET', $path); }
    private function post(string $path, array $body): array { return $this->req('POST', $path, $body); }
    private function patch(string $path, array $body): array { return $this->req('PATCH', $path, $body); }
}

class DBOSAPIError extends Exception {
    public int $status;
    public array $body;
    public function __construct(int $status, array $body) {
        parent::__construct("HTTP {$status}: " . json_encode($body));
        $this->status = $status;
        $this->body = $body;
    }
}
