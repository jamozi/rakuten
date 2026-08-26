"""Read-only bridge from the committed ST-1704 review journal to v2."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn, final

from raos.adapters.self_hosted_editorial_pilot_json import (
    OwnerPrivateLiveReviewDraftJournal,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PublicVerification,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    fail_editorial_pilot,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    fail_publication_operator,
    require_publish_article_id,
)


@final
class _ReadOnlyReviewDraftPort:
    """Satisfy the legacy journal constructor without granting an operation."""

    __slots__ = ()

    @staticmethod
    def _refuse() -> NoReturn:
        fail_editorial_pilot(EditorialPilotFailureCode.OPERATION_NOT_ALLOWED)

    def preflight(self, request: ReviewDraftRequest, command: str) -> None:
        del request, command
        self._refuse()

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None:
        del request, command
        self._refuse()

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        del request
        self._refuse()

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        del request
        self._refuse()

    def verify_public(
        self, request: ReviewDraftRequest, expected_public_post_id: int
    ) -> PublicVerification:
        del request, expected_public_post_id
        self._refuse()


def _map_review_failure(error: EditorialPilotFailure) -> NoReturn:
    mappings = {
        EditorialPilotFailureCode.JOURNAL_UNSAFE: (
            PublicationOperatorFailureCode.JOURNAL_UNSAFE
        ),
        EditorialPilotFailureCode.JOURNAL_AMBIGUOUS: (
            PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS
        ),
        EditorialPilotFailureCode.JOURNAL_MISMATCH: (
            PublicationOperatorFailureCode.JOURNAL_MISMATCH
        ),
    }
    fail_publication_operator(
        mappings.get(
            error.code,
            PublicationOperatorFailureCode.REVIEW_BINDING_INVALID,
        )
    )


@final
class OwnerPrivateCommittedReviewDraftBindingAdapter:
    """Load only the exact v1 COMMITTED request and its preserved post ID."""

    __slots__ = ("repository_root",)

    def __init__(self, repository_root: object) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_UNSAFE)
        self.repository_root = repository_root

    def __repr__(self) -> str:
        return "OwnerPrivateCommittedReviewDraftBindingAdapter(<redacted>)"

    def load(self, article_id: str) -> CommittedReviewDraftBinding:
        article_id = require_publish_article_id(article_id)
        try:
            request, draft_post_id = OwnerPrivateLiveReviewDraftJournal(
                self.repository_root,
                _ReadOnlyReviewDraftPort(),
            ).committed_request(article_id)
        except PublicationOperatorFailure:
            raise
        except EditorialPilotFailure as error:
            _map_review_failure(error)
        except BaseException:
            fail_publication_operator(PublicationOperatorFailureCode.JOURNAL_UNSAFE)
        if request.article_id != article_id:
            fail_publication_operator(
                PublicationOperatorFailureCode.REVIEW_BINDING_INVALID
            )
        return CommittedReviewDraftBinding.from_committed_request(
            request, draft_post_id
        )


__all__ = ["OwnerPrivateCommittedReviewDraftBindingAdapter"]
