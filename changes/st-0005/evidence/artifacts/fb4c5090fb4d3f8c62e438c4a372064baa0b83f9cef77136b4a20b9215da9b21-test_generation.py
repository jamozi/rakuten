"""Deterministic and fail-closed ST-0301 generator tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st0301_migration_framework as generator
from scripts import build_st0302_foundation as successor
from scripts import build_st0305_publication_analytics_finance as active_successor


def test_frozen_predecessor_outputs_are_parseable_and_hash_pinned() -> None:
    catalog_bytes = (REPOSITORY_ROOT / generator.CATALOG_PATH).read_bytes()
    manifest_bytes = (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_bytes()
    catalog = json.loads(catalog_bytes)
    manifest = yaml.safe_load(manifest_bytes)

    assert hashlib.sha256(catalog_bytes).hexdigest() == (
        "07de505a2dc75c8c06046dd1a588ff414c11ee21e1be07cbedf8e206c92d1e09"
    )
    assert hashlib.sha256(manifest_bytes).hexdigest() == (
        "287d1f365523f39bb7b28535680317103cb6abad5d5b3f5e4db4bc60250eb2ff"
    )
    assert catalog["revision_graph"]["head"] == "202608030001"
    assert catalog["revision_graph"]["revisions"][0]["runner_version"] == "1.0.0"
    assert catalog["revision_graph"]["revisions"][0]["server_version_num"] == 180004
    assert catalog["deferred_checkpoints"]["execution"] == "DISABLED"
    assert len(catalog["deferred_checkpoints"]["entries"]) == 18
    assert manifest["source_artifact_count"] == 58
    assert manifest["generated_artifact_count"] == 1


def test_legacy_entrypoint_delegates_to_active_cumulative_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[list[str] | None] = []
    monkeypatch.setattr(successor, "main", lambda argv=None: observed.append(argv) or 0)

    assert generator.main(["--check"]) == 0
    assert observed == [["--check"]]


def test_manifest_source_inventory_is_exact_and_unique() -> None:
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    )
    observed = [item["uri"] for item in manifest["source_artifacts"]]

    assert len(observed) == len(set(observed))
    assert len(observed) == manifest["source_artifact_count"] == 58
    assert not any(uri.startswith("repo://zip/") for uri in observed)
    assert not any(uri.startswith("repo://docs/canonical/") for uri in observed)
    assert not any(uri.startswith("repo://docs/upstream/") for uri in observed)


def test_manifest_pins_every_direct_dependency_and_predecessor() -> None:
    manifest = yaml.safe_load(
        (REPOSITORY_ROOT / generator.MANIFEST_PATH).read_text(encoding="utf-8")
    )
    dependencies = manifest["provenance"]["dependency_manifests"]

    assert [item["story_id"] for item in dependencies] == [
        "ST-0201",
        "ST-0002",
        "ST-0003",
        "ST-0004",
    ]
    assert manifest["provenance"]["predecessor_manifest"] == {
        "story_id": "ST-0204",
        "uri": "repo://changes/st-0204/manifest.yaml",
        "sha256": generator.EXPECTED_PREDECESSOR_SHA256,
    }


def test_source_or_dependency_drift_fails_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_hash = generator.shared.sha256_file

    def drift(path: Path) -> str:
        if path == REPOSITORY_ROOT / generator.PREDECESSOR_PATH:
            return "0" * 64
        return real_hash(path)

    monkeypatch.setattr(generator.shared, "sha256_file", drift)
    with pytest.raises(RuntimeError, match="predecessor manifest digest"):
        generator.render_catalog()


def test_contract_checkpoint_execution_cannot_be_enabled(
    migration_contract: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mutated = dict(migration_contract)
    mutated["checkpoint_catalog"] = dict(mutated["checkpoint_catalog"])  # type: ignore[arg-type]
    mutated["checkpoint_catalog"]["execution"] = "ENABLED"  # type: ignore[index]
    real_load = generator.shared.load_yaml

    def load(path: Path):
        if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
            return mutated
        return real_load(path)

    monkeypatch.setattr(generator.shared, "load_yaml", load)
    with pytest.raises(RuntimeError, match="must remain disabled"):
        generator.load_and_validate_contract()


def test_contract_revision_runtime_metadata_cannot_drift(
    migration_contract: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mutated = dict(migration_contract)
    revision_chain = dict(mutated["revision_chain"])  # type: ignore[arg-type]
    revisions = [dict(item) for item in revision_chain["revisions"]]
    revisions[0]["runner_version"] = "9.9.9"
    revision_chain["revisions"] = revisions
    mutated["revision_chain"] = revision_chain
    real_load = generator.shared.load_yaml

    def load(path: Path):
        if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
            return mutated
        return real_load(path)

    monkeypatch.setattr(generator.shared, "load_yaml", load)
    with pytest.raises(RuntimeError, match="revision catalog differs"):
        generator.load_and_validate_contract()


def test_wrong_tool_version_fails_before_repository_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verification_calls: list[Path] = []
    real_version = generator.importlib.metadata.version

    def version(name: str) -> str:
        if name == "alembic":
            return "0.0.0"
        return real_version(name)

    monkeypatch.setattr(generator.importlib.metadata, "version", version)
    monkeypatch.setattr(
        generator,
        "verify_repository",
        lambda root: verification_calls.append(root),
    )
    with pytest.raises(RuntimeError, match="toolchain"):
        generator.render_catalog()
    assert verification_calls == []


def test_check_mode_never_installs(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[Path] = []
    monkeypatch.setattr(active_successor, "check_generated", lambda: None)
    monkeypatch.setattr(
        active_successor,
        "install_generated",
        lambda root=active_successor.REPO_ROOT: writes.append(root),
    )

    assert generator.main(["--check"]) == 0
    assert writes == []


def test_install_rejects_symlink_target(tmp_path: Path) -> None:
    target = tmp_path / generator.CATALOG_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    target.symlink_to(outside)

    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator._install(generator.CATALOG_PATH, b"candidate", tmp_path)
    assert outside.read_bytes() == b"unchanged"


def test_install_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    changes = tmp_path / "changes"
    changes.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        generator._install(generator.CATALOG_PATH, b"candidate", tmp_path)
    assert list(outside.iterdir()) == []


def test_install_writes_exact_bytes_and_safe_mode(tmp_path: Path) -> None:
    generator._install(generator.CATALOG_PATH, b"candidate\n", tmp_path)
    target = tmp_path / generator.CATALOG_PATH

    assert target.read_bytes() == b"candidate\n"
    assert target.stat().st_mode & 0o022 == 0
