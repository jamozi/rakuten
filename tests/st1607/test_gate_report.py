from __future__ import annotations

from scripts import build_st1607_gate_evidence_pack as builder


def test_every_gate_is_blocked_by_the_same_global_inventory(
    contract: dict[str, object],
) -> None:
    report = builder.gate_evidence_pack(contract)
    gate_report = report["gate_report"]
    assert isinstance(gate_report, dict)
    gates = gate_report["gates"]
    assert isinstance(gates, list)
    assert [gate["gate_id"] for gate in gates] == list(builder.GATE_IDS)
    assert all(gate["status"] == "BLOCKED" for gate in gates)
    assert all(gate["blocker_scope"] == "GLOBAL_ONLY" for gate in gates)
    assert all(gate["blocker_codes"] == list(builder.GLOBAL_BLOCKERS) for gate in gates)
    assert all(gate["qualifying_evidence_references"] == [] for gate in gates)
    assert all(gate["approval_status"] == "NOT_REQUESTED" for gate in gates)


def test_no_suite_to_gate_mapping_is_invented(
    contract: dict[str, object],
) -> None:
    pack = builder.gate_evidence_pack(contract)
    gate_report = pack["gate_report"]
    assert isinstance(gate_report, dict)
    mapping = gate_report["mapping_policy"]
    assert mapping == {
        "suite_to_gate_mapping": "NOT_DEFINED_BY_CANONICAL",
        "inferred_suite_to_gate_mapping": "FORBIDDEN",
        "blocker_application": "GLOBAL_BLOCKERS_APPLY_TO_EVERY_GATE",
    }
    serialized = builder._json_bytes(pack).decode()  # noqa: SLF001
    assert '"suite_id": "TST-032"' in serialized
    assert "GATE-0:TST" not in serialized
    assert "TST-032:GATE" not in serialized


def test_open_decisions_are_bound_as_global_blockers(
    contract: dict[str, object],
) -> None:
    pack = builder.gate_evidence_pack(contract)
    decision = pack["decision_input"]
    assert isinstance(decision, dict)
    assert decision["overall_open_decision_check"] == "BLOCKED"
    assert decision["unresolved_blocking_count"] == 14
    assert decision["active_blocker_ids"] == list(builder.ACTIVE_BLOCKER_IDS)
    assert decision["blocker_targets"] == list(builder.DECISION_TARGETS)
    assert decision["decision_clearance"] == "NOT_AVAILABLE"


def test_missing_and_ineligible_evidence_has_no_qualifying_reference(
    contract: dict[str, object],
) -> None:
    pack = builder.gate_evidence_pack(contract)
    rows = pack["required_evidence"]
    assert isinstance(rows, list)
    assert {row["status"] for row in rows} == {
        "MISSING",
        "INELIGIBLE_NON_ATTESTING_REFERENCE_PLAN",
        "INELIGIBLE_LOCAL_SYNTHETIC_NON_ATTESTING",
        "BLOCKED",
        "NOT_EXECUTED",
    }
    assert all(row["qualifying_evidence_references"] == [] for row in rows)
    evidence = pack["evidence_boundary"]
    assert isinstance(evidence, dict)
    assert evidence["formal_tst_032"] == "NOT_EXECUTED"
    assert evidence["validated_claim"] is False
    assert evidence["release_eligible"] is False
    assert evidence["production_ready"] is False
