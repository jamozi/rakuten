"""Pure non-executable live-safe Item Search request policy for ST-0502."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import NoReturn, SupportsIndex
import unicodedata

from raos.domain.catalog.rakuten_item_search import fail_item_search


_REDACTED = "<redacted-rakuten-item-search-live-request-v1>"


class LiveItemSearchSortV1(str, Enum):
    """Exact editorial-safe subset of the installed 2026-07-01 sort vocabulary."""

    STANDARD = "standard"
    PRICE_ASCENDING = "+itemPrice"
    PRICE_DESCENDING = "-itemPrice"
    UPDATED_ASCENDING = "+updateTimestamp"
    UPDATED_DESCENDING = "-updateTimestamp"


class LiveItemSearchElementV1(str, Enum):
    """Exact current-documented live-safe output subset."""

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


LIVE_ITEM_SEARCH_ELEMENTS_V1: tuple[LiveItemSearchElementV1, ...] = tuple(
    sorted(LiveItemSearchElementV1, key=lambda element: element.value)
)


class ProviderTextTrustV1(str, Enum):
    UNTRUSTED_DATA = "UNTRUSTED_DATA"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("live-safe Item Search request serialization is not supported")


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_item_search()
    encoding_invalid = False
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        encoding_invalid = True
    if encoding_invalid:
        fail_item_search()
    return value


def _keyword_terms(value: object) -> tuple[str, ...]:
    if type(value) is not str or value != value.strip():
        fail_item_search()
    encoding_invalid = False
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        encoding_invalid = True
        encoded = b""
    if encoding_invalid or not 1 <= len(encoded) <= 128:
        fail_item_search()
    if any(
        character != " " and unicodedata.category(character)[0] in {"C", "M", "Z"}
        for character in value
    ):
        fail_item_search()

    terms = tuple(value.split(" "))
    for term in terms:
        if len(term) >= 2:
            continue
        if len(term) != 1:
            fail_item_search()
        character = term[0]
        category = unicodedata.category(character)
        name = unicodedata.name(character, "")
        if (
            unicodedata.east_asian_width(character) not in {"F", "W"}
            or category[0] not in {"L", "N"}
            or "HIRAGANA" in name
            or "KATAKANA" in name
        ):
            fail_item_search()
    return terms


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_item_search()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class RakutenItemSearchLiveRequestV1(_RedactedValue):
    """Validated policy projection only; it has no provider action surface."""

    api_version: str
    format_version: int
    keyword: str | None
    shop_code: str | None
    item_code: str | None
    genre_id: int | None
    hits: int
    page: int
    sort: LiveItemSearchSortV1
    elements: tuple[LiveItemSearchElementV1, ...]
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
        keyword_terms: tuple[str, ...] | None = None
        if self.keyword is not None:
            keyword_terms = _keyword_terms(self.keyword)
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
        if type(self.page) is not int or self.page != 1:
            fail_item_search()
        if (
            type(self.sort) is not LiveItemSearchSortV1
            or type(self.elements) is not tuple
            or self.elements != LIVE_ITEM_SEARCH_ELEMENTS_V1
        ):
            fail_item_search()
        if self.min_price_jpy is not None:
            _exact_int(self.min_price_jpy, minimum=1, maximum=999_999_998)
        if self.max_price_jpy is not None:
            _exact_int(self.max_price_jpy, minimum=1, maximum=999_999_998)
        if (
            self.min_price_jpy is not None
            and self.max_price_jpy is not None
            and self.min_price_jpy >= self.max_price_jpy
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
        if self.or_flag and (keyword_terms is None or len(keyword_terms) < 2):
            fail_item_search()
        if self.has_review_only:
            fail_item_search()
        if self.attribute_flag and (self.genre_id is None or self.genre_id == 0):
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

    @property
    def retry_limit(self) -> int:
        return 0

    @property
    def pagination_followup_limit(self) -> int:
        return 0

    @property
    def provider_text_trust(self) -> ProviderTextTrustV1:
        return ProviderTextTrustV1.UNTRUSTED_DATA

    @property
    def provider_derived_recommendation_inputs(self) -> tuple[()]:
        return ()


__all__ = [
    "LIVE_ITEM_SEARCH_ELEMENTS_V1",
    "LiveItemSearchElementV1",
    "LiveItemSearchSortV1",
    "ProviderTextTrustV1",
    "RakutenItemSearchLiveRequestV1",
]
