"""Closed domain model for the ST-1704 owner-local pilot ledger.

The model accepts only sanitized aggregate observations.  It has no provider,
WordPress, browser, publication, tracking, or recommendation mutation capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Mapping, NoReturn, SupportsIndex, cast


LEDGER_SCHEMA = "ST1704_OWNER_LOCAL_PILOT_LEDGER_V1"
OBSERVATION_SCHEMA = "ST1704_OWNER_LOCAL_PILOT_OBSERVATION_V1"
GENESIS_SHA256 = "0" * 64
PILOT_POLICY: dict[str, object] = {
    "article_slots": 5,
    "automatic_publication": "DISABLED",
    "duration_days": 14,
    "first_five_drafts": "CODEX_NOT_OPENAI_API",
    "improvement_output": "PROPOSAL_AND_DIFF_ONLY",
    "labor_cost_per_hour_jpy": 3000,
    "monthly_incremental_cost_cap_jpy": 2000,
    "nonessential_tracking": "DISABLED_OD_012",
    "site_origin": "https://kurashinoshirube.com",
}

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,127}\Z", re.ASCII)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC_SECOND = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_MAX_VALUE = (1 << 63) - 1


class PilotFailureCode(str, Enum):
    INVALID_DOCUMENT = "INVALID_DOCUMENT"
    OBSERVATION_ID_CONFLICT = "OBSERVATION_ID_CONFLICT"
    ARTICLE_IDENTITY_CONFLICT = "ARTICLE_IDENTITY_CONFLICT"
    LEDGER_TAMPERED = "LEDGER_TAMPERED"
    STORE_NOT_INITIALIZED = "STORE_NOT_INITIALIZED"
    STORE_UNSAFE = "STORE_UNSAFE"
    STORE_BUSY = "STORE_BUSY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RUNTIME_INVALID = "RUNTIME_INVALID"


@dataclass(slots=True, repr=False)
class PilotFailure(RuntimeError):
    code: PilotFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not PilotFailureCode:
            raise TypeError("invalid pilot failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PilotFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("pilot failure serialization is disabled")


def fail_pilot(code: PilotFailureCode = PilotFailureCode.INVALID_DOCUMENT) -> NoReturn:
    raise PilotFailure(code) from None


class ValueState(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
    OBSERVED_ZERO = "OBSERVED_ZERO"
    OBSERVED_VALUE = "OBSERVED_VALUE"


class PublicationStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    HUMAN_CONFIRMED_PUBLISHED = "HUMAN_CONFIRMED_PUBLISHED"
    HUMAN_CONFIRMED_NOT_PUBLISHED = "HUMAN_CONFIRMED_NOT_PUBLISHED"


class ReviewStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    HUMAN_REVIEW_COMPLETE = "HUMAN_REVIEW_COMPLETE"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    BLOCKED = "BLOCKED"


class MetricSourceKind(str, Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    OWNER_MANUAL_AGGREGATE = "OWNER_MANUAL_AGGREGATE"
    WORDPRESS_ADMIN_AGGREGATE = "WORDPRESS_ADMIN_AGGREGATE"
    SEARCH_CONSOLE_AGGREGATE = "SEARCH_CONSOLE_AGGREGATE"
    RAKUTEN_REPORT_AGGREGATE = "RAKUTEN_REPORT_AGGREGATE"


class AttributionBasis(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNVERIFIED = "UNVERIFIED"
    PROVIDER_REPORTED_UNVERIFIED = "PROVIDER_REPORTED_UNVERIFIED"
    DIRECT_UNVERIFIED = "DIRECT_UNVERIFIED"
    ESTIMATED_UNVERIFIED = "ESTIMATED_UNVERIFIED"
    UNATTRIBUTED = "UNATTRIBUTED"


class AppendDisposition(str, Enum):
    APPENDED = "APPENDED"
    REPLAYED = "REPLAYED"


class ImprovementDecision(str, Enum):
    STOP_AND_REVIEW = "STOP_AND_REVIEW"
    COLLECT_BASELINE = "COLLECT_BASELINE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVIEW_CANDIDATES_ONLY = "REVIEW_CANDIDATES_ONLY"


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        fail_pilot()
    return cast(Mapping[str, object], value)


def _keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        fail_pilot()


def _enum(enum_type: type[Enum], value: object) -> Enum:
    if type(value) is not str:
        fail_pilot()
    try:
        return enum_type(value)
    except ValueError:
        fail_pilot()


def _nonnegative(value: object, *, maximum: int = _MAX_VALUE) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        fail_pilot()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_pilot()
    return value


def _timestamp(value: object) -> str:
    if type(value) is not str or _UTC_SECOND.fullmatch(value) is None:
        fail_pilot()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_pilot()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        fail_pilot()
    return value


def _date(value: object) -> str:
    if type(value) is not str:
        fail_pilot()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        fail_pilot()
    if parsed.isoformat() != value:
        fail_pilot()
    return value


def canonical_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except TypeError, ValueError, UnicodeError:
        fail_pilot()
    return rendered.encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class NumberObservation:
    state: ValueState
    value: int | None

    def __post_init__(self) -> None:
        if type(self.state) is not ValueState:
            fail_pilot()
        if self.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}:
            if self.value is not None:
                fail_pilot()
        elif self.state is ValueState.UNVERIFIED:
            if self.value is not None:
                _nonnegative(self.value)
        elif self.state is ValueState.OBSERVED_ZERO:
            if self.value != 0 or type(self.value) is not int:
                fail_pilot()
        elif type(self.value) is not int or not 1 <= self.value <= _MAX_VALUE:
            fail_pilot()

    @classmethod
    def parse(cls, value: object) -> NumberObservation:
        source = _mapping(value)
        _keys(source, {"state", "value"})
        return cls(
            state=cast(ValueState, _enum(ValueState, source["state"])),
            value=cast(int | None, source["value"]),
        )

    def payload(self) -> dict[str, object]:
        return {"state": self.state.value, "value": self.value}


@dataclass(frozen=True, slots=True)
class MetricObservation:
    state: ValueState
    value: int | None
    period_start: str | None
    period_end: str | None
    source_kind: MetricSourceKind
    input_sha256: str | None
    attribution_basis: AttributionBasis

    def __post_init__(self) -> None:
        NumberObservation(self.state, self.value)
        if (
            type(self.source_kind) is not MetricSourceKind
            or type(self.attribution_basis) is not AttributionBasis
        ):
            fail_pilot()
        if self.state is ValueState.NOT_OBSERVED:
            if (
                self.period_start is not None
                or self.period_end is not None
                or self.input_sha256 is not None
                or self.source_kind is not MetricSourceKind.NOT_CONNECTED
                or self.attribution_basis is not AttributionBasis.NOT_APPLICABLE
            ):
                fail_pilot()
            return
        if (
            self.period_start is None
            or self.period_end is None
            or self.input_sha256 is None
            or self.source_kind is MetricSourceKind.NOT_CONNECTED
        ):
            fail_pilot()
        start = _date(self.period_start)
        end = _date(self.period_end)
        if start > end:
            fail_pilot()
        _sha256(self.input_sha256)

    @classmethod
    def parse(cls, value: object) -> MetricObservation:
        source = _mapping(value)
        _keys(
            source,
            {
                "state",
                "value",
                "period_start",
                "period_end",
                "source_kind",
                "input_sha256",
                "attribution_basis",
            },
        )
        return cls(
            state=cast(ValueState, _enum(ValueState, source["state"])),
            value=cast(int | None, source["value"]),
            period_start=cast(str | None, source["period_start"]),
            period_end=cast(str | None, source["period_end"]),
            source_kind=cast(
                MetricSourceKind, _enum(MetricSourceKind, source["source_kind"])
            ),
            input_sha256=cast(str | None, source["input_sha256"]),
            attribution_basis=cast(
                AttributionBasis,
                _enum(AttributionBasis, source["attribution_basis"]),
            ),
        )

    def payload(self) -> dict[str, object]:
        return {
            "attribution_basis": self.attribution_basis.value,
            "input_sha256": self.input_sha256,
            "period_end": self.period_end,
            "period_start": self.period_start,
            "source_kind": self.source_kind.value,
            "state": self.state.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ArticleIdentity:
    slot: int
    public_slug: str | None
    article_ref_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.slot) is not int or not 1 <= self.slot <= 5:
            fail_pilot()
        present = int(self.public_slug is not None) + int(
            self.article_ref_sha256 is not None
        )
        if present != 1:
            fail_pilot()
        if self.public_slug is not None:
            if (
                type(self.public_slug) is not str
                or not 1 <= len(self.public_slug) <= 120
                or _SLUG.fullmatch(self.public_slug) is None
            ):
                fail_pilot()
        if self.article_ref_sha256 is not None:
            _sha256(self.article_ref_sha256)

    def payload(self) -> dict[str, object]:
        return {
            "article_ref_sha256": self.article_ref_sha256,
            "public_slug": self.public_slug,
            "slot": self.slot,
        }


@dataclass(frozen=True, slots=True)
class PublicationObservation:
    status: PublicationStatus
    confirmed_by_role: str | None
    confirmed_at_utc: str | None

    def __post_init__(self) -> None:
        if type(self.status) is not PublicationStatus:
            fail_pilot()
        if self.status is PublicationStatus.NOT_OBSERVED:
            if self.confirmed_by_role is not None or self.confirmed_at_utc is not None:
                fail_pilot()
        elif self.confirmed_by_role != "OWNER" or self.confirmed_at_utc is None:
            fail_pilot()
        else:
            _timestamp(self.confirmed_at_utc)

    def payload(self) -> dict[str, object]:
        return {
            "confirmed_at_utc": self.confirmed_at_utc,
            "confirmed_by_role": self.confirmed_by_role,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ReviewObservation:
    status: ReviewStatus
    reviewer_role: str | None
    reviewed_at_utc: str | None

    def __post_init__(self) -> None:
        if type(self.status) is not ReviewStatus:
            fail_pilot()
        if self.status is ReviewStatus.NOT_OBSERVED:
            if self.reviewer_role is not None or self.reviewed_at_utc is not None:
                fail_pilot()
        elif self.reviewer_role != "OWNER" or self.reviewed_at_utc is None:
            fail_pilot()
        else:
            _timestamp(self.reviewed_at_utc)

    def payload(self) -> dict[str, object]:
        return {
            "reviewed_at_utc": self.reviewed_at_utc,
            "reviewer_role": self.reviewer_role,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class PilotObservation:
    observation_id: str
    observed_at_utc: str
    article: ArticleIdentity
    publication: PublicationObservation
    review: ReviewObservation
    work_minutes: NumberObservation
    incremental_cost_jpy: NumberObservation
    critical_defects: NumberObservation
    major_defects: NumberObservation
    minor_defects: NumberObservation
    access: MetricObservation
    clicks: MetricObservation
    revenue_jpy: MetricObservation

    def __post_init__(self) -> None:
        if (
            type(self.observation_id) is not str
            or _REFERENCE.fullmatch(self.observation_id) is None
        ):
            fail_pilot()
        _timestamp(self.observed_at_utc)
        expected_types = (
            (self.article, ArticleIdentity),
            (self.publication, PublicationObservation),
            (self.review, ReviewObservation),
            (self.work_minutes, NumberObservation),
            (self.incremental_cost_jpy, NumberObservation),
            (self.critical_defects, NumberObservation),
            (self.major_defects, NumberObservation),
            (self.minor_defects, NumberObservation),
            (self.access, MetricObservation),
            (self.clicks, MetricObservation),
            (self.revenue_jpy, MetricObservation),
        )
        if any(type(value) is not expected for value, expected in expected_types):
            fail_pilot()

    @classmethod
    def parse(cls, value: object) -> PilotObservation:
        source = _mapping(value)
        _keys(
            source,
            {
                "schema",
                "observation_id",
                "observed_at_utc",
                "article",
                "publication",
                "review",
                "work_minutes",
                "incremental_cost_jpy",
                "defects",
                "metrics",
            },
        )
        if source["schema"] != OBSERVATION_SCHEMA:
            fail_pilot()
        article = _mapping(source["article"])
        _keys(article, {"slot", "public_slug", "article_ref_sha256"})
        publication = _mapping(source["publication"])
        _keys(publication, {"status", "confirmed_by_role", "confirmed_at_utc"})
        review = _mapping(source["review"])
        _keys(review, {"status", "reviewer_role", "reviewed_at_utc"})
        defects = _mapping(source["defects"])
        _keys(defects, {"critical", "major", "minor"})
        metrics = _mapping(source["metrics"])
        _keys(metrics, {"access", "clicks", "revenue_jpy"})
        return cls(
            observation_id=cast(str, source["observation_id"]),
            observed_at_utc=cast(str, source["observed_at_utc"]),
            article=ArticleIdentity(
                slot=cast(int, article["slot"]),
                public_slug=cast(str | None, article["public_slug"]),
                article_ref_sha256=cast(str | None, article["article_ref_sha256"]),
            ),
            publication=PublicationObservation(
                status=cast(
                    PublicationStatus,
                    _enum(PublicationStatus, publication["status"]),
                ),
                confirmed_by_role=cast(str | None, publication["confirmed_by_role"]),
                confirmed_at_utc=cast(str | None, publication["confirmed_at_utc"]),
            ),
            review=ReviewObservation(
                status=cast(ReviewStatus, _enum(ReviewStatus, review["status"])),
                reviewer_role=cast(str | None, review["reviewer_role"]),
                reviewed_at_utc=cast(str | None, review["reviewed_at_utc"]),
            ),
            work_minutes=NumberObservation.parse(source["work_minutes"]),
            incremental_cost_jpy=NumberObservation.parse(
                source["incremental_cost_jpy"]
            ),
            critical_defects=NumberObservation.parse(defects["critical"]),
            major_defects=NumberObservation.parse(defects["major"]),
            minor_defects=NumberObservation.parse(defects["minor"]),
            access=MetricObservation.parse(metrics["access"]),
            clicks=MetricObservation.parse(metrics["clicks"]),
            revenue_jpy=MetricObservation.parse(metrics["revenue_jpy"]),
        )

    def payload(self) -> dict[str, object]:
        return {
            "article": self.article.payload(),
            "defects": {
                "critical": self.critical_defects.payload(),
                "major": self.major_defects.payload(),
                "minor": self.minor_defects.payload(),
            },
            "incremental_cost_jpy": self.incremental_cost_jpy.payload(),
            "metrics": {
                "access": self.access.payload(),
                "clicks": self.clicks.payload(),
                "revenue_jpy": self.revenue_jpy.payload(),
            },
            "observation_id": self.observation_id,
            "observed_at_utc": self.observed_at_utc,
            "publication": self.publication.payload(),
            "review": self.review.payload(),
            "schema": OBSERVATION_SCHEMA,
            "work_minutes": self.work_minutes.payload(),
        }


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    sequence: int
    previous_event_sha256: str
    observation_sha256: str
    event_sha256: str
    observation: PilotObservation

    def payload(self) -> dict[str, object]:
        return {
            "event_sha256": self.event_sha256,
            "observation": self.observation.payload(),
            "observation_sha256": self.observation_sha256,
            "previous_event_sha256": self.previous_event_sha256,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class PilotLedger:
    events: tuple[LedgerEvent, ...]

    @property
    def head_sha256(self) -> str:
        return self.events[-1].event_sha256 if self.events else GENESIS_SHA256

    def payload(self) -> dict[str, object]:
        return {
            "events": [event.payload() for event in self.events],
            "head_sha256": self.head_sha256,
            "policy": PILOT_POLICY,
            "schema": LEDGER_SCHEMA,
        }


def empty_ledger() -> PilotLedger:
    return PilotLedger(events=())


def parse_ledger(value: object) -> PilotLedger:
    source = _mapping(value)
    _keys(source, {"schema", "policy", "events", "head_sha256"})
    if source["schema"] != LEDGER_SCHEMA or source["policy"] != PILOT_POLICY:
        fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
    raw_events = source["events"]
    if type(raw_events) is not list or len(raw_events) > 1000:
        fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
    events: list[LedgerEvent] = []
    previous = GENESIS_SHA256
    ids: set[str] = set()
    identities: dict[int, ArticleIdentity] = {}
    for index, raw_event in enumerate(raw_events, 1):
        event = _mapping(raw_event)
        _keys(
            event,
            {
                "sequence",
                "previous_event_sha256",
                "observation_sha256",
                "event_sha256",
                "observation",
            },
        )
        observation = PilotObservation.parse(event["observation"])
        if observation.observation_id in ids:
            fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
        ids.add(observation.observation_id)
        prior_identity = identities.get(observation.article.slot)
        if prior_identity is not None and prior_identity != observation.article:
            fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
        identities[observation.article.slot] = observation.article
        observation_hash = digest(observation.payload())
        expected_event_hash = digest(
            {
                "observation": observation.payload(),
                "observation_sha256": observation_hash,
                "previous_event_sha256": previous,
                "sequence": index,
            }
        )
        if (
            event["sequence"] != index
            or event["previous_event_sha256"] != previous
            or event["observation_sha256"] != observation_hash
            or event["event_sha256"] != expected_event_hash
        ):
            fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
        events.append(
            LedgerEvent(
                sequence=index,
                previous_event_sha256=previous,
                observation_sha256=observation_hash,
                event_sha256=expected_event_hash,
                observation=observation,
            )
        )
        previous = expected_event_hash
    if source["head_sha256"] != previous:
        fail_pilot(PilotFailureCode.LEDGER_TAMPERED)
    return PilotLedger(events=tuple(events))


def append_observation(
    ledger: PilotLedger, observation: PilotObservation
) -> tuple[PilotLedger, AppendDisposition, str]:
    if type(ledger) is not PilotLedger or type(observation) is not PilotObservation:
        fail_pilot()
    for event in ledger.events:
        if event.observation.observation_id == observation.observation_id:
            if event.observation.payload() != observation.payload():
                fail_pilot(PilotFailureCode.OBSERVATION_ID_CONFLICT)
            return ledger, AppendDisposition.REPLAYED, event.event_sha256
        if (
            event.observation.article.slot == observation.article.slot
            and event.observation.article != observation.article
        ):
            fail_pilot(PilotFailureCode.ARTICLE_IDENTITY_CONFLICT)
    sequence = len(ledger.events) + 1
    previous = ledger.head_sha256
    observation_hash = digest(observation.payload())
    event_hash = digest(
        {
            "observation": observation.payload(),
            "observation_sha256": observation_hash,
            "previous_event_sha256": previous,
            "sequence": sequence,
        }
    )
    event = LedgerEvent(
        sequence=sequence,
        previous_event_sha256=previous,
        observation_sha256=observation_hash,
        event_sha256=event_hash,
        observation=observation,
    )
    return (
        PilotLedger(events=ledger.events + (event,)),
        AppendDisposition.APPENDED,
        event_hash,
    )


def _observed(number: NumberObservation) -> bool:
    return number.state in {ValueState.OBSERVED_ZERO, ValueState.OBSERVED_VALUE}


def build_report(ledger: PilotLedger) -> dict[str, object]:
    if type(ledger) is not PilotLedger:
        fail_pilot()
    latest: dict[int, PilotObservation] = {}
    for event in ledger.events:
        latest[event.observation.article.slot] = event.observation
    ordered = tuple(latest[slot] for slot in sorted(latest))
    critical_positive = any(
        observation.critical_defects.value is not None
        and observation.critical_defects.value > 0
        for observation in ordered
    )
    review_stop = any(
        observation.review.status
        in {ReviewStatus.CHANGES_REQUIRED, ReviewStatus.BLOCKED}
        for observation in ordered
    )
    complete = len(ordered) == 5 and all(
        observation.publication.status is PublicationStatus.HUMAN_CONFIRMED_PUBLISHED
        and observation.review.status is ReviewStatus.HUMAN_REVIEW_COMPLETE
        and all(
            _observed(value)
            for value in (
                observation.work_minutes,
                observation.incremental_cost_jpy,
                observation.critical_defects,
                observation.major_defects,
                observation.minor_defects,
                observation.access,
                observation.clicks,
                observation.revenue_jpy,
            )
        )
        for observation in ordered
    )
    candidates: set[str] = set()
    if len(ordered) < 5:
        candidates.add("COMPLETE_FIVE_ARTICLE_SLOTS")
    if any(
        observation.publication.status
        is not PublicationStatus.HUMAN_CONFIRMED_PUBLISHED
        for observation in ordered
    ):
        candidates.add("CONFIRM_HUMAN_PUBLICATION")
    if any(
        observation.review.status is not ReviewStatus.HUMAN_REVIEW_COMPLETE
        for observation in ordered
    ):
        candidates.add("COMPLETE_HUMAN_REVIEW_LOGS")
    if any(
        not all(
            _observed(value)
            for value in (
                observation.critical_defects,
                observation.major_defects,
                observation.minor_defects,
            )
        )
        for observation in ordered
    ):
        candidates.add("COMPLETE_QUALITY_OBSERVATIONS")
    if any(
        not _observed(observation.work_minutes)
        or not _observed(observation.incremental_cost_jpy)
        for observation in ordered
    ):
        candidates.add("COMPLETE_WORK_COST_OBSERVATIONS")
    if any(
        not all(
            _observed(value)
            for value in (
                observation.access,
                observation.clicks,
                observation.revenue_jpy,
            )
        )
        for observation in ordered
    ):
        candidates.add("COLLECT_AGGREGATED_METRICS")
    if any(
        (observation.major_defects.value or 0) > 0
        or (observation.minor_defects.value or 0) > 0
        for observation in ordered
    ):
        candidates.add("REVIEW_MAJOR_MINOR_DEFECTS")
    observed_costs = [
        cast(int, observation.incremental_cost_jpy.value)
        for observation in ordered
        if _observed(observation.incremental_cost_jpy)
    ]
    if sum(observed_costs) > 2000:
        candidates.add("REVIEW_MONTHLY_INCREMENTAL_COST_CAP")
    if critical_positive or review_stop:
        decision = ImprovementDecision.STOP_AND_REVIEW
    elif not ordered:
        decision = ImprovementDecision.COLLECT_BASELINE
    elif not complete:
        decision = ImprovementDecision.INSUFFICIENT_EVIDENCE
    else:
        decision = ImprovementDecision.REVIEW_CANDIDATES_ONLY
    articles = []
    for observation in ordered:
        articles.append(
            {
                "article": observation.article.payload(),
                "defects": {
                    "critical": observation.critical_defects.payload(),
                    "major": observation.major_defects.payload(),
                    "minor": observation.minor_defects.payload(),
                },
                "incremental_cost_jpy": observation.incremental_cost_jpy.payload(),
                "metrics": {
                    "access": observation.access.payload(),
                    "clicks": observation.clicks.payload(),
                    "revenue_jpy": observation.revenue_jpy.payload(),
                },
                "observation_id": observation.observation_id,
                "observed_at_utc": observation.observed_at_utc,
                "publication": observation.publication.payload(),
                "review": observation.review.payload(),
                "work_minutes": observation.work_minutes.payload(),
            }
        )
    return {
        "articles": articles,
        "authority": "OWNER_LOCAL_SANITIZED_OBSERVATION_ONLY",
        "boundaries": {
            "analytics_activation": "NOT_EXECUTED",
            "automatic_publication": "DISABLED",
            "finance_as_recommendation_input": "FORBIDDEN",
            "network_requests": 0,
            "provider_proof": "NOT_EXECUTED",
            "tracking": "DISABLED_OD_012",
            "wordpress_writes": 0,
        },
        "decision": decision.value,
        "event_count": len(ledger.events),
        "freshness": "PERIOD_REPORTED_NO_SLA_OD_007_UNRESOLVED",
        "head_sha256": ledger.head_sha256,
        "policy": PILOT_POLICY,
        "proposal_candidates": sorted(candidates),
        "schema": "ST1704_OWNER_LOCAL_PILOT_REPORT_V1",
        "slot_count": len(ordered),
        "status": {
            "ST-1704": "NOT_STARTED",
            "TST-018": "NOT_EXECUTED",
            "TST-020": "NOT_EXECUTED",
            "TST-032": "NOT_EXECUTED",
            "production": "NOT_READY",
        },
    }


__all__ = [
    "AppendDisposition",
    "AttributionBasis",
    "GENESIS_SHA256",
    "ImprovementDecision",
    "LEDGER_SCHEMA",
    "LedgerEvent",
    "MetricObservation",
    "MetricSourceKind",
    "NumberObservation",
    "OBSERVATION_SCHEMA",
    "PILOT_POLICY",
    "PilotFailure",
    "PilotFailureCode",
    "PilotLedger",
    "PilotObservation",
    "PublicationStatus",
    "ReviewStatus",
    "ValueState",
    "append_observation",
    "build_report",
    "canonical_bytes",
    "digest",
    "empty_ledger",
    "fail_pilot",
    "parse_ledger",
]
