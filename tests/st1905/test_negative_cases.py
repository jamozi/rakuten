"""Hostile input, drift, concurrency, and secret-safety tests for ST-1905."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
import json

import pytest

from raos.adapters.recorded_advanced_rank_provider import (
    RecordedAdvancedRankProviderSource,
)
from raos.application.analytics.advanced_rank_provider import (
    AdvancedRankProviderEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.advanced_rank_provider import (
    AdvancedRankProviderCommand,
    AdvancedRankProviderFailure,
    AdvancedRankProviderFailureCode,
    AdvancedRankProviderScope,
    RecordedAdvancedRankBatch,
    canonical_json_bytes,
    evaluate_recorded_provider,
)
from raos.domain.analytics.keyword_rank import Sha256Digest

from .support import command_for, fixture_bytes


def _json_payload(mutator: object) -> bytes:
    document = json.loads(fixture_bytes())
    assert callable(mutator)
    mutator(document)
    return canonical_json_bytes(document) + b"\n"


def _failure_code(payload: bytes) -> AdvancedRankProviderFailureCode:
    command = command_for(payload)
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        RecordedAdvancedRankProviderSource(payload).read(command)
    return caught.value.code


def test_provider_approval_and_release_decision_are_unrepresentable() -> None:
    baseline = command_for()
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        AdvancedRankProviderCommand(
            recording_id=baseline.recording_id,
            site_id=baseline.site_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            period=baseline.period,
            provider_approval_sha256=Sha256Digest("a" * 64),
            scope=AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY,
        )
    assert (
        caught.value.code
        is AdvancedRankProviderFailureCode.PROVIDER_APPROVAL_PROHIBITED
    )
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        AdvancedRankProviderCommand(
            recording_id=baseline.recording_id,
            site_id=baseline.site_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            period=baseline.period,
            release_decision_sha256=Sha256Digest("b" * 64),
            scope=AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY,
        )
    assert (
        caught.value.code is AdvancedRankProviderFailureCode.RELEASE_DECISION_PROHIBITED
    )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda value: value["document"].__setitem__("synthetic", False),
            AdvancedRankProviderFailureCode.DEPENDENCY_CONTRACT_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__(
                "adapter_version", "unapproved-adapter"
            ),
            AdvancedRankProviderFailureCode.DEPENDENCY_CONTRACT_DRIFT,
        ),
        (
            lambda value: value["observations"][0].__setitem__(
                "provider_code", "LIVE_PROVIDER"
            ),
            AdvancedRankProviderFailureCode.DEPENDENCY_CONTRACT_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__(
                "endpoint", "https://provider.invalid"
            ),
            AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][0].__setitem__(
                "query_text", "sensitive query"
            ),
            AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][0].__setitem__(
                "credential", "must-not-survive"
            ),
            AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][0].__setitem__("commission", "10"),
            AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][1].__setitem__(
                "provider_observation_id",
                value["observations"][0]["provider_observation_id"],
            ),
            AdvancedRankProviderFailureCode.DUPLICATE_PROVIDER_OBSERVATION,
        ),
        (
            lambda value: value["observations"].append(
                value["observations"][0]
                | {"provider_observation_id": "provider-observation-new"}
            ),
            AdvancedRankProviderFailureCode.DUPLICATE_CANONICAL_OBSERVATION,
        ),
    ],
)
def test_hostile_fixture_mutations_fail_closed(
    mutator: object,
    expected: AdvancedRankProviderFailureCode,
) -> None:
    assert _failure_code(_json_payload(mutator)) is expected


def test_duplicate_keys_floats_noncanonical_and_truncation_are_rejected() -> None:
    payload = fixture_bytes()
    duplicate = payload.replace(b'{"document":{', b'{"document":{"synthetic":true,', 1)
    assert (
        _failure_code(duplicate)
        is AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID
    )
    floating = payload.replace(b'"value":"4"', b'"value":4.0', 1)
    assert (
        _failure_code(floating)
        is AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID
    )
    pretty = (json.dumps(json.loads(payload), indent=2) + "\n").encode("utf-8")
    assert (
        _failure_code(pretty) is AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID
    )
    assert (
        _failure_code(payload[:-1])
        is AdvancedRankProviderFailureCode.SOURCE_BYTES_MISMATCH
    )


def test_command_batch_and_period_binding_drift_are_rejected() -> None:
    command = command_for()
    batch = RecordedAdvancedRankProviderSource(fixture_bytes()).read(command)
    wrong_command = replace(command, recording_id="st1905_other_recording")
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        evaluate_recorded_provider(wrong_command, batch)
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID

    wrong_batch = replace(batch, command_sha256=Sha256Digest("b" * 64))
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        evaluate_recorded_provider(command, wrong_batch)
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID

    narrow = command_for(date_from=date(2026, 8, 4), date_to=date(2026, 8, 4))
    narrow_batch = replace(batch, command_sha256=narrow.canonical_sha256)
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        evaluate_recorded_provider(narrow, narrow_batch)
    assert (
        caught.value.code is AdvancedRankProviderFailureCode.OBSERVATION_OUT_OF_PERIOD
    )


def test_source_exception_is_sanitized_to_closed_code() -> None:
    class FailingSource:
        def read(
            self, command: AdvancedRankProviderCommand
        ) -> RecordedAdvancedRankBatch:
            del command
            raise RuntimeError("sensitive-source-material")

    service = AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=FailingSource(),
    )
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        service.evaluate(command_for())
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_UNAVAILABLE
    assert "credential" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_one_shot_adapter_has_exactly_one_concurrent_winner() -> None:
    source = RecordedAdvancedRankProviderSource(fixture_bytes())
    command = command_for()

    def call() -> str:
        try:
            source.read(command)
        except AdvancedRankProviderFailure as failure:
            return failure.code.value
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _index: call(), range(32)))
    assert outcomes.count("SUCCESS") == 1
    assert outcomes.count(AdvancedRankProviderFailureCode.SOURCE_EXHAUSTED.value) == 31


def test_wrong_result_type_from_port_fails_closed() -> None:
    class WrongSource:
        def read(self, command: AdvancedRankProviderCommand) -> object:
            del command
            return {"raw_response": "must-not-escape"}

    service = AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=WrongSource(),  # type: ignore[arg-type]
    )
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        service.evaluate(command_for())
    assert caught.value.code is AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID


def test_default_disabled_service_does_not_consume_one_shot_source() -> None:
    source = RecordedAdvancedRankProviderSource(fixture_bytes())
    service = AdvancedRankProviderEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(AdvancedRankProviderFailure) as caught:
        service.evaluate(command_for(scope=AdvancedRankProviderScope.DISABLED))
    assert caught.value.code is AdvancedRankProviderFailureCode.FEATURE_DISABLED
    assert source.read(command_for()).recording_id == "st1905_recorded_provider_v1"
