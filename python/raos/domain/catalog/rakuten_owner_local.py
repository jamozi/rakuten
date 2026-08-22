"""Closed owner-local Rakuten production-read contracts for ST-0505."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import ipaddress
import json
import re
from typing import NoReturn, SupportsIndex, TypeAlias, cast
import unicodedata
from urllib.parse import unquote_to_bytes, urlsplit

from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    LIVE_ITEM_SEARCH_ELEMENTS_V1,
    LiveItemSearchSortV1,
    RakutenItemSearchLiveRequestV1,
)


RAKUTEN_OWNER_LOCAL_PROFILE = "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"
RAKUTEN_OWNER_LOCAL_HOST = "openapi.rakuten.co.jp"
RAKUTEN_OWNER_LOCAL_PORT = 443
RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA = "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V3"
RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY = "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"
RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION = "UNTRUSTED_PROVIDER_DATA"
RAKUTEN_OWNER_LOCAL_FORMAL_TST_016 = "NOT_EXECUTED"
RAKUTEN_OWNER_LOCAL_STAGING = "NOT_EXECUTED"
RAKUTEN_OWNER_LOCAL_PRODUCTION = "NOT_EXECUTED"
RAKUTEN_OWNER_LOCAL_OD_015 = "UNRESOLVED_EXTERNAL_EVIDENCE_REQUIRED"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{32}\Z", re.ASCII)
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_REDACTED = "<redacted-rakuten-owner-local>"
_SUMMARY_FIELDS = frozenset({"count", "first", "hits", "last", "page", "pageCount"})
_URL_FIELDS = frozenset(
    {
        "affiliateUrl",
        "itemUrl",
        "mediumImageUrl",
        "productUrlPC",
        "smallImageUrl",
    }
)
_URL_LIST_FIELDS = frozenset({"mediumImageUrls", "smallImageUrls"})
_ITEM_INTEGER_FIELDS = frozenset(
    {"availability", "genreId", "itemPrice", "postageFlag"}
)
_PRODUCT_INTEGER_FIELDS = frozenset(
    {
        "averagePrice",
        "genreId",
        "itemCount",
        "maxPrice",
        "minPrice",
        "salesItemCount",
        "salesMaxPrice",
        "salesMinPrice",
    }
)


class RakutenOwnerLocalApi(StrEnum):
    ITEM_SEARCH = "item-search"
    PRODUCT_SEARCH = "product-search"


_NON_NULL_URL_FIELDS = {
    RakutenOwnerLocalApi.ITEM_SEARCH: frozenset({"itemUrl"}),
    RakutenOwnerLocalApi.PRODUCT_SEARCH: frozenset({"productUrlPC"}),
}


class RakutenOwnerLocalProductSort(StrEnum):
    """Review-derived Product Search ordering is deliberately unavailable."""

    STANDARD = "standard"


class RakutenOwnerLocalRequestDisposition(StrEnum):
    NOT_SENT = "NOT_SENT"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"

    @property
    def request_count(self) -> int:
        return 0 if self is RakutenOwnerLocalRequestDisposition.NOT_SENT else 1


class RakutenOwnerLocalOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class RakutenOwnerLocalFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    API_NOT_ALLOWED = "API_NOT_ALLOWED"
    REQUEST_ALREADY_ATTEMPTED = "REQUEST_ALREADY_ATTEMPTED"
    REQUEST_FILE_INVALID = "REQUEST_FILE_INVALID"
    CREDENTIAL_STORE_INVALID = "CREDENTIAL_STORE_INVALID"
    RESULT_STORE_INVALID = "RESULT_STORE_INVALID"
    DNS_FAILED = "DNS_FAILED"
    DNS_ADDRESS_REJECTED = "DNS_ADDRESS_REJECTED"
    TLS_ENVIRONMENT_INVALID = "TLS_ENVIRONMENT_INVALID"
    TLS_CONTEXT_INVALID = "TLS_CONTEXT_INVALID"
    TLS_FAILED = "TLS_FAILED"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "REQUEST_AMBIGUOUS"
    HTTP_REDIRECT_REJECTED = "HTTP_REDIRECT_REJECTED"
    HTTP_400 = "HTTP_400"
    HTTP_401 = "HTTP_401"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_500 = "HTTP_500"
    HTTP_503 = "HTTP_503"
    HTTP_STATUS_UNEXPECTED = "HTTP_STATUS_UNEXPECTED"
    RESPONSE_OVERSIZED = "RESPONSE_OVERSIZED"
    RESPONSE_CONTENT_TYPE_INVALID = "RESPONSE_CONTENT_TYPE_INVALID"
    RESPONSE_ENCODING_INVALID = "RESPONSE_ENCODING_INVALID"
    RESPONSE_JSON_INVALID = "RESPONSE_JSON_INVALID"
    RESPONSE_JSON_DUPLICATE_KEY = "RESPONSE_JSON_DUPLICATE_KEY"
    RESPONSE_JSON_NONFINITE = "RESPONSE_JSON_NONFINITE"
    RESPONSE_JSON_TREE_INVALID = "RESPONSE_JSON_TREE_INVALID"
    RESPONSE_SCHEMA_DRIFT = "RESPONSE_SCHEMA_DRIFT"
    RESULT_MISMATCH = "RESULT_MISMATCH"


class RakutenOwnerLocalValidationStageCode(StrEnum):
    """Closed, value-free location for response-validation refusals."""

    SUMMARY_SHAPE = "SUMMARY_SHAPE"
    COLLECTION_SHAPE = "COLLECTION_SHAPE"
    RECORD_SHAPE = "RECORD_SHAPE"
    EXACT_SELECTOR = "EXACT_SELECTOR"
    MANDATORY_TEXT = "MANDATORY_TEXT"
    URL = "URL"
    CREDENTIAL_REFLECTION = "CREDENTIAL_REFLECTION"


class RakutenOwnerLocalValidationDetailCode(StrEnum):
    """Closed, value-free detail for collection-shape refusals."""

    ROOT_NOT_OBJECT = "ROOT_NOT_OBJECT"
    COLLECTION_KEY_INVALID = "COLLECTION_KEY_INVALID"
    ROOT_MEMBER_UNRECOGNIZED = "ROOT_MEMBER_UNRECOGNIZED"
    COLLECTION_NOT_ARRAY = "COLLECTION_NOT_ARRAY"
    OPTIONAL_ROOT_MEMBER_VALUE_INVALID = "OPTIONAL_ROOT_MEMBER_VALUE_INVALID"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten owner-local serialization is disabled")


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return value


def _bounded_text(
    value: object,
    *,
    maximum: int,
    failure_code: RakutenOwnerLocalFailureCode = (
        RakutenOwnerLocalFailureCode.INVALID_ARGUMENT
    ),
    validation_stage_code: RakutenOwnerLocalValidationStageCode | None = None,
) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_owner_local(failure_code, validation_stage_code=validation_stage_code)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_owner_local(failure_code, validation_stage_code=validation_stage_code)
    return value


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return value


def expected_response_page_count(count: object, hits: object) -> int:
    """Return the provider's capped page count for a validated result summary."""

    if (
        type(count) is not int
        or count < 0
        or type(hits) is not int
        or not 1 <= hits <= 30
    ):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.SUMMARY_SHAPE,
        )
    if count == 0:
        return 0
    return min((count + hits - 1) // hits, 100)


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return value


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _https_url(value: object) -> str:
    text = _bounded_text(
        value,
        maximum=4096,
        failure_code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
        validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
    )
    if (
        not text.startswith("https://")
        or "\\" in text
        or any(
            character.isspace() or unicodedata.category(character) in {"Cc", "Cf"}
            for character in text
        )
    ):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    if _MALFORMED_PERCENT_ESCAPE.search(text) is not None:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.netloc.endswith(":")
        or (port is not None and not 1 <= port <= 65535)
    ):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    _validate_https_host(parsed.hostname, parsed.netloc)
    return text


def _validate_https_host(host: str, netloc: str) -> None:
    if netloc.startswith("["):
        closing = netloc.find("]")
        if closing < 0:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        suffix = netloc[closing + 1 :]
        if suffix and not suffix.startswith(":"):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        try:
            bracket_address = ipaddress.IPv6Address(netloc[1:closing])
            parsed_address = ipaddress.IPv6Address(host)
        except ipaddress.AddressValueError:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        if bracket_address != parsed_address:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        return
    if any(character in netloc for character in "[]\\"):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )
    if ascii_host.endswith("."):
        ascii_host = ascii_host[:-1]
    labels = ascii_host.split(".")
    if (
        not ascii_host
        or len(ascii_host) > 253
        or any(_HOST_LABEL.fullmatch(label) is None for label in labels)
    ):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
        )


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalApiDefinition(_RedactedValue):
    api: RakutenOwnerLocalApi
    endpoint_id: str
    api_version: str
    path: str
    elements: tuple[str, ...]
    normalized_record_fields: tuple[str, ...]
    allowed_sorts: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.api) is not RakutenOwnerLocalApi:
            fail_owner_local(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)
        expected = _API_DEFINITION_VALUES.get(self.api)
        actual = (
            self.endpoint_id,
            self.api_version,
            self.path,
            self.elements,
            self.normalized_record_fields,
            self.allowed_sorts,
        )
        if expected != actual:
            fail_owner_local(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)


_ITEM_ELEMENTS = tuple(element.value for element in LIVE_ITEM_SEARCH_ELEMENTS_V1)
_ITEM_RECORD_FIELDS = (
    "affiliateUrl",
    "availability",
    "genreId",
    "itemCode",
    "itemName",
    "itemPrice",
    "itemUrl",
    "mediumImageUrls",
    "shopCode",
    "shopName",
    "smallImageUrls",
)
_PRODUCT_ELEMENTS = (
    "affiliateUrl",
    "averagePrice",
    "brandName",
    "count",
    "first",
    "genreId",
    "genreName",
    "hits",
    "itemCount",
    "last",
    "maxPrice",
    "mediumImageUrl",
    "minPrice",
    "page",
    "pageCount",
    "productCode",
    "productId",
    "productName",
    "productNo",
    "productUrlPC",
    "salesItemCount",
    "salesMaxPrice",
    "salesMinPrice",
    "smallImageUrl",
)
_PRODUCT_RECORD_FIELDS = tuple(
    field for field in _PRODUCT_ELEMENTS if field not in _SUMMARY_FIELDS
)
_MANDATORY_RECORD_FIELDS = {
    RakutenOwnerLocalApi.ITEM_SEARCH: frozenset(
        {"affiliateUrl", "itemCode", "itemName", "itemPrice", "itemUrl"}
    ),
    RakutenOwnerLocalApi.PRODUCT_SEARCH: frozenset(
        {"affiliateUrl", "productCode", "productId", "productUrlPC"}
    ),
}
_MANDATORY_TEXT_FIELDS = {
    RakutenOwnerLocalApi.ITEM_SEARCH: frozenset({"itemCode", "itemName"}),
    RakutenOwnerLocalApi.PRODUCT_SEARCH: frozenset({"productCode", "productId"}),
}

_API_DEFINITION_VALUES: dict[
    RakutenOwnerLocalApi,
    tuple[str, str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]],
] = {
    RakutenOwnerLocalApi.ITEM_SEARCH: (
        "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701",
        "2026-07-01",
        "/ichibams/api/IchibaItem/Search/20260701",
        _ITEM_ELEMENTS,
        _ITEM_RECORD_FIELDS,
        tuple(sort.value for sort in LiveItemSearchSortV1),
    ),
    RakutenOwnerLocalApi.PRODUCT_SEARCH: (
        "RAKUTEN_ICHIBA_PRODUCT_SEARCH_20250801",
        "2025-08-01",
        "/ichibaproduct/api/Product/Search/20250801",
        _PRODUCT_ELEMENTS,
        _PRODUCT_RECORD_FIELDS,
        (RakutenOwnerLocalProductSort.STANDARD.value,),
    ),
}


def api_definition(api: RakutenOwnerLocalApi) -> RakutenOwnerLocalApiDefinition:
    if type(api) is not RakutenOwnerLocalApi or api not in _API_DEFINITION_VALUES:
        fail_owner_local(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)
    endpoint_id, api_version, path, elements, record_fields, sorts = (
        _API_DEFINITION_VALUES[api]
    )
    return RakutenOwnerLocalApiDefinition(
        api=api,
        endpoint_id=endpoint_id,
        api_version=api_version,
        path=path,
        elements=elements,
        normalized_record_fields=record_fields,
        allowed_sorts=sorts,
    )


def owner_local_api_registry() -> tuple[RakutenOwnerLocalApiDefinition, ...]:
    return tuple(api_definition(api) for api in RakutenOwnerLocalApi)


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalItemSearchRequest(_RedactedValue):
    """Narrow wrapper around the unchanged ST-0502 Item live policy."""

    policy: RakutenItemSearchLiveRequestV1

    def __post_init__(self) -> None:
        if type(self.policy) is not RakutenItemSearchLiveRequestV1:
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        selectors = (
            self.policy.keyword,
            self.policy.shop_code,
            self.policy.item_code,
            self.policy.genre_id,
        )
        if sum(selector is not None for selector in selectors) != 1:
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        if (
            self.policy.api_version != "2026-07-01"
            or self.policy.format_version != 2
            or self.policy.page != 1
            or self.policy.elements != LIVE_ITEM_SEARCH_ELEMENTS_V1
            or self.policy.min_price_jpy is not None
            or self.policy.max_price_jpy is not None
            or self.policy.or_flag
            or self.policy.availability is not True
            or self.policy.postage_included_only
            or self.policy.has_review_only
            or self.policy.appoint_delivery_date_only
            or self.policy.attribute_flag
            or self.policy.genre_information_flag
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)

    @property
    def api(self) -> RakutenOwnerLocalApi:
        return RakutenOwnerLocalApi.ITEM_SEARCH

    @property
    def canonical_parameters(self) -> dict[str, object]:
        return {
            "api": self.api.value,
            "endpoint_id": api_definition(self.api).endpoint_id,
            "policy": self.policy.canonical_parameters,
        }

    @property
    def canonical_json(self) -> bytes:
        return _canonical_json(self.canonical_parameters)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalProductSearchRequest(_RedactedValue):
    keyword: str | None
    genre_id: int | None
    product_id: str | None
    product_code: str | None
    hits: int
    page: int
    sort: RakutenOwnerLocalProductSort

    def __post_init__(self) -> None:
        if self.keyword is not None:
            _bounded_text(self.keyword, maximum=128)
        if self.genre_id is not None:
            _exact_int(self.genre_id, minimum=0, maximum=(1 << 63) - 1)
        if self.product_id is not None:
            _bounded_text(self.product_id, maximum=4096)
        if self.product_code is not None:
            _bounded_text(self.product_code, maximum=4096)
        search_mode = self.keyword is not None or self.genre_id is not None
        identifier_count = sum(
            value is not None for value in (self.product_id, self.product_code)
        )
        if (
            (search_mode and identifier_count != 0)
            or (not search_mode and identifier_count != 1)
            or type(self.hits) is not int
            or not 1 <= self.hits <= 30
            or type(self.page) is not int
            or self.page != 1
            or type(self.sort) is not RakutenOwnerLocalProductSort
            or self.sort is not RakutenOwnerLocalProductSort.STANDARD
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)

    @property
    def api(self) -> RakutenOwnerLocalApi:
        return RakutenOwnerLocalApi.PRODUCT_SEARCH

    @property
    def canonical_parameters(self) -> dict[str, object]:
        parameters: dict[str, object] = {
            "api": self.api.value,
            "apiVersion": api_definition(self.api).api_version,
            "elements": list(api_definition(self.api).elements),
            "format": "json",
            "formatVersion": 2,
            "hits": self.hits,
            "page": self.page,
            "sort": self.sort.value,
        }
        optional = {
            "genreId": self.genre_id,
            "keyword": self.keyword,
            "productCode": self.product_code,
            "productId": self.product_id,
        }
        parameters.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return dict(sorted(parameters.items()))

    @property
    def canonical_json(self) -> bytes:
        return _canonical_json(self.canonical_parameters)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


RakutenOwnerLocalRequest: TypeAlias = (
    RakutenOwnerLocalItemSearchRequest | RakutenOwnerLocalProductSearchRequest
)


def exact_response_selector(
    request: RakutenOwnerLocalRequest,
) -> tuple[str, str] | None:
    """Return the one response identity field selected by an exact lookup."""

    if type(request) is RakutenOwnerLocalItemSearchRequest:
        selectors = (
            ("itemCode", request.policy.item_code),
            ("shopCode", request.policy.shop_code),
        )
    elif type(request) is RakutenOwnerLocalProductSearchRequest:
        selectors = (
            ("productId", request.product_id),
            ("productCode", request.product_code),
        )
    else:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    selected = tuple((field, value) for field, value in selectors if value is not None)
    if len(selected) > 1:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return selected[0] if selected else None


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fixed_item_request() -> RakutenOwnerLocalItemSearchRequest:
    return RakutenOwnerLocalItemSearchRequest(
        policy=RakutenItemSearchLiveRequestV1(
            api_version="2026-07-01",
            format_version=2,
            keyword="収納",
            shop_code=None,
            item_code=None,
            genre_id=None,
            hits=1,
            page=1,
            sort=LiveItemSearchSortV1.STANDARD,
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1,
            min_price_jpy=None,
            max_price_jpy=None,
            or_flag=False,
            availability=True,
            postage_included_only=False,
            has_review_only=False,
            appoint_delivery_date_only=False,
            attribute_flag=False,
            genre_information_flag=False,
        )
    )


def fixed_owner_local_smoke_request(
    api: RakutenOwnerLocalApi,
) -> RakutenOwnerLocalRequest:
    if api is RakutenOwnerLocalApi.ITEM_SEARCH:
        return _fixed_item_request()
    if api is RakutenOwnerLocalApi.PRODUCT_SEARCH:
        return RakutenOwnerLocalProductSearchRequest(
            keyword="収納",
            genre_id=None,
            product_id=None,
            product_code=None,
            hits=1,
            page=1,
            sort=RakutenOwnerLocalProductSort.STANDARD,
        )
    fail_owner_local(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalCredentials(_RedactedValue):
    profile: str
    _application_id: bytes
    _access_key: bytes
    _affiliate_id: bytes

    def __post_init__(self) -> None:
        if type(self.profile) is not str or self.profile != RAKUTEN_OWNER_LOCAL_PROFILE:
            fail_owner_local(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        for value, maximum in (
            (self._application_id, 256),
            (self._access_key, 4096),
            (self._affiliate_id, 256),
        ):
            if (
                type(value) is not bytes
                or not 1 <= len(value) <= maximum
                or any(byte < 0x21 or byte > 0x7E for byte in value)
            ):
                fail_owner_local(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)

    def application_id_query_value(self) -> str:
        return self._application_id.decode("ascii", errors="strict")

    def access_key_header_value(self) -> str:
        return self._access_key.decode("ascii", errors="strict")

    def affiliate_id_query_value(self) -> str:
        return self._affiliate_id.decode("ascii", errors="strict")

    def reject_reflected_result(self, result: RakutenOwnerLocalProviderResult) -> None:
        """Reject credentials reflected through normalized provider text."""

        if type(result) is not RakutenOwnerLocalProviderResult:
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        credential_values = (
            self._application_id,
            self._access_key,
            self._affiliate_id,
        )
        candidates = (
            candidate
            for record in result.records
            for _name, candidate in record.fields
            if type(candidate) in {str, tuple}
        )
        for candidate in candidates:
            text_values: tuple[str, ...]
            if type(candidate) is str:
                text_values = (candidate,)
            else:
                text_values = cast(tuple[str, ...], candidate)
            for text in text_values:
                encoded_values = (
                    text.encode("utf-8", errors="strict"),
                    unquote_to_bytes(text),
                )
                if any(
                    credential in encoded
                    for encoded in encoded_values
                    for credential in credential_values
                ):
                    fail_owner_local(
                        RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                        validation_stage_code=(
                            RakutenOwnerLocalValidationStageCode.CREDENTIAL_REFLECTION
                        ),
                    )


NormalizedValue: TypeAlias = None | bool | int | str | tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalNormalizedRecord(_RedactedValue):
    api: RakutenOwnerLocalApi
    fields: tuple[tuple[str, NormalizedValue], ...]

    def __post_init__(self) -> None:
        definition = api_definition(self.api)
        if (
            type(self.fields) is not tuple
            or not self.fields
            or any(
                type(field) is not tuple or len(field) != 2 or type(field[0]) is not str
                for field in self.fields
            )
        ):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        allowed = frozenset(definition.normalized_record_fields)
        expected_mandatory = mandatory_record_fields(self.api)
        names = tuple(name for name, _value in self.fields)
        if (
            names != tuple(sorted(names))
            or len(names) != len(set(names))
            or not frozenset(names) <= allowed
            or not expected_mandatory <= frozenset(names)
            or not frozenset(names).isdisjoint(
                {"reviewAverage", "reviewCount", "affiliateRate"}
            )
        ):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        for name, value in self.fields:
            if name in _MANDATORY_TEXT_FIELDS[self.api]:
                _validate_normalized_value(self.api, name, value)
        for name, value in self.fields:
            if name in _URL_FIELDS or name in _URL_LIST_FIELDS:
                _validate_normalized_value(self.api, name, value)
        for name, value in self.fields:
            if (
                name not in _MANDATORY_TEXT_FIELDS[self.api]
                and name not in _URL_FIELDS
                and name not in _URL_LIST_FIELDS
            ):
                _validate_normalized_value(self.api, name, value)

    def as_object(self) -> dict[str, object]:
        return {
            name: list(value) if type(value) is tuple else value
            for name, value in self.fields
        }


def _validate_normalized_value(
    api: RakutenOwnerLocalApi, name: str, value: object
) -> None:
    if name in _MANDATORY_TEXT_FIELDS[api]:
        validated_response_text(
            value,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.MANDATORY_TEXT,
        )
        return
    if name in _URL_LIST_FIELDS:
        if type(value) is not tuple:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        members = cast(tuple[object, ...], value)
        if len(members) > 64:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
            )
        for member in members:
            _https_url(member)
        return
    if name in _URL_FIELDS:
        if value is None:
            if name in _NON_NULL_URL_FIELDS[api]:
                fail_owner_local(
                    RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                    validation_stage_code=RakutenOwnerLocalValidationStageCode.URL,
                )
            return
        _https_url(value)
        return
    if api is RakutenOwnerLocalApi.ITEM_SEARCH and name in _ITEM_INTEGER_FIELDS:
        if type(value) is not int or value < 0:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        if name in {"availability", "postageFlag"} and value not in {0, 1}:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        return
    if api is RakutenOwnerLocalApi.PRODUCT_SEARCH and name in _PRODUCT_INTEGER_FIELDS:
        if type(value) is not int or value < 0:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        return
    if value is None:
        return
    if type(value) is not str or len(value) > 20_000:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.RECORD_SHAPE,
        )
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.RECORD_SHAPE,
        )


def mandatory_record_fields(api: RakutenOwnerLocalApi) -> frozenset[str]:
    if type(api) is not RakutenOwnerLocalApi:
        fail_owner_local(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)
    return _MANDATORY_RECORD_FIELDS[api]


def validated_response_text(
    value: object,
    *,
    validation_stage_code: RakutenOwnerLocalValidationStageCode = (
        RakutenOwnerLocalValidationStageCode.MANDATORY_TEXT
    ),
) -> str:
    return _bounded_text(
        value,
        maximum=20_000,
        failure_code=RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
        validation_stage_code=validation_stage_code,
    )


def _validated_record_mapping(
    api: RakutenOwnerLocalApi, fields: Mapping[str, object]
) -> dict[str, object]:
    if type(api) is not RakutenOwnerLocalApi or type(fields) is not dict:
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.RECORD_SHAPE,
        )
    mapping = cast(dict[str, object], fields)
    if any(type(name) is not str for name in mapping):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.RECORD_SHAPE,
        )
    names = frozenset(mapping)
    definition = api_definition(api)
    if (
        not names <= frozenset(definition.normalized_record_fields)
        or not mandatory_record_fields(api) <= names
        or not names.isdisjoint({"reviewAverage", "reviewCount", "affiliateRate"})
    ):
        fail_owner_local(
            RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
            validation_stage_code=RakutenOwnerLocalValidationStageCode.RECORD_SHAPE,
        )
    return mapping


def validate_record_mandatory_text(
    api: RakutenOwnerLocalApi, fields: Mapping[str, object]
) -> None:
    """Validate mandatory text without inspecting any later record stage."""

    mapping = _validated_record_mapping(api, fields)
    for name in _MANDATORY_TEXT_FIELDS[api]:
        validated_response_text(
            mapping[name],
            validation_stage_code=RakutenOwnerLocalValidationStageCode.MANDATORY_TEXT,
        )


def validate_record_shape(
    api: RakutenOwnerLocalApi, fields: Mapping[str, object]
) -> None:
    """Validate record structure and ordinary scalars before later stages."""

    mapping = _validated_record_mapping(api, fields)
    for name, value in mapping.items():
        if (
            name not in _MANDATORY_TEXT_FIELDS[api]
            and name not in _URL_FIELDS
            and name not in _URL_LIST_FIELDS
        ):
            _validate_normalized_value(api, name, value)


def validate_record_urls(
    api: RakutenOwnerLocalApi, fields: Mapping[str, object]
) -> None:
    """Validate URL values without inspecting any later record stage."""

    mapping = _validated_record_mapping(api, fields)
    for name, value in mapping.items():
        if name in _URL_LIST_FIELDS and type(value) is list:
            value = tuple(cast(list[object], value))
        if name in _URL_FIELDS or name in _URL_LIST_FIELDS:
            _validate_normalized_value(api, name, value)


def normalized_record(
    api: RakutenOwnerLocalApi, fields: Mapping[str, object]
) -> RakutenOwnerLocalNormalizedRecord:
    mapping = _validated_record_mapping(api, fields)
    validate_record_shape(api, mapping)
    validate_record_mandatory_text(api, mapping)
    validate_record_urls(api, mapping)
    normalized: list[tuple[str, NormalizedValue]] = []
    for name, value in mapping.items():
        converted: NormalizedValue
        if type(value) is list:
            raw_list = cast(list[object], value)
            if any(type(member) is not str for member in raw_list):
                fail_owner_local(
                    RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                    validation_stage_code=(
                        RakutenOwnerLocalValidationStageCode.URL
                        if name in _URL_LIST_FIELDS
                        else RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                    ),
                )
            converted = tuple(cast(list[str], raw_list))
        elif value is None or type(value) in {bool, int, str}:
            converted = cast(NormalizedValue, value)
        else:
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.URL
                    if name in _URL_FIELDS or name in _URL_LIST_FIELDS
                    else RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        normalized.append((name, converted))
    return RakutenOwnerLocalNormalizedRecord(
        api=api,
        fields=tuple(sorted(normalized)),
    )


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalProviderResult(_RedactedValue):
    api: RakutenOwnerLocalApi
    request_fingerprint: str
    http_status: int
    body_byte_count: int
    response_sha256: str
    count: int
    page: int
    first: int
    last: int
    hits: int
    page_count: int
    records: tuple[RakutenOwnerLocalNormalizedRecord, ...]
    disposition: RakutenOwnerLocalRequestDisposition = (
        RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )

    def __post_init__(self) -> None:
        _sha256(self.request_fingerprint)
        _sha256(self.response_sha256)
        if (
            type(self.api) is not RakutenOwnerLocalApi
            or type(self.http_status) is not int
            or self.http_status != 200
            or type(self.body_byte_count) is not int
            or not 2 <= self.body_byte_count <= RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES
            or type(self.count) is not int
            or self.count < 0
            or type(self.page) is not int
            or self.page != 1
            or type(self.first) is not int
            or self.first < 0
            or type(self.last) is not int
            or self.last < 0
            or type(self.hits) is not int
            or not 1 <= self.hits <= 30
            or type(self.page_count) is not int
            or not 0 <= self.page_count <= 100
            or self.disposition
            is not RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
        ):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.SUMMARY_SHAPE
                ),
            )
        if (
            type(self.records) is not tuple
            or len(self.records) > self.hits
            or any(
                type(record) is not RakutenOwnerLocalNormalizedRecord
                or record.api is not self.api
                for record in self.records
            )
        ):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.RECORD_SHAPE
                ),
            )
        record_count = len(self.records)
        if (
            self.count < record_count
            or (self.count == 0) != (record_count == 0)
            or (self.page_count == 0) != (record_count == 0)
            or self.page_count != expected_response_page_count(self.count, self.hits)
            or self.first != (1 if record_count else 0)
            or self.last != record_count
        ):
            fail_owner_local(
                RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT,
                validation_stage_code=(
                    RakutenOwnerLocalValidationStageCode.SUMMARY_SHAPE
                ),
            )

    @property
    def request_count(self) -> int:
        return self.disposition.request_count

    def normalized_object(self) -> dict[str, object]:
        collection_name = (
            "items" if self.api is RakutenOwnerLocalApi.ITEM_SEARCH else "products"
        )
        return {
            "classification": RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION,
            "count": self.count,
            "first": self.first,
            "hits": self.hits,
            "last": self.last,
            "page": self.page,
            "pageCount": self.page_count,
            collection_name: [record.as_object() for record in self.records],
        }


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalFailure(RuntimeError):
    code: RakutenOwnerLocalFailureCode
    disposition: RakutenOwnerLocalRequestDisposition = (
        RakutenOwnerLocalRequestDisposition.NOT_SENT
    )
    api: RakutenOwnerLocalApi | None = None
    request_fingerprint: str | None = None
    http_status: int | None = None
    body_byte_count: int | None = None
    response_sha256: str | None = None
    validation_stage_code: RakutenOwnerLocalValidationStageCode | None = None
    validation_detail_code: RakutenOwnerLocalValidationDetailCode | None = None

    def __post_init__(self) -> None:
        if (
            type(self.code) is not RakutenOwnerLocalFailureCode
            or (
                self.validation_stage_code is not None
                and type(self.validation_stage_code)
                is not RakutenOwnerLocalValidationStageCode
            )
            or (
                self.validation_detail_code is not None
                and type(self.validation_detail_code)
                is not RakutenOwnerLocalValidationDetailCode
            )
            or type(self.disposition) is not RakutenOwnerLocalRequestDisposition
            or (self.api is not None and type(self.api) is not RakutenOwnerLocalApi)
            or (
                self.request_fingerprint is not None
                and (
                    type(self.request_fingerprint) is not str
                    or _SHA256.fullmatch(self.request_fingerprint) is None
                )
            )
            or (self.http_status is not None and type(self.http_status) is not int)
            or (
                self.body_byte_count is not None
                and (type(self.body_byte_count) is not int or self.body_byte_count < 0)
            )
            or (
                self.response_sha256 is not None
                and (
                    type(self.response_sha256) is not str
                    or _SHA256.fullmatch(self.response_sha256) is None
                )
            )
        ):
            raise TypeError("invalid Rakuten owner-local failure")
        if self.validation_stage_code is not None:
            allowed_codes = {RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT}
            if (
                self.validation_stage_code
                is RakutenOwnerLocalValidationStageCode.EXACT_SELECTOR
            ):
                allowed_codes.add(RakutenOwnerLocalFailureCode.RESULT_MISMATCH)
            if self.code not in allowed_codes:
                raise TypeError("invalid Rakuten owner-local validation stage")
        if (
            self.validation_stage_code
            is RakutenOwnerLocalValidationStageCode.COLLECTION_SHAPE
        ) != (self.validation_detail_code is not None):
            raise TypeError("invalid Rakuten owner-local validation detail")
        if self.disposition is RakutenOwnerLocalRequestDisposition.NOT_SENT and any(
            value is not None
            for value in (self.http_status, self.body_byte_count, self.response_sha256)
        ):
            raise TypeError("unsent request cannot have response metadata")
        if self.disposition is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS:
            if any(
                value is not None
                for value in (
                    self.http_status,
                    self.body_byte_count,
                    self.response_sha256,
                )
            ):
                raise TypeError("ambiguous request cannot claim response metadata")
        if self.disposition is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED:
            if (
                self.http_status is None
                or self.body_byte_count is None
                or self.response_sha256 is None
            ):
                raise TypeError("received response requires complete metadata")
        RuntimeError.__init__(self, self.code.value)

    @property
    def request_count(self) -> int:
        return self.disposition.request_count

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"RakutenOwnerLocalFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Rakuten owner-local failure serialization is disabled")


def fail_owner_local(
    code: RakutenOwnerLocalFailureCode,
    *,
    validation_stage_code: RakutenOwnerLocalValidationStageCode | None = None,
    validation_detail_code: RakutenOwnerLocalValidationDetailCode | None = None,
    disposition: RakutenOwnerLocalRequestDisposition = (
        RakutenOwnerLocalRequestDisposition.NOT_SENT
    ),
    api: RakutenOwnerLocalApi | None = None,
    request_fingerprint: str | None = None,
    http_status: int | None = None,
    body_byte_count: int | None = None,
    response_sha256: str | None = None,
) -> NoReturn:
    raise RakutenOwnerLocalFailure(
        code=code,
        validation_stage_code=validation_stage_code,
        validation_detail_code=validation_detail_code,
        disposition=disposition,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=http_status,
        body_byte_count=body_byte_count,
        response_sha256=response_sha256,
    ) from None


def contextual_failure(
    failure: RakutenOwnerLocalFailure,
    *,
    api: RakutenOwnerLocalApi,
    request_fingerprint: str,
) -> RakutenOwnerLocalFailure:
    if type(failure) is not RakutenOwnerLocalFailure:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return RakutenOwnerLocalFailure(
        code=failure.code,
        validation_stage_code=failure.validation_stage_code,
        validation_detail_code=failure.validation_detail_code,
        disposition=failure.disposition,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=failure.http_status,
        body_byte_count=failure.body_byte_count,
        response_sha256=failure.response_sha256,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RakutenOwnerLocalResultEnvelope(_RedactedValue):
    run_id: str
    started_at: datetime
    finished_at: datetime
    api: RakutenOwnerLocalApi
    request_fingerprint: str
    outcome: RakutenOwnerLocalOutcome
    provider_result: RakutenOwnerLocalProviderResult | None
    failure: RakutenOwnerLocalFailure | None

    def __post_init__(self) -> None:
        _sha256(self.request_fingerprint)
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or _utc(self.started_at) > _utc(self.finished_at)
            or type(self.api) is not RakutenOwnerLocalApi
            or type(self.outcome) is not RakutenOwnerLocalOutcome
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        if self.outcome is RakutenOwnerLocalOutcome.SUCCESS:
            if (
                type(self.provider_result) is not RakutenOwnerLocalProviderResult
                or self.failure is not None
                or self.provider_result.api is not self.api
                or self.provider_result.request_fingerprint != self.request_fingerprint
            ):
                fail_owner_local(RakutenOwnerLocalFailureCode.RESULT_MISMATCH)
        elif (
            self.provider_result is not None
            or type(self.failure) is not RakutenOwnerLocalFailure
            or self.failure.api is not self.api
            or self.failure.request_fingerprint != self.request_fingerprint
        ):
            fail_owner_local(RakutenOwnerLocalFailureCode.RESULT_MISMATCH)

    @property
    def disposition(self) -> RakutenOwnerLocalRequestDisposition:
        if self.provider_result is not None:
            return self.provider_result.disposition
        if self.failure is None:
            fail_owner_local(RakutenOwnerLocalFailureCode.RESULT_MISMATCH)
        return self.failure.disposition

    @property
    def request_count(self) -> int:
        return self.disposition.request_count

    def as_result_object(self) -> dict[str, object]:
        definition = api_definition(self.api)
        result = self.provider_result
        failure = self.failure
        normalized = result.normalized_object() if result is not None else None
        return {
            "schema": RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA,
            "version": 3,
            "run_id": self.run_id,
            "started_at": _utc_text(self.started_at),
            "finished_at": _utc_text(self.finished_at),
            "api": self.api.value,
            "endpoint_id": definition.endpoint_id,
            "api_version": definition.api_version,
            "outcome": self.outcome.value,
            "diagnostic_code": failure.code.value if failure is not None else "PASS",
            "validation_stage_code": (
                failure.validation_stage_code.value
                if failure is not None and failure.validation_stage_code is not None
                else None
            ),
            "validation_detail_code": (
                failure.validation_detail_code.value
                if failure is not None and failure.validation_detail_code is not None
                else None
            ),
            "request_fingerprint": self.request_fingerprint,
            "request_disposition": self.disposition.value,
            "request_count": self.request_count,
            "retry_count": 0,
            "pagination_count": 0,
            "http_status": (
                result.http_status
                if result is not None
                else failure.http_status
                if failure is not None
                else None
            ),
            "body_byte_count": (
                result.body_byte_count
                if result is not None
                else failure.body_byte_count
                if failure is not None
                else None
            ),
            "response_sha256": (
                result.response_sha256
                if result is not None
                else failure.response_sha256
                if failure is not None
                else None
            ),
            "count": result.count if result is not None else None,
            "page": result.page if result is not None else None,
            "first": result.first if result is not None else None,
            "last": result.last if result is not None else None,
            "hits": result.hits if result is not None else None,
            "pageCount": result.page_count if result is not None else None,
            "items": (
                normalized.get("items")
                if normalized is not None
                and self.api is RakutenOwnerLocalApi.ITEM_SEARCH
                else None
            ),
            "products": (
                normalized.get("products")
                if normalized is not None
                and self.api is RakutenOwnerLocalApi.PRODUCT_SEARCH
                else None
            ),
            "provider_data_classification": (
                RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION
                if result is not None
                else None
            ),
            "evidence_authority": RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY,
            "formal_tst_016": RAKUTEN_OWNER_LOCAL_FORMAL_TST_016,
            "staging": RAKUTEN_OWNER_LOCAL_STAGING,
            "production": RAKUTEN_OWNER_LOCAL_PRODUCTION,
            "od_015": RAKUTEN_OWNER_LOCAL_OD_015,
        }


def validate_run_id(value: object) -> str:
    if type(value) is not str or _RUN_ID.fullmatch(value) is None:
        fail_owner_local(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
    return value


__all__ = [
    "RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY",
    "RAKUTEN_OWNER_LOCAL_FORMAL_TST_016",
    "RAKUTEN_OWNER_LOCAL_HOST",
    "RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES",
    "RAKUTEN_OWNER_LOCAL_OD_015",
    "RAKUTEN_OWNER_LOCAL_PORT",
    "RAKUTEN_OWNER_LOCAL_PRODUCTION",
    "RAKUTEN_OWNER_LOCAL_PROFILE",
    "RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION",
    "RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA",
    "RAKUTEN_OWNER_LOCAL_STAGING",
    "NormalizedValue",
    "RakutenOwnerLocalApi",
    "RakutenOwnerLocalApiDefinition",
    "RakutenOwnerLocalCredentials",
    "RakutenOwnerLocalFailure",
    "RakutenOwnerLocalFailureCode",
    "RakutenOwnerLocalValidationDetailCode",
    "RakutenOwnerLocalValidationStageCode",
    "RakutenOwnerLocalItemSearchRequest",
    "RakutenOwnerLocalNormalizedRecord",
    "RakutenOwnerLocalOutcome",
    "RakutenOwnerLocalProductSearchRequest",
    "RakutenOwnerLocalProductSort",
    "RakutenOwnerLocalProviderResult",
    "RakutenOwnerLocalRequest",
    "RakutenOwnerLocalRequestDisposition",
    "RakutenOwnerLocalResultEnvelope",
    "api_definition",
    "contextual_failure",
    "exact_response_selector",
    "fail_owner_local",
    "fixed_owner_local_smoke_request",
    "normalized_record",
    "owner_local_api_registry",
    "validate_record_mandatory_text",
    "validate_record_shape",
    "validate_record_urls",
    "validate_run_id",
]
