"""Static trust-boundary and dangerous-surface assertions for ST-0403."""

from __future__ import annotations

import ast
from pathlib import Path
import re

from conftest import REPOSITORY_ROOT


OWNED_SOURCE = (
    Path("python/raos/domain/iam/authorization.py"),
    Path("python/raos/ports/authorization.py"),
    Path("python/raos/application/iam/authorization.py"),
    Path("python/raos/adapters/development_authorization.py"),
)


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


def test_dependencies_point_inward_and_exclude_framework_database_provider_types() -> (
    None
):
    domain_imports = _imports(OWNED_SOURCE[0])
    port_imports = _imports(OWNED_SOURCE[1])
    application_imports = _imports(OWNED_SOURCE[2])
    adapter_imports = _imports(OWNED_SOURCE[3])

    assert {name for name in domain_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authentication"
    }
    assert {name for name in port_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authorization"
    }
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.application.iam.authentication",
        "raos.domain.iam.authentication",
        "raos.domain.iam.authorization",
        "raos.ports.authorization",
    }
    assert {name for name in adapter_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.iam.authorization",
    }

    forbidden_roots = {
        "alembic",
        "boto3",
        "fastapi",
        "httpx",
        "openai",
        "psycopg",
        "requests",
        "sqlalchemy",
        "starlette",
    }
    all_imports = set().union(
        domain_imports, port_imports, application_imports, adapter_imports
    )
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }


def test_adapter_has_no_file_network_process_env_sdk_or_logging_surface() -> None:
    tree = _tree(OWNED_SOURCE[3])
    identifiers = {
        node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    imported = _imports(OWNED_SOURCE[3])

    assert identifiers.isdisjoint(
        {
            "environ",
            "getenv",
            "open",
            "password",
            "secret",
            "socket",
            "subprocess",
        }
    )
    assert attributes.isdisjoint(
        {
            "connect",
            "getenv",
            "read_bytes",
            "read_text",
            "request",
            "urlopen",
            "write_bytes",
            "write_text",
        }
    )
    assert not {
        name
        for name in imported
        if name.partition(".")[0]
        in {
            "logging",
            "os",
            "pathlib",
            "requests",
            "socket",
            "subprocess",
            "urllib",
        }
    }


def test_no_database_workload_role_migration_http_or_live_surface_exists() -> None:
    workload_role = re.compile(r"\Araos_[a-z0-9_]+\Z")
    forbidden_definitions = {
        "app",
        "cookie",
        "decorator",
        "endpoint",
        "handler",
        "header",
        "http",
        "middleware",
        "migrate",
        "migration",
        "route",
        "router",
        "service_entrypoint",
    }
    for path in OWNED_SOURCE:
        tree = _tree(path)
        strings = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert not {value for value in strings if workload_role.fullmatch(value)}
        definitions = {
            node.name.lower()
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert definitions.isdisjoint(forbidden_definitions)


def test_public_application_surface_has_only_server_derived_admin_user_entrypoint() -> (
    None
):
    tree = _tree(OWNED_SOURCE[2])
    guard_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AuthorizationGuard"
    )
    public_methods = {
        node.name
        for node in guard_class.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert public_methods == {"require_admin_user"}
    entrypoint = next(
        node
        for node in guard_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_admin_user"
    )
    parameters = {
        argument.arg for argument in entrypoint.args.args + entrypoint.args.kwonlyargs
    }
    assert parameters == {
        "self",
        "session_id",
        "now",
        "action",
        "target",
        "correlation_id",
    }
    assert parameters.isdisjoint({"principal", "role", "permission_scope"})


def test_ui_hiding_and_database_roles_are_not_treated_as_authorization() -> None:
    combined = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in OWNED_SOURCE
    ).lower()
    assert "ui_hiding" not in combined
    assert "database_role" not in combined
    assert "postgres" not in combined
    assert "require_admin_user" in combined
