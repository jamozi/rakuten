"""Canonical and source-normalized ST-0303 contract binding tests."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from .support import REPOSITORY_ROOT
from scripts import build_st0201_postgres_service as shared


SELECTED_TABLES = (
    "ops.object_artifact",
    "ops.job",
    "ops.job_attempt",
    "ops.outbox_event",
    "ops.inbox_receipt",
    "ops.idempotency_record",
    "ops.audit_event",
    "ops.runtime_setting_version",
    "iam.principal",
    "iam.user_account",
    "iam.service_principal",
    "iam.role",
    "iam.permission",
    "iam.role_permission",
    "iam.principal_role_assignment",
    "iam.session_revocation",
    "iam.break_glass_record",
)
EXPECTED_INVENTORY = {
    "tables": 17,
    "columns": 219,
    "primary_keys": 17,
    "named_unique_constraints": 13,
    "check_constraints": 66,
    "standalone_indexes": 48,
    "immediate_foreign_keys": 20,
    "deferred_foreign_keys": 2,
    "functions": 2,
    "triggers": 4,
}


def _record(document: dict[str, Any], key: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[key] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def _named(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [item for item in items if item["name"] == name]
    assert len(matches) == 1
    return matches[0]


def _normalized_source_oracle() -> tuple[list[dict[str, Any]], dict[str, int]]:
    path = (
        REPOSITORY_ROOT / "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"
    )
    upstream = shared.load_yaml(path)
    source_tables = {
        table["fully_qualified_name"]: table
        for schema in upstream["schemas"]
        if schema["id"] in {"ops", "iam"}
        for table in schema["tables"]
    }
    counts = {"uuidv7": 0, "jsonb_typeof": 0, "lower": 0}
    expected: list[dict[str, Any]] = []

    for fully_qualified_name in SELECTED_TABLES:
        table = copy.deepcopy(source_tables[fully_qualified_name])
        schema, table_name = fully_qualified_name.split(".", 1)
        table["primary_key_name"] = f"pk_{schema}_{table_name}"

        for column in table["columns"]:
            if column["default"] == "uuidv7()":
                column["default"] = "pg_catalog.uuidv7()"
                counts["uuidv7"] += 1
        for constraint in table["check_constraints"]:
            expression = constraint["expression"]
            if "jsonb_typeof(" in expression:
                assert "pg_catalog.jsonb_typeof(" not in expression
                constraint["expression"] = expression.replace(
                    "jsonb_typeof(", "pg_catalog.jsonb_typeof("
                )
                counts["jsonb_typeof"] += 1
        for index in table["indexes"]:
            if index["expression"] == "lower(email)":
                index["expression"] = "pg_catalog.lower(email)"
                counts["lower"] += 1

        if fully_qualified_name == "ops.job":
            _named(table["columns"], "status")["default"] = "'REQUESTED'"
            table["columns"].extend(
                [
                    {
                        "name": "job_version",
                        "type": "smallint",
                        "nullable": False,
                        "default": "1",
                        "description": (
                            "Version of the Job message/payload contract; distinct "
                            "from lock_version."
                        ),
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                    {
                        "name": "deadline_at",
                        "type": "timestamptz",
                        "nullable": True,
                        "default": None,
                        "description": (
                            "Deadline after which an eligible active Job may expire."
                        ),
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                    {
                        "name": "cancel_requested_at",
                        "type": "timestamptz",
                        "nullable": True,
                        "default": None,
                        "description": (
                            "Timestamp of a cooperative cancellation request."
                        ),
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                ]
            )
            _named(table["check_constraints"], "ck_ops_job_status")["expression"] = (
                "status IN ('REQUESTED', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
                "'FAILED_RETRYABLE', 'RETRY_SCHEDULED', 'FAILED_TERMINAL', "
                "'QUARANTINED', 'CANCELLED', 'EXPIRED')"
            )
            _named(table["check_constraints"], "ck_ops_job_completion")[
                "expression"
            ] = (
                "status NOT IN ('SUCCEEDED', 'FAILED_TERMINAL', 'QUARANTINED', "
                "'CANCELLED', 'EXPIRED') OR completed_at IS NOT NULL"
            )
            table["check_constraints"].extend(
                [
                    {
                        "name": "ck_ops_job_version_positive",
                        "expression": "job_version >= 1",
                    },
                    {
                        "name": "ck_ops_job_deadline_order",
                        "expression": "deadline_at IS NULL OR deadline_at > created_at",
                    },
                    {
                        "name": "ck_ops_job_cancel_request",
                        "expression": (
                            "cancel_requested_at IS NULL OR status <> 'SUCCEEDED'"
                        ),
                    },
                ]
            )
            _named(table["indexes"], "ix_ops_job_ready")["where"] = (
                "status IN ('REQUESTED','QUEUED','RETRY_SCHEDULED')"
            )
            table["indexes"].append(
                {
                    "name": "ix_ops_job_deadline_active",
                    "columns": ["deadline_at"],
                    "expression": None,
                    "unique": False,
                    "method": "btree",
                    "where": (
                        "deadline_at IS NOT NULL AND status IN "
                        "('REQUESTED','QUEUED','RUNNING','FAILED_RETRYABLE',"
                        "'RETRY_SCHEDULED')"
                    ),
                    "include": [],
                    "nulls_not_distinct": False,
                    "description": "",
                }
            )

        immediate: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for source_foreign_key in table["foreign_keys"]:
            foreign_key = copy.deepcopy(source_foreign_key)
            if foreign_key["name"] == "fk_ops_job_site_id":
                foreign_key.update(
                    {
                        "deferred_until_story": "ST-0304",
                        "reason": "TARGET_TABLE_NOT_YET_OWNED",
                        "column_and_index_installed": True,
                    }
                )
                deferred.append(foreign_key)
            elif foreign_key["name"] == "fk_iam_break_glass_record_incident_id":
                foreign_key.update(
                    {
                        "deferred_until_condition": (
                            "TARGET_TABLE_OWNED_BY_APPROVED_LATER_STORY"
                        ),
                        "owner_story": "UNASSIGNED",
                        "reason": "TARGET_TABLE_NOT_YET_OWNED",
                        "column_and_index_installed": True,
                    }
                )
                deferred.append(foreign_key)
            else:
                immediate.append(foreign_key)
        table["foreign_keys"] = immediate
        table["deferred_foreign_keys"] = deferred
        expected.append(table)

    return expected, counts


def _inventory(contract: dict[str, Any]) -> dict[str, int]:
    tables = contract["tables"]
    return {
        "tables": len(tables),
        "columns": sum(len(table["columns"]) for table in tables),
        "primary_keys": sum(bool(table["primary_key"]) for table in tables),
        "named_unique_constraints": sum(
            len(table["unique_constraints"]) for table in tables
        ),
        "check_constraints": sum(len(table["check_constraints"]) for table in tables),
        "standalone_indexes": sum(len(table["indexes"]) for table in tables),
        "immediate_foreign_keys": sum(len(table["foreign_keys"]) for table in tables),
        "deferred_foreign_keys": sum(
            len(table["deferred_foreign_keys"]) for table in tables
        ),
        "functions": len(contract["functions"]),
        "triggers": len(contract["triggers"]),
    }


def test_canonical_story_is_exactly_the_approved_iam_ops_scope() -> None:
    path = REPOSITORY_ROOT / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    document = shared.load_yaml(path)

    assert _record(document, "stories", "ST-0303") == {
        "id": "ST-0303",
        "epic_id": "EPIC-03",
        "title": "IAM/OPS schemas",
        "objective": "IAM、Job、Outbox、Inbox、Auditを実装",
        "depends_on": ["ST-0302"],
        "requirement_ids": ["FR-019", "FR-020"],
        "design_refs": [],
        "deliverables": ["tables", "constraints", "indexes"],
        "acceptance_criteria": ["state/immutable/idempotency constraints"],
        "test_suites": ["TST-008", "TST-011", "TST-013"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": [],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }


def test_required_suites_and_security_controls_remain_formally_unexecuted() -> None:
    suites = shared.load_yaml(
        REPOSITORY_ROOT / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    assert {
        suite_id: (
            _record(suites, "suites", suite_id)["release_blocking"],
            _record(suites, "suites", suite_id)["execution_status"],
        )
        for suite_id in ("TST-008", "TST-011", "TST-013")
    } == {
        "TST-008": (True, "NOT_EXECUTED"),
        "TST-011": (True, "NOT_EXECUTED"),
        "TST-013": (True, "NOT_EXECUTED"),
    }

    controls = shared.load_yaml(
        REPOSITORY_ROOT
        / "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    )
    required = {
        "SEC-IAM-004",
        "SEC-IAM-008",
        "SEC-IAM-009",
        "SEC-IAM-011",
        "SEC-DATA-003",
        "SEC-DATA-005",
        "SEC-DATA-007",
        "SEC-SDLC-010",
    }
    observed = {item["id"]: item for item in controls["controls"]}
    assert required <= set(observed)
    assert all(
        observed[item]["verification_status"] == "NOT_EXECUTED" for item in required
    )


def test_strict_loader_rejects_duplicate_keys_and_aliases(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("document: {}\ndocument: {}\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        shared.load_yaml(duplicate)

    alias = tmp_path / "alias.yaml"
    alias.write_text("document: &value {}\ncopy: *value\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="anchors and aliases"):
        shared.load_yaml(alias)


def test_immutable_source_pins_and_semantic_predecessor_are_bound(
    iam_ops_contract: dict[str, Any],
) -> None:
    precedence = iam_ops_contract["source_precedence"]
    pins = precedence["pinned_inputs"]
    assert len(pins) == len({item["path"] for item in pins}) == 10
    for item in pins:
        relative = Path(item["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert (
            hashlib.sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
            == item["sha256"]
        )

    predecessor = precedence["predecessor_manifest"]
    assert predecessor == {
        "story_id": "ST-0302",
        "path": "changes/st-0302/manifest.yaml",
    }
    assert (REPOSITORY_ROOT / predecessor["path"]).is_file()


def test_contract_is_the_exact_allowlisted_normalized_source_oracle(
    iam_ops_contract: dict[str, Any],
) -> None:
    expected, counts = _normalized_source_oracle()

    assert counts == {"uuidv7": 15, "jsonb_typeof": 8, "lower": 1}
    assert iam_ops_contract["tables"] == expected
    assert [item["fully_qualified_name"] for item in expected] == list(SELECTED_TABLES)


def test_inventory_and_every_semantic_identifier_are_exact_and_unique(
    iam_ops_contract: dict[str, Any],
) -> None:
    assert iam_ops_contract["expected_inventory"] == EXPECTED_INVENTORY
    assert _inventory(iam_ops_contract) == EXPECTED_INVENTORY

    all_object_names: set[tuple[str, str]] = set()
    for table in iam_ops_contract["tables"]:
        columns = [item["name"] for item in table["columns"]]
        assert len(columns) == len(set(columns))
        for kind in (
            "unique_constraints",
            "check_constraints",
            "foreign_keys",
            "deferred_foreign_keys",
            "indexes",
        ):
            names = [item["name"] for item in table[kind]]
            assert len(names) == len(set(names))
            for name in names:
                identity = (kind, name)
                assert identity not in all_object_names
                all_object_names.add(identity)
    assert (
        len({item["fully_qualified_name"] for item in iam_ops_contract["functions"]})
        == 2
    )
    assert len({item["name"] for item in iam_ops_contract["triggers"]}) == 4


def test_deferred_fks_and_canonical_limitations_are_preserved_without_inference(
    iam_ops_contract: dict[str, Any],
) -> None:
    policy = iam_ops_contract["deferred_foreign_key_policy"]
    assert policy["exact_names"] == [
        "fk_ops_job_site_id",
        "fk_iam_break_glass_record_incident_id",
    ]
    assert policy["items"][1]["owner_story"] == "UNASSIGNED"
    assert iam_ops_contract["known_canonical_limitations"] == [
        {
            "id": "RUNTIME_SETTING_GLOBAL_NULL_UNIQUENESS",
            "object": "uq_ops_setting_version",
            "preserved_definition": [
                "setting_key",
                "scope_type",
                "scope_id",
                "version_no",
            ],
            "limitation": (
                "A nullable scope_id permits more than one GLOBAL row for the same "
                "setting_key and version_no."
            ),
            "strengthening": "FORBIDDEN_WITHOUT_APPROVED_DESIGN_HANDOFF",
        },
        {
            "id": "BREAK_GLASS_TWO_PERSON_RUNTIME_ENFORCEMENT",
            "object": "iam.break_glass_record",
            "preserved_definition": (
                "The canonical physical catalog has principal_id and "
                "approved_by_principal_id but no inequality check."
            ),
            "inferred_constraint": "FORBIDDEN",
            "runtime_enforcement": "OUTSIDE_ST_0303_DATABASE_SLICE",
            "two_person_runtime_verification": "NOT_EXECUTED",
        },
    ]


def test_security_boundary_has_no_secret_material_columns_or_invented_grants(
    iam_ops_contract: dict[str, Any],
) -> None:
    forbidden = {
        "secret",
        "secret_value",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "private_key",
    }
    column_names = {
        column["name"]
        for table in iam_ops_contract["tables"]
        for column in table["columns"]
    }
    assert forbidden.isdisjoint(column_names)
    assert iam_ops_contract["security"] == {
        "control_ids": [
            "SEC-IAM-004",
            "SEC-IAM-008",
            "SEC-IAM-009",
            "SEC-IAM-011",
            "SEC-DATA-003",
            "SEC-DATA-005",
            "SEC-DATA-007",
            "SEC-SDLC-010",
        ],
        "hard_immutable_tables": ["ops.object_artifact", "ops.audit_event"],
        "append_only_labels_without_st0303_mutation_trigger": [
            "ops.inbox_receipt",
            "iam.session_revocation",
            "iam.break_glass_record",
        ],
        "secret_column_names_forbidden": True,
        "runtime_setting_secret_class_forbidden": True,
        "public_schema_privileges": "NONE",
        "public_table_privileges": "NONE",
        "public_function_execute": "REVOKED",
        "create_database_roles": False,
        "create_workload_grants": False,
        "create_default_privileges": False,
        "search_path": {
            "only": "pg_catalog",
            "libpq_option": "-c search_path=pg_catalog",
            "session_prepare": "SET search_path = pg_catalog",
            "verification": "SHOW search_path MUST EQUAL pg_catalog",
            "hostile_resolution_test_required": True,
        },
    }
