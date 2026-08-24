"""Static authority and immutable-value boundaries for ST-0806 V2."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path
import pickle
from threading import Barrier, Thread

import pytest

from raos.adapters.recorded_ai_draft_integration_v2 import (
    RecordedAiDraftIntegrationAdapterV2,
    load_recorded_ai_draft_fixture_v2,
)
from raos.application.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationServiceV2,
)
from raos.domain.editorial import ai_draft_integration_v2 as domain
from raos.domain.editorial.ai_draft_integration_v2 import (
    AiDraftV2Activation,
    AiDraftV2Failure,
    AiDraftV2FailureCode,
)
from raos.ports.ai_draft_integration_v2 import RecordedAiDraftIntegrationPortV2
from v2_support import REPOSITORY_ROOT, V2_FIXTURE, request, service_and_adapter


RUNTIME_PATHS = (
    REPOSITORY_ROOT / "python/raos/domain/editorial/ai_draft_integration_v2.py",
    REPOSITORY_ROOT / "python/raos/ports/ai_draft_integration_v2.py",
    REPOSITORY_ROOT / "python/raos/application/editorial/ai_draft_integration_v2.py",
    REPOSITORY_ROOT / "python/raos/adapters/recorded_ai_draft_integration_v2.py",
)
BANNED_IMPORT_ROOTS = {
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


def test_runtime_surface_is_one_call_and_has_no_external_authority() -> None:
    imports: set[str] = set()
    calls: set[str] = set()
    combined = ""
    for path in RUNTIME_PATHS:
        source = path.read_text(encoding="utf-8")
        combined += source
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
    assert not any(name.split(".")[0] in BANNED_IMPORT_ROOTS for name in imports)
    assert not calls & BANNED_CALLS
    assert "RecordedDurableAiJobQueueServiceV2" not in combined
    assert "RecordedDurableAiJobStateAdapterV2" not in combined
    assert "ST-1404" not in combined
    assert _public_methods(RecordedAiDraftIntegrationPortV2) == {"integrate"}
    assert _public_methods(AiDraftIntegrationServiceV2) == {"integrate"}
    assert _public_methods(RecordedAiDraftIntegrationAdapterV2) == {"integrate"}


def test_default_disabled_fails_before_consuming_fixture() -> None:
    bound = request()
    service, adapter = service_and_adapter(bound_request=bound, enabled=False)
    with pytest.raises(AiDraftV2Failure) as failure:
        service.integrate(request=bound)
    assert failure.value.code is AiDraftV2FailureCode.DISABLED
    assert adapter.call_count == 0
    assert AiDraftV2Activation().enabled is False


def test_values_are_redacted_frozen_and_non_pickleable() -> None:
    bound = request()
    material = load_recorded_ai_draft_fixture_v2(V2_FIXTURE.read_bytes())
    service, _ = service_and_adapter(bound_request=bound)
    result = service.integrate(request=bound)
    values: tuple[object, ...] = (
        bound,
        material,
        material.after_ast,
        result,
        result.durable_binding,
        result.proposal,
        result.adoption_intent,
    )
    for value in values:
        assert "Synthetic" not in repr(value)
        assert "Synthetic" not in str(value)
        with pytest.raises((TypeError, pickle.PicklingError)):
            pickle.dumps(value)
        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            setattr(value, "unexpected", "secret")


def test_contract_and_policy_inventory_is_closed_and_versioned() -> None:
    assert domain.CONTRACT_SHA256 == (
        "c08c4b9cbf1c35d0c8e3177d0929d0fc9a0fbd2187d0fc4c08683ac636eef18e"
    )
    assert domain.POLICY_SHA256 == (
        "443b5ea91544ea1e8d5f9c7c2e71ebe331fda6f81397f0b51e25aa70da5c77f2"
    )
    assert set(domain.__all__) == {
        "AI_ARTICLE_DRAFT_TASK_V2",
        "CONTRACT_SHA256",
        "FIXTURE_DOCUMENT_ID",
        "FIXTURE_SCHEMA_VERSION",
        "MAXIMUM_COMPLETE_CLAIMS",
        "MAXIMUM_DIFF_OPERATIONS",
        "MAXIMUM_FIXTURE_BYTES",
        "MAXIMUM_JSON_POINTER_BYTES",
        "POLICY_ID",
        "POLICY_SHA256",
        "AiDraftIntegrationRequestV2",
        "AiDraftIntegrationResultV2",
        "AiDraftV2Activation",
        "AiDraftV2Failure",
        "AiDraftV2FailureCode",
        "BoundContentAstV2",
        "ContentAstDiffOperationV2",
        "ContentAstDiffV2",
        "CoverageBindingV2",
        "DiffOperationKindV2",
        "DraftAdoptionIntentV2",
        "DraftArticleVersionProposalV2",
        "DraftCoverageDecisionV2",
        "DraftExecutionV2",
        "DraftProposalDispositionV2",
        "DurableSucceededBindingV2",
        "RecordedDraftMaterialV2",
        "bind_coverage_v2",
        "bind_durable_succeeded_completion_v2",
        "build_content_ast_diff_v2",
        "fail_ai_draft_v2",
    }


def test_no_runtime_file_reads_fixture_or_environment() -> None:
    for path in RUNTIME_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {"read_bytes", "read_text", "write_bytes", "write_text"}
            for node in ast.walk(tree)
        )
    assert Path(V2_FIXTURE).is_file()


def test_concurrent_consumers_get_exactly_one_fixture_and_no_replay() -> None:
    bound = request()
    service, adapter = service_and_adapter(bound_request=bound)
    barrier = Barrier(8)
    successes: list[object] = []
    failures: list[AiDraftV2FailureCode] = []

    def consume() -> None:
        barrier.wait()
        try:
            successes.append(service.integrate(request=bound))
        except AiDraftV2Failure as failure:
            failures.append(failure.code)

    threads = tuple(Thread(target=consume) for _index in range(8))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert len(successes) == 1
    assert failures == [AiDraftV2FailureCode.COLLABORATOR_FAILURE] * 7
    assert adapter.call_count == 1
