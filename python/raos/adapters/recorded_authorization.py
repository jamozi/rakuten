"""Owner-private durable ST-0403 policy, entitlement, and decision adapter.

Only exact ``ENV-DEV`` and ``ENV-CI`` recorded fixtures are admitted.  The
adapter performs no network or provider access and owns one SQLite transaction
per explicit unit of work.  Snapshot rows are immutable, active revisions use
compare-and-set, decision commands are idempotent, and audit rows form a
verified SHA-256 chain.
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


_DATABASE_NAME = "st0403-recorded-authorization.sqlite3"
_SCHEMA_VERSION = "ST0403_RECORDED_AUTHORIZATION_V1"
_GENESIS_DIGEST = "0" * 64
_SHA256 = frozenset("0123456789abcdef")
_SCHEMA_OBJECTS_SHA256 = (
    "b1edb7c9d2cdcf76129f787dc99fbe8795bc0231967a49dcb6f0df3cd57b8720"
)
_MAX_DOCUMENT_BYTES = 256 * 1024
_TABLES = frozenset(
    {
        "recorded_authorization_metadata",
        "recorded_authorization_policy_snapshot",
        "recorded_authorization_active_policy",
        "recorded_authorization_entitlement_snapshot",
        "recorded_authorization_active_entitlement",
        "recorded_authorization_sod_evidence",
        "recorded_authorization_audit",
        "recorded_authorization_command",
    }
)
_T = TypeVar("_T")


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
    text = _text(value, maximum=_MAX_DOCUMENT_BYTES)
    try:
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
    if _json_bytes(document).decode("ascii") != text:
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


def _row_digest(values: tuple[object, ...]) -> str:
    return _digest(("RAOS_ST0403_RECORDED_ROW_V1", *values))


def _schema_objects_digest(connection: sqlite3.Connection) -> str:
    raw_rows: object = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()
    if type(raw_rows) is not list:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    normalized: list[tuple[str, str, str, str]] = []
    for raw in cast(list[object], raw_rows):
        if type(raw) is not tuple:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        raw_values = cast(tuple[object, ...], raw)
        if len(raw_values) != 4 or any(type(value) is not str for value in raw_values):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        values = cast(tuple[str, str, str, str], raw_values)
        normalized.append(values)
    return hashlib.sha256(
        _json_bytes(("RAOS_ST0403_SQLITE_SCHEMA_V1", *normalized))
    ).hexdigest()


def _verified_row(row: object, *, count: int) -> tuple[object, ...]:
    if type(row) is not tuple:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    values_with_digest = cast(tuple[object, ...], row)
    if len(values_with_digest) != count + 1:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    values = values_with_digest[:count]
    digest = _sha(values_with_digest[count])
    if _row_digest(values) != digest:
        _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
    return values


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
    """Restartable recorded repository and explicit UoW factory."""

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
        self._private_root = self._validate_private_root(private_root)
        self._database_path = self._private_root / _DATABASE_NAME
        self._fault_once_at = fault_once_at
        self._fault_lock = Lock()
        self._create_or_validate_database_file()
        self._initialize_or_validate_schema()

    @staticmethod
    def _validate_private_root(value: object) -> Path:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        root = Path(os.path.abspath(value))
        descriptors: list[int] = []
        try:
            current = os.open(
                "/",
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            descriptors.append(current)
            metadata = os.fstat(current)
            for component in root.parts[1:]:
                named = os.stat(component, dir_fd=current, follow_symlinks=False)
                if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=current,
                )
                descriptors.append(child)
                opened = os.fstat(child)
                if (
                    opened.st_dev != named.st_dev
                    or opened.st_ino != named.st_ino
                    or opened.st_mode != named.st_mode
                ):
                    _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
                current = child
                metadata = opened
        except OSError:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return root

    def _validate_database_file(self) -> None:
        self._validate_private_root(self._private_root)
        try:
            metadata = self._database_path.lstat()
        except OSError:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

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
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
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
                _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
            return connection
        except AuthorizationRepositoryFailure:
            raise
        except sqlite3.Error:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)

    def _initialize_or_validate_schema(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_policy_snapshot (
                    revision TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_active_policy (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    revision TEXT NOT NULL REFERENCES recorded_authorization_policy_snapshot(revision),
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_entitlement_snapshot (
                    principal_fingerprint TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    document TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    PRIMARY KEY (principal_fingerprint, revision)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_active_entitlement (
                    principal_fingerprint TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    record_sha256 TEXT NOT NULL,
                    FOREIGN KEY (principal_fingerprint, revision)
                      REFERENCES recorded_authorization_entitlement_snapshot(principal_fingerprint, revision)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_sod_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_audit (
                    sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
                    command_fingerprint TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    effect TEXT NOT NULL CHECK (effect IN ('ALLOW','DENY')),
                    occurred_at TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    digest TEXT NOT NULL UNIQUE,
                    record_sha256 TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS recorded_authorization_command (
                    command_fingerprint TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    request_digest TEXT NOT NULL,
                    result_document TEXT NOT NULL,
                    audit_sequence INTEGER NOT NULL UNIQUE
                      REFERENCES recorded_authorization_audit(sequence),
                    record_sha256 TEXT NOT NULL
                )"""
            )
            metadata = connection.execute(
                "SELECT schema_version FROM recorded_authorization_metadata WHERE singleton=1"
            ).fetchone()
            if metadata is None:
                connection.execute(
                    "INSERT INTO recorded_authorization_metadata VALUES (1, ?)",
                    (_SCHEMA_VERSION,),
                )
            elif metadata != (_SCHEMA_VERSION,):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            active = connection.execute(
                "SELECT revision,record_sha256 "
                "FROM recorded_authorization_active_policy WHERE singleton=1"
            ).fetchone()
            if active is None:
                disabled = PolicySnapshot(
                    revision=PolicyRevision("TEST_ONLY:DISABLED"),
                    mode=PolicyMode.DISABLED,
                    rules=(),
                )
                document = _json_bytes(_policy_document(disabled)).decode("ascii")
                values = (
                    disabled.revision.value,
                    document,
                    disabled.fingerprint,
                )
                connection.execute(
                    "INSERT INTO recorded_authorization_policy_snapshot VALUES (?,?,?,?)",
                    (*values, _row_digest(values)),
                )
                active_values = (1, disabled.revision.value)
                connection.execute(
                    "INSERT INTO recorded_authorization_active_policy VALUES (?,?,?)",
                    (*active_values, _row_digest(active_values)),
                )
            tables = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            )
            if tables != _TABLES or connection.execute(
                "PRAGMA integrity_check"
            ).fetchone() != ("ok",):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            self._validate_all(connection)
            connection.commit()
        except AuthorizationRepositoryFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        except Exception:
            connection.rollback()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def inject_commit_fault(self, point: RecordedAuthorizationCommitFault) -> None:
        with self._fault_lock:
            if self._fault_once_at is point:
                self._fault_once_at = None
                raise _InjectedCrash(point)

    def _validate_all(self, connection: sqlite3.Connection) -> None:
        if _schema_objects_digest(connection) != _SCHEMA_OBJECTS_SHA256:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        policy_rows = connection.execute(
            "SELECT revision,document,fingerprint,record_sha256 "
            "FROM recorded_authorization_policy_snapshot ORDER BY revision"
        ).fetchall()
        for raw in policy_rows:
            revision, document, fingerprint = _verified_row(tuple(raw), count=3)
            policy = _policy_from_document(_document(document))
            if policy.revision.value != _text(revision) or policy.fingerprint != _sha(
                fingerprint
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        active_policy_rows = connection.execute(
            "SELECT singleton,revision,record_sha256 "
            "FROM recorded_authorization_active_policy ORDER BY singleton"
        ).fetchall()
        if len(active_policy_rows) != 1:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        active_singleton, active_policy_revision = _verified_row(
            tuple(active_policy_rows[0]), count=2
        )
        if active_singleton != 1 or _text(active_policy_revision) not in {
            _text(cast(tuple[object, ...], row)[0]) for row in policy_rows
        }:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        entitlement_rows = connection.execute(
            "SELECT principal_fingerprint,revision,document,record_sha256 "
            "FROM recorded_authorization_entitlement_snapshot "
            "ORDER BY principal_fingerprint,revision"
        ).fetchall()
        for raw in entitlement_rows:
            principal_fingerprint, revision, document = _verified_row(
                tuple(raw), count=3
            )
            row = _document(document)
            if _sha(principal_fingerprint) != _sha(
                row.get("principal_fingerprint")
            ) or _text(revision) != _text(row.get("revision")):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        active_entitlement_rows = connection.execute(
            "SELECT principal_fingerprint,revision,record_sha256 "
            "FROM recorded_authorization_active_entitlement "
            "ORDER BY principal_fingerprint"
        ).fetchall()
        entitlement_keys = {
            (
                _sha(cast(tuple[object, ...], row)[0]),
                _text(cast(tuple[object, ...], row)[1]),
            )
            for row in entitlement_rows
        }
        for raw in active_entitlement_rows:
            principal_fingerprint, revision = _verified_row(tuple(raw), count=2)
            if (_sha(principal_fingerprint), _text(revision)) not in entitlement_keys:
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        evidence_rows = connection.execute(
            "SELECT evidence_id,document,fingerprint,record_sha256 "
            "FROM recorded_authorization_sod_evidence ORDER BY evidence_id"
        ).fetchall()
        for raw in evidence_rows:
            evidence_id, document, fingerprint = _verified_row(tuple(raw), count=3)
            evidence = _evidence_from_document(_document(document))
            if str(evidence.evidence_id) != _text(
                evidence_id
            ) or evidence.fingerprint != _sha(fingerprint):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        previous = _GENESIS_DIGEST
        expected_sequence = 1
        audit_by_sequence: dict[int, AuthorizationAuditRecord] = {}
        audit_rows = connection.execute(
            "SELECT sequence,command_fingerprint,request_digest,effect,occurred_at,"
            "previous_digest,digest,record_sha256 FROM recorded_authorization_audit "
            "ORDER BY sequence"
        ).fetchall()
        for raw in audit_rows:
            values = _verified_row(tuple(raw), count=7)
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
            if audit.previous_digest != previous or audit.digest != _audit_digest(
                sequence=audit.sequence,
                command_fingerprint=audit.command_fingerprint,
                request_digest=audit.request_digest,
                effect=audit.effect,
                occurred_at=audit.occurred_at,
                previous_digest=audit.previous_digest,
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
            audit_by_sequence[sequence] = audit
            previous = audit.digest
            expected_sequence += 1
        command_rows = connection.execute(
            "SELECT command_fingerprint,command_id,request_digest,result_document,"
            "audit_sequence,record_sha256 FROM recorded_authorization_command "
            "ORDER BY command_fingerprint"
        ).fetchall()
        if len(command_rows) != len(audit_rows):
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        for raw in command_rows:
            values = _verified_row(tuple(raw), count=5)
            command_fingerprint = _sha(values[0])
            command_id = AuthorizationCommandId(_text(values[1]))
            request_digest = _sha(values[2])
            result = _result_from_document(_document(values[3]))
            sequence = values[4]
            if (
                type(sequence) is not int
                or sequence not in audit_by_sequence
                or result.audit != audit_by_sequence[sequence]
                or result.command_id != command_id
                or result.command_id_fingerprint != command_fingerprint
                or result.request_digest != request_digest
            ):
                _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)

    def begin(self) -> RecordedAuthorizationUnitOfWork:
        _require_recorded_environment(self._environment)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection)
        except AuthorizationRepositoryFailure:
            connection.rollback()
            connection.close()
            raise
        except sqlite3.Error:
            connection.close()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return RecordedAuthorizationUnitOfWork(repository=self, connection=connection)

    def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        connection = self._connect()
        committed = False
        commit_started = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection)
            result = operation(connection)
            self.inject_commit_fault(RecordedAuthorizationCommitFault.BEFORE_COMMIT)
            commit_started = True
            connection.commit()
            committed = True
            self.inject_commit_fault(RecordedAuthorizationCommitFault.AFTER_COMMIT)
            return result
        except _InjectedCrash as error:
            if not committed:
                connection.rollback()
            _fail(
                AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                if error.point is RecordedAuthorizationCommitFault.AFTER_COMMIT
                else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
            )
        except AuthorizationRepositoryFailure:
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
                AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
            )
        except Exception:
            if not committed:
                connection.rollback()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

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
        document = _json_bytes(_policy_document(snapshot)).decode("ascii")
        values = (snapshot.revision.value, document, snapshot.fingerprint)

        def operation(connection: sqlite3.Connection) -> None:
            current = connection.execute(
                "SELECT revision,record_sha256 "
                "FROM recorded_authorization_active_policy WHERE singleton=1"
            ).fetchone()
            expected_active_values = (1, expected)
            expected_active_sha = _row_digest(expected_active_values)
            if (
                current != (expected, expected_active_sha)
                or snapshot.revision.value == expected
            ):
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            try:
                connection.execute(
                    "INSERT INTO recorded_authorization_policy_snapshot VALUES (?,?,?,?)",
                    (*values, _row_digest(values)),
                )
            except sqlite3.IntegrityError:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            next_active_values = (1, snapshot.revision.value)
            cursor = connection.execute(
                "UPDATE recorded_authorization_active_policy "
                "SET revision=?,record_sha256=? "
                "WHERE singleton=1 AND revision=? AND record_sha256=?",
                (
                    snapshot.revision.value,
                    _row_digest(next_active_values),
                    expected,
                    expected_active_sha,
                ),
            )
            if cursor.rowcount != 1:
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
        document = _json_bytes(_entitlement_document(snapshot)).decode("ascii")
        values = (principal.fingerprint, snapshot.revision.value, document)

        def operation(connection: sqlite3.Connection) -> None:
            current = connection.execute(
                "SELECT revision,record_sha256 "
                "FROM recorded_authorization_active_entitlement "
                "WHERE principal_fingerprint=?",
                (principal.fingerprint,),
            ).fetchone()
            expected_active_values = (
                None if expected is None else (principal.fingerprint, expected)
            )
            expected_current = (
                None
                if expected_active_values is None
                else (
                    expected,
                    _row_digest(expected_active_values),
                )
            )
            if current != expected_current:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            if expected == snapshot.revision.value:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            try:
                connection.execute(
                    "INSERT INTO recorded_authorization_entitlement_snapshot "
                    "VALUES (?,?,?,?)",
                    (*values, _row_digest(values)),
                )
                if expected is None:
                    next_active_values = (
                        principal.fingerprint,
                        snapshot.revision.value,
                    )
                    connection.execute(
                        "INSERT INTO recorded_authorization_active_entitlement "
                        "VALUES (?,?,?)",
                        (*next_active_values, _row_digest(next_active_values)),
                    )
                else:
                    next_active_values = (
                        principal.fingerprint,
                        snapshot.revision.value,
                    )
                    cursor = connection.execute(
                        "UPDATE recorded_authorization_active_entitlement "
                        "SET revision=?,record_sha256=? "
                        "WHERE principal_fingerprint=? AND revision=? "
                        "AND record_sha256=?",
                        (
                            snapshot.revision.value,
                            _row_digest(next_active_values),
                            principal.fingerprint,
                            expected,
                            _row_digest((principal.fingerprint, expected)),
                        ),
                    )
                    if cursor.rowcount != 1:
                        _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
            except sqlite3.IntegrityError:
                _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)

        self._write(operation)

    def append_independent_actor_evidence(
        self, evidence: IndependentActorEvidence
    ) -> None:
        _require_recorded_environment(self._environment)
        document = _json_bytes(_evidence_document(evidence)).decode("ascii")
        values = (str(evidence.evidence_id), document, evidence.fingerprint)

        def operation(connection: sqlite3.Connection) -> None:
            existing = connection.execute(
                "SELECT evidence_id,document,fingerprint,record_sha256 "
                "FROM recorded_authorization_sod_evidence WHERE evidence_id=?",
                (str(evidence.evidence_id),),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (*values, _row_digest(values)):
                    _fail(AuthorizationRepositoryFailureCode.REVISION_CONFLICT)
                return
            connection.execute(
                "INSERT INTO recorded_authorization_sod_evidence VALUES (?,?,?,?)",
                (*values, _row_digest(values)),
            )

        self._write(operation)

    def recover(self, command_id: AuthorizationCommandId) -> AuthorizationCommandResult:
        _require_recorded_environment(self._environment)
        if type(command_id) is not AuthorizationCommandId:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_UNKNOWN)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection)
            fingerprint = hashlib.sha256(command_id.value.encode("ascii")).hexdigest()
            row = connection.execute(
                "SELECT command_fingerprint,command_id,request_digest,result_document,"
                "audit_sequence,record_sha256 FROM recorded_authorization_command "
                "WHERE command_fingerprint=?",
                (fingerprint,),
            ).fetchone()
            if row is None:
                _fail(AuthorizationRepositoryFailureCode.COMMAND_UNKNOWN)
            values = _verified_row(tuple(row), count=5)
            result = _result_from_document(_document(values[3]))
            connection.commit()
            return result
        except AuthorizationRepositoryFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def audit_snapshot(self) -> tuple[AuthorizationAuditRecord, ...]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._validate_all(connection)
            rows = connection.execute(
                "SELECT result_document FROM recorded_authorization_command "
                "ORDER BY audit_sequence"
            ).fetchall()
            result = tuple(
                _result_from_document(_document(row[0])).audit for row in rows
            )
            connection.commit()
            return result
        except AuthorizationRepositoryFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            connection.close()

    def __repr__(self) -> str:
        return "RecordedSqliteAuthorizationRepository(<owner-private>)"


@final
class RecordedAuthorizationUnitOfWork:
    """One explicit SQLite transaction; no collaborator calls occur inside it."""

    def __init__(
        self,
        *,
        repository: RecordedSqliteAuthorizationRepository,
        connection: sqlite3.Connection,
    ) -> None:
        self._repository = repository
        self._connection = connection
        self._closed = False

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        return self._connection

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
            "SELECT command_fingerprint,command_id,request_digest,result_document,"
            "audit_sequence,record_sha256 FROM recorded_authorization_command "
            "WHERE command_fingerprint=?",
            (fingerprint,),
        ).fetchone()
        if row is None:
            return None
        values = _verified_row(tuple(row), count=5)
        if _sha(values[2]) != expected_digest:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_CONFLICT)
        return _result_from_document(_document(values[3]))

    def load_policy(self) -> PolicySnapshot:
        connection = self._require_open()
        row = connection.execute(
            "SELECT p.revision,p.document,p.fingerprint,p.record_sha256 "
            "FROM recorded_authorization_policy_snapshot p "
            "JOIN recorded_authorization_active_policy a ON a.revision=p.revision "
            "WHERE a.singleton=1"
        ).fetchone()
        if row is None:
            _fail(AuthorizationRepositoryFailureCode.TAMPER_DETECTED)
        values = _verified_row(tuple(row), count=3)
        return _policy_from_document(_document(values[1]))

    def load_entitlements(self, principal: PrincipalIdentity) -> EntitlementSnapshot:
        connection = self._require_open()
        if type(principal) is not PrincipalIdentity:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        row = connection.execute(
            "SELECT e.principal_fingerprint,e.revision,e.document,e.record_sha256 "
            "FROM recorded_authorization_entitlement_snapshot e "
            "JOIN recorded_authorization_active_entitlement a "
            "ON a.principal_fingerprint=e.principal_fingerprint "
            "AND a.revision=e.revision WHERE e.principal_fingerprint=?",
            (principal.fingerprint,),
        ).fetchone()
        if row is None:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        values = _verified_row(tuple(row), count=3)
        return _entitlement_from_document(_document(values[2]), principal=principal)

    def load_independent_actor_evidence(
        self, evidence_id: UUID
    ) -> IndependentActorEvidence | None:
        connection = self._require_open()
        if type(evidence_id) is not UUID or evidence_id.int == 0:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        row = connection.execute(
            "SELECT evidence_id,document,fingerprint,record_sha256 "
            "FROM recorded_authorization_sod_evidence WHERE evidence_id=?",
            (str(evidence_id),),
        ).fetchone()
        if row is None:
            return None
        values = _verified_row(tuple(row), count=3)
        return _evidence_from_document(_document(values[1]))

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
        last = connection.execute(
            "SELECT sequence,digest FROM recorded_authorization_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if last is None else int(last[0]) + 1
        previous = _GENESIS_DIGEST if last is None else _sha(last[1])
        command_fingerprint = hashlib.sha256(
            command_id.value.encode("ascii")
        ).hexdigest()
        instant = require_authorization_utc(occurred_at)
        digest = _audit_digest(
            sequence=sequence,
            command_fingerprint=command_fingerprint,
            request_digest=request_sha,
            effect=decision.effect,
            occurred_at=instant,
            previous_digest=previous,
        )
        audit = AuthorizationAuditRecord(
            sequence=sequence,
            command_fingerprint=command_fingerprint,
            request_digest=request_sha,
            effect=decision.effect,
            occurred_at=instant,
            previous_digest=previous,
            digest=digest,
        )
        result = AuthorizationCommandResult(
            command_id=command_id,
            request_digest=request_sha,
            session_fingerprint=session_sha,
            decision=decision,
            audit=audit,
            step_up_receipt_fingerprint=receipt_sha,
        )
        audit_values = (
            sequence,
            command_fingerprint,
            request_sha,
            decision.effect.value,
            _utc_text(instant),
            previous,
            digest,
        )
        result_document = _json_bytes(_result_document(result)).decode("ascii")
        command_values = (
            command_fingerprint,
            command_id.value,
            request_sha,
            result_document,
            sequence,
        )
        try:
            connection.execute(
                "INSERT INTO recorded_authorization_audit VALUES (?,?,?,?,?,?,?,?)",
                (*audit_values, _row_digest(audit_values)),
            )
            connection.execute(
                "INSERT INTO recorded_authorization_command VALUES (?,?,?,?,?,?)",
                (*command_values, _row_digest(command_values)),
            )
        except sqlite3.IntegrityError:
            _fail(AuthorizationRepositoryFailureCode.COMMAND_CONFLICT)
        return result

    def commit(self) -> None:
        connection = self._require_open()
        committed = False
        try:
            self._repository.inject_commit_fault(
                RecordedAuthorizationCommitFault.BEFORE_COMMIT
            )
            connection.commit()
            committed = True
            self._repository.inject_commit_fault(
                RecordedAuthorizationCommitFault.AFTER_COMMIT
            )
        except _InjectedCrash as error:
            if not committed:
                connection.rollback()
            self._closed = True
            connection.close()
            _fail(
                AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN
                if error.point is RecordedAuthorizationCommitFault.AFTER_COMMIT
                else AuthorizationRepositoryFailureCode.STORAGE_FAILURE
            )
        except sqlite3.Error:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            self._closed = True
            connection.close()
            _fail(AuthorizationRepositoryFailureCode.STORAGE_COMMIT_UNKNOWN)
        self._closed = True
        connection.close()

    def rollback(self) -> None:
        connection = self._require_open()
        try:
            connection.rollback()
        except sqlite3.Error:
            _fail(AuthorizationRepositoryFailureCode.STORAGE_FAILURE)
        finally:
            self._closed = True
            connection.close()

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
