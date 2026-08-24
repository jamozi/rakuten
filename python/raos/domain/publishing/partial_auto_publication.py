"""Maximum-safe values for the disabled ST-1903 evaluation seam.

The module can describe only sanitized metadata for a contraction-only change.
It has no publication command, CMS payload, URL, credential, release activation,
or positive publication outcome.  Every report remains a refusal that requires a
separate future human release decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex


PARTIAL_AUTO_PUBLICATION_CONTRACT_VERSION: Final = "1.0.0"
PARTIAL_AUTO_PUBLICATION_METHOD_VERSION: Final = (
    "RAOS_ST1903_DISABLED_RECORDED_ELIGIBILITY_V1"
)
PARTIAL_AUTO_PUBLICATION_PARSER_VERSION: Final = (
    "st1903-recorded-partial-auto-publication-json.v1"
)
PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE: Final = (
    "RAOS_ST1903_RECORDED_SYNTHETIC_ELIGIBILITY_V1"
)
MAX_SOURCE_BYTES: Final = 1_048_576
MAX_IDENTIFIER_LENGTH: Final = 160

TRUSTED_ST1805_CONTRACT_SHA256: Final = (
    "dd6c742d295f5bc7baa036aa6cca0a42e84b7a3168f0302aec8e40e46a87f4b9"
)
TRUSTED_ST1805_FIXTURE_SHA256: Final = (
    "c2b06e525c3d5c8e86997cbd67285eedad85c9b90fd12f95f162d6a6c6fc910e"
)
TRUSTED_ST1805_PACK_SHA256: Final = (
    "1288a29454435293fc47ff556215c5afee6e58fad8b995b13e4aca81d2535e22"
)
TRUSTED_ST1805_GENERATOR_SHA256: Final = (
    "79ed861e82efd80b10e884028fd99b122ac3b1713b66d63203c671162fdbb23e"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z", re.ASCII)
_RECORDING_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z", re.ASCII)
_REDACTED: Final = "<redacted-partial-auto-publication>"


class PartialAutoPublicationScope(str, Enum):
    """Closed local states; no live, activation, or publish state exists."""

    DISABLED = "DISABLED"
    RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY = (
        "RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY"
    )


DEFAULT_PARTIAL_AUTO_PUBLICATION_SCOPE: Final = PartialAutoPublicationScope.DISABLED


class LowRiskChangeClass(str, Enum):
    """Only deterministic safety contractions are representable."""

    STALE_VALUE_SUPPRESSION_ONLY = "STALE_VALUE_SUPPRESSION_ONLY"
    INVALID_AFFILIATE_CTA_DISABLEMENT_ONLY = "INVALID_AFFILIATE_CTA_DISABLEMENT_ONLY"


class PartialAutoPublicationOutcome(str, Enum):
    """Closed refusal outcomes; intentionally no publish/eligible member."""

    REFUSED_AMBIGUOUS_OR_HIGH_RISK = "REFUSED_AMBIGUOUS_OR_HIGH_RISK"
    REFUSED_DEPENDENCY_BLOCKED = "REFUSED_DEPENDENCY_BLOCKED"
    REFUSED_REQUIRED_EVIDENCE_UNAVAILABLE = "REFUSED_REQUIRED_EVIDENCE_UNAVAILABLE"


class CriterionStatus(str, Enum):
    PASS_RECORDED_SYNTHETIC_ONLY = "PASS_RECORDED_SYNTHETIC_ONLY"
    REFUSED = "REFUSED"
    UNAVAILABLE = "UNAVAILABLE"


class PartialAutoPublicationFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    RELEASE_DECISION_INPUT_PROHIBITED = "RELEASE_DECISION_INPUT_PROHIBITED"
    SOURCE_BYTES_MISMATCH = "SOURCE_BYTES_MISMATCH"
    SOURCE_DOCUMENT_INVALID = "SOURCE_DOCUMENT_INVALID"
    SOURCE_EXHAUSTED = "SOURCE_EXHAUSTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_RESULT_INVALID = "SOURCE_RESULT_INVALID"
    DEPENDENCY_CONTRACT_DRIFT = "DEPENDENCY_CONTRACT_DRIFT"


class PartialAutoPublicationFailure(ValueError):
    """Stable failure that never retains rejected source material."""

    __slots__ = ("code",)

    def __init__(self, code: PartialAutoPublicationFailureCode) -> None:
        if type(code) is not PartialAutoPublicationFailureCode:
            raise TypeError("invalid partial auto-publication failure code")
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PartialAutoPublicationFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("partial auto-publication failures cannot be serialized")


def fail_partial_auto_publication(
    code: PartialAutoPublicationFailureCode = (
        PartialAutoPublicationFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise PartialAutoPublicationFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("partial auto-publication values cannot be serialized")


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
        fail_partial_auto_publication()


def sha256_bytes(value: bytes) -> str:
    if type(value) is not bytes:
        fail_partial_auto_publication()
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_partial_auto_publication()
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        fail_partial_auto_publication()
    return value


def _recording_id(value: object) -> str:
    if type(value) is not str or _RECORDING_ID.fullmatch(value) is None:
        fail_partial_auto_publication()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class PartialAutoPublicationCommand(_RedactedValue):
    """One caller-bytes request for local eligibility evaluation only."""

    recording_id: str
    source_sha256: str
    source_bytes: int
    scope: PartialAutoPublicationScope = DEFAULT_PARTIAL_AUTO_PUBLICATION_SCOPE
    parser_version: str = PARTIAL_AUTO_PUBLICATION_PARSER_VERSION
    release_decision_sha256: str | None = None

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        _digest(self.source_sha256)
        if (
            type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or type(self.scope) is not PartialAutoPublicationScope
            or self.parser_version != PARTIAL_AUTO_PUBLICATION_PARSER_VERSION
        ):
            fail_partial_auto_publication()
        if self.release_decision_sha256 is not None:
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.RELEASE_DECISION_INPUT_PROHIBITED
            )

    @property
    def canonical_sha256(self) -> str:
        return sha256_bytes(
            canonical_json_bytes(
                {
                    "parser_version": self.parser_version,
                    "recording_id": self.recording_id,
                    "release_decision_sha256": None,
                    "scope": self.scope.value,
                    "source_bytes": self.source_bytes,
                    "source_sha256": self.source_sha256,
                }
            )
        )


@dataclass(frozen=True, slots=True, repr=False)
class PartialAutoPublicationCandidate(_RedactedValue):
    """Sanitized metadata; content, URL, HTML, and CMS payloads are absent."""

    candidate_id: str
    article_id: str
    candidate_sha256: str
    change_class: LowRiskChangeClass
    change_count: int
    synthetic: bool
    risk_ambiguous: bool
    high_risk: bool
    content_addition: bool
    claim_change: bool
    recommendation_order_change: bool
    product_identity_change: bool
    affiliate_destination_change: bool
    raw_html_present: bool
    price_or_stock_assertion_added: bool
    personal_data_present: bool
    finance_input_present: bool
    public_write_requested: bool

    def __post_init__(self) -> None:
        _identifier(self.candidate_id)
        _identifier(self.article_id)
        _digest(self.candidate_sha256)
        if (
            type(self.change_class) is not LowRiskChangeClass
            or type(self.change_count) is not int
            or self.change_count != 1
            or self.synthetic is not True
            or any(
                type(value) is not bool
                for value in (
                    self.risk_ambiguous,
                    self.high_risk,
                    self.content_addition,
                    self.claim_change,
                    self.recommendation_order_change,
                    self.product_identity_change,
                    self.affiliate_destination_change,
                    self.raw_html_present,
                    self.price_or_stock_assertion_added,
                    self.personal_data_present,
                    self.finance_input_present,
                    self.public_write_requested,
                )
            )
        ):
            fail_partial_auto_publication()
        if self.candidate_sha256 != candidate_material_sha256(self):
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
            )


def candidate_material(candidate: PartialAutoPublicationCandidate) -> dict[str, object]:
    if type(candidate) is not PartialAutoPublicationCandidate:
        fail_partial_auto_publication()
    return {
        "affiliate_destination_change": candidate.affiliate_destination_change,
        "article_id": candidate.article_id,
        "candidate_id": candidate.candidate_id,
        "change_class": candidate.change_class.value,
        "change_count": candidate.change_count,
        "claim_change": candidate.claim_change,
        "content_addition": candidate.content_addition,
        "finance_input_present": candidate.finance_input_present,
        "high_risk": candidate.high_risk,
        "personal_data_present": candidate.personal_data_present,
        "price_or_stock_assertion_added": candidate.price_or_stock_assertion_added,
        "product_identity_change": candidate.product_identity_change,
        "public_write_requested": candidate.public_write_requested,
        "raw_html_present": candidate.raw_html_present,
        "recommendation_order_change": candidate.recommendation_order_change,
        "risk_ambiguous": candidate.risk_ambiguous,
        "synthetic": candidate.synthetic,
    }


def candidate_material_sha256(candidate: PartialAutoPublicationCandidate) -> str:
    return sha256_bytes(canonical_json_bytes(candidate_material(candidate)))


@dataclass(frozen=True, slots=True, repr=False)
class BlockedPortfolioDependency(_RedactedValue):
    story_id: str
    pack_sha256: str
    overall: str
    outcome: str
    authorized: bool
    acceptance_criteria_satisfied: bool
    human_decision_required: bool
    local_integration_complete: bool

    def __post_init__(self) -> None:
        if (
            self.story_id != "ST-1805"
            or _digest(self.pack_sha256) != TRUSTED_ST1805_PACK_SHA256
            or self.overall != "BLOCKED"
            or self.outcome != "NO_DECISION"
            or self.authorized is not False
            or self.acceptance_criteria_satisfied is not False
            or self.human_decision_required is not True
            or self.local_integration_complete is not False
        ):
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.DEPENDENCY_CONTRACT_DRIFT
            )


@dataclass(frozen=True, slots=True, repr=False)
class UnavailableReleaseGates(_RedactedValue):
    formal_tst032: str
    separate_human_release_decision: str
    security_review: str
    operations_review: str
    kill_switch_state: str
    idempotency_evidence: str
    rollback_evidence: str
    actual_publication_execution: bool
    actual_public_write: bool

    def __post_init__(self) -> None:
        if (
            self.formal_tst032 != "NOT_EXECUTED"
            or self.separate_human_release_decision != "ABSENT"
            or self.security_review != "NOT_EXECUTED"
            or self.operations_review != "NOT_EXECUTED"
            or self.kill_switch_state != "UNKNOWN"
            or self.idempotency_evidence != "UNAVAILABLE"
            or self.rollback_evidence != "UNAVAILABLE"
            or self.actual_publication_execution is not False
            or self.actual_public_write is not False
        ):
            fail_partial_auto_publication(
                PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedPartialAutoPublicationBundle(_RedactedValue):
    recording_id: str
    command_sha256: str
    source_sha256: str
    source_bytes: int
    fixture_profile: str
    parser_version: str
    candidate: PartialAutoPublicationCandidate
    dependency: BlockedPortfolioDependency
    gates: UnavailableReleaseGates

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        _digest(self.command_sha256)
        _digest(self.source_sha256)
        if (
            type(self.source_bytes) is not int
            or not 1 <= self.source_bytes <= MAX_SOURCE_BYTES
            or self.fixture_profile != PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE
            or self.parser_version != PARTIAL_AUTO_PUBLICATION_PARSER_VERSION
            or type(self.candidate) is not PartialAutoPublicationCandidate
            or type(self.dependency) is not BlockedPortfolioDependency
            or type(self.gates) is not UnavailableReleaseGates
        ):
            fail_partial_auto_publication()


@dataclass(frozen=True, slots=True, repr=False)
class PartialAutoPublicationCriterion(_RedactedValue):
    code: str
    status: CriterionStatus
    reason: str

    def __post_init__(self) -> None:
        _identifier(self.code)
        _identifier(self.reason)
        if type(self.status) is not CriterionStatus:
            fail_partial_auto_publication()

    def payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "reason": self.reason,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class PartialAutoPublicationReport(_RedactedValue):
    recording_id: str
    command_sha256: str
    source_sha256: str
    candidate: PartialAutoPublicationCandidate
    dependency: BlockedPortfolioDependency
    criteria: tuple[PartialAutoPublicationCriterion, ...]
    outcome: PartialAutoPublicationOutcome

    def __post_init__(self) -> None:
        _recording_id(self.recording_id)
        _digest(self.command_sha256)
        _digest(self.source_sha256)
        if (
            type(self.candidate) is not PartialAutoPublicationCandidate
            or type(self.dependency) is not BlockedPortfolioDependency
            or type(self.criteria) is not tuple
            or len(self.criteria) != 9
            or any(
                type(row) is not PartialAutoPublicationCriterion
                for row in self.criteria
            )
            or len({row.code for row in self.criteria}) != len(self.criteria)
            or type(self.outcome) is not PartialAutoPublicationOutcome
        ):
            fail_partial_auto_publication()

    def payload(self) -> dict[str, object]:
        return {
            "actions": [],
            "authority": {
                "activation": False,
                "approval": False,
                "cms": False,
                "credentials": False,
                "network": False,
                "production": False,
                "public_write": False,
                "publication": False,
                "release": False,
                "staging": False,
                "status_apply": False,
            },
            "candidate": {
                "article_id": self.candidate.article_id,
                "candidate_id": self.candidate.candidate_id,
                "candidate_sha256": self.candidate.candidate_sha256,
                "change_class": self.candidate.change_class.value,
                "change_count": self.candidate.change_count,
                "synthetic": True,
            },
            "command_sha256": self.command_sha256,
            "criteria": [row.payload() for row in self.criteria],
            "dependency": {
                "acceptance_criteria_satisfied": False,
                "authorized": False,
                "human_decision_required": True,
                "local_integration_complete": False,
                "outcome": "NO_DECISION",
                "overall": "BLOCKED",
                "pack_sha256": self.dependency.pack_sha256,
                "story_id": "ST-1805",
            },
            "effects": [],
            "feature_scope": (
                PartialAutoPublicationScope.RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY.value
            ),
            "future_human_release_decision_required": True,
            "method_version": PARTIAL_AUTO_PUBLICATION_METHOD_VERSION,
            "mutations_applied": [],
            "outcome": self.outcome.value,
            "positive_publication_outcome_exists": False,
            "recording_id": self.recording_id,
            "source_sha256": self.source_sha256,
            "story_id": "ST-1903",
        }


def _candidate_is_ambiguous_or_high_risk(
    candidate: PartialAutoPublicationCandidate,
) -> bool:
    return any(
        (
            candidate.risk_ambiguous,
            candidate.high_risk,
            candidate.content_addition,
            candidate.claim_change,
            candidate.recommendation_order_change,
            candidate.product_identity_change,
            candidate.affiliate_destination_change,
            candidate.raw_html_present,
            candidate.price_or_stock_assertion_added,
            candidate.personal_data_present,
            candidate.finance_input_present,
            candidate.public_write_requested,
        )
    )


def evaluate_partial_auto_publication(
    bundle: RecordedPartialAutoPublicationBundle,
) -> PartialAutoPublicationReport:
    """Return refusal-only evidence; never approve or execute publication."""

    if type(bundle) is not RecordedPartialAutoPublicationBundle:
        fail_partial_auto_publication(
            PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
        )
    ambiguous = _candidate_is_ambiguous_or_high_risk(bundle.candidate)
    outcome = (
        PartialAutoPublicationOutcome.REFUSED_AMBIGUOUS_OR_HIGH_RISK
        if ambiguous
        else PartialAutoPublicationOutcome.REFUSED_DEPENDENCY_BLOCKED
    )
    criteria = (
        PartialAutoPublicationCriterion(
            "CHANGE_CLASS_CLOSED",
            CriterionStatus.PASS_RECORDED_SYNTHETIC_ONLY,
            "CONTRACTION_ONLY_CLASS_RECORDED",
        ),
        PartialAutoPublicationCriterion(
            "AMBIGUITY_ABSENT",
            CriterionStatus.REFUSED
            if ambiguous
            else CriterionStatus.PASS_RECORDED_SYNTHETIC_ONLY,
            "AMBIGUOUS_OR_HIGH_RISK" if ambiguous else "NO_AMBIGUITY_RECORDED",
        ),
        PartialAutoPublicationCriterion(
            "CONTENT_SCOPE_CONTRACTION_ONLY",
            CriterionStatus.REFUSED
            if ambiguous
            else CriterionStatus.PASS_RECORDED_SYNTHETIC_ONLY,
            "MUTATION_OR_ASSERTION_REQUESTED"
            if ambiguous
            else "NO_CONTENT_EXPANSION_RECORDED",
        ),
        PartialAutoPublicationCriterion(
            "ST1805_PORTFOLIO_DECISION",
            CriterionStatus.UNAVAILABLE,
            "ST1805_BLOCKED_NO_DECISION",
        ),
        PartialAutoPublicationCriterion(
            "FORMAL_TST032",
            CriterionStatus.UNAVAILABLE,
            "FORMAL_TST032_NOT_EXECUTED",
        ),
        PartialAutoPublicationCriterion(
            "SEPARATE_HUMAN_RELEASE_DECISION",
            CriterionStatus.UNAVAILABLE,
            "SEPARATE_RELEASE_DECISION_ABSENT",
        ),
        PartialAutoPublicationCriterion(
            "SECURITY_AND_OPERATIONS_REVIEW",
            CriterionStatus.UNAVAILABLE,
            "SECURITY_OPERATIONS_REVIEW_NOT_EXECUTED",
        ),
        PartialAutoPublicationCriterion(
            "KILL_SWITCH_SAFE_STATE",
            CriterionStatus.UNAVAILABLE,
            "KILL_SWITCH_STATE_UNKNOWN",
        ),
        PartialAutoPublicationCriterion(
            "IDEMPOTENCY_AND_ROLLBACK_EVIDENCE",
            CriterionStatus.UNAVAILABLE,
            "IDEMPOTENCY_ROLLBACK_EVIDENCE_UNAVAILABLE",
        ),
    )
    return PartialAutoPublicationReport(
        recording_id=bundle.recording_id,
        command_sha256=bundle.command_sha256,
        source_sha256=bundle.source_sha256,
        candidate=bundle.candidate,
        dependency=bundle.dependency,
        criteria=criteria,
        outcome=outcome,
    )


__all__ = (
    "DEFAULT_PARTIAL_AUTO_PUBLICATION_SCOPE",
    "LowRiskChangeClass",
    "PARTIAL_AUTO_PUBLICATION_CONTRACT_VERSION",
    "PARTIAL_AUTO_PUBLICATION_FIXTURE_PROFILE",
    "PARTIAL_AUTO_PUBLICATION_METHOD_VERSION",
    "PARTIAL_AUTO_PUBLICATION_PARSER_VERSION",
    "PartialAutoPublicationCandidate",
    "PartialAutoPublicationCommand",
    "PartialAutoPublicationFailure",
    "PartialAutoPublicationFailureCode",
    "PartialAutoPublicationOutcome",
    "PartialAutoPublicationReport",
    "PartialAutoPublicationScope",
    "RecordedPartialAutoPublicationBundle",
    "TRUSTED_ST1805_CONTRACT_SHA256",
    "TRUSTED_ST1805_FIXTURE_SHA256",
    "TRUSTED_ST1805_GENERATOR_SHA256",
    "TRUSTED_ST1805_PACK_SHA256",
    "UnavailableReleaseGates",
    "BlockedPortfolioDependency",
    "candidate_material",
    "candidate_material_sha256",
    "canonical_json_bytes",
    "evaluate_partial_auto_publication",
    "fail_partial_auto_publication",
    "sha256_bytes",
)
