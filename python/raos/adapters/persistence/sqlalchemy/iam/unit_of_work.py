"""IAM repository composition surface for the shared SQLAlchemy UoW owner."""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories.iam import (
    SqlAlchemyBreakGlassRecordRepository,
    SqlAlchemyPrincipalRepository,
    SqlAlchemyPrincipalRoleAssignmentRepository,
    SqlAlchemyRoleCatalogRepository,
    SqlAlchemySessionRevocationRepository,
)


class SqlAlchemyIamRepositories:
    __slots__ = (
        "break_glass_records",
        "principals",
        "role_assignments",
        "role_catalog",
        "session_revocations",
    )

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_IAM_UOW_SURFACE") from None
        self.principals = SqlAlchemyPrincipalRepository(session)
        self.role_catalog = SqlAlchemyRoleCatalogRepository(session)
        self.role_assignments = SqlAlchemyPrincipalRoleAssignmentRepository(session)
        self.session_revocations = SqlAlchemySessionRevocationRepository(session)
        self.break_glass_records = SqlAlchemyBreakGlassRecordRepository(session)


__all__ = ["SqlAlchemyIamRepositories"]
