"""Closed recorded-only Rakuten Ichiba ITEM_SEARCH values for ST-0502."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, NoReturn, SupportsIndex
from uuid import UUID


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_REDACTED = "<redacted-rakuten-item-search>"
_MAX_BODY_BYTES = 2 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 50_000


class ItemSearchOperation(str, Enum):
    ITEM_SEARCH = "ITEM_SEARCH"


class ItemSearchPurpose(str, Enum):
    CATEGORY_DISCOVERY = "CATEGORY_DISCOVERY"
    ARTICLE_RESEARCH = "ARTICLE_RESEARCH"
    OFFER_REFRESH = "OFFER_REFRESH"
    CONTRACT_TEST = "CONTRACT_TEST"


class ItemSearchSort(str, Enum):
    STANDARD = "standard"
    REVIEW_COUNT_ASCENDING = "+reviewCount"
    REVIEW_COUNT_DESCENDING = "-reviewCount"
    REVIEW_AVERAGE_ASCENDING = "+reviewAverage"
    REVIEW_AVERAGE_DESCENDING = "-reviewAverage"
    PRICE_ASCENDING = "+itemPrice"
    PRICE_DESCENDING = "-itemPrice"
    UPDATED_ASCENDING = "+updateTimestamp"
    UPDATED_DESCENDING = "-updateTimestamp"


class ItemSearchElement(str, Enum):
    AFFILIATE_URL = "affiliateUrl"
    AFFILIATE_RATE = "affiliateRate"
    AVAILABILITY = "availability"
    CATCHCOPY = "catchcopy"
    COUNT = "count"
    FIRST = "first"
    GENRE_ID = "genreId"
    HITS = "hits"
    ITEM_CODE = "itemCode"
    ITEM_CAPTION = "itemCaption"
    ITEM_NAME = "itemName"
    ITEM_PRICE = "itemPrice"
    ITEM_URL = "itemUrl"
    LAST = "last"
    MEDIUM_IMAGE_URLS = "mediumImageUrls"
    PAGE = "page"
    PAGE_COUNT = "pageCount"
    POSTAGE_FLAG = "postageFlag"
    REVIEW_AVERAGE = "reviewAverage"
    REVIEW_COUNT = "reviewCount"
    SHOP_CODE = "shopCode"
    SHOP_NAME = "shopName"
    SMALL_IMAGE_URLS = "smallImageUrls"
    TAG_IDS = "tagIds"
    UPDATE_TIMESTAMP = "updateTimestamp"


CANONICAL_ITEM_SEARCH_ELEMENTS: tuple[ItemSearchElement, ...] = tuple(
    sorted(ItemSearchElement, key=lambda element: element.value)
)


class ProviderMode(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class ProviderHealthStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class StorageExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class PersistenceExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ProviderFailureClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    MALFORMED = "MALFORMED"
    UNAVAILABLE = "UNAVAILABLE"

    @property
    def retryable(self) -> bool:
        return self is ProviderFailureClass.TRANSIENT


class RakutenItemSearchFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RAW_RESPONSE_INVALID = "RAW_RESPONSE_INVALID"
    RECORDING_UNAVAILABLE = "RECORDING_UNAVAILABLE"
    NORMALIZATION_UNAVAILABLE = "NORMALIZATION_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten item search serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class RakutenItemSearchFailure(RuntimeError):
    code: RakutenItemSearchFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not RakutenItemSearchFailureCode:
            raise TypeError("invalid Rakuten item search failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RakutenItemSearchFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten item search failure serialization is not supported")


def fail_item_search(
    code: RakutenItemSearchFailureCode = RakutenItemSearchFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise RakutenItemSearchFailure(code) from None


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_item_search()
    return value


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_item_search()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_item_search()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_item_search()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_item_search()
    return value


def _reject_constant(value: str) -> NoReturn:
    del value
    fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in current)
            continue
        if type(current) is dict:
            pending.extend((item, depth + 1) for item in current.values())
            continue
        fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class RakutenItemSearchRequest(_RedactedValue):
    api_version: str
    format_version: int
    keyword: str | None
    shop_code: str | None
    item_code: str | None
    genre_id: int | None
    hits: int
    page: int
    sort: ItemSearchSort
    elements: tuple[ItemSearchElement, ...]
    min_price_jpy: int | None
    max_price_jpy: int | None
    or_flag: bool
    availability: bool
    postage_included_only: bool
    has_review_only: bool
    appoint_delivery_date_only: bool
    attribute_flag: bool
    genre_information_flag: bool

    def __post_init__(self) -> None:
        if type(self.api_version) is not str or self.api_version != "2026-07-01":
            fail_item_search()
        if type(self.format_version) is not int or self.format_version != 2:
            fail_item_search()
        if self.keyword is not None:
            _bounded_text(self.keyword, maximum=128)
        if self.shop_code is not None:
            _bounded_text(self.shop_code, maximum=128)
        if self.item_code is not None:
            _bounded_text(self.item_code, maximum=256)
            before, separator, after = self.item_code.partition(":")
            if not before or not separator or not after:
                fail_item_search()
        if self.genre_id is not None:
            _exact_int(self.genre_id, minimum=0, maximum=(1 << 63) - 1)
        if (
            self.keyword is None
            and self.shop_code is None
            and self.item_code is None
            and self.genre_id is None
        ):
            fail_item_search()
        _exact_int(self.hits, minimum=1, maximum=30)
        _exact_int(self.page, minimum=1, maximum=100)
        if (
            type(self.sort) is not ItemSearchSort
            or type(self.elements) is not tuple
            or self.elements != CANONICAL_ITEM_SEARCH_ELEMENTS
        ):
            fail_item_search()
        if self.min_price_jpy is not None:
            _exact_int(self.min_price_jpy, minimum=1, maximum=999_999_998)
        if self.max_price_jpy is not None:
            _exact_int(self.max_price_jpy, minimum=1, maximum=999_999_998)
        if (
            self.min_price_jpy is not None
            and self.max_price_jpy is not None
            and self.min_price_jpy > self.max_price_jpy
        ):
            fail_item_search()
        for flag in (
            self.or_flag,
            self.availability,
            self.postage_included_only,
            self.has_review_only,
            self.appoint_delivery_date_only,
            self.attribute_flag,
            self.genre_information_flag,
        ):
            if type(flag) is not bool:
                fail_item_search()

    @property
    def canonical_parameters(self) -> dict[str, object]:
        parameters: dict[str, object] = {
            "api_version": self.api_version,
            "appoint_delivery_date_only": self.appoint_delivery_date_only,
            "attribute_flag": self.attribute_flag,
            "availability": self.availability,
            "elements": [element.value for element in self.elements],
            "format_version": self.format_version,
            "genre_information_flag": self.genre_information_flag,
            "has_review_only": self.has_review_only,
            "hits": self.hits,
            "or_flag": self.or_flag,
            "page": self.page,
            "postage_included_only": self.postage_included_only,
            "sort": self.sort.value,
        }
        optional = {
            "genre_id": self.genre_id,
            "item_code": self.item_code,
            "keyword": self.keyword,
            "max_price_jpy": self.max_price_jpy,
            "min_price_jpy": self.min_price_jpy,
            "shop_code": self.shop_code,
        }
        parameters.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return dict(sorted(parameters.items()))

    @property
    def canonical_json(self) -> bytes:
        return json.dumps(
            self.canonical_parameters,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RakutenItemSearchCommand(_RedactedValue):
    endpoint_id: UUID
    purpose: ItemSearchPurpose
    operation: ItemSearchOperation
    request: RakutenItemSearchRequest
    fingerprint: str

    def __post_init__(self) -> None:
        if type(self.endpoint_id) is not UUID or self.endpoint_id.int == 0:
            fail_item_search()
        if (
            self.purpose is not ItemSearchPurpose.CONTRACT_TEST
            or type(self.purpose) is not ItemSearchPurpose
            or type(self.operation) is not ItemSearchOperation
            or self.operation is not ItemSearchOperation.ITEM_SEARCH
            or type(self.request) is not RakutenItemSearchRequest
        ):
            fail_item_search()
        expected = hashlib.sha256(
            b"ITEM_SEARCH\0"
            + self.endpoint_id.bytes
            + b"\0"
            + self.purpose.value.encode("ascii")
            + b"\0"
            + self.request.canonical_json
        ).hexdigest()
        if _sha256(self.fingerprint) != expected:
            fail_item_search()

    @classmethod
    def from_request(
        cls,
        *,
        endpoint_id: UUID,
        purpose: ItemSearchPurpose,
        request: RakutenItemSearchRequest,
    ) -> RakutenItemSearchCommand:
        if (
            type(endpoint_id) is not UUID
            or endpoint_id.int == 0
            or purpose is not ItemSearchPurpose.CONTRACT_TEST
            or type(purpose) is not ItemSearchPurpose
            or type(request) is not RakutenItemSearchRequest
        ):
            fail_item_search()
        fingerprint = hashlib.sha256(
            b"ITEM_SEARCH\0"
            + endpoint_id.bytes
            + b"\0"
            + purpose.value.encode("ascii")
            + b"\0"
            + request.canonical_json
        ).hexdigest()
        return cls(
            endpoint_id, purpose, ItemSearchOperation.ITEM_SEARCH, request, fingerprint
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderCapabilities(_RedactedValue):
    provider: str
    mode: ProviderMode
    operations: tuple[ItemSearchOperation, ...]
    live_eligible: bool

    def __post_init__(self) -> None:
        if (
            type(self.provider) is not str
            or self.provider != "RAKUTEN_ICHIBA"
            or self.mode is not ProviderMode.RECORDED_TEST_ONLY
            or self.operations != (ItemSearchOperation.ITEM_SEARCH,)
            or self.live_eligible is not False
        ):
            fail_item_search()


@dataclass(frozen=True, slots=True, repr=False)
class ProviderHealth(_RedactedValue):
    status: ProviderHealthStatus

    def __post_init__(self) -> None:
        if self.status is not ProviderHealthStatus.NOT_EXECUTED:
            fail_item_search()


@dataclass(frozen=True, slots=True, repr=False)
class RateLimitMetadata(_RedactedValue):
    limit: int
    remaining: int
    reset_at: datetime

    def __post_init__(self) -> None:
        _exact_int(self.limit, minimum=1, maximum=1_000_000)
        _exact_int(self.remaining, minimum=0, maximum=self.limit)
        _utc(self.reset_at)


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFailure(_RedactedValue):
    failure_class: ProviderFailureClass
    code: str

    def __post_init__(self) -> None:
        if type(self.failure_class) is not ProviderFailureClass:
            fail_item_search()
        if type(self.code) is not str or _SAFE_TOKEN.fullmatch(self.code) is None:
            fail_item_search()

    @property
    def retryable(self) -> bool:
        return self.failure_class.retryable


class RawItemSearchResponse(_RedactedValue):
    """Immutable exact response bytes; public access is metadata-only."""

    __slots__ = (
        "_api",
        "_body",
        "_body_sha256",
        "_http_status",
        "_provider",
        "_rate",
        "_received_at",
        "_request_fingerprint",
        "_request_id",
        "_sealed",
    )
    _provider: str
    _api: ItemSearchOperation
    _request_fingerprint: str
    _body: bytes
    _body_sha256: str
    _received_at: datetime
    _http_status: int
    _request_id: str
    _rate: RateLimitMetadata
    _sealed: bool

    def __init__(
        self,
        *,
        provider: str,
        api: ItemSearchOperation,
        request_fingerprint: str,
        body: bytes,
        body_sha256: str,
        received_at: datetime,
        http_status: int,
        request_id: str,
        rate: RateLimitMetadata,
    ) -> None:
        if provider != "RAKUTEN_ICHIBA" or type(provider) is not str:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        if api is not ItemSearchOperation.ITEM_SEARCH:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        request_digest = _sha256(request_fingerprint)
        if type(body) is not bytes or not 2 <= len(body) <= _MAX_BODY_BYTES:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        observed_digest = hashlib.sha256(body).hexdigest()
        if _sha256(body_sha256) != observed_digest:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        try:
            decoded = body.decode("utf-8", errors="strict")
            parsed = json.loads(
                decoded,
                object_pairs_hook=_pairs,
                parse_constant=_reject_constant,
            )
        except UnicodeError, json.JSONDecodeError:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        if type(parsed) is not dict:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        _validate_json_tree(parsed)
        _utc(received_at)
        _exact_int(http_status, minimum=100, maximum=599)
        if type(request_id) is not str or _SAFE_TOKEN.fullmatch(request_id) is None:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        if type(rate) is not RateLimitMetadata:
            fail_item_search(RakutenItemSearchFailureCode.RAW_RESPONSE_INVALID)
        object.__setattr__(self, "_provider", provider)
        object.__setattr__(self, "_api", api)
        object.__setattr__(self, "_request_fingerprint", request_digest)
        object.__setattr__(self, "_body", body)
        object.__setattr__(self, "_body_sha256", observed_digest)
        object.__setattr__(self, "_received_at", received_at)
        object.__setattr__(self, "_http_status", http_status)
        object.__setattr__(self, "_request_id", request_id)
        object.__setattr__(self, "_rate", rate)
        object.__setattr__(self, "_sealed", True)

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def api(self) -> ItemSearchOperation:
        return self._api

    @property
    def request_fingerprint(self) -> str:
        return self._request_fingerprint

    @property
    def body_sha256(self) -> str:
        return self._body_sha256

    @property
    def body_size(self) -> int:
        return len(self._body)

    @property
    def received_at(self) -> datetime:
        return self._received_at

    @property
    def http_status(self) -> int:
        return self._http_status

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def rate(self) -> RateLimitMetadata:
        return self._rate

    def _recorded_body(self) -> bytes:
        return self._body

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("RawItemSearchResponse is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("RawItemSearchResponse is immutable")


@dataclass(frozen=True, slots=True, repr=False)
class RawResponseReceipt(_RedactedValue):
    artifact_id: UUID
    sha256: str
    byte_size: int
    content_type: str
    uri: None
    storage_status: StorageExecutionStatus

    def __post_init__(self) -> None:
        if type(self.artifact_id) is not UUID or self.artifact_id.int == 0:
            fail_item_search()
        _sha256(self.sha256)
        _exact_int(self.byte_size, minimum=2, maximum=_MAX_BODY_BYTES)
        if (
            type(self.content_type) is not str
            or self.content_type != "application/json"
            or self.uri is not None
            or self.storage_status is not StorageExecutionStatus.NOT_EXECUTED
        ):
            fail_item_search()


def _https_url(value: object, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    text = _bounded_text(value, maximum=2048)
    if not text.startswith("https://") or "@" in text.partition("/")[2] or "#" in text:
        fail_item_search()
    return text


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalItemSearchItem(_RedactedValue):
    provider: str
    api_version: str
    request_sha256: str
    raw_sha256: str
    item_code: str
    item_name: str
    catchcopy: str | None
    item_caption: str | None
    item_price_jpy: int
    item_url: str
    affiliate_url: str | None
    shop_code: str
    shop_name: str | None
    genre_id: int | None
    availability: bool
    review_count: int | None
    review_average: float | None
    affiliate_rate: float | None
    postage_included: bool | None
    image_urls: tuple[str, ...]
    provider_updated_at: datetime | None
    observed_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.provider) is not str
            or self.provider != "RAKUTEN_ICHIBA"
            or type(self.api_version) is not str
            or self.api_version != "2026-07-01"
        ):
            fail_item_search()
        _sha256(self.request_sha256)
        _sha256(self.raw_sha256)
        _bounded_text(self.item_code, maximum=256)
        if ":" not in self.item_code:
            fail_item_search()
        _bounded_text(self.item_name, maximum=1000)
        if self.catchcopy is not None:
            _bounded_text(self.catchcopy, maximum=2000)
        if self.item_caption is not None:
            _bounded_text(self.item_caption, maximum=10_000)
        _exact_int(self.item_price_jpy, minimum=0, maximum=999_999_999)
        _https_url(self.item_url)
        _https_url(self.affiliate_url, optional=True)
        _bounded_text(self.shop_code, maximum=128)
        if self.shop_name is not None:
            _bounded_text(self.shop_name, maximum=500)
        if self.genre_id is not None:
            _exact_int(self.genre_id, minimum=0, maximum=(1 << 63) - 1)
        if type(self.availability) is not bool:
            fail_item_search()
        if self.review_count is not None:
            _exact_int(self.review_count, minimum=0, maximum=(1 << 63) - 1)
        if self.review_average is not None and (
            type(self.review_average) is not float
            or not math.isfinite(self.review_average)
            or not 0.0 <= self.review_average <= 5.0
        ):
            fail_item_search()
        if self.affiliate_rate is not None and (
            type(self.affiliate_rate) is not float
            or not math.isfinite(self.affiliate_rate)
            or self.affiliate_rate < 0.0
        ):
            fail_item_search()
        if (
            self.postage_included is not None
            and type(self.postage_included) is not bool
        ):
            fail_item_search()
        if type(self.image_urls) is not tuple or len(set(self.image_urls)) != len(
            self.image_urls
        ):
            fail_item_search()
        for image_url in self.image_urls:
            _https_url(image_url)
        if self.provider_updated_at is not None:
            _utc(self.provider_updated_at)
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalItemSearchPage(_RedactedValue):
    provider: str
    api_version: str
    request_sha256: str
    raw_artifact: RawResponseReceipt
    observed_at: datetime
    count: int
    page: int
    hits: int
    page_count: int
    items: tuple[CanonicalItemSearchItem, ...]
    warnings: tuple[str, ...]
    provider_rate_limit: RateLimitMetadata

    def __post_init__(self) -> None:
        if (
            type(self.provider) is not str
            or self.provider != "RAKUTEN_ICHIBA"
            or type(self.api_version) is not str
            or self.api_version != "2026-07-01"
            or type(self.raw_artifact) is not RawResponseReceipt
            or type(self.provider_rate_limit) is not RateLimitMetadata
        ):
            fail_item_search()
        _sha256(self.request_sha256)
        _utc(self.observed_at)
        _exact_int(self.count, minimum=0, maximum=(1 << 63) - 1)
        if type(self.page) is not int or self.page != 1:
            fail_item_search()
        _exact_int(self.hits, minimum=0, maximum=30)
        _exact_int(self.page_count, minimum=0, maximum=100)
        if (
            type(self.items) is not tuple
            or len(self.items) > self.hits
            or len(self.items) > 30
            or any(type(item) is not CanonicalItemSearchItem for item in self.items)
            or len({item.item_code for item in self.items}) != len(self.items)
            or self.count < len(self.items)
            or (self.count == 0) != (self.page_count == 0)
            or type(self.warnings) is not tuple
            or len(set(self.warnings)) != len(self.warnings)
        ):
            fail_item_search()
        for warning in self.warnings:
            _bounded_text(warning, maximum=500)
        for item in self.items:
            if (
                item.provider != self.provider
                or item.api_version != self.api_version
                or item.request_sha256 != self.request_sha256
                or item.raw_sha256 != self.raw_artifact.sha256
                or item.observed_at != self.observed_at
            ):
                fail_item_search()


@dataclass(frozen=True, slots=True, repr=False)
class RakutenItemSearchResult(_RedactedValue):
    provider_mode: ProviderMode
    page: CanonicalItemSearchPage
    rate: RateLimitMetadata
    storage_status: StorageExecutionStatus
    persistence_status: PersistenceExecutionStatus
    live_eligible: bool

    def __post_init__(self) -> None:
        if (
            self.provider_mode is not ProviderMode.RECORDED_TEST_ONLY
            or type(self.page) is not CanonicalItemSearchPage
            or type(self.rate) is not RateLimitMetadata
            or self.storage_status is not StorageExecutionStatus.NOT_EXECUTED
            or self.persistence_status is not PersistenceExecutionStatus.NOT_EXECUTED
            or self.live_eligible is not False
        ):
            fail_item_search()


__all__ = [
    "CANONICAL_ITEM_SEARCH_ELEMENTS",
    "CanonicalItemSearchItem",
    "CanonicalItemSearchPage",
    "ItemSearchElement",
    "ItemSearchOperation",
    "ItemSearchPurpose",
    "ItemSearchSort",
    "ProviderCapabilities",
    "ProviderFailure",
    "ProviderFailureClass",
    "ProviderHealth",
    "ProviderHealthStatus",
    "ProviderMode",
    "PersistenceExecutionStatus",
    "RakutenItemSearchCommand",
    "RakutenItemSearchFailure",
    "RakutenItemSearchFailureCode",
    "RakutenItemSearchRequest",
    "RakutenItemSearchResult",
    "RateLimitMetadata",
    "RawItemSearchResponse",
    "RawResponseReceipt",
    "StorageExecutionStatus",
    "fail_item_search",
]
