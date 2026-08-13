"""Deterministic in-memory WordPress draft adapter for local ST-1703 use."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from threading import RLock
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    DraftDisposition,
    DraftOperation,
    MarketLearningPilotFailureCode,
    PILOT_SERIALIZATION_PROFILE,
    PilotExecutionStatus,
    WORDPRESS_DRAFT_STATUS,
    WordPressDraftReceipt,
    fail_market_learning_pilot,
)


_MAX_DRAFT_CAPACITY = 10_000


@dataclass(frozen=True, slots=True, repr=False)
class _RecordedDraftState:
    draft_id: int
    article_version_id: str
    content_binding_sha256: str
    logical_draft_sha256: str


def _digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        fail_market_learning_pilot()
    return hashlib.sha256(encoded).hexdigest()


def _draft_id(candidate: BoundWordPressDraft) -> int:
    value = int(candidate.content_binding_sha256[:16], 16) & ((1 << 63) - 1)
    return value or 1


def _logical_draft_sha256(candidate: BoundWordPressDraft, draft_id: int) -> str:
    return _digest(
        {
            "article_version_id": candidate.intent.article_version_id,
            "draft_id": draft_id,
            "profile": PILOT_SERIALIZATION_PROFILE,
        }
    )


@final
class RecordedWordPressDraftAdapter:
    """Apply exact draft-only operations with deterministic local replay."""

    __slots__ = (
        "_draft_capacity",
        "_drafts_by_article",
        "_lock",
        "_receipts_by_operation",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        draft_capacity: int,
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or type(draft_capacity) is not int
            or not 1 <= draft_capacity <= _MAX_DRAFT_CAPACITY
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.ENVIRONMENT_DISABLED
            )
        self._draft_capacity = draft_capacity
        self._drafts_by_article: dict[str, _RecordedDraftState] = {}
        self._receipts_by_operation: dict[str, WordPressDraftReceipt] = {}
        self._lock = RLock()

    @property
    def logical_draft_count(self) -> int:
        with self._lock:
            return len(self._drafts_by_article)

    @property
    def applied_operation_count(self) -> int:
        with self._lock:
            return len(self._receipts_by_operation)

    def __repr__(self) -> str:
        return "RecordedWordPressDraftAdapter(<redacted-wordpress-drafts>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded WordPress draft serialization is disabled")

    def apply(self, candidate: BoundWordPressDraft) -> WordPressDraftReceipt:
        if type(candidate) is not BoundWordPressDraft:
            fail_market_learning_pilot()
        with self._lock:
            prior_receipt = self._receipts_by_operation.get(
                candidate.operation_binding_sha256
            )
            if prior_receipt is not None:
                return self._replayed(prior_receipt)
            prior_state = self._drafts_by_article.get(
                candidate.intent.article_version_id
            )
            if candidate.intent.operation is DraftOperation.CREATE_DRAFT:
                return self._create(candidate, prior_state)
            return self._update(candidate, prior_state)

    def _create(
        self,
        candidate: BoundWordPressDraft,
        prior_state: _RecordedDraftState | None,
    ) -> WordPressDraftReceipt:
        if prior_state is not None:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_UPDATE_REQUIRED
            )
        if len(self._drafts_by_article) >= self._draft_capacity:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_EXCHANGE_UNAVAILABLE
            )
        draft_id = _draft_id(candidate)
        if any(
            state.draft_id == draft_id for state in self._drafts_by_article.values()
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_EXCHANGE_UNAVAILABLE
            )
        logical_digest = _logical_draft_sha256(candidate, draft_id)
        state = _RecordedDraftState(
            draft_id=draft_id,
            article_version_id=candidate.intent.article_version_id,
            content_binding_sha256=candidate.content_binding_sha256,
            logical_draft_sha256=logical_digest,
        )
        receipt = self._receipt(
            candidate=candidate,
            state=state,
            disposition=DraftDisposition.CREATED,
        )
        self._drafts_by_article[state.article_version_id] = state
        self._receipts_by_operation[candidate.operation_binding_sha256] = receipt
        return receipt

    def _update(
        self,
        candidate: BoundWordPressDraft,
        prior_state: _RecordedDraftState | None,
    ) -> WordPressDraftReceipt:
        if (
            prior_state is None
            or candidate.intent.existing_draft_id != prior_state.draft_id
        ):
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_TARGET_MISMATCH
            )
        if candidate.content_binding_sha256 == prior_state.content_binding_sha256:
            fail_market_learning_pilot(
                MarketLearningPilotFailureCode.DRAFT_UPDATE_REQUIRED
            )
        updated_state = _RecordedDraftState(
            draft_id=prior_state.draft_id,
            article_version_id=prior_state.article_version_id,
            content_binding_sha256=candidate.content_binding_sha256,
            logical_draft_sha256=prior_state.logical_draft_sha256,
        )
        receipt = self._receipt(
            candidate=candidate,
            state=updated_state,
            disposition=DraftDisposition.UPDATED,
        )
        self._drafts_by_article[updated_state.article_version_id] = updated_state
        self._receipts_by_operation[candidate.operation_binding_sha256] = receipt
        return receipt

    @staticmethod
    def _receipt(
        *,
        candidate: BoundWordPressDraft,
        state: _RecordedDraftState,
        disposition: DraftDisposition,
    ) -> WordPressDraftReceipt:
        return WordPressDraftReceipt(
            draft_id=state.draft_id,
            operation=candidate.intent.operation,
            disposition=disposition,
            status=WORDPRESS_DRAFT_STATUS,
            content_binding_sha256=candidate.content_binding_sha256,
            operation_binding_sha256=candidate.operation_binding_sha256,
            logical_draft_sha256=state.logical_draft_sha256,
            network_status=PilotExecutionStatus.NOT_EXECUTED,
            publication_authorized=False,
            production_eligible=False,
        )

    @staticmethod
    def _replayed(receipt: WordPressDraftReceipt) -> WordPressDraftReceipt:
        return WordPressDraftReceipt(
            draft_id=receipt.draft_id,
            operation=receipt.operation,
            disposition=DraftDisposition.REPLAYED,
            status=receipt.status,
            content_binding_sha256=receipt.content_binding_sha256,
            operation_binding_sha256=receipt.operation_binding_sha256,
            logical_draft_sha256=receipt.logical_draft_sha256,
            network_status=receipt.network_status,
            publication_authorized=receipt.publication_authorized,
            production_eligible=receipt.production_eligible,
        )


__all__ = ["RecordedWordPressDraftAdapter"]
