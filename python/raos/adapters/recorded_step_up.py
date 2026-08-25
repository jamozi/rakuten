"""Owner-private, tamper-evident recorded step-up storage for ST-0402.

This SQLite adapter is a deterministic ``ENV-DEV`` evidence surface, not a
Production database adapter. Only a database file created by this adapter may
be initialized. Lifecycle revisions, exact command intent/result records, and
audit events are append-only and fully revalidated at every transaction
boundary. File identity plus a process-lifetime command-prefix anchor detects
replacement and rollback while this process remains alive. No cross-process or
cross-restart trusted anchor is claimed.
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
    snapshot_bound_step_up_grant,
    snapshot_bound_step_up_grant_id,
    snapshot_step_up_audit,
    snapshot_step_up_authorization,
    snapshot_step_up_binding,
    snapshot_step_up_challenge,
    snapshot_step_up_challenge_id,
    snapshot_step_up_command_id,
    snapshot_step_up_command_result,
    snapshot_step_up_receipt_id,
    snapshot_step_up_verification,
)


_DATABASE_NAME: Final = "st0402-recorded-step-up.sqlite3"
_SCHEMA_VERSION: Final = 2
_APPLICATION_ID: Final = 1_380_400_202
_GENESIS: Final = "0" * 64
_MAX_TEXT: Final = 16 * 1024
_MAX_DOCUMENT_BYTES: Final = 64 * 1024
_T = TypeVar("_T")

_OPERATIONS: Final = frozenset(operation.value for operation in StepUpOperation)
_KINDS: Final = frozenset({"challenge", "receipt", "grant"})


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


_SCHEMA_TABLE_SQL: Final[tuple[tuple[str, str], ...]] = (
    (
        "recorded_step_up_metadata_v2",
        """CREATE TABLE recorded_step_up_metadata_v2 (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 2),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    command_count INTEGER NOT NULL CHECK (command_count >= 0),
    command_head_sha256 TEXT NOT NULL CHECK (length(command_head_sha256) = 64),
    audit_head_sha256 TEXT NOT NULL CHECK (length(audit_head_sha256) = 64)
) STRICT""",
    ),
    (
        "recorded_step_up_command_v2",
        """CREATE TABLE recorded_step_up_command_v2 (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    command_fingerprint TEXT NOT NULL UNIQUE CHECK (length(command_fingerprint) = 64),
    command_id TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL CHECK (operation IN ('BEGIN_CHALLENGE', 'VERIFY_CHALLENGE', 'ISSUE_GRANT', 'CONSUME_GRANT', 'REVOKE_GRANT')),
    entity_fingerprint TEXT NOT NULL CHECK (length(entity_fingerprint) = 64),
    intent_bytes BLOB NOT NULL,
    intent_sha256 TEXT NOT NULL CHECK (length(intent_sha256) = 64),
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    occurred_at TEXT NOT NULL,
    previous_command_sha256 TEXT NOT NULL CHECK (length(previous_command_sha256) = 64),
    command_sha256 TEXT NOT NULL UNIQUE CHECK (length(command_sha256) = 64)
) STRICT""",
    ),
    (
        "recorded_step_up_audit_v2",
        """CREATE TABLE recorded_step_up_audit_v2 (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    command_fingerprint TEXT NOT NULL UNIQUE CHECK (length(command_fingerprint) = 64),
    operation TEXT NOT NULL CHECK (operation IN ('BEGIN_CHALLENGE', 'VERIFY_CHALLENGE', 'ISSUE_GRANT', 'CONSUME_GRANT', 'REVOKE_GRANT')),
    outcome TEXT NOT NULL CHECK (outcome = 'SUCCEEDED'),
    binding_bytes BLOB NOT NULL,
    binding_sha256 TEXT NOT NULL CHECK (length(binding_sha256) = 64),
    session_fingerprint TEXT NOT NULL CHECK (length(session_fingerprint) = 64),
    issuer_fingerprint TEXT NOT NULL CHECK (length(issuer_fingerprint) = 64),
    subject_fingerprint TEXT NOT NULL CHECK (length(subject_fingerprint) = 64),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    previous_digest TEXT NOT NULL CHECK (length(previous_digest) = 64),
    digest TEXT NOT NULL UNIQUE CHECK (length(digest) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (sequence) REFERENCES recorded_step_up_command_v2(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    *tuple(
        (
            f"recorded_step_up_{kind}_revision_v2",
            f"""CREATE TABLE recorded_step_up_{kind}_revision_v2 (
    {kind}_fingerprint TEXT NOT NULL CHECK (length({kind}_fingerprint) = 64),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    {kind}_id TEXT NOT NULL,
    document_bytes BLOB NOT NULL,
    state TEXT NOT NULL,
    link TEXT,
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    PRIMARY KEY ({kind}_fingerprint, revision),
    FOREIGN KEY (command_sequence) REFERENCES recorded_step_up_command_v2(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
        )
        for kind in ("challenge", "receipt", "grant")
    ),
)

_SCHEMA_TRIGGER_SQL: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "recorded_step_up_metadata_v2_no_delete",
        "recorded_step_up_metadata_v2",
        "CREATE TRIGGER recorded_step_up_metadata_v2_no_delete BEFORE DELETE ON recorded_step_up_metadata_v2 BEGIN SELECT RAISE(ABORT, 'ST0402_METADATA_REQUIRED'); END",
    ),
    (
        "recorded_step_up_metadata_v2_guard_update",
        "recorded_step_up_metadata_v2",
        "CREATE TRIGGER recorded_step_up_metadata_v2_guard_update BEFORE UPDATE ON recorded_step_up_metadata_v2 WHEN NEW.singleton != OLD.singleton OR NEW.schema_version != OLD.schema_version OR NEW.schema_binding != OLD.schema_binding OR NEW.command_count != OLD.command_count + 1 OR NEW.command_head_sha256 = OLD.command_head_sha256 OR NEW.audit_head_sha256 = OLD.audit_head_sha256 BEGIN SELECT RAISE(ABORT, 'ST0402_METADATA_TRANSITION_INVALID'); END",
    ),
    *tuple(
        (
            f"{table}_no_update",
            table,
            f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'ST0402_APPEND_ONLY'); END",
        )
        for table, _statement in _SCHEMA_TABLE_SQL
        if table != "recorded_step_up_metadata_v2"
    ),
    *tuple(
        (
            f"{table}_no_delete",
            table,
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'ST0402_APPEND_ONLY'); END",
        )
        for table, _statement in _SCHEMA_TABLE_SQL
        if table != "recorded_step_up_metadata_v2"
    ),
)

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
    "recorded_step_up_command_v2": 3,
    "recorded_step_up_audit_v2": 3,
    "recorded_step_up_challenge_revision_v2": 3,
    "recorded_step_up_receipt_revision_v2": 3,
    "recorded_step_up_grant_revision_v2": 3,
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
    root_identity: tuple[int, int]
    count: int
    head: str
    lock: RLock


_PROCESS_ANCHORS: dict[tuple[str, int, int], _ProcessAnchor] = {}


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
    if not text.endswith("Z"):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    if _utc_text(parsed) != text:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
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
        _fail(StepUpFailureCode.STORAGE_FAILURE)


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        document[key] = value
    return document


def _reject_constant(_value: str) -> NoReturn:
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _canonical_mapping(value: object) -> dict[str, object]:
    if type(value) is not bytes or not value or len(value) > _MAX_DOCUMENT_BYTES:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    payload = bytes(value)
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate,
            parse_constant=_reject_constant,
        )
    except StepUpFailure:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    if type(parsed) is not dict:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    mapping = cast(dict[str, object], parsed)
    if _canonical_json_bytes(mapping) != payload:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return mapping


def _exact(document: object, keys: frozenset[str]) -> dict[str, object]:
    if type(document) is not dict:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    mapping = cast(dict[object, object], document)
    if frozenset(mapping) != keys or any(type(key) is not str for key in mapping):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    return cast(dict[str, object], mapping)


def _hash_material(value: object) -> object:
    if type(value) is bytes:
        return {"bytes_hex": value.hex()}
    if type(value) in {tuple, list}:
        return [_hash_material(item) for item in cast(Any, value)]
    if type(value) is dict:
        return {
            _text(key): _hash_material(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _record_hash(kind: str, values: tuple[object, ...]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes([kind, *(_hash_material(value) for value in values)])
    ).hexdigest()


def _binding_document(value: StepUpBinding) -> dict[str, str]:
    binding = snapshot_step_up_binding(value)
    return {
        "action": binding.action.value,
        "issuer": binding.issuer.reveal(),
        "resource_id": str(binding.resource.resource_id),
        "resource_type": binding.resource.resource_type.value,
        "session_id": binding.session_id.reveal(),
        "subject": binding.subject.reveal(),
    }


def _binding_from_document(document: object) -> StepUpBinding:
    value = _exact(
        document,
        frozenset(
            {
                "action",
                "issuer",
                "resource_id",
                "resource_type",
                "session_id",
                "subject",
            }
        ),
    )
    try:
        resource_text = _text(value["resource_id"], maximum=36)
        resource_id = UUID(resource_text)
        if str(resource_id) != resource_text:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        action = CriticalStepUpAction(_text(value["action"], maximum=64))
        resource_type = StepUpResourceType(_text(value["resource_type"], maximum=64))
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
    except StepUpFailure:
        raise
    except Exception:
        _fail(StepUpFailureCode.STORAGE_FAILURE)


def _challenge_document(value: StepUpChallenge) -> dict[str, object]:
    challenge = snapshot_step_up_challenge(value)
    return {
        "binding": _binding_document(challenge.binding),
        "challenge_id": challenge.challenge_id.reveal(),
        "created_at": _utc_text(challenge.created_at),
        "expires_at": _utc_text(challenge.expires_at),
    }


def _challenge_from_document(document: object) -> StepUpChallenge:
    value = _exact(
        document,
        frozenset({"binding", "challenge_id", "created_at", "expires_at"}),
    )
    return StepUpChallenge(
        challenge_id=StepUpChallengeId(_text(value["challenge_id"], maximum=43)),
        binding=_binding_from_document(value["binding"]),
        created_at=_instant(value["created_at"]),
        expires_at=_instant(value["expires_at"]),
    )


def _verification_document(value: StepUpVerificationReceipt) -> dict[str, object]:
    verification = snapshot_step_up_verification(value)
    return {
        "assurance_type": verification.assurance_type.value,
        "binding": _binding_document(verification.binding),
        "challenge_id": verification.challenge_id.reveal(),
        "expires_at": _utc_text(verification.expires_at),
        "receipt_id": verification.receipt_id.reveal(),
        "verified_at": _utc_text(verification.verified_at),
    }


def _verification_from_document(document: object) -> StepUpVerificationReceipt:
    value = _exact(
        document,
        frozenset(
            {
                "assurance_type",
                "binding",
                "challenge_id",
                "expires_at",
                "receipt_id",
                "verified_at",
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
    grant = snapshot_bound_step_up_grant(value)
    return {
        "binding": _binding_document(grant.binding),
        "expires_at": _utc_text(grant.expires_at),
        "grant_id": grant.grant_id.reveal(),
        "issued_at": _utc_text(grant.issued_at),
        "receipt_id": grant.receipt_id.reveal(),
    }


def _grant_from_document(document: object) -> BoundStepUpGrant:
    value = _exact(
        document,
        frozenset({"binding", "expires_at", "grant_id", "issued_at", "receipt_id"}),
    )
    return BoundStepUpGrant(
        grant_id=BoundStepUpGrantId(_text(value["grant_id"], maximum=43)),
        receipt_id=StepUpVerificationReceiptId(_text(value["receipt_id"], maximum=43)),
        binding=_binding_from_document(value["binding"]),
        issued_at=_instant(value["issued_at"]),
        expires_at=_instant(value["expires_at"]),
    )


LifecycleValue = StepUpChallenge | StepUpVerificationReceipt | BoundStepUpGrant


def _snapshot_lifecycle(kind: str, value: object) -> LifecycleValue:
    if kind == "challenge":
        return snapshot_step_up_challenge(value)
    if kind == "receipt":
        return snapshot_step_up_verification(value)
    if kind == "grant":
        return snapshot_bound_step_up_grant(value)
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _lifecycle_document(kind: str, value: LifecycleValue) -> dict[str, object]:
    if kind == "challenge" and type(value) is StepUpChallenge:
        return _challenge_document(value)
    if kind == "receipt" and type(value) is StepUpVerificationReceipt:
        return _verification_document(value)
    if kind == "grant" and type(value) is BoundStepUpGrant:
        return _grant_document(value)
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _lifecycle_from_document(kind: str, document: object) -> LifecycleValue:
    if kind == "challenge":
        return _challenge_from_document(document)
    if kind == "receipt":
        return _verification_from_document(document)
    if kind == "grant":
        return _grant_from_document(document)
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _lifecycle_identifier(kind: str, value: LifecycleValue) -> str:
    if kind == "challenge" and type(value) is StepUpChallenge:
        return value.challenge_id.reveal()
    if kind == "receipt" and type(value) is StepUpVerificationReceipt:
        return value.receipt_id.reveal()
    if kind == "grant" and type(value) is BoundStepUpGrant:
        return value.grant_id.reveal()
    _fail(StepUpFailureCode.STORAGE_FAILURE)


def _lifecycle_fingerprint(kind: str, value: LifecycleValue) -> str:
    if kind == "challenge" and type(value) is StepUpChallenge:
        return value.challenge_id.fingerprint()
    if kind == "receipt" and type(value) is StepUpVerificationReceipt:
        return value.receipt_id.fingerprint()
    if kind == "grant" and type(value) is BoundStepUpGrant:
        return value.grant_id.fingerprint()
    _fail(StepUpFailureCode.STORAGE_FAILURE)


@dataclass(frozen=True, slots=True)
class _LifecycleRevision:
    kind: str
    value: LifecycleValue
    state: str
    link: str | None
    revision: int
    command_sequence: int
    previous_record_sha256: str
    record_sha256: str


def _revision_values(
    *,
    kind: str,
    value: LifecycleValue,
    state: str,
    link: str | None,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> tuple[object, ...]:
    detached = _snapshot_lifecycle(kind, value)
    document_bytes = _canonical_json_bytes(_lifecycle_document(kind, detached))
    return (
        _lifecycle_fingerprint(kind, detached),
        revision,
        _lifecycle_identifier(kind, detached),
        document_bytes,
        state,
        link,
        command_sequence,
        previous_record_sha256,
    )


def _revision(
    *,
    kind: str,
    value: LifecycleValue,
    state: str,
    link: str | None,
    revision: int,
    command_sequence: int,
    previous_record_sha256: str,
) -> _LifecycleRevision:
    if kind not in _KINDS:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    detached = _snapshot_lifecycle(kind, value)
    values = _revision_values(
        kind=kind,
        value=detached,
        state=state,
        link=link,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
    )
    return _LifecycleRevision(
        kind=kind,
        value=detached,
        state=state,
        link=link,
        revision=revision,
        command_sequence=command_sequence,
        previous_record_sha256=previous_record_sha256,
        record_sha256=_record_hash(f"{kind.upper()}_REVISION", values),
    )


@dataclass(frozen=True, slots=True)
class _AuditRevision:
    sequence: int
    command_fingerprint: str
    operation: StepUpOperation
    binding: StepUpBinding
    occurred_at: datetime
    previous_digest: str
    digest: str
    record_sha256: str


def _audit_values(
    *,
    sequence: int,
    command_fingerprint: str,
    operation: StepUpOperation,
    binding: StepUpBinding,
    occurred_at: datetime,
    previous_digest: str,
) -> tuple[object, ...]:
    detached = snapshot_step_up_binding(binding)
    binding_bytes = _canonical_json_bytes(_binding_document(detached))
    return (
        sequence,
        command_fingerprint,
        operation.value,
        StepUpAuditOutcome.SUCCEEDED.value,
        binding_bytes,
        hashlib.sha256(binding_bytes).hexdigest(),
        detached.session_id.fingerprint(),
        hashlib.sha256(detached.issuer.reveal().encode("utf-8")).hexdigest(),
        hashlib.sha256(detached.subject.reveal().encode("utf-8")).hexdigest(),
        detached.action.value,
        detached.resource.resource_type.value,
        str(detached.resource.resource_id),
        _utc_text(occurred_at),
        previous_digest,
    )


def _audit_revision(
    *,
    sequence: int,
    command_id: StepUpCommandId,
    operation: StepUpOperation,
    binding: StepUpBinding,
    occurred_at: datetime,
    previous_digest: str,
) -> _AuditRevision:
    detached_command = snapshot_step_up_command_id(command_id)
    detached_binding = snapshot_step_up_binding(binding)
    values = _audit_values(
        sequence=sequence,
        command_fingerprint=detached_command.fingerprint(),
        operation=operation,
        binding=detached_binding,
        occurred_at=occurred_at,
        previous_digest=previous_digest,
    )
    digest = _record_hash("AUDIT_CHAIN", values)
    return _AuditRevision(
        sequence=sequence,
        command_fingerprint=detached_command.fingerprint(),
        operation=operation,
        binding=detached_binding,
        occurred_at=require_step_up_utc(occurred_at),
        previous_digest=previous_digest,
        digest=digest,
        record_sha256=_record_hash("AUDIT_RECORD", (*values, digest)),
    )


@dataclass(frozen=True, slots=True)
class _CommandRevision:
    sequence: int
    command_id: StepUpCommandId
    operation: StepUpOperation
    entity_fingerprint: str
    intent: dict[str, object]
    result: dict[str, object]
    occurred_at: datetime
    previous_command_sha256: str
    command_sha256: str


def _command_hash(
    *,
    sequence: int,
    command_fingerprint: str,
    operation: StepUpOperation,
    entity_fingerprint: str,
    intent_sha256: str,
    result_sha256: str,
    occurred_at: datetime,
    previous_command_sha256: str,
) -> str:
    return _record_hash(
        "COMMAND",
        (
            sequence,
            command_fingerprint,
            operation.value,
            entity_fingerprint,
            intent_sha256,
            result_sha256,
            _utc_text(occurred_at),
            previous_command_sha256,
        ),
    )


def _command_revision(
    *,
    sequence: int,
    command_id: StepUpCommandId,
    operation: StepUpOperation,
    entity_fingerprint: str,
    intent: dict[str, object],
    result: dict[str, object],
    occurred_at: datetime,
    previous_command_sha256: str,
) -> _CommandRevision:
    detached_id = snapshot_step_up_command_id(command_id)
    entity = _sha(entity_fingerprint)
    canonical_intent = _canonical_mapping(_canonical_json_bytes(intent))
    canonical_result = _canonical_mapping(_canonical_json_bytes(result))
    intent_sha = hashlib.sha256(_canonical_json_bytes(canonical_intent)).hexdigest()
    result_sha = hashlib.sha256(_canonical_json_bytes(canonical_result)).hexdigest()
    return _CommandRevision(
        sequence=sequence,
        command_id=detached_id,
        operation=operation,
        entity_fingerprint=entity,
        intent=canonical_intent,
        result=canonical_result,
        occurred_at=require_step_up_utc(occurred_at),
        previous_command_sha256=previous_command_sha256,
        command_sha256=_command_hash(
            sequence=sequence,
            command_fingerprint=detached_id.fingerprint(),
            operation=operation,
            entity_fingerprint=entity,
            intent_sha256=intent_sha,
            result_sha256=result_sha,
            occurred_at=occurred_at,
            previous_command_sha256=previous_command_sha256,
        ),
    )


class RecordedStepUpCommitFault(str, Enum):
    """Closed one-shot local crash points."""

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

    @property
    def external_action_count(self) -> int:
        return 0

    def verify(
        self,
        *,
        challenge: StepUpChallenge,
        receipt_id: StepUpVerificationReceiptId,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpVerificationReceipt:
        _require_development(self._environment)
        try:
            received_challenge = snapshot_step_up_challenge(challenge)
            received_receipt = snapshot_step_up_receipt_id(receipt_id)
        except StepUpFailure:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        observed_at = require_step_up_utc(now)
        expiry = require_step_up_utc(expires_at)
        if (
            observed_at < received_challenge.created_at
            or observed_at >= received_challenge.expires_at
            or not observed_at < expiry <= received_challenge.expires_at
        ):
            _fail(StepUpFailureCode.CHALLENGE_EXPIRED)
        return snapshot_step_up_verification(
            StepUpVerificationReceipt(
                receipt_id=received_receipt,
                challenge_id=received_challenge.challenge_id,
                binding=received_challenge.binding,
                assurance_type=StepUpAssuranceType.MULTI_FACTOR,
                verified_at=observed_at,
                expires_at=expiry,
            )
        )

    def __repr__(self) -> str:
        return "RecordedSyntheticMfaVerifier(environment='ENV-DEV', factor=<absent>)"


RevisionHistories = dict[str, dict[str, tuple[_LifecycleRevision, ...]]]


def _same_lifecycle(first: _LifecycleRevision, second: _LifecycleRevision) -> bool:
    return first.kind == second.kind and first.value == second.value


def _derive_command_material(
    *,
    operation: StepUpOperation,
    rows: dict[str, tuple[_LifecycleRevision, ...]],
    histories: RevisionHistories,
    audit_digest: str,
) -> tuple[str, StepUpBinding, datetime, dict[str, object], dict[str, object]]:
    """Derive exact command intent/result only from durable lifecycle rows."""

    audit_sha = _sha(audit_digest)
    challenge_rows = rows.get("challenge", ())
    receipt_rows = rows.get("receipt", ())
    grant_rows = rows.get("grant", ())
    if operation is StepUpOperation.BEGIN_CHALLENGE:
        if len(challenge_rows) != 1 or receipt_rows or grant_rows:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        challenge_row = challenge_rows[0]
        if (
            challenge_row.revision != 1
            or challenge_row.state != "PENDING"
            or challenge_row.link is not None
            or type(challenge_row.value) is not StepUpChallenge
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        challenge = challenge_row.value
        entity = challenge.challenge_id.fingerprint()
        return (
            entity,
            challenge.binding,
            challenge.created_at,
            {
                "challenge": _challenge_document(challenge),
                "operation": operation.value,
            },
            {
                "audit_digest": audit_sha,
                "challenge_fingerprint": entity,
                "challenge_record_sha256": challenge_row.record_sha256,
                "operation": operation.value,
            },
        )
    if operation is StepUpOperation.VERIFY_CHALLENGE:
        if len(challenge_rows) != 1 or len(receipt_rows) != 1 or grant_rows:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        challenge_row = challenge_rows[0]
        receipt_row = receipt_rows[0]
        if (
            challenge_row.revision != 2
            or challenge_row.state != "VERIFIED"
            or type(challenge_row.value) is not StepUpChallenge
            or receipt_row.revision != 1
            or receipt_row.state != "AVAILABLE"
            or receipt_row.link is not None
            or type(receipt_row.value) is not StepUpVerificationReceipt
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        challenge = challenge_row.value
        verification = receipt_row.value
        challenge_history = histories["challenge"].get(
            challenge.challenge_id.fingerprint(), ()
        )
        if len(challenge_history) < 2:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        previous = challenge_history[-2]
        if (
            previous.record_sha256 != challenge_row.previous_record_sha256
            or previous.state != "PENDING"
            or previous.link is not None
            or not _same_lifecycle(previous, challenge_row)
            or challenge_row.link != verification.receipt_id.fingerprint()
            or verification.challenge_id != challenge.challenge_id
            or verification.binding != challenge.binding
            or verification.verified_at < challenge.created_at
            or verification.verified_at >= challenge.expires_at
            or verification.expires_at > challenge.expires_at
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        entity = verification.receipt_id.fingerprint()
        return (
            entity,
            verification.binding,
            verification.verified_at,
            {
                "operation": operation.value,
                "verification": _verification_document(verification),
            },
            {
                "audit_digest": audit_sha,
                "challenge_record_sha256": challenge_row.record_sha256,
                "operation": operation.value,
                "receipt_fingerprint": entity,
                "receipt_record_sha256": receipt_row.record_sha256,
            },
        )
    if operation is StepUpOperation.ISSUE_GRANT:
        if challenge_rows or len(receipt_rows) != 1 or len(grant_rows) != 1:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        receipt_row = receipt_rows[0]
        grant_row = grant_rows[0]
        if (
            receipt_row.revision != 2
            or receipt_row.state != "CONSUMED"
            or type(receipt_row.value) is not StepUpVerificationReceipt
            or grant_row.revision != 1
            or grant_row.state != "ACTIVE"
            or grant_row.link is not None
            or type(grant_row.value) is not BoundStepUpGrant
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        verification = receipt_row.value
        grant = grant_row.value
        receipt_history = histories["receipt"].get(
            verification.receipt_id.fingerprint(), ()
        )
        if len(receipt_history) < 2:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        previous = receipt_history[-2]
        if (
            previous.record_sha256 != receipt_row.previous_record_sha256
            or previous.state != "AVAILABLE"
            or previous.link is not None
            or not _same_lifecycle(previous, receipt_row)
            or receipt_row.link != grant.grant_id.fingerprint()
            or grant.receipt_id != verification.receipt_id
            or grant.binding != verification.binding
            or grant.issued_at < verification.verified_at
            or grant.issued_at >= verification.expires_at
            or grant.expires_at > verification.expires_at
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        entity = grant.grant_id.fingerprint()
        return (
            entity,
            grant.binding,
            grant.issued_at,
            {
                "grant": _grant_document(grant),
                "operation": operation.value,
            },
            {
                "audit_digest": audit_sha,
                "grant_fingerprint": entity,
                "grant_record_sha256": grant_row.record_sha256,
                "operation": operation.value,
                "receipt_record_sha256": receipt_row.record_sha256,
            },
        )
    if (
        operation not in {StepUpOperation.CONSUME_GRANT, StepUpOperation.REVOKE_GRANT}
        or challenge_rows
        or receipt_rows
        or len(grant_rows) != 1
    ):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    grant_row = grant_rows[0]
    expected_state = (
        "CONSUMED" if operation is StepUpOperation.CONSUME_GRANT else "REVOKED"
    )
    if (
        grant_row.revision != 2
        or grant_row.state != expected_state
        or grant_row.link is None
        or type(grant_row.value) is not BoundStepUpGrant
    ):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    grant = grant_row.value
    history = histories["grant"].get(grant.grant_id.fingerprint(), ())
    if len(history) < 2:
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    previous = history[-2]
    finalized_at = _instant(grant_row.link)
    if (
        previous.record_sha256 != grant_row.previous_record_sha256
        or previous.state != "ACTIVE"
        or previous.link is not None
        or not _same_lifecycle(previous, grant_row)
        or finalized_at < grant.issued_at
        or finalized_at >= grant.expires_at
    ):
        _fail(StepUpFailureCode.STORAGE_FAILURE)
    entity = grant.grant_id.fingerprint()
    return (
        entity,
        grant.binding,
        finalized_at,
        {
            "expected_binding": _binding_document(grant.binding),
            "finalized_at": _utc_text(finalized_at),
            "grant_fingerprint": entity,
            "operation": operation.value,
        },
        {
            "audit_digest": audit_sha,
            "final_state": expected_state,
            "grant_fingerprint": entity,
            "grant_record_sha256": grant_row.record_sha256,
            "operation": operation.value,
        },
    )


@final
class RecordedSqliteStepUpRepository:
    """Exact-schema, append-only, process-monotonic local repository."""

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
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        root = Path(os.path.abspath(value))
        current = Path(root.anchor)
        try:
            for component in root.parts[1:]:
                current /= component
                metadata = current.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(StepUpFailureCode.STORAGE_FAILURE)
            metadata = root.lstat()
        except StepUpFailure:
            raise
        except OSError:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
                _fail(StepUpFailureCode.STORAGE_FAILURE)
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
            metadata = os.fstat(database_descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return created, (metadata.st_dev, metadata.st_ino)
        except StepUpFailure:
            raise
        except OSError:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        _created, identity = self._open_database_file(allow_create=False)
        if identity != self._database_identity:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
            if connection.execute("PRAGMA journal_mode = DELETE").fetchone() != (
                "delete",
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            self._validate_database_identity()
            if verify:
                self._verified_state(connection, check_process=True)
            return connection
        except StepUpFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error, OSError:
            if connection is not None:
                self._close_safely(connection)
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() != (
                0,
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            for _name, statement in _SCHEMA_TABLE_SQL:
                connection.execute(statement)
            for _name, _table, statement in _SCHEMA_TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO recorded_step_up_metadata_v2 VALUES (1, ?, ?, 0, ?, ?)",
                (_SCHEMA_VERSION, _SCHEMA_BINDING, _GENESIS, _GENESIS),
            )
            self._verify_schema(connection)
            self._verify_integrity(connection)
            connection.commit()
            self._validate_database_identity()
        except StepUpFailure:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _master_record(row: object) -> tuple[str, str, str, str | None]:
        if type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = cast(tuple[object, ...], row)
        if len(values) != 4:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        kind, name, table, statement = values
        if (
            type(kind) is not str
            or type(name) is not str
            or type(table) is not str
            or (statement is not None and type(statement) is not str)
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return kind, name, table, statement

    def _verify_schema(self, connection: sqlite3.Connection) -> None:
        if (
            connection.execute("PRAGMA application_id").fetchone() != (_APPLICATION_ID,)
            or connection.execute("PRAGMA user_version").fetchone()
            != (_SCHEMA_VERSION,)
            or connection.execute("PRAGMA foreign_keys").fetchone() != (1,)
            or connection.execute("PRAGMA trusted_schema").fetchone() != (0,)
            or connection.execute("PRAGMA synchronous").fetchone() != (2,)
            or connection.execute("PRAGMA secure_delete").fetchone() != (1,)
            or connection.execute("PRAGMA journal_mode").fetchone() != ("delete",)
            or connection.execute("PRAGMA busy_timeout").fetchone() != (5000,)
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
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
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        table_state = {
            str(row[1]): (int(row[4]), int(row[5]))
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("recorded_step_up_")
        }
        if table_state != {name: (0, 1) for name, _statement in _SCHEMA_TABLE_SQL}:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if (
            connection.execute("PRAGMA integrity_check").fetchone() != ("ok",)
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        metadata = connection.execute(
            "SELECT singleton, schema_version, schema_binding, command_count, "
            "command_head_sha256, audit_head_sha256 "
            "FROM recorded_step_up_metadata_v2"
        ).fetchall()
        if len(metadata) != 1 or tuple(metadata[0])[:3] != (
            1,
            _SCHEMA_VERSION,
            _SCHEMA_BINDING,
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _revision_from_row(kind: str, row: object) -> _LifecycleRevision:
        if kind not in _KINDS or type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = cast(tuple[object, ...], row)
        if len(values) != 9:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        try:
            fingerprint = _sha(values[0])
            revision = values[1]
            identifier = _text(values[2], maximum=43)
            document_bytes = values[3]
            state = _text(values[4], maximum=16)
            link = _optional_text(values[5])
            command_sequence = values[6]
            previous = _sha(values[7])
            stored_record = _sha(values[8])
            if (
                type(revision) is not int
                or revision < 1
                or type(command_sequence) is not int
                or command_sequence < 1
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            document = _canonical_mapping(document_bytes)
            value = _lifecycle_from_document(kind, document)
            if (
                _lifecycle_identifier(kind, value) != identifier
                or _lifecycle_fingerprint(kind, value) != fingerprint
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            canonical_values = _revision_values(
                kind=kind,
                value=value,
                state=state,
                link=link,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            )
            if tuple(values[:8]) != canonical_values:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            record = _revision(
                kind=kind,
                value=value,
                state=state,
                link=link,
                revision=revision,
                command_sequence=command_sequence,
                previous_record_sha256=previous,
            )
            if record.record_sha256 != stored_record:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return record
        except StepUpFailure:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except Exception:
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _command_from_row(row: object) -> _CommandRevision:
        if type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = cast(tuple[object, ...], row)
        if len(values) != 12:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        try:
            sequence = values[0]
            if type(sequence) is not int or sequence < 1:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            command_fingerprint = _sha(values[1])
            command_id = StepUpCommandId(_text(values[2], maximum=43))
            if command_id.fingerprint() != command_fingerprint:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            try:
                operation = StepUpOperation(_text(values[3], maximum=32))
            except ValueError:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            entity = _sha(values[4])
            intent = _canonical_mapping(values[5])
            intent_bytes = cast(bytes, values[5])
            intent_sha = _sha(values[6])
            result = _canonical_mapping(values[7])
            result_bytes = cast(bytes, values[7])
            result_sha = _sha(values[8])
            occurred_at = _instant(values[9])
            previous = _sha(values[10])
            stored_hash = _sha(values[11])
            if (
                hashlib.sha256(intent_bytes).hexdigest() != intent_sha
                or hashlib.sha256(result_bytes).hexdigest() != result_sha
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            expected_hash = _command_hash(
                sequence=sequence,
                command_fingerprint=command_fingerprint,
                operation=operation,
                entity_fingerprint=entity,
                intent_sha256=intent_sha,
                result_sha256=result_sha,
                occurred_at=occurred_at,
                previous_command_sha256=previous,
            )
            if expected_hash != stored_hash:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return _CommandRevision(
                sequence=sequence,
                command_id=command_id,
                operation=operation,
                entity_fingerprint=entity,
                intent=intent,
                result=result,
                occurred_at=occurred_at,
                previous_command_sha256=previous,
                command_sha256=stored_hash,
            )
        except StepUpFailure:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except Exception:
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _audit_from_row(row: object) -> _AuditRevision:
        if type(row) is not tuple:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        values = cast(tuple[object, ...], row)
        if len(values) != 16:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        try:
            sequence = values[0]
            if type(sequence) is not int or sequence < 1:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            command_fingerprint = _sha(values[1])
            try:
                operation = StepUpOperation(_text(values[2], maximum=32))
            except ValueError:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if values[3] != StepUpAuditOutcome.SUCCEEDED.value:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            binding_bytes = values[4]
            binding = _binding_from_document(_canonical_mapping(binding_bytes))
            binding_sha = _sha(values[5])
            if hashlib.sha256(cast(bytes, binding_bytes)).hexdigest() != binding_sha:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            occurred_at = _instant(values[12])
            previous = _sha(values[13])
            digest = _sha(values[14])
            record_sha = _sha(values[15])
            expected_values = _audit_values(
                sequence=sequence,
                command_fingerprint=command_fingerprint,
                operation=operation,
                binding=binding,
                occurred_at=occurred_at,
                previous_digest=previous,
            )
            if tuple(values[:14]) != expected_values:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if (
                _record_hash("AUDIT_CHAIN", expected_values) != digest
                or _record_hash("AUDIT_RECORD", (*expected_values, digest))
                != record_sha
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return _AuditRevision(
                sequence=sequence,
                command_fingerprint=command_fingerprint,
                operation=operation,
                binding=binding,
                occurred_at=occurred_at,
                previous_digest=previous,
                digest=digest,
                record_sha256=record_sha,
            )
        except StepUpFailure:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        except Exception:
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _command_rows(connection: sqlite3.Connection) -> tuple[_CommandRevision, ...]:
        rows = connection.execute(
            "SELECT sequence, command_fingerprint, command_id, operation, "
            "entity_fingerprint, intent_bytes, intent_sha256, result_bytes, "
            "result_sha256, occurred_at, previous_command_sha256, command_sha256 "
            "FROM recorded_step_up_command_v2 ORDER BY sequence"
        ).fetchall()
        return tuple(
            RecordedSqliteStepUpRepository._command_from_row(tuple(row)) for row in rows
        )

    @staticmethod
    def _audit_rows(connection: sqlite3.Connection) -> tuple[_AuditRevision, ...]:
        rows = connection.execute(
            "SELECT sequence, command_fingerprint, operation, outcome, "
            "binding_bytes, binding_sha256, session_fingerprint, "
            "issuer_fingerprint, subject_fingerprint, action, resource_type, "
            "resource_id, occurred_at, previous_digest, digest, record_sha256 "
            "FROM recorded_step_up_audit_v2 ORDER BY sequence"
        ).fetchall()
        return tuple(
            RecordedSqliteStepUpRepository._audit_from_row(tuple(row)) for row in rows
        )

    @staticmethod
    def _revision_rows(
        connection: sqlite3.Connection, kind: str
    ) -> tuple[_LifecycleRevision, ...]:
        if kind not in _KINDS:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        rows = connection.execute(
            f"SELECT {kind}_fingerprint, revision, {kind}_id, document_bytes, "
            f"state, link, command_sequence, previous_record_sha256, "
            f"record_sha256 FROM recorded_step_up_{kind}_revision_v2 "
            f"ORDER BY {kind}_fingerprint, revision"
        ).fetchall()
        return tuple(
            RecordedSqliteStepUpRepository._revision_from_row(kind, tuple(row))
            for row in rows
        )

    @classmethod
    def _histories(cls, connection: sqlite3.Connection) -> RevisionHistories:
        histories: RevisionHistories = {kind: {} for kind in _KINDS}
        for kind in _KINDS:
            for row in cls._revision_rows(connection, kind):
                fingerprint = _lifecycle_fingerprint(kind, row.value)
                histories[kind][fingerprint] = (
                    *histories[kind].get(fingerprint, ()),
                    row,
                )
        return histories

    @staticmethod
    def _validate_histories(histories: RevisionHistories) -> None:
        for kind, grouped in histories.items():
            for fingerprint, history in grouped.items():
                previous = _GENESIS
                for expected_revision, row in enumerate(history, start=1):
                    if (
                        row.kind != kind
                        or row.revision != expected_revision
                        or row.previous_record_sha256 != previous
                        or _lifecycle_fingerprint(kind, row.value) != fingerprint
                    ):
                        _fail(StepUpFailureCode.STORAGE_FAILURE)
                    previous = row.record_sha256
                if len(history) not in {1, 2}:
                    _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _validate_relationships(histories: RevisionHistories) -> None:
        challenges = histories["challenge"]
        receipts = histories["receipt"]
        grants = histories["grant"]
        for history in challenges.values():
            first = history[0]
            if (
                first.state != "PENDING"
                or first.link is not None
                or type(first.value) is not StepUpChallenge
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if len(history) == 1:
                continue
            current = history[1]
            if (
                current.state != "VERIFIED"
                or current.link is None
                or not _same_lifecycle(first, current)
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            receipt_history = receipts.get(_sha(current.link))
            if (
                receipt_history is None
                or type(receipt_history[0].value) is not StepUpVerificationReceipt
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            challenge = first.value
            receipt = receipt_history[0].value
            if (
                receipt.challenge_id != challenge.challenge_id
                or receipt.binding != challenge.binding
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
        for history in receipts.values():
            first = history[0]
            if (
                first.state != "AVAILABLE"
                or first.link is not None
                or type(first.value) is not StepUpVerificationReceipt
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            receipt = first.value
            challenge_history = challenges.get(receipt.challenge_id.fingerprint())
            if (
                challenge_history is None
                or len(challenge_history) != 2
                or challenge_history[1].link != receipt.receipt_id.fingerprint()
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if len(history) == 1:
                continue
            current = history[1]
            if (
                current.state != "CONSUMED"
                or current.link is None
                or not _same_lifecycle(first, current)
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant_history = grants.get(_sha(current.link))
            if (
                grant_history is None
                or type(grant_history[0].value) is not BoundStepUpGrant
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant = grant_history[0].value
            if (
                grant.receipt_id != receipt.receipt_id
                or grant.binding != receipt.binding
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
        for history in grants.values():
            first = history[0]
            if (
                first.state != "ACTIVE"
                or first.link is not None
                or type(first.value) is not BoundStepUpGrant
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant = first.value
            receipt_history = receipts.get(grant.receipt_id.fingerprint())
            if (
                receipt_history is None
                or len(receipt_history) != 2
                or receipt_history[1].link != grant.grant_id.fingerprint()
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            if len(history) == 1:
                continue
            current = history[1]
            if (
                current.state not in {"CONSUMED", "REVOKED"}
                or current.link is None
                or not _same_lifecycle(first, current)
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            finalized_at = _instant(current.link)
            if finalized_at < grant.issued_at or finalized_at >= grant.expires_at:
                _fail(StepUpFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _metadata_state(connection: sqlite3.Connection) -> tuple[int, str, str]:
        rows = connection.execute(
            "SELECT command_count, command_head_sha256, audit_head_sha256 "
            "FROM recorded_step_up_metadata_v2 WHERE singleton=1"
        ).fetchall()
        if len(rows) != 1:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        count, command_head, audit_head = tuple(rows[0])
        if type(count) is not int or count < 0:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return count, _sha(command_head), _sha(audit_head)

    @classmethod
    def _verify_integrity(cls, connection: sqlite3.Connection) -> tuple[str, int]:
        commands = cls._command_rows(connection)
        audits = cls._audit_rows(connection)
        histories = cls._histories(connection)
        cls._validate_histories(histories)
        cls._validate_relationships(histories)
        count, command_head, audit_head = cls._metadata_state(connection)
        if len(commands) != count or len(audits) != count:
            _fail(StepUpFailureCode.STORAGE_FAILURE)

        rows_by_sequence: dict[int, dict[str, tuple[_LifecycleRevision, ...]]] = {}
        for kind, grouped in histories.items():
            for history in grouped.values():
                for row in history:
                    if row.command_sequence > count:
                        _fail(StepUpFailureCode.STORAGE_FAILURE)
                    sequence_rows = rows_by_sequence.setdefault(
                        row.command_sequence, {}
                    )
                    sequence_rows[kind] = (
                        *sequence_rows.get(kind, ()),
                        row,
                    )

        previous_command = _GENESIS
        previous_audit = _GENESIS
        for expected_sequence, (command, audit) in enumerate(
            zip(commands, audits, strict=True), start=1
        ):
            if (
                command.sequence != expected_sequence
                or audit.sequence != expected_sequence
                or command.previous_command_sha256 != previous_command
                or audit.previous_digest != previous_audit
                or command.command_id.fingerprint() != audit.command_fingerprint
                or command.operation is not audit.operation
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            rows = rows_by_sequence.get(expected_sequence)
            if rows is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            entity, binding, occurred_at, intent, result = _derive_command_material(
                operation=command.operation,
                rows=rows,
                histories=histories,
                audit_digest=audit.digest,
            )
            if (
                command.entity_fingerprint != entity
                or command.intent != intent
                or command.result != result
                or command.occurred_at != occurred_at
                or audit.binding != binding
                or audit.occurred_at != occurred_at
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            previous_command = command.command_sha256
            previous_audit = audit.digest

        if frozenset(rows_by_sequence) != frozenset(range(1, count + 1)):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if command_head != previous_command or audit_head != previous_audit:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return command_head, count

    def _verified_state(
        self, connection: sqlite3.Connection, *, check_process: bool
    ) -> tuple[str, int]:
        self._validate_database_identity()
        self._verify_schema(connection)
        head, count = self._verify_integrity(connection)
        if check_process:
            self._require_process_monotonic(connection, head=head, count=count)
        return head, count

    def _anchor_key(self) -> tuple[str, int, int]:
        return (
            str(self._database_path),
            self._database_identity[0],
            self._database_identity[1],
        )

    def _bind_process_anchor(
        self, connection: sqlite3.Connection, *, head: str, count: int
    ) -> None:
        key = self._anchor_key()
        with _PROCESS_REGISTRY_LOCK:
            if any(
                registered[0] == key[0] and registered != key
                for registered in _PROCESS_ANCHORS
            ):
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            anchor = _PROCESS_ANCHORS.get(key)
            if anchor is None:
                anchor = _ProcessAnchor(
                    database_identity=self._database_identity,
                    root_identity=self._root_identity,
                    count=count,
                    head=head,
                    lock=RLock(),
                )
                _PROCESS_ANCHORS[key] = anchor
            self._process_anchor = anchor
        with anchor.lock:
            self._require_process_monotonic(connection, head=head, count=count)
            if count > anchor.count:
                anchor.count = count
                anchor.head = head

    def _require_process_monotonic(
        self, connection: sqlite3.Connection, *, head: str, count: int
    ) -> None:
        anchor = self._process_anchor
        if anchor is None:
            return
        if (
            anchor.database_identity != self._database_identity
            or anchor.root_identity != self._root_identity
            or count < anchor.count
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if anchor.count == 0:
            anchored_head = _GENESIS
        else:
            row = connection.execute(
                "SELECT command_sha256 FROM recorded_step_up_command_v2 "
                "WHERE sequence=?",
                (anchor.count,),
            ).fetchone()
            if row is None or len(row) != 1:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            anchored_head = _sha(row[0])
        if anchored_head != anchor.head or (
            count == anchor.count and head != anchor.head
        ):
            _fail(StepUpFailureCode.STORAGE_FAILURE)

    def _pin_process_state(self, *, head: str, count: int) -> None:
        anchor = self._process_anchor
        if anchor is None or count < anchor.count:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        if count == anchor.count and head != anchor.head:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        anchor.count = count
        anchor.head = head

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error:
            pass

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _inject_fault(self, point: RecordedStepUpCommitFault) -> None:
        with self._fault_lock:
            if self._fault_once_at is point:
                self._fault_once_at = None
                raise _InjectedCrash(point) from None

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=False)
            commit_attempted = False
            committed = False
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                head, count = self._verified_state(connection, check_process=True)
                self._inject_fault(RecordedStepUpCommitFault.BEFORE_COMMIT)
                commit_attempted = True
                connection.commit()
                committed = True
                self._pin_process_state(head=head, count=count)
                self._inject_fault(RecordedStepUpCommitFault.AFTER_COMMIT)
                return result
            except _InjectedCrash as error:
                if not committed:
                    self._rollback(connection)
                if error.point is RecordedStepUpCommitFault.AFTER_COMMIT:
                    _fail(StepUpFailureCode.STORAGE_COMMIT_UNKNOWN)
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            except StepUpFailure:
                if not committed:
                    self._rollback(connection)
                raise
            except sqlite3.Error:
                transaction_survived = connection.in_transaction
                if transaction_survived:
                    self._rollback(connection)
                if commit_attempted and not transaction_survived:
                    try:
                        recovered_head, recovered_count = self._verified_state(
                            connection, check_process=False
                        )
                        self._pin_process_state(
                            head=recovered_head, count=recovered_count
                        )
                    except Exception:
                        pass
                    _fail(StepUpFailureCode.STORAGE_COMMIT_UNKNOWN)
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            except Exception:
                if not committed:
                    self._rollback(connection)
                _fail(
                    StepUpFailureCode.STORAGE_COMMIT_UNKNOWN
                    if committed
                    else StepUpFailureCode.STORAGE_FAILURE
                )
            finally:
                self._close_safely(connection)

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=False)
            try:
                connection.execute("BEGIN")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                self._verified_state(connection, check_process=True)
                connection.commit()
                return result
            except StepUpFailure:
                self._rollback(connection)
                raise
            except Exception:
                self._rollback(connection)
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            finally:
                self._close_safely(connection)

    @staticmethod
    def _insert_revision(
        connection: sqlite3.Connection, row: _LifecycleRevision
    ) -> None:
        values = _revision_values(
            kind=row.kind,
            value=row.value,
            state=row.state,
            link=row.link,
            revision=row.revision,
            command_sequence=row.command_sequence,
            previous_record_sha256=row.previous_record_sha256,
        )
        connection.execute(
            f"INSERT INTO recorded_step_up_{row.kind}_revision_v2 VALUES "
            "(?,?,?,?,?,?,?,?,?)",
            (*values, row.record_sha256),
        )

    @staticmethod
    def _insert_command(
        connection: sqlite3.Connection, command: _CommandRevision
    ) -> None:
        intent_bytes = _canonical_json_bytes(command.intent)
        result_bytes = _canonical_json_bytes(command.result)
        connection.execute(
            "INSERT INTO recorded_step_up_command_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                command.sequence,
                command.command_id.fingerprint(),
                command.command_id.reveal(),
                command.operation.value,
                command.entity_fingerprint,
                intent_bytes,
                hashlib.sha256(intent_bytes).hexdigest(),
                result_bytes,
                hashlib.sha256(result_bytes).hexdigest(),
                _utc_text(command.occurred_at),
                command.previous_command_sha256,
                command.command_sha256,
            ),
        )

    @staticmethod
    def _insert_audit(connection: sqlite3.Connection, audit: _AuditRevision) -> None:
        values = _audit_values(
            sequence=audit.sequence,
            command_fingerprint=audit.command_fingerprint,
            operation=audit.operation,
            binding=audit.binding,
            occurred_at=audit.occurred_at,
            previous_digest=audit.previous_digest,
        )
        connection.execute(
            "INSERT INTO recorded_step_up_audit_v2 VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*values, audit.digest, audit.record_sha256),
        )

    @staticmethod
    def _audit_record(audit: _AuditRevision) -> StepUpAuditRecord:
        return snapshot_step_up_audit(
            StepUpAuditRecord(
                sequence=audit.sequence,
                command_fingerprint=audit.command_fingerprint,
                operation=audit.operation,
                outcome=StepUpAuditOutcome.SUCCEEDED,
                binding=audit.binding,
                occurred_at=audit.occurred_at,
                previous_digest=audit.previous_digest,
                digest=audit.digest,
            )
        )

    @classmethod
    def _command_by_id(
        cls, connection: sqlite3.Connection, command_id: StepUpCommandId
    ) -> _CommandRevision | None:
        row = connection.execute(
            "SELECT sequence, command_fingerprint, command_id, operation, "
            "entity_fingerprint, intent_bytes, intent_sha256, result_bytes, "
            "result_sha256, occurred_at, previous_command_sha256, command_sha256 "
            "FROM recorded_step_up_command_v2 WHERE command_fingerprint=?",
            (command_id.fingerprint(),),
        ).fetchone()
        return None if row is None else cls._command_from_row(tuple(row))

    @classmethod
    def _result_for_command(
        cls, connection: sqlite3.Connection, command: _CommandRevision
    ) -> StepUpCommandResult:
        audits = cls._audit_rows(connection)
        if command.sequence > len(audits):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        audit = audits[command.sequence - 1]
        histories = cls._histories(connection)
        challenge: StepUpChallenge | None = None
        verification: StepUpVerificationReceipt | None = None
        grant: BoundStepUpGrant | None = None
        authorization: StepUpAuthorizationReceipt | None = None
        if command.operation is StepUpOperation.BEGIN_CHALLENGE:
            history = histories["challenge"].get(command.entity_fingerprint)
            if history is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            challenge = snapshot_step_up_challenge(history[0].value)
        elif command.operation is StepUpOperation.VERIFY_CHALLENGE:
            history = histories["receipt"].get(command.entity_fingerprint)
            if history is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            verification = snapshot_step_up_verification(history[0].value)
        elif command.operation in {
            StepUpOperation.ISSUE_GRANT,
            StepUpOperation.REVOKE_GRANT,
        }:
            history = histories["grant"].get(command.entity_fingerprint)
            if history is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            grant = snapshot_bound_step_up_grant(history[0].value)
        else:
            history = histories["grant"].get(command.entity_fingerprint)
            if history is None or len(history) != 2 or history[1].link is None:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            stored_grant = snapshot_bound_step_up_grant(history[0].value)
            authorization = snapshot_step_up_authorization(
                StepUpAuthorizationReceipt(
                    grant_id=stored_grant.grant_id,
                    binding=stored_grant.binding,
                    authorized_at=_instant(history[1].link),
                )
            )
        return snapshot_step_up_command_result(
            StepUpCommandResult(
                command_id=command.command_id,
                operation=command.operation,
                audit=cls._audit_record(audit),
                challenge=challenge,
                verification=verification,
                grant=grant,
                authorization=authorization,
            )
        )

    @classmethod
    def _existing(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        intent: dict[str, object],
    ) -> StepUpCommandResult | None:
        command = cls._command_by_id(connection, command_id)
        if command is None:
            return None
        canonical_intent = _canonical_mapping(_canonical_json_bytes(intent))
        if (
            command.command_id != command_id
            or command.operation is not operation
            or command.intent != canonical_intent
        ):
            _fail(StepUpFailureCode.COMMAND_CONFLICT)
        return cls._result_for_command(connection, command)

    @staticmethod
    def _current(
        histories: RevisionHistories,
        *,
        kind: str,
        fingerprint: str,
        unknown: StepUpFailureCode,
    ) -> tuple[_LifecycleRevision, tuple[_LifecycleRevision, ...]]:
        history = histories[kind].get(fingerprint)
        if history is None:
            _fail(unknown)
        return history[-1], history

    @classmethod
    def _append_bundle(
        cls,
        connection: sqlite3.Connection,
        *,
        command_id: StepUpCommandId,
        operation: StepUpOperation,
        rows: tuple[_LifecycleRevision, ...],
    ) -> StepUpCommandResult:
        count, command_head, audit_head = cls._metadata_state(connection)
        sequence = count + 1
        if not rows or any(row.command_sequence != sequence for row in rows):
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        row_groups: dict[str, tuple[_LifecycleRevision, ...]] = {}
        for row in rows:
            if row.kind in row_groups:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            row_groups[row.kind] = (row,)

        histories = cls._histories(connection)
        proposed: RevisionHistories = {
            kind: dict(grouped) for kind, grouped in histories.items()
        }
        for row in rows:
            fingerprint = _lifecycle_fingerprint(row.kind, row.value)
            proposed[row.kind][fingerprint] = (
                *proposed[row.kind].get(fingerprint, ()),
                row,
            )
        _entity, provisional_binding, provisional_time, _intent, _result = (
            _derive_command_material(
                operation=operation,
                rows=row_groups,
                histories=proposed,
                audit_digest=_GENESIS,
            )
        )
        audit = _audit_revision(
            sequence=sequence,
            command_id=command_id,
            operation=operation,
            binding=provisional_binding,
            occurred_at=provisional_time,
            previous_digest=audit_head,
        )
        entity, binding, occurred_at, intent, result = _derive_command_material(
            operation=operation,
            rows=row_groups,
            histories=proposed,
            audit_digest=audit.digest,
        )
        if binding != provisional_binding or occurred_at != provisional_time:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        command = _command_revision(
            sequence=sequence,
            command_id=command_id,
            operation=operation,
            entity_fingerprint=entity,
            intent=intent,
            result=result,
            occurred_at=occurred_at,
            previous_command_sha256=command_head,
        )
        cls._insert_command(connection, command)
        cls._insert_audit(connection, audit)
        for row in rows:
            cls._insert_revision(connection, row)
        cursor = connection.execute(
            "UPDATE recorded_step_up_metadata_v2 SET command_count=?, "
            "command_head_sha256=?, audit_head_sha256=? WHERE singleton=1 "
            "AND command_count=? AND command_head_sha256=? AND audit_head_sha256=?",
            (
                sequence,
                command.command_sha256,
                audit.digest,
                count,
                command_head,
                audit_head,
            ),
        )
        if cursor.rowcount != 1:
            _fail(StepUpFailureCode.STORAGE_FAILURE)
        return cls._result_for_command(connection, command)

    def create_challenge(
        self, *, command_id: StepUpCommandId, challenge: StepUpChallenge
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        try:
            received_command = snapshot_step_up_command_id(command_id)
            received_challenge = snapshot_step_up_challenge(challenge)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        intent: dict[str, object] = {
            "challenge": _challenge_document(received_challenge),
            "operation": StepUpOperation.BEGIN_CHALLENGE.value,
        }

        def create(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=received_command,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                intent=intent,
            )
            if existing is not None:
                return existing
            histories = self._histories(connection)
            fingerprint = received_challenge.challenge_id.fingerprint()
            if fingerprint in histories["challenge"]:
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            count, _head, _audit = self._metadata_state(connection)
            row = _revision(
                kind="challenge",
                value=received_challenge,
                state="PENDING",
                link=None,
                revision=1,
                command_sequence=count + 1,
                previous_record_sha256=_GENESIS,
            )
            return self._append_bundle(
                connection,
                command_id=received_command,
                operation=StepUpOperation.BEGIN_CHALLENGE,
                rows=(row,),
            )

        return snapshot_step_up_command_result(self._write(create))

    def load_challenge(self, challenge_id: StepUpChallengeId) -> StepUpChallenge:
        _require_development(self._environment)
        try:
            received_id = snapshot_step_up_challenge_id(challenge_id)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)

        def load(connection: sqlite3.Connection) -> StepUpChallenge:
            current, _history = self._current(
                self._histories(connection),
                kind="challenge",
                fingerprint=received_id.fingerprint(),
                unknown=StepUpFailureCode.CHALLENGE_UNKNOWN,
            )
            return snapshot_step_up_challenge(current.value)

        return snapshot_step_up_challenge(self._read(load))

    def record_verification(
        self,
        *,
        command_id: StepUpCommandId,
        verification: StepUpVerificationReceipt,
        now: datetime,
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        try:
            received_command = snapshot_step_up_command_id(command_id)
            received_verification = snapshot_step_up_verification(verification)
            observed_at = require_step_up_utc(now)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        intent: dict[str, object] = {
            "operation": StepUpOperation.VERIFY_CHALLENGE.value,
            "verification": _verification_document(received_verification),
        }

        def record(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=received_command,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                intent=intent,
            )
            if existing is not None:
                return existing
            histories = self._histories(connection)
            challenge_current, challenge_history = self._current(
                histories,
                kind="challenge",
                fingerprint=received_verification.challenge_id.fingerprint(),
                unknown=StepUpFailureCode.CHALLENGE_UNKNOWN,
            )
            challenge = snapshot_step_up_challenge(challenge_current.value)
            if challenge.binding != received_verification.binding:
                _fail(StepUpFailureCode.CHALLENGE_MISMATCH)
            if (
                observed_at != received_verification.verified_at
                or observed_at < challenge.created_at
                or observed_at >= challenge.expires_at
                or received_verification.expires_at > challenge.expires_at
            ):
                _fail(StepUpFailureCode.CHALLENGE_EXPIRED)
            if (
                challenge_current.state != "PENDING"
                or challenge_current.link is not None
            ):
                _fail(StepUpFailureCode.CHALLENGE_REPLAY)
            receipt_fingerprint = received_verification.receipt_id.fingerprint()
            if receipt_fingerprint in histories["receipt"]:
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            count, _head, _audit = self._metadata_state(connection)
            sequence = count + 1
            challenge_row = _revision(
                kind="challenge",
                value=challenge,
                state="VERIFIED",
                link=receipt_fingerprint,
                revision=2,
                command_sequence=sequence,
                previous_record_sha256=challenge_history[-1].record_sha256,
            )
            receipt_row = _revision(
                kind="receipt",
                value=received_verification,
                state="AVAILABLE",
                link=None,
                revision=1,
                command_sequence=sequence,
                previous_record_sha256=_GENESIS,
            )
            return self._append_bundle(
                connection,
                command_id=received_command,
                operation=StepUpOperation.VERIFY_CHALLENGE,
                rows=(challenge_row, receipt_row),
            )

        return snapshot_step_up_command_result(self._write(record))

    def load_verification(
        self, receipt_id: StepUpVerificationReceiptId
    ) -> StepUpVerificationReceipt:
        _require_development(self._environment)
        try:
            received_id = snapshot_step_up_receipt_id(receipt_id)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)

        def load(connection: sqlite3.Connection) -> StepUpVerificationReceipt:
            current, _history = self._current(
                self._histories(connection),
                kind="receipt",
                fingerprint=received_id.fingerprint(),
                unknown=StepUpFailureCode.RECEIPT_UNKNOWN,
            )
            return snapshot_step_up_verification(current.value)

        return snapshot_step_up_verification(self._read(load))

    def issue_grant(
        self,
        *,
        command_id: StepUpCommandId,
        grant: BoundStepUpGrant,
        now: datetime,
    ) -> StepUpCommandResult:
        _require_development(self._environment)
        try:
            received_command = snapshot_step_up_command_id(command_id)
            received_grant = snapshot_bound_step_up_grant(grant)
            observed_at = require_step_up_utc(now)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        intent: dict[str, object] = {
            "grant": _grant_document(received_grant),
            "operation": StepUpOperation.ISSUE_GRANT.value,
        }

        def issue(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=received_command,
                operation=StepUpOperation.ISSUE_GRANT,
                intent=intent,
            )
            if existing is not None:
                return existing
            histories = self._histories(connection)
            receipt_current, receipt_history = self._current(
                histories,
                kind="receipt",
                fingerprint=received_grant.receipt_id.fingerprint(),
                unknown=StepUpFailureCode.RECEIPT_UNKNOWN,
            )
            verification = snapshot_step_up_verification(receipt_current.value)
            if verification.binding != received_grant.binding:
                _fail(StepUpFailureCode.RECEIPT_MISMATCH)
            if (
                observed_at != received_grant.issued_at
                or observed_at < verification.verified_at
                or observed_at >= verification.expires_at
                or received_grant.expires_at > verification.expires_at
            ):
                _fail(StepUpFailureCode.RECEIPT_EXPIRED)
            if receipt_current.state != "AVAILABLE" or receipt_current.link is not None:
                _fail(StepUpFailureCode.RECEIPT_REPLAY)
            grant_fingerprint = received_grant.grant_id.fingerprint()
            if grant_fingerprint in histories["grant"]:
                _fail(StepUpFailureCode.COMMAND_CONFLICT)
            count, _head, _audit = self._metadata_state(connection)
            sequence = count + 1
            receipt_row = _revision(
                kind="receipt",
                value=verification,
                state="CONSUMED",
                link=grant_fingerprint,
                revision=2,
                command_sequence=sequence,
                previous_record_sha256=receipt_history[-1].record_sha256,
            )
            grant_row = _revision(
                kind="grant",
                value=received_grant,
                state="ACTIVE",
                link=None,
                revision=1,
                command_sequence=sequence,
                previous_record_sha256=_GENESIS,
            )
            return self._append_bundle(
                connection,
                command_id=received_command,
                operation=StepUpOperation.ISSUE_GRANT,
                rows=(receipt_row, grant_row),
            )

        return snapshot_step_up_command_result(self._write(issue))

    def load_grant(self, grant_id: BoundStepUpGrantId) -> BoundStepUpGrant:
        _require_development(self._environment)
        try:
            received_id = snapshot_bound_step_up_grant_id(grant_id)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)

        def load(connection: sqlite3.Connection) -> BoundStepUpGrant:
            current, _history = self._current(
                self._histories(connection),
                kind="grant",
                fingerprint=received_id.fingerprint(),
                unknown=StepUpFailureCode.GRANT_UNKNOWN,
            )
            return snapshot_bound_step_up_grant(current.value)

        return snapshot_bound_step_up_grant(self._read(load))

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
        try:
            received_command = snapshot_step_up_command_id(command_id)
            received_grant_id = snapshot_bound_step_up_grant_id(grant_id)
            received_binding = snapshot_step_up_binding(expected_binding)
            observed_at = require_step_up_utc(now)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        if (
            operation
            not in {StepUpOperation.CONSUME_GRANT, StepUpOperation.REVOKE_GRANT}
            or final_state not in {"CONSUMED", "REVOKED"}
            or (operation is StepUpOperation.CONSUME_GRANT)
            != (final_state == "CONSUMED")
        ):
            _fail(StepUpFailureCode.CLAIM_MALFORMED)
        intent: dict[str, object] = {
            "expected_binding": _binding_document(received_binding),
            "finalized_at": _utc_text(observed_at),
            "grant_fingerprint": received_grant_id.fingerprint(),
            "operation": operation.value,
        }

        def finalize_grant(connection: sqlite3.Connection) -> StepUpCommandResult:
            existing = self._existing(
                connection,
                command_id=received_command,
                operation=operation,
                intent=intent,
            )
            if existing is not None:
                return existing
            histories = self._histories(connection)
            current, history = self._current(
                histories,
                kind="grant",
                fingerprint=received_grant_id.fingerprint(),
                unknown=StepUpFailureCode.GRANT_UNKNOWN,
            )
            grant = snapshot_bound_step_up_grant(current.value)
            if grant.binding != received_binding:
                _fail(StepUpFailureCode.GRANT_MISMATCH)
            if observed_at < grant.issued_at or observed_at >= grant.expires_at:
                _fail(StepUpFailureCode.GRANT_EXPIRED)
            if current.state == "REVOKED":
                _fail(StepUpFailureCode.GRANT_REVOKED)
            if current.state != "ACTIVE" or current.link is not None:
                _fail(StepUpFailureCode.GRANT_REPLAY)
            count, _head, _audit = self._metadata_state(connection)
            row = _revision(
                kind="grant",
                value=grant,
                state=final_state,
                link=_utc_text(observed_at),
                revision=2,
                command_sequence=count + 1,
                previous_record_sha256=history[-1].record_sha256,
            )
            return self._append_bundle(
                connection,
                command_id=received_command,
                operation=operation,
                rows=(row,),
            )

        return snapshot_step_up_command_result(self._write(finalize_grant))

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
        try:
            received_command = snapshot_step_up_command_id(command_id)
        except Exception:
            _fail(StepUpFailureCode.CLAIM_MALFORMED)

        def recover_command(connection: sqlite3.Connection) -> StepUpCommandResult:
            command = self._command_by_id(connection, received_command)
            if command is None:
                _fail(StepUpFailureCode.COMMAND_UNKNOWN)
            if command.command_id != received_command:
                _fail(StepUpFailureCode.STORAGE_FAILURE)
            return self._result_for_command(connection, command)

        return snapshot_step_up_command_result(self._read(recover_command))

    def audit_snapshot(self) -> tuple[StepUpAuditRecord, ...]:
        _require_development(self._environment)

        def load(connection: sqlite3.Connection) -> tuple[StepUpAuditRecord, ...]:
            return tuple(
                self._audit_record(audit) for audit in self._audit_rows(connection)
            )

        return tuple(snapshot_step_up_audit(value) for value in self._read(load))

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
