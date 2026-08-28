"""Isolated business observations; deliberately cannot rank products."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from raos.domain.decision_support_v2.models import exact_decimal


@dataclass(frozen=True, slots=True)
class BusinessObservation:
    article_id: str
    confirmed_reward_jpy: Decimal | None
    qualified_clicks: int | None
    sessions: int | None
    operating_cost_jpy: Decimal | None

    def __post_init__(self) -> None:
        for name in ("confirmed_reward_jpy", "operating_cost_jpy"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, exact_decimal(value))
        for name in ("qualified_clicks", "sessions"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError("counts cannot be negative")

    @property
    def confirmed_epc(self) -> Decimal | None:
        if self.confirmed_reward_jpy is None or not self.qualified_clicks:
            return None
        return self.confirmed_reward_jpy / Decimal(self.qualified_clicks)

    @property
    def confirmed_rpm(self) -> Decimal | None:
        if self.confirmed_reward_jpy is None or not self.sessions:
            return None
        return self.confirmed_reward_jpy * Decimal(1000) / Decimal(self.sessions)

    @property
    def contribution_profit(self) -> Decimal | None:
        if self.confirmed_reward_jpy is None or self.operating_cost_jpy is None:
            return None
        return self.confirmed_reward_jpy - self.operating_cost_jpy


def business_fields() -> frozenset[str]:
    return frozenset(
        {
            "confirmed_reward_jpy",
            "qualified_clicks",
            "sessions",
            "operating_cost_jpy",
            "confirmed_epc",
            "confirmed_rpm",
            "contribution_profit",
        }
    )


__all__ = ["BusinessObservation", "business_fields"]
