"""Owner-private baseline projections for committed live Google imports."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from raos.domain.analytics.google_live import (
    GA4_ARTICLE_ID_DIMENSION,
    Ga4ImportBatch,
    GoogleProviderFailureCode,
    SearchConsoleImportBatch,
    canonical_json_bytes,
    fail_google,
    sha256_hex,
)


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_page_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def gsc_baseline_document(batch: SearchConsoleImportBatch) -> dict[str, object]:
    """Project one committed GSC batch without exposing it outside private storage."""

    if type(batch) is not SearchConsoleImportBatch:
        fail_google()
    return {
        "schema_version": 1,
        "source": "GSC",
        "site_id": str(batch.site_id),
        "date_from": batch.date_from.isoformat(),
        "date_to": batch.date_to.isoformat(),
        "retrieved_at": _utc_text(batch.retrieved_at),
        "request_sha256": batch.request_sha256,
        "row_count": batch.provider_row_count,
        "rows": [
            {
                "metric_date": row.metric_date.isoformat(),
                "query_text": row.query_text,
                "page_url": _canonical_page_url(row.page_url),
                "country_code": row.country_code,
                "device": row.device,
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr": row.ctr,
                "average_position": row.average_position,
                "request_sha256": row.source_request_sha256,
            }
            for row in batch.rows
        ],
    }


def ga4_baseline_document(batch: Ga4ImportBatch) -> dict[str, object]:
    """Normalize the approved GA4 article custom dimension for economics input."""

    if (
        type(batch) is not Ga4ImportBatch
        or GA4_ARTICLE_ID_DIMENSION not in batch.dimensions
        or "article_id" in batch.dimensions
    ):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    configuration = batch.configuration
    response_sha256 = sha256_hex(
        canonical_json_bytes(
            {
                "property": configuration.property_response_sha256,
                "reporting_identity": (
                    configuration.reporting_identity_response_sha256
                ),
            }
        )
    )
    rows: list[dict[str, object]] = []
    for row in batch.rows:
        normalized_dimensions = [
            {
                "name": "article_id" if name == GA4_ARTICLE_ID_DIMENSION else name,
                "value": value,
            }
            for name, value in row.dimensions
        ]
        if sum(
            item["name"] == "article_id" for item in normalized_dimensions
        ) != 1:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        rows.append(
            {
                "metric_date": row.metric_date.isoformat(),
                "dimensions": normalized_dimensions,
                "metrics": [
                    {"name": name, "value": value} for name, value in row.metrics
                ],
                "grain_sha256": row.grain_key_sha256,
                "is_thresholded": row.is_thresholded,
                "request_sha256": row.source_request_sha256,
            }
        )
    return {
        "schema_version": 1,
        "source": "GA4",
        "site_id": str(batch.site_id),
        "date_from": batch.date_from.isoformat(),
        "date_to": batch.date_to.isoformat(),
        "retrieved_at": _utc_text(batch.retrieved_at),
        "request_sha256": batch.request_sha256,
        "row_count": batch.provider_row_count,
        "configuration": {
            "property_id": configuration.property_id,
            "property_resource": configuration.property_resource,
            "display_name": configuration.display_name,
            "time_zone": configuration.time_zone,
            "currency_code": configuration.currency_code,
            "reporting_identity": configuration.reporting_identity,
            "retrieved_at": _utc_text(configuration.retrieved_at),
            "response_sha256": response_sha256,
        },
        "rows": rows,
    }


__all__ = ["ga4_baseline_document", "gsc_baseline_document"]
