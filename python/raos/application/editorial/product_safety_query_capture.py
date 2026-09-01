"""Bounded, credential-free capture of official product-safety search results.

The public entry points accept only a tracked product identity and one of three
fixed Japanese administrative searches.  URLs, methods, headers, form fields,
query strings, output locations, and parsers are all derived from a tracked
plan that is cross-checked against the current editorial portfolio and against
constants in this module.

This is evidence collection, not a safety conclusion.  In particular,
``NONE_FOUND`` means only that one exact, parseable official query returned
zero rows at the recorded time.  Manufacturer evidence is deliberately outside
this adapter and remains a separate fail-closed requirement.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import fcntl
from html.parser import HTMLParser
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import stat
from typing import Final, Literal, NoReturn, Protocol, cast, final, runtime_checkable
import unicodedata
from urllib.parse import SplitResult, urlencode, urlsplit


QUERY_PLAN_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "product-safety-query-plan.v1.json"
)
PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
OWNER_CAPTURE_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-product-safety-query-capture-v1"
)
QUERY_PLAN_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_QUERY_PLAN_V1"
CAPTURE_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_QUERY_CAPTURE_V1"
CAPTURE_BUNDLE_SCHEMA: Final = "RAOS_PRODUCT_SAFETY_ADMIN_CAPTURE_BUNDLE_V1"
QUERY_PLAN_VERSION: Final = "1.0.0"
CAPTURE_VERSION: Final = "1.0.0"
CAPTURE_BUNDLE_VERSION: Final = "1.0.0"
PUBLICATION_AUTHORITY: Final = "NONE"
PARSER_VERSION_CAA: Final = "CAA_RECALL_HTML_V1"
PARSER_VERSION_NITE_RECALL: Final = "NITE_RECALL_JSON_HTML_V1"
PARSER_VERSION_NITE_ACCIDENT: Final = "NITE_ACCIDENT_JSON_HTML_V1"
PROVIDER_SCOPE_COUNT: Final = 3
MAX_PLAN_BYTES: Final = 256 * 1024
MAX_PORTFOLIO_BYTES: Final = 4 * 1024 * 1024
MAX_RESPONSE_BYTES: Final = 4 * 1024 * 1024
MAX_CAPTURE_METADATA_BYTES: Final = 128 * 1024
MAX_QUERY_BYTES: Final = 100
CONNECT_TIMEOUT_SECONDS: Final = 10
READ_TIMEOUT_SECONDS: Final = 20
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
MAX_CAPTURE_AGE: Final = timedelta(days=30)
MAX_CAPTURE_FUTURE_SKEW: Final = timedelta(minutes=5)
CAPTURE_LOCK_FILE: Final = "product-safety-query-capture.lock"
CAPTURE_USER_AGENT: Final = (
    "Mozilla/5.0 (compatible; RAOS-product-safety-query-capture/1; "
    "+https://kurashinoshirube.com/comparison-policy/)"
)
COVERAGE_CAVEAT: Final = (
    "この結果は、記録した公式検索・型番・確認日時の範囲だけを示し、"
    "安全情報が存在しないことを一般に証明しません。"
)

Provider = Literal["CAA", "NITE"]
Scope = Literal["RECALL", "ACCIDENT"]
ObservationResult = Literal["NONE_FOUND", "MATCH", "AMBIGUOUS"]
ProviderScope = tuple[Provider, Scope]

_PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_NOTICE_ID_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_CONTENT_LENGTH_RE: Final = re.compile(r"0|[1-9][0-9]*\Z", re.ASCII)
_MEDIA_TYPE_RE: Final = re.compile(
    r"(text/html|application/json)(?:\s*;\s*charset=\"?([A-Za-z0-9._-]+)\"?)?\Z",
    re.ASCII | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _ProviderSpec:
    provider: Provider
    scope: Scope
    endpoint: str
    query_field: str
    fixed_fields: tuple[tuple[str, str], ...]
    response_media_type: str
    parser_version: str
    maximum_results_per_response: int


_PROVIDER_SPECS: Final[dict[ProviderScope, _ProviderSpec]] = {
    ("CAA", "RECALL"): _ProviderSpec(
        provider="CAA",
        scope="RECALL",
        endpoint="https://www.recall.caa.go.jp/result/index.php",
        query_field="search",
        fixed_fields=(("screenkbn", "01"), ("category", "0")),
        response_media_type="text/html",
        parser_version=PARSER_VERSION_CAA,
        maximum_results_per_response=15,
    ),
    ("NITE", "RECALL"): _ProviderSpec(
        provider="NITE",
        scope="RECALL",
        endpoint="https://safe-lite.nite.go.jp/recall/search/index",
        query_field="searchWord",
        fixed_fields=(("isFreewordSearch", "true"), ("pagesize", "100")),
        response_media_type="application/json",
        parser_version=PARSER_VERSION_NITE_RECALL,
        maximum_results_per_response=100,
    ),
    ("NITE", "ACCIDENT"): _ProviderSpec(
        provider="NITE",
        scope="ACCIDENT",
        endpoint="https://safe-lite.nite.go.jp/jiko/search/index",
        query_field="searchWord",
        fixed_fields=(
            ("isMajor", "3"),
            ("isFreewordSearch", "true"),
            ("pagesize", "100"),
        ),
        response_media_type="application/json",
        parser_version=PARSER_VERSION_NITE_ACCIDENT,
        maximum_results_per_response=100,
    ),
}


class ProductSafetyQueryCaptureFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PLAN_INVALID = "PLAN_INVALID"
    PRODUCT_NOT_ALLOWLISTED = "PRODUCT_NOT_ALLOWLISTED"
    PROVIDER_SCOPE_NOT_ALLOWLISTED = "PROVIDER_SCOPE_NOT_ALLOWLISTED"
    REQUEST_INVALID = "REQUEST_INVALID"
    NETWORK_ENVIRONMENT_UNSAFE = "NETWORK_ENVIRONMENT_UNSAFE"
    DNS_FAILED = "DNS_FAILED"
    DNS_ADDRESS_REJECTED = "DNS_ADDRESS_REJECTED"
    TLS_CONTEXT_INVALID = "TLS_CONTEXT_INVALID"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "REQUEST_AMBIGUOUS"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    CONTENT_TYPE_INVALID = "CONTENT_TYPE_INVALID"
    RESPONSE_PARSE_FAILED = "RESPONSE_PARSE_FAILED"
    QUERY_ECHO_MISMATCH = "QUERY_ECHO_MISMATCH"
    STORE_UNSAFE = "STORE_UNSAFE"
    EVIDENCE_SET_MISSING = "EVIDENCE_SET_MISSING"
    EVIDENCE_SET_INVALID = "EVIDENCE_SET_INVALID"


class ProductSafetyQueryCaptureFailure(RuntimeError):
    """Sanitized failure that never includes request or response material."""

    __slots__ = ("_code",)

    def __init__(self, code: ProductSafetyQueryCaptureFailureCode) -> None:
        if type(code) is not ProductSafetyQueryCaptureFailureCode:
            raise TypeError("invalid product-safety query failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> ProductSafetyQueryCaptureFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ProductSafetyQueryCaptureFailure(code={self.code.value})"


def _fail(
    code: ProductSafetyQueryCaptureFailureCode = (
        ProductSafetyQueryCaptureFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ProductSafetyQueryCaptureFailure(code) from None


def _strict_json(
    raw: bytes,
    *,
    maximum: int,
    failure_code: ProductSafetyQueryCaptureFailureCode,
) -> object:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= maximum
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        _fail(failure_code)
    def pairs(rows: list[tuple[object, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in rows:
            if type(key) is not str or key in result:
                _fail(failure_code)
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            _fail(failure_code)
        return parsed

    def reject_constant(value: str) -> NoReturn:
        del value
        _fail(failure_code)

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_float=finite_float,
            parse_constant=reject_constant,
        )
    except ProductSafetyQueryCaptureFailure:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        _fail(failure_code)


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    return value


def _exact(value: Mapping[str, object], keys: frozenset[str]) -> None:
    if frozenset(value) != keys:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)


def _absolute_repository_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail()
    return value


def _read_regular_file(repository_root: Path, relative: Path, maximum: int) -> bytes:
    root = _absolute_repository_root(repository_root)
    target = root / relative
    descriptor = -1
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
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
            _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
        return b"".join(chunks)
    except ProductSafetyQueryCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class ProductQueryIdentity:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    query_model_token: str


@dataclass(frozen=True, slots=True)
class ProductSafetyQueryPlan:
    products: tuple[ProductQueryIdentity, ...]
    provider_specs: tuple[_ProviderSpec, ...]
    plan_sha256: str
    portfolio_sha256: str

    def product(self, product_id: str) -> ProductQueryIdentity:
        if type(product_id) is not str:
            _fail()
        matches = tuple(row for row in self.products if row.product_id == product_id)
        if len(matches) != 1:
            _fail(ProductSafetyQueryCaptureFailureCode.PRODUCT_NOT_ALLOWLISTED)
        return matches[0]

    def provider_spec(self, provider: str, scope: str) -> _ProviderSpec:
        if type(provider) is not str or type(scope) is not str:
            _fail()
        matches = tuple(
            row
            for row in self.provider_specs
            if row.provider == provider and row.scope == scope
        )
        if len(matches) != 1:
            _fail(
                ProductSafetyQueryCaptureFailureCode.PROVIDER_SCOPE_NOT_ALLOWLISTED
            )
        return matches[0]


_PLAN_ROOT_KEYS: Final = frozenset(
    {
        "schema",
        "version",
        "publication_authority",
        "portfolio_relative_path",
        "coverage_caveat",
        "normalization_policy",
        "matrix",
        "provider_scopes",
        "products",
    }
)
_PRODUCT_KEYS: Final = frozenset(
    {"product_id", "exact_model_tokens", "query_model_token"}
)
_PROVIDER_KEYS: Final = frozenset(
    {
        "provider",
        "scope",
        "method",
        "endpoint",
        "query_field",
        "fixed_fields",
        "response_media_type",
        "parser_version",
        "maximum_results_per_response",
    }
)
_NORMALIZATION_POLICY: Final = {
    "query_normalization": "NFKC_EXACT_MODEL_TOKEN_UTF8",
    "notice_id_order": "LEXICOGRAPHIC_UNIQUE",
    "none_found_rule": "PARSEABLE_OFFICIAL_ZERO_RESULT_ONLY",
    "positive_result_rule": "MATCH_IF_COUNT_EQUALS_UNIQUE_NOTICE_IDS_ELSE_AMBIGUOUS",
    "manufacturer_extension": "SEPARATE_FAIL_CLOSED_NOT_IMPLEMENTED_HERE",
}


def _provider_document(spec: _ProviderSpec) -> dict[str, object]:
    return {
        "provider": spec.provider,
        "scope": spec.scope,
        "method": "POST",
        "endpoint": spec.endpoint,
        "query_field": spec.query_field,
        "fixed_fields": [
            {"name": name, "value": value} for name, value in spec.fixed_fields
        ],
        "response_media_type": spec.response_media_type,
        "parser_version": spec.parser_version,
        "maximum_results_per_response": spec.maximum_results_per_response,
    }


def _portfolio_products(document: Mapping[str, object]) -> tuple[ProductQueryIdentity, ...]:
    if document.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V2":
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    selected_product_ids: set[str] = set()
    for raw_article in _list(document.get("articles")):
        article = _mapping(raw_article)
        for raw_product_id in _list(article.get("product_ids")):
            selected_product_ids.add(_text(raw_product_id, maximum=200))
    rows = _list(document.get("products"))
    products: list[ProductQueryIdentity] = []
    observed: set[str] = set()
    for raw_row in rows:
        row = _mapping(raw_row)
        product_id = _text(row.get("product_id"), maximum=200)
        raw_models = _list(row.get("official_models"))
        models = tuple(_text(value, maximum=100) for value in raw_models)
        representative_model = _text(row.get("representative_model"), maximum=100)
        if (
            _PRODUCT_ID_RE.fullmatch(product_id) is None
            or product_id in observed
            or not models
            or len(models) != len(set(models))
            or representative_model not in models
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
        observed.add(product_id)
        products.append(
            ProductQueryIdentity(product_id, models, representative_model)
        )
    if (
        not products
        or len(products) > 100
        or selected_product_ids != {product.product_id for product in products}
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    return tuple(products)


def load_product_safety_query_plan(repository_root: Path) -> ProductSafetyQueryPlan:
    """Bind every planned identity to the tracked V2 selected-product set."""

    plan_raw = _read_regular_file(
        repository_root, QUERY_PLAN_RELATIVE_PATH, MAX_PLAN_BYTES
    )
    portfolio_raw = _read_regular_file(
        repository_root, PORTFOLIO_RELATIVE_PATH, MAX_PORTFOLIO_BYTES
    )
    plan = _mapping(
        _strict_json(
            plan_raw,
            maximum=MAX_PLAN_BYTES,
            failure_code=ProductSafetyQueryCaptureFailureCode.PLAN_INVALID,
        )
    )
    portfolio = _mapping(
        _strict_json(
            portfolio_raw,
            maximum=MAX_PORTFOLIO_BYTES,
            failure_code=ProductSafetyQueryCaptureFailureCode.PLAN_INVALID,
        )
    )
    _exact(plan, _PLAN_ROOT_KEYS)
    if (
        plan["schema"] != QUERY_PLAN_SCHEMA
        or plan["version"] != QUERY_PLAN_VERSION
        or plan["publication_authority"] != PUBLICATION_AUTHORITY
        or plan["portfolio_relative_path"] != PORTFOLIO_RELATIVE_PATH.as_posix()
        or plan["coverage_caveat"] != COVERAGE_CAVEAT
        or plan["normalization_policy"] != _NORMALIZATION_POLICY
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)

    provider_rows = _list(plan["provider_scopes"])
    expected_provider_documents = tuple(
        _provider_document(_PROVIDER_SPECS[key]) for key in _PROVIDER_SPECS
    )
    if tuple(provider_rows) != expected_provider_documents:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)

    portfolio_products = _portfolio_products(portfolio)
    expected_matrix = {
        "mode": "ALL_PRODUCTS_X_ALL_PROVIDER_SCOPES",
        "expected_product_count": len(portfolio_products),
        "expected_provider_scope_count": PROVIDER_SCOPE_COUNT,
        "expected_query_count": len(portfolio_products) * PROVIDER_SCOPE_COUNT,
    }
    if plan["matrix"] != expected_matrix:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    product_rows = _list(plan["products"])
    planned_products: list[ProductQueryIdentity] = []
    for raw_row in product_rows:
        row = _mapping(raw_row)
        _exact(row, _PRODUCT_KEYS)
        product_id = _text(row["product_id"], maximum=200)
        models = tuple(
            _text(value, maximum=100) for value in _list(row["exact_model_tokens"])
        )
        query_model = _text(row["query_model_token"], maximum=100)
        if (
            _PRODUCT_ID_RE.fullmatch(product_id) is None
            or not models
            or len(models) != len(set(models))
            or query_model not in models
            or unicodedata.normalize("NFKC", query_model) != query_model
            or not 1 <= len(query_model.encode("utf-8")) <= MAX_QUERY_BYTES
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
        planned_products.append(ProductQueryIdentity(product_id, models, query_model))
    if tuple(planned_products) != portfolio_products:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)

    return ProductSafetyQueryPlan(
        products=tuple(planned_products),
        provider_specs=tuple(_PROVIDER_SPECS.values()),
        plan_sha256=_sha256(plan_raw),
        portfolio_sha256=_sha256(portfolio_raw),
    )


def _request_headers(spec: _ProviderSpec) -> tuple[tuple[str, str], ...]:
    parsed = urlsplit(spec.endpoint)
    if parsed.hostname is None:
        _fail(ProductSafetyQueryCaptureFailureCode.PLAN_INVALID)
    common = (
        ("Accept-Encoding", "identity"),
        ("Connection", "close"),
        ("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8"),
        ("Host", parsed.hostname),
        ("User-Agent", CAPTURE_USER_AGENT),
    )
    if spec.provider == "CAA":
        return (("Accept", "text/html"), *common)
    return (
        ("Accept", "application/json"),
        *common,
        ("Origin", "https://safe-lite.nite.go.jp"),
        ("Referer", "https://safe-lite.nite.go.jp/"),
        ("X-Requested-With", "XMLHttpRequest"),
    )


@dataclass(frozen=True, slots=True)
class ProductSafetyQueryRequest:
    product_id: str
    exact_model_tokens: tuple[str, ...]
    query: str
    provider: Provider
    scope: Scope
    method: str
    endpoint: str
    headers: tuple[tuple[str, str], ...]
    form_fields: tuple[tuple[str, str], ...]
    body: bytes
    request_material_sha256: str
    plan_sha256: str
    portfolio_sha256: str
    parser_version: str


def _request_hash_material(request: ProductSafetyQueryRequest) -> dict[str, object]:
    return {
        "body_sha256": _sha256(request.body),
        "endpoint": request.endpoint,
        "form_fields": [list(row) for row in request.form_fields],
        "headers": [list(row) for row in request.headers],
        "method": request.method,
        "parser_version": request.parser_version,
        "portfolio_sha256": request.portfolio_sha256,
        "product_id": request.product_id,
        "provider": request.provider,
        "query": request.query,
        "scope": request.scope,
        "plan_sha256": request.plan_sha256,
    }


def build_product_safety_query_request(
    plan: ProductSafetyQueryPlan,
    *,
    product_id: str,
    provider: str,
    scope: str,
) -> ProductSafetyQueryRequest:
    """Build one request solely from allowlisted product/provider/scope values."""

    if type(plan) is not ProductSafetyQueryPlan:
        _fail()
    product = plan.product(product_id)
    spec = plan.provider_spec(provider, scope)
    query = product.query_model_token
    form_fields = ((spec.query_field, query), *spec.fixed_fields)
    body = urlencode(form_fields, doseq=False, encoding="utf-8", errors="strict").encode(
        "ascii"
    )
    partial = ProductSafetyQueryRequest(
        product_id=product.product_id,
        exact_model_tokens=product.exact_model_tokens,
        query=query,
        provider=spec.provider,
        scope=spec.scope,
        method="POST",
        endpoint=spec.endpoint,
        headers=_request_headers(spec),
        form_fields=form_fields,
        body=body,
        request_material_sha256="",
        plan_sha256=plan.plan_sha256,
        portfolio_sha256=plan.portfolio_sha256,
        parser_version=spec.parser_version,
    )
    digest = _sha256(canonical_json_bytes(_request_hash_material(partial)))
    request = replace(partial, request_material_sha256=digest)
    validate_product_safety_query_request(plan, request)
    return request


def validate_product_safety_query_request(
    plan: ProductSafetyQueryPlan, request: ProductSafetyQueryRequest
) -> None:
    """Reject any request mutation, including URL, method, header, or body drift."""

    if type(plan) is not ProductSafetyQueryPlan or type(request) is not ProductSafetyQueryRequest:
        _fail()
    product = plan.product(request.product_id)
    spec = plan.provider_spec(request.provider, request.scope)
    expected_fields = ((spec.query_field, product.query_model_token), *spec.fixed_fields)
    expected_body = urlencode(
        expected_fields, doseq=False, encoding="utf-8", errors="strict"
    ).encode("ascii")
    expected = {
        "exact_model_tokens": product.exact_model_tokens,
        "query": product.query_model_token,
        "method": "POST",
        "endpoint": spec.endpoint,
        "headers": _request_headers(spec),
        "form_fields": expected_fields,
        "body": expected_body,
        "plan_sha256": plan.plan_sha256,
        "portfolio_sha256": plan.portfolio_sha256,
        "parser_version": spec.parser_version,
    }
    if any(getattr(request, key) != value for key, value in expected.items()):
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)
    material = _request_hash_material(request)
    if (
        _SHA256_RE.fullmatch(request.request_material_sha256) is None
        or _sha256(canonical_json_bytes(material))
        != request.request_material_sha256
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)


def _validate_closed_request_shape(request: ProductSafetyQueryRequest) -> None:
    """Recheck compile-time boundaries at the transport edge."""

    if type(request) is not ProductSafetyQueryRequest:
        _fail()
    spec = _PROVIDER_SPECS.get((request.provider, request.scope))
    expected_fields = (
        ()
        if spec is None
        else ((spec.query_field, request.query), *spec.fixed_fields)
    )
    expected_body = (
        b""
        if spec is None
        else urlencode(
            expected_fields,
            doseq=False,
            encoding="utf-8",
            errors="strict",
        ).encode("ascii")
    )
    if (
        spec is None
        or _PRODUCT_ID_RE.fullmatch(request.product_id) is None
        or not request.exact_model_tokens
        or len(request.exact_model_tokens) != len(set(request.exact_model_tokens))
        or request.query not in request.exact_model_tokens
        or unicodedata.normalize("NFKC", request.query) != request.query
        or not 1 <= len(request.query.encode("utf-8")) <= MAX_QUERY_BYTES
        or request.method != "POST"
        or request.endpoint != spec.endpoint
        or request.headers != _request_headers(spec)
        or request.form_fields != expected_fields
        or request.body != expected_body
        or request.parser_version != spec.parser_version
        or _SHA256_RE.fullmatch(request.plan_sha256) is None
        or _SHA256_RE.fullmatch(request.portfolio_sha256) is None
        or _SHA256_RE.fullmatch(request.request_material_sha256) is None
        or _sha256(canonical_json_bytes(_request_hash_material(request)))
        != request.request_material_sha256
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)


def require_clean_network_environment(
    environment: Mapping[str, str] | None = None,
) -> None:
    """Refuse proxy and TLS override variables before any DNS or connection."""

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
        _fail(ProductSafetyQueryCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE)


@dataclass(frozen=True, slots=True)
class ProductSafetyHttpResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    retrieved_at_utc: str


@runtime_checkable
class ProductSafetyQueryTransport(Protocol):
    def post(
        self, request: ProductSafetyQueryRequest
    ) -> ProductSafetyHttpResponse: ...


@runtime_checkable
class ProductSafetyHttpsResponse(Protocol):
    status: int

    def getheaders(self) -> list[tuple[str, str]]: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class ProductSafetyHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None: ...

    def getresponse(self) -> ProductSafetyHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class ProductSafetyHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> ProductSafetyHttpsConnection: ...


def _require_query_transport(value: object) -> ProductSafetyQueryTransport:
    if not isinstance(value, ProductSafetyQueryTransport):
        _fail()
    return value


def _require_connection_factory(
    value: object,
) -> ProductSafetyHttpsConnectionFactory:
    if not isinstance(value, ProductSafetyHttpsConnectionFactory):
        _fail()
    return value


@dataclass(frozen=True, slots=True)
class _ResolvedAddress:
    family: int
    socket_type: int
    protocol: int
    socket_address: tuple[str, int] | tuple[str, int, int, int]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


def _public_ip(
    value: object, *, family: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str:
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
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
        or (
            type(address) is ipaddress.IPv6Address
            and (address.ipv4_mapped is not None or address.scope_id is not None)
        )
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_ADDRESS_REJECTED)
    return address


def _resolve_public_addresses(host: str) -> tuple[_ResolvedAddress, ...]:
    try:
        rows = socket.getaddrinfo(
            host,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
            flags=0,
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
    if type(rows) is not list or not rows or len(rows) > 64:
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
    result: list[_ResolvedAddress] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 5 or type(row[4]) is not tuple:
            _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
        family, socket_type, protocol, canonical_name, raw_address = row
        if (
            family not in {socket.AF_INET, socket.AF_INET6}
            or socket_type != socket.SOCK_STREAM
            or protocol != socket.IPPROTO_TCP
            or type(canonical_name) is not str
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
        values = cast(tuple[object, ...], raw_address)
        if family == socket.AF_INET:
            if len(values) != 2 or values[1] != 443:
                _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
            ip = _public_ip(values[0], family=socket.AF_INET)
            socket_address: tuple[str, int] | tuple[str, int, int, int] = (
                str(ip),
                443,
            )
        else:
            if (
                len(values) != 4
                or values[1] != 443
                or values[2] != 0
                or values[3] != 0
            ):
                _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
            ip = _public_ip(values[0], family=socket.AF_INET6)
            socket_address = (str(ip), 443, 0, 0)
        candidate = _ResolvedAddress(
            family=cast(int, family),
            socket_type=cast(int, socket_type),
            protocol=protocol,
            socket_address=socket_address,
            ip=ip,
        )
        if candidate not in result:
            result.append(candidate)
    if not result:
        _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
    return tuple(result)


def _require_peer(candidate: _ResolvedAddress, peer: object) -> None:
    if type(peer) is not tuple:
        _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
    values = cast(tuple[object, ...], peer)
    if (
        len(values) not in {2, 4}
        or values[1] != 443
        or (candidate.family == socket.AF_INET and len(values) != 2)
        or (candidate.family == socket.AF_INET6 and len(values) != 4)
        or _public_ip(values[0], family=candidate.family) != candidate.ip
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)


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
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        self.attempted = True
        connection = socket.socket(
            self.candidate.family,
            self.candidate.socket_type,
            self.candidate.protocol,
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
class _SystemConnection:
    __slots__ = ("_attempted", "_candidates", "_connection", "_host", "_context")

    def __init__(
        self,
        *,
        host: str,
        candidates: tuple[_ResolvedAddress, ...],
        context: ssl.SSLContext,
    ) -> None:
        self._attempted = False
        self._candidates = candidates
        self._connection: http.client.HTTPSConnection | None = None
        self._host = host
        self._context = context

    def connect(self) -> None:
        if self._attempted or not self._candidates:
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        self._attempted = True
        for candidate in self._candidates:
            connection: http.client.HTTPSConnection | None = None
            try:
                connection = http.client.HTTPSConnection(
                    host=self._host,
                    port=443,
                    timeout=CONNECT_TIMEOUT_SECONDS,
                    context=self._context,
                )
                setattr(
                    connection,
                    "_create_connection",
                    _PinnedConnector(self._host, candidate),
                )
                if getattr(connection, "_tunnel_host", None) is not None:
                    _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
                connection.connect()
                if connection.sock is None:
                    _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
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
        _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)

    def set_read_timeout(self, seconds: int) -> None:
        if (
            self._connection is None
            or self._connection.sock is None
            or seconds != READ_TIMEOUT_SECONDS
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        self._connection.sock.settimeout(seconds)

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        if self._connection is None:
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        self._connection.request(method, path, body=body, headers=headers)

    def getresponse(self) -> ProductSafetyHttpsResponse:
        if self._connection is None:
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        return cast(ProductSafetyHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()


@final
class _SystemConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> ProductSafetyHttpsConnection:
        if (
            host not in {"www.recall.caa.go.jp", "safe-lite.nite.go.jp"}
            or port != 443
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
            or tls_context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.TLS_CONTEXT_INVALID)
        return _SystemConnection(
            host=host,
            candidates=_resolve_public_addresses(host),
            context=tls_context,
        )


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
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _response_headers(rows: object) -> dict[str, str]:
    if type(rows) is not list:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    headers: dict[str, str] = {}
    relevant = {
        "content-encoding",
        "content-length",
        "content-type",
        "location",
        "transfer-encoding",
    }
    for raw_row in cast(list[object], rows):
        if (
            type(raw_row) is not tuple
            or len(cast(tuple[object, ...], raw_row)) != 2
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
        key, value = cast(tuple[object, object], raw_row)
        if type(key) is not str or type(value) is not str:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
        normalized = key.casefold()
        if normalized not in relevant:
            continue
        if normalized in headers or "\r" in value or "\n" in value:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
        headers[normalized] = value.strip()
    return headers


def _bounded_response_body(
    response: ProductSafetyHttpsResponse, headers: Mapping[str, str]
) -> bytes:
    raw_length = headers.get("content-length")
    transfer_encoding = headers.get("transfer-encoding")
    expected: int | None = None
    if raw_length is not None:
        if _CONTENT_LENGTH_RE.fullmatch(raw_length) is None:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
        expected = int(raw_length)
        if expected > MAX_RESPONSE_BYTES:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_TOO_LARGE)
        if transfer_encoding is not None:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    elif transfer_encoding is not None and transfer_encoding.casefold() != "chunked":
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    chunks: list[bytes] = []
    observed = 0
    while True:
        try:
            chunk = response.read(min(65_536, MAX_RESPONSE_BYTES + 1 - observed))
        except BaseException:
            _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_AMBIGUOUS)
        if type(chunk) is not bytes:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
        if not chunk:
            break
        chunks.append(chunk)
        observed += len(chunk)
        if observed > MAX_RESPONSE_BYTES:
            _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_TOO_LARGE)
    if observed < 1 or (expected is not None and observed != expected):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    return b"".join(chunks)


def _request_path(endpoint: str) -> tuple[str, SplitResult]:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)
    if (
        endpoint not in {spec.endpoint for spec in _PROVIDER_SPECS.values()}
        or parsed.scheme != "https"
        or parsed.hostname not in {"www.recall.caa.go.jp", "safe-lite.nite.go.jp"}
        or parsed.netloc != parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)
    return parsed.path, parsed


@final
class BoundedProductSafetyHttpsTransport:
    """Pinned-DNS HTTPS POST transport for one prevalidated request."""

    __slots__ = ("_clock", "_connection_factory", "_environment", "_request")

    def __init__(
        self,
        request: ProductSafetyQueryRequest,
        *,
        connection_factory: ProductSafetyHttpsConnectionFactory | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if type(request) is not ProductSafetyQueryRequest or not callable(clock):
            _fail()
        _validate_closed_request_shape(request)
        self._request = request
        self._connection_factory = _require_connection_factory(
            connection_factory or _SystemConnectionFactory()
        )
        self._clock = clock
        self._environment = environment

    def post(self, request: ProductSafetyQueryRequest) -> ProductSafetyHttpResponse:
        if type(request) is not ProductSafetyQueryRequest or request != self._request:
            _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID)
        _validate_closed_request_shape(request)
        require_clean_network_environment(self._environment)
        path, parsed = _request_path(request.endpoint)
        try:
            context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except (OSError, ssl.SSLError, ValueError):
            _fail(ProductSafetyQueryCaptureFailureCode.TLS_CONTEXT_INVALID)
        connection: ProductSafetyHttpsConnection | None = None
        request_started = False
        try:
            connection = self._connection_factory.open(
                host=cast(str, parsed.hostname),
                port=443,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
            connection.connect()
            connection.set_read_timeout(READ_TIMEOUT_SECONDS)
            request_started = True
            connection.request(
                request.method,
                path,
                request.body,
                dict(request.headers),
            )
            response = connection.getresponse()
            headers = _response_headers(response.getheaders())
            if (
                type(response.status) is not int
                or response.status != 200
                or "location" in headers
                or headers.get("content-encoding") not in {None, "identity"}
            ):
                _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
            body = _bounded_response_body(response, headers)
            return ProductSafetyHttpResponse(
                status=response.status,
                headers=tuple(
                    (name, value)
                    for name, value in headers.items()
                    if name in {"content-type", "content-length"}
                ),
                body=body,
                retrieved_at_utc=_clock_value(self._clock),
            )
        except ProductSafetyQueryCaptureFailure:
            raise
        except socket.gaierror:
            _fail(ProductSafetyQueryCaptureFailureCode.DNS_FAILED)
        except ssl.SSLError:
            _fail(ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED)
        except (TimeoutError, socket.timeout, http.client.HTTPException, OSError):
            _fail(
                ProductSafetyQueryCaptureFailureCode.REQUEST_AMBIGUOUS
                if request_started
                else ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED
            )
        except BaseException:
            _fail(
                ProductSafetyQueryCaptureFailureCode.REQUEST_AMBIGUOUS
                if request_started
                else ProductSafetyQueryCaptureFailureCode.CONNECTION_FAILED
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass


def _validated_retrieved_at(value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.microsecond != 0
        or parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    return value


def _validated_response(
    request: ProductSafetyQueryRequest, response: ProductSafetyHttpResponse
) -> tuple[str, bytes, str]:
    if type(response) is not ProductSafetyHttpResponse or response.status != 200:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    if type(response.body) is not bytes or not 1 <= len(response.body) <= MAX_RESPONSE_BYTES:
        _fail(
            ProductSafetyQueryCaptureFailureCode.RESPONSE_TOO_LARGE
            if type(response.body) is bytes and len(response.body) > MAX_RESPONSE_BYTES
            else ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID
        )
    headers = _response_headers(list(response.headers))
    if (
        "location" in headers
        or headers.get("content-encoding") not in {None, "identity"}
        or "transfer-encoding" in headers
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    value = headers.get("content-type")
    match = None if value is None else _MEDIA_TYPE_RE.fullmatch(value)
    if match is None or match.group(1).casefold() != _PROVIDER_SPECS[
        (request.provider, request.scope)
    ].response_media_type:
        _fail(ProductSafetyQueryCaptureFailureCode.CONTENT_TYPE_INVALID)
    charset = match.group(2)
    if charset is not None and charset.casefold().replace("_", "-") != "utf-8":
        _fail(ProductSafetyQueryCaptureFailureCode.CONTENT_TYPE_INVALID)
    raw_length = headers.get("content-length")
    if (
        raw_length is not None
        and (
            _CONTENT_LENGTH_RE.fullmatch(raw_length) is None
            or int(raw_length) != len(response.body)
        )
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    return cast(str, value), response.body, _validated_retrieved_at(
        response.retrieved_at_utc
    )


@dataclass(frozen=True, slots=True)
class ProductSafetyQueryObservation:
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]
    parser_version: str


class _CaaHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.query_values: list[str] = []
        self.count_texts: list[str] = []
        self.notice_ids: list[str] = []
        self._count_depth = 0
        self._count_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        lowered = tag.casefold()
        if (
            lowered == "input"
            and values.get("id") == "suggest"
            and values.get("name") == "search"
        ):
            self.query_values.append(values.get("value", ""))
        if lowered == "p" and self._count_depth == 0:
            self._count_depth = 1
            self._count_parts = []
        elif self._count_depth:
            self._count_depth += 1
        if lowered == "a":
            href = values.get("href", "")
            match = re.search(r"(?:\?|&)rcl=([0-9]{1,32})(?:&|\Z)", href)
            if match is not None:
                self.notice_ids.append(match.group(1))

    def handle_endtag(self, tag: str) -> None:
        if self._count_depth:
            self._count_depth -= 1
            if self._count_depth == 0 and tag.casefold() == "p":
                value = "".join(self._count_parts).strip()
                if re.fullmatch(r"[0-9]+件中(?:\s+|　).+", value):
                    self.count_texts.append(value)

    def handle_data(self, data: str) -> None:
        if self._count_depth:
            self._count_parts.append(data)


class _NiteHtmlParser(HTMLParser):
    def __init__(self, *, scope: Scope) -> None:
        super().__init__(convert_charrefs=True)
        self.scope = scope
        self.query_echoes: list[str] = []
        self.count_values: list[str] = []
        self.notice_ids: list[str] = []
        self._query_depth = 0
        self._query_parts: list[str] = []
        self._count_depth = 0
        self._count_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        classes = frozenset(values.get("class", "").split())
        lowered = tag.casefold()
        if "searchExpression-display" in classes and self._query_depth == 0:
            self._query_depth = 1
            self._query_parts = []
        elif self._query_depth:
            self._query_depth += 1
        expected_count_id = "recall-count" if self.scope == "RECALL" else "jiko-count"
        if lowered == "span" and values.get("id") == expected_count_id:
            if self._count_depth:
                _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
            self._count_depth = 1
            self._count_parts = []
        elif self._count_depth:
            self._count_depth += 1
        if lowered == "a":
            href = values.get("href", "")
            path = "recall" if self.scope == "RECALL" else "jiko"
            match = re.search(rf"(?:\./|/){path}/detail/([A-Za-z0-9._-]+)", href)
            if match is not None:
                self.notice_ids.append(match.group(1))

    def handle_endtag(self, tag: str) -> None:
        if self._query_depth:
            self._query_depth -= 1
            if self._query_depth == 0:
                self.query_echoes.append("".join(self._query_parts).strip())
        if self._count_depth:
            self._count_depth -= 1
            if self._count_depth == 0 and tag.casefold() == "span":
                self.count_values.append("".join(self._count_parts).strip())

    def handle_data(self, data: str) -> None:
        if self._query_depth:
            self._query_parts.append(data)
        if self._count_depth:
            self._count_parts.append(data)


def _observation(
    *, count: int, notice_ids: Sequence[str], parser_version: str
) -> ProductSafetyQueryObservation:
    normalized_ids = tuple(sorted(set(notice_ids)))
    if (
        count < 0
        or any(_NOTICE_ID_RE.fullmatch(value) is None for value in normalized_ids)
        or len(normalized_ids) != len(notice_ids)
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    if count == 0 and not normalized_ids:
        result: ObservationResult = "NONE_FOUND"
    elif count > 0 and count == len(normalized_ids):
        result = "MATCH"
    else:
        result = "AMBIGUOUS"
    return ProductSafetyQueryObservation(
        result=result,
        result_count=count,
        notice_ids=normalized_ids,
        parser_version=parser_version,
    )


def _parse_caa(
    body: bytes, *, query: str, parser_version: str
) -> ProductSafetyQueryObservation:
    try:
        decoded = body.decode("utf-8", errors="strict")
        parser = _CaaHtmlParser()
        parser.feed(decoded)
        parser.close()
    except (UnicodeError, ValueError, TypeError):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    if parser.query_values != [query]:
        _fail(ProductSafetyQueryCaptureFailureCode.QUERY_ECHO_MISMATCH)
    if len(parser.count_texts) not in {1, 2} or len(set(parser.count_texts)) != 1:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    match = re.fullmatch(r"([0-9]+)件中(?:\s+|　).+", parser.count_texts[0])
    if match is None:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    return _observation(
        count=int(match.group(1)),
        notice_ids=parser.notice_ids,
        parser_version=parser_version,
    )


def _parse_nite(
    body: bytes, *, query: str, scope: Scope, parser_version: str
) -> ProductSafetyQueryObservation:
    document = _strict_json(
        body,
        maximum=MAX_RESPONSE_BYTES,
        failure_code=ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED,
    )
    if type(document) is not dict or set(cast(dict[object, object], document)) != {
        "htmlContent"
    }:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    html_content = cast(dict[str, object], document).get("htmlContent")
    if type(html_content) is not str or not 1 <= len(html_content) <= MAX_RESPONSE_BYTES:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    try:
        parser = _NiteHtmlParser(scope=scope)
        parser.feed(html_content)
        parser.close()
    except (ValueError, TypeError):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    expected_echo = f"フリーワード検索：{query}"
    if parser.query_echoes != [expected_echo]:
        _fail(ProductSafetyQueryCaptureFailureCode.QUERY_ECHO_MISMATCH)
    if len(parser.count_values) != 1 or not parser.count_values[0].isdigit():
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    return _observation(
        count=int(parser.count_values[0]),
        notice_ids=parser.notice_ids,
        parser_version=parser_version,
    )


def parse_product_safety_query_response(
    request: ProductSafetyQueryRequest,
    response: ProductSafetyHttpResponse,
) -> tuple[ProductSafetyQueryObservation, str, str]:
    """Validate content and derive NONE_FOUND, MATCH, or AMBIGUOUS."""

    content_type, body, retrieved_at = _validated_response(request, response)
    if request.provider == "CAA":
        observation = _parse_caa(
            body, query=request.query, parser_version=request.parser_version
        )
    else:
        observation = _parse_nite(
            body,
            query=request.query,
            scope=request.scope,
            parser_version=request.parser_version,
        )
    spec = _PROVIDER_SPECS[(request.provider, request.scope)]
    if (
        observation.result_count > spec.maximum_results_per_response
        and observation.result != "AMBIGUOUS"
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED)
    return observation, content_type, retrieved_at


def _safe_private_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            try:
                path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
            except FileExistsError:
                pass
        observed = path.lstat()
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)


def _capture_directory(repository_root: Path, product_id: str) -> Path:
    root = _absolute_repository_root(repository_root)
    secrets = root / OWNER_CAPTURE_RELATIVE_PATH.parts[0]
    captures = root / OWNER_CAPTURE_RELATIVE_PATH
    product = captures / product_id
    _safe_private_directory(secrets, create=True)
    _safe_private_directory(captures, create=True)
    _safe_private_directory(product, create=True)
    return product


def _read_private(path: Path, *, maximum: int) -> bytes | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
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
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _atomic_replace_private(directory: Path, name: str, payload: bytes) -> None:
    if (
        type(name) is not str
        or "/" in name
        or name in {"", ".", ".."}
        or type(payload) is not bytes
        or not 1 <= len(payload) <= MAX_RESPONSE_BYTES
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    target = directory / name
    existing = _read_private(target, maximum=MAX_RESPONSE_BYTES)
    if existing == payload:
        return
    descriptor = -1
    directory_fd = -1
    temporary = f".{name}.{os.getpid()}.{os.urandom(16).hex()}.tmp"
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
                _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
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
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        directory_fd = os.open(
            directory,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except ProductSafetyQueryCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
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
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)


def _capture_hash_material(document: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value for key, value in document.items() if key != "capture_sha256"
    }


@dataclass(frozen=True, slots=True)
class ProductSafetyQueryCaptureResult:
    product_id: str
    provider: Provider
    scope: Scope
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]
    retrieved_at_utc: str
    request_material_sha256: str
    response_raw_sha256: str
    capture_sha256: str
    metadata_path: Path
    raw_response_path: Path
    credentials_used: bool = False
    publication_authority: bool = False
    production_write: bool = False


def _capture_document(
    *,
    request: ProductSafetyQueryRequest,
    response: ProductSafetyHttpResponse,
    observation: ProductSafetyQueryObservation,
    content_type: str,
    retrieved_at_utc: str,
    raw_name: str,
) -> dict[str, object]:
    material: dict[str, object] = {
        "schema": CAPTURE_SCHEMA,
        "version": CAPTURE_VERSION,
        "publication_authority": PUBLICATION_AUTHORITY,
        "credentials_used": False,
        "production_write": False,
        "product_id": request.product_id,
        "exact_model_tokens": list(request.exact_model_tokens),
        "query_model_token": request.query,
        "provider": request.provider,
        "scope": request.scope,
        "method": request.method,
        "endpoint": request.endpoint,
        "request_material_sha256": request.request_material_sha256,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
        "response_status": response.status,
        "response_content_type": content_type,
        "response_raw_file": raw_name,
        "response_raw_size_bytes": len(response.body),
        "response_raw_sha256": _sha256(response.body),
        "retrieved_at_utc": retrieved_at_utc,
        "parser_version": observation.parser_version,
        "result": observation.result,
        "result_count": observation.result_count,
        "notice_ids": list(observation.notice_ids),
        "coverage_caveat": COVERAGE_CAVEAT,
        "manufacturer_receipt_generated": False,
    }
    return {
        **material,
        "capture_sha256": _sha256(canonical_json_bytes(material)),
    }


def _persist_capture(
    repository_root: Path,
    *,
    request: ProductSafetyQueryRequest,
    response: ProductSafetyHttpResponse,
    observation: ProductSafetyQueryObservation,
    content_type: str,
    retrieved_at_utc: str,
) -> ProductSafetyQueryCaptureResult:
    directory = _capture_directory(repository_root, request.product_id)
    basename = f"{request.provider.lower()}-{request.scope.lower()}"
    raw_name = f"{basename}.response"
    metadata_name = f"{basename}.capture.v1.json"
    lock_path = directory.parent / CAPTURE_LOCK_FILE
    lock_descriptor = -1
    try:
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        os.fchmod(lock_descriptor, PRIVATE_FILE_MODE)
        lock_stat = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or stat.S_IMODE(lock_stat.st_mode) != PRIVATE_FILE_MODE
            or lock_stat.st_nlink != 1
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        document = _capture_document(
            request=request,
            response=response,
            observation=observation,
            content_type=content_type,
            retrieved_at_utc=retrieved_at_utc,
            raw_name=raw_name,
        )
        metadata = canonical_json_bytes(document) + b"\n"
        _atomic_replace_private(directory, raw_name, response.body)
        _atomic_replace_private(directory, metadata_name, metadata)
        return ProductSafetyQueryCaptureResult(
            product_id=request.product_id,
            provider=request.provider,
            scope=request.scope,
            result=observation.result,
            result_count=observation.result_count,
            notice_ids=observation.notice_ids,
            retrieved_at_utc=retrieved_at_utc,
            request_material_sha256=request.request_material_sha256,
            response_raw_sha256=_sha256(response.body),
            capture_sha256=cast(str, document["capture_sha256"]),
            metadata_path=directory / metadata_name,
            raw_response_path=directory / raw_name,
        )
    except ProductSafetyQueryCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    finally:
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)


def describe_product_safety_query(
    repository_root: Path,
    *,
    product_id: str,
    provider: str,
    scope: str,
) -> dict[str, object]:
    """Return non-secret dry-run metadata without network or filesystem writes."""

    plan = load_product_safety_query_plan(repository_root)
    request = build_product_safety_query_request(
        plan, product_id=product_id, provider=provider, scope=scope
    )
    return {
        "status": "DRY_RUN",
        "publication_authority": PUBLICATION_AUTHORITY,
        "credentials_used": False,
        "production_write": False,
        "product_id": request.product_id,
        "provider": request.provider,
        "scope": request.scope,
        "method": request.method,
        "endpoint": request.endpoint,
        "parser_version": request.parser_version,
        "request_material_sha256": request.request_material_sha256,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
    }


def capture_product_safety_query(
    repository_root: Path,
    *,
    product_id: str,
    provider: str,
    scope: str,
    transport: ProductSafetyQueryTransport | None = None,
    connection_factory: ProductSafetyHttpsConnectionFactory | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    environment: Mapping[str, str] | None = None,
) -> ProductSafetyQueryCaptureResult:
    """Capture one exact official query and persist owner-private raw evidence."""

    if transport is not None and connection_factory is not None:
        _fail()
    plan = load_product_safety_query_plan(repository_root)
    request = build_product_safety_query_request(
        plan, product_id=product_id, provider=provider, scope=scope
    )
    selected_transport: ProductSafetyQueryTransport
    if transport is None:
        selected_transport = BoundedProductSafetyHttpsTransport(
            request,
            connection_factory=connection_factory,
            clock=clock,
            environment=environment,
        )
    else:
        selected_transport = _require_query_transport(transport)
    try:
        response = selected_transport.post(request)
    except ProductSafetyQueryCaptureFailure:
        raise
    except BaseException:
        _fail(ProductSafetyQueryCaptureFailureCode.REQUEST_AMBIGUOUS)
    observation, content_type, retrieved_at = parse_product_safety_query_response(
        request, response
    )
    return _persist_capture(
        repository_root,
        request=request,
        response=response,
        observation=observation,
        content_type=content_type,
        retrieved_at_utc=retrieved_at,
    )


def validate_product_safety_query_capture_document(
    document: Mapping[str, object], raw_response: bytes
) -> None:
    """Validate a persisted pair without granting it publication authority."""

    if type(document) is not dict or type(raw_response) is not bytes:
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)
    validated_document = cast(dict[str, object], document)
    expected_keys = {
        "schema",
        "version",
        "publication_authority",
        "credentials_used",
        "production_write",
        "product_id",
        "exact_model_tokens",
        "query_model_token",
        "provider",
        "scope",
        "method",
        "endpoint",
        "request_material_sha256",
        "plan_sha256",
        "portfolio_sha256",
        "response_status",
        "response_content_type",
        "response_raw_file",
        "response_raw_size_bytes",
        "response_raw_sha256",
        "retrieved_at_utc",
        "parser_version",
        "result",
        "result_count",
        "notice_ids",
        "coverage_caveat",
        "manufacturer_receipt_generated",
        "capture_sha256",
    }
    capture_sha = validated_document.get("capture_sha256")
    if (
        set(validated_document) != expected_keys
        or validated_document.get("schema") != CAPTURE_SCHEMA
        or validated_document.get("version") != CAPTURE_VERSION
        or validated_document.get("publication_authority") != PUBLICATION_AUTHORITY
        or validated_document.get("credentials_used") is not False
        or validated_document.get("production_write") is not False
        or validated_document.get("manufacturer_receipt_generated") is not False
        or validated_document.get("coverage_caveat") != COVERAGE_CAVEAT
        or validated_document.get("response_raw_size_bytes") != len(raw_response)
        or validated_document.get("response_raw_sha256") != _sha256(raw_response)
        or type(capture_sha) is not str
        or _SHA256_RE.fullmatch(capture_sha) is None
        or capture_sha
        != _sha256(
            canonical_json_bytes(_capture_hash_material(validated_document))
        )
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.RESPONSE_INVALID)


AdministrativeCaptureProductStatus = Literal[
    "VERIFIED_NONE_FOUND",
    "BLOCKED_MATCH_FOUND",
    "BLOCKED_AMBIGUOUS_RESULT",
    "BLOCKED_STALE_CAPTURE",
]


@dataclass(frozen=True, slots=True)
class ProductSafetyAdministrativeCaptureEvidence:
    """One replayed administrative capture, without its private path or body."""

    product_id: str
    provider: Provider
    scope: Scope
    retrieved_at: datetime
    result: ObservationResult
    result_count: int
    notice_ids: tuple[str, ...]
    request_material_sha256: str
    response_raw_sha256: str
    capture_sha256: str


@dataclass(frozen=True, slots=True)
class ProductSafetyAdministrativeProductEvidence:
    """Derived status for the required three-query set of one product."""

    product_id: str
    exact_model_tokens: tuple[str, ...]
    status: AdministrativeCaptureProductStatus
    captures: tuple[ProductSafetyAdministrativeCaptureEvidence, ...]
    matched_notice_ids: tuple[str, ...]
    stale_provider_scopes: tuple[ProviderScope, ...]


@dataclass(frozen=True, slots=True)
class ProductSafetyAdministrativeEvidenceSet:
    """Replay-verified exact 31 x 3 capture bundle.

    The digest binds only safe canonical evidence identifiers.  Absolute private
    paths, raw response material, and query response bodies are deliberately not
    exposed by this object.
    """

    schema: str
    version: str
    plan_sha256: str
    portfolio_sha256: str
    capture_count: int
    bundle_sha256: str
    evaluated_at: datetime
    products: tuple[ProductSafetyAdministrativeProductEvidence, ...]
    complete: bool


def _require_existing_private_directory(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING)
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    _safe_private_directory(path, create=False)


def _private_directory_entries(path: Path) -> dict[str, os.DirEntry[str]]:
    try:
        with os.scandir(path) as iterator:
            rows = list(iterator)
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    if any(
        type(row.name) is not str
        or row.name in {"", ".", ".."}
        or "/" in row.name
        or "\x00" in row.name
        for row in rows
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    names = {row.name: row for row in rows}
    if len(names) != len(rows):
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    return names


def _evidence_evaluated_at(now: datetime | None) -> datetime:
    value = datetime.now(UTC) if now is None else now
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.INVALID_ARGUMENT)
    return value.astimezone(UTC)


def _parse_capture_time(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    return parsed


def _replay_private_capture(
    *,
    directory: Path,
    plan: ProductSafetyQueryPlan,
    product: ProductQueryIdentity,
    spec: _ProviderSpec,
    evaluated_at: datetime,
) -> ProductSafetyAdministrativeCaptureEvidence:
    request = build_product_safety_query_request(
        plan,
        product_id=product.product_id,
        provider=spec.provider,
        scope=spec.scope,
    )
    basename = f"{spec.provider.lower()}-{spec.scope.lower()}"
    raw_name = f"{basename}.response"
    metadata_name = f"{basename}.capture.v1.json"
    metadata_raw = _read_private(
        directory / metadata_name,
        maximum=MAX_CAPTURE_METADATA_BYTES,
    )
    raw_response = _read_private(
        directory / raw_name,
        maximum=MAX_RESPONSE_BYTES,
    )
    if metadata_raw is None or raw_response is None:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING)
    parsed_document = _strict_json(
        metadata_raw,
        maximum=MAX_CAPTURE_METADATA_BYTES,
        failure_code=ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID,
    )
    if type(parsed_document) is not dict:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    document = cast(dict[str, object], parsed_document)
    if metadata_raw != canonical_json_bytes(document) + b"\n":
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    try:
        validate_product_safety_query_capture_document(document, raw_response)
    except ProductSafetyQueryCaptureFailure:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)

    expected = {
        "product_id": request.product_id,
        "exact_model_tokens": list(request.exact_model_tokens),
        "query_model_token": request.query,
        "provider": request.provider,
        "scope": request.scope,
        "method": request.method,
        "endpoint": request.endpoint,
        "request_material_sha256": request.request_material_sha256,
        "plan_sha256": request.plan_sha256,
        "portfolio_sha256": request.portfolio_sha256,
        "response_status": 200,
        "response_raw_file": raw_name,
        "parser_version": request.parser_version,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    content_type = document.get("response_content_type")
    retrieved_at_utc = document.get("retrieved_at_utc")
    if type(content_type) is not str or type(retrieved_at_utc) is not str:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    response = ProductSafetyHttpResponse(
        status=200,
        headers=(
            ("Content-Type", content_type),
            ("Content-Length", str(len(raw_response))),
        ),
        body=raw_response,
        retrieved_at_utc=retrieved_at_utc,
    )
    try:
        observation, replayed_content_type, replayed_at = (
            parse_product_safety_query_response(request, response)
        )
    except ProductSafetyQueryCaptureFailure:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    if (
        replayed_content_type != content_type
        or replayed_at != retrieved_at_utc
        or type(document.get("result_count")) is not int
        or document.get("result") != observation.result
        or document.get("result_count") != observation.result_count
        or document.get("notice_ids") != list(observation.notice_ids)
    ):
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    retrieved_at = _parse_capture_time(retrieved_at_utc)
    if retrieved_at - evaluated_at > MAX_CAPTURE_FUTURE_SKEW:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    capture_sha256 = document.get("capture_sha256")
    response_sha256 = document.get("response_raw_sha256")
    if type(capture_sha256) is not str or type(response_sha256) is not str:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    return ProductSafetyAdministrativeCaptureEvidence(
        product_id=product.product_id,
        provider=spec.provider,
        scope=spec.scope,
        retrieved_at=retrieved_at,
        result=observation.result,
        result_count=observation.result_count,
        notice_ids=observation.notice_ids,
        request_material_sha256=request.request_material_sha256,
        response_raw_sha256=response_sha256,
        capture_sha256=capture_sha256,
    )


def _capture_bundle_material(
    plan: ProductSafetyQueryPlan,
    captures: Sequence[ProductSafetyAdministrativeCaptureEvidence],
) -> dict[str, object]:
    return {
        "schema": CAPTURE_BUNDLE_SCHEMA,
        "version": CAPTURE_BUNDLE_VERSION,
        "plan_sha256": plan.plan_sha256,
        "portfolio_sha256": plan.portfolio_sha256,
        "expected_product_count": len(plan.products),
        "expected_provider_scope_count": len(plan.provider_specs),
        "capture_count": len(captures),
        "captures": [
            {
                "product_id": row.product_id,
                "provider": row.provider,
                "scope": row.scope,
                "retrieved_at_utc": row.retrieved_at.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "result": row.result,
                "result_count": row.result_count,
                "notice_ids": list(row.notice_ids),
                "request_material_sha256": row.request_material_sha256,
                "response_raw_sha256": row.response_raw_sha256,
                "capture_sha256": row.capture_sha256,
            }
            for row in captures
        ],
    }


def verify_product_safety_query_capture_set(
    repository_root: Path,
    *,
    now: datetime | None = None,
) -> ProductSafetyAdministrativeEvidenceSet:
    """Read and replay the exact fixed owner-private administrative evidence set.

    No capture root, URL, request, or parser is caller-selectable.  The only
    filesystem location is derived from ``repository_root`` and the tracked
    query plan.  Verification performs no network requests and no writes.
    """

    root = _absolute_repository_root(repository_root)
    evaluated_at = _evidence_evaluated_at(now)
    plan = load_product_safety_query_plan(root)
    secrets = root / OWNER_CAPTURE_RELATIVE_PATH.parts[0]
    capture_root = root / OWNER_CAPTURE_RELATIVE_PATH
    # Treat a wholly absent fixed capture root as missing evidence even when a
    # repository happens to have a non-private ``.secrets`` staging directory.
    # Once evidence exists, every ancestor in this private chain is mandatory.
    try:
        capture_root.lstat()
    except FileNotFoundError:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING)
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    _require_existing_private_directory(secrets)
    _require_existing_private_directory(capture_root)
    lock_path = capture_root / CAPTURE_LOCK_FILE
    lock_descriptor = -1
    try:
        try:
            lock_descriptor = os.open(
                lock_path,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        except FileNotFoundError:
            _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING)
        except OSError:
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        lock_stat = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or stat.S_IMODE(lock_stat.st_mode) != PRIVATE_FILE_MODE
            or lock_stat.st_nlink != 1
        ):
            _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
        fcntl.flock(lock_descriptor, fcntl.LOCK_SH)

        expected_root_names = {
            CAPTURE_LOCK_FILE,
            *(product.product_id for product in plan.products),
        }
        root_entries = _private_directory_entries(capture_root)
        if set(root_entries) != expected_root_names:
            missing = expected_root_names - set(root_entries)
            _fail(
                ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING
                if missing
                else ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID
            )
        captures: list[ProductSafetyAdministrativeCaptureEvidence] = []
        expected_product_files = {
            f"{spec.provider.lower()}-{spec.scope.lower()}.response"
            for spec in plan.provider_specs
        } | {
            f"{spec.provider.lower()}-{spec.scope.lower()}.capture.v1.json"
            for spec in plan.provider_specs
        }
        for product in plan.products:
            entry = root_entries[product.product_id]
            if not entry.is_dir(follow_symlinks=False):
                _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
            product_directory = capture_root / product.product_id
            _require_existing_private_directory(product_directory)
            product_entries = _private_directory_entries(product_directory)
            if set(product_entries) != expected_product_files:
                missing = expected_product_files - set(product_entries)
                _fail(
                    ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING
                    if missing
                    else ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID
                )
            for row in product_entries.values():
                if not row.is_file(follow_symlinks=False):
                    _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
            for spec in plan.provider_specs:
                captures.append(
                    _replay_private_capture(
                        directory=product_directory,
                        plan=plan,
                        product=product,
                        spec=spec,
                        evaluated_at=evaluated_at,
                    )
                )
    except ProductSafetyQueryCaptureFailure:
        raise
    except OSError:
        _fail(ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE)
    finally:
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)

    expected_count = len(plan.products) * len(plan.provider_specs)
    if len(captures) != expected_count:
        _fail(ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID)
    products: list[ProductSafetyAdministrativeProductEvidence] = []
    for product in plan.products:
        product_captures = tuple(
            row for row in captures if row.product_id == product.product_id
        )
        matched_notice_ids = tuple(
            dict.fromkeys(
                notice_id
                for row in product_captures
                for notice_id in row.notice_ids
            )
        )
        stale: tuple[ProviderScope, ...] = tuple(
            (row.provider, row.scope)
            for row in product_captures
            if evaluated_at - row.retrieved_at > MAX_CAPTURE_AGE
        )
        if any(row.result == "MATCH" for row in product_captures):
            status: AdministrativeCaptureProductStatus = "BLOCKED_MATCH_FOUND"
        elif any(row.result == "AMBIGUOUS" for row in product_captures):
            status = "BLOCKED_AMBIGUOUS_RESULT"
        elif stale:
            status = "BLOCKED_STALE_CAPTURE"
        else:
            status = "VERIFIED_NONE_FOUND"
        products.append(
            ProductSafetyAdministrativeProductEvidence(
                product_id=product.product_id,
                exact_model_tokens=product.exact_model_tokens,
                status=status,
                captures=product_captures,
                matched_notice_ids=matched_notice_ids,
                stale_provider_scopes=stale,
            )
        )
    bundle_sha256 = _sha256(
        canonical_json_bytes(_capture_bundle_material(plan, captures))
    )
    return ProductSafetyAdministrativeEvidenceSet(
        schema=CAPTURE_BUNDLE_SCHEMA,
        version=CAPTURE_BUNDLE_VERSION,
        plan_sha256=plan.plan_sha256,
        portfolio_sha256=plan.portfolio_sha256,
        capture_count=len(captures),
        bundle_sha256=bundle_sha256,
        evaluated_at=evaluated_at,
        products=tuple(products),
        complete=all(row.status == "VERIFIED_NONE_FOUND" for row in products),
    )
