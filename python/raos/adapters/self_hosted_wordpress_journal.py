"""Durable INTENT/COMMITTED journal for one self-hosted WordPress draft."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
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
    fail_self_hosted_wordpress,
)
from raos.ports.self_hosted_wordpress import SelfHostedWordPressAttemptPort


_STATE_SCHEMA = "SELF_HOSTED_WORDPRESS_DRAFT_JOURNAL_V1"
_STATE_DIRECTORY = "state"
_STATE_FILE = "draft-journal.v1.json"
_LOCK_FILE = ".draft-journal.v1.lock"
_MAX_STATE_BYTES = 64 * 1024
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_TOP_KEYS = frozenset(
    {"schema", "site_origin", "committed", "pending", "integrity_sha256"}
)
_CANDIDATE_KEYS = frozenset(
    {"operation", "existing_draft_id", "content_sha256", "operation_sha256"}
)
_COMMITTED_KEYS = _CANDIDATE_KEYS | frozenset({"draft_id", "status", "response_sha256"})


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


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
                state = _read_state(directory_fd)
                committed = None
                if state is not None:
                    pending = _validated_candidate(state["pending"])
                    if pending is not None:
                        _fail(SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS)
                    committed = _validated_committed(state["committed"])
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


__all__ = ["DurableSelfHostedWordPressDraftAdapter"]
