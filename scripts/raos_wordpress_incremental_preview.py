#!/usr/bin/env python3
"""Prepare owner-private mixed local drafts, never a publication manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from raos_wordpress_baseline_media import prepare_replay, write_assets  # noqa: E402

from raos.application.editorial.editorial_portfolio_v3 import (  # noqa: E402
    load_editorial_portfolio_v3,
)
from raos.application.editorial.verified_incremental_preview_v1 import (  # noqa: E402
    build_mixed_preview,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    IncrementalPublicationFailure,
    canonical,
    fail,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    read_private_json,
    write_private_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--articles", required=True)
    parser.add_argument("--materialize-baseline-images", action="store_true")
    parser.add_argument(
        "--update-policies",
        required=True,
        help="none, all, or exact comma-separated existing policy slugs",
    )
    parser.add_argument(
        "--home-mode",
        required=True,
        choices=("preserve-live-baseline", "shared-theme-candidate"),
    )
    arguments = parser.parse_args()
    try:
        owner = Path("/home/minami/rakuten")
        if owner.is_symlink() or owner.resolve(strict=True) != owner:
            fail("OWNER_CHECKOUT_INVALID")
        snapshot = read_private_json(
            owner / ".secrets/wordpress-mcp/incremental-snapshots",
            arguments.snapshot_name,
        )
        portfolio = load_editorial_portfolio_v3(ROOT)
        article_ids = {a.production_slug: a.article_id for a in portfolio.articles}
        selected = frozenset(
            article_ids
            if arguments.articles == "all"
            else arguments.articles.split(",")
        )
        fixture = ROOT / "changes/wordpress-local-preview-v1/fixtures"
        posts = json.loads((fixture / "posts.json").read_text())
        pages = json.loads((fixture / "production-pages.json").read_text())
        policy_slugs = {row["slug"] for row in pages["pages"]}
        updated_policies = frozenset(
            policy_slugs
            if arguments.update_policies == "all"
            else ()
            if arguments.update_policies == "none"
            else arguments.update_policies.split(",")
        )
        result = build_mixed_preview(
            snapshot=snapshot,
            source_posts=posts,
            source_articles={
                slug: (fixture / "articles" / f"{slug}.html").read_bytes()
                for slug in article_ids
            },
            selected_slugs=selected,
            article_ids_by_slug=article_ids,
            source_pages=pages,
            source_page_bodies={
                slug: (fixture / "production-pages" / f"{slug}.html").read_bytes()
                for slug in policy_slugs
            },
            updated_policy_slugs=updated_policies,
            home_mode=arguments.home_mode,
        )
        if arguments.materialize_baseline_images:
            from datetime import UTC, datetime

            result, assets = prepare_replay(snapshot, result, now=datetime.now(UTC))
            write_assets(assets)
        binding_raw = canonical(result.binding)
        binding_hash = hashlib.sha256(binding_raw).hexdigest()
        output = (
            owner / ".secrets/wordpress-mcp" / f"incremental-preview-{binding_hash}"
        )
        write_private_bytes(output, "posts.json", result.posts)
        for slug, raw in result.articles.items():
            write_private_bytes(output / "articles", f"{slug}.html", raw)
        if result.pages is not None:
            write_private_bytes(output, "pages.json", result.pages)
        for slug, raw in (result.page_bodies or {}).items():
            write_private_bytes(output / "pages", f"{slug}.html", raw)
        for slug, raw in (result.baseline_pages or {}).items():
            write_private_bytes(output / "baseline-pages", f"{slug}.html", raw)
        if result.seed_metadata is not None:
            write_private_bytes(output, "seed-metadata.v1.json", result.seed_metadata)
        write_private_bytes(output, "preparation-binding.v1.json", binding_raw)
        print(
            f"Mixed local preview: {len(result.articles)} articles; revised drafts: {len(selected)}"
        )
        print(f"Fixture root: {output}")
        print(f"Preparation SHA-256: {binding_hash}")
        if arguments.materialize_baseline_images:
            print(
                f"Baseline image bytes replayed locally: {len(assets)}; new commerce verification: NOT_PERFORMED"
            )
        states = cast(dict[str, str], result.binding["article_states"])
        for slug, state in sorted(states.items()):
            print(f"{slug}: {state}")
        print(f"Public metadata fields: {result.binding['metadata_status']}")
        print(f"Home: {result.binding['home_state']}")
        for slug, state in sorted(
            cast(dict[str, str], result.binding["policy_states"]).items()
        ):
            print(f"{slug}: {state}")
        print("Front-page setting, author and featured-media metadata: NOT_VERIFIED")
        print(
            "Publication status: NOT_VERIFIED_FOR_PUBLICATION; production writes: NOT_EXECUTED"
        )
        return 0
    except (IncrementalPublicationFailure, EditorialEconomicsV3Failure) as error:
        sys.stderr.write(f"{error}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
