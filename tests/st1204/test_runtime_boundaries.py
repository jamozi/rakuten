"""Static closure tests for the recorded, non-persistent GA4 runtime slice."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = (
    "python/raos/domain/analytics/ga4.py",
    "python/raos/ports/ga4.py",
    "python/raos/application/analytics/ga4_import.py",
    "python/raos/adapters/recorded_ga4.py",
)


@pytest.mark.parametrize("relative_path", RUNTIME_PATHS)
def test_runtime_imports_no_provider_network_database_or_filesystem(
    relative_path: str,
) -> None:
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
    forbidden = (
        "boto",
        "google",
        "httpx",
        "pathlib",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    )
    assert not any(name.startswith(forbidden) for name in imported)


@pytest.mark.parametrize("relative_path", RUNTIME_PATHS)
def test_runtime_calls_no_io_transport_persistence_or_external_action(
    relative_path: str,
) -> None:
    tree = ast.parse((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert names.isdisjoint({"open", "exec", "eval", "getenv", "Popen", "system"})
    assert attributes.isdisjoint(
        {
            "connect",
            "commit",
            "execute",
            "get",
            "post",
            "put",
            "publish",
            "save",
            "write_bytes",
            "write_text",
        }
    )


def test_adapter_does_not_retain_fixture_bytes_or_expose_transport() -> None:
    path = REPOSITORY_ROOT / "python/raos/adapters/recorded_ga4.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    slots = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__slots__"
            for target in node.targets
        )
    ]
    assert all("fixture_bytes" not in ast.unparse(value) for value in slots)
    assert "os.environ" not in source
    assert "credential" not in source.lower()


def test_port_exposes_only_one_read_operation() -> None:
    tree = ast.parse(
        (REPOSITORY_ROOT / "python/raos/ports/ga4.py").read_text(encoding="utf-8")
    )
    protocols = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    assert [node.name for node in protocols] == ["RecordedGa4ReportPort"]
    methods = [
        node.name
        for node in protocols[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ["read"]


def test_application_contains_no_retry_pagination_queue_or_job_loop() -> None:
    source = (
        REPOSITORY_ROOT / "python/raos/application/analytics/ga4_import.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))
    assert "sleep" not in source
    assert "retry" not in source.lower()
    assert "queue" not in source.lower()
    assert "repository" not in source.lower()


def test_runtime_never_claims_live_ready_validated_or_persisted() -> None:
    combined = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in RUNTIME_PATHS
    )
    for forbidden in ("VALIDATED", "PERSISTED", "LIVE_EXECUTED", "TST_030_PASS"):
        assert forbidden not in combined
