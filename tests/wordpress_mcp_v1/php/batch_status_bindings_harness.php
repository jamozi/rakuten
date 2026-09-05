<?php
/** Pure fake-storage GET harness: no WordPress bootstrap, network, approval or apply. */
declare(strict_types=1);

define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');
date_default_timezone_set('UTC');

final class WP_Error
{
    public function __construct(public string $code, $message = '', $data = array()) {}
}

function is_wp_error($value): bool { return $value instanceof WP_Error; }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function require_true($condition, string $code): void
{
    if (true !== $condition) { throw new RuntimeException($code); }
}

final class WP_REST_Request extends ArrayObject
{
    public function get_json_params() { throw new RuntimeException('GET_READ_JSON_FORBIDDEN'); }
    public function get_header($name) { throw new RuntimeException('GET_APPLY_HEADER_FORBIDDEN'); }
}

final class RAOS_Codex_MCP_Abilities
{
    public static function plugin_runtime_revision(): string
    {
        return RAOS_Codex_MCP_Store::RUNTIME_REVISION;
    }
}

final class ReadOnlyBatchDB
{
    public string $prefix = 'synthetic_';
    public array $batch = array();
    public array $rows = array();
    public array $reads = array();
    public function prepare($query, ...$values): array
    {
        require_true(str_starts_with($query, 'SELECT * FROM '), 'GET_WRITE_QUERY_FORBIDDEN');
        return array($query, $values);
    }
    public function get_row($prepared, $mode)
    {
        $this->reads[] = $prepared;
        require_true(ARRAY_A === $mode && count($prepared[1]) === 1, 'GET_QUERY_INVALID');
        $id = $prepared[1][0];
        if (str_contains($prepared[0], 'publication_batches_v1')) {
            return $id === $this->batch['batch_token'] ? $this->batch : null;
        }
        return $this->rows[$id] ?? null;
    }
    public function __call($name, $arguments)
    {
        throw new RuntimeException('GET_STORAGE_MUTATION_FORBIDDEN_' . $name);
    }
}

$includes = dirname(__DIR__, 3) . '/changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/';
require $includes . 'class-raos-codex-mcp-store.php';
require $includes . 'class-raos-codex-mcp-content.php';
require $includes . 'class-raos-codex-mcp-deployment.php';
define('RAOS_CODEX_MCP_RUNTIME_REVISION', RAOS_Codex_MCP_Store::RUNTIME_REVISION);
require_true(RAOS_Codex_MCP_Deployment::RUNTIME_REVISION === RAOS_CODEX_MCP_RUNTIME_REVISION, 'RUNTIME_MIXED');

function content_row(string $id, string $post_type): array
{
    $created = gmdate('Y-m-d H:i:s', time() - 30);
    $expires = gmdate('Y-m-d H:i:s', time() + 3600);
    $before = array(
        'schema' => 'ContentDocumentV1', 'id' => 'page' === $post_type ? 19 : 28,
        'post_type' => $post_type, 'status' => 'publish', 'title' => 'Before',
        'slug' => 'synthetic-existing', 'excerpt' => '', 'block_markup' => '<p>Before</p>',
        'taxonomies' => array(), 'media_ids' => array(), 'revision_id' => 12,
        'modified_gmt' => '2026-09-05T00:00:00Z',
    );
    $after = $before;
    $after['title'] = 'After';
    $after['block_markup'] = '<p>After</p>';
    $before_hash = RAOS_Codex_MCP_Content::document_hash($before);
    $after_hash = RAOS_Codex_MCP_Content::document_hash($after);
    $manifest = array(
        'schema' => 'ContentPublicationManifestV1', 'target_status' => 'publish',
        'post_type' => $post_type, 'post_id' => $before['id'],
        'before_sha256' => $before_hash, 'after_sha256' => $after_hash,
        'precondition' => array('revision_id' => 12, 'modified_gmt' => $before['modified_gmt'], 'content_sha256' => $before_hash),
    );
    $payload = array(
        'schema' => 'ContentReleaseProposalV1', 'proposal_id' => $id,
        'created_by' => 5, 'created_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($created),
        'expires_at_gmt' => RAOS_Codex_MCP_Store::timestamp_iso($expires),
        'idempotency_key' => str_repeat('e', 64), 'before' => $before, 'after' => $after,
        'before_sha256' => $before_hash, 'after_sha256' => $after_hash,
        'publication_manifest_sha256' => RAOS_Codex_MCP_Store::hash($manifest),
    );
    return array(
        'proposal_id' => $id, 'kind' => 'CONTENT_RELEASE', 'state' => 'PENDING',
        'created_by' => 5, 'created_at_gmt' => $created, 'expires_at_gmt' => $expires,
        'approved_at_gmt' => null, 'before_sha256' => $before_hash, 'after_sha256' => $after_hash,
        'idempotency_key' => $payload['idempotency_key'], 'payload_json' => json_encode($payload), 'receipt_json' => null,
    );
}

$wpdb = new ReadOnlyBatchDB();
$post_id = str_repeat('a', 64);
$page_id = str_repeat('b', 64);
$theme_id = str_repeat('c', 64);
$wpdb->rows[$post_id] = content_row($post_id, 'post');
$wpdb->rows[$page_id] = content_row($page_id, 'page');
$theme = $wpdb->rows[$post_id];
$theme_payload = json_decode($theme['payload_json'], true);
$theme_payload = array_intersect_key($theme_payload, array_flip(array(
    'created_by', 'created_at_gmt', 'expires_at_gmt', 'idempotency_key'
)));
$theme_payload += array(
    'schema' => 'CodeReleaseProposalV1', 'proposal_id' => $theme_id, 'kind' => 'THEME_RELEASE',
    'before_tree_sha256' => null, 'after_tree_sha256' => str_repeat('f', 64),
    'code_package' => array('file_manifest_sha256' => str_repeat('f', 64)),
);
$theme['proposal_id'] = $theme_id;
$theme['kind'] = 'THEME_RELEASE';
$theme['before_sha256'] = null;
$theme['after_sha256'] = str_repeat('f', 64);
$theme['payload_json'] = json_encode($theme_payload);
$wpdb->rows[$theme_id] = $theme;
$ids = array($post_id, $page_id, $theme_id);
$manifest = array(
    'schema' => 'RAOSWordPressPublicationBatchManifestV1',
    'expected_theme_tree_sha256' => str_repeat('f', 64), 'proposal_count' => count($ids),
    'proposals' => array_map(static fn($id) => array(
        'proposal_id' => $id, 'kind' => $GLOBALS['wpdb']->rows[$id]['kind'],
        'before_sha256' => $GLOBALS['wpdb']->rows[$id]['before_sha256'],
        'after_sha256' => $GLOBALS['wpdb']->rows[$id]['after_sha256'],
    ), $ids),
);
$wpdb->batch = array(
    'batch_token' => str_repeat('d', 64), 'state' => 'REGISTERED', 'created_by' => 5,
    'created_at_gmt' => $theme['created_at_gmt'], 'expires_at_gmt' => $theme['expires_at_gmt'],
    'applying_at_gmt' => null, 'batch_manifest_sha256' => RAOS_Codex_MCP_Store::hash($manifest),
    'proposal_ids_json' => json_encode($ids), 'manifest_json' => json_encode($manifest),
);
$controller = new RAOS_Codex_MCP_Deployment(null);
$request = new WP_REST_Request(array('batch_token' => $wpdb->batch['batch_token']));
$original = serialize(array($wpdb->rows, $wpdb->batch));
$status = $controller->get_publication_batch($request);
require_true(! is_wp_error($status), 'GET_VALID_STATUS_REFUSED');
require_true(array_keys($status['proposal_bindings']) === $ids, 'GET_MEMBER_SET_WRONG');
require_true(false === $status['preconditions_ready'] && 'REGISTERED' === $status['state'], 'GET_APPROVED_BATCH');
foreach ($ids as $id) {
    $row = $wpdb->rows[$id];
    $payload = json_decode($row['payload_json'], true);
    require_true($status['proposal_bindings'][$id] === array(
        'kind' => $row['kind'], 'idempotency_key' => $row['idempotency_key'],
        'before_sha256' => $row['before_sha256'], 'after_sha256' => $row['after_sha256'],
        'post_id' => 'CONTENT_RELEASE' === $row['kind'] ? $payload['after']['id'] : null,
        'post_type' => 'CONTENT_RELEASE' === $row['kind'] ? $payload['after']['post_type'] : null,
    ), 'GET_IDENTITY_OR_PRIVATE_FIELDS_WRONG');
}
require_true($original === serialize(array($wpdb->rows, $wpdb->batch)), 'GET_STORAGE_MUTATED');

$original_row = $wpdb->rows[$post_id];
foreach (array('title', 'id', 'post_type', 'idempotency_key', 'expiry', 'hash', 'missing') as $case) {
    $wpdb->rows[$post_id] = $original_row;
    $payload = json_decode($original_row['payload_json'], true);
    if ('idempotency_key' === $case) { $payload['idempotency_key'] = str_repeat('9', 64); }
    elseif ('expiry' === $case) { $payload['expires_at_gmt'] = '2099-01-01T00:00:00Z'; }
    elseif ('hash' === $case) { $wpdb->rows[$post_id]['after_sha256'] = str_repeat('9', 64); }
    elseif ('missing' === $case) { unset($payload['after']['id']); }
    else { $payload['after'][$case] = 'tampered'; }
    $wpdb->rows[$post_id]['payload_json'] = json_encode($payload);
    $before_get = serialize(array($wpdb->rows, $wpdb->batch));
    $result = $controller->get_publication_batch($request);
    require_true(is_wp_error($result), 'GET_TAMPER_ACCEPTED_' . $case);
    require_true($before_get === serialize(array($wpdb->rows, $wpdb->batch)), 'GET_TAMPER_MUTATED');
}
$wpdb->rows[$post_id] = $original_row;
// Even internally matching legacy payloads must not emit ill-typed identity maps.
foreach (array('idempotency-type', 'unsupported-kind') as $case) {
    $wpdb->rows[$theme_id] = $theme;
    $payload = json_decode($theme['payload_json'], true);
    if ('idempotency-type' === $case) {
        $wpdb->rows[$theme_id]['idempotency_key'] = true;
        $payload['idempotency_key'] = true;
    } else {
        $wpdb->rows[$theme_id]['kind'] = 'PLUGIN_CHANGE';
        $payload['kind'] = 'PLUGIN_CHANGE';
    }
    $wpdb->rows[$theme_id]['payload_json'] = json_encode($payload);
    $before_get = serialize(array($wpdb->rows, $wpdb->batch));
    $result = $controller->get_publication_batch($request);
    require_true(is_wp_error($result), 'GET_INVALID_BINDING_TYPE_ACCEPTED_' . $case);
    require_true($before_get === serialize(array($wpdb->rows, $wpdb->batch)), 'GET_TYPE_CHECK_MUTATED');
}
$wpdb->rows[$theme_id] = $theme;
unset($wpdb->rows[$page_id]);
require_true(is_wp_error($controller->get_publication_batch($request)), 'GET_MISSING_MEMBER_ACCEPTED');
require_true(is_wp_error($controller->get_publication_batch(new WP_REST_Request(array('batch_token' => '../bad')))), 'GET_BAD_TOKEN_ACCEPTED');
echo "BATCH_STATUS_BINDINGS_READ_ONLY_OK\n";
