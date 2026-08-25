"""Outward adapters for RAOS application ports.

The package facade is intentionally lazy.  Importing one provider-neutral recorded
adapter must not initialize unrelated live-provider SDKs merely because Python first
loads this parent package.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any, Final


if TYPE_CHECKING:
    from raos.adapters.ai_contract_registry import CompiledTaskRegistry
    from raos.adapters.development_oidc import (
        DevelopmentOidcAdapter,
        InMemoryAuthenticationRepository,
        SystemEntropySource,
    )
    from raos.adapters.openai_responses import (
        OpenAIResponseRoute,
        OpenAIResponsesAdapter,
        ReasoningEffort,
    )
    from raos.adapters.queue_fake import DeadLetter, QueueFake
    from raos.adapters.recorded_ai import (
        InMemoryProviderExchangeRecorder,
        SyntheticRecordedCostCalculator,
    )

__all__ = [
    "CompiledTaskRegistry",
    "DeadLetter",
    "DevelopmentOidcAdapter",
    "InMemoryAuthenticationRepository",
    "InMemoryProviderExchangeRecorder",
    "OpenAIResponseRoute",
    "OpenAIResponsesAdapter",
    "QueueFake",
    "ReasoningEffort",
    "SyntheticRecordedCostCalculator",
    "SystemEntropySource",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "CompiledTaskRegistry": (
        "raos.adapters.ai_contract_registry",
        "CompiledTaskRegistry",
    ),
    "DeadLetter": ("raos.adapters.queue_fake", "DeadLetter"),
    "DevelopmentOidcAdapter": (
        "raos.adapters.development_oidc",
        "DevelopmentOidcAdapter",
    ),
    "InMemoryAuthenticationRepository": (
        "raos.adapters.development_oidc",
        "InMemoryAuthenticationRepository",
    ),
    "InMemoryProviderExchangeRecorder": (
        "raos.adapters.recorded_ai",
        "InMemoryProviderExchangeRecorder",
    ),
    "OpenAIResponseRoute": (
        "raos.adapters.openai_responses",
        "OpenAIResponseRoute",
    ),
    "OpenAIResponsesAdapter": (
        "raos.adapters.openai_responses",
        "OpenAIResponsesAdapter",
    ),
    "QueueFake": ("raos.adapters.queue_fake", "QueueFake"),
    "ReasoningEffort": ("raos.adapters.openai_responses", "ReasoningEffort"),
    "SyntheticRecordedCostCalculator": (
        "raos.adapters.recorded_ai",
        "SyntheticRecordedCostCalculator",
    ),
    "SystemEntropySource": (
        "raos.adapters.development_oidc",
        "SystemEntropySource",
    ),
}


def __getattr__(name: str) -> Any:
    """Resolve a documented facade export without eagerly loading other adapters."""

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
