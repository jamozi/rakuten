#!/usr/bin/env python3
"""Owner-installed fixed CLI for the ST-0505 Rakuten live smoke."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Protocol
import uuid


REPOSITORY_ROOT = Path("/home/minami/rakuten")
TRUSTED_OWNER_ROOT = Path("/home/minami/.local/share/raos")
TRUSTED_RUNTIME_PARENT = TRUSTED_OWNER_ROOT / "rakuten-live-smoke" / "runtime"
DOCTOR_READY = "RAKUTEN_LIVE_SMOKE_DOCTOR_READY"
DOCTOR_NOT_READY = "RAKUTEN_LIVE_SMOKE_DOCTOR_NOT_READY"
LIVE_PASS = "RAKUTEN_LIVE_SMOKE_PASS"
LIVE_FAIL = "RAKUTEN_LIVE_SMOKE_FAIL"
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
    "bin/rakuten-live-smoke": "0500",
    "scripts/rakuten_live_smoke.py": "0400",
    "python/raos/__init__.py": "0400",
    "python/raos/domain/catalog/rakuten_item_search.py": "0400",
    "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py": "0400",
    "python/raos/domain/catalog/rakuten_live_smoke.py": "0400",
    "python/raos/application/catalog/rakuten_live_smoke.py": "0400",
    "python/raos/ports/rakuten_live_smoke.py": "0400",
    "python/raos/adapters/rakuten_live_smoke.py": "0400",
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
    entry_path = runtime_root / "bin/rakuten-live-smoke"
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
            manifest["schema"] != "RAOS_ST0505_INSTALLED_RUNTIME_V1"
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


def doctor(reader: _CredentialReader, writer: _ReportWriter) -> tuple[int, str]:
    """Validate credential and report metadata without constructing a transport."""

    try:
        writer.doctor_ready()
        reader.read()
    except BaseException:
        return 2, DOCTOR_NOT_READY
    return 0, DOCTOR_READY


def run_live_smoke(
    *,
    reader: _CredentialReader,
    transport: _Transport,
    writer: _ReportWriter,
    clock: Callable[[], datetime] = _utc_now,
    run_id_factory: Callable[[datetime], str] = _new_run_id,
) -> tuple[int, str]:
    """Attempt one GET and persist one fixed-shape sanitized report."""

    from raos.application.catalog.rakuten_live_smoke import RakutenLiveSmokeService
    from raos.domain.catalog.rakuten_live_smoke import (
        RakutenLiveSmokeAuthClassification,
        RakutenLiveSmokeDiagnosticCode,
        RakutenLiveSmokeFailure,
        RakutenLiveSmokeRateClassification,
        RakutenLiveSmokeReport,
        RakutenLiveSmokeResult,
        RakutenLiveSmokeSchemaClassification,
        fixed_rakuten_live_smoke_request_fingerprint,
    )

    started = clock()
    run_id = run_id_factory(started)
    policy_fingerprint = fixed_rakuten_live_smoke_request_fingerprint()
    try:
        writer.preflight()
        observation = RakutenLiveSmokeService(reader, transport).run()
        report = RakutenLiveSmokeReport(
            run_id=run_id,
            started_at=started,
            finished_at=clock(),
            result=RakutenLiveSmokeResult.PASS,
            diagnostic_code=RakutenLiveSmokeDiagnosticCode.LIVE_SMOKE_PASS,
            request_policy_fingerprint=policy_fingerprint,
            http_status=observation.http_status,
            body_byte_count=observation.body_byte_count,
            response_sha256=observation.response_sha256,
            auth_classification=RakutenLiveSmokeAuthClassification.ACCEPTED,
            schema_classification=RakutenLiveSmokeSchemaClassification.VALID,
            rate_classification=(
                RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED
            ),
            affiliate_url_present=True,
            request_count=1,
        )
        writer.write(report)
        return 0, LIVE_PASS
    except RakutenLiveSmokeFailure as failure:
        report = RakutenLiveSmokeReport(
            run_id=run_id,
            started_at=started,
            finished_at=clock(),
            result=RakutenLiveSmokeResult.FAIL,
            diagnostic_code=failure.code,
            request_policy_fingerprint=policy_fingerprint,
            http_status=failure.http_status,
            body_byte_count=failure.body_byte_count,
            response_sha256=failure.response_sha256,
            auth_classification=failure.auth,
            schema_classification=failure.schema,
            rate_classification=failure.rate,
            affiliate_url_present=failure.affiliate_url_present,
            request_count=failure.request_count,
        )
        try:
            writer.write(report)
        except BaseException:
            return (
                1,
                f"{LIVE_FAIL}_{RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID.value}",
            )
        return 1, f"{LIVE_FAIL}_{failure.code.value}"
    except BaseException:
        return (
            1,
            f"{LIVE_FAIL}_{RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS.value}",
        )


def _production_credential_reader() -> _CredentialReader:
    from raos.adapters.rakuten_live_smoke import (
        OwnerPrivateRakutenLiveSmokeCredentialReader,
    )

    return OwnerPrivateRakutenLiveSmokeCredentialReader(REPOSITORY_ROOT)


def _production_report_writer() -> _ReportWriter:
    from raos.adapters.rakuten_live_smoke import (
        OwnerPrivateRakutenLiveSmokeReportWriter,
    )

    return OwnerPrivateRakutenLiveSmokeReportWriter(REPOSITORY_ROOT)


def _production_dependencies() -> tuple[_Transport, _ReportWriter]:
    from raos.adapters.rakuten_live_smoke import (
        DirectRakutenLiveSmokeTransport,
        OwnerPrivateRakutenLiveSmokeReportWriter,
        SystemRakutenLiveSmokeHttpsConnectionFactory,
    )

    return (
        DirectRakutenLiveSmokeTransport(SystemRakutenLiveSmokeHttpsConnectionFactory()),
        OwnerPrivateRakutenLiveSmokeReportWriter(REPOSITORY_ROOT),
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    failure_message = DOCTOR_NOT_READY if arguments == ("doctor",) else LIVE_FAIL
    if (
        sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or getattr(sys, "dont_write_bytecode", False) is not True
        or dict(os.environ) != _STAGE_ZERO_ENVIRONMENT
        or os.geteuid() != os.getuid()
        or len(arguments) != 1
        or arguments[0] not in {"doctor", "run"}
    ):
        print(failure_message)
        return 2
    try:
        _verify_stage_zero_entry()
        runtime_root = _verify_installed_runtime()
        _activate_runtime(runtime_root)
        reader = _production_credential_reader()
        if arguments[0] == "doctor":
            writer = _production_report_writer()
        else:
            transport, writer = _production_dependencies()
    except BaseException:
        print(failure_message)
        return 2
    if arguments[0] == "doctor":
        code, message = doctor(reader, writer)
    else:
        code, message = run_live_smoke(
            reader=reader,
            transport=transport,
            writer=writer,
        )
    print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
