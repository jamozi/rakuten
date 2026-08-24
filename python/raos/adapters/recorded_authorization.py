"""Owner-private durable ST-0403 policy, entitlement, and decision adapter.

Only exact ``ENV-DEV`` and ``ENV-CI`` recorded fixtures are admitted.  The
adapter performs no network or provider access and owns one SQLite transaction
per explicit unit of work.  Snapshot rows are immutable, active revisions use
compare-and-set, decision commands are idempotent, and audit rows form a
verified SHA-256 chain.
"""

from __future__ import annotations

from collections.abc import Callable
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
from typing import Any, Final, NoReturn, TypeVar, cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationAuditRecord,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDecision,
    AuthorizationDecisionReason,
    AuthorizationRepositoryFailure,
    AuthorizationRepositoryFailureCode,
    AuthorizationRule,
    AuthorizationTarget,
    BusinessRole,
    CorrelationId,
    DecisionEffect,
    EntitlementRevision,
    EntitlementSnapshot,
    IndependentActorEvidence,
    MatrixAction,
    OperationId,
    PermissionScope,
    PolicyMode,
    PolicyRevision,
    PolicySnapshot,
    PrincipalIdentity,
    ResourceScope,
    ResourceScopeKind,
    ResourceState,
    RuleId,
    ScopedBusinessRole,
    ScopedPermission,
    _recorded_test_policy_snapshot,  # pyright: ignore[reportPrivateUsage]
    fail_authorization_repository,
    require_authorization_utc,
)


_DATABASE_NAME: Final = "st0403-recorded-authorization.sqlite3"
_SCHEMA_VERSION: Final = 2
_APPLICATION_ID: Final = 1_380_400_302
_GENESIS_DIGEST: Final = "0" * 64
_SHA256: Final = frozenset("0123456789abcdef")
_MAX_DOCUMENT_BYTES: Final = 256 * 1024
_SYNTHETIC_MANAGEMENT_INSTANT: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
_T = TypeVar("_T")

_MUTATION_OPERATIONS: Final = frozenset(
    {
        "INITIALIZE",
        "INSTALL_POLICY",
        "INSTALL_ENTITLEMENTS",
        "APPEND_SOD_EVIDENCE",
        "RECORD_DECISION",
    }
)


def _normalized_sql(value: str) -> str:
    return " ".join(value.split())


_SCHEMA_TABLE_SQL: Final[tuple[tuple[str, str], ...]] = (
    (
        "recorded_authorization_metadata",
        """CREATE TABLE recorded_authorization_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 2),
    schema_binding TEXT NOT NULL CHECK (length(schema_binding) = 64),
    mutation_count INTEGER NOT NULL CHECK (mutation_count >= 0),
    mutation_head_sha256 TEXT NOT NULL CHECK (length(mutation_head_sha256) = 64)
) STRICT""",
    ),
    (
        "recorded_authorization_mutation",
        """CREATE TABLE recorded_authorization_mutation (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    operation TEXT NOT NULL CHECK (operation IN ('INITIALIZE','INSTALL_POLICY','INSTALL_ENTITLEMENTS','APPEND_SOD_EVIDENCE','RECORD_DECISION')),
    entity_key TEXT NOT NULL,
    recovery_key TEXT UNIQUE,
    intent_bytes BLOB NOT NULL,
    intent_sha256 TEXT NOT NULL CHECK (length(intent_sha256) = 64),
    result_bytes BLOB NOT NULL,
    result_sha256 TEXT NOT NULL CHECK (length(result_sha256) = 64),
    committed_at TEXT NOT NULL,
    previous_mutation_sha256 TEXT NOT NULL CHECK (length(previous_mutation_sha256) = 64),
    mutation_sha256 TEXT NOT NULL UNIQUE CHECK (length(mutation_sha256) = 64),
    CHECK ((operation = 'RECORD_DECISION') = (recovery_key IS NOT NULL))
) STRICT""",
    ),
    (
        "recorded_authorization_policy_snapshot",
        """CREATE TABLE recorded_authorization_policy_snapshot (
    revision TEXT PRIMARY KEY,
    document BLOB NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64),
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_active_policy",
        """CREATE TABLE recorded_authorization_active_policy (
    activation_sequence INTEGER PRIMARY KEY CHECK (activation_sequence >= 1),
    revision TEXT NOT NULL,
    expected_revision TEXT,
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (revision) REFERENCES recorded_authorization_policy_snapshot(revision) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_entitlement_snapshot",
        """CREATE TABLE recorded_authorization_entitlement_snapshot (
    principal_fingerprint TEXT NOT NULL CHECK (length(principal_fingerprint) = 64),
    revision TEXT NOT NULL,
    document BLOB NOT NULL,
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    PRIMARY KEY (principal_fingerprint, revision),
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_active_entitlement",
        """CREATE TABLE recorded_authorization_active_entitlement (
    activation_sequence INTEGER PRIMARY KEY CHECK (activation_sequence >= 1),
    principal_fingerprint TEXT NOT NULL CHECK (length(principal_fingerprint) = 64),
    revision TEXT NOT NULL,
    expected_revision TEXT,
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (principal_fingerprint, revision) REFERENCES recorded_authorization_entitlement_snapshot(principal_fingerprint, revision) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_sod_evidence",
        """CREATE TABLE recorded_authorization_sod_evidence (
    evidence_id TEXT PRIMARY KEY,
    document BLOB NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64),
    command_sequence INTEGER NOT NULL UNIQUE,
    previous_record_sha256 TEXT NOT NULL CHECK (length(previous_record_sha256) = 64),
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_audit",
        """CREATE TABLE recorded_authorization_audit (
    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
    command_fingerprint TEXT NOT NULL UNIQUE CHECK (length(command_fingerprint) = 64),
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    effect TEXT NOT NULL CHECK (effect IN ('ALLOW','DENY')),
    occurred_at TEXT NOT NULL,
    previous_digest TEXT NOT NULL CHECK (length(previous_digest) = 64),
    digest TEXT NOT NULL UNIQUE CHECK (length(digest) = 64),
    command_sequence INTEGER NOT NULL UNIQUE,
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
    (
        "recorded_authorization_command",
        """CREATE TABLE recorded_authorization_command (
    command_fingerprint TEXT PRIMARY KEY CHECK (length(command_fingerprint) = 64),
    command_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
    intent_bytes BLOB NOT NULL,
    result_document BLOB NOT NULL,
    audit_sequence INTEGER NOT NULL UNIQUE,
    command_sequence INTEGER NOT NULL UNIQUE,
    record_sha256 TEXT NOT NULL UNIQUE CHECK (length(record_sha256) = 64),
    FOREIGN KEY (audit_sequence) REFERENCES recorded_authorization_audit(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT,
    FOREIGN KEY (command_sequence) REFERENCES recorded_authorization_mutation(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT
) STRICT""",
    ),
)

_APPEND_ONLY_TABLES: Final = tuple(
    name
    for name, _statement in _SCHEMA_TABLE_SQL
    if name != "recorded_authorization_metadata"
)
_SCHEMA_TRIGGER_SQL: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "recorded_authorization_metadata_no_delete",
        "recorded_authorization_metadata",
        "CREATE TRIGGER recorded_authorization_metadata_no_delete BEFORE DELETE ON recorded_authorization_metadata BEGIN SELECT RAISE(ABORT, 'ST0403_METADATA_REQUIRED'); END",
    ),
    (
        "recorded_authorization_metadata_guard_update",
        "recorded_authorization_metadata",
        "CREATE TRIGGER recorded_authorization_metadata_guard_update BEFORE UPDATE ON recorded_authorization_metadata WHEN NEW.singleton != OLD.singleton OR NEW.schema_version != OLD.schema_version OR NEW.schema_binding != OLD.schema_binding OR NEW.mutation_count != OLD.mutation_count + 1 OR NEW.mutation_head_sha256 = OLD.mutation_head_sha256 BEGIN SELECT RAISE(ABORT, 'ST0403_METADATA_TRANSITION_INVALID'); END",
    ),
    *tuple(
        (
            "{}_no_update".format(table),
            table,
            "CREATE TRIGGER {0}_no_update BEFORE UPDATE ON {0} BEGIN SELECT RAISE(ABORT, 'ST0403_APPEND_ONLY'); END".format(
                table
            ),
        )
        for table in _APPEND_ONLY_TABLES
    ),
    *tuple(
        (
            "{}_no_delete".format(table),
            table,
            "CREATE TRIGGER {0}_no_delete BEFORE DELETE ON {0} BEGIN SELECT RAISE(ABORT, 'ST0403_APPEND_ONLY'); END".format(
                table
            ),
        )
        for table in _APPEND_ONLY_TABLES
    ),
)

_SCHEMA_BINDING: Final = hashlib.sha256(
    "\n".join(
        [
            "table\0{}\0{}".format(name, _normalized_sql(sql))
            for name, sql in _SCHEMA_TABLE_SQL
        ]
        + [
            "trigger\0{}\0{}\0{}".format(name, table, _normalized_sql(sql))
            for name, table, sql in _SCHEMA_TRIGGER_SQL
        ]
    ).encode("utf-8")
).hexdigest()

_AUTO_INDEX_COUNTS: Final = {
    "recorded_authorization_mutation": 2,
    "recorded_authorization_policy_snapshot": 4,
    "recorded_authorization_active_policy": 2,
    "recorded_authorization_entitlement_snapshot": 3,
    "recorded_authorization_active_entitlement": 2,
    "recorded_authorization_sod_evidence": 4,
    "recorded_authorization_audit": 4,
    "recorded_authorization_command": 5,
}
_EXPECTED_AUTO_INDEXES: Final = frozenset(
    ("index", "sqlite_autoindex_{}_{}".format(table, index), table, None)
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


def _fail(code: AuthorizationRepositoryFailureCode) -> NoReturn:
    fail_authorization_repository(code)


def _require_recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }:
        _fail(AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY)
    return value


def _text(value: object, *, maximum: int = 16_384) -> str:
    if type(value) is not str or not value or len(value) > maximum or "\x00" in value:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return value


def _sha(value: object) -> str:
    text = _text(value, maximum=64)
    if len(text) != 64 or any(character not in _SHA256 for character in text):
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return text


def _utc_text(value: datetime) -> str:
    return (
        require_authorization_utc(value)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _instant(value: object) -> datetime:
    text = _text(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    if _utc_text(parsed) != text:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return parsed


def _json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    if not encoded or len(encoded) > _MAX_DOCUMENT_BYTES:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return encoded


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)


def _document(value: object) -> dict[str, object]:
    if type(value) is not bytes or not value or len(value) > _MAX_DOCUMENT_BYTES:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    try:
        text = value.decode("ascii")
        parsed: object = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError, UnicodeError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    if type(parsed) is not dict:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    untyped_document = cast(dict[object, object], parsed)
    if any(type(key) is not str for key in untyped_document):
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    document = cast(dict[str, object], untyped_document)
    if _json_bytes(document) != value:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return document


def _mapping(value: object, *, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    mapped = cast(dict[object, object], value)
    if frozenset(mapped) != keys:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return cast(dict[str, object], mapped)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return cast(list[object], value)


def _uuid(value: object) -> UUID:
    text = _text(value, maximum=36)
    try:
        parsed = UUID(text)
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    if parsed.int == 0 or str(parsed) != text:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return parsed


def _digest(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _record_hash(kind: str, values: tuple[object, ...]) -> str:
    return _digest(("RAOS_ST0403_RECORDED_ROW_V2", kind, *values))


def _blob_sha256(value: object) -> str:
    if type(value) is not bytes or not value or len(value) > _MAX_DOCUMENT_BYTES:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return hashlib.sha256(value).hexdigest()


def _mutation_hash(
    *,
    sequence: int,
    operation: str,
    entity_key: str,
    recovery_key: str | None,
    intent_sha256: str,
    result_sha256: str,
    committed_at: str,
    previous_mutation_sha256: str,
) -> str:
    return _record_hash(
        "MUTATION",
        (
            sequence,
            operation,
            entity_key,
            recovery_key,
            intent_sha256,
            result_sha256,
            committed_at,
            previous_mutation_sha256,
        ),
    )


def _scope_document(scope: ResourceScope) -> dict[str, object]:
    if type(scope) is not ResourceScope:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return {
        "kind": scope.kind.value,
        "site_id": str(scope.site_id),
        "resource_id": str(scope.resource_id),
    }


def _scope_from_document(value: object) -> ResourceScope:
    row = _mapping(value, keys=frozenset({"kind", "site_id", "resource_id"}))
    try:
        kind = ResourceScopeKind(_text(row["kind"], maximum=64))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return ResourceScope(
        kind=kind,
        site_id=_uuid(row["site_id"]),
        resource_id=_uuid(row["resource_id"]),
    )


def _target_document(target: AuthorizationTarget) -> dict[str, object]:
    if type(target) is not AuthorizationTarget:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return {
        "scope": _scope_document(target.scope),
        "state": None if target.state is None else target.state.value,
    }


def _target_from_document(value: object) -> AuthorizationTarget:
    row = _mapping(value, keys=frozenset({"scope", "state"}))
    state_value = row["state"]
    return AuthorizationTarget(
        scope=_scope_from_document(row["scope"]),
        state=None if state_value is None else ResourceState(_text(state_value)),
    )


def _rule_document(rule: AuthorizationRule) -> dict[str, object]:
    if type(rule) is not AuthorizationRule:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return {
        "rule_id": rule.rule_id.value,
        "role": rule.role.value,
        "permission_scope": rule.permission_scope.value,
        "action": rule.action.value,
        "resource_kind": rule.resource_kind.value,
        "resource_state": (
            None if rule.resource_state is None else rule.resource_state.value
        ),
    }


def _rule_from_document(value: object) -> AuthorizationRule:
    row = _mapping(
        value,
        keys=frozenset(
            {
                "rule_id",
                "role",
                "permission_scope",
                "action",
                "resource_kind",
                "resource_state",
            }
        ),
    )
    try:
        role = BusinessRole(_text(row["role"], maximum=64))
        resource_kind = ResourceScopeKind(_text(row["resource_kind"], maximum=64))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    raw_state = row["resource_state"]
    return AuthorizationRule(
        rule_id=RuleId(_text(row["rule_id"])),
        role=role,
        permission_scope=PermissionScope(_text(row["permission_scope"])),
        action=ActionCode(_text(row["action"])),
        resource_kind=resource_kind,
        resource_state=(None if raw_state is None else ResourceState(_text(raw_state))),
    )


def _policy_document(snapshot: PolicySnapshot) -> dict[str, object]:
    if type(snapshot) is not PolicySnapshot:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    snapshot.require_valid()
    return {
        "revision": snapshot.revision.value,
        "mode": snapshot.mode.value,
        "rules": [_rule_document(rule) for rule in snapshot.rules],
        "fingerprint": snapshot.fingerprint,
    }


def _policy_from_document(value: object) -> PolicySnapshot:
    row = _mapping(value, keys=frozenset({"revision", "mode", "rules", "fingerprint"}))
    try:
        mode = PolicyMode(_text(row["mode"], maximum=32))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    rules = tuple(_rule_from_document(value) for value in _list(row["rules"]))
    revision = PolicyRevision(_text(row["revision"]))
    snapshot = (
        PolicySnapshot(revision=revision, mode=PolicyMode.DISABLED, rules=rules)
        if mode is PolicyMode.DISABLED
        else _recorded_test_policy_snapshot(revision=revision, rules=rules)
    )
    if snapshot.fingerprint != _sha(row["fingerprint"]):
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return snapshot


def _entitlement_document(snapshot: EntitlementSnapshot) -> dict[str, object]:
    if type(snapshot) is not EntitlementSnapshot:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    snapshot.require_valid()
    return {
        "principal_fingerprint": snapshot.principal.fingerprint,
        "revision": snapshot.revision.value,
        "roles": [
            {"role": role.role.value, "scope": _scope_document(role.scope)}
            for role in snapshot.roles
        ],
        "permission_scopes": [
            {
                "permission_scope": permission.permission_scope.value,
                "scope": _scope_document(permission.scope),
            }
            for permission in snapshot.permission_scopes
        ],
    }


def _entitlement_from_document(
    value: object, *, principal: PrincipalIdentity
) -> EntitlementSnapshot:
    row = _mapping(
        value,
        keys=frozenset(
            {"principal_fingerprint", "revision", "roles", "permission_scopes"}
        ),
    )
    if _sha(row["principal_fingerprint"]) != principal.fingerprint:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    roles: list[ScopedBusinessRole] = []
    for value in _list(row["roles"]):
        item = _mapping(value, keys=frozenset({"role", "scope"}))
        try:
            role = BusinessRole(_text(item["role"], maximum=64))
        except ValueError:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        roles.append(
            ScopedBusinessRole(role=role, scope=_scope_from_document(item["scope"]))
        )
    permissions: list[ScopedPermission] = []
    for value in _list(row["permission_scopes"]):
        item = _mapping(value, keys=frozenset({"permission_scope", "scope"}))
        permissions.append(
            ScopedPermission(
                permission_scope=PermissionScope(_text(item["permission_scope"])),
                scope=_scope_from_document(item["scope"]),
            )
        )
    return EntitlementSnapshot(
        revision=EntitlementRevision(_text(row["revision"])),
        principal=principal,
        roles=tuple(roles),
        permission_scopes=tuple(permissions),
    )


def _evidence_document(evidence: IndependentActorEvidence) -> dict[str, object]:
    if type(evidence) is not IndependentActorEvidence:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return {
        "evidence_id": str(evidence.evidence_id),
        "actor_fingerprint": evidence.actor_fingerprint,
        "action": evidence.action.value,
        "operation_id": evidence.operation_id.value,
        "site_id": str(evidence.site_id),
        "resource_id": str(evidence.resource_id),
        "evidence_snapshot_sha256": evidence.evidence_snapshot_sha256,
        "recorded_at": _utc_text(evidence.recorded_at),
        "fingerprint": evidence.fingerprint,
    }


def _evidence_from_document(value: object) -> IndependentActorEvidence:
    row = _mapping(
        value,
        keys=frozenset(
            {
                "evidence_id",
                "actor_fingerprint",
                "action",
                "operation_id",
                "site_id",
                "resource_id",
                "evidence_snapshot_sha256",
                "recorded_at",
                "fingerprint",
            }
        ),
    )
    try:
        action = MatrixAction(_text(row["action"], maximum=64))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    evidence = IndependentActorEvidence(
        evidence_id=_uuid(row["evidence_id"]),
        actor_fingerprint=_sha(row["actor_fingerprint"]),
        action=action,
        operation_id=OperationId(_text(row["operation_id"])),
        site_id=_uuid(row["site_id"]),
        resource_id=_uuid(row["resource_id"]),
        evidence_snapshot_sha256=_sha(row["evidence_snapshot_sha256"]),
        recorded_at=_instant(row["recorded_at"]),
    )
    if evidence.fingerprint != _sha(row["fingerprint"]):
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return evidence


def _decision_document(decision: AuthorizationDecision) -> dict[str, object]:
    if type(decision) is not AuthorizationDecision:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return {
        "correlation_id": decision.correlation_id.value,
        "effect": decision.effect.value,
        "reason": decision.reason.value,
        "policy_revision": decision.policy_revision.value,
        "policy_fingerprint": decision.policy_fingerprint,
        "entitlement_revision": decision.entitlement_revision.value,
        "matched_rule_id": (
            None if decision.matched_rule_id is None else decision.matched_rule_id.value
        ),
        "action": decision.action.value,
        "target": _target_document(decision.target),
    }


def _decision_from_document(value: object) -> AuthorizationDecision:
    row = _mapping(
        value,
        keys=frozenset(
            {
                "correlation_id",
                "effect",
                "reason",
                "policy_revision",
                "policy_fingerprint",
                "entitlement_revision",
                "matched_rule_id",
                "action",
                "target",
            }
        ),
    )
    try:
        effect = DecisionEffect(_text(row["effect"], maximum=8))
        reason = AuthorizationDecisionReason(_text(row["reason"], maximum=64))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    raw_rule_id = row["matched_rule_id"]
    return AuthorizationDecision(
        correlation_id=CorrelationId(_text(row["correlation_id"])),
        effect=effect,
        reason=reason,
        policy_revision=PolicyRevision(_text(row["policy_revision"])),
        policy_fingerprint=_sha(row["policy_fingerprint"]),
        entitlement_revision=EntitlementRevision(_text(row["entitlement_revision"])),
        matched_rule_id=(None if raw_rule_id is None else RuleId(_text(raw_rule_id))),
        action=ActionCode(_text(row["action"])),
        target=_target_from_document(row["target"]),
    )


def _audit_digest(
    *,
    sequence: int,
    command_fingerprint: str,
    request_digest: str,
    effect: DecisionEffect,
    occurred_at: datetime,
    previous_digest: str,
) -> str:
    return _digest(
        {
            "schema": "ST0403_AUTHORIZATION_AUDIT_V1",
            "sequence": sequence,
            "command_fingerprint": command_fingerprint,
            "request_digest": request_digest,
            "effect": effect.value,
            "occurred_at": _utc_text(occurred_at),
            "previous_digest": previous_digest,
        }
    )


def _result_document(result: AuthorizationCommandResult) -> dict[str, object]:
    return {
        "command_id": result.command_id.value,
        "request_digest": result.request_digest,
        "session_fingerprint": result.session_fingerprint,
        "decision": _decision_document(result.decision),
        "audit": {
            "sequence": result.audit.sequence,
            "command_fingerprint": result.audit.command_fingerprint,
            "request_digest": result.audit.request_digest,
            "effect": result.audit.effect.value,
            "occurred_at": _utc_text(result.audit.occurred_at),
            "previous_digest": result.audit.previous_digest,
            "digest": result.audit.digest,
        },
        "step_up_receipt_fingerprint": result.step_up_receipt_fingerprint,
    }


def _result_from_document(value: object) -> AuthorizationCommandResult:
    row = _mapping(
        value,
        keys=frozenset(
            {
                "command_id",
                "request_digest",
                "session_fingerprint",
                "decision",
                "audit",
                "step_up_receipt_fingerprint",
            }
        ),
    )
    audit_row = _mapping(
        row["audit"],
        keys=frozenset(
            {
                "sequence",
                "command_fingerprint",
                "request_digest",
                "effect",
                "occurred_at",
                "previous_digest",
                "digest",
            }
        ),
    )
    sequence = audit_row["sequence"]
    if type(sequence) is not int:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    try:
        effect = DecisionEffect(_text(audit_row["effect"], maximum=8))
    except ValueError:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    audit = AuthorizationAuditRecord(
        sequence=sequence,
        command_fingerprint=_sha(audit_row["command_fingerprint"]),
        request_digest=_sha(audit_row["request_digest"]),
        effect=effect,
        occurred_at=_instant(audit_row["occurred_at"]),
        previous_digest=_sha(audit_row["previous_digest"]),
        digest=_sha(audit_row["digest"]),
    )
    expected_digest = _audit_digest(
        sequence=audit.sequence,
        command_fingerprint=audit.command_fingerprint,
        request_digest=audit.request_digest,
        effect=audit.effect,
        occurred_at=audit.occurred_at,
        previous_digest=audit.previous_digest,
    )
    if audit.digest != expected_digest:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    raw_receipt = row["step_up_receipt_fingerprint"]
    return AuthorizationCommandResult(
        command_id=AuthorizationCommandId(_text(row["command_id"])),
        request_digest=_sha(row["request_digest"]),
        session_fingerprint=_sha(row["session_fingerprint"]),
        decision=_decision_from_document(row["decision"]),
        audit=audit,
        step_up_receipt_fingerprint=(
            None if raw_receipt is None else _sha(raw_receipt)
        ),
    )


class RecordedAuthorizationCommitFault(str, Enum):
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


def recorded_authorization_policy_snapshot(
    *, revision: PolicyRevision, rules: tuple[AuthorizationRule, ...]
) -> PolicySnapshot:
    """Build a fixture policy only from active generated registry bindings."""

    from raos.adapters.generated_st0403_authorization_registry import (
        CANONICAL_AUTHORIZATION_REGISTRY,
    )

    if (
        type(revision) is not PolicyRevision
        or not revision.value.startswith("RECORDED:ST0403:")
        or type(rules) is not tuple
        or not rules
        or tuple(rule.canonical_key for rule in rules)
        != tuple(sorted(rule.canonical_key for rule in rules))
    ):
        _fail(AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY)
    for rule in rules:
        if type(rule) is not AuthorizationRule:
            _fail(AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY)
        try:
            action = MatrixAction(rule.action.value)
        except ValueError:
            _fail(AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY)
        definition = CANONICAL_AUTHORIZATION_REGISTRY.definition(action)
        candidates = tuple(
            binding
            for binding in CANONICAL_AUTHORIZATION_REGISTRY.bindings
            if binding.action is action
            and binding.status.value == "ACTIVE_RECORDED"
            and binding.permission_scope == rule.permission_scope
            and binding.resource_kind is rule.resource_kind
            and binding.accepts_state(rule.resource_state)
        )
        if len(candidates) != 1 or rule.role not in definition.allowed_roles:
            _fail(AuthorizationRepositoryFailureCode.DEVELOPMENT_ONLY)
    return _recorded_test_policy_snapshot(revision=revision, rules=rules)


class _InjectedCrash(RuntimeError):
    __slots__ = ("point",)

    def __init__(self, point: RecordedAuthorizationCommitFault) -> None:
        self.point = point
        super().__init__("RECORDED_AUTHORIZATION_PROCESS_CRASH")


@final
class RecordedSqliteAuthorizationRepository:
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
        fault_once_at: RecordedAuthorizationCommitFault | None = None,
    ) -> None:
        self._environment = _require_recorded_environment(environment)
        if (
            fault_once_at is not None
            and type(fault_once_at) is not RecordedAuthorizationCommitFault
        ):
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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

    @property
    def external_action_count(self) -> int:
        """Recorded authorization never dispatches an external action."""

        _require_recorded_environment(self._environment)
        return 0

    @staticmethod
    def _validate_private_root(value: object) -> tuple[Path, tuple[int, int]]:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        root = Path(os.path.abspath(value))
        try:
            current = Path(root.anchor)
            for component in root.parts[1:]:
                current /= component
                metadata = current.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            metadata = root.lstat()
        except OSError:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            return created, (metadata.st_dev, metadata.st_ino)
        except AuthorizationRepositoryFailure:
            raise
        except OSError:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

    def _connect(self, *, verify: bool = True) -> sqlite3.Connection:
        _created, identity = self._open_database_file(allow_create=False)
        if identity != self._database_identity:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            self._validate_database_identity()
            if verify:
                self._verified_state(connection, check_process=True)
            return connection
        except AuthorizationRepositoryFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error, OSError:
            if connection is not None:
                self._close_safely(connection)
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone() != (
                0,
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            connection.execute("PRAGMA application_id = 1380400302")
            connection.execute("PRAGMA user_version = 2")
            for _name, statement in _SCHEMA_TABLE_SQL:
                connection.execute(statement)
            for _name, _table, statement in _SCHEMA_TRIGGER_SQL:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO recorded_authorization_metadata VALUES (1, ?, ?, 0, ?)",
                (_SCHEMA_VERSION, _SCHEMA_BINDING, _GENESIS_DIGEST),
            )
            disabled = PolicySnapshot(
                revision=PolicyRevision("TEST_ONLY:DISABLED"),
                mode=PolicyMode.DISABLED,
                rules=(),
            )
            document = _json_bytes(_policy_document(disabled))
            sequence = 1
            policy_record = _record_hash(
                "POLICY",
                (
                    disabled.revision.value,
                    _blob_sha256(document),
                    disabled.fingerprint,
                    sequence,
                    _GENESIS_DIGEST,
                ),
            )
            activation_record = _record_hash(
                "POLICY_ACTIVATION",
                (
                    1,
                    disabled.revision.value,
                    None,
                    sequence,
                    _GENESIS_DIGEST,
                ),
            )
            inserted = self._insert_mutation(
                connection,
                operation="INITIALIZE",
                entity_key="POLICY",
                recovery_key=None,
                intent={"schema_version": _SCHEMA_VERSION},
                result={
                    "activation_record_sha256": activation_record,
                    "fingerprint": disabled.fingerprint,
                    "policy_record_sha256": policy_record,
                    "revision": disabled.revision.value,
                },
                committed_at=_SYNTHETIC_MANAGEMENT_INSTANT,
            )
            if inserted != sequence:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            connection.execute(
                "INSERT INTO recorded_authorization_policy_snapshot VALUES (?,?,?,?,?,?)",
                (
                    disabled.revision.value,
                    document,
                    disabled.fingerprint,
                    sequence,
                    _GENESIS_DIGEST,
                    policy_record,
                ),
            )
            connection.execute(
                "INSERT INTO recorded_authorization_active_policy VALUES (?,?,?,?,?,?)",
                (
                    1,
                    disabled.revision.value,
                    None,
                    sequence,
                    _GENESIS_DIGEST,
                    activation_record,
                ),
            )
            self._verify_schema(connection)
            self._verify_integrity(connection)
            connection.commit()
            self._validate_database_identity()
        except AuthorizationRepositoryFailure:
            self._rollback(connection)
            raise
        except sqlite3.Error:
            self._rollback(connection)
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

    @staticmethod
    def _master_record(row: object) -> tuple[str, str, str, str | None]:
        if type(row) is not tuple:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        values = cast(tuple[object, ...], row)
        if len(values) != 4:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        kind, name, table, statement = values
        if (
            type(kind) is not str
            or type(name) is not str
            or type(table) is not str
            or (statement is not None and type(statement) is not str)
        ):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
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
        ):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
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
        for raw in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' OR type='index'"
        ).fetchall():
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
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        table_state = {
            str(row[1]): (int(row[4]), int(row[5]))
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("recorded_authorization_")
        }
        if table_state != {name: (0, 1) for name, _statement in _SCHEMA_TABLE_SQL}:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        if (
            connection.execute("PRAGMA integrity_check").fetchone() != ("ok",)
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        metadata = connection.execute(
            "SELECT singleton,schema_version,schema_binding,mutation_count,"
            "mutation_head_sha256 FROM recorded_authorization_metadata"
        ).fetchall()
        if len(metadata) != 1 or tuple(metadata[0])[:3] != (
            1,
            _SCHEMA_VERSION,
            _SCHEMA_BINDING,
        ):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

    def inject_commit_fault(self, point: RecordedAuthorizationCommitFault) -> None:
        with self._fault_lock:
            if self._fault_once_at is point:
                self._fault_once_at = None
                raise _InjectedCrash(point)

    @staticmethod
    def _row(row: object, *, count: int) -> tuple[object, ...]:
        if type(row) is not tuple:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        values = cast(tuple[object, ...], row)
        if len(values) != count:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        return values

    @staticmethod
    def _insert_mutation(
        connection: sqlite3.Connection,
        *,
        operation: str,
        entity_key: str,
        recovery_key: str | None,
        intent: dict[str, object],
        result: dict[str, object],
        committed_at: datetime,
    ) -> int:
        if operation not in _MUTATION_OPERATIONS:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        metadata = connection.execute(
            "SELECT mutation_count,mutation_head_sha256 "
            "FROM recorded_authorization_metadata WHERE singleton=1"
        ).fetchone()
        if metadata is None or type(metadata[0]) is not int or metadata[0] < 0:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        sequence = metadata[0] + 1
        previous = _sha(metadata[1])
        intent_bytes = _json_bytes(intent)
        result_bytes = _json_bytes(result)
        intent_sha = hashlib.sha256(intent_bytes).hexdigest()
        result_sha = hashlib.sha256(result_bytes).hexdigest()
        instant = _utc_text(committed_at)
        mutation_sha = _mutation_hash(
            sequence=sequence,
            operation=operation,
            entity_key=_text(entity_key),
            recovery_key=(None if recovery_key is None else _text(recovery_key)),
            intent_sha256=intent_sha,
            result_sha256=result_sha,
            committed_at=instant,
            previous_mutation_sha256=previous,
        )
        connection.execute(
            "INSERT INTO recorded_authorization_mutation VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?)",
            (
                sequence,
                operation,
                entity_key,
                recovery_key,
                intent_bytes,
                intent_sha,
                result_bytes,
                result_sha,
                instant,
                previous,
                mutation_sha,
            ),
        )
        cursor = connection.execute(
            "UPDATE recorded_authorization_metadata "
            "SET mutation_count=?,mutation_head_sha256=? "
            "WHERE singleton=1 AND mutation_count=? AND mutation_head_sha256=?",
            (sequence, mutation_sha, sequence - 1, previous),
        )
        if cursor.rowcount != 1:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        return sequence

    def _verify_integrity(self, connection: sqlite3.Connection) -> None:
        mutation_rows = connection.execute(
            "SELECT sequence,operation,entity_key,recovery_key,intent_bytes,"
            "intent_sha256,result_bytes,result_sha256,committed_at,"
            "previous_mutation_sha256,mutation_sha256 "
            "FROM recorded_authorization_mutation ORDER BY sequence"
        ).fetchall()
        mutations: dict[int, tuple[str, str, str | None, bytes, bytes, datetime]] = {}
        previous_mutation = _GENESIS_DIGEST
        for expected_sequence, raw in enumerate(mutation_rows, start=1):
            values = self._row(tuple(raw), count=11)
            sequence, operation, entity_key, recovery_key = values[:4]
            if (
                type(sequence) is not int
                or sequence != expected_sequence
                or type(operation) is not str
                or operation not in _MUTATION_OPERATIONS
                or type(entity_key) is not str
                or not entity_key
                or (recovery_key is not None and type(recovery_key) is not str)
                or ((operation == "RECORD_DECISION") != (recovery_key is not None))
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            intent_bytes = values[4]
            result_bytes = values[6]
            intent = _document(intent_bytes)
            _document(result_bytes)
            intent_sha = _blob_sha256(intent_bytes)
            result_sha = _blob_sha256(result_bytes)
            instant = _instant(values[8])
            previous = _sha(values[9])
            mutation_sha = _sha(values[10])
            if (
                intent_sha != _sha(values[5])
                or result_sha != _sha(values[7])
                or previous != previous_mutation
                or mutation_sha
                != _mutation_hash(
                    sequence=sequence,
                    operation=operation,
                    entity_key=entity_key,
                    recovery_key=recovery_key,
                    intent_sha256=intent_sha,
                    result_sha256=result_sha,
                    committed_at=_utc_text(instant),
                    previous_mutation_sha256=previous,
                )
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            mutations[sequence] = (
                operation,
                entity_key,
                recovery_key,
                cast(bytes, intent_bytes),
                cast(bytes, result_bytes),
                instant,
            )
            previous_mutation = mutation_sha

        expected_payloads: dict[
            int,
            tuple[str, str, str | None, dict[str, object], dict[str, object], datetime],
        ] = {}
        policy_rows = connection.execute(
            "SELECT revision,document,fingerprint,command_sequence,"
            "previous_record_sha256,record_sha256 "
            "FROM recorded_authorization_policy_snapshot ORDER BY command_sequence"
        ).fetchall()
        policies: dict[str, tuple[bytes, str, int, str]] = {}
        previous_policy = _GENESIS_DIGEST
        for raw in policy_rows:
            values = self._row(tuple(raw), count=6)
            revision = _text(values[0])
            document = values[1]
            fingerprint = _sha(values[2])
            command_sequence = values[3]
            previous = _sha(values[4])
            record = _sha(values[5])
            if type(command_sequence) is not int or command_sequence < 1:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            policy = _policy_from_document(_document(document))
            if (
                policy.revision.value != revision
                or policy.fingerprint != fingerprint
                or previous != previous_policy
                or record
                != _record_hash(
                    "POLICY",
                    (
                        revision,
                        _blob_sha256(document),
                        fingerprint,
                        command_sequence,
                        previous,
                    ),
                )
                or revision in policies
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            policies[revision] = (
                cast(bytes, document),
                fingerprint,
                command_sequence,
                record,
            )
            previous_policy = record
        active_policy_rows = connection.execute(
            "SELECT activation_sequence,revision,expected_revision,command_sequence,"
            "previous_record_sha256,record_sha256 "
            "FROM recorded_authorization_active_policy ORDER BY activation_sequence"
        ).fetchall()
        if not active_policy_rows:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        previous_activation = _GENESIS_DIGEST
        prior_revision: str | None = None
        for expected_activation, raw in enumerate(active_policy_rows, start=1):
            values = self._row(tuple(raw), count=6)
            activation_value, revision_value, expected_value, command_value = values[:4]
            if (
                type(activation_value) is not int
                or activation_value != expected_activation
                or type(revision_value) is not str
                or (expected_value is not None and type(expected_value) is not str)
                or expected_value != prior_revision
                or type(command_value) is not int
                or revision_value not in policies
                or policies[revision_value][2] != command_value
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            activation = activation_value
            revision = revision_value
            expected_revision = expected_value
            command_sequence = command_value
            previous = _sha(values[4])
            record = _sha(values[5])
            if previous != previous_activation or record != _record_hash(
                "POLICY_ACTIVATION",
                (
                    activation,
                    revision,
                    expected_revision,
                    command_sequence,
                    previous,
                ),
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            document, fingerprint, _policy_command, policy_record = policies[revision]
            operation = "INITIALIZE" if activation == 1 else "INSTALL_POLICY"
            policy_intent: dict[str, object] = (
                {"schema_version": _SCHEMA_VERSION}
                if operation == "INITIALIZE"
                else {
                    "expected_revision": expected_revision,
                    "snapshot": _document(document),
                }
            )
            policy_result: dict[str, object] = {
                "activation_record_sha256": record,
                "fingerprint": fingerprint,
                "policy_record_sha256": policy_record,
                "revision": revision,
            }
            expected_payloads[command_sequence] = (
                operation,
                "POLICY",
                None,
                policy_intent,
                policy_result,
                _SYNTHETIC_MANAGEMENT_INSTANT,
            )
            previous_activation = record
            prior_revision = revision

        entitlement_rows = connection.execute(
            "SELECT principal_fingerprint,revision,document,command_sequence,"
            "previous_record_sha256,record_sha256 "
            "FROM recorded_authorization_entitlement_snapshot "
            "ORDER BY principal_fingerprint,command_sequence"
        ).fetchall()
        entitlements: dict[tuple[str, str], tuple[bytes, int, str]] = {}
        entitlement_heads: dict[str, str] = {}
        for raw in entitlement_rows:
            values = self._row(tuple(raw), count=6)
            principal_fingerprint = _sha(values[0])
            revision = _text(values[1])
            document = values[2]
            command_sequence = values[3]
            previous = _sha(values[4])
            record = _sha(values[5])
            if type(command_sequence) is not int or command_sequence < 1:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            row = _document(document)
            if (
                principal_fingerprint != _sha(row.get("principal_fingerprint"))
                or revision != _text(row.get("revision"))
                or previous
                != entitlement_heads.get(principal_fingerprint, _GENESIS_DIGEST)
                or record
                != _record_hash(
                    "ENTITLEMENT",
                    (
                        principal_fingerprint,
                        revision,
                        _blob_sha256(document),
                        command_sequence,
                        previous,
                    ),
                )
                or (principal_fingerprint, revision) in entitlements
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            entitlements[(principal_fingerprint, revision)] = (
                cast(bytes, document),
                command_sequence,
                record,
            )
            entitlement_heads[principal_fingerprint] = record
        active_entitlement_rows = connection.execute(
            "SELECT activation_sequence,principal_fingerprint,revision,"
            "expected_revision,command_sequence,previous_record_sha256,record_sha256 "
            "FROM recorded_authorization_active_entitlement "
            "ORDER BY activation_sequence"
        ).fetchall()
        entitlement_activation_heads: dict[str, str] = {}
        entitlement_active_revisions: dict[str, str] = {}
        for raw in active_entitlement_rows:
            values = self._row(tuple(raw), count=7)
            activation_value = values[0]
            principal = _sha(values[1])
            revision = _text(values[2])
            expected_value = values[3]
            command_value = values[4]
            previous = _sha(values[5])
            record = _sha(values[6])
            expected = entitlement_active_revisions.get(principal)
            if (
                type(activation_value) is not int
                or activation_value < 1
                or (expected_value is not None and type(expected_value) is not str)
                or expected_value != expected
                or type(command_value) is not int
                or (principal, revision) not in entitlements
                or entitlements[(principal, revision)][1] != command_value
                or previous
                != entitlement_activation_heads.get(principal, _GENESIS_DIGEST)
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            activation = activation_value
            expected_revision = expected_value
            command_sequence = command_value
            if record != _record_hash(
                "ENTITLEMENT_ACTIVATION",
                (
                    activation,
                    principal,
                    revision,
                    expected_revision,
                    command_sequence,
                    previous,
                ),
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            document, _snapshot_command, snapshot_record = entitlements[
                (principal, revision)
            ]
            expected_payloads[command_sequence] = (
                "INSTALL_ENTITLEMENTS",
                principal,
                None,
                {
                    "expected_revision": expected_revision,
                    "principal_fingerprint": principal,
                    "snapshot": _document(document),
                },
                {
                    "activation_record_sha256": record,
                    "entitlement_record_sha256": snapshot_record,
                    "principal_fingerprint": principal,
                    "revision": revision,
                },
                _SYNTHETIC_MANAGEMENT_INSTANT,
            )
            entitlement_activation_heads[principal] = record
            entitlement_active_revisions[principal] = revision

        evidence_rows = connection.execute(
            "SELECT evidence_id,document,fingerprint,command_sequence,"
            "previous_record_sha256,record_sha256 "
            "FROM recorded_authorization_sod_evidence ORDER BY command_sequence"
        ).fetchall()
        previous_evidence = _GENESIS_DIGEST
        for raw in evidence_rows:
            values = self._row(tuple(raw), count=6)
            evidence_id = _text(values[0], maximum=36)
            document = values[1]
            fingerprint = _sha(values[2])
            command_sequence = values[3]
            previous = _sha(values[4])
            record = _sha(values[5])
            if type(command_sequence) is not int or command_sequence < 1:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            evidence = _evidence_from_document(_document(document))
            if (
                str(evidence.evidence_id) != evidence_id
                or evidence.fingerprint != fingerprint
                or previous != previous_evidence
                or record
                != _record_hash(
                    "SOD_EVIDENCE",
                    (
                        evidence_id,
                        _blob_sha256(document),
                        fingerprint,
                        command_sequence,
                        previous,
                    ),
                )
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            expected_payloads[command_sequence] = (
                "APPEND_SOD_EVIDENCE",
                evidence_id,
                None,
                {"evidence": _document(document)},
                {
                    "evidence_id": evidence_id,
                    "evidence_record_sha256": record,
                    "fingerprint": fingerprint,
                },
                evidence.recorded_at,
            )
            previous_evidence = record

        previous = _GENESIS_DIGEST
        expected_sequence = 1
        audit_by_sequence: dict[int, AuthorizationAuditRecord] = {}
        audit_record_by_sequence: dict[int, str] = {}
        audit_mutation_by_sequence: dict[int, int] = {}
        audit_rows = connection.execute(
            "SELECT sequence,command_fingerprint,request_digest,effect,occurred_at,"
            "previous_digest,digest,command_sequence,record_sha256 "
            "FROM recorded_authorization_audit "
            "ORDER BY sequence"
        ).fetchall()
        for raw in audit_rows:
            values = self._row(tuple(raw), count=9)
            sequence = values[0]
            if type(sequence) is not int or sequence != expected_sequence:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            try:
                effect = DecisionEffect(_text(values[3], maximum=8))
            except ValueError:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            audit = AuthorizationAuditRecord(
                sequence=sequence,
                command_fingerprint=_sha(values[1]),
                request_digest=_sha(values[2]),
                effect=effect,
                occurred_at=_instant(values[4]),
                previous_digest=_sha(values[5]),
                digest=_sha(values[6]),
            )
            command_sequence = values[7]
            record = _sha(values[8])
            if (
                audit.previous_digest != previous
                or audit.digest
                != _audit_digest(
                    sequence=audit.sequence,
                    command_fingerprint=audit.command_fingerprint,
                    request_digest=audit.request_digest,
                    effect=audit.effect,
                    occurred_at=audit.occurred_at,
                    previous_digest=audit.previous_digest,
                )
                or type(command_sequence) is not int
                or record
                != _record_hash(
                    "AUDIT",
                    (
                        audit.sequence,
                        audit.command_fingerprint,
                        audit.request_digest,
                        audit.effect.value,
                        _utc_text(audit.occurred_at),
                        audit.previous_digest,
                        audit.digest,
                        command_sequence,
                    ),
                )
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            audit_by_sequence[sequence] = audit
            audit_record_by_sequence[sequence] = record
            audit_mutation_by_sequence[sequence] = command_sequence
            previous = audit.digest
            expected_sequence += 1
        command_rows = connection.execute(
            "SELECT command_fingerprint,command_id,request_digest,intent_bytes,"
            "result_document,audit_sequence,command_sequence,record_sha256 "
            "FROM recorded_authorization_command ORDER BY command_sequence"
        ).fetchall()
        if len(command_rows) != len(audit_rows):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        for raw in command_rows:
            values = self._row(tuple(raw), count=8)
            command_fingerprint = _sha(values[0])
            command_id = AuthorizationCommandId(_text(values[1]))
            request_digest = _sha(values[2])
            intent_bytes = values[3]
            result_document = values[4]
            command_result = _result_from_document(_document(result_document))
            sequence = values[5]
            command_sequence = values[6]
            record = _sha(values[7])
            if (
                type(sequence) is not int
                or type(command_sequence) is not int
                or sequence not in audit_by_sequence
                or command_result.audit != audit_by_sequence[sequence]
                or audit_mutation_by_sequence[sequence] != command_sequence
                or command_result.command_id != command_id
                or command_result.command_id_fingerprint != command_fingerprint
                or command_result.request_digest != request_digest
                or record
                != _record_hash(
                    "COMMAND",
                    (
                        command_fingerprint,
                        command_id.value,
                        request_digest,
                        _blob_sha256(intent_bytes),
                        _blob_sha256(result_document),
                        sequence,
                        command_sequence,
                    ),
                )
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

            intent = _document(intent_bytes)
            expected_intent: dict[str, object] = {
                "command_fingerprint": command_fingerprint,
                "command_id": command_id.value,
                "decision": _decision_document(command_result.decision),
                "occurred_at": _utc_text(command_result.audit.occurred_at),
                "request_digest": request_digest,
                "session_fingerprint": command_result.session_fingerprint,
                "step_up_receipt_fingerprint": command_result.step_up_receipt_fingerprint,
            }
            if intent != expected_intent:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            expected_payloads[command_sequence] = (
                "RECORD_DECISION",
                command_fingerprint,
                command_fingerprint,
                expected_intent,
                {
                    "audit_record_sha256": audit_record_by_sequence[sequence],
                    "command_record_sha256": record,
                    "result": _document(result_document),
                },
                command_result.audit.occurred_at,
            )

        if set(mutations) != set(expected_payloads):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        for sequence, expected_payload in expected_payloads.items():
            operation, entity_key, recovery_key, intent, expected_result, instant = (
                expected_payload
            )
            observed = mutations[sequence]
            if (
                observed[:3] != (operation, entity_key, recovery_key)
                or observed[3] != _json_bytes(intent)
                or observed[4] != _json_bytes(expected_result)
                or observed[5] != instant
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

        metadata = connection.execute(
            "SELECT mutation_count,mutation_head_sha256 "
            "FROM recorded_authorization_metadata WHERE singleton=1"
        ).fetchone()
        if (
            metadata is None
            or type(metadata[0]) is not int
            or metadata[0] != len(mutation_rows)
            or _sha(metadata[1]) != previous_mutation
        ):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

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
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
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
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        if count == anchor.count:
            if head != anchor.head:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            return
        if anchor.count == 0:
            if anchor.head != _GENESIS_DIGEST:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            return
        prefix = connection.execute(
            "SELECT mutation_sha256 FROM recorded_authorization_mutation "
            "WHERE sequence=?",
            (anchor.count,),
        ).fetchone()
        if prefix != (anchor.head,):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

    def _pin_process_state(self, *, count: int, head: str) -> None:
        anchor = self._process_anchor
        if anchor is None or count < anchor.count:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        if count == anchor.count and head != anchor.head:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        anchor.count = count
        anchor.head = head

    def _verified_state(
        self, connection: sqlite3.Connection, *, check_process: bool
    ) -> tuple[str, int]:
        self._validate_database_identity()
        self._verify_schema(connection)
        self._verify_integrity(connection)
        row = connection.execute(
            "SELECT mutation_head_sha256,mutation_count "
            "FROM recorded_authorization_metadata WHERE singleton=1"
        ).fetchone()
        if row is None or type(row[1]) is not int or row[1] < 0:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        head = _sha(row[0])
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

    def begin(self) -> RecordedAuthorizationUnitOfWork:
        _require_recorded_environment(self._environment)
        anchor = self._process_anchor
        if anchor is None:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        self._state_lock.acquire()
        anchor.lock.acquire()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect(verify=True)
            connection.execute("BEGIN IMMEDIATE")
            self._verified_state(connection, check_process=True)
        except AuthorizationRepositoryFailure:
            if connection is not None:
                self._rollback(connection)
                self._close_safely(connection)
            anchor.lock.release()
            self._state_lock.release()
            raise
        except sqlite3.Error:
            if connection is not None:
                self._rollback(connection)
                self._close_safely(connection)
            anchor.lock.release()
            self._state_lock.release()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return RecordedAuthorizationUnitOfWork(
            repository=self,
            connection=connection,
            release_locks=lambda: self._release_uow_locks(anchor),
        )

    def _release_uow_locks(self, anchor: _ProcessAnchor) -> None:
        anchor.lock.release()
        self._state_lock.release()

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=True)
            committed = False
            commit_attempted = False
            pending_head = _GENESIS_DIGEST
            pending_count = 0
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                pending_head, pending_count = self._verified_state(
                    connection, check_process=True
                )
                self.inject_commit_fault(RecordedAuthorizationCommitFault.BEFORE_COMMIT)
                commit_attempted = True
                try:
                    connection.commit()
                except sqlite3.Error:
                    if connection.in_transaction:
                        self._rollback(connection)
                        _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN)
                committed = True
                self._validate_database_identity()
                self._pin_process_state(count=pending_count, head=pending_head)
                self.inject_commit_fault(RecordedAuthorizationCommitFault.AFTER_COMMIT)
                return result
            except _InjectedCrash as error:
                if not committed:
                    self._rollback(connection)
                _fail(
                    AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                    if error.point is RecordedAuthorizationCommitFault.AFTER_COMMIT
                    else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
                )
            except AuthorizationRepositoryFailure:
                if not committed:
                    self._rollback(connection)
                raise
            except sqlite3.Error:
                if not committed:
                    self._rollback(connection)
                if commit_attempted and not connection.in_transaction:
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN)
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            except Exception:
                if not committed:
                    self._rollback(connection)
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            finally:
                self._close_safely(connection)

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        anchor = self._process_anchor
        if anchor is None:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        with self._state_lock, anchor.lock:
            connection = self._connect(verify=True)
            try:
                connection.execute("BEGIN")
                self._verified_state(connection, check_process=True)
                result = operation(connection)
                self._rollback(connection)
                return result
            except AuthorizationRepositoryFailure:
                self._rollback(connection)
                raise
            except sqlite3.Error:
                self._rollback(connection)
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            except Exception:
                self._rollback(connection)
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            finally:
                self._close_safely(connection)

    def install_policy(
        self, *, expected_revision: str, snapshot: PolicySnapshot
    ) -> None:
        _require_recorded_environment(self._environment)
        if type(snapshot) is not PolicySnapshot or snapshot.mode not in {
            PolicyMode.DISABLED,
            PolicyMode.RECORDED_TEST,
        }:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        expected = _text(expected_revision)
        document = _json_bytes(_policy_document(snapshot))
        exact_snapshot = _policy_from_document(_document(document))

        def operation(connection: sqlite3.Connection) -> None:
            current = connection.execute(
                "SELECT revision,record_sha256 FROM recorded_authorization_active_policy "
                "ORDER BY activation_sequence DESC LIMIT 1"
            ).fetchone()
            if (
                current is None
                or current[0] != expected
                or exact_snapshot.revision.value == expected
            ):
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            if (
                connection.execute(
                    "SELECT 1 FROM recorded_authorization_policy_snapshot WHERE revision=?",
                    (exact_snapshot.revision.value,),
                ).fetchone()
                is not None
            ):
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            metadata = connection.execute(
                "SELECT mutation_count FROM recorded_authorization_metadata WHERE singleton=1"
            ).fetchone()
            last_policy = connection.execute(
                "SELECT record_sha256 FROM recorded_authorization_policy_snapshot "
                "ORDER BY command_sequence DESC LIMIT 1"
            ).fetchone()
            last_activation = connection.execute(
                "SELECT activation_sequence,record_sha256 "
                "FROM recorded_authorization_active_policy "
                "ORDER BY activation_sequence DESC LIMIT 1"
            ).fetchone()
            if metadata is None or last_policy is None or last_activation is None:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            sequence = int(metadata[0]) + 1
            activation = int(last_activation[0]) + 1
            previous_policy = _sha(last_policy[0])
            previous_activation = _sha(last_activation[1])
            policy_record = _record_hash(
                "POLICY",
                (
                    exact_snapshot.revision.value,
                    _blob_sha256(document),
                    exact_snapshot.fingerprint,
                    sequence,
                    previous_policy,
                ),
            )
            activation_record = _record_hash(
                "POLICY_ACTIVATION",
                (
                    activation,
                    exact_snapshot.revision.value,
                    expected,
                    sequence,
                    previous_activation,
                ),
            )
            inserted = self._insert_mutation(
                connection,
                operation="INSTALL_POLICY",
                entity_key="POLICY",
                recovery_key=None,
                intent={
                    "expected_revision": expected,
                    "snapshot": _document(document),
                },
                result={
                    "activation_record_sha256": activation_record,
                    "fingerprint": exact_snapshot.fingerprint,
                    "policy_record_sha256": policy_record,
                    "revision": exact_snapshot.revision.value,
                },
                committed_at=_SYNTHETIC_MANAGEMENT_INSTANT,
            )
            if inserted != sequence:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            try:
                connection.execute(
                    "INSERT INTO recorded_authorization_policy_snapshot VALUES (?,?,?,?,?,?)",
                    (
                        exact_snapshot.revision.value,
                        document,
                        exact_snapshot.fingerprint,
                        sequence,
                        previous_policy,
                        policy_record,
                    ),
                )
                connection.execute(
                    "INSERT INTO recorded_authorization_active_policy VALUES (?,?,?,?,?,?)",
                    (
                        activation,
                        exact_snapshot.revision.value,
                        expected,
                        sequence,
                        previous_activation,
                        activation_record,
                    ),
                )
            except sqlite3.IntegrityError:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)

        self._write(operation)

    def install_entitlements(
        self,
        *,
        principal: PrincipalIdentity,
        expected_revision: str | None,
        snapshot: EntitlementSnapshot,
    ) -> None:
        _require_recorded_environment(self._environment)
        if (
            type(principal) is not PrincipalIdentity
            or type(snapshot) is not EntitlementSnapshot
            or snapshot.principal != principal
        ):
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        expected = None if expected_revision is None else _text(expected_revision)
        document = _json_bytes(_entitlement_document(snapshot))
        exact_snapshot = _entitlement_from_document(
            _document(document), principal=principal
        )
        principal_fingerprint = exact_snapshot.principal.fingerprint

        def operation(connection: sqlite3.Connection) -> None:
            current = connection.execute(
                "SELECT revision,record_sha256 "
                "FROM recorded_authorization_active_entitlement "
                "WHERE principal_fingerprint=? ORDER BY activation_sequence DESC LIMIT 1",
                (principal_fingerprint,),
            ).fetchone()
            if (None if current is None else current[0]) != expected:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            if expected == exact_snapshot.revision.value:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            if (
                connection.execute(
                    "SELECT 1 FROM recorded_authorization_entitlement_snapshot "
                    "WHERE principal_fingerprint=? AND revision=?",
                    (principal_fingerprint, exact_snapshot.revision.value),
                ).fetchone()
                is not None
            ):
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            metadata = connection.execute(
                "SELECT mutation_count FROM recorded_authorization_metadata WHERE singleton=1"
            ).fetchone()
            last_snapshot = connection.execute(
                "SELECT record_sha256 FROM recorded_authorization_entitlement_snapshot "
                "WHERE principal_fingerprint=? ORDER BY command_sequence DESC LIMIT 1",
                (principal_fingerprint,),
            ).fetchone()
            last_activation = connection.execute(
                "SELECT activation_sequence,record_sha256 "
                "FROM recorded_authorization_active_entitlement "
                "WHERE principal_fingerprint=? ORDER BY activation_sequence DESC LIMIT 1",
                (principal_fingerprint,),
            ).fetchone()
            last_global_activation = connection.execute(
                "SELECT activation_sequence FROM recorded_authorization_active_entitlement "
                "ORDER BY activation_sequence DESC LIMIT 1"
            ).fetchone()
            if metadata is None:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            sequence = int(metadata[0]) + 1
            activation = (
                1
                if last_global_activation is None
                else int(last_global_activation[0]) + 1
            )
            previous_snapshot = (
                _GENESIS_DIGEST if last_snapshot is None else _sha(last_snapshot[0])
            )
            previous_activation = (
                _GENESIS_DIGEST if last_activation is None else _sha(last_activation[1])
            )
            snapshot_record = _record_hash(
                "ENTITLEMENT",
                (
                    principal_fingerprint,
                    exact_snapshot.revision.value,
                    _blob_sha256(document),
                    sequence,
                    previous_snapshot,
                ),
            )
            activation_record = _record_hash(
                "ENTITLEMENT_ACTIVATION",
                (
                    activation,
                    principal_fingerprint,
                    exact_snapshot.revision.value,
                    expected,
                    sequence,
                    previous_activation,
                ),
            )
            inserted = self._insert_mutation(
                connection,
                operation="INSTALL_ENTITLEMENTS",
                entity_key=principal_fingerprint,
                recovery_key=None,
                intent={
                    "expected_revision": expected,
                    "principal_fingerprint": principal_fingerprint,
                    "snapshot": _document(document),
                },
                result={
                    "activation_record_sha256": activation_record,
                    "entitlement_record_sha256": snapshot_record,
                    "principal_fingerprint": principal_fingerprint,
                    "revision": exact_snapshot.revision.value,
                },
                committed_at=_SYNTHETIC_MANAGEMENT_INSTANT,
            )
            if inserted != sequence:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            try:
                connection.execute(
                    "INSERT INTO recorded_authorization_entitlement_snapshot "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        principal_fingerprint,
                        exact_snapshot.revision.value,
                        document,
                        sequence,
                        previous_snapshot,
                        snapshot_record,
                    ),
                )
                connection.execute(
                    "INSERT INTO recorded_authorization_active_entitlement "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        activation,
                        principal_fingerprint,
                        exact_snapshot.revision.value,
                        expected,
                        sequence,
                        previous_activation,
                        activation_record,
                    ),
                )
            except sqlite3.IntegrityError:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)

        self._write(operation)

    def append_independent_actor_evidence(
        self, evidence: IndependentActorEvidence
    ) -> None:
        _require_recorded_environment(self._environment)
        document = _json_bytes(_evidence_document(evidence))
        exact_evidence = _evidence_from_document(_document(document))

        def operation(connection: sqlite3.Connection) -> None:
            existing = connection.execute(
                "SELECT evidence_id,document,fingerprint "
                "FROM recorded_authorization_sod_evidence WHERE evidence_id=?",
                (str(exact_evidence.evidence_id),),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (
                    str(exact_evidence.evidence_id),
                    document,
                    exact_evidence.fingerprint,
                ):
                    _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
                return
            metadata = connection.execute(
                "SELECT mutation_count FROM recorded_authorization_metadata WHERE singleton=1"
            ).fetchone()
            last = connection.execute(
                "SELECT record_sha256 FROM recorded_authorization_sod_evidence "
                "ORDER BY command_sequence DESC LIMIT 1"
            ).fetchone()
            if metadata is None:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            sequence = int(metadata[0]) + 1
            previous = _GENESIS_DIGEST if last is None else _sha(last[0])
            record = _record_hash(
                "SOD_EVIDENCE",
                (
                    str(exact_evidence.evidence_id),
                    _blob_sha256(document),
                    exact_evidence.fingerprint,
                    sequence,
                    previous,
                ),
            )
            inserted = self._insert_mutation(
                connection,
                operation="APPEND_SOD_EVIDENCE",
                entity_key=str(exact_evidence.evidence_id),
                recovery_key=None,
                intent={"evidence": _document(document)},
                result={
                    "evidence_id": str(exact_evidence.evidence_id),
                    "evidence_record_sha256": record,
                    "fingerprint": exact_evidence.fingerprint,
                },
                committed_at=exact_evidence.recorded_at,
            )
            if inserted != sequence:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            connection.execute(
                "INSERT INTO recorded_authorization_sod_evidence VALUES (?,?,?,?,?,?)",
                (
                    str(exact_evidence.evidence_id),
                    document,
                    exact_evidence.fingerprint,
                    sequence,
                    previous,
                    record,
                ),
            )

        self._write(operation)

    def recover(self, command_id: AuthorizationCommandId) -> AuthorizationCommandResult:
        _require_recorded_environment(self._environment)
        if type(command_id) is not AuthorizationCommandId:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_UNKNOWN)

        def operation(connection: sqlite3.Connection) -> AuthorizationCommandResult:
            fingerprint = hashlib.sha256(command_id.value.encode("ascii")).hexdigest()
            row = connection.execute(
                "SELECT command_id,result_document FROM recorded_authorization_command "
                "WHERE command_fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if row is None or row[0] != command_id.value:
                _fail(AuthorizationRepositoryFailureCode.COMMAND_UNKNOWN)
            return _result_from_document(_document(row[1]))

        return self._read(operation)

    def audit_snapshot(self) -> tuple[AuthorizationAuditRecord, ...]:
        def operation(
            connection: sqlite3.Connection,
        ) -> tuple[AuthorizationAuditRecord, ...]:
            rows = connection.execute(
                "SELECT result_document FROM recorded_authorization_command "
                "ORDER BY command_sequence"
            ).fetchall()
            return tuple(_result_from_document(_document(row[0])).audit for row in rows)

        return self._read(operation)

    def __repr__(self) -> str:
        return "RecordedSqliteAuthorizationRepository(<owner-private>)"


@final
class RecordedAuthorizationUnitOfWork:
    """One explicit SQLite transaction; no collaborator calls occur inside it."""

    __slots__ = (
        "_closed",
        "_connection",
        "_release_locks",
        "_repository",
    )

    def __init__(
        self,
        *,
        repository: RecordedSqliteAuthorizationRepository,
        connection: sqlite3.Connection,
        release_locks: Callable[[], None],
    ) -> None:
        self._repository = repository
        self._connection = connection
        self._release_locks = release_locks
        self._closed = False

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return self._connection

    def _finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._repository._close_safely(self._connection)  # pyright: ignore[reportPrivateUsage]
        self._release_locks()

    def load_command(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
    ) -> AuthorizationCommandResult | None:
        connection = self._require_open()
        expected_digest = _sha(request_digest)
        fingerprint = hashlib.sha256(command_id.value.encode("ascii")).hexdigest()
        row = connection.execute(
            "SELECT command_id,request_digest,result_document "
            "FROM recorded_authorization_command "
            "WHERE command_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != command_id.value or _sha(row[1]) != expected_digest:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_CONFLICT)
        result = _result_from_document(_document(row[2]))
        if result.command_id != command_id or result.request_digest != expected_digest:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        return result

    def load_policy(self) -> PolicySnapshot:
        connection = self._require_open()
        row = connection.execute(
            "SELECT p.document "
            "FROM recorded_authorization_policy_snapshot p "
            "JOIN recorded_authorization_active_policy a ON a.revision=p.revision "
            "ORDER BY a.activation_sequence DESC LIMIT 1"
        ).fetchone()
        if row is None:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        return _policy_from_document(_document(row[0]))

    def load_entitlements(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        connection = self._require_open()
        if type(principal) is not PrincipalIdentity:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        row = connection.execute(
            "SELECT e.document "
            "FROM recorded_authorization_entitlement_snapshot e "
            "JOIN recorded_authorization_active_entitlement a "
            "ON a.principal_fingerprint=e.principal_fingerprint "
            "AND a.revision=e.revision WHERE e.principal_fingerprint=? "
            "ORDER BY a.activation_sequence DESC LIMIT 1",
            (principal.fingerprint,),
        ).fetchone()
        if row is None:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return _entitlement_from_document(_document(row[0]), principal=principal)

    def load_independent_actor_evidence(
        self, evidence_id: UUID
    ) -> IndependentActorEvidence | None:
        connection = self._require_open()
        if type(evidence_id) is not UUID or evidence_id.int == 0:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        row = connection.execute(
            "SELECT document "
            "FROM recorded_authorization_sod_evidence WHERE evidence_id=?",
            (str(evidence_id),),
        ).fetchone()
        if row is None:
            return None
        return _evidence_from_document(_document(row[0]))

    def record_decision(
        self,
        *,
        command_id: AuthorizationCommandId,
        request_digest: str,
        session_fingerprint: str,
        decision: AuthorizationDecision,
        occurred_at: datetime,
        step_up_receipt_fingerprint: str | None,
    ) -> AuthorizationCommandResult:
        connection = self._require_open()
        if (
            type(command_id) is not AuthorizationCommandId
            or type(decision) is not AuthorizationDecision
        ):
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        request_sha = _sha(request_digest)
        session_sha = _sha(session_fingerprint)
        receipt_sha = (
            None
            if step_up_receipt_fingerprint is None
            else _sha(step_up_receipt_fingerprint)
        )
        existing = self.load_command(command_id=command_id, request_digest=request_sha)
        if existing is not None:
            return existing
        exact_decision = _decision_from_document(
            _document(_json_bytes(_decision_document(decision)))
        )
        last = connection.execute(
            "SELECT sequence,digest FROM recorded_authorization_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        audit_sequence = 1 if last is None else int(last[0]) + 1
        previous = _GENESIS_DIGEST if last is None else _sha(last[1])
        command_fingerprint = hashlib.sha256(
            command_id.value.encode("ascii")
        ).hexdigest()
        instant = require_authorization_utc(occurred_at)
        digest = _audit_digest(
            sequence=audit_sequence,
            command_fingerprint=command_fingerprint,
            request_digest=request_sha,
            effect=exact_decision.effect,
            occurred_at=instant,
            previous_digest=previous,
        )
        audit = AuthorizationAuditRecord(
            sequence=audit_sequence,
            command_fingerprint=command_fingerprint,
            request_digest=request_sha,
            effect=exact_decision.effect,
            occurred_at=instant,
            previous_digest=previous,
            digest=digest,
        )
        result = AuthorizationCommandResult(
            command_id=command_id,
            request_digest=request_sha,
            session_fingerprint=session_sha,
            decision=exact_decision,
            audit=audit,
            step_up_receipt_fingerprint=receipt_sha,
        )
        metadata = connection.execute(
            "SELECT mutation_count FROM recorded_authorization_metadata WHERE singleton=1"
        ).fetchone()
        if metadata is None or type(metadata[0]) is not int:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        command_sequence = metadata[0] + 1
        intent: dict[str, object] = {
            "command_fingerprint": command_fingerprint,
            "command_id": command_id.value,
            "decision": _decision_document(exact_decision),
            "occurred_at": _utc_text(instant),
            "request_digest": request_sha,
            "session_fingerprint": session_sha,
            "step_up_receipt_fingerprint": receipt_sha,
        }
        intent_bytes = _json_bytes(intent)
        result_document = _json_bytes(_result_document(result))
        audit_record = _record_hash(
            "AUDIT",
            (
                audit.sequence,
                audit.command_fingerprint,
                audit.request_digest,
                audit.effect.value,
                _utc_text(audit.occurred_at),
                audit.previous_digest,
                audit.digest,
                command_sequence,
            ),
        )
        command_record = _record_hash(
            "COMMAND",
            (
                command_fingerprint,
                command_id.value,
                request_sha,
                _blob_sha256(intent_bytes),
                _blob_sha256(result_document),
                audit_sequence,
                command_sequence,
            ),
        )
        inserted = self._repository._insert_mutation(  # pyright: ignore[reportPrivateUsage]
            connection,
            operation="RECORD_DECISION",
            entity_key=command_fingerprint,
            recovery_key=command_fingerprint,
            intent=intent,
            result={
                "audit_record_sha256": audit_record,
                "command_record_sha256": command_record,
                "result": _document(result_document),
            },
            committed_at=instant,
        )
        if inserted != command_sequence:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        try:
            connection.execute(
                "INSERT INTO recorded_authorization_audit VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    audit.sequence,
                    audit.command_fingerprint,
                    audit.request_digest,
                    audit.effect.value,
                    _utc_text(audit.occurred_at),
                    audit.previous_digest,
                    audit.digest,
                    command_sequence,
                    audit_record,
                ),
            )
            connection.execute(
                "INSERT INTO recorded_authorization_command VALUES (?,?,?,?,?,?,?,?)",
                (
                    command_fingerprint,
                    command_id.value,
                    request_sha,
                    intent_bytes,
                    result_document,
                    audit_sequence,
                    command_sequence,
                    command_record,
                ),
            )
        except sqlite3.IntegrityError:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_CONFLICT)
        return _result_from_document(_document(result_document))

    def commit(self) -> None:
        connection = self._require_open()
        committed = False
        commit_attempted = False
        pending_head = _GENESIS_DIGEST
        pending_count = 0
        try:
            pending_head, pending_count = self._repository._verified_state(  # pyright: ignore[reportPrivateUsage]
                connection, check_process=True
            )
            self._repository.inject_commit_fault(
                RecordedAuthorizationCommitFault.BEFORE_COMMIT
            )
            commit_attempted = True
            try:
                connection.commit()
            except sqlite3.Error:
                if connection.in_transaction:
                    self._repository._rollback(connection)  # pyright: ignore[reportPrivateUsage]
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
                _fail(AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN)
            committed = True
            self._repository._validate_database_identity()  # pyright: ignore[reportPrivateUsage]
            self._repository._pin_process_state(  # pyright: ignore[reportPrivateUsage]
                count=pending_count, head=pending_head
            )
            self._repository.inject_commit_fault(
                RecordedAuthorizationCommitFault.AFTER_COMMIT
            )
        except _InjectedCrash as error:
            if not committed:
                self._repository._rollback(connection)  # pyright: ignore[reportPrivateUsage]
            self._finish()
            _fail(
                AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                if error.point is RecordedAuthorizationCommitFault.AFTER_COMMIT
                else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
            )
        except sqlite3.Error:
            if not committed:
                self._repository._rollback(connection)  # pyright: ignore[reportPrivateUsage]
            unknown = commit_attempted and not connection.in_transaction
            self._finish()
            _fail(
                AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                if unknown
                else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
            )
        except AuthorizationRepositoryFailure:
            if not committed:
                self._repository._rollback(connection)  # pyright: ignore[reportPrivateUsage]
            self._finish()
            raise
        except Exception:
            if not committed:
                self._repository._rollback(connection)  # pyright: ignore[reportPrivateUsage]
            self._finish()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        self._finish()

    def rollback(self) -> None:
        connection = self._require_open()
        try:
            connection.rollback()
        except sqlite3.Error:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            self._finish()

    def __enter__(self) -> NoReturn:
        _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

    def __exit__(self, *args: object) -> NoReturn:
        del args
        _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)


__all__ = [
    "RecordedAuthorizationCommitFault",
    "RecordedAuthorizationUnitOfWork",
    "RecordedSqliteAuthorizationRepository",
    "recorded_authorization_policy_snapshot",
]
