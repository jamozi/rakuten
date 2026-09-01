from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Callable

import pytest

import raos.application.editorial.product_safety_receipts as receipts
from raos.application.editorial.product_safety_query_capture import (
    CAPTURE_BUNDLE_SCHEMA,
    CAPTURE_BUNDLE_VERSION,
    ProductSafetyAdministrativeCaptureEvidence,
    ProductSafetyAdministrativeEvidenceSet,
    ProductSafetyAdministrativeProductEvidence,
    Provider,
    Scope,
)
from raos.application.editorial.product_safety_receipts import (
    CANONICALIZATION_DESCRIPTION,
    PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH,
    PRODUCT_SAFETY_RECEIPTS_SCHEMA,
    PRODUCT_SAFETY_RECEIPTS_VERSION,
    RECEIPT_HASH_FIELDS,
    REQUIRED_AUTHORITY_KINDS,
    REQUIRED_COVERAGE_CAVEAT,
    ProductSafetyOfficialSource,
    ProductSafetyReceiptFailure,
    ProductSafetyRequirement,
    ProductSafetySourceRegistryContext,
    evaluate_product_safety_receipts,
    load_product_safety_receipt_audit,
    product_safety_receipt_sha256,
    require_product_safety_receipts_complete,
)


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
PRODUCT_ID = "PRD-EXAMPLE-MODEL-ABC123"
MODEL_TOKENS = ("ABC-123",)
MANUFACTURER_REF = "SRC-EXAMPLE-MANUFACTURER-SAFETY"
ADMIN_REF = "SRC-METI-EXAMPLE-RECALL"
MANUFACTURER_URL = "https://support.example-maker.jp/safety/abc-123"
ADMIN_URL = "https://www.meti.go.jp/product_safety/recall/abc-123.html"
MANUFACTURER_CAPTURE = "a" * 64
ADMIN_CAPTURE = "b" * 64


def _owner_document() -> dict[str, object]:
    return json.loads(
        (ROOT / PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH).read_text(encoding="utf-8")
    )


def _requirements() -> tuple[ProductSafetyRequirement, ...]:
    return (
        ProductSafetyRequirement(
            product_id=PRODUCT_ID,
            exact_model_tokens=MODEL_TOKENS,
        ),
    )


def _registry() -> ProductSafetySourceRegistryContext:
    return ProductSafetySourceRegistryContext(
        sources={
            MANUFACTURER_REF: ProductSafetyOfficialSource(
                source_ref=MANUFACTURER_REF,
                url=MANUFACTURER_URL,
                authority_kind="MANUFACTURER_OFFICIAL",
                capture_sha256=MANUFACTURER_CAPTURE,
                covered_product_ids=frozenset({PRODUCT_ID}),
            ),
            ADMIN_REF: ProductSafetyOfficialSource(
                source_ref=ADMIN_REF,
                url=ADMIN_URL,
                authority_kind="JAPAN_ADMINISTRATIVE_OFFICIAL",
                capture_sha256=ADMIN_CAPTURE,
                covered_product_ids=frozenset({PRODUCT_ID}),
            ),
        },
        allowed_hosts_by_authority={
            "MANUFACTURER_OFFICIAL": frozenset({"support.example-maker.jp"}),
            "JAPAN_ADMINISTRATIVE_OFFICIAL": frozenset({"www.meti.go.jp"}),
        },
    )


def _receipt(
    authority: str,
    *,
    checked_at: datetime = NOW,
    result: str = "NONE_FOUND",
) -> dict[str, object]:
    if authority == "MANUFACTURER_OFFICIAL":
        source_ref = MANUFACTURER_REF
        source_url = MANUFACTURER_URL
        capture_sha256 = MANUFACTURER_CAPTURE
        query_terms = ["ABC-123 重要なお知らせ リコール"]
    else:
        source_ref = ADMIN_REF
        source_url = ADMIN_URL
        capture_sha256 = ADMIN_CAPTURE
        query_terms = ["ABC-123 リコール 事故情報"]
    material: dict[str, object] = {
        "product_id": PRODUCT_ID,
        "authority_kind": authority,
        "model_tokens": list(MODEL_TOKENS),
        "query_terms": query_terms,
        "official_source_ref": source_ref,
        "official_source_url": source_url,
        "checked_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
        "matched_notice_ids": ["NOTICE-2026-001"] if result == "MATCH" else [],
        "capture_sha256": capture_sha256,
        "coverage_caveat": REQUIRED_COVERAGE_CAVEAT,
    }
    return {**material, "receipt_sha256": product_safety_receipt_sha256(material)}


def _complete_document() -> dict[str, object]:
    document = _owner_document()
    document["receipts"] = [
        _receipt("MANUFACTURER_OFFICIAL"),
        _receipt("JAPAN_ADMINISTRATIVE_OFFICIAL"),
    ]
    return document


def _rehash(receipt: dict[str, object]) -> None:
    receipt["receipt_sha256"] = product_safety_receipt_sha256(
        {field: receipt[field] for field in RECEIPT_HASH_FIELDS}
    )


def _evaluate(document: object):
    return evaluate_product_safety_receipts(
        document,
        requirements=_requirements(),
        registry_context=_registry(),
        now=NOW,
    )


def test_empty_owner_document_is_structurally_valid_and_fail_closed() -> None:
    audit = load_product_safety_receipt_audit(
        ROOT,
        requirements=_requirements(),
        registry_context=_registry(),
        now=NOW,
    )

    assert audit.schema == PRODUCT_SAFETY_RECEIPTS_SCHEMA
    assert audit.complete is False
    assert len(audit.products) == 1
    assert audit.products[0].status == "BLOCKED_MISSING_RECEIPT"
    assert audit.products[0].missing_authority_kinds == REQUIRED_AUTHORITY_KINDS
    with pytest.raises(
        ProductSafetyReceiptFailure,
        match="RAOS_PRODUCT_SAFETY_RECEIPT_INCOMPLETE",
    ):
        require_product_safety_receipts_complete(audit)


def test_document_header_is_closed_and_does_not_accept_owner_status() -> None:
    document = _owner_document()
    assert document == {
        "schema": PRODUCT_SAFETY_RECEIPTS_SCHEMA,
        "version": PRODUCT_SAFETY_RECEIPTS_VERSION,
        "hash_contract": {
            "algorithm": "SHA-256",
            "canonicalization": CANONICALIZATION_DESCRIPTION,
            "fields": list(RECEIPT_HASH_FIELDS),
        },
        "freshness_policy": {
            "maximum_age_days": 30,
            "maximum_future_skew_minutes": 5,
        },
        "required_authority_kinds": list(REQUIRED_AUTHORITY_KINDS),
        "coverage_caveat_policy": {"required_receipt_value": REQUIRED_COVERAGE_CAVEAT},
        "receipts": [],
    }

    document["status"] = "COMPLETE_NONE_FOUND"
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(document)


def test_self_hashed_v1_rows_are_declarations_and_never_derive_complete_status() -> None:
    audit = _evaluate(_complete_document())

    assert audit.complete is False
    assert audit.products[0].status == "BLOCKED_MISSING_RECEIPT"
    assert [receipt.authority_kind for receipt in audit.products[0].receipts] == list(
        REQUIRED_AUTHORITY_KINDS
    )
    assert audit.products[0].verified_authority_kinds == ()
    assert audit.products[0].missing_authority_kinds == REQUIRED_AUTHORITY_KINDS
    with pytest.raises(ProductSafetyReceiptFailure):
        require_product_safety_receipts_complete(audit)


def test_replayed_administrative_set_verifies_only_the_admin_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(_owner_document(), ensure_ascii=False),
        encoding="utf-8",
    )
    provider_scopes: tuple[tuple[Provider, Scope], ...] = (
        ("CAA", "RECALL"),
        ("NITE", "RECALL"),
        ("NITE", "ACCIDENT"),
    )
    captures = tuple(
        ProductSafetyAdministrativeCaptureEvidence(
            product_id=PRODUCT_ID,
            provider=provider,
            scope=scope,
            retrieved_at=NOW,
            result="NONE_FOUND",
            result_count=0,
            notice_ids=(),
            request_material_sha256=str(index) * 64,
            response_raw_sha256=str(index + 3) * 64,
            capture_sha256=str(index + 6) * 64,
        )
        for index, (provider, scope) in enumerate(provider_scopes, 1)
    )
    evidence = ProductSafetyAdministrativeEvidenceSet(
        schema=CAPTURE_BUNDLE_SCHEMA,
        version=CAPTURE_BUNDLE_VERSION,
        plan_sha256="a" * 64,
        portfolio_sha256="b" * 64,
        capture_count=3,
        bundle_sha256="c" * 64,
        evaluated_at=NOW,
        products=(
            ProductSafetyAdministrativeProductEvidence(
                product_id=PRODUCT_ID,
                exact_model_tokens=MODEL_TOKENS,
                status="VERIFIED_NONE_FOUND",
                captures=captures,
                matched_notice_ids=(),
                stale_provider_scopes=(),
            ),
        ),
        complete=True,
    )
    monkeypatch.setattr(
        receipts,
        "verify_product_safety_query_capture_set",
        lambda repository_root, now: evidence,
    )

    audit = load_product_safety_receipt_audit(
        tmp_path,
        requirements=_requirements(),
        registry_context=_registry(),
        now=NOW,
    )

    product = audit.products[0]
    assert audit.complete is False
    assert audit.administrative_bundle_sha256 == "c" * 64
    assert audit.administrative_capture_count == 3
    assert product.verified_authority_kinds == (
        "JAPAN_ADMINISTRATIVE_OFFICIAL",
    )
    assert product.missing_authority_kinds == ("MANUFACTURER_OFFICIAL",)
    assert product.status == "BLOCKED_MISSING_RECEIPT"
    assert product.administrative_capture_sha256s == tuple(
        row.capture_sha256 for row in captures
    )


def test_one_authority_never_completes_the_product() -> None:
    document = _owner_document()
    document["receipts"] = [_receipt("MANUFACTURER_OFFICIAL")]

    product = _evaluate(document).products[0]

    assert product.status == "BLOCKED_MISSING_RECEIPT"
    assert product.missing_authority_kinds == REQUIRED_AUTHORITY_KINDS


def test_duplicate_product_authority_key_is_rejected() -> None:
    document = _complete_document()
    document["receipts"].append(_receipt("MANUFACTURER_OFFICIAL"))

    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(document)


@pytest.mark.parametrize(
    "age",
    [
        timedelta(days=30),
        timedelta(days=30, seconds=1),
    ],
)
def test_declaration_age_cannot_create_or_replace_verified_freshness(
    age: timedelta,
) -> None:
    document = _owner_document()
    document["receipts"] = [
        _receipt("MANUFACTURER_OFFICIAL", checked_at=NOW - age),
        _receipt("JAPAN_ADMINISTRATIVE_OFFICIAL", checked_at=NOW - age),
    ]

    product = _evaluate(document).products[0]

    assert product.status == "BLOCKED_MISSING_RECEIPT"
    assert product.stale_authority_kinds == ()
    assert product.verified_authority_kinds == ()


def test_future_timestamp_skew_boundary_is_fail_closed() -> None:
    allowed = _owner_document()
    allowed["receipts"] = [
        _receipt("MANUFACTURER_OFFICIAL", checked_at=NOW + timedelta(minutes=5)),
        _receipt("JAPAN_ADMINISTRATIVE_OFFICIAL"),
    ]
    assert _evaluate(allowed).complete is False

    blocked = deepcopy(allowed)
    blocked_receipt = blocked["receipts"][0]
    blocked_receipt["checked_at_utc"] = (
        NOW + timedelta(minutes=5, seconds=1)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    _rehash(blocked_receipt)
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(blocked)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("MATCH", "BLOCKED_MATCH_FOUND"),
        ("AMBIGUOUS", "BLOCKED_AMBIGUOUS_RESULT"),
    ],
)
def test_non_clear_result_always_blocks(result: str, expected: str) -> None:
    document = _complete_document()
    document["receipts"][0] = _receipt("MANUFACTURER_OFFICIAL", result=result)

    product = _evaluate(document).products[0]

    assert product.status == expected
    assert product.matched_notice_ids == (
        ("NOTICE-2026-001",) if result == "MATCH" else ()
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.update(receipt_sha256="0" * 64),
        lambda row: row.update(capture_sha256="c" * 64),
        lambda row: row.update(official_source_url="https://evil.example/safety"),
        lambda row: row.update(official_source_ref="SRC-UNKNOWN-OFFICIAL"),
        lambda row: row.update(model_tokens=["ABC-124"]),
        lambda row: row.update(query_terms=["ABC-123 product page"]),
        lambda row: row.update(query_terms=["brand recall"]),
        lambda row: row.update(query_terms=["XABC-1234 recall"]),
        lambda row: row.update(coverage_caveat="検索したので安全情報は存在しません。"),
        lambda row: row.update(product_id="PRD-UNKNOWN-MODEL"),
        lambda row: row.update(checked_at_utc="2026-09-01T12:00:00+00:00"),
    ],
    ids=(
        "bad-receipt-hash",
        "capture-mismatch",
        "source-url-mismatch",
        "source-ref-mismatch",
        "wrong-model-token",
        "missing-safety-intent",
        "generic-brand-query",
        "model-token-substring",
        "dishonest-coverage-caveat",
        "unknown-product",
        "noncanonical-time",
    ),
)
def test_receipt_identity_source_query_and_hash_tampering_is_rejected(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    document = _complete_document()
    receipt = document["receipts"][0]
    mutate(receipt)
    if receipt["receipt_sha256"] != "0" * 64:
        _rehash(receipt)

    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(document)


def test_authority_cannot_be_relabelled_to_use_the_other_official_source() -> None:
    document = _complete_document()
    receipt = document["receipts"][0]
    receipt.update(
        official_source_ref=ADMIN_REF,
        official_source_url=ADMIN_URL,
        capture_sha256=ADMIN_CAPTURE,
    )
    _rehash(receipt)

    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(document)


def test_match_requires_notice_ids_and_none_found_forbids_them() -> None:
    missing_match_id = _complete_document()
    row = missing_match_id["receipts"][0]
    row["result"] = "MATCH"
    _rehash(row)
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(missing_match_id)

    false_none_found = _complete_document()
    row = false_none_found["receipts"][0]
    row["matched_notice_ids"] = ["NOTICE-2026-001"]
    _rehash(row)
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(false_none_found)


def test_registry_context_rejects_unreviewed_or_non_japanese_admin_hosts() -> None:
    registry = _registry()
    sources = dict(registry.sources)
    sources[ADMIN_REF] = ProductSafetyOfficialSource(
        source_ref=ADMIN_REF,
        url="https://recalls.example.org/abc-123",
        authority_kind="JAPAN_ADMINISTRATIVE_OFFICIAL",
        capture_sha256=ADMIN_CAPTURE,
        covered_product_ids=frozenset({PRODUCT_ID}),
    )
    invalid = ProductSafetySourceRegistryContext(
        sources=sources,
        allowed_hosts_by_authority={
            **registry.allowed_hosts_by_authority,
            "JAPAN_ADMINISTRATIVE_OFFICIAL": frozenset({"recalls.example.org"}),
        },
    )

    with pytest.raises(ProductSafetyReceiptFailure):
        evaluate_product_safety_receipts(
            _complete_document(),
            requirements=_requirements(),
            registry_context=invalid,
            now=NOW,
        )


def test_receipt_source_must_explicitly_cover_the_exact_product() -> None:
    registry = _registry()
    sources = dict(registry.sources)
    sources[MANUFACTURER_REF] = ProductSafetyOfficialSource(
        source_ref=MANUFACTURER_REF,
        url=MANUFACTURER_URL,
        authority_kind="MANUFACTURER_OFFICIAL",
        capture_sha256=MANUFACTURER_CAPTURE,
        covered_product_ids=frozenset({"PRD-SIBLING-MODEL-ABC124"}),
    )
    invalid = ProductSafetySourceRegistryContext(
        sources=sources,
        allowed_hosts_by_authority=registry.allowed_hosts_by_authority,
    )

    with pytest.raises(ProductSafetyReceiptFailure):
        evaluate_product_safety_receipts(
            _complete_document(),
            requirements=_requirements(),
            registry_context=invalid,
            now=NOW,
        )


def test_header_policy_and_receipt_fields_are_tamper_evident() -> None:
    header_tamper = _complete_document()
    header_tamper["freshness_policy"]["maximum_age_days"] = 365
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(header_tamper)

    field_tamper = _complete_document()
    field_tamper["receipts"][0]["status"] = "COMPLETE_NONE_FOUND"
    with pytest.raises(ProductSafetyReceiptFailure):
        _evaluate(field_tamper)


def test_requirements_are_unique_and_cannot_vacuously_complete() -> None:
    with pytest.raises(ProductSafetyReceiptFailure):
        evaluate_product_safety_receipts(
            _owner_document(),
            requirements=(),
            registry_context=_registry(),
            now=NOW,
        )

    with pytest.raises(ProductSafetyReceiptFailure):
        evaluate_product_safety_receipts(
            _owner_document(),
            requirements=(*_requirements(), *_requirements()),
            registry_context=_registry(),
            now=NOW,
        )
