"""One-attempt failure tests for the ST-0505 live smoke."""

from __future__ import annotations

from datetime import timedelta

import pytest

from raos.adapters.rakuten_live_smoke import (
    RAKUTEN_ACCESS_KEY_ALIAS,
    RAKUTEN_APPLICATION_ID_ALIAS,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeRequest,
)

from conftest import (
    APPLICATION_MATERIAL,
    AUTHENTICATION_MATERIAL,
    NOW,
    FakeCredentials,
    FakeTransport,
    assert_failure,
    grant,
    request,
    response,
    runner_for,
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (301, RakutenLiveSmokeFailureCode.REDIRECT_FORBIDDEN),
        (302, RakutenLiveSmokeFailureCode.REDIRECT_FORBIDDEN),
        (401, RakutenLiveSmokeFailureCode.AUTH_REJECTED),
        (403, RakutenLiveSmokeFailureCode.AUTH_REJECTED),
        (429, RakutenLiveSmokeFailureCode.RATE_LIMITED),
        (400, RakutenLiveSmokeFailureCode.REQUEST_REJECTED),
        (404, RakutenLiveSmokeFailureCode.REQUEST_REJECTED),
        (500, RakutenLiveSmokeFailureCode.PROVIDER_UNAVAILABLE),
        (503, RakutenLiveSmokeFailureCode.PROVIDER_UNAVAILABLE),
        (418, RakutenLiveSmokeFailureCode.PROVIDER_REJECTED),
    ],
)
def test_http_failure_never_retries(
    status: int,
    expected: RakutenLiveSmokeFailureCode,
) -> None:
    transport = FakeTransport(response(status=status, body=b""))
    _authorizer, _source, used = assert_failure(expected, transport=transport)
    assert len(used.calls) == 1


def test_transport_exception_never_retries_or_leaks_original_message() -> None:
    transport = FakeTransport(
        response(),
        error=TimeoutError(
            f"do not leak {APPLICATION_MATERIAL} {AUTHENTICATION_MATERIAL}"
        ),
    )
    exact_grant = grant()
    runner, _authorizer = runner_for(
        exact_grant=exact_grant,
        credentials=FakeCredentials(),
        transport=transport,
    )
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        runner.run(request=request(), grant=exact_grant)
    assert captured.value.code is RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE
    assert len(transport.calls) == 1
    assert APPLICATION_MATERIAL not in str(captured.value)
    assert AUTHENTICATION_MATERIAL not in str(captured.value)
    assert captured.value.__cause__ is None


def test_missing_second_credential_prevents_network() -> None:
    credentials = FakeCredentials(fail_alias=RAKUTEN_ACCESS_KEY_ALIAS)
    transport = FakeTransport(response())
    _authorizer, source, used = assert_failure(
        RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE,
        credentials=credentials,
        transport=transport,
    )
    assert source.reads == [
        RAKUTEN_APPLICATION_ID_ALIAS,
        RAKUTEN_ACCESS_KEY_ALIAS,
    ]
    assert used.calls == []


def test_expired_or_wrong_request_grant_prevents_authorizer_credentials_and_network(
) -> None:
    credentials = FakeCredentials()
    transport = FakeTransport(response())
    expired = grant(
        issued_at=NOW - timedelta(minutes=2),
        expires_at=NOW - timedelta(minutes=1),
    )
    used_authorizer, source, used_transport = assert_failure(
        RakutenLiveSmokeFailureCode.NOT_AUTHORIZED,
        exact_grant=expired,
        credentials=credentials,
        transport=transport,
    )
    assert used_authorizer.calls == []
    assert source.reads == []
    assert used_transport.calls == []

    other = RakutenLiveSmokeRequest(keyword="another synthetic query")
    wrong = grant(bound_request=other)
    used_authorizer, source, used_transport = assert_failure(
        RakutenLiveSmokeFailureCode.NOT_AUTHORIZED,
        exact_grant=wrong,
        credentials=credentials,
        transport=transport,
    )
    assert used_authorizer.calls == []
    assert source.reads == []
    assert used_transport.calls == []
