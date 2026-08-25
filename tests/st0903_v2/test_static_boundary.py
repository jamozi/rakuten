from __future__ import annotations

import ast
import json
from pathlib import Path

from .conftest import read
from scripts import build_st0903_publication_snapshot_runtime_v2 as generator


_RUNTIME_PATHS = (
    Path("python/raos/domain/publishing/publication_snapshot_v2.py"),
    Path("python/raos/ports/publication_snapshot_v2.py"),
    Path("python/raos/application/publishing/publication_snapshot_v2.py"),
    Path("python/raos/adapters/recorded_publication_snapshot_v2.py"),
)
_FORBIDDEN_IMPORT_ROOTS = {
    "boto3",
    "django",
    "flask",
    "httpx",
    "requests",
    "socket",
    "sqlalchemy",
    "urllib",
}


def test_runtime_has_no_network_database_or_cms_import() -> None:
    for path in _RUNTIME_PATHS:
        tree = ast.parse(read(path), filename=path.as_posix())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                assert roots.isdisjoint(_FORBIDDEN_IMPORT_ROOTS)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                assert node.module.split(".")[0] not in _FORBIDDEN_IMPORT_ROOTS


def test_generated_snapshot_contains_no_sensitive_or_finance_material() -> None:
    document = json.loads(read(generator.FIXTURE_PATH))
    snapshot = document["output"]["snapshot"]
    serialized = json.dumps(snapshot, ensure_ascii=False).casefold()
    for token in (
        "credential",
        "password",
        "secret",
        "raw_prompt",
        "source_uri",
        "affiliate_rate",
        "commission",
        "epc",
        "finance",
        "profit",
        "revenue",
        "rpm",
    ):
        assert token not in serialized


def test_generated_snapshot_keeps_all_publication_authority_outside_payload() -> None:
    document = json.loads(read(generator.FIXTURE_PATH))
    snapshot = document["output"]["snapshot"]
    assert "publication_authorized" not in snapshot
    assert "production_authorized" not in snapshot
    authority = document["authority"]
    assert authority["external_write"] is False
    assert authority["publication_authorized"] is False
    assert authority["production_authorized"] is False


def test_canonical_story_dependencies_remain_exact() -> None:
    backlog = read(
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
    ).decode("utf-8")
    marker = backlog.index("- id: ST-0903")
    section = backlog[marker : marker + 1800]
    assert "- ST-0902" in section
    assert "- ST-0807" in section
    assert "- ST-0808" in section
