"""Create-only inward port for one WordPress.com review copy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.wordpresscom_review_draft import (
    WordPressComReviewDraft,
    WordPressComReviewDraftReceipt,
)


@runtime_checkable
class WordPressComReviewDraftPort(Protocol):
    """Create or replay the one exact draft; no mutation capability is exposed."""

    def create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt: ...


__all__ = ["WordPressComReviewDraftPort"]
