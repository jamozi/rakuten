"""Source pin, generation, ownership, and drift checks for ST-0104."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from .support import (
    INSTALLER_PATH,
    MANIFEST_NAME,
    REPO_ROOT,
    SOURCE_ROOT,
    VERSION_ROOT,
)


SOURCE_MANIFEST_SHA256 = (
    "5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458"
)
ROOT_README_SHA256 = "6ea0bb1d89007cf3a8cae6109d50963859ce764e05198a5b05c2a014733e5951"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        candidate for candidate in root.rglob("*") if candidate.is_file()
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def load_manifest(root: Path = VERSION_ROOT) -> dict[str, Any]:
    loaded = json.loads((root / MANIFEST_NAME).read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def copy_version(tmp_path: Path) -> Path:
    target = tmp_path / "raos-v0.4"
    shutil.copytree(VERSION_ROOT, target)
    return target


def test_pinned_source_bundle_is_complete(installer_module: ModuleType) -> None:
    assert sha256(SOURCE_ROOT / "manifest.yaml") == SOURCE_MANIFEST_SHA256
    artifacts = installer_module.verify_source_bundle()
    assert len(artifacts) == 306
    assert tuple(item.path for item in artifacts) == tuple(
        sorted(item.path for item in artifacts)
    )
    assert len({item.path.casefold() for item in artifacts}) == 306
    assert artifacts[-1].path == "job-state.v1.yaml"

    counts = Counter(Path(item.path).suffix for item in artifacts)
    assert counts == Counter({".json": 244, ".yaml": 48, ".md": 12, ".csv": 2})
    contract_yaml = [
        item
        for item in artifacts
        if item.path.startswith("contracts/") and item.path.endswith(".yaml")
    ]
    assert len(contract_yaml) == 47


def test_installed_manifest_has_exact_canonical_contract() -> None:
    manifest = load_manifest()
    assert set(manifest) == {
        "document",
        "provenance",
        "inventory",
        "schema_resolution",
        "artifact_count",
        "artifacts",
    }
    assert manifest["document"] == {
        "id": "RAOS-CONTRACT-REPOSITORY-001",
        "version": "0.4",
        "story_id": "ST-0104",
        "status": "IMPLEMENTED_NOT_VALIDATED",
        "generated_by": "scripts/build_st0104_contract_repository.py",
    }
    assert manifest["provenance"]["source_manifest"]["sha256"] == (
        SOURCE_MANIFEST_SHA256
    )
    assert manifest["provenance"]["copy_mode"] == "BYTE_IDENTICAL"
    assert manifest["inventory"]["boundary"] == "EXACT"
    assert manifest["inventory"]["manifest"]["included_in_artifact_count"] is False
    assert manifest["inventory"]["root_readme"]["included_in_artifact_count"] is False
    resolution = manifest["schema_resolution"]
    assert resolution["dialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert resolution["network_retrieval"] == "FORBIDDEN"
    assert resolution["alias_policy"] == "EXPLICIT_REVIEWED_ONLY"
    assert resolution["alias_count"] == 6
    aliases = resolution["retrieval_uri_aliases"]
    assert len(aliases) == 6
    assert [entry["retrieval_uri"] for entry in aliases] == sorted(
        entry["retrieval_uri"] for entry in aliases
    )
    assert all(
        set(entry) == {"retrieval_uri", "path", "canonical_id", "declared_by"}
        and set(entry["declared_by"]) == {"path", "reference"}
        for entry in aliases
    )
    assert manifest["artifact_count"] == 306
    entries = manifest["artifacts"]
    assert len(entries) == 306
    assert [entry["path"] for entry in entries] == sorted(
        entry["path"] for entry in entries
    )
    assert all(set(entry) == {"path", "bytes", "sha256"} for entry in entries)


def test_installed_payloads_are_byte_identical_to_st0004() -> None:
    manifest = load_manifest()
    for entry in manifest["artifacts"]:
        relative = Path(entry["path"])
        installed = VERSION_ROOT / relative
        source = SOURCE_ROOT / relative
        assert installed.is_file()
        assert source.is_file()
        assert installed.read_bytes() == source.read_bytes()
        assert installed.stat().st_size == entry["bytes"]
        assert sha256(installed) == entry["sha256"]

    actual = {
        path.relative_to(VERSION_ROOT).as_posix()
        for path in VERSION_ROOT.rglob("*")
        if path.is_file()
    }
    assert actual == {
        MANIFEST_NAME,
        *(entry["path"] for entry in manifest["artifacts"]),
    }


def test_two_level_layout_preserves_job_state_references() -> None:
    references = {
        "contracts/openapi-internal.v0.4.yaml": "../job-state.v1.yaml",
        "contracts/openapi-admin.v0.4.yaml": "../job-state.v1.yaml",
        "contracts/asyncapi.v0.4.yaml": "../job-state.v1.yaml",
        "contracts/catalogs/resource-contracts.v0.4.yaml": "../../job-state.v1.yaml",
    }
    expected = VERSION_ROOT / "job-state.v1.yaml"
    for relative, marker in references.items():
        document = VERSION_ROOT / relative
        assert marker in document.read_text(encoding="utf-8")
        assert (document.parent / marker).resolve() == expected.resolve()


def test_check_is_read_only_and_machine_readable() -> None:
    before = tree_digest(REPO_ROOT / "contracts")
    process = subprocess.run(
        [sys.executable, str(INSTALLER_PATH), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    after = tree_digest(REPO_ROOT / "contracts")
    assert process.returncode == 0, process.stderr
    assert process.stderr == ""
    assert json.loads(process.stdout) == {
        "artifact_count": 306,
        "installed_bundle_root": "contracts/raos-v0.4",
        "mode": "check",
        "status": "PASS",
        "story_id": "ST-0104",
    }
    assert after == before


def test_manifest_render_is_deterministic(installer_module: ModuleType) -> None:
    artifacts = installer_module.verify_source_bundle()
    first = installer_module.render_manifest(artifacts)
    second = installer_module.render_manifest(tuple(reversed(artifacts)))
    assert first == second == (VERSION_ROOT / MANIFEST_NAME).read_bytes()


def test_root_readme_and_source_bundle_remain_protected() -> None:
    assert sha256(REPO_ROOT / "contracts" / "README.md") == ROOT_README_SHA256
    assert sha256(SOURCE_ROOT / "manifest.yaml") == SOURCE_MANIFEST_SHA256
    assert not (VERSION_ROOT / "README.md").exists()


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered", "symlink"])
def test_owned_tree_mutations_fail_closed(
    tmp_path: Path, installer_module: ModuleType, mutation: str
) -> None:
    candidate = copy_version(tmp_path)
    target = candidate / "contracts" / "openapi-public.v0.1.yaml"
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        (candidate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    elif mutation == "tampered":
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        target.unlink()
        target.symlink_to(candidate / "job-state.v1.yaml")
    with pytest.raises(RuntimeError):
        installer_module._version_file_map(candidate)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("", "unsafe relative path"),
        ("/absolute", "unsafe relative path"),
        ("../escape", "unsafe relative path"),
        ("a/../../escape", "unsafe relative path"),
        ("a\\windows", "unsafe relative path"),
    ],
)
def test_path_validation_rejects_escape(
    installer_module: ModuleType, path: str, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        installer_module._checked_relative_path(path, source="test")


def test_manifest_hash_and_casefold_mutations_fail_closed(
    tmp_path: Path, installer_module: ModuleType
) -> None:
    candidate = copy_version(tmp_path)
    manifest_path = candidate / MANIFEST_NAME
    manifest = load_manifest(candidate)
    manifest["artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError):
        installer_module._version_file_map(candidate)

    candidate = copy_version(tmp_path / "casefold")
    duplicate = candidate / "contracts" / "OPENAPI-PUBLIC.v0.1.yaml"
    duplicate.write_bytes(
        (candidate / "contracts" / "openapi-public.v0.1.yaml").read_bytes()
    )
    with pytest.raises(RuntimeError, match="casefold"):
        installer_module._version_file_map(candidate)


def test_manifest_aggregate_size_is_rejected_before_payload_reads(
    installer_module: ModuleType,
) -> None:
    manifest = load_manifest()
    for entry in manifest["artifacts"]:
        entry["bytes"] = installer_module.MAX_ARTIFACT_BYTES
    with pytest.raises(RuntimeError, match="aggregate byte limit"):
        installer_module._validate_manifest_artifacts(manifest)


def test_cli_rejects_unowned_output_override() -> None:
    process = subprocess.run(
        [sys.executable, str(INSTALLER_PATH), "--output", "/tmp/escape"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode != 0
    assert "unrecognized arguments" in process.stderr


def test_install_failure_rolls_back_previous_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, installer_module: ModuleType
) -> None:
    contracts_root = tmp_path / "contracts"
    contracts_root.mkdir()
    install_root = contracts_root / installer_module.INSTALL_NAME
    shutil.copytree(VERSION_ROOT, install_root)
    temporary_root = contracts_root / ".raos-st0104-build-test"
    temporary_root.mkdir()
    staged_root = temporary_root / "generated"
    shutil.copytree(VERSION_ROOT, staged_root)

    monkeypatch.setattr(installer_module, "CONTRACTS_ROOT", contracts_root)
    monkeypatch.setattr(installer_module, "INSTALL_ROOT", install_root)
    real_has_symlink_component = installer_module._has_symlink_component

    def has_symlink_component(path: Path, *, stop: Path = tmp_path) -> bool:
        return real_has_symlink_component(path, stop=stop)

    monkeypatch.setattr(
        installer_module, "_has_symlink_component", has_symlink_component
    )
    real_rename_exchange = installer_module._rename_exchange
    exchange_calls = 0

    def observed_rename_exchange(
        source_name: str,
        destination_name: str,
        *,
        source_dir_fd: int,
        destination_dir_fd: int,
    ) -> None:
        nonlocal exchange_calls
        assert source_name == staged_root.name
        assert destination_name == installer_module.INSTALL_NAME
        assert staged_root.is_dir()
        assert install_root.is_dir()
        exchange_calls += 1
        real_rename_exchange(
            source_name,
            destination_name,
            source_dir_fd=source_dir_fd,
            destination_dir_fd=destination_dir_fd,
        )

    monkeypatch.setattr(installer_module, "_rename_exchange", observed_rename_exchange)
    previous_files = installer_module._version_file_map(install_root)
    expected_files = installer_module._version_file_map(staged_root)
    previous_digest = tree_digest(install_root)
    real_version_file_map = installer_module._version_file_map
    install_reads = 0

    def fail_after_replacement(path: Path) -> dict[str, bytes]:
        nonlocal install_reads
        if path == install_root:
            install_reads += 1
            if install_reads == 2:
                raise RuntimeError("injected post-replacement failure")
        return real_version_file_map(path)

    monkeypatch.setattr(installer_module, "_version_file_map", fail_after_replacement)
    with pytest.raises(RuntimeError, match="injected post-replacement failure"):
        installer_module._install_staged(
            temporary_root,
            staged_root,
            contracts_identity=installer_module._directory_identity(contracts_root),
            temporary_identity=installer_module._directory_identity(temporary_root),
            staged_identity=installer_module._directory_identity(staged_root),
            expected_files=expected_files,
            previous_files=previous_files,
        )

    assert tree_digest(install_root) == previous_digest
    assert staged_root.is_dir()
    assert not (temporary_root / "previous-raos-v0.4").exists()
    assert exchange_calls == 2
