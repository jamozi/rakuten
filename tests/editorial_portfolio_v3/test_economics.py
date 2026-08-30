from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from raos.application.editorial.editorial_portfolio_v3 import (
    EditorialPortfolioV3,
    PORTFOLIO_RELATIVE_PATH,
    load_editorial_portfolio_v3,
)
from raos.application.finance.editorial_economics_v3 import (
    EditorialEconomicsV3Failure,
    bind_rakuten_profile,
    build_baseline_report,
    candidate_query_demand_template,
    canonical_json_bytes,
    commit_rakuten_report,
    cost_input_template,
    detect_rakuten_sample,
    establish_t0_receipt,
    evaluate_followups,
    parse_rakuten_report,
    production_readback_template,
    rakuten_binding_template,
    read_private_bytes,
    render_baseline_html,
    sha256_bytes,
    validate_t0_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
HASH = "a" * 64
SAMPLE = (
    "fixture_id,fixture_state,fixture_reward,fixture_measurement,fixture_day,fixture_currency\n"
    "row-1,P,100,a01-p01-card,2026-08-01,JPY\n"
    "row-2,C,200,a01-p01-card,2026-08-02,JPY\n"
    "row-3,X,50,fixture-unmatched,2026-08-03,JPY\n"
).encode()


@pytest.fixture
def portfolio() -> EditorialPortfolioV3:
    return load_editorial_portfolio_v3(ROOT)


def _profile(
    portfolio: EditorialPortfolioV3,
) -> tuple[dict[str, object], dict[str, object]]:
    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    detection_content = canonical_json_bytes(detection)
    request = rakuten_binding_template(
        detection, detection_sha256=sha256_bytes(detection_content)
    )
    request["owner_verified_sanitized_real_sample"] = True
    request["measurement_id_echo_verified_in_provider_report"] = True
    request["columns"] = {
        "provider_row_id": "fixture_id",
        "status": "fixture_state",
        "reward_jpy": "fixture_reward",
        "measurement_id": "fixture_measurement",
        "occurred_on": "fixture_day",
        "currency": "fixture_currency",
    }
    request["status_values"] = {
        "PENDING": ["P"],
        "CONFIRMED": ["C"],
        "CANCELLED": ["X"],
    }
    request["amount_format"] = "INTEGER_JPY"
    request["date_format"] = "ISO_DATE"
    profile = bind_rakuten_profile(
        sample_content=SAMPLE,
        detection=detection,
        detection_content_sha256=sha256_bytes(detection_content),
        request=request,
        portfolio=portfolio,
    )
    return profile, request


def _dry_run(
    portfolio: EditorialPortfolioV3,
) -> tuple[dict[str, object], dict[str, object]]:
    profile, _request = _profile(portfolio)
    dry_run = parse_rakuten_report(
        content=SAMPLE,
        profile=profile,
        profile_sha256=sha256_bytes(canonical_json_bytes(profile)),
        portfolio=portfolio,
    )
    return dry_run, profile


def _commit(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    dry_run, _profile_document = _dry_run(portfolio)
    return commit_rakuten_report(
        dry_run=dry_run,
        reparsed=dry_run,
        expected_source_sha256=sha256_bytes(SAMPLE),
        provider_row_count=3,
        provider_totals_jpy={
            "PENDING": 100,
            "CONFIRMED": 200,
            "CANCELLED": 50,
        },
    )


def test_profile_binding_requires_owner_attestation_and_real_echo(
    portfolio: EditorialPortfolioV3,
) -> None:
    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    detection_content = canonical_json_bytes(detection)
    request = rakuten_binding_template(
        detection, detection_sha256=sha256_bytes(detection_content)
    )

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID",
    ):
        bind_rakuten_profile(
            sample_content=SAMPLE,
            detection=detection,
            detection_content_sha256=sha256_bytes(detection_content),
            request=request,
            portfolio=portfolio,
        )


def test_closed_profile_parses_direct_and_unattributed_without_estimation(
    portfolio: EditorialPortfolioV3,
) -> None:
    dry_run, profile = _dry_run(portfolio)

    assert profile["state"] == "VERIFIED_SAMPLE_BOUND"
    assert profile["direct_attribution_enabled"] is True
    assert profile["estimated_attribution_enabled"] is False
    assert dry_run["totals_jpy"] == {
        "PENDING": 100,
        "CONFIRMED": 200,
        "CANCELLED": 50,
    }
    assert dry_run["attribution"]["DIRECT"]["totals_jpy"] == {
        "PENDING": 100,
        "CONFIRMED": 200,
        "CANCELLED": 0,
    }
    assert dry_run["attribution"]["ESTIMATED"] == {
        "state": "NOT_PRODUCED_BY_PROVIDER_REPORT_IMPORT",
        "totals_jpy": {"PENDING": 0, "CONFIRMED": 0, "CANCELLED": 0},
    }
    assert dry_run["attribution"]["UNATTRIBUTED"]["totals_jpy"] == {
        "PENDING": 0,
        "CONFIRMED": 0,
        "CANCELLED": 50,
    }
    assert dry_run["unmatched_measurement_row_count"] == 1
    assert dry_run["raw_rows_persisted"] is False


def test_commit_requires_exact_source_and_provider_reconciliation(
    portfolio: EditorialPortfolioV3,
) -> None:
    dry_run, _profile_document = _dry_run(portfolio)
    committed = _commit(portfolio)

    assert committed["state"] == "COMMITTED_OWNER_PRIVATE_RECONCILED"
    assert committed["reconciliation"]["status"] == "PASS"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED",
    ):
        commit_rakuten_report(
            dry_run=dry_run,
            reparsed=dry_run,
            expected_source_sha256="b" * 64,
            provider_row_count=3,
            provider_totals_jpy={
                "PENDING": 100,
                "CONFIRMED": 200,
                "CANCELLED": 50,
            },
        )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PROVIDER_RECONCILIATION_FAILED",
    ):
        commit_rakuten_report(
            dry_run=dry_run,
            reparsed=dry_run,
            expected_source_sha256=sha256_bytes(SAMPLE),
            provider_row_count=3,
            provider_totals_jpy={
                "PENDING": 100,
                "CONFIRMED": 201,
                "CANCELLED": 50,
            },
        )


def test_duplicate_and_formula_like_rows_fail_closed(
    portfolio: EditorialPortfolioV3,
) -> None:
    profile, _request = _profile(portfolio)
    profile_sha = sha256_bytes(canonical_json_bytes(profile))
    duplicate = SAMPLE + ("row-1,C,1,a01-p01-card,2026-08-03,JPY\n").encode()
    formula = SAMPLE.replace(b"row-3,X", b"=CMD(),X")

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_REPORT_DUPLICATE_ROW",
    ):
        parse_rakuten_report(
            content=duplicate,
            profile=profile,
            profile_sha256=profile_sha,
            portfolio=portfolio,
        )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_REPORT_FORMULA_CELL_REJECTED",
    ):
        parse_rakuten_report(
            content=formula,
            profile=profile,
            profile_sha256=profile_sha,
            portfolio=portfolio,
        )


def _cost_input(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    document = cost_input_template(portfolio)
    document["owner_attested"] = True
    document["period"] = {"date_from": "2026-08-01", "date_to": "2026-08-03"}
    document["approved_hourly_cost_jpy"] = 2000
    for row in document["articles"]:
        row["editorial_minutes"] = (
            60 if row["article_id"] == portfolio.articles[0].article_id else 0
        )
        row["variable_external_cost_jpy"] = (
            100 if row["article_id"] == portfolio.articles[0].article_id else 0
        )
    return document


def _gsc_input(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    article = portfolio.articles[0]
    return {
        "schema_version": 1,
        "source": "GSC",
        "site_id": "fixture-site",
        "date_from": "2026-08-01",
        "date_to": "2026-08-03",
        "retrieved_at": "2026-08-04T00:00:00Z",
        "request_sha256": HASH,
        "row_count": 1,
        "rows": [
            {
                "metric_date": "2026-08-02",
                "query_text": "owner-private fixture query",
                "page_url": f"{portfolio.target_origin}/{article.production_slug}/",
                "country_code": "JPN",
                "device": "MOBILE",
                "clicks": 2,
                "impressions": 10,
                "ctr": 0.2,
                "average_position": 4.0,
                "request_sha256": HASH,
            }
        ],
    }


def _ga4_input(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    article = portfolio.articles[0]
    cta = article.cta_bindings[0]
    return {
        "schema_version": 1,
        "source": "GA4",
        "site_id": "fixture-property",
        "date_from": "2026-08-01",
        "date_to": "2026-08-03",
        "retrieved_at": "2026-08-04T00:00:00Z",
        "request_sha256": HASH,
        "row_count": 1,
        "configuration": {
            "property_id": "123",
            "property_resource": "properties/123",
            "display_name": "fixture",
            "time_zone": "Asia/Tokyo",
            "currency_code": "JPY",
            "reporting_identity": "BLENDED",
            "required_event_custom_dimensions": [
                "article_id",
                "snapshot_id",
                "cta_id",
                "offer_id",
                "product_id",
                "placement",
            ],
            "retrieved_at": "2026-08-04T00:00:00Z",
            "response_sha256": HASH,
        },
        "rows": [
            {
                "metric_date": "2026-08-02",
                "dimensions": [
                    {"name": "article_id", "value": article.article_id},
                    {"name": "snapshot_id", "value": article.snapshot_id},
                    {"name": "cta_id", "value": cta.cta_id},
                    {"name": "offer_id", "value": cta.offer_id},
                    {"name": "product_id", "value": cta.product_id},
                    {"name": "placement", "value": cta.placement},
                    {"name": "eventName", "value": "affiliate_click"},
                ],
                "metrics": [{"name": "eventCount", "value": "3"}],
                "grain_sha256": HASH,
                "is_thresholded": False,
                "request_sha256": HASH,
            }
        ],
    }


def _rakuten_activation(
    portfolio: EditorialPortfolioV3,
) -> tuple[dict[str, object], str, str]:
    portfolio_sha256 = sha256_bytes((ROOT / PORTFOLIO_RELATIVE_PATH).read_bytes())
    cta_count = sum(len(article.cta_bindings) for article in portfolio.articles)
    v2_materialization: dict[str, object] = {
        "portfolio_sha256": "3" * 64,
        "evidence_status_sha256": "4" * 64,
        "local_generated_at": "2026-08-01T00:00:00Z",
        "production_generated_at": "2026-08-01T00:00:00Z",
        "local_receipt_sha256": "5" * 64,
        "production_receipt_sha256": "6" * 64,
    }
    overlays: dict[str, object] = {}
    overlay_bindings: dict[str, object] = {}
    for mode in ("local", "production"):
        article_rows: list[dict[str, object]] = []
        for article in portfolio.articles:
            source_sha256 = sha256_bytes(
                f"{mode}:source:{article.article_id}".encode()
            )
            materialized_sha256 = sha256_bytes(
                f"{mode}:activated:{article.article_id}:{source_sha256}".encode()
            )
            article_rows.append(
                {
                    "article_id": article.article_id,
                    "production_slug": article.production_slug,
                    "source_sha256": source_sha256,
                    "materialized_sha256": materialized_sha256,
                    "cta_count": len(article.cta_bindings),
                }
            )
        article_set_sha256 = sha256_bytes(
            canonical_json_bytes(
                [
                    {
                        "article_id": row["article_id"],
                        "production_slug": row["production_slug"],
                        "sha256": row["materialized_sha256"],
                    }
                    for row in article_rows
                ]
            )
        )
        posts_sha256 = sha256_bytes(f"{mode}:posts".encode())
        v2_receipt_sha256 = (
            v2_materialization["local_receipt_sha256"]
            if mode == "local"
            else v2_materialization["production_receipt_sha256"]
        )
        receipt = {
            "schema": "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V1",
            "version": "1.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": v2_materialization["portfolio_sha256"],
            "v2_evidence_status_sha256": v2_materialization[
                "evidence_status_sha256"
            ],
            "v2_materialization_receipt_sha256": v2_receipt_sha256,
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "article_count": len(article_rows),
            "cta_count": cta_count,
            "articles": article_rows,
        }
        receipt_sha256 = sha256_bytes(canonical_json_bytes(receipt))
        prefix = (
            "local-materialized-fixtures-v3-"
            if mode == "local"
            else "production-materialized-fixtures-v3-"
        )
        overlays[mode] = {
            "directory_name": prefix + receipt_sha256[:16],
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "overlay_receipt_sha256": receipt_sha256,
            "articles": article_rows,
        }
        overlay_bindings[mode] = {
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "overlay_receipt_sha256": receipt_sha256,
        }
    document: dict[str, object] = {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2",
        "version": "2.0.0",
        "state": "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED",
        "portfolio_sha256": portfolio_sha256,
        "admin_receipt_sha256": "1" * 64,
        "money_link_mapping_sha256": "2" * 64,
        "v2_materialization": v2_materialization,
        "overlays": overlays,
        "materialized_set_sha256": sha256_bytes(canonical_json_bytes(overlay_bindings)),
        "article_count": len(portfolio.articles),
        "cta_count": cta_count,
        "provider_parameter_inference_used": False,
        "tracked_source_modified": False,
        "live_write_performed": False,
        "publication_authorized": False,
    }
    return (
        document,
        sha256_bytes(canonical_json_bytes(document)),
        portfolio_sha256,
    )


def _t0_receipt(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    document = production_readback_template(portfolio)
    document["owner_attested"] = True
    document["analytics_site_binding"] = {
        "state": "OWNER_PRIVATE_READ_ONLY_BINDING_VERIFIED",
        "binding_sha256": "e" * 64,
        "ga4_property_id_sha256": "d" * 64,
        "ga4_configuration_response_sha256": "f" * 64,
    }
    observed_at = (
        "2026-08-01T00:01:00Z",
        "2026-08-01T00:02:00Z",
        "2026-08-01T00:03:00Z",
    )
    for row, timestamp in zip(document["observations"], observed_at, strict=True):
        row["state"] = "SUCCESS"
        row["observed_at"] = timestamp
        row["request_sha256"] = HASH
        row["response_sha256"] = "b" * 64
    document["observations"][0]["details"]["live_link_count"] = 74
    document["observations"][0]["details"]["all_ids_echo_verified"] = True
    document["observations"][0]["details"]["activation_dry_run_sha256"] = (
        activation_sha256
    )
    document["observations"][0]["details"]["materialized_set_sha256"] = activation[
        "materialized_set_sha256"
    ]
    production = activation["overlays"]["production"]
    document["observations"][0]["details"]["production_posts_sha256"] = (
        production["posts_sha256"]
    )
    document["observations"][0]["details"]["production_article_set_sha256"] = (
        production["article_set_sha256"]
    )
    document["observations"][0]["details"][
        "production_overlay_receipt_sha256"
    ] = production["overlay_receipt_sha256"]
    document["observations"][1]["details"]["http_status"] = 202
    document["observations"][1]["details"]["aggregate_readback_observed"] = True
    document["observations"][1]["details"]["event_id_sha256"] = "c" * 64
    document["observations"][2]["details"]["property_id_sha256"] = "d" * 64
    document["observations"][2]["details"]["configuration_response_sha256"] = "f" * 64
    document["observations"][2]["details"]["analytics_site_binding_sha256"] = "e" * 64
    document["observations"][2]["details"]["article_id"] = portfolio.articles[
        0
    ].article_id
    document["observations"][2]["details"]["event_observed"] = True
    return establish_t0_receipt(
        document=document,
        observation_sha256=sha256_bytes(canonical_json_bytes(document)),
        rakuten_activation=activation,
        rakuten_activation_sha256=activation_sha256,
        expected_portfolio_sha256=portfolio_sha256,
        portfolio=portfolio,
        evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )


def test_actual_baseline_keeps_program_and_article_attribution_separate(
    portfolio: EditorialPortfolioV3,
) -> None:
    report = build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=_commit(portfolio),
        cost_input=_cost_input(portfolio),
        gsc_input=_gsc_input(portfolio),
        ga4_input=_ga4_input(portfolio),
        t0_receipt=_t0_receipt(portfolio),
        generated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    first = report["articles"][0]

    assert report["period_alignment"] == "PASS"
    assert report["period_kind"] == "PARTIAL_OR_NON_MONTHLY_BASELINE"
    assert report["t0"] == "2026-08-01T00:03:00Z"
    assert report["cohort"] == "MIXED_T0_BOUNDARY"
    assert len(report["t0_receipt_sha256"]) == 64
    assert report["north_star"]["value_jpy"] == -1900
    assert report["north_star"]["monthly_north_star_eligible"] is False
    assert report["north_star"]["unattributed_reward_allocated_to_articles"] is False
    assert first["gsc"]["impressions"] == 10
    assert first["gsc"]["average_position"] == 4.0
    assert first["ga4"]["events"] == {"affiliate_click": 3}
    assert first["rakuten_attribution_jpy"]["DIRECT"] == {
        "state": "RECONCILED",
        "PENDING": 100,
        "CONFIRMED": 200,
        "CANCELLED": 0,
    }
    assert first["rakuten_attribution_jpy"]["ESTIMATED"]["state"] == (
        "NOT_PRODUCED_BY_PROVIDER_REPORT_IMPORT"
    )
    assert first["rakuten_attribution_jpy"]["UNATTRIBUTED"]["state"] == (
        "NOT_ALLOCATED_TO_ARTICLE"
    )
    assert first["cost"]["editorial_minutes"] == 60
    assert first["cost"]["variable_external_cost_jpy"] == 100
    assert first["cost"]["human_cost_jpy"] == 2000
    assert first["freshness"]["gsc"]["retrieved_at"] == "2026-08-04T00:00:00Z"
    assert first["attribution_basis"]["rakuten"] == (
        "DIRECT_VERIFIED_MEASUREMENT_ID_MATCH"
    )
    assert first["data_quality"]["missing_is_zero"] is False
    assert report["rakuten_attribution_jpy"]["UNATTRIBUTED"] == {
        "state": "NO_VERIFIED_MEASUREMENT_ID_MATCH",
        "PENDING": 0,
        "CONFIRMED": 0,
        "CANCELLED": 50,
    }
    assert first["confirmed_contribution_profit_jpy"]["value_jpy"] == -1900
    serialized = json.dumps(report, ensure_ascii=False)
    assert "owner-private fixture query" not in serialized
    html = render_baseline_html(report).decode()
    assert "noindex,nofollow" in html
    assert "GSC平均順位" in html
    assert "affiliate_click=3" in html
    assert "楽天Direct pending" in html
    assert "NOT_ALLOCATED_TO_ARTICLE" in html
    assert "作業分" in html
    assert "freshness" in html
    assert "attribution basis" in html
    assert "data quality" in html
    assert "owner-private fixture query" not in html


def test_ga4_summary_rejects_custom_dimension_identity_drift(
    portfolio: EditorialPortfolioV3,
) -> None:
    document = _ga4_input(portfolio)
    dimensions = document["rows"][0]["dimensions"]
    next(row for row in dimensions if row["name"] == "snapshot_id")["value"] = (
        "snp-drifted"
    )

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_GA4_ROW_INVALID",
    ):
        build_baseline_report(
            portfolio=portfolio,
            rakuten_commit=None,
            cost_input=None,
            gsc_input=None,
            ga4_input=document,
            t0_receipt=None,
        )


def test_missing_cost_is_unavailable_not_zero(
    portfolio: EditorialPortfolioV3,
) -> None:
    report = build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=_commit(portfolio),
        cost_input=None,
        gsc_input=None,
        ga4_input=None,
        t0_receipt=None,
        generated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )

    assert report["north_star"] == {
        "state": "UNAVAILABLE",
        "reason": "RECONCILED_REWARD_OR_OWNER_COST_MISSING",
    }
    assert report["articles"][0]["cost"]["state"] == "UNAVAILABLE"
    assert report["articles"][0]["freshness"]["gsc"]["retrieved_at"] == ("UNAVAILABLE")
    assert report["t0"] == "UNAVAILABLE"


def test_mixed_periods_block_contribution_profit(
    portfolio: EditorialPortfolioV3,
) -> None:
    costs = _cost_input(portfolio)
    costs["period"] = {"date_from": "2026-08-01", "date_to": "2026-08-04"}

    report = build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=_commit(portfolio),
        cost_input=costs,
        gsc_input=None,
        ga4_input=None,
        t0_receipt=_t0_receipt(portfolio),
        generated_at=datetime(2026, 8, 5, tzinfo=UTC),
    )

    assert report["period_alignment"] == "MISMATCH"
    assert report["period_kind"] == "UNAVAILABLE"
    assert report["north_star"] == {
        "state": "UNAVAILABLE",
        "reason": "PERIOD_MISMATCH",
    }
    assert report["articles"][0]["confirmed_contribution_profit_jpy"] == {
        "state": "UNAVAILABLE",
        "reason": "PERIOD_MISMATCH",
    }


def test_t0_requires_all_exact_successful_production_readbacks(
    portfolio: EditorialPortfolioV3,
) -> None:
    receipt = _t0_receipt(portfolio)

    assert receipt["t0"] == "2026-08-01T00:03:00Z"
    assert receipt["analytics_site_binding"] == {
        "binding_sha256": "e" * 64,
        "ga4_property_id_sha256": "d" * 64,
        "ga4_configuration_response_sha256": "f" * 64,
    }
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    assert receipt["rakuten_activation_binding"]["dry_run_sha256"] == (
        activation_sha256
    )
    assert receipt["derivation"] == "MAX_OF_EARLIEST_SUCCESS_PER_REQUIRED_COMPONENT"
    assert validate_t0_receipt(receipt, portfolio) == "2026-08-01T00:03:00Z"
    assert receipt["automatic_publication"] is False
    incomplete = production_readback_template(portfolio)
    incomplete["owner_attested"] = True
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID",
    ):
        establish_t0_receipt(
            document=incomplete,
            observation_sha256=HASH,
            rakuten_activation=activation,
            rakuten_activation_sha256=activation_sha256,
            expected_portfolio_sha256=portfolio_sha256,
            portfolio=portfolio,
            evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
        )


def test_t0_rejects_ga4_readback_from_a_different_property_binding(
    portfolio: EditorialPortfolioV3,
) -> None:
    document = production_readback_template(portfolio)
    document["owner_attested"] = True
    document["analytics_site_binding"] = {
        "state": "OWNER_PRIVATE_READ_ONLY_BINDING_VERIFIED",
        "binding_sha256": "e" * 64,
        "ga4_property_id_sha256": "d" * 64,
        "ga4_configuration_response_sha256": "f" * 64,
    }
    for row, timestamp in zip(
        document["observations"],
        (
            "2026-08-01T00:01:00Z",
            "2026-08-01T00:02:00Z",
            "2026-08-01T00:03:00Z",
        ),
        strict=True,
    ):
        row["state"] = "SUCCESS"
        row["observed_at"] = timestamp
        row["request_sha256"] = HASH
        row["response_sha256"] = "b" * 64
    document["observations"][0]["details"]["live_link_count"] = 74
    document["observations"][0]["details"]["all_ids_echo_verified"] = True
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    document["observations"][0]["details"]["activation_dry_run_sha256"] = (
        activation_sha256
    )
    document["observations"][0]["details"]["materialized_set_sha256"] = activation[
        "materialized_set_sha256"
    ]
    production = activation["overlays"]["production"]
    document["observations"][0]["details"]["production_posts_sha256"] = (
        production["posts_sha256"]
    )
    document["observations"][0]["details"]["production_article_set_sha256"] = (
        production["article_set_sha256"]
    )
    document["observations"][0]["details"][
        "production_overlay_receipt_sha256"
    ] = production["overlay_receipt_sha256"]
    document["observations"][1]["details"]["http_status"] = 202
    document["observations"][1]["details"]["aggregate_readback_observed"] = True
    document["observations"][1]["details"]["event_id_sha256"] = "c" * 64
    ga4_details = document["observations"][2]["details"]
    ga4_details["property_id_sha256"] = "0" * 64
    ga4_details["configuration_response_sha256"] = "f" * 64
    ga4_details["analytics_site_binding_sha256"] = "e" * 64
    ga4_details["article_id"] = portfolio.articles[0].article_id
    ga4_details["event_observed"] = True

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID",
    ):
        establish_t0_receipt(
            document=document,
            observation_sha256=sha256_bytes(canonical_json_bytes(document)),
            rakuten_activation=activation,
            rakuten_activation_sha256=activation_sha256,
            expected_portfolio_sha256=portfolio_sha256,
            portfolio=portfolio,
            evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
        )


def test_t0_rejects_activation_set_and_live_readback_drift(
    portfolio: EditorialPortfolioV3,
) -> None:
    activation, _activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    tampered_activation = json.loads(json.dumps(activation))
    tampered_activation["overlays"]["production"]["articles"][0][
        "materialized_sha256"
    ] = "9" * 64
    document = production_readback_template(portfolio)

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID",
    ):
        establish_t0_receipt(
            document=document,
            observation_sha256=HASH,
            rakuten_activation=tampered_activation,
            rakuten_activation_sha256=sha256_bytes(
                canonical_json_bytes(tampered_activation)
            ),
            expected_portfolio_sha256=portfolio_sha256,
            portfolio=portfolio,
            evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
        )

    valid_receipt = _t0_receipt(portfolio)
    valid_receipt["rakuten_activation_binding"]["materialized_set_sha256"] = (
        "8" * 64
    )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(valid_receipt, portfolio)


def test_t0_rejects_legacy_unbound_receipt_schema(
    portfolio: EditorialPortfolioV3,
) -> None:
    receipt = _t0_receipt(portfolio)
    receipt["schema"] = "RAOS_EDITORIAL_V3_T0_RECEIPT_V1"
    receipt["version"] = "1.0.0"
    receipt.pop("rakuten_activation_binding")

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(receipt, portfolio)


def test_t0_rejects_legacy_activation_v1_shape(
    portfolio: EditorialPortfolioV3,
) -> None:
    activation, _activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    activation["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V1"
    activation["version"] = "1.0.0"

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_INVALID",
    ):
        establish_t0_receipt(
            document=production_readback_template(portfolio),
            observation_sha256=HASH,
            rakuten_activation=activation,
            rakuten_activation_sha256=sha256_bytes(canonical_json_bytes(activation)),
            expected_portfolio_sha256=portfolio_sha256,
            portfolio=portfolio,
            evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
        )


def _baseline_with_t0(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    return build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=_commit(portfolio),
        cost_input=_cost_input(portfolio),
        gsc_input=_gsc_input(portfolio),
        ga4_input=_ga4_input(portfolio),
        t0_receipt=_t0_receipt(portfolio),
        generated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )


def _baseline_for_period(
    portfolio: EditorialPortfolioV3, *, date_from: str, date_to: str
) -> dict[str, object]:
    rakuten = _commit(portfolio)
    rakuten["period"] = {"date_from": date_from, "date_to": date_to}
    costs = _cost_input(portfolio)
    costs["period"] = {"date_from": date_from, "date_to": date_to}
    gsc = _gsc_input(portfolio)
    gsc["date_from"] = date_from
    gsc["date_to"] = date_to
    gsc["rows"][0]["metric_date"] = date_from
    ga4 = _ga4_input(portfolio)
    ga4["date_from"] = date_from
    ga4["date_to"] = date_to
    ga4["rows"][0]["metric_date"] = date_from
    return build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=rakuten,
        cost_input=costs,
        gsc_input=gsc,
        ga4_input=ga4,
        t0_receipt=_t0_receipt(portfolio),
        generated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def _candidate_query_demand(
    *, date_from: str = "2026-08-02", date_to: str = "2026-08-29"
) -> dict[str, object]:
    document = candidate_query_demand_template()
    document["period"] = {"date_from": date_from, "date_to": date_to}
    document["retrieved_at"] = "2026-08-30T00:00:00Z"
    document["request_sha256"] = HASH
    document["query_cluster_sha256"] = "b" * 64
    document["impressions"] = 200
    document["clicks"] = 1
    return document


def test_followup_reviews_never_auto_pass_and_candidate_defaults_not_eligible(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = _baseline_with_t0(portfolio)
    evaluation = evaluate_followups(
        baseline=baseline,
        baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
        portfolio=portfolio,
        as_of="2026-08-29",
        generated_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    assert evaluation["reviews"]["day_30"]["status"] == "NOT_DUE"
    assert evaluation["reviews"]["day_90"]["status"] == "NOT_DUE"
    assert evaluation["reviews"]["day_30"]["automatic_pass"] is False
    assert evaluation["reviews"]["day_30"]["data_eligible"] is False
    gate = evaluation["new_article_candidate_gate"]
    assert gate["status"] == "NOT_ELIGIBLE"
    assert gate["conditions"]["independent_query_demand_confirmed"] is False
    assert gate["observations"]["impressions"] == "UNAVAILABLE"
    assert gate["automatic_article_creation"] is False
    assert gate["automatic_publication"] is False


def test_followup_gate_can_only_propose_after_all_actual_thresholds(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = _baseline_for_period(
        portfolio, date_from="2026-08-02", date_to="2026-10-31"
    )
    source = next(
        row
        for row in baseline["articles"]
        if row["article_id"] == "solota-vs-rakua-mini-plus"
    )
    source["rakuten_direct_jpy"] = {
        "state": "RECONCILED",
        "PENDING": 0,
        "CONFIRMED": 1,
        "CANCELLED": 0,
    }
    evaluation = evaluate_followups(
        baseline=baseline,
        baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
        portfolio=portfolio,
        as_of="2026-10-31",
        candidate_query_demand=_candidate_query_demand(),
        generated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )

    assert evaluation["reviews"]["day_30"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert evaluation["reviews"]["day_90"]["status"] == "HUMAN_REVIEW_REQUIRED"
    gate = evaluation["new_article_candidate_gate"]
    assert gate["conditions"] == {
        "post_t0_cohort": True,
        "independent_query_demand_confirmed": True,
        "observation_days_ge_28": True,
        "impressions_ge_200": True,
        "measurable_clicks": True,
        "mature_confirmed_result": True,
    }
    assert gate["status"] == "ELIGIBLE_FOR_HUMAN_PROPOSAL"
    assert gate["automatic_pass"] is False
    assert gate["automatic_publication"] is False


def test_coverage_uses_actual_period_range_not_elapsed_time_from_t0(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = _baseline_for_period(
        portfolio, date_from="2026-08-29", date_to="2026-08-29"
    )
    evaluation = evaluate_followups(
        baseline=baseline,
        baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
        portfolio=portfolio,
        as_of="2026-08-30",
        candidate_query_demand=_candidate_query_demand(
            date_from="2026-08-29", date_to="2026-08-29"
        ),
        generated_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    assert evaluation["elapsed_days"] == 29
    assert evaluation["actual_data_coverage_days_after_t0"] == 1
    gate = evaluation["new_article_candidate_gate"]
    assert gate["observations"]["query_demand_coverage_days_after_t0"] == 1
    assert gate["conditions"]["observation_days_ge_28"] is False
    assert gate["status"] == "NOT_ELIGIBLE"


@pytest.mark.parametrize(
    ("date_from", "date_to", "expected_cohort"),
    [
        ("2026-07-01", "2026-07-31", "PRE_T0_BASELINE"),
        ("2026-08-01", "2026-10-31", "MIXED_T0_BOUNDARY"),
    ],
)
def test_pre_t0_and_mixed_cohorts_cannot_drive_reviews_or_candidate_gate(
    portfolio: EditorialPortfolioV3,
    date_from: str,
    date_to: str,
    expected_cohort: str,
) -> None:
    baseline = _baseline_for_period(portfolio, date_from=date_from, date_to=date_to)
    assert baseline["cohort"] == expected_cohort
    evaluation = evaluate_followups(
        baseline=baseline,
        baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
        portfolio=portfolio,
        as_of="2026-10-31",
        candidate_query_demand=_candidate_query_demand(),
        generated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )

    assert evaluation["reviews"]["day_30"]["status"] == ("BLOCKED_NON_POST_T0_COHORT")
    assert evaluation["reviews"]["day_90"]["status"] == ("BLOCKED_NON_POST_T0_COHORT")
    gate = evaluation["new_article_candidate_gate"]
    assert gate["conditions"]["post_t0_cohort"] is False
    assert gate["observations"]["direct_confirmed_reward_jpy"] == "UNAVAILABLE"
    assert gate["status"] == "NOT_ELIGIBLE"


def test_article_impressions_are_never_reused_as_candidate_query_demand(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = _baseline_for_period(
        portfolio, date_from="2026-08-02", date_to="2026-10-31"
    )
    source = next(
        row
        for row in baseline["articles"]
        if row["article_id"] == "solota-vs-rakua-mini-plus"
    )
    source["gsc"] = {
        "state": "OBSERVED",
        "clicks": 50,
        "impressions": 10_000,
        "ctr": 0.005,
        "average_position": 3.0,
    }
    evaluation = evaluate_followups(
        baseline=baseline,
        baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
        portfolio=portfolio,
        as_of="2026-10-31",
        generated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )

    gate = evaluation["new_article_candidate_gate"]
    assert gate["observations"]["impressions"] == "UNAVAILABLE"
    assert gate["observations"]["clicks"] == "UNAVAILABLE"
    assert gate["conditions"]["independent_query_demand_confirmed"] is False
    assert gate["status"] == "NOT_ELIGIBLE"

    reused = _candidate_query_demand()
    reused["article_totals_reused"] = True
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_CANDIDATE_QUERY_DEMAND_INVALID",
    ):
        evaluate_followups(
            baseline=baseline,
            baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
            portfolio=portfolio,
            as_of="2026-10-31",
            candidate_query_demand=reused,
            generated_at=datetime(2026, 11, 1, tzinfo=UTC),
        )


def test_private_reader_requires_0700_root_and_0600_file(tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    source = private_root / "source.csv"
    source.write_bytes(SAMPLE)
    source.chmod(0o600)

    assert hashlib.sha256(
        read_private_bytes(private_root, "source.csv")
    ).hexdigest() == sha256_bytes(SAMPLE)
    source.chmod(0o644)
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PRIVATE_FILE_INVALID",
    ):
        read_private_bytes(private_root, "source.csv")
