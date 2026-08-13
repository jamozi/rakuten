"""Immutable local market-learning pilot values for ST-1703.

The values in this module can represent only a WordPress draft operation.  They
do not authorize publication, provider access, spend, release, or production
use.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


PILOT_SERIALIZATION_PROFILE = "ST1703_MARKET_LEARNING_PILOT_WAVE_1_V1"
POLICY_SERIALIZATION_PROFILE = "ST0805_LOCAL_RESULT_V1"
WORDPRESS_DRAFT_STATUS = "draft"

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,126}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_TITLE_CHARS = 512
_MAX_CONTENT_BYTES = 1_000_000


class DraftOperation(str, Enum):
    CREATE_DRAFT = "CREATE_DRAFT"
    UPDATE_DRAFT = "UPDATE_DRAFT"


class DraftDisposition(str, Enum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    REPLAYED = "REPLAYED"


class PilotEvidenceAuthority(str, Enum):
    LOCAL_RECORDED_ONLY = "LOCAL_RECORDED_ONLY"


class PilotExecutionStatus(str, Enum):
    EXECUTED_LOCAL_RECORDED = "EXECUTED_LOCAL_RECORDED"
    NOT_EXECUTED = "NOT_EXECUTED"


class PilotAuthorizationStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"


class PilotObservationStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"


class MarketLearningPilotFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    ENVIRONMENT_DISABLED = "ENVIRONMENT_DISABLED"
    POLICY_INELIGIBLE = "POLICY_INELIGIBLE"
    POLICY_RESULT_INVALID = "POLICY_RESULT_INVALID"
    RAKUTEN_RESULT_INVALID = "RAKUTEN_RESULT_INVALID"
    DRAFT_UPDATE_REQUIRED = "DRAFT_UPDATE_REQUIRED"
    DRAFT_TARGET_MISMATCH = "DRAFT_TARGET_MISMATCH"
    DRAFT_EXCHANGE_UNAVAILABLE = "DRAFT_EXCHANGE_UNAVAILABLE"
    WORDPRESS_ORIGIN_INVALID = "WORDPRESS_ORIGIN_INVALID"
    WORDPRESS_REQUEST_INVALID = "WORDPRESS_REQUEST_INVALID"
    WORDPRESS_RESPONSE_INVALID = "WORDPRESS_RESPONSE_INVALID"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"


@dataclass(frozen=True, slots=True, repr=False)
class MarketLearningPilotFailure(RuntimeError):
    """Closed, sanitized failure with no caller or provider material."""

    code: MarketLearningPilotFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not MarketLearningPilotFailureCode:
            raise TypeError("invalid market-learning pilot failure code")
        RuntimeError.__init__(self, self.code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"MarketLearningPilotFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("market-learning pilot failure serialization is disabled")


def fail_market_learning_pilot(
    code: MarketLearningPilotFailureCode = (
        MarketLearningPilotFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise MarketLearningPilotFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-market-learning-pilot>)"

    def __str__(self) -> str:
        return "<redacted-market-learning-pilot>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("market-learning pilot value serialization is disabled")


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_market_learning_pilot()
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except TypeError, ValueError, UnicodeError:
        fail_market_learning_pilot()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _article_version_id(value: object) -> str:
    if type(value) is not str or _REFERENCE.fullmatch(value) is None:
        fail_market_learning_pilot()
    return value


def _title(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= _MAX_TITLE_CHARS
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_market_learning_pilot()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_market_learning_pilot()
    return value


def _content(value: object) -> str:
    if type(value) is not str or not value.strip():
        fail_market_learning_pilot()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        fail_market_learning_pilot()
    if not 1 <= len(encoded) <= _MAX_CONTENT_BYTES or any(
        ord(character) < 32 and character not in "\t\n\r" for character in value
    ):
        fail_market_learning_pilot()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class PilotEconomics(_RedactedValue):
    duration_days: int = 90
    currency: str = "JPY"
    monthly_external_spend_cap: int = 30_000
    cumulative_loss_cap: int = 90_000
    labor_cost_per_hour: int = 3_000
    spending_activation: str = "DISABLED"

    def __post_init__(self) -> None:
        if (
            type(self.duration_days) is not int
            or self.duration_days != 90
            or type(self.currency) is not str
            or self.currency != "JPY"
            or type(self.monthly_external_spend_cap) is not int
            or self.monthly_external_spend_cap != 30_000
            or type(self.cumulative_loss_cap) is not int
            or self.cumulative_loss_cap != 90_000
            or type(self.labor_cost_per_hour) is not int
            or self.labor_cost_per_hour != 3_000
            or type(self.spending_activation) is not str
            or self.spending_activation != "DISABLED"
        ):
            fail_market_learning_pilot()

    def canonical_payload(self) -> dict[str, int | str]:
        return {
            "cumulative_loss_cap": self.cumulative_loss_cap,
            "currency": self.currency,
            "duration_days": self.duration_days,
            "labor_cost_per_hour": self.labor_cost_per_hour,
            "monthly_external_spend_cap": self.monthly_external_spend_cap,
            "spending_activation": self.spending_activation,
        }

    @property
    def digest(self) -> str:
        return _digest(self.canonical_payload())


@dataclass(frozen=True, slots=True, repr=False)
class WordPressDraftIntent(_RedactedValue):
    operation: DraftOperation
    article_version_id: str
    title: str
    content: str
    existing_draft_id: int | None = None

    def __post_init__(self) -> None:
        if type(self.operation) is not DraftOperation:
            fail_market_learning_pilot()
        _article_version_id(self.article_version_id)
        _title(self.title)
        _content(self.content)
        if self.operation is DraftOperation.CREATE_DRAFT:
            valid_target = self.existing_draft_id is None
        else:
            valid_target = (
                type(self.existing_draft_id) is int
                and 1 <= self.existing_draft_id <= (1 << 63) - 1
            )
        if not valid_target:
            fail_market_learning_pilot()


@dataclass(frozen=True, slots=True, repr=False)
class BoundWordPressDraft(_RedactedValue):
    intent: WordPressDraftIntent
    pilot: PilotEconomics
    policy_local_result_digest: str
    rakuten_request_fingerprint: str
    rakuten_raw_response_sha256: str
    content_binding_sha256: str
    operation_binding_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.intent) is not WordPressDraftIntent
            or type(self.pilot) is not PilotEconomics
        ):
            fail_market_learning_pilot()
        _sha256(self.policy_local_result_digest)
        _sha256(self.rakuten_request_fingerprint)
        _sha256(self.rakuten_raw_response_sha256)
        _sha256(self.content_binding_sha256)
        _sha256(self.operation_binding_sha256)
        if (
            self.content_binding_sha256 != self._expected_content_binding()
            or self.operation_binding_sha256 != self._expected_operation_binding()
        ):
            fail_market_learning_pilot()

    @classmethod
    def bind(
        cls,
        *,
        intent: WordPressDraftIntent,
        pilot: PilotEconomics,
        policy_local_result_digest: str,
        rakuten_request_fingerprint: str,
        rakuten_raw_response_sha256: str,
    ) -> BoundWordPressDraft:
        if (
            type(intent) is not WordPressDraftIntent
            or type(pilot) is not PilotEconomics
        ):
            fail_market_learning_pilot()
        for value in (
            policy_local_result_digest,
            rakuten_request_fingerprint,
            rakuten_raw_response_sha256,
        ):
            _sha256(value)
        content_payload = cls._content_payload(
            intent=intent,
            pilot=pilot,
            policy_local_result_digest=policy_local_result_digest,
            rakuten_request_fingerprint=rakuten_request_fingerprint,
            rakuten_raw_response_sha256=rakuten_raw_response_sha256,
        )
        content_binding = _digest(content_payload)
        operation_binding = _digest(
            {
                "content_binding_sha256": content_binding,
                "existing_draft_id": intent.existing_draft_id,
                "operation": intent.operation.value,
            }
        )
        return cls(
            intent=intent,
            pilot=pilot,
            policy_local_result_digest=policy_local_result_digest,
            rakuten_request_fingerprint=rakuten_request_fingerprint,
            rakuten_raw_response_sha256=rakuten_raw_response_sha256,
            content_binding_sha256=content_binding,
            operation_binding_sha256=operation_binding,
        )

    @staticmethod
    def _content_payload(
        *,
        intent: WordPressDraftIntent,
        pilot: PilotEconomics,
        policy_local_result_digest: str,
        rakuten_request_fingerprint: str,
        rakuten_raw_response_sha256: str,
    ) -> dict[str, object]:
        return {
            "article_version_id": intent.article_version_id,
            "content": intent.content,
            "pilot_config": pilot.canonical_payload(),
            "policy_local_result_digest": policy_local_result_digest,
            "rakuten_raw_response_sha256": rakuten_raw_response_sha256,
            "rakuten_request_fingerprint": rakuten_request_fingerprint,
            "title": intent.title,
        }

    def _expected_content_binding(self) -> str:
        return _digest(
            self._content_payload(
                intent=self.intent,
                pilot=self.pilot,
                policy_local_result_digest=self.policy_local_result_digest,
                rakuten_request_fingerprint=self.rakuten_request_fingerprint,
                rakuten_raw_response_sha256=self.rakuten_raw_response_sha256,
            )
        )

    def _expected_operation_binding(self) -> str:
        return _digest(
            {
                "content_binding_sha256": self.content_binding_sha256,
                "existing_draft_id": self.intent.existing_draft_id,
                "operation": self.intent.operation.value,
            }
        )


@dataclass(frozen=True, slots=True, repr=False)
class WordPressDraftReceipt(_RedactedValue):
    draft_id: int
    operation: DraftOperation
    disposition: DraftDisposition
    status: str
    content_binding_sha256: str
    operation_binding_sha256: str
    logical_draft_sha256: str
    network_status: PilotExecutionStatus
    publication_authorized: bool
    production_eligible: bool

    def __post_init__(self) -> None:
        if (
            type(self.draft_id) is not int
            or not 1 <= self.draft_id <= (1 << 63) - 1
            or type(self.operation) is not DraftOperation
            or type(self.disposition) is not DraftDisposition
            or type(self.status) is not str
            or self.status != WORDPRESS_DRAFT_STATUS
            or self.network_status is not PilotExecutionStatus.NOT_EXECUTED
            or self.publication_authorized is not False
            or self.production_eligible is not False
        ):
            fail_market_learning_pilot()
        for value in (
            self.content_binding_sha256,
            self.operation_binding_sha256,
            self.logical_draft_sha256,
        ):
            _sha256(value)


@dataclass(frozen=True, slots=True, repr=False)
class PilotEvidenceRecord(_RedactedValue):
    evidence_sha256: str
    pilot_config_sha256: str
    policy_local_result_digest: str
    rakuten_request_fingerprint: str
    rakuten_raw_response_sha256: str
    draft_content_binding_sha256: str
    draft_operation_binding_sha256: str
    logical_draft_sha256: str
    authority: PilotEvidenceAuthority
    local_execution: PilotExecutionStatus
    formal_test: PilotExecutionStatus
    live_validation: PilotExecutionStatus
    staging: PilotExecutionStatus
    release: PilotExecutionStatus
    publication: PilotAuthorizationStatus
    revenue: PilotObservationStatus
    production: PilotExecutionStatus

    def __post_init__(self) -> None:
        for value in (
            self.evidence_sha256,
            self.pilot_config_sha256,
            self.policy_local_result_digest,
            self.rakuten_request_fingerprint,
            self.rakuten_raw_response_sha256,
            self.draft_content_binding_sha256,
            self.draft_operation_binding_sha256,
            self.logical_draft_sha256,
        ):
            _sha256(value)
        if (
            self.authority is not PilotEvidenceAuthority.LOCAL_RECORDED_ONLY
            or self.local_execution is not PilotExecutionStatus.EXECUTED_LOCAL_RECORDED
            or any(
                status is not PilotExecutionStatus.NOT_EXECUTED
                for status in (
                    self.formal_test,
                    self.live_validation,
                    self.staging,
                    self.release,
                    self.production,
                )
            )
            or self.publication is not PilotAuthorizationStatus.NOT_AUTHORIZED
            or self.revenue is not PilotObservationStatus.NOT_OBSERVED
            or self.evidence_sha256 != self._expected_digest()
        ):
            fail_market_learning_pilot()

    @classmethod
    def from_draft(
        cls,
        *,
        candidate: BoundWordPressDraft,
        receipt: WordPressDraftReceipt,
    ) -> PilotEvidenceRecord:
        if (
            type(candidate) is not BoundWordPressDraft
            or type(receipt) is not WordPressDraftReceipt
        ):
            fail_market_learning_pilot()
        payload = cls._payload(candidate=candidate, receipt=receipt)
        return cls(
            evidence_sha256=_digest(payload),
            pilot_config_sha256=candidate.pilot.digest,
            policy_local_result_digest=candidate.policy_local_result_digest,
            rakuten_request_fingerprint=candidate.rakuten_request_fingerprint,
            rakuten_raw_response_sha256=candidate.rakuten_raw_response_sha256,
            draft_content_binding_sha256=candidate.content_binding_sha256,
            draft_operation_binding_sha256=candidate.operation_binding_sha256,
            logical_draft_sha256=receipt.logical_draft_sha256,
            authority=PilotEvidenceAuthority.LOCAL_RECORDED_ONLY,
            local_execution=PilotExecutionStatus.EXECUTED_LOCAL_RECORDED,
            formal_test=PilotExecutionStatus.NOT_EXECUTED,
            live_validation=PilotExecutionStatus.NOT_EXECUTED,
            staging=PilotExecutionStatus.NOT_EXECUTED,
            release=PilotExecutionStatus.NOT_EXECUTED,
            publication=PilotAuthorizationStatus.NOT_AUTHORIZED,
            revenue=PilotObservationStatus.NOT_OBSERVED,
            production=PilotExecutionStatus.NOT_EXECUTED,
        )

    @staticmethod
    def _payload(
        *, candidate: BoundWordPressDraft, receipt: WordPressDraftReceipt
    ) -> dict[str, object]:
        return {
            "authority": PilotEvidenceAuthority.LOCAL_RECORDED_ONLY.value,
            "draft_content_binding_sha256": candidate.content_binding_sha256,
            "draft_operation_binding_sha256": candidate.operation_binding_sha256,
            "formal_test": PilotExecutionStatus.NOT_EXECUTED.value,
            "live_validation": PilotExecutionStatus.NOT_EXECUTED.value,
            "local_execution": (PilotExecutionStatus.EXECUTED_LOCAL_RECORDED.value),
            "logical_draft_sha256": receipt.logical_draft_sha256,
            "pilot_config_sha256": candidate.pilot.digest,
            "policy_local_result_digest": candidate.policy_local_result_digest,
            "production": PilotExecutionStatus.NOT_EXECUTED.value,
            "profile": PILOT_SERIALIZATION_PROFILE,
            "publication": PilotAuthorizationStatus.NOT_AUTHORIZED.value,
            "rakuten_raw_response_sha256": candidate.rakuten_raw_response_sha256,
            "rakuten_request_fingerprint": candidate.rakuten_request_fingerprint,
            "release": PilotExecutionStatus.NOT_EXECUTED.value,
            "revenue": PilotObservationStatus.NOT_OBSERVED.value,
            "staging": PilotExecutionStatus.NOT_EXECUTED.value,
        }

    def _expected_digest(self) -> str:
        return _digest(
            {
                "authority": self.authority.value,
                "draft_content_binding_sha256": self.draft_content_binding_sha256,
                "draft_operation_binding_sha256": (self.draft_operation_binding_sha256),
                "formal_test": self.formal_test.value,
                "live_validation": self.live_validation.value,
                "local_execution": self.local_execution.value,
                "logical_draft_sha256": self.logical_draft_sha256,
                "pilot_config_sha256": self.pilot_config_sha256,
                "policy_local_result_digest": self.policy_local_result_digest,
                "production": self.production.value,
                "profile": PILOT_SERIALIZATION_PROFILE,
                "publication": self.publication.value,
                "rakuten_raw_response_sha256": self.rakuten_raw_response_sha256,
                "rakuten_request_fingerprint": self.rakuten_request_fingerprint,
                "release": self.release.value,
                "revenue": self.revenue.value,
                "staging": self.staging.value,
            }
        )


@dataclass(frozen=True, slots=True, repr=False)
class MarketLearningPilotResult(_RedactedValue):
    candidate: BoundWordPressDraft
    receipt: WordPressDraftReceipt
    evidence: PilotEvidenceRecord

    def __post_init__(self) -> None:
        if (
            type(self.candidate) is not BoundWordPressDraft
            or type(self.receipt) is not WordPressDraftReceipt
            or type(self.evidence) is not PilotEvidenceRecord
            or self.receipt.operation is not self.candidate.intent.operation
            or self.receipt.content_binding_sha256
            != self.candidate.content_binding_sha256
            or self.receipt.operation_binding_sha256
            != self.candidate.operation_binding_sha256
            or self.evidence.draft_content_binding_sha256
            != self.candidate.content_binding_sha256
            or self.evidence.draft_operation_binding_sha256
            != self.candidate.operation_binding_sha256
            or self.evidence.logical_draft_sha256 != self.receipt.logical_draft_sha256
        ):
            fail_market_learning_pilot()


__all__ = [
    "BoundWordPressDraft",
    "DraftDisposition",
    "DraftOperation",
    "MarketLearningPilotFailure",
    "MarketLearningPilotFailureCode",
    "MarketLearningPilotResult",
    "PILOT_SERIALIZATION_PROFILE",
    "POLICY_SERIALIZATION_PROFILE",
    "PilotAuthorizationStatus",
    "PilotEconomics",
    "PilotEvidenceAuthority",
    "PilotEvidenceRecord",
    "PilotExecutionStatus",
    "PilotObservationStatus",
    "WORDPRESS_DRAFT_STATUS",
    "WordPressDraftIntent",
    "WordPressDraftReceipt",
    "fail_market_learning_pilot",
]
