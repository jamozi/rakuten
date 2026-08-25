"""Fresh integration-audit regressions for the ST-0308 transaction boundary."""

from __future__ import annotations

import ast
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
import yaml

from raos.adapters.persistence.sqlalchemy import unit_of_work as sqlalchemy_uow
from raos.adapters.persistence.sqlalchemy.identity import WorkloadProfile
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.adapters.persistence.sqlalchemy.repositories import (
    catalog,
    editorial,
    portfolio,
)
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    bind_session_runtime,
    clear_session_runtime,
    record_successful_dml,
    require_no_unstaged_pending_events,
)
from raos.adapters.persistence.sqlalchemy.shared import (
    SqlAlchemyIdempotencyRepository,
    SqlAlchemyOutboxEventAppender,
    _execute_one,
)
from raos.adapters.persistence.sqlalchemy.transaction import (
    _ExecutionState,
    _ExecutionStateFactory,
    _SqlAlchemyTransaction,
)
from raos.adapters.persistence.sqlalchemy.unit_of_work import (
    _SqlAlchemyOuterUnitOfWork,
    SqlAlchemyIdempotentPortfolioUnitOfWorkFactory,
    SqlAlchemyPortfolioUnitOfWorkFactory,
)
from raos.domain.shared.persistence import AwareUtcDateTime, PendingEventBuffer
from raos.domain.editorial.aggregates import (
    ArticleDisclosureContext,
    ArticleMethodologyBinding,
    ReviewCommentState,
    SeoMetadataVersionState,
    StructuredDataManifest,
)
from raos.domain.editorial.enums import (
    ReviewCommentStatus,
    SeoMetadataVersionStatus,
    StructuredDataManifestValidationStatus,
)
from raos.domain.editorial.ids import (
    EditorialMethodologyVersionId,
    ReviewCommentId,
    SeoMetadataVersionId,
    StructuredDataManifestId,
    ThreadId,
)
from raos.domain.editorial.values import SeoMetadataVersionMetadataJson
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.ids import ObjectArtifactId
from raos.domain.catalog.values import ProviderEndpointNonSecretConfigJson
from raos.domain.catalog.aggregates import ProviderEndpoint
from raos.domain.catalog.enums import ProviderEndpointStatus
from raos.domain.portfolio.aggregates import ActionCandidate
from raos.domain.portfolio.enums import ActionCandidateStatus
from raos.domain.shared.events import DomainEvent
from raos.domain.shared.idempotency import (
    ActorFingerprint,
    ClaimGranted,
    IdempotencyClaim,
    IdempotencyIdentity,
    IdempotencyKey,
    IdempotencyOutcome,
    IdempotencyOutcomeDisposition,
    ReplayFailed,
    RequestHash,
    RouteKey,
    _issue_claim_handle,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import Sha256Digest
from raos.ports.persistence.audit import SanitizedAuditDetails
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.transaction import TransactionState
from scripts import build_st0308_persistence as generator
from tests.st0308_persistence.support import FIXED_TIME, make_context, make_event
from tests.postgresql18 import PostgreSQLCluster
from tests.st0308_persistence.test_postgresql_runtime import (
    _api_engine,
    _principal,
    _seed_principal,
    _site,
    _upgrade,
)
from tests.st0308_persistence.test_w2a_state_cas_and_ownership import (
    _Result,
    _ScriptedSession,
    _action,
    _provider,
    _provider_row,
)
from tests.st0308_persistence.test_w2b_evidence_editorial_repositories import (
    _article_version_graph,
    _uuid,
)


ErrorFactory = Callable[[], Exception]
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class _UnregisterRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, _SqlAlchemyTransaction]] = []
        self._registry: dict[UUID, object] = {}

    def _unregister(
        self,
        transaction_id: UUID,
        transaction: _SqlAlchemyTransaction,
    ) -> None:
        self.calls.append((transaction_id, transaction))


def _bound_transaction(*, suffix: str) -> tuple[Session, _SqlAlchemyTransaction]:
    session = Session()
    transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=make_context(suffix=suffix),
        timestamp=AwareUtcDateTime(FIXED_TIME),
        session=session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    return session, transaction


def _assert_not_unknown(error: PersistenceError) -> None:
    assert error.code is not PersistenceErrorCode.UNKNOWN_COMMIT


class _DmlAwareScriptedSession(_ScriptedSession):
    """Fake Session that preserves the real UoW successful-DML signal."""

    def execute(self, statement: object, *args: object, **kwargs: object) -> Any:
        result = super().execute(statement, *args, **kwargs)
        if (
            getattr(statement, "is_insert", False)
            or getattr(statement, "is_update", False)
            or getattr(statement, "is_delete", False)
        ):
            record_successful_dml(self)
        return result


def _commit_poisoned(
    transaction: _SqlAlchemyTransaction,
    session: Session,
) -> tuple[PersistenceError, _UnregisterRecorder, TransactionState]:
    recorder = _UnregisterRecorder()
    unit = object.__new__(_SqlAlchemyOuterUnitOfWork)
    unit._entered = True
    unit._state = TransactionState.ACTIVE
    unit._transaction = transaction
    unit._session = session
    unit._checkout = None
    unit._guard = None
    unit._factory = cast(Any, recorder)

    with pytest.raises(PersistenceError) as caught:
        unit.commit()
    return caught.value, recorder, unit._state


@pytest.mark.parametrize(
    ("error_factory", "expected_code"),
    (
        (
            lambda: IntegrityError(
                "INSERT secret",
                {"credential": "must-not-leak"},
                RuntimeError("driver-secret"),
            ),
            PersistenceErrorCode.INTEGRITY_CONFLICT,
        ),
        (
            lambda: DBAPIError(
                "UPDATE secret",
                {"credential": "must-not-leak"},
                RuntimeError("driver-secret"),
            ),
            PersistenceErrorCode.STORAGE_CORRUPTION,
        ),
        (
            lambda: RuntimeError("untrusted-local-detail"),
            PersistenceErrorCode.STORAGE_CORRUPTION,
        ),
        (
            lambda: PersistenceError(PersistenceErrorCode.NOT_FOUND),
            PersistenceErrorCode.NOT_FOUND,
        ),
    ),
    ids=("integrity", "dbapi", "generic", "persistence"),
)
def test_repository_operation_failure_poison_is_known_rollback(
    monkeypatch: pytest.MonkeyPatch,
    error_factory: ErrorFactory,
    expected_code: PersistenceErrorCode,
) -> None:
    session, transaction = _bound_transaction(suffix=expected_code.value)
    event = make_event(suffix=expected_code.value)
    buffer = PendingEventBuffer[DomainEvent]((event,))
    buffer.acknowledge_events((event.event_id,))
    transaction.acknowledge(buffer)

    execute_calls = 0

    def fail_execute(*_args: object, **_kwargs: object) -> None:
        nonlocal execute_calls
        execute_calls += 1
        raise error_factory()

    monkeypatch.setattr(session, "execute", fail_execute)
    try:
        with pytest.raises(PersistenceError) as operation:
            _execute_one(transaction, text("SELECT 1"))
        assert operation.value.code is expected_code
        assert str(operation.value) == expected_code.value
        assert operation.value.__cause__ is None
        assert execute_calls == 1

        assert transaction.rollback_only is True
        assert buffer.pending_events() == (event,)
        assert transaction.acknowledged_buffers == []

        with pytest.raises(PersistenceError) as subsequent:
            _execute_one(transaction, text("SELECT 2"))
        assert subsequent.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
        assert execute_calls == 1

        commit_error, recorder, state = _commit_poisoned(transaction, session)
        assert commit_error.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
        _assert_not_unknown(commit_error)
        assert state is TransactionState.ROLLED_BACK
        assert transaction.active is False
        assert recorder.calls == [(transaction.transaction_id, transaction)]
        assert buffer.pending_events() == (event,)
    finally:
        session.close()


def test_state_cas_methods_resolve_to_exact_repository_surface_owner() -> None:
    contract_directory = REPOSITORY_ROOT / "changes/st-0308/contracts/persistence"
    repository_surface = yaml.safe_load(
        (contract_directory / "repository-surface-matrix.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    state_cas = yaml.safe_load(
        (contract_directory / "state-cas-matrix.v1.yaml").read_text(encoding="utf-8")
    )
    domain_mapper = yaml.safe_load(
        (contract_directory / "domain-mapper-matrix.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    repository_methods = {
        repository["protocol"]: {
            method.split("(", 1)[0] for method in repository["methods"]
        }
        for repositories in repository_surface["modules"].values()
        for repository in repositories.values()
    }
    owner_by_relation = {
        relation["relation"]: relation["repository_owner"]["protocol"]
        for relation in domain_mapper["relations"]
    }
    observed_methods: set[str] = set()

    assert len(state_cas["relations"]) == 24
    for relation_name, relation in state_cas["relations"].items():
        expected_owner = owner_by_relation[relation_name]
        for edge in relation["edges"]:
            protocol, separator, method = edge["method"].partition(".")
            assert separator == "."
            assert protocol == expected_owner
            assert method in repository_methods[protocol]
            observed_methods.add(edge["method"])

    assert observed_methods


def test_all_53_repository_classes_implement_exact_202_guarded_methods() -> None:
    contract_directory = REPOSITORY_ROOT / "changes/st-0308/contracts/persistence"
    repository_surface = yaml.safe_load(
        (contract_directory / "repository-surface-matrix.v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    observed_classes = 0
    observed_methods = 0
    defects: list[str] = []

    for module_name, repositories in repository_surface["modules"].items():
        source_path = (
            REPOSITORY_ROOT
            / "python/raos/adapters/persistence/sqlalchemy/repositories"
            / f"{module_name}.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"), source_path.name)
        classes = {
            node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
        }
        for repository in repositories.values():
            class_name = f"SqlAlchemy{repository['protocol']}"
            repository_class = classes.get(class_name)
            if repository_class is None:
                defects.append(f"{class_name}:missing")
                continue
            observed_classes += 1
            decorators = {ast.unparse(item) for item in repository_class.decorator_list}
            if "guard_repository_class" not in decorators:
                defects.append(f"{class_name}:unguarded")
            actual = {
                node.name: node
                for node in repository_class.body
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
            }
            expected = {method.split("(", 1)[0] for method in repository["methods"]}
            if set(actual) != expected:
                defects.append(f"{class_name}:surface")
            observed_methods += len(actual)
            for method_name, method in actual.items():
                if any(
                    isinstance(statement, ast.Pass)
                    or isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and statement.value.value is Ellipsis
                    for statement in method.body
                ):
                    defects.append(f"{class_name}.{method_name}:stub")

    assert observed_classes == 53
    assert observed_methods == 202
    assert defects == []


@pytest.mark.parametrize(
    ("column", "tampered_value"),
    (
        ("confidence", Decimal("2")),
        ("urgency_score", Decimal("101")),
        ("expires_at", FIXED_TIME),
    ),
)
def test_action_candidate_mapper_rejects_tampered_physical_constraint_row(
    column: str,
    tampered_value: object,
) -> None:
    candidate = _action(
        status=ActionCandidateStatus.PROPOSED,
        decided=False,
        with_event=False,
    )
    row = portfolio._encode_portfolio_action_candidate(candidate.state)
    row[column] = tampered_value

    with pytest.raises(PersistenceError) as rejected:
        portfolio._decode_portfolio_action_candidate(row)
    assert rejected.value.code is PersistenceErrorCode.STORAGE_CORRUPTION


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("disposition_missing", "IDEMPOTENCY_OUTCOME_DISPOSITION_INVALID"),
        ("disposition_modified", "IDEMPOTENCY_OUTCOME_DISPOSITION_INVALID"),
        ("unknown_commit_removed", "IDEMPOTENCY_FAILURE_BOUNDARY_INVALID"),
    ),
)
def test_owner_render_rejects_idempotency_failure_boundary_mutation(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_code: str,
) -> None:
    matrix_path = generator.EXPECTED_MATRIX_PATHS["idempotency"]
    matrix = deepcopy(generator.load_yaml(generator.REPO_ROOT / matrix_path))
    if mutation == "disposition_missing":
        del matrix["outcome_shape"]["disposition"]
    elif mutation == "disposition_modified":
        matrix["outcome_shape"]["disposition"] = "caller-selected disposition"
    else:
        matrix["completion"]["never_confirm_as_failure"].remove("unknown commit")

    original_load = generator._load_yaml_at

    def load_with_mutation(root: Path, relative: Path) -> Any:
        if relative.as_posix() == matrix_path:
            return matrix
        return original_load(root, relative)

    monkeypatch.setattr(generator, "_load_yaml_at", load_with_mutation)
    with pytest.raises(generator.PersistenceBuildError) as caught:
        generator.render_outputs()
    assert caught.value.code == expected_code


def _unowned_article_version_rows() -> tuple[tuple[str, object], ...]:
    version = _article_version_graph()
    version_id = version.state.id
    seo_id = SeoMetadataVersionId(_uuid(508))
    return (
        (
            "article_disclosure_context_rows",
            ArticleDisclosureContext(
                article_version_id=version_id,
                affiliate_relationship=True,
                material_benefit_relationship=False,
                benefit_types=(),
                disclosure_policy_version="1.0.0",
                additional_disclosure_text=None,
                reviewed_by_principal_id=None,
                reviewed_at=None,
                created_at=AwareUtcDateTime(FIXED_TIME),
            ),
        ),
        (
            "article_methodology_binding_rows",
            ArticleMethodologyBinding(
                article_version_id=version_id,
                methodology_version_id=EditorialMethodologyVersionId(_uuid(502)),
                candidate_universe_artifact_id=ObjectArtifactId(_uuid(503)),
                candidate_universe_sha256=Sha256Digest("5" * 64),
                bound_at=AwareUtcDateTime(FIXED_TIME),
                bound_by_principal_id=PrincipalId(_uuid(504)),
            ),
        ),
        (
            "review_comment_rows",
            ReviewCommentState(
                id=ReviewCommentId(_uuid(505)),
                article_version_id=version_id,
                article_block_id=None,
                claim_id=None,
                thread_id=ThreadId(_uuid(506)),
                parent_comment_id=None,
                author_principal_id=PrincipalId(_uuid(507)),
                comment_text="owner boundary regression",
                status=ReviewCommentStatus.OPEN,
                resolved_by_principal_id=None,
                resolved_at=None,
                created_at=AwareUtcDateTime(FIXED_TIME),
            ),
        ),
        (
            "seo_metadata_version_rows",
            SeoMetadataVersionState(
                id=seo_id,
                article_version_id=version_id,
                semantic_version="1.0.0",
                metadata=SeoMetadataVersionMetadataJson(
                    FrozenJsonObject.from_mapping({"title": "owner boundary"})
                ),
                metadata_sha256=Sha256Digest("6" * 64),
                status=SeoMetadataVersionStatus.DRAFT,
                validated_at=None,
                approved_by_principal_id=None,
                approved_at=None,
                created_at=AwareUtcDateTime(FIXED_TIME),
            ),
        ),
        (
            "structured_data_manifest_rows",
            StructuredDataManifest(
                id=StructuredDataManifestId(_uuid(509)),
                article_version_id=version_id,
                seo_metadata_version_id=seo_id,
                generator_version="1.0.0",
                visible_content_sha256=Sha256Digest("7" * 64),
                jsonld_artifact_id=ObjectArtifactId(_uuid(510)),
                jsonld_sha256=Sha256Digest("8" * 64),
                enabled_types=("Article",),
                disabled_types=(),
                validation_status=StructuredDataManifestValidationStatus.PASS,
                validated_at=AwareUtcDateTime(FIXED_TIME),
                created_at=AwareUtcDateTime(FIXED_TIME),
            ),
        ),
    )


@pytest.mark.parametrize(("field_name", "unowned_row"), _unowned_article_version_rows())
def test_article_version_add_rejects_each_unowned_relation_before_dml(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    unowned_row: object,
) -> None:
    version = cast(
        Any,
        replace(
            cast(Any, _article_version_graph()),
            **{field_name: (unowned_row,)},
        ),
    )
    operations: list[str] = []

    def unexpected_operation(*_args: object, **_kwargs: object) -> None:
        operations.append("unexpected")
        raise AssertionError("owner-external relation reached a persistence seam")

    monkeypatch.setattr(editorial, "register_pending_events", unexpected_operation)
    monkeypatch.setattr(editorial, "_execute", unexpected_operation)
    monkeypatch.setattr(editorial, "stage_registered_events", unexpected_operation)
    session = Session()
    try:
        with pytest.raises(ValueError, match="INVALID_ARTICLE_VERSION"):
            editorial.SqlAlchemyArticleRepository(session).add_version(version)
    finally:
        session.close()
    assert operations == []


@pytest.mark.parametrize("repository_path", ("get", "add"))
def test_action_candidate_later_event_is_visible_to_commit_gate(
    repository_path: str,
) -> None:
    candidate = _action(
        status=ActionCandidateStatus.PROPOSED,
        decided=False,
        with_event=False,
    )
    if repository_path == "get":
        session = _ScriptedSession(
            _Result(row=portfolio._encode_portfolio_action_candidate(candidate.state))
        )
    else:
        session = _ScriptedSession(_Result())
    transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=make_context(suffix=f"action-candidate-{repository_path}"),
        timestamp=AwareUtcDateTime(FIXED_TIME),
        session=session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    bind_session_runtime(
        session,
        transaction=transaction,
        outbox=SqlAlchemyOutboxEventAppender(transaction),
    )
    try:
        repository = portfolio.SqlAlchemyActionCandidateRepository(session)
        if repository_path == "get":
            observed = repository.get(candidate.state.id)
            assert observed is not None
            candidate = observed
        else:
            assert repository.add(candidate).value == 0

        event_source = _action(
            status=ActionCandidateStatus.ACCEPTED,
            decided=True,
            with_event=True,
        )
        candidate._record_event(event_source.pending_events()[0])

        with pytest.raises(PersistenceError) as commit_gate:
            require_no_unstaged_pending_events(session)
        assert commit_gate.value.code is PersistenceErrorCode.STATE_CONFLICT
        assert transaction.rollback_only is True
    finally:
        clear_session_runtime(session)
        session.close()


def test_action_candidate_detached_decision_uses_one_registered_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _action(
        status=ActionCandidateStatus.PROPOSED,
        decided=False,
        with_event=False,
    )
    transition = _action(
        status=ActionCandidateStatus.ACCEPTED,
        decided=True,
        with_event=True,
    )
    session = _ScriptedSession(
        _Result(row=portfolio._encode_portfolio_action_candidate(current.state)),
        _Result(scalar=1),
    )
    transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=make_context(suffix="action-candidate-save"),
        timestamp=AwareUtcDateTime(FIXED_TIME),
        session=session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    bind_session_runtime(
        session,
        transaction=transaction,
        outbox=SqlAlchemyOutboxEventAppender(transaction),
    )
    monkeypatch.setattr(
        SqlAlchemyOutboxEventAppender,
        "append_many",
        lambda _self, _events: None,
    )
    try:
        persisted = portfolio.SqlAlchemyActionCandidateRepository(session).save(
            transition,
            expected_version=transition.state.lock_version,
        )
        assert persisted.value == 1
        assert transition.pending_events() == ()
        require_no_unstaged_pending_events(session)
        assert transaction.rollback_only is False
    finally:
        clear_session_runtime(session)
        session.close()


def test_repository_post_dml_returning_mismatch_poison_is_known_rollback() -> None:
    current = _provider(ProviderEndpointStatus.DRAFT)
    transition = ProviderEndpoint(
        replace(current.state, status=ProviderEndpointStatus.BLOCKED)
    )
    tampered_returning = ProviderEndpoint(
        replace(transition.state, provider_name="Tampered")
    )
    session = _DmlAwareScriptedSession(
        _Result(row=_provider_row(current)),
        _Result(row=_provider_row(tampered_returning)),
    )
    transaction = _SqlAlchemyTransaction(
        transaction_id=uuid7(),
        context=make_context(suffix="post-dml-returning-mismatch"),
        timestamp=AwareUtcDateTime(FIXED_TIME),
        session=session,
        execution_state=_ExecutionStateFactory().new_outer_state(),
    )
    event = make_event(suffix="post-dml-returning-mismatch")
    buffer = PendingEventBuffer[DomainEvent]((event,))
    buffer.acknowledge_events((event.event_id,))
    transaction.acknowledge(buffer)
    bind_session_runtime(
        session,
        transaction=transaction,
        outbox=SqlAlchemyOutboxEventAppender(transaction),
    )
    try:
        with pytest.raises(PersistenceError) as operation:
            catalog.SqlAlchemyProviderEndpointRepository(session).transition(
                current.state.id,
                transition,
                ProviderEndpointStatus.DRAFT,
            )
        assert operation.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert transaction.successful_dml_count == 1
        assert transaction.rollback_only is True
        assert transaction.acknowledged_buffers == []
        assert buffer.pending_events() == (event,)

        with pytest.raises(PersistenceError) as subsequent:
            _execute_one(transaction, text("SELECT 1"))
        assert subsequent.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
        assert len(session.statements) == 2

        commit_error, recorder, state = _commit_poisoned(transaction, session)
        assert commit_error.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
        assert state is TransactionState.ROLLED_BACK
        assert recorder.calls == [(transaction.transaction_id, transaction)]
    finally:
        clear_session_runtime(session)
        session.close()


def _idempotency_identity() -> tuple[IdempotencyIdentity, RequestHash]:
    return (
        IdempotencyIdentity(
            actor_fingerprint=ActorFingerprint("a" * 64),
            route_key=RouteKey("portfolio.action-candidate.audit"),
            idempotency_key=IdempotencyKey("st0308-independent-audit"),
        ),
        RequestHash("b" * 64),
    )


def test_complete_failure_rejects_unapproved_disposition_before_dml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, transaction = _bound_transaction(suffix="failure-disposition")
    identity, request_hash = _idempotency_identity()
    handle = _issue_claim_handle(
        record_id=UUID("00000000-0000-4000-8000-000000000701"),
        identity=identity,
        request_hash=request_hash,
        transaction_id=transaction.transaction_id,
    )
    execute_calls = 0

    def unexpected_execute(*_args: object, **_kwargs: object) -> None:
        nonlocal execute_calls
        execute_calls += 1
        raise AssertionError("unapproved failure disposition reached DML")

    monkeypatch.setattr(session, "execute", unexpected_execute)
    try:
        with pytest.raises(PersistenceError) as rejected:
            SqlAlchemyIdempotencyRepository(transaction).complete_failure(
                handle,
                IdempotencyOutcome(
                    response_status=422,
                    response_body=FrozenJsonObject.from_mapping(
                        {"error": "business-rule"}
                    ),
                ),
            )
        assert rejected.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert execute_calls == 0
        assert transaction.rollback_only is False
    finally:
        session.close()


@pytest.mark.parametrize(
    "sensitive_key",
    (
        "api_key",
        "access_key",
        "access_token",
        "affiliate_id",
        "client_secret",
        "authorization_header",
        "session_cookie",
        "private_key",
        "email_address",
    ),
)
def test_sanitized_audit_details_reject_sensitive_aliases_recursively(
    sensitive_key: str,
) -> None:
    details = FrozenJsonObject.from_mapping(
        {"nested": {sensitive_key: "credential-material"}}
    )
    with pytest.raises(ValueError, match="INVALID_SANITIZED_AUDIT_DETAILS"):
        SanitizedAuditDetails(details)


@pytest.mark.parametrize(
    "sensitive_key",
    (
        "application_id",
        "applicationId",
        "access_key",
        "accessKey",
        "affiliate_id",
        "affiliateId",
        "client_secret",
        "authorization_header",
    ),
)
def test_provider_non_secret_config_rejects_credential_aliases_recursively(
    sensitive_key: str,
) -> None:
    config = FrozenJsonObject.from_mapping(
        {"field_mapping": {sensitive_key: "credential-material"}}
    )
    with pytest.raises(ValueError, match="INVALID_PROVIDER_NON_SECRET_CONFIG"):
        ProviderEndpointNonSecretConfigJson(config)


@pytest.mark.parametrize(
    "config",
    (
        {"value": "abc123"},
        {"auth": "short-secret"},
        {"field_mapping": {"title": "abc123"}},
    ),
)
def test_provider_non_secret_config_has_no_arbitrary_json_escape_hatch(
    config: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_PROVIDER_NON_SECRET_CONFIG"):
        ProviderEndpointNonSecretConfigJson(FrozenJsonObject.from_mapping(config))


def test_every_direct_repository_execute_exception_path_poisons_transaction() -> None:
    repository_directory = (
        REPOSITORY_ROOT / "python/raos/adapters/persistence/sqlalchemy/repositories"
    )
    expected_counts = {
        "ai.py": 3,
        "catalog.py": 12,
        "editorial.py": 4,
        "evidence.py": 4,
        "iam.py": 4,
        "ops.py": 3,
        "policy.py": 3,
        "portfolio.py": 5,
    }
    observed_counts: dict[str, int] = {}
    unpoisoned: list[str] = []

    for path in sorted(repository_directory.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        execute_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ]
        observed_counts[path.name] = len(execute_calls)
        for execute_call in execute_calls:
            current: ast.AST = execute_call
            enclosing_try: ast.Try | None = None
            while current in parents:
                current = parents[current]
                if isinstance(current, ast.Try):
                    enclosing_try = current
                    break
            if enclosing_try is None:
                unpoisoned.append(f"{path.name}:{execute_call.lineno}:no-try")
                continue
            for handler in enclosing_try.handlers:
                has_poison = any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "fail_session_operation"
                    for statement in handler.body
                    for node in ast.walk(statement)
                )
                if not has_poison:
                    unpoisoned.append(
                        f"{path.name}:{execute_call.lineno}:handler-{handler.lineno}"
                    )

    assert observed_counts == expected_counts
    assert unpoisoned == []


def test_postgresql_duplicate_insert_catch_still_forces_known_rollback(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    site = _site(suffix="duplicate-poison", name="重複検査")
    try:
        with factory.begin(make_context(suffix="duplicate-seed")) as unit:
            unit.sites.add(site)
            unit.commit()

        with factory.begin(make_context(suffix="duplicate-catch")) as unit:
            with pytest.raises(PersistenceError) as duplicate:
                unit.sites.add(site)
            assert duplicate.value.code is PersistenceErrorCode.INTEGRITY_CONFLICT
            assert duplicate.value.__cause__ is None

            with pytest.raises(PersistenceError) as subsequent:
                unit.sites.get(site.state.id)
            assert (
                subsequent.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
            )

            with pytest.raises(PersistenceError) as commit:
                unit.commit()
            assert commit.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
            _assert_not_unknown(commit.value)

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT count(*) FROM portfolio.site WHERE id = %s",
                (site.state.id.value,),
            ).fetchone() == (1,)
    finally:
        engine.dispose()


def test_postgresql_route_approved_failure_replays_as_failure(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyIdempotentPortfolioUnitOfWorkFactory(provider)
    identity, request_hash = _idempotency_identity()
    approved_failure = IdempotencyOutcome(
        response_status=422,
        response_body=FrozenJsonObject.from_mapping({"error": "business-rule"}),
        disposition=(
            IdempotencyOutcomeDisposition.ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE
        ),
    )
    try:
        with factory.begin_idempotent(
            make_context(suffix="approved-failure-claim")
        ) as unit:
            decision = unit.idempotency.claim(
                IdempotencyClaim(
                    identity=identity,
                    request_hash=request_hash,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            assert type(decision) is ClaimGranted
            unit.idempotency.complete_failure(decision.handle, approved_failure)
            unit.commit()

        with factory.begin_idempotent(
            make_context(suffix="approved-failure-replay")
        ) as unit:
            replay = unit.idempotency.lookup(identity, request_hash)
            assert type(replay) is ReplayFailed
            assert replay.outcome.response_status == 422
            assert replay.outcome.response_body == approved_failure.response_body
            assert (
                replay.outcome.disposition
                is IdempotencyOutcomeDisposition.ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE
            )
            unit.commit()

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT status, response_status FROM ops.idempotency_record"
            ).fetchone() == ("FAILED", 422)
    finally:
        engine.dispose()


def test_postgresql_idempotency_text_insert_postcondition_failure_poison(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyIdempotentPortfolioUnitOfWorkFactory(provider)
    identity, request_hash = _idempotency_identity()

    def reject_returning_row(*_args: object, **_kwargs: object) -> None:
        raise PersistenceError(PersistenceErrorCode.STORAGE_CORRUPTION) from None

    monkeypatch.setattr(
        SqlAlchemyIdempotencyRepository,
        "_handle",
        reject_returning_row,
    )
    try:
        with factory.begin_idempotent(
            make_context(suffix="idempotency-text-dml-poison")
        ) as unit:
            with pytest.raises(PersistenceError) as operation:
                unit.idempotency.claim(
                    IdempotencyClaim(
                        identity=identity,
                        request_hash=request_hash,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    )
                )
            assert operation.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
            assert unit._transaction is not None
            assert unit._transaction.successful_dml_count == 1
            assert unit._transaction.rollback_only is True

            with pytest.raises(PersistenceError) as subsequent:
                unit.idempotency.lookup(identity, request_hash)
            assert (
                subsequent.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
            )

            with pytest.raises(PersistenceError) as commit:
                unit.commit()
            assert commit.value.code is PersistenceErrorCode.TRANSACTION_ROLLBACK_ONLY
            _assert_not_unknown(commit.value)

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT count(*) FROM ops.idempotency_record"
            ).fetchone() == (0,)
    finally:
        engine.dispose()


def _assert_outer_runtime_cleared(unit: _SqlAlchemyOuterUnitOfWork) -> None:
    assert unit._checkout is None
    assert unit._session is None
    assert unit._transaction is None
    assert unit._audit_appender is None
    assert unit._outbox_appender is None
    assert unit._idempotency_repository is None
    assert unit._repositories is None
    assert unit._guard is None
    assert unit._entered is False


def test_postgresql_every_terminal_state_clears_outer_runtime_references(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    try:
        committed = factory.begin(make_context(suffix="terminal-committed"))
        committed.__enter__()
        try:
            committed.commit()
            assert committed._state is TransactionState.COMMITTED
            _assert_outer_runtime_cleared(committed)
        finally:
            committed.__exit__(None, None, None)

        rolled_back = factory.begin(make_context(suffix="terminal-rolled-back"))
        rolled_back.__enter__()
        try:
            rolled_back.rollback()
            assert rolled_back._state is TransactionState.ROLLED_BACK
            _assert_outer_runtime_cleared(rolled_back)
        finally:
            rolled_back.__exit__(None, None, None)

        unknown = factory.begin(make_context(suffix="terminal-unknown"))
        unknown.__enter__()
        try:
            session = unknown._session
            assert session is not None

            def indeterminate_commit() -> None:
                raise DBAPIError(
                    "COMMIT",
                    None,
                    RuntimeError("indeterminate-driver-return"),
                    connection_invalidated=True,
                )

            monkeypatch.setattr(session, "commit", indeterminate_commit)
            with pytest.raises(PersistenceError) as commit:
                unknown.commit()
            assert commit.value.code is PersistenceErrorCode.UNKNOWN_COMMIT
            assert unknown._state is TransactionState.UNKNOWN
            _assert_outer_runtime_cleared(unknown)
        finally:
            unknown.__exit__(None, None, None)
    finally:
        engine.dispose()


def test_postgresql_noninvalidated_commit_failure_observer_fault_is_known_rollback(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    unit = factory.begin(make_context(suffix="known-commit-failure-observer"))
    unit.__enter__()
    transaction = unit._transaction
    session = unit._session
    assert transaction is not None
    assert session is not None

    def known_commit_failure() -> None:
        raise DBAPIError(
            "COMMIT",
            None,
            RuntimeError("known-driver-failure"),
            connection_invalidated=False,
        )

    def fail_observer() -> None:
        raise RuntimeError("post-driver-observer-failure")

    monkeypatch.setattr(session, "commit", known_commit_failure)
    monkeypatch.setattr(
        _ExecutionState,
        "observe_known_driver_return",
        fail_observer,
    )
    try:
        with pytest.raises(PersistenceError) as commit:
            unit.commit()
        assert commit.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        _assert_not_unknown(commit.value)
        assert commit.value.__cause__ is None
        assert unit._state is TransactionState.ROLLED_BACK
        assert transaction.active is False
        assert transaction.transaction_id not in cast(Any, factory)._registry
        _assert_outer_runtime_cleared(unit)
    finally:
        unit.__exit__(None, None, None)
        engine.dispose()


def test_postgresql_enter_failure_unregister_fault_still_clears_all_runtime(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    registered_ids: list[UUID] = []
    original_register = type(factory)._register

    def record_register(
        self: object,
        transaction_id: UUID,
        registration: object,
    ) -> None:
        original_register(cast(Any, self), transaction_id, cast(Any, registration))
        registered_ids.append(transaction_id)

    def fail_housekeeping(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("enter-housekeeping-failure")

    monkeypatch.setattr(type(factory), "_register", record_register)
    monkeypatch.setattr(type(factory), "_unregister", fail_housekeeping)
    monkeypatch.setattr(cast(Any, sqlalchemy_uow).event, "listen", fail_housekeeping)
    unit = factory.begin(make_context(suffix="enter-cleanup"))
    try:
        with pytest.raises(PersistenceError) as enter:
            unit.__enter__()
        assert enter.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert enter.value.__cause__ is None
        assert len(registered_ids) == 1
        assert registered_ids[0] not in cast(Any, factory)._registry
        assert unit._state is TransactionState.CLOSED
        _assert_outer_runtime_cleared(unit)
    finally:
        unit.__exit__(None, None, None)
        engine.dispose()


@pytest.mark.parametrize(
    "failure_point",
    ("session_rollback", "restore_acknowledged", "unregister", "close"),
)
def test_postgresql_known_rollback_housekeeping_failure_stays_known_and_clears(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    failure_point: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    unit = factory.begin(make_context(suffix=f"rollback-{failure_point}"))
    unit.__enter__()
    transaction = unit._transaction
    session = unit._session
    assert transaction is not None
    assert session is not None

    def fail_housekeeping(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("known-rollback-housekeeping-failure")

    if failure_point == "session_rollback":
        monkeypatch.setattr(session, "rollback", fail_housekeeping)
    elif failure_point == "restore_acknowledged":
        event = make_event(suffix="rollback-restore")
        buffer = PendingEventBuffer[DomainEvent]((event,))
        buffer.acknowledge_events((event.event_id,))
        transaction.acknowledge(buffer)
        monkeypatch.setattr(
            PendingEventBuffer,
            "_restore_acknowledged",
            fail_housekeeping,
        )
    elif failure_point == "unregister":
        monkeypatch.setattr(type(factory), "_unregister", fail_housekeeping)
    else:
        monkeypatch.setattr(SqlAlchemyEngineProvider, "_close", fail_housekeeping)

    try:
        with pytest.raises(PersistenceError) as rollback:
            unit.rollback()
        assert rollback.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        _assert_not_unknown(rollback.value)
        assert rollback.value.__cause__ is None
        assert unit._state is TransactionState.ROLLED_BACK
        assert transaction.active is False
        assert transaction.transaction_id not in cast(Any, factory)._registry
        _assert_outer_runtime_cleared(unit)
    finally:
        unit.__exit__(None, None, None)
        engine.dispose()


@pytest.mark.parametrize(
    "failure_point",
    ("finish_acknowledged", "unregister", "invalidate_close"),
)
def test_postgresql_unknown_commit_housekeeping_failure_preserves_unknown_and_clears(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    failure_point: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    unit = factory.begin(make_context(suffix=f"unknown-{failure_point}"))
    unit.__enter__()
    transaction = unit._transaction
    session = unit._session
    assert transaction is not None
    assert session is not None

    def indeterminate_commit() -> None:
        raise DBAPIError(
            "COMMIT",
            None,
            RuntimeError("indeterminate-driver-return"),
            connection_invalidated=True,
        )

    def fail_housekeeping(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("unknown-commit-housekeeping-failure")

    monkeypatch.setattr(session, "commit", indeterminate_commit)
    if failure_point == "finish_acknowledged":
        event = make_event(suffix="unknown-finish")
        buffer = PendingEventBuffer[DomainEvent]((event,))
        buffer.acknowledge_events((event.event_id,))
        transaction.acknowledge(buffer)
        monkeypatch.setattr(
            PendingEventBuffer,
            "_finish_acknowledged",
            fail_housekeeping,
        )
    elif failure_point == "unregister":
        monkeypatch.setattr(type(factory), "_unregister", fail_housekeeping)
    else:
        monkeypatch.setattr(
            SqlAlchemyEngineProvider,
            "_invalidate_and_close",
            fail_housekeeping,
        )

    try:
        with pytest.raises(PersistenceError) as commit:
            unit.commit()
        assert commit.value.code is PersistenceErrorCode.UNKNOWN_COMMIT
        assert commit.value.__cause__ is None
        assert unit._state is TransactionState.UNKNOWN
        assert transaction.active is False
        assert transaction.transaction_id not in cast(Any, factory)._registry
        _assert_outer_runtime_cleared(unit)
    finally:
        unit.__exit__(None, None, None)
        engine.dispose()


@pytest.mark.parametrize(
    "failure_point",
    ("observe", "finish_acknowledged", "unregister", "close"),
)
def test_postgresql_post_driver_housekeeping_failure_stays_known_committed(
    monkeypatch: pytest.MonkeyPatch,
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
    failure_point: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    unit = factory.begin(make_context(suffix=f"post-driver-{failure_point}"))
    unit.__enter__()
    transaction = unit._transaction
    session = unit._session
    assert transaction is not None
    assert session is not None
    rollback_calls = 0
    original_rollback = session.rollback

    def observed_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        original_rollback()

    monkeypatch.setattr(session, "rollback", observed_rollback)

    def fail_housekeeping(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("post-driver-housekeeping-failure")

    if failure_point == "observe":
        monkeypatch.setattr(
            _ExecutionState,
            "observe_known_driver_return",
            fail_housekeeping,
        )
    elif failure_point == "finish_acknowledged":
        event = make_event(suffix="post-driver-finish")
        buffer = PendingEventBuffer[DomainEvent]((event,))
        buffer.acknowledge_events((event.event_id,))
        transaction.acknowledge(buffer)
        monkeypatch.setattr(
            PendingEventBuffer,
            "_finish_acknowledged",
            fail_housekeeping,
        )
    elif failure_point == "unregister":
        monkeypatch.setattr(type(factory), "_unregister", fail_housekeeping)
    else:
        monkeypatch.setattr(SqlAlchemyEngineProvider, "_close", fail_housekeeping)

    try:
        with pytest.raises(PersistenceError) as commit:
            unit.commit()
        assert commit.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        _assert_not_unknown(commit.value)
        assert unit._state is TransactionState.COMMITTED
        assert transaction.active is False
        assert transaction.acknowledged_buffers == []
        assert rollback_calls == 0
        _assert_outer_runtime_cleared(unit)
    finally:
        unit.__exit__(None, None, None)
        engine.dispose()


def test_postgresql_action_candidate_proposed_to_accepted_stages_event(
    postgresql_cluster: PostgreSQLCluster,
    empty_database: str,
) -> None:
    _upgrade(postgresql_cluster, empty_database)
    engine = _api_engine(postgresql_cluster, empty_database)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)
    factory = SqlAlchemyPortfolioUnitOfWorkFactory(provider)
    site = _site(suffix="action-site", name="Action Candidate Site")
    proposed_source = _action(
        status=ActionCandidateStatus.PROPOSED,
        decided=False,
        with_event=False,
    )
    proposed = ActionCandidate(replace(proposed_source.state, site_id=site.state.id))
    accepted_source = _action(
        status=ActionCandidateStatus.ACCEPTED,
        decided=True,
        with_event=True,
    )
    accepted = ActionCandidate(
        replace(
            accepted_source.state,
            site_id=site.state.id,
            decided_by_principal_id=_principal().state.id,
        )
    )
    accepted._record_event(accepted_source.pending_events()[0])
    try:
        _seed_principal(provider)
        with factory.begin(make_context(suffix="action-proposed")) as unit:
            unit.sites.add(site)
            assert unit.action_candidates.add(proposed).value == 0
            unit.commit()

        with factory.begin(make_context(suffix="action-accepted")) as unit:
            assert (
                unit.action_candidates.save(accepted, accepted.state.lock_version).value
                == 1
            )
            assert accepted.pending_events() == ()
            unit.commit()

        with postgresql_cluster.connect(empty_database) as connection:
            assert connection.execute(
                "SELECT status, lock_version FROM portfolio.action_candidate "
                "WHERE id = %s",
                (accepted.state.id.value,),
            ).fetchone() == ("ACCEPTED", 1)
            assert connection.execute(
                "SELECT event_type, aggregate_id, aggregate_version "
                "FROM ops.outbox_event"
            ).fetchone() == (
                "jp.raos.portfolio.action_candidate_decided.v1",
                accepted.state.id.value,
                1,
            )
    finally:
        engine.dispose()
