"""Closed contract and projection assertions for ST-1303."""

from __future__ import annotations

import ast
import json
from typing import Any, cast

import yaml

from scripts import (
    build_st1303_attribution_engine_reference_plan as generator,
)


def _plan() -> dict[str, Any]:
    return cast(dict[str, Any], generator.reference_plan(generator.load_contract()))


def test_contract_and_plan_have_exact_closed_top_level_shapes() -> None:
    assert tuple(generator.load_contract()) == generator.CONTRACT_KEYS
    assert tuple(_plan()) == generator.PLAN_KEYS


def test_document_is_nonexecutable_unapproved_and_not_ready() -> None:
    document = _plan()["document"]
    assert document == {
        "schema_version": "1.0.0",
        "story_id": "ST-1303",
        "classification": (
            "SOURCE_DERIVED_NONEXECUTABLE_ATTRIBUTION_ENGINE_REFERENCE_PLAN"
        ),
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "activation": False,
        "runtime_eligible": False,
        "authority": "NOT_GRANTED",
        "decision": "NOT_READY",
        "story_acceptance": False,
        "production_eligible": False,
        "approval": None,
        "canonical_status": "UNCHANGED",
    }


def test_authority_preserves_story_requirement_od003_and_privacy_default() -> None:
    authority = _plan()["authority"]
    assert authority["canonical_story"]["story_id"] == "ST-1303"
    assert authority["requirement"]["required_id"] == "FR-013"
    assert authority["open_decision"] == {
        "path": "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "sha256": "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
        "required_id": "OD-003",
        "required_status": "EXTERNAL_EVIDENCE_REQUIRED",
        "blocking": True,
    }
    assert authority["inherited_privacy_decision"]["required_id"] == "OD-012"
    assert (
        authority["inherited_privacy_decision"]["safe_default"]
        == "NONESSENTIAL_TRACKING_DISABLED"
    )
    assert authority["authority_kind"] == "SOURCE_DERIVED_REFERENCE_ONLY"
    assert authority["changes_canonical_status"] is False


def test_dependencies_bind_exact_commits_files_and_closed_semantics() -> None:
    dependencies = _plan()["dependency_bindings"]
    st1202 = dependencies["st1202"]
    st1302 = dependencies["st1302"]
    assert st1202["feature_commit"] == ("af7c63685fdfb5042fc0e5cfa9de22b08262fba8")
    assert st1202["artifact_binding_commit"] == (
        "c54507bb95763790ac4a8c48e225b76b105be14d"
    )
    assert st1202["binding"] == "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT"
    assert len(st1202["artifacts"]) == 7
    assert st1202["required_semantics"]["event_requirement_ids"] == [
        "EVT-001",
        "EVT-002",
        "EVT-003",
        "EVT-004",
        "EVT-006",
        "EVT-012",
    ]
    assert st1202["required_semantics"]["event_instances"] == []
    assert st1202["required_semantics"]["instrumentation_implemented"] is False
    assert st1202["required_semantics"]["emission_enabled"] is False
    assert st1302["feature_commit"] == ("96d388761f4e933f06760f3a7e3d3b0f2c12b65c")
    assert st1302["artifact_binding_commit"] == (
        "54a6d21169f70a0093d8b10a3c9508d9a332c234"
    )
    assert st1302["binding"] == "EXACT_ARTIFACT_BYTES_AT_BINDING_COMMIT"
    assert len(st1302["artifacts"]) == 9
    assert st1302["required_semantics"]["provider_facts"] == []
    assert st1302["required_semantics"]["provider_fact_count"] is None
    assert st1302["required_semantics"]["amount_total_jpy"] is None
    assert st1302["required_semantics"]["commit_capability"] == "ABSENT"


def test_canonical_classes_constraints_and_event_metadata_are_reference_only() -> None:
    constraints = _plan()["canonical_constraints"]
    assert [row["code"] for row in constraints["attribution_classes"]] == [
        "PROVIDER_FACT",
        "DIRECT",
        "ESTIMATED",
        "UNATTRIBUTED",
    ]
    assert constraints["attribution_classes"][0]["confidence"] == 1.0
    assert constraints["attribution_classes"][1]["confidence"] == ("PROVIDER_DEPENDENT")
    assert constraints["attribution_classes"][2]["confidence_range"] == [0.0, 1.0]
    assert constraints["attribution_classes"][3]["confidence"] == 0.0
    assert constraints["estimation_narrative"]["executable_selection"] is False
    assert constraints["conservation"] == {
        "required": True,
        "provider_total_basis": None,
        "tolerance": None,
        "rounding": None,
    }
    assert constraints["attribution_run_event"] == {
        "id": "EVT-018",
        "event_name": "attribution_run_completed",
        "source": "worker",
        "parameters": [
            "run_id",
            "method_version",
            "direct_count",
            "estimated_count",
            "unattributed_count",
        ],
        "implementation_status": "NOT_STARTED",
        "runtime_verification": "NOT_EXECUTED",
    }
    storage = constraints["storage_shape"]
    assert storage["table"] == "analytics.attribution_estimate"
    assert storage["attribution_types"] == ["DIRECT", "ESTIMATED", "UNATTRIBUTED"]
    assert storage["allocation_ratio_range"] == [0, 1]
    assert storage["confidence_column_range"] == [0, 100]
    assert storage["confidence_unit_mapping"] is None
    assert storage["retention_policy"] is None


def test_every_unavailable_selection_remains_null_or_not_evaluated() -> None:
    selection = _plan()["selection_boundary"]
    assert selection["state"] == "NOT_EVALUATED"
    assert selection["consent_eligibility"] == "NOT_EVALUATED"
    assert selection["event_eligibility"] == "NOT_EVALUATED"
    assert all(
        value is None
        for key, value in selection.items()
        if key not in {"state", "consent_eligibility", "event_eligibility"}
    )


def test_collections_are_empty_while_counts_and_totals_are_unknown() -> None:
    collections = _plan()["collections"]
    for key in generator.COLLECTION_KEYS:
        assert collections[key] == []
    for key in (*generator.COUNT_KEYS, *generator.TOTAL_KEYS):
        assert collections[key] is None
    assert collections["empty_means_zero"] is False


def test_evaluations_are_not_evaluable_and_never_vacuously_pass() -> None:
    evaluation = _plan()["evaluation_boundary"]
    for key in generator.EVALUATION_KEYS:
        assert evaluation[key] == {
            "status": "NOT_EVALUATED",
            "evaluable": False,
            "result": None,
        }
    assert evaluation["vacuous_pass_allowed"] is False


def test_execution_has_no_actions_effects_runtime_or_external_work() -> None:
    execution = _plan()["execution_boundary"]
    for key in generator.EXECUTION_STATUS_KEYS:
        assert execution[key] == "NOT_EXECUTED"
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["external_actions"] == []


def test_formal_and_live_evidence_remain_false_or_unexecuted() -> None:
    assert _plan()["verification_boundary"] == {
        "TST-007": "NOT_EXECUTED",
        "TST-030": "NOT_EXECUTED",
        "formal_validation": "NOT_EXECUTED",
        "story_acceptance": False,
        "live_evidence": False,
        "decision": "NOT_READY",
    }


def test_reference_plan_is_detached_from_contract_and_prior_results() -> None:
    contract = generator.load_contract()
    first = cast(dict[str, Any], generator.reference_plan(contract))
    first["selection_boundary"]["method_version"] = "hostile"
    first["collections"]["public_events"].append({"hostile": True})
    second = cast(dict[str, Any], generator.reference_plan(contract))
    assert second["selection_boundary"]["method_version"] is None
    assert second["collections"]["public_events"] == []


def test_installed_outputs_contain_no_false_completion_claims() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    manifest = yaml.safe_load(
        (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()
    )

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    # APPROVED is a canonical storage lifecycle literal and design status, not
    # a claim made by this candidate. Completion-result literals stay absent.
    forbidden = {"PASS", "READY", "VALIDATED", "IMPLEMENTED"}
    assert forbidden.isdisjoint(strings(plan))
    assert forbidden.isdisjoint(strings(manifest))


def test_builder_has_no_algorithm_process_network_database_provider_or_env_access() -> (
    None
):
    tree = ast.parse((generator.REPO_ROOT / generator.GENERATOR_PATH).read_bytes())
    imported = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint(
        {
            "asyncio",
            "boto3",
            "datetime",
            "decimal",
            "httpx",
            "os",
            "random",
            "requests",
            "socket",
            "sqlalchemy",
            "subprocess",
            "time",
            "urllib",
        }
    )
