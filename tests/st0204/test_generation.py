"""Deterministic and symlink-safe ST-0204 artifact generation."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest
import yaml

from conftest import EXPECTED_TOOLCHAIN, TOOLCHAIN_SOURCE_PATHS
from scripts import build_st0204_config_loader as generator


class RuntimeVersion(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: str
    serial: int


def test_schema_and_manifest_rendering_are_byte_deterministic() -> None:
    assert generator.render_schema() == generator.render_schema()
    assert generator.render_manifest() == generator.render_manifest()


def test_installed_generated_artifacts_match_the_renderer() -> None:
    assert (generator.REPO_ROOT / generator.SCHEMA_PATH).read_bytes() == (
        generator.render_schema()
    )
    assert (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes() == (
        generator.render_manifest()
    )
    generator.check_generated()


def test_manifest_has_complete_unique_source_and_generated_inventories() -> None:
    manifest = yaml.safe_load(generator.render_manifest())
    sources = manifest["source_artifacts"]
    generated = manifest["generated_artifacts"]

    assert manifest["source_artifact_count"] == len(generator.SOURCE_ARTIFACT_PATHS)
    assert len(sources) == len(generator.SOURCE_ARTIFACT_PATHS)
    assert [item["uri"] for item in sources] == [
        f"repo://{path.as_posix()}" for path in generator.SOURCE_ARTIFACT_PATHS
    ]
    assert len({item["uri"] for item in sources}) == len(sources)
    assert manifest["generated_artifact_count"] == 1
    assert generated == [
        {
            "uri": f"repo://{generator.SCHEMA_PATH.as_posix()}",
            "bytes": len(generator.render_schema()),
            "sha256": generator.shared.sha256_bytes(generator.render_schema()),
        }
    ]
    assert manifest["evidence_chain"]["stories"] == [
        "ST-0201",
        "ST-0202",
        "ST-0203",
        "ST-0204",
    ]


def test_contract_and_manifest_pin_exact_runtime_toolchain_and_owning_sources(
    config_contract: dict[str, object],
) -> None:
    manifest = yaml.safe_load(generator.render_manifest())
    source_paths = set(generator.SOURCE_ARTIFACT_PATHS)
    source_uris = {item["uri"] for item in manifest["source_artifacts"]}

    assert config_contract["toolchain"] == EXPECTED_TOOLCHAIN
    assert manifest["provenance"]["toolchain"] == EXPECTED_TOOLCHAIN
    assert set(TOOLCHAIN_SOURCE_PATHS).issubset(source_paths)
    assert {f"repo://{path.as_posix()}" for path in TOOLCHAIN_SOURCE_PATHS}.issubset(
        source_uris
    )


def test_wrong_python_runtime_fails_before_schema_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_calls: list[None] = []

    def forbidden_schema_render(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        schema_calls.append(None)
        raise AssertionError("schema rendering must not start")

    monkeypatch.setattr(
        generator.sys,
        "version_info",
        RuntimeVersion(3, 14, 5, "final", 0),
    )
    monkeypatch.setattr(
        generator.RuntimeConfig,
        "model_json_schema",
        forbidden_schema_render,
    )

    with pytest.raises(RuntimeError, match="Python.*version"):
        generator.render_schema()
    assert schema_calls == []


def test_wrong_pydantic_runtime_fails_before_schema_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_calls: list[None] = []

    def forbidden_schema_render(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        schema_calls.append(None)
        raise AssertionError("schema rendering must not start")

    monkeypatch.setattr(generator.pydantic, "__version__", "2.13.3")
    monkeypatch.setattr(
        generator.RuntimeConfig,
        "model_json_schema",
        forbidden_schema_render,
    )

    with pytest.raises(RuntimeError, match="Pydantic.*version"):
        generator.render_schema()
    assert schema_calls == []


def test_wrong_pydantic_core_runtime_fails_before_schema_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_calls: list[None] = []

    def forbidden_schema_render(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        schema_calls.append(None)
        raise AssertionError("schema rendering must not start")

    monkeypatch.setattr(generator.pydantic_core, "__version__", "2.46.3")
    monkeypatch.setattr(
        generator.RuntimeConfig,
        "model_json_schema",
        forbidden_schema_render,
    )

    with pytest.raises(RuntimeError, match="pydantic-core.*version"):
        generator.render_schema()
    assert schema_calls == []


def test_wrong_pyyaml_runtime_fails_before_schema_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_calls: list[None] = []

    def forbidden_schema_render(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        schema_calls.append(None)
        raise AssertionError("schema rendering must not start")

    monkeypatch.setattr(generator.yaml, "__version__", "6.0.2")
    monkeypatch.setattr(
        generator.RuntimeConfig,
        "model_json_schema",
        forbidden_schema_render,
    )

    with pytest.raises(RuntimeError, match="PyYAML.*version"):
        generator.render_schema()
    assert schema_calls == []


def test_wrong_uv_pin_fails_before_schema_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_calls: list[None] = []
    uv_configuration = tmp_path / "uv.toml"
    uv_configuration.write_text('required-version = "==0.12.0"\n', encoding="utf-8")
    real_regular_file = generator.shared._repository_regular_file

    def repository_regular_file(
        root: Path,
        relative: Path,
        label: str,
    ) -> Path:
        if relative == generator.UV_CONFIGURATION_PATH:
            return uv_configuration
        return real_regular_file(root, relative, label)

    def forbidden_schema_render(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        schema_calls.append(None)
        raise AssertionError("schema rendering must not start")

    monkeypatch.setattr(
        generator.shared,
        "_repository_regular_file",
        repository_regular_file,
    )
    monkeypatch.setattr(
        generator.RuntimeConfig,
        "model_json_schema",
        forbidden_schema_render,
    )

    with pytest.raises(RuntimeError, match="uv required-version"):
        generator.render_schema()
    assert schema_calls == []


def test_check_mode_does_not_install_generated_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[Path] = []

    def forbidden(root: Path = generator.REPO_ROOT) -> None:
        writes.append(root)

    monkeypatch.setattr(generator, "install_generated", forbidden)
    assert generator.main(["--check"]) == 0
    assert writes == []


@pytest.mark.parametrize("relative", (generator.SCHEMA_PATH, generator.MANIFEST_PATH))
def test_install_rejects_symlink_target(tmp_path: Path, relative: Path) -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / f"outside-{relative.name}"
    outside.write_text("unchanged", encoding="utf-8")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator.install_artifact(relative, b"candidate", tmp_path)
    assert outside.read_text(encoding="utf-8") == "unchanged"


def test_install_rejects_symlink_root(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)

    with pytest.raises(RuntimeError, match="root must be a real directory"):
        generator.install_artifact(Path("target"), b"candidate", linked)


def test_held_parent_descriptor_defeats_ancestor_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path("generated/runtime-config.json")
    parent = tmp_path / relative.parent
    parent.mkdir(parents=True)
    target = parent / relative.name
    target.write_bytes(b"old")
    moved = tmp_path / "held-parent"
    outside = tmp_path / "outside"
    outside.mkdir()
    real_replace = generator.os.replace
    swapped = False

    def replace_with_swap(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        if not swapped:
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(generator.os, "replace", replace_with_swap)
    generator.install_artifact(relative, b"candidate", tmp_path)

    assert swapped is True
    assert (moved / relative.name).read_bytes() == b"candidate"
    assert not (outside / relative.name).exists()
