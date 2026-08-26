"""Static and value-safety boundaries for ST-0806."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import inspect
import pickle
from pathlib import Path

import pytest

from .support import REPOSITORY_ROOT, candidate, request
from raos.adapters.recorded_ai_draft_integration import (
    RecordedAiDraftIntegrationAdapter,
)
from raos.application.editorial.ai_draft_integration import AiDraftIntegrationService
from raos.domain.editorial import ai_draft_integration as domain_module
from raos.domain.editorial.ai_draft_integration import (
    AiDraftIntegrationFailure,
    AiDraftIntegrationFailureCode,
    ClaimFactReference,
    MinimalDraftDiff,
    RecordedDraftCandidate,
)
from raos.ports.ai_draft_integration import RecordedAiDraftIntegrationPort


RUNTIME_PATHS = (
    REPOSITORY_ROOT / "python/raos/domain/editorial/ai_draft_integration.py",
    REPOSITORY_ROOT / "python/raos/ports/ai_draft_integration.py",
    REPOSITORY_ROOT / "python/raos/application/editorial/ai_draft_integration.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_ai_draft_integration.py",
)
BANNED_IMPORTS = {
    "asyncio",
    "boto3",
    "fastapi",
    "http",
    "httpx",
    "logging",
    "multiprocessing",
    "openai",
    "os",
    "pathlib",
    "random",
    "requests",
    "socket",
    "sqlalchemy",
    "subprocess",
    "urllib",
}
BANNED_CALLS = {
    "create_task",
    "getenv",
    "open",
    "sleep",
    "spawn",
    "start",
    "system",
    "uuid4",
}


def _public_methods(value: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(value)
        if not name.startswith("_") and callable(member)
    }


def _module_path(module: object) -> Path:
    assert module is not None
    module_file = getattr(module, "__file__", None)
    assert isinstance(module_file, str)
    return Path(module_file).resolve()


def test_runtime_modules_and_one_call_public_surface_are_exact() -> None:
    modules = (
        domain_module,
        inspect.getmodule(RecordedAiDraftIntegrationPort),
        inspect.getmodule(AiDraftIntegrationService),
        inspect.getmodule(RecordedAiDraftIntegrationAdapter),
    )
    assert tuple(_module_path(module) for module in modules) == tuple(
        path.resolve() for path in RUNTIME_PATHS
    )
    assert _public_methods(RecordedAiDraftIntegrationPort) == {"integrate"}
    assert _public_methods(AiDraftIntegrationService) == {"integrate"}
    assert _public_methods(RecordedAiDraftIntegrationAdapter) == {"integrate"}


def test_runtime_has_no_external_or_side_effect_runtime_surface() -> None:
    imported: set[str] = set()
    called: set[str] = set()
    combined = ""
    for path in RUNTIME_PATHS:
        combined += path.read_text(encoding="utf-8")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
    assert "st1701" not in combined.lower()
    assert not any(name.split(".")[0] in BANNED_IMPORTS for name in imported)
    assert not (called & BANNED_CALLS)
    service_tree = ast.parse(RUNTIME_PATHS[2].read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.For, ast.While, ast.AsyncFunctionDef))
        for node in ast.walk(service_tree)
    )


@pytest.mark.parametrize(
    "value",
    [request(), candidate(), candidate().diff, candidate().claim_fact_references[0]],
)
def test_values_are_redacted_frozen_and_non_pickleable(value: object) -> None:
    assert "Synthetic" not in repr(value)
    assert "Synthetic" not in str(value)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(value)
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        setattr(value, "unexpected", "secret")


def test_changed_block_ids_are_unique_existing_and_ast_ordered() -> None:
    valid = candidate()
    with pytest.raises(AiDraftIntegrationFailure) as duplicate:
        replace(
            valid.diff,
            changed_block_ids=("BLK-FIX-002", "BLK-FIX-002"),
        )
    assert duplicate.value.code is AiDraftIntegrationFailureCode.INVALID_REQUEST
    with pytest.raises(AiDraftIntegrationFailure) as absent:
        replace(
            valid,
            diff=MinimalDraftDiff(
                before_body_sha256=valid.diff.before_body_sha256,
                after_body_sha256=valid.diff.after_body_sha256,
                changed=True,
                changed_block_ids=("BLK-NOT-PRESENT",),
            ),
        )
    assert absent.value.code is AiDraftIntegrationFailureCode.CANDIDATE_INVALID


def test_reference_order_and_source_packet_binding_are_strict() -> None:
    valid = candidate()
    first, second = valid.claim_fact_references
    with pytest.raises(AiDraftIntegrationFailure):
        replace(valid, claim_fact_references=(second, first))
    with pytest.raises(AiDraftIntegrationFailure) as mismatch:
        replace(
            valid,
            claim_fact_references=(
                replace(first, source_packet_version_id=first.fact_id),
                second,
            ),
        )
    assert mismatch.value.code is AiDraftIntegrationFailureCode.BINDING_MISMATCH


def test_exported_domain_inventory_is_closed() -> None:
    assert set(domain_module.__all__) == {
        "AI_ARTICLE_DRAFT_TASK",
        "AiDraftDisposition",
        "AiDraftEnvironment",
        "AiDraftIntegrationFailure",
        "AiDraftIntegrationFailureCode",
        "AiDraftIntegrationRequest",
        "AiDraftIntegrationResult",
        "ClaimFactReference",
        "CoverageStatus",
        "ExecutionStatus",
        "MinimalDraftDiff",
        "RecordedDraftCandidate",
        "fail_ai_draft_integration",
    }
    assert inspect.isclass(ClaimFactReference)
    assert inspect.isclass(RecordedDraftCandidate)
