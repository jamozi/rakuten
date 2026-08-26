"""Metadata-only fixtures for the isolated ST-0707 suite."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.domain.ai.evaluation import (  # noqa: E402
    BOOTSTRAP_DATASET_VERSION,
    BootstrapCaseObservation,
    BootstrapEvaluationCase,
    DeterministicCheckCode,
    DeterministicCheckObservation,
    EvaluationRisk,
    EvaluationSplit,
    ExpectedDisposition,
    ZeroToleranceClass,
)


ALL_CHECKS = tuple(DeterministicCheckCode)


def make_case(
    number: int = 1,
    *,
    dataset_version: str = BOOTSTRAP_DATASET_VERSION,
    split: EvaluationSplit = EvaluationSplit.BOOTSTRAP,
    expected_disposition: ExpectedDisposition = (
        ExpectedDisposition.CALL_PROVIDER_AND_PASS
    ),
    required_checks: tuple[DeterministicCheckCode, ...] = ALL_CHECKS,
) -> BootstrapEvaluationCase:
    return BootstrapEvaluationCase(
        case_id=f"AICASE-{number:04d}",
        task_code="ai.article_draft.v1",
        dataset_version=dataset_version,
        split=split,
        category="bootstrap_smoke",
        risk=EvaluationRisk.HIGH,
        expected_disposition=expected_disposition,
        required_checks=required_checks,
    )


def observe(
    case: BootstrapEvaluationCase,
    *,
    observed_disposition: ExpectedDisposition | None = None,
    failed_check: DeterministicCheckCode | None = None,
    zero_tolerance_classes: tuple[ZeroToleranceClass, ...] = (),
) -> BootstrapCaseObservation:
    return BootstrapCaseObservation(
        case_id=case.case_id,
        case_fingerprint_sha256=case.fingerprint_sha256,
        observed_disposition=observed_disposition or case.expected_disposition,
        check_results=tuple(
            DeterministicCheckObservation(code=code, passed=code is not failed_check)
            for code in case.required_checks
        ),
        zero_tolerance_classes=zero_tolerance_classes,
    )
