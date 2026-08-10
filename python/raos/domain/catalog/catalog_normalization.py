"""Lossless, recorded-only catalog normalization values for ST-0503."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.catalog.rakuten_item_search import (
    CanonicalItemSearchItem,
    ItemSearchOperation,
    ItemSearchPurpose,
    PersistenceExecutionStatus,
    ProviderMode,
    RakutenItemSearchCommand,
    RakutenItemSearchResult,
    StorageExecutionStatus,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-catalog-normalization>"


class CatalogNormalizer(str, Enum):
    RECORDED_LOSSLESS_STRUCTURAL_V1 = "RECORDED_LOSSLESS_STRUCTURAL_V1"


class NormalizationMode(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class NormalizationScope(str, Enum):
    LOSSLESS_STRUCTURAL_ONLY = "LOSSLESS_STRUCTURAL_ONLY"


class NameNormalization(str, Enum):
    LOSSLESS_PASSTHROUGH = "LOSSLESS_PASSTHROUGH"


class SourceSnapshotStatus(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"


class SourceConfidenceStatus(str, Enum):
    SOURCE_ABSENT = "SOURCE_ABSENT"


class SourceValidationStatus(str, Enum):
    VALIDATED_RECORDED_RECEIPT_ONLY = "VALIDATED_RECORDED_RECEIPT_ONLY"


class RepositoryBoundary(str, Enum):
    ABSENT = "ABSENT"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class IdentityStatus(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class NormalizationDecision(str, Enum):
    NOT_READY = "NOT_READY"


class CatalogNormalizationFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NORMALIZER_UNAVAILABLE = "NORMALIZER_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("catalog normalization serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationFailure(RuntimeError):
    code: CatalogNormalizationFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not CatalogNormalizationFailureCode:
            raise TypeError("invalid catalog normalization failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"CatalogNormalizationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("catalog normalization failure serialization is not supported")


def fail_catalog_normalization(
    code: CatalogNormalizationFailureCode = (
        CatalogNormalizationFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise CatalogNormalizationFailure(code) from None


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_catalog_normalization()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_catalog_normalization()
    return value


def _nonzero_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_catalog_normalization()
    return value


def _validate_predecessor(
    search_command: object,
    search_result: object,
    expected_raw_sha256: object,
    ingested_at: object,
) -> tuple[RakutenItemSearchCommand, RakutenItemSearchResult, str, datetime]:
    if (
        type(search_command) is not RakutenItemSearchCommand
        or search_command.purpose is not ItemSearchPurpose.CONTRACT_TEST
        or search_command.operation is not ItemSearchOperation.ITEM_SEARCH
        or search_command.request.page != 1
        or type(search_result) is not RakutenItemSearchResult
        or search_result.provider_mode is not ProviderMode.RECORDED_TEST_ONLY
        or search_result.live_eligible is not False
        or search_result.storage_status is not StorageExecutionStatus.NOT_EXECUTED
        or search_result.persistence_status
        is not PersistenceExecutionStatus.NOT_EXECUTED
        or search_result.page.page != 1
        or search_result.page.request_sha256 != search_command.request.fingerprint
        or search_result.page.api_version != search_command.request.api_version
        or search_result.page.raw_artifact.uri is not None
        or search_result.page.raw_artifact.storage_status
        is not StorageExecutionStatus.NOT_EXECUTED
        or search_result.page.raw_artifact.sha256 != expected_raw_sha256
        or search_result.page.provider != "RAKUTEN_ICHIBA"
        or search_result.page.provider_rate_limit != search_result.rate
    ):
        fail_catalog_normalization()
    raw_sha256 = _sha256(expected_raw_sha256)
    timestamp = _utc(ingested_at)
    if timestamp < search_result.page.observed_at:
        fail_catalog_normalization()
    return search_command, search_result, raw_sha256, timestamp


def _time_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds")


def _item_projection(item: CanonicalItemSearchItem) -> dict[str, object]:
    return {
        "provider": item.provider,
        "api_version": item.api_version,
        "request_sha256": item.request_sha256,
        "raw_sha256": item.raw_sha256,
        "item_code": item.item_code,
        "item_name": item.item_name,
        "item_price_jpy": item.item_price_jpy,
        "item_url": item.item_url,
        "genre_id": item.genre_id,
        "availability": item.availability,
        "review_count": item.review_count,
        "review_average": item.review_average,
        "image_urls": list(item.image_urls),
        "provider_updated_at": _time_text(item.provider_updated_at),
        "observed_at": _time_text(item.observed_at),
    }


def _fingerprint_payload(
    *,
    search_command: RakutenItemSearchCommand,
    search_result: RakutenItemSearchResult,
    ingestion_request_id: UUID,
    normalizer: CatalogNormalizer,
    ingested_at: datetime,
    expected_raw_sha256: str,
) -> bytes:
    page = search_result.page
    receipt = page.raw_artifact
    value = {
        "expected_raw_sha256": expected_raw_sha256,
        "ingested_at": _time_text(ingested_at),
        "ingestion_request_id": str(ingestion_request_id),
        "normalizer": normalizer.value,
        "search_command": {
            "endpoint_id": str(search_command.endpoint_id),
            "fingerprint": search_command.fingerprint,
            "operation": search_command.operation.value,
            "purpose": search_command.purpose.value,
            "request_sha256": search_command.request.fingerprint,
        },
        "search_result": {
            "live_eligible": search_result.live_eligible,
            "mode": search_result.provider_mode.value,
            "page": {
                "api_version": page.api_version,
                "count": page.count,
                "hits": page.hits,
                "items": [_item_projection(item) for item in page.items],
                "observed_at": _time_text(page.observed_at),
                "page": page.page,
                "page_count": page.page_count,
                "provider": page.provider,
                "rate": {
                    "limit": page.provider_rate_limit.limit,
                    "remaining": page.provider_rate_limit.remaining,
                    "reset_at": _time_text(page.provider_rate_limit.reset_at),
                },
                "raw_artifact": {
                    "artifact_id": str(receipt.artifact_id),
                    "byte_size": receipt.byte_size,
                    "content_type": receipt.content_type,
                    "sha256": receipt.sha256,
                    "storage_status": receipt.storage_status.value,
                    "uri": receipt.uri,
                },
                "request_sha256": page.request_sha256,
                "warnings": list(page.warnings),
            },
            "persistence_status": search_result.persistence_status.value,
            "storage_status": search_result.storage_status.value,
        },
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationCommand(_RedactedValue):
    search_command: RakutenItemSearchCommand
    search_result: RakutenItemSearchResult
    ingestion_request_id: UUID
    normalizer: CatalogNormalizer
    ingested_at: datetime
    expected_raw_sha256: str
    fingerprint: str

    def __post_init__(self) -> None:
        command, result, raw_sha256, timestamp = _validate_predecessor(
            self.search_command,
            self.search_result,
            self.expected_raw_sha256,
            self.ingested_at,
        )
        request_id = _nonzero_uuid(self.ingestion_request_id)
        if self.normalizer is not CatalogNormalizer.RECORDED_LOSSLESS_STRUCTURAL_V1:
            fail_catalog_normalization()
        expected = hashlib.sha256(
            _fingerprint_payload(
                search_command=command,
                search_result=result,
                ingestion_request_id=request_id,
                normalizer=self.normalizer,
                ingested_at=timestamp,
                expected_raw_sha256=raw_sha256,
            )
        ).hexdigest()
        if _sha256(self.fingerprint) != expected:
            fail_catalog_normalization()

    @classmethod
    def from_search_result(
        cls,
        *,
        search_command: RakutenItemSearchCommand,
        search_result: RakutenItemSearchResult,
        ingestion_request_id: UUID,
        ingested_at: datetime,
    ) -> CatalogNormalizationCommand:
        command, result, raw_sha256, timestamp = _validate_predecessor(
            search_command,
            search_result,
            search_result.page.raw_artifact.sha256,
            ingested_at,
        )
        request_id = _nonzero_uuid(ingestion_request_id)
        normalizer = CatalogNormalizer.RECORDED_LOSSLESS_STRUCTURAL_V1
        fingerprint = hashlib.sha256(
            _fingerprint_payload(
                search_command=command,
                search_result=result,
                ingestion_request_id=request_id,
                normalizer=normalizer,
                ingested_at=timestamp,
                expected_raw_sha256=raw_sha256,
            )
        ).hexdigest()
        return cls(
            search_command=command,
            search_result=result,
            ingestion_request_id=request_id,
            normalizer=normalizer,
            ingested_at=timestamp,
            expected_raw_sha256=raw_sha256,
            fingerprint=fingerprint,
        )


@dataclass(frozen=True, slots=True, repr=False)
class CatalogSourceReference(_RedactedValue):
    provider: str
    api_version: str
    endpoint_id: UUID
    command_fingerprint: str
    request_sha256: str
    raw_artifact_id: UUID
    raw_sha256: str
    raw_byte_size: int
    observed_at: datetime
    ingested_at: datetime
    source_snapshot_id: None
    source_snapshot_status: SourceSnapshotStatus
    confidence: None
    confidence_status: SourceConfidenceStatus
    validation_status: SourceValidationStatus
    persistence_executed: bool
    repository: RepositoryBoundary
    database: ExecutionStatus

    def __post_init__(self) -> None:
        if (
            type(self.provider) is not str
            or self.provider != "RAKUTEN_ICHIBA"
            or type(self.api_version) is not str
            or self.api_version != "2026-07-01"
            or self.source_snapshot_id is not None
            or self.source_snapshot_status is not SourceSnapshotStatus.NOT_AVAILABLE
            or self.confidence is not None
            or self.confidence_status is not SourceConfidenceStatus.SOURCE_ABSENT
            or self.validation_status
            is not SourceValidationStatus.VALIDATED_RECORDED_RECEIPT_ONLY
            or self.persistence_executed is not False
            or self.repository is not RepositoryBoundary.ABSENT
            or self.database is not ExecutionStatus.NOT_EXECUTED
        ):
            fail_catalog_normalization()
        _nonzero_uuid(self.endpoint_id)
        _sha256(self.command_fingerprint)
        _sha256(self.request_sha256)
        _nonzero_uuid(self.raw_artifact_id)
        _sha256(self.raw_sha256)
        if type(self.raw_byte_size) is not int or self.raw_byte_size < 2:
            fail_catalog_normalization()
        observed = _utc(self.observed_at)
        if _utc(self.ingested_at) < observed:
            fail_catalog_normalization()


@dataclass(frozen=True, slots=True, repr=False)
class CatalogCandidateDraft(_RedactedValue):
    ordinal: int
    external_item_code: str
    external_genre_id: int | None
    display_name: str
    normalized_name: str
    name_normalization: NameNormalization
    image_urls: tuple[str, ...]
    provider_updated_at: datetime | None
    observed_at: datetime
    source: CatalogSourceReference
    candidate_id: None
    product_id: None
    shop_id: None
    genre_id: None
    model_number: None
    jan_code: None
    status: None
    confidence: None
    identity_decision: None
    grouping_keys: tuple[()]

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.external_item_code) is not str
            or not self.external_item_code
            or ":" not in self.external_item_code
            or (
                self.external_genre_id is not None
                and (
                    type(self.external_genre_id) is not int
                    or self.external_genre_id < 0
                )
            )
            or type(self.display_name) is not str
            or not self.display_name
            or self.normalized_name != self.display_name
            or type(self.normalized_name) is not str
            or self.name_normalization is not NameNormalization.LOSSLESS_PASSTHROUGH
            or type(self.image_urls) is not tuple
            or len(set(self.image_urls)) != len(self.image_urls)
            or any(type(value) is not str or not value for value in self.image_urls)
            or self.candidate_id is not None
            or self.product_id is not None
            or self.shop_id is not None
            or self.genre_id is not None
            or self.model_number is not None
            or self.jan_code is not None
            or self.status is not None
            or self.confidence is not None
            or self.identity_decision is not None
            or self.grouping_keys != ()
            or type(self.source) is not CatalogSourceReference
        ):
            fail_catalog_normalization()
        if self.provider_updated_at is not None:
            _utc(self.provider_updated_at)
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class OfferDraft(_RedactedValue):
    ordinal: int
    external_item_code: str
    endpoint_id: UUID
    item_url: str
    observed_at: datetime
    source: CatalogSourceReference
    offer_id: None
    product_id: None
    shop_id: None
    external_offer_id: None
    status: None
    price: None
    currency: None
    shipping: None
    points: None
    affiliate_url: None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.external_item_code) is not str
            or not self.external_item_code
            or ":" not in self.external_item_code
            or type(self.item_url) is not str
            or not self.item_url
            or not self.item_url.startswith("https://")
            or type(self.source) is not CatalogSourceReference
            or self.offer_id is not None
            or self.product_id is not None
            or self.shop_id is not None
            or self.external_offer_id is not None
            or self.status is not None
            or self.price is not None
            or self.currency is not None
            or self.shipping is not None
            or self.points is not None
            or self.affiliate_url is not None
        ):
            fail_catalog_normalization()
        _nonzero_uuid(self.endpoint_id)
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class PriceDraft(_RedactedValue):
    ordinal: int
    external_item_code: str
    amount_jpy: int
    observed_at: datetime
    source: CatalogSourceReference
    tax_included: None
    shipping: None
    points: None
    status: None
    confidence: None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.external_item_code) is not str
            or not self.external_item_code
            or ":" not in self.external_item_code
            or type(self.amount_jpy) is not int
            or self.amount_jpy < 0
            or type(self.source) is not CatalogSourceReference
            or self.tax_included is not None
            or self.shipping is not None
            or self.points is not None
            or self.status is not None
            or self.confidence is not None
        ):
            fail_catalog_normalization()
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class AvailabilityDraft(_RedactedValue):
    ordinal: int
    external_item_code: str
    provider_value: bool
    observed_at: datetime
    source: CatalogSourceReference
    semantic_status: None
    status: None
    confidence: None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.external_item_code) is not str
            or not self.external_item_code
            or ":" not in self.external_item_code
            or type(self.provider_value) is not bool
            or type(self.source) is not CatalogSourceReference
            or self.semantic_status is not None
            or self.status is not None
            or self.confidence is not None
        ):
            fail_catalog_normalization()
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewAggregateDraft(_RedactedValue):
    ordinal: int
    external_item_code: str
    review_count: int | None
    review_average: float | None
    observed_at: datetime
    source: CatalogSourceReference
    review_body: None
    status: None
    confidence: None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int
            or self.ordinal < 1
            or type(self.external_item_code) is not str
            or not self.external_item_code
            or ":" not in self.external_item_code
            or (
                self.review_count is not None
                and (type(self.review_count) is not int or self.review_count < 0)
            )
            or (
                self.review_average is not None
                and (
                    type(self.review_average) is not float
                    or not math.isfinite(self.review_average)
                    or not 0.0 <= self.review_average <= 5.0
                )
            )
            or type(self.source) is not CatalogSourceReference
            or self.review_body is not None
            or self.status is not None
            or self.confidence is not None
        ):
            fail_catalog_normalization()
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True, repr=False)
class CatalogNormalizationBatch(_RedactedValue):
    command_fingerprint: str
    ingestion_request_id: UUID
    mode: NormalizationMode
    scope: NormalizationScope
    candidates: tuple[CatalogCandidateDraft, ...]
    offers: tuple[OfferDraft, ...]
    prices: tuple[PriceDraft, ...]
    availabilities: tuple[AvailabilityDraft, ...]
    review_aggregates: tuple[ReviewAggregateDraft, ...]
    identity_status: IdentityStatus
    confidence: None
    confidence_status: SourceConfidenceStatus
    canonical_products: tuple[()]
    grouping_decisions: tuple[()]
    identity_decisions: tuple[()]
    memberships: tuple[()]
    merges: tuple[()]
    splits: tuple[()]
    repository: RepositoryBoundary
    persistence_executed: bool
    database: ExecutionStatus
    job: ExecutionStatus
    event: ExecutionStatus
    live_eligible: bool
    decision: NormalizationDecision
    empty_identity_interpretation: str

    def __post_init__(self) -> None:
        _sha256(self.command_fingerprint)
        _nonzero_uuid(self.ingestion_request_id)
        lengths = (
            len(self.candidates),
            len(self.offers),
            len(self.prices),
            len(self.availabilities),
            len(self.review_aggregates),
        )
        if (
            self.mode is not NormalizationMode.RECORDED_TEST_ONLY
            or self.scope is not NormalizationScope.LOSSLESS_STRUCTURAL_ONLY
            or type(self.candidates) is not tuple
            or type(self.offers) is not tuple
            or type(self.prices) is not tuple
            or type(self.availabilities) is not tuple
            or type(self.review_aggregates) is not tuple
            or len(set(lengths)) != 1
            or any(
                type(value) is not expected_type
                for values, expected_type in (
                    (self.candidates, CatalogCandidateDraft),
                    (self.offers, OfferDraft),
                    (self.prices, PriceDraft),
                    (self.availabilities, AvailabilityDraft),
                    (self.review_aggregates, ReviewAggregateDraft),
                )
                for value in values
            )
            or tuple(value.ordinal for value in self.candidates)
            != tuple(range(1, lengths[0] + 1))
            or tuple(value.ordinal for value in self.offers)
            != tuple(range(1, lengths[0] + 1))
            or tuple(value.ordinal for value in self.prices)
            != tuple(range(1, lengths[0] + 1))
            or tuple(value.ordinal for value in self.availabilities)
            != tuple(range(1, lengths[0] + 1))
            or tuple(value.ordinal for value in self.review_aggregates)
            != tuple(range(1, lengths[0] + 1))
            or self.identity_status is not IdentityStatus.REVIEW_REQUIRED
            or self.confidence is not None
            or self.confidence_status is not SourceConfidenceStatus.SOURCE_ABSENT
            or self.canonical_products != ()
            or self.grouping_decisions != ()
            or self.identity_decisions != ()
            or self.memberships != ()
            or self.merges != ()
            or self.splits != ()
            or self.repository is not RepositoryBoundary.ABSENT
            or self.persistence_executed is not False
            or self.database is not ExecutionStatus.NOT_EXECUTED
            or self.job is not ExecutionStatus.NOT_EXECUTED
            or self.event is not ExecutionStatus.NOT_EXECUTED
            or self.live_eligible is not False
            or self.decision is not NormalizationDecision.NOT_READY
            or type(self.empty_identity_interpretation) is not str
            or self.empty_identity_interpretation
            != "NO_IDENTITY_OR_GROUPING_DECISION_NOT_ZERO_CONFIDENCE"
        ):
            fail_catalog_normalization()


def _source(command: CatalogNormalizationCommand) -> CatalogSourceReference:
    page = command.search_result.page
    receipt = page.raw_artifact
    return CatalogSourceReference(
        provider=page.provider,
        api_version=page.api_version,
        endpoint_id=command.search_command.endpoint_id,
        command_fingerprint=command.search_command.fingerprint,
        request_sha256=page.request_sha256,
        raw_artifact_id=receipt.artifact_id,
        raw_sha256=receipt.sha256,
        raw_byte_size=receipt.byte_size,
        observed_at=page.observed_at,
        ingested_at=command.ingested_at,
        source_snapshot_id=None,
        source_snapshot_status=SourceSnapshotStatus.NOT_AVAILABLE,
        confidence=None,
        confidence_status=SourceConfidenceStatus.SOURCE_ABSENT,
        validation_status=SourceValidationStatus.VALIDATED_RECORDED_RECEIPT_ONLY,
        persistence_executed=False,
        repository=RepositoryBoundary.ABSENT,
        database=ExecutionStatus.NOT_EXECUTED,
    )


def lossless_batch_from_command(
    command: CatalogNormalizationCommand,
) -> CatalogNormalizationBatch:
    """Create a deterministic structural projection without identity inference."""
    if type(command) is not CatalogNormalizationCommand:
        fail_catalog_normalization()
    source = _source(command)
    items = command.search_result.page.items
    candidates = tuple(
        CatalogCandidateDraft(
            ordinal=index,
            external_item_code=item.item_code,
            external_genre_id=item.genre_id,
            display_name=item.item_name,
            normalized_name=item.item_name,
            name_normalization=NameNormalization.LOSSLESS_PASSTHROUGH,
            image_urls=item.image_urls,
            provider_updated_at=item.provider_updated_at,
            observed_at=item.observed_at,
            source=source,
            candidate_id=None,
            product_id=None,
            shop_id=None,
            genre_id=None,
            model_number=None,
            jan_code=None,
            status=None,
            confidence=None,
            identity_decision=None,
            grouping_keys=(),
        )
        for index, item in enumerate(items, start=1)
    )
    offers = tuple(
        OfferDraft(
            ordinal=index,
            external_item_code=item.item_code,
            endpoint_id=command.search_command.endpoint_id,
            item_url=item.item_url,
            observed_at=item.observed_at,
            source=source,
            offer_id=None,
            product_id=None,
            shop_id=None,
            external_offer_id=None,
            status=None,
            price=None,
            currency=None,
            shipping=None,
            points=None,
            affiliate_url=None,
        )
        for index, item in enumerate(items, start=1)
    )
    prices = tuple(
        PriceDraft(
            ordinal=index,
            external_item_code=item.item_code,
            amount_jpy=item.item_price_jpy,
            observed_at=item.observed_at,
            source=source,
            tax_included=None,
            shipping=None,
            points=None,
            status=None,
            confidence=None,
        )
        for index, item in enumerate(items, start=1)
    )
    availabilities = tuple(
        AvailabilityDraft(
            ordinal=index,
            external_item_code=item.item_code,
            provider_value=item.availability,
            observed_at=item.observed_at,
            source=source,
            semantic_status=None,
            status=None,
            confidence=None,
        )
        for index, item in enumerate(items, start=1)
    )
    review_aggregates = tuple(
        ReviewAggregateDraft(
            ordinal=index,
            external_item_code=item.item_code,
            review_count=item.review_count,
            review_average=item.review_average,
            observed_at=item.observed_at,
            source=source,
            review_body=None,
            status=None,
            confidence=None,
        )
        for index, item in enumerate(items, start=1)
    )
    return CatalogNormalizationBatch(
        command_fingerprint=command.fingerprint,
        ingestion_request_id=command.ingestion_request_id,
        mode=NormalizationMode.RECORDED_TEST_ONLY,
        scope=NormalizationScope.LOSSLESS_STRUCTURAL_ONLY,
        candidates=candidates,
        offers=offers,
        prices=prices,
        availabilities=availabilities,
        review_aggregates=review_aggregates,
        identity_status=IdentityStatus.REVIEW_REQUIRED,
        confidence=None,
        confidence_status=SourceConfidenceStatus.SOURCE_ABSENT,
        canonical_products=(),
        grouping_decisions=(),
        identity_decisions=(),
        memberships=(),
        merges=(),
        splits=(),
        repository=RepositoryBoundary.ABSENT,
        persistence_executed=False,
        database=ExecutionStatus.NOT_EXECUTED,
        job=ExecutionStatus.NOT_EXECUTED,
        event=ExecutionStatus.NOT_EXECUTED,
        live_eligible=False,
        decision=NormalizationDecision.NOT_READY,
        empty_identity_interpretation=(
            "NO_IDENTITY_OR_GROUPING_DECISION_NOT_ZERO_CONFIDENCE"
        ),
    )


__all__ = [
    "AvailabilityDraft",
    "CatalogCandidateDraft",
    "CatalogNormalizationBatch",
    "CatalogNormalizationCommand",
    "CatalogNormalizationFailure",
    "CatalogNormalizationFailureCode",
    "CatalogNormalizer",
    "CatalogSourceReference",
    "ExecutionStatus",
    "IdentityStatus",
    "NameNormalization",
    "NormalizationDecision",
    "NormalizationMode",
    "NormalizationScope",
    "OfferDraft",
    "PriceDraft",
    "RepositoryBoundary",
    "ReviewAggregateDraft",
    "SourceConfidenceStatus",
    "SourceSnapshotStatus",
    "SourceValidationStatus",
    "fail_catalog_normalization",
    "lossless_batch_from_command",
]
