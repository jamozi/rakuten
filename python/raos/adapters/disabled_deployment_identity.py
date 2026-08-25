"""Default-disabled ST-1504 deployment-identity activation adapter."""

from __future__ import annotations

from raos.ports.deployment_identity import (
    DeploymentIdentityActivationCommand,
    DeploymentIdentityActivationReceipt,
)


class DisabledDeploymentIdentityActivation:
    """Return a closed refusal and perform no provider or external operation."""

    def activate(
        self, command: DeploymentIdentityActivationCommand
    ) -> DeploymentIdentityActivationReceipt:
        return DeploymentIdentityActivationReceipt(
            policy_id=command.policy_id,
            fixture_id=command.fixture_id,
            status="DISABLED",
            activation_allowed=False,
            credentials_issued=False,
            actions_executed=0,
            reason_code="LOCAL_ACTIVATION_DISABLED",
        )
