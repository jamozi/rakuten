"""Contract and authority-boundary tests for ST-0904."""

from typing import Any, cast

from scripts import build_st0904_public_projection_reference_plan as generator


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
    document = plan["document"]
    assert document == {
        "id": "RAOS-ST0904-PUBLIC-PROJECTION-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-0904",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLIC_PROJECTION_REFERENCE_PLAN",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "interface_only": True,
        "decision": "NOT_READY",
        "readiness": "NOT_READY",
        "story_acceptance": False,
        "projector_authorized": False,
        "runtime_projector_authorized": False,
        "approval_authority": False,
        "publication_permitted": False,
        "production_eligible": False,
    }
    assert plan["pro_assistance"] == {
        "status": "PRO_UNAVAILABLE",
        "authority": "NONE",
        "proposal_captured": False,
        "content_used": False,
    }


def test_exact_story_dependencies_and_public_surfaces_are_preserved() -> None:
    plan = _plan()
    projection = _mapping(plan["contract_projection"])
    story = _mapping(projection["story"])
    assert story["depends_on"] == ["ST-0903", "ST-0306"]
    assert story["test_suites"] == ["TST-011", "TST-021"]
    assert [row["story_id"] for row in _rows(plan["dependencies"])] == [
        "ST-0903",
        "ST-0306",
    ]
    readmodel = _mapping(projection["public_readmodel"])
    assert readmodel["tables"] == [
        "readmodel.public_article",
        "readmodel.public_article_block",
        "readmodel.public_product_card",
        "readmodel.public_offer",
        "readmodel.public_route",
    ]
    assert readmodel["runtime_control_implementation_slice"] == "SLICE-022"
    assert readmodel["runtime_control_in_scope"] is False
    roles = _mapping(projection["role_boundary"])
    assert roles["public_role_schema_usage"] == ["readmodel"]
    assert roles["public_role_table_privileges"] == ["SELECT"]


def test_jobs_conflicts_and_security_choices_remain_unresolved() -> None:
    projection = _mapping(_plan()["contract_projection"])
    job_surfaces = _mapping(projection["job_surfaces"])
    assert [_mapping(row)["job_type"] for row in job_surfaces.values()] == [
        "publishing.publish_snapshot.v1",
        "publishing.rebuild_public_projection.v1",
        "ops.rebuild_readmodel.v1",
    ]
    conflicts = _mapping(projection["surface_conflicts"])
    assert all(not _mapping(row)["reconciled"] for row in conflicts.values())
    security = _mapping(projection["security_boundary"])
    assert security["exact_snapshot_to_public_allowlist"] == "NOT_DEFINED"


def test_all_gates_records_and_verification_claims_fail_closed() -> None:
    plan = _plan()
    hard_gates = _rows(plan["hard_gates"])
    assert len(hard_gates) == 10
    assert all(
        row["safe_default"].startswith(("NO_", "KEEP_", "REFERENCE_"))
        for row in hard_gates
    )
    records = _mapping(plan["record_boundary"])
    assert all(
        _mapping(row)["status"] == "NOT_EVALUATED" and _mapping(row)["records"] == []
        for row in records.values()
    )
    assert _mapping(records["projections"])["empty_records_interpretation"] == (
        "NO_PROJECTION_OR_EVIDENCE_NOT_ZERO_VALID_PROJECTIONS"
    )
    verification = _mapping(plan["verification_boundary"])
    assert verification["formal_tst_011"] == "NOT_EXECUTED"
    assert verification["formal_tst_021"] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["effective_canonical_status"] == "UNCHANGED"
    boundary = _mapping(plan["implementation_boundary"])
    assert boundary["runtime_modules"] == []
    assert (
        boundary["executable_projector_requires"] == "OWNER_APPROVED_DESIGN_HANDOFF_V1"
    )
