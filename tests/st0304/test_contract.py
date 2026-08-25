"""Exact source, scope, and security-boundary tests for ST-0304."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from conftest import REPOSITORY_ROOT
from scripts import build_st0304_domain_schemas as generator


FROZEN_CONTRACT_PREDECESSOR_SHA256 = (
    "f795daab918844b2bd0c2fb6e8aa17031f4e849e9ccb5bcfe45d554ddf69fe8b"
)


def test_contract_binds_the_exact_approved_story_and_formal_boundary(
    domain_contract: dict[str, Any],
) -> None:
    assert domain_contract["document"] == {
        "id": "RAOS-DOMAIN-SCHEMA-001",
        "version": "1.0.0",
        "story_id": "ST-0304",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "formal_verification": "NOT_EXECUTED",
    }
    story = domain_contract["story"]
    assert story["dependencies"] == ["ST-0303"]
    assert story["requirement_ids"] == [
        "FR-001",
        "FR-002",
        "FR-003",
        "FR-004",
        "FR-007",
        "FR-018",
    ]
    assert story["required_suites"] == ["TST-008", "TST-010"]
    assert story["open_decisions"] == []
    assert tuple(domain_contract["source_precedence"]["schemas"]) == generator.SCHEMAS
    assert domain_contract["database"]["exact_server_version_num"] == 180004
    assert domain_contract["boundary"]["formal_tst_008"] == "NOT_EXECUTED"
    assert domain_contract["boundary"]["formal_tst_010"] == "NOT_EXECUTED"
    assert domain_contract["boundary"]["effective_canonical_status"] == "UNCHANGED"


def test_physical_inventory_is_independently_derived_from_all_fragments(
    physical_objects: tuple[generator.PhysicalObject, ...],
) -> None:
    counts = Counter(item.object_type for item in physical_objects)
    assert len(physical_objects) == 1842
    assert counts == {
        "COMMENT": 898,
        "CONSTRAINT": 179,
        "FK CONSTRAINT": 264,
        "FUNCTION": 48,
        "INDEX": 274,
        "ROW SECURITY": 11,
        "TABLE": 86,
        "TRIGGER": 81,
        "VIEW": 1,
    }
    tables = [item for item in physical_objects if item.object_type == "TABLE"]
    columns = [
        column
        for table in tables
        for column in generator._table_column_entries(table.sql)
    ]
    constraints = [
        item for item in physical_objects if item.object_type == "CONSTRAINT"
    ]
    assert len(columns) == 1141
    assert sum(" NOT NULL" in column for column in columns) == 861
    assert sum(table.sql.count('CONSTRAINT "ck_') for table in tables) == 453
    assert sum(" PRIMARY KEY " in item.sql for item in constraints) == 86
    assert sum(" UNIQUE " in item.sql for item in constraints) == 93


def test_upstream_baseline_table_and_column_identities_are_in_physical_inventory(
    physical_objects: tuple[generator.PhysicalObject, ...],
) -> None:
    upstream = yaml.safe_load(
        (REPOSITORY_ROOT / generator.UPSTREAM_CATALOG_PATH).read_bytes()
    )
    selected_schemas = [
        next(schema for schema in upstream["schemas"] if schema["id"] == schema_id)
        for schema_id in generator.SCHEMAS
    ]
    baseline_tables = {
        (schema["id"], table["name"])
        for schema in selected_schemas
        for table in schema["tables"]
    }
    baseline_columns = {
        (schema["id"], table["name"], column["name"])
        for schema in selected_schemas
        for table in schema["tables"]
        for column in table["columns"]
    }
    physical_tables = {
        (item.schema, item.name)
        for item in physical_objects
        if item.object_type == "TABLE"
    }
    physical_columns = {
        (item.schema, item.name, entry.split('"', 2)[1])
        for item in physical_objects
        if item.object_type == "TABLE"
        for entry in generator._table_column_entries(item.sql)
    }

    assert len(selected_schemas) == 6
    assert len(baseline_tables) == 66
    assert len(baseline_columns) == 821
    assert len(physical_tables) == 86
    assert len(physical_columns) == 1141
    assert baseline_tables <= physical_tables
    assert baseline_columns <= physical_columns


def test_every_provenance_input_and_fragment_is_live_hash_bound(
    domain_contract: dict[str, Any],
) -> None:
    assert (
        hashlib.sha256(
            (REPOSITORY_ROOT / generator.CONTRACT_PATH).read_bytes()
        ).hexdigest()
        == generator.EXPECTED_CONTRACT_SHA256
    )
    for path, digest in generator.PINNED_INPUTS.items():
        assert (
            hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest() == digest
        )
    rows = domain_contract["source_precedence"]["physical_translation_fragments"]
    assert tuple(Path(row["path"]) for row in rows) == generator.FRAGMENT_PATHS
    assert tuple(row["sha256"] for row in rows) == generator.EXPECTED_FRAGMENT_SHA256
    for path, digest in zip(
        generator.FRAGMENT_PATHS, generator.EXPECTED_FRAGMENT_SHA256, strict=True
    ):
        assert (
            hashlib.sha256((REPOSITORY_ROOT / path).read_bytes()).hexdigest() == digest
        )
    predecessor = domain_contract["source_precedence"]["predecessor_manifest"]
    assert predecessor == {
        "story_id": "ST-0303",
        "path": "changes/st-0303/manifest.yaml",
        "sha256": FROZEN_CONTRACT_PREDECESSOR_SHA256,
    }


def test_finalized_overlay_checkpoints_remain_provenance_only(
    domain_contract: dict[str, Any],
) -> None:
    overlay = domain_contract["source_precedence"]["finalized_overlay_checkpoints"]
    assert overlay["execution"] == "PROVENANCE_ONLY_NOT_CONCATENATED"
    assert len(overlay["files"]) == 10
    for row in overlay["files"]:
        path = REPOSITORY_ROOT / row["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def test_rls_table_state_is_exact_and_role_bound_policies_are_absent(
    domain_contract: dict[str, Any],
    physical_objects: tuple[generator.PhysicalObject, ...],
) -> None:
    force_tables = {
        f"{item.schema}.{item.name}"
        for item in physical_objects
        if " FORCE ROW LEVEL SECURITY" in item.sql
    }
    enabled_tables = {
        f"{item.schema}.{item.name}"
        for item in physical_objects
        if item.object_type == "ROW SECURITY"
        and " ENABLE ROW LEVEL SECURITY" in item.sql
    }
    assert force_tables == enabled_tables == set(generator.RLS_TABLES)
    assert domain_contract["security"]["rls_enabled_and_forced_tables"] == list(
        generator.RLS_TABLES
    )
    joined = "\n".join(item.sql for item in physical_objects)
    assert "CREATE POLICY" not in joined
    assert "CREATE ROLE" not in joined
    assert "ALTER DEFAULT PRIVILEGES" not in joined


def test_deferred_foreign_key_boundary_is_exact(
    domain_contract: dict[str, Any],
) -> None:
    statements = generator.render_upgrade_statements()
    joined = "\n".join(statements)
    preflight = joined.index("ST0304_OPS_JOB_SITE_ORPHAN")
    connected = joined.index('ADD CONSTRAINT "fk_ops_job_site_id"')

    assert preflight < connected
    assert joined.count('ADD CONSTRAINT "fk_ops_job_site_id"') == 1
    assert 'REFERENCES "portfolio"."site"("id") ON DELETE RESTRICT NOT VALID' in joined
    assert joined.count('VALIDATE CONSTRAINT "fk_ops_job_site_id"') == 1
    assert "fk_iam_break_glass_record_incident_id" not in joined
    policy = domain_contract["deferred_foreign_key_policy"]
    assert policy["exact_names"] == ["fk_iam_break_glass_record_incident_id"]
    assert policy["retained_deferred"] == [
        {
            "name": "fk_iam_break_glass_record_incident_id",
            "table": "iam.break_glass_record",
            "references": "ops.incident",
            "owner_story": "UNASSIGNED",
        }
    ]
