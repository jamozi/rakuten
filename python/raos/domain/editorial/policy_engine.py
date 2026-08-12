"""Pure deterministic ST-0805 editorial policy evaluation.

The evaluator accepts only strict, pre-resolved local inputs.  It binds the
reviewed editorial-policy and quality-gate catalogs but does not read those
files at runtime, detect article content, resolve evidence, persist findings,
authorize publication, or perform any external action.  Returned serialization
and its digest use the implementation-local ``ST0805_LOCAL_RESULT_V1`` profile;
they are not canonical, audit, formal-test, or release evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, TypeAlias


POLICY_CATALOG_ID = "RAOS-CONTENT-POLICY-001"
POLICY_CATALOG_VERSION = "0.1"
POLICY_BUNDLE_CODE = "content-editorial-policy.jp.v1"
POLICY_CATALOG_SHA256 = (
    "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a"
)
QUALITY_CATALOG_ID = "RAOS-CONTENT-QG-001"
QUALITY_CATALOG_VERSION = "0.1"
QUALITY_MODEL_VERSION = "1.0.0"
QUALITY_CATALOG_SHA256 = (
    "90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb"
)
REVIEW_CHECKLIST_ID = "RAOS-CONTENT-REVIEW-001"
REVIEW_CHECKLIST_VERSION = "1.0.0"
REVIEW_CHECKLIST_SHA256 = (
    "8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63"
)
CONTENT_TEST_MATRIX_SHA256 = (
    "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564"
)
LOCAL_RESULT_SERIALIZATION_PROFILE = "ST0805_LOCAL_RESULT_V1"
PUBLISH_THRESHOLD = Decimal("85")

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,126}\Z", re.ASCII)
_VERSION = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,62}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DECIMAL_MAX_DIGITS = 28
_DECIMAL_MIN_EXPONENT = -12
_DECIMAL_MAX_EXPONENT = 12


class PolicySeverity(str, Enum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"


class PolicyEnforcement(str, Enum):
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"
    SCHEMA = "schema"
    HUMAN = "human"


class PolicyRuleResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class AxisAssessmentState(str, Enum):
    EVALUATED = "EVALUATED"
    NOT_EVALUATED = "NOT_EVALUATED"


class ZeroToleranceState(str, Enum):
    CLEAR = "CLEAR"
    TRIGGERED = "TRIGGERED"
    NOT_EVALUATED = "NOT_EVALUATED"


class GateAssessmentState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class GateFailureAction(str, Enum):
    BLOCK = "BLOCK"
    ROLLBACK_OR_PAUSE = "ROLLBACK_OR_PAUSE"


class PredecessorStory(str, Enum):
    ST_0605 = "ST-0605"
    ST_0802 = "ST-0802"
    ST_0804 = "ST-0804"


class PredecessorState(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class LocalEvaluationStatus(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    NOT_EVALUATED = "NOT_EVALUATED"
    EVALUATED = "EVALUATED"


class FindingResolution(str, Enum):
    UNRESOLVED = "UNRESOLVED"


class FindingTargetType(str, Enum):
    ARTICLE_VERSION = "ARTICLE_VERSION"
    BLOCK = "BLOCK"
    CLAIM = "CLAIM"
    PRODUCT = "PRODUCT"
    OFFER = "OFFER"
    LINK = "LINK"
    SOURCE_PACKET = "SOURCE_PACKET"


class WaiverScopeType(str, Enum):
    FINDING = "FINDING"
    ARTICLE_VERSION = "ARTICLE_VERSION"
    ARTICLE = "ARTICLE"
    CATEGORY = "CATEGORY"


class WaiverAuthorityClaim(str, Enum):
    REQUESTED = "REQUESTED"
    PENDING_HUMAN_AUTHORITY = "PENDING_HUMAN_AUTHORITY"
    APPROVED = "APPROVED"


class WaiverDisposition(str, Enum):
    DENIED_BLOCKER = "DENIED_BLOCKER"
    PENDING_HUMAN_AUTHORITY = "PENDING_HUMAN_AUTHORITY"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class InputFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    COLLECTION_TYPE_INVALID = "COLLECTION_TYPE_INVALID"
    CONTRACT_BINDING_INVALID = "CONTRACT_BINDING_INVALID"
    ARTICLE_VERSION_INVALID = "ARTICLE_VERSION_INVALID"
    EVALUATED_AT_INVALID = "EVALUATED_AT_INVALID"
    PREDECESSOR_RECORD_INVALID = "PREDECESSOR_RECORD_INVALID"
    PREDECESSOR_UNKNOWN = "PREDECESSOR_UNKNOWN"
    PREDECESSOR_DUPLICATE = "PREDECESSOR_DUPLICATE"
    PREDECESSOR_SET_MISMATCH = "PREDECESSOR_SET_MISMATCH"
    PREDECESSOR_BINDING_MISMATCH = "PREDECESSOR_BINDING_MISMATCH"
    PREDECESSOR_STATE_INVALID = "PREDECESSOR_STATE_INVALID"
    POLICY_RECORD_INVALID = "POLICY_RECORD_INVALID"
    POLICY_UNKNOWN = "POLICY_UNKNOWN"
    POLICY_DUPLICATE = "POLICY_DUPLICATE"
    POLICY_SET_MISMATCH = "POLICY_SET_MISMATCH"
    POLICY_BINDING_MISMATCH = "POLICY_BINDING_MISMATCH"
    POLICY_STAGE_MISMATCH = "POLICY_STAGE_MISMATCH"
    POLICY_ARTICLE_MISMATCH = "POLICY_ARTICLE_MISMATCH"
    POLICY_RESULT_INVALID = "POLICY_RESULT_INVALID"
    POLICY_PROOF_INVALID = "POLICY_PROOF_INVALID"
    AXIS_RECORD_INVALID = "AXIS_RECORD_INVALID"
    AXIS_UNKNOWN = "AXIS_UNKNOWN"
    AXIS_DUPLICATE = "AXIS_DUPLICATE"
    AXIS_SET_MISMATCH = "AXIS_SET_MISMATCH"
    AXIS_BINDING_MISMATCH = "AXIS_BINDING_MISMATCH"
    AXIS_ARTICLE_MISMATCH = "AXIS_ARTICLE_MISMATCH"
    AXIS_STATE_INVALID = "AXIS_STATE_INVALID"
    AXIS_SCORE_INVALID = "AXIS_SCORE_INVALID"
    AXIS_PROOF_INVALID = "AXIS_PROOF_INVALID"
    SIGNAL_RECORD_INVALID = "SIGNAL_RECORD_INVALID"
    SIGNAL_UNKNOWN = "SIGNAL_UNKNOWN"
    SIGNAL_DUPLICATE = "SIGNAL_DUPLICATE"
    SIGNAL_SET_MISMATCH = "SIGNAL_SET_MISMATCH"
    SIGNAL_ARTICLE_MISMATCH = "SIGNAL_ARTICLE_MISMATCH"
    SIGNAL_STATE_INVALID = "SIGNAL_STATE_INVALID"
    SIGNAL_PROOF_INVALID = "SIGNAL_PROOF_INVALID"
    GATE_RECORD_INVALID = "GATE_RECORD_INVALID"
    GATE_UNKNOWN = "GATE_UNKNOWN"
    GATE_DUPLICATE = "GATE_DUPLICATE"
    GATE_SET_MISMATCH = "GATE_SET_MISMATCH"
    GATE_BINDING_MISMATCH = "GATE_BINDING_MISMATCH"
    GATE_STAGE_MISMATCH = "GATE_STAGE_MISMATCH"
    GATE_ARTICLE_MISMATCH = "GATE_ARTICLE_MISMATCH"
    GATE_STATE_INVALID = "GATE_STATE_INVALID"
    GATE_PROOF_INVALID = "GATE_PROOF_INVALID"
    WAIVER_RECORD_INVALID = "WAIVER_RECORD_INVALID"
    WAIVER_UNKNOWN_POLICY = "WAIVER_UNKNOWN_POLICY"
    WAIVER_DUPLICATE = "WAIVER_DUPLICATE"
    WAIVER_BINDING_MISMATCH = "WAIVER_BINDING_MISMATCH"
    WAIVER_POLICY_MISMATCH = "WAIVER_POLICY_MISMATCH"
    WAIVER_SCOPE_INVALID = "WAIVER_SCOPE_INVALID"
    WAIVER_AUTHORITY_INVALID = "WAIVER_AUTHORITY_INVALID"
    WAIVER_PROOF_INVALID = "WAIVER_PROOF_INVALID"
    PROHIBITED_INPUT = "PROHIBITED_INPUT"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class PolicyValueConstructionError(ValueError):
    """Closed exact-value construction failure without caller material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_EXACT_VALUE")


def _fail_value_construction() -> NoReturn:
    raise PolicyValueConstructionError() from None


@dataclass(frozen=True, slots=True, repr=False)
class ReferenceId(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _REFERENCE.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class VersionRef(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _VERSION.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class UtcInstant(_Redacted):
    value: datetime

    def __post_init__(self) -> None:
        if not _valid_datetime_value(self.value):
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class BoundReference(_Redacted):
    reference: ReferenceId
    sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class ContractBindings(_Redacted):
    policy_catalog_id: ReferenceId
    policy_catalog_version: VersionRef
    policy_catalog_sha256: Sha256Digest
    quality_catalog_id: ReferenceId
    quality_catalog_version: VersionRef
    quality_model_version: VersionRef
    quality_catalog_sha256: Sha256Digest
    review_checklist_id: ReferenceId
    review_checklist_version: VersionRef
    review_checklist_sha256: Sha256Digest
    content_test_matrix_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class PredecessorAssessment(_Redacted):
    story_id: PredecessorStory
    article_version_id: ReferenceId
    state: PredecessorState
    result: BoundReference | None
    provenance: BoundReference


@dataclass(frozen=True, slots=True, repr=False)
class FindingTarget(_Redacted):
    target_type: FindingTargetType
    target_ref: ReferenceId


@dataclass(frozen=True, slots=True, repr=False)
class PolicyAssessment(_Redacted):
    policy_id: str
    policy_version: VersionRef
    policy_source_sha256: Sha256Digest
    article_version_id: ReferenceId
    stage: str
    result: PolicyRuleResult
    target: FindingTarget
    evidence: tuple[BoundReference, ...]
    detector: BoundReference


@dataclass(frozen=True, slots=True, repr=False)
class QualityAxisAssessment(_Redacted):
    axis_id: str
    axis_code: str
    quality_model_version: VersionRef
    quality_source_sha256: Sha256Digest
    article_version_id: ReferenceId
    state: AxisAssessmentState
    score: Decimal | None
    evidence: tuple[BoundReference, ...]
    evaluator: BoundReference


@dataclass(frozen=True, slots=True, repr=False)
class ZeroToleranceAssessment(_Redacted):
    label: str
    article_version_id: ReferenceId
    state: ZeroToleranceState
    evidence: tuple[BoundReference, ...]
    detector: BoundReference


@dataclass(frozen=True, slots=True, repr=False)
class QualityGateAssessment(_Redacted):
    gate_id: str
    stage: str
    quality_catalog_version: VersionRef
    quality_source_sha256: Sha256Digest
    article_version_id: ReferenceId
    state: GateAssessmentState
    failure_action: GateFailureAction
    evidence: tuple[BoundReference, ...]
    evaluator: BoundReference


@dataclass(frozen=True, slots=True, repr=False)
class WaiverAttempt(_Redacted):
    policy_id: str
    policy_version: VersionRef
    policy_source_sha256: Sha256Digest
    article_version_id: ReferenceId
    scope_type: WaiverScopeType
    scope_ref: ReferenceId
    reason: BoundReference
    evidence: tuple[BoundReference, ...]
    expiry_at: UtcInstant
    compliance_approver: BoundReference
    audit_event: BoundReference
    authority_claim: WaiverAuthorityClaim


@dataclass(frozen=True, slots=True, repr=False)
class PolicyEvaluationInput(_Redacted):
    article_version_id: ReferenceId
    evaluated_at: UtcInstant
    contracts: ContractBindings
    predecessors: tuple[PredecessorAssessment, ...]
    policy_assessments: tuple[PolicyAssessment, ...]
    axis_assessments: tuple[QualityAxisAssessment, ...]
    zero_tolerance_assessments: tuple[ZeroToleranceAssessment, ...]
    gate_assessments: tuple[QualityGateAssessment, ...]
    waiver_attempts: tuple[WaiverAttempt, ...]


@dataclass(frozen=True, slots=True)
class PolicyDefinition:
    policy_id: str
    severity: PolicySeverity
    stage: str
    code: str
    rule: str
    enforcement: PolicyEnforcement


@dataclass(frozen=True, slots=True)
class QualityAxisDefinition:
    axis_id: str
    code: str
    name_ja: str
    weight: Decimal
    blocking_floor: Decimal


@dataclass(frozen=True, slots=True)
class QualityGateDefinition:
    gate_id: str
    stage: str
    name: str
    pass_condition: str
    failure_action: GateFailureAction


@dataclass(frozen=True, slots=True, repr=False)
class PolicyFinding(_Redacted):
    policy_id: str
    policy_version: VersionRef
    policy_source_sha256: Sha256Digest
    severity: PolicySeverity
    is_blocking: bool
    article_version_id: ReferenceId
    stage: str
    target: FindingTarget
    evidence: tuple[BoundReference, ...]
    detector: BoundReference
    evaluated_at: UtcInstant
    rule_result: PolicyRuleResult
    resolution: FindingResolution


@dataclass(frozen=True, slots=True, repr=False)
class WaiverEvaluation(_Redacted):
    policy_id: str
    article_version_id: ReferenceId
    scope_type: WaiverScopeType
    scope_ref: ReferenceId
    disposition: WaiverDisposition
    effective: bool


@dataclass(frozen=True, slots=True, repr=False)
class PolicyEvaluationResult(_Redacted):
    status: LocalEvaluationStatus
    input_findings: tuple[InputFindingCode, ...]
    policy_findings: tuple[PolicyFinding, ...]
    waiver_evaluations: tuple[WaiverEvaluation, ...]
    raw_quality_score: Decimal | None
    quality_threshold_met: bool | None
    quality_floors_met: bool | None
    policy_rules_passed: bool | None
    zero_tolerance_clear: bool | None
    quality_gates_passed: bool | None
    predecessors_available: bool | None
    local_eligibility: bool
    post_publication_required_action: GateFailureAction | None
    local_result_serialization_profile: str
    local_result_json: str
    local_result_digest: str
    publication_authorized: bool
    production_eligible: bool
    formal_test_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus


POLICY_DEFINITIONS: tuple[PolicyDefinition, ...] = (
    PolicyDefinition(
        "POL-CONT-001",
        PolicySeverity.BLOCKER,
        "all",
        "approved_source_packet_required",
        "承認済みSource Packetがない記事生成・公開を禁止する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-002",
        PolicySeverity.BLOCKER,
        "draft",
        "major_claim_evidence",
        "主要ClaimのEvidence Coverageは100%",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-003",
        PolicySeverity.BLOCKER,
        "draft",
        "fabricated_experience",
        "実施記録のない使用・検証・愛用表現を禁止する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-004",
        PolicySeverity.BLOCKER,
        "ingest",
        "rakuten_review_body",
        "楽天レビュー本文の取得・保存・要約・変形・依拠を禁止する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-005",
        PolicySeverity.BLOCKER,
        "recommendation",
        "affiliate_bias",
        "料率・EPC・RPM・報酬・利益を推薦入力へ含めない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-006",
        PolicySeverity.BLOCKER,
        "content_ast",
        "raw_html",
        "任意HTML、Script、iframe、Style、Event Handlerを禁止する",
        PolicyEnforcement.SCHEMA,
    ),
    PolicyDefinition(
        "POL-CONT-007",
        PolicySeverity.BLOCKER,
        "content_ast",
        "manual_affiliate_url",
        "Affiliate URLの手入力を禁止し、Offer/Link Resourceから解決する",
        PolicyEnforcement.SCHEMA,
    ),
    PolicyDefinition(
        "POL-CONT-008",
        PolicySeverity.BLOCKER,
        "render",
        "disclosure_top",
        "広告・アフィリエイト関係を記事上部の初回表示範囲で明示する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-009",
        PolicySeverity.BLOCKER,
        "render",
        "cta_destination",
        "CTAは楽天市場への遷移であることを明示する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-010",
        PolicySeverity.BLOCKER,
        "render",
        "paid_link_rel",
        "Affiliate Linkへrel=sponsoredを付与する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-011",
        PolicySeverity.BLOCKER,
        "render",
        "direct_affiliate_link",
        "自社RedirectでAffiliate URLを中継・改変しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-012",
        PolicySeverity.BLOCKER,
        "render",
        "rakuten_api_credit",
        "楽天API利用時の指定クレジットを共通Rendererへ表示する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-013",
        PolicySeverity.BLOCKER,
        "media",
        "rakuten_image_integrity",
        "楽天提供画像の改変、文字重畳、切り抜き、縦横比破壊を禁止する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-014",
        PolicySeverity.BLOCKER,
        "draft",
        "unsupported_superlative",
        "母集団・範囲・時点がない最上級・唯一性を禁止する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-015",
        PolicySeverity.BLOCKER,
        "publication",
        "stale_critical_fact",
        "鮮度期限を超えた価格・在庫・リンク・主要仕様を最新として表示しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-016",
        PolicySeverity.BLOCKER,
        "draft",
        "product_identity",
        "商品、型番、容量、色、セット、ショップOfferの同定不一致を禁止する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-017",
        PolicySeverity.BLOCKER,
        "scope",
        "high_risk_claim",
        "MVPで医療・法務・金融・安全性の高リスク助言を扱わない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-018",
        PolicySeverity.BLOCKER,
        "publication",
        "human_approval",
        "人間の明示承認なしに公開しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-019",
        PolicySeverity.MAJOR,
        "plan",
        "one_primary_intent",
        "一記事一主要意思決定・一主要Intent Clusterを維持する",
        PolicyEnforcement.HUMAN,
    ),
    PolicyDefinition(
        "POL-CONT-020",
        PolicySeverity.MAJOR,
        "plan",
        "scaled_thin_pages",
        "検索語、Tag、条件の組合せだけで低価値ページを量産しない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-021",
        PolicySeverity.MAJOR,
        "draft",
        "competitor_copy",
        "競合記事は発見専用とし、根拠・転載・近似言い換えに使用しない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-022",
        PolicySeverity.MAJOR,
        "draft",
        "balanced_tradeoffs",
        "推薦候補の不向き条件・制約・トレードオフを隠さない",
        PolicyEnforcement.HUMAN,
    ),
    PolicyDefinition(
        "POL-CONT-023",
        PolicySeverity.MAJOR,
        "draft",
        "uncertainty_disclosure",
        "不明・競合・欠損を推測で埋めず、表示またはClaim除外する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-024",
        PolicySeverity.MAJOR,
        "seo",
        "unique_metadata",
        "Title、H1、Meta Descriptionをページ固有かつ内容一致にする",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-025",
        PolicySeverity.BLOCKER,
        "seo",
        "index_state",
        "Draft/Preview/noindexページをSitemapへ含めず、公開CanonicalのみIndexableにする",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-026",
        PolicySeverity.BLOCKER,
        "structured_data",
        "visible_match",
        "JSON-LDと可視本文の不一致、存在しないRating/Review/Offer補完を禁止する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-027",
        PolicySeverity.MAJOR,
        "structured_data",
        "multi_product_product_markup",
        "複数商品記事にProduct Product Snippet用Markupを出さない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-028",
        PolicySeverity.MAJOR,
        "structured_data",
        "faqpage_disabled",
        "可視FAQは許可するがFAQPage JSON-LDを生成しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-029",
        PolicySeverity.MAJOR,
        "structured_data",
        "rakuten_rating_markup",
        "楽天の平均評価・件数からReview/AggregateRating JSON-LDを生成しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-030",
        PolicySeverity.MAJOR,
        "seo",
        "query_variant_consolidation",
        "意味が同じ検索語Variantは単一Canonical記事へ統合する",
        PolicyEnforcement.HUMAN,
    ),
    PolicyDefinition(
        "POL-CONT-031",
        PolicySeverity.MAJOR,
        "links",
        "internal_link_quality",
        "公開済み関連Routeだけへ説明的AnchorでLinkし、過剰Exact Matchを避ける",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-032",
        PolicySeverity.BLOCKER,
        "accessibility",
        "non_text_alternative",
        "情報画像・図表に同等目的の代替テキストまたは詳細説明を付与する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-033",
        PolicySeverity.MAJOR,
        "accessibility",
        "semantic_structure",
        "見出し階層、表見出し、Keyboard操作、色以外の区別を維持する",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-034",
        PolicySeverity.MAJOR,
        "metadata",
        "substantive_lastmod",
        "lastmod/Updated Atは実質的変更時のみ更新する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-035",
        PolicySeverity.BLOCKER,
        "publication",
        "kill_switch",
        "Publication/Affiliate Link Kill Switchが有効な場合は該当出力をFail Closedする",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-036",
        PolicySeverity.BLOCKER,
        "publication",
        "snapshot_integrity",
        "承認Version・Methodology・Policy・Evidence・SEO・Schema HashをPublication Snapshotへ固定する",
        PolicyEnforcement.DETERMINISTIC,
    ),
    PolicyDefinition(
        "POL-CONT-037",
        PolicySeverity.MAJOR,
        "draft",
        "review_aggregate_inference",
        "レビュー平均・件数だけから品質・満足・長所短所・代表意見を推定しない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-038",
        PolicySeverity.MAJOR,
        "draft",
        "price_language",
        "価格は取得時点の事実として書き、常時価格・最安保証を暗示しない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-039",
        PolicySeverity.BLOCKER,
        "media",
        "ai_product_depiction",
        "実在商品の外観・仕様をAI生成画像で代替しない",
        PolicyEnforcement.HYBRID,
    ),
    PolicyDefinition(
        "POL-CONT-040",
        PolicySeverity.MAJOR,
        "publication",
        "safe_degradation",
        "変動Factが失効した場合は該当Field/CTAを縮退し、推薦順位を自動変更しない",
        PolicyEnforcement.DETERMINISTIC,
    ),
)

QUALITY_AXIS_DEFINITIONS: tuple[QualityAxisDefinition, ...] = (
    QualityAxisDefinition(
        "QAX-001", "intent_fit", "検索意図への適合", Decimal("15"), Decimal("10")
    ),
    QualityAxisDefinition(
        "QAX-002", "decision_value", "購買意思決定価値", Decimal("20"), Decimal("14")
    ),
    QualityAxisDefinition(
        "QAX-003", "original_value", "独自価値", Decimal("15"), Decimal("9")
    ),
    QualityAxisDefinition(
        "QAX-004", "evidence_accuracy", "事実正確性・根拠", Decimal("20"), Decimal("16")
    ),
    QualityAxisDefinition(
        "QAX-005",
        "fairness_explainability",
        "公平性・説明可能性",
        Decimal("10"),
        Decimal("7"),
    ),
    QualityAxisDefinition("QAX-006", "freshness", "鮮度", Decimal("10"), Decimal("7")),
    QualityAxisDefinition(
        "QAX-007", "readability_ux", "読みやすさ・UX", Decimal("5"), Decimal("3")
    ),
    QualityAxisDefinition(
        "QAX-008", "compliance_disclosure", "広告・規約表示", Decimal("5"), Decimal("5")
    ),
)

ZERO_TOLERANCE_LABELS: tuple[str, ...] = (
    "重大な事実誤り",
    "主要Claimの根拠欠落",
    "架空の使用・検証体験",
    "楽天レビュー本文の不正利用",
    "料率・収益による推薦Bias",
    "不正・不明瞭なAffiliate Link",
    "広告表示欠落",
    "商品/Variant/Offer同定ミス",
    "期限切れ価格・在庫の最新断定",
    "Prompt Injection追随",
    "Structured Dataと可視本文の重大不一致",
    "Affiliate/Public Kill Switch無視",
    "Secret/Restricted Dataの公開",
)

QUALITY_GATE_DEFINITIONS: tuple[QualityGateDefinition, ...] = (
    QualityGateDefinition(
        "QG-CONT-001",
        "article_plan",
        "Article Plan Freeze",
        "Primary Intent、Decision、Article Type、Candidate Universe、対象外が明確",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-002",
        "source_packet",
        "Evidence Readiness",
        "承認済みSource Packet、商品同定、主要Fact、鮮度、欠損が条件を満たす",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-003",
        "content_schema",
        "Content AST Contract",
        "Schema、Block順序、許可Node、未知Field、URL禁止が合格",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-004",
        "claim_evidence",
        "Claim–Evidence",
        "主要Claim 100%、全検証可能Claim 95%以上、競合・期限切れなし",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-005",
        "recommendation",
        "Recommendation Integrity",
        "Methodology、Hard Constraint、Coverage、Bias、Tradeoff、Overrideを検査",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-006",
        "editorial_quality",
        "Editorial Quality",
        "100点中85点以上かつ各軸Floor以上",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-007",
        "compliance",
        "Compliance",
        "広告表示、楽天規約、体験、レビュー、画像、CTA、Policy Findingを検査",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-008",
        "seo_accessibility",
        "SEO & Accessibility",
        "Metadata、Canonical、Structured Data、Link、Heading、Alt、表を検査",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-009",
        "freshness_link",
        "Freshness & Link",
        "Critical Fact、Offer、Affiliate Link、確認時刻、Safe Degradationを検査",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-010",
        "human_review",
        "Human Approval",
        "ReviewerがEvidenceへアクセスし、Finding解消と明示承認を実施",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-011",
        "publication_snapshot",
        "Publication Snapshot",
        "Version、Hash、Policy、Methodology、SEO、Disclosure、Kill Switchを再確認",
        GateFailureAction.BLOCK,
    ),
    QualityGateDefinition(
        "QG-CONT-012",
        "post_publication",
        "Post-publication Verification",
        "公開HTML、CTA、JSON-LD、Canonical、robots、RUM、Cacheを実URLで検査",
        GateFailureAction.ROLLBACK_OR_PAUSE,
    ),
)


JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _valid_datetime_value(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is timezone.utc
        and value.utcoffset() == timezone.utc.utcoffset(value)
        and value.fold == 0
    )


def _valid_reference(value: object) -> bool:
    return (
        type(value) is ReferenceId
        and type(value.value) is str
        and _REFERENCE.fullmatch(value.value) is not None
    )


def _valid_version(value: object) -> bool:
    return (
        type(value) is VersionRef
        and type(value.value) is str
        and _VERSION.fullmatch(value.value) is not None
    )


def _valid_sha256(value: object) -> bool:
    return (
        type(value) is Sha256Digest
        and type(value.value) is str
        and _SHA256.fullmatch(value.value) is not None
    )


def _valid_instant(value: object) -> bool:
    return type(value) is UtcInstant and _valid_datetime_value(value.value)


def _reference_components(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^A-Z0-9]+", value.upper()) if part)


def _has_prohibited_reference(value: ReferenceId) -> bool:
    parts = _reference_components(value.value)
    direct = {
        "COMMISSION",
        "CREDENTIAL",
        "EARNINGS",
        "EPC",
        "FINANCE",
        "MARGIN",
        "PASSWORD",
        "PAYOUT",
        "PROFIT",
        "PROMPT",
        "REVENUE",
        "RPM",
        "SECRET",
        "SPONSOR",
        "SPONSORSHIP",
        "TOKEN",
    }
    if any(part in direct for part in parts):
        return True
    pairs = set(zip(parts, parts[1:], strict=False))
    return bool(
        pairs
        & {
            ("AFFILIATE", "RATE"),
            ("API", "KEY"),
            ("PRIVATE", "KEY"),
            ("RAW", "CONTENT"),
            ("RAW", "PROMPT"),
            ("RAW", "REVIEW"),
            ("REVIEW", "BODY"),
            ("SOURCE", "BODY"),
        }
    )


def _valid_bound_reference(value: object) -> bool:
    return (
        type(value) is BoundReference
        and _valid_reference(value.reference)
        and _valid_sha256(value.sha256)
    )


def _validate_bound_collection(
    value: object,
) -> tuple[bool, bool]:
    if type(value) is not tuple:
        return False, False
    seen: set[str] = set()
    prohibited = False
    for item in value:
        if not _valid_bound_reference(item):
            return False, prohibited
        assert type(item) is BoundReference
        if item.reference.value in seen:
            return False, prohibited
        seen.add(item.reference.value)
        prohibited = prohibited or _has_prohibited_reference(item.reference)
    return True, prohibited


def _valid_decimal(value: object, *, maximum: Decimal) -> bool:
    if type(value) is not Decimal or not value.is_finite():
        return False
    representation = value.as_tuple()
    exponent = representation.exponent
    return (
        type(exponent) is int
        and len(representation.digits) <= _DECIMAL_MAX_DIGITS
        and _DECIMAL_MIN_EXPONENT <= exponent <= _DECIMAL_MAX_EXPONENT
        and Decimal("0") <= value <= maximum
    )


def _decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


def _instant_text(value: UtcInstant) -> str:
    return value.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _local_result_json_text(payload: JsonValue) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _serialize_local(payload: dict[str, JsonValue]) -> tuple[str, str]:
    serialized = _local_result_json_text(payload)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return serialized, digest


def _bound_payload(value: BoundReference) -> dict[str, JsonValue]:
    return {"ref": value.reference.value, "sha256": value.sha256.value}


def _ordered_bound_references(
    value: tuple[BoundReference, ...],
) -> tuple[BoundReference, ...]:
    return tuple(
        sorted(
            value,
            key=lambda item: (item.reference.value, item.sha256.value),
        )
    )


def _target_payload(value: FindingTarget) -> dict[str, JsonValue]:
    return {
        "target_ref": value.target_ref.value,
        "target_type": value.target_type.value,
    }


def _authority_payload() -> dict[str, JsonValue]:
    return {
        "formal_test": ExecutionStatus.NOT_EXECUTED.value,
        "live_validation": ExecutionStatus.NOT_EXECUTED.value,
        "production": ExecutionStatus.NOT_EXECUTED.value,
        "publication_authorized": False,
        "production_eligible": False,
        "release": ExecutionStatus.NOT_EXECUTED.value,
        "staging": ExecutionStatus.NOT_EXECUTED.value,
    }


def _result(
    *,
    status: LocalEvaluationStatus,
    input_findings: tuple[InputFindingCode, ...],
    policy_findings: tuple[PolicyFinding, ...],
    waiver_evaluations: tuple[WaiverEvaluation, ...],
    raw_quality_score: Decimal | None,
    quality_threshold_met: bool | None,
    quality_floors_met: bool | None,
    policy_rules_passed: bool | None,
    zero_tolerance_clear: bool | None,
    quality_gates_passed: bool | None,
    predecessors_available: bool | None,
    local_eligibility: bool,
    post_publication_required_action: GateFailureAction | None,
    payload: dict[str, JsonValue],
) -> PolicyEvaluationResult:
    local_result_json, local_result_digest = _serialize_local(payload)
    return PolicyEvaluationResult(
        status=status,
        input_findings=input_findings,
        policy_findings=policy_findings,
        waiver_evaluations=waiver_evaluations,
        raw_quality_score=raw_quality_score,
        quality_threshold_met=quality_threshold_met,
        quality_floors_met=quality_floors_met,
        policy_rules_passed=policy_rules_passed,
        zero_tolerance_clear=zero_tolerance_clear,
        quality_gates_passed=quality_gates_passed,
        predecessors_available=predecessors_available,
        local_eligibility=local_eligibility,
        post_publication_required_action=post_publication_required_action,
        local_result_serialization_profile=LOCAL_RESULT_SERIALIZATION_PROFILE,
        local_result_json=local_result_json,
        local_result_digest=local_result_digest,
        publication_authorized=False,
        production_eligible=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )


def _invalid_result(findings: set[InputFindingCode]) -> PolicyEvaluationResult:
    ordered = tuple(code for code in InputFindingCode if code in findings)
    payload: dict[str, JsonValue] = {
        "authority": _authority_payload(),
        "input_findings": [code.value for code in ordered],
        "local_eligibility": False,
        "profile": LOCAL_RESULT_SERIALIZATION_PROFILE,
        "status": LocalEvaluationStatus.INVALID_INPUT.value,
    }
    return _result(
        status=LocalEvaluationStatus.INVALID_INPUT,
        input_findings=ordered,
        policy_findings=(),
        waiver_evaluations=(),
        raw_quality_score=None,
        quality_threshold_met=None,
        quality_floors_met=None,
        policy_rules_passed=None,
        zero_tolerance_clear=None,
        quality_gates_passed=None,
        predecessors_available=None,
        local_eligibility=False,
        post_publication_required_action=None,
        payload=payload,
    )


def _validate_contracts(
    value: object,
    findings: set[InputFindingCode],
) -> bool:
    if type(value) is not ContractBindings:
        findings.add(InputFindingCode.CONTRACT_BINDING_INVALID)
        return False
    valid = (
        _valid_reference(value.policy_catalog_id)
        and value.policy_catalog_id.value == POLICY_CATALOG_ID
        and _valid_version(value.policy_catalog_version)
        and value.policy_catalog_version.value == POLICY_CATALOG_VERSION
        and _valid_sha256(value.policy_catalog_sha256)
        and value.policy_catalog_sha256.value == POLICY_CATALOG_SHA256
        and _valid_reference(value.quality_catalog_id)
        and value.quality_catalog_id.value == QUALITY_CATALOG_ID
        and _valid_version(value.quality_catalog_version)
        and value.quality_catalog_version.value == QUALITY_CATALOG_VERSION
        and _valid_version(value.quality_model_version)
        and value.quality_model_version.value == QUALITY_MODEL_VERSION
        and _valid_sha256(value.quality_catalog_sha256)
        and value.quality_catalog_sha256.value == QUALITY_CATALOG_SHA256
        and _valid_reference(value.review_checklist_id)
        and value.review_checklist_id.value == REVIEW_CHECKLIST_ID
        and _valid_version(value.review_checklist_version)
        and value.review_checklist_version.value == REVIEW_CHECKLIST_VERSION
        and _valid_sha256(value.review_checklist_sha256)
        and value.review_checklist_sha256.value == REVIEW_CHECKLIST_SHA256
        and _valid_sha256(value.content_test_matrix_sha256)
        and value.content_test_matrix_sha256.value == CONTENT_TEST_MATRIX_SHA256
    )
    if not valid:
        findings.add(InputFindingCode.CONTRACT_BINDING_INVALID)
    return valid


def _validate_predecessors(
    value: tuple[PredecessorAssessment, ...],
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> dict[PredecessorStory, PredecessorAssessment]:
    records: dict[PredecessorStory, PredecessorAssessment] = {}
    for record in value:
        if type(record) is not PredecessorAssessment:
            findings.add(InputFindingCode.PREDECESSOR_RECORD_INVALID)
            continue
        if type(record.story_id) is not PredecessorStory:
            if type(record.story_id) is str:
                findings.add(InputFindingCode.PREDECESSOR_UNKNOWN)
            else:
                findings.add(InputFindingCode.PREDECESSOR_RECORD_INVALID)
            continue
        if record.story_id in records:
            findings.add(InputFindingCode.PREDECESSOR_DUPLICATE)
        else:
            records[record.story_id] = record
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.PREDECESSOR_BINDING_MISMATCH)
        if not _valid_bound_reference(record.provenance):
            findings.add(InputFindingCode.PREDECESSOR_BINDING_MISMATCH)
        elif _has_prohibited_reference(record.provenance.reference):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if type(record.state) is not PredecessorState:
            findings.add(InputFindingCode.PREDECESSOR_STATE_INVALID)
            continue
        if record.state is PredecessorState.AVAILABLE:
            result = record.result
            if not _valid_bound_reference(result):
                findings.add(InputFindingCode.PREDECESSOR_BINDING_MISMATCH)
            else:
                assert type(result) is BoundReference
                if _has_prohibited_reference(result.reference):
                    findings.add(InputFindingCode.PROHIBITED_INPUT)
        elif record.result is not None:
            findings.add(InputFindingCode.PREDECESSOR_STATE_INVALID)
    expected = set(PredecessorStory)
    if set(records) != expected or len(value) != len(expected):
        findings.add(InputFindingCode.PREDECESSOR_SET_MISMATCH)
    return records


def _validate_target(
    target: object,
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> bool:
    if (
        type(target) is not FindingTarget
        or type(target.target_type) is not FindingTargetType
        or not _valid_reference(target.target_ref)
    ):
        findings.add(InputFindingCode.POLICY_PROOF_INVALID)
        return False
    if _has_prohibited_reference(target.target_ref):
        findings.add(InputFindingCode.PROHIBITED_INPUT)
        return False
    if (
        target.target_type is FindingTargetType.ARTICLE_VERSION
        and target.target_ref != article_version_id
    ):
        findings.add(InputFindingCode.POLICY_ARTICLE_MISMATCH)
        return False
    return True


def _validate_policies(
    value: tuple[PolicyAssessment, ...],
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> dict[str, PolicyAssessment]:
    definitions = {
        definition.policy_id: definition for definition in POLICY_DEFINITIONS
    }
    records: dict[str, PolicyAssessment] = {}
    for record in value:
        if type(record) is not PolicyAssessment:
            findings.add(InputFindingCode.POLICY_RECORD_INVALID)
            continue
        if type(record.policy_id) is not str or record.policy_id not in definitions:
            findings.add(InputFindingCode.POLICY_UNKNOWN)
            continue
        if record.policy_id in records:
            findings.add(InputFindingCode.POLICY_DUPLICATE)
        else:
            records[record.policy_id] = record
        definition = definitions[record.policy_id]
        if (
            not _valid_version(record.policy_version)
            or record.policy_version.value != POLICY_CATALOG_VERSION
            or not _valid_sha256(record.policy_source_sha256)
            or record.policy_source_sha256.value != POLICY_CATALOG_SHA256
        ):
            findings.add(InputFindingCode.POLICY_BINDING_MISMATCH)
        if type(record.stage) is not str or record.stage != definition.stage:
            findings.add(InputFindingCode.POLICY_STAGE_MISMATCH)
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.POLICY_ARTICLE_MISMATCH)
        if type(record.result) is not PolicyRuleResult:
            findings.add(InputFindingCode.POLICY_RESULT_INVALID)
        target_valid = _validate_target(record.target, article_version_id, findings)
        evidence_valid, prohibited = _validate_bound_collection(record.evidence)
        detector_valid = _valid_bound_reference(record.detector)
        if not evidence_valid or not detector_valid or not target_valid:
            findings.add(InputFindingCode.POLICY_PROOF_INVALID)
        if prohibited:
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if detector_valid and _has_prohibited_reference(record.detector.reference):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if type(record.result) is PolicyRuleResult:
            if record.result is PolicyRuleResult.NOT_EVALUATED:
                if record.evidence != ():
                    findings.add(InputFindingCode.POLICY_RESULT_INVALID)
            elif record.evidence == ():
                findings.add(InputFindingCode.POLICY_PROOF_INVALID)
    expected = set(definitions)
    if set(records) != expected or len(value) != len(expected):
        findings.add(InputFindingCode.POLICY_SET_MISMATCH)
    return records


def _validate_axes(
    value: tuple[QualityAxisAssessment, ...],
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> dict[str, QualityAxisAssessment]:
    definitions = {
        definition.axis_id: definition for definition in QUALITY_AXIS_DEFINITIONS
    }
    records: dict[str, QualityAxisAssessment] = {}
    for record in value:
        if type(record) is not QualityAxisAssessment:
            findings.add(InputFindingCode.AXIS_RECORD_INVALID)
            continue
        if type(record.axis_id) is not str or record.axis_id not in definitions:
            findings.add(InputFindingCode.AXIS_UNKNOWN)
            continue
        if record.axis_id in records:
            findings.add(InputFindingCode.AXIS_DUPLICATE)
        else:
            records[record.axis_id] = record
        definition = definitions[record.axis_id]
        if (
            type(record.axis_code) is not str
            or record.axis_code != definition.code
            or not _valid_version(record.quality_model_version)
            or record.quality_model_version.value != QUALITY_MODEL_VERSION
            or not _valid_sha256(record.quality_source_sha256)
            or record.quality_source_sha256.value != QUALITY_CATALOG_SHA256
        ):
            findings.add(InputFindingCode.AXIS_BINDING_MISMATCH)
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.AXIS_ARTICLE_MISMATCH)
        if type(record.state) is not AxisAssessmentState:
            findings.add(InputFindingCode.AXIS_STATE_INVALID)
        evidence_valid, prohibited = _validate_bound_collection(record.evidence)
        evaluator_valid = _valid_bound_reference(record.evaluator)
        if not evidence_valid or not evaluator_valid:
            findings.add(InputFindingCode.AXIS_PROOF_INVALID)
        if prohibited:
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if evaluator_valid and _has_prohibited_reference(record.evaluator.reference):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if type(record.state) is AxisAssessmentState:
            if record.state is AxisAssessmentState.EVALUATED:
                if not _valid_decimal(record.score, maximum=definition.weight):
                    findings.add(InputFindingCode.AXIS_SCORE_INVALID)
                if record.evidence == ():
                    findings.add(InputFindingCode.AXIS_PROOF_INVALID)
            elif record.score is not None or record.evidence != ():
                findings.add(InputFindingCode.AXIS_STATE_INVALID)
    expected = set(definitions)
    if set(records) != expected or len(value) != len(expected):
        findings.add(InputFindingCode.AXIS_SET_MISMATCH)
    return records


def _validate_signals(
    value: tuple[ZeroToleranceAssessment, ...],
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> dict[str, ZeroToleranceAssessment]:
    expected = set(ZERO_TOLERANCE_LABELS)
    records: dict[str, ZeroToleranceAssessment] = {}
    for record in value:
        if type(record) is not ZeroToleranceAssessment:
            findings.add(InputFindingCode.SIGNAL_RECORD_INVALID)
            continue
        if type(record.label) is not str or record.label not in expected:
            findings.add(InputFindingCode.SIGNAL_UNKNOWN)
            continue
        if record.label in records:
            findings.add(InputFindingCode.SIGNAL_DUPLICATE)
        else:
            records[record.label] = record
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.SIGNAL_ARTICLE_MISMATCH)
        if type(record.state) is not ZeroToleranceState:
            findings.add(InputFindingCode.SIGNAL_STATE_INVALID)
        evidence_valid, prohibited = _validate_bound_collection(record.evidence)
        detector_valid = _valid_bound_reference(record.detector)
        if not evidence_valid or not detector_valid:
            findings.add(InputFindingCode.SIGNAL_PROOF_INVALID)
        if prohibited:
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if detector_valid and _has_prohibited_reference(record.detector.reference):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if type(record.state) is ZeroToleranceState:
            if record.state is ZeroToleranceState.NOT_EVALUATED:
                if record.evidence != ():
                    findings.add(InputFindingCode.SIGNAL_STATE_INVALID)
            elif record.evidence == ():
                findings.add(InputFindingCode.SIGNAL_PROOF_INVALID)
    if set(records) != expected or len(value) != len(expected):
        findings.add(InputFindingCode.SIGNAL_SET_MISMATCH)
    return records


def _validate_gates(
    value: tuple[QualityGateAssessment, ...],
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> dict[str, QualityGateAssessment]:
    definitions = {
        definition.gate_id: definition for definition in QUALITY_GATE_DEFINITIONS
    }
    records: dict[str, QualityGateAssessment] = {}
    for record in value:
        if type(record) is not QualityGateAssessment:
            findings.add(InputFindingCode.GATE_RECORD_INVALID)
            continue
        if type(record.gate_id) is not str or record.gate_id not in definitions:
            findings.add(InputFindingCode.GATE_UNKNOWN)
            continue
        if record.gate_id in records:
            findings.add(InputFindingCode.GATE_DUPLICATE)
        else:
            records[record.gate_id] = record
        definition = definitions[record.gate_id]
        if (
            not _valid_version(record.quality_catalog_version)
            or record.quality_catalog_version.value != QUALITY_CATALOG_VERSION
            or not _valid_sha256(record.quality_source_sha256)
            or record.quality_source_sha256.value != QUALITY_CATALOG_SHA256
            or type(record.failure_action) is not GateFailureAction
            or record.failure_action is not definition.failure_action
        ):
            findings.add(InputFindingCode.GATE_BINDING_MISMATCH)
        if type(record.stage) is not str or record.stage != definition.stage:
            findings.add(InputFindingCode.GATE_STAGE_MISMATCH)
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.GATE_ARTICLE_MISMATCH)
        if type(record.state) is not GateAssessmentState:
            findings.add(InputFindingCode.GATE_STATE_INVALID)
        evidence_valid, prohibited = _validate_bound_collection(record.evidence)
        evaluator_valid = _valid_bound_reference(record.evaluator)
        if not evidence_valid or not evaluator_valid:
            findings.add(InputFindingCode.GATE_PROOF_INVALID)
        if prohibited:
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if evaluator_valid and _has_prohibited_reference(record.evaluator.reference):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        if type(record.state) is GateAssessmentState:
            if record.state is GateAssessmentState.NOT_EVALUATED:
                if record.evidence != ():
                    findings.add(InputFindingCode.GATE_STATE_INVALID)
            elif record.evidence == ():
                findings.add(InputFindingCode.GATE_PROOF_INVALID)
    expected = set(definitions)
    if set(records) != expected or len(value) != len(expected):
        findings.add(InputFindingCode.GATE_SET_MISMATCH)
    return records


def _validate_waivers(
    value: tuple[WaiverAttempt, ...],
    article_version_id: ReferenceId,
    policy_records: dict[str, PolicyAssessment],
    findings: set[InputFindingCode],
) -> dict[str, WaiverAttempt]:
    definitions = {
        definition.policy_id: definition for definition in POLICY_DEFINITIONS
    }
    records: dict[str, WaiverAttempt] = {}
    for record in value:
        if type(record) is not WaiverAttempt:
            findings.add(InputFindingCode.WAIVER_RECORD_INVALID)
            continue
        if type(record.policy_id) is not str or record.policy_id not in definitions:
            findings.add(InputFindingCode.WAIVER_UNKNOWN_POLICY)
            continue
        if record.policy_id in records:
            findings.add(InputFindingCode.WAIVER_DUPLICATE)
        else:
            records[record.policy_id] = record
        if (
            not _valid_version(record.policy_version)
            or record.policy_version.value != POLICY_CATALOG_VERSION
            or not _valid_sha256(record.policy_source_sha256)
            or record.policy_source_sha256.value != POLICY_CATALOG_SHA256
        ):
            findings.add(InputFindingCode.WAIVER_BINDING_MISMATCH)
        if (
            not _valid_reference(record.article_version_id)
            or record.article_version_id != article_version_id
        ):
            findings.add(InputFindingCode.WAIVER_BINDING_MISMATCH)
        assessment = policy_records.get(record.policy_id)
        if assessment is None or assessment.result is not PolicyRuleResult.FAIL:
            findings.add(InputFindingCode.WAIVER_POLICY_MISMATCH)
        if (
            type(record.scope_type) is not WaiverScopeType
            or record.scope_type is not WaiverScopeType.ARTICLE_VERSION
            or not _valid_reference(record.scope_ref)
            or record.scope_ref != article_version_id
        ):
            findings.add(InputFindingCode.WAIVER_SCOPE_INVALID)
        if (
            type(record.authority_claim) is not WaiverAuthorityClaim
            or record.authority_claim is not WaiverAuthorityClaim.REQUESTED
        ):
            findings.add(InputFindingCode.WAIVER_AUTHORITY_INVALID)
        evidence_valid, prohibited = _validate_bound_collection(record.evidence)
        proof_values = (
            record.reason,
            record.compliance_approver,
            record.audit_event,
        )
        proof_valid = all(_valid_bound_reference(item) for item in proof_values)
        if (
            not evidence_valid
            or record.evidence == ()
            or not proof_valid
            or not _valid_instant(record.expiry_at)
        ):
            findings.add(InputFindingCode.WAIVER_PROOF_INVALID)
        if prohibited:
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        for item in proof_values:
            if _valid_bound_reference(item) and _has_prohibited_reference(
                item.reference
            ):
                findings.add(InputFindingCode.PROHIBITED_INPUT)
        if _valid_reference(record.scope_ref) and _has_prohibited_reference(
            record.scope_ref
        ):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
    return records


def _contracts_payload(value: ContractBindings) -> dict[str, JsonValue]:
    return {
        "content_test_matrix_sha256": value.content_test_matrix_sha256.value,
        "policy": {
            "catalog_id": value.policy_catalog_id.value,
            "catalog_sha256": value.policy_catalog_sha256.value,
            "catalog_version": value.policy_catalog_version.value,
            "policy_bundle_code": POLICY_BUNDLE_CODE,
        },
        "quality": {
            "catalog_id": value.quality_catalog_id.value,
            "catalog_sha256": value.quality_catalog_sha256.value,
            "catalog_version": value.quality_catalog_version.value,
            "quality_model_version": value.quality_model_version.value,
        },
        "review": {
            "checklist_id": value.review_checklist_id.value,
            "checklist_sha256": value.review_checklist_sha256.value,
            "checklist_version": value.review_checklist_version.value,
        },
    }


def _finding_payload(value: PolicyFinding) -> dict[str, JsonValue]:
    return {
        "article_version_id": value.article_version_id.value,
        "detector": _bound_payload(value.detector),
        "evaluated_at": _instant_text(value.evaluated_at),
        "evidence": [
            _bound_payload(item) for item in _ordered_bound_references(value.evidence)
        ],
        "is_blocking": value.is_blocking,
        "policy_id": value.policy_id,
        "policy_source_sha256": value.policy_source_sha256.value,
        "policy_version": value.policy_version.value,
        "resolution": value.resolution.value,
        "rule_result": value.rule_result.value,
        "severity": value.severity.value,
        "stage": value.stage,
        "target": _target_payload(value.target),
    }


def _valid_payload(
    value: PolicyEvaluationInput,
    predecessors: dict[PredecessorStory, PredecessorAssessment],
    policies: dict[str, PolicyAssessment],
    axes: dict[str, QualityAxisAssessment],
    signals: dict[str, ZeroToleranceAssessment],
    gates: dict[str, QualityGateAssessment],
    waivers: dict[str, WaiverAttempt],
    policy_findings: tuple[PolicyFinding, ...],
    waiver_evaluations: tuple[WaiverEvaluation, ...],
    *,
    status: LocalEvaluationStatus,
    raw_quality_score: Decimal | None,
    quality_threshold_met: bool | None,
    quality_floors_met: bool | None,
    policy_rules_passed: bool,
    zero_tolerance_clear: bool,
    quality_gates_passed: bool,
    predecessors_available: bool,
    local_eligibility: bool,
    post_publication_required_action: GateFailureAction | None,
) -> dict[str, JsonValue]:
    return {
        "article_version_id": value.article_version_id.value,
        "authority": _authority_payload(),
        "contracts": _contracts_payload(value.contracts),
        "derived": {
            "local_eligibility": local_eligibility,
            "policy_rules_passed": policy_rules_passed,
            "post_publication_required_action": (
                post_publication_required_action.value
                if post_publication_required_action is not None
                else None
            ),
            "predecessors_available": predecessors_available,
            "quality_floors_met": quality_floors_met,
            "quality_gates_passed": quality_gates_passed,
            "quality_threshold_met": quality_threshold_met,
            "raw_quality_score": (
                _decimal_text(raw_quality_score)
                if raw_quality_score is not None
                else None
            ),
            "zero_tolerance_clear": zero_tolerance_clear,
        },
        "evaluated_at": _instant_text(value.evaluated_at),
        "gates": [
            {
                "article_version_id": record.article_version_id.value,
                "evaluator": _bound_payload(record.evaluator),
                "evidence": [
                    _bound_payload(item)
                    for item in _ordered_bound_references(record.evidence)
                ],
                "failure_action": record.failure_action.value,
                "gate_id": definition.gate_id,
                "quality_catalog_version": record.quality_catalog_version.value,
                "quality_source_sha256": record.quality_source_sha256.value,
                "stage": record.stage,
                "state": record.state.value,
            }
            for definition in QUALITY_GATE_DEFINITIONS
            for record in (gates[definition.gate_id],)
        ],
        "policy_assessments": [
            {
                "article_version_id": record.article_version_id.value,
                "detector": _bound_payload(record.detector),
                "evidence": [
                    _bound_payload(item)
                    for item in _ordered_bound_references(record.evidence)
                ],
                "policy_id": definition.policy_id,
                "policy_source_sha256": record.policy_source_sha256.value,
                "policy_version": record.policy_version.value,
                "result": record.result.value,
                "stage": record.stage,
                "target": _target_payload(record.target),
            }
            for definition in POLICY_DEFINITIONS
            for record in (policies[definition.policy_id],)
        ],
        "policy_findings": [_finding_payload(item) for item in policy_findings],
        "predecessors": [
            {
                "article_version_id": record.article_version_id.value,
                "provenance": _bound_payload(record.provenance),
                "result": (
                    _bound_payload(record.result) if record.result is not None else None
                ),
                "state": record.state.value,
                "story_id": story.value,
            }
            for story in PredecessorStory
            for record in (predecessors[story],)
        ],
        "profile": LOCAL_RESULT_SERIALIZATION_PROFILE,
        "quality_axes": [
            {
                "article_version_id": record.article_version_id.value,
                "axis_code": record.axis_code,
                "axis_id": definition.axis_id,
                "evaluator": _bound_payload(record.evaluator),
                "evidence": [
                    _bound_payload(item)
                    for item in _ordered_bound_references(record.evidence)
                ],
                "quality_model_version": record.quality_model_version.value,
                "quality_source_sha256": record.quality_source_sha256.value,
                "score": (
                    _decimal_text(record.score) if record.score is not None else None
                ),
                "state": record.state.value,
            }
            for definition in QUALITY_AXIS_DEFINITIONS
            for record in (axes[definition.axis_id],)
        ],
        "status": status.value,
        "waiver_attempts": [
            {
                "article_version_id": record.article_version_id.value,
                "audit_event": _bound_payload(record.audit_event),
                "authority_claim": record.authority_claim.value,
                "compliance_approver": _bound_payload(record.compliance_approver),
                "evidence": [
                    _bound_payload(item)
                    for item in _ordered_bound_references(record.evidence)
                ],
                "expiry_at": _instant_text(record.expiry_at),
                "policy_id": policy_id,
                "policy_source_sha256": record.policy_source_sha256.value,
                "policy_version": record.policy_version.value,
                "reason": _bound_payload(record.reason),
                "scope_ref": record.scope_ref.value,
                "scope_type": record.scope_type.value,
            }
            for policy_id in sorted(waivers)
            for record in (waivers[policy_id],)
        ],
        "waiver_evaluations": [
            {
                "article_version_id": item.article_version_id.value,
                "disposition": item.disposition.value,
                "effective": item.effective,
                "policy_id": item.policy_id,
                "scope_ref": item.scope_ref.value,
                "scope_type": item.scope_type.value,
            }
            for item in waiver_evaluations
        ],
        "zero_tolerance": [
            {
                "article_version_id": record.article_version_id.value,
                "detector": _bound_payload(record.detector),
                "evidence": [
                    _bound_payload(item)
                    for item in _ordered_bound_references(record.evidence)
                ],
                "label": label,
                "state": record.state.value,
            }
            for label in ZERO_TOLERANCE_LABELS
            for record in (signals[label],)
        ],
    }


def _axis_meets_floor(
    assessment: QualityAxisAssessment,
    definition: QualityAxisDefinition,
) -> bool:
    score = assessment.score
    return score is not None and score >= definition.blocking_floor


def evaluate_editorial_policy(value: object) -> PolicyEvaluationResult:
    """Evaluate one complete, pre-resolved, local-only policy input."""

    findings: set[InputFindingCode] = set()
    if type(value) is not PolicyEvaluationInput:
        findings.add(InputFindingCode.INPUT_TYPE_INVALID)
        return _invalid_result(findings)
    if not all(
        type(collection) is tuple
        for collection in (
            value.predecessors,
            value.policy_assessments,
            value.axis_assessments,
            value.zero_tolerance_assessments,
            value.gate_assessments,
            value.waiver_attempts,
        )
    ):
        findings.add(InputFindingCode.COLLECTION_TYPE_INVALID)
        return _invalid_result(findings)
    if not _valid_reference(value.article_version_id):
        findings.add(InputFindingCode.ARTICLE_VERSION_INVALID)
        return _invalid_result(findings)
    if _has_prohibited_reference(value.article_version_id):
        findings.add(InputFindingCode.PROHIBITED_INPUT)
    if not _valid_instant(value.evaluated_at):
        findings.add(InputFindingCode.EVALUATED_AT_INVALID)
    _validate_contracts(value.contracts, findings)
    predecessors = _validate_predecessors(
        value.predecessors,
        value.article_version_id,
        findings,
    )
    policies = _validate_policies(
        value.policy_assessments,
        value.article_version_id,
        findings,
    )
    axes = _validate_axes(
        value.axis_assessments,
        value.article_version_id,
        findings,
    )
    signals = _validate_signals(
        value.zero_tolerance_assessments,
        value.article_version_id,
        findings,
    )
    gates = _validate_gates(
        value.gate_assessments,
        value.article_version_id,
        findings,
    )
    waivers = _validate_waivers(
        value.waiver_attempts,
        value.article_version_id,
        policies,
        findings,
    )
    if findings:
        return _invalid_result(findings)

    policy_findings = tuple(
        PolicyFinding(
            policy_id=definition.policy_id,
            policy_version=record.policy_version,
            policy_source_sha256=record.policy_source_sha256,
            severity=definition.severity,
            is_blocking=definition.severity is PolicySeverity.BLOCKER,
            article_version_id=record.article_version_id,
            stage=record.stage,
            target=record.target,
            evidence=_ordered_bound_references(record.evidence),
            detector=record.detector,
            evaluated_at=value.evaluated_at,
            rule_result=PolicyRuleResult.FAIL,
            resolution=FindingResolution.UNRESOLVED,
        )
        for definition in POLICY_DEFINITIONS
        for record in (policies[definition.policy_id],)
        if record.result is PolicyRuleResult.FAIL
    )
    definition_by_policy = {
        definition.policy_id: definition for definition in POLICY_DEFINITIONS
    }
    waiver_evaluations = tuple(
        WaiverEvaluation(
            policy_id=policy_id,
            article_version_id=record.article_version_id,
            scope_type=record.scope_type,
            scope_ref=record.scope_ref,
            disposition=(
                WaiverDisposition.DENIED_BLOCKER
                if definition_by_policy[policy_id].severity is PolicySeverity.BLOCKER
                else WaiverDisposition.PENDING_HUMAN_AUTHORITY
            ),
            effective=False,
        )
        for policy_id in sorted(waivers)
        for record in (waivers[policy_id],)
    )

    axes_complete = all(
        record.state is AxisAssessmentState.EVALUATED for record in axes.values()
    )
    if axes_complete:
        fixed_context = Context(
            prec=64,
            rounding=ROUND_HALF_EVEN,
            Emin=-999999,
            Emax=999999,
        )
        with localcontext(fixed_context):
            raw_quality_score = sum(
                (record.score for record in axes.values() if record.score is not None),
                Decimal("0"),
            )
    else:
        raw_quality_score = None
    quality_threshold_met = (
        raw_quality_score >= PUBLISH_THRESHOLD
        if raw_quality_score is not None
        else None
    )
    quality_floors_met = (
        all(
            _axis_meets_floor(axes[definition.axis_id], definition)
            for definition in QUALITY_AXIS_DEFINITIONS
        )
        if axes_complete
        else None
    )
    policy_rules_passed = all(
        record.result is PolicyRuleResult.PASS for record in policies.values()
    )
    zero_tolerance_clear = all(
        record.state is ZeroToleranceState.CLEAR for record in signals.values()
    )
    quality_gates_passed = all(
        record.state is GateAssessmentState.PASS for record in gates.values()
    )
    predecessors_available = all(
        record.state is PredecessorState.AVAILABLE for record in predecessors.values()
    )
    has_not_evaluated = (
        any(
            record.state is PredecessorState.NOT_EVALUATED
            for record in predecessors.values()
        )
        or any(
            record.result is PolicyRuleResult.NOT_EVALUATED
            for record in policies.values()
        )
        or not axes_complete
        or any(
            record.state is ZeroToleranceState.NOT_EVALUATED
            for record in signals.values()
        )
        or any(
            record.state is GateAssessmentState.NOT_EVALUATED
            for record in gates.values()
        )
    )
    status = (
        LocalEvaluationStatus.NOT_EVALUATED
        if has_not_evaluated
        else LocalEvaluationStatus.EVALUATED
    )
    local_eligibility = bool(
        status is LocalEvaluationStatus.EVALUATED
        and policy_rules_passed
        and raw_quality_score is not None
        and quality_threshold_met is True
        and quality_floors_met is True
        and zero_tolerance_clear
        and quality_gates_passed
        and predecessors_available
        and not policy_findings
    )
    post_publication_required_action = (
        GateFailureAction.ROLLBACK_OR_PAUSE
        if gates["QG-CONT-012"].state is GateAssessmentState.FAIL
        else None
    )
    payload = _valid_payload(
        value,
        predecessors,
        policies,
        axes,
        signals,
        gates,
        waivers,
        policy_findings,
        waiver_evaluations,
        status=status,
        raw_quality_score=raw_quality_score,
        quality_threshold_met=quality_threshold_met,
        quality_floors_met=quality_floors_met,
        policy_rules_passed=policy_rules_passed,
        zero_tolerance_clear=zero_tolerance_clear,
        quality_gates_passed=quality_gates_passed,
        predecessors_available=predecessors_available,
        local_eligibility=local_eligibility,
        post_publication_required_action=post_publication_required_action,
    )
    return _result(
        status=status,
        input_findings=(),
        policy_findings=policy_findings,
        waiver_evaluations=waiver_evaluations,
        raw_quality_score=raw_quality_score,
        quality_threshold_met=quality_threshold_met,
        quality_floors_met=quality_floors_met,
        policy_rules_passed=policy_rules_passed,
        zero_tolerance_clear=zero_tolerance_clear,
        quality_gates_passed=quality_gates_passed,
        predecessors_available=predecessors_available,
        local_eligibility=local_eligibility,
        post_publication_required_action=post_publication_required_action,
        payload=payload,
    )
