"""Closed-contract tests for administrative product-safety query capture."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import html
import inspect
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
from typing import Callable, cast

import pytest

import raos.application.editorial.product_safety_query_capture as capture
from raos.application.editorial.product_safety_query_capture import (
    MAX_RESPONSE_BYTES,
    OWNER_CAPTURE_RELATIVE_PATH,
    PORTFOLIO_RELATIVE_PATH,
    QUERY_PLAN_RELATIVE_PATH,
    BoundedProductSafetyHttpsTransport,
    ProductSafetyHttpResponse,
    ProductSafetyQueryCaptureFailure,
    ProductSafetyQueryCaptureFailureCode,
    ProductSafetyQueryRequest,
    build_product_safety_query_request,
    capture_product_safety_query,
    describe_product_safety_query,
    load_product_safety_query_plan,
    parse_product_safety_query_response,
    require_clean_network_environment,
    validate_product_safety_query_capture_document,
    validate_product_safety_query_request,
    verify_product_safety_query_capture_set,
)

import scripts.st1704_product_safety_query_capture as capture_cli


ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 9, 1, 1, 2, 3, tzinfo=UTC)


def _copy_contract(repository: Path) -> Path:
    for relative in (QUERY_PLAN_RELATIVE_PATH, PORTFOLIO_RELATIVE_PATH):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return repository


def _first_request(
    repository: Path = ROOT, *, provider: str = "CAA", scope: str = "RECALL"
) -> ProductSafetyQueryRequest:
    plan = load_product_safety_query_plan(repository)
    return build_product_safety_query_request(
        plan,
        product_id=plan.products[0].product_id,
        provider=provider,
        scope=scope,
    )


def _response(
    body: bytes,
    *,
    content_type: str,
    status: int = 200,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> ProductSafetyHttpResponse:
    return ProductSafetyHttpResponse(
        status=status,
        headers=(
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            *extra_headers,
        ),
        body=body,
        retrieved_at_utc="2026-09-01T01:02:03Z",
    )


def _caa_body(
    query: str, *, count: int, notice_ids: tuple[str, ...] = ()
) -> bytes:
    links = "".join(
        f'<a href="/result/detail.php?rcl={value}&amp;screenkbn=01">notice</a>'
        for value in notice_ids
    )
    count_text = f"{count}件中　{('0件を表示中' if count == 0 else f'1-{count}') }"
    return (
        "<!doctype html><html><body>"
        f'<input id="suggest" name="search" value="{html.escape(query)}">'
        f"<p>{count_text}</p>{links}<p>{count_text}</p>"
        "</body></html>"
    ).encode()


def _nite_body(
    query: str,
    *,
    scope: str,
    count: int,
    notice_ids: tuple[str, ...] = (),
) -> bytes:
    target = "recall" if scope == "RECALL" else "jiko"
    count_id = "recall-count" if scope == "RECALL" else "jiko-count"
    links = "".join(
        f'<a href="./{target}/detail/{value}?searchExp=x">notice</a>'
        for value in notice_ids
    )
    inner = (
        f'<div class="searchExpression-display"> フリーワード検索：{html.escape(query)}</div>'
        f'<p>全 <span id="{count_id}">{count}</span> 件がヒットしました。</p>'
        f"{links}"
    )
    return json.dumps(
        {"htmlContent": inner},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


class _FakeTransport:
    def __init__(self, response: ProductSafetyHttpResponse) -> None:
        self.response = response
        self.requests: list[ProductSafetyQueryRequest] = []

    def post(self, request: ProductSafetyQueryRequest) -> ProductSafetyHttpResponse:
        self.requests.append(request)
        return self.response


def _capture_exact_clear_set(repository: Path) -> None:
    plan = load_product_safety_query_plan(repository)
    for product in plan.products:
        for spec in plan.provider_specs:
            request = build_product_safety_query_request(
                plan,
                product_id=product.product_id,
                provider=spec.provider,
                scope=spec.scope,
            )
            if spec.provider == "CAA":
                body = _caa_body(request.query, count=0)
                content_type = "text/html; charset=UTF-8"
            else:
                body = _nite_body(request.query, scope=spec.scope, count=0)
                content_type = "application/json"
            capture_product_safety_query(
                repository,
                product_id=product.product_id,
                provider=spec.provider,
                scope=spec.scope,
                transport=_FakeTransport(
                    _response(body, content_type=content_type)
                ),
            )


@pytest.fixture(scope="module")
def complete_capture_repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repository = _copy_contract(tmp_path_factory.mktemp("safety-capture-set"))
    _capture_exact_clear_set(repository)
    return repository


def _copy_complete_capture_repository(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    return destination


def _rewrite_metadata(
    path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    material = {
        key: value for key, value in document.items() if key != "capture_sha256"
    }
    document["capture_sha256"] = hashlib.sha256(
        capture.canonical_json_bytes(material)
    ).hexdigest()
    path.write_bytes(capture.canonical_json_bytes(document) + b"\n")
    os.chmod(path, 0o600)


def test_plan_covers_exact_current_selected_inventory_and_three_fixed_queries() -> None:
    plan = load_product_safety_query_plan(ROOT)
    portfolio = json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text())
    selected = {
        product_id
        for article in portfolio["articles"]
        for product_id in article["product_ids"]
    }
    assert {product.product_id for product in plan.products} == selected
    assert len(plan.products) == len(portfolio["products"])
    assert {
        (spec.provider, spec.scope, spec.endpoint)
        for spec in plan.provider_specs
    } == {
        (
            "CAA",
            "RECALL",
            "https://www.recall.caa.go.jp/result/index.php",
        ),
        (
            "NITE",
            "RECALL",
            "https://safe-lite.nite.go.jp/recall/search/index",
        ),
        (
            "NITE",
            "ACCIDENT",
            "https://safe-lite.nite.go.jp/jiko/search/index",
        ),
    }


@pytest.mark.parametrize(
    ("provider", "scope", "expected_fields"),
    (
        ("CAA", "RECALL", ("search", "screenkbn", "category")),
        (
            "NITE",
            "RECALL",
            ("searchWord", "isFreewordSearch", "pagesize"),
        ),
        (
            "NITE",
            "ACCIDENT",
            ("searchWord", "isMajor", "isFreewordSearch", "pagesize"),
        ),
    ),
)
def test_request_is_exact_post_with_no_caller_selected_material(
    provider: str, scope: str, expected_fields: tuple[str, ...]
) -> None:
    request = _first_request(provider=provider, scope=scope)
    assert request.method == "POST"
    assert tuple(name for name, _value in request.form_fields) == expected_fields
    assert request.form_fields[0][1] == request.query
    assert request.query in request.exact_model_tokens
    assert dict(request.headers)["Content-Type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert len(request.request_material_sha256) == 64


@pytest.mark.parametrize(
    "mutation",
    (
        {"method": "GET"},
        {"endpoint": "https://example.com/result/index.php"},
        {"endpoint": "https://www.recall.caa.go.jp/other"},
        {"headers": (("Accept", "*/*"),)},
        {"form_fields": (("search", "attacker"),)},
        {"body": b"search=attacker"},
        {"query": "attacker"},
        {"request_material_sha256": "0" * 64},
    ),
)
def test_request_tamper_is_rejected(mutation: dict[str, object]) -> None:
    plan = load_product_safety_query_plan(ROOT)
    request = _first_request()
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        validate_product_safety_query_request(plan, replace(request, **mutation))
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID


def test_transport_edge_rejects_forged_request_before_network() -> None:
    request = _first_request()
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        BoundedProductSafetyHttpsTransport(
            replace(request, endpoint="https://www.recall.caa.go.jp/other"),
            environment={},
        )
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.REQUEST_INVALID


@pytest.mark.parametrize("field", ("endpoint", "method", "fixed_fields"))
def test_plan_rejects_wrong_host_path_method_or_fields(
    tmp_path: Path, field: str
) -> None:
    repository = _copy_contract(tmp_path)
    path = repository / QUERY_PLAN_RELATIVE_PATH
    document = json.loads(path.read_text())
    if field == "endpoint":
        document["provider_scopes"][0][field] = "https://example.com/"
    elif field == "method":
        document["provider_scopes"][0][field] = "GET"
    else:
        document["provider_scopes"][0][field][0]["value"] = "99"
    path.write_text(json.dumps(document, ensure_ascii=False))
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        load_product_safety_query_plan(repository)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.PLAN_INVALID


def test_plan_rejects_portfolio_identity_or_query_mismatch(tmp_path: Path) -> None:
    repository = _copy_contract(tmp_path)
    path = repository / PORTFOLIO_RELATIVE_PATH
    document = json.loads(path.read_text())
    document["products"][0]["official_models"] = ["tampered"]
    path.write_text(json.dumps(document, ensure_ascii=False))
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        load_product_safety_query_plan(repository)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.PLAN_INVALID


def test_plan_file_symlink_is_rejected(tmp_path: Path) -> None:
    repository = _copy_contract(tmp_path)
    path = repository / QUERY_PLAN_RELATIVE_PATH
    outside = tmp_path / "outside.json"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        load_product_safety_query_plan(repository)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.PLAN_INVALID


@pytest.mark.parametrize(
    ("count", "ids", "result"),
    (
        (0, (), "NONE_FOUND"),
        (1, ("00000012345",), "MATCH"),
        (2, ("00000012345",), "AMBIGUOUS"),
    ),
)
def test_caa_html_normalization_derives_result(
    count: int, ids: tuple[str, ...], result: str
) -> None:
    request = _first_request()
    response = _response(
        _caa_body(request.query, count=count, notice_ids=ids),
        content_type="text/html; charset=UTF-8",
    )
    observation, _content_type, _retrieved_at = (
        parse_product_safety_query_response(request, response)
    )
    assert observation.result == result
    assert observation.result_count == count
    assert observation.notice_ids == tuple(sorted(ids))


@pytest.mark.parametrize("scope", ("RECALL", "ACCIDENT"))
@pytest.mark.parametrize(
    ("count", "ids", "result"),
    (
        (0, (), "NONE_FOUND"),
        (2, ("20260001", "20260002"), "MATCH"),
        (3, ("20260001", "20260002"), "AMBIGUOUS"),
    ),
)
def test_nite_json_html_normalization_derives_result(
    scope: str, count: int, ids: tuple[str, ...], result: str
) -> None:
    request = _first_request(provider="NITE", scope=scope)
    response = _response(
        _nite_body(request.query, scope=scope, count=count, notice_ids=ids),
        content_type="application/json",
    )
    observation, _content_type, _retrieved_at = (
        parse_product_safety_query_response(request, response)
    )
    assert observation.result == result
    assert observation.result_count == count
    assert observation.notice_ids == tuple(sorted(ids))


@pytest.mark.parametrize(("provider", "scope"), (("CAA", "RECALL"), ("NITE", "RECALL")))
def test_query_echo_mismatch_is_rejected(provider: str, scope: str) -> None:
    request = _first_request(provider=provider, scope=scope)
    body = (
        _caa_body("wrong", count=0)
        if provider == "CAA"
        else _nite_body("wrong", scope=scope, count=0)
    )
    response = _response(
        body,
        content_type="text/html" if provider == "CAA" else "application/json",
    )
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        parse_product_safety_query_response(request, response)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.QUERY_ECHO_MISMATCH


@pytest.mark.parametrize(
    "response",
    (
        _response(b"{}", content_type="application/json", status=302),
        _response(
            b"{}",
            content_type="application/json",
            extra_headers=(("Location", "https://example.com"),),
        ),
        _response(b"not json", content_type="application/json"),
        _response(b"{}", content_type="text/plain"),
        ProductSafetyHttpResponse(
            status=200,
            headers=(("Content-Type", "application/json"),),
            body=b"x" * (MAX_RESPONSE_BYTES + 1),
            retrieved_at_utc="2026-09-01T01:02:03Z",
        ),
    ),
)
def test_invalid_status_redirect_json_mime_or_size_fails_closed(
    response: ProductSafetyHttpResponse,
) -> None:
    request = _first_request(provider="NITE", scope="RECALL")
    with pytest.raises(ProductSafetyQueryCaptureFailure):
        parse_product_safety_query_response(request, response)


def test_duplicate_json_key_is_not_parseable_zero_result() -> None:
    request = _first_request(provider="NITE", scope="RECALL")
    response = _response(
        b'{"htmlContent":"x","htmlContent":"y"}',
        content_type="application/json",
    )
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        parse_product_safety_query_response(request, response)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.RESPONSE_PARSE_FAILED


def test_capture_writes_only_private_atomic_pair_and_validates_hashes(
    tmp_path: Path,
) -> None:
    repository = _copy_contract(tmp_path)
    request = _first_request(repository, provider="NITE", scope="ACCIDENT")
    body = _nite_body(request.query, scope="ACCIDENT", count=0)
    transport = _FakeTransport(_response(body, content_type="application/json"))
    result = capture_product_safety_query(
        repository,
        product_id=request.product_id,
        provider="NITE",
        scope="ACCIDENT",
        transport=transport,
    )
    assert transport.requests == [request]
    assert result.result == "NONE_FOUND"
    assert result.credentials_used is False
    assert result.publication_authority is False
    assert result.production_write is False
    for directory in (
        repository / ".secrets",
        repository / OWNER_CAPTURE_RELATIVE_PATH,
        result.metadata_path.parent,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert not directory.is_symlink()
    for path in (result.metadata_path, result.raw_response_path):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_nlink == 1
        assert not path.is_symlink()
    document = json.loads(result.metadata_path.read_text())
    validate_product_safety_query_capture_document(
        document, result.raw_response_path.read_bytes()
    )


def test_store_rejects_symlink_without_touching_outside(tmp_path: Path) -> None:
    repository = _copy_contract(tmp_path)
    request = _first_request(repository)
    product_directory = (
        repository / OWNER_CAPTURE_RELATIVE_PATH / request.product_id
    )
    product_directory.mkdir(parents=True, mode=0o700)
    os.chmod(repository / ".secrets", 0o700)
    os.chmod(repository / OWNER_CAPTURE_RELATIVE_PATH, 0o700)
    os.chmod(product_directory, 0o700)
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    (product_directory / "caa-recall.response").symlink_to(outside)
    transport = _FakeTransport(
        _response(
            _caa_body(request.query, count=0),
            content_type="text/html; charset=UTF-8",
        )
    )
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        capture_product_safety_query(
            repository,
            product_id=request.product_id,
            provider="CAA",
            scope="RECALL",
            transport=transport,
        )
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE
    assert outside.read_bytes() == b"unchanged"


def test_clean_environment_and_public_dns_are_fail_closed() -> None:
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        require_clean_network_environment({"HTTP_PROXY": "http://127.0.0.1:1"})
    assert (
        failed.value.code
        is ProductSafetyQueryCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE
    )
    with pytest.raises(ProductSafetyQueryCaptureFailure) as address_failed:
        capture._public_ip("127.0.0.1", family=socket.AF_INET)
    assert (
        address_failed.value.code
        is ProductSafetyQueryCaptureFailureCode.DNS_ADDRESS_REJECTED
    )


class _FakeRawResponse:
    status = 200

    def __init__(self, body: bytes, content_type: str) -> None:
        self.body = body
        self.offset = 0
        self.content_type = content_type

    def getheaders(self) -> list[tuple[str, str]]:
        return [
            ("Content-Type", self.content_type),
            ("Content-Length", str(len(self.body))),
        ]

    def read(self, amount: int | None = None) -> bytes:
        size = len(self.body) if amount is None else amount
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class _FakeConnection:
    def __init__(self, response: _FakeRawResponse) -> None:
        self.response = response
        self.calls: list[tuple[object, ...]] = []

    def connect(self) -> None:
        self.calls.append(("connect",))

    def set_read_timeout(self, seconds: int) -> None:
        self.calls.append(("timeout", seconds))

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self.calls.append(("request", method, path, body, headers))

    def getresponse(self) -> _FakeRawResponse:
        self.calls.append(("response",))
        return self.response

    def close(self) -> None:
        self.calls.append(("close",))


class _FakeConnectionFactory:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.opened: list[tuple[object, ...]] = []

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> _FakeConnection:
        assert tls_context.verify_mode == ssl.CERT_REQUIRED
        assert tls_context.check_hostname is True
        assert tls_context.minimum_version >= ssl.TLSVersion.TLSv1_2
        self.opened.append((host, port, connect_timeout_seconds))
        return self.connection


def test_bounded_transport_uses_exact_tls_post_and_never_redirects() -> None:
    request = _first_request()
    body = _caa_body(request.query, count=0)
    connection = _FakeConnection(
        _FakeRawResponse(body, "text/html; charset=UTF-8")
    )
    factory = _FakeConnectionFactory(connection)
    transport = BoundedProductSafetyHttpsTransport(
        request,
        connection_factory=factory,
        clock=lambda: FIXED_NOW,
        environment={},
    )
    response = transport.post(request)
    assert response.body == body
    assert response.retrieved_at_utc == "2026-09-01T01:02:03Z"
    assert factory.opened == [("www.recall.caa.go.jp", 443, 10)]
    request_call = next(call for call in connection.calls if call[0] == "request")
    assert request_call[1:4] == ("POST", "/result/index.php", request.body)
    assert cast(dict[str, str], request_call[4]) == dict(request.headers)


def test_dry_run_has_no_network_or_secret_write(tmp_path: Path) -> None:
    repository = _copy_contract(tmp_path)
    plan = load_product_safety_query_plan(repository)
    output = describe_product_safety_query(
        repository,
        product_id=plan.products[0].product_id,
        provider="CAA",
        scope="RECALL",
    )
    assert output["status"] == "DRY_RUN"
    assert output["production_write"] is False
    assert not (repository / ".secrets").exists()


def _product_directory(repository: Path, index: int = 0) -> Path:
    product_id = load_product_safety_query_plan(repository).products[index].product_id
    return repository / OWNER_CAPTURE_RELATIVE_PATH / product_id


def test_exact_93_capture_set_is_replayed_without_paths_or_writes(
    complete_capture_repository: Path,
) -> None:
    root = complete_capture_repository / OWNER_CAPTURE_RELATIVE_PATH
    before = {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }

    evidence = verify_product_safety_query_capture_set(
        complete_capture_repository,
        now=FIXED_NOW,
    )

    after = {
        path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }
    assert evidence.capture_count == 93
    assert len(evidence.products) == 31
    assert evidence.complete is True
    assert all(row.status == "VERIFIED_NONE_FOUND" for row in evidence.products)
    assert len(evidence.bundle_sha256) == 64
    assert before == after
    assert str(complete_capture_repository) not in repr(evidence)
    assert "capture_root" not in inspect.signature(
        verify_product_safety_query_capture_set
    ).parameters


def test_verify_set_cli_emits_only_aggregate_safe_binding(
    complete_capture_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(capture_cli, "REPOSITORY_ROOT", complete_capture_repository)
    monkeypatch.setattr(
        capture_cli,
        "verify_product_safety_query_capture_set",
        lambda root: verify_product_safety_query_capture_set(root, now=FIXED_NOW),
    )

    assert capture_cli.main(["verify-set"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "administratively_verified_product_count": 31,
        "bundle_sha256": output["bundle_sha256"],
        "capture_count": 93,
        "network_used": False,
        "product_count": 31,
        "production_write": False,
        "status": "VERIFIED_ADMINISTRATIVE_CLEAR",
    }
    assert len(output["bundle_sha256"]) == 64


def test_missing_or_extra_capture_never_forms_an_exact_set(
    complete_capture_repository: Path,
    tmp_path: Path,
) -> None:
    missing = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "missing"
    )
    (_product_directory(missing) / "caa-recall.capture.v1.json").unlink()
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        verify_product_safety_query_capture_set(missing, now=FIXED_NOW)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_MISSING

    extra = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "extra"
    )
    unexpected = _product_directory(extra) / "unreviewed.response"
    unexpected.write_bytes(b"x")
    os.chmod(unexpected, 0o600)
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        verify_product_safety_query_capture_set(extra, now=FIXED_NOW)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.EVIDENCE_SET_INVALID


def test_product_capture_swap_is_rejected_even_after_attacker_rehash(
    complete_capture_repository: Path,
    tmp_path: Path,
) -> None:
    repository = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "swap"
    )
    first = _product_directory(repository, 0)
    second = _product_directory(repository, 1)
    first_raw = first / "caa-recall.response"
    second_raw = second / "caa-recall.response"
    first_body, second_body = first_raw.read_bytes(), second_raw.read_bytes()
    first_raw.write_bytes(second_body)
    second_raw.write_bytes(first_body)
    os.chmod(first_raw, 0o600)
    os.chmod(second_raw, 0o600)
    for directory, body in ((first, second_body), (second, first_body)):
        _rewrite_metadata(
            directory / "caa-recall.capture.v1.json",
            lambda row, body=body: row.update(
                response_raw_size_bytes=len(body),
                response_raw_sha256=hashlib.sha256(body).hexdigest(),
            ),
        )

    with pytest.raises(ProductSafetyQueryCaptureFailure):
        verify_product_safety_query_capture_set(repository, now=FIXED_NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("product_id", "PRD-ACE-DIFFERENCE-05721"),
        ("exact_model_tokens", ["WRONG-MODEL"]),
        ("query_model_token", "WRONG-MODEL"),
        ("provider", "NITE"),
        ("scope", "ACCIDENT"),
        ("method", "GET"),
        ("endpoint", "https://www.recall.caa.go.jp/other"),
        ("request_material_sha256", "f" * 64),
        ("parser_version", "ATTACKER_PARSER"),
        ("response_raw_file", "nite-recall.response"),
    ),
)
def test_current_plan_and_request_metadata_are_revalidated_after_rehash(
    complete_capture_repository: Path,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    repository = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / field
    )
    metadata = _product_directory(repository) / "caa-recall.capture.v1.json"
    _rewrite_metadata(metadata, lambda row: row.update({field: value}))

    with pytest.raises(ProductSafetyQueryCaptureFailure):
        verify_product_safety_query_capture_set(repository, now=FIXED_NOW)


def test_raw_response_is_reparsed_instead_of_trusting_rehashed_none_found(
    complete_capture_repository: Path,
    tmp_path: Path,
) -> None:
    repository = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "forged-result"
    )
    directory = _product_directory(repository)
    metadata = directory / "caa-recall.capture.v1.json"
    request = _first_request(repository)
    body = _caa_body(request.query, count=1, notice_ids=("123456",))
    raw_path = directory / "caa-recall.response"
    raw_path.write_bytes(body)
    os.chmod(raw_path, 0o600)
    _rewrite_metadata(
        metadata,
        lambda row: row.update(
            response_raw_size_bytes=len(body),
            response_raw_sha256=hashlib.sha256(body).hexdigest(),
        ),
    )

    with pytest.raises(ProductSafetyQueryCaptureFailure):
        verify_product_safety_query_capture_set(repository, now=FIXED_NOW)


@pytest.mark.parametrize(
    ("count", "notice_ids", "expected_status"),
    (
        (1, ("123456",), "BLOCKED_MATCH_FOUND"),
        (2, ("123456",), "BLOCKED_AMBIGUOUS_RESULT"),
    ),
)
def test_replayed_match_or_ambiguous_result_blocks_administrative_verification(
    complete_capture_repository: Path,
    tmp_path: Path,
    count: int,
    notice_ids: tuple[str, ...],
    expected_status: str,
) -> None:
    repository = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / expected_status
    )
    directory = _product_directory(repository)
    request = _first_request(repository)
    body = _caa_body(request.query, count=count, notice_ids=notice_ids)
    raw_path = directory / "caa-recall.response"
    raw_path.write_bytes(body)
    os.chmod(raw_path, 0o600)
    result = "MATCH" if count == len(notice_ids) else "AMBIGUOUS"
    _rewrite_metadata(
        directory / "caa-recall.capture.v1.json",
        lambda row: row.update(
            response_raw_size_bytes=len(body),
            response_raw_sha256=hashlib.sha256(body).hexdigest(),
            result=result,
            result_count=count,
            notice_ids=list(notice_ids),
        ),
    )

    evidence = verify_product_safety_query_capture_set(repository, now=FIXED_NOW)
    assert evidence.complete is False
    assert evidence.products[0].status == expected_status


def test_freshness_is_recomputed_at_30_days_and_future_five_minutes(
    complete_capture_repository: Path,
) -> None:
    boundary = verify_product_safety_query_capture_set(
        complete_capture_repository,
        now=FIXED_NOW + timedelta(days=30),
    )
    assert boundary.complete is True

    stale = verify_product_safety_query_capture_set(
        complete_capture_repository,
        now=FIXED_NOW + timedelta(days=30, seconds=1),
    )
    assert stale.complete is False
    assert all(row.status == "BLOCKED_STALE_CAPTURE" for row in stale.products)

    with pytest.raises(ProductSafetyQueryCaptureFailure):
        verify_product_safety_query_capture_set(
            complete_capture_repository,
            now=FIXED_NOW - timedelta(minutes=5, seconds=1),
        )


@pytest.mark.parametrize("unsafe_kind", ("symlink", "hardlink", "mode"))
def test_private_capture_file_safety_is_rechecked(
    complete_capture_repository: Path,
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    repository = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / unsafe_kind
    )
    raw_path = _product_directory(repository) / "caa-recall.response"
    body = raw_path.read_bytes()
    raw_path.unlink()
    outside = tmp_path / f"{unsafe_kind}.outside"
    outside.write_bytes(body)
    os.chmod(outside, 0o600)
    if unsafe_kind == "symlink":
        raw_path.symlink_to(outside)
    elif unsafe_kind == "hardlink":
        os.link(outside, raw_path)
    else:
        raw_path.write_bytes(body)
        os.chmod(raw_path, 0o644)

    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        verify_product_safety_query_capture_set(repository, now=FIXED_NOW)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE


def test_private_directory_and_shared_lock_safety_are_rechecked(
    complete_capture_repository: Path,
    tmp_path: Path,
) -> None:
    directory_mode = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "directory-mode"
    )
    os.chmod(_product_directory(directory_mode), 0o755)
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        verify_product_safety_query_capture_set(directory_mode, now=FIXED_NOW)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE

    lock_mode = _copy_complete_capture_repository(
        complete_capture_repository, tmp_path / "lock-mode"
    )
    lock_path = (
        lock_mode / OWNER_CAPTURE_RELATIVE_PATH / capture.CAPTURE_LOCK_FILE
    )
    os.chmod(lock_path, 0o644)
    with pytest.raises(ProductSafetyQueryCaptureFailure) as failed:
        verify_product_safety_query_capture_set(lock_mode, now=FIXED_NOW)
    assert failed.value.code is ProductSafetyQueryCaptureFailureCode.STORE_UNSAFE
