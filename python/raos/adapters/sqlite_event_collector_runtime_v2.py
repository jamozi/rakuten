"""Owner-private append-only SQLite event journal for ST-1201 V2.

The adapter is intentionally local and authority-free. A store instance pins
the database inode and strongest event-chain prefix it has observed. This
detects replacement and same-inode rollback while that instance remains alive;
a fresh process has no rollback claim without an external durable anchor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock
from typing import Any, Final, NoReturn, cast, final
from uuid import RFC_4122, UUID

from raos.domain.analytics.event_collector import (
    ConsentContext,
    ConsentState,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventDigest,
    EventEnvelope,
    EventName,
    EventParameter,
    EventSource,
    PrivacyMode,
    RecordedStoreDisposition,
    ValidatedEvent,
    fail_event_collector,
)
from raos.domain.analytics.event_collector_runtime_v2 import (
    DurableEventReceiptV2,
    DurableEventStoreFailure,
    DurableEventStoreFailureCode,
    fail_durable_event_store,
)
from raos.domain.portfolio.workflow import UtcTimestamp


_DATABASE_NAME: Final = "st1201-recorded-event-store.sqlite3"
_SCHEMA_VERSION: Final = "ST1201_DURABLE_RECORDED_EVENT_STORE_V2"
_USER_VERSION: Final = 120102
_APPLICATION_ID: Final = 0x52414F53
_GENESIS: Final = "0" * 64
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC_TEXT = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{6})?Z\Z",
    re.ASCII,
)
_MAX_CANONICAL_EVENT_BYTES: Final = 32_768
_MAX_JSON_DEPTH: Final = 8
_MAX_JSON_NODES: Final = 128

_CREATE_METADATA = """CREATE TABLE st1201_metadata_v2 (
    singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL CHECK (schema_version = 'ST1201_DURABLE_RECORDED_EVENT_STORE_V2'),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    event_head_sha256 TEXT NOT NULL CHECK (length(event_head_sha256) = 64 AND event_head_sha256 NOT GLOB '*[^0-9a-f]*'),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
) STRICT"""
_CREATE_EVENT = """CREATE TABLE st1201_event_v2 (
    sequence INTEGER NOT NULL PRIMARY KEY CHECK (sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
    command_sha256 TEXT NOT NULL CHECK (length(command_sha256) = 64 AND command_sha256 NOT GLOB '*[^0-9a-f]*'),
    recovery_sha256 TEXT NOT NULL CHECK (length(recovery_sha256) = 64 AND recovery_sha256 NOT GLOB '*[^0-9a-f]*'),
    site_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    received_at TEXT NOT NULL,
    canonical_event BLOB NOT NULL,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64 AND previous_record_sha256 NOT GLOB '*[^0-9a-f]*'),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
) STRICT"""
_CREATE_EVENT_APPEND_GUARD = """CREATE TRIGGER st1201_event_append_guard_v2
BEFORE INSERT ON st1201_event_v2
WHEN NEW.sequence != COALESCE((SELECT event_count + 1 FROM st1201_metadata_v2 WHERE singleton = 1), -1)
 OR NEW.previous_record_sha256 != COALESCE((SELECT event_head_sha256 FROM st1201_metadata_v2 WHERE singleton = 1), '')
BEGIN SELECT RAISE(ABORT, 'ST1201_EVENT_APPEND_INVALID'); END"""
_CREATE_EVENT_NO_UPDATE = """CREATE TRIGGER st1201_event_no_update_v2
BEFORE UPDATE ON st1201_event_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_EVENT_IMMUTABLE'); END"""
_CREATE_EVENT_NO_DELETE = """CREATE TRIGGER st1201_event_no_delete_v2
BEFORE DELETE ON st1201_event_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_EVENT_APPEND_ONLY'); END"""
_CREATE_METADATA_GUARD_UPDATE = """CREATE TRIGGER st1201_metadata_guard_update_v2
BEFORE UPDATE ON st1201_metadata_v2
WHEN NEW.singleton != OLD.singleton
 OR NEW.schema_version != OLD.schema_version
 OR NEW.event_count != OLD.event_count + 1
 OR NOT EXISTS (
    SELECT 1 FROM st1201_event_v2
    WHERE sequence = NEW.event_count
      AND previous_record_sha256 = OLD.event_head_sha256
      AND record_sha256 = NEW.event_head_sha256
 )
BEGIN SELECT RAISE(ABORT, 'ST1201_METADATA_TRANSITION_INVALID'); END"""
_CREATE_METADATA_NO_DELETE = """CREATE TRIGGER st1201_metadata_no_delete_v2
BEFORE DELETE ON st1201_metadata_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_METADATA_REQUIRED'); END"""
_CREATE_METADATA_NO_INSERT = """CREATE TRIGGER st1201_metadata_no_insert_v2
BEFORE INSERT ON st1201_metadata_v2
WHEN EXISTS (SELECT 1 FROM st1201_metadata_v2)
BEGIN SELECT RAISE(ABORT, 'ST1201_METADATA_SINGLETON'); END"""

_TABLE_SQL: Final = (
    ("st1201_metadata_v2", _CREATE_METADATA),
    ("st1201_event_v2", _CREATE_EVENT),
)
_TRIGGER_SQL: Final = (
    ("st1201_event_append_guard_v2", "st1201_event_v2", _CREATE_EVENT_APPEND_GUARD),
    ("st1201_event_no_update_v2", "st1201_event_v2", _CREATE_EVENT_NO_UPDATE),
    ("st1201_event_no_delete_v2", "st1201_event_v2", _CREATE_EVENT_NO_DELETE),
    (
        "st1201_metadata_guard_update_v2",
        "st1201_metadata_v2",
        _CREATE_METADATA_GUARD_UPDATE,
    ),
    ("st1201_metadata_no_delete_v2", "st1201_metadata_v2", _CREATE_METADATA_NO_DELETE),
    ("st1201_metadata_no_insert_v2", "st1201_metadata_v2", _CREATE_METADATA_NO_INSERT),
)
_AUTO_INDEXES: Final = frozenset(
    {
        ("index", "sqlite_autoindex_st1201_event_v2_1", "st1201_event_v2", None),
        ("index", "sqlite_autoindex_st1201_event_v2_2", "st1201_event_v2", None),
    }
)
_TABLE_COLUMNS: Final = {
    "st1201_metadata_v2": (
        ("singleton", "INTEGER", 1, 1, 0),
        ("schema_version", "TEXT", 1, 0, 0),
        ("event_count", "INTEGER", 1, 0, 0),
        ("event_head_sha256", "TEXT", 1, 0, 0),
        ("record_sha256", "TEXT", 1, 0, 0),
    ),
    "st1201_event_v2": (
        ("sequence", "INTEGER", 1, 1, 0),
        ("event_id", "TEXT", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("command_sha256", "TEXT", 1, 0, 0),
        ("recovery_sha256", "TEXT", 1, 0, 0),
        ("site_id", "TEXT", 1, 0, 0),
        ("event_name", "TEXT", 1, 0, 0),
        ("source", "TEXT", 1, 0, 0),
        ("schema_version", "TEXT", 1, 0, 0),
        ("received_at", "TEXT", 1, 0, 0),
        ("canonical_event", "BLOB", 1, 0, 0),
        ("previous_record_sha256", "TEXT", 1, 0, 0),
        ("record_sha256", "TEXT", 1, 0, 0),
    ),
}
_SCHEMA_INITIALIZATION_LOCK = RLock()


class EventStoreCommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class EventStoreCommitClassificationV2(StrEnum):
    COMMITTED = "COMMITTED"
    NOT_COMMITTED = "NOT_COMMITTED"
    AMBIGUOUS = "AMBIGUOUS"


class _InjectedCommitFault(sqlite3.OperationalError):
    __slots__ = ()


def _fail(code: DurableEventStoreFailureCode) -> NoReturn:
    fail_durable_event_store(code)


def _sha256(value: object) -> str:
    if type(value) is not str or _LOWER_SHA256.fullmatch(value) is None:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    return value


def _canonical_hash(value: dict[str, object]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _metadata_digest(count: int, head: str) -> str:
    return _canonical_hash(
        {
            "event_count": count,
            "event_head_sha256": head,
            "schema_version": _SCHEMA_VERSION,
            "singleton": 1,
        }
    )


def _command_digest(*, event_id: str, payload_sha256: str) -> str:
    return _canonical_hash(
        {
            "event_id": event_id,
            "operation": "ST1201_RECORD_CANONICAL_EVENT_V2",
            "payload_sha256": payload_sha256,
        }
    )


def _record_digest(
    *,
    sequence: int,
    event_id: str,
    payload_sha256: str,
    command_sha256: str,
    site_id: str,
    event_name: str,
    source: str,
    schema_version: str,
    received_at: str,
    previous_record_sha256: str,
) -> str:
    return _canonical_hash(
        {
            "command_sha256": command_sha256,
            "event_id": event_id,
            "event_name": event_name,
            "payload_sha256": payload_sha256,
            "previous_record_sha256": previous_record_sha256,
            "received_at": received_at,
            "schema_version": schema_version,
            "sequence": sequence,
            "site_id": site_id,
            "source": source,
        }
    )


def _recovery_digest(
    *,
    event_id: str,
    payload_sha256: str,
    command_sha256: str,
    sequence: int,
    previous_record_sha256: str,
    record_sha256: str,
) -> str:
    return _canonical_hash(
        {
            "command_sha256": command_sha256,
            "event_id": event_id,
            "payload_sha256": payload_sha256,
            "previous_record_sha256": previous_record_sha256,
            "record_sha256": record_sha256,
            "recovery": "ST1201_EXACT_COMMIT_RECOVERY_V2",
            "sequence": sequence,
        }
    )


def _reject_constant(_value: str) -> NoReturn:
    _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if depth > _MAX_JSON_DEPTH or nodes > _MAX_JSON_NODES:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        if type(current) is dict:
            stack.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in cast(list[object], current))
        elif type(current) is float:
            if not math.isfinite(current):
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        elif current is not None and type(current) not in {str, int, bool}:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)


def _canonical_uuid7_text(value: object) -> UUID:
    if type(value) is not str:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    try:
        parsed = UUID(value)
    except ValueError:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    if (
        parsed.version != 7
        or parsed.variant != RFC_4122
        or str(parsed) != value
        or value != value.lower()
    ):
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    return parsed


def _utc_timestamp(value: object) -> UtcTimestamp:
    if type(value) is not str or _UTC_TEXT.fullmatch(value) is None:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        timestamp = UtcTimestamp(parsed.astimezone(timezone.utc))
    except Exception:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    if timestamp.value.isoformat().replace("+00:00", "Z") != value:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    return timestamp


def _decode_canonical_event(payload: object) -> ValidatedEvent:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _MAX_CANONICAL_EVENT_BYTES
    ):
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except DurableEventStoreFailure:
        raise
    except Exception:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    _validate_json_tree(decoded)
    if type(decoded) is not dict:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    mapping = cast(dict[str, object], decoded)
    if set(mapping) != {
        "correlation_id",
        "event_id",
        "event_name",
        "occurred_at",
        "parameters",
        "received_at",
        "schema_version",
        "site_id",
        "source",
    }:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    canonical = json.dumps(
        mapping,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != payload:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    parameters_value = mapping["parameters"]
    if type(parameters_value) is not list:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    parameters: list[EventParameter] = []
    try:
        for item in cast(list[object], parameters_value):
            if type(item) is not dict:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            parameter = cast(dict[str, object], item)
            if (
                set(parameter) != {"name", "value"}
                or type(parameter["name"]) is not str
            ):
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            parameters.append(
                EventParameter(
                    parameter["name"],
                    cast(str | int | float | bool, parameter["value"]),
                )
            )
        event = EventEnvelope(
            event_id=_canonical_uuid7_text(mapping["event_id"]),
            event_name=EventName(cast(str, mapping["event_name"])),
            schema_version=cast(str, mapping["schema_version"]),
            occurred_at=_utc_timestamp(mapping["occurred_at"]),
            received_at=_utc_timestamp(mapping["received_at"]),
            source=EventSource(cast(str, mapping["source"])),
            site_id=_canonical_uuid7_text(mapping["site_id"]),
            correlation_id=_canonical_uuid7_text(mapping["correlation_id"]),
            parameters=tuple(parameters),
        )
        if event.source is not EventSource.PUBLIC_WEB or not event.definition.mvp:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        event_level_consent = tuple(
            item.value for item in event.parameters if item.name == "consent_state"
        )
        if event_level_consent and event_level_consent != (ConsentState.GRANTED.value,):
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        validated = ValidatedEvent(
            envelope=event,
            consent=ConsentContext(
                consent_state=ConsentState.GRANTED,
                privacy_mode=PrivacyMode.FULL_CONSENT,
            ),
        )
    except DurableEventStoreFailure:
        raise
    except Exception:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    if validated.canonical_bytes() != payload:
        _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
    return validated


@dataclass(frozen=True, slots=True)
class _EventMaterial:
    event_id: str
    site_id: str
    event_name: str
    source: str
    received_at: str
    canonical: bytes
    payload_sha256: str
    command_sha256: str


@dataclass(frozen=True, slots=True)
class _CommitRecovery:
    classification: EventStoreCommitClassificationV2
    receipt: DurableEventReceiptV2 | None
    count: int | None
    head: str | None


@final
class SqliteDurableRecordedEventStoreV2:
    """Append-only local journal; no query, export, delete, or lifecycle API."""

    __slots__ = (
        "_commit_fault",
        "_database_identity",
        "_database_path",
        "_fault_lock",
        "_fault_used",
        "_root",
        "_root_identity",
        "_seen_count",
        "_seen_head",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        private_root: Path,
        commit_fault_once: EventStoreCommitFault = EventStoreCommitFault.NONE,
    ) -> None:
        if type(commit_fault_once) is not EventStoreCommitFault:
            _fail(DurableEventStoreFailureCode.INVALID_ARGUMENT)
        root, root_identity = self._prepare_private_root(private_root)
        self._root = root
        self._root_identity = root_identity
        self._database_path = root / _DATABASE_NAME
        self._database_identity: tuple[int, int] | None = None
        self._commit_fault = commit_fault_once
        self._fault_lock = RLock()
        self._fault_used = False
        self._state_lock = RLock()
        self._seen_count = 0
        self._seen_head = _GENESIS
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(
                allow_create=True,
                allow_empty=True,
            )
            self._database_identity = identity
            connection = self._connect(verify=False, allow_empty=created)
            try:
                if created:
                    self._initialize_new(connection)
                else:
                    self._verify_schema(connection)
                    self._verify_integrity(connection)
                    self._validate_database_identity()
            finally:
                self._close_safely(connection)
            connection = self._connect(verify=False)
            try:
                count, head = self._verified_state(connection)
                self._pin_state(count=count, head=head)
            finally:
                self._close_safely(connection)

    @property
    def mode(self) -> str:
        return "DURABLE_RECORDED_LOCAL"

    @property
    def action_count(self) -> int:
        return 0

    @property
    def database_path(self) -> Path:
        return self._database_path

    @staticmethod
    def _prepare_private_root(value: object) -> tuple[Path, tuple[int, int]]:
        if (
            not isinstance(value, Path)
            or not value.is_absolute()
            or ".." in value.parts
        ):
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        root = Path(os.path.abspath(value))
        if root != value:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
            metadata = os.lstat(root)
        except DurableEventStoreFailure:
            raise
        except OSError:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        if (
            metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_nlink < 1
        ):
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        return root, (metadata.st_dev, metadata.st_ino)

    def _validate_private_root(self) -> None:
        root, identity = self._prepare_private_root(self._root)
        if root != self._root or identity != self._root_identity:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)

    def _open_database_file(
        self,
        *,
        allow_create: bool,
        allow_empty: bool = False,
    ) -> tuple[bool, tuple[int, int]]:
        self._validate_private_root()
        root_descriptor = -1
        descriptor = -1
        created = False
        try:
            root_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_metadata = os.fstat(root_descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
                _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
            if allow_create:
                try:
                    descriptor = os.open(
                        _DATABASE_NAME,
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | os.O_CLOEXEC
                        | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=root_descriptor,
                    )
                    created = True
                except FileExistsError:
                    descriptor = os.open(
                        _DATABASE_NAME,
                        os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=root_descriptor,
                    )
            else:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=root_descriptor,
                )
            metadata = os.fstat(descriptor)
            named = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            identity = (metadata.st_dev, metadata.st_ino)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (named.st_dev, named.st_ino) != identity
                or (
                    self._database_identity is not None
                    and identity != self._database_identity
                )
            ):
                _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
            if not created:
                if metadata.st_size < 100:
                    if not (allow_empty and metadata.st_size == 0):
                        _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
                elif os.pread(descriptor, 16, 0) != b"SQLite format 3\x00":
                    _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            if created:
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            return created, identity
        except DurableEventStoreFailure:
            raise
        except OSError:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self, *, allow_empty: bool = False) -> None:
        _created, identity = self._open_database_file(
            allow_create=False,
            allow_empty=allow_empty,
        )
        if self._database_identity is None or identity != self._database_identity:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)

    def _fsync_database_and_root(self) -> None:
        root_descriptor = -1
        descriptor = -1
        try:
            root_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=root_descriptor,
            )
            metadata = os.fstat(descriptor)
            if self._database_identity != (metadata.st_dev, metadata.st_ino):
                _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
            os.fsync(descriptor)
            os.fsync(root_descriptor)
        except DurableEventStoreFailure:
            raise
        except OSError:
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _connect(
        self,
        *,
        verify: bool = True,
        allow_empty: bool = False,
    ) -> sqlite3.Connection:
        self._validate_database_identity(allow_empty=allow_empty)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self._database_path.as_uri()}?mode=rw",
                uri=True,
                isolation_level=None,
                timeout=10.0,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            journal = connection.execute("PRAGMA journal_mode").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            trusted_schema = connection.execute("PRAGMA trusted_schema").fetchone()
            temp_store = connection.execute("PRAGMA temp_store").fetchone()
            synchronous = connection.execute("PRAGMA synchronous").fetchone()
            secure_delete = connection.execute("PRAGMA secure_delete").fetchone()
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
            if (
                journal is None
                or tuple(journal) != ("delete",)
                or foreign_keys is None
                or tuple(foreign_keys) != (1,)
                or trusted_schema is None
                or tuple(trusted_schema) != (0,)
                or temp_store is None
                or tuple(temp_store) != (2,)
                or synchronous is None
                or tuple(synchronous) != (2,)
                or secure_delete is None
                or tuple(secure_delete) != (1,)
                or busy_timeout is None
                or tuple(busy_timeout) != (10000,)
            ):
                _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
            self._validate_database_identity(allow_empty=allow_empty)
            if verify:
                self._verify_schema(connection)
                count, head = self._verify_integrity(connection)
                self._require_monotonic_state(connection, count=count, head=head)
                self._validate_database_identity()
                # A successfully verified connection observes committed state,
                # so retain the strongest process-local rollback anchor before
                # any later transaction or collaborator behavior can fail.
                self._pin_state(count=count, head=head)
            return connection
        except DurableEventStoreFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._close_safely(connection)
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            application_id = connection.execute("PRAGMA application_id").fetchone()
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if (
                version is None
                or tuple(version) != (0,)
                or application_id is None
                or tuple(application_id) != (0,)
                or existing is None
                or tuple(existing) != (0,)
            ):
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_database_identity(allow_empty=True)
            for _name, statement in _TABLE_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO st1201_metadata_v2(singleton,schema_version,event_count,event_head_sha256,record_sha256) VALUES (?,?,?,?,?)",
                (1, _SCHEMA_VERSION, 0, _GENESIS, _metadata_digest(0, _GENESIS)),
            )
            for _name, _table, statement in _TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {_USER_VERSION}")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            # SQLite can retain the newly created file at zero bytes until
            # this initial transaction commits. Identity, owner, mode, and
            # link count are still checked; the header is required after it.
            self._validate_database_identity(allow_empty=True)
            connection.execute("COMMIT")
            self._validate_database_identity()
            self._fsync_database_and_root()
        except DurableEventStoreFailure:
            self._rollback_quietly(connection, allow_empty=True)
            raise
        except sqlite3.Error:
            self._rollback_quietly(connection, allow_empty=True)
            _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
        self._verify_schema(connection)
        count, head = self._verify_integrity(connection)
        if count != 0 or head != _GENESIS:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _rollback_quietly(
        self,
        connection: sqlite3.Connection,
        *,
        allow_empty: bool = False,
    ) -> None:
        try:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        self._validate_database_identity(allow_empty=allow_empty)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        expected_objects = {
            *(("table", name, name, sql) for name, sql in _TABLE_SQL),
            *(("trigger", name, table, sql) for name, table, sql in _TRIGGER_SQL),
            *_AUTO_INDEXES,
        }
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            application_id = connection.execute("PRAGMA application_id").fetchone()
            observed_objects = {
                (row[0], row[1], row[2], row[3])
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master"
                ).fetchall()
            }
            if (
                version is None
                or tuple(version) != (_USER_VERSION,)
                or application_id is None
                or tuple(application_id) != (_APPLICATION_ID,)
                or observed_objects != expected_objects
            ):
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            for table, expected in _TABLE_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_xinfo({table})").fetchall()
                observed = tuple(
                    (row[1], row[2], row[3], row[5], row[6]) for row in rows
                )
                if observed != expected:
                    _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
                if connection.execute(f"PRAGMA foreign_key_list({table})").fetchall():
                    _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            strict = {
                row[1]: row[5]
                for row in connection.execute("PRAGMA table_list").fetchall()
                if row[1] in _TABLE_COLUMNS
            }
            if strict != {name: 1 for name in _TABLE_COLUMNS}:
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            observed_indexes: set[tuple[str, int, str, int, tuple[str, ...]]] = set()
            for row in connection.execute(
                "PRAGMA index_list(st1201_event_v2)"
            ).fetchall():
                columns = tuple(
                    cast(str, item[2])
                    for item in connection.execute(
                        f"PRAGMA index_info('{row[1]}')"
                    ).fetchall()
                )
                observed_indexes.add(
                    (
                        cast(str, row[1]),
                        cast(int, row[2]),
                        cast(str, row[3]),
                        cast(int, row[4]),
                        columns,
                    )
                )
            if observed_indexes != {
                ("sqlite_autoindex_st1201_event_v2_1", 1, "u", 0, ("event_id",)),
                (
                    "sqlite_autoindex_st1201_event_v2_2",
                    1,
                    "u",
                    0,
                    ("record_sha256",),
                ),
            }:
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            quick = connection.execute("PRAGMA quick_check").fetchall()
            if tuple(tuple(row) for row in quick) != (("ok",),):
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
        except DurableEventStoreFailure:
            raise
        except sqlite3.Error:
            _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)

    @staticmethod
    def _event_row_values(row: sqlite3.Row) -> tuple[object, ...]:
        expected_keys = (
            "sequence",
            "event_id",
            "payload_sha256",
            "command_sha256",
            "recovery_sha256",
            "site_id",
            "event_name",
            "source",
            "schema_version",
            "received_at",
            "canonical_event",
            "previous_record_sha256",
            "record_sha256",
        )
        if tuple(row.keys()) != expected_keys:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        return tuple(row)

    @classmethod
    def _verify_integrity(cls, connection: sqlite3.Connection) -> tuple[int, str]:
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchall()
            if tuple(tuple(row) for row in integrity) != (("ok",),):
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            metadata_rows = connection.execute(
                "SELECT singleton,schema_version,event_count,event_head_sha256,record_sha256 FROM st1201_metadata_v2"
            ).fetchall()
            if len(metadata_rows) != 1:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            singleton, schema_version, count, head, metadata_sha = tuple(
                metadata_rows[0]
            )
            if (
                singleton != 1
                or schema_version != _SCHEMA_VERSION
                or type(count) is not int
                or count < 0
                or type(head) is not str
                or type(metadata_sha) is not str
                or _sha256(head) != head
                or _sha256(metadata_sha) != metadata_sha
                or metadata_sha != _metadata_digest(count, head)
            ):
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            rows = connection.execute(
                "SELECT sequence,event_id,payload_sha256,command_sha256,recovery_sha256,site_id,event_name,source,schema_version,received_at,canonical_event,previous_record_sha256,record_sha256 FROM st1201_event_v2 ORDER BY sequence"
            ).fetchall()
            if len(rows) != count:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            previous = _GENESIS
            for expected_sequence, row in enumerate(rows, start=1):
                values = cls._event_row_values(row)
                (
                    sequence,
                    event_id,
                    payload_sha,
                    command_sha,
                    recovery_sha,
                    site_id,
                    event_name,
                    source,
                    event_schema_version,
                    received_at,
                    canonical_event,
                    previous_sha,
                    record_sha,
                ) = values
                if (
                    type(sequence) is not int
                    or sequence != expected_sequence
                    or type(canonical_event) is not bytes
                    or any(
                        type(item) is not str
                        for item in (
                            event_id,
                            payload_sha,
                            command_sha,
                            recovery_sha,
                            site_id,
                            event_name,
                            source,
                            event_schema_version,
                            received_at,
                            previous_sha,
                            record_sha,
                        )
                    )
                ):
                    _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
                event = _decode_canonical_event(canonical_event)
                envelope = event.envelope
                computed_payload = hashlib.sha256(canonical_event).hexdigest()
                computed_command = _command_digest(
                    event_id=cast(str, event_id),
                    payload_sha256=computed_payload,
                )
                computed_record = _record_digest(
                    sequence=sequence,
                    event_id=cast(str, event_id),
                    payload_sha256=computed_payload,
                    command_sha256=computed_command,
                    site_id=cast(str, site_id),
                    event_name=cast(str, event_name),
                    source=cast(str, source),
                    schema_version=cast(str, event_schema_version),
                    received_at=cast(str, received_at),
                    previous_record_sha256=cast(str, previous_sha),
                )
                computed_recovery = _recovery_digest(
                    event_id=cast(str, event_id),
                    payload_sha256=computed_payload,
                    command_sha256=computed_command,
                    sequence=sequence,
                    previous_record_sha256=cast(str, previous_sha),
                    record_sha256=computed_record,
                )
                if (
                    _canonical_uuid7_text(event_id) != envelope.event_id
                    or _canonical_uuid7_text(site_id) != envelope.site_id
                    or event_name != envelope.event_name.value
                    or source != envelope.source.value
                    or event_schema_version != envelope.schema_version
                    or received_at
                    != envelope.received_at.value.isoformat().replace("+00:00", "Z")
                    or payload_sha != computed_payload
                    or command_sha != computed_command
                    or previous_sha != previous
                    or record_sha != computed_record
                    or recovery_sha != computed_recovery
                ):
                    _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
                previous = record_sha
            if head != previous:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            return count, head
        except DurableEventStoreFailure:
            raise
        except sqlite3.Error:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    def _require_monotonic_state(
        self,
        connection: sqlite3.Connection,
        *,
        count: int,
        head: str,
    ) -> None:
        if count < self._seen_count:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        if self._seen_count == 0:
            if self._seen_head != _GENESIS:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        else:
            pinned = connection.execute(
                "SELECT record_sha256 FROM st1201_event_v2 WHERE sequence = ?",
                (self._seen_count,),
            ).fetchone()
            if pinned is None or pinned[0] != self._seen_head:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        if count == self._seen_count and head != self._seen_head:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    def _pin_state(self, *, count: int, head: str) -> None:
        if count < self._seen_count or (
            count == self._seen_count and head != self._seen_head
        ):
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        self._seen_count = count
        self._seen_head = head

    def _verified_state(self, connection: sqlite3.Connection) -> tuple[int, str]:
        self._validate_database_identity()
        self._verify_schema(connection)
        count, head = self._verify_integrity(connection)
        self._require_monotonic_state(connection, count=count, head=head)
        self._validate_database_identity()
        return count, head

    def _take_fault(self) -> EventStoreCommitFault:
        with self._fault_lock:
            if self._fault_used:
                return EventStoreCommitFault.NONE
            self._fault_used = True
            return self._commit_fault

    @staticmethod
    def _event_material(event: ValidatedEvent, digest: EventDigest) -> _EventMaterial:
        if type(event) is not ValidatedEvent or type(digest) is not EventDigest:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        try:
            canonical = event.canonical_bytes()
            decoded = _decode_canonical_event(canonical)
            recomputed = EventDigest.of(decoded)
        except EventCollectorFailure:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        if (
            event.consent.consent_state is not ConsentState.GRANTED
            or event.consent.privacy_mode is not PrivacyMode.FULL_CONSENT
            or recomputed != digest
            or hashlib.sha256(canonical).hexdigest() != digest.value
        ):
            fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
        envelope = decoded.envelope
        event_id = str(envelope.event_id)
        return _EventMaterial(
            event_id=event_id,
            site_id=str(envelope.site_id),
            event_name=envelope.event_name.value,
            source=envelope.source.value,
            received_at=envelope.received_at.value.isoformat().replace("+00:00", "Z"),
            canonical=canonical,
            payload_sha256=digest.value,
            command_sha256=_command_digest(
                event_id=event_id,
                payload_sha256=digest.value,
            ),
        )

    @staticmethod
    def _row_matches_material(row: sqlite3.Row, material: _EventMaterial) -> bool:
        return bool(
            row["event_id"] == material.event_id
            and row["payload_sha256"] == material.payload_sha256
            and row["command_sha256"] == material.command_sha256
            and row["site_id"] == material.site_id
            and row["event_name"] == material.event_name
            and row["source"] == material.source
            and row["schema_version"] == "1.0"
            and row["received_at"] == material.received_at
            and row["canonical_event"] == material.canonical
            and row["recovery_sha256"]
            == _recovery_digest(
                event_id=material.event_id,
                payload_sha256=material.payload_sha256,
                command_sha256=material.command_sha256,
                sequence=row["sequence"],
                previous_record_sha256=row["previous_record_sha256"],
                record_sha256=row["record_sha256"],
            )
        )

    @staticmethod
    def _receipt(
        row: sqlite3.Row,
        *,
        digest: EventDigest,
        replayed: bool,
    ) -> DurableEventReceiptV2:
        try:
            return DurableEventReceiptV2(
                event_id=_canonical_uuid7_text(row["event_id"]),
                digest=EventDigest(digest.value),
                disposition=(
                    RecordedStoreDisposition.RECORDED_DUPLICATE
                    if replayed
                    else RecordedStoreDisposition.RECORDED_ACCEPTED
                ),
                sequence=row["sequence"],
                previous_record_sha256=row["previous_record_sha256"],
                record_sha256=row["record_sha256"],
                replayed=replayed,
            )
        except DurableEventStoreFailure:
            raise
        except Exception:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    def exchange_durable(
        self,
        event: ValidatedEvent,
        digest: EventDigest,
    ) -> DurableEventReceiptV2:
        material = self._event_material(event, digest)
        with self._state_lock:
            return self._exchange_locked(material=material, digest=digest)

    def _exchange_locked(
        self,
        *,
        material: _EventMaterial,
        digest: EventDigest,
    ) -> DurableEventReceiptV2:
        connection = self._connect()
        starting_count = -1
        starting_head = ""
        commit_attempted = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_database_identity()
            starting_count, starting_head = self._verified_state(connection)
            existing = connection.execute(
                "SELECT sequence,event_id,payload_sha256,command_sha256,recovery_sha256,site_id,event_name,source,schema_version,received_at,canonical_event,previous_record_sha256,record_sha256 FROM st1201_event_v2 WHERE event_id = ?",
                (material.event_id,),
            ).fetchone()
            if existing is not None:
                if not self._row_matches_material(existing, material):
                    self._rollback_quietly(connection)
                    count, head = self._verified_state(connection)
                    self._pin_state(count=count, head=head)
                    fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
                receipt = self._receipt(existing, digest=digest, replayed=True)
                self._rollback_quietly(connection)
                count, head = self._verified_state(connection)
                self._pin_state(count=count, head=head)
                return receipt
            sequence = starting_count + 1
            record_sha = _record_digest(
                sequence=sequence,
                event_id=material.event_id,
                payload_sha256=material.payload_sha256,
                command_sha256=material.command_sha256,
                site_id=material.site_id,
                event_name=material.event_name,
                source=material.source,
                schema_version="1.0",
                received_at=material.received_at,
                previous_record_sha256=starting_head,
            )
            recovery_sha = _recovery_digest(
                event_id=material.event_id,
                payload_sha256=material.payload_sha256,
                command_sha256=material.command_sha256,
                sequence=sequence,
                previous_record_sha256=starting_head,
                record_sha256=record_sha,
            )
            connection.execute(
                "INSERT INTO st1201_event_v2(sequence,event_id,payload_sha256,command_sha256,recovery_sha256,site_id,event_name,source,schema_version,received_at,canonical_event,previous_record_sha256,record_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    material.event_id,
                    material.payload_sha256,
                    material.command_sha256,
                    recovery_sha,
                    material.site_id,
                    material.event_name,
                    material.source,
                    "1.0",
                    material.received_at,
                    material.canonical,
                    starting_head,
                    record_sha,
                ),
            )
            updated = connection.execute(
                "UPDATE st1201_metadata_v2 SET event_count = ?, event_head_sha256 = ?, record_sha256 = ? WHERE singleton = 1 AND event_count = ? AND event_head_sha256 = ? AND record_sha256 = ?",
                (
                    sequence,
                    record_sha,
                    _metadata_digest(sequence, record_sha),
                    starting_count,
                    starting_head,
                    _metadata_digest(starting_count, starting_head),
                ),
            )
            if updated.rowcount != 1:
                self._rollback_quietly(connection)
                _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
            appended_count, appended_head = self._verified_state(connection)
            if appended_count != sequence or appended_head != record_sha:
                self._rollback_quietly(connection)
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            self._validate_database_identity()
            fault = self._take_fault()
            commit_attempted = True
            if fault is EventStoreCommitFault.BEFORE_COMMIT:
                raise _InjectedCommitFault("ST1201_INJECTED_COMMIT_FAILURE")
            connection.execute("COMMIT")
            if fault is EventStoreCommitFault.AFTER_COMMIT:
                raise _InjectedCommitFault("ST1201_INJECTED_COMMIT_FAILURE")
            self._validate_database_identity()
        except EventCollectorFailure:
            if not commit_attempted:
                self._rollback_quietly(connection)
            raise
        except DurableEventStoreFailure:
            if not commit_attempted:
                self._rollback_quietly(connection)
            raise
        except sqlite3.Error:
            if not commit_attempted:
                self._rollback_quietly(connection)
                _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        finally:
            if commit_attempted and connection.in_transaction:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            self._close_safely(connection)
        if not commit_attempted:
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        recovery = self._classify_commit(
            material=material,
            digest=digest,
            starting_count=starting_count,
            starting_head=starting_head,
        )
        if (
            recovery.classification is EventStoreCommitClassificationV2.COMMITTED
            and recovery.receipt is not None
            and recovery.count is not None
            and recovery.head is not None
        ):
            self._pin_state(count=recovery.count, head=recovery.head)
            return recovery.receipt
        if recovery.classification is EventStoreCommitClassificationV2.NOT_COMMITTED:
            _fail(DurableEventStoreFailureCode.COMMIT_NOT_COMMITTED)
        _fail(DurableEventStoreFailureCode.COMMIT_AMBIGUOUS)

    def _classify_commit(
        self,
        *,
        material: _EventMaterial,
        digest: EventDigest,
        starting_count: int,
        starting_head: str,
    ) -> _CommitRecovery:
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN")
            count, head = self._verified_state(connection)
            if starting_count > count:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            if starting_count:
                prefix = connection.execute(
                    "SELECT record_sha256 FROM st1201_event_v2 WHERE sequence = ?",
                    (starting_count,),
                ).fetchone()
                if prefix is None or prefix[0] != starting_head:
                    _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            elif starting_head != _GENESIS:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            row = connection.execute(
                "SELECT sequence,event_id,payload_sha256,command_sha256,recovery_sha256,site_id,event_name,source,schema_version,received_at,canonical_event,previous_record_sha256,record_sha256 FROM st1201_event_v2 WHERE event_id = ?",
                (material.event_id,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                self._validate_database_identity()
                return _CommitRecovery(
                    classification=EventStoreCommitClassificationV2.NOT_COMMITTED,
                    receipt=None,
                    count=count,
                    head=head,
                )
            if (
                row["sequence"] != starting_count + 1
                or row["previous_record_sha256"] != starting_head
                or not self._row_matches_material(row, material)
            ):
                connection.execute("ROLLBACK")
                return _CommitRecovery(
                    classification=EventStoreCommitClassificationV2.AMBIGUOUS,
                    receipt=None,
                    count=None,
                    head=None,
                )
            receipt = self._receipt(row, digest=digest, replayed=False)
            connection.execute("ROLLBACK")
            self._validate_database_identity()
            return _CommitRecovery(
                classification=EventStoreCommitClassificationV2.COMMITTED,
                receipt=receipt,
                count=count,
                head=head,
            )
        except Exception:
            if connection is not None:
                try:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            return _CommitRecovery(
                classification=EventStoreCommitClassificationV2.AMBIGUOUS,
                receipt=None,
                count=None,
                head=None,
            )
        finally:
            if connection is not None:
                self._close_safely(connection)


__all__ = [
    "EventStoreCommitClassificationV2",
    "EventStoreCommitFault",
    "SqliteDurableRecordedEventStoreV2",
]
