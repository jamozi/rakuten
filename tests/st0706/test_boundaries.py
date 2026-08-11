"""Static trust-boundary checks for the local ST-0706 candidate."""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path
from types import ModuleType

from conftest import PLAN, REPOSITORY_ROOT
from raos.adapters.recorded_ai_job_orchestration import (
    RecordedAiJobOrchestrationAdapter,
    RecordedProviderStep,
    RecordedValidationStep,
)
from raos.application.ai.job_orchestration import (
    DevelopmentRecordedAiJobOrchestrationService,
)
from raos.domain.ai import job_orchestration as domain_module
from raos.ports.ai_job_orchestration import (
    RecordedAiJobEventSink,
    RecordedAiJobStatePort,
    RecordedAiProviderExecutionPort,
    RecordedAiValidationPort,
)


RUNTIME_PATHS = (
    REPOSITORY_ROOT / "python/raos/domain/ai/job_orchestration.py",
    REPOSITORY_ROOT / "python/raos/ports/ai_job_orchestration.py",
    REPOSITORY_ROOT / "python/raos/application/ai/job_orchestration.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_ai_job_orchestration.py",
)

BANNED_IMPORT_ROOTS = frozenset(
    {
        "asyncio",
        "boto3",
        "celery",
        "fastapi",
        "http",
        "httpx",
        "logging",
        "multiprocessing",
        "openai",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
)
BANNED_CALLS = frozenset(
    {
        "create_task",
        "getenv",
        "open",
        "sleep",
        "spawn",
        "start",
        "system",
        "Thread",
        "uuid4",
    }
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _public_methods(candidate: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(candidate)
        if not name.startswith("_") and callable(member)
    }


def _module_path(module: ModuleType | None) -> Path:
    assert module is not None
    assert module.__file__ is not None
    return Path(module.__file__).resolve()


def test_imported_modules_resolve_to_the_exact_owned_source_paths() -> None:
    modules = (
        domain_module,
        inspect.getmodule(RecordedAiJobEventSink),
        inspect.getmodule(DevelopmentRecordedAiJobOrchestrationService),
        inspect.getmodule(RecordedAiJobOrchestrationAdapter),
    )
    assert tuple(_module_path(module) for module in modules) == tuple(
        path.resolve() for path in RUNTIME_PATHS
    )


def test_st0705_validation_plan_binding_matches_committed_source_bytes() -> None:
    source = (
        REPOSITORY_ROOT
        / "changes/st-0705/contracts/ai-output-validation-reference-plan.v1.yaml"
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == PLAN.plan_sha256


def test_public_method_inventory_exposes_only_one_call_and_metadata_snapshots() -> None:
    assert _public_methods(DevelopmentRecordedAiJobOrchestrationService) == {"execute"}
    assert _public_methods(RecordedAiProviderExecutionPort) == {"execute"}
    assert _public_methods(RecordedAiValidationPort) == {"observe"}
    assert _public_methods(RecordedAiJobStatePort) == {"complete", "exchange"}
    assert _public_methods(RecordedAiJobEventSink) == {"append"}
    assert _public_methods(RecordedAiJobOrchestrationAdapter) == {
        "append",
        "complete",
        "completed_results",
        "event_observations",
        "exchange",
        "execute",
        "observe",
        "provider_outcomes",
        "validation_observations",
    }
    assert _public_methods(RecordedProviderStep) == set()
    assert _public_methods(RecordedValidationStep) == set()


def test_runtime_ast_has_no_st1404_or_external_runtime_imports_and_calls() -> None:
    imported: set[str] = set()
    called: set[str] = set()
    source = ""
    for path in RUNTIME_PATHS:
        source += path.read_text(encoding="utf-8")
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)

    assert "st1404" not in source.lower()
    assert not any(name.split(".")[0] in BANNED_IMPORT_ROOTS for name in imported)
    assert not (called & BANNED_CALLS)


def test_domain_has_no_arbitrary_content_or_exception_surface() -> None:
    forbidden = {
        "body",
        "content",
        "exception",
        "message",
        "metadata",
        "payload",
        "prompt",
        "response",
        "traceback",
    }
    declared_fields: set[str] = set()
    for node in ast.walk(_tree(RUNTIME_PATHS[0])):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared_fields.add(node.target.id)
    assert not (declared_fields & forbidden)


def test_application_has_no_attempt_loop_or_background_definition() -> None:
    tree = _tree(RUNTIME_PATHS[2])
    assert not any(
        isinstance(node, (ast.For, ast.While, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
    assert all(
        node.name not in {"retry", "replay", "release", "schedule"}
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
