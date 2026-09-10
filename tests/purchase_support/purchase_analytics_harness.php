<?php
function is_user_logged_in() { global $argv; return $argv[2] === 'owner'; }
if ($argv[2] !== 'off') { define('RAOS_PURCHASE_GA4_ENABLED', true); }
require $argv[1];
$binding = array('article_id'=>'article', 'product_id'=>'product', 'seller_id'=>'seller', 'offer_id'=>'offer', 'cta_id'=>'cta', 'placement'=>'top_summary', 'snapshot_id'=>'snapshot', 'href'=>'https://seller.example/item');
$result = kurashinoshirube_purchase_ga4_configuration(array($binding));
if ((in_array($argv[2], array('on', 'tampered'), true)) !== ($result !== null)) { exit(1); }
if ($result !== null && $result['debug_mode'] !== false) { exit(2); }
$article = array('article_id'=>'dishwasher-running-cost', 'snapshot_id'=>'ps-' . str_repeat('a',32));
$guide = kurashinoshirube_purchase_ga4_configuration(array(), $article);
if (in_array($argv[2], array('on','tampered'), true)) {
    if ($guide === null || $guide['bindings'] !== array() || $guide['article'] !== $article) { exit(11); }
} elseif ($guide !== null) { exit(12); }
if (kurashinoshirube_purchase_ga4_configuration(array()) !== null
    || kurashinoshirube_purchase_ga4_configuration(array($binding), $article) !== null
    || kurashinoshirube_purchase_ga4_configuration(array(), array('article_id'=>'guide')) !== null) { exit(13); }
$binding['extra'] = 'disallowed';
if (kurashinoshirube_purchase_ga4_configuration(array($binding)) !== null) { exit(3); }
echo "PURCHASE_PHP_" . strtoupper($argv[2]) . "_OK\n";

$hooks = array();
function add_action($name, $callback, $priority = 10) { global $hooks; $hooks[$name][$priority][] = $callback; }
$filters = array();
function add_filter($name, $callback, ...$args) { global $filters; $filters[$name][] = $callback; }
function wp_json_encode($value, $flags) { return json_encode($value, $flags); }
$enqueued = array();
function wp_enqueue_script(...$args) { global $enqueued; $enqueued[] = $args; }
define('KURASHINOSHIRUBE_PURCHASE_ANALYTICS_SHA256', hash('sha256', 'approved asset'));
$verified = array();
function kurashinoshirube_verified_asset_uri($path, $hash, $required) {
    global $argv, $verified;
    $verified[] = array($path, $hash, $required);
    if ($path !== 'assets/purchase-analytics.js' || $hash !== KURASHINOSHIRUBE_PURCHASE_ANALYTICS_SHA256 || $required !== true) { exit(6); }
    $bytes = $argv[2] === 'tampered' ? 'changed asset' : 'approved asset';
    return hash('sha256', $bytes) === $hash ? 'https://preview.example/verified.js' : null;
}
function get_stylesheet_directory_uri() { return 'https://preview.example/theme'; }
define('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION', 'test');
unset($binding['extra']);
add_action('wp_head', static function () use ($binding) { kurashinoshirube_purchase_ga4_enqueue(array($binding)); }, 1);
add_action('wp_head', static function () { echo '<script id="head-scripts"></script>'; }, 9);
ob_start();
// WordPress runs enqueue at head priority 1; callbacks added at 2 run in this head.
for ($priority = 0; $priority <= 10; $priority++) {
    foreach ($hooks['wp_head'][$priority] ?? array() as $callback) { $callback(); }
}
$output = ob_get_clean();
$config_position = strpos($output, 'raos-purchase-ga4-config');
if ($argv[2] === 'on' && ($config_position === false || $config_position > strpos($output, 'head-scripts'))) { exit(4); }
if ($argv[2] !== 'on' && $config_position !== false) { exit(5); }
echo "PURCHASE_HEAD_ORDER_OK\n";

$tag = '<script data-raos-consent-gate="statistics"></script>';
foreach ($filters['script_loader_tag'] ?? array() as $filter) { $tag = $filter($tag, 'google_gtagjs'); }
if (strpos($tag, 'data-raos-analytics-profile="purchase-support-v1"') === false) { exit(7); }
if (in_array($argv[2], array('on', 'tampered'), true) && count($verified) !== 1) { exit(8); }
if ($argv[2] === 'on' && (count($enqueued) !== 1 || $enqueued[0][1] !== 'https://preview.example/verified.js')) { exit(9); }
if ($argv[2] !== 'on' && count($enqueued) !== 0) { exit(10); }
echo "PURCHASE_ASSET_INTEGRITY_OK\n";
