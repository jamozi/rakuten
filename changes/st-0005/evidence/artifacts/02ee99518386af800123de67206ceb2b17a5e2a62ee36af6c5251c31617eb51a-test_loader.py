"""Fail-closed read API and mutation tests for the ST-0104 loader."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from conftest import MANIFEST_NAME, VERSION_ROOT
from raos.shared.contract_repository import (
    ContractRepository,
    ContractRepositoryError,
    parse_strict_json,
)


def copy_version(tmp_path: Path) -> Path:
    target = tmp_path / "raos-v0.4"
    shutil.copytree(VERSION_ROOT, target)
    return target


def load_manifest(root: Path) -> dict[str, Any]:
    value = json.loads((root / MANIFEST_NAME).read_bytes())
    assert isinstance(value, dict)
    return value


def write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def rebind_artifact(root: Path, path: str) -> None:
    manifest = load_manifest(root)
    payload = (root / path).read_bytes()
    entry = next(item for item in manifest["artifacts"] if item["path"] == path)
    entry["bytes"] = len(payload)
    entry["sha256"] = hashlib.sha256(payload).hexdigest()
    write_manifest(root, manifest)


def test_repository_loads_complete_inventory_and_schema_id_index() -> None:
    repository = ContractRepository()
    assert repository.root == VERSION_ROOT
    assert len(repository.artifacts) == 306
    assert repository.artifacts[-1].path == "job-state.v1.yaml"
    assert len(repository.schema_ids) > 200
    assert repository.schema_ids == tuple(sorted(repository.schema_ids))
    assert len(repository.schema_retrieval_aliases) == 6
    assert repository.schema_retrieval_aliases == tuple(
        sorted(repository.schema_retrieval_aliases)
    )
    repository.verify_integrity()


def test_registered_reads_and_strict_json_loading() -> None:
    repository = ContractRepository()
    path = "contracts/schemas/common/actor-ref.schema.json"
    payload = repository.read_bytes(path)
    assert repository.read_text(path) == payload.decode("utf-8")
    document = repository.load_json(path)
    assert isinstance(document, dict)
    schema_id = document["$id"]
    assert isinstance(schema_id, str)
    assert repository.path_for_id(schema_id) == path
    assert repository.resolve_id(schema_id) == document

    retrieval_uri = repository.schema_retrieval_aliases[0]
    alias_path = repository.path_for_uri(retrieval_uri)
    alias_document = repository.resolve_uri(retrieval_uri)
    assert alias_path == (
        "contracts/schemas/ai-governance/ai-task-definition.v1.schema.json"
    )
    assert alias_document["$id"] == (
        "https://schemas.raos.local/ai-governance/ai-task-definition/v1"
    )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute",
        "../escape",
        "contracts/../job-state.v1.yaml",
        "contracts//double",
        "contracts\\windows",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json",
        "contract-repository.v0.4.json",
        "contracts/unknown.schema.json",
    ],
)
def test_reads_reject_unregistered_or_unsafe_paths(path: str) -> None:
    repository = ContractRepository()
    with pytest.raises(ContractRepositoryError):
        repository.read_bytes(path)


@pytest.mark.parametrize(
    "schema_id",
    [
        "https://schemas.raos.local/unknown.schema.json",
        "http://schemas.raos.local/common/v1/actor-ref.schema.json",
        "https://example.com/schema.json",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json#fragment",
        "https://schemas.raos.local/common/v1/actor-ref.schema.json?query=1",
        "http://[",
    ],
)
def test_schema_id_resolution_never_falls_back_to_remote(schema_id: str) -> None:
    repository = ContractRepository()
    with pytest.raises(ContractRepositoryError):
        repository.resolve_id(schema_id)


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered", "symlink"])
def test_filesystem_mutations_fail_on_construction(
    tmp_path: Path, mutation: str
) -> None:
    root = copy_version(tmp_path)
    target = root / "contracts" / "openapi-public.v0.1.yaml"
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    elif mutation == "tampered":
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        target.unlink()
        target.symlink_to(root / "job-state.v1.yaml")
    with pytest.raises(ContractRepositoryError):
        ContractRepository(root)


def test_post_construction_mutation_is_rechecked(tmp_path: Path) -> None:
    root = copy_version(tmp_path)
    repository = ContractRepository(root)
    path = "contracts/openapi-public.v0.1.yaml"
    target = root / path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ContractRepositoryError, match="changed after verification"):
        repository.read_bytes(path)


def test_final_file_fifo_replacement_cannot_block_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_version(tmp_path)
    repository = ContractRepository(root)
    relative = "contracts/openapi-public.v0.1.yaml"
    target = root / relative
    real_open = os.open
    replaced = False

    def replace_with_fifo_before_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal replaced
        if not replaced and Path(path) == target:
            assert flags & os.O_NONBLOCK
            target.unlink()
            os.mkfifo(target)
            replaced = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", replace_with_fifo_before_open)
    with pytest.raises(ContractRepositoryError, match="artifact is not regular"):
        repository.read_bytes(relative)
    assert replaced


def test_manifest_duplicate_key_unknown_key_and_bad_hash_fail(tmp_path: Path) -> None:
    duplicate_root = copy_version(tmp_path / "duplicate")
    manifest_path = duplicate_root / MANIFEST_NAME
    content = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        content.replace('  "document": {', '  "document": {},\n  "document": {', 1),
        encoding="utf-8",
    )
    with pytest.raises(ContractRepositoryError, match="duplicate JSON object key"):
        ContractRepository(duplicate_root)

    unknown_root = copy_version(tmp_path / "unknown")
    manifest = load_manifest(unknown_root)
    manifest["unknown"] = True
    write_manifest(unknown_root, manifest)
    with pytest.raises(ContractRepositoryError, match="top-level"):
        ContractRepository(unknown_root)

    hash_root = copy_version(tmp_path / "hash")
    manifest = load_manifest(hash_root)
    manifest["artifacts"][0]["sha256"] = "0" * 64
    write_manifest(hash_root, manifest)
    with pytest.raises(ContractRepositoryError, match="SHA-256 mismatch"):
        ContractRepository(hash_root)

    alias_root = copy_version(tmp_path / "alias")
    manifest = load_manifest(alias_root)
    manifest["schema_resolution"]["retrieval_uri_aliases"][0]["path"] = (
        "contracts/schemas/common/actor-ref.schema.json"
    )
    write_manifest(alias_root, manifest)
    with pytest.raises(ContractRepositoryError, match="schema_resolution"):
        ContractRepository(alias_root)


def test_casefold_collision_and_symlinked_root_fail(tmp_path: Path) -> None:
    root = copy_version(tmp_path / "casefold")
    original = root / "contracts" / "openapi-public.v0.1.yaml"
    duplicate = root / "contracts" / "OPENAPI-PUBLIC.v0.1.yaml"
    duplicate.write_bytes(original.read_bytes())
    with pytest.raises(ContractRepositoryError, match="casefold"):
        ContractRepository(root)

    link = tmp_path / "linked-root"
    link.symlink_to(VERSION_ROOT, target_is_directory=True)
    with pytest.raises(ContractRepositoryError, match="symlink|not a real directory"):
        ContractRepository(link)


def test_symlinked_ancestor_of_root_fails(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    root = copy_version(real_parent)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ContractRepositoryError, match="contains a symlink"):
        ContractRepository(linked_parent / root.name)


def test_malformed_json_and_duplicate_schema_id_fail_after_valid_rebind(
    tmp_path: Path,
) -> None:
    malformed_root = copy_version(tmp_path / "malformed")
    malformed_path = "contracts/schemas/common/actor-ref.schema.json"
    (malformed_root / malformed_path).write_text("{invalid\n", encoding="utf-8")
    rebind_artifact(malformed_root, malformed_path)
    with pytest.raises(ContractRepositoryError, match="invalid JSON"):
        ContractRepository(malformed_root)

    duplicate_root = copy_version(tmp_path / "duplicate-id")
    first_path = "contracts/schemas/common/actor-ref.schema.json"
    second_path = "contracts/schemas/common/artifact-ref.schema.json"
    first = json.loads((duplicate_root / first_path).read_bytes())
    second = json.loads((duplicate_root / second_path).read_bytes())
    second["$id"] = first["$id"]
    (duplicate_root / second_path).write_text(
        json.dumps(second, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rebind_artifact(duplicate_root, second_path)
    with pytest.raises(ContractRepositoryError, match="duplicate top-level \\$id"):
        ContractRepository(duplicate_root)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"duplicate": 1, "duplicate": 2}',
        b'{"nan": NaN}',
        b"\xff",
        b"[",
    ],
)
def test_strict_json_rejects_extensions_and_malformed_input(payload: bytes) -> None:
    with pytest.raises(ContractRepositoryError):
        parse_strict_json(payload, source="test")
