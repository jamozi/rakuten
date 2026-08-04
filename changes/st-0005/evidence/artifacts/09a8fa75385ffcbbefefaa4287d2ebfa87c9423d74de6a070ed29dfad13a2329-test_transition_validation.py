"""Negative promotion, evidence, authority, and concurrency tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts import build_st0005_status as status
from conftest import (
    TEST_ARTIFACT_PREFIX,
    TEST_EVIDENCE_PREFIX,
    apply_request,
    repo_evidence,
    set_story_state,
)


Context = tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]


def validate(request: dict[str, Any], context: Context) -> dict[str, Any]:
    state, stories, suites = context
    return status.validate_request(
        request,
        state=state,
        story_index=stories,
        suite_index=suites,
        evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
        artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
    )


def validate_and_apply(request: dict[str, Any], context: Context) -> dict[str, Any]:
    validated = validate(request, context)
    status.apply_validated_request(context[0], validated)
    return validated


def base_apply(context: Context) -> dict[str, Any]:
    state, stories, _ = context
    return apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
    )


def test_adjacent_forward_apply_is_accepted(canonical_context: Context) -> None:
    request = base_apply(canonical_context)
    validated = validate(request, canonical_context)
    assert validated["transition_kinds"] == ["FORWARD"]


def test_apply_requires_exactly_one_story(canonical_context: Context) -> None:
    request = base_apply(canonical_context)
    request["changes"].append(deepcopy(request["changes"][0]))
    request["changes"][1]["story_id"] = "ST-0001"
    with pytest.raises(RuntimeError, match="exactly one Story"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda request: request.update({"unknown": True}), "strict field"),
        (
            lambda request: request["changes"][0].update({"unknown": True}),
            "strict field",
        ),
        (
            lambda request: request["changes"][0].update({"story_id": "ST-9999"}),
            "unknown story",
        ),
        (
            lambda request: request["changes"][0]["target"].update(
                {"implementation_status": "MAGIC"}
            ),
            "unknown or non-transitionable",
        ),
        (
            lambda request: request["changes"][0]["evidence"][0].update(
                {"suite_id": "TST-999"}
            ),
            "unknown suite",
        ),
    ],
)
def test_unknown_fields_story_suite_and_status_are_rejected(
    canonical_context: Context, mutation: Any, message: str
) -> None:
    request = base_apply(canonical_context)
    mutation(request)
    with pytest.raises(RuntimeError, match=message):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda request: request["document"].update({"schema_version": True}),
        lambda request: request["requested_by"].update({"id": "x"}),
        lambda request: request["approval"]["approver"].update({"id": "y"}),
    ],
)
def test_runtime_rejects_representative_values_rejected_by_generated_schema(
    canonical_context: Context, mutation: Any
) -> None:
    request = base_apply(canonical_context)
    mutation(request)
    assert list(Draft202012Validator(status.request_schema()).iter_errors(request))
    with pytest.raises(RuntimeError):
        validate(request, canonical_context)


@pytest.mark.parametrize("location", ["change", "pr", "approval", "scope"])
def test_explicit_null_expiry_is_rejected_by_schema_and_runtime(
    canonical_context: Context, location: str
) -> None:
    state, stories, _ = canonical_context
    if location == "scope":
        request = apply_request(
            state,
            stories,
            source_implementation="NOT_STARTED",
            source_verification="NOT_EXECUTED",
            target_implementation="OUT_OF_SCOPE",
            target_verification="NOT_APPLICABLE",
            evidence_class="SCOPE_DECISION",
            environment="LOCAL",
        )
        request["scope_decision_evidence"] = repo_evidence(
            f"{TEST_ARTIFACT_PREFIX}"
            "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
            "test-catalog.yaml"
        )
        request["scope_decision_evidence"]["expires_at"] = None
    else:
        request = base_apply(canonical_context)
        target = {
            "change": request["changes"][0]["evidence"][0],
            "pr": request["pr_evidence"],
            "approval": request["approval"]["evidence"],
        }[location]
        target["expires_at"] = None
    assert list(Draft202012Validator(status.request_schema()).iter_errors(request))
    with pytest.raises(RuntimeError, match="invalid string.*expires_at"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    "name",
    ["release_decision", "gate_report", "security_approval", "operations_approval"],
)
def test_production_governance_explicit_null_expiry_is_rejected(
    canonical_context: Context, name: str
) -> None:
    artifact_paths = [
        f"{TEST_ARTIFACT_PREFIX}"
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e-"
        "manifest.json",
        f"{TEST_ARTIFACT_PREFIX}"
        "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8-"
        "status-registry.yaml",
        f"{TEST_ARTIFACT_PREFIX}"
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d-"
        "story-backlog.yaml",
        f"{TEST_ARTIFACT_PREFIX}"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml",
    ]
    production = {
        key: repo_evidence(path)
        for key, path in zip(
            (
                "release_decision",
                "gate_report",
                "security_approval",
                "operations_approval",
            ),
            artifact_paths,
        )
    }
    production[name]["expires_at"] = None
    request = base_apply(canonical_context)
    request["production_approval_evidence"] = production
    assert list(Draft202012Validator(status.request_schema()).iter_errors(request))
    with pytest.raises(RuntimeError, match="invalid string.*expires_at"):
        status.validate_production_approval_evidence(
            production, artifact_uri_prefix=TEST_ARTIFACT_PREFIX
        )


def test_snapshot_optional_fields_reject_explicit_null(tmp_path: Path) -> None:
    source = status.REPO_ROOT / TEST_EVIDENCE_PREFIX / "st0005-change-plan.yaml"
    valid_until = status.load_yaml(source)
    valid_until["document"]["valid_until"] = None
    valid_until_path = tmp_path / "valid-until-null.yaml"
    status.write_yaml(valid_until_path, valid_until)
    with pytest.raises(RuntimeError, match="invalid string.*valid_until"):
        status.validate_evidence_snapshot(
            valid_until_path,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
            known_suite_ids={"TST-001"},
        )

    invalidates = status.load_yaml(source)
    invalidates["invalidates_evidence_sha256"] = None
    invalidates_path = tmp_path / "invalidates-null.yaml"
    status.write_yaml(invalidates_path, invalidates)
    with pytest.raises(RuntimeError, match="only EXPIRY snapshots"):
        status.validate_evidence_snapshot(
            invalidates_path,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
            known_suite_ids={"TST-001"},
        )


def test_required_suite_omission_is_rejected(canonical_context: Context) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        story_id="ST-0002",
    )
    request["changes"][0]["evidence"].pop()
    with pytest.raises(RuntimeError, match="required suite evidence mismatch"):
        validate(request, canonical_context)


def test_wrong_evidence_class_and_environment_are_rejected(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    evidence = request["changes"][0]["evidence"][0]
    evidence["evidence_class"] = "RUNTIME_SUITE_RESULT"
    evidence["environment"] = "CI"
    with pytest.raises(RuntimeError, match="evidence class"):
        validate(request, canonical_context)


def test_suite_evidence_must_use_append_only_snapshot(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["changes"][0]["evidence"][0] = repo_evidence(
        "changes/st-0005/README.md",
        suite_id="TST-001",
        environment="LOCAL",
        evidence_class="CHANGE_PLAN",
    )
    with pytest.raises(RuntimeError, match="append-only evidence snapshot"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    ("fixture_name", "message"),
    [
        ("st0002-change-plan.yaml", "snapshot Story mismatch"),
        ("st0005-runtime-partial.yaml", "snapshot class mismatch"),
        ("st0005-change-plan-wrong-suite.yaml", "exactly one result"),
        ("st0005-change-plan-wrong-environment.yaml", "environment mismatch"),
        ("st0005-change-plan-wrong-result.yaml", "inconsistent"),
        ("st0005-change-plan-unknown-suite.yaml", "unknown canonical Suite ID"),
    ],
)
def test_snapshot_cannot_be_relabelled_across_binding_dimensions(
    canonical_context: Context, fixture_name: str, message: str
) -> None:
    request = base_apply(canonical_context)
    evidence = request["changes"][0]["evidence"][0]
    fixture_path = f"{TEST_EVIDENCE_PREFIX}{fixture_name}"
    evidence["uri"] = f"repo://{fixture_path}"
    evidence["sha256"] = status.sha256_file(status.REPO_ROOT / fixture_path)
    with pytest.raises(RuntimeError, match=message):
        validate(request, canonical_context)


def test_stale_effective_digest_and_stale_row_are_rejected(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["expected"]["effective_status_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="lost update"):
        validate(request, canonical_context)

    request = base_apply(canonical_context)
    request["changes"][0]["expected"]["implementation_status"] = "IN_PROGRESS"
    with pytest.raises(RuntimeError, match="lost update"):
        validate(request, canonical_context)


def test_skipped_forward_and_non_adjacent_demotion_are_rejected(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["changes"][0]["target"]["implementation_status"] = (
        "IMPLEMENTED_NOT_VALIDATED"
    )
    with pytest.raises(RuntimeError, match="forbidden implementation transition"):
        validate(request, canonical_context)

    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="DEPLOYED_STAGING",
        source_verification="PASS",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
    )
    with pytest.raises(RuntimeError, match="forbidden implementation transition"):
        validate(request, canonical_context)


def test_regression_can_drive_adjacent_demotion(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
    )
    validated = validate(request, canonical_context)
    assert validated["transition_kinds"] == ["DEMOTION"]


def test_rollback_demotion_must_preserve_verification_result(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="NOT_EXECUTED",
        target_implementation="NOT_STARTED",
        target_verification="NOT_EXECUTED",
        evidence_class="ROLLBACK_DECISION",
        environment="CI",
    )
    assert validate(request, canonical_context)["transition_kinds"] == ["DEMOTION"]

    request["changes"][0]["evidence"][0]["evidence_class"] = "REGRESSION"
    with pytest.raises(RuntimeError, match="inconsistent with required"):
        validate(request, canonical_context)


def test_demotion_cannot_change_verification_without_matching_evidence_class(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
    )
    evidence = request["changes"][0]["evidence"][0]
    rollback_path = f"{TEST_EVIDENCE_PREFIX}st0005-rollback.yaml"
    evidence.update(
        {
            "evidence_class": "ROLLBACK_DECISION",
            "uri": f"repo://{rollback_path}",
            "sha256": status.sha256_file(status.REPO_ROOT / rollback_path),
        }
    )
    with pytest.raises(RuntimeError, match="inconsistent with required"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    ("source", "target", "evidence_class"),
    [
        ("NOT_EXECUTED", "PARTIAL", "RUNTIME_SUITE_RESULT"),
        ("NOT_EXECUTED", "FAIL", "RUNTIME_SUITE_RESULT"),
    ],
)
def test_verification_only_updates_are_supported_without_impl_transition(
    canonical_context: Context,
    source: str,
    target: str,
    evidence_class: str,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IMPLEMENTED_NOT_VALIDATED",
        source_verification=source,
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification=target,
        evidence_class=evidence_class,
        environment="CI",
    )
    validated = validate(request, canonical_context)
    assert validated["transition_kinds"][0] == "VERIFICATION_RESULT"


def test_deployed_fact_can_record_regression_and_bound_expiry_without_impl_change(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    regression = apply_request(
        state,
        stories,
        source_implementation="DEPLOYED_PRODUCTION",
        source_verification="PASS",
        target_implementation="DEPLOYED_PRODUCTION",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
    )
    assert validate(regression, canonical_context)["transition_kinds"] == ["REGRESSION"]

    old_snapshot = status.REPO_ROOT / TEST_EVIDENCE_PREFIX / "st0005-seq-pass-old.yaml"
    old_digest = status.sha256_file(old_snapshot)
    control = status.transition_control(state)
    control["story_active_evidence_sha256"]["ST-0005"] = [old_digest]
    control["story_active_evidence_observed_at"]["ST-0005"] = "2026-08-01T08:00:00Z"
    control["story_active_evidence_valid_until"]["ST-0005"] = "2026-08-02T00:00:00Z"
    expiry = apply_request(
        state,
        stories,
        source_implementation="DEPLOYED_PRODUCTION",
        source_verification="PASS",
        target_implementation="DEPLOYED_PRODUCTION",
        target_verification="NOT_EXECUTED",
        evidence_class="EXPIRY",
        environment="CI",
        fixture_name="st0005-seq-expiry.yaml",
        request_number=2,
        requested_at="2026-08-03T09:00:00Z",
        evidence_observed_at="2026-08-03T08:00:00Z",
        pr_observed_at="2026-08-03T08:30:00Z",
        approval_decided_at="2026-08-03T09:30:00Z",
    )
    assert validate(expiry, canonical_context)["transition_kinds"] == ["EXPIRY"]


def test_partial_and_failure_evidence_may_be_nonempty_required_suite_subset(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IMPLEMENTED_NOT_VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        story_id="ST-0002",
    )
    request["changes"][0]["evidence"] = request["changes"][0]["evidence"][:1]
    assert validate(request, canonical_context)["transition_kinds"] == [
        "VERIFICATION_RESULT"
    ]

    request["changes"][0]["evidence"] = []
    with pytest.raises(RuntimeError, match="nonempty subset"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    ("story_id", "environment"),
    [("ST-0505", "STAGING"), ("ST-1606", "RECOVERY")],
)
def test_canonical_suite_environment_labels_are_normalized(
    canonical_context: Context, story_id: str, environment: str
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IMPLEMENTED_NOT_VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment=environment,
        story_id=story_id,
    )
    assert validate(request, canonical_context)["transition_kinds"] == [
        "VERIFICATION_RESULT"
    ]
    request["changes"][0]["evidence"][0]["environment"] = "STAGING"
    if environment == "RECOVERY":
        with pytest.raises(RuntimeError, match="not declared"):
            validate(request, canonical_context)


def test_regression_demotion_does_not_wait_for_every_required_suite(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
        story_id="ST-0002",
    )
    request["changes"][0]["evidence"] = request["changes"][0]["evidence"][:1]
    assert validate(request, canonical_context)["transition_kinds"] == ["DEMOTION"]


def test_verification_pass_requires_validated_and_runtime_suite_evidence(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IMPLEMENTED_NOT_VALIDATED",
        source_verification="PARTIAL",
        target_implementation="IMPLEMENTED_NOT_VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
    )
    with pytest.raises(RuntimeError, match="PASS requires"):
        validate(request, canonical_context)


def test_validated_promotion_requires_human_requester_and_runtime_evidence(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="IMPLEMENTED_NOT_VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        requester_type="AUTOMATION",
    )
    with pytest.raises(RuntimeError, match="only be requested by a human"):
        validate(request, canonical_context)


def test_automation_approval_and_self_approval_are_rejected(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["approval"]["approver"]["actor_type"] = "AUTOMATION"
    with pytest.raises(RuntimeError, match="approval must come from a human"):
        validate(request, canonical_context)

    request = base_apply(canonical_context)
    request["approval"]["approver"]["id"] = request["requested_by"]["id"]
    with pytest.raises(RuntimeError, match="cannot approve"):
        validate(request, canonical_context)


def test_apply_requires_pr_and_approval_while_propose_forbids_them(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    del request["pr_evidence"]
    with pytest.raises(RuntimeError, match="requires PR evidence"):
        validate(request, canonical_context)

    proposal = base_apply(canonical_context)
    proposal["document"]["intent"] = "PROPOSE"
    del proposal["pr_evidence"]
    with pytest.raises(RuntimeError, match="PROPOSE must not"):
        validate(proposal, canonical_context)


def test_live_pr_context_must_match_request(
    canonical_context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = base_apply(canonical_context)
    state, stories, suites = canonical_context
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    monkeypatch.setenv("RAOS_PR_URI", "https://github.com/example/raos/pull/999")
    monkeypatch.setenv("RAOS_STATUS_PR_HEAD_SHA", "2" * 40)
    monkeypatch.setenv("RAOS_BASE_SHA", "0" * 40)
    with pytest.raises(RuntimeError, match="live GitHub context"):
        status.validate_request(
            request,
            state=state,
            story_index=stories,
            suite_index=suites,
            require_pr_context=True,
            evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
        )


def test_live_pr_context_accepts_prior_implementation_commit_ancestor(
    canonical_context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = base_apply(canonical_context)
    state, stories, suites = canonical_context
    current_head = "2" * 40
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("RAOS_PR_URI", request["pr_evidence"]["uri"])
    monkeypatch.setenv("RAOS_STATUS_PR_HEAD_SHA", current_head)
    monkeypatch.setenv("RAOS_BASE_SHA", "0" * 40)

    def fake_run(command: list[str], **_kwargs: object) -> Any:
        if command[1:3] == ["rev-parse", "HEAD"]:
            return status.subprocess.CompletedProcess(
                command, 0, stdout=f"{current_head}\n", stderr=""
            )
        assert command[1:3] == ["merge-base", "--is-ancestor"]
        return status.subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(status.subprocess, "run", fake_run)
    validated = status.validate_request(
        request,
        state=state,
        story_index=stories,
        suite_index=suites,
        require_pr_context=True,
        evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
        artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
    )
    assert validated["pr_evidence"]["implementation_commit_sha"] == "1" * 40


def test_live_pr_rejects_base_commit_as_implementation(
    canonical_context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = base_apply(canonical_context)
    state, stories, suites = canonical_context
    base = request["pr_evidence"]["implementation_commit_sha"]
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("RAOS_PR_URI", request["pr_evidence"]["uri"])
    monkeypatch.setenv("RAOS_STATUS_PR_HEAD_SHA", "2" * 40)
    monkeypatch.setenv("RAOS_BASE_SHA", base)
    with pytest.raises(RuntimeError, match="distinct commit inside the PR"):
        status.validate_request(
            request,
            state=state,
            story_index=stories,
            suite_index=suites,
            require_pr_context=True,
            evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda request: request.update(
                {"requested_at": "2026-08-01T09:00:00+00:00"}
            ),
            "strict UTC RFC3339",
        ),
        (
            lambda request: request["changes"][0]["evidence"][0].update(
                {"expires_at": "2026-08-01T08:30:00Z"}
            ),
            "expires_at must equal snapshot valid_until",
        ),
        (
            lambda request: request["approval"].update(
                {"decided_at": "2026-08-01T08:59:59Z"}
            ),
            "must not precede requested_at",
        ),
        (
            lambda request: request["changes"][0]["evidence"][0].update(
                {"observed_at": "2026-08-01T09:15:00Z"}
            ),
            "observed_at must equal snapshot recorded_at",
        ),
    ],
)
def test_temporal_audit_and_expiry_rules_reject_invalid_evidence(
    canonical_context: Context, mutation: Any, message: str
) -> None:
    request = base_apply(canonical_context)
    mutation(request)
    with pytest.raises(RuntimeError, match=message):
        validate(request, canonical_context)


def test_change_evidence_must_remain_valid_through_approval(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        evidence_expires_at="2026-08-02T00:00:00Z",
        approval_decided_at="2026-08-02T00:00:00Z",
    )
    with pytest.raises(RuntimeError, match="expired evidence.*approved request change"):
        validate(request, canonical_context)


def test_pr_evidence_must_remain_valid_through_approval(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["pr_evidence"]["expires_at"] = "2026-08-01T09:15:00Z"
    with pytest.raises(RuntimeError, match="expired evidence.*approved request.pr"):
        validate(request, canonical_context)


def test_scope_evidence_must_remain_valid_through_approval(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="OUT_OF_SCOPE",
        target_verification="NOT_APPLICABLE",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
    )
    request["scope_decision_evidence"] = repo_evidence(
        f"{TEST_ARTIFACT_PREFIX}"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml",
        expires_at="2026-08-01T09:15:00Z",
    )
    with pytest.raises(RuntimeError, match="expired evidence.*approved request.scope"):
        validate(request, canonical_context)


@pytest.mark.parametrize(
    ("source_implementation", "target_implementation", "evidence_class", "fresh"),
    [
        (
            "NOT_STARTED",
            "IN_PROGRESS",
            "CHANGE_PLAN",
            "st0005-seq-change-plan-fresh.yaml",
        ),
        (
            "IN_PROGRESS",
            "NOT_STARTED",
            "ROLLBACK_DECISION",
            "st0005-seq-rollback-fresh.yaml",
        ),
    ],
)
def test_active_observation_gate_covers_forward_and_demotion_families(
    canonical_context: Context,
    source_implementation: str,
    target_implementation: str,
    evidence_class: str,
    fresh: str,
) -> None:
    state, stories, _ = canonical_context
    set_story_state(
        state,
        story_id="ST-0005",
        implementation_status=source_implementation,
        verification_status="NOT_EXECUTED",
    )
    control = status.transition_control(state)
    active_path = (
        status.REPO_ROOT / TEST_EVIDENCE_PREFIX / "st0005-seq-partial-fresh.yaml"
    )
    control["story_active_evidence_sha256"]["ST-0005"] = [
        status.sha256_file(active_path)
    ]
    control["story_active_evidence_observed_at"]["ST-0005"] = "2026-08-01T12:00:00Z"
    stale = apply_request(
        state,
        stories,
        source_implementation=source_implementation,
        source_verification="NOT_EXECUTED",
        target_implementation=target_implementation,
        target_verification="NOT_EXECUTED",
        evidence_class=evidence_class,
        environment="LOCAL" if evidence_class == "CHANGE_PLAN" else "CI",
    )
    with pytest.raises(RuntimeError, match="status-changing evidence must postdate"):
        validate(stale, canonical_context)

    fresh_request = apply_request(
        state,
        stories,
        source_implementation=source_implementation,
        source_verification="NOT_EXECUTED",
        target_implementation=target_implementation,
        target_verification="NOT_EXECUTED",
        evidence_class=evidence_class,
        environment="LOCAL" if evidence_class == "CHANGE_PLAN" else "CI",
        fixture_name=fresh,
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T13:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    validate(fresh_request, canonical_context)


def test_propose_remains_non_effective_despite_apply_watermarks(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    control = status.transition_control(state)
    control["story_invalidation_watermarks"]["ST-0005"] = "2026-08-01T12:00:00Z"
    proposal = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
    )
    proposal["document"]["intent"] = "PROPOSE"
    del proposal["pr_evidence"]
    del proposal["approval"]
    assert validate(proposal, canonical_context)["transition_kinds"] == [
        "PROPOSAL_ONLY"
    ]


def test_wall_clock_checks_apply_only_to_current_validation(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["requested_at"] = "2999-01-01T09:00:00Z"
    request["approval"]["decided_at"] = "2999-01-01T09:30:00Z"
    state, stories, suites = canonical_context
    assert validate(request, canonical_context)["transition_kinds"] == ["FORWARD"]
    with pytest.raises(RuntimeError, match="future timestamp"):
        status.validate_request(
            request,
            state=state,
            story_index=stories,
            suite_index=suites,
            evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
            wall_clock_reference=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
        )


def test_live_validation_allows_future_expiry_boundary(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["pr_evidence"]["expires_at"] = "2999-01-01T00:00:00Z"
    state, stories, suites = canonical_context
    validated = status.validate_request(
        request,
        state=state,
        story_index=stories,
        suite_index=suites,
        evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
        artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
        wall_clock_reference=datetime(2026, 8, 1, 10, tzinfo=timezone.utc),
    )
    assert validated["pr_evidence"]["expires_at"] == "2999-01-01T00:00:00Z"


@pytest.mark.parametrize(
    (
        "source_implementation",
        "target_implementation",
        "evidence_class",
        "environment",
        "fixture_name",
    ),
    [
        (
            "VALIDATED",
            "DEPLOYED_STAGING",
            "STAGING_DEPLOYMENT",
            "STAGING",
            "st0005-production.yaml",
        ),
        (
            "DEPLOYED_STAGING",
            "VALIDATED",
            "ROLLBACK_DECISION",
            "CI",
            "st0005-rollback.yaml",
        ),
        (
            "DEPLOYED_STAGING",
            "DEPLOYED_PRODUCTION",
            "PRODUCTION_RELEASE",
            "PRODUCTION",
            "st0005-production.yaml",
        ),
        (
            "DEPLOYED_PRODUCTION",
            "DEPLOYED_STAGING",
            "ROLLBACK_DECISION",
            "CI",
            "st0005-rollback.yaml",
        ),
    ],
)
def test_deployment_status_transitions_are_fail_closed_without_typed_gates(
    canonical_context: Context,
    source_implementation: str,
    target_implementation: str,
    evidence_class: str,
    environment: str,
    fixture_name: str,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation=source_implementation,
        source_verification="PASS",
        target_implementation=target_implementation,
        target_verification="PASS",
        evidence_class=evidence_class,
        environment=environment,
        fixture_name=fixture_name,
    )
    with pytest.raises(
        RuntimeError, match="deployment status transitions are fail-closed"
    ):
        validate(request, canonical_context)


def test_production_governance_structure_uses_distinct_immutable_captures() -> None:
    paths = [
        "tests/st0005/fixtures/artifacts/"
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e-manifest.json",
        "tests/st0005/fixtures/artifacts/"
        "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8-status-registry.yaml",
        "tests/st0005/fixtures/artifacts/"
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d-story-backlog.yaml",
        "tests/st0005/fixtures/artifacts/"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-test-catalog.yaml",
    ]
    evidence = {
        name: repo_evidence(path)
        for name, path in zip(
            (
                "release_decision",
                "gate_report",
                "security_approval",
                "operations_approval",
            ),
            paths,
        )
    }
    assert status.validate_production_approval_evidence(
        evidence, artifact_uri_prefix=TEST_ARTIFACT_PREFIX
    )
    common = repo_evidence(paths[0])
    reused = {
        "release_decision": deepcopy(common),
        "gate_report": deepcopy(common),
        "security_approval": deepcopy(common),
        "operations_approval": deepcopy(common),
    }
    with pytest.raises(RuntimeError, match="four distinct"):
        status.validate_production_approval_evidence(
            reused, artifact_uri_prefix=TEST_ARTIFACT_PREFIX
        )


def test_deferred_story_activation_requires_human_pr_and_scope_decision(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="DEFERRED_POST_MVP",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        story_id="ST-1206",
    )
    with pytest.raises(RuntimeError, match="scope decision"):
        validate(request, canonical_context)
    request["scope_decision_evidence"] = repo_evidence(
        "tests/st0005/fixtures/artifacts/"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml"
    )
    assert validate(request, canonical_context)["transition_kinds"] == [
        "POST_MVP_ACTIVATION"
    ]

    request["requested_by"]["actor_type"] = "AUTOMATION"
    with pytest.raises(RuntimeError, match="only be requested by a human"):
        validate(request, canonical_context)


def test_deferral_watermark_rejects_stale_reactivation_and_accepts_fresh_plan(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    initial_scope_artifact = (
        f"{TEST_ARTIFACT_PREFIX}"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml"
    )
    activation_scope_artifact = (
        f"{TEST_ARTIFACT_PREFIX}"
        "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b-"
        "status-taxonomy.yaml"
    )
    deferral = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="DEFERRED_POST_MVP",
        target_verification="NOT_EXECUTED",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
        request_number=1,
    )
    deferral["scope_decision_evidence"] = repo_evidence(initial_scope_artifact)
    validate_and_apply(deferral, canonical_context)
    assert status.transition_control(state)["story_invalidation_watermarks"] == {
        "ST-0005": "2026-08-01T09:30:00Z"
    }

    stale = apply_request(
        state,
        stories,
        source_implementation="DEFERRED_POST_MVP",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        fixture_name="st0005-seq-change-plan-before-approval.yaml",
        request_number=2,
        requested_at="2026-08-01T10:00:00Z",
        evidence_observed_at="2026-08-01T09:15:00Z",
        pr_observed_at="2026-08-01T09:30:00Z",
        approval_decided_at="2026-08-01T10:30:00Z",
    )
    stale["scope_decision_evidence"] = repo_evidence(activation_scope_artifact)
    with pytest.raises(RuntimeError, match="latest applied approval decision"):
        validate(stale, canonical_context)

    fresh = apply_request(
        state,
        stories,
        source_implementation="DEFERRED_POST_MVP",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        fixture_name="st0005-seq-change-plan-fresh.yaml",
        request_number=3,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T13:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    fresh["scope_decision_evidence"] = repo_evidence(
        activation_scope_artifact, observed_at="2026-08-01T13:00:00Z"
    )
    validate_and_apply(fresh, canonical_context)


def test_out_of_scope_entry_requires_not_applicable_and_scope_decision(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="OUT_OF_SCOPE",
        target_verification="NOT_APPLICABLE",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
    )
    request["scope_decision_evidence"] = repo_evidence(
        "tests/st0005/fixtures/artifacts/"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml"
    )
    assert validate(request, canonical_context)["transition_kinds"] == ["SCOPE_CHANGE"]

    request["changes"][0]["target"]["verification_status"] = "NOT_EXECUTED"
    with pytest.raises(RuntimeError, match="OUT_OF_SCOPE requires"):
        validate(request, canonical_context)


def test_scope_decision_artifact_must_be_separate_from_approval(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="OUT_OF_SCOPE",
        target_verification="NOT_APPLICABLE",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
    )
    request["scope_decision_evidence"] = repo_evidence(
        f"{TEST_ARTIFACT_PREFIX}"
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e-"
        "manifest-copy.json"
    )
    assert (
        request["scope_decision_evidence"]["uri"]
        != request["approval"]["evidence"]["uri"]
    )
    with pytest.raises(RuntimeError, match="separate from approval evidence"):
        validate(request, canonical_context)


def test_out_of_scope_exit_resets_verification_and_proposal_cannot_bypass_scope(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="OUT_OF_SCOPE",
        source_verification="NOT_APPLICABLE",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
    )
    request["scope_decision_evidence"] = repo_evidence(
        "tests/st0005/fixtures/artifacts/"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml"
    )
    assert validate(request, canonical_context)["transition_kinds"] == ["SCOPE_CHANGE"]

    request["changes"][0]["target"]["verification_status"] = "NOT_APPLICABLE"
    with pytest.raises(RuntimeError, match="exit requires verification NOT_EXECUTED"):
        validate(request, canonical_context)

    proposal = apply_request(
        state,
        stories,
        source_implementation="DEFERRED_POST_MVP",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        story_id="ST-1206",
    )
    proposal["document"]["intent"] = "PROPOSE"
    proposal.pop("pr_evidence")
    proposal.pop("approval")
    with pytest.raises(RuntimeError, match="in-scope NOT_STARTED or IN_PROGRESS"):
        validate(proposal, canonical_context)


@pytest.mark.parametrize("failure", ("traversal", "missing", "hash", "symlink"))
def test_repo_evidence_rejects_unsafe_or_unverifiable_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    artifact = root / "artifact.txt"
    artifact.write_text("evidence\n", encoding="utf-8")
    monkeypatch.setattr(status, "REPO_ROOT", root)
    value = {
        "uri": "repo://artifact.txt",
        "sha256": status.sha256_file(artifact),
        "observed_at": "2026-08-01T08:00:00Z",
    }
    if failure == "traversal":
        value["uri"] = "repo://../outside"
    elif failure == "missing":
        value["uri"] = "repo://missing.txt"
    elif failure == "hash":
        value["sha256"] = "0" * 64
    else:
        real = root / "real"
        real.mkdir()
        nested = real / "nested.txt"
        nested.write_text("evidence\n", encoding="utf-8")
        (root / "linked").symlink_to(real, target_is_directory=True)
        value = {
            "uri": "repo://linked/nested.txt",
            "sha256": status.sha256_file(nested),
            "observed_at": "2026-08-01T08:00:00Z",
        }
    with pytest.raises(RuntimeError, match="unsafe|missing|hash mismatch|symlink"):
        status.validate_repo_evidence(
            value, source="negative evidence", required_suite=False
        )


@pytest.mark.parametrize("failure", ("traversal", "missing", "hash", "symlink"))
def test_snapshot_source_artifact_must_be_live_safe_and_hash_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    artifact = root / "artifact.txt"
    artifact.write_text("immutable evidence source\n", encoding="utf-8")
    source_hash = status.sha256_file(artifact)
    artifact_store = root / "artifacts"
    artifact_store.mkdir()
    capture = artifact_store / f"{source_hash}-artifact.txt"
    capture.write_bytes(artifact.read_bytes())
    artifact_uri = f"repo://artifacts/{capture.name}"
    if failure == "traversal":
        artifact_uri = "repo://../outside.txt"
    elif failure == "missing":
        artifact_uri = f"repo://artifacts/{source_hash}-missing.txt"
    elif failure == "hash":
        source_hash = "0" * 64
        mismatched = artifact_store / f"{source_hash}-artifact.txt"
        mismatched.write_bytes(artifact.read_bytes())
        artifact_uri = f"repo://artifacts/{mismatched.name}"
    else:
        real = root / "real"
        real.mkdir()
        nested = real / "nested.txt"
        nested.write_text("immutable evidence source\n", encoding="utf-8")
        (artifact_store / "linked").symlink_to(real, target_is_directory=True)
        source_hash = status.sha256_file(nested)
        artifact_uri = "repo://artifacts/linked/nested.txt"
    snapshot = {
        "document": {
            "id": "TEST-SNAPSHOT-SOURCE-VALIDATION",
            "schema_version": 1,
            "recorded_at": "2026-08-01T08:00:00Z",
        },
        "story_id": "ST-0005",
        "evidence_class": "CHANGE_PLAN",
        "formal_suite_status": "NOT_EXECUTED",
        "source_artifacts": [
            {
                "original_uri": "repo://original/artifact.txt",
                "artifact_uri": artifact_uri,
                "sha256": source_hash,
            }
        ],
        "suite_results": [
            {"suite_id": "TST-001", "environment": "LOCAL", "result": "PLANNED"}
        ],
        "local_results": [],
        "boundary": "Negative source-artifact validation fixture.",
    }
    snapshot_path = root / "snapshot.yaml"
    status.write_yaml(snapshot_path, snapshot)
    monkeypatch.setattr(status, "REPO_ROOT", root)
    with pytest.raises(RuntimeError, match="unsafe|missing|hash mismatch|symlink"):
        status.validate_evidence_snapshot(
            snapshot_path, artifact_uri_prefix="artifacts/"
        )


def test_sequential_replay_detects_second_request_lost_update(
    canonical_context: Context,
) -> None:
    state, stories, suites = canonical_context
    first = base_apply(canonical_context)
    second = deepcopy(first)
    second["document"]["id"] = "STATUS-ST0005-APPLY-TEST-002"
    validated = status.validate_request(
        first,
        state=state,
        story_index=stories,
        suite_index=suites,
        evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
        artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
    )
    status.apply_validated_request(state, validated)
    with pytest.raises(RuntimeError, match="lost update"):
        status.validate_request(
            second,
            state=state,
            story_index=stories,
            suite_index=suites,
            evidence_uri_prefix=TEST_EVIDENCE_PREFIX,
            artifact_uri_prefix=TEST_ARTIFACT_PREFIX,
        )


@pytest.mark.parametrize(
    ("target_verification", "stale_fixture", "fresh_fixture"),
    [
        (
            "PARTIAL",
            "st0005-seq-partial-stale-distinct.yaml",
            "st0005-seq-partial-after-expiry.yaml",
        ),
        (
            "FAIL",
            "st0005-seq-fail-stale-distinct.yaml",
            "st0005-seq-fail-after-expiry.yaml",
        ),
    ],
)
def test_expired_history_replays_offline_then_rejects_stale_recovery(
    canonical_context: Context,
    target_verification: str,
    stale_fixture: str,
    fresh_fixture: str,
) -> None:
    state, stories, suites = canonical_context
    first = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        request_number=1,
        evidence_expires_at="2026-08-02T00:00:00Z",
    )
    replay_state = deepcopy(state)
    validate_and_apply(first, canonical_context)
    old_digest = status.sha256_file(
        status.REPO_ROOT / TEST_EVIDENCE_PREFIX / "st0005-seq-pass-old.yaml"
    )
    assert status.transition_control(state)["story_active_evidence_sha256"] == {
        "ST-0005": [old_digest]
    }

    expiry = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="NOT_EXECUTED",
        evidence_class="EXPIRY",
        environment="CI",
        fixture_name="st0005-seq-expiry.yaml",
        request_number=2,
        requested_at="2026-08-03T09:00:00Z",
        evidence_observed_at="2026-08-03T08:00:00Z",
        pr_observed_at="2026-08-03T08:30:00Z",
        approval_decided_at="2026-08-03T09:30:00Z",
    )
    validate_and_apply(expiry, canonical_context)

    replay_context = (replay_state, stories, suites)
    validate_and_apply(deepcopy(first), replay_context)
    validate_and_apply(deepcopy(expiry), replay_context)
    replay_control = status.transition_control(replay_state)
    assert replay_control["sequence"] == 2
    assert replay_control["story_active_evidence_sha256"] == {}
    assert replay_control["story_active_evidence_valid_until"] == {}
    replay_row = next(
        row for row in replay_state["stories"] if row["story_id"] == "ST-0005"
    )
    assert replay_row["effective_verification_status"] == "NOT_EXECUTED"

    stale_recovery = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification=target_verification,
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name=stale_fixture,
        request_number=3,
        requested_at="2026-08-03T10:00:00Z",
        evidence_observed_at="2026-08-01T08:00:00Z",
        pr_observed_at="2026-08-03T09:30:00Z",
        approval_decided_at="2026-08-03T10:30:00Z",
    )
    with pytest.raises(RuntimeError, match="latest applied approval decision"):
        validate(stale_recovery, canonical_context)

    fresh_recovery = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification=target_verification,
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name=fresh_fixture,
        request_number=4,
        requested_at="2026-08-03T11:00:00Z",
        evidence_observed_at="2026-08-03T10:00:00Z",
        pr_observed_at="2026-08-03T10:30:00Z",
        approval_decided_at="2026-08-03T11:30:00Z",
    )
    validate_and_apply(fresh_recovery, canonical_context)


def test_stale_regression_cannot_overwrite_newer_active_pass(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    current_pass = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-fresh.yaml",
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(current_pass, canonical_context)
    assert status.transition_control(state)["story_active_evidence_observed_at"] == {
        "ST-0005": "2026-08-01T12:00:00Z"
    }

    stale_regression = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
        fixture_name="st0005-seq-regression.yaml",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    with pytest.raises(RuntimeError, match="status-changing evidence must postdate"):
        validate(stale_regression, canonical_context)

    fresh_regression = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
        fixture_name="st0005-seq-regression-fresh.yaml",
        request_number=3,
        requested_at="2026-08-01T15:00:00Z",
        evidence_observed_at="2026-08-01T14:00:00Z",
        pr_observed_at="2026-08-01T14:30:00Z",
        approval_decided_at="2026-08-01T15:30:00Z",
    )
    validate_and_apply(fresh_regression, canonical_context)
    row = next(row for row in state["stories"] if row["story_id"] == "ST-0005")
    assert row["effective_verification_status"] == "FAIL"


def test_stale_fail_cannot_overwrite_newer_active_partial(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    current_partial = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-partial-fresh.yaml",
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(current_partial, canonical_context)
    stale_fail = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-fail.yaml",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    with pytest.raises(RuntimeError, match="status-changing evidence must postdate"):
        validate(stale_fail, canonical_context)


def test_fail_to_partial_rejects_stale_result_and_accepts_fresh_recovery(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    failure = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-fail.yaml",
        requested_at="2026-08-01T11:00:00Z",
        evidence_observed_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T10:30:00Z",
        approval_decided_at="2026-08-01T11:30:00Z",
    )
    validate_and_apply(failure, canonical_context)

    stale = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-runtime-partial.yaml",
        request_number=2,
        requested_at="2026-08-01T12:00:00Z",
        evidence_observed_at="2026-08-01T08:00:00Z",
        pr_observed_at="2026-08-01T11:30:00Z",
        approval_decided_at="2026-08-01T12:30:00Z",
    )
    with pytest.raises(
        RuntimeError,
        match="must postdate (the active evidence|the latest applied approval)",
    ):
        validate(stale, canonical_context)

    fresh = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-partial-fresh.yaml",
        request_number=3,
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(fresh, canonical_context)


def test_stale_pass_cannot_overwrite_newer_active_partial(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    current_partial = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-partial-fresh.yaml",
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(current_partial, canonical_context)
    stale_pass = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T08:00:00Z",
        evidence_expires_at="2026-08-02T00:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    with pytest.raises(RuntimeError, match="status-changing evidence must postdate"):
        validate(stale_pass, canonical_context)


def test_expiry_observation_boundary_rejects_early_and_accepts_equality(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    active_pass = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        evidence_expires_at="2026-08-02T00:00:00Z",
    )
    validate_and_apply(active_pass, canonical_context)

    early = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="NOT_EXECUTED",
        evidence_class="EXPIRY",
        environment="CI",
        fixture_name="st0005-seq-expiry-early.yaml",
        request_number=2,
        requested_at="2026-08-02T00:00:00Z",
        evidence_observed_at="2026-08-01T23:59:59Z",
        pr_observed_at="2026-08-01T23:30:00Z",
        approval_decided_at="2026-08-02T00:30:00Z",
    )
    with pytest.raises(
        RuntimeError, match="observation predates active evidence expiry"
    ):
        validate(early, canonical_context)

    equal = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="NOT_EXECUTED",
        evidence_class="EXPIRY",
        environment="CI",
        fixture_name="st0005-seq-expiry-equal.yaml",
        request_number=3,
        requested_at="2026-08-02T00:00:00Z",
        evidence_observed_at="2026-08-02T00:00:00Z",
        pr_observed_at="2026-08-01T23:30:00Z",
        approval_decided_at="2026-08-02T00:30:00Z",
    )
    validate_and_apply(equal, canonical_context)
    row = next(row for row in state["stories"] if row["story_id"] == "ST-0005")
    assert row["effective_verification_status"] == "NOT_EXECUTED"
    assert status.transition_control(state)["story_active_evidence_observed_at"] == {}


def test_consumed_and_rewrapped_pass_are_rejected_but_fresh_recovery_applies(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    old_pass = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PARTIAL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        request_number=1,
        evidence_expires_at="2026-08-02T00:00:00Z",
    )
    validate_and_apply(old_pass, canonical_context)
    regression = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="REGRESSION",
        environment="CI",
        fixture_name="st0005-seq-regression.yaml",
        request_number=2,
        requested_at="2026-08-01T11:00:00Z",
        evidence_observed_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T10:30:00Z",
        approval_decided_at="2026-08-01T11:30:00Z",
    )
    validate_and_apply(regression, canonical_context)

    consumed = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        request_number=3,
        requested_at="2026-08-01T13:00:00Z",
        evidence_expires_at="2026-08-02T00:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    with pytest.raises(RuntimeError, match="reuse.*consumed|consumed evidence"):
        validate(consumed, canonical_context)

    rewrapped = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-rewrapped.yaml",
        request_number=4,
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    with pytest.raises(RuntimeError, match="reuse.*consumed|consumed evidence"):
        validate(rewrapped, canonical_context)

    fresh = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-fresh.yaml",
        request_number=5,
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(fresh, canonical_context)
    assert status.transition_control(state)["sequence"] == 3


@pytest.mark.parametrize("source_verification", ["NOT_EXECUTED", "PARTIAL"])
def test_unused_pass_before_failure_watermark_is_stale_but_new_pass_recovers(
    canonical_context: Context, source_verification: str
) -> None:
    state, stories, _ = canonical_context
    failure = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification=source_verification,
        target_implementation="VALIDATED",
        target_verification="FAIL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-fail.yaml",
        request_number=1,
        requested_at="2026-08-01T11:00:00Z",
        evidence_observed_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T10:30:00Z",
        approval_decided_at="2026-08-01T11:30:00Z",
    )
    validate_and_apply(failure, canonical_context)

    stale = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-old.yaml",
        request_number=2,
        requested_at="2026-08-01T12:00:00Z",
        evidence_expires_at="2026-08-02T00:00:00Z",
        pr_observed_at="2026-08-01T11:45:00Z",
        approval_decided_at="2026-08-01T12:30:00Z",
    )
    with pytest.raises(
        RuntimeError,
        match="must postdate (the active evidence|the latest applied approval)",
    ):
        validate(stale, canonical_context)

    fresh = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="FAIL",
        target_implementation="VALIDATED",
        target_verification="PASS",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-pass-fresh.yaml",
        request_number=3,
        requested_at="2026-08-01T13:00:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:30:00Z",
        approval_decided_at="2026-08-01T13:30:00Z",
    )
    validate_and_apply(fresh, canonical_context)


def test_transition_head_prevents_aba_lost_update(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    stale = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        request_number=3,
    )
    initial_digest = stale["expected"]["effective_status_sha256"]
    forward = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        request_number=1,
    )
    validate_and_apply(forward, canonical_context)
    rollback = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="NOT_EXECUTED",
        target_implementation="NOT_STARTED",
        target_verification="NOT_EXECUTED",
        evidence_class="ROLLBACK_DECISION",
        environment="CI",
        fixture_name="st0005-seq-rollback-fresh.yaml",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T13:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    validate_and_apply(rollback, canonical_context)
    row = next(row for row in state["stories"] if row["story_id"] == "ST-0005")
    assert row["effective_implementation_status"] == "NOT_STARTED"
    assert status.effective_status_digest(state) != initial_digest
    with pytest.raises(RuntimeError, match="lost update"):
        validate(stale, canonical_context)


def test_apply_requested_at_cannot_precede_prior_approval(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    validate_and_apply(base_apply(canonical_context), canonical_context)
    backward = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="NOT_EXECUTED",
        target_implementation="NOT_STARTED",
        target_verification="NOT_EXECUTED",
        evidence_class="ROLLBACK_DECISION",
        environment="CI",
        request_number=2,
        requested_at="2026-08-01T09:15:00Z",
        pr_observed_at="2026-08-01T09:10:00Z",
        approval_decided_at="2026-08-01T10:00:00Z",
    )
    with pytest.raises(RuntimeError, match="must not precede the prior approval"):
        validate(backward, canonical_context)


def test_one_capture_may_support_a_distinct_story_suite_class_dimension(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    validate_and_apply(base_apply(canonical_context), canonical_context)
    second = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        story_id="ST-0002",
        request_number=2,
        requested_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T09:45:00Z",
        approval_decided_at="2026-08-01T10:30:00Z",
    )
    validate_and_apply(second, canonical_context)
    assert status.transition_control(state)["sequence"] == 2


def test_apply_pr_uri_is_globally_single_use_but_distinct_pr_is_accepted(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    first = base_apply(canonical_context)
    validate_and_apply(first, canonical_context)

    second = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="NOT_EXECUTED",
        target_implementation="NOT_STARTED",
        target_verification="NOT_EXECUTED",
        evidence_class="ROLLBACK_DECISION",
        environment="CI",
        fixture_name="st0005-seq-rollback-fresh.yaml",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T13:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    distinct_pr_uri = second["pr_evidence"]["uri"]
    reused_pr_uri = first["pr_evidence"]["uri"]
    second["pr_evidence"]["uri"] = reused_pr_uri
    second["pr_evidence"]["sha256"] = status.pr_evidence_digest(
        reused_pr_uri, second["pr_evidence"]["implementation_commit_sha"]
    )
    with pytest.raises(RuntimeError, match="reuse consumed evidence identities"):
        validate(second, canonical_context)

    second["pr_evidence"]["uri"] = distinct_pr_uri
    second["pr_evidence"]["sha256"] = status.pr_evidence_digest(
        distinct_pr_uri, second["pr_evidence"]["implementation_commit_sha"]
    )
    validate_and_apply(second, canonical_context)


def test_approval_artifact_is_globally_single_use_across_stories(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    first = base_apply(canonical_context)
    validate_and_apply(first, canonical_context)

    second = apply_request(
        state,
        stories,
        source_implementation="NOT_STARTED",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="CHANGE_PLAN",
        environment="LOCAL",
        story_id="ST-0002",
        request_number=2,
        requested_at="2026-08-01T10:00:00Z",
        pr_observed_at="2026-08-01T09:45:00Z",
        approval_decided_at="2026-08-01T10:30:00Z",
    )
    distinct_approval = deepcopy(second["approval"]["evidence"])
    second["approval"]["evidence"] = deepcopy(first["approval"]["evidence"])
    with pytest.raises(RuntimeError, match="reuse consumed evidence identities"):
        validate(second, canonical_context)

    second["approval"]["evidence"] = distinct_approval
    validate_and_apply(second, canonical_context)


def test_pass_regression_to_partial_requires_partial_regression_evidence(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="PASS",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="REGRESSION",
        environment="CI",
        fixture_name="st0005-regression-partial.yaml",
    )
    assert validate(request, canonical_context)["transition_kinds"] == ["REGRESSION"]


def test_exact_all_pass_runtime_evidence_cannot_claim_partial(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    request = apply_request(
        state,
        stories,
        source_implementation="VALIDATED",
        source_verification="NOT_EXECUTED",
        target_implementation="VALIDATED",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-runtime-all-pass-partial-claim.yaml",
    )
    with pytest.raises(RuntimeError, match="PARTIAL requires incomplete or PARTIAL"):
        validate(request, canonical_context)


def test_scope_reset_clears_active_evidence_and_keeps_recovery_watermark(
    canonical_context: Context,
) -> None:
    state, stories, _ = canonical_context
    scope_artifact = (
        f"{TEST_ARTIFACT_PREFIX}"
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b-"
        "test-catalog.yaml"
    )
    exit_scope_artifact = (
        f"{TEST_ARTIFACT_PREFIX}"
        "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8-"
        "status-registry.yaml"
    )
    active = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="NOT_EXECUTED",
        target_implementation="IN_PROGRESS",
        target_verification="PARTIAL",
        evidence_class="RUNTIME_SUITE_RESULT",
        environment="CI",
        fixture_name="st0005-seq-partial-fresh.yaml",
        request_number=1,
        requested_at="2026-08-01T12:30:00Z",
        evidence_observed_at="2026-08-01T12:00:00Z",
        pr_observed_at="2026-08-01T12:15:00Z",
        approval_decided_at="2026-08-01T12:45:00Z",
    )
    validate_and_apply(active, canonical_context)
    control = status.transition_control(state)

    stale_scope = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="PARTIAL",
        target_implementation="OUT_OF_SCOPE",
        target_verification="NOT_APPLICABLE",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
        request_number=2,
        requested_at="2026-08-01T14:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    stale_scope["scope_decision_evidence"] = repo_evidence(scope_artifact)
    with pytest.raises(RuntimeError, match="status-changing evidence must postdate"):
        validate(stale_scope, canonical_context)

    fresh_scope = apply_request(
        state,
        stories,
        source_implementation="IN_PROGRESS",
        source_verification="PARTIAL",
        target_implementation="OUT_OF_SCOPE",
        target_verification="NOT_APPLICABLE",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
        fixture_name="st0005-seq-scope-fresh.yaml",
        request_number=3,
        requested_at="2026-08-01T14:00:00Z",
        evidence_observed_at="2026-08-01T13:00:00Z",
        pr_observed_at="2026-08-01T13:30:00Z",
        approval_decided_at="2026-08-01T14:30:00Z",
    )
    fresh_scope["scope_decision_evidence"] = repo_evidence(
        scope_artifact, observed_at="2026-08-01T13:00:00Z"
    )
    validate_and_apply(fresh_scope, canonical_context)
    assert "ST-0005" not in control["story_active_evidence_sha256"]
    assert "ST-0005" not in control["story_active_evidence_observed_at"]
    assert "ST-0005" not in control["story_active_evidence_valid_until"]
    assert control["story_invalidation_watermarks"]["ST-0005"] == (
        "2026-08-01T14:30:00Z"
    )

    stale_exit = apply_request(
        state,
        stories,
        source_implementation="OUT_OF_SCOPE",
        source_verification="NOT_APPLICABLE",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
        request_number=4,
        requested_at="2026-08-01T15:00:00Z",
        pr_observed_at="2026-08-01T14:45:00Z",
        approval_decided_at="2026-08-01T15:30:00Z",
    )
    stale_exit["scope_decision_evidence"] = repo_evidence(exit_scope_artifact)
    with pytest.raises(RuntimeError, match="must postdate the latest applied approval"):
        validate(stale_exit, canonical_context)

    fresh_exit = apply_request(
        state,
        stories,
        source_implementation="OUT_OF_SCOPE",
        source_verification="NOT_APPLICABLE",
        target_implementation="IN_PROGRESS",
        target_verification="NOT_EXECUTED",
        evidence_class="SCOPE_DECISION",
        environment="LOCAL",
        fixture_name="st0005-seq-scope-after-reset.yaml",
        request_number=5,
        requested_at="2026-08-01T16:00:00Z",
        evidence_observed_at="2026-08-01T15:00:00Z",
        pr_observed_at="2026-08-01T15:30:00Z",
        approval_decided_at="2026-08-01T16:30:00Z",
    )
    fresh_exit["scope_decision_evidence"] = repo_evidence(
        exit_scope_artifact, observed_at="2026-08-01T15:00:00Z"
    )
    validate_and_apply(fresh_exit, canonical_context)


def test_new_capture_checks_mutable_origin_but_offline_replay_uses_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    original = root / "current" / "report.txt"
    original.parent.mkdir(parents=True)
    original.write_text("approved report\n", encoding="utf-8")
    digest = status.sha256_file(original)
    artifact_store = root / "artifacts"
    artifact_store.mkdir()
    capture = artifact_store / f"{digest}-report.txt"
    capture.write_bytes(original.read_bytes())
    snapshot = root / "snapshot.yaml"
    status.write_yaml(
        snapshot,
        {
            "document": {
                "id": "TEST-LIVE-ORIGIN-CAPTURE",
                "schema_version": 1,
                "recorded_at": "2026-08-01T08:00:00Z",
            },
            "story_id": "ST-0005",
            "evidence_class": "CHANGE_PLAN",
            "formal_suite_status": "NOT_EXECUTED",
            "source_artifacts": [
                {
                    "original_uri": "repo://current/report.txt",
                    "artifact_uri": f"repo://artifacts/{capture.name}",
                    "sha256": digest,
                }
            ],
            "suite_results": [
                {
                    "suite_id": "TST-001",
                    "environment": "LOCAL",
                    "result": "PLANNED",
                }
            ],
            "local_results": [],
            "boundary": "Live capture and deterministic replay boundary.",
        },
    )
    monkeypatch.setattr(status, "REPO_ROOT", root)
    status.validate_evidence_snapshot(
        snapshot,
        artifact_uri_prefix="artifacts/",
        known_suite_ids={"TST-001"},
        verify_original_artifacts=True,
    )

    original.write_text("mutated after capture\n", encoding="utf-8")
    status.validate_evidence_snapshot(
        snapshot,
        artifact_uri_prefix="artifacts/",
        known_suite_ids={"TST-001"},
        verify_original_artifacts=False,
    )
    with pytest.raises(RuntimeError, match="does not match its declared original"):
        status.validate_evidence_snapshot(
            snapshot,
            artifact_uri_prefix="artifacts/",
            known_suite_ids={"TST-001"},
            verify_original_artifacts=True,
        )


def test_artifact_store_rejects_duplicate_digest_under_different_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "artifacts"
    store.mkdir()
    content = b"one immutable capture\n"
    digest = status.sha256_bytes(content)
    (store / f"{digest}-one.txt").write_bytes(content)
    (store / f"{digest}-two.txt").write_bytes(content)
    monkeypatch.setattr(status, "EVIDENCE_ARTIFACTS_ROOT", store)
    with pytest.raises(
        RuntimeError, match="duplicate content-addressed evidence artifact digest"
    ):
        status.evidence_artifact_files()


def test_evidence_identity_canonicalizes_duplicate_capture_digest() -> None:
    digest = "a" * 64
    base_change = {
        "story_id": "ST-0005",
        "evidence": [
            {
                "suite_id": "TST-001",
                "evidence_class": "RUNTIME_SUITE_RESULT",
                "snapshot_artifact_sha256": [digest],
            }
        ],
    }
    duplicated_change = {
        **base_change,
        "evidence": [
            {
                **base_change["evidence"][0],
                "snapshot_artifact_sha256": [digest, digest],
            }
        ],
    }
    assert status.evidence_identity_digests([base_change]) == (
        status.evidence_identity_digests([duplicated_change])
    )

    extra_digest = "b" * 64
    superset_change = {
        **base_change,
        "evidence": [
            {
                **base_change["evidence"][0],
                "snapshot_artifact_sha256": [digest, extra_digest],
            }
        ],
    }
    assert status.evidence_identity_digests([base_change]) & (
        status.evidence_identity_digests([superset_change])
    )


@pytest.mark.parametrize(
    "original_path",
    [
        ".git/config",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".aws/credentials",
        ".gnupg/private-keys-v1.d/key",
        ".ssh/config",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        ".env.production",
        "certificate.pem",
    ],
)
def test_sensitive_original_paths_cannot_enter_evidence_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    original_path: str,
) -> None:
    root = tmp_path / "repo"
    store = root / "artifacts"
    store.mkdir(parents=True)
    capture = store / "capture.txt"
    capture.write_text("safe test payload\n", encoding="utf-8")
    digest = status.sha256_file(capture)
    addressed = store / f"{digest}-capture.txt"
    capture.rename(addressed)
    monkeypatch.setattr(status, "REPO_ROOT", root)
    with pytest.raises(RuntimeError, match="sensitive paths"):
        status.validate_repo_artifact_reference(
            {
                "original_uri": f"repo://{original_path}",
                "artifact_uri": f"repo://artifacts/{addressed.name}",
                "sha256": digest,
            },
            source="sensitive capture",
            artifact_uri_prefix="artifacts/",
        )


def test_mutable_governance_paths_are_rejected(
    canonical_context: Context,
) -> None:
    request = base_apply(canonical_context)
    request["approval"]["evidence"] = repo_evidence("docs/manifest.json")
    with pytest.raises(RuntimeError, match="immutable evidence artifact store"):
        validate(request, canonical_context)


def test_yaml_resource_limits_reject_oversize_alias_and_excess_depth(
    tmp_path: Path,
) -> None:
    oversize = tmp_path / "oversize.yaml"
    oversize.write_bytes(b"root: " + b"x" * status.MAX_YAML_BYTES)
    with pytest.raises(RuntimeError, match="exceeds"):
        status.load_yaml(oversize)

    alias = tmp_path / "alias.yaml"
    alias.write_text("shared: &shared\n  value: one\ncopy: *shared\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="anchors and aliases"):
        status.load_yaml(alias)

    deep = tmp_path / "deep.yaml"
    deep.write_text("root: " + "[" * 70 + "0" + "]" * 70 + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="complexity limits"):
        status.load_yaml(deep)


@pytest.mark.parametrize(
    "names",
    [
        ["0001-first.yaml", "0003-gap.yaml"],
        ["1-noncanonical.yaml"],
        ["0001-.yaml"],
        ["0001-first.yaml", "notes.txt"],
    ],
)
def test_request_source_filenames_are_contiguous_and_canonical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    names: list[str],
) -> None:
    root = tmp_path / "requests"
    root.mkdir()
    for name in names:
        (root / name).write_text("document: {}\n", encoding="utf-8")
    monkeypatch.setattr(status, "REQUESTS_ROOT", root)
    with pytest.raises(RuntimeError, match="contiguous|unexpected"):
        status.request_files()


def test_live_apply_remains_fail_closed_after_structural_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = status.request_files()[0]
    relative = status.relative_repo_path(path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request_target")
    monkeypatch.setenv("RAOS_CHANGED_STATUS_REQUEST", relative)
    monkeypatch.setenv("RAOS_CHANGED_STATUS_REQUEST_COUNT", "1")
    monkeypatch.setattr(status, "assert_immutable_inputs", lambda: None)
    monkeypatch.setattr(
        status,
        "build_overlay",
        lambda **_kwargs: {
            "request_inventory": [
                {
                    "path": relative,
                    "intent": "APPLY",
                    "request_id": "STATUS-ST0005-APPLY-LIVE-TEST",
                }
            ]
        },
    )
    with pytest.raises(RuntimeError, match="authoritative live APPLY is fail-closed"):
        status.validate_live_committed_request(path)
