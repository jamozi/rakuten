"""Maximum-safe human-proposal portfolio optimizer boundary for ST-1907.

The module accepts only closed, non-finance portfolio signals.  It can emit
immutable proposal metadata for human review, but cannot choose or apply an
editorial, recommendation, publication, release, or Production mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex


CONTRACT_VERSION: Final = "1.0.0"
METHOD_VERSION: Final = "RAOS_ST1907_HUMAN_PROPOSAL_PORTFOLIO_OPTIMIZER_V1"
PARSER_VERSION: Final = "st1907-recorded-content-portfolio-optimizer-json.v1"
FIXTURE_PROFILE: Final = "RAOS_ST1907_RECORDED_SYNTHETIC_V1"
PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
PERIOD_DURATION_DAYS: Final = 14
MAX_SOURCE_BYTES: Final = 1_048_576
MAX_SIGNALS: Final = 100
MAX_ARTICLES_PER_SIGNAL: Final = 20
RECOMMENDATION_INPUTS_EXCLUDED: Final = (
    "AFFILIATE_COMMISSION_RATE",
    "CONFIRMED_REWARD",
    "UNATTRIBUTED_REWARD",
    "ESTIMATED_REWARD",
    "COMMISSION",
    "INCREMENTAL_COST",
    "LABOR_COST",
    "EPC",
    "RPM",
    "PROFIT",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_PROGRAM = re.compile(r"[A-Z][A-Z0-9_]{2,63}\Z", re.ASCII)
_REDACTED: Final = "<redacted-content-portfolio-optimizer>"


class PortfolioOptimizerScope(str, Enum):
    """Closed local scopes; no live or activation state exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY = (
        "RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY"
    )


DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE: Final = PortfolioOptimizerScope.DISABLED


class DependencyReadiness(str, Enum):
    BLOCKED_NO_DECISION = "BLOCKED_NO_DECISION"
    VERIFIED_HUMAN_DECISION = "VERIFIED_HUMAN_DECISION"


class SignalVerification(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"


class CohortMaturity(str, Enum):
    MATURE = "MATURE"
    IMMATURE = "IMMATURE"
    UNAVAILABLE = "UNAVAILABLE"


class ProposalAction(str, Enum):
    STRENGTHEN = "STRENGTHEN"
    CONSOLIDATE = "CONSOLIDATE"
    WITHDRAW = "WITHDRAW"


class ProposalBasis(str, Enum):
    MEASURED_VALUE_GAP_REVIEW = "MEASURED_VALUE_GAP_REVIEW"
    VERIFIED_DUPLICATE_INTENT_REVIEW = "VERIFIED_DUPLICATE_INTENT_REVIEW"
    VERIFIED_UNSUPPORTED_VALUE_REVIEW = "VERIFIED_UNSUPPORTED_VALUE_REVIEW"


_ACTION_BASIS: Final = {
    ProposalAction.STRENGTHEN: ProposalBasis.MEASURED_VALUE_GAP_REVIEW,
    ProposalAction.CONSOLIDATE: ProposalBasis.VERIFIED_DUPLICATE_INTENT_REVIEW,
    ProposalAction.WITHDRAW: ProposalBasis.VERIFIED_UNSUPPORTED_VALUE_REVIEW,
}
_ACTION_ORDER: Final = {
    ProposalAction.STRENGTHEN: 0,
    ProposalAction.CONSOLIDATE: 1,
    ProposalAction.WITHDRAW: 2,
}


class OptimizerAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class OptimizerUnavailableReason(str, Enum):
    DEPENDENCY_BLOCKED_NO_DECISION = "DEPENDENCY_BLOCKED_NO_DECISION"
    MISSING_OBSERVATIONS = "MISSING_OBSERVATIONS"
    PROGRAM_MISMATCH = "PROGRAM_MISMATCH"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    UNVERIFIED_INPUT = "UNVERIFIED_INPUT"
    COHORT_IMMATURE = "COHORT_IMMATURE"
    DENOMINATOR_UNAVAILABLE = "DENOMINATOR_UNAVAILABLE"
    ZERO_DENOMINATOR = "ZERO_DENOMINATOR"


class ProposalState(str, Enum):
    NO_PROPOSALS = "NO_PROPOSALS"
    HUMAN_REVIEW_PROPOSALS_ONLY = "HUMAN_REVIEW_PROPOSALS_ONLY"


class PortfolioOptimizerFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    RELEASE_DECISION_PROHIBITED = "RELEASE_DECISION_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"


class PortfolioOptimizerFailure(ValueError):
    """Closed failure that never retains rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: PortfolioOptimizerFailureCode) -> None:
        if type(code) is not PortfolioOptimizerFailureCode:
            raise TypeError("invalid portfolio optimizer failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"PortfolioOptimizerFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio optimizer failures cannot be serialized")


def fail_portfolio_optimizer(
    code: PortfolioOptimizerFailureCode = PortfolioOptimizerFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise PortfolioOptimizerFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio optimizer values cannot be serialized")


def canonical_json_bytes(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        fail_portfolio_optimizer()
    if not rendered or len(rendered) > MAX_SOURCE_BYTES:
        fail_portfolio_optimizer()
    return rendered


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_RedactedValue):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_portfolio_optimizer()


def digest_bytes(value: bytes) -> Sha256Digest:
    if type(value) is not bytes:
        fail_portfolio_optimizer()
    return Sha256Digest(hashlib.sha256(value).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_portfolio_optimizer()
    return Sha256Digest(value.value)


def _identifier(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 160
        or _IDENTIFIER.fullmatch(value) is None
    ):
        fail_portfolio_optimizer()
    return value


def _program(value: object) -> str:
    if type(value) is not str or _PROGRAM.fullmatch(value) is None:
        fail_portfolio_optimizer()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class ObservationPeriod(_RedactedValue):
    start_date: date
    end_exclusive_date: date

    def __post_init__(self) -> None:
        if (
            type(self.start_date) is not date
            or type(self.end_exclusive_date) is not date
            or self.end_exclusive_date
            != self.start_date + timedelta(days=PERIOD_DURATION_DAYS)
        ):
            fail_portfolio_optimizer()

    def payload(self) -> dict[str, object]:
        return {
            "duration_days": PERIOD_DURATION_DAYS,
            "end_exclusive_date": self.end_exclusive_date.isoformat(),
            "start_date": self.start_date.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioDecisionDependency(_RedactedValue):
    story_id: str
    pack_sha256: Sha256Digest
    readiness: DependencyReadiness
    acceptance_criteria_satisfied: bool
    actual_observation_count: int
    human_decision_present: bool
    local_integration_complete: bool
    source_authorized: bool
    source_overall: str | None = None
    source_outcome: str | None = None

    def __post_init__(self) -> None:
        if (
            self.story_id != "ST-1805"
            or type(self.readiness) is not DependencyReadiness
            or type(self.acceptance_criteria_satisfied) is not bool
            or type(self.actual_observation_count) is not int
            or not 0 <= self.actual_observation_count <= 10_000_000
            or type(self.human_decision_present) is not bool
            or type(self.local_integration_complete) is not bool
            or type(self.source_authorized) is not bool
        ):
            fail_portfolio_optimizer()
        _sha(self.pack_sha256)
        if self.readiness is DependencyReadiness.BLOCKED_NO_DECISION:
            if (
                self.acceptance_criteria_satisfied is not False
                or self.actual_observation_count != 0
                or self.human_decision_present is not False
                or self.local_integration_complete is not False
                or self.source_authorized is not False
                or self.source_overall != "BLOCKED"
                or self.source_outcome != "NO_DECISION"
            ):
                fail_portfolio_optimizer()
        elif (
            self.acceptance_criteria_satisfied is not True
            or self.actual_observation_count <= 0
            or self.human_decision_present is not True
            or self.local_integration_complete is not True
            or self.source_authorized is not True
            or self.source_overall is not None
            or self.source_outcome is not None
        ):
            fail_portfolio_optimizer()

    def payload(self) -> dict[str, object]:
        return {
            "acceptance_criteria_satisfied": self.acceptance_criteria_satisfied,
            "actual_observation_count": self.actual_observation_count,
            "human_decision_present": self.human_decision_present,
            "local_integration_complete": self.local_integration_complete,
            "pack_sha256": self.pack_sha256.value,
            "readiness": self.readiness.value,
            "source_authorized": self.source_authorized,
            "source_outcome": self.source_outcome,
            "source_overall": self.source_overall,
            "story_id": self.story_id,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioOptimizationSignal(_RedactedValue):
    signal_id: str
    action: ProposalAction
    basis: ProposalBasis
    article_ids: tuple[str, ...]
    source_sha256: Sha256Digest
    signal_policy_sha256: Sha256Digest
    program: str
    period: ObservationPeriod
    verification: SignalVerification
    cohort: CohortMaturity
    denominator_count: int | None
    finance_signal_present: bool = False
    personal_data_present: bool = False
    recommendation_order_change_requested: bool = False
    publication_mutation_requested: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.signal_id) is not str
            or not 1 <= len(self.signal_id) <= 96
            or _RECORDING_ID.fullmatch(self.signal_id) is None
            or type(self.action) is not ProposalAction
            or type(self.basis) is not ProposalBasis
            or _ACTION_BASIS.get(self.action) is not self.basis
            or type(self.article_ids) is not tuple
            or not self.article_ids
            or len(self.article_ids) > MAX_ARTICLES_PER_SIGNAL
            or any(
                _identifier(article_id) != article_id for article_id in self.article_ids
            )
            or tuple(sorted(set(self.article_ids))) != self.article_ids
            or (self.action is ProposalAction.CONSOLIDATE)
            != (len(self.article_ids) >= 2)
            or type(self.period) is not ObservationPeriod
            or type(self.verification) is not SignalVerification
            or type(self.cohort) is not CohortMaturity
            or (
                self.denominator_count is not None
                and (
                    type(self.denominator_count) is not int
                    or not 0 <= self.denominator_count <= (1 << 63) - 1
                )
            )
            or self.finance_signal_present is not False
            or self.personal_data_present is not False
            or self.recommendation_order_change_requested is not False
            or self.publication_mutation_requested is not False
        ):
            fail_portfolio_optimizer()
        _sha(self.source_sha256)
        _sha(self.signal_policy_sha256)
        _program(self.program)

    def proposal_material(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "article_ids": list(self.article_ids),
            "basis": self.basis.value,
            "signal_id": self.signal_id,
            "signal_policy_sha256": self.signal_policy_sha256.value,
            "source_sha256": self.source_sha256.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioOptimizerCommand(_RedactedValue):
    recording_id: str
    source_sha256: Sha256Digest
    source_bytes: int
    contract_sha256: Sha256Digest
    expected_dependency_pack_sha256: Sha256Digest
    measurement_contract_sha256: Sha256Digest
    signal_policy_sha256: Sha256Digest
    program: str
    period: ObservationPeriod
    release_decision_sha256: Sha256Digest | None = None
    method_version: str = METHOD_VERSION
    parser_version: str = PARSER_VERSION
    scope: PortfolioOptimizerScope = DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or not 1 <= len(self.recording_id) <= 96
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or type(self.period) is not ObservationPeriod
            or self.method_version != METHOD_VERSION
            or self.parser_version != PARSER_VERSION
            or type(self.scope) is not PortfolioOptimizerScope
        ):
            fail_portfolio_optimizer()
        for digest in (
            self.source_sha256,
            self.contract_sha256,
            self.expected_dependency_pack_sha256,
            self.measurement_contract_sha256,
            self.signal_policy_sha256,
        ):
            _sha(digest)
        _program(self.program)
        if self.release_decision_sha256 is not None:
            fail_portfolio_optimizer(
                PortfolioOptimizerFailureCode.RELEASE_DECISION_PROHIBITED
            )

    @property
    def canonical_sha256(self) -> Sha256Digest:
        return digest_bytes(
            canonical_json_bytes(
                {
                    "contract_sha256": self.contract_sha256.value,
                    "expected_dependency_pack_sha256": (
                        self.expected_dependency_pack_sha256.value
                    ),
                    "measurement_contract_sha256": (
                        self.measurement_contract_sha256.value
                    ),
                    "method_version": self.method_version,
                    "parser_version": self.parser_version,
                    "period": self.period.payload(),
                    "program": self.program,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "scope": self.scope.value,
                    "signal_policy_sha256": self.signal_policy_sha256.value,
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256.value,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPortfolioOptimizationBatch(_RedactedValue):
    recording_id: str
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    source_bytes: int
    contract_sha256: Sha256Digest
    dependency: PortfolioDecisionDependency
    measurement_contract_sha256: Sha256Digest
    signal_policy_sha256: Sha256Digest
    program: str
    period: ObservationPeriod
    fixture_profile: str
    parser_version: str
    signals: tuple[PortfolioOptimizationSignal, ...]

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _RECORDING_ID.fullmatch(self.recording_id) is None
            or type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or type(self.dependency) is not PortfolioDecisionDependency
            or type(self.period) is not ObservationPeriod
            or self.fixture_profile != FIXTURE_PROFILE
            or self.parser_version != PARSER_VERSION
            or type(self.signals) is not tuple
            or len(self.signals) > MAX_SIGNALS
            or any(
                type(signal) is not PortfolioOptimizationSignal
                for signal in self.signals
            )
        ):
            fail_portfolio_optimizer()
        for digest in (
            self.command_sha256,
            self.source_sha256,
            self.contract_sha256,
            self.measurement_contract_sha256,
            self.signal_policy_sha256,
        ):
            _sha(digest)
        _program(self.program)
        identities = tuple(signal.signal_id for signal in self.signals)
        candidates = tuple(
            (signal.action, signal.article_ids) for signal in self.signals
        )
        if len(set(identities)) != len(identities) or len(set(candidates)) != len(
            candidates
        ):
            fail_portfolio_optimizer(PortfolioOptimizerFailureCode.DUPLICATE_SIGNAL)


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioProposal(_RedactedValue):
    proposal_id: str
    action: ProposalAction
    basis: ProposalBasis
    article_ids: tuple[str, ...]
    signal_id: str
    source_sha256: Sha256Digest
    signal_policy_sha256: Sha256Digest

    def __post_init__(self) -> None:
        if (
            type(self.action) is not ProposalAction
            or type(self.basis) is not ProposalBasis
            or _ACTION_BASIS.get(self.action) is not self.basis
            or type(self.article_ids) is not tuple
            or not self.article_ids
            or any(
                _identifier(article_id) != article_id for article_id in self.article_ids
            )
            or type(self.signal_id) is not str
            or _RECORDING_ID.fullmatch(self.signal_id) is None
        ):
            fail_portfolio_optimizer()
        _sha(self.source_sha256)
        _sha(self.signal_policy_sha256)
        expected = (
            "st1907-proposal-"
            + digest_bytes(
                canonical_json_bytes(
                    {
                        "action": self.action.value,
                        "article_ids": list(self.article_ids),
                        "basis": self.basis.value,
                        "signal_id": self.signal_id,
                        "signal_policy_sha256": self.signal_policy_sha256.value,
                        "source_sha256": self.source_sha256.value,
                    }
                )
            ).value[:24]
        )
        if self.proposal_id != expected:
            fail_portfolio_optimizer()

    @classmethod
    def from_signal(cls, signal: PortfolioOptimizationSignal) -> PortfolioProposal:
        if type(signal) is not PortfolioOptimizationSignal:
            fail_portfolio_optimizer()
        proposal_id = (
            "st1907-proposal-"
            + digest_bytes(canonical_json_bytes(signal.proposal_material())).value[:24]
        )
        return cls(
            proposal_id=proposal_id,
            action=signal.action,
            basis=signal.basis,
            article_ids=signal.article_ids,
            signal_id=signal.signal_id,
            source_sha256=signal.source_sha256,
            signal_policy_sha256=signal.signal_policy_sha256,
        )

    def payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "actionable": False,
            "article_ids": list(self.article_ids),
            "automatic_apply": False,
            "basis": self.basis.value,
            "human_review_required": True,
            "mutation_authority": {
                "article_html": False,
                "cta": False,
                "editorial": False,
                "product_selection": False,
                "publication_snapshot": False,
                "recommendation_order": False,
            },
            "mutations_applied": [],
            "proposal_id": self.proposal_id,
            "proposal_kind": "HUMAN_REVIEW_METADATA_ONLY",
            "signal_id": self.signal_id,
            "signal_policy_sha256": self.signal_policy_sha256.value,
            "source_sha256": self.source_sha256.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioOptimizerAuthority(_RedactedValue):
    activation: bool = False
    approval: bool = False
    proposal_apply: bool = False
    status_apply: bool = False
    provider_call: bool = False
    network: bool = False
    credential_access: bool = False
    persistence: bool = False
    editorial_mutation: bool = False
    article_html_mutation: bool = False
    cta_mutation: bool = False
    product_selection_mutation: bool = False
    recommendation_order_mutation: bool = False
    publication_snapshot_mutation: bool = False
    public_projection: bool = False
    publication: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_portfolio_optimizer()

    def payload(self) -> dict[str, object]:
        return {name: False for name in self.__slots__}


_FORMAL_BLOCKERS: Final = (
    "FORMAL_TST_032_NOT_EXECUTED",
    "RECORDED_SYNTHETIC_ONLY",
    "SEPARATE_RELEASE_DECISION_REQUIRED",
)


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioOptimizationReport(_RedactedValue):
    report_sha256: Sha256Digest
    command_sha256: Sha256Digest
    source_sha256: Sha256Digest
    contract_sha256: Sha256Digest
    dependency: PortfolioDecisionDependency
    measurement_contract_sha256: Sha256Digest
    signal_policy_sha256: Sha256Digest
    availability: OptimizerAvailability
    unavailable_reason: OptimizerUnavailableReason | None
    proposal_state: ProposalState
    proposals: tuple[PortfolioProposal, ...]
    blockers: tuple[str, ...]
    authority: PortfolioOptimizerAuthority = field(
        default_factory=PortfolioOptimizerAuthority
    )

    def __post_init__(self) -> None:
        for digest in (
            self.report_sha256,
            self.command_sha256,
            self.source_sha256,
            self.contract_sha256,
            self.measurement_contract_sha256,
            self.signal_policy_sha256,
        ):
            _sha(digest)
        if (
            type(self.dependency) is not PortfolioDecisionDependency
            or type(self.availability) is not OptimizerAvailability
            or type(self.proposal_state) is not ProposalState
            or type(self.proposals) is not tuple
            or any(
                type(proposal) is not PortfolioProposal for proposal in self.proposals
            )
            or type(self.blockers) is not tuple
            or not self.blockers
            or tuple(sorted(set(self.blockers))) != self.blockers
            or type(self.authority) is not PortfolioOptimizerAuthority
        ):
            fail_portfolio_optimizer()
        if self.availability is OptimizerAvailability.AVAILABLE:
            if (
                self.unavailable_reason is not None
                or self.proposal_state is not ProposalState.HUMAN_REVIEW_PROPOSALS_ONLY
                or not self.proposals
            ):
                fail_portfolio_optimizer()
        elif (
            type(self.unavailable_reason) is not OptimizerUnavailableReason
            or self.proposal_state is not ProposalState.NO_PROPOSALS
            or self.proposals
        ):
            fail_portfolio_optimizer()

    def payload(self, *, include_report_sha256: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "authority": self.authority.payload(),
            "availability": self.availability.value,
            "blockers": list(self.blockers),
            "command_sha256": self.command_sha256.value,
            "contract_sha256": self.contract_sha256.value,
            "dependency": self.dependency.payload(),
            "measurement_contract_sha256": self.measurement_contract_sha256.value,
            "method_version": METHOD_VERSION,
            "policy": {
                "action_vocabulary": [action.value for action in ProposalAction],
                "automatic_apply": False,
                "finance_values_represented": False,
                "human_proposal_only": True,
                "proposal_order_is_recommendation_order": False,
                "recommendation_inputs_excluded": list(RECOMMENDATION_INPUTS_EXCLUDED),
                "thresholds_selected_by_this_story": False,
            },
            "proposal_count": len(self.proposals),
            "proposal_state": self.proposal_state.value,
            "proposals": [proposal.payload() for proposal in self.proposals],
            "signal_policy_sha256": self.signal_policy_sha256.value,
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


def _with_report_hash(
    report: PortfolioOptimizationReport,
) -> PortfolioOptimizationReport:
    digest = digest_bytes(
        canonical_json_bytes(report.payload(include_report_sha256=False))
    )
    return PortfolioOptimizationReport(
        report_sha256=digest,
        command_sha256=report.command_sha256,
        source_sha256=report.source_sha256,
        contract_sha256=report.contract_sha256,
        dependency=report.dependency,
        measurement_contract_sha256=report.measurement_contract_sha256,
        signal_policy_sha256=report.signal_policy_sha256,
        availability=report.availability,
        unavailable_reason=report.unavailable_reason,
        proposal_state=report.proposal_state,
        proposals=report.proposals,
        blockers=report.blockers,
        authority=report.authority,
    )


def _unavailable(
    command: PortfolioOptimizerCommand,
    batch: RecordedPortfolioOptimizationBatch,
    reason: OptimizerUnavailableReason,
) -> PortfolioOptimizationReport:
    blockers = tuple(sorted((*_FORMAL_BLOCKERS, reason.value)))
    preliminary = PortfolioOptimizationReport(
        report_sha256=Sha256Digest("0" * 64),
        command_sha256=command.canonical_sha256,
        source_sha256=batch.source_sha256,
        contract_sha256=command.contract_sha256,
        dependency=batch.dependency,
        measurement_contract_sha256=batch.measurement_contract_sha256,
        signal_policy_sha256=batch.signal_policy_sha256,
        availability=OptimizerAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        proposal_state=ProposalState.NO_PROPOSALS,
        proposals=(),
        blockers=blockers,
    )
    return _with_report_hash(preliminary)


def evaluate_recorded_portfolio_optimization(
    command: PortfolioOptimizerCommand,
    batch: RecordedPortfolioOptimizationBatch,
) -> PortfolioOptimizationReport:
    """Return human-review metadata only after every evidence gate passes."""

    if (
        type(command) is not PortfolioOptimizerCommand
        or type(batch) is not RecordedPortfolioOptimizationBatch
    ):
        fail_portfolio_optimizer()
    if (
        command.scope
        is not PortfolioOptimizerScope.RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY
    ):
        fail_portfolio_optimizer(PortfolioOptimizerFailureCode.FEATURE_DISABLED)
    if (
        batch.recording_id != command.recording_id
        or batch.command_sha256 != command.canonical_sha256
        or batch.source_sha256 != command.source_sha256
        or batch.source_bytes != command.source_bytes
        or batch.contract_sha256 != command.contract_sha256
        or batch.dependency.pack_sha256 != command.expected_dependency_pack_sha256
        or batch.measurement_contract_sha256 != command.measurement_contract_sha256
        or batch.signal_policy_sha256 != command.signal_policy_sha256
        or batch.fixture_profile != FIXTURE_PROFILE
        or batch.parser_version != command.parser_version
    ):
        fail_portfolio_optimizer(PortfolioOptimizerFailureCode.SOURCE_RESULT_INVALID)
    if batch.dependency.readiness is DependencyReadiness.BLOCKED_NO_DECISION:
        return _unavailable(
            command,
            batch,
            OptimizerUnavailableReason.DEPENDENCY_BLOCKED_NO_DECISION,
        )
    if not batch.signals:
        return _unavailable(
            command, batch, OptimizerUnavailableReason.MISSING_OBSERVATIONS
        )
    if batch.program != command.program or any(
        signal.program != command.program for signal in batch.signals
    ):
        return _unavailable(command, batch, OptimizerUnavailableReason.PROGRAM_MISMATCH)
    if batch.period != command.period or any(
        signal.period != command.period for signal in batch.signals
    ):
        return _unavailable(command, batch, OptimizerUnavailableReason.PERIOD_MISMATCH)
    if any(
        signal.signal_policy_sha256 != command.signal_policy_sha256
        or signal.verification is not SignalVerification.VERIFIED
        for signal in batch.signals
    ):
        return _unavailable(command, batch, OptimizerUnavailableReason.UNVERIFIED_INPUT)
    if any(signal.cohort is not CohortMaturity.MATURE for signal in batch.signals):
        return _unavailable(command, batch, OptimizerUnavailableReason.COHORT_IMMATURE)
    if any(signal.denominator_count is None for signal in batch.signals):
        return _unavailable(
            command, batch, OptimizerUnavailableReason.DENOMINATOR_UNAVAILABLE
        )
    if any(signal.denominator_count == 0 for signal in batch.signals):
        return _unavailable(command, batch, OptimizerUnavailableReason.ZERO_DENOMINATOR)

    ordered = tuple(
        sorted(
            batch.signals,
            key=lambda signal: (
                _ACTION_ORDER[signal.action],
                signal.article_ids,
                signal.signal_id,
            ),
        )
    )
    proposals = tuple(PortfolioProposal.from_signal(signal) for signal in ordered)
    preliminary = PortfolioOptimizationReport(
        report_sha256=Sha256Digest("0" * 64),
        command_sha256=command.canonical_sha256,
        source_sha256=batch.source_sha256,
        contract_sha256=command.contract_sha256,
        dependency=batch.dependency,
        measurement_contract_sha256=batch.measurement_contract_sha256,
        signal_policy_sha256=batch.signal_policy_sha256,
        availability=OptimizerAvailability.AVAILABLE,
        unavailable_reason=None,
        proposal_state=ProposalState.HUMAN_REVIEW_PROPOSALS_ONLY,
        proposals=proposals,
        blockers=tuple(sorted(_FORMAL_BLOCKERS)),
    )
    return _with_report_hash(preliminary)


__all__ = (
    "CONTRACT_VERSION",
    "DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE",
    "FIXTURE_PROFILE",
    "MAX_SOURCE_BYTES",
    "METHOD_VERSION",
    "PARSER_VERSION",
    "PERIOD_DURATION_DAYS",
    "PROGRAM",
    "RECOMMENDATION_INPUTS_EXCLUDED",
    "CohortMaturity",
    "DependencyReadiness",
    "ObservationPeriod",
    "OptimizerAvailability",
    "OptimizerUnavailableReason",
    "PortfolioDecisionDependency",
    "PortfolioOptimizationReport",
    "PortfolioOptimizationSignal",
    "PortfolioOptimizerAuthority",
    "PortfolioOptimizerCommand",
    "PortfolioOptimizerFailure",
    "PortfolioOptimizerFailureCode",
    "PortfolioOptimizerScope",
    "PortfolioProposal",
    "ProposalAction",
    "ProposalBasis",
    "ProposalState",
    "RecordedPortfolioOptimizationBatch",
    "Sha256Digest",
    "SignalVerification",
    "canonical_json_bytes",
    "digest_bytes",
    "evaluate_recorded_portfolio_optimization",
    "fail_portfolio_optimizer",
)
