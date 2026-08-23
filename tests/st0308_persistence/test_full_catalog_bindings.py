"""Exact no-reflection coverage for the complete generated ST-0308 catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import pytest
from sqlalchemy import CheckConstraint, Computed, Date, DateTime, Numeric, Table
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from raos.adapters.persistence.sqlalchemy.generated import catalog
from scripts import build_st0308_persistence as generator


ROOT = Path(__file__).resolve().parents[2]
IR_PATH = ROOT / "changes/st-0308/generated/persistence-catalog-ir.v1.json"
CATALOG_PATH = ROOT / "python/raos/adapters/persistence/sqlalchemy/generated/catalog.py"


def _ir() -> dict[str, object]:
    value = json.loads(IR_PATH.read_bytes())
    assert type(value) is dict
    return value


def _relations() -> dict[str, dict[str, object]]:
    rows = _ir()["relations"]
    assert type(rows) is list
    result: dict[str, dict[str, object]] = {}
    for raw in rows:
        assert type(raw) is dict
        relation = raw["relation"]
        assert type(relation) is str
        assert relation not in result
        result[relation] = raw
    return result


def _semantic(row: object) -> dict[str, object]:
    assert type(row) is dict
    semantics = row.get("semantics")
    if semantics is None:
        return row
    assert type(semantics) is dict
    return semantics


def test_complete_catalog_is_closed_separate_and_exactly_reproducible() -> None:
    relations = _relations()
    expected_tables = {
        name for name, row in relations.items() if row["kind"] == "TABLE"
    }
    expected_views = {name for name, row in relations.items() if row["kind"] == "VIEW"}
    assert len(relations) == 104
    assert len(expected_tables) == 103
    assert expected_views == {"catalog.v_safe_offer_current"}
    assert type(catalog.TABLES_BY_RELATION) is MappingProxyType
    assert type(catalog.READ_ONLY_VIEWS) is MappingProxyType
    assert type(catalog.RELATIONS_BY_NAME) is MappingProxyType
    assert set(catalog.TABLES_BY_RELATION) == expected_tables
    assert set(catalog.READ_ONLY_VIEWS) == expected_views
    assert set(catalog.RELATIONS_BY_NAME) == set(relations)
    assert catalog.METADATA.tables == catalog.RELATIONS_BY_NAME
    assert all(type(value) is Table for value in catalog.RELATIONS_BY_NAME.values())
    with pytest.raises(TypeError):
        catalog.TABLES_BY_RELATION["unknown.relation"] = object()  # type: ignore[index]

    outputs = generator.render_outputs(ROOT)
    assert generator.OUTPUT_FULL_CATALOG_PATH in outputs
    assert outputs[generator.OUTPUT_FULL_CATALOG_PATH] == CATALOG_PATH.read_bytes()
    assert generator.OUTPUT_FULL_CATALOG_PATH in generator.OWNER_OUTPUT_PATHS
    assert hashlib.sha256(IR_PATH.read_bytes()).hexdigest() == catalog.CATALOG_IR_SHA256
    assert (
        hashlib.sha256(
            (ROOT / "scripts/build_st0308_persistence.py").read_bytes()
        ).hexdigest()
        == catalog.OWNER_GENERATOR_SHA256
    )


def test_all_relation_columns_defaults_and_generated_expression_match_ir() -> None:
    relations = _relations()
    assert sum(len(row["columns"]) for row in relations.values()) == 1376
    computed_columns: list[str] = []
    for relation_name, row in relations.items():
        table = catalog.RELATIONS_BY_NAME[relation_name]
        columns = row["columns"]
        assert type(columns) is list
        assert tuple(table.c) == tuple(
            table.c[column["physical_column"]] for column in columns
        )
        assert tuple(table.c.keys()) == tuple(
            column["physical_column"] for column in columns
        )
        for raw_column in columns:
            assert type(raw_column) is dict
            column_name = raw_column["physical_column"]
            assert type(column_name) is str
            binding = table.c[column_name]
            assert binding.nullable is raw_column["nullable"]
            physical_type = raw_column["physical_sql_type"]
            assert type(physical_type) is str
            computed = binding.computed
            if " GENERATED ALWAYS AS " in physical_type:
                computed_columns.append(f"{relation_name}.{column_name}")
                assert type(computed) is Computed
                assert computed.persisted is True
            else:
                assert computed is None
            default = raw_column["server_default"]
            if default is None and computed is None:
                assert binding.server_default is None
            elif computed is None:
                assert binding.server_default is not None

            normalized = physical_type.replace('"', "")
            if " GENERATED ALWAYS AS " in normalized:
                normalized = normalized.split(" GENERATED ALWAYS AS ", 1)[0]
            normalized = normalized.split(" CONSTRAINT ", 1)[0]
            if normalized in {"timestamptz", "timestamp with time zone"}:
                assert type(binding.type) is DateTime
                assert binding.type.timezone is True
            elif normalized == "date":
                assert type(binding.type) is Date
            elif normalized == "jsonb":
                assert type(binding.type) is JSONB
            elif normalized == "text[]":
                assert type(binding.type) is ARRAY
            elif normalized.startswith("numeric"):
                assert type(binding.type) is Numeric
    assert computed_columns == [
        "ai.evaluation_case_result.zero_tolerance_failure_count"
    ]


def test_all_table_constraints_indexes_and_read_only_view_match_ir() -> None:
    relations = _relations()
    expected_foreign_keys = 0
    expected_uniques = 0
    expected_checks = 0
    expected_indexes = 0
    for relation_name, row in relations.items():
        binding = catalog.RELATIONS_BY_NAME[relation_name]
        if row["kind"] == "VIEW":
            assert binding.info == {"read_only": True}
            assert not binding.primary_key.columns
            assert not binding.foreign_key_constraints
            assert not binding.indexes
            continue
        primary = row["primary_key"]
        assert type(primary) is dict
        assert binding.primary_key.name == primary["name"]
        assert tuple(binding.primary_key.columns.keys()) == tuple(primary["columns"])

        foreign_rows = row["foreign_keys"]
        unique_rows = row["unique_constraints"]
        check_rows = row["check_constraints"]
        index_rows = row["indexes"]
        assert all(
            type(value) is list
            for value in (foreign_rows, unique_rows, check_rows, index_rows)
        )
        expected_foreign_keys += len(foreign_rows)
        expected_uniques += len(unique_rows)
        expected_checks += len(check_rows)
        expected_indexes += len(index_rows)

        expected_foreign_names = {_semantic(value)["name"] for value in foreign_rows}
        assert {
            value.name for value in binding.foreign_key_constraints
        } == expected_foreign_names
        expected_unique_names = {_semantic(value)["name"] for value in unique_rows}
        actual_unique_names = {
            value.name
            for value in binding.constraints
            if type(value).__name__ == "UniqueConstraint"
        }
        assert actual_unique_names == expected_unique_names
        expected_check_names = {value["name"] for value in check_rows}
        actual_check_names = {
            value.name
            for value in binding.constraints
            if type(value) is CheckConstraint
        }
        assert actual_check_names == expected_check_names
        assert {value.name for value in binding.indexes} == {
            _semantic(value)["name"] for value in index_rows
        }

    assert expected_foreign_keys == sum(
        len(table.foreign_key_constraints)
        for table in catalog.TABLES_BY_RELATION.values()
    )
    assert expected_uniques == sum(
        sum(type(value).__name__ == "UniqueConstraint" for value in table.constraints)
        for table in catalog.TABLES_BY_RELATION.values()
    )
    assert expected_checks == 519
    assert expected_checks == sum(
        sum(type(value) is CheckConstraint for value in table.constraints)
        for table in catalog.TABLES_BY_RELATION.values()
    )
    assert expected_indexes == sum(
        len(table.indexes) for table in catalog.TABLES_BY_RELATION.values()
    )


def test_catalog_source_contains_no_runtime_reflection_or_orm_relationship() -> None:
    source = CATALOG_PATH.read_text(encoding="utf-8")
    forbidden = (
        "autoload_with",
        "automap",
        "MetaData.reflect",
        "relationship(",
        "registry(",
        "create_engine(",
        "Engine(",
        "Session(",
        "postgresql://",
        "postgresql+psycopg://",
    )
    assert all(token not in source for token in forbidden)
    assert source.count("Final[Table] = Table(") == 104
    assert "info={'read_only': True}" in source
