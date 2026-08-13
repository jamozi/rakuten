"""Fail-closed values for the approved ST-1703 WordPress.com Wave 3 slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


WORDPRESSCOM_MVP_WAVE3_SCHEMA = "WORDPRESSCOM_MVP_DRAFT_PREPARATION_V1"
WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256 = (
    "46f43208309e139c062995adf7bae0cd522a564bd17d77d7966e76f8f51277be"
)
WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256 = (
    "aca2af51e2571a62215c600357fb8f0ee246e8891e60d6e5afbe40d8235ee681"
)
WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256 = (
    "e46de3b040bcb04276ff1cc0246857c10b763888e27a5eb4577f84e424103660"
)
WORDPRESSCOM_MVP_WAVE3_TARGET_ORIGIN = "https://kurashierabinote.wordpress.com"
WORDPRESSCOM_MVP_WAVE3_PROVIDER_ORIGIN = "https://public-api.wordpress.com"
WORDPRESSCOM_MVP_WAVE3_SITE_ID = "256699520"
WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID = "7"
WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID = "283672805"
WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME = "暮らし選びノート編集部"
WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY = "NONE"
WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_MODIFIED = "2026-08-13T02:34:35+09:00"
WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE = (
    "[レビュー用・未承認] "
    "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_CONTENT_SHA256 = (
    "6eab149a4057d3f21dad6fa9efdbe66aadfafa00f100038541a3971693a8503d"
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE = (
    "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256 = (
    "184a6214ed07ea4cf9f2acd6304df15464f21ef9e868cacb6ae71129178c63e4"
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256 = (
    "fd2c91dc1e2664df3bccf6c20da432eac3e3cca70aabfe8dd03f55b1207a9905"
)
WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER = (
    "article-7-update",
    "page-about-create",
    "page-editorial-policy-create",
    "page-privacy-policy-create",
    "page-advertising-policy-create",
    "page-contact-create",
)
WORDPRESSCOM_MVP_WAVE3_PAGE_SLUGS = (
    "about",
    "editorial-policy",
    "privacy-policy",
    "advertising-policy",
    "contact",
)
WORDPRESSCOM_MVP_WAVE3_AFFILIATE_PRODUCT_NAMES = (
    "ACE クレスタ 06316",
    "ace.TOKYO LABEL ディフェレンス 05721",
    "PROTECA マックスパス4 01471",
)
WORDPRESSCOM_MVP_WAVE3_OPERATION_BINDINGS = {
    "article-7-update": (
        "post",
        "7",
        "",
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE,
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256,
    ),
    "page-about-create": (
        "page",
        None,
        "about",
        "運営者情報",
        "147bfe03a538872597a014c41742d57f410355988c10fe246b92b5adcc1387d5",
    ),
    "page-editorial-policy-create": (
        "page",
        None,
        "editorial-policy",
        "編集方針",
        "6a824c6cbda474db4921db134e9cb8adf6678221d3913b863f3ec81e729eb159",
    ),
    "page-privacy-policy-create": (
        "page",
        None,
        "privacy-policy",
        "プライバシーポリシー",
        "09c1442ab4479b582c2974e0f32512ff03e118e1a78848c6bf0bf57f5a4e8868",
    ),
    "page-advertising-policy-create": (
        "page",
        None,
        "advertising-policy",
        "広告・アフィリエイトについて",
        "6731018bb1dfadcd83a82b3fc36dd288e5b3a2c946530a0ab36a88718337737f",
    ),
    "page-contact-create": (
        "page",
        None,
        "contact",
        "お問い合わせ",
        "03bb8256d4d93199f699c0919aa35570a29e7da4dd47d2b5d620f89970b98176",
    ),
}
WORDPRESSCOM_MVP_WAVE3_FULL_FIELDS = (
    "ID,site_ID,author,modified,title,content,URL,slug,status,type,discussion,"
    "likes_enabled,sharing_enabled,publicize_URLs"
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH = (
    "/rest/v1.1/sites/256699520/posts/7?context=edit&fields="
    + WORDPRESSCOM_MVP_WAVE3_FULL_FIELDS
)
WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH = (
    "/rest/v1.1/sites/256699520/posts/7?context=edit&fields=ID,site_ID"
)
WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH = (
    "/rest/v1.1/sites/256699520/posts/?context=edit&type=any&status=any&"
    "number=100&order=ASC&order_by=ID&fields=ID,site_ID,type,slug,status"
)
WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH = (
    "/rest/v1.1/sites/256699520/posts/new?context=edit&fields=ID,site_ID"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CANONICAL_ID = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_MAX_ID = (1 << 63) - 1


class WordPressComMvpDraftFailureCode(StrEnum):
    """Closed, value-free failures exposed by Wave 3."""

    BINDING_INVALID = "MVP_DRAFT_BINDING_INVALID"
    CONTENT_INVALID = "MVP_DRAFT_CONTENT_INVALID"
    JOURNAL_INVALID = "MVP_DRAFT_JOURNAL_INVALID"
    JOURNAL_IO_FAILURE = "MVP_DRAFT_JOURNAL_IO_FAILURE"
    HTTPS_SETUP_INVALID = "MVP_DRAFT_HTTPS_SETUP_INVALID"
    REMOTE_RESPONSE_INVALID = "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    REFUSED_MISMATCH = "MVP_DRAFT_REFUSED_MISMATCH"
    DRIFT = "MVP_DRAFT_DRIFT"
    MUTATION_AMBIGUOUS = "MVP_DRAFT_MUTATION_AMBIGUOUS"
    LIVE_MUTATION_NOT_AUTHORIZED = "MVP_DRAFT_LIVE_MUTATION_NOT_AUTHORIZED"
    AFFILIATE_INVALID = "MVP_DRAFT_AFFILIATE_INVALID"


class MvpDraftResponseStage(StrEnum):
    """Closed, value-free response stages retained only for preview diagnosis."""

    TRANSPORT = "TRANSPORT"
    STATUS = "STATUS"
    CONTENT_TYPE = "CONTENT_TYPE"
    BOUNDED_JSON = "BOUNDED_JSON"
    TOP_LEVEL_KEYS = "TOP_LEVEL_KEYS"
    SITE_ID = "SITE_ID"
    NESTED_SHAPE = "NESTED_SHAPE"
    AUTHOR_SHAPE = "AUTHOR_SHAPE"
    DISCUSSION_SHAPE = "DISCUSSION_SHAPE"
    DISCUSSION_TYPE = "DISCUSSION_TYPE"
    DISCUSSION_REQUIRED_KEYS_MISSING = "DISCUSSION_REQUIRED_KEYS_MISSING"
    DISCUSSION_EXTRA_KEYS = "DISCUSSION_EXTRA_KEYS"
    PUBLICIZE_URLS = "PUBLICIZE_URLS"
    IDENTIFIER = "IDENTIFIER"
    SCALAR_FIELD_TYPE = "SCALAR_FIELD_TYPE"
    URL = "URL"
    COLLECTION_SHAPE = "COLLECTION_SHAPE"
    ENTRY_SHAPE = "ENTRY_SHAPE"
    APPLICATION_INVARIANT = "APPLICATION_INVARIANT"


class MvpDraftResponseContext(StrEnum):
    """Closed read context; it contains no remote object or provider value."""

    ARTICLE_FULL_GET = "ARTICLE_FULL_GET"
    PAGE_SCAN = "PAGE_SCAN"
    PAGE_FULL_GET = "PAGE_FULL_GET"


class WordPressComMvpDraftFailure(RuntimeError):
    """Sanitized Wave 3 failure with no remote or credential material."""

    __slots__ = ("code", "response_context", "response_stage")

    def __init__(
        self,
        code: WordPressComMvpDraftFailureCode,
        *,
        response_stage: MvpDraftResponseStage | None = None,
        response_context: MvpDraftResponseContext | None = None,
    ) -> None:
        self.code = (
            code
            if type(code) is WordPressComMvpDraftFailureCode
            else WordPressComMvpDraftFailureCode.BINDING_INVALID
        )
        self.response_stage = (
            response_stage if type(response_stage) is MvpDraftResponseStage else None
        )
        self.response_context = (
            response_context
            if self.response_stage is not None
            and type(response_context) is MvpDraftResponseContext
            else None
        )
        super().__init__(self.code.value)


def fail_wordpresscom_mvp_draft(
    code: WordPressComMvpDraftFailureCode,
    *,
    response_stage: MvpDraftResponseStage | None = None,
    response_context: MvpDraftResponseContext | None = None,
) -> NoReturn:
    raise WordPressComMvpDraftFailure(
        code,
        response_stage=response_stage,
        response_context=response_context,
    ) from None


class MvpDraftOperationState(StrEnum):
    NO_STATE = "NO_STATE"
    REUSED_EXACT = "REUSED_EXACT"
    INTENT = "INTENT"
    COMMITTED = "COMMITTED"
    MUTATION_AMBIGUOUS = "MUTATION_AMBIGUOUS"
    RECONCILED_COMMITTED = "RECONCILED_COMMITTED"
    REFUSED_MISMATCH = "REFUSED_MISMATCH"


class MvpDraftObservation(StrEnum):
    EXACT = "EXACT"
    MISSING = "MISSING"
    DRIFT = "DRIFT"
    AMBIGUOUS = "AMBIGUOUS"
    REFUSED = "REFUSED"


class MvpDraftBaseState(StrEnum):
    PREPARED = "PREPARED"
    MISSING = "MISSING"
    DRIFT = "DRIFT"
    AMBIGUOUS = "AMBIGUOUS"
    REFUSED = "REFUSED"


class MvpDraftAffiliateState(StrEnum):
    SLOTS_PENDING = "AFFILIATE_SLOTS_PENDING"
    SLOTS_VALIDATED = "AFFILIATE_SLOTS_VALIDATED"
    SLOTS_INVALID = "AFFILIATE_SLOTS_INVALID"
    NOT_EVALUATED = "NOT_EVALUATED"


class MvpDraftManualReviewState(StrEnum):
    READY = "READY_FOR_MANUAL_PUBLICATION_REVIEW"
    NOT_READY = "NOT_READY"


class MvpDraftReasonCode(StrEnum):
    EXACT_DESIRED = "EXACT_DESIRED"
    EXACT_PLACEHOLDERS = "EXACT_PLACEHOLDERS"
    EXACT_AFFILIATE_SLOTS = "EXACT_AFFILIATE_SLOTS"
    OBJECT_MISSING = "OBJECT_MISSING"
    OBJECT_DRIFT = "OBJECT_DRIFT"
    ARTICLE_APPROVED_BASELINE = "ARTICLE_APPROVED_BASELINE"
    ARTICLE_MIXED_DESIRED_BASELINE_DRIFT = "ARTICLE_MIXED_DESIRED_BASELINE_DRIFT"
    ARTICLE_OBJECT_ID_DRIFT = "ARTICLE_OBJECT_ID_DRIFT"
    ARTICLE_SITE_ID_DRIFT = "ARTICLE_SITE_ID_DRIFT"
    ARTICLE_AUTHOR_ID_DRIFT = "ARTICLE_AUTHOR_ID_DRIFT"
    ARTICLE_AUTHOR_NAME_DRIFT = "ARTICLE_AUTHOR_NAME_DRIFT"
    ARTICLE_BASELINE_MODIFIED_DRIFT = "ARTICLE_BASELINE_MODIFIED_DRIFT"
    ARTICLE_TITLE_DRIFT = "ARTICLE_TITLE_DRIFT"
    ARTICLE_CONTENT_DRIFT = "ARTICLE_CONTENT_DRIFT"
    ARTICLE_SLUG_DRIFT = "ARTICLE_SLUG_DRIFT"
    ARTICLE_STATUS_DRIFT = "ARTICLE_STATUS_DRIFT"
    ARTICLE_TYPE_DRIFT = "ARTICLE_TYPE_DRIFT"
    ARTICLE_COMMENTS_OPEN_DRIFT = "ARTICLE_COMMENTS_OPEN_DRIFT"
    ARTICLE_PINGS_OPEN_DRIFT = "ARTICLE_PINGS_OPEN_DRIFT"
    ARTICLE_LIKES_ENABLED_DRIFT = "ARTICLE_LIKES_ENABLED_DRIFT"
    ARTICLE_SHARING_ENABLED_DRIFT = "ARTICLE_SHARING_ENABLED_DRIFT"
    ARTICLE_PUBLICIZE_URLS_DRIFT = "ARTICLE_PUBLICIZE_URLS_DRIFT"
    PAGE_SITE_ID_DRIFT = "PAGE_SITE_ID_DRIFT"
    PAGE_AUTHOR_ID_DRIFT = "PAGE_AUTHOR_ID_DRIFT"
    PAGE_AUTHOR_NAME_DRIFT = "PAGE_AUTHOR_NAME_DRIFT"
    PAGE_TITLE_DRIFT = "PAGE_TITLE_DRIFT"
    PAGE_CONTENT_DRIFT = "PAGE_CONTENT_DRIFT"
    PAGE_SLUG_DRIFT = "PAGE_SLUG_DRIFT"
    PAGE_STATUS_DRIFT = "PAGE_STATUS_DRIFT"
    PAGE_TYPE_DRIFT = "PAGE_TYPE_DRIFT"
    PAGE_COMMENTS_OPEN_DRIFT = "PAGE_COMMENTS_OPEN_DRIFT"
    PAGE_PINGS_OPEN_DRIFT = "PAGE_PINGS_OPEN_DRIFT"
    PAGE_LIKES_ENABLED_DRIFT = "PAGE_LIKES_ENABLED_DRIFT"
    PAGE_SHARING_ENABLED_DRIFT = "PAGE_SHARING_ENABLED_DRIFT"
    PAGE_PUBLICIZE_URLS_DRIFT = "PAGE_PUBLICIZE_URLS_DRIFT"
    OBJECT_DUPLICATE = "OBJECT_DUPLICATE"
    JOURNAL_AMBIGUOUS = "JOURNAL_AMBIGUOUS"
    JOURNAL_REFUSED = "JOURNAL_REFUSED"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    FULL_GET_TRANSPORT_INVALID = "FULL_GET_TRANSPORT_INVALID"
    FULL_GET_STATUS_INVALID = "FULL_GET_STATUS_INVALID"
    FULL_GET_CONTENT_TYPE_INVALID = "FULL_GET_CONTENT_TYPE_INVALID"
    FULL_GET_BOUNDED_JSON_INVALID = "FULL_GET_BOUNDED_JSON_INVALID"
    FULL_GET_TOP_LEVEL_KEYS_INVALID = "FULL_GET_TOP_LEVEL_KEYS_INVALID"
    FULL_GET_SITE_ID_INVALID = "FULL_GET_SITE_ID_INVALID"
    FULL_GET_NESTED_SHAPE_INVALID = "FULL_GET_NESTED_SHAPE_INVALID"
    FULL_GET_AUTHOR_SHAPE_INVALID = "FULL_GET_AUTHOR_SHAPE_INVALID"
    FULL_GET_DISCUSSION_SHAPE_INVALID = "FULL_GET_DISCUSSION_SHAPE_INVALID"
    FULL_GET_DISCUSSION_TYPE_INVALID = "FULL_GET_DISCUSSION_TYPE_INVALID"
    FULL_GET_DISCUSSION_REQUIRED_KEYS_MISSING = (
        "FULL_GET_DISCUSSION_REQUIRED_KEYS_MISSING"
    )
    FULL_GET_DISCUSSION_EXTRA_KEYS = "FULL_GET_DISCUSSION_EXTRA_KEYS"
    FULL_GET_PUBLICIZE_URLS_INVALID = "FULL_GET_PUBLICIZE_URLS_INVALID"
    FULL_GET_IDENTIFIER_INVALID = "FULL_GET_IDENTIFIER_INVALID"
    FULL_GET_SCALAR_FIELD_TYPE_INVALID = "FULL_GET_SCALAR_FIELD_TYPE_INVALID"
    FULL_GET_URL_INVALID = "FULL_GET_URL_INVALID"
    FULL_GET_APPLICATION_INVARIANT_INVALID = "FULL_GET_APPLICATION_INVARIANT_INVALID"
    PAGE_SCAN_TRANSPORT_INVALID = "PAGE_SCAN_TRANSPORT_INVALID"
    PAGE_SCAN_STATUS_INVALID = "PAGE_SCAN_STATUS_INVALID"
    PAGE_SCAN_CONTENT_TYPE_INVALID = "PAGE_SCAN_CONTENT_TYPE_INVALID"
    PAGE_SCAN_BOUNDED_JSON_INVALID = "PAGE_SCAN_BOUNDED_JSON_INVALID"
    PAGE_SCAN_TOP_LEVEL_KEYS_INVALID = "PAGE_SCAN_TOP_LEVEL_KEYS_INVALID"
    PAGE_SCAN_COLLECTION_SHAPE_INVALID = "PAGE_SCAN_COLLECTION_SHAPE_INVALID"
    PAGE_SCAN_ENTRY_SHAPE_INVALID = "PAGE_SCAN_ENTRY_SHAPE_INVALID"
    PAGE_SCAN_SITE_ID_INVALID = "PAGE_SCAN_SITE_ID_INVALID"
    PAGE_SCAN_IDENTIFIER_INVALID = "PAGE_SCAN_IDENTIFIER_INVALID"
    PAGE_SCAN_SCALAR_FIELD_TYPE_INVALID = "PAGE_SCAN_SCALAR_FIELD_TYPE_INVALID"
    PAGE_SCAN_APPLICATION_INVARIANT_INVALID = "PAGE_SCAN_APPLICATION_INVARIANT_INVALID"
    AFFILIATE_INVALID = "AFFILIATE_INVALID"


_PREVIEW_RESPONSE_REASONS = frozenset(
    reason
    for reason in MvpDraftReasonCode
    if reason is MvpDraftReasonCode.RESPONSE_INVALID
    or reason.value.startswith(("FULL_GET_", "PAGE_SCAN_"))
)
_PREVIEW_PAGE_SCAN_REASONS = frozenset(
    reason for reason in MvpDraftReasonCode if reason.value.startswith("PAGE_SCAN_")
)
_PREVIEW_ARTICLE_OBJECT_DRIFT_REASONS = frozenset(
    reason
    for reason in MvpDraftReasonCode
    if reason is MvpDraftReasonCode.ARTICLE_APPROVED_BASELINE
    or reason.value.startswith("ARTICLE_")
)
_PREVIEW_PAGE_OBJECT_DRIFT_REASONS = frozenset(
    reason
    for reason in MvpDraftReasonCode
    if reason.value.startswith("PAGE_") and not reason.value.startswith("PAGE_SCAN_")
)
_PREVIEW_OBJECT_DRIFT_REASONS = (
    _PREVIEW_ARTICLE_OBJECT_DRIFT_REASONS | _PREVIEW_PAGE_OBJECT_DRIFT_REASONS
)
_PREVIEW_REASONS_BY_OBSERVATION = {
    MvpDraftObservation.EXACT: frozenset(
        {
            MvpDraftReasonCode.EXACT_DESIRED,
            MvpDraftReasonCode.EXACT_PLACEHOLDERS,
            MvpDraftReasonCode.EXACT_AFFILIATE_SLOTS,
        }
    ),
    MvpDraftObservation.MISSING: frozenset({MvpDraftReasonCode.OBJECT_MISSING}),
    MvpDraftObservation.DRIFT: frozenset(
        {
            MvpDraftReasonCode.OBJECT_DRIFT,
            MvpDraftReasonCode.AFFILIATE_INVALID,
        }
    )
    | _PREVIEW_OBJECT_DRIFT_REASONS
    | _PREVIEW_RESPONSE_REASONS,
    MvpDraftObservation.AMBIGUOUS: frozenset({MvpDraftReasonCode.JOURNAL_AMBIGUOUS}),
    MvpDraftObservation.REFUSED: frozenset(
        {MvpDraftReasonCode.JOURNAL_REFUSED, MvpDraftReasonCode.OBJECT_DUPLICATE}
    ),
}


def normalize_wordpresscom_mvp_line_endings(value: object) -> str:
    """Apply the only normalization authorized for edit-context content."""

    if type(value) is not str:
        fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.CONTENT_INVALID)
    return value.replace("\r\n", "\n").replace("\r", "\n")


def normalize_wordpresscom_mvp_id(value: object) -> str:
    """Normalize the two exact JSON wire forms admitted for positive IDs."""

    if type(value) is int:
        if 1 <= value <= _MAX_ID:
            return str(value)
    elif (
        type(value) is str
        and _CANONICAL_ID.fullmatch(value) is not None
        and value != "0"
        and int(value) <= _MAX_ID
    ):
        return value
    fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID)


class _RedactedWave3Value:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-wordpresscom-wave3>)"

    def __str__(self) -> str:
        return "<redacted-wordpresscom-wave3>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress.com Wave 3 value serialization is disabled")


@dataclass(frozen=True, slots=True, repr=False)
class MvpDraftOperation(_RedactedWave3Value):
    operation_id: str
    object_type: str
    object_id: str | None
    slug: str
    title: str
    content: str
    content_sha256: str

    def __post_init__(self) -> None:
        expected = (
            WORDPRESSCOM_MVP_WAVE3_OPERATION_BINDINGS.get(self.operation_id)
            if type(self.operation_id) is str
            else None
        )
        if (
            type(self.operation_id) is not str
            or self.operation_id not in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
            or expected is None
            or type(self.object_type) is not str
            or type(self.slug) is not str
            or type(self.title) is not str
            or type(self.content) is not str
            or not self.content
            or type(self.content_sha256) is not str
            or _SHA256.fullmatch(self.content_sha256) is None
            or (
                self.object_type,
                self.object_id,
                self.slug,
                self.title,
                self.content_sha256,
            )
            != expected
            or hashlib.sha256(self.content.encode("utf-8", errors="strict")).hexdigest()
            != self.content_sha256
        ):
            fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.CONTENT_INVALID)

    def binding_sha256(self) -> str:
        """Bind the immutable operation without exposing its content in records."""

        self.__post_init__()
        encoded = json.dumps(
            {
                "author_id": WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID,
                "content_sha256": self.content_sha256,
                "handoff_sha256": WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256,
                "object_id": self.object_id,
                "object_type": self.object_type,
                "operation_id": self.operation_id,
                "site_id": WORDPRESSCOM_MVP_WAVE3_SITE_ID,
                "slug": self.slug,
                "status": "draft",
                "title": self.title,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class MvpDraftContentBundle(_RedactedWave3Value):
    operations: tuple[MvpDraftOperation, ...]
    article_baseline_content: str
    article_outside_slots_sha256: str
    affiliate_product_names: tuple[str, str, str]

    def __post_init__(self) -> None:
        if (
            type(self.operations) is not tuple
            or any(
                type(operation) is not MvpDraftOperation
                for operation in self.operations
            )
            or tuple(operation.operation_id for operation in self.operations)
            != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
            or type(self.article_baseline_content) is not str
            or hashlib.sha256(
                self.article_baseline_content.encode("utf-8", errors="strict")
            ).hexdigest()
            != WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_CONTENT_SHA256
            or self.article_outside_slots_sha256
            != WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256
            or type(self.affiliate_product_names) is not tuple
            or self.affiliate_product_names
            != WORDPRESSCOM_MVP_WAVE3_AFFILIATE_PRODUCT_NAMES
        ):
            fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.CONTENT_INVALID)
        for operation in self.operations:
            operation.__post_init__()


@dataclass(frozen=True, slots=True, repr=False)
class MvpDraftOperationPreview(_RedactedWave3Value):
    operation_id: str
    observation: MvpDraftObservation
    reason_code: MvpDraftReasonCode

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not str
            or self.operation_id not in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
            or type(self.observation) is not MvpDraftObservation
            or type(self.reason_code) is not MvpDraftReasonCode
            or self.reason_code
            not in _PREVIEW_REASONS_BY_OBSERVATION.get(self.observation, frozenset())
            or (
                self.reason_code in _PREVIEW_PAGE_SCAN_REASONS
                and self.operation_id == WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]
            )
            or (
                self.reason_code in _PREVIEW_ARTICLE_OBJECT_DRIFT_REASONS
                and self.operation_id != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]
            )
            or (
                self.reason_code in _PREVIEW_PAGE_OBJECT_DRIFT_REASONS
                and self.operation_id == WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]
            )
        ):
            fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.BINDING_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class MvpDraftPreview(_RedactedWave3Value):
    operations: tuple[MvpDraftOperationPreview, ...]
    base_state: MvpDraftBaseState
    affiliate_state: MvpDraftAffiliateState
    affiliate_slot_count: int
    manual_review_state: MvpDraftManualReviewState
    publication_authority: str = WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY

    def __post_init__(self) -> None:
        if (
            type(self.operations) is not tuple
            or len(self.operations) != len(WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER)
            or any(
                type(value) is not MvpDraftOperationPreview for value in self.operations
            )
            or type(self.base_state) is not MvpDraftBaseState
            or type(self.affiliate_state) is not MvpDraftAffiliateState
            or type(self.affiliate_slot_count) is not int
            or type(self.manual_review_state) is not MvpDraftManualReviewState
            or type(self.publication_authority) is not str
        ):
            fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        for value in self.operations:
            value.__post_init__()
        observations = tuple(value.observation for value in self.operations)
        expected_base = (
            MvpDraftBaseState.PREPARED
            if observations and set(observations) == {MvpDraftObservation.EXACT}
            else MvpDraftBaseState.REFUSED
            if MvpDraftObservation.REFUSED in observations
            else MvpDraftBaseState.AMBIGUOUS
            if MvpDraftObservation.AMBIGUOUS in observations
            else MvpDraftBaseState.DRIFT
            if MvpDraftObservation.DRIFT in observations
            else MvpDraftBaseState.MISSING
        )
        affiliate_count_valid = (
            self.affiliate_slot_count == 3
            if self.affiliate_state is MvpDraftAffiliateState.SLOTS_VALIDATED
            else self.affiliate_slot_count == 0
        )
        expected_manual = (
            MvpDraftManualReviewState.READY
            if self.base_state is MvpDraftBaseState.PREPARED
            and self.affiliate_state is MvpDraftAffiliateState.SLOTS_VALIDATED
            and self.affiliate_slot_count == 3
            else MvpDraftManualReviewState.NOT_READY
        )
        if (
            tuple(value.operation_id for value in self.operations)
            != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
            or not 0 <= self.affiliate_slot_count <= 3
            or not affiliate_count_valid
            or self.base_state is not expected_base
            or self.manual_review_state is not expected_manual
            or self.publication_authority
            != WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY
        ):
            fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.BINDING_INVALID)


@dataclass(frozen=True, slots=True, repr=False)
class MvpRemoteObject(_RedactedWave3Value):
    """Strict decoded edit-context object retained only in bounded memory."""

    object_id: str
    site_id: str
    author_id: str
    author_name: str
    modified: str
    title: str
    content: str
    url: str
    slug: str
    status: str
    object_type: str
    comments_open: bool
    pings_open: bool
    likes_enabled: bool
    sharing_enabled: bool
    publicize_urls_empty: bool

    def __post_init__(self) -> None:
        string_values = (
            self.object_id,
            self.site_id,
            self.author_id,
            self.author_name,
            self.modified,
            self.title,
            self.content,
            self.url,
            self.slug,
            self.status,
            self.object_type,
        )
        if (
            any(type(value) is not str for value in string_values)
            or not self.modified
            or type(self.comments_open) is not bool
            or type(self.pings_open) is not bool
            or type(self.likes_enabled) is not bool
            or type(self.sharing_enabled) is not bool
            or type(self.publicize_urls_empty) is not bool
        ):
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class MvpPageEntry(_RedactedWave3Value):
    object_id: str
    site_id: str
    object_type: str
    slug: str
    status: str

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not str
                for value in (
                    self.object_id,
                    self.site_id,
                    self.object_type,
                    self.slug,
                    self.status,
                )
            )
            or self.site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID
        ):
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class MvpPageScan(_RedactedWave3Value):
    entries: tuple[MvpPageEntry, ...]

    def __post_init__(self) -> None:
        if (
            type(self.entries) is not tuple
            or len(self.entries) > 100
            or any(type(entry) is not MvpPageEntry for entry in self.entries)
        ):
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class MvpMutationAcknowledgement(_RedactedWave3Value):
    object_id: str
    site_id: str

    def __post_init__(self) -> None:
        if (
            type(self.object_id) is not str
            or type(self.site_id) is not str
            or self.site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID
            or _CANONICAL_ID.fullmatch(self.object_id) is None
            or self.object_id == "0"
        ):
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS
            )


__all__ = [
    "MvpDraftAffiliateState",
    "MvpDraftBaseState",
    "MvpDraftContentBundle",
    "MvpDraftManualReviewState",
    "MvpDraftObservation",
    "MvpDraftOperation",
    "MvpDraftOperationPreview",
    "MvpDraftOperationState",
    "MvpDraftPreview",
    "MvpDraftReasonCode",
    "MvpDraftResponseContext",
    "MvpDraftResponseStage",
    "MvpMutationAcknowledgement",
    "MvpPageEntry",
    "MvpPageScan",
    "MvpRemoteObject",
    "WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_AFFILIATE_PRODUCT_NAMES",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_CONTENT_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_MODIFIED",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH",
    "WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID",
    "WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME",
    "WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256",
    "WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER",
    "WORDPRESSCOM_MVP_WAVE3_OPERATION_BINDINGS",
    "WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH",
    "WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH",
    "WORDPRESSCOM_MVP_WAVE3_PAGE_SLUGS",
    "WORDPRESSCOM_MVP_WAVE3_PROVIDER_ORIGIN",
    "WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY",
    "WORDPRESSCOM_MVP_WAVE3_SCHEMA",
    "WORDPRESSCOM_MVP_WAVE3_SITE_ID",
    "WORDPRESSCOM_MVP_WAVE3_TARGET_ORIGIN",
    "WordPressComMvpDraftFailure",
    "WordPressComMvpDraftFailureCode",
    "fail_wordpresscom_mvp_draft",
    "normalize_wordpresscom_mvp_id",
    "normalize_wordpresscom_mvp_line_endings",
]
