"""Maximum-safe deterministic Fact-conflict values for ST-0603 V2.

Only exact persisted ST-0602 Fact batches enter this boundary.  Detection is
exact: no tolerance, conversion, authority winner, silent resolution, Claim,
Unknown, ranking, recommendation, publication, AI, provider, or network
capability exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast
from uuid import UUID

from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FACT_EXTRACTOR_VERSION_V2,
    ExactOfferFactV2,
    FactSubjectTypeV2,
    FactValueKindV2,
    PersistedFactExtractionV2,
    fact_mapping_v2,
    persisted_from_mapping_v2 as extraction_persisted_from_mapping_v2,
    persisted_mapping_v2 as extraction_persisted_mapping_v2,
)
from raos.domain.shared.identity import deterministic_uuid7


FACT_CONFLICT_DETECTOR_VERSION_V2 = "ST0603_EXACT_FACT_CONFLICTS_V2"
FACT_CONFLICT_SCHEMA_VERSION_V2 = "ST0603_FACT_CONFLICT_RUNTIME_V2"
FACT_CONFLICT_EVENT_TYPE_V2 = "st0603.local.fact_conflicts_recorded.v2"
FACT_CONFLICT_EVENT_CHANNEL_V2 = "owner-private.local"
FACT_CONFLICT_CONTENT_POLICY_V2 = "source_conflict"
FACT_CONFLICT_GENESIS_SHA256_V2 = "0" * 64
FACT_CONFLICT_EXTERNAL_ACTION_COUNT_V2 = 0
FACT_CONFLICT_PROVIDER_ACTION_COUNT_V2 = 0
FACT_CONFLICT_PUBLICATION_ACTION_COUNT_V2 = 0
FACT_CONFLICT_AI_ACTION_COUNT_V2 = 0

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PREDICATE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z", re.ASCII)
_UNIT = re.compile(r"[A-Z][A-Z0-9_]{0,15}\Z", re.ASCII)
_LOCALE = re.compile(r"[a-z]{2}-[A-Z]{2}\Z", re.ASCII)
_INTEGER_TEXT = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z", re.ASCII)
_MAX_SEQUENCE = (1 << 63) - 1
_MAX_INPUT_BATCHES = 64
_MAX_INPUT_FACTS = 4096
_ID_NAMESPACE = UUID("943b2aa1-b76b-43a9-8f79-89ca339373cb")
_REDACTED = "<redacted-fact-conflict-runtime-v2>"


class FactConflictFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    INPUT_LIMIT_EXCEEDED = "INPUT_LIMIT_EXCEEDED"
    VALUE_KIND_MISMATCH = "VALUE_KIND_MISMATCH"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    UNSAFE_PATH = "UNSAFE_PATH"
    SCHEMA_INTEGRITY = "SCHEMA_INTEGRITY"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"


class FactConflictReasonV2(str, Enum):
    VALUE_MISMATCH = "VALUE_MISMATCH"
    INCOMPATIBLE_UNIT_OR_LOCALE = "INCOMPATIBLE_UNIT_OR_LOCALE"


class FactComparisonOutcomeV2(str, Enum):
    EQUAL = "EQUAL"
    VALUE_CONFLICT = "VALUE_CONFLICT"
    INCOMPATIBLE_UNIT_OR_LOCALE = "INCOMPATIBLE_UNIT_OR_LOCALE"


class FactConflictStatusV2(str, Enum):
    UNRESOLVED = "UNRESOLVED"


class FactConflictQueueStatusV2(str, Enum):
    HUMAN_REVIEW = "HUMAN_REVIEW"


class FactConflictReadinessV2(str, Enum):
    NOT_READY = "NOT_READY"


class FactConflictReplayStatusV2(str, Enum):
    DIRECT_COMMIT = "DIRECT_COMMIT"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    RECOVERED_COMMIT = "RECOVERED_COMMIT"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("fact-conflict runtime values cannot be serialized")


class FactConflictFailureV2(RuntimeError):
    """Closed, stable, traceback-assignable failure."""

    __slots__ = ("_code",)

    def __init__(self, code: FactConflictFailureCodeV2) -> None:
        if type(code) is not FactConflictFailureCodeV2:
            raise TypeError("invalid fact-conflict failure code")
        RuntimeError.__init__(self, code.value)
        self._code = code

    @property
    def code(self) -> FactConflictFailureCodeV2:
        return self._code

    def __repr__(self) -> str:
        return f"FactConflictFailureV2(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("fact-conflict failures cannot be serialized")


def fail_fact_conflict_v2(
    code: FactConflictFailureCodeV2 = FactConflictFailureCodeV2.INVALID_ARGUMENT,
) -> NoReturn:
    raise FactConflictFailureV2(code) from None


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_fact_conflict_v2()
    return value


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_fact_conflict_v2()
    return value


def _positive_int(value: object, *, maximum: int = _MAX_SEQUENCE) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        fail_fact_conflict_v2()
    return value


def _nonnegative_int(value: object, *, maximum: int = _MAX_SEQUENCE) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        fail_fact_conflict_v2()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_fact_conflict_v2()
    return value


def utc_text_v2(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        result = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    if result.tzinfo is not timezone.utc or utc_text_v2(result) != value:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return result


def canonical_json_bytes_v2(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        fail_fact_conflict_v2()


def canonical_sha256_v2(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes_v2(value)).hexdigest()


def _stable_id(kind: str, material: object) -> UUID:
    return deterministic_uuid7(
        _ID_NAMESPACE,
        canonical_json_bytes_v2(
            {
                "kind": kind,
                "material": material,
                "schema_version": FACT_CONFLICT_SCHEMA_VERSION_V2,
            }
        ),
    )


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    raw = cast(dict[object, object], value)
    if frozenset(raw) != keys or any(type(key) is not str for key in raw):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return {cast(str, key): item for key, item in raw.items()}


def _uuid_text(value: object) -> UUID:
    if type(value) is not str:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        result = UUID(value)
    except ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    if result.int == 0 or str(result) != value:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return result


def windows_overlap_v2(
    left_from: datetime,
    left_to: datetime | None,
    right_from: datetime,
    right_to: datetime | None,
) -> bool:
    """Return exact half-open validity overlap; touching boundaries are disjoint."""

    left_start = _utc(left_from)
    right_start = _utc(right_from)
    if left_to is not None:
        left_end = _utc(left_to)
        if left_end <= left_start:
            fail_fact_conflict_v2()
    else:
        left_end = None
    if right_to is not None:
        right_end = _utc(right_to)
        if right_end <= right_start:
            fail_fact_conflict_v2()
    else:
        right_end = None
    return (left_end is None or right_start < left_end) and (
        right_end is None or left_start < right_end
    )


@dataclass(frozen=True, slots=True, repr=False)
class ComparableFactValueV2(_RedactedValue):
    value_kind: FactValueKindV2
    value_numeric: Decimal | None
    value_boolean: bool | None
    unit_code: str | None
    locale: str | None

    def __post_init__(self) -> None:
        if type(self.value_kind) is not FactValueKindV2:
            fail_fact_conflict_v2()
        if self.value_kind is FactValueKindV2.NUMERIC:
            if (
                type(self.value_numeric) is not Decimal
                or not self.value_numeric.is_finite()
                or self.value_numeric != self.value_numeric.to_integral_value()
                or self.value_boolean is not None
                or type(self.unit_code) is not str
                or _UNIT.fullmatch(self.unit_code) is None
                or (
                    self.locale is not None
                    and (
                        type(self.locale) is not str
                        or _LOCALE.fullmatch(self.locale) is None
                    )
                )
            ):
                fail_fact_conflict_v2()
        elif (
            self.value_numeric is not None
            or type(self.value_boolean) is not bool
            or self.unit_code is not None
            or self.locale is not None
        ):
            fail_fact_conflict_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "locale": self.locale,
            "unit_code": self.unit_code,
            "value_boolean": self.value_boolean,
            "value_kind": self.value_kind.value,
            "value_numeric": (
                None
                if self.value_numeric is None
                else str(self.value_numeric.to_integral_value())
            ),
        }

    @classmethod
    def from_fact(cls, fact: ExactOfferFactV2) -> ComparableFactValueV2:
        if type(fact) is not ExactOfferFactV2:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
        return cls(
            value_kind=fact.value_kind,
            value_numeric=fact.value_numeric,
            value_boolean=fact.value_boolean,
            unit_code=fact.unit_code,
            locale=fact.locale,
        )


def compare_fact_values_v2(
    left: ComparableFactValueV2,
    right: ComparableFactValueV2,
) -> FactComparisonOutcomeV2:
    if (
        type(left) is not ComparableFactValueV2
        or type(right) is not ComparableFactValueV2
    ):
        fail_fact_conflict_v2()
    if left.value_kind is not right.value_kind:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.VALUE_KIND_MISMATCH)
    if left.unit_code != right.unit_code or left.locale != right.locale:
        return FactComparisonOutcomeV2.INCOMPATIBLE_UNIT_OR_LOCALE
    if left.canonical_material == right.canonical_material:
        return FactComparisonOutcomeV2.EQUAL
    return FactComparisonOutcomeV2.VALUE_CONFLICT


@dataclass(frozen=True, slots=True, repr=False)
class FactPayloadBindingV2(_RedactedValue):
    fact_id: UUID
    fact_sha256: str

    def __post_init__(self) -> None:
        _uuid(self.fact_id)
        _sha256(self.fact_sha256)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {"fact_id": str(self.fact_id), "fact_sha256": self.fact_sha256}


@dataclass(frozen=True, slots=True, repr=False)
class PersistedFactBatchBindingV2(_RedactedValue):
    batch_id: UUID
    batch_sha256: str
    persisted_sha256: str
    chain_hash: str
    source_snapshot_id: UUID
    extractor_version: str
    committed_at: datetime
    facts: tuple[FactPayloadBindingV2, ...]

    def __post_init__(self) -> None:
        _uuid(self.batch_id)
        _sha256(self.batch_sha256)
        _sha256(self.persisted_sha256)
        _sha256(self.chain_hash)
        _uuid(self.source_snapshot_id)
        if self.extractor_version != FACT_EXTRACTOR_VERSION_V2:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
        _utc(self.committed_at)
        if (
            type(self.facts) is not tuple
            or not self.facts
            or len(self.facts) > _MAX_INPUT_FACTS
            or any(type(item) is not FactPayloadBindingV2 for item in self.facts)
            or len({item.fact_id for item in self.facts}) != len(self.facts)
            or tuple(item.fact_id.hex for item in self.facts)
            != tuple(sorted(item.fact_id.hex for item in self.facts))
        ):
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "batch_id": str(self.batch_id),
            "batch_sha256": self.batch_sha256,
            "chain_hash": self.chain_hash,
            "committed_at": utc_text_v2(self.committed_at),
            "extractor_version": self.extractor_version,
            "facts": [item.canonical_material for item in self.facts],
            "persisted_sha256": self.persisted_sha256,
            "source_snapshot_id": str(self.source_snapshot_id),
        }


def _copy_persisted_input(value: object) -> PersistedFactExtractionV2:
    if type(value) is not PersistedFactExtractionV2:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
    try:
        facts = value.batch.facts
        validations = value.batch.validations
    except Exception:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
    if type(facts) is not tuple or type(validations) is not tuple:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
    if len(facts) > _MAX_INPUT_FACTS or len(validations) > _MAX_INPUT_FACTS:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED)
    try:
        value.command.source_binding.__post_init__()
        value.command.__post_init__()
        for fact in facts:
            fact.locator.__post_init__()
            fact.__post_init__()
        for validation in validations:
            validation.__post_init__()
        value.batch.__post_init__()
        value.event.__post_init__()
        value.__post_init__()
        copied = extraction_persisted_from_mapping_v2(
            extraction_persisted_mapping_v2(value)
        )
    except Exception:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
    if (
        copied.command.extractor_version != FACT_EXTRACTOR_VERSION_V2
        or not copied.batch.facts
        or type(copied.batch.external_action_count) is not int
        or copied.batch.external_action_count != 0
        or type(copied.batch.provider_action_count) is not int
        or copied.batch.provider_action_count != 0
        or type(copied.batch.publication_action_count) is not int
        or copied.batch.publication_action_count != 0
        or type(copied.batch.ai_action_count) is not int
        or copied.batch.ai_action_count != 0
        or type(copied.event.external_action_count) is not int
        or copied.event.external_action_count != 0
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
    return copied


def _input_binding(value: PersistedFactExtractionV2) -> PersistedFactBatchBindingV2:
    facts = tuple(
        sorted(
            (
                FactPayloadBindingV2(
                    fact_id=fact.fact_id,
                    fact_sha256=canonical_sha256_v2(fact_mapping_v2(fact)),
                )
                for fact in value.batch.facts
            ),
            key=lambda item: item.fact_id.hex,
        )
    )
    return PersistedFactBatchBindingV2(
        batch_id=value.batch.batch_id,
        batch_sha256=value.batch.sha256,
        persisted_sha256=canonical_sha256_v2(extraction_persisted_mapping_v2(value)),
        chain_hash=value.chain_hash,
        source_snapshot_id=value.command.source_snapshot_id,
        extractor_version=value.command.extractor_version,
        committed_at=value.committed_at,
        facts=facts,
    )


def normalize_persisted_inputs_v2(
    inputs: tuple[PersistedFactExtractionV2, ...],
) -> tuple[PersistedFactExtractionV2, ...]:
    if type(inputs) is not tuple or not inputs or len(inputs) > _MAX_INPUT_BATCHES:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED)
    unique: dict[UUID, PersistedFactExtractionV2] = {}
    digests: dict[UUID, str] = {}
    total = 0
    for item in inputs:
        copied = _copy_persisted_input(item)
        total += len(copied.batch.facts)
        if total > _MAX_INPUT_FACTS:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.INPUT_LIMIT_EXCEEDED)
        digest = canonical_sha256_v2(extraction_persisted_mapping_v2(copied))
        prior = digests.get(copied.batch.batch_id)
        if prior is not None and prior != digest:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
        unique[copied.batch.batch_id] = copied
        digests[copied.batch.batch_id] = digest
    return tuple(unique[key] for key in sorted(unique, key=lambda item: item.hex))


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictScanCommandV2(_RedactedValue):
    detector_version: str
    input_bindings: tuple[PersistedFactBatchBindingV2, ...]
    input_set_sha256: str
    payload_sha256: str

    def __post_init__(self) -> None:
        if (
            self.detector_version != FACT_CONFLICT_DETECTOR_VERSION_V2
            or type(self.input_bindings) is not tuple
            or not self.input_bindings
            or len(self.input_bindings) > _MAX_INPUT_BATCHES
            or any(
                type(item) is not PersistedFactBatchBindingV2
                for item in self.input_bindings
            )
            or len({item.batch_id for item in self.input_bindings})
            != len(self.input_bindings)
            or tuple(item.batch_id.hex for item in self.input_bindings)
            != tuple(sorted(item.batch_id.hex for item in self.input_bindings))
        ):
            fail_fact_conflict_v2()
        expected_set = canonical_sha256_v2(
            [item.canonical_material for item in self.input_bindings]
        )
        if _sha256(self.input_set_sha256) != expected_set:
            fail_fact_conflict_v2()
        expected_payload = canonical_sha256_v2(
            {
                "detector_version": self.detector_version,
                "input_bindings": [
                    item.canonical_material for item in self.input_bindings
                ],
                "input_set_sha256": self.input_set_sha256,
            }
        )
        if _sha256(self.payload_sha256) != expected_payload:
            fail_fact_conflict_v2()

    @property
    def idempotency_key(self) -> tuple[str, str]:
        return (self.input_set_sha256, self.detector_version)

    @classmethod
    def issue(
        cls, inputs: tuple[PersistedFactExtractionV2, ...]
    ) -> FactConflictScanCommandV2:
        normalized = normalize_persisted_inputs_v2(inputs)
        bindings = tuple(_input_binding(item) for item in normalized)
        input_set = canonical_sha256_v2([item.canonical_material for item in bindings])
        material = {
            "detector_version": FACT_CONFLICT_DETECTOR_VERSION_V2,
            "input_bindings": [item.canonical_material for item in bindings],
            "input_set_sha256": input_set,
        }
        return cls(
            detector_version=FACT_CONFLICT_DETECTOR_VERSION_V2,
            input_bindings=bindings,
            input_set_sha256=input_set,
            payload_sha256=canonical_sha256_v2(material),
        )


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictFactRefV2(_RedactedValue):
    fact_id: UUID
    fact_sha256: str
    batch_id: UUID
    source_snapshot_id: UUID
    subject_type: FactSubjectTypeV2
    subject_id: UUID
    predicate: str
    value: ComparableFactValueV2
    valid_from: datetime
    valid_to: datetime | None

    def __post_init__(self) -> None:
        _uuid(self.fact_id)
        _sha256(self.fact_sha256)
        _uuid(self.batch_id)
        _uuid(self.source_snapshot_id)
        if (
            self.subject_type is not FactSubjectTypeV2.OFFER
            or type(self.subject_id) is not UUID
            or self.subject_id.int == 0
            or type(self.predicate) is not str
            or _PREDICATE.fullmatch(self.predicate) is None
            or type(self.value) is not ComparableFactValueV2
        ):
            fail_fact_conflict_v2()
        _utc(self.valid_from)
        if self.valid_to is not None:
            _utc(self.valid_to)
            if self.valid_to <= self.valid_from:
                fail_fact_conflict_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "batch_id": str(self.batch_id),
            "fact_id": str(self.fact_id),
            "fact_sha256": self.fact_sha256,
            "predicate": self.predicate,
            "source_snapshot_id": str(self.source_snapshot_id),
            "subject_id": str(self.subject_id),
            "subject_type": self.subject_type.value,
            "valid_from": utc_text_v2(self.valid_from),
            "valid_to": None if self.valid_to is None else utc_text_v2(self.valid_to),
            "value": self.value.canonical_material,
        }

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.fact_id.hex, self.batch_id.hex, self.fact_sha256)

    @classmethod
    def from_fact(
        cls, *, batch_id: UUID, fact: ExactOfferFactV2
    ) -> FactConflictFactRefV2:
        if type(fact) is not ExactOfferFactV2:
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
        return cls(
            fact_id=fact.fact_id,
            fact_sha256=canonical_sha256_v2(fact_mapping_v2(fact)),
            batch_id=batch_id,
            source_snapshot_id=fact.source_snapshot_id,
            subject_type=fact.subject_type,
            subject_id=fact.subject_id,
            predicate=fact.predicate,
            value=ComparableFactValueV2.from_fact(fact),
            valid_from=fact.valid_from,
            valid_to=fact.valid_to,
        )


@dataclass(frozen=True, slots=True, repr=False)
class UnresolvedFactConflictV2(_RedactedValue):
    conflict_id: UUID
    display_id: str
    scan_id: UUID
    left: FactConflictFactRefV2
    right: FactConflictFactRefV2
    reason: FactConflictReasonV2
    status: FactConflictStatusV2
    queue_status: FactConflictQueueStatusV2
    readiness: FactConflictReadinessV2
    content_policy: str
    silent_resolution_forbidden: bool
    winner_fact_id: None
    tolerance: None
    authority_priority_used: bool
    resolution: None
    detected_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.conflict_id)
        _uuid(self.scan_id)
        if (
            type(self.display_id) is not str
            or self.display_id != f"CNF-{self.conflict_id.hex[:20].upper()}"
            or type(self.left) is not FactConflictFactRefV2
            or type(self.right) is not FactConflictFactRefV2
            or self.left.sort_key >= self.right.sort_key
            or self.left.subject_type is not self.right.subject_type
            or self.left.subject_id != self.right.subject_id
            or self.left.predicate != self.right.predicate
            or not windows_overlap_v2(
                self.left.valid_from,
                self.left.valid_to,
                self.right.valid_from,
                self.right.valid_to,
            )
            or type(self.reason) is not FactConflictReasonV2
            or self.status is not FactConflictStatusV2.UNRESOLVED
            or self.queue_status is not FactConflictQueueStatusV2.HUMAN_REVIEW
            or self.readiness is not FactConflictReadinessV2.NOT_READY
            or self.content_policy != FACT_CONFLICT_CONTENT_POLICY_V2
            or self.silent_resolution_forbidden is not True
            or self.winner_fact_id is not None
            or self.tolerance is not None
            or self.authority_priority_used is not False
            or self.resolution is not None
        ):
            fail_fact_conflict_v2()
        outcome = compare_fact_values_v2(self.left.value, self.right.value)
        expected_reason = {
            FactComparisonOutcomeV2.VALUE_CONFLICT: FactConflictReasonV2.VALUE_MISMATCH,
            FactComparisonOutcomeV2.INCOMPATIBLE_UNIT_OR_LOCALE: (
                FactConflictReasonV2.INCOMPATIBLE_UNIT_OR_LOCALE
            ),
        }.get(outcome)
        if expected_reason is None or self.reason is not expected_reason:
            fail_fact_conflict_v2()
        _utc(self.detected_at)
        expected = _stable_id(
            "unresolved_conflict",
            {
                "left": self.left.canonical_material,
                "reason": self.reason.value,
                "right": self.right.canonical_material,
                "scan_id": str(self.scan_id),
            },
        )
        if self.conflict_id != expected:
            fail_fact_conflict_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "authority_priority_used": self.authority_priority_used,
            "conflict_id": str(self.conflict_id),
            "content_policy": self.content_policy,
            "detected_at": utc_text_v2(self.detected_at),
            "display_id": self.display_id,
            "left": self.left.canonical_material,
            "queue_status": self.queue_status.value,
            "readiness": self.readiness.value,
            "reason": self.reason.value,
            "resolution": self.resolution,
            "right": self.right.canonical_material,
            "scan_id": str(self.scan_id),
            "silent_resolution_forbidden": self.silent_resolution_forbidden,
            "status": self.status.value,
            "tolerance": self.tolerance,
            "winner_fact_id": self.winner_fact_id,
        }

    @classmethod
    def create(
        cls,
        *,
        left: FactConflictFactRefV2,
        right: FactConflictFactRefV2,
        scan_id: UUID,
        detected_at: datetime,
    ) -> UnresolvedFactConflictV2:
        ordered = tuple(sorted((left, right), key=lambda item: item.sort_key))
        outcome = compare_fact_values_v2(ordered[0].value, ordered[1].value)
        if outcome is FactComparisonOutcomeV2.EQUAL:
            fail_fact_conflict_v2()
        reason = (
            FactConflictReasonV2.VALUE_MISMATCH
            if outcome is FactComparisonOutcomeV2.VALUE_CONFLICT
            else FactConflictReasonV2.INCOMPATIBLE_UNIT_OR_LOCALE
        )
        material = {
            "left": ordered[0].canonical_material,
            "reason": reason.value,
            "right": ordered[1].canonical_material,
            "scan_id": str(_uuid(scan_id)),
        }
        conflict_id = _stable_id("unresolved_conflict", material)
        return cls(
            conflict_id=conflict_id,
            display_id=f"CNF-{conflict_id.hex[:20].upper()}",
            scan_id=scan_id,
            left=ordered[0],
            right=ordered[1],
            reason=reason,
            status=FactConflictStatusV2.UNRESOLVED,
            queue_status=FactConflictQueueStatusV2.HUMAN_REVIEW,
            readiness=FactConflictReadinessV2.NOT_READY,
            content_policy=FACT_CONFLICT_CONTENT_POLICY_V2,
            silent_resolution_forbidden=True,
            winner_fact_id=None,
            tolerance=None,
            authority_priority_used=False,
            resolution=None,
            detected_at=detected_at,
        )


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictReviewQueueRecordV2(_RedactedValue):
    queue_id: UUID
    conflict_id: UUID
    status: FactConflictQueueStatusV2
    conflict_status: FactConflictStatusV2
    readiness: FactConflictReadinessV2
    assigned_actor_id: None
    resolution: None
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.queue_id)
        _uuid(self.conflict_id)
        if (
            self.status is not FactConflictQueueStatusV2.HUMAN_REVIEW
            or self.conflict_status is not FactConflictStatusV2.UNRESOLVED
            or self.readiness is not FactConflictReadinessV2.NOT_READY
            or self.assigned_actor_id is not None
            or self.resolution is not None
            or self.queue_id
            != _stable_id("review_queue", {"conflict_id": str(self.conflict_id)})
        ):
            fail_fact_conflict_v2()
        _utc(self.created_at)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "assigned_actor_id": self.assigned_actor_id,
            "conflict_id": str(self.conflict_id),
            "conflict_status": self.conflict_status.value,
            "created_at": utc_text_v2(self.created_at),
            "queue_id": str(self.queue_id),
            "readiness": self.readiness.value,
            "resolution": self.resolution,
            "status": self.status.value,
        }

    @classmethod
    def from_conflict(
        cls, conflict: UnresolvedFactConflictV2
    ) -> FactConflictReviewQueueRecordV2:
        if type(conflict) is not UnresolvedFactConflictV2:
            fail_fact_conflict_v2()
        return cls(
            queue_id=_stable_id(
                "review_queue", {"conflict_id": str(conflict.conflict_id)}
            ),
            conflict_id=conflict.conflict_id,
            status=FactConflictQueueStatusV2.HUMAN_REVIEW,
            conflict_status=FactConflictStatusV2.UNRESOLVED,
            readiness=FactConflictReadinessV2.NOT_READY,
            assigned_actor_id=None,
            resolution=None,
            created_at=conflict.detected_at,
        )


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictDetectionBatchV2(_RedactedValue):
    scan_id: UUID
    command: FactConflictScanCommandV2
    conflicts: tuple[UnresolvedFactConflictV2, ...]
    queue: tuple[FactConflictReviewQueueRecordV2, ...]
    scanned_at: datetime
    comparison_count: int
    equal_value_count: int
    disjoint_window_count: int
    incompatible_unit_or_locale_count: int
    content_policy: str
    silent_resolution_forbidden: bool
    status: FactConflictStatusV2
    queue_status: FactConflictQueueStatusV2
    readiness: FactConflictReadinessV2
    external_action_count: int
    provider_action_count: int
    publication_action_count: int
    ai_action_count: int

    def __post_init__(self) -> None:
        _uuid(self.scan_id)
        if (
            type(self.command) is not FactConflictScanCommandV2
            or type(self.conflicts) is not tuple
            or any(
                type(item) is not UnresolvedFactConflictV2 for item in self.conflicts
            )
            or len({item.conflict_id for item in self.conflicts}) != len(self.conflicts)
            or tuple(item.conflict_id.hex for item in self.conflicts)
            != tuple(sorted(item.conflict_id.hex for item in self.conflicts))
            or type(self.queue) is not tuple
            or any(
                type(item) is not FactConflictReviewQueueRecordV2 for item in self.queue
            )
            or tuple(item.conflict_id for item in self.queue)
            != tuple(item.conflict_id for item in self.conflicts)
            or self.queue
            != tuple(
                FactConflictReviewQueueRecordV2.from_conflict(item)
                for item in self.conflicts
            )
            or self.content_policy != FACT_CONFLICT_CONTENT_POLICY_V2
            or self.silent_resolution_forbidden is not True
            or self.status is not FactConflictStatusV2.UNRESOLVED
            or self.queue_status is not FactConflictQueueStatusV2.HUMAN_REVIEW
            or self.readiness is not FactConflictReadinessV2.NOT_READY
            or any(
                type(value) is not int or value != 0
                for value in (
                    self.external_action_count,
                    self.provider_action_count,
                    self.publication_action_count,
                    self.ai_action_count,
                )
            )
        ):
            fail_fact_conflict_v2()
        if any(item.scan_id != self.scan_id for item in self.conflicts):
            fail_fact_conflict_v2()
        for value in (
            self.comparison_count,
            self.equal_value_count,
            self.disjoint_window_count,
            self.incompatible_unit_or_locale_count,
        ):
            _nonnegative_int(value)
        if (
            self.incompatible_unit_or_locale_count
            != sum(
                item.reason is FactConflictReasonV2.INCOMPATIBLE_UNIT_OR_LOCALE
                for item in self.conflicts
            )
            or self.comparison_count
            != self.equal_value_count + self.disjoint_window_count + len(self.conflicts)
        ):
            fail_fact_conflict_v2()
        scanned = _utc(self.scanned_at)
        if any(item.detected_at != scanned for item in self.conflicts):
            fail_fact_conflict_v2()
        allowed = {
            (binding.fact_id, binding.fact_sha256)
            for batch in self.command.input_bindings
            for binding in batch.facts
        }
        if any(
            (ref.fact_id, ref.fact_sha256) not in allowed
            for conflict in self.conflicts
            for ref in (conflict.left, conflict.right)
        ):
            fail_fact_conflict_v2(FactConflictFailureCodeV2.DEPENDENCY_MISMATCH)
        expected = _stable_id(
            "conflict_scan",
            {
                "detector_version": self.command.detector_version,
                "input_set_sha256": self.command.input_set_sha256,
                "payload_sha256": self.command.payload_sha256,
            },
        )
        if self.scan_id != expected:
            fail_fact_conflict_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "ai_action_count": self.ai_action_count,
            "command": command_mapping_v2(self.command),
            "comparison_count": self.comparison_count,
            "conflicts": [item.canonical_material for item in self.conflicts],
            "content_policy": self.content_policy,
            "disjoint_window_count": self.disjoint_window_count,
            "equal_value_count": self.equal_value_count,
            "external_action_count": self.external_action_count,
            "incompatible_unit_or_locale_count": (
                self.incompatible_unit_or_locale_count
            ),
            "provider_action_count": self.provider_action_count,
            "publication_action_count": self.publication_action_count,
            "queue": [item.canonical_material for item in self.queue],
            "queue_status": self.queue_status.value,
            "readiness": self.readiness.value,
            "scan_id": str(self.scan_id),
            "scanned_at": utc_text_v2(self.scanned_at),
            "silent_resolution_forbidden": self.silent_resolution_forbidden,
            "status": self.status.value,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictsRecordedOutboxEventV2(_RedactedValue):
    event_id: UUID
    event_type: str
    channel: str
    aggregate_id: UUID
    aggregate_version: int
    conflict_ids: tuple[UUID, ...]
    queue_ids: tuple[UUID, ...]
    occurred_at: datetime
    delivery_status: str
    external_action_count: int

    def __post_init__(self) -> None:
        _uuid(self.event_id)
        _uuid(self.aggregate_id)
        if (
            self.event_type != FACT_CONFLICT_EVENT_TYPE_V2
            or self.channel != FACT_CONFLICT_EVENT_CHANNEL_V2
            or type(self.aggregate_version) is not int
            or self.aggregate_version != 1
            or type(self.conflict_ids) is not tuple
            or type(self.queue_ids) is not tuple
            or len(self.conflict_ids) != len(self.queue_ids)
            or any(
                type(item) is not UUID or item.int == 0 for item in self.conflict_ids
            )
            or any(type(item) is not UUID or item.int == 0 for item in self.queue_ids)
            or len(set(self.conflict_ids)) != len(self.conflict_ids)
            or len(set(self.queue_ids)) != len(self.queue_ids)
            or tuple(item.hex for item in self.conflict_ids)
            != tuple(sorted(item.hex for item in self.conflict_ids))
            or self.delivery_status != "RECORDED_LOCAL_NOT_DELIVERED"
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
        ):
            fail_fact_conflict_v2()
        _utc(self.occurred_at)
        expected = _stable_id(
            "conflict_event",
            {
                "conflict_ids": [str(item) for item in self.conflict_ids],
                "queue_ids": [str(item) for item in self.queue_ids],
                "scan_id": str(self.aggregate_id),
            },
        )
        if self.event_id != expected:
            fail_fact_conflict_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "aggregate_id": str(self.aggregate_id),
            "aggregate_version": self.aggregate_version,
            "channel": self.channel,
            "conflict_ids": [str(item) for item in self.conflict_ids],
            "delivery_status": self.delivery_status,
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "external_action_count": self.external_action_count,
            "occurred_at": utc_text_v2(self.occurred_at),
            "queue_ids": [str(item) for item in self.queue_ids],
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)

    @classmethod
    def from_batch(
        cls, batch: FactConflictDetectionBatchV2
    ) -> FactConflictsRecordedOutboxEventV2:
        if type(batch) is not FactConflictDetectionBatchV2:
            fail_fact_conflict_v2()
        conflicts = tuple(item.conflict_id for item in batch.conflicts)
        queues = tuple(item.queue_id for item in batch.queue)
        material = {
            "conflict_ids": [str(item) for item in conflicts],
            "queue_ids": [str(item) for item in queues],
            "scan_id": str(batch.scan_id),
        }
        return cls(
            event_id=_stable_id("conflict_event", material),
            event_type=FACT_CONFLICT_EVENT_TYPE_V2,
            channel=FACT_CONFLICT_EVENT_CHANNEL_V2,
            aggregate_id=batch.scan_id,
            aggregate_version=1,
            conflict_ids=conflicts,
            queue_ids=queues,
            occurred_at=batch.scanned_at,
            delivery_status="RECORDED_LOCAL_NOT_DELIVERED",
            external_action_count=0,
        )


def fact_conflict_chain_hash_v2(
    *,
    previous_chain_hash: str,
    sequence: int,
    command_payload_sha256: str,
    batch_sha256: str,
    event_sha256: str,
    committed_at: datetime,
) -> str:
    return canonical_sha256_v2(
        {
            "batch_sha256": _sha256(batch_sha256),
            "command_payload_sha256": _sha256(command_payload_sha256),
            "committed_at": utc_text_v2(committed_at),
            "event_sha256": _sha256(event_sha256),
            "previous_chain_hash": _sha256(previous_chain_hash),
            "sequence": _positive_int(sequence),
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class PersistedFactConflictDetectionV2(_RedactedValue):
    sequence: int
    previous_chain_hash: str
    chain_hash: str
    command: FactConflictScanCommandV2
    batch: FactConflictDetectionBatchV2
    event: FactConflictsRecordedOutboxEventV2
    committed_at: datetime

    def __post_init__(self) -> None:
        sequence = _positive_int(self.sequence)
        previous = _sha256(self.previous_chain_hash)
        if (
            type(self.command) is not FactConflictScanCommandV2
            or type(self.batch) is not FactConflictDetectionBatchV2
            or type(self.event) is not FactConflictsRecordedOutboxEventV2
            or self.batch.command != self.command
            or self.event != FactConflictsRecordedOutboxEventV2.from_batch(self.batch)
            or _utc(self.committed_at) != self.batch.scanned_at
            or _sha256(self.chain_hash)
            != fact_conflict_chain_hash_v2(
                previous_chain_hash=previous,
                sequence=sequence,
                command_payload_sha256=self.command.payload_sha256,
                batch_sha256=self.batch.sha256,
                event_sha256=self.event.sha256,
                committed_at=self.committed_at,
            )
        ):
            fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictStoreCommitV2(_RedactedValue):
    persisted: PersistedFactConflictDetectionV2
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedFactConflictDetectionV2
            or type(self.replayed) is not bool
        ):
            fail_fact_conflict_v2()


@dataclass(frozen=True, slots=True, repr=False)
class FactConflictDetectionResultV2(_RedactedValue):
    persisted: PersistedFactConflictDetectionV2
    replay_status: FactConflictReplayStatusV2
    external_action_count: int
    provider_action_count: int
    publication_action_count: int
    ai_action_count: int

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedFactConflictDetectionV2
            or type(self.replay_status) is not FactConflictReplayStatusV2
            or any(
                type(value) is not int or value != 0
                for value in (
                    self.external_action_count,
                    self.provider_action_count,
                    self.publication_action_count,
                    self.ai_action_count,
                )
            )
            or any(
                type(value) is not int or value != 0
                for value in (
                    self.persisted.batch.external_action_count,
                    self.persisted.batch.provider_action_count,
                    self.persisted.batch.publication_action_count,
                    self.persisted.batch.ai_action_count,
                    self.persisted.event.external_action_count,
                )
            )
        ):
            fail_fact_conflict_v2()


def build_fact_conflict_artifacts_v2(
    inputs: tuple[PersistedFactExtractionV2, ...],
) -> tuple[
    FactConflictScanCommandV2,
    FactConflictDetectionBatchV2,
    FactConflictsRecordedOutboxEventV2,
]:
    normalized = normalize_persisted_inputs_v2(inputs)
    command = FactConflictScanCommandV2.issue(normalized)
    scan_id = _stable_id(
        "conflict_scan",
        {
            "detector_version": command.detector_version,
            "input_set_sha256": command.input_set_sha256,
            "payload_sha256": command.payload_sha256,
        },
    )
    scanned_at = max(item.committed_at for item in normalized)
    refs = tuple(
        FactConflictFactRefV2.from_fact(batch_id=item.batch.batch_id, fact=fact)
        for item in normalized
        for fact in item.batch.facts
    )
    groups: dict[tuple[str, UUID, str], list[FactConflictFactRefV2]] = {}
    for ref in refs:
        groups.setdefault(
            (ref.subject_type.value, ref.subject_id, ref.predicate), []
        ).append(ref)
    comparisons = 0
    equal_values = 0
    disjoint = 0
    incompatible = 0
    conflicts: dict[UUID, UnresolvedFactConflictV2] = {}
    for key in sorted(groups, key=lambda item: (item[0], item[1].hex, item[2])):
        group = sorted(groups[key], key=lambda item: item.sort_key)
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                comparisons += 1
                if not windows_overlap_v2(
                    left.valid_from, left.valid_to, right.valid_from, right.valid_to
                ):
                    disjoint += 1
                    continue
                outcome = compare_fact_values_v2(left.value, right.value)
                if outcome is FactComparisonOutcomeV2.EQUAL:
                    equal_values += 1
                    continue
                conflict = UnresolvedFactConflictV2.create(
                    left=left,
                    right=right,
                    scan_id=scan_id,
                    detected_at=scanned_at,
                )
                if outcome is FactComparisonOutcomeV2.INCOMPATIBLE_UNIT_OR_LOCALE:
                    incompatible += 1
                prior = conflicts.get(conflict.conflict_id)
                if prior is not None and prior != conflict:
                    fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
                conflicts[conflict.conflict_id] = conflict
    ordered_conflicts = tuple(
        conflicts[key] for key in sorted(conflicts, key=lambda item: item.hex)
    )
    queue = tuple(
        FactConflictReviewQueueRecordV2.from_conflict(item)
        for item in ordered_conflicts
    )
    batch = FactConflictDetectionBatchV2(
        scan_id=scan_id,
        command=command,
        conflicts=ordered_conflicts,
        queue=queue,
        scanned_at=scanned_at,
        comparison_count=comparisons,
        equal_value_count=equal_values,
        disjoint_window_count=disjoint,
        incompatible_unit_or_locale_count=incompatible,
        content_policy=FACT_CONFLICT_CONTENT_POLICY_V2,
        silent_resolution_forbidden=True,
        status=FactConflictStatusV2.UNRESOLVED,
        queue_status=FactConflictQueueStatusV2.HUMAN_REVIEW,
        readiness=FactConflictReadinessV2.NOT_READY,
        external_action_count=0,
        provider_action_count=0,
        publication_action_count=0,
        ai_action_count=0,
    )
    return command, batch, FactConflictsRecordedOutboxEventV2.from_batch(batch)


def fact_payload_binding_mapping_v2(value: FactPayloadBindingV2) -> dict[str, object]:
    if type(value) is not FactPayloadBindingV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def fact_payload_binding_from_mapping_v2(value: object) -> FactPayloadBindingV2:
    data = _exact_mapping(value, frozenset({"fact_id", "fact_sha256"}))
    return FactPayloadBindingV2(
        fact_id=_uuid_text(data["fact_id"]),
        fact_sha256=cast(str, data["fact_sha256"]),
    )


def input_binding_mapping_v2(
    value: PersistedFactBatchBindingV2,
) -> dict[str, object]:
    if type(value) is not PersistedFactBatchBindingV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def input_binding_from_mapping_v2(value: object) -> PersistedFactBatchBindingV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "batch_id",
                "batch_sha256",
                "chain_hash",
                "committed_at",
                "extractor_version",
                "facts",
                "persisted_sha256",
                "source_snapshot_id",
            }
        ),
    )
    facts = data["facts"]
    if type(facts) is not list:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return PersistedFactBatchBindingV2(
        batch_id=_uuid_text(data["batch_id"]),
        batch_sha256=cast(str, data["batch_sha256"]),
        persisted_sha256=cast(str, data["persisted_sha256"]),
        chain_hash=cast(str, data["chain_hash"]),
        source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
        extractor_version=cast(str, data["extractor_version"]),
        committed_at=_parse_utc(data["committed_at"]),
        facts=tuple(
            fact_payload_binding_from_mapping_v2(item)
            for item in cast(list[object], facts)
        ),
    )


def command_mapping_v2(value: FactConflictScanCommandV2) -> dict[str, object]:
    if type(value) is not FactConflictScanCommandV2:
        fail_fact_conflict_v2()
    return {
        "detector_version": value.detector_version,
        "input_bindings": [
            input_binding_mapping_v2(item) for item in value.input_bindings
        ],
        "input_set_sha256": value.input_set_sha256,
        "payload_sha256": value.payload_sha256,
    }


def command_from_mapping_v2(value: object) -> FactConflictScanCommandV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "detector_version",
                "input_bindings",
                "input_set_sha256",
                "payload_sha256",
            }
        ),
    )
    bindings = data["input_bindings"]
    if type(bindings) is not list:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return FactConflictScanCommandV2(
        detector_version=cast(str, data["detector_version"]),
        input_bindings=tuple(
            input_binding_from_mapping_v2(item) for item in cast(list[object], bindings)
        ),
        input_set_sha256=cast(str, data["input_set_sha256"]),
        payload_sha256=cast(str, data["payload_sha256"]),
    )


def comparable_mapping_v2(value: ComparableFactValueV2) -> dict[str, object]:
    if type(value) is not ComparableFactValueV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def comparable_from_mapping_v2(value: object) -> ComparableFactValueV2:
    data = _exact_mapping(
        value,
        frozenset(
            {"locale", "unit_code", "value_boolean", "value_kind", "value_numeric"}
        ),
    )
    numeric_value = data["value_numeric"]
    if numeric_value is not None and (
        type(numeric_value) is not str or _INTEGER_TEXT.fullmatch(numeric_value) is None
    ):
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        return ComparableFactValueV2(
            value_kind=FactValueKindV2(cast(str, data["value_kind"])),
            value_numeric=(None if numeric_value is None else Decimal(numeric_value)),
            value_boolean=cast(bool | None, data["value_boolean"]),
            unit_code=cast(str | None, data["unit_code"]),
            locale=cast(str | None, data["locale"]),
        )
    except InvalidOperation, TypeError, ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def fact_ref_mapping_v2(value: FactConflictFactRefV2) -> dict[str, object]:
    if type(value) is not FactConflictFactRefV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def fact_ref_from_mapping_v2(value: object) -> FactConflictFactRefV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "batch_id",
                "fact_id",
                "fact_sha256",
                "predicate",
                "source_snapshot_id",
                "subject_id",
                "subject_type",
                "valid_from",
                "valid_to",
                "value",
            }
        ),
    )
    valid_to = data["valid_to"]
    try:
        return FactConflictFactRefV2(
            fact_id=_uuid_text(data["fact_id"]),
            fact_sha256=cast(str, data["fact_sha256"]),
            batch_id=_uuid_text(data["batch_id"]),
            source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
            subject_type=FactSubjectTypeV2(cast(str, data["subject_type"])),
            subject_id=_uuid_text(data["subject_id"]),
            predicate=cast(str, data["predicate"]),
            value=comparable_from_mapping_v2(data["value"]),
            valid_from=_parse_utc(data["valid_from"]),
            valid_to=None if valid_to is None else _parse_utc(valid_to),
        )
    except TypeError, ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def conflict_mapping_v2(value: UnresolvedFactConflictV2) -> dict[str, object]:
    if type(value) is not UnresolvedFactConflictV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def conflict_from_mapping_v2(value: object) -> UnresolvedFactConflictV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "authority_priority_used",
                "conflict_id",
                "content_policy",
                "detected_at",
                "display_id",
                "left",
                "queue_status",
                "readiness",
                "reason",
                "resolution",
                "right",
                "scan_id",
                "silent_resolution_forbidden",
                "status",
                "tolerance",
                "winner_fact_id",
            }
        ),
    )
    try:
        return UnresolvedFactConflictV2(
            conflict_id=_uuid_text(data["conflict_id"]),
            display_id=cast(str, data["display_id"]),
            scan_id=_uuid_text(data["scan_id"]),
            left=fact_ref_from_mapping_v2(data["left"]),
            right=fact_ref_from_mapping_v2(data["right"]),
            reason=FactConflictReasonV2(cast(str, data["reason"])),
            status=FactConflictStatusV2(cast(str, data["status"])),
            queue_status=FactConflictQueueStatusV2(cast(str, data["queue_status"])),
            readiness=FactConflictReadinessV2(cast(str, data["readiness"])),
            content_policy=cast(str, data["content_policy"]),
            silent_resolution_forbidden=cast(bool, data["silent_resolution_forbidden"]),
            winner_fact_id=cast(None, data["winner_fact_id"]),
            tolerance=cast(None, data["tolerance"]),
            authority_priority_used=cast(bool, data["authority_priority_used"]),
            resolution=cast(None, data["resolution"]),
            detected_at=_parse_utc(data["detected_at"]),
        )
    except TypeError, ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def queue_mapping_v2(value: FactConflictReviewQueueRecordV2) -> dict[str, object]:
    if type(value) is not FactConflictReviewQueueRecordV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def queue_from_mapping_v2(value: object) -> FactConflictReviewQueueRecordV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "assigned_actor_id",
                "conflict_id",
                "conflict_status",
                "created_at",
                "queue_id",
                "readiness",
                "resolution",
                "status",
            }
        ),
    )
    try:
        return FactConflictReviewQueueRecordV2(
            queue_id=_uuid_text(data["queue_id"]),
            conflict_id=_uuid_text(data["conflict_id"]),
            status=FactConflictQueueStatusV2(cast(str, data["status"])),
            conflict_status=FactConflictStatusV2(cast(str, data["conflict_status"])),
            readiness=FactConflictReadinessV2(cast(str, data["readiness"])),
            assigned_actor_id=cast(None, data["assigned_actor_id"]),
            resolution=cast(None, data["resolution"]),
            created_at=_parse_utc(data["created_at"]),
        )
    except TypeError, ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def batch_mapping_v2(value: FactConflictDetectionBatchV2) -> dict[str, object]:
    if type(value) is not FactConflictDetectionBatchV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def batch_from_mapping_v2(value: object) -> FactConflictDetectionBatchV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "ai_action_count",
                "command",
                "comparison_count",
                "conflicts",
                "content_policy",
                "disjoint_window_count",
                "equal_value_count",
                "external_action_count",
                "incompatible_unit_or_locale_count",
                "provider_action_count",
                "publication_action_count",
                "queue",
                "queue_status",
                "readiness",
                "scan_id",
                "scanned_at",
                "silent_resolution_forbidden",
                "status",
            }
        ),
    )
    conflicts = data["conflicts"]
    queue = data["queue"]
    if type(conflicts) is not list or type(queue) is not list:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    try:
        return FactConflictDetectionBatchV2(
            scan_id=_uuid_text(data["scan_id"]),
            command=command_from_mapping_v2(data["command"]),
            conflicts=tuple(
                conflict_from_mapping_v2(item) for item in cast(list[object], conflicts)
            ),
            queue=tuple(
                queue_from_mapping_v2(item) for item in cast(list[object], queue)
            ),
            scanned_at=_parse_utc(data["scanned_at"]),
            comparison_count=cast(int, data["comparison_count"]),
            equal_value_count=cast(int, data["equal_value_count"]),
            disjoint_window_count=cast(int, data["disjoint_window_count"]),
            incompatible_unit_or_locale_count=cast(
                int, data["incompatible_unit_or_locale_count"]
            ),
            content_policy=cast(str, data["content_policy"]),
            silent_resolution_forbidden=cast(bool, data["silent_resolution_forbidden"]),
            status=FactConflictStatusV2(cast(str, data["status"])),
            queue_status=FactConflictQueueStatusV2(cast(str, data["queue_status"])),
            readiness=FactConflictReadinessV2(cast(str, data["readiness"])),
            external_action_count=cast(int, data["external_action_count"]),
            provider_action_count=cast(int, data["provider_action_count"]),
            publication_action_count=cast(int, data["publication_action_count"]),
            ai_action_count=cast(int, data["ai_action_count"]),
        )
    except TypeError, ValueError:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)


def event_mapping_v2(
    value: FactConflictsRecordedOutboxEventV2,
) -> dict[str, object]:
    if type(value) is not FactConflictsRecordedOutboxEventV2:
        fail_fact_conflict_v2()
    return dict(value.canonical_material)


def event_from_mapping_v2(value: object) -> FactConflictsRecordedOutboxEventV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "aggregate_id",
                "aggregate_version",
                "channel",
                "conflict_ids",
                "delivery_status",
                "event_id",
                "event_type",
                "external_action_count",
                "occurred_at",
                "queue_ids",
            }
        ),
    )
    conflict_ids = data["conflict_ids"]
    queue_ids = data["queue_ids"]
    if type(conflict_ids) is not list or type(queue_ids) is not list:
        fail_fact_conflict_v2(FactConflictFailureCodeV2.TAMPER_DETECTED)
    return FactConflictsRecordedOutboxEventV2(
        event_id=_uuid_text(data["event_id"]),
        event_type=cast(str, data["event_type"]),
        channel=cast(str, data["channel"]),
        aggregate_id=_uuid_text(data["aggregate_id"]),
        aggregate_version=cast(int, data["aggregate_version"]),
        conflict_ids=tuple(
            _uuid_text(item) for item in cast(list[object], conflict_ids)
        ),
        queue_ids=tuple(_uuid_text(item) for item in cast(list[object], queue_ids)),
        occurred_at=_parse_utc(data["occurred_at"]),
        delivery_status=cast(str, data["delivery_status"]),
        external_action_count=cast(int, data["external_action_count"]),
    )


def persisted_mapping_v2(
    value: PersistedFactConflictDetectionV2,
) -> dict[str, object]:
    if type(value) is not PersistedFactConflictDetectionV2:
        fail_fact_conflict_v2()
    return {
        "batch": batch_mapping_v2(value.batch),
        "chain_hash": value.chain_hash,
        "command": command_mapping_v2(value.command),
        "committed_at": utc_text_v2(value.committed_at),
        "event": event_mapping_v2(value.event),
        "previous_chain_hash": value.previous_chain_hash,
        "sequence": value.sequence,
    }


def persisted_from_mapping_v2(value: object) -> PersistedFactConflictDetectionV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "batch",
                "chain_hash",
                "command",
                "committed_at",
                "event",
                "previous_chain_hash",
                "sequence",
            }
        ),
    )
    return PersistedFactConflictDetectionV2(
        sequence=cast(int, data["sequence"]),
        previous_chain_hash=cast(str, data["previous_chain_hash"]),
        chain_hash=cast(str, data["chain_hash"]),
        command=command_from_mapping_v2(data["command"]),
        batch=batch_from_mapping_v2(data["batch"]),
        event=event_from_mapping_v2(data["event"]),
        committed_at=_parse_utc(data["committed_at"]),
    )


__all__ = [
    "FACT_CONFLICT_AI_ACTION_COUNT_V2",
    "FACT_CONFLICT_CONTENT_POLICY_V2",
    "FACT_CONFLICT_DETECTOR_VERSION_V2",
    "FACT_CONFLICT_EVENT_CHANNEL_V2",
    "FACT_CONFLICT_EVENT_TYPE_V2",
    "FACT_CONFLICT_EXTERNAL_ACTION_COUNT_V2",
    "FACT_CONFLICT_GENESIS_SHA256_V2",
    "FACT_CONFLICT_PROVIDER_ACTION_COUNT_V2",
    "FACT_CONFLICT_PUBLICATION_ACTION_COUNT_V2",
    "FACT_CONFLICT_SCHEMA_VERSION_V2",
    "ComparableFactValueV2",
    "FactComparisonOutcomeV2",
    "FactConflictDetectionBatchV2",
    "FactConflictDetectionResultV2",
    "FactConflictFactRefV2",
    "FactConflictFailureCodeV2",
    "FactConflictFailureV2",
    "FactConflictQueueStatusV2",
    "FactConflictReadinessV2",
    "FactConflictReasonV2",
    "FactConflictReplayStatusV2",
    "FactConflictReviewQueueRecordV2",
    "FactConflictScanCommandV2",
    "FactConflictStatusV2",
    "FactConflictStoreCommitV2",
    "FactConflictsRecordedOutboxEventV2",
    "FactPayloadBindingV2",
    "PersistedFactBatchBindingV2",
    "PersistedFactConflictDetectionV2",
    "UnresolvedFactConflictV2",
    "batch_from_mapping_v2",
    "batch_mapping_v2",
    "build_fact_conflict_artifacts_v2",
    "canonical_json_bytes_v2",
    "canonical_sha256_v2",
    "command_from_mapping_v2",
    "command_mapping_v2",
    "comparable_from_mapping_v2",
    "comparable_mapping_v2",
    "compare_fact_values_v2",
    "conflict_from_mapping_v2",
    "conflict_mapping_v2",
    "event_from_mapping_v2",
    "event_mapping_v2",
    "fact_conflict_chain_hash_v2",
    "fact_ref_from_mapping_v2",
    "fact_ref_mapping_v2",
    "fail_fact_conflict_v2",
    "normalize_persisted_inputs_v2",
    "persisted_from_mapping_v2",
    "persisted_mapping_v2",
    "queue_from_mapping_v2",
    "queue_mapping_v2",
    "utc_text_v2",
    "windows_overlap_v2",
]
