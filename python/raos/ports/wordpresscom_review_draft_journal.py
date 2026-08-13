"""Outward one-attempt boundary used only inside the durable draft journal."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.wordpresscom_review_draft import (
    WordPressComReviewDraft,
    WordPressComReviewDraftReceipt,
)


@runtime_checkable
class WordPressComReviewDraftAttemptPort(Protocol):
    """Preflight and attempt one create; it is not the application-facing port."""

    def require_create_capability(self, candidate: WordPressComReviewDraft) -> None: ...

    def attempt_create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt: ...


__all__ = ["WordPressComReviewDraftAttemptPort"]
