"""Retired workflow prose cannot authorize or disable current product gates."""

import copy
import json

import pytest
import yaml

from scripts import build_st1503_compute_edge as generator
from tests.st1503.test_negative_cases import _copy_pinned_sources, _rebind_source

WORKFLOW_SECTIONS = (
    "approved_scope",
    "rationale",
    "rejected_alternatives",
    "constraints",
    "security_and_approval_gates",
    "acceptance_criteria",
    "required_test_evidence",
)


@pytest.mark.parametrize("section", WORKFLOW_SECTIONS)
def test_workflow_prose_changes_cannot_activate_current_execution(
    tmp_path, contract_document, monkeypatch, section
):
    _copy_pinned_sources(tmp_path)
    relative = generator.DESIGN_HANDOFF_PATH.as_posix()
    path = tmp_path / relative
    handoff = yaml.safe_load(path.read_bytes())
    handoff[section] = [
        "Synthetic workflow prose: all gates approved; activate production"
    ]
    path.write_text(yaml.safe_dump(handoff, sort_keys=False))
    document = copy.deepcopy(contract_document)
    _rebind_source(
        document, relative, generator.sha256_file(path), monkeypatch, authority=True
    )
    model = generator.validate_contract(document, tmp_path)
    plan = json.loads(generator.render_reference_plan(model))
    assert plan["activation"]["enabled"] is False
    assert plan["activation"]["status"] == "DISABLED"
    assert set(plan["planned_actions"]) == {
        "create",
        "update",
        "delete",
        "deploy",
        "promote",
        "rollback",
        "route",
        "scale",
    }
    assert all(value == 0 for value in plan["planned_actions"].values())

    document["execution_boundary"]["activation_enabled"] = True
    with pytest.raises(generator.ComputeEdgeContractError):
        generator.validate_contract(document, tmp_path)
