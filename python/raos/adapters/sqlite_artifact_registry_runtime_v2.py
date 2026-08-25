"""Owner-private SQLite object byte store and registry for ST-0601 V2.

SQLite is used only as a deterministic recorded-local object-store adapter.
It is not an S3/SeaweedFS attestation and has no live provider or retention
surface.  Object rows and command rows are append-only and hash bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import Lock
from typing import NoReturn, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2,
    ARTIFACT_REGISTRY_GENESIS_SHA256_V2,
    ARTIFACT_REGISTRY_SCHEMA_VERSION_V2,
    ArtifactPutCandidateV2,
    ArtifactPutCommandV2,
    ArtifactPutReceiptV2,
    ArtifactReadbackV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
    ArtifactSourceProvenanceV2,
    PersistedArtifactV2,
    RecordedLocalArtifactRefV2,
    artifact_entry_sha256_v2,
    artifact_id_v2,
    artifact_record_sha256_v2,
    canonical_sha256_v2,
    fail_artifact_registry_runtime_v2,
    utc_text_v2,
)
from raos.domain.ops.enums import ObjectArtifactArtifactKind
from raos.domain.ops.ids import ObjectArtifactId


_DATABASE_NAME = "st0601-recorded-artifact-registry-v2.sqlite3"
_TABLES = frozenset(
    {
        "artifact_registry_metadata_v2",
        "artifact_object_v2",
        "artifact_operation_v2",
    }
)
_TRIGGERS = frozenset(
    {
        "artifact_registry_metadata_v2_no_update",
        "artifact_registry_metadata_v2_no_delete",
        "artifact_object_v2_no_update",
        "artifact_object_v2_no_delete",
        "artifact_operation_v2_no_update",
        "artifact_operation_v2_no_delete",
    }
)
_METADATA_COLUMNS = (
    (0, "singleton", "INTEGER", 0, None, 1),
    (1, "schema_version", "TEXT", 1, None, 0),
    (2, "schema_sha256", "TEXT", 1, None, 0),
)
_OBJECT_COLUMNS = (
    (0, "sequence", "INTEGER", 0, None, 1),
    (1, "artifact_id", "TEXT", 1, None, 0),
    (2, "display_id", "TEXT", 1, None, 0),
    (3, "source_receipt_id", "TEXT", 1, None, 0),
    (4, "logical_key", "TEXT", 1, None, 0),
    (5, "artifact_version", "INTEGER", 1, None, 0),
    (6, "candidate_json", "TEXT", 1, None, 0),
    (7, "candidate_sha256", "TEXT", 1, None, 0),
    (8, "content_sha256", "TEXT", 1, None, 0),
    (9, "byte_size", "INTEGER", 1, None, 0),
    (10, "body", "BLOB", 1, None, 0),
    (11, "ref_sha256", "TEXT", 1, None, 0),
    (12, "previous_entry_sha256", "TEXT", 1, None, 0),
    (13, "entry_sha256", "TEXT", 1, None, 0),
    (14, "record_sha256", "TEXT", 1, None, 0),
)
_OPERATION_COLUMNS = (
    (0, "operation_id", "TEXT", 0, None, 1),
    (1, "request_sha256", "TEXT", 1, None, 0),
    (2, "artifact_id", "TEXT", 1, None, 0),
    (3, "artifact_version", "INTEGER", 1, None, 0),
    (4, "sequence", "INTEGER", 1, None, 0),
    (5, "receipt_sha256", "TEXT", 1, None, 0),
)
_EXPECTED_COLUMNS = {
    "artifact_registry_metadata_v2": _METADATA_COLUMNS,
    "artifact_object_v2": _OBJECT_COLUMNS,
    "artifact_operation_v2": _OPERATION_COLUMNS,
}
_TABLE_SQL = {
    "artifact_registry_metadata_v2": """CREATE TABLE artifact_registry_metadata_v2 (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version TEXT NOT NULL,
        schema_sha256 TEXT NOT NULL
    )""",
    "artifact_object_v2": """CREATE TABLE artifact_object_v2 (
        sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
        artifact_id TEXT NOT NULL UNIQUE,
        display_id TEXT NOT NULL UNIQUE,
        source_receipt_id TEXT NOT NULL UNIQUE,
        logical_key TEXT NOT NULL,
        artifact_version INTEGER NOT NULL CHECK (artifact_version >= 1),
        candidate_json TEXT NOT NULL,
        candidate_sha256 TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        byte_size INTEGER NOT NULL CHECK (byte_size >= 1),
        body BLOB NOT NULL,
        ref_sha256 TEXT NOT NULL,
        previous_entry_sha256 TEXT NOT NULL,
        entry_sha256 TEXT NOT NULL,
        record_sha256 TEXT NOT NULL,
        UNIQUE (logical_key, artifact_version)
    )""",
    "artifact_operation_v2": """CREATE TABLE artifact_operation_v2 (
        operation_id TEXT PRIMARY KEY,
        request_sha256 TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        artifact_version INTEGER NOT NULL CHECK (artifact_version >= 1),
        sequence INTEGER NOT NULL CHECK (sequence >= 1),
        receipt_sha256 TEXT NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES artifact_object_v2(artifact_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    )""",
}


def _normalized_schema_sql(value: str) -> str:
    return " ".join(value.split())


def _trigger_sql(table: str, operation: str, *, if_not_exists: bool) -> str:
    qualifier = " IF NOT EXISTS" if if_not_exists else ""
    return (
        f"CREATE TRIGGER{qualifier} {table}_no_{operation} "
        f"BEFORE {operation.upper()} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ST0601_V2'); END"
    )


_EXPECTED_TRIGGER_SQL = {
    f"{table}_no_{operation}": _normalized_schema_sql(
        _trigger_sql(table, operation, if_not_exists=False)
    )
    for table in _TABLES
    for operation in ("update", "delete")
}
_SCHEMA_SHA256 = canonical_sha256_v2(
    {
        "schema_version": ARTIFACT_REGISTRY_SCHEMA_VERSION_V2,
        "tables": {
            key: list(value) for key, value in sorted(_EXPECTED_COLUMNS.items())
        },
        "table_sql": {
            key: _normalized_schema_sql(value)
            for key, value in sorted(_TABLE_SQL.items())
        },
        "trigger_sql": dict(sorted(_EXPECTED_TRIGGER_SQL.items())),
        "triggers": sorted(_TRIGGERS),
        "constraints": [
            "append-only-metadata-object-operation",
            "artifact-id-display-id-source-receipt-unique",
            "logical-key-version-unique",
            "operation-idempotency",
            "operation-to-artifact-restrict",
            "global-object-hash-chain",
        ],
    }
)
_SCHEMA_INITIALIZATION_LOCK = Lock()


class RecordedArtifactRegistryFaultV2(str, Enum):
    AFTER_OBJECT_BEFORE_OPERATION = "AFTER_OBJECT_BEFORE_OPERATION"
    AFTER_COMMIT = "AFTER_COMMIT"


class _KnownRollback(RuntimeError):
    __slots__ = ()


@dataclass(slots=True)
class _FaultController:
    fault: RecordedArtifactRegistryFaultV2 | None
    lock: Lock

    def consume(self, point: RecordedArtifactRegistryFaultV2) -> bool:
        with self.lock:
            if self.fault is point:
                self.fault = None
                return True
            return False


def _fail(code: ArtifactRegistryRuntimeFailureCodeV2) -> NoReturn:
    fail_artifact_registry_runtime_v2(code)


def _recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
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
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    if not encoded or len(encoded.encode("ascii")) > 32 * 1024:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return encoded


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[object, object]:
    if type(value) is not dict:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys or any(type(key) is not str for key in mapping):
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return mapping


def _text(mapping: dict[object, object], key: str) -> str:
    value = mapping[key]
    if type(value) is not str:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return value


def _integer(mapping: dict[object, object], key: str) -> int:
    value = mapping[key]
    if type(value) is not int:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return value


def _uuid_text(value: object) -> UUID:
    if type(value) is not str:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed = UUID(value)
    except ValueError:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    if parsed.int == 0 or str(parsed) != value:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return parsed


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    if parsed.tzinfo is not timezone.utc or utc_text_v2(parsed) != value:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return parsed


_CANDIDATE_KEYS = frozenset(
    {
        "artifact_kind",
        "byte_size",
        "content_type",
        "logical_key",
        "provenance",
        "sha256",
    }
)
_PROVENANCE_KEYS = frozenset(
    {
        "acquired_at",
        "source_artifact_sha256",
        "source_artifact_version",
        "source_logical_key",
        "source_page",
        "source_receipt_id",
        "source_request_fingerprint",
        "source_system",
    }
)


def _candidate_text(candidate: ArtifactPutCandidateV2) -> str:
    if type(candidate) is not ArtifactPutCandidateV2:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return _canonical_text(candidate.canonical_material)


def _candidate_from_text(value: object) -> ArtifactPutCandidateV2:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 32 * 1024:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError, UnicodeError:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    candidate_row = _exact_mapping(parsed, _CANDIDATE_KEYS)
    if _canonical_text(candidate_row) != value:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    provenance_row = _exact_mapping(candidate_row["provenance"], _PROVENANCE_KEYS)
    try:
        kind = ObjectArtifactArtifactKind(_text(candidate_row, "artifact_kind"))
    except ValueError:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    invalid = False
    candidate: ArtifactPutCandidateV2 | None = None
    try:
        provenance = ArtifactSourceProvenanceV2(
            source_system=_text(provenance_row, "source_system"),
            source_receipt_id=_uuid_text(provenance_row["source_receipt_id"]),
            source_artifact_sha256=_text(provenance_row, "source_artifact_sha256"),
            source_artifact_version=_integer(provenance_row, "source_artifact_version"),
            source_logical_key=_text(provenance_row, "source_logical_key"),
            source_request_fingerprint=_text(
                provenance_row, "source_request_fingerprint"
            ),
            source_page=_integer(provenance_row, "source_page"),
            acquired_at=_parse_utc(provenance_row["acquired_at"]),
        )
        candidate = ArtifactPutCandidateV2(
            artifact_kind=kind,
            logical_key=_text(candidate_row, "logical_key"),
            content_type=_text(candidate_row, "content_type"),
            byte_size=_integer(candidate_row, "byte_size"),
            sha256=_text(candidate_row, "sha256"),
            provenance=provenance,
        )
    except Exception:
        invalid = True
    if invalid or candidate is None or _candidate_text(candidate) != value:
        _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
    return candidate


def _receipt_sha256(
    *,
    operation_id: UUID,
    request_sha256: str,
    record: PersistedArtifactV2,
) -> str:
    return canonical_sha256_v2(
        {
            "artifact_id": str(record.artifact_id.value),
            "artifact_version": record.artifact_version,
            "entry_sha256": record.entry_sha256,
            "operation_id": str(operation_id),
            "request_sha256": request_sha256,
            "sequence": record.sequence,
        }
    )


@final
class RecordedSqliteArtifactRegistryFactoryV2:
    """Factory for a fixed-path owner-private recorded-local store."""

    __slots__ = (
        "_environment",
        "_faults",
        "_lock",
        "_open_count",
        "_private_root",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
    ) -> None:
        self._environment = _recorded_environment(environment)
        self._private_root = private_root
        self._faults = _FaultController(fault=None, lock=Lock())
        self._lock = Lock()
        self._open_count = 0

    @property
    def external_action_count(self) -> int:
        return ARTIFACT_REGISTRY_EXTERNAL_ACTION_COUNT_V2

    @property
    def open_count(self) -> int:
        with self._lock:
            return self._open_count

    @property
    def database_path(self) -> Path:
        return self._private_root / _DATABASE_NAME

    def set_fault(self, fault: RecordedArtifactRegistryFaultV2 | None) -> None:
        if fault is not None and type(fault) is not RecordedArtifactRegistryFaultV2:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT)
        with self._faults.lock:
            self._faults.fault = fault

    def open(self) -> RecordedSqliteArtifactRegistryStoreV2:
        with self._lock:
            self._open_count += 1
        return RecordedSqliteArtifactRegistryStoreV2(
            environment=self._environment,
            private_root=self._private_root,
            faults=self._faults,
        )


@final
class RecordedSqliteArtifactRegistryStoreV2:
    """Append-only SQLite registry with exact-version BLOB readback."""

    __slots__ = (
        "_database_was_created",
        "_database_identity",
        "_database_path",
        "_environment",
        "_faults",
        "_private_root",
    )

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
        self._database_identity: tuple[int, int] | None = None
        self._database_was_created = False
        with _SCHEMA_INITIALIZATION_LOCK:
            self._database_was_created = self._create_or_validate_database_file()
            metadata = self._validate_database_file()
            self._database_identity = (metadata.st_dev, metadata.st_ino)
            self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        root = Path(os.path.abspath(value))
        try:
            metadata = root.lstat()
        except OSError:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current = current / component
                item = current.lstat()
                if stat.S_ISLNK(item.st_mode) or not stat.S_ISDIR(item.st_mode):
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        except OSError:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        return root

    def _validate_database_file(self) -> os.stat_result:
        self._validate_private_root(self._private_root)
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (
                self._database_identity is not None
                and (metadata.st_dev, metadata.st_ino) != self._database_identity
            )
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        return metadata

    def _create_or_validate_database_file(self) -> bool:
        root_fd = -1
        descriptor = -1
        created = False
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
                created = True
                os.fsync(descriptor)
                os.fsync(root_fd)
            except FileExistsError:
                pass
        except OSError:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_fd >= 0:
                os.close(root_fd)
        self._validate_database_file()
        return created

    def _raw_connect(self) -> sqlite3.Connection:
        self._validate_database_file()
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=2.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            if journal_mode is None or tuple(journal_mode) != ("delete",):
                connection.close()
                _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or tuple(foreign_keys) != (1,):
                connection.close()
                _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            self._validate_database_file()
            return connection
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    def _connect(self) -> sqlite3.Connection:
        connection = self._raw_connect()
        try:
            self._validate_schema(connection)
            return connection
        except Exception:
            connection.close()
            raise

    def _initialize_or_validate_schema(self) -> None:
        connection = self._raw_connect()
        if not self._database_was_created:
            try:
                self._validate_schema(connection)
                return
            finally:
                connection.close()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            for sql in _TABLE_SQL.values():
                connection.execute(sql)
            for table in (
                "artifact_registry_metadata_v2",
                "artifact_object_v2",
                "artifact_operation_v2",
            ):
                for operation in ("update", "delete"):
                    connection.execute(
                        _trigger_sql(table, operation, if_not_exists=False)
                    )
            row = connection.execute(
                "SELECT singleton, schema_version, schema_sha256 FROM artifact_registry_metadata_v2"
            ).fetchall()
            if not row:
                connection.execute(
                    "INSERT INTO artifact_registry_metadata_v2(singleton, schema_version, schema_sha256) VALUES (1, ?, ?)",
                    (ARTIFACT_REGISTRY_SCHEMA_VERSION_V2, _SCHEMA_SHA256),
                )
            connection.execute("COMMIT")
            self._validate_schema(connection)
        except ArtifactRegistryRuntimeFailureV2:
            self._rollback_quietly(connection)
            raise
        except sqlite3.Error:
            self._rollback_quietly(connection)
            _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
        finally:
            connection.close()

    @staticmethod
    def _rollback_quietly(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                if not cast(str, row[0]).startswith("sqlite_")
            }
            triggers = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
            }
            table_sql = {
                cast(str, row[0]): _normalized_schema_sql(row[1])
                for row in connection.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                if not cast(str, row[0]).startswith("sqlite_") and type(row[1]) is str
            }
            trigger_sql = {
                cast(str, row[0]): _normalized_schema_sql(row[1])
                for row in connection.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
                if type(row[1]) is str
            }
            explicit_indexes = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
            ).fetchall()
            views = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            ).fetchall()
            if (
                frozenset(tables) != _TABLES
                or frozenset(triggers) != _TRIGGERS
                or table_sql
                != {
                    key: _normalized_schema_sql(value)
                    for key, value in _TABLE_SQL.items()
                }
                or trigger_sql != _EXPECTED_TRIGGER_SQL
                or explicit_indexes
                or views
            ):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
            for table, expected in _EXPECTED_COLUMNS.items():
                actual = tuple(
                    tuple(row)
                    for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if actual != expected:
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
            unique_sets = {
                tuple(
                    cast(str, info[2])
                    for info in connection.execute(f"PRAGMA index_info('{row[1]}')")
                )
                for row in connection.execute("PRAGMA index_list('artifact_object_v2')")
                if row[2] == 1
            }
            if unique_sets != {
                ("artifact_id",),
                ("display_id",),
                ("source_receipt_id",),
                ("logical_key", "artifact_version"),
            }:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
            foreign_keys = tuple(
                tuple(row)
                for row in connection.execute(
                    "PRAGMA foreign_key_list('artifact_operation_v2')"
                )
            )
            if len(foreign_keys) != 1 or foreign_keys[0][2:8] != (
                "artifact_object_v2",
                "artifact_id",
                "artifact_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
            metadata = connection.execute(
                "SELECT singleton, schema_version, schema_sha256 FROM artifact_registry_metadata_v2"
            ).fetchall()
            if len(metadata) != 1 or tuple(metadata[0]) != (
                1,
                ARTIFACT_REGISTRY_SCHEMA_VERSION_V2,
                _SCHEMA_SHA256,
            ):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except sqlite3.Error:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT)

    @staticmethod
    def _row_for_artifact(
        connection: sqlite3.Connection, artifact_id: str
    ) -> sqlite3.Row | None:
        row = connection.execute(
            "SELECT * FROM artifact_object_v2 WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is not None and type(row) is not sqlite3.Row:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        return row

    @staticmethod
    def _record_from_row(row: object) -> PersistedArtifactV2:
        if type(row) is not sqlite3.Row or tuple(row.keys()) != tuple(
            value[1] for value in _OBJECT_COLUMNS
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        candidate = _candidate_from_text(row["candidate_json"])
        try:
            artifact_uuid = _uuid_text(row["artifact_id"])
            artifact_id = ObjectArtifactId(artifact_uuid)
            artifact_version = row["artifact_version"]
            if type(artifact_version) is not int:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            artifact_ref = RecordedLocalArtifactRefV2.issue(
                artifact_id=artifact_id,
                object_key=candidate.logical_key,
                object_version=artifact_version,
                sha256=candidate.sha256,
            )
            record = PersistedArtifactV2(
                candidate=candidate,
                artifact_id=artifact_id,
                display_id=cast(str, row["display_id"]),
                artifact_ref=artifact_ref,
                sequence=cast(int, row["sequence"]),
                previous_entry_sha256=cast(str, row["previous_entry_sha256"]),
                entry_sha256=cast(str, row["entry_sha256"]),
                record_sha256=cast(str, row["record_sha256"]),
            )
        except ArtifactRegistryRuntimeFailureV2:
            raise
        except Exception:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        body = row["body"]
        if (
            type(body) is not bytes
            or type(row["source_receipt_id"]) is not str
            or row["source_receipt_id"] != str(candidate.provenance.source_receipt_id)
            or row["logical_key"] != candidate.logical_key
            or row["candidate_sha256"] != candidate.fingerprint
            or row["content_sha256"] != candidate.sha256
            or row["byte_size"] != candidate.byte_size
            or row["ref_sha256"] != artifact_ref.ref_sha256
            or len(body) != candidate.byte_size
            or hashlib.sha256(body).hexdigest() != candidate.sha256
            or artifact_id
            != artifact_id_v2(candidate=candidate, artifact_version=artifact_version)
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        return record

    @classmethod
    def _receipt_from_operation(
        cls,
        row: object,
        *,
        record: PersistedArtifactV2,
        replayed: bool,
    ) -> ArtifactPutReceiptV2:
        if type(row) is not sqlite3.Row or tuple(row.keys()) != tuple(
            value[1] for value in _OPERATION_COLUMNS
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        operation_id = _uuid_text(row["operation_id"])
        request_sha256 = row["request_sha256"]
        if type(request_sha256) is not str:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        expected_receipt = _receipt_sha256(
            operation_id=operation_id,
            request_sha256=request_sha256,
            record=record,
        )
        if (
            row["artifact_id"] != str(record.artifact_id.value)
            or row["artifact_version"] != record.artifact_version
            or row["sequence"] != record.sequence
            or row["receipt_sha256"] != expected_receipt
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
        return ArtifactPutReceiptV2(
            operation_id=operation_id,
            request_sha256=request_sha256,
            artifact_id=record.artifact_id,
            artifact_ref=record.artifact_ref,
            sequence=record.sequence,
            entry_sha256=record.entry_sha256,
            replayed=replayed,
        )

    def append(
        self, *, command: ArtifactPutCommandV2, content: bytes
    ) -> ArtifactPutReceiptV2:
        if type(command) is not ArtifactPutCommandV2 or type(content) is not bytes:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT)
        invalid = False
        try:
            command.__post_init__()
            command.candidate.__post_init__()
        except Exception:
            invalid = True
        if (
            invalid
            or len(content) != command.candidate.byte_size
            or hashlib.sha256(content).hexdigest() != command.candidate.sha256
        ):
            _fail(ArtifactRegistryRuntimeFailureCodeV2.SOURCE_INTEGRITY)
        connection = self._connect()
        commit_started = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            operation_row = connection.execute(
                "SELECT * FROM artifact_operation_v2 WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if operation_row is not None:
                artifact_row = self._row_for_artifact(
                    connection, cast(str, operation_row["artifact_id"])
                )
                if artifact_row is None:
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
                record = self._record_from_row(artifact_row)
                receipt = self._receipt_from_operation(
                    operation_row, record=record, replayed=True
                )
                if (
                    receipt.request_sha256 != command.request_sha256
                    or record.candidate != command.candidate
                ):
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
                connection.execute("COMMIT")
                return receipt

            source_row = connection.execute(
                "SELECT * FROM artifact_object_v2 WHERE source_receipt_id = ?",
                (str(command.candidate.provenance.source_receipt_id),),
            ).fetchone()
            if source_row is not None:
                record = self._record_from_row(source_row)
                original_expected = (
                    None
                    if record.artifact_version == 1
                    else record.artifact_version - 1
                )
                if (
                    record.candidate != command.candidate
                    or command.expected_latest_version != original_expected
                ):
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
                self._insert_operation(connection, command=command, record=record)
                operation_row = connection.execute(
                    "SELECT * FROM artifact_operation_v2 WHERE operation_id = ?",
                    (str(command.operation_id),),
                ).fetchone()
                if operation_row is None:
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
                receipt = self._receipt_from_operation(
                    operation_row, record=record, replayed=True
                )
                commit_started = True
                connection.execute("COMMIT")
                if self._faults.consume(RecordedArtifactRegistryFaultV2.AFTER_COMMIT):
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.COMMIT_UNKNOWN)
                return receipt

            current_row = connection.execute(
                "SELECT MAX(artifact_version) FROM artifact_object_v2 WHERE logical_key = ?",
                (command.candidate.logical_key,),
            ).fetchone()
            current = (
                0 if current_row is None or current_row[0] is None else current_row[0]
            )
            if type(current) is not int:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            expected = command.expected_latest_version
            if (expected is None and current != 0) or (
                expected is not None and current != expected
            ):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.CONCURRENCY_CONFLICT)
            artifact_version = current + 1
            tail_row = connection.execute(
                "SELECT sequence, entry_sha256 FROM artifact_object_v2 ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = 1 if tail_row is None else cast(int, tail_row["sequence"]) + 1
            previous = (
                ARTIFACT_REGISTRY_GENESIS_SHA256_V2
                if tail_row is None
                else cast(str, tail_row["entry_sha256"])
            )
            artifact_id = artifact_id_v2(
                candidate=command.candidate,
                artifact_version=artifact_version,
            )
            display_id = f"OBJ-{artifact_id.value.hex[:20].upper()}"
            artifact_ref = RecordedLocalArtifactRefV2.issue(
                artifact_id=artifact_id,
                object_key=command.candidate.logical_key,
                object_version=artifact_version,
                sha256=command.candidate.sha256,
            )
            entry_sha256 = artifact_entry_sha256_v2(
                candidate=command.candidate,
                artifact_id=artifact_id,
                display_id=display_id,
                artifact_ref=artifact_ref,
                sequence=sequence,
                previous_entry_sha256=previous,
            )
            record_sha256 = artifact_record_sha256_v2(
                candidate=command.candidate,
                artifact_id=artifact_id,
                display_id=display_id,
                artifact_ref=artifact_ref,
                sequence=sequence,
                entry_sha256=entry_sha256,
            )
            record = PersistedArtifactV2(
                candidate=command.candidate,
                artifact_id=artifact_id,
                display_id=display_id,
                artifact_ref=artifact_ref,
                sequence=sequence,
                previous_entry_sha256=previous,
                entry_sha256=entry_sha256,
                record_sha256=record_sha256,
            )
            connection.execute(
                """INSERT INTO artifact_object_v2(
                    sequence, artifact_id, display_id, source_receipt_id,
                    logical_key, artifact_version, candidate_json,
                    candidate_sha256, content_sha256, byte_size, body,
                    ref_sha256, previous_entry_sha256, entry_sha256,
                    record_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.sequence,
                    str(record.artifact_id.value),
                    record.display_id,
                    str(record.candidate.provenance.source_receipt_id),
                    record.candidate.logical_key,
                    record.artifact_version,
                    _candidate_text(record.candidate),
                    record.candidate.fingerprint,
                    record.candidate.sha256,
                    record.candidate.byte_size,
                    content,
                    record.artifact_ref.ref_sha256,
                    record.previous_entry_sha256,
                    record.entry_sha256,
                    record.record_sha256,
                ),
            )
            if self._faults.consume(
                RecordedArtifactRegistryFaultV2.AFTER_OBJECT_BEFORE_OPERATION
            ):
                raise _KnownRollback
            self._insert_operation(connection, command=command, record=record)
            operation_row = connection.execute(
                "SELECT * FROM artifact_operation_v2 WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if operation_row is None:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            receipt = self._receipt_from_operation(
                operation_row, record=record, replayed=False
            )
            commit_started = True
            connection.execute("COMMIT")
            if self._faults.consume(RecordedArtifactRegistryFaultV2.AFTER_COMMIT):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.COMMIT_UNKNOWN)
            return receipt
        except _KnownRollback:
            self._rollback_quietly(connection)
            _fail(ArtifactRegistryRuntimeFailureCodeV2.COMMIT_KNOWN_ROLLBACK)
        except ArtifactRegistryRuntimeFailureV2:
            if connection.in_transaction:
                self._rollback_quietly(connection)
            raise
        except sqlite3.IntegrityError:
            self._rollback_quietly(connection)
            _fail(ArtifactRegistryRuntimeFailureCodeV2.CONCURRENCY_CONFLICT)
        except sqlite3.Error:
            self._rollback_quietly(connection)
            _fail(
                ArtifactRegistryRuntimeFailureCodeV2.COMMIT_UNKNOWN
                if commit_started
                else ArtifactRegistryRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        finally:
            connection.close()

    @staticmethod
    def _insert_operation(
        connection: sqlite3.Connection,
        *,
        command: ArtifactPutCommandV2,
        record: PersistedArtifactV2,
    ) -> None:
        receipt_sha256 = _receipt_sha256(
            operation_id=command.operation_id,
            request_sha256=command.request_sha256,
            record=record,
        )
        connection.execute(
            """INSERT INTO artifact_operation_v2(
                operation_id, request_sha256, artifact_id, artifact_version,
                sequence, receipt_sha256
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(command.operation_id),
                command.request_sha256,
                str(record.artifact_id.value),
                record.artifact_version,
                record.sequence,
                receipt_sha256,
            ),
        )

    def recover_exact(self, command: ArtifactPutCommandV2) -> ArtifactPutReceiptV2:
        if type(command) is not ArtifactPutCommandV2:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            operation_row = connection.execute(
                "SELECT * FROM artifact_operation_v2 WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if operation_row is None:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.RECOVERY_NOT_FOUND)
            artifact_row = self._row_for_artifact(
                connection, cast(str, operation_row["artifact_id"])
            )
            if artifact_row is None:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            record = self._record_from_row(artifact_row)
            receipt = self._receipt_from_operation(
                operation_row, record=record, replayed=True
            )
            if (
                receipt.request_sha256 != command.request_sha256
                or record.candidate != command.candidate
            ):
                _fail(ArtifactRegistryRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
            return receipt
        finally:
            connection.close()

    def load_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> PersistedArtifactV2 | None:
        if type(artifact_ref) is not RecordedLocalArtifactRefV2:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            row = self._row_for_artifact(
                connection, str(artifact_ref.artifact_id.value)
            )
            if row is None:
                return None
            record = self._record_from_row(row)
            if record.artifact_ref != artifact_ref:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            return record
        finally:
            connection.close()

    def read_exact(
        self, artifact_ref: RecordedLocalArtifactRefV2
    ) -> ArtifactReadbackV2:
        if type(artifact_ref) is not RecordedLocalArtifactRefV2:
            _fail(ArtifactRegistryRuntimeFailureCodeV2.INVALID_ARGUMENT)
        connection = self._connect()
        try:
            row = self._row_for_artifact(
                connection, str(artifact_ref.artifact_id.value)
            )
            if row is None:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            record = self._record_from_row(row)
            if record.artifact_ref != artifact_ref or type(row["body"]) is not bytes:
                _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
            return ArtifactReadbackV2(record=record, content=bytes(row["body"]))
        finally:
            connection.close()

    def verify_chain(self) -> tuple[str, int]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM artifact_object_v2 ORDER BY sequence"
            ).fetchall()
            previous = ARTIFACT_REGISTRY_GENESIS_SHA256_V2
            for expected_sequence, row in enumerate(rows, start=1):
                record = self._record_from_row(row)
                if (
                    record.sequence != expected_sequence
                    or record.previous_entry_sha256 != previous
                ):
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
                previous = record.entry_sha256
            operations = connection.execute(
                "SELECT * FROM artifact_operation_v2 ORDER BY operation_id"
            ).fetchall()
            for operation in operations:
                artifact_row = self._row_for_artifact(
                    connection, cast(str, operation["artifact_id"])
                )
                if artifact_row is None:
                    _fail(ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED)
                self._receipt_from_operation(
                    operation,
                    record=self._record_from_row(artifact_row),
                    replayed=True,
                )
            return previous, len(rows)
        finally:
            connection.close()


__all__ = [
    "RecordedArtifactRegistryFaultV2",
    "RecordedSqliteArtifactRegistryFactoryV2",
    "RecordedSqliteArtifactRegistryStoreV2",
]
