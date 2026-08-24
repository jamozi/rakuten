"""ST-0404 guarded durable recorded-local event collector for ST-1201 V2."""

from __future__ import annotations

from typing import final

from raos.application.analytics.event_collector import FirstPartyEventCollector
from raos.domain.analytics.event_collector import (
    CollectorDecision,
    CollectorExecution,
    ConsentAuthority,
    ConsentContext,
    EventCollectionPolicy,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventDigest,
    EventEnvelope,
    RecordedStoreOutcome,
    TrackingActivation,
    ValidatedEvent,
    fail_event_collector,
)
from raos.domain.analytics.event_collector_runtime_v2 import (
    DurableEventCollectionResultV2,
    DurableEventReceiptV2,
)
from raos.domain.http.security import HttpRequestMetadata, HttpSecurityPolicy
from raos.ports.event_collector_runtime_v2 import DurableEventStoreV2


def _copy_receipt(value: object) -> DurableEventReceiptV2:
    try:
        if type(value) is not DurableEventReceiptV2:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        receipt = value
        return DurableEventReceiptV2(
            event_id=receipt.event_id,
            digest=EventDigest(receipt.digest.value),
            disposition=receipt.disposition,
            sequence=receipt.sequence,
            previous_record_sha256=receipt.previous_record_sha256,
            record_sha256=receipt.record_sha256,
            replayed=receipt.replayed,
        )
    except Exception:
        fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


@final
class _DurableExchangeCapture:
    __slots__ = ("receipt", "store")

    def __init__(self, store: DurableEventStoreV2) -> None:
        self.store = store
        self.receipt: DurableEventReceiptV2 | None = None

    def exchange(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> RecordedStoreOutcome:
        try:
            observed = self.store.exchange_durable(event, digest)
        except EventCollectorFailure as error:
            if (
                type(error) is EventCollectorFailure
                and error.code is EventCollectorFailureCode.EVENT_ID_CONFLICT
            ):
                raise
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        except Exception:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        receipt = _copy_receipt(observed)
        if receipt.event_id != event.envelope.event_id or receipt.digest != digest:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        self.receipt = receipt
        return RecordedStoreOutcome(
            event_id=receipt.event_id,
            digest=receipt.digest,
            disposition=receipt.disposition,
        )


@final
class DurableRecordedFirstPartyEventCollectorV2:
    """Persist one explicitly consented synthetic public event, never track it."""

    __slots__ = ("_collection_policy", "_http_policy", "_store")

    def __init__(
        self,
        *,
        http_policy: HttpSecurityPolicy,
        collection_policy: EventCollectionPolicy,
        store: object,
    ) -> None:
        if (
            type(http_policy) is not HttpSecurityPolicy
            or type(collection_policy) is not EventCollectionPolicy
            or not isinstance(store, DurableEventStoreV2)
        ):
            fail_event_collector()
        try:
            mode = store.mode
            action_count = store.action_count
        except Exception:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        if (
            mode != "DURABLE_RECORDED_LOCAL"
            or type(action_count) is not int
            or action_count
        ):
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        self._http_policy = http_policy
        self._collection_policy = EventCollectionPolicy(
            mode=collection_policy.mode,
            event_allowlist=collection_policy.event_allowlist,
        )
        self._store = store

    @property
    def action_count(self) -> int:
        return 0

    def collect(
        self,
        *,
        request: HttpRequestMetadata,
        envelope: EventEnvelope,
        consent: ConsentContext,
    ) -> DurableEventCollectionResultV2:
        capture = _DurableExchangeCapture(self._store)
        collector = FirstPartyEventCollector(
            http_policy=self._http_policy,
            collection_policy=self._collection_policy,
            exchange=capture,
        )
        result = collector.collect(
            request=request,
            envelope=envelope,
            consent=consent,
        )
        receipt = capture.receipt
        if (
            type(receipt) is not DurableEventReceiptV2
            or receipt.event_id != result.event_id
            or receipt.digest != result.digest
            or receipt.disposition is not result.disposition
        ):
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        return DurableEventCollectionResultV2(
            receipt=receipt,
            execution=CollectorExecution.RECORDED_TEST_ONLY,
            tracking_activation=TrackingActivation.DISABLED,
            persistence="DURABLE_RECORDED_LOCAL",
            consent_authority=ConsentAuthority.UNRESOLVED_OD_012,
            measurement_observed=False,
            decision=CollectorDecision.NOT_READY,
            formal_tst_012=CollectorExecution.NOT_EXECUTED,
            formal_tst_030=CollectorExecution.NOT_EXECUTED,
            formal_tst_031=CollectorExecution.NOT_EXECUTED,
        )


__all__ = ["DurableRecordedFirstPartyEventCollectorV2"]
