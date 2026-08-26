"""Architecture and dangerous-surface assertions for the ST-0407 safe slice."""

from __future__ import annotations

import ast
from pathlib import Path

from .support import REPOSITORY_ROOT


DOMAIN = Path("python/raos/domain/iam/workload_credentials.py")
PORTS = Path("python/raos/ports/workload_credentials.py")
APPLICATION = Path("python/raos/application/iam/workload_credentials.py")
ADAPTER = Path("python/raos/adapters/development_workload_credentials.py")
OWNED_SOURCE = (DOMAIN, PORTS, APPLICATION, ADAPTER)


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


def _calls(path: Path) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def test_dependencies_point_inward_and_domain_is_stdlib_only() -> None:
    domain_imports = _imports(DOMAIN)
    ports_imports = _imports(PORTS)
    application_imports = _imports(APPLICATION)
    adapter_imports = _imports(ADAPTER)

    assert not {name for name in domain_imports if name.startswith("raos.")}
    assert {name for name in ports_imports if name.startswith("raos.")} == {
        "raos.domain.iam.workload_credentials"
    }
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.iam.workload_credentials",
        "raos.ports.workload_credentials",
    }
    assert {name for name in adapter_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.iam.workload_credentials",
    }


def test_no_provider_delivery_database_or_ambient_credential_imports() -> None:
    all_imports = set().union(*(_imports(path) for path in OWNED_SOURCE))
    forbidden_roots = {
        "boto3",
        "botocore",
        "fastapi",
        "google",
        "httpx",
        "jwt",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "starlette",
        "subprocess",
        "threading",
        "urllib",
    }
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }


def test_no_file_network_environment_process_or_background_execution_surface() -> None:
    forbidden_calls = {
        "Thread",
        "create_task",
        "getenv",
        "open",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "sleep",
        "urlopen",
    }
    assert (
        set()
        .union(*(_calls(path) for path in OWNED_SOURCE))
        .isdisjoint(forbidden_calls)
    )


def test_secret_reference_is_used_only_as_alias_membership_configuration() -> None:
    application_tree = _tree(APPLICATION)
    implementation_identifiers = {
        node.id
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Name)
    }
    implementation_attributes = {
        node.attr
        for path in OWNED_SOURCE
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Attribute)
    }
    assert "SecretReference" not in implementation_identifiers
    assert implementation_identifiers.isdisjoint(
        {"getattr", "hasattr", "inspect", "vars"}
    )
    assert implementation_attributes.isdisjoint(
        {
            "_SecretReference__logical_reference",
            "__dict__",
            "model_dump",
            "model_dump_json",
            "read_bytes",
            "read_text",
            "values",
        }
    )

    references = [
        node
        for node in ast.walk(application_tree)
        if isinstance(node, ast.Attribute) and node.attr == "secret_references"
    ]
    assert len(references) == 1
    reference = references[0]
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(application_tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    membership = parents[reference]
    assert isinstance(membership, ast.Compare)
    assert len(membership.ops) == 1
    assert isinstance(membership.ops[0], ast.In)
    assert membership.comparators == [reference]


def test_lease_public_surface_contains_only_safe_metadata_state_and_close() -> None:
    lease_class = next(
        node
        for node in _tree(DOMAIN).body
        if isinstance(node, ast.ClassDef) and node.name == "CredentialLease"
    )
    public_definitions = {
        node.name
        for node in lease_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_definitions == {"close", "closed", "metadata", "state"}
    assert public_definitions.isdisjoint(
        {"bytes", "material", "password", "secret", "serialize", "token", "value"}
    )


def test_application_has_no_retry_fallback_refresh_or_background_state_machine() -> (
    None
):
    prohibited = {"background", "fallback", "refresh", "retry", "thread"}
    defined_names = {
        node.name.lower()
        for node in ast.walk(_tree(APPLICATION))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined_names.isdisjoint(prohibited)
    assert not any(
        isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(_tree(APPLICATION))
    )
    assert not any(
        isinstance(node, (ast.While, ast.AsyncFor))
        for node in ast.walk(_tree(APPLICATION))
    )


def test_development_adapter_cannot_issue_ci_and_disabled_adapter_always_fails() -> (
    None
):
    adapter_tree = _tree(ADAPTER)
    comparisons = [
        node
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(operator, ast.Is) for operator in node.ops)
    ]
    rendered = ast.dump(adapter_tree, include_attributes=False)
    assert comparisons
    assert "CredentialPurpose" in rendered
    assert "CI_DEPLOYMENT" in rendered
    assert "BACKEND_NOT_CONFIGURED" in rendered
    assert "RuntimeEnvironment" in rendered
    assert "ENV_DEV" in rendered


def test_implementation_has_no_human_admin_migration_client_pool_or_oidc_surface() -> (
    None
):
    prohibited_names = {
        "admin",
        "authorization",
        "client",
        "connection_pool",
        "github",
        "header",
        "human",
        "jwt",
        "migration",
        "oidc",
        "pool",
        "role",
    }
    defined_names: set[str] = set()
    argument_names: set[str] = set()
    for path in OWNED_SOURCE:
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name.lower())
            elif isinstance(node, ast.arg):
                argument_names.add(node.arg.lower())
    assert defined_names.isdisjoint(prohibited_names)
    assert argument_names.isdisjoint(prohibited_names)


def test_owned_scope_is_exactly_the_four_runtime_modules_and_three_tests() -> None:
    expected = {
        DOMAIN,
        PORTS,
        APPLICATION,
        ADAPTER,
        Path("tests/st0407/conftest.py"),
        Path("tests/st0407/test_workload_credentials.py"),
        Path("tests/st0407/test_boundaries.py"),
    }
    assert expected == set(OWNED_SOURCE) | {
        Path("tests/st0407/conftest.py"),
        Path("tests/st0407/test_workload_credentials.py"),
        Path("tests/st0407/test_boundaries.py"),
    }
