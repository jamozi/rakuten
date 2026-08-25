"""Deterministic, fail-closed ST-0605 Claim--Evidence coverage evaluation.

The runtime consumes an already assembled, hash-bound snapshot.  It does not
map the policy vocabulary onto the non-isomorphic persistence or AI
vocabularies, read article/source text, resolve identity, mutate an article,
authorize publication, or perform I/O.  Reports contain only typed identities,
hashes, counts, and closed findings; caller-controlled claim/source text is not
accepted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Callable, NoReturn, SupportsIndex, TypeVar, cast
from uuid import UUID

from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.evidence.enums import (
    SourcePacketVersionStatus,
    SourceSnapshotValidationStatus,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    SourceId,
    SourcePacketId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.shared.identity import EntityId
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest


POLICY_DOCUMENT_ID = "RAOS-CONTENT-EVIDENCE-001"
POLICY_VERSION = "1.0.0"
POLICY_SHA256 = "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba"
EVALUATOR_VERSION = "ST0605_CLAIM_EVIDENCE_COVERAGE_V1"
CLAIM_SET_PROFILE = "ST0605_COMPLETE_CLAIM_SET_V1"
REPORT_PROFILE = "ST0605_COVERAGE_REPORT_V1"
MAJOR_REQUIRED_NUMERATOR = 1
MAJOR_REQUIRED_DENOMINATOR = 1
ALL_REQUIRED_NUMERATOR = 95
ALL_REQUIRED_DENOMINATOR = 100
_MAX_COLLECTION = 10_000
_MAX_EXACT_INTEGER = (1 << 53) - 1
_RecordT = TypeVar("_RecordT")


class PolicyClaimType(str, Enum):
    """Exact policy namespace; deliberately not a persisted-Claim mapping."""

    DIRECT_FACT = "direct_fact"
    DERIVED_FACT = "derived_fact"
    COMPARATIVE = "comparative"
    RECOMMENDATION = "recommendation"
    EXPERIENCE = "experience"
    PRICE_AVAILABILITY = "price_availability"
    SUPERLATIVE = "superlative"
    SAFETY_LEGAL_REGULATORY = "safety_legal_regulatory"
    PREDICTIVE = "predictive"


class PolicySourceTier(str, Enum):
    TIER_A = "SRC-TIER-A"
    TIER_B = "SRC-TIER-B"
    TIER_C = "SRC-TIER-C"
    TIER_D = "SRC-TIER-D"
    DISCOVERY = "SRC-DISCOVERY"
    EXCLUDED = "SRC-EXCLUDED"


class EvidenceOrigin(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    OFFER = "OFFER"
    INDEPENDENT = "INDEPENDENT"
    FIRST_HAND = "FIRST_HAND"
    AI_OUTPUT = "AI_OUTPUT"
    SEARCH_SNIPPET = "SEARCH_SNIPPET"
    RAKUTEN_REVIEW_BODY = "RAKUTEN_REVIEW_BODY"
    COMPETITOR_CONTENT = "COMPETITOR_CONTENT"


class PolicyLinkSupportType(str, Enum):
    """Policy link namespace; no implicit persisted-link conversion exists."""

    SUPPORTS = "SUPPORTS"
    QUALIFIES = "QUALIFIES"
    CONTRADICTS = "CONTRADICTS"


class IdentityStatus(str, Enum):
    MATCHED = "MATCHED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTING = "CONFLICTING"


class ConflictStatus(str, Enum):
    RESOLVED = "RESOLVED"
    OPEN = "OPEN"


class UnknownValueHandling(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXPLICIT_UNKNOWN = "EXPLICIT_UNKNOWN"
    IMPUTED = "IMPUTED"


class CoverageStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNEVALUABLE = "UNEVALUABLE"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ValidationAttestationKind(str, Enum):
    """Closed upstream-validation receipts accepted by the ST-0605 evaluator."""

    CLAIM_INVENTORY = "CLAIM_INVENTORY"
    ARTICLE_PACKET_BINDING = "ARTICLE_PACKET_BINDING"
    PACKET_APPROVAL_MEMBERSHIP = "PACKET_APPROVAL_MEMBERSHIP"
    FACT_VALIDATION = "FACT_VALIDATION"
    CONFLICT_CLOSURE = "CONFLICT_CLOSURE"
    IDENTITY_DECISION = "IDENTITY_DECISION"
    DERIVATION = "DERIVATION"
    COMPARISON = "COMPARISON"
    RECOMMENDATION = "RECOMMENDATION"
    EXPERIENCE = "EXPERIENCE"
    OFFER_FRESHNESS = "OFFER_FRESHNESS"
    SAFETY_COMPLIANCE = "SAFETY_COMPLIANCE"


class ValidationAttestationOrigin(str, Enum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


_ATTESTATION_OWNER_BINDING: dict[ValidationAttestationKind, tuple[str, str, str]] = {
    ValidationAttestationKind.CLAIM_INVENTORY: (
        "ST-0605",
        "RAOS-CONTENT-EVIDENCE-001@1.0.0",
        POLICY_SHA256,
    ),
    ValidationAttestationKind.ARTICLE_PACKET_BINDING: (
        "ST-0802",
        "RESOURCE-CONTRACTS@0.4",
        "aa53bf68b125821a46c093e653464e7f80e5710e31f6f860251aa8ebc30480c0",
    ),
    ValidationAttestationKind.PACKET_APPROVAL_MEMBERSHIP: (
        "ST-0604",
        "SOURCE-PACKET-LIFECYCLE-RUNTIME@2.0.0",
        "8fc6a6bc7a9b016ed70ec099da005f430f472702b0e422d227c32e45f8623f93",
    ),
    ValidationAttestationKind.FACT_VALIDATION: (
        "ST-0602",
        "FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1",
        "c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073",
    ),
    ValidationAttestationKind.CONFLICT_CLOSURE: (
        "ST-0603",
        "FACT-CONFLICT-REVIEW-REFERENCE-PLAN@1",
        "74d58a889c0e20cb74e699196c267b270a86db80667459c9178b04aefe66c093",
    ),
    ValidationAttestationKind.IDENTITY_DECISION: (
        "ST-0504",
        "PRODUCT-IDENTITY-HUMAN-REVIEW-REFERENCE-PLAN@1",
        "f8113f69157fc2afce5c5fb40ff5188c55d7d88b30ae7162441a710a7d54d5ab",
    ),
    ValidationAttestationKind.DERIVATION: (
        "ST-0602",
        "FACT-EXTRACTION-VALIDATION-REFERENCE-PLAN@1",
        "c7d7c16ee41a3d3ba5203c9cb091cc6f09fd1556400abb0d42438434d8bea073",
    ),
    ValidationAttestationKind.COMPARISON: (
        "ST-0803",
        "COMPARISON-TABLE-SCHEMA@1",
        "6da40ea538bd467a759613e0dca62f2e822ac4a9609adb71959d8bb624037c89",
    ),
    ValidationAttestationKind.RECOMMENDATION: (
        "ST-0804",
        "RECOMMENDATION-METHODOLOGY@0.1",
        "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862",
    ),
    ValidationAttestationKind.EXPERIENCE: (
        "ST-0605",
        "FIRST-HAND-EXPERIENCE-RECORD@1",
        "34dcb19731e44c3aa8a6991503cb78933461866f6393635d118eae9143f2f4ce",
    ),
    ValidationAttestationKind.OFFER_FRESHNESS: (
        "ST-1401",
        "FRESHNESS-UPDATE-POLICY@0.1",
        "a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2",
    ),
    ValidationAttestationKind.SAFETY_COMPLIANCE: (
        "ST-0805",
        "EDITORIAL-POLICY-CATALOG@0.1",
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
}


class CoverageFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"
    CONTRACT_BINDING_INVALID = "CONTRACT_BINDING_INVALID"
    ARTICLE_BINDING_INVALID = "ARTICLE_BINDING_INVALID"
    PACKET_BINDING_INVALID = "PACKET_BINDING_INVALID"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    RECORD_TYPE_INVALID = "RECORD_TYPE_INVALID"
    DUPLICATE_CLAIM_ID = "DUPLICATE_CLAIM_ID"
    COMPLETE_CLAIM_SET_MISMATCH = "COMPLETE_CLAIM_SET_MISMATCH"
    CLAIM_SET_HASH_MISMATCH = "CLAIM_SET_HASH_MISMATCH"
    CLAIM_ARTICLE_MISMATCH = "CLAIM_ARTICLE_MISMATCH"
    DUPLICATE_FACT_ID = "DUPLICATE_FACT_ID"
    PACKET_FACT_SET_MISMATCH = "PACKET_FACT_SET_MISMATCH"
    DUPLICATE_LINK = "DUPLICATE_LINK"
    LINK_REFERENCE_INVALID = "LINK_REFERENCE_INVALID"
    FACT_OUTSIDE_APPROVED_PACKET = "FACT_OUTSIDE_APPROVED_PACKET"
    DUPLICATE_SOURCE_ID = "DUPLICATE_SOURCE_ID"
    SOURCE_SET_MISMATCH = "SOURCE_SET_MISMATCH"
    DUPLICATE_SNAPSHOT_ID = "DUPLICATE_SNAPSHOT_ID"
    SNAPSHOT_SET_MISMATCH = "SNAPSHOT_SET_MISMATCH"
    SNAPSHOT_SOURCE_INVALID = "SNAPSHOT_SOURCE_INVALID"
    DUPLICATE_IDENTITY_BINDING = "DUPLICATE_IDENTITY_BINDING"
    IDENTITY_SET_MISMATCH = "IDENTITY_SET_MISMATCH"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    DUPLICATE_REQUIREMENT_PROOF = "DUPLICATE_REQUIREMENT_PROOF"
    REQUIREMENT_PROOF_SET_MISMATCH = "REQUIREMENT_PROOF_SET_MISMATCH"
    TEMPORAL_SCOPE_REQUIRED = "TEMPORAL_SCOPE_REQUIRED"
    DERIVED_FORMULA_REQUIRED = "DERIVED_FORMULA_REQUIRED"
    COMPARISON_POPULATION_REQUIRED = "COMPARISON_POPULATION_REQUIRED"
    RECOMMENDATION_METHODOLOGY_REQUIRED = "RECOMMENDATION_METHODOLOGY_REQUIRED"
    EXPERIENCE_RECORD_REQUIRED = "EXPERIENCE_RECORD_REQUIRED"
    EXPERIENCE_APPROVAL_REQUIRED = "EXPERIENCE_APPROVAL_REQUIRED"
    SAFETY_COMPLIANCE_REVIEW_REQUIRED = "SAFETY_COMPLIANCE_REVIEW_REQUIRED"
    PREDICTIVE_CLAIM_DEFAULT_BLOCKED = "PREDICTIVE_CLAIM_DEFAULT_BLOCKED"
    UNKNOWN_VALUE_IMPUTATION_FORBIDDEN = "UNKNOWN_VALUE_IMPUTATION_FORBIDDEN"
    SOURCE_INACTIVE = "SOURCE_INACTIVE"
    SOURCE_TIER_MISMATCH = "SOURCE_TIER_MISMATCH"
    AI_OUTPUT_IS_NOT_EVIDENCE = "AI_OUTPUT_IS_NOT_EVIDENCE"
    SEARCH_SNIPPET_IS_NOT_EVIDENCE = "SEARCH_SNIPPET_IS_NOT_EVIDENCE"
    RAKUTEN_REVIEW_BODY_PROHIBITED = "RAKUTEN_REVIEW_BODY_PROHIBITED"
    COMPETITOR_CONTENT_DISCOVERY_ONLY = "COMPETITOR_CONTENT_DISCOVERY_ONLY"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    DUPLICATE_CONFLICT_ID = "DUPLICATE_CONFLICT_ID"
    CONFLICT_REFERENCE_INVALID = "CONFLICT_REFERENCE_INVALID"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    DUPLICATE_CITATION_ID = "DUPLICATE_CITATION_ID"
    CITATION_SET_MISMATCH = "CITATION_SET_MISMATCH"
    CITATION_RESOLUTION_INVALID = "CITATION_RESOLUTION_INVALID"
    QUALIFIES_WITHOUT_SUPPORT = "QUALIFIES_WITHOUT_SUPPORT"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    MAJOR_COVERAGE_BELOW_100 = "MAJOR_COVERAGE_BELOW_100"
    ALL_COVERAGE_BELOW_95 = "ALL_COVERAGE_BELOW_95"
    ZERO_DENOMINATOR_UNEVALUABLE = "ZERO_DENOMINATOR_UNEVALUABLE"
    REQUIRED_ATTESTATION_MISSING = "REQUIRED_ATTESTATION_MISSING"
    ATTESTATION_SET_MISMATCH = "ATTESTATION_SET_MISMATCH"
    ATTESTATION_INVALID = "ATTESTATION_INVALID"
    ARTICLE_PACKET_BINDING_MISMATCH = "ARTICLE_PACKET_BINDING_MISMATCH"
    CLAIM_SUBJECT_IDENTITY_MISMATCH = "CLAIM_SUBJECT_IDENTITY_MISMATCH"
    FUTURE_EVIDENCE = "FUTURE_EVIDENCE"
    EVIDENCE_TIME_WINDOW_INVALID = "EVIDENCE_TIME_WINDOW_INVALID"
    OFFER_EXPIRY_REQUIRED = "OFFER_EXPIRY_REQUIRED"
    CONFLICT_RESOLUTION_EVIDENCE_REQUIRED = "CONFLICT_RESOLUTION_EVIDENCE_REQUIRED"


class CitationId(EntityId):
    __slots__ = ()


class ConflictId(EntityId):
    __slots__ = ()


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0605>)"

    def __str__(self) -> str:
        return "<redacted-st0605>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("ST-0605 generic serialization is not supported")


class ClaimEvidenceValueError(ValueError):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_CLAIM_EVIDENCE_VALUE")


def _invalid() -> NoReturn:
    raise ClaimEvidenceValueError() from None


@dataclass(frozen=True, slots=True, repr=False)
class CoverageContractBinding(_Redacted):
    policy_document_id: str
    policy_version: str
    policy_sha256: Sha256Digest
    evaluator_version: str
    claim_set_profile: str

    @classmethod
    def current(cls) -> CoverageContractBinding:
        return cls(
            policy_document_id=POLICY_DOCUMENT_ID,
            policy_version=POLICY_VERSION,
            policy_sha256=Sha256Digest(POLICY_SHA256),
            evaluator_version=EVALUATOR_VERSION,
            claim_set_profile=CLAIM_SET_PROFILE,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ArticleEvidenceBinding(_Redacted):
    article_version_id: ArticleVersionId
    article_body_sha256: Sha256Digest
    source_packet_version_id: SourcePacketVersionId
    source_packet_content_sha256: Sha256Digest
    complete_claim_ids: tuple[ClaimId, ...]
    complete_claim_set_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedPacketBinding(_Redacted):
    source_packet_id: SourcePacketId
    source_packet_version_id: SourcePacketVersionId
    version_no: int
    status: SourcePacketVersionStatus
    content_sha256: Sha256Digest
    fact_ids: tuple[FactId, ...]
    approval_decision_sha256: Sha256Digest
    approved_at: AwareUtcDateTime


@dataclass(frozen=True, slots=True, repr=False)
class PolicyClaim(_Redacted):
    claim_id: ClaimId
    article_version_id: ArticleVersionId
    claim_text_sha256: Sha256Digest
    claim_type: PolicyClaimType
    criticality: int
    affects_purchase_decision: bool
    affects_ranking: bool
    affects_price: bool
    affects_safety: bool
    affects_legal: bool
    temporal_scope_required: bool
    allowed_subject_identity_sha256s: tuple[Sha256Digest, ...]


@dataclass(frozen=True, slots=True, repr=False)
class ClaimRequirementProof(_Redacted):
    claim_id: ClaimId
    temporal_scope_sha256: Sha256Digest | None
    derivation_formula_sha256: Sha256Digest | None
    comparison_population_sha256: Sha256Digest | None
    recommendation_methodology_sha256: Sha256Digest | None
    experience_record_sha256: Sha256Digest | None
    experience_approved: bool
    safety_compliance_review_sha256: Sha256Digest | None
    unknown_value_handling: UnknownValueHandling


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceFact(_Redacted):
    fact_id: FactId
    source_snapshot_id: SourceSnapshotId
    fact_sha256: Sha256Digest
    subject_identity_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceLink(_Redacted):
    claim_id: ClaimId
    fact_id: FactId
    support_type: PolicyLinkSupportType


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceSource(_Redacted):
    source_id: SourceId
    tier: PolicySourceTier
    origin: EvidenceOrigin
    active: bool


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceSnapshot(_Redacted):
    source_snapshot_id: SourceSnapshotId
    source_id: SourceId
    content_sha256: Sha256Digest
    validation_status: SourceSnapshotValidationStatus
    acquired_at: AwareUtcDateTime
    expires_at: AwareUtcDateTime | None


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceIdentityBinding(_Redacted):
    fact_id: FactId
    status: IdentityStatus
    expected_subject_identity_sha256: Sha256Digest
    observed_subject_identity_sha256: Sha256Digest
    decision_sha256: Sha256Digest
    decided_at: AwareUtcDateTime


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceConflict(_Redacted):
    conflict_id: ConflictId
    fact_ids: tuple[FactId, ...]
    status: ConflictStatus
    resolution_decision_sha256: Sha256Digest | None
    reviewer_identity_sha256: Sha256Digest | None
    resolved_at: AwareUtcDateTime | None


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceValidationAttestation(_Redacted):
    kind: ValidationAttestationKind
    owner_story_id: str
    contract_version: str
    contract_sha256: Sha256Digest
    origin: ValidationAttestationOrigin
    subject_sha256: Sha256Digest
    input_sha256: Sha256Digest
    decision_sha256: Sha256Digest
    validated_at: AwareUtcDateTime
    valid: bool


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceCitation(_Redacted):
    citation_id: CitationId
    claim_id: ClaimId
    fact_id: FactId
    support_type: PolicyLinkSupportType
    source_id: SourceId
    source_snapshot_id: SourceSnapshotId


@dataclass(frozen=True, slots=True, repr=False)
class ClaimEvidenceSnapshot(_Redacted):
    contract: CoverageContractBinding
    article: ArticleEvidenceBinding
    approved_packet: ApprovedPacketBinding
    evaluated_at: AwareUtcDateTime
    claims: tuple[PolicyClaim, ...]
    requirement_proofs: tuple[ClaimRequirementProof, ...]
    facts: tuple[EvidenceFact, ...]
    links: tuple[EvidenceLink, ...]
    sources: tuple[EvidenceSource, ...]
    snapshots: tuple[EvidenceSnapshot, ...]
    identities: tuple[EvidenceIdentityBinding, ...]
    conflicts: tuple[EvidenceConflict, ...]
    citations: tuple[EvidenceCitation, ...]
    attestations: tuple[EvidenceValidationAttestation, ...]


@dataclass(frozen=True, slots=True, repr=False)
class CoverageFraction(_Redacted):
    evidenced: int
    total: int

    def __post_init__(self) -> None:
        if (
            type(self.evidenced) is not int
            or type(self.total) is not int
            or not 0 <= self.evidenced <= self.total <= _MAX_EXACT_INTEGER
            or self.total == 0
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class CoverageRecordReceipt(_Redacted):
    sequence: int
    report_sha256: Sha256Digest
    publication_authorized: bool = False

    def require_valid(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= _MAX_EXACT_INTEGER
            or type(self.report_sha256) is not Sha256Digest
            or self.publication_authorized is not False
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class ClaimEvidenceCoverageReport(_Redacted):
    article_version_id: ArticleVersionId | None
    article_body_sha256: Sha256Digest | None
    source_packet_version_id: SourcePacketVersionId | None
    source_packet_content_sha256: Sha256Digest | None
    policy_sha256: Sha256Digest
    evaluator_version: str
    evaluated_at: AwareUtcDateTime | None
    evaluation_input_sha256: Sha256Digest | None
    complete_claim_set_sha256: Sha256Digest | None
    status: CoverageStatus
    findings: tuple[CoverageFindingCode, ...]
    major_coverage: CoverageFraction | None
    all_verifiable_coverage: CoverageFraction | None
    major_requirement_satisfied: bool | None
    all_verifiable_requirement_satisfied: bool | None
    publication_authorized: bool
    production_eligible: bool
    formal_test_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus
    report_sha256: Sha256Digest

    def canonical_bytes(self) -> bytes:
        return _report_bytes(self, include_digest=True)

    def require_valid(self) -> None:
        major = self.major_coverage
        all_claims = self.all_verifiable_coverage
        if (
            (
                self.article_version_id is not None
                and not _valid_id(self.article_version_id, ArticleVersionId)
            )
            or (
                self.article_body_sha256 is not None
                and type(self.article_body_sha256) is not Sha256Digest
            )
            or (
                self.source_packet_version_id is not None
                and not _valid_id(self.source_packet_version_id, SourcePacketVersionId)
            )
            or (
                self.source_packet_content_sha256 is not None
                and type(self.source_packet_content_sha256) is not Sha256Digest
            )
            or type(self.policy_sha256) is not Sha256Digest
            or self.policy_sha256.value != POLICY_SHA256
            or type(self.evaluator_version) is not str
            or self.evaluator_version != EVALUATOR_VERSION
            or (
                self.evaluated_at is not None
                and type(self.evaluated_at) is not AwareUtcDateTime
            )
            or (
                self.evaluation_input_sha256 is not None
                and type(self.evaluation_input_sha256) is not Sha256Digest
            )
            or (
                self.complete_claim_set_sha256 is not None
                and type(self.complete_claim_set_sha256) is not Sha256Digest
            )
            or type(self.status) is not CoverageStatus
            or type(self.findings) is not tuple
            or any(type(item) is not CoverageFindingCode for item in self.findings)
            or self.findings
            != tuple(code for code in CoverageFindingCode if code in self.findings)
            or len(set(self.findings)) != len(self.findings)
            or (
                self.major_coverage is not None
                and type(self.major_coverage) is not CoverageFraction
            )
            or (
                self.all_verifiable_coverage is not None
                and type(self.all_verifiable_coverage) is not CoverageFraction
            )
            or self.publication_authorized is not False
            or self.production_eligible is not False
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.formal_test_status,
                    self.live_validation_status,
                    self.staging_status,
                    self.release_status,
                    self.production_status,
                )
            )
            or type(self.report_sha256) is not Sha256Digest
        ):
            _invalid()
        if major is not None:
            expected_major = major.evidenced == major.total
            if self.major_requirement_satisfied is None:
                if (
                    self.status is not CoverageStatus.UNEVALUABLE
                    or CoverageFindingCode.ZERO_DENOMINATOR_UNEVALUABLE
                    not in self.findings
                ):
                    _invalid()
            elif self.major_requirement_satisfied is not expected_major:
                _invalid()
        elif self.major_requirement_satisfied is not None:
            _invalid()
        if all_claims is not None:
            expected_all = meets_all_verifiable_threshold(
                evidenced=all_claims.evidenced,
                total=all_claims.total,
            )
            if self.all_verifiable_requirement_satisfied is None:
                if (
                    self.status is not CoverageStatus.UNEVALUABLE
                    or CoverageFindingCode.ZERO_DENOMINATOR_UNEVALUABLE
                    not in self.findings
                ):
                    _invalid()
            elif self.all_verifiable_requirement_satisfied is not expected_all:
                _invalid()
        elif self.all_verifiable_requirement_satisfied is not None:
            _invalid()
        complete_bindings = all(
            value is not None
            for value in (
                self.article_version_id,
                self.article_body_sha256,
                self.source_packet_version_id,
                self.source_packet_content_sha256,
                self.evaluated_at,
                self.evaluation_input_sha256,
                self.complete_claim_set_sha256,
            )
        )
        if self.status is CoverageStatus.PASS:
            if (
                not complete_bindings
                or self.findings
                or self.major_requirement_satisfied is not True
                or self.all_verifiable_requirement_satisfied is not True
            ):
                _invalid()
        elif self.status is CoverageStatus.BLOCK:
            if (
                not complete_bindings
                or not self.findings
                or major is None
                or all_claims is None
                or any(item in _STRUCTURAL_FINDINGS for item in self.findings)
            ):
                _invalid()
        elif not self.findings:
            _invalid()
        expected = hashlib.sha256(_report_bytes(self, include_digest=False)).hexdigest()
        if self.report_sha256.value != expected:
            _invalid()


_ELIGIBLE_TIERS: dict[PolicyClaimType, frozenset[PolicySourceTier]] = {
    PolicyClaimType.DIRECT_FACT: frozenset(
        {PolicySourceTier.TIER_A, PolicySourceTier.TIER_B}
    ),
    PolicyClaimType.DERIVED_FACT: frozenset(
        {PolicySourceTier.TIER_A, PolicySourceTier.TIER_B}
    ),
    PolicyClaimType.COMPARATIVE: frozenset(
        {
            PolicySourceTier.TIER_A,
            PolicySourceTier.TIER_C,
            PolicySourceTier.TIER_D,
        }
    ),
    PolicyClaimType.RECOMMENDATION: frozenset(
        {
            PolicySourceTier.TIER_A,
            PolicySourceTier.TIER_C,
            PolicySourceTier.TIER_D,
        }
    ),
    PolicyClaimType.EXPERIENCE: frozenset({PolicySourceTier.TIER_D}),
    PolicyClaimType.PRICE_AVAILABILITY: frozenset({PolicySourceTier.TIER_B}),
    PolicyClaimType.SUPERLATIVE: frozenset(
        {
            PolicySourceTier.TIER_A,
            PolicySourceTier.TIER_B,
            PolicySourceTier.TIER_C,
            PolicySourceTier.TIER_D,
        }
    ),
    PolicyClaimType.SAFETY_LEGAL_REGULATORY: frozenset({PolicySourceTier.TIER_A}),
    PolicyClaimType.PREDICTIVE: frozenset(
        {PolicySourceTier.TIER_A, PolicySourceTier.TIER_C}
    ),
}

_ORIGIN_TIER: dict[EvidenceOrigin, PolicySourceTier] = {
    EvidenceOrigin.AUTHORITATIVE: PolicySourceTier.TIER_A,
    EvidenceOrigin.OFFER: PolicySourceTier.TIER_B,
    EvidenceOrigin.INDEPENDENT: PolicySourceTier.TIER_C,
    EvidenceOrigin.FIRST_HAND: PolicySourceTier.TIER_D,
    EvidenceOrigin.AI_OUTPUT: PolicySourceTier.EXCLUDED,
    EvidenceOrigin.SEARCH_SNIPPET: PolicySourceTier.DISCOVERY,
    EvidenceOrigin.RAKUTEN_REVIEW_BODY: PolicySourceTier.EXCLUDED,
    EvidenceOrigin.COMPETITOR_CONTENT: PolicySourceTier.DISCOVERY,
}

_STRUCTURAL_FINDINGS = frozenset(
    {
        CoverageFindingCode.INPUT_TYPE_INVALID,
        CoverageFindingCode.INPUT_UNAVAILABLE,
        CoverageFindingCode.CONTRACT_BINDING_INVALID,
        CoverageFindingCode.ARTICLE_BINDING_INVALID,
        CoverageFindingCode.PACKET_BINDING_INVALID,
        CoverageFindingCode.COLLECTION_TYPE_INVALID,
        CoverageFindingCode.RECORD_TYPE_INVALID,
        CoverageFindingCode.DUPLICATE_CLAIM_ID,
        CoverageFindingCode.COMPLETE_CLAIM_SET_MISMATCH,
        CoverageFindingCode.CLAIM_SET_HASH_MISMATCH,
        CoverageFindingCode.CLAIM_ARTICLE_MISMATCH,
        CoverageFindingCode.DUPLICATE_FACT_ID,
        CoverageFindingCode.DUPLICATE_LINK,
        CoverageFindingCode.LINK_REFERENCE_INVALID,
        CoverageFindingCode.DUPLICATE_SOURCE_ID,
        CoverageFindingCode.DUPLICATE_SNAPSHOT_ID,
        CoverageFindingCode.SNAPSHOT_SOURCE_INVALID,
        CoverageFindingCode.DUPLICATE_IDENTITY_BINDING,
        CoverageFindingCode.DUPLICATE_REQUIREMENT_PROOF,
        CoverageFindingCode.DUPLICATE_CONFLICT_ID,
        CoverageFindingCode.CONFLICT_REFERENCE_INVALID,
        CoverageFindingCode.DUPLICATE_CITATION_ID,
        CoverageFindingCode.REQUIRED_ATTESTATION_MISSING,
        CoverageFindingCode.ATTESTATION_SET_MISMATCH,
        CoverageFindingCode.ATTESTATION_INVALID,
        CoverageFindingCode.ARTICLE_PACKET_BINDING_MISMATCH,
    }
)


def _id_key(value: EntityId) -> str:
    return str(value.value)


def _valid_id(value: object, expected: type[EntityId]) -> bool:
    return type(value) is expected and type(value.value) is UUID


def _exact_ids(values: object, expected: type[EntityId]) -> bool:
    if type(values) is not tuple:
        return False
    items = cast(tuple[object, ...], values)
    return len(items) <= _MAX_COLLECTION and all(
        _valid_id(value, expected) for value in items
    )


def _exact_digests(values: object, *, allow_empty: bool = False) -> bool:
    if type(values) is not tuple:
        return False
    items = cast(tuple[object, ...], values)
    return (
        len(items) <= _MAX_COLLECTION
        and (allow_empty or bool(items))
        and all(type(value) is Sha256Digest for value in items)
        and len(items) == len(set(items))
    )


def _has_duplicate_ids(values: tuple[EntityId, ...]) -> bool:
    keys = tuple(value.value for value in values)
    return len(keys) != len(set(keys))


def _claim_material(claim: PolicyClaim) -> dict[str, object]:
    return {
        "affects_legal": claim.affects_legal,
        "affects_price": claim.affects_price,
        "affects_purchase_decision": claim.affects_purchase_decision,
        "affects_ranking": claim.affects_ranking,
        "affects_safety": claim.affects_safety,
        "article_version_id": _id_key(claim.article_version_id),
        "claim_id": _id_key(claim.claim_id),
        "claim_text_sha256": claim.claim_text_sha256.value,
        "claim_type": claim.claim_type.value,
        "criticality": claim.criticality,
        "temporal_scope_required": claim.temporal_scope_required,
        "allowed_subject_identity_sha256s": sorted(
            value.value for value in claim.allowed_subject_identity_sha256s
        ),
    }


def _valid_claim(claim: object) -> bool:
    return (
        type(claim) is PolicyClaim
        and _valid_id(claim.claim_id, ClaimId)
        and _valid_id(claim.article_version_id, ArticleVersionId)
        and type(claim.claim_text_sha256) is Sha256Digest
        and type(claim.claim_type) is PolicyClaimType
        and type(claim.criticality) is int
        and 1 <= claim.criticality <= 5
        and all(
            type(value) is bool
            for value in (
                claim.affects_purchase_decision,
                claim.affects_ranking,
                claim.affects_price,
                claim.affects_safety,
                claim.affects_legal,
                claim.temporal_scope_required,
            )
        )
        and _exact_digests(claim.allowed_subject_identity_sha256s)
    )


def complete_claim_set_sha256(claims: tuple[PolicyClaim, ...]) -> Sha256Digest:
    """Hash the exact complete policy-Claim set without claim text."""

    if (
        type(claims) is not tuple
        or not claims
        or len(claims) > _MAX_COLLECTION
        or any(not _valid_claim(claim) for claim in claims)
        or len({claim.claim_id.value for claim in claims}) != len(claims)
    ):
        _invalid()
    material = {
        "claims": [
            _claim_material(claim)
            for claim in sorted(claims, key=lambda item: item.claim_id.value.int)
        ],
        "profile": CLAIM_SET_PROFILE,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return Sha256Digest(hashlib.sha256(encoded).hexdigest())


def meets_all_verifiable_threshold(*, evidenced: int, total: int) -> bool:
    """Use integer cross multiplication; zero never passes."""

    if (
        type(evidenced) is not int
        or type(total) is not int
        or not 0 <= evidenced <= total <= _MAX_EXACT_INTEGER
        or total == 0
    ):
        return False
    return evidenced * ALL_REQUIRED_DENOMINATOR >= total * ALL_REQUIRED_NUMERATOR


def _major(claim: PolicyClaim) -> bool:
    return claim.criticality >= 4 or any(
        (
            claim.affects_purchase_decision,
            claim.affects_ranking,
            claim.affects_price,
            claim.affects_safety,
            claim.affects_legal,
            claim.claim_type
            in {
                PolicyClaimType.RECOMMENDATION,
                PolicyClaimType.PRICE_AVAILABILITY,
                PolicyClaimType.SAFETY_LEGAL_REGULATORY,
            },
        )
    )


def _instant_key(value: AwareUtcDateTime | None) -> str | None:
    if value is None:
        return None
    return value.value.isoformat().replace("+00:00", "Z")


def _optional_digest_key(value: Sha256Digest | None) -> str | None:
    return None if value is None else value.value


def _digest_material(value: object) -> Sha256Digest:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _article_material(value: ArticleEvidenceBinding) -> dict[str, object]:
    return {
        "article_body_sha256": value.article_body_sha256.value,
        "article_version_id": _id_key(value.article_version_id),
        "complete_claim_ids": sorted(
            _id_key(item) for item in value.complete_claim_ids
        ),
        "complete_claim_set_sha256": value.complete_claim_set_sha256.value,
        "source_packet_content_sha256": value.source_packet_content_sha256.value,
        "source_packet_version_id": _id_key(value.source_packet_version_id),
    }


def _packet_material(value: ApprovedPacketBinding) -> dict[str, object]:
    return {
        "approval_decision_sha256": value.approval_decision_sha256.value,
        "approved_at": _instant_key(value.approved_at),
        "content_sha256": value.content_sha256.value,
        "fact_ids": sorted(_id_key(item) for item in value.fact_ids),
        "source_packet_id": _id_key(value.source_packet_id),
        "source_packet_version_id": _id_key(value.source_packet_version_id),
        "status": value.status.value,
        "version_no": value.version_no,
    }


def _proof_material(value: ClaimRequirementProof) -> dict[str, object]:
    return {
        "claim_id": _id_key(value.claim_id),
        "comparison_population_sha256": _optional_digest_key(
            value.comparison_population_sha256
        ),
        "derivation_formula_sha256": _optional_digest_key(
            value.derivation_formula_sha256
        ),
        "experience_approved": value.experience_approved,
        "experience_record_sha256": _optional_digest_key(
            value.experience_record_sha256
        ),
        "recommendation_methodology_sha256": _optional_digest_key(
            value.recommendation_methodology_sha256
        ),
        "safety_compliance_review_sha256": _optional_digest_key(
            value.safety_compliance_review_sha256
        ),
        "temporal_scope_sha256": _optional_digest_key(value.temporal_scope_sha256),
        "unknown_value_handling": value.unknown_value_handling.value,
    }


def _fact_material(value: EvidenceFact) -> dict[str, object]:
    return {
        "fact_id": _id_key(value.fact_id),
        "fact_sha256": value.fact_sha256.value,
        "source_snapshot_id": _id_key(value.source_snapshot_id),
        "subject_identity_sha256": value.subject_identity_sha256.value,
    }


def _source_material(value: EvidenceSource) -> dict[str, object]:
    return {
        "active": value.active,
        "origin": value.origin.value,
        "source_id": _id_key(value.source_id),
        "tier": value.tier.value,
    }


def _snapshot_material(value: EvidenceSnapshot) -> dict[str, object]:
    return {
        "acquired_at": _instant_key(value.acquired_at),
        "content_sha256": value.content_sha256.value,
        "expires_at": _instant_key(value.expires_at),
        "source_id": _id_key(value.source_id),
        "source_snapshot_id": _id_key(value.source_snapshot_id),
        "validation_status": value.validation_status.value,
    }


def _identity_material(value: EvidenceIdentityBinding) -> dict[str, object]:
    return {
        "decided_at": _instant_key(value.decided_at),
        "decision_sha256": value.decision_sha256.value,
        "expected_subject_identity_sha256": (
            value.expected_subject_identity_sha256.value
        ),
        "fact_id": _id_key(value.fact_id),
        "observed_subject_identity_sha256": (
            value.observed_subject_identity_sha256.value
        ),
        "status": value.status.value,
    }


def _conflict_material(value: EvidenceConflict) -> dict[str, object]:
    return {
        "conflict_id": _id_key(value.conflict_id),
        "fact_ids": sorted(_id_key(item) for item in value.fact_ids),
        "resolution_decision_sha256": _optional_digest_key(
            value.resolution_decision_sha256
        ),
        "resolved_at": _instant_key(value.resolved_at),
        "reviewer_identity_sha256": _optional_digest_key(
            value.reviewer_identity_sha256
        ),
        "status": value.status.value,
    }


def _attestation_subject(
    kind: ValidationAttestationKind,
    identity: str,
) -> Sha256Digest:
    return _digest_material(
        {"identity": identity, "kind": kind.value, "profile": EVALUATOR_VERSION}
    )


def required_validation_attestation_inputs(
    value: ClaimEvidenceSnapshot,
) -> tuple[tuple[ValidationAttestationKind, Sha256Digest, Sha256Digest], ...]:
    """Return the exact upstream receipt inputs required by one valid snapshot."""

    if (
        type(value) is not ClaimEvidenceSnapshot
        or not _article_valid(value.article)
        or not _packet_valid(value.approved_packet)
        or type(value.evaluated_at) is not AwareUtcDateTime
        or type(value.claims) is not tuple
        or any(not _valid_claim(item) for item in value.claims)
        or type(value.requirement_proofs) is not tuple
        or any(not _valid_proof(item) for item in value.requirement_proofs)
        or type(value.facts) is not tuple
        or any(not _valid_fact(item) for item in value.facts)
        or type(value.links) is not tuple
        or any(not _valid_link(item) for item in value.links)
        or type(value.sources) is not tuple
        or any(not _valid_source(item) for item in value.sources)
        or type(value.snapshots) is not tuple
        or any(not _valid_snapshot(item) for item in value.snapshots)
        or type(value.identities) is not tuple
        or any(not _valid_identity(item) for item in value.identities)
        or type(value.conflicts) is not tuple
        or any(not _valid_conflict(item) for item in value.conflicts)
    ):
        _invalid()
    article_identity = _id_key(value.article.article_version_id)
    packet_identity = _id_key(value.approved_packet.source_packet_version_id)
    requirements: list[
        tuple[ValidationAttestationKind, Sha256Digest, Sha256Digest]
    ] = []

    def add(kind: ValidationAttestationKind, identity: str, material: object) -> None:
        requirements.append(
            (kind, _attestation_subject(kind, identity), _digest_material(material))
        )

    ordered_claims = sorted(value.claims, key=lambda item: item.claim_id.value.int)
    ordered_facts = sorted(value.facts, key=lambda item: item.fact_id.value.int)
    add(
        ValidationAttestationKind.CLAIM_INVENTORY,
        article_identity,
        {
            "article": _article_material(value.article),
            "claims": [_claim_material(item) for item in ordered_claims],
        },
    )
    add(
        ValidationAttestationKind.ARTICLE_PACKET_BINDING,
        article_identity,
        {
            "article": _article_material(value.article),
            "packet": _packet_material(value.approved_packet),
        },
    )
    add(
        ValidationAttestationKind.PACKET_APPROVAL_MEMBERSHIP,
        packet_identity,
        {
            "facts": [_fact_material(item) for item in ordered_facts],
            "packet": _packet_material(value.approved_packet),
        },
    )
    source_by_id = {item.source_id: item for item in value.sources}
    snapshot_by_id = {item.source_snapshot_id: item for item in value.snapshots}
    for fact in ordered_facts:
        snapshot = snapshot_by_id.get(fact.source_snapshot_id)
        source = None if snapshot is None else source_by_id.get(snapshot.source_id)
        add(
            ValidationAttestationKind.FACT_VALIDATION,
            _id_key(fact.fact_id),
            {
                "fact": _fact_material(fact),
                "snapshot": None if snapshot is None else _snapshot_material(snapshot),
                "source": None if source is None else _source_material(source),
            },
        )
    identity_by_fact = {item.fact_id: item for item in value.identities}
    for fact in ordered_facts:
        identity = identity_by_fact.get(fact.fact_id)
        add(
            ValidationAttestationKind.IDENTITY_DECISION,
            _id_key(fact.fact_id),
            {
                "fact": _fact_material(fact),
                "identity": (
                    None if identity is None else _identity_material(identity)
                ),
            },
        )
    add(
        ValidationAttestationKind.CONFLICT_CLOSURE,
        packet_identity,
        {
            "conflicts": [
                _conflict_material(item)
                for item in sorted(
                    value.conflicts,
                    key=lambda item: item.conflict_id.value.int,
                )
            ],
            "packet_fact_ids": sorted(
                _id_key(item) for item in value.approved_packet.fact_ids
            ),
            "source_packet_version_id": packet_identity,
        },
    )
    proof_by_claim = {item.claim_id: item for item in value.requirement_proofs}
    fact_by_id = {item.fact_id: item for item in value.facts}
    links_by_claim: dict[ClaimId, list[EvidenceLink]] = {}
    for link in value.links:
        links_by_claim.setdefault(link.claim_id, []).append(link)
    kind_by_type = {
        PolicyClaimType.DERIVED_FACT: ValidationAttestationKind.DERIVATION,
        PolicyClaimType.COMPARATIVE: ValidationAttestationKind.COMPARISON,
        PolicyClaimType.RECOMMENDATION: ValidationAttestationKind.RECOMMENDATION,
        PolicyClaimType.EXPERIENCE: ValidationAttestationKind.EXPERIENCE,
        PolicyClaimType.PRICE_AVAILABILITY: ValidationAttestationKind.OFFER_FRESHNESS,
        PolicyClaimType.SUPERLATIVE: ValidationAttestationKind.COMPARISON,
        PolicyClaimType.SAFETY_LEGAL_REGULATORY: (
            ValidationAttestationKind.SAFETY_COMPLIANCE
        ),
    }
    for claim in ordered_claims:
        kind = kind_by_type.get(claim.claim_type)
        if kind is None:
            continue
        claim_links = sorted(
            links_by_claim.get(claim.claim_id, []),
            key=lambda item: (item.fact_id.value.int, item.support_type.value),
        )
        add(
            kind,
            _id_key(claim.claim_id),
            {
                "claim": _claim_material(claim),
                "facts": [
                    _fact_material(fact_by_id[item.fact_id])
                    for item in claim_links
                    if item.fact_id in fact_by_id
                ],
                "links": [
                    {
                        "claim_id": _id_key(item.claim_id),
                        "fact_id": _id_key(item.fact_id),
                        "support_type": item.support_type.value,
                    }
                    for item in claim_links
                ],
                "proof": (
                    None
                    if claim.claim_id not in proof_by_claim
                    else _proof_material(proof_by_claim[claim.claim_id])
                ),
            },
        )
    return tuple(requirements)


def validation_attestation_owner_binding(
    kind: ValidationAttestationKind,
) -> tuple[str, str, Sha256Digest]:
    """Expose the closed receipt issuer/version/hash tuple without mutation."""

    if type(kind) is not ValidationAttestationKind:
        _invalid()
    owner, version, digest = _ATTESTATION_OWNER_BINDING[kind]
    return owner, version, Sha256Digest(digest)


def recorded_synthetic_attestation_decision_sha256(
    kind: ValidationAttestationKind,
    subject_sha256: Sha256Digest,
    input_sha256: Sha256Digest,
) -> Sha256Digest:
    """Derive the corruption-check digest for one recorded synthetic receipt."""

    if (
        type(kind) is not ValidationAttestationKind
        or type(subject_sha256) is not Sha256Digest
        or type(input_sha256) is not Sha256Digest
    ):
        _invalid()
    owner, _, contract_sha256 = validation_attestation_owner_binding(kind)
    return _digest_material(
        {
            "contract_sha256": contract_sha256.value,
            "input_sha256": input_sha256.value,
            "kind": kind.value,
            "owner_story_id": owner,
            "profile": "ST0605_RECORDED_SYNTHETIC_ATTESTATION_V1",
            "subject_sha256": subject_sha256.value,
        }
    )


def _evaluation_input_sha256_or_none(
    value: ClaimEvidenceSnapshot,
) -> Sha256Digest | None:
    try:
        material = {
            "article": _article_material(value.article),
            "attestations": [
                {
                    "contract_sha256": item.contract_sha256.value,
                    "contract_version": item.contract_version,
                    "decision_sha256": item.decision_sha256.value,
                    "input_sha256": item.input_sha256.value,
                    "kind": item.kind.value,
                    "origin": item.origin.value,
                    "owner_story_id": item.owner_story_id,
                    "subject_sha256": item.subject_sha256.value,
                    "valid": item.valid,
                    "validated_at": _instant_key(item.validated_at),
                }
                for item in value.attestations
            ],
            "citations": [
                {
                    "citation_id": _id_key(item.citation_id),
                    "claim_id": _id_key(item.claim_id),
                    "fact_id": _id_key(item.fact_id),
                    "source_id": _id_key(item.source_id),
                    "source_snapshot_id": _id_key(item.source_snapshot_id),
                    "support_type": item.support_type.value,
                }
                for item in value.citations
            ],
            "claims": [_claim_material(item) for item in value.claims],
            "conflicts": [_conflict_material(item) for item in value.conflicts],
            "contract": {
                "claim_set_profile": value.contract.claim_set_profile,
                "evaluator_version": value.contract.evaluator_version,
                "policy_document_id": value.contract.policy_document_id,
                "policy_sha256": value.contract.policy_sha256.value,
                "policy_version": value.contract.policy_version,
            },
            "evaluated_at": _instant_key(value.evaluated_at),
            "facts": [_fact_material(item) for item in value.facts],
            "identities": [_identity_material(item) for item in value.identities],
            "links": [
                {
                    "claim_id": _id_key(item.claim_id),
                    "fact_id": _id_key(item.fact_id),
                    "support_type": item.support_type.value,
                }
                for item in value.links
            ],
            "packet": _packet_material(value.approved_packet),
            "profile": "ST0605_EVALUATION_INPUT_V1",
            "proofs": [_proof_material(item) for item in value.requirement_proofs],
            "snapshots": [_snapshot_material(item) for item in value.snapshots],
            "sources": [_source_material(item) for item in value.sources],
        }
        return _digest_material(material)
    except Exception:
        return None


def _fraction_payload(value: CoverageFraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"evidenced": value.evidenced, "total": value.total}


def _report_payload(report: ClaimEvidenceCoverageReport) -> dict[str, object]:
    return {
        "all_verifiable_coverage": _fraction_payload(report.all_verifiable_coverage),
        "all_verifiable_requirement_satisfied": (
            report.all_verifiable_requirement_satisfied
        ),
        "article_body_sha256": (
            None
            if report.article_body_sha256 is None
            else report.article_body_sha256.value
        ),
        "article_version_id": (
            None
            if report.article_version_id is None
            else _id_key(report.article_version_id)
        ),
        "complete_claim_set_sha256": (
            None
            if report.complete_claim_set_sha256 is None
            else report.complete_claim_set_sha256.value
        ),
        "evaluated_at": (
            None
            if report.evaluated_at is None
            else report.evaluated_at.value.isoformat().replace("+00:00", "Z")
        ),
        "evaluation_input_sha256": (
            None
            if report.evaluation_input_sha256 is None
            else report.evaluation_input_sha256.value
        ),
        "evaluator_version": report.evaluator_version,
        "findings": [finding.value for finding in report.findings],
        "formal_test_status": report.formal_test_status.value,
        "live_validation_status": report.live_validation_status.value,
        "major_coverage": _fraction_payload(report.major_coverage),
        "major_requirement_satisfied": report.major_requirement_satisfied,
        "policy_sha256": report.policy_sha256.value,
        "production_eligible": report.production_eligible,
        "production_status": report.production_status.value,
        "profile": REPORT_PROFILE,
        "publication_authorized": report.publication_authorized,
        "release_status": report.release_status.value,
        "source_packet_content_sha256": (
            None
            if report.source_packet_content_sha256 is None
            else report.source_packet_content_sha256.value
        ),
        "source_packet_version_id": (
            None
            if report.source_packet_version_id is None
            else _id_key(report.source_packet_version_id)
        ),
        "staging_status": report.staging_status.value,
        "status": report.status.value,
    }


def _report_bytes(
    report: ClaimEvidenceCoverageReport,
    *,
    include_digest: bool,
) -> bytes:
    payload = _report_payload(report)
    if include_digest:
        payload["report_sha256"] = report.report_sha256.value
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _make_report(
    *,
    value: ClaimEvidenceSnapshot | None,
    requested_article_version_id: ArticleVersionId | None,
    status: CoverageStatus,
    findings: set[CoverageFindingCode],
    major: CoverageFraction | None,
    all_claims: CoverageFraction | None,
    major_satisfied: bool | None,
    all_satisfied: bool | None,
) -> ClaimEvidenceCoverageReport:
    candidate_article = None if value is None else getattr(value, "article", None)
    candidate_packet = (
        None if value is None else getattr(value, "approved_packet", None)
    )
    article = candidate_article if _article_valid(candidate_article) else None
    packet = candidate_packet if _packet_valid(candidate_packet) else None
    article_id = requested_article_version_id
    if article is not None and _valid_id(article.article_version_id, ArticleVersionId):
        article_id = article.article_version_id
    ordered = tuple(code for code in CoverageFindingCode if code in findings)
    placeholder = Sha256Digest("0" * 64)
    report = ClaimEvidenceCoverageReport(
        article_version_id=article_id,
        article_body_sha256=(
            article.article_body_sha256 if article is not None else None
        ),
        source_packet_version_id=(
            packet.source_packet_version_id if packet is not None else None
        ),
        source_packet_content_sha256=(
            packet.content_sha256 if packet is not None else None
        ),
        policy_sha256=Sha256Digest(POLICY_SHA256),
        evaluator_version=EVALUATOR_VERSION,
        evaluated_at=(
            value.evaluated_at
            if value is not None
            and type(getattr(value, "evaluated_at", None)) is AwareUtcDateTime
            else None
        ),
        evaluation_input_sha256=(
            _evaluation_input_sha256_or_none(value) if value is not None else None
        ),
        complete_claim_set_sha256=(
            article.complete_claim_set_sha256 if article is not None else None
        ),
        status=status,
        findings=ordered,
        major_coverage=major,
        all_verifiable_coverage=all_claims,
        major_requirement_satisfied=major_satisfied,
        all_verifiable_requirement_satisfied=all_satisfied,
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=placeholder,
    )
    digest = Sha256Digest(
        hashlib.sha256(_report_bytes(report, include_digest=False)).hexdigest()
    )
    report = ClaimEvidenceCoverageReport(
        article_version_id=report.article_version_id,
        article_body_sha256=report.article_body_sha256,
        source_packet_version_id=report.source_packet_version_id,
        source_packet_content_sha256=report.source_packet_content_sha256,
        policy_sha256=report.policy_sha256,
        evaluator_version=report.evaluator_version,
        evaluated_at=report.evaluated_at,
        evaluation_input_sha256=report.evaluation_input_sha256,
        complete_claim_set_sha256=report.complete_claim_set_sha256,
        status=report.status,
        findings=report.findings,
        major_coverage=report.major_coverage,
        all_verifiable_coverage=report.all_verifiable_coverage,
        major_requirement_satisfied=report.major_requirement_satisfied,
        all_verifiable_requirement_satisfied=(
            report.all_verifiable_requirement_satisfied
        ),
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=digest,
    )
    report.require_valid()
    return report


def unavailable_claim_evidence_report(
    article_version_id: ArticleVersionId,
) -> ClaimEvidenceCoverageReport:
    if not _valid_id(article_version_id, ArticleVersionId):
        _invalid()
    return _make_report(
        value=None,
        requested_article_version_id=article_version_id,
        status=CoverageStatus.UNEVALUABLE,
        findings={CoverageFindingCode.INPUT_UNAVAILABLE},
        major=None,
        all_claims=None,
        major_satisfied=None,
        all_satisfied=None,
    )


def _contract_valid(value: object) -> bool:
    return (
        type(value) is CoverageContractBinding
        and value == CoverageContractBinding.current()
    )


def _article_valid(value: object) -> bool:
    return (
        type(value) is ArticleEvidenceBinding
        and _valid_id(value.article_version_id, ArticleVersionId)
        and type(value.article_body_sha256) is Sha256Digest
        and _valid_id(value.source_packet_version_id, SourcePacketVersionId)
        and type(value.source_packet_content_sha256) is Sha256Digest
        and _exact_ids(value.complete_claim_ids, ClaimId)
        and not _has_duplicate_ids(cast(tuple[EntityId, ...], value.complete_claim_ids))
        and type(value.complete_claim_set_sha256) is Sha256Digest
    )


def _packet_valid(value: object) -> bool:
    return (
        type(value) is ApprovedPacketBinding
        and _valid_id(value.source_packet_id, SourcePacketId)
        and _valid_id(value.source_packet_version_id, SourcePacketVersionId)
        and type(value.version_no) is int
        and 0 < value.version_no <= _MAX_EXACT_INTEGER
        and type(value.status) is SourcePacketVersionStatus
        and value.status is SourcePacketVersionStatus.APPROVED
        and type(value.content_sha256) is Sha256Digest
        and _exact_ids(value.fact_ids, FactId)
        and not _has_duplicate_ids(cast(tuple[EntityId, ...], value.fact_ids))
        and type(value.approval_decision_sha256) is Sha256Digest
        and type(value.approved_at) is AwareUtcDateTime
    )


def _record_collections(
    value: ClaimEvidenceSnapshot,
) -> tuple[tuple[object, ...], ...] | None:
    collections: tuple[object, ...] = (
        value.claims,
        value.requirement_proofs,
        value.facts,
        value.links,
        value.sources,
        value.snapshots,
        value.identities,
        value.conflicts,
        value.citations,
        value.attestations,
    )
    if any(
        type(collection) is not tuple or len(collection) > _MAX_COLLECTION
        for collection in collections
    ):
        return None
    return cast(tuple[tuple[object, ...], ...], collections)


def _valid_proof(value: object) -> bool:
    if type(value) is not ClaimRequirementProof or not _valid_id(
        value.claim_id, ClaimId
    ):
        return False
    for optional in (
        value.temporal_scope_sha256,
        value.derivation_formula_sha256,
        value.comparison_population_sha256,
        value.recommendation_methodology_sha256,
        value.experience_record_sha256,
        value.safety_compliance_review_sha256,
    ):
        if optional is not None and type(optional) is not Sha256Digest:
            return False
    return (
        type(value.experience_approved) is bool
        and type(value.unknown_value_handling) is UnknownValueHandling
    )


def _valid_fact(value: object) -> bool:
    return (
        type(value) is EvidenceFact
        and _valid_id(value.fact_id, FactId)
        and _valid_id(value.source_snapshot_id, SourceSnapshotId)
        and type(value.fact_sha256) is Sha256Digest
        and type(value.subject_identity_sha256) is Sha256Digest
    )


def _valid_link(value: object) -> bool:
    return (
        type(value) is EvidenceLink
        and _valid_id(value.claim_id, ClaimId)
        and _valid_id(value.fact_id, FactId)
        and type(value.support_type) is PolicyLinkSupportType
    )


def _valid_source(value: object) -> bool:
    return (
        type(value) is EvidenceSource
        and _valid_id(value.source_id, SourceId)
        and type(value.tier) is PolicySourceTier
        and type(value.origin) is EvidenceOrigin
        and type(value.active) is bool
    )


def _valid_snapshot(value: object) -> bool:
    return (
        type(value) is EvidenceSnapshot
        and _valid_id(value.source_snapshot_id, SourceSnapshotId)
        and _valid_id(value.source_id, SourceId)
        and type(value.content_sha256) is Sha256Digest
        and type(value.validation_status) is SourceSnapshotValidationStatus
        and type(value.acquired_at) is AwareUtcDateTime
        and (value.expires_at is None or type(value.expires_at) is AwareUtcDateTime)
    )


def _valid_identity(value: object) -> bool:
    return (
        type(value) is EvidenceIdentityBinding
        and _valid_id(value.fact_id, FactId)
        and type(value.status) is IdentityStatus
        and type(value.expected_subject_identity_sha256) is Sha256Digest
        and type(value.observed_subject_identity_sha256) is Sha256Digest
        and type(value.decision_sha256) is Sha256Digest
        and type(value.decided_at) is AwareUtcDateTime
    )


def _valid_conflict(value: object) -> bool:
    if not (
        type(value) is EvidenceConflict
        and _valid_id(value.conflict_id, ConflictId)
        and _exact_ids(value.fact_ids, FactId)
        and bool(value.fact_ids)
        and not _has_duplicate_ids(cast(tuple[EntityId, ...], value.fact_ids))
        and type(value.status) is ConflictStatus
    ):
        return False
    return (
        (
            value.resolution_decision_sha256 is None
            or type(value.resolution_decision_sha256) is Sha256Digest
        )
        and (
            value.reviewer_identity_sha256 is None
            or type(value.reviewer_identity_sha256) is Sha256Digest
        )
        and (value.resolved_at is None or type(value.resolved_at) is AwareUtcDateTime)
    )


def _valid_attestation(value: object) -> bool:
    if (
        type(value) is EvidenceValidationAttestation
        and type(value.kind) is ValidationAttestationKind
        and type(value.owner_story_id) is str
        and type(value.contract_version) is str
        and type(value.contract_sha256) is Sha256Digest
        and type(value.origin) is ValidationAttestationOrigin
        and type(value.subject_sha256) is Sha256Digest
        and type(value.input_sha256) is Sha256Digest
        and type(value.decision_sha256) is Sha256Digest
        and type(value.validated_at) is AwareUtcDateTime
        and type(value.valid) is bool
    ):
        owner, version, digest = _ATTESTATION_OWNER_BINDING[value.kind]
        return (
            value.owner_story_id == owner
            and value.contract_version == version
            and value.contract_sha256.value == digest
            and value.origin is ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY
            and value.decision_sha256
            == recorded_synthetic_attestation_decision_sha256(
                value.kind,
                value.subject_sha256,
                value.input_sha256,
            )
        )
    return False


def _valid_citation(value: object) -> bool:
    return (
        type(value) is EvidenceCitation
        and _valid_id(value.citation_id, CitationId)
        and _valid_id(value.claim_id, ClaimId)
        and _valid_id(value.fact_id, FactId)
        and type(value.support_type) is PolicyLinkSupportType
        and _valid_id(value.source_id, SourceId)
        and _valid_id(value.source_snapshot_id, SourceSnapshotId)
    )


def _duplicate(
    values: tuple[_RecordT, ...],
    key: Callable[[_RecordT], object],
) -> bool:
    keys = [key(item) for item in values]
    return len(keys) != len(set(keys))


def _proof_findings(
    claim: PolicyClaim, proof: ClaimRequirementProof
) -> set[CoverageFindingCode]:
    findings: set[CoverageFindingCode] = set()
    if claim.temporal_scope_required and proof.temporal_scope_sha256 is None:
        findings.add(CoverageFindingCode.TEMPORAL_SCOPE_REQUIRED)
    if (
        claim.claim_type is PolicyClaimType.DERIVED_FACT
        and proof.derivation_formula_sha256 is None
    ):
        findings.add(CoverageFindingCode.DERIVED_FORMULA_REQUIRED)
    if (
        claim.claim_type in {PolicyClaimType.COMPARATIVE, PolicyClaimType.SUPERLATIVE}
        and proof.comparison_population_sha256 is None
    ):
        findings.add(CoverageFindingCode.COMPARISON_POPULATION_REQUIRED)
    if (
        claim.claim_type is PolicyClaimType.RECOMMENDATION
        and proof.recommendation_methodology_sha256 is None
    ):
        findings.add(CoverageFindingCode.RECOMMENDATION_METHODOLOGY_REQUIRED)
    if claim.claim_type is PolicyClaimType.EXPERIENCE:
        if proof.experience_record_sha256 is None:
            findings.add(CoverageFindingCode.EXPERIENCE_RECORD_REQUIRED)
        if not proof.experience_approved:
            findings.add(CoverageFindingCode.EXPERIENCE_APPROVAL_REQUIRED)
    if (
        claim.claim_type is PolicyClaimType.SAFETY_LEGAL_REGULATORY
        and proof.safety_compliance_review_sha256 is None
    ):
        findings.add(CoverageFindingCode.SAFETY_COMPLIANCE_REVIEW_REQUIRED)
    if claim.claim_type is PolicyClaimType.PREDICTIVE:
        findings.add(CoverageFindingCode.PREDICTIVE_CLAIM_DEFAULT_BLOCKED)
    if proof.unknown_value_handling is UnknownValueHandling.IMPUTED:
        findings.add(CoverageFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN)
    return findings


def _evaluate_claim_evidence(value: object) -> ClaimEvidenceCoverageReport:
    """Evaluate one complete snapshot without mutation or external authority."""

    if type(value) is not ClaimEvidenceSnapshot:
        return _make_report(
            value=None,
            requested_article_version_id=None,
            status=CoverageStatus.UNEVALUABLE,
            findings={CoverageFindingCode.INPUT_TYPE_INVALID},
            major=None,
            all_claims=None,
            major_satisfied=None,
            all_satisfied=None,
        )
    snapshot = value
    findings: set[CoverageFindingCode] = set()
    if not _contract_valid(snapshot.contract):
        findings.add(CoverageFindingCode.CONTRACT_BINDING_INVALID)
    if not _article_valid(snapshot.article):
        findings.add(CoverageFindingCode.ARTICLE_BINDING_INVALID)
    if not _packet_valid(snapshot.approved_packet):
        findings.add(CoverageFindingCode.PACKET_BINDING_INVALID)
    if type(snapshot.evaluated_at) is not AwareUtcDateTime:
        findings.add(CoverageFindingCode.ARTICLE_BINDING_INVALID)
    elif (
        _packet_valid(snapshot.approved_packet)
        and snapshot.approved_packet.approved_at.value > snapshot.evaluated_at.value
    ):
        findings.add(CoverageFindingCode.FUTURE_EVIDENCE)
    collections = _record_collections(snapshot)
    if collections is None:
        findings.add(CoverageFindingCode.COLLECTION_TYPE_INVALID)
        return _make_report(
            value=snapshot,
            requested_article_version_id=None,
            status=CoverageStatus.UNEVALUABLE,
            findings=findings,
            major=None,
            all_claims=None,
            major_satisfied=None,
            all_satisfied=None,
        )

    validators = (
        _valid_claim,
        _valid_proof,
        _valid_fact,
        _valid_link,
        _valid_source,
        _valid_snapshot,
        _valid_identity,
        _valid_conflict,
        _valid_citation,
        _valid_attestation,
    )
    if any(
        any(not validator(item) for item in collection)
        for collection, validator in zip(collections, validators, strict=True)
    ):
        findings.add(CoverageFindingCode.RECORD_TYPE_INVALID)

    claims = tuple(item for item in snapshot.claims if _valid_claim(item))
    proofs = tuple(item for item in snapshot.requirement_proofs if _valid_proof(item))
    facts = tuple(item for item in snapshot.facts if _valid_fact(item))
    links = tuple(item for item in snapshot.links if _valid_link(item))
    sources = tuple(item for item in snapshot.sources if _valid_source(item))
    evidence_snapshots = tuple(
        item for item in snapshot.snapshots if _valid_snapshot(item)
    )
    identities = tuple(item for item in snapshot.identities if _valid_identity(item))
    conflicts = tuple(item for item in snapshot.conflicts if _valid_conflict(item))
    citations = tuple(item for item in snapshot.citations if _valid_citation(item))
    attestations = tuple(
        item for item in snapshot.attestations if _valid_attestation(item)
    )

    if _duplicate(claims, lambda item: item.claim_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_CLAIM_ID)
    if _duplicate(proofs, lambda item: item.claim_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_REQUIREMENT_PROOF)
    if _duplicate(facts, lambda item: item.fact_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_FACT_ID)
    if _duplicate(
        links,
        lambda item: (item.claim_id.value, item.fact_id.value, item.support_type.value),
    ):
        findings.add(CoverageFindingCode.DUPLICATE_LINK)
    if _duplicate(sources, lambda item: item.source_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_SOURCE_ID)
    if _duplicate(evidence_snapshots, lambda item: item.source_snapshot_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_SNAPSHOT_ID)
    if _duplicate(identities, lambda item: item.fact_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_IDENTITY_BINDING)
    if _duplicate(conflicts, lambda item: item.conflict_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_CONFLICT_ID)
    if _duplicate(citations, lambda item: item.citation_id.value):
        findings.add(CoverageFindingCode.DUPLICATE_CITATION_ID)
    if _duplicate(
        attestations,
        lambda item: (item.kind.value, item.subject_sha256.value),
    ):
        findings.add(CoverageFindingCode.ATTESTATION_SET_MISMATCH)

    claim_by_id = {item.claim_id: item for item in claims}
    proof_by_claim = {item.claim_id: item for item in proofs}
    fact_by_id = {item.fact_id: item for item in facts}
    source_by_id = {item.source_id: item for item in sources}
    snapshot_by_id = {item.source_snapshot_id: item for item in evidence_snapshots}
    identity_by_fact = {item.fact_id: item for item in identities}

    claim_ids = set(claim_by_id)
    fact_ids = set(fact_by_id)
    if _article_valid(snapshot.article):
        declared_claim_ids = set(snapshot.article.complete_claim_ids)
        if claim_ids != declared_claim_ids or len(claims) != len(
            snapshot.article.complete_claim_ids
        ):
            findings.add(CoverageFindingCode.COMPLETE_CLAIM_SET_MISMATCH)
        if claims:
            try:
                observed_hash = complete_claim_set_sha256(claims)
            except ClaimEvidenceValueError:
                findings.add(CoverageFindingCode.CLAIM_SET_HASH_MISMATCH)
            else:
                if observed_hash != snapshot.article.complete_claim_set_sha256:
                    findings.add(CoverageFindingCode.CLAIM_SET_HASH_MISMATCH)
        for claim in claims:
            if claim.article_version_id != snapshot.article.article_version_id:
                findings.add(CoverageFindingCode.CLAIM_ARTICLE_MISMATCH)
        if _packet_valid(snapshot.approved_packet) and (
            snapshot.article.source_packet_version_id
            != snapshot.approved_packet.source_packet_version_id
            or snapshot.article.source_packet_content_sha256
            != snapshot.approved_packet.content_sha256
        ):
            findings.add(CoverageFindingCode.ARTICLE_PACKET_BINDING_MISMATCH)
    if set(proof_by_claim) != claim_ids or len(proofs) != len(claims):
        findings.add(CoverageFindingCode.REQUIREMENT_PROOF_SET_MISMATCH)
    packet_fact_ids: set[FactId]
    if _packet_valid(snapshot.approved_packet):
        packet_fact_ids = set(snapshot.approved_packet.fact_ids)
        if packet_fact_ids != fact_ids or len(facts) != len(
            snapshot.approved_packet.fact_ids
        ):
            findings.add(CoverageFindingCode.PACKET_FACT_SET_MISMATCH)
    else:
        packet_fact_ids = set()

    referenced_snapshot_ids = {item.source_snapshot_id for item in facts}
    if referenced_snapshot_ids != set(snapshot_by_id):
        findings.add(CoverageFindingCode.SNAPSHOT_SET_MISMATCH)
    referenced_source_ids = {item.source_id for item in evidence_snapshots}
    if referenced_source_ids != set(source_by_id):
        findings.add(CoverageFindingCode.SOURCE_SET_MISMATCH)
    if set(identity_by_fact) != fact_ids or len(identities) != len(facts):
        findings.add(CoverageFindingCode.IDENTITY_SET_MISMATCH)

    invalid_facts: set[FactId] = set()
    for fact in facts:
        if fact.fact_id not in packet_fact_ids:
            findings.add(CoverageFindingCode.FACT_OUTSIDE_APPROVED_PACKET)
            invalid_facts.add(fact.fact_id)
        source_snapshot = snapshot_by_id.get(fact.source_snapshot_id)
        if source_snapshot is None:
            invalid_facts.add(fact.fact_id)
            continue
        source = source_by_id.get(source_snapshot.source_id)
        if source is None:
            findings.add(CoverageFindingCode.SNAPSHOT_SOURCE_INVALID)
            invalid_facts.add(fact.fact_id)
        if (
            source_snapshot.validation_status
            is not SourceSnapshotValidationStatus.VALID
        ):
            findings.add(CoverageFindingCode.SNAPSHOT_INVALID)
            invalid_facts.add(fact.fact_id)
        if (
            type(snapshot.evaluated_at) is AwareUtcDateTime
            and source_snapshot.acquired_at.value > snapshot.evaluated_at.value
        ):
            findings.add(CoverageFindingCode.FUTURE_EVIDENCE)
            invalid_facts.add(fact.fact_id)
        if (
            source_snapshot.expires_at is not None
            and source_snapshot.expires_at.value <= source_snapshot.acquired_at.value
        ):
            findings.add(CoverageFindingCode.EVIDENCE_TIME_WINDOW_INVALID)
            invalid_facts.add(fact.fact_id)
        if (
            source_snapshot.expires_at is not None
            and type(snapshot.evaluated_at) is AwareUtcDateTime
            and source_snapshot.expires_at.value <= snapshot.evaluated_at.value
        ):
            findings.add(CoverageFindingCode.STALE_EVIDENCE)
            invalid_facts.add(fact.fact_id)
        identity = identity_by_fact.get(fact.fact_id)
        if identity is None:
            invalid_facts.add(fact.fact_id)
        elif identity.status is IdentityStatus.UNRESOLVED:
            findings.add(CoverageFindingCode.IDENTITY_UNRESOLVED)
            invalid_facts.add(fact.fact_id)
        elif identity.status is IdentityStatus.CONFLICTING:
            findings.add(CoverageFindingCode.IDENTITY_CONFLICT)
            invalid_facts.add(fact.fact_id)
        elif (
            identity.expected_subject_identity_sha256 != fact.subject_identity_sha256
            or identity.observed_subject_identity_sha256 != fact.subject_identity_sha256
        ):
            findings.add(CoverageFindingCode.IDENTITY_CONFLICT)
            invalid_facts.add(fact.fact_id)
        if (
            identity is not None
            and type(snapshot.evaluated_at) is AwareUtcDateTime
            and identity.decided_at.value > snapshot.evaluated_at.value
        ):
            findings.add(CoverageFindingCode.FUTURE_EVIDENCE)
            invalid_facts.add(fact.fact_id)

    for conflict in conflicts:
        if not set(conflict.fact_ids).issubset(fact_ids):
            findings.add(CoverageFindingCode.CONFLICT_REFERENCE_INVALID)
            continue
        if conflict.status is ConflictStatus.OPEN:
            findings.add(CoverageFindingCode.UNRESOLVED_CONFLICT)
            invalid_facts.update(conflict.fact_ids)
        else:
            resolution_values = (
                conflict.resolution_decision_sha256,
                conflict.reviewer_identity_sha256,
                conflict.resolved_at,
            )
            if any(item is None for item in resolution_values):
                findings.add(CoverageFindingCode.CONFLICT_RESOLUTION_EVIDENCE_REQUIRED)
                invalid_facts.update(conflict.fact_ids)
            elif (
                type(snapshot.evaluated_at) is AwareUtcDateTime
                and conflict.resolved_at is not None
                and conflict.resolved_at.value > snapshot.evaluated_at.value
            ):
                findings.add(CoverageFindingCode.FUTURE_EVIDENCE)
                invalid_facts.update(conflict.fact_ids)

    link_keys = {(item.claim_id, item.fact_id, item.support_type) for item in links}
    citation_keys = {
        (item.claim_id, item.fact_id, item.support_type) for item in citations
    }
    if link_keys != citation_keys or len(links) != len(citations):
        findings.add(CoverageFindingCode.CITATION_SET_MISMATCH)
    citation_by_key = {
        (item.claim_id, item.fact_id, item.support_type): item for item in citations
    }

    invalid_links: set[tuple[ClaimId, FactId, PolicyLinkSupportType]] = set()
    links_by_claim: dict[ClaimId, list[EvidenceLink]] = {
        claim_id: [] for claim_id in claim_ids
    }
    for link in links:
        key = (link.claim_id, link.fact_id, link.support_type)
        if link.claim_id not in claim_ids or link.fact_id not in fact_ids:
            findings.add(CoverageFindingCode.LINK_REFERENCE_INVALID)
            invalid_links.add(key)
            continue
        links_by_claim[link.claim_id].append(link)
        fact = fact_by_id[link.fact_id]
        source_snapshot = snapshot_by_id.get(fact.source_snapshot_id)
        source = (
            None
            if source_snapshot is None
            else source_by_id.get(source_snapshot.source_id)
        )
        if source is None:
            invalid_links.add(key)
        else:
            if not source.active:
                findings.add(CoverageFindingCode.SOURCE_INACTIVE)
                invalid_links.add(key)
            if _ORIGIN_TIER.get(source.origin) is not source.tier:
                findings.add(CoverageFindingCode.SOURCE_TIER_MISMATCH)
                invalid_links.add(key)
            claim = claim_by_id[link.claim_id]
            if fact.subject_identity_sha256 not in (
                claim.allowed_subject_identity_sha256s
            ):
                findings.add(CoverageFindingCode.CLAIM_SUBJECT_IDENTITY_MISMATCH)
                invalid_links.add(key)
            if source.tier not in _ELIGIBLE_TIERS[claim.claim_type]:
                findings.add(CoverageFindingCode.SOURCE_TIER_MISMATCH)
                invalid_links.add(key)
            if (
                claim.claim_type is PolicyClaimType.PRICE_AVAILABILITY
                and source_snapshot is not None
                and source_snapshot.expires_at is None
            ):
                findings.add(CoverageFindingCode.OFFER_EXPIRY_REQUIRED)
                invalid_links.add(key)
            origin_findings = {
                EvidenceOrigin.AI_OUTPUT: CoverageFindingCode.AI_OUTPUT_IS_NOT_EVIDENCE,
                EvidenceOrigin.SEARCH_SNIPPET: CoverageFindingCode.SEARCH_SNIPPET_IS_NOT_EVIDENCE,
                EvidenceOrigin.RAKUTEN_REVIEW_BODY: CoverageFindingCode.RAKUTEN_REVIEW_BODY_PROHIBITED,
                EvidenceOrigin.COMPETITOR_CONTENT: CoverageFindingCode.COMPETITOR_CONTENT_DISCOVERY_ONLY,
            }
            origin_finding = origin_findings.get(source.origin)
            if origin_finding is not None:
                findings.add(origin_finding)
                invalid_links.add(key)
        citation = citation_by_key.get(key)
        if (
            citation is None
            or source_snapshot is None
            or citation.source_snapshot_id != source_snapshot.source_snapshot_id
            or citation.source_id != source_snapshot.source_id
        ):
            findings.add(CoverageFindingCode.CITATION_RESOLUTION_INVALID)
            invalid_links.add(key)
        if link.fact_id in invalid_facts:
            invalid_links.add(key)

    try:
        required_attestations = required_validation_attestation_inputs(snapshot)
    except Exception:
        findings.add(CoverageFindingCode.ATTESTATION_INVALID)
    else:
        expected_by_key = {
            (kind, subject): input_sha
            for kind, subject, input_sha in required_attestations
        }
        observed_by_key = {
            (item.kind, item.subject_sha256): item for item in attestations
        }
        missing = set(expected_by_key) - set(observed_by_key)
        extra = set(observed_by_key) - set(expected_by_key)
        if missing:
            findings.add(CoverageFindingCode.REQUIRED_ATTESTATION_MISSING)
        if extra or len(observed_by_key) != len(attestations):
            findings.add(CoverageFindingCode.ATTESTATION_SET_MISMATCH)
        for attestation_key, expected_input in expected_by_key.items():
            observed = observed_by_key.get(attestation_key)
            if observed is None:
                continue
            if (
                observed.input_sha256 != expected_input
                or observed.valid is not True
                or (
                    type(snapshot.evaluated_at) is AwareUtcDateTime
                    and observed.validated_at.value > snapshot.evaluated_at.value
                )
            ):
                findings.add(CoverageFindingCode.ATTESTATION_INVALID)

    evidenced_claims: set[ClaimId] = set()
    evidence_gap_claims: set[ClaimId] = set()
    for claim in claims:
        claim_links = links_by_claim.get(claim.claim_id, [])
        claim_blocked = False
        proof = proof_by_claim.get(claim.claim_id)
        if proof is None:
            claim_blocked = True
        else:
            proof_issues = _proof_findings(claim, proof)
            findings.update(proof_issues)
            claim_blocked = bool(proof_issues)
        if any(
            link.support_type is PolicyLinkSupportType.CONTRADICTS
            for link in claim_links
        ):
            findings.add(CoverageFindingCode.CONTRADICTORY_EVIDENCE)
            claim_blocked = True
        support_links = [
            link
            for link in claim_links
            if link.support_type is PolicyLinkSupportType.SUPPORTS
        ]
        if not support_links:
            if any(
                link.support_type is PolicyLinkSupportType.QUALIFIES
                for link in claim_links
            ):
                findings.add(CoverageFindingCode.QUALIFIES_WITHOUT_SUPPORT)
            evidence_gap_claims.add(claim.claim_id)
            continue
        valid_support = any(
            (link.claim_id, link.fact_id, link.support_type) not in invalid_links
            for link in support_links
        )
        if valid_support and not claim_blocked:
            evidenced_claims.add(claim.claim_id)
        else:
            evidence_gap_claims.add(claim.claim_id)

    all_total = len(claims)
    major_claim_ids = {claim.claim_id for claim in claims if _major(claim)}
    major_total = len(major_claim_ids)
    all_evidenced = len(evidenced_claims)
    major_evidenced = len(evidenced_claims & major_claim_ids)
    if all_total == 0 or major_total == 0:
        findings.add(CoverageFindingCode.ZERO_DENOMINATOR_UNEVALUABLE)
        major_fraction = (
            None if major_total == 0 else CoverageFraction(major_evidenced, major_total)
        )
        all_fraction = (
            None if all_total == 0 else CoverageFraction(all_evidenced, all_total)
        )
        return _make_report(
            value=snapshot,
            requested_article_version_id=None,
            status=CoverageStatus.UNEVALUABLE,
            findings=findings,
            major=major_fraction,
            all_claims=all_fraction,
            major_satisfied=None,
            all_satisfied=None,
        )
    major_satisfied = major_evidenced == major_total
    all_satisfied = meets_all_verifiable_threshold(
        evidenced=all_evidenced, total=all_total
    )
    if not major_satisfied:
        findings.add(CoverageFindingCode.MAJOR_COVERAGE_BELOW_100)
    if not all_satisfied:
        findings.add(CoverageFindingCode.ALL_COVERAGE_BELOW_95)
    if (evidence_gap_claims & major_claim_ids) or not all_satisfied:
        findings.add(CoverageFindingCode.EVIDENCE_REQUIRED)
    status = CoverageStatus.PASS
    if findings:
        status = (
            CoverageStatus.UNEVALUABLE
            if any(finding in _STRUCTURAL_FINDINGS for finding in findings)
            else CoverageStatus.BLOCK
        )
    return _make_report(
        value=snapshot,
        requested_article_version_id=None,
        status=status,
        findings=findings,
        major=CoverageFraction(major_evidenced, major_total),
        all_claims=CoverageFraction(all_evidenced, all_total),
        major_satisfied=major_satisfied,
        all_satisfied=all_satisfied,
    )


def evaluate_claim_evidence(value: object) -> ClaimEvidenceCoverageReport:
    """Evaluate fail-closed; malformed exact dataclasses never escape exceptions."""

    try:
        return _evaluate_claim_evidence(value)
    except Exception:
        return _make_report(
            value=None,
            requested_article_version_id=None,
            status=CoverageStatus.UNEVALUABLE,
            findings={CoverageFindingCode.INPUT_TYPE_INVALID},
            major=None,
            all_claims=None,
            major_satisfied=None,
            all_satisfied=None,
        )


__all__ = [
    "ALL_REQUIRED_DENOMINATOR",
    "ALL_REQUIRED_NUMERATOR",
    "ApprovedPacketBinding",
    "ArticleEvidenceBinding",
    "CLAIM_SET_PROFILE",
    "CitationId",
    "ClaimEvidenceCoverageReport",
    "ClaimEvidenceSnapshot",
    "ClaimEvidenceValueError",
    "ClaimRequirementProof",
    "ConflictId",
    "ConflictStatus",
    "CoverageContractBinding",
    "CoverageFindingCode",
    "CoverageFraction",
    "CoverageRecordReceipt",
    "CoverageStatus",
    "EVALUATOR_VERSION",
    "EvidenceCitation",
    "EvidenceConflict",
    "EvidenceFact",
    "EvidenceIdentityBinding",
    "EvidenceLink",
    "EvidenceOrigin",
    "EvidenceSnapshot",
    "EvidenceSource",
    "EvidenceValidationAttestation",
    "ExecutionStatus",
    "IdentityStatus",
    "MAJOR_REQUIRED_DENOMINATOR",
    "MAJOR_REQUIRED_NUMERATOR",
    "POLICY_DOCUMENT_ID",
    "POLICY_SHA256",
    "POLICY_VERSION",
    "PolicyClaim",
    "PolicyClaimType",
    "PolicyLinkSupportType",
    "PolicySourceTier",
    "UnknownValueHandling",
    "ValidationAttestationKind",
    "ValidationAttestationOrigin",
    "complete_claim_set_sha256",
    "evaluate_claim_evidence",
    "meets_all_verifiable_threshold",
    "recorded_synthetic_attestation_decision_sha256",
    "required_validation_attestation_inputs",
    "unavailable_claim_evidence_report",
    "validation_attestation_owner_binding",
]
