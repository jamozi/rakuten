#!/usr/bin/env python3
"""Prepare owner-private mixed local drafts, never a publication manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import UTC, datetime
from collections.abc import Mapping
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


def page_overrides_for_preview(
    arguments: argparse.Namespace, *, root: Path = ROOT
) -> dict[str, dict[str, object]]:
    """Resolve explicit source pages; a supplied candidate owns the exact set."""
    import raos_reader_release_pages as reader

    include_home = getattr(arguments, "include_home", False) or getattr(
        arguments, "home_page", False
    )
    reader_privacy = getattr(arguments, "reader_privacy", False)
    selected = getattr(arguments, "reader_pages", None)
    hubs = [] if selected is None else selected.split(",")
    candidate_path = getattr(arguments, "candidate", None)
    if candidate_path is not None:
        manifest = read_private_json(Path(candidate_path), "manifest.v1.json")
        shared = manifest.get("shared_artifacts", {})
        targets = manifest.get("reader_pages", {})
        if (
            not isinstance(shared, dict)
            or not isinstance(targets, dict)
            or not set(targets) <= reader.HUB_SLUGS | {"privacy-policy"}
            or not set(targets) <= set(shared)
        ):
            fail("PREVIEW_READER_PAGE_SELECTION_INVALID")
        include_home = "home" in shared
        reader_privacy = "privacy-policy" in targets
        hubs = sorted(set(targets) & reader.HUB_SLUGS)
    pages = []
    if include_home:
        pages.append(reader.load_home_page(root))
    if reader_privacy:
        pages.append(reader.load_reader_privacy_page(root))
    if hubs:
        pages.extend(reader.select_hub_pages(root, hubs))
    return {page.production_slug: page.document() for page in pages}


def article_bodies_for_preview(
    arguments: argparse.Namespace,
    *,
    snapshot: Mapping[str, object],
    selected: frozenset[str],
    source_articles: Mapping[str, bytes],
) -> dict[str, bytes]:
    """Seed the final reviewed markup, including rendered reader components."""
    result = dict(source_articles)
    candidate_path = getattr(arguments, "candidate", None)
    if candidate_path is None:
        return result
    from raos_wordpress_incremental_publication import prepare_candidate

    prepared = prepare_candidate(candidate_path, now=datetime.now(UTC))
    if (
        prepared.snapshot != snapshot
        or {row["slug"] for row in prepared.manifest["articles"]} != selected
    ):
        fail("PREVIEW_CANDIDATE_BINDING")
    for row in prepared.manifest["articles"]:
        result[row["slug"]] = prepared.artifacts[row["local_artifact"]["key"]]
    return result


def create_preview(arguments: argparse.Namespace) -> Path:
    """Materialize a new mixed preview, preserving already-bound fixture directories."""
    owner = Path("/home/minami/rakuten")
    if owner.is_symlink() or owner.resolve(strict=True) != owner:
        fail("OWNER_CHECKOUT_INVALID")
    snapshot = read_private_json(
        owner / ".secrets/wordpress-mcp/incremental-snapshots",
        arguments.snapshot_name,
    )
    portfolio = load_editorial_portfolio_v3(ROOT)
    article_ids = {a.production_slug: a.article_id for a in portfolio.articles}
    article_selection = getattr(arguments, "articles", None)
    selected = frozenset(
        article_ids
        if article_selection == "all"
        else ()
        if article_selection in (None, "", "none")
        else article_selection.split(",")
    )
    page_overrides = page_overrides_for_preview(arguments)
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
        source_articles=article_bodies_for_preview(
            arguments,
            snapshot=snapshot,
            selected=selected,
            source_articles={
                slug: (fixture / "articles" / f"{slug}.html").read_bytes()
                for slug in article_ids
            },
        ),
        selected_slugs=selected,
        article_ids_by_slug=article_ids,
        source_pages=pages,
        source_page_bodies={
            slug: (fixture / "production-pages" / f"{slug}.html").read_bytes()
            for slug in policy_slugs
        },
        updated_policy_slugs=updated_policies,
        home_mode=arguments.home_mode,
        page_overrides=page_overrides,
    )
    if arguments.materialize_baseline_images:
        from datetime import UTC, datetime

        result, assets = prepare_replay(snapshot, result, now=datetime.now(UTC))
        write_assets(assets)
    binding_raw = canonical(result.binding)
    binding_hash = hashlib.sha256(binding_raw).hexdigest()
    output = owner / ".secrets/wordpress-mcp" / f"incremental-preview-{binding_hash}"
    if (output / "preparation-binding.v1.json").exists():
        if (output / "preparation-binding.v1.json").read_bytes() != binding_raw:
            fail("PREVIEW_BINDING_CHANGED")
        return output
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
    if page_overrides:
        print("Explicit reader pages: " + ", ".join(sorted(page_overrides)))
    print("Front-page setting, author and featured-media metadata: NOT_VERIFIED")
    print(
        "Publication status: NOT_VERIFIED_FOR_PUBLICATION; production writes: NOT_EXECUTED"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument(
        "--articles",
        help="all or exact comma-separated article slugs; omit for page-only",
    )
    parser.add_argument(
        "--include-home", "--home-page", action="store_true", dest="include_home"
    )
    parser.add_argument(
        "--reader-pages", help="exact comma-separated registered hub slugs"
    )
    parser.add_argument("--reader-privacy", action="store_true")
    parser.add_argument(
        "--candidate",
        type=Path,
        help="use the existing candidate's exact page selection",
    )
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
        create_preview(arguments)
        return 0
    except (
        IncrementalPublicationFailure,
        EditorialEconomicsV3Failure,
        ValueError,
    ) as error:
        sys.stderr.write(f"{error}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
