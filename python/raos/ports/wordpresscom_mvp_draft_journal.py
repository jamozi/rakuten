"""Append-only state boundary for the fixed WordPress.com Wave 3 operations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contextlib import AbstractContextManager
from dataclasses import dataclass
from raos.domain.editorial.wordpresscom_mvp_drafts import MvpDraftOperationState


@dataclass(frozen=True, slots=True)
class MvpDraftJournalEntry:
    sequence: int
    operation_id: str
    operation_binding_sha256: str
    state: MvpDraftOperationState
    reason_code: str
    object_id: str | None
    previous_record_sha256: str
    record_sha256: str


@runtime_checkable
class WordPressComMvpDraftJournalPort(Protocol):
    """Expose only current state and immutable append; no update/delete operation."""

    def locked(self) -> AbstractContextManager[None]: ...

    def entries(self) -> tuple[MvpDraftJournalEntry, ...]: ...

    def inspect(self) -> tuple[MvpDraftJournalEntry, ...]: ...

    def append(
        self,
        *,
        operation_id: str,
        operation_binding_sha256: str,
        state: MvpDraftOperationState,
        reason_code: str,
        object_id: str | None,
    ) -> MvpDraftJournalEntry: ...


__all__ = ["MvpDraftJournalEntry", "WordPressComMvpDraftJournalPort"]
