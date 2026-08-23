"""Injected Engine checkout and Session construction boundary for ST-0308."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NoReturn

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.identity import (
    SqlAlchemyEffectiveRoleVerifier,
    VerifiedDatabaseIdentity,
    WorkloadProfile,
    _require_verified_identity,
)
from raos.adapters.persistence.sqlalchemy.transaction import (
    _ExecutionPoint,
    _ExecutionState,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


_CHECKOUT_ISSUER: Final[object] = object()


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


@dataclass(frozen=True, slots=True, repr=False, init=False)
class VerifiedConnection:
    """Opaque checkout capability; it does not expose URL or pool internals."""

    __connection: Connection
    __identity: VerifiedDatabaseIdentity
    __profile: WorkloadProfile
    __provider_key: object

    def __init__(
        self,
        connection: Connection,
        identity: VerifiedDatabaseIdentity,
        profile: WorkloadProfile,
        provider_key: object,
        *,
        _issuer: object,
    ) -> None:
        if (
            _issuer is not _CHECKOUT_ISSUER
            or not isinstance(connection, Connection)
            or type(identity) is not VerifiedDatabaseIdentity
            or type(profile) is not WorkloadProfile
            or provider_key is None
        ):
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)
        _require_verified_identity(identity, connection, profile)
        object.__setattr__(self, "_VerifiedConnection__connection", connection)
        object.__setattr__(self, "_VerifiedConnection__identity", identity)
        object.__setattr__(self, "_VerifiedConnection__profile", profile)
        object.__setattr__(self, "_VerifiedConnection__provider_key", provider_key)

    def _adapter_connection(
        self,
        provider_key: object,
        expected_profile: WorkloadProfile,
    ) -> Connection:
        if (
            provider_key is not self.__provider_key
            or expected_profile is not self.__profile
        ):
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        _require_verified_identity(
            self.__identity,
            self.__connection,
            self.__profile,
        )
        return self.__connection

    def __repr__(self) -> str:
        return "VerifiedConnection(<redacted>)"


class SqlAlchemyEngineProvider:
    """One externally created PostgreSQL Engine bound to one workload profile."""

    __slots__ = ("_engine", "_key", "_profile", "_verifier")

    def __init__(
        self,
        engine: Engine,
        expected_profile: WorkloadProfile,
        verifier: SqlAlchemyEffectiveRoleVerifier | None = None,
    ) -> None:
        if (
            not isinstance(engine, Engine)
            or engine.dialect.name != "postgresql"
            or type(expected_profile) is not WorkloadProfile
            or (
                verifier is not None
                and type(verifier) is not SqlAlchemyEffectiveRoleVerifier
            )
        ):
            raise ValueError("INVALID_SQLALCHEMY_ENGINE_PROVIDER") from None
        self._engine = engine
        self._profile = expected_profile
        self._verifier = (
            SqlAlchemyEffectiveRoleVerifier() if verifier is None else verifier
        )
        self._key = object()

    @property
    def expected_profile(self) -> WorkloadProfile:
        return self._profile

    def _checkout_verified(
        self,
        execution_state: _ExecutionState | None,
    ) -> VerifiedConnection:
        if execution_state is not None and type(execution_state) is not _ExecutionState:
            raise ValueError("INVALID_SQLALCHEMY_EXECUTION_STATE") from None
        connection: Connection | None = None
        try:
            connection = self._engine.connect()
            if (
                connection.closed
                or connection.invalidated
                or connection.in_transaction()
            ):
                _fail(PersistenceErrorCode.IDENTITY_REJECTED)
            if execution_state is not None:
                execution_state.require_allowed(_ExecutionPoint.POST_CHECKOUT)
            proof = self._verifier.verify(connection, self._profile)
            _require_verified_identity(proof, connection, self._profile)
            if execution_state is not None:
                execution_state.require_allowed(_ExecutionPoint.POST_IDENTITY)
            if connection.in_transaction():
                connection.rollback()
            if connection.in_transaction():
                _fail(PersistenceErrorCode.IDENTITY_REJECTED)
            return VerifiedConnection(
                connection,
                proof,
                self._profile,
                self._key,
                _issuer=_CHECKOUT_ISSUER,
            )
        except PersistenceError as error:
            if connection is not None:
                if error.code in {
                    PersistenceErrorCode.CANCELLED,
                    PersistenceErrorCode.DEADLINE_EXCEEDED,
                }:
                    self._close_raw(connection)
                else:
                    self._invalidate_and_close_raw(connection)
            raise
        except Exception:
            if connection is not None:
                self._invalidate_and_close_raw(connection)
            _fail(PersistenceErrorCode.IDENTITY_REJECTED)

    def _connection(self, checkout: VerifiedConnection) -> Connection:
        if type(checkout) is not VerifiedConnection:
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        return checkout._adapter_connection(self._key, self._profile)

    def _create_session(self, checkout: VerifiedConnection) -> Session:
        connection = self._connection(checkout)
        if connection.in_transaction():
            _fail(PersistenceErrorCode.TRANSACTION_OWNERSHIP)
        try:
            return Session(
                bind=connection,
                autobegin=False,
                autoflush=False,
                expire_on_commit=False,
            )
        except Exception:
            self._invalidate_and_close(checkout)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    def _invalidate_and_close(self, checkout: VerifiedConnection) -> None:
        connection = self._connection(checkout)
        self._invalidate_and_close_raw(connection)

    def _close(self, checkout: VerifiedConnection) -> None:
        connection = self._connection(checkout)
        try:
            connection.close()
        except Exception:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)

    @staticmethod
    def _invalidate_and_close_raw(connection: Connection) -> None:
        try:
            connection.invalidate()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

    @staticmethod
    def _close_raw(connection: Connection) -> None:
        try:
            connection.close()
        except Exception:
            pass


__all__ = ["SqlAlchemyEngineProvider"]
