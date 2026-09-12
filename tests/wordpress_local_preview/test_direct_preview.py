"""Minimal publication preview binds real inputs and never expands to a full audit."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import pytest


def fixture(tmp_path: Path):
    body = "<!-- wp:paragraph --><p>テスト用の記事です。</p><!-- /wp:paragraph -->"
    source = "content/wordpress/example.html"
    frozen = tmp_path / "sources" / source
    frozen.parent.mkdir(parents=True, exist_ok=True)
    frozen.write_text(body)
    return {
        "schema": "RAOSOwnerDirectCandidateV1",
        "profile": "owner-direct-v1",
        "candidate_id": "a" * 64,
        "source_sha256": "b" * 64,
        "sources": {source: hashlib.sha256(body.encode()).hexdigest()},
        "articles": [
            {
                "article_key": "example",
                "body_source": source,
                "body_file": "sources/" + source,
                "document": {
                    "post_type": "post",
                    "slug": "example",
                    "title": "テスト用の記事",
                    "excerpt": "テスト用の説明です。",
                    "block_markup": body,
                    "taxonomies": {},
                    "media_ids": [],
                },
            }
        ],
        "theme": None,
    }


def owner():
    from scripts import raos_wordpress_direct_preview

    return raos_wordpress_direct_preview


def test_product_image_mirror_is_exact_offline_and_detects_tampering(tmp_path):
    candidate = fixture(tmp_path)
    url = "https://thumbnail.image.rakuten.co.jp/synthetic.jpg"
    candidate["articles"][0]["document"]["block_markup"] = (
        f'<img src="{url}" data-raos-product-image-state="verified">'
    )
    calls = []

    def fetch(value):
        calls.append(value)
        return b"synthetic-image", "image/jpeg"

    result = owner().product_image_mirror(candidate, tmp_path, fetch=fetch)
    assert calls == [url]
    assert owner().product_image_mirror(candidate, tmp_path) == result
    (tmp_path / result[url]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="IMAGE_CHANGED"):
        owner().product_image_mirror(candidate, tmp_path)


def test_product_image_mirror_does_not_fetch_other_hosts_or_unverified_images(tmp_path):
    candidate = fixture(tmp_path)
    candidate["articles"][0]["document"]["block_markup"] = (
        '<img src="https://other.invalid/a.jpg" data-raos-product-image-state="verified">'
        '<img src="https://thumbnail.image.rakuten.co.jp/unverified.jpg">'
    )
    assert (
        owner().product_image_mirror(
            candidate, tmp_path, fetch=lambda _: pytest.fail("unexpected fetch")
        )
        == {}
    )


def test_registered_editorial_image_is_pinned_without_changing_public_url(
    tmp_path, monkeypatch
):
    candidate = fixture(tmp_path)
    url = "https://kurashinoshirube.com/wp-content/uploads/2026/09/kitchen.webp"
    payload = b"synthetic-owned-editorial-image"
    registry = tmp_path / "editorial-images.json"
    registry.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "url": url,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "purpose": "editorial_illustration",
                        "product_evidence": False,
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(owner(), "EDITORIAL_VISUALS", registry, raising=False)
    body = f'<figure><img src="{url}"><figcaption>AI image</figcaption></figure>'
    candidate["articles"][0]["document"]["block_markup"] = body
    result = owner().product_image_mirror(
        candidate, tmp_path, fetch=lambda _: (payload, "image/webp")
    )
    assert set(result) == {url}
    assert candidate["articles"][0]["document"]["block_markup"] == body
    assert owner().product_image_mirror(candidate, tmp_path) == result
    registry.write_text(
        registry.read_text().replace(hashlib.sha256(payload).hexdigest(), "f" * 64)
    )
    with pytest.raises(ValueError, match="EDITORIAL_IMAGE_CHANGED"):
        owner().product_image_mirror(candidate, tmp_path)


def test_editorial_image_registry_cannot_allow_other_hosts_or_changed_bytes(
    tmp_path, monkeypatch
):
    candidate = fixture(tmp_path)
    url = "https://kurashinoshirube.com/wp-content/uploads/2026/09/kitchen.webp"
    registry = tmp_path / "editorial-images.json"
    row = {
        "url": url,
        "sha256": "a" * 64,
        "purpose": "editorial_illustration",
        "product_evidence": False,
    }
    registry.write_text(json.dumps({"assets": [row]}))
    monkeypatch.setattr(owner(), "EDITORIAL_VISUALS", registry, raising=False)
    candidate["articles"][0]["document"]["block_markup"] = f'<img src="{url}">'
    with pytest.raises(ValueError, match="EDITORIAL_IMAGE_CHANGED"):
        owner().product_image_mirror(
            candidate, tmp_path, fetch=lambda _: (b"changed", "image/webp")
        )
    row["url"] = "https://other.invalid/image.webp"
    registry.write_text(json.dumps({"assets": [row]}))
    with pytest.raises(ValueError, match="EDITORIAL_IMAGE_REGISTRY_INVALID"):
        owner().product_image_mirror(
            candidate, tmp_path, fetch=lambda _: pytest.fail("unexpected fetch")
        )


@pytest.mark.parametrize(
    "image_host",
    ["thumbnail.image.rakuten.co.jp", "image.rakuten.co.jp", "other.invalid"],
)
def test_frozen_affiliate_images_are_bounded_and_mirrored_without_html_changes(
    tmp_path, image_host
):
    candidate = fixture(tmp_path)
    candidate["theme"] = {"directory": "theme"}
    assets = tmp_path / "theme/assets"
    assets.mkdir(parents=True)
    underlying = f"https://{image_host}/synthetic.jpg?_ex=300x300"
    url = "https://hbb.afl.rakuten.co.jp/hgb/synthetic/?s=300x300&pc=" + quote(
        underlying, safe=""
    )
    source = f'<a href="https://hb.afl.rakuten.co.jp/hgc/synthetic/"><img src="{url}" alt=""></a>'
    media = [
        {"slugs": ["example"], "sources": {"300": source}},
        {
            "slugs": ["unselected"],
            "sources": {"300": '<img src="https://other.invalid/ignored.jpg">'},
        },
    ]
    path = assets / "rakuten-product-media.json"
    path.write_text(json.dumps(media))
    calls = []

    def fetch(value):
        calls.append(value)
        return b"synthetic-image", "image/jpeg"

    if image_host == "other.invalid":
        with pytest.raises(ValueError, match="AFFILIATE_IMAGE_INVALID"):
            owner().product_image_mirror(candidate, tmp_path, fetch=fetch)
        assert calls == []
    else:
        result = owner().product_image_mirror(candidate, tmp_path, fetch=fetch)
        assert calls == [url]
        assert owner().product_image_mirror(candidate, tmp_path) == result
        assert json.loads(path.read_text())[0]["sources"]["300"] == source


def test_content_preview_checks_only_selected_articles_at_two_widths(tmp_path):
    candidate = fixture(tmp_path)
    planned = owner().preview_plan(candidate, tmp_path)
    assert planned["widths"] == [390, 1440]
    assert [(r["kind"], r["path"]) for r in planned["surfaces"]] == [
        ("article", "/example/")
    ]


def test_theme_preview_adds_home_and_listing_with_one_article(tmp_path):
    candidate = fixture(tmp_path)
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "style.css").write_text("/* Theme Name: fixture */")
    candidate["theme"] = {"directory": "theme"}
    planned = owner().preview_plan(candidate, tmp_path)
    assert [(r["kind"], r["path"]) for r in planned["surfaces"]] == [
        ("article", "/example/"),
        ("home", "/"),
        ("listing", "/?post_type=post"),
    ]


def test_frozen_body_changes_and_markup_substitution_are_refused(tmp_path):
    candidate = fixture(tmp_path)
    altered = deepcopy(candidate)
    altered["articles"][0]["document"]["block_markup"] = "<p>別の本文</p>"
    with pytest.raises(ValueError, match="BODY"):
        owner().preview_plan(altered, tmp_path)
    (tmp_path / candidate["articles"][0]["body_file"]).write_text("changed")
    with pytest.raises(ValueError, match="BODY"):
        owner().preview_plan(candidate, tmp_path)


def test_body_path_cannot_escape_snapshot_or_use_symlink(tmp_path):
    candidate = fixture(tmp_path)
    candidate["articles"][0]["body_file"] = "../outside.html"
    with pytest.raises(ValueError, match="PATH"):
        owner().preview_plan(candidate, tmp_path)
    candidate = fixture(tmp_path)
    frozen = tmp_path / candidate["articles"][0]["body_file"]
    target = tmp_path / "outside.html"
    target.write_bytes(frozen.read_bytes())
    frozen.unlink()
    frozen.symlink_to(target)
    with pytest.raises(ValueError, match="PATH"):
        owner().preview_plan(candidate, tmp_path)


def test_preview_never_navigates_external_or_duplicate_targets(tmp_path):
    candidate = fixture(tmp_path)
    candidate["articles"][0]["document"]["slug"] = "https://example.org"
    with pytest.raises(ValueError, match="SLUG"):
        owner().preview_plan(candidate, tmp_path)
    candidate = fixture(tmp_path)
    candidate["articles"].append(deepcopy(candidate["articles"][0]))
    with pytest.raises(ValueError, match="DUPLICATE"):
        owner().preview_plan(candidate, tmp_path)


def test_article_only_preview_cannot_use_a_different_theme_than_production(
    tmp_path, monkeypatch
):
    candidate = fixture(tmp_path)
    theme = tmp_path / "display-theme"
    theme.mkdir()
    (theme / "style.css").write_text("/* local pending theme change */")
    monkeypatch.setattr(owner(), "THEME", theme)
    candidate["publication_ready"] = True
    candidate["baseline_theme_tree_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="THEME_DIFFERS_INCLUDE_THEME"):
        owner().runtime_fingerprint(candidate, tmp_path)


def test_only_unedited_wordpress_initial_privacy_draft_can_be_adopted():
    import subprocess
    from scripts.raos_test_runtime import php_command

    path = (
        Path(__file__).resolve().parents[2]
        / "changes/wordpress-direct-publish-v1/preview-seed.php"
    )
    source = path.read_text()
    name = "function raos_direct_preview_is_initial_privacy_draft("
    assert name in source
    helper = name + source.split(name, 1)[1].split("\n$input =", 1)[0]
    assert source.index("wp_get_environment_type() !== 'local'") < source.index(name)
    harness = r"""
class WP_Privacy_Policy_Content { static function get_default_content() { return 'core initial privacy content'; } }
function __($value) { return $value; }
function get_option($key) { global $privacy_option; return $privacy_option; }
function get_post_meta($id) { global $meta; return $meta; }
$privacy_option = '3';
$meta = array('_wp_page_template' => array('default'));
$initial = (object) array('ID'=>3, 'post_type'=>'page', 'post_status'=>'draft', 'post_name'=>'privacy-policy',
    'post_title'=>'Privacy Policy', 'post_content'=>'core initial privacy content', 'post_excerpt'=>'',
    'post_parent'=>0, 'post_date'=>'2026-09-10 00:00:00', 'post_modified'=>'2026-09-10 00:00:00',
    'post_date_gmt'=>'2026-09-09 15:00:00', 'post_modified_gmt'=>'2026-09-09 15:00:00');
$document = array('post_type'=>'page', 'slug'=>'privacy-policy');
if (!raos_direct_preview_is_initial_privacy_draft($initial, $document)) { exit(1); }
foreach (array('ID'=>4, 'post_type'=>'post', 'post_status'=>'publish', 'post_name'=>'custom',
    'post_title'=>'Customized', 'post_content'=>'Edited content', 'post_excerpt'=>'Edited excerpt',
    'post_parent'=>2, 'post_modified'=>'2026-09-11 00:00:00', 'post_modified_gmt'=>'2026-09-10 15:00:00') as $key=>$value) {
    $changed = clone $initial; $changed->$key = $value;
    if (raos_direct_preview_is_initial_privacy_draft($changed, $document)) { exit(2); }
}
foreach (array(array('_wp_page_template'=>array('custom')), array('_raos_owner_direct_preview_key'=>array('owned')), array('custom_owner'=>array('value'))) as $value) {
    $meta = $value;
    if (raos_direct_preview_is_initial_privacy_draft($initial, $document)) { exit(3); }
}
$meta = array('_wp_page_template'=>array('default'));
$privacy_option = '4';
if (raos_direct_preview_is_initial_privacy_draft($initial, $document)) { exit(4); }
$privacy_option = '3';
if (raos_direct_preview_is_initial_privacy_draft($initial, array('post_type'=>'post', 'slug'=>'privacy-policy'))
    || raos_direct_preview_is_initial_privacy_draft($initial, array('post_type'=>'page', 'slug'=>'other'))) { exit(5); }
echo "INITIAL_PRIVACY_DRAFT_ADOPTION_OK\n";
"""
    subprocess.run(php_command(["-r", helper + harness]), check=True)


def test_saved_home_is_previewed_at_front_url_without_duplicate_or_post_title(tmp_path):
    candidate = fixture(tmp_path)
    candidate["articles"][0]["document"].update(
        post_type="page", slug="home", title="ホーム"
    )
    theme = tmp_path / "theme"
    theme.mkdir()
    candidate["theme"] = {"directory": "theme"}
    assert owner().preview_plan(candidate, tmp_path)["surfaces"] == [
        {"kind": "home", "path": "/"},
        {"kind": "listing", "path": "/?post_type=post"},
    ]


def test_only_untouched_local_install_sample_can_be_drafted():
    import subprocess
    from scripts.raos_test_runtime import php_command

    source = (
        Path(__file__).resolve().parents[2]
        / "changes/wordpress-direct-publish-v1/preview-seed.php"
    ).read_text()
    name = "function raos_direct_preview_is_initial_sample("
    helper = name + source.split(name, 1)[1].split("\n$input =", 1)[0]
    assert source.index("wp_get_environment_type() !== 'local'") < source.index(name)
    harness = r"""
function get_post_meta($id) { global $meta; return $meta; }
$meta = array();
$p=(object)array('ID'=>1,'post_author'=>1,'post_type'=>'post','post_status'=>'publish',
'post_name'=>'hello-world','post_title'=>'Hello world!','post_excerpt'=>'','post_parent'=>0,
'post_date'=>'2026-09-11','post_modified'=>'2026-09-11','post_date_gmt'=>'2026-09-10','post_modified_gmt'=>'2026-09-10',
'post_content'=>"<!-- wp:paragraph -->\n<p>Welcome to WordPress. This is your first post. Edit or delete it, then start writing!</p>\n<!-- /wp:paragraph -->");
if (!raos_direct_preview_is_initial_sample($p)) { exit(1); }
foreach(array('ID'=>2,'post_author'=>2,'post_type'=>'page','post_status'=>'draft','post_name'=>'custom',
'post_title'=>'My post','post_excerpt'=>'Edited','post_parent'=>2,'post_modified'=>'changed',
'post_modified_gmt'=>'changed','post_content'=>'custom content') as $k=>$v) {
 $q=clone $p; $q->$k=$v; if(raos_direct_preview_is_initial_sample($q)) { exit(2); }
}
$meta=array('_raos_owner_direct_preview_key'=>array('owned'));
if(raos_direct_preview_is_initial_sample($p) || raos_direct_preview_is_initial_sample(null)) { exit(3); }
echo "INITIAL_SAMPLE_GUARD_OK\n";
"""
    subprocess.run(php_command(["-r", helper + harness]), check=True)
