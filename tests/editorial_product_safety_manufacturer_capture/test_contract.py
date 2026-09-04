# pyright: reportPrivateUsage=false

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
from typing import Callable

import pytest

import raos.application.editorial.product_safety_manufacturer_capture as capture
from raos.application.editorial.product_safety_manufacturer_capture import (
    EMPTY_EVIDENCE_RELATIVE_PATH,
    MANUAL_REQUIRED_REASON,
    PLAN_RELATIVE_PATH,
    PORTFOLIO_RELATIVE_PATH,
    ProductSafetyManufacturerCaptureFailure,
    ProductSafetyManufacturerCaptureFailureCode,
    ProductSafetyManufacturerHttpResponse,
    ProductSafetyManufacturerQueryRequest,
    capture_product_safety_manufacturer_query,
    describe_product_safety_manufacturer_query,
    load_product_safety_manufacturer_query_plan,
    verify_product_safety_manufacturer_capture_set,
)

import scripts.st1704_product_safety_manufacturer_capture as capture_cli


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
CURRENT_PRODUCT_COUNT = len(
    json.loads((ROOT / PORTFOLIO_RELATIVE_PATH).read_text(encoding="utf-8"))["products"]
)
ACE_PRODUCT = "PRD-PROTECA-TRI-AIR-01541"
NON_ACE_PRODUCT = "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171"


class _FakeTransport:
    def __init__(self, response: ProductSafetyManufacturerHttpResponse) -> None:
        self.response = response
        self.requests: list[ProductSafetyManufacturerQueryRequest] = []

    def execute(
        self, request: ProductSafetyManufacturerQueryRequest
    ) -> ProductSafetyManufacturerHttpResponse:
        self.requests.append(request)
        return self.response


def _response(
    query: str,
    *,
    count: int = 0,
    notices: list[dict[str, object]] | None = None,
    retrieved_at: datetime = NOW,
) -> ProductSafetyManufacturerHttpResponse:
    body = json.dumps(
        {
            "query_model_token": query,
            "result_count": count,
            "notices": [] if notices is None else notices,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return ProductSafetyManufacturerHttpResponse(
        status=200,
        headers=(
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ),
        body=body,
        retrieved_at_utc=retrieved_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _copy_base_contract(repository: Path) -> Path:
    for relative in (
        PLAN_RELATIVE_PATH,
        EMPTY_EVIDENCE_RELATIVE_PATH,
        PORTFOLIO_RELATIVE_PATH,
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return repository


def _write_reviewed_contract(repository: Path) -> Path:
    portfolio = repository / PORTFOLIO_RELATIVE_PATH
    portfolio.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / PORTFOLIO_RELATIVE_PATH, portfolio)
    target = repository / PLAN_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        capture.render_product_safety_manufacturer_query_plan(repository)
    )
    empty = repository / EMPTY_EVIDENCE_RELATIVE_PATH
    empty.write_bytes(
        capture.render_product_safety_manufacturer_empty_evidence(repository)
    )
    return repository


@pytest.fixture
def reviewed_ace_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = capture._ReviewedEndpointSpec(
        contract_id="ACE_NOTICE_JSON_V1",
        manufacturer_code="ACE",
        endpoint="https://safety.example-maker.invalid/api/notices",
        host="safety.example-maker.invalid",
        method="GET",
        query_field="model",
        fixed_query_fields=(("scope", "safety"),),
        response_media_type="application/json",
        parser_version="MANUFACTURER_NOTICE_JSON_V1",
        official_authority_source_ref="SRC-ACE-SAFETY-QUERY",
    )
    monkeypatch.setattr(
        capture,
        "_REVIEWED_ENDPOINT_SPECS",
        {spec.contract_id: spec},
    )


def test_tracked_plan_is_exact_current_product_manual_required_matrix() -> None:
    plan = load_product_safety_manufacturer_query_plan(ROOT)

    assert len(plan.products) == CURRENT_PRODUCT_COUNT
    assert len({row.product_id for row in plan.products}) == CURRENT_PRODUCT_COUNT
    assert all(row.endpoint_review_status == "MANUAL_REQUIRED" for row in plan.products)
    assert all(row.endpoint_contract is None for row in plan.products)
    assert all(
        row.manual_required_reason == MANUAL_REQUIRED_REASON for row in plan.products
    )


def test_unreviewed_product_dry_run_and_capture_fail_closed() -> None:
    described = describe_product_safety_manufacturer_query(
        ROOT, product_id=NON_ACE_PRODUCT
    )

    assert described["status"] == "MANUAL_REQUIRED"
    assert described["reason"] == MANUAL_REQUIRED_REASON
    assert described["credentials_used"] is False
    assert described["production_write"] is False
    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as raised:
        capture_product_safety_manufacturer_query(
            ROOT,
            product_id=NON_ACE_PRODUCT,
            transport=_FakeTransport(_response("82353171")),
        )
    assert (
        raised.value.code is ProductSafetyManufacturerCaptureFailureCode.MANUAL_REQUIRED
    )


def test_empty_tracked_evidence_never_confers_manufacturer_authority() -> None:
    evidence = verify_product_safety_manufacturer_capture_set(ROOT, now=NOW)

    assert evidence.complete is False
    assert evidence.capture_count == 0
    assert len(evidence.products) == CURRENT_PRODUCT_COUNT
    assert {row.status for row in evidence.products} == {"MANUAL_REQUIRED"}
    assert all(row.capture is None for row in evidence.products)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.update(publication_authority="CONTENT_PUBLISH"),
        lambda document: document["matrix"].update(expected_product_count=30),
        lambda document: document["products"][0].update(
            endpoint_review_status="REVIEWED_EXACT_QUERY",
            endpoint_contract_id="UNREVIEWED_ENDPOINT",
            manual_required_reason=None,
        ),
        lambda document: document["products"][0].update(
            query_model_token="GENERIC_BRAND_QUERY"
        ),
        lambda document: document["products"][0].update(
            product_id="PRD-UNREVIEWED-PRODUCT"
        ),
    ],
    ids=(
        "publication-authority",
        "matrix-count",
        "unreviewed-endpoint",
        "generic-query",
        "product-identity",
    ),
)
def test_plan_tampering_is_rejected(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    repository = _copy_base_contract(tmp_path)
    plan_path = repository / PLAN_RELATIVE_PATH
    document = json.loads(plan_path.read_text(encoding="utf-8"))
    mutate(document)
    plan_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as raised:
        load_product_safety_manufacturer_query_plan(repository)
    assert raised.value.code is ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID


def test_portfolio_count_drift_fails_closed_and_can_be_rendered(
    tmp_path: Path,
) -> None:
    repository = _copy_base_contract(tmp_path)
    portfolio_path = repository / PORTFOLIO_RELATIVE_PATH
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    product_id = "PRD-BLUETTI-AORA300-V2"
    portfolio["products"].append(
        {
            "product_id": product_id,
            "official_models": ["AORA 300 V2"],
            "representative_model": "AORA 300 V2",
        }
    )
    portfolio["articles"][0]["product_ids"].append(product_id)
    portfolio_path.write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as raised:
        load_product_safety_manufacturer_query_plan(repository)
    assert raised.value.code is ProductSafetyManufacturerCaptureFailureCode.PLAN_INVALID

    rendered = json.loads(
        capture.render_product_safety_manufacturer_query_plan(repository)
    )
    added = next(row for row in rendered["products"] if row["product_id"] == product_id)
    assert rendered["matrix"]["expected_product_count"] == CURRENT_PRODUCT_COUNT + 1
    assert (
        rendered["portfolio_sha256"]
        != json.loads((ROOT / PLAN_RELATIVE_PATH).read_text(encoding="utf-8"))[
            "portfolio_sha256"
        ]
    )
    assert added["manufacturer_code"] == "BLUETTI_JAPAN"
    assert added["endpoint_review_status"] == "MANUAL_REQUIRED"


def test_tracked_empty_evidence_rejects_owner_authored_capture_or_status(
    tmp_path: Path,
) -> None:
    repository = _copy_base_contract(tmp_path)
    path = repository / EMPTY_EVIDENCE_RELATIVE_PATH
    document = json.loads(path.read_text(encoding="utf-8"))
    document["status"] = "VERIFIED_NONE_FOUND"
    document["evidence"] = [{"result": "NONE_FOUND", "receipt_sha256": "0" * 64}]
    path.write_bytes(capture._canonical_json_bytes(document) + b"\n")

    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as raised:
        load_product_safety_manufacturer_query_plan(repository)
    assert (
        raised.value.code
        is ProductSafetyManufacturerCaptureFailureCode.EMPTY_EVIDENCE_INVALID
    )


def test_reviewed_exact_endpoint_capture_is_private_and_replay_verified(
    tmp_path: Path,
    reviewed_ace_endpoint: None,
) -> None:
    del reviewed_ace_endpoint
    repository = _write_reviewed_contract(tmp_path)
    transport = _FakeTransport(_response("01541"))

    result = capture_product_safety_manufacturer_query(
        repository,
        product_id=ACE_PRODUCT,
        transport=transport,
    )
    evidence = verify_product_safety_manufacturer_capture_set(repository, now=NOW)
    product = next(row for row in evidence.products if row.product_id == ACE_PRODUCT)

    assert len(transport.requests) == 1
    assert transport.requests[0].endpoint == (
        "https://safety.example-maker.invalid/api/notices"
    )
    assert transport.requests[0].host == "safety.example-maker.invalid"
    assert transport.requests[0].method == "GET"
    assert transport.requests[0].query_model_token == "01541"
    assert result.credentials_used is False
    assert result.production_write is False
    assert stat_mode(result.metadata_path) == 0o600
    assert stat_mode(result.request_path) == 0o600
    assert stat_mode(result.response_path) == 0o600
    assert stat_mode(result.metadata_path.parent) == 0o700
    assert stat_mode(result.metadata_path.parent.parent) == 0o700
    assert product.status == "VERIFIED_NONE_FOUND"
    assert product.capture is not None
    assert evidence.capture_count == 1
    assert evidence.complete is False
    reviewed_count = sum(
        row.manufacturer_code == "ACE"
        for row in load_product_safety_manufacturer_query_plan(repository).products
    )
    assert (
        sum(row.status == "BLOCKED_MISSING_CAPTURE" for row in evidence.products)
        == reviewed_count - 1
    )
    assert (
        sum(row.status == "MANUAL_REQUIRED" for row in evidence.products)
        == CURRENT_PRODUCT_COUNT - reviewed_count
    )


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777


@pytest.mark.parametrize(
    ("count", "notices", "expected"),
    [
        (
            1,
            [{"notice_id": "ACE-2026-001", "model_tokens": ["01541"]}],
            "BLOCKED_MATCH_FOUND",
        ),
        (1, [], "BLOCKED_AMBIGUOUS_RESULT"),
    ],
)
def test_match_and_ambiguous_results_are_never_promoted(
    tmp_path: Path,
    reviewed_ace_endpoint: None,
    count: int,
    notices: list[dict[str, object]],
    expected: str,
) -> None:
    del reviewed_ace_endpoint
    repository = _write_reviewed_contract(tmp_path)
    capture_product_safety_manufacturer_query(
        repository,
        product_id=ACE_PRODUCT,
        transport=_FakeTransport(_response("01541", count=count, notices=notices)),
    )

    evidence = verify_product_safety_manufacturer_capture_set(repository, now=NOW)
    product = next(row for row in evidence.products if row.product_id == ACE_PRODUCT)

    assert product.status == expected
    assert evidence.complete is False


def test_stale_capture_and_missing_reviewed_capture_fail_closed(
    tmp_path: Path,
    reviewed_ace_endpoint: None,
) -> None:
    del reviewed_ace_endpoint
    repository = _write_reviewed_contract(tmp_path)
    old = NOW - timedelta(days=30, seconds=1)
    capture_product_safety_manufacturer_query(
        repository,
        product_id=ACE_PRODUCT,
        transport=_FakeTransport(_response("01541", retrieved_at=old)),
    )

    evidence = verify_product_safety_manufacturer_capture_set(repository, now=NOW)
    first = next(row for row in evidence.products if row.product_id == ACE_PRODUCT)
    missing = next(
        row for row in evidence.products if row.product_id == "PRD-ACE-DIFFERENCE-05721"
    )

    assert first.status == "BLOCKED_STALE_CAPTURE"
    assert missing.status == "BLOCKED_MISSING_CAPTURE"


def test_raw_response_tamper_and_permissions_are_rejected(
    tmp_path: Path,
    reviewed_ace_endpoint: None,
) -> None:
    del reviewed_ace_endpoint
    repository = _write_reviewed_contract(tmp_path)
    result = capture_product_safety_manufacturer_query(
        repository,
        product_id=ACE_PRODUCT,
        transport=_FakeTransport(_response("01541")),
    )
    result.response_path.write_bytes(_response("01542").body)
    os.chmod(result.response_path, 0o600)

    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as raised:
        verify_product_safety_manufacturer_capture_set(repository, now=NOW)
    assert (
        raised.value.code
        is ProductSafetyManufacturerCaptureFailureCode.EVIDENCE_SET_INVALID
    )

    result.response_path.write_bytes(_response("01541").body)
    os.chmod(result.response_path, 0o644)
    with pytest.raises(ProductSafetyManufacturerCaptureFailure) as permissions:
        verify_product_safety_manufacturer_capture_set(repository, now=NOW)
    assert (
        permissions.value.code
        is ProductSafetyManufacturerCaptureFailureCode.STORE_UNSAFE
    )


def test_cli_reports_manual_required_without_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert capture_cli.main(["validate"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["product_count"] == CURRENT_PRODUCT_COUNT
    assert validated["manual_required_product_count"] == CURRENT_PRODUCT_COUNT

    assert capture_cli.main(["dry-run", "--product", NON_ACE_PRODUCT]) == 0
    described = json.loads(capsys.readouterr().out)
    assert described["status"] == "MANUAL_REQUIRED"

    assert capture_cli.main(["capture", "--product", NON_ACE_PRODUCT]) == 2
    assert capsys.readouterr().err.strip() == "MANUAL_REQUIRED"
