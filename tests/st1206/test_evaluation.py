"""Deterministic happy-path and feature-gate tests for ST-1206."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
import pickle

import pytest

from conftest import FIXTURE_BYTES, command_for, service_for
from raos.application.analytics.keyword_rank_import import (
    KeywordRankEvaluationService,
)
from raos.domain.analytics.keyword_rank import (
    DEFAULT_KEYWORD_RANK_SCOPE,
    SYNTHETIC_PROVIDER_CODE,
    KeywordRankBoundaryStatus,
    KeywordRankEvaluationCommand,
    KeywordRankFailure,
    KeywordRankFailureCode,
    KeywordRankImportState,
    KeywordRankMetricType,
    KeywordRankScope,
)


def test_recorded_fixture_evaluates_to_fixed_redacted_summary() -> None:
    snapshot = service_for().evaluate(command_for())

    assert snapshot.row_count == 6
    assert snapshot.unique_keyword_count == 2
    assert snapshot.observation_from == date(2026, 8, 1)
    assert snapshot.observation_to == date(2026, 8, 2)
    assert [(row.metric_type, row.count) for row in snapshot.metric_counts] == [
        (KeywordRankMetricType.POSITION, 2),
        (KeywordRankMetricType.SEARCH_VOLUME, 2),
        (KeywordRankMetricType.DIFFICULTY, 2),
    ]
    assert (
        snapshot.normalized_sha256.value
        == "b2767fb7b6d59537d918ba95e3082c1b3380c9b51fb1eeabfa65fb85d96d6c64"
    )
    assert snapshot.import_state is KeywordRankImportState.EVALUATED_NOT_IMPORTED
    assert snapshot.scope is KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY
    assert snapshot.default_scope is KeywordRankScope.DISABLED


def test_evaluation_keeps_every_external_and_mutating_boundary_closed() -> None:
    snapshot = service_for().evaluate(command_for())

    assert snapshot.persistence is KeywordRankBoundaryStatus.NOT_EXECUTED
    assert snapshot.provider is KeywordRankBoundaryStatus.NOT_EXECUTED
    assert snapshot.network is KeywordRankBoundaryStatus.NOT_EXECUTED
    assert snapshot.credentials is KeywordRankBoundaryStatus.NOT_USED
    assert snapshot.serp_scrape is KeywordRankBoundaryStatus.FORBIDDEN
    assert snapshot.tracking_activation is KeywordRankBoundaryStatus.DISABLED
    assert snapshot.kpi_read_model_write is KeywordRankBoundaryStatus.NOT_EXECUTED
    assert snapshot.recommendation_input is KeywordRankBoundaryStatus.DISABLED
    assert snapshot.formal_tst_030 is KeywordRankBoundaryStatus.NOT_EXECUTED
    assert snapshot.canonical_status is KeywordRankBoundaryStatus.DEFERRED_POST_MVP


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, command: object) -> object:
        del command
        self.calls += 1
        raise AssertionError("disabled scope must not call the source")


def test_default_scope_is_disabled_and_rejected_before_port_call() -> None:
    explicit = command_for(scope=KeywordRankScope.DISABLED)
    defaulted = KeywordRankEvaluationCommand(
        recording_id=explicit.recording_id,
        site_id=explicit.site_id,
        source_sha256=explicit.source_sha256,
        source_bytes=explicit.source_bytes,
        period=explicit.period,
    )
    source = _CountingSource()

    assert DEFAULT_KEYWORD_RANK_SCOPE is KeywordRankScope.DISABLED
    assert defaulted.scope is KeywordRankScope.DISABLED
    with pytest.raises(KeywordRankFailure) as caught:
        KeywordRankEvaluationService(source=source).evaluate(defaulted)
    assert caught.value.code is KeywordRankFailureCode.FEATURE_DISABLED
    assert source.calls == 0


def test_same_fixture_and_command_produce_same_summary_hashes() -> None:
    first = service_for().evaluate(command_for())
    second = service_for().evaluate(command_for())

    assert first.command_sha256 == second.command_sha256
    assert first.source_sha256 == second.source_sha256
    assert first.normalized_sha256 == second.normalized_sha256


def test_snapshot_contains_no_observation_rows_or_raw_keyword_text() -> None:
    snapshot = service_for().evaluate(command_for())
    annotations = snapshot.__annotations__

    assert "observations" not in annotations
    assert "query" not in annotations
    assert "keyword_text" not in annotations
    assert SYNTHETIC_PROVIDER_CODE not in repr(snapshot)
    assert "018f3e90" not in repr(snapshot)
    assert FIXTURE_BYTES.decode("ascii") not in repr(snapshot)


def test_values_are_frozen_redacted_and_non_pickleable() -> None:
    command = command_for()
    snapshot = service_for().evaluate(command)

    with pytest.raises(FrozenInstanceError):
        command.recording_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        pickle.dumps(command)
    with pytest.raises(TypeError):
        pickle.dumps(snapshot)
    assert repr(command) == "KeywordRankEvaluationCommand(<redacted-keyword-rank>)"
    assert str(snapshot) == "<redacted-keyword-rank>"
