"""Immutable values for the ST-1703 WordPress.com review-copy slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


WORDPRESSCOM_REVIEW_DRAFT_SCHEMA = "WORDPRESSCOM_REVIEW_DRAFT_V1"
WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA = "WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_V1"
WORDPRESSCOM_REVIEW_DRAFT_TARGET = "https://kurashierabinote.wordpress.com"
WORDPRESSCOM_REVIEW_DRAFT_PROVIDER_API_ORIGIN = "https://public-api.wordpress.com"
WORDPRESSCOM_REVIEW_DRAFT_NUMERIC_SITE_ID = 256699520
WORDPRESSCOM_REVIEW_DRAFT_API_PATH = "/rest/v1.1/sites/256699520/posts/new"
WORDPRESSCOM_REVIEW_DRAFT_STATUS = "draft"
WORDPRESSCOM_REVIEW_DRAFT_OPERATION = "CREATE_REVIEW_DRAFT"
WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX = "[レビュー用・未承認] "
WORDPRESSCOM_REVIEW_DRAFT_TITLE = (
    "[レビュー用・未承認] "
    "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
)
WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256 = (
    "6eab149a4057d3f21dad6fa9efdbe66aadfafa00f100038541a3971693a8503d"
)
WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256 = (
    "794cee08b70ea1762f2c78b9be9826a486ab1beec44844a9fbd013e740ee2abd"
)
WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY = "OWNER_AUTHORIZED_EXTERNAL_REVIEW_COPY"
WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS = "EXECUTED_LIVE_DRAFT_CREATE"
WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256 = (
    "0a10b777ccd1e786f34890458621a21a9684feb73cee2b6808a5facefeef65ee"
)
WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256 = (
    "798e005faee6c7367496a79e71b9a2d84fc9d9433e4e368276633a8539325cbd"
)
WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256 = (
    "5e69433222435305f8a2decef8840de4764565929d483f0e4d8b35fcd6ed7bf6"
)
WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256 = (
    "58e225050d2bf30593fdd039ed9a307cd35db928b946bec470acbb7aa442a233"
)
WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256 = (
    "730de77b730afd692ca734746a7321d29a5191244832e4f44fb0d84a871707b2"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_TITLE_CHARS = 500
_MAX_CONTENT_BYTES = 1_000_000
_MAX_DRAFT_ID = (1 << 63) - 1


class WordPressComReviewDraftFailureCode(StrEnum):
    """Closed, non-sensitive failures for the separate review-copy path."""

    CANDIDATE_INVALID = "REVIEW_DRAFT_CANDIDATE_INVALID"
    SOURCE_BINDING_INVALID = "REVIEW_DRAFT_SOURCE_BINDING_INVALID"
    MARKDOWN_INVALID = "REVIEW_DRAFT_MARKDOWN_INVALID"
    RECEIPT_INVALID = "REVIEW_DRAFT_RECEIPT_INVALID"
    JOURNAL_INVALID = "REVIEW_DRAFT_JOURNAL_INVALID"
    JOURNAL_PENDING = "REVIEW_DRAFT_JOURNAL_PENDING"
    JOURNAL_AMBIGUOUS = "REVIEW_DRAFT_JOURNAL_AMBIGUOUS"
    JOURNAL_MISMATCH = "REVIEW_DRAFT_JOURNAL_MISMATCH"
    JOURNAL_IO_FAILURE = "REVIEW_DRAFT_JOURNAL_IO_FAILURE"
    HTTPS_SETUP_INVALID = "REVIEW_DRAFT_HTTPS_SETUP_INVALID"
    CREATE_AMBIGUOUS = "REVIEW_DRAFT_CREATE_AMBIGUOUS"
    OAUTH_SECRET_STORE_INVALID = "REVIEW_DRAFT_OAUTH_SECRET_STORE_INVALID"
    OAUTH_TOKEN_EXISTS = "REVIEW_DRAFT_OAUTH_TOKEN_EXISTS"
    OAUTH_AUTHORIZATION_INVALID = "REVIEW_DRAFT_OAUTH_AUTHORIZATION_INVALID"
    OAUTH_CALLBACK_INVALID = "REVIEW_DRAFT_OAUTH_CALLBACK_INVALID"
    OAUTH_TOKEN_EXCHANGE_INVALID = "REVIEW_DRAFT_OAUTH_TOKEN_EXCHANGE_INVALID"


class WordPressComReviewDraftFailure(RuntimeError):
    """A sanitized review-copy boundary failure."""

    __slots__ = ("code",)

    def __init__(self, code: WordPressComReviewDraftFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


def fail_wordpresscom_review_draft(
    code: WordPressComReviewDraftFailureCode,
) -> NoReturn:
    raise WordPressComReviewDraftFailure(code) from None


def review_draft_operation_binding_sha256(
    *, title: object, content_sha256: object
) -> str:
    """Return the sole operation binding admitted by the approved slice."""

    if (
        type(title) is not str
        or title != WORDPRESSCOM_REVIEW_DRAFT_TITLE
        or type(content_sha256) is not str
        or content_sha256 != WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256
    ):
        fail_wordpresscom_review_draft(
            WordPressComReviewDraftFailureCode.CANDIDATE_INVALID
        )
    binding_json = json.dumps(
        {
            "api_path": WORDPRESSCOM_REVIEW_DRAFT_API_PATH,
            "article_sha256": WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256,
            "content_sha256": content_sha256,
            "handoff_sha256": WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
            "operation": WORDPRESSCOM_REVIEW_DRAFT_OPERATION,
            "source_packet_sha256": WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256,
            "target_origin": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
            "title": title,
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    binding_sha256 = hashlib.sha256(binding_json.encode("utf-8")).hexdigest()
    if binding_sha256 != WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256:
        fail_wordpresscom_review_draft(
            WordPressComReviewDraftFailureCode.CANDIDATE_INVALID
        )
    return binding_sha256


class _RedactedReviewDraftValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-review-draft>)"

    def __str__(self) -> str:
        return "<redacted-review-draft>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress.com review-draft value serialization is disabled")


class ReviewDraftDisposition(StrEnum):
    CREATED = "CREATED"
    COMMITTED_REPLAY = "COMMITTED_REPLAY"


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComReviewDraft(_RedactedReviewDraftValue):
    """One exact create-only review-copy candidate."""

    schema: str
    target_origin: str
    api_path: str
    operation: str
    title: str
    rendered_content: str
    content_sha256: str
    operation_binding_sha256: str
    handoff_sha256: str

    def __post_init__(self) -> None:
        content_bytes = 0
        if type(self.rendered_content) is str:
            try:
                content_bytes = len(
                    self.rendered_content.encode("utf-8", errors="strict")
                )
            except UnicodeError:
                content_bytes = 0
        if (
            type(self.schema) is not str
            or self.schema != WORDPRESSCOM_REVIEW_DRAFT_SCHEMA
            or type(self.target_origin) is not str
            or self.target_origin != WORDPRESSCOM_REVIEW_DRAFT_TARGET
            or type(self.api_path) is not str
            or self.api_path != WORDPRESSCOM_REVIEW_DRAFT_API_PATH
            or type(self.operation) is not str
            or self.operation != WORDPRESSCOM_REVIEW_DRAFT_OPERATION
            or type(self.title) is not str
            or self.title != WORDPRESSCOM_REVIEW_DRAFT_TITLE
            or len(self.title) > _MAX_TITLE_CHARS
            or self.title != self.title.strip()
            or any(
                ord(character) < 32 or ord(character) == 127 for character in self.title
            )
            or type(self.rendered_content) is not str
            or not 1 <= content_bytes <= _MAX_CONTENT_BYTES
            or type(self.content_sha256) is not str
            or self.content_sha256 != WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256
            or hashlib.sha256(
                self.rendered_content.encode("utf-8", errors="strict")
            ).hexdigest()
            != self.content_sha256
            or type(self.operation_binding_sha256) is not str
            or self.operation_binding_sha256
            != WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256
            or self.operation_binding_sha256
            != review_draft_operation_binding_sha256(
                title=self.title,
                content_sha256=self.content_sha256,
            )
            or type(self.handoff_sha256) is not str
            or self.handoff_sha256 != WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256
        ):
            fail_wordpresscom_review_draft(
                WordPressComReviewDraftFailureCode.CANDIDATE_INVALID
            )


def require_exact_wordpresscom_review_draft(
    candidate: object,
) -> WordPressComReviewDraft:
    """Recheck the exact immutable candidate at every outward trust boundary."""

    if type(candidate) is not WordPressComReviewDraft:
        fail_wordpresscom_review_draft(
            WordPressComReviewDraftFailureCode.CANDIDATE_INVALID
        )
    exact_candidate = candidate
    exact_candidate.__post_init__()
    return exact_candidate


@dataclass(frozen=True, slots=True, repr=False)
class WordPressComReviewDraftReceipt(_RedactedReviewDraftValue):
    """Sanitized receipt; it conveys no publication or production authority."""

    schema: str
    authority: str
    network_status: str
    target_origin: str
    draft_id: int
    status: str
    operation_binding_sha256: str
    content_sha256: str
    response_body_sha256: str
    disposition: ReviewDraftDisposition
    publication_authorized: bool
    production_eligible: bool

    def __post_init__(self) -> None:
        if (
            type(self.schema) is not str
            or self.schema != WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA
            or type(self.authority) is not str
            or self.authority != WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY
            or type(self.network_status) is not str
            or self.network_status != WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS
            or type(self.target_origin) is not str
            or self.target_origin != WORDPRESSCOM_REVIEW_DRAFT_TARGET
            or type(self.draft_id) is not int
            or not 1 <= self.draft_id <= _MAX_DRAFT_ID
            or type(self.status) is not str
            or self.status != WORDPRESSCOM_REVIEW_DRAFT_STATUS
            or type(self.operation_binding_sha256) is not str
            or _SHA256.fullmatch(self.operation_binding_sha256) is None
            or type(self.content_sha256) is not str
            or _SHA256.fullmatch(self.content_sha256) is None
            or type(self.response_body_sha256) is not str
            or _SHA256.fullmatch(self.response_body_sha256) is None
            or type(self.disposition) is not ReviewDraftDisposition
            or type(self.publication_authorized) is not bool
            or self.publication_authorized
            or type(self.production_eligible) is not bool
            or self.production_eligible
        ):
            fail_wordpresscom_review_draft(
                WordPressComReviewDraftFailureCode.RECEIPT_INVALID
            )


__all__ = [
    "ReviewDraftDisposition",
    "WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_API_PATH",
    "WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY",
    "WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS",
    "WORDPRESSCOM_REVIEW_DRAFT_NUMERIC_SITE_ID",
    "WORDPRESSCOM_REVIEW_DRAFT_OPERATION",
    "WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_PROVIDER_API_ORIGIN",
    "WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA",
    "WORDPRESSCOM_REVIEW_DRAFT_SCHEMA",
    "WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256",
    "WORDPRESSCOM_REVIEW_DRAFT_STATUS",
    "WORDPRESSCOM_REVIEW_DRAFT_TARGET",
    "WORDPRESSCOM_REVIEW_DRAFT_TITLE",
    "WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX",
    "WordPressComReviewDraft",
    "WordPressComReviewDraftFailure",
    "WordPressComReviewDraftFailureCode",
    "WordPressComReviewDraftReceipt",
    "fail_wordpresscom_review_draft",
    "require_exact_wordpresscom_review_draft",
    "review_draft_operation_binding_sha256",
]
