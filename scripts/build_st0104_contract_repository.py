#!/usr/bin/env python3
"""Install the hash-pinned ST-0004 contract bundle for ST-0104.

The installed bundle deliberately retains the ST-0004 relative layout.  Several
contracts contain references to ``../job-state.v1.yaml`` (or the two-level
variant), so flattening ``changes/st-0004/contracts`` into the repository-level
``contracts`` directory would silently break otherwise valid references.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT: Final = REPO_ROOT / "contracts"
INSTALL_NAME: Final = "raos-v0.4"
INSTALL_ROOT: Final = CONTRACTS_ROOT / INSTALL_NAME
INSTALLED_MANIFEST_NAME: Final = "contract-repository.v0.4.json"
INSTALLED_MANIFEST: Final = INSTALL_ROOT / INSTALLED_MANIFEST_NAME
ROOT_README: Final = CONTRACTS_ROOT / "README.md"

# Repository-level contract families may coexist only when another registered
# generator owns their complete file inventory.  ST-0104 must preserve these
# sibling roots byte-for-byte; it never copies them into or removes them with
# the versioned ``raos-v0.4`` installation.
SEPARATELY_OWNED_CONTRACT_ROOTS: Final[Mapping[str, str]] = {
    "raos-v2": "build_raos_v2_successor",
}

SOURCE_ROOT: Final = REPO_ROOT / "changes" / "st-0004"
SOURCE_MANIFEST: Final = SOURCE_ROOT / "manifest.yaml"
SOURCE_MANIFEST_PATH: Final = "changes/st-0004/manifest.yaml"
SOURCE_PREFIX: Final = "changes/st-0004/"
SOURCE_CONTRACTS: Final = SOURCE_ROOT / "contracts"

DOCUMENT_ID: Final = "RAOS-CONTRACT-REPOSITORY-001"
DOCUMENT_VERSION: Final = "0.4"
STORY_ID: Final = "ST-0104"
GENERATOR_PATH: Final = "scripts/build_st0104_contract_repository.py"
SOURCE_DOCUMENT_ID: Final = "RAOS-CONTENT-REVISION-001"
SOURCE_STORY_ID: Final = "ST-0004"
SOURCE_GENERATOR_PATH: Final = "scripts/build_st0004_revision.py"
SOURCE_MANIFEST_SHA256: Final = (
    "5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458"
)
ROOT_README_SHA256: Final = (
    "6ea0bb1d89007cf3a8cae6109d50963859ce764e05198a5b05c2a014733e5951"
)
EXPECTED_ARTIFACT_COUNT: Final = 306
MAX_MANIFEST_BYTES: Final = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES: Final = 16 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES: Final = 128 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
RENAME_EXCHANGE: Final = 2
SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_RETRIEVAL_ALIASES: Final = (
    (
        "https://schemas.raos.local/ai-governance/ai-task-contract/"
        "ai-task-definition.v1.schema.json",
        "contracts/schemas/ai-governance/ai-task-definition.v1.schema.json",
        "https://schemas.raos.local/ai-governance/ai-task-definition/v1",
        "contracts/schemas/ai-governance/ai-task-contract.v1.schema.json",
        "ai-task-definition.v1.schema.json",
    ),
    (
        "https://schemas.raos.local/ai-governance/evaluation-run-detail/"
        "evaluation-run.v1.schema.json",
        "contracts/schemas/ai-governance/evaluation-run.v1.schema.json",
        "https://schemas.raos.local/ai-governance/evaluation-run/v1",
        "contracts/schemas/ai-governance/evaluation-run-detail.v1.schema.json",
        "evaluation-run.v1.schema.json",
    ),
    (
        "https://schemas.raos.local/ai-governance/"
        "release-decision-approval-result/release-approval.v1.schema.json",
        "contracts/schemas/ai-governance/release-approval.v1.schema.json",
        "https://schemas.raos.local/ai-governance/release-approval/v1",
        "contracts/schemas/ai-governance/"
        "release-decision-approval-result.v1.schema.json",
        "release-approval.v1.schema.json",
    ),
    (
        "https://schemas.raos.local/ai-governance/"
        "release-decision-approval-result/release-decision.v1.schema.json",
        "contracts/schemas/ai-governance/release-decision.v1.schema.json",
        "https://schemas.raos.local/ai-governance/release-decision/v1",
        "contracts/schemas/ai-governance/"
        "release-decision-approval-result.v1.schema.json",
        "release-decision.v1.schema.json",
    ),
    (
        "https://schemas.raos.local/content/schemas/content-ast.schema.json",
        "contracts/content/schemas/content-ast.schema.json",
        "https://schemas.raos.local/content/v1/content-ast.schema.json",
        "contracts/schemas/content-revision/content-validation-request.v1.schema.json",
        "../../content/schemas/content-ast.schema.json",
    ),
    (
        "https://schemas.raos.local/content/schemas/seo-metadata.schema.json",
        "contracts/content/schemas/seo-metadata.schema.json",
        "https://schemas.raos.local/content/v1/seo-metadata.schema.json",
        "contracts/schemas/content-revision/seo-metadata-update-request.v1.schema.json",
        "../../content/schemas/seo-metadata.schema.json",
    ),
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class RollbackRecoveryRequired(RuntimeError):
    """The original installation could not be restored automatically."""

    def __init__(self, recovery_path: Path) -> None:
        self.recovery_path = recovery_path
        super().__init__(
            "contract repository rollback was incomplete; recovery retained at "
            f"{recovery_path}"
        )


@dataclass(frozen=True)
class Artifact:
    """One verified, byte-identical payload in the cumulative bundle."""

    path: str
    bytes: int
    sha256: str
    content: bytes

    def manifest_entry(self) -> dict[str, object]:
        return {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _checked_relative_path(value: str, *, source: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"unsafe relative path in {source}: {value!r}")
    return path


def _has_symlink_component(path: Path, *, stop: Path = REPO_ROOT) -> bool:
    """Return true when a component at or below ``stop`` is a symlink."""

    try:
        relative = path.relative_to(stop)
    except ValueError as exc:
        raise RuntimeError(f"path escapes repository root: {path}") from exc
    current = stop
    try:
        root_metadata = stop.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        return True
    for component in relative.parts:
        current /= component
        try:
            metadata = current.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _read_regular(path: Path, *, maximum: int, kind: str) -> bytes:
    """Read a bounded regular file while detecting replacement during the read."""

    error = f"required regular non-symlink {kind} is missing or unsafe: {path}"
    if _has_symlink_component(path):
        raise RuntimeError(error)
    try:
        before = path.lstat()
    except OSError as exc:
        raise RuntimeError(error) from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
        raise RuntimeError(error)
    if before.st_size > maximum:
        raise RuntimeError(f"{kind} exceeds {maximum} bytes: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(error) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink < 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise RuntimeError(f"{kind} changed before read: {path}")
        chunks: list[bytes] = []
        consumed = 0
        while consumed <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - consumed))
            if not chunk:
                break
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
        if (
            consumed > maximum
            or consumed != after.st_size
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise RuntimeError(f"{kind} changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _load_source_manifest(content: bytes) -> dict[str, Any]:
    try:
        loaded = yaml.load(content, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise RuntimeError("pinned ST-0004 manifest is invalid YAML") from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("pinned ST-0004 manifest must be a mapping")
    return loaded


def _json_unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_installed_manifest(content: bytes) -> dict[str, Any]:
    try:
        loaded = json.loads(content, object_pairs_hook=_json_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            "installed contract repository manifest is invalid JSON"
        ) from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("installed contract repository manifest must be an object")
    return loaded


def _scan_tree(root: Path) -> tuple[dict[str, Path], set[str]]:
    """Return exact regular-file and directory inventories without following links."""

    if _has_symlink_component(root):
        raise RuntimeError(f"unsafe tree root: {root}")
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise RuntimeError(f"tree root is missing: {root}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"tree root must be a non-symlink directory: {root}")

    files: dict[str, Path] = {}
    directories: set[str] = set()
    folded: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise RuntimeError(f"cannot enumerate contract tree: {directory}") from exc
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            _checked_relative_path(relative, source=root.as_posix())
            folded_path = relative.casefold()
            if folded_path in folded:
                raise RuntimeError(f"casefold duplicate tree entry: {relative}")
            folded.add(folded_path)
            if entry.is_symlink():
                raise RuntimeError(f"symlink is forbidden in contract tree: {path}")
            if entry.is_dir(follow_symlinks=False):
                directories.add(relative)
                pending.append(path)
            elif entry.is_file(follow_symlinks=False):
                files[relative] = path
            else:
                raise RuntimeError(
                    f"special file is forbidden in contract tree: {path}"
                )
    return files, directories


def _expected_directories(paths: Sequence[str]) -> set[str]:
    result: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def verify_source_bundle() -> tuple[Artifact, ...]:
    """Verify the pinned manifest and its complete 306-file owned inventory."""

    manifest_content = _read_regular(
        SOURCE_MANIFEST,
        maximum=MAX_MANIFEST_BYTES,
        kind="ST-0004 manifest",
    )
    actual_manifest_hash = _sha256(manifest_content)
    if actual_manifest_hash != SOURCE_MANIFEST_SHA256:
        raise RuntimeError(
            "ST-0004 manifest hash drift: expected "
            f"{SOURCE_MANIFEST_SHA256}, got {actual_manifest_hash}"
        )
    manifest = _load_source_manifest(manifest_content)
    document = manifest.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != SOURCE_DOCUMENT_ID
        or document.get("version") != DOCUMENT_VERSION
        or document.get("story_id") != SOURCE_STORY_ID
        or document.get("generated_by") != SOURCE_GENERATOR_PATH
    ):
        raise RuntimeError("unexpected ST-0004 manifest identity or ownership")
    entries = manifest.get("generated_artifacts")
    if (
        not isinstance(entries, list)
        or manifest.get("generated_artifact_count") != EXPECTED_ARTIFACT_COUNT
        or len(entries) != EXPECTED_ARTIFACT_COUNT
    ):
        raise RuntimeError("ST-0004 generated-artifact count is not exactly 306")

    artifacts: list[Artifact] = []
    seen: set[str] = set()
    total_bytes = 0
    for raw_entry in entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise RuntimeError("malformed ST-0004 generated-artifact entry")
        raw_path = raw_entry["path"]
        expected_bytes = raw_entry["bytes"]
        expected_hash = raw_entry["sha256"]
        if (
            not isinstance(raw_path, str)
            or type(expected_bytes) is not int
            or expected_bytes < 0
            or expected_bytes > MAX_ARTIFACT_BYTES
            or not isinstance(expected_hash, str)
            or not SHA256_PATTERN.fullmatch(expected_hash)
        ):
            raise RuntimeError("invalid ST-0004 generated-artifact metadata")
        relative_repo = _checked_relative_path(raw_path, source=SOURCE_MANIFEST_PATH)
        if not raw_path.startswith(SOURCE_PREFIX):
            raise RuntimeError(f"ST-0004 artifact escapes source bundle: {raw_path}")
        installed_path = raw_path.removeprefix(SOURCE_PREFIX)
        _checked_relative_path(installed_path, source=SOURCE_MANIFEST_PATH)
        if installed_path != "job-state.v1.yaml" and not installed_path.startswith(
            "contracts/"
        ):
            raise RuntimeError(f"unexpected ST-0004 generated artifact: {raw_path}")
        folded = installed_path.casefold()
        if folded in seen:
            raise RuntimeError(f"duplicate/casefold ST-0004 artifact: {raw_path}")
        seen.add(folded)
        source_path = REPO_ROOT.joinpath(*relative_repo.parts)
        content = _read_regular(
            source_path,
            maximum=MAX_ARTIFACT_BYTES,
            kind="ST-0004 generated artifact",
        )
        if len(content) != expected_bytes or _sha256(content) != expected_hash:
            raise RuntimeError(
                f"ST-0004 generated artifact integrity failure: {raw_path}"
            )
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_ARTIFACT_BYTES:
            raise RuntimeError(
                "ST-0004 generated artifacts exceed aggregate size limit"
            )
        artifacts.append(
            Artifact(installed_path, expected_bytes, expected_hash, content)
        )

    source_files, source_directories = _scan_tree(SOURCE_CONTRACTS)
    actual_paths = {
        "job-state.v1.yaml",
        *(f"contracts/{path}" for path in source_files),
    }
    listed_paths = {artifact.path for artifact in artifacts}
    if actual_paths != listed_paths:
        raise RuntimeError(
            "ST-0004 manifest does not own the complete installable tree: "
            f"unexpected={sorted(actual_paths - listed_paths)}, "
            f"missing={sorted(listed_paths - actual_paths)}"
        )
    expected_source_directories = {
        path.removeprefix("contracts/")
        for path in _expected_directories(
            [path for path in listed_paths if path.startswith("contracts/")]
        )
        if path != "contracts"
    }
    if source_directories != expected_source_directories:
        raise RuntimeError(
            "ST-0004 contracts contain unowned or missing directories: "
            f"unexpected={sorted(source_directories - expected_source_directories)}, "
            f"missing={sorted(expected_source_directories - source_directories)}"
        )
    if {artifact.path for artifact in artifacts} != listed_paths:
        raise RuntimeError("ST-0004 artifact inventory contains duplicate paths")
    return tuple(sorted(artifacts, key=lambda artifact: artifact.path))


def build_manifest(
    artifacts: Sequence[Artifact | Mapping[str, object]],
) -> dict[str, Any]:
    entries: list[dict[str, object]] = []
    for artifact in artifacts:
        if isinstance(artifact, Artifact):
            entries.append(artifact.manifest_entry())
        else:
            entries.append(dict(artifact))
    entries.sort(key=lambda entry: str(entry["path"]))
    return {
        "document": {
            "id": DOCUMENT_ID,
            "version": DOCUMENT_VERSION,
            "story_id": STORY_ID,
            "status": "IMPLEMENTED_NOT_VALIDATED",
            "generated_by": GENERATOR_PATH,
        },
        "provenance": {
            "source_manifest": {
                "path": SOURCE_MANIFEST_PATH,
                "sha256": SOURCE_MANIFEST_SHA256,
                "document_id": SOURCE_DOCUMENT_ID,
                "version": DOCUMENT_VERSION,
                "story_id": SOURCE_STORY_ID,
                "generated_by": SOURCE_GENERATOR_PATH,
            },
            "source_bundle_root": "changes/st-0004",
            "installed_bundle_root": f"contracts/{INSTALL_NAME}",
            "copy_mode": "BYTE_IDENTICAL",
        },
        "inventory": {
            "boundary": "EXACT",
            "path_base": f"contracts/{INSTALL_NAME}",
            "source_path_base": "changes/st-0004",
            "root_readme": {
                "path": "contracts/README.md",
                "handling": "PRESERVED_BYTE_IDENTICAL_SIDECAR",
                "included_in_artifact_count": False,
            },
            "manifest": {
                "path": f"contracts/{INSTALL_NAME}/{INSTALLED_MANIFEST_NAME}",
                "included_in_artifact_count": False,
                "self_hash": "EXCLUDED_TO_AVOID_RECURSIVE_SELF_HASH",
            },
            "path_traversal_casefold_symlink_special_file_checks": True,
        },
        "schema_resolution": {
            "dialect": SCHEMA_DIALECT,
            "network_retrieval": "FORBIDDEN",
            "alias_policy": "EXPLICIT_REVIEWED_ONLY",
            "alias_count": len(SCHEMA_RETRIEVAL_ALIASES),
            "retrieval_uri_aliases": [
                {
                    "retrieval_uri": retrieval_uri,
                    "path": path,
                    "canonical_id": canonical_id,
                    "declared_by": {
                        "path": source_path,
                        "reference": reference,
                    },
                }
                for (
                    retrieval_uri,
                    path,
                    canonical_id,
                    source_path,
                    reference,
                ) in SCHEMA_RETRIEVAL_ALIASES
            ],
        },
        "artifact_count": EXPECTED_ARTIFACT_COUNT,
        "artifacts": entries,
    }


def render_manifest(artifacts: Sequence[Artifact | Mapping[str, object]]) -> bytes:
    return (
        json.dumps(build_manifest(artifacts), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _validate_manifest_artifacts(
    document: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    entries = document.get("artifacts")
    if (
        document.get("artifact_count") != EXPECTED_ARTIFACT_COUNT
        or not isinstance(entries, list)
        or len(entries) != EXPECTED_ARTIFACT_COUNT
    ):
        raise RuntimeError("installed artifact inventory is not exactly 306 entries")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    previous = ""
    aggregate_bytes = 0
    for raw_entry in entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise RuntimeError("malformed installed artifact entry")
        path = raw_entry["path"]
        byte_count = raw_entry["bytes"]
        digest = raw_entry["sha256"]
        if (
            not isinstance(path, str)
            or type(byte_count) is not int
            or byte_count < 0
            or byte_count > MAX_ARTIFACT_BYTES
            or not isinstance(digest, str)
            or not SHA256_PATTERN.fullmatch(digest)
        ):
            raise RuntimeError("invalid installed artifact metadata")
        aggregate_bytes += byte_count
        if aggregate_bytes > MAX_TOTAL_ARTIFACT_BYTES:
            raise RuntimeError("installed artifact aggregate byte limit exceeded")
        _checked_relative_path(path, source=INSTALLED_MANIFEST.as_posix())
        if path != "job-state.v1.yaml" and not path.startswith("contracts/"):
            raise RuntimeError(f"installed artifact escapes exact boundary: {path}")
        if previous and path <= previous:
            raise RuntimeError("installed artifacts must be uniquely path-sorted")
        previous = path
        folded = path.casefold()
        if folded in seen:
            raise RuntimeError(f"casefold duplicate installed artifact: {path}")
        seen.add(folded)
        result.append({"path": path, "bytes": byte_count, "sha256": digest})
    return tuple(result)


def _version_file_map(root: Path) -> dict[str, bytes]:
    files, directories = _scan_tree(root)
    if INSTALLED_MANIFEST_NAME not in files:
        raise RuntimeError("installed contract repository manifest is missing")
    manifest_content = _read_regular(
        files[INSTALLED_MANIFEST_NAME],
        maximum=MAX_MANIFEST_BYTES,
        kind="installed contract repository manifest",
    )
    document = _load_installed_manifest(manifest_content)
    entries = _validate_manifest_artifacts(document)
    expected_manifest = render_manifest(entries)
    if manifest_content != expected_manifest:
        raise RuntimeError("installed manifest metadata or canonical bytes drifted")

    expected_payload_paths = {str(entry["path"]) for entry in entries}
    actual_payload_paths = set(files) - {INSTALLED_MANIFEST_NAME}
    if actual_payload_paths != expected_payload_paths:
        raise RuntimeError(
            "installed contract inventory drift: "
            f"unexpected={sorted(actual_payload_paths - expected_payload_paths)}, "
            f"missing={sorted(expected_payload_paths - actual_payload_paths)}"
        )
    expected_directories = _expected_directories(
        [*expected_payload_paths, INSTALLED_MANIFEST_NAME]
    )
    if directories != expected_directories:
        raise RuntimeError(
            "installed contract directory inventory drift: "
            f"unexpected={sorted(directories - expected_directories)}, "
            f"missing={sorted(expected_directories - directories)}"
        )
    entry_by_path = {str(entry["path"]): entry for entry in entries}
    result = {INSTALLED_MANIFEST_NAME: manifest_content}
    for path in sorted(actual_payload_paths):
        content = _read_regular(
            files[path],
            maximum=MAX_ARTIFACT_BYTES,
            kind="installed contract artifact",
        )
        entry = entry_by_path[path]
        if len(content) != entry["bytes"] or _sha256(content) != entry["sha256"]:
            raise RuntimeError(f"installed contract artifact drift: {path}")
        result[path] = content
    return result


def _registered_contract_outputs(root_name: str, owner_id: str) -> set[str]:
    """Return one sibling contract tree's exact outputs from the build registry."""

    try:
        from scripts.raos_build_core import discover_registry
    except ModuleNotFoundError:  # Direct ``python scripts/...`` invocation.
        from raos_build_core import discover_registry

    registry = discover_registry(root=REPO_ROOT)
    owner = registry.get(owner_id)
    if owner is None:
        raise RuntimeError(
            f"separate contract owner is not registered: {root_name}: {owner_id}"
        )
    prefix = Path("contracts") / root_name
    outputs = {
        path.relative_to(prefix).as_posix()
        for path in owner.outputs
        if path.is_relative_to(prefix)
    }
    if not outputs:
        raise RuntimeError(
            f"separate contract owner declares no outputs: {root_name}: {owner_id}"
        )
    return outputs


def _assert_separately_owned_contract_root(root_name: str, owner_id: str) -> None:
    """Fail closed unless a sibling contract root exactly matches its owner."""

    root = CONTRACTS_ROOT / root_name
    files, directories = _scan_tree(root)
    expected_files = _registered_contract_outputs(root_name, owner_id)
    actual_files = set(files)
    if actual_files != expected_files:
        raise RuntimeError(
            f"separately owned contract inventory drift for {root_name}: "
            f"owner={owner_id}, "
            f"unexpected={sorted(actual_files - expected_files)}, "
            f"missing={sorted(expected_files - actual_files)}"
        )
    expected_directories = _expected_directories(sorted(expected_files))
    if directories != expected_directories:
        raise RuntimeError(
            f"separately owned contract directory drift for {root_name}: "
            f"owner={owner_id}, "
            f"unexpected={sorted(directories - expected_directories)}, "
            f"missing={sorted(expected_directories - directories)}"
        )


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect directory: {path}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"expected non-symlink directory: {path}")
    return metadata.st_dev, metadata.st_ino


def _assert_directory_identity(path: Path, expected: tuple[int, int]) -> None:
    if _directory_identity(path) != expected:
        raise RuntimeError(f"directory identity changed: {path}")


def _directory_open_flags() -> int:
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise RuntimeError("contract installation requires O_DIRECTORY and O_NOFOLLOW")
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_pinned_directory(path: Path, expected: tuple[int, int]) -> int:
    try:
        descriptor = os.open(path, _directory_open_flags())
    except OSError as exc:
        raise RuntimeError(f"cannot open pinned directory: {path}") from exc
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected
    ):
        os.close(descriptor)
        raise RuntimeError(f"directory identity changed before install: {path}")
    return descriptor


def _rename_exchange(
    source_name: str,
    destination_name: str,
    *,
    source_dir_fd: int,
    destination_dir_fd: int,
) -> None:
    """Atomically exchange two same-filesystem directory entries on Linux."""

    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise RuntimeError("atomic directory exchange requires renameat2") from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        source_dir_fd,
        os.fsencode(source_name),
        destination_dir_fd,
        os.fsencode(destination_name),
        RENAME_EXCHANGE,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise RuntimeError(
            "atomic directory exchange failed: "
            f"{os.strerror(error_number)} (errno={error_number})"
        )


def assert_owned_destination() -> tuple[tuple[int, int], dict[str, bytes] | None]:
    """Accept ST-0104 outputs plus complete, registered sibling contract roots."""

    if _has_symlink_component(CONTRACTS_ROOT):
        raise RuntimeError(f"unsafe contracts root: {CONTRACTS_ROOT}")
    root_identity = _directory_identity(CONTRACTS_ROOT)
    try:
        entries = list(os.scandir(CONTRACTS_ROOT))
    except OSError as exc:
        raise RuntimeError("cannot enumerate repository contracts root") from exc
    names = {entry.name for entry in entries}
    allowed = {"README.md", INSTALL_NAME, *SEPARATELY_OWNED_CONTRACT_ROOTS}
    if names - allowed:
        raise RuntimeError(
            f"unowned entry in repository contracts root: {sorted(names - allowed)}"
        )
    missing_sibling_roots = set(SEPARATELY_OWNED_CONTRACT_ROOTS) - names
    if missing_sibling_roots:
        raise RuntimeError(
            "registered sibling contract root is missing: "
            f"{sorted(missing_sibling_roots)}"
        )
    for root_name, owner_id in sorted(SEPARATELY_OWNED_CONTRACT_ROOTS.items()):
        _assert_separately_owned_contract_root(root_name, owner_id)
    if "README.md" not in names:
        raise RuntimeError("ST-0101 contracts README is missing")
    readme_content = _read_regular(
        ROOT_README,
        maximum=MAX_MANIFEST_BYTES,
        kind="ST-0101 contracts README",
    )
    if _sha256(readme_content) != ROOT_README_SHA256:
        raise RuntimeError("ST-0101 contracts README drifted from its pinned bytes")
    if INSTALL_NAME not in names:
        _assert_directory_identity(CONTRACTS_ROOT, root_identity)
        return root_identity, None
    previous = _version_file_map(INSTALL_ROOT)
    _assert_directory_identity(CONTRACTS_ROOT, root_identity)
    return root_identity, previous


def _write_durable_file(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if getattr(os, "O_NOFOLLOW", 0):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o644)
    except OSError as exc:
        raise RuntimeError(f"cannot create staged contract artifact: {path}") from exc
    try:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise RuntimeError(f"short staged contract write: {path}")
            offset += written
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_staged_directories(staged_root: Path) -> None:
    directories = sorted(
        (path for path in staged_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.relative_to(staged_root).parts),
        reverse=True,
    )
    directories.append(staged_root)
    for directory in directories:
        descriptor = os.open(directory, _directory_open_flags())
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write_staged(staged_root: Path, artifacts: Sequence[Artifact]) -> dict[str, bytes]:
    for artifact in artifacts:
        relative = _checked_relative_path(
            artifact.path, source="verified ST-0004 inventory"
        )
        destination = staged_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _write_durable_file(destination, artifact.content)
    manifest_content = render_manifest(artifacts)
    manifest = staged_root / INSTALLED_MANIFEST_NAME
    _write_durable_file(manifest, manifest_content)
    _fsync_staged_directories(staged_root)
    expected = {artifact.path: artifact.content for artifact in artifacts}
    expected[INSTALLED_MANIFEST_NAME] = manifest_content
    actual = _version_file_map(staged_root)
    if actual != expected:
        raise RuntimeError("staged contract repository differs from verified inputs")
    return expected


def _install_staged(
    temporary_root: Path,
    staged_root: Path,
    *,
    contracts_identity: tuple[int, int],
    temporary_identity: tuple[int, int],
    staged_identity: tuple[int, int],
    expected_files: Mapping[str, bytes],
    previous_files: Mapping[str, bytes] | None,
) -> None:
    installed_new = False
    exchanged_old = False
    contracts_fd = _open_pinned_directory(CONTRACTS_ROOT, contracts_identity)
    try:
        temporary_fd = _open_pinned_directory(temporary_root, temporary_identity)
    except BaseException:
        os.close(contracts_fd)
        raise
    try:
        _assert_directory_identity(staged_root, staged_identity)
        current = _version_file_map(INSTALL_ROOT) if INSTALL_ROOT.exists() else None
        if current != previous_files:
            raise RuntimeError(
                "installed contract repository changed before replacement"
            )
        if _version_file_map(staged_root) != expected_files:
            raise RuntimeError("staged contract repository changed before replacement")
        if previous_files is not None:
            _rename_exchange(
                staged_root.name,
                INSTALL_NAME,
                source_dir_fd=temporary_fd,
                destination_dir_fd=contracts_fd,
            )
            exchanged_old = True
        else:
            os.replace(
                staged_root.name,
                INSTALL_NAME,
                src_dir_fd=temporary_fd,
                dst_dir_fd=contracts_fd,
            )
        installed_new = True
        os.fsync(temporary_fd)
        os.fsync(contracts_fd)
        _assert_directory_identity(CONTRACTS_ROOT, contracts_identity)
        if _version_file_map(INSTALL_ROOT) != expected_files:
            raise RuntimeError(
                "installed contract repository differs from staged build"
            )
    except BaseException as install_error:
        rollback_errors: list[BaseException] = []
        if exchanged_old:
            try:
                _rename_exchange(
                    staged_root.name,
                    INSTALL_NAME,
                    source_dir_fd=temporary_fd,
                    destination_dir_fd=contracts_fd,
                )
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        elif installed_new:
            try:
                os.replace(
                    INSTALL_NAME,
                    staged_root.name,
                    src_dir_fd=contracts_fd,
                    dst_dir_fd=temporary_fd,
                )
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        try:
            os.fsync(temporary_fd)
            os.fsync(contracts_fd)
            restored = (
                _version_file_map(INSTALL_ROOT) if INSTALL_ROOT.exists() else None
            ) == previous_files
        except BaseException as rollback_error:
            rollback_errors.append(rollback_error)
            restored = False
        if not restored:
            recovery_error = RollbackRecoveryRequired(temporary_root)
            if rollback_errors:
                raise recovery_error from rollback_errors[0]
            raise recovery_error from install_error
        raise install_error
    finally:
        os.close(temporary_fd)
        os.close(contracts_fd)


def build() -> dict[str, object]:
    contracts_identity, previous_files = assert_owned_destination()
    artifacts = verify_source_bundle()
    temporary_root = Path(
        tempfile.mkdtemp(prefix=".raos-st0104-build-", dir=CONTRACTS_ROOT)
    )
    temporary_identity = _directory_identity(temporary_root)
    retain_recovery = False
    try:
        staged_root = temporary_root / "generated"
        staged_root.mkdir()
        staged_identity = _directory_identity(staged_root)
        expected_files = _write_staged(staged_root, artifacts)
        _install_staged(
            temporary_root,
            staged_root,
            contracts_identity=contracts_identity,
            temporary_identity=temporary_identity,
            staged_identity=staged_identity,
            expected_files=expected_files,
            previous_files=previous_files,
        )
    except RollbackRecoveryRequired:
        retain_recovery = True
        raise
    finally:
        if not retain_recovery:
            _assert_directory_identity(temporary_root, temporary_identity)
            shutil.rmtree(temporary_root)
    final_identity, final_files = assert_owned_destination()
    if final_identity != contracts_identity or final_files is None:
        raise RuntimeError("contract repository installation did not persist exactly")
    return {
        "status": "PASS",
        "story_id": STORY_ID,
        "mode": "build",
        "artifact_count": EXPECTED_ARTIFACT_COUNT,
        "installed_bundle_root": f"contracts/{INSTALL_NAME}",
    }


def check() -> dict[str, object]:
    _, installed_files = assert_owned_destination()
    if installed_files is None:
        raise RuntimeError("contract repository has not been installed")
    artifacts = verify_source_bundle()
    expected_files = {artifact.path: artifact.content for artifact in artifacts}
    expected_files[INSTALLED_MANIFEST_NAME] = render_manifest(artifacts)
    if installed_files != expected_files:
        missing = sorted(set(expected_files) - set(installed_files))
        unexpected = sorted(set(installed_files) - set(expected_files))
        changed = sorted(
            path
            for path in set(expected_files) & set(installed_files)
            if expected_files[path] != installed_files[path]
        )
        raise RuntimeError(
            "generated contract repository drift: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )
    return {
        "status": "PASS",
        "story_id": STORY_ID,
        "mode": "check",
        "artifact_count": EXPECTED_ARTIFACT_COUNT,
        "installed_bundle_root": f"contracts/{INSTALL_NAME}",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or verify the hash-pinned ST-0104 contract repository."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify exact generated bytes without changing the installation",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = check() if args.check else build()
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ST-0104 contract repository error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
