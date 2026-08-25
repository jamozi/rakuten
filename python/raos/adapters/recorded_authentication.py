"""Owner-private, tamper-evident recorded authentication storage for ST-0401.

This SQLite adapter is a deterministic local evidence surface, not a
Production database adapter. Only a file created by this adapter may be
initialized. Every authorization/session revision and its exact command
intent/result are append-only, hash chained, and fully revalidated at each
transaction boundary. File identity plus a process-lifetime prefix anchor
detect replacement and rollback while this process remains alive. No
cross-process or cross-restart trusted anchor is claimed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
from typing import Any, Final, NoReturn, TypeVar, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    AuthenticationFailure,
    AuthenticationFailureCode,
    AuthorizationTransaction,
    Issuer,
    OidcNonce,
    PkceVerifier,
    PrincipalIdentity,
    RedirectUri,
    Session,
    SessionId,
    Subject,
    require_utc,
    snapshot_authorization_transaction,
    snapshot_session,
    snapshot_session_id,
)


_DATABASE_NAME: Final = "st0401-recorded-auth.sqlite3"
_SCHEMA_VERSION: Final = 2
_APPLICATION_ID: Final = 1_380_400_102
_GENESIS: Final = "0" * 64
_MAX_TEXT_LENGTH: Final = 4096
_MAX_COMMAND_BYTES: Final = 32 * 1024
_T = TypeVar("_T")

_OPERATIONS: Final = frozenset(
    {
        "ADD_AUTHORIZATION",
        "CONSUME_AUTHORIZATION",
        "CREATE_SESSION",
        "REPLACE_SESSION",
        "ROTATE_SESSION",
    }
)

_SCHEMA_TABLE_SQL: Final[tuple[tuple[str, str], ...]] = (
    (
        "recorded_auth_metadata_v2",
        """CREATE TABLE recorded_auth_metadata_v2 (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 2),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    command_count INTEGER NOT NULL CHECK (command_count >= 0),
    command_head_sha256 TEXT NOT NULL CHECK (length(command_head_sha256) = 64)
) STRICT""",
    ),
    (
        "recorded_auth_command_v2",
        """CREATE TABLE recorded_auth_command_v2 (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    operation TEXT NOT NULL CHECK (operation IN ('ADD_AUTHORIZATION', 'CONSUME_AUTHORIZATION', 'CREATE_SESSION', 'REPLACE_SESSION', 'ROTATE_SESSION')),
    entity_fingerprint TEXT NOT NULL CHECK (length(entity_fingerprint) = 64),
    recovery_key TEXT UNIQUE,
    intent_bytes BLOB NOT NULL,
    intent_sha256 TEXT NOT NULL CHECK (length(intent_sha256) = 64),
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    previous_command_sha256 TEXT NOT NULL CHECK (length(previous_command_sha256) = 64),
    command_sha256 TEXT NOT NULL UNIQUE CHECK (length(command_sha256) = 64),
    CHECK ((operation = 'ROTATE_SESSION') = (recovery_key IS NOT NULL))
) STRICT""",
    ),
    (
        "recorded_authorization_revision_v2",
        """CREATE TABLE recorded_authorization_revision_v2 (
    state_fingerprint TEXT NOT NULL CHECK (length(state_fingerprint) = 64),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    nonce TEXT NOT NULL,
    verifier TEXT NOT NULL,
    redirect_uri TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    PRIMARY KEY (state_fingerprint, revision),
    FOREIGN KEY (command_sequence) REFERENCES recorded_auth_command_v2(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_session_revision_v2",
        """CREATE TABLE recorded_session_revision_v2 (
    session_fingerprint TEXT NOT NULL CHECK (length(session_fingerprint) = 64),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    session_id TEXT NOT NULL,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    idle_expires_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    rotated_from TEXT,
    rotated_from_fingerprint TEXT,
    revoked_at TEXT,
    command_sequence INTEGER NOT NULL,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    PRIMARY KEY (session_fingerprint, revision),
    UNIQUE (command_sequence, session_fingerprint),
    CHECK ((rotated_from IS NULL) = (rotated_from_fingerprint IS NULL)),
    FOREIGN KEY (command_sequence) REFERENCES recorded_auth_command_v2(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
)

_SCHEMA_TRIGGER_SQL: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "recorded_auth_metadata_v2_no_delete",
        "recorded_auth_metadata_v2",
        "CREATE TRIGGER recorded_auth_metadata_v2_no_delete BEFORE DELETE ON recorded_auth_metadata_v2 BEGIN SELECT RAISE(ABORT, 'ST0401_METADATA_REQUIRED'); END",
    ),
    (
        "recorded_auth_metadata_v2_guard_update",
        "recorded_auth_metadata_v2",
        "CREATE TRIGGER recorded_auth_metadata_v2_guard_update BEFORE UPDATE ON recorded_auth_metadata_v2 WHEN NEW.singleton != OLD.singleton OR NEW.schema_version != OLD.schema_version OR NEW.schema_binding != OLD.schema_binding OR NEW.command_count != OLD.command_count + 1 OR NEW.command_head_sha256 = OLD.command_head_sha256 BEGIN SELECT RAISE(ABORT, 'ST0401_METADATA_TRANSITION_INVALID'); END",
    ),
    *tuple(
        (
            f"{table}_no_update",
            table,
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'ST0401_APPEND_ONLY'); END",
        )
        for table in (
            "recorded_auth_command_v2",
            "recorded_authorization_revision_v2",
            "recorded_session_revision_v2",
        )
    ),
    *tuple(
        (
            f"{table}_no_delete",
            table,
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'ST0401_APPEND_ONLY'); END",
        )
        for table in (
            "recorded_auth_command_v2",
            "recorded_authorization_revision_v2",
            "recorded_session_revision_v2",
        )
    ),
)


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


_SCHEMA_BINDING: Final = hashlib.sha256(
    "\n".join(
        [f"table\0{name}\0{_normalized_sql(sql)}" for name, sql in _SCHEMA_TABLE_SQL]
        + [
            f"trigger\0{name}\0{table}\0{_normalized_sql(sql)}"
            for name, table, sql in _SCHEMA_TRIGGER_SQL
        ]
    ).encode("utf-8")
).hexdigest()

_AUTO_INDEX_COUNTS: Final = {
    "recorded_auth_command_v2": 2,
    "recorded_authorization_revision_v2": 3,
    "recorded_session_revision_v2": 3,
}
_EXPECTED_AUTO_INDEXES: Final = frozenset(
    ("index", f"sqlite_autoindex_{table}_{index}", table, None)
    for table, count in _AUTO_INDEX_COUNTS.items()
    for index in range(1, count + 1)
)

_SCHEMA_INITIALIZATION_LOCK = RLock()
_PROCESS_REGISTRY_LOCK = RLock()


@dataclass(slots=True)
class _ProcessAnchor:
    database_identity: tuple[int, int]
    count: int
    head: str
    lock: RLock


_PROCESS_ANCHORS: dict[tuple[str, int, int], _ProcessAnchor] = {}


def _raise(code: AuthenticationFailureCode) -> NoReturn:
    raise AuthenticationFailure(code) from None


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _raise(AuthenticationFailureCode.DEVELOPMENT_ONLY)
    return environment


def _require_text(value: object, *, maximum: int = _MAX_TEXT_LENGTH) -> str:
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return value


def _require_optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _require_text(value)


def _require_digest(value: object) -> str:
    text = _require_text(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return text


def _fingerprint(value: object) -> str:
    return _require_digest(value)


def _utc_text(value: datetime) -> str:
    return require_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    text = _require_text(value, maximum=40)
    if not text.endswith("Z"):
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    if _utc_text(parsed) != text:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return parsed


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    _raise(AuthenticationFailureCode.STORAGE_FAILURE)


def _canonical_mapping(value: object) -> dict[str, object]:
    if type(value) is not bytes or not value or len(value) > _MAX_COMMAND_BYTES:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    payload = bytes(value)
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate,
            parse_constant=_reject_constant,
        )
    except AuthenticationFailure:
        raise
    except UnicodeError, json.JSONDecodeError:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    if type(parsed) is not dict:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    mapping = cast(dict[str, object], parsed)
    if _canonical_json_bytes(mapping) != payload:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return mapping


def _record_hash(kind: str, values: tuple[object, ...]) -> str:
    return hashlib.sha256(_canonical_json_bytes([kind, *values])).hexdigest()


def _command_hash(
    *,
    sequence: int,
    operation: str,
    entity_fingerprint: str,
    recovery_key: str | None,
    intent_sha256: str,
    result_sha256: str,
    committed_at: str,
    previous_command_sha256: str,
) -> str:
    return _record_hash(
        "COMMAND",
        (
            sequence,
            operation,
            entity_fingerprint,
            recovery_key,
            intent_sha256,
            result_sha256,
            committed_at,
            previous_command_sha256,
        ),
    )


class RecordedCommitFault(str, Enum):
    """Closed one-shot fault points for local crash/recovery evidence."""

    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _InjectedCrash(RuntimeError):
    __slots__ = ("point",)

    def __init__(self, point: RecordedCommitFault) -> None:
        self.point = point
        super().__init__("RECORDED_PROCESS_CRASH")


@dataclass(frozen=True, slots=True)
class _AuthorizationRevision:
    transaction: AuthorizationTransaction
    revision: int
    command_sequence: int
    previous_record_sha256: str
    record_sha256: str


@dataclass(frozen=True, slots=True)
class _SessionRevision:
    session: Session
    revision: int
    command_sequence: int
    previous_record_sha256: str
    record_sha256: str


@dataclass(frozen=True, slots=True)
class _CommandRevision:
    sequence: int
    operation: str
    entity_fingerprint: str
    recovery_key: str | None
    intent: dict[str, object]
    result: dict[str, object]
    committed_at: datetime
    previous_command_sha256: str
    command_sha256: str


def _authorization_values(
    transaction: AuthorizationTransaction,
    *,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> tuple[object, ...]:
    return (
        transaction.state_fingerprint,
        revision,
        transaction.nonce.reveal(),
        transaction.verifier.reveal(),
        transaction.redirect_uri.reveal(),
        _utc_text(transaction.created_at),
        _utc_text(transaction.expires_at),
        None if transaction.consumed_at is None else _utc_text(transaction.consumed_at),
        command_sequence,
        previous_record_sha256,
    )


def _authorization_revision(
    transaction: AuthorizationTransaction,
    *,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> _AuthorizationRevision:
    detached = snapshot_authorization_transaction(transaction)
    values = _authorization_values(
        detached,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
    )
    return _AuthorizationRevision(
        transaction=detached,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
        record_sha256=_record_hash("AUTHORIZATION_REVISION", values),
    )


def _session_values(
    session: Session,
    *,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> tuple[object, ...]:
    rotated_from = (
        None if session.rotated_from is None else session.rotated_from.reveal()
    )
    rotated_fingerprint = (
        None if session.rotated_from is None else session.rotated_from.fingerprint()
    )
    return (
        session.session_id.fingerprint(),
        revision,
        session.session_id.reveal(),
        session.principal.issuer.reveal(),
        session.principal.subject.reveal(),
        session.principal.display_name,
        _utc_text(session.created_at),
        _utc_text(session.last_seen_at),
        _utc_text(session.idle_expires_at),
        _utc_text(session.absolute_expires_at),
        rotated_from,
        rotated_fingerprint,
        None if session.revoked_at is None else _utc_text(session.revoked_at),
        command_sequence,
        previous_record_sha256,
    )


def _session_revision(
    session: Session,
    *,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> _SessionRevision:
    detached = snapshot_session(session)
    values = _session_values(
        detached,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
    )
    return _SessionRevision(
        session=detached,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
        record_sha256=_record_hash("SESSION_REVISION", values),
    )


def _authorization_payloads(
    operation: str,
    current: _AuthorizationRevision,
    previous: _AuthorizationRevision | None,
) -> tuple[dict[str, object], dict[str, object], datetime]:
    state = current.transaction.state_fingerprint
    intent: dict[str, object]
    if operation == "ADD_AUTHORIZATION":
        if (
            previous is not None
            or current.revision != 1
            or current.transaction.consumed_at is not None
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        intent = {
            "candidate_record_sha256": current.record_sha256,
            "operation": operation,
            "state_fingerprint": state,
        }
        committed_at = current.transaction.created_at
    elif operation == "CONSUME_AUTHORIZATION":
        if (
            previous is None
            or current.revision != previous.revision + 1
            or current.revision != 2
            or previous.transaction.consumed_at is not None
            or current.transaction.consumed_at is None
            or current.transaction.state_fingerprint
            != previous.transaction.state_fingerprint
            or current.transaction.nonce != previous.transaction.nonce
            or current.transaction.verifier != previous.transaction.verifier
            or current.transaction.redirect_uri != previous.transaction.redirect_uri
            or current.transaction.created_at != previous.transaction.created_at
            or current.transaction.expires_at != previous.transaction.expires_at
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        intent = {
            "consumed_at": _utc_text(current.transaction.consumed_at),
            "expected_record_sha256": previous.record_sha256,
            "operation": operation,
            "state_fingerprint": state,
        }
        committed_at = current.transaction.consumed_at
    else:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return (
        intent,
        {
            "authorization_record_sha256": current.record_sha256,
            "operation": operation,
            "state_fingerprint": state,
        },
        committed_at,
    )


def _same_session_identity(first: Session, second: Session) -> bool:
    return (
        first.session_id == second.session_id
        and first.principal == second.principal
        and first.created_at == second.created_at
        and first.absolute_expires_at == second.absolute_expires_at
        and first.rotated_from == second.rotated_from
    )


def _valid_session_replace(previous: Session, current: Session) -> bool:
    if not _same_session_identity(previous, current) or previous.revoked_at is not None:
        return False
    refresh = (
        current.revoked_at is None
        and current.last_seen_at >= previous.last_seen_at
        and current.idle_expires_at >= previous.idle_expires_at
        and (
            current.last_seen_at != previous.last_seen_at
            or current.idle_expires_at != previous.idle_expires_at
        )
    )
    revoke = (
        current.revoked_at is not None
        and current.last_seen_at == previous.last_seen_at
        and current.idle_expires_at == previous.idle_expires_at
    )
    return refresh != revoke


def _session_payloads(
    operation: str,
    rows: tuple[_SessionRevision, ...],
    histories: dict[str, tuple[_SessionRevision, ...]],
    entity_fingerprint: str,
) -> tuple[dict[str, object], dict[str, object], datetime, str | None]:
    if operation == "CREATE_SESSION":
        if len(rows) != 1:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        current = rows[0]
        if (
            current.revision != 1
            or current.session.rotated_from is not None
            or current.session.revoked_at is not None
            or current.session.last_seen_at != current.session.created_at
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        fingerprint = current.session.session_id.fingerprint()
        if fingerprint != entity_fingerprint:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return (
            {
                "candidate_record_sha256": current.record_sha256,
                "operation": operation,
                "session_fingerprint": fingerprint,
            },
            {
                "operation": operation,
                "session_fingerprint": fingerprint,
                "session_record_sha256": current.record_sha256,
            },
            current.session.created_at,
            None,
        )
    if operation == "REPLACE_SESSION":
        if len(rows) != 1:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        current = rows[0]
        history = histories.get(entity_fingerprint)
        if (
            history is None
            or current.revision <= 1
            or history[current.revision - 2].record_sha256
            != current.previous_record_sha256
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        previous = history[current.revision - 2]
        if (
            current.session.session_id.fingerprint() != entity_fingerprint
            or not _valid_session_replace(previous.session, current.session)
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        committed_at = current.session.revoked_at or current.session.last_seen_at
        return (
            {
                "expected_record_sha256": previous.record_sha256,
                "operation": operation,
                "replacement_record_sha256": current.record_sha256,
                "session_fingerprint": entity_fingerprint,
            },
            {
                "operation": operation,
                "session_fingerprint": entity_fingerprint,
                "session_record_sha256": current.record_sha256,
            },
            committed_at,
            None,
        )
    if operation != "ROTATE_SESSION" or len(rows) != 2:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    predecessors = tuple(
        row
        for row in rows
        if row.session.session_id.fingerprint() == entity_fingerprint
    )
    successors = tuple(row for row in rows if row not in predecessors)
    if len(predecessors) != 1 or len(successors) != 1:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    predecessor = predecessors[0]
    successor = successors[0]
    history = histories.get(entity_fingerprint)
    if history is None or predecessor.revision <= 1:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    expected = history[predecessor.revision - 2]
    if (
        expected.record_sha256 != predecessor.previous_record_sha256
        or expected.session.revoked_at is not None
        or predecessor.session.revoked_at is None
        or not _same_session_identity(expected.session, predecessor.session)
        or predecessor.session.last_seen_at != expected.session.last_seen_at
        or predecessor.session.idle_expires_at != expected.session.idle_expires_at
        or successor.revision != 1
        or successor.session.rotated_from != expected.session.session_id
        or successor.session.principal != expected.session.principal
        or successor.session.absolute_expires_at != expected.session.absolute_expires_at
        or successor.session.created_at != predecessor.session.revoked_at
        or successor.session.last_seen_at != successor.session.created_at
        or successor.session.revoked_at is not None
    ):
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    successor_fingerprint = successor.session.session_id.fingerprint()
    return (
        {
            "expected_predecessor_record_sha256": expected.record_sha256,
            "operation": operation,
            "predecessor_fingerprint": entity_fingerprint,
            "revoked_predecessor_record_sha256": predecessor.record_sha256,
            "successor_fingerprint": successor_fingerprint,
            "successor_record_sha256": successor.record_sha256,
        },
        {
            "operation": operation,
            "predecessor_fingerprint": entity_fingerprint,
            "revoked_predecessor_record_sha256": predecessor.record_sha256,
            "successor_fingerprint": successor_fingerprint,
            "successor_record_sha256": successor.record_sha256,
        },
        successor.session.created_at,
        entity_fingerprint,
    )


@final
class RecordedSqliteAuthenticationRepository:
    """Exact-schema, append-only, process-monotonic local repository."""

    __slots__ = (
        "_database_identity",
        "_database_path",
        "_environment",
        "_fault_lock",
        "_fault_once_at",
        "_private_root",
        "_process_anchor",
        "_root_identity",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        fault_once_at: RecordedCommitFault | None = None,
    ) -> None:
        self._environment = _require_development(environment)
        if fault_once_at is not None and type(fault_once_at) is not RecordedCommitFault:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        self._private_root, self._root_identity = self._validate_private_root(
            private_root
        )
        self._database_path = self._private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] = (-1, -1)
        self._fault_once_at = fault_once_at
        self._fault_lock = RLock()
        self._state_lock = RLock()
        self._process_anchor: _ProcessAnchor | None = None
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
                head, count = self._verified_state(connection, check_process=False)
                self._bind_process_anchor(connection, head=head, count=count)
            finally:
                self._close_safely(connection)

    @property
    def database_path(self) -> Path:
        return self._database_path

    @staticmethod
    def _validate_private_root(value: object) -> tuple[Path, tuple[int, int]]:
        if not isinstance(value, Path) or not value.is_absolute():
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        root = Path(os.path.abspath(value))
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = current.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            metadata = root.lstat()
        except AuthenticationFailure:
            raise
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return root, (metadata.st_dev, metadata.st_ino)

    def _open_database_file(
        self, *, allow_create: bool
    ) -> tuple[bool, tuple[int, int]]:
        root_descriptor = -1
        database_descriptor = -1
        created = False
        try:
            root_descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_metadata = os.fstat(root_descriptor)
            if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
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
                        _DATABASE_NAME,
                        flags,
                        dir_fd=root_descriptor,
                    )
            else:
                database_descriptor = os.open(
                    _DATABASE_NAME,
                    flags,
                    dir_fd=root_descriptor,
                )
            metadata = os.fstat(database_descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return created, (metadata.st_dev, metadata.st_ino)
        except AuthenticationFailure:
            raise
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        finally:
            if database_descriptor >= 0:
                os.close(database_descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)

    def _validate_database_identity(self) -> None:
        try:
            root = self._private_root.lstat()
            database = self._database_path.lstat()
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if (
            (root.st_dev, root.st_ino) != self._root_identity
            or stat.S_ISLNK(root.st_mode)
            or not stat.S_ISDIR(root.st_mode)
            or root.st_uid != os.geteuid()
            or stat.S_IMODE(root.st_mode) != 0o700
            or (database.st_dev, database.st_ino) != self._database_identity
            or stat.S_ISLNK(database.st_mode)
            or not stat.S_ISREG(database.st_mode)
            or database.st_uid != os.geteuid()
            or database.st_nlink != 1
            or stat.S_IMODE(database.st_mode) != 0o600
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        _created, identity = self._open_database_file(allow_create=False)
        if identity != self._database_identity:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=5.0,
                isolation_level=None,
            )
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA secure_delete = ON")
            mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            if mode != ("delete",):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._validate_database_identity()
            if verify:
                self._verified_state(connection, check_process=True)
            return connection
        except AuthenticationFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error, OSError:
            if connection is not None:
                self._close_safely(connection)
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() != (
                0,
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            for _name, statement in _SCHEMA_TABLE_SQL:
                connection.execute(statement)
            for _name, _table, statement in _SCHEMA_TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO recorded_auth_metadata_v2 VALUES (1, ?, ?, 0, ?)",
                (_SCHEMA_VERSION, _SCHEMA_BINDING, _GENESIS),
            )
            self._verify_schema(connection)
            self._verify_integrity(connection)
            connection.commit()
            self._validate_database_identity()
        except AuthenticationFailure:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _master_record(row: object) -> tuple[str, str, str, str | None]:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 4:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        kind, name, table, statement = typed_row
        if (
            type(kind) is not str
            or type(name) is not str
            or type(table) is not str
            or (statement is not None and type(statement) is not str)
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return kind, name, table, statement

    def _verify_schema(self, connection: sqlite3.Connection) -> None:
        if (
            connection.execute("PRAGMA application_id").fetchone() != (_APPLICATION_ID,)
            or connection.execute("PRAGMA user_version").fetchone()
            != (_SCHEMA_VERSION,)
            or connection.execute("PRAGMA foreign_keys").fetchone() != (1,)
            or connection.execute("PRAGMA trusted_schema").fetchone() != (0,)
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        expected: set[tuple[str, str, str, str | None]] = {
            ("table", name, name, _normalized_sql(statement))
            for name, statement in _SCHEMA_TABLE_SQL
        }
        expected.update(
            ("trigger", name, table, _normalized_sql(statement))
            for name, table, statement in _SCHEMA_TRIGGER_SQL
        )
        expected.update(_EXPECTED_AUTO_INDEXES)
        observed: set[tuple[str, str, str, str | None]] = set()
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' OR type = 'index'"
        ).fetchall()
        for raw in rows:
            kind, name, table, statement = self._master_record(tuple(raw))
            observed.add(
                (
                    kind,
                    name,
                    table,
                    None if statement is None else _normalized_sql(statement),
                )
            )
        if observed != expected:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        table_state = {
            str(row[1]): (int(row[4]), int(row[5]))
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("recorded_")
        }
        if table_state != {name: (0, 1) for name, _statement in _SCHEMA_TABLE_SQL}:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if (
            connection.execute("PRAGMA integrity_check").fetchone() != ("ok",)
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        metadata = connection.execute(
            "SELECT singleton, schema_version, schema_binding, command_count, "
            "command_head_sha256 FROM recorded_auth_metadata_v2"
        ).fetchall()
        if len(metadata) != 1 or tuple(metadata[0])[:3] != (
            1,
            _SCHEMA_VERSION,
            _SCHEMA_BINDING,
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _authorization_from_row(row: object) -> _AuthorizationRevision:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 11:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        values = typed_row[:10]
        try:
            revision = values[1]
            command_sequence = values[8]
            if (
                type(revision) is not int
                or revision < 1
                or type(command_sequence) is not int
                or command_sequence < 1
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            consumed_text = _require_optional_text(values[7])
            transaction = AuthorizationTransaction(
                state_fingerprint=_fingerprint(values[0]),
                nonce=OidcNonce(_require_text(values[2])),
                verifier=PkceVerifier(_require_text(values[3])),
                redirect_uri=RedirectUri(_require_text(values[4])),
                created_at=_parse_utc(values[5]),
                expires_at=_parse_utc(values[6]),
                consumed_at=(
                    None if consumed_text is None else _parse_utc(consumed_text)
                ),
            )
            previous = _require_digest(values[9])
            record = _authorization_revision(
                transaction,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            )
            if values != _authorization_values(
                transaction,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            ) or record.record_sha256 != _require_digest(typed_row[10]):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return record
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _session_from_row(row: object) -> _SessionRevision:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 16:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        values = typed_row[:15]
        try:
            revision = values[1]
            command_sequence = values[13]
            if (
                type(revision) is not int
                or revision < 1
                or type(command_sequence) is not int
                or command_sequence < 1
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            session_id = SessionId(_require_text(values[2]))
            if session_id.fingerprint() != _fingerprint(values[0]):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            rotated_text = _require_optional_text(values[10])
            rotated_fingerprint = _require_optional_text(values[11])
            if (rotated_text is None) != (rotated_fingerprint is None):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            rotated = None if rotated_text is None else SessionId(rotated_text)
            if rotated is not None and rotated.fingerprint() != _fingerprint(
                rotated_fingerprint
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            revoked_text = _require_optional_text(values[12])
            session = Session(
                session_id=session_id,
                principal=PrincipalIdentity(
                    issuer=Issuer(_require_text(values[3])),
                    subject=Subject(_require_text(values[4])),
                    display_name=_require_text(values[5], maximum=128),
                ),
                created_at=_parse_utc(values[6]),
                last_seen_at=_parse_utc(values[7]),
                idle_expires_at=_parse_utc(values[8]),
                absolute_expires_at=_parse_utc(values[9]),
                rotated_from=rotated,
                revoked_at=None if revoked_text is None else _parse_utc(revoked_text),
            )
            previous = _require_digest(values[14])
            record = _session_revision(
                session,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            )
            if values != _session_values(
                session,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            ) or record.record_sha256 != _require_digest(typed_row[15]):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return record
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _command_from_row(row: object) -> _CommandRevision:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        values = cast(tuple[object, ...], row)
        if len(values) != 11:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        try:
            sequence = values[0]
            if type(sequence) is not int or sequence < 1:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            operation = _require_text(values[1], maximum=32)
            if operation not in _OPERATIONS:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            entity = _fingerprint(values[2])
            recovery = _require_optional_text(values[3])
            if recovery is not None:
                recovery = _fingerprint(recovery)
            intent_bytes = values[4]
            result_bytes = values[6]
            intent = _canonical_mapping(intent_bytes)
            result = _canonical_mapping(result_bytes)
            if hashlib.sha256(cast(bytes, intent_bytes)).hexdigest() != _require_digest(
                values[5]
            ) or hashlib.sha256(
                cast(bytes, result_bytes)
            ).hexdigest() != _require_digest(values[7]):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            committed_at = _parse_utc(values[8])
            previous = _require_digest(values[9])
            command_sha256 = _require_digest(values[10])
            expected = _command_hash(
                sequence=sequence,
                operation=operation,
                entity_fingerprint=entity,
                recovery_key=recovery,
                intent_sha256=cast(str, values[5]),
                result_sha256=cast(str, values[7]),
                committed_at=_utc_text(committed_at),
                previous_command_sha256=previous,
            )
            if expected != command_sha256:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return _CommandRevision(
                sequence=sequence,
                operation=operation,
                entity_fingerprint=entity,
                recovery_key=recovery,
                intent=intent,
                result=result,
                committed_at=committed_at,
                previous_command_sha256=previous,
                command_sha256=command_sha256,
            )
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _authorization_rows(
        connection: sqlite3.Connection,
    ) -> tuple[_AuthorizationRevision, ...]:
        rows = connection.execute(
            "SELECT state_fingerprint, revision, nonce, verifier, redirect_uri, "
            "created_at, expires_at, consumed_at, command_sequence, "
            "previous_record_sha256, record_sha256 "
            "FROM recorded_authorization_revision_v2 "
            "ORDER BY state_fingerprint, revision"
        ).fetchall()
        return tuple(
            RecordedSqliteAuthenticationRepository._authorization_from_row(tuple(row))
            for row in rows
        )

    @staticmethod
    def _session_rows(
        connection: sqlite3.Connection,
    ) -> tuple[_SessionRevision, ...]:
        rows = connection.execute(
            "SELECT session_fingerprint, revision, session_id, issuer, subject, "
            "display_name, created_at, last_seen_at, idle_expires_at, "
            "absolute_expires_at, rotated_from, rotated_from_fingerprint, "
            "revoked_at, command_sequence, previous_record_sha256, record_sha256 "
            "FROM recorded_session_revision_v2 "
            "ORDER BY session_fingerprint, revision"
        ).fetchall()
        return tuple(
            RecordedSqliteAuthenticationRepository._session_from_row(tuple(row))
            for row in rows
        )

    @staticmethod
    def _command_rows(
        connection: sqlite3.Connection,
    ) -> tuple[_CommandRevision, ...]:
        rows = connection.execute(
            "SELECT sequence, operation, entity_fingerprint, recovery_key, "
            "intent_bytes, intent_sha256, result_bytes, result_sha256, "
            "committed_at, previous_command_sha256, command_sha256 "
            "FROM recorded_auth_command_v2 ORDER BY sequence"
        ).fetchall()
        return tuple(
            RecordedSqliteAuthenticationRepository._command_from_row(tuple(row))
            for row in rows
        )

    def _verify_integrity(self, connection: sqlite3.Connection) -> None:
        commands = self._command_rows(connection)
        authorizations = self._authorization_rows(connection)
        sessions = self._session_rows(connection)
        previous_command = _GENESIS
        for expected_sequence, command in enumerate(commands, start=1):
            if (
                command.sequence != expected_sequence
                or command.previous_command_sha256 != previous_command
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            previous_command = command.command_sha256

        authorization_histories: dict[str, tuple[_AuthorizationRevision, ...]] = {}
        for authorization_row in authorizations:
            key = authorization_row.transaction.state_fingerprint
            authorization_histories[key] = (
                *authorization_histories.get(key, ()),
                authorization_row,
            )
        for key, authorization_history in authorization_histories.items():
            previous_record = _GENESIS
            for revision, authorization_row in enumerate(
                authorization_history, start=1
            ):
                if (
                    authorization_row.revision != revision
                    or authorization_row.previous_record_sha256 != previous_record
                    or authorization_row.transaction.state_fingerprint != key
                ):
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                previous_record = authorization_row.record_sha256

        session_histories: dict[str, tuple[_SessionRevision, ...]] = {}
        for session_row in sessions:
            key = session_row.session.session_id.fingerprint()
            session_histories[key] = (*session_histories.get(key, ()), session_row)
        for key, session_history in session_histories.items():
            previous_record = _GENESIS
            for revision, session_row in enumerate(session_history, start=1):
                if (
                    session_row.revision != revision
                    or session_row.previous_record_sha256 != previous_record
                    or session_row.session.session_id.fingerprint() != key
                ):
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                previous_record = session_row.record_sha256

        authorization_by_command: dict[int, list[_AuthorizationRevision]] = {}
        for authorization_row in authorizations:
            authorization_by_command.setdefault(
                authorization_row.command_sequence, []
            ).append(authorization_row)
        session_by_command: dict[int, list[_SessionRevision]] = {}
        for session_row in sessions:
            session_by_command.setdefault(session_row.command_sequence, []).append(
                session_row
            )
        for command in commands:
            if command.operation in {"ADD_AUTHORIZATION", "CONSUME_AUTHORIZATION"}:
                authorization_command_rows = authorization_by_command.pop(
                    command.sequence, []
                )
                if (
                    len(authorization_command_rows) != 1
                    or command.sequence in session_by_command
                ):
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                current = authorization_command_rows[0]
                history = authorization_histories.get(
                    current.transaction.state_fingerprint, ()
                )
                previous = (
                    None if current.revision == 1 else history[current.revision - 2]
                )
                intent, result, committed_at = _authorization_payloads(
                    command.operation, current, previous
                )
                recovery_key = None
                entity = current.transaction.state_fingerprint
            else:
                session_command_rows = session_by_command.pop(command.sequence, [])
                if command.sequence in authorization_by_command:
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                intent, result, committed_at, recovery_key = _session_payloads(
                    command.operation,
                    tuple(session_command_rows),
                    session_histories,
                    command.entity_fingerprint,
                )
                entity = command.entity_fingerprint
            if (
                command.intent != intent
                or command.result != result
                or command.committed_at != committed_at
                or command.recovery_key != recovery_key
                or command.entity_fingerprint != entity
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if authorization_by_command or session_by_command:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

        metadata = connection.execute(
            "SELECT command_count, command_head_sha256 "
            "FROM recorded_auth_metadata_v2 WHERE singleton = 1"
        ).fetchone()
        if (
            metadata is None
            or type(metadata[0]) is not int
            or metadata[0] != len(commands)
            or _require_digest(metadata[1]) != previous_command
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _bind_process_anchor(
        self, connection: sqlite3.Connection, *, head: str, count: int
    ) -> None:
        key = (str(self._private_root), *self._root_identity)
        with _PROCESS_REGISTRY_LOCK:
            anchor = _PROCESS_ANCHORS.get(key)
            if anchor is None:
                anchor = _ProcessAnchor(
                    database_identity=self._database_identity,
                    count=count,
                    head=head,
                    lock=RLock(),
                )
                _PROCESS_ANCHORS[key] = anchor
            self._process_anchor = anchor
        with anchor.lock:
            if anchor.database_identity != self._database_identity:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._require_process_monotonic(connection, count=count, head=head)
            anchor.count = count
            anchor.head = head

    def _require_process_monotonic(
        self, connection: sqlite3.Connection, *, count: int, head: str
    ) -> None:
        anchor = self._process_anchor
        if anchor is None:
            return
        if anchor.database_identity != self._database_identity or count < anchor.count:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if count == anchor.count:
            if head != anchor.head:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return
        if anchor.count == 0:
            if anchor.head != _GENESIS:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return
        prefix = connection.execute(
            "SELECT command_sha256 FROM recorded_auth_command_v2 WHERE sequence = ?",
            (anchor.count,),
        ).fetchone()
        if prefix != (anchor.head,):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _pin_process_state(self, *, count: int, head: str) -> None:
        anchor = self._process_anchor
        if anchor is None or count < anchor.count:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if count == anchor.count and head != anchor.head:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        anchor.count = count
        anchor.head = head

    def _verified_state(
        self, connection: sqlite3.Connection, *, check_process: bool
    ) -> tuple[str, int]:
        self._validate_database_identity()
        self._verify_schema(connection)
        self._verify_integrity(connection)
        row = connection.execute(
            "SELECT command_head_sha256, command_count "
            "FROM recorded_auth_metadata_v2 WHERE singleton = 1"
        ).fetchone()
        if row is None or len(row) != 2 or type(row[1]) is not int or row[1] < 0:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        head = _require_digest(row[0])
        count = row[1]
        if check_process:
            self._require_process_monotonic(connection, count=count, head=head)
        return head, count

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error:
            pass

    def _inject_fault(self, point: RecordedCommitFault) -> None:
        with self._fault_lock:
            if self._fault_once_at is point:
                self._fault_once_at = None
                raise _InjectedCrash(point) from None

    @staticmethod
    def _insert_command(
        connection: sqlite3.Connection,
        *,
        operation: str,
        entity_fingerprint: str,
        recovery_key: str | None,
        intent: dict[str, object],
        result: dict[str, object],
        committed_at: datetime,
    ) -> int:
        metadata = connection.execute(
            "SELECT command_count, command_head_sha256 "
            "FROM recorded_auth_metadata_v2 WHERE singleton = 1"
        ).fetchone()
        if metadata is None or type(metadata[0]) is not int or metadata[0] < 0:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        sequence = metadata[0] + 1
        previous = _require_digest(metadata[1])
        intent_bytes = _canonical_json_bytes(intent)
        result_bytes = _canonical_json_bytes(result)
        intent_sha256 = hashlib.sha256(intent_bytes).hexdigest()
        result_sha256 = hashlib.sha256(result_bytes).hexdigest()
        committed_text = _utc_text(committed_at)
        command_sha256 = _command_hash(
            sequence=sequence,
            operation=operation,
            entity_fingerprint=entity_fingerprint,
            recovery_key=recovery_key,
            intent_sha256=intent_sha256,
            result_sha256=result_sha256,
            committed_at=committed_text,
            previous_command_sha256=previous,
        )
        connection.execute(
            "INSERT INTO recorded_auth_command_v2 VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                operation,
                entity_fingerprint,
                recovery_key,
                intent_bytes,
                intent_sha256,
                result_bytes,
                result_sha256,
                committed_text,
                previous,
                command_sha256,
            ),
        )
        cursor = connection.execute(
            "UPDATE recorded_auth_metadata_v2 "
            "SET command_count = ?, command_head_sha256 = ? "
            "WHERE singleton = 1 AND command_count = ? "
            "AND command_head_sha256 = ?",
            (sequence, command_sha256, sequence - 1, previous),
        )
        if cursor.rowcount != 1:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return sequence

    @staticmethod
    def _insert_authorization(
        connection: sqlite3.Connection, row: _AuthorizationRevision
    ) -> None:
        connection.execute(
            "INSERT INTO recorded_authorization_revision_v2 VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                *_authorization_values(
                    row.transaction,
                    revision=row.revision,
                    command_sequence=row.command_sequence,
                    previous_record_sha256=row.previous_record_sha256,
                ),
                row.record_sha256,
            ),
        )

    @staticmethod
    def _insert_session(connection: sqlite3.Connection, row: _SessionRevision) -> None:
        connection.execute(
            "INSERT INTO recorded_session_revision_v2 VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                *_session_values(
                    row.session,
                    revision=row.revision,
                    command_sequence=row.command_sequence,
                    previous_record_sha256=row.previous_record_sha256,
                ),
                row.record_sha256,
            ),
        )

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=True)
            commit_attempted = False
            committed = False
            pending_head = _GENESIS
            pending_count = 0
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                pending_head, pending_count = self._verified_state(
                    connection, check_process=True
                )
                self._inject_fault(RecordedCommitFault.BEFORE_COMMIT)
                commit_attempted = True
                try:
                    connection.commit()
                except sqlite3.Error:
                    if connection.in_transaction:
                        self._rollback(connection)
                        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                    _raise(AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN)
                committed = True
                self._validate_database_identity()
                self._pin_process_state(count=pending_count, head=pending_head)
                self._inject_fault(RecordedCommitFault.AFTER_COMMIT)
                return result
            except _InjectedCrash as error:
                if not committed:
                    self._rollback(connection)
                if error.point is RecordedCommitFault.AFTER_COMMIT:
                    _raise(AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN)
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            except AuthenticationFailure:
                if not committed:
                    self._rollback(connection)
                raise
            except sqlite3.Error:
                if not committed:
                    self._rollback(connection)
                if commit_attempted and not connection.in_transaction:
                    _raise(AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN)
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            except Exception:
                if not committed:
                    self._rollback(connection)
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            finally:
                self._close_safely(connection)

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=True)
            try:
                connection.execute("BEGIN")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                self._rollback(connection)
                return result
            except AuthenticationFailure:
                self._rollback(connection)
                raise
            except sqlite3.Error:
                self._rollback(connection)
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            except Exception:
                self._rollback(connection)
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            finally:
                self._close_safely(connection)

    @staticmethod
    def _current_authorization(
        connection: sqlite3.Connection, state_fingerprint: str
    ) -> _AuthorizationRevision | None:
        row = connection.execute(
            "SELECT state_fingerprint, revision, nonce, verifier, redirect_uri, "
            "created_at, expires_at, consumed_at, command_sequence, "
            "previous_record_sha256, record_sha256 "
            "FROM recorded_authorization_revision_v2 "
            "WHERE state_fingerprint = ? ORDER BY revision DESC LIMIT 1",
            (state_fingerprint,),
        ).fetchone()
        return (
            None
            if row is None
            else RecordedSqliteAuthenticationRepository._authorization_from_row(
                tuple(row)
            )
        )

    @staticmethod
    def _session_history(
        connection: sqlite3.Connection, session_fingerprint: str
    ) -> tuple[_SessionRevision, ...]:
        rows = connection.execute(
            "SELECT session_fingerprint, revision, session_id, issuer, subject, "
            "display_name, created_at, last_seen_at, idle_expires_at, "
            "absolute_expires_at, rotated_from, rotated_from_fingerprint, "
            "revoked_at, command_sequence, previous_record_sha256, record_sha256 "
            "FROM recorded_session_revision_v2 WHERE session_fingerprint = ? "
            "ORDER BY revision",
            (session_fingerprint,),
        ).fetchall()
        return tuple(
            RecordedSqliteAuthenticationRepository._session_from_row(tuple(row))
            for row in rows
        )

    @staticmethod
    def _current_session(
        connection: sqlite3.Connection, session_fingerprint: str
    ) -> _SessionRevision | None:
        history = RecordedSqliteAuthenticationRepository._session_history(
            connection, session_fingerprint
        )
        return None if not history else history[-1]

    @staticmethod
    def _next_sequence(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT command_count FROM recorded_auth_metadata_v2 WHERE singleton = 1"
        ).fetchone()
        if row is None or type(row[0]) is not int or row[0] < 0:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return row[0] + 1

    def add_authorization(self, transaction: AuthorizationTransaction) -> None:
        _require_development(self._environment)
        try:
            detached = snapshot_authorization_transaction(transaction)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if detached.consumed_at is not None:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> None:
            if (
                self._current_authorization(connection, detached.state_fingerprint)
                is not None
            ):
                _raise(AuthenticationFailureCode.AUTHORIZATION_COLLISION)
            sequence = self._next_sequence(connection)
            row = _authorization_revision(
                detached,
                revision=1,
                command_sequence=sequence,
                previous_record_sha256=_GENESIS,
            )
            intent, result, committed_at = _authorization_payloads(
                "ADD_AUTHORIZATION", row, None
            )
            inserted = self._insert_command(
                connection,
                operation="ADD_AUTHORIZATION",
                entity_fingerprint=detached.state_fingerprint,
                recovery_key=None,
                intent=intent,
                result=result,
                committed_at=committed_at,
            )
            if inserted != sequence:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._insert_authorization(connection, row)

        self._write(operation)

    def consume_authorization(
        self, *, state_fingerprint: str, now: datetime
    ) -> AuthorizationTransaction:
        _require_development(self._environment)
        try:
            fingerprint = _fingerprint(state_fingerprint)
            observed_at = require_utc(now)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> AuthorizationTransaction:
            current = self._current_authorization(connection, fingerprint)
            if current is None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_UNKNOWN)
            if current.transaction.consumed_at is not None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_REPLAY)
            consumed = AuthorizationTransaction(
                state_fingerprint=current.transaction.state_fingerprint,
                nonce=current.transaction.nonce,
                verifier=current.transaction.verifier,
                redirect_uri=current.transaction.redirect_uri,
                created_at=current.transaction.created_at,
                expires_at=current.transaction.expires_at,
                consumed_at=observed_at,
            )
            sequence = self._next_sequence(connection)
            row = _authorization_revision(
                consumed,
                revision=current.revision + 1,
                command_sequence=sequence,
                previous_record_sha256=current.record_sha256,
            )
            intent, result, committed_at = _authorization_payloads(
                "CONSUME_AUTHORIZATION", row, current
            )
            inserted = self._insert_command(
                connection,
                operation="CONSUME_AUTHORIZATION",
                entity_fingerprint=fingerprint,
                recovery_key=None,
                intent=intent,
                result=result,
                committed_at=committed_at,
            )
            if inserted != sequence:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._insert_authorization(connection, row)
            return snapshot_authorization_transaction(consumed)

        consumed = self._write(operation)
        if observed_at >= consumed.expires_at:
            _raise(AuthenticationFailureCode.AUTHORIZATION_EXPIRED)
        return snapshot_authorization_transaction(consumed)

    def create_session(self, session: Session) -> None:
        _require_development(self._environment)
        try:
            detached = snapshot_session(session)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        fingerprint = detached.session_id.fingerprint()

        def operation(connection: sqlite3.Connection) -> None:
            if self._current_session(connection, fingerprint) is not None:
                _raise(AuthenticationFailureCode.SESSION_COLLISION)
            sequence = self._next_sequence(connection)
            row = _session_revision(
                detached,
                revision=1,
                command_sequence=sequence,
                previous_record_sha256=_GENESIS,
            )
            intent, result, committed_at, recovery = _session_payloads(
                "CREATE_SESSION", (row,), {fingerprint: (row,)}, fingerprint
            )
            inserted = self._insert_command(
                connection,
                operation="CREATE_SESSION",
                entity_fingerprint=fingerprint,
                recovery_key=recovery,
                intent=intent,
                result=result,
                committed_at=committed_at,
            )
            if inserted != sequence:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._insert_session(connection, row)

        self._write(operation)

    def load_session(self, session_id: SessionId) -> Session:
        _require_development(self._environment)
        try:
            detached_id = snapshot_session_id(session_id)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        fingerprint = detached_id.fingerprint()

        def operation(connection: sqlite3.Connection) -> Session:
            current = self._current_session(connection, fingerprint)
            if current is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            return snapshot_session(current.session)

        return snapshot_session(self._read(operation))

    def replace_session(self, *, expected: Session, replacement: Session) -> None:
        _require_development(self._environment)
        try:
            expected_value = snapshot_session(expected)
            replacement_value = snapshot_session(replacement)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        if (
            replacement_value.session_id != expected_value.session_id
            or not _valid_session_replace(expected_value, replacement_value)
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        fingerprint = expected_value.session_id.fingerprint()

        def operation(connection: sqlite3.Connection) -> None:
            history = self._session_history(connection, fingerprint)
            if not history or history[-1].session != expected_value:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            current = history[-1]
            sequence = self._next_sequence(connection)
            row = _session_revision(
                replacement_value,
                revision=current.revision + 1,
                command_sequence=sequence,
                previous_record_sha256=current.record_sha256,
            )
            histories = {fingerprint: (*history, row)}
            intent, result, committed_at, recovery = _session_payloads(
                "REPLACE_SESSION", (row,), histories, fingerprint
            )
            inserted = self._insert_command(
                connection,
                operation="REPLACE_SESSION",
                entity_fingerprint=fingerprint,
                recovery_key=recovery,
                intent=intent,
                result=result,
                committed_at=committed_at,
            )
            if inserted != sequence:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._insert_session(connection, row)

        self._write(operation)

    def rotate_session(
        self,
        *,
        expected: Session,
        revoked_predecessor: Session,
        successor: Session,
    ) -> None:
        _require_development(self._environment)
        try:
            expected_value = snapshot_session(expected)
            revoked_value = snapshot_session(revoked_predecessor)
            successor_value = snapshot_session(successor)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)
        predecessor_fingerprint = expected_value.session_id.fingerprint()
        successor_fingerprint = successor_value.session_id.fingerprint()
        if (
            revoked_value.session_id != expected_value.session_id
            or revoked_value.revoked_at is None
            or successor_value.rotated_from != expected_value.session_id
            or successor_fingerprint == predecessor_fingerprint
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)

        def operation(connection: sqlite3.Connection) -> None:
            predecessor_history = self._session_history(
                connection, predecessor_fingerprint
            )
            if (
                not predecessor_history
                or predecessor_history[-1].session != expected_value
                or self._current_session(connection, successor_fingerprint) is not None
            ):
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            current = predecessor_history[-1]
            sequence = self._next_sequence(connection)
            predecessor_row = _session_revision(
                revoked_value,
                revision=current.revision + 1,
                command_sequence=sequence,
                previous_record_sha256=current.record_sha256,
            )
            successor_row = _session_revision(
                successor_value,
                revision=1,
                command_sequence=sequence,
                previous_record_sha256=_GENESIS,
            )
            histories = {
                predecessor_fingerprint: (*predecessor_history, predecessor_row),
                successor_fingerprint: (successor_row,),
            }
            intent, result, committed_at, recovery = _session_payloads(
                "ROTATE_SESSION",
                (predecessor_row, successor_row),
                histories,
                predecessor_fingerprint,
            )
            inserted = self._insert_command(
                connection,
                operation="ROTATE_SESSION",
                entity_fingerprint=predecessor_fingerprint,
                recovery_key=recovery,
                intent=intent,
                result=result,
                committed_at=committed_at,
            )
            if inserted != sequence:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            self._insert_session(connection, predecessor_row)
            self._insert_session(connection, successor_row)

        self._write(operation)

    def recover_session_rotation(self, predecessor_id: SessionId) -> Session:
        _require_development(self._environment)
        try:
            detached_id = snapshot_session_id(predecessor_id)
        except AuthenticationFailure:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        fingerprint = detached_id.fingerprint()

        def operation(connection: sqlite3.Connection) -> Session:
            command_row = connection.execute(
                "SELECT sequence, operation, entity_fingerprint, recovery_key, "
                "intent_bytes, intent_sha256, result_bytes, result_sha256, "
                "committed_at, previous_command_sha256, command_sha256 "
                "FROM recorded_auth_command_v2 WHERE recovery_key = ?",
                (fingerprint,),
            ).fetchone()
            if command_row is None:
                predecessor = self._current_session(connection, fingerprint)
                if predecessor is None:
                    _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
                if predecessor.session.revoked_at is not None:
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                return snapshot_session(predecessor.session)
            command = self._command_from_row(tuple(command_row))
            if (
                command.operation != "ROTATE_SESSION"
                or command.entity_fingerprint != fingerprint
                or command.recovery_key != fingerprint
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            successor_fingerprint = _fingerprint(
                command.result.get("successor_fingerprint")
            )
            successor = self._current_session(connection, successor_fingerprint)
            if (
                successor is None
                or successor.record_sha256
                != _require_digest(command.result.get("successor_record_sha256"))
                or successor.session.rotated_from != detached_id
                or successor.session.revoked_at is not None
            ):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return snapshot_session(successor.session)

        return snapshot_session(self._read(operation))

    def __repr__(self) -> str:
        return (
            "RecordedSqliteAuthenticationRepository("
            "environment='ENV-DEV', path=<redacted>, state=<redacted>)"
        )


__all__ = ["RecordedCommitFault", "RecordedSqliteAuthenticationRepository"]
