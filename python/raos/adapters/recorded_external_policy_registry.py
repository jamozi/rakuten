"""Bounded immutable DEV/CI fixture adapter for ST-1407."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.external_policy_registry import (
    ExternalPolicyRegistryReport,
    ExternalPolicyRegistryRequest,
    RegistryFailureCode,
    evaluate_external_policy_registry,
    fail_registry,
    registry_report_json,
)


MAX_RECORDED_REGISTRY_FIXTURES = 128
RECORDED_FIXTURE_REQUEST_SHA256S: tuple[tuple[str, str], ...] = (
    (
        "ST1407-NOT-DUE-EMPTY-001",
        "aca34743ac05c92a6bab514fd1c65e83721e21f04e54739ae451953c942c2b30",
    ),
    (
        "ST1407-OVERDUE-AFFECTED-001",
        "3d7f995d6957ee0893be1a20d785f0d899fe5093b951bd39024aeda08056a8c4",
    ),
)
_RECORDED_FIXTURE_REQUEST_MAP = dict(RECORDED_FIXTURE_REQUEST_SHA256S)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedExternalPolicyRegistryFixture:
    request: ExternalPolicyRegistryRequest
    report: ExternalPolicyRegistryReport
    fixture_id: str

    def __post_init__(self) -> None:
        matches = False
        if (
            type(self.fixture_id) is str
            and self.fixture_id in _RECORDED_FIXTURE_REQUEST_MAP
            and type(self.request) is ExternalPolicyRegistryRequest
            and type(self.report) is ExternalPolicyRegistryReport
        ):
            try:
                expected = evaluate_external_policy_registry(self.request)
                matches = (
                    self.request.fingerprint
                    == _RECORDED_FIXTURE_REQUEST_MAP[self.fixture_id]
                    and expected.request_sha256.value
                    == _RECORDED_FIXTURE_REQUEST_MAP[self.fixture_id]
                    and expected == self.report
                    and expected.fingerprint == self.report.fingerprint
                    and registry_report_json(expected)
                    == registry_report_json(self.report)
                )
            except Exception:
                matches = False
        if not matches:
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)

    def __repr__(self) -> str:
        return "RecordedExternalPolicyRegistryFixture(<redacted-st1407>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded external policy fixture serialization is disabled")


@final
class RecordedExternalPolicyRegistryAdapter:
    """Replay only exact, pre-validated fixture request/result bindings."""

    __slots__ = ("_bindings",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        fixture_capacity: int,
        fixtures: tuple[RecordedExternalPolicyRegistryFixture, ...],
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_registry(RegistryFailureCode.DEVELOPMENT_ONLY)
        if (
            type(fixture_capacity) is not int
            or not 1 <= fixture_capacity <= MAX_RECORDED_REGISTRY_FIXTURES
            or type(fixtures) is not tuple
            or not 1 <= len(fixtures) <= fixture_capacity
            or any(
                type(item) is not RecordedExternalPolicyRegistryFixture
                for item in fixtures
            )
        ):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        bindings: list[tuple[str, str, str]] = []
        try:
            for fixture in fixtures:
                expected = evaluate_external_policy_registry(fixture.request)
                if (
                    expected != fixture.report
                    or expected.fingerprint != fixture.report.fingerprint
                ):
                    fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)
                bindings.append(
                    (
                        fixture.fixture_id,
                        fixture.request.fingerprint,
                        expected.fingerprint,
                    )
                )
        except Exception:
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        if len(set(bindings)) != len(bindings):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        self._bindings = tuple(bindings)

    def __repr__(self) -> str:
        return "RecordedExternalPolicyRegistryAdapter(<redacted-st1407>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded external policy adapter serialization is disabled")

    def evaluate(
        self,
        request: ExternalPolicyRegistryRequest,
    ) -> ExternalPolicyRegistryReport:
        expected = evaluate_external_policy_registry(request)
        binding = (expected.request_sha256.value, expected.fingerprint)
        if sum(item[1:] == binding for item in self._bindings) != 1:
            fail_registry(RegistryFailureCode.EVALUATOR_UNAVAILABLE)
        return expected


__all__ = [
    "MAX_RECORDED_REGISTRY_FIXTURES",
    "RECORDED_FIXTURE_REQUEST_SHA256S",
    "RecordedExternalPolicyRegistryAdapter",
    "RecordedExternalPolicyRegistryFixture",
]
