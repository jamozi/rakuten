"""Owner-private durable catalog normalization UoW for ST-0503 V2.

The adapter atomically persists one source snapshot, candidate/offer/
observation batch, an outbox event, CAS state, hash-chain entry, and command
journal.  It is local DEV/CI storage only and has no provider, network,
credential, worker, publication, staging, release, or Production capability.
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
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CATALOG_EVENT_CHANNEL_V2,
    CATALOG_EVENT_TYPE_V2,
    CATALOG_NORMALIZER_VERSION_V2,
    CatalogCandidateV2,
    CatalogCommitRecoveryOutcomeV2,
    CatalogCommitRecoveryV2,
    CatalogNormalizationBatchV2,
    CatalogNormalizationCommandV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogNormalizedOutboxEventV2,
    CatalogObservationV2,
    CatalogOfferV2,
    CatalogSourceSnapshotV2,
    PersistedCatalogNormalizationV2,
    catalog_candidate_from_mapping_v2,
    catalog_candidate_mapping_v2,
    catalog_chain_hash_v2,
    catalog_normalization_batch_from_mapping_v2,
    catalog_normalization_batch_mapping_v2,
    catalog_normalized_event_from_mapping_v2,
    catalog_normalized_event_mapping_v2,
    catalog_observation_from_mapping_v2,
    catalog_observation_mapping_v2,
    catalog_offer_from_mapping_v2,
    catalog_offer_mapping_v2,
    catalog_source_snapshot_from_mapping_v2,
    catalog_source_snapshot_mapping_v2,
    fail_catalog_normalization_runtime,
    persisted_catalog_normalization_from_mapping_v2,
    persisted_catalog_normalization_mapping_v2,
)


_DATABASE_NAME = "st0503-catalog-normalization.sqlite3"
_ZERO_HASH = "0" * 64
_SCHEMA_VERSION = 2
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 40
_MAX_JSON_NODES = 100_000

_SCHEMA_CREATE_SQL: tuple[tuple[str, str], ...] = (
    (
        "st0503_state",
        """CREATE TABLE st0503_state (
    state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    catalog_version INTEGER NOT NULL CHECK (catalog_version >= 0),
    head_hash TEXT NOT NULL CHECK (length(head_hash) = 64)
) STRICT""",
    ),
    (
        "st0503_snapshots",
        """CREATE TABLE st0503_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    receipt_id TEXT NOT NULL,
    normalizer_version TEXT NOT NULL CHECK (normalizer_version = 'ST0503_RECORDED_STRUCTURAL_V2'),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(receipt_id, normalizer_version)
) STRICT""",
    ),
    (
        "st0503_batches",
        """CREATE TABLE st0503_batches (
    batch_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    source_snapshot_id TEXT NOT NULL UNIQUE,
    expected_catalog_version INTEGER NOT NULL CHECK (expected_catalog_version >= 0),
    catalog_version INTEGER NOT NULL UNIQUE CHECK (catalog_version >= 1),
    command_fingerprint TEXT NOT NULL CHECK (length(command_fingerprint) = 64),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    previous_chain_hash TEXT NOT NULL CHECK (length(previous_chain_hash) = 64),
    chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
    event_id TEXT NOT NULL UNIQUE,
    committed_at TEXT NOT NULL,
    FOREIGN KEY(source_snapshot_id) REFERENCES st0503_snapshots(snapshot_id)
) STRICT""",
    ),
    (
        "st0503_candidates",
        """CREATE TABLE st0503_candidates (
    candidate_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 30),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(batch_id, ordinal),
    FOREIGN KEY(batch_id) REFERENCES st0503_batches(batch_id),
    FOREIGN KEY(source_snapshot_id) REFERENCES st0503_snapshots(snapshot_id)
) STRICT""",
    ),
    (
        "st0503_offers",
        """CREATE TABLE st0503_offers (
    offer_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 30),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(batch_id, ordinal),
    FOREIGN KEY(batch_id) REFERENCES st0503_batches(batch_id),
    FOREIGN KEY(source_snapshot_id) REFERENCES st0503_snapshots(snapshot_id)
) STRICT""",
    ),
    (
        "st0503_observations",
        """CREATE TABLE st0503_observations (
    observation_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 120),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(batch_id, ordinal),
    FOREIGN KEY(batch_id) REFERENCES st0503_batches(batch_id),
    FOREIGN KEY(offer_id) REFERENCES st0503_offers(offer_id),
    FOREIGN KEY(source_snapshot_id) REFERENCES st0503_snapshots(snapshot_id)
) STRICT""",
    ),
    (
        "st0503_outbox",
        """CREATE TABLE st0503_outbox (
    event_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL CHECK (event_type = 'jp.raos.catalog.candidates_normalized.v1'),
    channel TEXT NOT NULL CHECK (channel = 'ingestion.events'),
    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES st0503_batches(batch_id)
) STRICT""",
    ),
    (
        "st0503_journal",
        """CREATE TABLE st0503_journal (
    operation_id TEXT PRIMARY KEY,
    payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64),
    batch_id TEXT NOT NULL UNIQUE,
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES st0503_batches(batch_id)
) STRICT""",
    ),
)

_APPEND_ONLY_TABLES = (
    "st0503_snapshots",
    "st0503_batches",
    "st0503_candidates",
    "st0503_offers",
    "st0503_observations",
    "st0503_outbox",
    "st0503_journal",
)


def _immutable_trigger_sql(table: str, operation: str) -> str:
    return (
        f"CREATE TRIGGER {table}_no_{operation} "
        f"BEFORE {operation.upper()} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ST0503_V2'); END"
    )


_SCHEMA_TRIGGER_SQL: tuple[tuple[str, str], ...] = (
    *(
        (f"{table}_no_{operation}", _immutable_trigger_sql(table, operation))
        for table in _APPEND_ONLY_TABLES
        for operation in ("update", "delete")
    ),
    (
        "st0503_state_no_insert",
        _immutable_trigger_sql("st0503_state", "insert"),
    ),
    (
        "st0503_state_no_delete",
        _immutable_trigger_sql("st0503_state", "delete"),
    ),
)

_SCHEMA_BINDING = hashlib.sha256(
    "\n".join(
        f"{kind}\0{name}\0{sql}"
        for kind, definitions in (
            ("table", _SCHEMA_CREATE_SQL),
            ("trigger", _SCHEMA_TRIGGER_SQL),
        )
        for name, sql in definitions
    ).encode("utf-8")
).hexdigest()

_AUTO_INDEX_COUNTS: dict[str, int] = {
    "st0503_state": 0,
    "st0503_snapshots": 3,
    "st0503_batches": 5,
    "st0503_candidates": 2,
    "st0503_offers": 2,
    "st0503_observations": 2,
    "st0503_outbox": 2,
    "st0503_journal": 2,
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
    "st0503_state": (
        ("state_id", "INTEGER", 0, 1, 0),
        ("schema_binding", "TEXT", 1, 0, 0),
        ("catalog_version", "INTEGER", 1, 0, 0),
        ("head_hash", "TEXT", 1, 0, 0),
    ),
    "st0503_snapshots": (
        ("snapshot_id", "TEXT", 1, 1, 0),
        ("operation_id", "TEXT", 1, 0, 0),
        ("receipt_id", "TEXT", 1, 0, 0),
        ("normalizer_version", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0503_batches": (
        ("batch_id", "TEXT", 1, 1, 0),
        ("operation_id", "TEXT", 1, 0, 0),
        ("source_snapshot_id", "TEXT", 1, 0, 0),
        ("expected_catalog_version", "INTEGER", 1, 0, 0),
        ("catalog_version", "INTEGER", 1, 0, 0),
        ("command_fingerprint", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("previous_chain_hash", "TEXT", 1, 0, 0),
        ("chain_hash", "TEXT", 1, 0, 0),
        ("event_id", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
    "st0503_candidates": (
        ("candidate_id", "TEXT", 1, 1, 0),
        ("batch_id", "TEXT", 1, 0, 0),
        ("source_snapshot_id", "TEXT", 1, 0, 0),
        ("ordinal", "INTEGER", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0503_offers": (
        ("offer_id", "TEXT", 1, 1, 0),
        ("batch_id", "TEXT", 1, 0, 0),
        ("source_snapshot_id", "TEXT", 1, 0, 0),
        ("ordinal", "INTEGER", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0503_observations": (
        ("observation_id", "TEXT", 1, 1, 0),
        ("batch_id", "TEXT", 1, 0, 0),
        ("offer_id", "TEXT", 1, 0, 0),
        ("source_snapshot_id", "TEXT", 1, 0, 0),
        ("ordinal", "INTEGER", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0503_outbox": (
        ("event_id", "TEXT", 1, 1, 0),
        ("batch_id", "TEXT", 1, 0, 0),
        ("event_type", "TEXT", 1, 0, 0),
        ("channel", "TEXT", 1, 0, 0),
        ("aggregate_version", "INTEGER", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("created_at", "TEXT", 1, 0, 0),
    ),
    "st0503_journal": (
        ("operation_id", "TEXT", 1, 1, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("batch_id", "TEXT", 1, 0, 0),
        ("result_bytes", "BLOB", 1, 0, 0),
        ("result_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
}

_SCHEMA_FOREIGN_KEYS: dict[str, frozenset[tuple[str, str, str, str, str, str]]] = {
    "st0503_state": frozenset(),
    "st0503_snapshots": frozenset(),
    "st0503_batches": frozenset(
        {
            (
                "st0503_snapshots",
                "source_snapshot_id",
                "snapshot_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        }
    ),
    "st0503_candidates": frozenset(
        {
            (
                "st0503_batches",
                "batch_id",
                "batch_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
            (
                "st0503_snapshots",
                "source_snapshot_id",
                "snapshot_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
        }
    ),
    "st0503_offers": frozenset(
        {
            (
                "st0503_batches",
                "batch_id",
                "batch_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
            (
                "st0503_snapshots",
                "source_snapshot_id",
                "snapshot_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
        }
    ),
    "st0503_observations": frozenset(
        {
            (
                "st0503_batches",
                "batch_id",
                "batch_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
            (
                "st0503_offers",
                "offer_id",
                "offer_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
            (
                "st0503_snapshots",
                "source_snapshot_id",
                "snapshot_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
        }
    ),
    "st0503_outbox": frozenset(
        {
            (
                "st0503_batches",
                "batch_id",
                "batch_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        }
    ),
    "st0503_journal": frozenset(
        {
            (
                "st0503_batches",
                "batch_id",
                "batch_id",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            )
        }
    ),
}

_SCHEMA_INITIALIZATION_LOCK = RLock()


class CatalogNormalizationSqliteCommitFaultV2(str, Enum):
    NONE = "NONE"
    KNOWN_BEFORE_COMMIT = "KNOWN_BEFORE_COMMIT"
    UNKNOWN_BEFORE_COMMIT = "UNKNOWN_BEFORE_COMMIT"
    UNKNOWN_AFTER_COMMIT = "UNKNOWN_AFTER_COMMIT"


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_catalog_normalization_runtime()
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
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    if not payload or len(payload) > _MAX_JSON_BYTES:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return payload


def _reject_constant(_value: str) -> NoReturn:
    fail_catalog_normalization_runtime(
        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
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
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
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
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )


def _json_object(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > _MAX_JSON_BYTES:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
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
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    _validate_json_tree(value)
    if type(value) is not dict:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    result = {cast(str, key): item for key, item in raw.items()}
    if _json_bytes(result) != payload:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return result


def _payload_from_row(row: sqlite3.Row, *, prefix: str = "payload") -> bytes:
    payload = row[f"{prefix}_bytes"]
    digest = row[f"{prefix}_sha256"]
    if (
        type(payload) is not bytes
        or type(digest) is not str
        or hashlib.sha256(payload).hexdigest() != digest
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
        )
    return payload


def _validate_root_path(root: object) -> Path:
    if type(root) is not type(Path()) or not root.is_absolute() or ".." in root.parts:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
        )
    normalized = Path(os.path.abspath(root))
    if normalized != root:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
        )
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
            )
        if stat.S_ISLNK(metadata.st_mode):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
            )
    return root


def _validate_private_directory(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError:
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
        )
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
        )


@final
class OwnerPrivateSqliteCatalogNormalizationStoreV2:
    """Fixed-path local repository and single-transaction UoW."""

    __slots__ = (
        "_commit_fault_index",
        "_commit_faults",
        "_database",
        "_database_identity",
        "_fault_lock",
        "_pinned_catalog_version",
        "_pinned_head_hash",
        "_root",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        root: Path,
        commit_faults: tuple[CatalogNormalizationSqliteCommitFaultV2, ...] = (),
    ) -> None:
        _environment(environment)
        if type(commit_faults) is not tuple or any(
            type(value) is not CatalogNormalizationSqliteCommitFaultV2
            for value in commit_faults
        ):
            fail_catalog_normalization_runtime()
        private_root = _validate_root_path(root)
        try:
            os.mkdir(private_root, 0o700)
        except FileExistsError:
            pass
        except OSError:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
            )
        _validate_private_directory(private_root)
        self._root = private_root
        self._database = private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] | None = None
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        self._fault_lock = RLock()
        self._state_lock = RLock()
        self._pinned_catalog_version = 0
        self._pinned_head_hash = _ZERO_HASH
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(allow_create=True)
            self._database_identity = identity
            connection = self._connect(verify=False)
            try:
                self._initialize(connection, created=created)
            finally:
                self._close_safely(connection)
            connection = self._connect(verify=False)
            try:
                self._verify_schema(connection)
                version, head = self._verify_integrity(connection)
                self._validate_database_identity()
                self._pin_state(catalog_version=version, head_hash=head)
            finally:
                self._close_safely(connection)

    @property
    def database_path(self) -> Path:
        return self._database

    @property
    def external_action_count(self) -> int:
        return 0

    @property
    def current_version(self) -> int:
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT catalog_version FROM st0503_state WHERE state_id = 1"
                ).fetchone()
                version, head = self._verified_state(connection)
                if row is None or row["catalog_version"] != version:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                self._pin_state(catalog_version=version, head_hash=head)
                return version
            except CatalogNormalizationRuntimeFailure:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

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
            path_metadata = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (path_metadata.st_dev, path_metadata.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
                )
            if created:
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            return created, (metadata.st_dev, metadata.st_ino)
        except CatalogNormalizationRuntimeFailure:
            raise
        except OSError:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH
            )
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self) -> None:
        _created, identity = self._open_database_file(allow_create=False)
        if self._database_identity is None or identity != self._database_identity:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        self._validate_database_identity()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self._database.as_uri()}?mode=rw",
                uri=True,
                timeout=0.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA busy_timeout = 0")
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            trusted_schema = connection.execute("PRAGMA trusted_schema").fetchone()
            if (
                journal_mode is None
                or tuple(journal_mode) != ("delete",)
                or foreign_keys is None
                or tuple(foreign_keys) != (1,)
                or trusted_schema is None
                or tuple(trusted_schema) != (0,)
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
                )
            self._validate_database_identity()
        except sqlite3.OperationalError:
            if connection is not None:
                self._close_safely(connection)
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
            )
        except sqlite3.Error:
            if connection is not None:
                self._close_safely(connection)
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
            )
        except CatalogNormalizationRuntimeFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        if verify:
            try:
                self._verify_schema(connection)
                version, head = self._verify_integrity(connection)
                self._require_monotonic_state(
                    connection,
                    catalog_version=version,
                    head_hash=head,
                )
                self._validate_database_identity()
            except CatalogNormalizationRuntimeFailure:
                self._close_safely(connection)
                raise
        return connection

    def _initialize(self, connection: sqlite3.Connection, *, created: bool) -> None:
        if not created:
            self._verify_schema(connection)
            self._verify_integrity(connection)
            self._validate_database_identity()
            return
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.Error:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
            )
        if version is None or tuple(version) != (0,):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
            )
        try:
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if existing is None or existing[0] != 0:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
            connection.execute("BEGIN IMMEDIATE")
            self._validate_database_identity()
            for _table, statement in _SCHEMA_CREATE_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO st0503_state(state_id, schema_binding, catalog_version, head_hash) VALUES (1, ?, 0, ?)",
                (_SCHEMA_BINDING, _ZERO_HASH),
            )
            for _trigger, statement in _SCHEMA_TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._validate_database_identity()
            connection.execute("COMMIT")
            self._validate_database_identity()
        except CatalogNormalizationRuntimeFailure:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
            )
        self._verify_schema(connection)
        self._verify_integrity(connection)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or version[0] != _SCHEMA_VERSION:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
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
                *(
                    ("trigger", name, name.rsplit("_no_", 1)[0], statement)
                    for name, statement in _SCHEMA_TRIGGER_SQL
                ),
                *_SCHEMA_AUTO_INDEXES,
            }
            if observed_objects != expected_objects:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
            for table, expected in _SCHEMA_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_xinfo({table})").fetchall()
                observed = tuple(
                    (row[1], row[2], row[3], row[5], row[6]) for row in rows
                )
                if observed != expected:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                    )
            strict_rows = connection.execute("PRAGMA table_list").fetchall()
            strict_by_name = {
                row[1]: row[5] for row in strict_rows if row[1] in _SCHEMA_COLUMNS
            }
            if strict_by_name != {name: 1 for name in _SCHEMA_COLUMNS}:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
            foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys_enabled is None or tuple(foreign_keys_enabled) != (1,):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
            for table, expected_foreign_keys in _SCHEMA_FOREIGN_KEYS.items():
                rows = connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
                observed_foreign_keys = tuple(
                    (row[2], row[3], row[4], row[5], row[6], row[7]) for row in rows
                )
                if (
                    len(observed_foreign_keys) != len(expected_foreign_keys)
                    or frozenset(observed_foreign_keys) != expected_foreign_keys
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                    )
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
            quick_check = connection.execute("PRAGMA quick_check").fetchall()
            if tuple(tuple(row) for row in quick_check) != (("ok",),):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
                )
        except CatalogNormalizationRuntimeFailure:
            raise
        except sqlite3.Error:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY
            )

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> tuple[int, str]:
        try:
            integrity_check = connection.execute("PRAGMA integrity_check").fetchall()
            if tuple(tuple(row) for row in integrity_check) != (("ok",),):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            state = connection.execute(
                "SELECT schema_binding, catalog_version, head_hash FROM st0503_state WHERE state_id = 1"
            ).fetchone()
            state_count = connection.execute(
                "SELECT COUNT(*) FROM st0503_state"
            ).fetchone()
            if (
                state is None
                or state_count is None
                or state_count[0] != 1
                or state["schema_binding"] != _SCHEMA_BINDING
                or type(state["catalog_version"]) is not int
                or type(state["head_hash"]) is not str
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            rows = connection.execute(
                "SELECT * FROM st0503_batches ORDER BY catalog_version"
            ).fetchall()
            previous = _ZERO_HASH
            expected_version = 1
            candidate_total = 0
            offer_total = 0
            observation_total = 0
            for row in rows:
                if (
                    row["catalog_version"] != expected_version
                    or row["expected_catalog_version"] != expected_version - 1
                    or row["previous_chain_hash"] != previous
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                batch = catalog_normalization_batch_from_mapping_v2(
                    _json_object(_payload_from_row(row))
                )
                if (
                    tuple(row.keys())
                    != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_batches"])
                    or row["batch_id"] != str(batch.batch_id)
                    or row["operation_id"] != str(batch.operation_id)
                    or row["source_snapshot_id"]
                    != str(batch.source_snapshot.snapshot_id)
                    or row["command_fingerprint"] != batch.command_fingerprint
                    or row["payload_sha256"] != batch.sha256
                    or row["event_id"]
                    != str(CatalogNormalizedOutboxEventV2.from_batch(batch).event_id)
                    or row["committed_at"]
                    != batch.source_snapshot.normalized_at.isoformat(
                        timespec="microseconds"
                    )
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                snapshot_row = connection.execute(
                    "SELECT * FROM st0503_snapshots WHERE snapshot_id = ?",
                    (str(batch.source_snapshot.snapshot_id),),
                ).fetchone()
                if snapshot_row is None:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                snapshot_payload = _payload_from_row(snapshot_row)
                snapshot = catalog_source_snapshot_from_mapping_v2(
                    _json_object(snapshot_payload)
                )
                if (
                    tuple(snapshot_row.keys())
                    != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_snapshots"])
                    or snapshot != batch.source_snapshot
                    or snapshot_row["operation_id"] != str(batch.operation_id)
                    or snapshot_row["receipt_id"] != str(snapshot.receipt_id)
                    or snapshot_row["normalizer_version"]
                    != CATALOG_NORMALIZER_VERSION_V2
                    or _json_bytes(catalog_source_snapshot_mapping_v2(snapshot))
                    != snapshot_payload
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                candidates = (
                    OwnerPrivateSqliteCatalogNormalizationStoreV2._batch_candidates(
                        connection, batch.batch_id
                    )
                )
                offers = OwnerPrivateSqliteCatalogNormalizationStoreV2._batch_offers(
                    connection, batch.batch_id
                )
                observations = (
                    OwnerPrivateSqliteCatalogNormalizationStoreV2._batch_observations(
                        connection, batch.batch_id
                    )
                )
                if (
                    candidates != batch.candidates
                    or offers != batch.offers
                    or observations != batch.observations
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                candidate_total += len(candidates)
                offer_total += len(offers)
                observation_total += len(observations)
                event_row = connection.execute(
                    "SELECT * FROM st0503_outbox WHERE event_id = ?",
                    (row["event_id"],),
                ).fetchone()
                if event_row is None:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                event = catalog_normalized_event_from_mapping_v2(
                    _json_object(_payload_from_row(event_row))
                )
                if (
                    tuple(event_row.keys())
                    != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_outbox"])
                    or event != CatalogNormalizedOutboxEventV2.from_batch(batch)
                    or event_row["batch_id"] != str(batch.batch_id)
                    or event_row["event_type"] != CATALOG_EVENT_TYPE_V2
                    or event_row["channel"] != CATALOG_EVENT_CHANNEL_V2
                    or event_row["aggregate_version"] != expected_version
                    or event_row["payload_sha256"] != event.sha256
                    or event_row["created_at"]
                    != event.occurred_at.isoformat(timespec="microseconds")
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                expected_chain = catalog_chain_hash_v2(
                    previous_chain_hash=previous,
                    catalog_version=expected_version,
                    operation_id=batch.operation_id,
                    batch_sha256=batch.sha256,
                    event_sha256=event.sha256,
                    committed_at=batch.source_snapshot.normalized_at,
                )
                if row["chain_hash"] != expected_chain:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                journal = connection.execute(
                    "SELECT * FROM st0503_journal WHERE operation_id = ?",
                    (str(batch.operation_id),),
                ).fetchone()
                if journal is None:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                result_payload = _payload_from_row(journal, prefix="result")
                result = persisted_catalog_normalization_from_mapping_v2(
                    _json_object(result_payload)
                )
                if (
                    tuple(journal.keys())
                    != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_journal"])
                    or result.operation_id != batch.operation_id
                    or result.batch != batch
                    or result.event != event
                    or result.catalog_version != expected_version
                    or result.chain_hash != expected_chain
                    or journal["payload_fingerprint"] != batch.command_fingerprint
                    or journal["batch_id"] != str(batch.batch_id)
                    or journal["committed_at"]
                    != result.committed_at.isoformat(timespec="microseconds")
                    or _json_bytes(persisted_catalog_normalization_mapping_v2(result))
                    != result_payload
                ):
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
                previous = expected_chain
                expected_version += 1
            counts = {
                "st0503_snapshots": len(rows),
                "st0503_candidates": candidate_total,
                "st0503_offers": offer_total,
                "st0503_observations": observation_total,
                "st0503_outbox": len(rows),
                "st0503_journal": len(rows),
            }
            for table, expected_count in counts.items():
                observed_count = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()
                if observed_count is None or observed_count[0] != expected_count:
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                    )
            if state["catalog_version"] != len(rows) or state["head_hash"] != previous:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            return len(rows), previous
        except CatalogNormalizationRuntimeFailure:
            raise
        except sqlite3.Error:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )

    def _require_monotonic_state(
        self,
        connection: sqlite3.Connection,
        *,
        catalog_version: int,
        head_hash: str,
    ) -> None:
        if catalog_version < self._pinned_catalog_version:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )
        if self._pinned_catalog_version == 0:
            if self._pinned_head_hash != _ZERO_HASH:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
        else:
            pinned = connection.execute(
                "SELECT chain_hash FROM st0503_batches WHERE catalog_version = ?",
                (self._pinned_catalog_version,),
            ).fetchone()
            if pinned is None or pinned["chain_hash"] != self._pinned_head_hash:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
        if (
            catalog_version == self._pinned_catalog_version
            and head_hash != self._pinned_head_hash
        ):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )

    def _pin_state(self, *, catalog_version: int, head_hash: str) -> None:
        if catalog_version < self._pinned_catalog_version:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
            )
        self._pinned_catalog_version = catalog_version
        self._pinned_head_hash = head_hash

    def _verified_state(self, connection: sqlite3.Connection) -> tuple[int, str]:
        self._validate_database_identity()
        self._verify_schema(connection)
        version, head = self._verify_integrity(connection)
        self._require_monotonic_state(
            connection,
            catalog_version=version,
            head_hash=head,
        )
        self._validate_database_identity()
        return version, head

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _next_fault(self) -> CatalogNormalizationSqliteCommitFaultV2:
        with self._fault_lock:
            fault = (
                self._commit_faults[self._commit_fault_index]
                if self._commit_fault_index < len(self._commit_faults)
                else CatalogNormalizationSqliteCommitFaultV2.NONE
            )
            self._commit_fault_index += 1
            return fault

    def _finish_commit(self, connection: sqlite3.Connection) -> None:
        fault = self._next_fault()
        if fault is CatalogNormalizationSqliteCommitFaultV2.KNOWN_BEFORE_COMMIT:
            self._rollback(connection)
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_KNOWN_ROLLBACK
            )
        if fault is CatalogNormalizationSqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT:
            self._rollback(connection)
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        commit_failed = False
        try:
            connection.execute("COMMIT")
        except sqlite3.Error:
            commit_failed = True
        if commit_failed:
            self._validate_database_identity()
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )
        self._validate_database_identity()
        if fault is CatalogNormalizationSqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
            )

    def _rollback(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        self._validate_database_identity()

    @staticmethod
    def _map_sqlite_error(error: sqlite3.Error) -> NoReturn:
        if isinstance(error, sqlite3.IntegrityError):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
            )
        if isinstance(error, sqlite3.OperationalError):
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
            )
        fail_catalog_normalization_runtime(
            CatalogNormalizationRuntimeFailureCode.STORE_UNAVAILABLE
        )

    def lookup(
        self,
        command: CatalogNormalizationCommandV2,
    ) -> PersistedCatalogNormalizationV2 | None:
        if type(command) is not CatalogNormalizationCommandV2:
            fail_catalog_normalization_runtime()
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT payload_fingerprint, result_bytes, result_sha256 FROM st0503_journal WHERE operation_id = ?",
                    (str(command.operation_id),),
                ).fetchone()
                if row is None:
                    result = None
                else:
                    if row["payload_fingerprint"] != command.payload_fingerprint:
                        fail_catalog_normalization_runtime(
                            CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                        )
                    result = self._decode_result_row(row)
                version, head = self._verified_state(connection)
                self._pin_state(catalog_version=version, head_hash=head)
                return result
            except CatalogNormalizationRuntimeFailure:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    @staticmethod
    def _decode_result_row(row: sqlite3.Row) -> PersistedCatalogNormalizationV2:
        return persisted_catalog_normalization_from_mapping_v2(
            _json_object(_payload_from_row(row, prefix="result"))
        )

    def commit(
        self,
        *,
        command: CatalogNormalizationCommandV2,
        batch: CatalogNormalizationBatchV2,
        event: CatalogNormalizedOutboxEventV2,
    ) -> PersistedCatalogNormalizationV2:
        if (
            type(command) is not CatalogNormalizationCommandV2
            or type(batch) is not CatalogNormalizationBatchV2
            or type(event) is not CatalogNormalizedOutboxEventV2
            or batch.operation_id != command.operation_id
            or batch.command_fingerprint != command.payload_fingerprint
            or batch.expected_catalog_version != command.expected_catalog_version
            or event != CatalogNormalizedOutboxEventV2.from_batch(batch)
        ):
            fail_catalog_normalization_runtime()
        with self._state_lock:
            return self._commit_locked(command=command, batch=batch, event=event)

    def _commit_locked(
        self,
        *,
        command: CatalogNormalizationCommandV2,
        batch: CatalogNormalizationBatchV2,
        event: CatalogNormalizedOutboxEventV2,
    ) -> PersistedCatalogNormalizationV2:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            starting_version, starting_head = self._verified_state(connection)
            existing = connection.execute(
                "SELECT payload_fingerprint, result_bytes, result_sha256 FROM st0503_journal WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if existing is not None:
                if existing["payload_fingerprint"] != command.payload_fingerprint:
                    self._rollback(connection)
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                    )
                result = self._decode_result_row(existing)
                if result.batch != batch or result.event != event:
                    self._rollback(connection)
                    fail_catalog_normalization_runtime(
                        CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                    )
                self._rollback(connection)
                version, head = self._verified_state(connection)
                self._pin_state(catalog_version=version, head_hash=head)
                return result
            duplicate_source = connection.execute(
                "SELECT operation_id FROM st0503_snapshots WHERE receipt_id = ? AND normalizer_version = ?",
                (
                    str(batch.source_snapshot.receipt_id),
                    CATALOG_NORMALIZER_VERSION_V2,
                ),
            ).fetchone()
            if duplicate_source is not None:
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                )
            state = connection.execute(
                "SELECT catalog_version, head_hash FROM st0503_state WHERE state_id = 1"
            ).fetchone()
            if state is None:
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            if (
                starting_version != command.expected_catalog_version
                or state["catalog_version"] != starting_version
                or state["head_hash"] != starting_head
            ):
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
                )
            previous_hash = starting_head
            if type(previous_hash) is not str:
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            version = command.expected_catalog_version + 1
            chain_hash = catalog_chain_hash_v2(
                previous_chain_hash=previous_hash,
                catalog_version=version,
                operation_id=command.operation_id,
                batch_sha256=batch.sha256,
                event_sha256=event.sha256,
                committed_at=command.normalized_at,
            )
            result = PersistedCatalogNormalizationV2(
                operation_id=command.operation_id,
                payload_fingerprint=command.payload_fingerprint,
                catalog_version=version,
                previous_chain_hash=previous_hash,
                chain_hash=chain_hash,
                batch=batch,
                event=event,
                committed_at=command.normalized_at,
            )
            self._insert_snapshot(connection, command=command, batch=batch)
            self._insert_batch(
                connection,
                result=result,
            )
            self._insert_records(connection, batch=batch)
            self._insert_outbox(connection, event=event, batch=batch)
            result_payload = _json_bytes(
                persisted_catalog_normalization_mapping_v2(result)
            )
            connection.execute(
                "INSERT INTO st0503_journal(operation_id, payload_fingerprint, batch_id, result_bytes, result_sha256, committed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(command.operation_id),
                    command.payload_fingerprint,
                    str(batch.batch_id),
                    result_payload,
                    hashlib.sha256(result_payload).hexdigest(),
                    command.normalized_at.isoformat(timespec="microseconds"),
                ),
            )
            updated = connection.execute(
                "UPDATE st0503_state SET catalog_version = ?, head_hash = ? WHERE state_id = 1 AND catalog_version = ? AND head_hash = ?",
                (
                    version,
                    chain_hash,
                    command.expected_catalog_version,
                    previous_hash,
                ),
            )
            if updated.rowcount != 1:
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
                )
            appended_version, appended_head = self._verified_state(connection)
            if appended_version != version or appended_head != chain_hash:
                self._rollback(connection)
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            self._validate_database_identity()
            self._finish_commit(connection)
            self._validate_database_identity()
            durable_version, durable_head = self._verified_state(connection)
            if durable_version != version or durable_head != chain_hash:
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN
                )
            self._pin_state(
                catalog_version=durable_version,
                head_hash=durable_head,
            )
            return result
        except CatalogNormalizationRuntimeFailure:
            raise
        except sqlite3.Error as error:
            self._rollback(connection)
            self._map_sqlite_error(error)
        finally:
            self._close_safely(connection)

    @staticmethod
    def _insert_snapshot(
        connection: sqlite3.Connection,
        *,
        command: CatalogNormalizationCommandV2,
        batch: CatalogNormalizationBatchV2,
    ) -> None:
        snapshot = batch.source_snapshot
        payload = _json_bytes(catalog_source_snapshot_mapping_v2(snapshot))
        connection.execute(
            "INSERT INTO st0503_snapshots(snapshot_id, operation_id, receipt_id, normalizer_version, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(snapshot.snapshot_id),
                str(command.operation_id),
                str(snapshot.receipt_id),
                snapshot.normalizer_version,
                payload,
                hashlib.sha256(payload).hexdigest(),
            ),
        )

    @staticmethod
    def _insert_batch(
        connection: sqlite3.Connection,
        *,
        result: PersistedCatalogNormalizationV2,
    ) -> None:
        batch = result.batch
        payload = _json_bytes(catalog_normalization_batch_mapping_v2(batch))
        connection.execute(
            "INSERT INTO st0503_batches(batch_id, operation_id, source_snapshot_id, expected_catalog_version, catalog_version, command_fingerprint, payload_bytes, payload_sha256, previous_chain_hash, chain_hash, event_id, committed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(batch.batch_id),
                str(batch.operation_id),
                str(batch.source_snapshot.snapshot_id),
                batch.expected_catalog_version,
                result.catalog_version,
                batch.command_fingerprint,
                payload,
                hashlib.sha256(payload).hexdigest(),
                result.previous_chain_hash,
                result.chain_hash,
                str(result.event.event_id),
                result.committed_at.isoformat(timespec="microseconds"),
            ),
        )

    @staticmethod
    def _insert_records(
        connection: sqlite3.Connection,
        *,
        batch: CatalogNormalizationBatchV2,
    ) -> None:
        for candidate in batch.candidates:
            payload = _json_bytes(catalog_candidate_mapping_v2(candidate))
            connection.execute(
                "INSERT INTO st0503_candidates(candidate_id, batch_id, source_snapshot_id, ordinal, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(candidate.candidate_id),
                    str(batch.batch_id),
                    str(candidate.source_snapshot_id),
                    candidate.ordinal,
                    payload,
                    hashlib.sha256(payload).hexdigest(),
                ),
            )
        for offer in batch.offers:
            payload = _json_bytes(catalog_offer_mapping_v2(offer))
            connection.execute(
                "INSERT INTO st0503_offers(offer_id, batch_id, source_snapshot_id, ordinal, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(offer.offer_id),
                    str(batch.batch_id),
                    str(offer.source_snapshot_id),
                    offer.ordinal,
                    payload,
                    hashlib.sha256(payload).hexdigest(),
                ),
            )
        for observation in batch.observations:
            payload = _json_bytes(catalog_observation_mapping_v2(observation))
            connection.execute(
                "INSERT INTO st0503_observations(observation_id, batch_id, offer_id, source_snapshot_id, ordinal, payload_bytes, payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(observation.observation_id),
                    str(batch.batch_id),
                    str(observation.offer_id),
                    str(observation.source_snapshot_id),
                    observation.ordinal,
                    payload,
                    hashlib.sha256(payload).hexdigest(),
                ),
            )

    @staticmethod
    def _insert_outbox(
        connection: sqlite3.Connection,
        *,
        event: CatalogNormalizedOutboxEventV2,
        batch: CatalogNormalizationBatchV2,
    ) -> None:
        payload = _json_bytes(catalog_normalized_event_mapping_v2(event))
        connection.execute(
            "INSERT INTO st0503_outbox(event_id, batch_id, event_type, channel, aggregate_version, payload_bytes, payload_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(event.event_id),
                str(batch.batch_id),
                event.event_type,
                event.channel,
                event.aggregate_version,
                payload,
                hashlib.sha256(payload).hexdigest(),
                event.occurred_at.isoformat(timespec="microseconds"),
            ),
        )

    def recover_commit(
        self,
        command: CatalogNormalizationCommandV2,
    ) -> CatalogCommitRecoveryV2:
        persisted = self.lookup(command)
        return CatalogCommitRecoveryV2(
            outcome=(
                CatalogCommitRecoveryOutcomeV2.COMMITTED
                if persisted is not None
                else CatalogCommitRecoveryOutcomeV2.NOT_COMMITTED
            ),
            persisted=persisted,
        )

    def _read_one(self, query: str, identifier: str) -> sqlite3.Row | None:
        with self._state_lock:
            connection = self._connect()
            try:
                row = cast(
                    sqlite3.Row | None,
                    connection.execute(query, (identifier,)).fetchone(),
                )
                version, head = self._verified_state(connection)
                self._pin_state(catalog_version=version, head_hash=head)
                return row
            except CatalogNormalizationRuntimeFailure:
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
                version, head = self._verified_state(connection)
                self._pin_state(catalog_version=version, head_hash=head)
                return rows
            except CatalogNormalizationRuntimeFailure:
                raise
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def load_batch(self, batch_id: object) -> CatalogNormalizationBatchV2:
        identifier = self._identifier(batch_id)
        row = self._read_one(
            "SELECT payload_bytes, payload_sha256 FROM st0503_batches WHERE batch_id = ?",
            identifier,
        )
        if row is None:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STATE_CONFLICT
            )
        return catalog_normalization_batch_from_mapping_v2(
            _json_object(_payload_from_row(row))
        )

    def load_snapshot(self, snapshot_id: object) -> CatalogSourceSnapshotV2:
        identifier = self._identifier(snapshot_id)
        row = self._read_one(
            "SELECT payload_bytes, payload_sha256 FROM st0503_snapshots WHERE snapshot_id = ?",
            identifier,
        )
        if row is None:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STATE_CONFLICT
            )
        return catalog_source_snapshot_from_mapping_v2(
            _json_object(_payload_from_row(row))
        )

    def load_candidate(self, candidate_id: object) -> CatalogCandidateV2:
        identifier = self._identifier(candidate_id)
        row = self._read_one(
            "SELECT payload_bytes, payload_sha256 FROM st0503_candidates WHERE candidate_id = ?",
            identifier,
        )
        if row is None:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STATE_CONFLICT
            )
        return catalog_candidate_from_mapping_v2(_json_object(_payload_from_row(row)))

    def load_offer(self, offer_id: object) -> CatalogOfferV2:
        identifier = self._identifier(offer_id)
        row = self._read_one(
            "SELECT payload_bytes, payload_sha256 FROM st0503_offers WHERE offer_id = ?",
            identifier,
        )
        if row is None:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STATE_CONFLICT
            )
        return catalog_offer_from_mapping_v2(_json_object(_payload_from_row(row)))

    def list_observations(self, offer_id: object) -> tuple[CatalogObservationV2, ...]:
        identifier = self._identifier(offer_id)
        rows = self._read_many(
            "SELECT payload_bytes, payload_sha256 FROM st0503_observations WHERE offer_id = ? ORDER BY ordinal",
            identifier,
        )
        return tuple(
            catalog_observation_from_mapping_v2(_json_object(_payload_from_row(row)))
            for row in rows
        )

    def load_outbox(self, event_id: object) -> CatalogNormalizedOutboxEventV2:
        identifier = self._identifier(event_id)
        row = self._read_one(
            "SELECT payload_bytes, payload_sha256 FROM st0503_outbox WHERE event_id = ?",
            identifier,
        )
        if row is None:
            fail_catalog_normalization_runtime(
                CatalogNormalizationRuntimeFailureCode.STATE_CONFLICT
            )
        return catalog_normalized_event_from_mapping_v2(
            _json_object(_payload_from_row(row))
        )

    @staticmethod
    def _identifier(value: object) -> str:
        if type(value) is not UUID or value.int == 0:
            fail_catalog_normalization_runtime()
        return str(value)

    @staticmethod
    def _batch_candidates(
        connection: sqlite3.Connection, batch_id: UUID
    ) -> tuple[CatalogCandidateV2, ...]:
        rows = connection.execute(
            "SELECT * FROM st0503_candidates WHERE batch_id = ? ORDER BY ordinal",
            (str(batch_id),),
        ).fetchall()
        values: list[CatalogCandidateV2] = []
        for row in rows:
            payload = _payload_from_row(row)
            candidate = catalog_candidate_from_mapping_v2(_json_object(payload))
            if (
                tuple(row.keys())
                != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_candidates"])
                or row["candidate_id"] != str(candidate.candidate_id)
                or row["batch_id"] != str(batch_id)
                or row["source_snapshot_id"] != str(candidate.source_snapshot_id)
                or row["ordinal"] != candidate.ordinal
                or _json_bytes(catalog_candidate_mapping_v2(candidate)) != payload
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            values.append(candidate)
        return tuple(values)

    @staticmethod
    def _batch_offers(
        connection: sqlite3.Connection, batch_id: UUID
    ) -> tuple[CatalogOfferV2, ...]:
        rows = connection.execute(
            "SELECT * FROM st0503_offers WHERE batch_id = ? ORDER BY ordinal",
            (str(batch_id),),
        ).fetchall()
        values: list[CatalogOfferV2] = []
        for row in rows:
            payload = _payload_from_row(row)
            offer = catalog_offer_from_mapping_v2(_json_object(payload))
            if (
                tuple(row.keys())
                != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_offers"])
                or row["offer_id"] != str(offer.offer_id)
                or row["batch_id"] != str(batch_id)
                or row["source_snapshot_id"] != str(offer.source_snapshot_id)
                or row["ordinal"] != offer.ordinal
                or _json_bytes(catalog_offer_mapping_v2(offer)) != payload
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            values.append(offer)
        return tuple(values)

    @staticmethod
    def _batch_observations(
        connection: sqlite3.Connection, batch_id: UUID
    ) -> tuple[CatalogObservationV2, ...]:
        rows = connection.execute(
            "SELECT * FROM st0503_observations WHERE batch_id = ? ORDER BY ordinal",
            (str(batch_id),),
        ).fetchall()
        values: list[CatalogObservationV2] = []
        for row in rows:
            payload = _payload_from_row(row)
            observation = catalog_observation_from_mapping_v2(_json_object(payload))
            if (
                tuple(row.keys())
                != tuple(value[0] for value in _SCHEMA_COLUMNS["st0503_observations"])
                or row["observation_id"] != str(observation.observation_id)
                or row["batch_id"] != str(batch_id)
                or row["offer_id"] != str(observation.offer_id)
                or row["source_snapshot_id"] != str(observation.source_snapshot_id)
                or row["ordinal"] != observation.ordinal
                or _json_bytes(catalog_observation_mapping_v2(observation)) != payload
            ):
                fail_catalog_normalization_runtime(
                    CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED
                )
            values.append(observation)
        return tuple(values)


__all__ = [
    "CatalogNormalizationSqliteCommitFaultV2",
    "OwnerPrivateSqliteCatalogNormalizationStoreV2",
]
