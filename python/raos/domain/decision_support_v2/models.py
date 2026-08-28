"""Versioned value objects for the RAOS V2 carry-on vertical slice.

The objects deliberately contain neither network clients nor publication authority.
Decimal inputs reject binary floats so edge comparisons remain exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Mapping, cast
from urllib.parse import urlsplit


SCHEMA_VERSION = "2.0.0"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_SOURCE_ID = re.compile(r"SRC-[A-Z0-9][A-Z0-9-]{0,127}\Z")
_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9-]+\Z")
_VARIANT_ID = re.compile(r"[A-Z0-9][A-Z0-9-]{0,127}\Z")
_FEATURE_ID = re.compile(r"[A-Z][A-Z0-9_-]{0,63}\Z")
_CLAIM_ID = re.compile(r"CLM-[A-Z0-9-]+\Z")
_MACHINE_SUBJECT_ID = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,127}\Z")
_PREDICATE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


def exact_decimal(value: Decimal | str | int) -> Decimal:
    """Return a finite exact Decimal and reject float coercion."""

    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("decimal values must be Decimal, str, or int")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal value") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("decimal value must be finite and non-negative")
    return result


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_instance(value: object, expected_type: type[object], message: str) -> None:
    """Keep runtime validation at typed dataclass construction boundaries."""

    if not isinstance(value, expected_type):
        raise ValueError(message)


def _string_object_mapping(value: object, message: str) -> dict[str, object]:
    """Validate an untyped JSON object before exposing string-keyed values."""

    if not isinstance(value, Mapping):
        raise ValueError(message)
    raw = cast(Mapping[object, object], value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError(message)
        result[key] = item
    return result


def _empty_string_mapping() -> dict[str, str]:
    return {}


class ClaimType(StrEnum):
    A_OFFICIAL_FACT = "A_OFFICIAL_FACT"
    D_EDITORIAL_JUDGEMENT = "D_EDITORIAL_JUDGEMENT"
    UNKNOWN = "UNKNOWN"


class SourceClass(StrEnum):
    MANUFACTURER_PRIMARY = "MANUFACTURER_PRIMARY"
    AIRLINE_PRIMARY = "AIRLINE_PRIMARY"
    GOVERNMENT_PRIMARY = "GOVERNMENT_PRIMARY"
    RAKUTEN_PERMITTED_DATA = "RAKUTEN_PERMITTED_DATA"
    COMPETITOR_UX_ONLY = "COMPETITOR_UX_ONLY"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    DUE = "DUE"
    SOFT_STALE = "SOFT_STALE"
    HARD_STALE = "HARD_STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    REJECTED = "REJECTED"


class RiskClass(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClaimStatus(StrEnum):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    BLOCKED = "BLOCKED"


class IdentityStatus(StrEnum):
    EXACT = "EXACT"
    AMBIGUOUS = "AMBIGUOUS"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class OfferStatus(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    IDENTITY_BLOCKED = "IDENTITY_BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class CtaState(StrEnum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class MediaState(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NO_IMAGE_INTENTIONAL = "NO_IMAGE_INTENTIONAL"
    BLOCKED = "BLOCKED"


class DimensionOrientation(StrEnum):
    ORDERED = "ORDERED"
    PERMUTABLE = "PERMUTABLE"


class ItemPlacement(StrEnum):
    MAIN = "MAIN"
    UNDERSEAT = "UNDERSEAT"
    OVERHEAD = "OVERHEAD"


class JourneyScope(StrEnum):
    DOMESTIC = "DOMESTIC"
    INTERNATIONAL = "INTERNATIONAL"
    ALL = "ALL"


class DecisionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    BLOCKED = "BLOCKED"
    NO_MATCH = "NO_MATCH"


class CaptureMode(StrEnum):
    PUBLIC_READ_ONLY = "PUBLIC_READ_ONLY"
    RECORDED_FIXTURE = "RECORDED_FIXTURE"
    OWNER_SUPPLIED = "OWNER_SUPPLIED"


@dataclass(frozen=True, slots=True)
class CaptureProvenance:
    mode: CaptureMode
    captured_at: datetime

    def __post_init__(self) -> None:
        _require_instance(self.mode, CaptureMode, "invalid capture mode")
        _aware(self.captured_at, "captured_at")


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    source_class: SourceClass
    publisher: str
    title: str
    canonical_url: str
    published_at: datetime | None
    checked_at: datetime
    effective_from: datetime | None
    effective_to: datetime | None
    content_sha256: str
    next_review_at: datetime
    capture_provenance: CaptureProvenance
    status: FreshnessState = FreshnessState.FRESH

    def __post_init__(self) -> None:
        _require_instance(
            self.capture_provenance,
            CaptureProvenance,
            "invalid source capture provenance",
        )
        _require_instance(self.status, FreshnessState, "invalid source status")
        if not _MACHINE_SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("invalid source ID")
        if not self.publisher.strip() or not self.title.strip():
            raise ValueError("source publisher and title are required")
        try:
            parsed = urlsplit(self.canonical_url)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("source URL authority is invalid") from exc
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise ValueError("source URL must be public HTTPS")
        if parsed.query or parsed.fragment:
            raise ValueError("source URL query and fragment are forbidden")
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("invalid source content hash")
        _aware(self.checked_at, "checked_at")
        _aware(self.next_review_at, "next_review_at")
        if self.published_at is not None:
            _aware(self.published_at, "published_at")
        if self.next_review_at <= self.checked_at:
            raise ValueError("next review must be after checked_at")
        if self.capture_provenance.captured_at > self.checked_at:
            raise ValueError("source cannot be checked before capture")
        if self.effective_from is not None:
            _aware(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _aware(self.effective_to, "effective_to")
        if self.effective_from and self.effective_to:
            if self.effective_to <= self.effective_from:
                raise ValueError("invalid source effective interval")

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema_version": "1.0.0",
            "source_id": self.source_id,
            "source_class": self.source_class.value,
            "publisher": self.publisher,
            "title": self.title,
            "canonical_url": self.canonical_url,
            "published_at": (
                self.published_at.isoformat() if self.published_at is not None else None
            ),
            "effective_from": (
                self.effective_from.isoformat()
                if self.effective_from is not None
                else None
            ),
            "effective_to": (
                self.effective_to.isoformat() if self.effective_to is not None else None
            ),
            "checked_at": self.checked_at.isoformat(),
            "next_review_at": self.next_review_at.isoformat(),
            "content_sha256": self.content_sha256,
            "capture_provenance": {
                "mode": self.capture_provenance.mode.value,
                "captured_at": self.capture_provenance.captured_at.isoformat(),
            },
            "status": self.status.value,
        }

    @classmethod
    def from_contract_record(cls, value: Mapping[str, object]) -> SourceRecord:
        """Strictly map a source-record contract into the runtime value object."""

        expected = {
            "schema_version",
            "source_id",
            "source_class",
            "publisher",
            "title",
            "canonical_url",
            "published_at",
            "effective_from",
            "effective_to",
            "checked_at",
            "next_review_at",
            "content_sha256",
            "capture_provenance",
            "status",
        }
        if set(value) != expected or value.get("schema_version") != "1.0.0":
            raise ValueError("invalid source record fields")
        provenance = _string_object_mapping(
            value["capture_provenance"], "invalid capture provenance"
        )
        if set(provenance) != {
            "mode",
            "captured_at",
        }:
            raise ValueError("invalid capture provenance")

        def parse_time(
            raw: object, name: str, *, optional: bool = False
        ) -> datetime | None:
            if raw is None and optional:
                return None
            if not isinstance(raw, str):
                raise ValueError(f"invalid {name}")
            try:
                parsed_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"invalid {name}") from exc
            _aware(parsed_time, name)
            return parsed_time

        string_names = (
            "source_id",
            "source_class",
            "publisher",
            "title",
            "canonical_url",
            "content_sha256",
            "status",
        )
        if any(not isinstance(value[name], str) for name in string_names):
            raise ValueError("invalid source record field type")
        if not isinstance(provenance["mode"], str):
            raise ValueError("invalid capture mode")
        captured_at = parse_time(provenance["captured_at"], "captured_at")
        checked_at = parse_time(value["checked_at"], "checked_at")
        next_review_at = parse_time(value["next_review_at"], "next_review_at")
        assert captured_at is not None
        assert checked_at is not None
        assert next_review_at is not None
        return cls(
            source_id=str(value["source_id"]),
            source_class=SourceClass(str(value["source_class"])),
            publisher=str(value["publisher"]),
            title=str(value["title"]),
            canonical_url=str(value["canonical_url"]),
            published_at=parse_time(
                value["published_at"], "published_at", optional=True
            ),
            effective_from=parse_time(
                value["effective_from"], "effective_from", optional=True
            ),
            effective_to=parse_time(
                value["effective_to"], "effective_to", optional=True
            ),
            checked_at=checked_at,
            next_review_at=next_review_at,
            content_sha256=str(value["content_sha256"]),
            capture_provenance=CaptureProvenance(
                CaptureMode(str(provenance["mode"])), captured_at
            ),
            status=FreshnessState(str(value["status"])),
        )


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    claim_type: ClaimType
    subject_id: str
    predicate: str
    value: str | None
    unit: str | None
    source_ids: tuple[str, ...]
    checked_at: datetime
    next_review_at: datetime
    risk_class: RiskClass
    logic_inputs: Mapping[str, str] = field(default_factory=_empty_string_mapping)
    status: ClaimStatus = ClaimStatus.DRAFT

    def __post_init__(self) -> None:
        if not _CLAIM_ID.fullmatch(self.claim_id):
            raise ValueError("invalid claim ID")
        if not _MACHINE_SUBJECT_ID.fullmatch(self.subject_id):
            raise ValueError("invalid claim subject ID")
        if not _PREDICATE.fullmatch(self.predicate):
            raise ValueError("invalid claim predicate")
        if any(
            not _MACHINE_SOURCE_ID.fullmatch(source_id) for source_id in self.source_ids
        ) or len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("invalid or duplicate claim source")
        if any(
            not _FEATURE_ID.fullmatch(input_id)
            or not _MACHINE_SUBJECT_ID.fullmatch(value_ref)
            for input_id, value_ref in self.logic_inputs.items()
        ):
            raise ValueError("invalid claim logic input")
        _aware(self.checked_at, "checked_at")
        _aware(self.next_review_at, "next_review_at")
        if self.next_review_at <= self.checked_at:
            raise ValueError("next review must be after checked_at")
        if self.claim_type is ClaimType.UNKNOWN and (
            self.value is not None or self.unit is not None
        ):
            raise ValueError("UNKNOWN claim cannot contain value or unit")
        if self.claim_type is ClaimType.A_OFFICIAL_FACT and self.value is None:
            raise ValueError("official fact requires a value")
        if self.claim_type is ClaimType.A_OFFICIAL_FACT and not self.source_ids:
            raise ValueError("official fact requires a source")
        if self.claim_type is ClaimType.D_EDITORIAL_JUDGEMENT and not self.logic_inputs:
            raise ValueError("editorial judgement requires reproducible inputs")
        if self.claim_type is ClaimType.UNKNOWN and self.status not in {
            ClaimStatus.DRAFT,
            ClaimStatus.BLOCKED,
        }:
            raise ValueError("UNKNOWN claim cannot be verified or stale")

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema_version": "1.0.0",
            "claim_id": self.claim_id,
            "claim_type": self.claim_type.value,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "value": self.value,
            "unit": self.unit,
            "source_ids": list(self.source_ids),
            "logic_inputs": [
                {"input_id": input_id, "value_ref": value_ref}
                for input_id, value_ref in sorted(self.logic_inputs.items())
            ],
            "checked_at": self.checked_at.isoformat(),
            "next_review_at": self.next_review_at.isoformat(),
            "risk_class": self.risk_class.value,
            "status": self.status.value,
        }

    def validate_sources(self, sources: Mapping[str, SourceRecord]) -> None:
        if self.claim_type is ClaimType.UNKNOWN:
            if self.value is not None:
                raise ValueError("UNKNOWN claim cannot contain a value")
            return
        if self.claim_type is ClaimType.A_OFFICIAL_FACT:
            if not self.source_ids:
                raise ValueError("official fact requires a source")
            allowed = {
                SourceClass.MANUFACTURER_PRIMARY,
                SourceClass.AIRLINE_PRIMARY,
                SourceClass.GOVERNMENT_PRIMARY,
                SourceClass.RAKUTEN_PERMITTED_DATA,
            }
            if any(
                source_id not in sources
                or sources[source_id].source_class not in allowed
                for source_id in self.source_ids
            ):
                raise ValueError("official fact has an ineligible source")
        if self.claim_type is ClaimType.D_EDITORIAL_JUDGEMENT:
            if not self.logic_inputs:
                raise ValueError("editorial judgement requires reproducible inputs")


@dataclass(frozen=True, slots=True)
class DimensionEdges:
    height_cm: Decimal
    width_cm: Decimal
    depth_cm: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "height_cm", exact_decimal(self.height_cm))
        object.__setattr__(self, "width_cm", exact_decimal(self.width_cm))
        object.__setattr__(self, "depth_cm", exact_decimal(self.depth_cm))
        if any(value == 0 for value in self.as_tuple()):
            raise ValueError("dimension edges must be greater than zero")

    def as_tuple(self) -> tuple[Decimal, Decimal, Decimal]:
        return self.height_cm, self.width_cm, self.depth_cm

    @property
    def sum_cm(self) -> Decimal:
        return sum(self.as_tuple(), Decimal(0))


@dataclass(frozen=True, slots=True)
class ProductVariant:
    variant_id: str
    external_dimensions_cm: DimensionEdges
    expanded_dimensions_cm: DimensionEdges | None
    mass_kg: Decimal
    capacity_l: Decimal
    expanded_capacity_l: Decimal | None
    declared_features: tuple[str, ...]
    unknown_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _VARIANT_ID.fullmatch(self.variant_id):
            raise ValueError("invalid product variant ID")
        object.__setattr__(self, "mass_kg", exact_decimal(self.mass_kg))
        object.__setattr__(self, "capacity_l", exact_decimal(self.capacity_l))
        if self.mass_kg == 0 or self.capacity_l == 0:
            raise ValueError("product mass and capacity must be positive")
        if self.expanded_capacity_l is not None:
            object.__setattr__(
                self, "expanded_capacity_l", exact_decimal(self.expanded_capacity_l)
            )
            if self.expanded_capacity_l == 0:
                raise ValueError("expanded capacity must be positive")
        fields = self.declared_features + self.unknown_fields
        if any(not _FEATURE_ID.fullmatch(value) for value in fields):
            raise ValueError("invalid product feature field")
        if len(set(self.declared_features)) != len(self.declared_features) or len(
            set(self.unknown_fields)
        ) != len(self.unknown_fields):
            raise ValueError("duplicate product feature field")


@dataclass(frozen=True, slots=True)
class ProductModel:
    product_id: str
    manufacturer: str
    brand: str
    model_name: str
    model_number: str
    generation: str
    variants: tuple[ProductVariant, ...]
    official_source_ids: tuple[str, ...]
    identity_status: IdentityStatus

    def __post_init__(self) -> None:
        if not _PRODUCT_ID.fullmatch(self.product_id):
            raise ValueError("invalid product ID")
        if (
            any(
                not value.strip()
                for value in (
                    self.manufacturer,
                    self.brand,
                    self.model_name,
                    self.model_number,
                    self.generation,
                )
            )
            or not self.variants
        ):
            raise ValueError("product model needs model number and variant")
        if not self.official_source_ids or any(
            not _MACHINE_SOURCE_ID.fullmatch(source_id)
            for source_id in self.official_source_ids
        ):
            raise ValueError("product model needs valid official sources")
        if len(set(self.official_source_ids)) != len(self.official_source_ids):
            raise ValueError("duplicate official product source")
        if len({variant.variant_id for variant in self.variants}) != len(self.variants):
            raise ValueError("duplicate product variant")


@dataclass(frozen=True, slots=True)
class OfferObservation:
    offer_id: str
    product_id: str
    provider: str
    item_code: str | None
    shop_code: str | None
    observed_at: datetime
    affiliate_url_ref: str | None
    image_ref: str | None
    identity_evidence: tuple[str, ...]
    status: OfferStatus
    display_price_jpy: Decimal | None = None
    in_stock: bool | None = None

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        if self.display_price_jpy is not None:
            object.__setattr__(
                self, "display_price_jpy", exact_decimal(self.display_price_jpy)
            )
            if self.display_price_jpy == 0:
                raise ValueError("display price must be positive")


def cta_state_for_offer(
    product: ProductModel,
    offer: OfferObservation,
    *,
    media_state: MediaState,
    evaluated_at: datetime,
) -> CtaState:
    """Return CTA eligibility only when the media decision is explicit and safe.

    A missing image is allowed only as an intentional neutral-placeholder choice.
    A present image requires a separately validated provenance binding.  This makes
    an unbound or modified image fail closed for both rendering and the CTA.
    """

    _aware(evaluated_at, "evaluated_at")
    if evaluated_at < offer.observed_at:
        return CtaState.BLOCKED
    if offer.product_id != product.product_id:
        return CtaState.BLOCKED
    if product.identity_status is not IdentityStatus.EXACT:
        return CtaState.BLOCKED
    if offer.status is OfferStatus.IDENTITY_BLOCKED:
        return CtaState.BLOCKED
    if "EXACT" not in offer.identity_evidence:
        return CtaState.BLOCKED
    if media_state is MediaState.BLOCKED:
        return CtaState.BLOCKED
    if offer.image_ref is None:
        if media_state is not MediaState.NO_IMAGE_INTENTIONAL:
            return CtaState.BLOCKED
    elif media_state is not MediaState.ELIGIBLE:
        return CtaState.BLOCKED
    if (
        offer.status is not OfferStatus.CURRENT
        or evaluated_at >= offer.observed_at + timedelta(hours=24)
        or offer.in_stock is not True
        or not offer.affiliate_url_ref
        or not offer.item_code
        or not offer.shop_code
    ):
        return CtaState.UNAVAILABLE
    return CtaState.AVAILABLE


@dataclass(frozen=True, slots=True)
class RuleApplicability:
    carrier: str
    operator: str | None = None
    min_seat_count: int | None = None
    max_seat_count: int | None = None
    fare_classes: tuple[str, ...] = ()
    required_options: tuple[str, ...] = ()
    forbidden_options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.carrier.strip():
            raise ValueError("carrier cannot be blank")
        if self.min_seat_count is not None and self.min_seat_count < 1:
            raise ValueError("invalid minimum seat count")
        if self.max_seat_count is not None and self.max_seat_count < 1:
            raise ValueError("invalid maximum seat count")
        if self.min_seat_count and self.max_seat_count:
            if self.min_seat_count > self.max_seat_count:
                raise ValueError("invalid seat count interval")


@dataclass(frozen=True, slots=True)
class AirlineRuleVariant:
    variant_id: str
    applicability: RuleApplicability
    carry_on_bag_count: int
    personal_item_count: int
    dimension_edges_cm: DimensionEdges
    sum_edges_cm: Decimal | None
    total_weight_kg: Decimal | None
    orientation: DimensionOrientation
    appendages_included: bool
    max_per_item_weight_kg: Decimal | None = None
    item_allowances: tuple[ItemAllowance, ...] = ()
    notes: tuple[str, ...] = ()
    resolution_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.carry_on_bag_count < 0 or self.personal_item_count < 0:
            raise ValueError("bag counts cannot be negative")
        if self.total_weight_kg is not None:
            object.__setattr__(
                self, "total_weight_kg", exact_decimal(self.total_weight_kg)
            )
            if self.total_weight_kg == 0:
                raise ValueError("rule total weight must be greater than zero")
        if self.sum_edges_cm is not None:
            object.__setattr__(self, "sum_edges_cm", exact_decimal(self.sum_edges_cm))
            if self.sum_edges_cm == 0:
                raise ValueError("rule dimension sum must be greater than zero")
        if self.max_per_item_weight_kg is not None:
            object.__setattr__(
                self,
                "max_per_item_weight_kg",
                exact_decimal(self.max_per_item_weight_kg),
            )
            if self.max_per_item_weight_kg == 0:
                raise ValueError("per-item weight must be greater than zero")
        if len({item.slot_id for item in self.item_allowances}) != len(
            self.item_allowances
        ):
            raise ValueError("duplicate item allowance slot")
        if self.item_allowances:
            carry_slots = sum(
                item.placement in {ItemPlacement.MAIN, ItemPlacement.OVERHEAD}
                for item in self.item_allowances
            )
            personal_slots = sum(
                item.placement is ItemPlacement.UNDERSEAT
                for item in self.item_allowances
            )
            if (
                self.carry_on_bag_count != carry_slots
                or self.personal_item_count != personal_slots
            ):
                raise ValueError("item allowance roles must match declared count caps")


@dataclass(frozen=True, slots=True)
class ItemAllowance:
    slot_id: str
    placement: ItemPlacement
    dimension_edges_cm: DimensionEdges | None
    orientation: DimensionOrientation
    includes_wheels_and_handles: bool | None
    max_weight_kg: Decimal | None
    fit_requirement: str | None = None

    def __post_init__(self) -> None:
        if not self.slot_id:
            raise ValueError("item allowance slot ID is required")
        if self.max_weight_kg is not None:
            object.__setattr__(self, "max_weight_kg", exact_decimal(self.max_weight_kg))
            if self.max_weight_kg == 0:
                raise ValueError("item allowance weight must be positive")
        if self.fit_requirement not in {None, "UNDERSEAT"}:
            raise ValueError("unsupported fit requirement")


@dataclass(frozen=True, slots=True)
class AirlineRuleSet:
    rule_set_id: str
    carrier: str
    journey_scope: JourneyScope
    effective_from: datetime | None
    observed_applicable_from: datetime
    applicability_basis: str
    effective_interval_semantics: str
    effective_to: datetime | None
    variants: tuple[AirlineRuleVariant, ...]
    source_id: str
    checked_at: datetime
    source_next_review_at: datetime
    source_content_sha256: str
    recheck_required_before_use: bool
    source_status: FreshnessState = FreshnessState.FRESH

    def __post_init__(self) -> None:
        _require_instance(
            self.journey_scope, JourneyScope, "invalid airline journey scope"
        )
        if not _MACHINE_SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("invalid airline source ID")
        _require_instance(
            self.source_status, FreshnessState, "invalid airline source status"
        )
        if self.effective_from is not None:
            _aware(self.effective_from, "effective_from")
        _aware(self.observed_applicable_from, "observed_applicable_from")
        if self.applicability_basis not in {
            "OBSERVED_CURRENT_AT_CAPTURE_NO_PUBLISHED_EFFECTIVE_DATE",
            "OFFICIAL_EFFECTIVE_DATE",
        }:
            raise ValueError("invalid applicability basis")
        if self.effective_interval_semantics != "FROM_INCLUSIVE_TO_EXCLUSIVE":
            raise ValueError("effective interval must be half-open")
        if (
            self.applicability_basis == "OFFICIAL_EFFECTIVE_DATE"
            and self.effective_from is None
        ):
            raise ValueError("official effective date is required")
        _aware(self.checked_at, "checked_at")
        _aware(self.source_next_review_at, "source_next_review_at")
        if self.source_next_review_at <= self.checked_at:
            raise ValueError("source next review must follow checked_at")
        if not _SHA256.fullmatch(self.source_content_sha256):
            raise ValueError("invalid airline source content hash")
        _require_instance(
            self.recheck_required_before_use,
            bool,
            "recheck flag must be boolean",
        )
        if self.effective_to is not None:
            _aware(self.effective_to, "effective_to")
            lower = self.effective_from or self.observed_applicable_from
            if self.effective_to <= lower:
                raise ValueError("invalid rule effective interval")
        if not self.variants:
            raise ValueError("rule set needs a variant")


@dataclass(frozen=True, slots=True)
class JourneySegment:
    segment_id: str
    carrier: str | None
    departure_at: datetime
    journey_scope: JourneyScope | None = None
    operator: str | None = None
    seat_count: int | None = None
    fare_class: str | None = None
    options: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _aware(self.departure_at, "departure_at")
        if self.journey_scope is not None and self.journey_scope not in {
            JourneyScope.DOMESTIC,
            JourneyScope.INTERNATIONAL,
        }:
            raise ValueError("segment journey scope must be domestic or international")


@dataclass(frozen=True, slots=True)
class BagInput:
    external_dimensions_cm: DimensionEdges
    combined_weight_kg: Decimal
    carry_on_bag_count: int = 1
    personal_item_count: int = 1
    item_weights_kg: tuple[Decimal, ...] | None = None
    items: tuple[BagItem, ...] | None = None
    appendages_included: bool | None = None
    expanded: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "combined_weight_kg", exact_decimal(self.combined_weight_kg)
        )
        if self.carry_on_bag_count < 0 or self.personal_item_count < 0:
            raise ValueError("bag counts cannot be negative")
        if self.carry_on_bag_count + self.personal_item_count == 0:
            raise ValueError("at least one bag or personal item is required")
        if self.combined_weight_kg == 0:
            raise ValueError("combined weight must be greater than zero")
        if self.item_weights_kg is not None:
            values = tuple(exact_decimal(value) for value in self.item_weights_kg)
            if len(values) != self.carry_on_bag_count + self.personal_item_count:
                raise ValueError("item weight count does not match bag count")
            if sum(values, Decimal(0)) != self.combined_weight_kg:
                raise ValueError("item weights do not equal combined weight")
            object.__setattr__(self, "item_weights_kg", values)
        if self.items is not None:
            expected = self.carry_on_bag_count + self.personal_item_count
            if len(self.items) != expected:
                raise ValueError("item detail count does not match bag count")
            if sum((item.weight_kg for item in self.items), Decimal(0)) != (
                self.combined_weight_kg
            ):
                raise ValueError("item details do not equal combined weight")
            if self.items[0].external_dimensions_cm != self.external_dimensions_cm:
                raise ValueError(
                    "first item dimensions must match primary bag dimensions"
                )
            if (
                self.item_weights_kg is not None
                and tuple(item.weight_kg for item in self.items) != self.item_weights_kg
            ):
                raise ValueError("item weight inputs conflict")
            if all(item.placement is not None for item in self.items):
                carry_items = sum(
                    item.placement in {ItemPlacement.MAIN, ItemPlacement.OVERHEAD}
                    for item in self.items
                )
                personal_items = sum(
                    item.placement is ItemPlacement.UNDERSEAT for item in self.items
                )
                if (
                    carry_items != self.carry_on_bag_count
                    or personal_items != self.personal_item_count
                ):
                    raise ValueError("item roles do not match declared bag counts")


@dataclass(frozen=True, slots=True)
class BagItem:
    item_id: str
    external_dimensions_cm: DimensionEdges
    weight_kg: Decimal
    appendages_included: bool | None
    confirmed_fit: tuple[str, ...] = ()
    rejected_fit: tuple[str, ...] = ()
    placement: ItemPlacement | None = None

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("bag item ID is required")
        object.__setattr__(self, "weight_kg", exact_decimal(self.weight_kg))
        if self.weight_kg == 0:
            raise ValueError("item weight must be positive")
        if set(self.confirmed_fit) & set(self.rejected_fit):
            raise ValueError("item fit confirmation conflicts")


@dataclass(frozen=True, slots=True)
class SegmentDecision:
    segment_id: str
    status: DecisionStatus
    reason_codes: tuple[str, ...]
    source_ids: tuple[str, ...]
    checked_at: datetime | None
    rule_variant_id: str | None


@dataclass(frozen=True, slots=True)
class DecisionSupport:
    status: DecisionStatus
    segments: tuple[SegmentDecision, ...]
    reason_codes: tuple[str, ...]
    source_ids: tuple[str, ...]
    checked_at: datetime | None
    schema_version: str = SCHEMA_VERSION


__all__ = [
    "AirlineRuleSet",
    "AirlineRuleVariant",
    "BagItem",
    "BagInput",
    "CaptureMode",
    "CaptureProvenance",
    "Claim",
    "ClaimStatus",
    "ClaimType",
    "CtaState",
    "DecisionStatus",
    "DecisionSupport",
    "DimensionEdges",
    "DimensionOrientation",
    "FreshnessState",
    "IdentityStatus",
    "ItemAllowance",
    "ItemPlacement",
    "JourneySegment",
    "JourneyScope",
    "MediaState",
    "OfferObservation",
    "OfferStatus",
    "ProductModel",
    "ProductVariant",
    "RiskClass",
    "RuleApplicability",
    "SCHEMA_VERSION",
    "SegmentDecision",
    "SourceClass",
    "SourceRecord",
    "cta_state_for_offer",
    "exact_decimal",
]
