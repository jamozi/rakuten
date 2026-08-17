"""Fail-closed executable boundary for the bounded ST-0505 live smoke.

Importing this module performs no I/O. A caller must inject an external
one-shot authorizer and fixed-alias credential source before the runner can make
one HTTPS GET. No concrete authorizer or credential reader is provided here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Protocol, final

from raos.adapters._rakuten_live_smoke_transport import (
    RakutenLiveSmokeTransport,
    UrllibRakutenLiveSmokeTransport,
)
from raos.adapters._rakuten_live_smoke_validation import build_receipt
from raos.domain.catalog.rakuten_live_smoke import (
    MAX_RESPONSE_BYTES,
    NETWORK_TIMEOUT_SECONDS,
    RAKUTEN_ACCESS_KEY_ALIAS,
    RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON,
    RAKUTEN_API_DOCUMENTATION_URL,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_API_VERSION,
    RAKUTEN_APPLICATION_ID_ALIAS,
    RAKUTEN_ITEM_SEARCH_PATH,
    STAGING_ENVIRONMENT,
    RateObservation,
    RakutenHttpResponse,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    RakutenLiveSmokeGrant,
    RakutenLiveSmokeReceipt,
    RakutenLiveSmokeRequest,
    SecretText,
    fail_live_smoke,
)


class RakutenLiveSmokeAuthorizer(Protocol):
    """Atomically validate and consume one externally trusted grant hash."""

    def consume(
        self,
        *,
        grant_sha256: str,
        request_sha256: str,
        observed_at: datetime,
    ) -> bool: ...


class RakutenCredentialSource(Protocol):
    """Resolve the two fixed aliases without exposing storage details."""

    def read(self, alias: str) -> SecretText: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@final
class SystemClock:
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@final
class RakutenLiveSmokeRunner:
    """Consume one trusted grant, perform at most one GET, and return a receipt."""

    __slots__ = (
        "_authorizer",
        "_clock",
        "_consumed",
        "_credentials",
        "_lock",
        "_transport",
    )

    def __init__(
        self,
        *,
        authorizer: RakutenLiveSmokeAuthorizer,
        credentials: RakutenCredentialSource,
        transport: RakutenLiveSmokeTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._credentials = credentials
        self._transport = (
            UrllibRakutenLiveSmokeTransport() if transport is None else transport
        )
        self._clock = SystemClock() if clock is None else clock
        self._lock = Lock()
        self._consumed = False

    def run(
        self,
        *,
        request: RakutenLiveSmokeRequest,
        grant: RakutenLiveSmokeGrant,
    ) -> RakutenLiveSmokeReceipt:
        if (
            type(request) is not RakutenLiveSmokeRequest
            or type(grant) is not RakutenLiveSmokeGrant
        ):
            fail_live_smoke()
        try:
            now = self._clock.now()
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.NOT_AUTHORIZED)
        if not grant.permits(request.fingerprint, now):
            fail_live_smoke(RakutenLiveSmokeFailureCode.NOT_AUTHORIZED)
        with self._lock:
            if self._consumed:
                fail_live_smoke(RakutenLiveSmokeFailureCode.NOT_AUTHORIZED)
            self._consumed = True
        try:
            authorized = self._authorizer.consume(
                grant_sha256=grant.fingerprint,
                request_sha256=request.fingerprint,
                observed_at=now,
            )
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.NOT_AUTHORIZED)
        if authorized is not True:
            fail_live_smoke(RakutenLiveSmokeFailureCode.NOT_AUTHORIZED)

        try:
            application_id = self._credentials.read(RAKUTEN_APPLICATION_ID_ALIAS)
            access_key = self._credentials.read(RAKUTEN_ACCESS_KEY_ALIAS)
        except RakutenLiveSmokeFailure:
            raise
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE)
        if type(application_id) is not SecretText or type(access_key) is not SecretText:
            fail_live_smoke(RakutenLiveSmokeFailureCode.CREDENTIAL_UNAVAILABLE)

        try:
            response = self._transport.get(
                origin=RAKUTEN_API_ORIGIN,
                path=RAKUTEN_ITEM_SEARCH_PATH,
                query=request._query(application_id),
                headers=(
                    ("Accept", "application/json"),
                    ("Accept-Encoding", "identity"),
                    ("Connection", "close"),
                    ("User-Agent", "RAOS-ST0505/1"),
                    ("accessKey", access_key._transport_value()),
                ),
                timeout_seconds=NETWORK_TIMEOUT_SECONDS,
                max_body_bytes=MAX_RESPONSE_BYTES,
            )
        except RakutenLiveSmokeFailure:
            raise
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        if type(response) is not RakutenHttpResponse:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        if 300 <= response.status <= 399:
            fail_live_smoke(RakutenLiveSmokeFailureCode.REDIRECT_FORBIDDEN)
        if response.status in {401, 403}:
            fail_live_smoke(RakutenLiveSmokeFailureCode.AUTH_REJECTED)
        if response.status == 429:
            fail_live_smoke(RakutenLiveSmokeFailureCode.RATE_LIMITED)
        if response.status in {400, 404}:
            fail_live_smoke(RakutenLiveSmokeFailureCode.REQUEST_REJECTED)
        if 500 <= response.status <= 599:
            fail_live_smoke(RakutenLiveSmokeFailureCode.PROVIDER_UNAVAILABLE)
        if response.status != 200:
            fail_live_smoke(RakutenLiveSmokeFailureCode.PROVIDER_REJECTED)
        return build_receipt(response=response, request=request, observed_at=now)


__all__ = [
    "MAX_RESPONSE_BYTES",
    "RAKUTEN_ACCESS_KEY_ALIAS",
    "RAKUTEN_API_DOCUMENTATION_RETRIEVED_ON",
    "RAKUTEN_API_DOCUMENTATION_URL",
    "RAKUTEN_API_ORIGIN",
    "RAKUTEN_API_VERSION",
    "RAKUTEN_APPLICATION_ID_ALIAS",
    "RAKUTEN_ITEM_SEARCH_PATH",
    "STAGING_ENVIRONMENT",
    "RateObservation",
    "RakutenCredentialSource",
    "RakutenHttpResponse",
    "RakutenLiveSmokeAuthorizer",
    "RakutenLiveSmokeFailure",
    "RakutenLiveSmokeFailureCode",
    "RakutenLiveSmokeGrant",
    "RakutenLiveSmokeReceipt",
    "RakutenLiveSmokeRequest",
    "RakutenLiveSmokeRunner",
    "RakutenLiveSmokeTransport",
    "SecretText",
    "UrllibRakutenLiveSmokeTransport",
]
