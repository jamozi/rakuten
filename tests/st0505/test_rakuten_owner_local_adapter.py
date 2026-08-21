from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import stat
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from raos.adapters import rakuten_owner_local as adapter
from raos.adapters.rakuten_owner_local import (
    DirectRakutenOwnerLocalTransport,
    OwnerPrivateRakutenOwnerLocalCredentialReader,
    OwnerPrivateRakutenOwnerLocalCredentialStore,
    OwnerPrivateRakutenOwnerLocalRequestReader,
    OwnerPrivateRakutenOwnerLocalResultWriter,
    SystemRakutenOwnerLocalHttpsConnectionFactory,
)
from raos.domain.catalog.rakuten_owner_local import (
    RAKUTEN_OWNER_LOCAL_PROFILE,
    RakutenOwnerLocalApi,
    RakutenOwnerLocalCredentials,
    RakutenOwnerLocalFailure,
    RakutenOwnerLocalFailureCode,
    RakutenOwnerLocalItemSearchRequest,
    RakutenOwnerLocalOutcome,
    RakutenOwnerLocalProductSearchRequest,
    RakutenOwnerLocalProductSort,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
    RakutenOwnerLocalRequestDisposition,
    RakutenOwnerLocalResultEnvelope,
    api_definition,
    fixed_owner_local_smoke_request,
    normalized_record,
)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir(mode=0o700)
    return root


def _credentials(
    application: bytes = b"fixture-app",
    access: bytes = b"fixture-key",
    affiliate: bytes = b"fixture-affiliate",
) -> RakutenOwnerLocalCredentials:
    return RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=application,
        _access_key=access,
        _affiliate_id=affiliate,
    )


def _private_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def _item_request_value(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "keyword": "収納",
        "shop_code": None,
        "item_code": None,
        "genre_id": None,
        "hits": 1,
        "page": 1,
        "sort": "standard",
    }
    value.update(overrides)
    return value


def _product_request_value(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "keyword": "収納",
        "genre_id": None,
        "product_id": None,
        "product_code": None,
        "hits": 1,
        "page": 1,
        "sort": "standard",
    }
    value.update(overrides)
    return value


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
        content_length: str | None = None,
        transfer_encoding: str | None = None,
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._headers: dict[str, str] = {"Content-Type": content_type}
        if content_length is not None:
            self._headers["Content-Length"] = content_length
        if transfer_encoding is not None:
            self._headers["Transfer-Encoding"] = transfer_encoding

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._headers.get(name, default)

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            amount = len(self._body) - self._offset
        start = self._offset
        self._offset = min(len(self._body), self._offset + amount)
        return self._body[start : self._offset]


class _FakeConnection:
    def __init__(
        self,
        response: _FakeResponse,
        *,
        request_error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.request_error = request_error
        self.connect_count = 0
        self.request_count = 0
        self.closed = False
        self.read_timeout: int | None = None
        self.method: str | None = None
        self.target: str | None = None
        self.headers: dict[str, str] | None = None

    def connect(self) -> None:
        self.connect_count += 1

    def set_read_timeout(self, seconds: int) -> None:
        self.read_timeout = seconds

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.request_count += 1
        self.method = method
        self.target = path
        self.headers = dict(headers)
        if self.request_error is not None:
            raise self.request_error

    def getresponse(self) -> _FakeResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class _FakeFactory:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.open_count = 0
        self.arguments: dict[str, object] | None = None

    def open(self, **arguments: object) -> _FakeConnection:
        self.open_count += 1
        self.arguments = arguments
        return self.connection


def _clean_transport_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    names = {
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    }
    for name in names:
        monkeypatch.delenv(name, raising=False)


def _json_body(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _item_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "affiliateUrl": "https://example.invalid/affiliate/item",
        "itemCode": "shop:item",
        "itemName": "storage fixture",
        "itemPrice": 100,
        "itemUrl": "https://example.invalid/item",
    }
    record.update(overrides)
    return record


def _item_body(**record_overrides: object) -> bytes:
    return _json_body(
        {
            "count": 1,
            "page": 1,
            "first": 1,
            "last": 1,
            "hits": 1,
            "pageCount": 1,
            "items": [_item_record(**record_overrides)],
        }
    )


def _item_exact_request(
    selector_field: str,
    requested_value: str,
    *,
    hits: int = 1,
) -> RakutenOwnerLocalItemSearchRequest:
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH)
    assert type(request) is RakutenOwnerLocalItemSearchRequest
    if selector_field == "itemCode":
        policy = replace(
            request.policy,
            keyword=None,
            item_code=requested_value,
            hits=hits,
        )
    else:
        assert selector_field == "shopCode"
        policy = replace(
            request.policy,
            keyword=None,
            shop_code=requested_value,
            hits=hits,
        )
    return RakutenOwnerLocalItemSearchRequest(policy=policy)


def _product_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "affiliateUrl": "https://example.invalid/affiliate/product",
        "productCode": "fixture-product-code",
        "productId": "fixture-product-id",
        "productUrlPC": "https://example.invalid/product",
    }
    record.update(overrides)
    return record


def _product_body(collection: str = "products", **record_overrides: object) -> bytes:
    return _json_body(
        {
            "count": 1,
            "page": 1,
            "first": 1,
            "last": 1,
            "hits": 1,
            "pageCount": 1,
            collection: [_product_record(**record_overrides)],
        }
    )


def _summary_body(
    api: RakutenOwnerLocalApi,
    *,
    count: int,
    first: int,
    last: int,
    hits: int,
    page_count: int,
    records: list[object],
) -> bytes:
    collection = "items" if api is RakutenOwnerLocalApi.ITEM_SEARCH else "products"
    return _json_body(
        {
            "count": count,
            "page": 1,
            "first": first,
            "last": last,
            "hits": hits,
            "pageCount": page_count,
            collection: records,
        }
    )


def _execute(
    monkeypatch: pytest.MonkeyPatch,
    api: RakutenOwnerLocalApi,
    response: _FakeResponse,
    *,
    request_error: BaseException | None = None,
    request: RakutenOwnerLocalRequest | None = None,
) -> tuple[object, _FakeConnection, _FakeFactory, DirectRakutenOwnerLocalTransport]:
    _clean_transport_environment(monkeypatch)
    connection = _FakeConnection(response, request_error=request_error)
    factory = _FakeFactory(connection)
    transport = DirectRakutenOwnerLocalTransport(factory)
    selected_request = (
        fixed_owner_local_smoke_request(api) if request is None else request
    )
    result = transport.execute(api_definition(api), selected_request, _credentials())
    return result, connection, factory, transport


def test_credential_setup_read_rotate_and_no_overwrite(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    reader = OwnerPrivateRakutenOwnerLocalCredentialReader(root)

    store.setup_ready()
    store.setup(_credentials())
    path = root / ".secrets/rakuten-owner-local/credentials.v1.json"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    assert reader.read().application_id_query_value() == "fixture-app"
    mapping = json.loads(path.read_text(encoding="utf-8"))
    assert set(mapping) == {
        "schema_version",
        "profile",
        "application_id",
        "access_key",
        "affiliate_id",
    }
    assert mapping["profile"] == RAKUTEN_OWNER_LOCAL_PROFILE

    with pytest.raises(RakutenOwnerLocalFailure) as duplicate:
        store.setup(_credentials(application=b"other"))
    assert duplicate.value.code is RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID
    assert reader.read().application_id_query_value() == "fixture-app"

    before = path.stat().st_ino
    store.rotate_ready()
    store.rotate(_credentials(application=b"rotated-app"))
    assert path.stat().st_ino != before
    assert reader.read().application_id_query_value() == "rotated-app"


def test_credential_reader_rejects_schema_mode_symlink_and_recovery(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    reader = OwnerPrivateRakutenOwnerLocalCredentialReader(root)
    store.setup(_credentials())
    path = root / ".secrets/rakuten-owner-local/credentials.v1.json"

    path.chmod(0o640)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read()
    path.chmod(0o600)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["unexpected"] = True
    _private_json(path, value)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read()

    path.unlink()
    outside = root / "outside.json"
    _private_json(outside, value)
    path.symlink_to(outside)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read()

    path.unlink()
    store.setup(_credentials())
    marker = path.parent / ".credential-recovery-required"
    marker.write_text("fixed recovery marker\n", encoding="ascii")
    marker.chmod(0o600)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read()
    with pytest.raises(RakutenOwnerLocalFailure):
        store.rotate_ready()


def test_setup_rollback_failure_leaves_value_free_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    real_unlink = os.unlink

    monkeypatch.setattr(
        adapter,
        "_validate_published_file",
        lambda *_arguments, **_keywords: (_ for _ in ()).throw(OSError("fixture")),
    )

    def fail_target_unlink(path: object, *args: object, **kwargs: object) -> None:
        if path == "credentials.v1.json":
            raise OSError("fixture rollback")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", fail_target_unlink)
    with pytest.raises(RakutenOwnerLocalFailure):
        store.setup(_credentials())
    owner = root / ".secrets/rakuten-owner-local"
    marker = owner / ".credential-recovery-required"
    assert marker.is_file()
    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert b"fixture-key" not in marker.read_bytes()
    with pytest.raises(RakutenOwnerLocalFailure):
        OwnerPrivateRakutenOwnerLocalCredentialReader(root).read()


def test_rotate_exchange_rollback_failure_leaves_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    store.setup(_credentials())
    real_validate = adapter._validate_published_file
    real_exchange = adapter._rename_exchange
    validate_calls = 0
    exchange_calls = 0

    def fail_second_validation(*args: object, **kwargs: object) -> None:
        nonlocal validate_calls
        validate_calls += 1
        if validate_calls == 2:
            raise OSError("fixture post-exchange")
        real_validate(*args, **kwargs)

    def fail_rollback_exchange(*args: object, **kwargs: object) -> None:
        nonlocal exchange_calls
        exchange_calls += 1
        if exchange_calls == 2:
            raise OSError("fixture rollback exchange")
        real_exchange(*args, **kwargs)

    monkeypatch.setattr(adapter, "_validate_published_file", fail_second_validation)
    monkeypatch.setattr(adapter, "_rename_exchange", fail_rollback_exchange)
    with pytest.raises(RakutenOwnerLocalFailure):
        store.rotate(_credentials(application=b"rotated"))
    owner = root / ".secrets/rakuten-owner-local"
    assert (owner / ".credential-recovery-required").is_file()
    with pytest.raises(RakutenOwnerLocalFailure):
        OwnerPrivateRakutenOwnerLocalCredentialReader(root).read()


def test_rotate_post_exchange_fsync_failure_restores_old_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    store.setup(_credentials())
    real_fsync = os.fsync
    calls = 0

    def fail_post_exchange_once(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("fixture post-exchange fsync")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_post_exchange_once)
    with pytest.raises(RakutenOwnerLocalFailure):
        store.rotate(_credentials(application=b"rotated"))
    reader = OwnerPrivateRakutenOwnerLocalCredentialReader(root)
    assert reader.read().application_id_query_value() == "fixture-app"
    owner = root / ".secrets/rakuten-owner-local"
    assert not any(path.name.startswith(".rotate-") for path in owner.iterdir())


def test_rotate_final_directory_fsync_failure_leaves_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    store = OwnerPrivateRakutenOwnerLocalCredentialStore(root)
    store.setup(_credentials())
    real_fsync = os.fsync
    calls = 0

    def fail_final_fsync_once(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("fixture final directory fsync")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_final_fsync_once)
    with pytest.raises(RakutenOwnerLocalFailure):
        store.rotate(_credentials(application=b"rotated"))
    owner = root / ".secrets/rakuten-owner-local"
    assert (owner / ".credential-recovery-required").is_file()
    with pytest.raises(RakutenOwnerLocalFailure):
        OwnerPrivateRakutenOwnerLocalCredentialReader(root).read()


@pytest.mark.parametrize(
    ("api", "value"),
    [
        (RakutenOwnerLocalApi.ITEM_SEARCH, _item_request_value()),
        (RakutenOwnerLocalApi.PRODUCT_SEARCH, _product_request_value()),
        (
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            _product_request_value(
                keyword=None,
                product_id="fixture-id",
            ),
        ),
    ],
)
def test_request_reader_accepts_only_safe_absolute_private_json(
    tmp_path: Path, api: RakutenOwnerLocalApi, value: dict[str, object]
) -> None:
    path = tmp_path / f"{api.value}.json"
    _private_json(path, value)
    request = OwnerPrivateRakutenOwnerLocalRequestReader().read(path, api)
    assert request.api is api
    assert request.fingerprint == request.fingerprint


def test_request_reader_rejects_unknown_review_modes_aliases_and_permissions(
    tmp_path: Path,
) -> None:
    reader = OwnerPrivateRakutenOwnerLocalRequestReader()
    path = tmp_path / "request.json"
    _private_json(path, _item_request_value(reviewCount=1))
    with pytest.raises(RakutenOwnerLocalFailure) as unknown:
        reader.read(path, RakutenOwnerLocalApi.ITEM_SEARCH)
    assert unknown.value.code is RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID

    _private_json(path, _product_request_value(sort="-satisfied"))
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read(path, RakutenOwnerLocalApi.PRODUCT_SEARCH)

    _private_json(path, _product_request_value(product_id="x"))
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read(path, RakutenOwnerLocalApi.PRODUCT_SEARCH)

    _private_json(path, _item_request_value())
    path.chmod(0o644)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read(path, RakutenOwnerLocalApi.ITEM_SEARCH)
    path.chmod(0o600)
    link = tmp_path / "request-link.json"
    link.symlink_to(path)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read(link, RakutenOwnerLocalApi.ITEM_SEARCH)
    with pytest.raises(RakutenOwnerLocalFailure):
        reader.read(Path("relative.json"), RakutenOwnerLocalApi.ITEM_SEARCH)


def test_item_transport_exact_placement_and_single_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _item_body(
        catchcopy="discarded provider text",
        itemCaption="discarded provider text",
    )
    result, connection, factory, transport = _execute(
        monkeypatch,
        RakutenOwnerLocalApi.ITEM_SEARCH,
        _FakeResponse(body, content_length=str(len(body))),
    )
    provider = cast(RakutenOwnerLocalProviderResult, result)
    assert provider.response_sha256 == hashlib.sha256(body).hexdigest()
    assert provider.normalized_object()["classification"] == "UNTRUSTED_PROVIDER_DATA"
    records = cast(list[dict[str, object]], provider.normalized_object()["items"])
    assert "catchcopy" not in records[0]
    assert "itemCaption" not in records[0]
    assert connection.request_count == 1
    assert connection.connect_count == 1
    assert connection.closed
    assert connection.read_timeout == 20
    assert factory.open_count == 1
    assert factory.arguments is not None
    assert factory.arguments["host"] == "openapi.rakuten.co.jp"
    assert factory.arguments["port"] == 443
    assert connection.method == "GET"
    assert connection.target is not None
    target = urlsplit(connection.target)
    assert target.path == "/ichibams/api/IchibaItem/Search/20260701"
    query = parse_qs(target.query, keep_blank_values=True)
    assert query["applicationId"] == ["fixture-app"]
    assert query["affiliateId"] == ["fixture-affiliate"]
    assert query["keyword"] == ["収納"]
    assert query["page"] == ["1"]
    assert query["availability"] == ["1"]
    assert query["sort"] == ["standard"]
    assert "accessKey" not in query
    assert "reviewCount" not in query["elements"][0]
    assert "reviewAverage" not in query["elements"][0]
    assert "affiliateRate" not in query["elements"][0]
    assert connection.headers is not None
    assert connection.headers["accessKey"] == "fixture-key"
    assert connection.headers["Host"] == "openapi.rakuten.co.jp"
    assert "fixture-key" not in connection.target

    with pytest.raises(RakutenOwnerLocalFailure) as repeated:
        transport.execute(
            api_definition(RakutenOwnerLocalApi.ITEM_SEARCH),
            fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH),
            _credentials(),
        )
    assert repeated.value.code is RakutenOwnerLocalFailureCode.REQUEST_ALREADY_ATTEMPTED
    assert connection.request_count == 1


@pytest.mark.parametrize("collection", ["products", "items"])
def test_product_transport_accepts_only_closed_flat_v2_collection_aliases(
    monkeypatch: pytest.MonkeyPatch, collection: str
) -> None:
    body = _product_body(collection)
    result, connection, _factory, _transport = _execute(
        monkeypatch,
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        _FakeResponse(body, content_length=str(len(body))),
    )
    assert cast(RakutenOwnerLocalProviderResult, result).records
    assert connection.target is not None
    target = urlsplit(connection.target)
    assert target.path == "/ichibaproduct/api/Product/Search/20250801"
    query = parse_qs(target.query)
    assert query["sort"] == ["standard"]
    assert query["page"] == ["1"]
    assert "reviewCount" not in query["elements"][0]
    assert "reviewAverage" not in query["elements"][0]
    assert "affiliateRate" not in query["elements"][0]


@pytest.mark.parametrize(
    ("selector_field", "request_keyword"),
    (("productId", "product_id"), ("productCode", "product_code")),
)
def test_product_exact_selector_requires_an_exact_returned_match(
    monkeypatch: pytest.MonkeyPatch,
    selector_field: str,
    request_keyword: str,
) -> None:
    requested_value = f"requested-{request_keyword}"
    request = RakutenOwnerLocalProductSearchRequest(
        keyword=None,
        genre_id=None,
        product_id=requested_value if request_keyword == "product_id" else None,
        product_code=requested_value if request_keyword == "product_code" else None,
        hits=1,
        page=1,
        sort=RakutenOwnerLocalProductSort.STANDARD,
    )
    matching_body = _product_body(**{selector_field: requested_value})
    result, connection, _factory, _transport = _execute(
        monkeypatch,
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        _FakeResponse(matching_body, content_length=str(len(matching_body))),
        request=request,
    )
    record = cast(RakutenOwnerLocalProviderResult, result).records[0].as_object()
    assert record[selector_field] == requested_value
    nonselected_field = "productCode" if selector_field == "productId" else "productId"
    assert (
        record[nonselected_field]
        == {
            "productCode": "fixture-product-code",
            "productId": "fixture-product-id",
        }[nonselected_field]
    )
    assert connection.target is not None
    assert parse_qs(urlsplit(connection.target).query)[selector_field] == [
        requested_value
    ]

    mismatched_body = _product_body(**{selector_field: "different-provider-value"})
    with pytest.raises(RakutenOwnerLocalFailure) as mismatch:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            _FakeResponse(
                mismatched_body,
                content_length=str(len(mismatched_body)),
            ),
            request=request,
        )
    assert mismatch.value.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert (
        mismatch.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert mismatch.value.http_status == 200
    assert mismatch.value.body_byte_count == len(mismatched_body)
    assert mismatch.value.response_sha256 == hashlib.sha256(mismatched_body).hexdigest()
    assert mismatch.value.request_count == 1


@pytest.mark.parametrize(
    ("selector_field", "requested_value", "nonselected_field", "nonselected_value"),
    (
        ("itemCode", "requested-shop:item", "shopCode", "other-shop"),
        ("shopCode", "requested-shop", "itemCode", "other-shop:other-item"),
    ),
)
def test_item_exact_selector_requires_an_exact_returned_match(
    monkeypatch: pytest.MonkeyPatch,
    selector_field: str,
    requested_value: str,
    nonselected_field: str,
    nonselected_value: str,
) -> None:
    request = _item_exact_request(selector_field, requested_value)
    matching_body = _item_body(
        **{
            selector_field: requested_value,
            nonselected_field: nonselected_value,
        }
    )
    result, connection, _factory, _transport = _execute(
        monkeypatch,
        RakutenOwnerLocalApi.ITEM_SEARCH,
        _FakeResponse(matching_body, content_length=str(len(matching_body))),
        request=request,
    )
    record = cast(RakutenOwnerLocalProviderResult, result).records[0].as_object()
    assert record[selector_field] == requested_value
    assert record[nonselected_field] == nonselected_value
    assert connection.target is not None
    assert parse_qs(urlsplit(connection.target).query)[selector_field] == [
        requested_value
    ]

    mismatched_body = _item_body(
        **{
            selector_field: "different-provider-value",
            nonselected_field: nonselected_value,
        }
    )
    with pytest.raises(RakutenOwnerLocalFailure) as mismatch:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(
                mismatched_body,
                content_length=str(len(mismatched_body)),
            ),
            request=request,
        )
    assert mismatch.value.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert (
        mismatch.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert mismatch.value.http_status == 200
    assert mismatch.value.body_byte_count == len(mismatched_body)
    assert mismatch.value.response_sha256 == hashlib.sha256(mismatched_body).hexdigest()
    assert mismatch.value.request_count == 1


@pytest.mark.parametrize(
    ("selector_field", "requested_value"),
    (("itemCode", "requested-shop:item"), ("shopCode", "requested-shop")),
)
def test_item_exact_selector_requires_the_selected_response_field(
    monkeypatch: pytest.MonkeyPatch,
    selector_field: str,
    requested_value: str,
) -> None:
    request = _item_exact_request(selector_field, requested_value)
    record = _item_record()
    record.pop(selector_field, None)
    body = _summary_body(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        count=1,
        first=1,
        last=1,
        hits=1,
        page_count=1,
        records=[record],
    )

    with pytest.raises(RakutenOwnerLocalFailure) as missing:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
            request=request,
        )

    assert missing.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert missing.value.request_count == 1
    assert missing.value.body_byte_count == len(body)
    assert missing.value.response_sha256 == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize(
    ("selector_field", "requested_value"),
    (("itemCode", "requested-shop:item"), ("shopCode", "requested-shop")),
)
def test_item_exact_selector_checks_every_record_and_accepts_empty_results(
    monkeypatch: pytest.MonkeyPatch,
    selector_field: str,
    requested_value: str,
) -> None:
    request = _item_exact_request(selector_field, requested_value, hits=2)
    nonselected = (
        {"shopCode": "other-shop"}
        if selector_field == "itemCode"
        else {"itemCode": "other-shop:item"}
    )
    mismatched_body = _summary_body(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        count=2,
        first=1,
        last=2,
        hits=2,
        page_count=1,
        records=[
            _item_record(**{selector_field: requested_value}, **nonselected),
            _item_record(**{selector_field: "different-provider-value"}, **nonselected),
        ],
    )
    with pytest.raises(RakutenOwnerLocalFailure) as mismatch:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(mismatched_body, content_length=str(len(mismatched_body))),
            request=request,
        )
    assert mismatch.value.code is RakutenOwnerLocalFailureCode.RESULT_MISMATCH
    assert mismatch.value.request_count == 1

    empty_body = _summary_body(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        count=0,
        first=0,
        last=0,
        hits=2,
        page_count=0,
        records=[],
    )
    empty, _connection, _factory, _transport = _execute(
        monkeypatch,
        RakutenOwnerLocalApi.ITEM_SEARCH,
        _FakeResponse(empty_body, content_length=str(len(empty_body))),
        request=request,
    )
    assert cast(RakutenOwnerLocalProviderResult, empty).records == ()


@pytest.mark.parametrize(
    "api",
    (RakutenOwnerLocalApi.ITEM_SEARCH, RakutenOwnerLocalApi.PRODUCT_SEARCH),
)
def test_summary_relationships_accept_consistent_empty_and_capped_results(
    monkeypatch: pytest.MonkeyPatch,
    api: RakutenOwnerLocalApi,
) -> None:
    empty_body = _summary_body(
        api,
        count=0,
        first=0,
        last=0,
        hits=1,
        page_count=0,
        records=[],
    )
    empty, _connection, _factory, _transport = _execute(
        monkeypatch,
        api,
        _FakeResponse(empty_body, content_length=str(len(empty_body))),
    )
    assert cast(RakutenOwnerLocalProviderResult, empty).records == ()

    record = (
        _item_record() if api is RakutenOwnerLocalApi.ITEM_SEARCH else _product_record()
    )
    capped_body = _summary_body(
        api,
        count=101,
        first=1,
        last=1,
        hits=1,
        page_count=100,
        records=[record],
    )
    capped, _connection, _factory, _transport = _execute(
        monkeypatch,
        api,
        _FakeResponse(capped_body, content_length=str(len(capped_body))),
    )
    capped_result = cast(RakutenOwnerLocalProviderResult, capped)
    assert capped_result.count == 101
    assert capped_result.page_count == 100
    assert len(capped_result.records) == 1


@pytest.mark.parametrize(
    ("count", "first", "last", "page_count", "records"),
    (
        (0, 0, 0, 0, [_item_record()]),
        (1, 0, 0, 1, []),
        (0, 0, 0, 1, []),
        (0, 1, 0, 0, []),
        (0, 0, 1, 0, []),
        (2, 1, 1, 0, [_item_record()]),
        (1, 2, 2, 1, [_item_record()]),
        (1, 1, 2, 1, [_item_record()]),
        (101, 1, 1, 101, [_item_record()]),
    ),
)
def test_summary_relationship_contradictions_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    count: int,
    first: int,
    last: int,
    page_count: int,
    records: list[object],
) -> None:
    body = _summary_body(
        RakutenOwnerLocalApi.ITEM_SEARCH,
        count=count,
        first=first,
        last=last,
        hits=1,
        page_count=page_count,
        records=records,
    )
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert failure.value.body_byte_count == len(body)
    assert failure.value.response_sha256 == hashlib.sha256(body).hexdigest()
    assert failure.value.request_count == 1


def test_summary_count_cannot_be_less_than_returned_cardinality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = RakutenOwnerLocalProductSearchRequest(
        keyword="収納",
        genre_id=None,
        product_id=None,
        product_code=None,
        hits=2,
        page=1,
        sort=RakutenOwnerLocalProductSort.STANDARD,
    )
    body = _summary_body(
        RakutenOwnerLocalApi.PRODUCT_SEARCH,
        count=1,
        first=1,
        last=2,
        hits=2,
        page_count=1,
        records=[
            _product_record(),
            _product_record(
                productId="fixture-product-id-2",
                productCode="fixture-product-code-2",
            ),
        ],
    )
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
            request=request,
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert failure.value.body_byte_count == len(body)
    assert failure.value.response_sha256 == hashlib.sha256(body).hexdigest()
    assert failure.value.request_count == 1


@pytest.mark.parametrize(
    "body",
    [
        _product_body("Products"),
        _json_body(
            {
                "count": 1,
                "page": 1,
                "first": 1,
                "last": 1,
                "hits": 1,
                "pageCount": 1,
                "products": [
                    {
                        "Product": {
                            "affiliateUrl": "https://example.invalid/a",
                            "productCode": "code",
                            "productId": "id",
                            "productUrlPC": "https://example.invalid/p",
                        }
                    }
                ],
            }
        ),
    ],
)
def test_product_transport_rejects_case_alias_and_wrapped_v1_records(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.PRODUCT_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert failure.value.response_sha256 == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            b'{"count":1,"count":1}',
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_DUPLICATE_KEY,
        ),
        (
            b'{"count":NaN}',
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_NONFINITE,
        ),
        (
            b"[" * 34 + b"0" + b"]" * 34,
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_TREE_INVALID,
        ),
    ],
)
def test_response_json_failures_are_strict_hashed_and_non_reflective(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    code: RakutenOwnerLocalFailureCode,
) -> None:
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
        )
    assert failure.value.code is code
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert failure.value.response_sha256 == hashlib.sha256(body).hexdigest()
    assert str(failure.value) == code.value
    assert body.decode("ascii", errors="ignore") not in repr(failure.value)


@pytest.mark.parametrize("field", ["reviewCount", "reviewAverage", "affiliateRate"])
def test_response_rejects_forbidden_review_and_rate_fields(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    body = _item_body(**{field: 1})
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        _execute(
            monkeypatch,
            RakutenOwnerLocalApi.ITEM_SEARCH,
            _FakeResponse(body, content_length=str(len(body))),
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT


def test_redirect_and_complete_http_failure_are_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"provider":"untrusted"}'
    connection = _FakeConnection(
        _FakeResponse(body, status=302, content_length=str(len(body)))
    )
    factory = _FakeFactory(connection)
    _clean_transport_environment(monkeypatch)
    transport = DirectRakutenOwnerLocalTransport(factory)
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH)
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        transport.execute(
            api_definition(RakutenOwnerLocalApi.ITEM_SEARCH), request, _credentials()
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.HTTP_REDIRECT_REJECTED
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert failure.value.response_sha256 == hashlib.sha256(body).hexdigest()
    assert connection.request_count == 1
    assert factory.open_count == 1


def test_request_or_framing_failure_is_ambiguous_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _item_body()
    _clean_transport_environment(monkeypatch)
    connection = _FakeConnection(
        _FakeResponse(body, content_length=str(len(body) + 1)),
        request_error=OSError("fixture send uncertainty"),
    )
    factory = _FakeFactory(connection)
    transport = DirectRakutenOwnerLocalTransport(factory)
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        transport.execute(
            api_definition(RakutenOwnerLocalApi.ITEM_SEARCH),
            fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH),
            _credentials(),
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
    )
    assert failure.value.response_sha256 is None
    assert connection.request_count == 1

    connection = _FakeConnection(_FakeResponse(body, content_length=str(len(body) + 1)))
    transport = DirectRakutenOwnerLocalTransport(_FakeFactory(connection))
    with pytest.raises(RakutenOwnerLocalFailure) as framing:
        transport.execute(
            api_definition(RakutenOwnerLocalApi.ITEM_SEARCH),
            fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH),
            _credentials(),
        )
    assert (
        framing.value.disposition
        is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
    )
    assert framing.value.response_sha256 is None
    assert connection.request_count == 1


def test_proxy_or_tls_override_refuses_before_factory_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clean_transport_environment(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    body = _item_body()
    connection = _FakeConnection(_FakeResponse(body))
    factory = _FakeFactory(connection)
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        DirectRakutenOwnerLocalTransport(factory).execute(
            api_definition(RakutenOwnerLocalApi.ITEM_SEARCH),
            fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH),
            _credentials(),
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.TLS_ENVIRONMENT_INVALID
    assert factory.open_count == 0
    assert connection.request_count == 0


def test_mixed_public_and_private_dns_vetoes_before_https_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("8.8.8.8", 443),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            ),
        ],
    )
    constructed = False

    def forbidden_https(*_args: object, **_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("must reject every DNS candidate before construction")

    monkeypatch.setattr(adapter.http.client, "HTTPSConnection", forbidden_https)
    context = ssl.create_default_context()
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        SystemRakutenOwnerLocalHttpsConnectionFactory().open(
            host="openapi.rakuten.co.jp",
            port=443,
            connect_timeout_seconds=5,
            tls_context=context,
        )
    assert failure.value.code is RakutenOwnerLocalFailureCode.DNS_ADDRESS_REJECTED
    assert not constructed


def _success_envelope() -> RakutenOwnerLocalResultEnvelope:
    request = fixed_owner_local_smoke_request(RakutenOwnerLocalApi.ITEM_SEARCH)
    body = _item_body()
    result = RakutenOwnerLocalProviderResult(
        api=RakutenOwnerLocalApi.ITEM_SEARCH,
        request_fingerprint=request.fingerprint,
        http_status=200,
        body_byte_count=len(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
        count=1,
        page=1,
        first=1,
        last=1,
        hits=1,
        page_count=1,
        records=(
            normalized_record(
                RakutenOwnerLocalApi.ITEM_SEARCH,
                {
                    "affiliateUrl": "https://example.invalid/affiliate/item",
                    "itemCode": "shop:item",
                    "itemName": "storage fixture",
                    "itemPrice": 100,
                    "itemUrl": "https://example.invalid/item",
                },
            ),
        ),
    )
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    return RakutenOwnerLocalResultEnvelope(
        run_id="20260821T120000.000000Z-0123456789abcdef0123456789abcdef",
        started_at=now,
        finished_at=now,
        api=RakutenOwnerLocalApi.ITEM_SEARCH,
        request_fingerprint=request.fingerprint,
        outcome=RakutenOwnerLocalOutcome.SUCCESS,
        provider_result=result,
        failure=None,
    )


def test_result_writer_preflight_no_replace_and_sanitized_metadata(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    OwnerPrivateRakutenOwnerLocalCredentialStore(root).setup(_credentials())
    writer = OwnerPrivateRakutenOwnerLocalResultWriter(root)
    writer.doctor_ready()
    writer.preflight()
    envelope = _success_envelope()
    writer.write(envelope)
    path = root / f".secrets/rakuten-owner-local/results/{envelope.run_id}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["evidence_authority"] == "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"
    assert value["formal_tst_016"] == "NOT_EXECUTED"
    assert value["staging"] == "NOT_EXECUTED"
    assert value["production"] == "NOT_EXECUTED"
    assert value["od_015"] == "UNRESOLVED_EXTERNAL_EVIDENCE_REQUIRED"
    assert value["provider_data_classification"] == "UNTRUSTED_PROVIDER_DATA"
    assert len(value["items"]) == 1
    raw = path.read_bytes()
    assert b"fixture-key" not in raw
    assert b"reviewCount" not in raw
    assert b"reviewAverage" not in raw
    assert b"affiliateRate" not in raw

    with pytest.raises(RakutenOwnerLocalFailure) as duplicate:
        writer.write(envelope)
    assert duplicate.value.code is RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID
    assert (
        duplicate.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert duplicate.value.http_status == 200
    assert duplicate.value.response_sha256 == envelope.provider_result.response_sha256


def test_result_rollback_failure_preserves_metadata_and_blocks_future_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repository(tmp_path)
    OwnerPrivateRakutenOwnerLocalCredentialStore(root).setup(_credentials())
    writer = OwnerPrivateRakutenOwnerLocalResultWriter(root)
    writer.preflight()
    envelope = _success_envelope()
    target = f"{envelope.run_id}.json"
    real_unlink = os.unlink

    monkeypatch.setattr(
        adapter,
        "_validate_published_file",
        lambda *_arguments, **_keywords: (_ for _ in ()).throw(OSError("fixture")),
    )

    def fail_target_unlink(path: object, *args: object, **kwargs: object) -> None:
        if path == target:
            raise OSError("fixture rollback")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", fail_target_unlink)
    with pytest.raises(RakutenOwnerLocalFailure) as failure:
        writer.write(envelope)
    assert failure.value.code is RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID
    assert (
        failure.value.disposition
        is RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED
    )
    assert failure.value.http_status == 200
    assert failure.value.body_byte_count == envelope.provider_result.body_byte_count
    assert failure.value.response_sha256 == envelope.provider_result.response_sha256
    result_dir = root / ".secrets/rakuten-owner-local/results"
    marker = result_dir / f"{envelope.run_id}.recovery-required"
    assert marker.is_file()
    assert b"fixture-key" not in marker.read_bytes()
    with pytest.raises(RakutenOwnerLocalFailure):
        writer.preflight()
