"""One-shot application service for the ST-0505 Rakuten live smoke."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, NoReturn, cast

from raos.domain.catalog.rakuten_live_smoke import (
    RakutenLiveSmokeAuthClassification,
    RakutenLiveSmokeDiagnosticCode,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeObservation,
    RakutenLiveSmokeRateClassification,
    RakutenLiveSmokeSchemaClassification,
    fail_rakuten_live_smoke,
    fixed_rakuten_live_smoke_policy,
    valid_affiliate_url,
    valid_json_content_type,
)
from raos.ports.rakuten_live_smoke import (
    RakutenLiveSmokeCredentialReader,
    RakutenLiveSmokeTransport,
)


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000
_TOP_LEVEL_KEYS = frozenset(
    {"count", "page", "first", "last", "hits", "pageCount", "items"}
)
_ITEM_KEYS = frozenset({"affiliateUrl"})


def _fail(
    code: RakutenLiveSmokeDiagnosticCode,
    *,
    body_byte_count: int,
    response_sha256: str,
    affiliate_url_present: bool = False,
) -> NoReturn:
    fail_rakuten_live_smoke(
        code,
        http_status=200,
        body_byte_count=body_byte_count,
        response_sha256=response_sha256,
        request_count=1,
        auth=RakutenLiveSmokeAuthClassification.ACCEPTED,
        schema=RakutenLiveSmokeSchemaClassification.INVALID,
        rate=RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED,
        affiliate_url_present=affiliate_url_present,
    )


def _json_pairs(
    pairs: list[tuple[str, Any]],
    *,
    body_byte_count: int,
    response_sha256: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_rakuten_live_smoke(
                RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_DUPLICATE_KEY,
                http_status=200,
                body_byte_count=body_byte_count,
                response_sha256=response_sha256,
                request_count=1,
                auth=RakutenLiveSmokeAuthClassification.ACCEPTED,
                schema=RakutenLiveSmokeSchemaClassification.INVALID,
                rate=RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED,
            )
        result[key] = value
    return result


def _reject_constant(
    value: str, *, body_byte_count: int, response_sha256: str
) -> NoReturn:
    del value
    fail_rakuten_live_smoke(
        RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_NONFINITE,
        http_status=200,
        body_byte_count=body_byte_count,
        response_sha256=response_sha256,
        request_count=1,
        auth=RakutenLiveSmokeAuthClassification.ACCEPTED,
        schema=RakutenLiveSmokeSchemaClassification.INVALID,
        rate=RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED,
    )


def _validate_json_tree(
    value: object, *, body_byte_count: int, response_sha256: str
) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail(
                RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_TREE_INVALID,
                body_byte_count=body_byte_count,
                response_sha256=response_sha256,
            )
        if current is None or type(current) in {bool, int, str}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail(
                    RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_NONFINITE,
                    body_byte_count=body_byte_count,
                    response_sha256=response_sha256,
                )
            continue
        if type(current) is list:
            stack.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            if any(type(key) is not str for key in mapping):
                _fail(
                    RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_TREE_INVALID,
                    body_byte_count=body_byte_count,
                    response_sha256=response_sha256,
                )
            stack.extend((item, depth + 1) for item in mapping.values())
            continue
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_TREE_INVALID,
            body_byte_count=body_byte_count,
            response_sha256=response_sha256,
        )


def _parse_success_body(body: bytes, *, response_sha256: str) -> None:
    byte_count = len(body)
    if byte_count > MAX_RESPONSE_BYTES:
        fail_rakuten_live_smoke(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED,
            http_status=200,
            body_byte_count=byte_count,
            request_count=1,
            auth=RakutenLiveSmokeAuthClassification.ACCEPTED,
            schema=RakutenLiveSmokeSchemaClassification.INVALID,
            rate=RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED,
        )
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_ENCODING_INVALID,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=lambda pairs: _json_pairs(
                pairs,
                body_byte_count=byte_count,
                response_sha256=response_sha256,
            ),
            parse_constant=lambda value: _reject_constant(
                value,
                body_byte_count=byte_count,
                response_sha256=response_sha256,
            ),
        )
    except RakutenLiveSmokeFailure:
        raise
    except json.JSONDecodeError, RecursionError, ValueError:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_JSON_INVALID,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    _validate_json_tree(
        value,
        body_byte_count=byte_count,
        response_sha256=response_sha256,
    )
    if type(value) is not dict:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    root = cast(dict[str, object], value)
    if frozenset(root) != _TOP_LEVEL_KEYS:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    if type(root["count"]) is not int or not 1 <= root["count"] <= (1 << 63) - 1:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    for name, expected in (
        ("page", 1),
        ("first", 1),
        ("last", 1),
        ("hits", 1),
    ):
        if type(root[name]) is not int or root[name] != expected:
            _fail(
                RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
                body_byte_count=byte_count,
                response_sha256=response_sha256,
            )
    if type(root["pageCount"]) is not int or not 1 <= root["pageCount"] <= 100:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    items_value = root["items"]
    if type(items_value) is not list:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    items = cast(list[object], items_value)
    if len(items) != 1 or type(items[0]) is not dict:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    item = cast(dict[str, object], items[0])
    if frozenset(item) != _ITEM_KEYS:
        _fail(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_SCHEMA_DRIFT,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    affiliate_url = item["affiliateUrl"]
    if affiliate_url == "" or affiliate_url is None:
        _fail(
            RakutenLiveSmokeDiagnosticCode.AFFILIATE_URL_MISSING,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )
    if not valid_affiliate_url(affiliate_url):
        _fail(
            RakutenLiveSmokeDiagnosticCode.AFFILIATE_URL_INVALID,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
        )


_HTTP_FAILURES = {
    400: RakutenLiveSmokeDiagnosticCode.HTTP_400,
    401: RakutenLiveSmokeDiagnosticCode.HTTP_401,
    403: RakutenLiveSmokeDiagnosticCode.HTTP_403,
    404: RakutenLiveSmokeDiagnosticCode.HTTP_404,
    429: RakutenLiveSmokeDiagnosticCode.HTTP_429,
    500: RakutenLiveSmokeDiagnosticCode.HTTP_500,
    503: RakutenLiveSmokeDiagnosticCode.HTTP_503,
}


@dataclass(slots=True)
class RakutenLiveSmokeService:
    """Attempt the fixed smoke once; retry and pagination do not exist."""

    credential_reader: RakutenLiveSmokeCredentialReader
    transport: RakutenLiveSmokeTransport
    _attempted: bool = False

    def run(self) -> RakutenLiveSmokeObservation:
        if self._attempted:
            fail_rakuten_live_smoke(
                RakutenLiveSmokeDiagnosticCode.REQUEST_ALREADY_ATTEMPTED
            )
        self._attempted = True
        policy = fixed_rakuten_live_smoke_policy()
        credentials = self.credential_reader.read()
        response = self.transport.execute(policy, credentials)
        byte_count = len(response.body)
        if byte_count > MAX_RESPONSE_BYTES:
            auth = RakutenLiveSmokeAuthClassification.NOT_OBSERVED
            schema = RakutenLiveSmokeSchemaClassification.NOT_OBSERVED
            rate = RakutenLiveSmokeRateClassification.NOT_OBSERVED
            if response.status == 200:
                auth = RakutenLiveSmokeAuthClassification.ACCEPTED
                schema = RakutenLiveSmokeSchemaClassification.INVALID
                rate = RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED
            elif response.status in {401, 403}:
                auth = RakutenLiveSmokeAuthClassification.REJECTED
            elif response.status == 429:
                rate = RakutenLiveSmokeRateClassification.THROTTLED
            fail_rakuten_live_smoke(
                RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED,
                http_status=response.status,
                body_byte_count=byte_count,
                request_count=1,
                auth=auth,
                schema=schema,
                rate=rate,
            )
        response_sha256 = response.response_sha256
        if response.status != 200:
            code = _HTTP_FAILURES.get(response.status)
            if 300 <= response.status <= 399:
                code = RakutenLiveSmokeDiagnosticCode.HTTP_REDIRECT_REJECTED
            if code is None:
                code = RakutenLiveSmokeDiagnosticCode.HTTP_STATUS_UNEXPECTED
            auth = RakutenLiveSmokeAuthClassification.NOT_OBSERVED
            rate = RakutenLiveSmokeRateClassification.NOT_OBSERVED
            if response.status in {401, 403}:
                auth = RakutenLiveSmokeAuthClassification.REJECTED
            elif response.status == 429:
                rate = RakutenLiveSmokeRateClassification.THROTTLED
            fail_rakuten_live_smoke(
                code,
                http_status=response.status,
                body_byte_count=byte_count,
                response_sha256=response_sha256,
                request_count=1,
                auth=auth,
                rate=rate,
            )
        if not valid_json_content_type(response.content_type):
            _fail(
                RakutenLiveSmokeDiagnosticCode.RESPONSE_CONTENT_TYPE_INVALID,
                body_byte_count=byte_count,
                response_sha256=response_sha256,
            )
        _parse_success_body(response.body, response_sha256=response_sha256)
        return RakutenLiveSmokeObservation(
            http_status=200,
            body_byte_count=byte_count,
            response_sha256=response_sha256,
            request_count=1,
            affiliate_url_present=True,
        )


__all__ = ["MAX_RESPONSE_BYTES", "RakutenLiveSmokeService"]
