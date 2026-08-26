"""Deterministic plugin package and runtime-manifest checks."""

from __future__ import annotations

import ast
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

from scripts import build_st1506_wordpress_operator as builder


ROOT = Path(__file__).resolve().parents[2]


def _snapshot(paths: tuple[Path, ...]) -> dict[Path, tuple[bytes, int, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
        for path in paths
    }


def test_plugin_package_is_byte_deterministic_and_exact() -> None:
    first = builder.build_package()
    second = builder.build_package()
    assert first == second
    assert 1 <= len(first) <= builder.MAX_PACKAGE_BYTES
    with zipfile.ZipFile(io.BytesIO(first), "r") as archive:
        names = [
            f"{builder.PLUGIN_SLUG}/{relative}" for relative in builder.PLUGIN_FILES
        ]
        assert archive.namelist() == names
        for name in names:
            info = archive.getinfo(name)
            source = builder.PLUGIN_ROOT / name.split("/", 1)[1]
            assert archive.read(name) == source.read_bytes()
            assert info.date_time == builder.ZIP_TIMESTAMP
            assert info.compress_type == zipfile.ZIP_STORED
            assert stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG
            assert stat.S_IMODE(info.external_attr >> 16) == 0o644
            assert not stat.S_ISLNK(info.external_attr >> 16)


def test_runtime_manifest_tracks_sources_semantically() -> None:
    expected = builder.build_manifest()
    assert builder.MANIFEST_PATH.read_bytes() == expected
    manifest = json.loads(expected)
    assert manifest["schema"] == (
        "RAOS_SELF_HOSTED_WORDPRESS_OPERATOR_RUNTIME_MANIFEST_V1"
    )
    assert manifest["story_id"] == "ST-1506"
    assert manifest["slice_id"] == "SELF_HOSTED_WORDPRESS_OPERATOR_BRIDGE_V1"
    assert manifest["canonical_package_modified"] is False
    assert manifest["publication_authority"] == "NONE"
    assert manifest["writes_default"] == "DISABLED"
    assert manifest["external_action_authority"] == (
        "INDEPENDENT_HUMAN_APPROVAL_ONLY"
    )
    assert manifest["supported_mutations"] == [
        "APPLY_YOAST_PROFILE",
        "UPDATE_CHILD_THEME",
    ]
    assert [row["path"] for row in manifest["semantic_inputs"]] == list(
        builder.RUNTIME_PATHS
    )
    assert all(
        row == {"path": row["path"], "semantic_id": row["path"], "version": 1}
        for row in manifest["semantic_inputs"]
    )
    package = builder.build_package()
    assert manifest["package"] == {
        "bytes": len(package),
        "compression": "ZIP_STORED",
        "file_count": len(builder.PLUGIN_FILES),
        "root": "raos-bounded-operator/",
        "sha256": hashlib.sha256(package).hexdigest(),
        "version": "1.0.0",
    }


def test_manifest_check_is_read_only() -> None:
    paths = (builder.MANIFEST_PATH,) + tuple(
        ROOT / relative for relative in builder.RUNTIME_PATHS
    )
    before = _snapshot(paths)
    assert builder.main(["--check"]) == 0
    assert _snapshot(paths) == before


def test_builder_has_no_network_process_or_live_wordpress_surface() -> None:
    path = ROOT / "scripts/build_st1506_wordpress_operator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert not imported & {
        "http",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    assert not calls & {
        "Popen",
        "run",
        "system",
        "urlopen",
    }


def test_source_validator_rejects_an_extra_plugin_file(
    tmp_path: Path, monkeypatch: object
) -> None:
    plugin_root = tmp_path / builder.PLUGIN_SLUG
    plugin_root.mkdir()
    for relative in builder.PLUGIN_FILES:
        source = builder.PLUGIN_ROOT / relative
        (plugin_root / relative).write_bytes(source.read_bytes())
    (plugin_root / "unexpected.php").write_text("<?php\n", encoding="utf-8")
    monkeypatch.setattr(builder, "PLUGIN_ROOT", plugin_root)  # type: ignore[attr-defined]
    try:
        builder.validate_sources()
    except builder.WordPressOperatorBuildFailure as error:
        assert str(error) == "ST1506_WORDPRESS_OPERATOR_PLUGIN_TREE_INVALID"
    else:
        raise AssertionError("unexpected plugin file was accepted")
