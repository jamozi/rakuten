"""Parser, schema, grant, and receipt tests for ST-0505."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json

import pytest

from raos.adapters.rakuten_live_smoke import (
    MAX_RESPONSE_BYTES,
    RateObservation,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeGrant,
)

from conftest import (
    EXECUTION_APPROVAL_SHA256,
    NOW,
    OPERATIONS_EVIDENCE_SHA256,
    FakeCredentials,
    FakeTransport,
    assert_failure,
    grant,
    request,
    response,
    runner_for,
)



def test_grant_rejects_production_and_lifetime_over_fifteen_minutes() -> None:
    exact_request = request()
    with pytest.raises(RakutenLiveSmokeFailure):
        RakutenLiveSmokeGrant(
            environment="ENV-PRODUCTION",
            request_sha256=exact_request.fingerprint,
            operations_evidence_sha256=OPERATIONS_EVIDENCE_SHA256,
            execution_approval_sha256=EXECUTION_APPROVAL_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        )
    with pytest.raises(RakutenLiveSmokeFailure):
        RakutenLiveSmokeGrant(
            environment="ENV-STAGING",
            request_sha256=exact_request.fingerprint,
            operations_evidence_sha256=OPERATIONS_EVIDENCE_SHA256,
            execution_approval_sha256=EXECUTION_APPROVAL_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=16),
        )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"\xff\xfe", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b"{", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b'{"count":1,"count":1}', RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b'{"value":NaN}', RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (b"[]", RakutenLiveSmokeFailureCode.RESPONSE_INVALID),
        (
            b"x" * (MAX_RESPONSE_BYTES + 1),
            RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE,
        ),
    ],
)
def test_malformed_or_oversized_body_never_retries(
    body: bytes,
    expected: RakutenLiveSmokeFailureCode,
) -> None:
    transport = FakeTransport(response(body=body))
    _authorizer, _source, used = assert_failure(expected, transport=transport)
    assert len(used.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"count": 1, "page": 2, "hits": 1, "pageCount": 1, "items": []},
        {"count": 1, "page": 1, "hits": 2, "pageCount": 1, "items": []},
        {
            "count": 1,
            "page": 1,
            "hits": 1,
            "pageCount": 1,
            "items": [],
            "unknown": 1,
        },
        {"count": 1, "page": 1, "hits": 1, "pageCount": 1},
        {"count": 0, "page": 1, "hits": 0, "pageCount": 1, "items": []},
        {
            "count": 1,
            "page": 1,
            "hits": 1,
            "pageCount": 1,
            "items": [
                {
                    "itemCode": "test-shop:item-1",
                    "itemName": "Synthetic",
                    "itemPrice": 1,
                    "itemUrl": "http://example.invalid/item",
                    "shopCode": "test-shop",
                }
            ],
        },
    ],
)
def test_schema_drift_never_retries(payload: dict[str, object]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    transport = FakeTransport(response(body=body))
    _authorizer, _source, used = assert_failure(
        RakutenLiveSmokeFailureCode.SCHEMA_MISMATCH,
        transport=transport,
    )
    assert len(used.calls) == 1


def test_missing_unsafe_or_unallowlisted_response_headers_fail_closed() -> None:
    for headers in (
        (),
        (("Content-Type", "text/html"),),
        (("Content-Type", "application/json"), ("Content-Encoding", "gzip")),
        (
            ("Content-Type", "application/json"),
            ("Content-Type", "application/json"),
        ),
        (("Content-Type", "application/json"), ("X-Untrusted", "value")),
        (
            ("Content-Type", "application/json"),
            ("X-Rakuten-Request-Id", "one"),
            ("X-Request-Id", "two"),
        ),
    ):
        transport = FakeTransport(response(headers=headers))
        _authorizer, _source, used = assert_failure(
            RakutenLiveSmokeFailureCode.RESPONSE_INVALID,
            transport=transport,
        )
        assert len(used.calls) == 1


def test_partial_or_absent_rate_metadata_is_observed_without_invention() -> None:
    exact_request = request()
    for headers, expected in (
        (
            (("Content-Type", "application/json"),),
            RateObservation.NOT_EXPOSED,
        ),
        (
            (
                ("Content-Type", "application/json"),
                ("X-RateLimit-Remaining", "9"),
            ),
            RateObservation.PARTIAL_HEADER_METADATA,
        ),
    ):
        exact_grant = grant(bound_request=exact_request)
        runner, _authorizer = runner_for(
            exact_grant=exact_grant,
            credentials=FakeCredentials(),
            transport=FakeTransport(response(headers=headers)),
        )
        receipt = runner.run(request=exact_request, grant=exact_grant)
        assert receipt.rate_observation is expected


def test_nested_json_depth_limit_is_enforced_without_retry() -> None:
    nested: object = 0
    for _ in range(40):
        nested = [nested]
    body = json.dumps(
        {"count": 0, "page": 1, "hits": 0, "pageCount": 0, "items": nested}
    ).encode()
    transport = FakeTransport(response(body=body))
    _authorizer, _source, used = assert_failure(
        RakutenLiveSmokeFailureCode.RESPONSE_INVALID,
        transport=transport,
    )
    assert len(used.calls) == 1


def test_receipt_constructor_rejects_forged_counts_or_rate_metadata() -> None:
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)
    runner, _authorizer = runner_for(
        exact_grant=exact_grant,
        credentials=FakeCredentials(),
        transport=FakeTransport(response()),
    )
    receipt = runner.run(request=exact_request, grant=exact_grant)
    for field, value in (
        ("retry_count", 1),
        ("network_request_count", 0),
        ("http_status", 201),
        ("page", 2),
        ("response_sha256", "0" * 63),
        ("rate_remaining", 101),
        ("rate_observation", RateObservation.NOT_EXPOSED),
    ):
        with pytest.raises(RakutenLiveSmokeFailure):
            replace(receipt, **{field: value})
