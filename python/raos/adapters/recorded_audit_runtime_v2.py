"""Owner-private, append-only SQLite audit journal for ST-0405 V2.

The adapter is a recorded local development seam. It pins the owner-private
root and database inode, verifies the complete schema and event chain on every
operation, and retains the strongest prefix observed by this process. A fresh
process has no independent durable rollback anchor and no such authority is
claimed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
from typing import Final, NoReturn, cast, final
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
    snapshot_audit_authorization_proof_v2,
    snapshot_audit_candidate_v2,
)


_DATABASE_NAME: Final = "st0405-recorded-audit-runtime-v2.sqlite3"
_APPLICATION_ID: Final = 1_380_400_502
_USER_VERSION: Final = 2
_MAX_CANONICAL_BYTES: Final = 64 * 1024


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


_CREATE_METADATA = """CREATE TABLE audit_metadata_v2 (
    singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL CHECK (schema_version = 'ST0405_RECORDED_AUDIT_RUNTIME_V2'),
    schema_sha256 TEXT NOT NULL CHECK (length(schema_sha256) = 64 AND schema_sha256 NOT GLOB '*[^0-9a-f]*'),
    event_count INTEGER NOT NULL CHECK (event_count >= 0),
    event_head_sha256 TEXT NOT NULL CHECK (length(event_head_sha256) = 64 AND event_head_sha256 NOT GLOB '*[^0-9a-f]*'),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
) STRICT"""
_CREATE_MARKER = """CREATE TABLE audit_atomic_marker_v2 (
    sequence INTEGER NOT NULL PRIMARY KEY CHECK (sequence >= 1),
    authorization_command_id_fingerprint TEXT NOT NULL UNIQUE CHECK (length(authorization_command_id_fingerprint) = 64 AND authorization_command_id_fingerprint NOT GLOB '*[^0-9a-f]*'),
    event_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
    marker_sha256 TEXT NOT NULL UNIQUE CHECK (length(marker_sha256) = 64 AND marker_sha256 NOT GLOB '*[^0-9a-f]*'),
    UNIQUE (authorization_command_id_fingerprint, event_id, request_sha256, marker_sha256)
) STRICT"""
_CREATE_EVENT = """CREATE TABLE audit_event_v2 (
    sequence INTEGER NOT NULL PRIMARY KEY CHECK (sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    authorization_command_id_fingerprint TEXT NOT NULL UNIQUE CHECK (length(authorization_command_id_fingerprint) = 64 AND authorization_command_id_fingerprint NOT GLOB '*[^0-9a-f]*'),
    authorization_request_digest TEXT NOT NULL CHECK (length(authorization_request_digest) = 64 AND authorization_request_digest NOT GLOB '*[^0-9a-f]*'),
    authorization_session_fingerprint TEXT NOT NULL CHECK (length(authorization_session_fingerprint) = 64 AND authorization_session_fingerprint NOT GLOB '*[^0-9a-f]*'),
    authorization_audit_digest TEXT NOT NULL CHECK (length(authorization_audit_digest) = 64 AND authorization_audit_digest NOT GLOB '*[^0-9a-f]*'),
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
    correlation_id TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    previous_entry_sha256 TEXT NOT NULL CHECK (length(previous_entry_sha256) = 64 AND previous_entry_sha256 NOT GLOB '*[^0-9a-f]*'),
    entry_sha256 TEXT NOT NULL UNIQUE CHECK (length(entry_sha256) = 64 AND entry_sha256 NOT GLOB '*[^0-9a-f]*'),
    atomic_marker_sha256 TEXT NOT NULL CHECK (length(atomic_marker_sha256) = 64 AND atomic_marker_sha256 NOT GLOB '*[^0-9a-f]*'),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64 AND record_sha256 NOT GLOB '*[^0-9a-f]*'),
    FOREIGN KEY (sequence) REFERENCES audit_atomic_marker_v2(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (authorization_command_id_fingerprint, event_id, request_sha256, atomic_marker_sha256) REFERENCES audit_atomic_marker_v2(authorization_command_id_fingerprint, event_id, request_sha256, marker_sha256) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT"""
_CREATE_CORRELATION_INDEX = (
    "CREATE INDEX audit_event_v2_correlation_sequence_idx "
    "ON audit_event_v2(correlation_id, sequence)"
)
_CREATE_MARKER_APPEND_GUARD = """CREATE TRIGGER audit_atomic_marker_v2_append_guard
BEFORE INSERT ON audit_atomic_marker_v2
WHEN NEW.sequence != COALESCE((SELECT event_count + 1 FROM audit_metadata_v2 WHERE singleton = 1), -1)
 OR EXISTS (SELECT 1 FROM audit_event_v2 WHERE sequence = NEW.sequence)
BEGIN SELECT RAISE(ABORT, 'ST0405_MARKER_APPEND_INVALID'); END"""
_CREATE_MARKER_NO_UPDATE = """CREATE TRIGGER audit_atomic_marker_v2_no_update
BEFORE UPDATE ON audit_atomic_marker_v2
BEGIN SELECT RAISE(ABORT, 'ST0405_MARKER_IMMUTABLE'); END"""
_CREATE_MARKER_NO_DELETE = """CREATE TRIGGER audit_atomic_marker_v2_no_delete
BEFORE DELETE ON audit_atomic_marker_v2
BEGIN SELECT RAISE(ABORT, 'ST0405_MARKER_APPEND_ONLY'); END"""
_CREATE_EVENT_APPEND_GUARD = """CREATE TRIGGER audit_event_v2_append_guard
BEFORE INSERT ON audit_event_v2
WHEN NEW.sequence != COALESCE((SELECT event_count + 1 FROM audit_metadata_v2 WHERE singleton = 1), -1)
 OR NEW.previous_entry_sha256 != COALESCE((SELECT event_head_sha256 FROM audit_metadata_v2 WHERE singleton = 1), '')
 OR NOT EXISTS (
    SELECT 1 FROM audit_atomic_marker_v2
    WHERE sequence = NEW.sequence
      AND authorization_command_id_fingerprint = NEW.authorization_command_id_fingerprint
      AND event_id = NEW.event_id
      AND request_sha256 = NEW.request_sha256
      AND marker_sha256 = NEW.atomic_marker_sha256
 )
BEGIN SELECT RAISE(ABORT, 'ST0405_EVENT_APPEND_INVALID'); END"""
_CREATE_EVENT_NO_UPDATE = """CREATE TRIGGER audit_event_v2_no_update
BEFORE UPDATE ON audit_event_v2
BEGIN SELECT RAISE(ABORT, 'ST0405_EVENT_IMMUTABLE'); END"""
_CREATE_EVENT_NO_DELETE = """CREATE TRIGGER audit_event_v2_no_delete
BEFORE DELETE ON audit_event_v2
BEGIN SELECT RAISE(ABORT, 'ST0405_EVENT_APPEND_ONLY'); END"""
_CREATE_METADATA_GUARD_UPDATE = """CREATE TRIGGER audit_metadata_v2_guard_update
BEFORE UPDATE ON audit_metadata_v2
WHEN NEW.singleton != OLD.singleton
 OR NEW.schema_version != OLD.schema_version
 OR NEW.schema_sha256 != OLD.schema_sha256
 OR NEW.event_count != OLD.event_count + 1
 OR NEW.event_head_sha256 = OLD.event_head_sha256
 OR NOT EXISTS (
    SELECT 1 FROM audit_event_v2
    WHERE sequence = NEW.event_count
      AND previous_entry_sha256 = OLD.event_head_sha256
      AND entry_sha256 = NEW.event_head_sha256
 )
BEGIN SELECT RAISE(ABORT, 'ST0405_METADATA_TRANSITION_INVALID'); END"""
_CREATE_METADATA_NO_DELETE = """CREATE TRIGGER audit_metadata_v2_no_delete
BEFORE DELETE ON audit_metadata_v2
BEGIN SELECT RAISE(ABORT, 'ST0405_METADATA_REQUIRED'); END"""
_CREATE_METADATA_NO_INSERT = """CREATE TRIGGER audit_metadata_v2_no_insert
BEFORE INSERT ON audit_metadata_v2
WHEN EXISTS (SELECT 1 FROM audit_metadata_v2)
BEGIN SELECT RAISE(ABORT, 'ST0405_METADATA_SINGLETON'); END"""

_TABLE_SQL: Final = (
    ("audit_metadata_v2", _CREATE_METADATA),
    ("audit_atomic_marker_v2", _CREATE_MARKER),
    ("audit_event_v2", _CREATE_EVENT),
)
_INDEX_SQL: Final = (
    (
        "audit_event_v2_correlation_sequence_idx",
        "audit_event_v2",
        _CREATE_CORRELATION_INDEX,
    ),
)
_TRIGGER_SQL: Final = (
    (
        "audit_atomic_marker_v2_append_guard",
        "audit_atomic_marker_v2",
        _CREATE_MARKER_APPEND_GUARD,
    ),
    (
        "audit_atomic_marker_v2_no_update",
        "audit_atomic_marker_v2",
        _CREATE_MARKER_NO_UPDATE,
    ),
    (
        "audit_atomic_marker_v2_no_delete",
        "audit_atomic_marker_v2",
        _CREATE_MARKER_NO_DELETE,
    ),
    ("audit_event_v2_append_guard", "audit_event_v2", _CREATE_EVENT_APPEND_GUARD),
    ("audit_event_v2_no_update", "audit_event_v2", _CREATE_EVENT_NO_UPDATE),
    ("audit_event_v2_no_delete", "audit_event_v2", _CREATE_EVENT_NO_DELETE),
    (
        "audit_metadata_v2_guard_update",
        "audit_metadata_v2",
        _CREATE_METADATA_GUARD_UPDATE,
    ),
    (
        "audit_metadata_v2_no_delete",
        "audit_metadata_v2",
        _CREATE_METADATA_NO_DELETE,
    ),
    (
        "audit_metadata_v2_no_insert",
        "audit_metadata_v2",
        _CREATE_METADATA_NO_INSERT,
    ),
)
_AUTO_INDEXES: Final = frozenset(
    {
        (
            "index",
            "sqlite_autoindex_audit_atomic_marker_v2_1",
            "audit_atomic_marker_v2",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_audit_atomic_marker_v2_2",
            "audit_atomic_marker_v2",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_audit_atomic_marker_v2_3",
            "audit_atomic_marker_v2",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_audit_atomic_marker_v2_4",
            "audit_atomic_marker_v2",
            None,
        ),
        ("index", "sqlite_autoindex_audit_event_v2_1", "audit_event_v2", None),
        ("index", "sqlite_autoindex_audit_event_v2_2", "audit_event_v2", None),
        ("index", "sqlite_autoindex_audit_event_v2_3", "audit_event_v2", None),
    }
)
_TABLE_COLUMNS: Final = {
    "audit_metadata_v2": (
        (0, "singleton", "INTEGER", 1, None, 1, 0),
        (1, "schema_version", "TEXT", 1, None, 0, 0),
        (2, "schema_sha256", "TEXT", 1, None, 0, 0),
        (3, "event_count", "INTEGER", 1, None, 0, 0),
        (4, "event_head_sha256", "TEXT", 1, None, 0, 0),
        (5, "record_sha256", "TEXT", 1, None, 0, 0),
    ),
    "audit_atomic_marker_v2": (
        (0, "sequence", "INTEGER", 1, None, 1, 0),
        (1, "authorization_command_id_fingerprint", "TEXT", 1, None, 0, 0),
        (2, "event_id", "TEXT", 1, None, 0, 0),
        (3, "request_sha256", "TEXT", 1, None, 0, 0),
        (4, "marker_sha256", "TEXT", 1, None, 0, 0),
    ),
    "audit_event_v2": (
        (0, "sequence", "INTEGER", 1, None, 1, 0),
        (1, "event_id", "TEXT", 1, None, 0, 0),
        (2, "authorization_command_id_fingerprint", "TEXT", 1, None, 0, 0),
        (3, "authorization_request_digest", "TEXT", 1, None, 0, 0),
        (4, "authorization_session_fingerprint", "TEXT", 1, None, 0, 0),
        (5, "authorization_audit_digest", "TEXT", 1, None, 0, 0),
        (6, "request_sha256", "TEXT", 1, None, 0, 0),
        (7, "correlation_id", "TEXT", 1, None, 0, 0),
        (8, "candidate_json", "TEXT", 1, None, 0, 0),
        (9, "previous_entry_sha256", "TEXT", 1, None, 0, 0),
        (10, "entry_sha256", "TEXT", 1, None, 0, 0),
        (11, "atomic_marker_sha256", "TEXT", 1, None, 0, 0),
        (12, "record_sha256", "TEXT", 1, None, 0, 0),
    ),
}
_IndexSpec = tuple[str, int, str, int, tuple[str, ...]]
_EXPECTED_INDEXES: Final[dict[str, frozenset[_IndexSpec]]] = {
    "audit_metadata_v2": frozenset(),
    "audit_atomic_marker_v2": frozenset(
        {
            (
                "sqlite_autoindex_audit_atomic_marker_v2_1",
                1,
                "u",
                0,
                ("authorization_command_id_fingerprint",),
            ),
            ("sqlite_autoindex_audit_atomic_marker_v2_2", 1, "u", 0, ("event_id",)),
            (
                "sqlite_autoindex_audit_atomic_marker_v2_3",
                1,
                "u",
                0,
                ("marker_sha256",),
            ),
            (
                "sqlite_autoindex_audit_atomic_marker_v2_4",
                1,
                "u",
                0,
                (
                    "authorization_command_id_fingerprint",
                    "event_id",
                    "request_sha256",
                    "marker_sha256",
                ),
            ),
        }
    ),
    "audit_event_v2": frozenset(
        {
            (
                "audit_event_v2_correlation_sequence_idx",
                0,
                "c",
                0,
                ("correlation_id", "sequence"),
            ),
            ("sqlite_autoindex_audit_event_v2_1", 1, "u", 0, ("event_id",)),
            (
                "sqlite_autoindex_audit_event_v2_2",
                1,
                "u",
                0,
                ("authorization_command_id_fingerprint",),
            ),
            ("sqlite_autoindex_audit_event_v2_3", 1, "u", 0, ("entry_sha256",)),
        }
    ),
}
_ForeignKeySpec = tuple[str, str, str, str, str, str]
_EXPECTED_FOREIGN_KEYS: Final[dict[str, frozenset[_ForeignKeySpec]]] = {
    "audit_metadata_v2": frozenset(),
    "audit_atomic_marker_v2": frozenset(),
    "audit_event_v2": frozenset(
        {
            (
                "audit_atomic_marker_v2",
                "sequence",
                "sequence",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "audit_atomic_marker_v2",
                "authorization_command_id_fingerprint",
                "authorization_command_id_fingerprint",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "audit_atomic_marker_v2",
                "event_id",
                "event_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "audit_atomic_marker_v2",
                "request_sha256",
                "request_sha256",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "audit_atomic_marker_v2",
                "atomic_marker_sha256",
                "marker_sha256",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
}
_SCHEMA_SHA256: Final = canonical_sha256_v2(
    {
        "application_id": _APPLICATION_ID,
        "user_version": _USER_VERSION,
        "tables": [(name, _normalized_sql(sql)) for name, sql in _TABLE_SQL],
        "indexes": [
            (name, table, _normalized_sql(sql)) for name, table, sql in _INDEX_SQL
        ],
        "triggers": [
            (name, table, _normalized_sql(sql)) for name, table, sql in _TRIGGER_SQL
        ],
    }
)
_SCHEMA_INITIALIZATION_LOCK = RLock()
_PROCESS_REGISTRY_LOCK = RLock()


class RecordedAuditFaultV2(str, Enum):
    AFTER_MARKER_BEFORE_EVENT = "AFTER_MARKER_BEFORE_EVENT"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _KnownRollback(RuntimeError):
    __slots__ = ()


class _InjectedCommitFailure(sqlite3.OperationalError):
    __slots__ = ()


@dataclass(slots=True)
class _FaultController:
    fault: RecordedAuditFaultV2 | None
    lock: RLock

    def consume(self, point: RecordedAuditFaultV2) -> bool:
        with self.lock:
            if self.fault is point:
                self.fault = None
                return True
            return False


@dataclass(slots=True)
class _ProcessAnchor:
    root_identity: tuple[int, int]
    database_identity: tuple[int, int]
    count: int
    head: str
    lock: RLock


_PROCESS_ANCHORS: dict[str, _ProcessAnchor] = {}


def _fail(code: AuditRuntimeFailureCodeV2) -> NoReturn:
    fail_audit_runtime_v2(code)


def _recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
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
    if not encoded or len(encoded.encode("ascii")) > _MAX_CANONICAL_BYTES:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    return encoded


def _parse_candidate(value: object) -> AuditEventCandidateV2:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _MAX_CANONICAL_BYTES
    ):
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
        if str(parsed_uuid) != text(name) or parsed_uuid.int == 0:
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
        if str(parsed_uuid) != item or parsed_uuid.int == 0:
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


def _metadata_sha256(*, count: int, head: str) -> str:
    return canonical_sha256_v2(
        {
            "schema": "RAOS_ST0405_SQLITE_METADATA_V2",
            "schema_version": AUDIT_RUNTIME_SCHEMA_VERSION_V2,
            "schema_sha256": _SCHEMA_SHA256,
            "event_count": count,
            "event_head_sha256": head,
        }
    )


def _row_record(row: object) -> PersistedAuditEventV2:
    if type(row) is not tuple:
        _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    values = cast(tuple[object, ...], row)
    if (
        len(values) != 13
        or type(values[0]) is not int
        or any(type(item) is not str for item in values[1:])
    ):
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
    """Capture a path lexically; inspect it only after authorization succeeds."""

    __slots__ = ("_environment", "_faults", "_open_count", "_private_root", "_lock")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: object,
        fault_once_at: RecordedAuditFaultV2 | None = None,
    ) -> None:
        self._environment = _recorded_environment(environment)
        if not isinstance(private_root, Path):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        try:
            raw_private_root = os.fspath(private_root)
        except TypeError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if type(raw_private_root) is not str or "\x00" in raw_private_root:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        captured_private_root = Path(raw_private_root)
        if (
            not captured_private_root.is_absolute()
            or ".." in captured_private_root.parts
            or str(captured_private_root) != raw_private_root
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            fault_once_at is not None
            and type(fault_once_at) is not RecordedAuditFaultV2
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        self._private_root = captured_private_root
        self._faults = _FaultController(fault=fault_once_at, lock=RLock())
        self._open_count = 0
        self._lock = RLock()

    @property
    def open_count(self) -> int:
        with self._lock:
            return self._open_count

    @property
    def external_action_count(self) -> int:
        return 0

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
    """Exact-schema append-only store with a process-local prefix anchor."""

    __slots__ = (
        "_database_identity",
        "_database_path",
        "_environment",
        "_faults",
        "_private_root",
        "_process_anchor",
        "_root_identity",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        faults: _FaultController,
    ) -> None:
        self._environment = _recorded_environment(environment)
        self._private_root, self._root_identity = self._validate_private_root(
            private_root
        )
        self._database_path = self._private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] = (-1, -1)
        self._faults = faults
        self._process_anchor: _ProcessAnchor | None = None
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(
                allow_create=True, allow_empty=True
            )
            self._database_identity = identity
            connection = self._connect(verify=False, allow_empty=created)
            try:
                if created:
                    self._initialize_new(connection)
                else:
                    self._verify_schema(connection)
                    self._verify_all(connection)
                head, count = self._verified_state(connection, check_process=False)
                self._bind_process_anchor(connection, head=head, count=count)
            finally:
                self._close_safely(connection)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @property
    def external_action_count(self) -> int:
        _recorded_environment(self._environment)
        return 0

    @staticmethod
    def _validate_private_root(value: object) -> tuple[Path, tuple[int, int]]:
        if (
            not isinstance(value, Path)
            or not value.is_absolute()
            or ".." in value.parts
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        root = Path(os.path.abspath(value))
        if root != value:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            metadata = os.lstat(root)
        except AuditRuntimeFailureV2:
            raise
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_nlink < 1
        ):
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        return root, (metadata.st_dev, metadata.st_ino)

    def _validate_root_identity(self) -> None:
        root, identity = self._validate_private_root(self._private_root)
        if root != self._private_root or identity != self._root_identity:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def _open_database_file(
        self,
        *,
        allow_create: bool,
        allow_empty: bool = False,
    ) -> tuple[bool, tuple[int, int]]:
        self._validate_root_identity()
        root_descriptor = -1
        database_descriptor = -1
        created = False
        try:
            root_descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_metadata = os.fstat(root_descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
            if allow_create:
                try:
                    database_descriptor = os.open(
                        _DATABASE_NAME,
                        flags | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=root_descriptor,
                    )
                    created = True
                except FileExistsError:
                    database_descriptor = os.open(
                        _DATABASE_NAME, flags, dir_fd=root_descriptor
                    )
            else:
                database_descriptor = os.open(
                    _DATABASE_NAME, flags, dir_fd=root_descriptor
                )
            metadata = os.fstat(database_descriptor)
            named = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            identity = (metadata.st_dev, metadata.st_ino)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or (named.st_dev, named.st_ino) != identity
            ):
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            if (
                self._database_identity != (-1, -1)
                and identity != self._database_identity
            ):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            if not created:
                if metadata.st_size < 100:
                    if not (allow_empty and metadata.st_size == 0):
                        _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
                elif os.pread(database_descriptor, 16, 0) != b"SQLite format 3\x00":
                    _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            if created:
                os.fsync(database_descriptor)
                os.fsync(root_descriptor)
            return created, identity
        except AuditRuntimeFailureV2:
            raise
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self, *, allow_empty: bool = False) -> None:
        _created, identity = self._open_database_file(
            allow_create=False, allow_empty=allow_empty
        )
        if identity != self._database_identity:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def _fsync_database_and_root(self) -> None:
        root_descriptor = -1
        database_descriptor = -1
        try:
            root_descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_metadata = os.fstat(root_descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            database_descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=root_descriptor,
            )
            metadata = os.fstat(database_descriptor)
            named = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                (metadata.st_dev, metadata.st_ino) != self._database_identity
                or (named.st_dev, named.st_ino) != self._database_identity
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            os.fsync(database_descriptor)
            os.fsync(root_descriptor)
        except AuditRuntimeFailureV2:
            raise
        except OSError:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
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
                timeout=10.0,
                isolation_level=None,
            )
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            if connection.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            self._validate_database_identity(allow_empty=allow_empty)
            if verify:
                head, count = self._verified_state(connection, check_process=True)
                self._pin_process_state(count=count, head=head)
            return connection
        except AuditRuntimeFailureV2:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._close_safely(connection)
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            if connection.execute("PRAGMA application_id").fetchone() != (0,):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            if connection.execute("PRAGMA user_version").fetchone() != (0,):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            if connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() != (
                0,
            ):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            connection.execute("BEGIN EXCLUSIVE")
            self._validate_database_identity(allow_empty=True)
            for _name, statement in _TABLE_SQL:
                connection.execute(statement)
            for _name, _table, statement in _INDEX_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO audit_metadata_v2(singleton,schema_version,schema_sha256,event_count,event_head_sha256,record_sha256) VALUES (?,?,?,?,?,?)",
                (
                    1,
                    AUDIT_RUNTIME_SCHEMA_VERSION_V2,
                    _SCHEMA_SHA256,
                    0,
                    AUDIT_RUNTIME_GENESIS_SHA256_V2,
                    _metadata_sha256(count=0, head=AUDIT_RUNTIME_GENESIS_SHA256_V2),
                ),
            )
            for _name, _table, statement in _TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_USER_VERSION}")
            self._validate_database_identity(allow_empty=True)
            connection.execute("COMMIT")
            self._validate_database_identity()
            self._fsync_database_and_root()
        except AuditRuntimeFailureV2:
            self._rollback_quietly(connection, allow_empty=True)
            raise
        except sqlite3.Error:
            self._rollback_quietly(connection, allow_empty=True)
            _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
        self._verify_schema(connection)
        head, count = self._verify_all(connection)
        if count != 0 or head != AUDIT_RUNTIME_GENESIS_SHA256_V2:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

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
        try:
            if (
                connection.execute("PRAGMA application_id").fetchone()
                != (_APPLICATION_ID,)
                or connection.execute("PRAGMA user_version").fetchone()
                != (_USER_VERSION,)
                or connection.execute("PRAGMA foreign_keys").fetchone() != (1,)
                or connection.execute("PRAGMA trusted_schema").fetchone() != (0,)
                or connection.execute("PRAGMA temp_store").fetchone() != (2,)
                or connection.execute("PRAGMA synchronous").fetchone() != (2,)
                or connection.execute("PRAGMA secure_delete").fetchone() != (1,)
                or connection.execute("PRAGMA busy_timeout").fetchone() != (10000,)
                or connection.execute("PRAGMA journal_mode").fetchone() != ("delete",)
            ):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            expected_objects = {
                *(
                    ("table", name, name, _normalized_sql(sql))
                    for name, sql in _TABLE_SQL
                ),
                *(
                    ("index", name, table, _normalized_sql(sql))
                    for name, table, sql in _INDEX_SQL
                ),
                *(
                    ("trigger", name, table, _normalized_sql(sql))
                    for name, table, sql in _TRIGGER_SQL
                ),
                *_AUTO_INDEXES,
            }
            observed_objects = {
                (
                    cast(str, row[0]),
                    cast(str, row[1]),
                    cast(str, row[2]),
                    None if row[3] is None else _normalized_sql(cast(str, row[3])),
                )
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master"
                ).fetchall()
            }
            if observed_objects != expected_objects:
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            table_state = {
                cast(str, row[1]): (cast(int, row[4]), cast(int, row[5]))
                for row in connection.execute("PRAGMA table_list").fetchall()
                if row[1] in _TABLE_COLUMNS
            }
            if table_state != {name: (0, 1) for name in _TABLE_COLUMNS}:
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            for table, expected_columns in _TABLE_COLUMNS.items():
                observed_columns = tuple(
                    tuple(row)
                    for row in connection.execute(
                        f"PRAGMA table_xinfo({table})"
                    ).fetchall()
                )
                if observed_columns != expected_columns:
                    _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
                foreign_keys = frozenset(
                    (
                        cast(str, row[2]),
                        cast(str, row[3]),
                        cast(str, row[4]),
                        cast(str, row[5]),
                        cast(str, row[6]),
                        cast(str, row[7]),
                    )
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({table})"
                    ).fetchall()
                )
                if foreign_keys != _EXPECTED_FOREIGN_KEYS[table]:
                    _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
                indexes: set[tuple[str, int, str, int, tuple[str, ...]]] = set()
                for row in connection.execute(f"PRAGMA index_list({table})").fetchall():
                    name = cast(str, row[1])
                    columns = tuple(
                        cast(str, item[2])
                        for item in connection.execute(
                            f"PRAGMA index_info('{name}')"
                        ).fetchall()
                    )
                    indexes.add(
                        (
                            name,
                            cast(int, row[2]),
                            cast(str, row[3]),
                            cast(int, row[4]),
                            columns,
                        )
                    )
                if frozenset(indexes) != _EXPECTED_INDEXES[table]:
                    _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
            quick = tuple(
                tuple(row)
                for row in connection.execute("PRAGMA quick_check").fetchall()
            )
            if quick != (("ok",),):
                _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.SCHEMA_DRIFT)

    @classmethod
    def _verify_all(cls, connection: sqlite3.Connection) -> tuple[str, int]:
        try:
            integrity = tuple(
                tuple(row)
                for row in connection.execute("PRAGMA integrity_check").fetchall()
            )
            if integrity != (("ok",),):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            metadata_rows = connection.execute(
                "SELECT singleton,schema_version,schema_sha256,event_count,event_head_sha256,record_sha256 FROM audit_metadata_v2"
            ).fetchall()
            if len(metadata_rows) != 1:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            singleton, schema_version, schema_sha, count, head, metadata_sha = tuple(
                metadata_rows[0]
            )
            if (
                singleton != 1
                or schema_version != AUDIT_RUNTIME_SCHEMA_VERSION_V2
                or schema_sha != _SCHEMA_SHA256
                or type(count) is not int
                or count < 0
                or type(head) is not str
                or type(metadata_sha) is not str
                or metadata_sha != _metadata_sha256(count=count, head=head)
            ):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            rows = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 ORDER BY sequence"
            ).fetchall()
            markers = connection.execute(
                "SELECT sequence,authorization_command_id_fingerprint,event_id,request_sha256,marker_sha256 FROM audit_atomic_marker_v2 ORDER BY sequence"
            ).fetchall()
            if len(rows) != count or len(markers) != count:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            previous = AUDIT_RUNTIME_GENESIS_SHA256_V2
            for expected_sequence, (raw_row, raw_marker) in enumerate(
                zip(rows, markers, strict=True), start=1
            ):
                marker = tuple(raw_marker)
                if (
                    len(marker) != 5
                    or marker[0] != expected_sequence
                    or any(type(item) is not str for item in marker[1:])
                ):
                    _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
                record = _row_record(tuple(raw_row))
                candidate = record.candidate
                if (
                    record.sequence != expected_sequence
                    or record.previous_entry_sha256 != previous
                    or marker
                    != (
                        expected_sequence,
                        candidate.authorization.command_id_fingerprint,
                        str(candidate.event_id),
                        candidate.request_sha256,
                        record.atomic_marker_sha256,
                    )
                    or record.atomic_marker_sha256 != _marker_sha256(candidate)
                    or record.entry_sha256
                    != audit_entry_sha256_v2(
                        candidate=candidate,
                        sequence=record.sequence,
                        previous_entry_sha256=previous,
                        atomic_marker_sha256=record.atomic_marker_sha256,
                    )
                ):
                    _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
                previous = record.entry_sha256
            if head != previous:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            return head, count
        except AuditRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def _bind_process_anchor(
        self, connection: sqlite3.Connection, *, head: str, count: int
    ) -> None:
        key = str(self._private_root)
        with _PROCESS_REGISTRY_LOCK:
            anchor = _PROCESS_ANCHORS.get(key)
            if anchor is None:
                anchor = _ProcessAnchor(
                    root_identity=self._root_identity,
                    database_identity=self._database_identity,
                    count=count,
                    head=head,
                    lock=RLock(),
                )
                _PROCESS_ANCHORS[key] = anchor
            self._process_anchor = anchor
        with anchor.lock:
            if (
                anchor.root_identity != self._root_identity
                or anchor.database_identity != self._database_identity
            ):
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            self._require_process_monotonic(connection, count=count, head=head)
            anchor.count = count
            anchor.head = head

    def _require_process_monotonic(
        self, connection: sqlite3.Connection, *, count: int, head: str
    ) -> None:
        anchor = self._process_anchor
        if anchor is None:
            return
        if (
            anchor.root_identity != self._root_identity
            or anchor.database_identity != self._database_identity
            or count < anchor.count
        ):
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        if count == anchor.count:
            if head != anchor.head:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            return
        if anchor.count == 0:
            if anchor.head != AUDIT_RUNTIME_GENESIS_SHA256_V2:
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            return
        prefix = connection.execute(
            "SELECT entry_sha256 FROM audit_event_v2 WHERE sequence=?",
            (anchor.count,),
        ).fetchone()
        if prefix != (anchor.head,):
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def _pin_process_state(self, *, count: int, head: str) -> None:
        anchor = self._process_anchor
        if anchor is None or count < anchor.count:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        if count == anchor.count and head != anchor.head:
            _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        anchor.count = count
        anchor.head = head

    def _verified_state(
        self, connection: sqlite3.Connection, *, check_process: bool
    ) -> tuple[str, int]:
        self._validate_database_identity()
        self._verify_schema(connection)
        head, count = self._verify_all(connection)
        if check_process:
            self._require_process_monotonic(connection, count=count, head=head)
        self._validate_database_identity()
        return head, count

    def _anchor(self) -> _ProcessAnchor:
        anchor = self._process_anchor
        if anchor is None:
            _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        return anchor

    def _begin_verified_snapshot(
        self, connection: sqlite3.Connection
    ) -> tuple[str, int]:
        connection.execute("BEGIN")
        return self._verified_state(connection, check_process=True)

    def _commit_verified_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        head: str,
        count: int,
    ) -> None:
        self._validate_database_identity()
        connection.execute("COMMIT")
        self._validate_database_identity()
        self._pin_process_state(count=count, head=head)

    def lookup_authorization(
        self, proof: AuditAuthorizationProofV2
    ) -> PersistedAuditEventV2 | None:
        proof = snapshot_audit_authorization_proof_v2(proof)
        anchor = self._anchor()
        with anchor.lock:
            connection = self._connect(verify=False)
            try:
                head, count = self._begin_verified_snapshot(connection)
                row = connection.execute(
                    "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 WHERE authorization_command_id_fingerprint=?",
                    (proof.command_id_fingerprint,),
                ).fetchone()
                if row is None:
                    self._commit_verified_snapshot(connection, head=head, count=count)
                    return None
                record = _row_record(tuple(row))
                if record.candidate.authorization != proof:
                    _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
                self._commit_verified_snapshot(connection, head=head, count=count)
                return record
            except AuditRuntimeFailureV2:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                raise
            except sqlite3.Error:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            finally:
                self._close_safely(connection)

    def append_atomic(self, candidate: AuditEventCandidateV2) -> AuditAppendReceiptV2:
        candidate = snapshot_audit_candidate_v2(candidate)
        anchor = self._anchor()
        with anchor.lock:
            return self._append_locked(candidate)

    def _append_locked(self, candidate: AuditEventCandidateV2) -> AuditAppendReceiptV2:
        connection = self._connect(verify=False)
        committed = False
        commit_attempted = False
        record: PersistedAuditEventV2
        try:
            connection.execute("BEGIN IMMEDIATE")
            starting_head, starting_count = self._verified_state(
                connection, check_process=True
            )
            existing_row = connection.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 WHERE authorization_command_id_fingerprint=?",
                (candidate.authorization.command_id_fingerprint,),
            ).fetchone()
            if existing_row is not None:
                existing = _row_record(tuple(existing_row))
                if existing.candidate != candidate:
                    self._rollback_quietly(connection)
                    _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
                self._rollback_quietly(connection)
                head, count = self._verified_state(connection, check_process=True)
                self._pin_process_state(count=count, head=head)
                return _receipt(existing, replayed=True)
            sequence = starting_count + 1
            marker_sha = _marker_sha256(candidate)
            entry_sha = audit_entry_sha256_v2(
                candidate=candidate,
                sequence=sequence,
                previous_entry_sha256=starting_head,
                atomic_marker_sha256=marker_sha,
            )
            record = PersistedAuditEventV2(
                candidate=candidate,
                sequence=sequence,
                previous_entry_sha256=starting_head,
                entry_sha256=entry_sha,
                atomic_marker_sha256=marker_sha,
            )
            connection.execute(
                "INSERT INTO audit_atomic_marker_v2(sequence,authorization_command_id_fingerprint,event_id,request_sha256,marker_sha256) VALUES (?,?,?,?,?)",
                (
                    sequence,
                    candidate.authorization.command_id_fingerprint,
                    str(candidate.event_id),
                    candidate.request_sha256,
                    marker_sha,
                ),
            )
            if self._faults.consume(RecordedAuditFaultV2.AFTER_MARKER_BEFORE_EVENT):
                raise _KnownRollback()
            values = _row_values(record)
            connection.execute(
                "INSERT INTO audit_event_v2(sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*values, _record_sha256(values)),
            )
            updated = connection.execute(
                "UPDATE audit_metadata_v2 SET event_count=?,event_head_sha256=?,record_sha256=? WHERE singleton=1 AND schema_version=? AND schema_sha256=? AND event_count=? AND event_head_sha256=? AND record_sha256=?",
                (
                    sequence,
                    entry_sha,
                    _metadata_sha256(count=sequence, head=entry_sha),
                    AUDIT_RUNTIME_SCHEMA_VERSION_V2,
                    _SCHEMA_SHA256,
                    starting_count,
                    starting_head,
                    _metadata_sha256(count=starting_count, head=starting_head),
                ),
            )
            if updated.rowcount != 1:
                self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.CONCURRENCY_CONFLICT)
            appended_head, appended_count = self._verified_state(
                connection, check_process=True
            )
            if appended_count != sequence or appended_head != entry_sha:
                self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            self._validate_database_identity()
            commit_attempted = True
            if self._faults.consume(RecordedAuditFaultV2.BEFORE_COMMIT):
                raise _InjectedCommitFailure("ST0405_INJECTED_COMMIT_FAILURE")
            connection.execute("COMMIT")
            committed = True
            if self._faults.consume(RecordedAuditFaultV2.AFTER_COMMIT):
                raise _InjectedCommitFailure("ST0405_INJECTED_COMMIT_FAILURE")
            self._validate_database_identity()
        except _KnownRollback:
            self._rollback_quietly(connection)
            _fail(AuditRuntimeFailureCodeV2.STORAGE_ROLLED_BACK)
        except AuditRuntimeFailureV2:
            if connection.in_transaction:
                self._rollback_quietly(connection)
            raise
        except sqlite3.Error:
            if not commit_attempted:
                self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            if connection.in_transaction:
                self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORAGE_ROLLED_BACK)
            _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
        finally:
            self._close_safely(connection)
        if not committed:
            _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
        verification = self._connect(verify=False)
        try:
            head, count = self._begin_verified_snapshot(verification)
            if count < record.sequence:
                _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            row = verification.execute(
                "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 WHERE event_id=?",
                (str(candidate.event_id),),
            ).fetchone()
            if row is None or _row_record(tuple(row)) != record:
                _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            if count == record.sequence and head != record.entry_sha256:
                _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            self._commit_verified_snapshot(verification, head=head, count=count)
            return _receipt(record, replayed=False)
        except AuditRuntimeFailureV2:
            if verification.in_transaction:
                self._rollback_quietly(verification)
            raise
        except sqlite3.Error:
            if verification.in_transaction:
                self._rollback_quietly(verification)
            _fail(AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
        finally:
            self._close_safely(verification)

    def recover_exact(self, candidate: AuditEventCandidateV2) -> AuditAppendReceiptV2:
        candidate = snapshot_audit_candidate_v2(candidate)
        record = self.lookup_authorization(candidate.authorization)
        if record is None:
            _fail(AuditRuntimeFailureCodeV2.RECOVERY_NOT_FOUND)
        if record.candidate != candidate:
            _fail(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
        return _receipt(record, replayed=True)

    def load_exact(self, event_id: UUID) -> PersistedAuditEventV2 | None:
        if type(event_id) is not UUID or event_id.int == 0:
            _fail(AuditRuntimeFailureCodeV2.INVALID_ARGUMENT)
        anchor = self._anchor()
        with anchor.lock:
            connection = self._connect(verify=False)
            try:
                head, count = self._begin_verified_snapshot(connection)
                row = connection.execute(
                    "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 WHERE event_id=?",
                    (str(event_id),),
                ).fetchone()
                record = None if row is None else _row_record(tuple(row))
                self._commit_verified_snapshot(connection, head=head, count=count)
                return record
            except AuditRuntimeFailureV2:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                raise
            except sqlite3.Error:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            finally:
                self._close_safely(connection)

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
        anchor = self._anchor()
        with anchor.lock:
            connection = self._connect(verify=False)
            try:
                head, count = self._begin_verified_snapshot(connection)
                rows = connection.execute(
                    "SELECT sequence,event_id,authorization_command_id_fingerprint,authorization_request_digest,authorization_session_fingerprint,authorization_audit_digest,request_sha256,correlation_id,candidate_json,previous_entry_sha256,entry_sha256,atomic_marker_sha256,record_sha256 FROM audit_event_v2 WHERE correlation_id=? ORDER BY sequence LIMIT ?",
                    (str(correlation_id), limit),
                ).fetchall()
                records = tuple(_row_record(tuple(row)) for row in rows)
                self._commit_verified_snapshot(connection, head=head, count=count)
                return records
            except AuditRuntimeFailureV2:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                raise
            except sqlite3.Error:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            finally:
                self._close_safely(connection)

    def verify_chain(self) -> tuple[str, int]:
        anchor = self._anchor()
        with anchor.lock:
            connection = self._connect(verify=False)
            try:
                head, count = self._begin_verified_snapshot(connection)
                self._commit_verified_snapshot(connection, head=head, count=count)
                return head, count
            except AuditRuntimeFailureV2:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                raise
            except sqlite3.Error:
                if connection.in_transaction:
                    self._rollback_quietly(connection)
                _fail(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            finally:
                self._close_safely(connection)


__all__ = [
    "RecordedAuditFaultV2",
    "RecordedSqliteAuditRuntimeStoreFactoryV2",
    "RecordedSqliteAuditRuntimeStoreV2",
]
