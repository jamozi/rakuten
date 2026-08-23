"""Deterministic, closed theme-source and package tests for ST-1703."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_st1703_self_hosted_theme as theme  # noqa: E402


# Exact 1x1/2x2 fixtures were decoded successfully with ffmpeg 4.4.2/libwebp
# before being frozen here. Runtime acceptance does not depend on that executable.
VALID_WEBP_VP8 = bytes.fromhex(
    "52494646220000005745425056503820160000003001009d012a010001000140"
    "2625a400037000feff3d"
)
VALID_WEBP_VP8L = bytes.fromhex(
    "524946461e000000574542505650384c110000002f0140000007d0fffef7bfff8188e87f0000"
)
VALID_WEBP_VP8X_ALPHA = bytes.fromhex(
    "524946465c00000057454250565038580a00000010000000010000010000414c"
    "5048050000000080808080005650382030000000d001009d012a020002000140"
    "2625a00274ba01f80003b000fef36997fe6c0ae6b9f7fbffe9707e9707e9707f"
    "e8b80000"
)


def _webp_chunk(chunk_type: bytes, payload: bytes, *, pad: bytes = b"\x00") -> bytes:
    assert len(chunk_type) == 4 and len(pad) == 1
    return (
        chunk_type
        + len(payload).to_bytes(4, "little")
        + payload
        + (pad if len(payload) & 1 else b"")
    )


def _webp_container(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def _with_exact_riff_size(payload: bytes) -> bytes:
    return payload[:4] + (len(payload) - 8).to_bytes(4, "little") + payload[8:]


def _invalid_webp_cases() -> dict[str, bytes]:
    vp8 = bytearray(VALID_WEBP_VP8[20:])
    vp8[:3] = ((0x7FFFF << 5) | 0x10).to_bytes(3, "little")
    vp8_signature = bytearray(VALID_WEBP_VP8[20:])
    vp8_signature[3:6] = b"bad"
    vp8l = bytearray(VALID_WEBP_VP8L[20:-1])
    vp8l_header = int.from_bytes(vp8l[1:5], "little") | (1 << 29)
    vp8l[1:5] = vp8l_header.to_bytes(4, "little")
    vp8l_signature = bytearray(VALID_WEBP_VP8L[20:-1])
    vp8l_signature[0] = 0
    vp8x_reserved = bytearray(VALID_WEBP_VP8X_ALPHA)
    vp8x_reserved[20] |= 0x01
    vp8x_animation = bytearray(VALID_WEBP_VP8X_ALPHA)
    vp8x_animation[20] |= 0x02
    vp8x_canvas_mismatch = bytearray(VALID_WEBP_VP8X_ALPHA)
    vp8x_canvas_mismatch[24:27] = b"\x02\x00\x00"
    vp8x_feature_mismatch = bytearray(VALID_WEBP_VP8X_ALPHA)
    vp8x_feature_mismatch[20] = 0
    vp8x_payload = VALID_WEBP_VP8X_ALPHA[20:30]
    vp8x_vp8_payload = VALID_WEBP_VP8X_ALPHA[52:]
    compressed_alpha = bytearray(VALID_WEBP_VP8X_ALPHA[38:43])
    compressed_alpha[0] = 1
    odd_padding = bytearray(VALID_WEBP_VP8L)
    odd_padding[-1] = 1
    trailing = _with_exact_riff_size(VALID_WEBP_VP8 + b"\x00")
    return {
        "truncated-prefix": VALID_WEBP_VP8[:12],
        "riff-size-mismatch": (
            VALID_WEBP_VP8[:4] + b"\x00\x00\x00\x00" + VALID_WEBP_VP8[8:]
        ),
        "incomplete-chunk": _webp_container(
            b"VP8 " + (99).to_bytes(4, "little") + b"short"
        ),
        "vp8-partition-overflow": _webp_container(_webp_chunk(b"VP8 ", bytes(vp8))),
        "vp8-signature": _webp_container(_webp_chunk(b"VP8 ", bytes(vp8_signature))),
        "vp8l-version": _webp_container(_webp_chunk(b"VP8L", bytes(vp8l))),
        "vp8l-signature": _webp_container(_webp_chunk(b"VP8L", bytes(vp8l_signature))),
        "vp8x-reserved": bytes(vp8x_reserved),
        "vp8x-animation": bytes(vp8x_animation),
        "vp8x-canvas-mismatch": bytes(vp8x_canvas_mismatch),
        "vp8x-feature-mismatch": bytes(vp8x_feature_mismatch),
        "vp8x-short-uncompressed-alpha": _webp_container(
            _webp_chunk(b"VP8X", vp8x_payload),
            _webp_chunk(b"ALPH", b"\x00\x80"),
            _webp_chunk(b"VP8 ", vp8x_vp8_payload),
        ),
        "vp8x-compressed-alpha-unsupported": _webp_container(
            _webp_chunk(b"VP8X", vp8x_payload),
            _webp_chunk(b"ALPH", bytes(compressed_alpha)),
            _webp_chunk(b"VP8 ", vp8x_vp8_payload),
        ),
        "unknown-chunk": _webp_container(_webp_chunk(b"JUNK", b"x")),
        "duplicate-image": _webp_container(
            _webp_chunk(b"VP8 ", VALID_WEBP_VP8[20:]),
            _webp_chunk(b"VP8 ", VALID_WEBP_VP8[20:]),
        ),
        "misordered-metadata": _webp_container(
            _webp_chunk(b"VP8X", b"\x04\x00\x00\x00" + b"\x00\x00\x00" * 2),
            _webp_chunk(b"XMP ", b"<x/>"),
            _webp_chunk(b"VP8 ", VALID_WEBP_VP8[20:]),
        ),
        "odd-padding-missing": _with_exact_riff_size(VALID_WEBP_VP8L[:-1]),
        "odd-padding-nonzero": bytes(odd_padding),
        "trailing-byte": trailing,
    }


def _isolated_theme(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / theme.THEME_SLUG
    shutil.copytree(theme.THEME_ROOT, target)
    output_repository = tmp_path / "output-repository"
    output_repository.mkdir(mode=0o700)
    output_directory = output_repository.joinpath(*theme._PRIVATE_OUTPUT_PARTS)
    monkeypatch.setattr(theme, "THEME_ROOT", target)
    monkeypatch.setattr(theme, "MANIFEST_PATH", target / "raos-assets.v1.json")
    monkeypatch.setattr(theme, "OUTPUT_REPOSITORY_ROOT", output_repository)
    monkeypatch.setattr(theme, "OUTPUT_DIRECTORY", output_directory)
    monkeypatch.setattr(
        theme, "OUTPUT_PATH", output_directory / f"{theme.THEME_SLUG}.zip"
    )
    return target


def _create_private_output_parent() -> None:
    current = theme.OUTPUT_REPOSITORY_ROOT
    for part in theme._PRIVATE_OUTPUT_PARTS:
        current /= part
        current.mkdir(mode=theme.PRIVATE_OUTPUT_DIRECTORY_MODE, exist_ok=True)
        current.chmod(theme.PRIVATE_OUTPUT_DIRECTORY_MODE)
    assert current == theme.OUTPUT_DIRECTORY


def _manifest(path: Path) -> dict[str, object]:
    return json.loads((path / "raos-assets.v1.json").read_text(encoding="utf-8"))


def _write_manifest(path: Path, value: dict[str, object]) -> None:
    (path / "raos-assets.v1.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _synthetic_webp(seed: int) -> bytes:
    vp8_payload = VALID_WEBP_VP8[20:]
    vp8x_payload = b"\x04\x00\x00\x00" + b"\x00\x00\x00" * 2
    xmp_payload = f"<x>{seed}</x>".encode("ascii")
    return _webp_container(
        _webp_chunk(b"VP8X", vp8x_payload),
        _webp_chunk(b"VP8 ", vp8_payload),
        _webp_chunk(b"XMP ", xmp_payload),
    )


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _complete_assets(path: Path) -> None:
    manifest = _manifest(path)
    images = manifest["required_images"]
    assert isinstance(images, list)
    for index, image_value in enumerate(images, start=1):
        assert isinstance(image_value, dict)
        relative = image_value["path"]
        assert isinstance(relative, str)
        payload = _synthetic_webp(index)
        image_path = path / relative
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(payload)
        image_value["status"] = "FINAL"
        image_value["sha256"] = hashlib.sha256(payload).hexdigest()
    _write_manifest(path, manifest)


@pytest.mark.parametrize(
    ("payload", "expected_sha256"),
    [
        (
            VALID_WEBP_VP8,
            "7e74e6e307fc3dedeef1c33d61124413d7c3f20068170e940a307f01897cdaa7",
        ),
        (
            VALID_WEBP_VP8L,
            "eebf3679c38ec3a934864322fe7e5f590a9316c2ec6752164173bcfb702a669c",
        ),
        (
            VALID_WEBP_VP8X_ALPHA,
            "7ea27cbfb6af8eb36e9248bf6383d0f94cd48e9800b6cf473c5f8762897ab18e",
        ),
    ],
    ids=("vp8", "vp8l-odd-padding", "vp8x-alpha"),
)
def test_complete_webp_validator_accepts_real_minimal_fixtures(
    payload: bytes, expected_sha256: str
) -> None:
    assert hashlib.sha256(payload).hexdigest() == expected_sha256
    assert theme._is_complete_static_webp_container(payload)


@pytest.mark.parametrize(
    ("case", "payload"),
    tuple(_invalid_webp_cases().items()),
)
def test_complete_webp_validator_rejects_malformed_file(
    case: str, payload: bytes
) -> None:
    assert case
    assert not theme._is_complete_static_webp_container(payload)


@pytest.mark.parametrize(
    "payload",
    [VALID_WEBP_VP8, VALID_WEBP_VP8L, VALID_WEBP_VP8X_ALPHA],
    ids=("vp8", "vp8l", "vp8x"),
)
def test_complete_webp_validator_rejects_every_truncated_prefix(
    payload: bytes,
) -> None:
    for size in range(len(payload)):
        truncated = payload[:size]
        if len(truncated) >= 8:
            truncated = _with_exact_riff_size(truncated)
        assert not theme._is_complete_static_webp_container(truncated), size


@pytest.mark.parametrize(
    ("case", "payload"),
    tuple(_invalid_webp_cases().items()),
)
def test_hash_bound_malformed_final_asset_never_becomes_package_ready(
    case: str,
    payload: bytes,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert case and isinstance(images, list) and isinstance(images[0], dict)
    relative = images[0]["path"]
    assert isinstance(relative, str)
    (root / relative).write_bytes(payload)
    images[0]["sha256"] = hashlib.sha256(payload).hexdigest()
    _write_manifest(root, manifest)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_INVALID"):
        theme.source_check()


def test_real_source_and_final_assets_are_package_ready() -> None:
    result = theme.source_check()
    assert result == {
        "asset_status": "FINAL",
        "first_article_asset_status": "FINAL",
        "network_requests": 0,
        "package_ready": True,
        "pending_asset_count": 0,
        "source_file_count": 10,
        "status": "SOURCE_VALID",
        "theme_slug": "kurashinoshirube-child",
    }
    assert theme.package_bytes() == theme.package_bytes()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("alt", "", "THEME_MANIFEST_INVALID"),
        ("alt", "別の説明", "THEME_ARTICLE_ASSET_BINDING_INVALID"),
        ("usage", "site-wide image", "THEME_ARTICLE_ASSET_BINDING_INVALID"),
        ("delivery", "WORDPRESS_MEDIA_UPLOAD", "THEME_ASSET_DELIVERY_INVALID"),
        (
            "path",
            "assets/images/article-suitcase-guide-2.webp",
            "THEME_ASSET_DELIVERY_INVALID",
        ),
    ],
)
def test_article_asset_manifest_binding_rejects_alt_delivery_usage_or_path_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: str,
    code: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    manifest = _manifest(root)
    article_images = [
        item
        for item in manifest["required_images"]
        if isinstance(item, dict)
        and item.get("path") == theme.FIRST_ARTICLE_IMAGE_RELATIVE_PATH
    ]
    assert len(article_images) == 1
    article_images[0][field] = value
    _write_manifest(root, manifest)

    with pytest.raises(theme.ThemeBuildFailure, match=code):
        theme.source_check()


def test_article_asset_manifest_rejects_missing_or_duplicated_record(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert isinstance(images, list) and len(images) == 2
    article = next(
        item
        for item in images
        if isinstance(item, dict)
        and item.get("path") == theme.FIRST_ARTICLE_IMAGE_RELATIVE_PATH
    )
    images.remove(article)
    _write_manifest(root, manifest)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_MANIFEST_INVALID"):
        theme.source_check()

    images.append(article)
    images.append(dict(article))
    _write_manifest(root, manifest)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_MANIFEST_INVALID"):
        theme.source_check()


def test_first_article_shortcode_renderer_is_same_origin_article_and_path_bound() -> (
    None
):
    functions = (theme.THEME_ROOT / "functions.php").read_text(encoding="utf-8")
    single = (theme.THEME_ROOT / "templates/single.html").read_text(encoding="utf-8")

    assert hashlib.sha256(functions.encode("utf-8")).hexdigest() == (
        theme.EXPECTED_THEME_FUNCTIONS_SHA256
    )
    assert functions.count("kurashinoshirube_first_article_lead_image") == 2
    assert "$attributes !== array()" in functions
    assert "$content !== null" in functions
    assert "$tag !== 'kurashinoshirube_first_article_lead_image'" in functions
    assert "! is_singular('post')" in functions
    assert "get_post_field('post_title', get_the_ID(), 'raw')" in functions
    assert theme.FIRST_ARTICLE_TITLE in functions
    assert "get_post_field('post_name', get_the_ID(), 'raw')" in functions
    assert theme.FIRST_ARTICLE_SLUG in functions
    assert "get_stylesheet() !== 'kurashinoshirube-child'" in functions
    assert "get_stylesheet_directory()" in functions
    assert "is_link($image_path)" in functions
    assert "is_file($image_path)" in functions
    assert "is_readable($image_path)" in functions
    assert "get_stylesheet_directory_uri()" in functions
    assert "($uri['scheme'] ?? null) !== 'https'" in functions
    assert "($uri['host'] ?? null) !== 'kurashinoshirube.com'" in functions
    assert "array('port', 'user', 'pass', 'query', 'fragment')" in functions
    assert "(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*kurashinoshirube-child" in functions
    assert "/assets/images/article-suitcase-guide.webp" in functions
    assert theme.FIRST_ARTICLE_IMAGE_ALT in functions
    assert functions.count("<img src=") == 1
    assert "esc_url($image_uri)" in functions
    assert "esc_attr($alt)" in functions
    assert "https://kurashinoshirube.com/wp-content" not in functions
    assert "featured_media" not in functions
    assert "media_handle" not in functions
    assert "wp_insert_attachment" not in functions
    assert "add_filter" not in functions
    assert "wp:post-featured-image" not in single
    assert single.count("<!-- wp:post-content ") == 1


@pytest.mark.parametrize(
    ("path", "accepted"),
    [
        ("/wp-content/themes/kurashinoshirube-child", True),
        ("/custom-content/themes/kurashinoshirube-child", True),
        ("/kurashinoshirube-child", True),
        ("/wp-content/themes/other-child", False),
        ("/wp-content/themes/kurashinoshirube-child/extra", False),
        ("/wp-content//themes/kurashinoshirube-child", False),
        ("/wp-content/../themes/kurashinoshirube-child", False),
        ("/wp-content/%2e%2e/themes/kurashinoshirube-child", False),
        ("/wp-content\\themes\\kurashinoshirube-child", False),
        ("", False),
    ],
)
def test_shortcode_stylesheet_path_profile_rejects_unsafe_subpaths(
    path: str, accepted: bool
) -> None:
    profile = re.compile(r"/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*kurashinoshirube-child\Z")
    assert (profile.fullmatch(path) is not None) is accepted


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("($uri['scheme'] ?? null) !== 'https'", "($uri['scheme'] ?? null) !== 'http'"),
        (
            "($uri['host'] ?? null) !== 'kurashinoshirube.com'",
            "($uri['host'] ?? null) !== 'foreign.example.invalid'",
        ),
        (theme.FIRST_ARTICLE_TITLE, "無関係な記事"),
        (theme.FIRST_ARTICLE_SLUG, "different-post"),
        ("kurashinoshirube-child", "other-child"),
        ("article-suitcase-guide.webp", "home-hero.webp"),
        (theme.FIRST_ARTICLE_IMAGE_ALT, "説明なし"),
    ],
    ids=("scheme", "origin", "title", "slug", "theme", "asset-path", "alt"),
)
def test_source_check_rejects_shortcode_origin_article_path_or_alt_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    before: str,
    after: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    functions = root / "functions.php"
    source = functions.read_text(encoding="utf-8")
    assert source.count(before) >= 1
    functions.write_text(source.replace(before, after, 1), encoding="utf-8")

    with pytest.raises(
        theme.ThemeBuildFailure, match="THEME_ARTICLE_ASSET_BINDING_INVALID"
    ):
        theme.source_check()


def test_reveal_is_progressive_enhancement_with_failure_and_motion_fallbacks() -> None:
    stylesheet = (theme.THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    script = (theme.THEME_ROOT / "assets/theme.js").read_text(encoding="utf-8")
    default_rule = stylesheet.split(".raos-reveal {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "opacity: 1;" in default_rule
    assert "transform: none;" in default_rule
    assert ".raos-reveal-ready .raos-reveal:not(.is-visible)" in stylesheet
    reduced = stylesheet.split("@media (prefers-reduced-motion: reduce)", maxsplit=1)[1]
    assert ".raos-reveal-ready .raos-reveal" in reduced
    assert 'root.classList.add("raos-reveal-ready")' in script
    assert 'root.classList.remove("raos-reveal-ready")' in script
    assert script.index("observer = new IntersectionObserver") < script.index(
        'root.classList.add("raos-reveal-ready")'
    )
    assert "revealAll();" in script


def test_footer_link_states_and_focus_indicator_meet_contrast_contract() -> None:
    stylesheet = (theme.THEME_ROOT / "assets/theme.css").read_text(encoding="utf-8")
    assert hashlib.sha256(stylesheet.encode("utf-8")).hexdigest() == (
        theme.EXPECTED_THEME_CSS_SHA256
    )
    theme_document = json.loads(
        (theme.THEME_ROOT / "theme.json").read_text(encoding="utf-8")
    )
    assert theme_document["styles"]["elements"]["link"]["color"]["text"] == ("#24365f")
    assert ".raos-footer {\n  background: var(--raos-ink);" in stylesheet
    assert "  --raos-footer-link: #f6f1e8;\n" in stylesheet
    assert "  --raos-footer-link-interactive: #f0b49b;\n" in stylesheet
    assert (
        ".raos-footer a:link,\n.raos-footer a:visited {\n"
        "  color: var(--raos-footer-link);\n}" in stylesheet
    )
    assert (
        ".raos-footer a:hover,\n.raos-footer a:focus-visible,\n"
        ".raos-footer a:active {\n"
        "  color: var(--raos-footer-link-interactive);\n}" in stylesheet
    )
    assert (
        ".raos-footer a:focus-visible {\n"
        "  outline-color: var(--raos-footer-link-interactive);\n}" in stylesheet
    )

    footer_background = "#17243f"
    button_background = "#24365f"
    for foreground in ("#f6f1e8", "#f0b49b"):
        assert _contrast_ratio(foreground, footer_background) >= 4.5
        assert _contrast_ratio(foreground, button_background) >= 4.5
    assert _contrast_ratio("#f0b49b", footer_background) >= 3.0


def test_header_footer_landmarks_are_owned_only_by_template_part_wrappers() -> None:
    for relative in ("templates/front-page.html", "templates/single.html"):
        template = (theme.THEME_ROOT / relative).read_text(encoding="utf-8")
        assert (
            template.count(
                '<!-- wp:template-part {"slug":"header","tagName":"header"} /-->'
            )
            == 1
        )
        assert (
            template.count(
                '<!-- wp:template-part {"slug":"footer","tagName":"footer"} /-->'
            )
            == 1
        )
        assert "<header" not in template
        assert "<footer" not in template

    header = (theme.THEME_ROOT / "parts/header.html").read_text(encoding="utf-8")
    footer = (theme.THEME_ROOT / "parts/footer.html").read_text(encoding="utf-8")
    assert '"tagName":"header"' not in header
    assert '"tagName":"footer"' not in footer
    assert "<header" not in header
    assert "<footer" not in footer
    assert '<div class="wp-block-group alignwide raos-masthead">' in header
    assert '<div class="wp-block-group raos-footer">' in footer


@pytest.mark.parametrize(
    ("relative", "landmark"),
    [
        ("parts/header.html", "header"),
        ("parts/footer.html", "footer"),
    ],
)
def test_source_check_rejects_semantic_landmark_on_part_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative: str,
    landmark: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    target = root / relative
    text = target.read_text(encoding="utf-8")
    text = text.replace(
        "<!-- wp:group {",
        f'<!-- wp:group {{"tagName":"{landmark}",',
        1,
    ).replace("<div ", f"<{landmark} ", 1)
    closing = text.rfind("</div>")
    assert closing >= 0
    text = text[:closing] + f"</{landmark}>" + text[closing + len("</div>") :]
    target.write_text(text, encoding="utf-8")

    with pytest.raises(
        theme.ThemeBuildFailure, match="THEME_SEMANTIC_LANDMARK_INVALID"
    ):
        theme.source_check()


@pytest.mark.parametrize(
    ("relative", "landmark"),
    [
        ("templates/front-page.html", "header"),
        ("templates/front-page.html", "footer"),
        ("templates/single.html", "header"),
        ("templates/single.html", "footer"),
    ],
)
def test_source_check_rejects_missing_template_part_landmark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative: str,
    landmark: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    target = root / relative
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace(f',"tagName":"{landmark}"', "", 1), encoding="utf-8")

    with pytest.raises(
        theme.ThemeBuildFailure, match="THEME_SEMANTIC_LANDMARK_INVALID"
    ):
        theme.source_check()


def test_verified_theme_snapshot_does_not_reopen_mutated_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    payloads = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    (root / "assets/theme.css").write_bytes(b"unreviewed replacement")
    result = theme.source_check_from_verified_files(payloads)
    assert result["status"] == "SOURCE_VALID"
    assert result["package_ready"] is True


def test_complete_fixture_packages_deterministically_and_checks_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    verified_payloads = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    verified = theme.source_check_from_verified_files(verified_payloads)
    assert verified["asset_status"] == "FINAL"
    assert verified["first_article_asset_status"] == "FINAL"
    assert verified["package_ready"] is True
    assert verified["pending_asset_count"] == 0

    first = theme.package_bytes()
    second = theme.package_bytes()
    assert first == second
    theme._write_package(first)
    private_directory = theme.OUTPUT_REPOSITORY_ROOT
    for part in theme._PRIVATE_OUTPUT_PARTS:
        private_directory /= part
        details = private_directory.lstat()
        assert stat.S_ISDIR(details.st_mode)
        assert details.st_uid == os.getuid()
        assert stat.S_IMODE(details.st_mode) == theme.PRIVATE_OUTPUT_DIRECTORY_MODE
    output_details = theme.OUTPUT_PATH.lstat()
    assert stat.S_ISREG(output_details.st_mode)
    assert output_details.st_uid == os.getuid()
    assert output_details.st_nlink == 1
    assert stat.S_IMODE(output_details.st_mode) == theme.PRIVATE_OUTPUT_FILE_MODE
    before = theme.OUTPUT_PATH.stat().st_mtime_ns
    assert theme.main(["--check"]) == 0
    assert theme.OUTPUT_PATH.stat().st_mtime_ns == before
    assert '"status": "PACKAGE_VALID"' in capsys.readouterr().out

    with zipfile.ZipFile(theme.OUTPUT_PATH) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith("kurashinoshirube-child/") for name in names)
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()
        )
        embedded = json.loads(
            archive.read("kurashinoshirube-child/raos-assets.v1.json")
        )
        assert embedded["generated_by"] == "scripts/build_st1703_self_hosted_theme.py"
        assert embedded["package_command"] == (
            "make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile "
            "theme-package"
        )


def test_owner_private_package_path_is_fixed_and_gitignored() -> None:
    relative = theme.OUTPUT_PATH.relative_to(theme.REPOSITORY_ROOT).as_posix()
    assert relative == (
        ".secrets/self-hosted-theme-packages/kurashinoshirube-child.zip"
    )
    assert not relative.startswith(".secrets/wordpress-owner-local/")
    result = subprocess.run(
        ["/usr/bin/git", "check-ignore", "--quiet", "--", relative],
        cwd=theme.REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    runtime_manifest = json.loads(
        (
            theme.REPOSITORY_ROOT
            / "changes/st-1703/self-hosted-minimum-start-v1/runtime-manifest.v1.json"
        ).read_text(encoding="utf-8")
    )
    assert relative not in {row["path"] for row in runtime_manifest["paths"]}


def test_package_then_check_keeps_launcher_git_status_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    repository = theme.OUTPUT_REPOSITORY_ROOT
    shutil.copy2(REPOSITORY_ROOT / ".gitignore", repository / ".gitignore")
    git_environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(tmp_path / "empty-git-home"),
    }
    (tmp_path / "empty-git-home").mkdir(mode=0o700)

    def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["/usr/bin/git", *arguments],
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
            env=git_environment,
        )

    assert git("init", "--quiet").returncode == 0
    assert git("add", "--", ".gitignore").returncode == 0
    committed = git(
        "-c",
        "user.name=RAOS Test",
        "-c",
        "user.email=raos-test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    assert committed.returncode == 0, (committed.stdout, committed.stderr)
    assert git("status", "--porcelain=v1", "--untracked-files=all").stdout == b""

    assert theme.main(["--package"]) == 0
    assert theme.main(["--check"]) == 0
    assert '"status": "PACKAGE_VALID"' in capsys.readouterr().out
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    assert status.returncode == 0, (status.stdout, status.stderr)
    assert status.stdout == b""


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("traversal", "THEME_PATH_INVALID"),
        ("remote", "THEME_REMOTE_LOAD_FORBIDDEN"),
        ("motion", "THEME_ACCESSIBILITY_INVALID"),
        ("progressive", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-contrast", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-override", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-inline-variable", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-inline-color", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-background", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-background-color", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-outline", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-opacity", "THEME_ACCESSIBILITY_INVALID"),
        ("footer-text-fill", "THEME_ACCESSIBILITY_INVALID"),
    ],
)
def test_source_checks_reject_traversal_remote_load_and_missing_reduced_motion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
    code: str,
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    if mutation == "traversal":
        manifest = _manifest(root)
        source_files = manifest["source_files"]
        assert isinstance(source_files, list)
        source_files[0] = "../escape.css"
        _write_manifest(root, manifest)
    elif mutation == "remote":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + '\n.remote { background: url("https://untrusted.invalid/a.png"); }\n',
            encoding="utf-8",
        )
    elif mutation == "motion":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8").replace(
                "@media (prefers-reduced-motion: reduce)",
                "@media (min-width: 1px)",
            ),
            encoding="utf-8",
        )
    elif mutation == "progressive":
        script = root / "assets/theme.js"
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                'root.classList.remove("raos-reveal-ready")',
                'root.classList.remove("broken-reveal-state")',
            ),
            encoding="utf-8",
        )
    elif mutation == "footer-contrast":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8").replace(
                "  --raos-footer-link: #f6f1e8;",
                "  --raos-footer-link: #24365f;",
            ),
            encoding="utf-8",
        )
    elif mutation == "footer-override":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.raos-footer a:link {\n  color: #24365f;\n}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-inline-variable":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\nfooter{--raos-footer-link:#24365f}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-inline-color":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-block-template-part a:link{color:#24365f}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-background":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-site-blocks footer{background:#f6f1e8}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-background-color":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-site-blocks footer{background-color:#f6f1e8}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-outline":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-site-blocks footer a:focus-visible{outline:none}\n",
            encoding="utf-8",
        )
    elif mutation == "footer-opacity":
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-site-blocks footer a{opacity:.1}\n",
            encoding="utf-8",
        )
    else:
        stylesheet = root / "assets/theme.css"
        stylesheet.write_text(
            stylesheet.read_text(encoding="utf-8")
            + "\n.wp-site-blocks footer a{-webkit-text-fill-color:#24365f}\n",
            encoding="utf-8",
        )
    with pytest.raises(theme.ThemeBuildFailure, match=code):
        theme.source_check()


def test_final_asset_hash_and_package_drift_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert isinstance(images, list) and isinstance(images[0], dict)
    images[0]["sha256"] = "0" * 64
    _write_manifest(root, manifest)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_INVALID"):
        theme.package_bytes()

    _complete_assets(root)
    _create_private_output_parent()
    theme.OUTPUT_PATH.write_bytes(b"stale")
    theme.OUTPUT_PATH.chmod(theme.PRIVATE_OUTPUT_FILE_MODE)
    assert theme.main(["--check"]) == 2
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out


def test_source_snapshot_rejects_symlinked_ancestor_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    outside = tmp_path / "outside.css"
    outside.write_text("safe outside bytes", encoding="utf-8")
    source = root / "assets/theme.css"
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FILE_INVALID"):
        theme.source_check()

    shutil.rmtree(root)
    physical = tmp_path / "physical-theme"
    shutil.copytree(
        theme.REPOSITORY_ROOT
        / "changes/st-1703/self-hosted-minimum-start-v1/theme"
        / theme.THEME_SLUG,
        physical,
    )
    linked = tmp_path / "linked-theme"
    linked.symlink_to(physical, target_is_directory=True)
    monkeypatch.setattr(theme, "THEME_ROOT", linked)
    monkeypatch.setattr(theme, "MANIFEST_PATH", linked / "raos-assets.v1.json")
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_ROOT_INVALID"):
        theme.source_check()


def test_snapshot_detects_file_replacement_after_bounded_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    original = theme._read_regular_at
    changed = False

    def replacing_read(
        root_fd: int,
        relative: str,
        *,
        max_bytes: int = theme.MAX_FILE_BYTES,
        error_code: str = "THEME_FILE_INVALID",
    ) -> tuple[bytes, tuple[int, ...]]:
        nonlocal changed
        result = original(root_fd, relative, max_bytes=max_bytes, error_code=error_code)
        if relative == "assets/theme.css" and not changed:
            changed = True
            stylesheet = root / relative
            replacement = stylesheet.with_suffix(".css.replacement")
            replacement.write_bytes(result[0] + b"\n")
            os.replace(replacement, stylesheet)
        return result

    monkeypatch.setattr(theme, "_read_regular_at", replacing_read)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_INVENTORY_CHANGED"):
        theme.source_check()


def test_package_archives_each_validated_input_without_reopening(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    original = theme._read_regular_at
    reads: dict[str, int] = {}

    def counting_read(
        root_fd: int,
        relative: str,
        *,
        max_bytes: int = theme.MAX_FILE_BYTES,
        error_code: str = "THEME_FILE_INVALID",
    ) -> tuple[bytes, tuple[int, ...]]:
        reads[relative] = reads.get(relative, 0) + 1
        return original(root_fd, relative, max_bytes=max_bytes, error_code=error_code)

    monkeypatch.setattr(theme, "_read_regular_at", counting_read)
    assert theme.package_bytes()
    assert reads
    assert set(reads.values()) == {1}


def test_final_asset_is_validated_during_source_readiness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    manifest = _manifest(root)
    images = manifest["required_images"]
    assert isinstance(images, list) and isinstance(images[0], dict)
    image_path = images[0]["path"]
    assert isinstance(image_path, str)
    (root / image_path).write_bytes(b"not-a-webp")
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_FINAL_ASSET_INVALID"):
        theme.source_check()


def test_output_check_rejects_symlink_and_oversize_without_following(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    output = theme.OUTPUT_PATH
    _create_private_output_parent()
    victim = tmp_path / "victim.zip"
    victim.write_bytes(b"do-not-read-or-change")
    output.symlink_to(victim)
    assert theme.main(["--check"]) == 2
    assert victim.read_bytes() == b"do-not-read-or-change"
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out

    output.unlink()
    with output.open("wb") as stream:
        stream.truncate(theme.MAX_PACKAGE_BYTES + 1)
    output.chmod(theme.PRIVATE_OUTPUT_FILE_MODE)
    assert theme.main(["--check"]) == 2
    assert '"reason_code": "THEME_PACKAGE_DRIFT"' in capsys.readouterr().out


def test_package_write_fsyncs_created_parent_and_published_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_fsync = os.fsync
    original_replace = os.replace
    original_same_named_object = theme._same_named_object
    fsync_modes: list[int] = []
    events: list[str] = []

    def recording_fsync(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        fsync_modes.append(mode)
        events.append("file-fsync" if stat.S_ISREG(mode) else "directory-fsync")
        original_fsync(descriptor)

    def recording_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        events.append("replace")
        original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    def recording_same_named_object(
        details: os.stat_result,
        *,
        parent_fd: int,
        name: str,
        error_code: str,
    ) -> None:
        original_same_named_object(
            details,
            parent_fd=parent_fd,
            name=name,
            error_code=error_code,
        )
        if name == theme.OUTPUT_PATH.name:
            events.append("published-identity")

    monkeypatch.setattr(theme.os, "fsync", recording_fsync)
    monkeypatch.setattr(theme.os, "replace", recording_replace)
    monkeypatch.setattr(theme, "_same_named_object", recording_same_named_object)
    theme._write_package(payload)
    assert sum(stat.S_ISDIR(mode) for mode in fsync_modes) >= 2
    assert sum(stat.S_ISREG(mode) for mode in fsync_modes) >= 1
    assert events.index("file-fsync") < events.index("replace")
    published_checks = [
        index for index, event in enumerate(events) if event == "published-identity"
    ]
    final_directory_fsync = max(
        index for index, event in enumerate(events) if event == "directory-fsync"
    )
    assert len(published_checks) >= 2
    assert events.index("replace") < published_checks[0] < final_directory_fsync
    assert final_directory_fsync < published_checks[-1]
    assert events[-1] == "published-identity"


def test_package_write_atomically_replaces_only_private_regular_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    first = theme.package_bytes()
    theme._write_package(first)
    first_details = theme.OUTPUT_PATH.stat()

    second = first + b"bounded replacement"
    theme._write_package(second)
    second_details = theme.OUTPUT_PATH.stat()
    assert theme.OUTPUT_PATH.read_bytes() == second
    assert (second_details.st_dev, second_details.st_ino) != (
        first_details.st_dev,
        first_details.st_ino,
    )
    assert stat.S_IMODE(second_details.st_mode) == theme.PRIVATE_OUTPUT_FILE_MODE

    theme.OUTPUT_PATH.chmod(0o644)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)
    theme.OUTPUT_PATH.chmod(theme.PRIVATE_OUTPUT_FILE_MODE)
    hardlink = theme.OUTPUT_DIRECTORY / "package-hardlink.zip"
    os.link(theme.OUTPUT_PATH, hardlink)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)

    hardlink.unlink()
    theme.OUTPUT_PATH.unlink()
    victim = tmp_path / "package-victim.zip"
    victim.write_bytes(b"unchanged")
    theme.OUTPUT_PATH.symlink_to(victim)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)
    assert victim.read_bytes() == b"unchanged"

    theme.OUTPUT_PATH.unlink()
    theme.OUTPUT_PATH.mkdir(mode=theme.PRIVATE_OUTPUT_DIRECTORY_MODE)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)
    theme.OUTPUT_PATH.rmdir()
    os.mkfifo(theme.OUTPUT_PATH, mode=theme.PRIVATE_OUTPUT_FILE_MODE)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)
    theme.OUTPUT_PATH.unlink()
    with theme.OUTPUT_PATH.open("wb") as stream:
        stream.truncate(theme.MAX_PACKAGE_BYTES + 1)
    theme.OUTPUT_PATH.chmod(theme.PRIVATE_OUTPUT_FILE_MODE)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first)


def test_package_write_rejects_private_directory_drift_and_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    _create_private_output_parent()
    theme.OUTPUT_DIRECTORY.chmod(0o755)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)

    shutil.rmtree(theme.OUTPUT_DIRECTORY)
    outside = tmp_path / "outside-package-directory"
    outside.mkdir(mode=0o700)
    theme.OUTPUT_DIRECTORY.symlink_to(outside, target_is_directory=True)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert tuple(outside.iterdir()) == ()


def test_package_write_rejects_stale_preparing_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    _create_private_output_parent()
    preparing = theme.OUTPUT_DIRECTORY / f".{theme.OUTPUT_PATH.name}.preparing"
    preparing.write_bytes(b"stale")
    preparing.chmod(theme.PRIVATE_OUTPUT_FILE_MODE)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert preparing.read_bytes() == b"stale"
    assert not theme.OUTPUT_PATH.exists()


def test_package_write_rejects_output_path_contract_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    monkeypatch.setattr(
        theme,
        "OUTPUT_PATH",
        theme.OUTPUT_REPOSITORY_ROOT / "unreviewed" / "theme.zip",
    )
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert not (theme.OUTPUT_REPOSITORY_ROOT / "unreviewed").exists()


def test_package_write_rejects_final_directory_rename_after_descent_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_same_named_object = theme._same_named_object
    moved_name = "moved-theme-packages"
    renamed = False

    def rename_after_final_descent_check(
        details: os.stat_result,
        *,
        parent_fd: int,
        name: str,
        error_code: str,
    ) -> None:
        nonlocal renamed
        original_same_named_object(
            details,
            parent_fd=parent_fd,
            name=name,
            error_code=error_code,
        )
        if not renamed and name == theme._PRIVATE_OUTPUT_PARTS[-1]:
            os.rename(
                name,
                moved_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            renamed = True

    monkeypatch.setattr(theme, "_same_named_object", rename_after_final_descent_check)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert renamed is True
    assert not theme.OUTPUT_PATH.exists()
    moved = theme.OUTPUT_DIRECTORY.with_name(moved_name)
    assert moved.is_dir()
    assert tuple(moved.iterdir()) == ()


def test_package_write_rejects_final_directory_rename_after_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_fsync = os.fsync
    moved = theme.OUTPUT_DIRECTORY.with_name("moved-after-publication")
    renamed = False

    def rename_after_published_directory_fsync(descriptor: int) -> None:
        nonlocal renamed
        original_fsync(descriptor)
        if (
            not renamed
            and stat.S_ISDIR(os.fstat(descriptor).st_mode)
            and theme.OUTPUT_PATH.exists()
        ):
            theme.OUTPUT_DIRECTORY.rename(moved)
            renamed = True

    monkeypatch.setattr(theme.os, "fsync", rename_after_published_directory_fsync)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert renamed is True
    assert not theme.OUTPUT_PATH.exists()
    assert (moved / theme.OUTPUT_PATH.name).read_bytes() == payload


def test_package_write_rejects_same_inode_same_size_staging_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    hostile = bytes(len(payload))
    original_replace = os.replace

    def mutate_staging_before_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        descriptor = os.open(
            source,
            os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=src_dir_fd,
        )
        try:
            offset = 0
            while offset < len(hostile):
                written = os.write(descriptor, hostile[offset:])
                assert written > 0
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(theme.os, "replace", mutate_staging_before_replace)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert theme.OUTPUT_PATH.read_bytes() == hostile


def test_package_write_rechecks_existing_output_immediately_before_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    first = theme.package_bytes()
    theme._write_package(first)
    existing = theme.OUTPUT_PATH.stat()
    original_same_named_object = theme._same_named_object
    original_replace = os.replace
    swapped = False

    def swap_before_final_check(
        details: os.stat_result,
        *,
        parent_fd: int,
        name: str,
        error_code: str,
    ) -> None:
        nonlocal swapped
        if (
            not swapped
            and name == theme.OUTPUT_PATH.name
            and (details.st_dev, details.st_ino) == (existing.st_dev, existing.st_ino)
        ):
            attacker = ".hostile-output"
            descriptor = os.open(
                attacker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                theme.PRIVATE_OUTPUT_FILE_MODE,
                dir_fd=parent_fd,
            )
            try:
                assert os.write(descriptor, b"hostile-before-replace") == len(
                    b"hostile-before-replace"
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            original_replace(
                attacker,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            swapped = True
        original_same_named_object(
            details,
            parent_fd=parent_fd,
            name=name,
            error_code=error_code,
        )

    monkeypatch.setattr(theme, "_same_named_object", swap_before_final_check)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(first + b"replacement")
    assert swapped is True
    assert theme.OUTPUT_PATH.read_bytes() == b"hostile-before-replace"
    assert not (
        theme.OUTPUT_DIRECTORY / f".{theme.OUTPUT_PATH.name}.preparing"
    ).exists()


def test_package_write_rechecks_absent_output_immediately_before_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_stat = os.stat
    output_checks = 0

    def create_output_during_final_stat(
        path: str | bytes | int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal output_checks
        if (
            path == theme.OUTPUT_PATH.name
            and dir_fd is not None
            and follow_symlinks is False
        ):
            output_checks += 1
            if output_checks == 2:
                descriptor = os.open(
                    theme.OUTPUT_PATH.name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    theme.PRIVATE_OUTPUT_FILE_MODE,
                    dir_fd=dir_fd,
                )
                try:
                    assert os.write(descriptor, b"hostile-new-output") == len(
                        b"hostile-new-output"
                    )
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        return original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(theme.os, "stat", create_output_during_final_stat)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert output_checks == 2
    assert theme.OUTPUT_PATH.read_bytes() == b"hostile-new-output"
    assert not (
        theme.OUTPUT_DIRECTORY / f".{theme.OUTPUT_PATH.name}.preparing"
    ).exists()


def test_package_write_never_unlinks_replaced_staging_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_same_named_object = theme._same_named_object
    staging_name = f".{theme.OUTPUT_PATH.name}.preparing"
    replaced = False

    def replace_staging_before_identity_check(
        details: os.stat_result,
        *,
        parent_fd: int,
        name: str,
        error_code: str,
    ) -> None:
        nonlocal replaced
        if not replaced and name == staging_name:
            os.unlink(name, dir_fd=parent_fd)
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                theme.PRIVATE_OUTPUT_FILE_MODE,
                dir_fd=parent_fd,
            )
            try:
                assert os.write(descriptor, b"hostile-staging") == len(
                    b"hostile-staging"
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            replaced = True
        original_same_named_object(
            details,
            parent_fd=parent_fd,
            name=name,
            error_code=error_code,
        )

    monkeypatch.setattr(
        theme, "_same_named_object", replace_staging_before_identity_check
    )
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
    assert replaced is True
    assert (theme.OUTPUT_DIRECTORY / staging_name).read_bytes() == b"hostile-staging"
    assert not theme.OUTPUT_PATH.exists()


def test_package_write_rejects_post_replace_identity_swap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _isolated_theme(monkeypatch, tmp_path)
    _complete_assets(root)
    payload = theme.package_bytes()
    original_replace = os.replace

    def replacing_output(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        original_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        attacker = ".hostile-replacement"
        descriptor = os.open(
            attacker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            os.write(descriptor, b"hostile")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        original_replace(
            attacker,
            destination,
            src_dir_fd=dst_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(theme.os, "replace", replacing_output)
    with pytest.raises(theme.ThemeBuildFailure, match="THEME_PACKAGE_WRITE_FAILED"):
        theme._write_package(payload)
