"""Focused positive and zero-tolerance ST-0707 behavior."""

from __future__ import annotations

import pytest

from conftest import ALL_CHECKS, make_case, observe
from raos.application.ai.evaluation import BootstrapEvaluationRunner
from raos.domain.ai.evaluation import (
    BootstrapSmokeStatus,
    DeterministicCheckCode,
    ExpectedDisposition,
    ZeroToleranceClass,
)


def test_one_all_pass_case_is_non_authoritative_and_never_release_eligible() -> None:
    case = make_case()
    report = BootstrapEvaluationRunner().run((case,), (observe(case),))

    assert report.status is BootstrapSmokeStatus.SMOKE_PASSED_NON_RELEASE
    assert (report.case_count, report.passed_case_count, report.failed_case_count) == (
        1,
        1,
        0,
    )
    assert report.zero_tolerance_count == 0
    assert tuple(tally.code for tally in report.check_tallies) == ALL_CHECKS
    assert all(
        (tally.passed_count, tally.total_count) == (1, 1)
        for tally in report.check_tallies
    )
    assert report.scope == "BOOTSTRAP_SMOKE_ONLY"
    assert report.authority == "NON_AUTHORITATIVE"
    assert report.documented_bootstrap_case_count == 120
    assert report.canonical_bootstrap_payload_bound is False
    assert report.locked_holdout == "NOT_LOADED"
    assert report.human_labels == "NOT_OBTAINED"
    assert report.judge_calibration == "NOT_OBTAINED"
    assert report.threshold_evaluation == "NOT_PERFORMED"
    assert report.wilson_interval == "NOT_PERFORMED"
    assert report.statistical_claims == "NOT_PERFORMED"
    assert report.formal_tst_018 == "NOT_EXECUTED"
    assert report.formal_tst_019 == "NOT_EXECUTED"
    assert report.story_acceptance is False
    assert report.release_decision == "NOT_READY"
    assert report.release_eligible is False
    assert report.production_eligible is False
    assert type(report.external_action_count) is int
    assert type(report.action_count) is int
    assert report.external_action_count == report.action_count == 0


def test_exact_120_all_pass_cases_remain_smoke_only_and_non_release() -> None:
    cases = tuple(make_case(number) for number in range(1, 121))
    report = BootstrapEvaluationRunner().run(
        cases, tuple(observe(case) for case in cases)
    )

    assert report.status is BootstrapSmokeStatus.SMOKE_PASSED_NON_RELEASE
    assert (report.case_count, report.passed_case_count, report.failed_case_count) == (
        120,
        120,
        0,
    )
    assert report.release_eligible is report.production_eligible is False
    assert report.story_acceptance is False


def test_one_failed_check_fails_the_smoke_report_with_exact_integer_tally() -> None:
    case = make_case()
    failed = DeterministicCheckCode.NUMERIC_EXACTNESS
    report = BootstrapEvaluationRunner().run(
        (case,), (observe(case, failed_check=failed),)
    )

    assert report.status is BootstrapSmokeStatus.SMOKE_FAILED
    assert (report.passed_case_count, report.failed_case_count) == (0, 1)
    tally = next(item for item in report.check_tallies if item.code is failed)
    assert type(tally.passed_count) is int
    assert type(tally.total_count) is int
    assert (tally.passed_count, tally.total_count) == (0, 1)


def test_disposition_mismatch_fails_even_when_every_check_passes() -> None:
    case = make_case()
    report = BootstrapEvaluationRunner().run(
        (case,),
        (
            observe(
                case,
                observed_disposition=ExpectedDisposition.EXPECTED_REFUSAL,
            ),
        ),
    )
    assert report.status is BootstrapSmokeStatus.SMOKE_FAILED
    assert report.failed_case_count == 1


@pytest.mark.parametrize("finding", tuple(ZeroToleranceClass))
def test_each_exact_zero_tolerance_class_blocks(finding: ZeroToleranceClass) -> None:
    case = make_case()
    report = BootstrapEvaluationRunner().run(
        (case,), (observe(case, zero_tolerance_classes=(finding,)),)
    )

    assert report.status is BootstrapSmokeStatus.BLOCKED_ZERO_TOLERANCE
    assert report.zero_tolerance_count == 1
    assert report.failed_case_count == 1
    assert report.release_eligible is report.production_eligible is False
