from __future__ import annotations

from scripts import build_st1607_gate_evidence_pack as builder


def test_every_gate_remains_blocked_without_external_evidence() -> None:
    pack = builder.gate_evidence_pack(builder.load_contract())
    gates = pack["gate_report"]["gates"]
    assert [gate["gate_id"] for gate in gates] == list(builder.GATE_IDS)
    assert all(gate["status"] == "BLOCKED" for gate in gates)
    assert all(gate["blocker_codes"] == list(builder.GLOBAL_BLOCKERS) for gate in gates)
    assert all(gate["qualifying_evidence_references"] == [] for gate in gates)


def test_external_actions_remain_unexecuted() -> None:
    pack = builder.gate_evidence_pack(builder.load_contract())
    assert pack["snapshot_boundary"]["repository_tracking"] == "GIT_AND_CI"
    assert pack["evidence_boundary"]["formal_tst_032"] == "NOT_EXECUTED"
    assert pack["evidence_boundary"]["staging"] == "NOT_EXECUTED"
    assert pack["evidence_boundary"]["release"] == "NOT_AUTHORIZED"
    assert pack["evidence_boundary"]["production"] == "NOT_AUTHORIZED"
