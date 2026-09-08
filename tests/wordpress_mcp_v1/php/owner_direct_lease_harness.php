<?php
/** Exercise actual lease file creation/validation for both authorization profiles. */
declare(strict_types=1);
define('ABSPATH', __DIR__ . '/');
define('WP_CONTENT_DIR', __DIR__);
define('RAOS_OPERATOR_WRITES_ENABLED', true);
define('RAOS_CODEX_PRIVATE_DIR', sys_get_temp_dir() . '/raos-direct-lease-' . getmypid());
mkdir(RAOS_CODEX_PRIVATE_DIR, 0700);
class WP_Error {
    public function __construct(public string $code, $message = '', $data = array()) {}
    public function get_error_code() { return $this->code; }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
function get_current_user_id() { return 7; }
class RAOS_Codex_MCP_Abilities {
    public static function runtime_identity_gate() { return true; }
    public static function plugin_runtime_revision() { return RAOS_Codex_MCP_Store::RUNTIME_REVISION; }
}
function demand($condition, $code) { if ($condition !== true) throw new RuntimeException($code); }
$includes = dirname(__DIR__, 3) . '/changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/';
require $includes . 'class-raos-codex-mcp-store.php';
require $includes . 'class-raos-codex-mcp-deployment.php';
require $includes . 'class-raos-codex-mcp-owner-direct.php';
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION] = array(
    'profile' => 'owner-direct-v1', 'enabled' => true, 'publisher_user_id' => 7, 'configured_by' => 1,
    'allow_new_posts' => false, 'theme_slug' => 'kurashinoshirube-child',
    'targets' => array(array('article_key' => 'existing', 'post_id' => 12, 'post_type' => 'post', 'slug' => 'existing')),
);
$direct = new RAOS_Codex_MCP_Owner_Direct(new RAOS_Codex_MCP_Abilities());
$identity = array('id' => 12, 'post_type' => 'post', 'slug' => 'existing');
$row = array('proposal_id' => str_repeat('a', 64), 'kind' => 'CONTENT_RELEASE', 'created_by' => 7,
    'state' => 'APPROVED', 'approved_by' => 7, 'approved_at_gmt' => gmdate('Y-m-d H:i:s'),
    'expires_at_gmt' => gmdate('Y-m-d H:i:s', time() + 900), 'before_sha256' => str_repeat('b', 64), 'after_sha256' => str_repeat('c', 64),
    'payload' => array('authorization_profile' => $direct->binding('existing'), 'before' => $identity, 'after' => $identity));
$lease = RAOS_Codex_MCP_Deployment::create_approval_lease($row, 7, $row['approved_at_gmt']);
demand(is_array($lease) && $lease['schema'] === 'RAOS_CODEX_OWNER_DIRECT_LEASE_V1', 'DIRECT_LEASE_SCHEMA_REQUIRED');
demand(RAOS_Codex_MCP_Deployment::validate_approval_lease($row) === true, 'DIRECT_LEASE_REJECTED');
$legacy = $row; unset($legacy['payload']['authorization_profile']);
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($legacy)), 'DIRECT_LEASE_PROMOTED_TO_LEGACY');
$wrong = $row; $wrong['after_sha256'] = str_repeat('d', 64);
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($wrong)), 'DRIFT_ACCEPTED');
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION]['enabled'] = false;
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($row)), 'REVOKED_LEASE_ACCEPTED');
$GLOBALS['options'][RAOS_Codex_MCP_Owner_Direct::PROFILE_OPTION]['enabled'] = true;
RAOS_Codex_MCP_Deployment::remove_approval_lease($row['proposal_id']);
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($row)), 'CONSUMED_LEASE_ACCEPTED');
$expired = $row; $expired['expires_at_gmt'] = gmdate('Y-m-d H:i:s', time() - 1);
RAOS_Codex_MCP_Deployment::create_approval_lease($expired, 7, $row['approved_at_gmt']);
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($expired, true)), 'EXPIRED_LEASE_ACCEPTED');
RAOS_Codex_MCP_Deployment::remove_approval_lease($row['proposal_id']);
demand(is_wp_error(RAOS_Codex_MCP_Deployment::create_approval_lease($legacy, 7, $row['approved_at_gmt'])), 'LEGACY_SELF_APPROVAL_ACCEPTED');
$legacy['approved_by'] = 1;
$legacy_lease = RAOS_Codex_MCP_Deployment::create_approval_lease($legacy, 1, $row['approved_at_gmt']);
demand(is_array($legacy_lease) && $legacy_lease['schema'] === 'RAOS_CODEX_APPROVAL_LEASE_V1', 'LEGACY_LEASE_CHANGED');
demand(RAOS_Codex_MCP_Deployment::validate_approval_lease($legacy) === true, 'LEGACY_LEASE_REJECTED');
demand(is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($row)), 'LEGACY_LEASE_PROMOTED_TO_DIRECT');
RAOS_Codex_MCP_Deployment::remove_approval_lease($row['proposal_id']);
rmdir(RAOS_CODEX_PRIVATE_DIR);
echo "OWNER_DIRECT_LEASE_BEHAVIOR_OK\n";
