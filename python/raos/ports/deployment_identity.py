"""Outbound port for ST-1504 deployment-identity activation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from raos.domain.deployment_identity import (
    DeploymentIdentityPolicyError,
    validate_evaluation_digest,
)


@dataclass(frozen=True, slots=True)
class DeploymentIdentityActivationCommand:
    """A command shape that cannot carry credentials or requested actions."""

    policy_id: str
    fixture_id: str
    evaluation_digest: str
    enable_requested: bool = False
    requested_action_count: int = 0
    credential_material: None = None

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or not self.policy_id.startswith(
            "st1504-policy-"
        ):
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_COMMAND_INVALID", "policy_id"
            )
        if type(self.fixture_id) is not str or not self.fixture_id.startswith(
            "st1504-fixture-"
        ):
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_COMMAND_INVALID", "fixture_id"
            )
        validate_evaluation_digest(self.evaluation_digest)
        if type(self.enable_requested) is not bool:
            raise DeploymentIdentityPolicyError("TYPE_MISMATCH", "enable_requested")
        if type(self.requested_action_count) is not int:
            raise DeploymentIdentityPolicyError(
                "TYPE_MISMATCH", "requested_action_count"
            )
        if self.enable_requested or self.requested_action_count != 0:
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_FORBIDDEN", "activation_command"
            )
        if self.credential_material is not None:
            raise DeploymentIdentityPolicyError(
                "CREDENTIAL_MATERIAL_FORBIDDEN", "credential_material"
            )


@dataclass(frozen=True, slots=True)
class DeploymentIdentityActivationReceipt:
    """A deterministic refusal receipt with exactly zero actions."""

    policy_id: str
    fixture_id: str
    status: str
    activation_allowed: bool
    credentials_issued: bool
    actions_executed: int
    reason_code: str

    def __post_init__(self) -> None:
        if type(self.policy_id) is not str or not self.policy_id.startswith(
            "st1504-policy-"
        ):
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "policy_id"
            )
        if type(self.fixture_id) is not str or not self.fixture_id.startswith(
            "st1504-fixture-"
        ):
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "fixture_id"
            )
        if self.status != "DISABLED" or type(self.status) is not str:
            raise DeploymentIdentityPolicyError("ACTIVATION_RECEIPT_INVALID", "status")
        if type(self.activation_allowed) is not bool or self.activation_allowed:
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "activation_allowed"
            )
        if type(self.credentials_issued) is not bool or self.credentials_issued:
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "credentials_issued"
            )
        if type(self.actions_executed) is not int or self.actions_executed != 0:
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "actions_executed"
            )
        if (
            type(self.reason_code) is not str
            or self.reason_code != "LOCAL_ACTIVATION_DISABLED"
        ):
            raise DeploymentIdentityPolicyError(
                "ACTIVATION_RECEIPT_INVALID", "reason_code"
            )


class DeploymentIdentityActivationPort(Protocol):
    """A provider-neutral port; the local implementation is always disabled."""

    def activate(
        self, command: DeploymentIdentityActivationCommand
    ) -> DeploymentIdentityActivationReceipt: ...
