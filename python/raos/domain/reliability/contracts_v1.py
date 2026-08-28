"""Strict contracts for the reliability-first product research bounded context V1.

The contracts are deliberately provider-neutral and contain no publication or
approval authority.  Provider bodies, review text, credentials, affiliate
rates, points and coupon material have no representation in these schemas.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


ARTICLE_ID: Final[Literal["raos-reliability-suitcase-pilot-001"]] = (
    "raos-reliability-suitcase-pilot-001"
)
SCHEMA_VERSION: Final[Literal["1.0.0"]] = "1.0.0"
REVIEW_RETENTION_MONTHS: Final[Literal[13]] = 13
PROVIDER_OFFER_LIMIT: Final[Literal[3000]] = 3_000

Sha256Text = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ArtifactId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")]
SourceId = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_-]{2,79}$")]
ProductIdText = Annotated[
    str,
    Field(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
    ),
]
Score = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))]


class StrictContractV1(BaseModel):
    """Closed, immutable base for public V1 JSON artifacts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class SourceDecisionV1(StrEnum):
    ALLOW_STRUCTURED_FIELDS = "ALLOW_STRUCTURED_FIELDS"
    ALLOW_AGGREGATE_ONLY = "ALLOW_AGGREGATE_ONLY"
    ALLOW_DERIVED_THEMES = "ALLOW_DERIVED_THEMES"
    LINK_ONLY = "LINK_ONLY"
    PROHIBITED = "PROHIBITED"
    UNKNOWN = "UNKNOWN"


class AcquisitionMethodV1(StrEnum):
    JSON_API = "JSON_API"
    EXACT_URL_HTML = "EXACT_URL_HTML"
    TRANSIENT_REVIEW_BODY = "TRANSIENT_REVIEW_BODY"
    DISABLED = "DISABLED"


class IdentityConfidenceV1(StrEnum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    UNRESOLVED = "UNRESOLVED"


class CandidateDecisionCodeV1(StrEnum):
    INCLUDED = "INCLUDED"
    ACCESSORY = "ACCESSORY"
    BUNDLE = "BUNDLE"
    PARALLEL_IMPORT = "PARALLEL_IMPORT"
    USED = "USED"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    VARIANT_AMBIGUOUS = "VARIANT_AMBIGUOUS"
    HARD_CONSTRAINT_FAILED = "HARD_CONSTRAINT_FAILED"


class SafetyStateV1(StrEnum):
    CLEAR = "CLEAR"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    ACTIVE_RECALL = "ACTIVE_RECALL"
    NOT_CHECKED = "NOT_CHECKED"


class VerificationStateV1(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class ReviewEvidenceStatusV1(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class ThemeSeverityV1(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskLevelV1(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class ConfidenceGradeV1(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class RecommendationStatusV1(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    CONDITIONAL = "CONDITIONAL"
    WATCH = "WATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EXCLUDED = "EXCLUDED"


class ReviewDecisionActionV1(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ArtifactRefV1(StrictContractV1):
    artifact_type: str = Field(min_length=3, max_length=100)
    artifact_id: ArtifactId
    content_sha256: Sha256Text
    byte_size: int = Field(ge=2, le=16_777_216)


class RecommendationProfileV1(StrictContractV1):
    profile_id: Literal["LIGHTWEIGHT", "CAPACITY", "ACCESS"]
    weight_weight: int = Field(ge=0, le=100)
    capacity_weight: int = Field(ge=0, le=100)
    access_weight: int = Field(ge=0, le=100)
    support_weight: int = Field(ge=0, le=100)
    price_weight: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self) -> RecommendationProfileV1:
        if (
            self.weight_weight
            + self.capacity_weight
            + self.access_weight
            + self.support_weight
            + self.price_weight
            != 100
        ):
            raise ValueError("INVALID_PROFILE_WEIGHT_TOTAL")
        if self.price_weight != 25:
            raise ValueError("INVALID_PRICE_WEIGHT")
        return self


class ResearchPlanV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    market_country: Literal["JP"] = "JP"
    category_code: Literal["CARRY_ON_SUITCASE"] = "CARRY_ON_SUITCASE"
    queries: tuple[str, ...] = (
        "機内持ち込み スーツケース",
        "機内持ち込み キャリーケース",
    )
    provider_offer_limit: Literal[3000] = PROVIDER_OFFER_LIMIT
    allowed_sale_condition: Literal["NEW_DOMESTIC_REGULAR"] = (
        "NEW_DOMESTIC_REGULAR"
    )
    maximum_height_cm: Decimal = Decimal("55")
    maximum_width_cm: Decimal = Decimal("40")
    maximum_depth_cm: Decimal = Decimal("25")
    maximum_linear_cm: Decimal = Decimal("115")
    price_freshness_hours: Literal[24] = 24
    review_freshness_days: Literal[30] = 30
    profiles: tuple[RecommendationProfileV1, ...]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_fixed_scope(self) -> ResearchPlanV1:
        if self.queries != (
            "機内持ち込み スーツケース",
            "機内持ち込み キャリーケース",
        ):
            raise ValueError("INVALID_RESEARCH_QUERY_SET")
        if tuple(profile.profile_id for profile in self.profiles) != (
            "LIGHTWEIGHT",
            "CAPACITY",
            "ACCESS",
        ):
            raise ValueError("INVALID_PROFILE_SET")
        return self


class SourceRuleV1(StrictContractV1):
    source_id: SourceId
    decision: SourceDecisionV1
    acquisition_method: AcquisitionMethodV1
    allowed_hosts: tuple[str, ...]
    allowed_path_prefixes: tuple[str, ...]
    allowed_exact_urls: tuple[str, ...]
    allowed_fields: tuple[str, ...]
    raw_body_storage_allowed: bool
    quotation_storage_allowed: bool
    derived_storage_allowed: bool
    terms_checked_by: str | None = Field(default=None, max_length=120)
    terms_checked_at: AwareDatetime | None = None
    credential_ref: str | None = Field(default=None, max_length=256)
    minimum_request_interval_ms: int = Field(ge=0, le=60_000)
    freshness_hours: int = Field(ge=1, le=8_760)
    retention_months: int = Field(ge=0, le=120)

    @model_validator(mode="after")
    def validate_permission_shape(self) -> SourceRuleV1:
        blocked = {SourceDecisionV1.PROHIBITED, SourceDecisionV1.UNKNOWN}
        if self.decision in blocked and self.acquisition_method is not AcquisitionMethodV1.DISABLED:
            raise ValueError("BLOCKED_SOURCE_MUST_BE_DISABLED")
        if self.decision in blocked and self.credential_ref is not None:
            raise ValueError("BLOCKED_SOURCE_HAS_CREDENTIAL")
        if (
            self.acquisition_method is AcquisitionMethodV1.EXACT_URL_HTML
            and not self.allowed_exact_urls
        ):
            raise ValueError("EXACT_URL_ALLOWLIST_REQUIRED")
        if (
            self.acquisition_method is not AcquisitionMethodV1.EXACT_URL_HTML
            and self.allowed_exact_urls
        ):
            raise ValueError("EXACT_URL_ALLOWLIST_NOT_APPLICABLE")
        if self.raw_body_storage_allowed or self.quotation_storage_allowed:
            raise ValueError("RAW_OR_QUOTE_STORAGE_FORBIDDEN")
        if self.decision is SourceDecisionV1.ALLOW_DERIVED_THEMES:
            if not self.derived_storage_allowed:
                raise ValueError("DERIVED_THEME_STORAGE_REQUIRED")
            if self.retention_months != REVIEW_RETENTION_MONTHS:
                raise ValueError("INVALID_REVIEW_RETENTION")
        return self


class SourcePolicyV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    policy_profile: Literal["TRUST_SELECTION_CLAIM_EVIDENCE_V1"] = (
        "TRUST_SELECTION_CLAIM_EVIDENCE_V1"
    )
    rules: tuple[SourceRuleV1, ...]
    review_body_retention_months: Literal[0] = 0
    review_derived_retention_months: Literal[13] = REVIEW_RETENTION_MONTHS
    affiliate_inputs_allowed: Literal[False] = False
    points_inputs_allowed: Literal[False] = False
    social_rank_adjustment: Literal[0] = 0
    terms_attestation_days: Literal[90] = 90
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_unique_sources(self) -> SourcePolicyV1:
        identifiers = tuple(rule.source_id for rule in self.rules)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("DUPLICATE_SOURCE_RULE")
        return self

    def rule_for(self, source_id: str) -> SourceRuleV1:
        matches = tuple(rule for rule in self.rules if rule.source_id == source_id)
        if len(matches) != 1:
            raise ValueError("SOURCE_POLICY_UNKNOWN")
        return matches[0]


class DiscoveryOfferV1(StrictContractV1):
    source_id: SourceId
    provider_item_id: str = Field(min_length=1, max_length=300)
    item_url: str = Field(min_length=8, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    jan_gtin: str | None = Field(default=None, pattern=r"^[0-9]{8,14}$")
    brand: str | None = Field(default=None, max_length=120)
    manufacturer_part_number: str | None = Field(default=None, max_length=120)
    variant_label: str | None = Field(default=None, max_length=160)
    displayed_price_jpy: int | None = Field(default=None, ge=1, le=100_000_000)
    review_average: Decimal | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0, le=1_000_000_000)
    observed_at: AwareDatetime


class DiscoveryPageReceiptV1(StrictContractV1):
    source_id: SourceId
    query_index: int = Field(ge=0, le=1)
    page: int = Field(ge=1, le=10_000)
    request_fingerprint: Sha256Text
    response_sha256: Sha256Text
    hit_count: int = Field(ge=0, le=10_000)


class ProviderPageV1(StrictContractV1):
    source_id: SourceId
    query_index: int = Field(ge=0, le=1)
    page: int = Field(ge=1, le=10_000)
    offers: tuple[DiscoveryOfferV1, ...]
    request_fingerprint: Sha256Text
    response_sha256: Sha256Text
    is_last_page: bool


class DiscoveryRunV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    mode: Literal["RECORDED", "LIVE"]
    queries: tuple[str, ...]
    receipts: tuple[DiscoveryPageReceiptV1, ...]
    offers: tuple[DiscoveryOfferV1, ...]
    source_stop_reasons: dict[str, Literal["END_OF_RESULTS", "OFFER_LIMIT"]]
    unique_offer_count_by_source: dict[str, int]
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_limits(self) -> DiscoveryRunV1:
        if any(count > PROVIDER_OFFER_LIMIT for count in self.unique_offer_count_by_source.values()):
            raise ValueError("PROVIDER_OFFER_LIMIT_EXCEEDED")
        keys = tuple((item.source_id, item.provider_item_id) for item in self.offers)
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_DISCOVERY_OFFER")
        return self


class DiscoveryCheckpointV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    mode: Literal["RECORDED", "LIVE"]
    queries: tuple[str, ...]
    receipts: tuple[DiscoveryPageReceiptV1, ...]
    offers: tuple[DiscoveryOfferV1, ...]
    next_pages: dict[str, int]
    ended_searches: tuple[str, ...]
    source_stop_reasons: dict[
        str, Literal["END_OF_RESULTS", "OFFER_LIMIT"]
    ]
    started_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_checkpoint(self) -> DiscoveryCheckpointV1:
        if any(not 1 <= page <= 10_001 for page in self.next_pages.values()):
            raise ValueError("INVALID_CHECKPOINT_PAGE")
        keys = tuple((item.source_id, item.provider_item_id) for item in self.offers)
        if len(keys) != len(set(keys)):
            raise ValueError("DUPLICATE_CHECKPOINT_OFFER")
        return self


class CandidateDecisionV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    product_id: ProductIdText | None
    canonical_product_key: str = Field(min_length=3, max_length=300)
    source_offer_keys: tuple[str, ...]
    identity_evidence_refs: tuple[ArtifactRefV1, ...] = ()
    identity_confidence: IdentityConfidenceV1
    decision: CandidateDecisionCodeV1
    variant_key: str | None = Field(default=None, max_length=300)
    reason_codes: tuple[CandidateDecisionCodeV1, ...]
    decided_at: AwareDatetime


class SafetyObservationV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    product_id: ProductIdText
    state: SafetyStateV1
    source_refs: tuple[ArtifactRefV1, ...]
    model_match_confirmed: bool
    checked_at: AwareDatetime
    expires_at: AwareDatetime


class OfficialPageEvidenceV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    source_id: SourceId
    exact_url: str = Field(min_length=8, max_length=2048)
    body_sha256: Sha256Text
    byte_size: int = Field(ge=1, le=4_194_304)
    content_type: Literal["text/html"] = "text/html"
    captured_at: AwareDatetime
    raw_body_persisted: Literal[False] = False


class ReviewObservationV1(StrictContractV1):
    product_id: ProductIdText
    source_id: SourceId
    category_code: Literal["CARRY_ON_SUITCASE"] = "CARRY_ON_SUITCASE"
    rating_average: Decimal = Field(ge=0, le=5)
    rating_count: int = Field(ge=0, le=1_000_000_000)
    identity_match_confirmed: bool
    anomaly_factor: Decimal = Field(ge=0, le=1)
    verified_purchase: VerificationStateV1
    acquired_at: AwareDatetime


class ReviewContributionV1(StrictContractV1):
    source_id: SourceId
    rating_count: int = Field(ge=0)
    bayesian_rating: Decimal = Field(ge=0, le=5)
    percentile: Score
    final_weight: Decimal = Field(ge=0, le=Decimal("0.5"))
    verified_purchase: VerificationStateV1


class ProductReviewSignalV1(StrictContractV1):
    product_id: ProductIdText
    status: ReviewEvidenceStatusV1
    total_rating_count: int = Field(ge=0)
    review_signal: Score | None
    review_adjustment: Decimal = Field(ge=Decimal("-8"), le=Decimal("5"))
    maximum_percentile_spread: Score | None = None
    structural_anomaly_detected: bool = False
    contributions: tuple[ReviewContributionV1, ...]


class ReviewAggregateSetV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    observations: tuple[ReviewObservationV1, ...]
    signals: tuple[ProductReviewSignalV1, ...]
    bayesian_prior_weight: Literal[50] = 50
    count_cap: Literal[500] = 500
    minimum_domains: Literal[2] = 2
    minimum_total_reviews: Literal[30] = 30
    two_domain_weight: Decimal = Decimal("0.5")
    multi_domain_weight_cap: Decimal = Decimal("0.4")
    acquired_at: AwareDatetime
    expires_at: AwareDatetime


class ReviewThemeV1(StrictContractV1):
    theme_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    severity: ThemeSeverityV1
    matching_observation_count: int = Field(ge=1)
    source_domains: tuple[str, ...]
    identity_match_confirmed: bool
    human_validated: bool


class ReviewThemeSetV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    product_id: ProductIdText
    themes: tuple[ReviewThemeV1, ...]
    eligible_for_article: bool
    raw_body_persisted: Literal[False] = False
    quotations_persisted: Literal[False] = False
    derived_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_article_eligibility(self) -> ReviewThemeSetV1:
        domains = {domain for theme in self.themes for domain in theme.source_domains}
        observations = sum(theme.matching_observation_count for theme in self.themes)
        validated = bool(self.themes) and all(
            theme.human_validated and theme.identity_match_confirmed
            for theme in self.themes
        )
        expected = len(domains) >= 2 and observations >= 5 and validated
        if self.eligible_for_article is not expected:
            raise ValueError("INVALID_THEME_ELIGIBILITY")
        return self


class SocialSignalSetV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    enabled: Literal[False] = False
    status: Literal["DISABLED_BY_SOURCE_POLICY"] = "DISABLED_BY_SOURCE_POLICY"
    direct_rank_adjustment: Literal[0] = 0
    watch_product_ids: tuple[ProductIdText, ...] = ()
    checked_at: AwareDatetime


class OfferPriceV1(StrictContractV1):
    source_id: SourceId
    displayed_price_jpy: int = Field(ge=1, le=100_000_000)
    observed_at: AwareDatetime
    is_new: bool
    is_domestic_regular: bool


class FitCandidateV1(StrictContractV1):
    product_id: ProductIdText
    height_cm: Decimal | None = Field(default=None, gt=0, le=500)
    width_cm: Decimal | None = Field(default=None, gt=0, le=500)
    depth_cm: Decimal | None = Field(default=None, gt=0, le=500)
    body_weight_kg: Decimal | None = Field(default=None, gt=0, le=100)
    base_capacity_l: Decimal | None = Field(default=None, gt=0, le=1_000)
    access_utility: Score
    support_utility: Score
    offers: tuple[OfferPriceV1, ...]


class FitScoreV1(StrictContractV1):
    product_id: ProductIdText
    profile_id: Literal["LIGHTWEIGHT", "CAPACITY", "ACCESS"]
    hard_gate_passed: bool
    fit_score: Score | None
    evidence_coverage: Decimal = Field(ge=0, le=1)
    median_price_jpy: Decimal | None = Field(default=None, ge=1)
    price_current: bool
    reason_codes: tuple[str, ...]


class EvidenceDimensionScoresV1(StrictContractV1):
    identity: int = Field(ge=0, le=2)
    official_information: int = Field(ge=0, le=2)
    safety: int = Field(ge=0, le=2)
    independent_evidence: int = Field(ge=0, le=2)
    review_diversity: int = Field(ge=0, le=2)
    freshness_consistency: int = Field(ge=0, le=2)
    safety_required: bool = False
    unresolved_major_conflict: bool = False
    source_family_count: int = Field(ge=0, le=100)


class TrustedCandidateEvidenceV1(StrictContractV1):
    product_id: ProductIdText
    review_signal: Score | None
    review_adjustment: Decimal = Field(ge=Decimal("-8"), le=Decimal("5"))
    review_status: ReviewEvidenceStatusV1
    maximum_theme_severity: ThemeSeverityV1 | None
    safety_state: SafetyStateV1
    price_current: bool
    support_utility: Score
    evidence_dimensions: EvidenceDimensionScoresV1


class TrustedRecommendationCandidateV1(StrictContractV1):
    product_id: ProductIdText
    fit_score: Score | None
    review_signal: Score | None
    review_adjustment: Decimal = Field(ge=Decimal("-8"), le=Decimal("5"))
    confidence_score: int = Field(ge=0, le=12)
    confidence_grade: ConfidenceGradeV1
    risk_level: RiskLevelV1
    risk_penalty: Decimal = Field(ge=0, le=15)
    internal_rank_score: Decimal | None = Field(default=None, ge=0, le=105)
    recommendation_status: RecommendationStatusV1
    rank: int | None = Field(default=None, ge=1)
    tie_group: int | None = Field(default=None, ge=1)
    reason_codes: tuple[str, ...]


class TrustedRecommendationResultV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    profile_id: Literal["LIGHTWEIGHT", "CAPACITY", "ACCESS"]
    v2_report_sha256: Sha256Text
    methodology_id: Literal["TRUST_SELECTION_RECOMMENDATION_V3"] = (
        "TRUST_SELECTION_RECOMMENDATION_V3"
    )
    candidates: tuple[TrustedRecommendationCandidateV1, ...]
    ranking_order: tuple[ProductIdText, ...]
    calculated_at: AwareDatetime
    publication_authorized: Literal[False] = False
    activation_authorized: Literal[False] = False


class ReviewPacketV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    input_refs: tuple[ArtifactRefV1, ...]
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    override_forbidden_codes: tuple[str, ...]
    summary: dict[str, int | str | bool]
    created_at: AwareDatetime
    publication_authorized: Literal[False] = False


class ReviewDecisionV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    packet_ref: ArtifactRefV1
    action: ReviewDecisionActionV1
    reviewer_ref: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=3, max_length=1000)
    decided_at: AwareDatetime
    publication_authorized: Literal[False] = False


class ArticleEvidenceSnapshotV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    state: Literal["UNPUBLISHED_REVIEW_PACKET"] = "UNPUBLISHED_REVIEW_PACKET"
    evidence_refs: tuple[ArtifactRefV1, ...]
    recommendation_refs: tuple[ArtifactRefV1, ...]
    candidate_count: int = Field(ge=0)
    included_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    disclosure_no_hands_on_test: Literal[True] = True
    disclosure_affiliate_independence: Literal[True] = True
    disclosure_airline_limits_vary: Literal[True] = True
    price_as_of: AwareDatetime | None
    unknown_items: tuple[str, ...]
    created_at: AwareDatetime
    route_created: Literal[False] = False
    wordpress_written: Literal[False] = False
    publication_authorized: Literal[False] = False


class MonitorDiffV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    previous_snapshot_sha256: Sha256Text
    current_snapshot_sha256: Sha256Text
    changed_artifact_types: tuple[str, ...]
    update_required: bool
    required_regeneration_stages: tuple[
        Literal["RECOMMENDATION_V2", "TRUSTED_RECOMMENDATION_V3", "ARTICLE_PACKET"],
        ...,
    ]
    created_at: AwareDatetime
    automatic_publication_action_count: Literal[0] = 0


class MonitoringPolicyV1(StrictContractV1):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    artifact_id: ArtifactId
    article_id: Literal["raos-reliability-suitcase-pilot-001"] = ARTICLE_ID
    safety_hours: Literal[24] = 24
    price_hours: Literal[24] = 24
    availability_hours: Literal[24] = 24
    review_days: Literal[30] = 30
    official_spec_days: Literal[90] = 90
    independent_evidence_days: Literal[365] = 365
    source_terms_days: Literal[90] = 90
    runner_interval_hours: Literal[24] = 24
    social_days: Literal[30] = 30
    social_enabled: Literal[False] = False
    active_recall_action: Literal["EXCLUDE_AND_REVIEW"] = "EXCLUDE_AND_REVIEW"
    possible_recall_action: Literal["WATCH"] = "WATCH"
    stale_price_action: Literal["MAX_CONDITIONAL"] = "MAX_CONDITIONAL"
    stale_review_action: Literal["ZERO_ADJUSTMENT_MAX_CONDITIONAL"] = (
        "ZERO_ADJUSTMENT_MAX_CONDITIONAL"
    )
    source_terms_change_action: Literal["FAIL_CLOSED"] = "FAIL_CLOSED"
    evidence_hash_change_action: Literal["REGENERATE_V2_V3_ARTICLE_PACKET"] = (
        "REGENERATE_V2_V3_ARTICLE_PACKET"
    )
    automatic_publication_allowed: Literal[False] = False


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic UTF-8 JSON for one validated contract."""

    if not isinstance(value, StrictContractV1):
        raise TypeError("INVALID_RELIABILITY_CONTRACT")
    material = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        material,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def artifact_ref(value: StrictContractV1) -> ArtifactRefV1:
    """Bind one artifact to exact canonical bytes without storing its payload."""

    raw_artifact_id = getattr(value, "artifact_id", None)
    if not isinstance(raw_artifact_id, str):
        raise TypeError("ARTIFACT_ID_REQUIRED")
    payload = canonical_json_bytes(value)
    return ArtifactRefV1(
        artifact_type=type(value).__name__,
        artifact_id=raw_artifact_id,
        content_sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
    )


__all__ = [
    "ARTICLE_ID",
    "AcquisitionMethodV1",
    "ArticleEvidenceSnapshotV1",
    "ArtifactRefV1",
    "CandidateDecisionCodeV1",
    "CandidateDecisionV1",
    "ConfidenceGradeV1",
    "DiscoveryOfferV1",
    "DiscoveryCheckpointV1",
    "DiscoveryPageReceiptV1",
    "DiscoveryRunV1",
    "EvidenceDimensionScoresV1",
    "FitCandidateV1",
    "FitScoreV1",
    "IdentityConfidenceV1",
    "MonitorDiffV1",
    "MonitoringPolicyV1",
    "OfferPriceV1",
    "OfficialPageEvidenceV1",
    "ProductReviewSignalV1",
    "ProviderPageV1",
    "RecommendationProfileV1",
    "RecommendationStatusV1",
    "ResearchPlanV1",
    "ReviewAggregateSetV1",
    "ReviewContributionV1",
    "ReviewDecisionActionV1",
    "ReviewDecisionV1",
    "ReviewEvidenceStatusV1",
    "ReviewObservationV1",
    "ReviewPacketV1",
    "ReviewThemeSetV1",
    "ReviewThemeV1",
    "RiskLevelV1",
    "SafetyObservationV1",
    "SafetyStateV1",
    "SocialSignalSetV1",
    "SourceDecisionV1",
    "SourcePolicyV1",
    "SourceRuleV1",
    "StrictContractV1",
    "ThemeSeverityV1",
    "TrustedCandidateEvidenceV1",
    "TrustedRecommendationCandidateV1",
    "TrustedRecommendationResultV1",
    "VerificationStateV1",
    "artifact_ref",
    "canonical_json_bytes",
]
