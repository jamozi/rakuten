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
        self._assert_parent_directories(relative)
        path = self._root.joinpath(*relative.parts)
        try:
            path_stat = path.lstat()
        except OSError as exc:
            raise ContractRepositoryError(
                f"cannot stat artifact {relative}: {exc}"
            ) from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise ContractRepositoryError(f"artifact is not a regular file: {relative}")
        if path_stat.st_size > maximum_bytes:
            raise ContractRepositoryError(f"artifact exceeds size limit: {relative}")

        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise ContractRepositoryError("O_NOFOLLOW is required for contract reads")
        nonblocking = getattr(os, "O_NONBLOCK", None)
        if nonblocking is None:
            raise ContractRepositoryError("O_NONBLOCK is required for contract reads")
        flags = os.O_RDONLY | no_follow | nonblocking
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ContractRepositoryError(
                f"cannot open artifact {relative}: {exc}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ContractRepositoryError(f"artifact is not regular: {relative}")
            if (path_stat.st_dev, path_stat.st_ino) != (before.st_dev, before.st_ino):
                raise ContractRepositoryError(
                    f"artifact was replaced before open: {relative}"
                )
            if before.st_size > maximum_bytes:
                raise ContractRepositoryError(
                    f"artifact exceeds size limit: {relative}"
                )
            chunks: list[bytes] = []
            bytes_read = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > maximum_bytes:
                    raise ContractRepositoryError(
                        f"artifact exceeds size limit during read: {relative}"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ContractRepositoryError(
                    f"artifact changed during read: {relative}"
                )
            content = b"".join(chunks)
            if len(content) != after.st_size:
                raise ContractRepositoryError(f"short artifact read: {relative}")
            return content
        finally:
            os.close(descriptor)

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
        pending: list[tuple[Path, PurePosixPath | None]] = [(self._root, None)]
        while pending:
            directory, relative_directory = pending.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError as exc:
                raise ContractRepositoryError(
                    f"cannot scan {directory}: {exc}"
                ) from exc
            for entry in entries:
                relative = (
                    PurePosixPath(entry.name)
                    if relative_directory is None
                    else relative_directory / entry.name
                )
                normalized = _checked_path(relative.as_posix(), source="filesystem")
                folded = normalized.as_posix().casefold()
                if folded in seen_casefold:
                    raise ContractRepositoryError(
                        f"duplicate/casefold filesystem path: {normalized}"
                    )
                seen_casefold.add(folded)
                try:
                    mode = entry.stat(follow_symlinks=False).st_mode
                except OSError as exc:
                    raise ContractRepositoryError(
                        f"cannot stat {normalized}: {exc}"
                    ) from exc
                if stat.S_ISLNK(mode):
                    raise ContractRepositoryError(
                        f"symlink in repository: {normalized}"
                    )
                if stat.S_ISDIR(mode):
                    directories.add(normalized.as_posix())
                    pending.append((Path(entry.path), normalized))
                elif stat.S_ISREG(mode):
                    files.add(normalized.as_posix())
                else:
                    raise ContractRepositoryError(
                        f"special file in repository: {normalized}"
                    )
        return files, directories

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
