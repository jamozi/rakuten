#!/usr/bin/env python3
"""Build the additive Editorial V3 portfolio and navigation contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Final, NoReturn, cast


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.raos_build_core import atomic_write, canonical_json_bytes  # noqa: E402


GENERATOR_PATH: Final = Path("scripts/build_editorial_portfolio_v3.py")
INPUT_PORTFOLIO_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
INPUT_IDENTITIES_PATH: Final = Path(
    "changes/editorial-portfolio-v3/editorial-identities.v1.json"
)
PARSER_BOUNDARY_PATH: Final = Path(
    "changes/editorial-portfolio-v3/rakuten-parser-boundary.v1.json"
)
ARTICLE_CONTENT_PATHS: Final = (
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-comparison.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "portable-power-station-guide.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "anker-solix-c300-c800-c1000-differences.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "countertop-dishwasher-for-small-households.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "compact-robot-vacuum-shortlist.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-under-100-seats.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "lightweight-carry-on-suitcase-under-3kg.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "front-open-carry-on-suitcase-with-stopper.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "roomba-mini-vs-switchbot-k11-pro.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "solota-vs-rakua-mini-plus.html"
    ),
)
RUNTIME_PATHS: Final = (
    Path("python/raos/application/editorial/editorial_portfolio_v3.py"),
    Path("python/raos/application/finance/editorial_economics_v3.py"),
    Path("scripts/raos_editorial_economics_v3.py"),
    Path("changes/editorial-portfolio-v3/README.md"),
)
OUTPUT_PATHS: Final = (
    Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json"),
    Path("changes/editorial-portfolio-v3/generated/navigation.v3.json"),
)
TEST_PATHS: Final = (Path("tests/editorial_portfolio_v3"),)

ARTICLE_CODE_PATTERN: Final = "a{position:02d}"
PRODUCT_CODE_PATTERN: Final = "p{position:02d}"
PLACEMENTS: Final = (
    ("product_card", "card"),
    ("final_summary", "final"),
)


class EditorialV3BuildFailure(RuntimeError):
    """A stable, non-sensitive generator failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialV3BuildFailure(code) from None


def _read_json(relative: Path) -> dict[str, object]:
    try:
        raw = (REPOSITORY_ROOT / relative).read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except OSError, UnicodeError, json.JSONDecodeError:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return cast(dict[str, object], value)


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return cast(dict[str, object], value)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    result: list[dict[str, object]] = []
    for row in cast(list[object], value):
        result.append(_mapping(row))
    return result


def _text(value: object) -> str:
    if type(value) is not str or value != value.strip() or not value:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return value


def _positive_integer(value: object) -> int:
    if type(value) is not int or value <= 0:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return value


def _content_sha256(reference: object) -> str:
    relative = Path(_text(reference))
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative not in ARTICLE_CONTENT_PATHS
    ):
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    try:
        content = (REPOSITORY_ROOT / relative).read_bytes()
    except OSError:
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    if not content:
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    return hashlib.sha256(content).hexdigest()


def _validate_parser_boundary() -> None:
    boundary = _read_json(PARSER_BOUNDARY_PATH)
    if boundary != {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_BOUNDARY_V1",
        "version": "1.0.0",
        "state": "DISABLED_UNTIL_VERIFIED_SAMPLE_PROFILE_BOUND",
        "authority": "OWNER_PRIVATE_SANITIZED_SAMPLE_REQUIRED",
        "tracked_live_column_names": [],
        "tracked_status_values": [],
        "rules": {
            "automatic_column_guessing": False,
            "automatic_status_guessing": False,
            "direct_requires_verified_measurement_column": True,
            "estimated_never_promoted_to_direct": True,
            "unmatched_measurement_id": "UNATTRIBUTED",
            "dry_run_source_hash_must_equal_commit_source_hash": True,
            "provider_totals_must_reconcile_before_commit": True,
            "raw_rows_remain_owner_private": True,
        },
    }:
        _fail("RAOS_EDITORIAL_V3_PARSER_BOUNDARY_INVALID")


def build_documents() -> tuple[dict[str, object], dict[str, object]]:
    v2 = _read_json(INPUT_PORTFOLIO_PATH)
    identities = _read_json(INPUT_IDENTITIES_PATH)
    _validate_parser_boundary()
    if v2.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V2":
        _fail("RAOS_EDITORIAL_V3_PREDECESSOR_INVALID")
    if identities.get("schema") != "RAOS_EDITORIAL_V3_IDENTITIES_V1":
        _fail("RAOS_EDITORIAL_V3_IDENTITIES_INVALID")

    v2_articles = _rows(v2.get("articles"))
    v2_products = _rows(v2.get("products"))
    identity_articles = _rows(identities.get("articles"))
    identity_products = _rows(identities.get("products"))
    cluster_rows = _rows(identities.get("clusters"))
    if len(v2_articles) != 10 or len(v2_products) != 32:
        _fail("RAOS_EDITORIAL_V3_PREDECESSOR_CARDINALITY_INVALID")
    if len(identity_articles) != 10 or len(identity_products) != 32:
        _fail("RAOS_EDITORIAL_V3_IDENTITIES_CARDINALITY_INVALID")

    v2_article_ids = [_text(row.get("article_id")) for row in v2_articles]
    v2_product_ids = [_text(row.get("product_id")) for row in v2_products]
    article_identity_by_id = {
        _text(row.get("article_id")): row for row in identity_articles
    }
    product_identity_by_id = {
        _text(row.get("product_id")): row for row in identity_products
    }
    if set(article_identity_by_id) != set(v2_article_ids):
        _fail("RAOS_EDITORIAL_V3_ARTICLE_IDENTITY_COVERAGE_INVALID")
    if set(product_identity_by_id) != set(v2_product_ids):
        _fail("RAOS_EDITORIAL_V3_PRODUCT_IDENTITY_COVERAGE_INVALID")

    cluster_by_id: dict[str, dict[str, object]] = {}
    for expected_order, cluster in enumerate(cluster_rows, start=1):
        if set(cluster) != {"cluster_id", "category_label", "home_order"}:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        cluster_id = _text(cluster["cluster_id"])
        if cluster_id in cluster_by_id:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        if _positive_integer(cluster["home_order"]) != expected_order:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        _text(cluster["category_label"])
        cluster_by_id[cluster_id] = cluster
    if set(cluster_by_id) != {"mobility", "household", "preparedness"}:
        _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")

    product_code_by_id: dict[str, str] = {}
    v3_products: list[dict[str, object]] = []
    for position, product in enumerate(v2_products, start=1):
        product_id = _text(product.get("product_id"))
        identity = product_identity_by_id[product_id]
        if set(identity) != {"product_id", "product_code"}:
            _fail("RAOS_EDITORIAL_V3_PRODUCT_IDENTITY_INVALID")
        product_code = _text(identity["product_code"])
        if product_code != PRODUCT_CODE_PATTERN.format(position=position):
            _fail("RAOS_EDITORIAL_V3_PRODUCT_CODE_INVALID")
        product_code_by_id[product_id] = product_code
        v3_products.append({**product, "product_code": product_code})
    if len(set(product_code_by_id.values())) != len(product_code_by_id):
        _fail("RAOS_EDITORIAL_V3_PRODUCT_CODE_INVALID")

    article_code_by_id: dict[str, str] = {}
    article_cluster_by_id: dict[str, str] = {}
    for position, article_id in enumerate(v2_article_ids, start=1):
        identity = article_identity_by_id[article_id]
        if set(identity) != {
            "article_id",
            "article_code",
            "cluster_id",
            "home_order",
            "related_article_ids",
        }:
            _fail("RAOS_EDITORIAL_V3_ARTICLE_IDENTITY_INVALID")
        article_code = _text(identity["article_code"])
        if article_code != ARTICLE_CODE_PATTERN.format(position=position):
            _fail("RAOS_EDITORIAL_V3_ARTICLE_CODE_INVALID")
        cluster_id = _text(identity["cluster_id"])
        if cluster_id not in cluster_by_id:
            _fail("RAOS_EDITORIAL_V3_ARTICLE_CLUSTER_INVALID")
        article_code_by_id[article_id] = article_code
        article_cluster_by_id[article_id] = cluster_id
    if len(set(article_code_by_id.values())) != len(article_code_by_id):
        _fail("RAOS_EDITORIAL_V3_ARTICLE_CODE_INVALID")

    cluster_size = {
        cluster_id: sum(
            1 for value in article_cluster_by_id.values() if value == cluster_id
        )
        for cluster_id in cluster_by_id
    }

    home_orders: dict[str, set[int]] = {key: set() for key in cluster_by_id}
    v3_articles: list[dict[str, object]] = []
    navigation_articles: list[dict[str, object]] = []
    for article in v2_articles:
        article_id = _text(article.get("article_id"))
        identity = article_identity_by_id[article_id]
        article_code = article_code_by_id[article_id]
        cluster_id = article_cluster_by_id[article_id]
        cluster = cluster_by_id[cluster_id]
        home_order = _positive_integer(identity["home_order"])
        if home_order in home_orders[cluster_id]:
            _fail("RAOS_EDITORIAL_V3_HOME_ORDER_INVALID")
        home_orders[cluster_id].add(home_order)
        related = [
            _text(value)
            for value in cast(list[object], identity["related_article_ids"])
        ]
        same_cluster_count = sum(
            1 for value in related if article_cluster_by_id.get(value) == cluster_id
        )
        related_policy_satisfied = (
            same_cluster_count >= 2
            if cluster_size[cluster_id] >= 3
            else same_cluster_count == 1 and len(related) >= 2
        )
        if (
            len(related) < 2
            or len(related) != len(set(related))
            or article_id in related
            or not set(related).issubset(article_code_by_id)
            or not related_policy_satisfied
        ):
            _fail("RAOS_EDITORIAL_V3_RELATED_ARTICLES_INVALID")
        product_ids = [
            _text(value) for value in cast(list[object], article["product_ids"])
        ]
        content_sha256 = _content_sha256(article.get("content_ref"))
        snapshot_id = f"snp-{article_code}-{content_sha256[:12]}"
        bindings: list[dict[str, object]] = []
        for product_id in product_ids:
            product_code = product_code_by_id.get(product_id)
            if product_code is None:
                _fail("RAOS_EDITORIAL_V3_PRODUCT_REFERENCE_INVALID")
            offer_id = f"off-{article_code}-{product_code}"
            for placement, placement_code in PLACEMENTS:
                measurement_id = f"{article_code}-{product_code}-{placement_code}"
                bindings.append(
                    {
                        "article_id": article_id,
                        "article_code": article_code,
                        "product_id": product_id,
                        "product_code": product_code,
                        "snapshot_id": snapshot_id,
                        "offer_id": offer_id,
                        "cta_id": f"cta-{measurement_id}",
                        "placement": placement,
                        "placement_code": placement_code,
                        "rakuten_measurement_id": measurement_id,
                        "provider_profile_state": "UNVERIFIED_DISABLED",
                    }
                )
        category_label = _text(cluster["category_label"])
        related_records = [
            {
                "article_id": related_id,
                "relationship": (
                    "same_cluster"
                    if article_cluster_by_id[related_id] == cluster_id
                    else "adjacent_context"
                ),
                "context": (
                    "同一クラスタの次の判断"
                    if article_cluster_by_id[related_id] == cluster_id
                    else "持ち運び条件の隣接文脈"
                ),
            }
            for related_id in related
        ]
        v3_articles.append(
            {
                **article,
                "v2_category": article.get("category"),
                "article_code": article_code,
                "cluster_id": cluster_id,
                "category": cluster_id,
                "category_label": category_label,
                "home_order": home_order,
                "content_snapshot_sha256": content_sha256,
                "snapshot_id": snapshot_id,
                "related_article_ids": related,
                "related_articles": related_records,
                "cta_bindings": bindings,
            }
        )
        navigation_articles.append(
            {
                "article_id": article_id,
                "article_code": article_code,
                "production_slug": _text(article["production_slug"]),
                "title": _text(article["title"]),
                "cluster_id": cluster_id,
                "category_label": category_label,
                "home_order": home_order,
                "related_articles": [
                    {
                        "article_id": related_id,
                        "article_code": article_code_by_id[related_id],
                        "production_slug": _text(
                            next(
                                candidate["production_slug"]
                                for candidate in v2_articles
                                if candidate["article_id"] == related_id
                            )
                        ),
                        "relationship": (
                            "same_cluster"
                            if article_cluster_by_id[related_id] == cluster_id
                            else "adjacent_context"
                        ),
                        "context": (
                            "同一クラスタの次の判断"
                            if article_cluster_by_id[related_id] == cluster_id
                            else "持ち運び条件の隣接文脈"
                        ),
                    }
                    for related_id in related
                ],
            }
        )

    for cluster_id, orders in home_orders.items():
        count = sum(
            1 for value in article_cluster_by_id.values() if value == cluster_id
        )
        if orders != set(range(1, count + 1)):
            _fail("RAOS_EDITORIAL_V3_HOME_ORDER_INVALID")

    measurement_ids = [
        _text(binding["rakuten_measurement_id"])
        for article in v3_articles
        for binding in cast(list[dict[str, object]], article["cta_bindings"])
    ]
    cta_ids = [
        _text(binding["cta_id"])
        for article in v3_articles
        for binding in cast(list[dict[str, object]], article["cta_bindings"])
    ]
    if len(measurement_ids) != 74 or len(set(measurement_ids)) != 74:
        _fail("RAOS_EDITORIAL_V3_MEASUREMENT_ID_INVALID")
    if len(set(cta_ids)) != len(cta_ids):
        _fail("RAOS_EDITORIAL_V3_CTA_ID_INVALID")

    clusters = [
        {
            **cluster,
            "article_ids": [
                _text(article["article_id"])
                for article in sorted(
                    (
                        row
                        for row in navigation_articles
                        if row["cluster_id"] == cluster["cluster_id"]
                    ),
                    key=lambda row: cast(int, row["home_order"]),
                )
            ],
        }
        for cluster in cluster_rows
    ]
    portfolio = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_V3",
        "version": "3.0.0",
        "predecessor": {
            "schema": "RAOS_EDITORIAL_PORTFOLIO_V2",
            "version": v2.get("version"),
            "historical_contract_preserved": True,
        },
        "target_origin": v2.get("target_origin"),
        "theme_version": v2.get("theme_version"),
        "evidence_policy": v2.get("evidence_policy"),
        "content_contract": v2.get("content_contract"),
        "strategy": {
            "article_count": 10,
            "cluster_count": 3,
            "new_content_gate": "NO_NEW_CONTENT_UNTIL_ACTUAL_DATA_GATE",
            "north_star": {
                "metric": "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT_JPY",
                "formula": (
                    "confirmed_reward_jpy - variable_external_cost_jpy - "
                    "editorial_minutes / 60 * approved_hourly_cost_jpy"
                ),
                "missing_value": "UNAVAILABLE",
                "unattributed_article_allocation": False,
            },
        },
        "rakuten_measurement_policy": {
            "format": "{article_code}-{product_code}-{card|final}",
            "placements": [placement for placement, _code in PLACEMENTS],
            "candidate_id_count": len(measurement_ids),
            "provider_profile_state": "UNVERIFIED_DISABLED",
            "live_link_mutation_allowed": False,
            "activation_gate": "VERIFIED_SAMPLE_PROFILE_AND_PROVIDER_CONSOLE_RECONCILIATION",
        },
        "clusters": clusters,
        "articles": v3_articles,
        "products": v3_products,
    }
    navigation = {
        "schema": "RAOS_EDITORIAL_NAVIGATION_V3",
        "version": "3.0.0",
        "target_origin": v2.get("target_origin"),
        "source_portfolio_schema": "RAOS_EDITORIAL_PORTFOLIO_V3",
        "clusters": clusters,
        "articles": sorted(
            navigation_articles,
            key=lambda row: (
                _positive_integer(
                    cluster_by_id[_text(row["cluster_id"])]["home_order"]
                ),
                _positive_integer(row["home_order"]),
            ),
        ),
    }
    return portfolio, navigation


def _check_or_write(path: Path, content: bytes, *, check: bool) -> None:
    absolute = REPOSITORY_ROOT / path
    if check:
        try:
            current = absolute.read_bytes()
        except OSError:
            _fail("RAOS_EDITORIAL_V3_OUTPUT_MISSING")
        if current != content:
            _fail("RAOS_EDITORIAL_V3_OUTPUT_DRIFT")
        return
    atomic_write(path, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        documents = build_documents()
        for path, document in zip(OUTPUT_PATHS, documents, strict=True):
            _check_or_write(path, canonical_json_bytes(document), check=arguments.check)
        print(
            "RAOS_EDITORIAL_V3_GENERATION "
            f"mode={'check' if arguments.check else 'write'} status=PASS"
        )
        return 0
    except EditorialV3BuildFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
