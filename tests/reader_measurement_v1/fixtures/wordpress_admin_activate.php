<?php
/** Real WordPress activation boundary for a disposable, isolated test site. */

if (PHP_SAPI !== 'cli') {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ACTIVATION_CLI_ONLY\n");
    exit(64);
}

$admin_id = getenv('RAOS_READER_TEST_ADMIN_ID');
if (! is_string($admin_id) || preg_match('/\A[1-9][0-9]*\z/D', $admin_id) !== 1) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ADMIN_ID_INVALID\n");
    exit(64);
}

define('WP_ADMIN', true);
$_SERVER['HTTP_HOST'] = 'kurashinoshirube.com';
$_SERVER['HTTPS'] = 'on';
$_SERVER['REQUEST_METHOD'] = 'GET';

require '/var/www/html/wp-load.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';

$plugin = 'raos-reader-measurement/raos-reader-measurement.php';
wp_set_current_user((int) $admin_id);
if (! current_user_can('activate_plugins') || is_plugin_active($plugin)) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ACTIVATION_PRECONDITION_FAILED\n");
    exit(65);
}

$nonce = wp_create_nonce('activate-plugin_' . $plugin);
if (! is_string($nonce) || wp_verify_nonce($nonce, 'activate-plugin_' . $plugin) === false) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ACTIVATION_NONCE_FAILED\n");
    exit(66);
}
$_REQUEST['_wpnonce'] = $nonce;

$result = activate_plugin($plugin, '', false, false);
if (is_wp_error($result) || ! is_plugin_active($plugin)) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ACTIVATION_FAILED\n");
    exit(67);
}

$state = get_option('raos_reader_measurement_state_v1', null);
if ($state !== array('enabled' => false, 'approval' => null)) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_ACTIVATION_NOT_OFF\n");
    exit(68);
}

echo 'RAOS_READER_WORDPRESS_ACTIVATION_JSON=' . wp_json_encode(array(
    'method' => 'wordpress_core_activate_plugin_with_real_nonce',
    'test_only_admin' => true,
    'nonce_verified' => true,
    'plugin_active' => true,
    'collection_enabled' => false,
    'approval' => null,
), JSON_UNESCAPED_SLASHES) . "\n";
