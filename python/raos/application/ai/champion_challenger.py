"""Fail-closed application service for ST-1902 recorded shadow evaluation."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.champion_challenger import (
    ChampionChallengerScope,
    RecordedShadowBatch,
    ShadowRoutingCommand,
    ShadowRoutingFailure,
    ShadowRoutingFailureCode,
    ShadowRoutingReport,
    evaluate_recorded_shadow,
    fail_shadow_routing,
)
from raos.ports.champion_challenger import RecordedShadowEvidenceSource


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> ShadowRoutingCommand:
    if type(candidate) is not ShadowRoutingCommand:
        fail_shadow_routing()
    try:
        return ShadowRoutingCommand(
            recording_id=candidate.recording_id,
            task_code=candidate.task_code,
            route_code=candidate.route_code,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            policy_version=candidate.policy_version,
            canary_allocation_percent=candidate.canary_allocation_percent,
            release_decision_sha256=candidate.release_decision_sha256,
            parser_version=candidate.parser_version,
            scope=candidate.scope,
        )
    except ShadowRoutingFailure:
        raise
    except Exception:
        fail_shadow_routing()


@final
class ChampionChallengerShadowService:
    """Evaluate one local recording without routing, mutation, or activation."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: RecordedShadowEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), RecordedShadowEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_shadow_routing()
        self._source = source

    def evaluate(self, command: ShadowRoutingCommand) -> ShadowRoutingReport:
        normalized = _validated_command(command)
        if (
            normalized.scope
            is not ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY
        ):
            fail_shadow_routing(ShadowRoutingFailureCode.FEATURE_DISABLED)
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except ShadowRoutingFailure:
            raise
        except Exception:
            fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedShadowBatch:
            fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_RESULT_INVALID)
        return evaluate_recorded_shadow(normalized, observed)


__all__ = ["ChampionChallengerShadowService"]
