"""Versioned ST-1907 contract and fixture boundary tests."""

from __future__ import annotations

import json

import yaml

from raos.domain.portfolio.content_optimizer import (
    DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE,
    PortfolioOptimizerScope,
    RECOMMENDATION_INPUTS_EXCLUDED,
)

from .support import CONTRACT_PATH, FIXTURE_PATH


def test_contract_preserves_canonical_and_operational_boundaries() -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_bytes())
    assert contract["document"] == {
        "schema_version": "1.0.0",
        "story_id": "ST-1907",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_DISABLED_RECORDED_SYNTHETIC_HUMAN_PROPOSAL_OPTIMIZER_V1"
        ),
        "status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "implementation_mode": "STRICT_STORY",
        "mvp": False,
        "canonical_implementation_status": "DEFERRED_POST_MVP",
        "canonical_status_changed": False,
        "formal_validation": "NOT_EXECUTED",
        "authority": "NONE",
        "production_eligible": False,
    }
    assert DEFAULT_PORTFOLIO_OPTIMIZER_SCOPE is PortfolioOptimizerScope.DISABLED
    scope = contract["feature_scope"]
    assert scope["default"] == "DISABLED"
    assert scope["closed_states"] == [
        "DISABLED",
        "RECORDED_SYNTHETIC_PROPOSAL_EVALUATION_ONLY",
    ]
    assert scope["live_enabled_state_exists"] is False
    assert scope["activation_interface_exists"] is False
    assert scope["executable_environments"] == ["ENV-DEV", "ENV-CI"]

    proposal = contract["proposal_contract"]
    assert proposal["actions"] == ["STRENGTHEN", "CONSOLIDATE", "WITHDRAW"]
    assert proposal["output_kind"] == "HUMAN_REVIEW_METADATA_ONLY"
    assert proposal["actionable"] is False
    assert proposal["human_review_required"] is True
    assert proposal["automatic_apply"] is False
    assert proposal["status_APPLY_exists"] is False
    assert proposal["proposal_order_is_recommendation_order"] is False
    assert proposal["thresholds_selected_by_this_story"] is False
    assert proposal["mutations_applied"] == []

    boundary = contract["mutation_boundary"]
    assert boundary["recommendation_inputs_excluded"] == list(
        RECOMMENDATION_INPUTS_EXCLUDED
    )
    assert boundary["finance_values_represented"] is False
    assert all(
        boundary[field] is False
        for field in (
            "activation",
            "approval",
            "proposal_apply",
            "status_apply",
            "provider_call",
            "network",
            "credential_access",
            "persistence",
            "editorial_mutation",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
            "public_projection",
            "publication",
            "staging",
            "release",
            "production",
        )
    )


def test_current_fixture_is_exact_blocked_no_decision_with_no_signals() -> None:
    fixture = json.loads(FIXTURE_PATH.read_bytes())
    dependency = fixture["document"]["dependency"]
    assert dependency == {
        "acceptance_criteria_satisfied": False,
        "actual_observation_count": 0,
        "human_decision_present": False,
        "local_integration_complete": False,
        "pack_sha256": (
            "bf9899509a376ab6a9abd1613cfe5f12ab207629a6c94b2ba3bf2106a992098e"
        ),
        "readiness": "BLOCKED_NO_DECISION",
        "source_authorized": False,
        "source_outcome": "NO_DECISION",
        "source_overall": "BLOCKED",
        "story_id": "ST-1805",
    }
    assert fixture["signals"] == []
