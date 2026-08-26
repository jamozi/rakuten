"""Canonical pinning, complete-row preservation, and proposal-only behavior."""

from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator
import pytest
import yaml

from scripts import build_st0005_status as status


EXPECTED_APPLY_IDENTITY_SCOPES = {
    "status": "STORY_SUITE_CLASS_CAPTURE",
    "pull_request_uri": "GLOBAL",
    "pull_request_changeset": "GLOBAL",
    "approval_artifact": "GLOBAL",
    "production_governance_artifact": ("STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"),
    "scope_decision_artifact": "STORY_AND_ARTIFACT_SHA256",
}
EXPECTED_VERIFICATION_COVERAGE = {
    "PASS": "EXACT_REQUIRED_SUITE_SET",
    "PARTIAL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
    "FAIL": "NONEMPTY_REQUIRED_SUITE_SUBSET",
    "REGRESSION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
    "EXPIRY": "NONEMPTY_REQUIRED_SUITE_SUBSET",
    "DEMOTION": "NONEMPTY_REQUIRED_SUITE_SUBSET",
}
EXPECTED_PRODUCTION_GOVERNANCE_ARTIFACTS = [
    "release_decision",
    "gate_report",
    "security_approval",
    "operations_approval",
]
EXPECTED_VERIFICATION_ONLY_MATRIX = [
    {"from": "FAIL", "to": "NOT_EXECUTED", "kind": "EXPIRY"},
    {"from": "FAIL", "to": "PARTIAL", "kind": "VERIFICATION_RESULT"},
    {"from": "FAIL", "to": "PASS", "kind": "VERIFICATION_RESULT"},
    {"from": "NOT_EXECUTED", "to": "FAIL", "kind": "VERIFICATION_RESULT"},
    {"from": "NOT_EXECUTED", "to": "PARTIAL", "kind": "VERIFICATION_RESULT"},
    {"from": "PARTIAL", "to": "FAIL", "kind": "VERIFICATION_RESULT"},
    {"from": "PARTIAL", "to": "NOT_EXECUTED", "kind": "EXPIRY"},
    {"from": "PARTIAL", "to": "PASS", "kind": "VERIFICATION_RESULT"},
    {"from": "PASS", "to": "FAIL", "kind": "REGRESSION"},
    {"from": "PASS", "to": "NOT_EXECUTED", "kind": "EXPIRY"},
    {"from": "PASS", "to": "PARTIAL", "kind": "REGRESSION"},
]
EXPECTED_EVIDENCE_CLASS_CONTRACTS = {
    "CHANGE_PLAN": {
        "environment_contract": "LOCAL",
        "allowed_results": ["PLANNED"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
    "LOCAL_IMPLEMENTATION": {
        "environment_contract": "LOCAL",
        "allowed_results": ["LOCAL_PASS"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
    "PR_CHANGESET": {
        "environment_contract": "CI",
        "allowed_results": ["PR_REVIEWED"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
    "RUNTIME_SUITE_RESULT": {
        "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
        "allowed_results_by_target_verification": {
            "PASS": ["PASS"],
            "PARTIAL": ["PASS", "PARTIAL"],
            "FAIL": ["FAIL"],
        },
        "formal_suite_status_contract": "EQUALS_TARGET_VERIFICATION",
    },
    "STAGING_DEPLOYMENT": {
        "environment_contract": "STAGING",
        "allowed_results": ["DEPLOYED"],
        "formal_suite_status_contract": "PASS",
    },
    "PRODUCTION_RELEASE": {
        "environment_contract": "PRODUCTION",
        "allowed_results": ["RELEASED"],
        "formal_suite_status_contract": "PASS",
    },
    "REGRESSION": {
        "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
        "allowed_results_by_target_verification": {
            "PARTIAL": ["PARTIAL"],
            "FAIL": ["FAIL"],
        },
        "formal_suite_status_contract": "EQUALS_TARGET_VERIFICATION",
    },
    "EXPIRY": {
        "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
        "allowed_results": ["EXPIRED"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
    "ROLLBACK_DECISION": {
        "environment_contract": "EACH_SUITE_CANONICAL_ENVIRONMENT",
        "allowed_results": ["ROLLBACK_APPROVED"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
    "SCOPE_DECISION": {
        "environment_contract": "LOCAL",
        "allowed_results": ["SCOPE_APPROVED"],
        "formal_suite_status_contract": "NOT_EXECUTED",
    },
}


def test_immutable_st0001_import_and_pinned_status_inputs_verify() -> None:
    status.assert_immutable_inputs()


def test_overlay_preserves_every_canonical_row_and_effective_status() -> None:
    overlay = status.build_overlay()
    assert overlay["counts"]["story_rows"] == 129
    assert overlay["counts"]["test_suite_rows"] == 32
    assert overlay["counts"]["environment_rows"] == 6
    assert overlay["counts"]["proposal_requests"] == len(overlay["proposals"])
    assert overlay["counts"]["applied_requests"] == len(overlay["applied_transitions"])
    assert len({row["story_id"] for row in overlay["stories"]}) == 129
    assert len({row["suite_id"] for row in overlay["test_suites"]}) == 32
    assert len({row["environment_id"] for row in overlay["environments"]}) == 6

    initial_proposed = {"ST-0001", "ST-0002", "ST-0003", "ST-0004", "ST-0005"}
    rows = {row["story_id"]: row for row in overlay["stories"]}
    for story_id in initial_proposed:
        assert rows[story_id]["effective_implementation_status"] == "NOT_STARTED"
        assert rows[story_id]["effective_verification_status"] == "NOT_EXECUTED"
        assert len(rows[story_id]["proposal_request_ids"]) == 1
    for proposal in overlay["proposals"]:
        change = proposal["changes"][0]
        assert (
            proposal["request_id"] in rows[change["story_id"]]["proposal_request_ids"]
        )
    assert overlay["applied_transitions"] == []
    assert overlay["policy"]["canonical_source_rows_and_files_are_immutable"] is True
    assert overlay["policy"]["effective_status_fields_change_only_via_apply"] is True
    assert overlay["policy"]["one_story_change_per_request"] is True
    assert overlay["policy"]["proposal_never_changes_effective_status"] is True
    assert overlay["policy"]["proposal_governance_fields"] == "FORBIDDEN"
    assert overlay["policy"]["authoritative_live_apply"] == (
        "BLOCKED_PENDING_GOVERNANCE"
    )
    assert overlay["policy"]["currently_executable_live_apply_transitions"] == []
    assert overlay["policy"]["live_apply_activation_requires"] == [
        "ST-0006",
        "ST-0107",
    ]
    assert overlay["policy"]["deployment_apply_activation_additionally_requires"] == [
        "ST-1505",
        "ST-1506",
        "ST-1607",
    ]
    assert overlay["policy"]["deployment_transition_pairs_in_offline_grammar"] is True
    assert (
        overlay["policy"]["implementation_transitions_involving_deployed_statuses"]
        == "BLOCKED_PENDING_TYPED_GATES"
    )
    assert overlay["policy"]["offline_replay_uses_committed_capture"] is True
    assert (
        overlay["policy"]["apply_status_evidence_must_postdate_latest_applied_approval"]
        is True
    )
    assert overlay["policy"]["apply_evidence_valid_through_approval_decision"] is True
    assert overlay["policy"]["offline_replay_wall_clock_independent"] is True
    assert (
        overlay["policy"]["live_future_request_observation_or_decision_timestamps"]
        == "REJECT"
    )
    assert (
        overlay["policy"]["evidence_expired_at_request_approval_or_live_reference"]
        == "REJECT"
    )
    assert overlay["policy"]["change_pr_scope_evidence_postdating_request"] == "REJECT"
    assert (
        overlay["policy"]["approval_or_production_evidence_postdating_decision"]
        == "REJECT"
    )
    assert overlay["policy"]["pull_request_uri_single_use"] is True
    assert overlay["policy"]["approval_artifact_single_use"] is True
    assert overlay["policy"]["status_evidence_atomic_identity_fields"] == [
        "story_id",
        "suite_id",
        "evidence_class",
        "source_capture_sha256",
    ]
    assert overlay["policy"]["apply_status_evidence_atomic_identity_single_use"] is True
    assert (
        overlay["policy"]["apply_evidence_identity_scopes"]
        == EXPECTED_APPLY_IDENTITY_SCOPES
    )
    assert (
        overlay["policy"]["production_governance_identity_scope"]
        == "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
    )
    assert (
        overlay["policy"]["scope_decision_identity_scope"]
        == "STORY_AND_ARTIFACT_SHA256"
    )
    assert (
        overlay["policy"]["production_and_scope_artifact_cross_story_reuse"]
        == "ALLOWED"
    )
    assert overlay["policy"]["scope_decision_separate_from_approval"] is True
    assert overlay["policy"]["scope_transition_requires_human_requester"] is True
    assert overlay["policy"]["scope_transition_requires_pr"] is True
    assert (
        overlay["policy"]["scope_transition_requires_distinct_human_approver"] is True
    )
    assert (
        overlay["policy"]["scope_transition_requires_separate_scope_authority_artifact"]
        is True
    )
    assert overlay["policy"]["expiry_invalidates_evidence"] == "EXACT_ACTIVE_SET"
    assert (
        overlay["policy"][
            "expiry_requested_at_and_observed_at_must_be_at_or_after_active_valid_until"
        ]
        is True
    )
    assert (
        overlay["policy"]["verification_evidence_coverage"]
        == EXPECTED_VERIFICATION_COVERAGE
    )
    assert (
        overlay["policy"]["production_governance_artifacts"]
        == EXPECTED_PRODUCTION_GOVERNANCE_ARTIFACTS
    )
    assert overlay["policy"]["production_governance_artifacts_must_be_distinct"] is True
    assert overlay["policy"]["explicit_null_temporal_or_governance_fields"] == (
        "REJECT"
    )
    assert overlay["policy"]["expires_at_strictly_after_observed_at"] is True
    assert overlay["policy"]["approval_decided_at_not_before_requested_at"] is True
    assert (
        overlay["policy"]["apply_requested_at_not_before_prior_approval_decision"]
        is True
    )
    assert overlay["policy"]["proposal_sources"] == ["NOT_STARTED", "IN_PROGRESS"]
    assert overlay["policy"]["proposal_targets"] == [
        "IN_PROGRESS",
        "IMPLEMENTED_NOT_VALIDATED",
    ]
    assert overlay["policy"]["proposal_verification_status"] == "NOT_EXECUTED"
    assert overlay["policy"]["verification_pass_requires_implementation_status"] == [
        "VALIDATED",
        "DEPLOYED_STAGING",
        "DEPLOYED_PRODUCTION",
    ]
    assert overlay["policy"]["scope_verification_status_coupling"] == {
        "DEFERRED_POST_MVP": "NOT_EXECUTED",
        "OUT_OF_SCOPE": "NOT_APPLICABLE",
        "OUT_OF_SCOPE_EXIT": "NOT_EXECUTED",
    }
    assert (
        overlay["policy"]["forward_validated_promotion_requires_verification"] == "PASS"
    )
    assert (
        overlay["policy"]["forward_deployment_promotion_requires_verification"]
        == "PASS"
    )
    assert (
        overlay["policy"]["verification_only_transition_does_not_change_implementation"]
        is True
    )

    suites = {row["suite_id"]: row for row in overlay["test_suites"]}
    assert suites["TST-016"]["canonical_environment_labels"] == ["staging"]
    assert suites["TST-016"]["canonical_environments"] == ["STAGING"]
    assert suites["TST-029"]["canonical_environment_labels"] == ["staging/recovery"]
    assert suites["TST-029"]["canonical_environments"] == ["RECOVERY"]


def test_every_proposal_is_one_story_and_exact_required_suite_hash_bound() -> None:
    overlay = status.build_overlay()
    stories = {row["story_id"]: row for row in overlay["stories"]}
    for proposal in overlay["proposals"]:
        assert proposal["outcome"] == "PENDING_PR_EVIDENCE_AND_APPLY_REQUEST"
        assert len(proposal["changes"]) == 1
        change = proposal["changes"][0]
        evidence = change["evidence"]
        assert {item["suite_id"] for item in evidence} == set(
            stories[change["story_id"]]["required_suites"]
        )
        assert all(item["environment"] == "LOCAL" for item in evidence)
        assert all(
            item["evidence_class"] == "LOCAL_IMPLEMENTATION" for item in evidence
        )
        for item in evidence:
            assert item["uri"].startswith("repo://changes/st-0005/evidence/")
            relative = item["uri"].removeprefix("repo://")
            assert status.sha256_file(status.REPO_ROOT / relative) == item["sha256"]


def test_append_only_evidence_snapshots_are_strict_and_source_owned() -> None:
    files = status.evidence_files()
    story_ids = {status.load_yaml(path)["story_id"] for path in files}
    assert {
        "ST-0001",
        "ST-0002",
        "ST-0003",
        "ST-0004",
        "ST-0005",
    } <= story_ids
    assert len(files) == len(
        {status.load_yaml(path)["document"]["id"] for path in files}
    )


def test_overlay_rejects_unreferenced_append_only_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed = status.evidence_files()
    orphan = (
        status.REPO_ROOT
        / "tests"
        / "st0005"
        / "fixtures"
        / "evidence"
        / "st0005-change-plan.yaml"
    )
    monkeypatch.setattr(status, "evidence_files", lambda: [*committed, orphan])
    with pytest.raises(RuntimeError, match="orphan=.*st0005-change-plan.yaml"):
        status.build_overlay()


def test_overlay_rejects_unreferenced_content_addressed_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    committed = status.evidence_artifact_files()
    orphan = (
        status.REPO_ROOT
        / "tests"
        / "st0005"
        / "fixtures"
        / "artifacts"
        / "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b-"
        "status-taxonomy.yaml"
    )
    monkeypatch.setattr(status, "evidence_artifact_files", lambda: [*committed, orphan])
    with pytest.raises(RuntimeError, match="artifact inventory mismatch: orphan="):
        status.build_overlay()


def test_status_v1_workflow_is_archived_and_status_v2_is_active() -> None:
    assert not (
        status.REPO_ROOT / ".github" / "workflows" / "status-registry.yml"
    ).exists()
    active = status.REPO_ROOT / "changes" / "status" / "status.v2.yaml"
    document = yaml.safe_load(active.read_text(encoding="utf-8"))
    assert document["document"]["version"] == "2.0.0"
    assert document["document"]["history"] == "GIT_AND_CI"


def test_base_record_digests_cover_complete_canonical_rows() -> None:
    overlay = status.build_overlay()
    _, story_document, suite_document, registry_taxonomy = status.canonical_inputs()
    del registry_taxonomy
    stories = status.index_records(
        story_document, collection="stories", source="canonical story catalog"
    )
    suites = status.index_records(
        suite_document, collection="suites", source="canonical suite catalog"
    )
    assert {
        row["story_id"]: row["base_record_sha256"] for row in overlay["stories"]
    } == {identifier: status.object_digest(row) for identifier, row in stories.items()}
    assert {
        row["suite_id"]: row["base_record_sha256"] for row in overlay["test_suites"]
    } == {identifier: status.object_digest(row) for identifier, row in suites.items()}


def test_generated_request_schema_is_strict_draft_2020_12() -> None:
    schema = status.request_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["changes"]["maxItems"] == 1


def test_generated_policy_exposes_capture_and_live_apply_boundaries() -> None:
    policy = status.build_policy()
    assert (
        policy["implementation"]["canonical_source_rows_and_files_are_immutable"]
        is True
    )
    assert (
        policy["implementation"]["effective_status_fields_change_only_via_apply"]
        is True
    )
    assert policy["implementation"]["one_story_change_per_request"] is True
    assert policy["proposal"] == {
        "changes_effective_status": False,
        "governance_fields": "FORBIDDEN",
        "implementation_sources": ["NOT_STARTED", "IN_PROGRESS"],
        "implementation_targets": [
            "IN_PROGRESS",
            "IMPLEMENTED_NOT_VALIDATED",
        ],
        "verification_status": "NOT_EXECUTED",
    }
    assert policy["authority"]["authoritative_live_apply"] == (
        "BLOCKED_PENDING_GOVERNANCE"
    )
    assert policy["authority"]["currently_executable_live_apply_transitions"] == []
    assert policy["authority"]["live_apply_activation_requires"] == [
        "ST-0006",
        "ST-0107",
    ]
    assert (
        policy["implementation"]["deployment_transition_pairs_in_offline_grammar"]
        is True
    )
    assert (
        policy["implementation"][
            "implementation_transitions_involving_deployed_statuses"
        ]
        == "BLOCKED_PENDING_TYPED_GATES"
    )
    assert (
        policy["implementation"]["verification_only_transition_matrix"]
        == EXPECTED_VERIFICATION_ONLY_MATRIX
    )
    assert policy["history"]["snapshot_content_addressed_capture_path_and_sha"] == (
        "REQUIRED"
    )
    assert policy["history"]["new_live_snapshot_original_path_and_sha"] == "REQUIRED"
    assert policy["history"]["offline_replay_uses_committed_capture"] is True
    assert (
        policy["history"]["apply_status_evidence_must_postdate_latest_applied_approval"]
        is True
    )
    assert policy["history"]["apply_evidence_valid_through_approval_decision"] is True
    assert policy["history"]["offline_replay_wall_clock_independent"] is True
    assert (
        policy["history"]["live_future_request_observation_or_decision_timestamps"]
        == "REJECT"
    )
    assert (
        policy["history"]["evidence_expired_at_request_approval_or_live_reference"]
        == "REJECT"
    )
    assert policy["history"]["change_pr_scope_evidence_postdating_request"] == "REJECT"
    assert (
        policy["history"]["approval_or_production_evidence_postdating_decision"]
        == "REJECT"
    )
    assert policy["history"]["pull_request_uri_single_use"] is True
    assert policy["history"]["approval_artifact_single_use"] is True
    assert policy["history"]["status_evidence_atomic_identity_fields"] == [
        "story_id",
        "suite_id",
        "evidence_class",
        "source_capture_sha256",
    ]
    assert policy["history"]["apply_status_evidence_atomic_identity_single_use"] is True
    assert (
        policy["history"]["apply_evidence_identity_scopes"]
        == EXPECTED_APPLY_IDENTITY_SCOPES
    )
    assert (
        policy["history"]["production_governance_identity_scope"]
        == "STORY_GOVERNANCE_ROLE_AND_ARTIFACT_SHA256"
    )
    assert (
        policy["history"]["scope_decision_identity_scope"]
        == "STORY_AND_ARTIFACT_SHA256"
    )
    assert (
        policy["history"]["production_and_scope_artifact_cross_story_reuse"]
        == "ALLOWED"
    )
    assert policy["history"]["scope_decision_separate_from_approval"] is True
    assert policy["history"]["expiry_invalidates_evidence"] == "EXACT_ACTIVE_SET"
    assert (
        policy["history"][
            "expiry_requested_at_and_observed_at_must_be_at_or_after_active_valid_until"
        ]
        is True
    )
    assert policy["history"]["requested_observed_expires_decided_timestamps"] == (
        "STRICT_UTC_RFC3339"
    )
    assert policy["history"]["explicit_null_temporal_or_governance_fields"] == (
        "REJECT"
    )
    assert policy["history"]["expires_at_strictly_after_observed_at"] is True
    assert policy["history"]["approval_decided_at_not_before_requested_at"] is True
    assert (
        policy["history"]["apply_requested_at_not_before_prior_approval_decision"]
        is True
    )
    assert policy["history"]["append_only_modify_delete_rename_enforcement"] == (
        "BASE_OWNED_PR_WORKFLOW"
    )
    assert policy["verification"]["evidence_coverage"] == (
        EXPECTED_VERIFICATION_COVERAGE
    )
    assert (
        policy["verification"][
            "verification_only_transitions_preserve_implementation_status"
        ]
        is True
    )
    assert policy["authority"]["production_governance_artifacts"] == (
        EXPECTED_PRODUCTION_GOVERNANCE_ARTIFACTS
    )
    assert (
        policy["authority"]["production_governance_artifacts_must_be_distinct"] is True
    )
    assert policy["authority"]["scope_transition_requires_human_requester"] is True
    assert policy["authority"]["scope_transition_requires_pr"] is True
    assert (
        policy["authority"]["scope_transition_requires_distinct_human_approver"] is True
    )
    assert (
        policy["authority"][
            "scope_transition_requires_separate_scope_authority_artifact"
        ]
        is True
    )
    assert (
        policy["implementation"]["forward_validated_promotion_requires_verification"]
        == "PASS"
    )
    assert (
        policy["implementation"]["forward_deployment_promotion_requires_verification"]
        == "PASS"
    )
    assert (
        policy["implementation"][
            "verification_only_transition_does_not_change_implementation"
        ]
        is True
    )
    assert policy["implementation"][
        "verification_pass_requires_implementation_status"
    ] == [
        "VALIDATED",
        "DEPLOYED_STAGING",
        "DEPLOYED_PRODUCTION",
    ]
    assert policy["implementation"]["scope_verification_status_coupling"] == {
        "DEFERRED_POST_MVP": "NOT_EXECUTED",
        "OUT_OF_SCOPE": "NOT_APPLICABLE",
        "OUT_OF_SCOPE_EXIT": "NOT_EXECUTED",
    }
    assert policy["demotion"]["pass_to_partial_or_fail_requires_regression"] is True
    assert (
        policy["demotion"][
            "ordinary_verification_reset_to_not_executed_requires_expiry"
        ]
        is True
    )
    assert (
        policy["demotion"]["scope_exit_reset_to_not_executed_requires_scope_decision"]
        is True
    )
    assert policy["evidence_classes"] == EXPECTED_EVIDENCE_CLASS_CONTRACTS


def test_committed_requests_validate_against_generated_json_schema() -> None:
    validator = Draft202012Validator(status.request_schema())
    for path in status.request_files():
        request = status.load_yaml(path)
        assert list(validator.iter_errors(request)) == []


def test_unique_key_loader_rejects_duplicate_yaml_mapping_key(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("document:\n  id: ONE\n  id: TWO\n", encoding="utf-8")
    try:
        status.load_yaml(duplicate)
    except yaml.YAMLError as exc:
        assert "duplicate key" in str(exc)
    else:
        raise AssertionError("duplicate YAML key was accepted")
