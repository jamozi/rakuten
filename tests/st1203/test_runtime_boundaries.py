"""Static boundary checks for the non-persistent recorded runtime slice."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = (
    "python/raos/domain/analytics/search_console.py",
    "python/raos/ports/search_console.py",
    "python/raos/application/analytics/search_console_import.py",
    "python/raos/adapters/recorded_search_console.py",
)


@pytest.mark.parametrize("relative_path", RUNTIME_PATHS)
def test_runtime_source_has_no_live_or_persistence_imports(relative_path: str) -> None:
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    forbidden_prefixes = (
        "boto",
        "google",
        "httpx",
        "requests",
        "socket",
        "sqlalchemy",
        "psycopg",
        "urllib",
    )
    assert not any(name.startswith(forbidden_prefixes) for name in imported)


@pytest.mark.parametrize("relative_path", RUNTIME_PATHS)
def test_runtime_has_no_external_or_persistence_calls(relative_path: str) -> None:
    tree = ast.parse((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called_names.isdisjoint(
        {"open", "exec", "eval", "getenv", "system", "Popen", "run"}
    )
    assert called_attributes.isdisjoint(
        {
            "connect",
            "commit",
            "execute",
            "get",
            "post",
            "put",
            "save",
            "write_bytes",
            "write_text",
        }
    )


def test_adapter_does_not_open_paths_or_retain_fixture_bytes() -> None:
    source = (
        REPOSITORY_ROOT / "python/raos/adapters/recorded_search_console.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "pathlib" not in source
    assert "os.environ" not in source
    slot_assignments = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__slots__"
            for target in node.targets
        )
    ]
    assert all("fixture_bytes" not in ast.unparse(value) for value in slot_assignments)


def test_application_contains_no_pagination_retry_job_or_queue_loop() -> None:
    source = (
        REPOSITORY_ROOT / "python/raos/application/analytics/search_console_import.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))
    assert "sleep" not in source
    assert "retry" not in source.lower()
    assert "queue" not in source.lower()
    assert "import_job" not in source.lower()


def test_port_exposes_only_one_credential_free_exchange() -> None:
    path = REPOSITORY_ROOT / "python/raos/ports/search_console.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    protocols = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    assert [node.name for node in protocols] == ["RecordedSearchConsoleExchange"]
    methods = [
        node.name
        for node in protocols[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ["exchange"]
