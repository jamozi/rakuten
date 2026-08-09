"""Static inward-dependency and prohibited-surface tests for ST-1404."""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import REPOSITORY_ROOT


DOMAIN_INIT = Path("python/raos/domain/ops/__init__.py")
DOMAIN = Path("python/raos/domain/ops/job_runtime.py")
PORTS = Path("python/raos/ports/job_runtime.py")
APPLICATION_INIT = Path("python/raos/application/ops/__init__.py")
APPLICATION = Path("python/raos/application/ops/job_runtime.py")
ADAPTER = Path("python/raos/adapters/recorded_job_runtime.py")
OWNED_SOURCE = (
    DOMAIN_INIT,
    DOMAIN,
    PORTS,
    APPLICATION_INIT,
    APPLICATION,
    ADAPTER,
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


def test_dependency_directions_are_exactly_inward() -> None:
    assert not {name for name in _imports(DOMAIN) if name.startswith("raos.")}
    assert {name for name in _imports(PORTS) if name.startswith("raos.")} == {
        "raos.domain.ops.job_runtime"
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.domain.ops.job_runtime",
        "raos.ports.job_runtime",
        "raos.ports.queue",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.job_runtime",
    }


def test_no_database_provider_framework_network_file_or_process_imports() -> None:
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


def test_no_loop_task_thread_sleep_file_network_environment_or_process_calls() -> None:
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
        "start",
        "urlopen",
        "write_bytes",
        "write_text",
    }
    all_calls = set().union(*(_calls(path) for path in OWNED_SOURCE))
    assert all_calls.isdisjoint(forbidden_calls)
    for path in OWNED_SOURCE:
        tree = _tree(path)
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
            for node in ast.walk(tree)
        )


def test_runtime_public_methods_are_only_bounded_steps_and_safe_inspection() -> None:
    application_class = next(
        node
        for node in _tree(APPLICATION).body
        if isinstance(node, ast.ClassDef) and node.name == "RecordedJobRuntimeService"
    )
    public = {
        node.name
        for node in application_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public == {"dispatch_once", "work_once"}
    assert public.isdisjoint(
        {
            "close",
            "deploy",
            "expire_retry_state",
            "publish",
            "release_quarantine",
            "run",
            "serve",
            "start",
            "stop",
        }
    )


def test_domain_records_carry_fingerprints_but_no_raw_payload_or_result() -> None:
    tree = _tree(DOMAIN)
    protected_classes = {
        "JobRecord",
        "AttemptRecord",
        "OutboxRecord",
        "InboxRecord",
        "RecordedJobMessage",
        "RecordedJobInvocation",
        "RecordedHandlerResult",
        "DispatchStepResult",
        "WorkStepResult",
    }
    fields: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name not in protected_classes:
            continue
        fields.update(
            statement.target.id
            for statement in node.body
            if isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
        )
    assert "payload_fingerprint" in fields
    assert "result_fingerprint" in fields
    assert fields.isdisjoint(
        {
            "body",
            "credential",
            "exception",
            "exception_text",
            "payload",
            "provider_response",
            "raw_payload",
            "raw_result",
            "receipt_handle",
            "result",
            "secret",
            "sql",
            "worker_id",
        }
    )


def test_adapter_guard_names_only_exact_dev_and_ci_as_enabled() -> None:
    rendered = ast.dump(_tree(ADAPTER), include_attributes=False)
    assert "RuntimeEnvironment" in rendered
    assert "ENV_DEV" in rendered
    assert "CI" in rendered
    assert "DEVELOPMENT_ONLY" in rendered
    assert "PRODUCTION" not in rendered
    assert "STAGING" not in rendered
    assert "INTEGRATION" not in rendered
    assert "RECOVERY" not in rendered


def test_no_durable_or_external_runtime_dependency_is_claimed_by_code() -> None:
    source = "\n".join(
        (REPOSITORY_ROOT / path).read_text(encoding="utf-8") for path in OWNED_SOURCE
    )
    prohibited = {
        "Celery",
        "Dramatiq",
        "LocalStack",
        "SQS",
        "Temporal",
        "exactly-once",
        "multiprocessing",
        "psycopg",
        "sqlalchemy",
    }
    assert not {value for value in prohibited if value in source}
    normalized = " ".join(source.split())
    assert "same-process atomicity" in normalized
    assert "not a database transaction" in normalized


def test_owned_scope_is_exact_and_does_not_modify_queue_predecessor() -> None:
    expected = {
        DOMAIN_INIT,
        DOMAIN,
        PORTS,
        APPLICATION_INIT,
        APPLICATION,
        ADAPTER,
        Path("tests/st1404/conftest.py"),
        Path("tests/st1404/test_runtime.py"),
        Path("tests/st1404/test_boundaries.py"),
    }
    assert expected == set(OWNED_SOURCE) | {
        Path("tests/st1404/conftest.py"),
        Path("tests/st1404/test_runtime.py"),
        Path("tests/st1404/test_boundaries.py"),
    }
    assert Path("python/raos/ports/queue.py") not in expected
    assert Path("python/raos/adapters/queue_fake.py") not in expected
