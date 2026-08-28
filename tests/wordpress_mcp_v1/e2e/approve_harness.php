<?php
/**
 * Exercise the real wp-admin approval handler in a disposable E2E site.
 *
 * The runtime-only password belongs to the destroyed test administrator. No
 * production credential or alternate approval endpoint is accepted here.
 */

defined('ABSPATH') || exit;

if (! isset($args) || ! is_array($args) || 1 !== count($args)) {
    fwrite(STDERR, "RAOS_E2E_APPROVAL_ARGUMENT_INVALID\n");
    exit(64);
}

$proposal_id = (string) $args[0];
$administrator = get_user_by('login', 'raos-e2e-approver');
$row = RAOS_Codex_MCP_Store::get($proposal_id);
$password = getenv('RAOS_WORDPRESS_E2E_ADMIN_PASSWORD');
if (! $administrator instanceof WP_User
    || is_wp_error($row)
    || ! is_string($password)
    || strlen($password) < 32) {
    fwrite(STDERR, "RAOS_E2E_APPROVAL_TARGET_INVALID\n");
    exit(65);
}

wp_set_current_user($administrator->ID);
$_SERVER['REQUEST_METHOD'] = 'POST';
$_POST = array(
    'action' => 'raos_codex_mcp_approve',
    'proposal_id' => $proposal_id,
    '_wpnonce' => wp_create_nonce('raos_codex_mcp_approve_' . $proposal_id),
    'current_password' => $password,
    'reason' => 'Disposable E2E approval after verifying the complete hashes.',
    'hash_suffix' => substr($row['after_sha256'], -8),
);

RAOS_Codex_MCP_Abilities::instance()->handle_approval();
