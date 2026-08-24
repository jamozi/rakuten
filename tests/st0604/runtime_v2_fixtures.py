"""Recorded-local synthetic fixtures for ST-0604 V2 tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from uuid import UUID

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
    SystemEntropySource,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_authorization import RecordedSqliteAuthorizationRepository
from raos.adapters.sqlite_source_packet_lifecycle_runtime_v2 import (
    OwnerPrivateSqliteSourcePacketStoreV2,
    SourcePacketSqliteCommitFaultV2,
)
from raos.application.evidence.fact_conflict_runtime_v2 import (
    DurableFactConflictDetectionServiceV2,
)
from raos.application.evidence.source_packet_lifecycle_runtime_v2 import (
    DurableSourcePacketLifecycleServiceV2,
)
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.authorization import DurableAuthorizationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    SourcePacketContentV2,
    SourcePacketPurposeV2,
)
from raos.domain.iam.authentication import (
    Issuer,
    PrincipalIdentity as AuthenticatedPrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    AuthorizationTarget,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    OperationId,
    PolicyRevision,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
)
from tests.st0603.st0603_runtime_v2_fixtures import (
    conflict_store_v2,
    derive_persisted_fact_v2,
    exact_persisted_fact_v2,
)


PACKET_ID = UUID("74345678-1234-4234-8234-123456789001")
SITE_ID = UUID("74345678-1234-4234-8234-123456789002")
ARTICLE_PLAN_ID = UUID("74345678-1234-4234-8234-123456789003")
REVIEW_ASSIGNMENT_ID = UUID("74345678-1234-4234-8234-123456789004")
EDITOR_FINGERPRINT = hashlib.sha256(b"RECORDED-ST0604-EDITOR").hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorizationFixtureV2:
    service: DurableAuthorizationService
    session: Session
    command: AuthorizationEvaluationCommand
    result: AuthorizationCommandResult
    now: datetime


def source_content_v2(
    root: Path,
    *,
    conflicting: bool = False,
    label: str = "base",
) -> SourcePacketContentV2:
    first = exact_persisted_fact_v2(root / f"fact-{label}")
    if label != "base":
        first = derive_persisted_fact_v2(first, label=f"{label}-source")
    inputs = (first,)
    if conflicting:
        inputs = (
            first,
            derive_persisted_fact_v2(
                first,
                label=f"{label}-conflict",
                price_delta=1,
            ),
        )
    conflict_root = root / f"conflict-{label}"
    persisted = (
        DurableFactConflictDetectionServiceV2(conflict_store_v2(conflict_root))
        .detect(inputs=inputs)
        .persisted
    )
    return SourcePacketContentV2(
        purpose=SourcePacketPurposeV2.ARTICLE_DRAFT,
        fact_batches=tuple(sorted(inputs, key=lambda item: item.batch.batch_id.hex)),
        conflict_scan=persisted,
    )


def _authentication_service(session: Session) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(session)
    return AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=session.principal,
        ),
        repository=repository,
        entropy=SystemEntropySource(),
    )


def authorization_fixture_v2(
    root: Path,
    *,
    site_id: UUID = SITE_ID,
    review_assignment_id: UUID = REVIEW_ASSIGNMENT_ID,
    operation_id: str = "PUBADM-004",
    action: str = "review_article",
    state: str = "IN_PROGRESS",
    label: str = "ALLOW",
    now: datetime,
) -> AuthorizationFixtureV2:
    principal = AuthenticatedPrincipalIdentity(
        issuer=Issuer("https://st0604.test.invalid"),
        subject=Subject("RECORDED:ST0604:REVIEWER"),
        display_name="ST-0604 recorded reviewer",
    )
    session = Session(
        session_id=SessionId.from_bytes(
            hashlib.sha256(f"ST0604-SESSION-{label}".encode("ascii")).digest()
        ),
        principal=principal,
        created_at=now - timedelta(minutes=10),
        last_seen_at=now - timedelta(seconds=1),
        idle_expires_at=now + timedelta(hours=1),
        absolute_expires_at=now + timedelta(hours=2),
        revoked_at=None,
    )
    target = AuthorizationTarget(
        scope=ResourceScope(
            kind=ResourceScopeKind.REVIEW_ASSIGNMENT,
            site_id=site_id,
            resource_id=review_assignment_id,
        ),
        state=ResourceState(state),
    )
    command = AuthorizationEvaluationCommand(
        command_id=AuthorizationCommandId(f"RECORDED:ST0604:AUTH:{label}"),
        operation_id=OperationId(operation_id),
        target=target,
        correlation_id=CorrelationId(f"RECORDED:ST0604:CORRELATION:{label}"),
        expected_policy_revision=PolicyRevision("RECORDED:ST0604:POLICY:V1"),
        expected_entitlement_revision=EntitlementRevision(
            "RECORDED:ST0604:ENTITLEMENT:V1"
        ),
        observed_at=now,
    )
    private_root = root / f"authorization-{label}"
    private_root.mkdir(mode=0o700, parents=True)
    repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=private_root,
    )
    session_fingerprint = session.session_id.fingerprint()
    request_digest = command.request_digest(session_fingerprint=session_fingerprint)
    decision = AuthorizationDecision(
        correlation_id=command.correlation_id,
        effect=DecisionEffect.ALLOW,
        reason=AuthorizationDecisionReason.RULE_MATCH,
        policy_revision=command.expected_policy_revision,
        policy_fingerprint=hashlib.sha256(b"ST0604-POLICY").hexdigest(),
        entitlement_revision=command.expected_entitlement_revision,
        matched_rule_id=RuleId("RECORDED:ST0604:PUBADM004:REVIEWER"),
        action=ActionCode(action),
        target=target,
    )
    unit = repository.begin()
    result = unit.record_decision(
        command_id=command.command_id,
        request_digest=request_digest,
        session_fingerprint=session_fingerprint,
        decision=decision,
        occurred_at=now,
        step_up_receipt_fingerprint=None,
    )
    unit.commit()
    service = DurableAuthorizationService(
        session_service=_authentication_service(session),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    return AuthorizationFixtureV2(
        service=service,
        session=session,
        command=command,
        result=result,
        now=now,
    )


def source_packet_store_v2(
    root: Path,
    *,
    faults: tuple[SourcePacketSqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteSourcePacketStoreV2:
    return OwnerPrivateSqliteSourcePacketStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "source-packet-private",
        commit_faults=faults,
    )


def source_packet_runtime_v2(
    *,
    authorization: AuthorizationFixtureV2,
    store: OwnerPrivateSqliteSourcePacketStoreV2,
) -> DurableSourcePacketLifecycleServiceV2:
    return DurableSourcePacketLifecycleServiceV2(
        authorization_service=authorization.service,
        store=store,
    )


__all__ = [
    "ARTICLE_PLAN_ID",
    "AuthorizationFixtureV2",
    "EDITOR_FINGERPRINT",
    "PACKET_ID",
    "REVIEW_ASSIGNMENT_ID",
    "SITE_ID",
    "authorization_fixture_v2",
    "source_content_v2",
    "source_packet_runtime_v2",
    "source_packet_store_v2",
]
