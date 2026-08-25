"""Owner-private SQLite journal for ST-1505 recorded local admission.

This adapter has no network, provider, credential, staging, deployment, or
release surface. It persists only canonical synthetic result bytes in one
caller-created owner-private local directory. Storage initialization is
created-only and every later open is bound to the original directory and
database inode for the lifetime of the process.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock
from typing import Final, Mapping, NoReturn, final

from raos.domain.ops.staging_admission import canonical_sha256
from raos.ports.staging_admission import (
    AdmissionPersistCommand,
    AdmissionPersistReceipt,
    StagingAdmissionJournalError,
    StagingAdmissionJournalFailureCode,
)


_DATABASE_NAME: Final = "st1505-local-admission.sqlite3"
_APPLICATION_ID: Final = 1_505_003
_DATABASE_SCHEMA_VERSION: Final = 3
_SCHEMA_IDENTIFIER: Final = "ST1505_LOCAL_ADMISSION_JOURNAL_V3"
_ZERO_SHA256: Final = "0" * 64
_SIDECAR_NAMES: Final = tuple(
    f"{_DATABASE_NAME}{suffix}" for suffix in ("-journal", "-wal", "-shm")
)

_SCHEMA_TABLES: Mapping[str, str] = {
    "admission_metadata": f"""
        CREATE TABLE admission_metadata(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          schema_version TEXT NOT NULL CHECK(schema_version='{_SCHEMA_IDENTIFIER}'),
          entry_count INTEGER NOT NULL CHECK(entry_count>=0),
          tail_sha256 TEXT NOT NULL CHECK(length(tail_sha256)=64 AND tail_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "admission_run": """
        CREATE TABLE admission_run(
          run_id TEXT PRIMARY KEY CHECK(length(run_id) BETWEEN 14 AND 107),
          idempotency_key_sha256 TEXT NOT NULL UNIQUE CHECK(length(idempotency_key_sha256)=64 AND idempotency_key_sha256 NOT GLOB '*[^0-9a-f]*'),
          request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
          contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64 AND contract_sha256 NOT GLOB '*[^0-9a-f]*'),
          result_sha256 TEXT NOT NULL CHECK(length(result_sha256)=64 AND result_sha256 NOT GLOB '*[^0-9a-f]*'),
          result_json BLOB NOT NULL CHECK(length(result_json) BETWEEN 1 AND 131072),
          sequence INTEGER NOT NULL UNIQUE CHECK(sequence>=1),
          UNIQUE(run_id,idempotency_key_sha256,request_sha256,result_sha256,sequence)
        ) STRICT
    """,
    "admission_journal": """
        CREATE TABLE admission_journal(
          sequence INTEGER PRIMARY KEY CHECK(sequence>=1),
          previous_entry_sha256 TEXT NOT NULL CHECK(length(previous_entry_sha256)=64 AND previous_entry_sha256 NOT GLOB '*[^0-9a-f]*'),
          entry_sha256 TEXT NOT NULL UNIQUE CHECK(length(entry_sha256)=64 AND entry_sha256 NOT GLOB '*[^0-9a-f]*'),
          run_id TEXT NOT NULL UNIQUE,
          idempotency_key_sha256 TEXT NOT NULL UNIQUE CHECK(length(idempotency_key_sha256)=64 AND idempotency_key_sha256 NOT GLOB '*[^0-9a-f]*'),
          request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
          result_sha256 TEXT NOT NULL CHECK(length(result_sha256)=64 AND result_sha256 NOT GLOB '*[^0-9a-f]*'),
          FOREIGN KEY(run_id,idempotency_key_sha256,request_sha256,result_sha256,sequence)
            REFERENCES admission_run(run_id,idempotency_key_sha256,request_sha256,result_sha256,sequence)
            ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
}

_SCHEMA_TRIGGERS: Mapping[str, tuple[str, str]] = {
    "st1505_metadata_no_insert": (
        "admission_metadata",
        """
        CREATE TRIGGER st1505_metadata_no_insert
        BEFORE INSERT ON admission_metadata
        BEGIN SELECT RAISE(ABORT,'ST1505_METADATA_REQUIRED_SINGLETON'); END
        """,
    ),
    "st1505_metadata_no_delete": (
        "admission_metadata",
        """
        CREATE TRIGGER st1505_metadata_no_delete
        BEFORE DELETE ON admission_metadata
        BEGIN SELECT RAISE(ABORT,'ST1505_METADATA_REQUIRED_SINGLETON'); END
        """,
    ),
    "st1505_metadata_guard_update": (
        "admission_metadata",
        """
        CREATE TRIGGER st1505_metadata_guard_update
        BEFORE UPDATE ON admission_metadata
        WHEN NEW.singleton!=OLD.singleton
          OR NEW.schema_version!=OLD.schema_version
          OR NEW.entry_count!=OLD.entry_count+1
          OR NEW.tail_sha256=OLD.tail_sha256
          OR NOT EXISTS(
            SELECT 1 FROM admission_journal AS j
            WHERE j.sequence=NEW.entry_count
              AND j.previous_entry_sha256=OLD.tail_sha256
              AND j.entry_sha256=NEW.tail_sha256
          )
        BEGIN SELECT RAISE(ABORT,'ST1505_METADATA_TRANSITION_INVALID'); END
        """,
    ),
    "st1505_run_guard_insert": (
        "admission_run",
        """
        CREATE TRIGGER st1505_run_guard_insert
        BEFORE INSERT ON admission_run
        WHEN (SELECT COUNT(*) FROM admission_metadata WHERE singleton=1)!=1
          OR NEW.sequence!=COALESCE((
               SELECT entry_count+1 FROM admission_metadata WHERE singleton=1
             ),-1)
        BEGIN SELECT RAISE(ABORT,'ST1505_RUN_SEQUENCE_INVALID'); END
        """,
    ),
    "st1505_run_no_update": (
        "admission_run",
        """
        CREATE TRIGGER st1505_run_no_update
        BEFORE UPDATE ON admission_run
        BEGIN SELECT RAISE(ABORT,'ST1505_APPEND_ONLY'); END
        """,
    ),
    "st1505_run_no_delete": (
        "admission_run",
        """
        CREATE TRIGGER st1505_run_no_delete
        BEFORE DELETE ON admission_run
        BEGIN SELECT RAISE(ABORT,'ST1505_APPEND_ONLY'); END
        """,
    ),
    "st1505_journal_guard_insert": (
        "admission_journal",
        """
        CREATE TRIGGER st1505_journal_guard_insert
        BEFORE INSERT ON admission_journal
        WHEN (SELECT COUNT(*) FROM admission_metadata WHERE singleton=1)!=1
          OR NEW.sequence!=COALESCE((
               SELECT entry_count+1 FROM admission_metadata WHERE singleton=1
             ),-1)
          OR NEW.previous_entry_sha256!=COALESCE((
               SELECT tail_sha256 FROM admission_metadata WHERE singleton=1
             ),'')
          OR NOT EXISTS(
            SELECT 1 FROM admission_run AS r
            WHERE r.run_id=NEW.run_id
              AND r.idempotency_key_sha256=NEW.idempotency_key_sha256
              AND r.request_sha256=NEW.request_sha256
              AND r.result_sha256=NEW.result_sha256
              AND r.sequence=NEW.sequence
          )
        BEGIN SELECT RAISE(ABORT,'ST1505_JOURNAL_TRANSITION_INVALID'); END
        """,
    ),
    "st1505_journal_no_update": (
        "admission_journal",
        """
        CREATE TRIGGER st1505_journal_no_update
        BEFORE UPDATE ON admission_journal
        BEGIN SELECT RAISE(ABORT,'ST1505_APPEND_ONLY'); END
        """,
    ),
    "st1505_journal_no_delete": (
        "admission_journal",
        """
        CREATE TRIGGER st1505_journal_no_delete
        BEFORE DELETE ON admission_journal
        BEGIN SELECT RAISE(ABORT,'ST1505_APPEND_ONLY'); END
        """,
    ),
}

_EXPECTED_IMPLICIT_INDEXES: Mapping[str, str] = {
    "sqlite_autoindex_admission_journal_1": "admission_journal",
    "sqlite_autoindex_admission_journal_2": "admission_journal",
    "sqlite_autoindex_admission_journal_3": "admission_journal",
    "sqlite_autoindex_admission_run_1": "admission_run",
    "sqlite_autoindex_admission_run_2": "admission_run",
    "sqlite_autoindex_admission_run_3": "admission_run",
    "sqlite_autoindex_admission_run_4": "admission_run",
}
_EXPECTED_UNIQUE_INDEXES: Mapping[str, frozenset[tuple[str, tuple[str, ...]]]] = {
    "admission_metadata": frozenset(),
    "admission_run": frozenset(
        {
            ("pk", ("run_id",)),
            ("u", ("idempotency_key_sha256",)),
            ("u", ("sequence",)),
            (
                "u",
                (
                    "run_id",
                    "idempotency_key_sha256",
                    "request_sha256",
                    "result_sha256",
                    "sequence",
                ),
            ),
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

_SCHEMA_INITIALIZATION_LOCK = Lock()
_PROCESS_REGISTRY_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class _IntegrityState:
    entry_count: int
    tail_sha256: str


@dataclass(slots=True)
class _ProcessAnchor:
    process_id: int
    database_identity: tuple[int, int]
    root_identity: tuple[int, int]
    state: _IntegrityState
    lock: RLock


_PROCESS_ANCHORS: dict[tuple[int, str], _ProcessAnchor] = {}


def _fail(code: StagingAdmissionJournalFailureCode) -> NoReturn:
    raise StagingAdmissionJournalError(code) from None


def _sql_normalized(value: str) -> str:
    return (
        " ".join(value.split()).replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    )


@final
class RecordedStagingAdmissionJournal:
    """Restartable, idempotent, hash-chained synthetic local journal."""

    __slots__ = (
        "_ambiguity_lock",
        "_database_identity",
        "_database_path",
        "_private_root",
        "_process_anchor",
        "_root_identity",
        "_simulate_commit_ambiguity_once",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        private_root: Path,
        simulate_commit_ambiguity_once: bool = False,
    ) -> None:
        if type(simulate_commit_ambiguity_once) is not bool:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        self._private_root, self._root_identity = self._validate_private_root(
            private_root
        )
        self._database_path = self._private_root / _DATABASE_NAME
        self._database_identity = (-1, -1)
        self._process_anchor: _ProcessAnchor | None = None
        self._state_lock = RLock()
        self._simulate_commit_ambiguity_once = simulate_commit_ambiguity_once
        self._ambiguity_lock = Lock()
        with _SCHEMA_INITIALIZATION_LOCK:
            existing_anchor = self._acquire_existing_process_anchor()
            try:
                created, identity = self._open_database_file(allow_create=True)
                self._database_identity = identity
                connection, root_descriptor = self._connect(allow_empty=created)
                try:
                    if created:
                        self._initialize_new(connection)
                    connection.execute("BEGIN")
                    state = self._verify_integrity_in_transaction(connection)
                    self._bind_process_anchor(connection, state=state)
                    connection.commit()
                    self._validate_database_identity(require_no_sidecars=True)
                except StagingAdmissionJournalError:
                    self._rollback_safely(connection)
                    raise
                except sqlite3.Error:
                    self._rollback_safely(connection)
                    _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
                finally:
                    self._close(connection, root_descriptor)
            finally:
                if existing_anchor is not None:
                    existing_anchor.lock.release()

    def _acquire_existing_process_anchor(self) -> _ProcessAnchor | None:
        key = (os.getpid(), str(self._database_path))
        with _PROCESS_REGISTRY_LOCK:
            anchor = _PROCESS_ANCHORS.get(key)
        if anchor is not None:
            anchor.lock.acquire()
        return anchor

    @staticmethod
    def _validate_ancestor_chain(path: Path) -> None:
        descriptor = -1
        descriptors: list[int] = []
        try:
            descriptor = os.open(
                "/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
            )
            descriptors.append(descriptor)
            for component in path.parts[1:]:
                named = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                    _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                opened = os.fstat(child)
                if (
                    opened.st_dev != named.st_dev
                    or opened.st_ino != named.st_ino
                    or opened.st_mode != named.st_mode
                ):
                    os.close(child)
                    _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
                descriptors.append(child)
                descriptor = child
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            for opened_descriptor in reversed(descriptors):
                try:
                    os.close(opened_descriptor)
                except OSError:
                    pass

    @classmethod
    def _validate_private_root(cls, value: object) -> tuple[Path, tuple[int, int]]:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        normalized = Path(os.path.abspath(value))
        if value != normalized:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        cls._validate_ancestor_chain(normalized)
        try:
            metadata = normalized.lstat()
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        return normalized, (metadata.st_dev, metadata.st_ino)

    def _open_private_root(self) -> int:
        self._validate_ancestor_chain(self._private_root)
        descriptor = -1
        try:
            descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            metadata = os.fstat(descriptor)
        except OSError:
            if descriptor >= 0:
                os.close(descriptor)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            (metadata.st_dev, metadata.st_ino) != self._root_identity
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            os.close(descriptor)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        return descriptor

    @staticmethod
    def _validate_database_metadata(
        metadata: os.stat_result, *, allow_empty: bool
    ) -> tuple[int, int]:
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (not allow_empty and metadata.st_size == 0)
        ):
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        return metadata.st_dev, metadata.st_ino

    @staticmethod
    def _require_no_sidecars(root_descriptor: int) -> None:
        try:
            for name in _SIDECAR_NAMES:
                try:
                    os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)

    def _open_database_file(
        self, *, allow_create: bool, allow_empty: bool = False
    ) -> tuple[bool, tuple[int, int]]:
        root_descriptor = self._open_private_root()
        database_descriptor = -1
        created = False
        try:
            self._require_no_sidecars(root_descriptor)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if allow_create:
                try:
                    database_descriptor = os.open(
                        _DATABASE_NAME,
                        flags | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=root_descriptor,
                    )
                    created = True
                    os.fsync(database_descriptor)
                    os.fsync(root_descriptor)
                except FileExistsError:
                    database_descriptor = os.open(
                        _DATABASE_NAME, flags, dir_fd=root_descriptor
                    )
            else:
                database_descriptor = os.open(
                    _DATABASE_NAME, flags, dir_fd=root_descriptor
                )
            identity = self._validate_database_metadata(
                os.fstat(database_descriptor),
                allow_empty=created or allow_empty,
            )
            return created, identity
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)

    def _validate_database_identity(
        self, *, require_no_sidecars: bool, allow_empty: bool = False
    ) -> None:
        root_descriptor = self._open_private_root()
        database_descriptor = -1
        try:
            if require_no_sidecars:
                self._require_no_sidecars(root_descriptor)
            database_descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_descriptor,
            )
            identity = self._validate_database_metadata(
                os.fstat(database_descriptor), allow_empty=allow_empty
            )
            if identity != self._database_identity:
                _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        except StagingAdmissionJournalError:
            raise
        except OSError:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)

    def _connect(self, *, allow_empty: bool = False) -> tuple[sqlite3.Connection, int]:
        _created, identity = self._open_database_file(
            allow_create=False, allow_empty=allow_empty
        )
        if identity != self._database_identity:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
        root_descriptor = self._open_private_root()
        database_descriptor = -1
        connection: sqlite3.Connection | None = None
        try:
            self._require_no_sidecars(root_descriptor)
            database_descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=root_descriptor,
            )
            opened_identity = self._validate_database_metadata(
                os.fstat(database_descriptor), allow_empty=allow_empty
            )
            if opened_identity != self._database_identity:
                _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
            connection = sqlite3.connect(
                f"/proc/self/fd/{root_descriptor}/{_DATABASE_NAME}",
                timeout=10.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            if connection.execute("PRAGMA journal_mode=DELETE").fetchone() != (
                "delete",
            ):
                _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
            if (
                self._validate_database_metadata(
                    os.fstat(database_descriptor), allow_empty=allow_empty
                )
                != self._database_identity
            ):
                _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
            self._validate_database_identity(
                require_no_sidecars=True, allow_empty=allow_empty
            )
            os.close(database_descriptor)
            database_descriptor = -1
            return connection, root_descriptor
        except StagingAdmissionJournalError:
            if connection is not None:
                self._close_connection_safely(connection)
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)
            raise
        except OSError, sqlite3.Error:
            if connection is not None:
                self._close_connection_safely(connection)
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _rollback_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass

    @staticmethod
    def _close_connection_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    @classmethod
    def _close(cls, connection: sqlite3.Connection, root_descriptor: int) -> None:
        cls._close_connection_safely(connection)
        try:
            os.close(root_descriptor)
        except OSError:
            pass

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if connection.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone() != (
                0,
            ):
                _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
            connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={_DATABASE_SCHEMA_VERSION}")
            for statement in _SCHEMA_TABLES.values():
                connection.execute(statement)
            connection.execute(
                "INSERT INTO admission_metadata"
                "(singleton,schema_version,entry_count,tail_sha256) VALUES(1,?,0,?)",
                (_SCHEMA_IDENTIFIER, _ZERO_SHA256),
            )
            for _table_name, statement in _SCHEMA_TRIGGERS.values():
                connection.execute(statement)
            self._verify_integrity_in_transaction(connection)
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
        except StagingAdmissionJournalError:
            self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            self._rollback_safely(connection)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)

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
        observed_rows = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' "
            "AND sql IS NOT NULL ORDER BY type,name"
        ).fetchall()
        observed = {
            str(name): (str(kind), str(table), _sql_normalized(str(sql)))
            for kind, name, table, sql in observed_rows
        }
        expected: dict[str, tuple[str, str, str]] = {}
        for name, statement in _SCHEMA_TABLES.items():
            expected[name] = ("table", name, _sql_normalized(statement))
        for name, (table, statement) in _SCHEMA_TRIGGERS.items():
            expected[name] = ("trigger", table, _sql_normalized(statement))
        implicit_indexes = connection.execute(
            "SELECT name,tbl_name FROM sqlite_schema "
            "WHERE type='index' AND sql IS NULL ORDER BY name"
        ).fetchall()
        strict_rows = connection.execute(
            "SELECT name,strict FROM pragma_table_list "
            "WHERE schema='main' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if (
            observed != expected
            or tuple((str(name), str(table)) for name, table in implicit_indexes)
            != tuple(sorted(_EXPECTED_IMPLICIT_INDEXES.items()))
            or tuple((str(name), strict) for name, strict in strict_rows)
            != tuple((name, 1) for name in sorted(_SCHEMA_TABLES))
            or connection.execute("PRAGMA application_id").fetchone()
            != (_APPLICATION_ID,)
            or connection.execute("PRAGMA user_version").fetchone()
            != (_DATABASE_SCHEMA_VERSION,)
            or connection.execute("PRAGMA foreign_keys").fetchone() != (1,)
            or connection.execute("PRAGMA trusted_schema").fetchone() != (0,)
            or connection.execute("PRAGMA journal_mode").fetchone() != ("delete",)
            or connection.execute("PRAGMA synchronous").fetchone() != (2,)
            or connection.execute("PRAGMA secure_delete").fetchone() != (1,)
        ):
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
                columns = connection.execute(
                    f'PRAGMA index_info("{row[1]}")'
                ).fetchall()
                if not columns or any(
                    len(column) < 3 or type(column[2]) is not str for column in columns
                ):
                    _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
                observed_indexes.add(
                    (str(row[3]), tuple(str(column[2]) for column in columns))
                )
            if frozenset(observed_indexes) != expected_indexes:
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

        expected_foreign_keys = [
            (
                0,
                sequence,
                "admission_run",
                source,
                target,
                "RESTRICT",
                "RESTRICT",
                "NONE",
            )
            for sequence, (source, target) in enumerate(
                (
                    ("run_id", "run_id"),
                    ("idempotency_key_sha256", "idempotency_key_sha256"),
                    ("request_sha256", "request_sha256"),
                    ("result_sha256", "result_sha256"),
                    ("sequence", "sequence"),
                )
            )
        ]
        if (
            connection.execute(
                'PRAGMA foreign_key_list("admission_journal")'
            ).fetchall()
            != expected_foreign_keys
        ):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        for table_name in ("admission_metadata", "admission_run"):
            if connection.execute(
                f'PRAGMA foreign_key_list("{table_name}")'
            ).fetchall():
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

    def _verify_integrity_in_transaction(
        self, connection: sqlite3.Connection
    ) -> _IntegrityState:
        self._verify_schema_in_transaction(connection)
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        metadata_rows = connection.execute(
            "SELECT singleton,schema_version,entry_count,tail_sha256 "
            "FROM admission_metadata"
        ).fetchall()
        if len(metadata_rows) != 1:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        metadata = metadata_rows[0]
        if (
            metadata[0] != 1
            or metadata[1] != _SCHEMA_IDENTIFIER
            or type(metadata[2]) is not int
            or metadata[2] < 0
            or type(metadata[3]) is not str
            or len(metadata[3]) != 64
        ):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            """SELECT j.sequence, j.previous_entry_sha256, j.entry_sha256,
                      j.run_id, j.idempotency_key_sha256, j.request_sha256,
                      j.result_sha256, r.run_id, r.idempotency_key_sha256,
                      r.request_sha256, r.contract_sha256, r.result_sha256,
                      r.result_json, r.sequence
               FROM admission_journal AS j
               JOIN admission_run AS r
                 ON r.run_id=j.run_id
                AND r.idempotency_key_sha256=j.idempotency_key_sha256
                AND r.request_sha256=j.request_sha256
                AND r.result_sha256=j.result_sha256
                AND r.sequence=j.sequence
               ORDER BY j.sequence"""
        ).fetchall()
        if len(rows) != metadata[2]:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        if connection.execute("SELECT COUNT(*) FROM admission_run").fetchone() != (
            metadata[2],
        ):
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
        if metadata[3] != previous:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        return _IntegrityState(entry_count=metadata[2], tail_sha256=metadata[3])

    def _bind_process_anchor(
        self, connection: sqlite3.Connection, *, state: _IntegrityState
    ) -> None:
        process_id = os.getpid()
        key = (process_id, str(self._database_path))
        with _PROCESS_REGISTRY_LOCK:
            anchor = _PROCESS_ANCHORS.get(key)
            if anchor is None:
                anchor = _ProcessAnchor(
                    process_id=process_id,
                    database_identity=self._database_identity,
                    root_identity=self._root_identity,
                    state=state,
                    lock=RLock(),
                )
                _PROCESS_ANCHORS[key] = anchor
            elif (
                anchor.process_id != process_id
                or anchor.database_identity != self._database_identity
                or anchor.root_identity != self._root_identity
            ):
                _fail(StagingAdmissionJournalFailureCode.STORAGE_PATH_INVALID)
            self._process_anchor = anchor
        with anchor.lock:
            self._require_process_monotonic(connection, state=state)
            if state.entry_count > anchor.state.entry_count:
                anchor.state = state

    def _require_process_monotonic(
        self, connection: sqlite3.Connection, *, state: _IntegrityState
    ) -> None:
        anchor = self._process_anchor
        if anchor is None:
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        if (
            anchor.process_id != os.getpid()
            or anchor.database_identity != self._database_identity
            or anchor.root_identity != self._root_identity
            or state.entry_count < anchor.state.entry_count
        ):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        if anchor.state.entry_count == 0:
            observed_tail = _ZERO_SHA256
        else:
            row = connection.execute(
                "SELECT entry_sha256 FROM admission_journal WHERE sequence=?",
                (anchor.state.entry_count,),
            ).fetchone()
            if row is None or type(row[0]) is not str:
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            observed_tail = row[0]
        if observed_tail != anchor.state.tail_sha256 or (
            state.entry_count == anchor.state.entry_count and state != anchor.state
        ):
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)

    def _pin_process_state(self, *, state: _IntegrityState) -> None:
        anchor = self._process_anchor
        if anchor is None or state.entry_count < anchor.state.entry_count:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        if state.entry_count == anchor.state.entry_count and state != anchor.state:
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        anchor.state = state

    def _acquire_state(self) -> _ProcessAnchor:
        self._state_lock.acquire()
        anchor = self._process_anchor
        if anchor is None or anchor.process_id != os.getpid():
            self._state_lock.release()
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        anchor.lock.acquire()
        return anchor

    def _release_state(self, anchor: _ProcessAnchor) -> None:
        anchor.lock.release()
        self._state_lock.release()

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
               JOIN admission_journal AS j
                 ON j.run_id=r.run_id
                AND j.idempotency_key_sha256=r.idempotency_key_sha256
                AND j.request_sha256=r.request_sha256
                AND j.result_sha256=r.result_sha256
                AND j.sequence=r.sequence
               WHERE r.run_id=? OR r.idempotency_key_sha256=?""",
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
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        root_descriptor = -1
        committed = False
        commit_attempted = False
        try:
            connection, root_descriptor = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            current_state = self._verify_integrity_in_transaction(connection)
            self._require_process_monotonic(connection, state=current_state)
            existing = connection.execute(
                "SELECT 1 FROM admission_run "
                "WHERE run_id=? OR idempotency_key_sha256=? LIMIT 1",
                (command.run_id, command.idempotency_key_sha256),
            ).fetchone()
            if existing is not None:
                receipt = self._find_exact(
                    connection,
                    command,
                    not_found_code=StagingAdmissionJournalFailureCode.REPLAY_CONFLICT,
                )
                commit_attempted = True
                connection.commit()
                committed = True
                self._validate_database_identity(require_no_sidecars=True)
                self._pin_process_state(state=current_state)
                return receipt

            sequence = current_state.entry_count + 1
            previous = current_state.tail_sha256
            entry_sha256 = self._entry_sha256(
                command,
                sequence=sequence,
                previous_entry_sha256=previous,
            )
            connection.execute(
                """INSERT INTO admission_run
                   (run_id,idempotency_key_sha256,request_sha256,contract_sha256,
                    result_sha256,result_json,sequence)
                   VALUES(?,?,?,?,?,?,?)""",
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
                   (sequence,previous_entry_sha256,entry_sha256,run_id,
                    idempotency_key_sha256,request_sha256,result_sha256)
                   VALUES(?,?,?,?,?,?,?)""",
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
                   SET entry_count=?,tail_sha256=?
                   WHERE singleton=1 AND entry_count=? AND tail_sha256=?""",
                (sequence, entry_sha256, current_state.entry_count, previous),
            )
            if updated.rowcount != 1:
                _fail(StagingAdmissionJournalFailureCode.CONCURRENCY_FAILURE)
            new_state = self._verify_integrity_in_transaction(connection)
            if new_state != _IntegrityState(sequence, entry_sha256):
                _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
            commit_attempted = True
            connection.commit()
            committed = True
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=new_state)
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
            if connection is not None and not committed:
                self._rollback_safely(connection)
            raise
        except sqlite3.IntegrityError:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(StagingAdmissionJournalFailureCode.TAMPER_DETECTED)
        except sqlite3.OperationalError:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(StagingAdmissionJournalFailureCode.CONCURRENCY_FAILURE)
        except sqlite3.Error:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)

    def recover_exact(
        self, command: AdmissionPersistCommand
    ) -> AdmissionPersistReceipt:
        command = self._require_command(command)
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        root_descriptor = -1
        try:
            connection, root_descriptor = self._connect()
            connection.execute("BEGIN")
            state = self._verify_integrity_in_transaction(connection)
            self._require_process_monotonic(connection, state=state)
            receipt = self._find_exact(
                connection,
                command,
                not_found_code=StagingAdmissionJournalFailureCode.RECOVERY_NOT_FOUND,
            )
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=state)
            return receipt
        except StagingAdmissionJournalError:
            if connection is not None:
                self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback_safely(connection)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)

    def verify_integrity(self) -> int:
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        root_descriptor = -1
        try:
            connection, root_descriptor = self._connect()
            connection.execute("BEGIN")
            state = self._verify_integrity_in_transaction(connection)
            self._require_process_monotonic(connection, state=state)
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=state)
            return state.entry_count
        except StagingAdmissionJournalError:
            if connection is not None:
                self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback_safely(connection)
            _fail(StagingAdmissionJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)


__all__ = ["RecordedStagingAdmissionJournal"]
