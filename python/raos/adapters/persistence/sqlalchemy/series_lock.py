"""Closed transaction-scoped serialization for one nullable version series."""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    require_session_runtime,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


_LOCK_RUNTIME_SETTING_VERSION = text(
    'LOCK TABLE "ops"."runtime_setting_version" IN SHARE ROW EXCLUSIVE MODE'
)


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def lock_runtime_setting_version_series(session: Session) -> None:
    """Serialize append precheck+insert, including the GLOBAL NULL scope.

    The predecessor schema's four-column UNIQUE constraint treats NULL scope
    identifiers as distinct.  A transaction-level table lock is therefore
    required to prevent two first/global appends from admitting the same
    ``version_no``.  PostgreSQL INSERT takes ``ROW EXCLUSIVE`` and consequently
    also waits behind this lock, including writers outside this adapter.
    """

    require_session_runtime(session)
    try:
        session.execute(_LOCK_RUNTIME_SETTING_VERSION)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


__all__: list[str] = []
