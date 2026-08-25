"""Owner-generator checks for the ST-1103 V2 recorded workspace."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/build_st1103_freshness_operations_workspace.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("st1103_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_artifacts_match_owner_bytes() -> None:
    module = _module()
    artifacts = module.expected_artifacts(ROOT)
    assert tuple(path.as_posix() for path, _payload in artifacts) == (
        "changes/st-1103/freshness-operations-recorded.v2.json",
        "packages/web-ui/src/freshness-operations-recorded.v2.ts",
        "changes/st-1103/runtime-manifest.v2.yaml",
    )
    for relative, expected in artifacts:
        assert (ROOT / relative).read_bytes() == expected
    module.build(ROOT, check=True)


def test_fixture_is_exact_bounded_recorded_projection() -> None:
    module = _module()
    fixture_path, fixture = module.expected_artifacts(ROOT)[0]
    assert fixture_path.as_posix().endswith("recorded.v2.json")
    parsed = json.loads(fixture)
    assert parsed["environment"] == "CI"
    assert tuple(parsed["projections"]) == module.SCREEN_ORDER
    assert len(fixture) < module.MAX_GENERATED_BYTES
    assert hashlib.sha256(fixture).hexdigest() in (
        ROOT / "packages/web-ui/src/freshness-operations-recorded.v2.ts"
    ).read_text(encoding="ascii")
    assert all(
        projection["unknownAsZeroAllowed"] is False
        and projection["rawPayloadPresent"] is False
        for projection in parsed["projections"].values()
    )


def test_unknown_cli_argument_fails_without_writing() -> None:
    module = _module()
    before = tuple((ROOT / path).read_bytes() for path in module.GENERATED_PATHS)
    assert module.main(["--unknown"]) == 2
    after = tuple((ROOT / path).read_bytes() for path in module.GENERATED_PATHS)
    assert after == before
