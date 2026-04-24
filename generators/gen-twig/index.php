<?php
/**
 * gen-twig  —  PHP + Twig renderer.
 *
 * Reads `content_html` rows where is_template=TRUE, fills placeholders
 * with data pulled from `content_json` or `content_markdown` (depending
 * on what the target entity is), and writes the result back as a new
 * `content_html` row with source='generator'.
 *
 * Same contract as gen-jinja / gen-handlebars — just a different engine
 * and language. Swapping this for another PHP renderer would be a drop-in
 * replacement because it only interacts with tables, not with other services.
 */

require_once __DIR__ . '/vendor/autoload.php';

use Twig\Loader\ArrayLoader;
use Twig\Environment;

$RENDERER_NAME = getenv('RENDERER_NAME') ?: 'gen-twig';
$DSN           = getenv('DSN');
$DB_USER       = getenv('DB_USER');
$DB_PASS       = getenv('DB_PASS');

function db(): PDO {
    global $DSN, $DB_USER, $DB_PASS;
    static $pdo = null;
    if (!$pdo) {
        $pdo = new PDO($DSN, $DB_USER, $DB_PASS, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        ]);
    }
    return $pdo;
}

function json_out($data, int $status = 200): void {
    http_response_code($status);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// ------------- routing --------------
$path   = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$method = $_SERVER['REQUEST_METHOD'];

if ($path === '/health') {
    json_out(['ok' => true, 'service' => $RENDERER_NAME]);
}

if ($path === '/capabilities') {
    $stmt = db()->prepare("SELECT id FROM schemas WHERE :r = ANY(renderers) ORDER BY id");
    $stmt->execute([':r' => $RENDERER_NAME]);
    json_out(['renderer' => $RENDERER_NAME,
              'supports_schemas' => $stmt->fetchAll(PDO::FETCH_COLUMN)]);
}

// /render/{page_external_id}  — render an HTML template entity against a data entity
if (preg_match('#^/render/([^/]+)$#', $path, $m) && $method === 'POST') {
    $pageExtId = $m[1];

    $input = json_decode(file_get_contents('php://input'), true) ?: [];
    $dataExtId = $input['data_from'] ?? null;

    // Load the template
    $stmt = db()->prepare("
        SELECT e.id AS entity_id, ch.body, ch.variables
          FROM entities e
          JOIN content_html ch ON ch.entity_id = e.id
         WHERE e.external_id = :ext AND ch.is_template = TRUE
         ORDER BY ch.updated_at DESC LIMIT 1");
    $stmt->execute([':ext' => $pageExtId]);
    $tpl = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$tpl) json_out(['error' => "no template at '$pageExtId'"], 404);

    // Collect data from the requested source entity (JSON first, markdown fallback)
    $vars = [
        'renderer'    => $RENDERER_NAME,
        'rendered_at' => gmdate('c'),
        'title'       => $pageExtId,
    ];

    if ($dataExtId) {
        $s = db()->prepare("
            SELECT cj.data FROM entities e
              JOIN content_json cj ON cj.entity_id = e.id
             WHERE e.external_id = :x");
        $s->execute([':x' => $dataExtId]);
        if ($r = $s->fetch(PDO::FETCH_ASSOC)) {
            $vars = array_merge($vars, json_decode($r['data'], true) ?? []);
        } else {
            $s = db()->prepare("
                SELECT cm.body, cm.front_matter FROM entities e
                  JOIN content_markdown cm ON cm.entity_id = e.id
                 WHERE e.external_id = :x");
            $s->execute([':x' => $dataExtId]);
            if ($r = $s->fetch(PDO::FETCH_ASSOC)) {
                $fm = json_decode($r['front_matter'], true) ?? [];
                $vars = array_merge($vars, $fm, ['body' => $r['body']]);
            }
        }
    }

    // Render with Twig
    try {
        $twig = new Environment(
            new ArrayLoader(['t' => $tpl['body']]),
            ['autoescape' => 'html']
        );
        $rendered = $twig->render('t', $vars);
    } catch (\Throwable $e) {
        json_out(['error' => 'twig render failed', 'detail' => $e->getMessage()], 500);
    }

    $checksum = hash('sha256', $rendered);
    $ins = db()->prepare("
        INSERT INTO content_html (entity_id, body, is_template, rendered_from, checksum, source)
        VALUES (:e, :b, FALSE, :e, :c, 'generator')
        RETURNING id");
    $ins->execute([':e' => $tpl['entity_id'], ':b' => $rendered, ':c' => $checksum]);
    $htmlId = $ins->fetchColumn();

    db()->prepare("
        INSERT INTO audit_log (content_table, entity_id, content_id, source, action, after_state)
        VALUES ('content_html', :e, :h, 'generator', 'render',
                jsonb_build_object('renderer', :r, 'bytes', :sz))")
        ->execute([':e' => $tpl['entity_id'], ':h' => $htmlId,
                   ':r' => $RENDERER_NAME, ':sz' => strlen($rendered)]);

    json_out([
        'renderer' => $RENDERER_NAME,
        'entity_id' => $tpl['entity_id'],
        'content_html_id' => $htmlId,
        'bytes' => strlen($rendered),
    ]);
}

// Preview — returns HTML directly
if (preg_match('#^/preview/([^/]+)$#', $path, $m) && $method === 'GET') {
    $stmt = db()->prepare("
        SELECT ch.body FROM entities e
          JOIN content_html ch ON ch.entity_id = e.id
         WHERE e.external_id = :x AND ch.is_template = TRUE LIMIT 1");
    $stmt->execute([':x' => $m[1]]);
    $body = $stmt->fetchColumn();
    if (!$body) json_out(['error' => 'not found'], 404);
    header('Content-Type: text/html; charset=utf-8');
    $twig = new Environment(new ArrayLoader(['t' => $body]));
    echo $twig->render('t', [
        'title' => $m[1],
        'body'  => '<p>preview</p>',
        'renderer' => $RENDERER_NAME,
        'rendered_at' => gmdate('c'),
    ]);
    exit;
}

json_out(['error' => 'not found', 'path' => $path], 404);
