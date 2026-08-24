"""Owner-private recorded-local SQLite Fact store for ST-0602 V2.

The adapter has no network, provider, credential, AI, review-decision,
publication, delivery, retention, export, staging, release, or Production
capability.  It atomically appends an exact Fact batch, its structural
validation records, one undelivered outbox record, and an idempotency journal.
Rollback detection is process-lifetime monotonic only; no cross-restart anchor
is claimed.
"""

from __future__ import annotations

from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
from typing import Any, NoReturn, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FACT_EXTRACTION_EVENT_CHANNEL_V2,
    FACT_EXTRACTION_EVENT_TYPE_V2,
    FACT_EXTRACTION_GENESIS_SHA256_V2,
    ExactOfferFactV2,
    FactExtractionBatchV2,
    FactExtractionCommandV2,
    FactExtractionFailureCodeV2,
    FactExtractionFailureV2,
    FactStoreCommitV2,
    FactValidationRecordV2,
    FactsExtractedOutboxEventV2,
    PersistedFactExtractionV2,
    batch_from_mapping_v2,
    batch_mapping_v2,
    canonical_json_bytes_v2,
    event_from_mapping_v2,
    event_mapping_v2,
    fact_chain_hash_v2,
    fact_from_mapping_v2,
    fact_mapping_v2,
    fail_fact_extraction_v2,
    persisted_from_mapping_v2,
    persisted_mapping_v2,
    utc_text_v2,
    validation_from_mapping_v2,
    validation_mapping_v2,
)


_DATABASE_NAME = "st0602-fact-extraction.sqlite3"
_SCHEMA_VERSION = 1
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_JSON_DEPTH = 48
_MAX_JSON_NODES = 150_000

_SCHEMA_CREATE_SQL: tuple[tuple[str, str], ...] = (
    (
        "st0602_state",
        """CREATE TABLE st0602_state (
    state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
    head_hash TEXT NOT NULL CHECK (length(head_hash) = 64)
) STRICT""",
    ),
    (
        "st0602_batches",
        """CREATE TABLE st0602_batches (
    batch_id TEXT PRIMARY KEY,
    source_snapshot_id TEXT NOT NULL,
    extractor_version TEXT NOT NULL CHECK (extractor_version = 'ST0602_EXACT_STRUCTURAL_OFFER_FACTS_V2'),
    command_payload_sha256 TEXT NOT NULL CHECK (length(command_payload_sha256) = 64),
    sequence INTEGER NOT NULL UNIQUE CHECK (sequence >= 1),
    previous_chain_hash TEXT NOT NULL CHECK (length(previous_chain_hash) = 64),
    chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
    event_id TEXT NOT NULL UNIQUE,
    batch_bytes BLOB NOT NULL,
    batch_sha256 TEXT NOT NULL CHECK (length(batch_sha256) = 64),
    committed_at TEXT NOT NULL,
    UNIQUE(source_snapshot_id, extractor_version)
) STRICT""",
    ),
    (
        "st0602_facts",
        """CREATE TABLE st0602_facts (
    fact_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(batch_id, ordinal),
    FOREIGN KEY(batch_id) REFERENCES st0602_batches(batch_id)
) STRICT""",
    ),
    (
        "st0602_validations",
        """CREATE TABLE st0602_validations (
    fact_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(batch_id, ordinal),
    FOREIGN KEY(fact_id) REFERENCES st0602_facts(fact_id),
    FOREIGN KEY(batch_id) REFERENCES st0602_batches(batch_id)
) STRICT""",
    ),
    (
        "st0602_outbox",
        """CREATE TABLE st0602_outbox (
    event_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type = 'jp.raos.evidence.facts_extracted.v1'),
    channel TEXT NOT NULL CHECK (channel = 'quality.events'),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES st0602_batches(batch_id)
) STRICT""",
    ),
    (
        "st0602_journal",
        """CREATE TABLE st0602_journal (
    operation_id TEXT PRIMARY KEY,
    source_snapshot_id TEXT NOT NULL,
    extractor_version TEXT NOT NULL CHECK (extractor_version = 'ST0602_EXACT_STRUCTURAL_OFFER_FACTS_V2'),
    command_payload_sha256 TEXT NOT NULL CHECK (length(command_payload_sha256) = 64),
    batch_id TEXT NOT NULL UNIQUE,
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    UNIQUE(source_snapshot_id, extractor_version),
    FOREIGN KEY(batch_id) REFERENCES st0602_batches(batch_id)
) STRICT""",
    ),
)

_IMMUTABLE_TABLES = (
    "st0602_batches",
    "st0602_facts",
    "st0602_validations",
    "st0602_outbox",
    "st0602_journal",
)

_TRIGGER_CREATE_SQL: tuple[tuple[str, str, str], ...] = (
    (
        "st0602_state_no_delete",
        "st0602_state",
        """CREATE TRIGGER st0602_state_no_delete BEFORE DELETE ON st0602_state BEGIN SELECT RAISE(ABORT, 'append_only'); END""",
    ),
    (
        "st0602_state_guard_update",
        "st0602_state",
        """CREATE TRIGGER st0602_state_guard_update BEFORE UPDATE ON st0602_state WHEN NEW.state_id != OLD.state_id OR NEW.schema_binding != OLD.schema_binding OR NEW.entry_count != OLD.entry_count + 1 BEGIN SELECT RAISE(ABORT, 'invalid_state_transition'); END""",
    ),
    *tuple(
        (
            f"{table}_no_update",
            table,
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END",
        )
        for table in _IMMUTABLE_TABLES
    ),
    *tuple(
        (
            f"{table}_no_delete",
            table,
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'append_only'); END",
        )
        for table in _IMMUTABLE_TABLES
    ),
)

_SCHEMA_BINDING = hashlib.sha256(
    "\n".join(
        [f"table\0{name}\0{sql}" for name, sql in _SCHEMA_CREATE_SQL]
        + [
            f"trigger\0{name}\0{table}\0{sql}"
            for name, table, sql in _TRIGGER_CREATE_SQL
        ]
    ).encode("utf-8")
).hexdigest()

_AUTO_INDEX_COUNTS: dict[str, int] = {
    "st0602_state": 0,
    "st0602_batches": 4,
    "st0602_facts": 2,
    "st0602_validations": 2,
    "st0602_outbox": 2,
    "st0602_journal": 3,
}
_SCHEMA_AUTO_INDEXES: frozenset[tuple[str, str, str, None]] = frozenset(
    ("index", f"sqlite_autoindex_{table}_{index}", table, None)
    for table, count in _AUTO_INDEX_COUNTS.items()
    for index in range(1, count + 1)
)
_SCHEMA_INITIALIZATION_LOCK = RLock()


class FactExtractionSqliteCommitFaultV2(str, Enum):
    NONE = "NONE"
    KNOWN_BEFORE_COMMIT = "KNOWN_BEFORE_COMMIT"
    UNKNOWN_BEFORE_COMMIT = "UNKNOWN_BEFORE_COMMIT"
    UNKNOWN_AFTER_COMMIT = "UNKNOWN_AFTER_COMMIT"


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_fact_extraction_v2()
    return value


def _validate_root_path(root: object) -> Path:
    if type(root) is not type(Path()) or not root.is_absolute() or ".." in root.parts:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
    normalized = Path(os.path.abspath(root))
    if normalized != root:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
        if stat.S_ISLNK(metadata.st_mode):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
    return root


def _validate_private_directory(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)


def _reject_constant(_value: str) -> NoReturn:
    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    count = 0
    while stack:
        current, depth = stack.pop()
        count += 1
        if depth > _MAX_JSON_DEPTH or count > _MAX_JSON_NODES:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        if type(current) is dict:
            stack.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in cast(list[object], current))
        elif current is not None and type(current) not in {str, int, bool}:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)


def _json_object(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > _MAX_JSON_BYTES:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except FactExtractionFailureV2:
        raise
    except Exception:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    _validate_json_tree(value)
    if type(value) is not dict:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    mapping = cast(dict[str, object], value)
    if canonical_json_bytes_v2(mapping) != payload:
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return mapping


def _payload_from_row(row: sqlite3.Row, *, prefix: str = "payload") -> bytes:
    payload = row[f"{prefix}_bytes"]
    digest = row[f"{prefix}_sha256"]
    if (
        type(payload) is not bytes
        or type(digest) is not str
        or hashlib.sha256(payload).hexdigest() != digest
    ):
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
    return payload


def _identifier(value: object) -> str:
    if type(value) is not UUID or value.int == 0:
        fail_fact_extraction_v2()
    return str(value)


@final
class OwnerPrivateSqliteFactExtractionStoreV2:
    """Fixed-path, append-only, process-monotonic local Fact UoW."""

    __slots__ = (
        "_commit_fault_index",
        "_commit_faults",
        "_database",
        "_database_identity",
        "_fault_lock",
        "_root",
        "_seen_count",
        "_seen_head",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        root: Path,
        commit_faults: tuple[FactExtractionSqliteCommitFaultV2, ...] = (),
    ) -> None:
        _environment(environment)
        if type(commit_faults) is not tuple or any(
            type(item) is not FactExtractionSqliteCommitFaultV2
            for item in commit_faults
        ):
            fail_fact_extraction_v2()
        private_root = _validate_root_path(root)
        try:
            os.mkdir(private_root, 0o700)
        except FileExistsError:
            pass
        except OSError:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
        _validate_private_directory(private_root)
        self._root = private_root
        self._database = private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] | None = None
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        self._fault_lock = RLock()
        self._state_lock = RLock()
        self._seen_count = 0
        self._seen_head = FACT_EXTRACTION_GENESIS_SHA256_V2
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(allow_create=True)
            self._database_identity = identity
            connection = self._connect(verify=False)
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
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
            finally:
                self._close_safely(connection)

    @property
    def database_path(self) -> Path:
        return self._database

    def _open_database_file(
        self,
        *,
        allow_create: bool,
    ) -> tuple[bool, tuple[int, int]]:
        _validate_private_directory(self._root)
        root_descriptor = -1
        descriptor = -1
        created = False
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            root_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | nofollow,
            )
            if allow_create:
                try:
                    descriptor = os.open(
                        _DATABASE_NAME,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | nofollow,
                        0o600,
                        dir_fd=root_descriptor,
                    )
                    created = True
                except FileExistsError:
                    descriptor = os.open(
                        _DATABASE_NAME,
                        os.O_RDWR | os.O_CLOEXEC | nofollow,
                        dir_fd=root_descriptor,
                    )
            else:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CLOEXEC | nofollow,
                    dir_fd=root_descriptor,
                )
            metadata = os.fstat(descriptor)
            named = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (named.st_dev, named.st_ino) != (metadata.st_dev, metadata.st_ino)
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
            if created:
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            return created, (metadata.st_dev, metadata.st_ino)
        except FactExtractionFailureV2:
            raise
        except OSError:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.UNSAFE_PATH)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self) -> None:
        _created, identity = self._open_database_file(allow_create=False)
        if self._database_identity is None or identity != self._database_identity:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        self._validate_database_identity()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self._database.as_uri()}?mode=rw",
                uri=True,
                timeout=5.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            trusted_schema = connection.execute("PRAGMA trusted_schema").fetchone()
            synchronous = connection.execute("PRAGMA synchronous").fetchone()
            secure_delete = connection.execute("PRAGMA secure_delete").fetchone()
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()
            if (
                journal_mode is None
                or tuple(journal_mode) != ("delete",)
                or foreign_keys is None
                or tuple(foreign_keys) != (1,)
                or trusted_schema is None
                or tuple(trusted_schema) != (0,)
                or synchronous is None
                or tuple(synchronous) != (2,)
                or secure_delete is None
                or tuple(secure_delete) != (1,)
                or busy_timeout is None
                or tuple(busy_timeout) != (5000,)
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.STORE_UNAVAILABLE)
            self._validate_database_identity()
        except sqlite3.OperationalError:
            if connection is not None:
                self._close_safely(connection)
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.CONCURRENCY_CONFLICT)
        except sqlite3.Error:
            if connection is not None:
                self._close_safely(connection)
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.STORE_UNAVAILABLE)
        except FactExtractionFailureV2:
            if connection is not None:
                self._close_safely(connection)
            raise
        if verify:
            try:
                with self._state_lock:
                    self._verify_schema(connection)
                    head, count = self._verify_integrity(connection)
                    self._require_monotonic_state(
                        connection,
                        head=head,
                        count=count,
                    )
                    self._validate_database_identity()
            except FactExtractionFailureV2:
                self._close_safely(connection)
                raise
            except sqlite3.Error:
                self._close_safely(connection)
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        return connection

    def _rollback(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        self._validate_database_identity()

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if (
                version is None
                or version[0] != 0
                or existing is None
                or existing[0] != 0
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.SCHEMA_INTEGRITY)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_database_identity()
            for _name, statement in _SCHEMA_CREATE_SQL:
                connection.execute(statement)
            for _name, _table, statement in _TRIGGER_CREATE_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO st0602_state(state_id, schema_binding, entry_count, head_hash) VALUES (1, ?, 0, ?)",
                (_SCHEMA_BINDING, FACT_EXTRACTION_GENESIS_SHA256_V2),
            )
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._validate_database_identity()
            connection.execute("COMMIT")
            self._validate_database_identity()
        except FactExtractionFailureV2:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.SCHEMA_INTEGRITY)
        self._verify_schema(connection)
        head, count = self._verify_integrity(connection)
        if head != FACT_EXTRACTION_GENESIS_SHA256_V2 or count != 0:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        expected = {
            *(("table", name, name, sql) for name, sql in _SCHEMA_CREATE_SQL),
            *(
                ("trigger", name, table, sql)
                for name, table, sql in _TRIGGER_CREATE_SQL
            ),
            *_SCHEMA_AUTO_INDEXES,
        }
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            observed = {
                (row[0], row[1], row[2], row[3])
                for row in connection.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master"
                ).fetchall()
            }
            strict = {
                row[1]: row[5]
                for row in connection.execute("PRAGMA table_list").fetchall()
                if row[1] in dict(_SCHEMA_CREATE_SQL)
            }
            if (
                version is None
                or version[0] != _SCHEMA_VERSION
                or observed != expected
                or strict != {name: 1 for name, _sql in _SCHEMA_CREATE_SQL}
                or connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.SCHEMA_INTEGRITY)
        except FactExtractionFailureV2:
            raise
        except sqlite3.Error:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.SCHEMA_INTEGRITY)

    @staticmethod
    def _decode_batch(row: sqlite3.Row) -> FactExtractionBatchV2:
        return batch_from_mapping_v2(
            _json_object(_payload_from_row(row, prefix="batch"))
        )

    @staticmethod
    def _decode_event(row: sqlite3.Row) -> FactsExtractedOutboxEventV2:
        return event_from_mapping_v2(_json_object(_payload_from_row(row)))

    @staticmethod
    def _decode_result(row: sqlite3.Row) -> PersistedFactExtractionV2:
        return persisted_from_mapping_v2(
            _json_object(_payload_from_row(row, prefix="result"))
        )

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> tuple[str, int]:
        try:
            quick = connection.execute("PRAGMA quick_check").fetchall()
            state_rows = connection.execute("SELECT * FROM st0602_state").fetchall()
            if (
                len(quick) != 1
                or quick[0][0] != "ok"
                or len(state_rows) != 1
                or state_rows[0]["state_id"] != 1
                or state_rows[0]["schema_binding"] != _SCHEMA_BINDING
                or type(state_rows[0]["entry_count"]) is not int
                or type(state_rows[0]["head_hash"]) is not str
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
            rows = connection.execute(
                "SELECT * FROM st0602_batches ORDER BY sequence"
            ).fetchall()
            previous = FACT_EXTRACTION_GENESIS_SHA256_V2
            fact_total = 0
            validation_total = 0
            for sequence, row in enumerate(rows, 1):
                batch = OwnerPrivateSqliteFactExtractionStoreV2._decode_batch(row)
                if (
                    row["sequence"] != sequence
                    or row["batch_id"] != str(batch.batch_id)
                    or row["source_snapshot_id"]
                    != str(batch.command.source_snapshot_id)
                    or row["extractor_version"] != batch.command.extractor_version
                    or row["command_payload_sha256"] != batch.command.payload_sha256
                    or row["previous_chain_hash"] != previous
                    or row["event_id"] == ""
                    or row["batch_sha256"] != batch.sha256
                    or row["committed_at"] != utc_text_v2(batch.extracted_at)
                ):
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                fact_rows = connection.execute(
                    "SELECT * FROM st0602_facts WHERE batch_id = ? ORDER BY ordinal",
                    (str(batch.batch_id),),
                ).fetchall()
                validation_rows = connection.execute(
                    "SELECT * FROM st0602_validations WHERE batch_id = ? ORDER BY ordinal",
                    (str(batch.batch_id),),
                ).fetchall()
                if len(fact_rows) != len(batch.facts) or len(validation_rows) != len(
                    batch.validations
                ):
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                for ordinal, (fact_row, expected_fact) in enumerate(
                    zip(fact_rows, batch.facts, strict=True), 1
                ):
                    fact = fact_from_mapping_v2(
                        _json_object(_payload_from_row(fact_row))
                    )
                    if (
                        fact_row["ordinal"] != ordinal
                        or fact_row["fact_id"] != str(fact.fact_id)
                        or fact != expected_fact
                    ):
                        fail_fact_extraction_v2(
                            FactExtractionFailureCodeV2.TAMPER_DETECTED
                        )
                for ordinal, (validation_row, expected_validation) in enumerate(
                    zip(validation_rows, batch.validations, strict=True), 1
                ):
                    validation = validation_from_mapping_v2(
                        _json_object(_payload_from_row(validation_row))
                    )
                    if (
                        validation_row["ordinal"] != ordinal
                        or validation_row["fact_id"] != str(validation.fact_id)
                        or validation != expected_validation
                    ):
                        fail_fact_extraction_v2(
                            FactExtractionFailureCodeV2.TAMPER_DETECTED
                        )
                event_row = connection.execute(
                    "SELECT * FROM st0602_outbox WHERE batch_id = ?",
                    (str(batch.batch_id),),
                ).fetchone()
                if event_row is None:
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                event = OwnerPrivateSqliteFactExtractionStoreV2._decode_event(event_row)
                if (
                    event != FactsExtractedOutboxEventV2.from_batch(batch)
                    or row["event_id"] != str(event.event_id)
                    or event_row["event_id"] != str(event.event_id)
                    or event_row["event_type"] != FACT_EXTRACTION_EVENT_TYPE_V2
                    or event_row["channel"] != FACT_EXTRACTION_EVENT_CHANNEL_V2
                    or event_row["created_at"] != utc_text_v2(event.occurred_at)
                ):
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                computed = fact_chain_hash_v2(
                    previous_chain_hash=previous,
                    sequence=sequence,
                    command_payload_sha256=batch.command.payload_sha256,
                    batch_sha256=batch.sha256,
                    event_sha256=event.sha256,
                    committed_at=batch.extracted_at,
                )
                persisted = PersistedFactExtractionV2(
                    sequence=sequence,
                    previous_chain_hash=previous,
                    chain_hash=computed,
                    command=batch.command,
                    batch=batch,
                    event=event,
                    committed_at=batch.extracted_at,
                )
                journal = connection.execute(
                    "SELECT * FROM st0602_journal WHERE batch_id = ?",
                    (str(batch.batch_id),),
                ).fetchone()
                if journal is None:
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                decoded = OwnerPrivateSqliteFactExtractionStoreV2._decode_result(
                    journal
                )
                if (
                    row["chain_hash"] != computed
                    or decoded != persisted
                    or journal["source_snapshot_id"]
                    != str(batch.command.source_snapshot_id)
                    or journal["extractor_version"] != batch.command.extractor_version
                    or journal["command_payload_sha256"] != batch.command.payload_sha256
                    or journal["operation_id"]
                    != OwnerPrivateSqliteFactExtractionStoreV2._operation_id(
                        batch.command
                    )
                    or journal["committed_at"] != utc_text_v2(batch.extracted_at)
                ):
                    fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
                fact_total += len(batch.facts)
                validation_total += len(batch.validations)
                previous = computed
            counts = {
                "facts": connection.execute(
                    "SELECT COUNT(*) FROM st0602_facts"
                ).fetchone()[0],
                "validations": connection.execute(
                    "SELECT COUNT(*) FROM st0602_validations"
                ).fetchone()[0],
                "outbox": connection.execute(
                    "SELECT COUNT(*) FROM st0602_outbox"
                ).fetchone()[0],
                "journal": connection.execute(
                    "SELECT COUNT(*) FROM st0602_journal"
                ).fetchone()[0],
            }
            if (
                counts
                != {
                    "facts": fact_total,
                    "validations": validation_total,
                    "outbox": len(rows),
                    "journal": len(rows),
                }
                or state_rows[0]["entry_count"] != len(rows)
                or state_rows[0]["head_hash"] != previous
            ):
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
            return previous, len(rows)
        except FactExtractionFailureV2:
            raise
        except sqlite3.Error, IndexError, TypeError:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)

    def _require_monotonic_state(
        self,
        connection: sqlite3.Connection,
        *,
        head: str,
        count: int,
    ) -> None:
        if count < self._seen_count:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        if self._seen_count == 0:
            if self._seen_head != FACT_EXTRACTION_GENESIS_SHA256_V2:
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        else:
            pinned = connection.execute(
                "SELECT chain_hash FROM st0602_batches WHERE sequence = ?",
                (self._seen_count,),
            ).fetchone()
            if pinned is None or pinned["chain_hash"] != self._seen_head:
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        if count == self._seen_count and head != self._seen_head:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)

    def _pin_state(self, *, head: str, count: int) -> None:
        if count < self._seen_count:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
        self._seen_count = count
        self._seen_head = head

    def _verified_state(self, connection: sqlite3.Connection) -> tuple[str, int]:
        self._validate_database_identity()
        self._verify_schema(connection)
        head, count = self._verify_integrity(connection)
        self._require_monotonic_state(connection, head=head, count=count)
        self._validate_database_identity()
        return head, count

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    @staticmethod
    def _operation_id(command: FactExtractionCommandV2) -> str:
        return f"{command.source_snapshot_id}:{command.extractor_version}"

    def _next_fault(self) -> FactExtractionSqliteCommitFaultV2:
        with self._fault_lock:
            fault = (
                self._commit_faults[self._commit_fault_index]
                if self._commit_fault_index < len(self._commit_faults)
                else FactExtractionSqliteCommitFaultV2.NONE
            )
            self._commit_fault_index += 1
            return fault

    @staticmethod
    def _map_sqlite_error(error: sqlite3.Error) -> NoReturn:
        if isinstance(error, sqlite3.IntegrityError | sqlite3.OperationalError):
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.CONCURRENCY_CONFLICT)
        fail_fact_extraction_v2(FactExtractionFailureCodeV2.STORE_UNAVAILABLE)

    def lookup(
        self, command: FactExtractionCommandV2
    ) -> PersistedFactExtractionV2 | None:
        if type(command) is not FactExtractionCommandV2:
            fail_fact_extraction_v2()
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM st0602_journal WHERE source_snapshot_id = ? AND extractor_version = ?",
                    (str(command.source_snapshot_id), command.extractor_version),
                ).fetchone()
                if row is None:
                    result = None
                else:
                    if row["command_payload_sha256"] != command.payload_sha256:
                        fail_fact_extraction_v2(
                            FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT
                        )
                    result = self._decode_result(row)
                    if result.command != command:
                        fail_fact_extraction_v2(
                            FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT
                        )
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
                return result
            except FactExtractionFailureV2:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def commit(
        self,
        *,
        command: FactExtractionCommandV2,
        batch: FactExtractionBatchV2,
        event: FactsExtractedOutboxEventV2,
    ) -> FactStoreCommitV2:
        if (
            type(command) is not FactExtractionCommandV2
            or type(batch) is not FactExtractionBatchV2
            or type(event) is not FactsExtractedOutboxEventV2
            or batch.command != command
            or event != FactsExtractedOutboxEventV2.from_batch(batch)
        ):
            fail_fact_extraction_v2()
        with self._state_lock:
            return self._commit_locked(command=command, batch=batch, event=event)

    def _commit_locked(
        self,
        *,
        command: FactExtractionCommandV2,
        batch: FactExtractionBatchV2,
        event: FactsExtractedOutboxEventV2,
    ) -> FactStoreCommitV2:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            starting_head, starting_count = self._verified_state(connection)
            existing = connection.execute(
                "SELECT * FROM st0602_journal WHERE source_snapshot_id = ? AND extractor_version = ?",
                (str(command.source_snapshot_id), command.extractor_version),
            ).fetchone()
            if existing is not None:
                if existing["command_payload_sha256"] != command.payload_sha256:
                    self._rollback(connection)
                    fail_fact_extraction_v2(
                        FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT
                    )
                persisted = self._decode_result(existing)
                self._rollback(connection)
                if (
                    persisted.command != command
                    or persisted.batch != batch
                    or persisted.event != event
                ):
                    fail_fact_extraction_v2(
                        FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT
                    )
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
                return FactStoreCommitV2(persisted=persisted, replayed=True)
            state = connection.execute(
                "SELECT entry_count, head_hash FROM st0602_state WHERE state_id = 1"
            ).fetchone()
            if (
                state is None
                or type(state["entry_count"]) is not int
                or type(state["head_hash"]) is not str
                or state["entry_count"] != starting_count
                or state["head_hash"] != starting_head
            ):
                self._rollback(connection)
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
            sequence = starting_count + 1
            previous = starting_head
            chain_hash = fact_chain_hash_v2(
                previous_chain_hash=previous,
                sequence=sequence,
                command_payload_sha256=command.payload_sha256,
                batch_sha256=batch.sha256,
                event_sha256=event.sha256,
                committed_at=batch.extracted_at,
            )
            persisted = PersistedFactExtractionV2(
                sequence=sequence,
                previous_chain_hash=previous,
                chain_hash=chain_hash,
                command=command,
                batch=batch,
                event=event,
                committed_at=batch.extracted_at,
            )
            batch_payload = canonical_json_bytes_v2(batch_mapping_v2(batch))
            connection.execute(
                "INSERT INTO st0602_batches(batch_id, source_snapshot_id, extractor_version, command_payload_sha256, sequence, previous_chain_hash, chain_hash, event_id, batch_bytes, batch_sha256, committed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(batch.batch_id),
                    str(command.source_snapshot_id),
                    command.extractor_version,
                    command.payload_sha256,
                    sequence,
                    previous,
                    chain_hash,
                    str(event.event_id),
                    batch_payload,
                    hashlib.sha256(batch_payload).hexdigest(),
                    utc_text_v2(batch.extracted_at),
                ),
            )
            for ordinal, fact in enumerate(batch.facts, 1):
                payload = canonical_json_bytes_v2(fact_mapping_v2(fact))
                connection.execute(
                    "INSERT INTO st0602_facts(fact_id, batch_id, ordinal, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(fact.fact_id),
                        str(batch.batch_id),
                        ordinal,
                        payload,
                        hashlib.sha256(payload).hexdigest(),
                    ),
                )
            for ordinal, validation in enumerate(batch.validations, 1):
                payload = canonical_json_bytes_v2(validation_mapping_v2(validation))
                connection.execute(
                    "INSERT INTO st0602_validations(fact_id, batch_id, ordinal, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?)",
                    (
                        str(validation.fact_id),
                        str(batch.batch_id),
                        ordinal,
                        payload,
                        hashlib.sha256(payload).hexdigest(),
                    ),
                )
            event_payload = canonical_json_bytes_v2(event_mapping_v2(event))
            connection.execute(
                "INSERT INTO st0602_outbox(event_id, batch_id, event_type, channel, payload_bytes, payload_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(event.event_id),
                    str(batch.batch_id),
                    event.event_type,
                    event.channel,
                    event_payload,
                    hashlib.sha256(event_payload).hexdigest(),
                    utc_text_v2(event.occurred_at),
                ),
            )
            result_payload = canonical_json_bytes_v2(persisted_mapping_v2(persisted))
            connection.execute(
                "INSERT INTO st0602_journal(operation_id, source_snapshot_id, extractor_version, command_payload_sha256, batch_id, result_bytes, result_sha256, committed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._operation_id(command),
                    str(command.source_snapshot_id),
                    command.extractor_version,
                    command.payload_sha256,
                    str(batch.batch_id),
                    result_payload,
                    hashlib.sha256(result_payload).hexdigest(),
                    utc_text_v2(batch.extracted_at),
                ),
            )
            updated = connection.execute(
                "UPDATE st0602_state SET entry_count = ?, head_hash = ? WHERE state_id = 1 AND entry_count = ? AND head_hash = ?",
                (sequence, chain_hash, sequence - 1, previous),
            )
            if updated.rowcount != 1:
                self._rollback(connection)
                fail_fact_extraction_v2(
                    FactExtractionFailureCodeV2.CONCURRENCY_CONFLICT
                )
            appended_head, appended_count = self._verified_state(connection)
            if appended_head != chain_hash or appended_count != sequence:
                self._rollback(connection)
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.TAMPER_DETECTED)
            self._validate_database_identity()
            fault = self._next_fault()
            if fault is FactExtractionSqliteCommitFaultV2.KNOWN_BEFORE_COMMIT:
                self._rollback(connection)
                fail_fact_extraction_v2(
                    FactExtractionFailureCodeV2.COMMIT_KNOWN_ROLLBACK
                )
            if fault is FactExtractionSqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT:
                self._rollback(connection)
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.COMMIT_UNKNOWN)
            try:
                connection.execute("COMMIT")
            except sqlite3.Error:
                self._validate_database_identity()
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.COMMIT_UNKNOWN)
            self._validate_database_identity()
            if fault is FactExtractionSqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.COMMIT_UNKNOWN)
            durable_head, durable_count = self._verified_state(connection)
            if durable_head != chain_hash or durable_count != sequence:
                fail_fact_extraction_v2(FactExtractionFailureCodeV2.COMMIT_UNKNOWN)
            self._pin_state(head=durable_head, count=durable_count)
            return FactStoreCommitV2(persisted=persisted, replayed=False)
        except FactExtractionFailureV2:
            raise
        except sqlite3.Error as error:
            self._rollback(connection)
            self._map_sqlite_error(error)
        finally:
            self._close_safely(connection)

    def recover_exact(
        self, command: FactExtractionCommandV2
    ) -> PersistedFactExtractionV2 | None:
        return self.lookup(command)

    def _read_one(self, query: str, identifier: str) -> sqlite3.Row | None:
        with self._state_lock:
            connection = self._connect()
            try:
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(query, (identifier,)).fetchone(),
                )
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
                return row
            except FactExtractionFailureV2:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def _read_many(self, query: str, identifier: str) -> tuple[sqlite3.Row, ...]:
        with self._state_lock:
            connection = self._connect()
            try:
                rows = cast(
                    tuple[sqlite3.Row, ...],
                    tuple(connection.execute(query, (identifier,)).fetchall()),
                )
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
                return rows
            except FactExtractionFailureV2:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def load_batch(self, batch_id: UUID) -> FactExtractionBatchV2:
        identifier = _identifier(batch_id)
        row = self._read_one(
            "SELECT * FROM st0602_batches WHERE batch_id = ?",
            identifier,
        )
        if row is None:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.RECOVERY_NOT_FOUND)
        return self._decode_batch(row)

    def load_fact(self, fact_id: UUID) -> ExactOfferFactV2:
        identifier = _identifier(fact_id)
        row = self._read_one(
            "SELECT * FROM st0602_facts WHERE fact_id = ?",
            identifier,
        )
        if row is None:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.RECOVERY_NOT_FOUND)
        return fact_from_mapping_v2(_json_object(_payload_from_row(row)))

    def list_validations(self, batch_id: UUID) -> tuple[FactValidationRecordV2, ...]:
        identifier = _identifier(batch_id)
        rows = self._read_many(
            "SELECT * FROM st0602_validations WHERE batch_id = ? ORDER BY ordinal",
            identifier,
        )
        return tuple(
            validation_from_mapping_v2(_json_object(_payload_from_row(row)))
            for row in rows
        )

    def load_outbox(self, event_id: UUID) -> FactsExtractedOutboxEventV2:
        identifier = _identifier(event_id)
        row = self._read_one(
            "SELECT * FROM st0602_outbox WHERE event_id = ?",
            identifier,
        )
        if row is None:
            fail_fact_extraction_v2(FactExtractionFailureCodeV2.RECOVERY_NOT_FOUND)
        return self._decode_event(row)

    def verify_chain(self) -> tuple[str, int]:
        with self._state_lock:
            connection = self._connect()
            try:
                head, count = self._verified_state(connection)
                self._pin_state(head=head, count=count)
                return head, count
            except FactExtractionFailureV2:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)


__all__ = [
    "FactExtractionSqliteCommitFaultV2",
    "OwnerPrivateSqliteFactExtractionStoreV2",
]
