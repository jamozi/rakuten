"""Owner-private durable journal for ST-1506 synthetic canary steps.

This adapter has no network, provider, credential, deployment, traffic,
rollback, release, or public-write surface.  It persists only validated local
simulation bytes in one caller-created owner-private directory.  A database is
initialized only when this process created the file with ``O_EXCL``; an
existing empty or foreign SQLite file is never adopted.  Every later access is
bound to the original directory and database inode, an exact STRICT schema,
and a process-shared monotonic hash-chain anchor.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Lock, RLock
from typing import Final, Mapping, NoReturn, cast, final

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
_APPLICATION_ID: Final = 1_506_003
_DATABASE_SCHEMA_VERSION: Final = 3
_SCHEMA_VERSION: Final = "ST1506_LOCAL_PRODUCTION_CANARY_JOURNAL_V3"
_ZERO_SHA256: Final = "0" * 64
_TERMINAL_STATES: Final = (
    "HOLD_FOR_HUMAN_APPROVAL",
    "ABORT_REQUIRED",
    "ROLLBACK_REQUIRED",
)
_SIDECAR_NAMES: Final = tuple(
    f"{_DATABASE_NAME}{suffix}" for suffix in ("-journal", "-wal", "-shm")
)

_SCHEMA_TABLES: Mapping[str, str] = {
    "canary_metadata": f"""
        CREATE TABLE canary_metadata(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          schema_version TEXT NOT NULL CHECK(schema_version='{_SCHEMA_VERSION}'),
          entry_count INTEGER NOT NULL CHECK(entry_count>=0),
          tail_sha256 TEXT NOT NULL CHECK(length(tail_sha256)=64 AND tail_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "canary_run": """
        CREATE TABLE canary_run(
          run_id TEXT PRIMARY KEY NOT NULL CHECK(length(run_id) BETWEEN 14 AND 107),
          contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64 AND contract_sha256 NOT GLOB '*[^0-9a-f]*'),
          current_version INTEGER NOT NULL CHECK(current_version>=1),
          state TEXT NOT NULL CHECK(state IN ('OBSERVE','HOLD_FOR_HUMAN_APPROVAL','ABORT_REQUIRED','ROLLBACK_REQUIRED')),
          outcome TEXT NOT NULL CHECK(outcome IN ('OBSERVE_REQUIRED','DATA_BLOCKED','HUMAN_APPROVALS_REQUIRED','ABORT_REQUIRED','ROLLBACK_REQUIRED')),
          result_sha256 TEXT NOT NULL CHECK(length(result_sha256)=64 AND result_sha256 NOT GLOB '*[^0-9a-f]*'),
          result_json BLOB NOT NULL CHECK(length(result_json) BETWEEN 1 AND 131072),
          latest_sequence INTEGER NOT NULL UNIQUE CHECK(latest_sequence>=1),
          latest_entry_sha256 TEXT NOT NULL UNIQUE CHECK(length(latest_entry_sha256)=64 AND latest_entry_sha256 NOT GLOB '*[^0-9a-f]*'),
          UNIQUE(run_id,current_version)
        ) STRICT
    """,
    "canary_journal": """
        CREATE TABLE canary_journal(
          sequence INTEGER PRIMARY KEY CHECK(sequence>=1),
          previous_entry_sha256 TEXT NOT NULL CHECK(length(previous_entry_sha256)=64 AND previous_entry_sha256 NOT GLOB '*[^0-9a-f]*'),
          entry_sha256 TEXT NOT NULL UNIQUE CHECK(length(entry_sha256)=64 AND entry_sha256 NOT GLOB '*[^0-9a-f]*'),
          run_id TEXT NOT NULL,
          idempotency_key_sha256 TEXT NOT NULL UNIQUE CHECK(length(idempotency_key_sha256)=64 AND idempotency_key_sha256 NOT GLOB '*[^0-9a-f]*'),
          request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
          contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64 AND contract_sha256 NOT GLOB '*[^0-9a-f]*'),
          expected_version INTEGER NOT NULL CHECK(expected_version>=0),
          current_version INTEGER NOT NULL CHECK(current_version=expected_version+1),
          state TEXT NOT NULL CHECK(state IN ('OBSERVE','HOLD_FOR_HUMAN_APPROVAL','ABORT_REQUIRED','ROLLBACK_REQUIRED')),
          outcome TEXT NOT NULL CHECK(outcome IN ('OBSERVE_REQUIRED','DATA_BLOCKED','HUMAN_APPROVALS_REQUIRED','ABORT_REQUIRED','ROLLBACK_REQUIRED')),
          result_sha256 TEXT NOT NULL CHECK(length(result_sha256)=64 AND result_sha256 NOT GLOB '*[^0-9a-f]*'),
          result_json BLOB NOT NULL CHECK(length(result_json) BETWEEN 1 AND 131072),
          UNIQUE(run_id,current_version),
          FOREIGN KEY(run_id) REFERENCES canary_run(run_id) ON UPDATE RESTRICT ON DELETE RESTRICT
        ) STRICT
    """,
}

_SCHEMA_TRIGGERS: Mapping[str, tuple[str, str]] = {
    "st1506_metadata_no_insert": (
        "canary_metadata",
        """
        CREATE TRIGGER st1506_metadata_no_insert
        BEFORE INSERT ON canary_metadata
        BEGIN SELECT RAISE(ABORT,'ST1506_METADATA_REQUIRED_SINGLETON'); END
        """,
    ),
    "st1506_metadata_no_delete": (
        "canary_metadata",
        """
        CREATE TRIGGER st1506_metadata_no_delete
        BEFORE DELETE ON canary_metadata
        BEGIN SELECT RAISE(ABORT,'ST1506_METADATA_REQUIRED_SINGLETON'); END
        """,
    ),
    "st1506_metadata_guard_update": (
        "canary_metadata",
        """
        CREATE TRIGGER st1506_metadata_guard_update
        BEFORE UPDATE ON canary_metadata
        WHEN NEW.singleton!=OLD.singleton
          OR NEW.schema_version!=OLD.schema_version
          OR NEW.entry_count!=OLD.entry_count+1
          OR NEW.tail_sha256=OLD.tail_sha256
          OR NOT EXISTS(
            SELECT 1 FROM canary_journal AS j
            WHERE j.sequence=NEW.entry_count
              AND j.previous_entry_sha256=OLD.tail_sha256
              AND j.entry_sha256=NEW.tail_sha256
          )
        BEGIN SELECT RAISE(ABORT,'ST1506_METADATA_TRANSITION_INVALID'); END
        """,
    ),
    "st1506_run_guard_insert": (
        "canary_run",
        """
        CREATE TRIGGER st1506_run_guard_insert
        BEFORE INSERT ON canary_run
        WHEN (SELECT COUNT(*) FROM canary_metadata WHERE singleton=1)!=1
          OR NEW.current_version!=1
          OR NEW.state!='OBSERVE'
          OR NEW.outcome!='OBSERVE_REQUIRED'
          OR NEW.latest_sequence!=COALESCE((
               SELECT entry_count+1 FROM canary_metadata WHERE singleton=1
             ),-1)
        BEGIN SELECT RAISE(ABORT,'ST1506_RUN_INITIAL_TRANSITION_INVALID'); END
        """,
    ),
    "st1506_run_guard_update": (
        "canary_run",
        """
        CREATE TRIGGER st1506_run_guard_update
        BEFORE UPDATE ON canary_run
        WHEN NEW.run_id!=OLD.run_id
          OR NEW.contract_sha256!=OLD.contract_sha256
          OR OLD.state!='OBSERVE'
          OR NEW.current_version!=OLD.current_version+1
          OR NEW.latest_sequence!=COALESCE((
               SELECT entry_count+1 FROM canary_metadata WHERE singleton=1
             ),-1)
          OR NEW.latest_sequence<=OLD.latest_sequence
          OR NEW.latest_entry_sha256=OLD.latest_entry_sha256
          OR NOT (
            (NEW.state='OBSERVE' AND NEW.outcome='DATA_BLOCKED')
            OR (NEW.state='HOLD_FOR_HUMAN_APPROVAL' AND NEW.outcome='HUMAN_APPROVALS_REQUIRED')
            OR (NEW.state='ABORT_REQUIRED' AND NEW.outcome='ABORT_REQUIRED')
            OR (NEW.state='ROLLBACK_REQUIRED' AND NEW.outcome='ROLLBACK_REQUIRED')
          )
        BEGIN SELECT RAISE(ABORT,'ST1506_RUN_LIFECYCLE_INVALID'); END
        """,
    ),
    "st1506_run_no_delete": (
        "canary_run",
        """
        CREATE TRIGGER st1506_run_no_delete
        BEFORE DELETE ON canary_run
        BEGIN SELECT RAISE(ABORT,'ST1506_APPEND_ONLY'); END
        """,
    ),
    "st1506_journal_guard_insert": (
        "canary_journal",
        """
        CREATE TRIGGER st1506_journal_guard_insert
        BEFORE INSERT ON canary_journal
        WHEN (SELECT COUNT(*) FROM canary_metadata WHERE singleton=1)!=1
          OR NEW.sequence!=COALESCE((
               SELECT entry_count+1 FROM canary_metadata WHERE singleton=1
             ),-1)
          OR NEW.previous_entry_sha256!=COALESCE((
               SELECT tail_sha256 FROM canary_metadata WHERE singleton=1
             ),'')
          OR NOT EXISTS(
            SELECT 1 FROM canary_run AS r
            WHERE r.run_id=NEW.run_id
              AND r.contract_sha256=NEW.contract_sha256
              AND r.current_version=NEW.current_version
              AND r.state=NEW.state
              AND r.outcome=NEW.outcome
              AND r.result_sha256=NEW.result_sha256
              AND r.result_json=NEW.result_json
              AND r.latest_sequence=NEW.sequence
              AND r.latest_entry_sha256=NEW.entry_sha256
          )
          OR (NEW.current_version=1 AND NOT (
               NEW.expected_version=0
               AND NEW.state='OBSERVE'
               AND NEW.outcome='OBSERVE_REQUIRED'
               AND NOT EXISTS(
                 SELECT 1 FROM canary_journal WHERE run_id=NEW.run_id
               )
             ))
          OR (NEW.current_version>1 AND NOT EXISTS(
               SELECT 1 FROM canary_journal AS prior
               WHERE prior.run_id=NEW.run_id
                 AND prior.current_version=NEW.expected_version
                 AND prior.state='OBSERVE'
                 AND prior.contract_sha256=NEW.contract_sha256
             ))
        BEGIN SELECT RAISE(ABORT,'ST1506_JOURNAL_TRANSITION_INVALID'); END
        """,
    ),
    "st1506_journal_no_update": (
        "canary_journal",
        """
        CREATE TRIGGER st1506_journal_no_update
        BEFORE UPDATE ON canary_journal
        BEGIN SELECT RAISE(ABORT,'ST1506_APPEND_ONLY'); END
        """,
    ),
    "st1506_journal_no_delete": (
        "canary_journal",
        """
        CREATE TRIGGER st1506_journal_no_delete
        BEFORE DELETE ON canary_journal
        BEGIN SELECT RAISE(ABORT,'ST1506_APPEND_ONLY'); END
        """,
    ),
}

_EXPECTED_IMPLICIT_INDEXES: Mapping[str, str] = {
    "sqlite_autoindex_canary_journal_1": "canary_journal",
    "sqlite_autoindex_canary_journal_2": "canary_journal",
    "sqlite_autoindex_canary_journal_3": "canary_journal",
    "sqlite_autoindex_canary_run_1": "canary_run",
    "sqlite_autoindex_canary_run_2": "canary_run",
    "sqlite_autoindex_canary_run_3": "canary_run",
    "sqlite_autoindex_canary_run_4": "canary_run",
}
_EXPECTED_UNIQUE_INDEXES: Mapping[str, frozenset[tuple[str, tuple[str, ...]]]] = {
    "canary_metadata": frozenset(),
    "canary_run": frozenset(
        {
            ("pk", ("run_id",)),
            ("u", ("latest_sequence",)),
            ("u", ("latest_entry_sha256",)),
            ("u", ("run_id", "current_version")),
        }
    ),
    "canary_journal": frozenset(
        {
            ("u", ("entry_sha256",)),
            ("u", ("idempotency_key_sha256",)),
            ("u", ("run_id", "current_version")),
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


def _normalized_sql(value: str) -> str:
    return (
        " ".join(value.split()).replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    )


class CommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


def _fail(code: ProductionCanaryJournalFailureCode) -> NoReturn:
    raise ProductionCanaryJournalError(code) from None


@final
class RecordedProductionCanaryJournal:
    """Restartable CAS journal with exact schema and monotonic chain binding."""

    __slots__ = (
        "_database_identity",
        "_database_path",
        "_fault",
        "_fault_lock",
        "_fault_used",
        "_private_root",
        "_process_anchor",
        "_root_identity",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        private_root: Path,
        commit_fault_once: CommitFault = CommitFault.NONE,
    ) -> None:
        if type(commit_fault_once) is not CommitFault:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        self._private_root, self._root_identity = self._validate_private_root(
            private_root
        )
        self._database_path = self._private_root / _DATABASE_NAME
        self._database_identity = (-1, -1)
        self._process_anchor: _ProcessAnchor | None = None
        self._state_lock = RLock()
        self._fault = commit_fault_once
        self._fault_lock = Lock()
        self._fault_used = False
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
                except ProductionCanaryJournalError:
                    self._rollback_safely(connection)
                    raise
                except sqlite3.Error:
                    self._rollback_safely(connection)
                    _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
                finally:
                    self._close(connection, root_descriptor)
            finally:
                if existing_anchor is not None:
                    existing_anchor.lock.release()

    @property
    def database_path(self) -> Path:
        return self._database_path

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
                    _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
                    _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
                descriptors.append(child)
                descriptor = child
        except ProductionCanaryJournalError:
            raise
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            for opened_descriptor in reversed(descriptors):
                try:
                    os.close(opened_descriptor)
                except OSError:
                    pass

    @classmethod
    def _validate_private_root(cls, value: object) -> tuple[Path, tuple[int, int]]:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        normalized = Path(os.path.abspath(value))
        if value != normalized:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        cls._validate_ancestor_chain(normalized)
        try:
            metadata = normalized.lstat()
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        if (
            (metadata.st_dev, metadata.st_ino) != self._root_identity
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            os.close(descriptor)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        return metadata.st_dev, metadata.st_ino

    @staticmethod
    def _require_no_sidecars(root_descriptor: int) -> None:
        try:
            for name in _SIDECAR_NAMES:
                try:
                    os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        except ProductionCanaryJournalError:
            raise
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)

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
                os.fstat(database_descriptor), allow_empty=created or allow_empty
            )
            return created, identity
        except ProductionCanaryJournalError:
            raise
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
                _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        except ProductionCanaryJournalError:
            raise
        except OSError:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
            os.close(root_descriptor)

    def _connect(self, *, allow_empty: bool = False) -> tuple[sqlite3.Connection, int]:
        _created, identity = self._open_database_file(
            allow_create=False, allow_empty=allow_empty
        )
        if identity != self._database_identity:
            _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
                _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
                _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
            if (
                self._validate_database_metadata(
                    os.fstat(database_descriptor), allow_empty=allow_empty
                )
                != self._database_identity
            ):
                _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
            self._validate_database_identity(
                require_no_sidecars=True, allow_empty=allow_empty
            )
            os.close(database_descriptor)
            database_descriptor = -1
            return connection, root_descriptor
        except ProductionCanaryJournalError:
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
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)

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
                _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
            connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={_DATABASE_SCHEMA_VERSION}")
            for statement in _SCHEMA_TABLES.values():
                connection.execute(statement)
            connection.execute(
                "INSERT INTO canary_metadata"
                "(singleton,schema_version,entry_count,tail_sha256) VALUES(1,?,0,?)",
                (_SCHEMA_VERSION, _ZERO_SHA256),
            )
            for _table_name, statement in _SCHEMA_TRIGGERS.values():
                connection.execute(statement)
            self._verify_integrity_in_transaction(connection)
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
        except ProductionCanaryJournalError:
            self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            self._rollback_safely(connection)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _verify_schema_in_transaction(connection: sqlite3.Connection) -> None:
        observed_rows = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' "
            "AND sql IS NOT NULL ORDER BY type,name"
        ).fetchall()
        observed = {
            str(name): (str(kind), str(table), _normalized_sql(str(sql)))
            for kind, name, table, sql in observed_rows
        }
        expected: dict[str, tuple[str, str, str]] = {}
        for name, statement in _SCHEMA_TABLES.items():
            expected[name] = ("table", name, _normalized_sql(statement))
        for name, (table, statement) in _SCHEMA_TRIGGERS.items():
            expected[name] = ("trigger", table, _normalized_sql(statement))
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
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

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
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                columns = connection.execute(
                    f'PRAGMA index_info("{row[1]}")'
                ).fetchall()
                if not columns or any(
                    len(column) < 3 or type(column[2]) is not str for column in columns
                ):
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
                observed_indexes.add(
                    (str(row[3]), tuple(str(column[2]) for column in columns))
                )
            if frozenset(observed_indexes) != expected_indexes:
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

        if connection.execute(
            'PRAGMA foreign_key_list("canary_journal")'
        ).fetchall() != [
            (0, 0, "canary_run", "run_id", "run_id", "RESTRICT", "RESTRICT", "NONE")
        ]:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        for table_name in ("canary_metadata", "canary_run"):
            if connection.execute(
                f'PRAGMA foreign_key_list("{table_name}")'
            ).fetchall():
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    def _consume_fault(self, fault: CommitFault) -> bool:
        with self._fault_lock:
            if self._fault is not fault or self._fault_used:
                return False
            self._fault_used = True
            return True

    def _verify_integrity_in_transaction(
        self, connection: sqlite3.Connection
    ) -> _IntegrityState:
        self._verify_schema_in_transaction(connection)
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        metadata_rows = connection.execute(
            "SELECT singleton,schema_version,entry_count,tail_sha256 "
            "FROM canary_metadata"
        ).fetchall()
        if len(metadata_rows) != 1:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        metadata = metadata_rows[0]
        if (
            metadata[0] != 1
            or metadata[1] != _SCHEMA_VERSION
            or type(metadata[2]) is not int
            or metadata[2] < 0
            or type(metadata[3]) is not str
            or len(metadata[3]) != 64
        ):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        rows = connection.execute(
            "SELECT sequence,previous_entry_sha256,entry_sha256,run_id,"
            "idempotency_key_sha256,request_sha256,contract_sha256,"
            "expected_version,current_version,state,outcome,result_sha256,"
            "result_json FROM canary_journal ORDER BY sequence"
        ).fetchall()
        if len(rows) != metadata[2]:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        previous = _ZERO_SHA256
        latest_by_run: dict[str, PersistedCanaryStep] = {}
        for expected_sequence, row in enumerate(rows, start=1):
            persisted = self._row_to_persisted(row)
            from_state, _, _ = validated_persisted_transition(persisted)
            if (
                persisted.sequence != expected_sequence
                or persisted.previous_entry_sha256 != previous
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            prior = latest_by_run.get(persisted.run_id)
            if prior is None:
                if (
                    persisted.expected_version != 0
                    or persisted.current_version != 1
                    or from_state is not CanaryState.CANARY_READY
                ):
                    _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            elif (
                persisted.expected_version != prior.current_version
                or persisted.current_version != prior.current_version + 1
                or persisted.contract_sha256 != prior.contract_sha256
                or from_state is not prior.state
                or prior.state.value in _TERMINAL_STATES
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            latest_by_run[persisted.run_id] = persisted
            previous = persisted.entry_sha256
        if previous != metadata[3]:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        run_rows = connection.execute(
            "SELECT run_id,contract_sha256,current_version,state,outcome,"
            "result_sha256,result_json,latest_sequence,latest_entry_sha256 "
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
                or type(row[6]) is not bytes
                or row[6] != latest.result_json
                or row[7] != latest.sequence
                or row[8] != latest.entry_sha256
            ):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
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
                _fail(ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID)
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
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        if (
            anchor.process_id != os.getpid()
            or anchor.database_identity != self._database_identity
            or anchor.root_identity != self._root_identity
            or state.entry_count < anchor.state.entry_count
        ):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        if anchor.state.entry_count == 0:
            observed_tail = _ZERO_SHA256
        else:
            row = connection.execute(
                "SELECT entry_sha256 FROM canary_journal WHERE sequence=?",
                (anchor.state.entry_count,),
            ).fetchone()
            if row is None or type(row[0]) is not str:
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            observed_tail = row[0]
        if observed_tail != anchor.state.tail_sha256 or (
            state.entry_count == anchor.state.entry_count and state != anchor.state
        ):
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    def _pin_process_state(self, *, state: _IntegrityState) -> None:
        anchor = self._process_anchor
        if anchor is None or state.entry_count < anchor.state.entry_count:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        if state.entry_count == anchor.state.entry_count and state != anchor.state:
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        anchor.state = state

    def _acquire_state(self) -> _ProcessAnchor:
        self._state_lock.acquire()
        anchor = self._process_anchor
        if anchor is None or anchor.process_id != os.getpid():
            self._state_lock.release()
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        anchor.lock.acquire()
        return anchor

    def _release_state(self, anchor: _ProcessAnchor) -> None:
        anchor.lock.release()
        self._state_lock.release()

    def _find_exact(
        self,
        connection: sqlite3.Connection,
        command: CanaryStepPersistCommand,
        *,
        not_found_code: ProductionCanaryJournalFailureCode,
    ) -> CanaryStepPersistReceipt:
        rows = connection.execute(
            "SELECT sequence,previous_entry_sha256,entry_sha256,run_id,"
            "idempotency_key_sha256,request_sha256,contract_sha256,"
            "expected_version,current_version,state,outcome,result_sha256,"
            "result_json FROM canary_journal WHERE idempotency_key_sha256=?",
            (command.idempotency_key_sha256,),
        ).fetchall()
        if not rows:
            _fail(not_found_code)
        if len(rows) != 1:
            _fail(ProductionCanaryJournalFailureCode.REPLAY_CONFLICT)
        persisted = self._row_to_persisted(rows[0])
        try:
            validate_persisted_binding(persisted, command)
        except ProductionCanaryJournalError:
            _fail(ProductionCanaryJournalFailureCode.REPLAY_CONFLICT)
        return persisted.to_receipt(replayed=True)

    def commit(self, command: CanaryStepPersistCommand) -> CanaryStepPersistReceipt:
        if type(command) is not CanaryStepPersistCommand:
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        from_state, _, _ = validated_command_transition(command)
        if self._consume_fault(CommitFault.BEFORE_COMMIT):
            _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
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
            replay_row = connection.execute(
                "SELECT 1 FROM canary_journal WHERE idempotency_key_sha256=?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if replay_row is not None:
                receipt = self._find_exact(
                    connection,
                    command,
                    not_found_code=ProductionCanaryJournalFailureCode.REPLAY_CONFLICT,
                )
                connection.commit()
                committed = True
                self._validate_database_identity(require_no_sidecars=True)
                self._pin_process_state(state=current_state)
                return receipt
            sequence = current_state.entry_count + 1
            previous_entry_sha256 = current_state.tail_sha256
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
            new_state = self._verify_integrity_in_transaction(connection)
            if new_state != _IntegrityState(sequence, entry_sha256):
                _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
            commit_attempted = True
            connection.commit()
            committed = True
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=new_state)
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
            if connection is not None and not committed:
                self._rollback_safely(connection)
            raise
        except sqlite3.IntegrityError:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
        except sqlite3.OperationalError:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE)
        except sqlite3.Error:
            if connection is not None and not committed:
                self._rollback_safely(connection)
            if commit_attempted:
                _fail(ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)

    def recover_exact(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt:
        if type(command) is not CanaryStepPersistCommand:
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
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
                not_found_code=ProductionCanaryJournalFailureCode.RECOVERY_NOT_FOUND,
            )
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=state)
            return receipt
        except ProductionCanaryJournalError:
            if connection is not None:
                self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback_safely(connection)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)

    def load_latest(self, run_id: str) -> PersistedCanaryStep | None:
        if type(run_id) is not str or not re_full_run_id(run_id):
            _fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        root_descriptor = -1
        try:
            connection, root_descriptor = self._connect()
            connection.execute("BEGIN")
            state = self._verify_integrity_in_transaction(connection)
            self._require_process_monotonic(connection, state=state)
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
            persisted = None if row is None else self._row_to_persisted(row)
            connection.commit()
            self._validate_database_identity(require_no_sidecars=True)
            self._pin_process_state(state=state)
            return persisted
        except ProductionCanaryJournalError:
            if connection is not None:
                self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback_safely(connection)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
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
        except ProductionCanaryJournalError:
            if connection is not None:
                self._rollback_safely(connection)
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback_safely(connection)
            _fail(ProductionCanaryJournalFailureCode.STORAGE_FAILURE)
        finally:
            if connection is not None:
                self._close(connection, root_descriptor)
            self._release_state(anchor)

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


def re_full_run_id(value: str) -> bool:
    import re

    return re.fullmatch(r"st1506-run-[a-z0-9][a-z0-9.-]{2,95}", value) is not None


__all__ = ["CommitFault", "RecordedProductionCanaryJournal"]
