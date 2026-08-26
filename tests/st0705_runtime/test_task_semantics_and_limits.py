from __future__ import annotations

import json

from raos.domain.ai.output_validation import (
    FailureDisposition,
    FindingCode,
    LocalValidationStatus,
    evaluate_ai_output,
    failure_disposition,
)

from .support import CaseFactory


AIT004_DOCUMENT = {
    "schema_version": "1.0",
    "article": {
        "schema_version": "1.0",
        "locale": "ja-JP",
        "title": "Synthetic article",
        "meta_title": None,
        "meta_description": None,
        "excerpt": None,
        "blocks": [
            {
                "block_key": "paragraph-1",
                "block_type": "paragraph",
                "position": 0,
                "heading_level": None,
                "content": {},
                "product_refs": [],
                "claim_keys": [],
            }
        ],
    },
    "claims": [],
    "product_recommendations": [],
    "warnings": [],
}


def test_ait004_is_not_misclassified_as_content_ast_or_complete_coverage(
    case_factory: CaseFactory,
) -> None:
    report = evaluate_ai_output(case_factory("AIT-004", document=AIT004_DOCUMENT))
    assert report.status is LocalValidationStatus.UNEVALUABLE
    assert FindingCode.COVERAGE_UNAVAILABLE in report.findings
    assert FindingCode.SEMANTIC_CAPABILITY_UNAVAILABLE in report.findings


def test_nested_ait004_version_is_checked_at_the_explicit_hash_version_gate(
    case_factory: CaseFactory,
) -> None:
    document = {
        **AIT004_DOCUMENT,
        "article": {**AIT004_DOCUMENT["article"], "schema_version": "2.0"},
    }
    report = evaluate_ai_output(case_factory("AIT-004", document=document))
    assert report.status is LocalValidationStatus.BLOCKED
    assert FindingCode.HASH_OR_VERSION_MISMATCH in report.findings
    assert failure_disposition(report) is FailureDisposition.TERMINAL_BLOCK


def test_ait005_alignment_fields_absent_from_schema_remain_unevaluable(
    case_factory: CaseFactory,
) -> None:
    document = {"schema_version": "1.0", "claims": []}
    report = evaluate_ai_output(case_factory("AIT-005", document=document))
    assert report.status is LocalValidationStatus.UNEVALUABLE
    assert FindingCode.SEMANTIC_CAPABILITY_UNAVAILABLE in report.findings


def test_scalar_and_order_expectations_are_exact_not_coerced(
    case_factory: CaseFactory,
) -> None:
    document = {
        "schema_version": "1.0",
        "items": [
            {
                "item_id": "item-1",
                "input_rank": 1,
                "input_score": 0.5,
                "explanation": "synthetic",
                "fact_ids": [],
            }
        ],
    }
    scalar = evaluate_ai_output(
        case_factory(
            "AIT-007",
            document=document,
            scalar_values={"input_scores": (1,)},
        )
    )
    assert FindingCode.NUMERIC_OR_SEMANTIC_MISMATCH in scalar.findings
    order = evaluate_ai_output(
        case_factory(
            "AIT-007",
            document=document,
            order_values={"priority_order": (("item-1",), (2,))},
        )
    )
    assert FindingCode.ORDER_MISMATCH in order.findings
    assert scalar.status is order.status is LocalValidationStatus.BLOCKED


def test_four_mib_plus_one_is_terminal_oversize_not_parse_repair(
    case_factory: CaseFactory,
) -> None:
    document = {
        **AIT004_DOCUMENT,
        "article": {
            **AIT004_DOCUMENT["article"],
            "blocks": [
                {
                    "block_key": "paragraph-1",
                    "block_type": "paragraph",
                    "position": 0,
                    "heading_level": None,
                    "content": {"padding": ""},
                    "product_refs": [],
                    "claim_keys": [],
                }
            ],
        },
    }
    compact = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    target = 4 * 1024 * 1024 + 1
    document["article"]["blocks"][0]["content"]["padding"] = "x" * (
        target - len(compact)
    )
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert len(payload) == target
    report = evaluate_ai_output(
        case_factory(
            "AIT-004",
            raw_bytes=payload,
            locator_document=document,
        )
    )
    assert report.status is LocalValidationStatus.BLOCKED
    assert report.findings == (FindingCode.OUTPUT_TOO_LARGE,)
    assert failure_disposition(report) is FailureDisposition.TERMINAL_BLOCK
