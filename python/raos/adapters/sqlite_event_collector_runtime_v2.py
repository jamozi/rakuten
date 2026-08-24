"""Owner-private append-only SQLite event journal for ST-1201 V2."""

from __future__ import annotations

from enum import StrEnum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import Lock
from typing import Final, NoReturn, final

from raos.domain.analytics.event_collector import (
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventDigest,
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


_DATABASE_NAME: Final = "st1201-recorded-event-store.sqlite3"
_SCHEMA_VERSION: Final = "ST1201_DURABLE_RECORDED_EVENT_STORE_V2"
_GENESIS: Final = "0" * 64

_CREATE_METADATA = """CREATE TABLE st1201_metadata_v2 (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL CHECK (schema_version = 'ST1201_DURABLE_RECORDED_EVENT_STORE_V2'),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    event_head_sha256 TEXT NOT NULL CHECK (length(event_head_sha256) = 64),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64)
) STRICT"""
_CREATE_EVENT = """CREATE TABLE st1201_event_v2 (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    site_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    received_at TEXT NOT NULL,
    canonical_event BLOB NOT NULL,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64)
) STRICT"""
_CREATE_EVENT_NO_UPDATE = """CREATE TRIGGER st1201_event_no_update_v2
BEFORE UPDATE ON st1201_event_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_EVENT_IMMUTABLE'); END"""
_CREATE_EVENT_NO_DELETE = """CREATE TRIGGER st1201_event_no_delete_v2
BEFORE DELETE ON st1201_event_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_EVENT_APPEND_ONLY'); END"""
_CREATE_METADATA_NO_DELETE = """CREATE TRIGGER st1201_metadata_no_delete_v2
BEFORE DELETE ON st1201_metadata_v2
BEGIN SELECT RAISE(ABORT, 'ST1201_METADATA_REQUIRED'); END"""
_CREATE_METADATA_NO_INSERT = """CREATE TRIGGER st1201_metadata_no_insert_v2
BEFORE INSERT ON st1201_metadata_v2
WHEN EXISTS (SELECT 1 FROM st1201_metadata_v2)
BEGIN SELECT RAISE(ABORT, 'ST1201_METADATA_SINGLETON'); END"""

_SCHEMA_SQL: Final = {
    "st1201_metadata_v2": _CREATE_METADATA,
    "st1201_event_v2": _CREATE_EVENT,
    "st1201_event_no_update_v2": _CREATE_EVENT_NO_UPDATE,
    "st1201_event_no_delete_v2": _CREATE_EVENT_NO_DELETE,
    "st1201_metadata_no_delete_v2": _CREATE_METADATA_NO_DELETE,
    "st1201_metadata_no_insert_v2": _CREATE_METADATA_NO_INSERT,
}
_SCHEMA_OBJECTS: Final = {
    ("index", "sqlite_autoindex_st1201_event_v2_1"),
    ("index", "sqlite_autoindex_st1201_event_v2_2"),
    ("table", "st1201_event_v2"),
    ("table", "st1201_metadata_v2"),
    ("trigger", "st1201_event_no_delete_v2"),
    ("trigger", "st1201_event_no_update_v2"),
    ("trigger", "st1201_metadata_no_delete_v2"),
    ("trigger", "st1201_metadata_no_insert_v2"),
}


class EventStoreCommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _InjectedCommitFault(RuntimeError):
    pass


def _fail(code: DurableEventStoreFailureCode) -> NoReturn:
    fail_durable_event_store(code)


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


def _metadata_digest(count: int, head: str) -> str:
    payload = json.dumps(
        {
            "event_count": count,
            "event_head_sha256": head,
            "schema_version": _SCHEMA_VERSION,
            "singleton": 1,
        },
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _record_digest(
    *,
    sequence: int,
    event_id: str,
    payload_sha256: str,
    site_id: str,
    event_name: str,
    source: str,
    schema_version: str,
    received_at: str,
    previous_record_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "event_id": event_id,
            "event_name": event_name,
            "payload_sha256": payload_sha256,
            "previous_record_sha256": previous_record_sha256,
            "received_at": received_at,
            "schema_version": schema_version,
            "sequence": sequence,
            "site_id": site_id,
            "source": source,
        },
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


@final
class SqliteDurableRecordedEventStoreV2:
    """Append-only local journal; no query, export, delete, or lifecycle API."""

    __slots__ = ("_commit_fault", "_database_path", "_fault_lock", "_fault_used")

    def __init__(
        self,
        *,
        private_root: Path,
        commit_fault_once: EventStoreCommitFault = EventStoreCommitFault.NONE,
    ) -> None:
        if type(commit_fault_once) is not EventStoreCommitFault:
            _fail(DurableEventStoreFailureCode.INVALID_ARGUMENT)
        root = self._prepare_private_root(private_root)
        self._database_path = root / _DATABASE_NAME
        self._commit_fault = commit_fault_once
        self._fault_lock = Lock()
        self._fault_used = False
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @property
    def mode(self) -> str:
        return "DURABLE_RECORDED_LOCAL"

    @property
    def action_count(self) -> int:
        return 0

    @staticmethod
    def _prepare_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        root = Path(os.path.abspath(value))
        if root != value or not root.exists():
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        except DurableEventStoreFailure:
            raise
        except OSError:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        metadata = os.lstat(root)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        return root

    def _create_or_validate_database_file(self) -> None:
        root = self._database_path.parent
        self._prepare_private_root(root)
        root_fd = -1
        descriptor = -1
        try:
            root_fd = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
            except FileExistsError:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        except DurableEventStoreFailure:
            raise
        except OSError:
            _fail(DurableEventStoreFailureCode.PRIVATE_PATH_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_fd >= 0:
                os.close(root_fd)

    def _connect(self) -> sqlite3.Connection:
        self._create_or_validate_database_file()
        try:
            connection = sqlite3.connect(
                self._database_path,
                isolation_level=None,
                timeout=10.0,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            self._create_or_validate_database_file()
            return connection
        except sqlite3.Error:
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if not existing:
                connection.execute(_CREATE_METADATA)
                connection.execute(_CREATE_EVENT)
                connection.execute(
                    "INSERT INTO st1201_metadata_v2 VALUES (?,?,?,?,?)",
                    (1, _SCHEMA_VERSION, 0, _GENESIS, _metadata_digest(0, _GENESIS)),
                )
                connection.execute(_CREATE_EVENT_NO_UPDATE)
                connection.execute(_CREATE_EVENT_NO_DELETE)
                connection.execute(_CREATE_METADATA_NO_DELETE)
                connection.execute(_CREATE_METADATA_NO_INSERT)
                connection.execute("PRAGMA user_version=120102")
            self._validate_all(connection)
            connection.commit()
        except DurableEventStoreFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        finally:
            connection.close()

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()
        if version is None or tuple(version) != (120102,):
            _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
        rows = connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' OR type='index' ORDER BY type,name"
        ).fetchall()
        observed = {(str(row[0]), str(row[1])) for row in rows}
        if observed != _SCHEMA_OBJECTS:
            _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
        for row in rows:
            kind, name, sql = str(row[0]), str(row[1]), row[2]
            if kind == "index":
                if sql is not None:
                    _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
                continue
            expected = _SCHEMA_SQL.get(name)
            if expected is None or type(sql) is not str:
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)
            if _normalized_sql(sql) != _normalized_sql(expected):
                _fail(DurableEventStoreFailureCode.SCHEMA_DRIFT)

    @classmethod
    def _validate_all(cls, connection: sqlite3.Connection) -> None:
        cls._validate_schema(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or tuple(integrity) != ("ok",):
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        metadata_rows = connection.execute(
            "SELECT singleton,schema_version,event_count,event_head_sha256,record_sha256 "
            "FROM st1201_metadata_v2"
        ).fetchall()
        if len(metadata_rows) != 1:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        singleton, schema_version, count, head, metadata_sha = tuple(metadata_rows[0])
        if (
            singleton != 1
            or schema_version != _SCHEMA_VERSION
            or type(count) is not int
            or count < 0
            or type(head) is not str
            or type(metadata_sha) is not str
            or metadata_sha != _metadata_digest(count, head)
        ):
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            "SELECT sequence,event_id,payload_sha256,site_id,event_name,source,"
            "schema_version,received_at,canonical_event,previous_record_sha256,"
            "record_sha256 FROM st1201_event_v2 ORDER BY sequence"
        ).fetchall()
        if len(rows) != count:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
        previous = _GENESIS
        for expected_sequence, row in enumerate(rows, start=1):
            values = tuple(row)
            sequence = values[0]
            canonical_event = values[8]
            if (
                sequence != expected_sequence
                or type(canonical_event) is not bytes
                or not canonical_event
                or hashlib.sha256(canonical_event).hexdigest() != values[2]
                or values[9] != previous
                or _record_digest(
                    sequence=sequence,
                    event_id=values[1],
                    payload_sha256=values[2],
                    site_id=values[3],
                    event_name=values[4],
                    source=values[5],
                    schema_version=values[6],
                    received_at=values[7],
                    previous_record_sha256=values[9],
                )
                != values[10]
            ):
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            previous = values[10]
        if head != previous:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    def _take_fault(self) -> EventStoreCommitFault:
        with self._fault_lock:
            if self._fault_used:
                return EventStoreCommitFault.NONE
            self._fault_used = True
            return self._commit_fault

    @staticmethod
    def _event_values(
        event: ValidatedEvent, digest: EventDigest
    ) -> tuple[str, str, str, str, str, bytes]:
        if type(event) is not ValidatedEvent or type(digest) is not EventDigest:
            fail_event_collector(EventCollectorFailureCode.RECORDED_STORE_MISMATCH)
        recomputed = EventDigest.of(event)
        if recomputed != digest:
            fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
        envelope = event.envelope
        canonical = event.canonical_bytes()
        if hashlib.sha256(canonical).hexdigest() != digest.value:
            fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
        return (
            str(envelope.event_id),
            str(envelope.site_id),
            envelope.event_name.value,
            envelope.source.value,
            envelope.received_at.value.isoformat().replace("+00:00", "Z"),
            canonical,
        )

    @staticmethod
    def _receipt(
        row: sqlite3.Row, *, digest: EventDigest, replayed: bool
    ) -> DurableEventReceiptV2:
        try:
            from uuid import UUID

            return DurableEventReceiptV2(
                event_id=UUID(str(row["event_id"])),
                digest=EventDigest(digest.value),
                disposition=(
                    RecordedStoreDisposition.RECORDED_DUPLICATE
                    if replayed
                    else RecordedStoreDisposition.RECORDED_ACCEPTED
                ),
                sequence=int(row["sequence"]),
                previous_record_sha256=str(row["previous_record_sha256"]),
                record_sha256=str(row["record_sha256"]),
                replayed=replayed,
            )
        except Exception:
            _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)

    def exchange_durable(
        self, event: ValidatedEvent, digest: EventDigest
    ) -> DurableEventReceiptV2:
        event_id, site_id, event_name, source, received_at, canonical = (
            self._event_values(event, digest)
        )
        connection = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection)
            existing = connection.execute(
                "SELECT sequence,event_id,payload_sha256,site_id,event_name,source,"
                "schema_version,received_at,canonical_event,previous_record_sha256,"
                "record_sha256 FROM st1201_event_v2 WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["payload_sha256"] != digest.value
                    or existing["site_id"] != site_id
                    or existing["event_name"] != event_name
                    or existing["source"] != source
                    or existing["schema_version"] != "1.0"
                    or existing["received_at"] != received_at
                    or existing["canonical_event"] != canonical
                ):
                    connection.rollback()
                    fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
                receipt = self._receipt(existing, digest=digest, replayed=True)
                connection.commit()
                return receipt
            metadata = connection.execute(
                "SELECT event_count,event_head_sha256 FROM st1201_metadata_v2 "
                "WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                _fail(DurableEventStoreFailureCode.TAMPER_DETECTED)
            sequence = int(metadata["event_count"]) + 1
            previous = str(metadata["event_head_sha256"])
            record_sha = _record_digest(
                sequence=sequence,
                event_id=event_id,
                payload_sha256=digest.value,
                site_id=site_id,
                event_name=event_name,
                source=source,
                schema_version="1.0",
                received_at=received_at,
                previous_record_sha256=previous,
            )
            connection.execute(
                "INSERT INTO st1201_event_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    event_id,
                    digest.value,
                    site_id,
                    event_name,
                    source,
                    "1.0",
                    received_at,
                    canonical,
                    previous,
                    record_sha,
                ),
            )
            connection.execute(
                "UPDATE st1201_metadata_v2 SET event_count=?,event_head_sha256=?,"
                "record_sha256=? WHERE singleton=1",
                (sequence, record_sha, _metadata_digest(sequence, record_sha)),
            )
            self._validate_all(connection)
            fault = self._take_fault()
            if fault is EventStoreCommitFault.BEFORE_COMMIT:
                raise _InjectedCommitFault("BEFORE_COMMIT")
            connection.commit()
            committed = True
            if fault is EventStoreCommitFault.AFTER_COMMIT:
                raise _InjectedCommitFault("AFTER_COMMIT")
            row = connection.execute(
                "SELECT sequence,event_id,previous_record_sha256,record_sha256 "
                "FROM st1201_event_v2 WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                _fail(DurableEventStoreFailureCode.COMMIT_UNKNOWN)
            return self._receipt(row, digest=digest, replayed=False)
        except EventCollectorFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except _InjectedCommitFault:
            if not committed:
                connection.rollback()
                _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        except DurableEventStoreFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            _fail(DurableEventStoreFailureCode.STORAGE_FAILED)
        finally:
            connection.close()
        return self._recover_after_commit(event_id=event_id, digest=digest)

    def _recover_after_commit(
        self, *, event_id: str, digest: EventDigest
    ) -> DurableEventReceiptV2:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection)
            row = connection.execute(
                "SELECT sequence,event_id,payload_sha256,previous_record_sha256,"
                "record_sha256 FROM st1201_event_v2 WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                _fail(DurableEventStoreFailureCode.RECOVERY_NOT_FOUND)
            if row["payload_sha256"] != digest.value:
                fail_event_collector(EventCollectorFailureCode.EVENT_ID_CONFLICT)
            receipt = self._receipt(row, digest=digest, replayed=False)
            connection.commit()
            return receipt
        except EventCollectorFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except DurableEventStoreFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            _fail(DurableEventStoreFailureCode.COMMIT_UNKNOWN)
        finally:
            connection.close()


__all__ = [
    "EventStoreCommitFault",
    "SqliteDurableRecordedEventStoreV2",
]
