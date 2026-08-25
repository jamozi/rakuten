"""Maximum-safe recorded-local Fact extraction values for ST-0602 V2.

This module extracts only exact structural OFFER observations already committed
by ST-0503 and bound to exact ST-0601 raw bytes.  It has no provider, network,
AI, reviewer, ranking, publication, or external action capability.  Confidence
``1.0000`` means only deterministic extraction fidelity; it is never a truth or
publication attestation.
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

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CATALOG_IDENTITY_OPEN_DECISION_V2,
    CatalogConfidenceStatusV2,
    CatalogIdentityStatusV2,
    CatalogNormalizedOutboxEventV2,
    CatalogObservationKindV2,
    CatalogObservationV2,
    CatalogReadinessV2,
    PersistedCatalogNormalizationV2,
)
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ArtifactReadbackV2,
    artifact_id_v2,
)
from raos.domain.shared.identity import deterministic_uuid7


FACT_EXTRACTOR_VERSION_V2 = "ST0602_EXACT_STRUCTURAL_OFFER_FACTS_V2"
FACT_EXTRACTION_SCHEMA_VERSION_V2 = "ST0602_FACT_EXTRACTION_RUNTIME_V2"
FACT_EXTRACTION_JOB_TYPE_V2 = "evidence.extract_facts.v1"
FACT_EXTRACTION_JOB_QUEUE_V2 = "quality"
FACT_EXTRACTION_EVENT_TYPE_V2 = "jp.raos.evidence.facts_extracted.v1"
FACT_EXTRACTION_EVENT_CHANNEL_V2 = "quality.events"
FACT_EXTRACTION_CONFIDENCE_V2 = Decimal("1.0000")
FACT_EXTRACTION_GENESIS_SHA256_V2 = "0" * 64
FACT_EXTRACTION_EXTERNAL_ACTION_COUNT_V2 = 0
FACT_EXTRACTION_PROVIDER_ACTION_COUNT_V2 = 0
FACT_EXTRACTION_PUBLICATION_ACTION_COUNT_V2 = 0
FACT_EXTRACTION_AI_ACTION_COUNT_V2 = 0

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_POINTER = re.compile(r"/observations/(?:0|[1-9][0-9]{0,2})\Z", re.ASCII)
_PREDICATE = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z", re.ASCII)
_INTEGER_TEXT = re.compile(r"(?:0|[1-9][0-9]{0,19})\Z", re.ASCII)
_MAX_SEQUENCE = (1 << 63) - 1
_MAX_PRICE_INTEGER = 99_999_999_999_999_999_999
_ID_NAMESPACE = UUID("8ca28da8-cbb0-43c1-8e40-43335609d8ad")
_REDACTED = "<redacted-fact-extraction-runtime-v2>"


class FactExtractionFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    SOURCE_INTEGRITY = "SOURCE_INTEGRITY"
    OBSERVATION_SET_INVALID = "OBSERVATION_SET_INVALID"
    VALUE_INVALID = "VALUE_INVALID"
    UNIT_INVALID = "UNIT_INVALID"
    TIME_INVALID = "TIME_INVALID"
    CONFIDENCE_POLICY_INVALID = "CONFIDENCE_POLICY_INVALID"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    UNSAFE_PATH = "UNSAFE_PATH"
    SCHEMA_INTEGRITY = "SCHEMA_INTEGRITY"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"


class FactValueKindV2(str, Enum):
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"


class FactSubjectTypeV2(str, Enum):
    OFFER = "OFFER"


class FactKindV2(str, Enum):
    ASSERTED = "ASSERTED"


class FactConfidenceBasisV2(str, Enum):
    EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION = (
        "EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION"
    )


class FactStructuralValidationV2(str, Enum):
    VALID_STRUCTURAL_ONLY = "VALID_STRUCTURAL_ONLY"


class FactTruthAttestationV2(str, Enum):
    NOT_ATTESTED = "NOT_ATTESTED"


class FactPublicationReadinessV2(str, Enum):
    NOT_READY = "NOT_READY"


class FactExtractionReplayStatusV2(str, Enum):
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
        raise TypeError("fact extraction runtime values cannot be serialized")


class FactExtractionFailureV2(RuntimeError):
    """Closed failure with traceback-assignable exception state."""

    __slots__ = ("_code",)

    def __init__(self, code: FactExtractionFailureCodeV2) -> None:
        if type(code) is not FactExtractionFailureCodeV2:
            raise TypeError("invalid fact extraction failure code")
        RuntimeError.__init__(self, code.value)
        self._code = code

    @property
    def code(self) -> FactExtractionFailureCodeV2:
        return self._code

    def __repr__(self) -> str:
        return f"FactExtractionFailureV2(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("fact extraction failures cannot be serialized")


def fail_fact_extraction_v2(
    code: FactExtractionFailureCodeV2 = FactExtractionFailureCodeV2.INVALID_ARGUMENT,
) -> NoReturn:
    raise FactExtractionFailureV2(code) from None


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_fact_extraction_v2()
    return value


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_fact_extraction_v2()
    return value


def _positive_int(value: object, *, maximum: int = _MAX_SEQUENCE) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        fail_fact_extraction_v2()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TIME_INVALID)
    return value


def utc_text_v2(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        result = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    if result.tzinfo is not timezone.utc or utc_text_v2(result) != value:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
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
        fail_fact_extraction_v2()


def canonical_sha256_v2(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes_v2(value)).hexdigest()


def _stable_id(kind: str, material: object) -> UUID:
    return deterministic_uuid7(
        _ID_NAMESPACE,
        canonical_json_bytes_v2(
            {
                "kind": kind,
                "material": material,
                "schema_version": FACT_EXTRACTION_SCHEMA_VERSION_V2,
            }
        ),
    )


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    raw = cast(dict[object, object], value)
    if frozenset(raw) != keys or any(type(key) is not str for key in raw):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return {cast(str, key): item for key, item in raw.items()}


def _uuid_text(value: object) -> UUID:
    if type(value) is not str:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        result = UUID(value)
    except ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    if result.int == 0 or str(result) != value:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return result


@dataclass(frozen=True, slots=True, repr=False)
class FactExtractionSourceBindingV2(_RedactedValue):
    source_snapshot_id: UUID
    source_receipt_id: UUID
    artifact_id: UUID
    artifact_ref_sha256: str
    artifact_record_sha256: str
    artifact_entry_sha256: str
    artifact_object_version: int
    artifact_registry_sequence: int
    raw_sha256: str
    raw_byte_size: int
    raw_artifact_version: int
    raw_request_fingerprint: str
    raw_page: int
    observed_at: datetime
    normalized_at: datetime
    catalog_batch_id: UUID
    catalog_version: int
    catalog_chain_hash: str
    catalog_batch_sha256: str
    catalog_event_id: UUID
    catalog_event_sha256: str

    def __post_init__(self) -> None:
        for identifier in (
            self.source_snapshot_id,
            self.source_receipt_id,
            self.artifact_id,
            self.catalog_batch_id,
            self.catalog_event_id,
        ):
            _uuid(identifier)
        for digest in (
            self.artifact_ref_sha256,
            self.artifact_record_sha256,
            self.artifact_entry_sha256,
            self.raw_sha256,
            self.raw_request_fingerprint,
            self.catalog_chain_hash,
            self.catalog_batch_sha256,
            self.catalog_event_sha256,
        ):
            _sha256(digest)
        _positive_int(self.raw_byte_size, maximum=2 * 1024 * 1024)
        _positive_int(self.artifact_object_version)
        _positive_int(self.artifact_registry_sequence)
        _positive_int(self.raw_artifact_version)
        _positive_int(self.raw_page, maximum=100)
        observed = _utc(self.observed_at)
        if _utc(self.normalized_at) < observed:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TIME_INVALID)
        _positive_int(self.catalog_version)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "artifact_entry_sha256": self.artifact_entry_sha256,
            "artifact_id": str(self.artifact_id),
            "artifact_object_version": self.artifact_object_version,
            "artifact_record_sha256": self.artifact_record_sha256,
            "artifact_ref_sha256": self.artifact_ref_sha256,
            "artifact_registry_sequence": self.artifact_registry_sequence,
            "catalog_batch_id": str(self.catalog_batch_id),
            "catalog_batch_sha256": self.catalog_batch_sha256,
            "catalog_chain_hash": self.catalog_chain_hash,
            "catalog_event_id": str(self.catalog_event_id),
            "catalog_event_sha256": self.catalog_event_sha256,
            "catalog_version": self.catalog_version,
            "normalized_at": utc_text_v2(self.normalized_at),
            "observed_at": utc_text_v2(self.observed_at),
            "raw_artifact_version": self.raw_artifact_version,
            "raw_byte_size": self.raw_byte_size,
            "raw_page": self.raw_page,
            "raw_request_fingerprint": self.raw_request_fingerprint,
            "raw_sha256": self.raw_sha256,
            "source_receipt_id": str(self.source_receipt_id),
            "source_snapshot_id": str(self.source_snapshot_id),
        }


@dataclass(frozen=True, slots=True, repr=False)
class FactExtractionCommandV2(_RedactedValue):
    source_binding: FactExtractionSourceBindingV2
    extractor_version: str
    job_type: str
    queue: str
    subject_hints: tuple[()]
    payload_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.source_binding) is not FactExtractionSourceBindingV2
            or self.extractor_version != FACT_EXTRACTOR_VERSION_V2
            or self.job_type != FACT_EXTRACTION_JOB_TYPE_V2
            or self.queue != FACT_EXTRACTION_JOB_QUEUE_V2
            or self.subject_hints != ()
        ):
            fail_fact_extraction_v2()
        expected = canonical_sha256_v2(
            {
                "extractor_version": self.extractor_version,
                "job_type": self.job_type,
                "queue": self.queue,
                "source_binding": self.source_binding.canonical_material,
                "subject_hints": [],
            }
        )
        if _sha256(self.payload_sha256) != expected:
            fail_fact_extraction_v2()

    @property
    def source_snapshot_id(self) -> UUID:
        return self.source_binding.source_snapshot_id

    @property
    def idempotency_key(self) -> tuple[UUID, str]:
        return (self.source_snapshot_id, self.extractor_version)

    @classmethod
    def issue(
        cls, source_binding: FactExtractionSourceBindingV2
    ) -> FactExtractionCommandV2:
        if type(source_binding) is not FactExtractionSourceBindingV2:
            fail_fact_extraction_v2()
        material: dict[str, object] = {
            "extractor_version": FACT_EXTRACTOR_VERSION_V2,
            "job_type": FACT_EXTRACTION_JOB_TYPE_V2,
            "queue": FACT_EXTRACTION_JOB_QUEUE_V2,
            "source_binding": source_binding.canonical_material,
            "subject_hints": [],
        }
        return cls(
            source_binding=source_binding,
            extractor_version=FACT_EXTRACTOR_VERSION_V2,
            job_type=FACT_EXTRACTION_JOB_TYPE_V2,
            queue=FACT_EXTRACTION_JOB_QUEUE_V2,
            subject_hints=(),
            payload_sha256=canonical_sha256_v2(material),
        )


@dataclass(frozen=True, slots=True, repr=False)
class FactLocatorV2(_RedactedValue):
    pointer: str
    normalized_observation_id: UUID
    normalized_observation_ordinal: int
    normalized_observation_kind: CatalogObservationKindV2
    catalog_batch_id: UUID

    def __post_init__(self) -> None:
        if type(self.pointer) is not str or _POINTER.fullmatch(self.pointer) is None:
            fail_fact_extraction_v2()
        _uuid(self.normalized_observation_id)
        ordinal = _positive_int(self.normalized_observation_ordinal, maximum=120)
        if (
            self.pointer != f"/observations/{ordinal - 1}"
            or type(self.normalized_observation_kind) is not CatalogObservationKindV2
            or self.normalized_observation_kind
            is CatalogObservationKindV2.AFFILIATE_LINK
        ):
            fail_fact_extraction_v2()
        _uuid(self.catalog_batch_id)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "catalog_batch_id": str(self.catalog_batch_id),
            "kind": "NORMALIZED_OBSERVATION_JSON_POINTER",
            "normalized_observation_id": str(self.normalized_observation_id),
            "normalized_observation_kind": self.normalized_observation_kind.value,
            "normalized_observation_ordinal": self.normalized_observation_ordinal,
            "pointer": self.pointer,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ExactOfferFactV2(_RedactedValue):
    fact_id: UUID
    display_id: str
    source_snapshot_id: UUID
    subject_type: FactSubjectTypeV2
    subject_id: UUID
    predicate: str
    value_kind: FactValueKindV2
    value_numeric: Decimal | None
    value_boolean: bool | None
    unit_code: str | None
    locale: str | None
    fact_kind: FactKindV2
    confidence: Decimal
    confidence_basis: FactConfidenceBasisV2
    valid_from: datetime
    valid_to: None
    locator: FactLocatorV2
    extractor_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.fact_id)
        if (
            type(self.display_id) is not str
            or self.display_id != f"FCT-{self.fact_id.hex[:20].upper()}"
        ):
            fail_fact_extraction_v2()
        _uuid(self.source_snapshot_id)
        _uuid(self.subject_id)
        if (
            self.subject_type is not FactSubjectTypeV2.OFFER
            or type(self.predicate) is not str
            or _PREDICATE.fullmatch(self.predicate) is None
            or type(self.value_kind) is not FactValueKindV2
            or self.fact_kind is not FactKindV2.ASSERTED
            or type(self.confidence) is not Decimal
            or self.confidence != FACT_EXTRACTION_CONFIDENCE_V2
            or self.confidence.as_tuple() != FACT_EXTRACTION_CONFIDENCE_V2.as_tuple()
            or self.confidence_basis
            is not FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION
            or self.valid_to is not None
            or type(self.locator) is not FactLocatorV2
            or self.extractor_version != FACT_EXTRACTOR_VERSION_V2
            or self.locator.normalized_observation_kind.value != self.predicate
        ):
            fail_fact_extraction_v2()
        if self.value_kind is FactValueKindV2.NUMERIC:
            if (
                type(self.value_numeric) is not Decimal
                or not self.value_numeric.is_finite()
                or self.value_numeric != self.value_numeric.to_integral_value()
                or not Decimal(0) <= self.value_numeric <= Decimal(_MAX_PRICE_INTEGER)
                or self.value_boolean is not None
                or self.unit_code != "JPY"
                or self.locale != "ja-JP"
                or self.predicate != CatalogObservationKindV2.PRICE_JPY.value
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.VALUE_INVALID)
        else:
            if (
                self.value_numeric is not None
                or type(self.value_boolean) is not bool
                or self.unit_code is not None
                or self.locale is not None
                or self.predicate
                not in {
                    CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG.value,
                    CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG.value,
                }
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.VALUE_INVALID)
        valid_from = _utc(self.valid_from)
        if _utc(self.created_at) < valid_from:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TIME_INVALID)
        expected = _stable_id(
            "fact",
            {
                "extractor_version": self.extractor_version,
                "locator": self.locator.canonical_material,
                "predicate": self.predicate,
                "source_snapshot_id": str(self.source_snapshot_id),
                "subject_id": str(self.subject_id),
                "subject_type": self.subject_type.value,
                "unit_code": self.unit_code,
                "value_boolean": self.value_boolean,
                "value_numeric": (
                    None
                    if self.value_numeric is None
                    else str(self.value_numeric.to_integral_value())
                ),
            },
        )
        if self.fact_id != expected:
            fail_fact_extraction_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "confidence": "1.0000",
            "confidence_basis": self.confidence_basis.value,
            "created_at": utc_text_v2(self.created_at),
            "display_id": self.display_id,
            "extractor_version": self.extractor_version,
            "fact_id": str(self.fact_id),
            "fact_kind": self.fact_kind.value,
            "locale": self.locale,
            "locator": self.locator.canonical_material,
            "predicate": self.predicate,
            "source_snapshot_id": str(self.source_snapshot_id),
            "subject_id": str(self.subject_id),
            "subject_type": self.subject_type.value,
            "unit_code": self.unit_code,
            "valid_from": utc_text_v2(self.valid_from),
            "valid_to": None,
            "value_boolean": self.value_boolean,
            "value_kind": self.value_kind.value,
            "value_numeric": (
                None
                if self.value_numeric is None
                else str(self.value_numeric.to_integral_value())
            ),
        }


@dataclass(frozen=True, slots=True, repr=False)
class FactValidationRecordV2(_RedactedValue):
    fact_id: UUID
    source_snapshot_id: UUID
    unit: FactStructuralValidationV2
    time: FactStructuralValidationV2
    source: FactStructuralValidationV2
    confidence: FactStructuralValidationV2
    truth_attestation: FactTruthAttestationV2
    publication_readiness: FactPublicationReadinessV2
    manual_review_required: bool

    def __post_init__(self) -> None:
        _uuid(self.fact_id)
        _uuid(self.source_snapshot_id)
        if (
            self.unit is not FactStructuralValidationV2.VALID_STRUCTURAL_ONLY
            or self.time is not FactStructuralValidationV2.VALID_STRUCTURAL_ONLY
            or self.source is not FactStructuralValidationV2.VALID_STRUCTURAL_ONLY
            or self.confidence is not FactStructuralValidationV2.VALID_STRUCTURAL_ONLY
            or self.truth_attestation is not FactTruthAttestationV2.NOT_ATTESTED
            or self.publication_readiness is not FactPublicationReadinessV2.NOT_READY
            or self.manual_review_required is not True
        ):
            fail_fact_extraction_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "confidence": self.confidence.value,
            "fact_id": str(self.fact_id),
            "manual_review_required": self.manual_review_required,
            "publication_readiness": self.publication_readiness.value,
            "source": self.source.value,
            "source_snapshot_id": str(self.source_snapshot_id),
            "time": self.time.value,
            "truth_attestation": self.truth_attestation.value,
            "unit": self.unit.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class FactExtractionBatchV2(_RedactedValue):
    batch_id: UUID
    command: FactExtractionCommandV2
    facts: tuple[ExactOfferFactV2, ...]
    validations: tuple[FactValidationRecordV2, ...]
    extracted_at: datetime
    identity_status: CatalogIdentityStatusV2
    readiness: CatalogReadinessV2
    open_decision: str
    truth_attestation: FactTruthAttestationV2
    confidence_basis: FactConfidenceBasisV2
    external_action_count: int
    provider_action_count: int
    publication_action_count: int
    ai_action_count: int

    def __post_init__(self) -> None:
        _uuid(self.batch_id)
        if (
            type(self.command) is not FactExtractionCommandV2
            or type(self.facts) is not tuple
            or any(type(item) is not ExactOfferFactV2 for item in self.facts)
            or type(self.validations) is not tuple
            or any(
                type(item) is not FactValidationRecordV2 for item in self.validations
            )
            or len(self.facts) != len(self.validations)
            or len({item.fact_id for item in self.facts}) != len(self.facts)
            or tuple(item.fact_id for item in self.facts)
            != tuple(item.fact_id for item in self.validations)
            or any(
                item.source_snapshot_id != self.command.source_snapshot_id
                for item in self.facts
            )
            or any(
                item.source_snapshot_id != self.command.source_snapshot_id
                for item in self.validations
            )
            or any(
                item.locator.catalog_batch_id
                != self.command.source_binding.catalog_batch_id
                or item.valid_from != self.command.source_binding.observed_at
                or item.created_at != self.command.source_binding.normalized_at
                for item in self.facts
            )
            or tuple(item.locator.normalized_observation_ordinal for item in self.facts)
            != tuple(
                sorted(
                    item.locator.normalized_observation_ordinal for item in self.facts
                )
            )
            or self.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or self.readiness is not CatalogReadinessV2.NOT_READY
            or self.open_decision != CATALOG_IDENTITY_OPEN_DECISION_V2
            or self.truth_attestation is not FactTruthAttestationV2.NOT_ATTESTED
            or self.confidence_basis
            is not FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
            or type(self.provider_action_count) is not int
            or self.provider_action_count != 0
            or type(self.publication_action_count) is not int
            or self.publication_action_count != 0
            or type(self.ai_action_count) is not int
            or self.ai_action_count != 0
        ):
            fail_fact_extraction_v2()
        if _utc(self.extracted_at) != self.command.source_binding.normalized_at:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TIME_INVALID)
        expected = _stable_id(
            "fact_batch",
            {
                "extractor_version": self.command.extractor_version,
                "payload_sha256": self.command.payload_sha256,
                "source_snapshot_id": str(self.command.source_snapshot_id),
            },
        )
        if self.batch_id != expected:
            fail_fact_extraction_v2()

    @property
    def manual_review_required_count(self) -> int:
        return len(self.validations)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "ai_action_count": self.ai_action_count,
            "batch_id": str(self.batch_id),
            "command": command_mapping_v2(self.command),
            "confidence_basis": self.confidence_basis.value,
            "external_action_count": self.external_action_count,
            "extracted_at": utc_text_v2(self.extracted_at),
            "facts": [item.canonical_material for item in self.facts],
            "identity_status": self.identity_status.value,
            "manual_review_required_count": self.manual_review_required_count,
            "open_decision": self.open_decision,
            "provider_action_count": self.provider_action_count,
            "publication_action_count": self.publication_action_count,
            "readiness": self.readiness.value,
            "truth_attestation": self.truth_attestation.value,
            "validations": [item.canonical_material for item in self.validations],
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)


@dataclass(frozen=True, slots=True, repr=False)
class FactsExtractedOutboxEventV2(_RedactedValue):
    event_id: UUID
    event_type: str
    channel: str
    aggregate_id: UUID
    aggregate_version: int
    source_snapshot_id: UUID
    fact_ids: tuple[UUID, ...]
    extractor_version: str
    manual_review_required_count: int
    occurred_at: datetime
    delivery_status: str
    external_action_count: int

    def __post_init__(self) -> None:
        _uuid(self.event_id)
        _uuid(self.aggregate_id)
        _uuid(self.source_snapshot_id)
        if (
            self.event_type != FACT_EXTRACTION_EVENT_TYPE_V2
            or self.channel != FACT_EXTRACTION_EVENT_CHANNEL_V2
            or self.aggregate_id != self.source_snapshot_id
            or type(self.aggregate_version) is not int
            or self.aggregate_version != 1
            or type(self.fact_ids) is not tuple
            or any(type(item) is not UUID or item.int == 0 for item in self.fact_ids)
            or len(set(self.fact_ids)) != len(self.fact_ids)
            or self.extractor_version != FACT_EXTRACTOR_VERSION_V2
            or type(self.manual_review_required_count) is not int
            or self.manual_review_required_count != len(self.fact_ids)
            or self.delivery_status != "RECORDED_LOCAL_NOT_DELIVERED"
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
        ):
            fail_fact_extraction_v2()
        _utc(self.occurred_at)
        expected = _stable_id(
            "facts_extracted_event",
            {
                "event_type": self.event_type,
                "extractor_version": self.extractor_version,
                "fact_ids": [str(item) for item in self.fact_ids],
                "source_snapshot_id": str(self.source_snapshot_id),
            },
        )
        if self.event_id != expected:
            fail_fact_extraction_v2()

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "aggregate_id": str(self.aggregate_id),
            "aggregate_version": self.aggregate_version,
            "channel": self.channel,
            "delivery_status": self.delivery_status,
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "external_action_count": self.external_action_count,
            "fact_ids": [str(item) for item in self.fact_ids],
            "extractor_version": self.extractor_version,
            "manual_review_required_count": self.manual_review_required_count,
            "occurred_at": utc_text_v2(self.occurred_at),
            "source_snapshot_id": str(self.source_snapshot_id),
        }

    @property
    def schema_data(self) -> dict[str, object]:
        return {
            "source_snapshot_id": str(self.source_snapshot_id),
            "fact_ids": [str(item) for item in self.fact_ids],
            "extractor_version": self.extractor_version,
            "manual_review_required_count": self.manual_review_required_count,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)

    @classmethod
    def from_batch(cls, batch: FactExtractionBatchV2) -> FactsExtractedOutboxEventV2:
        if type(batch) is not FactExtractionBatchV2:
            fail_fact_extraction_v2()
        fact_ids = tuple(item.fact_id for item in batch.facts)
        material = {
            "event_type": FACT_EXTRACTION_EVENT_TYPE_V2,
            "extractor_version": batch.command.extractor_version,
            "fact_ids": [str(item) for item in fact_ids],
            "source_snapshot_id": str(batch.command.source_snapshot_id),
        }
        return cls(
            event_id=_stable_id("facts_extracted_event", material),
            event_type=FACT_EXTRACTION_EVENT_TYPE_V2,
            channel=FACT_EXTRACTION_EVENT_CHANNEL_V2,
            aggregate_id=batch.command.source_snapshot_id,
            aggregate_version=1,
            source_snapshot_id=batch.command.source_snapshot_id,
            fact_ids=fact_ids,
            extractor_version=batch.command.extractor_version,
            manual_review_required_count=len(fact_ids),
            occurred_at=batch.extracted_at,
            delivery_status="RECORDED_LOCAL_NOT_DELIVERED",
            external_action_count=0,
        )


def fact_chain_hash_v2(
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
class PersistedFactExtractionV2(_RedactedValue):
    sequence: int
    previous_chain_hash: str
    chain_hash: str
    command: FactExtractionCommandV2
    batch: FactExtractionBatchV2
    event: FactsExtractedOutboxEventV2
    committed_at: datetime

    def __post_init__(self) -> None:
        sequence = _positive_int(self.sequence)
        previous = _sha256(self.previous_chain_hash)
        if (
            type(self.command) is not FactExtractionCommandV2
            or type(self.batch) is not FactExtractionBatchV2
            or type(self.event) is not FactsExtractedOutboxEventV2
            or self.batch.command != self.command
            or self.event != FactsExtractedOutboxEventV2.from_batch(self.batch)
            or _utc(self.committed_at) != self.batch.extracted_at
            or _sha256(self.chain_hash)
            != fact_chain_hash_v2(
                previous_chain_hash=previous,
                sequence=sequence,
                command_payload_sha256=self.command.payload_sha256,
                batch_sha256=self.batch.sha256,
                event_sha256=self.event.sha256,
                committed_at=self.committed_at,
            )
        ):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)


@dataclass(frozen=True, slots=True, repr=False)
class FactStoreCommitV2(_RedactedValue):
    persisted: PersistedFactExtractionV2
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedFactExtractionV2
            or type(self.replayed) is not bool
        ):
            fail_fact_extraction_v2()


@dataclass(frozen=True, slots=True, repr=False)
class FactExtractionResultV2(_RedactedValue):
    persisted: PersistedFactExtractionV2
    replay_status: FactExtractionReplayStatusV2
    external_action_count: int
    provider_action_count: int
    publication_action_count: int
    ai_action_count: int

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedFactExtractionV2
            or type(self.replay_status) is not FactExtractionReplayStatusV2
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
            or type(self.provider_action_count) is not int
            or self.provider_action_count != 0
            or type(self.publication_action_count) is not int
            or self.publication_action_count != 0
            or type(self.ai_action_count) is not int
            or self.ai_action_count != 0
        ):
            fail_fact_extraction_v2()


def _revalidate_dependencies(
    artifact: ArtifactReadbackV2,
    normalization: PersistedCatalogNormalizationV2,
) -> None:
    if (
        type(artifact) is not ArtifactReadbackV2
        or type(normalization) is not PersistedCatalogNormalizationV2
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH)
    try:
        artifact.record.candidate.provenance.__post_init__()
        artifact.record.candidate.__post_init__()
        artifact.record.artifact_ref.__post_init__()
        artifact.record.__post_init__()
        artifact.__post_init__()
        normalization.batch.source_snapshot.__post_init__()
        for candidate in normalization.batch.candidates:
            candidate.__post_init__()
        for offer in normalization.batch.offers:
            offer.__post_init__()
        for observation in normalization.batch.observations:
            observation.__post_init__()
        normalization.batch.__post_init__()
        normalization.event.__post_init__()
        normalization.__post_init__()
    except Exception:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.DEPENDENCY_MISMATCH)


def source_binding_from_dependencies_v2(
    *,
    artifact: ArtifactReadbackV2,
    normalization: PersistedCatalogNormalizationV2,
) -> FactExtractionSourceBindingV2:
    _revalidate_dependencies(artifact, normalization)
    record = artifact.record
    provenance = record.candidate.provenance
    batch = normalization.batch
    snapshot = batch.source_snapshot
    if (
        len(artifact.content) != snapshot.raw_byte_size
        or hashlib.sha256(artifact.content).hexdigest() != snapshot.raw_sha256
        or record.candidate.sha256 != snapshot.raw_sha256
        or record.candidate.byte_size != snapshot.raw_byte_size
        or provenance.source_receipt_id != snapshot.receipt_id
        or provenance.source_artifact_sha256 != snapshot.raw_sha256
        or provenance.source_artifact_version != snapshot.artifact_version
        or provenance.source_logical_key != snapshot.logical_key
        or provenance.source_request_fingerprint != snapshot.request_fingerprint
        or provenance.source_page != snapshot.page
        or provenance.acquired_at != snapshot.observed_at
        or record.artifact_id
        != artifact_id_v2(
            candidate=record.candidate,
            artifact_version=record.artifact_version,
        )
        or record.artifact_ref.sha256 != snapshot.raw_sha256
        or normalization.event != CatalogNormalizedOutboxEventV2.from_batch(batch)
        or normalization.event.batch_id != batch.batch_id
        or normalization.event.source_snapshot_id != snapshot.snapshot_id
        or normalization.event.observation_count != len(batch.observations)
        or normalization.event.candidate_count != len(batch.candidates)
        or normalization.event.offer_count != len(batch.offers)
        or type(normalization.event.external_actions) is not int
        or normalization.event.external_actions != 0
        or type(batch.external_actions) is not int
        or batch.external_actions != 0
        or snapshot.confidence is not None
        or snapshot.confidence_status is not CatalogConfidenceStatusV2.SOURCE_ABSENT
        or batch.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
        or batch.readiness is not CatalogReadinessV2.NOT_READY
        or batch.open_decision != CATALOG_IDENTITY_OPEN_DECISION_V2
        or batch.canonical_products != ()
        or batch.grouping_decisions != ()
        or batch.provider_derived_recommendation_inputs != ()
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.SOURCE_INTEGRITY)
    return FactExtractionSourceBindingV2(
        source_snapshot_id=snapshot.snapshot_id,
        source_receipt_id=snapshot.receipt_id,
        artifact_id=record.artifact_id.value,
        artifact_ref_sha256=record.artifact_ref.ref_sha256,
        artifact_record_sha256=record.record_sha256,
        artifact_entry_sha256=record.entry_sha256,
        artifact_object_version=record.artifact_ref.object_version,
        artifact_registry_sequence=record.sequence,
        raw_sha256=snapshot.raw_sha256,
        raw_byte_size=snapshot.raw_byte_size,
        raw_artifact_version=snapshot.artifact_version,
        raw_request_fingerprint=snapshot.request_fingerprint,
        raw_page=snapshot.page,
        observed_at=snapshot.observed_at,
        normalized_at=snapshot.normalized_at,
        catalog_batch_id=batch.batch_id,
        catalog_version=normalization.catalog_version,
        catalog_chain_hash=normalization.chain_hash,
        catalog_batch_sha256=batch.sha256,
        catalog_event_id=normalization.event.event_id,
        catalog_event_sha256=normalization.event.sha256,
    )


def _fact_from_observation(
    *,
    command: FactExtractionCommandV2,
    catalog_batch_id: UUID,
    observation: CatalogObservationV2,
) -> ExactOfferFactV2:
    if observation.kind is CatalogObservationKindV2.AFFILIATE_LINK:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.OBSERVATION_SET_INVALID)
    locator = FactLocatorV2(
        pointer=f"/observations/{observation.ordinal - 1}",
        normalized_observation_id=observation.observation_id,
        normalized_observation_ordinal=observation.ordinal,
        normalized_observation_kind=observation.kind,
        catalog_batch_id=catalog_batch_id,
    )
    numeric: Decimal | None = None
    boolean: bool | None = None
    unit: str | None = None
    locale: str | None = None
    if observation.kind is CatalogObservationKindV2.PRICE_JPY:
        if (
            type(observation.integer_value) is not int
            or not 0 <= observation.integer_value <= _MAX_PRICE_INTEGER
            or observation.unit_code != "JPY"
        ):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.VALUE_INVALID)
        numeric = Decimal(observation.integer_value)
        unit = "JPY"
        locale = "ja-JP"
        kind = FactValueKindV2.NUMERIC
    else:
        if (
            type(observation.boolean_value) is not bool
            or observation.unit_code is not None
        ):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.VALUE_INVALID)
        boolean = observation.boolean_value
        kind = FactValueKindV2.BOOLEAN
    material = {
        "extractor_version": command.extractor_version,
        "locator": locator.canonical_material,
        "predicate": observation.kind.value,
        "source_snapshot_id": str(command.source_snapshot_id),
        "subject_id": str(observation.offer_id),
        "subject_type": FactSubjectTypeV2.OFFER.value,
        "unit_code": unit,
        "value_boolean": boolean,
        "value_numeric": None if numeric is None else str(numeric),
    }
    fact_id = _stable_id("fact", material)
    return ExactOfferFactV2(
        fact_id=fact_id,
        display_id=f"FCT-{fact_id.hex[:20].upper()}",
        source_snapshot_id=command.source_snapshot_id,
        subject_type=FactSubjectTypeV2.OFFER,
        subject_id=observation.offer_id,
        predicate=observation.kind.value,
        value_kind=kind,
        value_numeric=numeric,
        value_boolean=boolean,
        unit_code=unit,
        locale=locale,
        fact_kind=FactKindV2.ASSERTED,
        confidence=FACT_EXTRACTION_CONFIDENCE_V2,
        confidence_basis=(
            FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION
        ),
        valid_from=observation.observed_at,
        valid_to=None,
        locator=locator,
        extractor_version=command.extractor_version,
        created_at=command.source_binding.normalized_at,
    )


def build_fact_extraction_artifacts_v2(
    *,
    artifact: ArtifactReadbackV2,
    normalization: PersistedCatalogNormalizationV2,
) -> tuple[
    FactExtractionCommandV2,
    FactExtractionBatchV2,
    FactsExtractedOutboxEventV2,
]:
    binding = source_binding_from_dependencies_v2(
        artifact=artifact,
        normalization=normalization,
    )
    command = FactExtractionCommandV2.issue(binding)
    offers = normalization.batch.offers
    observations = normalization.batch.observations
    offer_ids = {item.offer_id for item in offers}
    if len(offer_ids) != len(offers):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.OBSERVATION_SET_INVALID)
    by_offer: dict[UUID, list[CatalogObservationV2]] = {
        offer_id: [] for offer_id in offer_ids
    }
    for observation in observations:
        if (
            observation.offer_id not in by_offer
            or observation.source_snapshot_id != command.source_snapshot_id
            or observation.observed_at != binding.observed_at
            or observation.normalized_at != binding.normalized_at
            or observation.confidence is not None
            or observation.confidence_status
            is not CatalogConfidenceStatusV2.SOURCE_ABSENT
            or observation.recommendation_input is not False
        ):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.OBSERVATION_SET_INVALID)
        by_offer[observation.offer_id].append(observation)
    required = {
        CatalogObservationKindV2.PRICE_JPY,
        CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG,
        CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG,
    }
    for offer in offers:
        rows = by_offer[offer.offer_id]
        kinds = [item.kind for item in rows]
        if (
            set(kinds) - (required | {CatalogObservationKindV2.AFFILIATE_LINK})
            or not required.issubset(kinds)
            or any(kinds.count(kind) != 1 for kind in required)
            or kinds.count(CatalogObservationKindV2.AFFILIATE_LINK) > 1
            or offer.source_snapshot_id != command.source_snapshot_id
            or offer.canonical_product_id is not None
            or offer.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or offer.readiness is not CatalogReadinessV2.NOT_READY
            or offer.recommendation_eligible is not False
        ):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.OBSERVATION_SET_INVALID)
    structural = tuple(
        item
        for item in observations
        if item.kind is not CatalogObservationKindV2.AFFILIATE_LINK
    )
    facts = tuple(
        _fact_from_observation(
            command=command,
            catalog_batch_id=normalization.batch.batch_id,
            observation=item,
        )
        for item in structural
    )
    validations = tuple(
        FactValidationRecordV2(
            fact_id=item.fact_id,
            source_snapshot_id=item.source_snapshot_id,
            unit=FactStructuralValidationV2.VALID_STRUCTURAL_ONLY,
            time=FactStructuralValidationV2.VALID_STRUCTURAL_ONLY,
            source=FactStructuralValidationV2.VALID_STRUCTURAL_ONLY,
            confidence=FactStructuralValidationV2.VALID_STRUCTURAL_ONLY,
            truth_attestation=FactTruthAttestationV2.NOT_ATTESTED,
            publication_readiness=FactPublicationReadinessV2.NOT_READY,
            manual_review_required=True,
        )
        for item in facts
    )
    batch_id = _stable_id(
        "fact_batch",
        {
            "extractor_version": command.extractor_version,
            "payload_sha256": command.payload_sha256,
            "source_snapshot_id": str(command.source_snapshot_id),
        },
    )
    batch = FactExtractionBatchV2(
        batch_id=batch_id,
        command=command,
        facts=facts,
        validations=validations,
        extracted_at=binding.normalized_at,
        identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
        readiness=CatalogReadinessV2.NOT_READY,
        open_decision=CATALOG_IDENTITY_OPEN_DECISION_V2,
        truth_attestation=FactTruthAttestationV2.NOT_ATTESTED,
        confidence_basis=(
            FactConfidenceBasisV2.EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION
        ),
        external_action_count=0,
        provider_action_count=0,
        publication_action_count=0,
        ai_action_count=0,
    )
    return command, batch, FactsExtractedOutboxEventV2.from_batch(batch)


def source_binding_mapping_v2(
    value: FactExtractionSourceBindingV2,
) -> dict[str, object]:
    if type(value) is not FactExtractionSourceBindingV2:
        fail_fact_extraction_v2()
    return dict(value.canonical_material)


def source_binding_from_mapping_v2(value: object) -> FactExtractionSourceBindingV2:
    keys = frozenset(
        {
            "artifact_entry_sha256",
            "artifact_id",
            "artifact_object_version",
            "artifact_record_sha256",
            "artifact_ref_sha256",
            "artifact_registry_sequence",
            "catalog_batch_id",
            "catalog_batch_sha256",
            "catalog_chain_hash",
            "catalog_event_id",
            "catalog_event_sha256",
            "catalog_version",
            "normalized_at",
            "observed_at",
            "raw_artifact_version",
            "raw_byte_size",
            "raw_page",
            "raw_request_fingerprint",
            "raw_sha256",
            "source_receipt_id",
            "source_snapshot_id",
        }
    )
    data = _exact_mapping(value, keys)
    return FactExtractionSourceBindingV2(
        source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
        source_receipt_id=_uuid_text(data["source_receipt_id"]),
        artifact_id=_uuid_text(data["artifact_id"]),
        artifact_ref_sha256=cast(str, data["artifact_ref_sha256"]),
        artifact_record_sha256=cast(str, data["artifact_record_sha256"]),
        artifact_entry_sha256=cast(str, data["artifact_entry_sha256"]),
        artifact_object_version=cast(int, data["artifact_object_version"]),
        artifact_registry_sequence=cast(int, data["artifact_registry_sequence"]),
        raw_sha256=cast(str, data["raw_sha256"]),
        raw_byte_size=cast(int, data["raw_byte_size"]),
        raw_artifact_version=cast(int, data["raw_artifact_version"]),
        raw_request_fingerprint=cast(str, data["raw_request_fingerprint"]),
        raw_page=cast(int, data["raw_page"]),
        observed_at=_parse_utc(data["observed_at"]),
        normalized_at=_parse_utc(data["normalized_at"]),
        catalog_batch_id=_uuid_text(data["catalog_batch_id"]),
        catalog_version=cast(int, data["catalog_version"]),
        catalog_chain_hash=cast(str, data["catalog_chain_hash"]),
        catalog_batch_sha256=cast(str, data["catalog_batch_sha256"]),
        catalog_event_id=_uuid_text(data["catalog_event_id"]),
        catalog_event_sha256=cast(str, data["catalog_event_sha256"]),
    )


def command_mapping_v2(value: FactExtractionCommandV2) -> dict[str, object]:
    if type(value) is not FactExtractionCommandV2:
        fail_fact_extraction_v2()
    return {
        "extractor_version": value.extractor_version,
        "job_type": value.job_type,
        "payload_sha256": value.payload_sha256,
        "queue": value.queue,
        "source_binding": source_binding_mapping_v2(value.source_binding),
        "subject_hints": [],
    }


def command_from_mapping_v2(value: object) -> FactExtractionCommandV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "extractor_version",
                "job_type",
                "payload_sha256",
                "queue",
                "source_binding",
                "subject_hints",
            }
        ),
    )
    if type(data["subject_hints"]) is not list or data["subject_hints"] != []:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return FactExtractionCommandV2(
        source_binding=source_binding_from_mapping_v2(data["source_binding"]),
        extractor_version=cast(str, data["extractor_version"]),
        job_type=cast(str, data["job_type"]),
        queue=cast(str, data["queue"]),
        subject_hints=(),
        payload_sha256=cast(str, data["payload_sha256"]),
    )


def locator_from_mapping_v2(value: object) -> FactLocatorV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "catalog_batch_id",
                "kind",
                "normalized_observation_id",
                "normalized_observation_kind",
                "normalized_observation_ordinal",
                "pointer",
            }
        ),
    )
    if data["kind"] != "NORMALIZED_OBSERVATION_JSON_POINTER":
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        observation_kind = CatalogObservationKindV2(
            cast(str, data["normalized_observation_kind"])
        )
    except TypeError, ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return FactLocatorV2(
        pointer=cast(str, data["pointer"]),
        normalized_observation_id=_uuid_text(data["normalized_observation_id"]),
        normalized_observation_ordinal=cast(
            int, data["normalized_observation_ordinal"]
        ),
        normalized_observation_kind=observation_kind,
        catalog_batch_id=_uuid_text(data["catalog_batch_id"]),
    )


def fact_mapping_v2(value: ExactOfferFactV2) -> dict[str, object]:
    if type(value) is not ExactOfferFactV2:
        fail_fact_extraction_v2()
    return dict(value.canonical_material)


def fact_from_mapping_v2(value: object) -> ExactOfferFactV2:
    keys = frozenset(
        {
            "confidence",
            "confidence_basis",
            "created_at",
            "display_id",
            "extractor_version",
            "fact_id",
            "fact_kind",
            "locale",
            "locator",
            "predicate",
            "source_snapshot_id",
            "subject_id",
            "subject_type",
            "unit_code",
            "valid_from",
            "valid_to",
            "value_boolean",
            "value_kind",
            "value_numeric",
        }
    )
    data = _exact_mapping(value, keys)
    confidence_text = data["confidence"]
    numeric_value = data["value_numeric"]
    if (
        type(confidence_text) is not str
        or confidence_text != "1.0000"
        or (
            numeric_value is not None
            and (
                type(numeric_value) is not str
                or _INTEGER_TEXT.fullmatch(numeric_value) is None
            )
        )
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        numeric = None if numeric_value is None else Decimal(numeric_value)
        return ExactOfferFactV2(
            fact_id=_uuid_text(data["fact_id"]),
            display_id=cast(str, data["display_id"]),
            source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
            subject_type=FactSubjectTypeV2(cast(str, data["subject_type"])),
            subject_id=_uuid_text(data["subject_id"]),
            predicate=cast(str, data["predicate"]),
            value_kind=FactValueKindV2(cast(str, data["value_kind"])),
            value_numeric=numeric,
            value_boolean=cast(bool | None, data["value_boolean"]),
            unit_code=cast(str | None, data["unit_code"]),
            locale=cast(str | None, data["locale"]),
            fact_kind=FactKindV2(cast(str, data["fact_kind"])),
            confidence=Decimal(confidence_text),
            confidence_basis=FactConfidenceBasisV2(cast(str, data["confidence_basis"])),
            valid_from=_parse_utc(data["valid_from"]),
            valid_to=cast(None, data["valid_to"]),
            locator=locator_from_mapping_v2(data["locator"]),
            extractor_version=cast(str, data["extractor_version"]),
            created_at=_parse_utc(data["created_at"]),
        )
    except FactExtractionFailureV2:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    except InvalidOperation, TypeError, ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)


def validation_mapping_v2(value: FactValidationRecordV2) -> dict[str, object]:
    if type(value) is not FactValidationRecordV2:
        fail_fact_extraction_v2()
    return dict(value.canonical_material)


def validation_from_mapping_v2(value: object) -> FactValidationRecordV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "confidence",
                "fact_id",
                "manual_review_required",
                "publication_readiness",
                "source",
                "source_snapshot_id",
                "time",
                "truth_attestation",
                "unit",
            }
        ),
    )
    try:
        return FactValidationRecordV2(
            fact_id=_uuid_text(data["fact_id"]),
            source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
            unit=FactStructuralValidationV2(cast(str, data["unit"])),
            time=FactStructuralValidationV2(cast(str, data["time"])),
            source=FactStructuralValidationV2(cast(str, data["source"])),
            confidence=FactStructuralValidationV2(cast(str, data["confidence"])),
            truth_attestation=FactTruthAttestationV2(
                cast(str, data["truth_attestation"])
            ),
            publication_readiness=FactPublicationReadinessV2(
                cast(str, data["publication_readiness"])
            ),
            manual_review_required=cast(bool, data["manual_review_required"]),
        )
    except TypeError, ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)


def batch_mapping_v2(value: FactExtractionBatchV2) -> dict[str, object]:
    if type(value) is not FactExtractionBatchV2:
        fail_fact_extraction_v2()
    return dict(value.canonical_material)


def batch_from_mapping_v2(value: object) -> FactExtractionBatchV2:
    keys = frozenset(
        {
            "ai_action_count",
            "batch_id",
            "command",
            "confidence_basis",
            "external_action_count",
            "extracted_at",
            "facts",
            "identity_status",
            "manual_review_required_count",
            "open_decision",
            "provider_action_count",
            "publication_action_count",
            "readiness",
            "truth_attestation",
            "validations",
        }
    )
    data = _exact_mapping(value, keys)
    facts_raw = data["facts"]
    validations_raw = data["validations"]
    if type(facts_raw) is not list or type(validations_raw) is not list:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        result = FactExtractionBatchV2(
            batch_id=_uuid_text(data["batch_id"]),
            command=command_from_mapping_v2(data["command"]),
            facts=tuple(
                fact_from_mapping_v2(item) for item in cast(list[object], facts_raw)
            ),
            validations=tuple(
                validation_from_mapping_v2(item)
                for item in cast(list[object], validations_raw)
            ),
            extracted_at=_parse_utc(data["extracted_at"]),
            identity_status=CatalogIdentityStatusV2(cast(str, data["identity_status"])),
            readiness=CatalogReadinessV2(cast(str, data["readiness"])),
            open_decision=cast(str, data["open_decision"]),
            truth_attestation=FactTruthAttestationV2(
                cast(str, data["truth_attestation"])
            ),
            confidence_basis=FactConfidenceBasisV2(cast(str, data["confidence_basis"])),
            external_action_count=cast(int, data["external_action_count"]),
            provider_action_count=cast(int, data["provider_action_count"]),
            publication_action_count=cast(int, data["publication_action_count"]),
            ai_action_count=cast(int, data["ai_action_count"]),
        )
    except TypeError, ValueError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    if (
        type(data["manual_review_required_count"]) is not int
        or data["manual_review_required_count"] != result.manual_review_required_count
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return result


def event_mapping_v2(value: FactsExtractedOutboxEventV2) -> dict[str, object]:
    if type(value) is not FactsExtractedOutboxEventV2:
        fail_fact_extraction_v2()
    return dict(value.canonical_material)


def event_from_mapping_v2(value: object) -> FactsExtractedOutboxEventV2:
    keys = frozenset(
        {
            "aggregate_id",
            "aggregate_version",
            "channel",
            "delivery_status",
            "event_id",
            "event_type",
            "external_action_count",
            "fact_ids",
            "extractor_version",
            "manual_review_required_count",
            "occurred_at",
            "source_snapshot_id",
        }
    )
    data = _exact_mapping(value, keys)
    fact_ids = data["fact_ids"]
    if type(fact_ids) is not list:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return FactsExtractedOutboxEventV2(
        event_id=_uuid_text(data["event_id"]),
        event_type=cast(str, data["event_type"]),
        channel=cast(str, data["channel"]),
        aggregate_id=_uuid_text(data["aggregate_id"]),
        aggregate_version=cast(int, data["aggregate_version"]),
        source_snapshot_id=_uuid_text(data["source_snapshot_id"]),
        fact_ids=tuple(_uuid_text(item) for item in cast(list[object], fact_ids)),
        extractor_version=cast(str, data["extractor_version"]),
        manual_review_required_count=cast(int, data["manual_review_required_count"]),
        occurred_at=_parse_utc(data["occurred_at"]),
        delivery_status=cast(str, data["delivery_status"]),
        external_action_count=cast(int, data["external_action_count"]),
    )


def persisted_mapping_v2(value: PersistedFactExtractionV2) -> dict[str, object]:
    if type(value) is not PersistedFactExtractionV2:
        fail_fact_extraction_v2()
    return {
        "batch": batch_mapping_v2(value.batch),
        "chain_hash": value.chain_hash,
        "command": command_mapping_v2(value.command),
        "committed_at": utc_text_v2(value.committed_at),
        "event": event_mapping_v2(value.event),
        "previous_chain_hash": value.previous_chain_hash,
        "sequence": value.sequence,
    }


def persisted_from_mapping_v2(value: object) -> PersistedFactExtractionV2:
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
    return PersistedFactExtractionV2(
        sequence=cast(int, data["sequence"]),
        previous_chain_hash=cast(str, data["previous_chain_hash"]),
        chain_hash=cast(str, data["chain_hash"]),
        command=command_from_mapping_v2(data["command"]),
        batch=batch_from_mapping_v2(data["batch"]),
        event=event_from_mapping_v2(data["event"]),
        committed_at=_parse_utc(data["committed_at"]),
    )


__all__ = [
    "FACT_EXTRACTION_AI_ACTION_COUNT_V2",
    "FACT_EXTRACTION_CONFIDENCE_V2",
    "FACT_EXTRACTION_EVENT_CHANNEL_V2",
    "FACT_EXTRACTION_EVENT_TYPE_V2",
    "FACT_EXTRACTION_EXTERNAL_ACTION_COUNT_V2",
    "FACT_EXTRACTION_GENESIS_SHA256_V2",
    "FACT_EXTRACTION_JOB_QUEUE_V2",
    "FACT_EXTRACTION_JOB_TYPE_V2",
    "FACT_EXTRACTION_PROVIDER_ACTION_COUNT_V2",
    "FACT_EXTRACTION_PUBLICATION_ACTION_COUNT_V2",
    "FACT_EXTRACTION_SCHEMA_VERSION_V2",
    "FACT_EXTRACTOR_VERSION_V2",
    "ExactOfferFactV2",
    "FactConfidenceBasisV2",
    "FactExtractionBatchV2",
    "FactExtractionCommandV2",
    "FactExtractionFailureCodeV2",
    "FactExtractionFailureV2",
    "FactExtractionReplayStatusV2",
    "FactExtractionResultV2",
    "FactExtractionSourceBindingV2",
    "FactKindV2",
    "FactLocatorV2",
    "FactPublicationReadinessV2",
    "FactStoreCommitV2",
    "FactStructuralValidationV2",
    "FactSubjectTypeV2",
    "FactTruthAttestationV2",
    "FactValidationRecordV2",
    "FactValueKindV2",
    "FactsExtractedOutboxEventV2",
    "PersistedFactExtractionV2",
    "batch_from_mapping_v2",
    "batch_mapping_v2",
    "build_fact_extraction_artifacts_v2",
    "canonical_json_bytes_v2",
    "canonical_sha256_v2",
    "command_from_mapping_v2",
    "command_mapping_v2",
    "event_from_mapping_v2",
    "event_mapping_v2",
    "fact_chain_hash_v2",
    "fact_from_mapping_v2",
    "fact_mapping_v2",
    "fail_fact_extraction_v2",
    "persisted_from_mapping_v2",
    "persisted_mapping_v2",
    "source_binding_from_dependencies_v2",
    "source_binding_from_mapping_v2",
    "source_binding_mapping_v2",
    "utc_text_v2",
    "validation_from_mapping_v2",
    "validation_mapping_v2",
]
