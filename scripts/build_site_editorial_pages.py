#!/usr/bin/env python3
"""Rebuild article registry projections; no network or publication side effects."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from raos.application.editorial.site_editorial_pages import render_pages  # noqa: E402
from raos.application.editorial.home_product_media import (  # noqa: E402
    build_home_product_media,
    bind_home_product_media,
)

INPUT_PATHS = (
    Path("changes/site-improvements-20260913/entry-pages.v1.json"),
    Path("changes/wordpress-direct-publish-v1/articles.v1.json"),
    Path("changes/reader-purchase-support-v1/purchase-support.v1.json"),
    Path("python/raos/application/editorial/site_editorial_pages.py"),
    Path("python/raos/application/editorial/home_product_media.py"),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/rakuten-product-media.json"
    ),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/roomba-mini-official.jpg"
    ),
)
SOURCE_ARTICLE_PATHS = (
    Path(
        "changes/wordpress-direct-publish-v1/articles/carry-on-suitcase-comparison.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/carry-on-suitcase-under-100-seats.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/front-open-carry-on-suitcase-with-stopper.html"
    ),
    Path("changes/wordpress-direct-publish-v1/articles/solota-vs-rakua-mini-plus.html"),
    Path(
        "changes/wordpress-direct-publish-v1/articles/roomba-mini-vs-switchbot-k11-pro.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/anker-solix-c300-c800-c1000-differences.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/carry-on-suitcase-comparison.patch.json"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/carry-on-suitcase-under-100-seats.patch.json"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/lightweight-carry-on-suitcase-under-3kg.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/front-open-carry-on-suitcase-with-stopper.patch.json"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/countertop-dishwasher-for-small-households.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/solota-vs-rakua-mini-plus.patch.json"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/dishwasher-installation-measurement.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/dishwasher-water-supply-methods.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/dishwasher-detergent-guide.html"
    ),
    Path("changes/wordpress-direct-publish-v1/articles/dishwasher-cleaning-guide.html"),
    Path("changes/wordpress-direct-publish-v1/articles/dishwasher-running-cost.html"),
    Path(
        "changes/wordpress-direct-publish-v1/articles/compact-robot-vacuum-shortlist.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/roomba-mini-vs-switchbot-k11-pro.patch.json"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/portable-power-station-guide.html"
    ),
    Path(
        "changes/wordpress-direct-publish-v1/articles/anker-solix-c300-c800-c1000-differences.patch.json"
    ),
)
PURCHASE_RUNTIME_PATH = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json"
)
TEST_PATHS = (Path("tests/site_editorial_pages"),)
OUTPUT_PATHS = (
    Path("changes/wordpress-direct-publish-v1/articles/home.html"),
    Path("changes/wordpress-direct-publish-v1/articles/travel.html"),
    Path("changes/wordpress-direct-publish-v1/articles/cleaning.html"),
    Path("changes/wordpress-direct-publish-v1/articles/preparedness.html"),
    Path("changes/wordpress-direct-publish-v1/articles/categories.html"),
    Path("changes/wordpress-direct-publish-v1/articles/small-space.html"),
    Path("changes/wordpress-direct-publish-v1/articles/save-housework.html"),
    Path("changes/wordpress-direct-publish-v1/articles/without-installation.html"),
    Path("changes/wordpress-direct-publish-v1/articles/easy-maintenance.html"),
    Path("changes/wordpress-direct-publish-v1/articles/comfortable-travel.html"),
    Path("changes/wordpress-direct-publish-v1/articles/prepare-outage.html"),
    Path("changes/wordpress-direct-publish-v1/articles/purposes.html"),
    Path("changes/wordpress-direct-publish-v1/articles/guides.html"),
    Path("changes/wordpress-direct-publish-v1/articles/comparisons.html"),
    Path("changes/wordpress-direct-publish-v1/articles/updates.html"),
    Path("changes/site-improvements-20260913/kitchen-template.html"),
    Path("changes/site-improvements-20260913/registry-updates.json"),
    Path(
        "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/site-editorial-metadata.v1.json"
    ),
)


def build() -> dict[Path, str]:
    data, registry, catalog = [
        json.loads((ROOT / p).read_text()) for p in INPUT_PATHS[:3]
    ]
    bodies = {}
    for row in registry["articles"]:
        if row["post_type"] != "post":
            continue
        path = row.get("body_source")
        if path:
            bodies[row["slug"]] = (ROOT / path).read_text()
        elif row.get("patch_source"):
            bodies[row["slug"]] = (ROOT / row["patch_source"]).read_text()
    runtime = json.loads((ROOT / PURCHASE_RUNTIME_PATH).read_text())
    for entry in runtime["articles"]:
        slug = entry["slug"]
        if slug not in bodies or entry.get("kind") != "comparison":
            continue
        body = bodies[slug]
        # The purchase owner already verifies image identity, rights and source
        # hashes. Match its exact public body and exact bound media placeholder.
        if hashlib.sha256(body.encode()).hexdigest() != entry["body_sha256"]:
            raise ValueError("EDITORIAL_AD_RUNTIME_BODY_DRIFT: " + slug)
        for product_id, markup in entry.get("media", {}).items():
            placeholder = (
                '<div class="ps-product-media" data-ps-media-product="'
                + product_id
                + '"></div>'
            )
            if body.count(placeholder) == 1:
                bodies[slug] += markup
    home_image_style = data.get("home_image_style", "product")
    if home_image_style not in {"editorial", "product"}:
        raise ValueError("HOME_IMAGE_STYLE_INVALID")
    home_projection = None
    if home_image_style == "product":
        home_projection = build_home_product_media(
            catalog,
            data["home_product_media"],
            json.loads((ROOT / INPUT_PATHS[5]).read_text()),
            (ROOT / INPUT_PATHS[6]).read_bytes(),
        )
    pages, metadata, updates = render_pages(
        registry,
        catalog,
        data,
        bodies,
        home_media=home_projection["slots"] if home_projection else None,
    )
    home_payload = (
        bind_home_product_media(home_projection, pages["home"])
        if home_projection
        else None
    )
    result = {}
    for path in OUTPUT_PATHS:
        if path.suffix == ".html":
            slug = "kitchen" if path.stem == "kitchen-template" else path.stem
            result[path] = pages[slug]
        else:
            value = (
                updates
                if path.name == "registry-updates.json"
                else {
                    "schema": "RAOS_SITE_EDITORIAL_METADATA_V1",
                    "articles": metadata,
                    "home_product_media": home_payload,
                }
            )
            result[path] = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = []
    for path, content in build().items():
        target = ROOT / path
        if not target.exists() or target.read_text() != content:
            changed.append(str(path))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
    if args.check and changed:
        print("Editorial projections need regeneration: " + ", ".join(changed))
        return 1
    print(
        "Editorial page projections verified"
        if args.check
        else "Editorial page projections generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
