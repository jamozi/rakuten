from __future__ import annotations

import json
from pathlib import Path
import re

from raos.application.editorial.editorial_portfolio_v3 import (
    load_editorial_portfolio_v3,
)
from scripts import build_editorial_portfolio_v3 as builder


ROOT = Path(__file__).resolve().parents[2]


def test_generated_successor_covers_all_v2_identities_without_rewriting_v2() -> None:
    v2 = json.loads(
        (ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_text(
            encoding="utf-8"
        )
    )
    v3 = json.loads(
        (ROOT / "changes/editorial-portfolio-v3/editorial-portfolio.v3.json").read_text(
            encoding="utf-8"
        )
    )
    portfolio = load_editorial_portfolio_v3(ROOT)

    assert portfolio.version == "3.0.0"
    assert len(portfolio.articles) == len(v2["articles"]) == 10
    assert len(portfolio.products) == len(v2["products"]) == 32
    assert {article.article_id for article in portfolio.articles} == {
        article["article_id"] for article in v2["articles"]
    }
    assert {product.product_id for product in portfolio.products} == {
        product["product_id"] for product in v2["products"]
    }
    assert v3["predecessor"] == {
        "historical_contract_preserved": True,
        "schema": "RAOS_EDITORIAL_PORTFOLIO_V2",
        "version": "2.0.0",
    }
    assert v3["strategy"]["north_star"]["missing_value"] == "UNAVAILABLE"
    assert v3["strategy"]["north_star"]["unattributed_article_allocation"] is False


def test_stable_identity_and_measurement_bindings_are_unique_and_disabled() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    measurements = portfolio.cta_by_measurement_id

    assert [article.article_code for article in portfolio.articles] == [
        f"a{position:02d}" for position in range(1, 11)
    ]
    assert [product.product_code for product in portfolio.products] == [
        f"p{position:02d}" for position in range(1, 33)
    ]
    assert len(measurements) == 74
    assert all(
        re.fullmatch(r"a[0-9]{2}-p[0-9]{2}-(?:card|final)", identifier)
        for identifier in measurements
    )
    assert all(
        binding.provider_profile_state == "UNVERIFIED_DISABLED"
        for binding in measurements.values()
    )
    assert all(
        {binding.placement for binding in article.cta_bindings}
        == {"product_card", "final_summary"}
        for article in portfolio.articles
    )


def test_navigation_has_three_clusters_and_explicit_relationship_policy() -> None:
    navigation = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/generated/navigation.v3.json"
        ).read_text(encoding="utf-8")
    )
    articles = {row["article_id"]: row for row in navigation["articles"]}

    assert [
        (row["cluster_id"], len(row["article_ids"])) for row in navigation["clusters"]
    ] == [
        ("mobility", 4),
        ("household", 4),
        ("preparedness", 2),
    ]
    assert set(articles) == {
        article_id
        for cluster in navigation["clusters"]
        for article_id in cluster["article_ids"]
    }
    for article in articles.values():
        related = article["related_articles"]
        same_cluster = [row for row in related if row["relationship"] == "same_cluster"]
        if article["cluster_id"] == "preparedness":
            adjacent = [
                row for row in related if row["relationship"] == "adjacent_context"
            ]
            assert len(same_cluster) == 1
            assert len(adjacent) == 1
            assert adjacent[0]["article_code"] == "a01"
            assert adjacent[0]["context"] == "持ち運び条件の隣接文脈"
        else:
            assert len(same_cluster) >= 2
            assert all(row["relationship"] == "same_cluster" for row in related)


def test_generator_is_deterministic_and_current() -> None:
    expected = builder.build_documents()

    for path, document in zip(builder.OUTPUT_PATHS, expected, strict=True):
        assert (ROOT / path).read_bytes() == builder.canonical_json_bytes(document)
    assert builder.main(["--check"]) == 0


def test_tracked_rakuten_boundary_contains_no_live_column_names() -> None:
    boundary = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/rakuten-parser-boundary.v1.json"
        ).read_text(encoding="utf-8")
    )

    assert boundary["state"] == "DISABLED_UNTIL_VERIFIED_SAMPLE_PROFILE_BOUND"
    assert boundary["tracked_live_column_names"] == []
    assert boundary["tracked_status_values"] == []
    assert boundary["rules"]["automatic_column_guessing"] is False
    assert boundary["rules"]["provider_totals_must_reconcile_before_commit"] is True
