"""Narrow inward/outward ports for the ST-1703 self-hosted draft slice."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDraft,
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressRecoveryObservation,
)


@runtime_checkable
class SelfHostedWordPressDraftPort(Protocol):
    """Apply a local bound draft value or return an exact committed replay.

    The ST-1703 operational adapter implements CREATE only. UPDATE remains a
    local interface value with activation disabled.
    """

    def apply(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt: ...


@runtime_checkable
class SelfHostedWordPressAttemptPort(Protocol):
    """Perform the sole allowed outward attempt after durable INTENT.

    Any live implementation in this slice must reject UPDATE before secret or
    transport access.
    """

    def attempt(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt: ...


@runtime_checkable
class SelfHostedWordPressRecoveryProbePort(Protocol):
    """Observe the exact draft slug once without any mutation or fallback."""

    def observe(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressRecoveryObservation: ...


__all__ = [
    "SelfHostedWordPressAttemptPort",
    "SelfHostedWordPressDraftPort",
    "SelfHostedWordPressRecoveryProbePort",
]
