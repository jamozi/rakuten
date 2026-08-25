"""Pure deterministic ST-0705 AI-output validation.

The evaluator accepts immutable, provider-neutral recorded values.  It never calls a
provider, repairs an output, infers a task profile, converts an AI article object into
the Content AST, persists a report, changes editorial state, or grants approval or
publication authority.  Task-specific JSON locators are supplied by the generated
profile registry; field-name heuristics are deliberately not used for resource,
numeric, order, or Claim mapping.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from types import MappingProxyType
from typing import Any, Final, NoReturn, SupportsIndex, cast, final
from uuid import RFC_4122, UUID

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)

from raos.domain.ai.provider import (
    CanonicalJsonObject,
    ProviderSuccess,
    Sha256Digest,
    StructuredOutputSchema,
)
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    CoverageStatus as ClaimCoverageStatus,
)


VALIDATOR_VERSION: Final = "ST0705_AI_OUTPUT_VALIDATION_V1"
PROFILE_REGISTRY_VERSION: Final = "ST0705_TASK_VALIDATION_PROFILES_V1"
TRUSTED_PROFILE_REGISTRY_SHA256: Final = Sha256Digest(
    "b3f19c2145e2cc003c94f6964e959eb546cee0d9bd053eaf855e03acbca8098b"
)
TRUSTED_PROFILE_SHA256_BY_TASK: Final[Mapping[str, Sha256Digest]] = MappingProxyType(
    {
        "AIT-001": Sha256Digest(
            "247246de42a0898db6010d14b92a28852c8ad1d47618b3edac685ce7cf85bcd5"
        ),
        "AIT-002": Sha256Digest(
            "fcd6fd7d7c3ceb4e06ecb2d21d6cd20144b877e4bfc2d1a2c5aca1f778b72791"
        ),
        "AIT-003": Sha256Digest(
            "26fb5c750af63ca25e787a6bca285452f3f3358af9f8739323cdb548499511e9"
        ),
        "AIT-004": Sha256Digest(
            "2a0f86668ef6c18efe1a4b67ea87c3c079340d16b79fb716de4bd8ed6914c26f"
        ),
        "AIT-005": Sha256Digest(
            "6ec82abd12772a79991f67c43e18e2bbddbd6553cd50bac6282ac9e61f13795f"
        ),
        "AIT-006": Sha256Digest(
            "9a2d5305472cee1368e226d8dcdc3a9f48bfe9a1569d9a400351baf7c40a11a8"
        ),
        "AIT-007": Sha256Digest(
            "79773c164f91cdae433e72a5e05df90e1f6bb45bfbe682b6c61f22cbb3371a06"
        ),
        "AIT-008": Sha256Digest(
            "da8108a2264cb652cce251a90d40fe1e503b837214976af9f65f157a5a6f3160"
        ),
        "AIT-009": Sha256Digest(
            "c6da22f063119fa6686b4b67f0b5213783e06bd5166f74638bfddfa3a0e76c9a"
        ),
        "AIT-010": Sha256Digest(
            "e8460cd3d5c8e934d545b2dea8f2944b78af1c5095a7a07da0b5147913229ec3"
        ),
        "AIT-011": Sha256Digest(
            "764d6fb52a0a78ecadf1eb128951424240999acc047568094f9cd3185ee111c4"
        ),
        "AIT-012": Sha256Digest(
            "dd06b3524ac36abb1108a93dfdc8afd7322e10c678db6c7a5b186bb6efb107d5"
        ),
    }
)
REPORT_PROFILE: Final = "ST0705_AI_OUTPUT_VALIDATION_REPORT_V1"
AUTHORITY: Final = "NONE"
_MAX_OUTPUT_BYTES: Final = 4 * 1024 * 1024
_MAX_RECORDED_OUTPUT_BYTES: Final = _MAX_OUTPUT_BYTES + 1
_MAX_COLLECTION: Final = 10_000
_MAX_PROFILE_ITEMS: Final = 256
_MAX_TEXT_LENGTH: Final = 4096
_MAX_REPORT_FINDINGS: Final = 64
_MAX_POINTER_DEPTH: Final = 24
_MAX_TEXT_VISITS: Final = 100_000
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z", re.ASCII)
_TASK_ID = re.compile(r"AIT-(?:00[1-9]|01[0-2])\Z", re.ASCII)
_RAOS_RESOURCE_ID = re.compile(r"[A-Z]{2,16}-[0-9A-HJKMNP-TV-Z]{26}\Z", re.ASCII)
_POINTER_TOKEN = re.compile(r"(?:\*|[A-Za-z0-9_$.-]{1,100})\Z", re.ASCII)


class LocalValidationStatus(str, Enum):
    LOCAL_VALIDATED = "LOCAL_VALIDATED"
    BLOCKED = "BLOCKED"
    UNEVALUABLE = "UNEVALUABLE"


class GateStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNEVALUABLE = "UNEVALUABLE"
    NOT_EXECUTED = "NOT_EXECUTED"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ProviderMode(str, Enum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


class ReferenceFormat(str, Enum):
    CANONICAL_UUID = "CANONICAL_UUID"
    RAOS_RESOURCE_ID = "RAOS_RESOURCE_ID"
    BOUNDED_TOKEN = "BOUNDED_TOKEN"


class ResourceKind(str, Enum):
    FACT = "FACT"
    PRODUCT = "PRODUCT"
    ARTICLE = "ARTICLE"
    KEYWORD = "KEYWORD"
    CLAIM = "CLAIM"
    FINDING = "FINDING"
    DIFF = "DIFF"
    OTHER = "OTHER"


class ResourceValidationStatus(str, Enum):
    VALID = "VALID"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class ScalarKind(str, Enum):
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    DATE = "DATE"
    UNIT = "UNIT"
    TAX = "TAX"
    CURRENCY = "CURRENCY"


class CoverageMode(str, Enum):
    NONE = "NONE"
    OPTIONAL_EXACT_ARTICLE_BINDING = "OPTIONAL_EXACT_ARTICLE_BINDING"
    REQUIRED_EXACT_ARTICLE_BINDING = "REQUIRED_EXACT_ARTICLE_BINDING"


class CoverageBindingState(str, Enum):
    ABSENT = "ABSENT"
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNEVALUABLE = "UNEVALUABLE"
    INVALID = "INVALID"


class SemanticReceiptKind(str, Enum):
    """Closed, hash-bound checks which cannot be inferred from output text."""

    INPUT_TAINT_SCAN = "INPUT_TAINT_SCAN"
    CONTEXT_MANIFEST_BINDING = "CONTEXT_MANIFEST_BINDING"
    PROVIDER_SUCCESS_SAFETY = "PROVIDER_SUCCESS_SAFETY"
    POLICY_BUNDLE_BINDING = "POLICY_BUNDLE_BINDING"
    REVIEW_CONTAMINATION_SCAN = "REVIEW_CONTAMINATION_SCAN"
    SENSITIVE_DATA_SCAN = "SENSITIVE_DATA_SCAN"
    EXPERIENCE_AUTHORIZATION = "EXPERIENCE_AUTHORIZATION"
    ARTICLE_STRUCTURE_INVENTORY = "ARTICLE_STRUCTURE_INVENTORY"
    COMPLETE_CLAIM_INVENTORY = "COMPLETE_CLAIM_INVENTORY"
    POLICY_COMPLETENESS_SCAN = "POLICY_COMPLETENESS_SCAN"
    REFRESH_DIFF_BINDING = "REFRESH_DIFF_BINDING"


class SemanticReceiptStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    UNEVALUABLE = "UNEVALUABLE"


class FailureDisposition(str, Enum):
    NO_FAILURE = "NO_FAILURE"
    ONE_REPAIR_ELIGIBLE = "ONE_REPAIR_ELIGIBLE"
    TERMINAL_BLOCK = "TERMINAL_BLOCK"
    UNEVALUABLE = "UNEVALUABLE"


class FindingCode(str, Enum):
    BINDING_UNAVAILABLE = "AIOV-BINDING-UNAVAILABLE"
    BINDING_MISMATCH = "AIOV-BINDING-MISMATCH"
    INVALID_JSON = "AI-OUT-001"
    SCHEMA_VIOLATION = "AI-OUT-002"
    UNKNOWN_PROPERTY_OR_ENUM = "AIOV-UNKNOWN-PROPERTY-OR-ENUM"
    UNKNOWN_RESOURCE_ID = "AI-OUT-003"
    RESOURCE_ID_INVALID = "AIOV-RESOURCE-ID-INVALID"
    FACT_SUPPORT_UNAVAILABLE = "AI-FCT-001"
    NUMERIC_OR_SEMANTIC_MISMATCH = "AI-FCT-002"
    PRODUCT_IDENTITY_MISMATCH = "AI-FCT-003"
    FABRICATED_EXPERIENCE = "AI-FCT-004"
    REVIEW_BODY_CONTAMINATION = "AI-POL-001"
    AFFILIATE_BIAS = "AI-POL-002"
    PROMPT_INJECTION_FOLLOWED = "AI-POL-003"
    SECRET_OR_RESTRICTED_DATA = "AI-POL-004"
    UNAUTHORIZED_STATE_CHANGE = "AI-POL-005"
    FORBIDDEN_FIELD_OR_TERM = "AIOV-FORBIDDEN-FIELD-OR-TERM"
    ORDER_MISMATCH = "AIOV-ORDER-MISMATCH"
    OUTPUT_TOO_LARGE = "AI-OUT-004"
    CLAIM_COUNT_EXCEEDED = "AIOV-CLAIM-COUNT-EXCEEDED"
    HASH_OR_VERSION_MISMATCH = "AIOV-HASH-OR-VERSION-MISMATCH"
    COVERAGE_UNAVAILABLE = "AIOV-COVERAGE-UNAVAILABLE"
    COVERAGE_BLOCKED = "AIOV-COVERAGE-BLOCKED"
    SEMANTIC_CAPABILITY_UNAVAILABLE = "AIOV-SEMANTIC-CAPABILITY-UNAVAILABLE"
    SEMANTIC_RECEIPT_UNAVAILABLE = "AIOV-SEMANTIC-RECEIPT-UNAVAILABLE"
    SEMANTIC_RECEIPT_BLOCKED = "AIOV-SEMANTIC-RECEIPT-BLOCKED"
    VALIDATOR_FAILURE = "AIOV-VALIDATOR-FAILURE"


GATE_IDS: Final[tuple[str, ...]] = tuple(f"AIOV-{number:03d}" for number in range(11))


@final
class AiOutputValidationError(ValueError):
    """Stable redacted construction/adapter failure."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_AI_OUTPUT_VALIDATION_VALUE")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("AI output validation errors are not serializable")


def _invalid() -> NoReturn:
    raise AiOutputValidationError() from None


def _require_sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        _invalid()
    return value


def _require_token(value: object) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        _invalid()
    return value


def _require_task_id(value: object) -> str:
    if type(value) is not str or _TASK_ID.fullmatch(value) is None:
        _invalid()
    return value


def _require_uuid(value: object) -> UUID:
    if (
        type(value) is not UUID
        or value.int == 0
        or value.variant != RFC_4122
        or str(value) != str(value).lower()
    ):
        _invalid()
    return value


def _require_utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        _invalid()
    try:
        offset = value.utcoffset()
    except Exception:
        _invalid()
    if offset != timezone.utc.utcoffset(None):
        _invalid()
    return value.replace(tzinfo=timezone.utc)


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    try:
        return CanonicalJsonObject(value).canonical_bytes()
    except Exception:
        _invalid()


def canonical_validation_time(value: object) -> datetime:
    """Return an immutable UTC snapshot using the evaluator's exact time rule."""

    return _require_utc(value)


@dataclass(frozen=True, slots=True, repr=False)
class JsonLocator:
    locator_id: str
    pointer: str
    _tokens: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_token(self.locator_id)
        if type(self.pointer) is not str or not self.pointer.startswith("/"):
            _invalid()
        tokens = tuple(self.pointer[1:].split("/"))
        if (
            not tokens
            or len(tokens) > _MAX_POINTER_DEPTH
            or any(_POINTER_TOKEN.fullmatch(token) is None for token in tokens)
        ):
            _invalid()
        object.__setattr__(self, "_tokens", tokens)

    def values(self, document: object) -> tuple[object, ...]:
        current: tuple[object, ...] = (document,)
        for token in self._tokens:
            following: list[object] = []
            for value in current:
                if token == "*":
                    if type(value) is not list:
                        return ()
                    following.extend(cast(list[object], value))
                else:
                    if type(value) is not dict or token not in value:
                        return ()
                    following.append(cast(dict[str, object], value)[token])
            current = tuple(following)
        return current


@dataclass(frozen=True, slots=True, repr=False)
class ResourceLocator:
    locator: JsonLocator
    reference_format: ReferenceFormat
    resource_kind: ResourceKind
    membership_required: bool = True

    def __post_init__(self) -> None:
        if (
            type(self.locator) is not JsonLocator
            or type(self.reference_format) is not ReferenceFormat
            or type(self.resource_kind) is not ResourceKind
            or type(self.membership_required) is not bool
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ScalarLocator:
    locator: JsonLocator
    scalar_kind: ScalarKind

    def __post_init__(self) -> None:
        if (
            type(self.locator) is not JsonLocator
            or type(self.scalar_kind) is not ScalarKind
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class OrderLocator:
    locator_id: str
    collection: JsonLocator
    identity_field: str
    rank_field: str

    def __post_init__(self) -> None:
        _require_token(self.locator_id)
        if type(self.collection) is not JsonLocator:
            _invalid()
        _require_token(self.identity_field)
        _require_token(self.rank_field)


@dataclass(frozen=True, slots=True, repr=False)
class ResourceBinding:
    resource_id: str
    resource_kind: ResourceKind
    validation_status: ResourceValidationStatus
    value_sha256: Sha256Digest | None
    expected_subject_identity_sha256: Sha256Digest | None
    observed_subject_identity_sha256: Sha256Digest | None

    def __post_init__(self) -> None:
        if (
            type(self.resource_id) is not str
            or not self.resource_id
            or len(self.resource_id) > 256
            or self.resource_id != self.resource_id.strip()
            or type(self.resource_kind) is not ResourceKind
            or type(self.validation_status) is not ResourceValidationStatus
        ):
            _invalid()
        for value in (
            self.value_sha256,
            self.expected_subject_identity_sha256,
            self.observed_subject_identity_sha256,
        ):
            if value is not None:
                _require_sha(value)
        if (self.expected_subject_identity_sha256 is None) != (
            self.observed_subject_identity_sha256 is None
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ScalarExpectation:
    locator_id: str
    scalar_kind: ScalarKind
    expected_values: tuple[None | bool | int | float | str, ...]
    expected_values_sha256: Sha256Digest = field(init=False)
    _canonical_values_bytes: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_token(self.locator_id)
        if (
            type(self.scalar_kind) is not ScalarKind
            or type(self.expected_values) is not tuple
            or len(self.expected_values) > _MAX_COLLECTION
            or any(
                type(value) not in {type(None), bool, int, float, str}
                for value in self.expected_values
            )
        ):
            _invalid()
        if any(
            type(value) is float and not math.isfinite(value)
            for value in self.expected_values
        ) or any(
            type(value) is str and len(value) > _MAX_TEXT_LENGTH
            for value in self.expected_values
        ):
            _invalid()
        payload = _canonical_bytes({"values": list(self.expected_values)})
        object.__setattr__(self, "_canonical_values_bytes", payload)
        object.__setattr__(self, "expected_values_sha256", Sha256Digest.of(payload))

    def matches(self, values: tuple[object, ...]) -> bool:
        if len(values) != len(self.expected_values) or any(
            type(observed) is not type(expected)
            for observed, expected in zip(values, self.expected_values, strict=True)
        ):
            return False
        try:
            return (
                _canonical_bytes({"values": list(values)})
                == self._canonical_values_bytes
            )
        except AiOutputValidationError:
            return False


@dataclass(frozen=True, slots=True, repr=False)
class SemanticReceiptBinding:
    receipt_kind: SemanticReceiptKind
    owner_story_id: str
    owner_contract_sha256: Sha256Digest
    request_sha256: Sha256Digest
    raw_output_sha256: Sha256Digest
    output_sha256: Sha256Digest | None
    input_context_sha256: Sha256Digest
    evidence_sha256: Sha256Digest
    status: SemanticReceiptStatus

    def __post_init__(self) -> None:
        if (
            type(self.receipt_kind) is not SemanticReceiptKind
            or type(self.status) is not SemanticReceiptStatus
            or type(self.owner_story_id) is not str
            or re.fullmatch(r"ST-[0-9]{4}", self.owner_story_id, re.ASCII) is None
        ):
            _invalid()
        _require_sha(self.owner_contract_sha256)
        _require_sha(self.request_sha256)
        _require_sha(self.raw_output_sha256)
        if self.output_sha256 is not None:
            _require_sha(self.output_sha256)
        _require_sha(self.input_context_sha256)
        _require_sha(self.evidence_sha256)


@dataclass(frozen=True, slots=True, repr=False)
class SemanticReceiptRequirement:
    receipt_kind: SemanticReceiptKind
    owner_story_id: str
    owner_contract_sha256: Sha256Digest

    def __post_init__(self) -> None:
        if (
            type(self.receipt_kind) is not SemanticReceiptKind
            or type(self.owner_story_id) is not str
            or re.fullmatch(r"ST-[0-9]{4}", self.owner_story_id, re.ASCII) is None
        ):
            _invalid()
        _require_sha(self.owner_contract_sha256)


@dataclass(frozen=True, slots=True, repr=False)
class RuntimeCheckBinding:
    check_name: str
    enforcement_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_token(self.check_name)
        if (
            type(self.enforcement_refs) is not tuple
            or not self.enforcement_refs
            or len(self.enforcement_refs) > _MAX_PROFILE_ITEMS
            or len(set(self.enforcement_refs)) != len(self.enforcement_refs)
            or any(
                _SAFE_TOKEN.fullmatch(item) is None for item in self.enforcement_refs
            )
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class OrderExpectation:
    locator_id: str
    ordered_resource_ids: tuple[str, ...]
    ordered_ranks: tuple[int, ...]

    def __post_init__(self) -> None:
        _require_token(self.locator_id)
        if (
            type(self.ordered_resource_ids) is not tuple
            or type(self.ordered_ranks) is not tuple
            or len(self.ordered_resource_ids) != len(self.ordered_ranks)
            or len(self.ordered_resource_ids) > _MAX_COLLECTION
            or len(set(self.ordered_resource_ids)) != len(self.ordered_resource_ids)
            or any(
                type(item) is not str
                or not item
                or len(item) > 256
                or item != item.strip()
                for item in self.ordered_resource_ids
            )
            or any(type(rank) is not int or rank < 0 for rank in self.ordered_ranks)
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ValidationManifest:
    manifest_version: str
    profile_registry_version: str
    profile_registry_sha256: Sha256Digest
    task_id: str
    task_code: str
    profile_sha256: Sha256Digest
    task_binding_sha256: Sha256Digest
    task_sha256: Sha256Digest
    prompt_sha256: Sha256Digest
    route_sha256: Sha256Digest
    output_schema_id: str
    output_schema_sha256: Sha256Digest
    expected_request_sha256: Sha256Digest
    expected_raw_output_sha256: Sha256Digest
    expected_output_sha256: Sha256Digest | None
    expected_input_context_sha256: Sha256Digest
    input_field_names: tuple[str, ...]
    resources: tuple[ResourceBinding, ...]
    scalar_expectations: tuple[ScalarExpectation, ...]
    order_expectations: tuple[OrderExpectation, ...]
    semantic_receipts: tuple[SemanticReceiptBinding, ...]
    article_version_id: UUID | None = None
    article_body_sha256: Sha256Digest | None = None
    source_packet_version_id: UUID | None = None
    source_packet_content_sha256: Sha256Digest | None = None
    complete_claim_set_sha256: Sha256Digest | None = None
    coverage_evaluation_input_sha256: Sha256Digest | None = None
    manifest_sha256: Sha256Digest = field(init=False)
    _canonical_bytes_snapshot: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_token(self.manifest_version)
        if self.profile_registry_version != PROFILE_REGISTRY_VERSION:
            _invalid()
        _require_sha(self.profile_registry_sha256)
        _require_task_id(self.task_id)
        _require_token(self.task_code)
        for value in (
            self.profile_sha256,
            self.task_binding_sha256,
            self.task_sha256,
            self.prompt_sha256,
            self.route_sha256,
            self.output_schema_sha256,
            self.expected_request_sha256,
            self.expected_raw_output_sha256,
            self.expected_input_context_sha256,
        ):
            _require_sha(value)
        if self.expected_output_sha256 is not None:
            _require_sha(self.expected_output_sha256)
        if (
            type(self.output_schema_id) is not str
            or len(self.output_schema_id) > 2048
            or not self.output_schema_id.startswith("https://schemas.raos.local/")
            or type(self.input_field_names) is not tuple
            or len(self.input_field_names) > _MAX_PROFILE_ITEMS
            or any(
                type(item) is not str or _SAFE_TOKEN.fullmatch(item) is None
                for item in self.input_field_names
            )
            or len(set(self.input_field_names)) != len(self.input_field_names)
            or type(self.resources) is not tuple
            or len(self.resources) > _MAX_COLLECTION
            or any(type(item) is not ResourceBinding for item in self.resources)
            or len({item.resource_id for item in self.resources}) != len(self.resources)
            or type(self.scalar_expectations) is not tuple
            or len(self.scalar_expectations) > _MAX_COLLECTION
            or any(
                type(item) is not ScalarExpectation for item in self.scalar_expectations
            )
            or len({item.locator_id for item in self.scalar_expectations})
            != len(self.scalar_expectations)
            or type(self.order_expectations) is not tuple
            or len(self.order_expectations) > _MAX_COLLECTION
            or any(
                type(item) is not OrderExpectation for item in self.order_expectations
            )
            or len({item.locator_id for item in self.order_expectations})
            != len(self.order_expectations)
            or type(self.semantic_receipts) is not tuple
            or len(self.semantic_receipts) > _MAX_COLLECTION
            or any(
                type(item) is not SemanticReceiptBinding
                for item in self.semantic_receipts
            )
            or len({item.receipt_kind for item in self.semantic_receipts})
            != len(self.semantic_receipts)
        ):
            _invalid()
        optional_uuid_values = (self.article_version_id, self.source_packet_version_id)
        for optional_uuid in optional_uuid_values:
            if optional_uuid is not None:
                _require_uuid(optional_uuid)
        for optional_digest in (
            self.article_body_sha256,
            self.source_packet_content_sha256,
            self.complete_claim_set_sha256,
            self.coverage_evaluation_input_sha256,
        ):
            if optional_digest is not None:
                _require_sha(optional_digest)
        article_fields = (
            self.article_version_id,
            self.article_body_sha256,
            self.source_packet_version_id,
            self.source_packet_content_sha256,
            self.complete_claim_set_sha256,
            self.coverage_evaluation_input_sha256,
        )
        if any(value is not None for value in article_fields) and not all(
            value is not None for value in article_fields
        ):
            _invalid()
        payload = _canonical_bytes(self._document())
        object.__setattr__(self, "_canonical_bytes_snapshot", payload)
        object.__setattr__(self, "manifest_sha256", Sha256Digest.of(payload))

    def _document(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "profile_registry_version": self.profile_registry_version,
            "profile_registry_sha256": self.profile_registry_sha256.value,
            "task_id": self.task_id,
            "task_code": self.task_code,
            "profile_sha256": self.profile_sha256.value,
            "task_binding_sha256": self.task_binding_sha256.value,
            "task_sha256": self.task_sha256.value,
            "prompt_sha256": self.prompt_sha256.value,
            "route_sha256": self.route_sha256.value,
            "output_schema_id": self.output_schema_id,
            "output_schema_sha256": self.output_schema_sha256.value,
            "expected_request_sha256": self.expected_request_sha256.value,
            "expected_raw_output_sha256": self.expected_raw_output_sha256.value,
            "expected_output_sha256": (
                None
                if self.expected_output_sha256 is None
                else self.expected_output_sha256.value
            ),
            "expected_input_context_sha256": self.expected_input_context_sha256.value,
            "input_field_names": list(self.input_field_names),
            "resources": [
                {
                    "resource_id": item.resource_id,
                    "resource_kind": item.resource_kind.value,
                    "validation_status": item.validation_status.value,
                    "value_sha256": (
                        None if item.value_sha256 is None else item.value_sha256.value
                    ),
                    "expected_subject_identity_sha256": (
                        None
                        if item.expected_subject_identity_sha256 is None
                        else item.expected_subject_identity_sha256.value
                    ),
                    "observed_subject_identity_sha256": (
                        None
                        if item.observed_subject_identity_sha256 is None
                        else item.observed_subject_identity_sha256.value
                    ),
                }
                for item in self.resources
            ],
            "scalar_expectations": [
                {
                    "locator_id": item.locator_id,
                    "scalar_kind": item.scalar_kind.value,
                    "expected_values_sha256": item.expected_values_sha256.value,
                }
                for item in self.scalar_expectations
            ],
            "order_expectations": [
                {
                    "locator_id": item.locator_id,
                    "ordered_resource_ids": list(item.ordered_resource_ids),
                    "ordered_ranks": list(item.ordered_ranks),
                }
                for item in self.order_expectations
            ],
            "semantic_receipts": [
                {
                    "receipt_kind": item.receipt_kind.value,
                    "owner_story_id": item.owner_story_id,
                    "owner_contract_sha256": item.owner_contract_sha256.value,
                    "request_sha256": item.request_sha256.value,
                    "raw_output_sha256": item.raw_output_sha256.value,
                    "output_sha256": (
                        None if item.output_sha256 is None else item.output_sha256.value
                    ),
                    "input_context_sha256": item.input_context_sha256.value,
                    "evidence_sha256": item.evidence_sha256.value,
                    "status": item.status.value,
                }
                for item in self.semantic_receipts
            ],
            "article_binding": (
                None
                if self.article_version_id is None
                else {
                    "article_version_id": str(self.article_version_id),
                    "article_body_sha256": cast(
                        Sha256Digest, self.article_body_sha256
                    ).value,
                    "source_packet_version_id": str(self.source_packet_version_id),
                    "source_packet_content_sha256": cast(
                        Sha256Digest, self.source_packet_content_sha256
                    ).value,
                    "complete_claim_set_sha256": cast(
                        Sha256Digest, self.complete_claim_set_sha256
                    ).value,
                    "coverage_evaluation_input_sha256": cast(
                        Sha256Digest, self.coverage_evaluation_input_sha256
                    ).value,
                }
            ),
        }

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes_snapshot


@dataclass(frozen=True, slots=True, repr=False)
class TaskValidationProfile:
    task_id: str
    task_code: str
    lifecycle: str
    output_schema_path: str
    output_schema_id: str
    output_schema_sha256: Sha256Digest
    task_binding_sha256: Sha256Digest
    task_sha256: Sha256Digest
    prompt_sha256: Sha256Digest
    route_sha256: Sha256Digest
    max_output_tokens: int
    max_output_bytes: int
    allowed_input_fields: tuple[str, ...]
    denied_input_fields: tuple[str, ...]
    required_runtime_checks: tuple[str, ...]
    prompt_required_runtime_checks: tuple[str, ...]
    runtime_check_bindings: tuple[RuntimeCheckBinding, ...]
    alignment_required_inputs: tuple[str, ...]
    alignment_required_outputs: tuple[str, ...]
    alignment_prohibited_outputs: tuple[str, ...]
    required_semantic_receipts: tuple[SemanticReceiptRequirement, ...]
    semantic_capability_limitations: tuple[str, ...]
    resource_locators: tuple[ResourceLocator, ...]
    scalar_locators: tuple[ScalarLocator, ...]
    order_locators: tuple[OrderLocator, ...]
    claim_collection: JsonLocator | None
    max_claim_count: int
    schema_version_locators: tuple[JsonLocator, ...]
    schema_version_value: str | None
    coverage_mode: CoverageMode
    profile_sha256: Sha256Digest = field(init=False)
    _canonical_bytes_snapshot: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_task_id(self.task_id)
        _require_token(self.task_code)
        _require_token(self.lifecycle)
        if (
            type(self.output_schema_path) is not str
            or len(self.output_schema_path) > 512
            or not self.output_schema_path.startswith(
                "contracts/raos-v0.4/contracts/ai/schemas/tasks/"
            )
            or type(self.output_schema_id) is not str
            or len(self.output_schema_id) > 2048
            or not self.output_schema_id.startswith("https://schemas.raos.local/")
        ):
            _invalid()
        _require_sha(self.output_schema_sha256)
        _require_sha(self.task_binding_sha256)
        _require_sha(self.task_sha256)
        _require_sha(self.prompt_sha256)
        _require_sha(self.route_sha256)
        if (
            type(self.max_output_tokens) is not int
            or self.max_output_tokens < 1
            or type(self.max_output_bytes) is not int
            or not 1 <= self.max_output_bytes <= _MAX_OUTPUT_BYTES
            or type(self.max_claim_count) is not int
            or not 0 <= self.max_claim_count <= _MAX_COLLECTION
            or type(self.coverage_mode) is not CoverageMode
        ):
            _invalid()
        tuple_fields = (
            self.allowed_input_fields,
            self.denied_input_fields,
            self.required_runtime_checks,
            self.prompt_required_runtime_checks,
            self.alignment_required_inputs,
            self.alignment_required_outputs,
            self.alignment_prohibited_outputs,
            self.semantic_capability_limitations,
        )
        if any(
            type(values) is not tuple
            or len(values) > _MAX_PROFILE_ITEMS
            or any(
                type(item) is not str
                or not item
                or item != item.strip()
                or len(item) > _MAX_TEXT_LENGTH
                for item in values
            )
            or len(set(values)) != len(values)
            for values in tuple_fields
        ):
            _invalid()
        if set(self.allowed_input_fields) & set(self.denied_input_fields):
            _invalid()
        expected_checks = set(self.required_runtime_checks) | set(
            self.prompt_required_runtime_checks
        )
        if (
            type(self.runtime_check_bindings) is not tuple
            or len(self.runtime_check_bindings) > _MAX_PROFILE_ITEMS
            or any(
                type(item) is not RuntimeCheckBinding
                for item in self.runtime_check_bindings
            )
            or {item.check_name for item in self.runtime_check_bindings}
            != expected_checks
        ):
            _invalid()
        if (
            type(self.required_semantic_receipts) is not tuple
            or len(self.required_semantic_receipts) > _MAX_PROFILE_ITEMS
            or any(
                type(item) is not SemanticReceiptRequirement
                for item in self.required_semantic_receipts
            )
            or len({item.receipt_kind for item in self.required_semantic_receipts})
            != len(self.required_semantic_receipts)
        ):
            _invalid()
        if (
            type(self.resource_locators) is not tuple
            or len(self.resource_locators) > _MAX_PROFILE_ITEMS
            or any(type(item) is not ResourceLocator for item in self.resource_locators)
            or type(self.scalar_locators) is not tuple
            or len(self.scalar_locators) > _MAX_PROFILE_ITEMS
            or any(type(item) is not ScalarLocator for item in self.scalar_locators)
            or type(self.order_locators) is not tuple
            or len(self.order_locators) > _MAX_PROFILE_ITEMS
            or any(type(item) is not OrderLocator for item in self.order_locators)
        ):
            _invalid()
        locator_ids = (
            tuple(item.locator.locator_id for item in self.resource_locators)
            + tuple(item.locator.locator_id for item in self.scalar_locators)
            + tuple(item.locator_id for item in self.order_locators)
        )
        if len(locator_ids) != len(set(locator_ids)):
            _invalid()
        if (
            self.claim_collection is not None
            and type(self.claim_collection) is not JsonLocator
        ):
            _invalid()
        if (self.claim_collection is None) != (self.max_claim_count == 0):
            _invalid()
        if (
            type(self.schema_version_locators) is not tuple
            or len(self.schema_version_locators) > _MAX_PROFILE_ITEMS
            or any(
                type(item) is not JsonLocator for item in self.schema_version_locators
            )
            or len({item.pointer for item in self.schema_version_locators})
            != len(self.schema_version_locators)
            or (not self.schema_version_locators) != (self.schema_version_value is None)
        ):
            _invalid()
        if self.schema_version_locators:
            _require_token(cast(str, self.schema_version_value))
        payload = _canonical_bytes(self._document())
        object.__setattr__(self, "_canonical_bytes_snapshot", payload)
        object.__setattr__(self, "profile_sha256", Sha256Digest.of(payload))

    def _document(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "task_code": self.task_code,
            "lifecycle": self.lifecycle,
            "output_schema_path": self.output_schema_path,
            "output_schema_id": self.output_schema_id,
            "output_schema_sha256": self.output_schema_sha256.value,
            "task_binding_sha256": self.task_binding_sha256.value,
            "task_sha256": self.task_sha256.value,
            "prompt_sha256": self.prompt_sha256.value,
            "route_sha256": self.route_sha256.value,
            "max_output_tokens": self.max_output_tokens,
            "max_output_bytes": self.max_output_bytes,
            "allowed_input_fields": list(self.allowed_input_fields),
            "denied_input_fields": list(self.denied_input_fields),
            "required_runtime_checks": list(self.required_runtime_checks),
            "prompt_required_runtime_checks": list(self.prompt_required_runtime_checks),
            "runtime_check_bindings": [
                {
                    "check_name": item.check_name,
                    "enforcement_refs": list(item.enforcement_refs),
                }
                for item in self.runtime_check_bindings
            ],
            "alignment_required_inputs": list(self.alignment_required_inputs),
            "alignment_required_outputs": list(self.alignment_required_outputs),
            "alignment_prohibited_outputs": list(self.alignment_prohibited_outputs),
            "required_semantic_receipts": [
                {
                    "receipt_kind": item.receipt_kind.value,
                    "owner_story_id": item.owner_story_id,
                    "owner_contract_sha256": item.owner_contract_sha256.value,
                }
                for item in self.required_semantic_receipts
            ],
            "semantic_capability_limitations": list(
                self.semantic_capability_limitations
            ),
            "resource_locators": [
                {
                    "locator_id": item.locator.locator_id,
                    "pointer": item.locator.pointer,
                    "reference_format": item.reference_format.value,
                    "resource_kind": item.resource_kind.value,
                    "membership_required": item.membership_required,
                }
                for item in self.resource_locators
            ],
            "scalar_locators": [
                {
                    "locator_id": item.locator.locator_id,
                    "pointer": item.locator.pointer,
                    "scalar_kind": item.scalar_kind.value,
                }
                for item in self.scalar_locators
            ],
            "order_locators": [
                {
                    "locator_id": item.locator_id,
                    "collection_pointer": item.collection.pointer,
                    "identity_field": item.identity_field,
                    "rank_field": item.rank_field,
                }
                for item in self.order_locators
            ],
            "claim_collection": (
                None
                if self.claim_collection is None
                else {
                    "locator_id": self.claim_collection.locator_id,
                    "pointer": self.claim_collection.pointer,
                    "max_claim_count": self.max_claim_count,
                }
            ),
            "schema_version": (
                None
                if not self.schema_version_locators
                else {
                    "locators": [
                        {"locator_id": item.locator_id, "pointer": item.pointer}
                        for item in self.schema_version_locators
                    ],
                    "value": self.schema_version_value,
                }
            ),
            "coverage_mode": self.coverage_mode.value,
        }

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes_snapshot


@dataclass(frozen=True, slots=True, repr=False)
class RecordedOutputEnvelope:
    task_code: str
    provider_mode: ProviderMode
    request_sha256: Sha256Digest
    provider_exchange_sha256: Sha256Digest
    raw_artifact_sha256: Sha256Digest
    output_bytes: bytes = field(repr=False)
    raw_output_sha256: Sha256Digest
    output_sha256: Sha256Digest | None = field(init=False)

    def __post_init__(self) -> None:
        _require_token(self.task_code)
        if type(self.provider_mode) is not ProviderMode:
            _invalid()
        for value in (
            self.request_sha256,
            self.provider_exchange_sha256,
            self.raw_artifact_sha256,
            self.raw_output_sha256,
        ):
            _require_sha(value)
        if (
            type(self.output_bytes) is not bytes
            or not self.output_bytes
            or len(self.output_bytes) > _MAX_RECORDED_OUTPUT_BYTES
            or Sha256Digest.of(self.output_bytes) != self.raw_output_sha256
            or self.provider_exchange_sha256 != self.raw_artifact_sha256
        ):
            _invalid()
        object.__setattr__(self, "output_bytes", bytes(self.output_bytes))
        canonical_sha256: Sha256Digest | None = None
        try:
            canonical = CanonicalJsonObject.from_bytes(self.output_bytes)
            if canonical.canonical_bytes() == self.output_bytes:
                canonical_sha256 = Sha256Digest.of(self.output_bytes)
        except Exception:
            canonical_sha256 = None
        object.__setattr__(self, "output_sha256", canonical_sha256)

    @classmethod
    def from_bound_provider_success(
        cls, *, task_code: str, result: ProviderSuccess
    ) -> RecordedOutputEnvelope:
        if type(result) is not ProviderSuccess:
            _invalid()
        _require_token(task_code)
        try:
            output = result.output.canonical_bytes()
            return cls(
                task_code=task_code,
                provider_mode=ProviderMode.RECORDED_SYNTHETIC_ONLY,
                request_sha256=result.request_sha256,
                provider_exchange_sha256=result.response_sha256,
                raw_artifact_sha256=result.raw_artifact.sha256,
                output_bytes=output,
                raw_output_sha256=Sha256Digest.of(output),
            )
        except AiOutputValidationError:
            raise
        except Exception:
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class CoverageEvidenceBinding:
    output_sha256: Sha256Digest
    article_version_id: UUID
    article_body_sha256: Sha256Digest
    source_packet_version_id: UUID
    source_packet_content_sha256: Sha256Digest
    complete_claim_set_sha256: Sha256Digest
    evaluation_input_sha256: Sha256Digest
    report: ClaimEvidenceCoverageReport = field(repr=False)
    binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        _require_sha(self.output_sha256)
        _require_uuid(self.article_version_id)
        _require_sha(self.article_body_sha256)
        _require_uuid(self.source_packet_version_id)
        _require_sha(self.source_packet_content_sha256)
        _require_sha(self.complete_claim_set_sha256)
        _require_sha(self.evaluation_input_sha256)
        if type(self.report) is not ClaimEvidenceCoverageReport:
            _invalid()
        try:
            self.report.require_valid()
        except Exception:
            _invalid()
        payload = _canonical_bytes(
            {
                "output_sha256": self.output_sha256.value,
                "article_version_id": str(self.article_version_id),
                "article_body_sha256": self.article_body_sha256.value,
                "source_packet_version_id": str(self.source_packet_version_id),
                "source_packet_content_sha256": self.source_packet_content_sha256.value,
                "complete_claim_set_sha256": self.complete_claim_set_sha256.value,
                "evaluation_input_sha256": self.evaluation_input_sha256.value,
                "coverage_report_sha256": self.report.report_sha256.value,
            }
        )
        object.__setattr__(self, "binding_sha256", Sha256Digest.of(payload))


@dataclass(frozen=True, slots=True, repr=False)
class AiOutputValidationInput:
    profile: TaskValidationProfile
    schema: StructuredOutputSchema
    manifest: ValidationManifest
    envelope: RecordedOutputEnvelope
    evaluated_at: datetime
    coverage: CoverageEvidenceBinding | None = None

    def __post_init__(self) -> None:
        if (
            type(self.profile) is not TaskValidationProfile
            or type(self.schema) is not StructuredOutputSchema
            or type(self.manifest) is not ValidationManifest
            or type(self.envelope) is not RecordedOutputEnvelope
        ):
            _invalid()
        object.__setattr__(self, "evaluated_at", _require_utc(self.evaluated_at))
        if (
            self.coverage is not None
            and type(self.coverage) is not CoverageEvidenceBinding
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class GateResult:
    gate_id: str
    status: GateStatus
    findings: tuple[FindingCode, ...]

    def __post_init__(self) -> None:
        if (
            self.gate_id not in GATE_IDS
            or type(self.status) is not GateStatus
            or type(self.findings) is not tuple
            or any(type(item) is not FindingCode for item in self.findings)
            or len(set(self.findings)) != len(self.findings)
            or self.findings
            != tuple(code for code in FindingCode if code in self.findings)
            or (self.status is GateStatus.PASS and self.findings)
            or (
                self.status in {GateStatus.BLOCKED, GateStatus.UNEVALUABLE}
                and not self.findings
            )
            or (self.status is GateStatus.NOT_EXECUTED and self.findings)
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class AiOutputValidationReport:
    task_id: str | None
    task_code: str | None
    profile_sha256: Sha256Digest | None
    manifest_sha256: Sha256Digest | None
    raw_output_sha256: Sha256Digest | None
    output_sha256: Sha256Digest | None
    provider_exchange_sha256: Sha256Digest | None
    coverage_binding_sha256: Sha256Digest | None
    evaluated_at: datetime
    status: LocalValidationStatus
    gates: tuple[GateResult, ...]
    findings: tuple[FindingCode, ...]
    validator_version: str
    authority: str
    approval_authorized: bool
    publication_authorized: bool
    state_mutation_authorized: bool
    persistence_authorized: bool
    provider_authorized: bool
    production_eligible: bool
    formal_tst_019: ExecutionStatus
    formal_tst_020: ExecutionStatus
    live: ExecutionStatus
    staging: ExecutionStatus
    release: ExecutionStatus
    production: ExecutionStatus
    report_sha256: Sha256Digest

    def canonical_bytes(self) -> bytes:
        return _report_bytes(self, include_hash=True)

    def require_valid(self) -> None:
        if self.task_id is not None:
            _require_task_id(self.task_id)
        if self.task_code is not None:
            _require_token(self.task_code)
        for value in (
            self.profile_sha256,
            self.manifest_sha256,
            self.raw_output_sha256,
            self.output_sha256,
            self.provider_exchange_sha256,
            self.coverage_binding_sha256,
        ):
            if value is not None:
                _require_sha(value)
        _require_utc(self.evaluated_at)
        if (
            type(self.status) is not LocalValidationStatus
            or type(self.gates) is not tuple
            or len(self.gates) != len(GATE_IDS)
            or tuple(item.gate_id for item in self.gates) != GATE_IDS
            or any(type(item) is not GateResult for item in self.gates)
            or type(self.findings) is not tuple
            or any(type(item) is not FindingCode for item in self.findings)
            or len(self.findings) > _MAX_REPORT_FINDINGS
            or len(set(self.findings)) != len(self.findings)
            or self.findings
            != tuple(code for code in FindingCode if code in self.findings)
            or self.validator_version != VALIDATOR_VERSION
            or self.authority != AUTHORITY
            or any(
                value is not False
                for value in (
                    self.approval_authorized,
                    self.publication_authorized,
                    self.state_mutation_authorized,
                    self.persistence_authorized,
                    self.provider_authorized,
                    self.production_eligible,
                )
            )
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_019,
                    self.formal_tst_020,
                    self.live,
                    self.staging,
                    self.release,
                    self.production,
                )
            )
            or type(self.report_sha256) is not Sha256Digest
        ):
            _invalid()
        gate_findings = tuple(
            code
            for code in FindingCode
            if any(code in gate.findings for gate in self.gates)
        )
        if gate_findings != self.findings:
            _invalid()
        if self.status is LocalValidationStatus.LOCAL_VALIDATED:
            if self.findings or any(
                gate.status is not GateStatus.PASS for gate in self.gates
            ):
                _invalid()
        elif self.status is LocalValidationStatus.BLOCKED:
            if not self.findings or not any(
                gate.status is GateStatus.BLOCKED for gate in self.gates
            ):
                _invalid()
        elif not self.findings or not any(
            gate.status is GateStatus.UNEVALUABLE for gate in self.gates
        ):
            _invalid()
        if (
            Sha256Digest.of(_report_bytes(self, include_hash=False))
            != self.report_sha256
        ):
            _invalid()


def _report_bytes(report: AiOutputValidationReport, *, include_hash: bool) -> bytes:
    document: dict[str, object] = {
        "report_profile": REPORT_PROFILE,
        "task_id": report.task_id,
        "task_code": report.task_code,
        "profile_sha256": None
        if report.profile_sha256 is None
        else report.profile_sha256.value,
        "manifest_sha256": None
        if report.manifest_sha256 is None
        else report.manifest_sha256.value,
        "raw_output_sha256": None
        if report.raw_output_sha256 is None
        else report.raw_output_sha256.value,
        "output_sha256": None
        if report.output_sha256 is None
        else report.output_sha256.value,
        "provider_exchange_sha256": (
            None
            if report.provider_exchange_sha256 is None
            else report.provider_exchange_sha256.value
        ),
        "coverage_binding_sha256": (
            None
            if report.coverage_binding_sha256 is None
            else report.coverage_binding_sha256.value
        ),
        "evaluated_at": report.evaluated_at.isoformat(),
        "status": report.status.value,
        "gates": [
            {
                "gate_id": gate.gate_id,
                "status": gate.status.value,
                "findings": [item.value for item in gate.findings],
            }
            for gate in report.gates
        ],
        "findings": [item.value for item in report.findings],
        "validator_version": report.validator_version,
        "authority": report.authority,
        "approval_authorized": report.approval_authorized,
        "publication_authorized": report.publication_authorized,
        "state_mutation_authorized": report.state_mutation_authorized,
        "persistence_authorized": report.persistence_authorized,
        "provider_authorized": report.provider_authorized,
        "production_eligible": report.production_eligible,
        "formal_tst_019": report.formal_tst_019.value,
        "formal_tst_020": report.formal_tst_020.value,
        "live": report.live.value,
        "staging": report.staging.value,
        "release": report.release.value,
        "production": report.production.value,
    }
    if include_hash:
        document["report_sha256"] = report.report_sha256.value
    return _canonical_bytes(document)


def _make_report(
    *,
    value: AiOutputValidationInput | None,
    evaluated_at: datetime,
    status: LocalValidationStatus,
    gates: tuple[GateResult, ...],
) -> AiOutputValidationReport:
    findings = tuple(
        code for code in FindingCode if any(code in gate.findings for gate in gates)
    )
    provisional = AiOutputValidationReport(
        task_id=None if value is None else value.profile.task_id,
        task_code=None if value is None else value.profile.task_code,
        profile_sha256=None if value is None else value.profile.profile_sha256,
        manifest_sha256=None if value is None else value.manifest.manifest_sha256,
        raw_output_sha256=(None if value is None else value.envelope.raw_output_sha256),
        output_sha256=None if value is None else value.envelope.output_sha256,
        provider_exchange_sha256=(
            None if value is None else value.envelope.provider_exchange_sha256
        ),
        coverage_binding_sha256=(
            None
            if value is None or value.coverage is None
            else value.coverage.binding_sha256
        ),
        evaluated_at=evaluated_at,
        status=status,
        gates=gates,
        findings=findings,
        validator_version=VALIDATOR_VERSION,
        authority=AUTHORITY,
        approval_authorized=False,
        publication_authorized=False,
        state_mutation_authorized=False,
        persistence_authorized=False,
        provider_authorized=False,
        production_eligible=False,
        formal_tst_019=ExecutionStatus.NOT_EXECUTED,
        formal_tst_020=ExecutionStatus.NOT_EXECUTED,
        live=ExecutionStatus.NOT_EXECUTED,
        staging=ExecutionStatus.NOT_EXECUTED,
        release=ExecutionStatus.NOT_EXECUTED,
        production=ExecutionStatus.NOT_EXECUTED,
        report_sha256=Sha256Digest("0" * 64),
    )
    digest = Sha256Digest.of(_report_bytes(provisional, include_hash=False))
    report = replace(provisional, report_sha256=digest)
    report.require_valid()
    return report


def unavailable_ai_output_validation_report(
    evaluated_at: datetime,
) -> AiOutputValidationReport:
    evaluated_at = _require_utc(evaluated_at)
    gates = (
        GateResult(
            GATE_IDS[0], GateStatus.UNEVALUABLE, (FindingCode.BINDING_UNAVAILABLE,)
        ),
    ) + tuple(
        GateResult(gate_id, GateStatus.NOT_EXECUTED, ()) for gate_id in GATE_IDS[1:]
    )
    return _make_report(
        value=None,
        evaluated_at=evaluated_at,
        status=LocalValidationStatus.UNEVALUABLE,
        gates=gates,
    )


def _binding_findings(value: AiOutputValidationInput) -> tuple[FindingCode, ...]:
    profile = value.profile
    manifest = value.manifest
    envelope = value.envelope
    schema = value.schema
    findings: set[FindingCode] = set()
    try:
        schema_digest = Sha256Digest.of(schema.document_bytes)
        profile_digest = Sha256Digest.of(profile.canonical_bytes())
        manifest_digest = Sha256Digest.of(manifest.canonical_bytes())
    except Exception:
        return (FindingCode.BINDING_UNAVAILABLE,)
    if (
        profile_digest != profile.profile_sha256
        or manifest_digest != manifest.manifest_sha256
        or schema_digest != schema.sha256
    ):
        findings.add(FindingCode.HASH_OR_VERSION_MISMATCH)
    if (
        manifest.profile_registry_sha256 != TRUSTED_PROFILE_REGISTRY_SHA256
        or TRUSTED_PROFILE_SHA256_BY_TASK.get(profile.task_id) != profile.profile_sha256
        or len(TRUSTED_PROFILE_SHA256_BY_TASK) != 12
        or manifest.task_id != profile.task_id
        or manifest.task_code != profile.task_code
        or envelope.task_code != profile.task_code
        or manifest.profile_sha256 != profile.profile_sha256
        or manifest.task_binding_sha256 != profile.task_binding_sha256
        or manifest.task_sha256 != profile.task_sha256
        or manifest.prompt_sha256 != profile.prompt_sha256
        or manifest.route_sha256 != profile.route_sha256
        or manifest.output_schema_id != profile.output_schema_id
        or manifest.output_schema_sha256 != profile.output_schema_sha256
        or schema.uri != profile.output_schema_id
        or schema.sha256 != profile.output_schema_sha256
        or manifest.expected_request_sha256 != envelope.request_sha256
        or manifest.expected_raw_output_sha256 != envelope.raw_output_sha256
        or manifest.expected_output_sha256 != envelope.output_sha256
        or envelope.provider_mode is not ProviderMode.RECORDED_SYNTHETIC_ONLY
        or envelope.provider_exchange_sha256 != envelope.raw_artifact_sha256
    ):
        findings.add(FindingCode.BINDING_MISMATCH)
    missing_inputs = set(profile.alignment_required_inputs) - set(
        manifest.input_field_names
    )
    unknown_inputs = (
        set(manifest.input_field_names)
        - set(profile.allowed_input_fields)
        - set(profile.alignment_required_inputs)
    )
    denied_inputs = set(manifest.input_field_names) & set(profile.denied_input_fields)
    expected_scalar_ids = {item.locator.locator_id for item in profile.scalar_locators}
    observed_scalar_ids = {item.locator_id for item in manifest.scalar_expectations}
    expected_order_ids = {item.locator_id for item in profile.order_locators}
    observed_order_ids = {item.locator_id for item in manifest.order_expectations}
    expected_receipts = {
        item.receipt_kind for item in profile.required_semantic_receipts
    }
    observed_receipts = {item.receipt_kind for item in manifest.semantic_receipts}
    if (
        missing_inputs
        or unknown_inputs
        or denied_inputs
        or expected_scalar_ids != observed_scalar_ids
        or expected_order_ids != observed_order_ids
        or expected_receipts != observed_receipts
    ):
        findings.add(FindingCode.BINDING_MISMATCH)
    return tuple(code for code in FindingCode if code in findings)


def _parse_output(
    value: AiOutputValidationInput,
) -> tuple[dict[str, object] | None, tuple[FindingCode, ...]]:
    try:
        canonical = CanonicalJsonObject.from_bytes(value.envelope.output_bytes)
        document = json.loads(canonical.canonical_bytes())
    except Exception:
        return None, (FindingCode.INVALID_JSON,)
    if type(document) is not dict:
        return None, (FindingCode.INVALID_JSON,)
    return cast(dict[str, object], document), ()


def _schema_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[tuple[FindingCode, ...], tuple[FindingCode, ...], bool]:
    try:
        schema_document = json.loads(value.schema.document_bytes)
        Draft202012Validator.check_schema(schema_document)
        validator = Draft202012Validator(
            schema_document,
            format_checker=FormatChecker(),
        )
        errors = tuple(
            cast(
                Iterable[object],
                validator.iter_errors(  # pyright: ignore[reportUnknownMemberType]
                    cast(Any, document)
                ),
            )
        )
    except SchemaError, ValueError, TypeError, json.JSONDecodeError:
        return (), (), False
    except Exception:
        return (), (), False
    schema = False
    unknown = False
    version_paths = {
        tuple(locator.pointer[1:].split("/"))
        for locator in value.profile.schema_version_locators
    }
    for error in errors:
        if not isinstance(error, ValidationError):
            return (), (), False
        if error.validator in {"additionalProperties", "enum"}:
            unknown = True
        elif error.validator == "const":
            error_path = tuple(str(item) for item in error.absolute_path)
            if (
                error_path in version_paths
                and error.validator_value == value.profile.schema_version_value
            ):
                # Exact declared versions are also checked at AIOV-010.
                continue
            schema = True
        else:
            schema = True
    if not _canonical_uuid_formats(schema_document, document):
        schema = True
    return (
        (FindingCode.SCHEMA_VIOLATION,) if schema else (),
        (FindingCode.UNKNOWN_PROPERTY_OR_ENUM,) if unknown else (),
        True,
    )


def _canonical_uuid_formats(schema_document: object, document: object) -> bool:
    """Apply canonical UUID syntax to every schema-declared UUID leaf."""

    if type(schema_document) is not dict:
        return False
    root = cast(dict[str, object], schema_document)
    visits = 0

    def resolve(reference: object) -> dict[str, object] | None:
        if type(reference) is not str or not reference.startswith("#/"):
            return None
        current: object = root
        for raw_token in reference[2:].split("/"):
            token = raw_token.replace("~1", "/").replace("~0", "~")
            if type(current) is not dict:
                return None
            current_map = cast(Mapping[str, object], current)
            if token not in current_map:
                return None
            current = current_map[token]
        return cast(dict[str, object], current) if type(current) is dict else None

    def walk(node: object, instance: object, depth: int) -> bool:
        nonlocal visits
        visits += 1
        instance_type = type(instance)
        if visits > _MAX_TEXT_VISITS or depth > _MAX_POINTER_DEPTH:
            return False
        if type(node) is not dict:
            return True
        schema_node = cast(dict[str, object], node)
        if "$ref" in schema_node:
            target = resolve(schema_node["$ref"])
            if target is None or not walk(target, instance, depth + 1):
                return False
        for composition in ("allOf", "anyOf", "oneOf"):
            branches = schema_node.get(composition)
            if type(branches) is list and any(
                not walk(branch, instance, depth + 1)
                for branch in cast(list[object], branches)
            ):
                return False
        if schema_node.get("format") == "uuid" and instance_type is str:
            try:
                parsed = UUID(cast(str, instance))
            except ValueError, AttributeError:
                return False
            if parsed.int == 0 or parsed.variant != RFC_4122 or str(parsed) != instance:
                return False
        properties = schema_node.get("properties")
        if instance_type is dict and type(properties) is dict:
            instance_map = cast(Mapping[str, object], instance)
            property_map = cast(Mapping[str, object], properties)
            for key, child_schema in property_map.items():
                if key in instance_map and not walk(
                    child_schema, instance_map[key], depth + 1
                ):
                    return False
        items = schema_node.get("items")
        if instance_type is list and type(items) is dict:
            item_schema = cast(Mapping[str, object], items)
            instance_items = cast(Sequence[object], instance)
            if any(not walk(item_schema, item, depth + 1) for item in instance_items):
                return False
        return True

    return walk(root, document, 0)


def _canonical_reference(
    value: object, reference_format: ReferenceFormat
) -> str | None:
    if type(value) is not str or not value or value != value.strip():
        return None
    if reference_format is ReferenceFormat.CANONICAL_UUID:
        try:
            parsed = UUID(value)
        except ValueError, AttributeError:
            return None
        if parsed.int == 0 or parsed.variant != RFC_4122 or str(parsed) != value:
            return None
    elif reference_format is ReferenceFormat.RAOS_RESOURCE_ID:
        if _RAOS_RESOURCE_ID.fullmatch(value) is None:
            return None
    elif _SAFE_TOKEN.fullmatch(value) is None:
        return None
    return value


def _resource_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    resources = {item.resource_id: item for item in value.manifest.resources}
    findings: set[FindingCode] = set()
    for locator in value.profile.resource_locators:
        for observed in locator.locator.values(document):
            reference = _canonical_reference(observed, locator.reference_format)
            if reference is None:
                findings.add(FindingCode.RESOURCE_ID_INVALID)
                continue
            binding = resources.get(reference)
            if locator.membership_required and (
                binding is None or binding.resource_kind is not locator.resource_kind
            ):
                findings.add(FindingCode.UNKNOWN_RESOURCE_ID)
    return tuple(code for code in FindingCode if code in findings)


def _coverage_state(value: AiOutputValidationInput) -> CoverageBindingState:
    coverage = value.coverage
    if coverage is None:
        return CoverageBindingState.ABSENT
    manifest = value.manifest
    report = coverage.report
    if value.envelope.output_sha256 is None or manifest.expected_output_sha256 is None:
        return CoverageBindingState.INVALID
    try:
        report.require_valid()
    except Exception:
        return CoverageBindingState.INVALID
    if (
        manifest.article_version_id is None
        or manifest.article_body_sha256 is None
        or manifest.source_packet_version_id is None
        or manifest.source_packet_content_sha256 is None
        or manifest.complete_claim_set_sha256 is None
        or manifest.coverage_evaluation_input_sha256 is None
    ):
        return CoverageBindingState.INVALID
    exact_binding = bool(
        coverage.output_sha256 == value.envelope.output_sha256
        and coverage.output_sha256 == manifest.expected_output_sha256
        and coverage.article_version_id == manifest.article_version_id
        and coverage.article_body_sha256 == manifest.article_body_sha256
        and coverage.source_packet_version_id == manifest.source_packet_version_id
        and coverage.source_packet_content_sha256
        == manifest.source_packet_content_sha256
        and coverage.complete_claim_set_sha256 == manifest.complete_claim_set_sha256
        and coverage.evaluation_input_sha256
        == manifest.coverage_evaluation_input_sha256
        and report.article_version_id is not None
        and report.article_version_id.value == coverage.article_version_id
        and report.article_body_sha256 is not None
        and report.article_body_sha256.value == coverage.article_body_sha256.value
        and report.source_packet_version_id is not None
        and report.source_packet_version_id.value == coverage.source_packet_version_id
        and report.source_packet_content_sha256 is not None
        and report.source_packet_content_sha256.value
        == coverage.source_packet_content_sha256.value
        and report.complete_claim_set_sha256 is not None
        and report.complete_claim_set_sha256.value
        == coverage.complete_claim_set_sha256.value
        and report.evaluation_input_sha256 is not None
        and report.evaluation_input_sha256.value
        == coverage.evaluation_input_sha256.value
        and report.publication_authorized is False
        and report.production_eligible is False
    )
    if not exact_binding:
        return CoverageBindingState.INVALID
    if report.status is ClaimCoverageStatus.PASS and not report.findings:
        return CoverageBindingState.PASS
    if report.status is ClaimCoverageStatus.BLOCK and report.findings:
        return CoverageBindingState.BLOCK
    return CoverageBindingState.UNEVALUABLE


def _fact_identity_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    resources = {item.resource_id: item for item in value.manifest.resources}
    findings: set[FindingCode] = set()
    for locator in value.profile.resource_locators:
        if locator.resource_kind not in {ResourceKind.FACT, ResourceKind.PRODUCT}:
            continue
        for observed in locator.locator.values(document):
            reference = _canonical_reference(observed, locator.reference_format)
            if reference is None:
                continue
            binding = resources.get(reference)
            if binding is None or binding.resource_kind is not locator.resource_kind:
                continue
            if binding.validation_status is not ResourceValidationStatus.VALID:
                findings.add(
                    FindingCode.FACT_SUPPORT_UNAVAILABLE
                    if locator.resource_kind is ResourceKind.FACT
                    else FindingCode.PRODUCT_IDENTITY_MISMATCH
                )
            if (
                locator.resource_kind is ResourceKind.FACT
                and binding.value_sha256 is None
            ):
                findings.add(FindingCode.FACT_SUPPORT_UNAVAILABLE)
            expected = binding.expected_subject_identity_sha256
            observed_identity = binding.observed_subject_identity_sha256
            if expected is not None and expected != observed_identity:
                findings.add(FindingCode.PRODUCT_IDENTITY_MISMATCH)
            if locator.resource_kind is ResourceKind.PRODUCT and expected is None:
                findings.add(FindingCode.PRODUCT_IDENTITY_MISMATCH)

    coverage_state = _coverage_state(value)
    mode = value.profile.coverage_mode
    if (
        mode is CoverageMode.REQUIRED_EXACT_ARTICLE_BINDING
        and coverage_state is CoverageBindingState.ABSENT
    ):
        findings.add(FindingCode.COVERAGE_UNAVAILABLE)
    elif coverage_state is CoverageBindingState.BLOCK:
        findings.add(FindingCode.COVERAGE_BLOCKED)
    elif coverage_state in {
        CoverageBindingState.INVALID,
        CoverageBindingState.UNEVALUABLE,
    }:
        findings.add(FindingCode.COVERAGE_UNAVAILABLE)
    if value.profile.semantic_capability_limitations:
        findings.add(FindingCode.SEMANTIC_CAPABILITY_UNAVAILABLE)
    return tuple(code for code in FindingCode if code in findings)


def _scalar_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    expectations = {
        item.locator_id: item for item in value.manifest.scalar_expectations
    }
    failed = False
    for locator in value.profile.scalar_locators:
        expected = expectations.get(locator.locator.locator_id)
        observed = locator.locator.values(document)
        if expected is None or expected.scalar_kind is not locator.scalar_kind:
            failed = True
            continue
        if not expected.matches(observed):
            failed = True
    return (FindingCode.NUMERIC_OR_SEMANTIC_MISMATCH,) if failed else ()


_AFFILIATE_INPUTS: Final = frozenset(
    {"affiliate_rate", "commission_amount", "revenue_by_product", "profit"}
)


def _order_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    expectations = {item.locator_id: item for item in value.manifest.order_expectations}
    order_failed = False
    for locator in value.profile.order_locators:
        expected = expectations.get(locator.locator_id)
        collections = locator.collection.values(document)
        if (
            expected is None
            or len(collections) != 1
            or type(collections[0]) is not list
        ):
            order_failed = True
            continue
        identities: list[str] = []
        ranks: list[int] = []
        for row in cast(list[object], collections[0]):
            if type(row) is not dict:
                order_failed = True
                break
            mapping = cast(dict[str, object], row)
            identity = mapping.get(locator.identity_field)
            rank = mapping.get(locator.rank_field)
            if type(identity) is not str or type(rank) is not int:
                order_failed = True
                break
            identities.append(identity)
            ranks.append(rank)
        if (
            tuple(identities) != expected.ordered_resource_ids
            or tuple(ranks) != expected.ordered_ranks
        ):
            order_failed = True
    findings: list[FindingCode] = []
    if order_failed:
        findings.append(FindingCode.ORDER_MISMATCH)
    if set(value.manifest.input_field_names) & _AFFILIATE_INPUTS:
        findings.append(FindingCode.AFFILIATE_BIAS)
    return tuple(code for code in FindingCode if code in findings)


_FORBIDDEN_FIELD_NAMES: Final = frozenset(
    {
        "affiliate_rate",
        "affiliate_url",
        "commission_amount",
        "disclosure_text_override",
        "freeform_html",
        "hidden_instruction",
        "json_ld",
        "live_serp_scrape",
        "manual_affiliate_url",
        "policy_override",
        "profit",
        "rakuten_review_body",
        "raw_html",
        "raw_url",
        "revenue_by_product",
        "structured_data",
        "unapproved_priority_override",
        "unapproved_web_content",
        "unpublished_article_body",
        "unverified_new_fact",
    }
)
_REVIEW_MARKERS: Final = ("[[RAKUTEN_REVIEW_BODY]]", "RAKUTEN_REVIEW_BODY")
_EXPERIENCE_MARKERS: Final = ("[[FABRICATED_FIRST_PERSON_EXPERIENCE]]",)
_INJECTION_MARKERS: Final = ("[[PROMPT_INJECTION_FOLLOWED]]",)
_STATE_MARKERS: Final = (
    "[[AI_APPROVAL]]",
    "[[AI_PUBLICATION]]",
    "[[POLICY_CLEARANCE]]",
    "[[STATE_MUTATION]]",
)
_AFFILIATE_MARKERS: Final = ("[[AFFILIATE_ECONOMICS]]",)


def _walk_json(value: object) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    keys: list[str] = []
    texts: list[str] = []
    visits = 0
    stack: list[object] = [value]
    while stack:
        visits += 1
        if visits > _MAX_TEXT_VISITS:
            return None
        item = stack.pop()
        if type(item) is dict:
            mapping = cast(dict[str, object], item)
            keys.extend(mapping)
            stack.extend(reversed(tuple(mapping.values())))
        elif type(item) is list:
            stack.extend(reversed(cast(list[object], item)))
        elif type(item) is str:
            texts.append(item)
    return tuple(keys), tuple(texts)


def _policy_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    walked = _walk_json(document)
    if walked is None:
        return (FindingCode.VALIDATOR_FAILURE,)
    keys, texts = walked
    findings: set[FindingCode] = set()
    prohibited = _FORBIDDEN_FIELD_NAMES | frozenset(
        value.profile.alignment_prohibited_outputs
    )
    if any(key in prohibited for key in keys):
        findings.add(FindingCode.FORBIDDEN_FIELD_OR_TERM)
    joined_values = texts
    if any(marker in text for text in joined_values for marker in _REVIEW_MARKERS):
        findings.add(FindingCode.REVIEW_BODY_CONTAMINATION)
    if any(marker in text for text in joined_values for marker in _EXPERIENCE_MARKERS):
        findings.add(FindingCode.FABRICATED_EXPERIENCE)
    if any(marker in text for text in joined_values for marker in _INJECTION_MARKERS):
        findings.add(FindingCode.PROMPT_INJECTION_FOLLOWED)
    if any(marker in text for text in joined_values for marker in _STATE_MARKERS):
        findings.add(FindingCode.UNAUTHORIZED_STATE_CHANGE)
    if any(marker in text for text in joined_values for marker in _AFFILIATE_MARKERS):
        findings.add(FindingCode.AFFILIATE_BIAS)
    if set(value.manifest.input_field_names) & set(value.profile.denied_input_fields):
        findings.add(FindingCode.FORBIDDEN_FIELD_OR_TERM)

    receipts = {item.receipt_kind: item for item in value.manifest.semantic_receipts}
    for requirement in value.profile.required_semantic_receipts:
        receipt = receipts.get(requirement.receipt_kind)
        if (
            receipt is None
            or receipt.owner_story_id != requirement.owner_story_id
            or receipt.owner_contract_sha256 != requirement.owner_contract_sha256
            or receipt.request_sha256 != value.envelope.request_sha256
            or receipt.raw_output_sha256 != value.envelope.raw_output_sha256
            or receipt.output_sha256 != value.envelope.output_sha256
            or receipt.input_context_sha256
            != value.manifest.expected_input_context_sha256
            or receipt.status is SemanticReceiptStatus.UNEVALUABLE
        ):
            findings.add(FindingCode.SEMANTIC_RECEIPT_UNAVAILABLE)
        elif receipt.status is SemanticReceiptStatus.BLOCKED:
            findings.add(FindingCode.SEMANTIC_RECEIPT_BLOCKED)
    return tuple(code for code in FindingCode if code in findings)


_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:bearer|basic) [A-Za-z0-9+/=_-]{16,}"),
)
_RESTRICTED_MARKERS: Final = ("[[RESTRICTED_PERSONAL_DATA]]", "[[CREDENTIAL]]")


def _secret_findings(document: Mapping[str, object]) -> tuple[FindingCode, ...]:
    walked = _walk_json(document)
    if walked is None:
        return (FindingCode.VALIDATOR_FAILURE,)
    _keys, texts = walked
    if any(
        pattern.search(text) is not None
        for text in texts
        for pattern in _SECRET_PATTERNS
    ) or any(marker in text for text in texts for marker in _RESTRICTED_MARKERS):
        return (FindingCode.SECRET_OR_RESTRICTED_DATA,)
    return ()


def _size_claim_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    findings: list[FindingCode] = []
    if len(value.envelope.output_bytes) > value.profile.max_output_bytes:
        findings.append(FindingCode.OUTPUT_TOO_LARGE)
    claim_locator = value.profile.claim_collection
    if claim_locator is not None:
        rows = claim_locator.values(document)
        if len(rows) != 1 or type(rows[0]) is not list:
            findings.append(FindingCode.CLAIM_COUNT_EXCEEDED)
        elif len(cast(list[object], rows[0])) > value.profile.max_claim_count:
            findings.append(FindingCode.CLAIM_COUNT_EXCEEDED)
    return tuple(code for code in FindingCode if code in findings)


def _hash_version_findings(
    value: AiOutputValidationInput, document: Mapping[str, object]
) -> tuple[FindingCode, ...]:
    profile = value.profile
    manifest = value.manifest
    envelope = value.envelope
    mismatch = False
    try:
        mismatch = bool(
            Sha256Digest.of(profile.canonical_bytes()) != profile.profile_sha256
            or Sha256Digest.of(manifest.canonical_bytes()) != manifest.manifest_sha256
            or Sha256Digest.of(envelope.output_bytes) != envelope.raw_output_sha256
            or envelope.output_sha256 is None
            or Sha256Digest.of(value.schema.document_bytes) != value.schema.sha256
            or envelope.provider_exchange_sha256 != envelope.raw_artifact_sha256
        )
    except Exception:
        mismatch = True
    for locator in profile.schema_version_locators:
        observed = locator.values(document)
        if observed != (profile.schema_version_value,):
            mismatch = True
    return (FindingCode.HASH_OR_VERSION_MISMATCH,) if mismatch else ()


def _gate(
    gate_id: str,
    findings: tuple[FindingCode, ...],
    *,
    unevaluable: bool = False,
) -> GateResult:
    if not findings:
        return GateResult(gate_id, GateStatus.PASS, ())
    return GateResult(
        gate_id,
        GateStatus.UNEVALUABLE if unevaluable else GateStatus.BLOCKED,
        tuple(code for code in FindingCode if code in findings),
    )


def _finish_early(
    value: AiOutputValidationInput,
    completed: Sequence[GateResult],
    *,
    unevaluable: bool,
) -> AiOutputValidationReport:
    gates = tuple(completed) + tuple(
        GateResult(gate_id, GateStatus.NOT_EXECUTED, ())
        for gate_id in GATE_IDS[len(completed) :]
    )
    return _make_report(
        value=value,
        evaluated_at=value.evaluated_at,
        status=(
            LocalValidationStatus.UNEVALUABLE
            if unevaluable
            else LocalValidationStatus.BLOCKED
        ),
        gates=gates,
    )


def evaluate_ai_output(value: AiOutputValidationInput) -> AiOutputValidationReport:
    """Evaluate one exact recorded output through AIOV-000..010 in order."""

    if type(value) is not AiOutputValidationInput:
        now = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return unavailable_ai_output_validation_report(now)

    gates: list[GateResult] = []
    binding = _binding_findings(value)
    gates.append(_gate(GATE_IDS[0], binding, unevaluable=True))
    if binding:
        return _finish_early(value, gates, unevaluable=True)

    if len(value.envelope.output_bytes) > value.profile.max_output_bytes:
        gates.extend(
            GateResult(gate_id, GateStatus.NOT_EXECUTED, ())
            for gate_id in GATE_IDS[1:9]
        )
        gates.append(_gate(GATE_IDS[9], (FindingCode.OUTPUT_TOO_LARGE,)))
        gates.append(GateResult(GATE_IDS[10], GateStatus.NOT_EXECUTED, ()))
        return _make_report(
            value=value,
            evaluated_at=value.evaluated_at,
            status=LocalValidationStatus.BLOCKED,
            gates=tuple(gates),
        )

    document, parse_findings = _parse_output(value)
    gates.append(_gate(GATE_IDS[1], parse_findings))
    if document is None:
        return _finish_early(value, gates, unevaluable=False)

    schema_findings, unknown_findings, schema_engine_available = _schema_findings(
        value, document
    )
    if not schema_engine_available:
        gates[-1] = _gate(
            GATE_IDS[1], (FindingCode.VALIDATOR_FAILURE,), unevaluable=True
        )
        return _finish_early(value, gates, unevaluable=True)
    gates[-1] = _gate(GATE_IDS[1], schema_findings)
    gates.append(_gate(GATE_IDS[2], unknown_findings))
    if schema_findings or unknown_findings:
        return _finish_early(value, gates, unevaluable=False)

    steps = (
        _resource_findings(value, document),
        _fact_identity_findings(value, document),
        _scalar_findings(value, document),
        _order_findings(value, document),
        _policy_findings(value, document),
        _secret_findings(document),
        _size_claim_findings(value, document),
        _hash_version_findings(value, document),
    )
    unevaluable_codes = {
        FindingCode.BINDING_UNAVAILABLE,
        FindingCode.COVERAGE_UNAVAILABLE,
        FindingCode.SEMANTIC_CAPABILITY_UNAVAILABLE,
        FindingCode.SEMANTIC_RECEIPT_UNAVAILABLE,
        FindingCode.VALIDATOR_FAILURE,
    }
    for gate_id, findings in zip(GATE_IDS[3:], steps, strict=True):
        gates.append(
            _gate(
                gate_id,
                findings,
                unevaluable=bool(findings)
                and all(code in unevaluable_codes for code in findings),
            )
        )

    if any(gate.status is GateStatus.BLOCKED for gate in gates):
        status = LocalValidationStatus.BLOCKED
    elif any(gate.status is GateStatus.UNEVALUABLE for gate in gates):
        status = LocalValidationStatus.UNEVALUABLE
    else:
        status = LocalValidationStatus.LOCAL_VALIDATED
    return _make_report(
        value=value,
        evaluated_at=value.evaluated_at,
        status=status,
        gates=tuple(gates),
    )


def failure_disposition(report: AiOutputValidationReport) -> FailureDisposition:
    """Project the closed ST-0706 repair boundary without executing a repair."""

    if type(report) is not AiOutputValidationReport:
        _invalid()
    report.require_valid()
    if report.status is LocalValidationStatus.LOCAL_VALIDATED:
        return FailureDisposition.NO_FAILURE
    if report.status is LocalValidationStatus.UNEVALUABLE:
        return FailureDisposition.UNEVALUABLE
    repairable = {FindingCode.INVALID_JSON, FindingCode.SCHEMA_VIOLATION}
    if (
        report.status is LocalValidationStatus.BLOCKED
        and bool(report.findings)
        and set(report.findings) <= repairable
    ):
        return FailureDisposition.ONE_REPAIR_ELIGIBLE
    return FailureDisposition.TERMINAL_BLOCK


__all__ = [
    "AiOutputValidationError",
    "AiOutputValidationInput",
    "AiOutputValidationReport",
    "CoverageEvidenceBinding",
    "CoverageMode",
    "ExecutionStatus",
    "FailureDisposition",
    "FindingCode",
    "GateResult",
    "GateStatus",
    "GATE_IDS",
    "JsonLocator",
    "LocalValidationStatus",
    "OrderExpectation",
    "OrderLocator",
    "PROFILE_REGISTRY_VERSION",
    "ProviderMode",
    "RecordedOutputEnvelope",
    "ReferenceFormat",
    "ResourceBinding",
    "ResourceKind",
    "ResourceLocator",
    "ResourceValidationStatus",
    "ScalarExpectation",
    "ScalarKind",
    "ScalarLocator",
    "SemanticReceiptBinding",
    "SemanticReceiptKind",
    "SemanticReceiptRequirement",
    "SemanticReceiptStatus",
    "TaskValidationProfile",
    "TRUSTED_PROFILE_REGISTRY_SHA256",
    "TRUSTED_PROFILE_SHA256_BY_TASK",
    "VALIDATOR_VERSION",
    "ValidationManifest",
    "canonical_validation_time",
    "evaluate_ai_output",
    "failure_disposition",
    "unavailable_ai_output_validation_report",
]
