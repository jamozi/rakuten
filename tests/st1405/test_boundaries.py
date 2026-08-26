"""Static architecture and dangerous-surface assertions for ST-1405."""

from __future__ import annotations

import ast
from pathlib import Path

from .support import REPOSITORY_ROOT


README = Path("changes/st-1405/README.md")
DOMAIN = Path("python/raos/domain/ops/kill_switch.py")
PORT = Path("python/raos/ports/kill_switch.py")
APPLICATION = Path("python/raos/application/ops/kill_switch.py")
ADAPTER = Path("python/raos/adapters/recorded_kill_switch.py")
OWNED_SOURCE = (DOMAIN, PORT, APPLICATION, ADAPTER)
OWNED_PATHS = {
    README,
    *OWNED_SOURCE,
    Path("tests/st1405/conftest.py"),
    Path("tests/st1405/test_runtime.py"),
    Path("tests/st1405/test_cache.py"),
    Path("tests/st1405/test_boundaries.py"),
}


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
    called: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _public_methods(path: Path, class_name: str) -> set[str]:
    selected = next(
        node
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name
        for node in selected.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def test_dependency_directions_are_exactly_inward() -> None:
    assert not {name for name in _imports(DOMAIN) if name.startswith("raos.")}
    assert {name for name in _imports(PORT) if name.startswith("raos.")} == {
        "raos.domain.ops.kill_switch"
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.application.iam.step_up",
        "raos.domain.iam.authentication",
        "raos.domain.ops.kill_switch",
        "raos.ports.kill_switch",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.kill_switch",
        "raos.ports.kill_switch",
    }


def test_no_database_provider_framework_network_file_or_process_surface() -> None:
    all_imports = set().union(*(_imports(path) for path in OWNED_SOURCE))
    forbidden_roots = {
        "asyncio",
        "boto3",
        "botocore",
        "fastapi",
        "httpx",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "starlette",
        "subprocess",
        "urllib",
    }
    assert not {
        name for name in all_imports if name.partition(".")[0] in forbidden_roots
    }
    forbidden_calls = {
        "create_task",
        "getenv",
        "open",
        "read_bytes",
        "read_text",
        "request",
        "run",
        "sleep",
        "start",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    assert (
        set()
        .union(*(_calls(path) for path in OWNED_SOURCE))
        .isdisjoint(forbidden_calls)
    )


def test_application_exposes_only_command_and_two_independent_guard_queries() -> None:
    assert _public_methods(APPLICATION, "KillSwitchRuntimeService") == {
        "change",
        "publication_commands_allowed",
        "affiliate_cta_eligible",
    }


def test_adapter_is_bounded_in_memory_and_has_no_event_delivery_action() -> None:
    public = _public_methods(ADAPTER, "RecordedKillSwitchAdapter")
    assert public == {
        "compare_and_swap",
        "read_cache",
        "install_cache_snapshot",
        "current_state",
        "event_intents",
    }
    assert public.isdisjoint(
        {
            "deploy",
            "disable",
            "enqueue",
            "execute",
            "publish",
            "release",
            "run",
            "send",
            "serve",
            "start",
            "unpublish",
        }
    )
    adapter_tree = ast.dump(_tree(ADAPTER), include_attributes=False)
    assert "RuntimeEnvironment" in adapter_tree
    assert "ENV_DEV" in adapter_tree
    assert "CI" in adapter_tree
    assert "PRODUCTION" not in adapter_tree
    assert "STAGING" not in adapter_tree
    assert "INTEGRATION" not in adapter_tree
    assert "RECOVERY" not in adapter_tree


def test_event_intent_has_no_publisher_port_or_delivery_state() -> None:
    port_source = (REPOSITORY_ROOT / PORT).read_text(encoding="utf-8")
    domain_tree = _tree(DOMAIN)
    event = next(
        node
        for node in domain_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "KillSwitchEventIntent"
    )
    fields = {
        statement.target.id
        for statement in event.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
    }
    assert "publisher" not in port_source.lower()
    assert fields.isdisjoint(
        {
            "delivered",
            "delivery_attempt",
            "published",
            "published_at",
            "queue_name",
            "topic",
        }
    )


def test_expiry_cannot_be_used_by_application_or_adapter_to_release_state() -> None:
    application_source = (REPOSITORY_ROOT / APPLICATION).read_text(encoding="utf-8")
    adapter_source = (REPOSITORY_ROOT / ADAPTER).read_text(encoding="utf-8")
    domain_source = (REPOSITORY_ROOT / DOMAIN).read_text(encoding="utf-8")
    assert "expires_at" not in application_source
    assert "expires_at" not in adapter_source
    assert "EXPIRES_AT_UNSUPPORTED" in domain_source
    assert "timedelta" not in domain_source


def test_domain_records_no_raw_credential_payload_or_exception_text() -> None:
    protected = {
        "KillSwitchChangeCommand",
        "KillSwitchState",
        "KillSwitchEventIntent",
        "KillSwitchChangeResult",
        "KillSwitchCacheEntry",
        "KillSwitchCacheSnapshot",
    }
    fields: set[str] = set()
    for node in _tree(DOMAIN).body:
        if not isinstance(node, ast.ClassDef) or node.name not in protected:
            continue
        fields.update(
            statement.target.id
            for statement in node.body
            if isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
        )
    assert fields.isdisjoint(
        {
            "credential",
            "exception",
            "exception_text",
            "password",
            "payload",
            "provider_response",
            "raw_reason",
            "secret",
            "token",
        }
    )


def test_owned_scope_is_exact_and_shared_exports_are_untouched() -> None:
    assert OWNED_PATHS == {
        Path("changes/st-1405/README.md"),
        Path("python/raos/domain/ops/kill_switch.py"),
        Path("python/raos/ports/kill_switch.py"),
        Path("python/raos/application/ops/kill_switch.py"),
        Path("python/raos/adapters/recorded_kill_switch.py"),
        Path("tests/st1405/conftest.py"),
        Path("tests/st1405/test_runtime.py"),
        Path("tests/st1405/test_cache.py"),
        Path("tests/st1405/test_boundaries.py"),
    }
    assert Path("python/raos/ports/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/adapters/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/domain/ops/__init__.py") not in OWNED_PATHS
    assert Path("python/raos/application/ops/__init__.py") not in OWNED_PATHS
