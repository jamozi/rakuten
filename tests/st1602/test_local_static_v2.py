"""Static trust-boundary and no-external-action checks for ST-1602 V2."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts import build_st1602_slo_alert_runtime as generator


RUNTIME_PATHS = (
    generator.DOMAIN_PATH,
    generator.PORT_PATH,
    generator.APPLICATION_PATH,
    generator.ADAPTER_PATH,
)


def _tree(path: Path) -> ast.Module:
    return ast.parse((generator.REPO_ROOT / path).read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_runtime_has_no_network_provider_credential_or_ambient_environment_import() -> (
    None
):
    imports: set[str] = set()
    for path in RUNTIME_PATHS:
        imports.update(_imports(path))
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "logging",
        "openai",
        "opentelemetry",
        "requests",
        "smtplib",
        "socket",
        "subprocess",
        "urllib",
    }
    assert not {name for name in imports if name.partition(".")[0] in forbidden}
    source = "\n".join(
        (generator.REPO_ROOT / path).read_text(encoding="utf-8")
        for path in RUNTIME_PATHS
    )
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert "getenv(" not in source


def test_no_loop_background_task_or_external_delivery_call_surface() -> None:
    forbidden_calls = {
        "Thread",
        "Timer",
        "create_task",
        "publish",
        "request",
        "send",
        "sendmail",
        "sleep",
        "start",
        "urlopen",
    }
    for path in RUNTIME_PATHS:
        tree = _tree(path)
        assert not any(
            isinstance(node, (ast.AsyncFor, ast.AsyncFunctionDef, ast.While))
            for node in ast.walk(tree)
        )
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert calls.isdisjoint(forbidden_calls)


def test_active_workflow_tree_uses_one_final_integration_gate() -> None:
    workflow = (generator.REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    assert "name: Final Integration" in workflow
    assert "needs: [lock, static, tests, contracts, data, storage, secrets]" in workflow
    assert "required approval" not in workflow.casefold()


def test_story_surfaces_exclude_finance_ranking_article_and_publication_inputs() -> (
    None
):
    constructors = (generator.DOMAIN_PATH, generator.PORT_PATH)
    source = "\n".join(
        (generator.REPO_ROOT / path).read_text(encoding="utf-8").lower()
        for path in constructors
    )
    forbidden = (
        "affiliate_rate",
        "commission",
        "epc",
        "profit",
        "recommendation_rank",
        "article_html",
        "publish_article",
    )
    assert all(term not in source for term in forbidden)


def test_story_ids_are_tracking_metadata_not_change_boundaries() -> None:
    policy = (generator.REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Story ID は要求・依存・status の追跡に使う" in policy
    assert "commit、branch、PR、実装 slice の境界にはしない" in policy
