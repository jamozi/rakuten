"""Owner-private SQLite BLOB archive and UoW store for ST-0502 V2.

The fixed local database is the content-addressed raw-response archive.  Raw
bytes, immutable artifact metadata, page metadata, session CAS, and the
idempotency journal are committed in one SQLite transaction.  The adapter is
limited to a caller-selected owner-private DEV/CI directory and exposes no
provider, network, credential, publication, staging, or Production action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock
from typing import Any, NoReturn, cast, final
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    CommitRecoveryOutcomeV2,
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ItemSearchIngestionSessionV2,
    ItemSearchCommitRecoveryV2,
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchSortV2,
    ItemSearchStepCommandV2,
    ItemSearchWireRequestV2,
    ParsedItemSearchPageV2,
    PersistedItemSearchStepV2,
    ProviderFailureClassV2,
    ProviderModeV2,
    ProviderObservationKindV2,
    RateLimitObservationV2,
    RawArchiveReceiptV2,
    fail_item_search_runtime,
    failure_transition_v2,
    parse_item_search_page_v2,
    success_transition_v2,
)


_DATABASE_NAME = "st0502-item-search-archive.sqlite3"
_RECEIPT_NAMESPACE = UUID("9f2cff16-8f31-5a83-b45a-f83b46f513c8")
_MAX_STATE_BYTES = 512 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 50_000
_SCHEMA_VERSION = 2
_ZERO_HASH = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CANONICAL_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z",
    re.ASCII,
)
_CANONICAL_UTC = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{6}\+00:00\Z",
    re.ASCII,
)
_SCHEMA_CREATE_SQL: tuple[tuple[str, str], ...] = (
    (
        "st0502_state",
        """CREATE TABLE st0502_state (
    state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    mutation_count INTEGER NOT NULL CHECK (mutation_count >= 0),
    head_hash TEXT NOT NULL CHECK (length(head_hash) = 64)
) STRICT""",
    ),
    (
        "st0502_sessions",
        """CREATE TABLE st0502_sessions (
    session_id TEXT PRIMARY KEY,
    plan_fingerprint TEXT NOT NULL,
    state_bytes BLOB NOT NULL,
    state_sha256 TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 0),
    updated_at TEXT NOT NULL
) STRICT""",
    ),
    (
        "st0502_artifacts",
        """CREATE TABLE st0502_artifacts (
    artifact_version INTEGER PRIMARY KEY CHECK (artifact_version >= 1),
    sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
    byte_size INTEGER NOT NULL CHECK (byte_size >= 2 AND byte_size <= 2097152),
    content_type TEXT NOT NULL CHECK (content_type = 'application/json'),
    logical_key TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source = 'RAKUTEN_ITEM_SEARCH_20260701'),
    body BLOB NOT NULL,
    created_at TEXT NOT NULL,
    metadata_bytes BLOB NOT NULL,
    metadata_sha256 TEXT NOT NULL CHECK (length(metadata_sha256) = 64)
) STRICT""",
    ),
    (
        "st0502_receipts",
        """CREATE TABLE st0502_receipts (
    receipt_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    page INTEGER NOT NULL CHECK (page BETWEEN 1 AND 100),
    artifact_sha256 TEXT NOT NULL,
    artifact_version INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    UNIQUE(operation_id),
    UNIQUE(session_id, page),
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(artifact_version) REFERENCES st0502_artifacts(artifact_version)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "st0502_page_metadata",
        """CREATE TABLE st0502_page_metadata (
    receipt_id TEXT PRIMARY KEY,
    rate_limit INTEGER,
    rate_remaining INTEGER,
    rate_reset_at TEXT,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    CHECK (
        (rate_limit IS NULL AND rate_remaining IS NULL AND rate_reset_at IS NULL)
        OR
        (rate_limit >= 1 AND rate_remaining >= 0 AND rate_remaining <= rate_limit AND rate_reset_at IS NOT NULL)
    ),
    FOREIGN KEY(receipt_id) REFERENCES st0502_receipts(receipt_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "st0502_commands",
        """CREATE TABLE st0502_commands (
    operation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    expected_version INTEGER NOT NULL CHECK (expected_version >= 0),
    observed_at TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    payload_bytes BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    external_action_count INTEGER NOT NULL CHECK (external_action_count = 0),
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "st0502_journal",
        """CREATE TABLE st0502_journal (
    operation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    receipt_id TEXT,
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    external_action_count INTEGER NOT NULL CHECK (external_action_count = 0),
    FOREIGN KEY(operation_id) REFERENCES st0502_commands(operation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(receipt_id) REFERENCES st0502_receipts(receipt_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "st0502_history",
        """CREATE TABLE st0502_history (
    history_version INTEGER PRIMARY KEY CHECK (history_version >= 1),
    mutation_kind TEXT NOT NULL CHECK (mutation_kind IN ('SESSION_CREATED', 'STEP_COMMITTED')),
    operation_id TEXT UNIQUE,
    session_id TEXT NOT NULL,
    before_version INTEGER,
    after_version INTEGER NOT NULL CHECK (after_version >= 0),
    command_sha256 TEXT,
    session_before_bytes BLOB,
    session_before_sha256 TEXT,
    session_after_bytes BLOB NOT NULL,
    session_after_sha256 TEXT NOT NULL CHECK (length(session_after_sha256) = 64),
    artifact_metadata_sha256 TEXT,
    receipt_id TEXT,
    receipt_sha256 TEXT,
    rate_sha256 TEXT,
    result_sha256 TEXT,
    previous_chain_hash TEXT NOT NULL CHECK (length(previous_chain_hash) = 64),
    chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
    committed_at TEXT NOT NULL,
    external_action_count INTEGER NOT NULL CHECK (external_action_count = 0),
    CHECK (
        (mutation_kind = 'SESSION_CREATED'
         AND operation_id IS NULL
         AND before_version IS NULL
         AND after_version = 0
         AND command_sha256 IS NULL
         AND session_before_bytes IS NULL
         AND session_before_sha256 IS NULL
         AND artifact_metadata_sha256 IS NULL
         AND receipt_id IS NULL
         AND receipt_sha256 IS NULL
         AND rate_sha256 IS NULL
         AND result_sha256 IS NULL)
        OR
        (mutation_kind = 'STEP_COMMITTED'
         AND operation_id IS NOT NULL
         AND before_version IS NOT NULL
         AND after_version = before_version + 1
         AND command_sha256 IS NOT NULL
         AND session_before_bytes IS NOT NULL
         AND session_before_sha256 IS NOT NULL
         AND result_sha256 IS NOT NULL
         AND ((receipt_id IS NULL
               AND artifact_metadata_sha256 IS NULL
               AND receipt_sha256 IS NULL
               AND rate_sha256 IS NULL)
              OR
              (receipt_id IS NOT NULL
               AND artifact_metadata_sha256 IS NOT NULL
               AND receipt_sha256 IS NOT NULL
               AND rate_sha256 IS NOT NULL)))
    ),
    FOREIGN KEY(operation_id) REFERENCES st0502_commands(operation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY(receipt_id) REFERENCES st0502_receipts(receipt_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
)


_APPEND_ONLY_TABLES = (
    "st0502_artifacts",
    "st0502_receipts",
    "st0502_page_metadata",
    "st0502_commands",
    "st0502_journal",
    "st0502_history",
)


def _immutable_trigger_sql(table: str, operation: str) -> str:
    return (
        f"CREATE TRIGGER {table}_no_{operation} "
        f"BEFORE {operation.upper()} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ST0502_V2'); END"
    )


_SCHEMA_TRIGGER_SQL: tuple[tuple[str, str], ...] = (
    *(
        (f"{table}_no_{operation}", _immutable_trigger_sql(table, operation))
        for table in _APPEND_ONLY_TABLES
        for operation in ("update", "delete")
    ),
    (
        "st0502_sessions_no_delete",
        _immutable_trigger_sql("st0502_sessions", "delete"),
    ),
    (
        "st0502_state_no_insert",
        _immutable_trigger_sql("st0502_state", "insert"),
    ),
    (
        "st0502_state_no_delete",
        _immutable_trigger_sql("st0502_state", "delete"),
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

_SCHEMA_AUTO_INDEXES: frozenset[tuple[str, str, str, None]] = frozenset(
    {
        (
            "index",
            "sqlite_autoindex_st0502_sessions_1",
            "st0502_sessions",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_artifacts_1",
            "st0502_artifacts",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_artifacts_2",
            "st0502_artifacts",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_receipts_1",
            "st0502_receipts",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_receipts_2",
            "st0502_receipts",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_receipts_3",
            "st0502_receipts",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_page_metadata_1",
            "st0502_page_metadata",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_commands_1",
            "st0502_commands",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_journal_1",
            "st0502_journal",
            None,
        ),
        (
            "index",
            "sqlite_autoindex_st0502_history_1",
            "st0502_history",
            None,
        ),
    }
)
_SCHEMA_FOREIGN_KEYS: dict[str, frozenset[tuple[str, str, str, str, str, str]]] = {
    "st0502_state": frozenset(),
    "st0502_sessions": frozenset(),
    "st0502_artifacts": frozenset(),
    "st0502_receipts": frozenset(
        {
            (
                "st0502_artifacts",
                "artifact_version",
                "artifact_version",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "st0502_sessions",
                "session_id",
                "session_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
    "st0502_page_metadata": frozenset(
        {
            (
                "st0502_receipts",
                "receipt_id",
                "receipt_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
    "st0502_commands": frozenset(
        {
            (
                "st0502_sessions",
                "session_id",
                "session_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
    "st0502_journal": frozenset(
        {
            (
                "st0502_commands",
                "operation_id",
                "operation_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "st0502_sessions",
                "session_id",
                "session_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "st0502_receipts",
                "receipt_id",
                "receipt_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
    "st0502_history": frozenset(
        {
            (
                "st0502_commands",
                "operation_id",
                "operation_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "st0502_sessions",
                "session_id",
                "session_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
            (
                "st0502_receipts",
                "receipt_id",
                "receipt_id",
                "RESTRICT",
                "RESTRICT",
                "NONE",
            ),
        }
    ),
}
_SCHEMA_COLUMNS: dict[str, tuple[tuple[str, str, int, int, int], ...]] = {
    "st0502_state": (
        ("state_id", "INTEGER", 0, 1, 0),
        ("schema_binding", "TEXT", 1, 0, 0),
        ("mutation_count", "INTEGER", 1, 0, 0),
        ("head_hash", "TEXT", 1, 0, 0),
    ),
    "st0502_sessions": (
        ("session_id", "TEXT", 1, 1, 0),
        ("plan_fingerprint", "TEXT", 1, 0, 0),
        ("state_bytes", "BLOB", 1, 0, 0),
        ("state_sha256", "TEXT", 1, 0, 0),
        ("version", "INTEGER", 1, 0, 0),
        ("updated_at", "TEXT", 1, 0, 0),
    ),
    "st0502_artifacts": (
        ("artifact_version", "INTEGER", 0, 1, 0),
        ("sha256", "TEXT", 1, 0, 0),
        ("byte_size", "INTEGER", 1, 0, 0),
        ("content_type", "TEXT", 1, 0, 0),
        ("logical_key", "TEXT", 1, 0, 0),
        ("source", "TEXT", 1, 0, 0),
        ("body", "BLOB", 1, 0, 0),
        ("created_at", "TEXT", 1, 0, 0),
        ("metadata_bytes", "BLOB", 1, 0, 0),
        ("metadata_sha256", "TEXT", 1, 0, 0),
    ),
    "st0502_receipts": (
        ("receipt_id", "TEXT", 1, 1, 0),
        ("operation_id", "TEXT", 1, 0, 0),
        ("session_id", "TEXT", 1, 0, 0),
        ("request_fingerprint", "TEXT", 1, 0, 0),
        ("page", "INTEGER", 1, 0, 0),
        ("artifact_sha256", "TEXT", 1, 0, 0),
        ("artifact_version", "INTEGER", 1, 0, 0),
        ("observed_at", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0502_page_metadata": (
        ("receipt_id", "TEXT", 1, 1, 0),
        ("rate_limit", "INTEGER", 0, 0, 0),
        ("rate_remaining", "INTEGER", 0, 0, 0),
        ("rate_reset_at", "TEXT", 0, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
    ),
    "st0502_commands": (
        ("operation_id", "TEXT", 1, 1, 0),
        ("session_id", "TEXT", 1, 0, 0),
        ("expected_version", "INTEGER", 1, 0, 0),
        ("observed_at", "TEXT", 1, 0, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("payload_bytes", "BLOB", 1, 0, 0),
        ("payload_sha256", "TEXT", 1, 0, 0),
        ("external_action_count", "INTEGER", 1, 0, 0),
    ),
    "st0502_journal": (
        ("operation_id", "TEXT", 1, 1, 0),
        ("session_id", "TEXT", 1, 0, 0),
        ("receipt_id", "TEXT", 0, 0, 0),
        ("result_bytes", "BLOB", 1, 0, 0),
        ("result_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
        ("external_action_count", "INTEGER", 1, 0, 0),
    ),
    "st0502_history": (
        ("history_version", "INTEGER", 0, 1, 0),
        ("mutation_kind", "TEXT", 1, 0, 0),
        ("operation_id", "TEXT", 0, 0, 0),
        ("session_id", "TEXT", 1, 0, 0),
        ("before_version", "INTEGER", 0, 0, 0),
        ("after_version", "INTEGER", 1, 0, 0),
        ("command_sha256", "TEXT", 0, 0, 0),
        ("session_before_bytes", "BLOB", 0, 0, 0),
        ("session_before_sha256", "TEXT", 0, 0, 0),
        ("session_after_bytes", "BLOB", 1, 0, 0),
        ("session_after_sha256", "TEXT", 1, 0, 0),
        ("artifact_metadata_sha256", "TEXT", 0, 0, 0),
        ("receipt_id", "TEXT", 0, 0, 0),
        ("receipt_sha256", "TEXT", 0, 0, 0),
        ("rate_sha256", "TEXT", 0, 0, 0),
        ("result_sha256", "TEXT", 0, 0, 0),
        ("previous_chain_hash", "TEXT", 1, 0, 0),
        ("chain_hash", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
        ("external_action_count", "INTEGER", 1, 0, 0),
    ),
}

_SCHEMA_INITIALIZATION_LOCK = RLock()
_PROCESS_WRITE_LOCK = RLock()


class SqliteCommitFaultV2(str, Enum):
    NONE = "NONE"
    KNOWN_BEFORE_COMMIT = "KNOWN_BEFORE_COMMIT"
    UNKNOWN_BEFORE_COMMIT = "UNKNOWN_BEFORE_COMMIT"
    UNKNOWN_AFTER_COMMIT = "UNKNOWN_AFTER_COMMIT"


def _environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        fail_item_search_runtime()
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
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    if len(payload) > _MAX_STATE_BYTES:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return payload


def _reject_constant(_value: str) -> NoReturn:
    fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        result[key] = value
    return result


def _validate_json_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if current is None or type(current) in {str, bool, int}:
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
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)


def _json_object(payload: object) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > _MAX_STATE_BYTES:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    try:
        decoded = payload.decode("utf-8", errors="strict")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeError, json.JSONDecodeError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    _validate_json_tree(parsed)
    if type(parsed) is not dict:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    raw = cast(dict[object, object], parsed)
    if not all(type(key) is str for key in raw):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    result = {cast(str, key): value for key, value in raw.items()}
    if _json_bytes(result) != payload:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return result


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    raw = cast(dict[object, object], value)
    if not all(type(key) is str for key in raw):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    result = {cast(str, key): item for key, item in raw.items()}
    if frozenset(result) != keys:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return result


def _string(value: object) -> str:
    if type(value) is not str:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return value


def _utc_text(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is not timezone.utc or value.fold:
        fail_item_search_runtime()
    return value.isoformat(timespec="microseconds")


def _parse_utc(value: object) -> datetime:
    text = _string(value)
    if _CANONICAL_UTC.fullmatch(text) is None:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    if parsed.tzinfo is not timezone.utc or parsed.fold or _utc_text(parsed) != text:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return parsed


def _uuid_text(value: UUID) -> str:
    if type(value) is not UUID or value.int == 0:
        fail_item_search_runtime()
    text = str(value)
    if _CANONICAL_UUID.fullmatch(text) is None:
        fail_item_search_runtime()
    return text


def _parse_uuid(value: object) -> UUID:
    text = _string(value)
    if _CANONICAL_UUID.fullmatch(text) is None:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    try:
        parsed = UUID(text)
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    if parsed.int == 0 or str(parsed) != text:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return parsed


def _payload_from_row(row: sqlite3.Row, *, prefix: str) -> bytes:
    payload = row[f"{prefix}_bytes"]
    digest = row[f"{prefix}_sha256"]
    if (
        type(payload) is not bytes
        or type(digest) is not str
        or _SHA256.fullmatch(digest) is None
        or hashlib.sha256(payload).hexdigest() != digest
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return payload


def _plan_mapping(plan: ItemSearchPlanV2) -> dict[str, object]:
    return {
        "appoint_delivery_date_only": plan.appoint_delivery_date_only,
        "attribute_flag": plan.attribute_flag,
        "availability": plan.availability,
        "circuit_cooldown_seconds": plan.circuit_cooldown_seconds,
        "circuit_failure_threshold": plan.circuit_failure_threshold,
        "genre_id": plan.genre_id,
        "genre_information_flag": plan.genre_information_flag,
        "hits": plan.hits,
        "item_code": plan.item_code,
        "keyword": plan.keyword,
        "max_pages": plan.max_pages,
        "max_price_jpy": plan.max_price_jpy,
        "min_price_jpy": plan.min_price_jpy,
        "or_flag": plan.or_flag,
        "postage_included_only": plan.postage_included_only,
        "retry_delays_seconds": list(plan.retry_delays_seconds),
        "shop_code": plan.shop_code,
        "sort": plan.sort.value,
    }


_PLAN_KEYS = frozenset(
    {
        "appoint_delivery_date_only",
        "attribute_flag",
        "availability",
        "circuit_cooldown_seconds",
        "circuit_failure_threshold",
        "genre_id",
        "genre_information_flag",
        "hits",
        "item_code",
        "keyword",
        "max_pages",
        "max_price_jpy",
        "min_price_jpy",
        "or_flag",
        "postage_included_only",
        "retry_delays_seconds",
        "shop_code",
        "sort",
    }
)


def _plan_from(value: object) -> ItemSearchPlanV2:
    data = _exact_mapping(value, _PLAN_KEYS)
    delays = data["retry_delays_seconds"]
    if type(delays) is not list:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    delay_items = cast(list[object], delays)
    if any(type(item) is not int for item in delay_items):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    try:
        sort_value = ItemSearchSortV2(_string(data["sort"]))
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return ItemSearchPlanV2(
        keyword=_optional_string(data["keyword"]),
        shop_code=_optional_string(data["shop_code"]),
        item_code=_optional_string(data["item_code"]),
        genre_id=None if data["genre_id"] is None else _integer(data["genre_id"]),
        hits=_integer(data["hits"]),
        sort=sort_value,
        min_price_jpy=(
            None if data["min_price_jpy"] is None else _integer(data["min_price_jpy"])
        ),
        max_price_jpy=(
            None if data["max_price_jpy"] is None else _integer(data["max_price_jpy"])
        ),
        or_flag=_boolean(data["or_flag"]),
        availability=_boolean(data["availability"]),
        postage_included_only=_boolean(data["postage_included_only"]),
        appoint_delivery_date_only=_boolean(data["appoint_delivery_date_only"]),
        attribute_flag=_boolean(data["attribute_flag"]),
        genre_information_flag=_boolean(data["genre_information_flag"]),
        max_pages=_integer(data["max_pages"]),
        retry_delays_seconds=tuple(cast(list[int], delay_items)),
        circuit_failure_threshold=_integer(data["circuit_failure_threshold"]),
        circuit_cooldown_seconds=_integer(data["circuit_cooldown_seconds"]),
    )


_SESSION_KEYS = frozenset(
    {
        "completed_pages",
        "consecutive_failures",
        "created_at",
        "current_attempt",
        "last_failure_class",
        "next_allowed_at",
        "next_page",
        "plan",
        "seen_item_fingerprints",
        "seen_request_fingerprints",
        "seen_response_sha256",
        "session_id",
        "state",
        "updated_at",
        "version",
    }
)


def _session_mapping(session: ItemSearchIngestionSessionV2) -> dict[str, object]:
    return {
        "completed_pages": session.completed_pages,
        "consecutive_failures": session.consecutive_failures,
        "created_at": _utc_text(session.created_at),
        "current_attempt": session.current_attempt,
        "last_failure_class": (
            None
            if session.last_failure_class is None
            else session.last_failure_class.value
        ),
        "next_allowed_at": (
            None
            if session.next_allowed_at is None
            else _utc_text(session.next_allowed_at)
        ),
        "next_page": session.next_page,
        "plan": _plan_mapping(session.plan),
        "seen_item_fingerprints": list(session.seen_item_fingerprints),
        "seen_request_fingerprints": list(session.seen_request_fingerprints),
        "seen_response_sha256": list(session.seen_response_sha256),
        "session_id": _uuid_text(session.session_id),
        "state": session.state.value,
        "updated_at": _utc_text(session.updated_at),
        "version": session.version,
    }


def _string_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    items = cast(list[object], value)
    if any(type(item) is not str for item in items):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return tuple(cast(list[str], items))


def _session_from(value: object) -> ItemSearchIngestionSessionV2:
    data = _exact_mapping(value, _SESSION_KEYS)
    try:
        state = IngestionSessionStateV2(_string(data["state"]))
        failure = (
            None
            if data["last_failure_class"] is None
            else ProviderFailureClassV2(_string(data["last_failure_class"]))
        )
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return ItemSearchIngestionSessionV2(
        session_id=_parse_uuid(data["session_id"]),
        plan=_plan_from(data["plan"]),
        state=state,
        next_page=_integer(data["next_page"]),
        completed_pages=_integer(data["completed_pages"]),
        current_attempt=_integer(data["current_attempt"]),
        consecutive_failures=_integer(data["consecutive_failures"]),
        next_allowed_at=(
            None
            if data["next_allowed_at"] is None
            else _parse_utc(data["next_allowed_at"])
        ),
        seen_request_fingerprints=_string_tuple(data["seen_request_fingerprints"]),
        seen_response_sha256=_string_tuple(data["seen_response_sha256"]),
        seen_item_fingerprints=_string_tuple(data["seen_item_fingerprints"]),
        last_failure_class=failure,
        version=_integer(data["version"]),
        created_at=_parse_utc(data["created_at"]),
        updated_at=_parse_utc(data["updated_at"]),
    )


_RECEIPT_KEYS = frozenset(
    {
        "artifact_sha256",
        "artifact_version",
        "byte_size",
        "logical_key",
        "observed_at",
        "page",
        "receipt_id",
        "request_fingerprint",
    }
)


def _receipt_mapping(receipt: RawArchiveReceiptV2) -> dict[str, object]:
    return {
        "artifact_sha256": receipt.artifact_sha256,
        "artifact_version": receipt.artifact_version,
        "byte_size": receipt.byte_size,
        "logical_key": receipt.logical_key,
        "observed_at": _utc_text(receipt.observed_at),
        "page": receipt.page,
        "receipt_id": _uuid_text(receipt.receipt_id),
        "request_fingerprint": receipt.request_fingerprint,
    }


def _receipt_from(value: object) -> RawArchiveReceiptV2:
    data = _exact_mapping(value, _RECEIPT_KEYS)
    return RawArchiveReceiptV2(
        receipt_id=_parse_uuid(data["receipt_id"]),
        artifact_sha256=_string(data["artifact_sha256"]),
        byte_size=_integer(data["byte_size"]),
        artifact_version=_integer(data["artifact_version"]),
        logical_key=_string(data["logical_key"]),
        request_fingerprint=_string(data["request_fingerprint"]),
        page=_integer(data["page"]),
        observed_at=_parse_utc(data["observed_at"]),
    )


_RESULT_KEYS = frozenset(
    {
        "failure_class",
        "outcome",
        "receipt",
        "request_fingerprint",
        "session",
    }
)


def _result_mapping(result: PersistedItemSearchStepV2) -> dict[str, object]:
    return {
        "failure_class": (
            None if result.failure_class is None else result.failure_class.value
        ),
        "outcome": result.outcome.value,
        "receipt": (
            None if result.receipt is None else _receipt_mapping(result.receipt)
        ),
        "request_fingerprint": result.request_fingerprint,
        "session": _session_mapping(result.session),
    }


def _result_from(value: object) -> PersistedItemSearchStepV2:
    data = _exact_mapping(value, _RESULT_KEYS)
    try:
        outcome = IngestionStepOutcomeV2(_string(data["outcome"]))
        failure = (
            None
            if data["failure_class"] is None
            else ProviderFailureClassV2(_string(data["failure_class"]))
        )
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return PersistedItemSearchStepV2(
        outcome=outcome,
        session=_session_from(data["session"]),
        request_fingerprint=_optional_string(data["request_fingerprint"]),
        receipt=(None if data["receipt"] is None else _receipt_from(data["receipt"])),
        failure_class=failure,
    )


_COMMAND_KEYS = frozenset(
    {
        "expected_version",
        "observed_at",
        "operation_id",
        "payload_fingerprint",
        "session_id",
    }
)


def _command_mapping(command: ItemSearchStepCommandV2) -> dict[str, object]:
    if type(command) is not ItemSearchStepCommandV2:
        fail_item_search_runtime()
    return {
        "expected_version": command.expected_version,
        "observed_at": _utc_text(command.observed_at),
        "operation_id": _uuid_text(command.operation_id),
        "payload_fingerprint": command.payload_fingerprint,
        "session_id": _uuid_text(command.session_id),
    }


def _command_from(value: object) -> ItemSearchStepCommandV2:
    data = _exact_mapping(value, _COMMAND_KEYS)
    command = ItemSearchStepCommandV2(
        operation_id=_parse_uuid(data["operation_id"]),
        session_id=_parse_uuid(data["session_id"]),
        expected_version=_integer(data["expected_version"]),
        observed_at=_parse_utc(data["observed_at"]),
    )
    if command.payload_fingerprint != _string(data["payload_fingerprint"]):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return command


def _rate_mapping(rate: RateLimitObservationV2 | None) -> dict[str, object]:
    if rate is None:
        return {"limit": None, "remaining": None, "reset_at": None}
    if type(rate) is not RateLimitObservationV2:
        fail_item_search_runtime()
    return {
        "limit": rate.limit,
        "remaining": rate.remaining,
        "reset_at": None if rate.reset_at is None else _utc_text(rate.reset_at),
    }


_RATE_KEYS = frozenset({"limit", "remaining", "reset_at"})


def _rate_from(value: object) -> RateLimitObservationV2:
    data = _exact_mapping(value, _RATE_KEYS)
    return RateLimitObservationV2(
        limit=None if data["limit"] is None else _integer(data["limit"]),
        remaining=(None if data["remaining"] is None else _integer(data["remaining"])),
        reset_at=(None if data["reset_at"] is None else _parse_utc(data["reset_at"])),
    )


def _artifact_metadata_mapping(
    *,
    artifact_version: int,
    sha256: str,
    byte_size: int,
    logical_key: str,
    created_at: datetime,
) -> dict[str, object]:
    return {
        "artifact_version": artifact_version,
        "byte_size": byte_size,
        "content_type": "application/json",
        "created_at": _utc_text(created_at),
        "logical_key": logical_key,
        "sha256": sha256,
        "source": "RAKUTEN_ITEM_SEARCH_20260701",
    }


def _chain_hash(
    *,
    history_version: int,
    mutation_kind: str,
    operation_id: str | None,
    session_id: str,
    before_version: int | None,
    after_version: int,
    command_sha256: str | None,
    session_before_sha256: str | None,
    session_after_sha256: str,
    artifact_metadata_sha256: str | None,
    receipt_id: str | None,
    receipt_sha256: str | None,
    rate_sha256: str | None,
    result_sha256: str | None,
    previous_chain_hash: str,
    committed_at: str,
) -> str:
    return hashlib.sha256(
        b"ST0502_MUTATION_CHAIN_V2\0"
        + _json_bytes(
            {
                "after_version": after_version,
                "artifact_metadata_sha256": artifact_metadata_sha256,
                "before_version": before_version,
                "command_sha256": command_sha256,
                "committed_at": committed_at,
                "external_action_count": 0,
                "history_version": history_version,
                "mutation_kind": mutation_kind,
                "operation_id": operation_id,
                "previous_chain_hash": previous_chain_hash,
                "rate_sha256": rate_sha256,
                "receipt_id": receipt_id,
                "receipt_sha256": receipt_sha256,
                "result_sha256": result_sha256,
                "session_after_sha256": session_after_sha256,
                "session_before_sha256": session_before_sha256,
                "session_id": session_id,
            }
        )
    ).hexdigest()


def _validate_root_path(root: object) -> Path:
    if type(root) is not type(Path()) or not root.is_absolute() or ".." in root.parts:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
    normalized = Path(os.path.abspath(root))
    if normalized != root:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
        if stat.S_ISLNK(metadata.st_mode):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
    return root


def _validate_private_directory(root: Path) -> None:
    try:
        metadata = root.lstat()
    except OSError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)


@dataclass(frozen=True, slots=True)
class _RawArchiveMaterial:
    body: bytes
    sha256: str
    observed_at: datetime
    rate: RateLimitObservationV2 | None


@dataclass(frozen=True, slots=True)
class _ArchivedMaterial:
    receipt: RawArchiveReceiptV2
    artifact_metadata_sha256: str
    receipt_sha256: str
    rate_sha256: str


_SessionMaterial = tuple[ItemSearchIngestionSessionV2, bytes, str]
_ArtifactMaterial = tuple[sqlite3.Row, str]
_ReceiptMaterial = tuple[sqlite3.Row, RawArchiveReceiptV2, str]
_JournalMaterial = tuple[sqlite3.Row, PersistedItemSearchStepV2, str]


def _integrity_state_and_sessions(
    connection: sqlite3.Connection,
) -> tuple[int, str, dict[str, _SessionMaterial]]:
    state_rows = connection.execute(
        "SELECT state_id, schema_binding, mutation_count, head_hash FROM st0502_state"
    ).fetchall()
    if len(state_rows) != 1:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    state_row = state_rows[0]
    mutation_count = state_row["mutation_count"]
    state_head = state_row["head_hash"]
    if (
        type(state_row["state_id"]) is not int
        or state_row["state_id"] != 1
        or state_row["schema_binding"] != _SCHEMA_BINDING
        or type(mutation_count) is not int
        or mutation_count < 0
        or type(state_head) is not str
        or _SHA256.fullmatch(state_head) is None
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    sessions: dict[str, _SessionMaterial] = {}
    for row in connection.execute(
        "SELECT session_id, plan_fingerprint, state_bytes, state_sha256, "
        "version, updated_at FROM st0502_sessions ORDER BY session_id"
    ).fetchall():
        payload = _payload_from_row(row, prefix="state")
        session = _session_from(_json_object(payload))
        session_id = _uuid_text(session.session_id)
        digest = hashlib.sha256(payload).hexdigest()
        if (
            row["session_id"] != session_id
            or row["plan_fingerprint"] != session.plan.fingerprint
            or type(row["version"]) is not int
            or row["version"] != session.version
            or row["updated_at"] != _utc_text(session.updated_at)
            or session_id in sessions
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        sessions[session_id] = session, payload, digest
    return mutation_count, state_head, sessions


def _integrity_artifacts(
    connection: sqlite3.Connection,
) -> dict[int, _ArtifactMaterial]:
    artifacts: dict[int, _ArtifactMaterial] = {}
    rows = connection.execute(
        "SELECT artifact_version, sha256, byte_size, content_type, logical_key, "
        "source, body, created_at, metadata_bytes, metadata_sha256 "
        "FROM st0502_artifacts ORDER BY artifact_version"
    ).fetchall()
    for expected_version, row in enumerate(rows, start=1):
        body = row["body"]
        version = row["artifact_version"]
        digest = row["sha256"]
        created_at = _parse_utc(row["created_at"])
        metadata_payload = _payload_from_row(row, prefix="metadata")
        metadata_digest = hashlib.sha256(metadata_payload).hexdigest()
        if (
            type(version) is not int
            or version != expected_version
            or type(body) is not bytes
            or type(digest) is not str
            or _SHA256.fullmatch(digest) is None
            or hashlib.sha256(body).hexdigest() != digest
            or type(row["byte_size"]) is not int
            or row["byte_size"] != len(body)
            or row["content_type"] != "application/json"
            or row["logical_key"] != f"sha256/{digest[:2]}/{digest}"
            or row["source"] != "RAKUTEN_ITEM_SEARCH_20260701"
            or _json_object(metadata_payload)
            != _artifact_metadata_mapping(
                artifact_version=version,
                sha256=digest,
                byte_size=len(body),
                logical_key=row["logical_key"],
                created_at=created_at,
            )
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        artifacts[version] = row, metadata_digest
    return artifacts


def _integrity_receipts(
    connection: sqlite3.Connection,
    *,
    artifacts: dict[int, _ArtifactMaterial],
    sessions: dict[str, _SessionMaterial],
) -> dict[str, _ReceiptMaterial]:
    receipts: dict[str, _ReceiptMaterial] = {}
    receipt_operations: set[str] = set()
    rows = connection.execute(
        "SELECT receipt_id, operation_id, session_id, request_fingerprint, page, "
        "artifact_sha256, artifact_version, observed_at, payload_bytes, "
        "payload_sha256 FROM st0502_receipts ORDER BY receipt_id"
    ).fetchall()
    for row in rows:
        payload = _payload_from_row(row, prefix="payload")
        receipt = _receipt_from(_json_object(payload))
        receipt_id = _uuid_text(receipt.receipt_id)
        operation_text = _uuid_text(_parse_uuid(row["operation_id"]))
        session_text = _uuid_text(_parse_uuid(row["session_id"]))
        artifact = artifacts.get(receipt.artifact_version)
        if artifact is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        artifact_row, _metadata_digest = artifact
        if (
            row["receipt_id"] != receipt_id
            or operation_text in receipt_operations
            or session_text not in sessions
            or row["request_fingerprint"] != receipt.request_fingerprint
            or row["page"] != receipt.page
            or row["artifact_sha256"] != receipt.artifact_sha256
            or row["artifact_version"] != receipt.artifact_version
            or row["observed_at"] != _utc_text(receipt.observed_at)
            or receipt.byte_size != artifact_row["byte_size"]
            or receipt.artifact_sha256 != artifact_row["sha256"]
            or receipt.logical_key != artifact_row["logical_key"]
            or _json_object(payload) != _receipt_mapping(receipt)
            or receipt_id in receipts
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        receipt_operations.add(operation_text)
        receipts[receipt_id] = row, receipt, hashlib.sha256(payload).hexdigest()
    return receipts


def _integrity_rates(
    connection: sqlite3.Connection,
    *,
    receipts: dict[str, _ReceiptMaterial],
) -> dict[str, tuple[RateLimitObservationV2, str]]:
    rates: dict[str, tuple[RateLimitObservationV2, str]] = {}
    rows = connection.execute(
        "SELECT receipt_id, rate_limit, rate_remaining, rate_reset_at, "
        "payload_bytes, payload_sha256 FROM st0502_page_metadata "
        "ORDER BY receipt_id"
    ).fetchall()
    for row in rows:
        receipt_id = row["receipt_id"]
        payload = _payload_from_row(row, prefix="payload")
        rate = _rate_from(_json_object(payload))
        if (
            type(receipt_id) is not str
            or receipt_id not in receipts
            or row["rate_limit"] != rate.limit
            or row["rate_remaining"] != rate.remaining
            or row["rate_reset_at"]
            != (None if rate.reset_at is None else _utc_text(rate.reset_at))
            or _json_object(payload) != _rate_mapping(rate)
            or receipt_id in rates
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        rates[receipt_id] = rate, hashlib.sha256(payload).hexdigest()
    if frozenset(rates) != frozenset(receipts):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return rates


def _integrity_commands(
    connection: sqlite3.Connection,
) -> dict[str, tuple[ItemSearchStepCommandV2, str]]:
    commands: dict[str, tuple[ItemSearchStepCommandV2, str]] = {}
    rows = connection.execute(
        "SELECT operation_id, session_id, expected_version, observed_at, "
        "payload_fingerprint, payload_bytes, payload_sha256, "
        "external_action_count FROM st0502_commands ORDER BY operation_id"
    ).fetchall()
    for row in rows:
        payload = _payload_from_row(row, prefix="payload")
        command = _command_from(_json_object(payload))
        operation_text = _uuid_text(command.operation_id)
        if (
            row["operation_id"] != operation_text
            or row["session_id"] != _uuid_text(command.session_id)
            or row["expected_version"] != command.expected_version
            or row["observed_at"] != _utc_text(command.observed_at)
            or row["payload_fingerprint"] != command.payload_fingerprint
            or type(row["external_action_count"]) is not int
            or row["external_action_count"] != 0
            or _json_object(payload) != _command_mapping(command)
            or operation_text in commands
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        commands[operation_text] = command, hashlib.sha256(payload).hexdigest()
    return commands


def _integrity_journal(
    connection: sqlite3.Connection,
    *,
    commands: dict[str, tuple[ItemSearchStepCommandV2, str]],
    receipts: dict[str, _ReceiptMaterial],
) -> dict[str, _JournalMaterial]:
    journal: dict[str, _JournalMaterial] = {}
    rows = connection.execute(
        "SELECT operation_id, session_id, receipt_id, result_bytes, "
        "result_sha256, committed_at, external_action_count "
        "FROM st0502_journal ORDER BY operation_id"
    ).fetchall()
    for row in rows:
        payload = _payload_from_row(row, prefix="result")
        result = _result_from(_json_object(payload))
        operation_text = _uuid_text(_parse_uuid(row["operation_id"]))
        receipt_id = row["receipt_id"]
        if (
            operation_text not in commands
            or row["session_id"] != _uuid_text(result.session.session_id)
            or row["committed_at"] != _utc_text(result.session.updated_at)
            or type(row["external_action_count"]) is not int
            or row["external_action_count"] != 0
            or _json_object(payload) != _result_mapping(result)
            or receipt_id
            != (
                None
                if result.receipt is None
                else _uuid_text(result.receipt.receipt_id)
            )
            or (
                result.receipt is not None
                and (
                    receipt_id not in receipts
                    or receipts[receipt_id][1] != result.receipt
                )
            )
            or operation_text in journal
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        journal[operation_text] = row, result, hashlib.sha256(payload).hexdigest()
    if frozenset(journal) != frozenset(commands):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return journal


def _integrity_history(
    connection: sqlite3.Connection,
    *,
    mutation_count: int,
    state_head: str,
    sessions: dict[str, _SessionMaterial],
    artifacts: dict[int, _ArtifactMaterial],
    receipts: dict[str, _ReceiptMaterial],
    rates: dict[str, tuple[RateLimitObservationV2, str]],
    commands: dict[str, tuple[ItemSearchStepCommandV2, str]],
    journal: dict[str, _JournalMaterial],
) -> None:
    latest_by_session: dict[str, _SessionMaterial] = {}
    seen_created: set[str] = set()
    seen_operations: set[str] = set()
    seen_receipts: set[str] = set()
    previous_chain = _ZERO_HASH
    rows = connection.execute(
        "SELECT history_version, mutation_kind, operation_id, session_id, "
        "before_version, after_version, command_sha256, session_before_bytes, "
        "session_before_sha256, session_after_bytes, session_after_sha256, "
        "artifact_metadata_sha256, receipt_id, receipt_sha256, rate_sha256, "
        "result_sha256, previous_chain_hash, chain_hash, committed_at, "
        "external_action_count FROM st0502_history ORDER BY history_version"
    ).fetchall()
    for expected_version, row in enumerate(rows, start=1):
        history_version = row["history_version"]
        mutation_kind = row["mutation_kind"]
        session_id = _uuid_text(_parse_uuid(row["session_id"]))
        operation_id = row["operation_id"]
        before_payload = row["session_before_bytes"]
        before_digest = row["session_before_sha256"]
        after_payload = _payload_from_row(row, prefix="session_after")
        after_session = _session_from(_json_object(after_payload))
        after_digest = hashlib.sha256(after_payload).hexdigest()
        committed_at = _utc_text(_parse_utc(row["committed_at"]))
        if (
            type(history_version) is not int
            or history_version != expected_version
            or session_id != _uuid_text(after_session.session_id)
            or row["after_version"] != after_session.version
            or row["previous_chain_hash"] != previous_chain
            or type(row["external_action_count"]) is not int
            or row["external_action_count"] != 0
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

        if mutation_kind == "SESSION_CREATED":
            if (
                operation_id is not None
                or before_payload is not None
                or before_digest is not None
                or session_id in seen_created
                or after_session
                != ItemSearchIngestionSessionV2.initial(
                    session_id=after_session.session_id,
                    plan=after_session.plan,
                    created_at=after_session.created_at,
                )
                or committed_at != _utc_text(after_session.created_at)
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            seen_created.add(session_id)
        elif mutation_kind == "STEP_COMMITTED":
            if (
                type(before_payload) is not bytes
                or type(before_digest) is not str
                or _SHA256.fullmatch(before_digest) is None
                or hashlib.sha256(before_payload).hexdigest() != before_digest
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            before_session = _session_from(_json_object(before_payload))
            operation_text = _uuid_text(_parse_uuid(operation_id))
            command_material = commands.get(operation_text)
            journal_material = journal.get(operation_text)
            if command_material is None or journal_material is None:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            command, command_digest = command_material
            journal_row, result, result_digest = journal_material
            receipt_id = row["receipt_id"]
            archived = None if receipt_id is None else receipts.get(receipt_id)
            rate_material = None if receipt_id is None else rates.get(receipt_id)
            artifact_metadata_digest = None
            receipt_digest = None
            rate_digest = None
            if archived is not None:
                receipt_row, receipt, receipt_digest = archived
                artifact = artifacts.get(receipt.artifact_version)
                if artifact is None or rate_material is None:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
                artifact_metadata_digest = artifact[1]
                rate_digest = rate_material[1]
                if (
                    receipt_row["operation_id"] != operation_text
                    or receipt_row["session_id"] != session_id
                ):
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
            expected_request = ItemSearchWireRequestV2.from_plan(
                before_session.plan,
                page=before_session.next_page,
            )
            if (
                operation_text in seen_operations
                or session_id not in seen_created
                or latest_by_session.get(session_id)
                != (before_session, before_payload, before_digest)
                or command.session_id != before_session.session_id
                or command.expected_version != before_session.version
                or command.observed_at != after_session.updated_at
                or after_session.session_id != before_session.session_id
                or after_session.plan != before_session.plan
                or after_session.version != before_session.version + 1
                or row["before_version"] != before_session.version
                or row["command_sha256"] != command_digest
                or row["artifact_metadata_sha256"] != artifact_metadata_digest
                or row["receipt_sha256"] != receipt_digest
                or row["rate_sha256"] != rate_digest
                or row["result_sha256"] != result_digest
                or result.session != after_session
                or result.request_fingerprint != expected_request.request_fingerprint
                or result.receipt != (None if archived is None else archived[1])
                or journal_row["session_id"] != session_id
                or journal_row["receipt_id"] != receipt_id
                or committed_at != _utc_text(command.observed_at)
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            seen_operations.add(operation_text)
            if receipt_id is not None:
                seen_receipts.add(receipt_id)
        else:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

        expected_chain = _chain_hash(
            history_version=history_version,
            mutation_kind=mutation_kind,
            operation_id=operation_id,
            session_id=session_id,
            before_version=row["before_version"],
            after_version=row["after_version"],
            command_sha256=row["command_sha256"],
            session_before_sha256=before_digest,
            session_after_sha256=after_digest,
            artifact_metadata_sha256=row["artifact_metadata_sha256"],
            receipt_id=row["receipt_id"],
            receipt_sha256=row["receipt_sha256"],
            rate_sha256=row["rate_sha256"],
            result_sha256=row["result_sha256"],
            previous_chain_hash=previous_chain,
            committed_at=committed_at,
        )
        if row["chain_hash"] != expected_chain:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        previous_chain = expected_chain
        latest_by_session[session_id] = after_session, after_payload, after_digest

    if (
        len(rows) != mutation_count
        or previous_chain != state_head
        or latest_by_session != sessions
        or seen_created != set(sessions)
        or seen_operations != set(commands)
        or seen_receipts != set(receipts)
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)


@final
class OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2:
    """Fixed-path transactional archive, metadata repository, and UoW."""

    __slots__ = (
        "_commit_fault_index",
        "_commit_faults",
        "_database",
        "_database_identity",
        "_fault_lock",
        "_pinned_head_hash",
        "_pinned_mutation_count",
        "_process_committed_operations",
        "_process_created_sessions",
        "_root",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        root: Path,
        commit_faults: tuple[SqliteCommitFaultV2, ...] = (),
    ) -> None:
        _environment(environment)
        if type(commit_faults) is not tuple or any(
            type(value) is not SqliteCommitFaultV2 for value in commit_faults
        ):
            fail_item_search_runtime()
        private_root = _validate_root_path(root)
        if not private_root.exists():
            try:
                os.mkdir(private_root, 0o700)
            except OSError:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
        _validate_private_directory(private_root)
        self._root = private_root
        self._database = private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] | None = None
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        self._fault_lock = RLock()
        self._state_lock = RLock()
        self._pinned_mutation_count = 0
        self._pinned_head_hash = _ZERO_HASH
        self._process_committed_operations: set[UUID] = set()
        self._process_created_sessions: set[UUID] = set()
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(allow_create=True)
            self._database_identity = identity
            connection = self._connect(verify=False)
            try:
                self._initialize(connection, created=created)
            finally:
                self._close_safely(connection)
            self._fsync_database_and_directory()
            connection = self._connect(verify=False)
            try:
                self._verify_schema(connection)
                count, head = self._verify_integrity(connection)
                self._validate_database_identity()
                self._pin_state(mutation_count=count, head_hash=head)
            finally:
                self._close_safely(connection)

    @property
    def database_path(self) -> Path:
        return self._database

    @property
    def external_action_count(self) -> int:
        return 0

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
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
            if created:
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            return created, (metadata.st_dev, metadata.st_ino)
        except ItemSearchRuntimeFailure:
            raise
        except OSError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self) -> None:
        _created, identity = self._open_database_file(allow_create=False)
        if self._database_identity is None or identity != self._database_identity:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    def _fsync_database_and_directory(self) -> None:
        _validate_private_directory(self._root)
        root_descriptor = -1
        descriptor = -1
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            root_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | nofollow,
            )
            descriptor = os.open(
                _DATABASE_NAME,
                os.O_RDONLY | os.O_CLOEXEC | nofollow,
                dir_fd=root_descriptor,
            )
            metadata = os.fstat(descriptor)
            if self._database_identity != (metadata.st_dev, metadata.st_ino):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            os.fsync(descriptor)
            os.fsync(root_descriptor)
        except ItemSearchRuntimeFailure:
            raise
        except OSError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

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
            pragmas = {
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone(),
                "foreign_keys": connection.execute("PRAGMA foreign_keys").fetchone(),
                "trusted_schema": connection.execute(
                    "PRAGMA trusted_schema"
                ).fetchone(),
                "temp_store": connection.execute("PRAGMA temp_store").fetchone(),
                "synchronous": connection.execute("PRAGMA synchronous").fetchone(),
                "secure_delete": connection.execute("PRAGMA secure_delete").fetchone(),
                "busy_timeout": connection.execute("PRAGMA busy_timeout").fetchone(),
            }
            if (
                pragmas["journal_mode"] is None
                or tuple(pragmas["journal_mode"]) != ("delete",)
                or pragmas["foreign_keys"] is None
                or tuple(pragmas["foreign_keys"]) != (1,)
                or pragmas["trusted_schema"] is None
                or tuple(pragmas["trusted_schema"]) != (0,)
                or pragmas["temp_store"] is None
                or tuple(pragmas["temp_store"]) != (2,)
                or pragmas["synchronous"] is None
                or tuple(pragmas["synchronous"]) != (2,)
                or pragmas["secure_delete"] is None
                or tuple(pragmas["secure_delete"]) != (1,)
                or pragmas["busy_timeout"] is None
                or tuple(pragmas["busy_timeout"]) != (0,)
            ):
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE
                )
            self._validate_database_identity()
        except sqlite3.OperationalError:
            if connection is not None:
                self._close_safely(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        except sqlite3.DatabaseError:
            if connection is not None:
                self._close_safely(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        except sqlite3.Error:
            if connection is not None:
                self._close_safely(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        except ItemSearchRuntimeFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        if verify:
            try:
                self._verify_schema(connection)
                count, head = self._verify_integrity(connection)
                self._require_monotonic_state(
                    connection,
                    mutation_count=count,
                    head_hash=head,
                )
                self._validate_database_identity()
            except ItemSearchRuntimeFailure:
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
            prior_version = connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        if prior_version is None or tuple(prior_version) != (0,):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        try:
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if existing is None or existing[0] != 0:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_database_identity()
            for _table, statement in _SCHEMA_CREATE_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO st0502_state(state_id, schema_binding, mutation_count, head_hash) VALUES (1, ?, 0, ?)",
                (_SCHEMA_BINDING, _ZERO_HASH),
            )
            for _trigger, statement in _SCHEMA_TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._validate_database_identity()
            connection.execute("COMMIT")
            self._validate_database_identity()
        except ItemSearchRuntimeFailure:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        self._verify_schema(connection)
        self._verify_integrity(connection)

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            if version is None or version[0] != _SCHEMA_VERSION:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
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
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            for table, expected in _SCHEMA_COLUMNS.items():
                rows = connection.execute(f"PRAGMA table_xinfo({table})").fetchall()
                observed = tuple(
                    (row[1], row[2], row[3], row[5], row[6]) for row in rows
                )
                if observed != expected:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
                foreign_key_rows = connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
                foreign_keys = frozenset(
                    (row[2], row[3], row[4], row[5], row[6], row[7])
                    for row in foreign_key_rows
                )
                if (
                    len(foreign_key_rows) != len(_SCHEMA_FOREIGN_KEYS[table])
                    or foreign_keys != _SCHEMA_FOREIGN_KEYS[table]
                ):
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
            strict_rows = connection.execute("PRAGMA table_list").fetchall()
            strict_by_name = {
                row[1]: row[5] for row in strict_rows if row[1] in _SCHEMA_COLUMNS
            }
            if strict_by_name != {name: 1 for name in _SCHEMA_COLUMNS}:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            quick_check = connection.execute("PRAGMA quick_check").fetchall()
            if tuple(tuple(row) for row in quick_check) != (("ok",),):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        except ItemSearchRuntimeFailure:
            raise
        except sqlite3.OperationalError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    @staticmethod
    def _verify_integrity(connection: sqlite3.Connection) -> tuple[int, str]:
        """Recompute every durable binding before trusting persisted results."""

        try:
            full_check = connection.execute("PRAGMA integrity_check").fetchall()
            if tuple(tuple(row) for row in full_check) != (("ok",),):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            mutation_count, state_head, sessions = _integrity_state_and_sessions(
                connection
            )
            artifacts = _integrity_artifacts(connection)
            receipts = _integrity_receipts(
                connection,
                artifacts=artifacts,
                sessions=sessions,
            )
            rates = _integrity_rates(connection, receipts=receipts)
            commands = _integrity_commands(connection)
            journal = _integrity_journal(
                connection,
                commands=commands,
                receipts=receipts,
            )
            _integrity_history(
                connection,
                mutation_count=mutation_count,
                state_head=state_head,
                sessions=sessions,
                artifacts=artifacts,
                receipts=receipts,
                rates=rates,
                commands=commands,
                journal=journal,
            )
            return mutation_count, state_head
        except ItemSearchRuntimeFailure:
            raise
        except sqlite3.OperationalError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        except sqlite3.Error, KeyError, TypeError, ValueError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    def _require_monotonic_state(
        self,
        connection: sqlite3.Connection,
        *,
        mutation_count: int,
        head_hash: str,
    ) -> None:
        if mutation_count < self._pinned_mutation_count:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if self._pinned_mutation_count == 0:
            if self._pinned_head_hash != _ZERO_HASH:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        else:
            pinned = connection.execute(
                "SELECT chain_hash FROM st0502_history WHERE history_version = ?",
                (self._pinned_mutation_count,),
            ).fetchone()
            if pinned is None or pinned["chain_hash"] != self._pinned_head_hash:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if (
            mutation_count == self._pinned_mutation_count
            and head_hash != self._pinned_head_hash
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    def _pin_state(self, *, mutation_count: int, head_hash: str) -> None:
        if mutation_count < self._pinned_mutation_count:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        self._pinned_mutation_count = mutation_count
        self._pinned_head_hash = head_hash

    def _verified_state(self, connection: sqlite3.Connection) -> tuple[int, str]:
        self._validate_database_identity()
        self._verify_schema(connection)
        count, head = self._verify_integrity(connection)
        self._require_monotonic_state(
            connection,
            mutation_count=count,
            head_hash=head,
        )
        self._validate_database_identity()
        return count, head

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _next_fault(self) -> SqliteCommitFaultV2:
        with self._fault_lock:
            fault = (
                self._commit_faults[self._commit_fault_index]
                if self._commit_fault_index < len(self._commit_faults)
                else SqliteCommitFaultV2.NONE
            )
            self._commit_fault_index += 1
            return fault

    def _finish_commit(
        self,
        connection: sqlite3.Connection,
        *,
        mutation_count: int,
        head_hash: str,
        operation_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> None:
        fault = self._next_fault()
        if fault is SqliteCommitFaultV2.KNOWN_BEFORE_COMMIT:
            self._rollback(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_KNOWN_ROLLBACK)
        if fault is SqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT:
            self._rollback(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)
        self._validate_database_identity()
        try:
            connection.execute("COMMIT")
        except sqlite3.Error:
            self._validate_database_identity()
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)
        self._validate_database_identity()
        self._pin_state(mutation_count=mutation_count, head_hash=head_hash)
        if operation_id is not None:
            self._process_committed_operations.add(operation_id)
        if session_id is not None:
            self._process_created_sessions.add(session_id)
        if fault is SqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)

    def _rollback(self, connection: sqlite3.Connection) -> None:
        self._validate_database_identity()
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        self._validate_database_identity()

    @staticmethod
    def _map_sqlite_error(error: sqlite3.Error) -> NoReturn:
        if isinstance(error, sqlite3.IntegrityError):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if isinstance(error, sqlite3.OperationalError):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)

    def create_session(self, session: ItemSearchIngestionSessionV2) -> None:
        if type(session) is not ItemSearchIngestionSessionV2:
            fail_item_search_runtime()
        if session != ItemSearchIngestionSessionV2.initial(
            session_id=session.session_id,
            plan=session.plan,
            created_at=session.created_at,
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
        payload = _json_bytes(_session_mapping(session))
        digest = hashlib.sha256(payload).hexdigest()
        session_id = _uuid_text(session.session_id)
        with _PROCESS_WRITE_LOCK, self._state_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                mutation_count, head_hash = self._verified_state(connection)
                row = connection.execute(
                    "SELECT state_bytes, state_sha256 FROM st0502_sessions "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is not None:
                    existing = self._decode_state_row(row)
                    self._rollback(connection)
                    if existing != session:
                        fail_item_search_runtime(
                            ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                        )
                    self._pin_state(
                        mutation_count=mutation_count,
                        head_hash=head_hash,
                    )
                    return
                connection.execute(
                    "INSERT INTO st0502_sessions(session_id, plan_fingerprint, "
                    "state_bytes, state_sha256, version, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        session.plan.fingerprint,
                        payload,
                        digest,
                        session.version,
                        _utc_text(session.updated_at),
                    ),
                )
                history_version = mutation_count + 1
                committed_at = _utc_text(session.created_at)
                chain_hash = _chain_hash(
                    history_version=history_version,
                    mutation_kind="SESSION_CREATED",
                    operation_id=None,
                    session_id=session_id,
                    before_version=None,
                    after_version=0,
                    command_sha256=None,
                    session_before_sha256=None,
                    session_after_sha256=digest,
                    artifact_metadata_sha256=None,
                    receipt_id=None,
                    receipt_sha256=None,
                    rate_sha256=None,
                    result_sha256=None,
                    previous_chain_hash=head_hash,
                    committed_at=committed_at,
                )
                connection.execute(
                    "INSERT INTO st0502_history(history_version, mutation_kind, "
                    "operation_id, session_id, before_version, after_version, "
                    "command_sha256, session_before_bytes, session_before_sha256, "
                    "session_after_bytes, session_after_sha256, "
                    "artifact_metadata_sha256, receipt_id, receipt_sha256, "
                    "rate_sha256, result_sha256, previous_chain_hash, chain_hash, "
                    "committed_at, external_action_count) VALUES "
                    "(?, 'SESSION_CREATED', NULL, ?, NULL, 0, NULL, NULL, NULL, "
                    "?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, 0)",
                    (
                        history_version,
                        session_id,
                        payload,
                        digest,
                        head_hash,
                        chain_hash,
                        committed_at,
                    ),
                )
                updated = connection.execute(
                    "UPDATE st0502_state SET mutation_count = ?, head_hash = ? "
                    "WHERE state_id = 1 AND mutation_count = ? AND head_hash = ?",
                    (history_version, chain_hash, mutation_count, head_hash),
                )
                if updated.rowcount != 1:
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                    )
                verified_count, verified_head = self._verify_integrity(connection)
                if (verified_count, verified_head) != (
                    history_version,
                    chain_hash,
                ):
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
                self._finish_commit(
                    connection,
                    mutation_count=history_version,
                    head_hash=chain_hash,
                    session_id=session.session_id,
                )
            except ItemSearchRuntimeFailure:
                raise
            except sqlite3.Error as error:
                self._rollback(connection)
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def load_session(self, session_id: object) -> ItemSearchIngestionSessionV2:
        if type(session_id) is not UUID or session_id.int == 0:
            fail_item_search_runtime()
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT state_bytes, state_sha256 FROM st0502_sessions "
                    "WHERE session_id = ?",
                    (_uuid_text(session_id),),
                ).fetchone()
                mutation_count, head_hash = self._verified_state(connection)
                if row is None:
                    if session_id in self._process_created_sessions:
                        fail_item_search_runtime(
                            ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                        )
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.STATE_CONFLICT
                    )
                session = self._decode_state_row(row)
                if session.session_id != session_id:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
                self._pin_state(
                    mutation_count=mutation_count,
                    head_hash=head_hash,
                )
                return session
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    @staticmethod
    def _decode_state_row(row: sqlite3.Row) -> ItemSearchIngestionSessionV2:
        payload = row["state_bytes"]
        digest = row["state_sha256"]
        if (
            type(payload) is not bytes
            or type(digest) is not str
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        return _session_from(_json_object(payload))

    def lookup_step(
        self,
        command: ItemSearchStepCommandV2,
    ) -> PersistedItemSearchStepV2 | None:
        if type(command) is not ItemSearchStepCommandV2:
            fail_item_search_runtime()
        command_payload = _json_bytes(_command_mapping(command))
        command_copy = _command_from(_json_object(command_payload))
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT c.session_id, c.payload_fingerprint, c.payload_bytes, "
                    "c.payload_sha256, j.result_bytes, j.result_sha256 "
                    "FROM st0502_commands AS c JOIN st0502_journal AS j "
                    "ON j.operation_id = c.operation_id WHERE c.operation_id = ?",
                    (_uuid_text(command_copy.operation_id),),
                ).fetchone()
                mutation_count, head_hash = self._verified_state(connection)
                if _command_from(_command_mapping(command)) != command_copy:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.CONTRACT_DRIFT
                    )
                if row is None:
                    if command_copy.operation_id in self._process_committed_operations:
                        fail_item_search_runtime(
                            ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN
                        )
                    self._pin_state(
                        mutation_count=mutation_count,
                        head_hash=head_hash,
                    )
                    return None
                stored_command = _command_from(
                    _json_object(_payload_from_row(row, prefix="payload"))
                )
                if stored_command != command_copy:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                    )
                result = self._decode_result_row(row)
                self._pin_state(
                    mutation_count=mutation_count,
                    head_hash=head_hash,
                )
                return result
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    def recover_commit(
        self,
        command: ItemSearchStepCommandV2,
    ) -> ItemSearchCommitRecoveryV2:
        persisted = self.lookup_step(command)
        return ItemSearchCommitRecoveryV2(
            outcome=(
                CommitRecoveryOutcomeV2.COMMITTED
                if persisted is not None
                else CommitRecoveryOutcomeV2.NOT_COMMITTED
            ),
            persisted=persisted,
        )

    @staticmethod
    def _decode_result_row(row: sqlite3.Row) -> PersistedItemSearchStepV2:
        payload = row["result_bytes"]
        digest = row["result_sha256"]
        if (
            type(payload) is not bytes
            or type(digest) is not str
            or hashlib.sha256(payload).hexdigest() != digest
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        return _result_from(_json_object(payload))

    def commit_success(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        observation: ItemSearchProviderObservationV2,
        page: ParsedItemSearchPageV2,
    ) -> PersistedItemSearchStepV2:
        if (
            type(observation) is not ItemSearchProviderObservationV2
            or observation.kind is not ProviderObservationKindV2.SUCCESS
            or observation.raw_body is None
            or observation.raw_sha256 is None
            or observation.request_fingerprint != request.request_fingerprint
            or observation.observed_at != command.observed_at
            or type(page) is not ParsedItemSearchPageV2
            or page.raw_sha256 != observation.raw_sha256
            or page.request_fingerprint != request.request_fingerprint
            or page.observed_at != observation.observed_at
            or parse_item_search_page_v2(request=request, observation=observation)
            != page
        ):
            fail_item_search_runtime()
        expected_after, _outcome = success_transition_v2(
            session=before,
            page=page,
            observed_at=command.observed_at,
        )
        if after != expected_after:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
        material = _RawArchiveMaterial(
            body=observation.raw_body,
            sha256=observation.raw_sha256,
            observed_at=observation.observed_at,
            rate=observation.rate,
        )
        return self._commit_step(
            command=command,
            before=before,
            after=after,
            request=request,
            material=material,
            failure_class=None,
        )

    def commit_failure(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        failure_class: ProviderFailureClassV2,
        observation: ItemSearchProviderObservationV2 | None,
    ) -> PersistedItemSearchStepV2:
        if type(failure_class) is not ProviderFailureClassV2:
            fail_item_search_runtime()
        material = None
        if observation is not None:
            if (
                type(observation) is not ItemSearchProviderObservationV2
                or observation.request_fingerprint != request.request_fingerprint
                or observation.observed_at != command.observed_at
                or (
                    observation.kind is not ProviderObservationKindV2.SUCCESS
                    and observation.failure_class is not failure_class
                )
                or (
                    observation.kind is ProviderObservationKindV2.SUCCESS
                    and failure_class
                    not in {
                        ProviderFailureClassV2.CONTRACT,
                        ProviderFailureClassV2.INTEGRITY,
                    }
                )
            ):
                fail_item_search_runtime()
            if observation.raw_body is not None:
                if observation.raw_sha256 is None:
                    fail_item_search_runtime()
                material = _RawArchiveMaterial(
                    body=observation.raw_body,
                    sha256=observation.raw_sha256,
                    observed_at=observation.observed_at,
                    rate=None,
                )
        expected_after, _outcome = failure_transition_v2(
            session=before,
            failure_class=failure_class,
            observed_at=command.observed_at,
            retry_after_at=(
                None if observation is None else observation.retry_after_at
            ),
        )
        if after != expected_after:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
        return self._commit_step(
            command=command,
            before=before,
            after=after,
            request=request,
            material=material,
            failure_class=failure_class,
        )

    def _commit_step(
        self,
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
        material: _RawArchiveMaterial | None,
        failure_class: ProviderFailureClassV2 | None,
    ) -> PersistedItemSearchStepV2:
        self._validate_mutation(
            command=command,
            before=before,
            after=after,
            request=request,
        )
        command_payload = _json_bytes(_command_mapping(command))
        command_digest = hashlib.sha256(command_payload).hexdigest()
        before_payload = _json_bytes(_session_mapping(before))
        before_digest = hashlib.sha256(before_payload).hexdigest()
        after_payload = _json_bytes(_session_mapping(after))
        after_digest = hashlib.sha256(after_payload).hexdigest()
        operation_id = _uuid_text(command.operation_id)
        session_id = _uuid_text(command.session_id)
        with _PROCESS_WRITE_LOCK, self._state_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                mutation_count, head_hash = self._verified_state(connection)
                existing = connection.execute(
                    "SELECT c.payload_bytes, c.payload_sha256, j.result_bytes, "
                    "j.result_sha256 FROM st0502_commands AS c "
                    "JOIN st0502_journal AS j ON j.operation_id = c.operation_id "
                    "WHERE c.operation_id = ?",
                    (operation_id,),
                ).fetchone()
                if existing is not None:
                    stored_command = _command_from(
                        _json_object(_payload_from_row(existing, prefix="payload"))
                    )
                    result = self._decode_result_row(existing)
                    self._rollback(connection)
                    if stored_command != command:
                        fail_item_search_runtime(
                            ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                        )
                    self._pin_state(
                        mutation_count=mutation_count,
                        head_hash=head_hash,
                    )
                    return result
                current_row = connection.execute(
                    "SELECT state_bytes, state_sha256, version, plan_fingerprint "
                    "FROM st0502_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if current_row is None:
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.STATE_CONFLICT
                    )
                current = self._decode_state_row(current_row)
                if (
                    current != before
                    or current_row["version"] != before.version
                    or current_row["plan_fingerprint"] != before.plan.fingerprint
                    or current_row["state_bytes"] != before_payload
                    or current_row["state_sha256"] != before_digest
                ):
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                    )
                connection.execute(
                    "INSERT INTO st0502_commands(operation_id, session_id, "
                    "expected_version, observed_at, payload_fingerprint, "
                    "payload_bytes, payload_sha256, external_action_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        operation_id,
                        session_id,
                        command.expected_version,
                        _utc_text(command.observed_at),
                        command.payload_fingerprint,
                        command_payload,
                        command_digest,
                    ),
                )
                archived = (
                    None
                    if material is None
                    else self._archive(
                        connection,
                        command=command,
                        request=request,
                        material=material,
                    )
                )
                receipt = None if archived is None else archived.receipt
                outcome = self._outcome_for(after, failure_class=failure_class)
                result = PersistedItemSearchStepV2(
                    outcome=outcome,
                    session=after,
                    request_fingerprint=request.request_fingerprint,
                    receipt=receipt,
                    failure_class=failure_class,
                )
                updated = connection.execute(
                    "UPDATE st0502_sessions SET state_bytes = ?, "
                    "state_sha256 = ?, version = ?, updated_at = ? "
                    "WHERE session_id = ? AND version = ? AND state_sha256 = ?",
                    (
                        after_payload,
                        after_digest,
                        after.version,
                        _utc_text(after.updated_at),
                        session_id,
                        before.version,
                        before_digest,
                    ),
                )
                if updated.rowcount != 1:
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                    )
                result_payload = _json_bytes(_result_mapping(result))
                result_digest = hashlib.sha256(result_payload).hexdigest()
                receipt_id = None if receipt is None else _uuid_text(receipt.receipt_id)
                committed_at = _utc_text(command.observed_at)
                connection.execute(
                    "INSERT INTO st0502_journal(operation_id, session_id, "
                    "receipt_id, result_bytes, result_sha256, committed_at, "
                    "external_action_count) VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (
                        operation_id,
                        session_id,
                        receipt_id,
                        result_payload,
                        result_digest,
                        committed_at,
                    ),
                )
                history_version = mutation_count + 1
                chain_hash = _chain_hash(
                    history_version=history_version,
                    mutation_kind="STEP_COMMITTED",
                    operation_id=operation_id,
                    session_id=session_id,
                    before_version=before.version,
                    after_version=after.version,
                    command_sha256=command_digest,
                    session_before_sha256=before_digest,
                    session_after_sha256=after_digest,
                    artifact_metadata_sha256=(
                        None if archived is None else archived.artifact_metadata_sha256
                    ),
                    receipt_id=receipt_id,
                    receipt_sha256=(
                        None if archived is None else archived.receipt_sha256
                    ),
                    rate_sha256=(None if archived is None else archived.rate_sha256),
                    result_sha256=result_digest,
                    previous_chain_hash=head_hash,
                    committed_at=committed_at,
                )
                connection.execute(
                    "INSERT INTO st0502_history(history_version, mutation_kind, "
                    "operation_id, session_id, before_version, after_version, "
                    "command_sha256, session_before_bytes, session_before_sha256, "
                    "session_after_bytes, session_after_sha256, "
                    "artifact_metadata_sha256, receipt_id, receipt_sha256, "
                    "rate_sha256, result_sha256, previous_chain_hash, chain_hash, "
                    "committed_at, external_action_count) VALUES "
                    "(?, 'STEP_COMMITTED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, 0)",
                    (
                        history_version,
                        operation_id,
                        session_id,
                        before.version,
                        after.version,
                        command_digest,
                        before_payload,
                        before_digest,
                        after_payload,
                        after_digest,
                        (
                            None
                            if archived is None
                            else archived.artifact_metadata_sha256
                        ),
                        receipt_id,
                        (None if archived is None else archived.receipt_sha256),
                        None if archived is None else archived.rate_sha256,
                        result_digest,
                        head_hash,
                        chain_hash,
                        committed_at,
                    ),
                )
                state_updated = connection.execute(
                    "UPDATE st0502_state SET mutation_count = ?, head_hash = ? "
                    "WHERE state_id = 1 AND mutation_count = ? AND head_hash = ?",
                    (history_version, chain_hash, mutation_count, head_hash),
                )
                if state_updated.rowcount != 1:
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                    )
                verified_count, verified_head = self._verify_integrity(connection)
                if (verified_count, verified_head) != (
                    history_version,
                    chain_hash,
                ):
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
                self._finish_commit(
                    connection,
                    mutation_count=history_version,
                    head_hash=chain_hash,
                    operation_id=command.operation_id,
                )
                return result
            except ItemSearchRuntimeFailure:
                raise
            except sqlite3.Error as error:
                self._rollback(connection)
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)

    @staticmethod
    def _validate_mutation(
        *,
        command: ItemSearchStepCommandV2,
        before: ItemSearchIngestionSessionV2,
        after: ItemSearchIngestionSessionV2,
        request: ItemSearchWireRequestV2,
    ) -> None:
        if (
            type(command) is not ItemSearchStepCommandV2
            or type(before) is not ItemSearchIngestionSessionV2
            or type(after) is not ItemSearchIngestionSessionV2
            or type(request) is not ItemSearchWireRequestV2
            or before.session_id != command.session_id
            or after.session_id != command.session_id
            or command.expected_version != before.version
            or after.version != before.version + 1
            or after.plan != before.plan
            or request.plan_fingerprint != before.plan.fingerprint
            or request.page != before.next_page
            or after.updated_at != command.observed_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)

    @staticmethod
    def _outcome_for(
        session: ItemSearchIngestionSessionV2,
        *,
        failure_class: ProviderFailureClassV2 | None,
    ) -> IngestionStepOutcomeV2:
        if failure_class is ProviderFailureClassV2.UNAVAILABLE:
            return IngestionStepOutcomeV2.PROVIDER_DISABLED
        mapping = {
            IngestionSessionStateV2.READY: IngestionStepOutcomeV2.PAGE_ARCHIVED,
            IngestionSessionStateV2.RETRY_WAIT: IngestionStepOutcomeV2.WAIT_RETRY,
            IngestionSessionStateV2.RATE_LIMITED: (
                IngestionStepOutcomeV2.WAIT_RATE_LIMIT
            ),
            IngestionSessionStateV2.CIRCUIT_OPEN: (IngestionStepOutcomeV2.WAIT_CIRCUIT),
            IngestionSessionStateV2.COMPLETED: IngestionStepOutcomeV2.COMPLETED,
            IngestionSessionStateV2.COMPLETED_BOUNDED: (
                IngestionStepOutcomeV2.COMPLETED_BOUNDED
            ),
            IngestionSessionStateV2.FAILED: IngestionStepOutcomeV2.FAILED,
            IngestionSessionStateV2.QUARANTINED: (IngestionStepOutcomeV2.QUARANTINED),
        }
        return mapping[session.state]

    @staticmethod
    def _archive(
        connection: sqlite3.Connection,
        *,
        command: ItemSearchStepCommandV2,
        request: ItemSearchWireRequestV2,
        material: _RawArchiveMaterial,
    ) -> _ArchivedMaterial:
        if (
            hashlib.sha256(material.body).hexdigest() != material.sha256
            or material.observed_at != command.observed_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        logical_key = f"sha256/{material.sha256[:2]}/{material.sha256}"
        row = connection.execute(
            "SELECT artifact_version, sha256, byte_size, content_type, logical_key, "
            "source, body, created_at, metadata_bytes, metadata_sha256 "
            "FROM st0502_artifacts WHERE sha256 = ?",
            (material.sha256,),
        ).fetchone()
        if row is None:
            version_row = connection.execute(
                "SELECT COALESCE(MAX(artifact_version), 0) + 1 FROM st0502_artifacts"
            ).fetchone()
            if (
                version_row is None
                or type(version_row[0]) is not int
                or version_row[0] < 1
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            version = version_row[0]
            metadata_payload = _json_bytes(
                _artifact_metadata_mapping(
                    artifact_version=version,
                    sha256=material.sha256,
                    byte_size=len(material.body),
                    logical_key=logical_key,
                    created_at=material.observed_at,
                )
            )
            metadata_digest = hashlib.sha256(metadata_payload).hexdigest()
            connection.execute(
                "INSERT INTO st0502_artifacts(artifact_version, sha256, "
                "byte_size, content_type, logical_key, source, body, created_at, "
                "metadata_bytes, metadata_sha256) VALUES "
                "(?, ?, ?, 'application/json', ?, "
                "'RAKUTEN_ITEM_SEARCH_20260701', ?, ?, ?, ?)",
                (
                    version,
                    material.sha256,
                    len(material.body),
                    logical_key,
                    material.body,
                    _utc_text(material.observed_at),
                    metadata_payload,
                    metadata_digest,
                ),
            )
        else:
            version = row["artifact_version"]
            metadata_payload = _payload_from_row(row, prefix="metadata")
            metadata_digest = hashlib.sha256(metadata_payload).hexdigest()
            if (
                type(version) is not int
                or version < 1
                or row["byte_size"] != len(material.body)
                or row["sha256"] != material.sha256
                or row["content_type"] != "application/json"
                or row["logical_key"] != logical_key
                or row["source"] != "RAKUTEN_ITEM_SEARCH_20260701"
                or row["body"] != material.body
                or _json_object(metadata_payload)
                != _artifact_metadata_mapping(
                    artifact_version=version,
                    sha256=material.sha256,
                    byte_size=len(material.body),
                    logical_key=logical_key,
                    created_at=_parse_utc(row["created_at"]),
                )
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        receipt_id = uuid5(
            _RECEIPT_NAMESPACE,
            "\0".join(
                (
                    _uuid_text(command.operation_id),
                    _uuid_text(command.session_id),
                    request.request_fingerprint,
                    material.sha256,
                    str(request.page),
                )
            ),
        )
        receipt = RawArchiveReceiptV2(
            receipt_id=receipt_id,
            artifact_sha256=material.sha256,
            byte_size=len(material.body),
            artifact_version=version,
            logical_key=logical_key,
            request_fingerprint=request.request_fingerprint,
            page=request.page,
            observed_at=material.observed_at,
        )
        receipt_payload = _json_bytes(_receipt_mapping(receipt))
        receipt_digest = hashlib.sha256(receipt_payload).hexdigest()
        connection.execute(
            "INSERT INTO st0502_receipts(receipt_id, operation_id, session_id, "
            "request_fingerprint, page, artifact_sha256, artifact_version, "
            "observed_at, payload_bytes, payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _uuid_text(receipt_id),
                _uuid_text(command.operation_id),
                _uuid_text(command.session_id),
                request.request_fingerprint,
                request.page,
                material.sha256,
                version,
                _utc_text(material.observed_at),
                receipt_payload,
                receipt_digest,
            ),
        )
        rate_payload = _json_bytes(_rate_mapping(material.rate))
        rate_digest = hashlib.sha256(rate_payload).hexdigest()
        connection.execute(
            "INSERT INTO st0502_page_metadata(receipt_id, rate_limit, "
            "rate_remaining, rate_reset_at, payload_bytes, payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _uuid_text(receipt_id),
                None if material.rate is None else material.rate.limit,
                None if material.rate is None else material.rate.remaining,
                (
                    None
                    if material.rate is None or material.rate.reset_at is None
                    else _utc_text(material.rate.reset_at)
                ),
                rate_payload,
                rate_digest,
            ),
        )
        return _ArchivedMaterial(
            receipt=receipt,
            artifact_metadata_sha256=metadata_digest,
            receipt_sha256=receipt_digest,
            rate_sha256=rate_digest,
        )

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        if type(receipt) is not RawArchiveReceiptV2:
            fail_item_search_runtime()
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    """
                SELECT r.request_fingerprint, r.page, r.artifact_sha256,
                       r.artifact_version, r.observed_at, a.byte_size,
                       a.sha256 AS stored_artifact_sha256, a.content_type,
                       a.logical_key, a.source, a.body
                FROM st0502_receipts AS r
                JOIN st0502_artifacts AS a
                  ON a.artifact_version = r.artifact_version
                WHERE r.receipt_id = ?
                """,
                    (str(receipt.receipt_id),),
                ).fetchone()
                mutation_count, head_hash = self._verified_state(connection)
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)
        if row is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        body = row["body"]
        if (
            type(body) is not bytes
            or row["request_fingerprint"] != receipt.request_fingerprint
            or row["page"] != receipt.page
            or row["artifact_sha256"] != receipt.artifact_sha256
            or row["stored_artifact_sha256"] != receipt.artifact_sha256
            or row["artifact_version"] != receipt.artifact_version
            or row["observed_at"] != _utc_text(receipt.observed_at)
            or row["byte_size"] != receipt.byte_size
            or row["content_type"] != "application/json"
            or row["logical_key"] != receipt.logical_key
            or row["source"] != "RAKUTEN_ITEM_SEARCH_20260701"
            or len(body) != receipt.byte_size
            or hashlib.sha256(body).hexdigest() != receipt.artifact_sha256
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        self._pin_state(mutation_count=mutation_count, head_hash=head_hash)
        return body

    def read_page(
        self,
        *,
        receipt: RawArchiveReceiptV2,
        request: ItemSearchWireRequestV2,
    ) -> ParsedItemSearchPageV2:
        if (
            type(receipt) is not RawArchiveReceiptV2
            or type(request) is not ItemSearchWireRequestV2
        ):
            fail_item_search_runtime()
        if (
            receipt.request_fingerprint != request.request_fingerprint
            or receipt.page != request.page
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        body = self.read_raw(receipt)
        with self._state_lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT rate_limit, rate_remaining, rate_reset_at, "
                    "payload_bytes, payload_sha256 FROM st0502_page_metadata "
                    "WHERE receipt_id = ?",
                    (_uuid_text(receipt.receipt_id),),
                ).fetchone()
                mutation_count, head_hash = self._verified_state(connection)
            except sqlite3.Error as error:
                self._map_sqlite_error(error)
            finally:
                self._close_safely(connection)
        if row is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        rate = _rate_from(_json_object(_payload_from_row(row, prefix="payload")))
        if (
            row["rate_limit"] != rate.limit
            or row["rate_remaining"] != rate.remaining
            or row["rate_reset_at"]
            != (None if rate.reset_at is None else _utc_text(rate.reset_at))
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        self._pin_state(mutation_count=mutation_count, head_hash=head_hash)
        observation = ItemSearchProviderObservationV2(
            kind=ProviderObservationKindV2.SUCCESS,
            mode=ProviderModeV2.RECORDED_SYNTHETIC,
            request_fingerprint=request.request_fingerprint,
            observed_at=receipt.observed_at,
            http_status=200,
            request_id="ARCHIVE:ST0502:REPLAY",
            raw_body=body,
            raw_sha256=receipt.artifact_sha256,
            rate=rate,
            retry_after_at=None,
            failure_class=None,
            external_actions=0,
        )
        return parse_item_search_page_v2(request=request, observation=observation)


__all__ = [
    "OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2",
    "SqliteCommitFaultV2",
]
