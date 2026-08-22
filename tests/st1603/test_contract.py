"""Positive non-attesting contract semantics for ST-1603."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from scripts import build_st1603_security_verification_pack as generator


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_is_closed_interface_only_and_non_attesting(
    contract_document: dict[str, Any],
) -> None:
    assert tuple(contract_document) == generator.TOP_LEVEL_KEYS
    assert contract_document["document"] == {
        "id": "RAOS-SECURITY-VERIFICATION-PACK-001",
        "version": "1.0.0",
        "story_id": "ST-1603",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert contract_document["approvals"] is None
    assert contract_document["decision"] == "NOT_READY"
    assert contract_document["asvs_mapping"] == generator.EXPECTED_ASVS_MAPPING
    assert (
        contract_document["verification_suites"]
        == generator.EXPECTED_VERIFICATION_SUITES
    )


def test_all_canonical_controls_are_projected_without_verification(
    reference_document: dict[str, Any],
) -> None:
    projection = _mapping(reference_document["catalog_projection"])
    controls = cast(list[dict[str, object]], projection["controls"])
    assert len(controls) == 83
    assert all(tuple(row) == generator.CONTROL_FIELDS for row in controls)
    assert len({row["id"] for row in controls}) == 83
    assert Counter(str(row["category"]) for row in controls) == Counter(
        generator.EXPECTED_CATEGORY_COUNTS
    )
    assert Counter(str(row["priority"]) for row in controls) == Counter(
        generator.EXPECTED_PRIORITY_COUNTS
    )
    assert len({str(row["verification"]) for row in controls}) == 75
    assert all(row["gate"] == "GATE-0" for row in controls)
    assert all(row["implementation_status"] == "NOT_STARTED" for row in controls)
    assert all(row["verification_status"] == "NOT_EXECUTED" for row in controls)
    assert projection["projection_coverage"] == "83/83"
    assert projection["verification_coverage"] == "0/83"
    assert projection["verified_control_count"] == 0


def test_empty_collections_never_claim_zero_findings_or_completed_work(
    reference_document: dict[str, Any],
) -> None:
    assert reference_document["findings"] == generator.EXPECTED_FINDINGS
    assert reference_document["remediations"] == generator.EXPECTED_REMEDIATIONS
    assert reference_document["exceptions"] == generator.EXPECTED_EXCEPTIONS
    assert reference_document["evidence"] == generator.EXPECTED_EVIDENCE
    assert reference_document["approvals"] is None
    assert reference_document["decision"] == "NOT_READY"
    assert (
        "EMPTY_FINDINGS_IS_NOT_ZERO_FINDINGS"
        in reference_document["prohibited_interpretations"]
    )


def test_predecessors_remain_material_free_disabled_and_zero_action(
    contract_document: dict[str, Any],
) -> None:
    bindings = _mapping(contract_document["predecessor_bindings"])
    workload = _mapping(bindings["workload_credential_seam"])
    assert workload["material_free"] is True
    assert workload["failure_mode"] == "FAIL_CLOSED"
    assert workload["credential_material"] == "ABSENT"
    assert workload["provider_selection"] is None
    assert workload["live_provider_calls"] == "FORBIDDEN"
    staging = _mapping(bindings["staging_deployment"])
    assert staging["executable"] is False
    assert staging["activation"] == "DISABLED"
    assert staging["credential_material"] == "ABSENT"
    assert staging["required_classification"] == (
        "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
        "REFERENCE_PLAN"
    )
    assert staging["provider_neutral_admission"] == (
        generator.EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION
    )
    assert staging["action_counts"] == generator.EXPECTED_STAGING_ACTION_COUNTS
    assert all(
        type(value) is int and value == 0 for value in staging["action_counts"].values()
    )


def test_execution_and_evidence_boundaries_are_inert(
    reference_document: dict[str, Any],
) -> None:
    assert reference_document["classification"] == (
        "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN"
    )
    assert reference_document["executable"] is False
    assert (
        reference_document["execution_boundary"]
        == generator.EXPECTED_EXECUTION_BOUNDARY
    )
    assert (
        reference_document["evidence_boundary"] == generator.EXPECTED_EVIDENCE_BOUNDARY
    )
    counts = reference_document["execution_boundary"]["action_counts"]
    assert all(type(value) is int and value == 0 for value in counts.values())
