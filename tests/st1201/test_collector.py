"""Focused catalog and recorded-collector behavior for ST-1201."""

from __future__ import annotations

import pytest

from raos.domain.analytics.event_collector import (
    EVENT_CATALOG,
    MVP_PUBLIC_EVENT_NAMES,
    PUBLIC_EVENT_NAMES,
    CollectorDecision,
    CollectorExecution,
    ConsentAuthority,
    ConsentState,
    EventCollectionPolicy,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventCollectorMode,
    EventDigest,
    EventName,
    EventSource,
    PrivacyMode,
    PROHIBITED_PARAMETERS,
    RecordedStoreDisposition,
    TrackingActivation,
)

from .support import (
    collector,
    consent,
    envelope,
    http_request,
    recorded_exchange,
    validated_event,
)


def test_exact_catalog_and_public_counts() -> None:
    assert len(EVENT_CATALOG) == 20
    assert len(PUBLIC_EVENT_NAMES) == 12
    assert len(MVP_PUBLIC_EVENT_NAMES) == 11
    assert tuple(item.catalog_id for item in EVENT_CATALOG) == tuple(
        f"EVT-{number:03d}" for number in range(1, 21)
    )


def test_exact_event_names_sources_and_mvp_projection() -> None:
    assert tuple(
        (item.event_name.value, item.source.value, item.mvp) for item in EVENT_CATALOG
    ) == (
        ("article_view", "public_web", True),
        ("qualified_decision_engagement", "public_web", True),
        ("affiliate_cta_impression", "public_web", True),
        ("affiliate_click", "public_web", True),
        ("product_card_view", "public_web", True),
        ("comparison_interaction", "public_web", True),
        ("internal_link_click", "public_web", True),
        ("disclosure_view", "public_web", True),
        ("content_feedback", "public_web", False),
        ("degraded_content_view", "public_web", True),
        ("affiliate_link_error", "public_web", True),
        ("web_vital", "public_web", True),
        ("search_console_fact_imported", "worker", True),
        ("ga4_fact_imported", "worker", True),
        ("revenue_file_uploaded", "admin", True),
        ("revenue_import_dry_run_completed", "worker", True),
        ("revenue_import_committed", "admin", True),
        ("attribution_run_completed", "worker", True),
        ("publication_state_changed", "backend", True),
        ("quality_gate_evaluated", "backend", True),
    )
    assert all(
        item.prohibited_parameters == PROHIBITED_PARAMETERS for item in EVENT_CATALOG
    )


def test_closed_source_consent_privacy_and_mode_vocabularies() -> None:
    assert tuple(value.value for value in EventSource) == (
        "public_web",
        "worker",
        "admin",
        "backend",
    )
    assert tuple(value.value for value in ConsentState) == (
        "GRANTED",
        "DENIED",
        "NOT_REQUIRED",
        "UNKNOWN",
    )
    assert tuple(value.value for value in PrivacyMode) == (
        "FULL_CONSENT",
        "COOKILESS",
        "ESSENTIAL_ONLY",
    )
    assert tuple(value.value for value in EventCollectorMode) == (
        "DISABLED_OD_012",
        "RECORDED_TEST_ONLY",
    )


def test_digest_is_exact_and_deterministic() -> None:
    first = EventDigest.of(validated_event())
    second = EventDigest.of(validated_event())
    assert first == second
    assert len(first.value) == 64
    assert first.value == first.value.lower()


def test_recorded_event_is_accepted_without_tracking_or_persistence() -> None:
    result = collector().collect(
        request=http_request(), envelope=envelope(), consent=consent()
    )

    assert result.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert result.execution is CollectorExecution.RECORDED_TEST_ONLY
    assert result.tracking_activation is TrackingActivation.DISABLED
    assert result.persistence is CollectorExecution.NOT_EXECUTED
    assert result.consent_authority is ConsentAuthority.UNRESOLVED_OD_012
    assert result.measurement_observed is False
    assert result.decision is CollectorDecision.NOT_READY
    assert result.formal_tst_012 is CollectorExecution.NOT_EXECUTED
    assert result.formal_tst_030 is CollectorExecution.NOT_EXECUTED
    assert result.formal_tst_031 is CollectorExecution.NOT_EXECUTED


def test_content_feedback_is_the_only_disabled_public_event() -> None:
    assert set(PUBLIC_EVENT_NAMES) - set(MVP_PUBLIC_EVENT_NAMES) == {
        EventName.CONTENT_FEEDBACK
    }


def test_disabled_policy_stops_before_consuming_recorded_exchange() -> None:
    exchange = recorded_exchange()
    disabled = collector(exchange=exchange, policy=EventCollectionPolicy.disabled())
    with pytest.raises(EventCollectorFailure) as caught:
        disabled.collect(request=http_request(), envelope=envelope(), consent=consent())
    assert caught.value.code is EventCollectorFailureCode.COLLECTION_DISABLED

    observed = collector(exchange=exchange).collect(
        request=http_request(), envelope=envelope(), consent=consent()
    )
    assert observed.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED


def test_exact_replay_is_only_a_recorded_duplicate() -> None:
    exchange = recorded_exchange(duplicate=True)
    service = collector(exchange=exchange)
    first = service.collect(
        request=http_request(), envelope=envelope(), consent=consent()
    )
    second = service.collect(
        request=http_request(), envelope=envelope(), consent=consent()
    )
    assert first.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert second.disposition is RecordedStoreDisposition.RECORDED_DUPLICATE
