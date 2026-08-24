"""Capability and data-minimization tests for ST-1904."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from raos.adapters.recorded_multi_category import (
    CallerBytesRecordedMultiCategorySource,
)
from raos.application.catalog.multi_category import MultiCategoryEvaluationService
from raos.domain.catalog.multi_category import MultiCategoryEvaluationReport
from tests.st1904.support import ROOT


RUNTIME_PATHS = (
    Path("python/raos/domain/catalog/multi_category.py"),
    Path("python/raos/ports/multi_category.py"),
    Path("python/raos/application/catalog/multi_category.py"),
    Path("python/raos/adapters/recorded_multi_category.py"),
)


def _public_methods(value: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(value, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_runtime_has_no_network_provider_persistence_process_or_file_capability() -> (
    None
):
    forbidden_imports = {
        "boto3",
        "httpx",
        "openai",
        "os",
        "pathlib",
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


def test_public_surfaces_have_only_read_evaluate_or_validation_methods() -> None:
    assert _public_methods(MultiCategoryEvaluationService) == {"evaluate"}
    assert _public_methods(CallerBytesRecordedMultiCategorySource) == {"read"}
    assert _public_methods(MultiCategoryEvaluationReport) == {"require_valid"}
    forbidden_fragments = {
        "activate",
        "approve",
        "deploy",
        "merge",
        "mutate",
        "publish",
        "release",
        "select",
        "split",
        "write",
    }
    methods = (
        _public_methods(MultiCategoryEvaluationService)
        | _public_methods(CallerBytesRecordedMultiCategorySource)
        | _public_methods(MultiCategoryEvaluationReport)
    )
    assert not {
        method
        for method in methods
        if any(fragment in method for fragment in forbidden_fragments)
    }


def test_runtime_source_contains_no_provider_secret_affiliate_or_url_material() -> None:
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower() for path in RUNTIME_PATHS
    )
    for prohibited in (
        "affiliate_commission",
        "api_key",
        "confirmed_reward",
        "endpoint_url",
        "epc",
        "https://",
        "profit_jpy",
        "provider_secret",
        "recommendation_score",
        "rpm",
        "secret://",
        "unattributed_reward",
    ):
        assert prohibited not in text


def test_runtime_has_no_logging_or_environment_read() -> None:
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8").lower() for path in RUNTIME_PATHS
    )
    for prohibited in (
        "logging.",
        "logger.",
        "environ[",
        "getenv(",
        "print(",
    ):
        assert prohibited not in text
