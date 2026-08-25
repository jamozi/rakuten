"""Always-disabled ST-1506 Production activation adapter."""

from __future__ import annotations

from typing import final

from raos.domain.ops.production_canary import (
    EXTERNAL_ACTION_NAMES,
    ProductionCanaryError,
)
from raos.ports.production_canary import (
    ProductionActivationCommand,
    ProductionActivationReceipt,
)


@final
class DisabledProductionActivation:
    """A zero-action adapter with no ambient configuration or credential read."""

    __slots__ = ()

    @property
    def mode(self) -> str:
        return "DISABLED_RECORDED_LOCAL_ONLY"

    @property
    def external_action_counts(self) -> tuple[tuple[str, int], ...]:
        return tuple((name, 0) for name in EXTERNAL_ACTION_NAMES)

    def request(
        self, command: ProductionActivationCommand
    ) -> ProductionActivationReceipt:
        if type(command) is not ProductionActivationCommand:
            raise ProductionCanaryError("ACTIVATION_COMMAND_INVALID", "activation")
        return ProductionActivationReceipt(
            contract_sha256=command.contract_sha256,
            status="DISABLED",
            activation_allowed=False,
            public_write_allowed=False,
            actions_executed=0,
            reason_code="LOCAL_PRODUCTION_ACTIVATION_DISABLED",
        )


__all__ = ["DisabledProductionActivation"]
