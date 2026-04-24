<?php
/**
 * worker-php  —  executes commands whose schema.target_runtime == 'php'.
 * Same /execute contract as worker-python.
 */

$DSN      = getenv('DSN');
$DB_USER  = getenv('DB_USER');
$DB_PASS  = getenv('DB_PASS');

function db(): PDO {
    global $DSN, $DB_USER, $DB_PASS;
    static $pdo = null;
    if (!$pdo) {
        $pdo = new PDO($DSN, $DB_USER, $DB_PASS,
            [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    }
    return $pdo;
}

function json_out($data, int $status = 200): void {
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

$path   = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$method = $_SERVER['REQUEST_METHOD'];

if ($path === '/health') {
    json_out(['ok' => true, 'service' => 'worker-php']);
}

if ($path === '/execute' && $method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true) ?: [];
    $cmd  = $body['command_name'] ?? '';
    $pl   = $body['payload']      ?? [];

    try {
        $result = match ($cmd) {
            'render_page'  => handle_render_page($pl),
            'render_report'=> handle_render_report($pl),
            default        => throw new RuntimeException("unknown command: $cmd"),
        };
        json_out($result);
    } catch (\Throwable $e) {
        json_out(['error' => $e->getMessage()], 500);
    }
}

json_out(['error' => 'not found', 'path' => $path], 404);


// ------------------- handlers -------------------

function handle_render_page(array $pl): array {
    $extId     = $pl['external_id'] ?? $pl['page_id'] ?? null;
    $dataExtId = $pl['data_from']   ?? null;
    if (!$extId) throw new RuntimeException('external_id required');

    $url = sprintf('http://gen-twig:6002/render/%s', rawurlencode($extId));
    $ch  = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode(['data_from' => $dataExtId]),
        CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 10,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return ['status_code' => $code, 'result' => json_decode($resp, true)];
}

function handle_render_report(array $pl): array {
    // Minimal stub demonstrating PDF generation path
    $extId = $pl['template_external_id'] ?? 'landing';

    $stmt = db()->prepare("
        SELECT ch.body FROM entities e
          JOIN content_html ch ON ch.entity_id = e.id
         WHERE e.external_id = :x AND ch.is_template = TRUE
         ORDER BY ch.updated_at DESC LIMIT 1");
    $stmt->execute([':x' => $extId]);
    $body = $stmt->fetchColumn();
    if (!$body) throw new RuntimeException("template $extId not found");

    return ['template' => $extId, 'bytes' => strlen($body),
            'note' => 'PDF conversion stub — wire wkhtmltopdf or Browsershot here'];
}
