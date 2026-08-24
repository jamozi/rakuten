"""Owner-private append-only SQLite journal for ST-1604 local reports."""

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
from uuid import UUID

from raos.domain.ops.performance_load import (
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    PerformanceLoadReport,
    fail_performance_load,
)
from raos.ports.performance_load import (
    PerformanceLoadReceipt,
    PerformanceLoadWriteDisposition,
)


_DATABASE_NAME: Final = "st1604-local-performance-load.sqlite3"
_SCHEMA_VERSION: Final = "ST1604_LOCAL_PERFORMANCE_LOAD_V2"
_USER_VERSION: Final = 160402
_GENESIS: Final = "0" * 64

_CREATE_METADATA: Final = """CREATE TABLE st1604_metadata_v2 (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL,
    report_count INTEGER NOT NULL CHECK (report_count >= 0),
    report_head_sha256 TEXT NOT NULL CHECK (length(report_head_sha256) = 64),
    record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64)
)"""
_CREATE_REPORT: Final = """CREATE TABLE st1604_report_v2 (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    run_id TEXT NOT NULL UNIQUE,
    report_sha256 TEXT NOT NULL CHECK (length(report_sha256) = 64),
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    observed_at TEXT NOT NULL,
    report_status TEXT NOT NULL,
    evidence_source TEXT NOT NULL,
    canonical_report BLOB NOT NULL CHECK (length(canonical_report) > 0),
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64)
)"""
_CREATE_REPORT_NO_UPDATE: Final = """CREATE TRIGGER st1604_report_no_update_v2
BEFORE UPDATE ON st1604_report_v2 BEGIN SELECT RAISE(ABORT, 'append-only'); END"""
_CREATE_REPORT_NO_DELETE: Final = """CREATE TRIGGER st1604_report_no_delete_v2
BEFORE DELETE ON st1604_report_v2 BEGIN SELECT RAISE(ABORT, 'append-only'); END"""
_CREATE_METADATA_NO_DELETE: Final = """CREATE TRIGGER st1604_metadata_no_delete_v2
BEFORE DELETE ON st1604_metadata_v2 BEGIN SELECT RAISE(ABORT, 'append-only'); END"""
_CREATE_METADATA_NO_INSERT: Final = """CREATE TRIGGER st1604_metadata_no_insert_v2
BEFORE INSERT ON st1604_metadata_v2 WHEN EXISTS (SELECT 1 FROM st1604_metadata_v2)
BEGIN SELECT RAISE(ABORT, 'singleton'); END"""

_SCHEMA_SQL: Final = {
    "st1604_metadata_v2": _CREATE_METADATA,
    "st1604_report_v2": _CREATE_REPORT,
    "st1604_report_no_update_v2": _CREATE_REPORT_NO_UPDATE,
    "st1604_report_no_delete_v2": _CREATE_REPORT_NO_DELETE,
    "st1604_metadata_no_delete_v2": _CREATE_METADATA_NO_DELETE,
    "st1604_metadata_no_insert_v2": _CREATE_METADATA_NO_INSERT,
}
_SCHEMA_OBJECTS: Final = {
    ("index", "sqlite_autoindex_st1604_report_v2_1"),
    ("index", "sqlite_autoindex_st1604_report_v2_2"),
    ("table", "st1604_metadata_v2"),
    ("table", "st1604_report_v2"),
    ("trigger", "st1604_metadata_no_delete_v2"),
    ("trigger", "st1604_metadata_no_insert_v2"),
    ("trigger", "st1604_report_no_delete_v2"),
    ("trigger", "st1604_report_no_update_v2"),
}


class PerformanceLoadCommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _InjectedCommitFault(RuntimeError):
    pass


def _fail(code: PerformanceLoadFailureCode) -> NoReturn:
    fail_performance_load(code)


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


def _metadata_digest(count: int, head: str) -> str:
    payload = json.dumps(
        {
            "report_count": count,
            "report_head_sha256": head,
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
    run_id: str,
    report_sha256: str,
    request_sha256: str,
    observed_at: str,
    report_status: str,
    evidence_source: str,
    previous_record_sha256: str,
) -> str:
    payload = json.dumps(
        {
            "evidence_source": evidence_source,
            "observed_at": observed_at,
            "previous_record_sha256": previous_record_sha256,
            "report_sha256": report_sha256,
            "report_status": report_status,
            "request_sha256": request_sha256,
            "run_id": run_id,
            "sequence": sequence,
        },
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


@final
class RecordedPerformanceLoadJournal:
    """Durable local report sink with no read/export/delete surface."""

    __slots__ = ("_commit_fault", "_database_path", "_fault_lock", "_fault_used")

    def __init__(
        self,
        *,
        private_root: Path,
        commit_fault_once: PerformanceLoadCommitFault = PerformanceLoadCommitFault.NONE,
    ) -> None:
        if type(commit_fault_once) is not PerformanceLoadCommitFault:
            _fail(PerformanceLoadFailureCode.INVALID_ARGUMENT)
        root = self._prepare_private_root(private_root)
        self._database_path = root / _DATABASE_NAME
        self._commit_fault = commit_fault_once
        self._fault_lock = Lock()
        self._fault_used = False
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @property
    def mode(self) -> str:
        return "OWNER_PRIVATE_RECORDED_LOCAL_ONLY"

    @property
    def action_count(self) -> int:
        return 0

    @staticmethod
    def _prepare_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        root = Path(os.path.abspath(value))
        if root != value or not root.exists():
            _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = os.lstat(current)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
            metadata = os.lstat(root)
        except PerformanceLoadFailure:
            raise
        except OSError:
            _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        return root

    def _create_or_validate_database_file(self) -> None:
        root = self._database_path.parent
        self._prepare_private_root(root)
        root_descriptor = -1
        descriptor = -1
        try:
            root_descriptor = os.open(
                root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=root_descriptor,
                )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        except PerformanceLoadFailure:
            raise
        except OSError:
            _fail(PerformanceLoadFailureCode.PRIVATE_PATH_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

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
            _fail(PerformanceLoadFailureCode.STORAGE_FAILED)

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
                connection.execute(_CREATE_REPORT)
                connection.execute(
                    "INSERT INTO st1604_metadata_v2 VALUES (?,?,?,?,?)",
                    (1, _SCHEMA_VERSION, 0, _GENESIS, _metadata_digest(0, _GENESIS)),
                )
                connection.execute(_CREATE_REPORT_NO_UPDATE)
                connection.execute(_CREATE_REPORT_NO_DELETE)
                connection.execute(_CREATE_METADATA_NO_DELETE)
                connection.execute(_CREATE_METADATA_NO_INSERT)
                connection.execute(f"PRAGMA user_version={_USER_VERSION}")
            self._validate_all(connection)
            connection.commit()
        except PerformanceLoadFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(PerformanceLoadFailureCode.STORAGE_FAILED)
        finally:
            connection.close()

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()
        if version is None or tuple(version) != (_USER_VERSION,):
            _fail(PerformanceLoadFailureCode.SCHEMA_DRIFT)
        rows = connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' OR type='index' ORDER BY type,name"
        ).fetchall()
        if {(str(row[0]), str(row[1])) for row in rows} != _SCHEMA_OBJECTS:
            _fail(PerformanceLoadFailureCode.SCHEMA_DRIFT)
        for row in rows:
            kind, name, sql = str(row[0]), str(row[1]), row[2]
            if kind == "index":
                if sql is not None:
                    _fail(PerformanceLoadFailureCode.SCHEMA_DRIFT)
                continue
            expected = _SCHEMA_SQL.get(name)
            if expected is None or type(sql) is not str:
                _fail(PerformanceLoadFailureCode.SCHEMA_DRIFT)
            if _normalized_sql(sql) != _normalized_sql(expected):
                _fail(PerformanceLoadFailureCode.SCHEMA_DRIFT)

    @classmethod
    def _validate_all(cls, connection: sqlite3.Connection) -> None:
        cls._validate_schema(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or tuple(integrity) != ("ok",):
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
        metadata_rows = connection.execute(
            "SELECT singleton,schema_version,report_count,report_head_sha256,"
            "record_sha256 FROM st1604_metadata_v2"
        ).fetchall()
        if len(metadata_rows) != 1:
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
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
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            "SELECT sequence,run_id,report_sha256,request_sha256,observed_at,"
            "report_status,evidence_source,canonical_report,previous_record_sha256,"
            "record_sha256 FROM st1604_report_v2 ORDER BY sequence"
        ).fetchall()
        if len(rows) != count:
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
        previous = _GENESIS
        for expected_sequence, row in enumerate(rows, start=1):
            values = tuple(row)
            canonical_report = values[7]
            if (
                values[0] != expected_sequence
                or type(canonical_report) is not bytes
                or not canonical_report
                or hashlib.sha256(canonical_report).hexdigest() != values[2]
                or values[8] != previous
                or _record_digest(
                    sequence=values[0],
                    run_id=values[1],
                    report_sha256=values[2],
                    request_sha256=values[3],
                    observed_at=values[4],
                    report_status=values[5],
                    evidence_source=values[6],
                    previous_record_sha256=values[8],
                )
                != values[9]
            ):
                _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
            previous = values[9]
        if head != previous:
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)

    def _take_fault(self) -> PerformanceLoadCommitFault:
        with self._fault_lock:
            if self._fault_used:
                return PerformanceLoadCommitFault.NONE
            self._fault_used = True
            return self._commit_fault

    @staticmethod
    def _receipt(row: sqlite3.Row, *, replayed: bool) -> PerformanceLoadReceipt:
        try:
            return PerformanceLoadReceipt(
                run_id=UUID(str(row["run_id"])),
                report_sha256=str(row["report_sha256"]),
                sequence=int(row["sequence"]),
                previous_record_sha256=str(row["previous_record_sha256"]),
                record_sha256=str(row["record_sha256"]),
                disposition=(
                    PerformanceLoadWriteDisposition.REPLAYED
                    if replayed
                    else PerformanceLoadWriteDisposition.APPENDED
                ),
            )
        except TypeError, ValueError, KeyError, IndexError:
            _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)

    def append(self, report: PerformanceLoadReport) -> PerformanceLoadReceipt:
        if type(report) is not PerformanceLoadReport:
            _fail(PerformanceLoadFailureCode.INVALID_ARGUMENT)
        canonical = report.canonical_bytes()
        report_sha = hashlib.sha256(canonical).hexdigest()
        if report_sha != report.report_sha256:
            _fail(PerformanceLoadFailureCode.INVALID_ARGUMENT)
        run_id = str(report.run_id)
        connection = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection)
            existing = connection.execute(
                "SELECT sequence,run_id,report_sha256,request_sha256,observed_at,"
                "report_status,evidence_source,canonical_report,"
                "previous_record_sha256,record_sha256 FROM st1604_report_v2 "
                "WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["report_sha256"] != report_sha
                    or existing["request_sha256"] != report.request_sha256
                    or existing["observed_at"] != report.observed_at
                    or existing["report_status"] != report.report_status.value
                    or existing["evidence_source"] != report.evidence_source.value
                    or existing["canonical_report"] != canonical
                ):
                    connection.rollback()
                    _fail(PerformanceLoadFailureCode.RUN_ID_CONFLICT)
                receipt = self._receipt(existing, replayed=True)
                connection.commit()
                return receipt
            metadata = connection.execute(
                "SELECT report_count,report_head_sha256 FROM st1604_metadata_v2 "
                "WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                _fail(PerformanceLoadFailureCode.TAMPER_DETECTED)
            sequence = int(metadata["report_count"]) + 1
            previous = str(metadata["report_head_sha256"])
            record_sha = _record_digest(
                sequence=sequence,
                run_id=run_id,
                report_sha256=report_sha,
                request_sha256=report.request_sha256,
                observed_at=report.observed_at,
                report_status=report.report_status.value,
                evidence_source=report.evidence_source.value,
                previous_record_sha256=previous,
            )
            connection.execute(
                "INSERT INTO st1604_report_v2 VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    run_id,
                    report_sha,
                    report.request_sha256,
                    report.observed_at,
                    report.report_status.value,
                    report.evidence_source.value,
                    canonical,
                    previous,
                    record_sha,
                ),
            )
            connection.execute(
                "UPDATE st1604_metadata_v2 SET report_count=?,report_head_sha256=?,"
                "record_sha256=? WHERE singleton=1",
                (sequence, record_sha, _metadata_digest(sequence, record_sha)),
            )
            self._validate_all(connection)
            fault = self._take_fault()
            if fault is PerformanceLoadCommitFault.BEFORE_COMMIT:
                raise _InjectedCommitFault("BEFORE_COMMIT")
            connection.commit()
            committed = True
            if fault is PerformanceLoadCommitFault.AFTER_COMMIT:
                raise _InjectedCommitFault("AFTER_COMMIT")
            return PerformanceLoadReceipt(
                run_id=report.run_id,
                report_sha256=report_sha,
                sequence=sequence,
                previous_record_sha256=previous,
                record_sha256=record_sha,
                disposition=PerformanceLoadWriteDisposition.APPENDED,
            )
        except _InjectedCommitFault:
            if not committed:
                connection.rollback()
                _fail(PerformanceLoadFailureCode.STORAGE_FAILED)
        except PerformanceLoadFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            _fail(PerformanceLoadFailureCode.STORAGE_FAILED)
        finally:
            connection.close()
        return self._recover_after_commit(run_id=run_id, report_sha256=report_sha)

    def _recover_after_commit(
        self, *, run_id: str, report_sha256: str
    ) -> PerformanceLoadReceipt:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection)
            row = connection.execute(
                "SELECT sequence,run_id,report_sha256,previous_record_sha256,"
                "record_sha256 FROM st1604_report_v2 WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None or row["report_sha256"] != report_sha256:
                _fail(PerformanceLoadFailureCode.COMMIT_UNKNOWN)
            receipt = self._receipt(row, replayed=False)
            connection.commit()
            return receipt
        except PerformanceLoadFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            _fail(PerformanceLoadFailureCode.COMMIT_UNKNOWN)
        finally:
            connection.close()


__all__ = [
    "PerformanceLoadCommitFault",
    "RecordedPerformanceLoadJournal",
]
