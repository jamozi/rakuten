"""Minimal publication preview binds real inputs and never expands to a full audit."""

from copy import deepcopy
import hashlib
from pathlib import Path

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
    assert owner().product_image_mirror(candidate, tmp_path, fetch=lambda _: pytest.fail("unexpected fetch")) == {}


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


def test_saved_home_is_previewed_at_front_url_without_duplicate_or_post_title(tmp_path):
    candidate = fixture(tmp_path)
    candidate['articles'][0]['document'].update(post_type='page', slug='home', title='ホーム')
    theme = tmp_path / 'theme'
    theme.mkdir()
    candidate['theme'] = {'directory': 'theme'}
    assert owner().preview_plan(candidate, tmp_path)['surfaces'] == [
        {'kind': 'home', 'path': '/'}, {'kind': 'listing', 'path': '/?post_type=post'},
    ]
