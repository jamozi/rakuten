"""Fail-closed application service for ST-1905 recorded contract evaluation."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.advanced_rank_provider import (
    AdvancedRankProviderCommand,
    AdvancedRankProviderFailure,
    AdvancedRankProviderFailureCode,
    AdvancedRankProviderReport,
    AdvancedRankProviderScope,
    AdvancedRankProviderSourceKind,
    RecordedAdvancedRankBatch,
    RecordedAdvancedRankObservation,
    evaluate_recorded_provider,
    fail_advanced_rank_provider,
)
from raos.domain.analytics.keyword_rank import (
    KeywordRankObservation,
    KeywordRankPeriod,
)
from raos.ports.advanced_rank_provider import AdvancedRankProviderEvidenceSource


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> AdvancedRankProviderCommand:
    if type(candidate) is not AdvancedRankProviderCommand:
        fail_advanced_rank_provider()
    try:
        return AdvancedRankProviderCommand(
            recording_id=candidate.recording_id,
            site_id=candidate.site_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            period=KeywordRankPeriod(
                date_from=candidate.period.date_from,
                date_to=candidate.period.date_to,
            ),
            provider_approval_sha256=candidate.provider_approval_sha256,
            release_decision_sha256=candidate.release_decision_sha256,
            adapter_version=candidate.adapter_version,
            parser_version=candidate.parser_version,
            scope=candidate.scope,
        )
    except AdvancedRankProviderFailure:
        raise
    except Exception:
        fail_advanced_rank_provider()


def _validated_batch(
    candidate: object,
    command: AdvancedRankProviderCommand,
) -> RecordedAdvancedRankBatch:
    if type(candidate) is not RecordedAdvancedRankBatch:
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
        )
    try:
        observations = tuple(
            RecordedAdvancedRankObservation(
                provider_observation_id=row.provider_observation_id,
                observation=KeywordRankObservation(
                    keyword_id=row.observation.keyword_id,
                    locale=row.observation.locale,
                    device=row.observation.device,
                    observation_date=row.observation.observation_date,
                    metric_type=row.observation.metric_type,
                    value=row.observation.value,
                    unit=row.observation.unit,
                    provider_code=row.observation.provider_code,
                    confidence=row.observation.confidence,
                    raw_row_sha256=row.observation.raw_row_sha256,
                ),
            )
            for row in candidate.observations
            if type(row) is RecordedAdvancedRankObservation
            and type(row.observation) is KeywordRankObservation
        )
        if len(observations) != len(candidate.observations):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
            )
        normalized = RecordedAdvancedRankBatch(
            recording_id=candidate.recording_id,
            site_id=candidate.site_id,
            command_sha256=candidate.command_sha256,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            source_kind=candidate.source_kind,
            fixture_profile=candidate.fixture_profile,
            parser_version=candidate.parser_version,
            adapter_version=candidate.adapter_version,
            observations=observations,
        )
    except AdvancedRankProviderFailure:
        raise
    except Exception:
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
        )
    if (
        normalized.recording_id != command.recording_id
        or normalized.site_id != command.site_id
        or normalized.command_sha256 != command.canonical_sha256
        or normalized.source_sha256 != command.source_sha256
        or normalized.source_bytes != command.source_bytes
        or normalized.source_kind
        is not AdvancedRankProviderSourceKind.RECORDED_SYNTHETIC_PROVIDER_RESPONSE
        or normalized.parser_version != command.parser_version
        or normalized.adapter_version != command.adapter_version
    ):
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
        )
    return normalized


@final
class AdvancedRankProviderEvaluationService:
    """Evaluate one local recording without provider or operational authority."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: AdvancedRankProviderEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), AdvancedRankProviderEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_advanced_rank_provider()
        self._source = source

    def evaluate(
        self,
        command: AdvancedRankProviderCommand,
    ) -> AdvancedRankProviderReport:
        normalized_command = _validated_command(command)
        if (
            normalized_command.scope
            is not AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
        ):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.FEATURE_DISABLED
            )
        observed: object = None
        source_unavailable = False
        try:
            observed = self._source.read(normalized_command)
        except AdvancedRankProviderFailure:
            raise
        except Exception:
            source_unavailable = True
        if source_unavailable:
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.SOURCE_UNAVAILABLE
            )
        batch = _validated_batch(observed, normalized_command)
        return evaluate_recorded_provider(normalized_command, batch)


__all__ = ["AdvancedRankProviderEvaluationService"]
