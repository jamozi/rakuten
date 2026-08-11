"""Strict caller-bytes adapter for the three recorded ST-1204 GA4 fixtures."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from threading import RLock
from typing import NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.domain.analytics.ga4 import (
    EXACT_DIMENSIONS,
    EXACT_METRICS,
    INTERNAL_REQUEST_SHA256,
    REPORTING_IDENTITY_SHA256,
    SYNTHETIC_PROPERTY_RESOURCE,
    WIRE_REQUEST_SHA256,
    Ga4FailureCode,
    Ga4MetricRow,
    Ga4PropertyConfigSnapshot,
    Ga4QuotaCounter,
    Ga4RecordedExchange,
    Ga4RecordedImportCommand,
    Ga4RecordedOutcome,
    Ga4RecordedRequest,
    Ga4RecordingId,
    Ga4ReportingIdentity,
    Ga4Sha256,
    Ga4UtcTimestamp,
    fail_ga4,
    fixture_binding,
)


_ROOT_KEYS = frozenset(
    {
        "fixture_version",
        "internal_request",
        "internal_request_sha256",
        "provider_capture",
        "recorded_result",
        "recording_id",
        "synthetic_marker",
        "wire_request",
        "wire_request_sha256",
    }
)
_INTERNAL_KEYS = frozenset(
    {
        "date_ranges",
        "dimension_filter",
        "dimensions",
        "keep_empty_rows",
        "limit",
        "metric_filter",
        "metrics",
        "offset",
        "order_bys",
        "property_id",
        "return_property_quota",
    }
)
_QUOTA_NAMES = (
    "concurrentRequests",
    "potentiallyThresholdedRequestsPerHour",
    "serverErrorsPerProjectPerHour",
    "tokensPerDay",
    "tokensPerHour",
    "tokensPerProjectPerHour",
)
_SUCCESS_RESULT_KEYS = frozenset(
    {
        "canonical_rows",
        "contract_semantics",
        "outcome",
        "pagination",
        "property_quota",
        "raw_ordered_report",
        "recorded_at",
        "report_metadata",
        "reporting_identity_snapshot",
        "request_hashes",
        "supersession_claim",
    }
)
_ERROR_RESULT_KEYS = frozenset(
    {
        "canonical_rows",
        "contract_semantics",
        "outcome",
        "provider_error",
        "recorded_at",
        "request_hashes",
        "retry_scheduling_policy",
        "supersession_claim",
    }
)


def _invalid() -> NoReturn:
    fail_ga4(Ga4FailureCode.FIXTURE_DOCUMENT_INVALID)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _invalid()


def _document(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    document = cast(dict[str, object], value)
    if frozenset(document) != keys:
        _invalid()
    return document


def _array(value: object) -> list[object]:
    if type(value) is not list:
        _invalid()
    return cast(list[object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        _invalid()
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _same_json(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        left = cast(dict[str, object], actual)
        right = cast(dict[str, object], expected)
        return left.keys() == right.keys() and all(
            _same_json(left[key], right[key]) for key in right
        )
    if type(expected) is list:
        left_list = cast(list[object], actual)
        right_list = cast(list[object], expected)
        return len(left_list) == len(right_list) and all(
            _same_json(left, right)
            for left, right in zip(left_list, right_list, strict=True)
        )
    return actual == expected


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _timestamp(value: object) -> Ga4UtcTimestamp:
    raw = _text(value)
    parsed: datetime | None = None
    if len(raw) == 20 and raw.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
        except ValueError:
            pass
    if parsed is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _invalid()
    return Ga4UtcTimestamp(parsed.astimezone(timezone.utc))


def _calendar_date(value: object) -> date:
    raw = _text(value)
    parsed: date | None = None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        pass
    if parsed is None or parsed.isoformat() != raw:
        _invalid()
    return parsed


def _expected_request(request: Ga4RecordedRequest) -> dict[str, object]:
    value = json.loads(request.internal_bytes())
    return _document(value, _INTERNAL_KEYS)


def _expected_wire(request: Ga4RecordedRequest) -> dict[str, object]:
    value = json.loads(request.wire_bytes())
    return _document(
        value,
        frozenset(
            {
                "dateRanges",
                "dimensions",
                "keepEmptyRows",
                "limit",
                "metrics",
                "offset",
                "returnPropertyQuota",
            }
        ),
    )


def _parse_quota(value: object) -> tuple[Ga4QuotaCounter, ...]:
    document = _document(value, frozenset(_QUOTA_NAMES))
    counters: list[Ga4QuotaCounter] = []
    for name in _QUOTA_NAMES:
        item = _document(document[name], frozenset({"consumed", "remaining"}))
        counters.append(
            Ga4QuotaCounter(
                name=name,
                consumed=_integer(item["consumed"]),
                remaining=_integer(item["remaining"]),
            )
        )
    return tuple(counters)


def _provider_rows(
    value: object,
) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    rows: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    for raw_row in _array(value):
        row = _document(raw_row, frozenset({"dimensionValues", "metricValues"}))
        dimensions = tuple(
            _text(_document(item, frozenset({"value"}))["value"])
            for item in _array(row["dimensionValues"])
        )
        metrics = tuple(
            _text(_document(item, frozenset({"value"}))["value"])
            for item in _array(row["metricValues"])
        )
        if len(dimensions) != len(EXACT_DIMENSIONS) or len(metrics) != len(
            EXACT_METRICS
        ):
            _invalid()
        rows.append((dimensions, metrics))
    return tuple(rows)


def _parse_success(
    *,
    root: dict[str, object],
    command: Ga4RecordedImportCommand,
) -> Ga4RecordedExchange:
    capture = _document(
        root["provider_capture"], frozenset({"reporting_identity", "run_report"})
    )
    report = _document(
        capture["run_report"],
        frozenset(
            {
                "api_version",
                "endpoint",
                "expected_response_sha256",
                "response",
                "retrieved_at",
            }
        ),
    )
    if (
        report["api_version"] != "v1beta"
        or report["endpoint"]
        != "https://analyticsdata.googleapis.com/v1beta/properties/1000001204:runReport"
    ):
        _invalid()
    response = _document(
        report["response"],
        frozenset(
            {
                "dimensionHeaders",
                "kind",
                "metadata",
                "metricHeaders",
                "propertyQuota",
                "rowCount",
                "rows",
            }
        ),
    )
    response_digest = Ga4Sha256.of(_canonical_json(response))
    if (
        _text(report["expected_response_sha256"]) != response_digest.value
        or response_digest != command_fixture_response(command)
        or response["kind"] != "analyticsData#runReport"
    ):
        _invalid()
    dimension_headers = tuple(
        _text(_document(item, frozenset({"name"}))["name"])
        for item in _array(response["dimensionHeaders"])
    )
    metric_headers = tuple(
        _text(_document(item, frozenset({"name", "type"}))["name"])
        for item in _array(response["metricHeaders"])
    )
    if dimension_headers != EXACT_DIMENSIONS or metric_headers != EXACT_METRICS:
        _invalid()
    for item in _array(response["metricHeaders"]):
        if _document(item, frozenset({"name", "type"}))["type"] != "TYPE_INTEGER":
            _invalid()
    provider_rows = _provider_rows(response["rows"])
    if len(provider_rows) != 2 or _integer(response["rowCount"]) != 3:
        _invalid()

    identity_capture = _document(
        capture["reporting_identity"],
        frozenset(
            {
                "api_version",
                "endpoint",
                "expected_response_sha256",
                "response",
                "retrieved_at",
            }
        ),
    )
    identity_response = _document(
        identity_capture["response"], frozenset({"name", "reportingIdentity"})
    )
    identity_digest = Ga4Sha256.of(_canonical_json(identity_response))
    if (
        identity_capture["api_version"] != "v1alpha"
        or identity_capture["endpoint"]
        != "https://analyticsadmin.googleapis.com/v1alpha/properties/1000001204/reportingIdentitySettings"
        or identity_response["name"]
        != "properties/1000001204/reportingIdentitySettings"
        or identity_response["reportingIdentity"] != "DEVICE_BASED"
        or identity_digest.value != REPORTING_IDENTITY_SHA256
        or identity_capture["expected_response_sha256"] != REPORTING_IDENTITY_SHA256
    ):
        _invalid()

    metadata = _document(
        response["metadata"],
        frozenset(
            {
                "currencyCode",
                "dataLossFromOtherRow",
                "emptyReason",
                "samplingMetadatas",
                "schemaRestrictionResponse",
                "subjectToThresholding",
                "timeZone",
            }
        ),
    )
    samples = _array(metadata["samplingMetadatas"])
    if len(samples) != 1:
        _invalid()
    sample = _document(samples[0], frozenset({"samplesReadCount", "samplingSpaceSize"}))
    restrictions = _document(
        metadata["schemaRestrictionResponse"], frozenset({"activeMetricRestrictions"})
    )
    if _array(restrictions["activeMetricRestrictions"]):
        _invalid()
    quota = _parse_quota(response["propertyQuota"])
    configuration = Ga4PropertyConfigSnapshot(
        property_resource=SYNTHETIC_PROPERTY_RESOURCE,
        reporting_identity=Ga4ReportingIdentity.DEVICE_BASED,
        reporting_identity_response_digest=identity_digest,
        reporting_identity_retrieved_at=_timestamp(identity_capture["retrieved_at"]),
        currency_code=_text(metadata["currencyCode"]),
        time_zone=_text(metadata["timeZone"]),
        subject_to_thresholding=_boolean(metadata["subjectToThresholding"]),
        data_loss_from_other_row=_boolean(metadata["dataLossFromOtherRow"]),
        empty_reason=_text(metadata["emptyReason"]),
        sampling_metadata=(
            (_text(sample["samplesReadCount"]), _text(sample["samplingSpaceSize"])),
        ),
        quota=quota,
    )

    result = _document(root["recorded_result"], _SUCCESS_RESULT_KEYS)
    if result["outcome"] != "SUCCESS" or result["supersession_claim"] != "NONE":
        _invalid()
    recorded_at = _timestamp(result["recorded_at"])
    canonical_rows = _array(result["canonical_rows"])
    if len(canonical_rows) != len(provider_rows):
        _invalid()
    rows: list[Ga4MetricRow] = []
    for index, raw_row in enumerate(canonical_rows):
        row = _document(
            raw_row,
            frozenset(
                {
                    "date_from",
                    "date_range_index",
                    "date_to",
                    "dimension_values",
                    "imported_at",
                    "metric_values",
                    "property_id",
                    "quota_metadata",
                    "reporting_identity",
                    "site_id",
                    "source_request_sha256",
                    "thresholding_applied",
                }
            ),
        )
        dimensions = _document(row["dimension_values"], frozenset(EXACT_DIMENSIONS))
        metrics = _document(row["metric_values"], frozenset(EXACT_METRICS))
        try:
            site_id = UUID(_text(row["site_id"]))
        except ValueError:
            site_id = UUID(int=0)
        parsed = Ga4MetricRow(
            site_id=site_id,
            property_id=_text(row["property_id"]),
            date_from=_calendar_date(row["date_from"]),
            date_to=_calendar_date(row["date_to"]),
            date_range_index=_integer(row["date_range_index"]),
            dimensions=EXACT_DIMENSIONS,
            metrics=EXACT_METRICS,
            dimension_values=tuple(
                _text(dimensions[name]) for name in EXACT_DIMENSIONS
            ),
            metric_values=tuple(_text(metrics[name]) for name in EXACT_METRICS),
            imported_at=_timestamp(row["imported_at"]),
            reporting_identity=Ga4ReportingIdentity.DEVICE_BASED,
            thresholding_applied=_boolean(row["thresholding_applied"]),
            source_request_sha256=Ga4Sha256(_text(row["source_request_sha256"])),
        )
        if (
            parsed.imported_at != recorded_at
            or (parsed.dimension_values, parsed.metric_values) != provider_rows[index]
            or row["reporting_identity"] != "DEVICE_BASED"
            or not _same_json(row["quota_metadata"], response["propertyQuota"])
        ):
            _invalid()
        rows.append(parsed)

    pagination = _document(
        result["pagination"],
        frozenset(
            {
                "limit",
                "offset",
                "provider_row_count",
                "returned_row_count",
                "row_count_independent_of_pagination",
            }
        ),
    )
    if (
        pagination["limit"] != 2
        or pagination["offset"] != 0
        or pagination["provider_row_count"] != 3
        or pagination["returned_row_count"] != 2
        or pagination["row_count_independent_of_pagination"] is not True
        or not _same_json(result["property_quota"], response["propertyQuota"])
        or not _same_json(result["report_metadata"], metadata)
        or not _same_json(result["reporting_identity_snapshot"], identity_response)
    ):
        _invalid()
    _validate_hash_projection(
        result["request_hashes"], response_digest, identity_digest
    )
    return Ga4RecordedExchange(
        recording_id=command.recording_id,
        fixture_digest=command.fixture_digest,
        fixture_length=command.fixture_length,
        request=command.request,
        response_digest=response_digest,
        run_report_retrieved_at=_timestamp(report["retrieved_at"]),
        recorded_at=recorded_at,
        outcome=Ga4RecordedOutcome.RECORDED_SUCCESS,
        rows=tuple(rows),
        provider_row_count=3,
        returned_row_count=2,
        row_count_independent_of_pagination=True,
        configuration=configuration,
        http_status=None,
    )


def command_fixture_response(command: Ga4RecordedImportCommand) -> Ga4Sha256:
    return fixture_binding(command.recording_id).response_digest


def _validate_hash_projection(
    value: object,
    response_digest: Ga4Sha256,
    identity_digest: Ga4Sha256 | None,
) -> None:
    hashes = _document(
        value,
        frozenset(
            {
                "internal_request_sha256",
                "reporting_identity_response_sha256",
                "run_report_response_sha256",
                "wire_request_sha256",
            }
        ),
    )
    expected_identity = identity_digest.value if identity_digest is not None else None
    if (
        hashes["internal_request_sha256"] != INTERNAL_REQUEST_SHA256
        or hashes["wire_request_sha256"] != WIRE_REQUEST_SHA256
        or hashes["run_report_response_sha256"] != response_digest.value
        or hashes["reporting_identity_response_sha256"] != expected_identity
    ):
        _invalid()


def _parse_error(
    *,
    root: dict[str, object],
    command: Ga4RecordedImportCommand,
) -> Ga4RecordedExchange:
    capture = _document(
        root["provider_capture"], frozenset({"reporting_identity", "run_report"})
    )
    if capture["reporting_identity"] != "NOT_ATTEMPTED_AFTER_PROVIDER_ERROR":
        _invalid()
    report = _document(
        capture["run_report"],
        frozenset(
            {
                "api_version",
                "endpoint",
                "expected_response_sha256",
                "http_status",
                "response",
                "retrieved_at",
            }
        ),
    )
    response = _document(report["response"], frozenset({"error"}))
    error = _document(response["error"], frozenset({"code", "message", "status"}))
    digest = Ga4Sha256.of(_canonical_json(response))
    if (
        report["api_version"] != "v1beta"
        or report["endpoint"]
        != "https://analyticsdata.googleapis.com/v1beta/properties/1000001204:runReport"
        or _integer(report["http_status"]) != 429
        or _integer(error["code"]) != 429
        or error["status"] != "RESOURCE_EXHAUSTED"
        or error["message"] != "Synthetic quota limit reached."
        or report["expected_response_sha256"] != digest.value
        or digest != command_fixture_response(command)
    ):
        _invalid()
    result = _document(root["recorded_result"], _ERROR_RESULT_KEYS)
    if (
        result["outcome"] != "PROVIDER_ERROR"
        or _array(result["canonical_rows"])
        or result["retry_scheduling_policy"] != "NOT_DEFINED"
        or result["supersession_claim"] != "NONE"
        or not _same_json(result["provider_error"], response)
    ):
        _invalid()
    _validate_hash_projection(result["request_hashes"], digest, None)
    return Ga4RecordedExchange(
        recording_id=command.recording_id,
        fixture_digest=command.fixture_digest,
        fixture_length=command.fixture_length,
        request=command.request,
        response_digest=digest,
        run_report_retrieved_at=_timestamp(report["retrieved_at"]),
        recorded_at=_timestamp(result["recorded_at"]),
        outcome=Ga4RecordedOutcome.RECORDED_RESOURCE_EXHAUSTED,
        rows=(),
        provider_row_count=None,
        returned_row_count=0,
        row_count_independent_of_pagination=None,
        configuration=None,
        http_status=429,
    )


def _parse_fixture(
    command: Ga4RecordedImportCommand,
    fixture_bytes: bytes,
) -> Ga4RecordedExchange:
    if (
        type(fixture_bytes) is not bytes
        or len(fixture_bytes) != command.fixture_length.value
        or Ga4Sha256.of(fixture_bytes) != command.fixture_digest
    ):
        fail_ga4(Ga4FailureCode.FIXTURE_BYTES_MISMATCH)
    value: object = None
    parsed = False
    try:
        value = json.loads(
            fixture_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
        parsed = True
    except Exception:
        pass
    if not parsed:
        _invalid()
    root = _document(value, _ROOT_KEYS)
    if (
        root["fixture_version"] != "1.0.0"
        or root["synthetic_marker"] != "SYNTHETIC_TEST_ONLY"
        or root["recording_id"] != command.recording_id.value
        or root["internal_request_sha256"] != INTERNAL_REQUEST_SHA256
        or root["wire_request_sha256"] != WIRE_REQUEST_SHA256
        or not _same_json(root["internal_request"], _expected_request(command.request))
        or not _same_json(root["wire_request"], _expected_wire(command.request))
    ):
        fail_ga4(Ga4FailureCode.REQUEST_MISMATCH)
    if command.recording_id == Ga4RecordingId("provider-error-429"):
        return _parse_error(root=root, command=command)
    return _parse_success(root=root, command=command)


@final
class RecordedGa4Adapter:
    """Consume one exact caller-supplied fixture without retaining its bytes."""

    __slots__ = ("_consumed", "_exchange", "_lock", "_recording_id", "_request")

    def __init__(
        self, *, command: Ga4RecordedImportCommand, fixture_bytes: bytes
    ) -> None:
        if type(command) is not Ga4RecordedImportCommand:
            fail_ga4()
        exchange = _parse_fixture(command, fixture_bytes)
        self._recording_id = command.recording_id
        self._request = command.request
        self._exchange = exchange
        self._consumed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return "RecordedGa4Adapter(<redacted-recorded-ga4-reference>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded GA4 adapter serialization is not supported")

    def read(
        self,
        *,
        recording_id: Ga4RecordingId,
        request: Ga4RecordedRequest,
    ) -> Ga4RecordedExchange:
        if (
            type(recording_id) is not Ga4RecordingId
            or type(request) is not Ga4RecordedRequest
            or recording_id != self._recording_id
            or request != self._request
        ):
            fail_ga4(Ga4FailureCode.REQUEST_MISMATCH)
        with self._lock:
            if self._consumed:
                fail_ga4(Ga4FailureCode.RECORDED_EXCHANGE_EXHAUSTED)
            self._consumed = True
            return self._exchange


__all__ = ["RecordedGa4Adapter"]
