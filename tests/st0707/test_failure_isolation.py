"""Hostile exact-type, binding, redaction, and no-partial-report checks."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import pickle
from typing import Any

import pytest

from conftest import ALL_CHECKS, make_case, observe
from raos.application.ai.evaluation import BootstrapEvaluationRunner
from raos.domain.ai.evaluation import (
    BootstrapCaseObservation,
    BootstrapEvaluationCase,
    BootstrapEvaluationFailure,
    BootstrapEvaluationFailureCode,
    BootstrapSmokeStatus,
    DeterministicCheckCode,
    DeterministicCheckObservation,
    EvaluationRisk,
    EvaluationSplit,
    ExpectedDisposition,
    ZeroToleranceClass,
)


def assert_failure(
    expected: BootstrapEvaluationFailureCode,
    call: object,
) -> BootstrapEvaluationFailure:
    with pytest.raises(BootstrapEvaluationFailure) as caught:
        call()  # type: ignore[operator]
    assert caught.value.code is expected
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    return caught.value


def test_empty_and_121_cases_fail_before_any_report() -> None:
    runner = BootstrapEvaluationRunner()
    assert_failure(
        BootstrapEvaluationFailureCode.CASE_COUNT_OUT_OF_RANGE,
        lambda: runner.run((), ()),
    )
    cases = tuple(make_case(number) for number in range(1, 122))
    assert_failure(
        BootstrapEvaluationFailureCode.CASE_COUNT_OUT_OF_RANGE,
        lambda: runner.run(cases, tuple(observe(case) for case in cases)),
    )


@pytest.mark.parametrize(
    "split",
    tuple(item for item in EvaluationSplit if item is not EvaluationSplit.BOOTSTRAP),
)
def test_every_non_bootstrap_split_is_rejected(split: EvaluationSplit) -> None:
    case = make_case(split=split)
    assert_failure(
        BootstrapEvaluationFailureCode.UNSUPPORTED_SPLIT,
        lambda: BootstrapEvaluationRunner().run((case,), (observe(case),)),
    )


def test_wrong_dataset_version_is_rejected() -> None:
    case = make_case(dataset_version="bootstrap-v0.2")
    assert_failure(
        BootstrapEvaluationFailureCode.UNSUPPORTED_DATASET_VERSION,
        lambda: BootstrapEvaluationRunner().run((case,), (observe(case),)),
    )


def test_duplicate_or_reordered_cases_are_rejected() -> None:
    first = make_case(1)
    second = make_case(2)
    assert_failure(
        BootstrapEvaluationFailureCode.DUPLICATE_CASE_IDENTITY,
        lambda: BootstrapEvaluationRunner().run(
            (first, first), (observe(first), observe(first))
        ),
    )
    assert_failure(
        BootstrapEvaluationFailureCode.CASE_ORDER_INVALID,
        lambda: BootstrapEvaluationRunner().run(
            (second, first), (observe(second), observe(first))
        ),
    )


def test_missing_extra_reordered_and_mismatched_observations_fail_closed() -> None:
    first = make_case(1)
    second = make_case(2)
    runner = BootstrapEvaluationRunner()
    assert_failure(
        BootstrapEvaluationFailureCode.OBSERVATION_CARDINALITY_MISMATCH,
        lambda: runner.run((first, second), (observe(first),)),
    )
    assert_failure(
        BootstrapEvaluationFailureCode.OBSERVATION_CARDINALITY_MISMATCH,
        lambda: runner.run((first,), (observe(first), observe(first))),
    )
    assert_failure(
        BootstrapEvaluationFailureCode.OBSERVATION_BINDING_MISMATCH,
        lambda: runner.run((first, second), (observe(second), observe(first))),
    )
    mismatched = BootstrapCaseObservation(
        case_id=first.case_id,
        case_fingerprint_sha256="f" * 64,
        observed_disposition=first.expected_disposition,
        check_results=observe(first).check_results,
        zero_tolerance_classes=(),
    )
    assert_failure(
        BootstrapEvaluationFailureCode.OBSERVATION_BINDING_MISMATCH,
        lambda: runner.run((first,), (mismatched,)),
    )


def test_required_checks_must_be_nonempty_unique_exact_and_canonical() -> None:
    with pytest.raises(BootstrapEvaluationFailure):
        make_case(required_checks=())
    with pytest.raises(BootstrapEvaluationFailure):
        make_case(required_checks=(ALL_CHECKS[0], ALL_CHECKS[0]))
    with pytest.raises(BootstrapEvaluationFailure):
        make_case(required_checks=(ALL_CHECKS[1], ALL_CHECKS[0]))
    with pytest.raises(BootstrapEvaluationFailure):
        make_case(required_checks=("SCHEMA_VALID",))  # type: ignore[arg-type]


def test_observation_checks_and_findings_must_be_exact_unique_and_canonical() -> None:
    case = make_case(required_checks=ALL_CHECKS[:2])
    good = observe(case)
    raw_bool = DeterministicCheckObservation.__new__(DeterministicCheckObservation)
    object.__setattr__(raw_bool, "code", ALL_CHECKS[0])
    object.__setattr__(raw_bool, "passed", 1)
    malformed = BootstrapCaseObservation.__new__(BootstrapCaseObservation)
    object.__setattr__(malformed, "case_id", case.case_id)
    object.__setattr__(malformed, "case_fingerprint_sha256", case.fingerprint_sha256)
    object.__setattr__(malformed, "observed_disposition", case.expected_disposition)
    object.__setattr__(malformed, "check_results", (raw_bool, good.check_results[1]))
    object.__setattr__(malformed, "zero_tolerance_classes", ())
    assert_failure(
        BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET,
        lambda: BootstrapEvaluationRunner().run((case,), (malformed,)),
    )
    with pytest.raises(BootstrapEvaluationFailure):
        BootstrapCaseObservation(
            case_id=case.case_id,
            case_fingerprint_sha256=case.fingerprint_sha256,
            observed_disposition=case.expected_disposition,
            check_results=(good.check_results[0], good.check_results[0]),
            zero_tolerance_classes=(),
        )
    with pytest.raises(BootstrapEvaluationFailure):
        BootstrapCaseObservation(
            case_id=case.case_id,
            case_fingerprint_sha256=case.fingerprint_sha256,
            observed_disposition=case.expected_disposition,
            check_results=good.check_results,
            zero_tolerance_classes=(
                ZeroToleranceClass.SECRET_OR_RESTRICTED_DATA,
                ZeroToleranceClass.UNSUPPORTED_CRITICAL_FACTUAL_CLAIM,
            ),
        )


class TupleSubclass(tuple[object, ...]):
    pass


class StringSubclass(str):
    pass


def test_builtins_tuples_enums_and_strings_reject_subclasses_or_raw_values() -> None:
    case = make_case()
    observation = observe(case)
    runner = BootstrapEvaluationRunner()
    assert_failure(
        BootstrapEvaluationFailureCode.INVALID_CASE_SET,
        lambda: runner.run(TupleSubclass((case,)), (observation,)),  # type: ignore[arg-type]
    )
    assert_failure(
        BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET,
        lambda: runner.run((case,), TupleSubclass((observation,))),  # type: ignore[arg-type]
    )
    with pytest.raises(BootstrapEvaluationFailure):
        BootstrapEvaluationCase(
            case_id=StringSubclass("AICASE-0001"),
            task_code="ai.article_draft.v1",
            dataset_version="bootstrap-v0.1",
            split=EvaluationSplit.BOOTSTRAP,
            category="bootstrap_smoke",
            risk=EvaluationRisk.HIGH,
            expected_disposition=ExpectedDisposition.CALL_PROVIDER_AND_PASS,
            required_checks=ALL_CHECKS,
        )
    with pytest.raises(BootstrapEvaluationFailure):
        BootstrapEvaluationCase(
            case_id="AICASE-0001",
            task_code="ai.article_draft.v1",
            dataset_version="bootstrap-v0.1",
            split="BOOTSTRAP",  # type: ignore[arg-type]
            category="bootstrap_smoke",
            risk=EvaluationRisk.HIGH,
            expected_disposition=ExpectedDisposition.CALL_PROVIDER_AND_PASS,
            required_checks=ALL_CHECKS,
        )


def test_redacted_values_errors_and_pickle_never_expose_canaries() -> None:
    canaries = (
        "secret-canary-st0707",
        "raw-prompt-canary-st0707",
        "raw-output-canary-st0707",
    )
    case = make_case()
    observation = observe(case)
    report = BootstrapEvaluationRunner().run((case,), (observation,))
    for value in (case, observation, observation.check_results[0], report):
        rendered = f"{value!r} {value!s}"
        assert all(canary not in rendered for canary in canaries)
        with pytest.raises(TypeError) as pickle_caught:
            pickle.dumps(value)
        assert all(canary not in str(pickle_caught.value) for canary in canaries)

    with pytest.raises(BootstrapEvaluationFailure) as construction_caught:
        BootstrapEvaluationCase(
            case_id=canaries[0],
            task_code=canaries[1],
            dataset_version="bootstrap-v0.1",
            split=EvaluationSplit.BOOTSTRAP,
            category=canaries[2],
            risk=EvaluationRisk.CRITICAL,
            expected_disposition=ExpectedDisposition.BLOCK_BEFORE_PROVIDER,
            required_checks=ALL_CHECKS,
        )
    failure = construction_caught.value
    serialized_error = f"{failure!s} {failure!r} {failure.args!r}"
    assert all(canary not in serialized_error for canary in canaries)
    assert failure.__cause__ is failure.__context__ is None
    with pytest.raises(TypeError):
        pickle.dumps(failure)


def test_report_is_frozen_and_zero_tolerance_precedes_other_smoke_failures() -> None:
    case = make_case()
    report = BootstrapEvaluationRunner().run(
        (case,),
        (
            observe(
                case,
                failed_check=DeterministicCheckCode.SCHEMA_VALID,
                zero_tolerance_classes=(
                    ZeroToleranceClass.UNSUPPORTED_CRITICAL_FACTUAL_CLAIM,
                ),
            ),
        ),
    )
    assert report.status is BootstrapSmokeStatus.BLOCKED_ZERO_TOLERANCE
    with pytest.raises(FrozenInstanceError):
        report.release_eligible = True  # type: ignore[misc]


def test_invalid_later_observation_returns_no_partial_report() -> None:
    first = make_case(1)
    second = make_case(2)
    invalid_second = BootstrapCaseObservation(
        case_id=second.case_id,
        case_fingerprint_sha256="0" * 64,
        observed_disposition=second.expected_disposition,
        check_results=observe(second).check_results,
        zero_tolerance_classes=(),
    )
    result: Any = None
    with pytest.raises(BootstrapEvaluationFailure):
        result = BootstrapEvaluationRunner().run(
            (first, second), (observe(first), invalid_second)
        )
    assert result is None
