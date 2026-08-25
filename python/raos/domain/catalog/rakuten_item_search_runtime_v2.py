"""Maximum-safe local Rakuten Item Search ingestion values for ST-0502.

This module is provider-action free.  It binds the current official
2026-07-01 wire vocabulary to a deterministic request template, treats every
provider string as untrusted data, and models one bounded ingestion step.  It
contains no credential value, HTTP client, filesystem, database, clock, loop,
sleep, worker, publication, or recommendation implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, NoReturn, SupportsIndex, cast
import unicodedata
from urllib.parse import quote, urlsplit
from uuid import UUID


OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL = (
    "https://webservice.rakuten.co.jp/index.php/documentation/ichiba-item-search"
)
OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256 = (
    "063d5a861f2f8677efca7e772256a980a45eb931bcba403f287025847e42e4cb"
)
ITEM_SEARCH_API_VERSION = "2026-07-01"
ITEM_SEARCH_FORMAT_VERSION = 2
ITEM_SEARCH_ORIGIN = "https://openapi.rakuten.co.jp"
ITEM_SEARCH_ENDPOINT_PATH = "/ichibams/api/IchibaItem/Search/20260701"
MAX_RAW_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_SHOP_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z", re.ASCII)
_LOGICAL_KEY = re.compile(r"sha256/[0-9a-f]{2}/[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-rakuten-item-search-runtime-v2>"


class ItemSearchRuntimeFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RAW_RESPONSE_INVALID = "RAW_RESPONSE_INVALID"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"
    STATE_CONFLICT = "STATE_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    ARCHIVE_INTEGRITY = "ARCHIVE_INTEGRITY"
    ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"
    UNSAFE_PATH = "UNSAFE_PATH"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class ProviderModeV2(str, Enum):
    RECORDED_SYNTHETIC = "RECORDED_SYNTHETIC"
    DISABLED = "DISABLED"


class SecretTransportV2(str, Enum):
    QUERY_SECRET_NAME_ONLY = "QUERY_SECRET_NAME_ONLY"
    HEADER_SECRET_NAME_ONLY = "HEADER_SECRET_NAME_ONLY"


class ProviderTextTrustV2(str, Enum):
    UNTRUSTED_DATA = "UNTRUSTED_DATA"


class ItemSearchSortV2(str, Enum):
    STANDARD = "standard"
    PRICE_ASCENDING = "+itemPrice"
    PRICE_DESCENDING = "-itemPrice"
    UPDATED_ASCENDING = "+updateTimestamp"
    UPDATED_DESCENDING = "-updateTimestamp"


class ItemSearchElementV2(str, Enum):
    AFFILIATE_URL = "affiliateUrl"
    AVAILABILITY = "availability"
    CATCHCOPY = "catchcopy"
    COUNT = "count"
    FIRST = "first"
    GENRE_ID = "genreId"
    HITS = "hits"
    ITEM_CAPTION = "itemCaption"
    ITEM_CODE = "itemCode"
    ITEM_NAME = "itemName"
    ITEM_PRICE = "itemPrice"
    ITEM_URL = "itemUrl"
    LAST = "last"
    MEDIUM_IMAGE_URLS = "mediumImageUrls"
    PAGE = "page"
    PAGE_COUNT = "pageCount"
    POSTAGE_FLAG = "postageFlag"
    SHOP_CODE = "shopCode"
    SHOP_NAME = "shopName"
    SMALL_IMAGE_URLS = "smallImageUrls"


SAFE_ITEM_SEARCH_ELEMENTS_V2: tuple[ItemSearchElementV2, ...] = tuple(
    sorted(ItemSearchElementV2, key=lambda value: value.value)
)

SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2: tuple[str, ...] = tuple(
    sorted(
        {
            "appointDeliveryDateFlag",
            "attributeFlag",
            "availability",
            "elements",
            "format",
            "formatVersion",
            "genreId",
            "genreInformationFlag",
            "hits",
            "itemCode",
            "keyword",
            "maxPrice",
            "minPrice",
            "orFlag",
            "page",
            "postageFlag",
            "shopCode",
            "sort",
        }
    )
)

FORBIDDEN_RECOMMENDATION_INPUTS_V2: tuple[str, ...] = (
    "affiliateRate",
    "commission",
    "EPC",
    "profit",
    "reviewAverage",
    "reviewCount",
    "RPM",
)


class ProviderObservationKindV2(str, Enum):
    SUCCESS = "SUCCESS"
    HTTP_FAILURE = "HTTP_FAILURE"
    DISABLED = "DISABLED"


class ProviderFailureClassV2(str, Enum):
    AUTH = "AUTH"
    CONTRACT = "CONTRACT"
    INTEGRITY = "INTEGRITY"
    PERMANENT = "PERMANENT"
    RATE_LIMITED = "RATE_LIMITED"
    TRANSIENT = "TRANSIENT"
    UNAVAILABLE = "UNAVAILABLE"


class IngestionSessionStateV2(str, Enum):
    READY = "READY"
    RETRY_WAIT = "RETRY_WAIT"
    RATE_LIMITED = "RATE_LIMITED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    COMPLETED = "COMPLETED"
    COMPLETED_BOUNDED = "COMPLETED_BOUNDED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class IngestionStepOutcomeV2(str, Enum):
    PAGE_ARCHIVED = "PAGE_ARCHIVED"
    COMPLETED = "COMPLETED"
    COMPLETED_BOUNDED = "COMPLETED_BOUNDED"
    WAIT_RETRY = "WAIT_RETRY"
    WAIT_RATE_LIMIT = "WAIT_RATE_LIMIT"
    WAIT_CIRCUIT = "WAIT_CIRCUIT"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class CommitRecoveryOutcomeV2(str, Enum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Item Search runtime serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchRuntimeFailure(RuntimeError):
    code: ItemSearchRuntimeFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not ItemSearchRuntimeFailureCode:
            raise TypeError("invalid Item Search runtime failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ItemSearchRuntimeFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Item Search runtime failure serialization is not supported")


def fail_item_search_runtime(
    code: ItemSearchRuntimeFailureCode = ItemSearchRuntimeFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ItemSearchRuntimeFailure(code) from None


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_item_search_runtime()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_item_search_runtime()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_item_search_runtime()
    return value


def _text(value: object, *, maximum_bytes: int, optional: bool = False) -> str | None:
    if optional and (value is None or (type(value) is str and value == "")):
        return None
    if type(value) is not str or value != value.strip() or not value:
        fail_item_search_runtime()
    if any(
        ord(character) == 127
        or unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        fail_item_search_runtime()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_item_search_runtime()
    if len(encoded) > maximum_bytes:
        fail_item_search_runtime()
    return value


def _safe_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_item_search_runtime()
    return value


def _safe_url(value: object, *, optional: bool = False) -> str | None:
    text = _text(value, maximum_bytes=2048, optional=optional)
    if text is None:
        return None
    if "\\" in text or any(character.isspace() for character in text):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    return text


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        fail_item_search_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class SecretNameBindingV2(_RedactedValue):
    provider_name: str
    secret_name: str
    transport: SecretTransportV2
    required: bool

    def __post_init__(self) -> None:
        expected = {
            "applicationId": (
                "rakuten_web_service_application_id",
                SecretTransportV2.QUERY_SECRET_NAME_ONLY,
                True,
            ),
            "accessKey": (
                "rakuten_web_service_access_key",
                SecretTransportV2.HEADER_SECRET_NAME_ONLY,
                True,
            ),
            "affiliateId": (
                "rakuten_affiliate_id",
                SecretTransportV2.QUERY_SECRET_NAME_ONLY,
                False,
            ),
        }.get(self.provider_name)
        if (
            expected is None
            or (self.secret_name, self.transport, self.required) != expected
        ):
            fail_item_search_runtime()


ITEM_SEARCH_SECRET_NAME_BINDINGS_V2: tuple[SecretNameBindingV2, ...] = (
    SecretNameBindingV2(
        provider_name="accessKey",
        secret_name="rakuten_web_service_access_key",
        transport=SecretTransportV2.HEADER_SECRET_NAME_ONLY,
        required=True,
    ),
    SecretNameBindingV2(
        provider_name="affiliateId",
        secret_name="rakuten_affiliate_id",
        transport=SecretTransportV2.QUERY_SECRET_NAME_ONLY,
        required=False,
    ),
    SecretNameBindingV2(
        provider_name="applicationId",
        secret_name="rakuten_web_service_application_id",
        transport=SecretTransportV2.QUERY_SECRET_NAME_ONLY,
        required=True,
    ),
)


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchPlanV2(_RedactedValue):
    keyword: str | None
    shop_code: str | None
    item_code: str | None
    genre_id: int | None
    hits: int
    sort: ItemSearchSortV2
    min_price_jpy: int | None
    max_price_jpy: int | None
    or_flag: bool
    availability: bool
    postage_included_only: bool
    appoint_delivery_date_only: bool
    attribute_flag: bool
    genre_information_flag: bool
    max_pages: int
    retry_delays_seconds: tuple[int, ...]
    circuit_failure_threshold: int
    circuit_cooldown_seconds: int

    def __post_init__(self) -> None:
        selectors = (self.keyword, self.shop_code, self.item_code, self.genre_id)
        if all(value is None for value in selectors):
            fail_item_search_runtime()
        if self.keyword is not None:
            keyword = cast(str, _text(self.keyword, maximum_bytes=128))
            terms = keyword.split(" ")
            if any(not term or len(term) < 2 for term in terms):
                fail_item_search_runtime()
        if self.shop_code is not None:
            shop = cast(str, _text(self.shop_code, maximum_bytes=128))
            if _SHOP_CODE.fullmatch(shop) is None:
                fail_item_search_runtime()
        if self.item_code is not None:
            item = cast(str, _text(self.item_code, maximum_bytes=256))
            before, separator, after = item.partition(":")
            if (
                not separator
                or not before
                or not after
                or _SHOP_CODE.fullmatch(before) is None
            ):
                fail_item_search_runtime()
        if self.genre_id is not None:
            _exact_int(self.genre_id, minimum=0, maximum=(1 << 63) - 1)
        _exact_int(self.hits, minimum=1, maximum=30)
        if type(self.sort) is not ItemSearchSortV2:
            fail_item_search_runtime()
        if self.min_price_jpy is not None:
            _exact_int(self.min_price_jpy, minimum=1, maximum=999_999_998)
        if self.max_price_jpy is not None:
            _exact_int(self.max_price_jpy, minimum=1, maximum=999_999_998)
        if (
            self.min_price_jpy is not None
            and self.max_price_jpy is not None
            and self.min_price_jpy >= self.max_price_jpy
        ):
            fail_item_search_runtime()
        for flag in (
            self.or_flag,
            self.availability,
            self.postage_included_only,
            self.appoint_delivery_date_only,
            self.attribute_flag,
            self.genre_information_flag,
        ):
            if type(flag) is not bool:
                fail_item_search_runtime()
        if self.or_flag and self.keyword is None:
            fail_item_search_runtime()
        if self.attribute_flag and (self.genre_id is None or self.genre_id == 0):
            fail_item_search_runtime()
        _exact_int(self.max_pages, minimum=1, maximum=100)
        if (
            type(self.retry_delays_seconds) is not tuple
            or not self.retry_delays_seconds
            or len(self.retry_delays_seconds) > 10
            or any(
                type(delay) is not int or not 0 <= delay <= 3600
                for delay in self.retry_delays_seconds
            )
        ):
            fail_item_search_runtime()
        _exact_int(
            self.circuit_failure_threshold,
            minimum=1,
            maximum=len(self.retry_delays_seconds) + 1,
        )
        _exact_int(self.circuit_cooldown_seconds, minimum=1, maximum=86_400)

    @property
    def canonical_mapping(self) -> dict[str, object]:
        mapping: dict[str, object] = {
            "appoint_delivery_date_only": self.appoint_delivery_date_only,
            "attribute_flag": self.attribute_flag,
            "availability": self.availability,
            "circuit_cooldown_seconds": self.circuit_cooldown_seconds,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "elements": [value.value for value in SAFE_ITEM_SEARCH_ELEMENTS_V2],
            "format_version": ITEM_SEARCH_FORMAT_VERSION,
            "genre_information_flag": self.genre_information_flag,
            "hits": self.hits,
            "max_pages": self.max_pages,
            "or_flag": self.or_flag,
            "postage_included_only": self.postage_included_only,
            "retry_delays_seconds": list(self.retry_delays_seconds),
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
        mapping.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return dict(sorted(mapping.items()))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_json_bytes(self.canonical_mapping)).hexdigest()


def _wire_pairs(plan: ItemSearchPlanV2, *, page: int) -> tuple[tuple[str, str], ...]:
    if type(plan) is not ItemSearchPlanV2:
        fail_item_search_runtime()
    _exact_int(page, minimum=1, maximum=100)
    parameters: dict[str, str] = {
        "appointDeliveryDateFlag": "1" if plan.appoint_delivery_date_only else "0",
        "attributeFlag": "1" if plan.attribute_flag else "0",
        "availability": "1" if plan.availability else "0",
        "elements": ",".join(value.value for value in SAFE_ITEM_SEARCH_ELEMENTS_V2),
        "format": "json",
        "formatVersion": str(ITEM_SEARCH_FORMAT_VERSION),
        "genreInformationFlag": "1" if plan.genre_information_flag else "0",
        "hits": str(plan.hits),
        "orFlag": "1" if plan.or_flag else "0",
        "page": str(page),
        "postageFlag": "1" if plan.postage_included_only else "0",
        "sort": plan.sort.value,
    }
    optional: dict[str, object | None] = {
        "genreId": plan.genre_id,
        "itemCode": plan.item_code,
        "keyword": plan.keyword,
        "maxPrice": plan.max_price_jpy,
        "minPrice": plan.min_price_jpy,
        "shopCode": plan.shop_code,
    }
    parameters.update(
        {key: str(value) for key, value in optional.items() if value is not None}
    )
    if not set(parameters).issubset(SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
    return tuple(sorted(parameters.items()))


def _percent_encode(value: str) -> str:
    try:
        return quote(value, safe="-._~", encoding="utf-8", errors="strict")
    except UnicodeError:
        fail_item_search_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchWireRequestV2(_RedactedValue):
    plan_fingerprint: str
    page: int
    origin: str
    endpoint_path: str
    parameter_pairs: tuple[tuple[str, str], ...]
    canonical_query: bytes
    request_fingerprint: str
    secret_name_bindings: tuple[SecretNameBindingV2, ...]

    def __post_init__(self) -> None:
        _sha256(self.plan_fingerprint)
        _exact_int(self.page, minimum=1, maximum=100)
        if (
            self.origin != ITEM_SEARCH_ORIGIN
            or self.endpoint_path != ITEM_SEARCH_ENDPOINT_PATH
        ):
            fail_item_search_runtime()
        if (
            type(self.parameter_pairs) is not tuple
            or not self.parameter_pairs
            or any(
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not str
                or type(pair[1]) is not str
                or not pair[0]
                or not pair[1]
                for pair in self.parameter_pairs
            )
            or tuple(sorted(self.parameter_pairs)) != self.parameter_pairs
            or len({key for key, _value in self.parameter_pairs})
            != len(self.parameter_pairs)
            or not {key for key, _value in self.parameter_pairs}.issubset(
                SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2
            )
            or type(self.canonical_query) is not bytes
        ):
            fail_item_search_runtime()
        expected_query = "&".join(
            f"{_percent_encode(key)}={_percent_encode(value)}"
            for key, value in self.parameter_pairs
        ).encode("ascii")
        if self.canonical_query != expected_query:
            fail_item_search_runtime()
        if any(
            binding.provider_name.encode("ascii") in self.canonical_query
            for binding in ITEM_SEARCH_SECRET_NAME_BINDINGS_V2
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        if self.secret_name_bindings != ITEM_SEARCH_SECRET_NAME_BINDINGS_V2:
            fail_item_search_runtime()
        expected = hashlib.sha256(
            b"RAKUTEN_ITEM_SEARCH_V2\0"
            + self.origin.encode("ascii")
            + b"\0"
            + self.endpoint_path.encode("ascii")
            + b"?"
            + self.canonical_query
            + b"\0"
            + self.plan_fingerprint.encode("ascii")
        ).hexdigest()
        if _sha256(self.request_fingerprint) != expected:
            fail_item_search_runtime()

    @classmethod
    def from_plan(cls, plan: ItemSearchPlanV2, *, page: int) -> ItemSearchWireRequestV2:
        pairs = _wire_pairs(plan, page=page)
        query = "&".join(
            f"{_percent_encode(key)}={_percent_encode(value)}" for key, value in pairs
        ).encode("ascii")
        fingerprint = hashlib.sha256(
            b"RAKUTEN_ITEM_SEARCH_V2\0"
            + ITEM_SEARCH_ORIGIN.encode("ascii")
            + b"\0"
            + ITEM_SEARCH_ENDPOINT_PATH.encode("ascii")
            + b"?"
            + query
            + b"\0"
            + plan.fingerprint.encode("ascii")
        ).hexdigest()
        return cls(
            plan_fingerprint=plan.fingerprint,
            page=page,
            origin=ITEM_SEARCH_ORIGIN,
            endpoint_path=ITEM_SEARCH_ENDPOINT_PATH,
            parameter_pairs=pairs,
            canonical_query=query,
            request_fingerprint=fingerprint,
            secret_name_bindings=ITEM_SEARCH_SECRET_NAME_BINDINGS_V2,
        )

    @property
    def query_parameter_names(self) -> tuple[str, ...]:
        return tuple(key for key, _value in self.parameter_pairs)

    @property
    def provider_derived_recommendation_inputs(self) -> tuple[()]:
        return ()


@dataclass(frozen=True, slots=True, repr=False)
class RateLimitObservationV2(_RedactedValue):
    limit: int | None
    remaining: int | None
    reset_at: datetime | None

    def __post_init__(self) -> None:
        if self.limit is None or self.remaining is None or self.reset_at is None:
            if any(
                value is not None
                for value in (self.limit, self.remaining, self.reset_at)
            ):
                fail_item_search_runtime()
            return
        _exact_int(self.limit, minimum=1, maximum=1_000_000)
        _exact_int(self.remaining, minimum=0, maximum=self.limit)
        _utc(self.reset_at)

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0 if self.remaining is not None else False


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchProviderObservationV2(_RedactedValue):
    kind: ProviderObservationKindV2
    mode: ProviderModeV2
    request_fingerprint: str
    observed_at: datetime
    http_status: int | None
    request_id: str
    raw_body: bytes | None
    raw_sha256: str | None
    rate: RateLimitObservationV2
    retry_after_at: datetime | None
    failure_class: ProviderFailureClassV2 | None
    external_actions: int

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not ProviderObservationKindV2
            or type(self.mode) is not ProviderModeV2
        ):
            fail_item_search_runtime()
        _sha256(self.request_fingerprint)
        _utc(self.observed_at)
        if (
            type(self.request_id) is not str
            or _SAFE_TOKEN.fullmatch(self.request_id) is None
        ):
            fail_item_search_runtime()
        if (
            type(self.rate) is not RateLimitObservationV2
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_item_search_runtime()
        if self.retry_after_at is not None:
            _utc(self.retry_after_at)
        if self.kind is ProviderObservationKindV2.SUCCESS:
            if (
                self.mode is not ProviderModeV2.RECORDED_SYNTHETIC
                or self.http_status != 200
                or type(self.raw_body) is not bytes
                or not 2 <= len(self.raw_body) <= MAX_RAW_RESPONSE_BYTES
                or hashlib.sha256(self.raw_body).hexdigest() != _sha256(self.raw_sha256)
                or self.failure_class is not None
                or self.retry_after_at is not None
            ):
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID
                )
            return
        if self.raw_body is not None or self.raw_sha256 is not None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
        if self.kind is ProviderObservationKindV2.DISABLED:
            if (
                self.mode is not ProviderModeV2.DISABLED
                or self.http_status is not None
                or self.failure_class is not ProviderFailureClassV2.UNAVAILABLE
                or self.retry_after_at is not None
            ):
                fail_item_search_runtime()
            return
        expected = classify_item_search_http_status(self.http_status)
        if (
            self.mode is not ProviderModeV2.RECORDED_SYNTHETIC
            or self.failure_class is not expected
        ):
            fail_item_search_runtime()
        if self.failure_class is ProviderFailureClassV2.RATE_LIMITED:
            if self.retry_after_at is None or self.retry_after_at <= self.observed_at:
                fail_item_search_runtime()
        elif self.retry_after_at is not None:
            fail_item_search_runtime()


def classify_item_search_http_status(status: object) -> ProviderFailureClassV2:
    if type(status) is not int:
        fail_item_search_runtime()
    mapping = {
        400: ProviderFailureClassV2.PERMANENT,
        401: ProviderFailureClassV2.AUTH,
        403: ProviderFailureClassV2.AUTH,
        404: ProviderFailureClassV2.PERMANENT,
        429: ProviderFailureClassV2.RATE_LIMITED,
        500: ProviderFailureClassV2.TRANSIENT,
        503: ProviderFailureClassV2.TRANSIENT,
    }
    result = mapping.get(status)
    if result is None:
        fail_item_search_runtime()
    return result


def _reject_constant(_value: str) -> NoReturn:
    fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID
                )
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1)
                for item in cast(dict[object, object], current).values()
            )
            continue
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class UntrustedProviderTextV2(_RedactedValue):
    value: str
    trust: ProviderTextTrustV2

    def __post_init__(self) -> None:
        _text(self.value, maximum_bytes=10_000)
        if self.trust is not ProviderTextTrustV2.UNTRUSTED_DATA:
            fail_item_search_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class ParsedItemSearchItemV2(_RedactedValue):
    item_code: UntrustedProviderTextV2
    item_name: UntrustedProviderTextV2
    catchcopy: UntrustedProviderTextV2 | None
    item_caption: UntrustedProviderTextV2 | None
    item_price_jpy: int
    item_url: str
    affiliate_url: str | None
    shop_code: UntrustedProviderTextV2
    shop_name: UntrustedProviderTextV2 | None
    genre_id: int
    availability: bool
    postage_included: bool
    image_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.item_code) is not UntrustedProviderTextV2
            or type(self.item_name) is not UntrustedProviderTextV2
        ):
            fail_item_search_runtime()
        if (
            self.catchcopy is not None
            and type(self.catchcopy) is not UntrustedProviderTextV2
        ):
            fail_item_search_runtime()
        if (
            self.item_caption is not None
            and type(self.item_caption) is not UntrustedProviderTextV2
        ):
            fail_item_search_runtime()
        _exact_int(self.item_price_jpy, minimum=0, maximum=999_999_999)
        _safe_url(self.item_url)
        _safe_url(self.affiliate_url, optional=True)
        if type(self.shop_code) is not UntrustedProviderTextV2:
            fail_item_search_runtime()
        if (
            self.shop_name is not None
            and type(self.shop_name) is not UntrustedProviderTextV2
        ):
            fail_item_search_runtime()
        _exact_int(self.genre_id, minimum=0, maximum=(1 << 63) - 1)
        if (
            type(self.availability) is not bool
            or type(self.postage_included) is not bool
        ):
            fail_item_search_runtime()
        if (
            type(self.image_urls) is not tuple
            or len(self.image_urls) > 6
            or len(self.image_urls) != len(set(self.image_urls))
        ):
            fail_item_search_runtime()
        for url in self.image_urls:
            _safe_url(url)

    @property
    def identity_fingerprint(self) -> str:
        return hashlib.sha256(self.item_code.value.encode("utf-8")).hexdigest()

    @property
    def provider_derived_recommendation_inputs(self) -> tuple[()]:
        return ()


@dataclass(frozen=True, slots=True, repr=False)
class ParsedItemSearchPageV2(_RedactedValue):
    request_fingerprint: str
    raw_sha256: str
    observed_at: datetime
    page: int
    page_count: int
    count: int
    hits: int
    first: int
    last: int
    items: tuple[ParsedItemSearchItemV2, ...]
    rate: RateLimitObservationV2

    def __post_init__(self) -> None:
        _sha256(self.request_fingerprint)
        _sha256(self.raw_sha256)
        _utc(self.observed_at)
        _exact_int(self.page, minimum=1, maximum=100)
        _exact_int(self.page_count, minimum=0, maximum=100)
        _exact_int(self.count, minimum=0, maximum=(1 << 63) - 1)
        _exact_int(self.hits, minimum=1, maximum=30)
        _exact_int(self.first, minimum=0, maximum=(1 << 63) - 1)
        _exact_int(self.last, minimum=0, maximum=(1 << 63) - 1)
        if (
            type(self.items) is not tuple
            or len(self.items) > self.hits
            or any(type(item) is not ParsedItemSearchItemV2 for item in self.items)
            or len({item.item_code.value for item in self.items}) != len(self.items)
            or type(self.rate) is not RateLimitObservationV2
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)


def _exact_keys(value: object, expected: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    mapping = cast(dict[object, object], value)
    if not all(type(key) is str for key in mapping):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    result = {cast(str, key): item for key, item in mapping.items()}
    if frozenset(result) != expected:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    return result


def _json_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    return value


def _provider_text(
    value: object, *, optional: bool = False
) -> UntrustedProviderTextV2 | None:
    text = _text(value, maximum_bytes=10_000, optional=optional)
    if text is None:
        return None
    return UntrustedProviderTextV2(
        value=text,
        trust=ProviderTextTrustV2.UNTRUSTED_DATA,
    )


def parse_item_search_page_v2(
    *,
    request: ItemSearchWireRequestV2,
    observation: ItemSearchProviderObservationV2,
) -> ParsedItemSearchPageV2:
    if (
        type(request) is not ItemSearchWireRequestV2
        or type(observation) is not ItemSearchProviderObservationV2
        or observation.kind is not ProviderObservationKindV2.SUCCESS
        or observation.request_fingerprint != request.request_fingerprint
        or observation.raw_body is None
        or observation.raw_sha256 is None
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    try:
        decoded = observation.raw_body.decode("utf-8", errors="strict")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeError, json.JSONDecodeError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    _validate_json_tree(parsed)
    root = _exact_keys(
        parsed,
        frozenset({"count", "first", "hits", "items", "last", "page", "pageCount"}),
    )
    page = _json_int(root["page"], minimum=1, maximum=100)
    page_count = _json_int(root["pageCount"], minimum=0, maximum=100)
    count = _json_int(root["count"], minimum=0, maximum=(1 << 63) - 1)
    hits = _json_int(root["hits"], minimum=1, maximum=30)
    first = _json_int(root["first"], minimum=0, maximum=(1 << 63) - 1)
    last = _json_int(root["last"], minimum=0, maximum=(1 << 63) - 1)
    if page != request.page or hits != int(dict(request.parameter_pairs)["hits"]):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
    raw_items = root["items"]
    if type(raw_items) is not list:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    item_keys = frozenset(
        {
            "affiliateUrl",
            "availability",
            "catchcopy",
            "genreId",
            "itemCaption",
            "itemCode",
            "itemName",
            "itemPrice",
            "itemUrl",
            "mediumImageUrls",
            "postageFlag",
            "shopCode",
            "shopName",
            "smallImageUrls",
        }
    )
    items: list[ParsedItemSearchItemV2] = []
    for value in cast(list[object], raw_items):
        item = _exact_keys(value, item_keys)
        medium = item["mediumImageUrls"]
        small = item["smallImageUrls"]
        if type(medium) is not list or type(small) is not list:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
        image_urls = tuple(
            cast(str, _safe_url(candidate))
            for candidate in (*cast(list[object], medium), *cast(list[object], small))
        )
        availability = _json_int(item["availability"], minimum=0, maximum=1)
        postage = _json_int(item["postageFlag"], minimum=0, maximum=1)
        items.append(
            ParsedItemSearchItemV2(
                item_code=cast(
                    UntrustedProviderTextV2, _provider_text(item["itemCode"])
                ),
                item_name=cast(
                    UntrustedProviderTextV2, _provider_text(item["itemName"])
                ),
                catchcopy=_provider_text(item["catchcopy"], optional=True),
                item_caption=_provider_text(item["itemCaption"], optional=True),
                item_price_jpy=_json_int(
                    item["itemPrice"], minimum=0, maximum=999_999_999
                ),
                item_url=cast(str, _safe_url(item["itemUrl"])),
                affiliate_url=_safe_url(item["affiliateUrl"], optional=True),
                shop_code=cast(
                    UntrustedProviderTextV2, _provider_text(item["shopCode"])
                ),
                shop_name=_provider_text(item["shopName"], optional=True),
                genre_id=_json_int(item["genreId"], minimum=0, maximum=(1 << 63) - 1),
                availability=availability == 1,
                postage_included=postage == 0,
                image_urls=image_urls,
            )
        )
    if len(items) > hits or count < len(items):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    if not items:
        if any(value != 0 for value in (count, first, last, page_count)):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    else:
        expected_first = (page - 1) * hits + 1
        if (
            page_count < page
            or first != expected_first
            or last != first + len(items) - 1
            or last > count
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.RAW_RESPONSE_INVALID)
    return ParsedItemSearchPageV2(
        request_fingerprint=request.request_fingerprint,
        raw_sha256=observation.raw_sha256,
        observed_at=observation.observed_at,
        page=page,
        page_count=page_count,
        count=count,
        hits=hits,
        first=first,
        last=last,
        items=tuple(items),
        rate=observation.rate,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RawArchiveReceiptV2(_RedactedValue):
    receipt_id: UUID
    artifact_sha256: str
    byte_size: int
    artifact_version: int
    logical_key: str
    request_fingerprint: str
    page: int
    observed_at: datetime

    def __post_init__(self) -> None:
        _safe_uuid(self.receipt_id)
        digest = _sha256(self.artifact_sha256)
        _exact_int(self.byte_size, minimum=2, maximum=MAX_RAW_RESPONSE_BYTES)
        _exact_int(self.artifact_version, minimum=1, maximum=(1 << 63) - 1)
        if (
            type(self.logical_key) is not str
            or _LOGICAL_KEY.fullmatch(self.logical_key) is None
        ):
            fail_item_search_runtime()
        if self.logical_key != f"sha256/{digest[:2]}/{digest}":
            fail_item_search_runtime()
        _sha256(self.request_fingerprint)
        _exact_int(self.page, minimum=1, maximum=100)
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchIngestionSessionV2(_RedactedValue):
    session_id: UUID
    plan: ItemSearchPlanV2
    state: IngestionSessionStateV2
    next_page: int
    completed_pages: int
    current_attempt: int
    consecutive_failures: int
    next_allowed_at: datetime | None
    seen_request_fingerprints: tuple[str, ...]
    seen_response_sha256: tuple[str, ...]
    seen_item_fingerprints: tuple[str, ...]
    last_failure_class: ProviderFailureClassV2 | None
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _safe_uuid(self.session_id)
        if (
            type(self.plan) is not ItemSearchPlanV2
            or type(self.state) is not IngestionSessionStateV2
        ):
            fail_item_search_runtime()
        _exact_int(self.next_page, minimum=1, maximum=100)
        _exact_int(self.completed_pages, minimum=0, maximum=self.plan.max_pages)
        _exact_int(self.current_attempt, minimum=0, maximum=100)
        _exact_int(self.consecutive_failures, minimum=0, maximum=1000)
        if self.next_allowed_at is not None:
            _utc(self.next_allowed_at)
        for values in (
            self.seen_request_fingerprints,
            self.seen_response_sha256,
            self.seen_item_fingerprints,
        ):
            if type(values) is not tuple or len(values) != len(set(values)):
                fail_item_search_runtime()
            for value in values:
                _sha256(value)
        if (
            len(self.seen_request_fingerprints) != self.completed_pages
            or len(self.seen_response_sha256) != self.completed_pages
        ):
            fail_item_search_runtime()
        if (
            self.last_failure_class is not None
            and type(self.last_failure_class) is not ProviderFailureClassV2
        ):
            fail_item_search_runtime()
        _exact_int(self.version, minimum=0, maximum=(1 << 63) - 1)
        _utc(self.created_at)
        _utc(self.updated_at)
        if self.updated_at < self.created_at:
            fail_item_search_runtime()
        waiting = {
            IngestionSessionStateV2.RETRY_WAIT,
            IngestionSessionStateV2.RATE_LIMITED,
            IngestionSessionStateV2.CIRCUIT_OPEN,
        }
        if (self.state in waiting) != (self.next_allowed_at is not None):
            fail_item_search_runtime()
        if (
            self.state is IngestionSessionStateV2.READY
            and self.last_failure_class is not None
        ):
            fail_item_search_runtime()
        terminal = {
            IngestionSessionStateV2.COMPLETED,
            IngestionSessionStateV2.COMPLETED_BOUNDED,
            IngestionSessionStateV2.FAILED,
            IngestionSessionStateV2.QUARANTINED,
        }
        if self.state in terminal and self.next_allowed_at is not None:
            fail_item_search_runtime()

    @classmethod
    def initial(
        cls,
        *,
        session_id: UUID,
        plan: ItemSearchPlanV2,
        created_at: datetime,
    ) -> ItemSearchIngestionSessionV2:
        return cls(
            session_id=session_id,
            plan=plan,
            state=IngestionSessionStateV2.READY,
            next_page=1,
            completed_pages=0,
            current_attempt=0,
            consecutive_failures=0,
            next_allowed_at=None,
            seen_request_fingerprints=(),
            seen_response_sha256=(),
            seen_item_fingerprints=(),
            last_failure_class=None,
            version=0,
            created_at=created_at,
            updated_at=created_at,
        )

    @property
    def terminal(self) -> bool:
        return self.state in {
            IngestionSessionStateV2.COMPLETED,
            IngestionSessionStateV2.COMPLETED_BOUNDED,
            IngestionSessionStateV2.FAILED,
            IngestionSessionStateV2.QUARANTINED,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchStepCommandV2(_RedactedValue):
    operation_id: UUID
    session_id: UUID
    expected_version: int
    observed_at: datetime

    def __post_init__(self) -> None:
        _safe_uuid(self.operation_id)
        _safe_uuid(self.session_id)
        _exact_int(self.expected_version, minimum=0, maximum=(1 << 63) - 1)
        _utc(self.observed_at)

    @property
    def payload_fingerprint(self) -> str:
        return hashlib.sha256(
            _json_bytes(
                {
                    "expected_version": self.expected_version,
                    "observed_at": self.observed_at.isoformat(),
                    "session_id": str(self.session_id),
                }
            )
        ).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class PersistedItemSearchStepV2(_RedactedValue):
    outcome: IngestionStepOutcomeV2
    session: ItemSearchIngestionSessionV2
    request_fingerprint: str | None
    receipt: RawArchiveReceiptV2 | None
    failure_class: ProviderFailureClassV2 | None

    def __post_init__(self) -> None:
        if (
            type(self.outcome) is not IngestionStepOutcomeV2
            or type(self.session) is not ItemSearchIngestionSessionV2
        ):
            fail_item_search_runtime()
        if self.request_fingerprint is not None:
            _sha256(self.request_fingerprint)
        if self.receipt is not None and type(self.receipt) is not RawArchiveReceiptV2:
            fail_item_search_runtime()
        if self.receipt is not None and (
            self.request_fingerprint is None
            or self.receipt.request_fingerprint != self.request_fingerprint
            or self.receipt.observed_at != self.session.updated_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if (
            self.failure_class is not None
            and type(self.failure_class) is not ProviderFailureClassV2
        ):
            fail_item_search_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchStepResultV2(_RedactedValue):
    persisted: PersistedItemSearchStepV2
    page: ParsedItemSearchPageV2 | None
    provider_mode: ProviderModeV2
    external_actions: int

    def __post_init__(self) -> None:
        if type(self.persisted) is not PersistedItemSearchStepV2:
            fail_item_search_runtime()
        if self.page is not None and type(self.page) is not ParsedItemSearchPageV2:
            fail_item_search_runtime()
        if self.page is not None and (
            self.persisted.receipt is None
            or self.persisted.request_fingerprint != self.page.request_fingerprint
            or self.persisted.receipt.artifact_sha256 != self.page.raw_sha256
            or self.persisted.receipt.observed_at != self.page.observed_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if (
            type(self.provider_mode) is not ProviderModeV2
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_item_search_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class ItemSearchCommitRecoveryV2(_RedactedValue):
    outcome: CommitRecoveryOutcomeV2
    persisted: PersistedItemSearchStepV2 | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not CommitRecoveryOutcomeV2:
            fail_item_search_runtime()
        if (self.outcome is CommitRecoveryOutcomeV2.COMMITTED) != (
            self.persisted is not None
        ):
            fail_item_search_runtime()


def success_transition_v2(
    *,
    session: ItemSearchIngestionSessionV2,
    page: ParsedItemSearchPageV2,
    observed_at: datetime,
) -> tuple[ItemSearchIngestionSessionV2, IngestionStepOutcomeV2]:
    if (
        type(session) is not ItemSearchIngestionSessionV2
        or type(page) is not ParsedItemSearchPageV2
    ):
        fail_item_search_runtime()
    now = _utc(observed_at)
    if session.terminal or page.page != session.next_page:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
    item_hashes = tuple(item.identity_fingerprint for item in page.items)
    if (
        page.request_fingerprint in session.seen_request_fingerprints
        or page.raw_sha256 in session.seen_response_sha256
        or set(item_hashes).intersection(session.seen_item_fingerprints)
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
    completed = session.completed_pages + 1
    more_provider_pages = page.page < page.page_count
    bounded = more_provider_pages and completed >= session.plan.max_pages
    if bounded:
        state = IngestionSessionStateV2.COMPLETED_BOUNDED
        outcome = IngestionStepOutcomeV2.COMPLETED_BOUNDED
        allowed_at = None
    elif not more_provider_pages:
        state = IngestionSessionStateV2.COMPLETED
        outcome = IngestionStepOutcomeV2.COMPLETED
        allowed_at = None
    elif page.rate.exhausted:
        if page.rate.reset_at is None or page.rate.reset_at <= now:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONTRACT_DRIFT)
        state = IngestionSessionStateV2.RATE_LIMITED
        outcome = IngestionStepOutcomeV2.WAIT_RATE_LIMIT
        allowed_at = page.rate.reset_at
    else:
        state = IngestionSessionStateV2.READY
        outcome = IngestionStepOutcomeV2.PAGE_ARCHIVED
        allowed_at = None
    return (
        replace(
            session,
            state=state,
            next_page=min(page.page + 1, 100),
            completed_pages=completed,
            current_attempt=0,
            consecutive_failures=0,
            next_allowed_at=allowed_at,
            seen_request_fingerprints=(
                *session.seen_request_fingerprints,
                page.request_fingerprint,
            ),
            seen_response_sha256=(*session.seen_response_sha256, page.raw_sha256),
            seen_item_fingerprints=(*session.seen_item_fingerprints, *item_hashes),
            last_failure_class=None,
            version=session.version + 1,
            updated_at=now,
        ),
        outcome,
    )


def failure_transition_v2(
    *,
    session: ItemSearchIngestionSessionV2,
    failure_class: ProviderFailureClassV2,
    observed_at: datetime,
    retry_after_at: datetime | None,
) -> tuple[ItemSearchIngestionSessionV2, IngestionStepOutcomeV2]:
    if (
        type(session) is not ItemSearchIngestionSessionV2
        or type(failure_class) is not ProviderFailureClassV2
    ):
        fail_item_search_runtime()
    now = _utc(observed_at)
    if session.terminal:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
    attempt = session.current_attempt + 1
    failures = session.consecutive_failures + 1
    if failure_class is ProviderFailureClassV2.RATE_LIMITED:
        if retry_after_at is None or _utc(retry_after_at) <= now:
            state = IngestionSessionStateV2.QUARANTINED
            outcome = IngestionStepOutcomeV2.QUARANTINED
            allowed_at = None
        else:
            state = IngestionSessionStateV2.RATE_LIMITED
            outcome = IngestionStepOutcomeV2.WAIT_RATE_LIMIT
            allowed_at = retry_after_at
    elif failure_class in {
        ProviderFailureClassV2.TRANSIENT,
        ProviderFailureClassV2.UNAVAILABLE,
    }:
        threshold = session.plan.circuit_failure_threshold
        if failures >= threshold or attempt > len(session.plan.retry_delays_seconds):
            state = IngestionSessionStateV2.CIRCUIT_OPEN
            outcome = (
                IngestionStepOutcomeV2.PROVIDER_DISABLED
                if failure_class is ProviderFailureClassV2.UNAVAILABLE
                else IngestionStepOutcomeV2.WAIT_CIRCUIT
            )
            allowed_at = now + timedelta(seconds=session.plan.circuit_cooldown_seconds)
            attempt = 0
        else:
            state = IngestionSessionStateV2.RETRY_WAIT
            outcome = (
                IngestionStepOutcomeV2.PROVIDER_DISABLED
                if failure_class is ProviderFailureClassV2.UNAVAILABLE
                else IngestionStepOutcomeV2.WAIT_RETRY
            )
            allowed_at = now + timedelta(
                seconds=session.plan.retry_delays_seconds[attempt - 1]
            )
    elif failure_class in {
        ProviderFailureClassV2.CONTRACT,
        ProviderFailureClassV2.INTEGRITY,
    }:
        state = IngestionSessionStateV2.QUARANTINED
        outcome = IngestionStepOutcomeV2.QUARANTINED
        allowed_at = None
    else:
        state = IngestionSessionStateV2.FAILED
        outcome = IngestionStepOutcomeV2.FAILED
        allowed_at = None
    return (
        replace(
            session,
            state=state,
            current_attempt=attempt,
            consecutive_failures=failures,
            next_allowed_at=allowed_at,
            last_failure_class=failure_class,
            version=session.version + 1,
            updated_at=now,
        ),
        outcome,
    )


__all__ = [
    "CommitRecoveryOutcomeV2",
    "FORBIDDEN_RECOMMENDATION_INPUTS_V2",
    "ITEM_SEARCH_API_VERSION",
    "ITEM_SEARCH_ENDPOINT_PATH",
    "ITEM_SEARCH_FORMAT_VERSION",
    "ITEM_SEARCH_ORIGIN",
    "ITEM_SEARCH_SECRET_NAME_BINDINGS_V2",
    "IngestionSessionStateV2",
    "IngestionStepOutcomeV2",
    "ItemSearchCommitRecoveryV2",
    "ItemSearchElementV2",
    "ItemSearchIngestionSessionV2",
    "ItemSearchPlanV2",
    "ItemSearchProviderObservationV2",
    "ItemSearchRuntimeFailure",
    "ItemSearchRuntimeFailureCode",
    "ItemSearchSortV2",
    "ItemSearchStepCommandV2",
    "ItemSearchStepResultV2",
    "ItemSearchWireRequestV2",
    "MAX_RAW_RESPONSE_BYTES",
    "OFFICIAL_ITEM_SEARCH_DOCUMENTATION_RAW_SHA256",
    "OFFICIAL_ITEM_SEARCH_DOCUMENTATION_URL",
    "ParsedItemSearchItemV2",
    "ParsedItemSearchPageV2",
    "PersistedItemSearchStepV2",
    "ProviderFailureClassV2",
    "ProviderModeV2",
    "ProviderObservationKindV2",
    "ProviderTextTrustV2",
    "RateLimitObservationV2",
    "RawArchiveReceiptV2",
    "SAFE_ITEM_SEARCH_ELEMENTS_V2",
    "SAFE_PROVIDER_QUERY_PARAMETER_NAMES_V2",
    "SecretNameBindingV2",
    "SecretTransportV2",
    "UntrustedProviderTextV2",
    "classify_item_search_http_status",
    "fail_item_search_runtime",
    "failure_transition_v2",
    "parse_item_search_page_v2",
    "success_transition_v2",
]
