"""Policy, finding, score, zero-tolerance, and gate behavior tests."""

from __future__ import annotations

from dataclasses import replace
from decimal import Context, Decimal, ROUND_DOWN, localcontext
import hashlib
import json

import pytest

from conftest import (
    EVALUATED_AT,
    bound,
    digest_for,
    reverse_collections,
    valid_policy_input,
    waiver_attempt,
    with_axis_score,
    with_gate_state,
    with_policy_result,
    with_predecessor_state,
    with_signal_state,
    with_total_score,
    with_waiver,
)
from raos.domain.editorial.policy_engine import (
    LOCAL_RESULT_SERIALIZATION_PROFILE,
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_GATE_DEFINITIONS,
    ZERO_TOLERANCE_LABELS,
    BoundReference,
    ExecutionStatus,
    FindingTarget,
    FindingTargetType,
    FindingResolution,
    GateAssessmentState,
    GateFailureAction,
    LocalEvaluationStatus,
    PolicyRuleResult,
    PolicySeverity,
    PredecessorState,
    PredecessorStory,
    ReferenceId,
    WaiverDisposition,
    ZeroToleranceState,
    evaluate_editorial_policy,
)


POLICY_IDS = tuple(item.policy_id for item in POLICY_DEFINITIONS)


def _bound_variants(
    value: BoundReference,
    label: str,
) -> tuple[BoundReference, BoundReference]:
    return (
        replace(value, reference=ReferenceId(f"DIGEST-{label}-REF")),
        replace(value, sha256=digest_for(f"DIGEST-{label}-HASH")),
    )


def _assert_valid_digest_change(
    baseline_digest: str,
    changed_input: object,
) -> None:
    changed = evaluate_editorial_policy(changed_input)

    assert changed.status is not LocalEvaluationStatus.INVALID_INPUT
    assert changed.input_findings == ()
    assert changed.local_result_digest != baseline_digest


def test_fully_resolved_local_run_is_eligible_but_never_authoritative() -> None:
    result = evaluate_editorial_policy(valid_policy_input())

    assert result.status is LocalEvaluationStatus.EVALUATED
    assert result.input_findings == ()
    assert result.policy_findings == ()
    assert result.waiver_evaluations == ()
    assert result.raw_quality_score == Decimal("100")
    assert result.quality_threshold_met is True
    assert result.quality_floors_met is True
    assert result.policy_rules_passed is True
    assert result.zero_tolerance_clear is True
    assert result.quality_gates_passed is True
    assert result.predecessors_available is True
    assert result.local_eligibility is True
    assert result.post_publication_required_action is None
    assert result.publication_authorized is False
    assert result.production_eligible is False
    assert result.formal_test_status is ExecutionStatus.NOT_EXECUTED
    assert result.live_validation_status is ExecutionStatus.NOT_EXECUTED
    assert result.staging_status is ExecutionStatus.NOT_EXECUTED
    assert result.release_status is ExecutionStatus.NOT_EXECUTED
    assert result.production_status is ExecutionStatus.NOT_EXECUTED


@pytest.mark.parametrize(
    ("score", "threshold_met", "eligible"),
    (
        (Decimal("84"), False, False),
        (Decimal("85"), True, True),
        (Decimal("100"), True, True),
    ),
)
def test_raw_score_84_85_and_100_boundaries_are_exact_and_separate(
    score: Decimal,
    threshold_met: bool,
    eligible: bool,
) -> None:
    result = evaluate_editorial_policy(with_total_score(score))

    assert result.raw_quality_score == score
    assert result.quality_threshold_met is threshold_met
    assert result.quality_floors_met is True
    assert result.local_eligibility is eligible


@pytest.mark.parametrize("axis_index", range(len(QUALITY_AXIS_DEFINITIONS)))
def test_every_axis_floor_is_individually_fail_closed(axis_index: int) -> None:
    definition = QUALITY_AXIS_DEFINITIONS[axis_index]
    value = with_axis_score(
        valid_policy_input(),
        definition.axis_id,
        definition.blocking_floor - Decimal("0.01"),
    )

    result = evaluate_editorial_policy(value)

    assert result.raw_quality_score is not None
    assert result.raw_quality_score >= Decimal("85")
    assert result.quality_threshold_met is True
    assert result.quality_floors_met is False
    assert result.local_eligibility is False


@pytest.mark.parametrize("label", ZERO_TOLERANCE_LABELS)
def test_every_triggered_zero_tolerance_signal_blocks_without_finding(
    label: str,
) -> None:
    value = with_signal_state(valid_policy_input(), label, ZeroToleranceState.TRIGGERED)

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.EVALUATED
    assert result.zero_tolerance_clear is False
    assert result.local_eligibility is False
    assert result.policy_findings == ()


@pytest.mark.parametrize("label", ZERO_TOLERANCE_LABELS)
def test_every_unevaluated_zero_tolerance_signal_is_distinct_from_failure(
    label: str,
) -> None:
    value = with_signal_state(
        valid_policy_input(), label, ZeroToleranceState.NOT_EVALUATED
    )

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.NOT_EVALUATED
    assert result.zero_tolerance_clear is False
    assert result.local_eligibility is False
    assert result.policy_findings == ()


@pytest.mark.parametrize("gate_index", range(len(QUALITY_GATE_DEFINITIONS)))
def test_each_pre_resolved_gate_failure_is_non_actioning(gate_index: int) -> None:
    definition = QUALITY_GATE_DEFINITIONS[gate_index]
    value = with_gate_state(
        valid_policy_input(), definition.gate_id, GateAssessmentState.FAIL
    )

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.EVALUATED
    assert result.quality_gates_passed is False
    assert result.local_eligibility is False
    assert result.policy_findings == ()
    expected = (
        GateFailureAction.ROLLBACK_OR_PAUSE
        if definition.gate_id == "QG-CONT-012"
        else None
    )
    assert result.post_publication_required_action is expected


@pytest.mark.parametrize("gate_index", range(len(QUALITY_GATE_DEFINITIONS)))
def test_each_unavailable_gate_is_not_evaluated_without_invented_action(
    gate_index: int,
) -> None:
    definition = QUALITY_GATE_DEFINITIONS[gate_index]
    value = with_gate_state(
        valid_policy_input(),
        definition.gate_id,
        GateAssessmentState.NOT_EVALUATED,
    )

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.NOT_EVALUATED
    assert result.quality_gates_passed is False
    assert result.local_eligibility is False
    assert result.post_publication_required_action is None
    assert result.policy_findings == ()


@pytest.mark.parametrize("story", tuple(PredecessorStory))
def test_each_unavailable_predecessor_is_not_a_vacuous_pass(
    story: PredecessorStory,
) -> None:
    value = with_predecessor_state(
        valid_policy_input(), story, PredecessorState.NOT_EVALUATED
    )

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.NOT_EVALUATED
    assert result.predecessors_available is False
    assert result.local_eligibility is False
    assert result.policy_findings == ()


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_compliant_fixture_passes_without_finding(policy_id: str) -> None:
    value = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.PASS)

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.EVALUATED
    assert result.policy_findings == ()
    assert result.local_eligibility is True


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_single_explicit_failure_emits_one_finding(
    policy_id: str,
) -> None:
    definition = next(
        item for item in POLICY_DEFINITIONS if item.policy_id == policy_id
    )
    value = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.FAIL)

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.EVALUATED
    assert len(result.policy_findings) == 1
    finding = result.policy_findings[0]
    assert finding.policy_id == policy_id
    assert finding.severity is definition.severity
    assert finding.is_blocking is (definition.severity is PolicySeverity.BLOCKER)
    assert result.local_eligibility is False


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_finding_carries_exact_traceability(policy_id: str) -> None:
    value = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.FAIL)
    assessment = next(
        item for item in value.policy_assessments if item.policy_id == policy_id
    )

    finding = evaluate_editorial_policy(value).policy_findings[0]

    assert finding.policy_version.value == POLICY_CATALOG_VERSION
    assert finding.policy_source_sha256.value == POLICY_CATALOG_SHA256
    assert finding.article_version_id == value.article_version_id
    assert finding.stage == assessment.stage
    assert finding.target == assessment.target
    assert finding.evidence == assessment.evidence
    assert finding.detector == assessment.detector
    assert finding.evaluated_at == EVALUATED_AT
    assert finding.rule_result is PolicyRuleResult.FAIL
    assert finding.resolution is FindingResolution.UNRESOLVED


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_waiver_is_denied_or_pending_and_never_effective(
    policy_id: str,
) -> None:
    definition = next(
        item for item in POLICY_DEFINITIONS if item.policy_id == policy_id
    )
    failed = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.FAIL)
    value = with_waiver(failed, policy_id)

    result = evaluate_editorial_policy(value)

    assert len(result.policy_findings) == 1
    assert len(result.waiver_evaluations) == 1
    waiver = result.waiver_evaluations[0]
    expected = (
        WaiverDisposition.DENIED_BLOCKER
        if definition.severity is PolicySeverity.BLOCKER
        else WaiverDisposition.PENDING_HUMAN_AUTHORITY
    )
    assert waiver.disposition is expected
    assert waiver.effective is False
    assert result.policy_findings[0].resolution is FindingResolution.UNRESOLVED
    assert result.raw_quality_score == Decimal("100")
    assert result.local_eligibility is False


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_publication_reevaluation_remains_non_authoritative(
    policy_id: str,
) -> None:
    value = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.FAIL)

    first = evaluate_editorial_policy(value)
    second = evaluate_editorial_policy(value)

    assert first == second
    assert first.publication_authorized is False
    assert first.production_eligible is False
    assert first.formal_test_status is ExecutionStatus.NOT_EXECUTED
    assert first.release_status is ExecutionStatus.NOT_EXECUTED


@pytest.mark.parametrize("policy_id", POLICY_IDS)
def test_each_policy_regression_rerun_is_byte_identical(policy_id: str) -> None:
    value = with_policy_result(valid_policy_input(), policy_id, PolicyRuleResult.FAIL)

    first = evaluate_editorial_policy(value)
    second = evaluate_editorial_policy(value)

    assert first.local_result_json == second.local_result_json
    assert first.local_result_digest == second.local_result_digest
    assert hashlib.sha256(first.local_result_json.encode("utf-8")).hexdigest() == (
        first.local_result_digest
    )


def test_major_failure_is_never_promoted_to_blocker() -> None:
    value = with_policy_result(
        valid_policy_input(), "POL-CONT-019", PolicyRuleResult.FAIL
    )

    result = evaluate_editorial_policy(value)

    assert result.policy_findings[0].severity is PolicySeverity.MAJOR
    assert result.policy_findings[0].is_blocking is False
    assert result.policy_findings[0].resolution is FindingResolution.UNRESOLVED
    assert result.local_eligibility is False


def test_policy_not_evaluated_does_not_fabricate_violation_finding() -> None:
    value = with_policy_result(
        valid_policy_input(), "POL-CONT-001", PolicyRuleResult.NOT_EVALUATED
    )

    result = evaluate_editorial_policy(value)

    assert result.status is LocalEvaluationStatus.NOT_EVALUATED
    assert result.policy_rules_passed is False
    assert result.policy_findings == ()
    assert result.local_eligibility is False


def test_score_100_never_overrides_other_fail_closed_dimensions() -> None:
    value = with_policy_result(
        valid_policy_input(), "POL-CONT-001", PolicyRuleResult.FAIL
    )
    value = with_signal_state(
        value, ZERO_TOLERANCE_LABELS[0], ZeroToleranceState.TRIGGERED
    )
    value = with_gate_state(value, "QG-CONT-011", GateAssessmentState.NOT_EVALUATED)

    result = evaluate_editorial_policy(value)

    assert result.raw_quality_score == Decimal("100")
    assert result.quality_threshold_met is True
    assert result.quality_floors_met is True
    assert result.status is LocalEvaluationStatus.NOT_EVALUATED
    assert len(result.policy_findings) == 1
    assert result.zero_tolerance_clear is False
    assert result.quality_gates_passed is False
    assert result.local_eligibility is False


def test_input_permutations_have_identical_local_serialization_and_digest() -> None:
    failed = with_policy_result(
        valid_policy_input(), "POL-CONT-019", PolicyRuleResult.FAIL
    )
    original = with_waiver(failed, "POL-CONT-019")
    permuted = reverse_collections(original)

    left = evaluate_editorial_policy(original)
    right = evaluate_editorial_policy(permuted)

    assert left.local_result_json == right.local_result_json
    assert left.local_result_digest == right.local_result_digest


def test_nested_evidence_permutations_are_identical_in_output_and_digest() -> None:
    value = with_policy_result(
        valid_policy_input(),
        "POL-CONT-019",
        PolicyRuleResult.FAIL,
    )
    policy_records = tuple(
        replace(
            record,
            evidence=(bound("EVIDENCE-POLICY-B"), bound("EVIDENCE-POLICY-A")),
        )
        if record.policy_id == "POL-CONT-019"
        else record
        for record in value.policy_assessments
    )
    axis_records = (
        replace(
            value.axis_assessments[0],
            evidence=(bound("EVIDENCE-AXIS-B"), bound("EVIDENCE-AXIS-A")),
        ),
        *value.axis_assessments[1:],
    )
    signal_records = (
        replace(
            value.zero_tolerance_assessments[0],
            evidence=(bound("EVIDENCE-SIGNAL-B"), bound("EVIDENCE-SIGNAL-A")),
        ),
        *value.zero_tolerance_assessments[1:],
    )
    gate_records = (
        replace(
            value.gate_assessments[0],
            evidence=(bound("EVIDENCE-GATE-B"), bound("EVIDENCE-GATE-A")),
        ),
        *value.gate_assessments[1:],
    )
    attempt = replace(
        waiver_attempt("POL-CONT-019"),
        evidence=(bound("EVIDENCE-WAIVER-B"), bound("EVIDENCE-WAIVER-A")),
    )
    original = replace(
        value,
        policy_assessments=policy_records,
        axis_assessments=axis_records,
        zero_tolerance_assessments=signal_records,
        gate_assessments=gate_records,
        waiver_attempts=(attempt,),
    )
    permuted = replace(
        original,
        policy_assessments=tuple(
            replace(record, evidence=tuple(reversed(record.evidence)))
            if len(record.evidence) > 1
            else record
            for record in original.policy_assessments
        ),
        axis_assessments=tuple(
            replace(record, evidence=tuple(reversed(record.evidence)))
            if len(record.evidence) > 1
            else record
            for record in original.axis_assessments
        ),
        zero_tolerance_assessments=tuple(
            replace(record, evidence=tuple(reversed(record.evidence)))
            if len(record.evidence) > 1
            else record
            for record in original.zero_tolerance_assessments
        ),
        gate_assessments=tuple(
            replace(record, evidence=tuple(reversed(record.evidence)))
            if len(record.evidence) > 1
            else record
            for record in original.gate_assessments
        ),
        waiver_attempts=(replace(attempt, evidence=tuple(reversed(attempt.evidence))),),
    )

    left = evaluate_editorial_policy(original)
    right = evaluate_editorial_policy(permuted)

    assert left.local_result_json == right.local_result_json
    assert left.local_result_digest == right.local_result_digest
    assert left.policy_findings == right.policy_findings
    assert tuple(item.reference.value for item in left.policy_findings[0].evidence) == (
        "EVIDENCE-POLICY-A",
        "EVIDENCE-POLICY-B",
    )


def test_decimal_result_is_independent_of_hostile_ambient_context() -> None:
    scores = (
        Decimal("10.123456789012"),
        Decimal("14.123456789012"),
        Decimal("9.123456789012"),
        Decimal("16.123456789012"),
        Decimal("7.123456789012"),
        Decimal("7.123456789012"),
        Decimal("3.123456789012"),
        Decimal("5"),
    )
    value = replace(
        valid_policy_input(),
        axis_assessments=tuple(
            replace(record, score=scores[index])
            for index, record in enumerate(valid_policy_input().axis_assessments)
        ),
    )

    baseline = evaluate_editorial_policy(value)
    with localcontext(Context(prec=4, rounding=ROUND_DOWN)):
        hostile = evaluate_editorial_policy(value)
        hostile_reversed = evaluate_editorial_policy(
            replace(value, axis_assessments=tuple(reversed(value.axis_assessments)))
        )

    assert baseline.raw_quality_score == Decimal("71.864197523084")
    assert hostile.raw_quality_score == baseline.raw_quality_score
    assert hostile.local_result_json == baseline.local_result_json
    assert hostile.local_result_digest == baseline.local_result_digest
    assert hostile_reversed.local_result_json == baseline.local_result_json
    assert hostile_reversed.local_result_digest == baseline.local_result_digest


def test_local_serialization_profile_unicode_null_and_digest_rules() -> None:
    result = evaluate_editorial_policy(valid_policy_input())
    decoded = json.loads(result.local_result_json)

    assert result.local_result_serialization_profile == (
        LOCAL_RESULT_SERIALIZATION_PROFILE
    )
    assert decoded["profile"] == "ST0805_LOCAL_RESULT_V1"
    assert decoded["derived"]["post_publication_required_action"] is None
    assert "重大な事実誤り" not in result.local_result_json
    assert "\\u91cd\\u5927" in result.local_result_json
    assert ": " not in result.local_result_json
    assert ", " not in result.local_result_json
    assert hashlib.sha256(result.local_result_json.encode("utf-8")).hexdigest() == (
        result.local_result_digest
    )


def test_structural_major_waiver_fields_change_digest_but_not_effect() -> None:
    failed = with_policy_result(
        valid_policy_input(), "POL-CONT-019", PolicyRuleResult.FAIL
    )
    attempt = waiver_attempt("POL-CONT-019")
    baseline = evaluate_editorial_policy(replace(failed, waiver_attempts=(attempt,)))
    changed = evaluate_editorial_policy(
        replace(
            failed,
            waiver_attempts=(
                replace(
                    attempt,
                    expiry_at=replace(
                        attempt.expiry_at,
                        value=attempt.expiry_at.value.replace(day=29),
                    ),
                ),
            ),
        )
    )

    assert baseline.local_result_digest != changed.local_result_digest
    assert baseline.waiver_evaluations[0].effective is False
    assert changed.waiver_evaluations[0].effective is False
    assert baseline.local_eligibility is False
    assert changed.local_eligibility is False


def test_local_digest_binds_top_level_time_and_every_article_coordinate() -> None:
    value = valid_policy_input()
    baseline = evaluate_editorial_policy(value)
    assert baseline.status is LocalEvaluationStatus.EVALUATED

    changed_time = replace(
        value,
        evaluated_at=replace(
            value.evaluated_at,
            value=value.evaluated_at.value.replace(hour=1),
        ),
    )
    _assert_valid_digest_change(baseline.local_result_digest, changed_time)

    article_version = ReferenceId("ARTICLE-VERSION-0805-ALT")
    rebound = replace(
        value,
        article_version_id=article_version,
        predecessors=tuple(
            replace(record, article_version_id=article_version)
            for record in value.predecessors
        ),
        policy_assessments=tuple(
            replace(
                record,
                article_version_id=article_version,
                target=replace(record.target, target_ref=article_version),
            )
            for record in value.policy_assessments
        ),
        axis_assessments=tuple(
            replace(record, article_version_id=article_version)
            for record in value.axis_assessments
        ),
        zero_tolerance_assessments=tuple(
            replace(record, article_version_id=article_version)
            for record in value.zero_tolerance_assessments
        ),
        gate_assessments=tuple(
            replace(record, article_version_id=article_version)
            for record in value.gate_assessments
        ),
    )
    _assert_valid_digest_change(baseline.local_result_digest, rebound)


def test_local_digest_binds_every_predecessor_reference_hash_and_state() -> None:
    value = valid_policy_input()
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for index, record in enumerate(value.predecessors):
        result = record.result
        assert result is not None
        for variant in _bound_variants(result, f"PRED-{index}-RESULT"):
            changed_record = replace(record, result=variant)
            changed = replace(
                value,
                predecessors=(
                    *value.predecessors[:index],
                    changed_record,
                    *value.predecessors[index + 1 :],
                ),
            )
            _assert_valid_digest_change(baseline_digest, changed)
        for variant in _bound_variants(
            record.provenance,
            f"PRED-{index}-PROVENANCE",
        ):
            changed_record = replace(record, provenance=variant)
            changed = replace(
                value,
                predecessors=(
                    *value.predecessors[:index],
                    changed_record,
                    *value.predecessors[index + 1 :],
                ),
            )
            _assert_valid_digest_change(baseline_digest, changed)
        unavailable = replace(
            record,
            state=PredecessorState.NOT_EVALUATED,
            result=None,
        )
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                predecessors=(
                    *value.predecessors[:index],
                    unavailable,
                    *value.predecessors[index + 1 :],
                ),
            ),
        )


def test_local_digest_binds_every_policy_proof_target_and_result() -> None:
    value = valid_policy_input()
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for index, record in enumerate(value.policy_assessments):
        for variant in _bound_variants(
            record.evidence[0],
            f"POL-{index}-EVIDENCE",
        ):
            changed_record = replace(record, evidence=(variant,))
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    policy_assessments=(
                        *value.policy_assessments[:index],
                        changed_record,
                        *value.policy_assessments[index + 1 :],
                    ),
                ),
            )
        for variant in _bound_variants(
            record.detector,
            f"POL-{index}-DETECTOR",
        ):
            changed_record = replace(record, detector=variant)
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    policy_assessments=(
                        *value.policy_assessments[:index],
                        changed_record,
                        *value.policy_assessments[index + 1 :],
                    ),
                ),
            )
        targets = (
            FindingTarget(FindingTargetType.CLAIM, record.target.target_ref),
            FindingTarget(
                FindingTargetType.CLAIM,
                ReferenceId(f"CLAIM-TARGET-{index:03d}"),
            ),
        )
        for target in targets:
            changed_record = replace(record, target=target)
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    policy_assessments=(
                        *value.policy_assessments[:index],
                        changed_record,
                        *value.policy_assessments[index + 1 :],
                    ),
                ),
            )
        failed_record = replace(record, result=PolicyRuleResult.FAIL)
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                policy_assessments=(
                    *value.policy_assessments[:index],
                    failed_record,
                    *value.policy_assessments[index + 1 :],
                ),
            ),
        )


def test_local_digest_binds_every_axis_score_and_proof() -> None:
    value = valid_policy_input()
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for index, record in enumerate(value.axis_assessments):
        assert record.score is not None
        changed_score = replace(record, score=record.score - Decimal("0.01"))
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                axis_assessments=(
                    *value.axis_assessments[:index],
                    changed_score,
                    *value.axis_assessments[index + 1 :],
                ),
            ),
        )
        for variant in _bound_variants(
            record.evidence[0],
            f"AXIS-{index}-EVIDENCE",
        ):
            changed_record = replace(record, evidence=(variant,))
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    axis_assessments=(
                        *value.axis_assessments[:index],
                        changed_record,
                        *value.axis_assessments[index + 1 :],
                    ),
                ),
            )
        for variant in _bound_variants(
            record.evaluator,
            f"AXIS-{index}-EVALUATOR",
        ):
            changed_record = replace(record, evaluator=variant)
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    axis_assessments=(
                        *value.axis_assessments[:index],
                        changed_record,
                        *value.axis_assessments[index + 1 :],
                    ),
                ),
            )


def test_local_digest_binds_every_zero_tolerance_state_and_proof() -> None:
    value = valid_policy_input()
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for index, record in enumerate(value.zero_tolerance_assessments):
        triggered = replace(record, state=ZeroToleranceState.TRIGGERED)
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                zero_tolerance_assessments=(
                    *value.zero_tolerance_assessments[:index],
                    triggered,
                    *value.zero_tolerance_assessments[index + 1 :],
                ),
            ),
        )
        for variant in _bound_variants(
            record.evidence[0],
            f"SIGNAL-{index}-EVIDENCE",
        ):
            changed_record = replace(record, evidence=(variant,))
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    zero_tolerance_assessments=(
                        *value.zero_tolerance_assessments[:index],
                        changed_record,
                        *value.zero_tolerance_assessments[index + 1 :],
                    ),
                ),
            )
        for variant in _bound_variants(
            record.detector,
            f"SIGNAL-{index}-DETECTOR",
        ):
            changed_record = replace(record, detector=variant)
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    zero_tolerance_assessments=(
                        *value.zero_tolerance_assessments[:index],
                        changed_record,
                        *value.zero_tolerance_assessments[index + 1 :],
                    ),
                ),
            )


def test_local_digest_binds_every_gate_state_and_proof() -> None:
    value = valid_policy_input()
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for index, record in enumerate(value.gate_assessments):
        failed = replace(record, state=GateAssessmentState.FAIL)
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                gate_assessments=(
                    *value.gate_assessments[:index],
                    failed,
                    *value.gate_assessments[index + 1 :],
                ),
            ),
        )
        for variant in _bound_variants(
            record.evidence[0],
            f"GATE-{index}-EVIDENCE",
        ):
            changed_record = replace(record, evidence=(variant,))
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    gate_assessments=(
                        *value.gate_assessments[:index],
                        changed_record,
                        *value.gate_assessments[index + 1 :],
                    ),
                ),
            )
        for variant in _bound_variants(
            record.evaluator,
            f"GATE-{index}-EVALUATOR",
        ):
            changed_record = replace(record, evaluator=variant)
            _assert_valid_digest_change(
                baseline_digest,
                replace(
                    value,
                    gate_assessments=(
                        *value.gate_assessments[:index],
                        changed_record,
                        *value.gate_assessments[index + 1 :],
                    ),
                ),
            )


def test_local_digest_binds_every_structural_waiver_reference_and_expiry() -> None:
    failed = with_policy_result(
        valid_policy_input(),
        "POL-CONT-019",
        PolicyRuleResult.FAIL,
    )
    attempt = waiver_attempt("POL-CONT-019")
    value = replace(failed, waiver_attempts=(attempt,))
    baseline_digest = evaluate_editorial_policy(value).local_result_digest

    for variant in _bound_variants(attempt.reason, "WAIVER-REASON"):
        _assert_valid_digest_change(
            baseline_digest,
            replace(value, waiver_attempts=(replace(attempt, reason=variant),)),
        )
    for variant in _bound_variants(
        attempt.evidence[0],
        "WAIVER-EVIDENCE",
    ):
        _assert_valid_digest_change(
            baseline_digest,
            replace(value, waiver_attempts=(replace(attempt, evidence=(variant,)),)),
        )
    for variant in _bound_variants(
        attempt.compliance_approver,
        "WAIVER-APPROVER",
    ):
        _assert_valid_digest_change(
            baseline_digest,
            replace(
                value,
                waiver_attempts=(replace(attempt, compliance_approver=variant),),
            ),
        )
    for variant in _bound_variants(attempt.audit_event, "WAIVER-AUDIT"):
        _assert_valid_digest_change(
            baseline_digest,
            replace(value, waiver_attempts=(replace(attempt, audit_event=variant),)),
        )
    _assert_valid_digest_change(
        baseline_digest,
        replace(
            value,
            waiver_attempts=(
                replace(
                    attempt,
                    expiry_at=replace(
                        attempt.expiry_at,
                        value=attempt.expiry_at.value.replace(day=28),
                    ),
                ),
            ),
        ),
    )


def test_local_serialization_binds_exact_inventory_in_stable_catalog_order() -> None:
    payload = json.loads(
        evaluate_editorial_policy(valid_policy_input()).local_result_json
    )

    assert [item["story_id"] for item in payload["predecessors"]] == [
        story.value for story in PredecessorStory
    ]
    assert [item["policy_id"] for item in payload["policy_assessments"]] == list(
        POLICY_IDS
    )
    assert [item["axis_id"] for item in payload["quality_axes"]] == [
        definition.axis_id for definition in QUALITY_AXIS_DEFINITIONS
    ]
    assert [item["label"] for item in payload["zero_tolerance"]] == list(
        ZERO_TOLERANCE_LABELS
    )
    assert [item["gate_id"] for item in payload["gates"]] == [
        definition.gate_id for definition in QUALITY_GATE_DEFINITIONS
    ]
    assert all(
        set(item["detector"]) == {"ref", "sha256"}
        and all(set(evidence) == {"ref", "sha256"} for evidence in item["evidence"])
        for item in payload["policy_assessments"]
    )
    assert all(
        set(item["evaluator"]) == {"ref", "sha256"}
        and all(set(evidence) == {"ref", "sha256"} for evidence in item["evidence"])
        for item in payload["quality_axes"]
    )
