"""Positive contract and artifact semantics for ST-0107."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0107_pr_governance as generator


EXPECTED_CHECKS = (
    "Final Integration",
)


def _codeowner_rows(content: bytes) -> list[tuple[str, tuple[str, ...]]]:
    rows: list[tuple[str, tuple[str, ...]]] = []
    for raw_line in content.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *owners = line.split()
        rows.append((pattern, tuple(owners)))
    return rows


def test_contract_is_pinned_to_reviewed_sources_and_safe_local_status(
    governance_contract: dict[str, Any],
) -> None:
    assert governance_contract["document"] == generator.EXPECTED_DOCUMENT
    assert {
        row["uri"].removeprefix("repo://"): row["sha256"]
        for row in governance_contract["sources"]
    } == generator.PINNED_SOURCES

    activation = governance_contract["activation"]
    assert activation["generator_remote_mutation"] == "FORBIDDEN"
    assert activation["live_status"] == "NOT_EXECUTED"
    assert activation["formal_tst_001"] == "NOT_EXECUTED"
    assert tuple(activation["prerequisites"]) == (
        generator.EXPECTED_ACTIVATION_PREREQUISITES
    )
    assert len(activation["prerequisites"]) == 3


def test_owner_placeholders_are_complete_unique_and_not_live_verified(
    governance_contract: dict[str, Any],
) -> None:
    bindings = governance_contract["owner_bindings"]
    teams = bindings["teams"]
    assert bindings == {
        "organization": "raos",
        "status": "UNVERIFIED_PLACEHOLDERS",
        "teams": teams,
    }
    assert tuple(sorted(teams)) == generator.EXPECTED_OWNER_ROLES
    assert set(teams.values()) == {
        f"@raos/{role}" for role in generator.EXPECTED_OWNER_ROLES
    }


def test_rendered_codeowners_preserves_canonical_rows_and_last_match_control(
    governance_contract: dict[str, Any],
) -> None:
    rendered = generator.render_codeowners(governance_contract)
    text = rendered.decode("utf-8")
    rows = _codeowner_rows(rendered)
    by_pattern = dict(rows)

    assert text.endswith("\n")
    assert "UNVERIFIED_PLACEHOLDERS" in text
    assert rows[0] == ("*", ("@raos/engineering",))
    assert rows[-1] == (
        "/.github/",
        ("@raos/security", "@raos/operations"),
    )
    assert len(by_pattern) == len(rows)
    expected_rows = [
        (
            pattern,
            tuple(
                governance_contract["owner_bindings"]["teams"][role] for role in roles
            ),
        )
        for pattern, roles in generator.EXPECTED_CODEOWNER_ENTRIES
    ]
    assert rows == expected_rows
    for pattern, owners in generator._canonical_codeowner_entries(
        REPOSITORY_ROOT
    ).items():
        assert by_pattern[pattern] == owners


def test_codeowners_remain_informational_not_required_review_gates(
    governance_contract: dict[str, Any],
) -> None:
    policy = governance_contract["ruleset_policy"]
    categories = policy["required_owner_categories"]
    assert categories == generator.EXPECTED_OWNER_CATEGORIES == {}
    assert policy["pull_request"]["require_code_owner_review"] is False


def test_deployment_changes_use_ci_without_a_review_category(
    governance_contract: dict[str, Any],
) -> None:
    policy = governance_contract["ruleset_policy"]
    assert policy["required_owner_categories"] == {}
    assert policy["required_status_checks"][0]["context"] == "Final Integration"


def test_pull_request_template_records_integration_results_once(
    governance_contract: dict[str, Any],
) -> None:
    rendered = generator.render_pull_request_template(
        governance_contract, REPOSITORY_ROOT
    ).decode("utf-8")

    assert rendered.startswith("<!-- Generated from PR governance v2. -->\n")
    for heading in (
        "## Tracking",
        "## Summary",
        "## Verification",
        "## External operations not run",
        "## Rollback",
    ):
        assert rendered.count(heading) == 1
    assert "Human reviewer" not in rendered
    assert "Required owner routing" not in rendered


def test_required_checks_match_fixed_workflow_job_names_and_sources(
    governance_contract: dict[str, Any],
) -> None:
    checks = governance_contract["ruleset_policy"]["required_status_checks"]
    assert tuple(row["context"] for row in checks) == EXPECTED_CHECKS
    assert generator.EXPECTED_CHECK_CONTEXTS == EXPECTED_CHECKS
    assert generator._workflow_check_names(REPOSITORY_ROOT) == EXPECTED_CHECKS
    assert all(row["expected_source"] == "github-actions" for row in checks)
    assert all(
        row["integration_id_binding"] == "REQUIRED_AT_ACTIVATION" for row in checks
    )


def test_ruleset_artifact_is_fail_closed_desired_state_not_api_payload(
    governance_contract: dict[str, Any],
) -> None:
    artifact = json.loads(generator.render_ruleset_policy(governance_contract))
    assert artifact["document"] == {
        "id": "RAOS-GITHUB-RULESET-POLICY-002",
        "version": "2.0.0",
        "story_id": "ST-0107",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "artifact_kind": "DESIRED_STATE_NOT_API_PAYLOAD",
        "github_api_version": "2026-03-10",
        "live_status": "NOT_EXECUTED",
        "formal_tst_001": "NOT_EXECUTED",
    }
    assert artifact["activation"] == governance_contract["activation"]

    ruleset = artifact["ruleset"]
    assert ruleset["target"] == "branch"
    assert ruleset["include"] == ["~DEFAULT_BRANCH"]
    assert ruleset["exclude"] == []
    assert ruleset["desired_enforcement"] == "active"
    assert ruleset["local_application_status"] == "NOT_EXECUTED"
    assert ruleset["bypass_actors"] == []
    assert ruleset["prohibit_deletion"] is True
    assert ruleset["prohibit_force_push"] is True
    assert ruleset["require_linear_history"] is True
    assert ruleset["strict_required_status_checks_policy"] is True
    assert ruleset["do_not_enforce_on_create"] is False
    assert ruleset["pull_request"] == {
        "allowed_merge_methods": ["squash"],
        "dismiss_stale_reviews_on_push": False,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": False,
        "auto_merge_after_required_checks": True,
    }


def test_source_pins_match_current_regular_files() -> None:
    for relative, expected_sha256 in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_sha256


def test_architecture_snapshot_is_semantically_parsed_without_hash_authority() -> None:
    generator._validate_architecture_snapshot(REPOSITORY_ROOT)
    snapshot_path = REPOSITORY_ROOT / generator.ARCHITECTURE_SNAPSHOT_PATH
    snapshot = generator.load_yaml(snapshot_path)
    assert snapshot["local_candidate"]["storage_check_boundary"] == {
        "source_story": "ST-0202",
        "context": "Storage",
        "wrapper": "scripts/object_storage_service.sh",
        "network_scope": "EXACT_DIGEST_PINNED_SEAWEEDFS_IMAGE_PULL_ONLY",
        "repository_dependency_hydration": "FORBIDDEN",
        "hosted_execution": "NOT_EXECUTED",
    }


def test_generated_artifacts_use_semantic_provenance_without_command_pins(
    governance_contract: dict[str, Any],
) -> None:
    codeowners = generator.render_codeowners(governance_contract).decode("utf-8")
    template = generator.render_pull_request_template(
        governance_contract, REPOSITORY_ROOT
    ).decode("utf-8")
    ruleset = json.loads(generator.render_ruleset_policy(governance_contract))
    manifest = yaml.safe_load(
        generator.render_outputs(REPOSITORY_ROOT)[generator.MANIFEST_PATH]
    )

    assert generator.SOURCE_CONTRACT_URI in codeowners
    assert "generation_command" not in manifest["document"]
    assert template.startswith("<!-- Generated from PR governance v2. -->")
    assert ruleset["document"]["source_contract"] == generator.SOURCE_CONTRACT_URI


def test_security_and_migration_changes_are_verified_without_review_gates(
    governance_contract: dict[str, Any],
) -> None:
    policy = governance_contract["ruleset_policy"]
    assert policy["required_owner_categories"] == {}
    assert policy["pull_request"]["require_code_owner_review"] is False
    assert policy["pull_request"]["require_last_push_approval"] is False
    assert policy["pull_request"]["required_approving_review_count"] == 0


def test_generated_paths_are_fixed_repository_relative_files() -> None:
    assert generator.GENERATED_PATHS == (
        Path(".github/CODEOWNERS"),
        Path(".github/PULL_REQUEST_TEMPLATE.md"),
        Path("changes/st-0107/ruleset-policy.v1.json"),
        Path("changes/st-0107/manifest.yaml"),
    )
    assert all(
        not path.is_absolute() and ".." not in path.parts
        for path in generator.GENERATED_PATHS
    )
