"""OPS repository composition surface for the shared SQLAlchemy UoW owner."""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories.ops import (
    SqlAlchemyJobRepository,
    SqlAlchemyObjectArtifactRepository,
    SqlAlchemyRuntimeSettingRepository,
)


class SqlAlchemyOpsRepositories:
    __slots__ = ("jobs", "object_artifacts", "runtime_settings")

    def __init__(self, session: Session) -> None:
        if not isinstance(cast(object, session), Session):
            raise ValueError("INVALID_OPS_UOW_SURFACE") from None
        self.jobs = SqlAlchemyJobRepository(session)
        self.object_artifacts = SqlAlchemyObjectArtifactRepository(session)
        self.runtime_settings = SqlAlchemyRuntimeSettingRepository(session)


__all__ = ["SqlAlchemyOpsRepositories"]
