"""Owner-private JSON adapter for the ST-1704 local pilot ledger."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import ctypes
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Final, NoReturn

from raos.domain.editorial.owner_local_pilot import (
    AppendDisposition,
    PilotFailure,
    PilotFailureCode,
    PilotLedger,
    PilotObservation,
    append_observation,
    canonical_bytes,
    empty_ledger,
    fail_pilot,
    parse_ledger,
)
from raos.ports.owner_local_pilot import PilotAppendResult


PILOT_DIRECTORY: Final = "st1704-owner-local-pilot"
LEDGER_FILE: Final = "ledger.v1.json"
INPUT_FILE: Final = "observation-input.v1.json"
LOCK_FILE: Final = "ledger.lock"
STAGE_FILE: Final = "ledger.v1.json.preparing"
MAX_LEDGER_BYTES: Final = 1_048_576
MAX_INPUT_BYTES: Final = 65_536
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_RENAME_EXCHANGE: Final = 2


def _fail() -> NoReturn:
    fail_pilot(PilotFailureCode.STORE_UNSAFE)


def _fsync(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        _fail()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_pilot()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    fail_pilot()


def decode_strict_json(raw: bytes) -> object:
    if type(raw) is not bytes or not raw or raw.startswith(b"\xef\xbb\xbf"):
        fail_pilot()
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except PilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, RecursionError:
        fail_pilot()


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail()
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        return current
    except OSError:
        os.close(current)
        _fail()


def _safe_directory(fd: int, *, mode: int | None) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or (mode is not None and stat.S_IMODE(observed.st_mode) != mode)
    ):
        _fail()
    return observed


def _open_child_directory(parent_fd: int, name: str, *, create: bool) -> int:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            fail_pilot(PilotFailureCode.STORE_NOT_INITIALIZED)
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            _fsync(parent_fd)
            return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail()
    except OSError:
        _fail()


def _safe_file(fd: int, *, maximum: int, allow_empty: bool = False) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != 0o600
        or observed.st_nlink != 1
        or observed.st_size > maximum
        or (not allow_empty and observed.st_size == 0)
    ):
        _fail()
    return observed


def _read_file_with_identity(
    directory_fd: int, name: str, *, maximum: int
) -> tuple[bytes, os.stat_result]:
    try:
        fd = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        fail_pilot(PilotFailureCode.STORE_NOT_INITIALIZED)
    except OSError:
        _fail()
    try:
        before = _safe_file(fd, maximum=maximum)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(remaining, 65_536))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            _fail()
        after = _safe_file(fd, maximum=maximum)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail()
        try:
            rebound_fd = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
        except OSError:
            _fail()
        try:
            rebound = _safe_file(rebound_fd, maximum=maximum)
            if (rebound.st_dev, rebound.st_ino) != (before.st_dev, before.st_ino):
                _fail()
        finally:
            os.close(rebound_fd)
        return b"".join(chunks), before
    finally:
        os.close(fd)


def _read_file(directory_fd: int, name: str, *, maximum: int) -> bytes:
    return _read_file_with_identity(directory_fd, name, maximum=maximum)[0]


def _exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        _fail()
    return True


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            _fail()
        offset += written


def _open_anonymous_file(directory_fd: int, payload: bytes) -> int:
    anonymous_flag = getattr(os, "O_TMPFILE", 0)
    if not anonymous_flag:
        _fail()
    try:
        descriptor = os.open(
            ".",
            os.O_RDWR | anonymous_flag | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
    except OSError:
        _fail()
    try:
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o600)
        _fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 0
            or observed.st_size != len(payload)
        ):
            _fail()
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _link_descriptor(directory_fd: int, descriptor: int, name: str) -> None:
    try:
        os.link(
            f"/proc/self/fd/{descriptor}",
            name,
            dst_dir_fd=directory_fd,
            follow_symlinks=True,
        )
    except OSError:
        _fail()


def _rename_exchange(directory_fd: int, left: str, right: str) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError, OSError:
        _fail()
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        os.fsencode(left),
        directory_fd,
        os.fsencode(right),
        _RENAME_EXCHANGE,
    )
    if result != 0:
        _fail()


def _same_events_prefix(first: PilotLedger, second: PilotLedger) -> bool:
    if len(first.events) > len(second.events):
        return False
    return all(
        left.payload() == right.payload()
        for left, right in zip(first.events, second.events, strict=False)
    )


class OwnerLocalPilotJsonStore:
    """Strict fixed-path adapter with descriptor-relative atomic writes."""

    __slots__ = ("_root", "_root_identity")

    def __init__(
        self,
        repository_root: Path,
        *,
        expected_root_identity: tuple[int, int] | None = None,
    ) -> None:
        if not repository_root.is_absolute():
            _fail()
        if expected_root_identity is not None and (
            type(expected_root_identity) is not tuple
            or len(expected_root_identity) != 2
            or any(
                type(value) is not int or value < 0 for value in expected_root_identity
            )
        ):
            _fail()
        self._root = repository_root
        self._root_identity = expected_root_identity

    def _validate_expected_root(self, root_fd: int) -> None:
        observed = _safe_directory(root_fd, mode=None)
        if (
            self._root_identity is not None
            and (
                observed.st_dev,
                observed.st_ino,
            )
            != self._root_identity
        ):
            _fail()

    @contextmanager
    def _layout(self, *, create: bool) -> Generator[tuple[int, int, int], None, None]:
        root_fd = _open_absolute_directory(self._root)
        secrets_fd = -1
        pilot_fd = -1
        try:
            self._validate_expected_root(root_fd)
            secrets_fd = _open_child_directory(root_fd, ".secrets", create=create)
            _safe_directory(secrets_fd, mode=0o700)
            pilot_fd = _open_child_directory(secrets_fd, PILOT_DIRECTORY, create=create)
            _safe_directory(pilot_fd, mode=0o700)
            yield root_fd, secrets_fd, pilot_fd
        finally:
            if root_fd >= 0 and secrets_fd >= 0 and pilot_fd >= 0:
                self._rebind_layout(root_fd, secrets_fd, pilot_fd)
            if pilot_fd >= 0:
                os.close(pilot_fd)
            if secrets_fd >= 0:
                os.close(secrets_fd)
            os.close(root_fd)

    @contextmanager
    def _exclusive_lock(
        self,
        root_fd: int,
        secrets_fd: int,
        pilot_fd: int,
        ledger_guard: list[tuple[PilotLedger, os.stat_result]],
    ) -> Generator[None, None, None]:
        try:
            lock_fd = os.open(
                LOCK_FILE,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=pilot_fd,
            )
        except OSError:
            _fail()
        try:
            _safe_file(lock_fd, maximum=0, allow_empty=True)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail_pilot(PilotFailureCode.STORE_BUSY)
            locked = _safe_file(lock_fd, maximum=0, allow_empty=True)
            self._rebind_layout(root_fd, secrets_fd, pilot_fd)
            self._rebind_file(
                pilot_fd,
                LOCK_FILE,
                locked,
                maximum=0,
                allow_empty=True,
                writable=True,
            )
            try:
                yield
            finally:
                self._rebind_layout(root_fd, secrets_fd, pilot_fd)
                self._rebind_file(
                    pilot_fd,
                    LOCK_FILE,
                    locked,
                    maximum=0,
                    allow_empty=True,
                    writable=True,
                )
                if len(ledger_guard) > 1:
                    _fail()
                if ledger_guard:
                    expected_ledger, expected_identity = ledger_guard[0]
                    self._verify_terminal_ledger(
                        pilot_fd,
                        expected_ledger,
                        expected_identity,
                    )
        finally:
            os.close(lock_fd)

    def _rebind_layout(
        self, root_fd: int, held_secrets_fd: int, held_pilot_fd: int
    ) -> None:
        rebound_root = _open_absolute_directory(self._root)
        try:
            expected_root = _safe_directory(root_fd, mode=None)
            observed_root = _safe_directory(rebound_root, mode=None)
            self._validate_expected_root(root_fd)
            self._validate_expected_root(rebound_root)
            if (
                expected_root.st_dev,
                expected_root.st_ino,
            ) != (
                observed_root.st_dev,
                observed_root.st_ino,
            ):
                _fail()
            rebound_secrets = _open_child_directory(
                rebound_root, ".secrets", create=False
            )
            try:
                expected_secrets = _safe_directory(held_secrets_fd, mode=0o700)
                observed_secrets = _safe_directory(rebound_secrets, mode=0o700)
                if (
                    expected_secrets.st_dev,
                    expected_secrets.st_ino,
                ) != (
                    observed_secrets.st_dev,
                    observed_secrets.st_ino,
                ):
                    _fail()
                rebound_pilot = _open_child_directory(
                    rebound_secrets, PILOT_DIRECTORY, create=False
                )
                try:
                    expected_pilot = _safe_directory(held_pilot_fd, mode=0o700)
                    observed_pilot = _safe_directory(rebound_pilot, mode=0o700)
                    if (
                        expected_pilot.st_dev,
                        expected_pilot.st_ino,
                    ) != (
                        observed_pilot.st_dev,
                        observed_pilot.st_ino,
                    ):
                        _fail()
                finally:
                    os.close(rebound_pilot)
            finally:
                os.close(rebound_secrets)
        finally:
            os.close(rebound_root)

    def _rebind_file(
        self,
        directory_fd: int,
        name: str,
        expected: os.stat_result,
        *,
        maximum: int,
        allow_empty: bool = False,
        writable: bool = False,
    ) -> None:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC if writable else _FILE_FLAGS
        try:
            rebound_fd = os.open(name, flags, dir_fd=directory_fd)
        except OSError:
            _fail()
        try:
            observed = _safe_file(
                rebound_fd,
                maximum=maximum,
                allow_empty=allow_empty,
            )
            if (expected.st_dev, expected.st_ino) != (
                observed.st_dev,
                observed.st_ino,
            ):
                _fail()
        finally:
            os.close(rebound_fd)

    def _read_ledger(self, pilot_fd: int) -> PilotLedger:
        return self._read_ledger_with_identity(pilot_fd)[0]

    def _read_ledger_with_identity(
        self, pilot_fd: int, name: str = LEDGER_FILE
    ) -> tuple[PilotLedger, os.stat_result]:
        raw, identity = _read_file_with_identity(
            pilot_fd,
            name,
            maximum=MAX_LEDGER_BYTES,
        )
        return parse_ledger(decode_strict_json(raw)), identity

    def _verify_terminal_ledger(
        self,
        pilot_fd: int,
        expected: PilotLedger,
        expected_identity: os.stat_result,
    ) -> None:
        observed, observed_identity = self._read_ledger_with_identity(pilot_fd)
        if observed.payload() != expected.payload() or (
            observed_identity.st_dev,
            observed_identity.st_ino,
        ) != (expected_identity.st_dev, expected_identity.st_ino):
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)

    def _open_terminal_descriptor(
        self, pilot_fd: int, expected_identity: os.stat_result
    ) -> int:
        try:
            descriptor = os.open(LEDGER_FILE, _FILE_FLAGS, dir_fd=pilot_fd)
        except OSError:
            _fail()
        try:
            observed = _safe_file(descriptor, maximum=MAX_LEDGER_BYTES)
            if (observed.st_dev, observed.st_ino) != (
                expected_identity.st_dev,
                expected_identity.st_ino,
            ):
                _fail()
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _restore_terminal_ledger(
        self,
        pilot_fd: int,
        terminal_descriptor: int,
        terminal: PilotLedger,
        terminal_identity: os.stat_result,
    ) -> NoReturn:
        replacement_descriptor = -1
        try:
            if _exists(pilot_fd, STAGE_FILE):
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            held = os.fstat(terminal_descriptor)
            payload = canonical_bytes(terminal.payload()) + b"\n"
            if (
                not stat.S_ISREG(held.st_mode)
                or held.st_uid != os.getuid()
                or stat.S_IMODE(held.st_mode) != 0o600
                or held.st_nlink not in {0, 1}
                or held.st_size != len(payload)
                or (held.st_dev, held.st_ino)
                != (
                    terminal_identity.st_dev,
                    terminal_identity.st_ino,
                )
                or os.pread(terminal_descriptor, len(payload) + 1, 0) != payload
            ):
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            replacement_descriptor = _open_anonymous_file(pilot_fd, payload)
            _link_descriptor(pilot_fd, replacement_descriptor, STAGE_FILE)
            replacement_identity = _safe_file(
                replacement_descriptor,
                maximum=MAX_LEDGER_BYTES,
            )
            if (replacement_identity.st_dev, replacement_identity.st_ino) == (
                terminal_identity.st_dev,
                terminal_identity.st_ino,
            ):
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            _rename_exchange(pilot_fd, STAGE_FILE, LEDGER_FILE)
            _fsync(pilot_fd)
            self._verify_terminal_ledger(
                pilot_fd,
                terminal,
                replacement_identity,
            )
        except BaseException:
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
        finally:
            if replacement_descriptor >= 0:
                os.close(replacement_descriptor)
        fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)

    def _replace_stage(
        self,
        pilot_fd: int,
        *,
        staged: PilotLedger,
        stage_identity: os.stat_result,
        current: PilotLedger,
        current_identity: os.stat_result,
    ) -> None:
        _rename_exchange(pilot_fd, STAGE_FILE, LEDGER_FILE)
        try:
            applied, applied_identity = self._read_ledger_with_identity(pilot_fd)
            preserved, preserved_identity = self._read_ledger_with_identity(
                pilot_fd, STAGE_FILE
            )
            if (
                applied.payload() != staged.payload()
                or preserved.payload() != current.payload()
                or (applied_identity.st_dev, applied_identity.st_ino)
                != (stage_identity.st_dev, stage_identity.st_ino)
                or (preserved_identity.st_dev, preserved_identity.st_ino)
                != (current_identity.st_dev, current_identity.st_ino)
            ):
                _fail()
        except BaseException:
            try:
                _rename_exchange(pilot_fd, STAGE_FILE, LEDGER_FILE)
                restored, restored_identity = self._read_ledger_with_identity(pilot_fd)
                if restored.payload() != current.payload() or (
                    restored_identity.st_dev,
                    restored_identity.st_ino,
                ) != (current_identity.st_dev, current_identity.st_ino):
                    fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
                _fsync(pilot_fd)
            except PilotFailure:
                raise
            except BaseException:
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            raise

    def _unlink_stage(
        self,
        *,
        root_fd: int,
        secrets_fd: int,
        pilot_fd: int,
        stage_identity: os.stat_result,
        terminal_descriptor: int,
        terminal: PilotLedger,
        terminal_identity: os.stat_result,
    ) -> None:
        self._rebind_layout(root_fd, secrets_fd, pilot_fd)
        self._rebind_file(
            pilot_fd,
            STAGE_FILE,
            stage_identity,
            maximum=MAX_LEDGER_BYTES,
        )
        try:
            os.unlink(STAGE_FILE, dir_fd=pilot_fd)
        except OSError:
            _fail()
        _fsync(pilot_fd)
        self._rebind_layout(root_fd, secrets_fd, pilot_fd)
        if _exists(pilot_fd, STAGE_FILE):
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
        try:
            self._verify_terminal_ledger(pilot_fd, terminal, terminal_identity)
        except PilotFailure:
            self._restore_terminal_ledger(
                pilot_fd,
                terminal_descriptor,
                terminal,
                terminal_identity,
            )

    def _atomic_write(
        self,
        *,
        root_fd: int,
        secrets_fd: int,
        pilot_fd: int,
        ledger: PilotLedger,
        previous: PilotLedger | None,
    ) -> os.stat_result:
        if _exists(pilot_fd, STAGE_FILE):
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
        payload = canonical_bytes(ledger.payload()) + b"\n"
        if len(payload) > MAX_LEDGER_BYTES:
            _fail()
        descriptor = _open_anonymous_file(pilot_fd, payload)
        try:
            if previous is None:
                if _exists(pilot_fd, LEDGER_FILE):
                    _fail()
                _link_descriptor(pilot_fd, descriptor, LEDGER_FILE)
                linked = _safe_file(descriptor, maximum=MAX_LEDGER_BYTES)
                self._rebind_layout(root_fd, secrets_fd, pilot_fd)
                self._rebind_file(
                    pilot_fd,
                    LEDGER_FILE,
                    linked,
                    maximum=MAX_LEDGER_BYTES,
                )
                _fsync(pilot_fd)
                observed, observed_identity = self._read_ledger_with_identity(pilot_fd)
                if observed.payload() != ledger.payload() or (
                    observed_identity.st_dev,
                    observed_identity.st_ino,
                ) != (linked.st_dev, linked.st_ino):
                    _fail()
                self._rebind_layout(root_fd, secrets_fd, pilot_fd)
                return linked
            current, current_identity = self._read_ledger_with_identity(pilot_fd)
            if current.payload() != previous.payload():
                _fail()
            _link_descriptor(pilot_fd, descriptor, STAGE_FILE)
            stage_identity = _safe_file(descriptor, maximum=MAX_LEDGER_BYTES)
            self._rebind_layout(root_fd, secrets_fd, pilot_fd)
            self._rebind_file(
                pilot_fd,
                STAGE_FILE,
                stage_identity,
                maximum=MAX_LEDGER_BYTES,
            )
            _fsync(pilot_fd)
            try:
                self._replace_stage(
                    pilot_fd,
                    staged=ledger,
                    stage_identity=stage_identity,
                    current=current,
                    current_identity=current_identity,
                )
            except PilotFailure:
                raise
            except OSError:
                _fail()
            _fsync(pilot_fd)
            _, old_identity = self._read_ledger_with_identity(pilot_fd, STAGE_FILE)
            self._unlink_stage(
                root_fd=root_fd,
                secrets_fd=secrets_fd,
                pilot_fd=pilot_fd,
                stage_identity=old_identity,
                terminal_descriptor=descriptor,
                terminal=ledger,
                terminal_identity=stage_identity,
            )
            self._verify_terminal_ledger(pilot_fd, ledger, stage_identity)
            self._rebind_layout(root_fd, secrets_fd, pilot_fd)
            return stage_identity
        finally:
            os.close(descriptor)

    def _recover(self, *, root_fd: int, secrets_fd: int, pilot_fd: int) -> None:
        if not _exists(pilot_fd, STAGE_FILE):
            return
        staged, stage_identity = self._read_ledger_with_identity(pilot_fd, STAGE_FILE)
        if not _exists(pilot_fd, LEDGER_FILE):
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
        current, current_identity = self._read_ledger_with_identity(pilot_fd)
        if staged.payload() == current.payload():
            terminal_descriptor = self._open_terminal_descriptor(
                pilot_fd, current_identity
            )
            try:
                self._unlink_stage(
                    root_fd=root_fd,
                    secrets_fd=secrets_fd,
                    pilot_fd=pilot_fd,
                    stage_identity=stage_identity,
                    terminal_descriptor=terminal_descriptor,
                    terminal=current,
                    terminal_identity=current_identity,
                )
            finally:
                os.close(terminal_descriptor)
            return
        if len(staged.events) == len(current.events) + 1 and _same_events_prefix(
            current, staged
        ):
            self._rebind_layout(root_fd, secrets_fd, pilot_fd)
            self._rebind_file(
                pilot_fd,
                STAGE_FILE,
                stage_identity,
                maximum=MAX_LEDGER_BYTES,
            )
            self._replace_stage(
                pilot_fd,
                staged=staged,
                stage_identity=stage_identity,
                current=current,
                current_identity=current_identity,
            )
            _fsync(pilot_fd)
            _, old_identity = self._read_ledger_with_identity(pilot_fd, STAGE_FILE)
            terminal_descriptor = self._open_terminal_descriptor(
                pilot_fd, stage_identity
            )
            try:
                self._unlink_stage(
                    root_fd=root_fd,
                    secrets_fd=secrets_fd,
                    pilot_fd=pilot_fd,
                    stage_identity=old_identity,
                    terminal_descriptor=terminal_descriptor,
                    terminal=staged,
                    terminal_identity=stage_identity,
                )
            finally:
                os.close(terminal_descriptor)
            self._verify_terminal_ledger(pilot_fd, staged, stage_identity)
            return
        if len(current.events) == len(staged.events) + 1 and _same_events_prefix(
            staged, current
        ):
            terminal_descriptor = self._open_terminal_descriptor(
                pilot_fd, current_identity
            )
            try:
                self._unlink_stage(
                    root_fd=root_fd,
                    secrets_fd=secrets_fd,
                    pilot_fd=pilot_fd,
                    stage_identity=stage_identity,
                    terminal_descriptor=terminal_descriptor,
                    terminal=current,
                    terminal_identity=current_identity,
                )
            finally:
                os.close(terminal_descriptor)
            return
        fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)

    def initialize(self) -> tuple[PilotLedger, bool]:
        with self._layout(create=True) as (root_fd, secrets_fd, pilot_fd):
            ledger_guard: list[tuple[PilotLedger, os.stat_result]] = []
            with self._exclusive_lock(
                root_fd,
                secrets_fd,
                pilot_fd,
                ledger_guard,
            ):
                self._recover(root_fd=root_fd, secrets_fd=secrets_fd, pilot_fd=pilot_fd)
                if _exists(pilot_fd, LEDGER_FILE):
                    ledger, identity = self._read_ledger_with_identity(pilot_fd)
                    ledger_guard.append((ledger, identity))
                    return ledger, False
                ledger = empty_ledger()
                identity = self._atomic_write(
                    root_fd=root_fd,
                    secrets_fd=secrets_fd,
                    pilot_fd=pilot_fd,
                    ledger=ledger,
                    previous=None,
                )
                ledger_guard.append((ledger, identity))
                return ledger, True

    def read(self) -> PilotLedger:
        with self._layout(create=False) as (_, _, pilot_fd):
            if _exists(pilot_fd, STAGE_FILE):
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            return self._read_ledger(pilot_fd)

    def read_observation(self) -> PilotObservation:
        with self._layout(create=False) as (_, _, pilot_fd):
            raw = _read_file(pilot_fd, INPUT_FILE, maximum=MAX_INPUT_BYTES)
        return PilotObservation.parse(decode_strict_json(raw))

    def append(self, observation: PilotObservation) -> PilotAppendResult:
        if type(observation) is not PilotObservation:
            fail_pilot()
        with self._layout(create=False) as (root_fd, secrets_fd, pilot_fd):
            ledger_guard: list[tuple[PilotLedger, os.stat_result]] = []
            with self._exclusive_lock(
                root_fd,
                secrets_fd,
                pilot_fd,
                ledger_guard,
            ):
                self._recover(root_fd=root_fd, secrets_fd=secrets_fd, pilot_fd=pilot_fd)
                current, current_identity = self._read_ledger_with_identity(pilot_fd)
                updated, disposition, event_hash = append_observation(
                    current, observation
                )
                if disposition is AppendDisposition.APPENDED:
                    terminal_identity = self._atomic_write(
                        root_fd=root_fd,
                        secrets_fd=secrets_fd,
                        pilot_fd=pilot_fd,
                        ledger=updated,
                        previous=current,
                    )
                else:
                    terminal_identity = current_identity
                ledger_guard.append((updated, terminal_identity))
                return PilotAppendResult(
                    ledger=updated,
                    disposition=disposition,
                    event_sha256=event_hash,
                )


__all__ = [
    "INPUT_FILE",
    "LEDGER_FILE",
    "LOCK_FILE",
    "MAX_INPUT_BYTES",
    "MAX_LEDGER_BYTES",
    "OwnerLocalPilotJsonStore",
    "PILOT_DIRECTORY",
    "STAGE_FILE",
    "decode_strict_json",
]
