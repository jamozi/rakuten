"""Local-only replay of images already present in an MCP baseline.

No product verification, owner attestation, affiliate API, or publication evidence
is created. The original bytes and source URLs remain in the owner-private path;
only identical public-image bytes are exposed by the isolated loopback gateway.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import html
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from raos.application.editorial.verified_incremental_preview_v1 import (  # noqa: E402
    MixedPreview,
    _snapshot_documents,
)
from raos.application.editorial.legacy_media_display_projection_v1 import (  # noqa: E402
    project_legacy_media,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    _Markup,
    canonical,
    digest,
    fail,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    read_private_json,
    write_private_bytes,
)

SCHEMA = "RAOS_WORDPRESS_BASELINE_IMAGE_REPLAY_V1"
PRIVATE = Path("/home/minami/rakuten/.secrets/wordpress-mcp")
MIRROR = PRIVATE / "baseline-preview-media"
PREFIX = "/raos-baseline-media/"
MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ImageResponse:
    url: str
    body: bytes
    content_type: str
    retrieved_at: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def validate_url(url: str) -> None:
    parts = urlsplit(url)
    if (
        not 1 <= len(url) <= 8192
        or parts.scheme != "https"
        or parts.netloc != "thumbnail.image.rakuten.co.jp"
        or parts.username
        or parts.password
        or parts.fragment
        or not parts.path.startswith("/@0_mall/")
        or re.search(r"[\x00-\x20\\]", url)
    ):
        fail("BASELINE_IMAGE_URL_NOT_SUPPORTED")


def fetch_image(url: str) -> ImageResponse:
    validate_url(url)
    try:
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "image/jpeg,image/png,image/gif,image/webp",
                "User-Agent": "RAOS-Baseline-Local-Replay/1.0",
            },
        )
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200 or response.url != url:
                fail("BASELINE_IMAGE_FETCH_FAILED")
            raw = response.read(MAX_BYTES + 1)
            content_type = response.headers.get_content_type()
        return ImageResponse(
            url, raw, content_type, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    except HTTPError, URLError, OSError, ValueError:
        fail("BASELINE_IMAGE_FETCH_FAILED")


def image_extension(raw: bytes, mime: str) -> str:
    if not 12 <= len(raw) <= MAX_BYTES:
        fail("BASELINE_IMAGE_BYTES_INVALID")
    if mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if mime == "image/gif" and raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if mime == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    fail("BASELINE_IMAGE_BYTES_INVALID")


def image_urls(markup: str) -> set[str]:
    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail("BASELINE_IMAGE_MARKUP_INVALID")
    urls = set()
    for element in parser.elements:
        if element.tag != "img":
            continue
        value = element.attrs.get("src")
        if not isinstance(value, str) or element.attrs.get("srcset"):
            fail("BASELINE_IMAGE_MARKUP_INVALID")
        if value.startswith("https://"):
            validate_url(value)
            urls.add(value)
        elif value.startswith("http:"):
            fail("BASELINE_IMAGE_URL_NOT_SUPPORTED")
    return urls


def project_body(raw: bytes, replacements: Mapping[str, str]) -> bytes:
    markup = raw.decode("utf-8", errors="strict")
    parser = _Markup(markup)
    parser.feed(markup)
    edits = []
    for element in parser.elements:
        if element.tag == "img" and element.attrs.get("src") in replacements:
            original = markup[element.start : element.opening_end]
            found = re.search(r'\bsrc=("|\')([^"\']+)\1', original)
            if found is None or html.unescape(found[2]) != element.attrs["src"]:
                fail("BASELINE_IMAGE_MARKUP_INVALID")
            url = element.attrs["src"]
            edits.append(
                (
                    element.start + found.start(2),
                    element.start + found.end(2),
                    replacements[url],
                )
            )
    for start, end, value in reversed(edits):
        markup = markup[:start] + value + markup[end:]
    return markup.encode()


def prepare_replay(
    snapshot: Mapping[str, object],
    mixed: MixedPreview,
    *,
    now: datetime,
    fetch: Callable[[str], ImageResponse] = fetch_image,
) -> tuple[MixedPreview, dict[str, bytes]]:
    documents = _snapshot_documents(snapshot)
    if (
        digest(canonical(snapshot).rstrip(b"\n"))
        != mixed.binding["source_snapshot_sha256"]
    ):
        fail("BASELINE_IMAGE_SNAPSHOT_MISMATCH")
    selected = set(cast(list[str], mixed.binding["selected_slugs"]))
    old = {slug: raw for slug, raw in mixed.articles.items() if slug not in selected}
    per_article = {}
    for slug, raw in old.items():
        if raw != cast(str, documents[slug]["block_markup"]).encode():
            fail("BASELINE_IMAGE_ORIGINAL_BODY_CHANGED")
        per_article[slug] = image_urls(raw.decode())
    urls = sorted(set().union(*per_article.values())) if per_article else []
    images, assets, replacements = {}, {}, {}
    for url in urls:
        captured = fetch(url)
        if captured.url != url:
            fail("BASELINE_IMAGE_RESPONSE_MISMATCH")
        try:
            retrieved = datetime.strptime(
                captured.retrieved_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=UTC)
        except ValueError:
            fail("BASELINE_IMAGE_TIME_INVALID")
        if not now - timedelta(minutes=5) <= retrieved <= now + timedelta(minutes=15):
            fail("BASELINE_IMAGE_TIME_INVALID")
        suffix = image_extension(captured.body, captured.content_type)
        name = digest(captured.body) + "." + suffix
        local = PREFIX + name
        replacements[url] = local
        assets[name] = captured.body
        # Key by source URL hash because different URLs may return identical bytes.
        images[digest(url.encode())] = {
            "source_url": url,
            "local_path": local,
            "content_sha256": digest(captured.body),
            "content_type": captured.content_type,
            "byte_count": len(captured.body),
            "retrieved_at": captured.retrieved_at,
            "article_slugs": sorted(
                slug for slug, sources in per_article.items() if url in sources
            ),
        }
    articles = {
        slug: project_body(raw, replacements) if slug in old else raw
        for slug, raw in mixed.articles.items()
    }
    receipt = {
        "schema": SCHEMA,
        "publication_profile": "verified-incremental",
        "publication_authority": False,
        "new_commerce_verified": False,
        "status": "BASELINE_PUBLIC_BYTES_REPLAYED_LOCALLY_ONLY",
        "source_snapshot_sha256": mixed.binding["source_snapshot_sha256"],
        "images": images,
        "articles": {
            slug: {
                "baseline_body_sha256": digest(old[slug]),
                "projected_body_sha256": digest(articles[slug]),
                "baseline_document_sha256": documents[slug]["content_sha256"],
            }
            for slug in sorted(old)
        },
    }
    binding = dict(mixed.binding)
    binding["baseline_media"] = receipt
    binding["article_body_sha256"] = {
        slug: digest(raw) for slug, raw in articles.items()
    }
    scope = deepcopy(cast(dict[str, Any], binding["incremental_scope"]))
    for row in scope["articles"]:
        inputs = [
            slug
            for slug, raw in mixed.articles.items()
            if row["display_projection"]["input_sha256"]
            in {digest(raw), digest(articles[slug])}
        ]
        proofs = [
            dict(project_legacy_media(articles[slug].decode(), row["article_id"]).proof)
            for slug in inputs
        ]
        if not proofs or any(proof != proofs[0] for proof in proofs):
            fail("BASELINE_DISPLAY_PROJECTION_SCOPE_INVALID")
        row["display_projection"] = proofs[0]
    binding["incremental_scope"] = scope
    return replace(mixed, articles=articles, binding=binding), assets


def write_assets(assets: Mapping[str, bytes]) -> None:
    # Original material remains 600/700. The separate mirror contains images
    # alone and is readable only through the local gateway's bounded mount.
    for name, raw in assets.items():
        if not re.fullmatch(r"[a-f0-9]{64}\.(?:jpg|png|gif|webp)", name) or name.split(
            "."
        )[0] != digest(raw):
            fail("BASELINE_IMAGE_ASSET_INVALID")
        write_private_bytes(PRIVATE / "baseline-image-originals", name, raw)
    if MIRROR.exists() and (
        MIRROR.is_symlink()
        or not MIRROR.is_dir()
        or MIRROR.stat().st_uid != os.geteuid()
    ):
        fail("BASELINE_IMAGE_MIRROR_INVALID")
    MIRROR.mkdir(mode=0o755, parents=False, exist_ok=True)
    for name, raw in assets.items():
        target = MIRROR / name
        if target.exists():
            info = target.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or target.read_bytes() != raw
            ):
                fail("BASELINE_IMAGE_MIRROR_CHANGED")
        else:
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)


def _asset_bytes(path: Path, private: bool) -> bytes:
    if path.resolve(strict=True) != path:
        fail("BASELINE_IMAGE_ASSET_INVALID")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or not 12 <= info.st_size <= MAX_BYTES
            or stat.S_IMODE(info.st_mode) != (0o600 if private else 0o444)
        ):
            fail("BASELINE_IMAGE_ASSET_INVALID")
        raw = os.read(descriptor, info.st_size + 1)
        if len(raw) != info.st_size:
            fail("BASELINE_IMAGE_ASSET_CHANGED")
        return raw
    finally:
        os.close(descriptor)


def validate_replay(fixture: Path, binding: Mapping[str, Any]) -> None:
    receipt = binding.get("baseline_media")
    if receipt is None:
        return
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != SCHEMA
        or receipt.get("publication_authority") is not False
        or receipt.get("new_commerce_verified") is not False
        or receipt.get("status") != "BASELINE_PUBLIC_BYTES_REPLAYED_LOCALLY_ONLY"
    ):
        fail("BASELINE_IMAGE_RECEIPT_INVALID")
    snapshot_hash = binding["source_snapshot_sha256"]
    snapshot = read_private_json(
        PRIVATE / "incremental-snapshots", f"live-{snapshot_hash}.v1.json"
    )
    if (
        digest(canonical(snapshot).rstrip(b"\n")) != snapshot_hash
        or receipt.get("source_snapshot_sha256") != snapshot_hash
    ):
        fail("BASELINE_IMAGE_SNAPSHOT_MISMATCH")
    responses = {}
    for entry in receipt["images"].values():
        name = entry["local_path"].removeprefix(PREFIX)
        if not re.fullmatch(r"[a-f0-9]{64}\.(?:jpg|png|gif|webp)", name):
            fail("BASELINE_IMAGE_ASSET_INVALID")
        raw = _asset_bytes(PRIVATE / "baseline-image-originals" / name, True)
        if (
            digest(raw) != entry["content_sha256"]
            or len(raw) != entry["byte_count"]
            or _asset_bytes(MIRROR / name, False) != raw
        ):
            fail("BASELINE_IMAGE_ASSET_CHANGED")
        responses[entry["source_url"]] = ImageResponse(
            entry["source_url"], raw, entry["content_type"], entry["retrieved_at"]
        )
    documents = _snapshot_documents(snapshot)
    selected = set(binding["selected_slugs"])
    raw_articles = {
        slug: (fixture / "articles" / f"{slug}.html").read_bytes()
        if slug in selected
        else cast(str, documents[slug]["block_markup"]).encode()
        for slug in binding["article_body_sha256"]
    }
    original = MixedPreview(b"", raw_articles, binding)
    captured_times = [
        datetime.strptime(row.retrieved_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        for row in responses.values()
    ]

    def captured_only(url: str) -> ImageResponse:
        if url not in responses:
            fail("BASELINE_IMAGE_RECEIPT_INCOMPLETE")
        return responses[url]

    replayed, _assets = prepare_replay(
        snapshot,
        original,
        now=min(captured_times) if captured_times else datetime.now(UTC),
        fetch=captured_only,
    )
    if (
        replayed.binding["baseline_media"] != receipt
        or replayed.binding["incremental_scope"] != binding["incremental_scope"]
    ) or any(
        replayed.articles[slug] != (fixture / "articles" / f"{slug}.html").read_bytes()
        for slug in raw_articles
    ):
        fail("BASELINE_IMAGE_PROJECTION_CHANGED")
