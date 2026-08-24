"""Owner-private durable authentication storage for recorded ST-0401 tests.

This adapter is deliberately not a Production database adapter.  It accepts
only the exact development runtime, creates one owner-private SQLite file in a
caller-provided private directory, performs no network access, and exposes no
credential or provider configuration surface.  Each repository mutation owns
one explicit SQLite transaction.  A one-shot fault seam proves rollback and
unknown-commit recovery without weakening the provider or delivery gates.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import Lock
from typing import NoReturn, TypeVar, cast, final

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
)


_DATABASE_NAME = "st0401-recorded-auth.sqlite3"
_SCHEMA_VERSION = "ST0401_RECORDED_AUTH_V1"
_SCHEMA_TABLES = frozenset(
    {"recorded_auth_metadata", "recorded_authorization", "recorded_session"}
)
_FINGERPRINT_LENGTH = 64
_MAX_TEXT_LENGTH = 4096
_T = TypeVar("_T")


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


def _utc_text(value: datetime) -> str:
    return require_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    text = _require_text(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    if _utc_text(parsed) != text:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return parsed


def _record_hash(kind: str, values: tuple[object, ...]) -> str:
    try:
        payload = json.dumps(
            [kind, *values],
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(value: object) -> str:
    text = _require_text(value, maximum=_FINGERPRINT_LENGTH)
    if len(text) != _FINGERPRINT_LENGTH or any(
        character not in "0123456789abcdef" for character in text
    ):
        _raise(AuthenticationFailureCode.STORAGE_FAILURE)
    return text


class RecordedCommitFault(str, Enum):
    """Closed one-shot fault points for local crash/recovery evidence."""

    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _InjectedCrash(RuntimeError):
    __slots__ = ("point",)

    def __init__(self, point: RecordedCommitFault) -> None:
        self.point = point
        super().__init__("RECORDED_PROCESS_CRASH")


@final
class RecordedSqliteAuthenticationRepository:
    """Transactional, restartable repository for synthetic local evidence only."""

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
        self._private_root = self._validate_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._fault_once_at = fault_once_at
        self._fault_lock = Lock()
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        root = Path(os.path.abspath(value))
        try:
            metadata = root.lstat()
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        return root

    def _validate_database_file(self) -> None:
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _create_or_validate_database_file(self) -> None:
        root_descriptor = -1
        descriptor = -1
        try:
            root_descriptor = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=root_descriptor,
                )
                os.fsync(descriptor)
                os.fsync(root_descriptor)
            except FileExistsError:
                pass
        except OSError:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)
        self._validate_database_file()

    def _connect(self) -> sqlite3.Connection:
        self._validate_database_file()
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=0.25,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            if mode != ("delete",):
                connection.close()
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return connection
        except AuthenticationFailure:
            raise
        except sqlite3.Error:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_auth_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization (
                    state_fingerprint TEXT PRIMARY KEY,
                    nonce TEXT NOT NULL,
                    verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_session (
                    session_fingerprint TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    idle_expires_at TEXT NOT NULL,
                    absolute_expires_at TEXT NOT NULL,
                    rotated_from TEXT,
                    rotated_from_fingerprint TEXT UNIQUE,
                    revoked_at TEXT,
                    record_sha256 TEXT NOT NULL,
                    CHECK ((rotated_from IS NULL) = (rotated_from_fingerprint IS NULL))
                )
                """
            )
            row = connection.execute(
                "SELECT schema_version FROM recorded_auth_metadata WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO recorded_auth_metadata(singleton, schema_version) "
                    "VALUES (1, ?)",
                    (_SCHEMA_VERSION,),
                )
            elif row != (_SCHEMA_VERSION,):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            tables = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            )
            if tables != _SCHEMA_TABLES:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            connection.commit()
        except AuthenticationFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()
        self._validate_database_file()

    def _inject_fault(self, point: RecordedCommitFault) -> None:
        with self._fault_lock:
            if self._fault_once_at is point:
                self._fault_once_at = None
                raise _InjectedCrash(point) from None

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        connection = self._connect()
        committed = False
        commit_started = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = operation(connection)
            self._inject_fault(RecordedCommitFault.BEFORE_COMMIT)
            commit_started = True
            connection.commit()
            committed = True
            self._inject_fault(RecordedCommitFault.AFTER_COMMIT)
            return result
        except _InjectedCrash as error:
            if not committed:
                connection.rollback()
            if error.point is RecordedCommitFault.AFTER_COMMIT:
                _raise(AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN)
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        except AuthenticationFailure:
            if not committed:
                connection.rollback()
            raise
        except sqlite3.Error:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            if commit_started:
                _raise(AuthenticationFailureCode.STORAGE_COMMIT_UNKNOWN)
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        except Exception:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            result = operation(connection)
            connection.commit()
            return result
        except AuthenticationFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    @staticmethod
    def _authorization_values(
        transaction: AuthorizationTransaction,
    ) -> tuple[object, ...]:
        return (
            transaction.state_fingerprint,
            transaction.nonce.reveal(),
            transaction.verifier.reveal(),
            transaction.redirect_uri.reveal(),
            _utc_text(transaction.created_at),
            _utc_text(transaction.expires_at),
            None
            if transaction.consumed_at is None
            else _utc_text(transaction.consumed_at),
        )

    @classmethod
    def _authorization_row(
        cls, transaction: AuthorizationTransaction
    ) -> tuple[object, ...]:
        values = cls._authorization_values(transaction)
        return (*values, _record_hash("AUTHORIZATION", values))

    @staticmethod
    def _authorization_from_row(row: object) -> AuthorizationTransaction:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 8:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        values = typed_row[:7]
        expected_hash = _require_text(typed_row[7], maximum=_FINGERPRINT_LENGTH)
        if _record_hash("AUTHORIZATION", values) != expected_hash:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        consumed_text = _require_optional_text(values[6])
        return AuthorizationTransaction(
            state_fingerprint=_fingerprint(values[0]),
            nonce=OidcNonce(_require_text(values[1])),
            verifier=PkceVerifier(_require_text(values[2])),
            redirect_uri=RedirectUri(_require_text(values[3])),
            created_at=_parse_utc(values[4]),
            expires_at=_parse_utc(values[5]),
            consumed_at=None if consumed_text is None else _parse_utc(consumed_text),
        )

    @staticmethod
    def _session_values(session: Session) -> tuple[object, ...]:
        rotated_from = (
            None if session.rotated_from is None else session.rotated_from.reveal()
        )
        rotated_from_fingerprint = (
            None if session.rotated_from is None else session.rotated_from.fingerprint()
        )
        return (
            session.session_id.fingerprint(),
            session.session_id.reveal(),
            session.principal.issuer.reveal(),
            session.principal.subject.reveal(),
            session.principal.display_name,
            _utc_text(session.created_at),
            _utc_text(session.last_seen_at),
            _utc_text(session.idle_expires_at),
            _utc_text(session.absolute_expires_at),
            rotated_from,
            rotated_from_fingerprint,
            None if session.revoked_at is None else _utc_text(session.revoked_at),
        )

    @classmethod
    def _session_row(cls, session: Session) -> tuple[object, ...]:
        values = cls._session_values(session)
        return (*values, _record_hash("SESSION", values))

    @staticmethod
    def _session_from_row(row: object) -> Session:
        if type(row) is not tuple:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 13:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        values = typed_row[:12]
        expected_hash = _require_text(typed_row[12], maximum=_FINGERPRINT_LENGTH)
        if _record_hash("SESSION", values) != expected_hash:
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        session_id = SessionId(_require_text(values[1]))
        if session_id.fingerprint() != _fingerprint(values[0]):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        rotated_from_text = _require_optional_text(values[9])
        rotated_fingerprint = _require_optional_text(values[10])
        if (rotated_from_text is None) != (rotated_fingerprint is None):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        rotated_from = (
            None if rotated_from_text is None else SessionId(rotated_from_text)
        )
        if rotated_from is not None and rotated_from.fingerprint() != _fingerprint(
            rotated_fingerprint
        ):
            _raise(AuthenticationFailureCode.STORAGE_FAILURE)
        revoked_text = _require_optional_text(values[11])
        return Session(
            session_id=session_id,
            principal=PrincipalIdentity(
                issuer=Issuer(_require_text(values[2])),
                subject=Subject(_require_text(values[3])),
                display_name=_require_text(values[4], maximum=128),
            ),
            created_at=_parse_utc(values[5]),
            last_seen_at=_parse_utc(values[6]),
            idle_expires_at=_parse_utc(values[7]),
            absolute_expires_at=_parse_utc(values[8]),
            rotated_from=rotated_from,
            revoked_at=None if revoked_text is None else _parse_utc(revoked_text),
        )

    @staticmethod
    def _select_authorization(
        connection: sqlite3.Connection, state_fingerprint: str
    ) -> tuple[object, ...] | None:
        row = connection.execute(
            "SELECT state_fingerprint, nonce, verifier, redirect_uri, created_at, "
            "expires_at, consumed_at, record_sha256 FROM recorded_authorization "
            "WHERE state_fingerprint = ?",
            (state_fingerprint,),
        ).fetchone()
        return None if row is None else tuple(row)

    @staticmethod
    def _select_session(
        connection: sqlite3.Connection, session_fingerprint: str
    ) -> tuple[object, ...] | None:
        row = connection.execute(
            "SELECT session_fingerprint, session_id, issuer, subject, display_name, "
            "created_at, last_seen_at, idle_expires_at, absolute_expires_at, "
            "rotated_from, rotated_from_fingerprint, revoked_at, record_sha256 "
            "FROM recorded_session WHERE session_fingerprint = ?",
            (session_fingerprint,),
        ).fetchone()
        return None if row is None else tuple(row)

    def add_authorization(self, transaction: AuthorizationTransaction) -> None:
        _require_development(self._environment)
        if (
            type(transaction) is not AuthorizationTransaction
            or transaction.consumed_at is not None
        ):
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> None:
            if self._select_authorization(connection, transaction.state_fingerprint):
                _raise(AuthenticationFailureCode.AUTHORIZATION_COLLISION)
            connection.execute(
                "INSERT INTO recorded_authorization VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._authorization_row(transaction),
            )

        self._write(operation)

    def consume_authorization(
        self, *, state_fingerprint: str, now: datetime
    ) -> AuthorizationTransaction:
        _require_development(self._environment)
        fingerprint = _fingerprint(state_fingerprint)
        observed_at = require_utc(now)

        def operation(connection: sqlite3.Connection) -> AuthorizationTransaction:
            row = self._select_authorization(connection, fingerprint)
            if row is None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_UNKNOWN)
            transaction = self._authorization_from_row(row)
            if transaction.consumed_at is not None:
                _raise(AuthenticationFailureCode.AUTHORIZATION_REPLAY)
            consumed = AuthorizationTransaction(
                state_fingerprint=transaction.state_fingerprint,
                nonce=transaction.nonce,
                verifier=transaction.verifier,
                redirect_uri=transaction.redirect_uri,
                created_at=transaction.created_at,
                expires_at=transaction.expires_at,
                consumed_at=observed_at,
            )
            values = self._authorization_values(consumed)
            cursor = connection.execute(
                "UPDATE recorded_authorization SET consumed_at = ?, record_sha256 = ? "
                "WHERE state_fingerprint = ? AND consumed_at IS NULL AND record_sha256 = ?",
                (
                    values[6],
                    _record_hash("AUTHORIZATION", values),
                    fingerprint,
                    row[7],
                ),
            )
            if cursor.rowcount != 1:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return consumed

        consumed = self._write(operation)
        if observed_at < consumed.created_at:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)
        if observed_at >= consumed.expires_at:
            _raise(AuthenticationFailureCode.AUTHORIZATION_EXPIRED)
        return consumed

    def create_session(self, session: Session) -> None:
        _require_development(self._environment)
        if type(session) is not Session:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> None:
            if self._select_session(connection, session.session_id.fingerprint()):
                _raise(AuthenticationFailureCode.SESSION_COLLISION)
            connection.execute(
                "INSERT INTO recorded_session VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._session_row(session),
            )

        self._write(operation)

    def load_session(self, session_id: SessionId) -> Session:
        _require_development(self._environment)
        if type(session_id) is not SessionId:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> Session:
            row = self._select_session(connection, session_id.fingerprint())
            if row is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            return self._session_from_row(row)

        return self._read(operation)

    def replace_session(self, *, expected: Session, replacement: Session) -> None:
        _require_development(self._environment)
        if (
            type(expected) is not Session
            or type(replacement) is not Session
            or replacement.session_id != expected.session_id
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)

        def operation(connection: sqlite3.Connection) -> None:
            row = self._select_session(connection, expected.session_id.fingerprint())
            if row is None or self._session_from_row(row) != expected:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            replacement_row = self._session_row(replacement)
            cursor = connection.execute(
                "UPDATE recorded_session SET issuer = ?, subject = ?, display_name = ?, "
                "created_at = ?, last_seen_at = ?, idle_expires_at = ?, "
                "absolute_expires_at = ?, rotated_from = ?, rotated_from_fingerprint = ?, "
                "revoked_at = ?, record_sha256 = ? WHERE session_fingerprint = ? "
                "AND record_sha256 = ?",
                (
                    *replacement_row[2:12],
                    replacement_row[12],
                    replacement_row[0],
                    row[12],
                ),
            )
            if cursor.rowcount != 1:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)

        self._write(operation)

    def rotate_session(
        self,
        *,
        expected: Session,
        revoked_predecessor: Session,
        successor: Session,
    ) -> None:
        _require_development(self._environment)
        if (
            type(expected) is not Session
            or type(revoked_predecessor) is not Session
            or type(successor) is not Session
            or revoked_predecessor.session_id != expected.session_id
            or revoked_predecessor.revoked_at is None
            or successor.rotated_from != expected.session_id
        ):
            _raise(AuthenticationFailureCode.SESSION_CONFLICT)

        def operation(connection: sqlite3.Connection) -> None:
            predecessor_row = self._select_session(
                connection, expected.session_id.fingerprint()
            )
            if (
                predecessor_row is None
                or self._session_from_row(predecessor_row) != expected
                or self._select_session(connection, successor.session_id.fingerprint())
                is not None
            ):
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)
            successor_row = self._session_row(successor)
            connection.execute(
                "INSERT INTO recorded_session VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                successor_row,
            )
            revoked_row = self._session_row(revoked_predecessor)
            cursor = connection.execute(
                "UPDATE recorded_session SET revoked_at = ?, record_sha256 = ? "
                "WHERE session_fingerprint = ? AND record_sha256 = ?",
                (
                    revoked_row[11],
                    revoked_row[12],
                    revoked_row[0],
                    predecessor_row[12],
                ),
            )
            if cursor.rowcount != 1:
                _raise(AuthenticationFailureCode.SESSION_CONFLICT)

        self._write(operation)

    def recover_session_rotation(self, predecessor_id: SessionId) -> Session:
        _require_development(self._environment)
        if type(predecessor_id) is not SessionId:
            _raise(AuthenticationFailureCode.MALFORMED_INPUT)

        def operation(connection: sqlite3.Connection) -> Session:
            predecessor_row = self._select_session(
                connection, predecessor_id.fingerprint()
            )
            if predecessor_row is None:
                _raise(AuthenticationFailureCode.SESSION_UNKNOWN)
            predecessor = self._session_from_row(predecessor_row)
            rows = connection.execute(
                "SELECT session_fingerprint, session_id, issuer, subject, display_name, "
                "created_at, last_seen_at, idle_expires_at, absolute_expires_at, "
                "rotated_from, rotated_from_fingerprint, revoked_at, record_sha256 "
                "FROM recorded_session WHERE rotated_from_fingerprint = ? LIMIT 2",
                (predecessor_id.fingerprint(),),
            ).fetchall()
            successors = tuple(self._session_from_row(tuple(row)) for row in rows)
            if not successors:
                if predecessor.revoked_at is not None:
                    _raise(AuthenticationFailureCode.STORAGE_FAILURE)
                return predecessor
            if len(successors) != 1 or predecessor.revoked_at is None:
                _raise(AuthenticationFailureCode.STORAGE_FAILURE)
            return successors[0]

        return self._read(operation)

    def __repr__(self) -> str:
        return (
            "RecordedSqliteAuthenticationRepository("
            "environment='ENV-DEV', path=<redacted>, state=<redacted>)"
        )


__all__ = ["RecordedCommitFault", "RecordedSqliteAuthenticationRepository"]
