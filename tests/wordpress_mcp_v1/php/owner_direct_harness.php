<?php
/** Deterministic server behavior harness. No WordPress bootstrap or network. */
declare(strict_types=1);
define('ABSPATH', __DIR__ . '/');
define('ARRAY_A', 'ARRAY_A');
define('RAOS_OPERATOR_WRITES_ENABLED', true);
define('RAOS_CODEX_MCP_VERSION', 'test');
class WP_Error {
    public function __construct(public string $code, $message = '', $data = array()) {}
    public function get_error_code() { return $this->code; }
}
function is_wp_error($v) { return $v instanceof WP_Error; }
function wp_json_encode($v, $flags = 0) { return json_encode($v, $flags); }
function get_current_user_id() { return 7; }
function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
function wp_cache_delete(...$args) {}
function wp_get_current_user() { return (object) array('ID' => 7); }
function get_post($id) { return $GLOBALS['posts'][$id] ?? null; }
function is_multisite() { return false; }
function get_stylesheet() { return 'kurashinoshirube-child'; }
function wp_insert_post($input, $error = false) {
    $id = 101 + count($GLOBALS['posts']);
    $GLOBALS['posts'][$id] = (object) array('ID' => $id, 'post_name' => $input['post_name'], 'post_type' => $input['post_type'], 'post_status' => 'draft');
    $GLOBALS['insert_count']++;
    return $id;
}
function clean_post_cache($id) {}
function wp_slash($value) { return $value; }
class WP_REST_Request extends ArrayObject {
    public function get_json_params() { return $this->getArrayCopy(); }
}
final class RAOS_Codex_MCP_Abilities {
    public static function runtime_identity_gate() { return true; }
    public static function plugin_runtime_revision() { return str_repeat('a', 64); }
    public function owner_direct_permission() { return true; }
}
final class RAOS_Codex_MCP_Store {
    public static function hash($value) { return hash('sha256', self::canonical_json($value)); }
    public static function canonical_json($value) { return json_encode($value); }
    public static function is_sha256($value) { return is_string($value) && preg_match('/^[a-f0-9]{64}$/D', $value) === 1; }
    public static function require_transactional_tables($tables) { return true; }
    public static function get($id) { return $GLOBALS['rows'][$id] ?? new WP_Error('missing'); }
    public static function register_publication_batch(...$args) { $GLOBALS['registered']++; return new WP_Error('stop_after_gate'); }
}
final class RAOS_Codex_MCP_Content {
    public function __construct($plugin) {}
    public static function document($id) {
        $post = get_post($id);
        return $post ? array('id' => $id, 'post_type' => $post->post_type, 'slug' => $post->post_name, 'status' => $post->post_status) : new WP_Error('missing');
    }
}
final class RAOS_Codex_MCP_Deployment {
    public function __construct($plugin) {}
    public static function private_directory() { return sys_get_temp_dir() . '/raos-owner-direct-harness-' . getmypid(); }
    public static function active_theme_tree_sha256() { return str_repeat('b', 64); }
    public function status() { return array('theme' => array('slug' => 'kurashinoshirube-child', 'tree_sha256' => str_repeat('b', 64))); }
}
class FakeDB {
    public $posts = 'wp_posts'; public $options = 'wp_options'; public $postmeta = 'wp_postmeta';
    public $term_relationships = 'wp_term_relationships'; public $term_taxonomy = 'wp_term_taxonomy'; public $terms = 'wp_terms';
    public $last_error = ''; public $fail_commit = false;
    public function prepare($sql, ...$values) { return array($sql, $values); }
    public function get_var($prepared) {
        [$sql, $values] = $prepared;
        if (str_contains($sql, 'option_value')) { return $GLOBALS['options'][$values[0]] ?? null; }
        foreach ($GLOBALS['posts'] as $post) { if ($post->post_name === $values[0]) { return $post->ID; } }
        return null;
    }
    public function query($sql) { if ($sql === 'COMMIT' && $this->fail_commit) { $this->fail_commit = false; return false; } return 1; }
    public function update($table, $data, $where, ...$rest) { $GLOBALS['options'][$where['option_name']] = $data['option_value']; return 1; }
    public function insert($table, $data, ...$rest) { if (isset($GLOBALS['options'][$data['option_name']])) return false; $GLOBALS['options'][$data['option_name']] = $data['option_value']; return 1; }
}
function add_option($name, $value, ...$rest) { if (isset($GLOBALS['options'][$name])) return false; $GLOBALS['options'][$name] = $value; return true; }
function expect_true($value, $message) { if ($value !== true) throw new RuntimeException($message); }
function expect_error($value, $code) { expect_true(is_wp_error($value) && $value->code === $code, 'expected ' . $code . ', got ' . json_encode($value)); }
$GLOBALS['options'] = array(); $GLOBALS['posts'] = array(); $GLOBALS['rows'] = array();
$GLOBALS['insert_count'] = 0; $GLOBALS['registered'] = 0; $GLOBALS['wpdb'] = new FakeDB();
$private = RAOS_Codex_MCP_Deployment::private_directory(); mkdir($private, 0700);
require dirname(__DIR__, 3) . '/changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-owner-direct.php';
$server = new RAOS_Codex_MCP_Owner_Direct(new RAOS_Codex_MCP_Abilities());
expect_true($server->status()['enabled'] === false, 'default must be off');
$input = array('profile' => 'owner-direct-v1', 'article_key' => 'new-article', 'slug' => 'new-article', 'idempotency_key' => str_repeat('c', 64));
expect_error($server->ensure_draft(new WP_REST_Request($input)), 'raos_codex_owner_direct_disabled');
$profile = array('profile' => 'owner-direct-v1', 'enabled' => true, 'publisher_user_id' => 7, 'configured_by' => 1, 'allow_new_posts' => true, 'theme_slug' => 'kurashinoshirube-child', 'targets' => array());
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION] = $profile;
$first = $server->ensure_draft(new WP_REST_Request($input));
expect_true(! is_wp_error($first) && $first['id'] === 101, 'create binds actual id');
$again = $server->ensure_draft(new WP_REST_Request($input));
expect_true($again['id'] === 101 && $GLOBALS['insert_count'] === 1, 'replay must not duplicate draft');
$different = $input; $different['slug'] = 'different';
expect_error($server->ensure_draft(new WP_REST_Request($different)), 'raos_codex_owner_direct_draft_conflict');
$collision = $input; $collision['article_key'] = 'other'; $collision['idempotency_key'] = str_repeat('d', 64);
expect_error($server->ensure_draft(new WP_REST_Request($collision)), 'raos_codex_owner_direct_slug_conflict');
$ambiguous = $input; $ambiguous['article_key'] = 'second'; $ambiguous['slug'] = 'second'; $ambiguous['idempotency_key'] = str_repeat('e', 64);
$GLOBALS['wpdb']->fail_commit = true;
expect_error($server->ensure_draft(new WP_REST_Request($ambiguous)), 'raos_codex_owner_direct_draft_outcome_unknown');
$reconciled = $server->ensure_draft(new WP_REST_Request($ambiguous));
expect_true($reconciled['id'] === 102 && $GLOBALS['insert_count'] === 2, 'ambiguous replay binds committed id');
expect_error($server->document(new WP_REST_Request(array('id' => 999))), 'raos_codex_owner_direct_target_forbidden');
$legacy = array('kind' => 'CONTENT_RELEASE', 'created_by' => 7, 'payload' => array());
expect_error(RAOS_Codex_MCP_Owner_Direct::validate_binding($legacy), 'raos_codex_owner_direct_legacy_forbidden');
$binding = $server->binding('new-article');
$row = array('kind' => 'CONTENT_RELEASE', 'created_by' => 7, 'payload' => array('authorization_profile' => $binding, 'before' => array('id' => 101, 'post_type' => 'post', 'slug' => 'new-article'), 'after' => array('id' => 101, 'post_type' => 'post', 'slug' => 'new-article')));
expect_true(RAOS_Codex_MCP_Owner_Direct::validate_binding($row) === true, 'owned article must authorize');
$wrong = $row; $wrong['payload']['after']['id'] = 999;
expect_error(RAOS_Codex_MCP_Owner_Direct::validate_binding($wrong), 'raos_codex_owner_direct_target_forbidden');
$wrong = $row; $wrong['created_by'] = 8;
expect_error(RAOS_Codex_MCP_Owner_Direct::validate_binding($wrong), 'raos_codex_owner_direct_identity_forbidden');
$wrong = $row; $wrong['kind'] = 'PLUGIN_CHANGE';
expect_error(RAOS_Codex_MCP_Owner_Direct::validate_binding($wrong), 'raos_codex_owner_direct_target_forbidden');
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION]['enabled'] = false;
expect_error(RAOS_Codex_MCP_Owner_Direct::validate_binding($row), 'raos_codex_owner_direct_disabled');
foreach (glob($private . '/*') as $path) { unlink($path); } rmdir($private);
echo "OWNER_DIRECT_BEHAVIOR_OK\n";
