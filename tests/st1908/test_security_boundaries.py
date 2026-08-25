"""Capability and data-minimization tests for ST-1908."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from raos.application.ai.fine_tuning_evaluation import (
    FineTuningEvaluationService,
)
from raos.domain.ai.fine_tuning_evaluation import FineTuningEvaluationReport
from tests.st1908.support import ROOT


RUNTIME_PATHS = (
    Path("python/raos/domain/ai/fine_tuning_evaluation.py"),
    Path("python/raos/ports/fine_tuning_evaluation.py"),
    Path("python/raos/application/ai/fine_tuning_evaluation.py"),
    Path("python/raos/adapters/recorded_fine_tuning_evaluation.py"),
)


def _public_methods(value: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(value, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_runtime_has_no_network_provider_persistence_or_process_capability() -> None:
    forbidden_imports = {
        "boto3",
        "httpx",
        "openai",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {
        "connect",
        "exec",
        "eval",
        "open",
        "popen",
        "remove",
        "run",
        "system",
        "unlink",
        "write",
        "write_bytes",
        "write_text",
    }
    for relative in RUNTIME_PATHS:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".")[0] not in forbidden_imports
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_imports
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in forbidden_calls


def test_public_surfaces_have_no_training_activation_or_mutation_method() -> None:
    assert _public_methods(FineTuningEvaluationService) == {"evaluate"}
    report_methods = _public_methods(FineTuningEvaluationReport)
    assert report_methods == {"canonical_bytes", "payload"}
    forbidden_fragments = {
        "activate",
        "approve",
        "deploy",
        "fine_tune",
        "mutate",
        "publish",
        "release",
        "train",
        "write",
    }
    for methods in (
        _public_methods(FineTuningEvaluationService),
        report_methods,
    ):
        assert not {
            method
            for method in methods
            if any(fragment in method for fragment in forbidden_fragments)
        }


def test_runtime_source_contains_no_affiliate_economic_or_publication_input() -> None:
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower() for path in RUNTIME_PATHS
    )
    for prohibited in (
        "affiliate_commission",
        "confirmed_reward",
        "unattributed_reward",
        "recommendation_score",
        "recommendation_rank",
        "publication_snapshot_id",
        "api_key",
        "secret://",
        "https://",
    ):
        assert prohibited not in text
