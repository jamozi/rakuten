from __future__ import annotations

import ast
from dataclasses import fields
import json
from pathlib import Path

from raos.domain.publishing.partial_auto_publication import (
    PartialAutoPublicationCommand,
)
from scripts import build_st1903_partial_auto_publication as builder


RUNTIME_PATHS = (
    Path("python/raos/domain/publishing/partial_auto_publication.py"),
    Path("python/raos/ports/publishing/partial_auto_publication.py"),
    Path("python/raos/application/publishing/partial_auto_publication.py"),
    Path("python/raos/adapters/publishing/recorded_partial_auto_publication.py"),
)


def test_runtime_has_no_network_provider_cms_or_process_capability() -> None:
    forbidden = {
        "boto3",
        "http.client",
        "httpx",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    observed: set[str] = set()
    for relative in RUNTIME_PATHS:
        tree = ast.parse((builder.REPO_ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                observed.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                observed.add(node.module)
    assert forbidden.isdisjoint(observed)


def test_command_has_no_url_html_cms_credential_or_publication_payload() -> None:
    names = {field.name for field in fields(PartialAutoPublicationCommand)}
    assert names == {
        "parser_version",
        "recording_id",
        "release_decision_sha256",
        "scope",
        "source_bytes",
        "source_sha256",
    }
    forbidden_fragments = ("url", "html", "cms", "credential", "body", "payload")
    assert not any(
        fragment in name for name in names for fragment in forbidden_fragments
    )


def test_fixture_and_report_have_no_secret_or_finance_value_fields() -> None:
    fixture = (builder.REPO_ROOT / builder.FIXTURE_PATH).read_bytes().lower()
    report = builder.build_report().lower()
    forbidden = (
        b'"cookie"',
        b'"email"',
        b'"password"',
        b'"secret"',
        b'"token"',
        b'"reward_jpy"',
        b'"commission"',
        b'"epc"',
        b'"rpm"',
        b'"profit_jpy"',
        b'"article_body"',
        b'"html"',
        b'"cms_payload"',
    )
    assert all(value not in fixture for value in forbidden)
    assert all(value not in report for value in forbidden)
    parsed = json.loads(report)
    assert parsed["actions"] == parsed["effects"] == []
    assert parsed["authority"]["public_write"] is False


def test_story_inventory_never_includes_playwright_artifacts() -> None:
    assert all(
        ".playwright-cli" not in path.as_posix() for path in builder.OWNED_SOURCE_PATHS
    )
