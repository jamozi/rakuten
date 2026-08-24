"""Hostile input and adapter-boundary tests for ST-1206."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from conftest import FIXTURE_BYTES, command_for, service_for
from raos.adapters.recorded_keyword_rank import RecordedKeywordRankCsvSource
from raos.application.analytics.keyword_rank_import import (
    KeywordRankEvaluationService,
)
from raos.domain.analytics.keyword_rank import (
    KeywordRankFailure,
    KeywordRankFailureCode,
    KeywordRankScope,
    Sha256Digest,
)


def _rebound_service(payload: bytes) -> tuple[KeywordRankEvaluationService, object]:
    return service_for(payload), command_for(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xef\xbb\xbf" + FIXTURE_BYTES,
        FIXTURE_BYTES.replace(b"\n", b"\r\n"),
        FIXTURE_BYTES[:-1],
        FIXTURE_BYTES.replace(b"\n", b"\n\n", 1),
        FIXTURE_BYTES.replace(b",3,,", b',"3",,', 1),
        FIXTURE_BYTES.replace(b",3,,", b",=3,,", 1),
        FIXTURE_BYTES.replace(b",3,,", b",+3,,", 1),
        FIXTURE_BYTES.replace(b",3,,", b",-3,,", 1),
        FIXTURE_BYTES.replace(b",3,,", b",@3,,", 1),
        FIXTURE_BYTES.replace(b"ja-JP", b"ja\x00P", 1),
        FIXTURE_BYTES.replace(b"confidence\n", b"confidence,extra\n", 1),
        FIXTURE_BYTES.replace(b"POSITION,3", b"POSITION,03", 1),
        FIXTURE_BYTES.replace(b",1\n", b",1e0\n", 1),
        FIXTURE_BYTES.replace(b"RAOS_ST1206_SYNTHETIC", b"UNAPPROVED_PROVIDER", 1),
    ],
)
def test_document_level_drift_fails_closed_without_partial_result(
    payload: bytes,
) -> None:
    service, command = _rebound_service(payload)
    with pytest.raises(KeywordRankFailure) as caught:
        service.evaluate(command)  # type: ignore[arg-type]
    assert caught.value.code is KeywordRankFailureCode.SOURCE_DOCUMENT_INVALID
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_source_hash_mismatch_is_rejected_and_consumes_one_shot_source() -> None:
    source = RecordedKeywordRankCsvSource(FIXTURE_BYTES)
    mismatch = replace(command_for(), source_sha256=Sha256Digest("0" * 64))

    with pytest.raises(KeywordRankFailure) as caught:
        KeywordRankEvaluationService(source=source).evaluate(mismatch)
    assert caught.value.code is KeywordRankFailureCode.SOURCE_BYTES_MISMATCH
    with pytest.raises(KeywordRankFailure) as replay:
        source.read(command_for())
    assert replay.value.code is KeywordRankFailureCode.SOURCE_EXHAUSTED


def test_duplicate_canonical_observation_rejects_entire_evaluation() -> None:
    lines = FIXTURE_BYTES.splitlines(keepends=True)
    payload = b"".join((*lines, lines[1]))
    with pytest.raises(KeywordRankFailure) as caught:
        service_for(payload).evaluate(command_for(payload))
    assert caught.value.code is KeywordRankFailureCode.DUPLICATE_OBSERVATION


def test_out_of_period_observation_rejects_entire_evaluation() -> None:
    payload = FIXTURE_BYTES.replace(b"2026-08-02", b"2026-08-03", 1)
    with pytest.raises(KeywordRankFailure) as caught:
        service_for(payload).evaluate(command_for(payload))
    assert caught.value.code is KeywordRankFailureCode.OBSERVATION_OUT_OF_PERIOD


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        (b"POSITION,3", b"POSITION,0"),
        (b"SEARCH_VOLUME,1200", b"SEARCH_VOLUME,-1"),
        (b"DIFFICULTY,42.5", b"DIFFICULTY,101"),
        (b",0.8\n", b",1.1\n"),
        (b"018f3e90-7b00-7000-8000-000000001206", b"not-a-uuid"),
        (b"2026-08-01", b"2026-02-30"),
    ],
)
def test_invalid_canonical_values_are_redacted_document_failures(
    needle: bytes, replacement: bytes
) -> None:
    payload = FIXTURE_BYTES.replace(needle, replacement, 1)
    with pytest.raises(KeywordRankFailure) as caught:
        service_for(payload).evaluate(command_for(payload))
    assert caught.value.code is KeywordRankFailureCode.SOURCE_DOCUMENT_INVALID
    assert replacement.decode("ascii") not in str(caught.value)
    assert replacement.decode("ascii") not in repr(caught.value)


class _ScriptedSource:
    def __init__(
        self, *, result: object = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def read(self, command: object) -> object:
        del command
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def test_untrusted_source_exception_is_sanitized_without_chaining() -> None:
    canary = "SECRET-CANARY-ST1206"
    source = _ScriptedSource(error=RuntimeError(canary))
    with pytest.raises(KeywordRankFailure) as caught:
        KeywordRankEvaluationService(source=source).evaluate(command_for())
    assert caught.value.code is KeywordRankFailureCode.SOURCE_UNAVAILABLE
    assert canary not in str(caught.value)
    assert canary not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert source.calls == 1


def test_malformed_source_result_is_rejected_after_exactly_one_call() -> None:
    source = _ScriptedSource(result=object())
    with pytest.raises(KeywordRankFailure) as caught:
        KeywordRankEvaluationService(source=source).evaluate(command_for())
    assert caught.value.code is KeywordRankFailureCode.SOURCE_RESULT_INVALID
    assert source.calls == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_bytes", True),
        ("site_id", "018f3e90-7b00-7000-8000-000000001200"),
        ("scope", "RECORDED_SYNTHETIC_EVALUATION_ONLY"),
        ("parser_version", "future"),
        ("recording_id", "../escape"),
    ],
)
def test_command_type_and_shape_bypasses_fail_closed(field: str, value: object) -> None:
    command = command_for()
    values = {
        "recording_id": command.recording_id,
        "site_id": command.site_id,
        "source_sha256": command.source_sha256,
        "source_bytes": command.source_bytes,
        "period": command.period,
        "parser_version": command.parser_version,
        "scope": KeywordRankScope.RECORDED_SYNTHETIC_EVALUATION_ONLY,
    }
    values[field] = value
    with pytest.raises(KeywordRankFailure):
        type(command)(**values)  # type: ignore[arg-type]


def test_period_is_bounded_and_canonical() -> None:
    with pytest.raises(KeywordRankFailure):
        command_for(date_from=date(2026, 8, 2), date_to=date(2026, 8, 1))
    with pytest.raises(KeywordRankFailure):
        command_for(date_from=date(2025, 1, 1), date_to=date(2026, 8, 1))
