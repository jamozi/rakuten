#!/usr/bin/env python3
"""Prepare/check a fixed owner-private local restoration; never invoke WordPress."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
OWNER = Path("/home/minami/rakuten")
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from raos.application.editorial.verified_incremental_preview_v1 import (  # noqa: E402
    LocalRestoration,
    build_local_restoration,
    verify_local_restoration,
)
from raos.application.editorial.verified_incremental_v1 import (  # noqa: E402
    IncrementalPublicationFailure,
    canonical,
    digest,
    fail,
    validate_hash,
)
from raos.application.finance.editorial_economics_v3 import (  # noqa: E402
    EditorialEconomicsV3Failure,
    read_private_bytes,
    read_private_json,
    write_private_bytes,
)


def owner_root() -> Path:
    if OWNER.is_symlink() or OWNER.resolve(strict=True) != OWNER:
        fail("OWNER_CHECKOUT_INVALID")
    return OWNER / ".secrets/wordpress-mcp"


def production_article_slugs() -> frozenset[str]:
    """Resolve unchanged URL identities without replaying in-flight draft content."""
    value: object = json.loads(
        (
            ROOT / "changes/wordpress-local-preview-v1/production-mapping.v1.json"
        ).read_bytes()
    )
    if type(value) is not dict:
        fail("RESTORE_MAPPING_INVALID")
    mapping = cast(dict[str, object], value)
    rows = mapping.get("articles")
    if (
        mapping.get("schema") != "RAOS_WORDPRESS_PRODUCTION_MAPPING_V1"
        or mapping.get("origin") != "https://kurashinoshirube.com"
        or type(rows) is not list
        or len(rows) != 10
    ):
        fail("RESTORE_MAPPING_INVALID")
    slugs: set[str] = set()
    for row_value in cast(list[object], rows):
        if type(row_value) is not dict:
            fail("RESTORE_MAPPING_INVALID")
        row = cast(dict[str, object], row_value)
        slug = row.get("production_slug")
        if (
            type(slug) is not str
            or slug in slugs
            or row.get("local_slug") != f"local-preview-{slug}"
        ):
            fail("RESTORE_MAPPING_INVALID")
        slugs.add(slug)
    return frozenset(slugs)


def expected_restoration(snapshot_name: str) -> LocalRestoration:
    snapshot = read_private_json(owner_root() / "incremental-snapshots", snapshot_name)
    result = build_local_restoration(
        snapshot,
        article_slugs=production_article_slugs(),
    )
    if snapshot_name != result.preparation["snapshot_name"]:
        fail("RESTORE_SNAPSHOT_NAME_INVALID")
    return result


def prepared_restoration(preparation_hash: str) -> tuple[Path, LocalRestoration]:
    root = owner_root() / f"local-restore-{validate_hash(preparation_hash)}"
    preparation = read_private_json(root, "preparation-binding.v1.json")
    snapshot_name = preparation.get("snapshot_name")
    if type(snapshot_name) is not str:
        fail("RESTORE_PREPARATION_INVALID")
    expected = expected_restoration(snapshot_name)
    expected_preparation = canonical(expected.preparation)
    if (
        digest(expected_preparation) != preparation_hash
        or canonical(preparation) != expected_preparation
        or read_private_bytes(root, "restoration-seed.v1.json") != expected.seed
    ):
        fail("RESTORE_PREPARATION_INVALID")
    for slug, body in expected.bodies.items():
        if read_private_bytes(root / "content", f"{slug}.html") != body:
            fail("RESTORE_BODY_INVALID")
    return root, expected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", allow_abbrev=False)
    prepare.add_argument("--snapshot-name", required=True)
    for name in ("check-inputs", "verify"):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--preparation-sha256", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "prepare":
            expected = expected_restoration(arguments.snapshot_name)
            binding = canonical(expected.preparation)
            preparation_hash = digest(binding)
            root = owner_root() / f"local-restore-{preparation_hash}"
            write_private_bytes(root, "restoration-seed.v1.json", expected.seed)
            for slug, body in expected.bodies.items():
                write_private_bytes(root / "content", f"{slug}.html", body)
            # Publish the binding last; an interrupted preparation is unusable.
            write_private_bytes(root, "preparation-binding.v1.json", binding)
            print(
                f"Local restoration prepared: 14 stored documents; SHA-256 {preparation_hash}"
            )
            print(f"Private preparation: {root}")
            print("Local restoration: NOT_EXECUTED; publication authority: false")
            return 0
        root, expected = prepared_restoration(arguments.preparation_sha256)
        if arguments.command == "verify":
            readback = read_private_json(root, "restoration-readback.v1.json")
            receipt = verify_local_restoration(expected, readback)
            write_private_bytes(root, "restoration-receipt.v1.json", canonical(receipt))
            print(
                "Local stored-field restoration: 14/14 verified; not an incremental preview pass"
            )
        else:
            print("Local restoration inputs: VERIFIED; restoration NOT_EXECUTED")
        return 0
    except (IncrementalPublicationFailure, EditorialEconomicsV3Failure) as error:
        sys.stderr.write(f"{error}\n")
        return 69
    except OSError, ValueError, TypeError:
        sys.stderr.write("RAOS_INCREMENTAL_RESTORE_INPUT_UNAVAILABLE\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
