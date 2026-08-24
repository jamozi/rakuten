from __future__ import annotations

import ast
import inspect
import pickle

import pytest

from raos.adapters.recorded_ai_evaluation import (
    RecordedAiEvaluationError,
    load_recorded_evaluation_bundle,
)
from raos.application.ai.evaluation_harness import RecordedEvaluationHarness
from raos.domain.ai.evaluation_harness import RecordedEvaluationBundle
from tests.st0707_runtime.support import PATHS, ROOT, artifact_bytes


def _mutate_one_byte(value: bytes) -> bytes:
    index = len(value) // 2
    replacement = b"0" if value[index : index + 1] != b"0" else b"1"
    return value[:index] + replacement + value[index + 1 :]


@pytest.mark.parametrize(
    "artifact_name", tuple(name for name in PATHS if name != "runtime_manifest_bytes")
)
def test_every_owner_and_dependency_artifact_tamper_fails_closed(
    artifact_name: str,
) -> None:
    values = artifact_bytes()
    values[artifact_name] = _mutate_one_byte(values[artifact_name])
    with pytest.raises(RecordedAiEvaluationError):
        load_recorded_evaluation_bundle(**values)


def test_duplicate_keys_noncanonical_json_and_oversize_fail_closed() -> None:
    values = artifact_bytes()
    duplicate = values["dataset_bytes"].replace(
        b'{"dataset":', b'{"dataset":{},"dataset":', 1
    )
    with pytest.raises(RecordedAiEvaluationError):
        load_recorded_evaluation_bundle(**(values | {"dataset_bytes": duplicate}))
    padded = values["suite_registry_bytes"] + b" "
    with pytest.raises(RecordedAiEvaluationError):
        load_recorded_evaluation_bundle(**(values | {"suite_registry_bytes": padded}))
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    with pytest.raises(RecordedAiEvaluationError):
        load_recorded_evaluation_bundle(
            **(values | {"suite_registry_bytes": oversized})
        )


def test_runtime_manifest_behavior_binding_tamper_fails_closed() -> None:
    values = artifact_bytes()
    manifest = values["runtime_manifest_bytes"].replace(
        b'"formal_tst_019":"NOT_EXECUTED"',
        b'"formal_tst_019":"NOT_EXECUTEX"',
        1,
    )
    with pytest.raises(RecordedAiEvaluationError):
        load_recorded_evaluation_bundle(
            **(values | {"runtime_manifest_bytes": manifest})
        )


def test_post_load_mutation_is_detected_before_any_report(
    bundle: RecordedEvaluationBundle,
) -> None:
    object.__setattr__(bundle.dataset, "dataset_sha256", "f" * 64)
    with pytest.raises(ValueError):
        RecordedEvaluationHarness().run(bundle)


def test_errors_and_values_do_not_serialize_rejected_canaries(
    bundle: RecordedEvaluationBundle,
) -> None:
    canary = b"secret-canary-st0707-runtime"
    values = artifact_bytes(suite_registry_bytes=canary)
    with pytest.raises(RecordedAiEvaluationError) as caught:
        load_recorded_evaluation_bundle(**values)
    assert canary.decode() not in f"{caught.value!s} {caught.value!r}"
    with pytest.raises(TypeError):
        pickle.dumps(caught.value)
    report = RecordedEvaluationHarness().run(bundle)
    assert canary.decode() not in f"{report!s} {report!r}"
    with pytest.raises(TypeError):
        pickle.dumps(report)


def test_runtime_modules_expose_no_live_provider_or_operational_capability() -> None:
    files = (
        ROOT / "python/raos/domain/ai/evaluation_harness.py",
        ROOT / "python/raos/application/ai/evaluation_harness.py",
        ROOT / "python/raos/adapters/recorded_ai_evaluation.py",
        ROOT / "python/raos/ports/ai_evaluation.py",
    )
    forbidden_import_roots = {
        "openai",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "sqlalchemy",
        "psycopg",
    }
    forbidden_calls = {
        "open",
        "exec",
        "eval",
        "compile",
        "system",
        "popen",
        "remove",
        "unlink",
        "write_text",
        "write_bytes",
    }
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in forbidden_import_roots
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_import_roots
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr == "compile" and isinstance(
                        node.func.value, ast.Name
                    ):
                        assert node.func.value.id == "re"
                    else:
                        assert node.func.attr not in forbidden_calls


def test_public_runner_surface_cannot_activate_release_or_call_a_model() -> None:
    public = {
        name
        for name, value in inspect.getmembers(
            RecordedEvaluationHarness, predicate=inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert public == {"run"}
