#!/usr/bin/env python3
"""Build the deterministic cumulative ST-0305 database schema bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts import build_st0201_postgres_service as shared
    from scripts import build_st0304_domain_schemas as predecessor
except ModuleNotFoundError:
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]
    import build_st0304_domain_schemas as predecessor  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-0305/contracts/publication-analytics-finance.v1.yaml"
)
GUARD_PATH: Final = Path("changes/st-0305/contracts/physical/publishing-guards.sql")
UPSTREAM_CATALOG_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"
)
UPSTREAM_DESIGN_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"
)
README_PATH: Final = Path("changes/st-0305/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st0305_publication_analytics_finance.py")
REVISION_PATH: Final = Path(
    "migrations/versions/202608030005_publication_analytics_finance.py"
)
CATALOG_PATH: Final = Path(
    "changes/st-0305/generated/publication-analytics-finance-catalog.v1.json"
)
VALIDATION_PATH: Final = Path(
    "changes/st-0305/generated/publication-analytics-finance-validation.v1.sql"
)
MANIFEST_PATH: Final = Path("changes/st-0305/manifest.yaml")
PREDECESSOR_MANIFEST_PATH: Final = Path("changes/st-0304/manifest.yaml")
SUCCESSOR_CONTRACT_PATH: Final = Path(
    "changes/st-0306/contracts/database-roles-grants.v1.yaml"
)
GENERATED_PATHS: Final = (
    REVISION_PATH,
    CATALOG_PATH,
    VALIDATION_PATH,
    MANIFEST_PATH,
)

REVISION: Final = "202608030005"
DOWN_REVISION: Final = "202608030004"
RUNNER_VERSION: Final = "1.4.0"
EXPECTED_SERVER_VERSION_NUM: Final = 180004
EXPECTED_CONTRACT_SHA256: Final = (
    "2947fe100633a2611b9287c6530856b9679365bb10d4af4728a5148ed970377f"
)
EXPECTED_GUARD_SHA256: Final = (
    "d3ecd89ac35c386333ac2bf75907259aa28fc8718f65e8c303499193d57fe82e"
)
EXPECTED_UPSTREAM_CATALOG_SHA256: Final = (
    "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d"
)
EXPECTED_UPSTREAM_DESIGN_SHA256: Final = (
    "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
)
EXPECTED_PREDECESSOR_MANIFEST_SHA256: Final = (
    "5a3772b87591b90b5f698eaa86131a10b5d9767d93cc8e2be67340df4b310623"
)
OWN_STORY_FLAG: Final = "--own-story"
GENERATION_COMMAND: Final = (
    "uv run --frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st0305_publication_analytics_finance.py --own-story"
)

SCHEMAS: Final = ("publishing", "freshness", "analytics", "finance", "readmodel")
SCHEMA_COMMENTS: Final = {
    "publishing": "人間Review、Approval、Publication Snapshot、公開状態、Route、Rollback",
    "freshness": "鮮度SLA、Refresh、Staleness、Affiliate Link検査、影響分析",
    "analytics": "匿名行動、楽天クリック、GSC・GA4取込、帰属推定、日次指標",
    "finance": "成果原本取込、発生・確定・取消、費用配賦、確定ユニットエコノミクス",
    "readmodel": "公開Rendererが読む安全な再生成可能Projection",
}
EXPECTED_TABLES: Final = {
    "publishing": (
        "review_assignment",
        "review_decision",
        "approval",
        "publication_candidate",
        "publication_snapshot",
        "publication",
        "publication_event",
        "public_route",
        "rollback_record",
    ),
    "freshness": (
        "freshness_policy",
        "refresh_schedule",
        "refresh_run",
        "staleness_assessment",
        "link_check",
        "impact_assessment",
    ),
    "analytics": (
        "anonymous_event",
        "affiliate_click_event",
        "import_run",
        "gsc_observation",
        "ga4_observation",
        "attribution_estimate",
        "data_quality_finding",
        "daily_article_metric",
    ),
    "finance": (
        "parser_version",
        "revenue_import",
        "revenue_import_row",
        "commission",
        "commission_event",
        "external_cost",
        "human_work_log",
        "allocation_rule",
        "cost_allocation",
        "unit_economics_snapshot",
    ),
    "readmodel": (
        "public_article",
        "public_article_block",
        "public_product_card",
        "public_offer",
        "public_route",
        "runtime_control",
    ),
}
DEFERRED_FOREIGN_KEYS: Final = frozenset(
    {
        "fk_publishing_publication_event_release_id",
        "fk_publishing_rollback_record_incident_id",
    }
)
CYCLIC_FOREIGN_KEYS: Final = frozenset(
    {
        "fk_publishing_publication_candidate_publication_snapshot_id",
        "fk_publishing_publication_snapshot_publication_candidate_id",
        "fk_publishing_publication_current_route_id",
        "fk_publishing_public_route_publication_id",
    }
)
HARD_IMMUTABLE_TABLES: Final = (
    "publishing.review_decision",
    "publishing.publication_snapshot",
    "publishing.publication_event",
    "analytics.anonymous_event",
    "analytics.affiliate_click_event",
    "finance.commission_event",
    "finance.cost_allocation",
)
TOUCH_TABLES: Final = (
    "publishing.review_assignment",
    "publishing.publication_candidate",
    "publishing.publication",
    "publishing.public_route",
    "freshness.refresh_schedule",
    "finance.revenue_import",
    "finance.commission",
)
EXPECTED_INVENTORY: Final = {
    "schemas_created": 5,
    "tables": 39,
    "columns": 629,
    "not_null_constraints": 447,
    "primary_keys": 39,
    "named_unique_constraints": 47,
    "check_constraints": 172,
    "catalog_foreign_keys": 152,
    "installed_foreign_keys": 150,
    "standalone_indexes": 153,
    "total_indexes": 239,
    "functions": 3,
    "triggers": 17,
}
CATALOG_FINGERPRINTS: Final = {
    "relations": {"count": 39, "digest": "8b7c92be0f2fd5402a424d95eea5233a"},
    "columns": {"count": 629, "digest": "5b45839a79986b7f09e97d9c18ab2ebb"},
    "constraints": {"count": 855, "digest": "486df24518366f36689d83135245b0fa"},
    "indexes": {"count": 239, "digest": "caa0c0ba455c58af334ea02bd0afa319"},
    "functions": {"count": 3, "digest": "92c2ea81850bf9cb5357e173476705f7"},
    "triggers": {"count": 17, "digest": "abbe0bced5705576cfce1a2dc2e0e615"},
}
EXPECTED_PARTITIONING_METADATA: Final = frozenset(
    {
        "NONE_MVP",
        "MONTHLY RANGE occurred_at from inception",
        "RANGE assessed_at when >50M rows",
        "RANGE checked_at when >50M rows",
        "MONTHLY RANGE metric_date when >50M rows",
        "YEARLY RANGE metric_date when >50M rows",
        "HASH revenue_import_id only when operationally required",
        "YEARLY RANGE business_month when >50M rows",
        "YEARLY RANGE recorded_at when >50M rows",
        "YEARLY RANGE period_month when >50M rows",
    }
)

PINNED_INPUTS: Final = {
    UPSTREAM_CATALOG_PATH.as_posix(): EXPECTED_UPSTREAM_CATALOG_SHA256,
    UPSTREAM_DESIGN_PATH.as_posix(): "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md": "d05d1d4ebe3f3904e58c104e0b1836bc897377dbf27f9019f57c3fc6440bd137",
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    "docs/canonical/01_integration/RAOS_07_canonical_contract_overlay_v1.0.yaml": "f9080e1744096b743b2ada2261d2a023cebf310a08cf3a9fc2d14a53ac56cf3e",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0",
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460",
    "docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml": "b33049dc60814109b3a68c166c473f474789dd401a72116fe0a700aeeffb05fa",
    "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml": "29624996381ff0709c6499edcdca1109eb713ce56ad8b981df02153e11fc8b0c",
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml": "f1cad721ade082f588461ff58c415fa21786e30b85c8281e651476514e2560a2",
    "docs/canonical/03_analytics/RAOS_09_implementation_slices_v1.0.yaml": "2435c82eaaf7a43183b89b793e0b9ab1c7b4963cfcae5a240e5749a24bd7c13d",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, path: Path, label: str, limit: int = 16 * 1024 * 1024) -> bytes:
    return predecessor._secure_read(root, path, label, limit)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    return predecessor._mapping(value, label)


def _sequence(value: object, label: str) -> Sequence[Any]:
    return predecessor._sequence(value, label)


def _quote(value: str) -> str:
    return predecessor._quote_identifier(value)


def _table(schema: str, table: str) -> str:
    return predecessor._quoted_table(schema, table)


def _literal(value: str) -> str:
    return predecessor._sql_literal(value)


def _load_yaml(content: bytes, label: str) -> dict[str, Any]:
    return predecessor._load_yaml(content, label)


def _load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    content = _read(root, CONTRACT_PATH, "ST-0305 source contract")
    _require(
        _sha256(content) == EXPECTED_CONTRACT_SHA256, "source contract digest differs"
    )
    contract = _load_yaml(content, "ST-0305 source contract")
    document = _mapping(contract.get("document"), "contract document")
    story = _mapping(contract.get("story"), "contract story")
    precedence = _mapping(contract.get("source_precedence"), "source precedence")
    inventory = _mapping(contract.get("expected_inventory"), "expected inventory")
    catalog_fingerprints = _mapping(
        contract.get("catalog_fingerprints"), "catalog fingerprints"
    )
    _require(document.get("story_id") == "ST-0305", "contract story differs")
    _require(story.get("dependencies") == ["ST-0304"], "contract dependency differs")
    _require(story.get("open_decisions") == [], "contract has open decisions")
    _require(tuple(precedence.get("schemas", ())) == SCHEMAS, "schema order differs")
    _require(
        catalog_fingerprints.get("exact_server_version_num")
        == EXPECTED_SERVER_VERSION_NUM
        and catalog_fingerprints.get("algorithm") == "MD5_SORTED_UNIT_SEPARATOR_ROWS"
        and tuple(catalog_fingerprints.get("selected_schemas", ())) == SCHEMAS
        and _mapping(catalog_fingerprints.get("objects"), "fingerprint objects")
        == CATALOG_FINGERPRINTS,
        "catalog fingerprints differ",
    )
    contract_pins = {
        str(_mapping(item, "pinned input")["path"]): str(
            _mapping(item, "pinned input")["sha256"]
        )
        for item in _sequence(precedence.get("pinned_inputs"), "pinned inputs")
    }
    _require(contract_pins == PINNED_INPUTS, "contract pinned input closure differs")
    fragments = tuple(
        _mapping(item, "physical translation fragment")
        for item in _sequence(
            precedence.get("physical_translation_fragments"),
            "physical translation fragments",
        )
    )
    _require(
        len(fragments) == 1
        and fragments[0].get("path") == GUARD_PATH.as_posix()
        and fragments[0].get("sha256") == EXPECTED_GUARD_SHA256
        and fragments[0].get("role") == "PUBLICATION_GUARDS_AND_SELECTED_TRIGGERS",
        "physical translation fragment binding differs",
    )
    for key, expected in EXPECTED_INVENTORY.items():
        _require(inventory.get(key) == expected, f"expected inventory {key} differs")
    by_schema = _mapping(inventory.get("by_schema"), "inventory by schema")
    _require(tuple(by_schema) == SCHEMAS, "by-schema inventory order differs")
    aggregate_keys = {
        "tables": "tables",
        "columns": "columns",
        "not_null": "not_null_constraints",
        "primary_keys": "primary_keys",
        "unique": "named_unique_constraints",
        "checks": "check_constraints",
        "catalog_foreign_keys": "catalog_foreign_keys",
        "installed_foreign_keys": "installed_foreign_keys",
        "standalone_indexes": "standalone_indexes",
        "total_indexes": "total_indexes",
        "functions": "functions",
        "triggers": "triggers",
    }
    for schema_key, aggregate_key in aggregate_keys.items():
        observed = sum(
            int(_mapping(by_schema[schema], f"inventory {schema}").get(schema_key, 0))
            for schema in SCHEMAS
        )
        _require(
            observed == EXPECTED_INVENTORY[aggregate_key],
            f"by-schema {schema_key} total differs",
        )
    _require(
        set(_sequence(contract.get("hard_immutable_tables"), "hard immutable tables"))
        == set(HARD_IMMUTABLE_TABLES),
        "hard immutable tables differ",
    )
    _require(
        tuple(_sequence(contract.get("touch_tables"), "touch tables")) == TOUCH_TABLES,
        "touch tables differ",
    )
    return contract


def _load_selected_schemas(root: Path = REPO_ROOT) -> tuple[dict[str, Any], ...]:
    content = _read(root, UPSTREAM_CATALOG_PATH, "upstream data catalog")
    _require(
        _sha256(content) == EXPECTED_UPSTREAM_CATALOG_SHA256,
        "upstream catalog digest differs",
    )
    catalog = _load_yaml(content, "upstream data catalog")
    by_id = {
        str(_mapping(item, "upstream schema").get("id")): dict(
            _mapping(item, "upstream schema")
        )
        for item in _sequence(catalog.get("schemas"), "upstream schemas")
    }
    _require(
        all(schema in by_id for schema in SCHEMAS), "selected upstream schema missing"
    )
    selected = tuple(by_id[schema] for schema in SCHEMAS)
    for schema, expected_names in zip(selected, EXPECTED_TABLES.values(), strict=True):
        _require(
            schema.get("purpose") == SCHEMA_COMMENTS[schema["id"]],
            "schema purpose differs",
        )
        tables = _sequence(schema.get("tables"), "schema tables")
        _require(
            tuple(_mapping(table, "table")["name"] for table in tables)
            == expected_names,
            f"upstream table inventory {schema['id']} differs",
        )
    return selected


def _iter_tables(
    schemas: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    return tuple(
        (str(schema["id"]), _mapping(table, "table"))
        for schema in schemas
        for table in _sequence(schema.get("tables"), "tables")
    )


def validate_source_inputs(root: Path = REPO_ROOT) -> dict[str, int]:
    _load_contract(root)
    for path, digest in PINNED_INPUTS.items():
        _require(
            re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            f"pinned input digest is invalid: {path}",
        )
        _require(
            _sha256(_read(root, Path(path), "pinned input")) == digest,
            f"pinned input digest differs: {path}",
        )
    _require(
        _sha256(_read(root, GUARD_PATH, "guard SQL")) == EXPECTED_GUARD_SHA256,
        "guard SQL digest differs",
    )
    _require(
        _sha256(_read(root, PREDECESSOR_MANIFEST_PATH, "predecessor manifest"))
        == EXPECTED_PREDECESSOR_MANIFEST_SHA256,
        "predecessor manifest digest differs",
    )
    schemas = _load_selected_schemas(root)
    tables = _iter_tables(schemas)
    counts = Counter(
        {
            "schemas_created": len(schemas),
            "tables": len(tables),
            "columns": sum(
                len(_sequence(table["columns"], "columns")) for _, table in tables
            ),
            "not_null_constraints": sum(
                column.get("nullable") is False
                for _, table in tables
                for column in map(
                    lambda value: _mapping(value, "column"),
                    _sequence(table["columns"], "columns"),
                )
            ),
            "primary_keys": len(tables),
            "named_unique_constraints": sum(
                len(_sequence(table["unique_constraints"], "unique constraints"))
                for _, table in tables
            ),
            "check_constraints": sum(
                len(_sequence(table["check_constraints"], "check constraints"))
                for _, table in tables
            ),
            "catalog_foreign_keys": sum(
                len(_sequence(table["foreign_keys"], "foreign keys"))
                for _, table in tables
            ),
            "standalone_indexes": sum(
                len(_sequence(table["indexes"], "indexes")) for _, table in tables
            ),
        }
    )
    observed_deferred: set[str] = set()
    observed_cyclic: set[str] = set()
    names: set[str] = set()
    for schema, table in tables:
        name = str(table["name"])
        _require(
            table.get("fully_qualified_name") == f"{schema}.{name}", "table FQN differs"
        )
        _require(
            table.get("partitioning") in EXPECTED_PARTITIONING_METADATA,
            "partitioning metadata differs",
        )
        column_names = [
            str(_mapping(item, "column")["name"])
            for item in _sequence(table["columns"], "columns")
        ]
        _require(len(column_names) == len(set(column_names)), "duplicate column name")
        _require(tuple(table.get("primary_key", ())), "table primary key missing")
        for collection in (
            "unique_constraints",
            "check_constraints",
            "foreign_keys",
            "indexes",
        ):
            for item in _sequence(table[collection], collection):
                object_name = str(_mapping(item, collection).get("name"))
                _require(object_name not in names, "physical object name duplicated")
                names.add(object_name)
        for item in _sequence(table["foreign_keys"], "foreign keys"):
            foreign_key = _mapping(item, "foreign key")
            foreign_name = str(foreign_key["name"])
            if foreign_name in DEFERRED_FOREIGN_KEYS:
                observed_deferred.add(foreign_name)
            if foreign_key.get("deferrable") or foreign_key.get("initially_deferred"):
                _require(
                    foreign_key.get("deferrable") is True
                    and foreign_key.get("initially_deferred") is True,
                    "partially deferred foreign key",
                )
                observed_cyclic.add(foreign_name)
    _require(observed_deferred == set(DEFERRED_FOREIGN_KEYS), "deferred FK set differs")
    _require(observed_cyclic == set(CYCLIC_FOREIGN_KEYS), "cyclic FK set differs")
    counts["installed_foreign_keys"] = counts["catalog_foreign_keys"] - len(
        observed_deferred
    )
    counts["total_indexes"] = (
        counts["primary_keys"]
        + counts["named_unique_constraints"]
        + counts["standalone_indexes"]
    )
    for key, expected in EXPECTED_INVENTORY.items():
        if key in counts:
            _require(counts[key] == expected, f"source inventory {key} differs")

    guard = _read(root, GUARD_PATH, "guard SQL").decode("utf-8")
    _require(
        len(re.findall(r"(?m)^CREATE FUNCTION publishing\.", guard)) == 3,
        "publication guard function count differs",
    )
    _require(
        len(re.findall(r"(?m)^CREATE TRIGGER ", guard)) == 17, "trigger count differs"
    )
    _require("SECURITY DEFINER" not in guard, "security definer is forbidden")
    _require(
        "ops.kill_switch" in guard and "WHEN undefined_table" in guard,
        "kill-switch fail-closed guard differs",
    )
    counts["functions"] = 3
    counts["triggers"] = 17
    return dict(counts)


def _column_sql(column: Mapping[str, Any]) -> str:
    name = _quote(str(column["name"]))
    data_type = str(column["type"])
    _require(
        re.fullmatch(r"[a-z]+(?:\([0-9]+(?:,[0-9]+)?\))?", data_type) is not None,
        "column type is outside the approved scalar set",
    )
    pieces = [name, data_type]
    default = column.get("default")
    if default is not None:
        pieces.extend(("DEFAULT", str(default)))
    if column.get("nullable") is False:
        pieces.append("NOT NULL")
    return " ".join(pieces)


def _constraint_columns(value: object, label: str) -> str:
    columns = tuple(str(item) for item in _sequence(value, label))
    _require(columns, f"{label} is empty")
    return ", ".join(_quote(column) for column in columns)


def render_upgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    validate_source_inputs(root)
    schemas = _load_selected_schemas(root)
    tables = _iter_tables(schemas)
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL check_function_bodies = false;",
    ]
    for schema in SCHEMAS:
        statements.extend(
            (
                f"CREATE SCHEMA {_quote(schema)};",
                f"COMMENT ON SCHEMA {_quote(schema)} IS {_literal(SCHEMA_COMMENTS[schema])};",
                f"REVOKE ALL PRIVILEGES ON SCHEMA {_quote(schema)} FROM PUBLIC;",
            )
        )
    for schema, table in tables:
        table_name = str(table["name"])
        columns = tuple(
            _mapping(item, "column") for item in _sequence(table["columns"], "columns")
        )
        statements.append(
            f"CREATE TABLE {_table(schema, table_name)} (\n    "
            + ",\n    ".join(_column_sql(column) for column in columns)
            + "\n);"
        )
        statements.append(
            f"COMMENT ON TABLE {_table(schema, table_name)} IS {_literal(str(table['purpose']))};"
        )
        statements.extend(
            f"COMMENT ON COLUMN {_table(schema, table_name)}.{_quote(str(column['name']))} "
            f"IS {_literal(str(column['description']))};"
            for column in columns
        )
    for schema, table in tables:
        table_name = str(table["name"])
        target = _table(schema, table_name)
        statements.append(
            f"ALTER TABLE ONLY {target} ADD CONSTRAINT "
            f"{_quote(f'pk_{schema}_{table_name}')} PRIMARY KEY "
            f"({_constraint_columns(table['primary_key'], 'primary key')});"
        )
        for item in _sequence(table["unique_constraints"], "unique constraints"):
            unique = _mapping(item, "unique constraint")
            statements.append(
                f"ALTER TABLE ONLY {target} ADD CONSTRAINT {_quote(str(unique['name']))} "
                f"UNIQUE ({_constraint_columns(unique['columns'], 'unique columns')});"
            )
        for item in _sequence(table["check_constraints"], "check constraints"):
            check = _mapping(item, "check constraint")
            statements.append(
                f"ALTER TABLE ONLY {target} ADD CONSTRAINT {_quote(str(check['name']))} "
                f"CHECK ({str(check['expression'])});"
            )
    for schema, table in tables:
        target = _table(schema, str(table["name"]))
        for item in _sequence(table["foreign_keys"], "foreign keys"):
            foreign = _mapping(item, "foreign key")
            name = str(foreign["name"])
            if name in DEFERRED_FOREIGN_KEYS:
                continue
            reference_schema, reference_table = str(foreign["references"]).split(".", 1)
            statement = (
                f"ALTER TABLE ONLY {target} ADD CONSTRAINT {_quote(name)} FOREIGN KEY "
                f"({_constraint_columns(foreign['columns'], 'foreign key columns')}) "
                f"REFERENCES {_table(reference_schema, reference_table)} "
                f"({_constraint_columns(foreign['referenced_columns'], 'referenced columns')}) "
                f"ON DELETE {str(foreign['on_delete'])}"
            )
            if foreign.get("deferrable") is True:
                statement += " DEFERRABLE INITIALLY DEFERRED"
            statements.append(statement + ";")
    for schema, table in tables:
        target = _table(schema, str(table["name"]))
        for item in _sequence(table["indexes"], "indexes"):
            index = _mapping(item, "index")
            _require(index.get("method") == "btree", "non-btree index is outside scope")
            _require(
                index.get("expression") is None, "expression index is outside scope"
            )
            prefix = (
                "CREATE UNIQUE INDEX" if index.get("unique") is True else "CREATE INDEX"
            )
            statement = (
                f"{prefix} {_quote(str(index['name']))} ON {target} USING btree "
                f"({_constraint_columns(index['columns'], 'index columns')})"
            )
            include = tuple(
                str(value)
                for value in _sequence(index.get("include", ()), "index include")
            )
            if include:
                statement += (
                    f" INCLUDE ({', '.join(_quote(value) for value in include)})"
                )
            if index.get("nulls_not_distinct") is True:
                statement += " NULLS NOT DISTINCT"
            if index.get("where") is not None:
                statement += f" WHERE {str(index['where'])}"
            statements.append(statement + ";")
    guard = _read(root, GUARD_PATH, "guard SQL").decode("utf-8")
    statements.extend(predecessor._split_sql_statements(guard))
    statements.extend(
        (
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA "
            + ", ".join(_quote(schema) for schema in SCHEMAS)
            + " FROM PUBLIC;",
            "REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA "
            + ", ".join(_quote(schema) for schema in SCHEMAS)
            + " FROM PUBLIC;",
        )
    )
    joined = "\n".join(statements)
    _require(joined.count("CREATE TABLE ") == 39, "rendered table count differs")
    _require(joined.count(" FOREIGN KEY ") == 150, "rendered foreign key count differs")
    _require(
        len(re.findall(r"(?m)^CREATE (?:UNIQUE )?INDEX ", joined)) == 153,
        "rendered index count differs",
    )
    _require(
        len(re.findall(r"(?m)^CREATE FUNCTION publishing\.", joined)) == 3,
        "rendered function count differs",
    )
    _require(
        len(re.findall(r"(?m)^CREATE TRIGGER ", joined)) == 17,
        "rendered trigger count differs",
    )
    forbidden = (
        "CREATE ROLE",
        "CREATE POLICY",
        "GRANT ",
        "CREATE EXTENSION",
        "CREATE TYPE",
    )
    _require(not any(token in joined for token in forbidden), "forbidden SQL rendered")
    return tuple(statements)


def render_downgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    """Render an atomic fail-before-drop downgrade to the frozen ST-0304 head."""

    schemas = _load_selected_schemas(root)
    tables = _iter_tables(schemas)
    identities = tuple(_table(schema, str(table["name"])) for schema, table in tables)
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL lock_timeout = '5000ms';",
        "LOCK TABLE " + ", ".join(identities) + " IN ACCESS EXCLUSIVE MODE;",
    ]
    checks = "\n".join(
        f"    IF EXISTS (SELECT 1 FROM {identity} LIMIT 1) THEN\n"
        "        RAISE EXCEPTION USING ERRCODE = '55000', "
        "MESSAGE = 'ST0305_DOWNGRADE_NONEMPTY';\n"
        "    END IF;"
        for identity in identities
    )
    statements.append(
        "DO $raos_st0305_downgrade$\nBEGIN\n"
        + checks
        + "\nEND\n$raos_st0305_downgrade$;"
    )
    for schema, table in reversed(tables):
        target = _table(schema, str(table["name"]))
        for item in reversed(tuple(_sequence(table["foreign_keys"], "foreign keys"))):
            foreign = _mapping(item, "foreign key")
            name = str(foreign["name"])
            if name not in DEFERRED_FOREIGN_KEYS:
                statements.append(
                    f"ALTER TABLE ONLY {target} DROP CONSTRAINT {_quote(name)} RESTRICT;"
                )
    statements.append("DROP TABLE " + ", ".join(reversed(identities)) + " RESTRICT;")
    statements.extend(
        (
            "DROP FUNCTION publishing.guard_publication_transition() RESTRICT;",
            "DROP FUNCTION publishing.guard_publication_candidate() RESTRICT;",
            "DROP FUNCTION publishing.guard_final_approval() RESTRICT;",
        )
    )
    statements.extend(
        f"DROP SCHEMA {_quote(schema)} RESTRICT;" for schema in reversed(SCHEMAS)
    )
    joined = "\n".join(statements)
    _require(
        joined.count("ST0305_DOWNGRADE_NONEMPTY") == 39,
        "downgrade preflight count differs",
    )
    _require(
        joined.count(" DROP CONSTRAINT ") == 150, "downgrade foreign key count differs"
    )
    _require(" CASCADE" not in joined, "downgrade cascade is forbidden")
    return tuple(statements)


def _render_bytes_tuple(name: str, content: bytes) -> str:
    chunks = tuple(content[index : index + 80] for index in range(0, len(content), 80))
    _require(
        all(
            all(0x21 <= byte <= 0x7E and byte not in (0x22, 0x5C) for byte in chunk)
            for chunk in chunks
        ),
        "encoded payload is not safe for a double-quoted bytes literal",
    )
    return (
        f"{name}: tuple[bytes, ...] = (\n"
        + "".join(f'    b"{chunk.decode("ascii")}",\n' for chunk in chunks)
        + ")"
    )


def render_revision(root: Path = REPO_ROOT) -> bytes:
    """Render the bounded executable Alembic revision."""

    payload = json.dumps(
        {
            "upgrade": render_upgrade_statements(root),
            "downgrade": render_downgrade_statements(root),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload_sha256 = _sha256(payload)
    encoded = base64.b85encode(zlib.compress(payload, level=9))
    text = f'''"""Install the exact ST-0305 publication/analytics/finance contract.

Revision ID: {REVISION}
Revises: {DOWN_REVISION}
Create Date: 2026-08-05

RAOS metadata:
- story: ST-0305
- requirement IDs: FR-010, FR-013, FR-014, FR-015
- architecture: MIG-006 publishing-only plus MIG-007/MIG-008 physical slice
- runner version: {RUNNER_VERSION}
- server version: {EXPECTED_SERVER_VERSION_NUM}
- risk class: B (additive schemas, tables, constraints, indexes, functions, and triggers)
- estimated lock: additive catalog DDL; guarded ACCESS EXCLUSIVE on downgrade
- backfill job: none
- rollback category: reversible only while all 39 owned tables are empty; RESTRICT
- transaction: one PostgreSQL transaction for the complete Story revision
- rollback: lock and prove all 39 owned tables empty, then RESTRICT only
"""

from __future__ import annotations

import base64
import hashlib
import json
import zlib
from typing import Any

from alembic import op

revision: str = "{REVISION}"
down_revision: str | None = "{DOWN_REVISION}"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None
runner_version: str = "{RUNNER_VERSION}"
story_id: str = "ST-0305"
server_version_num: int = {EXPECTED_SERVER_VERSION_NUM}
_PAYLOAD_SHA256 = "{payload_sha256}"
_MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

{_render_bytes_tuple("_PAYLOAD_B85", encoded)}


def _decode_payload() -> tuple[tuple[str, ...], tuple[str, ...]]:
    compressed = base64.b85decode(b"".join(_PAYLOAD_B85))
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, _MAX_PAYLOAD_BYTES + 1)
    if decompressor.unconsumed_tail or not decompressor.eof or decompressor.unused_data:
        raise RuntimeError("ST0305_PAYLOAD_COMPRESSION_INVALID")
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise RuntimeError("ST0305_PAYLOAD_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != _PAYLOAD_SHA256:
        raise RuntimeError("ST0305_PAYLOAD_DIGEST_MISMATCH")
    value: Any = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {{"upgrade", "downgrade"}}:
        raise RuntimeError("ST0305_PAYLOAD_SHAPE_INVALID")
    upgrade = value["upgrade"]
    downgrade = value["downgrade"]
    if (
        not isinstance(upgrade, list)
        or not isinstance(downgrade, list)
        or not all(isinstance(item, str) for item in (*upgrade, *downgrade))
    ):
        raise RuntimeError("ST0305_PAYLOAD_STATEMENTS_INVALID")
    return tuple(upgrade), tuple(downgrade)


UPGRADE_STATEMENTS, DOWNGRADE_STATEMENTS = _decode_payload()


def _execute(statements: tuple[str, ...]) -> None:
    connection = op.get_bind().execution_options(no_parameters=True)
    for statement in statements:
        connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute(UPGRADE_STATEMENTS)


def downgrade() -> None:
    _execute(DOWNGRADE_STATEMENTS)
'''
    content = text.encode("utf-8")
    _require(len(content) <= 256 * 1024, "revision exceeds size limit")
    compile(content, REVISION_PATH.as_posix(), "exec")
    return content


def _guard_inventory(root: Path = REPO_ROOT) -> dict[str, list[str]]:
    guard = _read(root, GUARD_PATH, "guard SQL").decode("utf-8")
    return {
        "functions": re.findall(r"(?m)^CREATE FUNCTION ([a-z0-9_.]+)\(\)", guard),
        "triggers": re.findall(r"(?m)^CREATE TRIGGER ([a-z0-9_]+)", guard),
    }


def render_catalog(
    root: Path,
    contract: Mapping[str, Any],
    revision: bytes,
    validation: bytes,
) -> bytes:
    """Render the deep machine-readable Story catalog."""

    schemas = _load_selected_schemas(root)
    inventory = _guard_inventory(root)
    document = {
        "document": {
            "id": "RAOS-PUBLICATION-ANALYTICS-FINANCE-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0305",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "source": {
            "path": f"repo://{UPSTREAM_CATALOG_PATH.as_posix()}",
            "sha256": EXPECTED_UPSTREAM_CATALOG_SHA256,
            "translation": "EXACT_SELECTED_MACHINE_METADATA_TO_UNPARTITIONED_MVP_DDL",
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "path": f"repo://{REVISION_PATH.as_posix()}",
            "sha256": _sha256(revision),
        },
        "validation": {
            "path": f"repo://{VALIDATION_PATH.as_posix()}",
            "sha256": _sha256(validation),
        },
        "expected_inventory": dict(
            _mapping(contract["expected_inventory"], "expected inventory")
        ),
        "catalog_fingerprints": dict(
            _mapping(contract["catalog_fingerprints"], "catalog fingerprints")
        ),
        "baseline_metadata": {
            "schema_count": len(schemas),
            "table_count": sum(
                len(_sequence(schema["tables"], "tables")) for schema in schemas
            ),
            "column_count": sum(
                len(_sequence(table["columns"], "columns"))
                for schema in schemas
                for table in map(
                    lambda value: _mapping(value, "table"),
                    _sequence(schema["tables"], "tables"),
                )
            ),
            "schemas": list(schemas),
        },
        "foreign_key_boundary": {
            "catalog_count": 152,
            "installed_count": 150,
            "deferred_absent_target_names": sorted(DEFERRED_FOREIGN_KEYS),
            "cyclic_deferrable_initially_deferred_names": sorted(CYCLIC_FOREIGN_KEYS),
        },
        "guard_surface": {
            **inventory,
            "touch_tables": list(TOUCH_TABLES),
            "hard_immutable_tables": list(HARD_IMMUTABLE_TABLES),
            "public_execute": "REVOKED",
            "kill_switch_absence": "FAIL_CLOSED",
        },
        "boundary": dict(_mapping(contract["boundary"], "boundary")),
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _values(rows: Sequence[Sequence[object]]) -> str:
    return predecessor._values(rows)


def _render_catalog_fingerprint_validation() -> str:
    expected_rows = [
        (kind, value["count"], value["digest"])
        for kind, value in CATALOG_FINGERPRINTS.items()
    ]
    return f"""
    WITH selected(schema_name) AS (
        SELECT pg_catalog.unnest(ARRAY[
            {", ".join(_literal(schema) for schema in SCHEMAS)}
        ]::pg_catalog.text[])
    ),
    relation_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   relation.relkind, relation.relpersistence,
                   relation.relreplident, relation.relrowsecurity,
                   relation.relforcerowsecurity,
                   COALESCE(
                       pg_catalog.array_to_string(relation.reloptions, E'\\x1d'),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(relation.oid, 'pg_class'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE relation.relkind IN ('r', 'v')
    ),
    column_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   attribute.attnum, attribute.attname,
                   pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
                   attribute.attnotnull, attribute.attidentity,
                   attribute.attgenerated, attribute.attisdropped,
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           attribute_default.adbin,
                           attribute_default.adrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       collation_namespace.nspname || '.'
                       || collation_record.collname,
                       '<NULL>'
                   ),
                   attribute.attstorage, attribute.attcompression,
                   attribute.attstattarget,
                   COALESCE(
                       pg_catalog.col_description(
                           relation.oid, attribute.attnum
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = relation.oid AND attribute.attnum > 0
        LEFT JOIN pg_catalog.pg_attrdef AS attribute_default
          ON attribute_default.adrelid = relation.oid
         AND attribute_default.adnum = attribute.attnum
        LEFT JOIN pg_catalog.pg_collation AS collation_record
          ON collation_record.oid = attribute.attcollation
        LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
          ON collation_namespace.oid = collation_record.collnamespace
        WHERE relation.relkind = 'r'
    ),
    constraint_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   constraint_record.conname, constraint_record.contype,
                   constraint_record.condeferrable,
                   constraint_record.condeferred,
                   constraint_record.convalidated,
                   constraint_record.connoinherit,
                   constraint_record.confmatchtype,
                   constraint_record.confupdtype,
                   constraint_record.confdeltype,
                   COALESCE(
                       pg_catalog.pg_get_constraintdef(
                           constraint_record.oid, false
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        WHERE constraint_record.contype IN ('c', 'f', 'n', 'p', 'u')
    ),
    index_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, table_record.relname,
                   index_record.relname, index_catalog.indisunique,
                   index_catalog.indisprimary, index_catalog.indisexclusion,
                   index_catalog.indimmediate, index_catalog.indisclustered,
                   index_catalog.indisvalid, index_catalog.indisready,
                   index_catalog.indislive, index_catalog.indisreplident,
                   index_catalog.indnullsnotdistinct,
                   index_catalog.indnkeyatts, index_catalog.indnatts,
                   index_catalog.indkey::pg_catalog.text,
                   index_catalog.indcollation::pg_catalog.text,
                   index_catalog.indclass::pg_catalog.text,
                   index_catalog.indoption::pg_catalog.text,
                   pg_catalog.pg_get_indexdef(index_record.oid, 0, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indpred, index_catalog.indrelid, false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           index_catalog.indexprs, index_catalog.indrelid, false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(index_record.oid, 'pg_class'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_index AS index_catalog
        JOIN pg_catalog.pg_class AS index_record
          ON index_record.oid = index_catalog.indexrelid
        JOIN pg_catalog.pg_class AS table_record
          ON table_record.oid = index_catalog.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_record.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
    ),
    function_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_function_result(routine.oid),
                   language_record.lanname, routine.provolatile,
                   routine.proisstrict, routine.prosecdef,
                   routine.proleakproof, routine.proparallel,
                   COALESCE(
                       pg_catalog.array_to_string(routine.proconfig, E'\\x1d'),
                       '<NULL>'
                   ),
                   pg_catalog.pg_get_functiondef(routine.oid),
                   COALESCE(
                       pg_catalog.obj_description(routine.oid, 'pg_proc'),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_language AS language_record
          ON language_record.oid = routine.prolang
        WHERE routine.prokind = 'f'
    ),
    trigger_rows AS (
        SELECT pg_catalog.concat_ws(
                   E'\\x1f', namespace.nspname, relation.relname,
                   trigger_record.tgname, trigger_record.tgtype,
                   trigger_record.tgenabled, trigger_record.tgisinternal,
                   routine_namespace.nspname, routine.proname,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_triggerdef(trigger_record.oid, false),
                   COALESCE(
                       pg_catalog.pg_get_expr(
                           trigger_record.tgqual,
                           trigger_record.tgrelid,
                           false
                       ),
                       '<NULL>'
                   ),
                   COALESCE(
                       pg_catalog.obj_description(
                           trigger_record.oid, 'pg_trigger'
                       ),
                       '<NULL>'
                   )
               ) AS row_value
        FROM pg_catalog.pg_trigger AS trigger_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_record.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN selected ON selected.schema_name = namespace.nspname
        JOIN pg_catalog.pg_proc AS routine
          ON routine.oid = trigger_record.tgfoid
        JOIN pg_catalog.pg_namespace AS routine_namespace
          ON routine_namespace.oid = routine.pronamespace
        WHERE trigger_record.tgisinternal IS FALSE
    ),
    observed(kind, object_count, digest) AS (
        SELECT 'relations', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM relation_rows
        UNION ALL
        SELECT 'columns', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM column_rows
        UNION ALL
        SELECT 'constraints', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM constraint_rows
        UNION ALL
        SELECT 'indexes', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM index_rows
        UNION ALL
        SELECT 'functions', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM function_rows
        UNION ALL
        SELECT 'triggers', pg_catalog.count(*),
               pg_catalog.md5(pg_catalog.string_agg(
                   row_value, E'\\x1e' ORDER BY row_value
               ))
        FROM trigger_rows
    ),
    expected(kind, object_count, digest) AS (VALUES
        {_values(expected_rows)}
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    FULL JOIN observed USING (kind)
    WHERE observed.kind IS NULL OR expected.kind IS NULL
       OR observed.object_count IS DISTINCT FROM expected.object_count
       OR observed.digest IS DISTINCT FROM expected.digest;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0305_CATALOG_FINGERPRINT_MISMATCH';
    END IF;
"""


def render_validation_sql(
    root: Path,
    contract: Mapping[str, Any],
    revision_sha256: str,
) -> bytes:
    """Render exact PostgreSQL 18.4 post-deploy validation SQL."""

    del contract
    schemas = _load_selected_schemas(root)
    tables = _iter_tables(schemas)
    schema_rows = [(schema, SCHEMA_COMMENTS[schema]) for schema in SCHEMAS]
    table_rows = [
        (schema, str(table["name"]), str(table["purpose"])) for schema, table in tables
    ]
    column_rows = [
        (schema, str(table["name"]), str(column["name"]), str(column["description"]))
        for schema, table in tables
        for column in map(
            lambda value: _mapping(value, "column"),
            _sequence(table["columns"], "columns"),
        )
    ]
    trigger_names = _guard_inventory(root)["triggers"]
    catalog_fingerprint_validation = _render_catalog_fingerprint_validation()
    sql_text = f"""-- Generated by {GENERATOR_PATH.as_posix()}; do not edit.
-- Story ST-0305 local candidate validation for exact PostgreSQL 18.4.
SET search_path = pg_catalog;
SET TIME ZONE 'UTC';

DO $raos_st0305_validation$
DECLARE
    mismatch_count bigint;
    inventory record;
BEGIN
    IF pg_catalog.current_setting('server_version_num') <> '{EXPECTED_SERVER_VERSION_NUM}' THEN
        RAISE EXCEPTION 'ST0305_SERVER_VERSION_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.count(*) FROM public.raos_migration_version) <> 1
       OR (SELECT pg_catalog.max(version_num) FROM public.raos_migration_version)
          IS DISTINCT FROM '{REVISION}' THEN
        RAISE EXCEPTION 'ST0305_REVISION_MISMATCH';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.raos_migration_history
        WHERE revision_id = '{REVISION}' AND story_id = 'ST-0305'
          AND direction = 'UPGRADE' AND status = 'SUCCEEDED'
          AND runner_version = '{RUNNER_VERSION}'
          AND server_version_num = {EXPECTED_SERVER_VERSION_NUM}
          AND source_sha256 = '{revision_sha256}'
    ) THEN
        RAISE EXCEPTION 'ST0305_HISTORY_MISMATCH';
    END IF;

    WITH selected AS (
        SELECT oid FROM pg_catalog.pg_namespace
        WHERE nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
    )
    SELECT
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class
         WHERE relnamespace IN (SELECT oid FROM selected) AND relkind = 'r'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS attribute
         JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
         WHERE relation.relnamespace IN (SELECT oid FROM selected)
           AND relation.relkind = 'r' AND attribute.attnum > 0
           AND attribute.attisdropped IS FALSE),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS attribute
         JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
         WHERE relation.relnamespace IN (SELECT oid FROM selected)
           AND relation.relkind = 'r' AND attribute.attnum > 0
           AND attribute.attisdropped IS FALSE AND attribute.attnotnull IS TRUE),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
         WHERE connamespace IN (SELECT oid FROM selected) AND contype = 'p'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
         WHERE connamespace IN (SELECT oid FROM selected) AND contype = 'u'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
         WHERE connamespace IN (SELECT oid FROM selected) AND contype = 'c'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
         WHERE connamespace IN (SELECT oid FROM selected) AND contype = 'f'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_index AS index_record
         JOIN pg_catalog.pg_class AS relation ON relation.oid = index_record.indrelid
         WHERE relation.relnamespace IN (SELECT oid FROM selected)
           AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint
                           WHERE conindid = index_record.indexrelid)),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_index AS index_record
         JOIN pg_catalog.pg_class AS relation ON relation.oid = index_record.indrelid
         WHERE relation.relnamespace IN (SELECT oid FROM selected)),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc
         WHERE pronamespace IN (SELECT oid FROM selected) AND prokind = 'f'),
        (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger AS trigger_record
         JOIN pg_catalog.pg_class AS relation ON relation.oid = trigger_record.tgrelid
         WHERE relation.relnamespace IN (SELECT oid FROM selected)
           AND trigger_record.tgisinternal IS FALSE)
    INTO inventory;
    IF inventory <> ROW(39::bigint, 629::bigint, 447::bigint, 39::bigint,
                         47::bigint, 172::bigint, 150::bigint, 153::bigint,
                         239::bigint, 3::bigint, 17::bigint) THEN
        RAISE EXCEPTION 'ST0305_INVENTORY_MISMATCH';
    END IF;

{catalog_fingerprint_validation}

    WITH expected(schema_name, description) AS (VALUES
        {_values(schema_rows)}
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    LEFT JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    WHERE namespace.oid IS NULL
       OR pg_catalog.pg_get_userbyid(namespace.nspowner)
          IS DISTINCT FROM current_user
       OR pg_catalog.obj_description(namespace.oid, 'pg_namespace')
          IS DISTINCT FROM expected.description
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.aclexplode(
               COALESCE(
                   namespace.nspacl,
                   pg_catalog.acldefault('n', namespace.nspowner)
               )
           ) AS acl
           WHERE acl.grantee <> namespace.nspowner
       );
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0305_SCHEMA_COMMENT_MISMATCH';
    END IF;

    WITH expected(schema_name, table_name, description) AS (VALUES
        {_values(table_rows)}
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    LEFT JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    LEFT JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name AND relation.relkind = 'r'
    WHERE relation.oid IS NULL
       OR pg_catalog.obj_description(relation.oid, 'pg_class')
          IS DISTINCT FROM expected.description;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0305_TABLE_COMMENT_MISMATCH';
    END IF;

    WITH expected(schema_name, table_name, column_name, description) AS (VALUES
        {_values(column_rows)}
    )
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM expected
    LEFT JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    LEFT JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name AND relation.relkind = 'r'
    LEFT JOIN pg_catalog.pg_attribute AS attribute
      ON attribute.attrelid = relation.oid
     AND attribute.attname = expected.column_name
     AND attribute.attnum > 0 AND attribute.attisdropped IS FALSE
    WHERE attribute.attnum IS NULL
       OR pg_catalog.col_description(relation.oid, attribute.attnum)
          IS DISTINCT FROM expected.description;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0305_COLUMN_COMMENT_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = ANY(ARRAY[{", ".join(_literal(name) for name in sorted(DEFERRED_FOREIGN_KEYS | {"fk_iam_break_glass_record_incident_id"}))}])
    ) THEN
        RAISE EXCEPTION 'ST0305_DEFERRED_FOREIGN_KEY_MISMATCH';
    END IF;
    IF (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_constraint
        WHERE conname = ANY(ARRAY[{", ".join(_literal(name) for name in sorted(CYCLIC_FOREIGN_KEYS))}])
          AND contype = 'f' AND condeferrable IS TRUE AND condeferred IS TRUE
    ) <> 4 THEN
        RAISE EXCEPTION 'ST0305_CYCLIC_FOREIGN_KEY_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(relation.relacl, pg_catalog.acldefault('r', relation.relowner))
        ) AS acl
        WHERE namespace.nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
          AND relation.relkind IN ('r','v') AND acl.grantee <> relation.relowner
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(routine.proacl, pg_catalog.acldefault('f', routine.proowner))
        ) AS acl
        WHERE namespace.nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
          AND acl.grantee <> routine.proowner
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_default_acl AS default_acl
        LEFT JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = default_acl.defaclnamespace
        WHERE default_acl.defaclnamespace = 0
           OR namespace.nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
    ) THEN
        RAISE EXCEPTION 'ST0305_PUBLIC_OR_DEFAULT_ACL_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
          AND relation.relkind = 'r'
          AND (relation.relrowsecurity IS TRUE OR relation.relforcerowsecurity IS TRUE)
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_policy AS policy_record
        JOIN pg_catalog.pg_class AS relation ON relation.oid = policy_record.polrelid
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(ARRAY[{", ".join(_literal(schema) for schema in SCHEMAS)}])
    ) THEN
        RAISE EXCEPTION 'ST0305_RLS_BOUNDARY_MISMATCH';
    END IF;

    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger
        WHERE tgname = ANY(ARRAY[{", ".join(_literal(name) for name in trigger_names)}])
          AND tgisinternal IS FALSE) <> 17 THEN
        RAISE EXCEPTION 'ST0305_TRIGGER_IDENTITY_MISMATCH';
    END IF;
END
$raos_st0305_validation$;

SELECT 'PASS'::pg_catalog.text AS status,
       39::pg_catalog.int4 AS tables,
       629::pg_catalog.int4 AS columns,
       150::pg_catalog.int4 AS installed_foreign_keys,
       17::pg_catalog.int4 AS triggers;
"""
    return sql_text.encode("utf-8")


CURRENT_SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    GUARD_PATH,
    *(Path(path) for path in PINNED_INPUTS),
    README_PATH,
    Path("README.md"),
    Path("Makefile"),
    Path("docs/execplans/ST-0305.md"),
    Path("docs/worklogs/ST-0305.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0304_domain_schemas.py"),
    PREDECESSOR_MANIFEST_PATH,
    Path("migrations/versions/202608030004_domain_schemas.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/runner.py"),
    Path("scripts/build_st0201_postgres_service.py"),
    Path("tests/postgresql18.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("tests/st0301/test_catalog.py"),
    Path("tests/st0301/test_cli.py"),
    Path("tests/st0301/test_contract.py"),
    Path("tests/st0301/test_generation.py"),
    Path("tests/st0301/test_postgresql.py"),
    Path("tests/st0302/test_contract.py"),
    Path("tests/st0302/test_revision.py"),
    Path("tests/st0302/test_postgresql.py"),
    Path("tests/st0303/test_generation.py"),
    Path("tests/st0303/test_postgresql.py"),
    Path("tests/st0304/test_generation.py"),
    Path("tests/st0304/test_postgresql.py"),
    Path("tests/st0305/conftest.py"),
    Path("tests/st0305/test_postgresql.py"),
    Path("tests/st0305/test_st0305_publication_analytics_finance.py"),
)


def _artifact(root: Path, path: Path) -> dict[str, object]:
    content = _read(root, path, "source artifact")
    return {
        "uri": f"repo://{path.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(
    root: Path,
    contract: Mapping[str, Any],
    outputs: Mapping[Path, bytes],
) -> bytes:
    """Render the complete current-Story source and generated hash closure."""

    _require(
        len(CURRENT_SOURCE_ARTIFACT_PATHS) == len(set(CURRENT_SOURCE_ARTIFACT_PATHS)),
        "source artifact inventory contains duplicates",
    )
    source_artifacts = [_artifact(root, path) for path in CURRENT_SOURCE_ARTIFACT_PATHS]
    generated_artifacts = [
        {
            "uri": f"repo://{path.as_posix()}",
            "bytes": len(outputs[path]),
            "sha256": _sha256(outputs[path]),
        }
        for path in GENERATED_PATHS
        if path != MANIFEST_PATH
    ]
    document = {
        "document": {
            "id": "RAOS-PUBLICATION-ANALYTICS-FINANCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0305",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "canonical_and_upstream_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in PINNED_INPUTS.items()
            ],
            "predecessor_manifest": {
                "story_id": "ST-0304",
                "uri": f"repo://{PREDECESSOR_MANIFEST_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_MANIFEST_SHA256,
            },
            "translation": {
                "source": "PINNED_MACHINE_CATALOG_SELECTED_SCHEMAS",
                "physical_mode": "ORDINARY_UNPARTITIONED_MVP_TABLES",
                "guard_fragment": f"repo://{GUARD_PATH.as_posix()}",
                "guard_sha256": EXPECTED_GUARD_SHA256,
            },
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "single_transaction": True,
            "maximum_revision_bytes": 256 * 1024,
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "inventory": dict(
            _mapping(contract["expected_inventory"], "expected inventory")
        ),
        "catalog_fingerprints": dict(
            _mapping(contract["catalog_fingerprints"], "catalog fingerprints")
        ),
        "security_boundary": {
            "public_privileges": "NONE",
            "public_function_execute": "REVOKED",
            "roles_or_default_privileges_created": False,
            "rls_policies_created": False,
            "hard_immutable_tables": list(HARD_IMMUTABLE_TABLES),
            "publication_kill_switch_absence": "FAIL_CLOSED",
        },
        "foreign_key_boundary": {
            "catalog_count": 152,
            "installed_count": 150,
            "deferred_absent_target_names": sorted(DEFERRED_FOREIGN_KEYS),
            "cyclic_deferrable_initially_deferred_names": sorted(CYCLIC_FOREIGN_KEYS),
        },
        "boundary": {
            **dict(_mapping(contract["boundary"], "boundary")),
            "source_inventory_status": "FINAL_CURRENT_STORY_CLOSURE",
            "future_source_change_requires_regeneration": True,
        },
    }
    return yaml.dump(
        document,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    """Render the complete generated bundle in memory before mutation."""

    validate_source_inputs(root)
    contract = _load_contract(root)
    revision = render_revision(root)
    validation = render_validation_sql(root, contract, _sha256(revision))
    catalog = render_catalog(root, contract, revision, validation)
    outputs: dict[Path, bytes] = {
        REVISION_PATH: revision,
        CATALOG_PATH: catalog,
        VALIDATION_PATH: validation,
    }
    outputs[MANIFEST_PATH] = render_manifest(root, contract, outputs)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output order differs")
    return outputs


def install_generated(root: Path = REPO_ROOT) -> None:
    """Atomically stage the entire generated bundle before committing it."""

    outputs = render_outputs(root)
    staged: list[predecessor._StagedOutput] = []
    try:
        for ordinal, path in enumerate(GENERATED_PATHS):
            staged.append(predecessor._stage_output(root, path, outputs[path], ordinal))
        try:
            for stage in staged:
                predecessor._verify_stage_target_unchanged(stage)
                os.replace(
                    stage.temporary_name,
                    stage.relative.name,
                    src_dir_fd=stage.parent_descriptor,
                    dst_dir_fd=stage.parent_descriptor,
                )
                stage.temporary_name = ""
                stage.committed = True
                os.fsync(stage.parent_descriptor)
        except BaseException as install_error:
            rollback_errors: list[BaseException] = []
            for ordinal, stage in enumerate(reversed(staged)):
                if not stage.committed:
                    continue
                try:
                    predecessor._restore_output(stage, ordinal)
                except BaseException as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise RuntimeError(
                    "generated bundle rollback incomplete"
                ) from install_error
            raise
    finally:
        for stage in staged:
            if stage.temporary_name:
                try:
                    os.unlink(stage.temporary_name, dir_fd=stage.parent_descriptor)
                except FileNotFoundError:
                    pass
            for descriptor in reversed(stage.descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def check_generated(root: Path = REPO_ROOT) -> None:
    """Compare every committed artifact with a fresh deterministic render."""

    expected = render_outputs(root)
    for path in GENERATED_PATHS:
        observed = _read(root, path, "generated artifact", 8 * 1024 * 1024)
        _require(observed == expected[path], f"generated artifact drift: {path}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        OWN_STORY_FLAG,
        action="store_true",
        help="operate ST-0305 outputs instead of delegating to the successor",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify generated outputs")
    mode.add_argument(
        "--source-check", action="store_true", help="validate only frozen sources"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    dispatch_arguments = sys.argv[1:] if argv is None else argv
    if (
        OWN_STORY_FLAG not in dispatch_arguments
        and (REPO_ROOT / SUCCESSOR_CONTRACT_PATH).is_file()
    ):
        try:
            from scripts import build_st0306_database_roles as successor
        except ModuleNotFoundError:
            import build_st0306_database_roles as successor  # type: ignore[no-redef]

        return successor.main(argv)
    arguments = parse_arguments(argv)
    try:
        if arguments.source_check:
            summary = validate_source_inputs()
            mode = "source-check"
        elif arguments.check:
            check_generated()
            summary = {"generated_artifacts": len(GENERATED_PATHS)}
            mode = "check"
        else:
            install_generated()
            summary = {"generated_artifacts": len(GENERATED_PATHS)}
            mode = "install"
    except (OSError, RuntimeError, UnicodeError, ValueError, yaml.YAMLError) as error:
        print(f"ST-0305 generation failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "PASS", "story_id": "ST-0305", "mode": mode, **summary},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
