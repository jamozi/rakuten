"""Static trust-boundary and dangerous-surface assertions for ST-0403."""

from __future__ import annotations

import ast
from pathlib import Path
import re

from .support import REPOSITORY_ROOT


DOMAIN = Path("python/raos/domain/iam/authorization.py")
PORTS = Path("python/raos/ports/authorization.py")
APPLICATION = Path("python/raos/application/iam/authorization.py")
ADAPTERS = (
    Path("python/raos/adapters/development_authorization.py"),
    Path("python/raos/adapters/recorded_authorization.py"),
    Path("python/raos/adapters/generated_st0403_authorization_registry.py"),
    Path("python/raos/adapters/disabled_admin_authorization_http.py"),
    Path("python/raos/adapters/disabled_service_authorization.py"),
)
OWNED_SOURCE = (DOMAIN, PORTS, APPLICATION, *ADAPTERS)


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_dependencies_point_inward_and_exclude_framework_provider_network_sdks() -> (
    None
):
    domain_imports = {value for value in _imports(DOMAIN) if value.startswith("raos.")}
    port_imports = {value for value in _imports(PORTS) if value.startswith("raos.")}
    application_imports = {
        value for value in _imports(APPLICATION) if value.startswith("raos.")
    }
    assert domain_imports == {
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
    }
    assert port_imports == {
        "raos.domain.iam.authentication",
        "raos.domain.iam.authorization",
        "raos.domain.iam.step_up",
    }
    assert application_imports == {
        "raos.application.iam.authentication",
        "raos.domain.iam.authentication",
        "raos.domain.iam.authorization",
        "raos.domain.iam.step_up",
        "raos.ports.authorization",
    }
    forbidden_roots = {
        "alembic",
        "boto3",
        "fastapi",
        "httpx",
        "openai",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "starlette",
        "subprocess",
    }
    all_imports = set().union(*(_imports(path) for path in OWNED_SOURCE))
    assert not {
        value for value in all_imports if value.partition(".")[0] in forbidden_roots
    }


def test_no_framework_route_cookie_bearer_or_active_service_entrypoint() -> None:
    definitions: set[str] = set()
    for path in OWNED_SOURCE:
        definitions.update(
            node.name.lower()
            for node in ast.walk(_tree(path))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        )
    assert definitions.isdisjoint(
        {
            "app",
            "endpoint",
            "middleware",
            "route",
            "router",
            "service_entrypoint",
        }
    )
    http_source = (
        REPOSITORY_ROOT / "python/raos/adapters/disabled_admin_authorization_http.py"
    ).read_text(encoding="utf-8")
    assert 'headers"] != {}' in http_source
    assert "dispatch_external" in http_source
    assert "del document" in http_source
    assert "route_registered" in http_source
    assert "Set-Cookie" not in http_source
    assert "Bearer " not in http_source


def test_sqlite_adapter_has_fixed_sql_no_caller_sql_or_raw_identity_columns() -> None:
    path = Path("python/raos/adapters/recorded_authorization.py")
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            raise AssertionError(
                "recorded authorization adapter contains dynamic SQL/text"
            )
    source = (REPOSITORY_ROOT / path).read_text(encoding="utf-8").lower()
    assert "principal_fingerprint" in source
    assert "issuer_fingerprint" not in source
    assert "subject_fingerprint" not in source
    assert "password" not in source
    assert "credential" not in source
    assert "token" not in source
    assert "pragma trusted_schema = off" in source
    assert "begin immediate" in source
    assert "sha-256 chain" in source


def test_decorator_is_metadata_only_and_dependency_does_not_accept_handler() -> None:
    tree = _tree(APPLICATION)
    decorator = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "authorization_requirement"
    )
    calls = {
        node.func.id
        for node in ast.walk(decorator)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls <= {
        "AuthorizationRequirement",
        "OperationId",
        "TypeError",
        "callable",
        "hasattr",
        "setattr",
    }
    dependency = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "AuthorizationEnforcementDependency"
    )
    enforce = next(
        node
        for node in dependency.body
        if isinstance(node, ast.FunctionDef) and node.name == "enforce"
    )
    parameters = {
        argument.arg for argument in enforce.args.args + enforce.args.kwonlyargs
    }
    assert parameters == {"self", "requirement", "session_id", "command"}
    assert parameters.isdisjoint({"handler", "callback", "business_action"})


def test_service_principal_adapter_contains_no_database_workload_role_mapping() -> None:
    adapter = (
        REPOSITORY_ROOT / "python/raos/adapters/disabled_service_authorization.py"
    ).read_text(encoding="utf-8")
    workload_role = re.compile(r"\braos_[a-z0-9_]+\b")
    assert workload_role.findall(adapter) == []
    assert "DISABLED_MAPPING_UNRESOLVED" in adapter
    assert "deny_authorization" in adapter


def test_ui_and_database_roles_remain_defense_in_depth_not_decision_inputs() -> None:
    combined = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in OWNED_SOURCE
    ).lower()
    assert "ui_hiding" not in combined
    assert "postgres role" not in combined
    service = next(
        node
        for node in _tree(APPLICATION).body
        if isinstance(node, ast.ClassDef) and node.name == "DurableAuthorizationService"
    )
    evaluate = next(
        node
        for node in service.body
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_admin"
    )
    parameters = {
        argument.arg for argument in evaluate.args.args + evaluate.args.kwonlyargs
    }
    assert parameters == {"self", "session_id", "command"}
    assert parameters.isdisjoint(
        {"principal", "role", "permission_scope", "database_role", "claims"}
    )
