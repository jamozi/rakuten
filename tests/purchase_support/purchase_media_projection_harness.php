<?php
$fixture = json_decode(base64_decode($argv[3]), true);
$fixture['runtime'] = file_get_contents(dirname(dirname($argv[1])) . '/assets/purchase-support.v1.json');
$mode = $argv[2] ?? 'valid';
$fixture['theme'] = sys_get_temp_dir() . '/purchase-media-' . uniqid();
mkdir($fixture['theme'] . '/assets', 0700, true);
file_put_contents($fixture['theme'] . '/assets/purchase-support.v1.json', $fixture['runtime']);
$runtime_path = $fixture['theme'] . '/assets/purchase-support.v1.json';
define('KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256', hash_file('sha256', $runtime_path));
if ($mode === 'runtime-tamper') { file_put_contents($runtime_path, "\n", FILE_APPEND); }
function is_admin() { return false; }
function is_feed() { return false; }
function is_singular($types) { return true; }
function get_queried_object_id() { return 41; }
function get_post_status($id) { return 'publish'; }
function get_stylesheet_directory() { global $fixture; return $fixture['theme']; }
function get_post_field($field, $id, $context = null) {
    global $fixture, $mode;
    $fields = array('post_name' => 'slug', 'post_title' => 'title', 'post_excerpt' => 'excerpt', 'post_content' => 'block_markup', 'post_type' => 'post_type');
    if ($field === 'post_password') { return ''; }
    $value = $fixture['snapshot'][$fields[$field]];
    if ($mode === 'body-tamper' && $field === 'post_content') { $value .= '<p>drift</p>'; }
    return $value;
}
class RAOS_Codex_MCP_Owner_Direct {
    static function public_article_snapshot($id) {
        global $fixture, $mode;
        return $mode === 'no-snapshot' ? null : $fixture['snapshot'];
    }
}
function add_filter(...$args) {}
function add_action(...$args) {}
require $argv[1];
$raw = $fixture['snapshot']['block_markup'];
$actual = kurashinoshirube_purchase_support_media($raw);
echo json_encode(array('unchanged' => $raw === $actual, 'sha256' => hash('sha256', $actual),
    'figures' => substr_count($actual, '<figure class="ps-product-image '),
    'unknown_unchanged' => kurashinoshirube_purchase_support_media('<div class="ps-product-media" data-ps-media-product="PRD-UNKNOWN"></div>') === '<div class="ps-product-media" data-ps-media-product="PRD-UNKNOWN"></div>'));
