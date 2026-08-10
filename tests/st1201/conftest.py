"""Synthetic builders for the isolated ST-1201 recorded seam."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_event_store import (  # noqa: E402
    RecordedEventCollectionExchange,
    RecordedEventStep,
)
from raos.application.analytics.event_collector import (  # noqa: E402
    FirstPartyEventCollector,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.analytics.event_collector import (  # noqa: E402
    ConsentContext,
    ConsentState,
    EventCollectionPolicy,
    EventCollectorMode,
    EventDigest,
    EventEnvelope,
    EventName,
    EventParameter,
    EventSource,
    PrivacyMode,
    RecordedStoreDisposition,
    RecordedStoreOutcome,
    ValidatedEvent,
)
from raos.domain.http.security import (  # noqa: E402
    HttpCredentialMode,
    HttpMethod,
    HttpRequestMetadata,
    HttpSecurityPolicy,
)
from raos.domain.portfolio.workflow import UtcTimestamp  # noqa: E402


EVENT_ID = UUID("018f3e90-7b00-7000-8000-000000001201")
SITE_ID = UUID("018f3e90-7b00-7000-8000-000000001202")
CORRELATION_ID = UUID("018f3e90-7b00-7000-8000-000000001203")
ARTICLE_ID = UUID("018f3e90-7b00-7000-8000-000000001204")
SNAPSHOT_ID = UUID("018f3e90-7b00-7000-8000-000000001205")
CTA_ID = UUID("018f3e90-7b00-7000-8000-000000001206")
OFFER_ID = UUID("018f3e90-7b00-7000-8000-000000001207")
OCCURRED_AT = UtcTimestamp(datetime(2026, 8, 10, 5, 0, tzinfo=timezone.utc))
RECEIVED_AT = UtcTimestamp(datetime(2026, 8, 10, 5, 0, 1, tzinfo=timezone.utc))


def http_policy() -> HttpSecurityPolicy:
    return HttpSecurityPolicy(
        max_content_length=4096,
        allowed_origins=frozenset(),
        allowed_methods=frozenset({HttpMethod.POST}),
        allowed_content_types=frozenset({"application/json"}),
        allowed_request_headers=frozenset({"content-type"}),
        hsts_max_age_seconds=None,
        allow_credentials=False,
    )


def http_request(
    *,
    method: HttpMethod = HttpMethod.POST,
    credential_mode: HttpCredentialMode = HttpCredentialMode.ANONYMOUS,
    content_type: str | None = "application/json",
) -> HttpRequestMetadata:
    return HttpRequestMetadata(
        method=method,
        origin=None,
        credential_mode=credential_mode,
        content_type=content_type,
        content_length=256,
        request_header_names=("content-type",),
        presented_csrf_proof=None,
        expected_csrf_proof=None,
        correlation_id="synthetic-st1201",
    )


def consent(
    *,
    state: ConsentState = ConsentState.GRANTED,
    privacy: PrivacyMode = PrivacyMode.FULL_CONSENT,
) -> ConsentContext:
    return ConsentContext(consent_state=state, privacy_mode=privacy)


def envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=EVENT_ID,
        event_name=EventName.AFFILIATE_CLICK,
        schema_version="1.0",
        occurred_at=OCCURRED_AT,
        received_at=RECEIVED_AT,
        source=EventSource.PUBLIC_WEB,
        site_id=SITE_ID,
        correlation_id=CORRELATION_ID,
        parameters=(
            EventParameter("article_id", ARTICLE_ID),
            EventParameter("snapshot_id", SNAPSHOT_ID),
            EventParameter("cta_id", CTA_ID),
            EventParameter("offer_id", OFFER_ID),
            EventParameter("placement", "article_top"),
            EventParameter("beacon_transport", "synthetic_beacon"),
            EventParameter("consent_state", "GRANTED"),
        ),
    )


def recorded_policy() -> EventCollectionPolicy:
    return EventCollectionPolicy(
        mode=EventCollectorMode.RECORDED_TEST_ONLY,
        event_allowlist=(EventName.AFFILIATE_CLICK,),
    )


def validated_event() -> ValidatedEvent:
    return ValidatedEvent(envelope=envelope(), consent=consent())


def recorded_exchange(
    *,
    duplicate: bool = False,
) -> RecordedEventCollectionExchange:
    event = validated_event()
    digest = EventDigest.of(event)
    accepted = RecordedEventStep(
        event_id=EVENT_ID,
        digest=digest,
        outcome=RecordedStoreOutcome(
            event_id=EVENT_ID,
            digest=digest,
            disposition=RecordedStoreDisposition.RECORDED_ACCEPTED,
        ),
    )
    scripts: tuple[RecordedEventStep, ...] = (accepted,)
    if duplicate:
        scripts = (
            accepted,
            RecordedEventStep(
                event_id=EVENT_ID,
                digest=digest,
                outcome=RecordedStoreOutcome(
                    event_id=EVENT_ID,
                    digest=digest,
                    disposition=RecordedStoreDisposition.RECORDED_DUPLICATE,
                ),
            ),
        )
    return RecordedEventCollectionExchange(
        environment=RuntimeEnvironment.ENV_DEV,
        mode=EventCollectorMode.RECORDED_TEST_ONLY,
        script_capacity=len(scripts),
        scripts=scripts,
    )


def collector(
    *,
    exchange: RecordedEventCollectionExchange | None = None,
    policy: EventCollectionPolicy | None = None,
) -> FirstPartyEventCollector:
    return FirstPartyEventCollector(
        http_policy=http_policy(),
        collection_policy=recorded_policy() if policy is None else policy,
        exchange=recorded_exchange() if exchange is None else exchange,
    )
