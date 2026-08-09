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
        ("oidc_audience", "cloud-session-service"),
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
        "repository_secret_cloud_credential",
        "fork_pr_credential_issuance",
        "untrusted_ref_credential_issuance",
        "untrusted_environment_credential_issuance",
        "role_chaining",
        "privilege_escalation",
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
        ("trust_policy_payload", {"Statement": []}),
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
    ["self_approval", "approval_bypass", "deployment_without_approval"],
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
        ("live_provider_calls", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("external_writes", "ALLOWED", "FIXED_VALUE_VIOLATION"),
        ("credential_issuance", "ALLOWED", "FIXED_VALUE_VIOLATION"),
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
def test_every_github_aws_iam_credential_deploy_and_native_operation_is_forbidden(
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
    }


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
