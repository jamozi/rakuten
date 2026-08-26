"""Deterministic ST-0204 generation under the shared toolchain boundary."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import build_st0204_config_loader as generator


def test_schema_and_manifest_rendering_are_byte_deterministic() -> None:
    assert generator.render_schema() == generator.render_schema()
    assert generator.render_manifest() == generator.render_manifest()


def test_installed_generated_artifacts_match_the_renderer() -> None:
    assert (generator.REPO_ROOT / generator.SCHEMA_PATH).read_bytes() == generator.render_schema()
    assert (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes() == generator.render_manifest()
    generator.check_generated()


def test_manifest_has_unique_semantic_source_inventory_and_owned_output() -> None:
    manifest = yaml.safe_load(generator.render_manifest())
    sources = manifest["source_artifacts"]
    assert len(sources) == len(generator.SOURCE_ARTIFACT_PATHS)
    assert len({item["uri"] for item in sources}) == len(sources)
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.SCHEMA_PATH.as_posix()}",
            "bytes": len(generator.render_schema()),
            "sha256": generator.shared.sha256_bytes(generator.render_schema()),
        }
    ]


def test_normal_generation_does_not_reverify_exact_tool_versions() -> None:
    source = Path(generator.__file__).read_text(encoding="utf-8")
    assert "def assert_generation_toolchain" in source
    assert "Tool versions are verified once by setup/final" in source
    assert "importlib.metadata.version" not in source
    assert generator.render_schema()


def test_schema_is_valid_json_and_keeps_the_runtime_identity() -> None:
    schema = json.loads(generator.render_schema())
    assert schema["title"] == "RuntimeConfig"
    assert schema["type"] == "object"
