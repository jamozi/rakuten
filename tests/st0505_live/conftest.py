"""Isolated ST-0505 executable-boundary test fixtures and helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from typing import Final

import pytest


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.rakuten_live_smoke import (  # noqa: E402
    RakutenHttpResponse,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeGrant,
    RakutenLiveSmokeRequest,
    RakutenLiveSmokeRunner,
    SecretText,
)


NOW: Final = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
APPLICATION_MATERIAL: Final = "fixture-application-identifier"
AUTHENTICATION_MATERIAL: Final = "fixture-authentication-material"
OPERATIONS_EVIDENCE_SHA256: Final = hashlib.sha256(
    b"synthetic operations evidence"
).hexdigest()
EXECUTION_APPROVAL_SHA256: Final = hashlib.sha256(
    b"synthetic execution approval"
).hexdigest()
BODY: Final = (
    b'{"count":1,"page":1,"first":1,"last":1,"hits":1,"carrier":0,'
    b'"pageCount":1,"items":[{"itemCode":"test-shop:item-1",'
    b'"itemName":"Synthetic suitcase","itemPrice":1234,'
    b'"itemUrl":"https://example.invalid/item-1","shopCode":"test-shop"}]}'
)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeAuthorizer:
    def __init__(
        self,
        *,
        trusted_grant_sha256: str,
        error: Exception | None = None,
    ) -> None:
        self.trusted_grant_sha256 = trusted_grant_sha256
        self.error = error
        self.consumed = False
        self.calls: list[dict[str, object]] = []

    def consume(
        self,
        *,
        grant_sha256: str,
        request_sha256: str,
        observed_at: datetime,
    ) -> bool:
        self.calls.append(
            {
                "grant_sha256": grant_sha256,
                "request_sha256": request_sha256,
                "observed_at": observed_at,
            }
        )
        if self.error is not None:
            raise self.error
        if self.consumed or grant_sha256 != self.trusted_grant_sha256:
            return False
        self.consumed = True
        return True


class FakeCredentials:
    def __init__(self, *, fail_alias: str | None = None) -> None:
        self.fail_alias = fail_alias
        self.reads: list[str] = []

    def read(self, alias: str) -> SecretText:
        self.reads.append(alias)
        if alias == self.fail_alias:
            raise RuntimeError("synthetic credential source failure")
        if alias == "rakuten_application_id":
            return SecretText(APPLICATION_MATERIAL)
        if alias == "rakuten_access_key":
            return SecretText(AUTHENTICATION_MATERIAL)
        raise AssertionError("unexpected alias")


class FakeTransport:
    def __init__(
        self,
        response: RakutenHttpResponse,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get(self, **kwargs: object) -> RakutenHttpResponse:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def request() -> RakutenLiveSmokeRequest:
    return RakutenLiveSmokeRequest(keyword="synthetic suitcase")


def grant(
    *,
    bound_request: RakutenLiveSmokeRequest | None = None,
    operations_evidence_sha256: str = OPERATIONS_EVIDENCE_SHA256,
    execution_approval_sha256: str = EXECUTION_APPROVAL_SHA256,
    issued_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(minutes=1),
) -> RakutenLiveSmokeGrant:
    exact_request = request() if bound_request is None else bound_request
    return RakutenLiveSmokeGrant(
        environment="ENV-STAGING",
        request_sha256=exact_request.fingerprint,
        operations_evidence_sha256=operations_evidence_sha256,
        execution_approval_sha256=execution_approval_sha256,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def response(
    *,
    status: int = 200,
    body: bytes = BODY,
    headers: tuple[tuple[str, str], ...] | None = None,
) -> RakutenHttpResponse:
    exact_headers = (
        (
            ("Content-Type", "application/json; charset=utf-8"),
            ("X-RateLimit-Limit", "100"),
            ("X-RateLimit-Remaining", "99"),
            ("X-RateLimit-Reset", "1723939200"),
            ("X-Rakuten-Request-Id", "TEST_ONLY:REQUEST:1"),
        )
        if headers is None
        else headers
    )
    return RakutenHttpResponse(status=status, headers=exact_headers, body=body)


def runner_for(
    *,
    exact_grant: RakutenLiveSmokeGrant,
    credentials: FakeCredentials,
    transport: FakeTransport,
    authorizer: FakeAuthorizer | None = None,
) -> tuple[RakutenLiveSmokeRunner, FakeAuthorizer]:
    exact_authorizer = (
        FakeAuthorizer(trusted_grant_sha256=exact_grant.fingerprint)
        if authorizer is None
        else authorizer
    )
    return (
        RakutenLiveSmokeRunner(
            authorizer=exact_authorizer,
            credentials=credentials,
            transport=transport,
            clock=FixedClock(),
        ),
        exact_authorizer,
    )


def assert_failure(
    expected: RakutenLiveSmokeFailureCode,
    *,
    exact_request: RakutenLiveSmokeRequest | None = None,
    exact_grant: RakutenLiveSmokeGrant | None = None,
    credentials: FakeCredentials | None = None,
    transport: FakeTransport | None = None,
    authorizer: FakeAuthorizer | None = None,
) -> tuple[FakeAuthorizer, FakeCredentials, FakeTransport]:
    req = request() if exact_request is None else exact_request
    bound_grant = grant(bound_request=req) if exact_grant is None else exact_grant
    source = FakeCredentials() if credentials is None else credentials
    fake = FakeTransport(response()) if transport is None else transport
    runner, used_authorizer = runner_for(
        exact_grant=bound_grant,
        credentials=source,
        transport=fake,
        authorizer=authorizer,
    )
    with pytest.raises(RakutenLiveSmokeFailure) as captured:
        runner.run(request=req, grant=bound_grant)
    assert captured.value.code is expected
    assert str(captured.value) == expected.value
    return used_authorizer, source, fake


def transport_inputs() -> tuple[
    tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]
]:
    exact_request = request()
    query = exact_request._query(SecretText(APPLICATION_MATERIAL))
    headers = (
        ("Accept", "application/json"),
        ("Accept-Encoding", "identity"),
        ("Connection", "close"),
        ("User-Agent", "RAOS-ST0505/1"),
        ("accessKey", AUTHENTICATION_MATERIAL),
    )
    return query, headers
