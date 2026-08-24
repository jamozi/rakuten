"""Owner-private durable and factor-neutral ST-0402 recorded adapter.

The adapter is exact-``ENV-DEV`` only, performs no network or provider access,
and writes one owner-private SQLite file selected by the caller.  Every
lifecycle transition, command journal entry, and append-only audit event is
committed in one SQLite transaction.  The fault seam models rollback and an
unknown commit without granting any live MFA, HTTP, publication, or role
authority.
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
from typing import Any, NoReturn, TypeVar, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import Issuer, SessionId, Subject
from raos.domain.iam.step_up import (
    BoundStepUpGrant,
    BoundStepUpGrantId,
    CriticalStepUpAction,
    StepUpAssuranceType,
    StepUpAuditOutcome,
    StepUpAuditRecord,
    StepUpAuthorizationReceipt,
    StepUpBinding,
    StepUpChallenge,
    StepUpChallengeId,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpFailure,
    StepUpFailureCode,
    StepUpOperation,
    StepUpResource,
    StepUpResourceType,
    StepUpVerificationReceipt,
    StepUpVerificationReceiptId,
    fail_step_up,
    require_step_up_utc,
)


_DATABASE_NAME = "st0402-recorded-step-up.sqlite3"
_SCHEMA_VERSION = "ST0402_RECORDED_STEP_UP_V2"
_SCHEMA_TABLES = frozenset(
    {
        "recorded_step_up_metadata",
        "recorded_step_up_challenge",
        "recorded_step_up_receipt",
        "recorded_step_up_grant",
        "recorded_step_up_command",
        "recorded_step_up_audit",
    }
)
_SCHEMA_INDEXES = frozenset(
    {
        "recorded_step_up_challenge_receipt_link_unique",
        "recorded_step_up_receipt_grant_link_unique",
    }
)
_GENESIS_DIGEST = "0" * 64
_MAX_TEXT = 16 * 1024
_T = TypeVar("_T")


def _fail(code: StepUpFailureCode) -> NoReturn:
    fail_step_up(code)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        _fail(StepUpFailureCode.DEVELOPMENT_ONLY)
    return environment


def _text(value: object, *, maximum: int = _MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _sha(value: object) -> str:
    text = _text(value, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return text


def _utc_text(value: datetime) -> str:
    return (
        require_step_up_utc(value)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _instant(value: object) -> datetime:
    text = _text(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    if _utc_text(parsed) != text:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return parsed


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)


def _digest(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        document[key] = value
    return document


def _reject_json_constant(value: str) -> NoReturn:
    del value
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _parse_document(value: object) -> dict[str, object]:
    text = _text(value)
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    if type(parsed) is not dict:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return cast(dict[str, object], parsed)


def _exact(document: object, keys: frozenset[str]) -> dict[str, object]:
    if type(document) is not dict:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    mapping = cast(dict[object, object], document)
    if frozenset(mapping) != keys or any(type(key) is not str for key in mapping):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return cast(dict[str, object], mapping)


def _binding_document(binding: StepUpBinding) -> dict[str, str]:
    if type(binding) is not StepUpBinding:
        _fail(StepUpFailureCode.CLAIM_MALFORMED)
    return {
        "session_id": binding.session_id.reveal(),
        "issuer": binding.issuer.reveal(),
        "subject": binding.subject.reveal(),
        "action": binding.action.value,
        "resource_type": binding.resource.resource_type.value,
        "resource_id": str(binding.resource.resource_id),
    }


def _binding_from_document(document: object) -> StepUpBinding:
    value = _exact(
        document,
        frozenset(
            {
                "session_id",
                "issuer",
                "subject",
                "action",
                "resource_type",
                "resource_id",
            }
        ),
    )
    try:
        resource_id = UUID(_text(value["resource_id"], maximum=36))
        action = CriticalStepUpAction(_text(value["action"], maximum=64))
        resource_type = StepUpResourceType(_text(value["resource_type"], maximum=64))
    except ValueError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return StepUpBinding(
        session_id=SessionId(_text(value["session_id"], maximum=43)),
        issuer=Issuer(_text(value["issuer"], maximum=2048)),
        subject=Subject(_text(value["subject"], maximum=255)),
        action=action,
        resource=StepUpResource(
            resource_type=resource_type,
            resource_id=resource_id,
        ),
    )


def _challenge_document(value: StepUpChallenge) -> dict[str, object]:
    return {
        "challenge_id": value.challenge_id.reveal(),
        "binding": _binding_document(value.binding),
        "created_at": _utc_text(value.created_at),
        "expires_at": _utc_text(value.expires_at),
    }


def _challenge_from_document(document: object) -> StepUpChallenge:
    value = _exact(
        document,
        frozenset({"challenge_id", "binding", "created_at", "expires_at"}),
    )
    return StepUpChallenge(
        challenge_id=StepUpChallengeId(_text(value["challenge_id"], maximum=43)),
        binding=_binding_from_document(value["binding"]),
        created_at=_instant(value["created_at"]),
        expires_at=_instant(value["expires_at"]),
    )


def _verification_document(value: StepUpVerificationReceipt) -> dict[str, object]:
    return {
        "receipt_id": value.receipt_id.reveal(),
        "challenge_id": value.challenge_id.reveal(),
        "binding": _binding_document(value.binding),
        "assurance_type": value.assurance_type.value,
        "verified_at": _utc_text(value.verified_at),
        "expires_at": _utc_text(value.expires_at),
    }


def _verification_from_document(document: object) -> StepUpVerificationReceipt:
    value = _exact(
        document,
        frozenset(
            {
                "receipt_id",
                "challenge_id",
                "binding",
                "assurance_type",
                "verified_at",
                "expires_at",
            }
        ),
    )
    try:
        assurance = StepUpAssuranceType(_text(value["assurance_type"], maximum=32))
    except ValueError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return StepUpVerificationReceipt(
        receipt_id=StepUpVerificationReceiptId(_text(value["receipt_id"], maximum=43)),
        challenge_id=StepUpChallengeId(_text(value["challenge_id"], maximum=43)),
        binding=_binding_from_document(value["binding"]),
        assurance_type=assurance,
        verified_at=_instant(value["verified_at"]),
        expires_at=_instant(value["expires_at"]),
    )


def _grant_document(value: BoundStepUpGrant) -> dict[str, object]:
    return {
        "grant_id": value.grant_id.reveal(),
        "receipt_id": value.receipt_id.reveal(),
        "binding": _binding_document(value.binding),
        "issued_at": _utc_text(value.issued_at),
        "expires_at": _utc_text(value.expires_at),
    }


def _grant_from_document(document: object) -> BoundStepUpGrant:
    value = _exact(
        document,
        frozenset({"grant_id", "receipt_id", "binding", "issued_at", "expires_at"}),
    )
    return BoundStepUpGrant(
        grant_id=BoundStepUpGrantId(_text(value["grant_id"], maximum=43)),
        receipt_id=StepUpVerificationReceiptId(_text(value["receipt_id"], maximum=43)),
        binding=_binding_from_document(value["binding"]),
        issued_at=_instant(value["issued_at"]),
        expires_at=_instant(value["expires_at"]),
    )


def _row_hash(values: tuple[object, ...]) -> str:
    return _digest(("RAOS_ST0402_RECORDED_ROW_V2", *values))


class RecordedStepUpCommitFault(str, Enum):
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


class _InjectedCrash(RuntimeError):
    __slots__ = ("point",)

    def __init__(self, point: RecordedStepUpCommitFault) -> None:
        self.point = point
        super().__init__("RECORDED_STEP_UP_PROCESS_CRASH")


@final
class RecordedSyntheticMfaVerifier:
    """Produce only explicit synthetic multi-factor receipts in ``ENV-DEV``."""

    __slots__ = ("_environment",)

    def __init__(self, *, environment: RuntimeEnvironment) -> None:
        self._environment = _require_development(environment)

    def verify(
        self,
        *,
        challenge: StepUpChallenge,
        receipt_id: StepUpVerificationReceiptId,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpVerificationReceipt:
        _require_development(self._environment)
        if (
            type(challenge) is not StepUpChallenge
            or type(receipt_id) is not StepUpVerificationReceiptId
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        observed_at = require_step_up_utc(now)
        expiry = require_step_up_utc(expires_at)
        if (
            observed_at < challenge.created_at
            or observed_at >= challenge.expires_at
            or not observed_at < expiry <= challenge.expires_at
        ):
            _fail(StepUpFailureCode.CHALLENGE_EXPIRED)
        return StepUpVerificationReceipt(
            receipt_id=receipt_id,
            challenge_id=challenge.challenge_id,
            binding=challenge.binding,
            assurance_type=StepUpAssuranceType.MULTI_FACTOR,
            verified_at=observed_at,
            expires_at=expiry,
        )

    def __repr__(self) -> str:
        return "RecordedSyntheticMfaVerifier(environment='ENV-DEV', factor=<absent>)"


@final
class RecordedSqliteStepUpRepository:
    """Restartable lifecycle, command journal, CAS fence, and audit adapter."""

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        fault_once_at: RecordedStepUpCommitFault | None = None,
    ) -> None:
        self._environment = _require_development(environment)
        if (
            fault_once_at is not None
            and type(fault_once_at) is not RecordedStepUpCommitFault
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        self._private_root = self._validate_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._fault_once_at = fault_once_at
        self._fault_lock = Lock()
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        root = Path(os.path.abspath(value))
        try:
            metadata = root.lstat()
        except OSError:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return root

    def _validate_database_file(self) -> None:
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)

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
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
                timeout=0.5,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            if connection.execute("PRAGMA journal_mode = DELETE").fetchone() != (
                "delete",
            ):
                connection.close()
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return connection
        except StepUpFailure:
            raise
        except sqlite3.Error:
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_step_up_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL
                )"""
            )
            for table, identity, states in (
                ("recorded_step_up_challenge", "challenge", "'PENDING','VERIFIED'"),
                ("recorded_step_up_receipt", "receipt", "'AVAILABLE','CONSUMED'"),
                ("recorded_step_up_grant", "grant", "'ACTIVE','CONSUMED','REVOKED'"),
            ):
                connection.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table} (
                        {identity}_fingerprint TEXT PRIMARY KEY,
                        {identity}_id TEXT NOT NULL UNIQUE,
                        document TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (state IN ({states})),
                        version INTEGER NOT NULL CHECK (version >= 1),
                        link TEXT,
                        record_sha256 TEXT NOT NULL
                    )"""
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "recorded_step_up_challenge_receipt_link_unique "
                "ON recorded_step_up_challenge(link) WHERE link IS NOT NULL"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "recorded_step_up_receipt_grant_link_unique "
                "ON recorded_step_up_receipt(link) WHERE link IS NOT NULL"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_step_up_audit (
                    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
                    command_fingerprint TEXT NOT NULL UNIQUE,
                    operation TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    session_fingerprint TEXT NOT NULL,
                    issuer_fingerprint TEXT NOT NULL,
                    subject_fingerprint TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    digest TEXT NOT NULL UNIQUE,
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_step_up_command (
                    command_fingerprint TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    operation TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    result_fingerprint TEXT NOT NULL,
                    audit_sequence INTEGER NOT NULL UNIQUE REFERENCES recorded_step_up_audit(sequence),
                    record_sha256 TEXT NOT NULL
                )"""
            )
            row = connection.execute(
                "SELECT schema_version FROM recorded_step_up_metadata WHERE singleton=1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO recorded_step_up_metadata VALUES (1, ?)",
                    (_SCHEMA_VERSION,),
                )
            elif row != (_SCHEMA_VERSION,):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            tables = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            )
            if tables != _SCHEMA_TABLES:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            indexes = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            )
            if indexes != _SCHEMA_INDEXES:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            self._validate_all(connection)
            connection.commit()
        except StepUpFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except Exception:
            connection.rollback()
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()
        self._validate_database_file()

    def _inject_fault(self, point: RecordedStepUpCommitFault) -> None:
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
            self._inject_fault(RecordedStepUpCommitFault.BEFORE_COMMIT)
            commit_started = True
            connection.commit()
            committed = True
            self._inject_fault(RecordedStepUpCommitFault.AFTER_COMMIT)
            return result
        except _InjectedCrash as error:
            if not committed:
                connection.rollback()
            if error.point is RecordedStepUpCommitFault.AFTER_COMMIT:
                _fail(StepUpFailureCode.STORAGE_COMMIT_UNKNOWN)
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except StepUpFailure:
            if not committed:
                connection.rollback()
            raise
        except sqlite3.Error:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            _fail(
                StepUpFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else StepUpFailureCode.STORAGE_FAILURE
            )
        except Exception:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            result = operation(connection)
            connection.commit()
            return result
        except StepUpFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except Exception:
            connection.rollback()
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    @staticmethod
    def _object_row(
        *,
        identifier_fingerprint: str,
        identifier: str,
        document: dict[str, object],
        state: str,
        version: int,
        link: str | None,
    ) -> tuple[object, ...]:
        document_text = _json_bytes(document).decode("utf-8")
        values: tuple[object, ...] = (
            identifier_fingerprint,
            identifier,
            document_text,
            state,
            version,
            link,
        )
        return (*values, _row_hash(values))

    @staticmethod
    def _verified_object_row(
        row: object, *, identifier_fingerprint: str
    ) -> tuple[dict[str, object], str, int, str | None]:
        if type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 7:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = typed_row[:6]
        expected = _sha(typed_row[6])
        if _row_hash(values) != expected or _sha(values[0]) != identifier_fingerprint:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        document = _parse_document(values[2])
        state = _text(values[3], maximum=16)
        version = values[4]
        if type(version) is not int or version < 1:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return document, state, version, _optional_text(values[5])

    @staticmethod
    def _select_object(
        connection: sqlite3.Connection,
        *,
        table: str,
        identity: str,
        fingerprint: str,
    ) -> tuple[object, ...] | None:
        if table not in {
            "recorded_step_up_challenge",
            "recorded_step_up_receipt",
            "recorded_step_up_grant",
        } or identity not in {"challenge", "receipt", "grant"}:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        row = connection.execute(
            f"SELECT {identity}_fingerprint,{identity}_id,document,state,version,link,record_sha256 "
            f"FROM {table} WHERE {identity}_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return None if row is None else tuple(row)

    @classmethod
    def _challenge(
        cls, connection: sqlite3.Connection, fingerprint: str
    ) -> tuple[StepUpChallenge, str, int, str | None]:
        row = cls._select_object(
            connection,
            table="recorded_step_up_challenge",
            identity="challenge",
            fingerprint=fingerprint,
        )
        if row is None:
            _fail(StepUpFailureCode.CHALLENGE_UNKNOWN)
        document, state, version, link = cls._verified_object_row(
            row, identifier_fingerprint=fingerprint
        )
        challenge = _challenge_from_document(document)
        if challenge.challenge_id.fingerprint() != fingerprint:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return challenge, state, version, link

    @classmethod
    def _verification(
        cls, connection: sqlite3.Connection, fingerprint: str
    ) -> tuple[StepUpVerificationReceipt, str, int, str | None]:
        row = cls._select_object(
            connection,
            table="recorded_step_up_receipt",
            identity="receipt",
            fingerprint=fingerprint,
        )
        if row is None:
            _fail(StepUpFailureCode.RECEIPT_UNKNOWN)
        document, state, version, link = cls._verified_object_row(
            row, identifier_fingerprint=fingerprint
        )
        verification = _verification_from_document(document)
        if verification.receipt_id.fingerprint() != fingerprint:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return verification, state, version, link

    @classmethod
    def _grant(
        cls, connection: sqlite3.Connection, fingerprint: str
    ) -> tuple[BoundStepUpGrant, str, int, str | None]:
        row = cls._select_object(
            connection,
            table="recorded_step_up_grant",
            identity="grant",
            fingerprint=fingerprint,
        )
        if row is None:
            _fail(StepUpFailureCode.GRANT_UNKNOWN)
        document, state, version, link = cls._verified_object_row(
            row, identifier_fingerprint=fingerprint
        )
        grant = _grant_from_document(document)
        if grant.grant_id.fingerprint() != fingerprint:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return grant, state, version, link

    @staticmethod
    def _audit_values(
        *,
        sequence: int,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        binding: StepUpBinding,
        occurred_at: datetime,
        previous_digest: str,
    ) -> tuple[object, ...]:
        return (
            sequence,
            command_id.fingerprint(),
            operation.value,
            StepUpAuditOutcome.SUCCEEDED.value,
            _utc_text(occurred_at),
            binding.session_id.fingerprint(),
            hashlib.sha256(binding.issuer.reveal().encode()).hexdigest(),
            hashlib.sha256(binding.subject.reveal().encode()).hexdigest(),
            binding.action.value,
            binding.resource.resource_type.value,
            str(binding.resource.resource_id),
            previous_digest,
        )

    @classmethod
    def _append_audit(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        binding: StepUpBinding,
        occurred_at: datetime,
    ) -> StepUpAuditRecord:
        latest = connection.execute(
            "SELECT sequence,digest FROM recorded_step_up_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            sequence, previous = 1, _GENESIS_DIGEST
        else:
            sequence, previous = int(latest[0]) + 1, _sha(latest[1])
        values = cls._audit_values(
            sequence=sequence,
            command_id=command_id,
            operation=operation,
            binding=binding,
            occurred_at=occurred_at,
            previous_digest=previous,
        )
        digest = _digest(("RAOS_ST0402_AUDIT_CHAIN_V2", *values))
        connection.execute(
            "INSERT INTO recorded_step_up_audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*values, digest, _row_hash((*values, digest))),
        )
        return StepUpAuditRecord(
            sequence=sequence,
            command_fingerprint=command_id.fingerprint(),
            operation=operation,
            outcome=StepUpAuditOutcome.SUCCEEDED,
            binding=binding,
            occurred_at=occurred_at,
            previous_digest=previous,
            digest=digest,
        )

    @staticmethod
    def _command_values(
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        payload_sha256: str,
        result_fingerprint: str,
        audit_sequence: int,
    ) -> tuple[object, ...]:
        return (
            command_id.fingerprint(),
            command_id.reveal(),
            operation.value,
            payload_sha256,
            result_fingerprint,
            audit_sequence,
        )

    @classmethod
    def _append_command(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        payload_sha256: str,
        result_fingerprint: str,
        audit_sequence: int,
    ) -> None:
        values = cls._command_values(
            command_id=command_id,
            operation=operation,
            payload_sha256=payload_sha256,
            result_fingerprint=result_fingerprint,
            audit_sequence=audit_sequence,
        )
        connection.execute(
            "INSERT INTO recorded_step_up_command VALUES (?,?,?,?,?,?,?)",
            (*values, _row_hash(values)),
        )

    @staticmethod
    def _command_row(
        connection: sqlite3.Connection, fingerprint: str
    ) -> tuple[object, ...] | None:
        row = connection.execute(
            "SELECT command_fingerprint,command_id,operation,payload_sha256,result_fingerprint,audit_sequence,record_sha256 "
            "FROM recorded_step_up_command WHERE command_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        return None if row is None else tuple(row)

    @classmethod
    def _verified_command(
        cls, row: object
    ) -> tuple[StepUpCommandId, StepUpOperation, str, str, int]:
        if type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        typed_row = cast(tuple[object, ...], row)
        if len(typed_row) != 7:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = typed_row[:6]
        if _row_hash(values) != _sha(typed_row[6]):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        command_id = StepUpCommandId(_text(values[1], maximum=43))
        if command_id.fingerprint() != _sha(values[0]):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        try:
            operation = StepUpOperation(_text(values[2], maximum=32))
        except ValueError:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        payload = _sha(values[3])
        result = _sha(values[4])
        sequence = values[5]
        if type(sequence) is not int or sequence < 1:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return command_id, operation, payload, result, sequence

    @classmethod
    def _audit(
        cls,
        connection: sqlite3.Connection,
        *,
        sequence: int,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        binding: StepUpBinding,
    ) -> StepUpAuditRecord:
        row = connection.execute(
            "SELECT sequence,command_fingerprint,operation,outcome,occurred_at,session_fingerprint,issuer_fingerprint,subject_fingerprint,action,resource_type,resource_id,previous_digest,digest,record_sha256 "
            "FROM recorded_step_up_audit WHERE sequence=?",
            (sequence,),
        ).fetchone()
        if row is None or len(row) != 14:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = tuple(row[:12])
        digest = _sha(row[12])
        if (
            _row_hash((*values, digest)) != _sha(row[13])
            or _digest(("RAOS_ST0402_AUDIT_CHAIN_V2", *values)) != digest
            or values
            != cls._audit_values(
                sequence=sequence,
                command_id=command_id,
                operation=operation,
                binding=binding,
                occurred_at=_instant(values[4]),
                previous_digest=_sha(values[11]),
            )
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return StepUpAuditRecord(
            sequence=sequence,
            command_fingerprint=command_id.fingerprint(),
            operation=operation,
            outcome=StepUpAuditOutcome.SUCCEEDED,
            binding=binding,
            occurred_at=_instant(values[4]),
            previous_digest=_sha(values[11]),
            digest=digest,
        )

    @classmethod
    def _result(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        result_fingerprint: str,
        audit_sequence: int,
    ) -> StepUpCommandResult:
        challenge: StepUpChallenge | None = None
        verification: StepUpVerificationReceipt | None = None
        grant: BoundStepUpGrant | None = None
        authorization: StepUpAuthorizationReceipt | None = None
        if operation is StepUpOperation.BEGIN_CHALLENGE:
            challenge = cls._challenge(connection, result_fingerprint)[0]
            binding = challenge.binding
        elif operation is StepUpOperation.VERIFY_CHALLENGE:
            verification = cls._verification(connection, result_fingerprint)[0]
            binding = verification.binding
        elif operation is StepUpOperation.ISSUE_GRANT:
            grant = cls._grant(connection, result_fingerprint)[0]
            binding = grant.binding
        else:
            grant_value, _state, _version, finalized = cls._grant(
                connection, result_fingerprint
            )
            binding = grant_value.binding
            if operation is StepUpOperation.CONSUME_GRANT:
                if finalized is None:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
                authorization = StepUpAuthorizationReceipt(
                    grant_id=grant_value.grant_id,
                    binding=binding,
                    authorized_at=_instant(finalized),
                )
            else:
                grant = grant_value
        audit = cls._audit(
            connection,
            sequence=audit_sequence,
            command_id=command_id,
            operation=operation,
            binding=binding,
        )
        return StepUpCommandResult(
            command_id=command_id,
            operation=operation,
            audit=audit,
            challenge=challenge,
            verification=verification,
            grant=grant,
            authorization=authorization,
        )

    @classmethod
    def _existing(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        payload_sha256: str,
    ) -> StepUpCommandResult | None:
        row = cls._command_row(connection, command_id.fingerprint())
        if row is None:
            return None
        stored_id, stored_operation, stored_payload, result, sequence = (
            cls._verified_command(row)
        )
        if (
            stored_id != command_id
            or stored_operation is not operation
            or stored_payload != payload_sha256
        ):
            _fail(StepUpFailureCode.COMMAND_CONFLICT)
        return cls._result(
            connection,
            command_id=stored_id,
            operation=stored_operation,
            result_fingerprint=result,
            audit_sequence=sequence,
        )

    def create_challenge(
        self, *, command_id: StepUpCommandId, challenge: StepUpChallenge
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        if (
            type(command_id) is not StepUpCommandId
            or type(challenge) is not StepUpChallenge
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        document = _challenge_document(challenge)
        payload = _digest(
            (
                StepUpOperation.BEGIN_CHALLENGE.value,
                _binding_document(challenge.binding),
                _utc_text(challenge.expires_at),
            )
        )

        def operation(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=command_id,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                payload_sha256=payload,
            )
            if existing is not None:
                return existing
            fingerprint = challenge.challenge_id.fingerprint()
            if (
                self._select_object(
                    connection,
                    table="recorded_step_up_challenge",
                    identity="challenge",
                    fingerprint=fingerprint,
                )
                is not None
            ):
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            connection.execute(
                "INSERT INTO recorded_step_up_challenge VALUES (?,?,?,?,?,?,?)",
                self._object_row(
                    identifier_fingerprint=fingerprint,
                    identifier=challenge.challenge_id.reveal(),
                    document=document,
                    state="PENDING",
                    version=1,
                    link=None,
                ),
            )
            audit = self._append_audit(
                connection,
                command_id=command_id,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                binding=challenge.binding,
                occurred_at=challenge.created_at,
            )
            self._append_command(
                connection,
                command_id=command_id,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                payload_sha256=payload,
                result_fingerprint=fingerprint,
                audit_sequence=audit.sequence,
            )
            return StepUpCommandResult(
                command_id=command_id,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                audit=audit,
                challenge=challenge,
            )

        return self._write(operation)

    def load_challenge(self, challenge_id: StepUpChallengeId) -> StepUpChallenge:
        _require_development(self._environment)
        if type(challenge_id) is not StepUpChallengeId:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        return self._read(
            lambda connection: self._challenge(connection, challenge_id.fingerprint())[
                0
            ]
        )

    def record_verification(
        self,
        *,
        command_id: StepUpCommandId,
        verification: StepUpVerificationReceipt,
        now: datetime,
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        observed_at = require_step_up_utc(now)
        if (
            type(command_id) is not StepUpCommandId
            or type(verification) is not StepUpVerificationReceipt
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        document = _verification_document(verification)
        payload = _digest(
            (
                StepUpOperation.VERIFY_CHALLENGE.value,
                verification.challenge_id.fingerprint(),
                _binding_document(verification.binding),
                _utc_text(verification.expires_at),
            )
        )

        def operation(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=command_id,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                payload_sha256=payload,
            )
            if existing is not None:
                return existing
            challenge, state, version, link = self._challenge(
                connection, verification.challenge_id.fingerprint()
            )
            if challenge.binding != verification.binding:
                _fail(StepUpFailureCode.CHALLENGE_MISMATCH)
            if (
                observed_at < challenge.created_at
                or observed_at >= challenge.expires_at
            ):
                _fail(StepUpFailureCode.CHALLENGE_EXPIRED)
            if state != "PENDING" or link is not None:
                _fail(StepUpFailureCode.CHALLENGE_REPLAY)
            receipt_fingerprint = verification.receipt_id.fingerprint()
            if (
                self._select_object(
                    connection,
                    table="recorded_step_up_receipt",
                    identity="receipt",
                    fingerprint=receipt_fingerprint,
                )
                is not None
            ):
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            updated = self._object_row(
                identifier_fingerprint=challenge.challenge_id.fingerprint(),
                identifier=challenge.challenge_id.reveal(),
                document=_challenge_document(challenge),
                state="VERIFIED",
                version=version + 1,
                link=receipt_fingerprint,
            )
            cursor = connection.execute(
                "UPDATE recorded_step_up_challenge SET challenge_id=?,document=?,state=?,version=?,link=?,record_sha256=? "
                "WHERE challenge_fingerprint=? AND state='PENDING' AND version=?",
                (*updated[1:], updated[0], version),
            )
            if cursor.rowcount != 1:
                _fail(StepUpFailureCode.CHALLENGE_REPLAY)
            connection.execute(
                "INSERT INTO recorded_step_up_receipt VALUES (?,?,?,?,?,?,?)",
                self._object_row(
                    identifier_fingerprint=receipt_fingerprint,
                    identifier=verification.receipt_id.reveal(),
                    document=document,
                    state="AVAILABLE",
                    version=1,
                    link=None,
                ),
            )
            audit = self._append_audit(
                connection,
                command_id=command_id,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                binding=verification.binding,
                occurred_at=observed_at,
            )
            self._append_command(
                connection,
                command_id=command_id,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                payload_sha256=payload,
                result_fingerprint=receipt_fingerprint,
                audit_sequence=audit.sequence,
            )
            return StepUpCommandResult(
                command_id=command_id,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                audit=audit,
                verification=verification,
            )

        return self._write(operation)

    def load_verification(
        self, receipt_id: StepUpVerificationReceiptId
    ) -> StepUpVerificationReceipt:
        _require_development(self._environment)
        if type(receipt_id) is not StepUpVerificationReceiptId:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        return self._read(
            lambda connection: self._verification(connection, receipt_id.fingerprint())[
                0
            ]
        )

    def issue_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant: BoundStepUpGrant,
        now: datetime,
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        observed_at = require_step_up_utc(now)
        if (
            type(command_id) is not StepUpCommandId
            or type(grant) is not BoundStepUpGrant
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        document = _grant_document(grant)
        payload = _digest(
            (
                StepUpOperation.ISSUE_GRANT.value,
                grant.receipt_id.fingerprint(),
                _binding_document(grant.binding),
                _utc_text(grant.expires_at),
            )
        )

        def operation(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=command_id,
                operation=StepUpOperation.ISSUE_GRANT,
                payload_sha256=payload,
            )
            if existing is not None:
                return existing
            verification, state, version, link = self._verification(
                connection, grant.receipt_id.fingerprint()
            )
            if verification.binding != grant.binding:
                _fail(StepUpFailureCode.RECEIPT_MISMATCH)
            if (
                observed_at < verification.verified_at
                or observed_at >= verification.expires_at
            ):
                _fail(StepUpFailureCode.RECEIPT_EXPIRED)
            if state != "AVAILABLE" or link is not None:
                _fail(StepUpFailureCode.RECEIPT_REPLAY)
            grant_fingerprint = grant.grant_id.fingerprint()
            if (
                self._select_object(
                    connection,
                    table="recorded_step_up_grant",
                    identity="grant",
                    fingerprint=grant_fingerprint,
                )
                is not None
            ):
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            updated = self._object_row(
                identifier_fingerprint=verification.receipt_id.fingerprint(),
                identifier=verification.receipt_id.reveal(),
                document=_verification_document(verification),
                state="CONSUMED",
                version=version + 1,
                link=grant_fingerprint,
            )
            cursor = connection.execute(
                "UPDATE recorded_step_up_receipt SET receipt_id=?,document=?,state=?,version=?,link=?,record_sha256=? "
                "WHERE receipt_fingerprint=? AND state='AVAILABLE' AND version=?",
                (*updated[1:], updated[0], version),
            )
            if cursor.rowcount != 1:
                _fail(StepUpFailureCode.RECEIPT_REPLAY)
            connection.execute(
                "INSERT INTO recorded_step_up_grant VALUES (?,?,?,?,?,?,?)",
                self._object_row(
                    identifier_fingerprint=grant_fingerprint,
                    identifier=grant.grant_id.reveal(),
                    document=document,
                    state="ACTIVE",
                    version=1,
                    link=None,
                ),
            )
            audit = self._append_audit(
                connection,
                command_id=command_id,
                operation=StepUpOperation.ISSUE_GRANT,
                binding=grant.binding,
                occurred_at=observed_at,
            )
            self._append_command(
                connection,
                command_id=command_id,
                operation=StepUpOperation.ISSUE_GRANT,
                payload_sha256=payload,
                result_fingerprint=grant_fingerprint,
                audit_sequence=audit.sequence,
            )
            return StepUpCommandResult(
                command_id=command_id,
                operation=StepUpOperation.ISSUE_GRANT,
                audit=audit,
                grant=grant,
            )

        return self._write(operation)

    def load_grant(self, grant_id: BoundStepUpGrantId) -> BoundStepUpGrant:
        _require_development(self._environment)
        if type(grant_id) is not BoundStepUpGrantId:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        return self._read(
            lambda connection: self._grant(connection, grant_id.fingerprint())[0]
        )

    def _finalize_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant_id: BoundStepUpGrantId,
        expected_binding: StepUpBinding,
        now: datetime,
        operation: StepUpOperation,
        final_state: str,
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        observed_at = require_step_up_utc(now)
        if (
            type(command_id) is not StepUpCommandId
            or type(grant_id) is not BoundStepUpGrantId
            or type(expected_binding) is not StepUpBinding
            or operation
            not in {StepUpOperation.CONSUME_GRANT, StepUpOperation.REVOKE_GRANT}
            or final_state not in {"CONSUMED", "REVOKED"}
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        payload = _digest(
            (
                operation.value,
                grant_id.fingerprint(),
                _binding_document(expected_binding),
            )
        )

        def command(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=command_id,
                operation=operation,
                payload_sha256=payload,
            )
            if existing is not None:
                return existing
            grant, state, version, link = self._grant(
                connection, grant_id.fingerprint()
            )
            if grant.binding != expected_binding:
                _fail(StepUpFailureCode.GRANT_MISMATCH)
            if observed_at < grant.issued_at or observed_at >= grant.expires_at:
                _fail(StepUpFailureCode.GRANT_EXPIRED)
            if state == "REVOKED":
                _fail(StepUpFailureCode.GRANT_REVOKED)
            if state != "ACTIVE" or link is not None:
                _fail(StepUpFailureCode.GRANT_REPLAY)
            finalized_at = _utc_text(observed_at)
            updated = self._object_row(
                identifier_fingerprint=grant.grant_id.fingerprint(),
                identifier=grant.grant_id.reveal(),
                document=_grant_document(grant),
                state=final_state,
                version=version + 1,
                link=finalized_at,
            )
            cursor = connection.execute(
                "UPDATE recorded_step_up_grant SET grant_id=?,document=?,state=?,version=?,link=?,record_sha256=? "
                "WHERE grant_fingerprint=? AND state='ACTIVE' AND version=?",
                (*updated[1:], updated[0], version),
            )
            if cursor.rowcount != 1:
                _fail(StepUpFailureCode.GRANT_REPLAY)
            audit = self._append_audit(
                connection,
                command_id=command_id,
                operation=operation,
                binding=grant.binding,
                occurred_at=observed_at,
            )
            self._append_command(
                connection,
                command_id=command_id,
                operation=operation,
                payload_sha256=payload,
                result_fingerprint=grant.grant_id.fingerprint(),
                audit_sequence=audit.sequence,
            )
            if operation is StepUpOperation.CONSUME_GRANT:
                return StepUpCommandResult(
                    command_id=command_id,
                    operation=operation,
                    audit=audit,
                    authorization=StepUpAuthorizationReceipt(
                        grant_id=grant.grant_id,
                        binding=grant.binding,
                        authorized_at=observed_at,
                    ),
                )
            return StepUpCommandResult(
                command_id=command_id,
                operation=operation,
                audit=audit,
                grant=grant,
            )

        return self._write(command)

    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant_id: BoundStepUpGrantId,
        expected_binding: StepUpBinding,
        now: datetime,
    ) -> StepUpCommandResult:
        return self._finalize_grant(
            command_id=command_id,
            grant_id=grant_id,
            expected_binding=expected_binding,
            now=now,
            operation=StepUpOperation.CONSUME_GRANT,
            final_state="CONSUMED",
        )

    def revoke_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant_id: BoundStepUpGrantId,
        expected_binding: StepUpBinding,
        now: datetime,
    ) -> StepUpCommandResult:
        return self._finalize_grant(
            command_id=command_id,
            grant_id=grant_id,
            expected_binding=expected_binding,
            now=now,
            operation=StepUpOperation.REVOKE_GRANT,
            final_state="REVOKED",
        )

    def recover(self, command_id: StepUpCommandId) -> StepUpCommandResult:
        _require_development(self._environment)
        if type(command_id) is not StepUpCommandId:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)

        def operation(connection: sqlite3.Connection) -> StepUpCommandResult:
            row = self._command_row(connection, command_id.fingerprint())
            if row is None:
                _fail(StepUpFailureCode.COMMAND_UNKNOWN)
            stored_id, stored_operation, _payload, result, sequence = (
                self._verified_command(row)
            )
            if stored_id != command_id:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return self._result(
                connection,
                command_id=stored_id,
                operation=stored_operation,
                result_fingerprint=result,
                audit_sequence=sequence,
            )

        return self._read(operation)

    @classmethod
    def _validate_all(cls, connection: sqlite3.Connection) -> None:
        challenge_rows = {
            fingerprint: cls._challenge(connection, fingerprint)
            for (raw_fingerprint,) in connection.execute(
                "SELECT challenge_fingerprint FROM recorded_step_up_challenge "
                "ORDER BY challenge_fingerprint"
            ).fetchall()
            for fingerprint in (_sha(raw_fingerprint),)
        }
        receipt_rows = {
            fingerprint: cls._verification(connection, fingerprint)
            for (raw_fingerprint,) in connection.execute(
                "SELECT receipt_fingerprint FROM recorded_step_up_receipt "
                "ORDER BY receipt_fingerprint"
            ).fetchall()
            for fingerprint in (_sha(raw_fingerprint),)
        }
        grant_rows = {
            fingerprint: cls._grant(connection, fingerprint)
            for (raw_fingerprint,) in connection.execute(
                "SELECT grant_fingerprint FROM recorded_step_up_grant "
                "ORDER BY grant_fingerprint"
            ).fetchall()
            for fingerprint in (_sha(raw_fingerprint),)
        }

        for challenge, state, version, link in challenge_rows.values():
            if state == "PENDING":
                if version != 1 or link is not None:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
                continue
            if state != "VERIFIED" or version != 2 or link is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            receipt_row = receipt_rows.get(_sha(link))
            if receipt_row is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            receipt = receipt_row[0]
            if (
                receipt.challenge_id != challenge.challenge_id
                or receipt.binding != challenge.binding
                or receipt.verified_at < challenge.created_at
                or receipt.verified_at >= challenge.expires_at
                or receipt.expires_at > challenge.expires_at
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)

        for receipt, state, version, link in receipt_rows.values():
            challenge_row = challenge_rows.get(receipt.challenge_id.fingerprint())
            if (
                challenge_row is None
                or challenge_row[1] != "VERIFIED"
                or challenge_row[3] != receipt.receipt_id.fingerprint()
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if state == "AVAILABLE":
                if version != 1 or link is not None:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
                continue
            if state != "CONSUMED" or version != 2 or link is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant_row = grant_rows.get(_sha(link))
            if grant_row is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant = grant_row[0]
            if (
                grant.receipt_id != receipt.receipt_id
                or grant.binding != receipt.binding
                or grant.issued_at < receipt.verified_at
                or grant.issued_at >= receipt.expires_at
                or grant.expires_at > receipt.expires_at
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)

        for grant, state, version, link in grant_rows.values():
            receipt_row = receipt_rows.get(grant.receipt_id.fingerprint())
            if (
                receipt_row is None
                or receipt_row[1] != "CONSUMED"
                or receipt_row[3] != grant.grant_id.fingerprint()
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if state == "ACTIVE":
                if version != 1 or link is not None:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
            elif state in {"CONSUMED", "REVOKED"}:
                if version != 2 or link is None:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
                finalized_at = _instant(link)
                if finalized_at < grant.issued_at or finalized_at >= grant.expires_at:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
            else:
                _fail(StepUpFailureCode.STORAGE_FAILURE)

        rows = connection.execute(
            "SELECT command_fingerprint,command_id,operation,payload_sha256,result_fingerprint,audit_sequence,record_sha256 "
            "FROM recorded_step_up_command ORDER BY audit_sequence"
        ).fetchall()
        previous = _GENESIS_DIGEST
        result_fingerprints: dict[StepUpOperation, set[str]] = {
            operation: set() for operation in StepUpOperation
        }
        operation_counts: dict[StepUpOperation, int] = {
            operation: 0 for operation in StepUpOperation
        }
        for expected_sequence, row in enumerate(rows, start=1):
            command_id, operation, _payload, result, sequence = cls._verified_command(
                tuple(row)
            )
            if sequence != expected_sequence:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            result_fingerprints[operation].add(result)
            operation_counts[operation] += 1
            command_result = cls._result(
                connection,
                command_id=command_id,
                operation=operation,
                result_fingerprint=result,
                audit_sequence=sequence,
            )
            if command_result.audit.previous_digest != previous:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            previous = command_result.audit.digest
        if result_fingerprints[StepUpOperation.BEGIN_CHALLENGE] != set(challenge_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if operation_counts[StepUpOperation.BEGIN_CHALLENGE] != len(challenge_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if result_fingerprints[StepUpOperation.VERIFY_CHALLENGE] != set(receipt_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if operation_counts[StepUpOperation.VERIFY_CHALLENGE] != len(receipt_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if result_fingerprints[StepUpOperation.ISSUE_GRANT] != set(grant_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if operation_counts[StepUpOperation.ISSUE_GRANT] != len(grant_rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM recorded_step_up_audit"
        ).fetchone()
        if audit_count != (len(rows),):
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    def audit_snapshot(self) -> tuple[StepUpAuditRecord, ...]:
        _require_development(self._environment)

        def operation(connection: sqlite3.Connection) -> tuple[StepUpAuditRecord, ...]:
            self._validate_all(connection)
            rows = connection.execute(
                "SELECT command_fingerprint,command_id,operation,payload_sha256,result_fingerprint,audit_sequence,record_sha256 "
                "FROM recorded_step_up_command ORDER BY audit_sequence"
            ).fetchall()
            return tuple(
                self._result(
                    connection,
                    command_id=command_id,
                    operation=operation,
                    result_fingerprint=result,
                    audit_sequence=sequence,
                ).audit
                for row in rows
                for command_id, operation, _payload, result, sequence in (
                    self._verified_command(tuple(row)),
                )
            )

        return self._read(operation)

    def __repr__(self) -> str:
        return (
            "RecordedSqliteStepUpRepository("
            "environment='ENV-DEV', path=<redacted>, state=<redacted>)"
        )


__all__ = [
    "RecordedSqliteStepUpRepository",
    "RecordedStepUpCommitFault",
    "RecordedSyntheticMfaVerifier",
]
