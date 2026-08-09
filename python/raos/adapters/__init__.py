"""Outward adapters for RAOS application ports."""

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
