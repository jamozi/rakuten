from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from raos.application.editorial.editorial_portfolio_v3 import (
    EditorialPortfolioV3,
    load_editorial_portfolio_v3,
)
from raos.application.finance.editorial_economics_v3 import (
    EditorialEconomicsV3Failure,
    bind_rakuten_profile,
    build_baseline_report,
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
            "retrieved_at": "2026-08-04T00:00:00Z",
            "response_sha256": HASH,
        },
        "rows": [
            {
                "metric_date": "2026-08-02",
                "dimensions": [
                    {"name": "article_id", "value": article.article_id},
                    {"name": "eventName", "value": "affiliate_click"},
                ],
                "metrics": [{"name": "eventCount", "value": "3"}],
                "grain_sha256": HASH,
                "is_thresholded": False,
                "request_sha256": HASH,
            }
        ],
    }


def _t0_receipt(portfolio: EditorialPortfolioV3) -> dict[str, object]:
    document = production_readback_template(portfolio)
    document["owner_attested"] = True
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
    document["observations"][1]["details"]["http_status"] = 202
    document["observations"][1]["details"]["aggregate_readback_observed"] = True
    document["observations"][1]["details"]["event_id_sha256"] = "c" * 64
    document["observations"][2]["details"]["property_id_sha256"] = "d" * 64
    document["observations"][2]["details"]["article_id"] = portfolio.articles[
        0
    ].article_id
    document["observations"][2]["details"]["event_observed"] = True
    return establish_t0_receipt(
        document=document,
        observation_sha256=sha256_bytes(canonical_json_bytes(document)),
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
    assert len(report["t0_receipt_sha256"]) == 64
    assert report["north_star"]["value_jpy"] == -1900
    assert report["north_star"]["monthly_north_star_eligible"] is False
    assert report["north_star"]["unattributed_reward_allocated_to_articles"] is False
    assert first["gsc"]["impressions"] == 10
    assert first["ga4"]["events"] == {"affiliate_click": 3}
    assert first["confirmed_contribution_profit_jpy"]["value_jpy"] == -1900
    serialized = json.dumps(report, ensure_ascii=False)
    assert "owner-private fixture query" not in serialized
    html = render_baseline_html(report).decode()
    assert "noindex,nofollow" in html
    assert "owner-private fixture query" not in html


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
    gate = evaluation["new_article_candidate_gate"]
    assert gate["status"] == "NOT_ELIGIBLE"
    assert gate["automatic_article_creation"] is False
    assert gate["automatic_publication"] is False


def test_followup_gate_can_only_propose_after_all_actual_thresholds(
    portfolio: EditorialPortfolioV3,
) -> None:
    baseline = _baseline_with_t0(portfolio)
    baseline["period"]["date_to"] = "2026-10-31"
    source = next(
        row
        for row in baseline["articles"]
        if row["article_id"] == "solota-vs-rakua-mini-plus"
    )
    source["gsc"] = {
        "state": "OBSERVED",
        "clicks": 1,
        "impressions": 200,
        "ctr": 0.005,
        "average_position": 10.0,
    }
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
        generated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )

    assert evaluation["reviews"]["day_30"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert evaluation["reviews"]["day_90"]["status"] == "HUMAN_REVIEW_REQUIRED"
    gate = evaluation["new_article_candidate_gate"]
    assert gate["conditions"] == {
        "observation_days_ge_28": True,
        "impressions_ge_200": True,
        "measurable_clicks": True,
        "mature_confirmed_result": True,
    }
    assert gate["status"] == "ELIGIBLE_FOR_HUMAN_PROPOSAL"
    assert gate["automatic_pass"] is False
    assert gate["automatic_publication"] is False


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
