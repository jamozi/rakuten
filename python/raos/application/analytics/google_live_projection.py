"""Owner-private baseline projections for committed live Google imports."""

from __future__ import annotations

from datetime import datetime
import re
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from raos.domain.analytics.google_live import (
    GA4_EVENT_CUSTOM_DIMENSIONS,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_PURCHASE_DIMENSIONS_V2,
    GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2,
    GA4_PURCHASE_EVENT_PARAMETER_NAMES_V2,
    Ga4ImportBatch,
    GoogleProviderFailureCode,
    SearchConsoleImportBatch,
    SearchConsoleUrlInspectionBatch,
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


def gsc_url_inspection_document(
    batch: SearchConsoleUrlInspectionBatch,
) -> dict[str, object]:
    """Project the exact URL Inspection batch into the SEO private input schema."""

    if type(batch) is not SearchConsoleUrlInspectionBatch:
        fail_google()
    return {
        "schema": "RAOS_OWNER_PRIVATE_URL_INSPECTION_V1",
        "version": 1,
        "source": "GSC_URL_INSPECTION_API_V1",
        "site_id": str(batch.site_id),
        "site_url": batch.site_url,
        "observed_at": _utc_text(batch.retrieved_at),
        "request_sha256": batch.request_sha256,
        "result_count": len(batch.results),
        "results": [
            {
                "url": result.inspected_url,
                "state": result.state,
                "verdict": result.verdict,
                "indexing_state": result.indexing_state,
                "last_crawl_at": result.last_crawl_at,
                "request_sha256": result.source_request_sha256,
                "response_sha256": result.provider_response_sha256,
            }
            for result in batch.results
        ],
    }


def ga4_baseline_document(batch: Ga4ImportBatch) -> dict[str, object]:
    """Normalize the approved GA4 article custom dimension for economics input."""

    if (
        type(batch) is not Ga4ImportBatch
        or not set(GA4_EVENT_CUSTOM_DIMENSIONS).issubset(batch.dimensions)
        or set(GA4_EVENT_PARAMETER_NAMES) & set(batch.dimensions)
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
                "name": (
                    name.removeprefix("customEvent:")
                    if name in GA4_EVENT_CUSTOM_DIMENSIONS
                    else name
                ),
                "value": value,
            }
            for name, value in row.dimensions
        ]
        normalized_names = {item["name"] for item in normalized_dimensions}
        if not set(GA4_EVENT_PARAMETER_NAMES).issubset(normalized_names):
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
            "required_event_custom_dimensions": list(GA4_EVENT_PARAMETER_NAMES),
            "retrieved_at": _utc_text(configuration.retrieved_at),
            "response_sha256": response_sha256,
        },
        "rows": rows,
    }


__all__ = [
    "ga4_baseline_document",
    "gsc_baseline_document",
    "gsc_url_inspection_document",
]


def ga4_purchase_document_v2(
    batch: Ga4ImportBatch,
    *,
    page_views: Ga4ImportBatch,
) -> dict[str, object]:
    """Keep CTA counts and article page-view sessions at their own query grains."""
    if (
        type(batch) is not Ga4ImportBatch
        or batch.dimensions != GA4_PURCHASE_DIMENSIONS_V2
        or type(page_views) is not Ga4ImportBatch
        or page_views.dimensions != GA4_PURCHASE_PAGE_VIEW_DIMENSIONS_V2
        or (batch.site_id, batch.property_id, batch.date_from, batch.date_to)
        != (
            page_views.site_id,
            page_views.property_id,
            page_views.date_from,
            page_views.date_to,
        )
    ):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    document = ga4_baseline_document(batch)
    document["schema_version"] = 2
    document["profile"] = "purchase-support-v2"
    cast(dict[str, object], document["configuration"])[
        "required_event_custom_dimensions"
    ] = list(GA4_PURCHASE_EVENT_PARAMETER_NAMES_V2)
    excluded: dict[str, dict[str, int]] = {"offer_click": {}, "page_view": {}}
    click_rows = []
    for row in batch.rows:
        dimensions = {
            key.removeprefix("customEvent:"): value for key, value in row.dimensions
        }
        reason = _purchase_row_scope(dimensions, "offer_click")
        if reason is not None:
            excluded["offer_click"][reason] = excluded["offer_click"].get(reason, 0) + 1
            continue
        _purchase_identity(dimensions, GA4_PURCHASE_EVENT_PARAMETER_NAMES_V2)
        if dimensions["placement"] not in {
            "top_summary",
            "comparison_table",
            "product_card",
            "final_summary",
        }:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        # CTA sessions cannot form a denominator and are omitted.
        click_rows.append(
            {
                "metric_date": row.metric_date.isoformat(),
                "dimensions": [
                    {"name": key, "value": value} for key, value in dimensions.items()
                ],
                "metrics": [
                    {"name": key, "value": value}
                    for key, value in row.metrics
                    if key == "eventCount"
                ],
                "grain_sha256": row.grain_key_sha256,
                "request_sha256": row.source_request_sha256,
                "is_thresholded": row.is_thresholded,
            }
        )
    view_rows = []
    for row in page_views.rows:
        dimensions = {
            key.removeprefix("customEvent:"): value for key, value in row.dimensions
        }
        reason = _purchase_row_scope(dimensions, "page_view")
        if reason is not None:
            excluded["page_view"][reason] = excluded["page_view"].get(reason, 0) + 1
            continue
        _purchase_identity(dimensions, ("article_id", "snapshot_id"))
        view_rows.append(
            {
                "metric_date": row.metric_date.isoformat(),
                "dimensions": [
                    {"name": key, "value": value} for key, value in dimensions.items()
                ],
                "metrics": [
                    {"name": key, "value": value} for key, value in row.metrics
                ],
                "grain_sha256": row.grain_key_sha256,
                "request_sha256": row.source_request_sha256,
                "is_thresholded": row.is_thresholded,
            }
        )
    document["rows"] = click_rows
    document["row_count"] = len(click_rows)
    document["page_view_rows"] = view_rows
    document["page_view_request_sha256"] = page_views.request_sha256
    document["subject_to_thresholding"] = (
        batch.subject_to_thresholding or page_views.subject_to_thresholding
    )
    document["data_loss_from_other_row"] = (
        batch.data_loss_from_other_row or page_views.data_loss_from_other_row
    )
    document["excluded_row_counts"] = excluded
    document["scope_status"] = (
        "PARTIAL_SCOPE_UNKNOWN"
        if any("UNATTRIBUTED_SCOPE" in reasons for reasons in excluded.values())
        else "OBSERVED_ROWS_ONLY"
        if click_rows or view_rows
        else "NO_PURCHASE_OBSERVATIONS"
    )
    document["purchase_and_reward"] = "UNAVAILABLE"
    return document


def _purchase_row_scope(dimensions: dict[str, str], event: str) -> str | None:
    """Quarantine explicit other profiles; unidentified scope is never success."""
    _purchase_identity(dimensions, ("eventName",))
    if dimensions["eventName"] != event:
        return "OTHER_EVENT"
    snapshot = dimensions.get("snapshot_id", "")
    if re.fullmatch(r"ps-[0-9a-f]{32}", snapshot):
        return None
    missing = {"", "(NOT SET)", "UNKNOWN", "UNAVAILABLE"}
    if snapshot.upper() in missing:
        if all(
            dimensions.get(key, "").upper() in missing
            for key in GA4_PURCHASE_EVENT_PARAMETER_NAMES_V2
        ):
            return "UNATTRIBUTED_SCOPE"
        # Populated IDs with missing snapshot cannot safely be assigned elsewhere.
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    if snapshot.lower().startswith("ps-"):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    _purchase_identity(dimensions, ("snapshot_id",))
    return "NON_PURCHASE_SNAPSHOT"


def _purchase_identity(dimensions: dict[str, str], keys: tuple[str, ...]) -> None:
    if any(
        key not in dimensions
        or dimensions[key].upper() in {"UNKNOWN", "UNAVAILABLE"}
        or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", dimensions[key]) is None
        for key in keys
    ):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
