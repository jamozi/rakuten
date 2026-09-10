#!/usr/bin/env python3
"""Build the adopted reader purchase-support articles and public CTA projection."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from raos.application.editorial.purchase_support import (  # noqa: E402
    compile_articles,
    resolve_product_media,
)

CATALOG_INPUT_PATH: Final = (
    ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
)
GUIDES_INPUT_PATH: Final = (
    ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
)
DOMAIN_INPUT_PATH: Final = ROOT / "python/raos/domain/editorial/purchase_support.py"
RENDERER_INPUT_PATH: Final = (
    ROOT / "python/raos/application/editorial/purchase_support.py"
)
COST_INPUT_PATH: Final = (
    ROOT / "python/raos/application/editorial/reader_running_cost.py"
)
MEDIA_INPUT_PATH: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/rakuten-product-media.json"
)
OFFICIAL_MEDIA_INPUT_PATH: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/roomba-mini-official.jpg"
)
MEDIA_EVIDENCE_INPUT_PATH: Final = (
    ROOT / "changes/wordpress-direct-publish-v1/official-media-sources.md"
)
TEMPLATE_INPUT_PATHS: Final = (
    ROOT
    / "changes/reader-purchase-support-v1/articles/countertop-dishwasher-for-small-households.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/lightweight-carry-on-suitcase-under-3kg.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/compact-robot-vacuum-shortlist.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/portable-power-station-guide.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/dishwasher-installation-measurement.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/dishwasher-water-supply-methods.html",
    ROOT
    / "changes/reader-purchase-support-v1/articles/dishwasher-detergent-guide.html",
    ROOT / "changes/reader-purchase-support-v1/articles/dishwasher-cleaning-guide.html",
    ROOT / "changes/reader-purchase-support-v1/articles/dishwasher-running-cost.html",
    ROOT / "changes/reader-purchase-support-v1/articles/kitchen.html",
    ROOT / "changes/reader-purchase-support-v1/articles/about-ad-policy.html",
    ROOT / "changes/reader-purchase-support-v1/articles/comparison-policy.html",
    ROOT / "changes/reader-purchase-support-v1/articles/privacy-policy.html",
)
ARTICLE_OUTPUT_PATHS: Final = (
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/countertop-dishwasher-for-small-households.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/lightweight-carry-on-suitcase-under-3kg.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/compact-robot-vacuum-shortlist.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/portable-power-station-guide.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/dishwasher-installation-measurement.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/dishwasher-water-supply-methods.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/dishwasher-detergent-guide.html",
    ROOT
    / "changes/wordpress-direct-publish-v1/articles/dishwasher-cleaning-guide.html",
    ROOT / "changes/wordpress-direct-publish-v1/articles/dishwasher-running-cost.html",
    ROOT / "changes/wordpress-direct-publish-v1/articles/kitchen.html",
    ROOT / "changes/wordpress-direct-publish-v1/articles/about-ad-policy.html",
    ROOT / "changes/wordpress-direct-publish-v1/articles/comparison-policy.html",
    ROOT / "changes/wordpress-direct-publish-v1/articles/privacy-policy.html",
)
RUNTIME_OUTPUT_PATH: Final = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json"
)
OUTPUT_PATHS: Final = (*ARTICLE_OUTPUT_PATHS, RUNTIME_OUTPUT_PATH)
TEST_PATHS: Final = (Path("tests/purchase_support"),)


def build():
    catalog = json.loads(CATALOG_INPUT_PATH.read_text())
    guides = json.loads(GUIDES_INPUT_PATH.read_text())
    templates = {p.stem: p.read_text() for p in TEMPLATE_INPUT_PATHS}
    media = resolve_product_media(
        catalog,
        json.loads(MEDIA_INPUT_PATH.read_text()),
        OFFICIAL_MEDIA_INPUT_PATH.read_bytes(),
    )
    articles, runtime = compile_articles(catalog, templates, guides, media)
    return {
        **{p: articles[p.stem] for p in ARTICLE_OUTPUT_PATHS},
        RUNTIME_OUTPUT_PATH: json.dumps(runtime, ensure_ascii=False, indent=2) + "\n",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build()
    if args.check:
        drift = [
            str(p.relative_to(ROOT))
            for p, s in outputs.items()
            if not p.exists() or p.read_text() != s
        ]
        if drift:
            raise SystemExit("purchase-support drift: " + ", ".join(drift))
    else:
        for p, s in outputs.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(s)
    print(
        f"purchase-support: {len(outputs) - 1} articles and public runtime {'verified' if args.check else 'generated'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
