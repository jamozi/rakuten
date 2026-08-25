"""Inward ports for the ST-1602 recorded synthetic alert runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from raos.domain.ops.slo_alert_runtime_v2 import (
    AlertLifecycleState,
    AlertPersistCommand,
    AlertPersistReceipt,
    AlertSnapshot,
    AlertTransitionOutcome,
    SloAlertFailureCode,
    fail,
)


class NotificationMode(StrEnum):
    LOCAL_LOG_ONLY_DISABLED = "LOCAL_LOG_ONLY_DISABLED"


class LocalNotificationOutcome(StrEnum):
    RECORDED_LOCAL_ONLY = "RECORDED_LOCAL_ONLY"
    REPLAYED_LOCAL_ONLY = "REPLAYED_LOCAL_ONLY"
    LOCAL_LOG_FAILED = "LOCAL_LOG_FAILED"


@dataclass(frozen=True, slots=True)
class LocalNotificationRecord:
    notification_fingerprint: str
    dedup_fingerprint: str
    instance_key: str
    alert_id: str
    severity: str
    owner_id: str
    runbook_id: str
    state: AlertLifecycleState
    outcome: AlertTransitionOutcome
    result_sha256: str
    external_action_count: int = 0
    delivery_claim: bool = False

    def __post_init__(self) -> None:
        sha256 = re.compile(r"[0-9a-f]{64}\Z")
        if (
            any(
                sha256.fullmatch(value) is None
                for value in (
                    self.notification_fingerprint,
                    self.dedup_fingerprint,
                    self.result_sha256,
                )
            )
            or type(self.instance_key) is not str
            or not self.instance_key.startswith(f"{self.alert_id}:")
            or type(self.alert_id) is not str
            or re.fullmatch(r"ALT-[0-9]{3}", self.alert_id) is None
            or self.severity not in {"SEV1", "SEV2", "SEV3", "SEV4"}
            or self.owner_id != "Operations Owner"
            or re.fullmatch(r"RB-[0-9]{3}", self.runbook_id) is None
            or type(self.state) is not AlertLifecycleState
            or type(self.outcome) is not AlertTransitionOutcome
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
            or type(self.delivery_claim) is not bool
            or self.delivery_claim
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "notification.record")


@runtime_checkable
class AlertStateJournal(Protocol):
    """Owner-private append-only state journal."""

    def load_latest(self, instance_key: str) -> AlertSnapshot | None:
        """Return the exact latest state or no state."""

        ...

    def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        """Compare-and-swap one append-only transition."""

        ...

    def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        """Recover an exact hash-bound ambiguous commit."""

        ...


@runtime_checkable
class LocalAlertNotificationPort(Protocol):
    """Disabled notification seam that may retain a local record only."""

    @property
    def mode(self) -> NotificationMode: ...

    @property
    def external_action_count(self) -> int: ...

    def record_local(self, record: LocalNotificationRecord) -> LocalNotificationOutcome:
        """Record locally without attempting any delivery."""

        ...


__all__ = [
    "AlertStateJournal",
    "LocalAlertNotificationPort",
    "LocalNotificationOutcome",
    "LocalNotificationRecord",
    "NotificationMode",
]
