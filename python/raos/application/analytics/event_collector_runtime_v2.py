"""ST-0404 guarded durable recorded-local event collector for ST-1201 V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, final
from uuid import UUID

from raos.application.analytics.event_collector import FirstPartyEventCollector
from raos.domain.analytics.event_collector import (
    CollectorDecision,
    CollectorExecution,
    ConsentAuthority,
    ConsentContext,
    ConsentState,
    EventCollectionPolicy,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventDigest,
    EventEnvelope,
    EventName,
    EventParameter,
    EventSource,
    PrivacyMode,
    RecordedStoreOutcome,
    RecordedStoreDisposition,
    TrackingActivation,
    ValidatedEvent,
    fail_event_collector,
)
from raos.domain.analytics.event_collector_runtime_v2 import (
    DurableEventCollectionResultV2,
    DurableEventReceiptV2,
)
from raos.domain.http.security import HttpRequestMetadata, HttpSecurityPolicy
from raos.domain.portfolio.workflow import UtcTimestamp
from raos.ports.event_collector_runtime_v2 import DurableEventStoreV2


@dataclass(frozen=True, slots=True)
class _ExchangeInputSnapshot:
    canonical_event: bytes
    event_id: UUID
    digest: str


def _failure(code: EventCollectorFailureCode) -> NoReturn:
    fail_event_collector(code)


def _copy_parameter(value: object) -> EventParameter:
    if type(value) is not EventParameter:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    parameter = value
    raw = parameter.value
    copied_value: str | int | float | bool | UUID
    if type(raw) is UUID:
        copied_value = UUID(str(raw))
    elif type(raw) in {str, int, float, bool}:
        copied_value = raw
    else:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    try:
        return EventParameter(name=parameter.name, value=copied_value)
    except Exception:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


def _copy_validated_event(value: object) -> ValidatedEvent:
    if type(value) is not ValidatedEvent:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    try:
        envelope = value.envelope
        consent = value.consent
        if type(envelope) is not EventEnvelope or type(consent) is not ConsentContext:
            _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        copied = ValidatedEvent(
            envelope=EventEnvelope(
                event_id=UUID(str(envelope.event_id)),
                event_name=EventName(envelope.event_name.value),
                schema_version=envelope.schema_version,
                occurred_at=UtcTimestamp(envelope.occurred_at.value),
                received_at=UtcTimestamp(envelope.received_at.value),
                source=EventSource(envelope.source.value),
                site_id=UUID(str(envelope.site_id)),
                correlation_id=UUID(str(envelope.correlation_id)),
                parameters=tuple(_copy_parameter(item) for item in envelope.parameters),
            ),
            consent=ConsentContext(
                consent_state=ConsentState(consent.consent_state.value),
                privacy_mode=PrivacyMode(consent.privacy_mode.value),
            ),
        )
        if copied.canonical_bytes() != value.canonical_bytes():
            _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        return copied
    except EventCollectorFailure:
        raise
    except Exception:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


def _input_snapshot(event: object, digest: object) -> _ExchangeInputSnapshot:
    if type(event) is not ValidatedEvent or type(digest) is not EventDigest:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    try:
        canonical = bytes(event.canonical_bytes())
        event_id = UUID(str(event.envelope.event_id))
        digest_text = str(digest.value)
        if EventDigest(digest_text) != digest or EventDigest.of(event) != digest:
            _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        return _ExchangeInputSnapshot(
            canonical_event=canonical,
            event_id=event_id,
            digest=digest_text,
        )
    except EventCollectorFailure:
        raise
    except Exception:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


def _verify_input_snapshot(
    event: object,
    digest: object,
    expected: _ExchangeInputSnapshot,
) -> None:
    try:
        observed = _input_snapshot(event, digest)
    except Exception:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    if observed != expected:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


def _verify_store_boundary(store: DurableEventStoreV2) -> None:
    try:
        before = store.action_count
        mode = store.mode
        after = store.action_count
    except Exception:
        _failure(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
    if (
        type(before) is not int
        or before != 0
        or type(mode) is not str
        or mode != "DURABLE_RECORDED_LOCAL"
        or type(after) is not int
        or after != 0
    ):
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


def _post_exchange_verification(
    *,
    store: DurableEventStoreV2,
    original_event: ValidatedEvent,
    original_digest: EventDigest,
    original_snapshot: _ExchangeInputSnapshot,
    copied_event: ValidatedEvent,
    copied_digest: EventDigest,
    copied_snapshot: _ExchangeInputSnapshot,
) -> None:
    input_mismatch = False
    for candidate_event, candidate_digest, expected in (
        (original_event, original_digest, original_snapshot),
        (copied_event, copied_digest, copied_snapshot),
    ):
        try:
            _verify_input_snapshot(candidate_event, candidate_digest, expected)
        except Exception:
            input_mismatch = True
    store_failure: EventCollectorFailureCode | None = None
    try:
        _verify_store_boundary(store)
    except EventCollectorFailure as error:
        if type(error) is EventCollectorFailure:
            try:
                code = error.code
            except Exception:
                code = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
            store_failure = (
                code
                if type(code) is EventCollectorFailureCode
                else EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
            )
        else:
            store_failure = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
    except Exception:
        store_failure = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
    if input_mismatch:
        _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
    if store_failure is not None:
        _failure(store_failure)


def _copy_receipt(value: object) -> DurableEventReceiptV2:
    try:
        if type(value) is not DurableEventReceiptV2:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        receipt = value
        return DurableEventReceiptV2(
            event_id=UUID(str(receipt.event_id)),
            digest=EventDigest(receipt.digest.value),
            disposition=RecordedStoreDisposition(receipt.disposition.value),
            sequence=receipt.sequence,
            previous_record_sha256=receipt.previous_record_sha256,
            record_sha256=receipt.record_sha256,
            replayed=receipt.replayed,
        )
    except Exception:
        fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)


@final
class _DurableExchangeCapture:
    __slots__ = ("failure_code", "receipt", "store")

    def __init__(self, store: DurableEventStoreV2) -> None:
        self.store = store
        self.receipt: DurableEventReceiptV2 | None = None
        self.failure_code: EventCollectorFailureCode | None = None

    def exchange(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> RecordedStoreOutcome:
        try:
            return self._exchange_checked(event, digest)
        except EventCollectorFailure as error:
            if type(error) is EventCollectorFailure:
                try:
                    code = error.code
                except Exception:
                    code = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
                if type(code) is EventCollectorFailureCode:
                    self.failure_code = code
                else:
                    self.failure_code = (
                        EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
                    )
            else:
                self.failure_code = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
            raise
        except Exception:
            self.failure_code = EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
            fail_event_collector(self.failure_code)

    def _exchange_checked(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> RecordedStoreOutcome:
        original_snapshot = _input_snapshot(event, digest)
        copied_event = _copy_validated_event(event)
        copied_digest = EventDigest(digest.value)
        copied_snapshot = _input_snapshot(copied_event, copied_digest)
        if copied_snapshot != original_snapshot:
            _failure(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        _verify_store_boundary(self.store)
        observed: object | None = None
        domain_code: EventCollectorFailureCode | None = None
        unexpected = False
        try:
            observed = self.store.exchange_durable(copied_event, copied_digest)
        except EventCollectorFailure as error:
            if type(error) is EventCollectorFailure:
                try:
                    code = error.code
                except Exception:
                    unexpected = True
                else:
                    if type(code) is EventCollectorFailureCode:
                        domain_code = code
                    else:
                        unexpected = True
            else:
                unexpected = True
        except Exception:
            unexpected = True
        _post_exchange_verification(
            store=self.store,
            original_event=event,
            original_digest=digest,
            original_snapshot=original_snapshot,
            copied_event=copied_event,
            copied_digest=copied_digest,
            copied_snapshot=copied_snapshot,
        )
        if domain_code is not None:
            if domain_code is EventCollectorFailureCode.EVENT_ID_CONFLICT:
                fail_event_collector(domain_code)
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        if unexpected:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        receipt = _copy_receipt(observed)
        if (
            receipt.event_id != original_snapshot.event_id
            or receipt.digest.value != original_snapshot.digest
            or type(receipt.disposition) is not RecordedStoreDisposition
        ):
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
        _verify_store_boundary(store)
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
        try:
            result = collector.collect(
                request=request,
                envelope=envelope,
                consent=consent,
            )
        except EventCollectorFailure:
            if capture.failure_code is not None:
                fail_event_collector(capture.failure_code)
            raise
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
