"""Disabled HTTP, metadata-only enforcement, and service-boundary tests."""

from __future__ import annotations

from pathlib import Path
import pickle
from typing import cast

import pytest

from .support import NOW, authentication_service, session
from raos.adapters.disabled_admin_authorization_http import (
    DisabledAdminAuthorizationHttpAdapter,
)
from raos.adapters.disabled_service_authorization import (
    DisabledServicePrincipalAuthorizationAdapter,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.application.iam.authorization import (
    AuthorizationEnforcementDependency,
    AuthorizationRequirement,
    DurableAuthorizationService,
    authorization_requirement,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import (
    AuthorizationFailure,
    OperationId,
    ServicePrincipalAuthorizationStatus,
)
from raos.adapters.recorded_authorization import (
    RecordedSqliteAuthorizationRepository,
)
from .test_durable_authorization import (
    ENTITLEMENT_REVISION,
    POLICY_REVISION,
    _command,
    _entitlements,
    _private,
    _repository,
    _rule,
    _service,
)


def _document(*, action: str = "EVALUATE") -> dict[str, object]:
    if action == "RECOVER":
        body: dict[str, object] = {
            "action": "RECOVER",
            "session_id": session().session_id.reveal(),
            "command_id": "RECORDED:ST0403:COMMAND:HTTP",
        }
    else:
        body = {
            "action": "EVALUATE",
            "session_id": session().session_id.reveal(),
            "command_id": "RECORDED:ST0403:COMMAND:HTTP",
            "operation_id": "ED-011",
            "correlation_id": "RECORDED:ST0403:CORRELATION:HTTP",
            "expected_policy_revision": POLICY_REVISION.value,
            "expected_entitlement_revision": ENTITLEMENT_REVISION.value,
            "resource_kind": "ARTICLE_VERSION",
            "site_id": "11111111-1111-4111-8111-111111111111",
            "resource_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "resource_state": "DRAFT",
            "step_up_command_id": None,
            "step_up_grant_id": None,
            "independent_actor_evidence_id": None,
        }
    return {
        "method": "POST",
        "target": "/__recorded__/st-0403/admin-authorization",
        "origin": "http://127.0.0.1:18403",
        "content_type": "application/json",
        "headers": {},
        "body": body,
    }


def _adapter(
    root: Path,
) -> tuple[
    DisabledAdminAuthorizationHttpAdapter,
    RecordedSqliteAuthorizationRepository,
]:
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    return (
        DisabledAdminAuthorizationHttpAdapter(
            environment=RuntimeEnvironment.ENV_DEV,
            service=_service(repository),
        ),
        repository,
    )


def test_external_projection_is_unconditional_rfc9457_503(tmp_path: Path) -> None:
    adapter, repository = _adapter(_private(tmp_path))
    response = adapter.dispatch_external(
        {"Authorization": "Bearer SHOULD_NOT_BE_PARSED", "Cookie": "ignored"}
    ).response
    assert response.status == 503
    assert response.body["code"] == "AUTHORIZATION_ROUTE_DISABLED"
    assert response.body["instance"] == "urn:raos:recorded:st-0403"
    assert {name.lower() for name, _value in response.headers} == {
        "content-type",
        "cache-control",
        "pragma",
        "x-content-type-options",
    }
    assert repository.audit_snapshot() == ()


def test_loopback_evaluate_and_recovery_expose_no_session_or_grant_handle(
    tmp_path: Path,
) -> None:
    adapter, repository = _adapter(_private(tmp_path))
    dispatch = adapter.dispatch_recorded(_document(), now=NOW)
    assert dispatch.response.status == 200
    assert dispatch.result is not None
    assert dispatch.response.body["outcome"] == "ALLOWED"
    serialized_response = repr(dict(dispatch.response.body))
    assert session().session_id.reveal() not in serialized_response
    assert "grant_id" not in serialized_response
    recovered = adapter.dispatch_recorded(_document(action="RECOVER"), now=NOW)
    assert recovered.response.status == 200
    assert recovered.result == dispatch.result
    assert len(repository.audit_snapshot()) == 1
    with pytest.raises(TypeError, match="not serializable"):
        pickle.dumps(dispatch)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("origin", "http://localhost:18403"),
        ("origin", "https://127.0.0.1:18403"),
        ("target", "/admin/authorization"),
        ("method", "GET"),
        ("content_type", "application/x-www-form-urlencoded"),
        ("headers", {"Authorization": "Bearer recorded"}),
        ("headers", {"Cookie": "recorded=value"}),
    ),
)
def test_recorded_http_rejects_origin_method_target_content_and_auth_delivery(
    tmp_path: Path, field: str, value: object
) -> None:
    adapter, repository = _adapter(_private(tmp_path))
    document = _document()
    document[field] = value
    response = adapter.dispatch_recorded(document, now=NOW).response
    assert response.status == 403
    assert response.body["code"] == "AUTHORIZATION_DENIED"
    assert repository.audit_snapshot() == ()


def test_recorded_http_denial_is_sanitized_rfc9457_and_durable(
    tmp_path: Path,
) -> None:
    adapter, repository = _adapter(_private(tmp_path))
    document = _document()
    body = document["body"]
    assert type(body) is dict
    body["operation_id"] = "PUBADM-005"
    body["resource_state"] = "HUMAN_REVIEW"
    response = adapter.dispatch_recorded(document, now=NOW).response
    assert response.status == 403
    assert response.body["type"] == "urn:raos:problem:st-0403:authorization-denied"
    assert response.body["code"] == "AUTHORIZATION_DENIED"
    assert "PUBADM" not in repr(dict(response.body))
    assert len(repository.audit_snapshot()) == 1


def test_metadata_decorator_and_dependency_never_execute_business_handler(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    service = _service(repository)
    calls = 0

    @authorization_requirement("ED-011")
    def business_handler() -> None:
        nonlocal calls
        calls += 1

    requirement = cast(
        AuthorizationRequirement,
        getattr(business_handler, "__raos_authorization_requirement__"),
    )
    assert type(requirement) is AuthorizationRequirement
    grant = AuthorizationEnforcementDependency(service=service).enforce(
        requirement=requirement,
        session_id=session().session_id,
        command=_command(label="DECORATOR"),
    )
    assert grant.action.value == "edit_article_draft"
    assert calls == 0
    with pytest.raises(AuthorizationFailure):
        AuthorizationEnforcementDependency(service=service).enforce(
            requirement=AuthorizationRequirement(
                operation_id=OperationId("PUBADM-004")
            ),
            session_id=session().session_id,
            command=_command(label="WRONG-DECORATOR"),
        )
    assert calls == 0


def test_service_principal_port_is_closed_and_has_no_workload_role_grant() -> None:
    adapter = DisabledServicePrincipalAuthorizationAdapter()
    assert (
        adapter.status()
        is ServicePrincipalAuthorizationStatus.DISABLED_MAPPING_UNRESOLVED
    )
    with pytest.raises(AuthorizationFailure):
        adapter.require_internal_service("raos-api")
    assert "raos_api_rw" not in repr(adapter)


@pytest.mark.parametrize(
    "environment",
    (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ),
)
def test_http_recorded_harness_rejects_external_environments(
    tmp_path: Path, environment: RuntimeEnvironment
) -> None:
    root = _private(tmp_path)
    repository = _repository(root, rule=_rule(), entitlements=_entitlements())
    service = DurableAuthorizationService(
        session_service=authentication_service(session()),
        repository=repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    with pytest.raises(AuthorizationFailure):
        DisabledAdminAuthorizationHttpAdapter(
            environment=environment,
            service=service,
        )
