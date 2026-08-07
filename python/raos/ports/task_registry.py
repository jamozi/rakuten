"""Inward port for resolving immutable AI task contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from raos.domain.ai import TaskContract


class TaskRegistryError(RuntimeError):
    """Base error for task-registry trust-boundary failures."""


class InvalidTaskCode(TaskRegistryError, ValueError):
    """A caller supplied an invalid task-code value."""


class UnknownTaskContract(TaskRegistryError, LookupError):
    """No exact contract exists for the requested task code."""


class TaskRegistryIntegrityError(TaskRegistryError):
    """The compiled registry or one of its source artifacts has drifted."""


@runtime_checkable
class TaskRegistry(Protocol):
    """Resolve an exact hash-bound task contract without activating it."""

    def get(self, task_code: str) -> TaskContract:
        """Return the exact registered contract or fail closed."""

        ...
