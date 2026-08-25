"""Hostile offline trust and disabled activation coverage for ST-1504."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from raos.domain.deployment_identity import (
    DeploymentIdentityPolicyError,
    OfflineTrustPolicy,
    RecordedClaimEnvelope,
    evaluate_recorded_claims,
)
from raos.ports.deployment_identity import (
    DeploymentIdentityActivationCommand,
    DeploymentIdentityActivationReceipt,
)
from scripts import build_st1504_github_oidc as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_RUNTIME_MARKER_1504"


def _claims_document() -> dict[str, Any]:
    value = generator.load_json(REPOSITORY_ROOT / generator.CLAIMS_FIXTURE_PATH)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _policy_document() -> dict[str, Any]:
    value = generator.load_json(REPOSITORY_ROOT / generator.TRUST_POLICY_FIXTURE_PATH)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


@pytest.mark.parametrize(
    "field",
    ["jwt", "token", "header", "signature", "signature_verified", "authenticated"],
)
def test_jwt_token_signature_and_authentication_claims_are_not_accepted(
    field: str,
) -> None:
    document = _claims_document()
    document[field] = MARKER
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authentication_status", "AUTHENTICATED"),
        ("signature_verification_status", "VERIFIED"),
        ("token_material", "PRESENT"),
    ],
)
def test_recorded_envelope_cannot_claim_authentication_or_signature(
    field: str, value: str
) -> None:
    document = _claims_document()
    document[field] = value
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_claim_set_is_closed(mutation: str) -> None:
    document = _claims_document()
    if mutation == "missing":
        document["claims"].pop("actor_id")
    else:
        document["claims"][MARKER] = MARKER
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("repository", "raos-fixture/*", "WILDCARD_OR_TEMPLATE_FORBIDDEN"),
        ("ref", "refs/heads/*", "WILDCARD_OR_TEMPLATE_FORBIDDEN"),
        ("aud", "*.invalid", "WILDCARD_OR_TEMPLATE_FORBIDDEN"),
        ("sub", "repo:raos-fixture/*", "WILDCARD_OR_TEMPLATE_FORBIDDEN"),
        ("environment", "production", "NON_SYNTHETIC_BINDING_FORBIDDEN"),
        ("event_name", "pull_request", "UNTRUSTED_EVENT"),
        ("event_name", "pull_request_target", "UNTRUSTED_EVENT"),
        ("job_workflow_ref", "some/reusable/workflow", "REUSABLE_CALLER_AMBIGUITY"),
        ("base_ref", "refs/heads/default", "PULL_REQUEST_CONTEXT_FORBIDDEN"),
        ("head_ref", "refs/heads/fork", "PULL_REQUEST_CONTEXT_FORBIDDEN"),
    ],
)
def test_wildcard_fork_pr_target_and_reusable_caller_claims_fail_closed(
    field: str, value: str, code: str
) -> None:
    document = _claims_document()
    document["claims"][field] = value
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == code


def test_subject_must_bind_exact_repository_and_environment() -> None:
    document = _claims_document()
    document["claims"]["sub"] = "repo:raos-fixture/other:environment:fixture"
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == "SUBJECT_BINDING_INVALID"


def test_workflow_must_bind_exact_repository_and_ref() -> None:
    document = _claims_document()
    document["claims"]["workflow_ref"] = (
        "raos-fixture/not-a-real-repository/other@refs/heads/fixture-other"
    )
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        RecordedClaimEnvelope.from_document(document)
    assert captured.value.code == "WORKFLOW_BINDING_INVALID"


@pytest.mark.parametrize(
    "field",
    [
        "wildcards_allowed",
        "fork_pull_request_allowed",
        "pull_request_allowed",
        "pull_request_target_allowed",
    ],
)
def test_trust_policy_broadening_is_rejected(field: str) -> None:
    document = _policy_document()
    document["trust"][field] = True
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


def test_reusable_caller_allowlist_is_not_inferred() -> None:
    document = _policy_document()
    document["trust"]["reusable_workflow_callers"] = [MARKER]
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code == "REUSABLE_CALLER_AMBIGUITY"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    [
        "role_chaining_allowed",
        "privilege_escalation_allowed",
        "static_credentials_allowed",
        "human_credentials_allowed",
        "cross_environment_reuse_allowed",
    ],
)
def test_session_escalation_static_human_and_cross_environment_reuse_are_denied(
    field: str,
) -> None:
    document = _policy_document()
    document["session"][field] = True
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    ("requested", "maximum"),
    [(299, 900), (600, 901), (901, 900), (True, 900), (600, "900")],
)
def test_session_duration_is_strictly_typed_and_bounded(
    requested: object, maximum: object
) -> None:
    document = _policy_document()
    document["session"]["requested_duration_seconds"] = requested
    document["session"]["maximum_duration_seconds"] = maximum
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code in {"TYPE_MISMATCH", "SESSION_DURATION_UNBOUNDED"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protected_environment_required", False),
        ("distinct_human_approval_required", False),
        ("self_approval_allowed", True),
        ("bypass_allowed", True),
    ],
)
def test_protected_distinct_human_approval_cannot_be_weakened(
    field: str, value: bool
) -> None:
    document = _policy_document()
    document["approval"][field] = value
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    "field",
    [
        "signed_provenance_required",
        "immutable_audit_required",
        "revocation_required",
        "rollback_required",
        "evidence_retention_required",
    ],
)
def test_provenance_audit_revocation_rollback_and_retention_remain_required(
    field: str,
) -> None:
    document = _policy_document()
    document["lifecycle"][field] = False
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [("enabled", True), ("enabled", 0), ("status", "ENABLED")],
)
def test_policy_activation_remains_disabled(field: str, value: object) -> None:
    document = _policy_document()
    document["activation"][field] = value
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code in {
        "TYPE_MISMATCH",
        "SAFE_BOUNDARY_VIOLATION",
        "FIXED_VALUE_VIOLATION",
    }


@pytest.mark.parametrize("action", ["create", "update", "delete"])
@pytest.mark.parametrize("value", [1, -1, True, "0"])
def test_policy_actions_are_exact_integer_zero(action: str, value: object) -> None:
    document = _policy_document()
    document["activation"]["planned_actions"][action] = value
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        OfflineTrustPolicy.from_document(document)
    assert captured.value.code in {"TYPE_MISMATCH", "NONZERO_ACTION_FORBIDDEN"}


def test_policy_match_failure_still_has_zero_authority() -> None:
    envelope = RecordedClaimEnvelope.from_document(_claims_document())
    policy = OfflineTrustPolicy.from_document(_policy_document())
    mismatched = RecordedClaimEnvelope(
        fixture_id=envelope.fixture_id,
        claims=tuple(
            (name, "100000099" if name == "actor_id" else value)
            for name, value in envelope.claims
        ),
    )
    result = evaluate_recorded_claims(policy, mismatched)
    assert result.policy_match is False
    assert "EXACT_CLAIM_MISMATCH" in result.reason_codes
    assert result.credential_issuance_authorized is False
    assert result.activation_authorized is False
    assert result.deployment_authorized is False
    assert result.action_count == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"enable_requested": True},
        {"requested_action_count": 1},
        {"requested_action_count": True},
        {"credential_material": MARKER},
    ],
)
def test_disabled_activation_command_rejects_enable_action_and_credentials(
    kwargs: dict[str, object],
) -> None:
    evaluation = _policy_document()
    digest = cast(str, generator.recorded_evaluation_document()["evidence_digest"])
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        DeploymentIdentityActivationCommand(
            policy_id=evaluation["policy_id"],
            fixture_id=evaluation["fixture_id"],
            evaluation_digest=digest,
            **kwargs,  # type: ignore[arg-type]
        )
    assert captured.value.code in {
        "TYPE_MISMATCH",
        "ACTIVATION_FORBIDDEN",
        "CREDENTIAL_MATERIAL_FORBIDDEN",
    }
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "ENABLED"},
        {"activation_allowed": True},
        {"activation_allowed": 0},
        {"credentials_issued": True},
        {"credentials_issued": 0},
        {"actions_executed": 1},
        {"actions_executed": True},
        {"reason_code": "ACTIVATED"},
    ],
)
def test_disabled_activation_receipt_cannot_be_forged(
    kwargs: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "policy_id": "st1504-policy-repository-inert-v1",
        "fixture_id": "st1504-fixture-repository-inert-v1",
        "status": "DISABLED",
        "activation_allowed": False,
        "credentials_issued": False,
        "actions_executed": 0,
        "reason_code": "LOCAL_ACTIVATION_DISABLED",
    }
    values.update(kwargs)
    with pytest.raises(DeploymentIdentityPolicyError) as captured:
        DeploymentIdentityActivationReceipt(**values)  # type: ignore[arg-type]
    assert captured.value.code == "ACTIVATION_RECEIPT_INVALID"
