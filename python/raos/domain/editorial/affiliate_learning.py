"""ST-1704 owner-private affiliate-learning measurement domain.

This additive V2 contract learns from sanitized aggregate observations only.
It deliberately cannot publish, track visitors, call a provider, mutate editorial
content, or use affiliate economics as a recommendation input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
import re
from typing import Mapping, NoReturn, Sequence, cast

from raos.domain.editorial.owner_local_pilot import (
    AppendDisposition,
    GENESIS_SHA256,
    PilotFailureCode,
    ValueState,
    digest,
    fail_pilot,
)


CONTRACT_SCHEMA = "ST1704_AFFILIATE_LEARNING_MEASUREMENT_CONTRACT_V2"
LEDGER_SCHEMA = "ST1704_AFFILIATE_LEARNING_LEDGER_V2"
ARTICLE_OBSERVATION_SCHEMA = "ST1704_AFFILIATE_LEARNING_ARTICLE_OBSERVATION_V2"
PROGRAM_OBSERVATION_SCHEMA = "ST1704_AFFILIATE_LEARNING_PROGRAM_OBSERVATION_V2"
REPORT_SCHEMA = "ST1704_AFFILIATE_LEARNING_REPORT_V2"
PROGRAM = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
PERIOD_DURATION_DAYS = 14

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,127}\Z", re.ASCII)
_ARTICLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_SLUG = _ARTICLE_ID
_TYPE_CODE = re.compile(r"AT-[0-9]{3}\Z", re.ASCII)
_UTC_SECOND = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z",
    re.ASCII,
)
_MAX_VALUE = (1 << 63) - 1

ARTICLE_METRIC_NAMES = (
    "search_impressions",
    "search_clicks",
    "article_views",
    "affiliate_clicks",
    "pending_outcomes",
    "confirmed_outcomes",
    "rejected_outcomes",
    "direct_confirmed_reward_jpy",
    "work_minutes",
    "incremental_cost_jpy",
    "broken_links",
)
DERIVED_METRIC_NAMES = (
    "search_ctr",
    "affiliate_click_rate",
    "confirmed_reward_per_click_jpy",
    "confirmation_rate",
    "confirmed_reward_per_content_hour_jpy",
)
INTENT_CLASSIFICATIONS = (
    "CONDITION_COMPARISON",
    "SELECTION_GUIDE",
    "HOUSEHOLD_FIT_COMPARISON",
    "MODEL_DIFFERENCES",
    "CONDITION_SHORTLIST",
)

EXPECTED_METRIC_CONTRACT: dict[str, object] = {
    "article_metrics": list(ARTICLE_METRIC_NAMES),
    "program_metrics": ["unattributed_confirmed_reward_jpy"],
    "states": [value.value for value in ValueState],
    "zero_is_observed_only_when_explicit": True,
}
EXPECTED_DERIVATION_CONTRACT: dict[str, object] = {
    "affiliate_click_rate": "sum(affiliate_clicks)/sum(article_views)",
    "confirmation_rate": "sum(confirmed_outcomes)/sum(confirmed_outcomes+rejected_outcomes)",
    "confirmed_reward_per_click_jpy": "sum(direct_confirmed_reward_jpy)/sum(affiliate_clicks)",
    "confirmed_reward_per_content_hour_jpy": "sum(direct_confirmed_reward_jpy)*60/sum(work_minutes)",
    "decimal_places": 6,
    "rounding": "ROUND_HALF_EVEN",
    "search_ctr": "sum(search_clicks)/sum(search_impressions)",
    "unavailability": [
        "MISSING_INPUT",
        "UNVERIFIED_INPUT",
        "ZERO_DENOMINATOR",
        "COHORT_IMMATURE",
        "PERIOD_MISMATCH",
        "PROGRAM_MISMATCH",
        "MISSING_ARTICLE_SLOTS",
    ],
}
EXPECTED_GUARDRAILS: dict[str, object] = {
    "article_html_mutation": False,
    "arbitrary_total_allocation": False,
    "automatic_publication": False,
    "cta_mutation": False,
    "live_provider_calls": False,
    "network_requests": False,
    "product_selection_mutation": False,
    "publication_snapshot_mutation": False,
    "recommendation_inputs_excluded": [
        "AFFILIATE_COMMISSION_RATE",
        "EPC",
        "RPM",
        "PROFIT",
    ],
    "recommendation_order_mutation": False,
    "tracking_activation": False,
    "unattributed_reward_article_allocation": False,
}


def _fail(code: PilotFailureCode = PilotFailureCode.INVALID_DOCUMENT) -> NoReturn:
    fail_pilot(code)


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        _fail()
    return cast(Mapping[str, object], value)


def _keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        _fail()


def _strict_string(
    value: object,
    *,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _fail()
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail()
    return value


def _sha256(value: object) -> str:
    return _strict_string(value, maximum=64, pattern=_SHA256)


def _timestamp(value: object) -> str:
    rendered = _strict_string(value, maximum=20, pattern=_UTC_SECOND)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        _fail()
    return rendered


def _date(value: object) -> str:
    if type(value) is not str:
        _fail()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail()
    if parsed.isoformat() != value:
        _fail()
    return value


def _nonnegative(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_VALUE:
        _fail()
    return value


class VerificationState(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class AttributionBasisV2(str, Enum):
    OWNER_VERIFIED_DIRECT_AGGREGATE = "OWNER_VERIFIED_DIRECT_AGGREGATE"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    UNATTRIBUTED_PROGRAM_TOTAL = "UNATTRIBUTED_PROGRAM_TOTAL"


class CohortMaturity(str, Enum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricResultState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricUnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    MISSING_ARTICLE_SLOTS = "MISSING_ARTICLE_SLOTS"


@dataclass(frozen=True, slots=True)
class AggregateValue:
    state: ValueState
    value: int | None
    input_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.state) is not ValueState:
            _fail()
        if self.state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}:
            if self.value is not None or self.input_sha256 is not None:
                _fail()
            return
        if self.input_sha256 is None:
            _fail()
        _sha256(self.input_sha256)
        if self.state is ValueState.UNVERIFIED:
            if self.value is not None:
                _nonnegative(self.value)
            return
        if self.state is ValueState.OBSERVED_ZERO:
            if type(self.value) is not int or self.value != 0:
                _fail()
            return
        if type(self.value) is not int or not 1 <= self.value <= _MAX_VALUE:
            _fail()

    @classmethod
    def parse(cls, value: object) -> AggregateValue:
        source = _mapping(value)
        _keys(source, {"state", "value", "input_sha256"})
        try:
            state = ValueState(source["state"])
        except TypeError, ValueError:
            _fail()
        return cls(
            state=state,
            value=cast(int | None, source["value"]),
            input_sha256=cast(str | None, source["input_sha256"]),
        )

    @property
    def is_observed(self) -> bool:
        return self.state in {ValueState.OBSERVED_ZERO, ValueState.OBSERVED_VALUE}

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": self.input_sha256,
            "state": self.state.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class MeasurementPeriod:
    start_date: str
    end_exclusive_date: str
    duration_days: int

    def __post_init__(self) -> None:
        start = date.fromisoformat(_date(self.start_date))
        end = date.fromisoformat(_date(self.end_exclusive_date))
        if (
            type(self.duration_days) is not int
            or self.duration_days != PERIOD_DURATION_DAYS
            or end != start + timedelta(days=PERIOD_DURATION_DAYS)
        ):
            _fail()

    @classmethod
    def parse(cls, value: object) -> MeasurementPeriod:
        source = _mapping(value)
        _keys(source, {"start_date", "end_exclusive_date", "duration_days"})
        return cls(
            start_date=cast(str, source["start_date"]),
            end_exclusive_date=cast(str, source["end_exclusive_date"]),
            duration_days=cast(int, source["duration_days"]),
        )

    def payload(self) -> dict[str, object]:
        return {
            "duration_days": self.duration_days,
            "end_exclusive_date": self.end_exclusive_date,
            "start_date": self.start_date,
        }


@dataclass(frozen=True, slots=True)
class ContractArticle:
    slot: int
    article_id: str
    slug: str
    article_type_code: str
    intent_cluster: str
    intent_classification: str
    packet_sha256: str

    def __post_init__(self) -> None:
        if type(self.slot) is not int or not 1 <= self.slot <= 5:
            _fail()
        _strict_string(self.article_id, maximum=128, pattern=_ARTICLE_ID)
        _strict_string(self.slug, maximum=120, pattern=_SLUG)
        _strict_string(self.article_type_code, maximum=6, pattern=_TYPE_CODE)
        _strict_string(self.intent_cluster, maximum=16)
        if self.intent_classification not in INTENT_CLASSIFICATIONS:
            _fail()
        _sha256(self.packet_sha256)

    @classmethod
    def parse(cls, value: object) -> ContractArticle:
        source = _mapping(value)
        _keys(
            source,
            {
                "slot",
                "article_id",
                "slug",
                "article_type_code",
                "intent_cluster",
                "intent_classification",
                "packet_sha256",
            },
        )
        return cls(
            slot=cast(int, source["slot"]),
            article_id=cast(str, source["article_id"]),
            slug=cast(str, source["slug"]),
            article_type_code=cast(str, source["article_type_code"]),
            intent_cluster=cast(str, source["intent_cluster"]),
            intent_classification=cast(str, source["intent_classification"]),
            packet_sha256=cast(str, source["packet_sha256"]),
        )

    def payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "article_type_code": self.article_type_code,
            "intent_classification": self.intent_classification,
            "intent_cluster": self.intent_cluster,
            "packet_sha256": self.packet_sha256,
            "slot": self.slot,
            "slug": self.slug,
        }


@dataclass(frozen=True, slots=True)
class MeasurementContract:
    articles: tuple[ContractArticle, ...]
    article_collection_sha256: str
    compatibility_template_sha256: str

    def __post_init__(self) -> None:
        if type(self.articles) is not tuple or len(self.articles) != 5:
            _fail()
        if any(type(article) is not ContractArticle for article in self.articles):
            _fail()
        if tuple(article.slot for article in self.articles) != (1, 2, 3, 4, 5):
            _fail()
        if len({article.article_id for article in self.articles}) != 5:
            _fail()
        if len({article.slug for article in self.articles}) != 5:
            _fail()
        _sha256(self.article_collection_sha256)
        _sha256(self.compatibility_template_sha256)

    @classmethod
    def parse(cls, value: object) -> MeasurementContract:
        source = _mapping(value)
        _keys(
            source,
            {
                "schema",
                "story_id",
                "slice_id",
                "program",
                "period_duration_days",
                "packet_hash_basis",
                "owner_private_paths",
                "source_bindings",
                "articles",
                "metric_contract",
                "derivation_contract",
                "guardrails",
            },
        )
        if (
            source["schema"] != CONTRACT_SCHEMA
            or source["story_id"] != "ST-1704"
            or source["slice_id"] != "AFFILIATE_LEARNING_MEASUREMENT_V2"
            or source["program"] != PROGRAM
            or source["period_duration_days"] != PERIOD_DURATION_DAYS
            or source["packet_hash_basis"]
            != "TRACKED_ARTICLE_OBJECT_CANONICAL_JSON_SHA256"
            or source["metric_contract"] != EXPECTED_METRIC_CONTRACT
            or source["derivation_contract"] != EXPECTED_DERIVATION_CONTRACT
            or source["guardrails"] != EXPECTED_GUARDRAILS
        ):
            _fail()
        paths = _mapping(source["owner_private_paths"])
        _keys(paths, {"directory", "ledger", "input", "lock", "stage"})
        if paths != {
            "directory": ".secrets/st1704-owner-local-pilot",
            "input": "affiliate-learning-observation-input.v2.json",
            "ledger": "affiliate-learning-ledger.v2.json",
            "lock": "affiliate-learning-ledger.v2.lock",
            "stage": "affiliate-learning-ledger.v2.json.preparing",
        }:
            _fail()
        bindings = _mapping(source["source_bindings"])
        _keys(
            bindings,
            {
                "article_collection_path",
                "article_collection_sha256",
                "compatibility_template_path",
                "compatibility_template_sha256",
            },
        )
        if (
            bindings["article_collection_path"]
            != "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
            or bindings["compatibility_template_path"]
            != "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json"
        ):
            _fail()
        raw_articles = source["articles"]
        if type(raw_articles) is not list:
            _fail()
        return cls(
            articles=tuple(ContractArticle.parse(item) for item in raw_articles),
            article_collection_sha256=_sha256(bindings["article_collection_sha256"]),
            compatibility_template_sha256=_sha256(
                bindings["compatibility_template_sha256"]
            ),
        )

    @property
    def sha256(self) -> str:
        return digest(self.payload())

    def article_for_slot(self, slot: int) -> ContractArticle:
        if type(slot) is not int or not 1 <= slot <= 5:
            _fail()
        return self.articles[slot - 1]

    def payload(self) -> dict[str, object]:
        return {
            "articles": [article.payload() for article in self.articles],
            "derivation_contract": EXPECTED_DERIVATION_CONTRACT,
            "guardrails": EXPECTED_GUARDRAILS,
            "metric_contract": EXPECTED_METRIC_CONTRACT,
            "owner_private_paths": {
                "directory": ".secrets/st1704-owner-local-pilot",
                "input": "affiliate-learning-observation-input.v2.json",
                "ledger": "affiliate-learning-ledger.v2.json",
                "lock": "affiliate-learning-ledger.v2.lock",
                "stage": "affiliate-learning-ledger.v2.json.preparing",
            },
            "packet_hash_basis": "TRACKED_ARTICLE_OBJECT_CANONICAL_JSON_SHA256",
            "period_duration_days": PERIOD_DURATION_DAYS,
            "program": PROGRAM,
            "schema": CONTRACT_SCHEMA,
            "slice_id": "AFFILIATE_LEARNING_MEASUREMENT_V2",
            "source_bindings": {
                "article_collection_path": "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
                "article_collection_sha256": self.article_collection_sha256,
                "compatibility_template_path": "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json",
                "compatibility_template_sha256": self.compatibility_template_sha256,
            },
            "story_id": "ST-1704",
        }


@dataclass(frozen=True, slots=True)
class EvidenceVerification:
    state: VerificationState
    attribution_basis: AttributionBasisV2
    input_sha256: str | None

    def __post_init__(self) -> None:
        if (
            type(self.state) is not VerificationState
            or type(self.attribution_basis) is not AttributionBasisV2
        ):
            _fail()
        if self.state is VerificationState.VERIFIED:
            if (
                self.attribution_basis
                not in {
                    AttributionBasisV2.OWNER_VERIFIED_DIRECT_AGGREGATE,
                    AttributionBasisV2.UNATTRIBUTED_PROGRAM_TOTAL,
                }
                or self.input_sha256 is None
            ):
                _fail()
            _sha256(self.input_sha256)
        elif self.state is VerificationState.UNVERIFIED:
            if (
                self.attribution_basis is not AttributionBasisV2.UNVERIFIED
                or self.input_sha256 is None
            ):
                _fail()
            _sha256(self.input_sha256)
        elif (
            self.attribution_basis is not AttributionBasisV2.UNAVAILABLE
            or self.input_sha256 is not None
        ):
            _fail()

    @classmethod
    def parse(cls, value: object) -> EvidenceVerification:
        source = _mapping(value)
        _keys(source, {"state", "attribution_basis", "input_sha256"})
        try:
            state = VerificationState(source["state"])
            basis = AttributionBasisV2(source["attribution_basis"])
        except TypeError, ValueError:
            _fail()
        return cls(
            state=state,
            attribution_basis=basis,
            input_sha256=cast(str | None, source["input_sha256"]),
        )

    def payload(self) -> dict[str, object]:
        return {
            "attribution_basis": self.attribution_basis.value,
            "input_sha256": self.input_sha256,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class CohortStatus:
    state: CohortMaturity
    verified_at_utc: str | None
    input_sha256: str | None

    def __post_init__(self) -> None:
        if type(self.state) is not CohortMaturity:
            _fail()
        if self.state is CohortMaturity.UNAVAILABLE:
            if self.verified_at_utc is not None or self.input_sha256 is not None:
                _fail()
            return
        if self.input_sha256 is None:
            _fail()
        _sha256(self.input_sha256)
        if self.state is CohortMaturity.MATURE:
            if self.verified_at_utc is None:
                _fail()
            _timestamp(self.verified_at_utc)
        elif self.verified_at_utc is not None:
            _fail()

    @classmethod
    def parse(cls, value: object) -> CohortStatus:
        source = _mapping(value)
        _keys(source, {"state", "verified_at_utc", "input_sha256"})
        try:
            state = CohortMaturity(source["state"])
        except TypeError, ValueError:
            _fail()
        return cls(
            state=state,
            verified_at_utc=cast(str | None, source["verified_at_utc"]),
            input_sha256=cast(str | None, source["input_sha256"]),
        )

    def payload(self) -> dict[str, object]:
        return {
            "input_sha256": self.input_sha256,
            "state": self.state.value,
            "verified_at_utc": self.verified_at_utc,
        }


@dataclass(frozen=True, slots=True)
class ArticleLearningObservation:
    observation_id: str
    observed_at_utc: str
    period: MeasurementPeriod
    program: str
    article: ContractArticle
    verification: EvidenceVerification
    cohort: CohortStatus
    metrics: Mapping[str, AggregateValue]

    def __post_init__(self) -> None:
        _strict_string(self.observation_id, maximum=128, pattern=_REFERENCE)
        observed = datetime.strptime(
            _timestamp(self.observed_at_utc), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        if (
            type(self.period) is not MeasurementPeriod
            or type(self.article) is not ContractArticle
            or type(self.verification) is not EvidenceVerification
            or type(self.cohort) is not CohortStatus
            or self.program != PROGRAM
            or set(self.metrics) != set(ARTICLE_METRIC_NAMES)
            or any(type(value) is not AggregateValue for value in self.metrics.values())
        ):
            _fail()
        if observed.date() < date.fromisoformat(self.period.end_exclusive_date):
            _fail()
        if self.cohort.verified_at_utc is not None:
            verified = datetime.strptime(
                self.cohort.verified_at_utc, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if verified > observed:
                _fail()
        self._validate_metric_relationships()

    def _validate_metric_relationships(self) -> None:
        search_impressions = self.metrics["search_impressions"]
        search_clicks = self.metrics["search_clicks"]
        if search_impressions.is_observed and search_clicks.is_observed:
            if cast(int, search_clicks.value) > cast(int, search_impressions.value):
                _fail()
        outcomes = tuple(
            self.metrics[name]
            for name in (
                "pending_outcomes",
                "confirmed_outcomes",
                "rejected_outcomes",
                "direct_confirmed_reward_jpy",
            )
        )
        evidence_hashes = {
            value.input_sha256
            for value in outcomes
            if value.state not in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}
        }
        if len(evidence_hashes) > 1:
            _fail()
        if evidence_hashes and self.verification.input_sha256 not in evidence_hashes:
            _fail()
        if self.cohort.state is CohortMaturity.MATURE:
            pending, confirmed, rejected, _ = outcomes
            if (
                self.verification.state is not VerificationState.VERIFIED
                or self.verification.attribution_basis
                is not AttributionBasisV2.OWNER_VERIFIED_DIRECT_AGGREGATE
                or not all(value.is_observed for value in outcomes)
                or pending.state is not ValueState.OBSERVED_ZERO
                or self.cohort.input_sha256 != self.verification.input_sha256
                or any(
                    value.input_sha256 != self.verification.input_sha256
                    for value in (pending, confirmed, rejected)
                )
            ):
                _fail()

    @classmethod
    def parse(
        cls, value: object, *, contract: MeasurementContract
    ) -> ArticleLearningObservation:
        source = _mapping(value)
        _keys(
            source,
            {
                "schema",
                "observation_id",
                "observed_at_utc",
                "period",
                "program",
                "article",
                "verification",
                "cohort",
                "metrics",
            },
        )
        if source["schema"] != ARTICLE_OBSERVATION_SCHEMA:
            _fail()
        article = ContractArticle.parse(source["article"])
        if article != contract.article_for_slot(article.slot):
            _fail()
        raw_metrics = _mapping(source["metrics"])
        _keys(raw_metrics, set(ARTICLE_METRIC_NAMES))
        return cls(
            observation_id=cast(str, source["observation_id"]),
            observed_at_utc=cast(str, source["observed_at_utc"]),
            period=MeasurementPeriod.parse(source["period"]),
            program=cast(str, source["program"]),
            article=article,
            verification=EvidenceVerification.parse(source["verification"]),
            cohort=CohortStatus.parse(source["cohort"]),
            metrics={
                name: AggregateValue.parse(raw_metrics[name])
                for name in ARTICLE_METRIC_NAMES
            },
        )

    def payload(self) -> dict[str, object]:
        return {
            "article": self.article.payload(),
            "cohort": self.cohort.payload(),
            "metrics": {
                name: self.metrics[name].payload() for name in ARTICLE_METRIC_NAMES
            },
            "observation_id": self.observation_id,
            "observed_at_utc": self.observed_at_utc,
            "period": self.period.payload(),
            "program": self.program,
            "schema": ARTICLE_OBSERVATION_SCHEMA,
            "verification": self.verification.payload(),
        }


@dataclass(frozen=True, slots=True)
class ProgramLearningObservation:
    observation_id: str
    observed_at_utc: str
    period: MeasurementPeriod
    program: str
    verification: EvidenceVerification
    cohort: CohortStatus
    unattributed_confirmed_reward_jpy: AggregateValue

    def __post_init__(self) -> None:
        _strict_string(self.observation_id, maximum=128, pattern=_REFERENCE)
        observed = datetime.strptime(
            _timestamp(self.observed_at_utc), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        if (
            type(self.period) is not MeasurementPeriod
            or self.program != PROGRAM
            or type(self.verification) is not EvidenceVerification
            or type(self.cohort) is not CohortStatus
            or type(self.unattributed_confirmed_reward_jpy) is not AggregateValue
            or observed.date() < date.fromisoformat(self.period.end_exclusive_date)
        ):
            _fail()
        if self.verification.state is VerificationState.VERIFIED:
            if (
                self.verification.attribution_basis
                is not AttributionBasisV2.UNATTRIBUTED_PROGRAM_TOTAL
                or self.unattributed_confirmed_reward_jpy.input_sha256
                != self.verification.input_sha256
            ):
                _fail()
        if self.cohort.state is CohortMaturity.MATURE:
            if (
                self.verification.state is not VerificationState.VERIFIED
                or self.cohort.input_sha256 != self.verification.input_sha256
                or self.cohort.verified_at_utc is None
            ):
                _fail()
            verified = datetime.strptime(
                self.cohort.verified_at_utc, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if verified > observed:
                _fail()

    @classmethod
    def parse(cls, value: object) -> ProgramLearningObservation:
        source = _mapping(value)
        _keys(
            source,
            {
                "schema",
                "observation_id",
                "observed_at_utc",
                "period",
                "program",
                "verification",
                "cohort",
                "metrics",
            },
        )
        if source["schema"] != PROGRAM_OBSERVATION_SCHEMA:
            _fail()
        metrics = _mapping(source["metrics"])
        _keys(metrics, {"unattributed_confirmed_reward_jpy"})
        return cls(
            observation_id=cast(str, source["observation_id"]),
            observed_at_utc=cast(str, source["observed_at_utc"]),
            period=MeasurementPeriod.parse(source["period"]),
            program=cast(str, source["program"]),
            verification=EvidenceVerification.parse(source["verification"]),
            cohort=CohortStatus.parse(source["cohort"]),
            unattributed_confirmed_reward_jpy=AggregateValue.parse(
                metrics["unattributed_confirmed_reward_jpy"]
            ),
        )

    def payload(self) -> dict[str, object]:
        return {
            "cohort": self.cohort.payload(),
            "metrics": {
                "unattributed_confirmed_reward_jpy": self.unattributed_confirmed_reward_jpy.payload()
            },
            "observation_id": self.observation_id,
            "observed_at_utc": self.observed_at_utc,
            "period": self.period.payload(),
            "program": self.program,
            "schema": PROGRAM_OBSERVATION_SCHEMA,
            "verification": self.verification.payload(),
        }


LearningObservation = ArticleLearningObservation | ProgramLearningObservation


def parse_observation(
    value: object, *, contract: MeasurementContract
) -> LearningObservation:
    source = _mapping(value)
    schema = source.get("schema")
    if schema == ARTICLE_OBSERVATION_SCHEMA:
        return ArticleLearningObservation.parse(value, contract=contract)
    if schema == PROGRAM_OBSERVATION_SCHEMA:
        return ProgramLearningObservation.parse(value)
    _fail()


@dataclass(frozen=True, slots=True)
class LearningLedgerEvent:
    sequence: int
    previous_event_sha256: str
    observation_sha256: str
    event_sha256: str
    observation: LearningObservation

    def payload(self) -> dict[str, object]:
        return {
            "event_sha256": self.event_sha256,
            "observation": self.observation.payload(),
            "observation_sha256": self.observation_sha256,
            "previous_event_sha256": self.previous_event_sha256,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class AffiliateLearningLedger:
    contract_sha256: str
    events: tuple[LearningLedgerEvent, ...]

    def __post_init__(self) -> None:
        _sha256(self.contract_sha256)
        if type(self.events) is not tuple or any(
            type(event) is not LearningLedgerEvent for event in self.events
        ):
            _fail()

    @property
    def head_sha256(self) -> str:
        return self.events[-1].event_sha256 if self.events else GENESIS_SHA256

    def payload(self) -> dict[str, object]:
        return {
            "contract_sha256": self.contract_sha256,
            "events": [event.payload() for event in self.events],
            "head_sha256": self.head_sha256,
            "program": PROGRAM,
            "schema": LEDGER_SCHEMA,
        }


def empty_ledger(contract: MeasurementContract) -> AffiliateLearningLedger:
    if type(contract) is not MeasurementContract:
        _fail()
    return AffiliateLearningLedger(contract_sha256=contract.sha256, events=())


def parse_ledger(
    value: object, *, contract: MeasurementContract
) -> AffiliateLearningLedger:
    source = _mapping(value)
    _keys(
        source,
        {"schema", "program", "contract_sha256", "events", "head_sha256"},
    )
    if (
        source["schema"] != LEDGER_SCHEMA
        or source["program"] != PROGRAM
        or source["contract_sha256"] != contract.sha256
    ):
        _fail(PilotFailureCode.LEDGER_TAMPERED)
    raw_events = source["events"]
    if type(raw_events) is not list or len(raw_events) > 1000:
        _fail(PilotFailureCode.LEDGER_TAMPERED)
    events: list[LearningLedgerEvent] = []
    previous = GENESIS_SHA256
    ids: set[str] = set()
    for sequence, raw_event in enumerate(cast(list[object], raw_events), 1):
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
        observation = parse_observation(event["observation"], contract=contract)
        if observation.observation_id in ids:
            _fail(PilotFailureCode.LEDGER_TAMPERED)
        ids.add(observation.observation_id)
        observation_sha256 = digest(observation.payload())
        event_sha256 = digest(
            {
                "observation": observation.payload(),
                "observation_sha256": observation_sha256,
                "previous_event_sha256": previous,
                "sequence": sequence,
            }
        )
        if (
            type(event["sequence"]) is not int
            or event["sequence"] != sequence
            or event["previous_event_sha256"] != previous
            or event["observation_sha256"] != observation_sha256
            or event["event_sha256"] != event_sha256
        ):
            _fail(PilotFailureCode.LEDGER_TAMPERED)
        events.append(
            LearningLedgerEvent(
                sequence=sequence,
                previous_event_sha256=previous,
                observation_sha256=observation_sha256,
                event_sha256=event_sha256,
                observation=observation,
            )
        )
        previous = event_sha256
    if source["head_sha256"] != previous:
        _fail(PilotFailureCode.LEDGER_TAMPERED)
    return AffiliateLearningLedger(
        contract_sha256=contract.sha256, events=tuple(events)
    )


def append_observation(
    ledger: AffiliateLearningLedger,
    observation: LearningObservation,
    *,
    contract: MeasurementContract,
) -> tuple[AffiliateLearningLedger, AppendDisposition, str]:
    if (
        type(ledger) is not AffiliateLearningLedger
        or type(observation)
        not in {ArticleLearningObservation, ProgramLearningObservation}
        or ledger.contract_sha256 != contract.sha256
        or len(ledger.events) >= 1000
    ):
        _fail()
    for event in ledger.events:
        if event.observation.observation_id != observation.observation_id:
            continue
        if event.observation.payload() != observation.payload():
            _fail(PilotFailureCode.OBSERVATION_ID_CONFLICT)
        return ledger, AppendDisposition.REPLAYED, event.event_sha256
    sequence = len(ledger.events) + 1
    previous = ledger.head_sha256
    observation_sha256 = digest(observation.payload())
    event_sha256 = digest(
        {
            "observation": observation.payload(),
            "observation_sha256": observation_sha256,
            "previous_event_sha256": previous,
            "sequence": sequence,
        }
    )
    event = LearningLedgerEvent(
        sequence=sequence,
        previous_event_sha256=previous,
        observation_sha256=observation_sha256,
        event_sha256=event_sha256,
        observation=observation,
    )
    return (
        AffiliateLearningLedger(
            contract_sha256=contract.sha256, events=ledger.events + (event,)
        ),
        AppendDisposition.APPENDED,
        event_sha256,
    )


@dataclass(frozen=True, slots=True)
class DerivedMetric:
    state: MetricResultState
    unavailable_reason: MetricUnavailableReason | None
    numerator: int | None
    denominator: int | None
    value_decimal: str | None
    unit: str
    basis: str

    def payload(self) -> dict[str, object]:
        return {
            "basis": self.basis,
            "denominator": self.denominator,
            "numerator": self.numerator,
            "state": self.state.value,
            "unavailable_reason": (
                self.unavailable_reason.value
                if self.unavailable_reason is not None
                else None
            ),
            "unit": self.unit,
            "value_decimal": self.value_decimal,
        }


def _unavailable(reason: MetricUnavailableReason, *, unit: str) -> DerivedMetric:
    return DerivedMetric(
        state=MetricResultState.UNAVAILABLE,
        unavailable_reason=reason,
        numerator=None,
        denominator=None,
        value_decimal=None,
        unit=unit,
        basis="DIRECT_CONFIRMED_REWARD_ONLY_UNATTRIBUTED_EXCLUDED",
    )


def _ratio(numerator: int, denominator: int, *, unit: str) -> DerivedMetric:
    if denominator == 0:
        return _unavailable(MetricUnavailableReason.ZERO_DENOMINATOR, unit=unit)
    with localcontext() as context:
        context.prec = 50
        value = (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
    return DerivedMetric(
        state=MetricResultState.AVAILABLE,
        unavailable_reason=None,
        numerator=numerator,
        denominator=denominator,
        value_decimal=f"{value:.6f}",
        unit=unit,
        basis="DIRECT_CONFIRMED_REWARD_ONLY_UNATTRIBUTED_EXCLUDED",
    )


def _observed_total(
    observations: Sequence[ArticleLearningObservation], name: str
) -> tuple[int | None, MetricUnavailableReason | None]:
    values = [observation.metrics[name] for observation in observations]
    if any(value.state is ValueState.UNVERIFIED for value in values):
        return None, MetricUnavailableReason.UNVERIFIED_INPUT
    if any(not value.is_observed for value in values):
        return None, MetricUnavailableReason.MISSING_INPUT
    return sum(cast(int, value.value) for value in values), None


def calculate_metrics(
    observations: Sequence[ArticleLearningObservation],
    *,
    require_five_slots: bool,
) -> dict[str, DerivedMetric]:
    rows = tuple(observations)
    if require_five_slots and (
        len(rows) != 5 or {row.article.slot for row in rows} != {1, 2, 3, 4, 5}
    ):
        reason = MetricUnavailableReason.MISSING_ARTICLE_SLOTS
    elif len({row.program for row in rows}) != 1 or any(
        row.program != PROGRAM for row in rows
    ):
        reason = MetricUnavailableReason.PROGRAM_MISMATCH
    elif (
        len({(row.period.start_date, row.period.end_exclusive_date) for row in rows})
        != 1
    ):
        reason = MetricUnavailableReason.PERIOD_MISMATCH
    elif any(row.verification.state is not VerificationState.VERIFIED for row in rows):
        reason = MetricUnavailableReason.UNVERIFIED_INPUT
    elif any(row.cohort.state is not CohortMaturity.MATURE for row in rows):
        reason = MetricUnavailableReason.COHORT_IMMATURE
    else:
        reason = None
    units = {
        "search_ctr": "RATIO",
        "affiliate_click_rate": "RATIO",
        "confirmed_reward_per_click_jpy": "JPY_PER_CLICK",
        "confirmation_rate": "RATIO",
        "confirmed_reward_per_content_hour_jpy": "JPY_PER_CONTENT_HOUR",
    }
    if reason is not None:
        return {name: _unavailable(reason, unit=units[name]) for name in units}

    totals: dict[str, int] = {}
    missing: dict[str, MetricUnavailableReason] = {}
    for name in ARTICLE_METRIC_NAMES:
        total, unavailable_reason = _observed_total(rows, name)
        if total is None:
            missing[name] = cast(MetricUnavailableReason, unavailable_reason)
        else:
            totals[name] = total

    def compute(
        metric_name: str,
        *,
        numerator_name: str,
        denominator_names: tuple[str, ...],
        numerator_multiplier: int = 1,
    ) -> DerivedMetric:
        dependencies = (numerator_name, *denominator_names)
        for dependency in dependencies:
            if dependency in missing:
                return _unavailable(missing[dependency], unit=units[metric_name])
        numerator = totals[numerator_name] * numerator_multiplier
        denominator = sum(totals[name] for name in denominator_names)
        return _ratio(numerator, denominator, unit=units[metric_name])

    pending = totals.get("pending_outcomes")
    if pending is not None and pending != 0:
        confirmation = _unavailable(
            MetricUnavailableReason.COHORT_IMMATURE,
            unit=units["confirmation_rate"],
        )
    else:
        confirmation = compute(
            "confirmation_rate",
            numerator_name="confirmed_outcomes",
            denominator_names=("confirmed_outcomes", "rejected_outcomes"),
        )
    return {
        "affiliate_click_rate": compute(
            "affiliate_click_rate",
            numerator_name="affiliate_clicks",
            denominator_names=("article_views",),
        ),
        "confirmation_rate": confirmation,
        "confirmed_reward_per_click_jpy": compute(
            "confirmed_reward_per_click_jpy",
            numerator_name="direct_confirmed_reward_jpy",
            denominator_names=("affiliate_clicks",),
        ),
        "confirmed_reward_per_content_hour_jpy": compute(
            "confirmed_reward_per_content_hour_jpy",
            numerator_name="direct_confirmed_reward_jpy",
            denominator_names=("work_minutes",),
            numerator_multiplier=60,
        ),
        "search_ctr": compute(
            "search_ctr",
            numerator_name="search_clicks",
            denominator_names=("search_impressions",),
        ),
    }


def _article_candidates(observation: ArticleLearningObservation) -> list[str]:
    candidates: set[str] = set()
    if any(
        value.state
        in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE, ValueState.UNVERIFIED}
        for value in observation.metrics.values()
    ):
        candidates.add("COLLECT_VERIFIED_BASELINE")
    broken_links = observation.metrics["broken_links"]
    if broken_links.is_observed and cast(int, broken_links.value) > 0:
        candidates.add("REVIEW_BROKEN_LINKS")
    impressions = observation.metrics["search_impressions"]
    search_clicks = observation.metrics["search_clicks"]
    if (
        impressions.is_observed
        and cast(int, impressions.value) > 0
        and search_clicks.state is ValueState.OBSERVED_ZERO
    ):
        candidates.add("REVIEW_SEARCH_DISCOVERABILITY")
    views = observation.metrics["article_views"]
    affiliate_clicks = observation.metrics["affiliate_clicks"]
    if (
        views.is_observed
        and cast(int, views.value) > 0
        and affiliate_clicks.state is ValueState.OBSERVED_ZERO
    ):
        candidates.add("REVIEW_AFFILIATE_PRESENTATION")
    confirmed = observation.metrics["confirmed_outcomes"]
    rejected = observation.metrics["rejected_outcomes"]
    if (
        observation.cohort.state is CohortMaturity.MATURE
        and confirmed.state is ValueState.OBSERVED_ZERO
        and rejected.is_observed
        and cast(int, rejected.value) > 0
    ):
        candidates.add("REVIEW_AUDIENCE_PRODUCT_FIT")
    return sorted(candidates)


def build_learning_report(
    ledger: AffiliateLearningLedger, *, contract: MeasurementContract
) -> dict[str, object]:
    if (
        type(ledger) is not AffiliateLearningLedger
        or ledger.contract_sha256 != contract.sha256
    ):
        _fail()
    latest_articles: dict[int, ArticleLearningObservation] = {}
    latest_program: ProgramLearningObservation | None = None
    for event in ledger.events:
        observation = event.observation
        if type(observation) is ArticleLearningObservation:
            latest_articles[observation.article.slot] = observation
        elif type(observation) is ProgramLearningObservation:
            latest_program = observation
        else:
            _fail(PilotFailureCode.LEDGER_TAMPERED)
    ordered = tuple(latest_articles[slot] for slot in sorted(latest_articles))
    article_reports: list[dict[str, object]] = []
    proposal_candidates: list[dict[str, object]] = []
    for observation in ordered:
        candidates = _article_candidates(observation)
        proposal_candidates.extend(
            {"article_id": observation.article.article_id, "candidate": candidate}
            for candidate in candidates
        )
        article_reports.append(
            {
                "article": observation.article.payload(),
                "cohort": observation.cohort.payload(),
                "derived_metrics": {
                    name: metric.payload()
                    for name, metric in sorted(
                        calculate_metrics(
                            (observation,), require_five_slots=False
                        ).items()
                    )
                },
                "metrics": {
                    name: observation.metrics[name].payload()
                    for name in ARTICLE_METRIC_NAMES
                },
                "observation_id": observation.observation_id,
                "observed_at_utc": observation.observed_at_utc,
                "period": observation.period.payload(),
                "program": observation.program,
                "verification": observation.verification.payload(),
            }
        )
    portfolio = calculate_metrics(ordered, require_five_slots=True)
    incomplete = len(ordered) != 5 or any(
        metric.state is MetricResultState.UNAVAILABLE for metric in portfolio.values()
    )
    return {
        "articles": article_reports,
        "authority": "OWNER_PRIVATE_SANITIZED_AGGREGATES_PROPOSAL_ONLY",
        "boundaries": {
            "analytics_activation": "NOT_EXECUTED",
            "article_html_mutation": False,
            "automatic_publication": False,
            "cta_mutation": False,
            "live_provider_calls": 0,
            "network_requests": 0,
            "product_selection_mutation": False,
            "publication_actions": 0,
            "publication_snapshot_mutation": False,
            "recommendation_order_mutation": False,
            "tracking_activation": "DISABLED_OD_012",
        },
        "contract_sha256": contract.sha256,
        "decision": (
            "INSUFFICIENT_EVIDENCE" if incomplete else "REVIEW_CANDIDATES_ONLY"
        ),
        "event_count": len(ledger.events),
        "head_sha256": ledger.head_sha256,
        "portfolio_metrics": {
            name: metric.payload() for name, metric in sorted(portfolio.items())
        },
        "program": PROGRAM,
        "program_unattributed_reward": (
            {
                "allocation_to_articles": "FORBIDDEN",
                "cohort": latest_program.cohort.payload(),
                "metric": latest_program.unattributed_confirmed_reward_jpy.payload(),
                "observation_id": latest_program.observation_id,
                "period": latest_program.period.payload(),
                "verification": latest_program.verification.payload(),
            }
            if latest_program is not None
            else {
                "allocation_to_articles": "FORBIDDEN",
                "cohort": None,
                "metric": AggregateValue(
                    state=ValueState.NOT_OBSERVED,
                    value=None,
                    input_sha256=None,
                ).payload(),
                "observation_id": None,
                "period": None,
                "verification": None,
            }
        ),
        "proposal_candidates": sorted(
            proposal_candidates,
            key=lambda item: (
                cast(str, item["article_id"]),
                cast(str, item["candidate"]),
            ),
        ),
        "recommendation_input_policy": {
            "excluded": ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"],
            "finance_may_change_recommendation_order": False,
        },
        "schema": REPORT_SCHEMA,
        "slot_count": len(ordered),
        "status": {
            "ST-1704": "LOCAL_IMPLEMENTATION_EVIDENCE_ONLY",
            "TST-018": "NOT_EXECUTED",
            "TST-020": "NOT_EXECUTED",
            "TST-032": "NOT_EXECUTED",
            "production": "NOT_READY",
        },
    }


__all__ = [
    "ARTICLE_METRIC_NAMES",
    "ARTICLE_OBSERVATION_SCHEMA",
    "AffiliateLearningLedger",
    "AggregateValue",
    "AppendDisposition",
    "ArticleLearningObservation",
    "AttributionBasisV2",
    "CONTRACT_SCHEMA",
    "CohortMaturity",
    "CohortStatus",
    "ContractArticle",
    "DERIVED_METRIC_NAMES",
    "DerivedMetric",
    "EvidenceVerification",
    "LEDGER_SCHEMA",
    "LearningLedgerEvent",
    "LearningObservation",
    "MeasurementContract",
    "MeasurementPeriod",
    "MetricResultState",
    "MetricUnavailableReason",
    "PROGRAM",
    "PROGRAM_OBSERVATION_SCHEMA",
    "ProgramLearningObservation",
    "REPORT_SCHEMA",
    "VerificationState",
    "append_observation",
    "build_learning_report",
    "calculate_metrics",
    "empty_ledger",
    "parse_ledger",
    "parse_observation",
]
