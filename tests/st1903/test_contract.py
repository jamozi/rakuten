"""Contract tests for the inert ST-1903 policy-revision candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import build_st1903_autonomous_publication_policy as generator


def test_pending_authority_and_exact_approval_target(
    contract: dict[str, Any], handoff: dict[str, Any]
) -> None:
    """The candidate must remain inert until a separate exact-SHA approval."""

    approval = contract["approval_binding"]
    handoff_bytes = (generator.REPO_ROOT / generator.HANDOFF_PATH).read_bytes()
    contract_bytes = (generator.REPO_ROOT / generator.CONTRACT_PATH).read_bytes()
    source_binding = handoff["policy_source_binding"]

    assert contract["candidate_status"] == "PENDING_OWNER_SHA256_APPROVAL"
    assert contract["authority"] == "UNAPPROVED_POLICY_REVISION_CANDIDATE"
    assert contract["activation"] == "DISABLED"
    assert contract["canonical_reconciliation"] == "NOT_EXECUTED"
    assert contract["production_readiness"] == "NOT_READY"
    assert approval["approval_record"] is None
    assert len(handoff_bytes) == generator.EXPECTED_HANDOFF_BYTES
    assert (
        hashlib.sha256(handoff_bytes).hexdigest() == generator.EXPECTED_HANDOFF_SHA256
    )
    assert approval["path"] == generator.HANDOFF_PATH.as_posix()
    assert approval["contract_binding_direction"] == (
        "ROOT_HANDOFF_BINDS_EXACT_CONTRACT_BYTES_AND_ORDERED_SEMANTICS"
    )
    assert source_binding["bytes"] == len(contract_bytes)
    assert source_binding["sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    assert (
        source_binding["ordered_semantic_sha256"]
        == generator.EXPECTED_CONTRACT_SEMANTIC_SHA256
    )
    assert handoff["approval_status"] == "PENDING_OWNER_SHA256_APPROVAL"
    assert handoff["open_decisions"] == []
    assert handoff["actions"] == handoff["effects"] == handoff["evidence"] == []


def test_publication_policy_is_fail_closed_and_bounded(
    contract: dict[str, Any],
) -> None:
    """The proposed future policy keeps rate, risk, and review bounds exact."""

    publication = contract["publication_policy"]
    rate = publication["rate_limit"]
    risk = publication["risk_gate"]

    assert rate == {
        "timezone": "Asia/Tokyo",
        "maximum_new_articles_per_calendar_day": 1,
        "catch_up": "FORBIDDEN",
        "unused_capacity_rollover": "FORBIDDEN",
        "duplicate_prevention_required": True,
    }
    assert risk["phase"] == "BEFORE_DRAFTING"
    assert risk["denied_categories"] == [
        "MEDICAL",
        "FINANCIAL",
        "LEGAL",
        "SAFETY",
        "MINORS",
    ]
    assert risk["denied_result"] == "DENY_WITHOUT_DRAFT_OR_PUBLICATION"
    assert risk["unknown_or_ambiguous_result"] == "QUEUE_FOR_OWNER_REVIEW"
    assert (
        risk["ordinary_eligible_result_after_activation"]
        == "CONTINUE_WITHOUT_PER_ARTICLE_OWNER_APPROVAL"
    )
    assert risk["exceptional_queue_requires_owner_review"] is True
    assert publication["pro_review"]["required_for_each_candidate_article"] is True
    assert publication["pro_review"]["outage_result"] == "QUEUE_WITHOUT_PUBLICATION"
    assert publication["pro_review"]["bypass"] == "FORBIDDEN"
    assert publication["pro_review"]["approval_authority"] == "NONE"


def test_commercial_affiliate_and_cms_rules_cannot_override_safety(
    contract: dict[str, Any],
) -> None:
    """Commercial scoring follows eligibility and external writes fail closed."""

    publication = contract["publication_policy"]
    eligibility = publication["eligibility"]
    commercial = publication["commercial_component"]
    affiliate = publication["affiliate"]
    wordpress = publication["wordpress"]

    assert eligibility["ordered_components"] == [
        "EVIDENCE",
        "USER_FIT",
        "QUALITY",
        "SAFETY",
        "COMMERCIAL_COMPONENT",
    ]
    assert commercial["eligible_products_only"] is True
    assert commercial["maximum_weight_basis_points"] == 1000
    assert commercial["may_override_prior_eligibility_components"] is False
    assert (
        commercial["expected_contribution_profit"]["attribution_basis"] == "ESTIMATED"
    )
    assert (
        commercial["expected_contribution_profit"]["confirmation_status"]
        == "NON_CONFIRMED"
    )
    assert commercial["activation"] == "DISABLED"
    assert affiliate["source_field"] == "affiliateUrl"
    assert affiliate["official_api_value_required"] is True
    assert affiliate["direct_destination_required"] is True
    assert affiliate["hand_built_url"] == "FORBIDDEN"
    assert affiliate["raos_redirect"] == "FORBIDDEN"
    assert affiliate["invalid_or_stale_cta"] == "DISABLED"
    assert wordpress["idempotency_binding_required"] is True
    assert wordpress["pre_write_duplicate_check_required"] is True
    assert wordpress["ambiguous_write_result"] == "STOP_AND_QUEUE_RECONCILIATION"
    assert wordpress["blind_retry_after_ambiguous_result"] == "FORBIDDEN"


def test_optimizer_privacy_and_editorial_containment(contract: dict[str, Any]) -> None:
    """Optimization cannot mutate policy authority or invent human experience."""

    assert all(value is False for value in contract["optimizer_containment"].values())
    assert contract["analytics_privacy_policy"] == {
        "analytics_shape": "AGGREGATE_ONLY",
        "nonessential_tracking_without_consent": "DENIED",
        "raw_ip": "FORBIDDEN",
        "full_user_agent": "FORBIDDEN",
        "fingerprinting": "FORBIDDEN",
        "invented_identity": "FORBIDDEN",
        "personal_data_collection_in_scope": False,
    }
    editorial = contract["editorial_style_policy"]
    assert editorial["tone"] == "QUIET_EDITORIAL"
    assert editorial["natural_readability_required"] is True
    assert editorial["evidence_grounding_required"] is True
    assert editorial["fabricated_first_person_experience"] == "FORBIDDEN"
    assert editorial["detector_evasion"] == "FORBIDDEN"


def test_open_decisions_and_projection_remain_unresolved(
    contract: dict[str, Any],
) -> None:
    """The proposal neither resolves canonical decisions nor attests runtime work."""

    decisions = contract["inherited_unresolved_canonical_open_decisions"]
    assert [row["id"] for row in decisions] == [
        f"OD-{number:03d}" for number in range(1, 16)
    ]
    assert [row["id"] for row in decisions if row["blocking"] is False] == ["OD-004"]
    assert contract["blocking_open_decision_ids"] == [
        row["id"] for row in decisions if row["blocking"] is True
    ]
    assert all(row["candidate_resolution"] == "UNCHANGED" for row in decisions)
    assert all(value is False for value in contract["projection_boundary"].values())
    assert contract["actions"] == contract["effects"] == contract["evidence"] == []


def test_contract_is_plain_round_trip_json(contract: dict[str, Any]) -> None:
    """The generated projection is detached JSON data, not an executable object."""

    encoded = json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
    assert json.loads(encoded) == contract
    assert Path(generator.OUTPUT_PATH).suffix == ".json"
