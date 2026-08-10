"""Source and projection contract tests for ST-1604."""

from __future__ import annotations

import json
from typing import Any

from scripts import build_st1604_performance_load_reference_plan as generator


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_contract_projects_exact_top_sections_and_slo_inventory() -> None:
    plan = _plan()
    assert tuple(plan) == generator.PLAN_KEYS
    context = plan["slo_context"]
    assert context["coverage"] == {"projected": 14, "canonical": 14}
    assert [row["id"] for row in context["slos"]] == [
        f"SLO-{index:03d}" for index in range(1, 15)
    ]


def test_tst_027_is_exact_but_no_tool_runner_or_environment_is_selected() -> None:
    suite = _plan()["test_suite"]
    for key, expected in generator.EXPECTED_TEST_SUITE.items():
        assert suite[key] == expected
    assert suite["candidate_tools"] == ["k6相当", "browser RUM lab"]
    assert suite["environments"] == ["staging"]
    for key in (
        "selected_tool",
        "runner",
        "version",
        "executor",
        "selected_environment",
    ):
        assert suite[key] is None
    assert suite["release_evidence_status"] == "NOT_EXECUTED"
    assert suite["release_evidence"] is None


def test_target_surfaces_are_ordered_and_entirely_unconfigured() -> None:
    surfaces = _plan()["target_surfaces"]
    assert [row["surface"] for row in surfaces] == list(generator.SURFACES)
    for row in surfaces:
        assert row["configuration_status"] == "NOT_CONFIGURED"
        for key in ("endpoint", "protocol", "authentication", "deployment"):
            assert row[key] is None
        for key in ("scenarios", "scenario_mix", "fixtures", "artifacts"):
            assert row[key] == []


def test_slo_rows_preserve_exact_fields_and_provisional_statuses() -> None:
    rows = _plan()["slo_context"]["slos"]
    assert all(tuple(row) == generator.SLO_FIELDS for row in rows)
    assert all(
        row["status"] == "PROVISIONAL_TARGET"
        and row["implementation_status"] == "NOT_STARTED"
        and row["measurement_status"] == "NOT_EXECUTED"
        and type(row["target"]) is str
        and type(row["window"]) is str
        for row in rows
    )


def test_slo_targets_are_context_only_and_no_selection_is_inferred() -> None:
    context = _plan()["slo_context"]
    assert context["selection_status"] == "NOT_DEFINED_IN_CANONICAL"
    assert context["selected_slo_ids"] == []
    assert context["evaluations"] == []
    assert context["targets_met"] == []
    assert context["capacities"] == []
    requirements = context["measurement_requirements"]
    assert requirements["dimensions"] == [
        "P95",
        "P99",
        "ERRORS",
        "QUEUE_AGE",
        "DB_CONNECTIONS",
        "COST",
    ]
    assert requirements["status"] == "REQUIRED_NOT_MEASURED"
    assert requirements["values"] == []
    assert requirements["evidence"] == []


def test_workload_resource_and_cost_inputs_remain_unset_not_zero() -> None:
    plan = _plan()
    workload = plan["workload_definition"]
    for key in (
        "concurrency",
        "duration",
        "ramp",
        "arrival_rate",
        "request_count",
        "worker_job_count",
        "dataset",
        "random_seed",
    ):
        assert workload[key] is None
    assert workload["headers"] == []
    assert workload["payloads"] == []
    resources = plan["resource_and_cost_boundaries"]
    for key in (
        "cpu_cap",
        "memory_cap",
        "db_connection_cap",
        "queue_depth_cap",
        "cost_cap",
        "currency",
    ):
        assert resources[key] is None
    assert resources["execution_permitted"] is False
    assert resources["unset_cap_interpretation"] == ("EXECUTION_NOT_PERMITTED_NOT_ZERO")


def test_empty_load_report_is_no_evidence_not_zero_results() -> None:
    report = _plan()["load_report"]
    assert report["status"] == "NOT_EXECUTED"
    assert report["started_at"] is None
    assert report["finished_at"] is None
    assert report["summary"] is None
    assert report["capacity_claim"] is None
    assert report["slo_target_claim"] is None
    assert report["results"] == []
    assert report["metrics"] == []
    assert report["errors"] == []
    assert report["artifacts"] == []
    assert report["empty_interpretation"] == ("NO_EVIDENCE_COLLECTED_NOT_ZERO_RESULTS")


def test_activation_is_disabled_with_exact_integer_zero_actions() -> None:
    activation = _plan()["activation"]
    assert activation["enabled"] is False
    assert activation["status"] == "DISABLED"
    assert tuple(activation["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in activation["action_counts"].values()
    )
    assert all(
        activation[key] == "FORBIDDEN"
        for key in (
            "load_execution",
            "browser_execution",
            "network_access",
            "credential_access",
            "provider_access",
            "external_actions",
            "staging_action",
            "release_action",
            "production_action",
        )
    )


def test_predecessors_are_interface_only_and_not_connected() -> None:
    assert _plan()["predecessor_bindings"] == generator._expected_predecessors()


def test_installed_plan_contains_no_false_readiness_claims() -> None:
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
