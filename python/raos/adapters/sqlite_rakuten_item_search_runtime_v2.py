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
import sqlite3
import stat
from threading import RLock
from typing import Any, NoReturn, cast, final
from uuid import UUID, uuid5

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    IngestionSessionStateV2,
    IngestionStepOutcomeV2,
    ItemSearchIngestionSessionV2,
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
_SCHEMA_VERSION = 1
_SCHEMA_CREATE_SQL: tuple[tuple[str, str], ...] = (
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
    artifact_version INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 2 AND byte_size <= 2097152),
    content_type TEXT NOT NULL CHECK (content_type = 'application/json'),
    logical_key TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL CHECK (source = 'RAKUTEN_ITEM_SEARCH_20260701'),
    body BLOB NOT NULL,
    created_at TEXT NOT NULL
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
    UNIQUE(operation_id),
    UNIQUE(session_id, page),
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id),
    FOREIGN KEY(artifact_version) REFERENCES st0502_artifacts(artifact_version)
) STRICT""",
    ),
    (
        "st0502_page_metadata",
        """CREATE TABLE st0502_page_metadata (
    receipt_id TEXT PRIMARY KEY,
    rate_limit INTEGER,
    rate_remaining INTEGER,
    rate_reset_at TEXT,
    CHECK (
        (rate_limit IS NULL AND rate_remaining IS NULL AND rate_reset_at IS NULL)
        OR
        (rate_limit >= 1 AND rate_remaining >= 0 AND rate_remaining <= rate_limit AND rate_reset_at IS NOT NULL)
    ),
    FOREIGN KEY(receipt_id) REFERENCES st0502_receipts(receipt_id)
) STRICT""",
    ),
    (
        "st0502_commands",
        """CREATE TABLE st0502_commands (
    operation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES st0502_sessions(session_id)
) STRICT""",
    ),
)
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
    }
)
_SCHEMA_FOREIGN_KEYS: dict[
    str, tuple[tuple[int, int, str, str, str, str, str, str], ...]
] = {
    "st0502_sessions": (),
    "st0502_artifacts": (),
    "st0502_receipts": (
        (
            0,
            0,
            "st0502_artifacts",
            "artifact_version",
            "artifact_version",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        ),
        (
            1,
            0,
            "st0502_sessions",
            "session_id",
            "session_id",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        ),
    ),
    "st0502_page_metadata": (
        (
            0,
            0,
            "st0502_receipts",
            "receipt_id",
            "receipt_id",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        ),
    ),
    "st0502_commands": (
        (
            0,
            0,
            "st0502_sessions",
            "session_id",
            "session_id",
            "NO ACTION",
            "NO ACTION",
            "NONE",
        ),
    ),
}
_SCHEMA_COLUMNS: dict[str, tuple[tuple[str, str, int, int, int], ...]] = {
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
    ),
    "st0502_page_metadata": (
        ("receipt_id", "TEXT", 1, 1, 0),
        ("rate_limit", "INTEGER", 0, 0, 0),
        ("rate_remaining", "INTEGER", 0, 0, 0),
        ("rate_reset_at", "TEXT", 0, 0, 0),
    ),
    "st0502_commands": (
        ("operation_id", "TEXT", 1, 1, 0),
        ("session_id", "TEXT", 1, 0, 0),
        ("payload_fingerprint", "TEXT", 1, 0, 0),
        ("result_bytes", "BLOB", 1, 0, 0),
        ("result_sha256", "TEXT", 1, 0, 0),
        ("committed_at", "TEXT", 1, 0, 0),
    ),
}


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
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
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
        if current is None or type(current) in {str, bool, int, float}:
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
    return {cast(str, key): value for key, value in raw.items()}


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
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    if parsed.tzinfo is not timezone.utc or parsed.fold:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return parsed


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
        "session_id": str(session.session_id),
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
        session_id = UUID(_string(data["session_id"]))
        state = IngestionSessionStateV2(_string(data["state"]))
        failure = (
            None
            if data["last_failure_class"] is None
            else ProviderFailureClassV2(_string(data["last_failure_class"]))
        )
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return ItemSearchIngestionSessionV2(
        session_id=session_id,
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
        "receipt_id": str(receipt.receipt_id),
        "request_fingerprint": receipt.request_fingerprint,
    }


def _receipt_from(value: object) -> RawArchiveReceiptV2:
    data = _exact_mapping(value, _RECEIPT_KEYS)
    try:
        receipt_id = UUID(_string(data["receipt_id"]))
    except ValueError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
    return RawArchiveReceiptV2(
        receipt_id=receipt_id,
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


def _validate_private_database(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)


@dataclass(frozen=True, slots=True)
class _RawArchiveMaterial:
    body: bytes
    sha256: str
    observed_at: datetime
    rate: RateLimitObservationV2 | None


@final
class OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2:
    """Fixed-path transactional archive, metadata repository, and UoW."""

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
        database = private_root / _DATABASE_NAME
        if not database.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(database, flags, 0o600)
                os.close(descriptor)
            except OSError:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.UNSAFE_PATH)
        _validate_private_database(database)
        self._root = private_root
        self._database = database
        self._commit_faults = commit_faults
        self._commit_fault_index = 0
        self._fault_lock = RLock()
        connection = self._connect(verify_schema=False)
        try:
            self._initialize(connection)
        finally:
            connection.close()
        _validate_private_database(database)

    @property
    def database_path(self) -> Path:
        return self._database

    def _connect(self, *, verify_schema: bool = True) -> sqlite3.Connection:
        _validate_private_directory(self._root)
        _validate_private_database(self._database)
        try:
            connection = sqlite3.connect(
                self._database,
                timeout=0.0,
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
            connection.execute("PRAGMA busy_timeout = 0")
        except sqlite3.OperationalError:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT)
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        if verify_schema:
            try:
                self._verify_schema(connection)
            except ItemSearchRuntimeFailure:
                connection.close()
                raise
        return connection

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        try:
            prior_version = connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        if prior_version is None or prior_version[0] not in {0, _SCHEMA_VERSION}:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        if prior_version[0] == _SCHEMA_VERSION:
            OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2._verify_schema(connection)
            return
        try:
            existing = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master"
            ).fetchone()
            if existing is None or existing[0] != 0:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            connection.execute("BEGIN IMMEDIATE")
            for _table, statement in _SCHEMA_CREATE_SQL:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except ItemSearchRuntimeFailure:
            OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2._rollback(connection)
            raise
        except sqlite3.Error:
            OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2._rollback(connection)
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_UNAVAILABLE)
        OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2._verify_schema(connection)

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
                (
                    "table",
                    "sqlite_sequence",
                    "sqlite_sequence",
                    "CREATE TABLE sqlite_sequence(name,seq)",
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
                foreign_keys = tuple(
                    tuple(row)
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({table})"
                    ).fetchall()
                )
                if foreign_keys != _SCHEMA_FOREIGN_KEYS[table]:
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
                    )
            strict_rows = connection.execute("PRAGMA table_list").fetchall()
            strict_by_name = {
                row[1]: row[5]
                for row in strict_rows
                if row[1] in {*_SCHEMA_COLUMNS, "sqlite_sequence"}
            }
            if strict_by_name != {
                **{name: 1 for name in _SCHEMA_COLUMNS},
                "sqlite_sequence": 0,
            }:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        except ItemSearchRuntimeFailure:
            raise
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)

    def _next_fault(self) -> SqliteCommitFaultV2:
        with self._fault_lock:
            fault = (
                self._commit_faults[self._commit_fault_index]
                if self._commit_fault_index < len(self._commit_faults)
                else SqliteCommitFaultV2.NONE
            )
            self._commit_fault_index += 1
            return fault

    def _finish_commit(self, connection: sqlite3.Connection) -> None:
        fault = self._next_fault()
        if fault is SqliteCommitFaultV2.KNOWN_BEFORE_COMMIT:
            connection.execute("ROLLBACK")
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_KNOWN_ROLLBACK)
        if fault is SqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT:
            connection.execute("ROLLBACK")
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)
        try:
            connection.execute("COMMIT")
        except sqlite3.Error:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)
        if fault is SqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.COMMIT_UNKNOWN)

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

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
        payload = _json_bytes(_session_mapping(session))
        digest = hashlib.sha256(payload).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state_bytes, state_sha256 FROM st0502_sessions WHERE session_id = ?",
                (str(session.session_id),),
            ).fetchone()
            if row is not None:
                existing = self._decode_state_row(row)
                if existing != session:
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                    )
                self._rollback(connection)
                return
            connection.execute(
                "INSERT INTO st0502_sessions(session_id, plan_fingerprint, state_bytes, state_sha256, version, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(session.session_id),
                    session.plan.fingerprint,
                    payload,
                    digest,
                    session.version,
                    _utc_text(session.updated_at),
                ),
            )
            self._finish_commit(connection)
        except ItemSearchRuntimeFailure:
            raise
        except sqlite3.Error as error:
            self._rollback(connection)
            self._map_sqlite_error(error)
        finally:
            connection.close()

    def load_session(self, session_id: object) -> ItemSearchIngestionSessionV2:
        if type(session_id) is not UUID or session_id.int == 0:
            fail_item_search_runtime()
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT state_bytes, state_sha256 FROM st0502_sessions WHERE session_id = ?",
                (str(session_id),),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
        session = self._decode_state_row(row)
        if session.session_id != session_id:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        return session

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
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT session_id, payload_fingerprint, result_bytes, result_sha256 FROM st0502_commands WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            return None
        if (
            row["session_id"] != str(command.session_id)
            or row["payload_fingerprint"] != command.payload_fingerprint
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
        return self._decode_result_row(row)

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
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT session_id, payload_fingerprint, result_bytes, result_sha256 FROM st0502_commands WHERE operation_id = ?",
                (str(command.operation_id),),
            ).fetchone()
            if existing is not None:
                if (
                    existing["session_id"] != str(command.session_id)
                    or existing["payload_fingerprint"] != command.payload_fingerprint
                ):
                    self._rollback(connection)
                    fail_item_search_runtime(
                        ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT
                    )
                result = self._decode_result_row(existing)
                self._rollback(connection)
                return result
            current_row = connection.execute(
                "SELECT state_bytes, state_sha256, version, plan_fingerprint FROM st0502_sessions WHERE session_id = ?",
                (str(command.session_id),),
            ).fetchone()
            if current_row is None:
                self._rollback(connection)
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.STATE_CONFLICT)
            current = self._decode_state_row(current_row)
            if (
                current != before
                or current_row["version"] != before.version
                or current_row["plan_fingerprint"] != before.plan.fingerprint
            ):
                self._rollback(connection)
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                )
            receipt = (
                None
                if material is None
                else self._archive(
                    connection,
                    command=command,
                    request=request,
                    material=material,
                )
            )
            outcome = self._outcome_for(after, failure_class=failure_class)
            result = PersistedItemSearchStepV2(
                outcome=outcome,
                session=after,
                request_fingerprint=request.request_fingerprint,
                receipt=receipt,
                failure_class=failure_class,
            )
            state_payload = _json_bytes(_session_mapping(after))
            updated = connection.execute(
                "UPDATE st0502_sessions SET state_bytes = ?, state_sha256 = ?, version = ?, updated_at = ? WHERE session_id = ? AND version = ?",
                (
                    state_payload,
                    hashlib.sha256(state_payload).hexdigest(),
                    after.version,
                    _utc_text(after.updated_at),
                    str(after.session_id),
                    before.version,
                ),
            )
            if updated.rowcount != 1:
                self._rollback(connection)
                fail_item_search_runtime(
                    ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT
                )
            result_payload = _json_bytes(_result_mapping(result))
            connection.execute(
                "INSERT INTO st0502_commands(operation_id, session_id, payload_fingerprint, result_bytes, result_sha256, committed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(command.operation_id),
                    str(command.session_id),
                    command.payload_fingerprint,
                    result_payload,
                    hashlib.sha256(result_payload).hexdigest(),
                    _utc_text(command.observed_at),
                ),
            )
            self._finish_commit(connection)
            return result
        except ItemSearchRuntimeFailure:
            raise
        except sqlite3.Error as error:
            self._rollback(connection)
            self._map_sqlite_error(error)
        finally:
            connection.close()

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
    ) -> RawArchiveReceiptV2:
        if (
            hashlib.sha256(material.body).hexdigest() != material.sha256
            or material.observed_at != command.observed_at
        ):
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        logical_key = f"sha256/{material.sha256[:2]}/{material.sha256}"
        row = connection.execute(
            "SELECT artifact_version, sha256, byte_size, content_type, logical_key, source, body FROM st0502_artifacts WHERE sha256 = ?",
            (material.sha256,),
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                "INSERT INTO st0502_artifacts(sha256, byte_size, content_type, logical_key, source, body, created_at) VALUES (?, ?, 'application/json', ?, 'RAKUTEN_ITEM_SEARCH_20260701', ?, ?)",
                (
                    material.sha256,
                    len(material.body),
                    logical_key,
                    material.body,
                    _utc_text(material.observed_at),
                ),
            )
            version = cursor.lastrowid
            if type(version) is not int or version < 1:
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        else:
            if (
                row["byte_size"] != len(material.body)
                or row["sha256"] != material.sha256
                or row["content_type"] != "application/json"
                or row["logical_key"] != logical_key
                or row["source"] != "RAKUTEN_ITEM_SEARCH_20260701"
                or row["body"] != material.body
            ):
                fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
            version = row["artifact_version"]
        receipt_id = uuid5(
            _RECEIPT_NAMESPACE,
            "\0".join(
                (
                    str(command.operation_id),
                    str(command.session_id),
                    request.request_fingerprint,
                    material.sha256,
                    str(request.page),
                )
            ),
        )
        connection.execute(
            "INSERT INTO st0502_receipts(receipt_id, operation_id, session_id, request_fingerprint, page, artifact_sha256, artifact_version, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(receipt_id),
                str(command.operation_id),
                str(command.session_id),
                request.request_fingerprint,
                request.page,
                material.sha256,
                version,
                _utc_text(material.observed_at),
            ),
        )
        if material.rate is not None:
            connection.execute(
                "INSERT INTO st0502_page_metadata(receipt_id, rate_limit, rate_remaining, rate_reset_at) VALUES (?, ?, ?, ?)",
                (
                    str(receipt_id),
                    material.rate.limit,
                    material.rate.remaining,
                    (
                        None
                        if material.rate.reset_at is None
                        else _utc_text(material.rate.reset_at)
                    ),
                ),
            )
        return RawArchiveReceiptV2(
            receipt_id=receipt_id,
            artifact_sha256=material.sha256,
            byte_size=len(material.body),
            artifact_version=version,
            logical_key=logical_key,
            request_fingerprint=request.request_fingerprint,
            page=request.page,
            observed_at=material.observed_at,
        )

    def read_raw(self, receipt: RawArchiveReceiptV2) -> bytes:
        if type(receipt) is not RawArchiveReceiptV2:
            fail_item_search_runtime()
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
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
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
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT rate_limit, rate_remaining, rate_reset_at FROM st0502_page_metadata WHERE receipt_id = ?",
                (str(receipt.receipt_id),),
            ).fetchone()
        except sqlite3.Error as error:
            self._map_sqlite_error(error)
        finally:
            connection.close()
        if row is None:
            fail_item_search_runtime(ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY)
        rate = RateLimitObservationV2(
            limit=row["rate_limit"],
            remaining=row["rate_remaining"],
            reset_at=(
                None
                if row["rate_reset_at"] is None
                else _parse_utc(row["rate_reset_at"])
            ),
        )
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
