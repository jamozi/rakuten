"""ST-0404-guarded application boundary for the disabled ST-1201 seam."""

from __future__ import annotations

from typing import final

from raos.application.http.security import HttpSecurityGuard
from raos.domain.analytics.event_collector import (
    CollectorDecision,
    CollectorExecution,
    ConsentAuthority,
    ConsentContext,
    ConsentState,
    EventCollectionPolicy,
    EventCollectionResult,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventCollectorMode,
    EventDigest,
    EventEnvelope,
    EventParameter,
    EventSource,
    PrivacyMode,
    RecordedStoreDisposition,
    RecordedStoreOutcome,
    TrackingActivation,
    ValidatedEvent,
    fail_event_collector,
)
from raos.domain.http.security import (
    HttpCredentialMode,
    HttpMethod,
    HttpRequestMetadata,
    HttpSecurityFailure,
    HttpSecurityPolicy,
)
from raos.domain.portfolio.workflow import UtcTimestamp
from raos.ports.event_collector import EventCollectionExchange


def _guard_request(
    guard: HttpSecurityGuard,
    request: HttpRequestMetadata,
) -> HttpRequestMetadata:
    guarded: HttpRequestMetadata | None = None
    denied = False
    try:
        guarded = guard.require(request)
    except HttpSecurityFailure:
        denied = True
    if denied or guarded is None:
        fail_event_collector(EventCollectorFailureCode.HTTP_GUARD_DENIED)
    if (
        guarded.method is not HttpMethod.POST
        or guarded.content_type != "application/json"
        or guarded.credential_mode is not HttpCredentialMode.ANONYMOUS
        or guarded.presented_csrf_proof is not None
        or guarded.expected_csrf_proof is not None
    ):
        fail_event_collector(EventCollectorFailureCode.HTTP_GUARD_DENIED)
    return guarded


def _validate_consent(event: EventEnvelope, consent: ConsentContext) -> None:
    if (
        type(consent) is not ConsentContext
        or consent.consent_state is not ConsentState.GRANTED
        or consent.privacy_mode is not PrivacyMode.FULL_CONSENT
    ):
        fail_event_collector(EventCollectorFailureCode.CONSENT_DENIED)
    event_level = tuple(
        parameter.value
        for parameter in event.parameters
        if parameter.name == "consent_state"
    )
    if event_level and event_level != (consent.consent_state.value,):
        fail_event_collector(EventCollectorFailureCode.CONSENT_DENIED)


def _validated_envelope(envelope: object) -> EventEnvelope:
    if type(envelope) is not EventEnvelope:
        fail_event_collector()
    normalized: EventEnvelope | None = None
    invalid = False
    try:
        parameters = tuple(
            EventParameter(name=parameter.name, value=parameter.value)
            for parameter in envelope.parameters
            if type(parameter) is EventParameter
        )
        if len(parameters) != len(envelope.parameters):
            fail_event_collector()
        normalized = EventEnvelope(
            event_id=envelope.event_id,
            event_name=envelope.event_name,
            schema_version=envelope.schema_version,
            occurred_at=UtcTimestamp(envelope.occurred_at.value),
            received_at=UtcTimestamp(envelope.received_at.value),
            source=envelope.source,
            site_id=envelope.site_id,
            correlation_id=envelope.correlation_id,
            parameters=parameters,
        )
    except EventCollectorFailure:
        raise
    except Exception:
        invalid = True
    if invalid or normalized is None:
        fail_event_collector()
    return normalized


@final
class FirstPartyEventCollector:
    """Guard, validate, and compare one synthetic event with one script step."""

    __slots__ = ("_exchange", "_guard", "_policy")

    def __init__(
        self,
        *,
        http_policy: HttpSecurityPolicy,
        collection_policy: EventCollectionPolicy,
        exchange: EventCollectionExchange,
    ) -> None:
        if (
            type(http_policy) is not HttpSecurityPolicy
            or type(collection_policy) is not EventCollectionPolicy
            or not callable(getattr(exchange, "exchange", None))
        ):
            fail_event_collector()
        self._guard = HttpSecurityGuard(policy=http_policy)
        self._policy = EventCollectionPolicy(
            mode=collection_policy.mode,
            event_allowlist=collection_policy.event_allowlist,
        )
        self._exchange = exchange

    def collect(
        self,
        *,
        request: HttpRequestMetadata,
        envelope: EventEnvelope,
        consent: ConsentContext,
    ) -> EventCollectionResult:
        _guard_request(self._guard, request)
        if self._policy.mode is EventCollectorMode.DISABLED_OD_012:
            fail_event_collector(EventCollectorFailureCode.COLLECTION_DISABLED)
        envelope = _validated_envelope(envelope)
        if type(consent) is not ConsentContext:
            fail_event_collector()
        consent = ConsentContext(
            consent_state=consent.consent_state,
            privacy_mode=consent.privacy_mode,
        )
        if (
            envelope.source is not EventSource.PUBLIC_WEB
            or not envelope.definition.mvp
            or envelope.event_name not in self._policy.event_allowlist
        ):
            fail_event_collector(EventCollectorFailureCode.SOURCE_DENIED)
        _validate_consent(envelope, consent)
        validated = ValidatedEvent(envelope=envelope, consent=consent)
        digest = EventDigest.of(validated)

        observed: object = None
        unavailable = False
        try:
            observed = self._exchange.exchange(validated, digest)
        except EventCollectorFailure as error:
            if error.code is EventCollectorFailureCode.EVENT_ID_CONFLICT:
                raise
            unavailable = True
        except Exception:
            unavailable = True
        if unavailable:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED)
        if (
            type(observed) is not RecordedStoreOutcome
            or observed.event_id != envelope.event_id
            or observed.digest != digest
            or observed.disposition
            not in {
                RecordedStoreDisposition.RECORDED_ACCEPTED,
                RecordedStoreDisposition.RECORDED_DUPLICATE,
            }
        ):
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        return EventCollectionResult(
            event_id=envelope.event_id,
            digest=digest,
            disposition=observed.disposition,
            execution=CollectorExecution.RECORDED_TEST_ONLY,
            tracking_activation=TrackingActivation.DISABLED,
            persistence=CollectorExecution.NOT_EXECUTED,
            consent_authority=ConsentAuthority.UNRESOLVED_OD_012,
            measurement_observed=False,
            decision=CollectorDecision.NOT_READY,
            formal_tst_012=CollectorExecution.NOT_EXECUTED,
            formal_tst_030=CollectorExecution.NOT_EXECUTED,
            formal_tst_031=CollectorExecution.NOT_EXECUTED,
        )


__all__ = ["FirstPartyEventCollector"]
