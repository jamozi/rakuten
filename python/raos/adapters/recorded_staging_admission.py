"""Owner-private SQLite journal for ST-1505 recorded local admission.

This adapter has no network, provider, credential, staging, deployment, or
release surface.  It persists only canonical synthetic result bytes in one
caller-created owner-private local directory.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from pathlib import Path
from threading import Lock
from typing import Final, NoReturn, final

from raos.domain.ops.staging_admission import canonical_sha256
from raos.ports.staging_admission import (
    AdmissionPersistCommand,
    AdmissionPersistReceipt,
    StagingAdmissionJournalError,
    StagingAdmissionJournalFailureCode,
)


_DATABASE_NAME: Final = "st1505-local-admission.sqlite3"
_SCHEMA_VERSION: Final = "ST1505_LOCAL_ADMISSION_JOURNAL_V2"
_ZERO_SHA256: Final = "0" * 64
_EXPECTED_TABLES: Final = frozenset(
    {"admission_metadata", "admission_run", "admission_journal"}
)
_CREATE_METADATA_SQL: Final = """CREATE TABLE IF NOT EXISTS admission_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL,
                    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
                    tail_sha256 TEXT NOT NULL
                )"""
_CREATE_RUN_SQL: Final = """CREATE TABLE IF NOT EXISTS admission_run (
                    run_id TEXT NOT NULL PRIMARY KEY,
                    idempotency_key_sha256 TEXT NOT NULL UNIQUE,
                    request_sha256 TEXT NOT NULL,
                    contract_sha256 TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    result_json BLOB NOT NULL,
                    sequence INTEGER NOT NULL UNIQUE
                )"""
_CREATE_JOURNAL_SQL: Final = """CREATE TABLE IF NOT EXISTS admission_journal (
                    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
                    previous_entry_sha256 TEXT NOT NULL,
                    entry_sha256 TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL UNIQUE,
                    idempotency_key_sha256 TEXT NOT NULL UNIQUE,
                    request_sha256 TEXT NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES admission_run(run_id)
                )"""
_EXPECTED_TABLE_SQL: Final = {
    "admission_metadata": " ".join(_CREATE_METADATA_SQL.split()).replace(
        "CREATE TABLE IF NOT EXISTS", "CREATE TABLE"
    ),
    "admission_run": " ".join(_CREATE_RUN_SQL.split()).replace(
        "CREATE TABLE IF NOT EXISTS", "CREATE TABLE"
    ),
    "admission_journal": " ".join(_CREATE_JOURNAL_SQL.split()).replace(
        "CREATE TABLE IF NOT EXISTS", "CREATE TABLE"
    ),
}
_EXPECTED_UNIQUE_INDEXES: Final[dict[str, frozenset[tuple[str, tuple[str, ...]]]]] = {
    "admission_metadata": frozenset(),
    "admission_run": frozenset(
        {
            ("pk", ("run_id",)),
            ("u", ("idempotency_key_sha256",)),
            ("u", ("sequence",)),
        }
    ),
    "admission_journal": frozenset(
        {
            ("u", ("entry_sha256",)),
            ("u", ("run_id",)),
            ("u", ("idempotency_key_sha256",)),
        }
    ),
}


def _fail(code: StagingAdmissionJournalFailureCode) -> NoReturn:
    raise StagingAdmissionJournalError(code) from None


@final
class RecordedStagingAdmissionJournal:
    """Restartable, idempotent, hash-chained synthetic local journal."""

    __slots__ = (
        "_ambiguity_lock",
        "_database_path",
        "_private_root",
        "_simulate_commit_ambiguity_once",
    )

    def __init__(
        self,
        *,
        private_root: Path,
        simulate_commit_ambiguity_once: bool = False,
    ) -> None:
        if type(simulate_commit_ambiguity_once) is not bool:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        self._private_root = self._validate_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._simulate_commit_ambiguity_once = simulate_commit_ambiguity_once
        self._ambiguity_lock = Lock()
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        normalized = Path(os.path.abspath(value))
        if value != normalized:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        cursor = Path(normalized.anchor)
        try:
            for part in normalized.parts[1:]:
                cursor = cursor / part
                metadata = cursor.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
            metadata = normalized.lstat()
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        return normalized

    def _open_private_root(self) -> int:
        self._validate_private_root(self._private_root)
        try:
            descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            metadata = os.fstat(descriptor)
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            os.close(descriptor)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        return descriptor

    @staticmethod
    def _validate_database_descriptor(descriptor: int) -> None:
        try:
            metadata = os.fstat(descriptor)
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)

    def _open_database_descriptor(self, root_descriptor: int) -> int:
        try:
            descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=root_descriptor,
            )
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        try:
            self._validate_database_descriptor(descriptor)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _create_or_validate_database_file(self) -> None:
        root_descriptor = self._open_private_root()
        descriptor = -1
        try:
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_descriptor,
                )
                self._validate_database_descriptor(descriptor)
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            except FileExistsError:
                descriptor = self._open_database_descriptor(root_descriptor)
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(root_descriptor)

    def _connect(self) -> tuple[sqlite3.Connection, int]:
        root_descriptor = self._open_private_root()
        database_descriptor = -1
        connection: sqlite3.Connection | None = None
        try:
            database_descriptor = self._open_database_descriptor(root_descriptor)
            os.close(database_descriptor)
            database_descriptor = -1
            connection = sqlite3.connect(
                f"/proc/self/fd/{root_descriptor}/{_DATABASE_NAME}",
                timeout=1.0,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            if mode != ("delete",):
                _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
            return connection, root_descriptor
        except StagingAdmissionJournalError:
            if connection is not None:
                connection.close()
            os.close(root_descriptor)
            raise
        except OSError, sqlite3.Error:
            if connection is not None:
                connection.close()
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _close(connection: sqlite3.Connection, root_descriptor: int) -> None:
        connection.close()
        os.close(root_descriptor)

    def _initialize_or_validate_schema(self) -> None:
        connection, root_descriptor = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(_CREATE_METADATA_SQL)
            connection.execute(_CREATE_RUN_SQL)
            connection.execute(_CREATE_JOURNAL_SQL)
            row = connection.execute(
                "SELECT schema_version, entry_count, tail_sha256 "
                "FROM admission_metadata WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO admission_metadata"
                    "(singleton, schema_version, entry_count, tail_sha256) "
                    "VALUES (1, ?, 0, ?)",
                    (_SCHEMA_VERSION, _ZERO_SHA256),
                )
            elif row != (_SCHEMA_VERSION, 0, _ZERO_SHA256):
                # Non-empty existing journals are verified below after commit.
                if type(row[1]) is not int or row[1] < 1:
                    _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            self._verify_integrity_in_transaction(connection)
            connection.commit()
        except StagingAdmissionJournalError:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            self._close(connection, root_descriptor)

    @staticmethod
    def _entry_sha256(
        command: AdmissionPersistCommand,
        *,
        sequence: int,
        previous_entry_sha256: str,
    ) -> str:
        return canonical_sha256(
            {
                "schema": "ST1505_LOCAL_ADMISSION_JOURNAL_ENTRY_V2",
                "sequence": sequence,
                "previous_entry_sha256": previous_entry_sha256,
                "run_id": command.run_id,
                "idempotency_key_sha256": command.idempotency_key_sha256,
                "request_sha256": command.request_sha256,
                "contract_sha256": command.contract_sha256,
                "result_sha256": command.result_sha256,
                "result_bytes_sha256": hashlib.sha256(command.result_json).hexdigest(),
            }
        )

    @staticmethod
    def _require_command(value: object) -> AdmissionPersistCommand:
        if type(value) is not AdmissionPersistCommand:
            _fail(StagingAdmissionJournalFailureCode.INVALID_COMMAND)
        return value

    @staticmethod
    def _verify_schema_in_transaction(connection: sqlite3.Connection) -> None:
        objects = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        if len(objects) != len(_EXPECTED_TABLES):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        observed_sql: dict[str, str] = {}
        for row in objects:
            if (
                len(row) != 4
                or row[0] != "table"
                or type(row[1]) is not str
                or row[2] != row[1]
                or type(row[3]) is not str
            ):
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            observed_sql[row[1]] = " ".join(row[3].split())
        if observed_sql != _EXPECTED_TABLE_SQL:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

        for table_name, expected_indexes in _EXPECTED_UNIQUE_INDEXES.items():
            rows = connection.execute(f'PRAGMA index_list("{table_name}")').fetchall()
            observed_indexes: set[tuple[str, tuple[str, ...]]] = set()
            for row in rows:
                if (
                    len(row) < 5
                    or type(row[1]) is not str
                    or not row[1].startswith(f"sqlite_autoindex_{table_name}_")
                    or row[2] != 1
                    or row[3] not in {"pk", "u"}
                    or row[4] != 0
                ):
                    _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
                index_name = row[1]
                if not index_name.removeprefix(
                    f"sqlite_autoindex_{table_name}_"
                ).isdigit():
                    _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
                columns = connection.execute(
                    f'PRAGMA index_info("{index_name}")'
                ).fetchall()
                if not columns or any(
                    len(column) < 3 or type(column[2]) is not str for column in columns
                ):
                    _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
                observed_indexes.add((row[3], tuple(column[2] for column in columns)))
            if frozenset(observed_indexes) != expected_indexes:
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

        foreign_keys = connection.execute(
            'PRAGMA foreign_key_list("admission_journal")'
        ).fetchall()
        if foreign_keys != [
            (
                0,
                0,
                "admission_run",
                "run_id",
                "run_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        ]:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        for table_name in ("admission_metadata", "admission_run"):
            if connection.execute(
                f'PRAGMA foreign_key_list("{table_name}")'
            ).fetchall():
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

    def _verify_integrity_in_transaction(self, connection: sqlite3.Connection) -> int:
        self._verify_schema_in_transaction(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        metadata = connection.execute(
            "SELECT schema_version, entry_count, tail_sha256 "
            "FROM admission_metadata WHERE singleton = 1"
        ).fetchone()
        if (
            metadata is None
            or metadata[0] != _SCHEMA_VERSION
            or type(metadata[1]) is not int
            or metadata[1] < 0
            or type(metadata[2]) is not str
        ):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            """SELECT j.sequence, j.previous_entry_sha256, j.entry_sha256,
                      j.run_id, j.idempotency_key_sha256, j.request_sha256,
                      j.result_sha256, r.run_id, r.idempotency_key_sha256,
                      r.request_sha256, r.contract_sha256, r.result_sha256,
                      r.result_json, r.sequence
               FROM admission_journal AS j
               JOIN admission_run AS r ON r.run_id = j.run_id
               ORDER BY j.sequence"""
        ).fetchall()
        if len(rows) != metadata[1]:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        run_count = connection.execute("SELECT COUNT(*) FROM admission_run").fetchone()
        if run_count != (metadata[1],):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        previous = _ZERO_SHA256
        for expected_sequence, row in enumerate(rows, start=1):
            if (
                row[0] != expected_sequence
                or row[1] != previous
                or row[13] != expected_sequence
                or row[3] != row[7]
                or row[4] != row[8]
                or row[5] != row[9]
                or row[6] != row[11]
                or type(row[12]) is not bytes
            ):
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            try:
                command = AdmissionPersistCommand(
                    run_id=row[3],
                    idempotency_key_sha256=row[4],
                    request_sha256=row[5],
                    contract_sha256=row[10],
                    result_sha256=row[6],
                    result_json=row[12],
                )
            except StagingAdmissionJournalError:
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            expected_entry = self._entry_sha256(
                command,
                sequence=expected_sequence,
                previous_entry_sha256=previous,
            )
            if row[2] != expected_entry:
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            previous = expected_entry
        if metadata[2] != previous:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        return metadata[1]

    def _find_exact(
        self,
        connection: sqlite3.Connection,
        command: AdmissionPersistCommand,
        *,
        not_found_code: StagingAdmissionJournalFailureCode,
    ) -> AdmissionPersistReceipt:
        rows = connection.execute(
            """SELECT r.run_id, r.idempotency_key_sha256, r.request_sha256,
                      r.contract_sha256, r.result_sha256, r.result_json,
                      j.sequence, j.previous_entry_sha256, j.entry_sha256
               FROM admission_run AS r
               JOIN admission_journal AS j ON j.run_id = r.run_id
               WHERE r.run_id = ? OR r.idempotency_key_sha256 = ?""",
            (command.run_id, command.idempotency_key_sha256),
        ).fetchall()
        if not rows:
            _fail(not_found_code)
        if len(rows) != 1:
            _fail(StagingAdmissionJournalFailureCode.REPLAY_CONFLICT)
        row = rows[0]
        if row[:6] != (
            command.run_id,
            command.idempotency_key_sha256,
            command.request_sha256,
            command.contract_sha256,
            command.result_sha256,
            command.result_json,
        ):
            _fail(StagingAdmissionJournalFailureCode.REPLAY_CONFLICT)
        return AdmissionPersistReceipt(
            run_id=command.run_id,
            idempotency_key_sha256=command.idempotency_key_sha256,
            request_sha256=command.request_sha256,
            result_sha256=command.result_sha256,
            sequence=row[6],
            previous_entry_sha256=row[7],
            entry_sha256=row[8],
            replayed=True,
        )

    def commit(self, command: AdmissionPersistCommand) -> AdmissionPersistReceipt:
        command = self._require_command(command)
        connection, root_descriptor = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_integrity_in_transaction(connection)
            existing = connection.execute(
                "SELECT 1 FROM admission_run "
                "WHERE run_id = ? OR idempotency_key_sha256 = ? LIMIT 1",
                (command.run_id, command.idempotency_key_sha256),
            ).fetchone()
            if existing is not None:
                receipt = self._find_exact(
                    connection,
                    command,
                    not_found_code=StagingAdmissionJournalFailureCode.REPLAY_CONFLICT,
                )
                connection.commit()
                committed = True
                return receipt
            metadata = connection.execute(
                "SELECT entry_count, tail_sha256 FROM admission_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            if (
                metadata is None
                or type(metadata[0]) is not int
                or type(metadata[1]) is not str
            ):
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            sequence = metadata[0] + 1
            previous = metadata[1]
            entry_sha256 = self._entry_sha256(
                command,
                sequence=sequence,
                previous_entry_sha256=previous,
            )
            connection.execute(
                """INSERT INTO admission_run
                   (run_id, idempotency_key_sha256, request_sha256,
                    contract_sha256, result_sha256, result_json, sequence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    command.run_id,
                    command.idempotency_key_sha256,
                    command.request_sha256,
                    command.contract_sha256,
                    command.result_sha256,
                    command.result_json,
                    sequence,
                ),
            )
            connection.execute(
                """INSERT INTO admission_journal
                   (sequence, previous_entry_sha256, entry_sha256, run_id,
                    idempotency_key_sha256, request_sha256, result_sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sequence,
                    previous,
                    entry_sha256,
                    command.run_id,
                    command.idempotency_key_sha256,
                    command.request_sha256,
                    command.result_sha256,
                ),
            )
            updated = connection.execute(
                """UPDATE admission_metadata
                   SET entry_count = ?, tail_sha256 = ?
                   WHERE singleton = 1 AND entry_count = ? AND tail_sha256 = ?""",
                (sequence, entry_sha256, metadata[0], previous),
            )
            if updated.rowcount != 1:
                _fail(StagingAdmissionJournalFailureCode.CONCURRENCY_FAILURE)
            connection.commit()
            committed = True
            receipt = AdmissionPersistReceipt(
                run_id=command.run_id,
                idempotency_key_sha256=command.idempotency_key_sha256,
                request_sha256=command.request_sha256,
                result_sha256=command.result_sha256,
                sequence=sequence,
                previous_entry_sha256=previous,
                entry_sha256=entry_sha256,
                replayed=False,
            )
            with self._ambiguity_lock:
                if self._simulate_commit_ambiguity_once:
                    self._simulate_commit_ambiguity_once = False
                    _fail(StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS)
            return receipt
        except StagingAdmissionJournalError:
            if not committed:
                connection.rollback()
            raise
        except sqlite3.IntegrityError:
            if not committed:
                connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.REPLAY_CONFLICT)
        except sqlite3.OperationalError:
            if not committed:
                connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.CONCURRENCY_FAILURE)
        except sqlite3.Error:
            if not committed:
                connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            self._close(connection, root_descriptor)

    def recover_exact(
        self, command: AdmissionPersistCommand
    ) -> AdmissionPersistReceipt:
        command = self._require_command(command)
        connection, root_descriptor = self._connect()
        try:
            connection.execute("BEGIN")
            self._verify_integrity_in_transaction(connection)
            receipt = self._find_exact(
                connection,
                command,
                not_found_code=StagingAdmissionJournalFailureCode.RECOVERY_NOT_FOUND,
            )
            connection.commit()
            return receipt
        except StagingAdmissionJournalError:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            self._close(connection, root_descriptor)

    def verify_integrity(self) -> int:
        connection, root_descriptor = self._connect()
        try:
            connection.execute("BEGIN")
            count = self._verify_integrity_in_transaction(connection)
            connection.commit()
            return count
        except StagingAdmissionJournalError:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            self._close(connection, root_descriptor)


__all__ = ["RecordedStagingAdmissionJournal"]
