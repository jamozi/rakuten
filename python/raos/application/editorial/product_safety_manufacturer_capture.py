"""Fail-closed manufacturer product-safety query capture and replay.

Only an exact endpoint that has been reviewed in both tracked data *and* this
module can be queried.  A product page, manual, support landing page, or generic
safety page is never interpreted as evidence that no notice exists.  The
current portfolio has no such reviewed endpoint, so every current product is
deliberately ``MANUAL_REQUIRED`` until a manufacturer-specific
query adapter is reviewed and added in code.

The tracked plan and empty evidence document are contracts, not evidence.  A
future reviewed query stores its canonical raw request, raw response, and
metadata only below the fixed owner-private directory.  Replay rebuilds the
request from the code allowlist, hashes both raw files, reparses the response,
and applies freshness before granting ``VERIFIED_NONE_FOUND``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import ssl
import stat
from typing import Final, Literal, NoReturn, Protocol, cast, runtime_checkable
import unicodedata
from urllib.parse import urlencode, urlsplit


PLAN_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "product-safety-manufacturer-query-plan.v1.json"
)
EMPTY_EVIDENCE_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "product-safety-manufacturer-query-evidence.empty.v1.json"
)
PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
OWNER_CAPTURE_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-product-safety-manufacturer-capture-v1"
)
PLAN_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_MANUFACTURER_QUERY_PLAN_V1"
EMPTY_EVIDENCE_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_MANUFACTURER_EMPTY_EVIDENCE_V1"
CAPTURE_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_MANUFACTURER_CAPTURE_V1"
BUNDLE_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_MANUFACTURER_CAPTURE_BUNDLE_V1"
VERSION: Final = "1.0.0"
PUBLICATION_AUTHORITY: Final = "NONE"
MAX_PLAN_BYTES: Final = 256 * 1024
MAX_PORTFOLIO_BYTES: Final = 4 * 1024 * 1024
MAX_EMPTY_EVIDENCE_BYTES: Final = 64 * 1024
MAX_CAPTURE_METADATA_BYTES: Final = 128 * 1024
MAX_REQUEST_BYTES: Final = 64 * 1024
MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024
MAX_CAPTURE_AGE: Final = timedelta(days=30)
MAX_FUTURE_SKEW: Final = timedelta(minutes=5)
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
LOCK_FILE_NAME: Final = "manufacturer-capture.lock"
REQUEST_FILE_NAME: Final = "request.bin"
RESPONSE_FILE_NAME: Final = "response.bin"
METADATA_FILE_NAME: Final = "capture.v1.json"
CONNECT_TIMEOUT_SECONDS: Final = 10
READ_TIMEOUT_SECONDS: Final = 20
COVERAGE_CAVEAT: Final = (
    "この結果は、審査済みのメーカー公式検索endpoint・型番・確認日時の範囲だけを示し、"
    "安全情報が存在しないことを一般に証明しません。"
)
MANUAL_REQUIRED_REASON: Final = "NO_REVIEWED_EXACT_MANUFACTURER_SAFETY_QUERY_ENDPOINT"
USER_AGENT: Final = (
    "Mozilla/5.0 (compatible; RAOS-manufacturer-safety-capture/1; "
    "+https://kurashinoshirube.com/comparison-policy/)"
)

EndpointReviewStatus = Literal["REVIEWED_EXACT_QUERY", "MANUAL_REQUIRED"]
ObservationResult = Literal["NONE_FOUND", "MATCH", "AMBIGUOUS"]
ManufacturerProductStatus = Literal[
    "VERIFIED_NONE_FOUND",
    "BLOCKED_MATCH_FOUND",
    "BLOCKED_AMBIGUOUS_RESULT",
    "BLOCKED_STALE_CAPTURE",
    "BLOCKED_MISSING_CAPTURE",
    "MANUAL_REQUIRED",
]

_PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
_CODE_RE: Final = re.compile(r"[A-Z][A-Z0-9_]{1,63}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_NOTICE_ID_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_CONTENT_TYPE_RE: Final = re.compile(
    r"application/json(?:\s*;\s*charset=\"?utf-8\"?)?\Z",
    re.ASCII | re.IGNORECASE,
)


class ProductSafetyManufacturerCaptureFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PLAN_INVALID = "PLAN_INVALID"
    EMPTY_EVIDENCE_INVALID = "EMPTY_EVIDENCE_INVALID"
    PRODUCT_NOT_ALLOWLISTED = "PRODUCT_NOT_ALLOWLISTED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"
    REQUEST_INVALID = "REQUEST_INVALID"
    NETWORK_ENVIRONMENT_UNSAFE = "NETWORK_ENVIRONMENT_UNSAFE"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_PARSE_FAILED = "RESPONSE_PARSE_FAILED"
    STORE_UNSAFE = "STORE_UNSAFE"
    EVIDENCE_SET_INVALID = "EVIDENCE_SET_INVALID"


class ProductSafetyManufacturerCaptureFailure(RuntimeError):
    """Stable failure that never includes a query or captured response."""

    __slots__ = ("_code",)

    def __init__(self, code: ProductSafetyManufacturerCaptureFailureCode) -> None:
        if type(code) is not ProductSafetyManufacturerCaptureFailureCode:
            raise TypeError("invalid manufacturer capture failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> ProductSafetyManufacturerCaptureFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value


def _fail(
    code: ProductSafetyManufacturerCaptureFailureCode = (
        ProductSafetyManufacturerCaptureFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ProductSafetyManufacturerCaptureFailure(code) from None


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json(
    raw: bytes,
    *,
    maximum: int,
    code: ProductSafetyManufacturerCaptureFailureCode,
) -> object:
    if not 1 <= len(raw) <= maximum or raw.startswith(b"\xef\xbb\xbf"):
        _fail(code)

    def pairs(rows: list[tuple[object, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in rows:
            if type(key) is not str or key in result:
                _fail(code)
            result[key] = value
        return result

    def finite(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            _fail(code)
        return parsed

    def constant(value: str) -> NoReturn:
        del value
        _fail(code)

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=finite,
            parse_constant=constant,
        )
    except ProductSafetyManufacturerCaptureFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(code)


def _absolute_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail()
    return value


def _read_regular(root: Path, relative: Path, maximum: int) -> bytes:
    target = _absolute_root(root) / relative
    descriptor = -1
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
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
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
        return raw
    except ProductSafetyManufacturerCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class _ReviewedEndpointSpec:
    contract_id: str
    manufacturer_code: str
    endpoint: str
    host: str
    method: Literal["GET", "POST"]
    query_field: str
    fixed_query_fields: tuple[tuple[str, str], ...]
    response_media_type: str
    parser_version: str
    official_authority_source_ref: str


# Intentionally empty.  Adding a row requires code review of the exact official
# host, endpoint, HTTP method, query binding, response contract, and parser.
_REVIEWED_ENDPOINT_SPECS: Final[dict[str, _ReviewedEndpointSpec]] = {}


@dataclass(frozen=True, slots=True)
class _FixedProduct:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    query_model_token: str
    manufacturer_code: str


_MANUFACTURER_CODE_BY_PRODUCT_PREFIX: Final[tuple[tuple[str, str], ...]] = (
    ("PRD-AMERICAN-TOURISTER-", "SAMSONITE_JAPAN"),
    ("PRD-SAMSONITE-", "SAMSONITE_JAPAN"),
    ("PRD-PROTECA-", "ACE"),
    ("PRD-ACE-", "ACE"),
    ("PRD-ANKER-", "ANKER_JAPAN"),
    ("PRD-EUFY-", "ANKER_JAPAN"),
    ("PRD-JACKERY-", "JACKERY_JAPAN"),
    ("PRD-DJI-", "DJI_JAPAN"),
    ("PRD-BLUETTI-", "BLUETTI_JAPAN"),
    ("PRD-THANKO-", "THANKO"),
    ("PRD-SIROCA-", "SIROCA"),
    ("PRD-TOSHIBA-", "TOSHIBA_LIFESTYLE"),
    ("PRD-SWITCHBOT-", "SWITCHBOT"),
    ("PRD-ECOVACS-", "ECOVACS_JAPAN"),
    ("PRD-IROBOT-", "IROBOT_JAPAN"),
    ("PRD-BERMAS-", "BERMAS"),
    ("PRD-RIMOWA-", "RIMOWA_JAPAN"),
    ("PRD-INNOVATOR-", "TRIO"),
)


def _manufacturer_code(product_id: str) -> str:
    matches = tuple(
        code
        for prefix, code in _MANUFACTURER_CODE_BY_PRODUCT_PREFIX
        if product_id.startswith(prefix)
    )
    if len(matches) != 1:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    return matches[0]


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerProductPlan:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    query_model_token: str
    manufacturer_code: str
    endpoint_review_status: EndpointReviewStatus
    endpoint_contract: _ReviewedEndpointSpec | None
    manual_required_reason: str | None


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerQueryPlan:
    products: tuple[ProductSafetyManufacturerProductPlan, ...]
    plan_sha256: str
    portfolio_sha256: str

    def product(self, product_id: str) -> ProductSafetyManufacturerProductPlan:
        if type(product_id) is not str:
            _fail()
        rows = tuple(row for row in self.products if row.product_id == product_id)
        if len(rows) != 1:
            _fail(ProductSafetyManufacturerCaptureFailureCode.PRODUCT_NOT_ALLOWLISTED)
        return rows[0]


def _endpoint_document(spec: _ReviewedEndpointSpec) -> dict[str, object]:
    return {
        "contract_id": spec.contract_id,
        "manufacturer_code": spec.manufacturer_code,
        "official_authority_source_ref": spec.official_authority_source_ref,
        "host": spec.host,
        "endpoint": spec.endpoint,
        "method": spec.method,
        "query_field": spec.query_field,
        "fixed_query_fields": [
            {"name": name, "value": value} for name, value in spec.fixed_query_fields
        ],
        "response_media_type": spec.response_media_type,
        "parser_version": spec.parser_version,
    }


def _product_document(product: _FixedProduct) -> dict[str, object]:
    matching = tuple(
        spec
        for spec in _REVIEWED_ENDPOINT_SPECS.values()
        if spec.manufacturer_code == product.manufacturer_code
    )
    if len(matching) > 1:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    if not matching:
        return {
            "product_id": product.product_id,
            "exact_model_tokens": list(product.exact_model_tokens),
            "query_model_token": product.query_model_token,
            "manufacturer_code": product.manufacturer_code,
            "endpoint_review_status": "MANUAL_REQUIRED",
            "endpoint_contract_id": None,
            "manual_required_reason": MANUAL_REQUIRED_REASON,
        }
    return {
        "product_id": product.product_id,
        "exact_model_tokens": list(product.exact_model_tokens),
        "query_model_token": product.query_model_token,
        "manufacturer_code": product.manufacturer_code,
        "endpoint_review_status": "REVIEWED_EXACT_QUERY",
        "endpoint_contract_id": matching[0].contract_id,
        "manual_required_reason": None,
    }


def _expected_plan_document(
    products: Sequence[_FixedProduct], *, portfolio_sha256: str
) -> dict[str, object]:
    reviewed_count = sum(
        _product_document(product)["endpoint_review_status"] == "REVIEWED_EXACT_QUERY"
        for product in products
    )
    return {
        "schema": PLAN_SCHEMA,
        "version": VERSION,
        "publication_authority": PUBLICATION_AUTHORITY,
        "portfolio_relative_path": PORTFOLIO_RELATIVE_PATH.as_posix(),
        "portfolio_sha256": portfolio_sha256,
        "owner_private_capture_relative_path": OWNER_CAPTURE_RELATIVE_PATH.as_posix(),
        "coverage_caveat": COVERAGE_CAVEAT,
        "evidence_policy": {
            "tracked_documents_are_evidence": False,
            "raw_request_private_mode": "0600",
            "raw_response_private_mode": "0600",
            "private_directory_mode": "0700",
            "none_found_rule": "REPLAYED_PARSEABLE_OFFICIAL_EXACT_QUERY_ZERO_ONLY",
            "product_or_general_safety_page_none_found_allowed": False,
            "unreviewed_endpoint_behavior": "MANUAL_REQUIRED",
            "maximum_age_days": 30,
            "maximum_future_skew_minutes": 5,
        },
        "matrix": {
            "mode": "EXACT_CURRENT_SELECTED_PRODUCTS",
            "expected_product_count": len(products),
            "reviewed_exact_query_product_count": reviewed_count,
            "manual_required_product_count": len(products) - reviewed_count,
        },
        "reviewed_endpoint_contracts": [
            _endpoint_document(_REVIEWED_ENDPOINT_SPECS[key])
            for key in sorted(_REVIEWED_ENDPOINT_SPECS)
        ],
        "products": [_product_document(product) for product in products],
    }


def _portfolio_products(document: object) -> tuple[_FixedProduct, ...]:
    if type(document) is not dict:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    mapping = cast(dict[str, object], document)
    rows = mapping.get("products")
    articles = mapping.get("articles")
    if (
        mapping.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V2"
        or type(rows) is not list
        or type(articles) is not list
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    selected_product_ids: set[str] = set()
    for raw_article in cast(list[object], articles):
        if type(raw_article) is not dict:
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
        raw_product_ids = cast(dict[str, object], raw_article).get("product_ids")
        if type(raw_product_ids) is not list:
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
        for value in cast(list[object], raw_product_ids):
            if type(value) is not str or _PRODUCT_ID_RE.fullmatch(value) is None:
                _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
            selected_product_ids.add(value)
    result: list[_FixedProduct] = []
    observed: set[str] = set()
    for raw in cast(list[object], rows):
        if type(raw) is not dict:
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
        row = cast(dict[str, object], raw)
        product_id = row.get("product_id")
        models = row.get("official_models")
        representative = row.get("representative_model")
        if (
            type(product_id) is not str
            or _PRODUCT_ID_RE.fullmatch(product_id) is None
            or product_id in observed
            or type(models) is not list
            or not models
            or any(
                type(token) is not str
                or not 1 <= len(token) <= 200
                or token != token.strip()
                or "\x00" in token
                or unicodedata.normalize("NFKC", token) != token
                for token in cast(list[object], models)
            )
            or type(representative) is not str
            or representative not in models
            or len(cast(list[object], models)) != len(set(cast(list[str], models)))
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
        observed.add(product_id)
        result.append(
            _FixedProduct(
                product_id=product_id,
                exact_model_tokens=tuple(cast(list[str], models)),
                query_model_token=representative,
                manufacturer_code=_manufacturer_code(product_id),
            )
        )
    if not result or selected_product_ids != observed:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    return tuple(result)


def _validate_endpoint_spec(spec: _ReviewedEndpointSpec) -> None:
    try:
        parsed = urlsplit(spec.endpoint)
        port = parsed.port
    except ValueError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    if (
        _CODE_RE.fullmatch(spec.contract_id) is None
        or _CODE_RE.fullmatch(spec.manufacturer_code) is None
        or _CODE_RE.fullmatch(spec.parser_version) is None
        or parsed.scheme != "https"
        or parsed.hostname != spec.host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
        or spec.method not in {"GET", "POST"}
        or not spec.query_field
        or spec.response_media_type != "application/json"
        or not spec.official_authority_source_ref.startswith("SRC-")
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)


def _empty_evidence_document(
    *, product_count: int, plan_sha256: str, portfolio_sha256: str
) -> dict[str, object]:
    return {
        "schema": EMPTY_EVIDENCE_SCHEMA,
        "version": VERSION,
        "publication_authority": PUBLICATION_AUTHORITY,
        "plan_relative_path": PLAN_RELATIVE_PATH.as_posix(),
        "plan_sha256": plan_sha256,
        "portfolio_sha256": portfolio_sha256,
        "owner_private_capture_relative_path": OWNER_CAPTURE_RELATIVE_PATH.as_posix(),
        "tracked_document_is_evidence": False,
        "expected_product_count": product_count,
        "evidence": [],
    }


def _validate_empty_evidence(
    root: Path, plan: ProductSafetyManufacturerQueryPlan
) -> None:
    raw = _read_regular(root, EMPTY_EVIDENCE_RELATIVE_PATH, MAX_EMPTY_EVIDENCE_BYTES)
    document = _strict_json(
        raw,
        maximum=MAX_EMPTY_EVIDENCE_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.EMPTY_EVIDENCE_INVALID,
    )
    expected = _empty_evidence_document(
        product_count=len(plan.products),
        plan_sha256=plan.plan_sha256,
        portfolio_sha256=plan.portfolio_sha256,
    )
    if document != expected or raw != _canonical_json_bytes(expected) + b"\n":
        _fail(ProductSafetyManufacturerCaptureFailureCode.EMPTY_EVIDENCE_INVALID)


def render_product_safety_manufacturer_query_plan(repository_root: Path) -> bytes:
    """Render a plan for the exact tracked portfolio without trusting an old plan."""

    root = _absolute_root(repository_root)
    for spec in _REVIEWED_ENDPOINT_SPECS.values():
        _validate_endpoint_spec(spec)
    portfolio_raw = _read_regular(root, PORTFOLIO_RELATIVE_PATH, MAX_PORTFOLIO_BYTES)
    portfolio_document = _strict_json(
        portfolio_raw,
        maximum=MAX_PORTFOLIO_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID,
    )
    products = _portfolio_products(portfolio_document)
    document = _expected_plan_document(
        products,
        portfolio_sha256=_sha256(portfolio_raw),
    )
    return json.dumps(document, ensure_ascii=False, indent=2).encode() + b"\n"


def render_product_safety_manufacturer_empty_evidence(
    repository_root: Path,
) -> bytes:
    """Render the authority-free empty evidence contract for the current plan."""

    root = _absolute_root(repository_root)
    plan_raw = render_product_safety_manufacturer_query_plan(root)
    portfolio_raw = _read_regular(root, PORTFOLIO_RELATIVE_PATH, MAX_PORTFOLIO_BYTES)
    portfolio_document = _strict_json(
        portfolio_raw,
        maximum=MAX_PORTFOLIO_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID,
    )
    products = _portfolio_products(portfolio_document)
    document = _empty_evidence_document(
        product_count=len(products),
        plan_sha256=_sha256(plan_raw),
        portfolio_sha256=_sha256(portfolio_raw),
    )
    return _canonical_json_bytes(document) + b"\n"


def load_product_safety_manufacturer_query_plan(
    repository_root: Path,
) -> ProductSafetyManufacturerQueryPlan:
    """Load the exact current-product plan and cross-check its code allowlist."""

    root = _absolute_root(repository_root)
    for spec in _REVIEWED_ENDPOINT_SPECS.values():
        _validate_endpoint_spec(spec)
    plan_raw = _read_regular(root, PLAN_RELATIVE_PATH, MAX_PLAN_BYTES)
    portfolio_raw = _read_regular(root, PORTFOLIO_RELATIVE_PATH, MAX_PORTFOLIO_BYTES)
    plan_document = _strict_json(
        plan_raw,
        maximum=MAX_PLAN_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID,
    )
    portfolio_document = _strict_json(
        portfolio_raw,
        maximum=MAX_PORTFOLIO_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID,
    )
    portfolio_products = _portfolio_products(portfolio_document)
    expected_plan = _expected_plan_document(
        portfolio_products,
        portfolio_sha256=_sha256(portfolio_raw),
    )
    if (
        plan_document != expected_plan
        or plan_raw
        != json.dumps(expected_plan, ensure_ascii=False, indent=2).encode() + b"\n"
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID)
    products: list[ProductSafetyManufacturerProductPlan] = []
    for fixed in portfolio_products:
        row = _product_document(fixed)
        contract_id = row["endpoint_contract_id"]
        endpoint_spec: _ReviewedEndpointSpec | None
        if contract_id is None:
            endpoint_spec = None
        else:
            endpoint_spec = _REVIEWED_ENDPOINT_SPECS.get(cast(str, contract_id))
        products.append(
            ProductSafetyManufacturerProductPlan(
                product_id=fixed.product_id,
                exact_model_tokens=fixed.exact_model_tokens,
                query_model_token=fixed.query_model_token,
                manufacturer_code=fixed.manufacturer_code,
                endpoint_review_status=cast(
                    EndpointReviewStatus, row["endpoint_review_status"]
                ),
                endpoint_contract=endpoint_spec,
                manual_required_reason=cast(str | None, row["manual_required_reason"]),
            )
        )
    result = ProductSafetyManufacturerQueryPlan(
        products=tuple(products),
        plan_sha256=_sha256(plan_raw),
        portfolio_sha256=_sha256(portfolio_raw),
    )
    _validate_empty_evidence(root, result)
    return result


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerQueryRequest:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    query_model_token: str
    manufacturer_code: str
    endpoint_contract_id: str
    method: Literal["GET", "POST"]
    endpoint: str
    host: str
    target: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    raw_request: bytes
    parser_version: str
    plan_sha256: str
    portfolio_sha256: str
    request_sha256: str


def _request_material(
    request: ProductSafetyManufacturerQueryRequest,
) -> dict[str, object]:
    return {
        "body_sha256": _sha256(request.body),
        "endpoint": request.endpoint,
        "endpoint_contract_id": request.endpoint_contract_id,
        "headers": [list(row) for row in request.headers],
        "host": request.host,
        "manufacturer_code": request.manufacturer_code,
        "method": request.method,
        "parser_version": request.parser_version,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
        "product_id": request.product_id,
        "query_model_token": request.query_model_token,
        "raw_request_sha256": _sha256(request.raw_request),
        "target": request.target,
    }


def _build_request(
    plan: ProductSafetyManufacturerQueryPlan,
    product: ProductSafetyManufacturerProductPlan,
) -> ProductSafetyManufacturerQueryRequest:
    spec = product.endpoint_contract
    if product.endpoint_review_status != "REVIEWED_EXACT_QUERY" or spec is None:
        _fail(ProductSafetyManufacturerCaptureFailureCode.MANUAL_REQUIRED)
    fields = ((spec.query_field, product.query_model_token), *spec.fixed_query_fields)
    encoded = urlencode(fields, doseq=False, encoding="utf-8", errors="strict")
    parsed = urlsplit(spec.endpoint)
    base_target = parsed.path or "/"
    if spec.method == "GET":
        body = b""
        target = f"{base_target}?{encoded}"
    else:
        body = encoded.encode("ascii")
        target = base_target
    headers: tuple[tuple[str, str], ...] = (
        ("Accept", "application/json"),
        ("Accept-Encoding", "identity"),
        ("Connection", "close"),
        ("Host", spec.host),
        ("User-Agent", USER_AGENT),
    )
    if spec.method == "POST":
        headers = (
            *headers,
            ("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8"),
            ("Content-Length", str(len(body))),
        )
    raw_request = (
        f"{spec.method} {target} HTTP/1.1\r\n"
        + "".join(f"{name}: {value}\r\n" for name, value in headers)
        + "\r\n"
    ).encode("utf-8") + body
    partial = ProductSafetyManufacturerQueryRequest(
        product_id=product.product_id,
        exact_model_tokens=product.exact_model_tokens,
        query_model_token=product.query_model_token,
        manufacturer_code=product.manufacturer_code,
        endpoint_contract_id=spec.contract_id,
        method=spec.method,
        endpoint=spec.endpoint,
        host=spec.host,
        target=target,
        headers=headers,
        body=body,
        raw_request=raw_request,
        parser_version=spec.parser_version,
        plan_sha256=plan.plan_sha256,
        portfolio_sha256=plan.portfolio_sha256,
        request_sha256="",
    )
    return replace(
        partial,
        request_sha256=_sha256(_canonical_json_bytes(_request_material(partial))),
    )


def _validate_request(
    plan: ProductSafetyManufacturerQueryPlan,
    request: ProductSafetyManufacturerQueryRequest,
) -> None:
    if (
        type(plan) is not ProductSafetyManufacturerQueryPlan
        or type(request) is not ProductSafetyManufacturerQueryRequest
    ):
        _fail()
    expected = _build_request(plan, plan.product(request.product_id))
    if request != expected:
        _fail(ProductSafetyManufacturerCaptureFailureCode.REQUEST_INVALID)


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    retrieved_at_utc: str


@runtime_checkable
class ProductSafetyManufacturerTransport(Protocol):
    def execute(
        self, request: ProductSafetyManufacturerQueryRequest
    ) -> ProductSafetyManufacturerHttpResponse: ...


def _require_transport(value: object) -> ProductSafetyManufacturerTransport:
    if not isinstance(value, ProductSafetyManufacturerTransport):
        _fail()
    return value


def _clean_network_environment(environment: Mapping[str, str] | None) -> None:
    values = os.environ if environment is None else environment
    forbidden = {
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
    if any(name in values for name in forbidden):
        _fail(ProductSafetyManufacturerCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE)


def _clock(clock: Callable[[], datetime]) -> str:
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
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class _SystemTransport:
    __slots__ = ("_clock", "_environment")

    def __init__(
        self,
        *,
        clock: Callable[[], datetime],
        environment: Mapping[str, str] | None,
    ) -> None:
        self._clock = clock
        self._environment = environment

    def execute(
        self, request: ProductSafetyManufacturerQueryRequest
    ) -> ProductSafetyManufacturerHttpResponse:
        _clean_network_environment(self._environment)
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        connection = http.client.HTTPSConnection(
            request.host,
            443,
            timeout=CONNECT_TIMEOUT_SECONDS,
            context=context,
        )
        try:
            connection.request(
                request.method,
                request.target,
                body=request.body,
                headers=dict(request.headers),
            )
            if connection.sock is not None:
                connection.sock.settimeout(READ_TIMEOUT_SECONDS)
            response = connection.getresponse()
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(min(65_536, MAX_RESPONSE_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    _fail(
                        ProductSafetyManufacturerCaptureFailureCode.RESPONSE_TOO_LARGE
                    )
            headers = tuple((name, value) for name, value in response.getheaders())
            return ProductSafetyManufacturerHttpResponse(
                status=response.status,
                headers=headers,
                body=b"".join(chunks),
                retrieved_at_utc=_clock(self._clock),
            )
        except ProductSafetyManufacturerCaptureFailure:
            raise
        except BaseException:
            _fail(ProductSafetyManufacturerCaptureFailureCode.CONNECTION_FAILED)
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class _Observation:
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]


def _response_headers(rows: Sequence[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in rows:
        if type(name) is not str or type(value) is not str:
            _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_INVALID)
        key = name.casefold()
        if key in result:
            _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_INVALID)
        result[key] = value.strip()
    return result


def _parse_response(
    request: ProductSafetyManufacturerQueryRequest,
    response: ProductSafetyManufacturerHttpResponse,
) -> tuple[_Observation, str, str]:
    if type(response) is not ProductSafetyManufacturerHttpResponse:
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_INVALID)
    headers = _response_headers(response.headers)
    content_type = headers.get("content-type", "")
    if (
        response.status != 200
        or not 1 <= len(response.body) <= MAX_RESPONSE_BYTES
        or _CONTENT_TYPE_RE.fullmatch(content_type) is None
        or headers.get("content-encoding", "identity").casefold()
        not in {"", "identity"}
        or "location" in headers
        or "set-cookie" in headers
        or "transfer-encoding" in headers
        or (
            "content-length" in headers
            and headers["content-length"] != str(len(response.body))
        )
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_INVALID)
    try:
        retrieved_at = datetime.strptime(
            response.retrieved_at_utc, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except TypeError, ValueError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_INVALID)
    del retrieved_at
    if request.parser_version != "MANUFACTURER_NOTICE_JSON_V1":
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
    raw = _strict_json(
        response.body,
        maximum=MAX_RESPONSE_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED,
    )
    if type(raw) is not dict:
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
    document = cast(dict[str, object], raw)
    if set(document) != {"query_model_token", "result_count", "notices"}:
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
    count = document["result_count"]
    notices = document["notices"]
    if (
        document["query_model_token"] != request.query_model_token
        or type(count) is not int
        or not 0 <= count <= 1000
        or type(notices) is not list
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
    notice_ids: list[str] = []
    for raw_notice in cast(list[object], notices):
        if type(raw_notice) is not dict:
            _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
        notice = cast(dict[str, object], raw_notice)
        if set(notice) != {"notice_id", "model_tokens"}:
            _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
        notice_id = notice["notice_id"]
        tokens = notice["model_tokens"]
        if (
            type(notice_id) is not str
            or _NOTICE_ID_RE.fullmatch(notice_id) is None
            or type(tokens) is not list
            or not tokens
            or any(type(token) is not str for token in cast(list[object], tokens))
            or not set(cast(list[str], tokens)) & set(request.exact_model_tokens)
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.RESPONSE_PARSE_FAILED)
        notice_ids.append(notice_id)
    unique = tuple(sorted(set(notice_ids)))
    if count == 0 and not notice_ids:
        result: ObservationResult = "NONE_FOUND"
    elif count == len(notice_ids) == len(unique) and count > 0:
        result = "MATCH"
    else:
        result = "AMBIGUOUS"
    return _Observation(result, count, unique), content_type, response.retrieved_at_utc


def _safe_private_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
        info = path.stat(follow_symlinks=False)
    except FileExistsError:
        info = path.stat(follow_symlinks=False)
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)


def _capture_root(root: Path, *, create: bool) -> Path:
    secrets = root / OWNER_CAPTURE_RELATIVE_PATH.parts[0]
    capture_root = root / OWNER_CAPTURE_RELATIVE_PATH
    if create:
        _safe_private_directory(secrets, create=True)
        _safe_private_directory(capture_root, create=True)
    return capture_root


def _atomic_private(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        os.chmod(path, PRIVATE_FILE_MODE, follow_symlinks=False)
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _capture_document(
    request: ProductSafetyManufacturerQueryRequest,
    response: ProductSafetyManufacturerHttpResponse,
    observation: _Observation,
    content_type: str,
    retrieved_at: str,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": CAPTURE_SCHEMA,
        "version": VERSION,
        "publication_authority": PUBLICATION_AUTHORITY,
        "credentials_used": False,
        "production_write": False,
        "product_id": request.product_id,
        "exact_model_tokens": list(request.exact_model_tokens),
        "query_model_token": request.query_model_token,
        "manufacturer_code": request.manufacturer_code,
        "endpoint_contract_id": request.endpoint_contract_id,
        "method": request.method,
        "endpoint": request.endpoint,
        "host": request.host,
        "parser_version": request.parser_version,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
        "request_raw_file": REQUEST_FILE_NAME,
        "request_raw_size_bytes": len(request.raw_request),
        "request_raw_sha256": _sha256(request.raw_request),
        "request_material_sha256": request.request_sha256,
        "response_status": response.status,
        "response_content_type": content_type,
        "response_raw_file": RESPONSE_FILE_NAME,
        "response_raw_size_bytes": len(response.body),
        "response_raw_sha256": _sha256(response.body),
        "retrieved_at_utc": retrieved_at,
        "result": observation.result,
        "result_count": observation.result_count,
        "notice_ids": list(observation.notice_ids),
        "coverage_caveat": COVERAGE_CAVEAT,
    }
    document["capture_sha256"] = _sha256(_canonical_json_bytes(document))
    return document


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerCaptureResult:
    product_id: str
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]
    retrieved_at_utc: str
    request_sha256: str
    response_sha256: str
    capture_sha256: str
    metadata_path: Path
    request_path: Path
    response_path: Path
    credentials_used: bool = False
    production_write: bool = False


def capture_product_safety_manufacturer_query(
    repository_root: Path,
    *,
    product_id: str,
    transport: ProductSafetyManufacturerTransport | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    environment: Mapping[str, str] | None = None,
) -> ProductSafetyManufacturerCaptureResult:
    """Capture one code-allowlisted query; unreviewed products fail closed."""

    root = _absolute_root(repository_root)
    plan = load_product_safety_manufacturer_query_plan(root)
    request = _build_request(plan, plan.product(product_id))
    _validate_request(plan, request)
    selected: ProductSafetyManufacturerTransport
    if transport is None:
        selected = _SystemTransport(clock=clock, environment=environment)
    else:
        selected = _require_transport(transport)
    try:
        response = selected.execute(request)
    except ProductSafetyManufacturerCaptureFailure:
        raise
    except BaseException:
        _fail(ProductSafetyManufacturerCaptureFailureCode.CONNECTION_FAILED)
    observation, content_type, retrieved_at = _parse_response(request, response)
    document = _capture_document(
        request, response, observation, content_type, retrieved_at
    )
    capture_root = _capture_root(root, create=True)
    product_root = capture_root / request.product_id
    _safe_private_directory(product_root, create=True)
    lock_path = capture_root / LOCK_FILE_NAME
    lock_descriptor = -1
    try:
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        os.fchmod(lock_descriptor, PRIVATE_FILE_MODE)
        lock_info = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_info.st_mode)
            or lock_info.st_uid != os.getuid()
            or stat.S_IMODE(lock_info.st_mode) != PRIVATE_FILE_MODE
            or lock_info.st_nlink != 1
            or lock_info.st_size != 0
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        _atomic_private(product_root / REQUEST_FILE_NAME, request.raw_request)
        _atomic_private(product_root / RESPONSE_FILE_NAME, response.body)
        _atomic_private(
            product_root / METADATA_FILE_NAME,
            _canonical_json_bytes(document) + b"\n",
        )
    except ProductSafetyManufacturerCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    finally:
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)
    return ProductSafetyManufacturerCaptureResult(
        product_id=request.product_id,
        result=observation.result,
        result_count=observation.result_count,
        notice_ids=observation.notice_ids,
        retrieved_at_utc=retrieved_at,
        request_sha256=_sha256(request.raw_request),
        response_sha256=_sha256(response.body),
        capture_sha256=cast(str, document["capture_sha256"]),
        metadata_path=product_root / METADATA_FILE_NAME,
        request_path=product_root / REQUEST_FILE_NAME,
        response_path=product_root / RESPONSE_FILE_NAME,
    )


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerCaptureEvidence:
    product_id: str
    retrieved_at: datetime
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]
    request_raw_sha256: str
    response_raw_sha256: str
    capture_sha256: str


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerProductEvidence:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    status: ManufacturerProductStatus
    capture: ProductSafetyManufacturerCaptureEvidence | None
    matched_notice_ids: tuple[str, ...]
    endpoint_contract_id: str | None
    manual_required_reason: str | None


@dataclass(frozen=True, slots=True)
class ProductSafetyManufacturerEvidenceSet:
    schema: str
    version: str
    plan_sha256: str
    portfolio_sha256: str
    capture_count: int
    bundle_sha256: str
    evaluated_at: datetime
    products: tuple[ProductSafetyManufacturerProductEvidence, ...]
    complete: bool


def _read_private(path: Path, maximum: int) -> bytes | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != PRIVATE_FILE_MODE
            or info.st_nlink != 1
            or not 1 <= info.st_size <= maximum
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
        raw = os.read(descriptor, info.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != info.st_size or (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
        return raw
    finally:
        os.close(descriptor)


def _validate_private_lock(path: Path) -> None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != PRIVATE_FILE_MODE
            or info.st_nlink != 1
            or info.st_size != 0
        ):
            _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    except FileNotFoundError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    except ProductSafetyManufacturerCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replay_capture(
    directory: Path,
    plan: ProductSafetyManufacturerQueryPlan,
    product: ProductSafetyManufacturerProductPlan,
    evaluated_at: datetime,
) -> ProductSafetyManufacturerCaptureEvidence | None:
    request_raw = _read_private(directory / REQUEST_FILE_NAME, MAX_REQUEST_BYTES)
    response_raw = _read_private(directory / RESPONSE_FILE_NAME, MAX_RESPONSE_BYTES)
    metadata_raw = _read_private(
        directory / METADATA_FILE_NAME, MAX_CAPTURE_METADATA_BYTES
    )
    if request_raw is None and response_raw is None and metadata_raw is None:
        return None
    if request_raw is None or response_raw is None or metadata_raw is None:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    document_raw = _strict_json(
        metadata_raw,
        maximum=MAX_CAPTURE_METADATA_BYTES,
        code=ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID,
    )
    if type(document_raw) is not dict:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    document = cast(dict[str, object], document_raw)
    if metadata_raw != _canonical_json_bytes(document) + b"\n":
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    capture_sha = document.get("capture_sha256")
    material = {
        key: value for key, value in document.items() if key != "capture_sha256"
    }
    if (
        type(capture_sha) is not str
        or _SHA256_RE.fullmatch(capture_sha) is None
        or capture_sha != _sha256(_canonical_json_bytes(material))
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    request = _build_request(plan, product)
    expected = {
        "schema": CAPTURE_SCHEMA,
        "version": VERSION,
        "publication_authority": PUBLICATION_AUTHORITY,
        "credentials_used": False,
        "production_write": False,
        "product_id": product.product_id,
        "exact_model_tokens": list(product.exact_model_tokens),
        "query_model_token": product.query_model_token,
        "manufacturer_code": product.manufacturer_code,
        "endpoint_contract_id": request.endpoint_contract_id,
        "method": request.method,
        "endpoint": request.endpoint,
        "host": request.host,
        "parser_version": request.parser_version,
        "plan_sha256": plan.plan_sha256,
        "portfolio_sha256": plan.portfolio_sha256,
        "request_raw_file": REQUEST_FILE_NAME,
        "request_raw_size_bytes": len(request_raw),
        "request_raw_sha256": _sha256(request_raw),
        "request_material_sha256": request.request_sha256,
        "response_status": 200,
        "response_raw_file": RESPONSE_FILE_NAME,
        "response_raw_size_bytes": len(response_raw),
        "response_raw_sha256": _sha256(response_raw),
        "coverage_caveat": COVERAGE_CAVEAT,
    }
    if request_raw != request.raw_request or any(
        document.get(key) != value for key, value in expected.items()
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    content_type = document.get("response_content_type")
    retrieved_at_text = document.get("retrieved_at_utc")
    if type(content_type) is not str or type(retrieved_at_text) is not str:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    response = ProductSafetyManufacturerHttpResponse(
        status=200,
        headers=(("Content-Type", content_type),),
        body=response_raw,
        retrieved_at_utc=retrieved_at_text,
    )
    observation, replay_type, replay_time = _parse_response(request, response)
    if (
        replay_type != content_type
        or replay_time != retrieved_at_text
        or document.get("result") != observation.result
        or document.get("result_count") != observation.result_count
        or document.get("notice_ids") != list(observation.notice_ids)
    ):
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    try:
        retrieved_at = datetime.strptime(
            retrieved_at_text, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except ValueError:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    if retrieved_at - evaluated_at > MAX_FUTURE_SKEW:
        _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
    return ProductSafetyManufacturerCaptureEvidence(
        product_id=product.product_id,
        retrieved_at=retrieved_at,
        result=observation.result,
        result_count=observation.result_count,
        notice_ids=observation.notice_ids,
        request_raw_sha256=_sha256(request_raw),
        response_raw_sha256=_sha256(response_raw),
        capture_sha256=capture_sha,
    )


def _evaluated_at(now: datetime | None) -> datetime:
    value = datetime.now(UTC) if now is None else now
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail()
    return value.astimezone(UTC)


def _bundle_material(
    plan: ProductSafetyManufacturerQueryPlan,
    products: Sequence[ProductSafetyManufacturerProductEvidence],
) -> dict[str, object]:
    return {
        "schema": BUNDLE_SCHEMA,
        "version": VERSION,
        "plan_sha256": plan.plan_sha256,
        "portfolio_sha256": plan.portfolio_sha256,
        "products": [
            {
                "product_id": row.product_id,
                "status": row.status,
                "endpoint_contract_id": row.endpoint_contract_id,
                "manual_required_reason": row.manual_required_reason,
                "capture_sha256": None
                if row.capture is None
                else row.capture.capture_sha256,
            }
            for row in products
        ],
    }


def verify_product_safety_manufacturer_capture_set(
    repository_root: Path,
    *,
    now: datetime | None = None,
) -> ProductSafetyManufacturerEvidenceSet:
    """Replay owner-private captures and derive every current product status."""

    root = _absolute_root(repository_root)
    evaluated_at = _evaluated_at(now)
    plan = load_product_safety_manufacturer_query_plan(root)
    capture_root = root / OWNER_CAPTURE_RELATIVE_PATH
    root_exists = capture_root.exists()
    if root_exists:
        _safe_private_directory(
            root / OWNER_CAPTURE_RELATIVE_PATH.parts[0], create=False
        )
        _safe_private_directory(capture_root, create=False)
        try:
            names = {entry.name for entry in os.scandir(capture_root)}
        except OSError:
            _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
        allowed = {
            LOCK_FILE_NAME,
            *(
                row.product_id
                for row in plan.products
                if row.endpoint_review_status == "REVIEWED_EXACT_QUERY"
            ),
        }
        if not names <= allowed or LOCK_FILE_NAME not in names:
            _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
        _validate_private_lock(capture_root / LOCK_FILE_NAME)
    products: list[ProductSafetyManufacturerProductEvidence] = []
    for product in plan.products:
        if product.endpoint_review_status == "MANUAL_REQUIRED":
            products.append(
                ProductSafetyManufacturerProductEvidence(
                    product_id=product.product_id,
                    exact_model_tokens=product.exact_model_tokens,
                    status="MANUAL_REQUIRED",
                    capture=None,
                    matched_notice_ids=(),
                    endpoint_contract_id=None,
                    manual_required_reason=MANUAL_REQUIRED_REASON,
                )
            )
            continue
        product_root = capture_root / product.product_id
        capture: ProductSafetyManufacturerCaptureEvidence | None = None
        if root_exists and product_root.exists():
            _safe_private_directory(product_root, create=False)
            try:
                names = {entry.name for entry in os.scandir(product_root)}
            except OSError:
                _fail(ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE)
            if names != {REQUEST_FILE_NAME, RESPONSE_FILE_NAME, METADATA_FILE_NAME}:
                _fail(ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID)
            capture = _replay_capture(product_root, plan, product, evaluated_at)
        if capture is None:
            status: ManufacturerProductStatus = "BLOCKED_MISSING_CAPTURE"
            matched: tuple[str, ...] = ()
        elif capture.result == "MATCH":
            status = "BLOCKED_MATCH_FOUND"
            matched = capture.notice_ids
        elif capture.result == "AMBIGUOUS":
            status = "BLOCKED_AMBIGUOUS_RESULT"
            matched = capture.notice_ids
        elif evaluated_at - capture.retrieved_at > MAX_CAPTURE_AGE:
            status = "BLOCKED_STALE_CAPTURE"
            matched = ()
        else:
            status = "VERIFIED_NONE_FOUND"
            matched = ()
        products.append(
            ProductSafetyManufacturerProductEvidence(
                product_id=product.product_id,
                exact_model_tokens=product.exact_model_tokens,
                status=status,
                capture=capture,
                matched_notice_ids=matched,
                endpoint_contract_id=(
                    None
                    if product.endpoint_contract is None
                    else product.endpoint_contract.contract_id
                ),
                manual_required_reason=None,
            )
        )
    capture_count = sum(row.capture is not None for row in products)
    bundle_sha = _sha256(_canonical_json_bytes(_bundle_material(plan, products)))
    return ProductSafetyManufacturerEvidenceSet(
        schema=BUNDLE_SCHEMA,
        version=VERSION,
        plan_sha256=plan.plan_sha256,
        portfolio_sha256=plan.portfolio_sha256,
        capture_count=capture_count,
        bundle_sha256=bundle_sha,
        evaluated_at=evaluated_at,
        products=tuple(products),
        complete=all(row.status == "VERIFIED_NONE_FOUND" for row in products),
    )


def describe_product_safety_manufacturer_query(
    repository_root: Path, *, product_id: str
) -> dict[str, object]:
    """Return safe dry-run metadata; never hide a manual-review requirement."""

    plan = load_product_safety_manufacturer_query_plan(repository_root)
    product = plan.product(product_id)
    if product.endpoint_review_status == "MANUAL_REQUIRED":
        return {
            "status": "MANUAL_REQUIRED",
            "publication_authority": PUBLICATION_AUTHORITY,
            "credentials_used": False,
            "production_write": False,
            "product_id": product.product_id,
            "manufacturer_code": product.manufacturer_code,
            "query_model_token": product.query_model_token,
            "reason": MANUAL_REQUIRED_REASON,
            "plan_sha256": plan.plan_sha256,
            "portfolio_sha256": plan.portfolio_sha256,
        }
    request = _build_request(plan, product)
    return {
        "status": "DRY_RUN",
        "publication_authority": PUBLICATION_AUTHORITY,
        "credentials_used": False,
        "production_write": False,
        "product_id": request.product_id,
        "manufacturer_code": request.manufacturer_code,
        "query_model_token": request.query_model_token,
        "endpoint_contract_id": request.endpoint_contract_id,
        "method": request.method,
        "endpoint": request.endpoint,
        "host": request.host,
        "parser_version": request.parser_version,
        "request_material_sha256": request.request_sha256,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
    }
