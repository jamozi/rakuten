"""Fail-closed owner-private activation of Editorial V3 Rakuten Money Links.

The tracked Editorial V3 contract deliberately keeps every provider profile in
``UNVERIFIED_DISABLED``.  This module does not infer a Rakuten query parameter
or create a live link.  It accepts only owner-private bindings for the 20
provider slots and final Money Link URLs for the separate 74 CTA identities.
Both sets must be bound to an exact administrator/CSV verification receipt
before owner-private HTML is materialized for a later publication workflow.
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
    EditorialPortfolioV2Failure,
    LOCAL_FIXTURE_RELATIVE_PATH,
    PORTFOLIO_RELATIVE_PATH as V2_PORTFOLIO_RELATIVE_PATH,
    PRODUCTION_FIXTURE_RELATIVE_PATH,
    load_editorial_portfolio_v2,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    ArticleBindingV3,
    CtaBindingV3,
    EditorialPortfolioV3,
    PORTFOLIO_RELATIVE_PATH,
    ProviderSlotV3,
)
from raos.application.finance.editorial_economics_v3 import (
    EditorialEconomicsV3Failure,
    canonical_json_bytes,
    read_private_bytes,
    write_private_bytes,
)


ADMIN_RECEIPT_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_ADMIN_VERIFICATION_RECEIPT_V2"
MONEY_LINK_MAPPING_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_MONEY_LINK_MAPPING_V2"
DRY_RUN_SCHEMA: Final = "RAOS_EDITORIAL_V3_RAKUTEN_MEASUREMENT_DRY_RUN_V3"
OVERLAY_RECEIPT_SCHEMA: Final = (
    "RAOS_EDITORIAL_V3_RAKUTEN_ACTIVATION_OVERLAY_RECEIPT_V2"
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
EXPECTED_PROVIDER_SLOT_COUNT: Final = 20
EXPECTED_CTA_COUNT: Final = 74
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
    v2_local_receipt_sha256: str
    v2_production_receipt_sha256: str
    admin_receipt_sha256: str
    money_link_mapping_sha256: str
    provider_slot_set_sha256: str
    provider_measurement_binding_sha256: str
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
    provider_slot_count: int
    provider_measurement_id_count: int
    internal_cta_identity_count: int
    live_link_count: int
    cta_count: int


@dataclass(frozen=True)
class _MoneyLinkMappingV2:
    """Validated private values plus safe hashes used by activation receipts."""

    urls: Mapping[tuple[str, str, str], str]
    provider_measurement_ids: Mapping[str, str]
    provider_slot_ids_by_article_placement: Mapping[tuple[str, str], str]
    provider_slot_set_sha256: str
    provider_measurement_binding_sha256: str


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
    if len(result) != EXPECTED_CTA_COUNT:
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    return result


def _expected_provider_slots(
    portfolio: EditorialPortfolioV3,
) -> dict[str, ProviderSlotV3]:
    result = {slot.provider_slot_id: slot for slot in portfolio.provider_slots}
    if (
        len(result) != EXPECTED_PROVIDER_SLOT_COUNT
        or len(portfolio.provider_slots) != EXPECTED_PROVIDER_SLOT_COUNT
        or set(result)
        != {
            binding.provider_slot_id
            for article in portfolio.articles
            for binding in article.cta_bindings
        }
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_PORTFOLIO_INVALID")
    return result


def _provider_slot_set_sha256(
    expected_slots: Mapping[str, ProviderSlotV3],
) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "provider_slot_id": slot.provider_slot_id,
                    "article_id": slot.article_id,
                    "placement": slot.placement,
                }
                for slot in sorted(
                    expected_slots.values(), key=lambda value: value.provider_slot_id
                )
            ]
        )
    )


def _provider_measurement_binding_sha256(
    provider_measurement_ids: Mapping[str, str],
) -> str:
    return _sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "provider_slot_id": provider_slot_id,
                    "rakuten_measurement_id": provider_measurement_ids[
                        provider_slot_id
                    ],
                }
                for provider_slot_id in sorted(provider_measurement_ids)
            ]
        )
    )


def _validate_money_link_mapping(
    document: Mapping[str, object],
    *,
    portfolio_sha256: str,
    expected: Mapping[tuple[str, str, str], CtaBindingV3],
    expected_slots: Mapping[str, ProviderSlotV3],
    representative_models: Mapping[str, str],
) -> _MoneyLinkMappingV2:
    _exact_keys(
        document,
        {
            "schema",
            "version",
            "generated_at",
            "portfolio_sha256",
            "provider_slot_count",
            "money_link_count",
            "urls_copied_from_rakuten_admin",
            "provider_parameter_inference_used",
            "provider_slots",
            "rows",
        },
    )
    if (
        document.get("schema") != MONEY_LINK_MAPPING_SCHEMA
        or document.get("version") != "2.0.0"
        or _timestamp(document.get("generated_at")) != document.get("generated_at")
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or type(document.get("provider_slot_count")) is not int
        or document.get("provider_slot_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or type(document.get("money_link_count")) is not int
        or document.get("money_link_count") != EXPECTED_CTA_COUNT
        or document.get("urls_copied_from_rakuten_admin") is not True
        or document.get("provider_parameter_inference_used") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID")

    provider_measurement_ids: dict[str, str] = {}
    seen_measurement_ids: set[str] = set()
    for row in _rows(document.get("provider_slots")):
        _exact_keys(row, {"provider_slot_id", "rakuten_measurement_id"})
        provider_slot_id = _text(row.get("provider_slot_id"), maximum=128)
        measurement_id = _text(row.get("rakuten_measurement_id"), maximum=64)
        if (
            provider_slot_id not in expected_slots
            or provider_slot_id in provider_measurement_ids
            or measurement_id in seen_measurement_ids
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID")
        provider_measurement_ids[provider_slot_id] = measurement_id
        seen_measurement_ids.add(measurement_id)
    if set(provider_measurement_ids) != set(expected_slots):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")

    urls: dict[tuple[str, str, str], str] = {}
    seen_urls: set[str] = set()
    provider_slot_ids_by_article_placement: dict[tuple[str, str], str] = {}
    for row in _rows(document.get("rows")):
        _exact_keys(
            row,
            {
                "article_id",
                "product_id",
                "placement",
                "provider_slot_id",
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
        provider_slot_id = _text(row.get("provider_slot_id"), maximum=128)
        article_placement = (identity[0], identity[2])
        observed_slot_id = provider_slot_ids_by_article_placement.get(article_placement)
        representative_model = representative_models.get(identity[1])
        destination_url = _validate_money_link_url(row.get("destination_url"))
        if (
            binding is None
            or identity in urls
            or provider_slot_id != binding.provider_slot_id
            or provider_slot_id not in provider_measurement_ids
            or observed_slot_id not in {None, provider_slot_id}
            or representative_model is None
            or _text(row.get("representative_model"), maximum=300)
            != representative_model
            or destination_url in seen_urls
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_MAPPING_INVALID")
        urls[identity] = destination_url
        provider_slot_ids_by_article_placement[article_placement] = provider_slot_id
        seen_urls.add(destination_url)
    expected_slot_ids_by_article_placement = {
        (slot.article_id, slot.placement): slot.provider_slot_id
        for slot in expected_slots.values()
    }
    if (
        set(urls) != set(expected)
        or provider_slot_ids_by_article_placement
        != expected_slot_ids_by_article_placement
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")
    return _MoneyLinkMappingV2(
        urls=dict(urls),
        provider_measurement_ids=dict(provider_measurement_ids),
        provider_slot_ids_by_article_placement=dict(
            provider_slot_ids_by_article_placement
        ),
        provider_slot_set_sha256=_provider_slot_set_sha256(expected_slots),
        provider_measurement_binding_sha256=_provider_measurement_binding_sha256(
            provider_measurement_ids
        ),
    )


def _validate_admin_receipt(
    document: Mapping[str, object],
    *,
    portfolio_sha256: str,
    mapping_sha256: str,
    mapping: _MoneyLinkMappingV2,
    expected: Mapping[tuple[str, str, str], CtaBindingV3],
    expected_slots: Mapping[str, ProviderSlotV3],
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
            "provider_slot_count",
            "money_link_count",
            "verification",
            "provider_slots",
            "money_links",
        },
    )
    verification = _mapping(document.get("verification"))
    _exact_keys(
        verification,
        {
            "all_expected_provider_slots_accepted_by_admin",
            "provider_slot_limit_verified",
            "character_set_and_length_verified",
            "csv_export_verified",
            "all_money_links_product_identity_verified",
            "provider_parameter_inference_used",
            "production_publication_authorized",
        },
    )
    if (
        document.get("schema") != ADMIN_RECEIPT_SCHEMA
        or document.get("version") != "2.0.0"
        or document.get("state") != "OWNER_VERIFIED_RAKUTEN_ADMIN_AND_CSV"
        or _timestamp(document.get("verified_at")) != document.get("verified_at")
        or document.get("owner_attested") is not True
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or _sha256(document.get("money_link_mapping_sha256")) != mapping_sha256
        or type(document.get("provider_slot_count")) is not int
        or document.get("provider_slot_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or type(document.get("money_link_count")) is not int
        or document.get("money_link_count") != EXPECTED_CTA_COUNT
        or verification.get("all_expected_provider_slots_accepted_by_admin") is not True
        or verification.get("provider_slot_limit_verified") is not True
        or verification.get("character_set_and_length_verified") is not True
        or verification.get("csv_export_verified") is not True
        or verification.get("all_money_links_product_identity_verified") is not True
        or verification.get("provider_parameter_inference_used") is not False
        or verification.get("production_publication_authorized") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID")

    observed_slots: set[str] = set()
    for row in _rows(document.get("provider_slots")):
        _exact_keys(
            row,
            {
                "provider_slot_id",
                "rakuten_measurement_id",
                "csv_echoed_measurement_id",
                "admin_console_measurement_id_verified",
            },
        )
        provider_slot_id = _text(row.get("provider_slot_id"), maximum=128)
        measurement_id = _text(row.get("rakuten_measurement_id"), maximum=64)
        if (
            provider_slot_id not in expected_slots
            or provider_slot_id in observed_slots
            or mapping.provider_measurement_ids.get(provider_slot_id) != measurement_id
            or _text(row.get("csv_echoed_measurement_id"), maximum=64) != measurement_id
            or row.get("admin_console_measurement_id_verified") is not True
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID")
        observed_slots.add(provider_slot_id)
    if observed_slots != set(expected_slots):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")

    observed_money_links: set[tuple[str, str, str]] = set()
    for row in _rows(document.get("money_links")):
        _exact_keys(
            row,
            {
                "article_id",
                "product_id",
                "placement",
                "provider_slot_id",
                "representative_model",
                "csv_echoed_representative_model",
                "money_link_provider_slot_selection_verified",
                "money_link_product_identity_verified",
            },
        )
        identity = (
            _text(row.get("article_id")),
            _text(row.get("product_id")),
            _text(row.get("placement")),
        )
        binding = expected.get(identity)
        expected_provider_slot_id = mapping.provider_slot_ids_by_article_placement.get(
            (identity[0], identity[2])
        )
        expected_model = representative_models.get(identity[1])
        if (
            binding is None
            or identity in observed_money_links
            or expected_provider_slot_id != binding.provider_slot_id
            or _text(row.get("provider_slot_id"), maximum=128)
            != expected_provider_slot_id
            or expected_model is None
            or _text(row.get("representative_model"), maximum=300) != expected_model
            or _text(row.get("csv_echoed_representative_model"), maximum=300)
            != expected_model
            or row.get("money_link_provider_slot_selection_verified") is not True
            or row.get("money_link_product_identity_verified") is not True
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_RECEIPT_INVALID")
        observed_money_links.add(identity)
    if observed_money_links != set(expected):
        _fail("RAOS_RAKUTEN_ACTIVATION_COVERAGE_INVALID")


def _anchor_attributes(opening: str) -> dict[str, str]:
    if not opening.casefold().startswith("<a") or not opening.endswith(">"):
        _fail("RAOS_RAKUTEN_ACTIVATION_HTML_INVALID")
    result: dict[str, str] = {}
    cursor = 2
    for match in ATTRIBUTE_RE.finditer(opening, 2, len(opening) - 1):
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
        ' data-raos-rakuten-provider-slot-id="'
        f'{escape(binding.provider_slot_id, quote=True)}"'
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


def _v2_materialization(
    *,
    repository_root: Path,
    fixture_root: Path,
    mode: str,
    portfolio: EditorialPortfolioV3,
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
            "articles",
            "products",
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
    if (
        receipt.get("schema") != V2_MATERIALIZATION_SCHEMA
        or receipt.get("mode") != mode
        or _sha256(receipt.get("portfolio_sha256")) != expected_v2_portfolio_sha256
        or evidence_status_sha256 == "0" * 64
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
    expected_articles = portfolio.article_by_id
    sources: dict[str, bytes] = {}
    article_rows: list[dict[str, str]] = []
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
        if (
            product_id not in expected_product_ids
            or product_id in seen_products
            or PRODUCT_ID_RE.fullmatch(product_id) is None
            or state not in {"verified", "not_found", "ambiguous", "expired"}
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_MATERIALIZATION_INVALID")
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
    return {
        "generated_at": generated_at,
        "portfolio_sha256": expected_v2_portfolio_sha256,
        "evidence_status_sha256": evidence_status_sha256,
        "receipt_raw": receipt_raw,
        "posts_raw": posts_raw,
        "sources": sources,
        "article_rows": article_rows,
        "products": products,
    }


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
    mapping_sha256 = _sha256_bytes(mapping_raw)
    admin_document = _json_document(admin_raw)
    mapping_document = _json_document(mapping_raw)
    _reject_formula_like_strings(admin_document)
    _reject_formula_like_strings(mapping_document)
    expected = _expected_bindings(portfolio)
    expected_slots = _expected_provider_slots(portfolio)
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
    mapping = _validate_money_link_mapping(
        mapping_document,
        portfolio_sha256=portfolio_sha256,
        expected=expected,
        expected_slots=expected_slots,
        representative_models=representative_models,
    )
    _validate_admin_receipt(
        admin_document,
        portfolio_sha256=portfolio_sha256,
        mapping_sha256=mapping_sha256,
        mapping=mapping,
        expected=expected,
        expected_slots=expected_slots,
        representative_models=representative_models,
    )
    default_local, default_production = _default_v2_fixture_roots(repository_root)
    local_source = _v2_materialization(
        repository_root=repository_root,
        fixture_root=local_v2_fixture_root or default_local,
        mode="local",
        portfolio=portfolio,
    )
    production_source = _v2_materialization(
        repository_root=repository_root,
        fixture_root=production_v2_fixture_root or default_production,
        mode="production",
        portfolio=portfolio,
    )
    if (
        local_source["portfolio_sha256"] != production_source["portfolio_sha256"]
        or local_source["evidence_status_sha256"]
        != production_source["evidence_status_sha256"]
        or local_source["products"] != production_source["products"]
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
            output = materialize_article_html(article, original, mapping.urls)
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
            "version": "2.0.0",
            "mode": mode,
            "portfolio_sha256": portfolio_sha256,
            "v2_portfolio_sha256": source["portfolio_sha256"],
            "v2_evidence_status_sha256": source["evidence_status_sha256"],
            "v2_materialization_receipt_sha256": _sha256_bytes(
                cast(bytes, source["receipt_raw"])
            ),
            "posts_sha256": _sha256_bytes(cast(bytes, source["posts_raw"])),
            "article_set_sha256": article_set_sha256,
            "article_count": len(rows),
            "provider_slot_count": len(expected_slots),
            "provider_measurement_id_count": len(mapping.provider_measurement_ids),
            "internal_cta_identity_count": sum(
                cast(int, row["cta_count"]) for row in rows
            ),
            "live_link_count": sum(cast(int, row["cta_count"]) for row in rows),
            "cta_count": sum(cast(int, row["cta_count"]) for row in rows),
            "provider_slot_set_sha256": mapping.provider_slot_set_sha256,
            "provider_measurement_binding_sha256": (
                mapping.provider_measurement_binding_sha256
            ),
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
        "version": "3.0.0",
        "state": "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED",
        "portfolio_sha256": portfolio_sha256,
        "admin_receipt_sha256": _sha256_bytes(admin_raw),
        "money_link_mapping_sha256": mapping_sha256,
        "provider_slot_set_sha256": mapping.provider_slot_set_sha256,
        "provider_measurement_binding_sha256": (
            mapping.provider_measurement_binding_sha256
        ),
        "v2_materialization": {
            "portfolio_sha256": local_source["portfolio_sha256"],
            "evidence_status_sha256": local_source["evidence_status_sha256"],
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
        "provider_slot_count": len(expected_slots),
        "provider_measurement_id_count": len(mapping.provider_measurement_ids),
        "internal_cta_identity_count": sum(
            len(article.cta_bindings) for article in portfolio.articles
        ),
        "live_link_count": sum(
            len(article.cta_bindings) for article in portfolio.articles
        ),
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
    provider_slot_set_sha256: str,
    provider_measurement_binding_sha256: str,
    v2_materialization: Mapping[str, object],
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
            "v2_materialization_receipt_sha256",
            "posts_sha256",
            "article_set_sha256",
            "article_count",
            "provider_slot_count",
            "provider_measurement_id_count",
            "internal_cta_identity_count",
            "live_link_count",
            "cta_count",
            "provider_slot_set_sha256",
            "provider_measurement_binding_sha256",
            "articles",
        },
    )
    expected_v2_receipt_key = f"{mode}_receipt_sha256"
    if (
        receipt.get("schema") != OVERLAY_RECEIPT_SCHEMA
        or receipt.get("version") != "2.0.0"
        or receipt.get("mode") != mode
        or receipt.get("portfolio_sha256") != portfolio_sha256
        or receipt.get("v2_portfolio_sha256")
        != v2_materialization.get("portfolio_sha256")
        or receipt.get("v2_evidence_status_sha256")
        != v2_materialization.get("evidence_status_sha256")
        or receipt.get("v2_materialization_receipt_sha256")
        != v2_materialization.get(expected_v2_receipt_key)
        or receipt.get("posts_sha256") != posts_sha256
        or receipt.get("article_set_sha256") != article_set_sha256
        or receipt.get("article_count") != 10
        or receipt.get("provider_slot_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or receipt.get("provider_measurement_id_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or receipt.get("internal_cta_identity_count") != EXPECTED_CTA_COUNT
        or receipt.get("live_link_count") != EXPECTED_CTA_COUNT
        or receipt.get("cta_count") != EXPECTED_CTA_COUNT
        or receipt.get("provider_slot_set_sha256") != provider_slot_set_sha256
        or receipt.get("provider_measurement_binding_sha256")
        != provider_measurement_binding_sha256
        or receipt.get("articles") != raw.get("articles")
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
    expected_by_id = portfolio.article_by_id
    article_rows: list[dict[str, object]] = []
    article_hashes: dict[str, str] = {}
    total_ctas = 0
    observed_provider_slots: set[str] = set()
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
                "data-raos-rakuten-provider-slot-id",
            }
            identity = (
                attributes.get("data-raos-product-id", ""),
                attributes.get("data-raos-placement", ""),
            )
            binding = expected_bindings.get(identity)
            href = attributes.get("href")
            if (
                data_attributes != required_data_attributes
                or binding is None
                or identity in observed
                or href is None
                or attributes.get("rel") != "sponsored nofollow"
                or attributes.get("data-raos-article-id") != binding.article_id
                or attributes.get("data-raos-cta-id") != binding.cta_id
                or attributes.get("data-raos-snapshot-id") != binding.snapshot_id
                or attributes.get("data-raos-offer-id") != binding.offer_id
                or attributes.get("data-raos-rakuten-provider-slot-id")
                != binding.provider_slot_id
            ):
                _fail("RAOS_RAKUTEN_ACTIVATION_OVERLAY_INVALID")
            _validate_money_link_url(href)
            observed_provider_slots.add(binding.provider_slot_id)
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
        or total_ctas != EXPECTED_CTA_COUNT
        or observed_provider_slots != set(portfolio.provider_slot_by_id)
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
            "provider_slot_set_sha256",
            "provider_measurement_binding_sha256",
            "v2_materialization",
            "overlays",
            "materialized_set_sha256",
            "article_count",
            "provider_slot_count",
            "provider_measurement_id_count",
            "internal_cta_identity_count",
            "live_link_count",
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
    expected_slots = _expected_provider_slots(portfolio)
    expected_provider_slot_set_sha256 = _provider_slot_set_sha256(expected_slots)
    admin_receipt_sha256 = _sha256(document.get("admin_receipt_sha256"))
    money_link_mapping_sha256 = _sha256(document.get("money_link_mapping_sha256"))
    provider_slot_set_sha256 = _sha256(document.get("provider_slot_set_sha256"))
    provider_measurement_binding_sha256 = _sha256(
        document.get("provider_measurement_binding_sha256")
    )
    materialized_set_sha256 = _sha256(document.get("materialized_set_sha256"))
    if (
        document.get("schema") != DRY_RUN_SCHEMA
        or document.get("version") != "3.0.0"
        or document.get("state") != "OWNER_PRIVATE_MATERIALIZED_NOT_PUBLISHED"
        or _sha256(document.get("portfolio_sha256")) != portfolio_sha256
        or document.get("article_count") != 10
        or type(document.get("provider_slot_count")) is not int
        or document.get("provider_slot_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or type(document.get("provider_measurement_id_count")) is not int
        or document.get("provider_measurement_id_count") != EXPECTED_PROVIDER_SLOT_COUNT
        or type(document.get("internal_cta_identity_count")) is not int
        or document.get("internal_cta_identity_count") != EXPECTED_CTA_COUNT
        or type(document.get("live_link_count")) is not int
        or document.get("live_link_count") != EXPECTED_CTA_COUNT
        or document.get("cta_count") != EXPECTED_CTA_COUNT
        or provider_slot_set_sha256 != expected_provider_slot_set_sha256
        or document.get("provider_parameter_inference_used") is not False
        or document.get("tracked_source_modified") is not False
        or document.get("live_write_performed") is not False
        or document.get("publication_authorized") is not False
    ):
        _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_INVALID")
    v2 = _mapping(document.get("v2_materialization"))
    _exact_keys(
        v2,
        {
            "portfolio_sha256",
            "evidence_status_sha256",
            "local_generated_at",
            "production_generated_at",
            "local_receipt_sha256",
            "production_receipt_sha256",
        },
    )
    v2_portfolio_sha256 = _sha256(v2.get("portfolio_sha256"))
    v2_evidence_status_sha256 = _sha256(v2.get("evidence_status_sha256"))
    local_receipt_sha256 = _sha256(v2.get("local_receipt_sha256"))
    production_receipt_sha256 = _sha256(v2.get("production_receipt_sha256"))
    generated_values = [
        _timestamp(v2.get("local_generated_at")),
        _timestamp(v2.get("production_generated_at")),
    ]
    now = datetime.now(UTC)
    for value in generated_values:
        generated = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if generated > now + timedelta(seconds=30) or (
            require_recent and now - generated > timedelta(minutes=15)
        ):
            _fail("RAOS_RAKUTEN_ACTIVATION_DRY_RUN_STALE")
    default_local, default_production = _default_v2_fixture_roots(repository_root)
    for source_root, expected_sha256 in (
        (
            local_v2_fixture_root or default_local,
            local_receipt_sha256,
        ),
        (
            production_v2_fixture_root or default_production,
            production_receipt_sha256,
        ),
    ):
        receipt_path = _owner_directory(source_root) / "materialization-receipt.v2.json"
        current = _read_owner_regular_file(
            receipt_path,
            maximum=MAX_PRIVATE_DOCUMENT_BYTES,
            exact_mode=0o600,
        )
        if _sha256_bytes(current) != expected_sha256:
            _fail("RAOS_RAKUTEN_ACTIVATION_V2_SOURCE_DRIFT")
    overlays = _mapping(document.get("overlays"))
    _exact_keys(overlays, {"local", "production"})
    local = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays.get("local")),
        mode="local",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        provider_slot_set_sha256=provider_slot_set_sha256,
        provider_measurement_binding_sha256=provider_measurement_binding_sha256,
        v2_materialization=v2,
    )
    production = _validate_overlay_output(
        private_root=private_root,
        raw=_mapping(overlays.get("production")),
        mode="production",
        portfolio=portfolio,
        portfolio_sha256=portfolio_sha256,
        provider_slot_set_sha256=provider_slot_set_sha256,
        provider_measurement_binding_sha256=provider_measurement_binding_sha256,
        v2_materialization=v2,
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
    return RakutenMeasurementActivationOverlayV3(
        dry_run_sha256=_sha256_bytes(dry_run_raw),
        portfolio_sha256=portfolio_sha256,
        v2_portfolio_sha256=v2_portfolio_sha256,
        v2_evidence_status_sha256=v2_evidence_status_sha256,
        v2_local_receipt_sha256=local_receipt_sha256,
        v2_production_receipt_sha256=production_receipt_sha256,
        admin_receipt_sha256=admin_receipt_sha256,
        money_link_mapping_sha256=money_link_mapping_sha256,
        provider_slot_set_sha256=provider_slot_set_sha256,
        provider_measurement_binding_sha256=provider_measurement_binding_sha256,
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
        provider_slot_count=EXPECTED_PROVIDER_SLOT_COUNT,
        provider_measurement_id_count=EXPECTED_PROVIDER_SLOT_COUNT,
        internal_cta_identity_count=EXPECTED_CTA_COUNT,
        live_link_count=EXPECTED_CTA_COUNT,
        cta_count=EXPECTED_CTA_COUNT,
    )


__all__ = [
    "ADMIN_RECEIPT_SCHEMA",
    "DRY_RUN_SCHEMA",
    "MONEY_LINK_MAPPING_SCHEMA",
    "OVERLAY_RECEIPT_SCHEMA",
    "RakutenMeasurementActivationOverlayV3",
    "RakutenMeasurementActivationV3Failure",
    "materialize_article_html",
    "materialize_rakuten_measurement_activation_v3",
    "validate_rakuten_measurement_activation_v3",
]
