"""Positive and authority-boundary behavior for ST-1902."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import pickle

import pytest

from raos.adapters.recorded_champion_challenger import (
    RecordedChampionChallengerSource,
)
from raos.application.ai.champion_challenger import (
    ChampionChallengerShadowService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.champion_challenger import (
    DEFAULT_CHAMPION_CHALLENGER_SCOPE,
    ChallengerState,
    ChampionChallengerScope,
    RecordedShadowBatch,
    ShadowBoundaryStatus,
    ShadowOutcome,
    ShadowRoutingFailure,
    ShadowRoutingFailureCode,
    evaluate_recorded_shadow,
    report_projection,
)
from raos.ports.champion_challenger import RecordedShadowEvidenceSource

from .support import command_for, fixture_bytes, service_for


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, command: object) -> RecordedShadowBatch:
        del command
        self.calls += 1
        raise AssertionError("disabled service reached source")


class _HostileSource:
    read = "not-callable"


def test_default_scope_is_disabled_and_fails_before_source_call() -> None:
    source = _CountingSource()
    service = ChampionChallengerShadowService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    command = command_for(scope=DEFAULT_CHAMPION_CHALLENGER_SCOPE)
    with pytest.raises(ShadowRoutingFailure) as caught:
        service.evaluate(command)
    assert caught.value.code is ShadowRoutingFailureCode.FEATURE_DISABLED
    assert source.calls == 0


@pytest.mark.parametrize(
    "environment",
    [
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ],
)
def test_nonlocal_environments_are_rejected(environment: RuntimeEnvironment) -> None:
    with pytest.raises(ShadowRoutingFailure) as caught:
        ChampionChallengerShadowService(
            environment=environment,
            source=RecordedChampionChallengerSource(fixture_bytes()),
        )
    assert caught.value.code is ShadowRoutingFailureCode.INVALID_ARGUMENT


def test_port_is_provider_neutral_and_runtime_checkable() -> None:
    source = RecordedChampionChallengerSource(fixture_bytes())
    assert isinstance(source, RecordedShadowEvidenceSource)
    with pytest.raises(ShadowRoutingFailure):
        ChampionChallengerShadowService(
            environment=RuntimeEnvironment.CI,
            source=_HostileSource(),  # type: ignore[arg-type]
        )
    assert tuple(ChampionChallengerScope) == (
        ChampionChallengerScope.DISABLED,
        ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY,
    )
    for name in ("activate", "publish", "release", "route", "send", "write"):
        assert not hasattr(source, name)
        assert not hasattr(ChampionChallengerShadowService, name)


def test_recorded_shadow_is_deterministic_and_always_keeps_champion() -> None:
    first = service_for().evaluate(command_for())
    second = service_for().evaluate(command_for())
    assert first == second
    assert first.report_sha256.value == (
        "a4aa242024d3feeed99133228f9f49a3ce2bfddbecc6e2f61fc5219e93ca6581"
    )
    assert (
        first.cohort_size,
        first.champion_wins,
        first.challenger_wins,
        first.ties,
    ) == (4, 1, 2, 1)
    assert (
        first.champion_mean_score_micros,
        first.challenger_mean_score_micros,
        first.challenger_delta_micros,
    ) == (895_000, 897_500, 2_500)
    assert first.outcome is ShadowOutcome.KEEP_CHAMPION_INCOMPLETE_EVIDENCE
    assert first.challenger_state is ChallengerState.SHADOW_NONAUTHORITATIVE
    assert first.blockers == (
        "CANARY_RELEASE_DECISION_ABSENT",
        "CANARY_UNREACHABLE",
        "FORMAL_TST_032_NOT_EXECUTED",
        "RECORDED_SYNTHETIC_ONLY",
        "ST0708_RELEASE_EVIDENCE_INCOMPLETE",
    )


def test_report_has_no_mutation_or_operational_authority() -> None:
    report = service_for().evaluate(command_for())
    assert report.authority == "NONE"
    assert report.canary_allocation_percent == 0
    assert report.canary is ShadowBoundaryStatus.RELEASE_DECISION_REQUIRED
    assert report.canonical_status is ShadowBoundaryStatus.DEFERRED_POST_MVP
    assert report.route_mutation is ShadowBoundaryStatus.FORBIDDEN
    assert report.editorial_mutation is ShadowBoundaryStatus.FORBIDDEN
    assert report.publication is ShadowBoundaryStatus.FORBIDDEN
    assert report.network is ShadowBoundaryStatus.FORBIDDEN
    assert report.provider is ShadowBoundaryStatus.NOT_EXECUTED
    assert report.release is ShadowBoundaryStatus.NOT_EXECUTED
    assert report.production is ShadowBoundaryStatus.NOT_EXECUTED

    projection = report_projection(report)
    serialized_names = {str(key).lower() for key in _walk_keys(projection)}
    prohibited_fragments = {
        "article",
        "body",
        "content",
        "cta",
        "finance",
        "offer",
        "personal",
        "price",
        "prompt",
        "recommendation",
        "response",
        "review",
        "snapshot",
        "url",
    }
    assert not any(
        fragment in name
        for name in serialized_names
        for fragment in prohibited_fragments
    )


def _walk_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(value) + tuple(
            nested for child in value.values() for nested in _walk_keys(child)
        )
    if isinstance(value, list):
        return tuple(nested for child in value for nested in _walk_keys(child))
    return ()


def test_values_are_immutable_redacted_and_not_pickleable() -> None:
    report = service_for().evaluate(command_for())
    assert "redacted" in repr(report)
    assert "redacted" in str(report)
    with pytest.raises(FrozenInstanceError):
        report.authority = "ROUTE"  # type: ignore[misc]
    for value in (report, report.source_sha256):
        with pytest.raises(TypeError):
            pickle.dumps(value)
    with pytest.raises(ShadowRoutingFailure) as caught:
        service_for().evaluate(object())  # type: ignore[arg-type]
    assert str(caught.value) == ShadowRoutingFailureCode.INVALID_ARGUMENT.value
    assert "redacted" not in str(caught.value)
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)


def test_source_is_one_shot_and_replay_is_rejected() -> None:
    source = RecordedChampionChallengerSource(fixture_bytes())
    command = command_for()
    first = source.read(command)
    assert first.recording_id == command.recording_id
    with pytest.raises(ShadowRoutingFailure) as caught:
        source.read(command)
    assert caught.value.code is ShadowRoutingFailureCode.SOURCE_EXHAUSTED
    assert "redacted" in repr(source)
    with pytest.raises(TypeError):
        pickle.dumps(source)


def test_zero_tolerance_and_schema_failures_can_only_pause_challenger() -> None:
    command = command_for()
    baseline = RecordedChampionChallengerSource(fixture_bytes()).read(command)
    zero_observation = replace(
        baseline.observations[0], challenger_zero_tolerance_failures=1
    )
    zero_batch = replace(
        baseline, observations=(zero_observation, *baseline.observations[1:])
    )
    zero_report = evaluate_recorded_shadow(command, zero_batch)
    assert zero_report.outcome is ShadowOutcome.KEEP_CHAMPION_ZERO_TOLERANCE
    assert zero_report.challenger_state is ChallengerState.PAUSED_RECORDED_ONLY
    assert "ZERO_TOLERANCE_FAILURE_OBSERVED" in zero_report.blockers

    schema_observation = replace(
        baseline.observations[0], challenger_schema_valid=False
    )
    schema_batch = replace(
        baseline, observations=(schema_observation, *baseline.observations[1:])
    )
    schema_report = evaluate_recorded_shadow(command, schema_batch)
    assert schema_report.outcome is ShadowOutcome.KEEP_CHAMPION_SCHEMA_FAILURE
    assert schema_report.challenger_state is ChallengerState.PAUSED_RECORDED_ONLY
    assert "SCHEMA_FAILURE_OBSERVED" in schema_report.blockers


def test_report_schema_contains_only_closed_projection_fields() -> None:
    names = {
        field.name for field in fields(type(service_for().evaluate(command_for())))
    }
    assert not names.intersection(
        {
            "article",
            "content",
            "cta",
            "editorial_selection",
            "publication_snapshot",
            "recommendation_order",
            "route_selection",
        }
    )
