"""Bounded, fail-closed executable boundary for ST-0505.

No CLI, scheduler, persistence layer, publication path, or provider call is
activated by importing this module. A caller must inject a short-lived staging
grant and fixed-alias credentials. The default transport performs one HTTPS GET
with system CA verification, proxy inheritance disabled, and redirects denied.
"""

from __future__ import annotations

import ssl
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol, final
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
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


class RakutenLiveSmokeTransport(Protocol):
    def get(
        self,
        *,
        origin: str,
        path: str,
        query: tuple[tuple[str, str], ...],
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> RakutenHttpResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


@final
class UrllibRakutenLiveSmokeTransport:
    """One-attempt HTTPS transport using the system trust store."""

    __slots__ = ()

    def get(
        self,
        *,
        origin: str,
        path: str,
        query: tuple[tuple[str, str], ...],
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> RakutenHttpResponse:
        if (
            origin != RAKUTEN_API_ORIGIN
            or path != RAKUTEN_ITEM_SEARCH_PATH
            or type(query) is not tuple
            or type(headers) is not tuple
            or type(timeout_seconds) is not float
            or timeout_seconds != NETWORK_TIMEOUT_SECONDS
            or type(max_body_bytes) is not int
            or max_body_bytes != MAX_RESPONSE_BYTES
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        encoded_query = urlencode(
            query,
            doseq=False,
            encoding="utf-8",
            errors="strict",
        )
        url = f"{origin}{path}?{encoded_query}"
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.rakuten.co.jp"
            or parsed.path != RAKUTEN_ITEM_SEARCH_PATH
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)

        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        opener = build_opener(
            ProxyHandler({}),
            _NoRedirectHandler(),
            HTTPSHandler(context=context),
        )
        outgoing = Request(url=url, method="GET")
        for name, value in headers:
            outgoing.add_header(name, value)
        try:
            response = opener.open(outgoing, timeout=timeout_seconds)
        except HTTPError as error:
            try:
                response_headers = tuple(error.headers.items())
                status = int(error.code)
            finally:
                error.close()
            return RakutenHttpResponse(
                status=status,
                headers=response_headers,
                body=b"",
            )
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)

        try:
            status = int(response.status)
            if response.geturl() != url:
                return RakutenHttpResponse(
                    status=302,
                    headers=tuple(response.headers.items()),
                    body=b"",
                )
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    length = int(content_length, 10)
                except ValueError:
                    fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
                if length < 0 or length > max_body_bytes:
                    fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE)
            body = response.read(max_body_bytes + 1)
            return RakutenHttpResponse(
                status=status,
                headers=tuple(response.headers.items()),
                body=body,
            )
        except RakutenLiveSmokeFailure:
            raise
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        finally:
            response.close()


@final
class RakutenLiveSmokeRunner:
    """Consume one exact grant, perform at most one GET, and return a receipt."""

    __slots__ = ("_clock", "_consumed", "_credentials", "_lock", "_transport")

    def __init__(
        self,
        *,
        credentials: RakutenCredentialSource,
        transport: RakutenLiveSmokeTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
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
