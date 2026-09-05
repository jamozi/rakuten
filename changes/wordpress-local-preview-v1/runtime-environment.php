<?php
/** Read-only public runtime identity. No options, users or credentials are exported. */
if (PHP_SAPI !== 'cli') {
    exit(69);
}
require_once '/var/www/html/wp-load.php';
if (!defined('RAOS_LOCAL_PREVIEW') || RAOS_LOCAL_PREVIEW !== true
    || wp_get_environment_type() !== 'local'
    || !preg_match('~^http://127\.0\.0\.1:[0-9]{4,5}$~D', (string) get_option('home'))) {
    exit(69);
}
global $wp_version;
$theme = wp_get_theme();
$parent = $theme->parent();
$root = get_stylesheet_directory();
$files = array();
$iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
foreach ($iterator as $file) {
    if ($file->isLink() || !$file->isFile() || count($files) >= 2000) {
        exit(69);
    }
    $relative = substr($file->getPathname(), strlen($root) + 1);
    $checksum = hash_file('sha256', $file->getPathname());
    if ($checksum === false) {
        exit(69);
    }
    // Same canonical projection as the production deployment bridge.
    $files[$relative] = array('path' => $relative, 'sha256' => $checksum, 'size' => $file->getSize());
}
ksort($files, SORT_STRING);
$projection = wp_json_encode(array_values($files), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
echo wp_json_encode(array(
    'schema' => 'RAOS_WORDPRESS_LOCAL_ENVIRONMENT_V1',
    'wordpress_version' => (string) $wp_version,
    'php_version' => PHP_VERSION,
    'theme' => array(
        'slug' => get_stylesheet(),
        'version' => $theme->get('Version'),
        'tree_sha256' => hash('sha256', $projection),
        'parent_slug' => get_template(),
        'parent_version' => $parent ? $parent->get('Version') : null,
    ),
    'yoast' => array(
        'version' => defined('WPSEO_VERSION') ? WPSEO_VERSION : null,
        'active' => defined('WPSEO_VERSION'),
        'settings_exact' => function_exists('kurashinoshirube_yoast_configuration_is_exact')
            && kurashinoshirube_yoast_configuration_is_exact(),
    ),
    'measurement' => array('plugin_active' => defined('RAOS_EDITORIAL_MEASUREMENT_VERSION')),
    'script_debug' => defined('SCRIPT_DEBUG') && SCRIPT_DEBUG,
), JSON_UNESCAPED_SLASHES) . "\n";
