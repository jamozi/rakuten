"""Content-addressed, local-only ST-0805 editorial policy evaluation V2.

The historical V1 evaluator remains the sole implementation of the canonical
40-policy, 8-axis, 13-zero-tolerance and 12-gate calculation.  This additive
boundary proves that its pre-resolved input belongs to one exact ST-0802 draft,
one independently re-evaluated ST-0605 coverage result, and one independently
re-evaluated ST-0804 recommendation result.  It grants no approval, waiver,
ranking, mutation, publication, activation, provider, or production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import NoReturn
import unicodedata

from raos.domain.editorial.article_lifecycle import (
    ArticleVersionState,
    BodySha256,
    VersionSnapshot,
)
from raos.domain.editorial.content_ast import dump_content_ast_json
from raos.domain.editorial.ids import ArticleId, ArticleVersionId
from raos.domain.editorial.policy_engine import (
    LocalEvaluationStatus,
    POLICY_DEFINITIONS,
    QUALITY_AXIS_DEFINITIONS,
    QUALITY_GATE_DEFINITIONS,
    ZERO_TOLERANCE_LABELS,
    PolicyEvaluationInput,
    PolicyEvaluationResult,
    PolicyFinding,
    PredecessorState,
    PredecessorStory,
    WaiverEvaluation,
    evaluate_editorial_policy,
)
from raos.domain.editorial.recommendation_v2 import (
    RecommendationEnvelopeV2,
    RecommendationEvaluationStatus,
    RecommendationRecordReceipt,
    RecommendationReportV2,
    evaluate_recommendations_v2,
    prohibited_ranking_alias,
)
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceCoverageReport,
    ClaimEvidenceSnapshot,
    CoverageRecordReceipt,
    CoverageStatus,
    ValidationAttestationKind,
    evaluate_claim_evidence,
)
from raos.domain.shared.persistence import Sha256Digest


CONTRACT_ID = "RAOS-ST0805-EDITORIAL-POLICY-RUNTIME-002"
CONTRACT_VERSION = "2.0.0"
EVALUATOR_VERSION = "ST0805_EDITORIAL_POLICY_ENGINE_V2"
POLICY_CATALOG_SHA256 = (
    "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a"
)
QUALITY_CATALOG_SHA256 = (
    "90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb"
)
CLAIM_EVIDENCE_POLICY_SHA256 = (
    "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba"
)
RECOMMENDATION_METHODOLOGY_SHA256 = (
    "fb71ad7900c7f688f305e10256b49563281893408e54d8668aac02efa7e57862"
)
LEGACY_POLICY_ENGINE_SHA256 = (
    "d858a9b010253cf411083bd5eb9da995ff3f9a172c7626ca9e499a6256559e51"
)
ARTICLE_LIFECYCLE_SHA256 = (
    "c44cb8c5d26f4862e7527bcb179c20f1f60d3a069d9ba67fad3b0109ef0c6edd"
)
CONTENT_AST_SOURCE_SHA256 = (
    "7cb4054cc8ab9b950cc572c0d8fa23dafe5baf77c40c242f81dac0fc0a492f68"
)
ST0804_DOMAIN_SHA256 = (
    "d7b020a65dfe2071335fda7bdb9b804fcd02def954c415a36318437a9e4d5de4"
)
LOCAL_STATUS = "LOCAL_IMPLEMENTATION_COMPLETE"

_MAX_AST_BYTES = 1_048_576
_MAX_RESULT_BYTES = 2_097_152
_MAX_EVIDENCE_PER_RECORD = 64
_MAX_COVERAGE_COLLECTION = 4096


class PolicyRuntimeValueError(ValueError):
    """Closed V2 construction error without caller-controlled material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_ST0805_V2_VALUE")


def _invalid() -> NoReturn:
    raise PolicyRuntimeValueError() from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0805-v2>)"


class PolicyEvaluationStatusV2(str, Enum):
    UNEVALUABLE = "UNEVALUABLE"
    BLOCK = "BLOCK"
    LOCAL_EVALUATED = "LOCAL_EVALUATED"


class PolicyFindingCodeV2(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    INPUT_BOUNDS_EXCEEDED = "INPUT_BOUNDS_EXCEEDED"
    CONTRACT_BINDING_MISMATCH = "CONTRACT_BINDING_MISMATCH"
    DRAFT_BINDING_MISMATCH = "DRAFT_BINDING_MISMATCH"
    COVERAGE_STRUCTURAL_INVALID = "COVERAGE_STRUCTURAL_INVALID"
    COVERAGE_REPORT_MISMATCH = "COVERAGE_REPORT_MISMATCH"
    COVERAGE_UNEVALUABLE = "COVERAGE_UNEVALUABLE"
    COVERAGE_BLOCKED = "COVERAGE_BLOCKED"
    COVERAGE_CORE_MISMATCH = "COVERAGE_CORE_MISMATCH"
    RECOMMENDATION_STRUCTURAL_INVALID = "RECOMMENDATION_STRUCTURAL_INVALID"
    RECOMMENDATION_REPORT_MISMATCH = "RECOMMENDATION_REPORT_MISMATCH"
    RECOMMENDATION_UNEVALUABLE = "RECOMMENDATION_UNEVALUABLE"
    RECOMMENDATION_BLOCKED = "RECOMMENDATION_BLOCKED"
    RECOMMENDATION_CORE_MISMATCH = "RECOMMENDATION_CORE_MISMATCH"
    POLICY_INPUT_HASH_MISMATCH = "POLICY_INPUT_HASH_MISMATCH"
    POLICY_INPUT_INVALID = "POLICY_INPUT_INVALID"
    POLICY_NOT_EVALUATED = "POLICY_NOT_EVALUATED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    PROHIBITED_AFFILIATE_INPUT = "PROHIBITED_AFFILIATE_INPUT"
    RECEIPT_INVALID = "RECEIPT_INVALID"
    DECLARED_INPUT_HASH_MISMATCH = "DECLARED_INPUT_HASH_MISMATCH"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


@dataclass(frozen=True, slots=True, repr=False)
class PolicyContractBindingV2(_Redacted):
    contract_id: str
    contract_version: str
    evaluator_version: str
    policy_catalog_sha256: Sha256Digest
    quality_catalog_sha256: Sha256Digest
    claim_evidence_policy_sha256: Sha256Digest
    recommendation_methodology_sha256: Sha256Digest
    legacy_policy_engine_sha256: Sha256Digest
    article_lifecycle_sha256: Sha256Digest
    content_ast_source_sha256: Sha256Digest
    st0804_domain_sha256: Sha256Digest

    @classmethod
    def current(cls) -> PolicyContractBindingV2:
        return cls(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            evaluator_version=EVALUATOR_VERSION,
            policy_catalog_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
            quality_catalog_sha256=Sha256Digest(QUALITY_CATALOG_SHA256),
            claim_evidence_policy_sha256=Sha256Digest(CLAIM_EVIDENCE_POLICY_SHA256),
            recommendation_methodology_sha256=Sha256Digest(
                RECOMMENDATION_METHODOLOGY_SHA256
            ),
            legacy_policy_engine_sha256=Sha256Digest(LEGACY_POLICY_ENGINE_SHA256),
            article_lifecycle_sha256=Sha256Digest(ARTICLE_LIFECYCLE_SHA256),
            content_ast_source_sha256=Sha256Digest(CONTENT_AST_SOURCE_SHA256),
            st0804_domain_sha256=Sha256Digest(ST0804_DOMAIN_SHA256),
        )


@dataclass(frozen=True, slots=True, repr=False)
class DraftAstBindingV2(_Redacted):
    snapshot: VersionSnapshot
    canonical_ast_sha256: Sha256Digest
    binding_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class PolicyEvaluationEnvelopeV2(_Redacted):
    contract: PolicyContractBindingV2
    draft: DraftAstBindingV2
    coverage_snapshot: ClaimEvidenceSnapshot
    coverage_report: ClaimEvidenceCoverageReport
    coverage_receipt: CoverageRecordReceipt
    recommendation: RecommendationEnvelopeV2
    recommendation_report: RecommendationReportV2
    recommendation_receipt: RecommendationRecordReceipt
    policy_input: PolicyEvaluationInput
    policy_result_sha256: Sha256Digest
    evaluation_input_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class PolicyEvaluationRecordReceiptV2(_Redacted):
    sequence: int
    report_sha256: Sha256Digest
    approval_authorized: bool = False
    apply_authorized: bool = False
    publication_authorized: bool = False
    ranking_override_authorized: bool = False

    def require_valid(self) -> None:
        if (
            type(self.sequence) is not int
            or not 1 <= self.sequence <= (1 << 53) - 1
            or type(self.report_sha256) is not Sha256Digest
            or self.approval_authorized is not False
            or self.apply_authorized is not False
            or self.publication_authorized is not False
            or self.ranking_override_authorized is not False
        ):
            _invalid()


@dataclass(frozen=True, slots=True, repr=False)
class PolicyEvaluationReportV2(_Redacted):
    article_id: ArticleId | None
    article_version_id: ArticleVersionId | None
    article_version_no: int | None
    article_body_sha256: Sha256Digest | None
    canonical_ast_sha256: Sha256Digest | None
    source_packet_version_id: str | None
    source_packet_content_sha256: Sha256Digest | None
    draft_binding_sha256: Sha256Digest | None
    coverage_input_sha256: Sha256Digest | None
    coverage_report_sha256: Sha256Digest | None
    coverage_receipt_sha256: Sha256Digest | None
    complete_claim_set_sha256: Sha256Digest | None
    recommendation_input_sha256: Sha256Digest | None
    recommendation_report_sha256: Sha256Digest | None
    recommendation_receipt_sha256: Sha256Digest | None
    candidate_universe_sha256: Sha256Digest | None
    axis_catalog_sha256: Sha256Digest | None
    fact_set_sha256: Sha256Digest | None
    temporal_scope_sha256: Sha256Digest | None
    decision_context_sha256: Sha256Digest | None
    methodology_sha256: Sha256Digest | None
    policy_result_sha256: Sha256Digest | None
    evaluation_input_sha256: Sha256Digest | None
    status: PolicyEvaluationStatusV2
    findings: tuple[PolicyFindingCodeV2, ...]
    legacy_status: LocalEvaluationStatus | None
    policy_findings: tuple[PolicyFinding, ...]
    waiver_evaluations: tuple[WaiverEvaluation, ...]
    raw_quality_score: str | None
    quality_threshold_met: bool | None
    quality_floors_met: bool | None
    policy_rules_passed: bool | None
    zero_tolerance_clear: bool | None
    quality_gates_passed: bool | None
    predecessors_available: bool | None
    local_eligibility: bool
    finding_proposal_only: bool
    waiver_proposal_only: bool
    approval_authorized: bool
    waiver_apply_authorized: bool
    merge_authorized: bool
    recommendation_override_authorized: bool
    ranking_override_authorized: bool
    publication_authorized: bool
    activation_authorized: bool
    production_eligible: bool
    formal_tst_019_status: ExecutionStatus
    formal_tst_020_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    publication_status: ExecutionStatus
    production_status: ExecutionStatus
    report_sha256: Sha256Digest

    @property
    def locally_evaluated(self) -> bool:
        return self.status is PolicyEvaluationStatusV2.LOCAL_EVALUATED

    def canonical_bytes(self) -> bytes:
        return _report_bytes(self, include_digest=True)

    def require_valid(self) -> None:
        if (
            type(self.status) is not PolicyEvaluationStatusV2
            or type(self.findings) is not tuple
            or len(self.findings) != len(set(self.findings))
            or any(type(item) is not PolicyFindingCodeV2 for item in self.findings)
            or type(self.policy_findings) is not tuple
            or len(self.policy_findings) > len(POLICY_DEFINITIONS)
            or type(self.waiver_evaluations) is not tuple
            or len(self.waiver_evaluations) > len(POLICY_DEFINITIONS)
            or self.finding_proposal_only is not True
            or self.waiver_proposal_only is not True
            or any(
                value is not False
                for value in (
                    self.approval_authorized,
                    self.waiver_apply_authorized,
                    self.merge_authorized,
                    self.recommendation_override_authorized,
                    self.ranking_override_authorized,
                    self.publication_authorized,
                    self.activation_authorized,
                    self.production_eligible,
                )
            )
            or any(
                value is not ExecutionStatus.NOT_EXECUTED
                for value in (
                    self.formal_tst_019_status,
                    self.formal_tst_020_status,
                    self.live_validation_status,
                    self.staging_status,
                    self.release_status,
                    self.publication_status,
                    self.production_status,
                )
            )
            or type(self.report_sha256) is not Sha256Digest
        ):
            _invalid()
        if self.status is PolicyEvaluationStatusV2.LOCAL_EVALUATED:
            if (
                self.findings
                or not self.local_eligibility
                or self.legacy_status is not LocalEvaluationStatus.EVALUATED
                or any(
                    value is None
                    for value in (
                        self.article_id,
                        self.article_version_id,
                        self.article_version_no,
                        self.article_body_sha256,
                        self.canonical_ast_sha256,
                        self.source_packet_version_id,
                        self.source_packet_content_sha256,
                        self.draft_binding_sha256,
                        self.coverage_input_sha256,
                        self.coverage_report_sha256,
                        self.coverage_receipt_sha256,
                        self.complete_claim_set_sha256,
                        self.recommendation_input_sha256,
                        self.recommendation_report_sha256,
                        self.recommendation_receipt_sha256,
                        self.candidate_universe_sha256,
                        self.axis_catalog_sha256,
                        self.fact_set_sha256,
                        self.temporal_scope_sha256,
                        self.decision_context_sha256,
                        self.methodology_sha256,
                        self.policy_result_sha256,
                        self.evaluation_input_sha256,
                    )
                )
            ):
                _invalid()
        if (
            self.status is PolicyEvaluationStatusV2.UNEVALUABLE
            and self.local_eligibility
        ):
            _invalid()
        expected = hashlib.sha256(_report_bytes(self, include_digest=False)).hexdigest()
        if self.report_sha256.value != expected:
            _invalid()


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        _invalid()


def _digest(value: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(value)).hexdigest())


def _contract_material(value: PolicyContractBindingV2) -> dict[str, object]:
    return {
        "article_lifecycle_sha256": value.article_lifecycle_sha256.value,
        "claim_evidence_policy_sha256": value.claim_evidence_policy_sha256.value,
        "content_ast_source_sha256": value.content_ast_source_sha256.value,
        "contract_id": value.contract_id,
        "contract_version": value.contract_version,
        "evaluator_version": value.evaluator_version,
        "legacy_policy_engine_sha256": value.legacy_policy_engine_sha256.value,
        "policy_catalog_sha256": value.policy_catalog_sha256.value,
        "quality_catalog_sha256": value.quality_catalog_sha256.value,
        "recommendation_methodology_sha256": (
            value.recommendation_methodology_sha256.value
        ),
        "st0804_domain_sha256": value.st0804_domain_sha256.value,
    }


def draft_ast_sha256(value: VersionSnapshot) -> Sha256Digest:
    if type(value) is not VersionSnapshot:
        _invalid()
    encoded = dump_content_ast_json(value.content_ast).encode("utf-8")
    if not encoded or len(encoded) > _MAX_AST_BYTES:
        _invalid()
    return Sha256Digest(hashlib.sha256(encoded).hexdigest())


def draft_binding_sha256(value: VersionSnapshot) -> Sha256Digest:
    ast_sha256 = draft_ast_sha256(value)
    return _digest(
        {
            "article_id": str(value.article_id),
            "article_type": value.article_type.value,
            "article_version_id": str(value.version_id),
            "article_version_no": value.version_no,
            "body_sha256": value.body_sha256.value,
            "canonical_ast_sha256": ast_sha256.value,
            "profile": "ST0805_DRAFT_AST_BINDING_V2",
            "source_packet_version_id": str(value.source_packet_version_id),
            "state": value.state.value,
            "title": value.title,
        }
    )


def coverage_receipt_sha256(value: CoverageRecordReceipt) -> Sha256Digest:
    try:
        value.require_valid()
    except Exception:
        _invalid()
    return _digest(
        {
            "profile": "ST0805_ST0605_COVERAGE_RECEIPT_V2",
            "publication_authorized": value.publication_authorized,
            "report_sha256": value.report_sha256.value,
            "sequence": value.sequence,
        }
    )


def recommendation_receipt_sha256(
    value: RecommendationRecordReceipt,
) -> Sha256Digest:
    try:
        value.require_valid()
    except Exception:
        _invalid()
    return _digest(
        {
            "profile": "ST0805_ST0804_RECOMMENDATION_RECEIPT_V2",
            "publication_authorized": value.publication_authorized,
            "ranking_authorized": value.ranking_authorized,
            "report_sha256": value.report_sha256.value,
            "sequence": value.sequence,
        }
    )


def policy_result_sha256(value: PolicyEvaluationResult) -> Sha256Digest:
    if type(value) is not PolicyEvaluationResult:
        _invalid()
    try:
        encoded = value.local_result_json.encode("ascii")
    except Exception:
        _invalid()
    if (
        not encoded
        or len(encoded) > _MAX_RESULT_BYTES
        or hashlib.sha256(encoded).hexdigest() != value.local_result_digest
    ):
        _invalid()
    return _digest(
        {
            "legacy_local_result_digest": value.local_result_digest,
            "legacy_serialization_profile": value.local_result_serialization_profile,
            "profile": "ST0805_POLICY_RESULT_BINDING_V2",
        }
    )


def policy_evaluation_input_sha256(
    *,
    contract: PolicyContractBindingV2,
    draft: DraftAstBindingV2,
    coverage_report: ClaimEvidenceCoverageReport,
    coverage_receipt: CoverageRecordReceipt,
    recommendation_report: RecommendationReportV2,
    recommendation_receipt: RecommendationRecordReceipt,
    policy_result_digest: Sha256Digest,
) -> Sha256Digest:
    if type(contract) is not PolicyContractBindingV2:
        _invalid()
    return _digest(
        {
            "contract": _contract_material(contract),
            "coverage_input_sha256": (
                None
                if coverage_report.evaluation_input_sha256 is None
                else coverage_report.evaluation_input_sha256.value
            ),
            "coverage_receipt_sha256": coverage_receipt_sha256(coverage_receipt).value,
            "coverage_report_sha256": coverage_report.report_sha256.value,
            "draft_binding_sha256": draft.binding_sha256.value,
            "policy_result_sha256": policy_result_digest.value,
            "profile": "ST0805_POLICY_EVALUATION_INPUT_V2",
            "recommendation_input_sha256": (
                None
                if recommendation_report.recommendation_input_sha256 is None
                else recommendation_report.recommendation_input_sha256.value
            ),
            "recommendation_receipt_sha256": recommendation_receipt_sha256(
                recommendation_receipt
            ).value,
            "recommendation_report_sha256": recommendation_report.report_sha256.value,
        }
    )


def _coverage_collections_bounded(value: ClaimEvidenceSnapshot) -> bool:
    return all(
        type(items) is tuple and len(items) <= _MAX_COVERAGE_COLLECTION
        for items in (
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
    )


def _policy_collections_bounded(value: PolicyEvaluationInput) -> bool:
    expected = (
        (value.predecessors, len(PredecessorStory)),
        (value.policy_assessments, len(POLICY_DEFINITIONS)),
        (value.axis_assessments, len(QUALITY_AXIS_DEFINITIONS)),
        (value.zero_tolerance_assessments, len(ZERO_TOLERANCE_LABELS)),
        (value.gate_assessments, len(QUALITY_GATE_DEFINITIONS)),
    )
    if any(type(items) is not tuple or len(items) != size for items, size in expected):
        return False
    if type(value.waiver_attempts) is not tuple or len(value.waiver_attempts) > len(
        POLICY_DEFINITIONS
    ):
        return False
    evidence_collections = (
        *(item.evidence for item in value.policy_assessments),
        *(item.evidence for item in value.axis_assessments),
        *(item.evidence for item in value.zero_tolerance_assessments),
        *(item.evidence for item in value.gate_assessments),
        *(item.evidence for item in value.waiver_attempts),
    )
    return all(
        type(items) is tuple and len(items) <= _MAX_EVIDENCE_PER_RECORD
        for items in evidence_collections
    )


def _reference_alias(value: object) -> bool:
    try:
        if type(value) is not str:
            return True
        normalized = unicodedata.normalize("NFKC", value).casefold()
        compact = "".join(character for character in normalized if character.isalnum())
        return (
            prohibited_ranking_alias(value)
            or any(term in normalized for term in ("料率", "報酬", "収益", "利益"))
            or any(
                term in compact
                for term in (
                    "affiliate",
                    "commission",
                    "finance",
                    "financial",
                    "reward",
                    "revenue",
                    "profit",
                    "sponsorbenefit",
                    "epc",
                    "rpm",
                )
            )
        )
    except Exception:
        return True


def _policy_alias_present(value: PolicyEvaluationInput) -> bool:
    dynamic: list[object] = [value.article_version_id.value]
    for predecessor in value.predecessors:
        dynamic.append(predecessor.article_version_id.value)
        dynamic.append(predecessor.provenance.reference.value)
        if predecessor.result is not None:
            dynamic.append(predecessor.result.reference.value)
    for policy_assessment in value.policy_assessments:
        dynamic.extend(
            (
                policy_assessment.stage,
                policy_assessment.article_version_id.value,
                policy_assessment.target.target_ref.value,
                policy_assessment.detector.reference.value,
            )
        )
        dynamic.extend(item.reference.value for item in policy_assessment.evidence)
    for axis_assessment in value.axis_assessments:
        dynamic.extend(
            (
                axis_assessment.axis_code,
                axis_assessment.article_version_id.value,
                axis_assessment.evaluator.reference.value,
            )
        )
        dynamic.extend(item.reference.value for item in axis_assessment.evidence)
    for signal_assessment in value.zero_tolerance_assessments:
        dynamic.extend(
            (
                signal_assessment.article_version_id.value,
                signal_assessment.detector.reference.value,
            )
        )
        dynamic.extend(item.reference.value for item in signal_assessment.evidence)
    for gate_assessment in value.gate_assessments:
        dynamic.extend(
            (
                gate_assessment.stage,
                gate_assessment.article_version_id.value,
                gate_assessment.evaluator.reference.value,
            )
        )
        dynamic.extend(item.reference.value for item in gate_assessment.evidence)
    for attempt in value.waiver_attempts:
        dynamic.extend(
            (
                attempt.article_version_id.value,
                attempt.scope_ref.value,
                attempt.reason.reference.value,
                attempt.compliance_approver.reference.value,
                attempt.audit_event.reference.value,
            )
        )
        dynamic.extend(item.reference.value for item in attempt.evidence)
    return any(_reference_alias(item) for item in dynamic)


def _predecessor_binding_matches(
    value: PolicyEvaluationInput,
    *,
    draft: DraftAstBindingV2,
    coverage_report: ClaimEvidenceCoverageReport,
    coverage_receipt: CoverageRecordReceipt,
    recommendation_report: RecommendationReportV2,
    recommendation_receipt: RecommendationRecordReceipt,
) -> bool:
    expected = {
        PredecessorStory.ST_0605: (
            coverage_report.report_sha256.value,
            coverage_receipt_sha256(coverage_receipt).value,
        ),
        PredecessorStory.ST_0802: (
            draft.binding_sha256.value,
            draft.canonical_ast_sha256.value,
        ),
        PredecessorStory.ST_0804: (
            recommendation_report.report_sha256.value,
            recommendation_receipt_sha256(recommendation_receipt).value,
        ),
    }
    records = {item.story_id: item for item in value.predecessors}
    if len(records) != len(expected):
        return False
    for story, (result_hash, provenance_hash) in expected.items():
        record = records.get(story)
        if (
            record is None
            or record.state is not PredecessorState.AVAILABLE
            or record.result is None
            or record.result.sha256.value != result_hash
            or record.provenance.sha256.value != provenance_hash
        ):
            return False
    return True


def _report_payload(
    value: PolicyEvaluationReportV2,
    *,
    include_digest: bool,
) -> dict[str, object]:
    def digest(item: Sha256Digest | None) -> str | None:
        return None if item is None else item.value

    payload: dict[str, object] = {
        "activation_authorized": value.activation_authorized,
        "approval_authorized": value.approval_authorized,
        "article_body_sha256": digest(value.article_body_sha256),
        "article_id": None if value.article_id is None else str(value.article_id.value),
        "article_version_id": (
            None
            if value.article_version_id is None
            else str(value.article_version_id.value)
        ),
        "article_version_no": value.article_version_no,
        "axis_catalog_sha256": digest(value.axis_catalog_sha256),
        "candidate_universe_sha256": digest(value.candidate_universe_sha256),
        "canonical_ast_sha256": digest(value.canonical_ast_sha256),
        "complete_claim_set_sha256": digest(value.complete_claim_set_sha256),
        "coverage_input_sha256": digest(value.coverage_input_sha256),
        "coverage_receipt_sha256": digest(value.coverage_receipt_sha256),
        "coverage_report_sha256": digest(value.coverage_report_sha256),
        "decision_context_sha256": digest(value.decision_context_sha256),
        "draft_binding_sha256": digest(value.draft_binding_sha256),
        "evaluation_input_sha256": digest(value.evaluation_input_sha256),
        "fact_set_sha256": digest(value.fact_set_sha256),
        "finding_proposal_only": value.finding_proposal_only,
        "findings": [item.value for item in value.findings],
        "formal_tst_019_status": value.formal_tst_019_status.value,
        "formal_tst_020_status": value.formal_tst_020_status.value,
        "legacy_status": (
            None if value.legacy_status is None else value.legacy_status.value
        ),
        "live_validation_status": value.live_validation_status.value,
        "local_eligibility": value.local_eligibility,
        "merge_authorized": value.merge_authorized,
        "methodology_sha256": digest(value.methodology_sha256),
        "policy_findings": [
            {
                "blocking": item.is_blocking,
                "policy_id": item.policy_id,
                "resolution": item.resolution.value,
                "severity": item.severity.value,
            }
            for item in value.policy_findings
        ],
        "policy_result_sha256": digest(value.policy_result_sha256),
        "policy_rules_passed": value.policy_rules_passed,
        "production_eligible": value.production_eligible,
        "production_status": value.production_status.value,
        "publication_authorized": value.publication_authorized,
        "publication_status": value.publication_status.value,
        "quality_floors_met": value.quality_floors_met,
        "quality_gates_passed": value.quality_gates_passed,
        "quality_threshold_met": value.quality_threshold_met,
        "ranking_override_authorized": value.ranking_override_authorized,
        "raw_quality_score": value.raw_quality_score,
        "recommendation_input_sha256": digest(value.recommendation_input_sha256),
        "recommendation_override_authorized": (
            value.recommendation_override_authorized
        ),
        "recommendation_receipt_sha256": digest(value.recommendation_receipt_sha256),
        "recommendation_report_sha256": digest(value.recommendation_report_sha256),
        "release_status": value.release_status.value,
        "source_packet_version_id": value.source_packet_version_id,
        "source_packet_content_sha256": digest(value.source_packet_content_sha256),
        "staging_status": value.staging_status.value,
        "status": value.status.value,
        "temporal_scope_sha256": digest(value.temporal_scope_sha256),
        "waiver_apply_authorized": value.waiver_apply_authorized,
        "waiver_evaluations": [
            {
                "disposition": item.disposition.value,
                "effective": item.effective,
                "policy_id": item.policy_id,
            }
            for item in value.waiver_evaluations
        ],
        "waiver_proposal_only": value.waiver_proposal_only,
        "zero_tolerance_clear": value.zero_tolerance_clear,
        "predecessors_available": value.predecessors_available,
    }
    if include_digest:
        payload["report_sha256"] = value.report_sha256.value
    return payload


def _report_bytes(value: PolicyEvaluationReportV2, *, include_digest: bool) -> bytes:
    return _canonical_bytes(_report_payload(value, include_digest=include_digest))


def _make_report(
    *,
    status: PolicyEvaluationStatusV2,
    findings: set[PolicyFindingCodeV2],
    draft: DraftAstBindingV2 | None = None,
    coverage_report: ClaimEvidenceCoverageReport | None = None,
    coverage_receipt: CoverageRecordReceipt | None = None,
    recommendation_report: RecommendationReportV2 | None = None,
    recommendation_receipt: RecommendationRecordReceipt | None = None,
    legacy: PolicyEvaluationResult | None = None,
    policy_digest: Sha256Digest | None = None,
    input_digest: Sha256Digest | None = None,
) -> PolicyEvaluationReportV2:
    report = PolicyEvaluationReportV2(
        article_id=(None if draft is None else ArticleId(draft.snapshot.article_id)),
        article_version_id=(
            None if draft is None else ArticleVersionId(draft.snapshot.version_id)
        ),
        article_version_no=None if draft is None else draft.snapshot.version_no,
        article_body_sha256=(
            None if draft is None else Sha256Digest(draft.snapshot.body_sha256.value)
        ),
        canonical_ast_sha256=(None if draft is None else draft.canonical_ast_sha256),
        source_packet_version_id=(
            None if draft is None else str(draft.snapshot.source_packet_version_id)
        ),
        source_packet_content_sha256=(
            None
            if coverage_report is None
            else coverage_report.source_packet_content_sha256
        ),
        draft_binding_sha256=None if draft is None else draft.binding_sha256,
        coverage_input_sha256=(
            None if coverage_report is None else coverage_report.evaluation_input_sha256
        ),
        coverage_report_sha256=(
            None if coverage_report is None else coverage_report.report_sha256
        ),
        coverage_receipt_sha256=(
            None
            if coverage_receipt is None
            else coverage_receipt_sha256(coverage_receipt)
        ),
        complete_claim_set_sha256=(
            None
            if coverage_report is None
            else coverage_report.complete_claim_set_sha256
        ),
        recommendation_input_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.recommendation_input_sha256
        ),
        recommendation_report_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.report_sha256
        ),
        recommendation_receipt_sha256=(
            None
            if recommendation_receipt is None
            else recommendation_receipt_sha256(recommendation_receipt)
        ),
        candidate_universe_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.candidate_universe_sha256
        ),
        axis_catalog_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.axis_catalog_sha256
        ),
        fact_set_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.fact_set_sha256
        ),
        temporal_scope_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.temporal_scope_sha256
        ),
        decision_context_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.decision_context_sha256
        ),
        methodology_sha256=(
            None
            if recommendation_report is None
            else recommendation_report.methodology_sha256
        ),
        policy_result_sha256=policy_digest,
        evaluation_input_sha256=input_digest,
        status=status,
        findings=tuple(sorted(findings, key=lambda item: item.value)),
        legacy_status=None if legacy is None else legacy.status,
        policy_findings=() if legacy is None else legacy.policy_findings,
        waiver_evaluations=() if legacy is None else legacy.waiver_evaluations,
        raw_quality_score=(
            None
            if legacy is None or legacy.raw_quality_score is None
            else format(legacy.raw_quality_score, "f")
        ),
        quality_threshold_met=(
            None if legacy is None else legacy.quality_threshold_met
        ),
        quality_floors_met=None if legacy is None else legacy.quality_floors_met,
        policy_rules_passed=None if legacy is None else legacy.policy_rules_passed,
        zero_tolerance_clear=None if legacy is None else legacy.zero_tolerance_clear,
        quality_gates_passed=(None if legacy is None else legacy.quality_gates_passed),
        predecessors_available=(
            None if legacy is None else legacy.predecessors_available
        ),
        local_eligibility=bool(
            status is PolicyEvaluationStatusV2.LOCAL_EVALUATED
            and legacy is not None
            and legacy.local_eligibility
        ),
        finding_proposal_only=True,
        waiver_proposal_only=True,
        approval_authorized=False,
        waiver_apply_authorized=False,
        merge_authorized=False,
        recommendation_override_authorized=False,
        ranking_override_authorized=False,
        publication_authorized=False,
        activation_authorized=False,
        production_eligible=False,
        formal_tst_019_status=ExecutionStatus.NOT_EXECUTED,
        formal_tst_020_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        publication_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
        report_sha256=Sha256Digest("0" * 64),
    )
    result = PolicyEvaluationReportV2(
        **{
            field: getattr(report, field)
            for field in report.__dataclass_fields__
            if field != "report_sha256"
        },
        report_sha256=Sha256Digest(
            hashlib.sha256(_report_bytes(report, include_digest=False)).hexdigest()
        ),
    )
    result.require_valid()
    return result


def unavailable_policy_report(
    finding: PolicyFindingCodeV2 = PolicyFindingCodeV2.INPUT_TYPE_INVALID,
) -> PolicyEvaluationReportV2:
    if type(finding) is not PolicyFindingCodeV2:
        finding = PolicyFindingCodeV2.INPUT_TYPE_INVALID
    return _make_report(
        status=PolicyEvaluationStatusV2.UNEVALUABLE,
        findings={finding},
    )


def evaluate_editorial_policy_v2(value: object) -> PolicyEvaluationReportV2:
    """Re-evaluate and bind one exact, local-only ST-0805 V2 envelope."""

    if type(value) is not PolicyEvaluationEnvelopeV2:
        return unavailable_policy_report()
    findings: set[PolicyFindingCodeV2] = set()
    if value.contract != PolicyContractBindingV2.current():
        findings.add(PolicyFindingCodeV2.CONTRACT_BINDING_MISMATCH)
    if type(value.draft) is not DraftAstBindingV2:
        return unavailable_policy_report(PolicyFindingCodeV2.DRAFT_BINDING_MISMATCH)
    try:
        draft_hash = draft_ast_sha256(value.draft.snapshot)
        draft_binding = draft_binding_sha256(value.draft.snapshot)
    except Exception:
        return unavailable_policy_report(PolicyFindingCodeV2.DRAFT_BINDING_MISMATCH)
    if (
        value.draft.snapshot.state is not ArticleVersionState.DRAFT
        or value.draft.snapshot.body_sha256
        != BodySha256.of(value.draft.snapshot.content_ast)
        or value.draft.canonical_ast_sha256 != draft_hash
        or value.draft.binding_sha256 != draft_binding
    ):
        findings.add(PolicyFindingCodeV2.DRAFT_BINDING_MISMATCH)
    if not _coverage_collections_bounded(value.coverage_snapshot):
        return unavailable_policy_report(PolicyFindingCodeV2.INPUT_BOUNDS_EXCEEDED)
    if not _policy_collections_bounded(value.policy_input):
        return unavailable_policy_report(PolicyFindingCodeV2.INPUT_BOUNDS_EXCEEDED)
    if _policy_alias_present(value.policy_input):
        findings.add(PolicyFindingCodeV2.PROHIBITED_AFFILIATE_INPUT)

    try:
        coverage = evaluate_claim_evidence(value.coverage_snapshot)
        coverage.require_valid()
        value.coverage_report.require_valid()
        value.coverage_receipt.require_valid()
    except Exception:
        return _make_report(
            status=PolicyEvaluationStatusV2.UNEVALUABLE,
            findings={PolicyFindingCodeV2.COVERAGE_STRUCTURAL_INVALID},
            draft=value.draft,
        )
    if coverage.canonical_bytes() != value.coverage_report.canonical_bytes():
        findings.add(PolicyFindingCodeV2.COVERAGE_REPORT_MISMATCH)
    if value.coverage_receipt.report_sha256 != coverage.report_sha256:
        findings.add(PolicyFindingCodeV2.RECEIPT_INVALID)
    if coverage.status is CoverageStatus.UNEVALUABLE:
        findings.add(PolicyFindingCodeV2.COVERAGE_UNEVALUABLE)
    elif coverage.status is CoverageStatus.BLOCK:
        findings.add(PolicyFindingCodeV2.COVERAGE_BLOCKED)

    try:
        recommendation = evaluate_recommendations_v2(value.recommendation)
        recommendation.require_valid()
        value.recommendation_report.require_valid()
        value.recommendation_receipt.require_valid()
    except Exception:
        return _make_report(
            status=PolicyEvaluationStatusV2.UNEVALUABLE,
            findings={PolicyFindingCodeV2.RECOMMENDATION_STRUCTURAL_INVALID},
            draft=value.draft,
            coverage_report=coverage,
            coverage_receipt=value.coverage_receipt,
        )
    if (
        recommendation.canonical_bytes()
        != value.recommendation_report.canonical_bytes()
    ):
        findings.add(PolicyFindingCodeV2.RECOMMENDATION_REPORT_MISMATCH)
    if value.recommendation_receipt.report_sha256 != recommendation.report_sha256:
        findings.add(PolicyFindingCodeV2.RECEIPT_INVALID)
    if recommendation.status is RecommendationEvaluationStatus.UNEVALUABLE:
        findings.add(PolicyFindingCodeV2.RECOMMENDATION_UNEVALUABLE)
    elif recommendation.status is RecommendationEvaluationStatus.BLOCK:
        findings.add(PolicyFindingCodeV2.RECOMMENDATION_BLOCKED)

    draft_snapshot = value.draft.snapshot
    coverage_article = value.coverage_snapshot.article
    if (
        coverage_article.article_version_id.value != draft_snapshot.version_id
        or coverage_article.article_body_sha256.value
        != draft_snapshot.body_sha256.value
        or coverage_article.source_packet_version_id.value
        != draft_snapshot.source_packet_version_id
        or coverage.complete_claim_set_sha256 is None
        or coverage.complete_claim_set_sha256
        != coverage_article.complete_claim_set_sha256
        or not any(
            item.kind is ValidationAttestationKind.COMPARISON
            for item in value.coverage_snapshot.attestations
        )
    ):
        findings.add(PolicyFindingCodeV2.COVERAGE_CORE_MISMATCH)
    comparison_article = value.recommendation.comparison.comparison.article
    if (
        comparison_article.article_id.value != draft_snapshot.article_id
        or comparison_article.article_version_id.value != draft_snapshot.version_id
        or comparison_article.article_version_no != draft_snapshot.version_no
        or comparison_article.article_body_sha256.value
        != draft_snapshot.body_sha256.value
        or comparison_article.source_packet_version_id.value
        != draft_snapshot.source_packet_version_id
        or comparison_article.complete_claim_set_sha256
        != coverage_article.complete_claim_set_sha256
        or recommendation.article_id is None
        or recommendation.article_id.value != draft_snapshot.article_id
        or recommendation.article_version_id is None
        or recommendation.article_version_id.value != draft_snapshot.version_id
    ):
        findings.add(PolicyFindingCodeV2.RECOMMENDATION_CORE_MISMATCH)

    legacy = evaluate_editorial_policy(value.policy_input)
    if legacy.status is LocalEvaluationStatus.INVALID_INPUT:
        findings.add(PolicyFindingCodeV2.POLICY_INPUT_INVALID)
    elif legacy.status is LocalEvaluationStatus.NOT_EVALUATED:
        findings.add(PolicyFindingCodeV2.POLICY_NOT_EVALUATED)
    elif not legacy.local_eligibility:
        findings.add(PolicyFindingCodeV2.POLICY_BLOCKED)
    try:
        policy_digest = policy_result_sha256(legacy)
    except Exception:
        return _make_report(
            status=PolicyEvaluationStatusV2.UNEVALUABLE,
            findings={PolicyFindingCodeV2.POLICY_INPUT_INVALID},
            draft=value.draft,
            coverage_report=coverage,
            coverage_receipt=value.coverage_receipt,
            recommendation_report=recommendation,
            recommendation_receipt=value.recommendation_receipt,
            legacy=legacy,
        )
    if policy_digest != value.policy_result_sha256:
        findings.add(PolicyFindingCodeV2.POLICY_INPUT_HASH_MISMATCH)
    if not _predecessor_binding_matches(
        value.policy_input,
        draft=value.draft,
        coverage_report=coverage,
        coverage_receipt=value.coverage_receipt,
        recommendation_report=recommendation,
        recommendation_receipt=value.recommendation_receipt,
    ):
        findings.add(PolicyFindingCodeV2.POLICY_INPUT_HASH_MISMATCH)
    try:
        input_digest = policy_evaluation_input_sha256(
            contract=value.contract,
            draft=value.draft,
            coverage_report=coverage,
            coverage_receipt=value.coverage_receipt,
            recommendation_report=recommendation,
            recommendation_receipt=value.recommendation_receipt,
            policy_result_digest=policy_digest,
        )
    except Exception:
        return unavailable_policy_report(
            PolicyFindingCodeV2.DECLARED_INPUT_HASH_MISMATCH
        )
    if input_digest != value.evaluation_input_sha256:
        findings.add(PolicyFindingCodeV2.DECLARED_INPUT_HASH_MISMATCH)

    unevaluable = {
        PolicyFindingCodeV2.INPUT_BOUNDS_EXCEEDED,
        PolicyFindingCodeV2.COVERAGE_STRUCTURAL_INVALID,
        PolicyFindingCodeV2.COVERAGE_UNEVALUABLE,
        PolicyFindingCodeV2.RECOMMENDATION_STRUCTURAL_INVALID,
        PolicyFindingCodeV2.RECOMMENDATION_UNEVALUABLE,
        PolicyFindingCodeV2.POLICY_INPUT_INVALID,
        PolicyFindingCodeV2.POLICY_NOT_EVALUATED,
    }
    status = (
        PolicyEvaluationStatusV2.UNEVALUABLE
        if findings & unevaluable
        else PolicyEvaluationStatusV2.BLOCK
        if findings
        else PolicyEvaluationStatusV2.LOCAL_EVALUATED
    )
    return _make_report(
        status=status,
        findings=findings,
        draft=value.draft,
        coverage_report=coverage,
        coverage_receipt=value.coverage_receipt,
        recommendation_report=recommendation,
        recommendation_receipt=value.recommendation_receipt,
        legacy=legacy,
        policy_digest=policy_digest,
        input_digest=input_digest,
    )


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "EVALUATOR_VERSION",
    "LOCAL_STATUS",
    "DraftAstBindingV2",
    "ExecutionStatus",
    "PolicyContractBindingV2",
    "PolicyEvaluationEnvelopeV2",
    "PolicyEvaluationRecordReceiptV2",
    "PolicyEvaluationReportV2",
    "PolicyEvaluationStatusV2",
    "PolicyFindingCodeV2",
    "PolicyRuntimeValueError",
    "coverage_receipt_sha256",
    "draft_ast_sha256",
    "draft_binding_sha256",
    "evaluate_editorial_policy_v2",
    "policy_evaluation_input_sha256",
    "policy_result_sha256",
    "recommendation_receipt_sha256",
    "unavailable_policy_report",
]
