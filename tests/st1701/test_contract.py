"""Positive unresolved-registry semantics for ST-1701."""

from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from scripts import build_st1701_business_inputs as generator


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _tree_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for nested in value.values():
            keys.update(_tree_keys(nested))
        return keys
    if isinstance(value, list):
        list_keys: set[str] = set()
        for nested in value:
            list_keys.update(_tree_keys(nested))
        return list_keys
    return set()


def _leaf_values(value: object) -> list[object]:
    if isinstance(value, dict):
        return [leaf for nested in value.values() for leaf in _leaf_values(nested)]
    if isinstance(value, list):
        return [leaf for nested in value for leaf in _leaf_values(nested)]
    return [value]


def test_contract_is_closed_non_authoritative_and_unresolved(
    contract_document: dict[str, Any],
) -> None:
    assert tuple(contract_document) == generator.TOP_LEVEL_KEYS
    assert contract_document["document"] == {
        "id": "RAOS-UNRESOLVED-MVP-BUSINESS-INPUTS-001",
        "version": "1.0.0",
        "story_id": "ST-1701",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "classification": "SOURCE_DERIVED_NON_AUTHORITATIVE_UNRESOLVED_REGISTRY",
        "executable": False,
        "canonical_acceptance_achieved": False,
    }
    assert contract_document["activation"] == {
        "enabled": False,
        "status": "BLOCKED_UNRESOLVED_INPUTS",
    }


def test_exact_seven_decisions_remain_active_blockers(
    contract_document: dict[str, Any],
) -> None:
    decisions = cast(list[dict[str, Any]], contract_document["decisions"])
    assert tuple(row["id"] for row in decisions) == generator.SCOPED_IDS
    assert len(decisions) == 7
    assert all(row["blocking"] is True for row in decisions)
    assert all(row["resolution_state"] == "UNRESOLVED" for row in decisions)
    assert all(row["active_blocker"] is True for row in decisions)
    assert all(
        tuple(row["blocked_targets"]) == generator.BLOCKED_TARGETS for row in decisions
    )
    assert all(row["safe_default_is_resolution"] is False for row in decisions)
    assert all(row["selected_value"] is None for row in decisions)
    assert all(row["resolution_payload"] == "FORBIDDEN_IN_V1" for row in decisions)
    by_id = {row["id"]: row for row in decisions}
    assert by_id["OD-006"]["source_status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert all(
        row["source_status"] == "HUMAN_DECISION_REQUIRED"
        for identifier, row in by_id.items()
        if identifier != "OD-006"
    )


def test_global_blockers_are_not_hidden_by_scoped_projection(
    reference_document: dict[str, object],
) -> None:
    registry = _mapping(reference_document["registry"])
    assert registry["decision_count"] == 7
    assert registry["resolved_count"] == 0
    assert registry["unresolved_count"] == 7
    assert registry["active_blocker_count"] == 7
    assert registry["global_decision_count"] == 15
    assert registry["global_unresolved_blocker_count"] == 14
    assert registry["global_blocked_target_count"] == 6
    assert tuple(registry["blocked_targets"]) == generator.BLOCKED_TARGETS


def test_all_business_values_remain_unset_and_safe_defaults_stay_fallbacks(
    contract_document: dict[str, Any],
) -> None:
    assert contract_document["business_inputs"] == generator.EXPECTED_BUSINESS_INPUTS
    assert all(value is None for value in contract_document["business_inputs"].values())
    assert contract_document["safe_defaults"] == generator.EXPECTED_SAFE_DEFAULTS
    safe = _mapping(contract_document["safe_defaults"])
    assert safe["selected_values"] == "FORBIDDEN"
    assert safe["safe_defaults_are_resolutions"] is False
    assert safe["synthetic_fixtures_only"] is True
    assert safe["external_publication"] == "BLOCKED"
    assert safe["production"] == "DISABLED"


def test_all_gates_actions_and_downstream_readiness_remain_blocked(
    contract_document: dict[str, Any],
) -> None:
    gates = cast(list[dict[str, Any]], contract_document["gates"])
    assert tuple(row["gate_id"] for row in gates) == generator.GATE_IDS
    assert all(
        row["status"] == "BLOCKED" and row["blocker_count"] == 7 for row in gates
    )
    action = _mapping(contract_document["action_boundary"])
    assert action == generator.EXPECTED_ACTION_BOUNDARY
    assert all(
        type(value) is int and value == 0 for value in action["action_counts"].values()
    )
    assert (
        contract_document["evidence_boundary"] == generator.EXPECTED_EVIDENCE_BOUNDARY
    )
    assert (
        contract_document["downstream_boundary"]
        == generator.EXPECTED_DOWNSTREAM_BOUNDARY
    )


def test_gold_validation_report_is_exact_fail_closed_preapproval_interface(
    gold_validation_document: dict[str, object],
) -> None:
    assert tuple(gold_validation_document) == (
        "schema",
        "story_id",
        "status",
        "stop_code",
        "authority",
        "authority_binding",
        "collection_feasibility",
        "closed_evidence_contract",
        "ledger_boundary",
        "required_handoff_addendum",
        "non_promotion_boundary",
    )
    assert gold_validation_document["schema"] == "GOLD_EVIDENCE_VALIDATION_V1"
    assert gold_validation_document["story_id"] == "ST-1701"
    assert gold_validation_document["status"] == "EVIDENCE_INSUFFICIENT"
    assert gold_validation_document["stop_code"] == "STOP_EVIDENCE_INSUFFICIENT"
    assert gold_validation_document["authority"] == "PROPOSAL_ONLY_NON_CANONICAL"
    assert gold_validation_document["authority_binding"] == {
        "handoff": {
            "uri": f"repo://{generator.GOLD_HANDOFF_PATH.as_posix()}",
            "bytes": generator.GOLD_HANDOFF_BYTES,
            "sha256": generator.GOLD_HANDOFF_SHA256,
        },
        "detached_approval": {
            "uri": f"repo://{generator.GOLD_HANDOFF_APPROVAL_PATH.as_posix()}",
            "bytes": generator.GOLD_HANDOFF_APPROVAL_BYTES,
            "sha256": generator.GOLD_HANDOFF_APPROVAL_SHA256,
            "status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_authority": (
                "ST1701_GOLD_EVIDENCE_CANONICAL_REVISION_V1_ONLY"
            ),
            "open_decisions": [],
        },
    }


def test_gold_validation_reports_only_bounded_observed_collection_facts(
    gold_validation_document: dict[str, object],
) -> None:
    assert gold_validation_document["collection_feasibility"] == {
        "category_id": "suitcase_and_carry_bags",
        "collection_mode": "BOUNDED_PUBLIC_PAGE_DESK_RESEARCH",
        "ranking_source": "PUBLIC_RAKUTEN_OFFICIAL_SUITCASE_RANKING",
        "ranking_url": "https://ranking.rakuten.co.jp/daily/301577/",
        "ranking_observed_at": "2026-08-12T02:30:56+09:00",
        "snapshot_update_date": "2026-08-11",
        "snapshot_aggregate_date": "2026-08-10",
        "required_first_bound": "TOP_50_AT_SNAPSHOT",
        "accessible_contiguous_rank_positions": {"first": 1, "last": 20},
        "unavailable_required_same_snapshot_positions": {"first": 21, "last": 50},
        "same_snapshot_top_50_route_found": False,
        "top_100_expansion_reached": False,
        "candidate_bound_exhaustion_claimed": False,
        "stale_snapshot_mixing_refused": True,
        "ranking_entries_are_family_seeds_not_observations": True,
        "out_of_pool_manual_substitution": "FORBIDDEN",
        "page_bodies_archived": False,
    }


def test_gold_validation_exposes_closed_target_without_claiming_complete_schema(
    gold_validation_document: dict[str, object],
) -> None:
    assert gold_validation_document["closed_evidence_contract"] == {
        "ledger_uri": f"repo://{generator.GOLD_LEDGER_PATH.as_posix()}",
        "complete_ledger_acceptance_enabled": False,
        "closed_counts": {
            "listing_count": 30,
            "family_count": 10,
            "listings_per_family": 3,
            "minimum_shops_per_family": 2,
            "minimum_shop_count": 5,
            "minimum_brand_count": 5,
            "maximum_families_per_brand": 2,
            "unordered_pair_count": 435,
        },
        "required_case_tags": list(generator.GOLD_REQUIRED_CASE_TAGS),
        "price_mix": {
            "low_family_count": 4,
            "mid_family_count": 4,
            "high_family_count": 2,
        },
        "required_exact_identity_fields": list(generator.OD006_REQUIRED_FIELDS),
        "jan_policy": {
            "accepted_lengths": [8, 13],
            "digits_only": True,
            "valid_ean_check_digit_required": True,
            "either_present": (
                "BOTH_PRESENT_VALID_AND_EXACTLY_EQUAL_FOR_AUTOMATIC_MERGE"
            ),
            "both_absent": ("NEUTRAL_DOES_NOT_AUTHORIZE_OR_VETO_OTHERWISE_EXACT_PAIR"),
            "invalid_or_conflicting": "HUMAN_REVIEW",
        },
        "pair_population": "ALL_435_UNORDERED_PAIRS_DERIVED_FROM_EXACT_30_LISTING_IDS",
        "derived_unordered_pair_count": 435,
        "pair_result_values": ["AUTOMATIC_MERGE", "HUMAN_REVIEW"],
        "maximum_false_automatic_merges": 0,
        "pair_metrics_emitted": False,
    }
    assert gold_validation_document["required_handoff_addendum"] == list(
        generator.GOLD_CONTRACT_MAPPING_GAPS
    )
    assert len(generator.GOLD_CONTRACT_MAPPING_GAPS) == 11


def test_gold_validation_has_no_ledger_resolution_bundle_or_promotion_claim(
    gold_validation_document: dict[str, object],
) -> None:
    assert gold_validation_document["ledger_boundary"] == {
        "ledger_present": False,
        "domain_editor_approval_uri": (
            f"repo://{generator.GOLD_EVIDENCE_APPROVAL_PATH.as_posix()}"
        ),
        "domain_editor_approval_present": False,
        "preapproval_result_uri": f"repo://{generator.GOLD_VALIDATION_PATH.as_posix()}",
        "gold_summary_generated": False,
        "resolution_candidates_generated": False,
        "open_decisions_revision_candidate_generated": False,
        "gold_canonical_revision_request_generated": False,
        "canonical_revision_bundle_manifest_generated": False,
        "canonical_revision_bundle_approval_present": False,
        "existing_predecessor_canonical_revision_request_preserved": True,
    }
    assert gold_validation_document["non_promotion_boundary"] == {
        "evidence_authority": "NONE",
        "maximum_evidence_authority_after_valid_domain_editor_approval": (
            "OWNER_REVIEWED_CANONICAL_REVISION_EVIDENCE_CANDIDATE_ONLY"
        ),
        "canonical_mutation_authority": "NONE",
        "canonical_open_decision_status": "UNCHANGED_UNTIL_SEPARATE_IMPORT",
        "canonical_scoped_unresolved_count": 7,
        "global_unresolved_blocker_count": 14,
        "st0006_blocker_state": "UNCHANGED_UNTIL_SEPARATE_IMPORT",
        "gate_state": "BLOCKED",
        "st1701_acceptance": "NOT_ACHIEVED",
        "tst_032": "NOT_EXECUTED",
        "st1607": "ABSENT_NOT_IMPLEMENTED_HERE",
        "st1702_ready": False,
        "status_overlays": "UNCHANGED",
        "staging": "NOT_EXECUTED",
        "publication": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }

    prohibited_material_keys = {
        "observations",
        "family_assertions",
        "pair_results",
        "source_reasoning",
        "page_html",
        "page_image",
        "screenshot",
        "review_text",
        "rating_comment",
        "personal_data",
        "credential",
        "cookie",
        "session_data",
        "raw_prompt",
    }
    assert _tree_keys(gold_validation_document).isdisjoint(prohibited_material_keys)
    assert set(_leaf_values(gold_validation_document)).isdisjoint(
        {"RESOLVED", "VALIDATED", "PASS", "ACHIEVED", "READY", "PRODUCTION_READY"}
    )


def test_decision_package_preserves_internal_pending_proposal_state(
    decision_package: dict[str, Any],
) -> None:
    assert tuple(decision_package) == generator.DECISION_PACKAGE_TOP_LEVEL_KEYS
    assert decision_package["document"] == generator.EXPECTED_DECISION_DOCUMENT
    authority = _mapping(decision_package["implementation_authority"])
    assert authority["mode"] == "STRICT_STORY"
    assert authority["approved_story"] == "ST-1701"
    assert authority["open_decisions"] == []
    assert authority["handoff"]["sha256"] == generator.HANDOFF_SHA256
    assert authority["approval"]["sha256"] == generator.HANDOFF_APPROVAL_SHA256
    assert authority["approval"]["status"] == "APPROVED_FOR_IMPLEMENTATION"
    assert (
        authority["approval"]["implementation_authority"]
        == "ST1701_MVP_DECISION_PACKAGE_V1_ONLY"
    )
    assert (
        decision_package["final_package_approval"]
        == generator.EXPECTED_FINAL_PACKAGE_APPROVAL
    )


def test_detached_final_approval_is_exact_and_non_authoritative(
    final_package_approval: dict[str, Any],
) -> None:
    expected = generator.EXPECTED_FINAL_PACKAGE_APPROVAL_DOCUMENT[
        "MVP_BUSINESS_DECISION_PACKAGE_APPROVAL_V1"
    ]
    assert final_package_approval == expected
    assert final_package_approval["source_package_sha256"] == (
        generator.APPROVED_DECISION_PACKAGE_SHA256
    )
    assert final_package_approval["source_package_bytes"] == (
        generator.APPROVED_DECISION_PACKAGE_BYTES
    )
    assert final_package_approval["status"] == generator.FINAL_PACKAGE_APPROVAL_STATUS
    assert final_package_approval["authority"] == (
        generator.FINAL_PACKAGE_APPROVAL_AUTHORITY
    )
    assert final_package_approval["open_decisions"] == []
    assert final_package_approval["effective_boundary"] == {
        "source_package_internal_pending_field": ("PRESERVED_IMMUTABLE_PROPOSAL_STATE"),
        "detached_exact_hash_approval": "EFFECTIVE",
        "canonical_revision_request": (generator.CANONICAL_REVISION_REQUEST_STATUS),
        "canonical_mutation_authority": "NONE",
        "canonical_open_decision_status": "UNCHANGED",
        "st0006_blocker_state": "UNCHANGED",
        "gate_state": "BLOCKED",
        "st1701_acceptance": "NOT_ACHIEVED",
        "st1702_ready": False,
    }


def test_scoped_owner_candidate_values_are_exact_and_ordered(
    decision_package: dict[str, Any],
) -> None:
    rows = cast(list[dict[str, Any]], decision_package["scoped_decisions"])
    assert tuple(row["id"] for row in rows) == generator.SCOPED_IDS
    assert tuple(row["record_status"] for row in rows) == (
        "OWNER_APPROVED",
        "EXECUTION_PENDING",
        "PARTIAL",
        "EVIDENCE_PENDING",
        "OWNER_APPROVED",
        "OWNER_APPROVED",
        "OWNER_APPROVED",
    )
    by_id = {row["id"]: row for row in rows}
    assert by_id["OD-001"]["selected_value"] == {
        "category_id": "suitcase_and_carry_bags",
        "display_name_ja": "スーツケース・キャリーバッグ",
    }
    assert by_id["OD-001"]["runtime_activation"] == "DISABLED"

    od002 = by_id["OD-002"]
    assert od002["selected_value"] == {
        "brand_name": "旅具比較ノート",
        "formal_domain_candidate": "tabigu-note.jp",
        "operator_form": "INDIVIDUAL_SOLE_PROPRIETOR_WITH_TRADE_NAME",
    }
    assert od002["execution_state"] == {
        "domain_purchase": "NOT_EXECUTED",
        "domain_control_evidence": "NOT_OBTAINED",
        "public_activation": "FORBIDDEN",
    }
    assert od002["domain_rules"]["fallback_domain"] == "example.invalid"
    assert od002["domain_rules"]["candidate_is_not_ownership_evidence"] is True

    od005 = by_id["OD-005"]
    assert od005["selected_value"]["primary_reviewer"] == "REPOSITORY_OWNER"
    assert od005["selected_value"]["alternate_reviewer"] is None
    assert od005["selected_value"]["standard_labor_cost"] == {
        "amount": 3000,
        "currency": "JPY",
        "unit": "HOUR",
    }
    assert od005["publication_until_alternate_or_explicit_exception"] == "BLOCKED"

    od006 = by_id["OD-006"]
    assert tuple(od006["selected_value"]["required_exact_fields"]) == (
        generator.OD006_REQUIRED_FIELDS
    )
    assert od006["selected_value"]["automatic_merge"] == "EXACT_MATCH_ONLY"
    assert od006["selected_value"]["fuzzy_matching"] == "FORBIDDEN"
    assert od006["selected_value"]["inferred_equivalence"] == "FORBIDDEN"
    assert od006["evidence_gate"]["minimum_listing_count"] == 30
    assert od006["evidence_gate"]["minimum_product_family_count"] == 10
    assert od006["evidence_gate"]["minimum_shop_count"] == 5
    assert od006["evidence_gate"]["maximum_false_automatic_merges"] == 0
    assert (
        od006["runtime_automatic_merge"]
        == "DISABLED_PENDING_EVIDENCE_AND_CANONICAL_REVISION"
    )

    od007 = by_id["OD-007"]["selected_value"]
    assert od007["maximum_age"] == {
        "price_hours": 72,
        "availability_hours": 48,
        "affiliate_link_hours": 72,
        "major_specifications_days": 90,
        "image_days": 30,
    }
    assert od007["stale_never_treated_as_fresh"] is True

    od008 = by_id["OD-008"]["selected_value"]
    assert od008["legal_judgment_by_ai_or_developer"] == "FORBIDDEN"
    assert od008["professional_decision_record_required"] is True

    od009 = by_id["OD-009"]["selected_value"]
    assert od009["currency"] == "JPY"
    assert od009["monthly_external_spend_cap"] == 30000
    assert od009["thresholds"] == {
        "warning_percent": 60,
        "optional_external_work_stop_percent": 80,
        "hard_stop_new_external_spend_percent": 100,
    }
    assert od009["initial_soft_allocation"] == {
        "aws": 15000,
        "llm": 10000,
        "other_external": 5000,
    }
    assert od009["acceptable_loss_window"] == {
        "months": 3,
        "cumulative_amount": 90000,
        "terminal_decision": "EXPLICIT_GO_NO_GO",
    }
    assert od009["overrun_behavior"] == "FAIL_CLOSED_NO_NEW_EXTERNAL_SPEND"


def test_informational_inventory_is_closed_and_has_no_status_effect(
    decision_package: dict[str, Any],
) -> None:
    inventory = _mapping(decision_package["informational_cross_story_owner_inputs"])
    rows = cast(list[dict[str, Any]], inventory["rows"])
    assert (
        inventory["authority"] == "INFORMATION_ONLY_NO_IMPLEMENTATION_OR_STATUS_EFFECT"
    )
    assert inventory["owner_follow_up_required"] is True
    assert tuple(row["id"] for row in rows) == generator.INFORMATIONAL_IDS
    assert tuple(row["record_status"] for row in rows) == (
        "EVIDENCE_PENDING",
        "OWNER_APPROVED",
        "EXECUTION_PENDING",
        "PARTIAL",
        "PARTIAL",
        "OWNER_APPROVED",
        "PARTIAL",
        "EXECUTION_PENDING",
    )
    assert decision_package["canonical_truth_boundary"] == (
        generator.EXPECTED_CANONICAL_TRUTH_BOUNDARY
    )


def test_informational_rows_cannot_be_forged_into_projection_or_revision_request(
    decision_package: dict[str, Any], contract_document: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(decision_package)
    rows = mutated["informational_cross_story_owner_inputs"]["rows"]
    rows[0]["selection"] = "MUST_NOT_AFFECT_BOUNDARIES"
    with pytest.raises(generator.BusinessInputsError):
        generator.decision_read_model(mutated, contract_document, generator.REPO_ROOT)
    with pytest.raises(generator.BusinessInputsError):
        generator.canonical_revision_request_bytes(mutated)


def test_read_model_keeps_owner_candidates_separate_from_canonical_truth(
    decision_read_model: dict[str, object],
) -> None:
    rows = cast(list[dict[str, Any]], decision_read_model["scoped_decisions"])
    assert tuple(row["id"] for row in rows) == generator.SCOPED_IDS
    assert all(
        row["canonical_truth"]["resolution_state"] == "UNRESOLVED" for row in rows
    )
    assert all(row["canonical_truth"]["active_blocker"] is True for row in rows)
    assert all(row["canonical_truth"]["selected_value"] is None for row in rows)
    assert rows[0]["owner_decision_candidate"]["record_status"] == "OWNER_APPROVED"
    evidence = cast(dict[str, Any], decision_read_model["evidence_boundary"])
    assert evidence["source_package_internal"] == (
        generator.EXPECTED_DECISION_EVIDENCE_BOUNDARY
    )
    assert evidence["effective_final_package_owner_approval"] == {
        "status": generator.FINAL_PACKAGE_APPROVAL_STATUS,
        "authority": generator.FINAL_PACKAGE_APPROVAL_AUTHORITY,
        "approval_sha256": generator.FINAL_PACKAGE_APPROVAL_SHA256,
    }
    assert evidence["canonical_revision_request_readiness"] == "NOT_READY"


def _synthetic_sku(*, jan: object = "4900000000009") -> dict[str, object]:
    row: dict[str, object] = {
        "brand": "Synthetic Brand",
        "manufacturer_model": "SYN-001",
        "size": "M",
        "capacity": "40L",
        "external_dimensions": "55x40x25cm",
        "color_or_variant": "blue",
        "set_count": 1,
    }
    if jan is not None:
        row["jan"] = jan
    return row


def test_od006_synthetic_exact_duplicate_and_optional_absent_jan() -> None:
    left = _synthetic_sku()
    assert (
        generator.evaluate_od006_synthetic_pair(left, dict(left)) == "EXACT_MATCH_ONLY"
    )
    without_jan = _synthetic_sku(jan=None)
    assert (
        generator.evaluate_od006_synthetic_pair(without_jan, dict(without_jan))
        == "EXACT_MATCH_ONLY"
    )
    valid_ean8 = _synthetic_sku(jan="96385074")
    assert (
        generator.evaluate_od006_synthetic_pair(valid_ean8, dict(valid_ean8))
        == "EXACT_MATCH_ONLY"
    )


def test_od006_synthetic_matrix_has_zero_false_automatic_merges() -> None:
    baseline = _synthetic_sku()
    hostile_rows: list[dict[str, object]] = []
    for field, value in (
        ("color_or_variant", "red"),
        ("size", "L"),
        ("capacity", "60L"),
        ("set_count", 2),
        ("manufacturer_model", "SYN-002"),
    ):
        changed = dict(baseline)
        changed[field] = value
        hostile_rows.append(changed)
    missing_required = dict(baseline)
    missing_required.pop("brand")
    hostile_rows.append(missing_required)
    missing_jan = dict(baseline)
    missing_jan.pop("jan")
    hostile_rows.append(missing_jan)
    conflicting_jan = dict(baseline)
    conflicting_jan["jan"] = "4900000000016"
    hostile_rows.append(conflicting_jan)
    invalid_jan = dict(baseline)
    invalid_jan["jan"] = "4900000000000"
    hostile_rows.append(invalid_jan)
    for invalid_digit_only_jan in ("123456789", "12345678901234"):
        invalid_length = dict(baseline)
        invalid_length["jan"] = invalid_digit_only_jan
        hostile_rows.append(invalid_length)
    invalid_characters = dict(baseline)
    invalid_characters["jan"] = "INVALID"
    hostile_rows.append(invalid_characters)

    decisions = [
        generator.evaluate_od006_synthetic_pair(baseline, row) for row in hostile_rows
    ]
    assert decisions == ["HUMAN_REVIEW"] * len(hostile_rows)
    assert decisions.count("EXACT_MATCH_ONLY") == 0


def test_od006_gold_pair_keeps_exact_jan_matrix_and_predecessor_vocabulary() -> None:
    automatic_pairs = (
        (_synthetic_sku(), _synthetic_sku()),
        (_synthetic_sku(jan=None), _synthetic_sku(jan=None)),
        (_synthetic_sku(jan="96385074"), _synthetic_sku(jan="96385074")),
    )
    for left, right in automatic_pairs:
        assert generator.evaluate_od006_synthetic_pair(left, right) == (
            "EXACT_MATCH_ONLY"
        )
        assert generator.evaluate_od006_gold_pair(left, right) == "AUTOMATIC_MERGE"

    baseline = _synthetic_sku()
    review_pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for field, value in (
        ("brand", "synthetic brand"),
        ("manufacturer_model", "SYN-001 "),
        ("size", "Ｍ"),
        ("capacity", "40l"),
        ("external_dimensions", "55×40×25cm"),
        ("color_or_variant", "Blue"),
        ("set_count", 2),
    ):
        changed = dict(baseline)
        changed[field] = value
        review_pairs.append((baseline, changed))

    for missing_field in generator.OD006_REQUIRED_FIELDS:
        missing = dict(baseline)
        missing.pop(missing_field)
        review_pairs.append((baseline, missing))

    empty_required = dict(baseline)
    empty_required["brand"] = ""
    review_pairs.append((baseline, empty_required))
    bool_set_count = dict(baseline)
    bool_set_count["set_count"] = True
    review_pairs.append((baseline, bool_set_count))
    invalid_set_counts: tuple[object, ...] = (
        True,
        0,
        -1,
        1.0,
        "1",
        None,
        [],
        {},
        b"1",
        (1,),
    )
    for invalid_set_count in invalid_set_counts:
        left = dict(baseline)
        right = dict(baseline)
        left["set_count"] = invalid_set_count
        right["set_count"] = invalid_set_count
        review_pairs.append((left, right))

    for jan in (
        None,
        "4900000000016",
        "4900000000000",
        "123456789",
        "12345678901234",
        "INVALID",
        4900000000009,
    ):
        changed = dict(baseline)
        if jan is None:
            changed.pop("jan")
        else:
            changed["jan"] = jan
        review_pairs.append((baseline, changed))

    for left, right in review_pairs:
        assert generator.evaluate_od006_synthetic_pair(left, right) == "HUMAN_REVIEW"
        assert generator.evaluate_od006_gold_pair(left, right) == "HUMAN_REVIEW"


@pytest.mark.parametrize(
    "field",
    (
        "brand",
        "manufacturer_model",
        "size",
        "capacity",
        "external_dimensions",
        "color_or_variant",
    ),
)
@pytest.mark.parametrize("unsupported_value", (True, 1, 1.5, [], {}, b"x", ("x",)))
def test_od006_pair_rejects_equal_unsupported_text_identity_types(
    field: str, unsupported_value: object
) -> None:
    left = _synthetic_sku()
    right = _synthetic_sku()
    left[field] = unsupported_value
    right[field] = copy.deepcopy(unsupported_value)
    assert generator.evaluate_od006_synthetic_pair(left, right) == "HUMAN_REVIEW"
    assert generator.evaluate_od006_gold_pair(left, right) == "HUMAN_REVIEW"


@pytest.mark.parametrize("listing_count", (0, 1, 2, 3, 30))
def test_gold_unordered_pair_count_is_exact(listing_count: int) -> None:
    expected = listing_count * (listing_count - 1) // 2
    assert generator.gold_unordered_pair_count(listing_count) == expected
    if listing_count == 30:
        assert expected == 435


@pytest.mark.parametrize("listing_count", (True, -1, 1.0, "30"))
def test_gold_unordered_pair_count_rejects_coercion_and_invalid_values(
    listing_count: object,
) -> None:
    with pytest.raises(generator.BusinessInputsError):
        generator.gold_unordered_pair_count(cast(Any, listing_count))
