"""Positive and authority-boundary behavior for ST-1905."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import pickle

import pytest

from raos.adapters.recorded_advanced_rank_provider import (
    RecordedAdvancedRankProviderSource,
)
from raos.application.analytics.advanced_rank_provider import (
    AdvancedRankProviderEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.advanced_rank_provider import (
    DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE,
    AdvancedRankProviderBoundaryStatus,
    AdvancedRankProviderFailure,
    AdvancedRankProviderFailureCode,
    AdvancedRankProviderOutcome,
    AdvancedRankProviderScope,
    RecordedAdvancedRankBatch,
    report_projection,
)
from raos.domain.analytics.keyword_rank import KeywordRankMetricType
from raos.ports.advanced_rank_provider import AdvancedRankProviderEvidenceSource

from .support import command_for, fixture_bytes, service_for


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, command: object) -> RecordedAdvancedRankBatch:
        del command
        self.calls += 1
        raise AssertionError("disabled service reached source")


class _HostileSource:
    read = "not-callable"


def _walk_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(value) + tuple(
            nested for child in value.values() for nested in _walk_keys(child)
        )
    if isinstance(value, list):
        return tuple(nested for child in value for nested in _walk_keys(child))
    return ()


def test_default_scope_is_disabled_and_fails_before_source_call() -> None:
    source = _CountingSource()
    service = AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        service.evaluate(command_for(scope=DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE))
    assert caught.value.code is AdvancedRankProviderFailureCode.FEATURE_DISABLED
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
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        AdvancedRankProviderEvaluationService(
            environment=environment,
            source=RecordedAdvancedRankProviderSource(fixture_bytes()),
        )
    assert caught.value.code is AdvancedRankProviderFailureCode.INVALID_ARGUMENT


def test_port_is_provider_neutral_and_runtime_checkable() -> None:
    source = RecordedAdvancedRankProviderSource(fixture_bytes())
    assert isinstance(source, AdvancedRankProviderEvidenceSource)
    with pytest.raises(AdvancedRankProviderFailure):
        AdvancedRankProviderEvaluationService(
            environment=RuntimeEnvironment.CI,
            source=_HostileSource(),  # type: ignore[arg-type]
        )
    assert tuple(AdvancedRankProviderScope) == (
        AdvancedRankProviderScope.DISABLED,
        AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY,
    )
    for name in (
        "activate",
        "approve",
        "connect",
        "fetch",
        "publish",
        "release",
        "send",
        "write",
    ):
        assert not hasattr(source, name)
        assert not hasattr(AdvancedRankProviderEvaluationService, name)


def test_recorded_evaluation_is_deterministic_and_st1206_compatible() -> None:
    first = service_for().evaluate(command_for())
    second = service_for().evaluate(command_for())
    assert first == second
    assert (
        first.outcome is AdvancedRankProviderOutcome.CONTRACT_COMPATIBLE_RECORDED_ONLY
    )
    assert first.row_count == 6
    assert first.unique_keyword_count == 2
    assert {row.metric_type: row.count for row in first.metric_counts} == {
        KeywordRankMetricType.POSITION: 2,
        KeywordRankMetricType.SEARCH_VOLUME: 2,
        KeywordRankMetricType.DIFFICULTY: 2,
    }
    assert first.observation_from.isoformat() == "2026-08-03"
    assert first.observation_to.isoformat() == "2026-08-04"
    assert first.blockers == (
        "FORMAL_TST_032_NOT_EXECUTED",
        "LIVE_PROVIDER_VALIDATION_NOT_EXECUTED",
        "OD_004_PROVIDER_SELECTION_UNRESOLVED",
        "PROVIDER_APPROVAL_ABSENT",
        "RECORDED_SYNTHETIC_ONLY",
        "RELEASE_DECISION_ABSENT",
    )


def test_report_has_no_operational_or_editorial_authority() -> None:
    report = service_for().evaluate(command_for())
    assert report.authority == "NONE"
    assert (
        report.provider_selection
        is AdvancedRankProviderBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    assert report.provider_approval is AdvancedRankProviderBoundaryStatus.ABSENT
    assert (
        report.release_decision
        is AdvancedRankProviderBoundaryStatus.RELEASE_DECISION_REQUIRED
    )
    assert report.adapter_activation is AdvancedRankProviderBoundaryStatus.DISABLED
    assert report.provider_call is AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    assert report.network is AdvancedRankProviderBoundaryStatus.FORBIDDEN
    assert report.credentials is AdvancedRankProviderBoundaryStatus.NOT_USED
    assert report.serp_scrape is AdvancedRankProviderBoundaryStatus.FORBIDDEN
    assert report.recommendation_input is AdvancedRankProviderBoundaryStatus.DISABLED
    assert report.publication is AdvancedRankProviderBoundaryStatus.FORBIDDEN
    assert report.production is AdvancedRankProviderBoundaryStatus.NOT_EXECUTED


def test_report_projection_has_only_closed_non_sensitive_fields() -> None:
    report = service_for().evaluate(command_for())
    projection = report_projection(report)
    keys = {key.lower() for key in _walk_keys(projection)}
    prohibited = {
        "affiliate",
        "commission",
        "content",
        "credential_value",
        "endpoint",
        "epc",
        "finance",
        "keyword_text",
        "personal",
        "profit",
        "query_text",
        "raw_response",
        "recommendation_order",
        "review",
        "rpm",
        "url",
    }
    assert not keys.intersection(prohibited)
    names = {
        field.name for field in fields(type(service_for().evaluate(command_for())))
    }
    assert not names.intersection(prohibited)
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        report_projection(replace(report, authority="PROVIDER"))
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID


def test_values_are_immutable_redacted_and_not_pickleable() -> None:
    report = service_for().evaluate(command_for())
    assert "redacted" in repr(report)
    assert "redacted" in str(report)
    with pytest.raises(FrozenInstanceError):
        report.authority = "PROVIDER"  # type: ignore[misc]
    for value in (report, report.source_sha256):
        with pytest.raises(TypeError):
            pickle.dumps(value)
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        service_for().evaluate(object())  # type: ignore[arg-type]
    assert str(caught.value) == AdvancedRankProviderFailureCode.INVALID_ARGUMENT.value
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)


def test_source_is_one_shot_and_replay_is_rejected() -> None:
    source = RecordedAdvancedRankProviderSource(fixture_bytes())
    command = command_for()
    assert source.read(command).recording_id == command.recording_id
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        source.read(command)
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_EXHAUSTED
    assert "redacted" in repr(source)
    assert "redacted" in str(source)
    with pytest.raises(TypeError):
        pickle.dumps(source)
