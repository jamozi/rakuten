"""Static trust-boundary and prohibited-surface checks for ST-1601."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from .support import REPOSITORY_ROOT
from raos.adapters.recorded_telemetry import (
    DisabledTelemetrySink,
    RecordedTelemetrySink,
)
from raos.application.ops.telemetry import TelemetryRecorder
from raos.domain.ops.telemetry import (
    LogRecord,
    MetricRecord,
    TelemetryContext,
    TraceRecord,
)


DOMAIN_INIT = Path("python/raos/domain/ops/__init__.py")
DOMAIN = Path("python/raos/domain/ops/telemetry.py")
PORT = Path("python/raos/ports/telemetry.py")
APPLICATION_INIT = Path("python/raos/application/ops/__init__.py")
APPLICATION = Path("python/raos/application/ops/telemetry.py")
ADAPTER = Path("python/raos/adapters/recorded_telemetry.py")
README = Path("changes/st-1601/README.md")
OWNED_RUNTIME = (DOMAIN_INIT, DOMAIN, PORT, APPLICATION_INIT, APPLICATION, ADAPTER)
OWNED_PATHS = {
    README,
    *OWNED_RUNTIME,
    Path("tests/st1601/conftest.py"),
    Path("tests/st1601/test_telemetry.py"),
    Path("tests/st1601/test_failure_isolation.py"),
    Path("tests/st1601/test_boundaries.py"),
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


def _calls(path: Path) -> list[ast.Call]:
    return [node for node in ast.walk(_tree(path)) if isinstance(node, ast.Call)]


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _public_methods(cls: type[object]) -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(cls)
        if not name.startswith("_") and callable(value)
    }


def test_dependency_directions_remain_inward() -> None:
    assert not {name for name in _imports(DOMAIN) if name.startswith("raos.")}
    assert {name for name in _imports(PORT) if name.startswith("raos.")} == {
        "raos.domain.ops.telemetry"
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.domain.ops.telemetry",
        "raos.ports.telemetry",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.telemetry",
    }


def test_no_backend_framework_network_file_environment_or_process_surface() -> None:
    all_imports = set().union(*(_imports(path) for path in OWNED_RUNTIME))
    forbidden_roots = {
        "asyncio",
        "boto3",
        "botocore",
        "contextvars",
        "fastapi",
        "http",
        "httpx",
        "logging",
        "openai",
        "opentelemetry",
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
    assert _imports(ADAPTER) & {"threading"} == {"threading"}
    adapter_import = next(
        node
        for node in _tree(ADAPTER).body
        if isinstance(node, ast.ImportFrom) and node.module == "threading"
    )
    assert {alias.name for alias in adapter_import.names} == {"RLock"}


def test_no_background_lifecycle_external_io_or_ambient_calls() -> None:
    forbidden_calls = {
        "Thread",
        "Timer",
        "clear",
        "create_task",
        "environ",
        "evict",
        "export",
        "flush",
        "getenv",
        "open",
        "Popen",
        "read_bytes",
        "read_text",
        "request",
        "retry",
        "run",
        "sleep",
        "socket",
        "start",
        "stop",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    called = {
        name
        for path in OWNED_RUNTIME
        for node in _calls(path)
        if (name := _call_name(node)) is not None
    }
    assert called.isdisjoint(forbidden_calls)
    for path in OWNED_RUNTIME:
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
            for node in ast.walk(_tree(path))
        )


def test_context_and_signal_constructor_surfaces_are_exactly_closed() -> None:
    assert set(inspect.signature(TelemetryContext).parameters) == {
        "correlation_id",
        "causation_id",
        "job_id",
        "article_id",
        "snapshot_id",
        "provider_request_id",
    }
    assert set(inspect.signature(TraceRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "outcome",
        "duration_ms",
    }
    assert set(inspect.signature(MetricRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "value",
        "unit",
    }
    assert set(inspect.signature(LogRecord).parameters) == {
        "context",
        "observed_at",
        "name",
        "level",
    }
    exposed = set().union(
        *(
            set(inspect.signature(cls).parameters)
            for cls in (TelemetryContext, TraceRecord, MetricRecord, LogRecord)
        )
    )
    assert exposed.isdisjoint(
        {
            "attributes",
            "authorization",
            "body",
            "cookie",
            "credential",
            "email",
            "exception",
            "exception_text",
            "finance",
            "header",
            "ip",
            "labels",
            "message",
            "metadata",
            "payload",
            "pii",
            "prompt",
            "provider_response",
            "query",
            "revenue",
            "secret",
            "source",
            "sql",
            "tags",
            "token",
            "url",
        }
    )


def test_port_is_exact_record_contract_not_generic_mapping_or_object() -> None:
    source = (REPOSITORY_ROOT / PORT).read_text(encoding="utf-8")
    assert "record: TelemetryRecord" in source
    assert "Mapping" not in source
    assert "Any" not in source
    assert "dict[" not in source
    assert "object" not in source


def test_application_failure_handler_is_single_emit_without_exception_binding() -> None:
    tree = _tree(APPLICATION)
    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler.type, ast.Name)
    assert handler.type.id == "Exception"
    assert handler.name is None
    emits = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "emit"
    ]
    assert len(emits) == 1
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"repr", "str"}
        for node in ast.walk(tree)
    )


def test_sink_and_recorder_public_apis_have_no_lifecycle_or_retention_controls() -> (
    None
):
    assert _public_methods(DisabledTelemetrySink) == {"emit"}
    assert _public_methods(RecordedTelemetrySink) == {"emit", "snapshot"}
    assert _public_methods(TelemetryRecorder) == {"record"}
    forbidden = {
        "clear",
        "close",
        "delete",
        "deploy",
        "evict",
        "export",
        "flush",
        "publish",
        "retry",
        "run",
        "serve",
        "start",
        "stop",
    }
    assert _public_methods(RecordedTelemetrySink).isdisjoint(forbidden)


def test_owned_scope_is_exactly_the_delegated_eleven_paths() -> None:
    assert OWNED_PATHS == {
        Path("changes/st-1601/README.md"),
        Path("python/raos/domain/ops/telemetry.py"),
        Path("python/raos/domain/ops/__init__.py"),
        Path("python/raos/ports/telemetry.py"),
        Path("python/raos/application/ops/telemetry.py"),
        Path("python/raos/application/ops/__init__.py"),
        Path("python/raos/adapters/recorded_telemetry.py"),
        Path("tests/st1601/conftest.py"),
        Path("tests/st1601/test_telemetry.py"),
        Path("tests/st1601/test_failure_isolation.py"),
        Path("tests/st1601/test_boundaries.py"),
    }
