"""Source and projection contract tests for ST-1602."""

from __future__ import annotations

import json

from scripts import build_st1602_slo_alert_reference_plan as generator


def test_contract_projects_exact_canonical_catalog_inventory() -> None:
    contract = generator.load_contract()
    plan = generator.reference_plan(contract)

    assert tuple(plan) == generator.PLAN_KEYS
    projection = plan["catalog_projection"]
    assert len(projection["slos"]) == 14
    assert len(projection["alerts"]) == 20
    assert len(projection["runbooks"]) == 20
    assert [row["id"] for row in projection["slos"]] == [
        f"SLO-{index:03d}" for index in range(1, 15)
    ]
    assert [row["id"] for row in projection["alerts"]] == [
        f"ALT-{index:03d}" for index in range(1, 21)
    ]
    assert [row["id"] for row in projection["runbooks"]] == [
        f"RB-{index:03d}" for index in range(1, 21)
    ]


def test_plan_is_non_executable_and_unrouted() -> None:
    plan = generator.reference_plan(generator.load_contract())
    assert plan["document"]["executable"] is False
    assert plan["routing"]["mode"] == "LOCAL_LOG_ONLY"
    assert plan["routing"]["route_status"] == "NOT_CONFIGURED"
    assert plan["routing"]["notifications_enabled"] is False
    assert plan["routing"]["owner"] is None
    assert plan["routing"]["runbook_links"] == []
    assert plan["catalog_projection"]["inferred_links"] == []
    assert plan["verification_boundary"]["story_acceptance"] is False
    assert plan["verification_boundary"]["production_eligible"] is False


def test_projected_rows_preserve_exact_fields_statuses_and_order() -> None:
    projection = generator.reference_plan(generator.load_contract())[
        "catalog_projection"
    ]
    assert all(tuple(row) == generator.SLO_FIELDS for row in projection["slos"])
    assert all(
        row["status"] == "PROVISIONAL_TARGET"
        and row["implementation_status"] == "NOT_STARTED"
        and row["measurement_status"] == "NOT_EXECUTED"
        and type(row["target"]) is str
        and type(row["window"]) is str
        for row in projection["slos"]
    )
    assert all(tuple(row) == generator.ALERT_FIELDS for row in projection["alerts"])
    assert all(
        row["implementation_status"] == "NOT_STARTED"
        and row["test_status"] == "NOT_EXECUTED"
        and type(row["condition"]) is str
        and type(row["initial_action"]) is str
        for row in projection["alerts"]
    )
    assert all(
        tuple(row) == generator.RUNBOOK_FIELDS
        and row["document_status"] == "DESIGNED_INDEX_ONLY"
        and row["implementation_status"] == "NOT_STARTED"
        and row["drill_status"] == "NOT_EXECUTED"
        and type(row["minimum_steps"]) is list
        for row in projection["runbooks"]
    )


def test_projection_counts_do_not_become_execution_evidence() -> None:
    plan = generator.reference_plan(generator.load_contract())
    assert plan["catalog_projection"]["coverage"] == {
        "slos": {"projected": 14, "canonical": 14},
        "alerts": {"projected": 20, "canonical": 20},
        "runbooks": {"projected": 20, "canonical": 20},
    }
    verification = plan["verification_boundary"]
    for name in (
        "implemented_count",
        "measured_count",
        "tested_count",
        "drilled_count",
        "owner_route_count",
        "runbook_route_count",
    ):
        assert type(verification[name]) is int
        assert verification[name] == 0
    assert verification["formal_tst_027"] == "NOT_EXECUTED"
    assert verification["formal_tst_028"] == "NOT_EXECUTED"


def test_telemetry_dependency_is_available_but_not_connected() -> None:
    plan = generator.reference_plan(generator.load_contract())
    assert plan["dependency"] == generator.EXPECTED_DEPENDENCY
    telemetry = plan["catalog_projection"]["telemetry_binding"]
    assert telemetry["interface_available"] is True
    assert telemetry["connected"] is False
    assert telemetry["runtime_status"] == "NOT_EXECUTED"
    for name in (
        "metric",
        "log",
        "formula",
        "trigger",
        "window",
        "error_budget",
        "backend",
    ):
        assert telemetry[name] is None


def test_initial_actions_and_steps_are_inert_catalog_text() -> None:
    plan = generator.reference_plan(generator.load_contract())
    assert plan["execution_boundary"]["initial_actions"] == "INERT_TEXT_NOT_EXECUTED"
    assert plan["execution_boundary"]["runbook_steps"] == "INERT_TEXT_NOT_EXECUTED"
    assert all(
        value == 0 for value in plan["execution_boundary"]["action_counts"].values()
    )
    assert plan["execution_boundary"]["external_actions"] == []


def test_installed_json_has_exact_top_sections_and_no_false_claim_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert tuple(plan) == generator.PLAN_KEYS

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    forbidden = {
        "PASS",
        "READY",
        "VALIDATED",
        "IMPLEMENTED",
        "HEALTHY",
        "PRODUCTION_READY",
    }
    assert forbidden.isdisjoint(strings(plan))


def test_empty_routing_arrays_mean_no_configuration_not_zero_incidents() -> None:
    routing = generator.reference_plan(generator.load_contract())["routing"]
    assert routing["delivery_records"] == []
    assert routing["external_actions"] == []
    assert routing["empty_interpretation"] == (
        "NO_CONFIGURATION_OR_EVIDENCE_NOT_ZERO_INCIDENTS"
    )
