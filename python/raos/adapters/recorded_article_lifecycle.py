"""Immutable ordered recorded exchange for the local ST-0802 seam."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, SupportsIndex, final, get_args

from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.article_lifecycle import (
    ArticleLifecycleFailureCode,
    ArticleLifecycleMode,
    ArticleLifecycleOperation,
    ArticleLifecycleOutcome,
    ArticleLifecycleRequest,
    fail_article_lifecycle,
)


_MAX_SCRIPT_CAPACITY = 100_000
_REQUEST_TYPES = get_args(ArticleLifecycleRequest)
_OUTCOME_TYPES = get_args(ArticleLifecycleOutcome)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedArticleLifecycleStep:
    request: ArticleLifecycleRequest
    outcome: ArticleLifecycleOutcome

    def __post_init__(self) -> None:
        if (
            type(self.request) not in _REQUEST_TYPES
            or type(self.outcome) not in _OUTCOME_TYPES
            or type(self.request.operation) is not ArticleLifecycleOperation
            or type(self.outcome.operation) is not ArticleLifecycleOperation
            or self.request.operation is not self.outcome.operation
        ):
            fail_article_lifecycle()

    def __repr__(self) -> str:
        return "RecordedArticleLifecycleStep(<redacted-article-lifecycle>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded lifecycle serialization is not supported")


def _replay_identity(step: RecordedArticleLifecycleStep) -> tuple[object, ...] | None:
    key = getattr(step.request, "idempotency_key", None)
    if key is None:
        return None
    return (
        step.request.operation,
        step.request.target.site_id,
        step.request.target.resource_id,
        key,
    )


@final
class RecordedArticleLifecycleExchange:
    """Consume exact pre-scripted requests without a business-state store."""

    __slots__ = ("_index", "_lock", "_scripts")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        mode: ArticleLifecycleMode,
        script_capacity: int,
        scripts: tuple[RecordedArticleLifecycleStep, ...],
    ) -> None:
        replay_identities = (
            tuple(
                identity
                for step in scripts
                if (identity := _replay_identity(step)) is not None
            )
            if type(scripts) is tuple
            else ()
        )
        if (
            environment not in {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
            or mode is not ArticleLifecycleMode.RECORDED_TEST_ONLY
            or type(script_capacity) is not int
            or not 0 < script_capacity <= _MAX_SCRIPT_CAPACITY
            or type(scripts) is not tuple
            or not scripts
            or len(scripts) > script_capacity
            or any(type(step) is not RecordedArticleLifecycleStep for step in scripts)
            or any(
                left.request == right.request
                for index, left in enumerate(scripts)
                for right in scripts[index + 1 :]
            )
            or len(set(replay_identities)) != len(replay_identities)
        ):
            fail_article_lifecycle()
        self._scripts = scripts
        self._index = 0
        self._lock = RLock()

    def __repr__(self) -> str:
        return "RecordedArticleLifecycleExchange(<redacted-article-lifecycle>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded lifecycle exchange serialization is not supported")

    def exchange(self, request: ArticleLifecycleRequest) -> ArticleLifecycleOutcome:
        with self._lock:
            if self._index >= len(self._scripts):
                fail_article_lifecycle(
                    ArticleLifecycleFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            step = self._scripts[self._index]
            if type(request) is not type(step.request) or request != step.request:
                fail_article_lifecycle(
                    ArticleLifecycleFailureCode.LOCAL_EXCHANGE_UNAVAILABLE
                )
            self._index += 1
            return step.outcome


__all__ = ["RecordedArticleLifecycleExchange", "RecordedArticleLifecycleStep"]
