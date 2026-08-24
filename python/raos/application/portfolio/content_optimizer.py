"""Fail-closed ENV-DEV/CI service for ST-1907 portfolio proposals."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.portfolio.content_optimizer import (
    ObservationPeriod,
    PortfolioOptimizationReport,
    PortfolioOptimizerCommand,
    PortfolioOptimizerFailure,
    PortfolioOptimizerFailureCode,
    PortfolioOptimizerScope,
    RecordedPortfolioOptimizationBatch,
    Sha256Digest,
    evaluate_recorded_portfolio_optimization,
    fail_portfolio_optimizer,
)
from raos.ports.content_portfolio_optimizer import (
    PortfolioOptimizationEvidenceSource,
)


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> PortfolioOptimizerCommand:
    if type(candidate) is not PortfolioOptimizerCommand:
        fail_portfolio_optimizer()
    try:
        return PortfolioOptimizerCommand(
            recording_id=candidate.recording_id,
            source_sha256=Sha256Digest(candidate.source_sha256.value),
            source_bytes=candidate.source_bytes,
            contract_sha256=Sha256Digest(candidate.contract_sha256.value),
            expected_dependency_pack_sha256=Sha256Digest(
                candidate.expected_dependency_pack_sha256.value
            ),
            measurement_contract_sha256=Sha256Digest(
                candidate.measurement_contract_sha256.value
            ),
            signal_policy_sha256=Sha256Digest(candidate.signal_policy_sha256.value),
            program=candidate.program,
            period=ObservationPeriod(
                start_date=candidate.period.start_date,
                end_exclusive_date=candidate.period.end_exclusive_date,
            ),
            release_decision_sha256=candidate.release_decision_sha256,
            method_version=candidate.method_version,
            parser_version=candidate.parser_version,
            scope=candidate.scope,
        )
    except PortfolioOptimizerFailure:
        raise
    except Exception:
        fail_portfolio_optimizer()


@final
class ContentPortfolioOptimizerService:
    """Evaluate one local recording without mutation or operational authority."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: PortfolioOptimizationEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), PortfolioOptimizationEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_portfolio_optimizer()
        self._source = source

    def evaluate(
        self, command: PortfolioOptimizerCommand
    ) -> PortfolioOptimizationReport:
        normalized = _validated_command(command)
        if (
            normalized.scope
            is not PortfolioOptimizerScope.RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY
        ):
            fail_portfolio_optimizer(PortfolioOptimizerFailureCode.FEATURE_DISABLED)
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except PortfolioOptimizerFailure:
            raise
        except Exception:
            fail_portfolio_optimizer(PortfolioOptimizerFailureCode.SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedPortfolioOptimizationBatch:
            fail_portfolio_optimizer(
                PortfolioOptimizerFailureCode.SOURCE_RESULT_INVALID
            )
        return evaluate_recorded_portfolio_optimization(normalized, observed)


__all__ = ("ContentPortfolioOptimizerService",)
