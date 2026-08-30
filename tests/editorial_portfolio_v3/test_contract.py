from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from raos.application.editorial.editorial_portfolio_v3 import (
    EditorialPortfolioV3Failure,
    PORTFOLIO_RELATIVE_PATH,
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
    assert v3["theme_version"] == "1.4.0"
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


def test_internal_cta_candidates_and_provider_slots_are_separate_and_disabled() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    candidates = portfolio.cta_by_candidate_id
    slots = portfolio.provider_slot_by_id

    assert [article.article_code for article in portfolio.articles] == [
        f"a{position:02d}" for position in range(1, 11)
    ]
    assert [product.product_code for product in portfolio.products] == [
        f"p{position:02d}" for position in range(1, 33)
    ]
    assert len(candidates) == 74
    assert all(
        re.fullmatch(r"icta_a[0-9]{2}_p[0-9]{2}_(?:card|final)", identifier)
        for identifier in candidates
    )
    assert all(
        binding.provider_profile_state == "UNVERIFIED_DISABLED"
        for binding in candidates.values()
    )
    assert candidates["icta_a01_p01_card"].cta_id == "icta_a01_p01_card"
    assert candidates["icta_a01_p01_card"].provider_slot_id == "rps-a01-card"
    assert len(slots) == 20
    assert set(portfolio.provider_slot_by_key) == {
        (article.article_id, placement)
        for article in portfolio.articles
        for placement in ("product_card", "final_summary")
    }
    assert all(
        re.fullmatch(r"rps-a[0-9]{2}-(?:card|final)", identifier)
        and slot.provider_profile_state == "UNVERIFIED_DISABLED"
        for identifier, slot in slots.items()
    )
    assert all(
        {binding.placement for binding in article.cta_bindings}
        == {"product_card", "final_summary"}
        for article in portfolio.articles
    )
    assert all(
        portfolio.provider_slot_by_id[binding.provider_slot_id]
        == portfolio.provider_slot_by_key[(article.article_id, binding.placement)]
        for article in portfolio.articles
        for binding in article.cta_bindings
    )


def test_tracked_provider_slots_never_contain_actual_provider_ids() -> None:
    document = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))

    def all_mapping_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                key for child in value.values() for key in all_mapping_keys(child)
            }
        if isinstance(value, list):
            return {key for child in value for key in all_mapping_keys(child)}
        return set()

    assert not {"provider_measurement_id", "rakuten_measurement_id"}.intersection(
        all_mapping_keys(document)
    )
    assert document["rakuten_measurement_policy"] == {
        "activation_gate": "VERIFIED_SAMPLE_PROFILE_AND_PROVIDER_CONSOLE_RECONCILIATION",
        "internal_cta_id_format": "icta_{article_code}_{product_code}_{card|final}",
        "internal_cta_identity_count": 74,
        "internal_cta_namespace": "RAOS_INTERNAL_CTA_V1",
        "live_link_mutation_allowed": False,
        "placements": ["product_card", "final_summary"],
        "provider_measurement_id_storage": "OWNER_PRIVATE_ONLY",
        "provider_profile_state": "UNVERIFIED_DISABLED",
        "provider_slot_count": 20,
        "provider_slot_format": "rps-{article_code}-{card|final}",
        "provider_slot_granularity": "ARTICLE_PLACEMENT",
        "provider_slot_limit": 20,
    }
    assert all(
        "provider_measurement_id" not in slot
        and set(slot)
        == {
            "article_code",
            "article_id",
            "placement",
            "placement_code",
            "provider_profile_state",
            "provider_slot_id",
        }
        for slot in document["rakuten_provider_slots"]
    )


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("provider_measurement_id", "must-remain-owner-private"),
        ("rakuten_measurement_id", "must-remain-owner-private"),
        ("provider_slot_id", "rps-a99-card"),
    ],
)
def test_loader_rejects_provider_slot_leak_or_cta_slot_drift(
    tmp_path: Path,
    mutation: str,
    value: str,
) -> None:
    document = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))
    if mutation == "provider_measurement_id":
        document["rakuten_provider_slots"][0][mutation] = value
    else:
        document["articles"][0]["cta_bindings"][0][mutation] = value
    target = tmp_path / PORTFOLIO_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        EditorialPortfolioV3Failure,
        match="RAOS_EDITORIAL_V3_CONTRACT_INVALID",
    ):
        load_editorial_portfolio_v3(tmp_path)


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


@pytest.mark.parametrize("field", ["related_article_ids", "product_ids"])
def test_loader_normalizes_malformed_article_lists_to_stable_failure(
    tmp_path: Path,
    field: str,
) -> None:
    document = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))
    document["articles"][0][field] = None
    target = tmp_path / PORTFOLIO_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        EditorialPortfolioV3Failure,
        match="RAOS_EDITORIAL_V3_CONTRACT_INVALID",
    ):
        load_editorial_portfolio_v3(tmp_path)
