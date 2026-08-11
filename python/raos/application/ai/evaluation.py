"""Pure ST-0707 bootstrap smoke evaluation runner."""

from __future__ import annotations

from typing import final

from raos.domain.ai.evaluation import (
    BOOTSTRAP_DATASET_VERSION,
    MAX_BOOTSTRAP_SMOKE_CASES,
    BootstrapCaseObservation,
    BootstrapEvaluationCase,
    BootstrapEvaluationFailureCode,
    BootstrapEvaluationReport,
    BootstrapSmokeStatus,
    DeterministicCheckCode,
    DeterministicCheckObservation,
    DeterministicCheckTally,
    EvaluationSplit,
    fail_bootstrap_evaluation,
)


def _normalize_case(candidate: object) -> BootstrapEvaluationCase:
    normalized: BootstrapEvaluationCase | None = None
    fingerprint: object = None
    if type(candidate) is BootstrapEvaluationCase:
        try:
            fingerprint = candidate.fingerprint_sha256
            normalized = BootstrapEvaluationCase(
                case_id=candidate.case_id,
                task_code=candidate.task_code,
                dataset_version=candidate.dataset_version,
                split=candidate.split,
                category=candidate.category,
                risk=candidate.risk,
                expected_disposition=candidate.expected_disposition,
                required_checks=candidate.required_checks,
            )
        except Exception:
            pass
    if normalized is None or normalized.fingerprint_sha256 != fingerprint:
        fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
    return normalized


def _normalize_observation(candidate: object) -> BootstrapCaseObservation:
    normalized: BootstrapCaseObservation | None = None
    if (
        type(candidate) is BootstrapCaseObservation
        and type(candidate.check_results) is tuple
        and all(
            type(result) is DeterministicCheckObservation
            for result in candidate.check_results
        )
        and type(candidate.zero_tolerance_classes) is tuple
    ):
        try:
            normalized_results = tuple(
                DeterministicCheckObservation(code=result.code, passed=result.passed)
                for result in candidate.check_results
            )
            normalized = BootstrapCaseObservation(
                case_id=candidate.case_id,
                case_fingerprint_sha256=candidate.case_fingerprint_sha256,
                observed_disposition=candidate.observed_disposition,
                check_results=normalized_results,
                zero_tolerance_classes=candidate.zero_tolerance_classes,
            )
        except Exception:
            pass
    if normalized is None or normalized != candidate:
        fail_bootstrap_evaluation(
            BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
        )
    return normalized


@final
class BootstrapEvaluationRunner:
    """Aggregate exact metadata and measured observations without side effects."""

    __slots__ = ()

    def run(
        self,
        cases: tuple[BootstrapEvaluationCase, ...],
        observations: tuple[BootstrapCaseObservation, ...],
    ) -> BootstrapEvaluationReport:
        if type(cases) is not tuple:
            fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.INVALID_CASE_SET)
        if not 1 <= len(cases) <= MAX_BOOTSTRAP_SMOKE_CASES:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.CASE_COUNT_OUT_OF_RANGE
            )
        normalized_cases = tuple(_normalize_case(case) for case in cases)
        for case in normalized_cases:
            if case.dataset_version != BOOTSTRAP_DATASET_VERSION:
                fail_bootstrap_evaluation(
                    BootstrapEvaluationFailureCode.UNSUPPORTED_DATASET_VERSION
                )
            if case.split is not EvaluationSplit.BOOTSTRAP:
                fail_bootstrap_evaluation(
                    BootstrapEvaluationFailureCode.UNSUPPORTED_SPLIT
                )
        identities = tuple(case.case_id for case in normalized_cases)
        fingerprints = tuple(case.fingerprint_sha256 for case in normalized_cases)
        if identities != tuple(sorted(identities)):
            fail_bootstrap_evaluation(BootstrapEvaluationFailureCode.CASE_ORDER_INVALID)
        if len(set(identities)) != len(identities) or len(set(fingerprints)) != len(
            fingerprints
        ):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.DUPLICATE_CASE_IDENTITY
            )

        if type(observations) is not tuple:
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.INVALID_OBSERVATION_SET
            )
        if len(observations) != len(normalized_cases):
            fail_bootstrap_evaluation(
                BootstrapEvaluationFailureCode.OBSERVATION_CARDINALITY_MISMATCH
            )
        normalized_observations = tuple(
            _normalize_observation(observation) for observation in observations
        )

        passed_by_check = {code: 0 for code in DeterministicCheckCode}
        total_by_check = {code: 0 for code in DeterministicCheckCode}
        passed_cases = 0
        zero_tolerance_count = 0
        for case, observation in zip(
            normalized_cases, normalized_observations, strict=True
        ):
            if (
                observation.case_id != case.case_id
                or observation.case_fingerprint_sha256 != case.fingerprint_sha256
                or tuple(result.code for result in observation.check_results)
                != case.required_checks
            ):
                fail_bootstrap_evaluation(
                    BootstrapEvaluationFailureCode.OBSERVATION_BINDING_MISMATCH
                )
            checks_pass = True
            for result in observation.check_results:
                total_by_check[result.code] += 1
                if result.passed:
                    passed_by_check[result.code] += 1
                else:
                    checks_pass = False
            findings = len(observation.zero_tolerance_classes)
            zero_tolerance_count += findings
            if (
                observation.observed_disposition is case.expected_disposition
                and checks_pass
                and findings == 0
            ):
                passed_cases += 1

        failed_cases = len(normalized_cases) - passed_cases
        status = BootstrapSmokeStatus.SMOKE_PASSED_NON_RELEASE
        if zero_tolerance_count:
            status = BootstrapSmokeStatus.BLOCKED_ZERO_TOLERANCE
        elif failed_cases:
            status = BootstrapSmokeStatus.SMOKE_FAILED
        tallies = tuple(
            DeterministicCheckTally(
                code=code,
                passed_count=passed_by_check[code],
                total_count=total_by_check[code],
            )
            for code in DeterministicCheckCode
        )
        return BootstrapEvaluationReport(
            status=status,
            case_count=len(normalized_cases),
            passed_case_count=passed_cases,
            failed_case_count=failed_cases,
            zero_tolerance_count=zero_tolerance_count,
            check_tallies=tallies,
        )
