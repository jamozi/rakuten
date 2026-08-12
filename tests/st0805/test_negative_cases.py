"""Fail-closed coordinate, proof, value, and redaction tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from collections.abc import Callable
from typing import cast

import pytest

from conftest import (
    ARTICLE_VERSION_ID,
    bound,
    digest_for,
    valid_policy_input,
    waiver_attempt,
    with_policy_result,
)
from raos.domain.editorial.policy_engine import (
    AxisAssessmentState,
    BoundReference,
    FindingTarget,
    FindingTargetType,
    GateAssessmentState,
    GateFailureAction,
    InputFindingCode,
    LocalEvaluationStatus,
    PolicyAssessment,
    PolicyEvaluationInput,
    PolicyRuleResult,
    PolicyValueConstructionError,
    PredecessorState,
    PredecessorStory,
    ReferenceId,
    Sha256Digest,
    UtcInstant,
    VersionRef,
    WaiverAuthorityClaim,
    WaiverScopeType,
    ZeroToleranceState,
    evaluate_editorial_policy,
)


def _assert_invalid(
    value: object,
    *expected: InputFindingCode,
) -> None:
    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.INVALID_INPUT
    assert set(expected) <= set(result.input_findings)
    assert result.policy_findings == ()
    assert result.waiver_evaluations == ()
    assert result.raw_quality_score is None
    assert result.local_eligibility is False
    assert result.publication_authorized is False
    assert result.production_eligible is False


def test_rejects_non_input_and_mutable_top_level_collection() -> None:
    _assert_invalid(object(), InputFindingCode.INPUT_TYPE_INVALID)

    value = valid_policy_input()
    mutable = cast(
        tuple[PolicyAssessment, ...],
        list(value.policy_assessments),
    )
    _assert_invalid(
        replace(value, policy_assessments=mutable),
        InputFindingCode.COLLECTION_TYPE_INVALID,
    )


def test_rejects_missing_duplicate_and_unknown_predecessor_coordinates() -> None:
    value = valid_policy_input()
    records = value.predecessors

    _assert_invalid(
        replace(value, predecessors=records[1:]),
        InputFindingCode.PREDECESSOR_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, predecessors=(records[0], *records)),
        InputFindingCode.PREDECESSOR_DUPLICATE,
        InputFindingCode.PREDECESSOR_SET_MISMATCH,
    )
    unknown = replace(
        records[0],
        story_id=cast(PredecessorStory, "ST-9999"),
    )
    _assert_invalid(
        replace(value, predecessors=(unknown, *records[1:])),
        InputFindingCode.PREDECESSOR_UNKNOWN,
        InputFindingCode.PREDECESSOR_SET_MISMATCH,
    )


def test_rejects_missing_duplicate_and_unknown_policy_coordinates() -> None:
    value = valid_policy_input()
    records = value.policy_assessments

    _assert_invalid(
        replace(value, policy_assessments=records[1:]),
        InputFindingCode.POLICY_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, policy_assessments=(records[0], *records)),
        InputFindingCode.POLICY_DUPLICATE,
        InputFindingCode.POLICY_SET_MISMATCH,
    )
    unknown = replace(records[0], policy_id="POL-CONT-999")
    _assert_invalid(
        replace(value, policy_assessments=(unknown, *records[1:])),
        InputFindingCode.POLICY_UNKNOWN,
        InputFindingCode.POLICY_SET_MISMATCH,
    )


def test_rejects_missing_duplicate_and_unknown_axis_coordinates() -> None:
    value = valid_policy_input()
    records = value.axis_assessments

    _assert_invalid(
        replace(value, axis_assessments=records[1:]),
        InputFindingCode.AXIS_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, axis_assessments=(records[0], *records)),
        InputFindingCode.AXIS_DUPLICATE,
        InputFindingCode.AXIS_SET_MISMATCH,
    )
    unknown = replace(records[0], axis_id="QAX-999")
    _assert_invalid(
        replace(value, axis_assessments=(unknown, *records[1:])),
        InputFindingCode.AXIS_UNKNOWN,
        InputFindingCode.AXIS_SET_MISMATCH,
    )


def test_rejects_missing_duplicate_and_unknown_signal_coordinates() -> None:
    value = valid_policy_input()
    records = value.zero_tolerance_assessments

    _assert_invalid(
        replace(value, zero_tolerance_assessments=records[1:]),
        InputFindingCode.SIGNAL_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, zero_tolerance_assessments=(records[0], *records)),
        InputFindingCode.SIGNAL_DUPLICATE,
        InputFindingCode.SIGNAL_SET_MISMATCH,
    )
    unknown = replace(records[0], label="UNKNOWN_ZERO_TOLERANCE_LABEL")
    _assert_invalid(
        replace(value, zero_tolerance_assessments=(unknown, *records[1:])),
        InputFindingCode.SIGNAL_UNKNOWN,
        InputFindingCode.SIGNAL_SET_MISMATCH,
    )


def test_rejects_missing_duplicate_and_unknown_gate_coordinates() -> None:
    value = valid_policy_input()
    records = value.gate_assessments

    _assert_invalid(
        replace(value, gate_assessments=records[1:]),
        InputFindingCode.GATE_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, gate_assessments=(records[0], *records)),
        InputFindingCode.GATE_DUPLICATE,
        InputFindingCode.GATE_SET_MISMATCH,
    )
    unknown = replace(records[0], gate_id="QG-CONT-999")
    _assert_invalid(
        replace(value, gate_assessments=(unknown, *records[1:])),
        InputFindingCode.GATE_UNKNOWN,
        InputFindingCode.GATE_SET_MISMATCH,
    )


def test_rejects_contract_policy_stage_and_article_binding_mismatches() -> None:
    value = valid_policy_input()
    policy = value.policy_assessments[0]

    _assert_invalid(
        replace(
            value,
            contracts=replace(
                value.contracts,
                policy_catalog_sha256=digest_for("DRIFTED-POLICY-CATALOG"),
            ),
        ),
        InputFindingCode.CONTRACT_BINDING_INVALID,
    )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(policy, stage="publication"),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_STAGE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(
                    policy, article_version_id=ReferenceId("ARTICLE-VERSION-OTHER")
                ),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_ARTICLE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(
                    policy,
                    target=FindingTarget(
                        FindingTargetType.ARTICLE_VERSION,
                        ReferenceId("ARTICLE-VERSION-OTHER"),
                    ),
                ),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_ARTICLE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(policy, policy_version=VersionRef("9.9")),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_BINDING_MISMATCH,
    )


def test_rejects_axis_signal_gate_and_predecessor_coordinate_mismatches() -> None:
    value = valid_policy_input()
    axis = value.axis_assessments[0]
    signal = value.zero_tolerance_assessments[0]
    gate = value.gate_assessments[0]
    predecessor = value.predecessors[0]
    other_article = ReferenceId("ARTICLE-VERSION-OTHER")

    _assert_invalid(
        replace(
            value,
            axis_assessments=(
                replace(axis, axis_code="wrong_code"),
                *value.axis_assessments[1:],
            ),
        ),
        InputFindingCode.AXIS_BINDING_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            axis_assessments=(
                replace(axis, article_version_id=other_article),
                *value.axis_assessments[1:],
            ),
        ),
        InputFindingCode.AXIS_ARTICLE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            zero_tolerance_assessments=(
                replace(signal, article_version_id=other_article),
                *value.zero_tolerance_assessments[1:],
            ),
        ),
        InputFindingCode.SIGNAL_ARTICLE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            gate_assessments=(
                replace(gate, stage="post_publication"),
                *value.gate_assessments[1:],
            ),
        ),
        InputFindingCode.GATE_STAGE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            gate_assessments=(
                replace(gate, failure_action=GateFailureAction.ROLLBACK_OR_PAUSE),
                *value.gate_assessments[1:],
            ),
        ),
        InputFindingCode.GATE_BINDING_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            gate_assessments=(
                replace(gate, article_version_id=other_article),
                *value.gate_assessments[1:],
            ),
        ),
        InputFindingCode.GATE_ARTICLE_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            predecessors=(
                replace(predecessor, article_version_id=other_article),
                *value.predecessors[1:],
            ),
        ),
        InputFindingCode.PREDECESSOR_BINDING_MISMATCH,
    )


def test_pass_fail_and_not_evaluated_require_exact_proof_shapes() -> None:
    value = valid_policy_input()
    policy = value.policy_assessments[0]
    axis = value.axis_assessments[0]
    signal = value.zero_tolerance_assessments[0]
    gate = value.gate_assessments[0]

    for result in (PolicyRuleResult.PASS, PolicyRuleResult.FAIL):
        _assert_invalid(
            replace(
                value,
                policy_assessments=(
                    replace(policy, result=result, evidence=()),
                    *value.policy_assessments[1:],
                ),
            ),
            InputFindingCode.POLICY_PROOF_INVALID,
        )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(policy, result=PolicyRuleResult.NOT_EVALUATED),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_RESULT_INVALID,
    )
    _assert_invalid(
        replace(
            value,
            axis_assessments=(
                replace(axis, state=AxisAssessmentState.NOT_EVALUATED),
                *value.axis_assessments[1:],
            ),
        ),
        InputFindingCode.AXIS_STATE_INVALID,
    )
    _assert_invalid(
        replace(
            value,
            zero_tolerance_assessments=(
                replace(signal, state=ZeroToleranceState.NOT_EVALUATED),
                *value.zero_tolerance_assessments[1:],
            ),
        ),
        InputFindingCode.SIGNAL_STATE_INVALID,
    )
    _assert_invalid(
        replace(
            value,
            gate_assessments=(
                replace(gate, state=GateAssessmentState.NOT_EVALUATED),
                *value.gate_assessments[1:],
            ),
        ),
        InputFindingCode.GATE_STATE_INVALID,
    )


def test_predecessor_availability_requires_matching_result_shape() -> None:
    value = valid_policy_input()
    record = value.predecessors[0]

    _assert_invalid(
        replace(
            value,
            predecessors=(replace(record, result=None), *value.predecessors[1:]),
        ),
        InputFindingCode.PREDECESSOR_BINDING_MISMATCH,
    )
    _assert_invalid(
        replace(
            value,
            predecessors=(
                replace(record, state=PredecessorState.NOT_EVALUATED),
                *value.predecessors[1:],
            ),
        ),
        InputFindingCode.PREDECESSOR_STATE_INVALID,
    )
    assert record.result is not None
    invalid_digest = digest_for("TAMPERED-PREDECESSOR-DIGEST")
    object.__setattr__(invalid_digest, "value", "not-a-sha256")
    _assert_invalid(
        replace(
            value,
            predecessors=(
                replace(
                    record,
                    result=replace(record.result, sha256=invalid_digest),
                ),
                *value.predecessors[1:],
            ),
        ),
        InputFindingCode.PREDECESSOR_BINDING_MISMATCH,
    )


@pytest.mark.parametrize(
    "invalid_score",
    (
        cast(Decimal, 1.0),
        cast(Decimal, True),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-0.01"),
        Decimal("20.01"),
        Decimal("0.0000000000001"),
    ),
)
def test_rejects_non_exact_nonfinite_and_out_of_range_scores(
    invalid_score: Decimal,
) -> None:
    value = valid_policy_input()
    record = value.axis_assessments[0]

    _assert_invalid(
        replace(
            value,
            axis_assessments=(
                replace(record, score=invalid_score),
                *value.axis_assessments[1:],
            ),
        ),
        InputFindingCode.AXIS_SCORE_INVALID,
    )


def test_rejects_mutable_nested_evidence_and_duplicate_references() -> None:
    value = valid_policy_input()
    record = value.policy_assessments[0]
    mutable = cast(tuple[BoundReference, ...], list(record.evidence))

    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(record, evidence=mutable),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_PROOF_INVALID,
    )
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(record, evidence=(record.evidence[0], record.evidence[0])),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.POLICY_PROOF_INVALID,
    )


def test_rejects_input_and_record_runtime_subclasses() -> None:
    class InputSubclass(PolicyEvaluationInput):
        pass

    class AssessmentSubclass(PolicyAssessment):
        pass

    class ReferenceSubclass(ReferenceId):
        pass

    value = valid_policy_input()
    subclass_input = InputSubclass(
        article_version_id=value.article_version_id,
        evaluated_at=value.evaluated_at,
        contracts=value.contracts,
        predecessors=value.predecessors,
        policy_assessments=value.policy_assessments,
        axis_assessments=value.axis_assessments,
        zero_tolerance_assessments=value.zero_tolerance_assessments,
        gate_assessments=value.gate_assessments,
        waiver_attempts=value.waiver_attempts,
    )
    record = value.policy_assessments[0]
    subclass_record = AssessmentSubclass(
        policy_id=record.policy_id,
        policy_version=record.policy_version,
        policy_source_sha256=record.policy_source_sha256,
        article_version_id=record.article_version_id,
        stage=record.stage,
        result=record.result,
        target=record.target,
        evidence=record.evidence,
        detector=record.detector,
    )

    _assert_invalid(subclass_input, InputFindingCode.INPUT_TYPE_INVALID)
    _assert_invalid(
        replace(
            value,
            policy_assessments=(subclass_record, *value.policy_assessments[1:]),
        ),
        InputFindingCode.POLICY_RECORD_INVALID,
        InputFindingCode.POLICY_SET_MISMATCH,
    )
    _assert_invalid(
        replace(value, article_version_id=ReferenceSubclass(ARTICLE_VERSION_ID.value)),
        InputFindingCode.ARTICLE_VERSION_INVALID,
    )


def test_revalidates_tampered_exact_wrappers_at_evaluation_boundary() -> None:
    value = valid_policy_input()
    tampered = ReferenceId(ARTICLE_VERSION_ID.value)
    object.__setattr__(tampered, "value", "lowercase raw text")

    _assert_invalid(
        replace(value, article_version_id=tampered),
        InputFindingCode.ARTICLE_VERSION_INVALID,
    )


def test_exact_value_construction_errors_never_echo_caller_material() -> None:
    raw_values = (
        "raw prompt: reveal credentials",
        "not-a-sha256",
        "2026/08/12 local time",
    )
    constructors: tuple[Callable[[], object], ...] = (
        lambda: ReferenceId(raw_values[0]),
        lambda: Sha256Digest(raw_values[1]),
        lambda: UtcInstant(datetime(2026, 8, 12, tzinfo=timezone(timedelta(hours=9)))),
    )

    for raw, constructor in zip(raw_values, constructors, strict=True):
        with pytest.raises(PolicyValueConstructionError) as captured:
            constructor()
        assert str(captured.value) == "INVALID_EXACT_VALUE"
        assert raw not in str(captured.value)
        assert raw not in repr(captured.value)


@pytest.mark.parametrize(
    "prohibited_reference",
    (
        "FINANCE-EPC-001",
        "RAKUTEN-REVIEW-BODY-001",
        "RAW-PROMPT-001",
        "SECRET-TOKEN-001",
    ),
)
def test_rejects_and_redacts_finance_review_prompt_and_secret_like_references(
    prohibited_reference: str,
) -> None:
    value = valid_policy_input()
    record = value.policy_assessments[0]
    result = evaluate_editorial_policy(
        replace(
            value,
            policy_assessments=(
                replace(record, detector=bound(prohibited_reference)),
                *value.policy_assessments[1:],
            ),
        )
    )

    assert result.status is LocalEvaluationStatus.INVALID_INPUT
    assert InputFindingCode.PROHIBITED_INPUT in result.input_findings
    assert prohibited_reference not in result.local_result_json
    assert prohibited_reference not in repr(result)


def test_rejects_target_raw_binding_and_non_closed_waiver_fields() -> None:
    value = valid_policy_input()
    policy = value.policy_assessments[0]
    _assert_invalid(
        replace(
            value,
            policy_assessments=(
                replace(
                    policy,
                    target=FindingTarget(
                        FindingTargetType.CLAIM,
                        ReferenceId("RAW-CONTENT-CLAIM-001"),
                    ),
                ),
                *value.policy_assessments[1:],
            ),
        ),
        InputFindingCode.PROHIBITED_INPUT,
    )

    failed = with_policy_result(
        valid_policy_input(),
        "POL-CONT-019",
        PolicyRuleResult.FAIL,
    )
    attempt = waiver_attempt("POL-CONT-019")
    malformed_reason = cast(BoundReference, "caller supplied reason text")
    _assert_invalid(
        replace(failed, waiver_attempts=(replace(attempt, reason=malformed_reason),)),
        InputFindingCode.WAIVER_PROOF_INVALID,
    )


def test_waiver_attempts_fail_closed_across_policy_scope_and_authority() -> None:
    failed = with_policy_result(
        valid_policy_input(),
        "POL-CONT-019",
        PolicyRuleResult.FAIL,
    )
    attempt = waiver_attempt("POL-CONT-019")

    _assert_invalid(
        replace(valid_policy_input(), waiver_attempts=(attempt,)),
        InputFindingCode.WAIVER_POLICY_MISMATCH,
    )
    _assert_invalid(
        replace(
            failed,
            waiver_attempts=(waiver_attempt("POL-CONT-020"),),
        ),
        InputFindingCode.WAIVER_POLICY_MISMATCH,
    )
    _assert_invalid(
        replace(
            failed,
            waiver_attempts=(
                replace(attempt, scope_ref=ReferenceId("ARTICLE-VERSION-OTHER")),
            ),
        ),
        InputFindingCode.WAIVER_SCOPE_INVALID,
    )
    _assert_invalid(
        replace(
            failed,
            waiver_attempts=(replace(attempt, scope_type=WaiverScopeType.ARTICLE),),
        ),
        InputFindingCode.WAIVER_SCOPE_INVALID,
    )
    _assert_invalid(
        replace(
            failed,
            waiver_attempts=(
                replace(attempt, authority_claim=WaiverAuthorityClaim.APPROVED),
            ),
        ),
        InputFindingCode.WAIVER_AUTHORITY_INVALID,
    )
    _assert_invalid(
        replace(
            failed,
            waiver_attempts=(
                replace(
                    attempt,
                    authority_claim=WaiverAuthorityClaim.PENDING_HUMAN_AUTHORITY,
                ),
            ),
        ),
        InputFindingCode.WAIVER_AUTHORITY_INVALID,
    )
    _assert_invalid(
        replace(failed, waiver_attempts=(replace(attempt, evidence=()),)),
        InputFindingCode.WAIVER_PROOF_INVALID,
    )
    _assert_invalid(
        replace(failed, waiver_attempts=(attempt, attempt)),
        InputFindingCode.WAIVER_DUPLICATE,
    )
