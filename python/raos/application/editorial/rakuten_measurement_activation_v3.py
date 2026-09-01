"""Fail-closed owner-private activation of Editorial V3 Rakuten Money Links.

The tracked Editorial V3 contract deliberately keeps every provider profile in
``UNVERIFIED_DISABLED``.  This module does not infer a Rakuten query parameter
or create a live link.  It accepts only owner-private final Money Link URLs that
are bound to an exact administrator/CSV verification receipt, validates all 74
CTA identities, and materializes owner-private HTML for a later publication
workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape, unescape
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, NoReturn, cast
from urllib.parse import parse_qsl, unquote, urlsplit

from raos.application.editorial.editorial_portfolio_v2 import (
    EditorialPortfolioV2,
    EditorialPortfolioV2Failure,
    LOCAL_FIXTURE_RELATIVE_PATH,
    MANUFACTURER_SALES_STATE_RELATIVE_PATH,
    PORTFOLIO_RELATIVE_PATH as V2_PORTFOLIO_RELATIVE_PATH,
    PRODUCTION_FIXTURE_RELATIVE_PATH,
    STATUS_RELATIVE_PATH as V2_STATUS_RELATIVE_PATH,
    load_editorial_portfolio_v2,
    product_evidence_views_v2,
    require_manufacturer_sales_state_for_products_v1,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    ArticleBindingV3,
    CtaBindingV3,
    EditorialPortfolioV3,
    PORTFOLIO_RELATIVE_PATH,
)
from raos.application.editorial.product_safety_query_capture import (
    CAPTURE_BUNDLE_SCHEMA,
    CAPTURE_BUNDLE_VERSION,
    PROVIDER_SCOPE_COUNT,
    ProductSafetyAdministrativeEvidenceSet,
    ProductSafetyQueryCaptureFailure,
    verify_product_safety_query_capture_set,
)
from raos.application.finance.editorial_economics_v3 import (
    EditorialEconomicsV3Failure,
    canonical_json_bytes,
    read_private_bytes,
    write_private_bytes,
)


ADMIN_RECEIPT_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_ADMIN_VERIFICATION_RECEIPT_V1"
MONEY_LINK_MAPPING_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_MONEY_LINK_MAPPING_V1"
DRY_RUN_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_DRY_RUN_V2"
OVERLAY_RECEIPT_SCHEMA: Final = (
    "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V1"
)
LOCAL_OVERLAY_PREFIX: Final = "local-materialized-fixtures-v3-"
PRODUCTION_OVERLAY_PREFIX: Final = "production-materialized-fixtures-v3-"
V2_MATERIALIZATION_SCHEMA: Final = "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2"
AFFILIATE_HOST: Final = "hb.afl.rakuten.co.jp"
AFFILIATE_PATH_PREFIXES: Final = ("/hgc/", "/ichiba/")
NESTED_DESTINATION_HOSTS: Final = frozenset({"item.rakuten.co.jp", "m.rakuten.co.jp"})
FORMULA_PREFIXES: Final = ("=", "+", "-", "@")
MAX_TRACKED_HTML_BYTES: Final = 4 * 1024 * 1024
MAX_PRIVATE_DOCUMENT_BYTES: Final = 8 * 1024 * 1024
MAX_URL_LENGTH: Final = 8192
MAX_MAPPING_TO_VERIFICATION_AGE: Final = timedelta(hours=24)
MAX_VERIFICATION_TO_ACTIVATION_AGE: Final = timedelta(minutes=15)
MAX_ACTIVATION_AGE: Final = timedelta(minutes=15)
MAX_FUTURE_SKEW: Final = timedelta(seconds=30)
EXPECTED_PRODUCT_CARD_COUNT: Final = 37
EXPECTED_AFFILIATE_CTA_COUNT: Final = EXPECTED_PRODUCT_CARD_COUNT * 2
EXPECTED_PRODUCT_COUNT: Final = 31
PRODUCT_SAFETY_PUBLICATION_BINDING_SCHEMA: Final = (
    "RAOS_PRODUCT_SAFETY_PUBLICATION_BINDING_V1"
)
PRODUCT_SAFETY_REQUIRED_AUTHORITY_KINDS: Final = (
    "MANUFACTURER_OFFICIAL",
    "JAPAN_ADMINISTRATIVE_OFFICIAL",
)
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
TIMESTAMP_RE: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
SLUG_RE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
ATTRIBUTE_RE: Final = re.compile(
    r"\s+([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*([\"'])(.*?)\2",
    flags=re.DOTALL,
)
CTA_ANCHOR_RE: Final = re.compile(
    r"(<a\b(?=[^>]*\bdata-raos-product-id=[\"'][^\"']+[\"'])"
    r"(?=[^>]*\bdata-raos-placement=[\"'](?:product_card|final_summary)[\"'])"
    r"[^>]*>)(.*?)</a>",
    flags=re.IGNORECASE | re.DOTALL,
)
PRODUCT_IMAGE_RE: Final = re.compile(
    r"<img\b(?=[^>]*\bdata-raos-product-image-id=[\"'][^\"']+[\"'])[^>]*>",
    flags=re.IGNORECASE | re.DOTALL,
)
PRODUCT_CARD_RE: Final = re.compile(
    r"(<article\b(?=[^>]*\bdata-raos-product-id=[\"'][^\"']+[\"'])[^>]*>)"
    r"(.*?)</article>",
    flags=re.IGNORECASE | re.DOTALL,
)
RAKUTEN_IMAGE_PATH_RE: Final = re.compile(
    r"/[A-Za-z0-9._~!$&()*+,;=:@%/-]+\Z",
    flags=re.ASCII,
)
SENSITIVE_QUERY_NAMES: Final = frozenset(
    {
        "accesskey",
        "apikey",
        "applicationid",
        "auth",
        "authorization",
        "credential",
        "keyword",
        "order",
        "orderid",
        "password",
        "passwd",
        "query",
        "q",
        "search",
        "secret",
        "token",
    }
)
SENSITIVE_QUERY_MARKERS: Final = (
    "accesskey",
    "apikey",
    "applicationid",
    "authorization",
    "credential",
    "keyword",
    "order",
    "password",
    "passwd",
    "query",
    "search",
    "secret",
    "token",
)


class RakutenMeasurementActivationV3Failure(RuntimeError):
    """A stable error that never includes owner-private values."""


@dataclass(frozen=True)
class RakutenMeasurementActivationOverlayV3:
    """Validated owner-private publication inputs without affiliate URLs."""

    dry_run_sha256: str
    portfolio_sha256: str
    v2_portfolio_sha256: str
    v2_evidence_status_sha256: str
    v2_manufacturer_sales_state_sha256: str
    v2_manufacturer_sales_state_checked_at_utc: str
    v2_product_safety: Mapping[str, object]
    v2_local_receipt_sha256: str
    v2_production_receipt_sha256: str
    admin_receipt_sha256: str
    money_link_mapping_sha256: str
    mapping_generated_at_utc: str
    admin_verified_at_utc: str
    activated_at_utc: str
    materialized_set_sha256: str
    local_fixture_root: Path
    production_fixture_root: Path
    local_article_set_sha256: str
    production_article_set_sha256: str
    local_overlay_receipt_sha256: str
    production_overlay_receipt_sha256: str
    local_article_sha256: Mapping[str, str]
    production_article_sha256: Mapping[str, str]
    article_count: int
    cta_count: int


@dataclass(frozen=True, slots=True)
class _VerifiedV2ProductEvidence:
    """Publication-critical values reloaded from one real V2 evidence set."""

    product_id: str
    retrieved_at: str
    provider_binding_sha256: str
    image_url: str
    image_sha256: str
    image_extension: str
    jan_evidence_sha256: str | None


@dataclass(frozen=True, slots=True)
class _VerifiedV2EvidenceSet:
    """Exact status-file identity and every owner-registered product identity."""

    portfolio_sha256: str
    status_sha256: str
    manufacturer_sales_state_sha256: str
    manufacturer_sales_state_checked_at_utc: str
    product_safety: Mapping[str, object]
    products: Mapping[str, _VerifiedV2ProductEvidence]


def _fail(code: str) -> NoReturn:
    raise RakutenMeasurementActivationV3Failure(code) from None


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID")
    return cast(Mapping[str, object], value)


def _rows(value: object) -> list[Mapping[str, object]]:
    if type(value) is not list:
        _fail("RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID")
    return [_mapping(row) for row in cast(list[object], value)]


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
        or any(ord(character) < 0x20 for character in value)
        or value.startswith(FORMULA_PREFIXES)
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_VALUE_INVALID")
    return value


def _sha256(value: object) -> str:
    result = _text(value, maximum=64)
    if SHA256_RE.fullmatch(result) is None:
        _fail("RAOS_RAKUTEN_ACTIVATION_VALUE_INVALID")
    return result


def _timestamp(value: object) -> str:
    result = _text(value, maximum=20)
    if TIMESTAMP_RE.fullmatch(result) is None:
        _fail("RAOS_RAKUTEN_ACTIVATION_VALUE_INVALID")
    try:
        datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError:
        _fail("RAOS_RAKUTEN_ACTIVATION_VALUE_INVALID")
    return result


def _utc_instant(value: object) -> tuple[str, datetime]:
    text = _timestamp(value)
    return text, datetime.fromisoformat(text.replace("Z", "+00:00"))


def _validate_activation_time_chain(
    *,
    mapping_generated_at: object,
    admin_verified_at: object,
    activated_at: object,
    now: datetime,
    require_recent: bool,
) -> tuple[str, str, str]:
    """Require one short, ordered owner-verification window.

    The Money Link mapping must exist before the owner verifies its CSV/admin
    echo.  The mapping has a 24-hour owner-work window; the verification and
    publication activation each have a 15-minute window.  Publication also
    requires the activation itself to remain recent.
    """

    mapping_text, mapping_time = _utc_instant(mapping_generated_at)
    verified_text, verified_time = _utc_instant(admin_verified_at)
    activated_text, activation_time = _utc_instant(activated_at)
    active_now = now.astimezone(UTC)
    if (
        mapping_time > verified_time
        or verified_time > activation_time
        or activation_time > active_now + MAX_FUTURE_SKEW
        or verified_time - mapping_time > MAX_MAPPING_TO_VERIFICATION_AGE
        or activation_time - verified_time > MAX_VERIFICATION_TO_ACTIVATION_AGE
        or (
            require_recent
            and active_now - activation_time > MAX_ACTIVATION_AGE
        )
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_INPUT_STALE")
    return mapping_text, verified_text, activated_text


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("RAOS_RAKUTEN_ACTIVATION_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _json_document(content: bytes) -> Mapping[str, object]:
    if not 1 <= len(content) <= MAX_PRIVATE_DOCUMENT_BYTES:
        _fail("RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID")
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
        )
    except RakutenMeasurementActivationV3Failure:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID")
    return _mapping(value)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _compact_json_sha256(value: object) -> str:
    """Match the canonical binding serialization used by the V2 materializer."""

    try:
        content = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_EVIDENCE_INVALID")
    return _sha256_bytes(content)


def _verified_manufacturer_product_safety_ids(
    repository_root: Path,
    portfolio: EditorialPortfolioV2,
    *,
    now: datetime,
) -> frozenset[str]:
    """Return independently replay-verified manufacturer safety coverage.

    No manufacturer replay adapter exists yet.  Tracked/owner-authored receipt
    rows are deliberately not accepted here because their hashes only prove
    integrity of the declaration, not that the official query was executed.
    """

    del repository_root, portfolio, now
    return frozenset()


def _validate_product_safety_publication_binding(
    value: object,
    *,
    require_complete: bool,
) -> dict[str, object]:
    binding = _mapping(value)
    expected_keys = {
        "schema",
        "required_product_count",
        "required_authority_kinds",
        "required_administrative_capture_count",
        "administrative_bundle_sha256",
        "administrative_capture_count",
        "administrative_verified_product_count",
        "manufacturer_verified_product_count",
        "complete_product_count",
        "complete",
        "binding_sha256",
    }
    _exact_keys(binding, expected_keys)
    hash_material = {
        key: binding[key] for key in expected_keys if key != "binding_sha256"
    }
    bundle_sha256 = binding.get("administrative_bundle_sha256")
    if (
        binding.get("schema") != PRODUCT_SAFETY_PUBLICATION_BINDING_SCHEMA
        or binding.get("required_product_count") != EXPECTED_PRODUCT_COUNT
        or binding.get("required_authority_kinds")
        != list(PRODUCT_SAFETY_REQUIRED_AUTHORITY_KINDS)
        or binding.get("required_administrative_capture_count")
        != EXPECTED_PRODUCT_COUNT * PROVIDER_SCOPE_COUNT
        or type(bundle_sha256) is not str
        or SHA256_RE.fullmatch(bundle_sha256) is None
        or binding.get("administrative_capture_count")
        != EXPECTED_PRODUCT_COUNT * PROVIDER_SCOPE_COUNT
        or binding.get("administrative_verified_product_count")
        != EXPECTED_PRODUCT_COUNT
        or binding.get("manufacturer_verified_product_count")
        != EXPECTED_PRODUCT_COUNT
        or binding.get("complete_product_count") != EXPECTED_PRODUCT_COUNT
        or binding.get("complete") is not True
        or _sha256(binding.get("binding_sha256"))
        != _compact_json_sha256(hash_material)
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INVALID")
    if require_complete and binding.get("complete") is not True:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INCOMPLETE")
    return dict(binding)


def _current_product_safety_publication_binding(
    repository_root: Path,
    portfolio: EditorialPortfolioV2,
    *,
    now: datetime,
    require_complete: bool = True,
) -> dict[str, object]:
    """Replay the exact 31 x 3 private set and derive a public-safe gate."""

    expected_products = {product.product_id: product for product in portfolio.products}
    if len(expected_products) != EXPECTED_PRODUCT_COUNT:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INVALID")
    expected_product_ids = frozenset(expected_products)
    try:
        administrative = verify_product_safety_query_capture_set(
            repository_root,
            now=now,
        )
    except ProductSafetyQueryCaptureFailure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INCOMPLETE")
    if (
        type(administrative) is not ProductSafetyAdministrativeEvidenceSet
        or administrative.schema != CAPTURE_BUNDLE_SCHEMA
        or administrative.version != CAPTURE_BUNDLE_VERSION
        or administrative.evaluated_at != now
        or administrative.portfolio_sha256
        != _sha256_bytes(
            _read_regular_file(
                repository_root / V2_PORTFOLIO_RELATIVE_PATH,
                maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            )
        )
        or administrative.capture_count
        != EXPECTED_PRODUCT_COUNT * PROVIDER_SCOPE_COUNT
        or SHA256_RE.fullmatch(administrative.bundle_sha256) is None
        or len(administrative.products) != EXPECTED_PRODUCT_COUNT
        or {row.product_id for row in administrative.products}
        != set(expected_products)
        or any(
            row.exact_model_tokens
            != expected_products[row.product_id].official_models
            or len(row.captures) != PROVIDER_SCOPE_COUNT
            for row in administrative.products
        )
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INVALID")
    administrative_verified_ids = frozenset(
        row.product_id
        for row in administrative.products
        if row.status == "VERIFIED_NONE_FOUND"
    )
    manufacturer_verified_ids = _verified_manufacturer_product_safety_ids(
        repository_root,
        portfolio,
        now=now,
    )
    if (
        type(manufacturer_verified_ids) is not frozenset
        or not manufacturer_verified_ids.issubset(expected_products)
        or any(type(product_id) is not str for product_id in manufacturer_verified_ids)
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INVALID")
    complete_product_ids = administrative_verified_ids & manufacturer_verified_ids
    complete = (
        administrative.complete
        and administrative_verified_ids == expected_product_ids
        and manufacturer_verified_ids == expected_product_ids
        and complete_product_ids == expected_product_ids
    )
    material: dict[str, object] = {
        "schema": PRODUCT_SAFETY_PUBLICATION_BINDING_SCHEMA,
        "required_product_count": EXPECTED_PRODUCT_COUNT,
        "required_authority_kinds": list(PRODUCT_SAFETY_REQUIRED_AUTHORITY_KINDS),
        "required_administrative_capture_count": (
            EXPECTED_PRODUCT_COUNT * PROVIDER_SCOPE_COUNT
        ),
        "administrative_bundle_sha256": administrative.bundle_sha256,
        "administrative_capture_count": administrative.capture_count,
        "administrative_verified_product_count": len(administrative_verified_ids),
        "manufacturer_verified_product_count": len(manufacturer_verified_ids),
        "complete_product_count": len(complete_product_ids),
        "complete": complete,
    }
    binding = {
        **material,
        "binding_sha256": _compact_json_sha256(material),
    }
    if require_complete and not complete:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRODUCT_SAFETY_INCOMPLETE")
    return _validate_product_safety_publication_binding(
        binding,
        require_complete=require_complete,
    )


def _read_regular_file(path: Path, *, maximum: int) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 1 <= before.st_size <= maximum
            or before.st_nlink != 1
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
        content = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(content) != before.st_size or (
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
            _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
        return content
    except RakutenMeasurementActivationV3Failure:
        raise
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _exact_keys(row: Mapping[str, object], expected: set[str]) -> None:
    if set(row) != expected:
        _fail("RAOS_RAKUTEN_ACTIVATION_DOCUMENT_INVALID")


def _reject_formula_like_strings(value: object) -> None:
    if type(value) is str:
        _text(value, maximum=MAX_URL_LENGTH)
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _reject_formula_like_strings(item)
        return
    if type(value) is dict:
        for key, item in cast(dict[object, object], value).items():
            _text(key, maximum=128)
            _reject_formula_like_strings(item)


def _normalized_query_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _is_sensitive_query_name(value: str) -> bool:
    normalized = _normalized_query_name(value)
    return normalized in SENSITIVE_QUERY_NAMES or any(
        marker in normalized for marker in SENSITIVE_QUERY_MARKERS
    )


def _validate_nested_destination(value: str) -> None:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value) is not None:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    try:
        parsed = urlsplit(value)
    except ValueError:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    decoded_path = unquote(parsed.path)
    path_segments = [segment for segment in decoded_path.split("/") if segment]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in NESTED_DESTINATION_HOSTS
        or parsed.netloc != parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path
        or parsed.path == "/"
        or parsed.query
        or parsed.fragment
        or "\\" in decoded_path
        or "//" in decoded_path
        or "?" in decoded_path
        or "#" in decoded_path
        or any(segment in {".", ".."} for segment in path_segments)
        or "/search" in decoded_path.casefold()
        or "/order" in decoded_path.casefold()
        or len(path_segments) < 2
        or (
            parsed.hostname == "m.rakuten.co.jp"
            and (len(path_segments) < 3 or path_segments[1] != "i")
        )
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")


def _validate_money_link_url(value: object) -> str:
    url = _text(value, maximum=MAX_URL_LENGTH)
    if re.search(r"%(?![0-9A-Fa-f]{2})", url) is not None:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    try:
        parsed = urlsplit(url)
        if parsed.port is not None:
            _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    except ValueError:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname != AFFILIATE_HOST
        or parsed.netloc != AFFILIATE_HOST
        or parsed.username is not None
        or parsed.password is not None
        or not decoded_path.startswith(AFFILIATE_PATH_PREFIXES)
        or "\\" in decoded_path
        or "//" in decoded_path
        or "?" in decoded_path
        or "#" in decoded_path
        or any(part in {".", ".."} for part in decoded_path.split("/"))
        or "/search" in decoded_path.casefold()
        or "/order" in decoded_path.casefold()
        or parsed.fragment
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    try:
        query = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=False,
            max_num_fields=64,
        )
    except ValueError:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    for key, raw_value in query:
        if (
            not key
            or key != key.strip()
            or raw_value != raw_value.strip()
            or any(ord(character) < 0x20 for character in key + raw_value)
            or key.startswith(FORMULA_PREFIXES)
            or raw_value.startswith(FORMULA_PREFIXES)
            or _is_sensitive_query_name(key)
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
        decoded = unquote(raw_value)
        if decoded.casefold().startswith(("http://", "https://")):
            _validate_nested_destination(decoded)
    return url


def _validate_rakuten_image_url(value: object) -> str:
    url = _text(value, maximum=MAX_URL_LENGTH)
    if re.search(r"%(?![0-9A-Fa-f]{2})", url) is not None:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    try:
        parsed = urlsplit(url)
        query = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=1,
        )
    except ValueError:
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "thumbnail.image.rakuten.co.jp"
        or parsed.netloc != "thumbnail.image.rakuten.co.jp"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or RAKUTEN_IMAGE_PATH_RE.fullmatch(parsed.path) is None
        or any(component in {".", ".."} for component in parsed.path.split("/"))
        or query != [("_ex", "128x128")]
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_URL_INVALID")
    return url


def _load_verified_v2_evidence(
    repository_root: Path,
    *,
    now: datetime,
) -> _VerifiedV2EvidenceSet:
    """Reload and validate the status plus all provider evidence behind V2.

    A V2 materialization receipt is only a cache of this evidence.  Activation
    therefore reopens the owner-private status/evidence/image files and derives
    each expected binding from those files instead of trusting receipt hashes.
    """

    portfolio_path = repository_root / V2_PORTFOLIO_RELATIVE_PATH
    status_path = repository_root / V2_STATUS_RELATIVE_PATH
    sales_state_path = repository_root / MANUFACTURER_SALES_STATE_RELATIVE_PATH
    portfolio_before = _read_regular_file(
        portfolio_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    status_before = _read_owner_regular_file(
        status_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    sales_state_before = _read_regular_file(
        sales_state_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    try:
        v2 = load_editorial_portfolio_v2(repository_root)
        sales_audit = require_manufacturer_sales_state_for_products_v1(
            v2,
            tuple(product.product_id for product in v2.products),
            now=now,
        )
        views = product_evidence_views_v2(
            repository_root,
            now=now,
            require_fresh_set=True,
            require_verified_set=True,
        )
    except EditorialPortfolioV2Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_EVIDENCE_INVALID")
    portfolio_after = _read_regular_file(
        portfolio_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    status_after = _read_owner_regular_file(
        status_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    sales_state_after = _read_regular_file(
        sales_state_path,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    portfolio_sha256 = _sha256_bytes(portfolio_before)
    sales_state_sha256 = _sha256_bytes(sales_state_before)
    if (
        portfolio_before != portfolio_after
        or status_before != status_after
        or sales_state_before != sales_state_after
        or sales_audit.document_sha256 != sales_state_sha256
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")

    product_safety = _current_product_safety_publication_binding(
        repository_root,
        v2,
        now=now,
        require_complete=True,
    )
    if (
        _read_regular_file(
            portfolio_path,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
        != portfolio_before
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")

    expected_product_ids = {product.product_id for product in v2.products}
    if (
        len(expected_product_ids) != len(v2.products)
        or set(views) != expected_product_ids
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_EVIDENCE_INCOMPLETE")

    verified: dict[str, _VerifiedV2ProductEvidence] = {}
    for binding in v2.products:
        view = views[binding.product_id]
        evidence = view.evidence
        if (
            view.state != "verified"
            or evidence is None
            or view.product_id != binding.product_id
            or view.retrieved_at != evidence.retrieved_at
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_EVIDENCE_INCOMPLETE")
        image_url = _validate_rakuten_image_url(evidence.image_url)
        image_sha256 = _sha256(evidence.image_sha256)
        image_extension = view.image_extension
        if image_extension not in {"jpg", "png", "gif"}:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_EVIDENCE_INVALID")
        provider_binding_sha256 = _compact_json_sha256(
            {
                "product_id": binding.product_id,
                "state": "verified",
                "item_code": evidence.item_code,
                "destination_url": evidence.destination_url,
                "image_url": image_url,
                "image_sha256": image_sha256,
                "jan_evidence_sha256": view.jan_evidence_sha256,
            }
        )
        verified[binding.product_id] = _VerifiedV2ProductEvidence(
            product_id=binding.product_id,
            retrieved_at=_timestamp(evidence.retrieved_at),
            provider_binding_sha256=provider_binding_sha256,
            image_url=image_url,
            image_sha256=image_sha256,
            image_extension=image_extension,
            jan_evidence_sha256=view.jan_evidence_sha256,
        )
    return _VerifiedV2EvidenceSet(
        portfolio_sha256=portfolio_sha256,
        status_sha256=_sha256_bytes(status_before),
        manufacturer_sales_state_sha256=sales_state_sha256,
        manufacturer_sales_state_checked_at_utc=sales_audit.checked_at_utc,
        product_safety=product_safety,
        products=dict(sorted(verified.items())),
    )


def _expected_bindings(
    portfolio: EditorialPortfolioV3,
) -> dict[tuple[str, str, str], CtaBindingV3]:
    result: dict[tuple[str, str, str], CtaBindingV3] = {}
    for article in portfolio.articles:
        for binding in article.cta_bindings:
            identity = (binding.article_id, binding.product_id, binding.placement)
            if identity in result:
                _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
            result[identity] = binding
    if len(result) != EXPECTED_AFFILIATE_CTA_COUNT:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    return result


def _portfolio_sha256(
    repository_root: Path,
    portfolio: EditorialPortfolioV3,
) -> str:
    raw = _read_regular_file(
        repository_root / PORTFOLIO_RELATIVE_PATH,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    digest = _sha256_bytes(raw)
    if digest != portfolio.source_sha256:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    return digest


def money_link_mapping_template_v3(
    *,
    repository_root: Path,
    portfolio: EditorialPortfolioV3,
    generated_at: str | None = None,
) -> Mapping[str, object]:
    """Build an owner-private 74-row mapping template without any provider URL."""

    if not repository_root.is_absolute():
        _fail("RAOS_RAKUTEN_ACTIVATION_ROOT_INVALID")
    portfolio_sha256 = _portfolio_sha256(repository_root, portfolio)
    try:
        v2 = load_editorial_portfolio_v2(repository_root)
    except EditorialPortfolioV2Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    models = {
        product.product_id: product.representative_model for product in v2.products
    }
    expected = _expected_bindings(portfolio)
    if set(models) != {identity[1] for identity in expected}:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    created_at = generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _timestamp(created_at)
    return {
        "schema": MONEY_LINK_MAPPING_SCHEMA,
        "version": "1.0.0",
        "generated_at": created_at,
        "portfolio_sha256": portfolio_sha256,
        "urls_copied_from_rakuten_admin": False,
        "provider_parameter_inference_used": False,
        "rows": [
            {
                "article_id": binding.article_id,
                "product_id": binding.product_id,
                "placement": binding.placement,
                "rakuten_measurement_id": binding.rakuten_measurement_id,
                "representative_model": models[binding.product_id],
                "destination_url": None,
            }
            for binding in (
                expected[identity]
                for identity in sorted(
                    expected,
                    key=lambda value: expected[value].rakuten_measurement_id,
                )
            )
        ],
    }


def admin_verification_receipt_template_v3(
    *,
    repository_root: Path,
    portfolio: EditorialPortfolioV3,
    money_link_mapping: bytes,
    generated_at: str | None = None,
) -> Mapping[str, object]:
    """Validate a completed mapping and build a fail-closed owner receipt template."""

    if not repository_root.is_absolute():
        _fail("RAOS_RAKUTEN_ACTIVATION_ROOT_INVALID")
    portfolio_sha256 = _portfolio_sha256(repository_root, portfolio)
    mapping = _json_document(money_link_mapping)
    _reject_formula_like_strings(mapping)
    expected = _expected_bindings(portfolio)
    try:
        v2 = load_editorial_portfolio_v2(repository_root)
    except EditorialPortfolioV2Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    models = {
        product.product_id: product.representative_model for product in v2.products
    }
    _mapping_urls(
        mapping,
        portfolio_sha256=portfolio_sha256,
        expected=expected,
        representative_models=models,
    )
    created_at = generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    _timestamp(created_at)
    return {
        "schema": ADMIN_RECEIPT_SCHEMA,
        "version": "1.0.0",
        "state": "OWNER_VERIFICATION_REQUIRED",
        "verified_at": created_at,
        "owner_attested": False,
        "portfolio_sha256": portfolio_sha256,
        "money_link_mapping_sha256": _sha256_bytes(money_link_mapping),
        "verification": {
            "all_expected_ids_accepted_by_admin": False,
            "character_set_and_length_verified": False,
            "csv_export_verified": False,
            "provider_parameter_inference_used": False,
            "production_publication_authorized": False,
        },
        "bindings": [
            {
                "article_id": binding.article_id,
                "product_id": binding.product_id,
                "placement": binding.placement,
                "rakuten_measurement_id": binding.rakuten_measurement_id,
                "csv_echoed_measurement_id": None,
                "representative_model": models[binding.product_id],
                "csv_echoed_representative_model": None,
                "admin_console_measurement_id_verified": False,
                "money_link_product_identity_verified": False,
            }
            for binding in (
                expected[identity]
                for identity in sorted(
                    expected,
                    key=lambda value: expected[value].rakuten_measurement_id,
                )
            )
        ],
    }


def _mapping_urls(
    document: Mapping[str, object],
    *,
    portfolio_sha256: str,
    expected: Mapping[tuple[str, str, str], CtaBindingV3],
    representative_models: Mapping[str, str],
) -> dict[tuple[str, str, str], str]:
    _exact_keys(
        document,
        {
            "schema",
            "version",
            "generated_at",
            "portfolio_sha256",
            "urls_copied_from_rakuten_admin",
            "provider_parameter_inference_used",
            "rows",
        },
    )
    if (
        document.get("schema") != MONEY_LINK_MAPPING_SCHEMA
        or document.get("version") != "1.0.0"
        or _timestamp(document.get("generated_at")) != document.get("generated_at")
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or document.get("urls_copied_from_rakuten_admin") is not True
        or document.get("provider_parameter_inference_used") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID")
    urls: dict[tuple[str, str, str], str] = {}
    seen_urls: set[str] = set()
    for row in _rows(document.get("rows")):
        _exact_keys(
            row,
            {
                "article_id",
                "product_id",
                "placement",
                "rakuten_measurement_id",
                "representative_model",
                "destination_url",
            },
        )
        identity = (
            _text(row.get("article_id")),
            _text(row.get("product_id")),
            _text(row.get("placement")),
        )
        binding = expected.get(identity)
        representative_model = representative_models.get(identity[1])
        destination_url = _validate_money_link_url(row.get("destination_url"))
        if (
            binding is None
            or identity in urls
            or _text(row.get("rakuten_measurement_id"))
            != binding.rakuten_measurement_id
            or representative_model is None
            or _text(row.get("representative_model"), maximum=300)
            != representative_model
            or destination_url in seen_urls
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID")
        urls[identity] = destination_url
        seen_urls.add(destination_url)
    if set(urls) != set(expected):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")
    return urls


def _validate_admin_receipt(
    document: Mapping[str, object],
    *,
    portfolio_sha256: str,
    mapping_sha256: str,
    expected: Mapping[tuple[str, str, str], CtaBindingV3],
    representative_models: Mapping[str, str],
) -> None:
    _exact_keys(
        document,
        {
            "schema",
            "version",
            "state",
            "verified_at",
            "owner_attested",
            "portfolio_sha256",
            "money_link_mapping_sha256",
            "verification",
            "bindings",
        },
    )
    verification = _mapping(document.get("verification"))
    _exact_keys(
        verification,
        {
            "all_expected_ids_accepted_by_admin",
            "character_set_and_length_verified",
            "csv_export_verified",
            "provider_parameter_inference_used",
            "production_publication_authorized",
        },
    )
    if (
        document.get("schema") != ADMIN_RECEIPT_SCHEMA
        or document.get("version") != "1.0.0"
        or document.get("state") != "OWNER_VERIFIED_RAKUTEN_ADMIN_AND_CSV"
        or _timestamp(document.get("verified_at")) != document.get("verified_at")
        or document.get("owner_attested") is not True
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or _sha256(document.get("money_link_mapping_sha256")) != mapping_sha256
        or verification.get("all_expected_ids_accepted_by_admin") is not True
        or verification.get("character_set_and_length_verified") is not True
        or verification.get("csv_export_verified") is not True
        or verification.get("provider_parameter_inference_used") is not False
        or verification.get("production_publication_authorized") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID")
    observed: set[tuple[str, str, str]] = set()
    for row in _rows(document.get("bindings")):
        _exact_keys(
            row,
            {
                "article_id",
                "product_id",
                "placement",
                "rakuten_measurement_id",
                "csv_echoed_measurement_id",
                "representative_model",
                "csv_echoed_representative_model",
                "admin_console_measurement_id_verified",
                "money_link_product_identity_verified",
            },
        )
        identity = (
            _text(row.get("article_id")),
            _text(row.get("product_id")),
            _text(row.get("placement")),
        )
        binding = expected.get(identity)
        expected_model = representative_models.get(identity[1])
        measurement_id = _text(row.get("rakuten_measurement_id"))
        if (
            binding is None
            or identity in observed
            or measurement_id != binding.rakuten_measurement_id
            or _text(row.get("csv_echoed_measurement_id")) != measurement_id
            or expected_model is None
            or _text(row.get("representative_model"), maximum=300) != expected_model
            or _text(row.get("csv_echoed_representative_model"), maximum=300)
            != expected_model
            or row.get("admin_console_measurement_id_verified") is not True
            or row.get("money_link_product_identity_verified") is not True
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID")
        observed.add(identity)
    if observed != set(expected):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")


def _tag_attributes(opening: str, *, tag_name: str) -> dict[str, str]:
    prefix = f"<{tag_name}"
    if not opening.casefold().startswith(prefix) or not opening.endswith(">"):
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    result: dict[str, str] = {}
    cursor = len(prefix)
    for match in ATTRIBUTE_RE.finditer(opening, cursor, len(opening) - 1):
        if opening[cursor : match.start()].strip():
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        name = match.group(1).casefold()
        if name in result:
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        value = unescape(match.group(3))
        if "\x00" in value or any(
            ord(character) < 0x20 and character not in "\t\r\n" for character in value
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        result[name] = value
        cursor = match.end()
    if opening[cursor:-1].strip():
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    return result


def _anchor_attributes(opening: str) -> dict[str, str]:
    return _tag_attributes(opening, tag_name="a")


def _materialized_anchor(
    binding: CtaBindingV3,
    *,
    destination_url: str,
    described_by: str | None,
) -> str:
    described = ""
    if described_by is not None:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", described_by) is None:
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        described = f' aria-describedby="{escape(described_by, quote=True)}"'
    label = (
        "型番と最新価格を楽天市場で確認する"
        if binding.placement == "product_card"
        else "在庫・カラーを楽天市場で確認する"
    )
    return (
        '<a class="rakuten-cta raos-cta"'
        f' href="{escape(destination_url, quote=True)}"'
        ' rel="sponsored nofollow"'
        f' data-raos-article-id="{escape(binding.article_id, quote=True)}"'
        f' data-raos-cta-id="{escape(binding.cta_id, quote=True)}"'
        f' data-raos-snapshot-id="{escape(binding.snapshot_id, quote=True)}"'
        f' data-raos-offer-id="{escape(binding.offer_id, quote=True)}"'
        f' data-raos-product-id="{escape(binding.product_id, quote=True)}"'
        f' data-raos-placement="{binding.placement}"'
        ' data-raos-rakuten-measurement-id="'
        f'{escape(binding.rakuten_measurement_id, quote=True)}"'
        f'{described}>{label} <span aria-hidden="true">→</span></a>'
    )


def materialize_article_html(
    article: ArticleBindingV3,
    source: bytes,
    urls: Mapping[tuple[str, str, str], str],
) -> bytes:
    """Materialize exactly one tracked article into a private candidate."""

    try:
        markup = source.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    expected = {
        (binding.article_id, binding.product_id, binding.placement): binding
        for binding in article.cta_bindings
    }
    observed: set[tuple[str, str, str]] = set()
    described_bindings: dict[str, CtaBindingV3] = {}

    def replace(match: re.Match[str]) -> str:
        attributes = _anchor_attributes(match.group(1))
        product_id = attributes.get("data-raos-product-id")
        placement = attributes.get("data-raos-placement")
        source_article_id = attributes.get("data-raos-article-id")
        if (
            product_id is None
            or placement is None
            or source_article_id not in {article.article_id, article.production_slug}
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        identity = (article.article_id, product_id, placement)
        binding = expected.get(identity)
        destination_url = urls.get(identity)
        if binding is None or destination_url is None or identity in observed:
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
        observed.add(identity)
        described_by = attributes.get("aria-describedby")
        if described_by is not None:
            if (
                binding.placement != "product_card"
                or described_by in described_bindings
            ):
                _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
            described_bindings[described_by] = binding
        return _materialized_anchor(
            binding,
            destination_url=destination_url,
            described_by=described_by,
        )

    materialized = CTA_ANCHOR_RE.sub(replace, markup)
    if observed != set(expected):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")
    expected_notes = {
        binding.cta_id
        for binding in article.cta_bindings
        if binding.placement == "product_card"
    }
    if {binding.cta_id for binding in described_bindings.values()} != expected_notes:
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    note = (
        "楽天市場の販売ページで、型番と最新価格、在庫、カラーを確認できます。"
        "購入前に商品名と型番がこの記事の比較対象と一致することを確認してください。"
    )
    for note_id in described_bindings:
        pattern = re.compile(
            r"(<p\b(?=[^>]*\bid=[\"']"
            + re.escape(note_id)
            + r"[\"'])(?=[^>]*\bclass=[\"'][^\"']*\bcta-note\b[^\"']*[\"'])"
            r"[^>]*>).*?(</p>)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        materialized, replacements = pattern.subn(
            lambda note_match: note_match.group(1) + escape(note) + note_match.group(2),
            materialized,
            count=1,
        )
        if replacements != 1:
            _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    if (
        "一致する楽天商品を確認できなかったため、楽天購入リンクは掲載していません。"
        in materialized
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    result = materialized.encode("utf-8")
    if result.count(b"https://hb.afl.rakuten.co.jp/") != len(expected):
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    return result


def _owner_directory(path: Path, *, exact_mode: int | None = None) -> Path:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or mode & 0o022
        or (exact_mode is not None and mode != exact_mode)
        or resolved != Path(os.path.abspath(path))
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
    return resolved


def _read_owner_regular_file(
    path: Path,
    *,
    maximum: int,
    exact_mode: int | None = None,
) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or mode & 0o022
            or (exact_mode is not None and mode != exact_mode)
            or not 1 <= before.st_size <= maximum
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
        content = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(content) != before.st_size or (
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
            _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
        return content
    except RakutenMeasurementActivationV3Failure:
        raise
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _default_v2_fixture_roots(repository_root: Path) -> tuple[Path, Path]:
    return (
        repository_root / LOCAL_FIXTURE_RELATIVE_PATH,
        repository_root / PRODUCTION_FIXTURE_RELATIVE_PATH,
    )


def _validate_v2_completion_html(
    *,
    article: ArticleBindingV3,
    source: bytes,
    mode: str,
    verified_evidence: Mapping[str, _VerifiedV2ProductEvidence],
) -> tuple[int, int]:
    try:
        markup = source.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
    if (
        "official-product-link" in markup
        or 'data-raos-product-image-state="neutral"' in markup
        or "一致する楽天商品を確認できなかったため" in markup
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")

    expected_ctas = {
        (binding.product_id, binding.placement) for binding in article.cta_bindings
    }
    observed_ctas: set[tuple[str, str]] = set()
    for match in CTA_ANCHOR_RE.finditer(markup):
        attributes = _anchor_attributes(match.group(1))
        identity = (
            attributes.get("data-raos-product-id", ""),
            attributes.get("data-raos-placement", ""),
        )
        classes = attributes.get("class", "").split()
        href = attributes.get("href")
        if (
            identity not in expected_ctas
            or identity in observed_ctas
            or attributes.get("data-raos-article-id")
            not in {article.article_id, article.production_slug}
            or attributes.get("rel") != "sponsored nofollow"
            or not {"rakuten-cta", "raos-cta"}.issubset(classes)
            or href is None
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        _validate_money_link_url(href)
        observed_ctas.add(identity)
    if observed_ctas != expected_ctas:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")

    expected_images = set(article.product_ids)
    observed_cards: set[str] = set()
    for card in PRODUCT_CARD_RE.finditer(markup):
        card_attributes = _tag_attributes(card.group(1), tag_name="article")
        product_id = card_attributes.get("data-raos-product-id", "")
        body = card.group(2)
        images = tuple(re.finditer(r"<img\b[^>]*>", body, flags=re.I | re.S))
        if (
            product_id not in expected_images
            or product_id in observed_cards
            or len(images) != 1
            or re.search(r"<source\b", body, flags=re.I) is not None
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        image_attributes = _tag_attributes(images[0].group(0), tag_name="img")
        if image_attributes.get("data-raos-product-image-id") != product_id:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        observed_cards.add(product_id)
    if observed_cards != expected_images:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")

    observed_images: set[str] = set()
    for match in PRODUCT_IMAGE_RE.finditer(markup):
        attributes = _tag_attributes(match.group(0), tag_name="img")
        product_id = attributes.get("data-raos-product-image-id", "")
        source_url = attributes.get("src", "")
        evidence = verified_evidence.get(product_id)
        if (
            product_id not in expected_images
            or product_id in observed_images
            or evidence is None
            or attributes.get("data-raos-product-image-state") != "verified"
            or attributes.get("width") != "128"
            or attributes.get("height") != "128"
            or attributes.get("loading") != "lazy"
            or "srcset" in attributes
            or "sizes" in attributes
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        if mode == "local":
            if source_url != (
                f"/raos-product-media/{product_id}.{evidence.image_extension}"
            ):
                _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        else:
            try:
                validated_url = _validate_rakuten_image_url(source_url)
            except RakutenMeasurementActivationV3Failure:
                _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
            if validated_url != evidence.image_url:
                _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        observed_images.add(product_id)
    if observed_images != expected_images:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
    return len(observed_images), len(observed_ctas)


def _v2_materialization(
    *,
    repository_root: Path,
    fixture_root: Path,
    mode: str,
    portfolio: EditorialPortfolioV3,
    verified_evidence: _VerifiedV2EvidenceSet,
) -> dict[str, object]:
    root = _owner_directory(fixture_root)
    article_root = _owner_directory(root / "articles")
    receipt_raw = _read_owner_regular_file(
        root / "materialization-receipt.v2.json",
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    posts_raw = _read_owner_regular_file(
        root / "posts.json",
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    receipt = _json_document(receipt_raw)
    _exact_keys(
        receipt,
        {
            "schema",
            "mode",
            "generated_at",
            "portfolio_sha256",
            "evidence_status_sha256",
            "manufacturer_sales_state_sha256",
            "manufacturer_sales_state_checked_at_utc",
            "product_safety",
            "articles",
            "products",
            "media",
            "completion",
        },
    )
    try:
        v2_portfolio_raw = _read_regular_file(
            repository_root / V2_PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
    except RakutenMeasurementActivationV3Failure:
        raise
    expected_v2_portfolio_sha256 = _sha256_bytes(v2_portfolio_raw)
    generated_at = _timestamp(receipt.get("generated_at"))
    evidence_status_sha256 = _sha256(receipt.get("evidence_status_sha256"))
    manufacturer_sales_state_sha256 = _sha256(
        receipt.get("manufacturer_sales_state_sha256")
    )
    manufacturer_sales_state_checked_at_utc = _timestamp(
        receipt.get("manufacturer_sales_state_checked_at_utc")
    )
    product_safety = _validate_product_safety_publication_binding(
        receipt.get("product_safety"),
        require_complete=True,
    )
    if (
        receipt.get("schema") != V2_MATERIALIZATION_SCHEMA
        or receipt.get("mode") != mode
        or _sha256(receipt.get("portfolio_sha256")) != expected_v2_portfolio_sha256
        or expected_v2_portfolio_sha256 != verified_evidence.portfolio_sha256
        or evidence_status_sha256 != verified_evidence.status_sha256
        or manufacturer_sales_state_sha256
        != verified_evidence.manufacturer_sales_state_sha256
        or manufacturer_sales_state_checked_at_utc
        != verified_evidence.manufacturer_sales_state_checked_at_utc
        or product_safety != verified_evidence.product_safety
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
    expected_articles = portfolio.article_by_id
    sources: dict[str, bytes] = {}
    article_rows: list[dict[str, str]] = []
    verified_product_card_count = 0
    verified_affiliate_cta_count = 0
    for raw in _rows(receipt.get("articles")):
        _exact_keys(raw, {"article_id", "production_slug", "content_sha256"})
        article_id = _text(raw.get("article_id"))
        slug = _text(raw.get("production_slug"))
        digest = _sha256(raw.get("content_sha256"))
        article = expected_articles.get(article_id)
        if (
            article is None
            or article_id in sources
            or slug != article.production_slug
            or SLUG_RE.fullmatch(slug) is None
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
        source = _read_owner_regular_file(
            article_root / f"{slug}.html",
            maximum=MAX_TRACKED_HTML_BYTES,
        )
        if _sha256_bytes(source) != digest:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
        image_count, cta_count = _validate_v2_completion_html(
            article=article,
            source=source,
            mode=mode,
            verified_evidence=verified_evidence.products,
        )
        verified_product_card_count += image_count
        verified_affiliate_cta_count += cta_count
        sources[article_id] = source
        article_rows.append(
            {
                "article_id": article_id,
                "production_slug": slug,
                "content_sha256": digest,
            }
        )
    if set(sources) != set(expected_articles):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")
    expected_product_ids = {product.product_id for product in portfolio.products}
    products: list[dict[str, str]] = []
    seen_products: set[str] = set()
    for raw in _rows(receipt.get("products")):
        _exact_keys(raw, {"product_id", "state", "provider_binding_sha256"})
        product_id = _text(raw.get("product_id"))
        state = _text(raw.get("state"))
        provider_binding_sha256 = _sha256(raw.get("provider_binding_sha256"))
        evidence = verified_evidence.products.get(product_id)
        if (
            product_id not in expected_product_ids
            or product_id in seen_products
            or PRODUCT_ID_RE.fullmatch(product_id) is None
            or state != "verified"
            or evidence is None
            or provider_binding_sha256 != evidence.provider_binding_sha256
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        seen_products.add(product_id)
        products.append(
            {
                "product_id": product_id,
                "state": state,
                "provider_binding_sha256": provider_binding_sha256,
            }
        )
    if seen_products != expected_product_ids:
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")
    media: list[dict[str, str]] = []
    seen_media: set[str] = set()
    for raw in _rows(receipt.get("media")):
        _exact_keys(raw, {"product_id", "image_sha256", "image_extension"})
        product_id = _text(raw.get("product_id"))
        image_sha256 = _sha256(raw.get("image_sha256"))
        image_extension = _text(raw.get("image_extension"), maximum=3)
        evidence = verified_evidence.products.get(product_id)
        if (
            product_id not in expected_product_ids
            or product_id in seen_media
            or evidence is None
            or image_sha256 != evidence.image_sha256
            or image_extension != evidence.image_extension
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        seen_media.add(product_id)
        media.append(
            {
                "product_id": product_id,
                "image_sha256": image_sha256,
                "image_extension": image_extension,
            }
        )
    if seen_media != expected_product_ids:
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
    if mode == "local":
        media_root = _owner_directory(fixture_root.parent / "product-media")
        try:
            actual_media_names = {path.name for path in media_root.iterdir()}
        except OSError:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        expected_media_names = {
            f"{row['product_id']}.{row['image_extension']}" for row in media
        }
        if actual_media_names != expected_media_names:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
        for row in media:
            payload = _read_owner_regular_file(
                media_root / f"{row['product_id']}.{row['image_extension']}",
                maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            )
            if _sha256_bytes(payload) != row["image_sha256"]:
                _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
    completion = _mapping(receipt.get("completion"))
    _exact_keys(
        completion,
        {
            "state",
            "product_count",
            "verified_product_count",
            "product_card_count",
            "verified_product_card_count",
            "affiliate_cta_count",
            "verified_affiliate_cta_count",
            "neutral_product_image_count",
            "manufacturer_fallback_cta_count",
            "measurement_collection_enabled",
        },
    )
    expected_product_count = len(expected_product_ids)
    if completion != {
        "state": "COMPLETE",
        "product_count": expected_product_count,
        "verified_product_count": expected_product_count,
        "product_card_count": EXPECTED_PRODUCT_CARD_COUNT,
        "verified_product_card_count": EXPECTED_PRODUCT_CARD_COUNT,
        "affiliate_cta_count": EXPECTED_AFFILIATE_CTA_COUNT,
        "verified_affiliate_cta_count": EXPECTED_AFFILIATE_CTA_COUNT,
        "neutral_product_image_count": 0,
        "manufacturer_fallback_cta_count": 0,
        "measurement_collection_enabled": False,
    } or (
        verified_product_card_count != EXPECTED_PRODUCT_CARD_COUNT
        or verified_affiliate_cta_count != EXPECTED_AFFILIATE_CTA_COUNT
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INCOMPLETE")
    return {
        "generated_at": generated_at,
        "portfolio_sha256": expected_v2_portfolio_sha256,
        "evidence_status_sha256": evidence_status_sha256,
        "manufacturer_sales_state_sha256": manufacturer_sales_state_sha256,
        "manufacturer_sales_state_checked_at_utc": (
            manufacturer_sales_state_checked_at_utc
        ),
        "product_safety": product_safety,
        "receipt_raw": receipt_raw,
        "posts_raw": posts_raw,
        "sources": sources,
        "article_rows": article_rows,
        "products": products,
        "media": media,
        "completion": completion,
    }


def _require_v2_materializations_current(
    *,
    repository_root: Path,
    portfolio: EditorialPortfolioV3,
    local_fixture_root: Path,
    production_fixture_root: Path,
    expected_evidence: _VerifiedV2EvidenceSet,
    expected_local: Mapping[str, object],
    expected_production: Mapping[str, object],
    require_recent: bool,
) -> None:
    """Reopen every V2 source and prove it is the original input snapshot."""

    current_now = datetime.now(UTC)
    try:
        current_evidence = _load_verified_v2_evidence(
            repository_root,
            now=current_now,
        )
        current_local = _v2_materialization(
            repository_root=repository_root,
            fixture_root=local_fixture_root,
            mode="local",
            portfolio=portfolio,
            verified_evidence=current_evidence,
        )
        current_production = _v2_materialization(
            repository_root=repository_root,
            fixture_root=production_fixture_root,
            mode="production",
            portfolio=portfolio,
            verified_evidence=current_evidence,
        )
    except RakutenMeasurementActivationV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    for source in (current_local, current_production):
        generated = datetime.fromisoformat(
            cast(str, source["generated_at"]).replace("Z", "+00:00")
        )
        if generated > current_now + timedelta(seconds=30) or (
            require_recent and current_now - generated > timedelta(minutes=15)
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    if current_local != expected_local or current_production != expected_production:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    try:
        final_evidence = _load_verified_v2_evidence(
            repository_root,
            now=datetime.now(UTC),
        )
        final_local_receipt = _read_owner_regular_file(
            local_fixture_root / "materialization-receipt.v2.json",
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            exact_mode=0o600,
        )
        final_production_receipt = _read_owner_regular_file(
            production_fixture_root / "materialization-receipt.v2.json",
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            exact_mode=0o600,
        )
    except RakutenMeasurementActivationV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    if (
        current_evidence != expected_evidence
        or final_evidence != expected_evidence
        or final_local_receipt != expected_local.get("receipt_raw")
        or final_production_receipt != expected_production.get("receipt_raw")
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")


def _article_set_sha256(rows: list[dict[str, object]]) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "article_id": row["article_id"],
                    "production_slug": row["production_slug"],
                    "sha256": row["materialized_sha256"],
                }
                for row in rows
            ]
        )
    )


def _write_overlay(
    *,
    private_root: Path,
    directory_name: str,
    posts_raw: bytes,
    articles: Mapping[str, bytes],
    receipt_raw: bytes,
) -> Path:
    overlay_root = private_root / directory_name
    article_root = overlay_root / "articles"
    try:
        overlay_root.mkdir(mode=0o700, parents=False, exist_ok=True)
        overlay_metadata = overlay_root.lstat()
        article_root.mkdir(mode=0o700, parents=False, exist_ok=True)
        article_metadata = article_root.lstat()
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    if (
        overlay_root.is_symlink()
        or not stat.S_ISDIR(overlay_metadata.st_mode)
        or overlay_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(overlay_metadata.st_mode) != 0o700
        or article_root.is_symlink()
        or not stat.S_ISDIR(article_metadata.st_mode)
        or article_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(article_metadata.st_mode) != 0o700
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    try:
        write_private_bytes(overlay_root, "posts.json", posts_raw)
        for slug, content in articles.items():
            write_private_bytes(article_root, f"{slug}.html", content)
        write_private_bytes(
            overlay_root,
            "materialization-receipt.v3.json",
            receipt_raw,
        )
    except EditorialEconomicsV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    try:
        root_names = {path.name for path in overlay_root.iterdir()}
        article_names = {path.name for path in article_root.iterdir()}
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    if root_names != {
        "articles",
        "posts.json",
        "materialization-receipt.v3.json",
    } or article_names != {f"{slug}.html" for slug in articles}:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    return overlay_root


def materialize_rakuten_measurement_activation_v3(
    *,
    repository_root: Path,
    private_root: Path,
    portfolio: EditorialPortfolioV3,
    admin_receipt_name: str,
    money_link_mapping_name: str,
    dry_run_output_name: str,
    local_v2_fixture_root: Path | None = None,
    production_v2_fixture_root: Path | None = None,
) -> Mapping[str, object]:
    """Validate private evidence and write only owner-private dry-run outputs."""

    if not repository_root.is_absolute() or not private_root.is_absolute():
        _fail("RAOS_RAKUTEN_ACTIVATION_ROOT_INVALID")
    private_names = {
        admin_receipt_name,
        money_link_mapping_name,
        dry_run_output_name,
    }
    if len(private_names) != 3:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_NAME_INVALID")
    try:
        portfolio_raw = _read_regular_file(
            repository_root / PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
        admin_raw = read_private_bytes(private_root, admin_receipt_name)
        mapping_raw = read_private_bytes(private_root, money_link_mapping_name)
    except EditorialEconomicsV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_INPUT_INVALID")
    portfolio_sha256 = _sha256_bytes(portfolio_raw)
    if portfolio_sha256 != portfolio.source_sha256:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    mapping_sha256 = _sha256_bytes(mapping_raw)
    admin_document = _json_document(admin_raw)
    mapping_document = _json_document(mapping_raw)
    _reject_formula_like_strings(admin_document)
    _reject_formula_like_strings(mapping_document)
    expected = _expected_bindings(portfolio)
    try:
        v2 = load_editorial_portfolio_v2(repository_root)
    except EditorialPortfolioV2Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    representative_models = {
        product.product_id: product.representative_model for product in v2.products
    }
    if set(representative_models) != {
        product.product_id for product in portfolio.products
    }:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    urls = _mapping_urls(
        mapping_document,
        portfolio_sha256=portfolio_sha256,
        expected=expected,
        representative_models=representative_models,
    )
    _validate_admin_receipt(
        admin_document,
        portfolio_sha256=portfolio_sha256,
        mapping_sha256=mapping_sha256,
        expected=expected,
        representative_models=representative_models,
    )
    activated_at = datetime.now(UTC)
    activated_at_utc = activated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    mapping_generated_at_utc, admin_verified_at_utc, activated_at_utc = (
        _validate_activation_time_chain(
            mapping_generated_at=mapping_document.get("generated_at"),
            admin_verified_at=admin_document.get("verified_at"),
            activated_at=activated_at_utc,
            now=activated_at,
            require_recent=True,
        )
    )
    verified_evidence = _load_verified_v2_evidence(
        repository_root,
        now=activated_at,
    )
    default_local, default_production = _default_v2_fixture_roots(repository_root)
    local_source_root = local_v2_fixture_root or default_local
    production_source_root = production_v2_fixture_root or default_production
    local_source = _v2_materialization(
        repository_root=repository_root,
        fixture_root=local_source_root,
        mode="local",
        portfolio=portfolio,
        verified_evidence=verified_evidence,
    )
    production_source = _v2_materialization(
        repository_root=repository_root,
        fixture_root=production_source_root,
        mode="production",
        portfolio=portfolio,
        verified_evidence=verified_evidence,
    )
    for source in (local_source, production_source):
        generated = datetime.fromisoformat(
            cast(str, source["generated_at"]).replace("Z", "+00:00")
        )
        if generated > activated_at + timedelta(
            seconds=30
        ) or activated_at - generated > timedelta(minutes=15):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_STALE")
    if (
        local_source["portfolio_sha256"] != production_source["portfolio_sha256"]
        or local_source["evidence_status_sha256"]
        != production_source["evidence_status_sha256"]
        or local_source["manufacturer_sales_state_sha256"]
        != production_source["manufacturer_sales_state_sha256"]
        or local_source["manufacturer_sales_state_checked_at_utc"]
        != production_source["manufacturer_sales_state_checked_at_utc"]
        or local_source["product_safety"] != production_source["product_safety"]
        or local_source["products"] != production_source["products"]
        or local_source["media"] != production_source["media"]
        or local_source["completion"] != production_source["completion"]
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_PAIR_INVALID")
    overlays: dict[str, dict[str, object]] = {}
    overlay_payloads: dict[str, dict[str, bytes]] = {}
    overlay_receipts: dict[str, bytes] = {}
    for mode, source in (
        ("local", local_source),
        ("production", production_source),
    ):
        sources = cast(dict[str, bytes], source["sources"])
        materialized: dict[str, bytes] = {}
        rows: list[dict[str, object]] = []
        for article in portfolio.articles:
            original = sources[article.article_id]
            output = materialize_article_html(article, original, urls)
            materialized[article.production_slug] = output
            rows.append(
                {
                    "article_id": article.article_id,
                    "production_slug": article.production_slug,
                    "source_sha256": _sha256_bytes(original),
                    "materialized_sha256": _sha256_bytes(output),
                    "cta_count": len(article.cta_bindings),
                }
            )
        article_set_sha256 = _article_set_sha256(rows)
        overlay_receipt: Mapping[str, object] = {
            "schema": OVERLAY_RECEIPT_SCHEMA,
            "version": "1.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": source["portfolio_sha256"],
            "v2_evidence_status_sha256": source["evidence_status_sha256"],
            "v2_manufacturer_sales_state_sha256": source[
                "manufacturer_sales_state_sha256"
            ],
            "v2_manufacturer_sales_state_checked_at_utc": source[
                "manufacturer_sales_state_checked_at_utc"
            ],
            "v2_materialization_receipt_sha256": _sha256_bytes(
                cast(bytes, source["receipt_raw"])
            ),
            "posts_sha256": _sha256_bytes(cast(bytes, source["posts_raw"])),
            "article_set_sha256": article_set_sha256,
            "article_count": len(rows),
            "cta_count": sum(cast(int, row["cta_count"]) for row in rows),
            "articles": rows,
        }
        overlay_receipt_raw = canonical_json_bytes(overlay_receipt)
        overlay_receipt_sha256 = _sha256_bytes(overlay_receipt_raw)
        prefix = LOCAL_OVERLAY_PREFIX if mode == "local" else PRODUCTION_OVERLAY_PREFIX
        directory_name = prefix + overlay_receipt_sha256[:16]
        overlays[mode] = {
            "directory_name": directory_name,
            "posts_sha256": overlay_receipt["posts_sha256"],
            "article_set_sha256": article_set_sha256,
            "overlay_receipt_sha256": overlay_receipt_sha256,
            "articles": rows,
        }
        overlay_payloads[mode] = materialized
        overlay_receipts[mode] = overlay_receipt_raw
    materialized_set_sha256 = _sha256_bytes(
        canonical_json_bytes(
            {
                mode: {
                    "posts_sha256": overlays[mode]["posts_sha256"],
                    "article_set_sha256": overlays[mode]["article_set_sha256"],
                    "overlay_receipt_sha256": overlays[mode]["overlay_receipt_sha256"],
                }
                for mode in ("local", "production")
            }
        )
    )
    report: Mapping[str, object] = {
        "schema": DRY_RUN_SCHEMA,
        "version": "2.1.0",
        "state": "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED",
        "portfolio_sha256": portfolio_sha256,
        "admin_receipt_sha256": _sha256_bytes(admin_raw),
        "money_link_mapping_sha256": mapping_sha256,
        "activation_inputs": {
            "admin_receipt_name": admin_receipt_name,
            "money_link_mapping_name": money_link_mapping_name,
            "mapping_generated_at_utc": mapping_generated_at_utc,
            "admin_verified_at_utc": admin_verified_at_utc,
            "activated_at_utc": activated_at_utc,
        },
        "v2_materialization": {
            "portfolio_sha256": local_source["portfolio_sha256"],
            "evidence_status_sha256": local_source["evidence_status_sha256"],
            "manufacturer_sales_state_sha256": local_source[
                "manufacturer_sales_state_sha256"
            ],
            "manufacturer_sales_state_checked_at_utc": local_source[
                "manufacturer_sales_state_checked_at_utc"
            ],
            "local_generated_at": local_source["generated_at"],
            "production_generated_at": production_source["generated_at"],
            "local_receipt_sha256": _sha256_bytes(
                cast(bytes, local_source["receipt_raw"])
            ),
            "production_receipt_sha256": _sha256_bytes(
                cast(bytes, production_source["receipt_raw"])
            ),
        },
        "overlays": overlays,
        "materialized_set_sha256": materialized_set_sha256,
        "article_count": len(portfolio.articles),
        "cta_count": sum(len(article.cta_bindings) for article in portfolio.articles),
        "provider_parameter_inference_used": False,
        "tracked_source_modified": False,
        "live_write_performed": False,
        "publication_authorized": False,
    }
    try:
        for mode, source in (
            ("local", local_source),
            ("production", production_source),
        ):
            overlay = overlays[mode]
            _write_overlay(
                private_root=private_root,
                directory_name=cast(str, overlay["directory_name"]),
                posts_raw=cast(bytes, source["posts_raw"]),
                articles=overlay_payloads[mode],
                receipt_raw=overlay_receipts[mode],
            )
        write_private_bytes(
            private_root,
            dry_run_output_name,
            canonical_json_bytes(report),
        )
    except EditorialEconomicsV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_OUTPUT_INVALID")
    try:
        current_portfolio_raw = _read_regular_file(
            repository_root / PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
        current_admin_raw = read_private_bytes(private_root, admin_receipt_name)
        current_mapping_raw = read_private_bytes(private_root, money_link_mapping_name)
    except EditorialEconomicsV3Failure, RakutenMeasurementActivationV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    if (
        current_portfolio_raw != portfolio_raw
        or current_admin_raw != admin_raw
        or current_mapping_raw != mapping_raw
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    _require_v2_materializations_current(
        repository_root=repository_root,
        portfolio=portfolio,
        local_fixture_root=local_source_root,
        production_fixture_root=production_source_root,
        expected_evidence=verified_evidence,
        expected_local=local_source,
        expected_production=production_source,
        require_recent=True,
    )
    try:
        final_portfolio_raw = _read_regular_file(
            repository_root / PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
        final_admin_raw = read_private_bytes(private_root, admin_receipt_name)
        final_mapping_raw = read_private_bytes(private_root, money_link_mapping_name)
    except EditorialEconomicsV3Failure, RakutenMeasurementActivationV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    if (
        final_portfolio_raw != portfolio_raw
        or final_admin_raw != admin_raw
        or final_mapping_raw != mapping_raw
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    return report


def _reject_urls_in_receipt(value: object) -> None:
    if type(value) is str:
        if "://" in value or AFFILIATE_HOST in value:
            _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
        return
    if type(value) is list:
        for child in cast(list[object], value):
            _reject_urls_in_receipt(child)
        return
    if type(value) is dict:
        for child in cast(dict[object, object], value).values():
            _reject_urls_in_receipt(child)


def _validate_overlay_output(
    *,
    private_root: Path,
    raw: Mapping[str, object],
    mode: str,
    portfolio: EditorialPortfolioV3,
    portfolio_sha256: str,
    v2_materialization: Mapping[str, object],
    verified_evidence: _VerifiedV2EvidenceSet,
    expected_urls: Mapping[tuple[str, str, str], str],
) -> tuple[Path, str, str, Mapping[str, str]]:
    _exact_keys(
        raw,
        {
            "directory_name",
            "posts_sha256",
            "article_set_sha256",
            "overlay_receipt_sha256",
            "articles",
        },
    )
    directory_name = _text(raw.get("directory_name"), maximum=96)
    expected_prefix = (
        LOCAL_OVERLAY_PREFIX if mode == "local" else PRODUCTION_OVERLAY_PREFIX
    )
    if (
        re.fullmatch(re.escape(expected_prefix) + r"[0-9a-f]{16}", directory_name)
        is None
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    posts_sha256 = _sha256(raw.get("posts_sha256"))
    article_set_sha256 = _sha256(raw.get("article_set_sha256"))
    overlay_receipt_sha256 = _sha256(raw.get("overlay_receipt_sha256"))
    overlay_root = _owner_directory(private_root / directory_name, exact_mode=0o700)
    article_root = _owner_directory(overlay_root / "articles", exact_mode=0o700)
    try:
        if {path.name for path in overlay_root.iterdir()} != {
            "articles",
            "posts.json",
            "materialization-receipt.v3.json",
        }:
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    posts_raw = _read_owner_regular_file(
        overlay_root / "posts.json",
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    receipt_raw = _read_owner_regular_file(
        overlay_root / "materialization-receipt.v3.json",
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    if (
        _sha256_bytes(posts_raw) != posts_sha256
        or _sha256_bytes(receipt_raw) != overlay_receipt_sha256
        or not directory_name.endswith(overlay_receipt_sha256[:16])
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    receipt = _json_document(receipt_raw)
    _exact_keys(
        receipt,
        {
            "schema",
            "version",
            "mode",
            "portfolio_sha256",
            "v2_portfolio_sha256",
            "v2_evidence_status_sha256",
            "v2_manufacturer_sales_state_sha256",
            "v2_manufacturer_sales_state_checked_at_utc",
            "v2_materialization_receipt_sha256",
            "posts_sha256",
            "article_set_sha256",
            "article_count",
            "cta_count",
            "articles",
        },
    )
    expected_v2_receipt_key = f"{mode}_receipt_sha256"
    if (
        receipt.get("schema") != OVERLAY_RECEIPT_SCHEMA
        or receipt.get("version") != "1.0.0"
        or receipt.get("mode") != mode
        or receipt.get("portfolio_sha256") != portfolio_sha256
        or receipt.get("v2_portfolio_sha256")
        != v2_materialization.get("portfolio_sha256")
        or receipt.get("v2_evidence_status_sha256")
        != v2_materialization.get("evidence_status_sha256")
        or receipt.get("v2_manufacturer_sales_state_sha256")
        != v2_materialization.get("manufacturer_sales_state_sha256")
        or receipt.get("v2_manufacturer_sales_state_checked_at_utc")
        != v2_materialization.get("manufacturer_sales_state_checked_at_utc")
        or receipt.get("v2_materialization_receipt_sha256")
        != v2_materialization.get(expected_v2_receipt_key)
        or receipt.get("posts_sha256") != posts_sha256
        or receipt.get("article_set_sha256") != article_set_sha256
        or receipt.get("article_count") != 10
        or receipt.get("cta_count") != EXPECTED_AFFILIATE_CTA_COUNT
        or receipt.get("articles") != raw.get("articles")
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    expected_by_id = portfolio.article_by_id
    article_rows: list[dict[str, object]] = []
    article_hashes: dict[str, str] = {}
    total_ctas = 0
    expected_names: set[str] = set()
    for row in _rows(raw.get("articles")):
        _exact_keys(
            row,
            {
                "article_id",
                "production_slug",
                "source_sha256",
                "materialized_sha256",
                "cta_count",
            },
        )
        article_id = _text(row.get("article_id"))
        slug = _text(row.get("production_slug"))
        source_sha256 = _sha256(row.get("source_sha256"))
        materialized_sha256 = _sha256(row.get("materialized_sha256"))
        cta_count = row.get("cta_count")
        article = expected_by_id.get(article_id)
        if (
            article is None
            or slug != article.production_slug
            or slug in article_hashes
            or type(cta_count) is not int
            or cta_count != len(article.cta_bindings)
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        content = _read_owner_regular_file(
            article_root / f"{slug}.html",
            maximum=MAX_TRACKED_HTML_BYTES,
            exact_mode=0o600,
        )
        if (
            _sha256_bytes(content) != materialized_sha256
            or content.count(b"https://hb.afl.rakuten.co.jp/") != cta_count
            or "一致する楽天商品を確認できなかったため".encode() in content
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        try:
            markup = content.decode("utf-8", errors="strict")
        except UnicodeError:
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        try:
            image_count, validated_cta_count = _validate_v2_completion_html(
                article=article,
                source=content,
                mode=mode,
                verified_evidence=verified_evidence.products,
            )
        except RakutenMeasurementActivationV3Failure:
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        if image_count != len(article.product_ids) or validated_cta_count != cta_count:
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        anchors = list(CTA_ANCHOR_RE.finditer(markup))
        expected_bindings = {
            (binding.product_id, binding.placement): binding
            for binding in article.cta_bindings
        }
        observed: set[tuple[str, str]] = set()
        for anchor in anchors:
            attributes = _anchor_attributes(anchor.group(1))
            data_attributes = {
                name for name in attributes if name.startswith("data-raos-")
            }
            required_data_attributes = {
                "data-raos-article-id",
                "data-raos-cta-id",
                "data-raos-snapshot-id",
                "data-raos-offer-id",
                "data-raos-product-id",
                "data-raos-placement",
                "data-raos-rakuten-measurement-id",
            }
            identity = (
                attributes.get("data-raos-product-id", ""),
                attributes.get("data-raos-placement", ""),
            )
            binding = expected_bindings.get(identity)
            href = attributes.get("href")
            expected_href = expected_urls.get((article_id, *identity))
            if (
                data_attributes != required_data_attributes
                or binding is None
                or identity in observed
                or href is None
                or href != expected_href
                or attributes.get("rel") != "sponsored nofollow"
                or attributes.get("data-raos-article-id") != binding.article_id
                or attributes.get("data-raos-cta-id") != binding.cta_id
                or attributes.get("data-raos-snapshot-id") != binding.snapshot_id
                or attributes.get("data-raos-offer-id") != binding.offer_id
                or attributes.get("data-raos-rakuten-measurement-id")
                != binding.rakuten_measurement_id
            ):
                _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
            _validate_money_link_url(href)
            observed.add(identity)
        if observed != set(expected_bindings):
            _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
        article_hashes[slug] = materialized_sha256
        expected_names.add(f"{slug}.html")
        total_ctas += cta_count
        article_rows.append(
            {
                "article_id": article_id,
                "production_slug": slug,
                "source_sha256": source_sha256,
                "materialized_sha256": materialized_sha256,
                "cta_count": cta_count,
            }
        )
    try:
        actual_names = {path.name for path in article_root.iterdir()}
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    if (
        set(article_hashes)
        != {article.production_slug for article in portfolio.articles}
        or actual_names != expected_names
        or total_ctas != EXPECTED_AFFILIATE_CTA_COUNT
        or _article_set_sha256(article_rows) != article_set_sha256
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    return (
        overlay_root,
        article_set_sha256,
        overlay_receipt_sha256,
        dict(sorted(article_hashes.items())),
    )


def validate_rakuten_measurement_activation_v3(
    *,
    repository_root: Path,
    dry_run_path: Path,
    portfolio: EditorialPortfolioV3,
    local_v2_fixture_root: Path | None = None,
    production_v2_fixture_root: Path | None = None,
    require_recent: bool = True,
) -> RakutenMeasurementActivationOverlayV3:
    """Validate one dry-run and both immutable overlay fixtures for publication."""

    if not repository_root.is_absolute() or not dry_run_path.is_absolute():
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    private_root = _owner_directory(dry_run_path.parent, exact_mode=0o700)
    try:
        lexical = Path(os.path.abspath(dry_run_path))
        resolved = dry_run_path.resolve(strict=True)
    except OSError:
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    if lexical != resolved or resolved.parent != private_root:
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    dry_run_raw = _read_owner_regular_file(
        resolved,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    document = _json_document(dry_run_raw)
    _reject_urls_in_receipt(document)
    _exact_keys(
        document,
        {
            "schema",
            "version",
            "state",
            "portfolio_sha256",
            "admin_receipt_sha256",
            "money_link_mapping_sha256",
            "activation_inputs",
            "v2_materialization",
            "overlays",
            "materialized_set_sha256",
            "article_count",
            "cta_count",
            "provider_parameter_inference_used",
            "tracked_source_modified",
            "live_write_performed",
            "publication_authorized",
        },
    )
    portfolio_raw = _read_regular_file(
        repository_root / PORTFOLIO_RELATIVE_PATH,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    portfolio_sha256 = _sha256_bytes(portfolio_raw)
    if portfolio_sha256 != portfolio.source_sha256:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    admin_receipt_sha256 = _sha256(document.get("admin_receipt_sha256"))
    money_link_mapping_sha256 = _sha256(document.get("money_link_mapping_sha256"))
    materialized_set_sha256 = _sha256(document.get("materialized_set_sha256"))
    if (
        document.get("schema") != DRY_RUN_SCHEMA
        or document.get("version") != "2.1.0"
        or document.get("state") != "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or document.get("article_count") != 10
        or document.get("cta_count") != EXPECTED_AFFILIATE_CTA_COUNT
        or document.get("provider_parameter_inference_used") is not False
        or document.get("tracked_source_modified") is not False
        or document.get("live_write_performed") is not False
        or document.get("publication_authorized") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    activation_inputs = _mapping(document.get("activation_inputs"))
    _exact_keys(
        activation_inputs,
        {
            "admin_receipt_name",
            "money_link_mapping_name",
            "mapping_generated_at_utc",
            "admin_verified_at_utc",
            "activated_at_utc",
        },
    )
    admin_receipt_name = _text(
        activation_inputs.get("admin_receipt_name"), maximum=255
    )
    money_link_mapping_name = _text(
        activation_inputs.get("money_link_mapping_name"), maximum=255
    )
    if len({resolved.name, admin_receipt_name, money_link_mapping_name}) != 3:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_NAME_INVALID")
    try:
        admin_raw = read_private_bytes(private_root, admin_receipt_name)
        mapping_raw = read_private_bytes(private_root, money_link_mapping_name)
    except EditorialEconomicsV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PRIVATE_INPUT_INVALID")
    if (
        _sha256_bytes(admin_raw) != admin_receipt_sha256
        or _sha256_bytes(mapping_raw) != money_link_mapping_sha256
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    admin_document = _json_document(admin_raw)
    mapping_document = _json_document(mapping_raw)
    _reject_formula_like_strings(admin_document)
    _reject_formula_like_strings(mapping_document)
    expected_bindings = _expected_bindings(portfolio)
    try:
        portfolio_v2 = load_editorial_portfolio_v2(repository_root)
    except EditorialPortfolioV2Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    representative_models = {
        product.product_id: product.representative_model
        for product in portfolio_v2.products
    }
    if set(representative_models) != {
        product.product_id for product in portfolio.products
    }:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    urls = _mapping_urls(
        mapping_document,
        portfolio_sha256=portfolio_sha256,
        expected=expected_bindings,
        representative_models=representative_models,
    )
    _validate_admin_receipt(
        admin_document,
        portfolio_sha256=portfolio_sha256,
        mapping_sha256=money_link_mapping_sha256,
        expected=expected_bindings,
        representative_models=representative_models,
    )
    now = datetime.now(UTC)
    mapping_generated_at_utc, admin_verified_at_utc, activated_at_utc = (
        _validate_activation_time_chain(
            mapping_generated_at=mapping_document.get("generated_at"),
            admin_verified_at=admin_document.get("verified_at"),
            activated_at=activation_inputs.get("activated_at_utc"),
            now=now,
            require_recent=require_recent,
        )
    )
    if (
        activation_inputs.get("mapping_generated_at_utc")
        != mapping_generated_at_utc
        or activation_inputs.get("admin_verified_at_utc") != admin_verified_at_utc
        or activation_inputs.get("activated_at_utc") != activated_at_utc
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    v2 = _mapping(document.get("v2_materialization"))
    _exact_keys(
        v2,
        {
            "portfolio_sha256",
            "evidence_status_sha256",
            "manufacturer_sales_state_sha256",
            "manufacturer_sales_state_checked_at_utc",
            "local_generated_at",
            "production_generated_at",
            "local_receipt_sha256",
            "production_receipt_sha256",
        },
    )
    v2_portfolio_sha256 = _sha256(v2.get("portfolio_sha256"))
    v2_evidence_status_sha256 = _sha256(v2.get("evidence_status_sha256"))
    v2_manufacturer_sales_state_sha256 = _sha256(
        v2.get("manufacturer_sales_state_sha256")
    )
    v2_manufacturer_sales_state_checked_at_utc = _timestamp(
        v2.get("manufacturer_sales_state_checked_at_utc")
    )
    local_receipt_sha256 = _sha256(v2.get("local_receipt_sha256"))
    production_receipt_sha256 = _sha256(v2.get("production_receipt_sha256"))
    generated_values = [
        _timestamp(v2.get("local_generated_at")),
        _timestamp(v2.get("production_generated_at")),
    ]
    activation_time = datetime.fromisoformat(
        activated_at_utc.replace("Z", "+00:00")
    )
    for value in generated_values:
        generated = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            generated > activation_time + MAX_FUTURE_SKEW
            or activation_time - generated > MAX_VERIFICATION_TO_ACTIVATION_AGE
            or generated > now + MAX_FUTURE_SKEW
            or (require_recent and now - generated > timedelta(minutes=15))
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_STALE")
    verified_evidence = _load_verified_v2_evidence(
        repository_root,
        now=now,
    )
    v2_product_safety = _validate_product_safety_publication_binding(
        verified_evidence.product_safety,
        require_complete=True,
    )
    default_local, default_production = _default_v2_fixture_roots(repository_root)
    local_source_root = local_v2_fixture_root or default_local
    production_source_root = production_v2_fixture_root or default_production
    current_v2: dict[str, dict[str, object]] = {}
    for mode, source_root, expected_sha256 in (
        (
            "local",
            local_source_root,
            local_receipt_sha256,
        ),
        (
            "production",
            production_source_root,
            production_receipt_sha256,
        ),
    ):
        source = _v2_materialization(
            repository_root=repository_root,
            fixture_root=source_root,
            mode=mode,
            portfolio=portfolio,
            verified_evidence=verified_evidence,
        )
        if (
            _sha256_bytes(cast(bytes, source["receipt_raw"])) != expected_sha256
            or source["portfolio_sha256"] != v2_portfolio_sha256
            or source["evidence_status_sha256"] != v2_evidence_status_sha256
            or source["manufacturer_sales_state_sha256"]
            != v2_manufacturer_sales_state_sha256
            or source["manufacturer_sales_state_checked_at_utc"]
            != v2_manufacturer_sales_state_checked_at_utc
            or source["product_safety"] != v2_product_safety
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_SOURCE_DRIFT")
        current_v2[mode] = source
    if (
        current_v2["local"]["products"] != current_v2["production"]["products"]
        or current_v2["local"]["manufacturer_sales_state_sha256"]
        != current_v2["production"]["manufacturer_sales_state_sha256"]
        or current_v2["local"]["manufacturer_sales_state_checked_at_utc"]
        != current_v2["production"]["manufacturer_sales_state_checked_at_utc"]
        or current_v2["local"]["product_safety"]
        != current_v2["production"]["product_safety"]
        or current_v2["local"]["media"] != current_v2["production"]["media"]
        or current_v2["local"]["completion"] != current_v2["production"]["completion"]
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_SOURCE_DRIFT")
    overlays = _mapping(document.get("overlays"))
    _exact_keys(overlays, {"local", "production"})
    local = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays.get("local")),
        mode="local",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        v2_materialization=v2,
        verified_evidence=verified_evidence,
        expected_urls=urls,
    )
    production = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays.get("production")),
        mode="production",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        v2_materialization=v2,
        verified_evidence=verified_evidence,
        expected_urls=urls,
    )
    computed_set_sha256 = _sha256_bytes(
        canonical_json_bytes(
            {
                "local": {
                    "posts_sha256": _mapping(overlays["local"])["posts_sha256"],
                    "article_set_sha256": local[1],
                    "overlay_receipt_sha256": local[2],
                },
                "production": {
                    "posts_sha256": _mapping(overlays["production"])["posts_sha256"],
                    "article_set_sha256": production[1],
                    "overlay_receipt_sha256": production[2],
                },
            }
        )
    )
    if computed_set_sha256 != materialized_set_sha256:
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    current_portfolio_raw = _read_regular_file(
        repository_root / PORTFOLIO_RELATIVE_PATH,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
    )
    current_dry_run_raw = _read_owner_regular_file(
        resolved,
        maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        exact_mode=0o600,
    )
    if current_portfolio_raw != portfolio_raw or current_dry_run_raw != dry_run_raw:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    _require_v2_materializations_current(
        repository_root=repository_root,
        portfolio=portfolio,
        local_fixture_root=local_source_root,
        production_fixture_root=production_source_root,
        expected_evidence=verified_evidence,
        expected_local=current_v2["local"],
        expected_production=current_v2["production"],
        require_recent=require_recent,
    )
    final_local = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays["local"]),
        mode="local",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        v2_materialization=v2,
        verified_evidence=verified_evidence,
        expected_urls=urls,
    )
    final_production = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays["production"]),
        mode="production",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        v2_materialization=v2,
        verified_evidence=verified_evidence,
        expected_urls=urls,
    )
    if final_local != local or final_production != production:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    try:
        final_admin_raw = read_private_bytes(private_root, admin_receipt_name)
        final_mapping_raw = read_private_bytes(private_root, money_link_mapping_name)
    except EditorialEconomicsV3Failure:
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    if (
        _read_regular_file(
            repository_root / PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
        )
        != portfolio_raw
        or _read_owner_regular_file(
            resolved,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            exact_mode=0o600,
        )
        != dry_run_raw
        or final_admin_raw != admin_raw
        or final_mapping_raw != mapping_raw
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_SOURCE_CHANGED")
    return RakutenMeasurementActivationOverlayV3(
        dry_run_sha256=_sha256_bytes(dry_run_raw),
        portfolio_sha256=portfolio_sha256,
        v2_portfolio_sha256=v2_portfolio_sha256,
        v2_evidence_status_sha256=v2_evidence_status_sha256,
        v2_manufacturer_sales_state_sha256=(v2_manufacturer_sales_state_sha256),
        v2_manufacturer_sales_state_checked_at_utc=(
            v2_manufacturer_sales_state_checked_at_utc
        ),
        v2_product_safety=v2_product_safety,
        v2_local_receipt_sha256=local_receipt_sha256,
        v2_production_receipt_sha256=production_receipt_sha256,
        admin_receipt_sha256=admin_receipt_sha256,
        money_link_mapping_sha256=money_link_mapping_sha256,
        mapping_generated_at_utc=mapping_generated_at_utc,
        admin_verified_at_utc=admin_verified_at_utc,
        activated_at_utc=activated_at_utc,
        materialized_set_sha256=materialized_set_sha256,
        local_fixture_root=local[0],
        production_fixture_root=production[0],
        local_article_set_sha256=local[1],
        production_article_set_sha256=production[1],
        local_overlay_receipt_sha256=local[2],
        production_overlay_receipt_sha256=production[2],
        local_article_sha256=local[3],
        production_article_sha256=production[3],
        article_count=10,
        cta_count=EXPECTED_AFFILIATE_CTA_COUNT,
    )


__all__ = [
    "ADMIN_RECEIPT_SCHEMA",
    "DRY_RUN_SCHEMA",
    "MONEY_LINK_MAPPING_SCHEMA",
    "OVERLAY_RECEIPT_SCHEMA",
    "RakutenMeasurementActivationOverlayV3",
    "RakutenMeasurementActivationV3Failure",
    "admin_verification_receipt_template_v3",
    "materialize_article_html",
    "materialize_rakuten_measurement_activation_v3",
    "money_link_mapping_template_v3",
    "validate_rakuten_measurement_activation_v3",
]
