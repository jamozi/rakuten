"""The real theme exposes metadata only for the saved direct publication snapshot."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def test_new_direct_article_has_exact_head_and_changed_snapshot_is_hidden():
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP runtime unavailable")
    program = r"""
define('OBJECT', 'OBJECT');
class WP_Post extends stdClass {}
function add_action(...$args) {}
function add_filter(...$args) {}
function add_shortcode(...$args) {}
function is_front_page() { return false; }
function is_singular($type) { return $type === 'post'; }
function get_stylesheet_directory() { return $GLOBALS['theme']; }
function get_option($name, $default = false) { return $default; }
function get_queried_object_id() { return 501; }
function get_post($id) { return $GLOBALS['post']; }
function get_post_field($field, $id, $context = 'raw') { return $GLOBALS['post']->$field ?? null; }
function get_post_type($id) { return 'post'; }
function get_post_status($id) { return 'publish'; }
function get_post_meta($id, $key, $single = false) { return ''; }
function wp_strip_all_tags($text) { return strip_tags($text); }
function wp_json_encode($value, $flags = 0) { return json_encode($value, $flags); }
class RAOS_Codex_MCP_Owner_Direct {
    public static function public_article_snapshot($id) { return $GLOBALS['snapshot']; }
    public static function is_direct_article($id) { return true; }
}
$GLOBALS['theme'] = $argv[1];
$GLOBALS['post'] = (object)array('ID'=>501,'post_type'=>'post','post_status'=>'publish',
    'post_name'=>'new-guide','post_title'=>'新しく作成した比較ガイド',
    'post_excerpt'=>'購入前の確認事項をまとめた新しいガイドです。', 'post_content'=>'<p>本文</p>', 'post_password'=>'');
$GLOBALS['snapshot'] = array('id'=>501,'post_type'=>'post','slug'=>'new-guide',
    'title'=>$GLOBALS['post']->post_title,'excerpt'=>$GLOBALS['post']->post_excerpt,
    'block_markup'=>'<p>本文</p>','content_sha256'=>hash('sha256','<p>本文</p>'));
require $argv[1] . '/functions.php';
$valid = kurashinoshirube_public_head_context();
$GLOBALS['snapshot'] = null;
$invalid = kurashinoshirube_public_head_context();
echo json_encode(array('valid'=>$valid,'invalid'=>$invalid), JSON_UNESCAPED_UNICODE);
"""
    result = subprocess.run(
        [php, "-r", program, str(THEME)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["valid"] == {
        "canonical_url": "https://kurashinoshirube.com/new-guide/",
        "title": "新しく作成した比較ガイド",
        "description": "購入前の確認事項をまとめた新しいガイドです。",
        "kind": "article",
        "section": "記事",
    }
    assert value["invalid"] is None
