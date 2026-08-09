"""Static ownership, architecture, and forbidden-capability checks for ST-0405."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import REPOSITORY_ROOT


OWNED_SOURCE_PATHS = (
    Path("python/raos/domain/ops/audit.py"),
    Path("python/raos/ports/audit.py"),
    Path("python/raos/application/ops/audit.py"),
    Path("python/raos/adapters/recorded_audit.py"),
)
FORBIDDEN_IMPORT_ROOTS = {
    "asyncio",
    "fastapi",
    "httpx",
    "logging",
    "os",
    "pathlib",
    "requests",
    "socket",
    "sqlalchemy",
    "subprocess",
}
FORBIDDEN_CALL_NAMES = {
    "Thread",
    "create_task",
    "getenv",
    "open",
    "sleep",
    "start",
}
FORBIDDEN_IDENTIFIERS = {
    "affiliate_url",
    "cookie",
    "exception_message",
    "header",
    "ip_address",
    "personal_data",
    "prompt_body",
    "provider_body",
    "raw_details",
    "secret",
    "source_body",
    "sql",
    "stack_trace",
    "access_token",
    "user_agent",
}


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_source_imports_respect_inward_architecture_and_capability_boundary() -> None:
    for relative_path in OWNED_SOURCE_PATHS:
        tree = _tree(relative_path)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
        assert FORBIDDEN_IMPORT_ROOTS.isdisjoint(
            {name.split(".", maxsplit=1)[0] for name in imports}
        )
        if relative_path == Path("python/raos/domain/ops/audit.py"):
            assert all(
                not name.startswith(("raos.application", "raos.adapters", "raos.ports"))
                for name in imports
            )
        if relative_path == Path("python/raos/ports/audit.py"):
            assert all(
                not name.startswith(("raos.application", "raos.adapters"))
                for name in imports
            )
        if relative_path == Path("python/raos/application/ops/audit.py"):
            assert all(not name.startswith("raos.adapters") for name in imports)


def test_source_has_no_io_background_loop_or_ambient_environment_calls() -> None:
    for relative_path in OWNED_SOURCE_PATHS:
        tree = _tree(relative_path)
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert FORBIDDEN_CALL_NAMES.isdisjoint(calls | attributes)
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
            for node in ast.walk(tree)
        )


def test_recorded_adapter_uses_only_rlock_from_threading() -> None:
    tree = _tree(Path("python/raos/adapters/recorded_audit.py"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    threading = [node for node in imports if node.module == "threading"]
    assert len(threading) == 1
    assert [(alias.name, alias.asname) for alias in threading[0].names] == [
        ("RLock", None)
    ]


def test_public_surfaces_expose_no_query_mutation_export_or_arbitrary_details() -> None:
    from raos.adapters.recorded_audit import RecordedAuditAdapter
    from raos.application.ops.audit import AuditService
    from raos.domain.ops.audit import AuditContext, AuditEvent
    from raos.ports.audit import AuditContextSource, AuditEventAppender

    forbidden = {
        "clear",
        "delete",
        "details",
        "export",
        "get",
        "list",
        "query",
        "remove",
        "retention",
        "update",
    }
    for candidate in (
        RecordedAuditAdapter,
        AuditService,
        AuditContext,
        AuditEvent,
        AuditContextSource,
        AuditEventAppender,
    ):
        assert forbidden.isdisjoint(set(dir(candidate)))


def test_sensitive_field_names_are_absent_from_owned_source_ast() -> None:
    identifiers: set[str] = set()
    for relative_path in OWNED_SOURCE_PATHS:
        for node in ast.walk(_tree(relative_path)):
            if isinstance(node, ast.Name):
                identifiers.add(node.id.lower())
            elif isinstance(node, (ast.Attribute, ast.arg)):
                identifiers.add(
                    (node.attr if isinstance(node, ast.Attribute) else node.arg).lower()
                )
    assert FORBIDDEN_IDENTIFIERS.isdisjoint(identifiers)


def test_owned_source_contains_no_database_http_or_provider_literals() -> None:
    forbidden_fragments = (
        "create table",
        "delete from",
        "http://",
        "https://",
        "insert into",
        "select ",
        "update ",
    )
    for relative_path in OWNED_SOURCE_PATHS:
        text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8").lower()
        assert not any(fragment in text for fragment in forbidden_fragments)
