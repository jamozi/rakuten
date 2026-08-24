"""Provider-neutral values for the disabled ST-1905 adapter seam.

The module models only a sanitized, recorded provider response mapped into the
ST-1206 canonical keyword-rank value types.  It deliberately has no endpoint,
credential, provider SDK, activation, persistence, publication, or arbitrary
metadata type.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.analytics.keyword_rank import (
    KeywordRankMetricCount,
    KeywordRankMetricType,
    KeywordRankObservation,
    KeywordRankPeriod,
    Sha256Digest,
)


ADVANCED_RANK_PROVIDER_CONTRACT_VERSION: Final = "1.0.0"
ADVANCED_RANK_PROVIDER_PARSER_VERSION: Final = (
    "st1905-recorded-provider-response-json.v1"
)
ADVANCED_RANK_PROVIDER_ADAPTER_VERSION: Final = "st1905-provider-neutral-adapter.v1"
SYNTHETIC_PROVIDER_PROFILE: Final = "RAOS_ST1905_SYNTHETIC_PROVIDER_V1"
SYNTHETIC_PROVIDER_CODE: Final = "RAOS_ST1905_SYNTHETIC"
MAX_PROVIDER_SOURCE_BYTES: Final = 1_048_576
MAX_PROVIDER_OBSERVATIONS: Final = 10_000

_REDACTED: Final = "<redacted-advanced-rank-provider>"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class AdvancedRankProviderScope(str, Enum):
    """Closed local states; no selected-provider or live-enabled member exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY = (
        "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY"
    )


DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE: Final = AdvancedRankProviderScope.DISABLED


class AdvancedRankProviderSourceKind(str, Enum):
    RECORDED_SYNTHETIC_PROVIDER_RESPONSE = "RECORDED_SYNTHETIC_PROVIDER_RESPONSE"


class AdvancedRankProviderOutcome(str, Enum):
    CONTRACT_COMPATIBLE_RECORDED_ONLY = "CONTRACT_COMPATIBLE_RECORDED_ONLY"


class AdvancedRankProviderBoundaryStatus(str, Enum):
    ABSENT = "ABSENT"
    DISABLED = "DISABLED"
    FORBIDDEN = "FORBIDDEN"
    HUMAN_DECISION_REQUIRED = "HUMAN_DECISION_REQUIRED"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    RELEASE_DECISION_REQUIRED = "RELEASE_DECISION_REQUIRED"
    DEFERRED_POST_MVP = "DEFERRED_POST_MVP"


class AdvancedRankProviderFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    PROVIDER_APPROVAL_PROHIBITED = "PROVIDER_APPROVAL_PROHIBITED"
    RELEASE_DECISION_PROHIBITED = "RELEASE_DECISION_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DUPLICATE_PROVIDER_OBSERVATION = "DUPLICATE_PROVIDER_OBSERVATION"
    DUPLICATE_CANONICAL_OBSERVATION = "DUPLICATE_CANONICAL_OBSERVATION"
    OBSERVATION_OUT_OF_PERIOD = "OBSERVATION_OUT_OF_PERIOD"
    DEPENDENCY_CONTRACT_DRIFT = "DEPENDENCY_CONTRACT_DRIFT"


class AdvancedRankProviderFailure(ValueError):
    """Closed failure that never retains rejected provider material."""

    __slots__ = ("code",)

    def __init__(self, code: AdvancedRankProviderFailureCode) -> None:
        if type(code) is not AdvancedRankProviderFailureCode:
            raise TypeError("invalid advanced rank provider failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"AdvancedRankProviderFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("advanced rank provider failures cannot be serialized")


def fail_advanced_rank_provider(
    code: AdvancedRankProviderFailureCode = (
        AdvancedRankProviderFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise AdvancedRankProviderFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("advanced rank provider values cannot be serialized")


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_advanced_rank_provider()


def _identifier(value: object) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        fail_advanced_rank_provider()
    return value


def _recording_id(value: object) -> str:
    if type(value) is not str or _RECORDING_ID.fullmatch(value) is None:
        fail_advanced_rank_provider()
    return value


def _nonzero_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_advanced_rank_provider()
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_advanced_rank_provider()
    return value


def _digest(value: object) -> Sha256Digest:
    if (
        type(value) is not Sha256Digest
        or type(value.value) is not str
        or _SHA256.fullmatch(value.value) is None
    ):
        fail_advanced_rank_provider()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class AdvancedRankProviderCommand(_RedactedValue):
    """One hash-bound request for local recorded contract evaluation."""

    recording_id: str
    site_id: UUID
    source_sha256: Sha256Digest
    source_bytes: int
    period: KeywordRankPeriod
    provider_approval_sha256: Sha256Digest | None = None
    release_decision_sha256: Sha256Digest | None = None
    adapter_version: str = ADVANCED_RANK_PROVIDER_ADAPTER_VERSION
    parser_version: str = ADVANCED_RANK_PROVIDER_PARSER_VERSION
    scope: AdvancedRankProviderScope = DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        _nonzero_uuid(self.site_id)
        _digest(self.source_sha256)
        _bounded_int(
            self.source_bytes,
            minimum=1,
            maximum=MAX_PROVIDER_SOURCE_BYTES,
        )
        if (
            type(self.period) is not KeywordRankPeriod
            or type(self.adapter_version) is not str
            or self.adapter_version != ADVANCED_RANK_PROVIDER_ADAPTER_VERSION
            or type(self.parser_version) is not str
            or self.parser_version != ADVANCED_RANK_PROVIDER_PARSER_VERSION
            or type(self.scope) is not AdvancedRankProviderScope
        ):
            fail_advanced_rank_provider()
        if self.provider_approval_sha256 is not None:
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.PROVIDER_APPROVAL_PROHIBITED
            )
        if self.release_decision_sha256 is not None:
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.RELEASE_DECISION_PROHIBITED
            )

    @property
    def canonical_sha256(self) -> Sha256Digest:
        return Sha256Digest.of(
            canonical_json_bytes(
                {
                    "adapter_version": self.adapter_version,
                    "parser_version": self.parser_version,
                    "period": {
                        "date_from": self.period.date_from.isoformat(),
                        "date_to": self.period.date_to.isoformat(),
                    },
                    "provider_approval_sha256": None,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "scope": self.scope.value,
                    "site_id": str(self.site_id),
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256.value,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdvancedRankObservation(_RedactedValue):
    """One sanitized provider-row identity plus one ST-1206 canonical row."""

    provider_observation_id: str
    observation: KeywordRankObservation

    def __post_init__(self) -> None:
        if (
            _identifier(self.provider_observation_id) != self.provider_observation_id
            or type(self.observation) is not KeywordRankObservation
            or self.observation.provider_code != SYNTHETIC_PROVIDER_CODE
        ):
            fail_advanced_rank_provider()


def observation_projection(row: RecordedAdvancedRankObservation) -> dict[str, object]:
    if type(row) is not RecordedAdvancedRankObservation:
        fail_advanced_rank_provider()
    return {
        "canonical_observation": row.observation.canonical_document(),
        "provider_observation_id": row.provider_observation_id,
    }


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAdvancedRankBatch(_RedactedValue):
    recording_id: str
    site_id: UUID
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int
    source_kind: AdvancedRankProviderSourceKind
    fixture_profile: str
    parser_version: str
    adapter_version: str
    observations: tuple[RecordedAdvancedRankObservation, ...]

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        _nonzero_uuid(self.site_id)
        _digest(self.command_sha256)
        _digest(self.source_sha256)
        _bounded_int(
            self.source_bytes,
            minimum=1,
            maximum=MAX_PROVIDER_SOURCE_BYTES,
        )
        if (
            self.source_kind
            is not AdvancedRankProviderSourceKind.RECORDED_SYNTHETIC_PROVIDER_RESPONSE
            or self.fixture_profile != SYNTHETIC_PROVIDER_PROFILE
            or self.parser_version != ADVANCED_RANK_PROVIDER_PARSER_VERSION
            or self.adapter_version != ADVANCED_RANK_PROVIDER_ADAPTER_VERSION
            or type(self.observations) is not tuple
            or not 1 <= len(self.observations) <= MAX_PROVIDER_OBSERVATIONS
            or any(
                type(row) is not RecordedAdvancedRankObservation
                for row in self.observations
            )
        ):
            fail_advanced_rank_provider()
        provider_ids = tuple(row.provider_observation_id for row in self.observations)
        if len(set(provider_ids)) != len(provider_ids):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.DUPLICATE_PROVIDER_OBSERVATION
            )
        canonical_ids = tuple(row.observation.identity for row in self.observations)
        if len(set(canonical_ids)) != len(canonical_ids):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.DUPLICATE_CANONICAL_OBSERVATION
            )

    @property
    def normalized_sha256(self) -> Sha256Digest:
        rows = sorted(
            (observation_projection(row) for row in self.observations),
            key=lambda row: str(row["provider_observation_id"]),
        )
        return Sha256Digest.of(canonical_json_bytes(rows))


@dataclass(frozen=True, slots=True, repr=False)
class AdvancedRankProviderReport(_RedactedValue):
    recording_id: str
    site_id: UUID
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    normalized_sha256: Sha256Digest
    row_count: int
    unique_keyword_count: int
    metric_counts: tuple[KeywordRankMetricCount, ...]
    observation_from: date
    observation_to: date
    outcome: AdvancedRankProviderOutcome
    blockers: tuple[str, ...]
    report_sha256: Sha256Digest
    scope: AdvancedRankProviderScope
    default_scope: AdvancedRankProviderScope = DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE
    authority: str = "NONE"
    provider_selection: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    provider_approval: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.ABSENT
    )
    release_decision: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.RELEASE_DECISION_REQUIRED
    )
    adapter_activation: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.DISABLED
    )
    provider_call: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    )
    network: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.FORBIDDEN
    )
    credentials: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_USED
    )
    persistence: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    )
    serp_scrape: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.FORBIDDEN
    )
    kpi_read_model_write: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    )
    tracking_activation: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.DISABLED
    )
    recommendation_input: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.DISABLED
    )
    publication: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.FORBIDDEN
    )
    formal_tst_032: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    )
    canonical_status: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.DEFERRED_POST_MVP
    )
    production: AdvancedRankProviderBoundaryStatus = (
        AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
    )

    def require_valid(self) -> None:
        _recording_id(self.recording_id)
        _nonzero_uuid(self.site_id)
        for digest in (
            self.command_sha256,
            self.source_sha256,
            self.normalized_sha256,
            self.report_sha256,
        ):
            _digest(digest)
        expected_order = tuple(KeywordRankMetricType)
        if (
            type(self.metric_counts) is not tuple
            or tuple(row.metric_type for row in self.metric_counts) != expected_order
            or any(
                type(row) is not KeywordRankMetricCount for row in self.metric_counts
            )
            or type(self.observation_from) is not date
            or type(self.observation_to) is not date
            or self.observation_from > self.observation_to
            or self.outcome
            is not AdvancedRankProviderOutcome.CONTRACT_COMPATIBLE_RECORDED_ONLY
            or type(self.blockers) is not tuple
            or self.blockers != tuple(sorted(set(self.blockers)))
            or any(_identifier(blocker) != blocker for blocker in self.blockers)
            or self.scope
            is not AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
            or self.default_scope is not AdvancedRankProviderScope.DISABLED
            or self.authority != "NONE"
            or self.provider_selection
            is not AdvancedRankProviderBoundaryStatus.HUMAN_DECISION_REQUIRED
            or self.provider_approval is not AdvancedRankProviderBoundaryStatus.ABSENT
            or self.release_decision
            is not AdvancedRankProviderBoundaryStatus.RELEASE_DECISION_REQUIRED
            or self.adapter_activation
            is not AdvancedRankProviderBoundaryStatus.DISABLED
            or self.provider_call is not AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
            or self.network is not AdvancedRankProviderBoundaryStatus.FORBIDDEN
            or self.credentials is not AdvancedRankProviderBoundaryStatus.NOT_USED
            or self.persistence is not AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
            or self.serp_scrape is not AdvancedRankProviderBoundaryStatus.FORBIDDEN
            or self.kpi_read_model_write
            is not AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
            or self.tracking_activation
            is not AdvancedRankProviderBoundaryStatus.DISABLED
            or self.recommendation_input
            is not AdvancedRankProviderBoundaryStatus.DISABLED
            or self.publication is not AdvancedRankProviderBoundaryStatus.FORBIDDEN
            or self.formal_tst_032
            is not AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
            or self.canonical_status
            is not AdvancedRankProviderBoundaryStatus.DEFERRED_POST_MVP
            or self.production is not AdvancedRankProviderBoundaryStatus.NOT_EXECUTED
        ):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
            )
        _bounded_int(self.row_count, minimum=1, maximum=MAX_PROVIDER_OBSERVATIONS)
        _bounded_int(
            self.unique_keyword_count,
            minimum=1,
            maximum=MAX_PROVIDER_OBSERVATIONS,
        )
        if (
            self.unique_keyword_count > self.row_count
            or sum(row.count for row in self.metric_counts) != self.row_count
            or self.report_sha256
            != Sha256Digest.of(canonical_json_bytes(_report_projection_unchecked(self)))
        ):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
            )


def _report_projection_unchecked(
    report: AdvancedRankProviderReport,
) -> dict[str, object]:
    return {
        "authority": report.authority,
        "blockers": list(report.blockers),
        "boundary": {
            "adapter_activation": report.adapter_activation.value,
            "canonical_status": report.canonical_status.value,
            "credentials": report.credentials.value,
            "formal_tst_032": report.formal_tst_032.value,
            "kpi_read_model_write": report.kpi_read_model_write.value,
            "network": report.network.value,
            "persistence": report.persistence.value,
            "production": report.production.value,
            "provider_approval": report.provider_approval.value,
            "provider_call": report.provider_call.value,
            "provider_selection": report.provider_selection.value,
            "publication": report.publication.value,
            "recommendation_input": report.recommendation_input.value,
            "release_decision": report.release_decision.value,
            "serp_scrape": report.serp_scrape.value,
            "tracking_activation": report.tracking_activation.value,
        },
        "command_sha256": report.command_sha256.value,
        "metrics": {
            "metric_counts": {
                row.metric_type.value: row.count for row in report.metric_counts
            },
            "observation_from": report.observation_from.isoformat(),
            "observation_to": report.observation_to.isoformat(),
            "row_count": report.row_count,
            "unique_keyword_count": report.unique_keyword_count,
        },
        "normalized_sha256": report.normalized_sha256.value,
        "outcome": report.outcome.value,
        "recording_id": report.recording_id,
        "scope": report.scope.value,
        "site_id": str(report.site_id),
        "source_sha256": report.source_sha256.value,
    }


def report_projection(report: AdvancedRankProviderReport) -> dict[str, object]:
    if type(report) is not AdvancedRankProviderReport:
        fail_advanced_rank_provider()
    report.require_valid()
    return _report_projection_unchecked(report)


def finalize_report(report: AdvancedRankProviderReport) -> AdvancedRankProviderReport:
    if type(report) is not AdvancedRankProviderReport:
        fail_advanced_rank_provider()
    finalized = replace(
        report,
        report_sha256=Sha256Digest.of(
            canonical_json_bytes(_report_projection_unchecked(report))
        ),
    )
    finalized.require_valid()
    return finalized


def evaluate_recorded_provider(
    command: AdvancedRankProviderCommand,
    batch: RecordedAdvancedRankBatch,
) -> AdvancedRankProviderReport:
    """Evaluate mapping compatibility without activating or calling a provider."""

    if (
        type(command) is not AdvancedRankProviderCommand
        or type(batch) is not RecordedAdvancedRankBatch
    ):
        fail_advanced_rank_provider()
    if (
        command.scope
        is not AdvancedRankProviderScope.RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY
    ):
        fail_advanced_rank_provider(AdvancedRankProviderFailureCode.FEATURE_DISABLED)
    if (
        batch.recording_id != command.recording_id
        or batch.site_id != command.site_id
        or batch.command_sha256 != command.canonical_sha256
        or batch.source_sha256 != command.source_sha256
        or batch.source_bytes != command.source_bytes
        or batch.parser_version != command.parser_version
        or batch.adapter_version != command.adapter_version
    ):
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.SOURCE_RESULT_INVALID
        )
    for row in batch.observations:
        if not (
            command.period.date_from
            <= row.observation.observation_date
            <= command.period.date_to
        ):
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.OBSERVATION_OUT_OF_PERIOD
            )

    counts = tuple(
        KeywordRankMetricCount(
            metric_type=metric,
            count=sum(
                row.observation.metric_type is metric for row in batch.observations
            ),
        )
        for metric in KeywordRankMetricType
    )
    dates = tuple(row.observation.observation_date for row in batch.observations)
    blockers = tuple(
        sorted(
            {
                "FORMAL_TST_032_NOT_EXECUTED",
                "LIVE_PROVIDER_VALIDATION_NOT_EXECUTED",
                "OD_004_PROVIDER_SELECTION_UNRESOLVED",
                "PROVIDER_APPROVAL_ABSENT",
                "RECORDED_SYNTHETIC_ONLY",
                "RELEASE_DECISION_ABSENT",
            }
        )
    )
    provisional = AdvancedRankProviderReport(
        recording_id=command.recording_id,
        site_id=command.site_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        normalized_sha256=batch.normalized_sha256,
        row_count=len(batch.observations),
        unique_keyword_count=len(
            {row.observation.keyword_id for row in batch.observations}
        ),
        metric_counts=counts,
        observation_from=min(dates),
        observation_to=max(dates),
        outcome=AdvancedRankProviderOutcome.CONTRACT_COMPATIBLE_RECORDED_ONLY,
        blockers=blockers,
        report_sha256=Sha256Digest(hashlib.sha256(b"").hexdigest()),
        scope=command.scope,
    )
    return finalize_report(provisional)


__all__ = [
    "ADVANCED_RANK_PROVIDER_ADAPTER_VERSION",
    "ADVANCED_RANK_PROVIDER_CONTRACT_VERSION",
    "ADVANCED_RANK_PROVIDER_PARSER_VERSION",
    "DEFAULT_ADVANCED_RANK_PROVIDER_SCOPE",
    "MAX_PROVIDER_OBSERVATIONS",
    "MAX_PROVIDER_SOURCE_BYTES",
    "SYNTHETIC_PROVIDER_CODE",
    "SYNTHETIC_PROVIDER_PROFILE",
    "AdvancedRankProviderBoundaryStatus",
    "AdvancedRankProviderCommand",
    "AdvancedRankProviderFailure",
    "AdvancedRankProviderFailureCode",
    "AdvancedRankProviderOutcome",
    "AdvancedRankProviderReport",
    "AdvancedRankProviderScope",
    "AdvancedRankProviderSourceKind",
    "RecordedAdvancedRankBatch",
    "RecordedAdvancedRankObservation",
    "canonical_json_bytes",
    "evaluate_recorded_provider",
    "fail_advanced_rank_provider",
    "finalize_report",
    "observation_projection",
    "report_projection",
]
