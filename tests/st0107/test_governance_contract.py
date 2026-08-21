"""Positive contract and artifact semantics for ST-0107."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest
import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st0107_pr_governance as generator
from scripts.classify_ci_scope import (
    codeowner_pattern_matches,
    high_risk_categories,
    load_contract as load_scope_contract,
    required_owner_roles,
)


EXPECTED_CHECKS = (
    "Static",
    "Unit",
    "Contracts",
    "Database",
    "Storage",
    "Secrets",
    "Validate status overlay",
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


def _owners_for_path(
    rows: list[tuple[str, tuple[str, ...]]], path: str
) -> tuple[str, ...]:
    owners: tuple[str, ...] = ()
    for pattern, candidate in rows:
        if codeowner_pattern_matches(path, pattern):
            owners = candidate
    return owners


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
    assert len(activation["prerequisites"]) == 6


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

    assert governance_contract["story_scope_ownership"] == {
        "scope_contract": generator.SCOPE_CONTRACT_URI,
        "canonical_story_source": generator.CANONICAL_STORY_SOURCE_URI,
        "default_roles": ["engineering", "security"],
        "ordering": "derived_story_defaults_before_path_specific_rows",
    }


def test_rendered_codeowners_routes_only_declared_paths_and_preserves_last_match_control(
    governance_contract: dict[str, Any],
) -> None:
    rendered = generator.render_codeowners(governance_contract)
    text = rendered.decode("utf-8")
    rows = _codeowner_rows(rendered)
    by_pattern = dict(rows)

    assert text.endswith("\n")
    assert "UNVERIFIED_PLACEHOLDERS" in text
    assert "*" not in by_pattern
    assert rows[0] == (
        "/changes/st-0001/",
        ("@raos/engineering", "@raos/security"),
    )
    assert rows[-1] == (
        "/.github/",
        ("@raos/security", "@raos/operations"),
    )
    assert len(by_pattern) == len(rows)
    expected_rows = [
        (
            row["pattern"],
            tuple(
                governance_contract["owner_bindings"]["teams"][role]
                for role in row["roles"]
            ),
        )
        for row in generator._expanded_codeowner_entries(
            governance_contract, REPOSITORY_ROOT
        )
    ]
    assert rows == expected_rows
    for pattern, owners in generator._canonical_codeowner_entries(
        REPOSITORY_ROOT
    ).items():
        if pattern == "*":
            continue
        assert by_pattern[pattern] == owners


def test_mandatory_high_risk_categories_have_enforced_rows(
    governance_contract: dict[str, Any],
) -> None:
    policy = governance_contract["ruleset_policy"]
    categories = policy["required_owner_categories"]
    entries = {
        row["pattern"]: set(row["roles"])
        for row in governance_contract["codeowners"]["entries"]
    }

    assert tuple(categories) == (
        "contract_codegen",
        "migration_database",
        "authentication_authorization_credentials",
        "security_controls",
        "publication_finance_kill_switch",
        "infrastructure_deployment",
        "provider_runtime",
        "governance_ci_status",
        "protected_sources",
    )
    assert categories == generator._expected_owner_categories(REPOSITORY_ROOT)
    for category in categories.values():
        required_roles = set(category["roles"])
        assert category["patterns"]
        assert required_roles
        for pattern in category["patterns"]:
            assert required_roles <= entries[pattern]


def test_deployment_category_covers_database_and_object_storage_surfaces(
    governance_contract: dict[str, Any],
) -> None:
    deployment = governance_contract["ruleset_policy"]["required_owner_categories"][
        "infrastructure_deployment"
    ]
    assert deployment == {
        "patterns": [
            "/infra/",
            "/docker-compose.yml",
            "/scripts/build_local_compose.py",
            "/scripts/*deploy*",
            "/scripts/*storage*",
            "/scripts/*postgres*",
        ],
        "roles": ["operations", "security"],
    }


def test_governance_category_covers_ci_and_policy_sources(
    governance_contract: dict[str, Any],
) -> None:
    governance = governance_contract["ruleset_policy"]["required_owner_categories"][
        "governance_ci_status"
    ]
    assert (
        governance
        == generator._expected_owner_categories(REPOSITORY_ROOT)["governance_ci_status"]
    )
    assert {
        "/AGENTS.md",
        "/.codex/",
        "/Makefile",
        "/changes/st-0106/",
        "/changes/st-0107/",
        "/scripts/classify_ci_scope.py",
        "/scripts/dev_check.py",
        "/scripts/build_st0107_pr_governance.py",
        "/scripts/github_ruleset_operator.py",
        "/tests/st0106/",
        "/tests/st0107/",
        "/.github/",
    } <= set(governance["patterns"])
    assert governance["roles"] == ["security", "operations"]


@pytest.mark.parametrize(
    ("path", "expected_owners"),
    [
        (
            "scripts/build_st0104_contract_repository.py",
            ("@raos/architecture", "@raos/engineering"),
        ),
        (
            "tests/st0104/test_verifier.py",
            ("@raos/architecture", "@raos/engineering"),
        ),
        (
            "scripts/build_st0301_migration_framework.py",
            ("@raos/data", "@raos/security"),
        ),
        ("tests/st0301/test_generation.py", ("@raos/data", "@raos/security")),
        (
            "scripts/build_st0005_status.py",
            ("@raos/security", "@raos/operations"),
        ),
        (
            "tests/st0005/test_overlay_contract.py",
            ("@raos/security", "@raos/operations"),
        ),
        (
            "python/raos/application/iam/authentication.py",
            ("@raos/security", "@raos/engineering"),
        ),
        (
            "python/raos/domain/iam/authorization.py",
            ("@raos/security", "@raos/architecture"),
        ),
        (
            "python/raos/adapters/development_workload_credentials.py",
            ("@raos/security", "@raos/operations"),
        ),
        (
            "python/raos/adapters/wordpresscom_oauth.py",
            ("@raos/security", "@raos/operations"),
        ),
        (
            "python/raos/domain/publishing/review_workflow.py",
            ("@raos/editorial", "@raos/security"),
        ),
        (
            "tests/st0904/test_contract.py",
            ("@raos/editorial", "@raos/security"),
        ),
        (
            "python/raos/domain/http/security.py",
            ("@raos/security", "@raos/architecture"),
        ),
        (
            "python/raos/application/http/security.py",
            ("@raos/security", "@raos/engineering"),
        ),
        (
            "tests/st0401/test_authentication.py",
            ("@raos/security", "@raos/engineering"),
        ),
        (
            "scripts/build_st1603_security_verification_pack.py",
            ("@raos/security", "@raos/engineering"),
        ),
        (
            "tests/st1603/test_contract.py",
            ("@raos/security", "@raos/operations"),
        ),
        (
            "changes/st-0106/contracts/developer-loop-scope.v1.json",
            (
                "@raos/architecture",
                "@raos/engineering",
                "@raos/security",
                "@raos/operations",
            ),
        ),
        (
            "changes/st-0005/contracts/status-policy.v1.yaml",
            (
                "@raos/architecture",
                "@raos/engineering",
                "@raos/security",
                "@raos/operations",
            ),
        ),
        (
            "changes/st-0107/contracts/pr-governance.v1.yaml",
            (
                "@raos/architecture",
                "@raos/engineering",
                "@raos/security",
                "@raos/operations",
            ),
        ),
        (
            "changes/st-0301/generated/migration-catalog.v1.json",
            (
                "@raos/architecture",
                "@raos/engineering",
                "@raos/data",
                "@raos/security",
            ),
        ),
        (
            "changes/st-1603/generated/security-verification-pack.reference-plan.v1.json",
            (
                "@raos/architecture",
                "@raos/engineering",
                "@raos/security",
                "@raos/operations",
            ),
        ),
        (
            "python/raos/domain/ai/provider.py",
            (
                "@raos/ai",
                "@raos/editorial",
                "@raos/operations",
                "@raos/security",
            ),
        ),
        (
            "tests/st0305/test_st0305_publication_analytics_finance.py",
            ("@raos/engineering", "@raos/security"),
        ),
        (
            "tests/st1703/test_wordpresscom_oauth.py",
            ("@raos/engineering", "@raos/security"),
        ),
        (
            "docs/upstream/README.md",
            ("@raos/architecture",),
        ),
    ],
)
def test_representative_high_risk_paths_resolve_to_expected_final_codeowners(
    governance_contract: dict[str, Any],
    path: str,
    expected_owners: tuple[str, ...],
) -> None:
    rows = _codeowner_rows(generator.render_codeowners(governance_contract))
    assert _owners_for_path(rows, path) == expected_owners


def test_every_tracked_high_risk_path_retains_all_effective_category_owners(
    governance_contract: dict[str, Any],
) -> None:
    scope = load_scope_contract(REPOSITORY_ROOT)
    teams = governance_contract["owner_bindings"]["teams"]
    rows = _codeowner_rows(generator.render_codeowners(governance_contract))
    tracked = (
        subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )

    gaps: list[tuple[str, list[str], tuple[str, ...]]] = []
    for path in tracked:
        if not path:
            continue
        matching_categories = high_risk_categories(path, scope)
        if not matching_categories:
            continue
        required = {teams[role] for role in required_owner_roles(path, scope)}
        effective = _owners_for_path(rows, path)
        if not required.issubset(effective):
            gaps.append((path, sorted(required), effective))

    assert gaps == []


def test_closed_ordinary_story_roots_do_not_receive_derived_default_owners(
    governance_contract: dict[str, Any],
) -> None:
    rows = _codeowner_rows(generator.render_codeowners(governance_contract))
    assert _owners_for_path(rows, "tests/st0501/test_workflow.py") == ()
    assert _owners_for_path(rows, "changes/st-0501/README.md") == ()
    assert _owners_for_path(rows, "scripts/build_st0501_unmapped_generator.py") == (
        "@raos/engineering",
        "@raos/security",
    )


def test_pull_request_template_captures_the_short_development_loop(
    governance_contract: dict[str, Any],
) -> None:
    rendered = generator.render_pull_request_template(
        governance_contract, REPOSITORY_ROOT
    ).decode("utf-8")

    assert rendered.startswith(
        "<!-- Generated by scripts/build_st0107_pr_governance.py. Do not edit. -->\n"
        f"<!-- Source contract: {generator.SOURCE_CONTRACT_URI} -->\n"
        f"<!-- Generation command: {generator.GENERATION_COMMAND} -->\n"
        "<!-- High-risk CODEOWNER and live GitHub evidence cannot be supplied by this template. -->\n"
    )
    for heading in (
        "## Story or slice",
        "## Risk",
        "## Development evidence",
        "## High-risk CODEOWNER review",
        "## Deferred formal or live work",
        "## Evidence boundary",
    ):
        assert rendered.count(heading) == 1
    table_rows = {
        tuple(cell.strip() for cell in line.strip("|").split("|"))
        for line in rendered.splitlines()
        if line.startswith("|")
    }
    for row in (
        ("Contract / generated types", "", "Architecture / Engineering"),
        ("Migration / database", "", "Data / Security"),
        ("Authentication / authorization / credentials", "", "Security"),
        ("Security controls", "", "Security"),
        ("Publication / finance / kill switch", "", "Security"),
        ("Deployment / infrastructure", "", "Operations / Security"),
        ("Provider runtime", "", "Operations / Security"),
        ("Governance / CI / status", "", "Security / Operations"),
        ("Unproven or new Story scope", "", "Engineering / Security"),
        ("Protected Canonical / upstream source", "", "Architecture"),
    ):
        assert row in table_rows
    assert (
        "`make dev-check STORY=ST-XXXX [STORIES=ST-XXXX,ST-YYYY] "
        "[BASE_REF=<ref>]`" in rendered
    )
    assert "- Hosted Base CI at the exact head:" in rendered
    assert "- Exact-head human approval (required fallback;" in rendered
    assert (
        "- Independent automated review: `NOT_AVAILABLE_HUMAN_REVIEW_FALLBACK`"
        in rendered
    )
    assert "- Formal TST not executed:" in rendered
    assert "- Provider / live / staging / Production work not executed:" in rendered
    assert (
        "Use `N/A` only when the path family is unchanged, and record the rationale."
        in rendered
    )
    assert (
        "- [ ] High-risk CODEOWNER review is complete, or every row has an `N/A` rationale"
        in rendered
    )


def test_required_checks_match_fixed_workflow_job_names_and_sources(
    governance_contract: dict[str, Any],
) -> None:
    checks = governance_contract["ruleset_policy"]["required_status_checks"]
    assert tuple(row["context"] for row in checks) == EXPECTED_CHECKS
    assert generator.EXPECTED_CHECK_CONTEXTS == EXPECTED_CHECKS
    workflow_names = generator._workflow_check_names(REPOSITORY_ROOT)
    assert tuple(name for name in workflow_names if name in EXPECTED_CHECKS) == (
        EXPECTED_CHECKS
    )
    assert "Classify Base CI scope" in workflow_names
    assert all(row["expected_source"] == "github-actions" for row in checks)
    assert all(
        row["integration_id_binding"] == "REQUIRED_AT_ACTIVATION" for row in checks
    )


def test_ruleset_artifact_is_fail_closed_desired_state_not_api_payload(
    governance_contract: dict[str, Any],
) -> None:
    artifact = json.loads(generator.render_ruleset_policy(governance_contract))
    assert artifact["document"] == {
        "id": "RAOS-GITHUB-RULESET-POLICY-001",
        "version": "1.0.0",
        "story_id": "ST-0107",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
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
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": True,
        "require_last_push_approval": False,
        "required_approving_review_count": 1,
        "required_review_thread_resolution": True,
    }


def test_source_pins_match_current_regular_files() -> None:
    for relative, expected_sha256 in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_sha256


def test_architecture_snapshot_is_strictly_parsed_and_hash_pinned() -> None:
    generator._validate_architecture_snapshot(REPOSITORY_ROOT)
    snapshot_path = REPOSITORY_ROOT / generator.ARCHITECTURE_SNAPSHOT_PATH
    assert generator.sha256_file(snapshot_path) == (
        generator.EXPECTED_ARCHITECTURE_SNAPSHOT_SHA256
    )
    snapshot = generator.load_yaml(snapshot_path)
    assert snapshot["local_candidate"]["remote_mutation_capability"] == "FORBIDDEN"
    assert snapshot["local_candidate"]["remote_mutation_scope"] == "GENERATOR_ONLY"
    assert snapshot["bounded_operator"]["repository"] == "jamozi/rakuten"
    assert snapshot["bounded_operator"]["api_origin"] == "https://api.github.com"
    assert snapshot["bounded_operator"]["live_mutation_activation"] == (
        "DISABLED_PENDING_REVIEWED_ACTIVATION_CONTRACT"
    )
    assert snapshot["bounded_operator"]["owner_bindings"] == ("UNVERIFIED_PLACEHOLDERS")
    assert snapshot["bounded_operator"]["mutation_with_unverified_owner_bindings"] == (
        "FORBIDDEN"
    )
    assert snapshot["bounded_operator"]["live_execution"] == "NOT_EXECUTED"
    assert (
        snapshot["desired_ruleset_semantics"]["general_required_approving_review_count"]
        == 1
    )
    assert snapshot["desired_ruleset_semantics"]["require_last_push_approval"] is False
    assert snapshot["local_candidate"]["storage_check_boundary"] == {
        "source_story": "ST-0202",
        "context": "Storage",
        "wrapper": "scripts/object_storage_service.sh",
        "network_scope": "EXACT_DIGEST_PINNED_SEAWEEDFS_IMAGE_PULL_ONLY",
        "repository_dependency_hydration": "FORBIDDEN",
        "hosted_execution": "NOT_EXECUTED",
    }


def test_every_generated_artifact_identifies_source_and_generation_command(
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

    for text in (codeowners, template):
        assert generator.SOURCE_CONTRACT_URI in text
        assert generator.GENERATION_COMMAND in text
    for document in (ruleset["document"], manifest["document"]):
        assert document["source_contract"] == generator.SOURCE_CONTRACT_URI
        assert document["generated_by"] == generator.GENERATOR_URI
        assert document["generation_command"] == generator.GENERATION_COMMAND


def test_sec_sdlc_010_maps_migrations_to_independent_review_controls(
    governance_contract: dict[str, Any],
) -> None:
    policy = governance_contract["ruleset_policy"]
    migration = policy["required_owner_categories"]["migration_database"]
    assert migration == {
        "patterns": [
            "/migrations/",
            "/changes/*/database/",
            "/changes/st-0301/",
            "/python/raos/migrations/",
            "/scripts/*migration*",
            "/tests/st0301/",
        ],
        "roles": ["data", "security"],
    }
    assert policy["pull_request"]["require_code_owner_review"] is True
    assert policy["pull_request"]["require_last_push_approval"] is False
    assert policy["pull_request"]["required_approving_review_count"] == 1
    execplan = (REPOSITORY_ROOT / "docs/execplans/ST-0107.md").read_text(
        encoding="utf-8"
    )
    assert "SEC-SDLC-010" in execplan
    assert "live migration probe" in " ".join(execplan.split())


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
