"""Fail-closed recorded evaluation harness for ST-1206."""

from __future__ import annotations

from collections import Counter
from typing import final

from raos.domain.analytics.keyword_rank import (
    DEFAULT_KEYWORD_RANK_SCOPE,
    KEYWORD_RANK_PARSER_VERSION,
    SYNTHETIC_PROVIDER_CODE,
    KeywordRankBatch,
    KeywordRankBoundaryStatus,
    KeywordRankEvaluationCommand,
    KeywordRankEvaluationSnapshot,
    KeywordRankFailure,
    KeywordRankFailureCode,
    KeywordRankImportState,
    KeywordRankMetricCount,
    KeywordRankMetricType,
    KeywordRankObservation,
    KeywordRankPeriod,
    KeywordRankScope,
    KeywordRankSourceKind,
    fail_keyword_rank,
)
from raos.ports.keyword_rank import KeywordRankSource


def _validated_command(candidate: object) -> KeywordRankEvaluationCommand:
    if type(candidate) is not KeywordRankEvaluationCommand:
        fail_keyword_rank()
    try:
        return KeywordRankEvaluationCommand(
            recording_id=candidate.recording_id,
            site_id=candidate.site_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            period=KeywordRankPeriod(
                date_from=candidate.period.date_from,
                date_to=candidate.period.date_to,
            ),
            parser_version=candidate.parser_version,
            scope=candidate.scope,
        )
    except KeywordRankFailure:
        raise
    except Exception:
        fail_keyword_rank()


def _validated_batch(
    candidate: object, command: KeywordRankEvaluationCommand
) -> KeywordRankBatch:
    if type(candidate) is not KeywordRankBatch:
        fail_keyword_rank(KeywordRankFailureCode.SOURCE_RESULT_INVALID)
    try:
        observations = tuple(
            KeywordRankObservation(
                keyword_id=row.keyword_id,
                locale=row.locale,
                device=row.device,
                observation_date=row.observation_date,
                metric_type=row.metric_type,
                value=row.value,
                unit=row.unit,
                provider_code=row.provider_code,
                confidence=row.confidence,
                raw_row_sha256=row.raw_row_sha256,
            )
            for row in candidate.observations
            if type(row) is KeywordRankObservation
        )
        if len(observations) != len(candidate.observations):
            fail_keyword_rank(KeywordRankFailureCode.SOURCE_RESULT_INVALID)
        normalized = KeywordRankBatch(
            recording_id=candidate.recording_id,
            site_id=candidate.site_id,
            command_sha256=candidate.command_sha256,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            source_kind=candidate.source_kind,
            parser_version=candidate.parser_version,
            observations=observations,
        )
    except KeywordRankFailure:
        raise
    except Exception:
        fail_keyword_rank(KeywordRankFailureCode.SOURCE_RESULT_INVALID)
    if (
        normalized.recording_id != command.recording_id
        or normalized.site_id != command.site_id
        or normalized.command_sha256 != command.canonical_sha256
        or normalized.source_sha256 != command.source_sha256
        or normalized.source_bytes != command.source_bytes
        or normalized.source_kind is not KeywordRankSourceKind.RECORDED_MANUAL_CSV
        or normalized.parser_version != KEYWORD_RANK_PARSER_VERSION
    ):
        fail_keyword_rank(KeywordRankFailureCode.SOURCE_RESULT_INVALID)
    return normalized


@final
class KeywordRankEvaluationService:
    """Evaluate a caller-bound synthetic CSV without importing any observation."""

    __slots__ = ("_source",)

    def __init__(self, *, source: KeywordRankSource) -> None:
        if not isinstance(source, KeywordRankSource):
            fail_keyword_rank()
        self._source = source

    def evaluate(
        self, command: KeywordRankEvaluationCommand
    ) -> KeywordRankEvaluationSnapshot:
        normalized_command = _validated_command(command)
        if (
            normalized_command.scope
            is not KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY
        ):
            fail_keyword_rank(KeywordRankFailureCode.FEATURE_DISABLED)
        observed: object = None
        source_unavailable = False
        try:
            observed = self._source.read(normalized_command)
        except KeywordRankFailure:
            raise
        except Exception:
            source_unavailable = True
        if source_unavailable:
            fail_keyword_rank(KeywordRankFailureCode.SOURCE_UNAVAILABLE)
        batch = _validated_batch(observed, normalized_command)

        identities: set[object] = set()
        for row in batch.observations:
            if row.identity in identities:
                fail_keyword_rank(KeywordRankFailureCode.DUPLICATE_OBSERVATION)
            identities.add(row.identity)
            if not (
                normalized_command.period.date_from
                <= row.observation_date
                <= normalized_command.period.date_to
            ):
                fail_keyword_rank(KeywordRankFailureCode.OBSERVATION_OUT_OF_PERIOD)
            if row.provider_code != SYNTHETIC_PROVIDER_CODE:
                fail_keyword_rank(KeywordRankFailureCode.SOURCE_RESULT_INVALID)

        counts = Counter(row.metric_type for row in batch.observations)
        metric_counts = tuple(
            KeywordRankMetricCount(metric_type=metric_type, count=counts[metric_type])
            for metric_type in KeywordRankMetricType
        )
        dates = tuple(row.observation_date for row in batch.observations)
        return KeywordRankEvaluationSnapshot(
            recording_id=batch.recording_id,
            site_id=batch.site_id,
            command_sha256=batch.command_sha256,
            source_sha256=batch.source_sha256,
            normalized_sha256=batch.normalized_sha256,
            source_kind=batch.source_kind,
            parser_version=batch.parser_version,
            row_count=len(batch.observations),
            unique_keyword_count=len({row.keyword_id for row in batch.observations}),
            metric_counts=metric_counts,
            observation_from=min(dates),
            observation_to=max(dates),
            scope=normalized_command.scope,
            default_scope=DEFAULT_KEYWORD_RANK_SCOPE,
            import_state=KeywordRankImportState.EVALUATED_NOT_IMPORTED,
            persistence=KeywordRankBoundaryStatus.NOT_EXECUTED,
            provider=KeywordRankBoundaryStatus.NOT_EXECUTED,
            network=KeywordRankBoundaryStatus.NOT_EXECUTED,
            credentials=KeywordRankBoundaryStatus.NOT_USED,
            serp_scrape=KeywordRankBoundaryStatus.FORBIDDEN,
            tracking_activation=KeywordRankBoundaryStatus.DISABLED,
            kpi_read_model_write=KeywordRankBoundaryStatus.NOT_EXECUTED,
            recommendation_input=KeywordRankBoundaryStatus.DISABLED,
            formal_tst_030=KeywordRankBoundaryStatus.NOT_EXECUTED,
            canonical_status=KeywordRankBoundaryStatus.DEFERRED_POST_MVP,
        )


__all__ = ["KeywordRankEvaluationService"]
