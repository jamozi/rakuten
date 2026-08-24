"""One-shot caller-bytes adapter for the ST-1903 synthetic fixture."""

from __future__ import annotations

import json
from threading import RLock
from typing import NoReturn, SupportsIndex, cast, final

from raos.domain.publishing.partial_auto_publication import (
    MAX_SOURCE_BYTES,
    PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE,
    PARTIAL_AUTO_PUBLICATION_PARSER_VERSION,
    BlockedPortfolioDependency,
    LowRiskChangeClass,
    PartialAutoPublicationCandidate,
    PartialAutoPublicationCommand,
    PartialAutoPublicationFailure,
    PartialAutoPublicationFailureCode,
    RecordedPartialAutoPublicationBundle,
    UnavailableReleaseGates,
    canonical_json_bytes,
    fail_partial_auto_publication,
    sha256_bytes,
)


_REDACTED = "<redacted-recorded-partial-auto-publication-source>"
_ROOT_KEYS = frozenset({"candidate", "dependency", "document", "gates"})
_DOCUMENT_KEYS = frozenset(
    {
        "actual_publication",
        "fixture_profile",
        "parser_version",
        "recording_id",
        "synthetic",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "affiliate_destination_change",
        "article_id",
        "candidate_id",
        "candidate_sha256",
        "change_class",
        "change_count",
        "claim_change",
        "content_addition",
        "finance_input_present",
        "high_risk",
        "personal_data_present",
        "price_or_stock_assertion_added",
        "product_identity_change",
        "public_write_requested",
        "raw_html_present",
        "recommendation_order_change",
        "risk_ambiguous",
        "synthetic",
    }
)
_DEPENDENCY_KEYS = frozenset(
    {
        "acceptance_criteria_satisfied",
        "authorized",
        "human_decision_required",
        "local_integration_complete",
        "outcome",
        "overall",
        "pack_sha256",
        "story_id",
    }
)
_GATE_KEYS = frozenset(
    {
        "actual_public_write",
        "actual_publication_execution",
        "formal_tst032",
        "idempotency_evidence",
        "kill_switch_state",
        "operations_review",
        "rollback_evidence",
        "security_review",
        "separate_human_release_decision",
    }
)


def _invalid() -> NoReturn:
    fail_partial_auto_publication(
        PartialAutoPublicationFailureCode.SOURCE_DOCUMENT_INVALID
    )


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != keys:
        _invalid()
    return cast(dict[str, object], value)


def _string(value: object, maximum: int = 160) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in "\x00\r\n")
    ):
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        _invalid()
    return value


def parse_recorded_partial_auto_publication(
    payload: bytes,
    command: PartialAutoPublicationCommand,
) -> RecordedPartialAutoPublicationBundle:
    """Parse exact canonical JSON without repair, coercion, or discovery."""

    if type(command) is not PartialAutoPublicationCommand:
        fail_partial_auto_publication()
    if (
        type(payload) is not bytes
        or not 1 <= len(payload) <= MAX_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or sha256_bytes(payload) != command.source_sha256
        or not payload.endswith(b"\n")
    ):
        fail_partial_auto_publication(
            PartialAutoPublicationFailureCode.SOURCE_BYTES_MISMATCH
        )
    try:
        parsed = json.loads(
            payload.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except PartialAutoPublicationFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != payload:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    if (
        document["recording_id"] != command.recording_id
        or document["fixture_profile"] != PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE
        or document["parser_version"] != PARTIAL_AUTO_PUBLICATION_PARSER_VERSION
        or _boolean(document["synthetic"]) is not True
        or _boolean(document["actual_publication"]) is not False
    ):
        _invalid()
    candidate_row = _mapping(root["candidate"], _CANDIDATE_KEYS)
    dependency_row = _mapping(root["dependency"], _DEPENDENCY_KEYS)
    gates_row = _mapping(root["gates"], _GATE_KEYS)
    try:
        candidate = PartialAutoPublicationCandidate(
            candidate_id=_string(candidate_row["candidate_id"]),
            article_id=_string(candidate_row["article_id"]),
            candidate_sha256=_string(candidate_row["candidate_sha256"], 64),
            change_class=LowRiskChangeClass(_string(candidate_row["change_class"])),
            change_count=_integer(candidate_row["change_count"]),
            synthetic=_boolean(candidate_row["synthetic"]),
            risk_ambiguous=_boolean(candidate_row["risk_ambiguous"]),
            high_risk=_boolean(candidate_row["high_risk"]),
            content_addition=_boolean(candidate_row["content_addition"]),
            claim_change=_boolean(candidate_row["claim_change"]),
            recommendation_order_change=_boolean(
                candidate_row["recommendation_order_change"]
            ),
            product_identity_change=_boolean(candidate_row["product_identity_change"]),
            affiliate_destination_change=_boolean(
                candidate_row["affiliate_destination_change"]
            ),
            raw_html_present=_boolean(candidate_row["raw_html_present"]),
            price_or_stock_assertion_added=_boolean(
                candidate_row["price_or_stock_assertion_added"]
            ),
            personal_data_present=_boolean(candidate_row["personal_data_present"]),
            finance_input_present=_boolean(candidate_row["finance_input_present"]),
            public_write_requested=_boolean(candidate_row["public_write_requested"]),
        )
        dependency = BlockedPortfolioDependency(
            story_id=_string(dependency_row["story_id"]),
            pack_sha256=_string(dependency_row["pack_sha256"], 64),
            overall=_string(dependency_row["overall"]),
            outcome=_string(dependency_row["outcome"]),
            authorized=_boolean(dependency_row["authorized"]),
            acceptance_criteria_satisfied=_boolean(
                dependency_row["acceptance_criteria_satisfied"]
            ),
            human_decision_required=_boolean(dependency_row["human_decision_required"]),
            local_integration_complete=_boolean(
                dependency_row["local_integration_complete"]
            ),
        )
        gates = UnavailableReleaseGates(
            formal_tst032=_string(gates_row["formal_tst032"]),
            separate_human_release_decision=_string(
                gates_row["separate_human_release_decision"]
            ),
            security_review=_string(gates_row["security_review"]),
            operations_review=_string(gates_row["operations_review"]),
            kill_switch_state=_string(gates_row["kill_switch_state"]),
            idempotency_evidence=_string(gates_row["idempotency_evidence"]),
            rollback_evidence=_string(gates_row["rollback_evidence"]),
            actual_publication_execution=_boolean(
                gates_row["actual_publication_execution"]
            ),
            actual_public_write=_boolean(gates_row["actual_public_write"]),
        )
    except PartialAutoPublicationFailure:
        raise
    except ValueError:
        _invalid()
    return RecordedPartialAutoPublicationBundle(
        recording_id=command.recording_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        fixture_profile=PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE,
        parser_version=PARTIAL_AUTO_PUBLICATION_PARSER_VERSION,
        candidate=candidate,
        dependency=dependency,
        gates=gates,
    )


@final
class RecordedPartialAutoPublicationSource:
    """Consume one immutable caller-supplied recording exactly once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if type(payload) is not bytes or not 1 <= len(payload) <= MAX_SOURCE_BYTES:
            _invalid()
        self._payload = bytes(payload)
        self._consumed = False
        self._lock = RLock()

    def read(
        self, command: PartialAutoPublicationCommand
    ) -> RecordedPartialAutoPublicationBundle:
        if type(command) is not PartialAutoPublicationCommand:
            fail_partial_auto_publication()
        with self._lock:
            if self._consumed:
                fail_partial_auto_publication(
                    PartialAutoPublicationFailureCode.SOURCE_EXHAUSTED
                )
            self._consumed = True
            return parse_recorded_partial_auto_publication(self._payload, command)

    def __repr__(self) -> str:
        return f"RecordedPartialAutoPublicationSource({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError(
            "recorded partial auto-publication sources cannot be serialized"
        )


__all__ = (
    "RecordedPartialAutoPublicationSource",
    "parse_recorded_partial_auto_publication",
)
