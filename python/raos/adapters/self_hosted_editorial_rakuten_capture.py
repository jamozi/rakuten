"""Owner-authorized bounded Rakuten product capture for the ST-1704 pilot.

The adapter accepts only one of the five tracked article IDs.  Product selectors,
provider origins, response fields, image size, output paths, and write policy all
come from verified tracked documents.  It has no caller URL, publication,
WordPress, media-upload, taxonomy, plugin, theme, analytics, or generic HTTP
capability.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import fcntl
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import time
from typing import Final, NoReturn, Protocol, cast, final, runtime_checkable
import unicodedata
from urllib.parse import unquote, urlencode, urlsplit
from urllib.parse import parse_qs
import zlib

from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    PILOT_ARTICLE_IDENTITIES,
    RakutenProductEvidence,
    bytes_sha256,
    canonical_rakuten_provider_item_url,
    canonical_json_bytes,
    canonical_sha256,
    decoded_baseline_jpeg_dimensions,
    require_rakuten_affiliate_url,
)


ARTICLES_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)
SOURCE_REGISTRY_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json"
)
MEDIA_REGISTRY_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/media/"
    "product-media-registry.v1.json"
)
PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
OWNER_DIRECTORY: Final = "st1704-self-hosted-editorial-pilot"
RAKUTEN_DIRECTORY: Final = "rakuten"
OWNER_CREDENTIAL_RELATIVE_PATH: Final = Path(
    ".secrets/rakuten-owner-local/credentials.v1.json"
)
OWNER_CREDENTIAL_PROFILE: Final = "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"
RAKUTEN_API_HOST: Final = "openapi.rakuten.co.jp"
RAKUTEN_API_PATH: Final = "/ichibams/api/IchibaItem/Search/20260701"
RAKUTEN_API_ENDPOINT: Final = f"https://{RAKUTEN_API_HOST}{RAKUTEN_API_PATH}"
RAKUTEN_IMAGE_HOST: Final = "thumbnail.image.rakuten.co.jp"
CAPTURE_USER_AGENT: Final = "RAOS-ST-1704-bounded-product-capture/1"
CONNECT_TIMEOUT_SECONDS: Final = 10
READ_TIMEOUT_SECONDS: Final = 20
MINIMUM_REQUEST_INTERVAL_SECONDS: Final = 1.1
MAX_REGISTRY_BYTES: Final = 4_000_000
MAX_RESPONSE_BYTES: Final = 4_000_000
MAX_IMAGE_BYTES: Final = 2_000_000
MAX_IMAGE_CANDIDATES: Final = 3
MAX_CREDENTIAL_BYTES: Final = 4096
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
CAPTURE_LOCK_FILE: Final = "rakuten-product-capture.lock"
REQUEST_PACING_FILE: Final = "rakuten-request-pacing.v1"
PUBLICATION_AUTHORITY: Final = "NONE"

_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z", re.ASCII)
_ITEM_CODE = re.compile(r"[A-Za-z0-9._~-]{1,100}:[A-Za-z0-9._~-]{1,200}\Z", re.ASCII)
_JAN = re.compile(r"[0-9]{8,14}\Z", re.ASCII)
_CONTENT_LENGTH = re.compile(r"0|[1-9][0-9]*\Z", re.ASCII)
_JSON_CONTENT_TYPE = re.compile(
    r'application/json(?:\s*;\s*charset="?(?:utf-8|UTF-8)"?)?\Z', re.ASCII
)
_IMAGE_CONTENT_TYPE = re.compile(
    r"image/(?:jpeg|png|gif)(?:\s*;\s*charset=binary)?\Z",
    re.ASCII | re.IGNORECASE,
)
_ARTICLE_IDS: Final = frozenset(
    identity.article_id for identity in PILOT_ARTICLE_IDENTITIES
)
_FINAL_PORTFOLIO_ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)
_FINAL_PORTFOLIO_PRODUCT_COUNT: Final = 31
_FINAL_PORTFOLIO_PRODUCT_PLACEMENT_COUNT: Final = 37
_FINAL_PORTFOLIO_CTA_PLACEMENT_COUNT: Final = 74
_PRODUCT_SHOP_CODES: Final = (
    ("PRD-PROTECA-TRI-AIR-01541", "ace-store"),
    ("PRD-ACE-DIFFERENCE-05721", "ace-store"),
    ("PRD-ACE-MAXPASS4-01471", "ace-store"),
    ("PRD-ANKER-SOLIX-C300", "anker"),
    ("PRD-JACKERY-500-NEW", "jackery-japan"),
    ("PRD-ANKER-SOLIX-C800", "wich"),
    ("PRD-JACKERY-1000-NEW-V3", "jackery-japan"),
    ("PRD-DJI-POWER-1000-V2", "dji-shop"),
    ("PRD-SIROCA-SS-M171", "siroca"),
    ("PRD-THANKO-RAKUA-MINI-TK-MDW22W", "thanko"),
    ("PRD-SIROCA-SS-MA251", "siroca"),
    ("PRD-TOSHIBA-DWS-33B-W", "jyupro"),
    ("PRD-ANKER-SOLIX-C800-PLUS", "anker"),
    ("PRD-ANKER-SOLIX-C1000", "anker"),
    ("PRD-ANKER-SOLIX-C1000-GEN2", "anker"),
    ("PRD-EUFY-AUTOEMPTY-C10-T2292", "anker"),
    ("PRD-SWITCHBOT-K11-PRO", "switchbot"),
    ("PRD-ECOVACS-DEEBOT-MINI2", "store-ecovacs-japan"),
    ("PRD-IROBOT-ROOMBA-PLUS-515-COMBO", "edion"),
)
_FIXED_PRODUCT_ITEM_CODES: Final = {
    "PRD-PROTECA-TRI-AIR-01541": "ace-store:01541",
    "PRD-ANKER-SOLIX-C300": "anker:10002036",
    "PRD-JACKERY-500-NEW": "jackery-japan:10000000",
    "PRD-ANKER-SOLIX-C800": "wich:a-a17535z1",
    "PRD-DJI-POWER-1000-V2": "dji-shop:6937224104761",
    "PRD-ANKER-SOLIX-C800-PLUS": "anker:10001890",
    "PRD-ANKER-SOLIX-C1000": "anker:10001654",
    "PRD-ANKER-SOLIX-C1000-GEN2": "anker:10002336",
    "PRD-THANKO-RAKUA-MINI-TK-MDW22W": "thanko:10005443",
    "PRD-SIROCA-SS-MA251": "siroca:10000024",
    "PRD-TOSHIBA-DWS-33B-W": "jyupro:10136298",
    "PRD-SWITCHBOT-K11-PRO": "switchbot:10000327",
    "PRD-ECOVACS-DEEBOT-MINI2": "store-ecovacs-japan:djx28-01ee",
    "PRD-IROBOT-ROOMBA-PLUS-515-COMBO": "edion:10909675",
}
_PORTABLE_POWER_PRODUCT_IDS: Final = frozenset(
    {
        "PRD-ANKER-SOLIX-C300",
        "PRD-JACKERY-500-NEW",
        "PRD-ANKER-SOLIX-C800",
        "PRD-DJI-POWER-1000-V2",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    }
)
_PORTABLE_POWER_BUNDLE_TOKENS: Final = (
    "solar generator",
    "with ",
    "ソーラーパネル",
    "セット",
)
_DISCOVERY_ACCESSORY_TOKENS: Final = (
    "ケーブル",
    "変換",
    "拡張バッテリー",
    "防水バッグ",
    "収納用",
    "延長保証",
    "保証サービス",
    "保証プラン",
    "あんしん保証",
    "物損保証",
)
_REQUEST_ELEMENTS: Final = (
    "itemCode",
    "itemName",
    "itemUrl",
    "mediumImageUrls",
)
_AFFILIATE_REQUEST_ELEMENTS: Final = ("affiliateUrl", *_REQUEST_ELEMENTS)
_DISCOVERY_ELEMENTS: Final = (*_REQUEST_ELEMENTS, "shopCode", "shopName")
_RESPONSE_SUMMARY_FIELDS: Final = frozenset(
    {"count", "page", "first", "last", "hits", "pageCount"}
)
_NO_MODIFICATION_POLICY: Final = (
    ("aspect_ratio_change_allowed", False),
    ("crop_allowed", False),
    ("modification_allowed", False),
    ("text_overlay_allowed", False),
    ("upscale_allowed", False),
)
_FORBIDDEN_ENVIRONMENT: Final = frozenset(
    {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "sslkeylogfile",
    }
)


class RakutenProductCaptureFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    ARTICLE_NOT_ALLOWLISTED = "ARTICLE_NOT_ALLOWLISTED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    CREDENTIAL_UNSAFE = "CREDENTIAL_UNSAFE"
    CREDENTIAL_REFLECTION = "CREDENTIAL_REFLECTION"
    NETWORK_ENVIRONMENT_UNSAFE = "NETWORK_ENVIRONMENT_UNSAFE"
    DNS_FAILED = "DNS_FAILED"
    DNS_ADDRESS_REJECTED = "DNS_ADDRESS_REJECTED"
    TLS_CONTEXT_INVALID = "TLS_CONTEXT_INVALID"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "REQUEST_AMBIGUOUS"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    MIME_INVALID = "MIME_INVALID"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_IDENTITY_AMBIGUOUS = "PRODUCT_IDENTITY_AMBIGUOUS"
    PRODUCT_LISTING_MISMATCH = "PRODUCT_LISTING_MISMATCH"
    PRODUCT_IDENTITY_INVALID = "PRODUCT_IDENTITY_INVALID"
    IMAGE_INVALID = "IMAGE_INVALID"
    STORE_UNSAFE = "STORE_UNSAFE"
    STORE_CONFLICT = "STORE_CONFLICT"


class RakutenProductCaptureFailure(RuntimeError):
    """Sanitized refusal that never carries a secret, URL, or provider body."""

    __slots__ = ("_code", "_credentials_used")

    def __init__(
        self,
        code: RakutenProductCaptureFailureCode,
        *,
        credentials_used: bool = False,
    ) -> None:
        if (
            type(code) is not RakutenProductCaptureFailureCode
            or type(credentials_used) is not bool
        ):
            raise TypeError("invalid Rakuten product capture failure")
        self._code = code
        self._credentials_used = credentials_used
        super().__init__(code.value)

    @property
    def code(self) -> RakutenProductCaptureFailureCode:
        return self._code

    @property
    def credentials_used(self) -> bool:
        return self._credentials_used

    def __repr__(self) -> str:
        return f"RakutenProductCaptureFailure(code={self.code.value})"


def _fail(
    code: RakutenProductCaptureFailureCode = (
        RakutenProductCaptureFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise RakutenProductCaptureFailure(code) from None


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)


def _strict_json(raw: bytes, *, maximum: int) -> object:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= maximum
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except RakutenProductCaptureFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return value


def _read_tracked_file(repository_root: Path, relative: Path, maximum: int) -> bytes:
    target = repository_root / relative
    descriptor = -1
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        return b"".join(chunks)
    except RakutenProductCaptureFailure:
        raise
    except OSError:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class ProductCaptureTarget:
    product_id: str
    shop_code: str
    affiliate_ref: str
    media_asset_ref: str
    variants: tuple[str, ...]
    required_title_tokens: tuple[str, ...]
    product_kind_tokens: tuple[str, ...]
    forbidden_title_tokens: tuple[str, ...]
    jan: str | None
    fixed_item_code: str | None
    fixed_destination_url: str | None

    def __post_init__(self) -> None:
        if (
            _PRODUCT_ID.fullmatch(self.product_id) is None
            or _ITEM_CODE.fullmatch(f"{self.shop_code}:item") is None
            or not self.affiliate_ref.startswith("AFF-")
            or not self.media_asset_ref.startswith("MEDIA-")
            or not self.variants
            or not self.required_title_tokens
            or not self.product_kind_tokens
            or (
                self.fixed_item_code is not None
                and _ITEM_CODE.fullmatch(self.fixed_item_code) is None
            )
            or (self.jan is not None and _JAN.fullmatch(self.jan) is None)
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)


@dataclass(frozen=True, slots=True)
class ProductCapturePlan:
    """Exact final inventory plus the currently owner-bounded capture slice."""

    article_products: tuple[tuple[str, tuple[ProductCaptureTarget, ...]], ...]
    portfolio_article_products: tuple[tuple[str, tuple[str, ...]], ...]
    portfolio_product_ids: frozenset[str]
    portfolio_cta_placement_count: int

    def for_article(self, article_id: str) -> tuple[ProductCaptureTarget, ...]:
        if article_id not in _ARTICLE_IDS:
            _fail(RakutenProductCaptureFailureCode.ARTICLE_NOT_ALLOWLISTED)
        matches = [
            products
            for candidate, products in self.article_products
            if candidate == article_id
        ]
        if len(matches) != 1:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        return matches[0]

    @property
    def portfolio_product_count(self) -> int:
        return len(self.portfolio_product_ids)

    @property
    def portfolio_product_placement_count(self) -> int:
        return sum(len(products) for _article_id, products in self.portfolio_article_products)


def _tuple_text(value: object, *, maximum: int = 300) -> tuple[str, ...]:
    result = tuple(_text(item, maximum=maximum) for item in _list(value))
    if not result or len(result) != len(set(result)):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return result


def _load_final_portfolio_inventory(
    repository_root: Path,
) -> tuple[
    tuple[tuple[str, tuple[str, ...]], ...],
    frozenset[str],
    int,
]:
    """Load the exact 10-article/31-product/37-card/74-CTA contract.

    The owner-private capture adapter remains intentionally bounded to the five
    article packets that have structured capture metadata.  Loading a bounded
    slice must nevertheless prove that it belongs to the current final
    portfolio; otherwise the legacy 18-row registry could be mistaken for
    complete all-article coverage.
    """

    portfolio = _mapping(
        _strict_json(
            _read_tracked_file(
                repository_root, PORTFOLIO_RELATIVE_PATH, MAX_REGISTRY_BYTES
            ),
            maximum=MAX_REGISTRY_BYTES,
        )
    )
    policy = _mapping(portfolio.get("evidence_policy"))
    completion_gate = _mapping(policy.get("completion_gate"))
    cta_placements = _tuple_text(
        policy.get("verified_cta_placements"), maximum=80
    )
    if (
        portfolio.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V2"
        or portfolio.get("version") != "2.0.0"
        or portfolio.get("target_origin") != "https://kurashinoshirube.com"
        or cta_placements != ("product_card", "final_summary")
        or completion_gate
        != {
            "required_product_count": _FINAL_PORTFOLIO_PRODUCT_COUNT,
            "required_product_card_count": (
                _FINAL_PORTFOLIO_PRODUCT_PLACEMENT_COUNT
            ),
            "required_affiliate_cta_count": _FINAL_PORTFOLIO_CTA_PLACEMENT_COUNT,
            "required_product_state": "verified",
            "required_product_image_state": "verified",
            "maximum_neutral_product_images": 0,
            "maximum_manufacturer_fallback_ctas": 0,
        }
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)

    product_ids: set[str] = set()
    for raw_product in _list(portfolio.get("products")):
        product = _mapping(raw_product)
        product_id = _text(product.get("product_id"), maximum=160)
        if _PRODUCT_ID.fullmatch(product_id) is None or product_id in product_ids:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        product_ids.add(product_id)

    article_products: list[tuple[str, tuple[str, ...]]] = []
    observed_article_ids: set[str] = set()
    for raw_article in _list(portfolio.get("articles")):
        article = _mapping(raw_article)
        article_id = _text(article.get("article_id"), maximum=160)
        references = tuple(
            _text(item, maximum=160) for item in _list(article.get("product_ids"))
        )
        if (
            article_id in observed_article_ids
            or len(references) != len(set(references))
            or (article_id == "solota-vs-rakua-mini-plus") != (not references)
            or any(_PRODUCT_ID.fullmatch(product_id) is None for product_id in references)
            or not set(references) <= product_ids
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        observed_article_ids.add(article_id)
        article_products.append((article_id, references))

    placement_count = sum(len(products) for _article_id, products in article_products)
    referenced_product_ids = {
        product_id
        for _article_id, products in article_products
        for product_id in products
    }
    cta_placement_count = placement_count * len(cta_placements)
    if (
        tuple(article_id for article_id, _products in article_products)
        != _FINAL_PORTFOLIO_ARTICLE_IDS
        or len(product_ids) != _FINAL_PORTFOLIO_PRODUCT_COUNT
        or placement_count != _FINAL_PORTFOLIO_PRODUCT_PLACEMENT_COUNT
        or cta_placement_count != _FINAL_PORTFOLIO_CTA_PLACEMENT_COUNT
        or product_ids != referenced_product_ids
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return tuple(article_products), frozenset(product_ids), cta_placement_count


def load_product_capture_plan(repository_root: Path) -> ProductCapturePlan:
    """Cross-bind the final portfolio and its owner-bounded first-five slice."""

    if not repository_root.is_absolute():
        _fail()
    (
        portfolio_article_products,
        portfolio_product_ids,
        portfolio_cta_placement_count,
    ) = _load_final_portfolio_inventory(repository_root)
    portfolio_products_by_article = dict(portfolio_article_products)
    if len(portfolio_products_by_article) != len(portfolio_article_products):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    try:
        expected_capture_products_by_article = {
            article_id: portfolio_products_by_article[article_id]
            for article_id in _ARTICLE_IDS
        }
    except KeyError:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    expected_capture_product_ids = {
        product_id
        for product_ids in expected_capture_products_by_article.values()
        for product_id in product_ids
    }
    articles = _mapping(
        _strict_json(
            _read_tracked_file(
                repository_root, ARTICLES_RELATIVE_PATH, MAX_REGISTRY_BYTES
            ),
            maximum=MAX_REGISTRY_BYTES,
        )
    )
    sources = _mapping(
        _strict_json(
            _read_tracked_file(
                repository_root, SOURCE_REGISTRY_RELATIVE_PATH, MAX_REGISTRY_BYTES
            ),
            maximum=MAX_REGISTRY_BYTES,
        )
    )
    media = _mapping(
        _strict_json(
            _read_tracked_file(
                repository_root, MEDIA_REGISTRY_RELATIVE_PATH, MAX_REGISTRY_BYTES
            ),
            maximum=MAX_REGISTRY_BYTES,
        )
    )
    if (
        articles.get("schema") != "SELF_HOSTED_EDITORIAL_ARTICLE_COLLECTION_V1"
        or articles.get("story_id") != "ST-1704"
        or articles.get("publication_authority") != PUBLICATION_AUTHORITY
        or sources.get("schema") != "SELF_HOSTED_EDITORIAL_SOURCE_REGISTRY_V1"
        or sources.get("story_id") != "ST-1704"
        or sources.get("publication_authority") != PUBLICATION_AUTHORITY
        or media.get("schema") != "SELF_HOSTED_EDITORIAL_PRODUCT_MEDIA_REGISTRY_V1"
        or media.get("story_id") != "ST-1704"
        or media.get("publication_authority") != PUBLICATION_AUTHORITY
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)

    affiliates: dict[str, Mapping[str, object]] = {}
    for raw in _list(sources.get("affiliate_resources")):
        row = _mapping(raw)
        product_id = _text(row.get("product_id"), maximum=300)
        if product_id in affiliates:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        affiliates[product_id] = row
    assets: dict[str, Mapping[str, object]] = {}
    for raw in _list(media.get("assets")):
        row = _mapping(raw)
        product_id = _text(row.get("product_id"), maximum=300)
        if product_id in assets:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        assets[product_id] = row
    if (
        set(affiliates) != expected_capture_product_ids
        or set(assets) != expected_capture_product_ids
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)

    targets: dict[str, ProductCaptureTarget] = {}
    shop_codes = dict(_PRODUCT_SHOP_CODES)
    if (
        len(shop_codes) != len(_PRODUCT_SHOP_CODES)
        or set(shop_codes) != expected_capture_product_ids
        or not set(_FIXED_PRODUCT_ITEM_CODES) <= expected_capture_product_ids
    ):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    for product_id, asset in assets.items():
        affiliate = affiliates[product_id]
        identity = _mapping(asset.get("identity"))
        fixed_item_code = identity.get("item_code")
        if fixed_item_code is not None and type(fixed_item_code) is not str:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        jan = identity.get("jan")
        if jan is not None and type(jan) is not str:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        destination = affiliate.get("destination_url")
        if (
            affiliate.get("status") != "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE"
            or destination is not None
            or affiliate.get("evidence") is not None
            or affiliate.get("publication_blocker")
            != "PENDING_AFFILIATE_EVIDENCE"
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        selected_item_code = _FIXED_PRODUCT_ITEM_CODES.get(
            product_id,
            fixed_item_code,
        )
        if (
            fixed_item_code is not None
            and selected_item_code != fixed_item_code
            or selected_item_code is not None
            and not selected_item_code.startswith(f"{shop_codes[product_id]}:")
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        target = ProductCaptureTarget(
            product_id=product_id,
            shop_code=shop_codes[product_id],
            affiliate_ref=_text(affiliate.get("affiliate_ref"), maximum=300),
            media_asset_ref=_text(asset.get("media_asset_ref"), maximum=300),
            variants=_tuple_text(identity.get("allowed_variants")),
            required_title_tokens=_tuple_text(identity.get("required_title_tokens")),
            product_kind_tokens=_tuple_text(identity.get("product_kind_tokens")),
            forbidden_title_tokens=_tuple_text(identity.get("forbidden_title_tokens")),
            jan=jan,
            fixed_item_code=selected_item_code,
            fixed_destination_url=None,
        )
        if (
            asset.get("provider") != "RAKUTEN_ICHIBA_ITEM_SEARCH"
            or asset.get("required_width") != 128
            or asset.get("required_height") != 128
            or affiliate.get("destination_policy") != "DIRECT_RAKUTEN_AFFILIATE_URL"
            or affiliate.get("required_rel") != "sponsored nofollow"
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        targets[product_id] = target

    article_rows: list[tuple[str, tuple[ProductCaptureTarget, ...]]] = []
    observed_articles: set[str] = set()
    for raw in _list(articles.get("articles")):
        article = _mapping(raw)
        article_id_value = article.get("article_id")
        if article_id_value is None:
            continue
        article_id = _text(article_id_value, maximum=300)
        if article_id not in _ARTICLE_IDS or article_id in observed_articles:
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        observed_articles.add(article_id)
        render = _mapping(article.get("render_model"))
        product_rows: list[ProductCaptureTarget] = []
        observed_products: set[str] = set()
        for raw_card in _list(render.get("product_cards")):
            card = _mapping(raw_card)
            product_id = _text(card.get("product_id"), maximum=300)
            article_target = targets.get(product_id)
            if article_target is None or product_id in observed_products:
                _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
            if (
                card.get("affiliate_ref") != article_target.affiliate_ref
                or card.get("media_asset_ref") != article_target.media_asset_ref
            ):
                _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
            observed_products.add(product_id)
            product_rows.append(article_target)
        if (
            not product_rows
            or tuple(target.product_id for target in product_rows)
            != expected_capture_products_by_article[article_id]
        ):
            _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
        article_rows.append((article_id, tuple(product_rows)))
    if observed_articles != set(_ARTICLE_IDS):
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    return ProductCapturePlan(
        article_products=tuple(article_rows),
        portfolio_article_products=portfolio_article_products,
        portfolio_product_ids=portfolio_product_ids,
        portfolio_cta_placement_count=portfolio_cta_placement_count,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RakutenCredentials:
    application_id: str
    access_key: str
    affiliate_id: str

    def __post_init__(self) -> None:
        for value in (self.application_id, self.access_key, self.affiliate_id):
            if (
                type(value) is not str
                or not 1 <= len(value) <= 256
                or not value.isascii()
                or value != value.strip()
                or any(
                    ord(character) < 0x21 or ord(character) > 0x7E
                    for character in value
                )
            ):
                _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE)

    def __repr__(self) -> str:
        return "RakutenCredentials(<redacted>)"


def read_owner_credentials(repository_root: Path) -> RakutenCredentials:
    path = repository_root / OWNER_CREDENTIAL_RELATIVE_PATH
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNAVAILABLE)
    except OSError:
        _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_CREDENTIAL_BYTES
        ):
            _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE)
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE)
    finally:
        os.close(descriptor)
    document = _mapping(_strict_json(raw, maximum=MAX_CREDENTIAL_BYTES))
    if (
        set(document)
        != {
            "schema_version",
            "profile",
            "application_id",
            "access_key",
            "affiliate_id",
        }
        or document["schema_version"] != 1
        or document["profile"] != OWNER_CREDENTIAL_PROFILE
    ):
        _fail(RakutenProductCaptureFailureCode.CREDENTIAL_UNSAFE)
    return RakutenCredentials(
        _text(document["application_id"], maximum=256),
        _text(document["access_key"], maximum=256),
        _text(document["affiliate_id"], maximum=256),
    )


def require_clean_capture_environment(
    environment: Mapping[str, str] | None = None,
) -> None:
    values = os.environ if environment is None else environment
    if any(key in values for key in _FORBIDDEN_ENVIRONMENT):
        _fail(RakutenProductCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE)


@runtime_checkable
class RakutenHttpsResponse(Protocol):
    status: int

    def getheaders(self) -> list[tuple[str, str]]: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class RakutenHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(self, method: str, path: str, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> RakutenHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class RakutenHttpsConnectionFactory(Protocol):
    @property
    def credentials_used(self) -> bool: ...

    def mark_credentials_used(self) -> None: ...

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenHttpsConnection: ...


@dataclass(frozen=True, slots=True)
class _ResolvedAddress:
    family: int
    socket_type: int
    protocol: int
    socket_address: tuple[str, int] | tuple[str, int, int, int]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


def _require_peer(candidate: _ResolvedAddress, peer: object) -> None:
    if type(peer) is not tuple:
        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
    values = cast(tuple[object, ...], peer)
    if (
        len(values) not in {2, 4}
        or type(values[1]) is not int
        or values[1] != 443
        or (candidate.family == socket.AF_INET and len(values) != 2)
        or (candidate.family == socket.AF_INET6 and len(values) != 4)
    ):
        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
    if _public_ip(values[0], family=candidate.family) != candidate.ip:
        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)


def _public_ip(
    value: object, *, family: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    if (
        (family == socket.AF_INET and type(address) is not ipaddress.IPv4Address)
        or (family == socket.AF_INET6 and type(address) is not ipaddress.IPv6Address)
        or not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or getattr(address, "is_site_local", False)
        or (type(address) is ipaddress.IPv6Address and address.ipv4_mapped is not None)
    ):
        _fail(RakutenProductCaptureFailureCode.DNS_ADDRESS_REJECTED)
    return address


def _resolve_public_addresses(host: str) -> tuple[_ResolvedAddress, ...]:
    if host not in {RAKUTEN_API_HOST, RAKUTEN_IMAGE_HOST}:
        _fail(RakutenProductCaptureFailureCode.CONTRACT_INVALID)
    try:
        rows = socket.getaddrinfo(
            host,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
            flags=0,
        )
    except OSError, UnicodeError, ValueError, TypeError:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    if type(rows) is not list or not rows or len(rows) > 64:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    results: list[_ResolvedAddress] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 5 or type(row[4]) is not tuple:
            _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
        family, socket_type, protocol, canonical_name, raw_address = row
        if (
            family not in {socket.AF_INET, socket.AF_INET6}
            or socket_type != socket.SOCK_STREAM
            or protocol != socket.IPPROTO_TCP
            or type(canonical_name) is not str
        ):
            _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
        values = cast(tuple[object, ...], raw_address)
        if family == socket.AF_INET:
            if len(values) != 2 or values[1] != 443:
                _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
            address: tuple[str, int] | tuple[str, int, int, int] = (
                str(_public_ip(values[0], family=family)),
                443,
            )
        else:
            if len(values) != 4 or values[1:] != (443, 0, 0):
                _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
            address = (str(_public_ip(values[0], family=family)), 443, 0, 0)
        candidate = _ResolvedAddress(
            cast(int, family),
            cast(int, socket_type),
            protocol,
            address,
            _public_ip(address[0], family=cast(int, family)),
        )
        if candidate not in results:
            results.append(candidate)
    if not results:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    return tuple(results)


@dataclass(slots=True)
class _PinnedConnector:
    host: str
    candidate: _ResolvedAddress
    attempted: bool = False

    def __call__(
        self,
        address: tuple[str, int],
        timeout: object,
        source_address: tuple[str, int] | None,
    ) -> socket.socket:
        if (
            self.attempted
            or address != (self.host, 443)
            or timeout != CONNECT_TIMEOUT_SECONDS
            or source_address is not None
        ):
            _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
        self.attempted = True
        connection = socket.socket(
            self.candidate.family, self.candidate.socket_type, self.candidate.protocol
        )
        try:
            connection.settimeout(CONNECT_TIMEOUT_SECONDS)
            connection.connect(self.candidate.socket_address)
            _require_peer(self.candidate, connection.getpeername())
            return connection
        except BaseException:
            connection.close()
            raise


@final
@dataclass(slots=True)
class _OwnerRequestPacer:
    path: Path
    clock_ns: Callable[[], int] = time.monotonic_ns
    sleeper: Callable[[float], None] = time.sleep

    def acquire(self) -> int:
        descriptor = -1
        leased = False
        try:
            descriptor = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                PRIVATE_FILE_MODE,
            )
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
            observed_file = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed_file.st_mode)
                or observed_file.st_uid != os.getuid()
                or stat.S_IMODE(observed_file.st_mode) != PRIVATE_FILE_MODE
                or observed_file.st_nlink != 1
                or observed_file.st_size > 64
            ):
                _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw = os.read(descriptor, 65)
            if len(raw) > 64:
                _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
            previous: int | None = None
            if raw:
                if re.fullmatch(rb"(?:0|[1-9][0-9]{0,31})\n", raw) is None:
                    _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
                previous = int(raw[:-1])
            observed = self.clock_ns()
            if type(observed) is not int or observed < 0:
                _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
            interval_ns = int(MINIMUM_REQUEST_INTERVAL_SECONDS * 1_000_000_000)
            if previous is not None and observed >= previous:
                remaining_ns = interval_ns - (observed - previous)
                if remaining_ns > 0:
                    self.sleeper(remaining_ns / 1_000_000_000)
                    observed = self.clock_ns()
                    if (
                        type(observed) is not int
                        or observed < previous
                        or observed - previous < interval_ns
                    ):
                        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
            leased = True
            return descriptor
        except RakutenProductCaptureFailure:
            raise
        except OSError, ValueError, OverflowError:
            _fail(RakutenProductCaptureFailureCode.STORE_CONFLICT)
        finally:
            if descriptor >= 0 and not leased:
                os.close(descriptor)

    def release(self, descriptor: int) -> None:
        if type(descriptor) is not int or descriptor < 0:
            _fail(RakutenProductCaptureFailureCode.STORE_CONFLICT)
        try:
            observed = self.clock_ns()
            if type(observed) is not int or observed < 0:
                _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
            material = f"{observed}\n".encode("ascii")
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            if os.write(descriptor, material) != len(material):
                _fail(RakutenProductCaptureFailureCode.STORE_CONFLICT)
            os.fsync(descriptor)
        except RakutenProductCaptureFailure:
            raise
        except OSError, ValueError, OverflowError:
            _fail(RakutenProductCaptureFailureCode.STORE_CONFLICT)
        finally:
            os.close(descriptor)


@final
class _SystemConnection:
    __slots__ = (
        "_attempted",
        "_candidates",
        "_connection",
        "_host",
        "_pacer",
        "_tls_context",
    )

    def __init__(
        self,
        *,
        host: str,
        candidates: tuple[_ResolvedAddress, ...],
        pacer: _OwnerRequestPacer,
        tls_context: ssl.SSLContext,
    ) -> None:
        self._attempted = False
        self._candidates = candidates
        self._connection: http.client.HTTPSConnection | None = None
        self._host = host
        self._pacer = pacer
        self._tls_context = tls_context

    def connect(self) -> None:
        if self._attempted:
            _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
        self._attempted = True
        for candidate in self._candidates:
            connection: http.client.HTTPSConnection | None = None
            try:
                connection = http.client.HTTPSConnection(
                    host=self._host,
                    port=443,
                    timeout=CONNECT_TIMEOUT_SECONDS,
                    context=self._tls_context,
                )
                setattr(
                    connection,
                    "_create_connection",
                    _PinnedConnector(self._host, candidate),
                )
                if getattr(connection, "_tunnel_host", None) is not None:
                    _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
                connection.connect()
                if connection.sock is None:
                    raise OSError
                _require_peer(candidate, connection.sock.getpeername())
            except BaseException:
                if connection is not None:
                    try:
                        connection.close()
                    except BaseException:
                        pass
                continue
            self._connection = connection
            return
        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)

    def set_read_timeout(self, seconds: int) -> None:
        if (
            self._connection is None
            or self._connection.sock is None
            or seconds != READ_TIMEOUT_SECONDS
        ):
            _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
        self._connection.sock.settimeout(seconds)

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        if self._connection is None:
            _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
        pacing_lease = self._pacer.acquire()
        try:
            self._connection.request(method, path, body=None, headers=headers)
        finally:
            self._pacer.release(pacing_lease)

    def getresponse(self) -> RakutenHttpsResponse:
        if self._connection is None:
            _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
        return cast(RakutenHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()


@final
class SystemRakutenHttpsConnectionFactory:
    __slots__ = ("_credentials_used", "_pacer")

    def __init__(self, repository_root: Path) -> None:
        self._credentials_used = False
        if not repository_root.is_absolute():
            _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
        self._pacer = _OwnerRequestPacer(
            _rakuten_directory(repository_root) / REQUEST_PACING_FILE
        )

    @property
    def credentials_used(self) -> bool:
        return self._credentials_used

    def mark_credentials_used(self) -> None:
        self._credentials_used = True

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenHttpsConnection:
        if (
            host not in {RAKUTEN_API_HOST, RAKUTEN_IMAGE_HOST}
            or port != 443
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(RakutenProductCaptureFailureCode.TLS_CONTEXT_INVALID)
        return _SystemConnection(
            host=host,
            candidates=_resolve_public_addresses(host),
            pacer=self._pacer,
            tls_context=tls_context,
        )


def _response_headers(response: RakutenHttpsResponse) -> dict[str, str]:
    result: dict[str, str] = {}
    relevant = {
        "content-encoding",
        "content-length",
        "content-type",
        "location",
        "transfer-encoding",
    }
    try:
        rows = response.getheaders()
    except BaseException:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    if type(rows) is not list:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    for key, value in rows:
        if type(key) is not str or type(value) is not str:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        normalized = key.casefold()
        if normalized in relevant:
            if normalized in result:
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
            result[normalized] = value
    return result


def _bounded_body(
    response: RakutenHttpsResponse, headers: Mapping[str, str], *, maximum: int
) -> bytes:
    raw_length = headers.get("content-length")
    transfer = headers.get("transfer-encoding")
    expected: int | None
    if raw_length is not None:
        if _CONTENT_LENGTH.fullmatch(raw_length) is None or transfer is not None:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        expected = int(raw_length)
        if expected > maximum:
            _fail(RakutenProductCaptureFailureCode.BODY_TOO_LARGE)
    else:
        expected = None
        if transfer is not None and transfer.casefold() != "chunked":
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    chunks: list[bytes] = []
    observed = 0
    while True:
        try:
            chunk = response.read(min(65_536, maximum + 1 - observed))
        except BaseException:
            _fail(RakutenProductCaptureFailureCode.REQUEST_AMBIGUOUS)
        if type(chunk) is not bytes:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        if not chunk:
            break
        chunks.append(chunk)
        observed += len(chunk)
        if observed > maximum:
            _fail(RakutenProductCaptureFailureCode.BODY_TOO_LARGE)
    if expected is not None and observed != expected:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    if observed < 1:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    return b"".join(chunks)


def _fetch(
    *,
    host: str,
    path: str,
    headers: dict[str, str],
    expected_mime: re.Pattern[str],
    maximum: int,
    connection_factory: RakutenHttpsConnectionFactory,
) -> bytes:
    require_clean_capture_environment()
    try:
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except OSError, ssl.SSLError, ValueError:
        _fail(RakutenProductCaptureFailureCode.TLS_CONTEXT_INVALID)
    connection: RakutenHttpsConnection | None = None
    started = False
    try:
        connection = connection_factory.open(
            host=host,
            port=443,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            tls_context=context,
        )
        connection.connect()
        connection.set_read_timeout(READ_TIMEOUT_SECONDS)
        started = True
        if host == RAKUTEN_API_HOST:
            connection_factory.mark_credentials_used()
        connection.request("GET", path, headers)
        response = connection.getresponse()
        response_headers = _response_headers(response)
        content_type = response_headers.get("content-type")
        if (
            response.status != 200
            or "location" in response_headers
            or response_headers.get("content-encoding") not in {None, "identity"}
            or type(content_type) is not str
            or expected_mime.fullmatch(content_type) is None
        ):
            _fail(
                RakutenProductCaptureFailureCode.MIME_INVALID
                if response.status == 200
                else RakutenProductCaptureFailureCode.RESPONSE_INVALID
            )
        return _bounded_body(response, response_headers, maximum=maximum)
    except RakutenProductCaptureFailure:
        raise
    except socket.gaierror:
        _fail(RakutenProductCaptureFailureCode.DNS_FAILED)
    except ssl.SSLError:
        _fail(RakutenProductCaptureFailureCode.CONNECTION_FAILED)
    except TimeoutError, socket.timeout, http.client.HTTPException, OSError:
        _fail(
            RakutenProductCaptureFailureCode.REQUEST_AMBIGUOUS
            if started
            else RakutenProductCaptureFailureCode.CONNECTION_FAILED
        )
    except BaseException:
        _fail(
            RakutenProductCaptureFailureCode.REQUEST_AMBIGUOUS
            if started
            else RakutenProductCaptureFailureCode.CONNECTION_FAILED
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except BaseException:
                pass


_IDENTITY_TOKEN_SEPARATOR = re.compile(r"[\s+*・_.\-/＆&]+")
_IDENTITY_TOKEN_SEPARATOR_PATTERN: Final = r"[\s+*・_.\-/＆&]*"


def _provider_title_has_token(title: str, token: str) -> bool:
    """Match one provider-returned identity token without substring models.

    Rakuten shops vary harmless separators in model numbers (for example
    ``K10+ Pro Combo`` and ``K10+ProCombo``). NFKC plus a bounded separator
    pattern accepts those display differences while the ASCII boundaries keep
    ``F155260X`` from satisfying ``F155260``.
    """

    if type(title) is not str or type(token) is not str or not title or not token:
        return False
    normalized_title = unicodedata.normalize("NFKC", title).casefold()
    normalized_token = unicodedata.normalize("NFKC", token).casefold()
    components = tuple(
        component
        for component in _IDENTITY_TOKEN_SEPARATOR.split(normalized_token)
        if component
    )
    if not components:
        return False
    token_pattern = _IDENTITY_TOKEN_SEPARATOR_PATTERN.join(
        re.escape(component) for component in components
    )
    prefix = (
        r"(?<![a-z0-9])"
        if re.fullmatch(r"[a-z0-9]", components[0][0], re.ASCII)
        else ""
    )
    suffix = (
        r"(?![a-z0-9])"
        if re.fullmatch(r"[a-z0-9]", components[-1][-1], re.ASCII)
        else ""
    )
    return (
        re.search(prefix + token_pattern + suffix, normalized_title)
        is not None
    )


def _provider_variant(title: str, variants: tuple[str, ...]) -> str | None:
    """Return the one configured model proven present in provider title data."""

    matches = tuple(
        variant for variant in variants if _provider_title_has_token(title, variant)
    )
    return matches[0] if len(matches) == 1 else None


def _provider_jan(row: Mapping[str, object]) -> str | None:
    """Read only a provider-returned JAN; never fill it from the registry."""

    value = row.get("jan")
    if value is None or value == "":
        return None
    if type(value) is not str or _JAN.fullmatch(value) is None:
        return None
    return value


def _decode_provider_response(raw: bytes) -> Mapping[str, object]:
    try:
        value = _strict_json(raw, maximum=MAX_RESPONSE_BYTES)
        return _mapping(value)
    except RakutenProductCaptureFailure as exc:
        if exc.code is RakutenProductCaptureFailureCode.CONTRACT_INVALID:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        raise


def _item_rows(
    raw: bytes, *, expected_fields: frozenset[str], expected_hits: int
) -> list[Mapping[str, object]]:
    if not expected_fields or expected_hits not in {1, 30}:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    try:
        document = _decode_provider_response(raw)
        if not document:
            return []
        rows: list[Mapping[str, object]] = []
        aliases = {"items", "Items"} & set(document)
        if set(document) == {"Items"}:
            raw_rows = document["Items"]
        elif len(aliases) == 1:
            alias = aliases.pop()
            expected_root = _RESPONSE_SUMMARY_FIELDS | {alias}
            if "carrier" in document:
                expected_root = expected_root | {"carrier"}
            if frozenset(document) != expected_root:
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
            if "carrier" in document and (
                type(document["carrier"]) is not int or document["carrier"] != 0
            ):
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
            raw_rows = document[alias]
        else:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        provider_rows = _list(raw_rows)
        if len(provider_rows) > expected_hits:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        if set(document) != {"Items"}:
            summary = tuple(document[field] for field in _RESPONSE_SUMMARY_FIELDS)
            if any(type(value) is not int for value in summary):
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
            count = cast(int, document["count"])
            page = cast(int, document["page"])
            first = cast(int, document["first"])
            last = cast(int, document["last"])
            hits = cast(int, document["hits"])
            page_count = cast(int, document["pageCount"])
            returned = len(provider_rows)
            if (
                page != 1
                or hits != expected_hits
                or (returned == 0 and (count, first, last, page_count) != (0, 0, 0, 0))
                or (
                    returned > 0
                    and (
                        count < returned
                        or first != 1
                        or last != returned
                        or page_count != min((count + hits - 1) // hits, 100)
                    )
                )
            ):
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        for raw_row in provider_rows:
            row = _mapping(raw_row)
            if frozenset(row) != expected_fields:
                _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
            rows.append(row)
        return rows
    except RakutenProductCaptureFailure as exc:
        if exc.code is RakutenProductCaptureFailureCode.CONTRACT_INVALID:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        raise


def _normalized_reflection_candidates(value: str) -> tuple[str, str]:
    try:
        normalized = unicodedata.normalize("NFKC", value)
        decoded = unicodedata.normalize(
            "NFKC", unquote(normalized, encoding="utf-8", errors="strict")
        )
    except UnicodeError:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    return normalized, decoded


def _reject_credential_reflection(
    rows: list[Mapping[str, object]], credentials: RakutenCredentials
) -> None:
    link_fields = frozenset({"affiliateUrl", "itemUrl"})
    for row in rows:
        for field, value in row.items():
            values: list[object]
            if type(value) is str:
                values = [value]
            elif type(value) is list:
                values = cast(list[object], value)
            else:
                continue
            for member in values:
                if type(member) is not str:
                    continue
                candidates = _normalized_reflection_candidates(member)
                if any(credentials.access_key in candidate for candidate in candidates):
                    _fail(RakutenProductCaptureFailureCode.CREDENTIAL_REFLECTION)
                if field not in link_fields and any(
                    credential in candidate
                    for credential in (
                        credentials.application_id,
                        credentials.affiliate_id,
                    )
                    for candidate in candidates
                ):
                    _fail(RakutenProductCaptureFailureCode.CREDENTIAL_REFLECTION)


def _valid_identity(target: ProductCaptureTarget, row: Mapping[str, object]) -> bool:
    item_code = row.get("itemCode")
    item_name = row.get("itemName")
    raw_provider_jan = row.get("jan")
    provider_jan = _provider_jan(row)
    return bool(
        type(item_code) is str
        and _ITEM_CODE.fullmatch(item_code) is not None
        and type(item_name) is str
        and (
            raw_provider_jan is None
            or raw_provider_jan == ""
            or provider_jan is not None
        )
        and _provider_variant(item_name, target.variants) is not None
        and (target.jan is None or provider_jan == target.jan)
        and all(
            _provider_title_has_token(item_name, token)
            for token in target.required_title_tokens
        )
        and any(
            _provider_title_has_token(item_name, token)
            for token in target.product_kind_tokens
        )
        and not any(
            token.casefold() in item_name.casefold()
            for token in target.forbidden_title_tokens
        )
        and not any(token in item_name for token in _DISCOVERY_ACCESSORY_TOKENS)
        and not (
            target.product_id in _PORTABLE_POWER_PRODUCT_IDS
            and any(
                token in item_name.casefold() for token in _PORTABLE_POWER_BUNDLE_TOKENS
            )
        )
    )


def _api_path(
    credentials: RakutenCredentials,
    *,
    selector_name: str,
    selector_value: str,
    affiliate: bool,
    elements: tuple[str, ...],
    hits: int,
    shop_code: str | None = None,
) -> str:
    if (
        selector_name not in {"keyword", "itemCode"}
        or hits not in {1, 30}
        or (selector_name == "keyword" and shop_code is None)
        or (selector_name == "itemCode" and shop_code is not None)
        or (shop_code is not None and _ITEM_CODE.fullmatch(f"{shop_code}:item") is None)
    ):
        _fail()
    pairs = [("applicationId", credentials.application_id)]
    if affiliate:
        pairs.append(("affiliateId", credentials.affiliate_id))
    if shop_code is not None:
        pairs.append(("shopCode", shop_code))
    pairs.extend(
        [
            (selector_name, selector_value),
            ("hits", str(hits)),
            ("page", "1"),
            ("format", "json"),
            ("formatVersion", "2"),
            ("imageFlag", "1"),
            ("elements", ",".join(elements)),
        ]
    )
    return f"{RAKUTEN_API_PATH}?{urlencode(pairs, doseq=False, safe='')}"


def _api_headers(credentials: RakutenCredentials) -> dict[str, str]:
    return dict(
        (
            ("Accept", "application/json"),
            ("Accept-Encoding", "identity"),
            ("Connection", "close"),
            ("Host", RAKUTEN_API_HOST),
            ("User-Agent", CAPTURE_USER_AGENT),
            ("accessKey", credentials.access_key),
        )
    )


def _api_request(
    credentials: RakutenCredentials,
    *,
    selector_name: str,
    selector_value: str,
    affiliate: bool,
    elements: tuple[str, ...],
    hits: int,
    connection_factory: RakutenHttpsConnectionFactory,
    shop_code: str | None = None,
) -> bytes:
    return _fetch(
        host=RAKUTEN_API_HOST,
        path=_api_path(
            credentials,
            selector_name=selector_name,
            selector_value=selector_value,
            affiliate=affiliate,
            elements=elements,
            hits=hits,
            shop_code=shop_code,
        ),
        headers=_api_headers(credentials),
        expected_mime=_JSON_CONTENT_TYPE,
        maximum=MAX_RESPONSE_BYTES,
        connection_factory=connection_factory,
    )


def _discover_item_code(
    target: ProductCaptureTarget,
    credentials: RakutenCredentials,
    connection_factory: RakutenHttpsConnectionFactory,
) -> tuple[str, str, int]:
    if target.fixed_item_code is not None:
        return target.fixed_item_code, target.variants[0], 0
    matched_variants: dict[str, str] = {}
    for variant in target.variants:
        raw = _api_request(
            credentials,
            selector_name="keyword",
            selector_value=variant,
            affiliate=False,
            elements=_DISCOVERY_ELEMENTS,
            hits=30,
            connection_factory=connection_factory,
            shop_code=target.shop_code,
        )
        rows = _item_rows(
            raw,
            expected_fields=frozenset(_DISCOVERY_ELEMENTS),
            expected_hits=30,
        )
        _reject_credential_reflection(rows, credentials)
        matches = [
            row
            for row in rows
            if row.get("shopCode") == target.shop_code and _valid_identity(target, row)
        ]
        unique_codes = sorted({cast(str, row["itemCode"]) for row in matches})
        if len(unique_codes) > 1:
            _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS)
        if len(unique_codes) == 1:
            matched_variants.setdefault(unique_codes[0], variant)
    if len(matched_variants) > 1:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS)
    if len(matched_variants) == 1:
        item_code, variant = next(iter(matched_variants.items()))
        return item_code, variant, len(target.variants)
    _fail(RakutenProductCaptureFailureCode.PRODUCT_NOT_FOUND)


def _validate_provider_row_structure(
    row: Mapping[str, object], *, affiliate: bool
) -> None:
    """Validate provider-controlled structure before semantic fallback.

    A valid but different listing may safely become a per-product fallback.
    Malformed URLs, fields, image identities, and PC/mobile disagreement must
    remain hard capture failures and therefore run before title/model/JAN
    matching.
    """

    item_code = row.get("itemCode")
    if type(item_code) is not str or _ITEM_CODE.fullmatch(item_code) is None:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    try:
        _text(row.get("itemName"), maximum=1000)
        item_url = _text(row.get("itemUrl"), maximum=4096)
    except RakutenProductCaptureFailure as exc:
        if exc.code is RakutenProductCaptureFailureCode.CONTRACT_INVALID:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        raise
    _image_urls(row)
    if not affiliate:
        try:
            source_url = canonical_rakuten_provider_item_url(item_url)
        except EditorialPilotFailure:
            _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
        source_parts = urlsplit(source_url).path.strip("/").split("/")
        item_parts = item_code.split(":", 1)
        if len(source_parts) != 2 or source_parts[0] != item_parts[0]:
            _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
        return
    affiliate_url = row.get("affiliateUrl")
    if type(affiliate_url) is not str or affiliate_url != item_url:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    try:
        query = parse_qs(
            urlsplit(affiliate_url).query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
        if set(query) != {"m", "pc", "rafcid"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise ValueError
        require_rakuten_affiliate_url(
            affiliate_url,
            item_url=query["pc"][0],
            item_code=item_code,
        )
    except (EditorialPilotFailure, ValueError):
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)


def _one_exact_row(
    raw: bytes,
    target: ProductCaptureTarget,
    item_code: str,
    credentials: RakutenCredentials,
    *,
    affiliate: bool,
) -> Mapping[str, object]:
    expected_fields = frozenset(
        _AFFILIATE_REQUEST_ELEMENTS if affiliate else _REQUEST_ELEMENTS
    )
    rows = _item_rows(raw, expected_fields=expected_fields, expected_hits=1)
    _reject_credential_reflection(rows, credentials)
    for candidate in rows:
        _validate_provider_row_structure(candidate, affiliate=affiliate)
    matches = [row for row in rows if row.get("itemCode") == item_code]
    if len(matches) != 1:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS)
    row = matches[0]
    if (
        not item_code.startswith(f"{target.shop_code}:")
        or (affiliate and "affiliateUrl" not in row)
    ):
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    if not _valid_identity(target, row):
        _fail(RakutenProductCaptureFailureCode.PRODUCT_LISTING_MISMATCH)
    return row


def _image_urls(row: Mapping[str, object]) -> tuple[str, ...]:
    urls = _list(row.get("mediumImageUrls"))
    if not 1 <= len(urls) <= MAX_IMAGE_CANDIDATES:
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    validated: list[str] = []
    for value in urls:
        if type(value) is not str:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != RAKUTEN_IMAGE_HOST
            or parsed.hostname != RAKUTEN_IMAGE_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.fragment
            or parsed.query != "_ex=128x128"
            or not parsed.path.startswith("/")
            or value in validated
        ):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        validated.append(value)
    return tuple(validated)


def _png_scanline_layout(
    width: int, height: int, bit_depth: int, color_type: int, interlace: int
) -> tuple[tuple[int, int, int], ...]:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    if interlace == 0:
        return ((width, height, (width * bits_per_pixel + 7) // 8),)
    passes = (
        (0, 0, 8, 8),
        (4, 0, 8, 8),
        (0, 4, 4, 8),
        (2, 0, 4, 4),
        (0, 2, 2, 4),
        (1, 0, 2, 2),
        (0, 1, 1, 2),
    )
    layout: list[tuple[int, int, int]] = []
    for start_x, start_y, step_x, step_y in passes:
        pass_width = 0 if width <= start_x else (width - start_x + step_x - 1) // step_x
        pass_height = (
            0 if height <= start_y else (height - start_y + step_y - 1) // step_y
        )
        if pass_width and pass_height:
            layout.append(
                (
                    pass_width,
                    pass_height,
                    (pass_width * bits_per_pixel + 7) // 8,
                )
            )
    return tuple(layout)


def _validate_png_pixels(
    compressed: bytes,
    *,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
    interlace: int,
    palette_entries: int | None,
) -> None:
    layout = _png_scanline_layout(width, height, bit_depth, color_type, interlace)
    expected = sum(rows * (row_bytes + 1) for _width, rows, row_bytes in layout)
    if (
        not compressed
        or not 1 <= expected <= MAX_IMAGE_BYTES
        or (
            color_type == 3
            and (
                type(palette_entries) is not int
                or not 1 <= palette_entries <= 1 << bit_depth
            )
        )
    ):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(compressed, expected + 1)
    except zlib.error:
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    if (
        len(decoded) != expected
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    decoded_offset = 0
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    filter_bytes_per_pixel = max(1, (channels * bit_depth + 7) // 8)
    for pass_width, rows, row_bytes in layout:
        previous = bytes(row_bytes)
        for _row in range(rows):
            filter_type = decoded[decoded_offset]
            if filter_type > 4:
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            encoded = decoded[decoded_offset + 1 : decoded_offset + 1 + row_bytes]
            decoded_offset += row_bytes + 1
            if color_type != 3:
                continue
            reconstructed = bytearray(row_bytes)
            for index, value in enumerate(encoded):
                left = (
                    reconstructed[index - filter_bytes_per_pixel]
                    if index >= filter_bytes_per_pixel
                    else 0
                )
                up = previous[index]
                upper_left = (
                    previous[index - filter_bytes_per_pixel]
                    if index >= filter_bytes_per_pixel
                    else 0
                )
                if filter_type == 0:
                    predictor = 0
                elif filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left + up) // 2
                else:
                    estimate = left + up - upper_left
                    distances = (
                        abs(estimate - left),
                        abs(estimate - up),
                        abs(estimate - upper_left),
                    )
                    predictor = (left, up, upper_left)[distances.index(min(distances))]
                reconstructed[index] = (value + predictor) & 0xFF
            entries = cast(int, palette_entries)
            mask = (1 << bit_depth) - 1
            for pixel in range(pass_width):
                bit_offset = pixel * bit_depth
                shift = 8 - bit_depth - (bit_offset % 8)
                palette_index = (reconstructed[bit_offset // 8] >> shift) & mask
                if palette_index >= entries:
                    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            previous = bytes(reconstructed)
    if decoded_offset != len(decoded):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    offset = 8
    image_header: tuple[int, int, int, int, int] | None = None
    compressed = bytearray()
    idat_closed = False
    saw_idat = False
    palette_entries: int | None = None
    while offset + 12 <= len(raw):
        length = int.from_bytes(raw[offset : offset + 4], "big")
        chunk_type = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if (
            length > MAX_IMAGE_BYTES
            or end > len(raw)
            or any(
                not (65 <= value <= 90 or 97 <= value <= 122) for value in chunk_type
            )
            or chunk_type[2] & 0x20
        ):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        data = raw[offset + 8 : offset + 8 + length]
        expected_crc = int.from_bytes(raw[offset + 8 + length : end], "big")
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        if chunk_type == b"IHDR":
            if offset != 8 or length != 13 or image_header is not None:
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            width = int.from_bytes(data[0:4], "big")
            height = int.from_bytes(data[4:8], "big")
            bit_depth = data[8]
            color_type = data[9]
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                (width, height) != (128, 128)
                or color_type not in valid_depths
                or bit_depth not in valid_depths[color_type]
                or data[10:12] != b"\x00\x00"
                or data[12] not in {0, 1}
            ):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            image_header = (width, height, bit_depth, color_type, data[12])
        elif chunk_type == b"PLTE":
            if (
                image_header is None
                or saw_idat
                or palette_entries is not None
                or image_header[3] in {0, 4}
                or not 3 <= length <= 768
                or length % 3 != 0
                or (image_header[3] == 3 and length > 3 * (1 << image_header[2]))
            ):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            palette_entries = length // 3
        elif chunk_type == b"IDAT":
            if (
                image_header is None
                or idat_closed
                or (image_header[3] == 3 and palette_entries is None)
            ):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            saw_idat = True
            if len(compressed) + len(data) > MAX_IMAGE_BYTES:
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            compressed.extend(data)
        elif chunk_type == b"IEND":
            if length != 0 or image_header is None or not compressed or end != len(raw):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            width, height, bit_depth, color_type, interlace = image_header
            _validate_png_pixels(
                bytes(compressed),
                width=width,
                height=height,
                bit_depth=bit_depth,
                color_type=color_type,
                interlace=interlace,
                palette_entries=palette_entries,
            )
            return width, height
        elif image_header is None:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        elif not chunk_type[0] & 0x20:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        elif saw_idat:
            idat_closed = True
        offset = end
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _gif_sub_blocks(raw: bytes, offset: int) -> tuple[bytes, int]:
    chunks: list[bytes] = []
    while offset < len(raw):
        length = raw[offset]
        offset += 1
        if length == 0:
            return b"".join(chunks), offset
        if offset + length > len(raw):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        chunks.append(raw[offset : offset + length])
        offset += length
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _validate_gif_lzw(
    data: bytes,
    *,
    minimum_code_size: int,
    expected_pixels: int,
    palette_entries: int,
) -> None:
    if (
        not data
        or not 2 <= minimum_code_size <= 8
        or not 1 <= expected_pixels <= MAX_IMAGE_BYTES
        or not 2 <= palette_entries <= 256
    ):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    clear_code = 1 << minimum_code_size
    end_code = clear_code + 1
    table: dict[int, bytes] = {}
    code_size = minimum_code_size + 1
    next_code = end_code + 1
    previous: bytes | None = None
    bit_offset = 0
    decoded_pixels = 0
    saw_clear = False

    def reset() -> None:
        nonlocal table, code_size, next_code, previous
        table = {index: bytes((index,)) for index in range(clear_code)}
        code_size = minimum_code_size + 1
        next_code = end_code + 1
        previous = None

    reset()
    while bit_offset + code_size <= len(data) * 8:
        byte_offset = bit_offset // 8
        shift = bit_offset % 8
        window = int.from_bytes(data[byte_offset : byte_offset + 3], "little")
        code = (window >> shift) & ((1 << code_size) - 1)
        bit_offset += code_size
        if code == clear_code:
            reset()
            saw_clear = True
            continue
        if not saw_clear:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        if code == end_code:
            if decoded_pixels != expected_pixels:
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            return
        if previous is None:
            entry = table.get(code)
            if entry is None:
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        else:
            entry = table.get(code)
            if entry is None:
                if code != next_code:
                    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
                entry = previous + previous[:1]
            if next_code < 4096:
                table[next_code] = previous + entry[:1]
                next_code += 1
                if next_code == 1 << code_size and code_size < 12:
                    code_size += 1
        if any(index >= palette_entries for index in entry):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        decoded_pixels += len(entry)
        if decoded_pixels > expected_pixels:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        previous = entry
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _gif_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith((b"GIF87a", b"GIF89a")) or len(raw) < 14:
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    width = int.from_bytes(raw[6:8], "little")
    height = int.from_bytes(raw[8:10], "little")
    if (width, height) != (128, 128):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    packed = raw[10]
    global_entries = 1 << ((packed & 0x07) + 1) if packed & 0x80 else 0
    offset = 13 + (3 * global_entries)
    if offset > len(raw):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    saw_image = False
    while offset < len(raw):
        introducer = raw[offset]
        offset += 1
        if introducer == 0x3B:
            if not saw_image or offset != len(raw):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            return width, height
        if introducer == 0x21:
            if offset >= len(raw):
                _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
            offset += 1
            _extension, offset = _gif_sub_blocks(raw, offset)
            continue
        if introducer != 0x2C or offset + 9 > len(raw):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        descriptor = raw[offset : offset + 9]
        offset += 9
        left = int.from_bytes(descriptor[0:2], "little")
        top = int.from_bytes(descriptor[2:4], "little")
        image_width = int.from_bytes(descriptor[4:6], "little")
        image_height = int.from_bytes(descriptor[6:8], "little")
        local_packed = descriptor[8]
        if (
            image_width < 1
            or image_height < 1
            or left + image_width > width
            or top + image_height > height
            or local_packed & 0x18
        ):
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        local_entries = 0
        if local_packed & 0x80:
            local_entries = 1 << ((local_packed & 0x07) + 1)
            offset += 3 * local_entries
        if offset >= len(raw) or not 2 <= raw[offset] <= 8:
            _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
        minimum_code_size = raw[offset]
        offset += 1
        image_data, offset = _gif_sub_blocks(raw, offset)
        _validate_gif_lzw(
            image_data,
            minimum_code_size=minimum_code_size,
            expected_pixels=image_width * image_height,
            palette_entries=local_entries or global_entries,
        )
        saw_image = True
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _jpeg_dimensions(raw: bytes) -> tuple[int, int]:
    try:
        return decoded_baseline_jpeg_dimensions(
            raw, maximum=MAX_IMAGE_BYTES, required_dimensions=(128, 128)
        )
    except ValueError:
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _image_dimensions(raw: bytes) -> tuple[int, int]:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return _png_dimensions(raw)
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return _gif_dimensions(raw)
    if raw.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(raw)
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _download_image(
    image_url: str, connection_factory: RakutenHttpsConnectionFactory
) -> bytes:
    parsed = urlsplit(image_url)
    raw = _fetch(
        host=RAKUTEN_IMAGE_HOST,
        path=f"{parsed.path}?{parsed.query}",
        headers={
            "Accept": "image/jpeg,image/png,image/gif",
            "Accept-Encoding": "identity",
            "Connection": "close",
            "Host": RAKUTEN_IMAGE_HOST,
            "User-Agent": CAPTURE_USER_AGENT,
        },
        expected_mime=_IMAGE_CONTENT_TYPE,
        maximum=MAX_IMAGE_BYTES,
        connection_factory=connection_factory,
    )
    if _image_dimensions(raw) != (128, 128):
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    return raw


def _download_first_exact_image(
    image_urls: tuple[str, ...],
    connection_factory: RakutenHttpsConnectionFactory,
) -> tuple[str, bytes, int]:
    if not 1 <= len(image_urls) <= MAX_IMAGE_CANDIDATES:
        _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)
    attempted = 0
    for image_url in image_urls:
        attempted += 1
        try:
            return image_url, _download_image(image_url, connection_factory), attempted
        except RakutenProductCaptureFailure as exc:
            if exc.code not in {
                RakutenProductCaptureFailureCode.IMAGE_INVALID,
                RakutenProductCaptureFailureCode.MIME_INVALID,
            }:
                raise
    _fail(RakutenProductCaptureFailureCode.IMAGE_INVALID)


def _safe_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            try:
                path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
            except FileExistsError:
                pass
        observed = path.lstat()
    except OSError:
        _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)


def _rakuten_directory(repository_root: Path) -> Path:
    secrets = repository_root / ".secrets"
    owner = secrets / OWNER_DIRECTORY
    directory = owner / RAKUTEN_DIRECTORY
    _safe_directory(secrets, create=True)
    _safe_directory(owner, create=True)
    _safe_directory(directory, create=True)
    return directory


def _replace_private(directory: Path, name: str, payload: bytes) -> None:
    if "/" in name or name in {"", ".", ".."} or not payload:
        _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
    temporary = f".{name}.{os.getpid()}.{os.urandom(16).hex()}.tmp"
    descriptor = -1
    directory_fd = -1
    try:
        descriptor = os.open(
            directory / temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset : offset + 65_536])
            if written <= 0:
                _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
            offset += written
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != PRIVATE_FILE_MODE
            or observed.st_nlink != 1
            or observed.st_size != len(payload)
        ):
            _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
        directory_fd = os.open(
            directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    except RakutenProductCaptureFailure:
        raise
    except OSError:
        _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        if descriptor >= 0:
            os.close(descriptor)
        try:
            (directory / temporary).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _fail(RakutenProductCaptureFailureCode.STORE_UNSAFE)


def _clock_value(clock: Callable[[], datetime]) -> str:
    try:
        value = clock()
    except BaseException:
        _fail()
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail()
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@dataclass(frozen=True, slots=True)
class ProductCaptureResult:
    product_id: str
    item_code: str
    retrieved_at: str
    request_count: int
    response_sha256: str
    affiliate_response_sha256: str
    image_sha256: str
    status: str = "CAPTURED_EXACT_PRODUCT"
    credentials_used: bool = True
    publication_authority: bool = False
    production_evidence: bool = False


def _capture_product(
    repository_root: Path,
    target: ProductCaptureTarget,
    credentials: RakutenCredentials,
    *,
    connection_factory: RakutenHttpsConnectionFactory,
    clock: Callable[[], datetime],
) -> ProductCaptureResult:
    item_code, _discovery_variant, discovery_count = _discover_item_code(
        target, credentials, connection_factory
    )
    response_raw = _api_request(
        credentials,
        selector_name="itemCode",
        selector_value=item_code,
        affiliate=False,
        elements=_REQUEST_ELEMENTS,
        hits=1,
        connection_factory=connection_factory,
        shop_code=None,
    )
    row = _one_exact_row(response_raw, target, item_code, credentials, affiliate=False)
    affiliate_raw = _api_request(
        credentials,
        selector_name="itemCode",
        selector_value=item_code,
        affiliate=True,
        elements=_AFFILIATE_REQUEST_ELEMENTS,
        hits=1,
        connection_factory=connection_factory,
        shop_code=None,
    )
    affiliate_row = _one_exact_row(
        affiliate_raw, target, item_code, credentials, affiliate=True
    )
    item_name = _text(row["itemName"], maximum=1000)
    if affiliate_row.get("itemName") != item_name:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    variant = _provider_variant(item_name, target.variants)
    if variant is None:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_LISTING_MISMATCH)
    # Rakuten Ichiba Item Search does not expose JAN as an output element.
    # Keep the nullable evidence field for compatibility with other authoritative
    # provider surfaces, but never synthesize a provider JAN from our registry.
    provider_jan = _provider_jan(row)
    if target.jan is not None and provider_jan != target.jan:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_LISTING_MISMATCH)
    image_urls = _image_urls(row)
    if _image_urls(affiliate_row) != image_urls:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    try:
        source_url = canonical_rakuten_provider_item_url(
            _text(row["itemUrl"], maximum=4096)
        )
    except EditorialPilotFailure:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    source_parts = urlsplit(source_url).path.strip("/").split("/")
    item_parts = item_code.split(":", 1)
    if len(source_parts) != 2 or source_parts[0] != item_parts[0]:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    destination_url = _text(affiliate_row["affiliateUrl"], maximum=4096)
    if affiliate_row.get("itemUrl") != destination_url:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    try:
        require_rakuten_affiliate_url(
            destination_url,
            item_url=source_url,
            item_code=item_code,
        )
    except EditorialPilotFailure:
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    if (
        target.fixed_destination_url is not None
        and destination_url != target.fixed_destination_url
    ):
        _fail(RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_INVALID)
    image_url, image_raw, image_request_count = _download_first_exact_image(
        image_urls, connection_factory
    )
    retrieved_at = _clock_value(clock)
    request_material = {
        "api_version": "2026-07-01",
        "elements": list(_REQUEST_ELEMENTS),
        "endpoint": RAKUTEN_API_ENDPOINT,
        "format": "json",
        "format_version": 2,
        "affiliate_id_supplied": False,
        "image_flag": 1,
        "item_code": item_code,
        "schema": "RAOS_ST1704_RAKUTEN_ITEM_SEARCH_REQUEST_V1",
        "secret_fields_excluded": ["accessKey", "affiliateId", "applicationId"],
    }
    affiliate_request_material = {
        **request_material,
        "elements": list(_AFFILIATE_REQUEST_ELEMENTS),
        "affiliate_id_supplied": True,
    }
    identity_material = {
        "image_url": image_url,
        "item_code": item_code,
        "item_name": item_name,
        "jan": provider_jan,
        "schema": "RAOS_ST1704_RAKUTEN_PROVIDER_IDENTITY_V1",
        "source_url": source_url,
    }
    affiliate_identity_material = {
        "affiliate_url": destination_url,
        "image_url": image_url,
        "item_code": item_code,
        "item_name": item_name,
        "item_url": destination_url,
        "jan": provider_jan,
        "schema": "RAOS_ST1704_RAKUTEN_AFFILIATE_PROVIDER_IDENTITY_V1",
    }
    try:
        evidence = RakutenProductEvidence(
            product_id=target.product_id,
            affiliate_ref=target.affiliate_ref,
            media_asset_ref=target.media_asset_ref,
            item_code=item_code,
            item_name=item_name,
            jan=provider_jan,
            variant=variant,
            source_url=source_url,
            destination_url=destination_url,
            image_url=image_url,
            width=128,
            height=128,
            retrieved_at=retrieved_at,
            request_fingerprint=canonical_sha256(request_material),
            response_sha256=bytes_sha256(response_raw),
            selected_result_sha256=canonical_sha256(identity_material),
            affiliate_request_fingerprint=canonical_sha256(affiliate_request_material),
            affiliate_response_sha256=bytes_sha256(affiliate_raw),
            affiliate_selected_result_sha256=canonical_sha256(
                affiliate_identity_material
            ),
            image_sha256=bytes_sha256(image_raw),
            no_modification_policy=_NO_MODIFICATION_POLICY,
        )
    except EditorialPilotFailure:
        _fail(RakutenProductCaptureFailureCode.RESPONSE_INVALID)
    document = {
        "schema": evidence.schema,
        "product_id": evidence.product_id,
        "affiliate_ref": evidence.affiliate_ref,
        "media_asset_ref": evidence.media_asset_ref,
        "item_code": evidence.item_code,
        "item_name": evidence.item_name,
        "jan": evidence.jan,
        "variant": evidence.variant,
        "source_url": evidence.source_url,
        "destination_url": evidence.destination_url,
        "image_url": evidence.image_url,
        "width": evidence.width,
        "height": evidence.height,
        "retrieved_at": evidence.retrieved_at,
        "request_fingerprint": evidence.request_fingerprint,
        "response_sha256": evidence.response_sha256,
        "selected_result_sha256": evidence.selected_result_sha256,
        "affiliate_request_fingerprint": evidence.affiliate_request_fingerprint,
        "affiliate_response_sha256": evidence.affiliate_response_sha256,
        "affiliate_selected_result_sha256": evidence.affiliate_selected_result_sha256,
        "image_sha256": evidence.image_sha256,
        "no_modification_policy": dict(evidence.no_modification_policy),
    }
    directory = _rakuten_directory(repository_root)
    lock_path = directory / CAPTURE_LOCK_FILE
    lock_fd = -1
    try:
        lock_fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        os.fchmod(lock_fd, PRIVATE_FILE_MODE)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _replace_private(
            directory, f"{target.product_id}.item-search-response.v1.json", response_raw
        )
        _replace_private(
            directory,
            f"{target.product_id}.affiliate-item-search-response.v1.json",
            affiliate_raw,
        )
        _replace_private(directory, f"{target.product_id}.image", image_raw)
        _replace_private(
            directory,
            f"{target.product_id}.v1.json",
            canonical_json_bytes(document) + b"\n",
        )
    except RakutenProductCaptureFailure:
        raise
    except OSError:
        _fail(RakutenProductCaptureFailureCode.STORE_CONFLICT)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
    return ProductCaptureResult(
        product_id=target.product_id,
        item_code=item_code,
        retrieved_at=retrieved_at,
        request_count=discovery_count + 2 + image_request_count,
        response_sha256=evidence.response_sha256,
        affiliate_response_sha256=evidence.affiliate_response_sha256,
        image_sha256=evidence.image_sha256,
    )


def capture_article_products(
    repository_root: Path,
    *,
    article_id: str,
    connection_factory: RakutenHttpsConnectionFactory | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[ProductCaptureResult, ...]:
    """Capture every unique product for one allowlisted article, one at a time."""

    if article_id not in _ARTICLE_IDS:
        _fail(RakutenProductCaptureFailureCode.ARTICLE_NOT_ALLOWLISTED)
    factory: RakutenHttpsConnectionFactory | None = None
    try:
        require_clean_capture_environment()
        plan = load_product_capture_plan(repository_root)
        credentials = read_owner_credentials(repository_root)
        factory = (
            SystemRakutenHttpsConnectionFactory(repository_root)
            if connection_factory is None
            else connection_factory
        )
        active_clock = (lambda: datetime.now(timezone.utc)) if clock is None else clock
        results: list[ProductCaptureResult] = []
        targets = plan.for_article(article_id)
        capture_order = sorted(
            enumerate(targets),
            key=lambda row: (row[1].fixed_item_code is None, row[0]),
        )
        captured: dict[str, ProductCaptureResult] = {}
        for _index, target in capture_order:
            captured[target.product_id] = _capture_product(
                repository_root,
                target,
                credentials,
                connection_factory=factory,
                clock=active_clock,
            )
        results.extend(captured[target.product_id] for target in targets)
        return tuple(results)
    except RakutenProductCaptureFailure as exc:
        credentials_used = factory.credentials_used if factory is not None else False
        if credentials_used != exc.credentials_used:
            raise RakutenProductCaptureFailure(
                exc.code, credentials_used=credentials_used
            ) from None
        raise


__all__ = [
    "ProductCaptureResult",
    "RakutenHttpsConnectionFactory",
    "RakutenProductCaptureFailure",
    "RakutenProductCaptureFailureCode",
    "SystemRakutenHttpsConnectionFactory",
    "capture_article_products",
    "load_product_capture_plan",
    "read_owner_credentials",
]
