"""Contract binding and automated-preflight boundary tests."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from .support import (
    CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES,
    EXPECTED_ARCHIVE_TUPLE,
    EXPECTED_ARCHIVE_BYTES,
    EXPECTED_ARCHIVE_MEMBER_BYTES,
    EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
    EXPECTED_APPROVED_INPUT_SOURCE_PATH,
    EXPECTED_BOUNDARY_CLOSURE_COUNT,
    EXPECTED_BOUNDARY_EXPLICIT_ALIAS_COUNT,
    EXPECTED_BOUNDARY_GENERATED_ALIAS_COUNT,
    EXPECTED_BOUNDARY_PATTERN_COUNTS,
    EXPECTED_BOUNDARY_REPRESENTATIVE_ALIASES,
    EXPECTED_HANDOFF_BYTES,
    EXPECTED_INVENTORY_SHA256,
    EXPECTED_LOCK_VERSION_RELATIONS,
    EXPECTED_PHYSICAL_TABLE_RELATIONS,
    EXPECTED_OWNER_APPROVAL_STATEMENT_SHA256,
    EXPECTED_REPOSITORY_TEXT_BYTES,
    EXPECTED_SQL_FRAGMENT_BYTES,
    EXPECTED_STATE_CAS_RELATIONS,
    EXPECTED_TABLE_COUNT,
    EXPECTED_VIEW_COUNT,
    EXPECTED_YAML_DEPTH,
    EXPECTED_YAML_NODES,
    REPOSITORY_ROOT,
    TRUSTED_V2_BUNDLE_SOURCE_REFERENCE_TUPLES,
    build_pass_candidate,
    load_validator_module,
    report,
    run_validator,
)


def test_contract_declares_only_mechanical_preflight_authority() -> None:
    import yaml

    contract = yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
        ).read_text(encoding="utf-8")
    )
    document = contract["document"]
    assert document["story_id"] == "ST-0308"
    assert document["status"] == "LOCAL_AUTOMATED_PREFLIGHT_ONLY"
    assert document["authority"] == "NOT_IMPLEMENTATION_AUTHORITY"
    assert document["semantic_authority"] == "MANUAL_ONLY"
    assert document["network_access"] == "FORBIDDEN"
    assert document["repository_writes"] == "FORBIDDEN"

    cli = contract["cli"]
    assert cli["required_arguments"] == [
        "--handoff PATH",
        "--expected-sha256 LOWERCASE_64_HEX",
    ]
    assert cli["exit_codes"] == {
        "pass": 0,
        "candidate_validation_failure": 1,
        "usage_or_trusted_environment_failure": 2,
    }
    assert cli["report_binding"]["candidate_sha256"] == (
        "REQUIRED_WHEN_CANDIDATE_BYTES_ARE_READ"
    )
    assert cli["report_binding"]["oversized_candidate_sha256"] == (
        "BOUNDED_PREFIX_DIGEST_WITH_COMPLETE_FALSE"
    )
    assert cli["report_binding"]["implementation_authority"] == "NOT_GRANTED"
    assert cli["report_binding"]["exact_byte_owner_approval_required"] is True
    assert cli["report_binding"]["manual_canonical_reconciliation_required"] is True

    assert contract["limits"] == {
        "handoff_bytes": EXPECTED_HANDOFF_BYTES,
        "repository_text_bytes": EXPECTED_REPOSITORY_TEXT_BYTES,
        "sql_fragment_bytes": EXPECTED_SQL_FRAGMENT_BYTES,
        "archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "yaml_depth": EXPECTED_YAML_DEPTH,
        "yaml_nodes": EXPECTED_YAML_NODES,
        "archive_member_bytes": EXPECTED_ARCHIVE_MEMBER_BYTES,
        "archive_uncompressed_regular_bytes": EXPECTED_ARCHIVE_UNCOMPRESSED_REGULAR_LIMIT,
    }

    mandatory = set(contract["candidate"]["mandatory_fields"])
    assert mandatory == {
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
        "open_decisions",
    }
    assert set(contract["candidate"]["optional_boundary_sections"]) == {
        "authority",
        "approval",
    }
    boundary = contract["candidate"]["approval_boundary"]
    assert set(boundary["canonical_fields"]) == {
        "status",
        "implementation_authority",
        "owner_approval",
        "approved_by",
        "approved_at",
        "timestamp",
        "canonical_reconciliation",
    }
    assert boundary["subject_field_bindings"] == {
        "authority": "implementation_authority",
        "approval": "status",
        "implementation": "implementation_authority",
        "implementation_authority": "implementation_authority",
        "owner": "owner_approval",
        "owner_approval": "owner_approval",
        "canonical_reconciliation": "canonical_reconciliation",
    }
    grammar = boundary["finite_alias_grammar"]
    assert grammar["max_generated_aliases"] == 8192
    assert (
        grammar["expected_generated_aliases"] == EXPECTED_BOUNDARY_GENERATED_ALIAS_COUNT
    )
    assert set(grammar["patterns"]) == load_validator_module()._BOUNDARY_PATTERN_IDS
    assert set(grammar["subject_tokens"]) == {
        "authority",
        "approval",
        "implementation",
        "implementation_authority",
        "owner",
        "owner_approval",
        "canonical_reconciliation",
    }
    assert set(grammar["predicate_tokens"]) == {
        "approval",
        "approved",
        "authorization",
        "authorized",
        "authorisation",
        "authorised",
        "completion",
        "complete",
        "completed",
        "grant",
        "granted",
    }
    assert grammar["status_tokens"] == ["status"]
    assert grammar["identity_suffix_tokens"] == ["by"]
    assert set(grammar["time_suffix_tokens"]) == {"at", "timestamp"}
    assert set(boundary["allowed_value_classes"]) == {
        "status",
        "implementation_authority",
        "owner_approval",
        "approved_by",
        "approved_at",
        "timestamp",
        "canonical_reconciliation",
    }
    assert set(boundary["value_aliases"]) == {
        "proposal",
        "pending",
        "blocked",
        "not_granted",
        "not_executed",
    }
    assert set(boundary["boundary_section_aliases"]) == {"authority", "approval"}
    assert len(boundary["explicit_aliases"]) == EXPECTED_BOUNDARY_EXPLICIT_ALIAS_COUNT
    assert {row["alias"] for row in boundary["explicit_aliases"]} == {
        "automated_pass_authorizes_implementation",
        "automated_pass_authorises_implementation",
        "automated_pass_authorized_implementation",
        "automated_pass_authorised_implementation",
    }

    required_member = contract["source_inputs"]["required_archive_members"][0]
    assert required_member == {
        "id": "approved_but_rejected_handoff",
        "archive_path": EXPECTED_ARCHIVE_TUPLE[0],
        "archive_sha256": EXPECTED_ARCHIVE_TUPLE[1],
        "member_path": EXPECTED_ARCHIVE_TUPLE[2],
        "member_sha256": EXPECTED_ARCHIVE_TUPLE[3],
    }
    contract_lock_relations = set(
        contract["physical_reconstruction"]["lock_version_relations"]
    )
    assert contract_lock_relations == set(EXPECTED_LOCK_VERSION_RELATIONS)
    assert len(contract_lock_relations) == 27
    assert len(EXPECTED_PHYSICAL_TABLE_RELATIONS) == EXPECTED_TABLE_COUNT
    contract_state_relations = set(
        contract["physical_reconstruction"]["non_version_state_cas_required"]
    )
    assert contract_state_relations == set(EXPECTED_STATE_CAS_RELATIONS)
    assert len(contract_state_relations) == 24
    assert contract_state_relations <= set(EXPECTED_PHYSICAL_TABLE_RELATIONS)
    assert contract_state_relations.isdisjoint(contract_lock_relations)
    assert contract["physical_reconstruction"]["table_count"] == EXPECTED_TABLE_COUNT
    assert contract["physical_reconstruction"]["view_count"] == EXPECTED_VIEW_COUNT
    assert (
        contract["physical_reconstruction"]["normalized_inventory_sha256"]
        == EXPECTED_INVENTORY_SHA256
    )
    assert (
        contract["v2_bundle"]["approved_input_source_path"]
        == EXPECTED_APPROVED_INPUT_SOURCE_PATH
    )
    assert (
        contract["v2_bundle"]["owner_approval_statement_sha256"]
        == EXPECTED_OWNER_APPROVAL_STATEMENT_SHA256
    )
    contract_refs = {
        (row["path"], row["sha256"])
        for row in contract["source_inputs"]["required_repository_refs"]
        + contract["source_inputs"]["required_st0304_physical_fragments"]
    }
    assert contract_refs == set(CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES)
    trusted_v2_bundle_refs = {
        (row["path"], row["sha256"])
        for row in contract["source_inputs"]["trusted_v2_bundle_source_refs"]
    }
    assert trusted_v2_bundle_refs == set(TRUSTED_V2_BUNDLE_SOURCE_REFERENCE_TUPLES)
    assert contract_refs.isdisjoint(trusted_v2_bundle_refs)
    assert contract["source_inputs"]["trusted_v2_bundle_source_reference_policy"] == (
        "INTERNAL_BUNDLE_VALIDATION_ONLY_DIRECT_CANDIDATE_REFERENCE_FORBIDDEN"
    )
    assert "d6_connection_and_identity_boundary_semantics" in set(
        contract["automated_checks"]["manual_topics_even_after_pass"]
    )


def _boundary_contract() -> dict[str, Any]:
    return yaml.safe_load(
        (
            REPOSITORY_ROOT
            / "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
        ).read_text(encoding="utf-8")
    )


def test_boundary_grammar_has_independent_exact_compiled_closure() -> None:
    validator = load_validator_module()
    rules = validator._approval_boundary_rules(_boundary_contract())
    observed_pattern_counts = Counter(
        rule.pattern_id
        for rule in rules.aliases.values()
        if rule.pattern_id != "explicit_alias"
    )
    assert len(rules.aliases) == EXPECTED_BOUNDARY_CLOSURE_COUNT
    assert (
        sum(rule.pattern_id != "explicit_alias" for rule in rules.aliases.values())
        == EXPECTED_BOUNDARY_GENERATED_ALIAS_COUNT
    )
    assert (
        sum(rule.pattern_id == "explicit_alias" for rule in rules.aliases.values())
        == EXPECTED_BOUNDARY_EXPLICIT_ALIAS_COUNT
    )
    assert {
        pattern: observed_pattern_counts.get(pattern, 0)
        for pattern in EXPECTED_BOUNDARY_PATTERN_COUNTS
    } == EXPECTED_BOUNDARY_PATTERN_COUNTS
    assert EXPECTED_BOUNDARY_REPRESENTATIVE_ALIASES <= set(rules.aliases)


def test_boundary_false_policy_independent_oracle() -> None:
    validator = load_validator_module()
    rules = validator._approval_boundary_rules(_boundary_contract())

    expected_alias_policies = {
        "isstatus": False,
        "isapproval": True,
        "isauthorization": True,
        "isimplementationauthority": True,
        "isimplementationstatus": False,
        "isimplementationby": False,
        "isimplementationat": False,
        "isimplementationtimestamp": False,
        "authorized": True,
        "authorization": False,
        "implementation": False,
        "implementationauthorized": True,
        "implementationapproval": False,
        "authorizedimplementation": True,
        "approvalimplementation": False,
    }
    for normalized_alias, expected_false_allowed in expected_alias_policies.items():
        assert normalized_alias in rules.aliases
        assert rules.aliases[normalized_alias].false_allowed is expected_false_allowed

    assert all(
        rule.false_allowed is False
        for rule in rules.aliases.values()
        if rule.pattern_id.endswith(("_status", "_by", "_at", "_timestamp"))
    )


def test_boundary_alias_normalization_surfaces_share_one_rule() -> None:
    validator = load_validator_module()
    rules = validator._approval_boundary_rules(_boundary_contract())
    expected = rules.aliases["canonicalreconciliationisapproved"]
    rendered = (
        "canonical_reconciliation_is_approved",
        "canonical-reconciliation-is-approved",
        "canonical reconciliation is approved",
        "canonical__reconciliation__is__approved",
        "canonicalReconciliationIsApproved",
        "CanonicalReconciliationIsApproved",
        "CANONICAL_RECONCILIATION_IS_APPROVED",
        "canonicalreconciliationisapproved",
    )
    assert {
        rules.aliases[validator._normalize_boundary_token(value)] for value in rendered
    } == {expected}


def test_every_generated_alias_has_true_failure_and_declared_false_policy() -> None:
    validator = load_validator_module()
    rules = validator._approval_boundary_rules(_boundary_contract())
    for rule in rules.aliases.values():
        assert validator._boundary_value_allowed(rule, True, rules) is False
        assert (
            validator._boundary_value_allowed(rule, False, rules) is rule.false_allowed
        )
        if rule.pattern_id != "explicit_alias":
            for dangerous in (
                "APPROVAL",
                "APPROVED",
                "AUTHORIZATION",
                "AUTHORIZED",
                "AUTHORISED",
                "COMPLETION",
                "COMPLETE",
                "COMPLETED",
                "GRANT",
                "GRANTED",
            ):
                assert (
                    validator._boundary_value_allowed(rule, dangerous, rules) is False
                )


def test_boundary_grammar_rejects_unknown_pattern_id() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "patterns"
    ].append("arbitrary_regex")
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_pattern_unknown"


def test_boundary_grammar_rejects_missing_pattern_id() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    patterns = contract["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "patterns"
    ]
    patterns.remove("is_subject_is_predicate_timestamp")
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_pattern_set_invalid"


def test_boundary_grammar_rejects_duplicate_pattern_id() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "patterns"
    ].append("subject_predicate")
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_pattern_duplicate"


def test_boundary_grammar_rejects_invalid_non_lowercase_token() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "subject_tokens"
    ][0] = "Authority"
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_token_invalid"


def test_boundary_grammar_rejects_cross_field_collision() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["explicit_aliases"][0].update(
        alias="implementation_authority", field="status"
    )
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_alias_collision"


def test_boundary_grammar_rejects_conflicting_false_policy() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["explicit_aliases"][0].update(
        alias="authorization_granted", field="status", false_allowed=False
    )
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_alias_false_policy_conflict"


def test_boundary_grammar_rejects_false_for_non_boolean_explicit_field() -> None:
    validator = load_validator_module()
    contract = _boundary_contract()
    contract["candidate"]["approval_boundary"]["explicit_aliases"][0].update(
        alias="manual_approval_time", field="approved_at", false_allowed=True
    )
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(contract)
    assert error.value.code == "contract_boundary_explicit_alias_semantics_invalid"


def test_boundary_grammar_enforces_exact_maximum_and_expected_count() -> None:
    validator = load_validator_module()
    exact = _boundary_contract()
    grammar = exact["candidate"]["approval_boundary"]["finite_alias_grammar"]
    grammar["max_generated_aliases"] = EXPECTED_BOUNDARY_GENERATED_ALIAS_COUNT
    assert (
        len(validator._compile_boundary_aliases(exact))
        == EXPECTED_BOUNDARY_CLOSURE_COUNT
    )

    one_below = copy.deepcopy(exact)
    below_grammar = one_below["candidate"]["approval_boundary"]["finite_alias_grammar"]
    below_grammar["max_generated_aliases"] -= 1
    below_grammar["expected_generated_aliases"] -= 1
    with pytest.raises(validator.TrustedFailure) as overflow:
        validator._compile_boundary_aliases(one_below)
    assert overflow.value.code == "contract_boundary_generated_alias_overflow"

    mismatch = _boundary_contract()
    mismatch["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "expected_generated_aliases"
    ] += 1
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(mismatch)
    assert error.value.code == "contract_boundary_generated_alias_count_mismatch"

    hard_cap = _boundary_contract()
    hard_cap["candidate"]["approval_boundary"]["finite_alias_grammar"][
        "max_generated_aliases"
    ] = 8193
    with pytest.raises(validator.TrustedFailure) as error:
        validator._compile_boundary_aliases(hard_cap)
    assert error.value.code == "contract_boundary_generated_limit_invalid"


def test_boundary_aliases_retain_canonical_field_ownership() -> None:
    validator = load_validator_module()
    rules = validator._approval_boundary_rules(_boundary_contract())
    expected_fields = {
        "implementation_authorized_status": "implementation_authority",
        "implementation_is_authorized_status": "implementation_authority",
        "is_implementation_authorized_status": "implementation_authority",
        "authorization_granted_status": "status",
        "implementation_approved_by": "approved_by",
        "canonical_reconciliation_approved_at": "approved_at",
        "owner_approval_authorized_by": "approved_by",
        "implementation_authorized_timestamp": "timestamp",
        "is_authorization_implementation": "implementation_authority",
        "authorization_is_implementation": "implementation_authority",
    }
    for alias, field in expected_fields.items():
        assert rules.aliases[validator._normalize_boundary_token(alias)].field == field


def test_archived_candidate_never_authorizes_current_implementation(
    candidate_path: Path,
) -> None:
    process = run_validator(candidate_path)
    result = report(process)
    assert process.returncode in {0, 2}
    assert result["status"] in {"PASS_AUTOMATED_PREFLIGHT_ONLY", "ERROR"}
    assert result["implementation_authority"] == "NOT_GRANTED"
    assert result["automated_pass_authorizes_implementation"] is False
    assert result["semantic_validation"] == "MANUAL_REQUIRED"


def test_candidate_builder_is_self_contained_and_not_windows_bound() -> None:
    candidate: dict[str, Any] = build_pass_candidate()
    assert candidate["DESIGN_HANDOFF_V1"]["approved_story"]["id"] == "ST-0308"
    assert candidate["DESIGN_HANDOFF_V1"]["open_decisions"] == []


def test_candidate_fixture_uses_exact_independent_reference_sets(
    pass_candidate: dict[str, object],
) -> None:
    refs = pass_candidate["DESIGN_HANDOFF_V1"]["source_design_refs"][
        "required_v3_authority_inputs"
    ]  # type: ignore[index]
    direct = {(row["path"], row["sha256"]) for row in refs if "path" in row}  # type: ignore[union-attr]
    structured = {
        (
            row["archive_path"],
            row["archive_sha256"],
            row["member_path"],
            row["member_sha256"],
        )
        for row in refs
        if "archive_path" in row
    }  # type: ignore[union-attr]
    assert direct == set(CANDIDATE_REQUIRED_SOURCE_REFERENCE_TUPLES)
    assert structured == {EXPECTED_ARCHIVE_TUPLE}


def test_authority_and_approval_sections_are_optional(
    tmp_path: Path,
    pass_candidate: dict[str, object],
) -> None:
    import yaml

    payload = pass_candidate["DESIGN_HANDOFF_V1"]
    payload.pop("authority")  # type: ignore[union-attr]
    payload.pop("approval")  # type: ignore[union-attr]
    path = tmp_path / "optional-boundaries.yaml"
    path.write_text(
        yaml.safe_dump(pass_candidate, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    result = report(run_validator(path))
    assert result["status"] in {"PASS_AUTOMATED_PREFLIGHT_ONLY", "ERROR"}
    assert result["implementation_authority"] == "NOT_GRANTED"
