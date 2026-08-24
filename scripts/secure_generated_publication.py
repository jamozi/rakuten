"""Foreign-preserving local publication for owner-generated artifacts.

The helper is intentionally Linux-only and fails closed when ``renameat2`` is
not available.  Existing destinations are exchanged atomically so a target
that changes after validation can be restored without overwriting it.  Missing
destinations are installed with a no-clobber hard-link transaction.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat
from typing import Final, NoReturn


class SecurePublicationError(RuntimeError):
    """Closed failure emitted by the secure publication boundary."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise SecurePublicationError(code) from None


@dataclass(frozen=True, slots=True)
class _DirectoryBinding:
    descriptor: int
    identity: tuple[int, int, int]
    parent_descriptor: int | None = None
    name: str | None = None
    absolute_path: Path | None = None


@dataclass(slots=True)
class _StagedOutput:
    descriptors: list[int]
    directory_bindings: list[_DirectoryBinding]
    parent_descriptor: int
    target_name: str
    temporary_name: str
    temporary_descriptor: int
    temporary_identity: tuple[int, ...]
    previous_identity: tuple[int, ...] | None
    namespace: str
    commit_started: bool = False


_RENAME_NOREPLACE: Final = 1
_RENAME_EXCHANGE: Final = 2


def _directory_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode)


def _leaf_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
    )


def _same_inode_material(left: tuple[int, ...], right: tuple[int, ...]) -> bool:
    # Link count is expected to change during a no-clobber hard-link install.
    return left[:5] == right[:5] and left[6:] == right[6:]


def _renameat2(
    parent_descriptor: int, source: str, destination: str, flags: int
) -> None:
    if (
        type(parent_descriptor) is not int
        or parent_descriptor < 0
        or type(source) is not str
        or not source
        or "/" in source
        or "\x00" in source
        or type(destination) is not str
        or not destination
        or "/" in destination
        or "\x00" in destination
        or flags not in {_RENAME_NOREPLACE, _RENAME_EXCHANGE}
    ):
        _fail("SECURE_PUBLICATION_RENAME_INPUT_INVALID")
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            os.fsencode(source),
            parent_descriptor,
            os.fsencode(destination),
            flags,
        )
    except AttributeError, OSError:
        _fail("SECURE_PUBLICATION_RENAME_UNAVAILABLE")
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number == errno.EEXIST:
            raise FileExistsError("SECURE_PUBLICATION_DESTINATION_EXISTS") from None
        _fail("SECURE_PUBLICATION_RENAME_FAILED")


def _rename_exchange(parent_descriptor: int, left: str, right: str) -> None:
    _renameat2(parent_descriptor, left, right, _RENAME_EXCHANGE)


def _rename_noreplace(parent_descriptor: int, source: str, destination: str) -> None:
    _renameat2(parent_descriptor, source, destination, _RENAME_NOREPLACE)


def _raw_identity(parent_descriptor: int, name: str) -> tuple[int, ...] | None:
    try:
        value = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return _leaf_identity(value)


def _regular_identity(parent_descriptor: int, name: str) -> tuple[int, ...] | None:
    identity = _raw_identity(parent_descriptor, name)
    if identity is None:
        return None
    if not stat.S_ISREG(identity[2]) or identity[5] != 1:
        _fail("SECURE_PUBLICATION_LEAF_INVALID")
    return identity


def _validate_directories(bindings: tuple[_DirectoryBinding, ...]) -> None:
    for binding in reversed(bindings):
        opened = os.fstat(binding.descriptor)
        if binding.absolute_path is not None:
            named = binding.absolute_path.lstat()
        else:
            if binding.parent_descriptor is None or binding.name is None:
                _fail("SECURE_PUBLICATION_DIRECTORY_BINDING_INVALID")
            named = os.stat(
                binding.name,
                dir_fd=binding.parent_descriptor,
                follow_symlinks=False,
            )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or stat.S_ISLNK(named.st_mode)
            or _directory_identity(opened) != binding.identity
            or _directory_identity(named) != binding.identity
        ):
            _fail("SECURE_PUBLICATION_DIRECTORY_IDENTITY_CHANGED")


def _open_output_parent(
    destination: Path,
) -> tuple[list[int], list[_DirectoryBinding], int]:
    absolute = Path(os.path.abspath(destination))
    if destination != absolute or not absolute.is_absolute() or not absolute.name:
        _fail("SECURE_PUBLICATION_DESTINATION_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    filesystem_root = Path(absolute.anchor)
    root_before = filesystem_root.lstat()
    if not stat.S_ISDIR(root_before.st_mode) or stat.S_ISLNK(root_before.st_mode):
        _fail("SECURE_PUBLICATION_ROOT_INVALID")
    descriptors: list[int] = []
    bindings: list[_DirectoryBinding] = []
    root_descriptor = os.open(filesystem_root, flags)
    descriptors.append(root_descriptor)
    try:
        root_identity = _directory_identity(root_before)
        if _directory_identity(os.fstat(root_descriptor)) != root_identity:
            _fail("SECURE_PUBLICATION_ROOT_IDENTITY_CHANGED")
        bindings.append(
            _DirectoryBinding(
                descriptor=root_descriptor,
                identity=root_identity,
                absolute_path=filesystem_root,
            )
        )
        current = root_descriptor
        for part in absolute.parent.parts[1:]:
            before = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
                _fail("SECURE_PUBLICATION_PARENT_INVALID")
            child = os.open(part, flags, dir_fd=current)
            descriptors.append(child)
            identity = _directory_identity(before)
            if _directory_identity(os.fstat(child)) != identity:
                _fail("SECURE_PUBLICATION_PARENT_IDENTITY_CHANGED")
            bindings.append(
                _DirectoryBinding(
                    descriptor=child,
                    identity=identity,
                    parent_descriptor=current,
                    name=part,
                )
            )
            current = child
        _validate_directories(tuple(bindings))
        return descriptors, bindings, current
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _read_existing(
    parent_descriptor: int, name: str, *, maximum_bytes: int
) -> tuple[int, ...] | None:
    identity = _regular_identity(parent_descriptor, name)
    if identity is None:
        return None
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if _leaf_identity(opened) != identity or opened.st_size > maximum_bytes:
            _fail("SECURE_PUBLICATION_EXISTING_IDENTITY_INVALID")
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail("SECURE_PUBLICATION_EXISTING_READ_TRUNCATED")
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail("SECURE_PUBLICATION_EXISTING_READ_GREW")
        if (
            _leaf_identity(os.fstat(descriptor)) != identity
            or _regular_identity(parent_descriptor, name) != identity
        ):
            _fail("SECURE_PUBLICATION_EXISTING_IDENTITY_CHANGED")
        return identity
    finally:
        os.close(descriptor)


def _create_staged_leaf(
    *,
    parent_descriptor: int,
    target_name: str,
    namespace: str,
    ordinal: int,
    payload: bytes,
) -> tuple[str, int, tuple[int, ...]]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = -1
    name = ""
    for suffix in range(100):
        candidate = f".{target_name}.{namespace}-{os.getpid()}-{ordinal}-{suffix}"
        try:
            descriptor = os.open(candidate, flags, 0o600, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        name = candidate
        break
    if descriptor < 0 or not name:
        _fail("SECURE_PUBLICATION_STAGE_NAME_EXHAUSTED")
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("SECURE_PUBLICATION_STAGE_WRITE_FAILED")
            view = view[written:]
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = _leaf_identity(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != len(payload)
            or stat.S_IMODE(opened.st_mode) != 0o644
            or _leaf_identity(named) != identity
        ):
            _fail("SECURE_PUBLICATION_STAGE_IDENTITY_INVALID")
        return name, descriptor, identity
    except BaseException:
        try:
            if name and descriptor >= 0:
                observed = _raw_identity(parent_descriptor, name)
                opened_identity = _leaf_identity(os.fstat(descriptor))
                if observed == opened_identity:
                    os.unlink(name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        raise


def _stage_output(
    destination: Path,
    payload: bytes,
    ordinal: int,
    *,
    namespace: str,
    maximum_bytes: int,
) -> _StagedOutput:
    descriptors, bindings, parent_descriptor = _open_output_parent(destination)
    temporary_name = ""
    temporary_descriptor = -1
    try:
        previous_identity = _read_existing(
            parent_descriptor,
            destination.name,
            maximum_bytes=maximum_bytes,
        )
        temporary_name, temporary_descriptor, temporary_identity = _create_staged_leaf(
            parent_descriptor=parent_descriptor,
            target_name=destination.name,
            namespace=namespace,
            ordinal=ordinal,
            payload=payload,
        )
        _validate_directories(tuple(bindings))
        return _StagedOutput(
            descriptors=descriptors,
            directory_bindings=bindings,
            parent_descriptor=parent_descriptor,
            target_name=destination.name,
            temporary_name=temporary_name,
            temporary_descriptor=temporary_descriptor,
            temporary_identity=temporary_identity,
            previous_identity=previous_identity,
            namespace=namespace,
        )
    except BaseException:
        cleanup_failed = False
        if temporary_name and temporary_descriptor >= 0:
            try:
                if _raw_identity(parent_descriptor, temporary_name) == _leaf_identity(
                    os.fstat(temporary_descriptor)
                ):
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
            except BaseException:
                cleanup_failed = True
            try:
                os.close(temporary_descriptor)
            except BaseException:
                cleanup_failed = True
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except BaseException:
                cleanup_failed = True
        if cleanup_failed:
            _fail("SECURE_PUBLICATION_STAGE_CLEANUP_FAILED")
        raise


def _commit_stage(stage: _StagedOutput) -> None:
    stage.commit_started = True
    if stage.previous_identity is not None:
        _rename_exchange(
            stage.parent_descriptor,
            stage.temporary_name,
            stage.target_name,
        )
        target = _raw_identity(stage.parent_descriptor, stage.target_name)
        displaced = _raw_identity(stage.parent_descriptor, stage.temporary_name)
        target_is_generated = target is not None and _same_inode_material(
            target, stage.temporary_identity
        )
        if target_is_generated and displaced == stage.previous_identity:
            pass
        elif target_is_generated and displaced is not None:
            # The destination changed before the exchange.  The displaced
            # foreign leaf is restored to its original name atomically.
            _rename_exchange(
                stage.parent_descriptor,
                stage.temporary_name,
                stage.target_name,
            )
            os.fsync(stage.parent_descriptor)
            if (
                _raw_identity(stage.parent_descriptor, stage.target_name) != displaced
                or _raw_identity(stage.parent_descriptor, stage.temporary_name)
                != target
            ):
                _fail("SECURE_PUBLICATION_EXCHANGE_RESTORE_FAILED")
            _fail("SECURE_PUBLICATION_TARGET_RACED")
        else:
            # The destination changed after the exchange.  Preserve that
            # foreign leaf in place and retain the displaced previous target
            # under the private recovery name; moving either would clobber
            # external state.
            _fail("SECURE_PUBLICATION_POST_EXCHANGE_TARGET_RACED")
    else:
        try:
            os.link(
                stage.temporary_name,
                stage.target_name,
                src_dir_fd=stage.parent_descriptor,
                dst_dir_fd=stage.parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            _fail("SECURE_PUBLICATION_TARGET_RACED")
        target = _raw_identity(stage.parent_descriptor, stage.target_name)
        temporary = _raw_identity(stage.parent_descriptor, stage.temporary_name)
        if (
            target is None
            or temporary is None
            or target != temporary
            or target[5] != 2
            or not _same_inode_material(target, stage.temporary_identity)
        ):
            _fail("SECURE_PUBLICATION_LINK_INSTALL_INVALID")
        os.unlink(stage.temporary_name, dir_fd=stage.parent_descriptor)
        stage.temporary_name = ""
        target = _regular_identity(stage.parent_descriptor, stage.target_name)
        if target is None or not _same_inode_material(target, stage.temporary_identity):
            _fail("SECURE_PUBLICATION_LINK_INSTALL_RACED")
    os.fsync(stage.parent_descriptor)


def _move_target_noreplace(stage: _StagedOutput, purpose: str) -> str:
    for suffix in range(100):
        destination = (
            f".{stage.target_name}.{stage.namespace}-{purpose}-{os.getpid()}-{suffix}"
        )
        try:
            _rename_noreplace(
                stage.parent_descriptor,
                stage.target_name,
                destination,
            )
        except FileExistsError:
            continue
        return destination
    _fail("SECURE_PUBLICATION_ROLLBACK_NAME_EXHAUSTED")


def _rollback_stage(stage: _StagedOutput) -> None:
    current = _raw_identity(stage.parent_descriptor, stage.target_name)
    if current == stage.previous_identity:
        return
    if stage.previous_identity is not None:
        if current is None or not _same_inode_material(
            current, stage.temporary_identity
        ):
            _fail("SECURE_PUBLICATION_ROLLBACK_FOREIGN_TARGET")
        displaced = _raw_identity(stage.parent_descriptor, stage.temporary_name)
        if displaced != stage.previous_identity:
            _fail("SECURE_PUBLICATION_ROLLBACK_BACKUP_INVALID")
        _rename_exchange(
            stage.parent_descriptor,
            stage.target_name,
            stage.temporary_name,
        )
        if _raw_identity(
            stage.parent_descriptor, stage.target_name
        ) != displaced or not _same_inode_material(
            _raw_identity(stage.parent_descriptor, stage.temporary_name) or (),
            current,
        ):
            _fail("SECURE_PUBLICATION_ROLLBACK_EXCHANGE_INVALID")
        os.fsync(stage.parent_descriptor)
        return
    if current is None:
        return
    if not _same_inode_material(current, stage.temporary_identity):
        _fail("SECURE_PUBLICATION_ROLLBACK_FOREIGN_TARGET")
    rollback_name = _move_target_noreplace(stage, "rollback")
    moved = _raw_identity(stage.parent_descriptor, rollback_name)
    if moved is None or not _same_inode_material(moved, stage.temporary_identity):
        if moved is not None:
            try:
                _rename_noreplace(
                    stage.parent_descriptor,
                    rollback_name,
                    stage.target_name,
                )
            except FileExistsError:
                pass
        _fail("SECURE_PUBLICATION_ROLLBACK_MOVE_RACED")
    os.unlink(rollback_name, dir_fd=stage.parent_descriptor)
    os.fsync(stage.parent_descriptor)
    if _raw_identity(stage.parent_descriptor, stage.target_name) is not None:
        _fail("SECURE_PUBLICATION_ROLLBACK_TARGET_REAPPEARED")


def _cleanup_named_leaf(
    stage: _StagedOutput, name: str | None, identity: tuple[int, ...] | None
) -> None:
    if name is None:
        return
    current = _raw_identity(stage.parent_descriptor, name)
    if current is None:
        return
    if identity is None or current != identity:
        _fail("SECURE_PUBLICATION_CLEANUP_FOREIGN_TARGET")
    os.unlink(name, dir_fd=stage.parent_descriptor)
    os.fsync(stage.parent_descriptor)


def _close_stage(stage: _StagedOutput) -> None:
    os.close(stage.temporary_descriptor)
    for descriptor in reversed(stage.descriptors):
        os.close(descriptor)


def publish_generated(
    artifacts: tuple[tuple[Path, bytes], ...],
    *,
    namespace: str,
    maximum_payload_bytes: int,
) -> None:
    """Publish a bounded artifact set without clobbering raced targets."""

    if (
        type(namespace) is not str
        or not namespace
        or len(namespace) > 32
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
            for character in namespace
        )
        or type(maximum_payload_bytes) is not int
        or maximum_payload_bytes <= 0
        or maximum_payload_bytes > 64 * 1024 * 1024
        or not artifacts
        or any(
            not isinstance(path, Path)
            or not path.is_absolute()
            or type(payload) is not bytes
            or not payload
            or len(payload) > maximum_payload_bytes
            for path, payload in artifacts
        )
        or len({path for path, _payload in artifacts}) != len(artifacts)
    ):
        _fail("SECURE_PUBLICATION_INPUT_INVALID")

    stages: list[_StagedOutput] = []
    primary: BaseException | None = None
    commits_complete = False
    try:
        for ordinal, (destination, payload) in enumerate(artifacts):
            stages.append(
                _stage_output(
                    destination,
                    payload,
                    ordinal,
                    namespace=namespace,
                    maximum_bytes=maximum_payload_bytes,
                )
            )
        for stage in stages:
            _validate_directories(tuple(stage.directory_bindings))
            if (
                _regular_identity(stage.parent_descriptor, stage.target_name)
                != stage.previous_identity
                or _regular_identity(stage.parent_descriptor, stage.temporary_name)
                != stage.temporary_identity
            ):
                _fail("SECURE_PUBLICATION_PRECOMMIT_IDENTITY_CHANGED")
            _commit_stage(stage)
            target = _regular_identity(stage.parent_descriptor, stage.target_name)
            if target is None or not _same_inode_material(
                target, stage.temporary_identity
            ):
                _fail("SECURE_PUBLICATION_COMMIT_IDENTITY_INVALID")
            _validate_directories(tuple(stage.directory_bindings))
        commits_complete = True
        for stage in stages:
            if stage.previous_identity is not None:
                _cleanup_named_leaf(
                    stage,
                    stage.temporary_name,
                    stage.previous_identity,
                )
                stage.temporary_name = ""
    except BaseException as failure:
        primary = failure
        if commits_complete:
            raise
        rollback_failed = False
        for stage in reversed(stages):
            if not stage.commit_started:
                continue
            try:
                _rollback_stage(stage)
            except BaseException:
                rollback_failed = True
        if rollback_failed:
            _fail("SECURE_PUBLICATION_ROLLBACK_FAILED")
        if isinstance(failure, Exception):
            _fail("SECURE_PUBLICATION_TRANSACTION_FAILED")
        raise
    finally:
        cleanup_failed = False
        for stage in stages:
            try:
                _cleanup_named_leaf(
                    stage,
                    stage.temporary_name or None,
                    stage.temporary_identity,
                )
            except BaseException:
                cleanup_failed = True
            try:
                _close_stage(stage)
            except BaseException:
                cleanup_failed = True
        if cleanup_failed and primary is None:
            _fail("SECURE_PUBLICATION_FINAL_CLEANUP_FAILED")
