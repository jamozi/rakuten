"""ENV-DEV/CI-only application service for Canonical ST-1304."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.unit_economics import (
    UnitEconomicsFailure,
    UnitEconomicsFailureCode,
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
    build_unit_economics,
    fail_unit_economics,
)
from raos.ports.unit_economics import UnitEconomicsRunPort


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class UnitEconomicsService:
    """Validate a pure result around one local recorded adapter invocation."""

    __slots__ = ("_runner",)

    def __init__(
        self, *, environment: RuntimeEnvironment, runner: UnitEconomicsRunPort
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(cast(object, runner), UnitEconomicsRunPort)
        ):
            fail_unit_economics(UnitEconomicsFailureCode.LOCAL_ENVIRONMENT_REQUIRED)
        self._runner = runner

    def execute(self, request: UnitEconomicsRunRequest) -> UnitEconomicsRunResult:
        if type(request) is not UnitEconomicsRunRequest:
            fail_unit_economics()
        expected = build_unit_economics(request)
        observed: object = None
        try:
            observed = self._runner.run(request)
        except Exception as error:
            if type(error) is UnitEconomicsFailure:
                raise error from None
            fail_unit_economics(UnitEconomicsFailureCode.RECORDED_RUN_UNAVAILABLE)
        if (
            type(observed) is not UnitEconomicsRunResult
            or observed != expected
            or observed.canonical_bytes() != expected.canonical_bytes()
        ):
            fail_unit_economics(UnitEconomicsFailureCode.RESULT_MISMATCH)
        return observed


__all__ = ("UnitEconomicsService",)
