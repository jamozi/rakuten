"""Owner-private fixed-path JSON adapter for affiliate-learning V2."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Final, NoReturn

from raos.domain.editorial.affiliate_learning import (
    AffiliateLearningLedger,
    AppendDisposition,
    LearningObservation,
    MeasurementContract,
    append_observation,
    empty_ledger,
    parse_ledger,
    parse_observation,
)
from raos.domain.editorial.owner_local_pilot import (
    PilotFailure,
    PilotFailureCode,
    canonical_bytes,
    fail_pilot,
)
from raos.ports.affiliate_learning import AffiliateLearningAppendResult


PILOT_DIRECTORY: Final = "st1704-owner-local-pilot"
LEDGER_FILE: Final = "affiliate-learning-ledger.v2.json"
INPUT_FILE: Final = "affiliate-learning-observation-input.v2.json"
LOCK_FILE: Final = "affiliate-learning-ledger.v2.lock"
STAGE_FILE: Final = "affiliate-learning-ledger.v2.json.preparing"
MAX_LEDGER_BYTES: Final = 2_097_152
MAX_INPUT_BYTES: Final = 131_072
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


def _fail(code: PilotFailureCode = PilotFailureCode.STORE_UNSAFE) -> NoReturn:
    fail_pilot(code)


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
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except PilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, RecursionError:
        fail_pilot()


def _fsync(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError:
        _fail()


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


def _safe_directory(descriptor: int, *, mode: int | None) -> os.stat_result:
    observed = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or (mode is not None and stat.S_IMODE(observed.st_mode) != mode)
    ):
        _fail()
    return observed


def _open_child_directory(parent: int, name: str, *, create: bool) -> int:
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
    except FileNotFoundError:
        if not create:
            _fail(PilotFailureCode.STORE_NOT_INITIALIZED)
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
            _fsync(parent)
            return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
        except OSError:
            _fail()
    except OSError:
        _fail()


def _safe_file(
    descriptor: int, *, maximum: int, allow_empty: bool = False
) -> os.stat_result:
    observed = os.fstat(descriptor)
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


def _exists(directory: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        _fail()
    return True


def _read_file_with_identity(
    directory: int, name: str, *, maximum: int
) -> tuple[bytes, os.stat_result]:
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory)
    except FileNotFoundError:
        _fail(PilotFailureCode.STORE_NOT_INITIALIZED)
    except OSError:
        _fail()
    try:
        before = _safe_file(descriptor, maximum=maximum)
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
        after = _safe_file(descriptor, maximum=maximum)
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
            rebound = os.open(name, _FILE_FLAGS, dir_fd=directory)
        except OSError:
            _fail()
        try:
            rebound_stat = _safe_file(rebound, maximum=maximum)
            if (rebound_stat.st_dev, rebound_stat.st_ino) != (
                before.st_dev,
                before.st_ino,
            ):
                _fail()
        finally:
            os.close(rebound)
        return b"".join(chunks), before
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            _fail()
        offset += written


class AffiliateLearningJsonStore:
    """Atomic owner-only store in the existing ST-1704 private directory."""

    __slots__ = ("_contract", "_root", "_root_identity")

    def __init__(
        self,
        repository_root: Path,
        *,
        contract: MeasurementContract,
        expected_root_identity: tuple[int, int] | None = None,
    ) -> None:
        if (
            not repository_root.is_absolute()
            or type(contract) is not MeasurementContract
            or (
                expected_root_identity is not None
                and (
                    type(expected_root_identity) is not tuple
                    or len(expected_root_identity) != 2
                    or any(
                        type(value) is not int or value < 0
                        for value in expected_root_identity
                    )
                )
            )
        ):
            _fail()
        self._root = repository_root
        self._contract = contract
        self._root_identity = expected_root_identity

    def _validate_root(self, descriptor: int) -> None:
        observed = _safe_directory(descriptor, mode=None)
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
        root = _open_absolute_directory(self._root)
        secrets = -1
        pilot = -1
        try:
            self._validate_root(root)
            secrets = _open_child_directory(root, ".secrets", create=create)
            _safe_directory(secrets, mode=0o700)
            pilot = _open_child_directory(secrets, PILOT_DIRECTORY, create=create)
            _safe_directory(pilot, mode=0o700)
            yield root, secrets, pilot
        finally:
            try:
                if root >= 0 and secrets >= 0 and pilot >= 0:
                    self._rebind_layout(root, secrets, pilot)
            finally:
                if pilot >= 0:
                    os.close(pilot)
                if secrets >= 0:
                    os.close(secrets)
                os.close(root)

    def _rebind_layout(self, root: int, secrets: int, pilot: int) -> None:
        rebound_root = _open_absolute_directory(self._root)
        try:
            self._validate_root(root)
            self._validate_root(rebound_root)
            first_root = _safe_directory(root, mode=None)
            second_root = _safe_directory(rebound_root, mode=None)
            if (first_root.st_dev, first_root.st_ino) != (
                second_root.st_dev,
                second_root.st_ino,
            ):
                _fail()
            rebound_secrets = _open_child_directory(
                rebound_root, ".secrets", create=False
            )
            try:
                first_secrets = _safe_directory(secrets, mode=0o700)
                second_secrets = _safe_directory(rebound_secrets, mode=0o700)
                if (first_secrets.st_dev, first_secrets.st_ino) != (
                    second_secrets.st_dev,
                    second_secrets.st_ino,
                ):
                    _fail()
                rebound_pilot = _open_child_directory(
                    rebound_secrets, PILOT_DIRECTORY, create=False
                )
                try:
                    first_pilot = _safe_directory(pilot, mode=0o700)
                    second_pilot = _safe_directory(rebound_pilot, mode=0o700)
                    if (first_pilot.st_dev, first_pilot.st_ino) != (
                        second_pilot.st_dev,
                        second_pilot.st_ino,
                    ):
                        _fail()
                finally:
                    os.close(rebound_pilot)
            finally:
                os.close(rebound_secrets)
        finally:
            os.close(rebound_root)

    @contextmanager
    def _exclusive_lock(
        self, root: int, secrets: int, pilot: int
    ) -> Generator[None, None, None]:
        try:
            lock = os.open(
                LOCK_FILE,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=pilot,
            )
        except OSError:
            _fail()
        try:
            identity = _safe_file(lock, maximum=0, allow_empty=True)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _fail(PilotFailureCode.STORE_BUSY)
            self._rebind_layout(root, secrets, pilot)
            try:
                rebound = os.open(
                    LOCK_FILE,
                    os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=pilot,
                )
            except OSError:
                _fail()
            try:
                rebound_identity = _safe_file(rebound, maximum=0, allow_empty=True)
                if (identity.st_dev, identity.st_ino) != (
                    rebound_identity.st_dev,
                    rebound_identity.st_ino,
                ):
                    _fail()
            finally:
                os.close(rebound)
            try:
                yield
            finally:
                self._rebind_layout(root, secrets, pilot)
        finally:
            os.close(lock)

    def _read_ledger(self, pilot: int) -> AffiliateLearningLedger:
        raw, _ = _read_file_with_identity(pilot, LEDGER_FILE, maximum=MAX_LEDGER_BYTES)
        return parse_ledger(decode_strict_json(raw), contract=self._contract)

    def _write_ledger(
        self,
        *,
        root: int,
        secrets: int,
        pilot: int,
        ledger: AffiliateLearningLedger,
        expected_previous: AffiliateLearningLedger | None,
    ) -> None:
        if _exists(pilot, STAGE_FILE):
            _fail(PilotFailureCode.RECOVERY_REQUIRED)
        if expected_previous is None:
            if _exists(pilot, LEDGER_FILE):
                _fail()
        else:
            current = self._read_ledger(pilot)
            if current.payload() != expected_previous.payload():
                _fail(PilotFailureCode.RECOVERY_REQUIRED)
        payload = canonical_bytes(ledger.payload()) + b"\n"
        if len(payload) > MAX_LEDGER_BYTES:
            _fail()
        try:
            stage = os.open(
                STAGE_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=pilot,
            )
        except OSError:
            _fail()
        try:
            _write_all(stage, payload)
            os.fchmod(stage, 0o600)
            _fsync(stage)
            _safe_file(stage, maximum=MAX_LEDGER_BYTES)
        except BaseException:
            os.close(stage)
            raise
        os.close(stage)
        try:
            staged_raw, _ = _read_file_with_identity(
                pilot, STAGE_FILE, maximum=MAX_LEDGER_BYTES
            )
            staged = parse_ledger(
                decode_strict_json(staged_raw), contract=self._contract
            )
            if staged.payload() != ledger.payload():
                _fail()
            self._rebind_layout(root, secrets, pilot)
            os.replace(
                STAGE_FILE,
                LEDGER_FILE,
                src_dir_fd=pilot,
                dst_dir_fd=pilot,
            )
            _fsync(pilot)
            terminal = self._read_ledger(pilot)
            if terminal.payload() != ledger.payload() or _exists(pilot, STAGE_FILE):
                _fail(PilotFailureCode.RECOVERY_REQUIRED)
            self._rebind_layout(root, secrets, pilot)
        except PilotFailure:
            raise
        except OSError:
            _fail(PilotFailureCode.RECOVERY_REQUIRED)

    def initialize(self) -> tuple[AffiliateLearningLedger, bool]:
        with self._layout(create=True) as (root, secrets, pilot):
            with self._exclusive_lock(root, secrets, pilot):
                if _exists(pilot, STAGE_FILE):
                    _fail(PilotFailureCode.RECOVERY_REQUIRED)
                if _exists(pilot, LEDGER_FILE):
                    return self._read_ledger(pilot), False
                ledger = empty_ledger(self._contract)
                self._write_ledger(
                    root=root,
                    secrets=secrets,
                    pilot=pilot,
                    ledger=ledger,
                    expected_previous=None,
                )
                return ledger, True

    def read(self) -> AffiliateLearningLedger:
        with self._layout(create=False) as (_, _, pilot):
            if _exists(pilot, STAGE_FILE):
                _fail(PilotFailureCode.RECOVERY_REQUIRED)
            return self._read_ledger(pilot)

    def read_observation(self) -> LearningObservation:
        with self._layout(create=False) as (_, _, pilot):
            raw, _ = _read_file_with_identity(
                pilot, INPUT_FILE, maximum=MAX_INPUT_BYTES
            )
        return parse_observation(decode_strict_json(raw), contract=self._contract)

    def append(self, observation: LearningObservation) -> AffiliateLearningAppendResult:
        with self._layout(create=False) as (root, secrets, pilot):
            with self._exclusive_lock(root, secrets, pilot):
                if _exists(pilot, STAGE_FILE):
                    _fail(PilotFailureCode.RECOVERY_REQUIRED)
                current = self._read_ledger(pilot)
                updated, disposition, event_sha256 = append_observation(
                    current, observation, contract=self._contract
                )
                if disposition is AppendDisposition.APPENDED:
                    self._write_ledger(
                        root=root,
                        secrets=secrets,
                        pilot=pilot,
                        ledger=updated,
                        expected_previous=current,
                    )
                return AffiliateLearningAppendResult(
                    ledger=updated,
                    disposition=disposition,
                    event_sha256=event_sha256,
                )


__all__ = [
    "AffiliateLearningJsonStore",
    "INPUT_FILE",
    "LEDGER_FILE",
    "LOCK_FILE",
    "MAX_INPUT_BYTES",
    "MAX_LEDGER_BYTES",
    "PILOT_DIRECTORY",
    "STAGE_FILE",
    "decode_strict_json",
]
