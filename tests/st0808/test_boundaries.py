"""Static architecture and forbidden-capability checks for ST-0808."""

from __future__ import annotations

import ast
from pathlib import Path

from raos.domain.editorial.media_asset import AdminOnlyMediaAssetReference


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    ROOT / "python/raos/domain/editorial/media_asset.py",
    ROOT / "python/raos/ports/media_asset.py",
    ROOT / "python/raos/application/editorial/media_asset.py",
    ROOT / "python/raos/adapters/recorded_media_asset.py",
)


def _trees() -> list[ast.AST]:
    return [ast.parse(path.read_text(encoding="utf-8")) for path in SOURCES]


def test_source_files_parse() -> None:
    assert len(_trees()) == 4


def test_no_forbidden_import_capability() -> None:
    forbidden = {
        "boto3",
        "botocore",
        "http",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    imported: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)


def test_no_io_or_external_action_calls() -> None:
    forbidden = {
        "open",
        "getenv",
        "put",
        "get",
        "head",
        "read",
        "write",
        "delete",
        "upload",
        "download",
        "publish",
        "render",
        "request",
        "send",
        "commit",
        "save",
    }
    calls: set[str] = set()
    for tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
    assert calls.isdisjoint(forbidden)


def test_admin_reference_has_no_locator_or_content_surface() -> None:
    assert set(AdminOnlyMediaAssetReference.__dataclass_fields__) == {
        "asset_id",
        "visibility",
    }
    text = "\n".join(path.read_text(encoding="utf-8") for path in SOURCES)
    for forbidden in (
        "raw_bytes",
        "object_key",
        "filesystem_path",
        "public_url",
        "renderer_payload",
        "license_verified",
    ):
        assert forbidden not in text


def test_domain_imports_only_inward_predecessor_domains() -> None:
    tree = ast.parse(SOURCES[0].read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert all(
        not module.startswith(("raos.application", "raos.adapters", "raos.ports"))
        for module in imports
    )
