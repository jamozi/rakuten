"""Closed recorded-only Rakuten Product Search values for ST-0502."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import ipaddress
import json
import re
import unicodedata
from typing import NoReturn, SupportsIndex
from urllib.parse import urlsplit


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-rakuten-product-search>"

PRODUCT_SEARCH_ENDPOINT_PATH = "/ichibaproduct/api/Product/Search/20250801"
PRODUCT_SEARCH_FUTURE_SECRET_ALIASES: tuple[tuple[str, str], ...] = (
    ("application_id", "rakuten_web_service_application_id"),
    ("access_key", "rakuten_web_service_access_key"),
    ("affiliate_id", "rakuten_affiliate_id"),
)
PRODUCT_SEARCH_FUTURE_ACCESS_KEY_TRANSPORT = "DEDICATED_HTTP_HEADER_ONLY"


class ProductSelectorKind(str, Enum):
    PRODUCT_ID = "PRODUCT_ID"
    PRODUCT_CODE = "PRODUCT_CODE"


class ProductSearchElement(str, Enum):
    AFFILIATE_URL = "affiliateUrl"
    BRAND_NAME = "brandName"
    COUNT = "count"
    FIRST = "first"
    HITS = "hits"
    LAST = "last"
    MAKER_NAME = "makerName"
    MEDIUM_IMAGE_URL = "mediumImageUrl"
    PAGE = "page"
    PAGE_COUNT = "pageCount"
    PRODUCT_CODE = "productCode"
    PRODUCT_ID = "productId"
    PRODUCT_NAME = "productName"
    PRODUCT_NO = "productNo"
    PRODUCT_URL_PC = "productUrlPC"


PRODUCT_SEARCH_ELEMENTS: tuple[ProductSearchElement, ...] = tuple(
    sorted(ProductSearchElement, key=lambda element: element.value)
)


class ProductSearchProviderMode(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class ProductSearchReceiptPurpose(str, Enum):
    VALIDATION_ONLY = "VALIDATION_ONLY"


class ProductSearchStorageStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ProductSearchPersistenceStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ProductSearchProviderFailureClass(str, Enum):
    PERMANENT = "PERMANENT"
    THROTTLED_RETRYABLE_DECLARATION_ONLY = "THROTTLED_RETRYABLE_DECLARATION_ONLY"
    TRANSIENT_RETRYABLE_DECLARATION_ONLY = "TRANSIENT_RETRYABLE_DECLARATION_ONLY"

    @property
    def retryable(self) -> bool:
        return self is not ProductSearchProviderFailureClass.PERMANENT


class RakutenProductSearchFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RAW_RESPONSE_INVALID = "RAW_RESPONSE_INVALID"
    RESULT_MISMATCH = "RESULT_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten product search serialization is not supported")


@dataclass(slots=True, repr=False)
class RakutenProductSearchFailure(RuntimeError):
    code: RakutenProductSearchFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not RakutenProductSearchFailureCode:
            raise TypeError("invalid Rakuten product search failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RakutenProductSearchFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten product search failure serialization is not supported")


def fail_product_search(
    code: RakutenProductSearchFailureCode = (
        RakutenProductSearchFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise RakutenProductSearchFailure(code) from None


def product_search_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_product_search()
    return value


def product_search_utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_product_search()
    return value


def _text(value: object, *, allow_empty: bool, maximum: int) -> str:
    if (
        type(value) is not str
        or len(value) > maximum
        or (not allow_empty and not value)
        or value != value.strip()
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        fail_product_search()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_product_search()
    return value


def _https_url(value: object) -> str:
    text = _text(value, allow_empty=False, maximum=4096)
    if (
        not text.startswith("https://")
        or "#" in text
        or "\\" in text
        or any(ord(character) <= 32 or ord(character) == 127 for character in text)
    ):
        fail_product_search()
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        fail_product_search()
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        fail_product_search()
    if ":" in hostname:
        try:
            ipaddress.IPv6Address(hostname)
        except ipaddress.AddressValueError:
            fail_product_search()
    else:
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            fail_product_search()
        labels = ascii_host.split(".")
        if any(
            not label
            or len(label) > 63
            or not label[0].isalnum()
            or not label[-1].isalnum()
            or any(not (character.isalnum() or character == "-") for character in label)
            for label in labels
        ):
            fail_product_search()
    return text


@dataclass(frozen=True, slots=True, repr=False)
class RakutenProductSearchRequest(_RedactedValue):
    api_version: str
    response_format: str
    format_version: int
    hits: int
    page: int
    product_id: str | None
    product_code: str | None
    elements: tuple[ProductSearchElement, ...]

    def __post_init__(self) -> None:
        if (
            type(self.api_version) is not str
            or self.api_version != "2025-08-01"
            or type(self.response_format) is not str
            or self.response_format != "json"
            or type(self.format_version) is not int
            or self.format_version != 2
            or type(self.hits) is not int
            or self.hits != 1
            or type(self.page) is not int
            or self.page != 1
            or type(self.elements) is not tuple
            or self.elements != PRODUCT_SEARCH_ELEMENTS
            or (self.product_id is None) == (self.product_code is None)
        ):
            fail_product_search()
        _text(self.selector_value, allow_empty=False, maximum=4096)

    @property
    def selector_kind(self) -> ProductSelectorKind:
        if self.product_id is not None:
            return ProductSelectorKind.PRODUCT_ID
        return ProductSelectorKind.PRODUCT_CODE

    @property
    def selector_value(self) -> str:
        value = self.product_id if self.product_id is not None else self.product_code
        if type(value) is not str:
            fail_product_search()
        return value

    @property
    def canonical_parameters(self) -> dict[str, object]:
        parameters: dict[str, object] = {
            "apiVersion": self.api_version,
            "elements": [element.value for element in self.elements],
            "format": self.response_format,
            "formatVersion": self.format_version,
            "hits": self.hits,
            "page": self.page,
        }
        parameters[
            "productId"
            if self.selector_kind is ProductSelectorKind.PRODUCT_ID
            else "productCode"
        ] = self.selector_value
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
class RakutenProduct(_RedactedValue):
    product_id: str
    product_code: str
    product_url_pc: str
    affiliate_url: str
    brand_name: str | None
    maker_name: str | None
    medium_image_url: str | None
    product_name: str | None
    product_no: str | None

    def __post_init__(self) -> None:
        _text(self.product_id, allow_empty=False, maximum=4096)
        _text(self.product_code, allow_empty=False, maximum=4096)
        _https_url(self.product_url_pc)
        _https_url(self.affiliate_url)
        for value in (
            self.brand_name,
            self.maker_name,
            self.product_name,
            self.product_no,
        ):
            if value is not None:
                _text(value, allow_empty=True, maximum=10_000)
        if self.medium_image_url is not None:
            _https_url(self.medium_image_url)


@dataclass(frozen=True, slots=True, repr=False)
class ProductSearchValidationReceipt(_RedactedValue):
    purpose: ProductSearchReceiptPurpose
    provider: str
    api_version: str
    request_fingerprint: str
    response_sha256: str
    byte_size: int
    received_at: datetime
    uri: None
    storage_status: ProductSearchStorageStatus
    persistence_status: ProductSearchPersistenceStatus

    def __post_init__(self) -> None:
        if (
            self.purpose is not ProductSearchReceiptPurpose.VALIDATION_ONLY
            or type(self.provider) is not str
            or self.provider != "RAKUTEN_ICHIBA"
            or type(self.api_version) is not str
            or self.api_version != "2025-08-01"
            or type(self.byte_size) is not int
            or not 2 <= self.byte_size <= 2 * 1024 * 1024
            or self.uri is not None
            or self.storage_status is not ProductSearchStorageStatus.NOT_EXECUTED
            or self.persistence_status
            is not ProductSearchPersistenceStatus.NOT_EXECUTED
        ):
            fail_product_search()
        product_search_sha256(self.request_fingerprint)
        product_search_sha256(self.response_sha256)
        product_search_utc(self.received_at)


@dataclass(frozen=True, slots=True, repr=False)
class RakutenProductSearchResult(_RedactedValue):
    provider_mode: ProductSearchProviderMode
    request_fingerprint: str
    product: RakutenProduct
    receipt: ProductSearchValidationReceipt
    live_eligible: bool

    def __post_init__(self) -> None:
        if (
            self.provider_mode is not ProductSearchProviderMode.RECORDED_TEST_ONLY
            or type(self.product) is not RakutenProduct
            or type(self.receipt) is not ProductSearchValidationReceipt
            or self.live_eligible is not False
            or self.receipt.request_fingerprint != self.request_fingerprint
        ):
            fail_product_search()
        product_search_sha256(self.request_fingerprint)


@dataclass(frozen=True, slots=True, repr=False)
class ProductSearchProviderFailure(_RedactedValue):
    http_status: int
    failure_class: ProductSearchProviderFailureClass
    retries_executed: int

    def __post_init__(self) -> None:
        expected = {
            400: ProductSearchProviderFailureClass.PERMANENT,
            404: ProductSearchProviderFailureClass.PERMANENT,
            429: ProductSearchProviderFailureClass.THROTTLED_RETRYABLE_DECLARATION_ONLY,
            500: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
            503: ProductSearchProviderFailureClass.TRANSIENT_RETRYABLE_DECLARATION_ONLY,
        }
        if (
            type(self.http_status) is not int
            or expected.get(self.http_status) is not self.failure_class
            or type(self.retries_executed) is not int
            or self.retries_executed != 0
        ):
            fail_product_search()

    @property
    def retryable(self) -> bool:
        return self.failure_class.retryable


__all__ = [
    "PRODUCT_SEARCH_ELEMENTS",
    "PRODUCT_SEARCH_ENDPOINT_PATH",
    "PRODUCT_SEARCH_FUTURE_ACCESS_KEY_TRANSPORT",
    "PRODUCT_SEARCH_FUTURE_SECRET_ALIASES",
    "ProductSearchElement",
    "ProductSearchPersistenceStatus",
    "ProductSearchProviderFailure",
    "ProductSearchProviderFailureClass",
    "ProductSearchProviderMode",
    "ProductSearchReceiptPurpose",
    "ProductSearchStorageStatus",
    "ProductSearchValidationReceipt",
    "ProductSelectorKind",
    "RakutenProduct",
    "RakutenProductSearchFailure",
    "RakutenProductSearchFailureCode",
    "RakutenProductSearchRequest",
    "RakutenProductSearchResult",
    "fail_product_search",
    "product_search_sha256",
    "product_search_utc",
]
