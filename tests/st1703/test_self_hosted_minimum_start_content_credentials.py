"""Content and owner-private credential boundaries for self-hosted Minimum Start."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import Callable

import pytest

from raos.adapters.self_hosted_wordpress_credentials import (
    CREDENTIAL_RELATIVE_PATH,
    MAX_CREDENTIAL_BYTES,
    OwnerPrivateSelfHostedWordPressCredentialStore,
    SelfHostedWordPressCredentials,
)
from raos.application.editorial.self_hosted_minimum_start import (
    CONTENT_PACKET_RELATIVE_PATH,
    FIRST_ARTICLE_THEME_IMAGE_RELATIVE_PATH,
    FIRST_ARTICLE_THEME_SHORTCODE,
    FIRST_ARTICLE_THEME_SLUG,
    FIRST_ARTICLE_SLUG,
    FIRST_ARTICLE_TARGET_ORIGIN,
    FIRST_ARTICLE_TITLE,
    load_first_article_candidate,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDraft,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _copy_content(tmp_path: Path) -> Path:
    target = tmp_path / CONTENT_PACKET_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH, target)
    return target


def _credentials() -> SelfHostedWordPressCredentials:
    return SelfHostedWordPressCredentials(
        username="owner-editor",
        _application_password="synthetic-" + "credential",
    )


def test_content_packet_builds_only_bound_create_and_positive_id_update() -> None:
    create = load_first_article_candidate(
        REPOSITORY_ROOT,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
    )
    update = load_first_article_candidate(
        REPOSITORY_ROOT,
        operation=SelfHostedWordPressOperation.UPDATE_DRAFT,
        existing_draft_id=1703,
    )

    assert create.existing_draft_id is None
    assert create.title == FIRST_ARTICLE_TITLE
    assert create.slug == FIRST_ARTICLE_SLUG
    assert update.existing_draft_id == 1703
    assert create.content_sha256 == update.content_sha256
    assert create.operation_sha256 != update.operation_sha256
    assert "AIを補助的に利用" in create.content_html
    assert create.content_html.startswith(f"{FIRST_ARTICLE_THEME_SHORTCODE}\n")
    assert create.content_html.count(FIRST_ARTICLE_THEME_SHORTCODE) == 1
    assert create.content_html.count("PENDING_OFFICIAL_RAKUTEN_LINK") == 0
    assert create.content_html.count("公式楽天アフィリエイトリンク未設定") == 3


def test_self_hosted_draft_slug_is_strict_and_content_hash_bound() -> None:
    first = SelfHostedWordPressDraft.bind(
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        title="Bound title",
        slug="bound-post",
        content_html="<p>Bound content.</p>",
    )
    other = SelfHostedWordPressDraft.bind(
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        title=first.title,
        slug="different-post",
        content_html=first.content_html,
    )
    assert first.content_sha256 != other.content_sha256
    assert first.operation_sha256 != other.operation_sha256

    for invalid_slug in ("", "Bound-Post", "bound_post", "../bound-post"):
        with pytest.raises(SelfHostedWordPressFailure):
            SelfHostedWordPressDraft.bind(
                operation=SelfHostedWordPressOperation.CREATE_DRAFT,
                title=first.title,
                slug=invalid_slug,
                content_html=first.content_html,
            )


def test_verified_content_bytes_are_used_without_reopening_repository_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import raos.application.editorial.self_hosted_minimum_start as content_module

    payload = (REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH).read_bytes()

    def forbidden_read(path: Path) -> bytes:
        del path
        raise AssertionError("verified content path reopened")

    monkeypatch.setattr(content_module, "_read_stable", forbidden_read)
    candidate = content_module.load_first_article_candidate(
        REPOSITORY_ROOT,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        packet_bytes=payload,
    )
    assert candidate.operation is SelfHostedWordPressOperation.CREATE_DRAFT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_origin", "https://foreign.example.invalid"),
        ("publication_authority", "PUBLISH"),
        ("story_id", "ST-1704"),
    ],
)
def test_content_packet_rejects_authority_or_target_drift(
    tmp_path: Path, field: str, value: str
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet[field] = value
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_origin", "http://kurashinoshirube.com"),
        ("target_origin", "https://foreign.example.invalid"),
        ("target_origin", "https://kurashinoshirube.com/blog"),
        ("target_origin", "https://user@kurashinoshirube.com"),
        ("target_origin", "https://kurashinoshirube.com:443"),
        ("target_origin", "https://kurashinoshirube.com?variant=1"),
        ("theme_slug", "other-child"),
        ("theme_asset_path", "assets/images/home-hero.webp"),
        ("theme_asset_path", "../article-suitcase-guide.webp"),
        ("shortcode", "[kurashinoshirube_first_article_lead_image extra]"),
        ("alt", ""),
        ("alt", "スーツケースの商品写真"),
        ("delivery", "WORDPRESS_MEDIA_UPLOAD"),
    ],
    ids=(
        "http-origin",
        "foreign-origin",
        "wordpress-subpath",
        "userinfo",
        "port",
        "query",
        "wrong-theme",
        "wrong-image-path",
        "traversal",
        "shortcode-attributes",
        "missing-alt",
        "wrong-alt",
        "media-upload",
    ),
)
def test_content_packet_rejects_lead_image_binding_drift(
    tmp_path: Path, field: str, value: str
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"]["lead_image"][field] = value
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


def test_content_packet_rejects_missing_or_duplicated_article_image_binding(
    tmp_path: Path,
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    lead_image = packet["article"].pop("lead_image")
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )

    packet["article"]["lead_image"] = lead_image
    packet["article"]["content_html"] += FIRST_ARTICLE_THEME_SHORTCODE
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SelfHostedWordPressFailure) as duplicate:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert duplicate.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


@pytest.mark.parametrize(
    "extra_shortcode",
    [
        "[gallery]",
        "[/kurashinoshirube_first_article_lead_image]",
        "[kurashinoshirube_first_article_lead_image extra]",
        "[" + ("a" * 256) + "]",
    ],
)
def test_content_packet_rejects_any_additional_shortcode(
    tmp_path: Path, extra_shortcode: str
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"]["content_html"] += extra_shortcode
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


def test_content_packet_lead_image_matches_exact_theme_manifest_contract() -> None:
    packet = json.loads(
        (REPOSITORY_ROOT / CONTENT_PACKET_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (
            REPOSITORY_ROOT / "changes/st-1703/self-hosted-minimum-start-v1/theme/"
            "kurashinoshirube-child/raos-assets.v1.json"
        ).read_text(encoding="utf-8")
    )
    matching = [
        image
        for image in manifest["required_images"]
        if image["path"] == FIRST_ARTICLE_THEME_IMAGE_RELATIVE_PATH
    ]
    assert len(matching) == 1
    assert packet["article"]["lead_image"] == {
        "alt": matching[0]["alt"],
        "delivery": matching[0]["delivery"],
        "shortcode": FIRST_ARTICLE_THEME_SHORTCODE,
        "target_origin": "https://kurashinoshirube.com",
        "theme_asset_path": matching[0]["path"],
        "theme_slug": FIRST_ARTICLE_THEME_SLUG,
    }


def test_content_packet_rejects_first_article_title_drift(tmp_path: Path) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"]["title"] = "無関係な記事"
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slug", "different-post"),
        ("slug", "carry-on-suitcase-comparison/extra"),
        ("canonical_url", f"{FIRST_ARTICLE_TARGET_ORIGIN}/different-post/"),
    ],
)
def test_content_packet_rejects_first_article_slug_or_canonical_drift(
    tmp_path: Path, field: str, value: str
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"][field] = value
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


@pytest.mark.parametrize(
    "mutation",
    [
        lambda content: content + "<script>alert(1)</script>",
        lambda content: content + "<svg/onload=alert(1)>",
        lambda content: content + '<img src="https://tracking.invalid/pixel">',
        lambda content: (
            content + '<p style="background:url(https://tracking.invalid)">x</p>'
        ),
        lambda content: content + "<p>実際に使ってみた結果です。</p>",
        lambda content: content.replace(
            "報酬率、価格、ポイント、在庫は評価や掲載順に使いません", ""
        ),
    ],
)
def test_content_packet_rejects_active_html_fake_experience_or_disclosure_loss(
    tmp_path: Path, mutation: Callable[[str], str]
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    article = packet["article"]
    article["content_html"] = mutation(article["content_html"])
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


def test_content_packet_requires_pending_direct_sponsored_slots_and_safe_jsonld(
    tmp_path: Path,
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"]["affiliate_slots"][0]["required_rel"] = "follow"
    packet["article"]["structured_data"]["allowed_types"].append("Product")
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


def test_pending_affiliate_slot_rejects_injected_active_link(
    tmp_path: Path,
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    article = packet["article"]
    article["content_html"] = article["content_html"].replace(
        "<p>公式楽天アフィリエイトリンク未設定</p>",
        '<p><a href="https://item.rakuten.co.jp/ace-store/06316/">商品</a></p>',
        1,
    )
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


def test_affiliate_slot_metadata_must_have_exact_unique_identity(
    tmp_path: Path,
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    slots = packet["article"]["affiliate_slots"]
    slots[1]["slot_id"] = slots[0]["slot_id"]
    slots[1]["product_name"] = slots[0]["product_name"]
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure):
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )


@pytest.mark.parametrize(
    "extra_html",
    [
        (
            "<!-- RAOS-AFFILIATE-SLOT:evil BEGIN -->"
            '<div class="raos-affiliate-slot" data-raos-affiliate-slot="evil">'
            "<p>公式楽天アフィリエイトリンク未設定</p></div>"
            "<!-- RAOS-AFFILIATE-SLOT:evil END -->"
        ),
        "<!-- RAOS-AFFILIATE-SLOT:ace-cresta-06316 BEGIN -->",
    ],
)
def test_content_packet_rejects_extra_slot_or_comment_inventory(
    tmp_path: Path, extra_html: str
) -> None:
    path = _copy_content(tmp_path)
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["article"]["content_html"] += extra_html
    path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        load_first_article_candidate(
            tmp_path,
            operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        )
    assert failure.value.code is SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID


def test_private_json_install_is_exclusive_metadata_only_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path)
    assert store.metadata_status() == "MISSING"
    store.install(_credentials())
    credential_path = tmp_path / CREDENTIAL_RELATIVE_PATH

    assert credential_path.stat().st_mode & 0o777 == 0o600
    assert credential_path.parent.stat().st_mode & 0o777 == 0o700
    monkeypatch.setattr(
        OwnerPrivateSelfHostedWordPressCredentialStore,
        "read",
        lambda ignored: (_ for _ in ()).throw(AssertionError()),
    )
    monkeypatch.setattr(
        os,
        "read",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("metadata doctor read credential bytes")
        ),
    )
    assert store.metadata_status() == "METADATA_READY"
    monkeypatch.undo()

    loaded = OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path).read()
    assert loaded.username == "owner-editor"
    assert "synthetic" not in repr(loaded)
    assert "synthetic" not in str(loaded)

    with pytest.raises(SelfHostedWordPressFailure) as repeat:
        OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path).install(_credentials())
    assert (
        repeat.value.code is SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED
    )


def test_private_json_rejects_unknown_fields_wrong_mode_and_oversize(
    tmp_path: Path,
) -> None:
    store = OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path)
    store.install(_credentials())
    path = tmp_path / CREDENTIAL_RELATIVE_PATH
    value = json.loads(path.read_text(encoding="ascii"))
    value["unexpected"] = True
    path.write_text(json.dumps(value), encoding="ascii")
    path.chmod(0o600)
    with pytest.raises(SelfHostedWordPressFailure):
        store.read()

    value.pop("unexpected")
    path.write_text(json.dumps(value), encoding="ascii")
    path.chmod(0o644)
    with pytest.raises(SelfHostedWordPressFailure) as mode:
        store.metadata_status()
    assert mode.value.code is SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID

    path.chmod(0o600)
    path.write_bytes(b"x" * (MAX_CREDENTIAL_BYTES + 1))
    with pytest.raises(SelfHostedWordPressFailure):
        store.metadata_status()


def test_private_json_rejects_symlinked_secret_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (tmp_path / ".secrets").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SelfHostedWordPressFailure):
        OwnerPrivateSelfHostedWordPressCredentialStore(tmp_path).install(_credentials())


@pytest.mark.parametrize(
    ("username", "secret"),
    [
        ("owner:admin", "synthetic-credential"),
        (" owner", "synthetic-credential"),
        ("owner", "line\nbreak"),
        ("owner", ""),
    ],
)
def test_credential_value_grammar_is_closed(username: str, secret: str) -> None:
    with pytest.raises(SelfHostedWordPressFailure):
        SelfHostedWordPressCredentials(
            username=username,
            _application_password=secret,
        )
