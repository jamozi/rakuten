"""Maximum-safe, non-authoritative causal analysis values for ST-1906.

Only aggregate, recorded/synthetic, randomized two-arm evidence is representable.
The result is an analysis candidate; it can never allocate provider reward or
mutate editorial, recommendation, publication, tracking, or Production state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex

from raos.domain.finance.attribution import (
    CohortMaturity,
    MeasurementAttributionContract,
    MeasurementPeriod,
    PROGRAM,
    RECOMMENDATION_INPUTS_EXCLUDED,
    VerificationState,
)
from raos.domain.ops.object_intake import Sha256Digest


CAUSAL_CONTRACT_VERSION: Final = "1.0.0"
CAUSAL_METHOD_VERSION: Final = "RAOS_ST1906_RANDOMIZED_AGGREGATE_RISK_DIFFERENCE_V1"
CAUSAL_PARSER_VERSION: Final = "st1906-recorded-causal-aggregate-json.v1"
SYNTHETIC_CAUSAL_PROFILE: Final = "RAOS_ST1906_SYNTHETIC_CAUSAL_AGGREGATE_V1"
PRIVACY_SCOPE: Final = "AGGREGATE_NON_PERSONAL_RECORDED_SYNTHETIC_ONLY"
OUTCOME_CODE: Final = "AFFILIATE_CLICK"
MIN_ARM_EXPOSURES: Final = 500
MIN_ARM_OUTCOMES: Final = 20
EXPECTED_ARTICLE_CELLS: Final = 5
MAX_ARM_EXPOSURES: Final = 100_000_000
EFFECT_SCALE: Final = 1_000_000
CONFIDENCE_BPS: Final = 9_500
MAX_SOURCE_BYTES: Final = 1_048_576
_Z_95: Final = Decimal("1.959963984540054")

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_PROGRAM = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED: Final = "<redacted-causal-attribution>"


class CausalAttributionScope(str, Enum):
    """Closed states; no live, activation, or Production state exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY = (
        "RECORDED_SYNTHETIC_AGGREGATE_EVALUATION_ONLY"
    )


DEFAULT_CAUSAL_ATTRIBUTION_SCOPE: Final = CausalAttributionScope.DISABLED


class PrivacyReviewStatus(str, Enum):
    NOT_REVIEWED = "NOT_REVIEWED"
    RECORDED_SYNTHETIC_SCOPE_REVIEWED = "RECORDED_SYNTHETIC_SCOPE_REVIEWED"


class CausalAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CausalUnavailableReason(str, Enum):
    MISSING_INPUT = "MISSING_INPUT"
    PRIVACY_REVIEW_REQUIRED = "PRIVACY_REVIEW_REQUIRED"
    ARTICLE_BINDING_MISMATCH = "ARTICLE_BINDING_MISMATCH"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    ASSIGNMENT_UNVERIFIED = "ASSIGNMENT_UNVERIFIED"
    ARM_BALANCE_MISMATCH = "ARM_BALANCE_MISMATCH"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"
    LOW_SAMPLE_SIZE = "LOW_SAMPLE_SIZE"
    LOW_OUTCOME_COUNT = "LOW_OUTCOME_COUNT"
    INSUFFICIENT_CAUSAL_SIGNAL = "INSUFFICIENT_CAUSAL_SIGNAL"


class CausalCandidateState(str, Enum):
    ANALYSIS_CANDIDATE_ONLY = "ANALYSIS_CANDIDATE_ONLY"
    NO_ANALYSIS_AVAILABLE = "NO_ANALYSIS_AVAILABLE"


class CausalAttributionFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    RELEASE_DECISION_PROHIBITED = "RELEASE_DECISION_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DUPLICATE_ARTICLE_CELL = "DUPLICATE_ARTICLE_CELL"
    DEPENDENCY_CONTRACT_DRIFT = "DEPENDENCY_CONTRACT_DRIFT"


class CausalAttributionFailure(ValueError):
    """Closed failure that never retains rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: CausalAttributionFailureCode) -> None:
        if type(code) is not CausalAttributionFailureCode:
            raise TypeError("invalid causal-attribution failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"CausalAttributionFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("causal-attribution failures cannot be serialized")


def fail_causal_attribution(
    code: CausalAttributionFailureCode = CausalAttributionFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise CausalAttributionFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("causal-attribution values cannot be serialized")


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
        fail_causal_attribution()


def digest_bytes(value: bytes) -> Sha256Digest:
    if type(value) is not bytes:
        fail_causal_attribution()
    return Sha256Digest(hashlib.sha256(value).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest or _SHA256.fullmatch(value.value) is None:
        fail_causal_attribution()
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        fail_causal_attribution()
    return value


def _program(value: object) -> str:
    if type(value) is not str or _PROGRAM.fullmatch(value) is None:
        fail_causal_attribution()
    return value


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= MAX_ARM_EXPOSURES:
        fail_causal_attribution()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class PrivacyReviewEvidence(_RedactedValue):
    """Synthetic-only privacy review record; never a live/privacy approval."""

    status: PrivacyReviewStatus
    review_sha256: Sha256Digest | None
    scope: str = PRIVACY_SCOPE
    synthetic: bool = True
    aggregate_only: bool = True
    personal_data: bool = False
    persistent_identifier: bool = False
    raw_ip: bool = False
    full_user_agent: bool = False
    free_text: bool = False
    tracking_activation: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.status) is not PrivacyReviewStatus
            or self.scope != PRIVACY_SCOPE
            or self.synthetic is not True
            or self.aggregate_only is not True
            or self.personal_data is not False
            or self.persistent_identifier is not False
            or self.raw_ip is not False
            or self.full_user_agent is not False
            or self.free_text is not False
            or self.tracking_activation is not False
        ):
            fail_causal_attribution()
        if self.status is PrivacyReviewStatus.NOT_REVIEWED:
            if self.review_sha256 is not None:
                fail_causal_attribution()
        else:
            _sha(self.review_sha256)

    def payload(self) -> dict[str, object]:
        return {
            "aggregate_only": self.aggregate_only,
            "free_text": self.free_text,
            "full_user_agent": self.full_user_agent,
            "personal_data": self.personal_data,
            "persistent_identifier": self.persistent_identifier,
            "raw_ip": self.raw_ip,
            "review_sha256": (
                None if self.review_sha256 is None else self.review_sha256.value
            ),
            "scope": self.scope,
            "status": self.status.value,
            "synthetic": self.synthetic,
            "tracking_activation": self.tracking_activation,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CausalAttributionCommand(_RedactedValue):
    recording_id: str
    experiment_id: str
    source_sha256: Sha256Digest
    source_bytes: int
    contract: MeasurementAttributionContract
    program: str
    period: MeasurementPeriod
    privacy_review: PrivacyReviewEvidence
    preregistration_sha256: Sha256Digest
    release_decision_sha256: Sha256Digest | None = None
    method_version: str = CAUSAL_METHOD_VERSION
    parser_version: str = CAUSAL_PARSER_VERSION
    scope: CausalAttributionScope = DEFAULT_CAUSAL_ATTRIBUTION_SCOPE

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or _identifier(self.experiment_id) != self.experiment_id
            or type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or type(self.contract) is not MeasurementAttributionContract
            or type(self.period) is not MeasurementPeriod
            or type(self.privacy_review) is not PrivacyReviewEvidence
            or self.method_version != CAUSAL_METHOD_VERSION
            or self.parser_version != CAUSAL_PARSER_VERSION
            or type(self.scope) is not CausalAttributionScope
        ):
            fail_causal_attribution()
        _sha(self.source_sha256)
        _sha(self.preregistration_sha256)
        _program(self.program)
        if self.release_decision_sha256 is not None:
            fail_causal_attribution(
                CausalAttributionFailureCode.RELEASE_DECISION_PROHIBITED
            )

    @property
    def canonical_sha256(self) -> Sha256Digest:
        return digest_bytes(
            canonical_json_bytes(
                {
                    "contract_sha256": self.contract.sha256.value,
                    "experiment_id": self.experiment_id,
                    "method_version": self.method_version,
                    "parser_version": self.parser_version,
                    "period": self.period.payload(),
                    "preregistration_sha256": self.preregistration_sha256.value,
                    "privacy_review": self.privacy_review.payload(),
                    "program": self.program,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "scope": self.scope.value,
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256.value,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class AggregateExperimentCell(_RedactedValue):
    slot: int
    article_id: str
    packet_sha256: Sha256Digest
    program: str
    period: MeasurementPeriod
    verification: VerificationState
    cohort: CohortMaturity
    assignment_verified: bool
    assignment_sha256: Sha256Digest
    source_sha256: Sha256Digest
    control_exposures: int
    control_outcomes: int
    treatment_exposures: int
    treatment_outcomes: int

    def __post_init__(self) -> None:
        if (
            type(self.slot) is not int
            or not 1 <= self.slot <= EXPECTED_ARTICLE_CELLS
            or _identifier(self.article_id) != self.article_id
            or type(self.period) is not MeasurementPeriod
            or type(self.verification) is not VerificationState
            or type(self.cohort) is not CohortMaturity
            or type(self.assignment_verified) is not bool
        ):
            fail_causal_attribution()
        _sha(self.packet_sha256)
        _sha(self.assignment_sha256)
        _sha(self.source_sha256)
        _program(self.program)
        control_exposures = _count(self.control_exposures)
        control_outcomes = _count(self.control_outcomes)
        treatment_exposures = _count(self.treatment_exposures)
        treatment_outcomes = _count(self.treatment_outcomes)
        if (
            control_outcomes > control_exposures
            or treatment_outcomes > treatment_exposures
        ):
            fail_causal_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "article_id": self.article_id,
            "assignment_sha256": self.assignment_sha256.value,
            "assignment_verified": self.assignment_verified,
            "cohort": self.cohort.value,
            "control_exposures": self.control_exposures,
            "control_outcomes": self.control_outcomes,
            "packet_sha256": self.packet_sha256.value,
            "period": self.period.payload(),
            "program": self.program,
            "slot": self.slot,
            "source_sha256": self.source_sha256.value,
            "treatment_exposures": self.treatment_exposures,
            "treatment_outcomes": self.treatment_outcomes,
            "verification": self.verification.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class RecordedCausalAttributionBatch(_RedactedValue):
    recording_id: str
    experiment_id: str
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int
    contract_sha256: Sha256Digest
    program: str
    period: MeasurementPeriod
    privacy_review: PrivacyReviewEvidence
    preregistration_sha256: Sha256Digest
    fixture_profile: str
    parser_version: str
    outcome_code: str
    cells: tuple[AggregateExperimentCell, ...]

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or _identifier(self.experiment_id) != self.experiment_id
            or type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or type(self.period) is not MeasurementPeriod
            or type(self.privacy_review) is not PrivacyReviewEvidence
            or self.fixture_profile != SYNTHETIC_CAUSAL_PROFILE
            or self.parser_version != CAUSAL_PARSER_VERSION
            or self.outcome_code != OUTCOME_CODE
            or type(self.cells) is not tuple
            or len(self.cells) > EXPECTED_ARTICLE_CELLS
            or any(type(cell) is not AggregateExperimentCell for cell in self.cells)
        ):
            fail_causal_attribution()
        _sha(self.command_sha256)
        _sha(self.source_sha256)
        _sha(self.contract_sha256)
        _sha(self.preregistration_sha256)
        _program(self.program)
        if (
            len({cell.slot for cell in self.cells}) != len(self.cells)
            or len({cell.article_id for cell in self.cells}) != len(self.cells)
            or len({cell.assignment_sha256.value for cell in self.cells})
            != len(self.cells)
            or len({cell.source_sha256.value for cell in self.cells}) != len(self.cells)
        ):
            fail_causal_attribution(CausalAttributionFailureCode.DUPLICATE_ARTICLE_CELL)


@dataclass(frozen=True, slots=True, repr=False)
class CausalEffectEstimate(_RedactedValue):
    control_exposures: int
    control_outcomes: int
    treatment_exposures: int
    treatment_outcomes: int
    control_rate_micros: int
    treatment_rate_micros: int
    risk_difference_micros: int
    confidence_lower_micros: int
    confidence_upper_micros: int
    confidence_bps: int = CONFIDENCE_BPS

    def __post_init__(self) -> None:
        for value in (
            self.control_exposures,
            self.control_outcomes,
            self.treatment_exposures,
            self.treatment_outcomes,
        ):
            _count(value)
        for value in (
            self.control_rate_micros,
            self.treatment_rate_micros,
            self.risk_difference_micros,
            self.confidence_lower_micros,
            self.confidence_upper_micros,
        ):
            if type(value) is not int or not -EFFECT_SCALE <= value <= EFFECT_SCALE:
                fail_causal_attribution()
        if (
            self.control_exposures <= 0
            or self.treatment_exposures <= 0
            or self.control_outcomes > self.control_exposures
            or self.treatment_outcomes > self.treatment_exposures
            or self.confidence_bps != CONFIDENCE_BPS
            or self.confidence_lower_micros > self.risk_difference_micros
            or self.confidence_upper_micros < self.risk_difference_micros
        ):
            fail_causal_attribution()

    def payload(self) -> dict[str, object]:
        return {
            "confidence_bps": self.confidence_bps,
            "confidence_lower_micros": self.confidence_lower_micros,
            "confidence_upper_micros": self.confidence_upper_micros,
            "control_exposures": self.control_exposures,
            "control_outcomes": self.control_outcomes,
            "control_rate_micros": self.control_rate_micros,
            "risk_difference_micros": self.risk_difference_micros,
            "treatment_exposures": self.treatment_exposures,
            "treatment_outcomes": self.treatment_outcomes,
            "treatment_rate_micros": self.treatment_rate_micros,
        }


@dataclass(frozen=True, slots=True, repr=False)
class CausalAuthority(_RedactedValue):
    provider_call: bool = False
    network: bool = False
    persistence: bool = False
    tracking_activation: bool = False
    editorial_mutation: bool = False
    article_html_mutation: bool = False
    cta_mutation: bool = False
    product_selection_mutation: bool = False
    recommendation_order_mutation: bool = False
    publication_snapshot_mutation: bool = False
    publication: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_causal_attribution()

    def payload(self) -> dict[str, object]:
        return {name: False for name in self.__slots__}


@dataclass(frozen=True, slots=True, repr=False)
class CausalAttributionReport(_RedactedValue):
    report_sha256: Sha256Digest
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    contract_sha256: Sha256Digest
    preregistration_sha256: Sha256Digest
    privacy_review_sha256: Sha256Digest | None
    availability: CausalAvailability
    unavailable_reason: CausalUnavailableReason | None
    candidate_state: CausalCandidateState
    method_version: str
    outcome_code: str
    cell_count: int
    estimate: CausalEffectEstimate | None
    blockers: tuple[str, ...]
    authority: CausalAuthority = field(default_factory=CausalAuthority)

    def __post_init__(self) -> None:
        for digest in (
            self.report_sha256,
            self.command_sha256,
            self.source_sha256,
            self.contract_sha256,
            self.preregistration_sha256,
        ):
            _sha(digest)
        if self.privacy_review_sha256 is not None:
            _sha(self.privacy_review_sha256)
        if (
            type(self.availability) is not CausalAvailability
            or type(self.candidate_state) is not CausalCandidateState
            or self.method_version != CAUSAL_METHOD_VERSION
            or self.outcome_code != OUTCOME_CODE
            or type(self.cell_count) is not int
            or not 0 <= self.cell_count <= EXPECTED_ARTICLE_CELLS
            or type(self.blockers) is not tuple
            or not self.blockers
            or tuple(sorted(set(self.blockers))) != self.blockers
            or type(self.authority) is not CausalAuthority
        ):
            fail_causal_attribution()
        if self.availability is CausalAvailability.AVAILABLE:
            if (
                self.unavailable_reason is not None
                or self.candidate_state
                is not CausalCandidateState.ANALYSIS_CANDIDATE_ONLY
                or type(self.estimate) is not CausalEffectEstimate
                or self.privacy_review_sha256 is None
            ):
                fail_causal_attribution()
        elif (
            type(self.unavailable_reason) is not CausalUnavailableReason
            or self.candidate_state is not CausalCandidateState.NO_ANALYSIS_AVAILABLE
            or self.estimate is not None
        ):
            fail_causal_attribution()

    def payload(self, *, include_report_sha256: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "authority": self.authority.payload(),
            "availability": self.availability.value,
            "blockers": list(self.blockers),
            "candidate_state": self.candidate_state.value,
            "cell_count": self.cell_count,
            "command_sha256": self.command_sha256.value,
            "contract_sha256": self.contract_sha256.value,
            "estimate": None if self.estimate is None else self.estimate.payload(),
            "method_version": self.method_version,
            "outcome_code": self.outcome_code,
            "policy": {
                "arbitrary_provider_total_allocation": False,
                "automatic_editorial_use": False,
                "automatic_recommendation_use": False,
                "finance_values_represented": False,
                "recommendation_inputs_excluded": list(RECOMMENDATION_INPUTS_EXCLUDED),
                "result_is_provider_fact": False,
            },
            "preregistration_sha256": self.preregistration_sha256.value,
            "privacy_review_sha256": (
                None
                if self.privacy_review_sha256 is None
                else self.privacy_review_sha256.value
            ),
            "source_sha256": self.source_sha256.value,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
        }
        if include_report_sha256:
            payload["report_sha256"] = self.report_sha256.value
        return payload


_BLOCKERS: Final = (
    "FORMAL_TST_032_NOT_EXECUTED",
    "LIVE_PRIVACY_REVIEW_NOT_EXECUTED",
    "LIVE_SIGNAL_VALIDATION_NOT_EXECUTED",
    "RECORDED_SYNTHETIC_ONLY",
    "SEPARATE_RELEASE_DECISION_REQUIRED",
)


def _unavailable(
    command: CausalAttributionCommand,
    batch: RecordedCausalAttributionBatch,
    reason: CausalUnavailableReason,
) -> CausalAttributionReport:
    preliminary = CausalAttributionReport(
        report_sha256=Sha256Digest("0" * 64),
        command_sha256=command.canonical_sha256,
        source_sha256=batch.source_sha256,
        contract_sha256=command.contract.sha256,
        preregistration_sha256=command.preregistration_sha256,
        privacy_review_sha256=batch.privacy_review.review_sha256,
        availability=CausalAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        candidate_state=CausalCandidateState.NO_ANALYSIS_AVAILABLE,
        method_version=CAUSAL_METHOD_VERSION,
        outcome_code=OUTCOME_CODE,
        cell_count=len(batch.cells),
        estimate=None,
        blockers=_BLOCKERS,
    )
    return _with_report_hash(preliminary)


def _with_report_hash(report: CausalAttributionReport) -> CausalAttributionReport:
    digest = digest_bytes(
        canonical_json_bytes(report.payload(include_report_sha256=False))
    )
    return CausalAttributionReport(
        report_sha256=digest,
        command_sha256=report.command_sha256,
        source_sha256=report.source_sha256,
        contract_sha256=report.contract_sha256,
        preregistration_sha256=report.preregistration_sha256,
        privacy_review_sha256=report.privacy_review_sha256,
        availability=report.availability,
        unavailable_reason=report.unavailable_reason,
        candidate_state=report.candidate_state,
        method_version=report.method_version,
        outcome_code=report.outcome_code,
        cell_count=report.cell_count,
        estimate=report.estimate,
        blockers=report.blockers,
        authority=report.authority,
    )


def _effect(cells: tuple[AggregateExperimentCell, ...]) -> CausalEffectEstimate:
    control_exposures = sum(cell.control_exposures for cell in cells)
    control_outcomes = sum(cell.control_outcomes for cell in cells)
    treatment_exposures = sum(cell.treatment_exposures for cell in cells)
    treatment_outcomes = sum(cell.treatment_outcomes for cell in cells)
    with localcontext() as context:
        context.prec = 50
        control_rate = Decimal(control_outcomes) / Decimal(control_exposures)
        treatment_rate = Decimal(treatment_outcomes) / Decimal(treatment_exposures)
        difference = treatment_rate - control_rate
        variance = treatment_rate * (Decimal(1) - treatment_rate) / Decimal(
            treatment_exposures
        ) + control_rate * (Decimal(1) - control_rate) / Decimal(control_exposures)
        margin = _Z_95 * context.sqrt(variance)
        lower = max(Decimal(-1), difference - margin)
        upper = min(Decimal(1), difference + margin)
        scale = Decimal(EFFECT_SCALE)
        return CausalEffectEstimate(
            control_exposures=control_exposures,
            control_outcomes=control_outcomes,
            treatment_exposures=treatment_exposures,
            treatment_outcomes=treatment_outcomes,
            control_rate_micros=int(
                (control_rate * scale).to_integral_value(rounding=ROUND_HALF_EVEN)
            ),
            treatment_rate_micros=int(
                (treatment_rate * scale).to_integral_value(rounding=ROUND_HALF_EVEN)
            ),
            risk_difference_micros=int(
                (difference * scale).to_integral_value(rounding=ROUND_HALF_EVEN)
            ),
            confidence_lower_micros=int(
                (lower * scale).to_integral_value(rounding=ROUND_FLOOR)
            ),
            confidence_upper_micros=int(
                (upper * scale).to_integral_value(rounding=ROUND_CEILING)
            ),
        )


def evaluate_recorded_causal_attribution(
    command: CausalAttributionCommand,
    batch: RecordedCausalAttributionBatch,
) -> CausalAttributionReport:
    """Evaluate aggregate randomized evidence without allocating or mutating."""

    if (
        type(command) is not CausalAttributionCommand
        or type(batch) is not RecordedCausalAttributionBatch
        or batch.recording_id != command.recording_id
        or batch.experiment_id != command.experiment_id
        or batch.command_sha256 != command.canonical_sha256
        or batch.source_sha256 != command.source_sha256
        or batch.source_bytes != command.source_bytes
        or batch.contract_sha256 != command.contract.sha256
        or batch.preregistration_sha256 != command.preregistration_sha256
        or batch.fixture_profile != SYNTHETIC_CAUSAL_PROFILE
        or batch.parser_version != command.parser_version
        or batch.outcome_code != OUTCOME_CODE
    ):
        fail_causal_attribution(CausalAttributionFailureCode.SOURCE_RESULT_INVALID)

    if (
        command.privacy_review.status is PrivacyReviewStatus.NOT_REVIEWED
        or batch.privacy_review.status is PrivacyReviewStatus.NOT_REVIEWED
        or batch.privacy_review != command.privacy_review
    ):
        return _unavailable(
            command, batch, CausalUnavailableReason.PRIVACY_REVIEW_REQUIRED
        )
    if not batch.cells:
        return _unavailable(command, batch, CausalUnavailableReason.MISSING_INPUT)

    expected_articles = command.contract.articles
    if (
        len(batch.cells) != EXPECTED_ARTICLE_CELLS
        or tuple(cell.slot for cell in batch.cells) != (1, 2, 3, 4, 5)
        or any(
            cell.article_id != article.article_id
            or cell.packet_sha256 != article.packet_sha256
            for cell, article in zip(batch.cells, expected_articles, strict=True)
        )
    ):
        return _unavailable(
            command, batch, CausalUnavailableReason.ARTICLE_BINDING_MISMATCH
        )
    if (
        command.program != PROGRAM
        or batch.program != command.program
        or any(cell.program != command.program for cell in batch.cells)
    ):
        return _unavailable(command, batch, CausalUnavailableReason.PROGRAM_MISMATCH)
    if batch.period != command.period or any(
        cell.period != command.period for cell in batch.cells
    ):
        return _unavailable(command, batch, CausalUnavailableReason.PERIOD_MISMATCH)
    if any(cell.verification is not VerificationState.VERIFIED for cell in batch.cells):
        return _unavailable(command, batch, CausalUnavailableReason.UNVERIFIED_INPUT)
    if any(cell.cohort is not CohortMaturity.MATURE for cell in batch.cells):
        return _unavailable(command, batch, CausalUnavailableReason.COHORT_IMMATURE)
    if any(not cell.assignment_verified for cell in batch.cells):
        return _unavailable(
            command, batch, CausalUnavailableReason.ASSIGNMENT_UNVERIFIED
        )
    if any(cell.control_exposures != cell.treatment_exposures for cell in batch.cells):
        return _unavailable(
            command, batch, CausalUnavailableReason.ARM_BALANCE_MISMATCH
        )
    if any(
        cell.control_exposures == 0 or cell.treatment_exposures == 0
        for cell in batch.cells
    ):
        return _unavailable(command, batch, CausalUnavailableReason.ZERO_DENOMINATOR)
    if any(
        cell.control_exposures < MIN_ARM_EXPOSURES
        or cell.treatment_exposures < MIN_ARM_EXPOSURES
        for cell in batch.cells
    ):
        return _unavailable(command, batch, CausalUnavailableReason.LOW_SAMPLE_SIZE)
    if any(
        cell.control_outcomes < MIN_ARM_OUTCOMES
        or cell.treatment_outcomes < MIN_ARM_OUTCOMES
        for cell in batch.cells
    ):
        return _unavailable(command, batch, CausalUnavailableReason.LOW_OUTCOME_COUNT)

    estimate = _effect(batch.cells)
    if estimate.confidence_lower_micros <= 0 <= estimate.confidence_upper_micros:
        return _unavailable(
            command, batch, CausalUnavailableReason.INSUFFICIENT_CAUSAL_SIGNAL
        )
    preliminary = CausalAttributionReport(
        report_sha256=Sha256Digest("0" * 64),
        command_sha256=command.canonical_sha256,
        source_sha256=batch.source_sha256,
        contract_sha256=command.contract.sha256,
        preregistration_sha256=command.preregistration_sha256,
        privacy_review_sha256=batch.privacy_review.review_sha256,
        availability=CausalAvailability.AVAILABLE,
        unavailable_reason=None,
        candidate_state=CausalCandidateState.ANALYSIS_CANDIDATE_ONLY,
        method_version=CAUSAL_METHOD_VERSION,
        outcome_code=OUTCOME_CODE,
        cell_count=len(batch.cells),
        estimate=estimate,
        blockers=_BLOCKERS,
    )
    return _with_report_hash(preliminary)


__all__ = (
    "CAUSAL_CONTRACT_VERSION",
    "CAUSAL_METHOD_VERSION",
    "CAUSAL_PARSER_VERSION",
    "CONFIDENCE_BPS",
    "DEFAULT_CAUSAL_ATTRIBUTION_SCOPE",
    "EFFECT_SCALE",
    "EXPECTED_ARTICLE_CELLS",
    "MAX_SOURCE_BYTES",
    "MIN_ARM_EXPOSURES",
    "MIN_ARM_OUTCOMES",
    "OUTCOME_CODE",
    "PRIVACY_SCOPE",
    "SYNTHETIC_CAUSAL_PROFILE",
    "AggregateExperimentCell",
    "CausalAttributionCommand",
    "CausalAttributionFailure",
    "CausalAttributionFailureCode",
    "CausalAttributionReport",
    "CausalAttributionScope",
    "CausalAvailability",
    "CausalAuthority",
    "CausalCandidateState",
    "CausalEffectEstimate",
    "CausalUnavailableReason",
    "PrivacyReviewEvidence",
    "PrivacyReviewStatus",
    "RecordedCausalAttributionBatch",
    "canonical_json_bytes",
    "digest_bytes",
    "evaluate_recorded_causal_attribution",
    "fail_causal_attribution",
)
