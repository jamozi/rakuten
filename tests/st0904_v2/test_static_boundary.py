from __future__ import annotations

import ast
import json
from pathlib import Path

from .support import read
from scripts import build_st0904_public_projection_runtime_v2 as generator


_RUNTIME_PATHS = (
    Path("python/raos/domain/publishing/public_projection_v2.py"),
    Path("python/raos/ports/public_projection_v2.py"),
    Path("python/raos/application/publishing/public_projection_v2.py"),
    Path("python/raos/adapters/recorded_public_projection_v2.py"),
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


def test_generated_public_projection_has_no_internal_or_finance_material() -> None:
    document = json.loads(read(generator.FIXTURE_PATH))
    projection = document["output"]["projection"]
    serialized = json.dumps(projection, ensure_ascii=False).casefold()
    for token in (
        "approval_ids",
        "article_version_id",
        "claim_ids",
        "commission",
        "epc",
        "evidence",
        "finance",
        "input_hashes",
        "profit",
        "quality_result_id",
        "recommendation_ref",
        "revenue",
        "rpm",
        "secret",
        "source_packet_version_ref",
    ):
        assert token not in serialized


def test_generated_fixture_keeps_every_action_disabled() -> None:
    authority = json.loads(read(generator.FIXTURE_PATH))["authority"]
    assert authority["database_write"] is False
    assert authority["network"] is False
    assert authority["route_activated"] is False
    assert authority["public_read_served"] is False
    assert authority["public_projection_authorized"] is False
    assert authority["publication_authorized"] is False
    assert authority["release_authorized"] is False
    assert authority["production_authorized"] is False


def test_canonical_story_dependencies_remain_exact() -> None:
    backlog = read(
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
    ).decode("utf-8")
    marker = backlog.index("- id: ST-0904")
    section = backlog[marker : marker + 900]
    assert "- ST-0903" in section
    assert "- ST-0306" in section
    assert "- TST-011" in section
    assert "- TST-021" in section
