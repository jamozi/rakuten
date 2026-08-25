"""Durable, identity-safe structural catalog normalization for ST-0503 V2.

Only exact persisted ST-0502 V2 archive receipts and pages can enter this
domain.  Provider strings and URLs stay untrusted data, source absence is never
converted to zero confidence, and OD-006 keeps every identity decision in
human review.  This module has no I/O, clock, provider, worker, publication, or
recommendation capability.
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
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    FORBIDDEN_RECOMMENDATION_INPUTS_V2,
    ITEM_SEARCH_API_VERSION,
    IngestionStepOutcomeV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchItemV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderTextTrustV2,
    RawArchiveReceiptV2,
    UntrustedProviderTextV2,
)


CATALOG_NORMALIZER_VERSION_V2 = "ST0503_RECORDED_STRUCTURAL_V2"
CATALOG_PROVIDER_V2 = "RAKUTEN_ICHIBA"
CATALOG_EVENT_TYPE_V2 = "jp.raos.catalog.candidates_normalized.v1"
CATALOG_EVENT_CHANNEL_V2 = "ingestion.events"
CATALOG_IDENTITY_OPEN_DECISION_V2 = "OD-006"
CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2: tuple[str, ...] = tuple(
    sorted(
        {
            *FORBIDDEN_RECOMMENDATION_INPUTS_V2,
            "affiliate_rate",
            "commission",
            "epc",
            "profit",
            "recommendation_score",
            "reward",
            "review_aggregate",
            "review_body",
            "rpm",
        }
    )
)

_MAX_VERSION = (1 << 63) - 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_LOGICAL_KEY = re.compile(r"sha256/[0-9a-f]{2}/[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-catalog-normalization-runtime-v2>"
_ID_NAMESPACE = UUID("ff521ada-3754-5f9c-9585-7a6413c2cb25")


class CatalogNormalizationRuntimeFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    SOURCE_INTEGRITY = "SOURCE_INTEGRITY"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    UNSAFE_PATH = "UNSAFE_PATH"
    SCHEMA_INTEGRITY = "SCHEMA_INTEGRITY"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    STATE_CONFLICT = "STATE_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    COMMIT_KNOWN_ROLLBACK = "COMMIT_KNOWN_ROLLBACK"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


class CatalogSourceModeV2(str, Enum):
    RECORDED_PERSISTED = "RECORDED_PERSISTED"
    DISABLED = "DISABLED"


class CatalogIdentityStatusV2(str, Enum):
    HUMAN_REVIEW = "HUMAN_REVIEW"


class CatalogReadinessV2(str, Enum):
    NOT_READY = "NOT_READY"


class CatalogConfidenceStatusV2(str, Enum):
    SOURCE_ABSENT = "SOURCE_ABSENT"


class CatalogObservationKindV2(str, Enum):
    PRICE_JPY = "PRICE_JPY"
    AVAILABILITY_PROVIDER_FLAG = "AVAILABILITY_PROVIDER_FLAG"
    POSTAGE_INCLUDED_PROVIDER_FLAG = "POSTAGE_INCLUDED_PROVIDER_FLAG"
    AFFILIATE_LINK = "AFFILIATE_LINK"


class CatalogReplayStatusV2(str, Enum):
    DIRECT_COMMIT = "DIRECT_COMMIT"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    RECOVERED_COMMIT = "RECOVERED_COMMIT"


class CatalogCommitRecoveryOutcomeV2(str, Enum):
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
        raise TypeError("catalog normalization runtime serialization is unsupported")


class CatalogNormalizationRuntimeFailure(RuntimeError):
    """Closed sanitized failure whose traceback remains assignable by Python."""

    __slots__ = ("_code",)

    def __init__(self, code: CatalogNormalizationRuntimeFailureCode) -> None:
        if type(code) is not CatalogNormalizationRuntimeFailureCode:
            raise TypeError("invalid catalog normalization runtime failure code")
        self._code = code
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> CatalogNormalizationRuntimeFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"CatalogNormalizationRuntimeFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("catalog normalization runtime failure is non-serializable")


def fail_catalog_normalization_runtime(
    code: CatalogNormalizationRuntimeFailureCode = (
        CatalogNormalizationRuntimeFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise CatalogNormalizationRuntimeFailure(code) from None


def _exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_catalog_normalization_runtime()
    return value


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_catalog_normalization_runtime()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_catalog_normalization_runtime()
    return value


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("+00:00"):
        fail_catalog_normalization_runtime()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        fail_catalog_normalization_runtime()
    parsed = _utc(parsed)
    if _utc_text(parsed) != value:
        fail_catalog_normalization_runtime()
    return parsed


def _parse_uuid(value: object) -> UUID:
    if type(value) is not str:
        fail_catalog_normalization_runtime()
    try:
        parsed = UUID(value)
    except ValueError:
        fail_catalog_normalization_runtime()
    if parsed.int == 0 or str(parsed) != value:
        fail_catalog_normalization_runtime()
    return parsed


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_catalog_normalization_runtime()
    return value


def _text(value: object, *, maximum_bytes: int) -> str:
    if type(value) is not str or not value or value != value.strip():
        fail_catalog_normalization_runtime()
    if any(
        ord(character) == 127
        or unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        fail_catalog_normalization_runtime()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_catalog_normalization_runtime()
    if len(encoded) > maximum_bytes:
        fail_catalog_normalization_runtime()
    return value


def _safe_url(value: object) -> str:
    text = _text(value, maximum_bytes=2048)
    if "\\" in text or any(character.isspace() for character in text):
        fail_catalog_normalization_runtime()
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        fail_catalog_normalization_runtime()
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        fail_catalog_normalization_runtime()
    return text


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
        fail_catalog_normalization_runtime()


def _stable_uuid(kind: str, *parts: object) -> UUID:
    material = _json_bytes({"kind": kind, "parts": list(parts)})
    return uuid5(_ID_NAMESPACE, hashlib.sha256(material).hexdigest())


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    result = {cast(str, key): item for key, item in raw.items()}
    if frozenset(result) != keys:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return result


@dataclass(frozen=True, slots=True, repr=False)
class CatalogUntrustedTextV2(_RedactedValue):
    value: str
    trust: ProviderTextTrustV2

    def __post_init__(self) -> None:
        _text(self.value, maximum_bytes=10_000)
        if self.trust is not ProviderTextTrustV2.UNTRUSTED_DATA:
            fail_catalog_normalization_runtime()

    @classmethod
    def from_provider(cls, value: UntrustedProviderTextV2) -> CatalogUntrustedTextV2:
        if type(value) is not UntrustedProviderTextV2:
            fail_catalog_normalization_runtime()
        return cls(value=value.value, trust=ProviderTextTrustV2.UNTRUSTED_DATA)


@dataclass(frozen=True, slots=True, repr=False)
class CatalogUntrustedUrlV2(_RedactedValue):
    value: str
    trust: ProviderTextTrustV2

    def __post_init__(self) -> None:
        _safe_url(self.value)
        if self.trust is not ProviderTextTrustV2.UNTRUSTED_DATA:
            fail_catalog_normalization_runtime()

    @classmethod
    def from_provider(cls, value: str) -> CatalogUntrustedUrlV2:
        return cls(
            value=_safe_url(value),
            trust=ProviderTextTrustV2.UNTRUSTED_DATA,
        )


def _successful_source_step(
    source_step: object,
    source_request: object,
) -> tuple[PersistedItemSearchStepV2, ItemSearchWireRequestV2, RawArchiveReceiptV2]:
    if (
        type(source_step) is not PersistedItemSearchStepV2
        or type(source_request) is not ItemSearchWireRequestV2
        or source_step.outcome
        not in {
            IngestionStepOutcomeV2.PAGE_ARCHIVED,
            IngestionStepOutcomeV2.COMPLETED,
            IngestionStepOutcomeV2.COMPLETED_BOUNDED,
        }
        or source_step.failure_class is not None
        or type(source_step.receipt) is not RawArchiveReceiptV2
        or source_step.request_fingerprint != source_request.request_fingerprint
        or source_step.session.plan.fingerprint != source_request.plan_fingerprint
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
        )
    receipt = source_step.receipt
    if (
        receipt.request_fingerprint != source_request.request_fingerprint
        or receipt.page != source_request.page
        or receipt.observed_at != source_step.session.updated_at
        or receipt.request_fingerprint
        not in source_step.session.seen_request_fingerprints
        or receipt.artifact_sha256 not in source_step.session.seen_response_sha256
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_MISMATCH
        )
    return source_step, source_request, receipt


def _source_binding_mapping(
    *,
    source_step: PersistedItemSearchStepV2,
    source_request: ItemSearchWireRequestV2,
    receipt: RawArchiveReceiptV2,
    expected_catalog_version: int,
    normalized_at: datetime,
    normalizer_version: str,
) -> dict[str, object]:
    return {
        "api_version": ITEM_SEARCH_API_VERSION,
        "artifact_sha256": receipt.artifact_sha256,
        "artifact_version": receipt.artifact_version,
        "byte_size": receipt.byte_size,
        "expected_catalog_version": expected_catalog_version,
        "logical_key": receipt.logical_key,
        "normalized_at": _utc_text(normalized_at),
        "normalizer_version": normalizer_version,
        "observed_at": _utc_text(receipt.observed_at),
        "page": receipt.page,
        "plan_fingerprint": source_request.plan_fingerprint,
        "provider": CATALOG_PROVIDER_V2,
        "receipt_id": str(receipt.receipt_id),
        "request_fingerprint": source_request.request_fingerprint,
        "session_id": str(source_step.session.session_id),
        "source_session_version": source_step.session.version,
    }


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationCommandV2(_RedactedValue):
    operation_id: UUID
    source_step: PersistedItemSearchStepV2
    source_request: ItemSearchWireRequestV2
    expected_catalog_version: int
    normalized_at: datetime
    normalizer_version: str
    source_binding_sha256: str
    payload_fingerprint: str

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        source_step, source_request, receipt = _successful_source_step(
            self.source_step,
            self.source_request,
        )
        version = _exact_int(
            self.expected_catalog_version,
            minimum=0,
            maximum=_MAX_VERSION - 1,
        )
        normalized_at = _utc(self.normalized_at)
        if (
            normalized_at < receipt.observed_at
            or self.normalizer_version != CATALOG_NORMALIZER_VERSION_V2
        ):
            fail_catalog_normalization_runtime()
        binding = _source_binding_mapping(
            source_step=source_step,
            source_request=source_request,
            receipt=receipt,
            expected_catalog_version=version,
            normalized_at=normalized_at,
            normalizer_version=self.normalizer_version,
        )
        expected_binding = hashlib.sha256(_json_bytes(binding)).hexdigest()
        expected_payload = hashlib.sha256(
            _json_bytes(
                {
                    "operation_id": str(self.operation_id),
                    "source_binding_sha256": expected_binding,
                }
            )
        ).hexdigest()
        if (
            _sha256(self.source_binding_sha256) != expected_binding
            or _sha256(self.payload_fingerprint) != expected_payload
        ):
            fail_catalog_normalization_runtime()

    @classmethod
    def from_persisted_page(
        cls,
        *,
        operation_id: UUID,
        source_step: PersistedItemSearchStepV2,
        source_request: ItemSearchWireRequestV2,
        expected_catalog_version: int,
        normalized_at: datetime,
    ) -> CatalogNormalizationCommandV2:
        source_step, source_request, receipt = _successful_source_step(
            source_step,
            source_request,
        )
        _uuid(operation_id)
        version = _exact_int(
            expected_catalog_version,
            minimum=0,
            maximum=_MAX_VERSION - 1,
        )
        instant = _utc(normalized_at)
        if instant < receipt.observed_at:
            fail_catalog_normalization_runtime()
        binding = _source_binding_mapping(
            source_step=source_step,
            source_request=source_request,
            receipt=receipt,
            expected_catalog_version=version,
            normalized_at=instant,
            normalizer_version=CATALOG_NORMALIZER_VERSION_V2,
        )
        binding_sha256 = hashlib.sha256(_json_bytes(binding)).hexdigest()
        payload_fingerprint = hashlib.sha256(
            _json_bytes(
                {
                    "operation_id": str(operation_id),
                    "source_binding_sha256": binding_sha256,
                }
            )
        ).hexdigest()
        return cls(
            operation_id=operation_id,
            source_step=source_step,
            source_request=source_request,
            expected_catalog_version=version,
            normalized_at=instant,
            normalizer_version=CATALOG_NORMALIZER_VERSION_V2,
            source_binding_sha256=binding_sha256,
            payload_fingerprint=payload_fingerprint,
        )


@dataclass(frozen=True, slots=True, repr=False)
class CatalogSourceSnapshotV2(_RedactedValue):
    snapshot_id: UUID
    provider: str
    api_version: str
    source_mode: CatalogSourceModeV2
    source_session_id: UUID
    source_session_version: int
    receipt_id: UUID
    request_fingerprint: str
    raw_sha256: str
    raw_byte_size: int
    artifact_version: int
    logical_key: str
    page: int
    observed_at: datetime
    normalized_at: datetime
    normalizer_version: str
    confidence: None
    confidence_status: CatalogConfidenceStatusV2

    def __post_init__(self) -> None:
        _uuid(self.snapshot_id)
        _uuid(self.source_session_id)
        _uuid(self.receipt_id)
        if (
            self.provider != CATALOG_PROVIDER_V2
            or self.api_version != ITEM_SEARCH_API_VERSION
            or self.source_mode is not CatalogSourceModeV2.RECORDED_PERSISTED
            or self.normalizer_version != CATALOG_NORMALIZER_VERSION_V2
            or self.confidence is not None
            or self.confidence_status is not CatalogConfidenceStatusV2.SOURCE_ABSENT
        ):
            fail_catalog_normalization_runtime()
        _exact_int(self.source_session_version, minimum=1, maximum=_MAX_VERSION)
        _sha256(self.request_fingerprint)
        digest = _sha256(self.raw_sha256)
        _exact_int(self.raw_byte_size, minimum=2, maximum=2 * 1024 * 1024)
        _exact_int(self.artifact_version, minimum=1, maximum=_MAX_VERSION)
        if (
            type(self.logical_key) is not str
            or _LOGICAL_KEY.fullmatch(self.logical_key) is None
            or self.logical_key != f"sha256/{digest[:2]}/{digest}"
        ):
            fail_catalog_normalization_runtime()
        _exact_int(self.page, minimum=1, maximum=100)
        observed = _utc(self.observed_at)
        if _utc(self.normalized_at) < observed:
            fail_catalog_normalization_runtime()
        expected = _stable_uuid(
            "source_snapshot",
            self.provider,
            self.api_version,
            self.normalizer_version,
            str(self.source_session_id),
            self.source_session_version,
            str(self.receipt_id),
            self.request_fingerprint,
            self.raw_sha256,
            self.raw_byte_size,
            self.artifact_version,
            self.logical_key,
            self.page,
            _utc_text(self.observed_at),
        )
        if self.snapshot_id != expected:
            fail_catalog_normalization_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogCandidateV2(_RedactedValue):
    candidate_id: UUID
    ordinal: int
    provider: str
    api_version: str
    external_item_code: CatalogUntrustedTextV2
    external_shop_code: CatalogUntrustedTextV2
    shop_id: UUID
    item_name: CatalogUntrustedTextV2
    catchcopy: CatalogUntrustedTextV2 | None
    item_caption: CatalogUntrustedTextV2 | None
    shop_name: CatalogUntrustedTextV2 | None
    genre_id: int
    image_urls: tuple[CatalogUntrustedUrlV2, ...]
    source_snapshot_id: UUID
    observed_at: datetime
    identity_status: CatalogIdentityStatusV2
    readiness: CatalogReadinessV2
    canonical_product_id: None
    model_number_candidate: None
    jan_code_candidate: None
    identity_confidence: None
    recommendation_eligible: bool

    def __post_init__(self) -> None:
        _uuid(self.candidate_id)
        _exact_int(self.ordinal, minimum=1, maximum=30)
        if (
            self.provider != CATALOG_PROVIDER_V2
            or self.api_version != ITEM_SEARCH_API_VERSION
            or type(self.external_item_code) is not CatalogUntrustedTextV2
            or type(self.external_shop_code) is not CatalogUntrustedTextV2
            or type(self.item_name) is not CatalogUntrustedTextV2
            or self.external_item_code.value.partition(":")[0]
            != self.external_shop_code.value
            or ":" not in self.external_item_code.value
        ):
            fail_catalog_normalization_runtime()
        for value in (self.catchcopy, self.item_caption, self.shop_name):
            if value is not None and type(value) is not CatalogUntrustedTextV2:
                fail_catalog_normalization_runtime()
        _uuid(self.shop_id)
        _exact_int(self.genre_id, minimum=0, maximum=_MAX_VERSION)
        if (
            type(self.image_urls) is not tuple
            or len(self.image_urls) > 6
            or any(
                type(value) is not CatalogUntrustedUrlV2 for value in self.image_urls
            )
            or len({value.value for value in self.image_urls}) != len(self.image_urls)
        ):
            fail_catalog_normalization_runtime()
        _uuid(self.source_snapshot_id)
        _utc(self.observed_at)
        if (
            self.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or self.readiness is not CatalogReadinessV2.NOT_READY
            or self.canonical_product_id is not None
            or self.model_number_candidate is not None
            or self.jan_code_candidate is not None
            or self.identity_confidence is not None
            or self.recommendation_eligible is not False
        ):
            fail_catalog_normalization_runtime()
        expected = _stable_uuid(
            "candidate",
            self.provider,
            self.api_version,
            CATALOG_NORMALIZER_VERSION_V2,
            self.external_item_code.value,
            self.external_shop_code.value,
            str(self.shop_id),
            str(self.source_snapshot_id),
            self.ordinal,
        )
        if self.candidate_id != expected:
            fail_catalog_normalization_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogOfferV2(_RedactedValue):
    offer_id: UUID
    ordinal: int
    provider: str
    api_version: str
    external_offer_id: CatalogUntrustedTextV2
    candidate_id: UUID
    shop_id: UUID
    item_url: CatalogUntrustedUrlV2
    source_snapshot_id: UUID
    observed_at: datetime
    canonical_product_id: None
    identity_status: CatalogIdentityStatusV2
    readiness: CatalogReadinessV2
    recommendation_eligible: bool

    def __post_init__(self) -> None:
        _uuid(self.offer_id)
        _exact_int(self.ordinal, minimum=1, maximum=30)
        if (
            self.provider != CATALOG_PROVIDER_V2
            or self.api_version != ITEM_SEARCH_API_VERSION
            or type(self.external_offer_id) is not CatalogUntrustedTextV2
            or type(self.item_url) is not CatalogUntrustedUrlV2
        ):
            fail_catalog_normalization_runtime()
        _uuid(self.candidate_id)
        _uuid(self.shop_id)
        _uuid(self.source_snapshot_id)
        _utc(self.observed_at)
        if (
            self.canonical_product_id is not None
            or self.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or self.readiness is not CatalogReadinessV2.NOT_READY
            or self.recommendation_eligible is not False
        ):
            fail_catalog_normalization_runtime()
        expected = _stable_uuid(
            "offer",
            self.provider,
            self.api_version,
            CATALOG_NORMALIZER_VERSION_V2,
            self.external_offer_id.value,
            str(self.candidate_id),
            str(self.shop_id),
            self.item_url.value,
            str(self.source_snapshot_id),
            self.ordinal,
        )
        if self.offer_id != expected:
            fail_catalog_normalization_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogObservationV2(_RedactedValue):
    observation_id: UUID
    ordinal: int
    offer_id: UUID
    kind: CatalogObservationKindV2
    integer_value: int | None
    boolean_value: bool | None
    url_value: CatalogUntrustedUrlV2 | None
    unit_code: str | None
    observed_at: datetime
    normalized_at: datetime
    source_snapshot_id: UUID
    confidence: None
    confidence_status: CatalogConfidenceStatusV2
    recommendation_input: bool

    def __post_init__(self) -> None:
        _uuid(self.observation_id)
        _exact_int(self.ordinal, minimum=1, maximum=120)
        _uuid(self.offer_id)
        if type(self.kind) is not CatalogObservationKindV2:
            fail_catalog_normalization_runtime()
        expected_shape = {
            CatalogObservationKindV2.PRICE_JPY: (
                type(self.integer_value) is int and self.integer_value >= 0,
                self.boolean_value is None,
                self.url_value is None,
                self.unit_code == "JPY",
            ),
            CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG: (
                self.integer_value is None,
                type(self.boolean_value) is bool,
                self.url_value is None,
                self.unit_code is None,
            ),
            CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG: (
                self.integer_value is None,
                type(self.boolean_value) is bool,
                self.url_value is None,
                self.unit_code is None,
            ),
            CatalogObservationKindV2.AFFILIATE_LINK: (
                self.integer_value is None,
                self.boolean_value is None,
                type(self.url_value) is CatalogUntrustedUrlV2,
                self.unit_code is None,
            ),
        }[self.kind]
        if not all(expected_shape):
            fail_catalog_normalization_runtime()
        observed = _utc(self.observed_at)
        if _utc(self.normalized_at) < observed:
            fail_catalog_normalization_runtime()
        _uuid(self.source_snapshot_id)
        if (
            self.confidence is not None
            or self.confidence_status is not CatalogConfidenceStatusV2.SOURCE_ABSENT
            or self.recommendation_input is not False
        ):
            fail_catalog_normalization_runtime()
        value_material: object = (
            self.integer_value
            if self.integer_value is not None
            else self.boolean_value
            if self.boolean_value is not None
            else cast(CatalogUntrustedUrlV2, self.url_value).value
        )
        expected = _stable_uuid(
            "observation",
            CATALOG_NORMALIZER_VERSION_V2,
            str(self.offer_id),
            self.kind.value,
            value_material,
            self.unit_code,
            str(self.source_snapshot_id),
            self.ordinal,
        )
        if self.observation_id != expected:
            fail_catalog_normalization_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationBatchV2(_RedactedValue):
    batch_id: UUID
    operation_id: UUID
    command_fingerprint: str
    expected_catalog_version: int
    normalizer_version: str
    source_snapshot: CatalogSourceSnapshotV2
    candidates: tuple[CatalogCandidateV2, ...]
    offers: tuple[CatalogOfferV2, ...]
    observations: tuple[CatalogObservationV2, ...]
    identity_status: CatalogIdentityStatusV2
    readiness: CatalogReadinessV2
    open_decision: str
    canonical_products: tuple[()]
    grouping_decisions: tuple[()]
    provider_derived_recommendation_inputs: tuple[()]
    forbidden_recommendation_inputs: tuple[str, ...]
    external_actions: int

    def __post_init__(self) -> None:
        _uuid(self.batch_id)
        _uuid(self.operation_id)
        _sha256(self.command_fingerprint)
        _exact_int(self.expected_catalog_version, minimum=0, maximum=_MAX_VERSION - 1)
        if (
            self.normalizer_version != CATALOG_NORMALIZER_VERSION_V2
            or type(self.source_snapshot) is not CatalogSourceSnapshotV2
            or type(self.candidates) is not tuple
            or any(type(value) is not CatalogCandidateV2 for value in self.candidates)
            or type(self.offers) is not tuple
            or any(type(value) is not CatalogOfferV2 for value in self.offers)
            or type(self.observations) is not tuple
            or any(
                type(value) is not CatalogObservationV2 for value in self.observations
            )
        ):
            fail_catalog_normalization_runtime()
        if (
            len(self.candidates) != len(self.offers)
            or tuple(value.ordinal for value in self.candidates)
            != tuple(range(1, len(self.candidates) + 1))
            or tuple(value.ordinal for value in self.offers)
            != tuple(range(1, len(self.offers) + 1))
            or tuple(value.ordinal for value in self.observations)
            != tuple(range(1, len(self.observations) + 1))
            or len({value.candidate_id for value in self.candidates})
            != len(self.candidates)
            or len({value.offer_id for value in self.offers}) != len(self.offers)
            or len({value.observation_id for value in self.observations})
            != len(self.observations)
        ):
            fail_catalog_normalization_runtime()
        candidate_by_ordinal = {value.ordinal: value for value in self.candidates}
        offer_ids = {value.offer_id for value in self.offers}
        for offer in self.offers:
            candidate = candidate_by_ordinal.get(offer.ordinal)
            if (
                candidate is None
                or offer.candidate_id != candidate.candidate_id
                or offer.shop_id != candidate.shop_id
                or offer.source_snapshot_id != self.source_snapshot.snapshot_id
            ):
                fail_catalog_normalization_runtime()
        if any(
            value.offer_id not in offer_ids
            or value.source_snapshot_id != self.source_snapshot.snapshot_id
            for value in self.observations
        ):
            fail_catalog_normalization_runtime()
        if any(
            value.source_snapshot_id != self.source_snapshot.snapshot_id
            or value.observed_at != self.source_snapshot.observed_at
            for value in self.candidates
        ) or any(
            value.source_snapshot_id != self.source_snapshot.snapshot_id
            or value.observed_at != self.source_snapshot.observed_at
            for value in self.offers
        ):
            fail_catalog_normalization_runtime()
        if (
            self.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or self.readiness is not CatalogReadinessV2.NOT_READY
            or self.open_decision != CATALOG_IDENTITY_OPEN_DECISION_V2
            or self.canonical_products != ()
            or self.grouping_decisions != ()
            or self.provider_derived_recommendation_inputs != ()
            or self.forbidden_recommendation_inputs
            != CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2
            or self.external_actions != 0
        ):
            fail_catalog_normalization_runtime()
        expected = _stable_uuid(
            "batch",
            self.normalizer_version,
            str(self.source_snapshot.snapshot_id),
            self.command_fingerprint,
        )
        if self.batch_id != expected:
            fail_catalog_normalization_runtime()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            _json_bytes(catalog_normalization_batch_mapping_v2(self))
        ).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizedOutboxEventV2(_RedactedValue):
    event_id: UUID
    event_type: str
    channel: str
    aggregate_id: UUID
    aggregate_version: int
    batch_id: UUID
    source_snapshot_id: UUID
    candidate_count: int
    offer_count: int
    observation_count: int
    occurred_at: datetime
    identity_status: CatalogIdentityStatusV2
    readiness: CatalogReadinessV2
    external_actions: int

    def __post_init__(self) -> None:
        _uuid(self.event_id)
        if (
            self.event_type != CATALOG_EVENT_TYPE_V2
            or self.channel != CATALOG_EVENT_CHANNEL_V2
        ):
            fail_catalog_normalization_runtime()
        _uuid(self.aggregate_id)
        _exact_int(self.aggregate_version, minimum=1, maximum=_MAX_VERSION)
        _uuid(self.batch_id)
        _uuid(self.source_snapshot_id)
        for value in (
            self.candidate_count,
            self.offer_count,
            self.observation_count,
        ):
            _exact_int(value, minimum=0, maximum=120)
        _utc(self.occurred_at)
        if (
            self.identity_status is not CatalogIdentityStatusV2.HUMAN_REVIEW
            or self.readiness is not CatalogReadinessV2.NOT_READY
            or self.external_actions != 0
        ):
            fail_catalog_normalization_runtime()
        expected = _stable_uuid(
            "outbox_event",
            self.event_type,
            str(self.aggregate_id),
            self.aggregate_version,
            str(self.batch_id),
            str(self.source_snapshot_id),
        )
        if self.event_id != expected:
            fail_catalog_normalization_runtime()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            _json_bytes(catalog_normalized_event_mapping_v2(self))
        ).hexdigest()

    @classmethod
    def from_batch(
        cls, batch: CatalogNormalizationBatchV2
    ) -> CatalogNormalizedOutboxEventV2:
        if type(batch) is not CatalogNormalizationBatchV2:
            fail_catalog_normalization_runtime()
        version = batch.expected_catalog_version + 1
        event_id = _stable_uuid(
            "outbox_event",
            CATALOG_EVENT_TYPE_V2,
            str(batch.source_snapshot.source_session_id),
            version,
            str(batch.batch_id),
            str(batch.source_snapshot.snapshot_id),
        )
        return cls(
            event_id=event_id,
            event_type=CATALOG_EVENT_TYPE_V2,
            channel=CATALOG_EVENT_CHANNEL_V2,
            aggregate_id=batch.source_snapshot.source_session_id,
            aggregate_version=version,
            batch_id=batch.batch_id,
            source_snapshot_id=batch.source_snapshot.snapshot_id,
            candidate_count=len(batch.candidates),
            offer_count=len(batch.offers),
            observation_count=len(batch.observations),
            occurred_at=batch.source_snapshot.normalized_at,
            identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
            readiness=CatalogReadinessV2.NOT_READY,
            external_actions=0,
        )


@dataclass(frozen=True, slots=True, repr=False)
class PersistedCatalogNormalizationV2(_RedactedValue):
    operation_id: UUID
    payload_fingerprint: str
    catalog_version: int
    previous_chain_hash: str
    chain_hash: str
    batch: CatalogNormalizationBatchV2
    event: CatalogNormalizedOutboxEventV2
    committed_at: datetime

    def __post_init__(self) -> None:
        _uuid(self.operation_id)
        _sha256(self.payload_fingerprint)
        _exact_int(self.catalog_version, minimum=1, maximum=_MAX_VERSION)
        previous = _sha256(self.previous_chain_hash)
        _sha256(self.chain_hash)
        if (
            type(self.batch) is not CatalogNormalizationBatchV2
            or type(self.event) is not CatalogNormalizedOutboxEventV2
            or self.operation_id != self.batch.operation_id
            or self.payload_fingerprint != self.batch.command_fingerprint
            or self.catalog_version != self.batch.expected_catalog_version + 1
            or self.event.aggregate_version != self.catalog_version
            or self.event.batch_id != self.batch.batch_id
        ):
            fail_catalog_normalization_runtime()
        committed_at = _utc(self.committed_at)
        if committed_at != self.batch.source_snapshot.normalized_at:
            fail_catalog_normalization_runtime()
        expected_chain = catalog_chain_hash_v2(
            previous_chain_hash=previous,
            catalog_version=self.catalog_version,
            operation_id=self.operation_id,
            batch_sha256=self.batch.sha256,
            event_sha256=self.event.sha256,
            committed_at=committed_at,
        )
        if self.chain_hash != expected_chain:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationResultV2(_RedactedValue):
    persisted: PersistedCatalogNormalizationV2
    replay_status: CatalogReplayStatusV2
    external_actions: int

    def __post_init__(self) -> None:
        if (
            type(self.persisted) is not PersistedCatalogNormalizationV2
            or type(self.replay_status) is not CatalogReplayStatusV2
            or self.external_actions != 0
        ):
            fail_catalog_normalization_runtime()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogCommitRecoveryV2(_RedactedValue):
    outcome: CatalogCommitRecoveryOutcomeV2
    persisted: PersistedCatalogNormalizationV2 | None

    def __post_init__(self) -> None:
        if type(self.outcome) is not CatalogCommitRecoveryOutcomeV2 or (
            self.outcome is CatalogCommitRecoveryOutcomeV2.COMMITTED
        ) != (type(self.persisted) is PersistedCatalogNormalizationV2):
            fail_catalog_normalization_runtime()


def catalog_chain_hash_v2(
    *,
    previous_chain_hash: str,
    catalog_version: int,
    operation_id: UUID,
    batch_sha256: str,
    event_sha256: str,
    committed_at: datetime,
) -> str:
    return hashlib.sha256(
        _json_bytes(
            {
                "batch_sha256": _sha256(batch_sha256),
                "catalog_version": _exact_int(
                    catalog_version, minimum=1, maximum=_MAX_VERSION
                ),
                "committed_at": _utc_text(committed_at),
                "event_sha256": _sha256(event_sha256),
                "operation_id": str(_uuid(operation_id)),
                "previous_chain_hash": _sha256(previous_chain_hash),
            }
        )
    ).hexdigest()


def _source_snapshot_from_command(
    command: CatalogNormalizationCommandV2,
) -> CatalogSourceSnapshotV2:
    receipt = cast(RawArchiveReceiptV2, command.source_step.receipt)
    snapshot_id = _stable_uuid(
        "source_snapshot",
        CATALOG_PROVIDER_V2,
        ITEM_SEARCH_API_VERSION,
        command.normalizer_version,
        str(command.source_step.session.session_id),
        command.source_step.session.version,
        str(receipt.receipt_id),
        receipt.request_fingerprint,
        receipt.artifact_sha256,
        receipt.byte_size,
        receipt.artifact_version,
        receipt.logical_key,
        receipt.page,
        _utc_text(receipt.observed_at),
    )
    return CatalogSourceSnapshotV2(
        snapshot_id=snapshot_id,
        provider=CATALOG_PROVIDER_V2,
        api_version=ITEM_SEARCH_API_VERSION,
        source_mode=CatalogSourceModeV2.RECORDED_PERSISTED,
        source_session_id=command.source_step.session.session_id,
        source_session_version=command.source_step.session.version,
        receipt_id=receipt.receipt_id,
        request_fingerprint=receipt.request_fingerprint,
        raw_sha256=receipt.artifact_sha256,
        raw_byte_size=receipt.byte_size,
        artifact_version=receipt.artifact_version,
        logical_key=receipt.logical_key,
        page=receipt.page,
        observed_at=receipt.observed_at,
        normalized_at=command.normalized_at,
        normalizer_version=command.normalizer_version,
        confidence=None,
        confidence_status=CatalogConfidenceStatusV2.SOURCE_ABSENT,
    )


def _optional_provider_text(
    value: UntrustedProviderTextV2 | None,
) -> CatalogUntrustedTextV2 | None:
    return None if value is None else CatalogUntrustedTextV2.from_provider(value)


def _item_records(
    *,
    item: ParsedItemSearchItemV2,
    ordinal: int,
    snapshot: CatalogSourceSnapshotV2,
    next_observation_ordinal: int,
) -> tuple[
    CatalogCandidateV2,
    CatalogOfferV2,
    tuple[CatalogObservationV2, ...],
]:
    if type(item) is not ParsedItemSearchItemV2:
        fail_catalog_normalization_runtime()
    item_code = CatalogUntrustedTextV2.from_provider(item.item_code)
    shop_code = CatalogUntrustedTextV2.from_provider(item.shop_code)
    shop_id = _stable_uuid(
        "shop",
        CATALOG_PROVIDER_V2,
        ITEM_SEARCH_API_VERSION,
        CATALOG_NORMALIZER_VERSION_V2,
        shop_code.value,
        str(snapshot.receipt_id),
        str(snapshot.snapshot_id),
        snapshot.artifact_version,
    )
    candidate_id = _stable_uuid(
        "candidate",
        CATALOG_PROVIDER_V2,
        ITEM_SEARCH_API_VERSION,
        CATALOG_NORMALIZER_VERSION_V2,
        item_code.value,
        shop_code.value,
        str(shop_id),
        str(snapshot.snapshot_id),
        ordinal,
    )
    candidate = CatalogCandidateV2(
        candidate_id=candidate_id,
        ordinal=ordinal,
        provider=CATALOG_PROVIDER_V2,
        api_version=ITEM_SEARCH_API_VERSION,
        external_item_code=item_code,
        external_shop_code=shop_code,
        shop_id=shop_id,
        item_name=CatalogUntrustedTextV2.from_provider(item.item_name),
        catchcopy=_optional_provider_text(item.catchcopy),
        item_caption=_optional_provider_text(item.item_caption),
        shop_name=_optional_provider_text(item.shop_name),
        genre_id=item.genre_id,
        image_urls=tuple(
            CatalogUntrustedUrlV2.from_provider(value) for value in item.image_urls
        ),
        source_snapshot_id=snapshot.snapshot_id,
        observed_at=snapshot.observed_at,
        identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
        readiness=CatalogReadinessV2.NOT_READY,
        canonical_product_id=None,
        model_number_candidate=None,
        jan_code_candidate=None,
        identity_confidence=None,
        recommendation_eligible=False,
    )
    item_url = CatalogUntrustedUrlV2.from_provider(item.item_url)
    offer_id = _stable_uuid(
        "offer",
        CATALOG_PROVIDER_V2,
        ITEM_SEARCH_API_VERSION,
        CATALOG_NORMALIZER_VERSION_V2,
        item_code.value,
        str(candidate_id),
        str(shop_id),
        item_url.value,
        str(snapshot.snapshot_id),
        ordinal,
    )
    offer = CatalogOfferV2(
        offer_id=offer_id,
        ordinal=ordinal,
        provider=CATALOG_PROVIDER_V2,
        api_version=ITEM_SEARCH_API_VERSION,
        external_offer_id=item_code,
        candidate_id=candidate_id,
        shop_id=shop_id,
        item_url=item_url,
        source_snapshot_id=snapshot.snapshot_id,
        observed_at=snapshot.observed_at,
        canonical_product_id=None,
        identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
        readiness=CatalogReadinessV2.NOT_READY,
        recommendation_eligible=False,
    )
    values: list[tuple[CatalogObservationKindV2, object, str | None]] = [
        (CatalogObservationKindV2.PRICE_JPY, item.item_price_jpy, "JPY"),
        (
            CatalogObservationKindV2.AVAILABILITY_PROVIDER_FLAG,
            item.availability,
            None,
        ),
        (
            CatalogObservationKindV2.POSTAGE_INCLUDED_PROVIDER_FLAG,
            item.postage_included,
            None,
        ),
    ]
    if item.affiliate_url is not None:
        values.append(
            (
                CatalogObservationKindV2.AFFILIATE_LINK,
                CatalogUntrustedUrlV2.from_provider(item.affiliate_url),
                None,
            )
        )
    observations: list[CatalogObservationV2] = []
    for offset, (kind, value, unit) in enumerate(values):
        observation_ordinal = next_observation_ordinal + offset
        integer_value = value if type(value) is int else None
        boolean_value = value if type(value) is bool else None
        url_value = value if type(value) is CatalogUntrustedUrlV2 else None
        value_material: object = (
            integer_value
            if integer_value is not None
            else boolean_value
            if boolean_value is not None
            else cast(CatalogUntrustedUrlV2, url_value).value
        )
        observation_id = _stable_uuid(
            "observation",
            CATALOG_NORMALIZER_VERSION_V2,
            str(offer_id),
            kind.value,
            value_material,
            unit,
            str(snapshot.snapshot_id),
            observation_ordinal,
        )
        observations.append(
            CatalogObservationV2(
                observation_id=observation_id,
                ordinal=observation_ordinal,
                offer_id=offer_id,
                kind=kind,
                integer_value=integer_value,
                boolean_value=boolean_value,
                url_value=url_value,
                unit_code=unit,
                observed_at=snapshot.observed_at,
                normalized_at=snapshot.normalized_at,
                source_snapshot_id=snapshot.snapshot_id,
                confidence=None,
                confidence_status=CatalogConfidenceStatusV2.SOURCE_ABSENT,
                recommendation_input=False,
            )
        )
    return candidate, offer, tuple(observations)


def normalize_persisted_item_search_page_v2(
    *,
    command: CatalogNormalizationCommandV2,
    page: ParsedItemSearchPageV2,
    raw_body: bytes,
) -> CatalogNormalizationBatchV2:
    if (
        type(command) is not CatalogNormalizationCommandV2
        or type(page) is not ParsedItemSearchPageV2
        or type(raw_body) is not bytes
    ):
        fail_catalog_normalization_runtime()
    receipt = cast(RawArchiveReceiptV2, command.source_step.receipt)
    if (
        len(raw_body) != receipt.byte_size
        or hashlib.sha256(raw_body).hexdigest() != receipt.artifact_sha256
        or page.raw_sha256 != receipt.artifact_sha256
        or page.request_fingerprint != receipt.request_fingerprint
        or page.page != receipt.page
        or page.observed_at != receipt.observed_at
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.SOURCE_INTEGRITY
        )
    snapshot = _source_snapshot_from_command(command)
    candidates: list[CatalogCandidateV2] = []
    offers: list[CatalogOfferV2] = []
    observations: list[CatalogObservationV2] = []
    for ordinal, item in enumerate(page.items, start=1):
        candidate, offer, item_observations = _item_records(
            item=item,
            ordinal=ordinal,
            snapshot=snapshot,
            next_observation_ordinal=len(observations) + 1,
        )
        candidates.append(candidate)
        offers.append(offer)
        observations.extend(item_observations)
    batch_id = _stable_uuid(
        "batch",
        command.normalizer_version,
        str(snapshot.snapshot_id),
        command.payload_fingerprint,
    )
    return CatalogNormalizationBatchV2(
        batch_id=batch_id,
        operation_id=command.operation_id,
        command_fingerprint=command.payload_fingerprint,
        expected_catalog_version=command.expected_catalog_version,
        normalizer_version=command.normalizer_version,
        source_snapshot=snapshot,
        candidates=tuple(candidates),
        offers=tuple(offers),
        observations=tuple(observations),
        identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
        readiness=CatalogReadinessV2.NOT_READY,
        open_decision=CATALOG_IDENTITY_OPEN_DECISION_V2,
        canonical_products=(),
        grouping_decisions=(),
        provider_derived_recommendation_inputs=(),
        forbidden_recommendation_inputs=CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2,
        external_actions=0,
    )


def _text_mapping(value: CatalogUntrustedTextV2 | None) -> object:
    if value is None:
        return None
    if type(value) is not CatalogUntrustedTextV2:
        fail_catalog_normalization_runtime()
    return {"trust": value.trust.value, "value": value.value}


def _text_from_mapping(
    value: object, *, optional: bool = False
) -> CatalogUntrustedTextV2 | None:
    if optional and value is None:
        return None
    data = _exact_mapping(value, frozenset({"trust", "value"}))
    if data["trust"] != ProviderTextTrustV2.UNTRUSTED_DATA.value:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return CatalogUntrustedTextV2(
        value=cast(str, data["value"]),
        trust=ProviderTextTrustV2.UNTRUSTED_DATA,
    )


def _url_mapping(value: CatalogUntrustedUrlV2 | None) -> object:
    if value is None:
        return None
    if type(value) is not CatalogUntrustedUrlV2:
        fail_catalog_normalization_runtime()
    return {"trust": value.trust.value, "value": value.value}


def _url_from_mapping(
    value: object, *, optional: bool = False
) -> CatalogUntrustedUrlV2 | None:
    if optional and value is None:
        return None
    data = _exact_mapping(value, frozenset({"trust", "value"}))
    if data["trust"] != ProviderTextTrustV2.UNTRUSTED_DATA.value:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return CatalogUntrustedUrlV2(
        value=cast(str, data["value"]),
        trust=ProviderTextTrustV2.UNTRUSTED_DATA,
    )


def catalog_source_snapshot_mapping_v2(
    value: CatalogSourceSnapshotV2,
) -> dict[str, object]:
    if type(value) is not CatalogSourceSnapshotV2:
        fail_catalog_normalization_runtime()
    return {
        "api_version": value.api_version,
        "artifact_version": value.artifact_version,
        "confidence": value.confidence,
        "confidence_status": value.confidence_status.value,
        "logical_key": value.logical_key,
        "normalized_at": _utc_text(value.normalized_at),
        "normalizer_version": value.normalizer_version,
        "observed_at": _utc_text(value.observed_at),
        "page": value.page,
        "provider": value.provider,
        "raw_byte_size": value.raw_byte_size,
        "raw_sha256": value.raw_sha256,
        "receipt_id": str(value.receipt_id),
        "request_fingerprint": value.request_fingerprint,
        "snapshot_id": str(value.snapshot_id),
        "source_mode": value.source_mode.value,
        "source_session_id": str(value.source_session_id),
        "source_session_version": value.source_session_version,
    }


def catalog_source_snapshot_from_mapping_v2(
    value: object,
) -> CatalogSourceSnapshotV2:
    keys = frozenset(
        {
            "api_version",
            "artifact_version",
            "confidence",
            "confidence_status",
            "logical_key",
            "normalized_at",
            "normalizer_version",
            "observed_at",
            "page",
            "provider",
            "raw_byte_size",
            "raw_sha256",
            "receipt_id",
            "request_fingerprint",
            "snapshot_id",
            "source_mode",
            "source_session_id",
            "source_session_version",
        }
    )
    data = _exact_mapping(value, keys)
    if (
        data["source_mode"] != CatalogSourceModeV2.RECORDED_PERSISTED.value
        or data["confidence_status"] != CatalogConfidenceStatusV2.SOURCE_ABSENT.value
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    try:
        return CatalogSourceSnapshotV2(
            snapshot_id=_parse_uuid(data["snapshot_id"]),
            provider=cast(str, data["provider"]),
            api_version=cast(str, data["api_version"]),
            source_mode=CatalogSourceModeV2.RECORDED_PERSISTED,
            source_session_id=_parse_uuid(data["source_session_id"]),
            source_session_version=cast(int, data["source_session_version"]),
            receipt_id=_parse_uuid(data["receipt_id"]),
            request_fingerprint=cast(str, data["request_fingerprint"]),
            raw_sha256=cast(str, data["raw_sha256"]),
            raw_byte_size=cast(int, data["raw_byte_size"]),
            artifact_version=cast(int, data["artifact_version"]),
            logical_key=cast(str, data["logical_key"]),
            page=cast(int, data["page"]),
            observed_at=_parse_utc(data["observed_at"]),
            normalized_at=_parse_utc(data["normalized_at"]),
            normalizer_version=cast(str, data["normalizer_version"]),
            confidence=cast(None, data["confidence"]),
            confidence_status=CatalogConfidenceStatusV2.SOURCE_ABSENT,
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def catalog_candidate_mapping_v2(value: CatalogCandidateV2) -> dict[str, object]:
    if type(value) is not CatalogCandidateV2:
        fail_catalog_normalization_runtime()
    return {
        "api_version": value.api_version,
        "candidate_id": str(value.candidate_id),
        "canonical_product_id": value.canonical_product_id,
        "catchcopy": _text_mapping(value.catchcopy),
        "external_item_code": _text_mapping(value.external_item_code),
        "external_shop_code": _text_mapping(value.external_shop_code),
        "genre_id": value.genre_id,
        "identity_confidence": value.identity_confidence,
        "identity_status": value.identity_status.value,
        "image_urls": [_url_mapping(item) for item in value.image_urls],
        "item_caption": _text_mapping(value.item_caption),
        "item_name": _text_mapping(value.item_name),
        "jan_code_candidate": value.jan_code_candidate,
        "model_number_candidate": value.model_number_candidate,
        "observed_at": _utc_text(value.observed_at),
        "ordinal": value.ordinal,
        "provider": value.provider,
        "readiness": value.readiness.value,
        "recommendation_eligible": value.recommendation_eligible,
        "shop_id": str(value.shop_id),
        "shop_name": _text_mapping(value.shop_name),
        "source_snapshot_id": str(value.source_snapshot_id),
    }


def catalog_candidate_from_mapping_v2(value: object) -> CatalogCandidateV2:
    keys = frozenset(
        {
            "api_version",
            "candidate_id",
            "canonical_product_id",
            "catchcopy",
            "external_item_code",
            "external_shop_code",
            "genre_id",
            "identity_confidence",
            "identity_status",
            "image_urls",
            "item_caption",
            "item_name",
            "jan_code_candidate",
            "model_number_candidate",
            "observed_at",
            "ordinal",
            "provider",
            "readiness",
            "recommendation_eligible",
            "shop_id",
            "shop_name",
            "source_snapshot_id",
        }
    )
    data = _exact_mapping(value, keys)
    images = data["image_urls"]
    if type(images) is not list:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    if (
        data["identity_status"] != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or data["readiness"] != CatalogReadinessV2.NOT_READY.value
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    try:
        return CatalogCandidateV2(
            candidate_id=_parse_uuid(data["candidate_id"]),
            ordinal=cast(int, data["ordinal"]),
            provider=cast(str, data["provider"]),
            api_version=cast(str, data["api_version"]),
            external_item_code=cast(
                CatalogUntrustedTextV2,
                _text_from_mapping(data["external_item_code"]),
            ),
            external_shop_code=cast(
                CatalogUntrustedTextV2,
                _text_from_mapping(data["external_shop_code"]),
            ),
            shop_id=_parse_uuid(data["shop_id"]),
            item_name=cast(
                CatalogUntrustedTextV2, _text_from_mapping(data["item_name"])
            ),
            catchcopy=_text_from_mapping(data["catchcopy"], optional=True),
            item_caption=_text_from_mapping(data["item_caption"], optional=True),
            shop_name=_text_from_mapping(data["shop_name"], optional=True),
            genre_id=cast(int, data["genre_id"]),
            image_urls=tuple(
                cast(CatalogUntrustedUrlV2, _url_from_mapping(item))
                for item in cast(list[object], images)
            ),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            observed_at=_parse_utc(data["observed_at"]),
            identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
            readiness=CatalogReadinessV2.NOT_READY,
            canonical_product_id=cast(None, data["canonical_product_id"]),
            model_number_candidate=cast(None, data["model_number_candidate"]),
            jan_code_candidate=cast(None, data["jan_code_candidate"]),
            identity_confidence=cast(None, data["identity_confidence"]),
            recommendation_eligible=cast(bool, data["recommendation_eligible"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def catalog_offer_mapping_v2(value: CatalogOfferV2) -> dict[str, object]:
    if type(value) is not CatalogOfferV2:
        fail_catalog_normalization_runtime()
    return {
        "api_version": value.api_version,
        "candidate_id": str(value.candidate_id),
        "canonical_product_id": value.canonical_product_id,
        "external_offer_id": _text_mapping(value.external_offer_id),
        "identity_status": value.identity_status.value,
        "item_url": _url_mapping(value.item_url),
        "observed_at": _utc_text(value.observed_at),
        "offer_id": str(value.offer_id),
        "ordinal": value.ordinal,
        "provider": value.provider,
        "readiness": value.readiness.value,
        "recommendation_eligible": value.recommendation_eligible,
        "shop_id": str(value.shop_id),
        "source_snapshot_id": str(value.source_snapshot_id),
    }


def catalog_offer_from_mapping_v2(value: object) -> CatalogOfferV2:
    keys = frozenset(
        {
            "api_version",
            "candidate_id",
            "canonical_product_id",
            "external_offer_id",
            "identity_status",
            "item_url",
            "observed_at",
            "offer_id",
            "ordinal",
            "provider",
            "readiness",
            "recommendation_eligible",
            "shop_id",
            "source_snapshot_id",
        }
    )
    data = _exact_mapping(value, keys)
    if (
        data["identity_status"] != CatalogIdentityStatusV2.HUMAN_REVIEW.value
        or data["readiness"] != CatalogReadinessV2.NOT_READY.value
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    try:
        return CatalogOfferV2(
            offer_id=_parse_uuid(data["offer_id"]),
            ordinal=cast(int, data["ordinal"]),
            provider=cast(str, data["provider"]),
            api_version=cast(str, data["api_version"]),
            external_offer_id=cast(
                CatalogUntrustedTextV2,
                _text_from_mapping(data["external_offer_id"]),
            ),
            candidate_id=_parse_uuid(data["candidate_id"]),
            shop_id=_parse_uuid(data["shop_id"]),
            item_url=cast(CatalogUntrustedUrlV2, _url_from_mapping(data["item_url"])),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            observed_at=_parse_utc(data["observed_at"]),
            canonical_product_id=cast(None, data["canonical_product_id"]),
            identity_status=CatalogIdentityStatusV2.HUMAN_REVIEW,
            readiness=CatalogReadinessV2.NOT_READY,
            recommendation_eligible=cast(bool, data["recommendation_eligible"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def catalog_observation_mapping_v2(
    value: CatalogObservationV2,
) -> dict[str, object]:
    if type(value) is not CatalogObservationV2:
        fail_catalog_normalization_runtime()
    return {
        "boolean_value": value.boolean_value,
        "confidence": value.confidence,
        "confidence_status": value.confidence_status.value,
        "integer_value": value.integer_value,
        "kind": value.kind.value,
        "normalized_at": _utc_text(value.normalized_at),
        "observation_id": str(value.observation_id),
        "observed_at": _utc_text(value.observed_at),
        "offer_id": str(value.offer_id),
        "ordinal": value.ordinal,
        "recommendation_input": value.recommendation_input,
        "source_snapshot_id": str(value.source_snapshot_id),
        "unit_code": value.unit_code,
        "url_value": _url_mapping(value.url_value),
    }


def catalog_observation_from_mapping_v2(value: object) -> CatalogObservationV2:
    keys = frozenset(
        {
            "boolean_value",
            "confidence",
            "confidence_status",
            "integer_value",
            "kind",
            "normalized_at",
            "observation_id",
            "observed_at",
            "offer_id",
            "ordinal",
            "recommendation_input",
            "source_snapshot_id",
            "unit_code",
            "url_value",
        }
    )
    data = _exact_mapping(value, keys)
    try:
        kind = CatalogObservationKindV2(cast(str, data["kind"]))
        confidence_status = CatalogConfidenceStatusV2(
            cast(str, data["confidence_status"])
        )
        return CatalogObservationV2(
            observation_id=_parse_uuid(data["observation_id"]),
            ordinal=cast(int, data["ordinal"]),
            offer_id=_parse_uuid(data["offer_id"]),
            kind=kind,
            integer_value=cast(int | None, data["integer_value"]),
            boolean_value=cast(bool | None, data["boolean_value"]),
            url_value=_url_from_mapping(data["url_value"], optional=True),
            unit_code=cast(str | None, data["unit_code"]),
            observed_at=_parse_utc(data["observed_at"]),
            normalized_at=_parse_utc(data["normalized_at"]),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            confidence=cast(None, data["confidence"]),
            confidence_status=confidence_status,
            recommendation_input=cast(bool, data["recommendation_input"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def catalog_normalization_batch_mapping_v2(
    value: CatalogNormalizationBatchV2,
) -> dict[str, object]:
    if type(value) is not CatalogNormalizationBatchV2:
        fail_catalog_normalization_runtime()
    return {
        "batch_id": str(value.batch_id),
        "canonical_products": [],
        "candidates": [catalog_candidate_mapping_v2(item) for item in value.candidates],
        "command_fingerprint": value.command_fingerprint,
        "expected_catalog_version": value.expected_catalog_version,
        "external_actions": value.external_actions,
        "forbidden_recommendation_inputs": list(value.forbidden_recommendation_inputs),
        "grouping_decisions": [],
        "identity_status": value.identity_status.value,
        "normalizer_version": value.normalizer_version,
        "observations": [
            catalog_observation_mapping_v2(item) for item in value.observations
        ],
        "offers": [catalog_offer_mapping_v2(item) for item in value.offers],
        "open_decision": value.open_decision,
        "operation_id": str(value.operation_id),
        "provider_derived_recommendation_inputs": [],
        "readiness": value.readiness.value,
        "source_snapshot": catalog_source_snapshot_mapping_v2(value.source_snapshot),
    }


def _list(value: object) -> list[object]:
    if type(value) is not list:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return cast(list[object], value)


def catalog_normalization_batch_from_mapping_v2(
    value: object,
) -> CatalogNormalizationBatchV2:
    keys = frozenset(
        {
            "batch_id",
            "canonical_products",
            "candidates",
            "command_fingerprint",
            "expected_catalog_version",
            "external_actions",
            "forbidden_recommendation_inputs",
            "grouping_decisions",
            "identity_status",
            "normalizer_version",
            "observations",
            "offers",
            "open_decision",
            "operation_id",
            "provider_derived_recommendation_inputs",
            "readiness",
            "source_snapshot",
        }
    )
    data = _exact_mapping(value, keys)
    empty_keys = (
        "canonical_products",
        "grouping_decisions",
        "provider_derived_recommendation_inputs",
    )
    if any(_list(data[key]) != [] for key in empty_keys):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    forbidden = _list(data["forbidden_recommendation_inputs"])
    if any(type(item) is not str for item in forbidden):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    try:
        return CatalogNormalizationBatchV2(
            batch_id=_parse_uuid(data["batch_id"]),
            operation_id=_parse_uuid(data["operation_id"]),
            command_fingerprint=cast(str, data["command_fingerprint"]),
            expected_catalog_version=cast(int, data["expected_catalog_version"]),
            normalizer_version=cast(str, data["normalizer_version"]),
            source_snapshot=catalog_source_snapshot_from_mapping_v2(
                data["source_snapshot"]
            ),
            candidates=tuple(
                catalog_candidate_from_mapping_v2(item)
                for item in _list(data["candidates"])
            ),
            offers=tuple(
                catalog_offer_from_mapping_v2(item) for item in _list(data["offers"])
            ),
            observations=tuple(
                catalog_observation_from_mapping_v2(item)
                for item in _list(data["observations"])
            ),
            identity_status=CatalogIdentityStatusV2(cast(str, data["identity_status"])),
            readiness=CatalogReadinessV2(cast(str, data["readiness"])),
            open_decision=cast(str, data["open_decision"]),
            canonical_products=(),
            grouping_decisions=(),
            provider_derived_recommendation_inputs=(),
            forbidden_recommendation_inputs=tuple(cast(list[str], forbidden)),
            external_actions=cast(int, data["external_actions"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def catalog_normalized_event_mapping_v2(
    value: CatalogNormalizedOutboxEventV2,
) -> dict[str, object]:
    if type(value) is not CatalogNormalizedOutboxEventV2:
        fail_catalog_normalization_runtime()
    return {
        "aggregate_id": str(value.aggregate_id),
        "aggregate_version": value.aggregate_version,
        "batch_id": str(value.batch_id),
        "candidate_count": value.candidate_count,
        "channel": value.channel,
        "event_id": str(value.event_id),
        "event_type": value.event_type,
        "external_actions": value.external_actions,
        "identity_status": value.identity_status.value,
        "observation_count": value.observation_count,
        "occurred_at": _utc_text(value.occurred_at),
        "offer_count": value.offer_count,
        "readiness": value.readiness.value,
        "source_snapshot_id": str(value.source_snapshot_id),
    }


def catalog_normalized_event_from_mapping_v2(
    value: object,
) -> CatalogNormalizedOutboxEventV2:
    keys = frozenset(
        {
            "aggregate_id",
            "aggregate_version",
            "batch_id",
            "candidate_count",
            "channel",
            "event_id",
            "event_type",
            "external_actions",
            "identity_status",
            "observation_count",
            "occurred_at",
            "offer_count",
            "readiness",
            "source_snapshot_id",
        }
    )
    data = _exact_mapping(value, keys)
    try:
        return CatalogNormalizedOutboxEventV2(
            event_id=_parse_uuid(data["event_id"]),
            event_type=cast(str, data["event_type"]),
            channel=cast(str, data["channel"]),
            aggregate_id=_parse_uuid(data["aggregate_id"]),
            aggregate_version=cast(int, data["aggregate_version"]),
            batch_id=_parse_uuid(data["batch_id"]),
            source_snapshot_id=_parse_uuid(data["source_snapshot_id"]),
            candidate_count=cast(int, data["candidate_count"]),
            offer_count=cast(int, data["offer_count"]),
            observation_count=cast(int, data["observation_count"]),
            occurred_at=_parse_utc(data["occurred_at"]),
            identity_status=CatalogIdentityStatusV2(cast(str, data["identity_status"])),
            readiness=CatalogReadinessV2(cast(str, data["readiness"])),
            external_actions=cast(int, data["external_actions"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def persisted_catalog_normalization_mapping_v2(
    value: PersistedCatalogNormalizationV2,
) -> dict[str, object]:
    if type(value) is not PersistedCatalogNormalizationV2:
        fail_catalog_normalization_runtime()
    return {
        "batch": catalog_normalization_batch_mapping_v2(value.batch),
        "catalog_version": value.catalog_version,
        "chain_hash": value.chain_hash,
        "committed_at": _utc_text(value.committed_at),
        "event": catalog_normalized_event_mapping_v2(value.event),
        "operation_id": str(value.operation_id),
        "payload_fingerprint": value.payload_fingerprint,
        "previous_chain_hash": value.previous_chain_hash,
    }


def persisted_catalog_normalization_from_mapping_v2(
    value: object,
) -> PersistedCatalogNormalizationV2:
    keys = frozenset(
        {
            "batch",
            "catalog_version",
            "chain_hash",
            "committed_at",
            "event",
            "operation_id",
            "payload_fingerprint",
            "previous_chain_hash",
        }
    )
    data = _exact_mapping(value, keys)
    try:
        return PersistedCatalogNormalizationV2(
            operation_id=_parse_uuid(data["operation_id"]),
            payload_fingerprint=cast(str, data["payload_fingerprint"]),
            catalog_version=cast(int, data["catalog_version"]),
            previous_chain_hash=cast(str, data["previous_chain_hash"]),
            chain_hash=cast(str, data["chain_hash"]),
            batch=catalog_normalization_batch_from_mapping_v2(data["batch"]),
            event=catalog_normalized_event_from_mapping_v2(data["event"]),
            committed_at=_parse_utc(data["committed_at"]),
        )
    except ValueError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


__all__ = [
    "CATALOG_EVENT_CHANNEL_V2",
    "CATALOG_EVENT_TYPE_V2",
    "CATALOG_FORBIDDEN_RECOMMENDATION_INPUTS_V2",
    "CATALOG_IDENTITY_OPEN_DECISION_V2",
    "CATALOG_NORMALIZER_VERSION_V2",
    "CATALOG_PROVIDER_V2",
    "CatalogCandidateV2",
    "CatalogCommitRecoveryOutcomeV2",
    "CatalogCommitRecoveryV2",
    "CatalogConfidenceStatusV2",
    "CatalogIdentityStatusV2",
    "CatalogNormalizationBatchV2",
    "CatalogNormalizationCommandV2",
    "CatalogNormalizationResultV2",
    "CatalogNormalizationRuntimeFailure",
    "CatalogNormalizationRuntimeFailureCode",
    "CatalogNormalizedOutboxEventV2",
    "CatalogObservationKindV2",
    "CatalogObservationV2",
    "CatalogOfferV2",
    "CatalogReadinessV2",
    "CatalogReplayStatusV2",
    "CatalogSourceModeV2",
    "CatalogSourceSnapshotV2",
    "CatalogUntrustedTextV2",
    "CatalogUntrustedUrlV2",
    "PersistedCatalogNormalizationV2",
    "catalog_candidate_from_mapping_v2",
    "catalog_candidate_mapping_v2",
    "catalog_chain_hash_v2",
    "catalog_normalization_batch_from_mapping_v2",
    "catalog_normalization_batch_mapping_v2",
    "catalog_normalized_event_from_mapping_v2",
    "catalog_normalized_event_mapping_v2",
    "catalog_observation_from_mapping_v2",
    "catalog_observation_mapping_v2",
    "catalog_offer_from_mapping_v2",
    "catalog_offer_mapping_v2",
    "catalog_source_snapshot_from_mapping_v2",
    "catalog_source_snapshot_mapping_v2",
    "fail_catalog_normalization_runtime",
    "normalize_persisted_item_search_page_v2",
    "persisted_catalog_normalization_from_mapping_v2",
    "persisted_catalog_normalization_mapping_v2",
]
