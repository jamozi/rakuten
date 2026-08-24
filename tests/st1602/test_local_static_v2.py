"""Static trust-boundary and no-external-action checks for ST-1602 V2."""

from __future__ import annotations

import ast
import hashlib
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


def test_active_workflow_tree_matches_exact_pre_story_base() -> None:
    digest = hashlib.sha256()
    for path in sorted((generator.REPO_ROOT / ".github/workflows").rglob("*")):
        if path.is_file():
            relative = path.relative_to(generator.REPO_ROOT).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    assert (
        digest.hexdigest()
        == "1f4df3af36bac255dd37c2815d866657656be1534b3a91e4dbbfa91f8657ada8"
    )


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


def test_only_story_owned_paths_are_changed_against_exact_base() -> None:
    import subprocess

    changed = subprocess.run(
        ["git", "diff", "--name-only", "9470434d6c4ad3c80254ea16a3879544ff5d670a"],
        cwd=generator.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=generator.REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    output = sorted(set(changed) | set(untracked))
    assert output
    allowed_prefixes = (
        "changes/st-1602/",
        "python/raos/domain/ops/slo_alert_runtime_v2.py",
        "python/raos/ports/slo_alert_runtime_v2.py",
        "python/raos/application/ops/slo_alert_runtime_v2.py",
        "python/raos/adapters/recorded_slo_alert_runtime_v2.py",
        "scripts/build_st1602_",
        "tests/st1602/",
    )
    assert all(path.startswith(allowed_prefixes) for path in output)
