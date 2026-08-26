"""Static trust-boundary checks for the ST-1404 durability-capable seam."""

from __future__ import annotations

import ast
from pathlib import Path

from .support import REPOSITORY_ROOT


DOMAIN = Path("python/raos/domain/ops/durable_job_runtime.py")
PORTS = Path("python/raos/ports/durable_job_runtime.py")
APPLICATION = Path("python/raos/application/ops/durable_job_runtime.py")
ADAPTER = Path("python/raos/adapters/recorded_durable_job_runtime.py")
SOURCE = (DOMAIN, PORTS, APPLICATION, ADAPTER)


def _tree(path: Path) -> ast.Module:
    return ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            values.add(node.module)
    return values


def _calls(path: Path) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            values.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            values.add(node.func.attr)
    return values


def test_v2_dependency_arrows_remain_inward() -> None:
    assert {name for name in _imports(DOMAIN) if name.startswith("raos.")} == {
        "raos.domain.ops.job_runtime"
    }
    assert {name for name in _imports(PORTS) if name.startswith("raos.")} == {
        "raos.domain.ops.durable_job_runtime",
        "raos.domain.ops.job_runtime",
        "raos.ports.persistence.context",
    }
    assert {name for name in _imports(APPLICATION) if name.startswith("raos.")} == {
        "raos.domain.ops.durable_job_runtime",
        "raos.domain.ops.job_runtime",
        "raos.ports.durable_job_runtime",
        "raos.ports.persistence.context",
        "raos.ports.queue",
    }
    assert {name for name in _imports(ADAPTER) if name.startswith("raos.")} == {
        "raos.config.runtime",
        "raos.domain.ops.durable_job_runtime",
        "raos.domain.ops.job_runtime",
        "raos.domain.shared.identity",
        "raos.ports.persistence.context",
    }


def test_v2_has_no_live_database_broker_provider_file_or_process_surface() -> None:
    forbidden_import_roots = {
        "aiohttp",
        "asyncio",
        "boto3",
        "botocore",
        "celery",
        "dramatiq",
        "httpx",
        "kafka",
        "kombu",
        "openai",
        "os",
        "pathlib",
        "psycopg",
        "redis",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
    imports: set[str] = set()
    for path in SOURCE:
        imports.update(_imports(path))
    assert not {
        value for value in imports if value.partition(".")[0] in forbidden_import_roots
    }
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
    calls: set[str] = set()
    for path in SOURCE:
        calls.update(_calls(path))
    assert calls.isdisjoint(forbidden_calls)
    for path in SOURCE:
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
            for node in ast.walk(_tree(path))
        )


def test_v2_application_exposes_only_bounded_one_step_methods() -> None:
    service = next(
        node
        for node in _tree(APPLICATION).body
        if isinstance(node, ast.ClassDef)
        and node.name == "DurableRecordedJobRuntimeService"
    )
    public = {
        node.name
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public == {
        "dispatch_once",
        "recover_once",
        "release_quarantine_once",
        "request_cancellation",
        "work_once",
    }
    assert public.isdisjoint(
        {
            "activate",
            "deploy",
            "listen",
            "publish",
            "run",
            "serve",
            "start",
            "subscribe",
        }
    )


def test_v2_records_only_identities_timestamps_classifications_and_fingerprints() -> (
    None
):
    protected = {
        "DeadLetterRecord",
        "DurableHandlerResult",
        "HandlerEffectIntent",
        "HandlerEffectRecord",
        "OutboxLeaseRecord",
        "QuarantineReleaseApproval",
        "QuarantineReleaseRecord",
        "QuarantineReplayClaim",
        "RecordedDurableJobRuntimeSnapshot",
        "WorkLeaseRecord",
    }
    fields: set[str] = set()
    for path in (DOMAIN, ADAPTER):
        for node in _tree(path).body:
            if not isinstance(node, ast.ClassDef) or node.name not in protected:
                continue
            fields.update(
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
            )
    assert "payload_fingerprint" not in fields or "raw_payload" not in fields
    assert fields.isdisjoint(
        {
            "body",
            "credential",
            "exception",
            "exception_text",
            "provider_response",
            "raw_payload",
            "raw_result",
            "receipt_handle",
            "secret",
            "sql",
        }
    )


def test_v2_recorded_adapter_is_dev_ci_only_and_never_claims_live_durability() -> None:
    adapter = (REPOSITORY_ROOT / ADAPTER).read_text(encoding="utf-8")
    assert "RuntimeEnvironment.ENV_DEV" in adapter
    assert "RuntimeEnvironment.CI" in adapter
    assert "RuntimeEnvironment.PRODUCTION" not in adapter
    assert "RuntimeEnvironment.STAGING" not in adapter
    assert "provider" in adapter.lower()
    for prohibited in (
        "Amazon SQS",
        "Google Pub/Sub",
        "Kafka",
        "RabbitMQ",
        "exactly-once",
        "production-ready",
    ):
        assert prohibited not in adapter
