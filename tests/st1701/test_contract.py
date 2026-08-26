"""ST-1701 semantic contract checks."""

from __future__ import annotations

from scripts import build_st1701_business_inputs as generator


def test_unresolved_registry_uses_owner_graph(
    contract_document: dict[str, object],
) -> None:
    predecessor = contract_document["predecessor_binding"]
    assert isinstance(predecessor, dict)
    assert predecessor["owner_id"] == "build_st0006_decision_gates"
    assert predecessor["owner_version"] == "2"
    assert predecessor["binding"] == "SEMANTIC_OWNER_GRAPH"
    generator.validate_contract(contract_document)


def test_canonical_inputs_remain_checksum_protected(
    contract_document: dict[str, object],
) -> None:
    sources = contract_document["sources"]
    assert isinstance(sources, list)
    assert len(sources) == 6
    assert all(row["uri"].startswith("repo://docs/canonical/") for row in sources)
    assert all(len(row["sha256"]) == 64 for row in sources)


def test_decision_model_has_no_development_approval_hashes(
    decision_package: dict[str, object],
) -> None:
    generator.validate_decision_package(decision_package)
    serialized = str(decision_package).lower()
    assert "handoff_sha256" not in serialized
    assert "approval_sha256" not in serialized
    assert "base_commit" not in serialized
    assert decision_package["status_boundary"]["gate_state"] == "BLOCKED"  # type: ignore[index]
