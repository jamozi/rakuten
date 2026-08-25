"""Positive offline runtime and repository-inert fixture coverage for ST-1504."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from raos.adapters.disabled_deployment_identity import (
    DisabledDeploymentIdentityActivation,
)
from raos.domain.deployment_identity import (
    OfflineTrustPolicy,
    RecordedClaimEnvelope,
    evaluate_recorded_claims,
)
from raos.ports.deployment_identity import DeploymentIdentityActivationCommand
from scripts import build_st1504_github_oidc as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _json_fixture(relative: Path) -> dict[str, Any]:
    value = generator.load_json(REPOSITORY_ROOT / relative)
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_recorded_claim_shape_is_token_free_and_explicitly_unauthenticated() -> None:
    document = _json_fixture(generator.CLAIMS_FIXTURE_PATH)
    envelope = RecordedClaimEnvelope.from_document(document)
    assert envelope.fixture_id == generator.FIXTURE_ID
    assert document["authentication_status"] == "NOT_AUTHENTICATED"
    assert document["signature_verification_status"] == "NOT_PERFORMED"
    assert document["token_material"] == "ABSENT"
    assert set(document["claims"]) == set(generator.RECORDED_CLAIM_KEYS)
    assert not ({"jwt", "token", "header", "signature"} & set(document))


def test_offline_policy_matches_exact_recorded_claims_without_granting_authority() -> (
    None
):
    envelope = RecordedClaimEnvelope.from_document(
        _json_fixture(generator.CLAIMS_FIXTURE_PATH)
    )
    policy = OfflineTrustPolicy.from_document(
        _json_fixture(generator.TRUST_POLICY_FIXTURE_PATH)
    )
    result = evaluate_recorded_claims(policy, envelope)
    expected = _json_fixture(generator.EVALUATION_FIXTURE_PATH)
    assert result.policy_match is True
    assert result.classification == "OFFLINE_POLICY_MATCH_ONLY_NOT_AUTHENTICATION"
    assert result.authentication_status == "NOT_AUTHENTICATED"
    assert result.signature_verification_status == "NOT_PERFORMED"
    assert result.credential_issuance_authorized is False
    assert result.activation_authorized is False
    assert result.deployment_authorized is False
    assert result.action_count == 0
    assert list(result.reason_codes) == expected["reason_codes"]
    assert result.evidence_digest == expected["evidence_digest"]
    assert expected["formal_evidence"] == "NOT_EXECUTED"


def test_disabled_activation_port_returns_zero_action_refusal() -> None:
    envelope = RecordedClaimEnvelope.from_document(
        _json_fixture(generator.CLAIMS_FIXTURE_PATH)
    )
    policy = OfflineTrustPolicy.from_document(
        _json_fixture(generator.TRUST_POLICY_FIXTURE_PATH)
    )
    evaluation = evaluate_recorded_claims(policy, envelope)
    command = DeploymentIdentityActivationCommand(
        policy_id=policy.policy_id,
        fixture_id=envelope.fixture_id,
        evaluation_digest=evaluation.evidence_digest,
    )
    receipt = DisabledDeploymentIdentityActivation().activate(command)
    assert receipt.status == "DISABLED"
    assert receipt.activation_allowed is False
    assert receipt.credentials_issued is False
    assert receipt.actions_executed == 0
    assert receipt.reason_code == "LOCAL_ACTIVATION_DISABLED"


def test_workflow_fixture_is_valid_yaml_repository_inert_and_fail_closed() -> None:
    path = REPOSITORY_ROOT / generator.WORKFLOW_FIXTURE_PATH
    workflow = yaml.safe_load(path.read_bytes())
    assert workflow == generator.inert_workflow_document()
    assert ".github/workflows" not in path.as_posix()
    assert workflow["on"] == {"workflow_dispatch": {}}
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {"recorded_deployment_identity_fixture"}
    job = workflow["jobs"]["recorded_deployment_identity_fixture"]
    assert job["if"] == "${{ false }}"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert job["environment"] == "production-fixture-disabled"
    assert job["steps"] == [
        {
            "name": "Fail-closed repository-inert fixture sentinel",
            "shell": "bash",
            "run": "set -euo pipefail\nexit 1\n",
        }
    ]


def test_recorded_policy_requires_bounded_session_approval_and_lifecycle() -> None:
    policy = _json_fixture(generator.TRUST_POLICY_FIXTURE_PATH)
    assert policy["session"] == {
        "requested_duration_seconds": 600,
        "maximum_duration_seconds": 900,
        "permission_scopes": ["deployment-fixture:evaluate"],
        "least_privilege_required": True,
        "role_chaining_allowed": False,
        "privilege_escalation_allowed": False,
        "static_credentials_allowed": False,
        "human_credentials_allowed": False,
        "cross_environment_reuse_allowed": False,
    }
    assert policy["approval"] == {
        "protected_environment_required": True,
        "distinct_human_approval_required": True,
        "self_approval_allowed": False,
        "bypass_allowed": False,
        "approval_record_status": "NOT_EXECUTED",
    }
    assert policy["lifecycle"] == {
        "signed_provenance_required": True,
        "immutable_audit_required": True,
        "revocation_required": True,
        "rollback_required": True,
        "evidence_retention_required": True,
        "evidence_status": "RECORDED_FIXTURE_ONLY_NOT_FORMAL",
    }
    assert policy["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "planned_actions": {"create": 0, "delete": 0, "update": 0},
    }


def test_fixture_values_are_synthetic_and_do_not_select_live_bindings() -> None:
    claims = _json_fixture(generator.CLAIMS_FIXTURE_PATH)["claims"]
    assert claims["iss"].endswith(".invalid")
    assert claims["aud"].endswith(".invalid")
    assert "fixture" in claims["repository"]
    assert "fixture" in claims["ref"]
    assert "fixture" in claims["environment"]
    contract = generator.load_and_validate_contract(REPOSITORY_ROOT).contract
    assert all(
        value is None or value == [] for value in contract["selected_bindings"].values()
    )


def test_offline_runtime_modules_have_no_provider_or_network_imports() -> None:
    paths = (
        REPOSITORY_ROOT / "python/raos/domain/deployment_identity.py",
        REPOSITORY_ROOT / "python/raos/ports/deployment_identity.py",
        REPOSITORY_ROOT / "python/raos/adapters/disabled_deployment_identity.py",
    )
    forbidden = (
        "boto3",
        "botocore",
        "requests",
        "socket",
        "subprocess",
        "urllib",
        "httpx",
        "os.environ",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert all(fragment not in source for fragment in forbidden)
