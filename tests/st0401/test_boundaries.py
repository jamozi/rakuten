"""Static trust-boundary assertions for the ST-0401 implementation."""

from __future__ import annotations

import ast
from pathlib import Path
import pickle

import pytest

from conftest import REPOSITORY_ROOT
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
