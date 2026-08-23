"""Fail-closed PostgreSQL workload identity verification for ST-0308.

The factory selects the expected profile.  Request data never reaches this
module, and this module neither resolves credentials nor creates an Engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final, NoReturn, SupportsIndex, cast

from sqlalchemy.engine import Connection, RowMapping

from raos.adapters.persistence.sqlalchemy.generated.identity_contract import (
    IDENTITY_FACTS_SQL,
    IDENTITY_RESULT_FIELDS,
    PROFILE_REQUIRED_GROUP,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


class WorkloadProfile(str, Enum):
    API_COMMAND = "API_COMMAND"
    WORKER_COMMAND = "WORKER_COMMAND"


_PROOF_ISSUER: Final[object] = object()
_EXPECTED_KEYS: Final = frozenset(IDENTITY_RESULT_FIELDS)


def _reject_identity() -> NoReturn:
    raise PersistenceError(PersistenceErrorCode.IDENTITY_REJECTED) from None


@dataclass(frozen=True, slots=True, repr=False)
class _DatabaseIdentityFacts:
    login_role: str
    inherited_groups: frozenset[str]
    is_superuser: bool
    bypass_rls: bool
    create_role: bool
    create_database: bool
    owns_selected_relation: bool

    def __repr__(self) -> str:
        return "_DatabaseIdentityFacts(<redacted>)"


def _validated_identity_facts(row: Mapping[str, object]) -> _DatabaseIdentityFacts:
    if type(row) not in {dict, RowMapping} and not isinstance(row, Mapping):
        _reject_identity()
    if frozenset(row) != _EXPECTED_KEYS or len(row) != len(_EXPECTED_KEYS):
        _reject_identity()
    login_role = row.get("login_role")
    inherited_groups_value = row.get("inherited_groups")
    if (
        type(login_role) is not str
        or not login_role
        or type(inherited_groups_value) not in {list, tuple}
    ):
        _reject_identity()
    inherited_group_items = cast(
        list[object] | tuple[object, ...], inherited_groups_value
    )
    if any(type(group) is not str or not group for group in inherited_group_items):
        _reject_identity()
    inherited_groups = frozenset(cast(str, group) for group in inherited_group_items)
    if len(inherited_groups) != len(inherited_group_items):
        _reject_identity()
    boolean_fields = (
        "is_superuser",
        "bypass_rls",
        "create_role",
        "create_database",
        "owns_selected_relation",
    )
    if any(type(row.get(field)) is not bool for field in boolean_fields):
        _reject_identity()
    return _DatabaseIdentityFacts(
        login_role=login_role,
        inherited_groups=inherited_groups,
        is_superuser=cast(bool, row["is_superuser"]),
        bypass_rls=cast(bool, row["bypass_rls"]),
        create_role=cast(bool, row["create_role"]),
        create_database=cast(bool, row["create_database"]),
        owns_selected_relation=cast(bool, row["owns_selected_relation"]),
    )


@dataclass(frozen=True, slots=True, repr=False, init=False)
class VerifiedDatabaseIdentity:
    """Opaque proof bound to one exact checked-out Connection and profile."""

    __login_role: str
    __groups: frozenset[str]
    __profile: WorkloadProfile
    __connection: Connection

    def __init__(
        self,
        facts: _DatabaseIdentityFacts,
        profile: WorkloadProfile,
        connection: Connection,
        *,
        _issuer: object,
    ) -> None:
        if (
            _issuer is not _PROOF_ISSUER
            or type(facts) is not _DatabaseIdentityFacts
            or type(profile) is not WorkloadProfile
            or not isinstance(connection, Connection)
            or connection.closed
            or connection.invalidated
        ):
            _reject_identity()
        object.__setattr__(
            self, "_VerifiedDatabaseIdentity__login_role", facts.login_role
        )
        object.__setattr__(
            self, "_VerifiedDatabaseIdentity__groups", facts.inherited_groups
        )
        object.__setattr__(self, "_VerifiedDatabaseIdentity__profile", profile)
        object.__setattr__(self, "_VerifiedDatabaseIdentity__connection", connection)

    def _matches(
        self,
        *,
        connection: Connection,
        profile: WorkloadProfile,
    ) -> bool:
        return (
            self.__connection is connection
            and self.__profile is profile
            and not connection.closed
            and not connection.invalidated
        )

    @property
    def login_role(self) -> str:
        return self.__login_role

    @property
    def inherited_groups(self) -> frozenset[str]:
        return self.__groups

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("database identity proof serialization is not supported")

    def __repr__(self) -> str:
        return "VerifiedDatabaseIdentity(<redacted>)"


class SqlAlchemyEffectiveRoleVerifier:
    """Execute the generated seven-fact query before Session construction."""

    __slots__ = ()

    def verify(
        self,
        connection: Connection,
        expected_profile: WorkloadProfile,
    ) -> VerifiedDatabaseIdentity:
        if (
            not isinstance(connection, Connection)
            or connection.closed
            or connection.invalidated
            or type(expected_profile) is not WorkloadProfile
        ):
            _reject_identity()
        required_group = PROFILE_REQUIRED_GROUP.get(expected_profile.value)
        if type(required_group) is not str or not required_group:
            _reject_identity()
        try:
            result = connection.execute(
                IDENTITY_FACTS_SQL,
                {"required_group": required_group},
            )
            row = result.mappings().one_or_none()
        except Exception:
            _reject_identity()
        if row is None:
            _reject_identity()
        facts = _validated_identity_facts(cast(Mapping[str, object], row))
        if (
            facts.inherited_groups != frozenset({required_group})
            or facts.is_superuser
            or facts.bypass_rls
            or facts.create_role
            or facts.create_database
            or facts.owns_selected_relation
        ):
            _reject_identity()
        return VerifiedDatabaseIdentity(
            facts,
            expected_profile,
            connection,
            _issuer=_PROOF_ISSUER,
        )


def _require_verified_identity(
    proof: object,
    connection: Connection,
    expected_profile: WorkloadProfile,
) -> VerifiedDatabaseIdentity:
    if (
        type(proof) is not VerifiedDatabaseIdentity
        or not isinstance(connection, Connection)
        or type(expected_profile) is not WorkloadProfile
        or not proof._matches(connection=connection, profile=expected_profile)
    ):
        _reject_identity()
    return proof


__all__ = [
    "SqlAlchemyEffectiveRoleVerifier",
    "WorkloadProfile",
]
