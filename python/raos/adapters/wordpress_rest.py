"""No-I/O builder for the official WordPress REST posts draft boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, NoReturn, SupportsIndex, cast, final
from urllib.parse import SplitResult, urlsplit

from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    DraftOperation,
    MarketLearningPilotFailureCode,
    WORDPRESS_DRAFT_STATUS,
    WordPressDraftReceipt,
    fail_market_learning_pilot,
)


_CREATE_PATH = "/wp-json/wp/v2/posts"
_UPDATE_PATH = re.compile(r"/wp-json/wp/v2/posts/([1-9][0-9]{0,18})\Z", re.ASCII)
_CREATE_ROUTE = "/wp/v2/posts"
_UPDATE_ROUTE = re.compile(r"/wp/v2/posts/([1-9][0-9]{0,18})\Z", re.ASCII)
_POST_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_SECRET_ALIAS = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z", re.ASCII)
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.ASCII)
_MAX_ORIGIN_CHARS = 2048
_MAX_REQUEST_BYTES = 1_100_000
_MAX_RESPONSE_BYTES = 4_000_000
_MAX_RESPONSE_DEPTH = 64
_MAX_RESPONSE_NODES = 100_000


class _RedactedTransportValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-wordpress-rest>)"

    def __str__(self) -> str:
        return "<redacted-wordpress-rest>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress REST value serialization is disabled")


def _split_url(value: object, *, origin_only: bool) -> SplitResult:
    if (
        type(value) is not str
        or not 1 <= len(value) <= _MAX_ORIGIN_CHARS
        or value != value.strip()
    ):
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID
        )
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID
        )
    hostname = parts.hostname
    if (
        not value.startswith("https://")
        or parts.scheme != "https"
        or not parts.netloc
        or hostname is None
        or len(hostname) > 253
        or any(_HOST_LABEL.fullmatch(label) is None for label in hostname.split("."))
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "@" in parts.netloc
        or "%" in parts.netloc
        or "\\" in value
        or any(ord(character) < 33 or ord(character) == 127 for character in value)
        or parts.netloc != parts.netloc.lower()
        or (port is not None and not 1 <= port <= 65535)
        or (origin_only and parts.path != "")
    ):
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID
        )
    try:
        parts.netloc.encode("ascii", errors="strict")
    except UnicodeError:
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID
        )
    return parts


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        value[key] = item
    return value


def _reject_constant(value: str) -> NoReturn:
    del value
    fail_market_learning_pilot(
        MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )


def _request_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        value[key] = item
    return value


def _reject_request_constant(value: str) -> NoReturn:
    del value
    fail_market_learning_pilot(MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID)


def _validate_response_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_RESPONSE_NODES or depth > _MAX_RESPONSE_DEPTH:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                fail_market_learning_pilot(
                    MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
                )
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
            continue
        fail_market_learning_pilot(
            MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
        )


@dataclass(frozen=True, slots=True, repr=False)
class WordPressRestRequest(_RedactedTransportValue):
    method: str
    url: str
    path: str
    logical_route: str
    headers: tuple[tuple[str, str], ...]
    body_json: str
    credential_secret_alias: str
    idempotency_key: str
    expected_http_status: int
    existing_draft_receipt: WordPressDraftReceipt | None

    def __post_init__(self) -> None:
        parts = _split_url(self.url, origin_only=False)
        body_size = 0
        if type(self.body_json) is str:
            try:
                body_size = len(self.body_json.encode("utf-8", errors="strict"))
            except UnicodeError:
                fail_market_learning_pilot(
                    MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
                )
        update_match = (
            _UPDATE_PATH.fullmatch(self.path) if type(self.path) is str else None
        )
        update_route_match = (
            _UPDATE_ROUTE.fullmatch(self.logical_route)
            if type(self.logical_route) is str
            else None
        )
        valid_endpoint = bool(
            (
                self.path == _CREATE_PATH
                and self.logical_route == _CREATE_ROUTE
                and self.expected_http_status == 201
                and self.existing_draft_receipt is None
            )
            or (
                update_match is not None
                and update_route_match is not None
                and update_route_match.group(1) == update_match.group(1)
                and int(update_match.group(1)) <= (1 << 63) - 1
                and self.expected_http_status == 200
                and type(self.existing_draft_receipt) is WordPressDraftReceipt
                and self.existing_draft_receipt.draft_id == int(update_match.group(1))
            )
        )
        if (
            type(self.method) is not str
            or self.method != "POST"
            or type(self.path) is not str
            or type(self.logical_route) is not str
            or parts.path != self.path
            or parts.query
            or parts.fragment
            or self.headers != (("Content-Type", "application/json"),)
            or type(self.body_json) is not str
            or not 2 <= body_size <= _MAX_REQUEST_BYTES
            or type(self.credential_secret_alias) is not str
            or _SECRET_ALIAS.fullmatch(self.credential_secret_alias) is None
            or len(self.credential_secret_alias) > 64
            or type(self.idempotency_key) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.idempotency_key) is None
            or type(self.expected_http_status) is not int
            or self.expected_http_status not in {200, 201}
            or not valid_endpoint
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        try:
            payload = json.loads(
                self.body_json,
                object_pairs_hook=_request_json_pairs,
                parse_constant=_reject_request_constant,
            )
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except UnicodeError, ValueError, RecursionError:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        if type(payload) is not dict:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        mapping = cast(dict[object, object], payload)
        body_keys = set(mapping)
        slug = mapping.get("slug")
        if (
            canonical != self.body_json
            or body_keys
            not in (
                {"content", "status", "title"},
                {"content", "slug", "status", "title"},
            )
            or type(mapping.get("title")) is not str
            or type(mapping.get("content")) is not str
            or mapping.get("status") != WORDPRESS_DRAFT_STATUS
            or (
                "slug" in body_keys
                and (
                    self.path != _CREATE_PATH
                    or type(slug) is not str
                    or not 1 <= len(slug) <= 200
                    or _POST_SLUG.fullmatch(slug) is None
                )
            )
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        title = cast(str, mapping["title"])
        content = cast(str, mapping["content"])
        try:
            title.encode("utf-8", errors="strict")
            content_size = len(content.encode("utf-8", errors="strict"))
        except UnicodeError:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        if (
            not 1 <= len(title) <= 512
            or title != title.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in title)
            or not content.strip()
            or content_size > 1_000_000
            or any(
                ord(character) < 32 and character not in "\t\n\r"
                for character in content
            )
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class WordPressDraftResponseMetadata(_RedactedTransportValue):
    draft_id: int
    status: str
    http_status: int

    def __post_init__(self) -> None:
        if (
            type(self.draft_id) is not int
            or not 1 <= self.draft_id <= (1 << 63) - 1
            or type(self.status) is not str
            or self.status != WORDPRESS_DRAFT_STATUS
            or type(self.http_status) is not int
            or self.http_status not in {200, 201}
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )


@final
class OfficialWordPressRestRequestBuilder:
    """Build and validate official posts requests without executing them."""

    __slots__ = ("_origin", "_origin_netloc")

    def __init__(self, *, origin: str) -> None:
        parts = _split_url(origin, origin_only=True)
        self._origin = origin
        self._origin_netloc = parts.netloc

    def __repr__(self) -> str:
        return "OfficialWordPressRestRequestBuilder(<redacted-wordpress-origin>)"

    def build(
        self,
        *,
        candidate: BoundWordPressDraft,
        endpoint_url: str,
        credential_secret_alias: str,
        existing_draft_receipt: WordPressDraftReceipt | None = None,
    ) -> WordPressRestRequest:
        if type(candidate) is not BoundWordPressDraft:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        if (
            type(credential_secret_alias) is not str
            or not 1 <= len(credential_secret_alias) <= 64
            or _SECRET_ALIAS.fullmatch(credential_secret_alias) is None
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        if candidate.intent.operation is DraftOperation.CREATE_DRAFT:
            path = _CREATE_PATH
            logical_route = _CREATE_ROUTE
            expected_status = 201
            if existing_draft_receipt is not None:
                fail_market_learning_pilot(
                    MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
                )
        else:
            path = f"{_CREATE_PATH}/{candidate.intent.existing_draft_id}"
            logical_route = f"{_CREATE_ROUTE}/{candidate.intent.existing_draft_id}"
            expected_status = 200
            if (
                type(existing_draft_receipt) is not WordPressDraftReceipt
                or existing_draft_receipt.draft_id != candidate.intent.existing_draft_id
            ):
                fail_market_learning_pilot(
                    MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
                )
        parts = _split_url(endpoint_url, origin_only=False)
        if (
            parts.netloc != self._origin_netloc
            or endpoint_url != f"{self._origin}{path}"
            or parts.path != path
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        try:
            body_json = json.dumps(
                {
                    "content": candidate.intent.content,
                    "status": WORDPRESS_DRAFT_STATUS,
                    "title": candidate.intent.title,
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except TypeError, ValueError, UnicodeError:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
            )
        return WordPressRestRequest(
            method="POST",
            url=endpoint_url,
            path=path,
            logical_route=logical_route,
            headers=(("Content-Type", "application/json"),),
            body_json=body_json,
            credential_secret_alias=credential_secret_alias,
            idempotency_key=candidate.operation_binding_sha256,
            expected_http_status=expected_status,
            existing_draft_receipt=existing_draft_receipt,
        )

    def validate_response(
        self,
        *,
        request: WordPressRestRequest,
        http_status: int,
        body: bytes,
    ) -> WordPressDraftResponseMetadata:
        if (
            type(request) is not WordPressRestRequest
            or request.url != f"{self._origin}{request.path}"
            or urlsplit(request.url).netloc != self._origin_netloc
            or type(http_status) is not int
            or http_status != request.expected_http_status
            or type(body) is not bytes
            or not 2 <= len(body) <= _MAX_RESPONSE_BYTES
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        try:
            payload = json.loads(
                body.decode("utf-8", errors="strict"),
                object_pairs_hook=_json_pairs,
                parse_constant=_reject_constant,
            )
        except UnicodeError, ValueError, RecursionError:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        if type(payload) is not dict:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        _validate_response_tree(cast(object, payload))
        mapping = cast(dict[str, object], payload)
        draft_id = mapping.get("id")
        status = mapping.get("status")
        if (
            type(draft_id) is not int
            or not 1 <= draft_id <= (1 << 63) - 1
            or type(status) is not str
            or status != WORDPRESS_DRAFT_STATUS
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
            )
        if request.path != _CREATE_PATH:
            expected_id = int(request.path.removeprefix(f"{_CREATE_PATH}/"))
            if draft_id != expected_id:
                fail_market_learning_pilot(
                    MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
                )
        return WordPressDraftResponseMetadata(
            draft_id=draft_id,
            status=status,
            http_status=http_status,
        )


__all__ = [
    "OfficialWordPressRestRequestBuilder",
    "WordPressDraftResponseMetadata",
    "WordPressRestRequest",
]
