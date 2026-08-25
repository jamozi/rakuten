"""Deterministic no-I/O persistence adapter for the ST-0308 OPS slice."""

from raos.adapters.persistence.memory.identity import (
    DatabaseIdentityFacts,
    EffectiveRoleVerifier,
    MemoryConnectionPool,
    MemoryEffectiveRoleVerifier,
    MemorySessionFactory,
    VerifiedDatabaseIdentity,
    WorkloadProfile,
)
from raos.adapters.persistence.memory.store import (
    MemoryPersistenceSnapshot,
    MemoryPersistenceStore,
)
from raos.adapters.persistence.memory.unit_of_work import MemoryOpsUnitOfWorkFactory

__all__ = [
    "EffectiveRoleVerifier",
    "DatabaseIdentityFacts",
    "MemoryConnectionPool",
    "MemoryEffectiveRoleVerifier",
    "MemoryOpsUnitOfWorkFactory",
    "MemoryPersistenceSnapshot",
    "MemoryPersistenceStore",
    "MemorySessionFactory",
    "VerifiedDatabaseIdentity",
    "WorkloadProfile",
]
