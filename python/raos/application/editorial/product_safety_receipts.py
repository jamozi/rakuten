"""Standalone product-specific safety-query receipt contract.

The tracked receipt document is an owner input.  It contains observations from
official manufacturer and Japanese administrative sources, but it never carries
an owner-authored completion status.  Status is derived here from exact product,
authority, source, capture, hash, result, and freshness bindings.

This module intentionally does not integrate with article source packets yet.
Article gates can consume :class:`ProductSafetyReceiptAudit` in a later slice
without copying receipts into every article that happens to select a product.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, Literal, Mapping, NoReturn, Sequence, cast
import unicodedata
from urllib.parse import urlsplit

from raos.application.editorial.product_safety_query_capture import (
    ProductSafetyAdministrativeEvidenceSet,
    ProductSafetyQueryCaptureFailure,
    ProductSafetyQueryCaptureFailureCode,
    verify_product_safety_query_capture_set,
)


PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "product-safety-query-receipts.v1.json"
)
PRODUCT_SAFETY_RECEIPTS_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_QUERY_RECEIPTS_V1"
PRODUCT_SAFETY_RECEIPTS_VERSION: Final = "1.0.0"
MAX_TRACKED_BYTES: Final = 1024 * 1024
MAX_RECEIPT_AGE: Final = timedelta(days=30)
MAX_FUTURE_SKEW: Final = timedelta(minutes=5)

AuthorityKind = Literal[
    "MANUFACTURER_OFFICIAL",
    "JAPAN_ADMINISTRATIVE_OFFICIAL",
]
ReceiptResult = Literal["NONE_FOUND", "MATCH", "AMBIGUOUS"]
ProductSafetyStatus = Literal[
    "COMPLETE_NONE_FOUND",
    "BLOCKED_MATCH_FOUND",
    "BLOCKED_AMBIGUOUS_RESULT",
    "BLOCKED_STALE_RECEIPT",
    "BLOCKED_MISSING_RECEIPT",
]

REQUIRED_AUTHORITY_KINDS: Final[tuple[AuthorityKind, ...]] = (
    "MANUFACTURER_OFFICIAL",
    "JAPAN_ADMINISTRATIVE_OFFICIAL",
)
RECEIPT_HASH_FIELDS: Final[tuple[str, ...]] = (
    "product_id",
    "authority_kind",
    "model_tokens",
    "query_terms",
    "official_source_ref",
    "official_source_url",
    "checked_at_utc",
    "result",
    "matched_notice_ids",
    "capture_sha256",
    "coverage_caveat",
)
CANONICALIZATION_DESCRIPTION: Final = (
    "UTF-8 JSON with recursively sorted object keys, no insignificant whitespace, "
    "and unescaped Unicode"
)
REQUIRED_COVERAGE_CAVEAT: Final = (
    "この結果は、記録した公式source・型番token・query・確認日時の範囲だけを示し、"
    "安全情報が存在しないことを一般に証明しません。"
)

_PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
_SOURCE_REF_RE: Final = re.compile(r"SRC-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_NOTICE_ID_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_QUERY_INTENT_RE: Final = re.compile(
    r"リコール|重要なお知らせ|安全情報|事故情報|recall|safety|incident",
    re.IGNORECASE,
)


class ProductSafetyReceiptFailure(RuntimeError):
    """Stable, non-sensitive product-safety receipt failure."""


def _fail(code: str) -> NoReturn:
    raise ProductSafetyReceiptFailure(code) from None


@dataclass(frozen=True, slots=True)
class ProductSafetyRequirement:
    """Exact selected-product identity required by the receipt contract."""

    product_id: str
    exact_model_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductSafetyOfficialSource:
    """Reviewed official source supplied by the source-registry integration."""

    source_ref: str
    url: str
    authority_kind: AuthorityKind
    capture_sha256: str
    covered_product_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class ProductSafetySourceRegistryContext:
    """Official source and exact-host context supplied by the caller."""

    sources: Mapping[str, ProductSafetyOfficialSource]
    allowed_hosts_by_authority: Mapping[AuthorityKind, frozenset[str]]


@dataclass(frozen=True, slots=True)
class ProductSafetyReceipt:
    product_id: str
    authority_kind: AuthorityKind
    model_tokens: tuple[str, ...]
    query_terms: tuple[str, ...]
    official_source_ref: str
    official_source_url: str
    checked_at: datetime
    result: ReceiptResult
    matched_notice_ids: tuple[str, ...]
    capture_sha256: str
    coverage_caveat: str
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class ProductSafetyProductStatus:
    product_id: str
    status: ProductSafetyStatus
    receipts: tuple[ProductSafetyReceipt, ...]
    missing_authority_kinds: tuple[AuthorityKind, ...]
    stale_authority_kinds: tuple[AuthorityKind, ...]
    matched_notice_ids: tuple[str, ...]
    verified_authority_kinds: tuple[AuthorityKind, ...] = ()
    administrative_capture_sha256s: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductSafetyReceiptAudit:
    schema: str
    evaluated_at: datetime
    products: tuple[ProductSafetyProductStatus, ...]
    complete: bool
    administrative_bundle_sha256: str | None = None
    administrative_capture_count: int = 0


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")


def product_safety_receipt_sha256(material: Mapping[str, object]) -> str:
    """Return the canonical receipt hash for the exact contract fields."""

    if set(material) != set(RECEIPT_HASH_FIELDS):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    ordered = {field: material[field] for field in RECEIPT_HASH_FIELDS}
    return hashlib.sha256(_canonical_bytes(ordered)).hexdigest()


def _read_document(path: Path) -> object:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_TRACKED_BYTES
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_FILE_INVALID")
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
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_FILE_INVALID")
        return json.loads(raw.decode("utf-8", errors="strict"))
    except ProductSafetyReceiptFailure:
        raise
    except OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_FILE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    return value


def _text_tuple(
    value: object, *, maximum: int, allow_empty: bool = False
) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    values = tuple(_text(item, maximum=maximum) for item in cast(list[object], value))
    if (not allow_empty and not values) or len(values) != len(set(values)):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    return values


def _normalized_model_token(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _parse_https_url(value: object) -> tuple[str, str]:
    url = _text(value, maximum=4096)
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    hostname = (parsed.hostname or "").casefold()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    return url, hostname


def _validate_requirements(
    requirements: Sequence[ProductSafetyRequirement],
) -> dict[str, ProductSafetyRequirement]:
    if not requirements:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
    result: dict[str, ProductSafetyRequirement] = {}
    for requirement in requirements:
        if type(requirement) is not ProductSafetyRequirement:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        product_id = requirement.product_id
        tokens = requirement.exact_model_tokens
        if (
            type(product_id) is not str
            or _PRODUCT_ID_RE.fullmatch(product_id) is None
            or product_id in result
            or type(tokens) is not tuple
            or not tokens
            or len(tokens) != len(set(tokens))
            or any(
                type(token) is not str
                or not 2 <= len(token) <= 200
                or token != token.strip()
                or "\x00" in token
                for token in tokens
            )
            or len({_normalized_model_token(token) for token in tokens}) != len(tokens)
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        result[product_id] = requirement
    return result


def _validate_registry_context(
    context: ProductSafetySourceRegistryContext,
) -> dict[str, ProductSafetyOfficialSource]:
    if type(context) is not ProductSafetySourceRegistryContext:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
    if (
        not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            context.sources, Mapping
        )
        or not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            context.allowed_hosts_by_authority, Mapping
        )
        or set(context.allowed_hosts_by_authority) != set(REQUIRED_AUTHORITY_KINDS)
    ):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
    allowed_hosts: dict[AuthorityKind, frozenset[str]] = {}
    for authority in REQUIRED_AUTHORITY_KINDS:
        raw_hosts = context.allowed_hosts_by_authority[authority]
        if type(raw_hosts) is not frozenset or not raw_hosts:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        if any(
            type(host) is not str
            or not host
            or host != host.strip()
            or "/" in host
            or ":" in host
            for host in raw_hosts
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        normalized = frozenset(host.casefold() for host in raw_hosts)
        if len(normalized) != len(raw_hosts):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        allowed_hosts[authority] = normalized

    result: dict[str, ProductSafetyOfficialSource] = {}
    for source_ref, source in context.sources.items():
        if (
            type(source_ref) is not str
            or type(source) is not ProductSafetyOfficialSource
            or source.source_ref != source_ref
            or _SOURCE_REF_RE.fullmatch(source_ref) is None
            or source_ref in result
            or source.authority_kind not in REQUIRED_AUTHORITY_KINDS
            or type(source.capture_sha256) is not str
            or _SHA256_RE.fullmatch(source.capture_sha256) is None
            or type(source.covered_product_ids) is not frozenset
            or not source.covered_product_ids
            or any(
                type(product_id) is not str
                or _PRODUCT_ID_RE.fullmatch(product_id) is None
                for product_id in source.covered_product_ids
            )
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        _url, host = _parse_https_url(source.url)
        if host not in allowed_hosts[source.authority_kind]:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        if (
            source.authority_kind == "JAPAN_ADMINISTRATIVE_OFFICIAL"
            and not host.endswith(".go.jp")
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
        result[source_ref] = source
    return result


def _parse_checked_at(value: object) -> datetime:
    text = _text(value, maximum=20)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    return parsed


def _validate_document_header(document: Mapping[str, object]) -> list[object]:
    if set(document) != {
        "schema",
        "version",
        "hash_contract",
        "freshness_policy",
        "required_authority_kinds",
        "coverage_caveat_policy",
        "receipts",
    }:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    if (
        document.get("schema") != PRODUCT_SAFETY_RECEIPTS_SCHEMA
        or document.get("version") != PRODUCT_SAFETY_RECEIPTS_VERSION
        or document.get("hash_contract")
        != {
            "algorithm": "SHA-256",
            "canonicalization": CANONICALIZATION_DESCRIPTION,
            "fields": list(RECEIPT_HASH_FIELDS),
        }
        or document.get("freshness_policy")
        != {
            "maximum_age_days": 30,
            "maximum_future_skew_minutes": 5,
        }
        or document.get("required_authority_kinds") != list(REQUIRED_AUTHORITY_KINDS)
        or document.get("coverage_caveat_policy")
        != {"required_receipt_value": REQUIRED_COVERAGE_CAVEAT}
        or type(document.get("receipts")) is not list
    ):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    return cast(list[object], document["receipts"])


def _query_contains_exact_model_token(
    query_terms: tuple[str, ...], model_token: str
) -> bool:
    normalized_token = _normalized_model_token(model_token)
    pattern = re.compile(
        rf"(?<![0-9a-z]){re.escape(normalized_token)}(?![0-9a-z])",
        re.IGNORECASE,
    )
    return any(pattern.search(_normalized_model_token(term)) for term in query_terms)


def _evaluate_product_safety_receipts(
    document: object,
    *,
    requirements: Sequence[ProductSafetyRequirement],
    registry_context: ProductSafetySourceRegistryContext,
    now: datetime | None = None,
    administrative_evidence: ProductSafetyAdministrativeEvidenceSet | None = None,
) -> ProductSafetyReceiptAudit:
    """Validate declarations and derive a fail-closed status per product."""

    if type(document) is not dict:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
    evaluated_at = now or datetime.now(UTC)
    if (
        type(evaluated_at) is not datetime
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() != timedelta(0)
    ):
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTEXT_INVALID")
    evaluated_at = evaluated_at.astimezone(UTC)
    requirement_by_product = _validate_requirements(requirements)
    sources = _validate_registry_context(registry_context)
    raw_receipts = _validate_document_header(cast(Mapping[str, object], document))

    administrative_by_product = {}
    if administrative_evidence is not None:
        if (
            type(administrative_evidence) is not ProductSafetyAdministrativeEvidenceSet
            or administrative_evidence.evaluated_at != evaluated_at
            or administrative_evidence.capture_count
            != len(requirement_by_product) * 3
            or {row.product_id for row in administrative_evidence.products}
            != set(requirement_by_product)
            or any(
                row.exact_model_tokens
                != requirement_by_product[row.product_id].exact_model_tokens
                for row in administrative_evidence.products
            )
        ):
            _fail("RAOS_PRODUCT_SAFETY_ADMIN_CAPTURE_CONTEXT_INVALID")
        administrative_by_product = {
            row.product_id: row for row in administrative_evidence.products
        }

    receipts_by_key: dict[tuple[str, AuthorityKind], ProductSafetyReceipt] = {}
    expected_fields: set[str] = set(RECEIPT_HASH_FIELDS)
    expected_fields.add("receipt_sha256")
    for raw_receipt in raw_receipts:
        if type(raw_receipt) is not dict:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        raw_receipt_mapping = cast(dict[object, object], raw_receipt)
        if set(raw_receipt_mapping) != expected_fields:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        receipt = cast(Mapping[str, object], raw_receipt_mapping)
        product_id = _text(receipt["product_id"], maximum=160)
        requirement = requirement_by_product.get(product_id)
        raw_authority = receipt["authority_kind"]
        if raw_authority == "MANUFACTURER_OFFICIAL":
            authority: AuthorityKind = "MANUFACTURER_OFFICIAL"
        elif raw_authority == "JAPAN_ADMINISTRATIVE_OFFICIAL":
            authority = "JAPAN_ADMINISTRATIVE_OFFICIAL"
        else:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        if requirement is None:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        key = (product_id, authority)
        if key in receipts_by_key:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")

        model_tokens = _text_tuple(receipt["model_tokens"], maximum=200)
        query_terms = _text_tuple(receipt["query_terms"], maximum=500)
        if model_tokens != requirement.exact_model_tokens:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        if any(
            not _query_contains_exact_model_token(query_terms, token)
            for token in requirement.exact_model_tokens
        ) or not any(_QUERY_INTENT_RE.search(term) for term in query_terms):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")

        source_ref = _text(receipt["official_source_ref"], maximum=300)
        source = sources.get(source_ref)
        source_url, _host = _parse_https_url(receipt["official_source_url"])
        capture_sha256 = _text(receipt["capture_sha256"], maximum=64)
        if (
            source is None
            or source.authority_kind != authority
            or product_id not in source.covered_product_ids
            or source_url != source.url
            or capture_sha256 != source.capture_sha256
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")

        checked_at = _parse_checked_at(receipt["checked_at_utc"])
        if checked_at - evaluated_at > MAX_FUTURE_SKEW:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        result = receipt["result"]
        if type(result) is not str or result not in {
            "NONE_FOUND",
            "MATCH",
            "AMBIGUOUS",
        }:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        result = cast(ReceiptResult, result)
        notice_ids = _text_tuple(
            receipt["matched_notice_ids"], maximum=200, allow_empty=True
        )
        if any(_NOTICE_ID_RE.fullmatch(value) is None for value in notice_ids):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        if (result == "MATCH") != bool(notice_ids) or (
            result == "NONE_FOUND" and notice_ids
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        coverage_caveat = _text(receipt["coverage_caveat"], maximum=1000)
        if coverage_caveat != REQUIRED_COVERAGE_CAVEAT:
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")
        receipt_sha256 = _text(receipt["receipt_sha256"], maximum=64)
        if (
            _SHA256_RE.fullmatch(capture_sha256) is None
            or _SHA256_RE.fullmatch(receipt_sha256) is None
            or receipt_sha256
            != product_safety_receipt_sha256(
                {field: receipt[field] for field in RECEIPT_HASH_FIELDS}
            )
        ):
            _fail("RAOS_PRODUCT_SAFETY_RECEIPT_CONTRACT_INVALID")

        receipts_by_key[key] = ProductSafetyReceipt(
            product_id=product_id,
            authority_kind=authority,
            model_tokens=model_tokens,
            query_terms=query_terms,
            official_source_ref=source_ref,
            official_source_url=source_url,
            checked_at=checked_at,
            result=result,
            matched_notice_ids=notice_ids,
            capture_sha256=capture_sha256,
            coverage_caveat=coverage_caveat,
            receipt_sha256=receipt_sha256,
        )

    products: list[ProductSafetyProductStatus] = []
    for requirement in requirements:
        product_receipts = tuple(
            receipts_by_key[(requirement.product_id, authority)]
            for authority in REQUIRED_AUTHORITY_KINDS
            if (requirement.product_id, authority) in receipts_by_key
        )
        administrative = administrative_by_product.get(requirement.product_id)
        verified: tuple[AuthorityKind, ...] = (
            ("JAPAN_ADMINISTRATIVE_OFFICIAL",)
            if administrative is not None
            and administrative.status == "VERIFIED_NONE_FOUND"
            else ()
        )
        missing_values: list[AuthorityKind] = ["MANUFACTURER_OFFICIAL"]
        if administrative is None:
            missing_values.append("JAPAN_ADMINISTRATIVE_OFFICIAL")
        missing = tuple(missing_values)
        stale: tuple[AuthorityKind, ...] = (
            ("JAPAN_ADMINISTRATIVE_OFFICIAL",)
            if administrative is not None
            and administrative.status == "BLOCKED_STALE_CAPTURE"
            else ()
        )
        matched = tuple(
            dict.fromkeys(
                notice_id
                for receipt in product_receipts
                for notice_id in receipt.matched_notice_ids
            )
            | dict.fromkeys(
                ()
                if administrative is None
                else administrative.matched_notice_ids
            )
        )
        if (
            administrative is not None
            and administrative.status == "BLOCKED_MATCH_FOUND"
        ) or any(receipt.result == "MATCH" for receipt in product_receipts):
            status: ProductSafetyStatus = "BLOCKED_MATCH_FOUND"
        elif (
            administrative is not None
            and administrative.status == "BLOCKED_AMBIGUOUS_RESULT"
        ) or any(receipt.result == "AMBIGUOUS" for receipt in product_receipts):
            status = "BLOCKED_AMBIGUOUS_RESULT"
        elif stale:
            status = "BLOCKED_STALE_RECEIPT"
        elif missing:
            status = "BLOCKED_MISSING_RECEIPT"
        else:
            status = "COMPLETE_NONE_FOUND"
        products.append(
            ProductSafetyProductStatus(
                product_id=requirement.product_id,
                status=status,
                receipts=product_receipts,
                missing_authority_kinds=missing,
                stale_authority_kinds=stale,
                matched_notice_ids=matched,
                verified_authority_kinds=verified,
                administrative_capture_sha256s=(
                    ()
                    if administrative is None
                    else tuple(row.capture_sha256 for row in administrative.captures)
                ),
            )
        )

    complete = all(product.status == "COMPLETE_NONE_FOUND" for product in products)
    return ProductSafetyReceiptAudit(
        schema=PRODUCT_SAFETY_RECEIPTS_SCHEMA,
        evaluated_at=evaluated_at,
        products=tuple(products),
        complete=complete,
        administrative_bundle_sha256=(
            None
            if administrative_evidence is None
            else administrative_evidence.bundle_sha256
        ),
        administrative_capture_count=(
            0
            if administrative_evidence is None
            else administrative_evidence.capture_count
        ),
    )


def evaluate_product_safety_receipts(
    document: object,
    *,
    requirements: Sequence[ProductSafetyRequirement],
    registry_context: ProductSafetySourceRegistryContext,
    now: datetime | None = None,
) -> ProductSafetyReceiptAudit:
    """Validate tracked declarations without treating their hashes as evidence.

    This pure evaluator intentionally has no way to confer administrative or
    manufacturer verification.  Administrative authority is available only via
    :func:`load_product_safety_receipt_audit`, which replays the fixed private
    capture set.  Manufacturer verification is not implemented and therefore
    remains missing even when a tracked V1 row declares a clear result.
    """

    return _evaluate_product_safety_receipts(
        document,
        requirements=requirements,
        registry_context=registry_context,
        now=now,
        administrative_evidence=None,
    )


def load_product_safety_receipt_audit(
    repository_root: Path,
    *,
    requirements: Sequence[ProductSafetyRequirement],
    registry_context: ProductSafetySourceRegistryContext,
    now: datetime | None = None,
) -> ProductSafetyReceiptAudit:
    """Read the tracked owner input safely and return its derived audit."""

    document = _read_document(repository_root / PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH)
    evaluated_at = datetime.now(UTC) if now is None else now
    administrative_evidence: ProductSafetyAdministrativeEvidenceSet | None
    try:
        administrative_evidence = verify_product_safety_query_capture_set(
            repository_root,
            now=evaluated_at,
        )
    except ProductSafetyQueryCaptureFailure as exc:
        if exc.code is ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING:
            administrative_evidence = None
        else:
            _fail("RAOS_PRODUCT_SAFETY_ADMIN_CAPTURE_SET_INVALID")
    return _evaluate_product_safety_receipts(
        document,
        requirements=requirements,
        registry_context=registry_context,
        now=evaluated_at,
        administrative_evidence=administrative_evidence,
    )


def require_product_safety_receipts_complete(
    audit: ProductSafetyReceiptAudit,
) -> None:
    """Fail closed unless both official authorities are current and clear."""

    if type(audit) is not ProductSafetyReceiptAudit or not audit.complete:
        _fail("RAOS_PRODUCT_SAFETY_RECEIPT_INCOMPLETE")
