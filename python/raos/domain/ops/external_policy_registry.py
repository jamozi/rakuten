"""Recorded-only external-policy registry boundary for ST-1407.

The module intentionally has no acquisition, persistence, notification, audit,
activation, publication, or clock dependency.  It evaluates exact caller-supplied
DEV/CI fixture coordinates and therefore cannot attest to a current official page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.editorial.policy_engine import (
    POLICY_CATALOG_ID,
    POLICY_CATALOG_SHA256,
    POLICY_CATALOG_VERSION,
    POLICY_DEFINITIONS,
)
from raos.domain.shared.persistence import Sha256Digest


CONTRACT_ID = "RAOS-ST1407-EXTERNAL-POLICY-REGISTRY-RUNTIME-002"
CONTRACT_VERSION = "2.0.0"
LOCAL_STATUS = "LOCAL_IMPLEMENTATION_COMPLETE_FOR_UNRESOLVED_BOUNDARY"
EXTERNAL_RULE_CATALOG_ID = "RAOS-CONTENT-EXTERNAL-001"
EXTERNAL_RULE_CATALOG_VERSION = "0.1"
EXTERNAL_RULE_CATALOG_SHA256 = (
    "14a4131215f8c2f70a2f5b73aef0ccb1162f1a8ac6d410079c6a3b6b68955042"
)
OFFICIAL_REFERENCE_CATALOG_ID = "RAOS-CONTENT-REF-001"
OFFICIAL_REFERENCE_CATALOG_VERSION = "0.1"
OFFICIAL_REFERENCE_CATALOG_SHA256 = (
    "d7a3986affce9d2fc1110d6b3fffb196c668dae7db00288d466b9e62ba57e030"
)
OPEN_SOURCE_ALLOWLIST_DECISION = "OPEN-018"
LEGAL_REVIEW_DECISION = "OD-008"
NOTIFICATION_CHANNEL_DECISION = "OD-011"
ALERT_CATALOG_ID = "ALT-019"
RUNBOOK_ID = "RB-018"
MAX_RECORDED_ARTICLES = 5_000
RECORDED_ARTICLE_BINDING_SET_SHA256S: tuple[str, ...] = (
    "28bb5cc92bc27cbe388e7146a59721c2d7409940a5f6ecb896ac971a8038648e",
    "d8f1713a8c19adbf343dbd80cadedd66d11899582327015627a97e670f7512ec",
)

EXTERNAL_RULE_POLICY_LINKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "EXT-GOOGLE-001",
        ("POL-CONT-019", "POL-CONT-020", "POL-CONT-021"),
    ),
    ("EXT-GOOGLE-002", ("POL-CONT-020", "POL-CONT-030")),
    ("EXT-GOOGLE-003", ("POL-CONT-010",)),
    (
        "EXT-GOOGLE-004",
        ("POL-CONT-001", "POL-CONT-002", "POL-CONT-020"),
    ),
    ("EXT-GOOGLE-005", ("POL-CONT-020", "POL-CONT-030")),
    ("EXT-GOOGLE-006", ("POL-CONT-027", "POL-CONT-029")),
    ("EXT-GOOGLE-007", ("POL-CONT-028",)),
    ("EXT-GOOGLE-008", ("POL-CONT-032", "POL-CONT-033")),
    ("EXT-W3C-001", ("POL-CONT-032",)),
    (
        "EXT-RAKUTEN-001",
        ("POL-CONT-004", "POL-CONT-007", "POL-CONT-011", "POL-CONT-013"),
    ),
    ("EXT-RAKUTEN-002", ("POL-CONT-008",)),
    ("EXT-RAKUTEN-003", ("POL-CONT-012",)),
    ("EXT-CAA-001", ("POL-CONT-008",)),
)

_EXTERNAL_RULE_POLICY_MAP: dict[str, tuple[str, ...]] = dict(EXTERNAL_RULE_POLICY_LINKS)
_POLICY_IDS = frozenset(definition.policy_id for definition in POLICY_DEFINITIONS)
_MAX_POLICY_LINKS = max(len(item) for item in _EXTERNAL_RULE_POLICY_MAP.values())
_REDACTED = "<redacted-st1407-external-policy-registry>"


class RegistryFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTRACT_BINDING_MISMATCH = "CONTRACT_BINDING_MISMATCH"
    SNAPSHOT_BINDING_MISMATCH = "SNAPSHOT_BINDING_MISMATCH"
    VERSION_LINK_SET_MISMATCH = "VERSION_LINK_SET_MISMATCH"
    ARTICLE_BINDING_SET_INVALID = "ARTICLE_BINDING_SET_INVALID"
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    EVALUATION_MISMATCH = "EVALUATION_MISMATCH"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"


@final
class RegistryFailure(ValueError):
    """Closed failure without caller-controlled material."""

    __slots__ = ("code",)

    def __init__(self, code: RegistryFailureCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __repr__(self) -> str:
        return f"RegistryFailure(code={self.code.value!r})"


def fail_registry(code: RegistryFailureCode) -> NoReturn:
    raise RegistryFailure(code) from None


class RegistryMode(str, Enum):
    RECORDED_DEV_CI_ONLY = "RECORDED_DEV_CI_ONLY"


class SnapshotValidation(str, Enum):
    RECORDED_SYNTHETIC_VALID = "RECORDED_SYNTHETIC_VALID"


class ArticleBindingScope(str, Enum):
    EXACT_COMPLETE_RECORDED_FIXTURE = "EXACT_COMPLETE_RECORDED_FIXTURE"


class ImpactQueryStatus(str, Enum):
    LOCAL_EVALUATED = "LOCAL_EVALUATED"


class EmptyAffectedMeaning(str, Enum):
    NOT_EMPTY = "NOT_EMPTY"
    ZERO_WITHIN_EXACT_COMPLETE_RECORDED_FIXTURE = (
        "ZERO_WITHIN_EXACT_COMPLETE_RECORDED_FIXTURE"
    )


class ReviewDueState(str, Enum):
    NOT_DUE = "NOT_DUE"
    DUE = "DUE"
    OVERDUE = "OVERDUE"


class NotificationRoute(str, Enum):
    LOCAL_LOG_ONLY = "LOCAL_LOG_ONLY"


class AssignmentState(str, Enum):
    NOT_ASSIGNED = "NOT_ASSIGNED"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("external policy registry value serialization is disabled")


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    return value


def _instant_text(value: datetime) -> str:
    _utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _uuid_text(value: UUID) -> str:
    if type(value) is not UUID or value.int == 0 or str(value) != str(UUID(str(value))):
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    return str(value)


def _digest_value(value: object) -> str:
    if type(value) is not Sha256Digest:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    try:
        reconstructed = Sha256Digest(value.value)
    except Exception:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    return reconstructed.value


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


@final
@dataclass(frozen=True, slots=True, repr=False)
class RegistryContractBinding(_Redacted):
    contract_id: str
    contract_version: str
    external_rule_catalog_id: str
    external_rule_catalog_version: str
    external_rule_catalog_sha256: Sha256Digest
    official_reference_catalog_id: str
    official_reference_catalog_version: str
    official_reference_catalog_sha256: Sha256Digest
    policy_catalog_id: str
    policy_catalog_version: str
    policy_catalog_sha256: Sha256Digest
    source_allowlist_decision: str
    legal_review_decision: str
    notification_channel_decision: str

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not str
                for value in (
                    self.contract_id,
                    self.contract_version,
                    self.external_rule_catalog_id,
                    self.external_rule_catalog_version,
                    self.official_reference_catalog_id,
                    self.official_reference_catalog_version,
                    self.policy_catalog_id,
                    self.policy_catalog_version,
                    self.source_allowlist_decision,
                    self.legal_review_decision,
                    self.notification_channel_decision,
                )
            )
            or self.contract_id != CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or self.external_rule_catalog_id != EXTERNAL_RULE_CATALOG_ID
            or self.external_rule_catalog_version != EXTERNAL_RULE_CATALOG_VERSION
            or _digest_value(self.external_rule_catalog_sha256)
            != EXTERNAL_RULE_CATALOG_SHA256
            or self.official_reference_catalog_id != OFFICIAL_REFERENCE_CATALOG_ID
            or self.official_reference_catalog_version
            != OFFICIAL_REFERENCE_CATALOG_VERSION
            or _digest_value(self.official_reference_catalog_sha256)
            != OFFICIAL_REFERENCE_CATALOG_SHA256
            or self.policy_catalog_id != POLICY_CATALOG_ID
            or self.policy_catalog_version != POLICY_CATALOG_VERSION
            or _digest_value(self.policy_catalog_sha256) != POLICY_CATALOG_SHA256
            or self.source_allowlist_decision != OPEN_SOURCE_ALLOWLIST_DECISION
            or self.legal_review_decision != LEGAL_REVIEW_DECISION
            or self.notification_channel_decision != NOTIFICATION_CHANNEL_DECISION
        ):
            fail_registry(RegistryFailureCode.CONTRACT_BINDING_MISMATCH)

    @classmethod
    def current(cls) -> RegistryContractBinding:
        return cls(
            contract_id=CONTRACT_ID,
            contract_version=CONTRACT_VERSION,
            external_rule_catalog_id=EXTERNAL_RULE_CATALOG_ID,
            external_rule_catalog_version=EXTERNAL_RULE_CATALOG_VERSION,
            external_rule_catalog_sha256=Sha256Digest(EXTERNAL_RULE_CATALOG_SHA256),
            official_reference_catalog_id=OFFICIAL_REFERENCE_CATALOG_ID,
            official_reference_catalog_version=OFFICIAL_REFERENCE_CATALOG_VERSION,
            official_reference_catalog_sha256=Sha256Digest(
                OFFICIAL_REFERENCE_CATALOG_SHA256
            ),
            policy_catalog_id=POLICY_CATALOG_ID,
            policy_catalog_version=POLICY_CATALOG_VERSION,
            policy_catalog_sha256=Sha256Digest(POLICY_CATALOG_SHA256),
            source_allowlist_decision=OPEN_SOURCE_ALLOWLIST_DECISION,
            legal_review_decision=LEGAL_REVIEW_DECISION,
            notification_channel_decision=NOTIFICATION_CHANNEL_DECISION,
        )

    @property
    def fingerprint(self) -> str:
        return _sha(_binding_payload(self))


@final
@dataclass(frozen=True, slots=True, repr=False)
class ExternalPolicySnapshot(_Redacted):
    snapshot_id: UUID
    external_rule_id: str
    source_content_sha256: Sha256Digest
    acquired_at: datetime
    review_due_at: datetime
    contract_binding_sha256: Sha256Digest
    mode: RegistryMode = RegistryMode.RECORDED_DEV_CI_ONLY
    validation: SnapshotValidation = SnapshotValidation.RECORDED_SYNTHETIC_VALID
    official_source_attested: bool = False
    current_source_verified: bool = False

    def __post_init__(self) -> None:
        _uuid_text(self.snapshot_id)
        if (
            type(self.external_rule_id) is not str
            or self.external_rule_id not in _EXTERNAL_RULE_POLICY_MAP
            or type(self.mode) is not RegistryMode
            or self.mode is not RegistryMode.RECORDED_DEV_CI_ONLY
            or type(self.validation) is not SnapshotValidation
            or self.validation is not SnapshotValidation.RECORDED_SYNTHETIC_VALID
            or self.official_source_attested is not False
            or self.current_source_verified is not False
        ):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        _digest_value(self.source_content_sha256)
        _digest_value(self.contract_binding_sha256)
        acquired = _utc(self.acquired_at)
        due = _utc(self.review_due_at)
        if due <= acquired:
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)

    @property
    def fingerprint(self) -> str:
        return _sha(_snapshot_payload(self))


@final
@dataclass(frozen=True, slots=True, repr=False)
class PolicyVersionLink(_Redacted):
    snapshot_id: UUID
    external_rule_id: str
    policy_id: str
    policy_version: str
    policy_catalog_sha256: Sha256Digest
    reference_only: bool = True
    activation_authorized: bool = False

    def __post_init__(self) -> None:
        _uuid_text(self.snapshot_id)
        if (
            type(self.external_rule_id) is not str
            or self.external_rule_id not in _EXTERNAL_RULE_POLICY_MAP
            or type(self.policy_id) is not str
            or self.policy_id not in _POLICY_IDS
            or type(self.policy_version) is not str
            or self.policy_version != POLICY_CATALOG_VERSION
            or _digest_value(self.policy_catalog_sha256) != POLICY_CATALOG_SHA256
            or self.reference_only is not True
            or self.activation_authorized is not False
        ):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)

    @property
    def fingerprint(self) -> str:
        return _sha(_version_link_payload(self))


@final
@dataclass(frozen=True, slots=True, repr=False)
class ArticlePolicyBinding(_Redacted):
    article_id: UUID
    article_version_id: UUID
    publication_snapshot_sha256: Sha256Digest
    policy_ids: tuple[str, ...]
    scope: ArticleBindingScope = ArticleBindingScope.EXACT_COMPLETE_RECORDED_FIXTURE
    content_mutation_authorized: bool = False
    recommendation_mutation_authorized: bool = False
    publication_authorized: bool = False

    def __post_init__(self) -> None:
        _uuid_text(self.article_id)
        _uuid_text(self.article_version_id)
        _digest_value(self.publication_snapshot_sha256)
        if (
            type(self.policy_ids) is not tuple
            or not 1 <= len(self.policy_ids) <= len(_POLICY_IDS)
            or any(
                type(item) is not str or item not in _POLICY_IDS
                for item in self.policy_ids
            )
            or tuple(sorted(self.policy_ids)) != self.policy_ids
            or len(set(self.policy_ids)) != len(self.policy_ids)
            or type(self.scope) is not ArticleBindingScope
            or self.scope is not ArticleBindingScope.EXACT_COMPLETE_RECORDED_FIXTURE
            or self.content_mutation_authorized is not False
            or self.recommendation_mutation_authorized is not False
            or self.publication_authorized is not False
        ):
            fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)

    @property
    def fingerprint(self) -> str:
        return _sha(_article_binding_payload(self))


@final
@dataclass(frozen=True, slots=True, repr=False)
class ExternalPolicyRegistryRequest(_Redacted):
    binding: RegistryContractBinding
    snapshot: ExternalPolicySnapshot
    version_links: tuple[PolicyVersionLink, ...]
    article_bindings: tuple[ArticlePolicyBinding, ...]
    article_binding_set_sha256: Sha256Digest
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.binding) is not RegistryContractBinding
            or type(self.snapshot) is not ExternalPolicySnapshot
            or type(self.version_links) is not tuple
            or not 1 <= len(self.version_links) <= _MAX_POLICY_LINKS
            or any(type(item) is not PolicyVersionLink for item in self.version_links)
            or type(self.article_bindings) is not tuple
            or len(self.article_bindings) > MAX_RECORDED_ARTICLES
            or any(
                type(item) is not ArticlePolicyBinding for item in self.article_bindings
            )
        ):
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
        observed_article_binding_set = article_binding_set_fingerprint(
            self.article_bindings
        )
        if (
            _digest_value(self.article_binding_set_sha256)
            != observed_article_binding_set
            or observed_article_binding_set not in RECORDED_ARTICLE_BINDING_SET_SHA256S
        ):
            fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)
        evaluated = _utc(self.evaluated_at)
        if evaluated < self.snapshot.acquired_at:
            fail_registry(RegistryFailureCode.INVALID_ARGUMENT)

    @property
    def fingerprint(self) -> str:
        return _sha(_registry_request_payload_trusted(self))


@final
@dataclass(frozen=True, slots=True, repr=False)
class AffectedArticle(_Redacted):
    article_id: UUID
    article_version_id: UUID
    publication_snapshot_sha256: Sha256Digest
    matched_policy_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _uuid_text(self.article_id)
        _uuid_text(self.article_version_id)
        _digest_value(self.publication_snapshot_sha256)
        if (
            type(self.matched_policy_ids) is not tuple
            or not self.matched_policy_ids
            or tuple(sorted(self.matched_policy_ids)) != self.matched_policy_ids
            or len(set(self.matched_policy_ids)) != len(self.matched_policy_ids)
            or any(item not in _POLICY_IDS for item in self.matched_policy_ids)
        ):
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ImpactQueryResult(_Redacted):
    status: ImpactQueryStatus
    request_sha256: Sha256Digest
    snapshot_id: UUID
    external_rule_id: str
    changed_policy_ids: tuple[str, ...]
    article_binding_set_sha256: Sha256Digest
    affected_articles: tuple[AffectedArticle, ...]
    empty_affected_meaning: EmptyAffectedMeaning
    query_scope: ArticleBindingScope
    persistence_status: ExecutionStatus = ExecutionStatus.NOT_EXECUTED
    article_mutation_authorized: bool = False
    recommendation_mutation_authorized: bool = False
    publication_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.status) is not ImpactQueryStatus
            or self.status is not ImpactQueryStatus.LOCAL_EVALUATED
            or type(self.request_sha256) is not Sha256Digest
            or type(self.snapshot_id) is not UUID
            or type(self.external_rule_id) is not str
            or self.external_rule_id not in _EXTERNAL_RULE_POLICY_MAP
            or type(self.changed_policy_ids) is not tuple
            or not self.changed_policy_ids
            or tuple(sorted(self.changed_policy_ids)) != self.changed_policy_ids
            or len(set(self.changed_policy_ids)) != len(self.changed_policy_ids)
            or any(
                type(item) is not str or item not in _POLICY_IDS
                for item in self.changed_policy_ids
            )
            or _digest_value(self.article_binding_set_sha256)
            not in RECORDED_ARTICLE_BINDING_SET_SHA256S
            or type(self.affected_articles) is not tuple
            or any(type(item) is not AffectedArticle for item in self.affected_articles)
            or type(self.empty_affected_meaning) is not EmptyAffectedMeaning
            or (
                bool(self.affected_articles)
                and self.empty_affected_meaning is not EmptyAffectedMeaning.NOT_EMPTY
            )
            or (
                not self.affected_articles
                and self.empty_affected_meaning
                is not EmptyAffectedMeaning.ZERO_WITHIN_EXACT_COMPLETE_RECORDED_FIXTURE
            )
            or type(self.query_scope) is not ArticleBindingScope
            or self.query_scope
            is not ArticleBindingScope.EXACT_COMPLETE_RECORDED_FIXTURE
            or type(self.persistence_status) is not ExecutionStatus
            or self.persistence_status is not ExecutionStatus.NOT_EXECUTED
            or self.article_mutation_authorized is not False
            or self.recommendation_mutation_authorized is not False
            or self.publication_authorized is not False
        ):
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class PolicyReviewAlertCandidate(_Redacted):
    alert_catalog_id: str
    runbook_id: str
    severity: str
    snapshot_id: UUID
    external_rule_id: str
    request_sha256: Sha256Digest
    route: NotificationRoute
    assignment_state: AssignmentState
    delivery_authorized: bool = False
    reviewer_assignment_authorized: bool = False
    audit_write_authorized: bool = False
    external_action_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not str
                for value in (
                    self.alert_catalog_id,
                    self.runbook_id,
                    self.severity,
                    self.external_rule_id,
                )
            )
            or self.alert_catalog_id != ALERT_CATALOG_ID
            or self.runbook_id != RUNBOOK_ID
            or self.severity != "SEV4"
            or type(self.snapshot_id) is not UUID
            or type(self.external_rule_id) is not str
            or type(self.request_sha256) is not Sha256Digest
            or type(self.route) is not NotificationRoute
            or self.route is not NotificationRoute.LOCAL_LOG_ONLY
            or type(self.assignment_state) is not AssignmentState
            or self.assignment_state is not AssignmentState.NOT_ASSIGNED
            or self.delivery_authorized is not False
            or self.reviewer_assignment_authorized is not False
            or self.audit_write_authorized is not False
            or self.external_action_authorized is not False
        ):
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ReviewDueEvaluation(_Redacted):
    state: ReviewDueState
    review_due_at: datetime
    evaluated_at: datetime
    alert_candidate: PolicyReviewAlertCandidate | None
    cadence_inferred: bool = False

    def __post_init__(self) -> None:
        _utc(self.review_due_at)
        _utc(self.evaluated_at)
        expected_has_alert = self.state is ReviewDueState.OVERDUE
        if (
            type(self.state) is not ReviewDueState
            or (
                self.alert_candidate is not None
                and type(self.alert_candidate) is not PolicyReviewAlertCandidate
            )
            or (self.alert_candidate is not None) is not expected_has_alert
            or self.cadence_inferred is not False
        ):
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class ExternalPolicyRegistryReport(_Redacted):
    mode: RegistryMode
    binding_sha256: Sha256Digest
    snapshot_sha256: Sha256Digest
    request_sha256: Sha256Digest
    impact: ImpactQueryResult
    review: ReviewDueEvaluation
    official_source_attested: bool
    current_source_verified: bool
    legal_review_completed: bool
    notification_delivered: bool
    audit_written: bool
    activation_authorized: bool
    publication_authorized: bool
    live_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus

    def __post_init__(self) -> None:
        if (
            type(self.mode) is not RegistryMode
            or self.mode is not RegistryMode.RECORDED_DEV_CI_ONLY
            or type(self.binding_sha256) is not Sha256Digest
            or type(self.snapshot_sha256) is not Sha256Digest
            or type(self.request_sha256) is not Sha256Digest
            or type(self.impact) is not ImpactQueryResult
            or type(self.review) is not ReviewDueEvaluation
            or self.official_source_attested is not False
            or self.current_source_verified is not False
            or self.legal_review_completed is not False
            or self.notification_delivered is not False
            or self.audit_written is not False
            or self.activation_authorized is not False
            or self.publication_authorized is not False
            or any(
                type(status) is not ExecutionStatus
                or status is not ExecutionStatus.NOT_EXECUTED
                for status in (
                    self.live_status,
                    self.staging_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_registry(RegistryFailureCode.EVALUATION_MISMATCH)

    @property
    def fingerprint(self) -> str:
        return _sha(registry_report_payload(self))


def _binding_payload(binding: RegistryContractBinding) -> dict[str, object]:
    return {
        "contract_id": binding.contract_id,
        "contract_version": binding.contract_version,
        "external_rule_catalog": {
            "id": binding.external_rule_catalog_id,
            "version": binding.external_rule_catalog_version,
            "sha256": _digest_value(binding.external_rule_catalog_sha256),
        },
        "official_reference_catalog": {
            "id": binding.official_reference_catalog_id,
            "version": binding.official_reference_catalog_version,
            "sha256": _digest_value(binding.official_reference_catalog_sha256),
        },
        "policy_catalog": {
            "id": binding.policy_catalog_id,
            "version": binding.policy_catalog_version,
            "sha256": _digest_value(binding.policy_catalog_sha256),
        },
        "unresolved_decisions": [
            binding.source_allowlist_decision,
            binding.legal_review_decision,
            binding.notification_channel_decision,
        ],
    }


def _snapshot_payload(snapshot: ExternalPolicySnapshot) -> dict[str, object]:
    return {
        "snapshot_id": _uuid_text(snapshot.snapshot_id),
        "external_rule_id": snapshot.external_rule_id,
        "source_content_sha256": _digest_value(snapshot.source_content_sha256),
        "acquired_at": _instant_text(snapshot.acquired_at),
        "review_due_at": _instant_text(snapshot.review_due_at),
        "contract_binding_sha256": _digest_value(snapshot.contract_binding_sha256),
        "mode": snapshot.mode.value,
        "validation": snapshot.validation.value,
        "official_source_attested": snapshot.official_source_attested,
        "current_source_verified": snapshot.current_source_verified,
    }


def _version_link_payload(link: PolicyVersionLink) -> dict[str, object]:
    return {
        "snapshot_id": _uuid_text(link.snapshot_id),
        "external_rule_id": link.external_rule_id,
        "policy_id": link.policy_id,
        "policy_version": link.policy_version,
        "policy_catalog_sha256": _digest_value(link.policy_catalog_sha256),
        "reference_only": link.reference_only,
        "activation_authorized": link.activation_authorized,
    }


def _article_binding_payload(binding: ArticlePolicyBinding) -> dict[str, object]:
    return {
        "article_id": _uuid_text(binding.article_id),
        "article_version_id": _uuid_text(binding.article_version_id),
        "publication_snapshot_sha256": _digest_value(
            binding.publication_snapshot_sha256
        ),
        "policy_ids": list(binding.policy_ids),
        "scope": binding.scope.value,
        "content_mutation_authorized": binding.content_mutation_authorized,
        "recommendation_mutation_authorized": (
            binding.recommendation_mutation_authorized
        ),
        "publication_authorized": binding.publication_authorized,
    }


def article_binding_set_fingerprint(
    bindings: tuple[ArticlePolicyBinding, ...],
) -> str:
    """Hash one exact non-empty complete recorded article-binding universe."""

    if (
        type(bindings) is not tuple
        or not 1 <= len(bindings) <= MAX_RECORDED_ARTICLES
        or any(type(item) is not ArticlePolicyBinding for item in bindings)
    ):
        fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)
    keys = tuple(
        (_uuid_text(item.article_id), _uuid_text(item.article_version_id))
        for item in bindings
    )
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)
    try:
        return _sha([_article_binding_payload(item) for item in bindings])
    except RegistryFailure:
        raise
    except Exception:
        fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)


def _registry_request_payload_trusted(
    request: ExternalPolicyRegistryRequest,
) -> dict[str, object]:
    return {
        "binding": _binding_payload(request.binding),
        "snapshot": _snapshot_payload(request.snapshot),
        "version_links": [
            _version_link_payload(item) for item in request.version_links
        ],
        "article_bindings": [
            _article_binding_payload(item) for item in request.article_bindings
        ],
        "article_binding_set_sha256": _digest_value(request.article_binding_set_sha256),
        "evaluated_at": _instant_text(request.evaluated_at),
    }


def _affected_payload(item: AffectedArticle) -> dict[str, object]:
    return {
        "article_id": _uuid_text(item.article_id),
        "article_version_id": _uuid_text(item.article_version_id),
        "publication_snapshot_sha256": _digest_value(item.publication_snapshot_sha256),
        "matched_policy_ids": list(item.matched_policy_ids),
    }


def _alert_payload(item: PolicyReviewAlertCandidate) -> dict[str, object]:
    return {
        "alert_catalog_id": item.alert_catalog_id,
        "runbook_id": item.runbook_id,
        "severity": item.severity,
        "snapshot_id": _uuid_text(item.snapshot_id),
        "external_rule_id": item.external_rule_id,
        "request_sha256": _digest_value(item.request_sha256),
        "route": item.route.value,
        "assignment_state": item.assignment_state.value,
        "delivery_authorized": item.delivery_authorized,
        "reviewer_assignment_authorized": item.reviewer_assignment_authorized,
        "audit_write_authorized": item.audit_write_authorized,
        "external_action_authorized": item.external_action_authorized,
    }


def registry_report_payload(report: ExternalPolicyRegistryReport) -> dict[str, object]:
    if type(report) is not ExternalPolicyRegistryReport:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    impact = report.impact
    review = report.review
    return {
        "mode": report.mode.value,
        "binding_sha256": _digest_value(report.binding_sha256),
        "snapshot_sha256": _digest_value(report.snapshot_sha256),
        "request_sha256": _digest_value(report.request_sha256),
        "impact": {
            "status": impact.status.value,
            "request_sha256": _digest_value(impact.request_sha256),
            "snapshot_id": _uuid_text(impact.snapshot_id),
            "external_rule_id": impact.external_rule_id,
            "changed_policy_ids": list(impact.changed_policy_ids),
            "article_binding_set_sha256": _digest_value(
                impact.article_binding_set_sha256
            ),
            "affected_articles": [
                _affected_payload(item) for item in impact.affected_articles
            ],
            "empty_affected_meaning": impact.empty_affected_meaning.value,
            "query_scope": impact.query_scope.value,
            "persistence_status": impact.persistence_status.value,
            "article_mutation_authorized": impact.article_mutation_authorized,
            "recommendation_mutation_authorized": (
                impact.recommendation_mutation_authorized
            ),
            "publication_authorized": impact.publication_authorized,
        },
        "review": {
            "state": review.state.value,
            "review_due_at": _instant_text(review.review_due_at),
            "evaluated_at": _instant_text(review.evaluated_at),
            "alert_candidate": (
                None
                if review.alert_candidate is None
                else _alert_payload(review.alert_candidate)
            ),
            "cadence_inferred": review.cadence_inferred,
        },
        "authority": {
            "official_source_attested": report.official_source_attested,
            "current_source_verified": report.current_source_verified,
            "legal_review_completed": report.legal_review_completed,
            "notification_delivered": report.notification_delivered,
            "audit_written": report.audit_written,
            "activation_authorized": report.activation_authorized,
            "publication_authorized": report.publication_authorized,
        },
        "execution": {
            "live": report.live_status.value,
            "staging": report.staging_status.value,
            "release": report.release_status.value,
            "production": report.production_status.value,
        },
    }


def registry_report_json(report: ExternalPolicyRegistryReport) -> str:
    return _canonical_json_bytes(registry_report_payload(report)).decode("ascii")


def _snapshot_request_unchecked(candidate: object) -> ExternalPolicyRegistryRequest:
    if type(candidate) is not ExternalPolicyRegistryRequest:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)
    binding = RegistryContractBinding(
        contract_id=candidate.binding.contract_id,
        contract_version=candidate.binding.contract_version,
        external_rule_catalog_id=candidate.binding.external_rule_catalog_id,
        external_rule_catalog_version=candidate.binding.external_rule_catalog_version,
        external_rule_catalog_sha256=Sha256Digest(
            candidate.binding.external_rule_catalog_sha256.value
        ),
        official_reference_catalog_id=candidate.binding.official_reference_catalog_id,
        official_reference_catalog_version=(
            candidate.binding.official_reference_catalog_version
        ),
        official_reference_catalog_sha256=Sha256Digest(
            candidate.binding.official_reference_catalog_sha256.value
        ),
        policy_catalog_id=candidate.binding.policy_catalog_id,
        policy_catalog_version=candidate.binding.policy_catalog_version,
        policy_catalog_sha256=Sha256Digest(
            candidate.binding.policy_catalog_sha256.value
        ),
        source_allowlist_decision=candidate.binding.source_allowlist_decision,
        legal_review_decision=candidate.binding.legal_review_decision,
        notification_channel_decision=(candidate.binding.notification_channel_decision),
    )
    snapshot = ExternalPolicySnapshot(
        snapshot_id=UUID(str(candidate.snapshot.snapshot_id)),
        external_rule_id=candidate.snapshot.external_rule_id,
        source_content_sha256=Sha256Digest(
            candidate.snapshot.source_content_sha256.value
        ),
        acquired_at=candidate.snapshot.acquired_at,
        review_due_at=candidate.snapshot.review_due_at,
        contract_binding_sha256=Sha256Digest(
            candidate.snapshot.contract_binding_sha256.value
        ),
        mode=candidate.snapshot.mode,
        validation=candidate.snapshot.validation,
        official_source_attested=candidate.snapshot.official_source_attested,
        current_source_verified=candidate.snapshot.current_source_verified,
    )
    links = tuple(
        PolicyVersionLink(
            snapshot_id=UUID(str(item.snapshot_id)),
            external_rule_id=item.external_rule_id,
            policy_id=item.policy_id,
            policy_version=item.policy_version,
            policy_catalog_sha256=Sha256Digest(item.policy_catalog_sha256.value),
            reference_only=item.reference_only,
            activation_authorized=item.activation_authorized,
        )
        for item in candidate.version_links
    )
    articles = tuple(
        ArticlePolicyBinding(
            article_id=UUID(str(item.article_id)),
            article_version_id=UUID(str(item.article_version_id)),
            publication_snapshot_sha256=Sha256Digest(
                item.publication_snapshot_sha256.value
            ),
            policy_ids=tuple(item.policy_ids),
            scope=item.scope,
            content_mutation_authorized=item.content_mutation_authorized,
            recommendation_mutation_authorized=(
                item.recommendation_mutation_authorized
            ),
            publication_authorized=item.publication_authorized,
        )
        for item in candidate.article_bindings
    )
    return ExternalPolicyRegistryRequest(
        binding=binding,
        snapshot=snapshot,
        version_links=links,
        article_bindings=articles,
        article_binding_set_sha256=Sha256Digest(
            candidate.article_binding_set_sha256.value
        ),
        evaluated_at=candidate.evaluated_at,
    )


def _snapshot_request(candidate: object) -> ExternalPolicyRegistryRequest:
    try:
        return _snapshot_request_unchecked(candidate)
    except RegistryFailure:
        raise
    except Exception:
        fail_registry(RegistryFailureCode.INVALID_ARGUMENT)


def registry_request_payload(
    request: ExternalPolicyRegistryRequest,
) -> dict[str, object]:
    trusted = _snapshot_request(request)
    return _registry_request_payload_trusted(trusted)


def evaluate_external_policy_registry(
    request: ExternalPolicyRegistryRequest,
) -> ExternalPolicyRegistryReport:
    trusted = _snapshot_request(request)
    binding_sha256 = trusted.binding.fingerprint
    if trusted.snapshot.contract_binding_sha256.value != binding_sha256:
        fail_registry(RegistryFailureCode.SNAPSHOT_BINDING_MISMATCH)

    expected_policy_ids = tuple(
        sorted(_EXTERNAL_RULE_POLICY_MAP[trusted.snapshot.external_rule_id])
    )
    actual_policy_ids = tuple(item.policy_id for item in trusted.version_links)
    if (
        actual_policy_ids != expected_policy_ids
        or len(set(actual_policy_ids)) != len(actual_policy_ids)
        or any(
            item.snapshot_id != trusted.snapshot.snapshot_id
            or item.external_rule_id != trusted.snapshot.external_rule_id
            for item in trusted.version_links
        )
    ):
        fail_registry(RegistryFailureCode.VERSION_LINK_SET_MISMATCH)

    article_keys = tuple(
        (str(item.article_id), str(item.article_version_id))
        for item in trusted.article_bindings
    )
    if article_keys != tuple(sorted(article_keys)) or len(set(article_keys)) != len(
        article_keys
    ):
        fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)
    article_binding_set_sha256 = article_binding_set_fingerprint(
        trusted.article_bindings
    )
    if (
        article_binding_set_sha256 != trusted.article_binding_set_sha256.value
        or article_binding_set_sha256 not in RECORDED_ARTICLE_BINDING_SET_SHA256S
    ):
        fail_registry(RegistryFailureCode.ARTICLE_BINDING_SET_INVALID)

    request_sha256 = trusted.fingerprint
    affected: list[AffectedArticle] = []
    changed_set = frozenset(expected_policy_ids)
    for article in trusted.article_bindings:
        matched = tuple(sorted(changed_set.intersection(article.policy_ids)))
        if matched:
            affected.append(
                AffectedArticle(
                    article_id=article.article_id,
                    article_version_id=article.article_version_id,
                    publication_snapshot_sha256=article.publication_snapshot_sha256,
                    matched_policy_ids=matched,
                )
            )

    impact = ImpactQueryResult(
        status=ImpactQueryStatus.LOCAL_EVALUATED,
        request_sha256=Sha256Digest(request_sha256),
        snapshot_id=trusted.snapshot.snapshot_id,
        external_rule_id=trusted.snapshot.external_rule_id,
        changed_policy_ids=expected_policy_ids,
        article_binding_set_sha256=Sha256Digest(article_binding_set_sha256),
        affected_articles=tuple(affected),
        empty_affected_meaning=(
            EmptyAffectedMeaning.NOT_EMPTY
            if affected
            else EmptyAffectedMeaning.ZERO_WITHIN_EXACT_COMPLETE_RECORDED_FIXTURE
        ),
        query_scope=ArticleBindingScope.EXACT_COMPLETE_RECORDED_FIXTURE,
    )

    if trusted.evaluated_at < trusted.snapshot.review_due_at:
        due_state = ReviewDueState.NOT_DUE
    elif trusted.evaluated_at == trusted.snapshot.review_due_at:
        due_state = ReviewDueState.DUE
    else:
        due_state = ReviewDueState.OVERDUE
    alert = (
        PolicyReviewAlertCandidate(
            alert_catalog_id=ALERT_CATALOG_ID,
            runbook_id=RUNBOOK_ID,
            severity="SEV4",
            snapshot_id=trusted.snapshot.snapshot_id,
            external_rule_id=trusted.snapshot.external_rule_id,
            request_sha256=Sha256Digest(request_sha256),
            route=NotificationRoute.LOCAL_LOG_ONLY,
            assignment_state=AssignmentState.NOT_ASSIGNED,
        )
        if due_state is ReviewDueState.OVERDUE
        else None
    )
    review = ReviewDueEvaluation(
        state=due_state,
        review_due_at=trusted.snapshot.review_due_at,
        evaluated_at=trusted.evaluated_at,
        alert_candidate=alert,
    )
    return ExternalPolicyRegistryReport(
        mode=RegistryMode.RECORDED_DEV_CI_ONLY,
        binding_sha256=Sha256Digest(binding_sha256),
        snapshot_sha256=Sha256Digest(trusted.snapshot.fingerprint),
        request_sha256=Sha256Digest(request_sha256),
        impact=impact,
        review=review,
        official_source_attested=False,
        current_source_verified=False,
        legal_review_completed=False,
        notification_delivered=False,
        audit_written=False,
        activation_authorized=False,
        publication_authorized=False,
        live_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )


__all__ = [
    "ALERT_CATALOG_ID",
    "ArticleBindingScope",
    "ArticlePolicyBinding",
    "AssignmentState",
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "EmptyAffectedMeaning",
    "ExecutionStatus",
    "EXTERNAL_RULE_CATALOG_ID",
    "EXTERNAL_RULE_CATALOG_SHA256",
    "EXTERNAL_RULE_CATALOG_VERSION",
    "EXTERNAL_RULE_POLICY_LINKS",
    "ExternalPolicyRegistryReport",
    "ExternalPolicyRegistryRequest",
    "ExternalPolicySnapshot",
    "ImpactQueryStatus",
    "LEGAL_REVIEW_DECISION",
    "LOCAL_STATUS",
    "MAX_RECORDED_ARTICLES",
    "RECORDED_ARTICLE_BINDING_SET_SHA256S",
    "NOTIFICATION_CHANNEL_DECISION",
    "NotificationRoute",
    "OFFICIAL_REFERENCE_CATALOG_ID",
    "OFFICIAL_REFERENCE_CATALOG_SHA256",
    "OFFICIAL_REFERENCE_CATALOG_VERSION",
    "OPEN_SOURCE_ALLOWLIST_DECISION",
    "PolicyVersionLink",
    "RegistryContractBinding",
    "RegistryFailure",
    "RegistryFailureCode",
    "RegistryMode",
    "ReviewDueState",
    "RUNBOOK_ID",
    "SnapshotValidation",
    "article_binding_set_fingerprint",
    "evaluate_external_policy_registry",
    "fail_registry",
    "registry_report_json",
    "registry_report_payload",
    "registry_request_payload",
]
