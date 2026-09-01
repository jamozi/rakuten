from __future__ import annotations

from datetime import date
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
from scripts import raos_editorial_portfolio_v2 as selection_builder


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
    assert v3["theme_version"] == "1.5.0"
    assert len(portfolio.articles) == len(v2["articles"]) == 10
    assert len(portfolio.products) == len(v2["products"]) == 31
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
    assert v3["selection_policy"]["zero_weight_factors"] == {
        "price": 0,
        "affiliate_reward_rate": 0,
        "rakuten_availability": 0,
    }


def test_stable_identity_and_measurement_bindings_are_unique_and_disabled() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    measurements = portfolio.cta_by_measurement_id

    assert [article.article_code for article in portfolio.articles] == [
        f"a{position:02d}" for position in range(1, 11)
    ]
    assert [product.product_code for product in portfolio.products] == [
        f"p{position:02d}" for position in range(1, len(portfolio.products) + 1)
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
    document = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert (
        document["rakuten_measurement_policy"]["client_measurement_default_enabled"]
        is False
    )
    assert (
        document["rakuten_measurement_policy"]["additional_tracking_default_enabled"]
        is False
    )
    for article in portfolio.articles:
        placements = {binding.placement for binding in article.cta_bindings}
        if article.article_id == "solota-vs-rakua-mini-plus":
            assert placements == set()
        else:
            assert placements == {"product_card", "final_summary"}


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
    intent_group_sizes = {
        intent_group_id: sum(
            row["intent_group_id"] == intent_group_id for row in articles.values()
        )
        for intent_group_id in {row["intent_group_id"] for row in articles.values()}
    }
    assert intent_group_sizes == {
        "carry-on-suitcase": 4,
        "countertop-dishwasher": 2,
        "portable-power": 2,
        "robot-vacuum": 2,
    }
    for article in articles.values():
        related = article["related_articles"]
        assert len(related) == min(
            2, intent_group_sizes[article["intent_group_id"]] - 1
        )
        for row in related:
            target = articles[row["article_id"]]
            expected_relationship = (
                "broader_guide"
                if article["broader_article_id"] == row["article_id"]
                else (
                    "narrower_comparison"
                    if target["broader_article_id"] == article["article_id"]
                    else "adjacent_condition"
                )
            )
            assert row["relationship"] == expected_relationship
            assert (
                row["context"]
                == {
                    "adjacent_condition": "近い条件を別の軸で比べる",
                    "broader_guide": "候補を広げて選び直す",
                    "narrower_comparison": "条件を絞った比較へ進む",
                }[expected_relationship]
            )
        assert all(
            articles[row["article_id"]]["intent_group_id"] == article["intent_group_id"]
            for row in related
        )


def test_every_article_has_a_reader_facing_role_scope_and_broader_route() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    by_code = {article.article_code: article for article in portfolio.articles}

    assert {code: article.content_role for code, article in by_code.items()} == {
        "a01": "brand_family_comparison",
        "a02": "category_guide",
        "a03": "model_family_comparison",
        "a04": "category_guide",
        "a05": "category_guide",
        "a06": "constraint_shortlist",
        "a07": "constraint_shortlist",
        "a08": "feature_shortlist",
        "a09": "constraint_shortlist",
        "a10": "lifecycle_status_route",
    }
    assert all(article.content_role_label for article in portfolio.articles)
    assert all(article.primary_query_intent for article in portfolio.articles)
    assert all(article.comparison_scope for article in portfolio.articles)
    assert {
        code: article.broader_article_id
        for code, article in by_code.items()
        if article.broader_article_id is not None
    } == {
        "a01": "lightweight-carry-on-suitcase-under-3kg",
        "a03": "st1704-portable-power-station-guide",
        "a09": "st1704-compact-robot-vacuum-shortlist",
        "a10": "st1704-countertop-dishwasher-for-small-households",
    }
    for article in portfolio.articles:
        if article.broader_article_id is None:
            continue
        broader = portfolio.article_by_id[article.broader_article_id]
        assert broader.intent_group_id == article.intent_group_id
        assert broader.content_role in {"category_guide", "constraint_shortlist"}
    for intent_group_id in {article.intent_group_id for article in portfolio.articles}:
        primary_intents = [
            article.primary_query_intent
            for article in portfolio.articles
            if article.intent_group_id == intent_group_id
        ]
        assert len(primary_intents) == len(set(primary_intents))


def test_generator_rejects_duplicate_primary_query_intent_within_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = json.loads(
        (ROOT / builder.INPUT_IDENTITIES_PATH).read_text(encoding="utf-8")
    )
    carry_on = [
        row
        for row in identities["articles"]
        if row["intent_group_id"] == "carry-on-suitcase"
    ]
    carry_on[1]["primary_query_intent"] = carry_on[0]["primary_query_intent"]
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_IDENTITIES_PATH:
            return identities
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_PRIMARY_QUERY_INTENT_INVALID",
    ):
        builder.build_documents()


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        ("origin", "RAOS_EDITORIAL_V3_PREDECESSOR_INVALID"),
        ("category", "RAOS_EDITORIAL_V3_ARTICLE_CLUSTER_INVALID"),
    ],
)
def test_generator_owns_cross_version_site_and_category_consistency(
    mutation: str,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor = json.loads(
        (ROOT / builder.INPUT_PORTFOLIO_PATH).read_text(encoding="utf-8")
    )
    if mutation == "origin":
        predecessor["target_origin"] = "https://example.invalid"
    else:
        predecessor["articles"][0]["category"] = "家事"
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_PORTFOLIO_PATH:
            return predecessor
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(builder.EditorialV3BuildFailure, match=failure):
        builder.build_documents()


def test_legacy_v2_theme_revision_does_not_invalidate_semantic_v3_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deployment cache identity is not semantic editorial input."""

    baseline = tuple(
        builder.canonical_json_bytes(row) for row in builder.build_documents()
    )
    predecessor = json.loads(
        (ROOT / builder.INPUT_PORTFOLIO_PATH).read_text(encoding="utf-8")
    )
    predecessor["theme_runtime_revision"] = "f" * 64
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_PORTFOLIO_PATH:
            return predecessor
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    mutated = tuple(
        builder.canonical_json_bytes(row) for row in builder.build_documents()
    )

    assert mutated == baseline


def test_generator_rejects_role_label_or_broader_route_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = json.loads(
        (ROOT / builder.INPUT_IDENTITIES_PATH).read_text(encoding="utf-8")
    )
    target = next(row for row in identities["articles"] if row["article_code"] == "a09")
    target["content_role_label"] = "市場全体ランキング"
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_IDENTITIES_PATH:
            return identities
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_CONTENT_ROLE_INVALID",
    ):
        builder.build_documents()


@pytest.mark.parametrize(
    ("article_code", "broader_article_id"),
    [
        ("a01", None),
        ("a02", "st1704-anker-solix-c300-c800-c1000-differences"),
    ],
)
def test_generator_enforces_required_and_allowed_broader_routes(
    article_code: str,
    broader_article_id: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = json.loads(
        (ROOT / builder.INPUT_IDENTITIES_PATH).read_text(encoding="utf-8")
    )
    target = next(
        row for row in identities["articles"] if row["article_code"] == article_code
    )
    target["broader_article_id"] = broader_article_id
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_IDENTITIES_PATH:
            return identities
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_CONTENT_ROLE_INVALID",
    ):
        builder.build_documents()


def test_market_candidate_audit_is_concrete_complete_and_not_self_referential() -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    portfolio = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))
    articles = {row["article_id"]: row for row in portfolio["articles"]}
    portfolio_product_ids = {product["product_id"] for product in portfolio["products"]}

    assert audit["rules"] == {
        "decision_critical_unknown_allowed": False,
        "generic_unnamed_candidate_allowed": False,
        "hard_filters_required": True,
        "official_category_sources_required": True,
        "exact_model_variant_scope_required": True,
        "lifecycle_crosscheck_required": True,
        "reader_visible_lifecycle_precedence": True,
        "embedded_lifecycle_conflict_state": "CONFLICT",
        "external_disposition_states": ["EXCLUDED", "DEFERRED"],
        "portfolio_reference_disposition": "REFERENCE_ONLY",
        "portfolio_products_must_use_reference_bindings": True,
        "reader_visible_exclusions_required": True,
        "selected_candidate_only_audit_allowed": False,
        "selected_product_due_diligence_source": "RAOS_PRODUCT_SELECTION_AUDIT_V2",
        "article_guidance_never_establishes_product_axis_completion": True,
        "incomplete_selected_product_axes_block_publication": True,
        "price_weight": 0,
        "affiliate_reward_rate_weight": 0,
        "rakuten_availability_weight": 0,
    }
    assert len(audit["articles"]) == 10
    selection_report = selection_builder._selection_audit_report(
        selection_builder.load_editorial_portfolio_v2(ROOT)
    )
    selection_by_id = {row["product_id"]: row for row in selection_report["products"]}
    observed_candidates: set[str] = set()
    lifecycle_conflicts = []
    exclusion_headings: set[str] = set()
    for row in audit["articles"]:
        article = articles[row["article_id"]]
        assert row["content_role"] == article["content_role"]
        assert row["primary_query_intent"] == article["primary_query_intent"]
        assert row["comparison_scope"] == article["comparison_scope"]
        assert row["hard_filters"]
        assert row["official_category_sources"]
        assert row["selected_product_ids"] == article["product_ids"]
        for candidate in row["considered_portfolio_candidates"]:
            assert candidate["disposition"] == "REFERENCE_ONLY"
            assert candidate["product_id"] not in row["selected_product_ids"]
            route = articles[candidate["route_article_id"]]
            assert candidate["product_id"] in route["product_ids"]
            assert route["intent_group_id"] == article["intent_group_id"]
        heading = row["reader_visible_exclusions_heading"]
        assert 8 <= len(heading) <= 60
        assert heading not in exclusion_headings
        exclusion_headings.add(heading)
        assert row["reader_visible_required"] is True
        assert row["considered_external_candidates"]
        assert set(row["axis_assessments"]) == set(audit["required_axes"])
        for axis, assessment in row["axis_assessments"].items():
            assert assessment["state"] != "NOT_EVALUATED"
            assert "未確認" not in assessment["rationale"]
            if axis in {"safety", "warranty_and_support", "maintainability"}:
                assert assessment["state"] == (
                    "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
                )
                assert assessment["evidence_refs"] == []
                assert date.fromisoformat(
                    assessment["recheck_by"]
                ) > date.fromisoformat(audit["evaluated_at"])
                assert "商品別" in assessment["rationale"]
                assert "推奨根拠" in assessment["rationale"]
                if row["selected_product_ids"]:
                    assert any(
                        next(
                            value
                            for value in selection_by_id[product_id]["axes"]
                            if value["axis"] == axis
                        )["state"]
                        in {
                            "NOT_EXECUTED",
                            "OFFICIAL_SAFETY_GUIDANCE_BOUND_RECHECK_REQUIRED",
                        }
                        for product_id in row["selected_product_ids"]
                    )
                else:
                    assert row["content_role"] == "lifecycle_status_route"
        for candidate in row["considered_external_candidates"]:
            assert candidate["candidate_id"].startswith("EXT-")
            assert candidate["candidate_id"] not in portfolio_product_ids
            assert candidate["disposition"] in {"EXCLUDED", "DEFERRED"}
            assert candidate["brand"]
            assert candidate["exact_model"]
            assert candidate["exact_variant_scope"]
            assert candidate["use_role"]
            assert (
                candidate["effective_lifecycle"]
                == candidate["reader_visible_lifecycle"]
            )
            assert candidate["decision_critical_unknowns"] == []
            assert candidate["official_url"] in candidate["evidence_refs"]
            assert "公式情報で照合できない候補" not in candidate["reason"]
            if candidate["lifecycle_evidence_state"] == "CONFLICT":
                lifecycle_conflicts.append(candidate)
            observed_candidates.add(candidate["candidate_id"])
    assert lifecycle_conflicts
    assert all(
        candidate["embedded_structured_lifecycle"]
        != candidate["reader_visible_lifecycle"]
        and candidate["effective_lifecycle"] == candidate["reader_visible_lifecycle"]
        and candidate["disposition"] != "INCLUDED"
        for candidate in lifecycle_conflicts
    )
    assert {
        "EXT-RIMOWA-CABIN-U",
        "EXT-SAMSONITE-AUDRINA-SPINNER-45",
        "EXT-ANKER-SOLIX-C1000-PLUS",
        "EXT-PANASONIC-NP-TSP2",
        "EXT-THANKO-RAKUA-MINI-COLOR",
        "EXT-THANKO-RAKUA-MINI-PLUS",
    } <= observed_candidates
    thanko = next(
        candidate
        for article in audit["articles"]
        for candidate in article["considered_external_candidates"]
        if candidate["candidate_id"] == "EXT-THANKO-RAKUA-MINI-PLUS"
    )
    assert thanko["model_lifecycle"] == "AVAILABLE"
    assert thanko["variant_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert thanko["reader_visible_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert thanko["effective_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert "再入荷通知だけ" in thanko["reason"]
    assert "売り切れ" not in thanko["reason"]

    thanko_color = next(
        candidate
        for article in audit["articles"]
        for candidate in article["considered_external_candidates"]
        if candidate["candidate_id"] == "EXT-THANKO-RAKUA-MINI-COLOR"
    )
    assert thanko_color["exact_model"] == "ラクアmini color"
    assert thanko_color["evaluated_at"] == "2026-09-01"
    assert thanko_color["variant_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert "TDWS25SBL" in thanko_color["exact_variant_scope"]
    assert "TDWS25SRD" in thanko_color["exact_variant_scope"]


@pytest.mark.parametrize(
    ("candidate_date", "should_pass"),
    [("2026-09-01", True), ("2026-08-30", False)],
)
def test_market_candidate_observation_may_advance_but_never_precede_audit_baseline(
    candidate_date: str,
    should_pass: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    audit["articles"][0]["considered_external_candidates"][0]["evaluated_at"] = (
        candidate_date
    )
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    if should_pass:
        builder.build_documents()
    else:
        with pytest.raises(
            builder.EditorialV3BuildFailure,
            match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
        ):
            builder.build_documents()


def test_generator_rejects_lifecycle_conflict_hidden_as_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    candidate = audit["articles"][0]["considered_external_candidates"][0]
    candidate["reader_visible_lifecycle"] = "AVAILABLE"
    candidate["embedded_structured_lifecycle"] = "SOLD_OUT"
    candidate["lifecycle_evidence_state"] = "CONSISTENT"
    candidate["effective_lifecycle"] = "AVAILABLE"
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
    ):
        builder.build_documents()


@pytest.mark.parametrize(
    ("mutation",),
    [
        ("missing_exact_variant",),
        ("generic_model",),
        ("included_without_selected_binding",),
        ("decision_critical_lifecycle_unknown",),
    ],
)
def test_generator_rejects_invalid_named_candidate_disposition_or_scope(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    candidate = audit["articles"][0]["considered_external_candidates"][0]
    if mutation == "missing_exact_variant":
        candidate["exact_variant_scope"] = ""
    elif mutation == "generic_model":
        candidate["exact_model"] = "その他"
    elif mutation == "included_without_selected_binding":
        candidate["disposition"] = "INCLUDED"
        candidate["exclusion_axis"] = None
    else:
        candidate["decision_critical"] = True
        candidate["model_lifecycle"] = "UNKNOWN"
        candidate["variant_lifecycle"] = "UNKNOWN"
        candidate["reader_visible_lifecycle"] = "UNKNOWN"
        candidate["embedded_structured_lifecycle"] = "NOT_PRESENT"
        candidate["lifecycle_evidence_state"] = "READER_VISIBLE_ONLY"
        candidate["effective_lifecycle"] = "UNKNOWN"
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_(?:INPUT|MARKET_AUDIT)_INVALID",
    ):
        builder.build_documents()


@pytest.mark.parametrize("field", ["hard_filters", "official_category_sources"])
def test_generator_rejects_empty_candidate_universe_inputs(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    audit["articles"][0][field] = []
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
    ):
        builder.build_documents()


def test_generator_rejects_portfolio_candidate_without_owner_article_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    candidate = audit["articles"][0]["considered_portfolio_candidates"][0]
    candidate["route_article_id"] = "st1704-portable-power-station-guide"
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
    ):
        builder.build_documents()


def test_generator_rejects_decision_critical_unknown_in_market_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    audit["articles"][0]["axis_assessments"]["safety"] = {
        "state": "NOT_EVALUATED",
        "rationale": "決定に重要だが未確認",
        "evidence_refs": [],
    }
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
    ):
        builder.build_documents()


def test_generator_rejects_article_guidance_overstated_as_selected_product_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audit = json.loads(
        (ROOT / builder.MARKET_CANDIDATE_AUDIT_PATH).read_text(encoding="utf-8")
    )
    audit["articles"][0]["axis_assessments"]["safety"] = {
        "state": "OFFICIAL_EVIDENCE_USED",
        "rationale": "航空会社の一般案内があるため商品別確認も完了した。",
        "evidence_refs": ["https://www.ana.co.jp/"],
    }
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.MARKET_CANDIDATE_AUDIT_PATH:
            return audit
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID",
    ):
        builder.build_documents()


def test_generator_is_deterministic_and_current() -> None:
    expected = builder.build_documents()

    for path, document in zip(builder.OUTPUT_PATHS, expected, strict=True):
        assert (ROOT / path).read_bytes() == builder.canonical_json_bytes(document)
    assert builder.main(["--check"]) == 0


def test_generator_rejects_related_article_from_a_different_search_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = json.loads(
        (ROOT / builder.INPUT_IDENTITIES_PATH).read_text(encoding="utf-8")
    )
    target = next(
        row
        for row in identities["articles"]
        if row["article_id"] == "carry-on-suitcase-under-100-seats"
    )
    target["related_article_ids"] = [
        "st1703-first-suitcase-comparison",
        "st1704-compact-robot-vacuum-shortlist",
    ]
    original_read_json = builder._read_json

    def read_json(path: Path) -> dict[str, object]:
        if path == builder.INPUT_IDENTITIES_PATH:
            return identities
        return original_read_json(path)

    monkeypatch.setattr(builder, "_read_json", read_json)
    with pytest.raises(
        builder.EditorialV3BuildFailure,
        match="RAOS_EDITORIAL_V3_RELATED_ARTICLES_INVALID",
    ):
        builder.build_documents()


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


def test_private_workflow_readme_lists_every_unset_product_identity() -> None:
    v2 = json.loads(
        (ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_text(
            encoding="utf-8"
        )
    )
    expected = tuple(
        product["product_id"]
        for product in v2["products"]
        if product["rakuten_shop_code"] is None or product["rakuten_item_code"] is None
    )
    readme = (ROOT / "changes/editorial-portfolio-v3/README.md").read_text(
        encoding="utf-8"
    )
    section = readme.split(
        "The current tracked registry intentionally leaves these thirteen ", 1
    )[1].split("After all product evidence is complete", 1)[0]
    documented = tuple(re.findall(r"^- `(PRD-[A-Z0-9-]+)`$", section, flags=re.M))

    assert len(expected) == 13
    assert documented == expected


def test_loader_rejects_stale_fixed_completion_product_count(tmp_path: Path) -> None:
    document = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))
    completion = document["evidence_policy"]["completion_gate"]
    completion["required_product_count"] = len(document["products"]) + 1
    target = tmp_path / PORTFOLIO_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(
        EditorialPortfolioV3Failure,
        match="RAOS_EDITORIAL_V3_CONTRACT_INVALID",
    ):
        load_editorial_portfolio_v3(tmp_path)


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
