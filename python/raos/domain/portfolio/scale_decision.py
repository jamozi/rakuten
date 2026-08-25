"""Fail-closed, non-attesting portfolio decision boundary for ST-1805.

This module can evaluate one immutable recorded/synthetic dependency summary.
It cannot approve GATE-3, choose SCALE/HOLD/PIVOT, change a category limit,
rank products, mutate editorial state, or perform any external operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex, final

from raos.domain.analytics.kpi_read_model import RAKUTEN_BLOG_PROGRAM


PROGRAM: Final = RAKUTEN_BLOG_PROGRAM
FIXTURE_SCHEMA: Final = "ST1805_RECORDED_SYNTHETIC_PORTFOLIO_DECISION_V1"
REPORT_SCHEMA: Final = "ST1805_PORTFOLIO_DECISION_REPORT_V1"
METHOD_VERSION: Final = "RAOS_ST1805_PORTFOLIO_DECISION_V1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_MAX_BYTES = 1024 * 1024
_REDACTED = "<redacted-portfolio-decision>"


class PortfolioDecisionFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FIXTURE_BYTES_MISMATCH = "FIXTURE_BYTES_MISMATCH"
    FIXTURE_DOCUMENT_INVALID = "FIXTURE_DOCUMENT_INVALID"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    RECORDED_EXCHANGE_EXHAUSTED = "RECORDED_EXCHANGE_EXHAUSTED"
    RECORDED_RESULT_MISMATCH = "RECORDED_RESULT_MISMATCH"


class EvidenceState(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"
    UNAVAILABLE = "UNAVAILABLE"
    RECORDED_SYNTHETIC_NON_ATTESTING = "RECORDED_SYNTHETIC_NON_ATTESTING"


class EvidenceAvailability(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"


class DecisionOutcome(str, Enum):
    NO_DECISION = "NO_DECISION"


class DecisionOverall(str, Enum):
    BLOCKED = "BLOCKED"


class CriterionStatus(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


@final
class PortfolioDecisionFailure(RuntimeError):
    __slots__ = ("code",)

    def __init__(self, code: PortfolioDecisionFailureCode) -> None:
        if type(code) is not PortfolioDecisionFailureCode:
            raise TypeError("invalid portfolio decision failure code")
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"PortfolioDecisionFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio decision failure serialization is forbidden")


def fail_portfolio_decision(
    code: PortfolioDecisionFailureCode = PortfolioDecisionFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise PortfolioDecisionFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("portfolio decision serialization is forbidden")


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_portfolio_decision()

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            fail_portfolio_decision()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class FixtureByteLength(_Redacted):
    value: int

    def __post_init__(self) -> None:
        if type(self.value) is not int or not 0 < self.value <= _MAX_BYTES:
            fail_portfolio_decision()


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioDecisionCommand(_Redacted):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    expected_input_digest: Sha256Digest
    expected_source_pack_digest: Sha256Digest
    program_id: str

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _TOKEN.fullmatch(self.recording_id) is None
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.expected_input_digest) is not Sha256Digest
            or type(self.expected_source_pack_digest) is not Sha256Digest
            or self.program_id != PROGRAM
        ):
            fail_portfolio_decision()


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioDecisionEvidence(_Redacted):
    recording_id: str
    fixture_digest: Sha256Digest
    fixture_length: FixtureByteLength
    contract_digest: Sha256Digest
    input_digest: Sha256Digest
    source_pack_digest: Sha256Digest
    program_id: str
    dependency_schema: str
    dependency_overall: str
    dependency_gate_pass_claim: bool
    dependency_actual_observation_count: int
    dependency_acceptance_criteria_satisfied: bool
    dependency_scale_authority: str
    quality_state: EvidenceState
    economics_state: EvidenceState
    risk_state: EvidenceState
    formal_tst032_state: EvidenceState
    human_decision_present: bool
    synthetic: bool
    actual_observation: bool

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _TOKEN.fullmatch(self.recording_id) is None
            or type(self.fixture_digest) is not Sha256Digest
            or type(self.fixture_length) is not FixtureByteLength
            or type(self.contract_digest) is not Sha256Digest
            or type(self.input_digest) is not Sha256Digest
            or type(self.source_pack_digest) is not Sha256Digest
            or self.program_id != PROGRAM
            or self.dependency_schema != "ST1804_GATE3_PACK_V1"
            or self.dependency_overall != "BLOCKED"
            or self.dependency_gate_pass_claim is not False
            or type(self.dependency_actual_observation_count) is not int
            or self.dependency_actual_observation_count != 0
            or self.dependency_acceptance_criteria_satisfied is not False
            or self.dependency_scale_authority != "NONE"
            or self.quality_state is not EvidenceState.NOT_EXECUTED
            or self.economics_state
            is not EvidenceState.RECORDED_SYNTHETIC_NON_ATTESTING
            or self.risk_state is not EvidenceState.NOT_EXECUTED
            or self.formal_tst032_state is not EvidenceState.NOT_EXECUTED
            or self.human_decision_present is not False
            or self.synthetic is not True
            or self.actual_observation is not False
        ):
            fail_portfolio_decision()


def canonical_input_digest(evidence: PortfolioDecisionEvidence) -> Sha256Digest:
    if type(evidence) is not PortfolioDecisionEvidence:
        fail_portfolio_decision()
    payload = {
        "actual_observation": evidence.actual_observation,
        "dependency_acceptance_criteria_satisfied": (
            evidence.dependency_acceptance_criteria_satisfied
        ),
        "dependency_actual_observation_count": (
            evidence.dependency_actual_observation_count
        ),
        "dependency_gate_pass_claim": evidence.dependency_gate_pass_claim,
        "dependency_overall": evidence.dependency_overall,
        "dependency_scale_authority": evidence.dependency_scale_authority,
        "dependency_schema": evidence.dependency_schema,
        "economics_state": evidence.economics_state.value,
        "formal_tst032_state": evidence.formal_tst032_state.value,
        "human_decision_present": evidence.human_decision_present,
        "program": evidence.program_id,
        "quality_state": evidence.quality_state.value,
        "risk_state": evidence.risk_state.value,
        "source_pack_sha256": evidence.source_pack_digest.value,
        "synthetic": evidence.synthetic,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return Sha256Digest.of(encoded)


@dataclass(frozen=True, slots=True, repr=False)
class PortfolioDecisionReport(_Redacted):
    recording_id: str
    input_digest: Sha256Digest
    source_pack_digest: Sha256Digest
    quality_state: EvidenceState
    economics_state: EvidenceState
    risk_state: EvidenceState
    formal_tst032_state: EvidenceState
    overall: DecisionOverall = DecisionOverall.BLOCKED
    outcome: DecisionOutcome = DecisionOutcome.NO_DECISION

    def __post_init__(self) -> None:
        if (
            type(self.recording_id) is not str
            or _TOKEN.fullmatch(self.recording_id) is None
            or type(self.input_digest) is not Sha256Digest
            or type(self.source_pack_digest) is not Sha256Digest
            or self.quality_state is not EvidenceState.NOT_EXECUTED
            or self.economics_state
            is not EvidenceState.RECORDED_SYNTHETIC_NON_ATTESTING
            or self.risk_state is not EvidenceState.NOT_EXECUTED
            or self.formal_tst032_state is not EvidenceState.NOT_EXECUTED
            or self.overall is not DecisionOverall.BLOCKED
            or self.outcome is not DecisionOutcome.NO_DECISION
        ):
            fail_portfolio_decision()

    @staticmethod
    def _evidence_row(state: EvidenceState, reason: str) -> dict[str, str]:
        return {
            "availability": EvidenceAvailability.UNAVAILABLE.value,
            "reason": reason,
            "source_state": state.value,
        }

    def payload(self) -> dict[str, object]:
        criteria = [
            {
                "criterion_id": "ST1805-QUALITY",
                "evidence_class": "QUALITY",
                "status": CriterionStatus.NOT_ELIGIBLE.value,
                "reason": "ACTUAL_30_45_ARTICLE_QUALITY_EVIDENCE_NOT_EXECUTED",
            },
            {
                "criterion_id": "ST1805-ECONOMICS",
                "evidence_class": "ECONOMICS",
                "status": CriterionStatus.NOT_ELIGIBLE.value,
                "reason": "RECORDED_SYNTHETIC_GATE3_IS_NON_ATTESTING",
            },
            {
                "criterion_id": "ST1805-RISK",
                "evidence_class": "RISK",
                "status": CriterionStatus.NOT_ELIGIBLE.value,
                "reason": "FORMAL_SECURITY_COMPLIANCE_RISK_EVIDENCE_NOT_EXECUTED",
            },
            {
                "criterion_id": "ST1805-TST032",
                "evidence_class": "FORMAL_GATE_PACK",
                "status": CriterionStatus.NOT_ELIGIBLE.value,
                "reason": "FORMAL_TST_032_NOT_EXECUTED",
            },
            {
                "criterion_id": "ST1805-HUMAN-DECISION",
                "evidence_class": "HUMAN_AUTHORITY",
                "status": CriterionStatus.NOT_ELIGIBLE.value,
                "reason": "PRODUCT_OWNER_DECISION_NOT_PRESENT",
            },
        ]
        return {
            "authority": {
                "category_change": "NONE",
                "decision": "NONE",
                "editorial_mutation": "NONE",
                "gate_approval": "NONE",
                "publication": "NONE",
                "scale_hold_pivot": "NONE",
                "status_apply": "NONE",
            },
            "criteria": criteria,
            "decision": {
                "authorized": False,
                "category_limit_change": None,
                "human_decision_required": True,
                "mutations_applied": [],
                "outcome": self.outcome.value,
                "scale_limit_change": None,
            },
            "evidence": {
                "economics": self._evidence_row(
                    self.economics_state,
                    "RECORDED_SYNTHETIC_NON_ATTESTING_NOT_ACTUAL_ECONOMICS",
                ),
                "formal_tst032": self._evidence_row(
                    self.formal_tst032_state,
                    "FORMAL_TST_032_NOT_EXECUTED",
                ),
                "quality": self._evidence_row(
                    self.quality_state,
                    "ACTUAL_30_45_ARTICLE_QUALITY_EVIDENCE_NOT_EXECUTED",
                ),
                "risk": self._evidence_row(
                    self.risk_state,
                    "FORMAL_SECURITY_COMPLIANCE_RISK_EVIDENCE_NOT_EXECUTED",
                ),
            },
            "finance_editorial_boundary": {
                "affiliate_rate_used_for_product_ranking": False,
                "epc_used_for_product_ranking": False,
                "finance_used_for_product_or_recommendation_ranking": False,
                "profit_used_for_product_ranking": False,
                "recommendation_order_changed": False,
                "reward_used_for_product_ranking": False,
            },
            "input_sha256": self.input_digest.value,
            "method_version": METHOD_VERSION,
            "overall": self.overall.value,
            "program": PROGRAM,
            "recording_id": self.recording_id,
            "schema": REPORT_SCHEMA,
            "source_pack_sha256": self.source_pack_digest.value,
        }


def build_portfolio_decision_report(
    evidence: PortfolioDecisionEvidence,
) -> PortfolioDecisionReport:
    if type(evidence) is not PortfolioDecisionEvidence:
        fail_portfolio_decision()
    if canonical_input_digest(evidence) != evidence.input_digest:
        fail_portfolio_decision(PortfolioDecisionFailureCode.RECORDED_RESULT_MISMATCH)
    return PortfolioDecisionReport(
        recording_id=evidence.recording_id,
        input_digest=evidence.input_digest,
        source_pack_digest=evidence.source_pack_digest,
        quality_state=evidence.quality_state,
        economics_state=evidence.economics_state,
        risk_state=evidence.risk_state,
        formal_tst032_state=evidence.formal_tst032_state,
    )


__all__ = [
    "DecisionOutcome",
    "DecisionOverall",
    "EvidenceAvailability",
    "EvidenceState",
    "FIXTURE_SCHEMA",
    "FixtureByteLength",
    "METHOD_VERSION",
    "PROGRAM",
    "PortfolioDecisionCommand",
    "PortfolioDecisionEvidence",
    "PortfolioDecisionFailure",
    "PortfolioDecisionFailureCode",
    "PortfolioDecisionReport",
    "REPORT_SCHEMA",
    "Sha256Digest",
    "build_portfolio_decision_report",
    "canonical_input_digest",
    "fail_portfolio_decision",
]
