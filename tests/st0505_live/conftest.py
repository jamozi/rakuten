"""Isolated ST-0505 executable-boundary test fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from typing import Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.rakuten_live_smoke import (  # noqa: E402
    RakutenHttpResponse,
    RakutenLiveSmokeGrant,
    RakutenLiveSmokeRequest,
    SecretText,
)


NOW: Final = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
APP_ID: Final = "00000000-0000-0000-0000-000000000001"
ACCESS_KEY: Final = "pk_test_only_access_key"
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


class FakeCredentials:
    def __init__(self, *, fail_alias: str | None = None) -> None:
        self.fail_alias = fail_alias
        self.reads: list[str] = []

    def read(self, alias: str) -> SecretText:
        self.reads.append(alias)
        if alias == self.fail_alias:
            raise RuntimeError("synthetic secret source failure")
        if alias == "rakuten_application_id":
            return SecretText(APP_ID)
        if alias == "rakuten_access_key":
            return SecretText(ACCESS_KEY)
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
    issued_at: datetime = NOW - timedelta(minutes=1),
    expires_at: datetime = NOW + timedelta(minutes=1),
) -> RakutenLiveSmokeGrant:
    exact_request = request() if bound_request is None else bound_request
    return RakutenLiveSmokeGrant(
        environment="ENV-STAGING",
        request_sha256=exact_request.fingerprint,
        operations_evidence_sha256=OPERATIONS_EVIDENCE_SHA256,
        execution_approval_sha256=EXECUTION_APPROVAL_SHA256,
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
