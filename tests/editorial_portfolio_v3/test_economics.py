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
    BASELINE_INCOMPLETE_STATE,
    EditorialEconomicsV3Failure,
    TRUSTED_T0_EVIDENCE_REQUIRED,
    _derive_unsigned_t0_candidate,
    bind_rakuten_profile,
    build_baseline_report,
    candidate_query_demand_template,
    canonical_json_bytes,
    commit_rakuten_report,
    cost_input_template,
    detect_rakuten_sample,
    establish_t0_receipt as _establish_t0_receipt,
    evaluate_followups,
    parse_rakuten_report,
    production_readback_template,
    rakuten_binding_template,
    read_private_bytes,
    render_baseline_html,
    sha256_bytes,
    validate_t0_publication_receipts,
    validate_t0_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
HASH = "a" * 64
SAMPLE_MEASUREMENT_ID = "fixture-provider-slot-a01-card"
SAMPLE = (
    "synthetic export explanation\n"
    "\n"
    "fixture_summary_key,fixture_summary_value\n"
    "synthetic,total\n"
    "\n"
    "fixture_id,fixture_state,fixture_reward,fixture_measurement,fixture_day,fixture_currency\n"
    f"row-1,P,100,{SAMPLE_MEASUREMENT_ID},2026-08-01,JPY\n"
    f"row-2,C,200,{SAMPLE_MEASUREMENT_ID},2026-08-02,JPY\n"
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
        detection,
        detection_sha256=sha256_bytes(detection_content),
        portfolio=portfolio,
    )
    request["owner_verified_sanitized_real_sample"] = True
    request["provider_measurement_id_echo_verified_in_provider_report"] = True
    selected_section = detection["sections"][1]
    request["section_selection"] = {
        "section_index": selected_section["section_index"],
        "header_row_index": selected_section["header_row_index"],
        "section_sha256": selected_section["section_sha256"],
    }
    for index, row in enumerate(request["provider_slots"], start=1):
        row["rakuten_measurement_id"] = (
            SAMPLE_MEASUREMENT_ID
            if row["provider_slot_id"] == "rps-a01-card"
            else f"fixture-provider-measurement-{index:02d}"
        )
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
        portfolio=portfolio,
    )


def test_profile_binding_requires_owner_attestation_and_real_echo(
    portfolio: EditorialPortfolioV3,
) -> None:
    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    detection_content = canonical_json_bytes(detection)
    request = rakuten_binding_template(
        detection,
        detection_sha256=sha256_bytes(detection_content),
        portfolio=portfolio,
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


def test_detection_selects_one_rectangular_section_from_multi_table_export(
    portfolio: EditorialPortfolioV3,
) -> None:
    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    template = rakuten_binding_template(
        detection,
        detection_sha256=sha256_bytes(canonical_json_bytes(detection)),
        portfolio=portfolio,
    )

    assert detection["schema"] == "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V2"
    assert [section["section_index"] for section in detection["sections"]] == [0, 1]
    assert [section["column_count"] for section in detection["sections"]] == [2, 6]
    assert template["section_selection"] == {
        "section_index": None,
        "header_row_index": None,
        "section_sha256": None,
    }
    assert template["provider_slot_count"] == 20
    assert template["provider_measurement_id_count"] == 20
    assert len(template["provider_slots"]) == 20


def test_detection_ignores_rectangular_summary_with_merged_heading_cells() -> None:
    sample = (
        "export explanation\n"
        "\n"
        "summary,,,range\n"
        "one,two,three,four\n"
        "\n"
        "detail_id,state,reward,measurement,day,currency\n"
        "row-1,P,100,fixture-id,2026-08-01,JPY\n"
    ).encode()

    detection = detect_rakuten_sample(
        sample, encoding="utf-8-sig", delimiter_name="comma"
    )

    assert detection["physical_row_count"] == 7
    assert len(detection["sections"]) == 1
    assert detection["sections"][0]["header_row_index"] == 5
    assert detection["sections"][0]["column_count"] == 6


def test_legacy_detection_bind_request_and_profile_versions_fail_closed(
    portfolio: EditorialPortfolioV3,
) -> None:
    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    legacy_detection = json.loads(json.dumps(detection))
    legacy_detection["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_SCHEMA_DETECTION_V1"
    legacy_detection["version"] = "1.0.0"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_DETECTION_INVALID",
    ):
        rakuten_binding_template(
            legacy_detection,
            detection_sha256=HASH,
            portfolio=portfolio,
        )

    profile, request = _profile(portfolio)
    detection_content = canonical_json_bytes(detection)
    legacy_request = json.loads(json.dumps(request))
    legacy_request["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_BIND_REQUEST_V1"
    legacy_request["version"] = "1.0.0"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID",
    ):
        bind_rakuten_profile(
            sample_content=SAMPLE,
            detection=detection,
            detection_content_sha256=sha256_bytes(detection_content),
            request=legacy_request,
            portfolio=portfolio,
        )

    legacy_profile = json.loads(json.dumps(profile))
    legacy_profile["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_PROFILE_V1"
    legacy_profile["version"] = "1.0.0"
    legacy_profile["parser_version"] = "rakuten-sanitized-csv.v1"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PROFILE_INVALID",
    ):
        parse_rakuten_report(
            content=SAMPLE,
            profile=legacy_profile,
            profile_sha256=HASH,
            portfolio=portfolio,
        )


def test_provider_mapping_is_one_to_one_and_internal_cta_ids_are_not_direct(
    portfolio: EditorialPortfolioV3,
) -> None:
    profile, request = _profile(portfolio)
    assert profile["provider_slot_count"] == 20
    assert profile["provider_measurement_id_count"] == 20
    assert len(profile["provider_slots"]) == 20

    detection = detect_rakuten_sample(
        SAMPLE, encoding="utf-8-sig", delimiter_name="comma"
    )
    duplicate_mapping = json.loads(json.dumps(request))
    duplicate_mapping["provider_slots"][1]["rakuten_measurement_id"] = (
        duplicate_mapping["provider_slots"][0]["rakuten_measurement_id"]
    )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_BIND_REQUEST_INVALID",
    ):
        bind_rakuten_profile(
            sample_content=SAMPLE,
            detection=detection,
            detection_content_sha256=sha256_bytes(canonical_json_bytes(detection)),
            request=duplicate_mapping,
            portfolio=portfolio,
        )

    internal_cta_id = portfolio.articles[0].cta_bindings[0].cta_id
    internal_cta_report = SAMPLE.replace(
        SAMPLE_MEASUREMENT_ID.encode(), internal_cta_id.encode()
    )
    parsed = parse_rakuten_report(
        content=internal_cta_report,
        profile=profile,
        profile_sha256=sha256_bytes(canonical_json_bytes(profile)),
        portfolio=portfolio,
    )
    assert parsed["attribution"]["DIRECT"]["totals_jpy"] == {
        "PENDING": 0,
        "CONFIRMED": 0,
        "CANCELLED": 0,
    }
    assert parsed["unmatched_measurement_row_count"] == 3


def test_report_section_position_and_header_are_bound_exactly(
    portfolio: EditorialPortfolioV3,
) -> None:
    profile, _request = _profile(portfolio)
    shifted = SAMPLE.replace(
        b"\n\nfixture_id,",
        b"\n\nsecond synthetic explanation\n\nfixture_id,",
    )

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_REPORT_HEADER_MISMATCH",
    ):
        parse_rakuten_report(
            content=shifted,
            profile=profile,
            profile_sha256=HASH,
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
    direct_by_slot = dry_run["direct_by_provider_slot_jpy"]
    assert set(direct_by_slot) == set(portfolio.provider_slot_by_id)
    assert len(direct_by_slot) == 20
    assert direct_by_slot["rps-a01-card"] == {
        "PENDING": 100,
        "CONFIRMED": 200,
        "CANCELLED": 0,
    }
    assert all(
        row == {"PENDING": 0, "CONFIRMED": 0, "CANCELLED": 0}
        for provider_slot_id, row in direct_by_slot.items()
        if provider_slot_id != "rps-a01-card"
    )
    assert not {
        binding.cta_id
        for article in portfolio.articles
        for binding in article.cta_bindings
    }.intersection(direct_by_slot)
    assert dry_run["unmatched_measurement_row_count"] == 1
    assert dry_run["raw_rows_persisted"] is False


def test_commit_requires_exact_source_and_provider_reconciliation(
    portfolio: EditorialPortfolioV3,
) -> None:
    dry_run, _profile_document = _dry_run(portfolio)
    committed = _commit(portfolio)

    assert committed["state"] == "COMMITTED_OWNER_PRIVATE_RECONCILED"
    assert committed["schema"] == "RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_V2"
    assert committed["reconciliation"]["status"] == "PASS"
    assert len(committed["direct_by_provider_slot_jpy"]) == 20
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
            portfolio=portfolio,
        )

    tampered = json.loads(json.dumps(dry_run))
    tampered["direct_by_provider_slot_jpy"]["rps-a01-card"]["PENDING"] = 0
    tampered["direct_by_provider_slot_jpy"]["rps-a02-card"]["PENDING"] = 100
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED",
    ):
        commit_rakuten_report(
            dry_run=tampered,
            reparsed=tampered,
            expected_source_sha256=sha256_bytes(SAMPLE),
            provider_row_count=3,
            provider_totals_jpy={
                "PENDING": 100,
                "CONFIRMED": 200,
                "CANCELLED": 50,
            },
            portfolio=portfolio,
        )

    legacy_cta_attribution = json.loads(json.dumps(dry_run))
    legacy_cta_attribution["direct_by_cta_jpy"] = {}
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_COMMIT_PRECONDITION_FAILED",
    ):
        commit_rakuten_report(
            dry_run=legacy_cta_attribution,
            reparsed=legacy_cta_attribution,
            expected_source_sha256=sha256_bytes(SAMPLE),
            provider_row_count=3,
            provider_totals_jpy={
                "PENDING": 100,
                "CONFIRMED": 200,
                "CANCELLED": 50,
            },
            portfolio=portfolio,
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
            portfolio=portfolio,
        )

    legacy_commit = json.loads(json.dumps(committed))
    legacy_commit["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_V1"
    legacy_commit["version"] = "1.0.0"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_RAKUTEN_COMMIT_INVALID",
    ):
        build_baseline_report(
            portfolio=portfolio,
            rakuten_commit=legacy_commit,
            cost_input=None,
            gsc_input=None,
            ga4_input=None,
            t0_receipt=None,
        )


def test_duplicate_and_formula_like_rows_fail_closed(
    portfolio: EditorialPortfolioV3,
) -> None:
    profile, _request = _profile(portfolio)
    profile_sha = sha256_bytes(canonical_json_bytes(profile))
    duplicate = (
        SAMPLE + (f"row-1,C,1,{SAMPLE_MEASUREMENT_ID},2026-08-03,JPY\n").encode()
    )
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
    provider_slot_rows = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "article_id": slot.article_id,
            "placement": slot.placement,
        }
        for slot in sorted(
            portfolio.provider_slots, key=lambda value: value.provider_slot_id
        )
    ]
    provider_measurement_rows = [
        {
            "provider_slot_id": slot.provider_slot_id,
            "rakuten_measurement_id": f"fixture-activation-{index:02d}",
        }
        for index, slot in enumerate(
            sorted(portfolio.provider_slots, key=lambda value: value.provider_slot_id),
            start=1,
        )
    ]
    provider_slot_set_sha256 = sha256_bytes(canonical_json_bytes(provider_slot_rows))
    provider_measurement_binding_sha256 = sha256_bytes(
        canonical_json_bytes(provider_measurement_rows)
    )
    v2_materialization: dict[str, object] = {
        "portfolio_sha256": "3" * 64,
        "evidence_status_sha256": "4" * 64,
        "manufacturer_sales_state_sha256": "7" * 64,
        "manufacturer_sales_state_checked_at_utc": "2026-08-01T00:00:00Z",
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
            source_sha256 = sha256_bytes(f"{mode}:source:{article.article_id}".encode())
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
            "schema": "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V2",
            "version": "2.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": v2_materialization["portfolio_sha256"],
            "v2_evidence_status_sha256": v2_materialization[
                "evidence_status_sha256"
            ],
            "v2_manufacturer_sales_state_sha256": v2_materialization[
                "manufacturer_sales_state_sha256"
            ],
            "v2_manufacturer_sales_state_checked_at_utc": v2_materialization[
                "manufacturer_sales_state_checked_at_utc"
            ],
            "v2_materialization_receipt_sha256": v2_receipt_sha256,
            "posts_sha256": posts_sha256,
            "article_set_sha256": article_set_sha256,
            "article_count": len(article_rows),
            "provider_slot_count": len(provider_slot_rows),
            "provider_measurement_id_count": len(provider_measurement_rows),
            "internal_cta_identity_count": cta_count,
            "live_link_count": cta_count,
            "cta_count": cta_count,
            "provider_slot_set_sha256": provider_slot_set_sha256,
            "provider_measurement_binding_sha256": (
                provider_measurement_binding_sha256
            ),
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
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_MEASUREMENT_DRY_RUN_V3",
        "version": "3.0.0",
        "state": "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED",
        "portfolio_sha256": portfolio_sha256,
        "admin_receipt_sha256": "1" * 64,
        "money_link_mapping_sha256": "2" * 64,
        "activation_inputs": {
            "admin_receipt_name": "admin-receipt.json",
            "money_link_mapping_name": "money-links.json",
            "mapping_generated_at_utc": "2026-08-01T00:00:00Z",
            "admin_verified_at_utc": "2026-08-01T00:05:00Z",
            "activated_at_utc": "2026-08-01T00:06:00Z",
        },
        "v2_materialization": v2_materialization,
        "overlays": overlays,
        "materialized_set_sha256": sha256_bytes(canonical_json_bytes(overlay_bindings)),
        "article_count": len(portfolio.articles),
        "provider_slot_count": len(provider_slot_rows),
        "provider_measurement_id_count": len(provider_measurement_rows),
        "internal_cta_identity_count": cta_count,
        "live_link_count": cta_count,
        "cta_count": cta_count,
        "provider_slot_set_sha256": provider_slot_set_sha256,
        "provider_measurement_binding_sha256": provider_measurement_binding_sha256,
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


def _publication_binding() -> dict[str, object]:
    return {
        "separate_admin_apply_receipt_sha256": "6" * 64,
        "separate_admin_apply_state": "APPLIED",
        "separate_admin_verified": True,
        "self_approval_performed": False,
        "publication_receipt_sha256": "7" * 64,
        "publication_receipt_state": "APPLIED",
        "public_readback_receipt_sha256": "8" * 64,
        "public_readback_receipt_state": "READBACK_VERIFIED",
    }


def _fixture_digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _publication_evidence(
    portfolio: EditorialPortfolioV3,
    activation: dict[str, object],
    activation_sha256: str,
    portfolio_sha256: str,
) -> tuple[dict[str, object], dict[str, bytes]]:
    policy_slugs = ["privacy-policy", "advertising-policy", "contact"]
    selected_slugs = sorted(
        [article.production_slug for article in portfolio.articles] + policy_slugs
    )
    selected_documents = {
        slug: ("page" if slug in policy_slugs else "post") for slug in selected_slugs
    }
    desired = {slug: _fixture_digest(f"content:{slug}") for slug in selected_slugs}
    proposals: list[dict[str, object]] = []
    operations: list[dict[str, object]] = []
    for slug in selected_slugs:
        proposal_id = _fixture_digest(f"proposal:{slug}")
        proposal = {
            "kind": "CONTENT_RELEASE",
            "slug": slug,
            "proposal_id": proposal_id,
            "after_sha256": desired[slug],
            "expires_at_gmt": "2026-08-31T01:00:00Z",
            "idempotency_key": _fixture_digest(f"key:{slug}"),
            "post_type": selected_documents[slug],
        }
        operation = {
            "schema": "OperationReceiptV1",
            "proposal_id": proposal_id,
            "operation_id": proposal_id,
            "state": "APPLIED",
            "result_code": "CONTENT_RELEASE_APPLIED",
            "before_sha256": _fixture_digest(f"before:{slug}"),
            "after_sha256": desired[slug],
            "audit_id": _fixture_digest(f"audit:{slug}"),
        }
        proposals.append(proposal)
        operations.append(operation)
    proposal_ids = sorted(operation["proposal_id"] for operation in operations)
    apply_receipt: dict[str, object] = {
        "schema": "ReleaseWaitApplyReceiptV1",
        "batch_token": _fixture_digest("batch-token"),
        "batch_manifest_sha256": _fixture_digest("batch-manifest"),
        "proposal_count": len(proposal_ids),
        "proposal_ids": proposal_ids,
        "state": "APPLIED",
        "receipts": operations,
    }
    apply_content = canonical_json_bytes(apply_receipt)
    production = activation["overlays"]["production"]
    materialization_activation = {
        "dry_run_sha256": activation_sha256,
        "admin_receipt_sha256": activation["admin_receipt_sha256"],
        "money_link_mapping_sha256": activation["money_link_mapping_sha256"],
        "materialized_set_sha256": activation["materialized_set_sha256"],
        "local_article_set_sha256": activation["overlays"]["local"][
            "article_set_sha256"
        ],
        "production_article_set_sha256": production["article_set_sha256"],
        "local_overlay_receipt_sha256": activation["overlays"]["local"][
            "overlay_receipt_sha256"
        ],
        "production_overlay_receipt_sha256": production["overlay_receipt_sha256"],
        "provider_slot_set_sha256": activation["provider_slot_set_sha256"],
        "provider_measurement_binding_sha256": activation[
            "provider_measurement_binding_sha256"
        ],
        "article_count": 10,
        "cta_count": 74,
        "provider_slot_count": 20,
        "provider_measurement_id_count": 20,
        "internal_cta_identity_count": 74,
        "live_link_count": 74,
    }
    runtime_revision = _fixture_digest("theme-runtime-revision")
    theme_tree_sha256 = _fixture_digest("theme-tree")
    public_readback = {
        slug: {
            "url": f"{portfolio.target_origin}/{slug}/",
            "status": 200,
            "canonical_url": f"{portfolio.target_origin}/{slug}/",
            "indexable": True,
            "theme_runtime_revision": runtime_revision,
        }
        for slug in selected_slugs
    }
    operation_by_proposal = {
        operation["proposal_id"]: operation for operation in operations
    }
    content_by_slug = {proposal["slug"]: proposal for proposal in proposals}
    publication_receipt: dict[str, object] = {
        "schema": "RAOS_WORDPRESS_PUBLICATION_REQUEST_RECEIPT_V1",
        "receipt_path_sha256": _fixture_digest("receipt-path"),
        "selected_slugs": selected_slugs,
        "selected_documents": selected_documents,
        "desired_sha256": desired,
        "desired_theme_tree_sha256": theme_tree_sha256,
        "desired_theme_runtime_revision": runtime_revision,
        "state": "APPLIED",
        "attempt_id": _fixture_digest("attempt"),
        "attempt_created_at_gmt": "2026-08-30T23:50:00Z",
        "materialization_binding": {
            "schema": "RAOS_WORDPRESS_MATERIALIZATION_BINDING_V3",
            "portfolio_sha256": portfolio_sha256,
            "articles": {
                article.production_slug: _fixture_digest(
                    f"article:{article.production_slug}"
                )
                for article in portfolio.articles
            },
            "products": {
                product.product_id: {
                    "state": "verified",
                    "provider_binding_sha256": _fixture_digest(
                        f"product:{product.product_id}"
                    ),
                }
                for product in portfolio.products
            },
            "activation": materialization_activation,
        },
        "baselines": {},
        "drafts": {
            slug: {"id": index, "content_sha256": desired[slug]}
            for index, slug in enumerate(selected_slugs, start=1)
        },
        "proposal_keys": {
            f"content:{proposal['slug']}": proposal["idempotency_key"]
            for proposal in proposals
        },
        "proposals": proposals,
        "operation_ids": {proposal_id: proposal_id for proposal_id in proposal_ids},
        "batch_registration": {
            "schema": "RAOSWordPressPublicationBatchV1",
            "batch_token": apply_receipt["batch_token"],
            "batch_manifest_sha256": apply_receipt["batch_manifest_sha256"],
            "expected_theme_tree_sha256": theme_tree_sha256,
            "proposal_count": len(proposal_ids),
            "proposal_ids": proposal_ids,
            "state": "REGISTERED",
            "expires_at_gmt": "2026-08-31T01:00:00Z",
            "review_url": f"{portfolio.target_origin}/wp-admin/",
        },
        "review_url": f"{portfolio.target_origin}/wp-admin/",
        "apply_receipt": apply_receipt,
        "authenticated_readback": {
            "documents": {
                slug: {
                    "id": index,
                    "slug": slug,
                    "post_type": selected_documents[slug],
                    "status": "publish",
                    "content_sha256": content_by_slug[slug]["after_sha256"],
                    "revision_id": index,
                    "modified_gmt": "2026-08-31T00:02:00Z",
                }
                for index, slug in enumerate(selected_slugs, start=1)
            },
            "operations": operation_by_proposal,
            "public_pages": public_readback,
            "theme": {
                "version": "1.4.0",
                "runtime_version": "1.4.0",
                "runtime_revision": runtime_revision,
                "tree_sha256": theme_tree_sha256,
                "proposed": False,
            },
        },
        "prior_applied_reconciliation": None,
        "public_readback": public_readback,
        "updated_at_gmt": "2026-08-31T00:03:00Z",
    }
    publication_content = canonical_json_bytes(publication_receipt)
    public_readback_receipt = {
        "schema": "RAOS_WORDPRESS_PUBLIC_READBACK_RECEIPT_V1",
        "state": "READBACK_VERIFIED",
        "target_origin": portfolio.target_origin,
        "verification_authority": "SEPARATE_ADMIN",
        "self_approval_performed": False,
        "separate_admin_apply_receipt_sha256": sha256_bytes(apply_content),
        "publication_receipt_sha256": sha256_bytes(publication_content),
        "public_readback_sha256": sha256_bytes(canonical_json_bytes(public_readback)),
        "selected_slugs_sha256": sha256_bytes(canonical_json_bytes(selected_slugs)),
        "verified_at": "2026-08-31T00:03:00Z",
    }
    public_readback_content = canonical_json_bytes(public_readback_receipt)
    contents = {
        "separate_admin_apply_receipt_content": apply_content,
        "publication_receipt_content": publication_content,
        "public_readback_receipt_content": public_readback_content,
    }
    binding = validate_t0_publication_receipts(
        **contents,
        expected_target_origin=portfolio.target_origin,
        expected_portfolio_sha256=portfolio_sha256,
        expected_activation_binding={
            "dry_run_sha256": activation_sha256,
            "admin_receipt_sha256": activation["admin_receipt_sha256"],
            "money_link_mapping_sha256": activation["money_link_mapping_sha256"],
            "materialized_set_sha256": activation["materialized_set_sha256"],
            "production_article_set_sha256": production["article_set_sha256"],
            "production_overlay_receipt_sha256": production["overlay_receipt_sha256"],
            "provider_slot_set_sha256": activation["provider_slot_set_sha256"],
            "provider_measurement_binding_sha256": activation[
                "provider_measurement_binding_sha256"
            ],
        },
    )
    return binding, contents


def establish_t0_receipt(
    *,
    document: dict[str, object],
    observation_sha256: str,
    rakuten_activation: dict[str, object],
    rakuten_activation_sha256: str,
    expected_portfolio_sha256: str,
    portfolio: EditorialPortfolioV3,
    evaluated_at: datetime | None = None,
) -> dict[str, object]:
    _binding, contents = _publication_evidence(
        portfolio,
        rakuten_activation,
        rakuten_activation_sha256,
        expected_portfolio_sha256,
    )
    return _establish_t0_receipt(
        document=document,
        observation_sha256=observation_sha256,
        rakuten_activation=rakuten_activation,
        rakuten_activation_sha256=rakuten_activation_sha256,
        expected_portfolio_sha256=expected_portfolio_sha256,
        portfolio=portfolio,
        **contents,
        evaluated_at=evaluated_at,
    )


def _t0_receipt(
    portfolio: EditorialPortfolioV3, *, public_boundary: bool = False
) -> dict[str, object]:
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    document = production_readback_template(portfolio)
    document["owner_attested"] = True
    publication_binding, contents = _publication_evidence(
        portfolio,
        activation,
        activation_sha256,
        portfolio_sha256,
    )
    document["publication_binding"] = publication_binding
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
    document["observations"][0]["details"]["provider_measurement_id_count"] = 20
    document["observations"][0]["details"]["internal_cta_identity_count"] = 74
    document["observations"][0]["details"]["live_link_count"] = 74
    document["observations"][0]["details"][
        "all_provider_measurement_ids_echo_verified"
    ] = True
    document["observations"][0]["details"]["provider_measurement_binding_sha256"] = (
        activation["provider_measurement_binding_sha256"]
    )
    document["observations"][0]["details"]["activation_dry_run_sha256"] = (
        activation_sha256
    )
    document["observations"][0]["details"]["materialized_set_sha256"] = activation[
        "materialized_set_sha256"
    ]
    production = activation["overlays"]["production"]
    document["observations"][0]["details"]["production_posts_sha256"] = production[
        "posts_sha256"
    ]
    document["observations"][0]["details"]["production_article_set_sha256"] = (
        production["article_set_sha256"]
    )
    document["observations"][0]["details"]["production_overlay_receipt_sha256"] = (
        production["overlay_receipt_sha256"]
    )
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
    establish = (
        _establish_t0_receipt if public_boundary else _derive_unsigned_t0_candidate
    )
    return establish(
        document=document,
        observation_sha256=sha256_bytes(canonical_json_bytes(document)),
        rakuten_activation=activation,
        rakuten_activation_sha256=activation_sha256,
        expected_portfolio_sha256=portfolio_sha256,
        portfolio=portfolio,
        **contents,
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
    assert report["state"] == BASELINE_INCOMPLETE_STATE
    assert report["t0"] == "UNAVAILABLE"
    assert report["cohort"] == "PRE_T0_BASELINE"
    assert report["t0_receipt_sha256"] == "UNAVAILABLE"
    assert report["sources"]["t0_receipt"] == TRUSTED_T0_EVIDENCE_REQUIRED
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
    assert BASELINE_INCOMPLETE_STATE in html
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


def test_unsigned_or_modified_t0_never_becomes_an_observed_baseline(
    portfolio: EditorialPortfolioV3,
) -> None:
    unsigned = _t0_receipt(portfolio)
    modified = json.loads(json.dumps(unsigned))
    modified["t0"] = "2026-08-01T00:04:00Z"
    synthetic = {
        "schema": "RAOS_EDITORIAL_V3_T0_RECEIPT_V4",
        "t0": "2026-08-01T00:03:00Z",
    }

    for supplied_t0 in (unsigned, modified, synthetic):
        report = build_baseline_report(
            portfolio=portfolio,
            rakuten_commit=None,
            cost_input=None,
            gsc_input=None,
            ga4_input=None,
            t0_receipt=supplied_t0,
            generated_at=datetime(2026, 8, 4, tzinfo=UTC),
        )

        assert report["state"] == BASELINE_INCOMPLETE_STATE
        assert report["t0"] == "UNAVAILABLE"
        assert report["t0_receipt_sha256"] == "UNAVAILABLE"
        assert report["cohort"] == "PRE_T0_BASELINE"
        assert report["sources"]["t0_receipt"] == (TRUSTED_T0_EVIDENCE_REQUIRED)


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
    assert receipt["schema"] == "RAOS_EDITORIAL_V3_T0_RECEIPT_V4"
    expected_publication_binding, _contents = _publication_evidence(
        portfolio,
        activation,
        activation_sha256,
        portfolio_sha256,
    )
    assert receipt["publication_binding"] == expected_publication_binding
    assert receipt["rakuten_activation_binding"]["provider_slot_count"] == 20
    assert receipt["rakuten_activation_binding"]["provider_measurement_id_count"] == 20
    assert receipt["rakuten_activation_binding"]["internal_cta_identity_count"] == 74
    assert receipt["rakuten_activation_binding"]["live_link_count"] == 74
    rakuten_component = receipt["components"][0]
    assert rakuten_component["provider_slot_count"] == 20
    assert rakuten_component["provider_measurement_id_count"] == 20
    assert rakuten_component["internal_cta_identity_count"] == 74
    assert rakuten_component["live_link_count"] == 74
    assert receipt["derivation"] == "MAX_OF_EARLIEST_SUCCESS_PER_REQUIRED_COMPONENT"
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match=f"^{TRUSTED_T0_EVIDENCE_REQUIRED}$",
    ):
        validate_t0_receipt(receipt, portfolio)
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match=f"^{TRUSTED_T0_EVIDENCE_REQUIRED}$",
    ):
        _t0_receipt(portfolio, public_boundary=True)
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


def test_t0_requires_separate_admin_applied_publication_and_readback_binding(
    portfolio: EditorialPortfolioV3,
) -> None:
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    invalid_bindings: list[dict[str, object]] = []
    missing_hash = _publication_binding()
    missing_hash.pop("separate_admin_apply_receipt_sha256")
    invalid_bindings.append(missing_hash)
    for field, wrong_value in (
        ("separate_admin_verified", False),
        ("self_approval_performed", True),
        ("separate_admin_apply_state", "SELF_APPROVED"),
        ("publication_receipt_state", "WAITING_FOR_APPROVAL"),
        ("public_readback_receipt_state", "NOT_RECORDED"),
        ("public_readback_receipt_sha256", "not-a-hash"),
    ):
        binding = _publication_binding()
        binding[field] = wrong_value
        invalid_bindings.append(binding)

    for publication_binding in invalid_bindings:
        document = production_readback_template(portfolio)
        document["owner_attested"] = True
        document["publication_binding"] = publication_binding
        with pytest.raises(
            EditorialEconomicsV3Failure,
            match="RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INVALID",
        ):
            establish_t0_receipt(
                document=document,
                observation_sha256=HASH,
                rakuten_activation=activation,
                rakuten_activation_sha256=activation_sha256,
                expected_portfolio_sha256=portfolio_sha256,
                portfolio=portfolio,
                evaluated_at=datetime(2026, 8, 4, tzinfo=UTC),
            )

    for field, wrong_value in (
        ("separate_admin_verified", False),
        ("self_approval_performed", True),
        ("publication_receipt_state", "WAITING_FOR_APPROVAL"),
        ("public_readback_receipt_sha256", "0" * 63),
    ):
        receipt = _t0_receipt(portfolio)
        receipt["publication_binding"][field] = wrong_value
        with pytest.raises(
            EditorialEconomicsV3Failure,
            match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
        ):
            validate_t0_receipt(receipt, portfolio)


def test_t0_publication_evidence_requires_exact_files_and_cross_hashes(
    portfolio: EditorialPortfolioV3,
) -> None:
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    _binding, contents = _publication_evidence(
        portfolio,
        activation,
        activation_sha256,
        portfolio_sha256,
    )
    expected_activation_binding = {
        "dry_run_sha256": activation_sha256,
        "admin_receipt_sha256": activation["admin_receipt_sha256"],
        "money_link_mapping_sha256": activation["money_link_mapping_sha256"],
        "materialized_set_sha256": activation["materialized_set_sha256"],
        "production_article_set_sha256": activation["overlays"]["production"][
            "article_set_sha256"
        ],
        "production_overlay_receipt_sha256": activation["overlays"]["production"][
            "overlay_receipt_sha256"
        ],
        "provider_slot_set_sha256": activation["provider_slot_set_sha256"],
        "provider_measurement_binding_sha256": activation[
            "provider_measurement_binding_sha256"
        ],
    }

    publication = json.loads(contents["publication_receipt_content"])
    publication["apply_receipt"]["batch_manifest_sha256"] = "0" * 64
    mismatched_apply = dict(contents)
    mismatched_apply["publication_receipt_content"] = canonical_json_bytes(publication)
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID",
    ):
        validate_t0_publication_receipts(
            **mismatched_apply,
            expected_target_origin=portfolio.target_origin,
            expected_portfolio_sha256=portfolio_sha256,
            expected_activation_binding=expected_activation_binding,
        )

    readback = json.loads(contents["public_readback_receipt_content"])
    readback["publication_receipt_sha256"] = "0" * 64
    mismatched_readback = dict(contents)
    mismatched_readback["public_readback_receipt_content"] = canonical_json_bytes(
        readback
    )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID",
    ):
        validate_t0_publication_receipts(
            **mismatched_readback,
            expected_target_origin=portfolio.target_origin,
            expected_portfolio_sha256=portfolio_sha256,
            expected_activation_binding=expected_activation_binding,
        )

    for field, invalid_value in (
        ("verification_authority", "OWNER"),
        ("self_approval_performed", True),
    ):
        authority_readback = json.loads(contents["public_readback_receipt_content"])
        authority_readback[field] = invalid_value
        invalid_authority = dict(contents)
        invalid_authority["public_readback_receipt_content"] = canonical_json_bytes(
            authority_readback
        )
        with pytest.raises(
            EditorialEconomicsV3Failure,
            match="RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID",
        ):
            validate_t0_publication_receipts(
                **invalid_authority,
                expected_target_origin=portfolio.target_origin,
                expected_portfolio_sha256=portfolio_sha256,
                expected_activation_binding=expected_activation_binding,
            )

    forged_claim_only = {
        "separate_admin_apply_receipt_content": canonical_json_bytes(
            {"schema": "ReleaseWaitApplyReceiptV1", "state": "APPLIED"}
        ),
        "publication_receipt_content": contents["publication_receipt_content"],
        "public_readback_receipt_content": contents["public_readback_receipt_content"],
    }
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_PUBLICATION_EVIDENCE_INVALID",
    ):
        validate_t0_publication_receipts(
            **forged_claim_only,
            expected_target_origin=portfolio.target_origin,
            expected_portfolio_sha256=portfolio_sha256,
            expected_activation_binding=expected_activation_binding,
        )


def test_t0_rejects_provider_id_count_and_live_link_count_conflation(
    portfolio: EditorialPortfolioV3,
) -> None:
    template = production_readback_template(portfolio)
    details = template["observations"][0]["details"]
    assert template["schema"] == "RAOS_EDITORIAL_V3_PRODUCTION_READBACK_INPUT_V4"
    assert details["provider_slot_count"] == 20
    assert details["provider_measurement_id_count"] is None
    assert details["internal_cta_identity_count"] is None
    assert details["live_link_count"] is None
    assert "measurement_ids" not in details

    for field, wrong_value in (
        ("provider_measurement_id_count", 74),
        ("internal_cta_identity_count", 20),
        ("live_link_count", 20),
    ):
        receipt = _t0_receipt(portfolio)
        receipt["components"][0][field] = wrong_value
        with pytest.raises(
            EditorialEconomicsV3Failure,
            match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
        ):
            validate_t0_receipt(receipt, portfolio)

    missing_component_count = _t0_receipt(portfolio)
    missing_component_count["components"][0].pop("internal_cta_identity_count")
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(missing_component_count, portfolio)

    missing_activation_count = _t0_receipt(portfolio)
    missing_activation_count["rakuten_activation_binding"].pop(
        "internal_cta_identity_count"
    )
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(missing_activation_count, portfolio)


def test_t0_rejects_ga4_readback_from_a_different_property_binding(
    portfolio: EditorialPortfolioV3,
) -> None:
    document = production_readback_template(portfolio)
    document["owner_attested"] = True
    document["publication_binding"] = _publication_binding()
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
    document["observations"][0]["details"]["provider_measurement_id_count"] = 20
    document["observations"][0]["details"]["internal_cta_identity_count"] = 74
    document["observations"][0]["details"]["live_link_count"] = 74
    document["observations"][0]["details"][
        "all_provider_measurement_ids_echo_verified"
    ] = True
    activation, activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    document["observations"][0]["details"]["provider_measurement_binding_sha256"] = (
        activation["provider_measurement_binding_sha256"]
    )
    document["observations"][0]["details"]["activation_dry_run_sha256"] = (
        activation_sha256
    )
    document["observations"][0]["details"]["materialized_set_sha256"] = activation[
        "materialized_set_sha256"
    ]
    production = activation["overlays"]["production"]
    document["observations"][0]["details"]["production_posts_sha256"] = production[
        "posts_sha256"
    ]
    document["observations"][0]["details"]["production_article_set_sha256"] = (
        production["article_set_sha256"]
    )
    document["observations"][0]["details"]["production_overlay_receipt_sha256"] = (
        production["overlay_receipt_sha256"]
    )
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
    valid_receipt["rakuten_activation_binding"]["materialized_set_sha256"] = "8" * 64
    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(valid_receipt, portfolio)


def test_t0_rejects_legacy_unbound_receipt_schema(
    portfolio: EditorialPortfolioV3,
) -> None:
    receipt = _t0_receipt(portfolio)
    receipt["schema"] = "RAOS_EDITORIAL_V3_T0_RECEIPT_V3"
    receipt["version"] = "3.0.0"

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match="RAOS_EDITORIAL_V3_T0_RECEIPT_INVALID",
    ):
        validate_t0_receipt(receipt, portfolio)


def test_t0_rejects_legacy_activation_v2_shape(
    portfolio: EditorialPortfolioV3,
) -> None:
    activation, _activation_sha256, portfolio_sha256 = _rakuten_activation(portfolio)
    activation["schema"] = "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2"
    activation["version"] = "2.0.0"

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


def test_followups_reject_unsigned_or_modified_baseline_at_public_boundary(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = build_baseline_report(
        portfolio=portfolio,
        rakuten_commit=_commit(portfolio),
        cost_input=_cost_input(portfolio),
        gsc_input=_gsc_input(portfolio),
        ga4_input=_ga4_input(portfolio),
        t0_receipt=_t0_receipt(portfolio),
        generated_at=datetime(2026, 8, 4, tzinfo=UTC),
    )
    baseline["t0"] = "2026-08-01T00:04:00Z"

    with pytest.raises(
        EditorialEconomicsV3Failure,
        match=f"^{TRUSTED_T0_EVIDENCE_REQUIRED}$",
    ):
        evaluate_followups(
            baseline=baseline,
            baseline_sha256=sha256_bytes(canonical_json_bytes(baseline)),
            portfolio=portfolio,
            as_of="2026-08-29",
            generated_at=datetime(2026, 8, 30, tzinfo=UTC),
        )


def test_candidate_query_template_remains_non_observed_and_private() -> None:
    document = candidate_query_demand_template()

    assert document["period"] == {"date_from": None, "date_to": None}
    assert document["impressions"] is None
    assert document["clicks"] is None
    assert document["raw_queries_included"] is False
    assert document["article_totals_reused"] is False


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
