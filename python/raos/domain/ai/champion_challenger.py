"""Provider-neutral, non-authoritative ST-1902 shadow evaluation values.

The domain deliberately has no provider, publication, editorial, activation,
credential, network, persistence, or free-form content type.  A recorded
challenger can be compared with a recorded champion, but the only possible
operational result is to keep the champion.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex


SHADOW_CONTRACT_VERSION: Final = "1.0.0"
SHADOW_PARSER_VERSION: Final = "st1902-recorded-shadow-json.v1"
SYNTHETIC_SHADOW_PROFILE: Final = "RAOS_ST1902_SYNTHETIC_SHADOW_V1"
TARGET_TASK_CODE: Final = "ai.article_draft.v1"
TARGET_ROUTE_CODE: Final = "route.editorial_balanced.v1"
EXPECTED_ST0708_OUTCOME: Final = "REFUSED_INCOMPLETE_EVIDENCE"
MAX_SHADOW_SOURCE_BYTES: Final = 1_048_576
MAX_SHADOW_OBSERVATIONS: Final = 10_000
METRIC_SCALE: Final = 1_000_000

_REDACTED: Final = "<redacted-champion-challenger>"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class ChampionChallengerScope(str, Enum):
    """Closed feature states; there is no canary/live enabled member."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_SHADOW_ONLY = "RECORDED_SYNTHETIC_SHADOW_ONLY"


DEFAULT_CHAMPION_CHALLENGER_SCOPE: Final = ChampionChallengerScope.DISABLED


class ShadowOutcome(str, Enum):
    KEEP_CHAMPION_INCOMPLETE_EVIDENCE = "KEEP_CHAMPION_INCOMPLETE_EVIDENCE"
    KEEP_CHAMPION_SCHEMA_FAILURE = "KEEP_CHAMPION_SCHEMA_FAILURE"
    KEEP_CHAMPION_ZERO_TOLERANCE = "KEEP_CHAMPION_ZERO_TOLERANCE"


class ChallengerState(str, Enum):
    SHADOW_NONAUTHORITATIVE = "SHADOW_NONAUTHORITATIVE"
    PAUSED_RECORDED_ONLY = "PAUSED_RECORDED_ONLY"


class ShadowBoundaryStatus(str, Enum):
    DISABLED = "DISABLED"
    FORBIDDEN = "FORBIDDEN"
    NONE = "NONE"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_USED = "NOT_USED"
    DEFERRED_POST_MVP = "DEFERRED_POST_MVP"
    RELEASE_DECISION_REQUIRED = "RELEASE_DECISION_REQUIRED"


class ShadowRoutingFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    CANARY_ALLOCATION_PROHIBITED = "CANARY_ALLOCATION_PROHIBITED"
    RELEASE_DECISION_PROHIBITED = "RELEASE_DECISION_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DUPLICATE_COHORT_MEMBER = "DUPLICATE_COHORT_MEMBER"
    DEPENDENCY_EVIDENCE_DRIFT = "DEPENDENCY_EVIDENCE_DRIFT"
    ROUTE_POLICY_DRIFT = "ROUTE_POLICY_DRIFT"


class ShadowRoutingFailure(ValueError):
    """Closed diagnostic that never retains rejected evidence or content."""

    __slots__ = ("code",)

    def __init__(self, code: ShadowRoutingFailureCode) -> None:
        if type(code) is not ShadowRoutingFailureCode:
            raise TypeError("invalid shadow-routing failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"ShadowRoutingFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("shadow-routing failures cannot be serialized")


def fail_shadow_routing(
    code: ShadowRoutingFailureCode = ShadowRoutingFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ShadowRoutingFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("shadow-routing values cannot be serialized")


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
        fail_shadow_routing()


def _identifier(value: object) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        fail_shadow_routing()
    return value


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_shadow_routing()
    return value


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        fail_shadow_routing()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        _sha(self.value)

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_shadow_routing()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class ShadowRoutingCommand(_RedactedValue):
    """One hash-bound request for local recorded shadow evaluation."""

    recording_id: str
    task_code: str
    route_code: str
    source_sha256: Sha256Digest
    source_bytes: int
    policy_version: str
    canary_allocation_percent: int = 0
    release_decision_sha256: Sha256Digest | None = None
    parser_version: str = SHADOW_PARSER_VERSION
    scope: ChampionChallengerScope = DEFAULT_CHAMPION_CHALLENGER_SCOPE

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or _identifier(self.task_code) != TARGET_TASK_CODE
            or _identifier(self.route_code) != TARGET_ROUTE_CODE
            or type(self.source_sha256) is not Sha256Digest
            or type(self.policy_version) is not str
            or self.policy_version != "st1902-disabled-shadow.v1"
            or type(self.parser_version) is not str
            or self.parser_version != SHADOW_PARSER_VERSION
            or type(self.scope) is not ChampionChallengerScope
        ):
            fail_shadow_routing()
        _bounded_int(self.source_bytes, minimum=1, maximum=MAX_SHADOW_SOURCE_BYTES)
        if type(self.canary_allocation_percent) is not int:
            fail_shadow_routing()
        if self.canary_allocation_percent != 0:
            fail_shadow_routing(ShadowRoutingFailureCode.CANARY_ALLOCATION_PROHIBITED)
        if self.release_decision_sha256 is not None:
            fail_shadow_routing(ShadowRoutingFailureCode.RELEASE_DECISION_PROHIBITED)

    @property
    def canonical_sha256(self) -> Sha256Digest:
        return Sha256Digest.of(
            canonical_json_bytes(
                {
                    "canary_allocation_percent": self.canary_allocation_percent,
                    "parser_version": self.parser_version,
                    "policy_version": self.policy_version,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "route_code": self.route_code,
                    "scope": self.scope.value,
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256.value,
                    "task_code": self.task_code,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedShadowObservation(_RedactedValue):
    """Content-free recorded pair for one blinded synthetic cohort member."""

    case_id: str
    assignment_sha256: Sha256Digest
    champion_output_sha256: Sha256Digest
    challenger_output_sha256: Sha256Digest
    champion_score_micros: int
    challenger_score_micros: int
    champion_schema_valid: bool
    challenger_schema_valid: bool
    champion_zero_tolerance_failures: int
    challenger_zero_tolerance_failures: int
    human_label_available: bool

    def __post_init__(self) -> None:
        if (
            _identifier(self.case_id) != self.case_id
            or type(self.assignment_sha256) is not Sha256Digest
            or type(self.champion_output_sha256) is not Sha256Digest
            or type(self.challenger_output_sha256) is not Sha256Digest
            or type(self.champion_schema_valid) is not bool
            or type(self.challenger_schema_valid) is not bool
            or type(self.human_label_available) is not bool
            or self.human_label_available
        ):
            fail_shadow_routing()
        _bounded_int(self.champion_score_micros, minimum=0, maximum=METRIC_SCALE)
        _bounded_int(self.challenger_score_micros, minimum=0, maximum=METRIC_SCALE)
        _bounded_int(
            self.champion_zero_tolerance_failures,
            minimum=0,
            maximum=MAX_SHADOW_OBSERVATIONS,
        )
        _bounded_int(
            self.challenger_zero_tolerance_failures,
            minimum=0,
            maximum=MAX_SHADOW_OBSERVATIONS,
        )


def observation_projection(item: RecordedShadowObservation) -> dict[str, object]:
    if type(item) is not RecordedShadowObservation:
        fail_shadow_routing()
    return {
        "assignment_sha256": item.assignment_sha256.value,
        "case_id": item.case_id,
        "challenger_output_sha256": item.challenger_output_sha256.value,
        "challenger_schema_valid": item.challenger_schema_valid,
        "challenger_score_micros": item.challenger_score_micros,
        "challenger_zero_tolerance_failures": (item.challenger_zero_tolerance_failures),
        "champion_output_sha256": item.champion_output_sha256.value,
        "champion_schema_valid": item.champion_schema_valid,
        "champion_score_micros": item.champion_score_micros,
        "champion_zero_tolerance_failures": item.champion_zero_tolerance_failures,
        "human_label_available": item.human_label_available,
    }


@dataclass(frozen=True, slots=True, repr=False)
class RecordedShadowBatch(_RedactedValue):
    """One immutable, exact-dependency recorded shadow cohort."""

    recording_id: str
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int
    fixture_profile: str
    parser_version: str
    route_catalog_sha256: Sha256Digest
    route_catalog_canary_max_percent: int
    critical_effective_canary_max_percent: int
    st0708_report_sha256: Sha256Digest
    st0708_report_outcome: str
    observations: tuple[RecordedShadowObservation, ...]
    normalized_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.command_sha256) is not Sha256Digest
            or type(self.source_sha256) is not Sha256Digest
            or self.fixture_profile != SYNTHETIC_SHADOW_PROFILE
            or self.parser_version != SHADOW_PARSER_VERSION
            or type(self.route_catalog_sha256) is not Sha256Digest
            or type(self.st0708_report_sha256) is not Sha256Digest
            or self.st0708_report_outcome != EXPECTED_ST0708_OUTCOME
            or type(self.observations) is not tuple
            or not 1 <= len(self.observations) <= MAX_SHADOW_OBSERVATIONS
            or any(
                type(item) is not RecordedShadowObservation
                for item in self.observations
            )
        ):
            fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_RESULT_INVALID)
        _bounded_int(self.source_bytes, minimum=1, maximum=MAX_SHADOW_SOURCE_BYTES)
        if self.route_catalog_canary_max_percent != 5:
            fail_shadow_routing(ShadowRoutingFailureCode.ROUTE_POLICY_DRIFT)
        if self.critical_effective_canary_max_percent != 1:
            fail_shadow_routing(ShadowRoutingFailureCode.ROUTE_POLICY_DRIFT)
        case_ids = tuple(item.case_id for item in self.observations)
        assignments = tuple(item.assignment_sha256 for item in self.observations)
        if (
            case_ids != tuple(sorted(case_ids))
            or len(set(case_ids)) != len(case_ids)
            or len(set(assignments)) != len(assignments)
        ):
            fail_shadow_routing(ShadowRoutingFailureCode.DUPLICATE_COHORT_MEMBER)
        object.__setattr__(
            self,
            "normalized_sha256",
            Sha256Digest.of(
                canonical_json_bytes(
                    {
                        "command_sha256": self.command_sha256.value,
                        "critical_effective_canary_max_percent": (
                            self.critical_effective_canary_max_percent
                        ),
                        "fixture_profile": self.fixture_profile,
                        "observations": [
                            observation_projection(item) for item in self.observations
                        ],
                        "parser_version": self.parser_version,
                        "recording_id": self.recording_id,
                        "route_catalog_canary_max_percent": (
                            self.route_catalog_canary_max_percent
                        ),
                        "route_catalog_sha256": self.route_catalog_sha256.value,
                        "source_bytes": self.source_bytes,
                        "source_sha256": self.source_sha256.value,
                        "st0708_report_outcome": self.st0708_report_outcome,
                        "st0708_report_sha256": self.st0708_report_sha256.value,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True, repr=False)
class ShadowRoutingReport(_RedactedValue):
    """Content-free non-authoritative result that cannot promote a route."""

    recording_id: str
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    normalized_sha256: Sha256Digest
    task_code: str
    route_code: str
    route_catalog_sha256: Sha256Digest
    st0708_report_sha256: Sha256Digest
    cohort_size: int
    champion_wins: int
    challenger_wins: int
    ties: int
    champion_schema_failures: int
    challenger_schema_failures: int
    champion_zero_tolerance_failures: int
    challenger_zero_tolerance_failures: int
    champion_mean_score_micros: int
    challenger_mean_score_micros: int
    challenger_delta_micros: int
    outcome: ShadowOutcome
    challenger_state: ChallengerState
    blockers: tuple[str, ...]
    report_sha256: Sha256Digest
    scope: ChampionChallengerScope
    default_scope: ChampionChallengerScope = DEFAULT_CHAMPION_CHALLENGER_SCOPE
    phase: str = "SHADOW"
    decision_kind: str = "NONAUTHORITATIVE_OBSERVATION"
    authority: str = "NONE"
    canary_allocation_percent: int = 0
    route_catalog_canary_max_percent: int = 5
    critical_effective_canary_max_percent: int = 1
    canary: ShadowBoundaryStatus = ShadowBoundaryStatus.RELEASE_DECISION_REQUIRED
    canonical_status: ShadowBoundaryStatus = ShadowBoundaryStatus.DEFERRED_POST_MVP
    formal_tst_032: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_EXECUTED
    provider: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_EXECUTED
    network: ShadowBoundaryStatus = ShadowBoundaryStatus.FORBIDDEN
    credentials: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_USED
    persistence: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_EXECUTED
    route_mutation: ShadowBoundaryStatus = ShadowBoundaryStatus.FORBIDDEN
    editorial_mutation: ShadowBoundaryStatus = ShadowBoundaryStatus.FORBIDDEN
    publication: ShadowBoundaryStatus = ShadowBoundaryStatus.FORBIDDEN
    release: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_EXECUTED
    production: ShadowBoundaryStatus = ShadowBoundaryStatus.NOT_EXECUTED

    def require_valid(self) -> None:
        counts = (
            self.cohort_size,
            self.champion_wins,
            self.challenger_wins,
            self.ties,
            self.champion_schema_failures,
            self.challenger_schema_failures,
            self.champion_zero_tolerance_failures,
            self.challenger_zero_tolerance_failures,
        )
        statuses = (
            self.canary,
            self.canonical_status,
            self.formal_tst_032,
            self.provider,
            self.network,
            self.credentials,
            self.persistence,
            self.route_mutation,
            self.editorial_mutation,
            self.publication,
            self.release,
            self.production,
        )
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or any(
                type(item) is not Sha256Digest
                for item in (
                    self.command_sha256,
                    self.source_sha256,
                    self.normalized_sha256,
                    self.route_catalog_sha256,
                    self.st0708_report_sha256,
                    self.report_sha256,
                )
            )
            or self.task_code != TARGET_TASK_CODE
            or self.route_code != TARGET_ROUTE_CODE
            or any(type(value) is not int or value < 0 for value in counts)
            or self.cohort_size <= 0
            or self.champion_wins + self.challenger_wins + self.ties != self.cohort_size
            or any(value > self.cohort_size for value in counts[1:6])
            or type(self.challenger_delta_micros) is not int
            or not -METRIC_SCALE <= self.challenger_delta_micros <= METRIC_SCALE
            or not 0 <= self.champion_mean_score_micros <= METRIC_SCALE
            or not 0 <= self.challenger_mean_score_micros <= METRIC_SCALE
            or type(self.outcome) is not ShadowOutcome
            or type(self.challenger_state) is not ChallengerState
            or type(self.blockers) is not tuple
            or self.blockers != tuple(sorted(set(self.blockers)))
            or any(_identifier(item) != item for item in self.blockers)
            or type(self.scope) is not ChampionChallengerScope
            or self.scope is not ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY
            or self.default_scope is not ChampionChallengerScope.DISABLED
            or self.phase != "SHADOW"
            or self.decision_kind != "NONAUTHORITATIVE_OBSERVATION"
            or self.authority != "NONE"
            or self.canary_allocation_percent != 0
            or self.route_catalog_canary_max_percent != 5
            or self.critical_effective_canary_max_percent != 1
            or any(type(item) is not ShadowBoundaryStatus for item in statuses)
            or self.canary is not ShadowBoundaryStatus.RELEASE_DECISION_REQUIRED
            or self.canonical_status is not ShadowBoundaryStatus.DEFERRED_POST_MVP
            or self.formal_tst_032 is not ShadowBoundaryStatus.NOT_EXECUTED
            or self.provider is not ShadowBoundaryStatus.NOT_EXECUTED
            or self.network is not ShadowBoundaryStatus.FORBIDDEN
            or self.credentials is not ShadowBoundaryStatus.NOT_USED
            or self.persistence is not ShadowBoundaryStatus.NOT_EXECUTED
            or self.route_mutation is not ShadowBoundaryStatus.FORBIDDEN
            or self.editorial_mutation is not ShadowBoundaryStatus.FORBIDDEN
            or self.publication is not ShadowBoundaryStatus.FORBIDDEN
            or self.release is not ShadowBoundaryStatus.NOT_EXECUTED
            or self.production is not ShadowBoundaryStatus.NOT_EXECUTED
            or self.report_sha256
            != Sha256Digest.of(canonical_json_bytes(report_projection(self)))
        ):
            fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_RESULT_INVALID)


def report_projection(report: ShadowRoutingReport) -> dict[str, object]:
    if type(report) is not ShadowRoutingReport:
        fail_shadow_routing()
    return {
        "authority": report.authority,
        "blockers": list(report.blockers),
        "boundary": {
            "canary": report.canary.value,
            "canonical_status": report.canonical_status.value,
            "credentials": report.credentials.value,
            "editorial_mutation": report.editorial_mutation.value,
            "formal_tst_032": report.formal_tst_032.value,
            "network": report.network.value,
            "persistence": report.persistence.value,
            "production": report.production.value,
            "provider": report.provider.value,
            "publication": report.publication.value,
            "release": report.release.value,
            "route_mutation": report.route_mutation.value,
        },
        "canary_allocation_percent": report.canary_allocation_percent,
        "challenger_state": report.challenger_state.value,
        "command_sha256": report.command_sha256.value,
        "critical_effective_canary_max_percent": (
            report.critical_effective_canary_max_percent
        ),
        "decision_kind": report.decision_kind,
        "metrics": {
            "challenger_delta_micros": report.challenger_delta_micros,
            "challenger_mean_score_micros": report.challenger_mean_score_micros,
            "challenger_schema_failures": report.challenger_schema_failures,
            "challenger_wins": report.challenger_wins,
            "challenger_zero_tolerance_failures": (
                report.challenger_zero_tolerance_failures
            ),
            "champion_mean_score_micros": report.champion_mean_score_micros,
            "champion_schema_failures": report.champion_schema_failures,
            "champion_wins": report.champion_wins,
            "champion_zero_tolerance_failures": (
                report.champion_zero_tolerance_failures
            ),
            "cohort_size": report.cohort_size,
            "ties": report.ties,
        },
        "normalized_sha256": report.normalized_sha256.value,
        "outcome": report.outcome.value,
        "phase": report.phase,
        "recording_id": report.recording_id,
        "route_catalog_canary_max_percent": report.route_catalog_canary_max_percent,
        "route_catalog_sha256": report.route_catalog_sha256.value,
        "route_code": report.route_code,
        "scope": report.scope.value,
        "source_sha256": report.source_sha256.value,
        "st0708_report_sha256": report.st0708_report_sha256.value,
        "task_code": report.task_code,
    }


def finalize_report(report: ShadowRoutingReport) -> ShadowRoutingReport:
    if type(report) is not ShadowRoutingReport:
        fail_shadow_routing()
    finalized = replace(
        report,
        report_sha256=Sha256Digest.of(canonical_json_bytes(report_projection(report))),
    )
    finalized.require_valid()
    return finalized


def evaluate_recorded_shadow(
    command: ShadowRoutingCommand,
    batch: RecordedShadowBatch,
) -> ShadowRoutingReport:
    """Evaluate one synthetic cohort while always retaining the champion."""

    if (
        type(command) is not ShadowRoutingCommand
        or type(batch) is not RecordedShadowBatch
    ):
        fail_shadow_routing()
    if command.scope is not ChampionChallengerScope.RECORDED_SYNTHETIC_SHADOW_ONLY:
        fail_shadow_routing(ShadowRoutingFailureCode.FEATURE_DISABLED)
    if (
        batch.recording_id != command.recording_id
        or batch.command_sha256 != command.canonical_sha256
        or batch.source_sha256 != command.source_sha256
        or batch.source_bytes != command.source_bytes
    ):
        fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_RESULT_INVALID)
    if batch.st0708_report_outcome != EXPECTED_ST0708_OUTCOME:
        fail_shadow_routing(ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT)

    champion_wins = sum(
        item.champion_score_micros > item.challenger_score_micros
        for item in batch.observations
    )
    challenger_wins = sum(
        item.challenger_score_micros > item.champion_score_micros
        for item in batch.observations
    )
    ties = len(batch.observations) - champion_wins - challenger_wins
    champion_schema_failures = sum(
        not item.champion_schema_valid for item in batch.observations
    )
    challenger_schema_failures = sum(
        not item.challenger_schema_valid for item in batch.observations
    )
    champion_zero = sum(
        item.champion_zero_tolerance_failures for item in batch.observations
    )
    challenger_zero = sum(
        item.challenger_zero_tolerance_failures for item in batch.observations
    )
    cohort_size = len(batch.observations)
    champion_mean = (
        sum(item.champion_score_micros for item in batch.observations) // cohort_size
    )
    challenger_mean = (
        sum(item.challenger_score_micros for item in batch.observations) // cohort_size
    )

    blockers = {
        "CANARY_RELEASE_DECISION_ABSENT",
        "CANARY_UNREACHABLE",
        "FORMAL_TST_032_NOT_EXECUTED",
        "RECORDED_SYNTHETIC_ONLY",
        "ST0708_RELEASE_EVIDENCE_INCOMPLETE",
    }
    outcome = ShadowOutcome.KEEP_CHAMPION_INCOMPLETE_EVIDENCE
    challenger_state = ChallengerState.SHADOW_NONAUTHORITATIVE
    if champion_zero or challenger_zero:
        blockers.add("ZERO_TOLERANCE_FAILURE_OBSERVED")
        outcome = ShadowOutcome.KEEP_CHAMPION_ZERO_TOLERANCE
        challenger_state = ChallengerState.PAUSED_RECORDED_ONLY
    elif champion_schema_failures or challenger_schema_failures:
        blockers.add("SCHEMA_FAILURE_OBSERVED")
        outcome = ShadowOutcome.KEEP_CHAMPION_SCHEMA_FAILURE
        challenger_state = ChallengerState.PAUSED_RECORDED_ONLY

    provisional = ShadowRoutingReport(
        recording_id=command.recording_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        normalized_sha256=batch.normalized_sha256,
        task_code=command.task_code,
        route_code=command.route_code,
        route_catalog_sha256=batch.route_catalog_sha256,
        st0708_report_sha256=batch.st0708_report_sha256,
        cohort_size=cohort_size,
        champion_wins=champion_wins,
        challenger_wins=challenger_wins,
        ties=ties,
        champion_schema_failures=champion_schema_failures,
        challenger_schema_failures=challenger_schema_failures,
        champion_zero_tolerance_failures=champion_zero,
        challenger_zero_tolerance_failures=challenger_zero,
        champion_mean_score_micros=champion_mean,
        challenger_mean_score_micros=challenger_mean,
        challenger_delta_micros=challenger_mean - champion_mean,
        outcome=outcome,
        challenger_state=challenger_state,
        blockers=tuple(sorted(blockers)),
        report_sha256=Sha256Digest("0" * 64),
        scope=command.scope,
    )
    return finalize_report(provisional)


__all__ = [
    "ChampionChallengerScope",
    "ChallengerState",
    "DEFAULT_CHAMPION_CHALLENGER_SCOPE",
    "EXPECTED_ST0708_OUTCOME",
    "MAX_SHADOW_OBSERVATIONS",
    "MAX_SHADOW_SOURCE_BYTES",
    "METRIC_SCALE",
    "RecordedShadowBatch",
    "RecordedShadowObservation",
    "SHADOW_CONTRACT_VERSION",
    "SHADOW_PARSER_VERSION",
    "SYNTHETIC_SHADOW_PROFILE",
    "Sha256Digest",
    "ShadowBoundaryStatus",
    "ShadowOutcome",
    "ShadowRoutingCommand",
    "ShadowRoutingFailure",
    "ShadowRoutingFailureCode",
    "ShadowRoutingReport",
    "TARGET_ROUTE_CODE",
    "TARGET_TASK_CODE",
    "canonical_json_bytes",
    "evaluate_recorded_shadow",
    "fail_shadow_routing",
    "finalize_report",
    "observation_projection",
    "report_projection",
]
