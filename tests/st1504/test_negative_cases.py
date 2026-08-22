"""Hostile and exact-type validation cases for ST-1504."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st1504_github_oidc as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_INPUT_MARKER_1504"


def _validate(document: dict[str, Any]) -> generator.GithubOidcModel:
    return generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize("field", generator._selected_bindings())
def test_every_real_binding_policy_payload_and_tool_selection_must_remain_unset(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    current = document["selected_bindings"][field]
    document["selected_bindings"][field] = (
        [MARKER] if isinstance(current, list) else MARKER
    )
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    ["github_repository_numeric_id", "session_duration_seconds"],
)
@pytest.mark.parametrize("value", [True, False, 0, 1, "1"])
def test_unset_numeric_bindings_reject_bool_as_int_and_value_attempts(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["selected_bindings"][field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    ("field", "attempt"),
    [
        ("oidc_subject", "repo:organization/*"),
        ("oidc_subject", "repo:organization/repository"),
        ("github_repository", "organization/repository"),
        ("deploy_ref", "refs/heads/default"),
        ("github_environment_name", "production-like"),
        ("target_audience", "cloud-session-service"),
        ("workflow_ref", "organization/repository/.github/workflows/deploy.yml"),
    ],
)
def test_wildcard_partial_subject_repository_ref_environment_audience_and_workflow_attempts_fail(
    contract_document: dict[str, Any], field: str, attempt: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["selected_bindings"][field] = attempt
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert attempt not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    [
        "wildcard_trust",
        "fork_pull_request",
        "untrusted_pull_request",
        "untrusted_ref",
        "untrusted_environment",
        "pull_request_target_credential_path",
        "unbounded_reusable_workflow_caller",
        "broad_organization_subject",
        "broad_repository_subject",
        "broad_ref_subject",
        "broad_audience",
    ],
)
def test_every_forbidden_trust_broadening_remains_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["trust_constraints"][field] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    [
        "exact_repository_identity",
        "exact_trusted_ref",
        "exact_workflow_identity",
        "exact_environment",
        "exact_audience",
        "exact_subject",
    ],
)
def test_exact_trust_constraints_cannot_claim_configuration(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["trust_constraints"][field] = "CONFIGURED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("mutation", ["duplicate", "reorder", "remove"])
def test_required_claim_inventory_rejects_duplicates_reordering_and_omission(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    claims = document["trust_constraints"]["required_claim_bindings"]
    if mutation == "duplicate":
        claims[1] = claims[0]
    elif mutation == "reorder":
        claims[0], claims[1] = claims[1], claims[0]
    else:
        claims.pop()
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    [
        "long_lived_cloud_key",
        "static_provider_credential",
        "repository_secret_cloud_credential",
        "human_cloud_credential",
        "fork_pr_credential_issuance",
        "untrusted_ref_credential_issuance",
        "untrusted_environment_credential_issuance",
        "role_chaining",
        "privilege_escalation",
        "cross_environment_identity_reuse",
    ],
)
def test_long_lived_key_fork_untrusted_and_escalation_paths_remain_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["credential_boundary"][field] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("field", ["secret_names", "secret_values"])
def test_secret_name_or_value_inventory_attempt_is_rejected_without_echo(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["credential_boundary"][field] = [MARKER]
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("credential_material", "PRESENT"),
        ("credential_issuance_capability", "PRESENT"),
        ("oidc_session", "LONG_LIVED"),
        ("least_privilege", "CONFIGURED"),
    ],
)
def test_credential_absence_and_unconfigured_claims_cannot_be_promoted(
    contract_document: dict[str, Any], field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["credential_boundary"][field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    [
        "write_all",
        "admin_permissions",
        "secrets_access",
        "mutable_external_action_references",
        "unbounded_reusable_workflow_callers",
        "pull_request_target_credential_path",
    ],
)
def test_workflow_permission_pr_target_and_reusable_caller_escalation_is_rejected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["workflow_permission_intent"][field] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actual_workflow", "PRESENT"),
        ("id_token_write_scope", "WORKFLOW_WIDE"),
        ("contents_permission", "WRITE"),
    ],
)
def test_workflow_presence_broad_id_token_or_contents_write_attempt_is_rejected(
    contract_document: dict[str, Any], field: str, value: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["workflow_permission_intent"][field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "attempt"),
    [
        ("workflow_trigger_events", ["pull_request_target"]),
        ("reusable_workflow_callers", ["unbounded-caller"]),
        ("external_action_references", ["mutable-action-reference"]),
        ("workflow_permissions_payload", {"id-token": "write"}),
        ("federation_trust_material", {"Statement": []}),
        ("permission_policy_payload", {"Statement": []}),
    ],
)
def test_pr_target_reusable_action_permission_and_trust_payload_attempts_are_rejected(
    contract_document: dict[str, Any], field: str, attempt: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["selected_bindings"][field] = attempt
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"


@pytest.mark.parametrize(
    "field",
    [
        "self_approval",
        "approval_bypass",
        "deployment_without_approval",
        "cross_environment_target_reuse",
    ],
)
def test_production_approval_self_approval_and_bypass_paths_remain_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["environment_protection_intent"][field] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    "field",
    [
        "production_environment",
        "distinct_human_approval",
        "protected_environment",
        "exact_allowed_refs",
        "target_account_project_tenant_isolation",
    ],
)
def test_environment_protection_requirements_cannot_claim_configuration(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["environment_protection_intent"][field] = "CONFIGURED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("activation_enabled", True, "SAFE_BOUNDARY_VIOLATION"),
        ("activation_enabled", 0, "TYPE_MISMATCH"),
        ("network_access", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("credential_access", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("live_provider_calls", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("external_writes", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("credential_issuance", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("deploy_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("release_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("production_action", "ALLOWED", "FIXED_VALUE_VIOLATION"),
    ],
)
def test_activation_bool_as_int_live_write_and_issuance_attempts_are_rejected(
    contract_document: dict[str, Any],
    field: str,
    value: object,
    expected_code: str,
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"][field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == expected_code


@pytest.mark.parametrize("operation", generator.NATIVE_OPERATIONS)
def test_every_github_provider_credential_deploy_and_native_operation_is_forbidden(
    contract_document: dict[str, Any], operation: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["operations"][operation] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


@pytest.mark.parametrize("action", generator.ACTION_NAMES)
@pytest.mark.parametrize("value", [1, -1, True, "0"])
def test_planned_actions_require_exact_integer_zero(
    contract_document: dict[str, Any], action: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["execution_boundary"]["planned_actions"][action] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == (
        "SAFE_BOUNDARY_VIOLATION" if type(value) is int else "TYPE_MISMATCH"
    )


@pytest.mark.parametrize("mutation", ["missing", "unknown", "duplicate", "reorder"])
def test_capability_inventory_rejects_missing_unknown_duplicate_and_reordered_rows(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    rows = document["provider_neutral_deployment_identity_admission"][
        "capability_mapping_requirements"
    ]
    if mutation == "missing":
        rows.pop()
        expected = "MISSING_CAPABILITY_MAPPING"
    elif mutation == "unknown":
        rows[0]["capability_id"] = "unknown_capability"
        expected = "UNKNOWN_CAPABILITY_MAPPING"
    elif mutation == "duplicate":
        rows[1]["capability_id"] = rows[0]["capability_id"]
        expected = "DUPLICATE_CAPABILITY_MAPPING"
    else:
        rows[0], rows[1] = rows[1], rows[0]
        expected = "CAPABILITY_MAPPING_ORDER_DRIFT"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("configured_mapping_count", 1),
        ("complete_mapping", True),
        ("partial_mapping", "ALLOW"),
        ("implicit_mapping", "ALLOW"),
        ("provider_label_only_mapping", "ALLOW"),
        ("aws_label_only_mapping", "ALLOW"),
        ("source_label_only_mapping", "ALLOW"),
        ("reference_only_mapping", "ALLOW"),
    ],
)
def test_partial_label_and_claimed_complete_admission_attempts_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_deployment_identity_admission"]["mapping_policy"][
        field
    ] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code in {"SAFE_BOUNDARY_VIOLATION", "FIXED_VALUE_VIOLATION"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("admission_status", "ELIGIBLE"),
        ("eligible", True),
        ("selected_profile_id", "aws-by-label"),
        ("selected_profile_kind", "AWS"),
        ("selected_provider_name", "AWS"),
        ("default_profile_id", "aws-default"),
        ("fallback_profile_id", "aws-fallback"),
        ("concrete_alternate_provider_selected", True),
        ("eligibility_condition", "PROVIDER_LABEL_ONLY"),
    ],
)
def test_admission_eligibility_selection_default_and_fallback_fail_closed(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_deployment_identity_admission"][field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SAFE_BOUNDARY_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_mapping", "aws-label-only"),
        ("evidence_refs", ["aws-label-only"]),
        ("mapping_status", "CONFIGURED"),
    ],
)
def test_single_capability_or_aws_label_cannot_claim_mapping_or_evidence(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    row = document["provider_neutral_deployment_identity_admission"][
        "capability_mapping_requirements"
    ][0]
    row[field] = value
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
    }


@pytest.mark.parametrize("binding", tuple(generator._binding_policy())[:-2])
@pytest.mark.parametrize("mode", ["selected", "default", "fallback"])
def test_target_binding_default_and_fallback_attempts_fail_closed(
    contract_document: dict[str, Any], binding: str, mode: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_deployment_identity_admission"]["binding_policy"][
        binding
    ][mode] = MARKER
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SELECTION_MUST_REMAIN_UNSET"
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    "field",
    [
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ],
)
def test_aws_reference_labels_never_select_or_satisfy_admission(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["provider_neutral_deployment_identity_admission"][
        "aws_reference_boundary"
    ][field] = True
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "SAFE_BOUNDARY_VIOLATION"


@pytest.mark.parametrize(
    "field",
    (
        "identical_security_evidence",
        "identical_operations_evidence",
        "identical_release_evidence",
        "identical_provenance_evidence",
        "identical_audit_evidence",
        "identical_revocation_rollback_evidence",
        "identical_identity_session_evidence",
        "identical_isolation_residency_evidence",
        "provider_label_as_evidence",
        "aws_label_as_evidence",
        "github_source_label_as_evidence",
        "reference_metadata_as_evidence",
        "local_test_as_live_evidence",
    ),
)
def test_every_equivalent_evidence_requirement_rejects_downgrade(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    policy = document["provider_neutral_deployment_identity_admission"][
        "evidence_equivalence_policy"
    ]
    policy[field] = "OPTIONAL" if policy[field] == "REQUIRED" else "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_github_fixed_source_cannot_be_replaced_or_used_as_target_selection(
    contract_document: dict[str, Any],
) -> None:
    for field, value in (
        ("ci_source", "OTHER_CI"),
        ("oidc_source", "OTHER_OIDC"),
        ("external_review_connector", "OTHER_CONNECTOR"),
        ("target_provider_selected", True),
    ):
        document = copy.deepcopy(contract_document)
        document["ci_source_boundary"][field] = value
        with pytest.raises(generator.GithubOidcContractError) as captured:
            _validate(document)
        assert captured.value.code in {
            "FIXED_VALUE_VIOLATION",
            "SAFE_BOUNDARY_VIOLATION",
        }


@pytest.mark.parametrize(
    "field",
    [
        "audit_bypass",
        "revocation_bypass",
        "rollback_bypass",
        "irreversible_promotion",
    ],
)
def test_lifecycle_evidence_and_rollback_bypass_remain_forbidden(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["lifecycle_control_intent"][field] = "ALLOWED"
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_unknown_fields_are_rejected_without_echoing_names_or_values(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document[MARKER] = MARKER
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"
    assert MARKER not in str(captured.value)


def test_nested_iam_resource_like_unknown_field_is_rejected(
    contract_document: dict[str, Any],
) -> None:
    document = copy.deepcopy(contract_document)
    document["trust_constraints"]["iam_resource"] = {"type": "role"}
    with pytest.raises(generator.GithubOidcContractError) as captured:
        _validate(document)
    assert captured.value.code == "CLOSED_SCHEMA_VIOLATION"


def test_yaml_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(f"document: safe\ndocument: {MARKER}\n", encoding="utf-8")
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_INVALID"
    assert MARKER not in str(captured.value)


def test_yaml_aliases_are_forbidden_without_echoing_content(tmp_path: Path) -> None:
    path = tmp_path / "alias.yaml"
    path.write_text(f"value: &blocked {MARKER}\ncopy: *blocked\n", encoding="utf-8")
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_ALIAS_FORBIDDEN"
    assert MARKER not in str(captured.value)


def test_yaml_tags_are_forbidden_without_echoing_content(tmp_path: Path) -> None:
    path = tmp_path / "tag.yaml"
    path.write_text(f"value: !blocked {MARKER}\n", encoding="utf-8")
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.load_yaml(path)
    assert captured.value.code == "YAML_TAG_FORBIDDEN"
    assert MARKER not in str(captured.value)


def test_json_duplicate_keys_fail_with_sanitized_error(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(f'{{"safe": 1, "safe": "{MARKER}"}}', encoding="utf-8")
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.load_json(path)
    assert captured.value.code == "JSON_DUPLICATE_KEY"
    assert MARKER not in str(captured.value)


def test_source_inventory_drift_duplicate_and_reordering_fail_closed(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("digest", "duplicate", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "digest":
            document["sources"][0]["sha256"] = "0" * 64
        elif mutation == "duplicate":
            document["sources"][1] = copy.deepcopy(document["sources"][0])
        else:
            document["sources"][0], document["sources"][1] = (
                document["sources"][1],
                document["sources"][0],
            )
        with pytest.raises(generator.GithubOidcContractError) as captured:
            _validate(document)
        assert captured.value.code in {"SOURCE_DUPLICATE", "SOURCE_INVENTORY_DRIFT"}


def _copy_pinned_sources(target_root: Path) -> None:
    for relative in generator.PINNED_SOURCES:
        source = REPOSITORY_ROOT / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


@pytest.mark.parametrize("relative", tuple(generator.PREDECESSOR_SOURCES))
def test_each_predecessor_byte_drift_fails_closed(
    tmp_path: Path, contract_document: dict[str, Any], relative: str
) -> None:
    _copy_pinned_sources(tmp_path)
    predecessor = tmp_path / relative
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "SOURCE_DIGEST_MISMATCH"


def _rebind_source_digest(
    document: dict[str, Any],
    relative: str,
    new_digest: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if relative in generator.PREDECESSOR_SOURCES:
        predecessor_sources = dict(generator.PREDECESSOR_SOURCES)
        predecessor_sources[relative] = new_digest
        monkeypatch.setattr(generator, "PREDECESSOR_SOURCES", predecessor_sources)
        pinned_sources = {**generator.AUTHORITY_SOURCES, **predecessor_sources}
    else:
        authority_sources = dict(generator.AUTHORITY_SOURCES)
        authority_sources[relative] = new_digest
        monkeypatch.setattr(generator, "AUTHORITY_SOURCES", authority_sources)
        pinned_sources = {**authority_sources, **generator.PREDECESSOR_SOURCES}
    monkeypatch.setattr(generator, "PINNED_SOURCES", pinned_sources)
    for row in document["sources"]:
        if row["uri"] == f"repo://{relative}":
            row["sha256"] = new_digest
            break


@pytest.mark.parametrize(
    ("relative", "kind"),
    [
        ("changes/st-0107/contracts/pr-governance.v1.yaml", "governance_contract"),
        ("changes/st-0107/ruleset-policy.v1.json", "governance_desired_state"),
        (
            "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
            "foundation_handoff",
        ),
        (
            "changes/st-1501/contracts/terraform-foundation.v1.yaml",
            "foundation_contract",
        ),
        (
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
            "foundation_plan",
        ),
    ],
)
def test_each_predecessor_semantic_tamper_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    kind: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    path = tmp_path / relative
    if kind == "governance_contract":
        value = yaml.safe_load(path.read_bytes())
        value["ruleset_policy"]["bypass_actors"] = ["attempt"]
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    elif kind == "governance_desired_state":
        value = json.loads(path.read_bytes())
        value["document"]["live_status"] = "EXECUTED"
        path.write_text(json.dumps(value), encoding="utf-8")
    elif kind == "foundation_handoff":
        value = yaml.safe_load(path.read_bytes())
        value["decision"]["selected_profile"] = "attempt"
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    elif kind == "foundation_contract":
        value = yaml.safe_load(path.read_bytes())
        value["execution_boundary"]["activation_enabled"] = True
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    else:
        value = json.loads(path.read_bytes())
        value["planned_actions"]["create"] = 1
        path.write_text(json.dumps(value), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "FIXED_VALUE_VIOLATION",
        "SAFE_BOUNDARY_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "PREDECESSOR_SEMANTIC_DRIFT",
    }


@pytest.mark.parametrize(
    "section",
    (
        "document",
        "sources",
        "owner_bindings",
        "codeowners",
        "pull_request_template",
        "ruleset_policy",
        "activation",
    ),
)
def test_every_pr_governance_contract_section_rejects_semantic_drift(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "changes/st-0107/contracts/pr-governance.v1.yaml"
    path = tmp_path / relative
    value = yaml.safe_load(path.read_bytes())
    if section == "document":
        value[section]["formal_verification"] = "EXECUTED"
    elif section == "sources":
        value[section][0]["sha256"] = "0" * 64
    elif section == "owner_bindings":
        value[section]["status"] = "VERIFIED"
    elif section == "codeowners":
        value[section]["entries"][0]["roles"] = ["security"]
    elif section == "pull_request_template":
        value[section]["require_generated_or_ai_assisted_review"] = False
    elif section == "ruleset_policy":
        value[section]["strict_required_status_checks_policy"] = False
    else:
        value[section]["prerequisites"][0] = "bypassed"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"


@pytest.mark.parametrize(
    "field",
    (
        "id",
        "version",
        "story_id",
        "source_contract",
        "generated_by",
        "generation_command",
        "artifact_kind",
        "github_api_version",
        "live_status",
        "formal_tst_001",
    ),
)
def test_every_pr_governance_generated_provenance_field_rejects_drift(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "changes/st-0107/ruleset-policy.v1.json"
    path = tmp_path / relative
    value = json.loads(path.read_bytes())
    value["document"][field] = MARKER
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_SEMANTIC_DRIFT"
    assert MARKER not in str(captured.value)


def test_pr_governance_generated_format_drift_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "changes/st-0107/ruleset-policy.v1.json"
    path = tmp_path / relative
    value = json.loads(path.read_bytes())
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


def test_foundation_plan_deterministic_byte_drift_fails_after_digest_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
    path = tmp_path / relative
    value = json.loads(path.read_bytes())
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "PREDECESSOR_GENERATED_DRIFT"


@pytest.mark.parametrize(
    "section",
    [
        "schema",
        "version",
        "record_status",
        "approved_story",
        "approved_scope",
        "source_design_refs",
        "decision",
        "rationale",
        "rejected_alternatives",
        "constraints",
        "security_and_approval_gates",
        "acceptance_criteria",
        "required_test_evidence",
        "open_decision_state",
    ],
)
def test_every_normative_handoff_section_fails_after_hash_rebinding(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    section: str,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    value = yaml.safe_load(path.read_bytes())
    if section == "security_and_approval_gates":
        value[section] = ["ALLOW_SECURITY_GATE_BYPASS"]
    elif isinstance(value[section], list):
        value[section][0] = MARKER
    elif isinstance(value[section], dict):
        first = next(iter(value[section]))
        value[section][first] = MARKER
    else:
        value[section] = MARKER
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code in {
        "HANDOFF_SEMANTIC_DRIFT",
        "FIXED_VALUE_VIOLATION",
        "SELECTION_MUST_REMAIN_UNSET",
        "TYPE_MISMATCH",
    }
    assert MARKER not in str(captured.value)


def test_authority_semantic_drift_fails_even_if_digest_inventory_is_rebound(
    tmp_path: Path,
    contract_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _copy_pinned_sources(tmp_path)
    relative = "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"
    path = tmp_path / relative
    value = yaml.safe_load(path.read_bytes())
    for threat in value["threats"]:
        if threat["id"] == "THR-008":
            threat["controls"] = "weakened"
            break
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    document = copy.deepcopy(contract_document)
    _rebind_source_digest(document, relative, generator.sha256_file(path), monkeypatch)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(document, tmp_path)
    assert captured.value.code == "FIXED_VALUE_VIOLATION"


def test_contract_file_symlink_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    link = tmp_path / "contract.yaml"
    link.symlink_to(target)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.load_yaml(link)
    assert captured.value.code == "UNSAFE_FILE_TYPE"


def test_pinned_source_ancestor_symlink_is_rejected_without_escape(
    tmp_path: Path, contract_document: dict[str, Any]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "docs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(generator.GithubOidcContractError) as captured:
        generator.validate_contract(copy.deepcopy(contract_document), tmp_path)
    assert captured.value.code == "UNSAFE_ANCESTOR"
    assert list(outside.iterdir()) == []
