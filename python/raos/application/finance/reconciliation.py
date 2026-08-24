"""ENV-DEV/CI-only application service for Canonical ST-1305."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.reconciliation import (
    FinanceReconciliationFailure,
    FinanceReconciliationFailureCode,
    FinanceReconciliationRunRequest,
    FinanceReconciliationRunResult,
    build_finance_reconciliation,
    fail_finance_reconciliation,
)
from raos.ports.finance_reconciliation import FinanceReconciliationRunPort


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class FinanceReconciliationService:
    """Validate a pure result around one local recorded adapter invocation."""

    __slots__ = ("_runner",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        runner: FinanceReconciliationRunPort,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(cast(object, runner), FinanceReconciliationRunPort)
        ):
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.LOCAL_ENVIRONMENT_REQUIRED
            )
        self._runner = runner

    def execute(
        self, request: FinanceReconciliationRunRequest
    ) -> FinanceReconciliationRunResult:
        if type(request) is not FinanceReconciliationRunRequest:
            fail_finance_reconciliation()
        expected = build_finance_reconciliation(request)
        observed: object = None
        try:
            observed = self._runner.run(request)
        except Exception as error:
            if type(error) is FinanceReconciliationFailure:
                raise error from None
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.RECORDED_RUN_UNAVAILABLE
            )
        if (
            type(observed) is not FinanceReconciliationRunResult
            or observed != expected
            or observed.canonical_bytes() != expected.canonical_bytes()
        ):
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.RESULT_MISMATCH
            )
        return observed


__all__ = ("FinanceReconciliationService",)
