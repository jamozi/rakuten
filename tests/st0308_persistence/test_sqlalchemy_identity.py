"""No-network tests for the PostgreSQL identity/session construction seam."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import Connection, Engine

from raos.adapters.persistence.sqlalchemy.identity import (
    SqlAlchemyEffectiveRoleVerifier,
    WorkloadProfile,
    _validated_identity_facts,
)
from raos.adapters.persistence.sqlalchemy.provider import SqlAlchemyEngineProvider
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


def _identity_row(*, group: str = "raos_api_rw") -> dict[str, object]:
    return {
        "login_role": "raos_api_login",
        "inherited_groups": [group],
        "is_superuser": False,
        "bypass_rls": False,
        "create_role": False,
        "create_database": False,
        "owns_selected_relation": False,
    }


def _connection_with_row(row: dict[str, object]) -> MagicMock:
    connection = MagicMock(spec=Connection)
    connection.closed = False
    connection.invalidated = False
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = row
    return connection


def _postgresql_engine(connection: MagicMock) -> MagicMock:
    engine = MagicMock(spec=Engine)
    object.__setattr__(engine, "dialect", SimpleNamespace(name="postgresql"))
    engine.connect.return_value = connection
    return engine


def test_identity_row_shape_is_exact_and_sanitized() -> None:
    facts = _validated_identity_facts(_identity_row())
    assert facts.login_role == "raos_api_login"
    assert facts.inherited_groups == frozenset({"raos_api_rw"})

    extra = {**_identity_row(), "unrecognized_authority": "GRANTED"}
    with pytest.raises(PersistenceError) as caught:
        _validated_identity_facts(extra)
    assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "mutation",
    ("wrong_group", "superuser", "duplicate_group", "non_boolean"),
)
def test_effective_role_verifier_fails_closed(mutation: str) -> None:
    row = _identity_row()
    if mutation == "wrong_group":
        row["inherited_groups"] = ["raos_worker_rw"]
    elif mutation == "superuser":
        row["is_superuser"] = True
    elif mutation == "duplicate_group":
        row["inherited_groups"] = ["raos_api_rw", "raos_api_rw"]
    else:
        row["create_role"] = 0
    connection = _connection_with_row(row)
    with pytest.raises(PersistenceError) as caught:
        SqlAlchemyEffectiveRoleVerifier().verify(
            connection,
            WorkloadProfile.API_COMMAND,
        )
    assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
    assert str(caught.value) == "IDENTITY_REJECTED"


def test_engine_provider_invalidates_rejected_checkout_before_session() -> None:
    connection = _connection_with_row(_identity_row(group="raos_worker_rw"))
    connection.in_transaction.return_value = False
    engine = _postgresql_engine(connection)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)

    with pytest.raises(PersistenceError) as caught:
        provider._checkout_verified(None)
    assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
    connection.invalidate.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_engine_provider_returns_only_hash_bound_verified_checkout() -> None:
    connection = _connection_with_row(_identity_row())
    connection.in_transaction.side_effect = (False, True, False)
    engine = _postgresql_engine(connection)
    provider = SqlAlchemyEngineProvider(engine, WorkloadProfile.API_COMMAND)

    checkout = provider._checkout_verified(None)
    assert repr(checkout) == "VerifiedConnection(<redacted>)"
    assert provider._connection(checkout) is connection
    connection.rollback.assert_called_once_with()
