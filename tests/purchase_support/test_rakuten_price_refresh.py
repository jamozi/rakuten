"""KS-020 price refresh core: identity safety, refusal paths and the private overlay.

Every Rakuten response here is synthetic (fixtures/rakuten_price_refresh). The
HTTP transport is injected and sockets are disabled for the whole module.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html import unescape
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
from urllib.parse import parse_qsl, urlsplit

import pytest

from raos.adapters.rakuten_price_refresh_client import (
    HttpResult,
    PriceRefreshClient,
    PrivateStore,
    RefreshCredentials,
    read_refresh_credentials,
    scan_repository_for_overlay,
)
from raos.domain.editorial import rakuten_price_refresh as rpr
from raos.domain.editorial.purchase_support import reference_price
from scripts import raos_rakuten_price_refresh as cli

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures/rakuten_price_refresh"
CATALOG_BYTES = (FIXTURES / "catalog.synthetic.json").read_bytes()
RESPONSES = json.loads((FIXTURES / "responses.synthetic.json").read_text())
BODY = (FIXTURES / "body.price-free.synthetic.html").read_text()
APP_ID = "synthetic-app-0001"
ACCESS_KEY = "synthetic-key-0001"
RUN_ID = "ks020-synthetic-0001"
# Odd microseconds: the ISO strings derived from this instant appear in no tracked file.
T0 = datetime(2026, 9, 15, 1, 2, 3, 456789, tzinfo=timezone.utc)
CREDIT = '<p class="ps-note ps-media-credit">'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def refuse(*_args, **_kwargs):
        attempts.append("connect")
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    yield
    # The client converts transport exceptions to status 0, so a refused connect
    # could otherwise pass silently; record attempts and fail at teardown.
    assert attempts == [], "network access attempted"


def plan():
    return rpr.build_plan(json.loads(CATALOG_BYTES), rpr.sha256_hex(CATALOG_BYTES))


def entry(offer_id):
    return next(e for e in rpr.validate_plan(plan()) if e.offer_id == offer_id)


def body_for(*rows):
    return json.dumps(
        {"count": len(rows), "page": 1, "hits": 1, "items": list(rows)},
        ensure_ascii=False,
    )


def row(name="row_single", **changes):
    return {**deepcopy(RESPONSES[name]), **changes}


def matched_entry(observed=T0, **row_changes):
    return rpr.classify_observation(
        entry("synthetic-single"), 200, body_for(row(**row_changes)), observed
    )


def overlay_of(*entries, created=None):
    created = created or max(
        rpr.parse_time(e["observed_at"]) for e in entries
    ) + timedelta(minutes=5)
    return rpr.build_overlay(RUN_ID, "a" * 64, list(entries), created)


def approval(**changes):
    return {**rpr.new_approval(RUN_ID, "a" * 64, T0 - timedelta(minutes=1)), **changes}


def codes(findings):
    return {f.code for f in findings}


def git(root, *args):
    return subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "user.name=t",
            *args,
        ],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Request format and plan
# ---------------------------------------------------------------------------


def test_request_uses_the_official_2026_07_01_item_search_parameters():
    path = rpr.request_path("synth-shop:synth-item-a", APP_ID)
    parts = urlsplit(path)
    assert parts.path == "/ichibams/api/IchibaItem/Search/20260701"
    assert dict(parse_qsl(parts.query)) == {
        "applicationId": APP_ID,
        "itemCode": "synth-shop:synth-item-a",
        "hits": "1",
        "availability": "0",
        "format": "json",
        "formatVersion": "2",
        "elements": "itemCode,itemName,itemUrl,shopCode,itemPrice,itemPriceMin1,itemPriceMax1,itemPriceMin3,itemPriceMax3,availability,taxFlag,postageFlag",
    }
    assert "affiliateId" not in parts.query and "accessKey" not in parts.query
    with pytest.raises(rpr.RefreshError, match="ITEM_CODE_INVALID"):
        rpr.request_path("no-colon", APP_ID)


def test_plan_binds_editorial_identity_without_api_values():
    document = plan()
    by_id = {e["offer_id"]: e for e in document["entries"]}
    assert sorted(by_id) == [
        "synthetic-shared-page",
        "synthetic-single",
        "synthetic-variant",
    ]
    assert {s["offer_id"]: s["reason"] for s in document["skipped"]} == {
        "synthetic-maker": "NOT_RAKUTEN_ITEM_PAGE",
        "synthetic-shop-top": "MERCHANT_URL_UNPARSEABLE",
    }
    single = by_id["synthetic-single"]
    assert single["item_code"] == "synth-shop:synth-item-a"
    assert single["item_url"] == "https://item.rakuten.co.jp/synth-shop/synth-item-a/"
    assert single["multi_sku"] is False and single["required_title_tokens"] == [
        "SYN-100A"
    ]
    assert by_id["synthetic-variant"]["sku_variant_id"] == "02"
    assert "VARIANT_ID_IN_URL" in by_id["synthetic-variant"]["multi_sku_reasons"]
    assert (
        "VARIANT_TEXT_SELECTION" in by_id["synthetic-shared-page"]["multi_sku_reasons"]
    )
    assert by_id["synthetic-shared-page"]["seller_shop_consistent"] is True
    keys = set(rpr._walk_keys(document))
    assert not keys & rpr.API_VALUE_KEYS


def test_plan_over_the_repository_catalog_is_offline_and_price_free():
    raw = (
        ROOT / "changes/reader-purchase-support-v1/purchase-support.v1.json"
    ).read_bytes()
    catalog = json.loads(raw)
    document = rpr.build_plan(catalog, rpr.sha256_hex(raw))
    covered = {e["offer_id"] for e in document["entries"]} | {
        s["offer_id"] for s in document["skipped"]
    }
    assert covered == {o["offer_id"] for o in catalog["offers"]}
    assert document["entries"], "the repository catalog links Rakuten item pages"
    for item in document["entries"]:
        if "variantId=" in item["merchant_url"]:
            assert item["multi_sku"] is True
    assert not set(rpr._walk_keys(document)) & rpr.API_VALUE_KEYS


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda p: p["entries"][0].__setitem__("price_yen", 1),
            "PLAN_CONTAINS_API_VALUE_FIELD",
        ),
        (
            lambda p: p["entries"][0].__setitem__("reference_price", None),
            "PLAN_CONTAINS_API_VALUE_FIELD",
        ),
        (
            lambda p: p["entries"][2].update(multi_sku=False, multi_sku_reasons=[]),
            "PLAN_ENTRY_BINDING_INVALID",
        ),
        (
            lambda p: p["entries"][1].__setitem__("item_code", "synth-shop:other"),
            "PLAN_ENTRY_BINDING_INVALID",
        ),
        (
            lambda p: p["entries"][1].__setitem__("required_title_tokens", []),
            "PLAN_ENTRY_INVALID",
        ),
        (
            lambda p: p["entries"].append(deepcopy(p["entries"][1])),
            "PLAN_OFFER_DUPLICATE",
        ),
    ],
)
def test_plan_validation_refuses_value_fields_and_unsafe_bindings(mutate, code):
    document = plan()
    mutate(document)
    with pytest.raises(rpr.RefreshError, match=code):
        rpr.validate_plan(document)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_single_sku_match_sets_price_tax_state_and_a_24h_cache():
    result = matched_entry()
    assert result["status"] == "MATCHED"
    assert (
        result["price_yen"],
        result["tax_included"],
        result["postage_included"],
        result["state"],
    ) == (
        12340,
        True,
        True,
        "AVAILABLE",
    )
    assert rpr.parse_time(result["cache_expires_at"]) - rpr.parse_time(
        result["observed_at"]
    ) == timedelta(hours=24)
    ref = result["reference_price"]
    offer = {
        "product_id": "PRD-SYN-100A",
        "product_model": "SYN-100A",
        "variant": "ホワイト・本体単体",
        "variant_id": "synth-item-a",
        "identity_verified": True,
        "condition": "UNKNOWN",
        "state": "AVAILABLE",
        "merchant_url": "https://item.rakuten.co.jp/synth-shop/synth-item-a/",
        "reference_price": ref,
    }
    product = {"product_id": "PRD-SYN-100A", "exact_model": "SYN-100A"}
    assert (
        reference_price(offer, product, T0 + timedelta(hours=1))["amount_yen"] == 12340
    )
    assert reference_price(offer, product, T0 + timedelta(hours=24)) is None


def test_tax_flag_1_is_tax_excluded_and_never_a_reference_price():
    result = matched_entry(taxFlag=1)
    assert result["status"] == "MATCHED" and result["tax_included"] is False
    assert result["reference_price"] is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"itemCode": "synth-shop:synth-item-z"}, "ITEM_CODE_MISMATCH"),
        ({"shopCode": "other-shop"}, "SHOP_CODE_MISMATCH"),
        (
            {"itemUrl": "https://item.rakuten.co.jp/synth-shop/synth-item-z/"},
            "ITEM_URL_MISMATCH",
        ),
        (
            {"itemUrl": "https://example.com/synth-shop/synth-item-a/"},
            "ITEM_URL_MISMATCH",
        ),
        ({"itemName": "シンセ 卓上機 SYN-100AX ホワイト"}, "TITLE_TOKEN_MISSING"),
        (
            {"itemName": "シンセ 卓上機 SYN-100A 分岐水栓セット"},
            "TITLE_FORBIDDEN_TOKEN",
        ),
    ],
)
def test_identity_mismatch_carries_no_price_and_no_state(changes, reason):
    result = matched_entry(**changes)
    assert result["status"] == "IDENTITY_MISMATCH" and reason in result["reasons"]
    assert result["price_yen"] is None and result["tax_included"] is None
    assert result["state"] is None and result["reference_price"] is None
    assert rpr.carries_values(result) is False


def test_multiple_rows_are_an_identity_mismatch():
    result = rpr.classify_observation(
        entry("synthetic-single"), 200, body_for(row(), row()), T0
    )
    assert result["status"] == "IDENTITY_MISMATCH" and result["reasons"] == [
        "MULTIPLE_ROWS"
    ]


@pytest.mark.parametrize(
    ("offer_id", "response", "reason"),
    [
        ("synthetic-variant", row("row_variant"), "VARIANT_ID_IN_URL"),
        ("synthetic-single", row(itemPriceMax3=15000), "PURCHASABLE_PRICE_RANGE"),
        (
            "synthetic-single",
            {k: v for k, v in row().items() if k != "itemPriceMin3"},
            "PURCHASABLE_PRICE_RANGE",
        ),
    ],
)
def test_multi_sku_pages_never_receive_an_api_price(offer_id, response, reason):
    result = rpr.classify_observation(entry(offer_id), 200, body_for(response), T0)
    assert result["status"] == "MULTI_SKU_NO_PRICE" and reason in result["reasons"]
    assert (
        result["price_yen"] is None
        and result["reference_price"] is None
        and result["state"] == "UNKNOWN"
    )


def test_shared_sales_page_text_forces_multi_sku_even_without_variant_id():
    shared = entry("synthetic-shared-page")
    response = row(
        itemCode=shared.item_code,
        shopCode=shared.shop_code,
        itemUrl=shared.item_url,
        itemName="SYN-300C 本体",
    )
    result = rpr.classify_observation(shared, 200, body_for(response), T0)
    assert result["status"] == "MULTI_SKU_NO_PRICE" and result["price_yen"] is None


def test_availability_0_is_sold_out_without_price():
    result = matched_entry(availability=0)
    assert (
        result["status"],
        result["state"],
        result["price_yen"],
        result["tax_included"],
    ) == ("SOLD_OUT", "SOLD_OUT", None, None)


@pytest.mark.parametrize(("status", "body"), [(404, None), (200, body_for())])
def test_not_found_is_pending_with_unknown_state(status, body):
    result = rpr.classify_observation(entry("synthetic-single"), status, body, T0)
    assert (result["status"], result["state"], result["price_yen"]) == (
        "NOT_FOUND_PENDING",
        "UNKNOWN",
        None,
    )


@pytest.mark.parametrize("status", [0, 429, 500, 502, 503])
def test_throttling_server_and_transport_failures_write_no_values(status):
    result = rpr.classify_observation(
        entry("synthetic-single"), status, body_for(row()), T0
    )
    assert result["status"] == "REQUEST_FAILED" and rpr.carries_values(result) is False


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "RAKUTEN_WRONG_PARAMETER"),
        (401, "RAKUTEN_AUTH_REJECTED"),
        (403, "RAKUTEN_AUTH_REJECTED"),
    ],
)
def test_parameter_and_authentication_errors_abort_the_run(status, code):
    with pytest.raises(rpr.RefreshError, match=code):
        rpr.classify_observation(entry("synthetic-single"), status, None, T0)


@pytest.mark.parametrize(
    "body",
    [
        body_for(row(taxFlag=2)),
        body_for(row(itemPrice=True)),
        body_for(row(itemPrice=0)),
        '{"items": [], "items": []}',
        '{"items": [{"itemPrice": NaN}]}',
        "not json",
        None,
    ],
)
def test_malformed_success_responses_are_request_failures(body):
    result = rpr.classify_observation(entry("synthetic-single"), 200, body, T0)
    assert result["status"] == "REQUEST_FAILED" and rpr.carries_values(result) is False


# ---------------------------------------------------------------------------
# Client and credentials
# ---------------------------------------------------------------------------


class FakeTransport:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def get(self, *, host, path, headers, max_bytes):
        self.calls.append(
            {
                "host": host,
                "path": path,
                "headers": dict(headers),
                "max_bytes": max_bytes,
            }
        )
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def ok(text, content_type="application/json;charset=UTF-8"):
    return HttpResult(200, (("Content-Type", content_type),), text.encode("utf-8"))


def client(transport, **kwargs):
    return PriceRefreshClient(
        transport, RefreshCredentials(APP_ID, ACCESS_KEY), clock=lambda: T0, **kwargs
    )


def test_client_sends_access_key_as_header_and_no_affiliate_id():
    transport = FakeTransport([ok(body_for(row()))])
    fetched = client(transport).fetch("synth-shop:synth-item-a")
    call = transport.calls[0]
    assert call["host"] == "openapi.rakuten.co.jp" and call["max_bytes"] == 4_000_000
    assert call["headers"]["accessKey"] == ACCESS_KEY
    assert "affiliateId" not in json.dumps(call)
    assert ACCESS_KEY not in call["path"]
    assert fetched.http_status == 200 and fetched.body is not None


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            HttpResult(302, (("Location", "https://example.com/"),), b""),
            "RAKUTEN_REDIRECT_REFUSED",
        ),
        (
            HttpResult(200, (("Location", "https://example.com/"),), b"{}"),
            "RAKUTEN_REDIRECT_REFUSED",
        ),
        (ok("x" * 4_000_001), "RAKUTEN_RESPONSE_TOO_LARGE"),
        (ok('{"echo": "' + ACCESS_KEY + '"}'), "RAKUTEN_CREDENTIAL_REFLECTED"),
        (ok('{"echo": "' + APP_ID + '"}'), "RAKUTEN_CREDENTIAL_REFLECTED"),
        (
            HttpResult(429, (("X-Debug", ACCESS_KEY),), b""),
            "RAKUTEN_CREDENTIAL_REFLECTED",
        ),
    ],
)
def test_client_aborts_on_redirect_oversize_and_credential_reflection(response, code):
    with pytest.raises(rpr.RefreshError, match=code) as raised:
        client(FakeTransport([response])).fetch("synth-shop:synth-item-a")
    assert ACCESS_KEY not in str(raised.value) and APP_ID not in str(raised.value)


def test_client_drops_error_bodies_and_hides_transport_errors():
    transport = FakeTransport(
        [
            HttpResult(
                429,
                (("Content-Type", "application/json"),),
                json.dumps(RESPONSES["error_429"]).encode(),
            ),
            RuntimeError("GET /?applicationId=" + APP_ID + " failed"),
            ok(body_for(row()), content_type="text/html"),
        ]
    )
    refresh = client(transport, sleep=lambda _s: None)
    throttled = refresh.fetch("synth-shop:synth-item-a")
    broken = refresh.fetch("synth-shop:synth-item-a")
    html = refresh.fetch("synth-shop:synth-item-a")
    assert (throttled.http_status, throttled.body) == (429, None)
    assert (broken.http_status, broken.body) == (0, None)
    assert (html.http_status, html.body) == (200, None)
    assert ACCESS_KEY not in repr(refresh) + repr(
        RefreshCredentials(APP_ID, ACCESS_KEY)
    )


def test_client_paces_requests_at_least_1_1_seconds():
    # Clock reads: before request 1, after response 1, before request 2 (wait), before/after request 2.
    ticks = iter([100.0, 100.2, 100.3, 101.3, 101.5])
    sleeps = []
    refresh = client(
        FakeTransport([ok(body_for(row())), ok(body_for(row()))]),
        monotonic=lambda: next(ticks),
        sleep=sleeps.append,
    )
    refresh.fetch("synth-shop:synth-item-a")
    refresh.fetch("synth-shop:synth-item-a")
    assert len(sleeps) == 1 and sleeps[0] == pytest.approx(1.0)


def write_credentials(root, mode=0o600, **changes):
    directory = root / ".secrets/rakuten-owner-local"
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = directory / "credentials.v1.json"
    document = {
        "schema_version": 1,
        "profile": "OWNER_LOCAL_RAKUTEN_PRODUCTION_API",
        "application_id": APP_ID,
        "access_key": ACCESS_KEY,
        "affiliate_id": "synthetic-affiliate-0001",
        **changes,
    }
    path.write_text(json.dumps(document))
    path.chmod(mode)
    return path


def test_credentials_require_owner_only_file_and_profile(tmp_path):
    root = tmp_path.resolve()
    with pytest.raises(rpr.RefreshError, match="CREDENTIAL_UNAVAILABLE"):
        read_refresh_credentials(root)
    write_credentials(root, mode=0o644)
    with pytest.raises(rpr.RefreshError, match="CREDENTIAL_UNSAFE"):
        read_refresh_credentials(root)
    write_credentials(root, profile="OTHER")
    with pytest.raises(rpr.RefreshError, match="CREDENTIAL_UNSAFE"):
        read_refresh_credentials(root)
    write_credentials(root)
    credentials = read_refresh_credentials(root)
    assert credentials.access_key == ACCESS_KEY and ACCESS_KEY not in repr(
        credentials
    ) + str(credentials)


# ---------------------------------------------------------------------------
# CLI against a temporary owner checkout
# ---------------------------------------------------------------------------


@pytest.fixture
def owner(tmp_path):
    root = (tmp_path / "owner").resolve()
    root.mkdir()
    git(root, "init", "-q")
    (root / ".gitignore").write_text(".secrets/\n")
    (root / "README.md").write_text("synthetic owner checkout\n")
    git(root, "add", ".gitignore", "README.md")
    git(root, "commit", "-q", "-m", "init")
    (root / ".secrets").mkdir(mode=0o700)
    write_credentials(root)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan(), ensure_ascii=False, indent=2) + "\n")
    return root, plan_path


def run(argv, capsys, **kwargs):
    kwargs.setdefault("clock", lambda: T0)
    code = cli.main([str(a) for a in argv], **kwargs)
    out = capsys.readouterr()
    text = out.out + out.err
    assert ACCESS_KEY not in text and APP_ID not in text
    return code, [
        json.loads(line) for line in out.out.splitlines() if line.startswith("{")
    ]


def fetch_args(root, plan_path, *extra):
    return ["fetch", "--owner-checkout", root, "--plan", plan_path, *extra]


def test_fetch_refuses_to_run_without_owner_approved_run(owner, capsys):
    root, plan_path = owner
    transport = FakeTransport()
    code, lines = run(fetch_args(root, plan_path), capsys, transport=transport)
    assert code == 2 and lines[-1] == {
        "result": "REFUSED",
        "code": "OWNER_APPROVAL_REQUIRED",
    }
    assert transport.calls == [] and not (root / rpr.PRIVATE_ROOT_RELATIVE).exists()


@pytest.mark.parametrize(
    ("prepare", "extra", "code"),
    [
        (lambda root: None, ["--owner-approved-run", "Bad Run"], "RUN_ID_INVALID"),
        (
            lambda root: (root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID).mkdir(
                parents=True
            ),
            ["--owner-approved-run", RUN_ID],
            "RUN_ALREADY_EXISTS",
        ),
        (
            lambda root: None,
            ["--owner-approved-run", RUN_ID, "--max-requests", "2"],
            "MAX_REQUESTS_EXCEEDED",
        ),
        (
            lambda root: (root / ".gitignore").write_text(""),
            ["--owner-approved-run", RUN_ID],
            "PRIVATE_PATH_NOT_GIT_IGNORED",
        ),
        (
            lambda root: write_credentials(root, mode=0o640),
            ["--owner-approved-run", RUN_ID],
            "CREDENTIAL_UNSAFE",
        ),
    ],
)
def test_fetch_refusals_happen_before_any_request(owner, capsys, prepare, extra, code):
    root, plan_path = owner
    prepare(root)
    transport = FakeTransport()
    result, lines = run(
        fetch_args(root, plan_path, *extra), capsys, transport=transport
    )
    assert result == 2 and lines[-1]["code"] == code
    assert transport.calls == []


def test_fetch_aborts_on_http_400_and_records_the_abort(owner, capsys):
    root, plan_path = owner
    transport = FakeTransport(
        [HttpResult(400, (), json.dumps(RESPONSES["error_400"]).encode())]
    )
    code, lines = run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=transport,
        clock=lambda: T0,
        sleep=lambda _s: None,
    )
    assert (
        code == 2
        and lines[-1]["code"] == "RAKUTEN_WRONG_PARAMETER"
        and len(transport.calls) == 1
    )
    assert (root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID / "abort.v1.json").exists()


def test_fetch_apply_gate_and_purge_keep_values_owner_private(owner, capsys, tmp_path):
    root, plan_path = owner
    # Plan order: synthetic-shared-page, synthetic-single, synthetic-variant.
    transport = FakeTransport(
        [
            HttpResult(
                429,
                (("Content-Type", "application/json"),),
                json.dumps(RESPONSES["error_429"]).encode(),
            ),
            ok(body_for(row())),
            ok(body_for(row("row_variant"))),
        ]
    )
    code, lines = run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=transport,
        clock=lambda: T0,
        sleep=lambda _s: None,
    )
    assert code == 0 and lines[-1]["http_status_counts"] == {"429": 1, "200": 2}
    run_dir = root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID
    raw = sorted((run_dir / "raw").glob("*.json"))
    assert len(raw) == 3 and json.loads(raw[0].read_text())["body"] is None
    for path in [*raw, run_dir / "approval.v1.json"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for directory in (
        root / ".secrets/rakuten-price-refresh",
        run_dir,
        run_dir / "raw",
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700

    now = T0 + timedelta(minutes=10)
    code, lines = run(
        [
            "apply",
            "--owner-checkout",
            root,
            "--run-id",
            RUN_ID,
            "--plan",
            plan_path,
            "--now",
            rpr.iso(now),
        ],
        capsys,
    )
    assert code == 0
    assert lines[-1]["status_counts"] == {
        "MATCHED": 1,
        "MULTI_SKU_NO_PRICE": 1,
        "REQUEST_FAILED": 1,
    }
    assert "12340" not in json.dumps(lines)
    overlay_path = run_dir / "overlay.v1.json"
    assert stat.S_IMODE(overlay_path.stat().st_mode) == 0o600
    assert git(root, "status", "--porcelain", "--untracked-files=all").stdout == b""

    body_path = tmp_path / "body.html"
    body_path.write_text(BODY)
    gate_args = [
        "gate",
        "--owner-checkout",
        root,
        "--run-id",
        RUN_ID,
        "--repository",
        root,
        "--body",
        f"synthetic-comparison={body_path}",
    ]
    code, lines = run([*gate_args, "--now", rpr.iso(T0 + timedelta(hours=1))], capsys)
    assert (code, lines[-1]["result"]) == (0, "GATE_PASS")
    code, lines = run(
        [*gate_args, "--now", rpr.iso(T0 + timedelta(hours=22, seconds=1))], capsys
    )
    assert code == 3 and "OVERLAY_VALUE_EXPIRING" in {
        f["code"] for f in lines[-1]["findings"]
    }
    # --now cannot move the clock backwards past the real clock to bypass expiry.
    code, lines = run(
        [*gate_args, "--now", rpr.iso(T0 + timedelta(hours=1))],
        capsys,
        clock=lambda: T0 + timedelta(hours=23),
    )
    assert code == 3 and "OVERLAY_VALUE_EXPIRING" in {
        f["code"] for f in lines[-1]["findings"]
    }

    overlay = json.loads(overlay_path.read_text())
    leaked = root / "changes/article.html"
    leaked.parent.mkdir()
    leaked.write_text(rpr.inject_body(BODY, overlay).body)
    git(root, "add", "changes/article.html")
    code, lines = run([*gate_args, "--now", rpr.iso(T0 + timedelta(hours=1))], capsys)
    assert code == 3 and "GIT_TRACKED_OVERLAY_VALUE" in {
        f["code"] for f in lines[-1]["findings"]
    }
    clean = (tmp_path / "clean-worktree").resolve()
    clean.mkdir()
    git(clean, "init", "-q")
    other_repository = [*gate_args[:5], "--repository", clean, *gate_args[7:]]
    code, lines = run(
        [*other_repository, "--now", rpr.iso(T0 + timedelta(hours=1))], capsys
    )
    subjects = {
        f["subject"]
        for f in lines[-1]["findings"]
        if f["code"] == "GIT_TRACKED_OVERLAY_VALUE"
    }
    assert code == 3 and any(s.startswith("owner_checkout:") for s in subjects), (
        "owner checkout is always scanned"
    )
    git(root, "rm", "-q", "--cached", "changes/article.html")
    leaked.unlink()

    purge = ["purge-expired", "--owner-checkout", root]
    code, lines = run([*purge, "--now", rpr.iso(T0 + timedelta(hours=1))], capsys)
    assert (
        lines[-1]["runs"][0]["result"] == "NOT_EXPIRED" and (run_dir / "raw").exists()
    )
    approval_path = run_dir / "approval.v1.json"
    published = rpr.record_publish(
        json.loads(approval_path.read_text()),
        overlay,
        candidate_id="d" * 64,
        article_keys=["synthetic-comparison"],
        injected_body_sha256={"synthetic-comparison": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    approval_path.write_text(json.dumps(published))
    code, lines = run(
        [*purge, "--now", rpr.iso(T0 + timedelta(hours=24, minutes=11))], capsys
    )
    report = lines[-1]["runs"][0]
    assert (
        code,
        report["result"],
        report["raw_files_deleted"],
        report["published"],
    ) == (0, "PURGE_PUBLISH_MISSING", 3, True)
    redacted_approval = approval_path.read_text()
    assert "e" * 64 not in redacted_approval and "f" * 64 not in redacted_approval
    assert stat.S_IMODE(approval_path.stat().st_mode) == 0o600
    assert not (run_dir / "raw").exists()
    purged = json.loads(overlay_path.read_text())
    assert (
        purged["schema"] == rpr.PURGED_SCHEMA
        and "12340" not in overlay_path.read_text()
    )
    assert stat.S_IMODE(overlay_path.stat().st_mode) == 0o600
    code, lines = run([*purge, "--now", rpr.iso(T0 + timedelta(hours=30))], capsys)
    # Local values are gone, but no purge publish was recorded: WordPress still serves them.
    assert lines[-1]["runs"][0]["result"] == "PURGE_PUBLISH_MISSING"


def test_apply_refuses_a_plan_other_than_the_approved_one(owner, capsys, tmp_path):
    root, plan_path = owner
    transport = FakeTransport([ok(body_for(row()))] * 3)
    run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=transport,
        clock=lambda: T0,
        sleep=lambda _s: None,
    )
    other = tmp_path / "other-plan.json"
    other.write_text(plan_path.read_text() + "\n")
    code, lines = run(
        [
            "apply",
            "--owner-checkout",
            root,
            "--run-id",
            RUN_ID,
            "--plan",
            other,
            "--now",
            rpr.iso(T0),
        ],
        capsys,
    )
    assert code == 2 and lines[-1]["code"] == "APPROVAL_PLAN_MISMATCH"
    code, lines = run(
        [
            "apply",
            "--owner-checkout",
            root,
            "--run-id",
            RUN_ID,
            "--plan",
            plan_path,
            "--now",
            rpr.iso(T0 + timedelta(hours=24)),
        ],
        capsys,
    )
    assert code == 2 and lines[-1]["code"] == "OBSERVATION_OUTSIDE_CACHE_WINDOW"
    raw_path = sorted(
        (root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID / "raw").glob("*.json")
    )[1]
    record = json.loads(raw_path.read_text())
    apply_args = [
        "apply",
        "--owner-checkout",
        root,
        "--run-id",
        RUN_ID,
        "--plan",
        plan_path,
        "--now",
        rpr.iso(T0 + timedelta(minutes=10)),
    ]
    raw_path.write_text(
        json.dumps({**record, "body": record["body"].replace("12340", "12341")})
    )
    code, lines = run(apply_args, capsys)
    assert code == 2 and lines[-1]["code"] == "RAW_OBSERVATION_TAMPERED"
    raw_path.write_text(json.dumps({**record, "item_code": "synth-shop:synth-item-z"}))
    code, lines = run(apply_args, capsys)
    assert code == 2 and lines[-1]["code"] == "RAW_OBSERVATION_UNBOUND"
    assert not (root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID / "overlay.v1.json").exists()


def test_expired_unpurged_run_blocks_new_fetch_until_purged(owner, capsys):
    root, plan_path = owner
    first = FakeTransport([ok(body_for(row()))] * 3)
    run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=first,
        sleep=lambda _s: None,
    )
    later = lambda: T0 + timedelta(hours=25)  # noqa: E731
    blocked = FakeTransport()
    code, lines = run(
        fetch_args(root, plan_path, "--owner-approved-run", "ks020-synthetic-0002"),
        capsys,
        transport=blocked,
        clock=later,
    )
    assert (
        code == 2
        and lines[-1]["code"] == "EXPIRED_RUN_NOT_PURGED"
        and blocked.calls == []
    )
    code, lines = run(["purge-expired", "--owner-checkout", root], capsys, clock=later)
    assert (
        lines[-1]["runs"][0]["result"] == "PURGED"
        and lines[-1]["runs"][0]["raw_files_deleted"] == 3
    )
    second = FakeTransport([ok(body_for(row()))] * 3)
    code, lines = run(
        fetch_args(root, plan_path, "--owner-approved-run", "ks020-synthetic-0002"),
        capsys,
        transport=second,
        clock=later,
        sleep=lambda _s: None,
    )
    assert code == 0 and len(second.calls) == 3


def test_purge_deletes_raw_values_even_when_run_records_are_invalid(owner, capsys):
    root, plan_path = owner
    run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=FakeTransport([ok(body_for(row()))] * 3),
        sleep=lambda _s: None,
    )
    run_dir = root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID
    overlay_path = run_dir / "overlay.v1.json"
    overlay_path.write_text('{"schema": "tampered"}')
    overlay_path.chmod(0o600)
    code, lines = run(
        ["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys
    )
    report = lines[-1]["runs"][0]
    assert (
        code,
        report["result"],
        report["record_state"],
        report["raw_files_deleted"],
    ) == (0, "PURGED", "UNDATED", 3)
    assert (
        not (run_dir / "raw").exists()
        and json.loads(overlay_path.read_text())["schema"] == rpr.PURGED_SCHEMA
    )


# ---------------------------------------------------------------------------
# Gate refusal paths
# ---------------------------------------------------------------------------


def gate_overlay(**matched_changes):
    matched = {**matched_entry(), **matched_changes}
    return overlay_of(matched)


def run_gate(
    overlay,
    *,
    now=T0 + timedelta(hours=1),
    bodies=None,
    leaks=(),
    approval_record="default",
):
    record = approval() if approval_record == "default" else approval_record
    return codes(
        rpr.gate(
            overlay,
            now=now,
            bodies={"synthetic-comparison": BODY} if bodies is None else bodies,
            tracked_leaks=list(leaks),
            approval=record,
        )
    )


def test_gate_passes_a_fresh_price_free_publication():
    assert run_gate(gate_overlay()) == set()


def test_gate_refuses_values_with_less_than_two_hours_left():
    assert "OVERLAY_VALUE_EXPIRING" in run_gate(
        gate_overlay(), now=T0 + timedelta(hours=22, seconds=1)
    )
    assert "OVERLAY_VALUE_EXPIRING" not in run_gate(
        gate_overlay(), now=T0 + timedelta(hours=21, minutes=59)
    )
    assert "OVERLAY_VALUE_EXPIRING" not in run_gate(
        gate_overlay(), now=T0 + timedelta(hours=22)
    )


def test_gate_refuses_values_older_than_24_hours():
    found = run_gate(gate_overlay(), now=T0 + timedelta(hours=24, seconds=1))
    assert {"OVERLAY_VALUE_OLDER_THAN_24H", "OVERLAY_VALUE_EXPIRING"} <= found


def test_gate_refuses_a_cache_window_longer_than_24_hours():
    overlay = gate_overlay()
    overlay["entries"][0]["cache_expires_at"] = rpr.iso(T0 + timedelta(hours=25))
    assert run_gate(overlay) == {"OVERLAY_INVALID"}


def test_gate_refuses_a_price_without_tax_included():
    assert "TAX_INCLUDED_MISSING" in run_gate(
        gate_overlay(tax_included=None, reference_price=None)
    )


def test_gate_refuses_identity_mismatch_while_a_cta_is_present():
    mismatch = matched_entry(shopCode="other-shop")
    overlay = overlay_of(mismatch)
    assert "IDENTITY_MISMATCH_WITH_CTA" in run_gate(overlay)
    without_cta = re.sub(r'<p><a class="ps-offer-link".*?</a></p>', "", BODY)
    assert "IDENTITY_MISMATCH_WITH_CTA" not in run_gate(
        overlay, bodies={"synthetic-comparison": without_cta}
    )


def test_gate_refuses_tracked_file_leaks():
    assert "GIT_TRACKED_OVERLAY_VALUE" in run_gate(
        gate_overlay(), leaks=["OVERLAY_EXACT_VALUE:worktree:x.html"]
    )


@pytest.mark.parametrize(
    ("record", "code"),
    [
        (None, "APPROVAL_MISSING"),
        ({"publish": {"candidate_id": "b" * 64}}, "APPROVAL_PUBLISH_ALREADY_USED"),
        ({"plan_sha256": "c" * 64}, "APPROVAL_PLAN_MISMATCH"),
        ({"run_id": "ks020-other-run"}, "APPROVAL_RUN_MISMATCH"),
    ],
)
def test_gate_refuses_without_a_single_unused_approval(record, code):
    approval_record = None if record is None else approval(**record)
    assert code in run_gate(gate_overlay(), approval_record=approval_record)


def test_gate_refuses_bodies_that_are_not_price_free_or_lack_the_credit():
    overlay = gate_overlay()
    priced = BODY.replace(
        'data-ps-price-state="UNKNOWN"',
        'data-ps-price-state="UNKNOWN" ' + rpr.ATTR_PRICE_YEN + '="1"',
    )
    assert "BODY_NOT_PRICE_FREE" in run_gate(overlay, bodies={"a": priced})
    assert "RAKUTEN_CREDIT_MISSING" in run_gate(
        overlay, bodies={"a": BODY.replace(CREDIT, "<p>")}
    )
    assert "BODY_ALREADY_INJECTED" in run_gate(
        overlay, bodies={"a": rpr.inject_body(BODY, overlay).body}
    )
    assert "BODIES_REQUIRED" in run_gate(overlay, bodies={})
    unlinked_credit = BODY.replace(
        '<a href="https://developers.rakuten.com/">Supported by Rakuten Developers</a>',
        "Rakuten",
    )
    assert "RAKUTEN_CREDIT_MISSING" in run_gate(overlay, bodies={"a": unlinked_credit})


def test_gate_refuses_a_dated_price_without_the_adjacent_rws_disclaimer_link():
    overlay = gate_overlay()
    link = '<a href="/about-ad-policy/#production-about-rakuten-price">価格・販売可能情報の注意</a>'
    assert link in BODY
    assert "RAKUTEN_PRICE_DISCLAIMER_MISSING" in run_gate(
        overlay, bodies={"a": BODY.replace(link, "")}
    )
    moved = BODY.replace(link, "").replace(CREDIT, CREDIT + link)
    assert "RAKUTEN_PRICE_DISCLAIMER_MISSING" in run_gate(
        overlay, bodies={"a": moved}
    ), "must sit in the price-date line"


# ---------------------------------------------------------------------------
# Injection, hashes, purge and the approval unit
# ---------------------------------------------------------------------------


def test_injection_sets_documented_attributes_time_and_reference_json():
    matched = matched_entry()
    failed = rpr.classify_observation(entry("synthetic-variant"), 503, None, T0)
    overlay = overlay_of(matched, failed)
    result = rpr.inject_body(BODY, overlay)
    assert result.seller_offer_ids == (
        "synthetic-single",
    ) and result.reference_offer_ids == ("synthetic-single",)
    tag = re.search(r'<div class="ps-seller"[^>]*>', result.body).group(0)
    attrs = dict(re.findall(r' ([a-z-]+)="([^"]*)"', tag))
    assert (
        attrs["data-ps-price-yen"] == "12340"
        and attrs["data-ps-tax-included"] == "true"
    )
    assert attrs["data-ps-checked-at"] == matched["observed_at"]
    assert attrs["data-ps-valid-until"] == matched["cache_expires_at"]
    assert (
        attrs["data-ps-state"] == attrs["data-ps-purchasability-state"] == "AVAILABLE"
    )
    assert (
        attrs["data-ps-price-source"] == rpr.API_VERSION_ID
        and attrs["data-ps-overlay-run"] == RUN_ID
    )
    assert attrs["data-ps-price-state"] == "UNKNOWN", (
        "static price_state stays; the theme clock owns CURRENT"
    )
    assert (
        f'<time datetime="{matched["observed_at"]}">2026年9月15日 10:02（日本時間）</time>'
        in result.body
    )
    reference = re.search(r'data-ps-reference-price="([^"]*)"', result.body).group(1)
    assert json.loads(unescape(reference)) == matched["reference_price"]
    assert rpr.body_sha256(result.body) != rpr.body_sha256(BODY)
    assert rpr.price_free_violations(BODY, overlay) == []
    assert {"OVERLAY_RUN_MARKER", "API_PRICE_SOURCE_MARKER"} <= set(
        rpr.price_free_violations(result.body, overlay)
    )
    with pytest.raises(rpr.RefreshError, match="BODY_ALREADY_INJECTED"):
        rpr.inject_body(result.body, overlay)


def test_identity_mismatch_and_failed_requests_inject_nothing():
    overlay = overlay_of(matched_entry(itemCode="synth-shop:other"))
    assert rpr.inject_body(BODY, overlay).body == BODY


def test_runtime_hash_rebinding_matches_the_build_serialization():
    runtime = (FIXTURES / "runtime.synthetic.json").read_bytes()
    unchanged, digest = rpr.inject_runtime(runtime, {})
    assert unchanged == runtime and digest == rpr.sha256_hex(runtime)
    injected_body = rpr.inject_body(BODY, gate_overlay()).body
    payload, digest = rpr.inject_runtime(
        runtime, {"synthetic-comparison": injected_body}
    )
    articles = {a["slug"]: a["body_sha256"] for a in json.loads(payload)["articles"]}
    assert articles == {
        "synthetic-comparison": rpr.body_sha256(injected_body),
        "synthetic-guide": "1" * 64,
    }
    assert digest == rpr.sha256_hex(payload)
    with pytest.raises(rpr.RefreshError, match="RUNTIME_SLUG_UNBOUND"):
        rpr.inject_runtime(runtime, {"missing": BODY})
    with pytest.raises(rpr.RefreshError, match="RUNTIME_NOT_CANONICAL"):
        rpr.inject_runtime(runtime.replace(b'"schema"', b' "schema"', 1), {})
    real = (
        ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.v1.json"
    ).read_bytes()
    assert rpr.inject_runtime(real, {})[0] == real
    functions = (FIXTURES / "functions.synthetic.php").read_text()
    rebound = rpr.rebind_runtime_constant(functions, digest)
    assert f"KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256 = '{digest}';" in rebound
    assert "3" * 64 in rebound and rebound.count(digest) == 1
    with pytest.raises(rpr.RefreshError, match="RUNTIME_CONSTANT_NOT_UNIQUE"):
        rpr.rebind_runtime_constant("<?php\n", digest)
    theme_functions = (
        ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php"
    )
    assert (
        rpr.rebind_runtime_constant(theme_functions.read_text(), digest).count(digest)
        == 1
    )


def test_one_approval_covers_one_publish_and_one_purge_publish():
    overlay = gate_overlay()
    record = approval()
    with pytest.raises(rpr.RefreshError, match="APPROVAL_PURGE_WITHOUT_PUBLISH"):
        rpr.record_purge_publish(record, candidate_id="d" * 64, now=T0)
    with pytest.raises(rpr.RefreshError, match="OVERLAY_VALUE_EXPIRING"):
        rpr.record_publish(
            record,
            overlay,
            candidate_id="d" * 64,
            article_keys=["a"],
            injected_body_sha256={"a": "e" * 64},
            runtime_sha256="f" * 64,
            now=T0 + timedelta(hours=23),
        )
    published = rpr.record_publish(
        record,
        overlay,
        candidate_id="d" * 64,
        article_keys=["a"],
        injected_body_sha256={"a": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    assert published["publish"]["purge_publish_due_by"] == overlay["cache_expires_at"]
    assert {"e" * 64, "f" * 64} <= set(rpr.leak_needles(overlay, published))
    with pytest.raises(rpr.RefreshError, match="APPROVAL_PUBLISH_ALREADY_USED"):
        rpr.record_publish(
            published,
            overlay,
            candidate_id="d" * 64,
            article_keys=["a"],
            injected_body_sha256={"a": "e" * 64},
            runtime_sha256="f" * 64,
            now=T0 + timedelta(hours=2),
        )
    late = rpr.record_purge_publish(
        published, candidate_id="9" * 64, now=T0 + timedelta(hours=24)
    )
    assert late["purge_publish"]["before_expiry"] is False
    purged = rpr.record_purge_publish(
        published, candidate_id="9" * 64, now=T0 + timedelta(hours=21)
    )
    assert purged["purge_publish"]["before_expiry"] is True
    with pytest.raises(rpr.RefreshError, match="APPROVAL_PURGE_ALREADY_USED"):
        rpr.record_purge_publish(
            purged, candidate_id="9" * 64, now=T0 + timedelta(hours=21)
        )
    assert "d" * 64 in rpr.leak_needles(overlay, published), (
        "candidate id hashes injected bodies"
    )
    redacted = rpr.redact_approval(purged)
    assert "e" * 64 not in json.dumps(redacted) and "f" * 64 not in json.dumps(redacted)
    assert "d" * 64 not in json.dumps(redacted)


# ---------------------------------------------------------------------------
# Tracked-file scans
# ---------------------------------------------------------------------------


def test_scan_finds_worktree_untracked_and_index_leaks_but_not_ignored_files(tmp_path):
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text(".secrets/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "init")
    overlay = gate_overlay()
    matched = overlay["entries"][0]
    assert scan_repository_for_overlay(repo, overlay) == []
    (repo / ".secrets").mkdir()
    (repo / ".secrets/overlay.json").write_text(json.dumps(overlay))
    assert scan_repository_for_overlay(repo, overlay) == []
    (repo / "notes.md").write_text("observed " + matched["observed_at"] + "\n")
    assert scan_repository_for_overlay(repo, overlay) == [
        "OVERLAY_EXACT_VALUE:worktree:notes.md"
    ]
    (repo / "notes.md").unlink()
    (repo / "catalog.json").write_text(
        json.dumps({"offers": [{"offer_id": "synthetic-single", "price_yen": 12340}]})
    )
    git(repo, "add", "catalog.json")
    (repo / "catalog.json").write_text(
        json.dumps({"offers": [{"offer_id": "synthetic-single", "price_yen": None}]})
    )
    assert scan_repository_for_overlay(repo, overlay) == [
        "PRICE_JSON_FIELD:index:catalog.json"
    ]
    git(repo, "rm", "-q", "-f", "--cached", "catalog.json")
    (repo / "catalog.json").unlink()
    (repo / "leak.md").write_text("observed " + matched["observed_at"] + "\n")
    git(repo, "add", "leak.md")
    git(repo, "commit", "-q", "-m", "leak")
    git(repo, "rm", "-q", "leak.md")
    git(repo, "commit", "-q", "-m", "remove leak")
    findings = scan_repository_for_overlay(repo, overlay)
    assert (
        len(findings) == 1
        and findings[0].startswith("OVERLAY_EXACT_VALUE:history:")
        and findings[0].endswith(":leak.md")
    )


def test_repository_tracked_files_contain_no_overlay_values_or_injection_markers():
    overlay = gate_overlay()
    assert scan_repository_for_overlay(ROOT, overlay) == []
    for pattern in (
        rpr.ATTR_OVERLAY_RUN + '="[a-z0-9][a-z0-9-]{7,63}"',
        rpr.ATTR_PRICE_SOURCE + '="rakuten_ws_item_search_' + '[0-9]{8}"',
    ):
        result = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "grep",
                "-l",
                "-I",
                "-E",
                "--untracked",
                "-e",
                pattern,
            ],
            capture_output=True,
        )
        assert result.returncode == 1, result.stdout.decode()


# ---------------------------------------------------------------------------
# Tampered overlays, injection targets, leak needles and private paths
# ---------------------------------------------------------------------------


def _overlay_entry(kind):
    if kind == "mismatch":
        return matched_entry(shopCode="other-shop")
    if kind == "sold_out":
        return matched_entry(availability=0)
    if kind == "multi_sku":
        return rpr.classify_observation(
            entry("synthetic-variant"), 200, body_for(row("row_variant")), T0
        )
    return matched_entry()


@pytest.mark.parametrize(
    ("kind", "changes", "code"),
    [
        (
            "mismatch",
            {"price_yen": 12340, "tax_included": True},
            "OVERLAY_PRICE_WITHOUT_MATCH",
        ),
        ("mismatch", {"state": "AVAILABLE"}, "OVERLAY_STATUS_STATE_MISMATCH"),
        (
            "sold_out",
            {"price_yen": 12340, "tax_included": True},
            "OVERLAY_PRICE_WITHOUT_MATCH",
        ),
        ("multi_sku", {"price_yen": 23450}, "OVERLAY_PRICE_WITHOUT_MATCH"),
        ("matched", {"price_yen": 12341}, "OVERLAY_REFERENCE_INVALID"),
    ],
)
def test_tampered_overlays_are_refused_by_gate_and_injection(kind, changes, code):
    overlay = overlay_of(_overlay_entry(kind))
    overlay["entries"][0].update(changes)
    findings = rpr.gate(
        overlay,
        now=T0 + timedelta(hours=1),
        bodies={"synthetic-comparison": BODY},
        tracked_leaks=[],
        approval=approval(),
    )
    assert [(f.code, f.subject) for f in findings] == [("OVERLAY_INVALID", code)]
    with pytest.raises(rpr.RefreshError, match=code):
        rpr.inject_body(BODY, overlay)


def test_gate_checks_the_age_of_sold_out_state_values_too():
    overlay = overlay_of(matched_entry(availability=0))
    assert "OVERLAY_VALUE_EXPIRING" in run_gate(
        overlay, now=T0 + timedelta(hours=22, seconds=1)
    )
    assert "OVERLAY_VALUE_OLDER_THAN_24H" in run_gate(
        overlay, now=T0 + timedelta(hours=24, seconds=1)
    )


def test_reference_price_is_injected_only_next_to_its_own_offer():
    placeholder = '<p class="ps-reference-price" role="status">価格は販売先で確認</p>'
    other = (
        placeholder
        + '<p><a class="ps-offer-link" data-raos-offer-id="synthetic-variant" href="https://item.rakuten.co.jp/synth-shop/synth-item-b/">楽天で見る</a></p>'
    )
    body = BODY.replace(
        "</td></tr></table>", "</td><td>" + other + "</td></tr></table>"
    )
    overlay = gate_overlay()
    result = rpr.inject_body(body, overlay)
    assert result.reference_offer_ids == ("synthetic-single",)
    assert (
        result.body.count(rpr.ATTR_REFERENCE_PRICE + '="') == 1 and other in result.body
    )
    explicit = (
        '<p class="ps-reference-price" role="status" '
        + rpr.ATTR_REFERENCE_OFFER
        + '="synthetic-single">'
    )
    marked = rpr.inject_body(
        BODY.replace(CREDIT, explicit + "価格は販売先で確認</p>" + CREDIT), overlay
    )
    assert marked.body.count(rpr.ATTR_REFERENCE_PRICE + '="') == 2


def test_injection_refuses_bodies_without_a_price_date_or_with_a_price():
    overlay = gate_overlay()
    with pytest.raises(rpr.RefreshError, match="BODY_PRICE_DATE_MISSING"):
        rpr.inject_body(
            BODY.replace('<p class="ps-price-date">', '<p class="ps-date">'), overlay
        )
    priced = BODY.replace(
        'data-ps-price-state="UNKNOWN"',
        'data-ps-price-state="UNKNOWN" ' + rpr.ATTR_PRICE_YEN + '="1"',
    )
    with pytest.raises(rpr.RefreshError, match="BODY_PRICE_CONFLICT"):
        rpr.inject_body(priced, overlay)


def test_scan_finds_a_price_attribute_leak_without_timestamps_and_needles_cover_each_value(
    tmp_path,
):
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text(".secrets/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "init")
    overlay = gate_overlay()
    tag = (
        '<div class="ps-seller" data-ps-offer="synthetic-single" '
        + rpr.ATTR_PRICE_YEN
        + '="12340">'
    )
    (repo / "article.html").write_text(tag + "</div>\n")
    assert scan_repository_for_overlay(repo, overlay) == [
        "PRICE_ATTRIBUTE:worktree:article.html"
    ]
    git(repo, "add", "article.html")
    (repo / "article.html").write_text("price-free\n")
    assert scan_repository_for_overlay(repo, overlay) == [
        "PRICE_ATTRIBUTE:index:article.html"
    ]
    matched = overlay["entries"][0]
    expected = {
        rpr.ATTR_OVERLAY_RUN + '="' + RUN_ID + '"',
        matched["observed_at"],
        matched["cache_expires_at"],
        matched["response_row_sha256"],
    }
    assert expected <= set(rpr.leak_needles(overlay))


def test_client_aborts_on_url_encoded_credential_reflection():
    refresh = PriceRefreshClient(
        FakeTransport([ok('{"echo": "synthetic%2Bkey"}')]),
        RefreshCredentials(APP_ID, "synthetic+key"),
        clock=lambda: T0,
    )
    with pytest.raises(rpr.RefreshError, match="RAKUTEN_CREDENTIAL_REFLECTED"):
        refresh.fetch("synth-shop:synth-item-a")


def test_private_store_refuses_an_ignored_path_that_is_tracked(owner):
    root, _plan_path = owner
    path = root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID / "overlay.v1.json"
    path.parent.mkdir(parents=True, mode=0o700)
    path.write_text("{}\n")
    git(root, "add", "-f", path.relative_to(root).as_posix())
    with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_NOT_GIT_IGNORED"):
        PrivateStore(root).write_json(path, {"schema": "synthetic"}, replace=True)
    assert path.read_text() == "{}\n"


# ---------------------------------------------------------------------------
# Identity-safety review: wrong variant, reused page, "+" models, CTA drift
# ---------------------------------------------------------------------------


def entry_with(**offer_changes):
    catalog = json.loads(CATALOG_BYTES)
    catalog["offers"][0].update(offer_changes)
    raw = json.dumps(catalog).encode()
    document = rpr.build_plan(catalog, rpr.sha256_hex(raw))
    return next(
        e for e in rpr.validate_plan(document) if e.offer_id == "synthetic-single"
    )


def classify_row(plan_entry, response):
    return rpr.classify_observation(plan_entry, 200, body_for(response), T0)


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"itemName": "シンセ 卓上機 SYN-100A ブラック"}, "TITLE_COLOR_CONFLICT"),
        ({"itemName": "シンセ 卓上機 SYN-100A 黒"}, "TITLE_COLOR_CONFLICT"),
        ({"itemName": "SYN-100A 対応 交換用フィルター"}, "TITLE_FORBIDDEN_TOKEN"),
        (
            {"itemName": "SYN-100A ホワイト 整備済み リファービッシュ"},
            "TITLE_FORBIDDEN_TOKEN",
        ),
        ({"itemName": "SYN-100A ホワイト 並行輸入品"}, "TITLE_FORBIDDEN_TOKEN"),
        (
            {"itemName": "シンセ SYN-100A+ ホワイト ステーション付"},
            "TITLE_TOKEN_MISSING",
        ),
        ({"itemName": "シンセ 卓上機 ホワイト 100A SYN"}, "TITLE_TOKEN_MISSING"),
    ],
)
def test_wrong_variant_reused_page_and_plus_model_titles_are_identity_mismatches(
    changes, reason
):
    result = matched_entry(**changes)
    assert result["status"] == "IDENTITY_MISMATCH" and reason in result["reasons"]
    assert rpr.carries_values(result) is False


def test_a_plus_model_never_matches_the_model_without_plus():
    plus = entry_with(product_model="SYN-100A+")
    result = classify_row(plus, row(itemName="シンセ 卓上機 SYN-100A ホワイト"))
    assert (
        result["status"] == "IDENTITY_MISMATCH"
        and "TITLE_TOKEN_MISSING" in result["reasons"]
    )
    assert (
        classify_row(plus, row(itemName="シンセ 卓上機 SYN-100A＋ ホワイト"))["status"]
        == "MATCHED"
    )


def test_seller_bound_to_another_shop_gets_no_price():
    result = classify_row(entry_with(seller_id="rakuten-other-shop"), row())
    assert result["status"] == "IDENTITY_MISMATCH" and result["reasons"] == [
        "SELLER_SHOP_INCONSISTENT"
    ]


def row_without(key):
    return {k: v for k, v in row().items() if k != key}


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (
            row(itemName="シンセ 卓上機 SYN-100A ホワイト ブラック"),
            "TITLE_LISTS_OTHER_COLORS",
        ),
        (row(itemName="シンセ 卓上機 SYN-100A 全２色"), "TITLE_MULTI_VARIANT"),
        (
            row(itemName="シンセ 卓上機 SYN-100A ホワイト ×2 お得"),
            "TITLE_QUANTITY_PACK",
        ),
        (row(itemName="シンセ 卓上機 SYN-100A ホワイト ２台組"), "TITLE_QUANTITY_PACK"),
        (row(itemPriceMax1=15000), "ALL_SKU_PRICE_RANGE"),
        (row_without("itemPriceMin1"), "ALL_SKU_PRICE_RANGE"),
        (
            row(availability=0, itemPriceMin3=None, itemPriceMax3=None),
            "PURCHASABLE_PRICE_RANGE",
        ),
    ],
)
def test_pages_that_may_hold_another_sku_receive_no_price(response, reason):
    result = classify_row(entry("synthetic-single"), response)
    assert result["status"] == "MULTI_SKU_NO_PRICE" and reason in result["reasons"]
    assert (
        result["price_yen"] is None
        and result["tax_included"] is None
        and result["reference_price"] is None
    )


def test_colour_words_inside_other_words_do_not_block_a_match():
    result = matched_entry(
        itemName="シンセ 卓上機 SYN-100A ホワイト グレードアップ ブラックフライデー 面白い"
    )
    assert result["status"] == "MATCHED"
    assert rpr.color_groups("ホワイト×グレー・本体", editorial=True) == {
        "white",
        "gray",
    }
    assert rpr.color_groups("白（SHIRO）・本体", editorial=True) == {"white"}


def test_weak_title_tokens_are_refused_in_plans():
    catalog = json.loads(CATALOG_BYTES)
    catalog["offers"][0]["product_model"] = "シンセ 500"
    raw = json.dumps(catalog).encode()
    document = rpr.build_plan(catalog, rpr.sha256_hex(raw))
    assert {
        "offer_id": "synthetic-single",
        "reason": "TITLE_TOKEN_TOO_WEAK",
    } in document["skipped"]
    edited = plan()
    edited["entries"][1]["required_title_tokens"] = ["500"]
    with pytest.raises(rpr.RefreshError, match="PLAN_TITLE_TOKEN_WEAK"):
        rpr.validate_plan(edited)


AFFILIATE_CTA = (
    'href="https://hb.afl.rakuten.co.jp/ichiba/synthetic/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2F{shop}%2F{item}%2F'
    '&amp;link_type=hybrid_url"'
)
DIRECT_CTA = 'href="https://item.rakuten.co.jp/synth-shop/synth-item-a/"'


def test_gate_accepts_an_affiliate_cta_to_the_observed_item_page():
    body = BODY.replace(
        DIRECT_CTA, AFFILIATE_CTA.format(shop="synth-shop", item="synth-item-a")
    )
    assert run_gate(gate_overlay(), bodies={"a": body}) == set()


@pytest.mark.parametrize(
    ("replacement", "code"),
    [
        (
            'href="https://item.rakuten.co.jp/synth-shop/synth-item-z/"',
            "CTA_TARGET_MISMATCH",
        ),
        (
            AFFILIATE_CTA.format(shop="other-shop", item="synth-item-a"),
            "CTA_TARGET_MISMATCH",
        ),
        ('href="https://maker.example/syn-100a"', "CTA_TARGET_MISMATCH"),
    ],
)
def test_gate_refuses_values_when_the_cta_leads_to_another_page(replacement, code):
    assert code in run_gate(
        gate_overlay(), bodies={"a": BODY.replace(DIRECT_CTA, replacement)}
    )


def test_gate_refuses_values_for_an_offer_whose_cta_cannot_be_checked():
    without_cta = re.sub(r'<p><a class="ps-offer-link".*?</a></p>', "", BODY)
    assert "CTA_TARGET_UNVERIFIED" in run_gate(
        gate_overlay(), bodies={"a": without_cta}
    )


def test_gate_refuses_identity_mismatch_linked_without_the_cta_class():
    overlay = overlay_of(matched_entry(shopCode="other-shop"))
    plain = BODY.replace(
        '<a class="ps-offer-link" data-raos-cta-type="offer" data-raos-offer-id="synthetic-single" ',
        "<a ",
    )
    assert 'class="ps-offer-link"' not in plain
    assert "IDENTITY_MISMATCH_WITH_CTA" in run_gate(overlay, bodies={"a": plain})


def test_gate_refuses_a_tax_excluded_price_until_the_theme_can_label_it():
    overlay = overlay_of(matched_entry(taxFlag=1))
    assert "TAX_EXCLUDED_PRICE_UNSUPPORTED" in run_gate(overlay)


def test_overlay_entries_must_bind_a_canonical_item_page():
    overlay = gate_overlay()
    overlay["entries"][0]["item_url"] = (
        "https://item.rakuten.co.jp/synth-shop/synth-item-a/?variantId=1"
    )
    with pytest.raises(rpr.RefreshError, match="OVERLAY_ENTRY_INVALID"):
        rpr.validate_overlay(overlay)


# ---------------------------------------------------------------------------
# Batch G publisher integration: sold-out CTA, tax-excluded label, purge ids
# ---------------------------------------------------------------------------

THEME_JS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.js"
)


@pytest.mark.parametrize(
    "observation",
    [
        lambda: matched_entry(availability=0),
        lambda: rpr.classify_observation(entry("synthetic-single"), 404, None, T0),
        lambda: rpr.classify_observation(
            entry("synthetic-single"), 200, body_for(), T0
        ),
    ],
    ids=["sold-out", "not-found-404", "not-found-empty"],
)
def test_gate_refuses_sold_out_or_missing_pages_that_keep_a_cta(observation):
    result = observation()
    assert result["status"] in {"SOLD_OUT", "NOT_FOUND_PENDING"}
    overlay = overlay_of(result)
    assert "SOLD_OUT_WITH_CTA" in run_gate(overlay)
    without_cta = re.sub(r'<p><a class="ps-offer-link".*?</a></p>', "", BODY)
    found = run_gate(overlay, bodies={"synthetic-comparison": without_cta})
    assert "SOLD_OUT_WITH_CTA" not in found and "CTA_TARGET_UNVERIFIED" not in found
    plain_link = BODY.replace('<a class="ps-offer-link"', "<a")
    assert "SOLD_OUT_WITH_CTA" in run_gate(overlay, bodies={"a": plain_link})


def test_gate_accepts_a_tax_excluded_price_only_for_a_theme_that_labels_it():
    overlay = overlay_of(matched_entry(taxFlag=1))
    js = THEME_JS.read_text(encoding="utf-8")
    assert rpr.theme_labels_tax_excluded(js)
    findings = codes(
        rpr.gate(
            overlay,
            now=T0 + timedelta(hours=1),
            bodies={"synthetic-comparison": BODY},
            tracked_leaks=[],
            approval=approval(),
            theme_js=js,
        )
    )
    assert findings == set()
    old = js.replace(rpr.TAX_EXCLUDED_LABEL, "本体税込")
    assert "TAX_EXCLUDED_PRICE_UNSUPPORTED" in codes(
        rpr.gate(
            overlay,
            now=T0 + timedelta(hours=1),
            bodies={"synthetic-comparison": BODY},
            tracked_leaks=[],
            approval=approval(),
            theme_js=old,
        )
    )


def test_purge_publish_candidate_ids_are_leak_needles_until_redacted():
    overlay = gate_overlay()
    published = rpr.record_publish(
        approval(),
        overlay,
        candidate_id="d" * 64,
        article_keys=["a"],
        injected_body_sha256={"a": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    purged = rpr.record_purge_publish(
        published, candidate_id="9" * 64, now=T0 + timedelta(hours=2)
    )
    purged["purge_publish"]["base_candidate_id"] = "8" * 64
    purged[rpr.PREPARED_CANDIDATES_KEY] = {"PUBLISH": "7" * 64, "PURGE": "6" * 64}
    assert rpr.validate_approval(purged, RUN_ID) == purged
    assert {"9" * 64, "8" * 64, "7" * 64, "6" * 64} <= set(rpr.leak_needles(overlay, purged))
    # After the purge publish only the purge-side ids go; publish ids wait for purge-expired.
    partial = rpr.redact_purge_candidates(purged)
    assert partial["purge_publish"]["candidate_id"] == "PURGED"
    assert partial["purge_publish"]["base_candidate_id"] == "PURGED"
    assert partial[rpr.PREPARED_CANDIDATES_KEY] == {"PUBLISH": "7" * 64, "PURGE": "PURGED"}
    assert partial["publish"]["candidate_id"] == "d" * 64
    redacted = json.dumps(rpr.redact_approval(purged))
    for value in ("9", "8", "7", "6", "d", "e", "f"):
        assert value * 64 not in redacted
    assert rpr.redact_approval(purged)["purge_publish"]["before_expiry"] is True
    for prepared in ({"OTHER": "7" * 64}, {"PUBLISH": 7}, ["7" * 64]):
        with pytest.raises(rpr.RefreshError, match="APPROVAL_INVALID"):
            rpr.validate_approval({**purged, rpr.PREPARED_CANDIDATES_KEY: prepared}, RUN_ID)


def test_gate_and_fetch_refuse_until_the_purge_publish_or_an_owner_incident_resolution(
    owner, capsys, tmp_path
):
    root, plan_path = owner
    run(
        fetch_args(root, plan_path, "--owner-approved-run", RUN_ID),
        capsys,
        transport=FakeTransport([ok(body_for(row()))] * 3),
        sleep=lambda _s: None,
    )
    code, _lines = run(
        ["apply", "--owner-checkout", root, "--run-id", RUN_ID, "--plan", plan_path,
         "--now", rpr.iso(T0 + timedelta(minutes=10))],
        capsys,
    )
    assert code == 0
    run_dir = root / rpr.PRIVATE_ROOT_RELATIVE / RUN_ID
    approval_path = run_dir / "approval.v1.json"
    overlay = json.loads((run_dir / "overlay.v1.json").read_text())
    published = rpr.record_publish(
        json.loads(approval_path.read_text()),
        overlay,
        candidate_id="d" * 64,
        article_keys=["synthetic-comparison"],
        injected_body_sha256={"synthetic-comparison": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    approval_path.write_text(json.dumps(published))
    later = T0 + timedelta(hours=25)
    code, lines = run(["purge-expired", "--owner-checkout", root], capsys, clock=lambda: later)
    assert (code, lines[-1]["runs"][0]["result"]) == (0, "PURGE_PUBLISH_MISSING")
    assert not (run_dir / "raw").exists()

    second = "ks020-synthetic-0002"
    blocked = FakeTransport()
    code, lines = run(
        fetch_args(root, plan_path, "--owner-approved-run", second),
        capsys,
        transport=blocked,
        clock=lambda: later,
    )
    assert (code, lines[-1]["code"], blocked.calls) == (2, "EXPIRED_RUN_NOT_PURGED", [])

    store = PrivateStore(root)
    observed = later - timedelta(minutes=30)
    store.write_json(
        store.run_directory(second) / "approval.v1.json",
        rpr.new_approval(second, "a" * 64, observed - timedelta(minutes=1)),
    )
    store.write_json(
        store.run_directory(second) / "overlay.v1.json",
        rpr.build_overlay(
            second, "a" * 64, [matched_entry(observed=observed)], observed + timedelta(minutes=5)
        ),
    )
    body_path = tmp_path / "body.html"
    body_path.write_text(BODY)
    gate_args = [
        "gate", "--owner-checkout", root, "--run-id", second, "--repository", root,
        "--body", f"synthetic-comparison={body_path}",
    ]
    code, lines = run(gate_args, capsys, clock=lambda: later)
    assert code == 3 and [(f["code"], f["subject"]) for f in lines[-1]["findings"]] == [
        ("EXPIRED_RUN_NOT_PURGED", RUN_ID)
    ]

    resolve = [
        "resolve-incident", "--owner-checkout", root, "--run-id", RUN_ID,
        "--resolution", "WORDPRESS_POSTS_WITHDRAWN",
    ]
    for extra in ([], ["--owner-confirmed-price-free", second]):
        code, lines = run([*resolve, *extra], capsys, clock=lambda: later)
        assert (code, lines[-1]["code"]) == (2, "OWNER_CONFIRMATION_REQUIRED")
    code, lines = run(
        ["resolve-incident", "--owner-checkout", root, "--run-id", second,
         "--owner-confirmed-price-free", second, "--resolution", "WORDPRESS_POSTS_WITHDRAWN"],
        capsys,
        clock=lambda: later,
    )
    assert (code, lines[-1]["code"]) == (2, "INCIDENT_RESOLUTION_NOT_APPLICABLE")
    code, lines = run(gate_args, capsys, clock=lambda: later)
    assert code == 3, "refusals recorded nothing"

    confirmed = [*resolve, "--owner-confirmed-price-free", RUN_ID]
    # The plugin redaction runs only when a purge publish is finalized: the owner also confirms,
    # with the run's exact text, that the plugin rows and undo options were cleaned by hand.
    for extra in ([], ["--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:" + second]):
        code, lines = run([*confirmed, *extra], capsys, clock=lambda: later)
        assert (code, lines[-1]["code"]) == (2, "PLUGIN_CLEANUP_CONFIRMATION_REQUIRED")
    assert not (run_dir / "incident-resolution.v1.json").exists()
    # Local copies left behind (a candidate frozen from the live page, a preview fixture) are
    # swept by the resolution itself before anything is recorded.
    from raos.adapters.rakuten_price_refresh_client import run_status

    stray = root / ".secrets/wordpress-mcp/owner-direct-v1" / ("c" * 64)
    stray.mkdir(parents=True)
    (stray / "journal.json").write_text(
        json.dumps({"baseline": f'<div data-ps-overlay-run="{RUN_ID}">'})
    )
    fixture = root / ".secrets/wordpress-direct-preview/fixtures/articles/synthetic.html"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(f'<div data-ps-overlay-run="{RUN_ID}">')
    assert run_status(PrivateStore(root), RUN_ID)[0] == "PUBLISHED_NOT_PURGED"
    code, lines = run(
        [*confirmed, "--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:" + RUN_ID],
        capsys,
        clock=lambda: later,
    )
    assert (code, lines[-1]) == (
        0,
        {
            "result": "INCIDENT_RESOLUTION_RECORDED",
            "run_id": RUN_ID,
            "resolution": "WORDPRESS_POSTS_WITHDRAWN",
            "record_state": "PURGED",
            "candidate_directories_deleted": 1,
            "preview_copies_deleted": 1,
        },
    )
    assert not stray.exists() and not fixture.exists()
    for name in ("incident-resolution.v1.json", "plugin-cleanup.v1.json"):
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600
    code, lines = run(gate_args, capsys, clock=lambda: later)
    assert (code, lines[-1]["result"]) == (0, "GATE_PASS")
    code, lines = run(
        [*confirmed, "--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:" + RUN_ID],
        capsys,
        clock=lambda: later,
    )
    assert (code, lines[-1]["code"]) == (2, "INCIDENT_RESOLUTION_NOT_APPLICABLE")


def test_an_invalid_incident_resolution_keeps_the_run_blocked(owner, capsys):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status

    root, _plan_path = owner
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    published = rpr.record_publish(
        approval(),
        gate_overlay(),
        candidate_id="d" * 64,
        article_keys=["a"],
        injected_body_sha256={"a": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    store.write_json(directory / "approval.v1.json", rpr.redact_approval(published))
    store.write_json(
        directory / "overlay.v1.json",
        {"schema": rpr.PURGED_SCHEMA, "run_id": RUN_ID, "purged_at": rpr.iso(T0), "offer_ids": []},
    )
    assert run_status(store, RUN_ID)[0] == "PUBLISHED_NOT_PURGED"
    store.write_json(
        directory / "incident-resolution.v1.json",
        {"schema": "tampered", "run_id": RUN_ID, "resolution": "WORDPRESS_POSTS_WITHDRAWN",
         "recorded_at": rpr.iso(T0)},
    )
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]
    # A valid resolution still needs the plugin cleanup record, and a tampered one blocks.
    store.write_json(
        directory / "incident-resolution.v1.json",
        {"schema": "RAOS_RAKUTEN_PRICE_OVERLAY_INCIDENT_RESOLUTION_V1", "run_id": RUN_ID,
         "resolution": "WORDPRESS_POSTS_WITHDRAWN", "recorded_at": rpr.iso(T0)},
        replace=True,
    )
    assert run_status(store, RUN_ID)[0] == "WORDPRESS_REDACTION_UNCONFIRMED"
    cleanup = {
        "schema": "RAOS_RAKUTEN_PRICE_OVERLAY_PLUGIN_CLEANUP_V1",
        "run_id": RUN_ID,
        "reason": "INCIDENT_RESOLUTION",
        "confirmation": "PLUGIN_COPIES_REMOVED:ks020-synthetic-0002",
        "recorded_at": rpr.iso(T0),
    }
    store.write_json(directory / "plugin-cleanup.v1.json", cleanup)
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]
    cleanup["confirmation"] = "PLUGIN_COPIES_REMOVED:" + RUN_ID
    store.write_json(directory / "plugin-cleanup.v1.json", cleanup, replace=True)
    assert run_status(store, RUN_ID)[0] == "PURGED"
    assert expired_unpurged_runs(store, T0) == []


def test_standalone_gate_reads_the_theme_js_from_the_repository(owner, capsys, tmp_path):
    root, _plan_path = owner
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    store.write_json(directory / "approval.v1.json", approval())
    store.write_json(directory / "overlay.v1.json", overlay_of(matched_entry(taxFlag=1)))
    repository = (tmp_path / "repository").resolve()
    repository.mkdir()
    git(repository, "init", "-q")
    body_path = tmp_path / "body.html"
    body_path.write_text(BODY)
    gate_args = [
        "gate", "--owner-checkout", root, "--run-id", RUN_ID, "--repository", repository,
        "--body", f"synthetic-comparison={body_path}", "--now", rpr.iso(T0 + timedelta(hours=1)),
    ]
    code, lines = run(gate_args, capsys)
    assert code == 3 and {f["code"] for f in lines[-1]["findings"]} == {
        "TAX_EXCLUDED_PRICE_UNSUPPORTED"
    }, "no theme JS in --repository"
    js = repository / cli.THEME_JS_RELATIVE
    js.parent.mkdir(parents=True)
    js.write_text(THEME_JS.read_text(encoding="utf-8"), encoding="utf-8")
    code, lines = run(gate_args, capsys)
    assert (code, lines[-1]["result"]) == (0, "GATE_PASS")
    js.write_text(
        THEME_JS.read_text(encoding="utf-8").replace(rpr.TAX_EXCLUDED_LABEL, "本体税込"),
        encoding="utf-8",
    )
    code, lines = run(gate_args, capsys)
    assert code == 3 and {f["code"] for f in lines[-1]["findings"]} == {
        "TAX_EXCLUDED_PRICE_UNSUPPORTED"
    }


def test_an_interrupted_replace_write_leftover_is_removed_only_when_stale(owner, capsys):
    from raos.adapters.rakuten_price_refresh_client import (
        STALE_TMP_SECONDS,
        expired_unpurged_runs,
        run_status,
    )

    root, _plan_path = owner
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    path = directory / "approval.v1.json"
    store.write_json(path, approval())
    leftover = path.with_name(path.name + ".tmp")

    def interrupted_write(payload):
        descriptor = os.open(leftover, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)

    # A young leftover may belong to a concurrent writer: refused, nothing replaced.
    interrupted_write(json.dumps({"publish": {"candidate_id": "d" * 64}}).encode())
    with pytest.raises(rpr.RefreshError, match="PRIVATE_TMP_BUSY"):
        store.write_json(path, {**approval(), "cache_expires_at": rpr.iso(T0)}, replace=True)
    assert json.loads(path.read_text()) == approval() and leftover.exists()
    # A stale one (interrupted between create and rename) is deleted, never renamed into place.
    stale = leftover.stat().st_mtime - STALE_TMP_SECONDS - 5
    os.utime(leftover, (stale, stale))
    store.write_json(path, {**approval(), "cache_expires_at": rpr.iso(T0)}, replace=True)
    assert not leftover.exists()
    assert json.loads(path.read_text())["cache_expires_at"] == rpr.iso(T0)
    # Anything but a private regular file is refused however old it is.
    leftover.symlink_to(root / "README.md")
    with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_UNSAFE"):
        store.write_json(path, approval(), replace=True)
    leftover.unlink()

    # In a purged run a leftover (it may hold injected hashes) blocks until purge-expired.
    store.write_json(path, approval(), replace=True)
    store.write_json(
        directory / "overlay.v1.json",
        {"schema": rpr.PURGED_SCHEMA, "run_id": RUN_ID, "purged_at": rpr.iso(T0), "offer_ids": []},
    )
    assert run_status(store, RUN_ID)[0] == "PURGED"
    interrupted_write(json.dumps({"publish": {"candidate_id": "d" * 64}}).encode())
    os.utime(leftover, (stale, stale))
    assert run_status(store, RUN_ID)[0] == "REDACTION_PENDING"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]
    code, lines = run(["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys)
    report = lines[-1]["runs"][0]
    assert (code, report["result"], report["record_state"], report["stale_tmp_files_deleted"]) == (
        0,
        "ALREADY_PURGED",
        "REDACTION_PENDING",
        1,
    )
    assert not leftover.exists() and run_status(store, RUN_ID)[0] == "PURGED"


# ---------------------------------------------------------------------------
# Local copies, stale leftovers and missing approvals keep a purged run blocked
# ---------------------------------------------------------------------------

CANDIDATES_RELATIVE = ".secrets/wordpress-mcp/owner-direct-v1"
PREVIEW_RELATIVE = ".secrets/wordpress-direct-preview"
RUN_MARKER = f'<div data-ps-overlay-run="{RUN_ID}">'


def purged_run(root, *, redacted=True):
    """A published run whose local values are purged, with an owner incident resolution and
    plugin cleanup record: PURGED unless a local copy or leftover remains."""
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    published = rpr.record_publish(
        approval(),
        gate_overlay(),
        candidate_id="d" * 64,
        article_keys=["a"],
        injected_body_sha256={"a": "e" * 64},
        runtime_sha256="f" * 64,
        now=T0 + timedelta(hours=1),
    )
    store.write_json(
        directory / "approval.v1.json", rpr.redact_approval(published) if redacted else published
    )
    store.write_json(
        directory / "overlay.v1.json",
        {"schema": rpr.PURGED_SCHEMA, "run_id": RUN_ID, "purged_at": rpr.iso(T0), "offer_ids": []},
    )
    store.write_json(
        directory / "incident-resolution.v1.json",
        {"schema": "RAOS_RAKUTEN_PRICE_OVERLAY_INCIDENT_RESOLUTION_V1", "run_id": RUN_ID,
         "resolution": "WORDPRESS_POSTS_WITHDRAWN", "recorded_at": rpr.iso(T0)},
    )
    store.write_json(
        directory / "plugin-cleanup.v1.json",
        {"schema": "RAOS_RAKUTEN_PRICE_OVERLAY_PLUGIN_CLEANUP_V1", "run_id": RUN_ID,
         "reason": "INCIDENT_RESOLUTION", "confirmation": "PLUGIN_COPIES_REMOVED:" + RUN_ID,
         "recorded_at": rpr.iso(T0)},
    )
    return store, directory


def test_a_purged_run_without_a_readable_approval_stays_undated(owner, capsys):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status

    root, _plan_path = owner
    store, directory = purged_run(root)
    assert run_status(store, RUN_ID)[0] == "PURGED"
    path = directory / "approval.v1.json"
    path.unlink()
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]
    code, lines = run(["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys)
    assert (code, lines[-1]["runs"][0]["result"]) == (0, "UNDATED")
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    path.symlink_to(directory / "missing.v1.json")
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    path.unlink()
    store.write_json(path, ["not", "an", "approval"])
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    path.write_text("{")
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]


@pytest.mark.parametrize(
    ("name", "relative", "content"),
    [
        # An interrupted derived candidate: removed whatever it holds (its injected theme
        # carries only hashes that no record names yet).
        (".staging-" + "c" * 64, "theme/functions.php", "<?php // synthetic\n"),
        ("c" * 64, "preview.json", json.dumps({"fixture": RUN_MARKER})),
        ("c" * 64, "bodies/synthetic-comparison.html", RUN_MARKER),
        ("c" * 64, "candidate.json.tmp", RUN_MARKER),
    ],
)
def test_a_candidate_copy_anywhere_in_its_directory_blocks_until_it_is_swept(
    owner, capsys, name, relative, content
):
    from raos.adapters.rakuten_price_refresh_client import expired_unpurged_runs, run_status

    root, _plan_path = owner
    store, _directory = purged_run(root)
    unrelated = root / CANDIDATES_RELATIVE / ("0" * 64) / "candidate.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('{"synthetic": "price-free"}\n')
    assert run_status(store, RUN_ID)[0] == "PURGED"
    target = root / CANDIDATES_RELATIVE / name / relative
    target.parent.mkdir(parents=True)
    target.write_text(content)
    assert run_status(store, RUN_ID)[0] == "REDACTION_PENDING"
    assert expired_unpurged_runs(store, T0) == [RUN_ID]
    code, lines = run(["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys)
    report = lines[-1]["runs"][0]
    assert (code, report["result"], report["candidate_directories_deleted"]) == (
        0,
        "ALREADY_PURGED",
        1,
    )
    assert not (root / CANDIDATES_RELATIVE / name).exists() and unrelated.exists()
    assert run_status(store, RUN_ID)[0] == "PURGED"


def test_a_candidate_named_only_by_its_recorded_id_is_deleted(owner, capsys):
    from raos.adapters.rakuten_price_refresh_client import run_status

    root, _plan_path = owner
    store, _directory = purged_run(root, redacted=False)
    recorded = root / CANDIDATES_RELATIVE / ("d" * 64)
    recorded.mkdir(parents=True)
    (recorded / "candidate.json").write_text("{}\n")
    assert run_status(store, RUN_ID)[0] == "REDACTION_PENDING"
    code, lines = run(["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys)
    report = lines[-1]["runs"][0]
    assert (code, report["result"], report["record_state"], report["candidate_directories_deleted"]) == (
        0,
        "ALREADY_PURGED",
        "REDACTION_PENDING",
        1,
    )
    assert not recorded.exists() and run_status(store, RUN_ID)[0] == "PURGED"


def test_preview_copies_behind_a_symlink_or_outside_the_preview_directory_are_never_deleted(
    owner, capsys, tmp_path
):
    from raos.adapters.rakuten_price_refresh_client import local_copies, run_status

    root, _plan_path = owner
    store, _directory = purged_run(root)
    sentinel = root / ".secrets/sentinel.txt"
    sentinel.write_text("keep")
    for relative in ("../sentinel.txt", "fixtures/../../sentinel.txt", "theme-1/../../sentinel.txt", "other", ""):
        with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_UNSAFE"):
            store.delete_preview_copy(relative)
    assert sentinel.read_text() == "keep"

    elsewhere = tmp_path / "elsewhere"
    frozen = elsewhere / ("theme-" + "1" * 64) / "functions.php"
    frozen.parent.mkdir(parents=True)
    frozen.write_text(RUN_MARKER)
    (root / PREVIEW_RELATIVE).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_UNSAFE"):
        local_copies(store, RUN_ID, None, None)
    with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_UNSAFE"):
        store.delete_preview_copy("theme-" + "1" * 64)
    assert run_status(store, RUN_ID)[0] == "UNDATED"
    code, lines = run(["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID], capsys)
    assert (code, lines[-1]["code"]) == (2, "PRIVATE_PATH_UNSAFE")
    assert frozen.read_text() == RUN_MARKER


@pytest.mark.parametrize("kind", ["mode-0644", "hardlink"])
def test_a_stale_leftover_that_is_not_a_private_single_link_file_is_refused(owner, kind):
    from raos.adapters.rakuten_price_refresh_client import STALE_TMP_SECONDS

    root, _plan_path = owner
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    path = directory / "approval.v1.json"
    store.write_json(path, approval())
    leftover = path.with_name(path.name + ".tmp")
    linked = directory / "other.v1.json"
    if kind == "mode-0644":
        leftover.write_text("interrupted")
        leftover.chmod(0o644)
    else:
        store.write_json(linked, {"kept": True})
        os.link(linked, leftover)
    stale = leftover.stat().st_mtime - STALE_TMP_SECONDS - 5
    os.utime(leftover, (stale, stale))
    before = path.read_bytes()
    with pytest.raises(rpr.RefreshError, match="PRIVATE_PATH_UNSAFE"):
        store.write_json(path, approval(cache_expires_at=rpr.iso(T0)), replace=True)
    assert leftover.exists() and path.read_bytes() == before
    if kind == "hardlink":
        assert leftover.stat().st_nlink == 2 and json.loads(linked.read_text()) == {"kept": True}
    else:
        assert leftover.read_text() == "interrupted"


def test_resolve_incident_records_nothing_while_a_local_copy_survives_the_sweep(
    owner, capsys, monkeypatch
):
    from raos.adapters.rakuten_price_refresh_client import run_status

    root, _plan_path = owner
    store, directory = purged_run(root)
    (directory / "incident-resolution.v1.json").unlink()
    (directory / "plugin-cleanup.v1.json").unlink()
    assert run_status(store, RUN_ID)[0] == "PUBLISHED_NOT_PURGED"
    stray = root / CANDIDATES_RELATIVE / ("c" * 64) / "journal.json"
    stray.parent.mkdir(parents=True)
    stray.write_text(json.dumps({"baseline": RUN_MARKER}))
    monkeypatch.setattr(PrivateStore, "delete_owner_direct_candidate", lambda self, candidate_id: False)
    code, lines = run(
        ["resolve-incident", "--owner-checkout", root, "--run-id", RUN_ID,
         "--resolution", "WORDPRESS_POSTS_WITHDRAWN", "--owner-confirmed-price-free", RUN_ID,
         "--owner-confirmed-plugin-cleanup", "PLUGIN_COPIES_REMOVED:" + RUN_ID],
        capsys,
        clock=lambda: T0 + timedelta(hours=25),
    )
    assert (code, lines[-1]["code"]) == (2, "LOCAL_COPIES_REMAIN")
    assert stray.exists()
    assert not (directory / "incident-resolution.v1.json").exists()
    assert not (directory / "plugin-cleanup.v1.json").exists()
    assert run_status(store, RUN_ID)[0] == "PUBLISHED_NOT_PURGED"


def test_purge_expired_deletes_a_stale_leftover_of_an_unpurged_run(owner, capsys):
    from raos.adapters.rakuten_price_refresh_client import STALE_TMP_SECONDS, run_status

    root, _plan_path = owner
    store = PrivateStore(root)
    directory = store.run_directory(RUN_ID)
    store.write_json(directory / "approval.v1.json", approval())
    store.write_json(directory / "overlay.v1.json", gate_overlay())
    # Not rewritten by the purge itself: only the run-wide leftover sweep removes it.
    leftover = directory / "incident-resolution.v1.json.tmp"
    os.close(os.open(leftover, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    stale = leftover.stat().st_mtime - STALE_TMP_SECONDS - 5
    os.utime(leftover, (stale, stale))
    assert run_status(store, RUN_ID)[0] == "DATED"
    code, lines = run(
        ["purge-expired", "--owner-checkout", root, "--run-id", RUN_ID, "--include-unexpired"],
        capsys,
    )
    report = lines[-1]["runs"][0]
    assert (code, report["result"], report["record_state"], report["stale_tmp_files_deleted"]) == (
        0,
        "PURGED",
        "DATED",
        1,
    )
    assert not leftover.exists() and run_status(store, RUN_ID)[0] == "PURGED"
