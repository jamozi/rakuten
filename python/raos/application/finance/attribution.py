"""ENV-DEV/CI-only application service for Canonical ST-1303."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import (
    AttributionFailure,
    AttributionFailureCode,
    AttributionRunRequest,
    AttributionRunResult,
    build_attribution_run,
    fail_attribution,
)
from raos.ports.attribution import AttributionRunPort


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


@final
class AttributionService:
    """Validate a pure result around one local recorded adapter invocation."""

    __slots__ = ("_runner",)

    def __init__(
        self, *, environment: RuntimeEnvironment, runner: AttributionRunPort
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or not _implements(cast(object, runner), AttributionRunPort)
        ):
            fail_attribution(AttributionFailureCode.LOCAL_ENVIRONMENT_REQUIRED)
        self._runner = runner

    def execute(self, request: AttributionRunRequest) -> AttributionRunResult:
        if type(request) is not AttributionRunRequest:
            fail_attribution()
        expected = build_attribution_run(request)
        observed: object = None
        try:
            observed = self._runner.run(request)
        except Exception as error:
            if type(error) is AttributionFailure:
                raise error from None
            fail_attribution(AttributionFailureCode.RECORDED_RUN_UNAVAILABLE)
        if (
            type(observed) is not AttributionRunResult
            or observed != expected
            or observed.canonical_bytes() != expected.canonical_bytes()
        ):
            fail_attribution(AttributionFailureCode.RESULT_MISMATCH)
        return observed


__all__ = ("AttributionService",)
