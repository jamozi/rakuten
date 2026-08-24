"""Durable human-review-only product identity records for ST-0504 V2.

The domain consumes only an exact persisted ST-0503 V2 normalization result.
It creates deterministic candidate pairs, but it never infers identity,
similarity, rank, a category rule, or a merge/split outcome.  A human decision
is an append-only recorded fact; it does not mutate a canonical product or
make any candidate recommendation-ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast
import unicodedata
from uuid import UUID, uuid5

from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    CATALOG_IDENTITY_OPEN_DECISION_V2,
    CATALOG_NORMALIZER_VERSION_V2,
    CatalogCandidateV2,
    CatalogIdentityStatusV2,
    CatalogReadinessV2,
    PersistedCatalogNormalizationV2,
    catalog_candidate_mapping_v2,
    catalog_source_snapshot_mapping_v2,
    persisted_catalog_normalization_mapping_v2,
)


PRODUCT_IDENTITY_RUNTIME_VERSION_V2 = "ST0504_RECORDED_HUMAN_DECISION_V2"
PRODUCT_IDENTITY_OPEN_DECISION_V2 = CATALOG_IDENTITY_OPEN_DECISION_V2
PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2 = "jp.raos.catalog.identity_review_queued.v2"
PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2 = (
    "jp.raos.catalog.grouping_decision_recorded.v1"
)
PRODUCT_IDENTITY_EVENT_CHANNEL_V2 = "ingestion.events"
PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2 = "CAT-006"
PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2 = "manage_product_identity"
PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2 = "PRODUCT"
PRODUCT_IDENTITY_AUTHORIZATION_STATE_V2: None = None
PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2: tuple[str, ...] = tuple(
    sorted(
        {
            *CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2,
            "affiliate_rate",
            "commission",
            "epc",
            "profit",
            "ranking_score",
            "recommendation_score",
            "review_aggregate",
            "review_body",
            "reward",
            "rpm",
        }
    )
)
PRODUCT_IDENTITY_ZERO_HASH_V2 = "0" * 64

_MAX_VERSION = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-product-identity-runtime-v2>"
_ID_NAMESPACE = UUID("6cbb1c16-e145-5daa-b0a4-9819242f8f15")


class ProductIdentityRuntimeFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    SOURCE_INTEGRITY = "SOURCE_INTEGRITY"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    AUTHORIZATION_NOT_DURABLE = "AUTHORIZATION_NOT_DURABLE"
    AUTHORIZATION_MISMATCH = "AUTHORIZATION_MISMATCH"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    UNSAFE_PATH = "UNSAFE_PATH"
    SCHEMA_INTEGRITY = "SCHEMA_INTEGRITY"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    STATE_CONFLICT = "STATE_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class ProductIdentityReviewStatusV2(str, Enum):
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ProductIdentityReadinessV2(str, Enum):
    NOT_READY = "NOT_READY"


class ProductIdentityDecisionTypeV2(str, Enum):
    MERGE = "MERGE"
    SPLIT = "SPLIT"


class ProductIdentityCommitKindV2(str, Enum):
    REVIEW_QUEUE = "REVIEW_QUEUE"
    HUMAN_DECISION = "HUMAN_DECISION"


class ProductIdentityReplayStatusV2(str, Enum):
    DIRECT_COMMIT = "DIRECT_COMMIT"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    RECOVERED_COMMIT = "RECOVERED_COMMIT"


class ProductIdentityCommitRecoveryOutcomeV2(str, Enum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("product identity runtime serialization is unsupported")


class ProductIdentityRuntimeFailureV2(RuntimeError):
    """Closed sanitized exception with a Python-assignable traceback."""

    __slots__ = ("_code",)

    def __init__(self, code: ProductIdentityRuntimeFailureCodeV2) -> None:
        if type(code) is not ProductIdentityRuntimeFailureCodeV2:
            raise TypeError("invalid product identity runtime failure code")
        self._code = code
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> ProductIdentityRuntimeFailureCodeV2:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ProductIdentityRuntimeFailureV2(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("product identity runtime failure is non-serializable")


def fail_product_identity_runtime_v2(
    code: ProductIdentityRuntimeFailureCodeV2 = (
        ProductIdentityRuntimeFailureCodeV2.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise ProductIdentityRuntimeFailureV2(code) from None


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_product_identity_runtime_v2()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_product_identity_runtime_v2()
    return value


def _version(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= _MAX_VERSION:
        fail_product_identity_runtime_v2()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_product_identity_runtime_v2()
    return value


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("+00:00"):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    parsed = _utc(parsed)
    if _utc_text(parsed) != value:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return parsed


def _parse_uuid(value: object) -> UUID:
    if type(value) is not str:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    try:
        parsed = UUID(value)
    except ValueError, AttributeError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    if parsed.int == 0 or str(parsed) != value:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return parsed


def _text(value: object, *, maximum_bytes: int) -> str:
    if type(value) is not str or not value or value != value.strip():
        fail_product_identity_runtime_v2()
    if any(
        ord(character) == 127
        or unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        fail_product_identity_runtime_v2()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_product_identity_runtime_v2()
    if len(encoded) > maximum_bytes:
        fail_product_identity_runtime_v2()
    return value


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        fail_product_identity_runtime_v2()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    result = {cast(str, key): item for key, item in raw.items()}
    if frozenset(result) != keys:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return result


def _list(value: object) -> list[object]:
    if type(value) is not list:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return cast(list[object], value)


def _stable_uuid(kind: str, *parts: object) -> UUID:
    material = hashlib.sha256(
        _json_bytes({"kind": kind, "parts": list(parts)})
    ).hexdigest()
    return uuid5(_ID_NAMESPACE, material)


def _record_sha256(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentitySourceBindingV2(_RedactedValue):
    catalog_operation_id: UUID
    catalog_payload_fingerprint: str
    catalog_version: int
    catalog_previous_chain_hash: str
    catalog_chain_hash: str
    catalog_batch_id: UUID
    catalog_batch_sha256: str
    catalog_source_snapshot_id: UUID
    catalog_source_snapshot_sha256: str
    catalog_receipt_id: UUID
    catalog_request_fingerprint: str
    catalog_raw_sha256: str
    catalog_normalizer_version: str
    catalog_committed_at: datetime
    persisted_record_sha256: str

    def __post_init__(self) -> None:
        _uuid(self.catalog_operation_id)
        _sha256(self.catalog_payload_fingerprint)
        _version(self.catalog_version, minimum=1)
        _sha256(self.catalog_previous_chain_hash)
        _sha256(self.catalog_chain_hash)
        _uuid(self.catalog_batch_id)
        _sha256(self.catalog_batch_sha256)
        _uuid(self.catalog_source_snapshot_id)
        _sha256(self.catalog_source_snapshot_sha256)
        _uuid(self.catalog_receipt_id)
        _sha256(self.catalog_request_fingerprint)
        _sha256(self.catalog_raw_sha256)
        if self.catalog_normalizer_version != CATALOG_NORMALIZER_VERSION_V2:
            fail_product_identity_runtime_v2()
        _utc(self.catalog_committed_at)
        _sha256(self.persisted_record_sha256)

    @classmethod
    def from_persisted(
        cls, value: PersistedCatalogNormalizationV2
    ) -> ProductIdentitySourceBindingV2:
        if type(value) is not PersistedCatalogNormalizationV2:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SOURCE_MISMATCH
            )
        try:
            batch = value.batch
            snapshot = batch.source_snapshot
            if (
                batch.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
                or batch.readiness is not CatalogReadinessV2.NOT_READY
                or batch.open_decision != PRODUCT_IDENTITY_OPEN_DECISION_V2
                or batch.grouping_decisions != ()
                or batch.canonical_products != ()
                or batch.external_actions != 0
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SOURCE_MISMATCH
                )
            return cls(
                catalog_operation_id=value.operation_id,
                catalog_payload_fingerprint=value.payload_fingerprint,
                catalog_version=value.catalog_version,
                catalog_previous_chain_hash=value.previous_chain_hash,
                catalog_chain_hash=value.chain_hash,
                catalog_batch_id=batch.batch_id,
                catalog_batch_sha256=batch.sha256,
                catalog_source_snapshot_id=snapshot.snapshot_id,
                catalog_source_snapshot_sha256=_record_sha256(
                    catalog_source_snapshot_mapping_v2(snapshot)
                ),
                catalog_receipt_id=snapshot.receipt_id,
                catalog_request_fingerprint=snapshot.request_fingerprint,
                catalog_raw_sha256=snapshot.raw_sha256,
                catalog_normalizer_version=batch.normalizer_version,
                catalog_committed_at=value.committed_at,
                persisted_record_sha256=_record_sha256(
                    persisted_catalog_normalization_mapping_v2(value)
                ),
            )
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_source_binding_mapping_v2(self))


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityCandidateRefV2(_RedactedValue):
    candidate_id: UUID
    ordinal: int
    batch_id: UUID
    source_snapshot_id: UUID
    record_sha256: str
    identity_status: ProductIdentityReviewStatusV2
    readiness: ProductIdentityReadinessV2

    def __post_init__(self) -> None:
        _uuid(self.candidate_id)
        _version(self.ordinal, minimum=1)
        _uuid(self.batch_id)
        _uuid(self.source_snapshot_id)
        _sha256(self.record_sha256)
        if (
            self.identity_status is not ProductIdentityReviewStatusV2.HUMAN_REVIEW
            or self.readiness is not ProductIdentityReadinessV2.NOT_READY
        ):
            fail_product_identity_runtime_v2()

    @classmethod
    def from_candidate(
        cls,
        *,
        candidate: CatalogCandidateV2,
        source: ProductIdentitySourceBindingV2,
    ) -> ProductIdentityCandidateRefV2:
        if (
            type(candidate) is not CatalogCandidateV2
            or type(source) is not ProductIdentitySourceBindingV2
            or candidate.source_snapshot_id != source.catalog_source_snapshot_id
            or candidate.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or candidate.readiness is not CatalogReadinessV2.NOT_READY
            or candidate.recommendation_eligible is not False
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SOURCE_MISMATCH
            )
        return cls(
            candidate_id=candidate.candidate_id,
            ordinal=candidate.ordinal,
            batch_id=source.catalog_batch_id,
            source_snapshot_id=source.catalog_source_snapshot_id,
            record_sha256=_record_sha256(catalog_candidate_mapping_v2(candidate)),
            identity_status=ProductIdentityReviewStatusV2.HUMAN_REVIEW,
            readiness=ProductIdentityReadinessV2.NOT_READY,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityCandidatePairV2(_RedactedValue):
    pair_id: UUID
    ordinal: int
    left: ProductIdentityCandidateRefV2
    right: ProductIdentityCandidateRefV2
    source_binding_sha256: str
    identity_status: ProductIdentityReviewStatusV2
    readiness: ProductIdentityReadinessV2
    automatic_merge_enabled: bool
    automatic_split_enabled: bool
    rule_ids: tuple[()]
    thresholds: tuple[()]
    scores: tuple[()]
    recommendation_input: bool

    def __post_init__(self) -> None:
        _uuid(self.pair_id)
        _version(self.ordinal, minimum=1)
        if (
            type(self.left) is not ProductIdentityCandidateRefV2
            or type(self.right) is not ProductIdentityCandidateRefV2
            or self.left.ordinal >= self.right.ordinal
            or self.left.batch_id != self.right.batch_id
            or self.left.source_snapshot_id != self.right.source_snapshot_id
        ):
            fail_product_identity_runtime_v2()
        _sha256(self.source_binding_sha256)
        if (
            self.identity_status is not ProductIdentityReviewStatusV2.HUMAN_REVIEW
            or self.readiness is not ProductIdentityReadinessV2.NOT_READY
            or self.automatic_merge_enabled is not False
            or self.automatic_split_enabled is not False
            or self.rule_ids != ()
            or self.thresholds != ()
            or self.scores != ()
            or self.recommendation_input is not False
        ):
            fail_product_identity_runtime_v2()
        expected = _stable_uuid(
            "candidate_pair",
            PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
            str(self.left.batch_id),
            str(self.left.source_snapshot_id),
            self.left.record_sha256,
            self.right.record_sha256,
            self.source_binding_sha256,
        )
        if self.pair_id != expected:
            fail_product_identity_runtime_v2()

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_candidate_pair_mapping_v2(self))


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityReviewQueueV2(_RedactedValue):
    queue_id: UUID
    site_id: UUID
    runtime_version: str
    source: ProductIdentitySourceBindingV2
    pairs: tuple[ProductIdentityCandidatePairV2, ...]
    prepared_at: datetime
    identity_status: ProductIdentityReviewStatusV2
    readiness: ProductIdentityReadinessV2
    open_decision: str
    automatic_merge_enabled: bool
    automatic_split_enabled: bool
    canonical_products: tuple[()]
    recommendation_inputs: tuple[()]
    forbidden_inputs: tuple[str, ...]
    external_actions: int

    def __post_init__(self) -> None:
        _uuid(self.queue_id)
        _uuid(self.site_id)
        if (
            self.runtime_version != PRODUCT_IDENTITY_RUNTIME_VERSION_V2
            or type(self.source) is not ProductIdentitySourceBindingV2
            or type(self.pairs) is not tuple
            or any(
                type(pair) is not ProductIdentityCandidatePairV2 for pair in self.pairs
            )
        ):
            fail_product_identity_runtime_v2()
        prepared = _utc(self.prepared_at)
        if prepared < self.source.catalog_committed_at:
            fail_product_identity_runtime_v2()
        if tuple(pair.ordinal for pair in self.pairs) != tuple(
            range(1, len(self.pairs) + 1)
        ) or len({pair.pair_id for pair in self.pairs}) != len(self.pairs):
            fail_product_identity_runtime_v2()
        if any(
            pair.source_binding_sha256 != self.source.sha256
            or pair.left.batch_id != self.source.catalog_batch_id
            or pair.left.source_snapshot_id != self.source.catalog_source_snapshot_id
            for pair in self.pairs
        ):
            fail_product_identity_runtime_v2()
        if (
            self.identity_status is not ProductIdentityReviewStatusV2.HUMAN_REVIEW
            or self.readiness is not ProductIdentityReadinessV2.NOT_READY
            or self.open_decision != PRODUCT_IDENTITY_OPEN_DECISION_V2
            or self.automatic_merge_enabled is not False
            or self.automatic_split_enabled is not False
            or self.canonical_products != ()
            or self.recommendation_inputs != ()
            or self.forbidden_inputs != PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_product_identity_runtime_v2()
        expected = _stable_uuid(
            "review_queue",
            self.runtime_version,
            str(self.site_id),
            self.source.sha256,
        )
        if self.queue_id != expected:
            fail_product_identity_runtime_v2()

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_review_queue_mapping_v2(self))


@dataclass(frozen=True, slots=True, repr=False)
class PrepareProductIdentityReviewQueueCommandV2(_RedactedValue):
    operation_id: UUID
    site_id: UUID
    source: PersistedCatalogNormalizationV2
    expected_history_version: int
    prepared_at: datetime
    payload_fingerprint: str

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        _uuid(self.site_id)
        if type(self.source) is not PersistedCatalogNormalizationV2:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SOURCE_MISMATCH
            )
        binding = ProductIdentitySourceBindingV2.from_persisted(self.source)
        if self.expected_history_version != 0:
            fail_product_identity_runtime_v2()
        prepared = _utc(self.prepared_at)
        if prepared < binding.catalog_committed_at:
            fail_product_identity_runtime_v2()
        expected = _record_sha256(
            {
                "expected_history_version": 0,
                "operation_id": str(self.operation_id),
                "prepared_at": _utc_text(prepared),
                "site_id": str(self.site_id),
                "source_binding_sha256": binding.sha256,
            }
        )
        if _sha256(self.payload_fingerprint) != expected:
            fail_product_identity_runtime_v2()

    @classmethod
    def from_persisted_catalog(
        cls,
        *,
        operation_id: UUID,
        site_id: UUID,
        source: PersistedCatalogNormalizationV2,
        prepared_at: datetime,
    ) -> PrepareProductIdentityReviewQueueCommandV2:
        _uuid(operation_id)
        _uuid(site_id)
        binding = ProductIdentitySourceBindingV2.from_persisted(source)
        instant = _utc(prepared_at)
        if instant < binding.catalog_committed_at:
            fail_product_identity_runtime_v2()
        fingerprint = _record_sha256(
            {
                "expected_history_version": 0,
                "operation_id": str(operation_id),
                "prepared_at": _utc_text(instant),
                "site_id": str(site_id),
                "source_binding_sha256": binding.sha256,
            }
        )
        return cls(
            operation_id=operation_id,
            site_id=site_id,
            source=source,
            expected_history_version=0,
            prepared_at=instant,
            payload_fingerprint=fingerprint,
        )


def build_product_identity_review_queue_v2(
    command: PrepareProductIdentityReviewQueueCommandV2,
) -> ProductIdentityReviewQueueV2:
    if type(command) is not PrepareProductIdentityReviewQueueCommandV2:
        fail_product_identity_runtime_v2()
    source = ProductIdentitySourceBindingV2.from_persisted(command.source)
    refs = tuple(
        ProductIdentityCandidateRefV2.from_candidate(
            candidate=candidate,
            source=source,
        )
        for candidate in command.source.batch.candidates
    )
    raw_pairs: list[
        tuple[ProductIdentityCandidateRefV2, ProductIdentityCandidateRefV2]
    ] = []
    for left_index, left in enumerate(refs):
        for right in refs[left_index + 1 :]:
            raw_pairs.append((left, right))
    pairs = tuple(
        ProductIdentityCandidatePairV2(
            pair_id=_stable_uuid(
                "candidate_pair",
                PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
                str(left.batch_id),
                str(left.source_snapshot_id),
                left.record_sha256,
                right.record_sha256,
                source.sha256,
            ),
            ordinal=index,
            left=left,
            right=right,
            source_binding_sha256=source.sha256,
            identity_status=ProductIdentityReviewStatusV2.HUMAN_REVIEW,
            readiness=ProductIdentityReadinessV2.NOT_READY,
            automatic_merge_enabled=False,
            automatic_split_enabled=False,
            rule_ids=(),
            thresholds=(),
            scores=(),
            recommendation_input=False,
        )
        for index, (left, right) in enumerate(raw_pairs, start=1)
    )
    return ProductIdentityReviewQueueV2(
        queue_id=_stable_uuid(
            "review_queue",
            PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
            str(command.site_id),
            source.sha256,
        ),
        site_id=command.site_id,
        runtime_version=PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
        source=source,
        pairs=pairs,
        prepared_at=command.prepared_at,
        identity_status=ProductIdentityReviewStatusV2.HUMAN_REVIEW,
        readiness=ProductIdentityReadinessV2.NOT_READY,
        open_decision=PRODUCT_IDENTITY_OPEN_DECISION_V2,
        automatic_merge_enabled=False,
        automatic_split_enabled=False,
        canonical_products=(),
        recommendation_inputs=(),
        forbidden_inputs=PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2,
        external_actions=0,
    )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityAuthorizationProofV2(_RedactedValue):
    authorization_command_id: str
    authorization_command_id_fingerprint: str
    authorization_request_digest: str
    authorization_session_fingerprint: str
    authorization_audit_sequence: int
    authorization_audit_digest: str
    authorization_policy_revision: str
    authorization_policy_fingerprint: str
    authorization_entitlement_revision: str
    authorization_matched_rule_id: str
    authorization_checked_at: datetime
    operation_id: str
    action: str
    site_id: UUID
    resource_kind: str
    resource_id: UUID
    resource_state: None
    step_up_receipt_fingerprint: None

    def __post_init__(self) -> None:
        _text(self.authorization_command_id, maximum_bytes=128)
        _sha256(self.authorization_command_id_fingerprint)
        if (
            self.authorization_command_id_fingerprint
            != hashlib.sha256(self.authorization_command_id.encode("ascii")).hexdigest()
        ):
            fail_product_identity_runtime_v2()
        _sha256(self.authorization_request_digest)
        _sha256(self.authorization_session_fingerprint)
        _version(self.authorization_audit_sequence, minimum=1)
        _sha256(self.authorization_audit_digest)
        _text(self.authorization_policy_revision, maximum_bytes=128)
        _sha256(self.authorization_policy_fingerprint)
        _text(self.authorization_entitlement_revision, maximum_bytes=128)
        _text(self.authorization_matched_rule_id, maximum_bytes=128)
        _utc(self.authorization_checked_at)
        if (
            self.operation_id != PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2
            or self.action != PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2
        ):
            fail_product_identity_runtime_v2()
        _uuid(self.site_id)
        if (
            self.resource_kind != PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2
            or type(self.resource_id) is not UUID
            or self.resource_id.int == 0
            or self.resource_state is not PRODUCT_IDENTITY_AUTHORIZATION_STATE_V2
            or self.step_up_receipt_fingerprint is not None
        ):
            fail_product_identity_runtime_v2()

    @property
    def actor_fingerprint(self) -> str:
        return self.authorization_session_fingerprint

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_authorization_proof_mapping_v2(self))


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityDecisionCommandV2(_RedactedValue):
    operation_id: UUID
    queue_id: UUID
    pair_id: UUID
    decision_type: ProductIdentityDecisionTypeV2
    reason: str
    reason_sha256: str
    expected_history_version: int
    supersedes_decision_id: UUID | None
    decided_at: datetime
    authorization: ProductIdentityAuthorizationProofV2
    payload_fingerprint: str

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        _uuid(self.queue_id)
        _uuid(self.pair_id)
        if type(self.decision_type) is not ProductIdentityDecisionTypeV2:
            fail_product_identity_runtime_v2()
        reason = _text(self.reason, maximum_bytes=2_000)
        if (
            _sha256(self.reason_sha256)
            != hashlib.sha256(reason.encode("utf-8")).hexdigest()
        ):
            fail_product_identity_runtime_v2()
        version = _version(self.expected_history_version, minimum=1)
        if self.supersedes_decision_id is not None:
            _uuid(self.supersedes_decision_id)
        decided_at = _utc(self.decided_at)
        if type(self.authorization) is not ProductIdentityAuthorizationProofV2:
            fail_product_identity_runtime_v2()
        if decided_at < self.authorization.authorization_checked_at:
            fail_product_identity_runtime_v2()
        expected = _record_sha256(
            {
                "authorization_sha256": self.authorization.sha256,
                "decided_at": _utc_text(self.decided_at),
                "decision_type": self.decision_type.value,
                "expected_history_version": version,
                "operation_id": str(self.operation_id),
                "pair_id": str(self.pair_id),
                "queue_id": str(self.queue_id),
                "reason_sha256": self.reason_sha256,
                "supersedes_decision_id": (
                    None
                    if self.supersedes_decision_id is None
                    else str(self.supersedes_decision_id)
                ),
            }
        )
        if _sha256(self.payload_fingerprint) != expected:
            fail_product_identity_runtime_v2()

    @classmethod
    def create(
        cls,
        *,
        operation_id: UUID,
        queue_id: UUID,
        pair_id: UUID,
        decision_type: ProductIdentityDecisionTypeV2,
        reason: str,
        expected_history_version: int,
        supersedes_decision_id: UUID | None,
        decided_at: datetime,
        authorization: ProductIdentityAuthorizationProofV2,
    ) -> ProductIdentityDecisionCommandV2:
        _uuid(operation_id)
        _uuid(queue_id)
        _uuid(pair_id)
        if type(decision_type) is not ProductIdentityDecisionTypeV2:
            fail_product_identity_runtime_v2()
        exact_reason = _text(reason, maximum_bytes=2_000)
        version = _version(expected_history_version, minimum=1)
        if supersedes_decision_id is not None:
            _uuid(supersedes_decision_id)
        instant = _utc(decided_at)
        if type(authorization) is not ProductIdentityAuthorizationProofV2:
            fail_product_identity_runtime_v2()
        if instant < authorization.authorization_checked_at:
            fail_product_identity_runtime_v2()
        reason_sha = hashlib.sha256(exact_reason.encode("utf-8")).hexdigest()
        fingerprint = _record_sha256(
            {
                "authorization_sha256": authorization.sha256,
                "decided_at": _utc_text(instant),
                "decision_type": decision_type.value,
                "expected_history_version": version,
                "operation_id": str(operation_id),
                "pair_id": str(pair_id),
                "queue_id": str(queue_id),
                "reason_sha256": reason_sha,
                "supersedes_decision_id": (
                    None
                    if supersedes_decision_id is None
                    else str(supersedes_decision_id)
                ),
            }
        )
        return cls(
            operation_id=operation_id,
            queue_id=queue_id,
            pair_id=pair_id,
            decision_type=decision_type,
            reason=exact_reason,
            reason_sha256=reason_sha,
            expected_history_version=version,
            supersedes_decision_id=supersedes_decision_id,
            decided_at=instant,
            authorization=authorization,
            payload_fingerprint=fingerprint,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityHumanDecisionV2(_RedactedValue):
    decision_id: UUID
    queue_id: UUID
    pair: ProductIdentityCandidatePairV2
    history_version: int
    decision_type: ProductIdentityDecisionTypeV2
    reason: str
    reason_sha256: str
    actor_fingerprint: str
    authorization: ProductIdentityAuthorizationProofV2
    supersedes_decision_id: UUID | None
    decided_at: datetime
    source_binding_sha256: str
    source_batch_sha256: str
    source_snapshot_sha256: str
    identity_status: ProductIdentityReviewStatusV2
    readiness: ProductIdentityReadinessV2
    canonical_product_id: None
    grouping_applied: bool
    ranking_impact: bool
    external_actions: int

    def __post_init__(self) -> None:
        _uuid(self.decision_id)
        _uuid(self.queue_id)
        if type(self.pair) is not ProductIdentityCandidatePairV2:
            fail_product_identity_runtime_v2()
        version = _version(self.history_version, minimum=2)
        if type(self.decision_type) is not ProductIdentityDecisionTypeV2:
            fail_product_identity_runtime_v2()
        reason = _text(self.reason, maximum_bytes=2_000)
        if (
            _sha256(self.reason_sha256)
            != hashlib.sha256(reason.encode("utf-8")).hexdigest()
        ):
            fail_product_identity_runtime_v2()
        _sha256(self.actor_fingerprint)
        if (
            type(self.authorization) is not ProductIdentityAuthorizationProofV2
            or self.actor_fingerprint != self.authorization.actor_fingerprint
        ):
            fail_product_identity_runtime_v2()
        if self.supersedes_decision_id is not None:
            _uuid(self.supersedes_decision_id)
        _utc(self.decided_at)
        _sha256(self.source_binding_sha256)
        _sha256(self.source_batch_sha256)
        _sha256(self.source_snapshot_sha256)
        if (
            self.source_binding_sha256 != self.pair.source_binding_sha256
            or self.identity_status is not ProductIdentityReviewStatusV2.HUMAN_REVIEW
            or self.readiness is not ProductIdentityReadinessV2.NOT_READY
            or self.canonical_product_id is not None
            or self.grouping_applied is not False
            or self.ranking_impact is not False
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_product_identity_runtime_v2()
        expected = _stable_uuid(
            "human_decision",
            PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
            str(self.queue_id),
            str(self.pair.pair_id),
            version,
            self.decision_type.value,
            self.reason_sha256,
            self.authorization.sha256,
            None
            if self.supersedes_decision_id is None
            else str(self.supersedes_decision_id),
            _utc_text(self.decided_at),
        )
        if self.decision_id != expected:
            fail_product_identity_runtime_v2()

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_human_decision_mapping_v2(self))


def build_product_identity_human_decision_v2(
    *,
    command: ProductIdentityDecisionCommandV2,
    queue: ProductIdentityReviewQueueV2,
) -> ProductIdentityHumanDecisionV2:
    if (
        type(command) is not ProductIdentityDecisionCommandV2
        or type(queue) is not ProductIdentityReviewQueueV2
        or command.queue_id != queue.queue_id
        or command.authorization.site_id != queue.site_id
        or command.decided_at < queue.prepared_at
    ):
        fail_product_identity_runtime_v2()
    matches = tuple(pair for pair in queue.pairs if pair.pair_id == command.pair_id)
    if len(matches) != 1:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
        )
    pair = matches[0]
    history_version = command.expected_history_version + 1
    decision_id = _stable_uuid(
        "human_decision",
        PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
        str(queue.queue_id),
        str(pair.pair_id),
        history_version,
        command.decision_type.value,
        command.reason_sha256,
        command.authorization.sha256,
        None
        if command.supersedes_decision_id is None
        else str(command.supersedes_decision_id),
        _utc_text(command.decided_at),
    )
    return ProductIdentityHumanDecisionV2(
        decision_id=decision_id,
        queue_id=queue.queue_id,
        pair=pair,
        history_version=history_version,
        decision_type=command.decision_type,
        reason=command.reason,
        reason_sha256=command.reason_sha256,
        actor_fingerprint=command.authorization.actor_fingerprint,
        authorization=command.authorization,
        supersedes_decision_id=command.supersedes_decision_id,
        decided_at=command.decided_at,
        source_binding_sha256=queue.source.sha256,
        source_batch_sha256=queue.source.catalog_batch_sha256,
        source_snapshot_sha256=queue.source.catalog_source_snapshot_sha256,
        identity_status=ProductIdentityReviewStatusV2.HUMAN_REVIEW,
        readiness=ProductIdentityReadinessV2.NOT_READY,
        canonical_product_id=None,
        grouping_applied=False,
        ranking_impact=False,
        external_actions=0,
    )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityOutboxEventV2(_RedactedValue):
    event_id: UUID
    event_type: str
    channel: str
    commit_kind: ProductIdentityCommitKindV2
    queue_id: UUID
    aggregate_version: int
    pair_id: UUID | None
    decision_id: UUID | None
    decision_type: ProductIdentityDecisionTypeV2 | None
    supersedes_decision_id: UUID | None
    source_batch_id: UUID
    source_batch_sha256: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    occurred_at: datetime
    external_actions: int

    def __post_init__(self) -> None:
        _uuid(self.event_id)
        if self.channel != PRODUCT_IDENTITY_EVENT_CHANNEL_V2:
            fail_product_identity_runtime_v2()
        if type(self.commit_kind) is not ProductIdentityCommitKindV2:
            fail_product_identity_runtime_v2()
        _uuid(self.queue_id)
        version = _version(self.aggregate_version, minimum=1)
        queue_shape = self.commit_kind is ProductIdentityCommitKindV2.REVIEW_QUEUE
        if queue_shape:
            if (
                self.event_type != PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2
                or version != 1
                or self.pair_id is not None
                or self.decision_id is not None
                or self.decision_type is not None
                or self.supersedes_decision_id is not None
            ):
                fail_product_identity_runtime_v2()
        else:
            if (
                self.event_type != PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2
                or type(self.pair_id) is not UUID
                or type(self.decision_id) is not UUID
                or type(self.decision_type) is not ProductIdentityDecisionTypeV2
            ):
                fail_product_identity_runtime_v2()
            if self.supersedes_decision_id is not None:
                _uuid(self.supersedes_decision_id)
        _uuid(self.source_batch_id)
        _sha256(self.source_batch_sha256)
        _uuid(self.source_snapshot_id)
        _sha256(self.source_snapshot_sha256)
        _utc(self.occurred_at)
        if type(self.external_actions) is not int or self.external_actions != 0:
            fail_product_identity_runtime_v2()
        expected = _stable_uuid(
            "outbox_event",
            PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
            self.event_type,
            str(self.queue_id),
            version,
            None if self.pair_id is None else str(self.pair_id),
            None if self.decision_id is None else str(self.decision_id),
            self.source_batch_sha256,
            self.source_snapshot_sha256,
        )
        if self.event_id != expected:
            fail_product_identity_runtime_v2()

    @classmethod
    def from_queue(
        cls, queue: ProductIdentityReviewQueueV2
    ) -> ProductIdentityOutboxEventV2:
        if type(queue) is not ProductIdentityReviewQueueV2:
            fail_product_identity_runtime_v2()
        return cls(
            event_id=_stable_uuid(
                "outbox_event",
                PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
                PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2,
                str(queue.queue_id),
                1,
                None,
                None,
                queue.source.catalog_batch_sha256,
                queue.source.catalog_source_snapshot_sha256,
            ),
            event_type=PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2,
            channel=PRODUCT_IDENTITY_EVENT_CHANNEL_V2,
            commit_kind=ProductIdentityCommitKindV2.REVIEW_QUEUE,
            queue_id=queue.queue_id,
            aggregate_version=1,
            pair_id=None,
            decision_id=None,
            decision_type=None,
            supersedes_decision_id=None,
            source_batch_id=queue.source.catalog_batch_id,
            source_batch_sha256=queue.source.catalog_batch_sha256,
            source_snapshot_id=queue.source.catalog_source_snapshot_id,
            source_snapshot_sha256=queue.source.catalog_source_snapshot_sha256,
            occurred_at=queue.prepared_at,
            external_actions=0,
        )

    @classmethod
    def from_decision(
        cls,
        *,
        decision: ProductIdentityHumanDecisionV2,
        queue: ProductIdentityReviewQueueV2,
    ) -> ProductIdentityOutboxEventV2:
        if (
            type(decision) is not ProductIdentityHumanDecisionV2
            or type(queue) is not ProductIdentityReviewQueueV2
            or decision.queue_id != queue.queue_id
        ):
            fail_product_identity_runtime_v2()
        return cls(
            event_id=_stable_uuid(
                "outbox_event",
                PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
                PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2,
                str(queue.queue_id),
                decision.history_version,
                str(decision.pair.pair_id),
                str(decision.decision_id),
                queue.source.catalog_batch_sha256,
                queue.source.catalog_source_snapshot_sha256,
            ),
            event_type=PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2,
            channel=PRODUCT_IDENTITY_EVENT_CHANNEL_V2,
            commit_kind=ProductIdentityCommitKindV2.HUMAN_DECISION,
            queue_id=queue.queue_id,
            aggregate_version=decision.history_version,
            pair_id=decision.pair.pair_id,
            decision_id=decision.decision_id,
            decision_type=decision.decision_type,
            supersedes_decision_id=decision.supersedes_decision_id,
            source_batch_id=queue.source.catalog_batch_id,
            source_batch_sha256=queue.source.catalog_batch_sha256,
            source_snapshot_id=queue.source.catalog_source_snapshot_id,
            source_snapshot_sha256=queue.source.catalog_source_snapshot_sha256,
            occurred_at=decision.decided_at,
            external_actions=0,
        )

    @property
    def sha256(self) -> str:
        return _record_sha256(product_identity_outbox_event_mapping_v2(self))


def product_identity_chain_hash_v2(
    *,
    previous_chain_hash: str,
    commit_kind: ProductIdentityCommitKindV2,
    queue_id: UUID,
    history_version: int,
    operation_id: UUID,
    payload_sha256: str,
    event_sha256: str,
    committed_at: datetime,
) -> str:
    if type(commit_kind) is not ProductIdentityCommitKindV2:
        fail_product_identity_runtime_v2()
    return _record_sha256(
        {
            "commit_kind": commit_kind.value,
            "committed_at": _utc_text(committed_at),
            "event_sha256": _sha256(event_sha256),
            "history_version": _version(history_version, minimum=1),
            "operation_id": str(_uuid(operation_id)),
            "payload_sha256": _sha256(payload_sha256),
            "previous_chain_hash": _sha256(previous_chain_hash),
            "queue_id": str(_uuid(queue_id)),
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class PersistedProductIdentityReviewQueueV2(_RedactedValue):
    operation_id: UUID
    payload_fingerprint: str
    history_version: int
    previous_chain_hash: str
    chain_hash: str
    queue: ProductIdentityReviewQueueV2
    event: ProductIdentityOutboxEventV2
    committed_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        _sha256(self.payload_fingerprint)
        if self.history_version != 1:
            fail_product_identity_runtime_v2()
        previous = _sha256(self.previous_chain_hash)
        _sha256(self.chain_hash)
        if (
            type(self.queue) is not ProductIdentityReviewQueueV2
            or type(self.event) is not ProductIdentityOutboxEventV2
            or self.event.commit_kind is not ProductIdentityCommitKindV2.REVIEW_QUEUE
            or self.event.queue_id != self.queue.queue_id
            or self.event.aggregate_version != 1
        ):
            fail_product_identity_runtime_v2()
        committed = _utc(self.committed_at)
        if committed != self.queue.prepared_at:
            fail_product_identity_runtime_v2()
        expected = product_identity_chain_hash_v2(
            previous_chain_hash=previous,
            commit_kind=ProductIdentityCommitKindV2.REVIEW_QUEUE,
            queue_id=self.queue.queue_id,
            history_version=1,
            operation_id=self.operation_id,
            payload_sha256=self.queue.sha256,
            event_sha256=self.event.sha256,
            committed_at=committed,
        )
        if self.chain_hash != expected:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )


@dataclass(frozen=True, slots=True, repr=False)
class PersistedProductIdentityDecisionV2(_RedactedValue):
    operation_id: UUID
    payload_fingerprint: str
    history_version: int
    previous_chain_hash: str
    chain_hash: str
    decision: ProductIdentityHumanDecisionV2
    event: ProductIdentityOutboxEventV2
    committed_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        _sha256(self.payload_fingerprint)
        version = _version(self.history_version, minimum=2)
        previous = _sha256(self.previous_chain_hash)
        _sha256(self.chain_hash)
        if (
            type(self.decision) is not ProductIdentityHumanDecisionV2
            or type(self.event) is not ProductIdentityOutboxEventV2
            or self.decision.history_version != version
            or self.event.commit_kind is not ProductIdentityCommitKindV2.HUMAN_DECISION
            or self.event.queue_id != self.decision.queue_id
            or self.event.decision_id != self.decision.decision_id
            or self.event.aggregate_version != version
        ):
            fail_product_identity_runtime_v2()
        committed = _utc(self.committed_at)
        if committed != self.decision.decided_at:
            fail_product_identity_runtime_v2()
        expected = product_identity_chain_hash_v2(
            previous_chain_hash=previous,
            commit_kind=ProductIdentityCommitKindV2.HUMAN_DECISION,
            queue_id=self.decision.queue_id,
            history_version=version,
            operation_id=self.operation_id,
            payload_sha256=self.decision.sha256,
            event_sha256=self.event.sha256,
            committed_at=committed,
        )
        if self.chain_hash != expected:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityReviewQueueResultV2(_RedactedValue):
    persisted: PersistedProductIdentityReviewQueueV2
    replay_status: ProductIdentityReplayStatusV2
    external_actions: int

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedProductIdentityReviewQueueV2
            or type(self.replay_status) is not ProductIdentityReplayStatusV2
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_product_identity_runtime_v2()


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityDecisionResultV2(_RedactedValue):
    persisted: PersistedProductIdentityDecisionV2
    replay_status: ProductIdentityReplayStatusV2
    external_actions: int

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedProductIdentityDecisionV2
            or type(self.replay_status) is not ProductIdentityReplayStatusV2
            or type(self.external_actions) is not int
            or self.external_actions != 0
        ):
            fail_product_identity_runtime_v2()


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityQueueCommitRecoveryV2(_RedactedValue):
    outcome: ProductIdentityCommitRecoveryOutcomeV2
    persisted: PersistedProductIdentityReviewQueueV2 | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not ProductIdentityCommitRecoveryOutcomeV2 or (
            self.outcome is ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
        ) != (type(self.persisted) is PersistedProductIdentityReviewQueueV2):
            fail_product_identity_runtime_v2()


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityDecisionCommitRecoveryV2(_RedactedValue):
    outcome: ProductIdentityCommitRecoveryOutcomeV2
    persisted: PersistedProductIdentityDecisionV2 | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not ProductIdentityCommitRecoveryOutcomeV2 or (
            self.outcome is ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
        ) != (type(self.persisted) is PersistedProductIdentityDecisionV2):
            fail_product_identity_runtime_v2()


def product_identity_source_binding_mapping_v2(
    value: ProductIdentitySourceBindingV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentitySourceBindingV2:
        fail_product_identity_runtime_v2()
    return {
        "catalog_batch_id": str(value.catalog_batch_id),
        "catalog_batch_sha256": value.catalog_batch_sha256,
        "catalog_chain_hash": value.catalog_chain_hash,
        "catalog_committed_at": _utc_text(value.catalog_committed_at),
        "catalog_normalizer_version": value.catalog_normalizer_version,
        "catalog_operation_id": str(value.catalog_operation_id),
        "catalog_payload_fingerprint": value.catalog_payload_fingerprint,
        "catalog_previous_chain_hash": value.catalog_previous_chain_hash,
        "catalog_raw_sha256": value.catalog_raw_sha256,
        "catalog_receipt_id": str(value.catalog_receipt_id),
        "catalog_request_fingerprint": value.catalog_request_fingerprint,
        "catalog_source_snapshot_id": str(value.catalog_source_snapshot_id),
        "catalog_source_snapshot_sha256": value.catalog_source_snapshot_sha256,
        "catalog_version": value.catalog_version,
        "persisted_record_sha256": value.persisted_record_sha256,
    }


def product_identity_source_binding_from_mapping_v2(
    value: object,
) -> ProductIdentitySourceBindingV2:
    data = _mapping(
        value,
        frozenset(
            {
                "catalog_batch_id",
                "catalog_batch_sha256",
                "catalog_chain_hash",
                "catalog_committed_at",
                "catalog_normalizer_version",
                "catalog_operation_id",
                "catalog_payload_fingerprint",
                "catalog_previous_chain_hash",
                "catalog_raw_sha256",
                "catalog_receipt_id",
                "catalog_request_fingerprint",
                "catalog_source_snapshot_id",
                "catalog_source_snapshot_sha256",
                "catalog_version",
                "persisted_record_sha256",
            }
        ),
    )
    try:
        return ProductIdentitySourceBindingV2(
            catalog_operation_id=_parse_uuid(data["catalog_operation_id"]),
            catalog_payload_fingerprint=cast(str, data["catalog_payload_fingerprint"]),
            catalog_version=cast(int, data["catalog_version"]),
            catalog_previous_chain_hash=cast(str, data["catalog_previous_chain_hash"]),
            catalog_chain_hash=cast(str, data["catalog_chain_hash"]),
            catalog_batch_id=_parse_uuid(data["catalog_batch_id"]),
            catalog_batch_sha256=cast(str, data["catalog_batch_sha256"]),
            catalog_source_snapshot_id=_parse_uuid(data["catalog_source_snapshot_id"]),
            catalog_source_snapshot_sha256=cast(
                str, data["catalog_source_snapshot_sha256"]
            ),
            catalog_receipt_id=_parse_uuid(data["catalog_receipt_id"]),
            catalog_request_fingerprint=cast(str, data["catalog_request_fingerprint"]),
            catalog_raw_sha256=cast(str, data["catalog_raw_sha256"]),
            catalog_normalizer_version=cast(str, data["catalog_normalizer_version"]),
            catalog_committed_at=_parse_utc(data["catalog_committed_at"]),
            persisted_record_sha256=cast(str, data["persisted_record_sha256"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_candidate_ref_mapping_v2(
    value: ProductIdentityCandidateRefV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityCandidateRefV2:
        fail_product_identity_runtime_v2()
    return {
        "batch_id": str(value.batch_id),
        "candidate_id": str(value.candidate_id),
        "identity_status": value.identity_status.value,
        "ordinal": value.ordinal,
        "readiness": value.readiness.value,
        "record_sha256": value.record_sha256,
        "source_snapshot_id": str(value.source_snapshot_id),
    }


def product_identity_candidate_ref_from_mapping_v2(
    value: object,
) -> ProductIdentityCandidateRefV2:
    data = _mapping(
        value,
        frozenset(
            {
                "batch_id",
                "candidate_id",
                "identity_status",
                "ordinal",
                "readiness",
                "record_sha256",
                "source_snapshot_id",
            }
        ),
    )
    try:
        return ProductIdentityCandidateRefV2(
            candidate_id=_parse_uuid(data["candidate_id"]),
            ordinal=cast(int, data["ordinal"]),
            batch_id=_parse_uuid(data["batch_id"]),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            record_sha256=cast(str, data["record_sha256"]),
            identity_status=ProductIdentityReviewStatusV2(
                cast(str, data["identity_status"])
            ),
            readiness=ProductIdentityReadinessV2(cast(str, data["readiness"])),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_candidate_pair_mapping_v2(
    value: ProductIdentityCandidatePairV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityCandidatePairV2:
        fail_product_identity_runtime_v2()
    return {
        "automatic_merge_enabled": value.automatic_merge_enabled,
        "automatic_split_enabled": value.automatic_split_enabled,
        "identity_status": value.identity_status.value,
        "left": product_identity_candidate_ref_mapping_v2(value.left),
        "ordinal": value.ordinal,
        "pair_id": str(value.pair_id),
        "readiness": value.readiness.value,
        "recommendation_input": value.recommendation_input,
        "right": product_identity_candidate_ref_mapping_v2(value.right),
        "rule_ids": [],
        "scores": [],
        "source_binding_sha256": value.source_binding_sha256,
        "thresholds": [],
    }


def product_identity_candidate_pair_from_mapping_v2(
    value: object,
) -> ProductIdentityCandidatePairV2:
    data = _mapping(
        value,
        frozenset(
            {
                "automatic_merge_enabled",
                "automatic_split_enabled",
                "identity_status",
                "left",
                "ordinal",
                "pair_id",
                "readiness",
                "recommendation_input",
                "right",
                "rule_ids",
                "scores",
                "source_binding_sha256",
                "thresholds",
            }
        ),
    )
    for key in ("rule_ids", "scores", "thresholds"):
        if _list(data[key]) != []:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
    try:
        return ProductIdentityCandidatePairV2(
            pair_id=_parse_uuid(data["pair_id"]),
            ordinal=cast(int, data["ordinal"]),
            left=product_identity_candidate_ref_from_mapping_v2(data["left"]),
            right=product_identity_candidate_ref_from_mapping_v2(data["right"]),
            source_binding_sha256=cast(str, data["source_binding_sha256"]),
            identity_status=ProductIdentityReviewStatusV2(
                cast(str, data["identity_status"])
            ),
            readiness=ProductIdentityReadinessV2(cast(str, data["readiness"])),
            automatic_merge_enabled=cast(bool, data["automatic_merge_enabled"]),
            automatic_split_enabled=cast(bool, data["automatic_split_enabled"]),
            rule_ids=(),
            thresholds=(),
            scores=(),
            recommendation_input=cast(bool, data["recommendation_input"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_review_queue_mapping_v2(
    value: ProductIdentityReviewQueueV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityReviewQueueV2:
        fail_product_identity_runtime_v2()
    return {
        "automatic_merge_enabled": value.automatic_merge_enabled,
        "automatic_split_enabled": value.automatic_split_enabled,
        "canonical_products": [],
        "external_actions": value.external_actions,
        "forbidden_inputs": list(value.forbidden_inputs),
        "identity_status": value.identity_status.value,
        "open_decision": value.open_decision,
        "pairs": [
            product_identity_candidate_pair_mapping_v2(pair) for pair in value.pairs
        ],
        "prepared_at": _utc_text(value.prepared_at),
        "queue_id": str(value.queue_id),
        "readiness": value.readiness.value,
        "recommendation_inputs": [],
        "runtime_version": value.runtime_version,
        "site_id": str(value.site_id),
        "source": product_identity_source_binding_mapping_v2(value.source),
    }


def product_identity_review_queue_from_mapping_v2(
    value: object,
) -> ProductIdentityReviewQueueV2:
    data = _mapping(
        value,
        frozenset(
            {
                "automatic_merge_enabled",
                "automatic_split_enabled",
                "canonical_products",
                "external_actions",
                "forbidden_inputs",
                "identity_status",
                "open_decision",
                "pairs",
                "prepared_at",
                "queue_id",
                "readiness",
                "recommendation_inputs",
                "runtime_version",
                "site_id",
                "source",
            }
        ),
    )
    if (
        _list(data["canonical_products"]) != []
        or _list(data["recommendation_inputs"]) != []
    ):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    forbidden = _list(data["forbidden_inputs"])
    if any(type(item) is not str for item in forbidden):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    try:
        return ProductIdentityReviewQueueV2(
            queue_id=_parse_uuid(data["queue_id"]),
            site_id=_parse_uuid(data["site_id"]),
            runtime_version=cast(str, data["runtime_version"]),
            source=product_identity_source_binding_from_mapping_v2(data["source"]),
            pairs=tuple(
                product_identity_candidate_pair_from_mapping_v2(item)
                for item in _list(data["pairs"])
            ),
            prepared_at=_parse_utc(data["prepared_at"]),
            identity_status=ProductIdentityReviewStatusV2(
                cast(str, data["identity_status"])
            ),
            readiness=ProductIdentityReadinessV2(cast(str, data["readiness"])),
            open_decision=cast(str, data["open_decision"]),
            automatic_merge_enabled=cast(bool, data["automatic_merge_enabled"]),
            automatic_split_enabled=cast(bool, data["automatic_split_enabled"]),
            canonical_products=(),
            recommendation_inputs=(),
            forbidden_inputs=tuple(cast(list[str], forbidden)),
            external_actions=cast(int, data["external_actions"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_authorization_proof_mapping_v2(
    value: ProductIdentityAuthorizationProofV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityAuthorizationProofV2:
        fail_product_identity_runtime_v2()
    return {
        "action": value.action,
        "authorization_audit_digest": value.authorization_audit_digest,
        "authorization_audit_sequence": value.authorization_audit_sequence,
        "authorization_checked_at": _utc_text(value.authorization_checked_at),
        "authorization_command_id": value.authorization_command_id,
        "authorization_command_id_fingerprint": value.authorization_command_id_fingerprint,
        "authorization_entitlement_revision": value.authorization_entitlement_revision,
        "authorization_matched_rule_id": value.authorization_matched_rule_id,
        "authorization_policy_fingerprint": value.authorization_policy_fingerprint,
        "authorization_policy_revision": value.authorization_policy_revision,
        "authorization_request_digest": value.authorization_request_digest,
        "authorization_session_fingerprint": value.authorization_session_fingerprint,
        "operation_id": value.operation_id,
        "resource_id": str(value.resource_id),
        "resource_kind": value.resource_kind,
        "resource_state": None,
        "site_id": str(value.site_id),
        "step_up_receipt_fingerprint": None,
    }


def product_identity_authorization_proof_from_mapping_v2(
    value: object,
) -> ProductIdentityAuthorizationProofV2:
    data = _mapping(
        value,
        frozenset(
            {
                "action",
                "authorization_audit_digest",
                "authorization_audit_sequence",
                "authorization_checked_at",
                "authorization_command_id",
                "authorization_command_id_fingerprint",
                "authorization_entitlement_revision",
                "authorization_matched_rule_id",
                "authorization_policy_fingerprint",
                "authorization_policy_revision",
                "authorization_request_digest",
                "authorization_session_fingerprint",
                "operation_id",
                "resource_id",
                "resource_kind",
                "resource_state",
                "site_id",
                "step_up_receipt_fingerprint",
            }
        ),
    )
    try:
        return ProductIdentityAuthorizationProofV2(
            authorization_command_id=cast(str, data["authorization_command_id"]),
            authorization_command_id_fingerprint=cast(
                str, data["authorization_command_id_fingerprint"]
            ),
            authorization_request_digest=cast(
                str, data["authorization_request_digest"]
            ),
            authorization_session_fingerprint=cast(
                str, data["authorization_session_fingerprint"]
            ),
            authorization_audit_sequence=cast(
                int, data["authorization_audit_sequence"]
            ),
            authorization_audit_digest=cast(str, data["authorization_audit_digest"]),
            authorization_policy_revision=cast(
                str, data["authorization_policy_revision"]
            ),
            authorization_policy_fingerprint=cast(
                str, data["authorization_policy_fingerprint"]
            ),
            authorization_entitlement_revision=cast(
                str, data["authorization_entitlement_revision"]
            ),
            authorization_matched_rule_id=cast(
                str, data["authorization_matched_rule_id"]
            ),
            authorization_checked_at=_parse_utc(data["authorization_checked_at"]),
            operation_id=cast(str, data["operation_id"]),
            action=cast(str, data["action"]),
            site_id=_parse_uuid(data["site_id"]),
            resource_kind=cast(str, data["resource_kind"]),
            resource_id=_parse_uuid(data["resource_id"]),
            resource_state=cast(None, data["resource_state"]),
            step_up_receipt_fingerprint=cast(None, data["step_up_receipt_fingerprint"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_human_decision_mapping_v2(
    value: ProductIdentityHumanDecisionV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityHumanDecisionV2:
        fail_product_identity_runtime_v2()
    return {
        "actor_fingerprint": value.actor_fingerprint,
        "authorization": product_identity_authorization_proof_mapping_v2(
            value.authorization
        ),
        "canonical_product_id": None,
        "decided_at": _utc_text(value.decided_at),
        "decision_id": str(value.decision_id),
        "decision_type": value.decision_type.value,
        "external_actions": value.external_actions,
        "grouping_applied": value.grouping_applied,
        "history_version": value.history_version,
        "identity_status": value.identity_status.value,
        "pair": product_identity_candidate_pair_mapping_v2(value.pair),
        "queue_id": str(value.queue_id),
        "ranking_impact": value.ranking_impact,
        "readiness": value.readiness.value,
        "reason": value.reason,
        "reason_sha256": value.reason_sha256,
        "source_batch_sha256": value.source_batch_sha256,
        "source_binding_sha256": value.source_binding_sha256,
        "source_snapshot_sha256": value.source_snapshot_sha256,
        "supersedes_decision_id": (
            None
            if value.supersedes_decision_id is None
            else str(value.supersedes_decision_id)
        ),
    }


def product_identity_human_decision_from_mapping_v2(
    value: object,
) -> ProductIdentityHumanDecisionV2:
    data = _mapping(
        value,
        frozenset(
            {
                "actor_fingerprint",
                "authorization",
                "canonical_product_id",
                "decided_at",
                "decision_id",
                "decision_type",
                "external_actions",
                "grouping_applied",
                "history_version",
                "identity_status",
                "pair",
                "queue_id",
                "ranking_impact",
                "readiness",
                "reason",
                "reason_sha256",
                "source_batch_sha256",
                "source_binding_sha256",
                "source_snapshot_sha256",
                "supersedes_decision_id",
            }
        ),
    )
    raw_supersedes = data["supersedes_decision_id"]
    try:
        return ProductIdentityHumanDecisionV2(
            decision_id=_parse_uuid(data["decision_id"]),
            queue_id=_parse_uuid(data["queue_id"]),
            pair=product_identity_candidate_pair_from_mapping_v2(data["pair"]),
            history_version=cast(int, data["history_version"]),
            decision_type=ProductIdentityDecisionTypeV2(
                cast(str, data["decision_type"])
            ),
            reason=cast(str, data["reason"]),
            reason_sha256=cast(str, data["reason_sha256"]),
            actor_fingerprint=cast(str, data["actor_fingerprint"]),
            authorization=product_identity_authorization_proof_from_mapping_v2(
                data["authorization"]
            ),
            supersedes_decision_id=(
                None if raw_supersedes is None else _parse_uuid(raw_supersedes)
            ),
            decided_at=_parse_utc(data["decided_at"]),
            source_binding_sha256=cast(str, data["source_binding_sha256"]),
            source_batch_sha256=cast(str, data["source_batch_sha256"]),
            source_snapshot_sha256=cast(str, data["source_snapshot_sha256"]),
            identity_status=ProductIdentityReviewStatusV2(
                cast(str, data["identity_status"])
            ),
            readiness=ProductIdentityReadinessV2(cast(str, data["readiness"])),
            canonical_product_id=cast(None, data["canonical_product_id"]),
            grouping_applied=cast(bool, data["grouping_applied"]),
            ranking_impact=cast(bool, data["ranking_impact"]),
            external_actions=cast(int, data["external_actions"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def product_identity_outbox_event_mapping_v2(
    value: ProductIdentityOutboxEventV2,
) -> dict[str, object]:
    if type(value) is not ProductIdentityOutboxEventV2:
        fail_product_identity_runtime_v2()
    return {
        "aggregate_version": value.aggregate_version,
        "channel": value.channel,
        "commit_kind": value.commit_kind.value,
        "decision_id": None if value.decision_id is None else str(value.decision_id),
        "decision_type": (
            None if value.decision_type is None else value.decision_type.value
        ),
        "event_id": str(value.event_id),
        "event_type": value.event_type,
        "external_actions": value.external_actions,
        "occurred_at": _utc_text(value.occurred_at),
        "pair_id": None if value.pair_id is None else str(value.pair_id),
        "queue_id": str(value.queue_id),
        "source_batch_id": str(value.source_batch_id),
        "source_batch_sha256": value.source_batch_sha256,
        "source_snapshot_id": str(value.source_snapshot_id),
        "source_snapshot_sha256": value.source_snapshot_sha256,
        "supersedes_decision_id": (
            None
            if value.supersedes_decision_id is None
            else str(value.supersedes_decision_id)
        ),
    }


def product_identity_outbox_event_from_mapping_v2(
    value: object,
) -> ProductIdentityOutboxEventV2:
    data = _mapping(
        value,
        frozenset(
            {
                "aggregate_version",
                "channel",
                "commit_kind",
                "decision_id",
                "decision_type",
                "event_id",
                "event_type",
                "external_actions",
                "occurred_at",
                "pair_id",
                "queue_id",
                "source_batch_id",
                "source_batch_sha256",
                "source_snapshot_id",
                "source_snapshot_sha256",
                "supersedes_decision_id",
            }
        ),
    )
    raw_pair = data["pair_id"]
    raw_decision = data["decision_id"]
    raw_type = data["decision_type"]
    raw_supersedes = data["supersedes_decision_id"]
    try:
        return ProductIdentityOutboxEventV2(
            event_id=_parse_uuid(data["event_id"]),
            event_type=cast(str, data["event_type"]),
            channel=cast(str, data["channel"]),
            commit_kind=ProductIdentityCommitKindV2(cast(str, data["commit_kind"])),
            queue_id=_parse_uuid(data["queue_id"]),
            aggregate_version=cast(int, data["aggregate_version"]),
            pair_id=None if raw_pair is None else _parse_uuid(raw_pair),
            decision_id=(None if raw_decision is None else _parse_uuid(raw_decision)),
            decision_type=(
                None
                if raw_type is None
                else ProductIdentityDecisionTypeV2(cast(str, raw_type))
            ),
            supersedes_decision_id=(
                None if raw_supersedes is None else _parse_uuid(raw_supersedes)
            ),
            source_batch_id=_parse_uuid(data["source_batch_id"]),
            source_batch_sha256=cast(str, data["source_batch_sha256"]),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            source_snapshot_sha256=cast(str, data["source_snapshot_sha256"]),
            occurred_at=_parse_utc(data["occurred_at"]),
            external_actions=cast(int, data["external_actions"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def persisted_product_identity_review_queue_mapping_v2(
    value: PersistedProductIdentityReviewQueueV2,
) -> dict[str, object]:
    if type(value) is not PersistedProductIdentityReviewQueueV2:
        fail_product_identity_runtime_v2()
    return {
        "chain_hash": value.chain_hash,
        "committed_at": _utc_text(value.committed_at),
        "event": product_identity_outbox_event_mapping_v2(value.event),
        "history_version": value.history_version,
        "operation_id": str(value.operation_id),
        "payload_fingerprint": value.payload_fingerprint,
        "previous_chain_hash": value.previous_chain_hash,
        "queue": product_identity_review_queue_mapping_v2(value.queue),
    }


def persisted_product_identity_review_queue_from_mapping_v2(
    value: object,
) -> PersistedProductIdentityReviewQueueV2:
    data = _mapping(
        value,
        frozenset(
            {
                "chain_hash",
                "committed_at",
                "event",
                "history_version",
                "operation_id",
                "payload_fingerprint",
                "previous_chain_hash",
                "queue",
            }
        ),
    )
    try:
        return PersistedProductIdentityReviewQueueV2(
            operation_id=_parse_uuid(data["operation_id"]),
            payload_fingerprint=cast(str, data["payload_fingerprint"]),
            history_version=cast(int, data["history_version"]),
            previous_chain_hash=cast(str, data["previous_chain_hash"]),
            chain_hash=cast(str, data["chain_hash"]),
            queue=product_identity_review_queue_from_mapping_v2(data["queue"]),
            event=product_identity_outbox_event_from_mapping_v2(data["event"]),
            committed_at=_parse_utc(data["committed_at"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def persisted_product_identity_decision_mapping_v2(
    value: PersistedProductIdentityDecisionV2,
) -> dict[str, object]:
    if type(value) is not PersistedProductIdentityDecisionV2:
        fail_product_identity_runtime_v2()
    return {
        "chain_hash": value.chain_hash,
        "committed_at": _utc_text(value.committed_at),
        "decision": product_identity_human_decision_mapping_v2(value.decision),
        "event": product_identity_outbox_event_mapping_v2(value.event),
        "history_version": value.history_version,
        "operation_id": str(value.operation_id),
        "payload_fingerprint": value.payload_fingerprint,
        "previous_chain_hash": value.previous_chain_hash,
    }


def persisted_product_identity_decision_from_mapping_v2(
    value: object,
) -> PersistedProductIdentityDecisionV2:
    data = _mapping(
        value,
        frozenset(
            {
                "chain_hash",
                "committed_at",
                "decision",
                "event",
                "history_version",
                "operation_id",
                "payload_fingerprint",
                "previous_chain_hash",
            }
        ),
    )
    try:
        return PersistedProductIdentityDecisionV2(
            operation_id=_parse_uuid(data["operation_id"]),
            payload_fingerprint=cast(str, data["payload_fingerprint"]),
            history_version=cast(int, data["history_version"]),
            previous_chain_hash=cast(str, data["previous_chain_hash"]),
            chain_hash=cast(str, data["chain_hash"]),
            decision=product_identity_human_decision_from_mapping_v2(data["decision"]),
            event=product_identity_outbox_event_from_mapping_v2(data["event"]),
            committed_at=_parse_utc(data["committed_at"]),
        )
    except ValueError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


__all__ = [
    "PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2",
    "PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2",
    "PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2",
    "PRODUCT_IDENTITY_AUTHORIZATION_STATE_V2",
    "PRODUCT_IDENTITY_DECISION_EVENT_TYPE_V2",
    "PRODUCT_IDENTITY_EVENT_CHANNEL_V2",
    "PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2",
    "PRODUCT_IDENTITY_OPEN_DECISION_V2",
    "PRODUCT_IDENTITY_QUEUE_EVENT_TYPE_V2",
    "PRODUCT_IDENTITY_RUNTIME_VERSION_V2",
    "PRODUCT_IDENTITY_ZERO_HASH_V2",
    "PersistedProductIdentityDecisionV2",
    "PersistedProductIdentityReviewQueueV2",
    "PrepareProductIdentityReviewQueueCommandV2",
    "ProductIdentityAuthorizationProofV2",
    "ProductIdentityCandidatePairV2",
    "ProductIdentityCandidateRefV2",
    "ProductIdentityCommitKindV2",
    "ProductIdentityCommitRecoveryOutcomeV2",
    "ProductIdentityDecisionCommandV2",
    "ProductIdentityDecisionCommitRecoveryV2",
    "ProductIdentityDecisionResultV2",
    "ProductIdentityDecisionTypeV2",
    "ProductIdentityHumanDecisionV2",
    "ProductIdentityOutboxEventV2",
    "ProductIdentityQueueCommitRecoveryV2",
    "ProductIdentityReadinessV2",
    "ProductIdentityReplayStatusV2",
    "ProductIdentityReviewQueueResultV2",
    "ProductIdentityReviewQueueV2",
    "ProductIdentityReviewStatusV2",
    "ProductIdentityRuntimeFailureCodeV2",
    "ProductIdentityRuntimeFailureV2",
    "ProductIdentitySourceBindingV2",
    "build_product_identity_human_decision_v2",
    "build_product_identity_review_queue_v2",
    "fail_product_identity_runtime_v2",
    "persisted_product_identity_decision_from_mapping_v2",
    "persisted_product_identity_decision_mapping_v2",
    "persisted_product_identity_review_queue_from_mapping_v2",
    "persisted_product_identity_review_queue_mapping_v2",
    "product_identity_authorization_proof_from_mapping_v2",
    "product_identity_authorization_proof_mapping_v2",
    "product_identity_candidate_pair_from_mapping_v2",
    "product_identity_candidate_pair_mapping_v2",
    "product_identity_chain_hash_v2",
    "product_identity_human_decision_from_mapping_v2",
    "product_identity_human_decision_mapping_v2",
    "product_identity_outbox_event_from_mapping_v2",
    "product_identity_outbox_event_mapping_v2",
    "product_identity_review_queue_from_mapping_v2",
    "product_identity_review_queue_mapping_v2",
    "product_identity_source_binding_from_mapping_v2",
    "product_identity_source_binding_mapping_v2",
]
