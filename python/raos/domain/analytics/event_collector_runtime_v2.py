"""Durable recorded-local result contract for ST-1201 V2.

This module adds no tracking, browser, provider, credential, retention,
deletion, publication, or network authority.  It only describes the receipt
returned after an already validated synthetic event is committed to an
owner-private local journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.analytics.event_collector import (
    CollectorDecision,
    CollectorExecution,
    ConsentAuthority,
    EventDigest,
    RecordedStoreDisposition,
    TrackingActivation,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-durable-event>"


class DurableEventStoreFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PRIVATE_PATH_INVALID = "PRIVATE_PATH_INVALID"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    STORAGE_FAILED = "STORAGE_FAILED"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"


class DurableEventStoreFailure(RuntimeError):
    """Closed regular exception, safe for context-manager traceback restore."""

    __slots__ = ("code",)

    def __init__(self, code: DurableEventStoreFailureCode) -> None:
        if type(code) is not DurableEventStoreFailureCode:
            raise TypeError("invalid durable event failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"DurableEventStoreFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("durable event failure serialization is not supported")


def fail_durable_event_store(
    code: DurableEventStoreFailureCode = DurableEventStoreFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise DurableEventStoreFailure(code) from None


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_durable_event_store()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_durable_event_store()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class DurableEventReceiptV2:
    event_id: UUID
    digest: EventDigest
    disposition: RecordedStoreDisposition
    sequence: int
    previous_record_sha256: str
    record_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        _uuid7(self.event_id)
        if (
            type(self.digest) is not EventDigest
            or type(self.disposition) is not RecordedStoreDisposition
            or type(self.sequence) is not int
            or self.sequence < 1
            or type(self.replayed) is not bool
            or (
                self.replayed
                != (self.disposition is RecordedStoreDisposition.RECORDED_DUPLICATE)
            )
        ):
            fail_durable_event_store()
        _sha256(self.previous_record_sha256)
        _sha256(self.record_sha256)

    def __repr__(self) -> str:
        return f"DurableEventReceiptV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class DurableEventCollectionResultV2:
    receipt: DurableEventReceiptV2
    execution: CollectorExecution
    tracking_activation: TrackingActivation
    persistence: str
    consent_authority: ConsentAuthority
    measurement_observed: bool
    decision: CollectorDecision
    formal_tst_012: CollectorExecution
    formal_tst_030: CollectorExecution
    formal_tst_031: CollectorExecution

    def __post_init__(self) -> None:
        if (
            type(self.receipt) is not DurableEventReceiptV2
            or self.execution is not CollectorExecution.RECORDED_TEST_ONLY
            or self.tracking_activation is not TrackingActivation.DISABLED
            or self.persistence != "DURABLE_RECORDED_LOCAL"
            or self.consent_authority is not ConsentAuthority.UNRESOLVED_OD_012
            or type(self.measurement_observed) is not bool
            or self.measurement_observed
            or self.decision is not CollectorDecision.NOT_READY
            or self.formal_tst_012 is not CollectorExecution.NOT_EXECUTED
            or self.formal_tst_030 is not CollectorExecution.NOT_EXECUTED
            or self.formal_tst_031 is not CollectorExecution.NOT_EXECUTED
        ):
            fail_durable_event_store()

    def __repr__(self) -> str:
        return f"DurableEventCollectionResultV2({_REDACTED})"


__all__ = [
    "DurableEventCollectionResultV2",
    "DurableEventReceiptV2",
    "DurableEventStoreFailure",
    "DurableEventStoreFailureCode",
    "fail_durable_event_store",
]
