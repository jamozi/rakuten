"""Approved semantic contract tests for the ST-1703 low-cost pilot."""

from __future__ import annotations

from typing import Any

from scripts import build_st1703_low_cost_publication_pilot as generator


def test_contract_validates_and_preserves_exact_authority(
    contract_document: dict[str, Any],
) -> None:
    generator.validate_contract(contract_document)
    proposal = contract_document["authority"]["approved_proposal"]
    response = contract_document["authority"]["owner_response"]
    assert proposal["utf8_bytes"] == 342
    assert proposal["sha256"] == generator.PROPOSAL_SHA256
    assert response["utf8_bytes"] == 6
    assert response["sha256"] == generator.OWNER_RESPONSE_SHA256


def test_platform_spend_and_codex_boundaries_are_exact(
    contract_document: dict[str, Any],
) -> None:
    platform = contract_document["pilot"]["public_platforms"]
    assert platform["candidate_count"] == 1
    assert [row["id"] for row in platform["candidates"]] == ["WORDPRESSCOM_PERSONAL"]
    assert platform["dual_run"] == "FORBIDDEN"
    assert platform["cutover"] == "NOT_AUTHORIZED"
    assert contract_document["pilot"]["deferred_disabled_components"] == [
        "OPENAI_API",
        "AWS",
        "CLOUDFLARE_PAGES",
        "CUSTOM_ADMIN",
        "CUSTOM_API",
        "CUSTOM_WORKER",
    ]
    spend = contract_document["spend_boundary"]
    assert spend["exact_incremental_external_spend_cap"] == 2000
    assert spend["canonical_od_009"]["status"] == "UNRESOLVED"
    assert spend["historical_wave1_business_cap"]["amount"] == 30000
    assert spend["historical_wave1_business_cap"]["changed_by_this_slice"] is False
    roles = contract_document["pilot"]["drafting_and_quality"]
    assert roles["mode"] == "INTERACTIVE_HUMAN_CONTROLLED_ONLY"
    assert "PUBLISHER" in roles["forbidden_codex_roles"]
    assert "APPROVER" in roles["forbidden_codex_roles"]


def test_quality_and_inherited_evidence_are_requirements_only(
    contract_document: dict[str, Any],
) -> None:
    quality = contract_document["quality_and_ux_requirements"]
    assert quality["execution_status"] == "NOT_EXECUTED"
    assert quality["verification_status"] == "NOT_VERIFIED"
    assert quality["core_web_vitals"] == {
        "classification": "CANONICAL_TARGETS_NOT_MEASURED",
        "percentile": 75,
        "lcp_seconds_max": 2.5,
        "inp_milliseconds_max": 200,
        "cls_max": 0.1,
    }
    assert [
        row["id"] for row in contract_document["inherited_blockers"]["open_decisions"]
    ] == [
        "OD-002",
        "OD-005",
        "OD-007",
        "OD-008",
        "OD-009",
        "OD-012",
        "OD-013",
        "OD-015",
    ]
    assert contract_document["inherited_blockers"]["dependencies_promoted"] is False
    assert contract_document["inherited_blockers"]["story_acceptance_achieved"] is False
    assert set(contract_document["evidence_boundary"]["formal_suites"].values()) == {
        "NOT_EXECUTED"
    }
