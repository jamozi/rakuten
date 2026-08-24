"""Static and denied-network authority checks for ST-0602 V2."""

from __future__ import annotations

import ast
from pathlib import Path
import socket

from raos.adapters.sqlite_fact_extraction_runtime_v2 import (
    OwnerPrivateSqliteFactExtractionStoreV2,
)
from raos.application.evidence.fact_extraction_runtime_v2 import (
    DurableFactExtractionServiceV2,
)
from tests.st0602.runtime_v2_fixtures import (
    exact_dependencies_v2,
    fact_store_v2,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATHS = (
    "python/raos/domain/evidence/fact_extraction_runtime_v2.py",
    "python/raos/ports/fact_extraction_runtime_v2.py",
    "python/raos/application/evidence/fact_extraction_runtime_v2.py",
    "python/raos/adapters/sqlite_fact_extraction_runtime_v2.py",
)


def test_runtime_imports_have_no_external_action_client() -> None:
    forbidden_roots = {
        "aiohttp",
        "boto3",
        "httpx",
        "openai",
        "playwright",
        "requests",
        "selenium",
        "urllib",
    }
    for relative in RUNTIME_PATHS:
        tree = ast.parse((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.partition(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                roots.add(node.module.partition(".")[0])
        assert roots.isdisjoint(forbidden_roots)


def test_public_surfaces_expose_no_external_or_mutating_authority() -> None:
    service_methods = {
        name for name in dir(DurableFactExtractionServiceV2) if not name.startswith("_")
    }
    store_methods = {
        name
        for name in dir(OwnerPrivateSqliteFactExtractionStoreV2)
        if not name.startswith("_")
    }
    assert service_methods == {"extract"}
    assert store_methods == {
        "commit",
        "database_path",
        "list_validations",
        "load_batch",
        "load_fact",
        "load_outbox",
        "lookup",
        "recover_exact",
        "verify_chain",
    }
    combined = " ".join(service_methods | store_methods).lower()
    for forbidden in (
        "delete",
        "deliver",
        "export",
        "live",
        "manual",
        "model",
        "network",
        "plugin",
        "provider",
        "publish",
        "rank",
        "release",
        "retention",
        "review",
        "staging",
        "update",
    ):
        assert forbidden not in combined


def test_complete_recorded_pipeline_succeeds_with_network_denied(
    tmp_path, monkeypatch
) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network action attempted")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    dependencies = exact_dependencies_v2(tmp_path)
    result = DurableFactExtractionServiceV2(fact_store_v2(tmp_path)).extract(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )
    assert result.external_action_count == 0
    assert result.provider_action_count == 0
    assert result.publication_action_count == 0
    assert result.ai_action_count == 0
