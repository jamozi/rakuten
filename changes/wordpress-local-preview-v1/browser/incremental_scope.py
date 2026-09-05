#!/usr/bin/env python3
"""Replay a private, hash-bound mixed overlay into URL-free browser expectations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from raos_wordpress_baseline_media import validate_replay  # noqa: E402

from raos.application.editorial.verified_incremental_preview_v1 import (  # noqa: E402
    derive_editorial_browser_expectations,
)
from raos.application.editorial.legacy_media_display_projection_v1 import (  # noqa: E402
    project_legacy_media,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    IncrementalPublicationFailure,
    _Markup,
)


class ScopeFailure(ValueError):
    pass


def reject() -> None:
    raise ScopeFailure("RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID")


def read_private(path: Path) -> bytes:
    if not path.is_absolute() or path.resolve(strict=True) != path:
        reject()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or not 1 <= before.st_size <= 4 * 1024 * 1024
        ):
            reject()
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or (
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            reject()
        return raw
    finally:
        os.close(descriptor)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def derive_article(markup: str, article_id: str) -> dict[str, object]:
    display = project_legacy_media(markup, article_id)
    markup = display.markup
    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        reject()
    products, images, ctas = [], [], []
    for element in parser.elements:
        attrs = element.attrs
        classes = set((attrs.get("class") or "").split())
        if element.tag == "article" and "product-profile" in classes:
            products.append(attrs.get("data-raos-product-id"))
        if element.tag == "img" and (
            "data-raos-product-image-id" in attrs or element.product
        ):
            images.append(attrs.get("data-raos-product-image-id") or element.product)
        if element.tag == "a" and (
            "data-raos-placement" in attrs
            or "raos-cta" in classes
            or urlsplit(attrs.get("href") or "").hostname == "hb.afl.rakuten.co.jp"
        ):
            ctas.append(
                {
                    "cta_id": attrs.get("data-raos-cta-id"),
                    "product_id": attrs.get("data-raos-product-id") or element.product,
                    "placement": attrs.get("data-raos-placement"),
                }
            )
    if any(type(value) is not str for value in products + images):
        reject()
    return {
        "article_id": article_id,
        "editorial_product_ids": sorted(products),
        "expected_cta_ids": sorted(
            row["cta_id"] for row in ctas if row["cta_id"] is not None
        ),
        "expected_ctas": ctas,
        "expected_image_product_ids": sorted(images),
        "display_projection": dict(display.proof),
        **derive_editorial_browser_expectations(markup),
    }


def load_scope(fixture_root: Path, inventory: dict[str, object]) -> dict[str, object]:
    if (
        not fixture_root.is_absolute()
        or fixture_root.resolve(strict=True) != fixture_root
        or stat.S_IMODE(fixture_root.stat().st_mode) != 0o700
    ):
        reject()
    raw = read_private(fixture_root / "preparation-binding.v1.json")
    binding_hash = digest(raw)
    if fixture_root.name != f"incremental-preview-{binding_hash}":
        reject()
    binding = json.loads(raw)
    if (
        binding.get("schema") != "RAOS_WORDPRESS_MIXED_PREVIEW_PREPARATION_V1"
        or binding.get("publication_profile") != "verified-incremental"
        or binding.get("link_mode") != "standard-api"
        or binding.get("publication_authority") is not False
        or binding.get("status") != "NOT_VERIFIED_FOR_PUBLICATION"
        or binding.get("selected_commerce") != "OMITTED_NOT_VERIFIED"
        or re.fullmatch("[a-f0-9]{64}", binding.get("source_snapshot_sha256", ""))
        is None
    ):
        reject()
    validate_replay(fixture_root, binding)
    article_ids = {
        row["production_path"].strip("/"): row["article_id"]
        for row in inventory["surfaces"]
        if row.get("kind") == "article"
    }
    selected = binding.get("selected_slugs")
    if (
        len(article_ids) != 10
        or type(selected) is not list
        or not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= set(article_ids)
        or set(binding.get("article_body_sha256", {})) != set(article_ids)
        or set(binding.get("baseline_document_sha256", {})) != set(article_ids)
        or set(binding.get("article_states", {})) != set(article_ids)
    ):
        reject()
    posts_raw = read_private(fixture_root / "posts.json")
    if digest(posts_raw) != binding.get("posts_sha256"):
        reject()
    posts = json.loads(posts_raw)
    if (
        posts.get("schema") != "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
        or len(posts.get("posts", [])) != 10
        or {row.get("slug") for row in posts["posts"]}
        != {f"local-preview-{slug}" for slug in article_ids}
        or any(
            row.get("content_file")
            != f"articles/{row['slug'].removeprefix('local-preview-')}.html"
            for row in posts["posts"]
        )
    ):
        reject()
    scope_rows = []
    for slug, article_id in sorted(article_ids.items()):
        if (
            binding["article_states"][slug]
            != (
                "REVISED_DRAFT_NOT_VERIFIED"
                if slug in selected
                else "UNCHANGED_LIVE_CONTENT"
            )
            or re.fullmatch("[a-f0-9]{64}", binding["baseline_document_sha256"][slug])
            is None
        ):
            reject()
        body_raw = read_private(fixture_root / "articles" / f"{slug}.html")
        if digest(body_raw) != binding["article_body_sha256"][slug]:
            reject()
        row = derive_article(body_raw.decode("utf-8", errors="strict"), article_id)
        if slug in selected and (
            row["expected_ctas"] or row["expected_image_product_ids"]
        ):
            reject()  # This preparation contract cannot supply verified commerce.
        scope_rows.append(row)
    scope = {
        "schema": "RAOS_WORDPRESS_INCREMENTAL_BROWSER_SCOPE_V1",
        "publication_profile": "verified-incremental",
        "link_mode": "standard-api",
        "selected_article_ids": sorted(article_ids[slug] for slug in selected),
        "articles": scope_rows,
    }
    if scope != binding.get("incremental_scope"):
        reject()
    if "seed_metadata_sha256" in binding:
        metadata_raw = read_private(fixture_root / "seed-metadata.v1.json")
        metadata = json.loads(metadata_raw)
        if (
            digest(metadata_raw) != binding["seed_metadata_sha256"]
            or metadata.get("schema") != "RAOS_WORDPRESS_MIXED_PREVIEW_SEED_METADATA_V1"
            or metadata.get("publication_profile") != "verified-incremental"
            or metadata.get("publication_authority") is not False
            or metadata.get("status") != "VERIFIED_FIELDS_ONLY"
            or binding.get("metadata_status") != "VERIFIED_FIELDS_ONLY"
            or binding.get("metadata_blockers") != []
            or metadata.get("policy_states") != binding.get("policy_states")
            or metadata.get("home_state") != binding.get("home_state")
        ):
            reject()
        policy_slugs = {
            row["production_path"].strip("/")
            for row in inventory["surfaces"]
            if row.get("kind") == "policy"
        }
        if (
            len(policy_slugs) != 3
            or set(binding.get("page_body_sha256", {})) != policy_slugs
            or set(binding.get("baseline_page_sha256", {})) != policy_slugs | {"home"}
            or set(metadata.get("documents", {}))
            != set(article_ids) | policy_slugs | {"home"}
        ):
            reject()
        page_raw = read_private(fixture_root / "pages.json")
        if digest(page_raw) != binding.get("pages_sha256"):
            reject()
        pages = json.loads(page_raw)
        if (
            pages.get("schema") != "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
            or len(pages.get("pages", [])) != 3
            or {row.get("slug") for row in pages["pages"]} != policy_slugs
            or any(
                row.get("content_file") != f"pages/{row['slug']}.html"
                for row in pages["pages"]
            )
        ):
            reject()
        for slug in policy_slugs:
            if (
                digest(read_private(fixture_root / "pages" / f"{slug}.html"))
                != binding["page_body_sha256"][slug]
            ):
                reject()
        for slug in policy_slugs | {"home"}:
            if (
                digest(read_private(fixture_root / "baseline-pages" / f"{slug}.html"))
                != binding["baseline_page_sha256"][slug]
            ):
                reject()
    scope["preparation_binding_sha256"] = binding_hash
    return scope


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--fixture-root", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        inventory = json.loads(
            (
                ROOT
                / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
            ).read_text()
        )
        scope = load_scope(arguments.fixture_root, inventory)
        print(
            json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        return 0
    except (
        ScopeFailure,
        IncrementalPublicationFailure,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    ):
        sys.stderr.write("RAOS_WORDPRESS_INCREMENTAL_SCOPE_INVALID\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
