"""Static architecture and dangerous-surface assertions for ST-0402."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OWNED_SOURCE = (
    Path("python/raos/domain/iam/step_up.py"),
    Path("python/raos/ports/step_up.py"),
    Path("python/raos/application/iam/step_up.py"),
    Path("python/raos/adapters/development_step_up.py"),
    Path("python/raos/adapters/recorded_step_up.py"),
    Path("python/raos/adapters/disabled_admin_mfa_http.py"),
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


def test_source_dependencies_point_inward_and_exclude_delivery_provider_db_types() -> (
    None
):
    domain_imports = _imports(OWNED_SOURCE[0])
    port_imports = _imports(OWNED_SOURCE[1])
    application_imports = _imports(OWNED_SOURCE[2])
    development_adapter_imports = _imports(OWNED_SOURCE[3])
    recorded_adapter_imports = _imports(OWNED_SOURCE[4])
    http_adapter_imports = _imports(OWNED_SOURCE[5])

    assert {name for name in domain_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authentication"
    }
    assert {name for name in port_imports if name.startswith("raos.")} == {
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
    }
    assert {name for name in application_imports if name.startswith("raos.")} == {
        "raos.application.iam.authentication",
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
        "raos.ports.step_up",
    }
    assert {
        name for name in development_adapter_imports if name.startswith("raos.")
    } == {
        "raos.config.runtime",
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
    }
    assert {name for name in recorded_adapter_imports if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
    }
    assert {name for name in http_adapter_imports if name.startswith("raos.")} == {
        "raos.application.iam.step_up",
        "raos.config.runtime",
        "raos.domain.iam.authentication",
        "raos.domain.iam.step_up",
    }

    all_imports = set().union(
        domain_imports,
        port_imports,
        application_imports,
        development_adapter_imports,
        recorded_adapter_imports,
        http_adapter_imports,
    )
    forbidden_roots = {
        "boto3",
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


def test_development_adapter_has_no_file_network_process_env_or_factor_surface() -> (
    None
):
    tree = _tree(OWNED_SOURCE[3])
    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
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
        }
    )
    assert not {
        name
        for name in imported
        if name.partition(".")[0]
        in {"os", "pathlib", "requests", "socket", "subprocess", "urllib"}
    }


def test_new_runtime_selects_no_provider_factor_or_credential_mechanism() -> None:
    prohibited = {
        "acr",
        "amr",
        "auth_time",
        "bearer",
        "cookie",
        "middleware",
        "otp",
        "password",
        "secret",
        "totp",
        "webauthn",
    }
    defined_names: set[str] = set()
    for path in OWNED_SOURCE:
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name.lower())
            elif isinstance(node, ast.arg):
                defined_names.add(node.arg.lower())
    assert defined_names.isdisjoint(prohibited)


def test_recorded_adapter_has_no_network_provider_process_or_environment_input() -> (
    None
):
    tree = _tree(OWNED_SOURCE[4])
    identifiers = {
        node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    imported = _imports(OWNED_SOURCE[4])

    assert identifiers.isdisjoint(
        {
            "cookie",
            "bearer",
            "environ",
            "getenv",
            "password",
            "secret",
            "socket",
            "subprocess",
            "totp",
            "webauthn",
        }
    )
    assert attributes.isdisjoint({"getenv", "request", "urlopen", "popen", "system"})
    assert not {
        name
        for name in imported
        if name.partition(".")[0]
        in {"boto3", "httpx", "requests", "socket", "subprocess", "urllib"}
    }


def test_admin_mfa_projection_registers_no_route_server_or_token_delivery() -> None:
    path = OWNED_SOURCE[5]
    tree = _tree(path)
    imported = _imports(path)
    identifiers = {
        node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr.lower() for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not {
        name
        for name in imported
        if name.partition(".")[0]
        in {
            "aiohttp",
            "boto3",
            "fastapi",
            "flask",
            "httpx",
            "requests",
            "socket",
            "starlette",
        }
    }
    assert identifiers.isdisjoint(
        {"app", "bearer", "cookie", "middleware", "router", "server", "socket"}
    )
    assert attributes.isdisjoint(
        {"add_api_route", "add_route", "listen", "route", "run", "serve"}
    )
