"""Owner-private SQLite audit writer for the ST-0405 recorded local runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import Lock
from typing import NoReturn, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.audit_runtime_v2 import (
    AUDIT_RUNTIME_GENESIS_SHA256_V2,
    AUDIT_RUNTIME_SCHEMA_VERSION_V2,
    AuditAppendReceiptV2,
    AuditAuthorizationProofV2,
    AuditEventCandidateV2,
    AuditRuntimeFailureCodeV2,
    AuditRuntimeFailureV2,
    PersistedAuditEventV2,
    audit_entry_sha256_v2,
    canonical_sha256_v2,
    fail_audit_runtime_v2,
)


_DATABASE_NAME = "st0405-recorded-audit-runtime-v2.sqlite3"
_TABLES = frozenset({"audit_metadata_v2", "audit_atomic_marker_v2", "audit_event_v2"})
_METADATA_COLUMNS = (
    (0, "singleton", "INTEGER", 0, None, 1),
    (1, "schema_version", "TEXT", 1, None, 0),
    (2, "schema_sha256", "TEXT", 1, None, 0),
)
_MARKER_COLUMNS = (
    (0, "authorization_command_id_fingerprint", "TEXT", 0, None, 1),
    (1, "event_id", "TEXT", 1, None, 0),
    (2, "request_sha256", "TEXT", 1, None, 0),
    (3, "marker_sha256", "TEXT", 1, None, 0),
)
_EVENT_COLUMNS = (
    (0, "sequence", "INTEGER", 0, None, 1),
    (1, "event_id", "TEXT", 1, None, 0),
    (2, "authorization_command_id_fingerprint", "TEXT", 1, None, 0),
    (3, "authorization_request_digest", "TEXT", 1, None, 0),
    (4, "authorization_session_fingerprint", "TEXT", 1, None, 0),
    (5, "authorization_audit_digest", "TEXT", 1, None, 0),
    (6, "request_sha256", "TEXT", 1, None, 0),
    (7, "correlation_id", "TEXT", 1, None, 0),
    (8, "candidate_json", "TEXT", 1, None, 0),
    (9, "previous_entry_sha256", "TEXT", 1, None, 0),
    (10, "entry_sha256", "TEXT", 1, None, 0),
    (11, "atomic_marker_sha256", "TEXT", 1, None, 0),
    (12, "record_sha256", "TEXT", 1, None, 0),
)
_EXPECTED_COLUMNS = {
    "audit_metadata_v2": _METADATA_COLUMNS,
    "audit_atomic_marker_v2": _MARKER_COLUMNS,
    "audit_event_v2": _EVENT_COLUMNS,
}
_SCHEMA_SHA256 = canonical_sha256_v2(
    {
        "schema": AUDIT_RUNTIME_SCHEMA_VERSION_V2,
        "tables": {
            key: list(value) for key, value in sorted(_EXPECTED_COLUMNS.items())
        },
        "constraints": (
            "append-only-port",
            "atomic-marker-and-event",
            "command-idempotency",
            "event-unique",
            "hash-chain",
        ),
    }
)


class RecordedAuditFaultV2(str, Enum):
    AFTER_MARKER_BEFORE_EVENT = "AFTER_MARKER_BEFORE_EVENT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _KnownRollback(RuntimeError):
    __slots__ = ()


@dataclass(slots=True)
class _FaultController:
    fault: RecordedAuditFaultV2 | None
    lock: Lock

    def consume(self, point: RecordedAuditFaultV2) -> bool:
        with self.lock:
            if self.fault is point:
                self.fault = None
                return True
            return False


def _fail(code: AuditRuntimeFailureCodeV2) -> NoReturn:
    fail_audit_runtime_v2(code)


def _recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,  # type: ignore[attr-defined]
        RuntimeEnvironment.CI,  # type: ignore[attr-defined]
    }:
        _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
    return value


def _canonical_text(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except TypeError, ValueError, UnicodeError:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if not encoded or len(encoded.encode("ascii")) > 64 * 1024:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    return encoded


def _parse_candidate(value: object) -> AuditEventCandidateV2:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 64 * 1024:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError, UnicodeError:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if type(parsed) is not dict:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    row = cast(dict[object, object], parsed)
    if _canonical_text(row) != value:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    expected = frozenset(
        {
            "authorization_audit_digest",
            "authorization_command_id_fingerprint",
            "authorization_request_digest",
            "authorization_session_fingerprint",
            "request_sha256",
            "event_id",
            "occurred_at",
            "actor_type",
            "actor_id",
            "action",
            "target_type",
            "target_id",
            "outcome",
            "severity",
            "correlation_id",
            "request_id",
            "reason_code",
            "before_hash",
            "after_hash",
            "event_digest",
        }
    )
    if frozenset(row) != expected:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def text(name: str) -> str:
        item = row[name]
        if type(item) is not str:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        return item

    def optional_text(name: str) -> str | None:
        item = row[name]
        if item is None:
            return None
        if type(item) is not str:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        return item

    def uuid(name: str) -> UUID:
        try:
            parsed_uuid = UUID(text(name))
        except ValueError:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        if str(parsed_uuid) != text(name):
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        return parsed_uuid

    def optional_uuid(name: str) -> UUID | None:
        item = optional_text(name)
        if item is None:
            return None
        try:
            parsed_uuid = UUID(item)
        except ValueError:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        if str(parsed_uuid) != item:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        return parsed_uuid

    occurred_text = text("occurred_at")
    try:
        occurred_at = datetime.fromisoformat(occurred_text.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if occurred_at.tzinfo is not timezone.utc or occurred_at.fold != 0:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        candidate = AuditEventCandidateV2(
            authorization=AuditAuthorizationProofV2(
                command_id_fingerprint=text("authorization_command_id_fingerprint"),
                request_digest=text("authorization_request_digest"),
                session_fingerprint=text("authorization_session_fingerprint"),
                authorization_audit_digest=text("authorization_audit_digest"),
            ),
            request_sha256=text("request_sha256"),
            event_id=uuid("event_id"),
            occurred_at=occurred_at,
            actor_type=text("actor_type"),
            actor_id=optional_uuid("actor_id"),
            action=text("action"),
            target_type=text("target_type"),
            target_id=uuid("target_id"),
            outcome=text("outcome"),
            severity=text("severity"),
            correlation_id=uuid("correlation_id"),
            request_id=optional_text("request_id"),
            reason_code=text("reason_code"),
            before_hash=optional_text("before_hash"),
            after_hash=optional_text("after_hash"),
            event_digest=text("event_digest"),
        )
    except AuditRuntimeFailureV2:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if _canonical_text(candidate.canonical_material) != value:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    return candidate


def _marker_sha256(candidate: AuditEventCandidateV2) -> str:
    return canonical_sha256_v2(
        {
            "schema": "RAOS_ST0405_ATOMIC_MARKER_V2",
            "authorization_command_id_fingerprint": (
                candidate.authorization.command_id_fingerprint
            ),
            "event_id": str(candidate.event_id),
            "request_sha256": candidate.request_sha256,
        }
    )


def _row_values(record: PersistedAuditEventV2) -> tuple[object, ...]:
    candidate = record.candidate
    return (
        record.sequence,
        str(candidate.event_id),
        candidate.authorization.command_id_fingerprint,
        candidate.authorization.request_digest,
        candidate.authorization.session_fingerprint,
        candidate.authorization.authorization_audit_digest,
        candidate.request_sha256,
        str(candidate.correlation_id),
        _canonical_text(candidate.canonical_material),
        record.previous_entry_sha256,
        record.entry_sha256,
        record.atomic_marker_sha256,
    )


def _record_sha256(values: tuple[object, ...]) -> str:
    return canonical_sha256_v2(
        {"schema": "RAOS_ST0405_SQLITE_ROW_V2", "values": list(values)}
    )


def _row_record(row: object) -> PersistedAuditEventV2:
    if type(row) is not tuple:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    values = cast(tuple[object, ...], row)
    if len(values) != 13:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if type(values[0]) is not int or any(type(item) is not str for item in values[1:]):
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    raw_values = values[:-1]
    if _record_sha256(raw_values) != values[-1]:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    candidate = _parse_candidate(values[8])
    if (
        str(candidate.event_id) != values[1]
        or candidate.authorization.command_id_fingerprint != values[2]
        or candidate.authorization.request_digest != values[3]
        or candidate.authorization.session_fingerprint != values[4]
        or candidate.authorization.authorization_audit_digest != values[5]
        or candidate.request_sha256 != values[6]
        or str(candidate.correlation_id) != values[7]
    ):
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        return PersistedAuditEventV2(
            candidate=candidate,
            sequence=values[0],
            previous_entry_sha256=cast(str, values[9]),
            entry_sha256=cast(str, values[10]),
            atomic_marker_sha256=cast(str, values[11]),
        )
    except AuditRuntimeFailureV2:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)


def _receipt(record: PersistedAuditEventV2, *, replayed: bool) -> AuditAppendReceiptV2:
    return AuditAppendReceiptV2(
        event_id=record.candidate.event_id,
        request_sha256=record.candidate.request_sha256,
        sequence=record.sequence,
        previous_entry_sha256=record.previous_entry_sha256,
        entry_sha256=record.entry_sha256,
        replayed=replayed,
    )


@final
class RecordedSqliteAuditRuntimeStoreFactoryV2:
    """Lexically capture a path; filesystem inspection is delayed until open()."""

    __slots__ = ("_environment", "_faults", "_open_count", "_private_root", "_lock")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: object,
        fault_once_at: RecordedAuditFaultV2 | None = None,
    ) -> None:
        self._environment = _recorded_environment(environment)
        if not isinstance(private_root, Path) or not private_root.is_absolute():
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            fault_once_at is not None
            and type(fault_once_at) is not RecordedAuditFaultV2
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        self._private_root = private_root
        self._faults = _FaultController(fault=fault_once_at, lock=Lock())
        self._open_count = 0
        self._lock = Lock()

    @property
    def open_count(self) -> int:
        with self._lock:
            return self._open_count

    def arm_fault(self, fault: RecordedAuditFaultV2) -> None:
        if type(fault) is not RecordedAuditFaultV2:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        with self._faults.lock:
            if self._faults.fault is not None:
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            self._faults.fault = fault

    def open(self) -> RecordedSqliteAuditRuntimeStoreV2:
        with self._lock:
            self._open_count += 1
        return RecordedSqliteAuditRuntimeStoreV2(
            environment=self._environment,
            private_root=self._private_root,
            faults=self._faults,
        )


@final
class RecordedSqliteAuditRuntimeStoreV2:
    """Append-only SQLite store with one atomic synthetic marker transaction."""

    __slots__ = ("_database_path", "_environment", "_faults", "_private_root")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        faults: _FaultController,
    ) -> None:
        self._environment = _recorded_environment(environment)
        self._private_root = self._validate_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._faults = faults
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        root = Path(os.path.abspath(value))
        try:
            metadata = root.lstat()
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current = current / component
                item = current.lstat()
                if stat.S_ISLNK(item.st_mode) or not stat.S_ISDIR(item.st_mode):
                    _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        return root

    def _validate_database_file(self) -> None:
        self._validate_private_root(self._private_root)
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    def _create_or_validate_database_file(self) -> None:
        root_fd = -1
        descriptor = -1
        try:
            root_fd = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_fd,
                )
                os.fsync(descriptor)
                os.fsync(root_fd)
            except FileExistsError:
                pass
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_fd >= 0:
                os.close(root_fd)
        self._validate_database_file()

    def _connect(self) -> sqlite3.Connection:
        self._validate_database_file()
        try:
            connection = sqlite3.connect(
                self._database_path, timeout=0.25, isolation_level=None
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            if connection.execute("PRAGMA journal_mode = DELETE").fetchone() != (
                "delete",
            ):
                connection.close()
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            return connection
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS audit_metadata_v2 (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    schema_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS audit_atomic_marker_v2 (
                    authorization_command_id_fingerprint TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    request_sha256 TEXT NOT NULL,
                    marker_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS audit_event_v2 (
                    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
                    event_id TEXT NOT NULL UNIQUE,
                    authorization_command_id_fingerprint TEXT NOT NULL UNIQUE,
                    authorization_request_digest TEXT NOT NULL,
                    authorization_session_fingerprint TEXT NOT NULL,
                    authorization_audit_digest TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    previous_entry_sha256 TEXT NOT NULL,
                    entry_sha256 TEXT NOT NULL UNIQUE,
                    atomic_marker_sha256 TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    FOREIGN KEY (authorization_command_id_fingerprint)
                      REFERENCES audit_atomic_marker_v2(authorization_command_id_fingerprint),
                    FOREIGN KEY (event_id) REFERENCES audit_atomic_marker_v2(event_id)
                )"""
            )
            metadata = connection.execute(
                "SELECT schema_version,schema_sha256 FROM audit_metadata_v2 WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                connection.execute(
                    "INSERT INTO audit_metadata_v2 VALUES (1,?,?)",
                    (AUDIT_RUNTIME_SCHEMA_VERSION_V2, _SCHEMA_SHA256),
                )
            elif metadata != (AUDIT_RUNTIME_SCHEMA_VERSION_V2, _SCHEMA_SHA256):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            self._verify_schema(connection)
            self._verify_all(connection)
            connection.commit()
        except AuditRuntimeFailureV2:
            connection.rollback()
            raise
        except sqlite3.IntegrityError:
            connection.rollback()
            _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
        except sqlite3.Error:
            connection.rollback()
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        tables = frozenset(
            cast(str, row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        )
        if tables != _TABLES:
            _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
        for table, expected in _EXPECTED_COLUMNS.items():
            rows = tuple(
                tuple(row) for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if rows != expected:
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def _verify_all(cls, connection: sqlite3.Connection) -> tuple[str, int]:
        rows = connection.execute(
            "SELECT sequence,event_id,authorization_command_id_fingerprint,"
            "authorization_request_digest,authorization_session_fingerprint,"
            "authorization_audit_digest,request_sha256,correlation_id,candidate_json,"
            "previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 "
            "FROM audit_event_v2 ORDER BY sequence"
        ).fetchall()
        marker_rows = {
            cast(str, row[0]): tuple(row)
            for row in connection.execute(
                "SELECT authorization_command_id_fingerprint,event_id,request_sha256,marker_sha256 "
                "FROM audit_atomic_marker_v2"
            ).fetchall()
        }
        if len(marker_rows) != len(rows):
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        previous = AUDIT_RUNTIME_GENESIS_SHA256_V2
        for index, raw in enumerate(rows, start=1):
            record = _row_record(tuple(raw))
            if record.sequence != index or record.previous_entry_sha256 != previous:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            candidate = record.candidate
            marker = marker_rows.get(candidate.authorization.command_id_fingerprint)
            if marker != (
                candidate.authorization.command_id_fingerprint,
                str(candidate.event_id),
                candidate.request_sha256,
                record.atomic_marker_sha256,
            ) or record.atomic_marker_sha256 != _marker_sha256(candidate):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            previous = record.entry_sha256
        return previous, len(rows)

    def lookup_authorization(
        self, proof: AuditAuthorizationProofV2
    ) -> PersistedAuditEventV2 | None:
        if type(proof) is not AuditAuthorizationProofV2:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            self._verify_schema(connection)
            self._verify_all(connection)
            row = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,"
                "authorization_request_digest,authorization_session_fingerprint,"
                "authorization_audit_digest,request_sha256,correlation_id,candidate_json,"
                "previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 "
                "FROM audit_event_v2 WHERE authorization_command_id_fingerprint=?",
                (proof.command_id_fingerprint,),
            ).fetchone()
            if row is None:
                return None
            record = _row_record(tuple(row))
            if record.candidate.authorization != proof:
                _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
            return record
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()

    def append_atomic(self, candidate: AuditEventCandidateV2) -> AuditAppendReceiptV2:
        if type(candidate) is not AuditEventCandidateV2:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        committed = False
        record: PersistedAuditEventV2
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_schema(connection)
            tail, count = self._verify_all(connection)
            raw_existing = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,"
                "authorization_request_digest,authorization_session_fingerprint,"
                "authorization_audit_digest,request_sha256,correlation_id,candidate_json,"
                "previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 "
                "FROM audit_event_v2 WHERE authorization_command_id_fingerprint=?",
                (candidate.authorization.command_id_fingerprint,),
            ).fetchone()
            if raw_existing is not None:
                existing = _row_record(tuple(raw_existing))
                if existing.candidate != candidate:
                    _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
                connection.commit()
                return _receipt(existing, replayed=True)
            sequence = count + 1
            marker_sha256 = _marker_sha256(candidate)
            entry_sha256 = audit_entry_sha256_v2(
                candidate=candidate,
                sequence=sequence,
                previous_entry_sha256=tail,
                atomic_marker_sha256=marker_sha256,
            )
            record = PersistedAuditEventV2(
                candidate=candidate,
                sequence=sequence,
                previous_entry_sha256=tail,
                entry_sha256=entry_sha256,
                atomic_marker_sha256=marker_sha256,
            )
            connection.execute(
                "INSERT INTO audit_atomic_marker_v2 VALUES (?,?,?,?)",
                (
                    candidate.authorization.command_id_fingerprint,
                    str(candidate.event_id),
                    candidate.request_sha256,
                    marker_sha256,
                ),
            )
            if self._faults.consume(RecordedAuditFaultV2.AFTER_MARKER_BEFORE_EVENT):
                raise _KnownRollback()
            values = _row_values(record)
            connection.execute(
                "INSERT INTO audit_event_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*values, _record_sha256(values)),
            )
            self._verify_all(connection)
            connection.commit()
            committed = True
        except _KnownRollback:
            connection.rollback()
            _fail(AuditRuntimeFailureCodeV2.STORAGE_ROLLED_BACK)
        except AuditRuntimeFailureV2:
            if not committed:
                connection.rollback()
            raise
        except sqlite3.IntegrityError:
            connection.rollback()
            _fail(AuditRuntimeFailureCodeV2.CONCURRENCY_CONFLICT)
        except sqlite3.Error:
            connection.rollback()
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()
        if self._faults.consume(RecordedAuditFaultV2.AFTER_COMMIT):
            _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
        return _receipt(record, replayed=False)

    def recover_exact(self, candidate: AuditEventCandidateV2) -> AuditAppendReceiptV2:
        if type(candidate) is not AuditEventCandidateV2:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        record = self.lookup_authorization(candidate.authorization)
        if record is None:
            _fail(AuditRuntimeFailureCodeV2.RECOVERY_NOT_FOUND)
        if record.candidate != candidate:
            _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
        return _receipt(record, replayed=True)

    def load_exact(self, event_id: UUID) -> PersistedAuditEventV2 | None:
        if type(event_id) is not UUID or event_id.int == 0:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            self._verify_schema(connection)
            self._verify_all(connection)
            row = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,"
                "authorization_request_digest,authorization_session_fingerprint,"
                "authorization_audit_digest,request_sha256,correlation_id,candidate_json,"
                "previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 "
                "FROM audit_event_v2 WHERE event_id=?",
                (str(event_id),),
            ).fetchone()
            return None if row is None else _row_record(tuple(row))
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()

    def query_internal_correlation(
        self, correlation_id: UUID, *, limit: int
    ) -> tuple[PersistedAuditEventV2, ...]:
        if (
            type(correlation_id) is not UUID
            or correlation_id.int == 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            self._verify_schema(connection)
            self._verify_all(connection)
            rows = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,"
                "authorization_request_digest,authorization_session_fingerprint,"
                "authorization_audit_digest,request_sha256,correlation_id,candidate_json,"
                "previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 "
                "FROM audit_event_v2 WHERE correlation_id=? ORDER BY sequence LIMIT ?",
                (str(correlation_id), limit),
            ).fetchall()
            return tuple(_row_record(tuple(row)) for row in rows)
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()

    def verify_chain(self) -> tuple[str, int]:
        connection = self._connect()
        try:
            self._verify_schema(connection)
            return self._verify_all(connection)
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            connection.close()


__all__ = [
    "RecordedAuditFaultV2",
    "RecordedSqliteAuditRuntimeStoreFactoryV2",
    "RecordedSqliteAuditRuntimeStoreV2",
]
