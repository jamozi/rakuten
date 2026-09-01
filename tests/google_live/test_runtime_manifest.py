from __future__ import annotations

import json
from pathlib import Path

from scripts import build_google_live_runtime_v1 as build
from scripts.raos_build_core import discover_registry


ROOT = Path(__file__).resolve().parents[2]


def test_google_live_runtime_manifest_is_current_and_owner_discoverable() -> None:
    manifest = json.loads((ROOT / build.OUTPUT_PATH).read_text(encoding="utf-8"))
    assert manifest == build.document()
    assert manifest["provider_mode"] == "OWNER_PRIVATE_READ_ONLY"
    assert manifest["credential_material_tracked"] is False
    assert manifest["raw_gsc_queries_tracked"] is False
    assert Path("scripts/raos_google_owner_private_v1.py") in build.RUNTIME_INPUT_PATHS

    owner = discover_registry()["build_google_live_runtime_v1"]
    assert owner.outputs == (build.OUTPUT_PATH,)
    assert owner.test_paths == (Path("tests/google_live"),)
    assert "build_st0301_migration_framework" in owner.owner_dependencies
