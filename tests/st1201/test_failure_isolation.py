"""Consent, PII, source, and script failure isolation for ST-1201."""

from __future__ import annotations

from dataclasses import replace
import pickle
from typing import cast
from uuid import UUID

import pytest

from raos.adapters.recorded_event_store import (
    RecordedEventCollectionExchange,
    RecordedEventStep,
)
from raos.application.analytics.event_collector import FirstPartyEventCollector
from raos.config.runtime import RuntimeEnvironment
from raos.domain.analytics.event_collector import (
    PROHIBITED_PARAMETERS,
    ConsentState,
    EventCollectionPolicy,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventCollectorMode,
    EventDigest,
    EventEnvelope,
    EventName,
    EventParameter,
    EventSource,
    ParameterScalar,
    PrivacyMode,
    PublicPagePath,
    RecordedStoreDisposition,
    RecordedStoreOutcome,
    ValidatedEvent,
)
from raos.domain.http.security import HttpCredentialMode, HttpMethod

from .support import (
    EVENT_ID,
    collector,
    consent,
    envelope,
    http_policy,
    http_request,
    recorded_exchange,
    recorded_policy,
)


REJECTED_CANARY = "REJECTED_VALUE_CANARY_ST1201_DO_NOT_ECHO"
OTHER_EVENT_ID = UUID("018f3e90-7b00-7000-8000-000000001299")


class _ExchangeProbe:
    def __init__(self, outcome: object) -> None:
        self.calls = 0
        self.error: Exception | None = None
        self.outcome = outcome

    def exchange(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> RecordedStoreOutcome:
        del event, digest
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(RecordedStoreOutcome, self.outcome)


def _service(
    probe: _ExchangeProbe,
    *,
    policy: EventCollectionPolicy | None = None,
) -> FirstPartyEventCollector:
    return FirstPartyEventCollector(
        http_policy=http_policy(),
        collection_policy=recorded_policy() if policy is None else policy,
        exchange=probe,
    )


def _changed_parameter(name: str, value: ParameterScalar) -> EventEnvelope:
    original = envelope()
    parameters = tuple(
        EventParameter(parameter.name, value) if parameter.name == name else parameter
        for parameter in original.parameters
    )
    return replace(original, parameters=parameters)


@pytest.mark.parametrize(
    "state",
    (ConsentState.DENIED, ConsentState.NOT_REQUIRED, ConsentState.UNKNOWN),
)
def test_non_granted_consent_makes_zero_exchange_calls(state: ConsentState) -> None:
    probe = _ExchangeProbe(object())
    with pytest.raises(EventCollectorFailure) as caught:
        _service(probe).collect(
            request=http_request(),
            envelope=envelope(),
            consent=consent(state=state),
        )
    assert caught.value.code is EventCollectorFailureCode.CONSENT_DENIED
    assert probe.calls == 0


@pytest.mark.parametrize("privacy", (PrivacyMode.COOKILESS, PrivacyMode.ESSENTIAL_ONLY))
def test_unresolved_privacy_modes_make_zero_exchange_calls(
    privacy: PrivacyMode,
) -> None:
    probe = _ExchangeProbe(object())
    with pytest.raises(EventCollectorFailure):
        _service(probe).collect(
            request=http_request(),
            envelope=envelope(),
            consent=consent(privacy=privacy),
        )
    assert probe.calls == 0


def test_event_level_consent_must_equal_separate_context() -> None:
    probe = _ExchangeProbe(object())
    changed = _changed_parameter("consent_state", "DENIED")
    with pytest.raises(EventCollectorFailure) as caught:
        _service(probe).collect(
            request=http_request(), envelope=changed, consent=consent()
        )
    assert caught.value.code is EventCollectorFailureCode.CONSENT_DENIED
    assert probe.calls == 0


@pytest.mark.parametrize("name", PROHIBITED_PARAMETERS)
def test_each_exact_prohibited_parameter_is_rejected(name: str) -> None:
    with pytest.raises(EventCollectorFailure) as caught:
        EventParameter(name, REJECTED_CANARY)
    assert caught.value.code is EventCollectorFailureCode.PII_FORBIDDEN


@pytest.mark.parametrize(
    "value",
    (
        "person@example.invalid",
        "+81 90 1234 5678",
        "192.0.2.1",
        "Mozilla/5.0 synthetic",
        "https://example.invalid/path?" + "token" + "=not-a-real-secret",
        "safe?secret=credential",
        "token" + "=placeholder",
    ),
)
def test_sensitive_value_shapes_are_rejected_without_echo(value: str) -> None:
    with pytest.raises(EventCollectorFailure) as caught:
        EventParameter("placement", value)
    assert value not in f"{caught.value!s} {caught.value!r}"


@pytest.mark.parametrize(
    "value",
    ({"nested": "value"}, ["nested"], b"raw-bytes", None),
)
def test_nested_raw_or_null_parameter_values_are_rejected(value: object) -> None:
    with pytest.raises(EventCollectorFailure):
        EventParameter("placement", cast(ParameterScalar, value))


def test_bool_cannot_bypass_nonnegative_number_validation() -> None:
    with pytest.raises(EventCollectorFailure):
        EventParameter("row_count", True)
    with pytest.raises(EventCollectorFailure):
        EventParameter("row_count", -1)
    assert EventParameter("pass", True).value is True


@pytest.mark.parametrize(
    "parameters",
    (
        envelope().parameters[:-1],
        (*envelope().parameters, EventParameter("extra", "value")),
        tuple(reversed(envelope().parameters)),
    ),
)
def test_missing_extra_or_reordered_parameters_are_rejected(
    parameters: tuple[EventParameter, ...],
) -> None:
    with pytest.raises(EventCollectorFailure) as caught:
        replace(envelope(), parameters=parameters)
    assert caught.value.code is EventCollectorFailureCode.PARAMETER_SET_MISMATCH


def test_unknown_event_and_malformed_schema_fail_closed() -> None:
    with pytest.raises(EventCollectorFailure):
        replace(envelope(), event_name=cast(EventName, "affiliate-click"))
    with pytest.raises(EventCollectorFailure):
        replace(envelope(), schema_version="2.0")


def test_nil_or_non_uuid7_envelope_ids_are_rejected() -> None:
    with pytest.raises(EventCollectorFailure):
        replace(envelope(), event_id=UUID(int=0))
    with pytest.raises(EventCollectorFailure):
        replace(envelope(), site_id=UUID(int=1))


@pytest.mark.parametrize(
    "value",
    (
        "/",
        "/articles/test-only",
    ),
)
def test_path_only_page_path_value_is_inert_and_strict(value: str) -> None:
    assert PublicPagePath(value).value == value


@pytest.mark.parametrize(
    "value",
    (
        "https://example.invalid/path",
        "//example.invalid/path",
        "/path?query=value",
        "/path#fragment",
        "/path\\escape",
    ),
)
def test_page_path_rejects_origin_query_fragment_or_escape(value: str) -> None:
    with pytest.raises(EventCollectorFailure):
        PublicPagePath(value)


@pytest.mark.parametrize(
    ("method", "credential"),
    (
        (HttpMethod.GET, HttpCredentialMode.ANONYMOUS),
        (HttpMethod.POST, HttpCredentialMode.BEARER),
        (HttpMethod.POST, HttpCredentialMode.COOKIE),
    ),
)
def test_http_guard_runs_before_disabled_mode(
    method: HttpMethod,
    credential: HttpCredentialMode,
) -> None:
    probe = _ExchangeProbe(object())
    service = _service(probe, policy=EventCollectionPolicy.disabled())
    with pytest.raises(EventCollectorFailure) as caught:
        service.collect(
            request=http_request(method=method, credential_mode=credential),
            envelope=envelope(),
            consent=consent(),
        )
    assert caught.value.code is EventCollectorFailureCode.HTTP_GUARD_DENIED
    assert probe.calls == 0


def test_changed_payload_for_same_event_id_is_a_conflict() -> None:
    service = collector(exchange=recorded_exchange())
    changed = _changed_parameter("placement", "comparison_table")
    with pytest.raises(EventCollectorFailure) as caught:
        service.collect(request=http_request(), envelope=changed, consent=consent())
    assert caught.value.code is EventCollectorFailureCode.EVENT_ID_CONFLICT


def test_non_public_source_is_rejected_before_exchange() -> None:
    original = envelope()
    worker = EventEnvelope(
        event_id=original.event_id,
        event_name=EventName.SEARCH_CONSOLE_FACT_IMPORTED,
        schema_version="1.0",
        occurred_at=original.occurred_at,
        received_at=original.received_at,
        source=EventSource.WORKER,
        site_id=original.site_id,
        correlation_id=original.correlation_id,
        parameters=(
            EventParameter("import_batch_id", OTHER_EVENT_ID),
            EventParameter("date", "2026-08-10"),
            EventParameter("dimension_set", "synthetic_dimensions"),
            EventParameter("row_count", 1),
        ),
    )
    probe = _ExchangeProbe(object())
    with pytest.raises(EventCollectorFailure) as caught:
        _service(probe).collect(
            request=http_request(), envelope=worker, consent=consent()
        )
    assert caught.value.code is EventCollectorFailureCode.SOURCE_DENIED
    assert probe.calls == 0


def test_reordered_script_is_rejected_without_consuming_expected_first_step() -> None:
    first_event = ValidatedEvent(envelope=envelope(), consent=consent())
    second_envelope = replace(envelope(), event_id=OTHER_EVENT_ID)
    second_event = ValidatedEvent(envelope=second_envelope, consent=consent())
    first_digest = EventDigest.of(first_event)
    second_digest = EventDigest.of(second_event)
    adapter = RecordedEventCollectionExchange(
        environment=RuntimeEnvironment.CI,
        mode=EventCollectorMode.RECORDED_TEST_ONLY,
        script_capacity=2,
        scripts=(
            RecordedEventStep(
                EVENT_ID,
                first_digest,
                RecordedStoreOutcome(
                    EVENT_ID,
                    first_digest,
                    RecordedStoreDisposition.RECORDED_ACCEPTED,
                ),
            ),
            RecordedEventStep(
                OTHER_EVENT_ID,
                second_digest,
                RecordedStoreOutcome(
                    OTHER_EVENT_ID,
                    second_digest,
                    RecordedStoreDisposition.RECORDED_ACCEPTED,
                ),
            ),
        ),
    )
    with pytest.raises(EventCollectorFailure):
        adapter.exchange(second_event, second_digest)
    assert adapter.exchange(first_event, first_digest).event_id == EVENT_ID


def test_script_exhaustion_and_extra_call_fail_closed() -> None:
    service = collector(exchange=recorded_exchange())
    service.collect(request=http_request(), envelope=envelope(), consent=consent())
    with pytest.raises(EventCollectorFailure) as caught:
        service.collect(request=http_request(), envelope=envelope(), consent=consent())
    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED


def test_exchange_exception_is_sanitized_without_retry_or_context() -> None:
    probe = _ExchangeProbe(object())
    probe.error = RuntimeError(REJECTED_CANARY)
    with pytest.raises(EventCollectorFailure) as caught:
        _service(probe).collect(
            request=http_request(), envelope=envelope(), consent=consent()
        )
    assert probe.calls == 1
    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
    assert REJECTED_CANARY not in f"{caught.value!s} {caught.value!r}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_malformed_recorded_outcome_is_rejected() -> None:
    probe = _ExchangeProbe(object())
    with pytest.raises(EventCollectorFailure) as caught:
        _service(probe).collect(
            request=http_request(), envelope=envelope(), consent=consent()
        )
    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_MISMATCH
    assert probe.calls == 1


def test_recorded_values_are_redacted_and_not_pickleable() -> None:
    for value in (envelope(), consent(), recorded_exchange()):
        assert REJECTED_CANARY not in f"{value!s} {value!r}"
        with pytest.raises(TypeError):
            pickle.dumps(value)


def test_nonlocal_recorded_adapter_environment_is_rejected() -> None:
    event = ValidatedEvent(envelope=envelope(), consent=consent())
    digest = EventDigest.of(event)
    step = RecordedEventStep(
        event_id=EVENT_ID,
        digest=digest,
        outcome=RecordedStoreOutcome(
            event_id=EVENT_ID,
            digest=digest,
            disposition=RecordedStoreDisposition.RECORDED_ACCEPTED,
        ),
    )
    with pytest.raises(EventCollectorFailure):
        RecordedEventCollectionExchange(
            environment=RuntimeEnvironment.PRODUCTION,
            mode=EventCollectorMode.RECORDED_TEST_ONLY,
            script_capacity=1,
            scripts=(step,),
        )
