"""Fail-closed reader for the installed, content-addressed contract repository."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import cast
from urllib.parse import SplitResult, urljoin, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "raos-v0.4"
MANIFEST_NAME = "contract-repository.v0.4.json"
EXPECTED_ARTIFACT_COUNT = 306
EXPECTED_PATH_INVENTORY_SHA256 = (
    "b50df406069a2efa9097b2f79e656c01edc46e9b5259651edd76f9d223961b8f"
)
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_AGGREGATE_BYTES = 128 * 1024 * 1024
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

_SCHEMA_RETRIEVAL_ALIAS_SPECS = (
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

_EXPECTED_DOCUMENT: Mapping[str, object] = {
    "id": "RAOS-CONTRACT-REPOSITORY-001",
    "version": "0.4",
    "story_id": "ST-0104",
    "status": "IMPLEMENTED_NOT_VALIDATED",
    "generated_by": "scripts/build_st0104_contract_repository.py",
}
_EXPECTED_PROVENANCE: Mapping[str, object] = {
    "source_manifest": {
        "path": "changes/st-0004/manifest.yaml",
        "sha256": ("5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458"),
        "document_id": "RAOS-CONTENT-REVISION-001",
        "version": "0.4",
        "story_id": "ST-0004",
        "generated_by": "scripts/build_st0004_revision.py",
    },
    "source_bundle_root": "changes/st-0004",
    "installed_bundle_root": "contracts/raos-v0.4",
    "copy_mode": "BYTE_IDENTICAL",
}
_EXPECTED_INVENTORY: Mapping[str, object] = {
    "boundary": "EXACT",
    "path_base": "contracts/raos-v0.4",
    "source_path_base": "changes/st-0004",
    "root_readme": {
        "path": "contracts/README.md",
        "handling": "PRESERVED_BYTE_IDENTICAL_SIDECAR",
        "included_in_artifact_count": False,
    },
    "manifest": {
        "path": "contracts/raos-v0.4/contract-repository.v0.4.json",
        "included_in_artifact_count": False,
        "self_hash": "EXCLUDED_TO_AVOID_RECURSIVE_SELF_HASH",
    },
    "path_traversal_casefold_symlink_special_file_checks": True,
}
_EXPECTED_SCHEMA_RESOLUTION: Mapping[str, object] = {
    "dialect": SCHEMA_DIALECT,
    "network_retrieval": "FORBIDDEN",
    "alias_policy": "EXPLICIT_REVIEWED_ONLY",
    "alias_count": len(_SCHEMA_RETRIEVAL_ALIAS_SPECS),
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
        for retrieval_uri, path, canonical_id, source_path, reference in (
            _SCHEMA_RETRIEVAL_ALIAS_SPECS
        )
    ],
}


class ContractRepositoryError(RuntimeError):
    """The installed repository is unsafe, malformed, or has drifted."""


@dataclass(frozen=True, slots=True)
class ContractArtifact:
    """One content-addressed artifact registered by the install manifest."""

    path: str
    byte_count: int
    sha256: str


def _reject_json_constant(value: str) -> object:
    raise ContractRepositoryError(f"non-JSON numeric constant: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ContractRepositoryError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def parse_strict_json(content: bytes, *, source: str) -> object:
    """Parse UTF-8 JSON while rejecting duplicate keys and extensions."""

    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ContractRepositoryError(f"invalid UTF-8 in {source}: {exc}") from exc
    try:
        return cast(
            object,
            json.loads(
                text,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            ),
        )
    except ContractRepositoryError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractRepositoryError(f"invalid JSON in {source}: {exc}") from exc


def _mapping(value: object, *, source: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ContractRepositoryError(f"expected JSON object in {source}")
    raw_mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw_mapping):
        raise ContractRepositoryError(f"non-string object key in {source}")
    return cast(Mapping[str, object], raw_mapping)


def _sequence(value: object, *, source: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ContractRepositoryError(f"expected JSON array in {source}")
    return cast(Sequence[object], value)


def _strict_equal(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            return False
        actual_mapping = cast(dict[object, object], actual)
        expected_mapping = cast(dict[object, object], expected)
        return all(
            _strict_equal(actual_mapping[key], value)
            for key, value in expected_mapping.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        actual_sequence = cast(list[object], actual)
        expected_sequence = cast(list[object], expected)
        if len(actual_sequence) != len(expected_sequence):
            return False
        return all(
            _strict_equal(left, right)
            for left, right in zip(actual_sequence, expected_sequence)
        )
    return actual == expected


def _require_exact(actual: object, expected: object, *, source: str) -> None:
    if not _strict_equal(actual, expected):
        raise ContractRepositoryError(f"unexpected value or shape in {source}")


def _checked_path(value: str, *, source: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise ContractRepositoryError(f"unsafe repository path in {source}: {value!r}")
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or path.as_posix() != value
    ):
        raise ContractRepositoryError(f"unsafe repository path in {source}: {value!r}")
    return path


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _stat_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity_signature(metadata: os.stat_result) -> tuple[int, ...]:
    """Bind a directory path without treating unrelated child churn as a swap.

    Directory size, link count, mtime, and ctime can change when an unrelated
    sibling is created below an ancestor such as ``/tmp``.  Those fields are
    useful for directories *inside* the repository, whose exact inventory is
    owned here, but they are not stable identity material for the filesystem
    root or parents above the repository.  Device, inode, and file type still
    fail closed on path replacement or a symlink/directory type change.
    """

    return (metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode))


def _required_filesystem_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        raise ContractRepositoryError(
            "required repository filesystem safety is unavailable"
        )
    return value


def _split_schema_uri(value: str, *, source: str) -> SplitResult:
    try:
        return urlsplit(value)
    except ValueError as exc:
        raise ContractRepositoryError(
            f"malformed schema URI in {source}: {value!r}"
        ) from exc


class ContractRepository:
    """Read and verify the installed v0.4 repository without network access.

    Construction verifies the complete manifest and filesystem. Every later read
    checks the selected artifact again, so a post-construction mutation cannot be
    consumed silently.
    """

    def __init__(self, root: Path | str = DEFAULT_CONTRACT_ROOT) -> None:
        requested_root = Path(root)
        if not requested_root.is_absolute():
            requested_root = Path.cwd() / requested_root
        normalized_root = Path(os.path.abspath(requested_root))
        try:
            resolved_root = normalized_root.resolve(strict=True)
        except OSError as exc:
            raise ContractRepositoryError(
                f"cannot resolve contract repository root {normalized_root}: {exc}"
            ) from exc
        if resolved_root != normalized_root:
            raise ContractRepositoryError(
                "contract repository root contains a symlink or is not normalized: "
                f"{normalized_root}"
            )
        self._root = normalized_root
        self._manifest_path = self._root / MANIFEST_NAME
        self._artifacts: Mapping[str, ContractArtifact] = MappingProxyType({})
        self._schema_ids: Mapping[str, str] = MappingProxyType({})
        self._schema_aliases: Mapping[str, str] = MappingProxyType({})
        self._assert_root_directory()
        artifacts = self._load_manifest()
        self._artifacts = MappingProxyType({item.path: item for item in artifacts})
        self.verify_integrity()
        self._schema_ids = MappingProxyType(self._build_schema_id_index())
        self._schema_aliases = MappingProxyType(self._build_schema_alias_index())

    @property
    def root(self) -> Path:
        return self._root

    @property
    def artifacts(self) -> tuple[ContractArtifact, ...]:
        return tuple(self._artifacts.values())

    @property
    def schema_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._schema_ids))

    @property
    def schema_retrieval_aliases(self) -> tuple[str, ...]:
        """Return the exact reviewed offline retrieval-URI aliases."""

        return tuple(sorted(self._schema_aliases))

    def _assert_root_directory(self) -> None:
        try:
            mode = self._root.lstat().st_mode
        except OSError as exc:
            raise ContractRepositoryError(
                f"cannot stat contract repository root {self._root}: {exc}"
            ) from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ContractRepositoryError(
                f"contract repository root is not a real directory: {self._root}"
            )

    def _assert_parent_directories(self, relative: PurePosixPath) -> None:
        current = self._root
        for part in relative.parts[:-1]:
            current /= part
            try:
                mode = current.lstat().st_mode
            except OSError as exc:
                raise ContractRepositoryError(
                    f"cannot stat parent {current}: {exc}"
                ) from exc
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ContractRepositoryError(f"unsafe artifact parent: {current}")

    def _read_regular(
        self, relative: PurePosixPath, *, maximum_bytes: int = MAX_ARTIFACT_BYTES
    ) -> bytes:
        normalized_relative = _checked_path(relative.as_posix(), source="artifact read")
        directory_flag = _required_filesystem_flag("O_DIRECTORY")
        nofollow_flag = _required_filesystem_flag("O_NOFOLLOW")
        nonblock_flag = _required_filesystem_flag("O_NONBLOCK")
        close_on_exec_flag = _required_filesystem_flag("O_CLOEXEC")
        directory_flags = (
            os.O_RDONLY | directory_flag | nofollow_flag | close_on_exec_flag
        )
        file_flags = os.O_RDONLY | nofollow_flag | nonblock_flag | close_on_exec_flag
        descriptors: list[int] = []
        root_captures: list[tuple[int, str, int, tuple[int, ...]]] = []
        ancestor_captures: list[tuple[int, str, int, tuple[int, ...]]] = []
        primary_error: BaseException | None = None
        try:
            try:
                absolute_root = Path(os.path.abspath(self._root))
                filesystem_root = Path(absolute_root.anchor)
                if absolute_root.anchor != os.sep or not filesystem_root.is_absolute():
                    raise ContractRepositoryError(
                        "contract repository root must be an absolute path"
                    )

                filesystem_root_path_before = filesystem_root.lstat()
                filesystem_root_signature = _directory_identity_signature(
                    filesystem_root_path_before
                )
                if stat.S_ISLNK(
                    filesystem_root_path_before.st_mode
                ) or not stat.S_ISDIR(filesystem_root_path_before.st_mode):
                    raise ContractRepositoryError(
                        "filesystem root is not a real directory"
                    )
                filesystem_root_descriptor = os.open(filesystem_root, directory_flags)
                descriptors.append(filesystem_root_descriptor)
                filesystem_root_opened_before = os.fstat(filesystem_root_descriptor)
                if not stat.S_ISDIR(
                    filesystem_root_opened_before.st_mode
                ) or filesystem_root_signature != _directory_identity_signature(
                    filesystem_root_opened_before
                ):
                    raise ContractRepositoryError(
                        "contract repository root changed before secure capture"
                    )

                parent_descriptor = filesystem_root_descriptor
                for part in absolute_root.parts[1:]:
                    path_before = os.stat(
                        part,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISDIR(
                        path_before.st_mode
                    ):
                        raise ContractRepositoryError(
                            "contract repository root and its ancestors must be "
                            "real directories"
                        )
                    component_signature = _directory_identity_signature(path_before)
                    directory_descriptor = os.open(
                        part,
                        directory_flags,
                        dir_fd=parent_descriptor,
                    )
                    descriptors.append(directory_descriptor)
                    opened_before = os.fstat(directory_descriptor)
                    if not stat.S_ISDIR(
                        opened_before.st_mode
                    ) or component_signature != _directory_identity_signature(
                        opened_before
                    ):
                        raise ContractRepositoryError(
                            "contract repository root changed before secure capture"
                        )
                    root_captures.append(
                        (
                            parent_descriptor,
                            part,
                            directory_descriptor,
                            component_signature,
                        )
                    )
                    parent_descriptor = directory_descriptor

                for part in normalized_relative.parts[:-1]:
                    path_before = os.stat(
                        part,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISDIR(
                        path_before.st_mode
                    ):
                        raise ContractRepositoryError(
                            f"unsafe artifact parent: {normalized_relative}"
                        )
                    ancestor_signature = _stat_signature(path_before)
                    directory_descriptor = os.open(
                        part,
                        directory_flags,
                        dir_fd=parent_descriptor,
                    )
                    descriptors.append(directory_descriptor)
                    opened_before = os.fstat(directory_descriptor)
                    if not stat.S_ISDIR(
                        opened_before.st_mode
                    ) or ancestor_signature != _stat_signature(opened_before):
                        raise ContractRepositoryError(
                            "artifact ancestor changed before secure capture: "
                            f"{normalized_relative}"
                        )
                    ancestor_captures.append(
                        (
                            parent_descriptor,
                            part,
                            directory_descriptor,
                            ancestor_signature,
                        )
                    )
                    parent_descriptor = directory_descriptor

                leaf = normalized_relative.name
                path_before = os.stat(
                    leaf,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(
                    path_before.st_mode
                ):
                    raise ContractRepositoryError(
                        f"artifact is not a regular file: {normalized_relative}"
                    )
                if path_before.st_nlink != 1:
                    raise ContractRepositoryError(
                        f"artifact must have one filesystem link: {normalized_relative}"
                    )
                if path_before.st_size < 0 or path_before.st_size > maximum_bytes:
                    raise ContractRepositoryError(
                        f"artifact exceeds size limit: {normalized_relative}"
                    )
                file_signature = _stat_signature(path_before)

                file_descriptor = os.open(
                    leaf,
                    file_flags,
                    dir_fd=parent_descriptor,
                )
                descriptors.append(file_descriptor)
                opened_before = os.fstat(file_descriptor)
                if not stat.S_ISREG(opened_before.st_mode):
                    raise ContractRepositoryError(
                        f"artifact is not regular: {normalized_relative}"
                    )
                if opened_before.st_nlink != 1:
                    raise ContractRepositoryError(
                        f"artifact must have one filesystem link: {normalized_relative}"
                    )
                if opened_before.st_size < 0 or opened_before.st_size > maximum_bytes:
                    raise ContractRepositoryError(
                        f"artifact exceeds size limit: {normalized_relative}"
                    )
                if file_signature != _stat_signature(opened_before):
                    raise ContractRepositoryError(
                        f"artifact was replaced before open: {normalized_relative}"
                    )

                remaining = opened_before.st_size
                chunks: list[bytes] = []
                while remaining:
                    chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        raise ContractRepositoryError(
                            f"short artifact read: {normalized_relative}"
                        )
                    if len(chunk) > remaining:
                        raise ContractRepositoryError(
                            f"artifact changed during read: {normalized_relative}"
                        )
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(file_descriptor, 1):
                    raise ContractRepositoryError(
                        f"artifact changed during read: {normalized_relative}"
                    )
                content = b"".join(chunks)

                opened_after = os.fstat(file_descriptor)
                path_after = os.stat(
                    leaf,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISREG(opened_after.st_mode)
                    or stat.S_ISLNK(path_after.st_mode)
                    or not stat.S_ISREG(path_after.st_mode)
                    or opened_after.st_nlink != 1
                    or path_after.st_nlink != 1
                    or file_signature != _stat_signature(opened_after)
                    or file_signature != _stat_signature(path_after)
                    or len(content) != opened_before.st_size
                ):
                    raise ContractRepositoryError(
                        f"artifact changed during read: {normalized_relative}"
                    )

                for (
                    ancestor_parent,
                    ancestor_name,
                    ancestor_descriptor,
                    ancestor_signature,
                ) in reversed(ancestor_captures):
                    ancestor_opened_after = os.fstat(ancestor_descriptor)
                    ancestor_path_after = os.stat(
                        ancestor_name,
                        dir_fd=ancestor_parent,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(ancestor_opened_after.st_mode)
                        or stat.S_ISLNK(ancestor_path_after.st_mode)
                        or not stat.S_ISDIR(ancestor_path_after.st_mode)
                        or ancestor_signature != _stat_signature(ancestor_opened_after)
                        or ancestor_signature != _stat_signature(ancestor_path_after)
                    ):
                        raise ContractRepositoryError(
                            "artifact ancestor changed during read: "
                            f"{normalized_relative}"
                        )

                for (
                    root_parent,
                    root_name,
                    root_component_descriptor,
                    root_component_signature,
                ) in reversed(root_captures):
                    root_component_opened_after = os.fstat(root_component_descriptor)
                    root_component_path_after = os.stat(
                        root_name,
                        dir_fd=root_parent,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(root_component_opened_after.st_mode)
                        or stat.S_ISLNK(root_component_path_after.st_mode)
                        or not stat.S_ISDIR(root_component_path_after.st_mode)
                        or root_component_signature
                        != _directory_identity_signature(root_component_opened_after)
                        or root_component_signature
                        != _directory_identity_signature(root_component_path_after)
                    ):
                        raise ContractRepositoryError(
                            "contract repository root changed during secure capture"
                        )

                filesystem_root_opened_after = os.fstat(filesystem_root_descriptor)
                filesystem_root_path_after = filesystem_root.lstat()
                if (
                    not stat.S_ISDIR(filesystem_root_opened_after.st_mode)
                    or stat.S_ISLNK(filesystem_root_path_after.st_mode)
                    or not stat.S_ISDIR(filesystem_root_path_after.st_mode)
                    or filesystem_root_signature
                    != _directory_identity_signature(filesystem_root_opened_after)
                    or filesystem_root_signature
                    != _directory_identity_signature(filesystem_root_path_after)
                ):
                    raise ContractRepositoryError(
                        "contract repository root changed during secure capture"
                    )
                return content
            except OSError:
                raise ContractRepositoryError(
                    f"artifact could not be captured safely: {normalized_relative}"
                ) from None
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            close_failed = False
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    close_failed = True
            if close_failed and primary_error is not None:
                try:
                    primary_error.add_note("descriptor cleanup also failed")
                except BaseException:
                    pass
            elif close_failed:
                raise ContractRepositoryError(
                    f"artifact descriptor cleanup failed: {normalized_relative}"
                ) from None

    def _load_manifest(self) -> tuple[ContractArtifact, ...]:
        manifest_content = self._read_regular(
            PurePosixPath(MANIFEST_NAME), maximum_bytes=MAX_MANIFEST_BYTES
        )
        manifest = _mapping(
            parse_strict_json(manifest_content, source=MANIFEST_NAME),
            source=MANIFEST_NAME,
        )
        expected_keys = {
            "document",
            "provenance",
            "inventory",
            "schema_resolution",
            "artifact_count",
            "artifacts",
        }
        if set(manifest) != expected_keys:
            raise ContractRepositoryError("unexpected manifest top-level keys")
        _require_exact(
            manifest["document"], _EXPECTED_DOCUMENT, source="manifest.document"
        )
        _require_exact(
            manifest["provenance"], _EXPECTED_PROVENANCE, source="manifest.provenance"
        )
        _require_exact(
            manifest["inventory"], _EXPECTED_INVENTORY, source="manifest.inventory"
        )
        _require_exact(
            manifest["schema_resolution"],
            _EXPECTED_SCHEMA_RESOLUTION,
            source="manifest.schema_resolution",
        )
        if (
            not isinstance(manifest["artifact_count"], int)
            or isinstance(manifest["artifact_count"], bool)
            or manifest["artifact_count"] != EXPECTED_ARTIFACT_COUNT
        ):
            raise ContractRepositoryError("unexpected manifest artifact_count")

        entries = _sequence(manifest["artifacts"], source="manifest.artifacts")
        if len(entries) != EXPECTED_ARTIFACT_COUNT:
            raise ContractRepositoryError("manifest artifact list length mismatch")
        artifacts: list[ContractArtifact] = []
        seen_casefold: set[str] = set()
        aggregate_bytes = 0
        for index, raw_entry in enumerate(entries):
            entry = _mapping(raw_entry, source=f"manifest.artifacts[{index}]")
            if set(entry) != {"path", "bytes", "sha256"}:
                raise ContractRepositoryError(
                    f"unexpected artifact entry keys at index {index}"
                )
            raw_path = entry["path"]
            byte_count = entry["bytes"]
            digest = entry["sha256"]
            if not isinstance(raw_path, str):
                raise ContractRepositoryError(
                    f"non-string artifact path at index {index}"
                )
            checked = _checked_path(raw_path, source=f"manifest.artifacts[{index}]")
            if raw_path == MANIFEST_NAME:
                raise ContractRepositoryError("manifest cannot hash itself")
            if raw_path != "job-state.v1.yaml" and not raw_path.startswith(
                "contracts/"
            ):
                raise ContractRepositoryError(
                    f"artifact outside installed tree: {raw_path}"
                )
            if (
                not isinstance(byte_count, int)
                or isinstance(byte_count, bool)
                or byte_count < 0
                or byte_count > MAX_ARTIFACT_BYTES
            ):
                raise ContractRepositoryError(f"invalid byte count for {raw_path}")
            aggregate_bytes += byte_count
            if aggregate_bytes > MAX_AGGREGATE_BYTES:
                raise ContractRepositoryError("manifest aggregate byte limit exceeded")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ContractRepositoryError(f"invalid SHA-256 for {raw_path}")
            folded = checked.as_posix().casefold()
            if folded in seen_casefold:
                raise ContractRepositoryError(
                    f"duplicate/casefold artifact path: {raw_path}"
                )
            seen_casefold.add(folded)
            artifacts.append(ContractArtifact(raw_path, byte_count, digest))
        paths = [artifact.path for artifact in artifacts]
        if paths != sorted(paths):
            raise ContractRepositoryError("manifest artifacts are not sorted by path")
        if paths.count("job-state.v1.yaml") != 1:
            raise ContractRepositoryError(
                "job-state.v1.yaml must be registered exactly once"
            )
        if sum(path.startswith("contracts/") for path in paths) != 305:
            raise ContractRepositoryError("expected exactly 305 contract artifacts")
        path_inventory = "".join(f"{path}\n" for path in paths).encode("utf-8")
        if _sha256(path_inventory) != EXPECTED_PATH_INVENTORY_SHA256:
            raise ContractRepositoryError("unexpected artifact path inventory")
        return tuple(artifacts)

    def _filesystem_inventory(self) -> tuple[set[str], set[str]]:
        files: set[str] = set()
        directories: set[str] = set()
        seen_casefold: set[str] = set()
        directory_flag = _required_filesystem_flag("O_DIRECTORY")
        nofollow_flag = _required_filesystem_flag("O_NOFOLLOW")
        nonblock_flag = _required_filesystem_flag("O_NONBLOCK")
        close_on_exec_flag = _required_filesystem_flag("O_CLOEXEC")
        directory_flags = (
            os.O_RDONLY | directory_flag | nofollow_flag | close_on_exec_flag
        )
        file_flags = os.O_RDONLY | nofollow_flag | nonblock_flag | close_on_exec_flag
        descriptors: list[int] = []
        root_captures: list[tuple[int, str, int, tuple[int, ...]]] = []
        directory_captures: list[
            tuple[int, str, int, tuple[int, ...], PurePosixPath]
        ] = []
        file_captures: list[tuple[int, str, tuple[int, ...], PurePosixPath]] = []
        listing_captures: list[tuple[int, tuple[str, ...], PurePosixPath | None]] = []
        primary_error: BaseException | None = None
        try:
            try:
                absolute_root = Path(os.path.abspath(self._root))
                filesystem_root = Path(absolute_root.anchor)
                if absolute_root.anchor != os.sep or not filesystem_root.is_absolute():
                    raise ContractRepositoryError(
                        "contract repository root must be an absolute path"
                    )

                filesystem_root_path_before = filesystem_root.lstat()
                filesystem_root_signature = _directory_identity_signature(
                    filesystem_root_path_before
                )
                if stat.S_ISLNK(
                    filesystem_root_path_before.st_mode
                ) or not stat.S_ISDIR(filesystem_root_path_before.st_mode):
                    raise ContractRepositoryError(
                        "filesystem root is not a real directory"
                    )
                filesystem_root_descriptor = os.open(filesystem_root, directory_flags)
                descriptors.append(filesystem_root_descriptor)
                filesystem_root_opened_before = os.fstat(filesystem_root_descriptor)
                if not stat.S_ISDIR(
                    filesystem_root_opened_before.st_mode
                ) or filesystem_root_signature != _directory_identity_signature(
                    filesystem_root_opened_before
                ):
                    raise ContractRepositoryError(
                        "contract repository root changed before inventory capture"
                    )

                parent_descriptor = filesystem_root_descriptor
                for part in absolute_root.parts[1:]:
                    path_before = os.stat(
                        part,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISDIR(
                        path_before.st_mode
                    ):
                        raise ContractRepositoryError(
                            "contract repository root and its ancestors must be "
                            "real directories"
                        )
                    component_signature = _directory_identity_signature(path_before)
                    directory_descriptor = os.open(
                        part,
                        directory_flags,
                        dir_fd=parent_descriptor,
                    )
                    descriptors.append(directory_descriptor)
                    opened_before = os.fstat(directory_descriptor)
                    if not stat.S_ISDIR(
                        opened_before.st_mode
                    ) or component_signature != _directory_identity_signature(
                        opened_before
                    ):
                        raise ContractRepositoryError(
                            "contract repository root changed before inventory capture"
                        )
                    root_captures.append(
                        (
                            parent_descriptor,
                            part,
                            directory_descriptor,
                            component_signature,
                        )
                    )
                    parent_descriptor = directory_descriptor

                pending: list[tuple[int, PurePosixPath | None]] = [
                    (parent_descriptor, None)
                ]
                while pending:
                    directory_descriptor, relative_directory = pending.pop()
                    raw_names = os.listdir(directory_descriptor)
                    if not all(type(name) is str for name in raw_names):
                        raise ContractRepositoryError(
                            "unsafe filesystem entry name in repository"
                        )
                    names = sorted(raw_names)
                    listing_captures.append(
                        (directory_descriptor, tuple(names), relative_directory)
                    )
                    for name in names:
                        relative = (
                            PurePosixPath(name)
                            if relative_directory is None
                            else relative_directory / name
                        )
                        normalized = _checked_path(
                            relative.as_posix(), source="filesystem"
                        )
                        folded = normalized.as_posix().casefold()
                        if folded in seen_casefold:
                            raise ContractRepositoryError(
                                f"duplicate/casefold filesystem path: {normalized}"
                            )
                        seen_casefold.add(folded)
                        path_before = os.stat(
                            name,
                            dir_fd=directory_descriptor,
                            follow_symlinks=False,
                        )
                        if stat.S_ISLNK(path_before.st_mode):
                            raise ContractRepositoryError(
                                f"symlink in repository: {normalized}"
                            )
                        entry_signature = _stat_signature(path_before)
                        if stat.S_ISDIR(path_before.st_mode):
                            entry_descriptor = os.open(
                                name,
                                directory_flags,
                                dir_fd=directory_descriptor,
                            )
                            descriptors.append(entry_descriptor)
                            opened_before = os.fstat(entry_descriptor)
                            if not stat.S_ISDIR(
                                opened_before.st_mode
                            ) or entry_signature != _stat_signature(opened_before):
                                raise ContractRepositoryError(
                                    "directory changed before inventory capture: "
                                    f"{normalized}"
                                )
                            directories.add(normalized.as_posix())
                            directory_captures.append(
                                (
                                    directory_descriptor,
                                    name,
                                    entry_descriptor,
                                    entry_signature,
                                    normalized,
                                )
                            )
                            pending.append((entry_descriptor, normalized))
                        elif stat.S_ISREG(path_before.st_mode):
                            entry_descriptor = os.open(
                                name,
                                file_flags,
                                dir_fd=directory_descriptor,
                            )
                            descriptors.append(entry_descriptor)
                            file_primary_error: BaseException | None = None
                            try:
                                try:
                                    opened_before = os.fstat(entry_descriptor)
                                    if not stat.S_ISREG(
                                        opened_before.st_mode
                                    ) or entry_signature != _stat_signature(
                                        opened_before
                                    ):
                                        raise ContractRepositoryError(
                                            "file changed before inventory capture: "
                                            f"{normalized}"
                                        )
                                    opened_after = os.fstat(entry_descriptor)
                                    if not stat.S_ISREG(
                                        opened_after.st_mode
                                    ) or entry_signature != _stat_signature(
                                        opened_after
                                    ):
                                        raise ContractRepositoryError(
                                            "file changed during inventory: "
                                            f"{normalized}"
                                        )
                                    files.add(normalized.as_posix())
                                    file_captures.append(
                                        (
                                            directory_descriptor,
                                            name,
                                            entry_signature,
                                            normalized,
                                        )
                                    )
                                except OSError:
                                    raise ContractRepositoryError(
                                        "repository inventory could not be captured "
                                        "safely"
                                    ) from None
                            except BaseException as exc:
                                file_primary_error = exc
                                raise
                            finally:
                                descriptors.pop()
                                try:
                                    os.close(entry_descriptor)
                                except OSError:
                                    if file_primary_error is not None:
                                        try:
                                            file_primary_error.add_note(
                                                "inventory file descriptor cleanup "
                                                "also failed"
                                            )
                                        except BaseException:
                                            pass
                                    else:
                                        raise ContractRepositoryError(
                                            "repository inventory file descriptor "
                                            "cleanup failed"
                                        ) from None
                        else:
                            raise ContractRepositoryError(
                                f"special file in repository: {normalized}"
                            )

                for (
                    file_parent,
                    file_name,
                    file_signature,
                    file_relative,
                ) in reversed(file_captures):
                    path_after = os.stat(
                        file_name,
                        dir_fd=file_parent,
                        follow_symlinks=False,
                    )
                    if (
                        stat.S_ISLNK(path_after.st_mode)
                        or not stat.S_ISREG(path_after.st_mode)
                        or file_signature != _stat_signature(path_after)
                    ):
                        raise ContractRepositoryError(
                            f"file changed during inventory: {file_relative}"
                        )

                for (
                    listed_descriptor,
                    listed_names,
                    listed_relative,
                ) in reversed(listing_captures):
                    raw_names_after = os.listdir(listed_descriptor)
                    if not all(type(name) is str for name in raw_names_after):
                        raise ContractRepositoryError(
                            "unsafe filesystem entry name in repository"
                        )
                    names_after = tuple(sorted(raw_names_after))
                    if listed_names != names_after:
                        if listed_relative is None:
                            raise ContractRepositoryError(
                                "contract repository root changed during inventory"
                            )
                        raise ContractRepositoryError(
                            f"directory changed during inventory: {listed_relative}"
                        )

                for (
                    directory_parent,
                    directory_name,
                    captured_descriptor,
                    directory_signature,
                    directory_relative,
                ) in reversed(directory_captures):
                    opened_after = os.fstat(captured_descriptor)
                    path_after = os.stat(
                        directory_name,
                        dir_fd=directory_parent,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(opened_after.st_mode)
                        or stat.S_ISLNK(path_after.st_mode)
                        or not stat.S_ISDIR(path_after.st_mode)
                        or directory_signature != _stat_signature(opened_after)
                        or directory_signature != _stat_signature(path_after)
                    ):
                        raise ContractRepositoryError(
                            f"directory changed during inventory: {directory_relative}"
                        )

                for (
                    root_parent,
                    root_name,
                    root_component_descriptor,
                    root_component_signature,
                ) in reversed(root_captures):
                    opened_after = os.fstat(root_component_descriptor)
                    path_after = os.stat(
                        root_name,
                        dir_fd=root_parent,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISDIR(opened_after.st_mode)
                        or stat.S_ISLNK(path_after.st_mode)
                        or not stat.S_ISDIR(path_after.st_mode)
                        or root_component_signature
                        != _directory_identity_signature(opened_after)
                        or root_component_signature
                        != _directory_identity_signature(path_after)
                    ):
                        raise ContractRepositoryError(
                            "contract repository root changed during inventory"
                        )

                filesystem_root_opened_after = os.fstat(filesystem_root_descriptor)
                filesystem_root_path_after = filesystem_root.lstat()
                if (
                    not stat.S_ISDIR(filesystem_root_opened_after.st_mode)
                    or stat.S_ISLNK(filesystem_root_path_after.st_mode)
                    or not stat.S_ISDIR(filesystem_root_path_after.st_mode)
                    or filesystem_root_signature
                    != _directory_identity_signature(filesystem_root_opened_after)
                    or filesystem_root_signature
                    != _directory_identity_signature(filesystem_root_path_after)
                ):
                    raise ContractRepositoryError(
                        "contract repository root changed during inventory"
                    )
                return files, directories
            except OSError:
                raise ContractRepositoryError(
                    "repository inventory could not be captured safely"
                ) from None
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            close_failed = False
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    close_failed = True
            if close_failed and primary_error is not None:
                try:
                    primary_error.add_note("inventory descriptor cleanup also failed")
                except BaseException:
                    pass
            elif close_failed:
                raise ContractRepositoryError(
                    "repository inventory descriptor cleanup failed"
                ) from None

    def verify_integrity(self) -> None:
        """Recheck exact inventory, file types, byte lengths, and SHA-256 hashes."""

        self._assert_root_directory()
        actual_files, actual_directories = self._filesystem_inventory()
        expected_files = set(self._artifacts) | {MANIFEST_NAME}
        if actual_files != expected_files:
            missing = sorted(expected_files - actual_files)
            extra = sorted(actual_files - expected_files)
            raise ContractRepositoryError(
                f"filesystem inventory mismatch; missing={missing}, extra={extra}"
            )
        expected_directories: set[str] = set()
        for artifact_path in expected_files:
            parent = PurePosixPath(artifact_path).parent
            while parent != PurePosixPath("."):
                expected_directories.add(parent.as_posix())
                parent = parent.parent
        if actual_directories != expected_directories:
            missing = sorted(expected_directories - actual_directories)
            extra = sorted(actual_directories - expected_directories)
            raise ContractRepositoryError(
                f"directory inventory mismatch; missing={missing}, extra={extra}"
            )
        for artifact in self._artifacts.values():
            content = self._read_regular(PurePosixPath(artifact.path))
            if len(content) != artifact.byte_count:
                raise ContractRepositoryError(f"byte length mismatch: {artifact.path}")
            if _sha256(content) != artifact.sha256:
                raise ContractRepositoryError(f"SHA-256 mismatch: {artifact.path}")

    def _registered_artifact(self, path: str | PurePosixPath) -> ContractArtifact:
        raw_path = path.as_posix() if isinstance(path, PurePosixPath) else path
        checked = _checked_path(raw_path, source="read path")
        artifact = self._artifacts.get(checked.as_posix())
        if artifact is None:
            raise ContractRepositoryError(f"unregistered artifact path: {raw_path!r}")
        return artifact

    def read_bytes(self, path: str | PurePosixPath) -> bytes:
        """Read a registered artifact and reverify its length and digest."""

        artifact = self._registered_artifact(path)
        content = self._read_regular(PurePosixPath(artifact.path))
        if len(content) != artifact.byte_count or _sha256(content) != artifact.sha256:
            raise ContractRepositoryError(
                f"artifact changed after verification: {artifact.path}"
            )
        return content

    def read_text(self, path: str | PurePosixPath) -> str:
        """Read a registered UTF-8 artifact."""

        raw_path = path.as_posix() if isinstance(path, PurePosixPath) else path
        try:
            return self.read_bytes(path).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ContractRepositoryError(
                f"invalid UTF-8 in {raw_path}: {exc}"
            ) from exc

    def load_json(self, path: str | PurePosixPath) -> object:
        """Strictly parse one registered JSON artifact."""

        raw_path = path.as_posix() if isinstance(path, PurePosixPath) else path
        return parse_strict_json(self.read_bytes(path), source=raw_path)

    def _build_schema_id_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for artifact in self._artifacts.values():
            if not artifact.path.endswith(".json"):
                continue
            document = self.load_json(artifact.path)
            if not isinstance(document, dict):
                continue
            schema = _mapping(cast(object, document), source=artifact.path)
            if "$id" not in schema:
                continue
            schema_id = schema["$id"]
            if not isinstance(schema_id, str):
                raise ContractRepositoryError(
                    f"non-string top-level $id: {artifact.path}"
                )
            parsed = _split_schema_uri(schema_id, source=artifact.path)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "schemas.raos.local"
                or not parsed.path.startswith("/")
                or parsed.query
                or parsed.fragment
                or "\\" in schema_id
            ):
                raise ContractRepositoryError(
                    f"unsafe or unsupported top-level $id in {artifact.path}: {schema_id!r}"
                )
            if schema_id in index:
                raise ContractRepositoryError(f"duplicate top-level $id: {schema_id}")
            index[schema_id] = artifact.path
        return index

    def _build_schema_alias_index(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        previous_uri = ""
        for (
            retrieval_uri,
            target_path,
            canonical_id,
            source_path,
            reference,
        ) in _SCHEMA_RETRIEVAL_ALIAS_SPECS:
            parsed = _split_schema_uri(
                retrieval_uri, source="manifest.schema_resolution"
            )
            if (
                parsed.scheme != "https"
                or parsed.netloc != "schemas.raos.local"
                or not parsed.path.startswith("/")
                or parsed.query
                or parsed.fragment
                or "\\" in retrieval_uri
            ):
                raise ContractRepositoryError(
                    f"unsafe schema retrieval URI alias: {retrieval_uri!r}"
                )
            if retrieval_uri <= previous_uri:
                raise ContractRepositoryError(
                    "schema retrieval URI aliases are not uniquely sorted"
                )
            previous_uri = retrieval_uri
            if retrieval_uri in self._schema_ids or retrieval_uri in aliases:
                raise ContractRepositoryError(
                    f"schema retrieval URI alias collision: {retrieval_uri}"
                )
            if self._schema_ids.get(canonical_id) != target_path:
                raise ContractRepositoryError(
                    f"schema retrieval alias target mismatch: {retrieval_uri}"
                )
            source = _mapping(self.load_json(source_path), source=source_path)
            source_id = source.get("$id")
            if not isinstance(source_id, str) or urljoin(source_id, reference) != (
                retrieval_uri
            ):
                raise ContractRepositoryError(
                    f"schema retrieval alias base mismatch: {retrieval_uri}"
                )
            pending: list[object] = [cast(object, source)]
            declared = False
            while pending:
                node = pending.pop()
                if isinstance(node, dict):
                    raw_mapping = cast(dict[object, object], node)
                    if raw_mapping.get("$ref") == reference:
                        declared = True
                    pending.extend(raw_mapping.values())
                elif isinstance(node, list):
                    pending.extend(cast(list[object], node))
            if not declared:
                raise ContractRepositoryError(
                    f"schema retrieval alias declaration missing: {retrieval_uri}"
                )
            aliases[retrieval_uri] = target_path
        return aliases

    def path_for_id(self, schema_id: str) -> str:
        """Return the registered local path for an exact schema identifier."""

        parsed = _split_schema_uri(schema_id, source="schema identifier")
        if parsed.fragment or parsed.query:
            raise ContractRepositoryError(
                f"schema identifiers with query/fragment are unsupported: {schema_id!r}"
            )
        path = self._schema_ids.get(schema_id)
        if path is None:
            raise ContractRepositoryError(
                f"schema identifier is not registered locally: {schema_id!r}"
            )
        return path

    def resolve_id(self, schema_id: str) -> Mapping[str, object]:
        """Resolve an exact local schema ID without performing a remote fetch."""

        path = self.path_for_id(schema_id)
        return _mapping(self.load_json(path), source=path)

    def path_for_uri(self, schema_uri: str) -> str:
        """Resolve a canonical ID or reviewed retrieval alias to a local path."""

        parsed = _split_schema_uri(schema_uri, source="schema URI")
        if (
            parsed.scheme != "https"
            or parsed.netloc != "schemas.raos.local"
            or not parsed.path.startswith("/")
            or parsed.query
            or parsed.fragment
            or "\\" in schema_uri
        ):
            raise ContractRepositoryError(
                f"unsafe or unsupported schema URI: {schema_uri!r}"
            )
        path = self._schema_ids.get(schema_uri) or self._schema_aliases.get(schema_uri)
        if path is None:
            raise ContractRepositoryError(
                f"schema URI is not registered locally: {schema_uri!r}"
            )
        return path

    def resolve_uri(self, schema_uri: str) -> Mapping[str, object]:
        """Resolve a canonical ID or explicit alias without network retrieval."""

        path = self.path_for_uri(schema_uri)
        return _mapping(self.load_json(path), source=path)
