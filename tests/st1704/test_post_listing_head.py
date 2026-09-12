"""Exercise the real PHP listing head resolver with bounded query contexts."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php"
)


def php_program():
    source = THEME.read_text()
    body = source.split("function kurashinoshirube_post_listing_head_context", 1)[
        1
    ].split("/**", 1)[0]
    return (
        """<?php
class WP_Query {
 public array $values;
 function __construct($v) { $this->values=$v; }
 function is_home() { return $this->values['home'] ?? true; }
 function is_search() { return $this->values['search'] ?? false; }
 function is_404() { return $this->values['404'] ?? false; }
 function get($key) { return $this->values[$key] ?? ''; }
}
function kurashinoshirube_post_listing_head_context"""
        + body
        + """
$cases = [
 'first'=>['post_type'=>'post','paged'=>0],
 'second'=>['post_type'=>'post','paged'=>'2'],
 'tracking'=>['post_type'=>'post','paged'=>2,'audit_probe'=>'other'],
 'search'=>['post_type'=>'post','paged'=>2,'search'=>true],
 'missing'=>['post_type'=>'post','paged'=>2,'404'=>true],
 'article'=>['post_type'=>'post','home'=>false],
 'page'=>['post_type'=>'page','paged'=>0],
 'array-type'=>['post_type'=>['post'],'paged'=>0],
 'negative'=>['post_type'=>'post','paged'=>-2],
 'invalid'=>['post_type'=>'post','paged'=>'2/elsewhere'],
 'array-page'=>['post_type'=>'post','paged'=>[2]],
];
$result=[];
foreach(['public'=>'https://kurashinoshirube.com','local'=>'http://127.0.0.1:48142'] as $env=>$origin) {
 foreach($cases as $key=>$values) {
  $GLOBALS['wp_query']=new WP_Query($values);
  $result[$env][$key]=kurashinoshirube_post_listing_head_context($origin);
 }
}
unset($GLOBALS['wp_query']);
$result['absent']=kurashinoshirube_post_listing_head_context('https://kurashinoshirube.com');
echo json_encode($result,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
"""
    )


def verify(result):
    assert result["absent"] is None
    for env, origin in [
        ("public", "https://kurashinoshirube.com"),
        ("local", "http://127.0.0.1:48142"),
    ]:
        cases = result[env]
        assert cases["first"]["canonical_url"] == origin + "/?post_type=post"
        assert cases["second"]["canonical_url"] == origin + "/page/2/?post_type=post"
        assert cases["tracking"] == cases["second"]
        assert cases["second"]["title"] == "記事一覧（2ページ目）｜暮らしのしるべ"
        assert cases["first"]["kind"] == "article_listing"
        assert all(
            v is None
            for k, v in cases.items()
            if k not in ["first", "second", "tracking"]
        )


def test_post_listing_head_boundaries():
    php = shutil.which("php")
    if php is None:
        pytest.skip("PHP is required for the real theme resolver")
    result = subprocess.run(
        [php, "-r", php_program().removeprefix("<?php")],
        text=True,
        capture_output=True,
        check=True,
    )
    verify(json.loads(result.stdout))
