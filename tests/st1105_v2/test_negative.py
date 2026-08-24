from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_st1105_admin_visual_accessibility as owner


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def test_source_hash_drift_is_rejected(isolated_root: Path) -> None:
    path = isolated_root / owner.SCREEN_CATALOG_PATH
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(owner.BuildError, match="SOURCE_HASH_DRIFT"):
        owner.build_projection(isolated_root)


def test_unknown_screen_mapping_is_rejected(isolated_root: Path) -> None:
    path = isolated_root / owner.CONTRACT_PATH
    contract = json.loads(path.read_text("utf-8"))
    contract["critical_workflow_mappings"][0]["screen_ids"].append("NOPE-999")
    write_json(path, contract)
    with pytest.raises(owner.BuildError, match="WORKFLOW_SCOPE_INVALID"):
        owner.build_projection(isolated_root)


def test_duplicate_json_key_and_non_finite_number_are_rejected(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"story_id":"ST-1105","story_id":"ST-0000"}\n', "utf-8")
    with pytest.raises(owner.BuildError, match="JSON_DUPLICATE_KEY"):
        owner.load_json(tmp_path, Path("duplicate.json"))
    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value":NaN}\n', "utf-8")
    with pytest.raises(owner.BuildError, match="JSON_NON_FINITE_NUMBER"):
        owner.load_json(tmp_path, Path("non-finite.json"))


def test_symlink_and_hardlink_inputs_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}\n", "utf-8")
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(owner.BuildError, match="SYMLINK_REJECTED"):
        owner.read_regular(tmp_path, Path("symlink.json"))
    hardlink = tmp_path / "hardlink.json"
    os.link(target, hardlink)
    with pytest.raises(owner.BuildError, match="INPUT_INVALID"):
        owner.read_regular(tmp_path, Path("hardlink.json"))
