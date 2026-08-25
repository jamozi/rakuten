"""Hostile input, drift, and concurrency tests for ST-1902."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json

import pytest

from raos.adapters.recorded_champion_challenger import (
    RecordedChampionChallengerSource,
)
from raos.domain.ai.champion_challenger import (
    ChampionChallengerScope,
    RecordedShadowBatch,
    ShadowRoutingCommand,
    ShadowRoutingFailure,
    ShadowRoutingFailureCode,
    Sha256Digest,
    evaluate_recorded_shadow,
)

from .support import command_for, fixture_bytes


def _json_payload(mutator: object) -> bytes:
    document = json.loads(fixture_bytes())
    assert callable(mutator)
    mutator(document)
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _read(payload: bytes) -> RecordedShadowBatch:
    return RecordedChampionChallengerSource(payload).read(command_for(payload))


def _failure_code(payload: bytes) -> ShadowRoutingFailureCode:
    with pytest.raises(ShadowRoutingFailure) as caught:
        _read(payload)
    return caught.value.code


def test_nonzero_canary_and_release_decision_are_unrepresentable() -> None:
    baseline = command_for()
    with pytest.raises(ShadowRoutingFailure) as caught:
        ShadowRoutingCommand(
            recording_id=baseline.recording_id,
            task_code=baseline.task_code,
            route_code=baseline.route_code,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            policy_version=baseline.policy_version,
            canary_allocation_percent=1,
            scope=ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY,
        )
    assert caught.value.code is ShadowRoutingFailureCode.CANARY_ALLOCATION_PROHIBITED

    with pytest.raises(ShadowRoutingFailure) as caught:
        ShadowRoutingCommand(
            recording_id=baseline.recording_id,
            task_code=baseline.task_code,
            route_code=baseline.route_code,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            policy_version=baseline.policy_version,
            release_decision_sha256=Sha256Digest("a" * 64),
            scope=ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY,
        )
    assert caught.value.code is ShadowRoutingFailureCode.RELEASE_DECISION_PROHIBITED


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda value: value["document"].__setitem__("synthetic", False),
            ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__(
                "route_catalog_canary_max_percent", 6
            ),
            ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__(
                "critical_effective_canary_max_percent", 2
            ),
            ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__(
                "st0708_report_outcome", "PASSED"
            ),
            ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT,
        ),
        (
            lambda value: value["document"].__setitem__("provider", "example"),
            ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][0].__setitem__(
                "human_label_available", True
            ),
            ShadowRoutingFailureCode.INVALID_ARGUMENT,
        ),
        (
            lambda value: value["observations"][0].__setitem__(
                "content", "must-not-survive"
            ),
            ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"][0].__setitem__("commission", 100),
            ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID,
        ),
        (
            lambda value: value["observations"].append(value["observations"][0]),
            ShadowRoutingFailureCode.DUPLICATE_COHORT_MEMBER,
        ),
        (
            lambda value: value["observations"].reverse(),
            ShadowRoutingFailureCode.DUPLICATE_COHORT_MEMBER,
        ),
        (
            lambda value: value["observations"][1].__setitem__(
                "assignment_sha256",
                value["observations"][0]["assignment_sha256"],
            ),
            ShadowRoutingFailureCode.DUPLICATE_COHORT_MEMBER,
        ),
    ],
)
def test_hostile_fixture_mutations_fail_closed(
    mutator: object, expected: ShadowRoutingFailureCode
) -> None:
    assert _failure_code(_json_payload(mutator)) is expected


def test_duplicate_keys_floats_noncanonical_and_truncation_are_rejected() -> None:
    payload = fixture_bytes()
    duplicate = payload.replace(b'{"document":{', b'{"document":{"synthetic":true,', 1)
    assert _failure_code(duplicate) is ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID

    floating = payload.replace(
        b'"champion_score_micros":900000', b'"champion_score_micros":0.9', 1
    )
    assert _failure_code(floating) is ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID

    parsed = json.loads(payload)
    pretty = (json.dumps(parsed, indent=2) + "\n").encode("utf-8")
    assert _failure_code(pretty) is ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID

    assert _failure_code(payload[:-1]) is ShadowRoutingFailureCode.SOURCE_BYTES_MISMATCH


def test_command_and_batch_binding_drift_is_rejected() -> None:
    command = command_for()
    batch = _read(fixture_bytes())
    wrong_command = replace(command, recording_id="st1902-other-recording")
    with pytest.raises(ShadowRoutingFailure) as caught:
        evaluate_recorded_shadow(wrong_command, batch)
    assert caught.value.code is ShadowRoutingFailureCode.SOURCE_RESULT_INVALID

    wrong_batch = replace(batch, command_sha256=Sha256Digest("b" * 64))
    with pytest.raises(ShadowRoutingFailure) as caught:
        evaluate_recorded_shadow(command, wrong_batch)
    assert caught.value.code is ShadowRoutingFailureCode.SOURCE_RESULT_INVALID

    with pytest.raises(ShadowRoutingFailure) as caught:
        replace(batch, route_catalog_canary_max_percent=4)
    assert caught.value.code is ShadowRoutingFailureCode.ROUTE_POLICY_DRIFT


def test_one_shot_adapter_has_exactly_one_concurrent_winner() -> None:
    source = RecordedChampionChallengerSource(fixture_bytes())
    command = command_for()

    def call() -> str:
        try:
            source.read(command)
        except ShadowRoutingFailure as failure:
            return failure.code.value
        return "SUCCESS"

    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(lambda _index: call(), range(32)))
    assert outcomes.count("SUCCESS") == 1
    assert outcomes.count(ShadowRoutingFailureCode.SOURCE_EXHAUSTED.value) == 31
