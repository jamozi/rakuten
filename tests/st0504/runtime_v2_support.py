"""Recorded local fixtures for the ST-0504 V2 runtime tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
from uuid import UUID

from tests.st0503.runtime_v2_fixtures import (
    NORMALIZED_AT_V2,
    normalization_service_v2,
    normalization_store_v2,
    source_fixture_v2,
)

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
    SystemEntropySource,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_authorization import RecordedSqliteAuthorizationRepository
from raos.adapters.sqlite_product_identity_runtime_v2 import (
    OwnerPrivateSqliteProductIdentityStoreV2,
    ProductIdentitySqliteCommitFaultV2,
)
from raos.application.catalog.product_identity_runtime_v2 import (
    DurableProductIdentityRuntimeV2,
)
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.authorization import DurableAuthorizationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    PersistedCatalogNormalizationV2,
)
from raos.domain.catalog.product_identity_runtime_v2 import (
    PersistedProductIdentityReviewQueueV2,
    PrepareProductIdentityReviewQueueCommandV2,
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
    RuleId,
)


SITE_ID_V2 = UUID("72345678-1234-4234-8234-123456789001")
AUTH_RESOURCE_ID_V2 = UUID("72345678-1234-4234-8234-123456789002")
QUEUE_OPERATION_ID_V2 = UUID("72345678-1234-4234-8234-123456789003")
DECISION_OPERATION_IDS_V2 = (
    UUID("72345678-1234-4234-8234-123456789101"),
    UUID("72345678-1234-4234-8234-123456789102"),
    UUID("72345678-1234-4234-8234-123456789103"),
)
DECISION_AT_V2 = NORMALIZED_AT_V2 + timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class AuthorizationFixtureV2:
    service: DurableAuthorizationService
    session: Session
    command: AuthorizationEvaluationCommand
    result: AuthorizationCommandResult


def persisted_catalog_v2(
    root: Path,
    *,
    item_ordinals: tuple[int, ...] = (1, 2),
) -> PersistedCatalogNormalizationV2:
    fixture = source_fixture_v2(
        root / "source",
        item_ordinals=item_ordinals,
    )
    store = normalization_store_v2(root / "normalization")
    return (
        normalization_service_v2(fixture=fixture, store=store)
        .normalize(fixture.command)
        .persisted
    )


def queue_command_v2(
    source: PersistedCatalogNormalizationV2,
    *,
    operation_id: UUID = QUEUE_OPERATION_ID_V2,
    site_id: UUID = SITE_ID_V2,
) -> PrepareProductIdentityReviewQueueCommandV2:
    return PrepareProductIdentityReviewQueueCommandV2.from_persisted_catalog(
        operation_id=operation_id,
        site_id=site_id,
        source=source,
        prepared_at=NORMALIZED_AT_V2,
    )


def product_identity_store_v2(
    root: Path,
    *,
    faults: tuple[ProductIdentitySqliteCommitFaultV2, ...] = (),
) -> OwnerPrivateSqliteProductIdentityStoreV2:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return OwnerPrivateSqliteProductIdentityStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root / "st0504-private",
        commit_faults=faults,
    )


def _session(*, now: datetime = DECISION_AT_V2) -> Session:
    principal = AuthenticatedPrincipalIdentity(
        issuer=Issuer("https://st0504.test.invalid"),
        subject=Subject("RECORDED:ST0504:REVIEWER"),
        display_name="ST-0504 recorded reviewer",
    )
    return Session(
        session_id=SessionId.from_bytes(
            hashlib.sha256(b"ST0504-RECORDED-SESSION").digest()
        ),
        principal=principal,
        created_at=now - timedelta(minutes=10),
        last_seen_at=now - timedelta(seconds=1),
        idle_expires_at=now + timedelta(hours=1),
        absolute_expires_at=now + timedelta(hours=2),
        revoked_at=None,
    )


def _authentication_service(active_session: Session) -> AuthenticationService:
    repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    repository.create_session(active_session)
    return AuthenticationService(
        provider=DevelopmentOidcAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            principal=active_session.principal,
        ),
        repository=repository,
        entropy=SystemEntropySource(),
    )


def authorization_fixture_v2(
    root: Path,
    *,
    label: str = "1",
    site_id: UUID = SITE_ID_V2,
    resource_id: UUID = AUTH_RESOURCE_ID_V2,
    action: str = "manage_product_identity",
    operation_id: str = "CAT-006",
    now: datetime = DECISION_AT_V2,
) -> AuthorizationFixtureV2:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    active_session = _session(now=now)
    target = AuthorizationTarget(
        scope=ResourceScope(
            kind=ResourceScopeKind.PRODUCT,
            site_id=site_id,
            resource_id=resource_id,
        ),
        state=None,
    )
    command = AuthorizationEvaluationCommand(
        command_id=AuthorizationCommandId(f"RECORDED:ST0504:AUTH:{label}"),
        operation_id=OperationId(operation_id),
        target=target,
        correlation_id=CorrelationId(f"RECORDED:ST0504:CORRELATION:{label}"),
        expected_policy_revision=PolicyRevision("RECORDED:ST0504:POLICY:V1"),
        expected_entitlement_revision=EntitlementRevision(
            "RECORDED:ST0504:ENTITLEMENT:V1"
        ),
        observed_at=now,
    )
    repository_root = root / f"authorization-{label}"
    repository_root.mkdir(mode=0o700)
    repository = RecordedSqliteAuthorizationRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=repository_root,
    )
    session_fingerprint = active_session.session_id.fingerprint()
    request_digest = command.request_digest(session_fingerprint=session_fingerprint)
    decision = AuthorizationDecision(
        correlation_id=command.correlation_id,
        effect=DecisionEffect.ALLOW,
        reason=AuthorizationDecisionReason.RULE_MATCH,
        policy_revision=command.expected_policy_revision,
        policy_fingerprint=hashlib.sha256(
            b"RECORDED-ST0504-POLICY-FIXTURE"
        ).hexdigest(),
        entitlement_revision=command.expected_entitlement_revision,
        matched_rule_id=RuleId("RECORDED:ST0504:CAT006:HUMAN"),
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
        session_service=_authentication_service(active_session),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    return AuthorizationFixtureV2(
        service=service,
        session=active_session,
        command=command,
        result=result,
    )


def runtime_v2(
    *,
    authorization: AuthorizationFixtureV2,
    store: OwnerPrivateSqliteProductIdentityStoreV2,
) -> DurableProductIdentityRuntimeV2:
    return DurableProductIdentityRuntimeV2(
        authorization_service=authorization.service,
        store=store,
    )


def prepared_queue_v2(
    root: Path,
    *,
    item_ordinals: tuple[int, ...] = (1, 2),
    faults: tuple[ProductIdentitySqliteCommitFaultV2, ...] = (),
) -> tuple[
    DurableProductIdentityRuntimeV2,
    OwnerPrivateSqliteProductIdentityStoreV2,
    AuthorizationFixtureV2,
    PersistedProductIdentityReviewQueueV2,
]:
    source = persisted_catalog_v2(root / "catalog", item_ordinals=item_ordinals)
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(root / "auth")
    store = product_identity_store_v2(root / "identity", faults=faults)
    runtime = runtime_v2(authorization=authorization, store=store)
    queue = runtime.prepare_review_queue(command).persisted
    return runtime, store, authorization, queue


__all__ = [
    "AUTH_RESOURCE_ID_V2",
    "AuthorizationFixtureV2",
    "DECISION_AT_V2",
    "DECISION_OPERATION_IDS_V2",
    "QUEUE_OPERATION_ID_V2",
    "SITE_ID_V2",
    "authorization_fixture_v2",
    "persisted_catalog_v2",
    "prepared_queue_v2",
    "product_identity_store_v2",
    "queue_command_v2",
    "runtime_v2",
]
