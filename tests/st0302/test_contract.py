"""Canonical, upstream, and local ST-0302 contract binding tests."""

from __future__ import annotations

from typing import Any

import yaml

from .support import REPOSITORY_ROOT
from raos.migrations import catalog


def _record(document: dict[str, Any], key: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[key] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def test_canonical_story_is_exactly_the_foundation_scope() -> None:
    path = REPOSITORY_ROOT / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert _record(document, "stories", "ST-0302") == {
        "id": "ST-0302",
        "epic_id": "EPIC-03",
        "title": "Foundation schemas and extensions",
        "objective": "MIG-001相当を実装",
        "depends_on": ["ST-0301"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["schemas", "types", "uuidv7 validation"],
        "acceptance_criteria": ["baseline validation SQL pass"],
        "test_suites": ["TST-008"],
        "priority": "P0",
        "mvp": True,
        "size": "M",
        "open_decisions": [],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }


def test_tst008_remains_release_blocking_and_formally_unexecuted() -> None:
    path = (
        REPOSITORY_ROOT / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    suite = _record(document, "suites", "TST-008")

    assert suite == {
        "id": "TST-008",
        "name": "PostgreSQL baseline integration",
        "layer": "database",
        "purpose": "DDL/extension/seed/constraint/trigger/role",
        "candidate_tools": ["PostgreSQL 18 container", "pytest"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    }


def test_contract_fixes_the_exact_empty_schema_and_builtin_type_policy(
    foundation_contract: dict[str, Any],
) -> None:
    assert foundation_contract["story"]["dependencies"] == ["ST-0301"]
    assert foundation_contract["story"]["required_suites"] == ["TST-008"]
    assert [item["name"] for item in foundation_contract["schemas"]] == [
        "ops",
        "iam",
    ]
    assert {
        item["name"]: item["owner_privileges"]
        for item in foundation_contract["schemas"]
    } == {"ops": ["CREATE", "USAGE"], "iam": ["CREATE", "USAGE"]}
    assert foundation_contract["extensions"] == {
        "created": [],
        "runtime_dependencies": [],
        "id_generation_dependencies": [],
        "explicitly_not_required": ["pgcrypto", "uuid-ossp"],
    }
    assert foundation_contract["types"]["custom_types_created"] == []
    assert foundation_contract["types"]["native_enums_created"] == []
    assert foundation_contract["scope_precedence"]["table_creation"] == (
        "DEFERRED_TO_ST_0303"
    )
    assert foundation_contract["security"]["extension_install"] == "FORBIDDEN"
    assert foundation_contract["security"]["non_owner_schema_privileges"] == (
        "FORBIDDEN"
    )
    assert foundation_contract["security"]["foundation_default_privileges"] == (
        "FORBIDDEN_UNTIL_ST_0306"
    )
    assert foundation_contract["security"]["production_execution"] == "FORBIDDEN"


def test_upstream_mig001_and_uuidv7_facts_are_bound_without_importing_tables() -> None:
    playbook = (
        REPOSITORY_ROOT
        / "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md"
    ).read_text(encoding="utf-8")
    design = (
        REPOSITORY_ROOT
        / "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"
    ).read_text(encoding="utf-8")

    assert "### MIG-001 — Foundation schemas and shared operations" in playbook
    assert "- Schemas: ops, iam" in playbook
    assert "`uuidv7()`を組み込み関数として使用" in design
    assert "| `ops` | Operations | 16 |" in design
    assert "| `iam` | Identity and Access | 9 |" in design


def test_catalog_preserves_foundation_in_the_cumulative_linear_graph() -> None:
    assert catalog.ANCHOR_REVISION == "202608030001"
    assert catalog.FOUNDATION_REVISION == "202608030002"
    assert catalog.IAM_OPS_REVISION == "202608030003"
    assert catalog.DOMAIN_REVISION == "202608030004"
    assert catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION == "202608030005"
    assert catalog.DATABASE_ROLES_REVISION == catalog.HEAD_REVISION == "202608030006"
    assert [item.revision for item in catalog.REVISION_SPECS] == [
        "202608030001",
        "202608030002",
        "202608030003",
        "202608030004",
        "202608030005",
        "202608030006",
    ]
    foundation = catalog.REVISION_SPECS[1]
    assert foundation.down_revision == catalog.ANCHOR_REVISION
    assert foundation.story_id == "ST-0302"
    assert foundation.runner_version == "1.1.0"
    assert foundation.server_version_num == 180004
    iam_ops = catalog.REVISION_SPECS[2]
    assert iam_ops.down_revision == catalog.FOUNDATION_REVISION
    assert iam_ops.story_id == "ST-0303"
    assert iam_ops.runner_version == "1.2.0"
    assert iam_ops.server_version_num == 180004
    domain = catalog.REVISION_SPECS[3]
    assert domain.down_revision == catalog.IAM_OPS_REVISION
    assert domain.story_id == "ST-0304"
    assert domain.runner_version == "1.3.0"
    assert domain.server_version_num == 180004
    publication_analytics_finance = catalog.REVISION_SPECS[4]
    assert publication_analytics_finance.down_revision == catalog.DOMAIN_REVISION
    assert publication_analytics_finance.story_id == "ST-0305"
    assert publication_analytics_finance.runner_version == "1.4.0"
    assert publication_analytics_finance.server_version_num == 180004
    database_roles = catalog.REVISION_SPECS[5]
    assert (
        database_roles.down_revision == catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION
    )
    assert database_roles.story_id == "ST-0306"
    assert database_roles.runner_version == "1.5.0"
    assert database_roles.server_version_num == 180004


def test_execplan_records_all_required_sections_and_unchanged_canonical_status() -> (
    None
):
    text = (REPOSITORY_ROOT / "docs/execplans/ST-0302.md").read_text(encoding="utf-8")
    for number, title in enumerate(
        (
            "Story and outcome",
            "Context read",
            "Invariants",
            "Proposed design",
            "Milestones",
            "Test plan",
            "Evidence plan",
            "Risks and decisions",
            "Progress log",
            "Completion note",
        ),
        start=1,
    ):
        assert f"## {number}. {title}" in text
    assert "canonical status remains unchanged" in text
