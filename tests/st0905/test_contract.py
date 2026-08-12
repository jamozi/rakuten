"""Contract and authority-boundary tests for ST-0905."""

from typing import Any, cast

from scripts import build_st0905_publication_commands_reference_plan as generator


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def _mapping(value: object) -> dict[str, Any]:
    assert type(value) is dict
    return cast(dict[str, Any], value)


def _rows(value: object) -> list[dict[str, Any]]:
    assert type(value) is list
    assert all(type(row) is dict for row in value)
    return cast(list[dict[str, Any]], value)


def test_reference_plan_is_non_executable_and_non_authoritative() -> None:
    plan = _plan()
    document = _mapping(plan["document"])
    assert document["executable"] is False
    assert document["interface_only"] is True
    assert document["command_handlers_authorized"] is False
    assert document["job_producers_authorized"] is False
    assert document["event_emission_authorized"] is False
    assert document["database_mutation_authorized"] is False
    assert document["external_actions_authorized"] is False
    assert document["publication_authority"] is False
    assert document["publication_permitted"] is False
    assert plan["pro_assistance"] == {"pro_required_for_reference_slice": False}


def test_exact_dependencies_and_command_event_surfaces_are_preserved() -> None:
    plan = _plan()
    assert [row["story_id"] for row in _rows(plan["dependencies"])] == [
        "ST-0903",
        "ST-0904",
        "ST-0402",
    ]
    projection = _mapping(plan["contract_projection"])
    commands = _mapping(projection["command_surfaces"])
    assert [_mapping(row)["operation_id"] for row in commands.values()] == [
        "PUBADM-009",
        "PUBADM-012",
        "PUBADM-013",
    ]
    jobs = _mapping(projection["job_surfaces"])
    assert [_mapping(row)["job_type"] for row in jobs.values()] == [
        "publishing.publish_snapshot.v1",
        "publishing.unpublish.v1",
        "publishing.rollback.v1",
    ]
    events = _mapping(projection["event_surfaces"])
    assert [_mapping(row)["event_type"] for row in events.values()] == [
        "jp.raos.publishing.article_published.v1",
        "jp.raos.publishing.article_unpublished.v1",
        "jp.raos.publishing.article_rolled_back.v1",
    ]


def test_security_gap_conflicts_and_empty_records_fail_closed() -> None:
    plan = _plan()
    projection = _mapping(plan["contract_projection"])
    security = _mapping(projection["security_boundary"])
    assert _mapping(security["unpublish"])["role_matrix_action_present"] is False
    assert _mapping(security["unpublish"])["safe_default"] == "DENY_UNPUBLISH"
    conflicts = _rows(projection["surface_conflicts"])
    assert len(conflicts) == 8
    assert all(row["status"] != "RESOLVED" for row in conflicts)
    records = _mapping(plan["record_boundary"])
    assert tuple(records) == (
        "commands",
        "jobs",
        "events",
        "audits",
        "database_mutations",
        "external_actions",
        "publications",
        "rollbacks",
    )
    assert all(
        _mapping(row)["status"] == "NOT_EVALUATED" and _mapping(row)["records"] == []
        for row in records.values()
    )


def test_all_execution_verification_and_implementation_claims_are_closed() -> None:
    plan = _plan()
    gates = _rows(plan["hard_gates"])
    assert len(gates) == 12
    assert all(
        str(row["safe_default"]).startswith(("NO_", "DENY_", "KEEP_", "REFERENCE_"))
        for row in gates
    )
    execution = _mapping(plan["execution_boundary"])
    assert execution["command_handlers"] == "NOT_IMPLEMENTED"
    assert execution["external_side_effects"] == []
    verification = _mapping(plan["verification_boundary"])
    assert verification["formal_tst_012"] == "NOT_EXECUTED"
    assert verification["formal_tst_013"] == "NOT_EXECUTED"
    assert verification["formal_tst_021"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["effective_canonical_status"] == "UNCHANGED"
    boundary = _mapping(plan["implementation_boundary"])
    for key in (
        "existing_file_changes",
        "runtime_modules",
        "domain_modules",
        "application_modules",
        "ports",
        "adapters",
        "database_changes",
        "migration_changes",
        "api_changes",
        "job_changes",
        "event_changes",
        "canonical_changes",
        "status_changes",
        "generated_binding_changes",
    ):
        assert boundary[key] == []
    assert boundary["executable_work_requires"] == "OWNER_APPROVED_DESIGN_HANDOFF_V1"
