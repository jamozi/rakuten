"""Static trust-boundary assertions for the ST-0401 implementation."""

from __future__ import annotations

import ast
from pathlib import Path
import pickle

import pytest

from .support import REPOSITORY_ROOT
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationState,
)


OWNED_SOURCE = (
    Path("python/raos/domain/iam/authentication.py"),
    Path("python/raos/ports/oidc.py"),
    Path("python/raos/application/iam/authentication.py"),
    Path("python/raos/adapters/development_oidc.py"),
)

V2_ADAPTER_SOURCE = (
    Path("python/raos/adapters/recorded_authentication.py"),
    Path("python/raos/adapters/disabled_admin_auth_http.py"),
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_source_dependencies_point_inward_and_contain_no_delivery_or_sdk_types() -> (
    None
):
    domain_imports = _imports(OWNED_SOURCE[0])
    port_imports = _imports(OWNED_SOURCE[1])
    application_imports = _imports(OWNED_SOURCE[2])
    adapter_imports = _imports(OWNED_SOURCE[3])

    assert not {name for name in domain_imports if name.startswith("raos.")}
    assert {name for name in port_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authentication"
    }
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authentication",
        "raos.ports.oidc",
    }
    assert {name for name in adapter_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.iam.authentication",
    }

    all_imports = set().union(
        domain_imports,
        port_imports,
        application_imports,
        adapter_imports,
    )
    forbidden_roots = {
        "fastapi",
        "httpx",
        "openai",
        "requests",
        "sqlalchemy",
        "starlette",
    }
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }


def test_adapter_has_no_process_environment_file_network_or_password_surface() -> None:
    adapter_path = REPOSITORY_ROOT / OWNED_SOURCE[3]
    tree = ast.parse(adapter_path.read_text(encoding="utf-8"))
    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert identifiers.isdisjoint({"open", "environ", "getenv"})
    assert attributes.isdisjoint({"connect", "request", "urlopen"})
    assert "password" not in identifiers
    assert "password" not in attributes


def test_v2_adapters_keep_framework_provider_and_delivery_dependencies_absent() -> None:
    imports = set().union(*(_imports(path) for path in V2_ADAPTER_SOURCE))
    forbidden_roots = {
        "boto3",
        "fastapi",
        "httpx",
        "requests",
        "sqlalchemy",
        "starlette",
    }
    assert not {name for name in imports if name.partition(".")[0] in forbidden_roots}
    assert "socket" not in imports

    http_source = (REPOSITORY_ROOT / V2_ADAPTER_SOURCE[1]).read_text(encoding="utf-8")
    for forbidden in ("Set-Cookie", "Bearer ", "add_route", "include_router"):
        assert forbidden not in http_source
    assert "dispatch_external" in http_source
    assert "AUTH_TRANSPORT_DISABLED" in http_source


def test_durable_adapter_owns_explicit_transactions_and_unknown_commit_recovery() -> (
    None
):
    source = (REPOSITORY_ROOT / V2_ADAPTER_SOURCE[0]).read_text(encoding="utf-8")
    assert 'connection.execute("BEGIN IMMEDIATE")' in source
    assert "connection.commit()" in source
    assert "connection.rollback()" in source
    assert "STORAGE_COMMIT_UNKNOWN" in source
    assert "recover_session_rotation" in source
    assert "requests" not in source
    assert "urlopen" not in source


def test_sensitive_values_reject_generic_pickle_serialization() -> None:
    value = AuthorizationState.from_bytes(bytes(range(32)))
    with pytest.raises(TypeError, match="serialization is not supported"):
        pickle.dumps(value)


def test_typed_failure_is_immutable_and_contains_only_its_stable_code() -> None:
    failure = AuthenticationFailure(AuthenticationFailureCode.CODE_UNKNOWN)
    with pytest.raises(AttributeError, match="immutable"):
        failure.args = ("replacement",)
    assert str(failure) == AuthenticationFailureCode.CODE_UNKNOWN.value
    assert repr(failure) == (
        "AuthenticationFailure(code="
        "<AuthenticationFailureCode.CODE_UNKNOWN: 'CODE_UNKNOWN'>)"
    )
