"""Run the real ST-1704 theme PHP with a small WordPress stub layer (no WordPress needed)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
ORIGIN = "https://kurashinoshirube.com"

# Stubs shared by every harness. They model only the WordPress calls the theme
# makes while resolving public head data, hub pages and render-time filters.
STUBS = r"""
define('OBJECT', 'OBJECT');
class WP_Post extends stdClass {}
class WP_Error {
    public $code; public $message; public $data;
    function __construct($code = '', $message = '', $data = null) { $this->code = $code; $this->message = $message; $this->data = $data; }
}
class WP_HTML_Tag_Processor {
    private $html; private $attrs = array(); private $tag = null; private $start = 0; private $end = 0;
    function __construct($html) { $this->html = $html; }
    function next_tag($query = null) {
        $name = is_array($query) ? ($query['tag_name'] ?? null) : $query;
        $class = is_array($query) ? ($query['class_name'] ?? null) : null;
        $offset = $this->end;
        while (preg_match('/<([a-zA-Z][a-zA-Z0-9-]*)\b([^>]*)>/s', $this->html, $m, PREG_OFFSET_CAPTURE, $offset) === 1) {
            $offset = $m[0][1] + strlen($m[0][0]);
            if ($name !== null && strtoupper($m[1][0]) !== strtoupper($name)) { continue; }
            $attrs = array();
            if (preg_match_all('/\s([a-zA-Z_:][a-zA-Z0-9_:.-]*)(?:="([^"]*)")?/', $m[2][0], $am, PREG_SET_ORDER)) {
                foreach ($am as $a) { $attrs[strtolower($a[1])] = $a[2] ?? true; }
            }
            if ($class !== null && ! in_array($class, preg_split('/\s+/', (string) ($attrs['class'] ?? '')), true)) { continue; }
            $this->tag = $m[1][0]; $this->attrs = $attrs; $this->start = $m[0][1]; $this->end = $offset;
            return true;
        }
        return false;
    }
    function get_attribute($name) { $name = strtolower($name); return array_key_exists($name, $this->attrs) ? $this->attrs[$name] : null; }
    function set_attribute($name, $value) { $this->attrs[strtolower($name)] = (string) $value; $this->render(); }
    private function render() {
        $parts = array();
        foreach ($this->attrs as $k => $v) { $parts[] = $v === true ? $k : $k . '="' . htmlspecialchars((string) $v, ENT_QUOTES, 'UTF-8') . '"'; }
        $tag = '<' . $this->tag . ($parts ? ' ' . implode(' ', $parts) : '') . '>';
        $this->html = substr($this->html, 0, $this->start) . $tag . substr($this->html, $this->end);
        $this->end = $this->start + strlen($tag);
    }
    function get_updated_html() { return $this->html; }
}
$GLOBALS['raos_state'] = array('front' => false, 'singular' => null, 'search' => false, 'archive' => false, '404' => false,
    'in_loop' => true, 'main_query' => true, 'feed' => false, 'admin' => false, 'logged_in' => false, 'caps' => array(),
    'search_query' => '', 'author' => false, 'category' => false, 'tag' => false, 'date' => false, 'ssl' => true);
function raos_state($key) { return $GLOBALS['raos_state'][$key] ?? null; }
function add_action(...$args) { $GLOBALS['raos_hooks'][] = array('action', $args[0], $args[1]); }
function add_filter(...$args) { $GLOBALS['raos_hooks'][] = array('filter', $args[0], $args[1]); }
function remove_action(...$args) { $GLOBALS['raos_removed'][] = $args; }
function remove_filter(...$args) {}
function add_shortcode(...$args) { $GLOBALS['raos_shortcodes'][$args[0]] = $args[1]; }
function is_front_page() { return raos_state('front'); }
function is_singular($type = null) {
    $current = raos_state('singular');
    if ($current === null) { return false; }
    if ($type === null) { return true; }
    return in_array($current, (array) $type, true);
}
function is_search() { return raos_state('search'); }
function is_archive() { return raos_state('archive'); }
function is_404() { return raos_state('404'); }
function is_category() { return raos_state('category'); }
function is_tag() { return raos_state('tag'); }
function is_author() { return raos_state('author'); }
function is_date() { return raos_state('date'); }
function is_post_type_archive() { return false; }
function is_attachment() { return false; }
function is_admin() { return raos_state('admin'); }
function is_feed() { return raos_state('feed'); }
function is_ssl() { return raos_state('ssl'); }
function in_the_loop() { return raos_state('in_loop'); }
function is_main_query() { return raos_state('main_query'); }
function is_user_logged_in() { return raos_state('logged_in'); }
function current_user_can($cap) { return in_array($cap, raos_state('caps'), true); }
function rest_authorization_required_code() { return raos_state('logged_in') ? 403 : 401; }
function get_search_query($escaped = true) { return raos_state('search_query'); }
function get_stylesheet_directory() { return $GLOBALS['theme']; }
function get_stylesheet_directory_uri() { return 'https://kurashinoshirube.com/wp-content/themes/kurashinoshirube-child'; }
function get_stylesheet() { return 'kurashinoshirube-child'; }
function get_option($name, $default = false) { return $GLOBALS['raos_options'][$name] ?? $default; }
function home_url($path = '') { return 'https://kurashinoshirube.com' . $path; }
function untrailingslashit($value) { return rtrim($value, '/'); }
function trailingslashit($value) { return rtrim($value, '/') . '/'; }
function wp_parse_url($url) { return parse_url($url); }
function esc_url($url) { return $url; }
function esc_attr($value) { return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8'); }
function esc_html($value) { return htmlspecialchars((string) $value, ENT_QUOTES, 'UTF-8'); }
function has_site_icon() { return false; }
function wp_strip_all_tags($text) { return trim(strip_tags($text)); }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
function get_queried_object_id() { return $GLOBALS['page']->ID; }
function get_the_ID() { return $GLOBALS['page']->ID; }
function get_post($id = null) {
    if ($id instanceof WP_Post) { return $id; }
    if ($id === null || $id === $GLOBALS['page']->ID) { return $GLOBALS['page']; }
    foreach ($GLOBALS['pages'] ?? array() as $page) { if ($page->ID === $id) { return $page; } }
    return null;
}
function get_post_field($field, $id, $context = 'raw') {
    $post = get_post($id); return $post === null ? null : ($post->$field ?? null);
}
function get_post_type($id) { return get_post_field('post_type', $id); }
function get_post_status($id) { return get_post_field('post_status', $id); }
function get_post_meta($id, $key, $single = false) { return ''; }
function get_page_by_path($slug, $output = OBJECT, $type = 'page') {
    $post = $GLOBALS['page'];
    if ($post->post_name === $slug && $post->post_type === $type) { return $post; }
    $candidate = $GLOBALS['pages'][$slug] ?? null;
    return $candidate instanceof WP_Post && $candidate->post_type === $type ? $candidate : null;
}
function get_permalink($post) { return 'https://kurashinoshirube.com/' . get_post($post)->post_name . '/'; }
function get_post_time($format, $gmt = false, $post = null) { return '2026-09-09T00:00:00Z'; }
function get_post_modified_time($format, $gmt = false, $post = null) { return '2026-09-12T00:00:00Z'; }
$GLOBALS['theme'] = $argv[1];
$GLOBALS['pages'] = array();
"""


def run_theme_php(program: str, *extra_args: str, timeout: int = 60) -> dict[str, object]:
    """Run ``program`` after the stubs and the theme; return its JSON stdout."""

    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP is required for the theme behavior harness")
    source = STUBS + "\nrequire $argv[1] . '/functions.php';\n" + program
    result = subprocess.run(
        [php, "-r", source, str(THEME), *extra_args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stderr == "", result.stderr
    return json.loads(result.stdout)
