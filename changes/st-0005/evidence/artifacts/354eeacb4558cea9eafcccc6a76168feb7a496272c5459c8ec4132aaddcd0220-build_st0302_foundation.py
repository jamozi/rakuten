#!/usr/bin/env python3
"""Validate ST-0302 and build its reversible foundation migration bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
from typing import Any, Final, cast

import yaml

try:
    from scripts import build_st0201_postgres_service as shared
    from scripts import build_st0301_migration_framework as framework
except ModuleNotFoundError:
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]
    import build_st0301_migration_framework as framework  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0302/contracts/foundation-schema.v1.yaml")
README_PATH: Final = Path("changes/st-0302/README.md")
EXECPLAN_PATH: Final = Path("docs/execplans/ST-0302.md")
WORKLOG_PATH: Final = Path("docs/worklogs/ST-0302.md")
GENERATOR_PATH: Final = Path("scripts/build_st0302_foundation.py")
REVISION_PATH: Final = Path("migrations/versions/202608030002_foundation_schemas.py")
VALIDATION_PATH: Final = Path(
    "changes/st-0302/generated/foundation-baseline-validation.v1.sql"
)
CATALOG_PATH: Final = Path("changes/st-0302/generated/foundation-catalog.v1.json")
MANIFEST_PATH: Final = Path("changes/st-0302/manifest.yaml")
PREDECESSOR_PATH: Final = Path("changes/st-0301/manifest.yaml")
GENERATED_PATHS: Final = (
    REVISION_PATH,
    VALIDATION_PATH,
    CATALOG_PATH,
    MANIFEST_PATH,
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python scripts/build_st0302_foundation.py"
)

PINNED_INPUTS: Final = {
    "docs/manifest.json": "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml": "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d",
    "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md": "d05d1d4ebe3f3904e58c104e0b1836bc897377dbf27f9019f57c3fc6440bd137",
    "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml": "2cdc9afb4b9a1fc7cb44b78dc5198bc443a219ca895713b75220f8625aea6305",
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md": "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3",
    "docs/canonical/08_codex/prompts/02_database_migration.md": "753a5301ad3aac43dd1954e6e9f7ecc777aaf5c21979a6037f33ae5da72ee160",
    "docs/canonical/08_codex/PLANS.md": "e8ff1bd1ac181380e9bff2bcbd27aeddcadf0858692bc666b08cb8f9c4d7f84a",
}

# Updated once after the shared graph source freeze.
EXPECTED_PREDECESSOR_SHA256: Final = (
    "287d1f365523f39bb7b28535680317103cb6abad5d5b3f5e4db4bc60250eb2ff"
)

SOURCE_ARTIFACT_PATHS: Final = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
    CONTRACT_PATH,
    README_PATH,
    EXECPLAN_PATH,
    WORKLOG_PATH,
    GENERATOR_PATH,
    Path("scripts/build_st0201_postgres_service.py"),
    Path("scripts/build_st0301_migration_framework.py"),
    Path("changes/st-0301/contracts/migration-framework.v1.yaml"),
    Path("changes/st-0301/README.md"),
    Path("migrations/FRAMEWORK.md"),
    Path("migrations/env.py"),
    Path("migrations/script.py.mako"),
    Path("migrations/versions/202608030001_framework_install_history.py"),
    Path("python/raos/__init__.py"),
    Path("python/raos/migrations/__init__.py"),
    Path("python/raos/migrations/__main__.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/cli.py"),
    Path("python/raos/migrations/runner.py"),
    Path("tests/conftest.py"),
    Path("tests/st0102/test_commands_and_docs.py"),
    Path("tests/st0301/conftest.py"),
    Path("tests/st0301/test_catalog.py"),
    Path("tests/st0301/test_cli.py"),
    Path("tests/st0301/test_contract.py"),
    Path("tests/st0301/test_generation.py"),
    Path("tests/st0301/test_postgresql.py"),
    Path("tests/st0301/test_runner.py"),
    Path("tests/postgresql18.py"),
    Path("tests/st0302/conftest.py"),
    Path("tests/st0302/test_contract.py"),
    Path("tests/st0302/test_generation.py"),
    Path("tests/st0302/test_postgresql.py"),
    Path("tests/st0302/test_revision.py"),
    Path("pyrightconfig.json"),
    Path("Makefile"),
    Path("README.md"),
    PREDECESSOR_PATH,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def _exact_value(actual: object, expected: object) -> bool:
    """Compare YAML contract values without Python's bool/int coercion."""

    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping) or set(actual) != set(expected):
            return False
        return all(_exact_value(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _exact_value(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _regular_file(root: Path, relative: Path, label: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"{label} path is unsafe")
    root_metadata = root.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError(f"{label} root is unsafe")
    expected = root.absolute() / relative
    try:
        resolved = expected.resolve(strict=True)
        metadata = expected.lstat()
    except OSError:
        raise RuntimeError(f"{label} is missing") from None
    if (
        resolved != expected.absolute()
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise RuntimeError(f"{label} is not a regular file")
    return expected


def _load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    value = shared.load_yaml(_regular_file(root, CONTRACT_PATH, "ST-0302 contract"))
    contract = dict(_mapping(value, "ST-0302 contract"))
    _require(
        set(contract)
        == {
            "document",
            "story",
            "scope_precedence",
            "database",
            "schemas",
            "extensions",
            "types",
            "uuidv7",
            "revision",
            "validation",
            "downgrade",
            "security",
            "verification",
            "boundary",
        },
        "ST-0302 contract top-level keys differ",
    )
    _require(
        _exact_value(
            contract["document"],
            {
                "id": "RAOS-FOUNDATION-SCHEMA-001",
                "version": "1.0.0",
                "story_id": "ST-0302",
                "status": "LOCAL_AND_CI_CANDIDATE",
                "formal_verification": "NOT_EXECUTED",
            },
        ),
        "ST-0302 document differs",
    )
    _require(
        _exact_value(
            _mapping(contract["story"], "story"),
            {
                "epic_id": "EPIC-03",
                "title": "Foundation schemas and extensions",
                "objective": "MIG-001_FOUNDATION_SUBSET",
                "dependencies": ["ST-0301"],
                "deliverables": ["SCHEMAS", "BUILTIN_TYPE_POLICY", "UUIDV7_VALIDATION"],
                "acceptance": ["BASELINE_VALIDATION_SQL_PASS"],
                "required_suites": ["TST-008"],
                "priority": "P0",
                "mvp": True,
                "size": "M",
                "one_pr_preferred": True,
                "open_decisions": [],
            },
        ),
        "story contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["scope_precedence"], "scope precedence"),
            {
                "canonical_split": {
                    "ST-0302": "SCHEMAS_EXTENSIONS_TYPES_UUIDV7",
                    "ST-0303": "IAM_JOB_OUTBOX_INBOX_AUDIT_TABLES_CONSTRAINTS_INDEXES",
                },
                "upstream_wave": "MIG-001",
                "architecture_slices": [
                    "SLICE-003",
                    "SLICE-004",
                    "SLICE-005",
                    "SLICE-007",
                ],
                "table_creation": "DEFERRED_TO_ST_0303",
            },
        ),
        "scope precedence differs",
    )
    _require(
        _exact_value(
            _mapping(contract["database"], "database"),
            {
                "product": "PostgreSQL",
                "exact_server_version_num": 180004,
                "minimum_uuidv7_server_version_num": 180000,
                "timezone": "UTC",
                "transactional_ddl": True,
            },
        ),
        "database contract differs",
    )
    schemas_value = contract["schemas"]
    _require(isinstance(schemas_value, list), "foundation schemas differ")
    schemas = [_mapping(item, "foundation schema") for item in schemas_value]
    _require(
        _exact_value(
            schemas,
            [
                {
                    "name": "ops",
                    "comment": (
                        "ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定"
                    ),
                    "owner": "CURRENT_MIGRATION_ROLE",
                    "owner_privileges": ["CREATE", "USAGE"],
                    "public_privileges": "NONE",
                    "non_owner_privileges": "NONE",
                },
                {
                    "name": "iam",
                    "comment": "OIDC主体、アプリケーションRole、権限、緊急アクセス",
                    "owner": "CURRENT_MIGRATION_ROLE",
                    "owner_privileges": ["CREATE", "USAGE"],
                    "public_privileges": "NONE",
                    "non_owner_privileges": "NONE",
                },
            ],
        ),
        "foundation schemas differ",
    )
    _require(
        _exact_value(
            _mapping(contract["extensions"], "extensions"),
            {
                "created": [],
                "runtime_dependencies": [],
                "id_generation_dependencies": [],
                "explicitly_not_required": ["pgcrypto", "uuid-ossp"],
            },
        ),
        "extension-zero policy differs",
    )
    _require(
        _exact_value(
            _mapping(contract["types"], "types"),
            {
                "strategy": "POSTGRESQL_BUILTINS_WITH_TABLE_CHECK_CONSTRAINTS",
                "custom_types_created": [],
                "native_enums_created": [],
                "baseline_builtins": [
                    "bigint",
                    "boolean",
                    "character",
                    "date",
                    "integer",
                    "interval",
                    "jsonb",
                    "numeric",
                    "smallint",
                    "text",
                    "timestamp with time zone",
                    "uuid",
                ],
            },
        ),
        "type policy differs",
    )
    _require(
        _exact_value(
            _mapping(contract["uuidv7"], "uuidv7"),
            {
                "generation_function": "pg_catalog.uuidv7()",
                "shifted_generation_function": "pg_catalog.uuidv7(interval)",
                "version_function": "pg_catalog.uuid_extract_version(uuid)",
                "timestamp_function": "pg_catalog.uuid_extract_timestamp(uuid)",
                "expected_return_type": "uuid",
                "expected_version": 7,
                "business_time_source": "FORBIDDEN",
            },
        ),
        "UUIDv7 policy differs",
    )
    revision = _mapping(contract["revision"], "revision")
    _require(
        _exact_value(
            revision,
            {
                "revision": "202608030002",
                "down_revision": "202608030001",
                "story_id": "ST-0302",
                "path": REVISION_PATH.as_posix(),
                "runner_version": "1.1.0",
                "server_version_num": 180004,
                "transaction": "ALEMBIC_PER_REVISION",
                "upgrade": "CREATE_EMPTY_OPS_AND_IAM_SCHEMAS",
                "downgrade": "DROP_EMPTY_SCHEMAS_RESTRICT_TO_ST_0301_ANCHOR",
            },
        ),
        "revision contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["validation"], "validation"),
            {
                "sql_path": VALIDATION_PATH.as_posix(),
                "assertions": [
                    "EXACT_POSTGRESQL_18_4",
                    "EXACT_OPS_AND_IAM_SCHEMA_METADATA",
                    "EXACT_OWNER_ONLY_SCHEMA_PRIVILEGES",
                    "NO_FOUNDATION_RELATIONS_ROUTINES_OR_CUSTOM_TYPES",
                    "NO_NON_PLPGSQL_EXTENSIONS",
                    "BUILTIN_TYPE_SET_RESOLVES_IN_PG_CATALOG",
                    "UUIDV7_RETURNS_UUID_VERSION_7_WITH_TIMESTAMP",
                    "EXACT_HEAD_AND_SUCCEEDED_HISTORY",
                ],
                "result": "EXCEPTION_ON_FAILURE_AND_ONE_ALLOWLISTED_SUMMARY_ROW",
            },
        ),
        "validation contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["downgrade"], "downgrade"),
            {
                "operational_command": "ONE_STEP_ONLY",
                "below_history_anchor": "FORBIDDEN",
                "cascade": "FORBIDDEN",
                "nonempty_schema": "FAIL_AND_ROLL_BACK",
                "version_ddl_and_success_history_atomic": True,
            },
        ),
        "downgrade contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["security"], "security"),
            {
                "public_usage": "FORBIDDEN",
                "public_create": "FORBIDDEN",
                "non_owner_schema_privileges": "FORBIDDEN",
                "foundation_default_privileges": "FORBIDDEN_UNTIL_ST_0306",
                "dynamic_sql": "FORBIDDEN",
                "extension_install": "FORBIDDEN",
                "provider_or_network_access": "FORBIDDEN",
                "production_execution": "FORBIDDEN",
            },
        ),
        "security contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["verification"], "verification"),
            {
                "local_command": (
                    "RAOS_CI_OFFLINE=1 RAOS_NETWORK_DENIED=1 "
                    "RAOS_PG_BIN=/home/minami/.cache/raos-toolchains/postgresql/"
                    "18.4/root/usr/lib/postgresql/18/bin "
                    "RAOS_PG_LIB=/home/minami/.cache/raos-toolchains/postgresql/"
                    "18.4/root/usr/lib/x86_64-linux-gnu "
                    "make migration-test "
                    "UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv"
                ),
                "required_behaviors": [
                    "EMPTY_DATABASE_TO_FOUNDATION_HEAD",
                    "PREVIOUS_REVISION_TO_FOUNDATION_HEAD",
                    "FOUNDATION_DOWNGRADE_AND_REUPGRADE",
                    "BASELINE_VALIDATION_SQL",
                    "SCHEMA_METADATA_TAMPER_DETECTION",
                    "REVISION_SOURCE_AND_GRAPH_INTEGRITY",
                    "REPEATED_UPGRADE_NOOP",
                    "FAILED_DOWNGRADE_FORWARD_RECOVERY",
                ],
            },
        ),
        "verification contract differs",
    )
    _require(
        _exact_value(
            _mapping(contract["boundary"], "boundary"),
            {
                "environment": "LOCAL_AND_CI_IMPLEMENTATION_CANDIDATE",
                "formal_tst_008": "NOT_EXECUTED",
                "independent_migration_owner_review": "NOT_EXECUTED",
                "hosted_ci_postgresql_18_4": "NOT_EXECUTED",
                "production_execution": "FORBIDDEN",
                "effective_canonical_status": "UNCHANGED",
            },
        ),
        "formal boundary differs",
    )
    return contract


def render_revision(contract: Mapping[str, Any]) -> bytes:
    schemas = cast(list[dict[str, Any]], contract["schemas"])
    ops_comment = schemas[0]["comment"]
    iam_comment = schemas[1]["comment"]
    text = f'''\
"""Create the empty RAOS foundation schemas and validate UUIDv7 policy.

Revision ID: 202608030002
Revises: 202608030001
Create Date: 2026-08-03

RAOS metadata:
- story: ST-0302
- requirement IDs: none
- architecture: RAOS-DATA-001 MIG-001 foundation subset
- risk class: A (additive empty schemas)
- estimated lock: catalog-only schema DDL
- backfill job: none
- rollback category: reversible while schemas remain empty; RESTRICT only
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "202608030002"
down_revision: str | None = "202608030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA ops")
    op.execute(
        "COMMENT ON SCHEMA ops IS '{ops_comment}'"
    )
    op.execute("REVOKE ALL ON SCHEMA ops FROM PUBLIC")
    op.execute("CREATE SCHEMA iam")
    op.execute(
        "COMMENT ON SCHEMA iam IS '{iam_comment}'"
    )
    op.execute("REVOKE ALL ON SCHEMA iam FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP SCHEMA iam RESTRICT")
    op.execute("DROP SCHEMA ops RESTRICT")
'''
    return text.encode("utf-8")


def render_validation_sql(revision_sha256: str) -> bytes:
    anchor = framework.REVISION_SPECS[0]
    _require(
        anchor.revision == "202608030001"
        and anchor.story_id == "ST-0301"
        and anchor.runner_version == "1.0.0"
        and anchor.server_version_num == 180004,
        "ST-0301 anchor contract differs",
    )
    text = f"""\
-- ST-0302 deterministic PostgreSQL 18.4 foundation validation.
-- Execute as the migration owner after upgrading to revision 202608030002.
DO $raos_st0302$
DECLARE
    observed_count bigint;
    sample_id uuid;
BEGIN
    IF current_setting('server_version_num')::integer <> 180004 THEN
        RAISE EXCEPTION 'ST0302_SERVER_VERSION_MISMATCH';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
      AND pg_catalog.pg_get_userbyid(n.nspowner) = current_user
      AND pg_catalog.obj_description(n.oid, 'pg_namespace') = CASE n.nspname
          WHEN 'ops' THEN 'ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定'
          WHEN 'iam' THEN 'OIDC主体、アプリケーションRole、権限、緊急アクセス'
      END;
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0302_SCHEMA_METADATA_MISMATCH';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
      AND (
          SELECT COALESCE(
              array_agg(acl.privilege_type ORDER BY acl.privilege_type),
              ARRAY[]::text[]
          )
          FROM pg_catalog.aclexplode(
              COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
          ) AS acl
          WHERE acl.grantee = n.nspowner
      ) = ARRAY['CREATE', 'USAGE']::text[]
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(n.nspacl, pg_catalog.acldefault('n', n.nspowner))
          ) AS acl
          WHERE acl.grantee <> n.nspowner
      );
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0302_SCHEMA_PRIVILEGE_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS defaults
        JOIN pg_catalog.pg_namespace AS n
          ON n.oid = defaults.defaclnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) THEN
        RAISE EXCEPTION 'ST0302_FOUNDATION_DEFAULT_PRIVILEGE';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_namespace AS n
    WHERE n.nspname = ANY (ARRAY[
        'ai', 'analytics', 'catalog', 'editorial', 'evidence', 'finance',
        'freshness', 'policy', 'portfolio', 'publishing', 'readmodel'
    ]::text[]);
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_LATER_SCHEMA_PRESENT';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS p
        JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_type AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_collation AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.collnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_conversion AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.connamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_operator AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.oprnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_opclass AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_opfamily AS o
        JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opfnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_config AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.cfgnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_dict AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.dictnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_parser AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.prsnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_ts_template AS t
        JOIN pg_catalog.pg_namespace AS n ON n.oid = t.tmplnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_statistic_ext AS s
        JOIN pg_catalog.pg_namespace AS n ON n.oid = s.stxnamespace
        WHERE n.nspname = ANY (ARRAY['ops', 'iam']::text[])
    ) THEN
        RAISE EXCEPTION 'ST0302_FOUNDATION_NOT_EMPTY';
    END IF;

    SELECT count(*) INTO observed_count
    FROM pg_catalog.pg_extension
    WHERE extname <> 'plpgsql';
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_EXTENSION_DEPENDENCY';
    END IF;

    SELECT count(*) INTO observed_count
    FROM (VALUES
        ('int8'), ('bool'), ('bpchar'), ('date'), ('int4'), ('interval'),
        ('jsonb'), ('numeric'), ('int2'), ('text'), ('timestamptz'), ('uuid')
    ) AS expected(typname)
    LEFT JOIN pg_catalog.pg_type AS t ON t.typname = expected.typname
    LEFT JOIN pg_catalog.pg_namespace AS n
      ON n.oid = t.typnamespace AND n.nspname = 'pg_catalog'
    WHERE n.oid IS NULL;
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0302_BUILTIN_TYPE_MISSING';
    END IF;

    IF pg_catalog.to_regprocedure('pg_catalog.uuidv7()') IS NULL
       OR pg_catalog.to_regprocedure('pg_catalog.uuidv7(interval)') IS NULL
       OR pg_catalog.to_regprocedure(
           'pg_catalog.uuid_extract_version(uuid)'
       ) IS NULL
       OR pg_catalog.to_regprocedure(
           'pg_catalog.uuid_extract_timestamp(uuid)'
       ) IS NULL THEN
        RAISE EXCEPTION 'ST0302_UUID_FUNCTION_MISSING';
    END IF;
    sample_id := pg_catalog.uuidv7();
    IF pg_catalog.pg_typeof(sample_id) <> 'pg_catalog.uuid'::pg_catalog.regtype
       OR pg_catalog.uuid_extract_version(sample_id) <> 7
       OR pg_catalog.uuid_extract_timestamp(sample_id) IS NULL THEN
        RAISE EXCEPTION 'ST0302_UUIDV7_INVALID';
    END IF;

    IF (SELECT count(*) FROM public.raos_migration_version) <> 1
       OR NOT EXISTS (
           SELECT 1
           FROM public.raos_migration_version
           WHERE version_num = '202608030002'
       ) THEN
        RAISE EXCEPTION 'ST0302_MIGRATION_VERSION_MISMATCH';
    END IF;

    IF (SELECT count(*) FROM public.raos_migration_history) <> 3
       OR NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history AS anchor
        JOIN public.raos_migration_history AS started
          ON started.event_id > anchor.event_id
        JOIN public.raos_migration_history AS succeeded
          ON succeeded.event_id > started.event_id
        JOIN public.raos_migration_version AS version
          ON version.version_num = '202608030002'
        WHERE anchor.revision_id = '202608030001'
          AND anchor.story_id = 'ST-0301'
          AND anchor.direction = 'UPGRADE'
          AND anchor.status = 'SUCCEEDED'
          AND anchor.source_sha256 = '{anchor.sha256}'
          AND anchor.runner_version = '1.0.0'
          AND anchor.server_version_num = 180004
          AND anchor.error_code IS NULL
          AND started.revision_id = '202608030002'
          AND started.story_id = 'ST-0302'
          AND started.direction = 'UPGRADE'
          AND started.status = 'STARTED'
          AND started.source_sha256 = '{revision_sha256}'
          AND started.runner_version = '1.1.0'
          AND started.server_version_num = 180004
          AND started.error_code IS NULL
          AND succeeded.revision_id = '202608030002'
          AND succeeded.story_id = 'ST-0302'
          AND succeeded.direction = 'UPGRADE'
          AND succeeded.status = 'SUCCEEDED'
          AND succeeded.source_sha256 = '{revision_sha256}'
          AND succeeded.runner_version = '1.1.0'
          AND succeeded.server_version_num = 180004
          AND succeeded.error_code IS NULL
          AND anchor.attempt_id <> started.attempt_id
          AND started.attempt_id = succeeded.attempt_id
          AND started.transaction_id <> succeeded.transaction_id
          AND succeeded.transaction_id = version.xmin::text
          AND succeeded.xmin::text = version.xmin::text
    ) THEN
        RAISE EXCEPTION 'ST0302_MIGRATION_HISTORY_MISMATCH';
    END IF;
END
$raos_st0302$;

SELECT
    'PASS'::text AS status,
    current_setting('server_version_num')::integer AS server_version_num,
    2::integer AS foundation_schema_count,
    0::integer AS extension_dependency_count,
    pg_catalog.uuid_extract_version(pg_catalog.uuidv7()) AS uuid_version;
"""
    return text.encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _verify_inputs(root: Path) -> None:
    for name, expected in PINNED_INPUTS.items():
        path = _regular_file(root, Path(name), "pinned input")
        _require(shared.sha256_file(path) == expected, "pinned input digest differs")
    predecessor = _regular_file(root, PREDECESSOR_PATH, "ST-0301 predecessor manifest")
    _require(
        shared.sha256_file(predecessor) == EXPECTED_PREDECESSOR_SHA256,
        "ST-0301 predecessor manifest digest differs",
    )


def render_catalog(
    root: Path,
    contract: Mapping[str, Any],
    revision: bytes,
    validation: bytes,
) -> bytes:
    document = {
        "document": {
            "id": "RAOS-FOUNDATION-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0302",
            "formal_verification": "NOT_EXECUTED",
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "sha256": _sha256(
                _regular_file(root, CONTRACT_PATH, "ST-0302 contract").read_bytes()
            ),
        },
        "revision": {
            **dict(contract["revision"]),
            "sha256": _sha256(revision),
        },
        "validation": {
            "path": VALIDATION_PATH.as_posix(),
            "sha256": _sha256(validation),
            "assertions": contract["validation"]["assertions"],
        },
        "schemas": contract["schemas"],
        "extensions": contract["extensions"],
        "types": contract["types"],
        "uuidv7": contract["uuidv7"],
        "boundary": contract["boundary"],
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _regular_file(root, relative, "ST-0302 source artifact").read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(
    root: Path,
    contract: Mapping[str, Any],
    outputs: Mapping[Path, bytes],
) -> bytes:
    artifacts = [_artifact(root, path) for path in SOURCE_ARTIFACT_PATHS]
    generated = [
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
            "id": "RAOS-FOUNDATION-SCHEMA-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0302",
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
                "story_id": "ST-0301",
                "uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_SHA256,
            },
        },
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": dict(contract["boundary"]),
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
    framework.assert_generation_toolchain(root)
    _verify_inputs(root)
    contract = _load_contract(root)
    revision = render_revision(contract)
    validation = render_validation_sql(_sha256(revision))
    catalog = render_catalog(root, contract, revision, validation)
    outputs: dict[Path, bytes] = {
        REVISION_PATH: revision,
        VALIDATION_PATH: validation,
        CATALOG_PATH: catalog,
    }
    outputs[MANIFEST_PATH] = render_manifest(root, contract, outputs)
    return outputs


def _install(relative: Path, content: bytes, root: Path) -> None:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError("unsafe generated path")
    root_metadata = root.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("generated root must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    descriptor = -1
    temporary_name = f".{relative.name}.st0302-{os.getpid()}"
    temporary_descriptor: int | None = None
    try:
        descriptor = os.open(root, directory_flags)
        descriptors.append(descriptor)
        for part in relative.parent.parts:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(part, directory_flags, dir_fd=descriptor)
            descriptor = child
            descriptors.append(descriptor)
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError("generated target must be a regular non-symlink file")
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=descriptor,
        )
        view = memoryview(content)
        while view:
            written = os.write(temporary_descriptor, view)
            if written <= 0:
                raise RuntimeError("generated artifact short write")
            view = view[written:]
        os.fsync(temporary_descriptor)
        os.close(temporary_descriptor)
        temporary_descriptor = None
        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
        )
        temporary_name = ""
        os.fsync(descriptor)
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name and descriptors:
            try:
                os.unlink(temporary_name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass


def install_generated(root: Path = REPO_ROOT) -> None:
    outputs = render_outputs(root)
    for path in GENERATED_PATHS:
        _install(path, outputs[path], root)


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_outputs(root)
    for path in GENERATED_PATHS:
        target = _regular_file(root, path, "generated artifact")
        _require(target.read_bytes() == expected[path], "generated artifact drift")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            install_generated()
            mode = "install"
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_artifacts": len(GENERATED_PATHS),
                "mode": mode,
                "status": "PASS",
                "story_id": "ST-0302",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
