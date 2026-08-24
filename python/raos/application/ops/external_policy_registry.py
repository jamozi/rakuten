"""Fail-closed application service for the recorded ST-1407 exchange."""

from __future__ import annotations

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
from raos.ports.external_policy_registry import ExternalPolicyRegistryExchange


def _supports_exchange(value: object) -> bool:
    try:
        return isinstance(value, ExternalPolicyRegistryExchange)
    except Exception:
        return False


@final
class ExternalPolicyRegistryService:
    """Call one read-only collaborator once and independently verify its result."""

    __slots__ = ("_exchange",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        exchange: ExternalPolicyRegistryExchange,
    ) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_registry(RegistryFailureCode.DEVELOPMENT_ONLY)
        if not _supports_exchange(exchange):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        self._exchange = exchange

    def __repr__(self) -> str:
        return "ExternalPolicyRegistryService(<redacted-st1407>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("external policy registry service serialization is disabled")

    def evaluate(
        self,
        request: ExternalPolicyRegistryRequest,
    ) -> ExternalPolicyRegistryReport:
        expected = evaluate_external_policy_registry(request)
        request_sha256 = expected.request_sha256.value
        outcome: object = None
        unavailable = False
        try:
            outcome = self._exchange.evaluate(request)
        except Exception:
            unavailable = True
        if unavailable:
            fail_registry(RegistryFailureCode.EVALUATOR_UNAVAILABLE)

        request_unchanged = False
        try:
            rechecked = evaluate_external_policy_registry(request)
            request_unchanged = (
                rechecked.request_sha256.value == request_sha256
                and rechecked.fingerprint == expected.fingerprint
            )
        except Exception:
            request_unchanged = False
        if not request_unchanged:
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)

        matches = False
        if type(outcome) is ExternalPolicyRegistryReport:
            try:
                matches = (
                    outcome == expected
                    and outcome.fingerprint == expected.fingerprint
                    and registry_report_json(outcome) == registry_report_json(expected)
                )
            except Exception:
                matches = False
        if not matches:
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)
        return expected


__all__ = ["ExternalPolicyRegistryService"]
