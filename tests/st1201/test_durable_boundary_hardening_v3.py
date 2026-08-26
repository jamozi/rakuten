"""ST-1201 hostile durable-store application-boundary evidence."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from .support import consent, envelope, http_policy, http_request, recorded_policy
from raos.application.analytics.event_collector_runtime_v2 import (
    DurableRecordedFirstPartyEventCollectorV2,
)
from raos.domain.analytics.event_collector import (
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventDigest,
    EventEnvelope,
    RecordedStoreDisposition,
    ValidatedEvent,
    fail_event_collector,
)
from raos.domain.analytics.event_collector_runtime_v2 import DurableEventReceiptV2


_MUTATED_EVENT_ID = UUID("018f3e90-7b00-7000-8000-000000129991")


def _receipt(event: ValidatedEvent, digest: EventDigest) -> DurableEventReceiptV2:
    return DurableEventReceiptV2(
        event_id=event.envelope.event_id,
        digest=EventDigest(digest.value),
        disposition=RecordedStoreDisposition.RECORDED_ACCEPTED,
        sequence=1,
        previous_record_sha256="0" * 64,
        record_sha256="1" * 64,
        replayed=False,
    )


class _ValidStore:
    def __init__(self) -> None:
        self.current_action_count: object = 0

    @property
    def mode(self) -> str:
        return "DURABLE_RECORDED_LOCAL"

    @property
    def action_count(self) -> object:
        return self.current_action_count

    def exchange_durable(
        self,
        event: ValidatedEvent,
        digest: EventDigest,
    ) -> DurableEventReceiptV2:
        return _receipt(event, digest)


def _service(store: object) -> DurableRecordedFirstPartyEventCollectorV2:
    return DurableRecordedFirstPartyEventCollectorV2(
        http_policy=http_policy(),
        collection_policy=recorded_policy(),
        store=store,
    )


@pytest.mark.parametrize("action_count", [False, True, 1, -1])
def test_constructor_requires_exact_integer_zero_action_count(
    action_count: object,
) -> None:
    store = _ValidStore()
    store.current_action_count = action_count

    with pytest.raises(EventCollectorFailure) as caught:
        _service(store)

    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH


def test_mode_getter_action_count_mutation_is_rejected() -> None:
    class GetterMutationStore(_ValidStore):
        @property
        def mode(self) -> str:
            self.current_action_count = 1
            return "DURABLE_RECORDED_LOCAL"

    with pytest.raises(EventCollectorFailure) as caught:
        _service(GetterMutationStore())

    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH


@pytest.mark.parametrize("raised", ["success", "domain", "unexpected"])
def test_mutated_reconstructed_event_is_rejected_after_every_outcome(
    raised: str,
) -> None:
    class MutatingStore(_ValidStore):
        def exchange_durable(
            self,
            event: ValidatedEvent,
            digest: EventDigest,
        ) -> DurableEventReceiptV2:
            receipt = _receipt(event, digest)
            object.__setattr__(event.envelope, "event_id", _MUTATED_EVENT_ID)
            if raised == "domain":
                fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
            if raised == "unexpected":
                raise RuntimeError("untrusted collaborator text")
            return receipt

    original_envelope = envelope()
    before = ValidatedEvent(
        envelope=original_envelope,
        consent=consent(),
    ).canonical_bytes()

    with pytest.raises(EventCollectorFailure) as caught:
        _service(MutatingStore()).collect(
            request=http_request(),
            envelope=original_envelope,
            consent=consent(),
        )

    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH
    assert (
        ValidatedEvent(envelope=original_envelope, consent=consent()).canonical_bytes()
        == before
    )


@pytest.mark.parametrize("raised", ["success", "domain", "unexpected"])
def test_mutated_reconstructed_digest_is_rejected_after_every_outcome(
    raised: str,
) -> None:
    class MutatingDigestStore(_ValidStore):
        def exchange_durable(
            self,
            event: ValidatedEvent,
            digest: EventDigest,
        ) -> DurableEventReceiptV2:
            receipt = _receipt(event, digest)
            object.__setattr__(digest, "value", "f" * 64)
            if raised == "domain":
                fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
            if raised == "unexpected":
                raise RuntimeError("untrusted collaborator text")
            return receipt

    with pytest.raises(EventCollectorFailure) as caught:
        _service(MutatingDigestStore()).collect(
            request=http_request(),
            envelope=envelope(),
            consent=consent(),
        )

    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH


@pytest.mark.parametrize("raised", ["success", "domain", "unexpected"])
def test_post_call_action_count_drift_is_always_rejected(raised: str) -> None:
    class ActionDriftStore(_ValidStore):
        def exchange_durable(
            self,
            event: ValidatedEvent,
            digest: EventDigest,
        ) -> DurableEventReceiptV2:
            receipt = _receipt(event, digest)
            self.current_action_count = 1
            if raised == "domain":
                fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
            if raised == "unexpected":
                raise RuntimeError("untrusted collaborator text")
            return receipt

    with pytest.raises(EventCollectorFailure) as caught:
        _service(ActionDriftStore()).collect(
            request=http_request(),
            envelope=envelope(),
            consent=consent(),
        )

    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH


def test_success_receives_a_reconstructed_input_and_preserves_original() -> None:
    class IdentityStore(_ValidStore):
        def __init__(self, original: EventEnvelope) -> None:
            super().__init__()
            self.original = original
            self.observed_event: ValidatedEvent | None = None

        def exchange_durable(
            self,
            event: ValidatedEvent,
            digest: EventDigest,
        ) -> DurableEventReceiptV2:
            assert event.envelope is not self.original
            assert event.envelope == self.original
            self.observed_event = event
            return _receipt(event, digest)

    original = envelope()
    store = IdentityStore(original)
    result = _service(store).collect(
        request=http_request(),
        envelope=original,
        consent=consent(),
    )

    assert result.receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert store.observed_event is not None
    assert store.current_action_count == 0


def test_boundary_module_has_no_network_or_external_authority_surface() -> None:
    application_source = Path(
        "python/raos/application/analytics/event_collector_runtime_v2.py"
    ).read_text(encoding="utf-8")
    port_source = Path("python/raos/ports/event_collector_runtime_v2.py").read_text(
        encoding="utf-8"
    )
    prohibited = (
        "requests",
        "urllib",
        "httpx",
        "socket",
        "credential",
        "publication",
        "revenue",
        "export",
    )
    lowered = (application_source + port_source).lower()
    assert all(token not in lowered for token in prohibited)
