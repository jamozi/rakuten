"""Closed values for the ST-1704 WordPress publication operator v2.

Only the four ``PUBLISH_NEW`` review drafts from the ST-1704 publication plan
can be represented.  The types deliberately cannot carry title, excerpt,
content, snapshot JSON, media, arbitrary taxonomy, arbitrary URLs, or the
AT-003 existing-post update.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex

from raos.domain.editorial.self_hosted_editorial_pilot import (
    PILOT_ORIGIN,
    PILOT_REVIEW_STATUS,
    ReviewDraftRequest,
    article_identity,
)


PUBLICATION_OPERATOR_ORIGIN: Final = PILOT_ORIGIN
PUBLICATION_OPERATOR_NAMESPACE: Final = "/wp-json/raos-operator/v2"
PUBLICATION_OPERATOR_EXPECTED_ROLE: Final = "raos_operator_executor"
PUBLICATION_OPERATOR_CONTRACT_VERSION: Final = 2
PUBLICATION_OPERATOR_PROFILE_VERSION: Final = 2
PUBLICATION_OPERATOR_TTL_SECONDS: Final = 900
PUBLICATION_OPERATOR_CATEGORY_NAME: Final = "暮らしの道具"
PUBLICATION_OPERATOR_CATEGORY_CONTRACT: Final = "KURASHINO_DOGU_SINGLE_V1"
PUBLICATION_OPERATOR_VERSION: Final = "2.0.0"
PUBLICATION_OPERATOR_RESULT_CODE: Final = "ST1704_ARTICLE_PUBLISHED"

ST1704_PUBLISH_NEW_ARTICLE_IDS: Final = (
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
ST1704_PUBLISH_NEW_ARTICLE_ID_SET: Final = frozenset(ST1704_PUBLISH_NEW_ARTICLE_IDS)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z",
    re.ASCII,
)
_MAX_POST_ID: Final = (1 << 63) - 1


class PublicationOperatorOperation(StrEnum):
    PUBLISH_ST1704_ARTICLE = "PUBLISH_ST1704_ARTICLE"


class PublicationProposalState(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    NEEDS_RECOVERY = "NEEDS_RECOVERY"
    EXPIRED = "EXPIRED"


class PublicationOperatorFailureCode(StrEnum):
    INVALID_ARGUMENT = "ST1704_PUBLICATION_OPERATOR_INVALID_ARGUMENT"
    ARTICLE_NOT_ALLOWLISTED = "ST1704_PUBLICATION_OPERATOR_ARTICLE_NOT_ALLOWLISTED"
    REVIEW_BINDING_INVALID = "ST1704_PUBLICATION_OPERATOR_REVIEW_BINDING_INVALID"
    SOURCE_POST_MISMATCH = "ST1704_PUBLICATION_OPERATOR_SOURCE_POST_MISMATCH"
    CATEGORY_PREREQUISITE_FAILED = (
        "ST1704_PUBLICATION_OPERATOR_CATEGORY_PREREQUISITE_FAILED"
    )
    CREDENTIAL_STORE_INVALID = "ST1704_PUBLICATION_OPERATOR_CREDENTIAL_STORE_INVALID"
    REQUEST_INVALID = "ST1704_PUBLICATION_OPERATOR_REQUEST_INVALID"
    RESPONSE_INVALID = "ST1704_PUBLICATION_OPERATOR_RESPONSE_INVALID"
    TRANSPORT_REFUSED = "ST1704_PUBLICATION_OPERATOR_TRANSPORT_REFUSED"
    OUTCOME_AMBIGUOUS = "ST1704_PUBLICATION_OPERATOR_OUTCOME_AMBIGUOUS"
    PROPOSAL_NOT_CREATED = "ST1704_PUBLICATION_OPERATOR_PROPOSAL_NOT_CREATED"
    JOURNAL_UNSAFE = "ST1704_PUBLICATION_OPERATOR_JOURNAL_UNSAFE"
    JOURNAL_AMBIGUOUS = "ST1704_PUBLICATION_OPERATOR_JOURNAL_AMBIGUOUS"
    JOURNAL_MISMATCH = "ST1704_PUBLICATION_OPERATOR_JOURNAL_MISMATCH"
    WRITE_WINDOW_DISABLED = "ST1704_PUBLICATION_OPERATOR_WRITE_WINDOW_DISABLED"
    HUMAN_APPROVAL_REQUIRED = "ST1704_PUBLICATION_OPERATOR_HUMAN_APPROVAL_REQUIRED"
    SEPARATION_OF_DUTIES_REQUIRED = (
        "ST1704_PUBLICATION_OPERATOR_SEPARATION_OF_DUTIES_REQUIRED"
    )
    PROPOSAL_EXPIRED = "ST1704_PUBLICATION_OPERATOR_PROPOSAL_EXPIRED"
    PRECONDITION_DRIFT = "ST1704_PUBLICATION_OPERATOR_PRECONDITION_DRIFT"
    PUBLIC_READBACK_MISMATCH = "ST1704_PUBLICATION_OPERATOR_PUBLIC_READBACK_MISMATCH"
    OPERATION_NOT_ALLOWED = "ST1704_PUBLICATION_OPERATOR_OPERATION_NOT_ALLOWED"
    INTERNAL_FAILURE = "ST1704_PUBLICATION_OPERATOR_INTERNAL_FAILURE"


class PublicationOperatorFailure(RuntimeError):
    """Sanitized failure without response, credential, or article material."""

    __slots__ = ("_code",)

    def __init__(self, code: PublicationOperatorFailureCode) -> None:
        if type(code) is not PublicationOperatorFailureCode:
            raise TypeError("invalid publication operator failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> PublicationOperatorFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PublicationOperatorFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication operator failure serialization is disabled")


def fail_publication_operator(
    code: PublicationOperatorFailureCode = (
        PublicationOperatorFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise PublicationOperatorFailure(code) from None


def require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_publication_operator()
    return value


def require_publish_article_id(value: object) -> str:
    if type(value) is not str or value not in ST1704_PUBLISH_NEW_ARTICLE_ID_SET:
        fail_publication_operator(
            PublicationOperatorFailureCode.ARTICLE_NOT_ALLOWLISTED
        )
    return value


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail_publication_operator()


def _require_post_id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_POST_ID:
        fail_publication_operator(PublicationOperatorFailureCode.REVIEW_BINDING_INVALID)
    return value


def _require_rfc3339(value: object) -> str:
    if type(value) is not str or _RFC3339.fullmatch(value) is None:
        fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class CommittedReviewDraftBinding:
    """Content-free binding loaded from the owner-private v1 committed journal."""

    article_id: str
    draft_post_id: int
    packet_sha256: str
    request_sha256: str
    snapshot_payload_sha256: str
    visible_content_sha256: str
    public_slug: str

    def __post_init__(self) -> None:
        identity = article_identity(require_publish_article_id(self.article_id))
        _require_post_id(self.draft_post_id)
        for value in (
            self.packet_sha256,
            self.request_sha256,
            self.snapshot_payload_sha256,
            self.visible_content_sha256,
        ):
            require_sha256(value)
        if self.public_slug != identity.slug:
            fail_publication_operator(
                PublicationOperatorFailureCode.REVIEW_BINDING_INVALID
            )

    @classmethod
    def from_committed_request(
        cls, request: ReviewDraftRequest, draft_post_id: int
    ) -> CommittedReviewDraftBinding:
        if type(request) is not ReviewDraftRequest:
            fail_publication_operator(
                PublicationOperatorFailureCode.REVIEW_BINDING_INVALID
            )
        require_publish_article_id(request.article_id)
        if (
            request.status != PILOT_REVIEW_STATUS
            or request.publication_authority is not False
            or request.live_authority is not False
        ):
            fail_publication_operator(
                PublicationOperatorFailureCode.REVIEW_BINDING_INVALID
            )
        return cls(
            article_id=request.article_id,
            draft_post_id=_require_post_id(draft_post_id),
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            snapshot_payload_sha256=request.snapshot.payload_sha256,
            visible_content_sha256=(request.snapshot.payload.visible_content_sha256),
            public_slug=request.public_slug,
        )

    def payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "draft_post_id": self.draft_post_id,
            "packet_sha256": self.packet_sha256,
            "public_slug": self.public_slug,
            "request_sha256": self.request_sha256,
            "snapshot_payload_sha256": self.snapshot_payload_sha256,
            "visible_content_sha256": self.visible_content_sha256,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PublicationProposal:
    binding: CommittedReviewDraftBinding
    request_token: str
    proposal_id: str
    operation: PublicationOperatorOperation = (
        PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE
    )
    ttl_seconds: int = PUBLICATION_OPERATOR_TTL_SECONDS

    def __post_init__(self) -> None:
        if (
            type(self.binding) is not CommittedReviewDraftBinding
            or self.operation is not PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE
            or type(self.ttl_seconds) is not int
            or self.ttl_seconds != PUBLICATION_OPERATOR_TTL_SECONDS
        ):
            fail_publication_operator()
        require_sha256(self.request_token)
        require_sha256(self.proposal_id)
        if self.proposal_id != hashlib.sha256(self.canonical_bytes()).hexdigest():
            fail_publication_operator()

    @classmethod
    def bind(
        cls, binding: CommittedReviewDraftBinding, request_token: str
    ) -> PublicationProposal:
        if type(binding) is not CommittedReviewDraftBinding:
            fail_publication_operator()
        request_token = require_sha256(request_token)
        payload = cls.payload_for(binding, request_token)
        return cls(
            binding=binding,
            request_token=request_token,
            proposal_id=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    @staticmethod
    def payload_for(
        binding: CommittedReviewDraftBinding, request_token: str
    ) -> dict[str, object]:
        if type(binding) is not CommittedReviewDraftBinding:
            fail_publication_operator()
        request_token = require_sha256(request_token)
        return {
            **binding.payload(),
            "category_contract": PUBLICATION_OPERATOR_CATEGORY_CONTRACT,
            "operator_contract_version": PUBLICATION_OPERATOR_CONTRACT_VERSION,
            "operation": PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE.value,
            "profile_version": PUBLICATION_OPERATOR_PROFILE_VERSION,
            "request_token": request_token,
            "site_origin": PUBLICATION_OPERATOR_ORIGIN,
            "ttl_seconds": PUBLICATION_OPERATOR_TTL_SECONDS,
        }

    def payload(self) -> dict[str, object]:
        return self.payload_for(self.binding, self.request_token)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.payload())


@dataclass(frozen=True, slots=True, repr=False)
class PublicationProposalReceipt:
    proposal_id: str
    operation: PublicationOperatorOperation
    state: PublicationProposalState
    created_at: str
    expires_at: str
    replayed: bool

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        if (
            type(self.operation) is not PublicationOperatorOperation
            or type(self.state) is not PublicationProposalState
            or type(self.replayed) is not bool
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
        created_text = _require_rfc3339(self.created_at)
        expires_text = _require_rfc3339(self.expires_at)
        try:
            created = datetime.fromisoformat(created_text.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(expires_text.replace("Z", "+00:00"))
        except ValueError:
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
        if expires - created != timedelta(seconds=PUBLICATION_OPERATOR_TTL_SECONDS):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)
        if not self.replayed and (
            self.state is not PublicationProposalState.PROPOSED
            or expires <= datetime.now(timezone.utc)
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def is_expired(self, now: datetime | None = None) -> bool:
        if now is None:
            observed = datetime.now(timezone.utc)
        elif type(now) is not datetime or now.tzinfo is None:
            fail_publication_operator()
        else:
            observed = now
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return expires <= observed

    def requires_new_proposal(self, now: datetime | None = None) -> bool:
        return self.state in {
            PublicationProposalState.FAILED,
            PublicationProposalState.EXPIRED,
        } or (
            self.state
            in {
                PublicationProposalState.PROPOSED,
                PublicationProposalState.APPROVED,
            }
            and self.is_expired(now)
        )

    def public_payload(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "operation": self.operation.value,
            "proposal_id": self.proposal_id,
            "replayed": self.replayed,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PublicationApplyReceipt:
    proposal_id: str
    operation: PublicationOperatorOperation
    result_code: str
    replayed: bool
    state: PublicationProposalState = PublicationProposalState.APPLIED

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        if (
            self.operation is not PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE
            or self.state is not PublicationProposalState.APPLIED
            or self.result_code != PUBLICATION_OPERATOR_RESULT_CODE
            or type(self.replayed) is not bool
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "operation": self.operation.value,
            "proposal_id": self.proposal_id,
            "replayed": self.replayed,
            "result_code": self.result_code,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PublicationOperatorStatus:
    master_writes_enabled: bool
    publication_writes_enabled: bool
    writes_enabled: bool
    proposal_counts: tuple[tuple[PublicationProposalState, int], ...]
    operator_version: str = PUBLICATION_OPERATOR_VERSION

    def __post_init__(self) -> None:
        expected_states = tuple(PublicationProposalState)
        if (
            type(self.master_writes_enabled) is not bool
            or type(self.publication_writes_enabled) is not bool
            or type(self.writes_enabled) is not bool
            or self.writes_enabled
            is not (self.master_writes_enabled and self.publication_writes_enabled)
            or self.operator_version != PUBLICATION_OPERATOR_VERSION
            or type(self.proposal_counts) is not tuple
            or tuple(state for state, _count in self.proposal_counts) != expected_states
            or any(
                type(count) is not int or not 0 <= count <= _MAX_POST_ID
                for _state, count in self.proposal_counts
            )
        ):
            fail_publication_operator(PublicationOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "master_writes_enabled": self.master_writes_enabled,
            "operator_version": self.operator_version,
            "proposal_counts": {
                state.value: count for state, count in self.proposal_counts
            },
            "publication_writes_enabled": self.publication_writes_enabled,
            "supported_operations": [
                PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE.value
            ],
            "writes_enabled": self.writes_enabled,
        }


__all__ = [
    "CommittedReviewDraftBinding",
    "PUBLICATION_OPERATOR_CATEGORY_NAME",
    "PUBLICATION_OPERATOR_CATEGORY_CONTRACT",
    "PUBLICATION_OPERATOR_CONTRACT_VERSION",
    "PUBLICATION_OPERATOR_EXPECTED_ROLE",
    "PUBLICATION_OPERATOR_NAMESPACE",
    "PUBLICATION_OPERATOR_ORIGIN",
    "PUBLICATION_OPERATOR_PROFILE_VERSION",
    "PUBLICATION_OPERATOR_RESULT_CODE",
    "PUBLICATION_OPERATOR_TTL_SECONDS",
    "PUBLICATION_OPERATOR_VERSION",
    "PublicationApplyReceipt",
    "PublicationOperatorFailure",
    "PublicationOperatorFailureCode",
    "PublicationOperatorOperation",
    "PublicationOperatorStatus",
    "PublicationProposal",
    "PublicationProposalReceipt",
    "PublicationProposalState",
    "ST1704_PUBLISH_NEW_ARTICLE_IDS",
    "ST1704_PUBLISH_NEW_ARTICLE_ID_SET",
    "canonical_json_bytes",
    "fail_publication_operator",
    "require_publish_article_id",
    "require_sha256",
]
