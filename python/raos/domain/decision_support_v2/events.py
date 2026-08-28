"""Privacy-minimal analytics event validation and deterministic QDS counting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import re
from typing import Mapping, Sequence


EVENT_ALLOWLIST = frozenset(
    {
        "tool_result_view",
        "comparison_view",
        "evidence_link_open",
        "official_source_open",
        "affiliate_outbound_activate",
        "article_complete",
        "error_state_view",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "raw_ip",
        "raw_user_agent",
        "full_referrer",
        "query_string",
        "email",
        "name",
        "address",
        "provider_order_id",
        "credential",
        "password",
    }
)
EVENT_FIELDS = frozenset(
    {
        "event_name",
        "event_version",
        "event_time_jst",
        "session_token_hmac",
        "article_id",
        "placement",
        "consent_state",
        "result_state",
        "source_id",
        "product_id",
        "schema_version",
    }
)
RESULT_STATES = frozenset({"PASS", "FAIL", "UNKNOWN", "STALE", "BLOCKED", "NO_MATCH"})
CONSENT_STATES = frozenset({"UNKNOWN", "DENIED", "GRANTED"})
EVENT_FIELD_POLICY: Mapping[str, tuple[frozenset[str], frozenset[str]]] = {
    "tool_result_view": (frozenset({"result_state"}), frozenset({"result_state"})),
    "comparison_view": (frozenset(), frozenset()),
    "evidence_link_open": (frozenset({"source_id"}), frozenset({"source_id"})),
    "official_source_open": (frozenset({"source_id"}), frozenset({"source_id"})),
    "affiliate_outbound_activate": (
        frozenset({"product_id"}),
        frozenset({"product_id"}),
    ),
    "article_complete": (frozenset(), frozenset()),
    "error_state_view": (frozenset({"result_state"}), frozenset({"result_state"})),
}
_PLACEMENT = re.compile(r"[a-z0-9_-]{1,64}\Z")
_HMAC = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9-]+\Z")
_SOURCE_ID = re.compile(r"SRC-[A-Z0-9-]+\Z")


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    event_name: str
    event_version: int
    event_time_jst: datetime
    session_token_hmac: str
    article_id: str
    placement: str
    consent_state: str
    result_state: str | None = None
    source_id: str | None = None
    product_id: str | None = None
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.event_name not in EVENT_ALLOWLIST:
            raise ValueError("event is not allowlisted")
        if self.event_version != 1:
            raise ValueError("unsupported event version")
        if self.schema_version != "1.0.0":
            raise ValueError("unsupported event schema")
        if (
            self.event_time_jst.tzinfo is None
            or self.event_time_jst.utcoffset() is None
        ):
            raise ValueError("event time must be timezone-aware")
        if self.event_time_jst.utcoffset() != timedelta(hours=9):
            raise ValueError("event time must use JST (+09:00)")
        if self.consent_state not in CONSENT_STATES:
            raise ValueError("invalid consent state")
        if self.result_state is not None and self.result_state not in RESULT_STATES:
            raise ValueError("invalid result state")
        if not _PLACEMENT.fullmatch(self.placement):
            raise ValueError("invalid placement")
        if not _MACHINE_ID.fullmatch(self.article_id):
            raise ValueError("article ID must be a machine identifier")
        if self.source_id is not None and not _SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("source ID must be a machine identifier")
        if self.product_id is not None and not _PRODUCT_ID.fullmatch(self.product_id):
            raise ValueError("product ID must be a machine identifier")
        if not _HMAC.fullmatch(self.session_token_hmac):
            raise ValueError("invalid session token HMAC")
        optional_values = {
            "result_state": self.result_state,
            "source_id": self.source_id,
            "product_id": self.product_id,
        }
        required_fields, allowed_fields = EVENT_FIELD_POLICY[self.event_name]
        if any(optional_values[field] is None for field in required_fields):
            raise ValueError("event-specific required field is missing")
        if any(
            value is not None and field not in allowed_fields
            for field, value in optional_values.items()
        ):
            raise ValueError("event-specific irrelevant field is forbidden")

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_name": self.event_name,
            "event_version": self.event_version,
            "event_time_jst": self.event_time_jst.isoformat(),
            "session_token_hmac": self.session_token_hmac,
            "article_id": self.article_id,
            "placement": self.placement,
            "consent_state": self.consent_state,
            "result_state": self.result_state,
            "source_id": self.source_id,
            "product_id": self.product_id,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> AnalyticsEvent:
        keys = set(payload)
        if keys & FORBIDDEN_FIELDS or not keys.issubset(EVENT_FIELDS):
            raise ValueError("event fields are forbidden or unknown")
        required = {
            "event_name",
            "event_version",
            "event_time_jst",
            "session_token_hmac",
            "article_id",
            "placement",
            "consent_state",
            "schema_version",
        }
        if not required.issubset(payload):
            raise ValueError("required event field is missing")
        event_time = payload["event_time_jst"]
        if isinstance(event_time, str):
            try:
                event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("invalid event time") from exc
        if not isinstance(event_time, datetime):
            raise ValueError("invalid event time")
        string_fields = (
            "event_name",
            "session_token_hmac",
            "article_id",
            "placement",
            "consent_state",
            "schema_version",
        )
        if any(not isinstance(payload[name], str) for name in string_fields):
            raise ValueError("invalid event field type")
        optional = ("result_state", "source_id", "product_id")
        if any(
            payload.get(name) is not None and not isinstance(payload.get(name), str)
            for name in optional
        ):
            raise ValueError("invalid optional event field type")
        version = payload["event_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("invalid event version")
        return cls(
            event_name=str(payload["event_name"]),
            event_version=version,
            event_time_jst=event_time,
            session_token_hmac=str(payload["session_token_hmac"]),
            article_id=str(payload["article_id"]),
            placement=str(payload["placement"]),
            consent_state=str(payload["consent_state"]),
            result_state=(
                str(payload["result_state"])
                if payload.get("result_state") is not None
                else None
            ),
            source_id=(
                str(payload["source_id"])
                if payload.get("source_id") is not None
                else None
            ),
            product_id=(
                str(payload["product_id"])
                if payload.get("product_id") is not None
                else None
            ),
            schema_version=str(payload["schema_version"]),
        )


class SessionTokenRotator:
    """Rotate after 30 minutes of inactivity, not on an epoch boundary."""

    __slots__ = (
        "_ephemeral_id",
        "_generation",
        "_hmac_key",
        "_last_activity",
        "_token",
    )

    def __init__(self, *, hmac_key: bytes, ephemeral_session_id: str) -> None:
        if len(hmac_key) < 16 or not ephemeral_session_id:
            raise ValueError("invalid rotator input")
        self._hmac_key = hmac_key
        self._ephemeral_id = ephemeral_session_id
        self._generation = 0
        self._last_activity: datetime | None = None
        self._token: str | None = None

    def _new_token(self, at: datetime) -> str:
        material = f"{self._ephemeral_id}:{self._generation}:{at.isoformat()}".encode()
        return hmac.new(self._hmac_key, material, hashlib.sha256).hexdigest()

    def token_for(self, event_time: datetime) -> str:
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            raise ValueError("event time must be timezone-aware")
        if self._last_activity is not None and event_time < self._last_activity:
            raise ValueError("event time cannot move backwards")
        if self._last_activity is None:
            self._token = self._new_token(event_time)
        elif event_time - self._last_activity >= timedelta(minutes=30):
            self._generation += 1
            self._token = self._new_token(event_time)
        self._last_activity = event_time
        assert self._token is not None
        return self._token


def dedupe_events(events: Sequence[AnalyticsEvent]) -> tuple[AnalyticsEvent, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[AnalyticsEvent] = []
    for event in sorted(events, key=lambda item: item.event_time_jst):
        key = (
            event.event_name,
            event.event_time_jst,
            event.session_token_hmac,
            event.article_id,
            event.placement,
            event.result_state,
            event.source_id,
            event.product_id,
        )
        if key not in seen:
            seen.add(key)
            result.append(event)
    return tuple(result)


def qualified_decision_sessions(events: Sequence[AnalyticsEvent]) -> int:
    """Count a local QDS once per rotating session/article decision sequence."""

    unique = dedupe_events(events)
    grouped: dict[tuple[str, str], list[AnalyticsEvent]] = {}
    for event in unique:
        grouped.setdefault((event.session_token_hmac, event.article_id), []).append(
            event
        )
    count = 0
    for group in grouped.values():
        if any(
            event.event_name == "tool_result_view"
            and event.result_state in RESULT_STATES
            for event in group
        ):
            count += 1
            continue
        decision_times = [
            event.event_time_jst
            for event in group
            if event.event_name in {"comparison_view", "evidence_link_open"}
        ]
        completion_times = [
            event.event_time_jst
            for event in group
            if event.event_name
            in {
                "official_source_open",
                "affiliate_outbound_activate",
            }
        ]
        if any(
            start <= finish <= start + timedelta(minutes=30)
            for start in decision_times
            for finish in completion_times
        ):
            count += 1
    return count


__all__ = [
    "AnalyticsEvent",
    "CONSENT_STATES",
    "EVENT_ALLOWLIST",
    "EVENT_FIELDS",
    "EVENT_FIELD_POLICY",
    "FORBIDDEN_FIELDS",
    "SessionTokenRotator",
    "RESULT_STATES",
    "dedupe_events",
    "qualified_decision_sessions",
]
