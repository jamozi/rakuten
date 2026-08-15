"""Owner-private immutable record journal for the ST-1703 WordPress.com Wave 3."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import TracebackType
from typing import Any, Generator, NoReturn, cast, final

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftOperationState,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
)
from raos.ports.wordpresscom_mvp_draft_journal import MvpDraftJournalEntry


_SCHEMA = "WORDPRESSCOM_MVP_DRAFT_JOURNAL_RECORD_V1"
_ROOT_DIRECTORY = "mvp-wave3-state"
_ROOT_PARENT_DIRECTORY = "wordpresscom-review-draft"
_RECORDS_DIRECTORY = "records"
_LOCK_FILE = ".mvp-wave3.lock"
_MAX_RECORDS = 128
_MAX_RECORD_BYTES = 4096
_ZERO_SHA256 = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RECORD_NAME = re.compile(r"([0-9]{8})\.json\Z", re.ASCII)
_CANONICAL_ID = re.compile(r"[1-9][0-9]*\Z", re.ASCII)
_MAX_ID = (1 << 63) - 1
_RECORD_KEYS = {
    "object_id",
    "operation_binding_sha256",
    "operation_id",
    "previous_record_sha256",
    "reason_code",
    "record_sha256",
    "schema",
    "sequence",
    "state",
}
_EXACT_TERMINAL = {
    MvpDraftOperationState.REUSED_EXACT,
    MvpDraftOperationState.COMMITTED,
    MvpDraftOperationState.RECONCILED_COMMITTED,
}
_REASONS_BY_STATE = {
    MvpDraftOperationState.REUSED_EXACT: frozenset({"EXACT_DESIRED"}),
    MvpDraftOperationState.INTENT: frozenset({"POST_BUDGET_CONSUMED"}),
    MvpDraftOperationState.COMMITTED: frozenset({"EXACT_READBACK"}),
    MvpDraftOperationState.MUTATION_AMBIGUOUS: frozenset({"READBACK_UNCERTAIN"}),
    MvpDraftOperationState.RECONCILED_COMMITTED: frozenset({"EXACT_RECONCILIATION"}),
    MvpDraftOperationState.REFUSED_MISMATCH: frozenset(
        {
            "BASELINE_MISMATCH",
            "SECOND_BASELINE_MISMATCH",
            "DUPLICATE_SLUG",
            "EXISTING_PAGE_MISMATCH",
            "EXISTING_PAGE_ID_MISMATCH",
            "SECOND_SCAN_COLLISION",
        }
    ),
}
_ARTICLE_REFUSAL_REASONS = frozenset({"BASELINE_MISMATCH", "SECOND_BASELINE_MISMATCH"})
_PAGE_REFUSAL_REASONS = frozenset(
    {
        "DUPLICATE_SLUG",
        "EXISTING_PAGE_MISMATCH",
        "EXISTING_PAGE_ID_MISMATCH",
        "SECOND_SCAN_COLLISION",
    }
)


def _fail(code: WordPressComMvpDraftFailureCode) -> NoReturn:
    fail_wordpresscom_mvp_draft(code)


def _canonical(value: dict[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)


def _record_hash(value: dict[str, object]) -> str:
    try:
        core = {key: item for key, item in value.items() if key != "record_sha256"}
        return hashlib.sha256(_canonical(core)).hexdigest()
    except WordPressComMvpDraftFailure:
        raise
    except RecursionError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)


def _release_lock(descriptor: int) -> None:
    failed = False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except BaseException:
        failed = True
    try:
        os.close(descriptor)
    except BaseException:
        failed = True
    if failed:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)


def _no_symlink_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        if stat.S_ISLNK(metadata.st_mode):
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        if current.parent == current:
            return
        current = current.parent


def _private_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)


def _open_private(path: Path, flags: int, mode: int = 0o600) -> int:
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
        metadata = os.fstat(descriptor)
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        os.close(descriptor)
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    return descriptor


def _read_record(path: Path) -> dict[str, object]:
    descriptor = _open_private(path, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(4096, _MAX_RECORD_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_RECORD_BYTES:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
            chunks.append(chunk)
    except WordPressComMvpDraftFailure:
        raise
    except OSError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        value = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeError, ValueError, RecursionError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    if type(value) is not dict:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    mapping = cast(dict[str, object], value)
    if set(mapping) != _RECORD_KEYS or _canonical(mapping) != raw:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    return mapping


def _entry(mapping: dict[str, object]) -> MvpDraftJournalEntry:
    sequence = mapping.get("sequence")
    operation_id = mapping.get("operation_id")
    binding = mapping.get("operation_binding_sha256")
    state_value = mapping.get("state")
    reason_code = mapping.get("reason_code")
    object_id = mapping.get("object_id")
    previous = mapping.get("previous_record_sha256")
    record = mapping.get("record_sha256")
    if (
        mapping.get("schema") != _SCHEMA
        or type(sequence) is not int
        or not 1 <= sequence <= _MAX_RECORDS
        or type(operation_id) is not str
        or operation_id not in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
        or type(binding) is not str
        or _SHA256.fullmatch(binding) is None
        or type(state_value) is not str
        or state_value == MvpDraftOperationState.NO_STATE.value
        or type(reason_code) is not str
        or not reason_code
        or not reason_code.isascii()
        or len(reason_code) > 80
        or not re.fullmatch(r"[A-Z][A-Z0-9_]*", reason_code, re.ASCII)
        or (object_id is not None and type(object_id) is not str)
        or type(previous) is not str
        or _SHA256.fullmatch(previous) is None
        or type(record) is not str
        or _SHA256.fullmatch(record) is None
        or record != _record_hash(mapping)
    ):
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    try:
        state = MvpDraftOperationState(state_value)
    except ValueError:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    canonical_object_id = (
        type(object_id) is str
        and _CANONICAL_ID.fullmatch(object_id) is not None
        and int(object_id) <= _MAX_ID
    )
    article = operation_id == WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]
    if (
        reason_code not in _REASONS_BY_STATE.get(state, frozenset())
        or (
            state is MvpDraftOperationState.REFUSED_MISMATCH
            and reason_code
            not in (_ARTICLE_REFUSAL_REASONS if article else _PAGE_REFUSAL_REASONS)
        )
        or (state is MvpDraftOperationState.REFUSED_MISMATCH and object_id is not None)
        or (
            state is MvpDraftOperationState.INTENT
            and object_id != ("7" if article else None)
        )
        or (
            state is MvpDraftOperationState.MUTATION_AMBIGUOUS
            and object_id != ("7" if article else None)
        )
        or (
            state
            in {
                MvpDraftOperationState.REUSED_EXACT,
                MvpDraftOperationState.COMMITTED,
                MvpDraftOperationState.RECONCILED_COMMITTED,
            }
            and not canonical_object_id
        )
        or (article and object_id is not None and object_id != "7")
    ):
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    return MvpDraftJournalEntry(
        sequence=sequence,
        operation_id=operation_id,
        operation_binding_sha256=binding,
        state=state,
        reason_code=reason_code,
        object_id=object_id,
        previous_record_sha256=previous,
        record_sha256=record,
    )


def _validate_lifecycle(entries: tuple[MvpDraftJournalEntry, ...]) -> None:
    histories: dict[str, list[MvpDraftOperationState]] = {
        operation_id: [] for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
    }
    bindings: dict[str, str] = {}
    for expected_sequence, entry in enumerate(entries, start=1):
        if entry.sequence != expected_sequence:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        history = histories[entry.operation_id]
        binding = bindings.setdefault(
            entry.operation_id, entry.operation_binding_sha256
        )
        if binding != entry.operation_binding_sha256:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        if not history:
            if entry.state not in {
                MvpDraftOperationState.REUSED_EXACT,
                MvpDraftOperationState.INTENT,
                MvpDraftOperationState.REFUSED_MISMATCH,
            }:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        elif history == [MvpDraftOperationState.INTENT]:
            if entry.state not in {
                MvpDraftOperationState.COMMITTED,
                MvpDraftOperationState.MUTATION_AMBIGUOUS,
                MvpDraftOperationState.RECONCILED_COMMITTED,
                MvpDraftOperationState.REFUSED_MISMATCH,
            }:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        elif history == [
            MvpDraftOperationState.INTENT,
            MvpDraftOperationState.MUTATION_AMBIGUOUS,
        ]:
            if entry.state is not MvpDraftOperationState.RECONCILED_COMMITTED:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        else:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        operation_index = WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER.index(
            entry.operation_id
        )
        for predecessor in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[:operation_index]:
            predecessor_history = histories[predecessor]
            if (
                not predecessor_history
                or predecessor_history[-1] not in _EXACT_TERMINAL
            ):
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        histories[entry.operation_id].append(entry.state)


@final
class _RefusedLock(AbstractContextManager[None]):
    __slots__ = ()

    def __enter__(self) -> NoReturn:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback


@final
class EmptyWordPressComMvpDraftJournalView:
    """Represent a missing Wave 3 journal without creating any filesystem state."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "EmptyWordPressComMvpDraftJournalView(<redacted-wordpresscom-wave3>)"

    def locked(self) -> AbstractContextManager[None]:
        return _RefusedLock()

    def entries(self) -> tuple[MvpDraftJournalEntry, ...]:
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)

    def inspect(self) -> tuple[MvpDraftJournalEntry, ...]:
        return ()

    def append(
        self,
        *,
        operation_id: str,
        operation_binding_sha256: str,
        state: MvpDraftOperationState,
        reason_code: str,
        object_id: str | None,
    ) -> MvpDraftJournalEntry:
        del operation_id, operation_binding_sha256, state, reason_code, object_id
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)


@final
class ImmutableWordPressComMvpDraftJournal:
    """Append exclusive, fsynced, sequence/hash-chain records under one lock."""

    __slots__ = ("_lock_depth", "_lock_descriptor", "_records", "_root")

    def __init__(self, *, root: object) -> None:
        if not isinstance(root, Path):
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        physical = Path(os.path.abspath(root))
        if (
            physical.name != _ROOT_DIRECTORY
            or physical.parent.name != _ROOT_PARENT_DIRECTORY
        ):
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        _no_symlink_ancestors(physical)
        _private_directory(physical)
        records = physical / _RECORDS_DIRECTORY
        _private_directory(records)
        self._root = physical
        self._records = records
        self._lock_descriptor: int | None = None
        self._lock_depth = 0

    def __repr__(self) -> str:
        return "ImmutableWordPressComMvpDraftJournal(<redacted-wordpresscom-wave3>)"

    @contextmanager
    def locked(self) -> Generator[None]:
        if self._lock_depth != 0 or self._lock_descriptor is not None:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        _no_symlink_ancestors(self._root)
        _private_directory(self._root)
        _private_directory(self._records)
        descriptor = _open_private(self._root / _LOCK_FILE, os.O_RDWR | os.O_CREAT)
        self._lock_descriptor = descriptor
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._lock_depth = 1
            self.entries()
            yield
        except WordPressComMvpDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        finally:
            self._lock_depth = 0
            self._lock_descriptor = None
            _release_lock(descriptor)

    def _require_locked(self) -> None:
        if self._lock_depth != 1 or self._lock_descriptor is None:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)

    def entries(self) -> tuple[MvpDraftJournalEntry, ...]:
        self._require_locked()
        try:
            names = sorted(os.listdir(self._records))
        except OSError:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        if len(names) > _MAX_RECORDS:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        entries: list[MvpDraftJournalEntry] = []
        previous = _ZERO_SHA256
        for expected_sequence, name in enumerate(names, start=1):
            match = _RECORD_NAME.fullmatch(name)
            if match is None or int(match.group(1)) != expected_sequence:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
            mapping = _read_record(self._records / name)
            entry = _entry(mapping)
            if (
                entry.sequence != expected_sequence
                or entry.previous_record_sha256 != previous
            ):
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
            entries.append(entry)
            previous = entry.record_sha256
        result = tuple(entries)
        _validate_lifecycle(result)
        return result

    def inspect(self) -> tuple[MvpDraftJournalEntry, ...]:
        """Read under a shared existing lock without creating or appending files."""

        if self._lock_depth != 0 or self._lock_descriptor is not None:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        lock_path = self._root / _LOCK_FILE
        names_before: list[str] | None = None
        try:
            lock_metadata = lock_path.lstat()
        except FileNotFoundError:
            try:
                names_before = os.listdir(self._records)
                lock_path.lstat()
            except FileNotFoundError:
                try:
                    names_after = os.listdir(self._records)
                except OSError:
                    _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
                if (
                    names_before is not None
                    and names_before == []
                    and names_after == []
                ):
                    return ()
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
            except OSError:
                _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
            return self.inspect()
        except OSError:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        if (
            stat.S_ISLNK(lock_metadata.st_mode)
            or not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(lock_metadata.st_mode) != 0o600
        ):
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        descriptor = _open_private(lock_path, os.O_RDONLY)
        self._lock_descriptor = descriptor
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
            self._lock_depth = 1
            return self.entries()
        except WordPressComMvpDraftFailure:
            raise
        except BaseException:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        finally:
            self._lock_depth = 0
            self._lock_descriptor = None
            _release_lock(descriptor)

    def append(
        self,
        *,
        operation_id: str,
        operation_binding_sha256: str,
        state: MvpDraftOperationState,
        reason_code: str,
        object_id: str | None,
    ) -> MvpDraftJournalEntry:
        self._require_locked()
        entries = self.entries()
        sequence = len(entries) + 1
        if sequence > _MAX_RECORDS:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
        previous = entries[-1].record_sha256 if entries else _ZERO_SHA256
        mapping: dict[str, object] = {
            "object_id": object_id,
            "operation_binding_sha256": operation_binding_sha256,
            "operation_id": operation_id,
            "previous_record_sha256": previous,
            "reason_code": reason_code,
            "schema": _SCHEMA,
            "sequence": sequence,
            "state": state.value if type(state) is MvpDraftOperationState else "",
        }
        mapping["record_sha256"] = _record_hash(mapping)
        candidate = _entry(mapping)
        _validate_lifecycle((*entries, candidate))
        data = _canonical(mapping)
        descriptor = _open_private(
            self._records / f"{sequence:08d}.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        )
        try:
            offset = 0
            while offset < len(data):
                written = os.write(descriptor, data[offset:])
                if written <= 0:
                    _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
                offset += written
            os.fsync(descriptor)
        except WordPressComMvpDraftFailure:
            raise
        except OSError:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        finally:
            os.close(descriptor)
        try:
            directory = os.open(
                self._records,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            _fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
        return candidate


__all__ = [
    "EmptyWordPressComMvpDraftJournalView",
    "ImmutableWordPressComMvpDraftJournal",
]
