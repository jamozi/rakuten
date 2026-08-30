from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from raos.application.analytics.google_live_projection import (
    ga4_baseline_document,
    gsc_baseline_document,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    load_editorial_portfolio_v3,
)
from raos.application.finance.editorial_economics_v3 import (
    summarize_ga4,
    summarize_gsc,
)
from raos.domain.analytics.google_live import (
    GA4_ARTICLE_ID_DIMENSION,
    GA4_BASELINE_DIMENSIONS,
    GA4_BASELINE_METRICS,
    Ga4ImportBatch,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleProviderFailure,
    SearchConsoleImportBatch,
    SearchConsoleObservation,
    canonical_json_bytes,
    sha256_hex,
)


ROOT = Path(__file__).resolve().parents[2]
SITE_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime(2026, 8, 30, 1, 2, 3, tzinfo=timezone.utc)
REQUEST_SHA = "1" * 64
PAGE_SHA = "2" * 64


def test_gsc_projection_is_private_baseline_input_and_strips_url_query() -> None:
    portfolio = load_editorial_portfolio_v3(ROOT)
    article = portfolio.articles[0]
    page_url = (
        f"{portfolio.target_origin}/{article.production_slug}/?utm_source=private"
    )
    dimension_sha = sha256_hex(
        canonical_json_bytes(
            {
                "country": "jpn",
                "date": "2026-08-29",
                "device": "MOBILE",
                "page": page_url,
                "query": "owner private query",
            }
        )
    )
    batch = SearchConsoleImportBatch(
        site_id=SITE_ID,
        site_url="sc-domain:kurashinoshirube.com",
        date_from=date(2026, 8, 29),
        date_to=date(2026, 8, 29),
        request_sha256=REQUEST_SHA,
        page_request_sha256s=(PAGE_SHA,),
        rows=(
            SearchConsoleObservation(
                metric_date=date(2026, 8, 29),
                query_text="owner private query",
                page_url=page_url,
                country_code="jpn",
                device="MOBILE",
                clicks=1,
                impressions=10,
                ctr=0.1,
                average_position=2.5,
                dimension_key_sha256=dimension_sha,
                source_request_sha256=PAGE_SHA,
            ),
        ),
        retrieved_at=NOW,
        provider_row_count=1,
    )

    document = gsc_baseline_document(batch)
    assert document["rows"][0]["page_url"] == (  # type: ignore[index]
        f"{portfolio.target_origin}/{article.production_slug}/"
    )
    summary = summarize_gsc(document, portfolio)
    assert summary["by_article"][article.article_id]["impressions"] == 10  # type: ignore[index]
    assert summary["raw_queries_included"] is False
    assert "owner private query" not in repr(summary)


def _ga4_batch() -> Ga4ImportBatch:
    portfolio = load_editorial_portfolio_v3(ROOT)
    article = portfolio.articles[0]
    configuration_payload = {
        "currency_code": "JPY",
        "display_name": "Kurashi",
        "property_resource": "properties/12345",
        "reporting_identity": "DEVICE_BASED",
        "time_zone": "Asia/Tokyo",
    }
    configuration = Ga4PropertyConfigSnapshot(
        property_id="12345",
        property_resource="properties/12345",
        display_name="Kurashi",
        time_zone="Asia/Tokyo",
        currency_code="JPY",
        reporting_identity="DEVICE_BASED",
        retrieved_at=NOW,
        property_response_sha256="3" * 64,
        reporting_identity_response_sha256="4" * 64,
        snapshot_sha256=sha256_hex(canonical_json_bytes(configuration_payload)),
    )
    dimensions = (
        ("date", "20260829"),
        ("pagePath", f"/{article.production_slug}/"),
        ("eventName", "affiliate_click"),
        ("deviceCategory", "mobile"),
        (GA4_ARTICLE_ID_DIMENSION, article.article_id),
    )
    grain_sha = sha256_hex(
        canonical_json_bytes(
            {"date": "2026-08-29", "dimensions": dict(dimensions)}
        )
    )
    return Ga4ImportBatch(
        site_id=SITE_ID,
        property_id="12345",
        date_from=date(2026, 8, 29),
        date_to=date(2026, 8, 29),
        dimensions=GA4_BASELINE_DIMENSIONS,
        metrics=GA4_BASELINE_METRICS,
        request_sha256=REQUEST_SHA,
        page_request_sha256s=(PAGE_SHA,),
        rows=(
            Ga4Observation(
                metric_date=date(2026, 8, 29),
                dimensions=dimensions,
                metrics=(
                    ("eventCount", "3"),
                    ("sessions", "2"),
                    ("totalUsers", "2"),
                ),
                grain_key_sha256=grain_sha,
                source_request_sha256=PAGE_SHA,
                is_thresholded=False,
            ),
        ),
        configuration=configuration,
        retrieved_at=NOW,
        provider_row_count=1,
        subject_to_thresholding=False,
        data_loss_from_other_row=False,
    )


def test_ga4_projection_normalizes_approved_article_dimension_and_round_trips() -> (
    None
):
    portfolio = load_editorial_portfolio_v3(ROOT)
    article = portfolio.articles[0]
    batch = _ga4_batch()

    document = ga4_baseline_document(batch)
    dimensions = document["rows"][0]["dimensions"]  # type: ignore[index]
    assert {row["name"] for row in dimensions} >= {"article_id", "eventName"}
    assert GA4_ARTICLE_ID_DIMENSION not in {row["name"] for row in dimensions}
    summary = summarize_ga4(document, portfolio)
    assert summary["by_article"][article.article_id]["events"] == {  # type: ignore[index]
        "affiliate_click": 3
    }


def test_ga4_projection_fails_closed_before_article_dimension_is_approved() -> None:
    batch = replace(
        _ga4_batch(),
        dimensions=("date", "pagePath", "eventName", "deviceCategory"),
    )
    with pytest.raises(GoogleProviderFailure):
        ga4_baseline_document(batch)
