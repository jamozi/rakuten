"""Old public photographs can be reproduced locally, never relabeled verified."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts import raos_wordpress_baseline_media as media
from raos.application.editorial.verified_incremental_v1 import (
    IncrementalPublicationFailure,
)

NOW = datetime(2026, 9, 5, 2, tzinfo=UTC)
URL = "https://thumbnail.image.rakuten.co.jp/@0_mall/example/cabinet/example.jpg?_ex=300x300"
IMAGE = b"\xff\xd8\xff" + b"synthetic image header for byte-preservation test"


def inputs() -> tuple[dict[str, Any], media.MixedPreview]:
    rows = []
    for identifier, slug in enumerate(("old-article", "new-article"), 1):
        body = (
            '<div><article data-raos-product-id="P1"><img src="'
            + URL
            + '" alt="Existing picture" width="300" height="300"><a href="https://example.com/spec">Existing source</a></article></div>'
        )
        row = {
            "schema": "ContentDocumentV1",
            "post_type": "post",
            "id": identifier,
            "status": "publish",
            "title": slug,
            "slug": slug,
            "excerpt": "Original excerpt",
            "block_markup": body,
            "taxonomies": {},
            "media_ids": [],
        }
        row["content_sha256"] = media.digest(media.canonical(row).rstrip(b"\n"))
        rows.append(row)
    snapshot = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_LIVE_SNAPSHOT_V1",
        "publication_profile": "verified-incremental",
        "source": "BOUNDED_WORDPRESS_EDITOR_MCP",
        "origin": "https://kurashinoshirube.com",
        "publication_authority": False,
        "documents": rows,
    }
    articles = {
        "old-article": rows[0]["block_markup"].encode(),
        "new-article": b"<div>New informational article without any purchase photograph.</div>",
    }
    mixed = media.MixedPreview(
        b"{}",
        articles,
        {
            "source_snapshot_sha256": media.digest(
                media.canonical(snapshot).rstrip(b"\n")
            ),
            "selected_slugs": ["new-article"],
            "article_body_sha256": {
                slug: media.digest(raw) for slug, raw in articles.items()
            },
        },
    )
    return snapshot, mixed


def fetch(url: str) -> media.ImageResponse:
    return media.ImageResponse(
        url, IMAGE, "image/jpeg", NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def test_only_existing_unselected_image_is_fetched_and_only_src_changes() -> None:
    snapshot, mixed = inputs()
    called = []

    def recorded(url: str) -> media.ImageResponse:
        called.append(url)
        return fetch(url)

    replayed, assets = media.prepare_replay(snapshot, mixed, now=NOW, fetch=recorded)
    local = media.PREFIX + media.digest(IMAGE) + ".jpg"
    assert called == [URL]
    assert replayed.articles["old-article"] == mixed.articles["old-article"].replace(
        URL.encode(), local.encode()
    )
    assert replayed.articles["new-article"] == mixed.articles["new-article"]
    assert assets == {media.digest(IMAGE) + ".jpg": IMAGE}
    receipt = replayed.binding["baseline_media"]
    assert receipt["publication_authority"] is False
    assert receipt["new_commerce_verified"] is False
    assert receipt["status"] == "BASELINE_PUBLIC_BYTES_REPLAYED_LOCALLY_ONLY"
    assert receipt["articles"]["old-article"]["baseline_body_sha256"] == media.digest(
        mixed.articles["old-article"]
    )


def test_changed_old_body_is_not_an_authorized_url_source() -> None:
    snapshot, mixed = inputs()
    changed = media.replace(
        mixed,
        articles={
            **mixed.articles,
            "old-article": mixed.articles["old-article"].replace(
                b"example.jpg", b"another.jpg"
            ),
        },
    )
    with pytest.raises(IncrementalPublicationFailure, match="ORIGINAL_BODY_CHANGED"):
        media.prepare_replay(
            snapshot, changed, now=NOW, fetch=lambda _: pytest.fail("must not fetch")
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://thumbnail.image.rakuten.co.jp/@0_mall/x/a.jpg",
        "https://evil.example/@0_mall/x/a.jpg",
        "https://thumbnail.image.rakuten.co.jp.evil.example/@0_mall/x/a.jpg",
        "https://user:secret@thumbnail.image.rakuten.co.jp/@0_mall/x/a.jpg",
        "https://thumbnail.image.rakuten.co.jp/@0_mall/x/a.jpg#different",
        "https://thumbnail.image.rakuten.co.jp/arbitrary-path",
        "https://thumbnail.image.rakuten.co.jp:444/@0_mall/x/a.jpg",
    ],
)
def test_network_targets_are_bounded_before_io(url: str) -> None:
    with pytest.raises(IncrementalPublicationFailure, match="URL_NOT_SUPPORTED"):
        media.validate_url(url)


@pytest.mark.parametrize(
    "response",
    [
        media.ImageResponse(
            URL,
            b"<svg>Active content is not a raster.</svg>",
            "image/svg+xml",
            "2026-09-05T02:00:00Z",
        ),
        media.ImageResponse(URL, IMAGE, "text/html", "2026-09-05T02:00:00Z"),
        media.ImageResponse(URL, IMAGE, "image/jpeg", "2026-09-04T02:00:00Z"),
        media.ImageResponse(
            URL + "&changed=1", IMAGE, "image/jpeg", "2026-09-05T02:00:00Z"
        ),
    ],
)
def test_wrong_bytes_mime_old_capture_or_response_url_are_rejected(
    response: media.ImageResponse,
) -> None:
    snapshot, mixed = inputs()
    with pytest.raises(IncrementalPublicationFailure):
        media.prepare_replay(snapshot, mixed, now=NOW, fetch=lambda _: response)


def test_selected_articles_do_not_cause_any_old_image_fetch() -> None:
    snapshot, mixed = inputs()
    mixed = media.replace(
        mixed, binding={**mixed.binding, "selected_slugs": list(mixed.articles)}
    )
    replayed, assets = media.prepare_replay(
        snapshot,
        mixed,
        now=NOW,
        fetch=lambda _: pytest.fail("no selected product image capture"),
    )
    assert assets == {}
    assert replayed.articles == mixed.articles


def test_private_original_and_public_byte_only_mirror_are_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private = tmp_path / "owner-private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(media, "PRIVATE", private)
    monkeypatch.setattr(media, "MIRROR", private / "baseline-preview-media")
    name = media.digest(IMAGE) + ".jpg"
    media.write_assets({name: IMAGE})
    assert (private / "baseline-image-originals" / name).stat().st_mode & 0o777 == 0o600
    assert (private / "baseline-image-originals").stat().st_mode & 0o777 == 0o700
    assert (media.MIRROR / name).stat().st_mode & 0o777 == 0o444
    assert {path.name for path in media.MIRROR.iterdir()} == {name}
    assert (media.MIRROR / name).read_bytes() == IMAGE


def test_exact_replay_refuses_projection_or_receipt_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, mixed = inputs()
    private = tmp_path / "owner-private"
    private.mkdir(mode=0o700)
    monkeypatch.setattr(media, "PRIVATE", private)
    monkeypatch.setattr(media, "MIRROR", private / "baseline-preview-media")
    replayed, assets = media.prepare_replay(snapshot, mixed, now=NOW, fetch=fetch)
    media.write_assets(assets)
    media.write_private_bytes(
        private / "incremental-snapshots",
        f"live-{mixed.binding['source_snapshot_sha256']}.v1.json",
        media.canonical(snapshot),
    )
    fixture = tmp_path / "fixture"
    for slug, raw in replayed.articles.items():
        media.write_private_bytes(fixture / "articles", slug + ".html", raw)
    media.validate_replay(fixture, replayed.binding)
    changed = deepcopy(replayed.binding)
    changed["baseline_media"]["new_commerce_verified"] = True
    with pytest.raises(IncrementalPublicationFailure, match="RECEIPT_INVALID"):
        media.validate_replay(fixture, changed)
    media.write_private_bytes(
        fixture / "articles",
        "old-article.html",
        replayed.articles["old-article"].replace(b"Existing picture", b"Wrong picture"),
    )
    with pytest.raises(IncrementalPublicationFailure, match="PROJECTION_CHANGED"):
        media.validate_replay(fixture, replayed.binding)
