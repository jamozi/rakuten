"""Runtime and authorization tests for the ST-0505 live smoke."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json

import pytest

from raos.adapters.rakuten_live_smoke import (
    RAKUTEN_ACCESS_KEY_ALIAS,
    RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON,
    RAKUTEN_API_DOCUMENTATION_URL,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_APPLICATION_ID_ALIAS,
    RAKUTEN_ITEM_SEARCH_PATH,
    RateObservation,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeRunner,
    SecretText,
)

from conftest import (
    APPLICATION_MATERIAL,
    AUTHENTICATION_MATERIAL,
    BODY,
    NOW,
    OPERATIONS_EVIDENCE_SHA256,
    FakeAuthorizer,
    FakeCredentials,
    FakeTransport,
    FixedClock,
    assert_failure,
    grant,
    request,
    response,
    runner_for,
)



def test_success_is_one_request_one_page_no_retry_and_safe_receipt() -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)
    runner, authorizer = runner_for(
        exact_grant=exact_grant,
        credentials=credentials,
        transport=transport,
    )

    receipt = runner.run(request=exact_request, grant=exact_grant)

    assert len(authorizer.calls) == 1
    assert authorizer.calls[0]["grant_sha256"] == exact_grant.fingerprint
    assert authorizer.calls[0]["request_sha256"] == exact_request.fingerprint
    assert credentials.reads == [
        RAKUTEN_APPLICATION_ID_ALIAS,
        RAKUTEN_ACCESS_KEY_ALIAS,
    ]
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["origin"] == RAKUTEN_API_ORIGIN
    assert call["path"] == RAKUTEN_ITEM_SEARCH_PATH
    query = dict(call["query"])
    headers = dict(call["headers"])
    assert query["applicationId"] == APPLICATION_MATERIAL
    assert "accessKey" not in query
    assert "affiliateId" not in query
    assert query["formatVersion"] == "2"
    assert query["page"] == "1"
    assert query["hits"] == "1"
    assert headers["accessKey"] == AUTHENTICATION_MATERIAL
    assert headers["Accept-Encoding"] == "identity"

    assert receipt.network_request_count == 1
    assert receipt.retry_count == 0
    assert receipt.pagination_count == 0
    assert receipt.storage_write_count == 0
    assert receipt.persistence_write_count == 0
    assert receipt.publication_count == 0
    assert receipt.request_sha256 == exact_request.fingerprint
    assert receipt.response_bytes == len(BODY)
    assert receipt.http_status == 200
    assert receipt.rate_observation is RateObservation.COMPLETE_HEADER_METADATA
    assert receipt.rate_limit == 100
    assert receipt.rate_remaining == 99
    assert receipt.returned_item_count == 1

    serialized = json.loads(receipt.canonical_json)
    text = receipt.canonical_json.decode("ascii")
    assert serialized["request_sha256"] == exact_request.fingerprint
    assert APPLICATION_MATERIAL not in text
    assert AUTHENTICATION_MATERIAL not in text
    assert "synthetic suitcase" not in text
    assert "Synthetic suitcase" not in text


def test_request_secret_grant_and_raw_response_displays_are_redacted() -> None:
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)
    secret = SecretText(AUTHENTICATION_MATERIAL)
    raw = response()
    for value, hidden in (
        (exact_request, "synthetic suitcase"),
        (exact_grant, OPERATIONS_EVIDENCE_SHA256),
        (secret, AUTHENTICATION_MATERIAL),
        (raw, "Synthetic suitcase"),
    ):
        assert hidden not in repr(value)
        assert hidden not in str(value)


def test_raw_response_has_no_public_body_or_headers_and_cannot_pickle() -> None:
    raw = response(headers=(("Content-Type", "application/json"),))
    assert not hasattr(raw, "body")
    assert not hasattr(raw, "headers")
    with pytest.raises(TypeError):
        raw.__reduce_ex__(5)


def test_official_contract_pin_is_exact() -> None:
    assert RAKUTEN_API_DOCUMENTATION_URL == (
        "https://webservice.rakuten.co.jp/documentation/ichiba-item-search"
    )
    assert RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON == "2026-08-18"
    assert RAKUTEN_ITEM_SEARCH_PATH.endswith("/20260701")


def test_runner_requires_an_external_authorizer() -> None:
    with pytest.raises(TypeError):
        RakutenLiveSmokeRunner(  # type: ignore[call-arg]
            credentials=FakeCredentials(),
            transport=FakeTransport(response()),
            clock=FixedClock(),
        )


def test_forged_well_formed_grant_is_rejected_before_credentials_or_network() -> None:
    exact_request = request()
    trusted = grant(bound_request=exact_request)
    forged = grant(
        bound_request=exact_request,
        operations_evidence_sha256=hashlib.sha256(b"untrusted evidence").hexdigest(),
    )
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    authorizer = FakeAuthorizer(trusted_grant_sha256=trusted.fingerprint)

    used_authorizer, source, used_transport = assert_failure(
        RakutenLiveSmokeFailureCode.NOT_AUTHORIZED,
        exact_request=exact_request,
        exact_grant=forged,
        credentials=credentials,
        transport=transport,
        authorizer=authorizer,
    )

    assert len(used_authorizer.calls) == 1
    assert source.reads == []
    assert used_transport.calls == []


def test_authorizer_exception_is_sanitized_and_prevents_credentials_and_network(
) -> None:
    exact_grant = grant()
    authorizer = FakeAuthorizer(
        trusted_grant_sha256=exact_grant.fingerprint,
        error=RuntimeError(
            f"do not leak {APPLICATION_MATERIAL} {AUTHENTICATION_MATERIAL}"
        ),
    )
    credentials = FakeCredentials()
    transport = FakeTransport(response())

    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        runner_for(
            exact_grant=exact_grant,
            credentials=credentials,
            transport=transport,
            authorizer=authorizer,
        )[0].run(request=request(), grant=exact_grant)

    assert captured.value.code is RakutenLiveSmokeFailureCode.NOT_AUTHORIZED
    assert APPLICATION_MATERIAL not in str(captured.value)
    assert AUTHENTICATION_MATERIAL not in str(captured.value)
    assert captured.value.__cause__ is None
    assert credentials.reads == []
    assert transport.calls == []


def test_runner_and_authorizer_each_consume_a_valid_grant_once() -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)
    runner, authorizer = runner_for(
        exact_grant=exact_grant,
        credentials=credentials,
        transport=transport,
    )

    runner.run(request=exact_request, grant=exact_grant)
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        runner.run(request=exact_request, grant=exact_grant)

    assert captured.value.code is RakutenLiveSmokeFailureCode.NOT_AUTHORIZED
    assert len(authorizer.calls) == 1
    assert len(transport.calls) == 1


def test_grant_fingerprint_binds_evidence_and_time() -> None:
    first = grant()
    changed_evidence = grant(
        operations_evidence_sha256=hashlib.sha256(b"different evidence").hexdigest()
    )
    changed_time = grant(expires_at=NOW + timedelta(minutes=2))
    assert len(first.fingerprint) == 64
    assert first.fingerprint != changed_evidence.fingerprint
    assert first.fingerprint != changed_time.fingerprint



def test_request_and_grant_cannot_be_generically_serialized() -> None:
    exact_request = request()
    exact_grant = grant(bound_request=exact_request)
    with pytest.raises(TypeError):
        exact_request.__reduce_ex__(5)
    with pytest.raises(TypeError):
        exact_grant.__reduce_ex__(5)
