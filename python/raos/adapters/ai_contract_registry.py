"""Stdlib-only adapter for a compiled, hash-bound AI task registry."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import cast

from raos.domain.ai import (
    ContractValue,
    OutputSchemaContract,
    PromptContract,
    RouteContract,
    TaskContract,
)
from raos.ports.task_registry import (
    InvalidTaskCode,
    TaskRegistry,
    TaskRegistryIntegrityError,
    UnknownTaskContract,
)
from raos.shared.contract_repository import ContractRepository, parse_strict_json


MAX_COMPILED_REGISTRY_BYTES = 4 * 1024 * 1024
EXPECTED_DOCUMENT: Mapping[str, object] = {
    "id": "RAOS-AI-TASK-REGISTRY-001",
    "version": "1.0.0",
    "story_id": "ST-0701",
    "status": "IMPLEMENTATION_CANDIDATE",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _require_sha256(value: object, *, source: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TaskRegistryIntegrityError(f"invalid SHA-256 in {source}")
    return value


def _mapping(value: object, *, source: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise TaskRegistryIntegrityError(f"expected string-keyed object in {source}")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise TaskRegistryIntegrityError(f"expected string-keyed object in {source}")
    return cast(Mapping[str, object], raw)


def _sequence(value: object, *, source: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise TaskRegistryIntegrityError(f"expected array in {source}")
    return cast(Sequence[object], value)


def _string(value: object, *, source: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise TaskRegistryIntegrityError(
            f"expected non-empty printable string in {source}"
        )
    return value


def _integer(value: object, *, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaskRegistryIntegrityError(f"expected integer in {source}")
    return value


def _require_exact_keys(
    value: Mapping[str, object], expected: set[str], *, source: str
) -> None:
    if set(value) != expected:
        raise TaskRegistryIntegrityError(f"unexpected object shape in {source}")


def _canonical_sha256(value: object) -> str:
    try:
        content = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise TaskRegistryIntegrityError(
            "non-canonical compiled registry value"
        ) from exc
    return _sha256(content)


def _freeze(value: object, *, source: str) -> ContractValue:
    visits = 0
    active: set[int] = set()

    def freeze(item: object, depth: int) -> ContractValue:
        nonlocal visits
        visits += 1
        if visits > 100_000 or depth > 100:
            raise TaskRegistryIntegrityError(f"{source} exceeds the JSON graph limit")
        if item is None or type(item) in {bool, int, str}:
            return cast(None | bool | int | str, item)
        if type(item) is float:
            number = item
            if not math.isfinite(number):
                raise TaskRegistryIntegrityError(f"non-finite number in {source}")
            return number
        if not isinstance(item, (Mapping, list, tuple)):
            raise TaskRegistryIntegrityError(f"unsupported value in {source}")
        container = cast(
            Mapping[object, object] | list[object] | tuple[object, ...], item
        )
        identity = id(container)
        if identity in active:
            raise TaskRegistryIntegrityError(f"cycle in {source}")
        active.add(identity)
        try:
            if isinstance(container, Mapping):
                raw_mapping = container
                if not all(type(key) is str for key in raw_mapping):
                    raise TaskRegistryIntegrityError(
                        f"non-string object key in {source}"
                    )
                return MappingProxyType(
                    {
                        cast(str, key): freeze(child, depth + 1)
                        for key, child in raw_mapping.items()
                    }
                )
            raw_sequence = container
            return tuple(freeze(child, depth + 1) for child in raw_sequence)
        finally:
            active.remove(identity)

    return freeze(value, 0)


def _frozen_mapping(
    value: Mapping[str, object], *, source: str
) -> Mapping[str, ContractValue]:
    frozen = _freeze(dict(value), source=source)
    if not isinstance(frozen, Mapping):
        raise TaskRegistryIntegrityError(f"expected object in {source}")
    return frozen


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


def _required_filesystem_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        raise TaskRegistryIntegrityError(
            "required registry filesystem safety is unavailable"
        )
    return value


def _read_regular_file(path: Path) -> bytes:
    try:
        normalized = Path(os.path.abspath(path))
    except OSError, RuntimeError, ValueError:
        raise TaskRegistryIntegrityError("cannot resolve compiled registry") from None
    directory_flag = _required_filesystem_flag("O_DIRECTORY")
    nofollow_flag = _required_filesystem_flag("O_NOFOLLOW")
    nonblock_flag = _required_filesystem_flag("O_NONBLOCK")
    close_on_exec_flag = _required_filesystem_flag("O_CLOEXEC")
    directory_flags = os.O_RDONLY | directory_flag | nofollow_flag | close_on_exec_flag
    file_flags = os.O_RDONLY | nofollow_flag | nonblock_flag | close_on_exec_flag
    filesystem_root = Path(normalized.anchor)
    if normalized.anchor != os.sep or normalized == filesystem_root:
        raise TaskRegistryIntegrityError("compiled registry is not a regular file")

    descriptors: list[int] = []
    directory_captures: list[tuple[int, str, int, tuple[int, ...]]] = []
    primary_error: BaseException | None = None
    failure_message = "cannot resolve compiled registry"
    try:
        try:
            filesystem_root_path_before = filesystem_root.lstat()
            if stat.S_ISLNK(filesystem_root_path_before.st_mode) or not stat.S_ISDIR(
                filesystem_root_path_before.st_mode
            ):
                raise TaskRegistryIntegrityError(
                    "compiled registry path contains a symlink or invalid root"
                )

            failure_message = "cannot open compiled registry"
            filesystem_root_descriptor = os.open(filesystem_root, directory_flags)
            descriptors.append(filesystem_root_descriptor)
            failure_message = "cannot stat compiled registry"
            filesystem_root_opened_before = os.fstat(filesystem_root_descriptor)
            filesystem_root_signature = _stat_signature(filesystem_root_path_before)
            if not stat.S_ISDIR(
                filesystem_root_opened_before.st_mode
            ) or filesystem_root_signature != _stat_signature(
                filesystem_root_opened_before
            ):
                raise TaskRegistryIntegrityError(
                    "compiled registry path changed before open"
                )

            parent_descriptor = filesystem_root_descriptor
            for part in normalized.parts[1:-1]:
                failure_message = "cannot resolve compiled registry"
                path_before = os.stat(
                    part,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if stat.S_ISLNK(path_before.st_mode):
                    raise TaskRegistryIntegrityError(
                        "compiled registry path contains a symlink"
                    )
                if not stat.S_ISDIR(path_before.st_mode):
                    raise TaskRegistryIntegrityError(
                        "compiled registry path ancestor is not a directory"
                    )
                failure_message = "cannot open compiled registry"
                directory_descriptor = os.open(
                    part,
                    directory_flags,
                    dir_fd=parent_descriptor,
                )
                descriptors.append(directory_descriptor)
                failure_message = "cannot stat compiled registry"
                opened_before = os.fstat(directory_descriptor)
                directory_signature = _stat_signature(path_before)
                if not stat.S_ISDIR(
                    opened_before.st_mode
                ) or directory_signature != _stat_signature(opened_before):
                    raise TaskRegistryIntegrityError(
                        "compiled registry path changed before open"
                    )
                directory_captures.append(
                    (
                        parent_descriptor,
                        part,
                        directory_descriptor,
                        directory_signature,
                    )
                )
                parent_descriptor = directory_descriptor

            leaf = normalized.name
            failure_message = "cannot resolve compiled registry"
            path_before = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(path_before.st_mode):
                raise TaskRegistryIntegrityError(
                    "compiled registry path contains a symlink"
                )
            if not stat.S_ISREG(path_before.st_mode):
                raise TaskRegistryIntegrityError(
                    "compiled registry is not a regular file"
                )
            if path_before.st_nlink != 1:
                raise TaskRegistryIntegrityError(
                    "compiled registry must have one filesystem link"
                )
            if (
                path_before.st_size < 0
                or path_before.st_size > MAX_COMPILED_REGISTRY_BYTES
            ):
                raise TaskRegistryIntegrityError("compiled registry exceeds size limit")

            failure_message = "cannot open compiled registry"
            file_descriptor = os.open(
                leaf,
                file_flags,
                dir_fd=parent_descriptor,
            )
            descriptors.append(file_descriptor)
            failure_message = "cannot stat compiled registry"
            opened_before = os.fstat(file_descriptor)
            file_signature = _stat_signature(path_before)
            if not stat.S_ISREG(
                opened_before.st_mode
            ) or file_signature != _stat_signature(opened_before):
                raise TaskRegistryIntegrityError(
                    "compiled registry changed before open"
                )

            remaining = opened_before.st_size
            chunks: list[bytes] = []
            failure_message = "cannot read compiled registry"
            while remaining:
                chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
                if not chunk or len(chunk) > remaining:
                    raise TaskRegistryIntegrityError("short compiled registry read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(file_descriptor, 1):
                raise TaskRegistryIntegrityError(
                    "compiled registry changed during read"
                )
            content = b"".join(chunks)

            failure_message = "cannot restat compiled registry"
            opened_after = os.fstat(file_descriptor)
            failure_message = "cannot resolve compiled registry"
            path_after = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened_after.st_mode)
                or not stat.S_ISREG(path_after.st_mode)
                or opened_after.st_nlink != 1
                or path_after.st_nlink != 1
                or file_signature != _stat_signature(opened_after)
                or file_signature != _stat_signature(path_after)
                or len(content) != opened_after.st_size
            ):
                raise TaskRegistryIntegrityError(
                    "compiled registry changed during read"
                )

            for (
                directory_parent,
                directory_name,
                directory_descriptor,
                directory_signature,
            ) in reversed(directory_captures):
                failure_message = "cannot restat compiled registry"
                directory_opened_after = os.fstat(directory_descriptor)
                failure_message = "cannot resolve compiled registry"
                directory_path_after = os.stat(
                    directory_name,
                    dir_fd=directory_parent,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(directory_opened_after.st_mode)
                    or not stat.S_ISDIR(directory_path_after.st_mode)
                    or stat.S_ISLNK(directory_path_after.st_mode)
                    or directory_signature != _stat_signature(directory_opened_after)
                    or directory_signature != _stat_signature(directory_path_after)
                ):
                    raise TaskRegistryIntegrityError(
                        "compiled registry path changed during read"
                    )

            failure_message = "cannot restat compiled registry"
            filesystem_root_opened_after = os.fstat(filesystem_root_descriptor)
            failure_message = "cannot resolve compiled registry"
            filesystem_root_path_after = filesystem_root.lstat()
            if (
                not stat.S_ISDIR(filesystem_root_opened_after.st_mode)
                or not stat.S_ISDIR(filesystem_root_path_after.st_mode)
                or stat.S_ISLNK(filesystem_root_path_after.st_mode)
                or filesystem_root_signature
                != _stat_signature(filesystem_root_opened_after)
                or filesystem_root_signature
                != _stat_signature(filesystem_root_path_after)
            ):
                raise TaskRegistryIntegrityError(
                    "compiled registry path changed during read"
                )
            return content
        except OSError, ValueError:
            raise TaskRegistryIntegrityError(failure_message) from None
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
            raise TaskRegistryIntegrityError("cannot close compiled registry") from None


def _require_repository(value: object) -> ContractRepository:
    """Retain runtime validation at the statically typed adapter boundary."""

    if not isinstance(value, ContractRepository):
        raise TaskRegistryIntegrityError(
            "repository must be a verified ContractRepository"
        )
    return value


class CompiledTaskRegistry(TaskRegistry):
    """Resolve frozen task contracts from one explicitly pinned JSON artifact.

    YAML compilation and catalog/frontmatter reconciliation are generation-time
    responsibilities. This adapter imports no YAML parser, provider SDK, network,
    database, or activation policy.
    """

    def __init__(
        self,
        repository: ContractRepository,
        compiled_registry_path: Path | str,
        *,
        expected_sha256: str,
    ) -> None:
        self._repository = _require_repository(repository)
        requested_path = Path(compiled_registry_path)
        normalized_path = Path(os.path.abspath(requested_path))
        if not requested_path.is_absolute() or requested_path != normalized_path:
            raise TaskRegistryIntegrityError(
                "compiled registry path must be absolute and normalized"
            )
        self._path = normalized_path
        self._expected_sha256 = _require_sha256(
            expected_sha256, source="expected compiled registry digest"
        )
        content = self._read_compiled_registry()
        self._tasks = MappingProxyType(self._load_tasks(content))

    @property
    def task_codes(self) -> tuple[str, ...]:
        """Return registered task codes in deterministic order."""

        self._read_compiled_registry()
        return tuple(self._tasks)

    def get(self, task_code: str) -> TaskContract:
        """Return one immutable task contract after selected-byte revalidation."""

        self._read_compiled_registry()
        if (
            type(task_code) is not str
            or not task_code
            or len(task_code) > 200
            or task_code != task_code.strip()
            or any(
                character.isspace() or not character.isprintable()
                for character in task_code
            )
        ):
            raise InvalidTaskCode("task_code is invalid")
        contract = self._tasks.get(task_code)
        if contract is None:
            raise UnknownTaskContract("task contract is not registered")
        self._verify_artifact(
            contract.prompt.artifact_path,
            contract.prompt.sha256,
            label="prompt",
        )
        self._verify_artifact(
            contract.output_schema.artifact_path,
            contract.output_schema.sha256,
            label="output schema",
        )
        return contract

    def _read_compiled_registry(self) -> bytes:
        content = _read_regular_file(self._path)
        if _sha256(content) != self._expected_sha256:
            raise TaskRegistryIntegrityError("compiled registry SHA-256 mismatch")
        return content

    def _verify_artifact(self, path: str, digest: str, *, label: str) -> bytes:
        try:
            content = self._repository.read_bytes(path)
        except Exception as exc:
            raise TaskRegistryIntegrityError(
                f"cannot read registered {label} artifact"
            ) from exc
        if _sha256(content) != digest:
            raise TaskRegistryIntegrityError(f"{label} SHA-256 mismatch")
        return content

    def _load_tasks(self, content: bytes) -> dict[str, TaskContract]:
        try:
            raw_document = parse_strict_json(content, source="compiled AI registry")
        except Exception as exc:
            raise TaskRegistryIntegrityError(
                "invalid compiled AI registry JSON"
            ) from exc
        document = _mapping(raw_document, source="compiled registry")
        _require_exact_keys(
            document, {"document", "task_count", "tasks"}, source="compiled registry"
        )
        metadata = _mapping(document["document"], source="compiled registry.document")
        if dict(metadata) != dict(EXPECTED_DOCUMENT):
            raise TaskRegistryIntegrityError("unexpected compiled registry document")
        task_count = _integer(
            document["task_count"], source="compiled registry.task_count"
        )
        raw_tasks = _sequence(document["tasks"], source="compiled registry.tasks")
        if task_count != len(raw_tasks) or task_count < 1:
            raise TaskRegistryIntegrityError("compiled registry task count mismatch")

        tasks: dict[str, TaskContract] = {}
        previous_code = ""
        for index, raw_task in enumerate(raw_tasks):
            source = f"compiled registry.tasks[{index}]"
            entry = _mapping(raw_task, source=source)
            _require_exact_keys(
                entry,
                {
                    "task",
                    "task_sha256",
                    "prompt",
                    "output_schema",
                    "route",
                    "binding_sha256",
                },
                source=source,
            )
            binding_digest = _require_sha256(
                entry["binding_sha256"], source=f"{source}.binding_sha256"
            )
            unsigned_entry = {
                key: value for key, value in entry.items() if key != "binding_sha256"
            }
            if _canonical_sha256(unsigned_entry) != binding_digest:
                raise TaskRegistryIntegrityError("task binding SHA-256 mismatch")

            task = _mapping(entry["task"], source=f"{source}.task")
            task_digest = _require_sha256(
                entry["task_sha256"], source=f"{source}.task_sha256"
            )
            if _canonical_sha256(task) != task_digest:
                raise TaskRegistryIntegrityError("task SHA-256 mismatch")
            task_code = _string(
                task.get("task_code"), source=f"{source}.task.task_code"
            )
            if task_code <= previous_code or task_code in tasks:
                raise TaskRegistryIntegrityError(
                    "compiled tasks must be uniquely sorted by task_code"
                )
            previous_code = task_code

            prompt_contract = self._load_prompt(entry["prompt"], task, source=source)
            schema_contract = self._load_schema(
                entry["output_schema"], task, source=source
            )
            route_contract = self._load_route(entry["route"], task, source=source)
            try:
                contract = TaskContract(
                    task_code=task_code,
                    catalog_id=_string(task.get("id"), source=f"{source}.task.id"),
                    lifecycle=_string(
                        task.get("lifecycle"), source=f"{source}.task.lifecycle"
                    ),
                    risk_level=_string(
                        task.get("risk_level"), source=f"{source}.task.risk_level"
                    ),
                    sha256=task_digest,
                    binding_sha256=binding_digest,
                    prompt=prompt_contract,
                    output_schema=schema_contract,
                    route=route_contract,
                    metadata=_frozen_mapping(task, source=f"{source}.task"),
                )
            except ValueError as exc:
                raise TaskRegistryIntegrityError(
                    "invalid immutable task contract"
                ) from exc
            tasks[task_code] = contract
        return tasks

    def _load_prompt(
        self, value: object, task: Mapping[str, object], *, source: str
    ) -> PromptContract:
        prompt = _mapping(value, source=f"{source}.prompt")
        _require_exact_keys(
            prompt,
            {
                "prompt_code",
                "version",
                "task_code",
                "status",
                "locale",
                "artifact_path",
                "sha256",
                "metadata",
            },
            source=f"{source}.prompt",
        )
        prompt_code = _string(prompt["prompt_code"], source=f"{source}.prompt_code")
        task_code = _string(prompt["task_code"], source=f"{source}.prompt.task_code")
        if prompt_code != task.get("prompt_code") or task_code != task.get("task_code"):
            raise TaskRegistryIntegrityError("task/prompt cross-reference mismatch")
        artifact_path = _string(
            prompt["artifact_path"], source=f"{source}.prompt.artifact_path"
        )
        digest = _require_sha256(prompt["sha256"], source=f"{source}.prompt.sha256")
        content = self._verify_artifact(artifact_path, digest, label="prompt")
        try:
            text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TaskRegistryIntegrityError("prompt is not valid UTF-8") from exc
        metadata = _mapping(prompt["metadata"], source=f"{source}.prompt.metadata")
        try:
            return PromptContract(
                prompt_code=prompt_code,
                version=_integer(prompt["version"], source=f"{source}.prompt.version"),
                task_code=task_code,
                status=_string(prompt["status"], source=f"{source}.prompt.status"),
                locale=_string(prompt["locale"], source=f"{source}.prompt.locale"),
                artifact_path=artifact_path,
                sha256=digest,
                content=text,
                metadata=_frozen_mapping(metadata, source=f"{source}.prompt.metadata"),
            )
        except ValueError as exc:
            raise TaskRegistryIntegrityError(
                "invalid immutable prompt contract"
            ) from exc

    def _load_schema(
        self, value: object, task: Mapping[str, object], *, source: str
    ) -> OutputSchemaContract:
        schema = _mapping(value, source=f"{source}.output_schema")
        _require_exact_keys(
            schema,
            {"schema_id", "artifact_path", "sha256", "metadata"},
            source=f"{source}.output_schema",
        )
        artifact_path = _string(
            schema["artifact_path"], source=f"{source}.output_schema.artifact_path"
        )
        digest = _require_sha256(
            schema["sha256"], source=f"{source}.output_schema.sha256"
        )
        content = self._verify_artifact(artifact_path, digest, label="output schema")
        try:
            raw_document = parse_strict_json(content, source=artifact_path)
        except Exception as exc:
            raise TaskRegistryIntegrityError("invalid output schema JSON") from exc
        document = _mapping(raw_document, source=f"{source}.output_schema.document")
        schema_id = _string(
            schema["schema_id"], source=f"{source}.output_schema.schema_id"
        )
        if (
            document.get("$id") != schema_id
            or task.get("output_schema_sha256") != digest
        ):
            raise TaskRegistryIntegrityError("task/output-schema binding mismatch")
        metadata = _mapping(
            schema["metadata"], source=f"{source}.output_schema.metadata"
        )
        try:
            return OutputSchemaContract(
                schema_id=schema_id,
                artifact_path=artifact_path,
                sha256=digest,
                document=_frozen_mapping(
                    document, source=f"{source}.output_schema.document"
                ),
                metadata=_frozen_mapping(
                    metadata, source=f"{source}.output_schema.metadata"
                ),
            )
        except ValueError as exc:
            raise TaskRegistryIntegrityError(
                "invalid immutable schema contract"
            ) from exc

    def _load_route(
        self, value: object, task: Mapping[str, object], *, source: str
    ) -> RouteContract:
        route = _mapping(value, source=f"{source}.route")
        _require_exact_keys(
            route, {"route_code", "sha256", "metadata"}, source=f"{source}.route"
        )
        route_code = _string(route["route_code"], source=f"{source}.route.route_code")
        metadata = _mapping(route["metadata"], source=f"{source}.route.metadata")
        digest = _require_sha256(route["sha256"], source=f"{source}.route.sha256")
        if (
            route_code != task.get("route_code")
            or metadata.get("route_code") != route_code
        ):
            raise TaskRegistryIntegrityError("task/route cross-reference mismatch")
        if _canonical_sha256(metadata) != digest:
            raise TaskRegistryIntegrityError("route SHA-256 mismatch")
        try:
            return RouteContract(
                route_code=route_code,
                sha256=digest,
                metadata=_frozen_mapping(metadata, source=f"{source}.route.metadata"),
            )
        except ValueError as exc:
            raise TaskRegistryIntegrityError(
                "invalid immutable route contract"
            ) from exc
