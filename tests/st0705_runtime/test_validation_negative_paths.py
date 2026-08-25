from __future__ import annotations

from dataclasses import replace
import json

import pytest

from raos.domain.ai.output_validation import (
    AiOutputValidationInput,
    FailureDisposition,
    FindingCode,
    LocalValidationStatus,
    ResourceValidationStatus,
    SemanticReceiptKind,
    SemanticReceiptStatus,
    evaluate_ai_output,
    failure_disposition,
)

from .conftest import CaseFactory


PASS_DOCUMENT = {
    "schema_version": "1.0",
    "search_intent": "synthetic intent",
    "decision_criteria": [],
    "content_gaps": [],
    "risks": [],
    "source_fact_ids": ["66666666-6666-4666-8666-666666666666"],
}


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b'{"schema_version":"1.0","schema_version":"1.0"}',
        b'{"schema_version":"1.0","x":NaN}',
        b'{"schema_version":"1.0","x":"\xff"}',
    ],
)
def test_invalid_json_is_blocked_and_only_parse_or_schema_is_repairable(
    case_factory: CaseFactory, payload: bytes
) -> None:
    value = case_factory("AIT-001", raw_bytes=payload)
    report = evaluate_ai_output(value)
    assert report.status is LocalValidationStatus.BLOCKED
    assert report.findings == (FindingCode.INVALID_JSON,)
    assert failure_disposition(report) is FailureDisposition.ONE_REPAIR_ELIGIBLE


def test_schema_violation_is_repairable_but_unknown_property_or_enum_is_terminal(
    case_factory: CaseFactory,
) -> None:
    missing = dict(PASS_DOCUMENT)
    missing.pop("search_intent")
    report = evaluate_ai_output(case_factory("AIT-001", document=missing))
    assert report.findings == (FindingCode.SCHEMA_VIOLATION,)
    assert failure_disposition(report) is FailureDisposition.ONE_REPAIR_ELIGIBLE

    unknown = {**PASS_DOCUMENT, "unexpected": True}
    report = evaluate_ai_output(case_factory("AIT-001", document=unknown))
    assert FindingCode.UNKNOWN_PROPERTY_OR_ENUM in report.findings
    assert failure_disposition(report) is FailureDisposition.TERMINAL_BLOCK


@pytest.mark.parametrize(
    "fact_id",
    [
        "66666666-6666-4666-8666-66666666666A",
        "00000000-0000-0000-0000-000000000000",
        "{66666666-6666-4666-8666-666666666666}",
    ],
)
def test_uuid_format_is_canonical_not_only_jsonschema_parseable(
    case_factory: CaseFactory, fact_id: str
) -> None:
    document = {**PASS_DOCUMENT, "source_fact_ids": [fact_id]}
    report = evaluate_ai_output(case_factory("AIT-001", document=document))
    assert report.status is LocalValidationStatus.BLOCKED
    assert FindingCode.SCHEMA_VIOLATION in report.findings


def test_noncanonical_valid_json_never_receives_a_canonical_output_hash(
    case_factory: CaseFactory,
) -> None:
    payload = json.dumps(PASS_DOCUMENT, ensure_ascii=False, indent=2).encode()
    value = case_factory("AIT-001", raw_bytes=payload, locator_document=PASS_DOCUMENT)
    assert value.envelope.output_sha256 is None
    report = evaluate_ai_output(value)
    assert report.status is LocalValidationStatus.BLOCKED
    assert report.findings == (FindingCode.HASH_OR_VERSION_MISMATCH,)
    assert failure_disposition(report) is FailureDisposition.TERMINAL_BLOCK


def test_unknown_or_invalid_fact_is_terminal(
    case_factory: CaseFactory,
) -> None:
    unknown = evaluate_ai_output(
        case_factory("AIT-001", document=PASS_DOCUMENT, omit_resources=True)
    )
    assert FindingCode.UNKNOWN_RESOURCE_ID in unknown.findings
    assert unknown.status is LocalValidationStatus.BLOCKED
    invalid = evaluate_ai_output(
        case_factory(
            "AIT-001",
            document=PASS_DOCUMENT,
            resource_status=ResourceValidationStatus.UNKNOWN,
        )
    )
    assert FindingCode.FACT_SUPPORT_UNAVAILABLE in invalid.findings
    assert invalid.status is LocalValidationStatus.BLOCKED


def test_denied_or_unknown_manifest_input_is_unevaluable_preflight(
    case_factory: CaseFactory,
) -> None:
    for field in ("affiliate_rate", "caller_invented_field"):
        report = evaluate_ai_output(
            case_factory("AIT-001", document=PASS_DOCUMENT, input_fields=(field,))
        )
        assert report.status is LocalValidationStatus.UNEVALUABLE
        assert report.findings == (FindingCode.BINDING_MISMATCH,)
        assert failure_disposition(report) is FailureDisposition.UNEVALUABLE


def test_missing_or_untrusted_semantic_receipt_never_passes(
    case_factory: CaseFactory,
) -> None:
    missing = evaluate_ai_output(
        case_factory(
            "AIT-001",
            document=PASS_DOCUMENT,
            omit_receipt=SemanticReceiptKind.INPUT_TAINT_SCAN,
        )
    )
    assert missing.status is LocalValidationStatus.UNEVALUABLE
    assert missing.findings == (FindingCode.BINDING_MISMATCH,)
    unavailable = evaluate_ai_output(
        case_factory(
            "AIT-001",
            document=PASS_DOCUMENT,
            receipt_statuses={
                SemanticReceiptKind.SENSITIVE_DATA_SCAN: SemanticReceiptStatus.UNEVALUABLE
            },
        )
    )
    assert unavailable.status is LocalValidationStatus.UNEVALUABLE
    assert FindingCode.SEMANTIC_RECEIPT_UNAVAILABLE in unavailable.findings


def test_positive_policy_and_secret_detectors_are_terminal(
    case_factory: CaseFactory,
) -> None:
    contaminated = {
        **PASS_DOCUMENT,
        "search_intent": "[[RAKUTEN_REVIEW_BODY]]",
    }
    report = evaluate_ai_output(case_factory("AIT-001", document=contaminated))
    assert FindingCode.REVIEW_BODY_CONTAMINATION in report.findings
    assert report.status is LocalValidationStatus.BLOCKED

    secret = "sk-" + "x" * 24
    sensitive = {**PASS_DOCUMENT, "search_intent": secret}
    report = evaluate_ai_output(case_factory("AIT-001", document=sensitive))
    assert FindingCode.SECRET_OR_RESTRICTED_DATA in report.findings
    assert secret.encode() not in report.canonical_bytes()
    assert failure_disposition(report) is FailureDisposition.TERMINAL_BLOCK


def test_self_consistent_fake_profile_is_rejected_by_static_registry_anchor(
    passing_input: AiOutputValidationInput,
) -> None:
    fake_profile = replace(passing_input.profile, task_code="ai.fake_profile.v1")
    fake_envelope = replace(passing_input.envelope, task_code="ai.fake_profile.v1")
    fake_manifest = replace(
        passing_input.manifest,
        task_code="ai.fake_profile.v1",
        profile_sha256=fake_profile.profile_sha256,
    )
    value = AiOutputValidationInput(
        profile=fake_profile,
        schema=passing_input.schema,
        manifest=fake_manifest,
        envelope=fake_envelope,
        evaluated_at=passing_input.evaluated_at,
    )
    report = evaluate_ai_output(value)
    assert report.status is LocalValidationStatus.UNEVALUABLE
    assert report.findings == (FindingCode.BINDING_MISMATCH,)
