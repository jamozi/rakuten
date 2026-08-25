"""Strict caller-bytes adapter for the ST-1805 synthetic decision boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from threading import Lock
from typing import NoReturn, cast, final

from raos.domain.portfolio.scale_decision import (
    FIXTURE_SCHEMA,
    EvidenceState,
    FixtureByteLength,
    PortfolioDecisionCommand,
    PortfolioDecisionEvidence,
    PortfolioDecisionFailure,
    PortfolioDecisionFailureCode,
    Sha256Digest,
    canonical_input_digest,
    fail_portfolio_decision,
)


_TOP_KEYS = {
    "actual_observation",
    "contract_sha256",
    "evidence",
    "immutable",
    "input_sha256",
    "recorded_at",
    "recording_id",
    "schema",
    "synthetic",
}
_EVIDENCE_KEYS = {
    "dependency_acceptance_criteria_satisfied",
    "dependency_actual_observation_count",
    "dependency_gate_pass_claim",
    "dependency_overall",
    "dependency_scale_authority",
    "dependency_schema",
    "economics_state",
    "formal_tst032_state",
    "human_decision_present",
    "program",
    "quality_state",
    "risk_state",
    "source_pack_sha256",
}
_PROHIBITED_KEYS = {
    "article_body",
    "cookie",
    "email",
    "name",
    "phone",
    "raw_provider_row",
    "secret",
    "token",
}


def _fail() -> NoReturn:
    fail_portfolio_decision(PortfolioDecisionFailureCode.FIXTURE_DOCUMENT_INVALID)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def _mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw) or set(raw) != keys:
        _fail()
    if any(cast(str, key).lower() in _PROHIBITED_KEYS for key in raw):
        _fail()
    return cast(Mapping[str, object], value)


def _string(value: object, *, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        _fail()
    return value


def _digest(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value, maximum=64))
    except PortfolioDecisionFailure:
        _fail()


def _timestamp(value: object) -> str:
    rendered = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        _fail()
    return rendered


def parse_recorded_portfolio_decision_fixture(
    fixture_bytes: bytes,
    command: PortfolioDecisionCommand,
) -> PortfolioDecisionEvidence:
    if (
        type(fixture_bytes) is not bytes
        or type(command) is not PortfolioDecisionCommand
    ):
        fail_portfolio_decision()
    if (
        not 0 < len(fixture_bytes) <= 1024 * 1024
        or Sha256Digest.of(fixture_bytes) != command.fixture_digest
        or FixtureByteLength(len(fixture_bytes)) != command.fixture_length
    ):
        fail_portfolio_decision(PortfolioDecisionFailureCode.FIXTURE_BYTES_MISMATCH)
    try:
        document = json.loads(
            fixture_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail(),
            parse_float=lambda _: _fail(),
        )
    except PortfolioDecisionFailure, UnicodeDecodeError, ValueError, RecursionError:
        _fail()
    source = _mapping(document, _TOP_KEYS)
    if (
        _string(source["schema"]) != FIXTURE_SCHEMA
        or _string(source["recording_id"]) != command.recording_id
        or _timestamp(source["recorded_at"]) != "2026-04-01T00:00:00Z"
        or _boolean(source["synthetic"]) is not True
        or _boolean(source["actual_observation"]) is not False
        or _boolean(source["immutable"]) is not True
        or _digest(source["contract_sha256"]) != command.contract_digest
    ):
        _fail()
    evidence = _mapping(source["evidence"], _EVIDENCE_KEYS)
    try:
        result = PortfolioDecisionEvidence(
            recording_id=command.recording_id,
            fixture_digest=command.fixture_digest,
            fixture_length=command.fixture_length,
            contract_digest=command.contract_digest,
            input_digest=_digest(source["input_sha256"]),
            source_pack_digest=_digest(evidence["source_pack_sha256"]),
            program_id=_string(evidence["program"]),
            dependency_schema=_string(evidence["dependency_schema"]),
            dependency_overall=_string(evidence["dependency_overall"]),
            dependency_gate_pass_claim=_boolean(evidence["dependency_gate_pass_claim"]),
            dependency_actual_observation_count=_integer(
                evidence["dependency_actual_observation_count"]
            ),
            dependency_acceptance_criteria_satisfied=_boolean(
                evidence["dependency_acceptance_criteria_satisfied"]
            ),
            dependency_scale_authority=_string(evidence["dependency_scale_authority"]),
            quality_state=EvidenceState(_string(evidence["quality_state"])),
            economics_state=EvidenceState(_string(evidence["economics_state"])),
            risk_state=EvidenceState(_string(evidence["risk_state"])),
            formal_tst032_state=EvidenceState(_string(evidence["formal_tst032_state"])),
            human_decision_present=_boolean(evidence["human_decision_present"]),
            synthetic=True,
            actual_observation=False,
        )
    except PortfolioDecisionFailure, ValueError:
        _fail()
    if (
        result.input_digest != command.expected_input_digest
        or result.source_pack_digest != command.expected_source_pack_digest
        or canonical_input_digest(result) != result.input_digest
    ):
        _fail()
    return result


@final
class RecordedPortfolioDecisionAdapter:
    __slots__ = ("_consumed", "_fixture", "_lock")

    def __init__(self, fixture_bytes: bytes) -> None:
        if type(fixture_bytes) is not bytes or not fixture_bytes:
            fail_portfolio_decision()
        self._fixture = fixture_bytes
        self._consumed = False
        self._lock = Lock()

    def read(self, command: PortfolioDecisionCommand) -> PortfolioDecisionEvidence:
        with self._lock:
            if self._consumed:
                fail_portfolio_decision(
                    PortfolioDecisionFailureCode.RECORDED_EXCHANGE_EXHAUSTED
                )
            self._consumed = True
            return parse_recorded_portfolio_decision_fixture(self._fixture, command)


__all__ = [
    "RecordedPortfolioDecisionAdapter",
    "parse_recorded_portfolio_decision_fixture",
]
