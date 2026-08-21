"""Fail-closed and adversarial contract tests for ST-0107."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from yaml.constructor import ConstructorError

from conftest import RejectContract
from scripts import build_st0107_pr_governance as generator


def _entry(contract: dict[str, Any], pattern: str) -> dict[str, Any]:
    return next(
        row for row in contract["codeowners"]["entries"] if row["pattern"] == pattern
    )


def test_yaml_duplicate_mapping_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text("document: one\ndocument: two\n", encoding="utf-8")

    with pytest.raises(ConstructorError, match="found duplicate key 'document'"):
        generator.load_yaml(path)


@pytest.mark.parametrize(
    "content",
    [
        "shared: &shared\n  value: one\n",
        "shared: &shared\n  value: one\ncopy: *shared\n",
    ],
    ids=["anchor", "alias"],
)
def test_yaml_anchor_or_alias_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "alias.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(RuntimeError, match="anchors and aliases are forbidden"):
        generator.load_yaml(path)


def test_yaml_symlink_input_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.yaml"
    link = tmp_path / "link.yaml"
    target.write_text("value: safe\n", encoding="utf-8")
    link.symlink_to(target)

    with pytest.raises(RuntimeError, match="regular non-symlink file"):
        generator.load_yaml(link)


def test_pinned_source_symlink_is_rejected_even_when_content_hash_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(b"safe: content\n")
    (repository / "pinned.yaml").symlink_to(outside)
    digest = generator.sha256_file(outside)
    monkeypatch.setattr(generator, "PINNED_SOURCES", {"pinned.yaml": digest})
    contract = {
        "sources": [{"uri": "repo://pinned.yaml", "sha256": digest}],
    }

    with pytest.raises(
        RuntimeError, match="pinned source must be a regular non-symlink"
    ):
        generator._validate_sources(contract, repository)


def test_repository_file_ancestor_symlink_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (outside / "source.yaml").write_text("safe: true\n", encoding="utf-8")
    (repository / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="ancestor must be a real directory"):
        generator._repository_regular_file(
            repository, Path("linked/source.yaml"), "source artifact"
        )


def test_architecture_snapshot_unknown_field_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    snapshot = repository / generator.ARCHITECTURE_SNAPSHOT_PATH
    snapshot.parent.mkdir(parents=True)
    original = generator.REPO_ROOT / generator.ARCHITECTURE_SNAPSHOT_PATH
    snapshot.write_bytes(original.read_bytes() + b"unknown_field: rejected\n")

    with pytest.raises(RuntimeError, match="architecture snapshot keys differ"):
        generator._validate_architecture_snapshot(repository)


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.invalid/source",
        "repo://",
        "repo:///absolute",
        "repo://../escape",
        "repo://a/../escape",
        "repo://./source",
    ],
)
def test_untrusted_source_uri_is_rejected(uri: str) -> None:
    with pytest.raises(RuntimeError, match="source uri|unsafe repository source uri"):
        generator._repo_relative_uri(uri)


def test_unknown_top_level_contract_key_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["unexpected"] = {}
    reject_contract(mutable_contract, "governance contract keys differ")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "ACTIVE"),
        ("formal_verification", "PASS"),
        ("story_id", "ST-9999"),
    ],
)
def test_document_status_or_identity_promotion_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
) -> None:
    mutable_contract["document"][field] = value
    reject_contract(mutable_contract, "document identity/status differs")


def test_source_inventory_addition_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["sources"].append({"uri": "repo://README.md", "sha256": "0" * 64})
    reject_contract(mutable_contract, "source inventory differs")


def test_source_digest_substitution_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["sources"][0]["sha256"] = "0" * 64
    reject_contract(mutable_contract, "source inventory differs")


def test_duplicate_source_uri_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["sources"].append(dict(mutable_contract["sources"][0]))
    reject_contract(mutable_contract, "duplicate source uri")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("organization", "real-org", "organization must remain"),
        ("status", "VERIFIED", "cannot be presented as live-verified"),
    ],
)
def test_owner_binding_promotion_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
    message: str,
) -> None:
    mutable_contract["owner_bindings"][field] = value
    reject_contract(mutable_contract, message)


@pytest.mark.parametrize(
    "handle",
    [
        "security",
        "@RAOS/security",
        "@raos/security team",
        "@other/security",
        "@raos/engineering",
    ],
)
def test_invalid_or_mismatched_owner_handle_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    handle: str,
) -> None:
    mutable_contract["owner_bindings"]["teams"]["security"] = handle
    reject_contract(mutable_contract, "invalid GitHub team|does not match role")


def test_missing_owner_role_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    del mutable_contract["owner_bindings"]["teams"]["security"]
    reject_contract(mutable_contract, "owner role inventory differs")


def test_story_scope_ownership_cannot_diverge_from_scope_contract(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["story_scope_ownership"]["default_roles"] = ["security"]
    reject_contract(mutable_contract, "Story-scope ownership policy differs")


def test_codeowners_global_default_row_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["codeowners"]["entries"].insert(
        0, {"pattern": "*", "roles": ["engineering"]}
    )
    reject_contract(mutable_contract, "global default CODEOWNER row is forbidden")


def test_codeowners_github_row_must_be_last(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    entries = mutable_contract["codeowners"]["entries"]
    entries.insert(-1, entries.pop())
    reject_contract(mutable_contract, "must be the last")


def test_duplicate_codeowners_pattern_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["codeowners"]["entries"].insert(
        1, {"pattern": "/contracts/", "roles": ["engineering"]}
    )
    reject_contract(mutable_contract, "duplicate CODEOWNERS pattern")


@pytest.mark.parametrize(
    "pattern",
    ["relative/", "/unsafe path/", "/[unsupported]/", "/a/../b/", "/#comment/"],
)
def test_unsafe_or_unsupported_codeowners_pattern_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    pattern: str,
) -> None:
    mutable_contract["codeowners"]["entries"].insert(
        1, {"pattern": pattern, "roles": ["engineering"]}
    )
    reject_contract(
        mutable_contract,
        "must be root anchored|unsafe CODEOWNERS|unsupported CODEOWNERS",
    )


def test_unknown_codeowner_role_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    _entry(mutable_contract, "/apps/web/")["roles"] = ["unknown"]
    reject_contract(mutable_contract, "CODEOWNERS roles are invalid")


def test_duplicate_codeowner_role_is_rejected(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    _entry(mutable_contract, "/apps/web/")["roles"] = ["security", "security"]
    reject_contract(mutable_contract, "CODEOWNERS roles are duplicated")


def test_canonical_codeowner_row_cannot_be_weakened(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    _entry(mutable_contract, "/contracts/")["roles"] = ["architecture"]
    reject_contract(mutable_contract, "CODEOWNERS inventory differs")


def test_unreviewed_codeowners_entry_cannot_be_added(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["codeowners"]["entries"].insert(
        -1, {"pattern": "/extra/", "roles": ["engineering"]}
    )
    reject_contract(mutable_contract, "CODEOWNERS inventory differs")


def test_required_owner_category_cannot_reference_an_unowned_pattern(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["ruleset_policy"]["required_owner_categories"][
        "authentication_authorization_credentials"
    ]["patterns"].append("/not-owned/")
    reject_contract(mutable_contract, "required owner categories differ")


def test_required_owner_category_inventory_cannot_be_reduced(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    del mutable_contract["ruleset_policy"]["required_owner_categories"][
        "migration_database"
    ]
    reject_contract(mutable_contract, "required owner categories differ")


def test_effective_last_match_owners_cannot_drop_intersecting_category_roles(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _entry(mutable_contract, "/changes/st-0106/contracts/")["roles"] = [
        "security",
        "operations",
    ]
    observed_entries = tuple(
        (row["pattern"], tuple(row["roles"]))
        for row in mutable_contract["codeowners"]["entries"]
    )
    monkeypatch.setattr(generator, "EXPECTED_CODEOWNER_ENTRIES", observed_entries)

    reject_contract(
        mutable_contract,
        "effective CODEOWNERS roles differ for mandatory representative",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("local_application_status", "ACTIVE"),
        ("bypass_actors", [{"actor_id": 1}]),
        ("prohibit_deletion", False),
        ("prohibit_force_push", False),
        ("require_linear_history", False),
        ("strict_required_status_checks_policy", False),
        ("do_not_enforce_on_create", True),
        ("include", ["refs/heads/main"]),
    ],
)
def test_fail_closed_ruleset_field_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: object,
) -> None:
    mutable_contract["ruleset_policy"][field] = value
    reject_contract(
        mutable_contract, f"ruleset policy field {field} is not fail-closed"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_merge_methods", ["merge", "squash"]),
        ("dismiss_stale_reviews_on_push", False),
        ("require_code_owner_review", False),
        ("require_last_push_approval", True),
        ("required_approving_review_count", 0),
        ("required_review_thread_resolution", False),
    ],
)
def test_pull_request_protection_cannot_be_weakened(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: object,
) -> None:
    mutable_contract["ruleset_policy"]["pull_request"][field] = value
    reject_contract(mutable_contract, "pull-request protection differs")


def test_required_check_context_cannot_drift(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["ruleset_policy"]["required_status_checks"][4]["context"] = (
        "Secret scan"
    )
    reject_contract(mutable_contract, "status-check inventory differs")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("expected_source", "any", "must be bound to GitHub Actions"),
        (
            "integration_id_binding",
            "12345",
            "required check source must remain unbound locally",
        ),
    ],
)
def test_required_check_source_binding_cannot_be_faked_locally(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
    message: str,
) -> None:
    mutable_contract["ruleset_policy"]["required_status_checks"][0][field] = value
    reject_contract(mutable_contract, message)


def test_workflow_job_name_drift_is_rejected(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generator,
        "_workflow_check_names",
        lambda root: (
            "Static",
            "Unit",
            "Contracts",
            "Database",
            "Storage",
            "Drift",
            "Validate status overlay",
        ),
    )
    reject_contract(mutable_contract, "drifted from workflow job names")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("generator_remote_mutation", "ALLOWED", "must never mutate GitHub"),
        ("live_status", "ACTIVE", "live ruleset application is not locally proven"),
        (
            "formal_tst_001",
            "PASS",
            "formal TST-001 cannot be promoted by local generation",
        ),
    ],
)
def test_activation_boundary_cannot_be_promoted_by_local_artifacts(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: str,
    message: str,
) -> None:
    mutable_contract["activation"][field] = value
    reject_contract(mutable_contract, message)


def test_activation_prerequisite_cannot_be_omitted(
    mutable_contract: dict[str, Any], reject_contract: RejectContract
) -> None:
    mutable_contract["activation"]["prerequisites"].pop()
    reject_contract(mutable_contract, "activation prerequisite inventory differs")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("require_not_applicable_rationale", False),
        ("require_dev_check", False),
        ("require_hosted_ci", False),
        ("require_exact_head_human_review", False),
        ("independent_automated_review", "SELF_ATTESTED"),
        ("require_deferred_formal_live_items", False),
        (
            "required_owner_categories",
            ["contract_codegen", "migration_database"],
        ),
    ],
)
def test_pull_request_template_review_requirements_cannot_be_reduced(
    mutable_contract: dict[str, Any],
    reject_contract: RejectContract,
    field: str,
    value: object,
) -> None:
    mutable_contract["pull_request_template"][field] = value
    reject_contract(mutable_contract, "pull-request template extension differs")
