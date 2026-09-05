"""API-derived affiliate publication, without administrator measurement claims.

This is a separate receipt family, not a synthetic measurement activation.
Every validation replays the real V2 evidence and both materializations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from raos.application.editorial import rakuten_measurement_activation_v3 as common
from raos.application.editorial.editorial_portfolio_v2 import product_evidence_views_v2
from raos.application.editorial.editorial_portfolio_v3 import (
    load_editorial_portfolio_v3,
)
from raos.application.finance.editorial_economics_v3 import (
    canonical_json_bytes,
    read_private_bytes,
    write_private_bytes,
)

SCHEMA = "RAOS_RAKUTEN_STANDARD_API_PUBLICATION_V1"
BINDING_SCHEMA = "RAOS_WORDPRESS_STANDARD_API_BINDING_V1"


@dataclass(frozen=True)
class RakutenStandardApiOverlayV1:
    receipt_path: Path
    dry_run_sha256: str
    local_fixture_root: Path
    production_fixture_root: Path
    production_article_sha256: Mapping[str, str]
    binding: Mapping[str, object]


def _snapshot(
    repository_root: Path, *, require_recent: bool
) -> tuple[
    dict[str, object],
    dict[str, dict[str, bytes]],
    dict[str, dict[str, object]],
]:
    portfolio = load_editorial_portfolio_v3(repository_root)
    now = datetime.now(UTC)
    evidence = common.load_verified_v2_evidence(repository_root, now=now)
    views = product_evidence_views_v2(
        repository_root,
        now=now,
        require_fresh_set=True,
        require_verified_set=True,
    )
    if len(views) != 33 or set(views) != set(evidence.products):
        common.fail("RAOS_STANDARD_API_COVERAGE_INVALID")
    urls: dict[tuple[str, str, str], str] = {}
    for article in portfolio.articles:
        for cta in article.cta_bindings:
            item = views[cta.product_id].evidence
            if item is None:
                common.fail("RAOS_STANDARD_API_EVIDENCE_INVALID")
            urls[(article.article_id, cta.product_id, cta.placement)] = (
                item.destination_url
            )
    if len(urls) != 74:
        common.fail("RAOS_STANDARD_API_COVERAGE_INVALID")
    roots = dict(
        zip(
            ("local", "production"),
            common.default_v2_fixture_roots(repository_root),
            strict=True,
        )
    )
    sources = {
        mode: common.v2_materialization(
            repository_root=repository_root,
            fixture_root=root,
            mode=mode,
            portfolio=portfolio,
            verified_evidence=evidence,
        )
        for mode, root in roots.items()
    }
    outputs: dict[str, dict[str, bytes]] = {}
    article_hashes: dict[str, dict[str, str]] = {}
    for mode, source in sources.items():
        originals = cast(dict[str, bytes], source["sources"])
        rendered: dict[str, bytes] = {}
        for article in portfolio.articles:
            # The predecessor must already contain the exact API destinations.
            # Never turn an unrelated/tampered URL into a valid publication.
            for match in common.CTA_ANCHOR_RE.finditer(
                originals[article.article_id].decode()
            ):
                attrs = common.anchor_attributes(match.group(1))
                key = (
                    article.article_id,
                    attrs.get("data-raos-product-id", ""),
                    attrs.get("data-raos-placement", ""),
                )
                if attrs.get("href") != urls.get(key):
                    common.fail("RAOS_STANDARD_API_DESTINATION_MISMATCH")
            rendered[article.production_slug] = common.materialize_article_html(
                article,
                originals[article.article_id],
                urls,
                include_provider_slot=False,
            )
        outputs[mode] = rendered
        article_hashes[mode] = {
            slug: common.sha256_bytes(raw) for slug, raw in sorted(rendered.items())
        }
    common.require_v2_materializations_current(
        repository_root=repository_root,
        portfolio=portfolio,
        local_fixture_root=roots["local"],
        production_fixture_root=roots["production"],
        expected_evidence=evidence,
        expected_local=sources["local"],
        expected_production=sources["production"],
        require_recent=require_recent,
    )
    production = sources["production"]
    binding: dict[str, object] = {
        "schema": BINDING_SCHEMA,
        "link_mode": "standard-api",
        "measurement_collection_enabled": False,
        "portfolio_sha256": portfolio.source_sha256,
        "evidence_status_sha256": evidence.status_sha256,
        "local_receipt_sha256": common.sha256_bytes(
            cast(bytes, sources["local"]["receipt_raw"])
        ),
        "production_receipt_sha256": common.sha256_bytes(
            cast(bytes, production["receipt_raw"])
        ),
        "manufacturer_sales_state_sha256": evidence.manufacturer_sales_state_sha256,
        "manufacturer_sales_state_checked_at_utc": evidence.manufacturer_sales_state_checked_at_utc,
        "product_safety": dict(evidence.product_safety),
        "articles": article_hashes["production"],
        "products": {
            row["product_id"]: {
                "state": row["state"],
                "provider_binding_sha256": row["provider_binding_sha256"],
            }
            for row in cast(list[dict[str, str]], production["products"])
        },
        "media": production["media"],
        "completion": production["completion"],
    }
    document: dict[str, object] = {
        "schema": SCHEMA,
        "link_mode": "standard-api",
        "provenance": "API_VERIFIED",
        "measurement_collection_enabled": False,
        "owner_attested": False,
        "binding": binding,
        "local_article_sha256": article_hashes["local"],
        "posts_sha256": {
            mode: common.sha256_bytes(cast(bytes, source["posts_raw"]))
            for mode, source in sources.items()
        },
    }
    return document, outputs, sources


def materialize_standard_api_v1(
    *, repository_root: Path, private_root: Path, receipt_name: str
) -> Mapping[str, object]:
    """Write private API-only overlays after all product and safety gates pass."""
    common.owner_directory(private_root, exact_mode=0o700)
    document, outputs, sources = _snapshot(repository_root, require_recent=True)
    raw = canonical_json_bytes(document)
    digest = common.sha256_bytes(raw)
    for mode in ("local", "production"):
        common.write_overlay(
            private_root=private_root,
            directory_name=f"standard-api-{mode}-{digest}",
            posts_raw=cast(bytes, sources[mode]["posts_raw"]),
            articles=outputs[mode],
            receipt_raw=raw,
        )
    # Revalidate before committing the final receipt. Partial files confer no authority.
    current, _, _ = _snapshot(repository_root, require_recent=True)
    if canonical_json_bytes(current) != raw:
        common.fail("RAOS_STANDARD_API_SOURCE_CHANGED")
    write_private_bytes(private_root, receipt_name, raw)
    return {
        "schema": SCHEMA,
        "status": "VERIFIED",
        "receipt_sha256": digest,
        "link_mode": "standard-api",
        "product_count": 33,
        "image_count": 37,
        "cta_count": 74,
        "measurement_collection_enabled": False,
        "publication_authority": False,
    }


def validate_standard_api_v1(
    *, repository_root: Path, receipt_path: Path, require_recent: bool = True
) -> RakutenStandardApiOverlayV1:
    if not receipt_path.is_absolute():
        common.fail("RAOS_STANDARD_API_RECEIPT_INVALID")
    common.owner_directory(receipt_path.parent, exact_mode=0o700)
    raw = read_private_bytes(receipt_path.parent, receipt_path.name)
    document, outputs, sources = _snapshot(
        repository_root, require_recent=require_recent
    )
    if raw != canonical_json_bytes(document):
        common.fail("RAOS_STANDARD_API_RECEIPT_INVALID")
    digest = common.sha256_bytes(raw)
    roots: dict[str, Path] = {}
    for mode in ("local", "production"):
        root = common.owner_directory(
            receipt_path.parent / f"standard-api-{mode}-{digest}", exact_mode=0o700
        )
        articles = common.owner_directory(root / "articles", exact_mode=0o700)
        if (
            {path.name for path in root.iterdir()}
            != {"posts.json", "articles", "materialization-receipt.v3.json"}
            or {path.name for path in articles.iterdir()}
            != {f"{slug}.html" for slug in outputs[mode]}
            or read_private_bytes(root, "posts.json") != sources[mode]["posts_raw"]
            or read_private_bytes(root, "materialization-receipt.v3.json") != raw
        ):
            common.fail("RAOS_STANDARD_API_OVERLAY_INVALID")
        for slug, expected in outputs[mode].items():
            if read_private_bytes(articles, f"{slug}.html") != expected:
                common.fail("RAOS_STANDARD_API_OVERLAY_INVALID")
        roots[mode] = root
    current, _, _ = _snapshot(repository_root, require_recent=require_recent)
    if canonical_json_bytes(current) != raw:
        common.fail("RAOS_STANDARD_API_SOURCE_CHANGED")
    binding = dict(cast(Mapping[str, object], document["binding"]))
    binding["standard_api_receipt_sha256"] = digest
    return RakutenStandardApiOverlayV1(
        receipt_path=receipt_path,
        dry_run_sha256=digest,
        local_fixture_root=roots["local"],
        production_fixture_root=roots["production"],
        production_article_sha256=cast(Mapping[str, str], binding["articles"]),
        binding=binding,
    )
