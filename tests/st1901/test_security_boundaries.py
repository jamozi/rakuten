"""Static and runtime trust-boundary checks for ST-1901."""

from __future__ import annotations

import ast
import json
import pickle

import pytest

from .support import FIXTURE_PATH, REPOSITORY_ROOT, load_batch
from raos.application.ai.model_judge_calibration import ModelJudgeCalibrationHarness
from raos.domain.ai.model_judge_calibration import (
    ModelJudgeCalibrationError,
    ModelJudgeCalibrationFailureCode,
    ModelJudgeCalibrationScope,
    fail_calibration,
)


RUNTIME_FILES = (
    "python/raos/domain/ai/model_judge_calibration.py",
    "python/raos/ports/model_judge_calibration.py",
    "python/raos/application/ai/model_judge_calibration.py",
    "python/raos/adapters/recorded_model_judge_calibration.py",
)


def test_runtime_has_no_network_provider_credential_or_persistence_imports() -> None:
    forbidden_roots = {
        "aiohttp",
        "boto3",
        "httpx",
        "openai",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib3",
    }
    forbidden_calls = {"open", "exec", "eval", "compile", "input"}
    for raw_path in RUNTIME_FILES:
        tree = ast.parse((REPOSITORY_ROOT / raw_path).read_text())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module.split(".")[0])
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert imports.isdisjoint(forbidden_roots)
        assert calls.isdisjoint(forbidden_calls)


def test_runtime_scope_has_no_live_or_release_state() -> None:
    values = {item.value for item in ModelJudgeCalibrationScope}
    assert values == {"DISABLED", "RECORDED_SYNTHETIC_CALIBRATION_ONLY"}
    assert not any(
        fragment in value
        for value in values
        for fragment in ("LIVE", "ENABLED", "PRODUCTION", "RELEASE")
    )


def test_fixture_contains_only_opaque_labels_and_zero_privacy_flags() -> None:
    fixture = json.loads((REPOSITORY_ROOT / FIXTURE_PATH).read_bytes())
    dataset = fixture["dataset"]
    assert set(dataset["privacy"].values()) == {False}
    forbidden = {
        "prompt",
        "source",
        "output",
        "rationale",
        "review_body",
        "credential",
        "secret",
        "email",
        "url",
        "price",
        "reward",
        "epc",
        "rpm",
        "profit",
        "model_name",
        "provider_name",
    }
    for case in dataset["cases"]:
        assert forbidden.isdisjoint(case)


def test_report_is_summary_only_and_contains_no_labels_or_provider_identity() -> None:
    report = ModelJudgeCalibrationHarness().evaluate(load_batch())
    document = json.loads(report.canonical_bytes())
    forbidden = {
        "cases",
        "labels",
        "prompt",
        "source",
        "output",
        "rationale",
        "provider",
        "model",
        "credential",
        "personal_data",
        "affiliate_economics",
    }
    assert forbidden.isdisjoint(document)
    assert document["decision"]["authority"] == "NONE"
    assert document["decision"]["external_action_count"] == 0


def test_failure_is_redacted_and_nonserializable() -> None:
    with pytest.raises(ModelJudgeCalibrationError) as captured:
        fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_VALUE)
    failure = captured.value
    assert str(failure) == "INVALID_MODEL_JUDGE_CALIBRATION_VALUE"
    assert "secret" not in repr(failure).lower()
    with pytest.raises(TypeError):
        pickle.dumps(failure)
