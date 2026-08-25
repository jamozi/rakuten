"""Concrete aggregate-specific SQLAlchemy repositories for IAM (ST-0308)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar, cast
from uuid import UUID

from sqlalchemy import Table, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

import raos.adapters.persistence.sqlalchemy.mappers.iam as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    guard_repository_class,
    persistence_context,
)
from raos.domain.iam.aggregates import (
    BreakGlassRecord,
    Permission,
    Principal,
    PrincipalRoleAssignment,
    PrincipalRoleAssignmentRecord,
    PrincipalState,
    Role,
    ServicePrincipal,
    SessionRevocation,
    UserAccount,
)
from raos.domain.iam.enums import (
    PermissionRiskLevel,
    PermissionStatus,
    PrincipalPrincipalType,
    PrincipalRoleAssignmentScopeType,
    PrincipalStatus,
    RoleStatus,
    ServicePrincipalAllowedEnvironment,
)
from raos.domain.iam.ids import (
    BreakGlassRecordId,
    PermissionId,
    PrincipalId,
    PrincipalRoleAssignmentId,
    RoleId,
    SessionRevocationId,
)
from raos.domain.iam.values import (
    BreakGlassRecordPermissionsJson,
)
from raos.domain.ops.ids import (
    IncidentId,
)
from raos.domain.shared.identity import (
    ScopeId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    EmailAddress,
)
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.domain.shared.persistence import Sha256Digest, UriReference, YenMinor
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode

T = TypeVar("T")
RowData = Mapping[str, object] | RowMapping


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = cast(object, TABLES_BY_RELATION[relation])
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(table, Table):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return table


def _exact(row: RowData, key: str, expected: type[T]) -> T:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _optional(row: RowData, key: str, expected: type[T]) -> T | None:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if value is None:
        return None
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: RowData, key: str) -> FrozenJsonObject:
    value = cast(dict[str, object], _exact(row, key, dict))
    try:
        return FrozenJsonObject.from_mapping(value)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_scalar(value: object) -> object:
    if value is None or type(value) in {str, int, bool, Decimal, date}:
        return value
    if isinstance(value, EntityId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    if isinstance(
        value,
        (AggregateVersion, YenMinor, Sha256Digest, EmailAddress, UriReference),
    ):
        return value.value
    if isinstance(value, BreakGlassRecordPermissionsJson):
        return json.loads(canonical_json_bytes(value.value))
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encoded(columns: tuple[str, ...], values: tuple[object, ...]) -> dict[str, object]:
    if len(columns) != len(values):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return {
        column: _encode_scalar(value)
        for column, value in zip(columns, values, strict=True)
    }


def _execute_one(session: Session, statement: Executable) -> RowMapping | None:
    try:
        return session.execute(statement).mappings().one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _execute(session: Session, statement: Executable) -> None:
    try:
        session.execute(statement)
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_iam_break_glass_record(row: RowData) -> BreakGlassRecord:
    try:
        return domain_mappers.map_iam_break_glass_record_from_row(
            id=BreakGlassRecordId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            principal_id=PrincipalId(_exact(row, "principal_id", UUID)),
            incident_id=IncidentId(_exact(row, "incident_id", UUID)),
            reason=_exact(row, "reason", str),
            approved_by_principal_id=PrincipalId(
                _exact(row, "approved_by_principal_id", UUID)
            ),
            permissions=BreakGlassRecordPermissionsJson(
                _json_object(row, "permissions")
            ),
            started_at=AwareUtcDateTime(_exact(row, "started_at", datetime)),
            expires_at=AwareUtcDateTime(_exact(row, "expires_at", datetime)),
            ended_at=(
                None
                if row.get("ended_at") is None
                else AwareUtcDateTime(_exact(row, "ended_at", datetime))
            ),
            end_reason=_optional(row, "end_reason", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_break_glass_record(value: BreakGlassRecord) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "principal_id",
            "incident_id",
            "reason",
            "approved_by_principal_id",
            "permissions",
            "started_at",
            "expires_at",
            "ended_at",
            "end_reason",
            "created_at",
        ),
        domain_mappers.map_iam_break_glass_record_to_row(value),
    )


def _decode_iam_permission(row: RowData) -> Permission:
    try:
        return domain_mappers.map_iam_permission_from_row(
            id=PermissionId(_exact(row, "id", UUID)),
            permission_code=_exact(row, "permission_code", str),
            description=_exact(row, "description", str),
            risk_level=PermissionRiskLevel(_exact(row, "risk_level", str)),
            status=PermissionStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_iam_principal(row: RowData) -> PrincipalState:
    try:
        return domain_mappers.map_iam_principal_from_row(
            id=PrincipalId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            principal_type=PrincipalPrincipalType(_exact(row, "principal_type", str)),
            status=PrincipalStatus(_exact(row, "status", str)),
            display_name=_exact(row, "display_name", str),
            deactivated_at=(
                None
                if row.get("deactivated_at") is None
                else AwareUtcDateTime(_exact(row, "deactivated_at", datetime))
            ),
            deactivation_reason=_optional(row, "deactivation_reason", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_principal(value: PrincipalState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "principal_type",
            "status",
            "display_name",
            "deactivated_at",
            "deactivation_reason",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_iam_principal_to_row(value),
    )


def _decode_iam_principal_role_assignment(
    row: RowData,
) -> PrincipalRoleAssignmentRecord:
    try:
        return domain_mappers.map_iam_principal_role_assignment_from_row(
            id=PrincipalRoleAssignmentId(_exact(row, "id", UUID)),
            principal_id=PrincipalId(_exact(row, "principal_id", UUID)),
            role_id=RoleId(_exact(row, "role_id", UUID)),
            scope_type=PrincipalRoleAssignmentScopeType(_exact(row, "scope_type", str)),
            scope_id=(
                None
                if row.get("scope_id") is None
                else ScopeId(_exact(row, "scope_id", UUID))
            ),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row.get("valid_to") is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            assigned_by_principal_id=PrincipalId(
                _exact(row, "assigned_by_principal_id", UUID)
            ),
            assignment_reason=_exact(row, "assignment_reason", str),
            revoked_at=(
                None
                if row.get("revoked_at") is None
                else AwareUtcDateTime(_exact(row, "revoked_at", datetime))
            ),
            revoked_by_principal_id=(
                None
                if row.get("revoked_by_principal_id") is None
                else PrincipalId(_exact(row, "revoked_by_principal_id", UUID))
            ),
            revocation_reason=_optional(row, "revocation_reason", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_principal_role_assignment(
    value: PrincipalRoleAssignmentRecord,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "principal_id",
            "role_id",
            "scope_type",
            "scope_id",
            "valid_from",
            "valid_to",
            "assigned_by_principal_id",
            "assignment_reason",
            "revoked_at",
            "revoked_by_principal_id",
            "revocation_reason",
            "created_at",
        ),
        domain_mappers.map_iam_principal_role_assignment_to_row(value),
    )


def _decode_iam_role(row: RowData) -> Role:
    try:
        return domain_mappers.map_iam_role_from_row(
            id=RoleId(_exact(row, "id", UUID)),
            role_code=_exact(row, "role_code", str),
            name=_exact(row, "name", str),
            description=_exact(row, "description", str),
            is_system_role=_exact(row, "is_system_role", bool),
            status=RoleStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_iam_service_principal(row: RowData) -> ServicePrincipal:
    try:
        return domain_mappers.map_iam_service_principal_from_row(
            principal_id=PrincipalId(_exact(row, "principal_id", UUID)),
            service_code=_exact(row, "service_code", str),
            workload_identity=_exact(row, "workload_identity", str),
            allowed_environment=ServicePrincipalAllowedEnvironment(
                _exact(row, "allowed_environment", str)
            ),
            credential_rotated_at=(
                None
                if row.get("credential_rotated_at") is None
                else AwareUtcDateTime(_exact(row, "credential_rotated_at", datetime))
            ),
            last_used_at=(
                None
                if row.get("last_used_at") is None
                else AwareUtcDateTime(_exact(row, "last_used_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_service_principal(value: ServicePrincipal) -> dict[str, object]:
    return _encoded(
        (
            "principal_id",
            "service_code",
            "workload_identity",
            "allowed_environment",
            "credential_rotated_at",
            "last_used_at",
            "created_at",
        ),
        domain_mappers.map_iam_service_principal_to_row(value),
    )


def _decode_iam_session_revocation(row: RowData) -> SessionRevocation:
    try:
        return domain_mappers.map_iam_session_revocation_from_row(
            id=SessionRevocationId(_exact(row, "id", UUID)),
            principal_id=PrincipalId(_exact(row, "principal_id", UUID)),
            oidc_issuer=_exact(row, "oidc_issuer", str),
            oidc_subject=_exact(row, "oidc_subject", str),
            revoke_before=AwareUtcDateTime(_exact(row, "revoke_before", datetime)),
            reason=_exact(row, "reason", str),
            created_by_principal_id=PrincipalId(
                _exact(row, "created_by_principal_id", UUID)
            ),
            expires_at=(
                None
                if row.get("expires_at") is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_session_revocation(value: SessionRevocation) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "principal_id",
            "oidc_issuer",
            "oidc_subject",
            "revoke_before",
            "reason",
            "created_by_principal_id",
            "expires_at",
            "created_at",
        ),
        domain_mappers.map_iam_session_revocation_to_row(value),
    )


def _decode_iam_user_account(row: RowData) -> UserAccount:
    try:
        return domain_mappers.map_iam_user_account_from_row(
            principal_id=PrincipalId(_exact(row, "principal_id", UUID)),
            oidc_issuer=_exact(row, "oidc_issuer", str),
            oidc_subject=_exact(row, "oidc_subject", str),
            email=(
                None
                if row.get("email") is None
                else EmailAddress(_exact(row, "email", str))
            ),
            email_verified=_exact(row, "email_verified", bool),
            mfa_required=_exact(row, "mfa_required", bool),
            last_login_at=(
                None
                if row.get("last_login_at") is None
                else AwareUtcDateTime(_exact(row, "last_login_at", datetime))
            ),
            last_mfa_at=(
                None
                if row.get("last_mfa_at") is None
                else AwareUtcDateTime(_exact(row, "last_mfa_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_iam_user_account(value: UserAccount) -> dict[str, object]:
    return _encoded(
        (
            "principal_id",
            "oidc_issuer",
            "oidc_subject",
            "email",
            "email_verified",
            "mfa_required",
            "last_login_at",
            "last_mfa_at",
            "created_at",
        ),
        domain_mappers.map_iam_user_account_to_row(value),
    )


# Aggregate-specific classes below are the only DML surface.


def _cas_principal(
    session: Session,
    table: Table,
    state: PrincipalState,
    expected_version: AggregateVersion,
) -> AggregateVersion:
    if state.lock_version != expected_version:
        raise ValueError("INVALID_PRINCIPAL_VERSION") from None
    values = _encode_iam_principal(state)
    values.pop("id")
    values["lock_version"] = expected_version.value + 1
    statement = (
        update(table)
        .where(
            table.c.id == state.id.value,
            table.c.lock_version == expected_version.value,
        )
        .values(**values)
        .returning(table.c.lock_version)
    )
    try:
        persisted = session.execute(statement).scalar_one_or_none()
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(persisted) is int:
        return AggregateVersion(persisted)
    observed = _execute_one(
        session, select(table.c.lock_version).where(table.c.id == state.id.value)
    )
    if observed is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    observed_version = _exact(observed, "lock_version", int)
    if observed_version != expected_version.value:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


@guard_repository_class
class SqlAlchemyPrincipalRepository:
    __slots__ = ("_principal", "_service", "_session", "_user")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_REPOSITORY") from None
        self._session = session
        self._principal = _table("iam.principal")
        self._user = _table("iam.user_account")
        self._service = _table("iam.service_principal")

    def get(self, principal_id: PrincipalId) -> Principal | None:
        if type(principal_id) is not PrincipalId:
            raise ValueError("INVALID_PRINCIPAL_ID") from None
        row = _execute_one(
            self._session,
            select(self._principal).where(self._principal.c.id == principal_id.value),
        )
        if row is None:
            return None
        user = _execute_one(
            self._session,
            select(self._user).where(self._user.c.principal_id == principal_id.value),
        )
        service = _execute_one(
            self._session,
            select(self._service).where(
                self._service.c.principal_id == principal_id.value
            ),
        )
        try:
            return Principal(
                state=_decode_iam_principal(row),
                user_account=None if user is None else _decode_iam_user_account(user),
                service_principal=(
                    None if service is None else _decode_iam_service_principal(service)
                ),
            )
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def add(self, principal: Principal) -> AggregateVersion:
        if type(principal) is not Principal or principal.state.lock_version.value != 0:
            raise ValueError("INVALID_PRINCIPAL") from None
        _execute(
            self._session,
            insert(self._principal).values(**_encode_iam_principal(principal.state)),
        )
        if principal.user_account is not None:
            _execute(
                self._session,
                insert(self._user).values(
                    **_encode_iam_user_account(principal.user_account)
                ),
            )
        if principal.service_principal is not None:
            _execute(
                self._session,
                insert(self._service).values(
                    **_encode_iam_service_principal(principal.service_principal)
                ),
            )
        return AggregateVersion(0)

    def save(
        self, principal: Principal, expected_version: AggregateVersion
    ) -> AggregateVersion:
        if (
            type(principal) is not Principal
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_PRINCIPAL") from None
        current = self.get(principal.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if (current.user_account is None) != (principal.user_account is None) or (
            current.service_principal is None
        ) != (principal.service_principal is None):
            _fail(PersistenceErrorCode.INTEGRITY_CONFLICT)
        persisted = _cas_principal(
            self._session, self._principal, principal.state, expected_version
        )
        if principal.user_account is not None:
            values = _encode_iam_user_account(principal.user_account)
            values.pop("principal_id")
            row = _execute_one(
                self._session,
                update(self._user)
                .where(self._user.c.principal_id == principal.state.id.value)
                .values(**values)
                .returning(self._user.c.principal_id),
            )
            if row is None:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if principal.service_principal is not None:
            values = _encode_iam_service_principal(principal.service_principal)
            values.pop("principal_id")
            row = _execute_one(
                self._session,
                update(self._service)
                .where(self._service.c.principal_id == principal.state.id.value)
                .values(**values)
                .returning(self._service.c.principal_id),
            )
            if row is None:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted


@guard_repository_class
class SqlAlchemyRoleCatalogRepository:
    __slots__ = ("_binding", "_permission", "_role", "_session")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_REPOSITORY") from None
        self._session = session
        self._role = _table("iam.role")
        self._permission = _table("iam.permission")
        self._binding = _table("iam.role_permission")

    def get_role(self, role_id: RoleId) -> Role | None:
        if type(role_id) is not RoleId:
            raise ValueError("INVALID_ROLE_ID") from None
        row = _execute_one(
            self._session, select(self._role).where(self._role.c.id == role_id.value)
        )
        return None if row is None else _decode_iam_role(row)

    def get_role_by_code(self, role_code: str) -> Role | None:
        if type(role_code) is not str or not role_code:
            raise ValueError("INVALID_ROLE_CODE") from None
        row = _execute_one(
            self._session,
            select(self._role).where(self._role.c.role_code == role_code),
        )
        return None if row is None else _decode_iam_role(row)

    def get_permission(self, permission_id: PermissionId) -> Permission | None:
        if type(permission_id) is not PermissionId:
            raise ValueError("INVALID_PERMISSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._permission).where(
                self._permission.c.id == permission_id.value
            ),
        )
        return None if row is None else _decode_iam_permission(row)

    def get_permission_by_code(self, permission_code: str) -> Permission | None:
        if type(permission_code) is not str or not permission_code:
            raise ValueError("INVALID_PERMISSION_CODE") from None
        row = _execute_one(
            self._session,
            select(self._permission).where(
                self._permission.c.permission_code == permission_code
            ),
        )
        return None if row is None else _decode_iam_permission(row)

    def list_permissions_for_role(self, role_id: RoleId) -> tuple[Permission, ...]:
        if type(role_id) is not RoleId:
            raise ValueError("INVALID_ROLE_ID") from None
        statement = (
            select(self._permission)
            .join(
                self._binding,
                self._binding.c.permission_id == self._permission.c.id,
            )
            .where(self._binding.c.role_id == role_id.value)
            .order_by(self._permission.c.id)
        )
        try:
            rows = self._session.execute(statement).mappings()
            return tuple(_decode_iam_permission(row) for row in rows)
        except DBAPIError:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )
        except PersistenceError as error:
            fail_session_operation(self._session, error.code)
        except Exception:
            fail_session_operation(
                self._session, PersistenceErrorCode.STORAGE_CORRUPTION
            )


@guard_repository_class
class SqlAlchemyPrincipalRoleAssignmentRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_REPOSITORY") from None
        self._session = session
        self._table = _table("iam.principal_role_assignment")

    def get(
        self, assignment_id: PrincipalRoleAssignmentId
    ) -> PrincipalRoleAssignment | None:
        if type(assignment_id) is not PrincipalRoleAssignmentId:
            raise ValueError("INVALID_ASSIGNMENT_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == assignment_id.value),
        )
        return (
            None
            if row is None
            else PrincipalRoleAssignment(_decode_iam_principal_role_assignment(row))
        )

    def append(self, assignment: PrincipalRoleAssignment) -> None:
        if type(assignment) is not PrincipalRoleAssignment:
            raise ValueError("INVALID_ASSIGNMENT") from None
        _execute(
            self._session,
            insert(self._table).values(
                **_encode_iam_principal_role_assignment(assignment.state)
            ),
        )

    def revoke(
        self,
        assignment_id: PrincipalRoleAssignmentId,
        revocation: PrincipalRoleAssignment,
        expected_state: str,
    ) -> PrincipalRoleAssignment:
        if (
            type(assignment_id) is not PrincipalRoleAssignmentId
            or type(revocation) is not PrincipalRoleAssignment
            or revocation.state.id != assignment_id
            or expected_state != "ACTIVE"
            or revocation.state.revoked_at is None
            or revocation.state.revoked_by_principal_id is None
            or revocation.state.revocation_reason is None
        ):
            raise ValueError("INVALID_ASSIGNMENT_REVOCATION") from None
        state = revocation.state
        revoked_at = state.revoked_at
        revoked_by = state.revoked_by_principal_id
        if revoked_at is None or revoked_by is None:
            raise ValueError("INVALID_ASSIGNMENT_REVOCATION") from None
        actor_id = persistence_context(self._session).actor.actor_id
        if actor_id is None or revoked_by.value != actor_id:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        current = self.get(assignment_id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_state = current.state
        if (
            (
                current_state.id,
                current_state.principal_id,
                current_state.role_id,
                current_state.scope_type,
                current_state.scope_id,
                current_state.valid_from,
                current_state.valid_to,
                current_state.assigned_by_principal_id,
                current_state.assignment_reason,
                current_state.created_at,
            )
            != (
                state.id,
                state.principal_id,
                state.role_id,
                state.scope_type,
                state.scope_id,
                state.valid_from,
                state.valid_to,
                state.assigned_by_principal_id,
                state.assignment_reason,
                state.created_at,
            )
            or current_state.revoked_at is not None
            or current_state.revoked_by_principal_id is not None
            or current_state.revocation_reason is not None
            or current_state.valid_from.value > revoked_at.value
            or (
                current_state.valid_to is not None
                and current_state.valid_to.value <= revoked_at.value
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        statement = (
            update(self._table)
            .where(
                self._table.c.id == assignment_id.value,
                self._table.c.revoked_at.is_(None),
                self._table.c.revoked_by_principal_id.is_(None),
                self._table.c.revocation_reason.is_(None),
                self._table.c.valid_from <= revoked_at.value,
                (self._table.c.valid_to.is_(None))
                | (self._table.c.valid_to > revoked_at.value),
            )
            .values(
                revoked_at=revoked_at.value,
                revoked_by_principal_id=actor_id,
                revocation_reason=state.revocation_reason,
            )
            .returning(self._table)
        )
        row = _execute_one(self._session, statement)
        if row is None:
            existing = self.get(assignment_id)
            if existing is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            existing_state = existing.state
            if (
                existing_state.revoked_at is not None
                or existing_state.revoked_by_principal_id is not None
                or existing_state.revocation_reason is not None
                or existing_state.valid_from.value > revoked_at.value
                or (
                    existing_state.valid_to is not None
                    and existing_state.valid_to.value <= revoked_at.value
                )
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        persisted = PrincipalRoleAssignment(_decode_iam_principal_role_assignment(row))
        if persisted.state != revocation.state:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return persisted


@guard_repository_class
class SqlAlchemySessionRevocationRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_REPOSITORY") from None
        self._session = session
        self._table = _table("iam.session_revocation")

    def get(self, revocation_id: SessionRevocationId) -> SessionRevocation | None:
        if type(revocation_id) is not SessionRevocationId:
            raise ValueError("INVALID_REVOCATION_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == revocation_id.value),
        )
        return None if row is None else _decode_iam_session_revocation(row)

    def append(self, revocation: SessionRevocation) -> None:
        if type(revocation) is not SessionRevocation:
            raise ValueError("INVALID_REVOCATION") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_iam_session_revocation(revocation)),
        )


@guard_repository_class
class SqlAlchemyBreakGlassRecordRepository:
    __slots__ = ("_session", "_table")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_REPOSITORY") from None
        self._session = session
        self._table = _table("iam.break_glass_record")

    def get(self, record_id: BreakGlassRecordId) -> BreakGlassRecord | None:
        if type(record_id) is not BreakGlassRecordId:
            raise ValueError("INVALID_BREAK_GLASS_ID") from None
        row = _execute_one(
            self._session,
            select(self._table).where(self._table.c.id == record_id.value),
        )
        return None if row is None else _decode_iam_break_glass_record(row)

    def append(self, record: BreakGlassRecord) -> None:
        if type(record) is not BreakGlassRecord:
            raise ValueError("INVALID_BREAK_GLASS_RECORD") from None
        _execute(
            self._session,
            insert(self._table).values(**_encode_iam_break_glass_record(record)),
        )


__all__ = [
    "SqlAlchemyBreakGlassRecordRepository",
    "SqlAlchemyPrincipalRepository",
    "SqlAlchemyPrincipalRoleAssignmentRepository",
    "SqlAlchemyRoleCatalogRepository",
    "SqlAlchemySessionRevocationRepository",
]
