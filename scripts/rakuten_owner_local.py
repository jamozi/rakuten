#!/usr/bin/env python3
"""Owner-installed fixed CLI for ST-0505 owner-local Rakuten reads."""

from __future__ import annotations

from collections.abc import Sequence
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import termios
from typing import Any, Protocol
import uuid


REPOSITORY_ROOT = Path("/home/minami/rakuten")
TRUSTED_OWNER_ROOT = Path("/home/minami/.local/share/raos")
TRUSTED_RUNTIME_PARENT = TRUSTED_OWNER_ROOT / "rakuten-owner-local" / "runtime"
DOCTOR_READY = "RAKUTEN_OWNER_LOCAL_DOCTOR_READY"
DOCTOR_NOT_READY = "RAKUTEN_OWNER_LOCAL_DOCTOR_NOT_READY"
OWNER_LOCAL_OK = "RAKUTEN_OWNER_LOCAL_OK"
OWNER_LOCAL_FAIL = "RAKUTEN_OWNER_LOCAL_FAIL"
SETUP_COMPLETE = "RAKUTEN_OWNER_LOCAL_SETUP_COMPLETE"
ROTATE_COMPLETE = "RAKUTEN_OWNER_LOCAL_ROTATE_COMPLETE"
_RUNTIME_MANIFEST = "runtime-manifest.v1.json"
_BUNDLE_NAME = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_MAX_RUNTIME_FILE_BYTES = 2 * 1024 * 1024
_STAGE_ZERO_FD = 3
_STAGE_ZERO_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TZ": "UTC",
}
_INSTALLED_PAYLOAD_MODES = {
    "bin/rakuten-owner-local": "0500",
    "scripts/rakuten_owner_local.py": "0400",
    "python/raos/__init__.py": "0400",
    "python/raos/domain/catalog/rakuten_item_search.py": "0400",
    "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py": "0400",
    "python/raos/domain/catalog/rakuten_owner_local.py": "0400",
    "python/raos/application/catalog/rakuten_owner_local.py": "0400",
    "python/raos/ports/rakuten_owner_local.py": "0400",
    "python/raos/adapters/rakuten_owner_local.py": "0400",
}


class _CredentialReader(Protocol):
    def read(self) -> Any: ...


class _Transport(Protocol):
    def execute(self, policy: Any, credentials: Any) -> Any: ...


class _ReportWriter(Protocol):
    def doctor_ready(self) -> None: ...

    def preflight(self) -> None: ...

    def write(self, report: Any) -> None: ...


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _open_runtime_root(runtime_root: Path) -> int:
    if (
        runtime_root.parent != TRUSTED_RUNTIME_PARENT
        or _BUNDLE_NAME.fullmatch(runtime_root.name) is None
    ):
        raise RuntimeError("RUNTIME_UNTRUSTED")
    current = os.open("/", _DIRECTORY_FLAGS)
    walked = Path("/")
    try:
        for component in runtime_root.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            details = os.fstat(following)
            named = os.stat(component, dir_fd=current, follow_symlinks=False)
            walked /= component
            if not _same_identity(details, named) or not stat.S_ISDIR(details.st_mode):
                os.close(following)
                raise RuntimeError("RUNTIME_UNTRUSTED")
            if walked.is_relative_to(TRUSTED_OWNER_ROOT) and (
                details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o700
            ):
                os.close(following)
                raise RuntimeError("RUNTIME_UNTRUSTED")
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _verify_stage_zero_entry() -> None:
    runtime_root = Path(__file__).absolute().parent.parent
    entry_path = runtime_root / "bin/rakuten-owner-local"
    try:
        inherited = os.fstat(_STAGE_ZERO_FD)
        named = os.stat(entry_path, follow_symlinks=False)
    except OSError:
        raise RuntimeError("RUNTIME_UNTRUSTED") from None
    if (
        not _same_identity(inherited, named)
        or not stat.S_ISREG(inherited.st_mode)
        or inherited.st_uid != os.getuid()
        or stat.S_IMODE(inherited.st_mode) != 0o500
        or inherited.st_nlink != 1
    ):
        raise RuntimeError("RUNTIME_UNTRUSTED")
    os.close(_STAGE_ZERO_FD)


def _read_runtime_file(root_fd: int, relative: str, expected_mode: int) -> bytes:
    parts = relative.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError("RUNTIME_UNTRUSTED")
    current = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            details = os.fstat(following)
            named = os.stat(component, dir_fd=current, follow_symlinks=False)
            if (
                not _same_identity(details, named)
                or not stat.S_ISDIR(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o700
            ):
                os.close(following)
                raise RuntimeError("RUNTIME_UNTRUSTED")
            os.close(current)
            current = following
        descriptor = os.open(parts[-1], _FILE_FLAGS, dir_fd=current)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != expected_mode
                or before.st_nlink != 1
                or not 0 <= before.st_size <= _MAX_RUNTIME_FILE_BYTES
            ):
                raise RuntimeError("RUNTIME_UNTRUSTED")
            chunks: list[bytes] = []
            remaining = _MAX_RUNTIME_FILE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            after = os.fstat(descriptor)
            named = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if (
                len(payload) > _MAX_RUNTIME_FILE_BYTES
                or len(payload) != before.st_size
                or not _same_identity(before, after)
                or not _same_identity(after, named)
                or after.st_size != before.st_size
            ):
                raise RuntimeError("RUNTIME_UNTRUSTED")
            return payload
        finally:
            os.close(descriptor)
    finally:
        os.close(current)


def _expected_runtime_children(paths: set[str], prefix: str) -> set[str]:
    boundary = f"{prefix}/" if prefix else ""
    children: set[str] = set()
    for path in paths:
        if path.startswith(boundary):
            children.add(path[len(boundary) :].split("/", 1)[0])
    return children


def _validate_runtime_inventory(
    directory_fd: int, paths: set[str], prefix: str = ""
) -> None:
    if set(os.listdir(directory_fd)) != _expected_runtime_children(paths, prefix):
        raise RuntimeError("RUNTIME_UNTRUSTED")
    boundary = f"{prefix}/" if prefix else ""
    relevant = (
        path[len(boundary) :]
        for path in paths
        if not prefix or path.startswith(boundary)
    )
    child_directories = {path.split("/", 1)[0] for path in relevant if "/" in path}
    for name in child_directories:
        child = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory_fd)
        try:
            details = os.fstat(child)
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not _same_identity(details, named)
                or not stat.S_ISDIR(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o700
            ):
                raise RuntimeError("RUNTIME_UNTRUSTED")
            child_prefix = f"{prefix}/{name}" if prefix else name
            _validate_runtime_inventory(child, paths, child_prefix)
        finally:
            os.close(child)


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise RuntimeError("RUNTIME_UNTRUSTED")
        value[key] = item
    return value


def _canonical_rows(rows: object) -> bytes:
    return json.dumps(
        rows,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _verify_installed_runtime() -> Path:
    runtime_root = Path(__file__).absolute().parent.parent
    root_fd = _open_runtime_root(runtime_root)
    try:
        _validate_runtime_inventory(
            root_fd, set(_INSTALLED_PAYLOAD_MODES) | {_RUNTIME_MANIFEST}
        )
        manifest_bytes = _read_runtime_file(root_fd, _RUNTIME_MANIFEST, 0o400)
        try:
            manifest = json.loads(
                manifest_bytes.decode("ascii", errors="strict"),
                object_pairs_hook=_json_pairs,
                parse_constant=lambda ignored: (_ for _ in ()).throw(
                    RuntimeError("RUNTIME_UNTRUSTED")
                ),
            )
        except UnicodeError, ValueError, TypeError, RecursionError:
            raise RuntimeError("RUNTIME_UNTRUSTED") from None
        if type(manifest) is not dict or set(manifest) != {
            "schema",
            "version",
            "bundle_sha256",
            "files",
        }:
            raise RuntimeError("RUNTIME_UNTRUSTED")
        if (
            manifest["schema"] != "RAOS_ST0505_OWNER_LOCAL_INSTALLED_RUNTIME_V1"
            or manifest["version"] != 1
            or manifest["bundle_sha256"] != runtime_root.name
            or type(manifest["files"]) is not list
        ):
            raise RuntimeError("RUNTIME_UNTRUSTED")
        rows = manifest["files"]
        if hashlib.sha256(_canonical_rows(rows)).hexdigest() != runtime_root.name:
            raise RuntimeError("RUNTIME_UNTRUSTED")
        if len(rows) != len(_INSTALLED_PAYLOAD_MODES):
            raise RuntimeError("RUNTIME_UNTRUSTED")
        for row, (expected_path, expected_mode) in zip(
            rows, _INSTALLED_PAYLOAD_MODES.items(), strict=True
        ):
            if type(row) is not dict or set(row) != {"path", "sha256", "mode"}:
                raise RuntimeError("RUNTIME_UNTRUSTED")
            if row["path"] != expected_path or row["mode"] != expected_mode:
                raise RuntimeError("RUNTIME_UNTRUSTED")
            digest = row["sha256"]
            if type(digest) is not str or _BUNDLE_NAME.fullmatch(digest) is None:
                raise RuntimeError("RUNTIME_UNTRUSTED")
            payload = _read_runtime_file(root_fd, expected_path, int(expected_mode, 8))
            if hashlib.sha256(payload).hexdigest() != digest:
                raise RuntimeError("RUNTIME_UNTRUSTED")
    finally:
        os.close(root_fd)
    return runtime_root


def _activate_runtime(runtime_root: Path) -> None:
    sys.path.insert(0, str(runtime_root / "python"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id(now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{uuid.uuid4().hex}"


class _TTYInterrupted(RuntimeError):
    pass


def _disable_process_disclosure() -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = (
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        )
        prctl.restype = ctypes.c_int
        if prctl(4, 0, 0, 0, 0) != 0:  # Linux PR_SET_DUMPABLE
            raise OSError(ctypes.get_errno(), "process disclosure lock failed")
    except BaseException:
        raise RuntimeError("PROCESS_DISCLOSURE_INVALID") from None


def _tty_signal_handler(_signal_number: int, _frame: object) -> None:
    raise _TTYInterrupted from None


def _read_hidden_tty(prompt: bytes, *, maximum: int = 4096) -> bytearray:
    """Read one bounded line from /dev/tty with echo disabled."""

    if not prompt.isascii() or b"\n" in prompt or not 1 <= maximum <= 4096:
        raise RuntimeError("TTY_INVALID")
    descriptor = os.open(
        "/dev/tty",
        os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
    )
    handlers: dict[int, Any] = {}
    original: list[Any] | None = None
    value = bytearray()
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISCHR(details.st_mode):
            raise RuntimeError("TTY_INVALID")
        os.set_blocking(descriptor, True)
        original = termios.tcgetattr(descriptor)
        if not original[3] & termios.ICANON:
            raise RuntimeError("TTY_INVALID")
        hidden = list(original)
        hidden[3] &= ~(termios.ECHO | termios.ECHONL)
        for candidate in (signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
            handlers[int(candidate)] = signal.getsignal(candidate)
            signal.signal(candidate, _tty_signal_handler)
        termios.tcsetattr(descriptor, termios.TCSAFLUSH, hidden)
        os.write(descriptor, prompt)
        while True:
            chunk = os.read(descriptor, 1)
            if chunk in {b"", b"\n"}:
                break
            if chunk == b"\r":
                continue
            if len(value) >= maximum:
                while chunk not in {b"", b"\n"}:
                    chunk = os.read(descriptor, 1)
                raise RuntimeError("TTY_INVALID")
            value.extend(chunk)
        if not value:
            raise RuntimeError("TTY_INVALID")
        return value
    finally:
        if original is not None:
            try:
                termios.tcsetattr(descriptor, termios.TCSAFLUSH, original)
            except BaseException:
                pass
            try:
                os.write(descriptor, b"\n")
            except BaseException:
                pass
        for number, handler in handlers.items():
            try:
                signal.signal(number, handler)
            except BaseException:
                pass
        os.close(descriptor)


def _wipe(value: bytearray) -> None:
    value[:] = b"\x00" * len(value)
    value.clear()


def _capture_credentials() -> Any:
    from raos.domain.catalog.rakuten_owner_local import (
        RAKUTEN_OWNER_LOCAL_PROFILE,
        RakutenOwnerLocalCredentials,
    )

    _disable_process_disclosure()
    values: list[bytearray] = []
    try:
        for label in (b"Application ID", b"Access key", b"Affiliate ID"):
            first = _read_hidden_tty(label + b": ")
            values.append(first)
            second = _read_hidden_tty(label + b" again: ")
            values.append(second)
            if first != second:
                raise RuntimeError("TTY_CONFIRMATION_FAILED")
        confirmation = _read_hidden_tty(b"Type YES to confirm: ", maximum=3)
        values.append(confirmation)
        if confirmation != b"YES":
            raise RuntimeError("TTY_CONFIRMATION_FAILED")
        return RakutenOwnerLocalCredentials(
            profile=RAKUTEN_OWNER_LOCAL_PROFILE,
            _application_id=bytes(values[0]),
            _access_key=bytes(values[2]),
            _affiliate_id=bytes(values[4]),
        )
    finally:
        for value in values:
            _wipe(value)


def _production_store() -> Any:
    from raos.adapters.rakuten_owner_local import (
        OwnerPrivateRakutenOwnerLocalCredentialStore,
    )

    return OwnerPrivateRakutenOwnerLocalCredentialStore(REPOSITORY_ROOT)


def _production_reader() -> Any:
    from raos.adapters.rakuten_owner_local import (
        OwnerPrivateRakutenOwnerLocalCredentialReader,
    )

    return OwnerPrivateRakutenOwnerLocalCredentialReader(REPOSITORY_ROOT)


def _production_request_reader() -> Any:
    from raos.adapters.rakuten_owner_local import (
        OwnerPrivateRakutenOwnerLocalRequestReader,
    )

    return OwnerPrivateRakutenOwnerLocalRequestReader()


def _production_writer() -> Any:
    from raos.adapters.rakuten_owner_local import (
        OwnerPrivateRakutenOwnerLocalResultWriter,
    )

    return OwnerPrivateRakutenOwnerLocalResultWriter(REPOSITORY_ROOT)


def _production_transport() -> Any:
    from raos.adapters.rakuten_owner_local import (
        DirectRakutenOwnerLocalTransport,
        SystemRakutenOwnerLocalHttpsConnectionFactory,
    )

    return DirectRakutenOwnerLocalTransport(
        SystemRakutenOwnerLocalHttpsConnectionFactory()
    )


def _doctor(reader: Any, writer: Any) -> tuple[int, str]:
    try:
        writer.doctor_ready()
        reader.read()
    except BaseException:
        return 2, DOCTOR_NOT_READY
    return 0, DOCTOR_READY


def _execute_request(
    api_name: str,
    request: Any,
    *,
    reader: Any,
    writer: Any,
    transport: Any,
) -> tuple[int, str]:
    from raos.application.catalog.rakuten_owner_local import RakutenOwnerLocalService
    from raos.domain.catalog.rakuten_owner_local import (
        RakutenOwnerLocalApi,
        RakutenOwnerLocalFailure,
        RakutenOwnerLocalOutcome,
    )

    try:
        api = RakutenOwnerLocalApi(api_name)
        run_id = _new_run_id(_utc_now())
        envelope = RakutenOwnerLocalService(reader, transport, writer).run(
            api,
            request,
            run_id=run_id,
        )
    except RakutenOwnerLocalFailure as failure:
        return 1, f"{OWNER_LOCAL_FAIL}_{failure.code.value}"
    except BaseException:
        return 1, OWNER_LOCAL_FAIL
    if envelope.outcome is RakutenOwnerLocalOutcome.FAILURE:
        if envelope.failure is None:
            return 1, OWNER_LOCAL_FAIL
        return 1, f"{OWNER_LOCAL_FAIL}_{envelope.failure.code.value}"
    return 0, OWNER_LOCAL_OK


def _valid_arguments(arguments: tuple[str, ...]) -> bool:
    if arguments in {
        ("setup",),
        ("rotate",),
        ("doctor",),
        ("list-apis",),
    }:
        return True
    if (
        len(arguments) == 5
        and arguments[0] == "request"
        and arguments[1] == "--api"
        and arguments[2] in {"item-search", "product-search"}
        and arguments[3] == "--request-file"
        and Path(arguments[4]).is_absolute()
    ):
        return True
    return (
        len(arguments) == 3
        and arguments[0] == "smoke"
        and arguments[1] == "--api"
        and arguments[2] in {"item-search", "product-search"}
    )


def _dispatch(arguments: tuple[str, ...]) -> tuple[int, str]:
    from raos.domain.catalog.rakuten_owner_local import (
        RakutenOwnerLocalApi,
        fixed_owner_local_smoke_request,
    )

    command = arguments[0]
    if command == "setup":
        store = _production_store()
        store.setup_ready()
        credentials = _capture_credentials()
        store.setup(credentials)
        return 0, SETUP_COMPLETE
    if command == "rotate":
        store = _production_store()
        store.rotate_ready()
        credentials = _capture_credentials()
        store.rotate(credentials)
        return 0, ROTATE_COMPLETE
    if command == "doctor":
        return _doctor(_production_reader(), _production_writer())
    if command == "list-apis":
        return (
            0,
            '{"apis":["item-search","product-search"],"schema_version":1}',
        )
    api = RakutenOwnerLocalApi(arguments[2])
    if command == "request":
        request = _production_request_reader().read(Path(arguments[4]), api)
    else:
        request = fixed_owner_local_smoke_request(api)
    return _execute_request(
        api.value,
        request,
        reader=_production_reader(),
        writer=_production_writer(),
        transport=_production_transport(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    failure_message = DOCTOR_NOT_READY if arguments == ("doctor",) else OWNER_LOCAL_FAIL
    if (
        sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or getattr(sys, "dont_write_bytecode", False) is not True
        or dict(os.environ) != _STAGE_ZERO_ENVIRONMENT
        or os.geteuid() != os.getuid()
        or not _valid_arguments(arguments)
    ):
        print(failure_message)
        return 2
    try:
        _verify_stage_zero_entry()
        runtime_root = _verify_installed_runtime()
        _activate_runtime(runtime_root)
        code, message = _dispatch(arguments)
    except BaseException:
        code, message = 2, failure_message
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
