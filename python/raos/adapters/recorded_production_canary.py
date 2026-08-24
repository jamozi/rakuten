"""Owner-private durable journal for ST-1506 synthetic canary steps."""

from __future__ import annotations

import os
import sqlite3
import stat
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Final, NoReturn, cast, final

from raos.domain.ops.production_canary import CanaryOutcome, CanaryState
from raos.ports.production_canary import (
    CanaryStepPersistCommand,
    CanaryStepPersistReceipt,
    PersistedCanaryStep,
    ProductionCanaryJournalError,
    ProductionCanaryJournalFailureCode,
    canary_entry_sha256,
    validate_persisted_binding,
    validated_command_transition,
    validated_persisted_transition,
)


_DATABASE_NAME: Final = "st1506-local-production-canary.sqlite3"
_SCHEMA_VERSION: Final = "ST1506_LOCAL_PRODUCTION_CANARY_JOURNAL_V2"
_ZERO_SHA256: Final = "0" * 64
_TERMINAL_STATES: Final = (
    "HOLD_FOR_HUMAN_APPROVAL",
    "ABORT_REQUIRED",
    "ROLLBACK_REQUIRED",
)

_CREATE_METADATA_SQL: Final = """CREATE TABLE IF NOT EXISTS canary_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version TEXT NOT NULL CHECK (schema_version = 'ST1506_LOCAL_PRODUCTION_CANARY_JOURNAL_V2'),
    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
    tail_sha256 TEXT NOT NULL CHECK (length(tail_sha256) = 64)
) STRICT"""
_CREATE_RUN_SQL: Final = """CREATE TABLE IF NOT EXISTS canary_run (
    run_id TEXT PRIMARY KEY NOT NULL,
    contract_sha256 TEXT NOT NULL CHECK (length(contract_sha256) = 64),
    current_version INTEGER NOT NULL CHECK (current_version >= 1),
    state TEXT NOT NULL CHECK (state IN ('OBSERVE', 'HOLD_FOR_HUMAN_APPROVAL', 'ABORT_REQUIRED', 'ROLLBACK_REQUIRED')),
    outcome TEXT NOT NULL CHECK (outcome IN ('OBSERVE_REQUIRED', 'DATA_BLOCKED', 'HUMAN_APPROVALS_REQUIRED', 'ABORT_REQUIRED', 'ROLLBACK_REQUIRED')),
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    result_json BLOB NOT NULL,
    latest_sequence INTEGER NOT NULL UNIQUE CHECK (latest_sequence >= 1),
    latest_entry_sha256 TEXT NOT NULL UNIQUE CHECK (length(latest_entry_sha256) = 64)
) STRICT"""
_CREATE_JOURNAL_SQL: Final = """CREATE TABLE IF NOT EXISTS canary_journal (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    previous_entry_sha256 TEXT NOT NULL CHECK (length(previous_entry_sha256) = 64),
    entry_sha256 TEXT NOT NULL UNIQUE CHECK (length(entry_sha256) = 64),
    run_id TEXT NOT NULL,
    idempotency_key_sha256 TEXT NOT NULL UNIQUE CHECK (length(idempotency_key_sha256) = 64),
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    contract_sha256 TEXT NOT NULL CHECK (length(contract_sha256) = 64),
    expected_version INTEGER NOT NULL CHECK (expected_version >= 0),
    current_version INTEGER NOT NULL CHECK (current_version = expected_version + 1),
    state TEXT NOT NULL CHECK (state IN ('OBSERVE', 'HOLD_FOR_HUMAN_APPROVAL', 'ABORT_REQUIRED', 'ROLLBACK_REQUIRED')),
    outcome TEXT NOT NULL CHECK (outcome IN ('OBSERVE_REQUIRED', 'DATA_BLOCKED', 'HUMAN_APPROVALS_REQUIRED', 'ABORT_REQUIRED', 'ROLLBACK_REQUIRED')),
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    result_json BLOB NOT NULL,
    UNIQUE (run_id, current_version),
    FOREIGN KEY (run_id) REFERENCES canary_run(run_id)
) STRICT"""


def _normalized_sql(value: str) -> str:
    return " ".join(value.split()).replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")


_EXPECTED_TABLE_SQL: Final = {
    "canary_metadata": _normalized_sql(_CREATE_METADATA_SQL),
    "canary_run": _normalized_sql(_CREATE_RUN_SQL),
    "canary_journal": _normalized_sql(_CREATE_JOURNAL_SQL),
}
_EXPECTED_COLUMNS: Final = {
    "canary_metadata": (
        ("singleton", "INTEGER", 0, 1),
        ("schema_version", "TEXT", 1, 0),
        ("entry_count", "INTEGER", 1, 0),
        ("tail_sha256", "TEXT", 1, 0),
    ),
    "canary_run": (
        ("run_id", "TEXT", 1, 1),
        ("contract_sha256", "TEXT", 1, 0),
        ("current_version", "INTEGER", 1, 0),
        ("state", "TEXT", 1, 0),
        ("outcome", "TEXT", 1, 0),
        ("result_sha256", "TEXT", 1, 0),
        ("result_json", "BLOB", 1, 0),
        ("latest_sequence", "INTEGER", 1, 0),
        ("latest_entry_sha256", "TEXT", 1, 0),
    ),
    "canary_journal": (
        ("sequence", "INTEGER", 0, 1),
        ("previous_entry_sha256", "TEXT", 1, 0),
        ("entry_sha256", "TEXT", 1, 0),
        ("run_id", "TEXT", 1, 0),
        ("idempotency_key_sha256", "TEXT", 1, 0),
        ("request_sha256", "TEXT", 1, 0),
        ("contract_sha256", "TEXT", 1, 0),
        ("expected_version", "INTEGER", 1, 0),
        ("current_version", "INTEGER", 1, 0),
        ("state", "TEXT", 1, 0),
        ("outcome", "TEXT", 1, 0),
        ("result_sha256", "TEXT", 1, 0),
        ("result_json", "BLOB", 1, 0),
    ),
}
_EXPECTED_UNIQUE_COLUMNS: Final[dict[str, frozenset[tuple[str, ...]]]] = {
    "canary_metadata": frozenset(),
    "canary_run": frozenset(
        {("run_id",), ("latest_sequence",), ("latest_entry_sha256",)}
    ),
    "canary_journal": frozenset(
        {
            ("entry_sha256",),
            ("idempotency_key_sha256",),
            ("run_id", "current_version"),
        }
    ),
}


class CommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


def _fail(code: ProductionCanaryJournalFailureCode) -> NoReturn:
    raise ProductionCanaryJournalError(code) from None


@final
class RecordedProductionCanaryJournal:
    """SQLite CAS journal with an exact schema and content hash chain."""

    __slots__ = ("_database_path", "_fault", "_fault_lock", "_fault_used")

    def __init__(
        self,
        *,
        private_root: Path,
        commit_fault_once: CommitFault = CommitFault.NONE,
    ) -> None:
        if type(commit_fault_once) is not CommitFault:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        root = self._validate_private_root(private_root)
        self._database_path = root / _DATABASE_NAME
        self._fault = commit_fault_once
        self._fault_lock = Lock()
        self._fault_used = False
        self._prepare_database_file()
        connection = self._connect(initialize=True)
        connection.close()

    @property
    def database_path(self) -> Path:
        return self._database_path

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        normalized = Path(os.path.abspath(value))
        if value != normalized:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        cursor = Path(normalized.anchor)
        try:
            for part in normalized.parts[1:]:
                cursor /= part
                metadata = cursor.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
            metadata = normalized.lstat()
        except ProductionCanaryJournalError:
            raise
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        return normalized

    def _prepare_database_file(self) -> None:
        path = self._database_path
        try:
            descriptor = os.open(
                path,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
        except FileExistsError:
            self._verify_database_file()
            return
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            os.close(descriptor)
        try:
            parent_descriptor = os.open(
                path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        self._verify_database_file()

    def _verify_database_file(self) -> None:
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)

    def _connect(self, *, initialize: bool = False) -> sqlite3.Connection:
        self._verify_database_file()
        previous_umask = os.umask(0o077)
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=0,
                isolation_level=None,
            )
        except sqlite3.Error:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            os.umask(previous_umask)
        try:
            connection.execute("PRAGMA busy_timeout = 0")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            mode = cast(
                str, connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            )
            if mode.lower() != "delete":
                _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
            if initialize:
                self._initialize_schema(connection)
            self._verify_schema(connection)
            self._verify_database_file()
            return connection
        except ProductionCanaryJournalError:
            connection.close()
            raise
        except sqlite3.Error:
            connection.close()
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    @staticmethod
    def _initialize_schema(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_CREATE_METADATA_SQL)
            connection.execute(_CREATE_RUN_SQL)
            connection.execute(_CREATE_JOURNAL_SQL)
            connection.execute("PRAGMA user_version = 2")
            connection.execute(
                "INSERT OR IGNORE INTO canary_metadata "
                "(singleton, schema_version, entry_count, tail_sha256) "
                "VALUES (1, ?, 0, ?)",
                (_SCHEMA_VERSION, _ZERO_SHA256),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            if version != (2,):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            rows = connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            table_rows = [row for row in rows if row[0] == "table"]
            if len(table_rows) != 3 or any(row[0] != "table" for row in rows):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            observed_tables = {
                cast(str, row[1]): cast(str, row[3]) for row in table_rows
            }
            if set(observed_tables) != set(_EXPECTED_TABLE_SQL):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            for name, expected_sql in _EXPECTED_TABLE_SQL.items():
                if _normalized_sql(observed_tables[name]) != expected_sql:
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                columns = tuple(
                    (
                        cast(str, row[1]),
                        cast(str, row[2]),
                        cast(int, row[3]),
                        cast(int, row[5]),
                    )
                    for row in connection.execute(
                        f"PRAGMA table_info('{name}')"  # noqa: S608 - closed names
                    ).fetchall()
                )
                if columns != _EXPECTED_COLUMNS[name]:
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                unique_columns: set[tuple[str, ...]] = set()
                for index_row in connection.execute(
                    f"PRAGMA index_list('{name}')"  # noqa: S608 - closed names
                ).fetchall():
                    if cast(int, index_row[2]) != 1:
                        _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                    index_name = cast(str, index_row[1])
                    if not index_name.startswith("sqlite_autoindex_"):
                        _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                    unique_columns.add(
                        tuple(
                            cast(str, item[2])
                            for item in connection.execute(
                                f"PRAGMA index_info('{index_name}')"
                            ).fetchall()
                        )
                    )
                if frozenset(unique_columns) != _EXPECTED_UNIQUE_COLUMNS[name]:
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list('canary_journal')"
            ).fetchall()
            projected = tuple(
                (row[2], row[3], row[4], row[5], row[6]) for row in foreign_keys
            )
            if projected != (
                ("canary_run", "run_id", "run_id", "NO ACTION", "NO ACTION"),
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            if connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        except ProductionCanaryJournalError:
            raise
        except sqlite3.Error:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    def _consume_fault(self, fault: CommitFault) -> bool:
        with self._fault_lock:
            if self._fault is not fault or self._fault_used:
                return False
            self._fault_used = True
            return True

    def commit(self, command: CanaryStepPersistCommand) -> CanaryStepPersistReceipt:
        if type(command) is not CanaryStepPersistCommand:
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        from_state, _, _ = validated_command_transition(command)
        if self._consume_fault(CommitFault.BEFORE_COMMIT):
            _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_chain(connection)
            replay_row = connection.execute(
                "SELECT sequence, previous_entry_sha256, entry_sha256, run_id, "
                "idempotency_key_sha256, request_sha256, contract_sha256, "
                "expected_version, current_version, state, outcome, result_sha256, "
                "result_json FROM canary_journal WHERE idempotency_key_sha256 = ?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if replay_row is not None:
                persisted = self._row_to_persisted(replay_row)
                validate_persisted_binding(persisted, command)
                connection.rollback()
                return persisted.to_receipt(replayed=True)
            metadata = connection.execute(
                "SELECT schema_version, entry_count, tail_sha256 FROM canary_metadata "
                "WHERE singleton = 1"
            ).fetchone()
            if (
                metadata is None
                or metadata[0] != _SCHEMA_VERSION
                or type(metadata[1]) is not int
                or type(metadata[2]) is not str
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            sequence = metadata[1] + 1
            previous_entry_sha256 = metadata[2]
            current_row = connection.execute(
                "SELECT current_version, state, contract_sha256 FROM canary_run "
                "WHERE run_id = ?",
                (command.run_id,),
            ).fetchone()
            if current_row is None:
                if (
                    command.expected_version != 0
                    or from_state is not CanaryState.CANARY_READY
                ):
                    _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
            else:
                if (
                    current_row[0] != command.expected_version
                    or current_row[1] in _TERMINAL_STATES
                    or current_row[1] != from_state.value
                    or current_row[2] != command.contract_sha256
                ):
                    _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
            entry_sha256 = canary_entry_sha256(
                run_id=command.run_id,
                idempotency_key_sha256=command.idempotency_key_sha256,
                request_sha256=command.request_sha256,
                contract_sha256=command.contract_sha256,
                expected_version=command.expected_version,
                current_version=command.current_version,
                state=command.state,
                outcome=command.outcome,
                result_sha256=command.result_sha256,
                sequence=sequence,
                previous_entry_sha256=previous_entry_sha256,
            )
            if current_row is None:
                connection.execute(
                    "INSERT INTO canary_run "
                    "(run_id, contract_sha256, current_version, state, outcome, "
                    "result_sha256, result_json, latest_sequence, latest_entry_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        command.run_id,
                        command.contract_sha256,
                        command.current_version,
                        command.state.value,
                        command.outcome.value,
                        command.result_sha256,
                        command.result_json,
                        sequence,
                        entry_sha256,
                    ),
                )
            else:
                updated = connection.execute(
                    "UPDATE canary_run SET current_version = ?, state = ?, outcome = ?, "
                    "result_sha256 = ?, result_json = ?, latest_sequence = ?, "
                    "latest_entry_sha256 = ? WHERE run_id = ? AND current_version = ?",
                    (
                        command.current_version,
                        command.state.value,
                        command.outcome.value,
                        command.result_sha256,
                        command.result_json,
                        sequence,
                        entry_sha256,
                        command.run_id,
                        command.expected_version,
                    ),
                ).rowcount
                if updated != 1:
                    _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
            connection.execute(
                "INSERT INTO canary_journal "
                "(sequence, previous_entry_sha256, entry_sha256, run_id, "
                "idempotency_key_sha256, request_sha256, contract_sha256, "
                "expected_version, current_version, state, outcome, result_sha256, "
                "result_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sequence,
                    previous_entry_sha256,
                    entry_sha256,
                    command.run_id,
                    command.idempotency_key_sha256,
                    command.request_sha256,
                    command.contract_sha256,
                    command.expected_version,
                    command.current_version,
                    command.state.value,
                    command.outcome.value,
                    command.result_sha256,
                    command.result_json,
                ),
            )
            updated_metadata = connection.execute(
                "UPDATE canary_metadata SET entry_count = ?, tail_sha256 = ? "
                "WHERE singleton = 1 AND entry_count = ? AND tail_sha256 = ?",
                (
                    sequence,
                    entry_sha256,
                    sequence - 1,
                    previous_entry_sha256,
                ),
            ).rowcount
            if updated_metadata != 1:
                _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
            connection.commit()
            self._verify_database_file()
            receipt = CanaryStepPersistReceipt(
                run_id=command.run_id,
                current_version=command.current_version,
                request_sha256=command.request_sha256,
                result_sha256=command.result_sha256,
                sequence=sequence,
                previous_entry_sha256=previous_entry_sha256,
                entry_sha256=entry_sha256,
                replayed=False,
            )
            if self._consume_fault(CommitFault.AFTER_COMMIT):
                _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
            return receipt
        except ProductionCanaryJournalError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.rollback()
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        except sqlite3.OperationalError:
            if connection.in_transaction:
                connection.rollback()
            _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def recover_exact(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt:
        if type(command) is not CanaryStepPersistCommand:
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        connection = self._connect()
        try:
            self._verify_chain(connection)
            row = connection.execute(
                "SELECT sequence, previous_entry_sha256, entry_sha256, run_id, "
                "idempotency_key_sha256, request_sha256, contract_sha256, "
                "expected_version, current_version, state, outcome, result_sha256, "
                "result_json FROM canary_journal WHERE idempotency_key_sha256 = ?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if row is None:
                _fail(ProductionCanaryJournalFailureCode.RECOVERY_NOT_FOUND)
            persisted = self._row_to_persisted(row)
            validate_persisted_binding(persisted, command)
            return persisted.to_receipt(replayed=True)
        except ProductionCanaryJournalError:
            raise
        except sqlite3.Error:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def load_latest(self, run_id: str) -> PersistedCanaryStep | None:
        if type(run_id) is not str or not re_full_run_id(run_id):
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        connection = self._connect()
        try:
            self._verify_chain(connection)
            row = connection.execute(
                "SELECT j.sequence, j.previous_entry_sha256, j.entry_sha256, "
                "j.run_id, j.idempotency_key_sha256, j.request_sha256, "
                "j.contract_sha256, j.expected_version, j.current_version, "
                "j.state, j.outcome, j.result_sha256, j.result_json "
                "FROM canary_journal AS j JOIN canary_run AS r "
                "ON r.run_id = j.run_id AND r.latest_sequence = j.sequence "
                "WHERE j.run_id = ?",
                (run_id,),
            ).fetchone()
            return None if row is None else self._row_to_persisted(row)
        except ProductionCanaryJournalError:
            raise
        except sqlite3.Error:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def verify_integrity(self) -> int:
        connection = self._connect()
        try:
            return self._verify_chain(connection)
        finally:
            connection.close()

    @staticmethod
    def _row_to_persisted(row: tuple[object, ...]) -> PersistedCanaryStep:
        if len(row) != 13:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        try:
            return PersistedCanaryStep(
                sequence=cast(int, row[0]),
                previous_entry_sha256=cast(str, row[1]),
                entry_sha256=cast(str, row[2]),
                run_id=cast(str, row[3]),
                idempotency_key_sha256=cast(str, row[4]),
                request_sha256=cast(str, row[5]),
                contract_sha256=cast(str, row[6]),
                expected_version=cast(int, row[7]),
                current_version=cast(int, row[8]),
                state=CanaryState(cast(str, row[9])),
                outcome=CanaryOutcome(cast(str, row[10])),
                result_sha256=cast(str, row[11]),
                result_json=bytes(cast(bytes, row[12])),
            )
        except TypeError, ValueError, ProductionCanaryJournalError:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    @classmethod
    def _verify_chain(cls, connection: sqlite3.Connection) -> int:
        metadata = connection.execute(
            "SELECT schema_version, entry_count, tail_sha256 FROM canary_metadata "
            "WHERE singleton = 1"
        ).fetchone()
        if (
            metadata is None
            or metadata[0] != _SCHEMA_VERSION
            or type(metadata[1]) is not int
            or type(metadata[2]) is not str
        ):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            "SELECT sequence, previous_entry_sha256, entry_sha256, run_id, "
            "idempotency_key_sha256, request_sha256, contract_sha256, "
            "expected_version, current_version, state, outcome, result_sha256, "
            "result_json FROM canary_journal ORDER BY sequence"
        ).fetchall()
        if len(rows) != metadata[1]:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        previous = _ZERO_SHA256
        latest_by_run: dict[str, PersistedCanaryStep] = {}
        for expected_sequence, row in enumerate(rows, start=1):
            persisted = cls._row_to_persisted(row)
            from_state, _, _ = validated_persisted_transition(persisted)
            if (
                persisted.sequence != expected_sequence
                or persisted.previous_entry_sha256 != previous
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            previous = persisted.entry_sha256
            prior = latest_by_run.get(persisted.run_id)
            if prior is None:
                if (
                    persisted.expected_version != 0
                    or from_state is not CanaryState.CANARY_READY
                ):
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            elif (
                persisted.expected_version != prior.current_version
                or persisted.contract_sha256 != prior.contract_sha256
                or from_state is not prior.state
                or prior.state.value in _TERMINAL_STATES
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            latest_by_run[persisted.run_id] = persisted
        if previous != metadata[2]:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        run_rows = connection.execute(
            "SELECT run_id, contract_sha256, current_version, state, outcome, "
            "result_sha256, result_json, latest_sequence, latest_entry_sha256 "
            "FROM canary_run ORDER BY run_id"
        ).fetchall()
        if len(run_rows) != len(latest_by_run):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        for row in run_rows:
            latest = latest_by_run.get(cast(str, row[0]))
            if latest is None or (
                row[1] != latest.contract_sha256
                or row[2] != latest.current_version
                or row[3] != latest.state.value
                or row[4] != latest.outcome.value
                or row[5] != latest.result_sha256
                or bytes(cast(bytes, row[6])) != latest.result_json
                or row[7] != latest.sequence
                or row[8] != latest.entry_sha256
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        return len(rows)


def re_full_run_id(value: str) -> bool:
    import re

    return re.fullmatch(r"st1506-run-[a-z0-9][a-z0-9.-]{2,95}", value) is not None


__all__ = ["CommitFault", "RecordedProductionCanaryJournal"]
