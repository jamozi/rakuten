"""Pure review-workflow domain values for ST-0901 PR1.

The module contains no application command, authorization decision, persistence,
approval eligibility, Finding mutation, or publication behavior.  Callers supply
all identifiers and timestamps.  Validation is deterministic and fail closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum, EnumType
import re
from types import MappingProxyType
from typing import Any, Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID


_REDACTED: Final = "<redacted>"
_MAX_HUMAN_TEXT_LENGTH: Final = 8_000
_MAX_LOCK_VERSION: Final = 9_223_372_036_854_775_807
_CHECKLIST_ITEM_ID = re.compile(r"REV-[0-9]{3}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)


class _ClosedEnumType(EnumType):
    """Reject invalid values before Enum can retain them in a ValueError."""

    def __getitem__(cls, name: str) -> Any:
        if type(name) is not str:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        member: Any
        for member in cls:
            if member.name == name:
                return member
        _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)

    def __call__(
        cls,
        value: Any,
        names: Any = None,
        *values: Any,
        **kwargs: Any,
    ) -> Any:
        if names is not None or values or kwargs:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        member: Any
        for member in cls:
            if value is member:
                return member
        if type(value) is not str:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        for member in cls:
            if member.value == value:
                return member
        _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)


class _ClosedEnum(str, Enum, metaclass=_ClosedEnumType):
    @classmethod
    def _missing_(cls, value: object) -> NoReturn:
        del cls, value
        _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)


class ReviewWorkflowFailureCode(_ClosedEnum):
    """Closed, non-sensitive failure vocabulary for the PR1 domain seam."""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    IDENTIFIER_INVALID = "IDENTIFIER_INVALID"
    TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
    VOCABULARY_INVALID = "VOCABULARY_INVALID"
    PRIORITY_INVALID = "PRIORITY_INVALID"
    LOCK_VERSION_INVALID = "LOCK_VERSION_INVALID"
    ASSIGNMENT_STATE_INVALID = "ASSIGNMENT_STATE_INVALID"
    STATE_TRANSITION_FORBIDDEN = "STATE_TRANSITION_FORBIDDEN"
    COMPLETION_DECISION_REQUIRED = "COMPLETION_DECISION_REQUIRED"
    COMPLETION_DECISION_UNEXPECTED = "COMPLETION_DECISION_UNEXPECTED"
    ASSIGNMENT_BINDING_MISMATCH = "ASSIGNMENT_BINDING_MISMATCH"
    ARTICLE_VERSION_BINDING_MISMATCH = "ARTICLE_VERSION_BINDING_MISMATCH"
    CHECKLIST_ITEM_ID_INVALID = "CHECKLIST_ITEM_ID_INVALID"
    CHECKLIST_VERSION_MISMATCH = "CHECKLIST_VERSION_MISMATCH"
    CHECKLIST_HASH_MISMATCH = "CHECKLIST_HASH_MISMATCH"
    CHECKLIST_MEMBERSHIP_INVALID = "CHECKLIST_MEMBERSHIP_INVALID"
    CHECKLIST_ITEM_DUPLICATE = "CHECKLIST_ITEM_DUPLICATE"
    CHECKLIST_STATUS_INVALID = "CHECKLIST_STATUS_INVALID"
    CHECKLIST_EVIDENCE_INVALID = "CHECKLIST_EVIDENCE_INVALID"
    CHECKLIST_FAIL_JUSTIFICATION_REQUIRED = "CHECKLIST_FAIL_JUSTIFICATION_REQUIRED"
    CHECKLIST_APPLICABILITY_UNRESOLVED = "CHECKLIST_APPLICABILITY_UNRESOLVED"
    DECISION_SUMMARY_INVALID = "DECISION_SUMMARY_INVALID"
    APPROVE_GATE_UNRESOLVED = "APPROVE_GATE_UNRESOLVED"


class ReviewWorkflowFailure(RuntimeError):
    """Stable-code exception that never includes rejected caller material."""

    __slots__ = ("_code",)

    def __init__(self, code: ReviewWorkflowFailureCode) -> None:
        if type(code) is not ReviewWorkflowFailureCode:
            raise TypeError("invalid review workflow failure code")
        self._code = code
        RuntimeError.__init__(self, code.value)

    @property
    def code(self) -> ReviewWorkflowFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ReviewWorkflowFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review workflow failure serialization is not supported")


def _fail(code: ReviewWorkflowFailureCode) -> NoReturn:
    raise ReviewWorkflowFailure(code) from None


class ReviewType(_ClosedEnum):
    EDITORIAL = "EDITORIAL"
    FACT = "FACT"
    COMPLIANCE = "COMPLIANCE"
    UX = "UX"
    FINAL = "FINAL"


class ReviewAssignmentState(_ClosedEnum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ChecklistItemStatus(_ClosedEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE_WITH_REASON = "NOT_APPLICABLE_WITH_REASON"


class ReviewDecisionKind(_ClosedEnum):
    APPROVE = "APPROVE"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECT = "REJECT"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("review workflow value serialization is not supported")


def _require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        _fail(ReviewWorkflowFailureCode.IDENTIFIER_INVALID)
    return value


def _require_uuid_value(
    value: object,
    expected_type: type[_UuidValue],
) -> _UuidValue:
    if type(value) is not expected_type or not isinstance(value, _UuidValue):
        _fail(ReviewWorkflowFailureCode.IDENTIFIER_INVALID)
    _require_uuid7(value.value)
    return value


def _is_utf8_encodable(value: str) -> bool:
    """Return after clearing any encoding exception that could retain text."""

    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _require_human_text(
    value: object,
    *,
    code: ReviewWorkflowFailureCode,
) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_HUMAN_TEXT_LENGTH
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail(code)
    if not _is_utf8_encodable(value):
        _fail(code)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class _UuidValue(_RedactedValue):
    value: UUID

    def __post_init__(self) -> None:
        _require_uuid7(self.value)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewAssignmentId(_UuidValue):
    """UUIDv7 identity for one review assignment."""


@dataclass(frozen=True, slots=True, repr=False)
class ArticleVersionId(_UuidValue):
    """UUIDv7 identity for the immutable article version under review."""


@dataclass(frozen=True, slots=True, repr=False)
class PrincipalId(_UuidValue):
    """Opaque principal coordinate; it grants no local authorization."""


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDecisionId(_UuidValue):
    """UUIDv7 identity for an externally established review decision."""


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceId(_UuidValue):
    """UUIDv7 identity for immutable checklist evidence."""


@dataclass(frozen=True, slots=True, repr=False)
class UtcTimestamp(_RedactedValue):
    value: datetime

    def __post_init__(self) -> None:
        if (
            type(self.value) is not datetime
            or self.value.tzinfo is not timezone.utc
            or self.value.fold != 0
        ):
            _fail(ReviewWorkflowFailureCode.TIMESTAMP_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class HumanComment(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        _require_human_text(
            self.value,
            code=ReviewWorkflowFailureCode.CHECKLIST_FAIL_JUSTIFICATION_REQUIRED,
        )


@dataclass(frozen=True, slots=True, repr=False)
class DecisionSummary(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        _require_human_text(
            self.value,
            code=ReviewWorkflowFailureCode.DECISION_SUMMARY_INVALID,
        )


@dataclass(frozen=True, slots=True, repr=False)
class ChecklistItemId(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or _CHECKLIST_ITEM_ID.fullmatch(self.value) is None
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_ITEM_ID_INVALID)


HUMAN_REVIEW_CHECKLIST_VERSION: Final = "1.0.0"
HUMAN_REVIEW_CHECKLIST_SHA256: Final = (
    "8373dbd354c751c699d02bc8c49b18074ae2e10a2ed0573ebd77d99103d3ea63"
)
CHECKLIST_RESPONSE_TOKENS: Final = tuple(ChecklistItemStatus)
CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON: Final = (
    ChecklistItemStatus.FAIL,
    ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON,
)


@dataclass(frozen=True, slots=True, repr=False)
class ChecklistCatalogItem(_RedactedValue):
    item_id: str
    section: str
    check: str

    def __post_init__(self) -> None:
        if (
            type(self.item_id) is not str
            or _CHECKLIST_ITEM_ID.fullmatch(self.item_id) is None
            or type(self.section) is not str
            or not self.section
            or len(self.section) > 64
            or self.section != self.section.strip()
            or type(self.check) is not str
            or not self.check
            or len(self.check) > 500
            or self.check != self.check.strip()
        ):
            _fail(ReviewWorkflowFailureCode.INVALID_ARGUMENT)
        if not _is_utf8_encodable(self.section) or not _is_utf8_encodable(self.check):
            _fail(ReviewWorkflowFailureCode.INVALID_ARGUMENT)

    @property
    def response_tokens(self) -> tuple[ChecklistItemStatus, ...]:
        return CHECKLIST_RESPONSE_TOKENS

    @property
    def evidence_or_comment_required_on(self) -> tuple[ChecklistItemStatus, ...]:
        return CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON


HUMAN_REVIEW_CHECKLIST: Final = (
    ChecklistCatalogItem(
        "REV-001", "PLAN", "Primary IntentとDecisionが1つに定義されている"
    ),
    ChecklistCatalogItem("REV-002", "PLAN", "Article TypeがIntentに適合する"),
    ChecklistCatalogItem("REV-003", "PLAN", "同義Keywordページの重複がない"),
    ChecklistCatalogItem("REV-004", "PLAN", "対象読者と対象外が明確"),
    ChecklistCatalogItem("REV-005", "PLAN", "Candidate Universeと除外理由が明確"),
    ChecklistCatalogItem("REV-006", "PLAN", "高リスクカテゴリ・Claimを含まない"),
    ChecklistCatalogItem(
        "REV-007", "IDENTITY", "各商品がCanonical Product/Variant/Offerへ正しく紐付く"
    ),
    ChecklistCatalogItem(
        "REV-008", "IDENTITY", "型番・容量・色・セット・世代の取り違えがない"
    ),
    ChecklistCatalogItem("REV-009", "IDENTITY", "比較対象が同等な商品単位である"),
    ChecklistCatalogItem("REV-010", "IDENTITY", "不明な商品統合を人間が解決した"),
    ChecklistCatalogItem("REV-011", "EVIDENCE", "承認済みSource Packetを使用している"),
    ChecklistCatalogItem("REV-012", "EVIDENCE", "主要Claim 100%にEvidenceがある"),
    ChecklistCatalogItem("REV-013", "EVIDENCE", "全検証可能Claim Coverageが95%以上"),
    ChecklistCatalogItem(
        "REV-014", "EVIDENCE", "Sourceの対象・時点・定義がClaimと一致する"
    ),
    ChecklistCatalogItem("REV-015", "EVIDENCE", "競合Sourceを無言で解消していない"),
    ChecklistCatalogItem(
        "REV-016",
        "EVIDENCE",
        "AI出力・検索Snippet・楽天Review本文をEvidenceにしていない",
    ),
    ChecklistCatalogItem(
        "REV-017", "EVIDENCE", "価格・在庫・送料・Rankに取得時刻がある"
    ),
    ChecklistCatalogItem("REV-018", "EVIDENCE", "Derived Factに式と入力Factがある"),
    ChecklistCatalogItem("REV-019", "COPY", "導入が対象読者と決定内容を示す"),
    ChecklistCatalogItem("REV-020", "COPY", "結論が条件付きで説明されている"),
    ChecklistCatalogItem("REV-021", "COPY", "商品説明の言い換えだけでない"),
    ChecklistCatalogItem("REV-022", "COPY", "不明を推測で埋めていない"),
    ChecklistCatalogItem("REV-023", "COPY", "体験表現にFirst-hand Recordがある"),
    ChecklistCatalogItem("REV-024", "COPY", "最上級に母集団・範囲・時点がある"),
    ChecklistCatalogItem("REV-025", "COPY", "長所と短所・不向き条件を両方示す"),
    ChecklistCatalogItem("REV-026", "COPY", "読み手が次の行動を判断できる"),
    ChecklistCatalogItem(
        "REV-027", "RECOMMENDATION", "Methodology Versionが固定されている"
    ),
    ChecklistCatalogItem(
        "REV-028", "RECOMMENDATION", "Hard Constraintを先に適用している"
    ),
    ChecklistCatalogItem("REV-029", "RECOMMENDATION", "重みと正規化が記事条件に妥当"),
    ChecklistCatalogItem(
        "REV-030", "RECOMMENDATION", "Evidence Coverageが順位閾値を満たす"
    ),
    ChecklistCatalogItem("REV-031", "RECOMMENDATION", "同点を無理に順位付けしていない"),
    ChecklistCatalogItem(
        "REV-032", "RECOMMENDATION", "Affiliate Rate/EPC/RPM/利益が入力・画面にない"
    ),
    ChecklistCatalogItem(
        "REV-033", "RECOMMENDATION", "Overrideには理由とEvidenceがある"
    ),
    ChecklistCatalogItem(
        "REV-034", "RECOMMENDATION", "候補外の商品を暗黙に市場全体と扱っていない"
    ),
    ChecklistCatalogItem(
        "REV-035", "COMPLIANCE", "記事上部に広告・Affiliate表示がある"
    ),
    ChecklistCatalogItem(
        "REV-036", "COMPLIANCE", "便益提供がある場合に追加関係表示がある"
    ),
    ChecklistCatalogItem("REV-037", "COMPLIANCE", "CTAが楽天市場遷移を明示する"),
    ChecklistCatalogItem(
        "REV-038", "COMPLIANCE", "Affiliate Linkが正規Resourceから生成される"
    ),
    ChecklistCatalogItem("REV-039", "COMPLIANCE", "rel=sponsoredが付与される"),
    ChecklistCatalogItem("REV-040", "COMPLIANCE", "楽天API Creditが表示される"),
    ChecklistCatalogItem("REV-041", "COMPLIANCE", "楽天Review本文を利用していない"),
    ChecklistCatalogItem("REV-042", "COMPLIANCE", "画像利用条件と非改変を確認した"),
    ChecklistCatalogItem("REV-043", "COMPLIANCE", "誇大・優良誤認の疑いがない"),
    ChecklistCatalogItem("REV-044", "SEO", "Title/H1/主題が一致する"),
    ChecklistCatalogItem("REV-045", "SEO", "TitleとMeta Descriptionが固有"),
    ChecklistCatalogItem("REV-046", "SEO", "CanonicalとIndex Stateが正しい"),
    ChecklistCatalogItem("REV-047", "SEO", "Draft/Previewはnoindex,nofollow"),
    ChecklistCatalogItem("REV-048", "SEO", "Sitemap対象条件を満たす"),
    ChecklistCatalogItem(
        "REV-049", "SEO", "Article/Breadcrumb JSON-LDが可視内容と一致"
    ),
    ChecklistCatalogItem("REV-050", "SEO", "複数商品記事にProduct Markupがない"),
    ChecklistCatalogItem(
        "REV-051", "SEO", "FAQPage/Review/AggregateRatingを誤生成していない"
    ),
    ChecklistCatalogItem("REV-052", "SEO", "内部Linkが文脈的で公開Routeを指す"),
    ChecklistCatalogItem(
        "REV-053", "ACCESSIBILITY_MEDIA", "画像にAsset Provenanceがある"
    ),
    ChecklistCatalogItem(
        "REV-054", "ACCESSIBILITY_MEDIA", "Informative Imageに適切なaltがある"
    ),
    ChecklistCatalogItem(
        "REV-055", "ACCESSIBILITY_MEDIA", "複雑図表にデータ表または詳細説明がある"
    ),
    ChecklistCatalogItem("REV-056", "ACCESSIBILITY_MEDIA", "Decorative Imageのaltが空"),
    ChecklistCatalogItem("REV-057", "ACCESSIBILITY_MEDIA", "見出し階層が連続"),
    ChecklistCatalogItem(
        "REV-058", "ACCESSIBILITY_MEDIA", "比較表に行・列Headerがある"
    ),
    ChecklistCatalogItem(
        "REV-059", "ACCESSIBILITY_MEDIA", "色だけで意味を伝えていない"
    ),
    ChecklistCatalogItem(
        "REV-060", "ACCESSIBILITY_MEDIA", "Keyboard操作とFocusが維持される"
    ),
    ChecklistCatalogItem("REV-061", "FRESHNESS", "Critical FactがFresh"),
    ChecklistCatalogItem("REV-062", "FRESHNESS", "Near ExpiryをQueue化した"),
    ChecklistCatalogItem("REV-063", "FRESHNESS", "Stale FactがSafe Degradationされる"),
    ChecklistCatalogItem("REV-064", "FRESHNESS", "Link Healthが有効"),
    ChecklistCatalogItem(
        "REV-065", "FRESHNESS", "Offer Unavailable時に自動順位変更していない"
    ),
    ChecklistCatalogItem("REV-066", "FRESHNESS", "最終確認日時が表示される"),
    ChecklistCatalogItem(
        "REV-067", "FRESHNESS", "Policy/Methodologyの影響評価が済んでいる"
    ),
    ChecklistCatalogItem("REV-068", "PUBLICATION", "Blocking Findingが0"),
    ChecklistCatalogItem("REV-069", "PUBLICATION", "品質Score 85以上で各Floorを満たす"),
    ChecklistCatalogItem(
        "REV-070", "PUBLICATION", "人間承認が明示操作として記録された"
    ),
    ChecklistCatalogItem(
        "REV-071", "PUBLICATION", "Publication/Affiliate Kill SwitchがOFF"
    ),
    ChecklistCatalogItem(
        "REV-072", "PUBLICATION", "Snapshotに全Version/Hashが固定された"
    ),
    ChecklistCatalogItem("REV-073", "PUBLICATION", "Previewと公開の差分を確認した"),
    ChecklistCatalogItem("REV-074", "PUBLICATION", "Rollback対象が存在する"),
    ChecklistCatalogItem("REV-075", "PUBLICATION", "公開後検査とAlertが設定された"),
)
HUMAN_REVIEW_CHECKLIST_IDS: Final = tuple(
    item.item_id for item in HUMAN_REVIEW_CHECKLIST
)
_CHECKLIST_INDEX_BY_ID: Final[Mapping[str, int]] = MappingProxyType(
    {item_id: index for index, item_id in enumerate(HUMAN_REVIEW_CHECKLIST_IDS)}
)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDecisionReference(_RedactedValue):
    """Immutable completion coordinate, without history/effectiveness semantics."""

    decision_id: ReviewDecisionId
    review_assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId

    def __post_init__(self) -> None:
        _require_uuid_value(self.decision_id, ReviewDecisionId)
        _require_uuid_value(self.review_assignment_id, ReviewAssignmentId)
        _require_uuid_value(self.article_version_id, ArticleVersionId)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewAssignment(_RedactedValue):
    assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    review_type: ReviewType
    assigned_by: PrincipalId
    assigned_to: PrincipalId
    priority: int
    status: ReviewAssignmentState
    started_at: UtcTimestamp | None
    completed_at: UtcTimestamp | None
    cancelled_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    lock_version: int
    completion_decision_reference: ReviewDecisionReference | None

    def __post_init__(self) -> None:
        _require_uuid_value(self.assignment_id, ReviewAssignmentId)
        _require_uuid_value(self.article_version_id, ArticleVersionId)
        _require_uuid_value(self.assigned_by, PrincipalId)
        _require_uuid_value(self.assigned_to, PrincipalId)
        if type(self.review_type) is not ReviewType:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        if type(self.priority) is not int or not 0 <= self.priority <= 100:
            _fail(ReviewWorkflowFailureCode.PRIORITY_INVALID)
        if type(self.status) is not ReviewAssignmentState:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        _require_timestamp_or_none(self.started_at)
        _require_timestamp_or_none(self.completed_at)
        _require_timestamp_or_none(self.cancelled_at)
        _require_timestamp(self.created_at)
        _require_timestamp(self.updated_at)
        if (
            type(self.lock_version) is not int
            or not 0 <= self.lock_version <= _MAX_LOCK_VERSION
        ):
            _fail(ReviewWorkflowFailureCode.LOCK_VERSION_INVALID)
        if self.updated_at.value < self.created_at.value:
            _fail(ReviewWorkflowFailureCode.TIMESTAMP_INVALID)
        for marker in (self.started_at, self.completed_at, self.cancelled_at):
            if marker is not None and not (
                self.created_at.value <= marker.value <= self.updated_at.value
            ):
                _fail(ReviewWorkflowFailureCode.TIMESTAMP_INVALID)
        _require_assignment_state_shape(self)


def _require_timestamp(value: object) -> UtcTimestamp:
    if type(value) is not UtcTimestamp or not isinstance(value, UtcTimestamp):
        _fail(ReviewWorkflowFailureCode.TIMESTAMP_INVALID)
    UtcTimestamp(value.value)
    return value


def _require_timestamp_or_none(value: object) -> UtcTimestamp | None:
    if value is None:
        return None
    return _require_timestamp(value)


def _require_decision_reference(value: object) -> ReviewDecisionReference:
    if type(value) is not ReviewDecisionReference or not isinstance(
        value, ReviewDecisionReference
    ):
        _fail(ReviewWorkflowFailureCode.COMPLETION_DECISION_REQUIRED)
    ReviewDecisionReference(
        value.decision_id,
        value.review_assignment_id,
        value.article_version_id,
    )
    return value


def _require_assignment_state_shape(assignment: ReviewAssignment) -> None:
    reference = assignment.completion_decision_reference
    if assignment.status is ReviewAssignmentState.ASSIGNED:
        if (
            assignment.started_at is not None
            or assignment.completed_at is not None
            or assignment.cancelled_at is not None
            or reference is not None
            or assignment.lock_version != 0
            or assignment.updated_at != assignment.created_at
        ):
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)
        return
    if assignment.status is ReviewAssignmentState.IN_PROGRESS:
        if (
            assignment.started_at is None
            or assignment.completed_at is not None
            or assignment.cancelled_at is not None
            or reference is not None
            or assignment.lock_version != 1
            or assignment.updated_at != assignment.started_at
        ):
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)
        return
    if assignment.status is ReviewAssignmentState.CANCELLED:
        expected_lock = 1 if assignment.started_at is None else 2
        if (
            assignment.completed_at is not None
            or assignment.cancelled_at is None
            or reference is not None
            or assignment.lock_version != expected_lock
            or assignment.updated_at != assignment.cancelled_at
        ):
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)
        return
    if assignment.status is ReviewAssignmentState.COMPLETED:
        if (
            assignment.started_at is None
            or assignment.completed_at is None
            or assignment.cancelled_at is not None
            or assignment.lock_version != 2
            or assignment.updated_at != assignment.completed_at
            or assignment.completed_at.value < assignment.started_at.value
        ):
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)
        bound = _require_decision_reference(reference)
        if bound.review_assignment_id != assignment.assignment_id:
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH)
        if bound.article_version_id != assignment.article_version_id:
            _fail(ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH)
        return
    _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)


def _require_assignment(value: object) -> ReviewAssignment:
    if type(value) is not ReviewAssignment or not isinstance(value, ReviewAssignment):
        _fail(ReviewWorkflowFailureCode.INVALID_ARGUMENT)
    ReviewAssignment(
        value.assignment_id,
        value.article_version_id,
        value.review_type,
        value.assigned_by,
        value.assigned_to,
        value.priority,
        value.status,
        value.started_at,
        value.completed_at,
        value.cancelled_at,
        value.created_at,
        value.updated_at,
        value.lock_version,
        value.completion_decision_reference,
    )
    return value


def create_review_assignment(
    *,
    assignment_id: ReviewAssignmentId,
    article_version_id: ArticleVersionId,
    review_type: ReviewType,
    assigned_by: PrincipalId,
    assigned_to: PrincipalId,
    priority: int,
    created_at: UtcTimestamp,
) -> ReviewAssignment:
    """Create the sole PR1 initial assignment state from caller coordinates."""

    return ReviewAssignment(
        assignment_id,
        article_version_id,
        review_type,
        assigned_by,
        assigned_to,
        priority,
        ReviewAssignmentState.ASSIGNED,
        None,
        None,
        None,
        created_at,
        created_at,
        0,
        None,
    )


_ALLOWED_ASSIGNMENT_TRANSITIONS: Final = frozenset(
    {
        (ReviewAssignmentState.ASSIGNED, ReviewAssignmentState.IN_PROGRESS),
        (ReviewAssignmentState.ASSIGNED, ReviewAssignmentState.CANCELLED),
        (ReviewAssignmentState.IN_PROGRESS, ReviewAssignmentState.COMPLETED),
        (ReviewAssignmentState.IN_PROGRESS, ReviewAssignmentState.CANCELLED),
    }
)


def transition_review_assignment(
    assignment: ReviewAssignment,
    target_state: ReviewAssignmentState,
    occurred_at: UtcTimestamp,
    completion_decision_reference: ReviewDecisionReference | None,
) -> ReviewAssignment:
    """Return a new assignment for one exact canonical state transition."""

    current = _require_assignment(assignment)
    if type(target_state) is not ReviewAssignmentState:
        _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
    event_time = _require_timestamp(occurred_at)
    if (current.status, target_state) not in _ALLOWED_ASSIGNMENT_TRANSITIONS:
        _fail(ReviewWorkflowFailureCode.STATE_TRANSITION_FORBIDDEN)
    if event_time.value < current.updated_at.value:
        _fail(ReviewWorkflowFailureCode.TIMESTAMP_INVALID)
    if current.lock_version == _MAX_LOCK_VERSION:
        _fail(ReviewWorkflowFailureCode.LOCK_VERSION_INVALID)
    if target_state is ReviewAssignmentState.COMPLETED:
        reference = _require_decision_reference(completion_decision_reference)
        if reference.review_assignment_id != current.assignment_id:
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH)
        if reference.article_version_id != current.article_version_id:
            _fail(ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH)
        result = replace(
            current,
            status=target_state,
            completed_at=event_time,
            updated_at=event_time,
            lock_version=current.lock_version + 1,
            completion_decision_reference=reference,
        )
    else:
        if completion_decision_reference is not None:
            _fail(ReviewWorkflowFailureCode.COMPLETION_DECISION_UNEXPECTED)
        if target_state is ReviewAssignmentState.IN_PROGRESS:
            result = replace(
                current,
                status=target_state,
                started_at=event_time,
                updated_at=event_time,
                lock_version=current.lock_version + 1,
            )
        else:
            result = replace(
                current,
                status=target_state,
                cancelled_at=event_time,
                updated_at=event_time,
                lock_version=current.lock_version + 1,
            )
    if (
        result.assignment_id != current.assignment_id
        or result.article_version_id != current.article_version_id
        or result.review_type is not current.review_type
        or result.assigned_by != current.assigned_by
        or result.assigned_to != current.assigned_to
        or result.priority != current.priority
        or result.created_at != current.created_at
    ):
        _fail(ReviewWorkflowFailureCode.INVALID_ARGUMENT)
    return result


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceReference(_RedactedValue):
    evidence_id: EvidenceId
    sha256: Sha256Digest
    review_assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId

    def __post_init__(self) -> None:
        _require_uuid_value(self.evidence_id, EvidenceId)
        if type(self.sha256) is not Sha256Digest:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID)
        Sha256Digest(self.sha256.value)
        _require_uuid_value(self.review_assignment_id, ReviewAssignmentId)
        _require_uuid_value(self.article_version_id, ArticleVersionId)


@dataclass(frozen=True, slots=True, repr=False)
class ChecklistResult(_RedactedValue):
    item_id: ChecklistItemId
    status: ChecklistItemStatus
    evidence: tuple[EvidenceReference, ...]
    human_comment: HumanComment | None

    def __post_init__(self) -> None:
        if type(self.item_id) is not ChecklistItemId:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_ITEM_ID_INVALID)
        ChecklistItemId(self.item_id.value)
        if type(self.status) is not ChecklistItemStatus:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_STATUS_INVALID)
        if type(self.evidence) is not tuple:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID)
        normalized: list[EvidenceReference] = []
        seen_evidence_ids: set[UUID] = set()
        for reference in self.evidence:
            if type(reference) is not EvidenceReference:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID)
            rebuilt = EvidenceReference(
                reference.evidence_id,
                reference.sha256,
                reference.review_assignment_id,
                reference.article_version_id,
            )
            if rebuilt.evidence_id.value in seen_evidence_ids:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_EVIDENCE_INVALID)
            seen_evidence_ids.add(rebuilt.evidence_id.value)
            normalized.append(rebuilt)
        normalized.sort(
            key=lambda value: (value.evidence_id.value.int, value.sha256.value)
        )
        object.__setattr__(self, "evidence", tuple(normalized))
        if self.human_comment is not None:
            if type(self.human_comment) is not HumanComment:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_FAIL_JUSTIFICATION_REQUIRED)
            HumanComment(self.human_comment.value)
        if (
            self.status is ChecklistItemStatus.FAIL
            and not self.evidence
            and self.human_comment is None
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_FAIL_JUSTIFICATION_REQUIRED)


@dataclass(frozen=True, slots=True, repr=False)
class ReviewDecisionDraft(_RedactedValue):
    review_assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    decision: ReviewDecisionKind
    summary: DecisionSummary
    checklist_version: str
    checklist_sha256: str
    checklist_results: tuple[ChecklistResult, ...]

    def __post_init__(self) -> None:
        _require_uuid_value(self.review_assignment_id, ReviewAssignmentId)
        _require_uuid_value(self.article_version_id, ArticleVersionId)
        if type(self.decision) is not ReviewDecisionKind:
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        if type(self.summary) is not DecisionSummary:
            _fail(ReviewWorkflowFailureCode.DECISION_SUMMARY_INVALID)
        DecisionSummary(self.summary.value)
        if (
            type(self.checklist_version) is not str
            or _SEMVER.fullmatch(self.checklist_version) is None
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_VERSION_MISMATCH)
        if (
            type(self.checklist_sha256) is not str
            or _SHA256.fullmatch(self.checklist_sha256) is None
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_HASH_MISMATCH)
        if type(self.checklist_results) is not tuple:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
        normalized: list[ChecklistResult] = []
        for result in self.checklist_results:
            if type(result) is not ChecklistResult:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
            normalized.append(
                ChecklistResult(
                    result.item_id,
                    result.status,
                    result.evidence,
                    result.human_comment,
                )
            )
        object.__setattr__(self, "checklist_results", tuple(normalized))


@dataclass(frozen=True, slots=True, repr=False)
class StructurallyValidatedReviewDecision(_RedactedValue):
    review_assignment_id: ReviewAssignmentId
    article_version_id: ArticleVersionId
    decision: ReviewDecisionKind
    summary: DecisionSummary
    checklist_version: str
    checklist_sha256: str
    checklist_results: tuple[ChecklistResult, ...]

    def __post_init__(self) -> None:
        _require_uuid_value(self.review_assignment_id, ReviewAssignmentId)
        _require_uuid_value(self.article_version_id, ArticleVersionId)
        if type(self.decision) is not ReviewDecisionKind or self.decision not in (
            ReviewDecisionKind.CHANGES_REQUESTED,
            ReviewDecisionKind.REJECT,
        ):
            if self.decision is ReviewDecisionKind.APPROVE:
                _fail(ReviewWorkflowFailureCode.APPROVE_GATE_UNRESOLVED)
            _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
        if type(self.summary) is not DecisionSummary:
            _fail(ReviewWorkflowFailureCode.DECISION_SUMMARY_INVALID)
        DecisionSummary(self.summary.value)
        if (
            type(self.checklist_version) is not str
            or self.checklist_version != HUMAN_REVIEW_CHECKLIST_VERSION
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_VERSION_MISMATCH)
        if (
            type(self.checklist_sha256) is not str
            or self.checklist_sha256 != HUMAN_REVIEW_CHECKLIST_SHA256
        ):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_HASH_MISMATCH)
        if type(self.checklist_results) is not tuple or len(
            self.checklist_results
        ) != len(HUMAN_REVIEW_CHECKLIST):
            _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
        normalized: list[ChecklistResult] = []
        for expected_id, result in zip(
            HUMAN_REVIEW_CHECKLIST_IDS,
            self.checklist_results,
            strict=True,
        ):
            if type(result) is not ChecklistResult:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
            rebuilt = ChecklistResult(
                result.item_id,
                result.status,
                result.evidence,
                result.human_comment,
            )
            if rebuilt.item_id.value != expected_id:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
            if rebuilt.status is ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON:
                _fail(ReviewWorkflowFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED)
            _require_evidence_binding(
                rebuilt,
                self.review_assignment_id,
                self.article_version_id,
            )
            normalized.append(rebuilt)
        object.__setattr__(self, "checklist_results", tuple(normalized))


def _require_evidence_binding(
    result: ChecklistResult,
    assignment_id: ReviewAssignmentId,
    article_version_id: ArticleVersionId,
) -> None:
    for reference in result.evidence:
        if reference.review_assignment_id != assignment_id:
            _fail(ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH)
        if reference.article_version_id != article_version_id:
            _fail(ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH)


def validate_review_decision(
    assignment: ReviewAssignment,
    draft: ReviewDecisionDraft,
) -> StructurallyValidatedReviewDecision:
    """Validate structure only; never append, approve, authorize, or mutate."""

    if type(draft) is not ReviewDecisionDraft:
        _fail(ReviewWorkflowFailureCode.INVALID_ARGUMENT)
    if type(draft.decision) is not ReviewDecisionKind:
        _fail(ReviewWorkflowFailureCode.VOCABULARY_INVALID)
    if draft.decision is ReviewDecisionKind.APPROVE:
        _fail(ReviewWorkflowFailureCode.APPROVE_GATE_UNRESOLVED)
    current = _require_assignment(assignment)
    if current.status is not ReviewAssignmentState.IN_PROGRESS:
        _fail(ReviewWorkflowFailureCode.ASSIGNMENT_STATE_INVALID)
    ReviewDecisionDraft(
        draft.review_assignment_id,
        draft.article_version_id,
        draft.decision,
        draft.summary,
        draft.checklist_version,
        draft.checklist_sha256,
        draft.checklist_results,
    )
    if draft.review_assignment_id != current.assignment_id:
        _fail(ReviewWorkflowFailureCode.ASSIGNMENT_BINDING_MISMATCH)
    if draft.article_version_id != current.article_version_id:
        _fail(ReviewWorkflowFailureCode.ARTICLE_VERSION_BINDING_MISMATCH)
    if draft.checklist_version != HUMAN_REVIEW_CHECKLIST_VERSION:
        _fail(ReviewWorkflowFailureCode.CHECKLIST_VERSION_MISMATCH)
    if draft.checklist_sha256 != HUMAN_REVIEW_CHECKLIST_SHA256:
        _fail(ReviewWorkflowFailureCode.CHECKLIST_HASH_MISMATCH)
    if len(draft.checklist_results) != len(HUMAN_REVIEW_CHECKLIST):
        _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
    result_by_id: dict[str, ChecklistResult] = {}
    for result in draft.checklist_results:
        normalized = ChecklistResult(
            result.item_id,
            result.status,
            result.evidence,
            result.human_comment,
        )
        item_id = normalized.item_id.value
        if item_id in result_by_id:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_ITEM_DUPLICATE)
        if item_id not in _CHECKLIST_INDEX_BY_ID:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
        result_by_id[item_id] = normalized
    if result_by_id.keys() != _CHECKLIST_INDEX_BY_ID.keys():
        _fail(ReviewWorkflowFailureCode.CHECKLIST_MEMBERSHIP_INVALID)
    ordered = tuple(result_by_id[item_id] for item_id in HUMAN_REVIEW_CHECKLIST_IDS)
    for result in ordered:
        if result.status is ChecklistItemStatus.NOT_APPLICABLE_WITH_REASON:
            _fail(ReviewWorkflowFailureCode.CHECKLIST_APPLICABILITY_UNRESOLVED)
        _require_evidence_binding(
            result,
            current.assignment_id,
            current.article_version_id,
        )
    return StructurallyValidatedReviewDecision(
        current.assignment_id,
        current.article_version_id,
        draft.decision,
        draft.summary,
        draft.checklist_version,
        draft.checklist_sha256,
        ordered,
    )


__all__ = (
    "ArticleVersionId",
    "CHECKLIST_EVIDENCE_OR_COMMENT_REQUIRED_ON",
    "CHECKLIST_RESPONSE_TOKENS",
    "ChecklistCatalogItem",
    "ChecklistItemId",
    "ChecklistItemStatus",
    "ChecklistResult",
    "DecisionSummary",
    "EvidenceId",
    "EvidenceReference",
    "HUMAN_REVIEW_CHECKLIST",
    "HUMAN_REVIEW_CHECKLIST_IDS",
    "HUMAN_REVIEW_CHECKLIST_SHA256",
    "HUMAN_REVIEW_CHECKLIST_VERSION",
    "HumanComment",
    "PrincipalId",
    "ReviewAssignment",
    "ReviewAssignmentId",
    "ReviewAssignmentState",
    "ReviewDecisionDraft",
    "ReviewDecisionId",
    "ReviewDecisionKind",
    "ReviewDecisionReference",
    "ReviewType",
    "ReviewWorkflowFailure",
    "ReviewWorkflowFailureCode",
    "Sha256Digest",
    "StructurallyValidatedReviewDecision",
    "UtcTimestamp",
    "create_review_assignment",
    "transition_review_assignment",
    "validate_review_decision",
)
