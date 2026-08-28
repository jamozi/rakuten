"""Bidirectional P0-P3 decision/requirement/backlog/test traceability."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def effective() -> dict[str, object]:
    value = yaml.safe_load(
        (
            ROOT / "changes/raos-v2/generated/decision-traceability.effective.v1.yaml"
        ).read_text(encoding="utf-8")
    )
    assert isinstance(value, dict)
    return value


def test_source_counts_are_preserved_and_effective_scope_is_p0_to_p3() -> None:
    value = effective()
    assert value["source_counts"] == {
        "decisions": 34,
        "requirements": 36,
        "backlog": 49,
        "tests": 51,
    }
    assert value["scope"] == ["P0", "P1", "P2", "P3"]
    assert len(value["backlog"]) == 40
    assert len(value["tests"]) == 47
    assert all(value["invariants"].values())


def test_effective_dependency_corrections_are_closed_and_acyclic() -> None:
    value = effective()
    rows = {row["id"]: row for row in value["backlog"]}
    assert rows["B-V2-009"]["depends_on"] == [
        f"B-V2-{number:03d}" for number in range(1, 9)
    ]
    assert "B-V2-030" in rows["B-V2-031"]["depends_on"]
    assert {"B-V2-027", "B-V2-029", "B-V2-030"} <= set(rows["B-V2-033"]["depends_on"])
    assert rows["B-V2-034"]["depends_on"] == [
        f"B-V2-{number:03d}" for number in range(19, 34)
    ]
    assert rows["B-V2-040"]["depends_on"] == [
        "B-V2-036",
        "B-V2-037",
        "B-V2-038",
        "B-V2-039",
    ]
    assert rows["B-V2-040"]["implementation_status"] == "BLOCKED_EXTERNAL"
    assert rows["B-V2-040"]["external_action_status"] == "NOT_EXECUTED"
    pending = {identifier: set(row["depends_on"]) for identifier, row in rows.items()}
    while pending:
        ready = {
            identifier
            for identifier, dependencies in pending.items()
            if not (dependencies & pending.keys())
        }
        assert ready
        for identifier in ready:
            pending.pop(identifier)


def test_every_effective_relationship_has_a_reverse_link() -> None:
    value = effective()
    decisions = {row["id"]: row for row in value["decisions"]}
    requirements = {row["id"]: row for row in value["requirements"]}
    backlog = {row["id"]: row for row in value["backlog"]}
    tests = {row["id"]: row for row in value["tests"]}
    for decision_id, row in decisions.items():
        for requirement_id in row["requirement_ids"]:
            assert decision_id in requirements[requirement_id]["decision_ids"]
    for requirement_id, row in requirements.items():
        for backlog_id in row["backlog_ids"]:
            assert requirement_id in backlog[backlog_id]["requirement_ids"]
        for test_id in row["test_ids"]:
            assert requirement_id in tests[test_id]["requirement_ids"]
    for backlog_id, row in backlog.items():
        for test_id in row["test_ids"]:
            assert backlog_id in tests[test_id]["backlog_ids"]


def test_test_phase_correction_matches_user_plan() -> None:
    rows = {row["id"]: row for row in effective()["tests"]}
    assert rows["T-V2-006"]["effective_phases"] == ["P0"]
    assert rows["T-V2-007"]["effective_phases"] == ["P1"]
    assert rows["T-V2-019"]["effective_phases"] == ["P1"]
    assert rows["T-V2-020"]["effective_phases"] == ["P2"]
    assert rows["T-V2-040"]["effective_phases"] == ["P0", "P3"]
    assert rows["T-V2-051"]["effective_phases"] == ["P0", "P1", "P2", "P3"]
    assert rows["T-V2-040"]["phase3_external_execution_status"] == "NOT_EXECUTED"
