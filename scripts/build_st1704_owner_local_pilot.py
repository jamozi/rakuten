#!/usr/bin/env python3
"""Generate/check the single ST-1704 owner-local runtime manifest."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Final, NoReturn


ROOT: Final = Path(os.path.abspath(__file__)).parent.parent
SLICE_ROOT: Final = ROOT / "changes/st-1704/owner-local-pilot-v1"
MANIFEST_PATH: Final = SLICE_ROOT / "runtime-manifest.v1.json"
MAX_RUNTIME_BYTES: Final = 2 * 1024 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_RENAME_EXCHANGE: Final = 2

POLICY: Final = {
    "article_slots": 5,
    "automatic_publication": "DISABLED",
    "duration_days": 14,
    "first_five_drafts": "CODEX_NOT_OPENAI_API",
    "improvement_output": "PROPOSAL_AND_DIFF_ONLY",
    "labor_cost_per_hour_jpy": 3000,
    "monthly_incremental_cost_cap_jpy": 2000,
    "nonessential_tracking": "DISABLED_OD_012",
    "site_origin": "https://kurashinoshirube.com",
}
STATE_SCHEMA: Final = {
    "enum": [
        "NOT_OBSERVED",
        "UNAVAILABLE",
        "UNVERIFIED",
        "OBSERVED_ZERO",
        "OBSERVED_VALUE",
    ]
}
NUMBER_OBSERVATION_SCHEMA: Final = {
    "additionalProperties": False,
    "properties": {
        "state": STATE_SCHEMA,
        "value": {"anyOf": [{"minimum": 0, "type": "integer"}, {"type": "null"}]},
    },
    "required": ["state", "value"],
    "type": "object",
}
METRIC_OBSERVATION_SCHEMA: Final = {
    "additionalProperties": False,
    "properties": {
        "attribution_basis": {
            "enum": [
                "NOT_APPLICABLE",
                "UNVERIFIED",
                "OWNER_REPORTED_PROVIDER_TOTAL",
                "OWNER_REPORTED_DIRECT",
                "OWNER_REPORTED_ESTIMATED",
                "OWNER_REPORTED_UNATTRIBUTED",
            ]
        },
        "input_sha256": {
            "anyOf": [
                {"pattern": "^[0-9a-f]{64}$", "type": "string"},
                {"type": "null"},
            ]
        },
        "period_end": {
            "anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]
        },
        "period_start": {
            "anyOf": [{"format": "date", "type": "string"}, {"type": "null"}]
        },
        "source_kind": {
            "enum": [
                "NOT_CONNECTED",
                "OWNER_MANUAL_AGGREGATE",
                "WORDPRESS_ADMIN_AGGREGATE",
                "FIRST_PARTY_AGGREGATE",
                "SEARCH_CONSOLE_AGGREGATE",
                "RAKUTEN_REPORT_AGGREGATE",
            ]
        },
        "state": STATE_SCHEMA,
        "value": {"anyOf": [{"minimum": 0, "type": "integer"}, {"type": "null"}]},
    },
    "required": [
        "attribution_basis",
        "input_sha256",
        "period_end",
        "period_start",
        "source_kind",
        "state",
        "value",
    ],
    "type": "object",
}
REVENUE_OBSERVATION_SCHEMA: Final = {
    "additionalProperties": False,
    "properties": {
        "direct_jpy": METRIC_OBSERVATION_SCHEMA,
        "estimated_jpy": METRIC_OBSERVATION_SCHEMA,
        "provider_total_jpy": METRIC_OBSERVATION_SCHEMA,
        "unattributed_jpy": METRIC_OBSERVATION_SCHEMA,
    },
    "required": [
        "direct_jpy",
        "estimated_jpy",
        "provider_total_jpy",
        "unattributed_jpy",
    ],
    "type": "object",
}
_TIMESTAMP_PATTERN: Final = "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
OBSERVATION_SCHEMA_PAYLOAD: Final = {
    "$id": "urn:raos:st1704:owner-local-pilot-observation:v1",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "properties": {
        "article": {
            "additionalProperties": False,
            "properties": {
                "article_ref_sha256": {
                    "anyOf": [
                        {"pattern": "^[0-9a-f]{64}$", "type": "string"},
                        {"type": "null"},
                    ]
                },
                "public_slug": {
                    "anyOf": [
                        {
                            "maxLength": 120,
                            "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                            "type": "string",
                        },
                        {"type": "null"},
                    ]
                },
                "slot": {"maximum": 5, "minimum": 1, "type": "integer"},
            },
            "required": ["article_ref_sha256", "public_slug", "slot"],
            "type": "object",
        },
        "defects": {
            "additionalProperties": False,
            "properties": {
                "critical": NUMBER_OBSERVATION_SCHEMA,
                "major": NUMBER_OBSERVATION_SCHEMA,
                "minor": NUMBER_OBSERVATION_SCHEMA,
            },
            "required": ["critical", "major", "minor"],
            "type": "object",
        },
        "incremental_cost_jpy": NUMBER_OBSERVATION_SCHEMA,
        "metrics": {
            "additionalProperties": False,
            "properties": {
                "affiliate_clicks": METRIC_OBSERVATION_SCHEMA,
                "article_views": METRIC_OBSERVATION_SCHEMA,
                "organic_clicks": METRIC_OBSERVATION_SCHEMA,
                "revenue_jpy": REVENUE_OBSERVATION_SCHEMA,
            },
            "required": [
                "affiliate_clicks",
                "article_views",
                "organic_clicks",
                "revenue_jpy",
            ],
            "type": "object",
        },
        "observation_id": {
            "maxLength": 128,
            "pattern": "^[A-Z0-9][A-Z0-9_.:-]*$",
            "type": "string",
        },
        "observed_at_utc": {
            "pattern": _TIMESTAMP_PATTERN,
            "type": "string",
        },
        "pilot_window": {
            "additionalProperties": False,
            "properties": {
                "duration_days": {"const": 14},
                "end_exclusive_date": {"format": "date", "type": "string"},
                "start_date": {"format": "date", "type": "string"},
            },
            "required": ["duration_days", "end_exclusive_date", "start_date"],
            "type": "object",
        },
        "publication": {
            "additionalProperties": False,
            "properties": {
                "confirmed_at_utc": {
                    "anyOf": [
                        {"pattern": _TIMESTAMP_PATTERN, "type": "string"},
                        {"type": "null"},
                    ]
                },
                "confirmed_by_role": {"enum": ["OWNER", None]},
                "status": {
                    "enum": [
                        "NOT_OBSERVED",
                        "HUMAN_CONFIRMED_PUBLISHED",
                        "HUMAN_CONFIRMED_NOT_PUBLISHED",
                    ]
                },
            },
            "required": ["confirmed_at_utc", "confirmed_by_role", "status"],
            "type": "object",
        },
        "review": {
            "additionalProperties": False,
            "properties": {
                "reviewed_at_utc": {
                    "anyOf": [
                        {"pattern": _TIMESTAMP_PATTERN, "type": "string"},
                        {"type": "null"},
                    ]
                },
                "reviewer_role": {"enum": ["OWNER", None]},
                "status": {
                    "enum": [
                        "NOT_OBSERVED",
                        "HUMAN_REVIEW_COMPLETE",
                        "CHANGES_REQUIRED",
                        "BLOCKED",
                    ]
                },
            },
            "required": ["reviewed_at_utc", "reviewer_role", "status"],
            "type": "object",
        },
        "schema": {"const": "ST1704_OWNER_LOCAL_PILOT_OBSERVATION_V1"},
        "work_minutes": NUMBER_OBSERVATION_SCHEMA,
    },
    "required": [
        "article",
        "defects",
        "incremental_cost_jpy",
        "metrics",
        "observation_id",
        "observed_at_utc",
        "pilot_window",
        "publication",
        "review",
        "schema",
        "work_minutes",
    ],
    "title": "ST-1704 owner-local sanitized pilot observation",
    "type": "object",
}
RUNTIME_PATHS: Final = (
    "changes/st-1704/owner-local-pilot-v1/DESIGN_HANDOFF_V1.yaml",
    "changes/st-1704/owner-local-pilot-v1/Makefile",
    "changes/st-1704/owner-local-pilot-v1/PREFLIGHT.md",
    "changes/st-1704/owner-local-pilot-v1/README.md",
    "changes/st-1704/owner-local-pilot-v1/examples/bootstrap-first-publication.v1.json",
    "python/raos/adapters/owner_local_pilot_json.py",
    "python/raos/application/editorial/owner_local_pilot.py",
    "python/raos/domain/editorial/owner_local_pilot.py",
    "python/raos/ports/owner_local_pilot.py",
    "scripts/build_st1704_owner_local_pilot.py",
    "scripts/st1704_owner_local_pilot.py",
)


class BuildFailure(RuntimeError):
    """Stable fail-closed build error."""


def _fail() -> NoReturn:
    raise BuildFailure("ST1704_OWNER_LOCAL_PILOT_BUILD_INVALID") from None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _render(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def contract_sha256() -> str:
    return hashlib.sha256(
        _canonical(
            {
                "observation_input_schema": OBSERVATION_SCHEMA_PAYLOAD,
                "policy": POLICY,
            }
        )
    ).hexdigest()


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail()
    current = -1
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
        for part in path.parts[1:]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        return current
    except OSError:
        if current >= 0:
            os.close(current)
        _fail()


def _safe_root(root_fd: int) -> os.stat_result:
    observed = os.fstat(root_fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        _fail()
    return observed


def _rebind_root(root_fd: int) -> None:
    rebound = _open_absolute_directory(ROOT)
    try:
        expected = _safe_root(root_fd)
        observed = _safe_root(rebound)
        if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
            _fail()
    finally:
        os.close(rebound)


def _relative_parts(relative: str) -> tuple[str, ...]:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail()
    return path.parts


def _open_parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative_parts(relative)
    current = -1
    try:
        current = os.dup(root_fd)
        for part in parts[:-1]:
            following = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        return current, parts[-1]
    except OSError:
        if current >= 0:
            os.close(current)
        _fail()


def _safe_file(fd: int, *, maximum: int, allow_empty: bool = False) -> os.stat_result:
    observed = os.fstat(fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
        or stat.S_IMODE(observed.st_mode) & 0o022
        or observed.st_size > maximum
        or (not allow_empty and observed.st_size == 0)
    ):
        _fail()
    return observed


def _read_relative_with_identity(
    root_fd: int, relative: str
) -> tuple[bytes, os.stat_result]:
    parent_fd, name = _open_parent(root_fd, relative)
    try:
        try:
            fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
        except OSError:
            _fail()
        try:
            before = _safe_file(fd, maximum=MAX_RUNTIME_BYTES)
            remaining = before.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(fd, min(remaining, 65_536))
                if not chunk:
                    _fail()
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(fd, 1):
                _fail()
            after = _safe_file(fd, maximum=MAX_RUNTIME_BYTES)
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
                rebound_fd = os.open(name, _FILE_FLAGS, dir_fd=parent_fd)
            except OSError:
                _fail()
            try:
                rebound = _safe_file(rebound_fd, maximum=MAX_RUNTIME_BYTES)
                if (before.st_dev, before.st_ino) != (
                    rebound.st_dev,
                    rebound.st_ino,
                ):
                    _fail()
            finally:
                os.close(rebound_fd)
            return b"".join(chunks), before
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def _read_relative(root_fd: int, relative: str) -> bytes:
    return _read_relative_with_identity(root_fd, relative)[0]


RuntimeSnapshot = tuple[str, int, int, int, int, int, str]


def _runtime_snapshot(root_fd: int, relative: str) -> tuple[bytes, RuntimeSnapshot]:
    raw = _read_relative(root_fd, relative)
    confirmed, identity = _read_relative_with_identity(root_fd, relative)
    if raw != confirmed:
        _fail()
    return raw, (
        relative,
        identity.st_dev,
        identity.st_ino,
        identity.st_size,
        identity.st_mtime_ns,
        identity.st_ctime_ns,
        hashlib.sha256(raw).hexdigest(),
    )


def _manifest_snapshot(
    root_fd: int,
) -> tuple[bytes, tuple[RuntimeSnapshot, ...]]:
    entries: list[dict[str, object]] = []
    snapshots: list[RuntimeSnapshot] = []
    for relative in RUNTIME_PATHS:
        raw, snapshot = _runtime_snapshot(root_fd, relative)
        snapshots.append(snapshot)
        entries.append(
            {
                "bytes": len(raw),
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return (
        _render(
            {
                "contract_sha256": contract_sha256(),
                "external_action_authority": "NONE",
                "generated_by": "scripts/build_st1704_owner_local_pilot.py",
                "observation_input_schema": OBSERVATION_SCHEMA_PAYLOAD,
                "paths": entries,
                "policy": POLICY,
                "schema": "ST1704_OWNER_LOCAL_PILOT_RUNTIME_MANIFEST_V1",
                "slice_id": "ST1704_OWNER_LOCAL_PILOT_LEDGER_V1",
                "story_id": "ST-1704",
            }
        ),
        tuple(snapshots),
    )


def _verify_runtime_snapshot(
    root_fd: int, snapshots: tuple[RuntimeSnapshot, ...]
) -> None:
    if len(snapshots) != len(RUNTIME_PATHS):
        _fail()
    for snapshot, relative in zip(snapshots, RUNTIME_PATHS, strict=True):
        (
            expected_relative,
            expected_device,
            expected_inode,
            expected_size,
            expected_mtime,
            expected_ctime,
            expected_sha256,
        ) = snapshot
        if expected_relative != relative:
            _fail()
        raw, identity = _read_relative_with_identity(root_fd, relative)
        if (
            identity.st_dev,
            identity.st_ino,
            identity.st_size,
            identity.st_mtime_ns,
            identity.st_ctime_ns,
            hashlib.sha256(raw).hexdigest(),
        ) != (
            expected_device,
            expected_inode,
            expected_size,
            expected_mtime,
            expected_ctime,
            expected_sha256,
        ):
            _fail()
    _rebind_root(root_fd)


def _exists(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        _fail()
    return True


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except OSError:
            _fail()
        if written <= 0:
            _fail()
        offset += written


def _open_anonymous_file(parent_fd: int, payload: bytes) -> int:
    anonymous_flag = getattr(os, "O_TMPFILE", 0)
    if not anonymous_flag:
        _fail()
    try:
        descriptor = os.open(
            ".",
            os.O_RDWR | anonymous_flag | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o644,
            dir_fd=parent_fd,
        )
    except OSError:
        _fail()
    try:
        os.fchmod(descriptor, 0o644)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != 0o644
            or observed.st_nlink != 0
            or observed.st_size != len(payload)
        ):
            _fail()
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _link_descriptor(parent_fd: int, descriptor: int, name: str) -> None:
    try:
        os.link(
            f"/proc/self/fd/{descriptor}",
            name,
            dst_dir_fd=parent_fd,
            follow_symlinks=True,
        )
    except OSError:
        _fail()


def _rename_exchange(parent_fd: int, left: str, right: str) -> None:
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
    if (
        renameat2(
            parent_fd,
            os.fsencode(left),
            parent_fd,
            os.fsencode(right),
            _RENAME_EXCHANGE,
        )
        != 0
    ):
        _fail()


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _verify_relative(
    root_fd: int,
    relative: str,
    payload: bytes,
    identity: os.stat_result,
) -> None:
    observed, observed_identity = _read_relative_with_identity(root_fd, relative)
    if observed != payload or not _same_identity(observed_identity, identity):
        _fail()


def _atomic_write(root_fd: int, payload: bytes) -> None:
    relative = MANIFEST_PATH.relative_to(ROOT).as_posix()
    parent_fd, name = _open_parent(root_fd, relative)
    stage = f".{name}.preparing"
    stage_relative = (Path(relative).parent / stage).as_posix()
    descriptor = -1
    try:
        if _exists(parent_fd, stage):
            _fail()
        old_exists = _exists(parent_fd, name)
        if old_exists:
            old_payload, old_identity = _read_relative_with_identity(
                root_fd,
                relative,
            )
        else:
            old_payload = b""
            old_identity = None
        descriptor = _open_anonymous_file(parent_fd, payload)
        _rebind_root(root_fd)
        rebound_parent, rebound_name = _open_parent(root_fd, relative)
        try:
            expected_parent = os.fstat(parent_fd)
            observed_parent = os.fstat(rebound_parent)
            if (
                expected_parent.st_dev,
                expected_parent.st_ino,
                name,
            ) != (
                observed_parent.st_dev,
                observed_parent.st_ino,
                rebound_name,
            ):
                _fail()
        finally:
            os.close(rebound_parent)
        if not old_exists:
            if _exists(parent_fd, name):
                _fail()
            _link_descriptor(parent_fd, descriptor, name)
            published_identity = _safe_file(
                descriptor,
                maximum=MAX_RUNTIME_BYTES,
            )
            try:
                os.fsync(parent_fd)
            except OSError:
                _fail()
            _rebind_root(root_fd)
            _verify_relative(root_fd, relative, payload, published_identity)
            return
        if old_identity is None:
            _fail()
        _link_descriptor(parent_fd, descriptor, stage)
        published_identity = _safe_file(descriptor, maximum=MAX_RUNTIME_BYTES)
        try:
            os.fsync(parent_fd)
        except OSError:
            _fail()
        _rebind_root(root_fd)
        _verify_relative(root_fd, relative, old_payload, old_identity)
        _verify_relative(root_fd, stage_relative, payload, published_identity)
        exchanged = False
        try:
            _rename_exchange(parent_fd, stage, name)
            exchanged = True
            os.fsync(parent_fd)
            _verify_relative(root_fd, relative, payload, published_identity)
            _verify_relative(root_fd, stage_relative, old_payload, old_identity)
        except BaseException:
            if exchanged:
                try:
                    _rename_exchange(parent_fd, stage, name)
                    os.fsync(parent_fd)
                    _verify_relative(root_fd, relative, old_payload, old_identity)
                except BaseException:
                    _fail()
            _fail()
        _rebind_root(root_fd)
        _verify_relative(root_fd, relative, payload, published_identity)
        _verify_relative(root_fd, stage_relative, old_payload, old_identity)
        try:
            os.unlink(stage, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except OSError:
            _fail()
        _rebind_root(root_fd)
        if _exists(parent_fd, stage):
            _fail()
        _verify_relative(root_fd, relative, payload, published_identity)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def _verify_process() -> None:
    flags = sys.flags
    expected_python = (ROOT / ".venv/bin/python").as_posix()
    if (
        sys.executable != expected_python
        or sys.version_info[:3] != (3, 14, 6)
        or flags.isolated != 1
        or flags.ignore_environment != 1
        or flags.no_user_site != 1
        or flags.no_site != 1
        or flags.dont_write_bytecode != 1
        or not flags.safe_path
        or os.getcwd() != ROOT.as_posix()
    ):
        _fail()
    cwd_fd = os.open(".", _DIRECTORY_FLAGS)
    root_fd = _open_absolute_directory(ROOT)
    try:
        cwd = _safe_root(cwd_fd)
        root = _safe_root(root_fd)
        if (cwd.st_dev, cwd.st_ino) != (root.st_dev, root.st_ino):
            _fail()
    finally:
        os.close(cwd_fd)
        os.close(root_fd)


def generate(*, check: bool) -> None:
    root_fd = _open_absolute_directory(ROOT)
    try:
        _safe_root(root_fd)
        expected, snapshots = _manifest_snapshot(root_fd)
        _rebind_root(root_fd)
        relative = MANIFEST_PATH.relative_to(ROOT).as_posix()
        if check:
            if _read_relative(root_fd, relative) != expected:
                _fail()
            _verify_runtime_snapshot(root_fd, snapshots)
            return
        _atomic_write(root_fd, expected)
        _verify_runtime_snapshot(root_fd, snapshots)
    finally:
        os.close(root_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        _verify_process()
        generate(check=arguments.check)
    except BuildFailure as error:
        print(str(error))
        return 2
    except Exception:
        print("ST1704_OWNER_LOCAL_PILOT_BUILD_INVALID")
        return 2
    print("ST1704_OWNER_LOCAL_PILOT_BUILD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
