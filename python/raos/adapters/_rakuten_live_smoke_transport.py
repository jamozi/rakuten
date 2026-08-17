"""One-attempt HTTPS transport for the bounded ST-0505 live smoke."""

from __future__ import annotations

import ssl
from typing import Final, Protocol, final
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from raos.domain.catalog.rakuten_live_smoke import (
    MAX_RESPONSE_BYTES,
    NETWORK_TIMEOUT_SECONDS,
    RAKUTEN_API_ORIGIN,
    RAKUTEN_ITEM_SEARCH_PATH,
    RakutenHttpResponse,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeFailureCode,
    fail_live_smoke,
)


_QUERY_NAMES: Final = (
    "applicationId",
    "format",
    "formatVersion",
    "keyword",
    "hits",
    "page",
    "sort",
    "availability",
    "elements",
)
_HEADER_NAMES: Final = (
    "Accept",
    "Accept-Encoding",
    "Connection",
    "User-Agent",
    "accessKey",
)
_ELEMENTS_VALUE: Final = "itemCode,itemName,itemPrice,itemUrl,shopCode"
_RESPONSE_HEADER_ALLOWLIST: Final = frozenset(
    {
        "content-encoding",
        "content-type",
        "x-rakuten-request-id",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-request-id",
    }
)


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


def _bounded_ascii(value: object, *, minimum: int, maximum: int) -> str:
    if (
        type(value) is not str
        or not minimum <= len(value) <= maximum
        or not value.isascii()
        or any(ord(character) < 33 or ord(character) == 127 for character in value)
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    return value


def _validate_query(query: object) -> tuple[tuple[str, str], ...]:
    if type(query) is not tuple or len(query) != len(_QUERY_NAMES):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    rows = query
    exact_rows: list[tuple[str, str]] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 2:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        name, value = row
        if type(name) is not str or type(value) is not str:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        exact_rows.append((name, value))
    exact = tuple(exact_rows)
    if tuple(name for name, _value in exact) != _QUERY_NAMES:
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    values = dict(exact)
    _bounded_ascii(values["applicationId"], minimum=1, maximum=128)
    keyword = values["keyword"]
    if (
        type(keyword) is not str
        or keyword != keyword.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in keyword)
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    try:
        keyword_bytes = keyword.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    if not 2 <= len(keyword_bytes) <= 128:
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    expected = {
        "availability": "1",
        "elements": _ELEMENTS_VALUE,
        "format": "json",
        "formatVersion": "2",
        "hits": "1",
        "page": "1",
        "sort": "standard",
    }
    if any(values[name] != value for name, value in expected.items()):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    return exact


def _validate_headers(headers: object) -> tuple[tuple[str, str], ...]:
    if type(headers) is not tuple or len(headers) != len(_HEADER_NAMES):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    rows = headers
    exact_rows: list[tuple[str, str]] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 2:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        name, value = row
        if type(name) is not str or type(value) is not str:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        exact_rows.append((name, value))
    exact = tuple(exact_rows)
    if tuple(name for name, _value in exact) != _HEADER_NAMES:
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    values = dict(exact)
    if (
        values["Accept"] != "application/json"
        or values["Accept-Encoding"] != "identity"
        or values["Connection"] != "close"
        or values["User-Agent"] != "RAOS-ST0505/1"
    ):
        fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
    _bounded_ascii(values["accessKey"], minimum=1, maximum=512)
    return exact


def _header_values(
    rows: tuple[tuple[str, str], ...],
    name: str,
) -> tuple[str, ...]:
    lowered = name.lower()
    return tuple(value for key, value in rows if key.lower() == lowered)


def _declared_content_length(rows: tuple[tuple[str, str], ...]) -> int | None:
    values = _header_values(rows, "Content-Length")
    if len(values) > 1:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    if not values:
        return None
    value = values[0]
    if not value.isascii() or not value.isdigit():
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
    parsed = int(value, 10)
    if parsed > MAX_RESPONSE_BYTES:
        fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE)
    return parsed


def _selected_headers(
    rows: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, value)
        for name, value in rows
        if name.lower() in _RESPONSE_HEADER_ALLOWLIST
    )


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
            or type(timeout_seconds) is not float
            or timeout_seconds != NETWORK_TIMEOUT_SECONDS
            or type(max_body_bytes) is not int
            or max_body_bytes != MAX_RESPONSE_BYTES
        ):
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        exact_query = _validate_query(query)
        exact_headers = _validate_headers(headers)
        encoded_query = urlencode(
            exact_query,
            doseq=False,
            encoding="utf-8",
            errors="strict",
        )
        if len(encoded_query.encode("ascii")) > 4096:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        url = f"{origin}{path}?{encoded_query}"
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "openapi.rakuten.co.jp"
            or parsed.path != RAKUTEN_ITEM_SEARCH_PATH
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or "accessKey=" in parsed.query
            or "affiliateId=" in parsed.query
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
        for name, value in exact_headers:
            outgoing.add_header(name, value)
        try:
            response = opener.open(outgoing, timeout=timeout_seconds)
        except HTTPError as error:
            try:
                status = int(error.code)
            finally:
                error.close()
            return RakutenHttpResponse(status=status, headers=(), body=b"")
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)

        try:
            status = int(response.status)
            response_rows = tuple(response.headers.items())
            if response.geturl() != url:
                return RakutenHttpResponse(status=302, headers=(), body=b"")
            declared_length = _declared_content_length(response_rows)
            body = response.read(max_body_bytes + 1)
            if len(body) > max_body_bytes:
                fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_TOO_LARGE)
            if declared_length is not None and declared_length != len(body):
                fail_live_smoke(RakutenLiveSmokeFailureCode.RESPONSE_INVALID)
            return RakutenHttpResponse(
                status=status,
                headers=_selected_headers(response_rows),
                body=body,
            )
        except RakutenLiveSmokeFailure:
            raise
        except Exception:
            fail_live_smoke(RakutenLiveSmokeFailureCode.TRANSPORT_FAILURE)
        finally:
            response.close()


__all__ = ["RakutenLiveSmokeTransport", "UrllibRakutenLiveSmokeTransport"]
