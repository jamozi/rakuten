"""Provider-neutral application ports.

Facade exports stay backwards compatible while loading only the selected port.  This
keeps an evidence-only import from initializing unrelated registries and generated
contract inventories.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any, Final


if TYPE_CHECKING:
    from raos.ports.oidc import AuthenticationRepository, EntropySource, OidcProvider
    from raos.ports.queue import (
        InvalidQueueMessage,
        QueueDelivery,
        QueueError,
        QueueMessage,
        QueuePort,
        ReceiptHandleError,
        StaleReceiptHandle,
        UnknownReceiptHandle,
    )
    from raos.ports.task_registry import (
        InvalidTaskCode,
        TaskRegistry,
        TaskRegistryError,
        TaskRegistryIntegrityError,
        UnknownTaskContract,
    )

__all__ = [
    "AuthenticationRepository",
    "EntropySource",
    "InvalidQueueMessage",
    "QueueDelivery",
    "QueueError",
    "QueueMessage",
    "QueuePort",
    "ReceiptHandleError",
    "StaleReceiptHandle",
    "UnknownReceiptHandle",
    "InvalidTaskCode",
    "OidcProvider",
    "TaskRegistry",
    "TaskRegistryError",
    "TaskRegistryIntegrityError",
    "UnknownTaskContract",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "AuthenticationRepository": (
        "raos.ports.oidc",
        "AuthenticationRepository",
    ),
    "EntropySource": ("raos.ports.oidc", "EntropySource"),
    "InvalidQueueMessage": ("raos.ports.queue", "InvalidQueueMessage"),
    "InvalidTaskCode": ("raos.ports.task_registry", "InvalidTaskCode"),
    "OidcProvider": ("raos.ports.oidc", "OidcProvider"),
    "QueueDelivery": ("raos.ports.queue", "QueueDelivery"),
    "QueueError": ("raos.ports.queue", "QueueError"),
    "QueueMessage": ("raos.ports.queue", "QueueMessage"),
    "QueuePort": ("raos.ports.queue", "QueuePort"),
    "ReceiptHandleError": ("raos.ports.queue", "ReceiptHandleError"),
    "StaleReceiptHandle": ("raos.ports.queue", "StaleReceiptHandle"),
    "TaskRegistry": ("raos.ports.task_registry", "TaskRegistry"),
    "TaskRegistryError": ("raos.ports.task_registry", "TaskRegistryError"),
    "TaskRegistryIntegrityError": (
        "raos.ports.task_registry",
        "TaskRegistryIntegrityError",
    ),
    "UnknownReceiptHandle": ("raos.ports.queue", "UnknownReceiptHandle"),
    "UnknownTaskContract": (
        "raos.ports.task_registry",
        "UnknownTaskContract",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve a documented facade export without eager sibling imports."""

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy facade names to interactive and inspection consumers."""

    return sorted((*globals(), *_LAZY_EXPORTS))
