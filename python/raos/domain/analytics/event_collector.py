"""Closed first-party event contract for the disabled ST-1201 local seam.

The canonical catalog is projected as immutable values.  This module provides
no tracking activation, HTTP endpoint, persistence, consent authority, or
translation to the publication or physical analytics contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import ipaddress
import json
import math
import re
from typing import NoReturn, SupportsIndex, TypeAlias, cast
from uuid import RFC_4122, UUID

from raos.domain.portfolio.workflow import UtcTimestamp


_SAFE_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z", re.ASCII)
_SAFE_TEXT = re.compile(r"[ -~]+\Z", re.ASCII)
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+", re.ASCII)
_PHONE_SHAPE = re.compile(r"(?:\+?[0-9][0-9 ()-]{8,}[0-9])\Z", re.ASCII)
_MAX_PARAMETER_TEXT = 512
_MAX_EXACT_INTEGER = (1 << 63) - 1
_NONNEGATIVE_INTEGER_PARAMETERS = frozenset(
    {
        "blocking_count",
        "direct_count",
        "duplicate_count",
        "error_count",
        "estimated_count",
        "file_size",
        "provider_row_count",
        "row_count",
        "unattributed_count",
    }
)
_REDACTED = "<redacted-event-collector>"
_ENVELOPE_PARAMETER_NAMES = frozenset(
    {
        "event_id",
        "event_name",
        "schema_version",
        "occurred_at",
        "received_at",
        "source",
        "site_id",
        "correlation_id",
    }
)


class EventSource(str, Enum):
    PUBLIC_WEB = "public_web"
    WORKER = "worker"
    ADMIN = "admin"
    BACKEND = "backend"


class EventName(str, Enum):
    ARTICLE_VIEW = "article_view"
    QUALIFIED_DECISION_ENGAGEMENT = "qualified_decision_engagement"
    AFFILIATE_CTA_IMPRESSION = "affiliate_cta_impression"
    AFFILIATE_CLICK = "affiliate_click"
    PRODUCT_CARD_VIEW = "product_card_view"
    COMPARISON_INTERACTION = "comparison_interaction"
    INTERNAL_LINK_CLICK = "internal_link_click"
    DISCLOSURE_VIEW = "disclosure_view"
    CONTENT_FEEDBACK = "content_feedback"
    DEGRADED_CONTENT_VIEW = "degraded_content_view"
    AFFILIATE_LINK_ERROR = "affiliate_link_error"
    WEB_VITAL = "web_vital"
    SEARCH_CONSOLE_FACT_IMPORTED = "search_console_fact_imported"
    GA4_FACT_IMPORTED = "ga4_fact_imported"
    REVENUE_FILE_UPLOADED = "revenue_file_uploaded"
    REVENUE_IMPORT_DRY_RUN_COMPLETED = "revenue_import_dry_run_completed"
    REVENUE_IMPORT_COMMITTED = "revenue_import_committed"
    ATTRIBUTION_RUN_COMPLETED = "attribution_run_completed"
    PUBLICATION_STATE_CHANGED = "publication_state_changed"
    QUALITY_GATE_EVALUATED = "quality_gate_evaluated"


class ConsentState(str, Enum):
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class PrivacyMode(str, Enum):
    FULL_CONSENT = "FULL_CONSENT"
    COOKILESS = "COOKILESS"
    ESSENTIAL_ONLY = "ESSENTIAL_ONLY"


class EventCollectorMode(str, Enum):
    DISABLED_OD_012 = "DISABLED_OD_012"
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"


class RecordedStoreDisposition(str, Enum):
    RECORDED_ACCEPTED = "RECORDED_ACCEPTED"
    RECORDED_DUPLICATE = "RECORDED_DUPLICATE"


class CollectorExecution(str, Enum):
    RECORDED_TEST_ONLY = "RECORDED_TEST_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


class TrackingActivation(str, Enum):
    DISABLED = "DISABLED"


class ConsentAuthority(str, Enum):
    UNRESOLVED_OD_012 = "UNRESOLVED_OD_012"


class CollectorDecision(str, Enum):
    NOT_READY = "NOT_READY"


class EventCollectorFailureCode(str, Enum):
    MALFORMED_EVENT = "MALFORMED_EVENT"
    UNKNOWN_EVENT = "UNKNOWN_EVENT"
    SOURCE_DENIED = "SOURCE_DENIED"
    PARAMETER_SET_MISMATCH = "PARAMETER_SET_MISMATCH"
    PII_FORBIDDEN = "PII_FORBIDDEN"
    CONSENT_DENIED = "CONSENT_DENIED"
    COLLECTION_DISABLED = "COLLECTION_DISABLED"
    EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"
    RECORDED_STORE_MISMATCH = "RECORDED_STORE_MISMATCH"
    RECORDED_STORE_EXHAUSTED = "RECORDED_STORE_EXHAUSTED"
    HTTP_GUARD_DENIED = "HTTP_GUARD_DENIED"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("event collector serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class EventCollectorFailure(RuntimeError):
    code: EventCollectorFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not EventCollectorFailureCode:
            raise TypeError("invalid event collector failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"EventCollectorFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("event collector failure serialization is not supported")


def fail_event_collector(
    code: EventCollectorFailureCode = EventCollectorFailureCode.MALFORMED_EVENT,
) -> NoReturn:
    raise EventCollectorFailure(code) from None


def _require_uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_event_collector()
    return value


PROHIBITED_PARAMETERS = (
    "email",
    "phone",
    "raw_ip",
    "full_user_agent",
    "raw_search_query",
    "article_body",
    "source_packet_text",
    "affiliate_url_query_secret",
)


@dataclass(frozen=True, slots=True, repr=False)
class EventDefinition(_RedactedValue):
    catalog_id: str
    event_name: EventName
    source: EventSource
    mvp: bool
    parameters: tuple[str, ...]
    prohibited_parameters: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.catalog_id) is not str
            or re.fullmatch(r"EVT-[0-9]{3}", self.catalog_id, re.ASCII) is None
            or type(self.event_name) is not EventName
            or type(self.source) is not EventSource
            or type(self.mvp) is not bool
            or type(self.parameters) is not tuple
            or not self.parameters
            or any(
                type(name) is not str or _SAFE_NAME.fullmatch(name) is None
                for name in self.parameters
            )
            or len(set(self.parameters)) != len(self.parameters)
            or self.prohibited_parameters != PROHIBITED_PARAMETERS
        ):
            fail_event_collector()


def _event(
    number: int,
    name: EventName,
    source: EventSource,
    mvp: bool,
    parameters: tuple[str, ...],
) -> EventDefinition:
    return EventDefinition(
        catalog_id=f"EVT-{number:03d}",
        event_name=name,
        source=source,
        mvp=mvp,
        parameters=parameters,
        prohibited_parameters=PROHIBITED_PARAMETERS,
    )


EVENT_CATALOG = (
    _event(
        1,
        EventName.ARTICLE_VIEW,
        EventSource.PUBLIC_WEB,
        True,
        (
            "event_id",
            "occurred_at",
            "anonymous_session_id",
            "article_id",
            "snapshot_id",
            "category_id",
            "referrer_class",
            "consent_state",
        ),
    ),
    _event(
        2,
        EventName.QUALIFIED_DECISION_ENGAGEMENT,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "component_type", "engagement_kind"),
    ),
    _event(
        3,
        EventName.AFFILIATE_CTA_IMPRESSION,
        EventSource.PUBLIC_WEB,
        True,
        (
            "article_id",
            "snapshot_id",
            "cta_id",
            "offer_id",
            "placement",
            "visibility_threshold",
        ),
    ),
    _event(
        4,
        EventName.AFFILIATE_CLICK,
        EventSource.PUBLIC_WEB,
        True,
        (
            "article_id",
            "snapshot_id",
            "cta_id",
            "offer_id",
            "placement",
            "beacon_transport",
            "consent_state",
        ),
    ),
    _event(
        5,
        EventName.PRODUCT_CARD_VIEW,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "product_id", "offer_id", "placement"),
    ),
    _event(
        6,
        EventName.COMPARISON_INTERACTION,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "interaction", "axis_code"),
    ),
    _event(
        7,
        EventName.INTERNAL_LINK_CLICK,
        EventSource.PUBLIC_WEB,
        True,
        ("from_article_id", "to_article_id", "placement"),
    ),
    _event(
        8,
        EventName.DISCLOSURE_VIEW,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "disclosure_version"),
    ),
    _event(
        9,
        EventName.CONTENT_FEEDBACK,
        EventSource.PUBLIC_WEB,
        False,
        ("article_id", "snapshot_id", "rating", "reason_code"),
    ),
    _event(
        10,
        EventName.DEGRADED_CONTENT_VIEW,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "degradation_code"),
    ),
    _event(
        11,
        EventName.AFFILIATE_LINK_ERROR,
        EventSource.PUBLIC_WEB,
        True,
        ("article_id", "snapshot_id", "cta_id", "error_code"),
    ),
    _event(
        12,
        EventName.WEB_VITAL,
        EventSource.PUBLIC_WEB,
        True,
        (
            "article_id",
            "snapshot_id",
            "metric_name",
            "metric_value",
            "rating",
            "navigation_type",
        ),
    ),
    _event(
        13,
        EventName.SEARCH_CONSOLE_FACT_IMPORTED,
        EventSource.WORKER,
        True,
        ("import_batch_id", "site_id", "date", "dimension_set", "row_count"),
    ),
    _event(
        14,
        EventName.GA4_FACT_IMPORTED,
        EventSource.WORKER,
        True,
        ("import_batch_id", "property_id", "date_range", "metric_set", "row_count"),
    ),
    _event(
        15,
        EventName.REVENUE_FILE_UPLOADED,
        EventSource.ADMIN,
        True,
        ("import_batch_id", "file_hash", "file_size", "uploader_id"),
    ),
    _event(
        16,
        EventName.REVENUE_IMPORT_DRY_RUN_COMPLETED,
        EventSource.WORKER,
        True,
        (
            "import_batch_id",
            "row_count",
            "error_count",
            "duplicate_count",
            "amount_totals",
        ),
    ),
    _event(
        17,
        EventName.REVENUE_IMPORT_COMMITTED,
        EventSource.ADMIN,
        True,
        ("import_batch_id", "committer_id", "provider_row_count", "confirmed_total"),
    ),
    _event(
        18,
        EventName.ATTRIBUTION_RUN_COMPLETED,
        EventSource.WORKER,
        True,
        (
            "run_id",
            "method_version",
            "direct_count",
            "estimated_count",
            "unattributed_count",
        ),
    ),
    _event(
        19,
        EventName.PUBLICATION_STATE_CHANGED,
        EventSource.BACKEND,
        True,
        ("article_id", "snapshot_id", "from_state", "to_state", "actor_type"),
    ),
    _event(
        20,
        EventName.QUALITY_GATE_EVALUATED,
        EventSource.BACKEND,
        True,
        (
            "article_version_id",
            "policy_bundle_version",
            "score",
            "pass",
            "blocking_count",
        ),
    ),
)

PUBLIC_EVENT_NAMES = tuple(
    definition.event_name
    for definition in EVENT_CATALOG
    if definition.source is EventSource.PUBLIC_WEB
)
MVP_PUBLIC_EVENT_NAMES = tuple(
    definition.event_name
    for definition in EVENT_CATALOG
    if definition.source is EventSource.PUBLIC_WEB and definition.mvp
)


ParameterScalar: TypeAlias = str | int | float | bool | UUID


def _looks_sensitive(value: str) -> bool:
    lowered = value.lower()
    if (
        _EMAIL.search(value) is not None
        or (
            _PHONE_SHAPE.fullmatch(value) is not None
            and sum(character.isdigit() for character in value) >= 10
        )
        or lowered.startswith(("http://", "https://"))
        or "mozilla/" in lowered
        or "user-agent" in lowered
        or "?" in value
        or "#" in value
        or any(
            marker in lowered
            for marker in ("api_key=", "apikey=", "password=", "secret=", "token=")
        )
    ):
        return True
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True, repr=False)
class EventParameter(_RedactedValue):
    name: str
    value: ParameterScalar

    def __post_init__(self) -> None:
        if (
            type(self.name) is not str
            or _SAFE_NAME.fullmatch(self.name) is None
            or self.name in PROHIBITED_PARAMETERS
            or self.name in _ENVELOPE_PARAMETER_NAMES
        ):
            fail_event_collector(EventCollectorFailureCode.PII_FORBIDDEN)
        if type(self.value) is str:
            if (
                not self.value
                or len(self.value.encode("utf-8")) > _MAX_PARAMETER_TEXT
                or self.value != self.value.strip()
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in self.value
                )
                or _looks_sensitive(self.value)
            ):
                fail_event_collector(EventCollectorFailureCode.PII_FORBIDDEN)
        elif type(self.value) is int:
            if not -_MAX_EXACT_INTEGER <= self.value <= _MAX_EXACT_INTEGER or (
                self.name in _NONNEGATIVE_INTEGER_PARAMETERS and self.value < 0
            ):
                fail_event_collector()
        elif type(self.value) is float:
            if not math.isfinite(self.value):
                fail_event_collector()
        elif type(self.value) is bool:
            if self.name != "pass":
                fail_event_collector()
        elif type(self.value) is UUID:
            _require_uuid7(self.value)
        else:
            fail_event_collector()


@dataclass(frozen=True, slots=True, repr=False)
class PublicPagePath(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 1 <= len(self.value) <= 1024
            or not self.value.startswith("/")
            or self.value.startswith("//")
            or "?" in self.value
            or "#" in self.value
            or "\\" in self.value
            or any(
                ord(character) < 32 or ord(character) == 127 for character in self.value
            )
        ):
            fail_event_collector()


def definition_for(event_name: EventName) -> EventDefinition:
    if type(event_name) is not EventName:
        fail_event_collector(EventCollectorFailureCode.UNKNOWN_EVENT)
    for definition in EVENT_CATALOG:
        if definition.event_name is event_name:
            return definition
    fail_event_collector(EventCollectorFailureCode.UNKNOWN_EVENT)


@dataclass(frozen=True, slots=True, repr=False)
class EventEnvelope(_RedactedValue):
    event_id: UUID
    event_name: EventName
    schema_version: str
    occurred_at: UtcTimestamp
    received_at: UtcTimestamp
    source: EventSource
    site_id: UUID
    correlation_id: UUID
    parameters: tuple[EventParameter, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.event_id)
        _require_uuid7(self.site_id)
        _require_uuid7(self.correlation_id)
        if (
            type(self.event_name) is not EventName
            or type(self.schema_version) is not str
            or self.schema_version != "1.0"
            or type(self.occurred_at) is not UtcTimestamp
            or type(self.received_at) is not UtcTimestamp
            or self.received_at.value < self.occurred_at.value
            or type(self.source) is not EventSource
            or type(self.parameters) is not tuple
            or any(
                type(parameter) is not EventParameter for parameter in self.parameters
            )
        ):
            fail_event_collector()
        definition = definition_for(self.event_name)
        expected = tuple(
            name
            for name in definition.parameters
            if name not in _ENVELOPE_PARAMETER_NAMES
        )
        observed = tuple(parameter.name for parameter in self.parameters)
        if self.source is not definition.source or observed != expected:
            fail_event_collector(EventCollectorFailureCode.PARAMETER_SET_MISMATCH)

    @property
    def definition(self) -> EventDefinition:
        return definition_for(self.event_name)


@dataclass(frozen=True, slots=True, repr=False)
class EventCollectionPolicy(_RedactedValue):
    mode: EventCollectorMode
    event_allowlist: tuple[EventName, ...]

    def __post_init__(self) -> None:
        if (
            type(self.mode) is not EventCollectorMode
            or type(self.event_allowlist) is not tuple
        ):
            fail_event_collector()
        if self.mode is EventCollectorMode.DISABLED_OD_012:
            if self.event_allowlist:
                fail_event_collector()
            return
        if (
            any(type(name) is not EventName for name in self.event_allowlist)
            or len(set(self.event_allowlist)) != len(self.event_allowlist)
            or any(name not in MVP_PUBLIC_EVENT_NAMES for name in self.event_allowlist)
            or tuple(
                name for name in MVP_PUBLIC_EVENT_NAMES if name in self.event_allowlist
            )
            != self.event_allowlist
        ):
            fail_event_collector()

    @classmethod
    def disabled(cls) -> EventCollectionPolicy:
        return cls(mode=EventCollectorMode.DISABLED_OD_012, event_allowlist=())


@dataclass(frozen=True, slots=True, repr=False)
class ConsentContext(_RedactedValue):
    consent_state: ConsentState
    privacy_mode: PrivacyMode

    def __post_init__(self) -> None:
        if (
            type(self.consent_state) is not ConsentState
            or type(self.privacy_mode) is not PrivacyMode
        ):
            fail_event_collector()


def _json_value(value: ParameterScalar) -> str | int | float | bool:
    if type(value) is UUID:
        return str(value)
    return cast(str | int | float | bool, value)


@dataclass(frozen=True, slots=True, repr=False)
class ValidatedEvent(_RedactedValue):
    envelope: EventEnvelope
    consent: ConsentContext

    def __post_init__(self) -> None:
        if (
            type(self.envelope) is not EventEnvelope
            or type(self.consent) is not ConsentContext
        ):
            fail_event_collector()

    def canonical_bytes(self) -> bytes:
        payload = {
            "correlation_id": str(self.envelope.correlation_id),
            "event_id": str(self.envelope.event_id),
            "event_name": self.envelope.event_name.value,
            "occurred_at": self.envelope.occurred_at.value.isoformat().replace(
                "+00:00", "Z"
            ),
            "parameters": [
                {"name": parameter.name, "value": _json_value(parameter.value)}
                for parameter in self.envelope.parameters
            ],
            "received_at": self.envelope.received_at.value.isoformat().replace(
                "+00:00", "Z"
            ),
            "schema_version": self.envelope.schema_version,
            "site_id": str(self.envelope.site_id),
            "source": self.envelope.source.value,
        }
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return rendered.encode("utf-8")


@dataclass(frozen=True, slots=True, repr=False)
class EventDigest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _LOWER_SHA256.fullmatch(self.value) is None:
            fail_event_collector()

    @classmethod
    def of(cls, event: ValidatedEvent) -> EventDigest:
        if type(event) is not ValidatedEvent:
            fail_event_collector()
        return cls(hashlib.sha256(event.canonical_bytes()).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class RecordedStoreOutcome(_RedactedValue):
    event_id: UUID
    digest: EventDigest
    disposition: RecordedStoreDisposition

    def __post_init__(self) -> None:
        _require_uuid7(self.event_id)
        if (
            type(self.digest) is not EventDigest
            or type(self.disposition) is not RecordedStoreDisposition
        ):
            fail_event_collector()


@dataclass(frozen=True, slots=True, repr=False)
class EventCollectionResult(_RedactedValue):
    event_id: UUID
    digest: EventDigest
    disposition: RecordedStoreDisposition
    execution: CollectorExecution
    tracking_activation: TrackingActivation
    persistence: CollectorExecution
    consent_authority: ConsentAuthority
    measurement_observed: bool
    decision: CollectorDecision
    formal_tst_012: CollectorExecution
    formal_tst_030: CollectorExecution
    formal_tst_031: CollectorExecution

    def __post_init__(self) -> None:
        _require_uuid7(self.event_id)
        if (
            type(self.digest) is not EventDigest
            or type(self.disposition) is not RecordedStoreDisposition
            or self.execution is not CollectorExecution.RECORDED_TEST_ONLY
            or self.tracking_activation is not TrackingActivation.DISABLED
            or self.persistence is not CollectorExecution.NOT_EXECUTED
            or self.consent_authority is not ConsentAuthority.UNRESOLVED_OD_012
            or type(self.measurement_observed) is not bool
            or self.measurement_observed
            or self.decision is not CollectorDecision.NOT_READY
            or self.formal_tst_012 is not CollectorExecution.NOT_EXECUTED
            or self.formal_tst_030 is not CollectorExecution.NOT_EXECUTED
            or self.formal_tst_031 is not CollectorExecution.NOT_EXECUTED
        ):
            fail_event_collector()


__all__ = [
    "EVENT_CATALOG",
    "MVP_PUBLIC_EVENT_NAMES",
    "PROHIBITED_PARAMETERS",
    "PUBLIC_EVENT_NAMES",
    "CollectorDecision",
    "CollectorExecution",
    "ConsentAuthority",
    "ConsentContext",
    "ConsentState",
    "EventCollectionPolicy",
    "EventCollectionResult",
    "EventCollectorFailure",
    "EventCollectorFailureCode",
    "EventCollectorMode",
    "EventDefinition",
    "EventDigest",
    "EventEnvelope",
    "EventName",
    "EventParameter",
    "EventSource",
    "ParameterScalar",
    "PrivacyMode",
    "PublicPagePath",
    "RecordedStoreDisposition",
    "RecordedStoreOutcome",
    "TrackingActivation",
    "ValidatedEvent",
    "definition_for",
    "fail_event_collector",
]
