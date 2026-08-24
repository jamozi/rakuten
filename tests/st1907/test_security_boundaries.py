"""Static capability and data-minimization tests for ST-1907."""

from __future__ import annotations

import ast
from dataclasses import fields
import inspect
import json
from pathlib import Path

from raos.adapters.recorded_content_portfolio_optimizer import (
    RecordedContentPortfolioOptimizerSource,
)
from raos.application.portfolio.content_optimizer import (
    ContentPortfolioOptimizerService,
)
from raos.domain.portfolio.content_optimizer import (
    PortfolioOptimizationReport,
    PortfolioOptimizerCommand,
    PortfolioProposal,
)
from scripts import build_st1907_content_portfolio_optimizer as generator


RUNTIME_PATHS = (
    Path("python/raos/domain/portfolio/content_optimizer.py"),
    Path("python/raos/ports/content_portfolio_optimizer.py"),
    Path("python/raos/application/portfolio/content_optimizer.py"),
    Path("python/raos/adapters/recorded_content_portfolio_optimizer.py"),
)


def _public_methods(value: type[object]) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(value, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested for child in value.values() for nested in _all_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _all_keys(child)}
    return set()


def test_runtime_has_no_network_provider_persistence_or_process_capability() -> None:
    forbidden_imports = {
        "boto3",
        "http",
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
        tree = ast.parse((generator.REPO_ROOT / relative).read_text(encoding="utf-8"))
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


def test_public_runtime_surfaces_have_no_apply_or_publish_method() -> None:
    assert _public_methods(ContentPortfolioOptimizerService) == {"evaluate"}
    assert _public_methods(RecordedContentPortfolioOptimizerSource) == {"read"}
    assert _public_methods(PortfolioOptimizationReport) == {"payload"}
    assert _public_methods(PortfolioProposal) == {"payload"}
    methods = set().union(
        _public_methods(ContentPortfolioOptimizerService),
        _public_methods(RecordedContentPortfolioOptimizerSource),
        _public_methods(PortfolioOptimizationReport),
        _public_methods(PortfolioProposal),
    )
    forbidden_fragments = {
        "activate",
        "apply",
        "approve",
        "deploy",
        "mutate",
        "publish",
        "release",
        "write",
    }
    assert not {
        method
        for method in methods
        if any(fragment in method for fragment in forbidden_fragments)
    }


def test_command_has_no_content_provider_or_credential_payload() -> None:
    names = {field.name for field in fields(PortfolioOptimizerCommand)}
    assert names == {
        "contract_sha256",
        "expected_dependency_pack_sha256",
        "measurement_contract_sha256",
        "method_version",
        "parser_version",
        "period",
        "program",
        "recording_id",
        "release_decision_sha256",
        "scope",
        "signal_policy_sha256",
        "source_bytes",
        "source_sha256",
    }
    assert not names.intersection(
        {
            "article_html",
            "body",
            "credential",
            "cta",
            "password",
            "provider",
            "publication_snapshot",
            "secret",
            "token",
            "url",
        }
    )


def test_fixture_and_report_have_no_sensitive_finance_or_content_value_fields() -> None:
    fixture = json.loads((generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes())
    report = json.loads((generator.REPO_ROOT / generator.REPORT_PATH).read_bytes())
    keys = _all_keys(fixture) | _all_keys(report)
    assert not keys.intersection(
        {
            "affiliate_commission_rate",
            "article_body",
            "article_html",
            "commission",
            "confirmed_reward",
            "credential",
            "cta",
            "epc",
            "password",
            "profit",
            "provider_endpoint",
            "publication_snapshot",
            "reward",
            "rpm",
            "secret",
            "token",
            "unattributed_reward",
            "url",
        }
    )
    assert fixture["signals"] == []
    assert report["evaluation"]["proposals"] == []


def test_story_inventory_excludes_browser_and_foreign_story_artifacts() -> None:
    paths = {path.as_posix() for path in generator.SOURCE_ARTIFACT_PATHS}
    assert all(".playwright-cli" not in path for path in paths)
    assert all("changes/st-1903/" not in path for path in paths)
    assert all("changes/st-1904/" not in path for path in paths)
    assert all("changes/st-1105/" not in path for path in paths)
