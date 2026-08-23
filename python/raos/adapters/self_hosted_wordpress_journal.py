"""Durable INTENT/COMMITTED journal for one self-hosted WordPress draft."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, NoReturn, cast, final

from raos.domain.editorial.self_hosted_wordpress import (
    SELF_HOSTED_WORDPRESS_ORIGIN,
    SELF_HOSTED_WORDPRESS_STATUS,
    SelfHostedWordPressDisposition,
    SelfHostedWordPressDraft,
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    SelfHostedWordPressRecoveryObservation,
    SelfHostedWordPressRecoveryObservationDisposition,
    fail_self_hosted_wordpress,
)
from raos.ports.self_hosted_wordpress import (
    SelfHostedWordPressAttemptPort,
    SelfHostedWordPressRecoveryProbePort,
)


_STATE_SCHEMA = "SELF_HOSTED_WORDPRESS_DRAFT_JOURNAL_V1"
_STATE_DIRECTORY = "state"
_STATE_FILE = "draft-journal.v1.json"
_LOCK_FILE = ".draft-journal.v1.lock"
_JOURNAL_PREPARING_FILE = ".draft-journal.v1.preparing"
_RECOVERY_SCHEMA = "SELF_HOSTED_WORDPRESS_DRAFT_RECOVERY_V1"
_RECOVERY_SCOPE = "SELF_HOSTED_AMBIGUOUS_DRAFT_RECOVERY_V1"
_RECOVERY_FILE = "draft-recovery.v1.json"
_RECOVERY_GUARD_SCHEMA = "SELF_HOSTED_WORDPRESS_DRAFT_RECOVERY_GUARD_V1"
_RECOVERY_GUARD_FILE = "draft-recovery.v1.guard"
_RECOVERY_TERMINAL_FILE = ".draft-recovery.v1.terminal"
_RECOVERY_ORIGIN_SHA256 = hashlib.sha256(
    SELF_HOSTED_WORDPRESS_ORIGIN.encode("ascii")
).hexdigest()
_MAX_STATE_BYTES = 64 * 1024
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_HELD_FILE_FLAGS = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_TOP_KEYS = frozenset(
    {"schema", "site_origin", "committed", "pending", "integrity_sha256"}
)
_CANDIDATE_KEYS = frozenset(
    {"operation", "existing_draft_id", "content_sha256", "operation_sha256"}
)
_COMMITTED_KEYS = _CANDIDATE_KEYS | frozenset({"draft_id", "status", "response_sha256"})
_RECOVERY_KEYS = frozenset(
    {
        "schema",
        "scope",
        "origin_sha256",
        "state",
        "outcome",
        "candidate",
        "pending_journal_integrity_sha256",
        "query_sha256",
        "read_response_sha256",
        "write_response_sha256",
        "draft_id",
        "status",
        "reason_code",
        "integrity_sha256",
    }
)
_RECOVERY_GUARD_KEYS = frozenset(
    {
        "schema",
        "scope",
        "origin_sha256",
        "state",
        "candidate",
        "pending_journal_integrity_sha256",
        "integrity_sha256",
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


@dataclass(slots=True)
class _HeldPrivateFile:
    descriptor: int
    name: str
    payload: bytes
    details: os.stat_result


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        component in {"", ".", ".."} for component in path.parts[1:]
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        opened = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if not _same_identity(opened, named) or not stat.S_ISDIR(opened.st_mode):
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
        return current
    except BaseException:
        os.close(current)
        raise


def _private_directory(parent_fd: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    opened = os.fstat(child)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not _same_identity(opened, named)
        or not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_nlink < 2
    ):
        os.close(child)
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    return child


def _open_state_directory(repository_root: Path) -> int:
    current = _open_absolute_directory(repository_root)
    try:
        for component in (".secrets", "wordpress-owner-local", _STATE_DIRECTORY):
            following = _private_directory(current, component, create=True)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


@contextmanager
def _locked(directory_fd: int) -> Generator[None]:
    descriptor = os.open(
        _LOCK_FILE,
        os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
        ):
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            + b"\n"
        )
    except UnicodeError, ValueError, TypeError:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)


def _integrity_payload(*, committed: object, pending: object) -> dict[str, object]:
    return {
        "committed": committed,
        "pending": pending,
        "schema": _STATE_SCHEMA,
        "site_origin": SELF_HOSTED_WORDPRESS_ORIGIN,
    }


def _state_value(*, committed: object, pending: object) -> dict[str, object]:
    payload = _integrity_payload(committed=committed, pending=pending)
    return {
        **payload,
        "integrity_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def _recovery_payload(
    *,
    state: str,
    outcome: str,
    candidate: object,
    pending_journal_integrity_sha256: object,
    query_sha256: object = None,
    read_response_sha256: object = None,
    write_response_sha256: object = None,
    draft_id: object = None,
    status_value: object = None,
    reason_code: object = None,
) -> dict[str, object]:
    return {
        "candidate": candidate,
        "draft_id": draft_id,
        "origin_sha256": _RECOVERY_ORIGIN_SHA256,
        "outcome": outcome,
        "pending_journal_integrity_sha256": pending_journal_integrity_sha256,
        "query_sha256": query_sha256,
        "read_response_sha256": read_response_sha256,
        "reason_code": reason_code,
        "schema": _RECOVERY_SCHEMA,
        "scope": _RECOVERY_SCOPE,
        "state": state,
        "status": status_value,
        "write_response_sha256": write_response_sha256,
    }


def _recovery_value(
    *,
    state: str,
    outcome: str,
    candidate: object,
    pending_journal_integrity_sha256: object,
    query_sha256: object = None,
    read_response_sha256: object = None,
    write_response_sha256: object = None,
    draft_id: object = None,
    status_value: object = None,
    reason_code: object = None,
) -> dict[str, object]:
    payload = _recovery_payload(
        state=state,
        outcome=outcome,
        candidate=candidate,
        pending_journal_integrity_sha256=pending_journal_integrity_sha256,
        query_sha256=query_sha256,
        read_response_sha256=read_response_sha256,
        write_response_sha256=write_response_sha256,
        draft_id=draft_id,
        status_value=status_value,
        reason_code=reason_code,
    )
    return {
        **payload,
        "integrity_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def _recovery_guard_value(
    *,
    candidate: object,
    pending_journal_integrity_sha256: object,
) -> dict[str, object]:
    payload = {
        "candidate": candidate,
        "origin_sha256": _RECOVERY_ORIGIN_SHA256,
        "pending_journal_integrity_sha256": pending_journal_integrity_sha256,
        "schema": _RECOVERY_GUARD_SCHEMA,
        "scope": _RECOVERY_SCOPE,
        "state": "CONSUMED",
    }
    return {
        **payload,
        "integrity_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def _valid_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_PATTERN.fullmatch(value) is not None


def _entry_exists(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return True


def _validated_recovery_candidate(value: object) -> dict[str, object]:
    try:
        candidate = _validated_candidate(value)
    except SelfHostedWordPressFailure:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    if (
        candidate is None
        or candidate["operation"] != SelfHostedWordPressOperation.CREATE_DRAFT.value
        or candidate["existing_draft_id"] is not None
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return candidate


def _validated_integrity_record(
    value: object,
    *,
    expected_keys: frozenset[str],
    expected_schema: str,
    expected_state: str,
) -> dict[str, object]:
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    record = cast(dict[str, object], value)
    if frozenset(record) != expected_keys:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    integrity = record["integrity_sha256"]
    payload = {key: record[key] for key in record if key != "integrity_sha256"}
    if (
        record["schema"] != expected_schema
        or record["scope"] != _RECOVERY_SCOPE
        or record["origin_sha256"] != _RECOVERY_ORIGIN_SHA256
        or record["state"] != expected_state
        or not _valid_sha256(integrity)
        or integrity != hashlib.sha256(_canonical_json(payload)).hexdigest()
        or not _valid_sha256(record["pending_journal_integrity_sha256"])
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    _validated_recovery_candidate(record["candidate"])
    return record


def _validated_recovery_guard(value: object) -> dict[str, object]:
    return _validated_integrity_record(
        value,
        expected_keys=_RECOVERY_GUARD_KEYS,
        expected_schema=_RECOVERY_GUARD_SCHEMA,
        expected_state="CONSUMED",
    )


def _read_recovery_state(directory_fd: int) -> dict[str, object] | None:
    try:
        descriptor = os.open(_RECOVERY_FILE, _FILE_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= _MAX_STATE_BYTES
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
        raw = os.read(descriptor, _MAX_STATE_BYTES + 1)
        after = os.fstat(descriptor)
        named = os.stat(_RECOVERY_FILE, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or len(raw) > _MAX_STATE_BYTES
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    except OSError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    recovery = cast(dict[str, object], value)
    if frozenset(recovery) != _RECOVERY_KEYS:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    integrity = recovery["integrity_sha256"]
    payload = {key: recovery[key] for key in recovery if key != "integrity_sha256"}
    if (
        recovery["schema"] != _RECOVERY_SCHEMA
        or recovery["scope"] != _RECOVERY_SCOPE
        or recovery["origin_sha256"] != _RECOVERY_ORIGIN_SHA256
        or not _valid_sha256(integrity)
        or integrity != hashlib.sha256(_canonical_json(payload)).hexdigest()
        or not _valid_sha256(recovery["pending_journal_integrity_sha256"])
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    _validated_recovery_candidate(recovery["candidate"])
    nullable_hashes = (
        recovery["query_sha256"],
        recovery["read_response_sha256"],
        recovery["write_response_sha256"],
    )
    if any(value is not None and not _valid_sha256(value) for value in nullable_hashes):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    if recovery["state"] == "INTENT" and recovery["outcome"] == "PENDING":
        valid_state = all(
            recovery[key] is None
            for key in (
                "query_sha256",
                "read_response_sha256",
                "write_response_sha256",
                "draft_id",
                "status",
                "reason_code",
            )
        )
    elif recovery["state"] == "TERMINAL" and recovery["outcome"] == "BLOCKED":
        valid_state = (
            type(recovery["reason_code"]) is str
            and recovery["reason_code"]
            in {code.value for code in SelfHostedWordPressFailureCode}
            and all(
                recovery[key] is None
                for key in (
                    "query_sha256",
                    "read_response_sha256",
                    "write_response_sha256",
                    "draft_id",
                    "status",
                )
            )
        )
    elif recovery["state"] == "TERMINAL" and recovery["outcome"] in {
        "RECONCILED_EXISTING",
        "CREATED_AFTER_EXACT_ABSENCE",
    }:
        valid_state = (
            _valid_sha256(recovery["query_sha256"])
            and _valid_sha256(recovery["read_response_sha256"])
            and (
                recovery["write_response_sha256"] is None
                if recovery["outcome"] == "RECONCILED_EXISTING"
                else _valid_sha256(recovery["write_response_sha256"])
            )
            and type(recovery["draft_id"]) is int
            and 1 <= recovery["draft_id"] <= (1 << 63) - 1
            and recovery["status"] == SELF_HOSTED_WORDPRESS_STATUS
            and recovery["reason_code"] is None
        )
    else:
        valid_state = False
    if not valid_state:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return recovery


def _write_recovery_intent(
    directory_fd: int,
    *,
    candidate: SelfHostedWordPressDraft,
    pending_journal_integrity_sha256: str,
) -> tuple[dict[str, object], _HeldPrivateFile]:
    if _entry_exists(directory_fd, _RECOVERY_FILE) or _entry_exists(
        directory_fd, _RECOVERY_TERMINAL_FILE
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED)
    value = _recovery_value(
        state="INTENT",
        outcome="PENDING",
        candidate=_candidate_record(candidate),
        pending_journal_integrity_sha256=pending_journal_integrity_sha256,
    )
    payload = _canonical_json(value)
    held = _create_held_private_file(
        directory_fd,
        name=_RECOVERY_FILE,
        payload=payload,
    )
    observed = _read_recovery_state(directory_fd)
    if observed != value:
        _close_held_private_file(held)
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return value, held


def _write_recovery_guard(
    directory_fd: int,
    *,
    candidate: SelfHostedWordPressDraft,
    pending_journal_integrity_sha256: str,
) -> tuple[dict[str, object], _HeldPrivateFile]:
    if _entry_exists(directory_fd, _RECOVERY_GUARD_FILE):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED)
    value = _recovery_guard_value(
        candidate=_candidate_record(candidate),
        pending_journal_integrity_sha256=pending_journal_integrity_sha256,
    )
    _validated_recovery_guard(value)
    held = _create_held_private_file(
        directory_fd,
        name=_RECOVERY_GUARD_FILE,
        payload=_canonical_json(value),
    )
    return value, held


def _write_recovery_terminal(
    directory_fd: int,
    *,
    held: _HeldPrivateFile,
    intent: dict[str, object],
    outcome: str,
    query_sha256: str | None = None,
    read_response_sha256: str | None = None,
    write_response_sha256: str | None = None,
    draft_id: int | None = None,
    status_value: str | None = None,
    reason_code: SelfHostedWordPressFailureCode | None = None,
) -> dict[str, object]:
    current = _read_recovery_state(directory_fd)
    if current != intent or current is None or current["state"] != "INTENT":
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    value = _recovery_value(
        state="TERMINAL",
        outcome=outcome,
        candidate=current["candidate"],
        pending_journal_integrity_sha256=current["pending_journal_integrity_sha256"],
        query_sha256=query_sha256,
        read_response_sha256=read_response_sha256,
        write_response_sha256=write_response_sha256,
        draft_id=draft_id,
        status_value=status_value,
        reason_code=None if reason_code is None else reason_code.value,
    )
    _rewrite_held_private_file(directory_fd, held, _canonical_json(value))
    if _read_recovery_state(directory_fd) != value:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return value


def _candidate_record(candidate: SelfHostedWordPressDraft) -> dict[str, object]:
    return {
        "content_sha256": candidate.content_sha256,
        "existing_draft_id": candidate.existing_draft_id,
        "operation": candidate.operation.value,
        "operation_sha256": candidate.operation_sha256,
    }


def _validated_candidate(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    record = cast(dict[str, object], value)
    if (
        frozenset(record) != _CANDIDATE_KEYS
        or record["operation"]
        not in {
            SelfHostedWordPressOperation.CREATE_DRAFT.value,
            SelfHostedWordPressOperation.UPDATE_DRAFT.value,
        }
        or any(
            type(record[key]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", cast(str, record[key]), re.ASCII) is None
            for key in ("content_sha256", "operation_sha256")
        )
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    existing_draft_id = record["existing_draft_id"]
    if record["operation"] == SelfHostedWordPressOperation.CREATE_DRAFT.value:
        if existing_draft_id is not None:
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    elif (
        type(existing_draft_id) is not int
        or not 1 <= existing_draft_id <= (1 << 63) - 1
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    return record


def _committed_record(
    candidate: SelfHostedWordPressDraft,
    receipt: SelfHostedWordPressDraftReceipt,
) -> dict[str, object]:
    return {
        **_candidate_record(candidate),
        "draft_id": receipt.draft_id,
        "response_sha256": receipt.response_sha256,
        "status": receipt.status,
    }


def _read_state(directory_fd: int) -> dict[str, object] | None:
    try:
        descriptor = os.open(_STATE_FILE, _FILE_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= _MAX_STATE_BYTES
        ):
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
        raw = os.read(descriptor, _MAX_STATE_BYTES + 1)
        after = os.fstat(descriptor)
        named = os.stat(_STATE_FILE, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or len(raw) > _MAX_STATE_BYTES
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    state = cast(dict[str, object], value)
    if (
        frozenset(state) != _TOP_KEYS
        or state["schema"] != _STATE_SCHEMA
        or state["site_origin"] != SELF_HOSTED_WORDPRESS_ORIGIN
        or type(state["integrity_sha256"]) is not str
        or state["integrity_sha256"]
        != hashlib.sha256(
            _canonical_json(
                _integrity_payload(
                    committed=state["committed"], pending=state["pending"]
                )
            )
        ).hexdigest()
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    committed = state["committed"]
    pending = state["pending"]
    if committed is not None and (
        type(committed) is not dict
        or frozenset(cast(dict[str, object], committed)) != _COMMITTED_KEYS
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    if pending is not None and (
        type(pending) is not dict
        or frozenset(cast(dict[str, object], pending)) != _CANDIDATE_KEYS
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    return state


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("journal write failed")
        offset += written


def _validated_held_details(
    directory_fd: int,
    held: _HeldPrivateFile,
    *,
    expected_previous: os.stat_result | None,
) -> os.stat_result:
    try:
        before = os.fstat(held.descriptor)
        raw = os.pread(held.descriptor, _MAX_STATE_BYTES + 1, 0)
        after = os.fstat(held.descriptor)
        named = os.stat(held.name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 1 <= before.st_size <= _MAX_STATE_BYTES
        or raw != held.payload
        or len(raw) != before.st_size
        or not _same_identity(before, after)
        or not _same_identity(after, named)
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    if expected_previous is not None and (
        not _same_identity(expected_previous, before)
        or expected_previous.st_nlink != before.st_nlink
        or expected_previous.st_size != before.st_size
        or expected_previous.st_mtime_ns != before.st_mtime_ns
        or expected_previous.st_ctime_ns != before.st_ctime_ns
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return after


def _open_held_private_file(
    directory_fd: int,
    *,
    name: str,
    payload: bytes,
) -> _HeldPrivateFile:
    descriptor = -1
    try:
        descriptor = os.open(name, _HELD_FILE_FLAGS, dir_fd=directory_fd)
        held = _HeldPrivateFile(
            descriptor=descriptor,
            name=name,
            payload=payload,
            details=os.fstat(descriptor),
        )
        held.details = _validated_held_details(
            directory_fd,
            held,
            expected_previous=None,
        )
        return held
    except SelfHostedWordPressFailure:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError, TypeError, ValueError:
        if descriptor >= 0:
            os.close(descriptor)
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)


def _create_held_private_file(
    directory_fd: int,
    *,
    name: str,
    payload: bytes,
) -> _HeldPrivateFile:
    if type(payload) is not bytes or not 1 <= len(payload) <= _MAX_STATE_BYTES:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            _HELD_FILE_FLAGS | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(directory_fd)
        held = _HeldPrivateFile(
            descriptor=descriptor,
            name=name,
            payload=payload,
            details=os.fstat(descriptor),
        )
        held.details = _validated_held_details(
            directory_fd,
            held,
            expected_previous=None,
        )
        return held
    except SelfHostedWordPressFailure:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError, TypeError, ValueError:
        if descriptor >= 0:
            os.close(descriptor)
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)


def _revalidate_held_private_file(
    directory_fd: int,
    held: _HeldPrivateFile,
) -> None:
    _validated_held_details(
        directory_fd,
        held,
        expected_previous=held.details,
    )


def _rewrite_held_private_file(
    directory_fd: int,
    held: _HeldPrivateFile,
    payload: bytes,
) -> None:
    if type(payload) is not bytes or not 1 <= len(payload) <= _MAX_STATE_BYTES:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    _revalidate_held_private_file(directory_fd, held)
    try:
        os.ftruncate(held.descriptor, 0)
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        _write_all(held.descriptor, payload)
        os.fchmod(held.descriptor, 0o600)
        os.fsync(held.descriptor)
        os.fsync(directory_fd)
    except OSError, TypeError, ValueError:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    held.payload = payload
    held.details = _validated_held_details(
        directory_fd,
        held,
        expected_previous=None,
    )


def _close_held_private_file(held: _HeldPrivateFile | None) -> None:
    if held is None:
        return
    try:
        os.close(held.descriptor)
    except OSError:
        pass


def _validate_recovery_window(
    directory_fd: int,
    *,
    guard: dict[str, object],
    guard_held: _HeldPrivateFile,
    intent: dict[str, object],
    intent_held: _HeldPrivateFile,
    pending_journal: dict[str, object],
    journal_held: _HeldPrivateFile,
) -> None:
    _revalidate_held_private_file(directory_fd, guard_held)
    _revalidate_held_private_file(directory_fd, intent_held)
    _revalidate_held_private_file(directory_fd, journal_held)
    validated_guard = _validated_recovery_guard(guard)
    observed_intent = _read_recovery_state(directory_fd)
    observed_journal = _read_state(directory_fd)
    pending = _validated_candidate(pending_journal.get("pending"))
    if (
        observed_intent != intent
        or observed_journal != pending_journal
        or intent.get("state") != "INTENT"
        or intent.get("outcome") != "PENDING"
        or pending_journal.get("committed") is not None
        or pending != validated_guard["candidate"]
        or pending != intent["candidate"]
        or pending_journal.get("integrity_sha256")
        != validated_guard["pending_journal_integrity_sha256"]
        or pending_journal.get("integrity_sha256")
        != intent["pending_journal_integrity_sha256"]
        or _entry_exists(directory_fd, _RECOVERY_TERMINAL_FILE)
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)


def _write_committed_recovery_journal(
    directory_fd: int,
    *,
    held: _HeldPrivateFile,
    candidate: SelfHostedWordPressDraft,
    receipt: SelfHostedWordPressDraftReceipt,
) -> dict[str, object]:
    value = _state_value(
        committed=_committed_record(candidate, receipt),
        pending=None,
    )
    _rewrite_held_private_file(directory_fd, held, _canonical_json(value))
    if _read_state(directory_fd) != value:
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
    return value


def _ensure_recovery_guard(
    directory_fd: int,
    *,
    guard: dict[str, object],
) -> None:
    try:
        if _entry_exists(directory_fd, _RECOVERY_GUARD_FILE):
            return
        replacement = _create_held_private_file(
            directory_fd,
            name=_RECOVERY_GUARD_FILE,
            payload=_canonical_json(guard),
        )
        _close_held_private_file(replacement)
    except BaseException:
        pass


def _terminalize_recovery_failure(
    directory_fd: int,
    *,
    guard: dict[str, object],
    guard_held: _HeldPrivateFile,
    intent: dict[str, object],
    intent_held: _HeldPrivateFile,
    pending_journal: dict[str, object],
    journal_held: _HeldPrivateFile,
    reason_code: SelfHostedWordPressFailureCode,
) -> None:
    _validate_recovery_window(
        directory_fd,
        guard=guard,
        guard_held=guard_held,
        intent=intent,
        intent_held=intent_held,
        pending_journal=pending_journal,
        journal_held=journal_held,
    )
    terminal = _write_recovery_terminal(
        directory_fd,
        held=intent_held,
        intent=intent,
        outcome="BLOCKED",
        reason_code=reason_code,
    )
    _revalidate_held_private_file(directory_fd, guard_held)
    _revalidate_held_private_file(directory_fd, intent_held)
    _revalidate_held_private_file(directory_fd, journal_held)
    if (
        _validated_recovery_guard(guard) != guard
        or _read_state(directory_fd) != pending_journal
        or _read_recovery_state(directory_fd) != terminal
    ):
        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)


def _write_state(directory_fd: int, value: dict[str, object]) -> None:
    payload = _canonical_json(value)
    temporary = ".draft-journal.v1.preparing"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.replace(
            temporary,
            _STATE_FILE,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    except OSError, TypeError, ValueError:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError:
            pass


def _validated_committed(
    value: object,
) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    record = cast(dict[str, object], value)
    if frozenset(record) != _COMMITTED_KEYS:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    candidate = _validated_candidate({key: record[key] for key in _CANDIDATE_KEYS})
    if candidate is None:
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    if (
        type(record["draft_id"]) is not int
        or not 1 <= record["draft_id"] <= (1 << 63) - 1
        or record["status"] != SELF_HOSTED_WORDPRESS_STATUS
        or type(record["response_sha256"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", record["response_sha256"], re.ASCII) is None
        or (
            record["operation"] == SelfHostedWordPressOperation.UPDATE_DRAFT.value
            and record["existing_draft_id"] != record["draft_id"]
        )
    ):
        _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
    return record


@final
class DurableSelfHostedWordPressDraftAdapter:
    """Application-facing exactly-once local journal wrapper."""

    __slots__ = ("_attempt_port", "_repository_root")

    def __init__(
        self,
        *,
        repository_root: object,
        attempt_port: object,
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(attempt_port, SelfHostedWordPressAttemptPort)
        ):
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
        self._repository_root = repository_root
        self._attempt_port = attempt_port

    def __repr__(self) -> str:
        return "DurableSelfHostedWordPressDraftAdapter(<redacted>)"

    def apply(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt:
        if type(candidate) is not SelfHostedWordPressDraft:
            _fail(SelfHostedWordPressFailureCode.INVALID_ARGUMENT)
        directory_fd = -1
        try:
            directory_fd = _open_state_directory(self._repository_root)
            with _locked(directory_fd):
                recovery_marker = any(
                    _entry_exists(directory_fd, name)
                    for name in (
                        _RECOVERY_GUARD_FILE,
                        _RECOVERY_FILE,
                        _RECOVERY_TERMINAL_FILE,
                    )
                )
                try:
                    state = _read_state(directory_fd)
                except SelfHostedWordPressFailure:
                    if recovery_marker:
                        _fail(SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS)
                    raise
                committed = None
                if state is not None:
                    pending = _validated_candidate(state["pending"])
                    if pending is not None:
                        _fail(SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS)
                    committed = _validated_committed(state["committed"])
                if recovery_marker and committed is None:
                    _fail(SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS)
                if committed is not None:
                    if committed["operation_sha256"] == candidate.operation_sha256:
                        if (
                            committed["content_sha256"] != candidate.content_sha256
                            or committed["operation"] != candidate.operation.value
                            or committed["existing_draft_id"]
                            != candidate.existing_draft_id
                        ):
                            _fail(SelfHostedWordPressFailureCode.JOURNAL_MISMATCH)
                        return SelfHostedWordPressDraftReceipt(
                            draft_id=cast(int, committed["draft_id"]),
                            operation=candidate.operation,
                            disposition=SelfHostedWordPressDisposition.REPLAYED,
                            status=SELF_HOSTED_WORDPRESS_STATUS,
                            content_sha256=candidate.content_sha256,
                            operation_sha256=candidate.operation_sha256,
                            response_sha256=cast(str, committed["response_sha256"]),
                        )
                    if candidate.operation is SelfHostedWordPressOperation.CREATE_DRAFT:
                        _fail(SelfHostedWordPressFailureCode.JOURNAL_MISMATCH)
                    if candidate.existing_draft_id != committed["draft_id"]:
                        _fail(SelfHostedWordPressFailureCode.JOURNAL_MISMATCH)
                elif candidate.operation is SelfHostedWordPressOperation.UPDATE_DRAFT:
                    _fail(SelfHostedWordPressFailureCode.JOURNAL_MISMATCH)

                _write_state(
                    directory_fd,
                    _state_value(
                        committed=committed,
                        pending=_candidate_record(candidate),
                    ),
                )
                receipt = self._attempt_port.attempt(candidate)
                expected_disposition = (
                    SelfHostedWordPressDisposition.CREATED
                    if candidate.operation is SelfHostedWordPressOperation.CREATE_DRAFT
                    else SelfHostedWordPressDisposition.UPDATED
                )
                if (
                    type(receipt) is not SelfHostedWordPressDraftReceipt
                    or receipt.operation is not candidate.operation
                    or receipt.disposition is not expected_disposition
                    or receipt.content_sha256 != candidate.content_sha256
                    or receipt.operation_sha256 != candidate.operation_sha256
                    or receipt.status != SELF_HOSTED_WORDPRESS_STATUS
                    or (
                        candidate.existing_draft_id is not None
                        and receipt.draft_id != candidate.existing_draft_id
                    )
                ):
                    _fail(SelfHostedWordPressFailureCode.OUTCOME_MISMATCH)
                _write_state(
                    directory_fd,
                    _state_value(
                        committed=_committed_record(candidate, receipt),
                        pending=None,
                    ),
                )
                return receipt
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(SelfHostedWordPressFailureCode.JOURNAL_INVALID)
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)


@final
class DurableSelfHostedWordPressDraftRecoveryAdapter:
    """Consume one pending CREATE intent through one read-before-write path."""

    __slots__ = ("_attempt_port", "_probe_port", "_repository_root")

    def __init__(
        self,
        *,
        repository_root: object,
        probe_port: object,
        attempt_port: object,
    ) -> None:
        if (
            not isinstance(repository_root, Path)
            or not repository_root.is_absolute()
            or not isinstance(probe_port, SelfHostedWordPressRecoveryProbePort)
            or not isinstance(attempt_port, SelfHostedWordPressAttemptPort)
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
        self._repository_root = repository_root
        self._probe_port = probe_port
        self._attempt_port = attempt_port

    def __repr__(self) -> str:
        return "DurableSelfHostedWordPressDraftRecoveryAdapter(<redacted>)"

    def recover(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt:
        if (
            type(candidate) is not SelfHostedWordPressDraft
            or candidate.operation is not SelfHostedWordPressOperation.CREATE_DRAFT
            or candidate.existing_draft_id is not None
        ):
            _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
        directory_fd = -1
        guard_held: _HeldPrivateFile | None = None
        intent_held: _HeldPrivateFile | None = None
        journal_held: _HeldPrivateFile | None = None
        try:
            directory_fd = _open_state_directory(self._repository_root)
            with _locked(directory_fd):
                if _entry_exists(directory_fd, _JOURNAL_PREPARING_FILE):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
                if _entry_exists(directory_fd, _RECOVERY_GUARD_FILE):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED)
                existing_recovery = _read_recovery_state(directory_fd)
                if existing_recovery is not None or _entry_exists(
                    directory_fd, _RECOVERY_TERMINAL_FILE
                ):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED)
                state = _read_state(directory_fd)
                if state is None:
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
                pending = _validated_candidate(state["pending"])
                committed = _validated_committed(state["committed"])
                expected_pending = _candidate_record(candidate)
                if (
                    committed is not None
                    or pending is None
                    or pending != expected_pending
                    or pending["operation"]
                    != SelfHostedWordPressOperation.CREATE_DRAFT.value
                ):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
                journal_integrity = state["integrity_sha256"]
                if not _valid_sha256(journal_integrity):
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
                journal_held = _open_held_private_file(
                    directory_fd,
                    name=_STATE_FILE,
                    payload=_canonical_json(state),
                )
                guard, guard_held = _write_recovery_guard(
                    directory_fd,
                    candidate=candidate,
                    pending_journal_integrity_sha256=cast(str, journal_integrity),
                )
                intent, intent_held = _write_recovery_intent(
                    directory_fd,
                    candidate=candidate,
                    pending_journal_integrity_sha256=cast(str, journal_integrity),
                )
                try:
                    _validate_recovery_window(
                        directory_fd,
                        guard=guard,
                        guard_held=guard_held,
                        intent=intent,
                        intent_held=intent_held,
                        pending_journal=state,
                        journal_held=journal_held,
                    )
                    observation = self._probe_port.observe(candidate)
                    _validate_recovery_window(
                        directory_fd,
                        guard=guard,
                        guard_held=guard_held,
                        intent=intent,
                        intent_held=intent_held,
                        pending_journal=state,
                        journal_held=journal_held,
                    )
                    if (
                        type(observation) is not SelfHostedWordPressRecoveryObservation
                        or observation.content_sha256 != candidate.content_sha256
                        or observation.operation_sha256 != candidate.operation_sha256
                    ):
                        _fail(SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH)
                    if (
                        observation.disposition
                        is SelfHostedWordPressRecoveryObservationDisposition.EXACT_DRAFT
                    ):
                        if observation.draft_id is None:
                            _fail(
                                SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH
                            )
                        receipt = SelfHostedWordPressDraftReceipt(
                            draft_id=observation.draft_id,
                            operation=candidate.operation,
                            disposition=SelfHostedWordPressDisposition.RECONCILED,
                            status=SELF_HOSTED_WORDPRESS_STATUS,
                            content_sha256=candidate.content_sha256,
                            operation_sha256=candidate.operation_sha256,
                            response_sha256=observation.response_sha256,
                        )
                        outcome = "RECONCILED_EXISTING"
                        write_response_sha256 = None
                    elif (
                        observation.disposition
                        is SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE
                    ):
                        _validate_recovery_window(
                            directory_fd,
                            guard=guard,
                            guard_held=guard_held,
                            intent=intent,
                            intent_held=intent_held,
                            pending_journal=state,
                            journal_held=journal_held,
                        )
                        receipt = self._attempt_port.attempt(candidate)
                        _validate_recovery_window(
                            directory_fd,
                            guard=guard,
                            guard_held=guard_held,
                            intent=intent,
                            intent_held=intent_held,
                            pending_journal=state,
                            journal_held=journal_held,
                        )
                        if (
                            type(receipt) is not SelfHostedWordPressDraftReceipt
                            or receipt.operation
                            is not SelfHostedWordPressOperation.CREATE_DRAFT
                            or receipt.disposition
                            is not SelfHostedWordPressDisposition.CREATED
                            or receipt.content_sha256 != candidate.content_sha256
                            or receipt.operation_sha256 != candidate.operation_sha256
                            or receipt.status != SELF_HOSTED_WORDPRESS_STATUS
                        ):
                            _fail(SelfHostedWordPressFailureCode.OUTCOME_MISMATCH)
                        outcome = "CREATED_AFTER_EXACT_ABSENCE"
                        write_response_sha256 = receipt.response_sha256
                    else:
                        _fail(SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH)
                    _validate_recovery_window(
                        directory_fd,
                        guard=guard,
                        guard_held=guard_held,
                        intent=intent,
                        intent_held=intent_held,
                        pending_journal=state,
                        journal_held=journal_held,
                    )
                    committed_journal = _write_committed_recovery_journal(
                        directory_fd,
                        held=journal_held,
                        candidate=candidate,
                        receipt=receipt,
                    )
                    terminal = _write_recovery_terminal(
                        directory_fd,
                        held=intent_held,
                        intent=intent,
                        outcome=outcome,
                        query_sha256=observation.query_sha256,
                        read_response_sha256=observation.response_sha256,
                        write_response_sha256=write_response_sha256,
                        draft_id=receipt.draft_id,
                        status_value=receipt.status,
                    )
                    _revalidate_held_private_file(directory_fd, guard_held)
                    _revalidate_held_private_file(directory_fd, intent_held)
                    _revalidate_held_private_file(directory_fd, journal_held)
                    if (
                        _validated_recovery_guard(guard) != guard
                        or _read_recovery_state(directory_fd) != terminal
                        or _read_state(directory_fd) != committed_journal
                    ):
                        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
                    return receipt
                except SelfHostedWordPressFailure as error:
                    try:
                        _terminalize_recovery_failure(
                            directory_fd,
                            guard=guard,
                            guard_held=guard_held,
                            intent=intent,
                            intent_held=intent_held,
                            pending_journal=state,
                            journal_held=journal_held,
                            reason_code=error.code,
                        )
                    except BaseException:
                        _ensure_recovery_guard(directory_fd, guard=guard)
                        _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
                    raise
                except BaseException:
                    try:
                        _terminalize_recovery_failure(
                            directory_fd,
                            guard=guard,
                            guard_held=guard_held,
                            intent=intent,
                            intent_held=intent_held,
                            pending_journal=state,
                            journal_held=journal_held,
                            reason_code=(
                                SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
                            ),
                        )
                    except BaseException:
                        _ensure_recovery_guard(directory_fd, guard=guard)
                    _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
        except SelfHostedWordPressFailure:
            raise
        except BaseException:
            _fail(SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID)
        finally:
            _close_held_private_file(journal_held)
            _close_held_private_file(intent_held)
            _close_held_private_file(guard_held)
            if directory_fd >= 0:
                os.close(directory_fd)


__all__ = [
    "DurableSelfHostedWordPressDraftAdapter",
    "DurableSelfHostedWordPressDraftRecoveryAdapter",
]
