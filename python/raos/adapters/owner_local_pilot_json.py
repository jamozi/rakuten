"""Owner-private JSON adapter for the ST-1704 local pilot ledger."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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


def _fail() -> NoReturn:
    fail_pilot(PilotFailureCode.STORE_UNSAFE)


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
            os.fsync(parent_fd)
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


def _read_file(directory_fd: int, name: str, *, maximum: int) -> bytes:
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
        return b"".join(chunks)
    finally:
        os.close(fd)


def _exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        _fail()
    return True


def _same_events_prefix(first: PilotLedger, second: PilotLedger) -> bool:
    if len(first.events) > len(second.events):
        return False
    return all(
        left.payload() == right.payload()
        for left, right in zip(first.events, second.events, strict=False)
    )


class OwnerLocalPilotJsonStore:
    """Strict fixed-path adapter with descriptor-relative atomic writes."""

    __slots__ = ("_root",)

    def __init__(self, repository_root: Path) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            _fail()
        self._root = repository_root

    @contextmanager
    def _layout(self, *, create: bool) -> Iterator[tuple[int, int, int]]:
        root_fd = _open_absolute_directory(self._root)
        secrets_fd = -1
        pilot_fd = -1
        try:
            _safe_directory(root_fd, mode=None)
            secrets_fd = _open_child_directory(root_fd, ".secrets", create=create)
            _safe_directory(secrets_fd, mode=0o700)
            pilot_fd = _open_child_directory(secrets_fd, PILOT_DIRECTORY, create=create)
            _safe_directory(pilot_fd, mode=0o700)
            yield root_fd, secrets_fd, pilot_fd
        finally:
            if pilot_fd >= 0:
                os.close(pilot_fd)
            if secrets_fd >= 0:
                os.close(secrets_fd)
            os.close(root_fd)

    @contextmanager
    def _exclusive_lock(self, pilot_fd: int) -> Iterator[None]:
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
            yield
        finally:
            os.close(lock_fd)

    def _rebind(self, secrets_fd: int, held_pilot_fd: int) -> None:
        rebound = _open_child_directory(secrets_fd, PILOT_DIRECTORY, create=False)
        try:
            if (
                os.fstat(rebound).st_dev,
                os.fstat(rebound).st_ino,
            ) != (
                os.fstat(held_pilot_fd).st_dev,
                os.fstat(held_pilot_fd).st_ino,
            ):
                _fail()
        finally:
            os.close(rebound)

    def _read_ledger(self, pilot_fd: int) -> PilotLedger:
        return parse_ledger(
            decode_strict_json(
                _read_file(pilot_fd, LEDGER_FILE, maximum=MAX_LEDGER_BYTES)
            )
        )

    def _replace_stage(self, pilot_fd: int) -> None:
        os.replace(
            STAGE_FILE,
            LEDGER_FILE,
            src_dir_fd=pilot_fd,
            dst_dir_fd=pilot_fd,
        )

    def _atomic_write(
        self, *, secrets_fd: int, pilot_fd: int, ledger: PilotLedger
    ) -> None:
        if _exists(pilot_fd, STAGE_FILE):
            fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
        payload = canonical_bytes(ledger.payload()) + b"\n"
        if len(payload) > MAX_LEDGER_BYTES:
            _fail()
        try:
            stage_fd = os.open(
                STAGE_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=pilot_fd,
            )
        except OSError:
            _fail()
        try:
            _safe_file(stage_fd, maximum=MAX_LEDGER_BYTES, allow_empty=True)
            offset = 0
            while offset < len(payload):
                written = os.write(stage_fd, payload[offset:])
                if written <= 0:
                    _fail()
                offset += written
            os.fsync(stage_fd)
            _safe_file(stage_fd, maximum=MAX_LEDGER_BYTES)
        finally:
            os.close(stage_fd)
        self._rebind(secrets_fd, pilot_fd)
        self._replace_stage(pilot_fd)
        os.fsync(pilot_fd)
        self._rebind(secrets_fd, pilot_fd)
        observed = self._read_ledger(pilot_fd)
        if observed.payload() != ledger.payload():
            _fail()

    def _recover(self, *, secrets_fd: int, pilot_fd: int) -> None:
        if not _exists(pilot_fd, STAGE_FILE):
            return
        staged = parse_ledger(
            decode_strict_json(
                _read_file(pilot_fd, STAGE_FILE, maximum=MAX_LEDGER_BYTES)
            )
        )
        if not _exists(pilot_fd, LEDGER_FILE):
            if staged.events:
                fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)
            self._rebind(secrets_fd, pilot_fd)
            self._replace_stage(pilot_fd)
            os.fsync(pilot_fd)
            return
        current = self._read_ledger(pilot_fd)
        if staged.payload() == current.payload():
            os.unlink(STAGE_FILE, dir_fd=pilot_fd)
            os.fsync(pilot_fd)
            return
        if len(staged.events) == len(current.events) + 1 and _same_events_prefix(
            current, staged
        ):
            self._rebind(secrets_fd, pilot_fd)
            self._replace_stage(pilot_fd)
            os.fsync(pilot_fd)
            return
        fail_pilot(PilotFailureCode.RECOVERY_REQUIRED)

    def initialize(self) -> tuple[PilotLedger, bool]:
        with self._layout(create=True) as (_, secrets_fd, pilot_fd):
            with self._exclusive_lock(pilot_fd):
                self._recover(secrets_fd=secrets_fd, pilot_fd=pilot_fd)
                if _exists(pilot_fd, LEDGER_FILE):
                    return self._read_ledger(pilot_fd), False
                ledger = empty_ledger()
                self._atomic_write(
                    secrets_fd=secrets_fd, pilot_fd=pilot_fd, ledger=ledger
                )
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
        with self._layout(create=False) as (_, secrets_fd, pilot_fd):
            with self._exclusive_lock(pilot_fd):
                self._recover(secrets_fd=secrets_fd, pilot_fd=pilot_fd)
                current = self._read_ledger(pilot_fd)
                updated, disposition, event_hash = append_observation(
                    current, observation
                )
                if disposition is AppendDisposition.APPENDED:
                    self._atomic_write(
                        secrets_fd=secrets_fd,
                        pilot_fd=pilot_fd,
                        ledger=updated,
                    )
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
