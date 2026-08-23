"""No-I/O identity/session seam proving the required begin ordering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, NoReturn, Protocol, SupportsIndex, runtime_checkable

from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


class WorkloadProfile(str, Enum):
    API_COMMAND = "API_COMMAND"
    WORKER_COMMAND = "WORKER_COMMAND"


_REQUIRED_GROUP = {
    WorkloadProfile.API_COMMAND: "raos_api_rw",
    WorkloadProfile.WORKER_COMMAND: "raos_worker_rw",
}
_IDENTITY_PROOF_ISSUER: Final[object] = object()


def _reject_identity() -> NoReturn:
    raise PersistenceError(PersistenceErrorCode.IDENTITY_REJECTED) from None


@dataclass(frozen=True, slots=True, repr=False)
class DatabaseIdentityFacts:
    login_role: str
    inherited_groups: frozenset[str]
    is_superuser: bool = False
    bypass_rls: bool = False
    create_role: bool = False
    create_database: bool = False
    owns_selected_relation: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.login_role) is not str
            or not self.login_role
            or type(self.inherited_groups) is not frozenset
            or any(
                type(group) is not str or not group for group in self.inherited_groups
            )
            or type(self.is_superuser) is not bool
            or type(self.bypass_rls) is not bool
            or type(self.create_role) is not bool
            or type(self.create_database) is not bool
            or type(self.owns_selected_relation) is not bool
        ):
            raise ValueError("INVALID_DATABASE_IDENTITY") from None

    def __repr__(self) -> str:
        return "DatabaseIdentityFacts(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, init=False)
class VerifiedDatabaseIdentity:
    """Opaque positive proof bound to one checked-out connection and profile."""

    __login_role: str
    __inherited_groups: frozenset[str]
    __expected_profile: WorkloadProfile
    __connection_key: object

    def __init__(
        self,
        login_role: str,
        inherited_groups: frozenset[str],
        expected_profile: WorkloadProfile,
        connection_key: object,
        *,
        _issuer: object,
    ) -> None:
        if (
            _issuer is not _IDENTITY_PROOF_ISSUER
            or type(login_role) is not str
            or not login_role
            or type(inherited_groups) is not frozenset
            or any(type(group) is not str or not group for group in inherited_groups)
            or type(expected_profile) is not WorkloadProfile
            or connection_key is None
        ):
            raise ValueError("INVALID_DATABASE_IDENTITY") from None
        object.__setattr__(self, "_VerifiedDatabaseIdentity__login_role", login_role)
        object.__setattr__(
            self,
            "_VerifiedDatabaseIdentity__inherited_groups",
            inherited_groups,
        )
        object.__setattr__(
            self,
            "_VerifiedDatabaseIdentity__expected_profile",
            expected_profile,
        )
        object.__setattr__(
            self,
            "_VerifiedDatabaseIdentity__connection_key",
            connection_key,
        )

    @property
    def login_role(self) -> str:
        return self.__login_role

    @property
    def inherited_groups(self) -> frozenset[str]:
        return self.__inherited_groups

    def _matches(
        self,
        *,
        connection_key: object,
        expected_profile: WorkloadProfile,
        login_role: str,
        inherited_groups: frozenset[str],
    ) -> bool:
        return (
            self.__connection_key is connection_key
            and self.__expected_profile is expected_profile
            and self.__login_role == login_role
            and self.__inherited_groups == inherited_groups
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("database identity proof serialization is not supported")

    def __repr__(self) -> str:
        return "VerifiedDatabaseIdentity(<redacted>)"


class MemoryConnection:
    """Opaque local connection marker; never owns credentials or network I/O."""

    __slots__ = (
        "_closed",
        "_identity",
        "_identity_proof_key",
        "_invalidated",
        "_trace",
    )

    def __init__(
        self,
        identity: DatabaseIdentityFacts,
        trace: list[str],
    ) -> None:
        if type(identity) is not DatabaseIdentityFacts or type(trace) is not list:
            raise ValueError("INVALID_MEMORY_CONNECTION") from None
        self._identity = identity
        self._trace = trace
        self._closed = False
        self._invalidated = False
        self._identity_proof_key = object()

    @property
    def identity(self) -> DatabaseIdentityFacts:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def invalidated(self) -> bool:
        return self._invalidated

    def invalidate(self) -> None:
        self._trace.append("connection.invalidate")
        self._invalidated = True

    def close(self) -> None:
        if not self._closed:
            self._trace.append("connection.close")
            self._closed = True


class MemoryConnectionPool:
    __slots__ = ("_identity", "trace")

    def __init__(self, identity: DatabaseIdentityFacts) -> None:
        if type(identity) is not DatabaseIdentityFacts:
            raise ValueError("INVALID_MEMORY_CONNECTION_POOL") from None
        self._identity = identity
        self.trace: list[str] = []

    def checkout(self) -> MemoryConnection:
        self.trace.append("connection.checkout")
        return MemoryConnection(self._identity, self.trace)


@runtime_checkable
class EffectiveRoleVerifier(Protocol):
    def verify(
        self,
        connection: MemoryConnection,
        expected_profile: WorkloadProfile,
    ) -> VerifiedDatabaseIdentity: ...


class MemoryEffectiveRoleVerifier:
    """Fail-closed verifier over injected recorded identity facts."""

    __slots__ = ()

    def verify(
        self,
        connection: MemoryConnection,
        expected_profile: WorkloadProfile,
    ) -> VerifiedDatabaseIdentity:
        if (
            type(connection) is not MemoryConnection
            or type(expected_profile) is not WorkloadProfile
        ):
            _reject_identity()
        connection._trace.append("identity.verify")
        identity = connection.identity
        required = _REQUIRED_GROUP[expected_profile]
        groups = identity.inherited_groups
        if (
            groups != frozenset({required})
            or identity.is_superuser
            or identity.bypass_rls
            or identity.create_role
            or identity.create_database
            or identity.owns_selected_relation
        ):
            _reject_identity()
        return _issue_verified_identity(connection, expected_profile)


def _issue_verified_identity(
    connection: MemoryConnection,
    expected_profile: WorkloadProfile,
) -> VerifiedDatabaseIdentity:
    if (
        type(connection) is not MemoryConnection
        or connection.closed
        or connection.invalidated
        or type(expected_profile) is not WorkloadProfile
    ):
        _reject_identity()
    identity = connection.identity
    return VerifiedDatabaseIdentity(
        identity.login_role,
        identity.inherited_groups,
        expected_profile,
        connection._identity_proof_key,
        _issuer=_IDENTITY_PROOF_ISSUER,
    )


def _require_verified_identity(
    proof: object,
    connection: MemoryConnection,
    expected_profile: WorkloadProfile,
) -> VerifiedDatabaseIdentity:
    if (
        type(proof) is not VerifiedDatabaseIdentity
        or type(connection) is not MemoryConnection
        or type(expected_profile) is not WorkloadProfile
        or connection.closed
        or connection.invalidated
        or not proof._matches(
            connection_key=connection._identity_proof_key,
            expected_profile=expected_profile,
            login_role=connection.identity.login_role,
            inherited_groups=connection.identity.inherited_groups,
        )
    ):
        _reject_identity()
    return proof


class MemoryCommitMode(str, Enum):
    SUCCESS = "SUCCESS"
    KNOWN_FAILURE = "KNOWN_FAILURE"
    UNKNOWN = "UNKNOWN"


class _KnownCommitFailure(RuntimeError):
    pass


class _UnknownCommit(RuntimeError):
    pass


class MemorySession:
    __slots__ = ("_active", "_closed", "_commit_mode", "_connection", "_trace")

    def __init__(
        self,
        connection: MemoryConnection,
        commit_mode: MemoryCommitMode,
    ) -> None:
        self._connection = connection
        self._trace = connection._trace
        self._commit_mode = commit_mode
        self._active = False
        self._closed = False

    def begin(self) -> None:
        if self._closed or self._active:
            raise _KnownCommitFailure
        self._trace.append("session.begin")
        self._active = True

    def commit(self) -> None:
        if self._closed or not self._active:
            raise _KnownCommitFailure
        self._trace.append("session.commit")
        if self._commit_mode is MemoryCommitMode.UNKNOWN:
            self._active = False
            raise _UnknownCommit
        if self._commit_mode is MemoryCommitMode.KNOWN_FAILURE:
            raise _KnownCommitFailure
        self._active = False

    def rollback(self) -> None:
        if not self._closed and self._active:
            self._trace.append("session.rollback")
            self._active = False

    def close(self) -> None:
        if not self._closed:
            self._trace.append("session.close")
            self._closed = True


class MemorySessionFactory:
    __slots__ = ("_commit_mode",)

    def __init__(
        self, commit_mode: MemoryCommitMode = MemoryCommitMode.SUCCESS
    ) -> None:
        if type(commit_mode) is not MemoryCommitMode:
            raise ValueError("INVALID_MEMORY_SESSION_FACTORY") from None
        self._commit_mode = commit_mode

    def create(self, connection: MemoryConnection) -> MemorySession:
        if type(connection) is not MemoryConnection or connection.closed:
            raise PersistenceError(PersistenceErrorCode.IDENTITY_REJECTED) from None
        connection._trace.append("session.construct")
        return MemorySession(connection, self._commit_mode)


__all__ = [
    "DatabaseIdentityFacts",
    "EffectiveRoleVerifier",
    "MemoryCommitMode",
    "MemoryConnection",
    "MemoryConnectionPool",
    "MemoryEffectiveRoleVerifier",
    "MemorySession",
    "MemorySessionFactory",
    "VerifiedDatabaseIdentity",
    "WorkloadProfile",
]
