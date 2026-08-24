"""Owner-private SQLite UoW for recorded ST-0504 product identity V2.

The adapter stores one generic review queue and an append-only decision
history with exact schema binding, CAS, idempotency journal, local outbox and
per-queue hash chain.  It has no network, worker, provider, credential,
publication, ranking, staging, release, or Production capability.
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
from raos.domain.catalog.product_identity_runtime_v2 import (
    PRODUCT_IDENTITY_ZERO_HASH_V2,
    PersistedProductIdentityDecisionV2,
    PersistedProductIdentityReviewQueueV2,
    PrepareProductIdentityReviewQueueCommandV2,
    ProductIdentityCommitKindV2,
    ProductIdentityCommitRecoveryOutcomeV2,
    ProductIdentityDecisionCommandV2,
    ProductIdentityDecisionCommitRecoveryV2,
    ProductIdentityHumanDecisionV2,
    ProductIdentityOutboxEventV2,
    ProductIdentityQueueCommitRecoveryV2,
    ProductIdentityReviewQueueV2,
    ProductIdentityRuntimeFailureCodeV2,
    ProductIdentityRuntimeFailureV2,
    fail_product_identity_runtime_v2,
    persisted_product_identity_decision_from_mapping_v2,
    persisted_product_identity_decision_mapping_v2,
    persisted_product_identity_review_queue_from_mapping_v2,
    persisted_product_identity_review_queue_mapping_v2,
    product_identity_candidate_pair_from_mapping_v2,
    product_identity_candidate_pair_mapping_v2,
    product_identity_chain_hash_v2,
    product_identity_outbox_event_from_mapping_v2,
    product_identity_outbox_event_mapping_v2,
)


_DATABASE_NAME = "st0504-product-identity.sqlite3"
_SCHEMA_VERSION = 1
_MAX_JSON_BYTES = 16 * 1024 * 1024
_MAX_JSON_DEPTH = 48
_MAX_JSON_NODES = 500_000

_SCHEMA_CREATE_SQL: tuple[tuple[str, str], ...] = (
    (
        "st0504_state",
        """CREATE TABLE st0504_state (
    queue_id TEXT PRIMARY KEY,
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    history_version INTEGER NOT NULL CHECK (history_version >= 1),
    head_hash TEXT NOT NULL CHECK (length(head_hash) = 64)
) STRICT""",
    ),
    (
        "st0504_queues",
        """CREATE TABLE st0504_queues (
    queue_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    site_id TEXT NOT NULL,
    source_binding_sha256 TEXT NOT NULL CHECK (length(source_binding_sha256) = 64),
    payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64),
    history_version INTEGER NOT NULL CHECK (history_version = 1),
    previous_chain_hash TEXT NOT NULL CHECK (length(previous_chain_hash) = 64),
    chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
    event_id TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    committed_at TEXT NOT NULL,
    UNIQUE(site_id, source_binding_sha256)
) STRICT""",
    ),
    (
        "st0504_pairs",
        """CREATE TABLE st0504_pairs (
    pair_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(queue_id, ordinal),
    FOREIGN KEY(queue_id) REFERENCES st0504_queues(queue_id)
) STRICT""",
    ),
    (
        "st0504_decisions",
        """CREATE TABLE st0504_decisions (
    decision_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    queue_id TEXT NOT NULL,
    pair_id TEXT NOT NULL,
    history_version INTEGER NOT NULL CHECK (history_version >= 2),
    supersedes_decision_id TEXT,
    payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64),
    previous_chain_hash TEXT NOT NULL CHECK (length(previous_chain_hash) = 64),
    chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
    event_id TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    committed_at TEXT NOT NULL,
    UNIQUE(queue_id, history_version),
    FOREIGN KEY(queue_id) REFERENCES st0504_queues(queue_id),
    FOREIGN KEY(pair_id) REFERENCES st0504_pairs(pair_id),
    FOREIGN KEY(supersedes_decision_id) REFERENCES st0504_decisions(decision_id)
) STRICT""",
    ),
    (
        "st0504_outbox",
        """CREATE TABLE st0504_outbox (
    event_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
    event_type TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel = 'ingestion.events'),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(queue_id, aggregate_version),
    FOREIGN KEY(queue_id) REFERENCES st0504_queues(queue_id)
) STRICT""",
    ),
    (
        "st0504_journal",
        """CREATE TABLE st0504_journal (
    operation_id TEXT PRIMARY KEY,
    commit_kind TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    history_version INTEGER NOT NULL CHECK (history_version >= 1),
    payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64),
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    FOREIGN KEY(queue_id) REFERENCES st0504_queues(queue_id)
) STRICT""",
    ),
)

_SCHEMA_BINDING = hashlib.sha256(
    "\n".join(f"{name}\0{sql}" for name, sql in _SCHEMA_CREATE_SQL).encode("utf-8")
).hexdigest()

_AUTO_INDEX_COUNTS: dict[str, int] = {
    "st0504_state": 1,
    "st0504_queues": 3,
    "st0504_pairs": 2,
    "st0504_decisions": 3,
    "st0504_outbox": 2,
    "st0504_journal": 1,
}
_SCHEMA_AUTO_INDEXES: frozenset[tuple[str, str, str, None]] = frozenset(
    (
        "index",
        f"sqlite_autoindex_{table}_{index}",
        table,
        None,
    )
    for table, count in _AUTO_INDEX_COUNTS.items()
    for index in range(1, count + 1)
)

_SCHEMA_COLUMNS: dict[str, tuple[tuple[str, str, int, int, int], ...]] = {
    "st0504_state": (
        ("queue_id", "TEXT", 1, 1, 0),
        ("schema_binding", "TEXT", 1, 0, 0),
        ("history_version", "INTEGER", 1, 0, 0),
        ("head_hash", "TEXT", 1, 0, 0),
    ),
    "st0504_queues": (
        ("queue_id", "TEXT", 1, 1, 0),
        ("operation_id", "TEXT", 1, 0, 0),
        ("site_id", "TEXT", 1, 0, 0),
        ("source_binding_sha256", "TEXT", 1, 0, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("history_version", "INTEGER", 1, 0, 0),
        ("previous_chain_hash", "TEXT", 1, 0, 0),
        ("chain_hash", "TEXT", 1, 0, 0),
        ("event_id", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
    "st0504_pairs": (
        ("pair_id", "TEXT", 1, 1, 0),
        ("queue_id", "TEXT", 1, 0, 0),
        ("ordinal", "INTEGER", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0504_decisions": (
        ("decision_id", "TEXT", 1, 1, 0),
        ("operation_id", "TEXT", 1, 0, 0),
        ("queue_id", "TEXT", 1, 0, 0),
        ("pair_id", "TEXT", 1, 0, 0),
        ("history_version", "INTEGER", 1, 0, 0),
        ("supersedes_decision_id", "TEXT", 0, 0, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("previous_chain_hash", "TEXT", 1, 0, 0),
        ("chain_hash", "TEXT", 1, 0, 0),
        ("event_id", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
    "st0504_outbox": (
        ("event_id", "TEXT", 1, 1, 0),
        ("queue_id", "TEXT", 1, 0, 0),
        ("aggregate_version", "INTEGER", 1, 0, 0),
        ("event_type", "TEXT", 1, 0, 0),
        ("channel", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("created_at", "TEXT", 1, 0, 0),
    ),
    "st0504_journal": (
        ("operation_id", "TEXT", 1, 1, 0),
        ("commit_kind", "TEXT", 1, 0, 0),
        ("queue_id", "TEXT", 1, 0, 0),
        ("history_version", "INTEGER", 1, 0, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("result_bytes", "BLOB", 1, 0, 0),
        ("result_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
}


class ProductIdentitySqliteCommitFaultV2(str, Enum):
    NONE = "NONE"
    KNOWN_BEFORE_COMMIT = "KNOWN_BEFORE_COMMIT"
    UNKNOWN_BEFORE_COMMIT = "UNKNOWN_BEFORE_COMMIT"
    UNKNOWN_AFTER_COMMIT = "UNKNOWN_AFTER_COMMIT"


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_product_identity_runtime_v2()
    return value


def _json_bytes(value: object) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    if not payload or len(payload) > _MAX_JSON_BYTES:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return payload


def _reject_constant(_value: str) -> NoReturn:
    fail_product_identity_runtime_v2(
        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        if current is None or type(current) in {str, int, bool}:
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1)
                for item in cast(dict[object, object], current).values()
            )
            continue
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )


def _json_object(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > _MAX_JSON_BYTES:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    try:
        value = cast(
            object,
            json.loads(
                payload.decode("utf-8", errors="strict"),
                object_pairs_hook=_pairs,
                parse_constant=_reject_constant,
            ),
        )
    except UnicodeError, json.JSONDecodeError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    _validate_json_tree(value)
    if type(value) is not dict:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return {cast(str, key): item for key, item in raw.items()}


def _payload_from_row(row: sqlite3.Row, *, prefix: str = "payload") -> bytes:
    payload = row[f"{prefix}_bytes"]
    digest = row[f"{prefix}_sha256"]
    if (
        type(payload) is not bytes
        or type(digest) is not str
        or hashlib.sha256(payload).hexdigest() != digest
    ):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return payload


def _validate_root_path(root: object) -> Path:
    if type(root) is not type(Path()) or not root.is_absolute() or ".." in root.parts:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )
    normalized = Path(os.path.abspath(root))
    if normalized != root:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
            )
        if stat.S_ISLNK(metadata.st_mode):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
            )
    return root


def _validate_private_directory(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )


def _validate_private_database(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
        )


@final
class OwnerPrivateSqliteProductIdentityStoreV2:
    """Fixed-path DEV/CI repository; all writes are one SQLite transaction."""

    __slots__ = (
        "_commit_fault_index",
        "_commit_faults",
        "_database",
        "_fault_lock",
        "_root",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        root: Path,
        commit_faults: tuple[ProductIdentitySqliteCommitFaultV2, ...] = (),
    ) -> None:
        _environment(environment)
        if type(commit_faults) is not tuple or any(
            type(value) is not ProductIdentitySqliteCommitFaultV2
            for value in commit_faults
        ):
            fail_product_identity_runtime_v2()
        private_root = _validate_root_path(root)
        if not private_root.exists():
            try:
                os.mkdir(private_root, 0o700)
            except OSError:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
                )
        _validate_private_directory(private_root)
        database = private_root / _DATABASE_NAME
        if not database.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(database, flags, 0o600)
                os.close(descriptor)
            except OSError:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH
                )
        _validate_private_database(database)
        self._root = private_root
        self._database = database
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        self._fault_lock = RLock()
        connection = self._connect(verify=False)
        try:
            self._initialize(connection)
        finally:
            connection.close()
        _validate_private_database(database)

    @property
    def database_path(self) -> Path:
        return self._database

    @property
    def external_action_count(self) -> int:
        return 0

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        _validate_private_directory(self._root)
        _validate_private_database(self._database)
        try:
            connection = sqlite3.connect(
                self._database,
                timeout=1.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 1000")
        except sqlite3.OperationalError:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
            )
        except sqlite3.Error:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        if verify:
            try:
                connection.execute("BEGIN")
                self._verify_schema(connection)
                self._verify_integrity(connection)
                connection.execute("ROLLBACK")
            except ProductIdentityRuntimeFailureV2:
                self._rollback(connection)
                connection.close()
                raise
            except sqlite3.OperationalError as error:
                self._rollback(connection)
                connection.close()
                self._map_sqlite_error(error)
            except sqlite3.Error:
                self._rollback(connection)
                connection.close()
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
                )
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.Error:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        if version is None or version[0] not in {0, _SCHEMA_VERSION}:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
            )
        if version[0] == _SCHEMA_VERSION:
            OwnerPrivateSqliteProductIdentityStoreV2._verify_schema(connection)
            OwnerPrivateSqliteProductIdentityStoreV2._verify_integrity(connection)
            return
        try:
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if existing is None or existing[0] != 0:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                )
            connection.execute("BEGIN IMMEDIATE")
            for _table, statement in _SCHEMA_CREATE_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except ProductIdentityRuntimeFailureV2:
            OwnerPrivateSqliteProductIdentityStoreV2._rollback(connection)
            raise
        except sqlite3.Error:
            OwnerPrivateSqliteProductIdentityStoreV2._rollback(connection)
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        OwnerPrivateSqliteProductIdentityStoreV2._verify_schema(connection)
        OwnerPrivateSqliteProductIdentityStoreV2._verify_integrity(connection)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or version[0] != _SCHEMA_VERSION:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                )
            observed_objects = {
                (row[0], row[1], row[2], row[3])
                for row in connection.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master"
                ).fetchall()
            }
            expected_objects = {
                *(
                    ("table", name, name, statement)
                    for name, statement in _SCHEMA_CREATE_SQL
                ),
                *_SCHEMA_AUTO_INDEXES,
            }
            if observed_objects != expected_objects:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                )
            for table, expected in _SCHEMA_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_xinfo({table})").fetchall()
                observed = tuple(
                    (row[1], row[2], row[3], row[5], row[6]) for row in rows
                )
                if observed != expected:
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                    )
            strict_rows = connection.execute("PRAGMA table_list").fetchall()
            strict_by_name = {
                row[1]: row[5] for row in strict_rows if row[1] in _SCHEMA_COLUMNS
            }
            if strict_by_name != {name: 1 for name in _SCHEMA_COLUMNS}:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                )
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
                )
        except ProductIdentityRuntimeFailureV2:
            raise
        except sqlite3.Error:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY
            )

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> None:
        try:
            queue_rows = connection.execute(
                "SELECT * FROM st0504_queues ORDER BY queue_id"
            ).fetchall()
            expected_journal = 0
            expected_outbox = 0
            expected_pairs = 0
            expected_decisions = 0
            for queue_row in queue_rows:
                persisted_queue = (
                    persisted_product_identity_review_queue_from_mapping_v2(
                        _json_object(_payload_from_row(queue_row))
                    )
                )
                queue = persisted_queue.queue
                if (
                    queue_row["queue_id"] != str(queue.queue_id)
                    or queue_row["operation_id"] != str(persisted_queue.operation_id)
                    or queue_row["site_id"] != str(queue.site_id)
                    or queue_row["source_binding_sha256"] != queue.source.sha256
                    or queue_row["payload_fingerprint"]
                    != persisted_queue.payload_fingerprint
                    or queue_row["history_version"] != 1
                    or queue_row["previous_chain_hash"] != PRODUCT_IDENTITY_ZERO_HASH_V2
                    or queue_row["chain_hash"] != persisted_queue.chain_hash
                    or queue_row["event_id"] != str(persisted_queue.event.event_id)
                    or queue_row["payload_sha256"]
                    != hashlib.sha256(_payload_from_row(queue_row)).hexdigest()
                    or queue_row["committed_at"]
                    != persisted_queue.committed_at.isoformat(timespec="microseconds")
                ):
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                    )
                pair_rows = connection.execute(
                    "SELECT * FROM st0504_pairs WHERE queue_id = ? ORDER BY ordinal",
                    (str(queue.queue_id),),
                ).fetchall()
                pairs = tuple(
                    product_identity_candidate_pair_from_mapping_v2(
                        _json_object(_payload_from_row(row))
                    )
                    for row in pair_rows
                )
                if pairs != queue.pairs or any(
                    row["pair_id"] != str(pair.pair_id)
                    or row["queue_id"] != str(queue.queue_id)
                    or row["ordinal"] != pair.ordinal
                    or row["payload_sha256"] != pair.sha256
                    for row, pair in zip(pair_rows, pairs, strict=True)
                ):
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                    )
                expected_pairs += len(pairs)
                previous = persisted_queue.chain_hash
                expected_version = 2
                pair_heads: dict[UUID, UUID] = {}
                decision_rows = connection.execute(
                    "SELECT * FROM st0504_decisions WHERE queue_id = ? ORDER BY history_version",
                    (str(queue.queue_id),),
                ).fetchall()
                for decision_row in decision_rows:
                    persisted = persisted_product_identity_decision_from_mapping_v2(
                        _json_object(_payload_from_row(decision_row))
                    )
                    decision = persisted.decision
                    current_head = pair_heads.get(decision.pair.pair_id)
                    if (
                        persisted.history_version != expected_version
                        or persisted.previous_chain_hash != previous
                        or decision.supersedes_decision_id != current_head
                        or decision.source_binding_sha256 != queue.source.sha256
                        or decision.source_batch_sha256
                        != queue.source.catalog_batch_sha256
                        or decision.source_snapshot_sha256
                        != queue.source.catalog_source_snapshot_sha256
                        or decision_row["decision_id"] != str(decision.decision_id)
                        or decision_row["operation_id"] != str(persisted.operation_id)
                        or decision_row["pair_id"] != str(decision.pair.pair_id)
                        or decision_row["history_version"] != expected_version
                        or decision_row["supersedes_decision_id"]
                        != (None if current_head is None else str(current_head))
                        or decision_row["payload_fingerprint"]
                        != persisted.payload_fingerprint
                        or decision_row["previous_chain_hash"] != previous
                        or decision_row["chain_hash"] != persisted.chain_hash
                        or decision_row["event_id"] != str(persisted.event.event_id)
                        or decision_row["payload_sha256"]
                        != hashlib.sha256(_payload_from_row(decision_row)).hexdigest()
                        or decision_row["committed_at"]
                        != persisted.committed_at.isoformat(timespec="microseconds")
                    ):
                        fail_product_identity_runtime_v2(
                            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                        )
                    pair_heads[decision.pair.pair_id] = decision.decision_id
                    previous = persisted.chain_hash
                    expected_version += 1
                expected_decisions += len(decision_rows)
                state = connection.execute(
                    "SELECT * FROM st0504_state WHERE queue_id = ?",
                    (str(queue.queue_id),),
                ).fetchone()
                if (
                    state is None
                    or state["schema_binding"] != _SCHEMA_BINDING
                    or state["history_version"] != expected_version - 1
                    or state["head_hash"] != previous
                ):
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                    )
                expected_journal += 1 + len(decision_rows)
                expected_outbox += 1 + len(decision_rows)
                OwnerPrivateSqliteProductIdentityStoreV2._verify_queue_records(
                    connection,
                    persisted_queue=persisted_queue,
                    decisions=tuple(
                        persisted_product_identity_decision_from_mapping_v2(
                            _json_object(_payload_from_row(row))
                        )
                        for row in decision_rows
                    ),
                )
            counts = {
                name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in _SCHEMA_COLUMNS
            }
            if counts != {
                "st0504_state": len(queue_rows),
                "st0504_queues": len(queue_rows),
                "st0504_pairs": expected_pairs,
                "st0504_decisions": expected_decisions,
                "st0504_outbox": expected_outbox,
                "st0504_journal": expected_journal,
            }:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
        except ProductIdentityRuntimeFailureV2:
            raise
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        except IndexError, KeyError, TypeError, ValueError, sqlite3.Error:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )

    @staticmethod
    def _verify_queue_records(
        connection: sqlite3.Connection,
        *,
        persisted_queue: PersistedProductIdentityReviewQueueV2,
        decisions: tuple[PersistedProductIdentityDecisionV2, ...],
    ) -> None:
        all_records: tuple[
            tuple[
                ProductIdentityCommitKindV2,
                UUID,
                int,
                str,
                object,
                ProductIdentityOutboxEventV2,
            ],
            ...,
        ] = (
            (
                ProductIdentityCommitKindV2.REVIEW_QUEUE,
                persisted_queue.operation_id,
                1,
                persisted_queue.payload_fingerprint,
                persisted_queue,
                persisted_queue.event,
            ),
            *(
                (
                    ProductIdentityCommitKindV2.HUMAN_DECISION,
                    item.operation_id,
                    item.history_version,
                    item.payload_fingerprint,
                    item,
                    item.event,
                )
                for item in decisions
            ),
        )
        for kind, operation_id, version, fingerprint, persisted, event in all_records:
            journal = connection.execute(
                "SELECT * FROM st0504_journal WHERE operation_id = ?",
                (str(operation_id),),
            ).fetchone()
            outbox = connection.execute(
                "SELECT * FROM st0504_outbox WHERE event_id = ?",
                (str(event.event_id),),
            ).fetchone()
            expected_result = (
                persisted_product_identity_review_queue_mapping_v2(
                    cast(PersistedProductIdentityReviewQueueV2, persisted)
                )
                if kind is ProductIdentityCommitKindV2.REVIEW_QUEUE
                else persisted_product_identity_decision_mapping_v2(
                    cast(PersistedProductIdentityDecisionV2, persisted)
                )
            )
            if (
                journal is None
                or journal["commit_kind"] != kind.value
                or journal["queue_id"] != str(persisted_queue.queue.queue_id)
                or journal["history_version"] != version
                or journal["payload_fingerprint"] != fingerprint
                or _json_object(_payload_from_row(journal, prefix="result"))
                != expected_result
                or outbox is None
                or outbox["queue_id"] != str(event.queue_id)
                or outbox["aggregate_version"] != event.aggregate_version
                or outbox["event_type"] != event.event_type
                or outbox["channel"] != event.channel
                or product_identity_outbox_event_from_mapping_v2(
                    _json_object(_payload_from_row(outbox))
                )
                != event
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )

    def _next_fault(self) -> ProductIdentitySqliteCommitFaultV2:
        with self._fault_lock:
            if self._commit_fault_index >= len(self._commit_faults):
                return ProductIdentitySqliteCommitFaultV2.NONE
            value = self._commit_faults[self._commit_fault_index]
            self._commit_fault_index += 1
            return value

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    @staticmethod
    def _map_sqlite_error(error: sqlite3.Error) -> NoReturn:
        if isinstance(error, sqlite3.IntegrityError):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
            )
        if isinstance(error, sqlite3.OperationalError) and (
            "locked" in str(error).lower() or "busy" in str(error).lower()
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
            )
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
        )

    @staticmethod
    def _identifier(value: object) -> str:
        if type(value) is not UUID or value.int == 0:
            fail_product_identity_runtime_v2()
        return str(value)

    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        if type(command) is not PrepareProductIdentityReviewQueueCommandV2:
            fail_product_identity_runtime_v2()
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM st0504_journal WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            return None
        if (
            row["commit_kind"] != ProductIdentityCommitKindV2.REVIEW_QUEUE.value
            or row["payload_fingerprint"] != command.payload_fingerprint
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
            )
        return persisted_product_identity_review_queue_from_mapping_v2(
            _json_object(_payload_from_row(row, prefix="result"))
        )

    def commit_review_queue(
        self,
        *,
        command: PrepareProductIdentityReviewQueueCommandV2,
        queue: ProductIdentityReviewQueueV2,
        event: ProductIdentityOutboxEventV2,
    ) -> PersistedProductIdentityReviewQueueV2:
        if (
            type(command) is not PrepareProductIdentityReviewQueueCommandV2
            or type(queue) is not ProductIdentityReviewQueueV2
            or type(event) is not ProductIdentityOutboxEventV2
            or event != ProductIdentityOutboxEventV2.from_queue(queue)
            or command.site_id != queue.site_id
        ):
            fail_product_identity_runtime_v2()
        connection = self._connect()
        fault = self._next_fault()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT payload_fingerprint FROM st0504_journal WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if existing is not None:
                if existing["payload_fingerprint"] != command.payload_fingerprint:
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                    )
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
                )
            chain_hash = product_identity_chain_hash_v2(
                previous_chain_hash=PRODUCT_IDENTITY_ZERO_HASH_V2,
                commit_kind=ProductIdentityCommitKindV2.REVIEW_QUEUE,
                queue_id=queue.queue_id,
                history_version=1,
                operation_id=command.operation_id,
                payload_sha256=queue.sha256,
                event_sha256=event.sha256,
                committed_at=queue.prepared_at,
            )
            persisted = PersistedProductIdentityReviewQueueV2(
                operation_id=command.operation_id,
                payload_fingerprint=command.payload_fingerprint,
                history_version=1,
                previous_chain_hash=PRODUCT_IDENTITY_ZERO_HASH_V2,
                chain_hash=chain_hash,
                queue=queue,
                event=event,
                committed_at=queue.prepared_at,
            )
            self._insert_queue(connection, persisted=persisted)
            if fault in {
                ProductIdentitySqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
                ProductIdentitySqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            }:
                self._rollback(connection)
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_KNOWN_ROLLBACK
                    if fault is ProductIdentitySqliteCommitFaultV2.KNOWN_BEFORE_COMMIT
                    else ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            connection.execute("COMMIT")
            if fault is ProductIdentitySqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            return persisted
        except ProductIdentityRuntimeFailureV2:
            self._rollback(connection)
            raise
        except sqlite3.Error as error:
            self._rollback(connection)
            self._map_sqlite_error(error)
        finally:
            connection.close()

    @staticmethod
    def _insert_queue(
        connection: sqlite3.Connection,
        *,
        persisted: PersistedProductIdentityReviewQueueV2,
    ) -> None:
        queue = persisted.queue
        payload = _json_bytes(
            persisted_product_identity_review_queue_mapping_v2(persisted)
        )
        connection.execute(
            "INSERT INTO st0504_queues VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(queue.queue_id),
                str(persisted.operation_id),
                str(queue.site_id),
                queue.source.sha256,
                persisted.payload_fingerprint,
                1,
                persisted.previous_chain_hash,
                persisted.chain_hash,
                str(persisted.event.event_id),
                payload,
                hashlib.sha256(payload).hexdigest(),
                persisted.committed_at.isoformat(timespec="microseconds"),
            ),
        )
        for pair in queue.pairs:
            pair_payload = _json_bytes(product_identity_candidate_pair_mapping_v2(pair))
            connection.execute(
                "INSERT INTO st0504_pairs VALUES (?,?,?,?,?)",
                (
                    str(pair.pair_id),
                    str(queue.queue_id),
                    pair.ordinal,
                    pair_payload,
                    pair.sha256,
                ),
            )
        connection.execute(
            "INSERT INTO st0504_state VALUES (?,?,?,?)",
            (str(queue.queue_id), _SCHEMA_BINDING, 1, persisted.chain_hash),
        )
        OwnerPrivateSqliteProductIdentityStoreV2._insert_outbox(
            connection, event=persisted.event
        )
        OwnerPrivateSqliteProductIdentityStoreV2._insert_journal_queue(
            connection, persisted=persisted
        )

    @staticmethod
    def _insert_outbox(
        connection: sqlite3.Connection,
        *,
        event: ProductIdentityOutboxEventV2,
    ) -> None:
        payload = _json_bytes(product_identity_outbox_event_mapping_v2(event))
        connection.execute(
            "INSERT INTO st0504_outbox VALUES (?,?,?,?,?,?,?,?)",
            (
                str(event.event_id),
                str(event.queue_id),
                event.aggregate_version,
                event.event_type,
                event.channel,
                payload,
                hashlib.sha256(payload).hexdigest(),
                event.occurred_at.isoformat(timespec="microseconds"),
            ),
        )

    @staticmethod
    def _insert_journal_queue(
        connection: sqlite3.Connection,
        *,
        persisted: PersistedProductIdentityReviewQueueV2,
    ) -> None:
        result = _json_bytes(
            persisted_product_identity_review_queue_mapping_v2(persisted)
        )
        connection.execute(
            "INSERT INTO st0504_journal VALUES (?,?,?,?,?,?,?,?)",
            (
                str(persisted.operation_id),
                ProductIdentityCommitKindV2.REVIEW_QUEUE.value,
                str(persisted.queue.queue_id),
                1,
                persisted.payload_fingerprint,
                result,
                hashlib.sha256(result).hexdigest(),
                persisted.committed_at.isoformat(timespec="microseconds"),
            ),
        )

    def recover_review_queue_commit(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> ProductIdentityQueueCommitRecoveryV2:
        persisted = self.lookup_review_queue(command)
        return ProductIdentityQueueCommitRecoveryV2(
            outcome=(
                ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
                if persisted is not None
                else ProductIdentityCommitRecoveryOutcomeV2.NOT_COMMITTED
            ),
            persisted=persisted,
        )

    def lookup_decision(
        self, command: ProductIdentityDecisionCommandV2
    ) -> PersistedProductIdentityDecisionV2 | None:
        if type(command) is not ProductIdentityDecisionCommandV2:
            fail_product_identity_runtime_v2()
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM st0504_journal WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            return None
        if (
            row["commit_kind"] != ProductIdentityCommitKindV2.HUMAN_DECISION.value
            or row["payload_fingerprint"] != command.payload_fingerprint
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
            )
        return persisted_product_identity_decision_from_mapping_v2(
            _json_object(_payload_from_row(row, prefix="result"))
        )

    def commit_decision(
        self,
        *,
        command: ProductIdentityDecisionCommandV2,
        decision: ProductIdentityHumanDecisionV2,
        event: ProductIdentityOutboxEventV2,
    ) -> PersistedProductIdentityDecisionV2:
        if (
            type(command) is not ProductIdentityDecisionCommandV2
            or type(decision) is not ProductIdentityHumanDecisionV2
            or type(event) is not ProductIdentityOutboxEventV2
            or command.queue_id != decision.queue_id
            or command.pair_id != decision.pair.pair_id
            or command.expected_history_version + 1 != decision.history_version
        ):
            fail_product_identity_runtime_v2()
        connection = self._connect()
        fault = self._next_fault()
        try:
            connection.execute("BEGIN IMMEDIATE")
            journal = connection.execute(
                "SELECT payload_fingerprint FROM st0504_journal WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if journal is not None:
                if journal["payload_fingerprint"] != command.payload_fingerprint:
                    fail_product_identity_runtime_v2(
                        ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                    )
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
                )
            queue_row = connection.execute(
                "SELECT * FROM st0504_queues WHERE queue_id = ?",
                (str(command.queue_id),),
            ).fetchone()
            state = connection.execute(
                "SELECT * FROM st0504_state WHERE queue_id = ?",
                (str(command.queue_id),),
            ).fetchone()
            if queue_row is None or state is None:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
                )
            queue_record = persisted_product_identity_review_queue_from_mapping_v2(
                _json_object(_payload_from_row(queue_row))
            )
            if (
                state["history_version"] != command.expected_history_version
                or state["head_hash"] is None
                or command.authorization.site_id != queue_record.queue.site_id
                or event
                != ProductIdentityOutboxEventV2.from_decision(
                    decision=decision,
                    queue=queue_record.queue,
                )
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
                )
            latest = connection.execute(
                "SELECT decision_id FROM st0504_decisions WHERE queue_id = ? AND pair_id = ? ORDER BY history_version DESC LIMIT 1",
                (str(command.queue_id), str(command.pair_id)),
            ).fetchone()
            latest_id = None if latest is None else UUID(latest["decision_id"])
            if (
                command.supersedes_decision_id != latest_id
                or decision.supersedes_decision_id != latest_id
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
                )
            previous = cast(str, state["head_hash"])
            chain_hash = product_identity_chain_hash_v2(
                previous_chain_hash=previous,
                commit_kind=ProductIdentityCommitKindV2.HUMAN_DECISION,
                queue_id=command.queue_id,
                history_version=decision.history_version,
                operation_id=command.operation_id,
                payload_sha256=decision.sha256,
                event_sha256=event.sha256,
                committed_at=decision.decided_at,
            )
            persisted = PersistedProductIdentityDecisionV2(
                operation_id=command.operation_id,
                payload_fingerprint=command.payload_fingerprint,
                history_version=decision.history_version,
                previous_chain_hash=previous,
                chain_hash=chain_hash,
                decision=decision,
                event=event,
                committed_at=decision.decided_at,
            )
            self._insert_decision(connection, persisted=persisted)
            updated = connection.execute(
                "UPDATE st0504_state SET history_version = ?, head_hash = ? WHERE queue_id = ? AND history_version = ? AND head_hash = ?",
                (
                    decision.history_version,
                    chain_hash,
                    str(command.queue_id),
                    command.expected_history_version,
                    previous,
                ),
            )
            if updated.rowcount != 1:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT
                )
            if fault in {
                ProductIdentitySqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
                ProductIdentitySqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            }:
                self._rollback(connection)
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_KNOWN_ROLLBACK
                    if fault is ProductIdentitySqliteCommitFaultV2.KNOWN_BEFORE_COMMIT
                    else ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            connection.execute("COMMIT")
            if fault is ProductIdentitySqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            return persisted
        except ProductIdentityRuntimeFailureV2:
            self._rollback(connection)
            raise
        except (ValueError, sqlite3.Error) as error:
            self._rollback(connection)
            if isinstance(error, sqlite3.Error):
                self._map_sqlite_error(error)
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        finally:
            connection.close()

    @staticmethod
    def _insert_decision(
        connection: sqlite3.Connection,
        *,
        persisted: PersistedProductIdentityDecisionV2,
    ) -> None:
        decision = persisted.decision
        payload = _json_bytes(persisted_product_identity_decision_mapping_v2(persisted))
        connection.execute(
            "INSERT INTO st0504_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(decision.decision_id),
                str(persisted.operation_id),
                str(decision.queue_id),
                str(decision.pair.pair_id),
                decision.history_version,
                None
                if decision.supersedes_decision_id is None
                else str(decision.supersedes_decision_id),
                persisted.payload_fingerprint,
                persisted.previous_chain_hash,
                persisted.chain_hash,
                str(persisted.event.event_id),
                payload,
                hashlib.sha256(payload).hexdigest(),
                persisted.committed_at.isoformat(timespec="microseconds"),
            ),
        )
        OwnerPrivateSqliteProductIdentityStoreV2._insert_outbox(
            connection, event=persisted.event
        )
        result = _json_bytes(persisted_product_identity_decision_mapping_v2(persisted))
        connection.execute(
            "INSERT INTO st0504_journal VALUES (?,?,?,?,?,?,?,?)",
            (
                str(persisted.operation_id),
                ProductIdentityCommitKindV2.HUMAN_DECISION.value,
                str(decision.queue_id),
                decision.history_version,
                persisted.payload_fingerprint,
                result,
                hashlib.sha256(result).hexdigest(),
                persisted.committed_at.isoformat(timespec="microseconds"),
            ),
        )

    def recover_decision_commit(
        self, command: ProductIdentityDecisionCommandV2
    ) -> ProductIdentityDecisionCommitRecoveryV2:
        persisted = self.lookup_decision(command)
        return ProductIdentityDecisionCommitRecoveryV2(
            outcome=(
                ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
                if persisted is not None
                else ProductIdentityCommitRecoveryOutcomeV2.NOT_COMMITTED
            ),
            persisted=persisted,
        )

    def load_review_queue(
        self, queue_id: object
    ) -> PersistedProductIdentityReviewQueueV2:
        identifier = self._identifier(queue_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_bytes, payload_sha256 FROM st0504_queues WHERE queue_id = ?",
                (identifier,),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
            )
        return persisted_product_identity_review_queue_from_mapping_v2(
            _json_object(_payload_from_row(row))
        )

    def list_decisions(
        self, queue_id: object
    ) -> tuple[PersistedProductIdentityDecisionV2, ...]:
        identifier = self._identifier(queue_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT payload_bytes, payload_sha256 FROM st0504_decisions WHERE queue_id = ? ORDER BY history_version",
                (identifier,),
            ).fetchall()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        return tuple(
            persisted_product_identity_decision_from_mapping_v2(
                _json_object(_payload_from_row(row))
            )
            for row in rows
        )

    def load_outbox(self, event_id: object) -> ProductIdentityOutboxEventV2:
        identifier = self._identifier(event_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_bytes, payload_sha256 FROM st0504_outbox WHERE event_id = ?",
                (identifier,),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
            )
        return product_identity_outbox_event_from_mapping_v2(
            _json_object(_payload_from_row(row))
        )

    def current_history_version(self, queue_id: object) -> int:
        identifier = self._identifier(queue_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT history_version FROM st0504_state WHERE queue_id = ?",
                (identifier,),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None or type(row["history_version"]) is not int:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT
            )
        return row["history_version"]


__all__ = [
    "OwnerPrivateSqliteProductIdentityStoreV2",
    "ProductIdentitySqliteCommitFaultV2",
]
