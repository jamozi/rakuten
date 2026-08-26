"""ST-1702 semantic contract checks."""

from __future__ import annotations

from scripts import build_st1702_category_fixtures_rules_reference_plan as generator


def test_dependency_graph_uses_owner_versions() -> None:
    contract = generator.load_contract()
    dependencies = contract["dependencies"]
    assert dependencies[0]["owner_id"] == "build_st1701_business_inputs"
    assert dependencies[0]["owner_version"] == "2"
    assert dependencies[1]["owner_id"] == (
        "build_st0504_product_identity_human_review_reference_plan"
    )
    assert dependencies[2]["semantic_id"] == "st1401-freshness-safe-default"


def test_reference_plan_remains_non_executable() -> None:
    contract = generator.load_contract()
    document = contract["document"]
    execution = contract["execution_boundary"]
    assert document["executable"] is False
    assert document["st1702_ready"] is False
    assert execution["enabled"] is False
    assert execution["external_authority"] == "NONE"
    assert all(value == 0 for value in execution["action_counts"].values())
