#!/usr/bin/env python3
"""Validate ST-0303 and build its deterministic IAM/OPS migration bundle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
CONTRACT_PATH: Final = Path("changes/st-0303/contracts/iam-ops-schema.v1.yaml")
PREDECESSOR_CONTRACT_PATH: Final = Path(
    "changes/st-0302/contracts/foundation-schema.v1.yaml"
)
README_PATH: Final = Path("changes/st-0303/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st0303_iam_ops.py")
REVISION_PATH: Final = Path("migrations/versions/202608030003_iam_ops_tables.py")
CATALOG_PATH: Final = Path("changes/st-0303/generated/iam-ops-catalog.v1.json")
VALIDATION_PATH: Final = Path("changes/st-0303/generated/iam-ops-validation.v1.sql")
MANIFEST_PATH: Final = Path("changes/st-0303/manifest.yaml")
PREDECESSOR_PATH: Final = Path("changes/st-0302/manifest.yaml")
UPSTREAM_CATALOG_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"
)
GENERATED_PATHS: Final = (
    REVISION_PATH,
    CATALOG_PATH,
    VALIDATION_PATH,
    MANIFEST_PATH,
)
PREDECESSOR_SOURCE_ARTIFACT_PATHS: Final = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
    PREDECESSOR_CONTRACT_PATH,
    Path("changes/st-0302/README.md"),
    Path("docs/execplans/ST-0302.md"),
    Path("docs/worklogs/ST-0302.md"),
    Path("scripts/build_st0302_foundation.py"),
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
    Path("tests/st0106/test_workflow_contract.py"),
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
    Path("changes/st-0301/manifest.yaml"),
)
CURRENT_SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    Path("docs/execplans/ST-0303.md"),
    Path("docs/worklogs/ST-0303.md"),
    GENERATOR_PATH,
    Path("migrations/versions/202608030002_foundation_schemas.py"),
    Path("tests/st0303/conftest.py"),
    Path("tests/st0303/test_contract.py"),
    Path("tests/st0303/test_generation.py"),
    Path("tests/st0303/test_postgresql.py"),
    PREDECESSOR_PATH,
)
SOURCE_ARTIFACT_PATHS: Final = (
    *PREDECESSOR_SOURCE_ARTIFACT_PATHS,
    *CURRENT_SOURCE_ARTIFACT_PATHS,
)
EXPECTED_SOURCE_ARTIFACT_COUNT: Final = 54
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python scripts/build_st0303_iam_ops.py"
)
REVISION: Final = "202608030003"
DOWN_REVISION: Final = "202608030002"
RUNNER_VERSION: Final = "1.2.0"
EXPECTED_CONTRACT_SHA256: Final = (
    "fbf7c27d94b4fc10a8353e907e55502e3f003af24295ca9fa70d4983af2f22c7"
)
SUCCESSOR_CONTRACT_PATH: Final = Path("changes/st-0304/contracts/domain-schema.v1.yaml")
PINNED_INPUTS: Final = {
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml": "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d",
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    "changes/st-0002/job-state.v1.yaml": "9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a",
    "changes/st-0002/database/202607300001_job_state_expand.sql": "6171d33b0ac8a15d48a7ccfdff5ff6872ba8de5c919ca836effea3523d39ff31",
    "changes/st-0002/database/202607300002_job_state_expand_validate.sql": "50fb0c65d8482817ffa7fbbb84e02965683fcb8dda2a6f9ecb0a3e7766d75c95",
    "changes/st-0002/database/202607300004_job_state_contract_prepare.sql": "6e0bca4e086547fb9035971fcef812a79edb155ef0af69a9e2b55de30b2ac779",
    "changes/st-0002/database/202607300005_job_state_contract.sql": "9e54b1719d9fdd02a2790916d02875a909dbb027be33c3108285f5d788a91897",
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
}
EXPECTED_INVENTORY: Final = {
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
SELECTED_TABLES: Final = (
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
TABLE_CREATION_ORDER: Final = (
    "ops.object_artifact",
    "ops.job",
    "ops.job_attempt",
    "ops.outbox_event",
    "ops.inbox_receipt",
    "ops.idempotency_record",
    "ops.audit_event",
    "iam.principal",
    "ops.runtime_setting_version",
    "iam.user_account",
    "iam.service_principal",
    "iam.role",
    "iam.permission",
    "iam.role_permission",
    "iam.principal_role_assignment",
    "iam.session_revocation",
    "iam.break_glass_record",
)
DEFERRED_FOREIGN_KEYS: Final = {
    "fk_ops_job_site_id": "portfolio.site",
    "fk_iam_break_glass_record_incident_id": "ops.incident",
}

# PostgreSQL 18.4 canonical deparse captured with search_path=pg_catalog and
# pretty=false.  These exact strings are deliberately not normalized: the
# validation artifact must reject same-name objects whose executable bodies
# have drifted while their coarse catalog shape remains unchanged.
CANONICAL_CHECK_EXPRESSIONS: Final = {
    "ck_iam_assignment_revoke_pair": (
        "((revoked_at IS NULL) = (revoked_by_principal_id IS NULL))"
    ),
    "ck_iam_assignment_scope": (
        "(scope_type = ANY (ARRAY['GLOBAL'::text, 'SITE'::text, "
        "'CATEGORY'::text, 'ARTICLE'::text]))"
    ),
    "ck_iam_assignment_scope_id": (
        "(((scope_type = 'GLOBAL'::text) AND (scope_id IS NULL)) OR "
        "((scope_type <> 'GLOBAL'::text) AND (scope_id IS NOT NULL)))"
    ),
    "ck_iam_assignment_window": ("((valid_to IS NULL) OR (valid_to > valid_from))"),
    "ck_iam_break_glass_permissions": ("(jsonb_typeof(permissions) = 'object'::text)"),
    "ck_iam_break_glass_window": (
        "((expires_at > started_at) AND ((ended_at IS NULL) OR "
        "(ended_at >= started_at)))"
    ),
    "ck_iam_permission_risk": (
        "(risk_level = ANY (ARRAY['LOW'::text, 'MEDIUM'::text, "
        "'HIGH'::text, 'CRITICAL'::text]))"
    ),
    "ck_iam_permission_status": (
        "(status = ANY (ARRAY['ACTIVE'::text, 'RETIRED'::text]))"
    ),
    "ck_iam_principal_deactivation": (
        "((status <> 'DEACTIVATED'::text) OR (deactivated_at IS NOT NULL))"
    ),
    "ck_iam_principal_status": (
        "(status = ANY (ARRAY['ACTIVE'::text, 'SUSPENDED'::text, 'DEACTIVATED'::text]))"
    ),
    "ck_iam_principal_type": (
        "(principal_type = ANY (ARRAY['USER'::text, 'SERVICE'::text]))"
    ),
    "ck_iam_principal_version": "(lock_version >= 0)",
    "ck_iam_role_status": ("(status = ANY (ARRAY['ACTIVE'::text, 'RETIRED'::text]))"),
    "ck_iam_service_env": (
        "(allowed_environment = ANY (ARRAY['LOCAL'::text, 'CI'::text, "
        "'STAGING'::text, 'PRODUCTION'::text]))"
    ),
    "ck_iam_session_expiry": ("((expires_at IS NULL) OR (expires_at > revoke_before))"),
    "ck_iam_session_issuer": "(oidc_issuer ~ '^https://'::text)",
    "ck_iam_user_https_issuer": "(oidc_issuer ~ '^https://'::text)",
    "ck_ops_audit_actor": (
        "(actor_type = ANY (ARRAY['USER'::text, 'SERVICE'::text, "
        "'SCHEDULE'::text, 'SYSTEM'::text, 'ANONYMOUS'::text]))"
    ),
    "ck_ops_audit_after_hash": (
        "((after_hash IS NULL) OR (after_hash ~ '^[0-9a-f]{64}$'::text))"
    ),
    "ck_ops_audit_before_hash": (
        "((before_hash IS NULL) OR (before_hash ~ '^[0-9a-f]{64}$'::text))"
    ),
    "ck_ops_audit_details": "(jsonb_typeof(details) = 'object'::text)",
    "ck_ops_audit_outcome": (
        "(outcome = ANY (ARRAY['SUCCESS'::text, 'DENIED'::text, "
        "'FAILED'::text, 'NOOP'::text]))"
    ),
    "ck_ops_audit_severity": (
        "(severity = ANY (ARRAY['INFO'::text, 'NOTICE'::text, "
        "'WARNING'::text, 'CRITICAL'::text]))"
    ),
    "ck_ops_idem_expiry": "(expires_at > created_at)",
    "ck_ops_idem_request_hash": "(request_hash ~ '^[0-9a-f]{64}$'::text)",
    "ck_ops_idem_response": (
        "((status = 'IN_PROGRESS'::text) OR (response_status IS NOT NULL))"
    ),
    "ck_ops_idem_response_body": (
        "((response_body IS NULL) OR (jsonb_typeof(response_body) = 'object'::text))"
    ),
    "ck_ops_idem_status": (
        "(status = ANY (ARRAY['IN_PROGRESS'::text, 'COMPLETED'::text, 'FAILED'::text]))"
    ),
    "ck_ops_inbox_hash": (
        "((result_hash IS NULL) OR (result_hash ~ '^[0-9a-f]{64}$'::text))"
    ),
    "ck_ops_inbox_processed": (
        "((status = 'PROCESSING'::text) OR (processed_at IS NOT NULL))"
    ),
    "ck_ops_inbox_status": (
        "(status = ANY (ARRAY['PROCESSING'::text, 'PROCESSED'::text, "
        "'FAILED'::text, 'IGNORED'::text]))"
    ),
    "ck_ops_job_attempt_end": (
        "((status = 'RUNNING'::text) OR (completed_at IS NOT NULL))"
    ),
    "ck_ops_job_attempt_metrics": "(jsonb_typeof(metrics) = 'object'::text)",
    "ck_ops_job_attempt_no": "(attempt_no >= 1)",
    "ck_ops_job_attempt_status": (
        "(status = ANY (ARRAY['RUNNING'::text, 'SUCCEEDED'::text, "
        "'FAILED'::text, 'CANCELLED'::text, 'TIMED_OUT'::text]))"
    ),
    "ck_ops_job_attempts": (
        "(((max_attempts >= 1) AND (max_attempts <= 50)) AND "
        "((attempt_count >= 0) AND (attempt_count <= max_attempts)))"
    ),
    "ck_ops_job_budget": "((budget_jpy IS NULL) OR (budget_jpy >= 0))",
    "ck_ops_job_cancel_request": (
        "((cancel_requested_at IS NULL) OR (status <> 'SUCCEEDED'::text))"
    ),
    "ck_ops_job_completion": (
        "((status <> ALL (ARRAY['SUCCEEDED'::text, 'FAILED_TERMINAL'::text, "
        "'QUARANTINED'::text, 'CANCELLED'::text, 'EXPIRED'::text])) OR "
        "(completed_at IS NOT NULL))"
    ),
    "ck_ops_job_deadline_order": (
        "((deadline_at IS NULL) OR (deadline_at > created_at))"
    ),
    "ck_ops_job_lease_pair": ("((lease_owner IS NULL) = (lease_expires_at IS NULL))"),
    "ck_ops_job_payload": "(jsonb_typeof(payload) = 'object'::text)",
    "ck_ops_job_priority": "((priority >= 0) AND (priority <= 100))",
    "ck_ops_job_status": (
        "(status = ANY (ARRAY['REQUESTED'::text, 'QUEUED'::text, "
        "'RUNNING'::text, 'SUCCEEDED'::text, 'FAILED_RETRYABLE'::text, "
        "'RETRY_SCHEDULED'::text, 'FAILED_TERMINAL'::text, "
        "'QUARANTINED'::text, 'CANCELLED'::text, 'EXPIRED'::text]))"
    ),
    "ck_ops_job_version": "(lock_version >= 0)",
    "ck_ops_job_version_positive": "(job_version >= 1)",
    "ck_ops_object_artifact_enc": (
        "(encryption_state = ANY (ARRAY['SSE_KMS'::text, 'SSE_S3'::text, "
        "'LOCAL_DEV'::text]))"
    ),
    "ck_ops_object_artifact_kind": (
        "(artifact_kind = ANY (ARRAY['raw_provider_response'::text, "
        "'raw_primary_source'::text, 'source_snapshot'::text, "
        "'source_packet'::text, 'ai_input'::text, 'ai_output'::text, "
        "'publication_snapshot'::text, 'revenue_original'::text, "
        "'revenue_rejects'::text, 'audit_export'::text, "
        "'quality_report'::text, 'diff'::text, 'import_report'::text, "
        "'other'::text]))"
    ),
    "ck_ops_object_artifact_meta": "(jsonb_typeof(metadata) = 'object'::text)",
    "ck_ops_object_artifact_sha": "(sha256 ~ '^[0-9a-f]{64}$'::text)",
    "ck_ops_object_artifact_size": "(byte_size >= 0)",
    "ck_ops_outbox_attempts": "(publish_attempts >= 0)",
    "ck_ops_outbox_event_version": (
        "((event_version >= 1) AND (aggregate_version >= 0))"
    ),
    "ck_ops_outbox_hash": "(payload_schema_hash ~ '^[0-9a-f]{64}$'::text)",
    "ck_ops_outbox_payload": "(jsonb_typeof(payload) = 'object'::text)",
    "ck_ops_outbox_published": (
        "((status <> 'PUBLISHED'::text) OR (published_at IS NOT NULL))"
    ),
    "ck_ops_outbox_status": (
        "(status = ANY (ARRAY['PENDING'::text, 'DISPATCHING'::text, "
        "'PUBLISHED'::text, 'FAILED'::text, 'DEAD'::text]))"
    ),
    "ck_ops_setting_class": (
        "(setting_class = ANY (ARRAY['FEATURE_FLAG'::text, "
        "'THRESHOLD'::text, 'PROVIDER'::text, 'FRESHNESS'::text, "
        "'BUDGET'::text, 'UI'::text, 'OTHER'::text]))"
    ),
    "ck_ops_setting_hash": "(value_sha256 ~ '^[0-9a-f]{64}$'::text)",
    "ck_ops_setting_no_secret": "(setting_class <> 'SECRET'::text)",
    "ck_ops_setting_scope": (
        "(scope_type = ANY (ARRAY['GLOBAL'::text, 'SITE'::text, "
        "'CATEGORY'::text, 'ARTICLE'::text, 'PROVIDER'::text, 'TASK'::text]))"
    ),
    "ck_ops_setting_scope_id": (
        "(((scope_type = 'GLOBAL'::text) AND (scope_id IS NULL)) OR "
        "((scope_type <> 'GLOBAL'::text) AND (scope_id IS NOT NULL)))"
    ),
    "ck_ops_setting_status": (
        "(status = ANY (ARRAY['DRAFT'::text, 'ACTIVE'::text, "
        "'RETIRED'::text, 'REJECTED'::text]))"
    ),
    "ck_ops_setting_value": "(jsonb_typeof(value) = 'object'::text)",
    "ck_ops_setting_version": "(version_no >= 1)",
    "ck_ops_setting_window": (
        "((effective_to IS NULL) OR (effective_from IS NULL) OR "
        "(effective_to > effective_from))"
    ),
}
CANONICAL_INDEX_EXPRESSIONS: Final = {
    "ix_iam_user_email_lower": "lower(email)",
}
CANONICAL_INDEX_PREDICATES: Final = {
    "ix_iam_break_glass_active": "(ended_at IS NULL)",
    "ix_iam_user_email_lower": "(email IS NOT NULL)",
    "ix_ops_job_deadline_active": (
        "((deadline_at IS NOT NULL) AND (status = ANY "
        "(ARRAY['REQUESTED'::text, 'QUEUED'::text, 'RUNNING'::text, "
        "'FAILED_RETRYABLE'::text, 'RETRY_SCHEDULED'::text])))"
    ),
    "ix_ops_job_lease": "(status = 'RUNNING'::text)",
    "ix_ops_job_ready": (
        "(status = ANY (ARRAY['REQUESTED'::text, 'QUEUED'::text, "
        "'RETRY_SCHEDULED'::text]))"
    ),
    "ix_ops_outbox_ready": ("(status = ANY (ARRAY['PENDING'::text, 'FAILED'::text]))"),
    "uq_iam_assignment_active": "(revoked_at IS NULL)",
    "uq_ops_job_idempotency": "(idempotency_key IS NOT NULL)",
    "uq_ops_setting_active": "(status = 'ACTIVE'::text)",
}
CANONICAL_TRIGGER_DEFINITIONS: Final = {
    "trg_iam_principal_touch": (
        "CREATE TRIGGER trg_iam_principal_touch BEFORE UPDATE ON iam.principal "
        "FOR EACH ROW EXECUTE FUNCTION ops.touch_mutable_row()"
    ),
    "trg_ops_audit_event_immutable": (
        "CREATE TRIGGER trg_ops_audit_event_immutable BEFORE DELETE OR UPDATE "
        "ON ops.audit_event FOR EACH ROW EXECUTE FUNCTION "
        "ops.reject_immutable_mutation()"
    ),
    "trg_ops_job_touch": (
        "CREATE TRIGGER trg_ops_job_touch BEFORE UPDATE ON ops.job FOR EACH ROW "
        "EXECUTE FUNCTION ops.touch_mutable_row()"
    ),
    "trg_ops_object_artifact_immutable": (
        "CREATE TRIGGER trg_ops_object_artifact_immutable BEFORE DELETE OR UPDATE "
        "ON ops.object_artifact FOR EACH ROW EXECUTE FUNCTION "
        "ops.reject_immutable_mutation()"
    ),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{label} must be a mapping")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def _exact_value(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(_exact_value(actual[key], value) for key, value in expected.items())
        )
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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _verify_inputs(root: Path) -> None:
    for name, expected in PINNED_INPUTS.items():
        path = _regular_file(root, Path(name), "pinned input")
        if name.startswith(("docs/canonical/", "docs/upstream/")):
            _require(shared.sha256_file(path) == expected, "pinned input digest differs")
    _regular_file(root, PREDECESSOR_PATH, "ST-0302 predecessor")


def _named(items: list[Any], name: str, label: str) -> dict[str, Any]:
    matches = [item for item in items if _mapping(item, label).get("name") == name]
    _require(len(matches) == 1, f"{label} {name} is missing or duplicated")
    _require(isinstance(matches[0], dict), f"{label} {name} must be mutable")
    return cast(dict[str, Any], matches[0])


def _expected_tables(root: Path) -> list[dict[str, Any]]:
    upstream = _mapping(
        shared.load_yaml(
            _regular_file(root, UPSTREAM_CATALOG_PATH, "upstream catalog")
        ),
        "upstream catalog",
    )
    schemas = _sequence(upstream.get("schemas"), "upstream schemas")
    source_tables: dict[str, dict[str, Any]] = {}
    for schema_value in schemas:
        schema = _mapping(schema_value, "upstream schema")
        schema_id = schema.get("id")
        if schema_id not in {"ops", "iam"}:
            continue
        for table_value in _sequence(schema.get("tables"), "upstream tables"):
            table = dict(_mapping(table_value, "upstream table"))
            fully_qualified_name = table.get("fully_qualified_name")
            _require(
                isinstance(fully_qualified_name, str)
                and fully_qualified_name not in source_tables,
                "upstream table identity is invalid",
            )
            source_tables[fully_qualified_name] = table
    _require(
        set(SELECTED_TABLES) <= set(source_tables),
        "selected upstream table is missing",
    )

    expected: list[dict[str, Any]] = []
    normalization_counts = {"uuidv7": 0, "jsonb_typeof": 0, "lower": 0}
    for fully_qualified_name in SELECTED_TABLES:
        table = copy.deepcopy(source_tables[fully_qualified_name])
        schema, table_name = fully_qualified_name.split(".", 1)
        table["primary_key_name"] = f"pk_{schema}_{table_name}"

        columns = _sequence(table.get("columns"), "table columns")
        for column_value in columns:
            column = _mapping(column_value, "table column")
            if column.get("default") == "uuidv7()":
                column["default"] = "pg_catalog.uuidv7()"
                normalization_counts["uuidv7"] += 1

        checks = _sequence(table.get("check_constraints"), "check constraints")
        for check_value in checks:
            check = _mapping(check_value, "check constraint")
            expression = check.get("expression")
            _require(isinstance(expression, str), "check expression is invalid")
            if "jsonb_typeof(" in expression:
                _require(
                    "pg_catalog.jsonb_typeof(" not in expression,
                    "upstream check is already unexpectedly normalized",
                )
                check["expression"] = expression.replace(
                    "jsonb_typeof(", "pg_catalog.jsonb_typeof("
                )
                normalization_counts["jsonb_typeof"] += 1

        indexes = _sequence(table.get("indexes"), "table indexes")
        for index_value in indexes:
            index = _mapping(index_value, "table index")
            if index.get("expression") == "lower(email)":
                index["expression"] = "pg_catalog.lower(email)"
                normalization_counts["lower"] += 1

        if fully_qualified_name == "ops.job":
            _named(columns, "status", "job column")["default"] = "'REQUESTED'"
            columns.extend(
                [
                    {
                        "name": "job_version",
                        "type": "smallint",
                        "nullable": False,
                        "default": "1",
                        "description": "Version of the Job message/payload contract; distinct from lock_version.",
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                    {
                        "name": "deadline_at",
                        "type": "timestamptz",
                        "nullable": True,
                        "default": None,
                        "description": "Deadline after which an eligible active Job may expire.",
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                    {
                        "name": "cancel_requested_at",
                        "type": "timestamptz",
                        "nullable": True,
                        "default": None,
                        "description": "Timestamp of a cooperative cancellation request.",
                        "classification": "INTERNAL",
                        "pii": False,
                    },
                ]
            )
            _named(checks, "ck_ops_job_status", "job check")["expression"] = (
                "status IN ('REQUESTED', 'QUEUED', 'RUNNING', 'SUCCEEDED', "
                "'FAILED_RETRYABLE', 'RETRY_SCHEDULED', 'FAILED_TERMINAL', "
                "'QUARANTINED', 'CANCELLED', 'EXPIRED')"
            )
            _named(checks, "ck_ops_job_completion", "job check")["expression"] = (
                "status NOT IN ('SUCCEEDED', 'FAILED_TERMINAL', 'QUARANTINED', "
                "'CANCELLED', 'EXPIRED') OR completed_at IS NOT NULL"
            )
            checks.extend(
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
                        "expression": "cancel_requested_at IS NULL OR status <> 'SUCCEEDED'",
                    },
                ]
            )
            _named(indexes, "ix_ops_job_ready", "job index")["where"] = (
                "status IN ('REQUESTED','QUEUED','RETRY_SCHEDULED')"
            )
            indexes.append(
                {
                    "name": "ix_ops_job_deadline_active",
                    "columns": ["deadline_at"],
                    "expression": None,
                    "unique": False,
                    "method": "btree",
                    "where": "deadline_at IS NOT NULL AND status IN ('REQUESTED','QUEUED','RUNNING','FAILED_RETRYABLE','RETRY_SCHEDULED')",
                    "include": [],
                    "nulls_not_distinct": False,
                    "description": "",
                }
            )

        immediate: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for foreign_key_value in _sequence(table.get("foreign_keys"), "foreign keys"):
            foreign_key = dict(_mapping(foreign_key_value, "foreign key"))
            name = foreign_key.get("name")
            if name not in DEFERRED_FOREIGN_KEYS:
                immediate.append(foreign_key)
                continue
            _require(
                foreign_key.get("references") == DEFERRED_FOREIGN_KEYS[name],
                "deferred foreign key target differs",
            )
            if name == "fk_ops_job_site_id":
                foreign_key["deferred_until_story"] = "ST-0304"
            else:
                foreign_key["deferred_until_condition"] = (
                    "TARGET_TABLE_OWNED_BY_APPROVED_LATER_STORY"
                )
                foreign_key["owner_story"] = "UNASSIGNED"
            foreign_key["reason"] = "TARGET_TABLE_NOT_YET_OWNED"
            foreign_key["column_and_index_installed"] = True
            deferred.append(foreign_key)
        table["foreign_keys"] = immediate
        table["deferred_foreign_keys"] = deferred
        expected.append(table)

    _require(
        normalization_counts == {"uuidv7": 15, "jsonb_typeof": 8, "lower": 1},
        "allowlisted normalization count differs",
    )
    return expected


def _inventory(contract: Mapping[str, Any]) -> dict[str, int]:
    tables = _sequence(contract.get("tables"), "contract tables")
    return {
        "tables": len(tables),
        "columns": sum(
            len(_sequence(_mapping(t, "table").get("columns"), "columns"))
            for t in tables
        ),
        "primary_keys": sum(
            bool(_mapping(t, "table").get("primary_key")) for t in tables
        ),
        "named_unique_constraints": sum(
            len(
                _sequence(
                    _mapping(t, "table").get("unique_constraints"), "unique constraints"
                )
            )
            for t in tables
        ),
        "check_constraints": sum(
            len(
                _sequence(
                    _mapping(t, "table").get("check_constraints"), "check constraints"
                )
            )
            for t in tables
        ),
        "standalone_indexes": sum(
            len(_sequence(_mapping(t, "table").get("indexes"), "indexes"))
            for t in tables
        ),
        "immediate_foreign_keys": sum(
            len(_sequence(_mapping(t, "table").get("foreign_keys"), "foreign keys"))
            for t in tables
        ),
        "deferred_foreign_keys": sum(
            len(
                _sequence(
                    _mapping(t, "table").get("deferred_foreign_keys"),
                    "deferred foreign keys",
                )
            )
            for t in tables
        ),
        "functions": len(_sequence(contract.get("functions"), "functions")),
        "triggers": len(_sequence(contract.get("triggers"), "triggers")),
    }


def _load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = _regular_file(root, CONTRACT_PATH, "ST-0303 contract")
    value = shared.load_yaml(path)
    contract = dict(_mapping(value, "ST-0303 contract"))
    _require(
        set(contract)
        == {
            "document",
            "story",
            "source_precedence",
            "database",
            "expected_inventory",
            "job_contract",
            "tables",
            "deferred_foreign_key_policy",
            "functions",
            "triggers",
            "security",
            "downgrade",
            "known_canonical_limitations",
            "verification",
            "boundary",
            "out_of_scope",
        },
        "ST-0303 contract top-level keys differ",
    )
    _require(
        _exact_value(
            contract["document"],
            {
                "id": "RAOS-IAM-OPS-SCHEMA-001",
                "version": "1.0.0",
                "story_id": "ST-0303",
                "status": "LOCAL_AND_CI_CANDIDATE",
                "formal_verification": "NOT_EXECUTED",
            },
        ),
        "ST-0303 document differs",
    )
    story = _mapping(contract["story"], "story")
    _require(story.get("dependencies") == ["ST-0302"], "story dependency differs")
    _require(story.get("open_decisions") == [], "story has unresolved decisions")
    _require(
        story.get("required_suites") == ["TST-008", "TST-011", "TST-013"],
        "story suites differ",
    )
    precedence = _mapping(contract["source_precedence"], "source precedence")
    pins = _sequence(precedence.get("pinned_inputs"), "pinned inputs")
    _require(
        {
            str(_mapping(item, "pin").get("path")): _mapping(item, "pin").get("sha256")
            for item in pins
        }
        == PINNED_INPUTS,
        "contract pinned inputs differ",
    )
    _require(
        _exact_value(
            precedence.get("predecessor_manifest"),
            {
                "story_id": "ST-0302",
                "path": PREDECESSOR_PATH.as_posix(),
            },
        ),
        "contract predecessor differs",
    )
    _require(
        precedence.get("translation_rules")
        == [
            "COPY_SELECTED_TABLE_METADATA_EXACTLY_EXCEPT_ALLOWLISTED_PG_CATALOG_QUALIFICATION",
            "APPLY_ST_0002_FINAL_JOB_CONTRACT_TO_FRESH_TABLE",
            "DEFER_ONLY_FKS_WITH_UNAVAILABLE_TARGETS",
            "DO_NOT_CONCATENATE_PROPOSAL_PHASE_SQL",
        ],
        "translation rules differ",
    )
    _require(
        _exact_value(
            precedence.get("allowed_security_normalizations"),
            {
                "policy": "ALLOWLIST_ONLY",
                "reject_unlisted_source_drift": True,
                "items": [
                    {
                        "field_kind": "COLUMN_DEFAULT",
                        "source": "uuidv7()",
                        "normalized": "pg_catalog.uuidv7()",
                        "exact_occurrences": 15,
                    },
                    {
                        "field_kind": "CHECK_EXPRESSION",
                        "source": "jsonb_typeof(",
                        "normalized": "pg_catalog.jsonb_typeof(",
                        "exact_occurrences": 8,
                    },
                    {
                        "field_kind": "INDEX_EXPRESSION",
                        "source": "lower(email)",
                        "normalized": "pg_catalog.lower(email)",
                        "exact_occurrences": 1,
                    },
                ],
            },
        ),
        "security normalization allowlist differs",
    )
    _require(
        contract.get("expected_inventory") == EXPECTED_INVENTORY,
        "expected inventory differs",
    )
    _require(_inventory(contract) == EXPECTED_INVENTORY, "structured inventory differs")
    _require(
        _exact_value(
            _sequence(contract.get("tables"), "tables"), _expected_tables(root)
        ),
        "contract tables differ from pinned sources and approved transformations",
    )
    _validate_contract_semantics(contract)
    return contract


def _foundation_schema_rows(root: Path) -> list[tuple[object, ...]]:
    contract = _mapping(
        shared.load_yaml(
            _regular_file(root, PREDECESSOR_CONTRACT_PATH, "ST-0302 contract")
        ),
        "ST-0302 contract",
    )
    schemas = [
        _mapping(schema, "ST-0302 schema")
        for schema in _sequence(contract.get("schemas"), "ST-0302 schemas")
    ]
    _require(
        [schema.get("name") for schema in schemas] == ["ops", "iam"],
        "ST-0302 schema inventory differs",
    )
    rows: list[tuple[object, ...]] = []
    for schema in schemas:
        name = schema.get("name")
        comment = schema.get("comment")
        _require(
            isinstance(name, str) and isinstance(comment, str) and comment,
            "ST-0302 schema identity differs",
        )
        _require(
            schema.get("owner") == "CURRENT_MIGRATION_ROLE"
            and schema.get("owner_privileges") == ["CREATE", "USAGE"]
            and schema.get("public_privileges") == "NONE"
            and schema.get("non_owner_privileges") == "NONE",
            f"ST-0302 schema ACL contract differs: {name}",
        )
        rows.append((name, comment))
    return rows


def _validate_contract_semantics(contract: Mapping[str, Any]) -> None:
    _require(
        _exact_value(
            contract.get("database"),
            {
                "product": "PostgreSQL",
                "exact_server_version_num": 180004,
                "timezone": "UTC",
                "transactional_ddl": True,
                "schemas": ["ops", "iam"],
                "extension_dependencies": [],
                "custom_types": [],
            },
        ),
        "database contract differs",
    )
    expected_states = [
        "REQUESTED",
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED_RETRYABLE",
        "RETRY_SCHEDULED",
        "FAILED_TERMINAL",
        "QUARANTINED",
        "CANCELLED",
        "EXPIRED",
    ]
    _require(
        _exact_value(
            contract.get("job_contract"),
            {
                "decision_id": "INT-DEC-003",
                "initial_state": "REQUESTED",
                "states": expected_states,
                "status_default": "REQUESTED",
                "added_columns": ["job_version", "deadline_at", "cancel_requested_at"],
                "final_check_constraints": [
                    "ck_ops_job_status",
                    "ck_ops_job_completion",
                    "ck_ops_job_version_positive",
                    "ck_ops_job_deadline_order",
                    "ck_ops_job_cancel_request",
                ],
                "final_ready_index": "ix_ops_job_ready",
                "final_deadline_index": "ix_ops_job_deadline_active",
                "total_check_constraints": 11,
                "total_standalone_indexes": 9,
                "runtime_owner_story": "ST-1404",
            },
        ),
        "final ST-0002 Job identity differs",
    )

    tables = [
        dict(_mapping(item, "table"))
        for item in _sequence(contract.get("tables"), "tables")
    ]
    _require(
        tuple(str(table.get("fully_qualified_name")) for table in tables)
        == SELECTED_TABLES,
        "selected table order differs",
    )
    table_by_name = {str(table["fully_qualified_name"]): table for table in tables}
    _require(len(table_by_name) == 17, "table identity is duplicated")
    creation_position = {name: index for index, name in enumerate(TABLE_CREATION_ORDER)}
    _require(set(creation_position) == set(table_by_name), "creation order differs")
    object_names: set[str] = set()
    allowed_types = {
        "bigint",
        "boolean",
        "integer",
        "jsonb",
        "smallint",
        "text",
        "timestamptz",
        "uuid",
    }
    allowed_defaults = {
        "'ACTIVE'",
        "'INFO'",
        "'IN_PROGRESS'",
        "'PENDING'",
        "'REQUESTED'",
        "'s3'",
        "'{}'::jsonb",
        "0",
        "1",
        "5",
        "50",
        "CURRENT_TIMESTAMP",
        "false",
        "pg_catalog.uuidv7()",
        "true",
    }
    for table in tables:
        fully_qualified_name = str(table["fully_qualified_name"])
        schema, table_name = fully_qualified_name.split(".", 1)
        _require(schema in {"ops", "iam"}, "table schema is outside ST-0303")
        _require(table.get("name") == table_name, "table identity differs")
        _require(table.get("owner_module") == schema, "logical owner differs")
        _require(
            table.get("primary_key_name") == f"pk_{schema}_{table_name}",
            "primary key name differs",
        )
        columns = [
            dict(_mapping(item, "column"))
            for item in _sequence(table.get("columns"), "columns")
        ]
        column_names = [str(column.get("name")) for column in columns]
        _require(
            len(column_names) == len(set(column_names)), "column name is duplicated"
        )
        for column in columns:
            name = column.get("name")
            _require(
                isinstance(name, str)
                and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None,
                "column name is unsafe",
            )
            _require(
                column.get("type") in allowed_types, "column type is outside allowlist"
            )
            _require(
                type(column.get("nullable")) is bool, "column nullability is invalid"
            )
            default = column.get("default")
            _require(
                default is None or default in allowed_defaults,
                "column default is outside allowlist",
            )
            _require(
                isinstance(column.get("description"), str)
                and bool(str(column["description"]).strip()),
                "column description is empty",
            )
            _require(
                column.get("classification")
                in {"INTERNAL", "CONFIDENTIAL", "RESTRICTED"},
                "column classification differs",
            )
            _require(type(column.get("pii")) is bool, "column PII flag is invalid")
            _require(
                name
                not in {"password", "password_hash", "secret", "token", "credential"}
                and not name.endswith(("_password", "_secret", "_token")),
                "secret-bearing column name is forbidden",
            )
        primary_key = _sequence(table.get("primary_key"), "primary key")
        _require(
            primary_key and set(primary_key) <= set(column_names),
            "primary key columns differ",
        )
        for key in ("primary_key_name",):
            object_name = str(table[key])
            _require(
                object_name not in object_names, "database object name is duplicated"
            )
            object_names.add(object_name)
        for collection_name in (
            "unique_constraints",
            "check_constraints",
            "foreign_keys",
            "deferred_foreign_keys",
            "indexes",
        ):
            for item_value in _sequence(table.get(collection_name), collection_name):
                item = _mapping(item_value, collection_name)
                object_name = item.get("name")
                _require(
                    isinstance(object_name, str)
                    and re.fullmatch(r"[a-z][a-z0-9_]*", object_name) is not None
                    and object_name not in object_names,
                    "database object name is unsafe or duplicated",
                )
                object_names.add(object_name)
        for item_value in _sequence(
            table.get("unique_constraints"), "unique constraints"
        ):
            item = _mapping(item_value, "unique constraint")
            _require(
                set(_sequence(item.get("columns"), "unique columns"))
                <= set(column_names),
                "unique columns differ",
            )
        for item_value in _sequence(
            table.get("check_constraints"), "check constraints"
        ):
            expression = _mapping(item_value, "check constraint").get("expression")
            _require(
                isinstance(expression, str)
                and expression
                and all(
                    token not in expression for token in (";", "--", "/*", "*/", "$$")
                ),
                "check expression is unsafe",
            )
        for item_value in _sequence(table.get("indexes"), "indexes"):
            item = _mapping(item_value, "index")
            index_columns = _sequence(item.get("columns"), "index columns")
            expression = item.get("expression")
            _require(
                bool(index_columns) != bool(expression),
                "index columns/expression shape differs",
            )
            _require(set(index_columns) <= set(column_names), "index columns differ")
            _require(item.get("method") in {"btree", "brin"}, "index method differs")
            _require(type(item.get("unique")) is bool, "index uniqueness is invalid")
            _require(
                type(item.get("nulls_not_distinct")) is bool,
                "index NULL policy is invalid",
            )
            _require(
                not item.get("nulls_not_distinct") or item.get("unique") is True,
                "NULLS NOT DISTINCT requires unique index",
            )
            for fragment in (expression, item.get("where")):
                _require(
                    fragment is None
                    or (
                        isinstance(fragment, str)
                        and fragment
                        and all(
                            token not in fragment
                            for token in (";", "--", "/*", "*/", "$$")
                        )
                    ),
                    "index expression is unsafe",
                )
        for item_value in _sequence(table.get("foreign_keys"), "foreign keys"):
            item = _mapping(item_value, "foreign key")
            target = item.get("references")
            _require(
                target in table_by_name, "immediate foreign key target is unavailable"
            )
            _require(
                set(_sequence(item.get("columns"), "foreign key columns"))
                <= set(column_names),
                "foreign key columns differ",
            )
            if target != fully_qualified_name:
                _require(
                    creation_position[str(target)]
                    < creation_position[fully_qualified_name],
                    "table dependency order differs",
                )
        for item_value in _sequence(
            table.get("deferred_foreign_keys"), "deferred foreign keys"
        ):
            item = _mapping(item_value, "deferred foreign key")
            _require(
                item.get("name") in DEFERRED_FOREIGN_KEYS,
                "unexpected deferred foreign key",
            )
            _require(
                item.get("references") not in table_by_name,
                "available foreign key was deferred",
            )
            _require(
                item.get("column_and_index_installed") is True,
                "deferred column/index policy differs",
            )

    deferred_policy = _mapping(
        contract.get("deferred_foreign_key_policy"), "deferred policy"
    )
    _require(
        deferred_policy.get("exact_names") == list(DEFERRED_FOREIGN_KEYS),
        "deferred foreign key names differ",
    )
    policy_items = _sequence(deferred_policy.get("items"), "deferred policy items")
    _require(len(policy_items) == 2, "deferred policy item count differs")
    incident_items = [
        _mapping(item, "deferred item")
        for item in policy_items
        if _mapping(item, "deferred item").get("name")
        == "fk_iam_break_glass_record_incident_id"
    ]
    _require(len(incident_items) == 1, "incident deferred owner record differs")
    _require(
        incident_items[0].get("deferred_until_condition")
        == "TARGET_TABLE_OWNED_BY_APPROVED_LATER_STORY"
        and incident_items[0].get("owner_story") == "UNASSIGNED"
        and "deferred_until_story" not in incident_items[0],
        "incident deferred owner was inferred",
    )

    functions = {
        str(_mapping(item, "function").get("fully_qualified_name")): _mapping(
            item, "function"
        )
        for item in _sequence(contract.get("functions"), "functions")
    }
    _require(
        set(functions) == {"ops.touch_mutable_row", "ops.reject_immutable_mutation"},
        "function set differs",
    )
    for function in functions.values():
        _require(function.get("security") == "INVOKER", "function security differs")
        _require(
            function.get("set_search_path") == "pg_catalog",
            "function search path differs",
        )
        _require(
            function.get("public_execute") == "REVOKED", "function PUBLIC ACL differs"
        )
        _require(
            function.get("language") == "plpgsql"
            and function.get("returns") == "trigger",
            "function shape differs",
        )
    rejection = _mapping(
        functions["ops.reject_immutable_mutation"].get("behavior"), "immutable behavior"
    )
    _require(
        rejection.get("maintenance_guc") == "raos.allow_immutable_maintenance"
        and rejection.get("maintenance_value") == "on"
        and rejection.get("maintenance_role") == "raos_migrator"
        and rejection.get("maintenance_role_check")
        == "pg_catalog.pg_has_role(current_user, 'raos_migrator', 'MEMBER')"
        and rejection.get("rejection_sqlstate") == "55000",
        "immutable maintenance boundary differs",
    )
    triggers = {
        str(_mapping(item, "trigger").get("name")): _mapping(item, "trigger")
        for item in _sequence(contract.get("triggers"), "triggers")
    }
    _require(
        set(triggers)
        == {
            "trg_ops_job_touch",
            "trg_iam_principal_touch",
            "trg_ops_object_artifact_immutable",
            "trg_ops_audit_event_immutable",
        },
        "trigger set differs",
    )
    _require(
        {
            str(item.get("table"))
            for item in triggers.values()
            if item.get("function") == "ops.reject_immutable_mutation()"
        }
        == {"ops.object_artifact", "ops.audit_event"},
        "hard immutability trigger scope differs",
    )

    security = _mapping(contract.get("security"), "security")
    _require(
        security.get("hard_immutable_tables")
        == ["ops.object_artifact", "ops.audit_event"],
        "hard immutable tables differ",
    )
    for key in (
        "create_database_roles",
        "create_workload_grants",
        "create_default_privileges",
    ):
        _require(security.get(key) is False, "role or grant creation was enabled")
    _require(
        security.get("public_table_privileges") == "NONE", "PUBLIC table policy differs"
    )
    _require(
        security.get("public_function_execute") == "REVOKED",
        "PUBLIC function policy differs",
    )
    search_path = _mapping(security.get("search_path"), "search path")
    _require(search_path.get("only") == "pg_catalog", "search path differs")
    _require(
        search_path.get("hostile_resolution_test_required") is True,
        "hostile search path test differs",
    )

    downgrade = _mapping(contract.get("downgrade"), "downgrade")
    _require(
        downgrade.get("transaction_required") is True
        and downgrade.get("preflight_before_any_drop") is True
        and downgrade.get("require_all_owned_tables_empty") is True
        and downgrade.get("owned_table_count") == 17
        and downgrade.get("nonempty_failure_code") == "ST0303_DOWNGRADE_NONEMPTY"
        and downgrade.get("drop_tables_with") == "RESTRICT"
        and downgrade.get("partial_drop_forbidden") is True
        and downgrade.get("predecessor_revision") == DOWN_REVISION,
        "downgrade contract differs",
    )
    unresolved_paths: list[tuple[str, ...]] = []

    def visit(value: object, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                visit(child, (*path, str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*path, str(index)))
        elif value == "UNASSIGNED":
            unresolved_paths.append(path)

    visit(contract)
    _require(
        len(unresolved_paths) == 2
        and all(path[-1] == "owner_story" for path in unresolved_paths),
        "unexpected unresolved contract field",
    )


SQL_TYPES: Final = {
    "bigint": "pg_catalog.int8",
    "boolean": "pg_catalog.bool",
    "integer": "pg_catalog.int4",
    "jsonb": "pg_catalog.jsonb",
    "smallint": "pg_catalog.int2",
    "text": "pg_catalog.text",
    "timestamptz": "pg_catalog.timestamptz",
    "uuid": "pg_catalog.uuid",
}


def _identifier(value: object, label: str) -> str:
    _require(
        isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None,
        f"{label} is not a safe SQL identifier",
    )
    return value


def _qualified_identifier(value: object, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be text")
    parts = value.split(".")
    _require(len(parts) == 2, f"{label} must be schema-qualified")
    return ".".join(_identifier(part, label) for part in parts)


def _sql_literal(value: object) -> str:
    _require(isinstance(value, str) and "\x00" not in value, "SQL literal is invalid")
    return "'" + value.replace("'", "''") + "'"


def _table_map(contract: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(_mapping(item, "table")["fully_qualified_name"]): _mapping(item, "table")
        for item in _sequence(contract.get("tables"), "tables")
    }


def _create_table_statement(table: Mapping[str, Any]) -> str:
    fully_qualified_name = _qualified_identifier(
        table.get("fully_qualified_name"), "table"
    )
    definitions: list[str] = []
    for column_value in _sequence(table.get("columns"), "columns"):
        column = _mapping(column_value, "column")
        name = _identifier(column.get("name"), "column")
        sql_type = SQL_TYPES[str(column.get("type"))]
        definition = f"    {name} {sql_type}"
        default = column.get("default")
        if default is not None:
            definition += f" DEFAULT {default}"
        if column.get("nullable") is False:
            definition += " NOT NULL"
        definitions.append(definition)
    primary_key_name = _identifier(table.get("primary_key_name"), "primary key")
    primary_columns = ", ".join(
        _identifier(item, "primary key column")
        for item in _sequence(table.get("primary_key"), "primary key")
    )
    definitions.append(
        f"    CONSTRAINT {primary_key_name} PRIMARY KEY ({primary_columns})"
    )
    for item_value in _sequence(table.get("unique_constraints"), "unique constraints"):
        item = _mapping(item_value, "unique constraint")
        name = _identifier(item.get("name"), "unique constraint")
        columns = ", ".join(
            _identifier(column, "unique column")
            for column in _sequence(item.get("columns"), "unique columns")
        )
        definitions.append(f"    CONSTRAINT {name} UNIQUE ({columns})")
    for item_value in _sequence(table.get("check_constraints"), "check constraints"):
        item = _mapping(item_value, "check constraint")
        name = _identifier(item.get("name"), "check constraint")
        definitions.append(f"    CONSTRAINT {name} CHECK ({item['expression']})")
    return f"CREATE TABLE {fully_qualified_name} (\n" + ",\n".join(definitions) + "\n)"


def _index_statement(table_name: str, index: Mapping[str, Any]) -> str:
    name = _identifier(index.get("name"), "index")
    unique = "UNIQUE " if index.get("unique") is True else ""
    method = _identifier(index.get("method"), "index method")
    columns = _sequence(index.get("columns"), "index columns")
    if columns:
        keys = ", ".join(_identifier(column, "index column") for column in columns)
    else:
        keys = str(index["expression"])
    statement = f"CREATE {unique}INDEX {name} ON {table_name} USING {method} ({keys})"
    include = _sequence(index.get("include"), "included columns")
    if include:
        statement += (
            " INCLUDE ("
            + ", ".join(_identifier(column, "included column") for column in include)
            + ")"
        )
    if index.get("nulls_not_distinct") is True:
        statement += " NULLS NOT DISTINCT"
    if index.get("where") is not None:
        statement += f" WHERE {index['where']}"
    return statement


TOUCH_FUNCTION_BODY: Final = """BEGIN
    IF NEW IS DISTINCT FROM OLD THEN
        NEW.updated_at := pg_catalog.statement_timestamp();
        NEW.lock_version := OLD.lock_version + 1;
    END IF;
    RETURN NEW;
END;"""

REJECT_FUNCTION_BODY: Final = """BEGIN
    IF pg_catalog.current_setting('raos.allow_immutable_maintenance', true) = 'on'
       AND pg_catalog.pg_has_role(current_user, 'raos_migrator', 'MEMBER') THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = 'RAOS immutable table mutation is forbidden';
END;"""


def _function_statements() -> list[str]:
    touch = f"""CREATE FUNCTION ops.touch_mutable_row()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog
AS $raos_st0303_touch${TOUCH_FUNCTION_BODY}$raos_st0303_touch$"""
    reject = f"""CREATE FUNCTION ops.reject_immutable_mutation()
RETURNS pg_catalog.trigger
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog
AS $raos_st0303_immutable${REJECT_FUNCTION_BODY}$raos_st0303_immutable$"""
    return [
        touch,
        "REVOKE ALL ON FUNCTION ops.touch_mutable_row() FROM PUBLIC",
        "COMMENT ON FUNCTION ops.touch_mutable_row() IS "
        + _sql_literal(
            "Mutable rows receive a statement timestamp and monotonic lock version only when row values change."
        ),
        reject,
        "REVOKE ALL ON FUNCTION ops.reject_immutable_mutation() FROM PUBLIC",
        "COMMENT ON FUNCTION ops.reject_immutable_mutation() IS "
        + _sql_literal(
            "Reject normal UPDATE and DELETE on hard-immutable tables; permit only an explicit migrator maintenance session."
        ),
    ]


def render_upgrade_statements(contract: Mapping[str, Any]) -> tuple[str, ...]:
    table_by_name = _table_map(contract)
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog",
        "SET LOCAL TIME ZONE 'UTC'",
    ]
    for table_name in TABLE_CREATION_ORDER:
        table = table_by_name[table_name]
        statements.append(_create_table_statement(table))
        statements.append(
            f"COMMENT ON TABLE {table_name} IS {_sql_literal(table['purpose'])}"
        )
        for column_value in _sequence(table.get("columns"), "columns"):
            column = _mapping(column_value, "column")
            column_name = _identifier(column.get("name"), "column")
            statements.append(
                f"COMMENT ON COLUMN {table_name}.{column_name} IS "
                + _sql_literal(column["description"])
            )
        statements.append(f"REVOKE ALL ON TABLE {table_name} FROM PUBLIC")

    for table_name in TABLE_CREATION_ORDER:
        table = table_by_name[table_name]
        for item_value in _sequence(table.get("foreign_keys"), "foreign keys"):
            item = _mapping(item_value, "foreign key")
            name = _identifier(item.get("name"), "foreign key")
            columns = ", ".join(
                _identifier(column, "foreign key column")
                for column in _sequence(item.get("columns"), "foreign key columns")
            )
            referenced_columns = ", ".join(
                _identifier(column, "referenced column")
                for column in _sequence(
                    item.get("referenced_columns"), "referenced columns"
                )
            )
            target = _qualified_identifier(item.get("references"), "foreign key target")
            deferrability = (
                "DEFERRABLE" if item.get("deferrable") is True else "NOT DEFERRABLE"
            )
            if item.get("deferrable") is True:
                deferrability += (
                    " INITIALLY DEFERRED"
                    if item.get("initially_deferred") is True
                    else " INITIALLY IMMEDIATE"
                )
            statements.append(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {name} "
                f"FOREIGN KEY ({columns}) REFERENCES {target} ({referenced_columns}) "
                f"ON DELETE {item['on_delete']} {deferrability}"
            )

    for table_name in TABLE_CREATION_ORDER:
        table = table_by_name[table_name]
        for item_value in _sequence(table.get("indexes"), "indexes"):
            item = _mapping(item_value, "index")
            statements.append(_index_statement(table_name, item))
            if item.get("description"):
                statements.append(
                    f"COMMENT ON INDEX {_qualified_identifier(table_name.split('.')[0] + '.' + str(item['name']), 'index')} IS "
                    + _sql_literal(item["description"])
                )

    statements.extend(_function_statements())
    for trigger_value in _sequence(contract.get("triggers"), "triggers"):
        trigger = _mapping(trigger_value, "trigger")
        name = _identifier(trigger.get("name"), "trigger")
        table_name = _qualified_identifier(trigger.get("table"), "trigger table")
        events = " OR ".join(
            str(event) for event in _sequence(trigger.get("events"), "trigger events")
        )
        function = str(trigger.get("function"))
        statements.append(
            f"CREATE TRIGGER {name} {trigger['timing']} {events} ON {table_name} "
            f"FOR EACH {trigger['level']} EXECUTE FUNCTION {function}"
        )
        statements.append(
            f"COMMENT ON TRIGGER {name} ON {table_name} IS "
            + _sql_literal(trigger["comment"])
        )
    return tuple(statements)


def render_downgrade_statements() -> tuple[str, ...]:
    lock = "LOCK TABLE " + ", ".join(TABLE_CREATION_ORDER) + " IN ACCESS EXCLUSIVE MODE"
    checks = []
    for table_name in TABLE_CREATION_ORDER:
        checks.append(
            f"    IF EXISTS (SELECT 1 FROM {table_name} LIMIT 1) THEN\n"
            f"        nonempty_tables := pg_catalog.array_append(nonempty_tables, {_sql_literal(table_name)});\n"
            "    END IF;"
        )
    preflight = """DO $raos_st0303_downgrade$
DECLARE
    nonempty_tables pg_catalog.text[] := ARRAY[]::pg_catalog.text[];
BEGIN
{checks}
    IF pg_catalog.cardinality(nonempty_tables) <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'ST0303_DOWNGRADE_NONEMPTY';
    END IF;
END
$raos_st0303_downgrade$""".format(checks="\n".join(checks))
    statements = [
        "SET LOCAL search_path = pg_catalog",
        "SET LOCAL TIME ZONE 'UTC'",
        lock,
        preflight,
    ]
    statements.extend(
        f"DROP TABLE {table_name} RESTRICT"
        for table_name in reversed(TABLE_CREATION_ORDER)
    )
    statements.extend(
        [
            "DROP FUNCTION ops.reject_immutable_mutation() RESTRICT",
            "DROP FUNCTION ops.touch_mutable_row() RESTRICT",
        ]
    )
    return tuple(statements)


def _render_statement_tuple(name: str, statements: Sequence[str]) -> str:
    lines = [f"{name}: tuple[str, ...] = ("]
    lines.extend(
        f"    {json.dumps(statement, ensure_ascii=False)}," for statement in statements
    )
    lines.append(")")
    return "\n".join(lines)


def render_revision(contract: Mapping[str, Any]) -> bytes:
    upgrade = render_upgrade_statements(contract)
    downgrade = render_downgrade_statements()
    text = f'''\
"""Install the exact ST-0303 IAM/OPS table contract.

Revision ID: {REVISION}
Revises: {DOWN_REVISION}
Create Date: 2026-08-03

RAOS metadata:
- story: ST-0303
- requirement IDs: FR-019, FR-020
- architecture: MIG-001 SLICE-004/SLICE-005/SLICE-007 IAM/OPS subset
- runner version: {RUNNER_VERSION}
- server version: 180004
- risk class: B (additive tables, constraints, indexes, and triggers)
- estimated lock: additive catalog DDL; guarded ACCESS EXCLUSIVE on downgrade
- backfill job: none
- rollback category: reversible only while all 17 owned tables are empty; RESTRICT
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "{REVISION}"
down_revision: str | None = "{DOWN_REVISION}"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


{_render_statement_tuple("UPGRADE_STATEMENTS", upgrade)}


{_render_statement_tuple("DOWNGRADE_STATEMENTS", downgrade)}


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
'''
    return text.encode("utf-8")


CATALOG_TYPES: Final = {
    "bigint": "bigint",
    "boolean": "boolean",
    "integer": "integer",
    "jsonb": "jsonb",
    "smallint": "smallint",
    "text": "text",
    "timestamptz": "timestamp with time zone",
    "uuid": "uuid",
}


def _catalog_default(column: Mapping[str, Any]) -> str:
    default = column.get("default")
    if default is None:
        return ""
    _require(isinstance(default, str), "column default must be text")
    if default == "pg_catalog.uuidv7()":
        return "uuidv7()"
    if column.get("type") == "text" and default.startswith("'"):
        return default + "::text"
    return default


def _sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return str(value)
    return _sql_literal(value)


def _values(rows: Sequence[Sequence[object]]) -> str:
    _require(bool(rows), "expected validation rows are empty")
    return ",\n        ".join(
        "(" + ", ".join(_sql_value(value) for value in row) + ")" for row in rows
    )


def _constraint_rows(contract: Mapping[str, Any]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for table_name, table in _table_map(contract).items():
        schema, name = table_name.split(".", 1)
        for column_value in _sequence(table.get("columns"), "columns"):
            column = _mapping(column_value, "column")
            if column.get("nullable") is not False:
                continue
            column_name = str(column["name"])
            not_null_name = f"{name}_{column_name}_not_null"
            _require(
                len(not_null_name.encode("utf-8")) <= 63,
                "PostgreSQL 18.4 NOT NULL constraint name would be truncated",
            )
            rows.append(
                (
                    schema,
                    name,
                    not_null_name,
                    "n",
                    column_name,
                    "",
                    "",
                    "",
                    "",
                    "",
                    False,
                    False,
                    f"NOT NULL {column_name}",
                    None,
                )
            )
        rows.append(
            (
                schema,
                name,
                table["primary_key_name"],
                "p",
                ",".join(str(item) for item in table["primary_key"]),
                "",
                "",
                "",
                "",
                "",
                False,
                False,
                "PRIMARY KEY ("
                + ", ".join(str(item) for item in table["primary_key"])
                + ")",
                None,
            )
        )
        for item_value in _sequence(
            table.get("unique_constraints"), "unique constraints"
        ):
            item = _mapping(item_value, "unique constraint")
            columns = [str(value) for value in item["columns"]]
            rows.append(
                (
                    schema,
                    name,
                    item["name"],
                    "u",
                    ",".join(columns),
                    "",
                    "",
                    "",
                    "",
                    "",
                    False,
                    False,
                    "UNIQUE (" + ", ".join(columns) + ")",
                    None,
                )
            )
        for item_value in _sequence(
            table.get("check_constraints"), "check constraints"
        ):
            item = _mapping(item_value, "check constraint")
            constraint_name = str(item["name"])
            check_expression = CANONICAL_CHECK_EXPRESSIONS.get(constraint_name)
            _require(
                check_expression is not None,
                f"missing PostgreSQL 18.4 CHECK deparse: {constraint_name}",
            )
            rows.append(
                (
                    schema,
                    name,
                    constraint_name,
                    "c",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    False,
                    False,
                    f"CHECK ({check_expression})",
                    check_expression,
                )
            )
        for item_value in _sequence(table.get("foreign_keys"), "foreign keys"):
            item = _mapping(item_value, "foreign key")
            columns = [str(value) for value in item["columns"]]
            referenced_columns = [str(value) for value in item["referenced_columns"]]
            delete_action = str(item["on_delete"])
            definition = (
                "FOREIGN KEY ("
                + ", ".join(columns)
                + ") REFERENCES "
                + str(item["references"])
                + "("
                + ", ".join(referenced_columns)
                + f") ON DELETE {delete_action}"
            )
            if item["deferrable"]:
                definition += " DEFERRABLE"
                definition += (
                    " INITIALLY DEFERRED"
                    if item["initially_deferred"]
                    else " INITIALLY IMMEDIATE"
                )
            rows.append(
                (
                    schema,
                    name,
                    item["name"],
                    "f",
                    ",".join(columns),
                    item["references"],
                    ",".join(referenced_columns),
                    "a",
                    {"RESTRICT": "r", "SET NULL": "n"}[delete_action],
                    "s",
                    item["deferrable"],
                    item["initially_deferred"],
                    definition,
                    None,
                )
            )
    expected_check_names = {
        str(_mapping(item, "check constraint")["name"])
        for table in _table_map(contract).values()
        for item in _sequence(table.get("check_constraints"), "check constraints")
    }
    _require(
        expected_check_names == set(CANONICAL_CHECK_EXPRESSIONS),
        "PostgreSQL 18.4 CHECK deparse inventory differs from contract",
    )
    return rows


def _index_rows(contract: Mapping[str, Any]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    expected_expression_names: set[str] = set()
    expected_predicate_names: set[str] = set()
    for table_name, table in _table_map(contract).items():
        schema, name = table_name.split(".", 1)
        for item_value in _sequence(table.get("indexes"), "indexes"):
            item = _mapping(item_value, "index")
            index_name = str(item["name"])
            columns = [str(value) for value in item["columns"]]
            if item["expression"] is None:
                index_expression = None
                keys = ", ".join(columns)
            else:
                expected_expression_names.add(index_name)
                index_expression = CANONICAL_INDEX_EXPRESSIONS.get(index_name)
                _require(
                    index_expression is not None,
                    f"missing PostgreSQL 18.4 index expression deparse: {index_name}",
                )
                keys = index_expression
            if item["where"] is None:
                index_predicate = None
            else:
                expected_predicate_names.add(index_name)
                index_predicate = CANONICAL_INDEX_PREDICATES.get(index_name)
                _require(
                    index_predicate is not None,
                    f"missing PostgreSQL 18.4 index predicate deparse: {index_name}",
                )
            unique = "UNIQUE " if item["unique"] else ""
            index_definition = (
                f"CREATE {unique}INDEX {index_name} ON {table_name} "
                f"USING {item['method']} ({keys})"
            )
            include = [str(value) for value in item["include"]]
            if include:
                index_definition += " INCLUDE (" + ", ".join(include) + ")"
            if item["nulls_not_distinct"]:
                index_definition += " NULLS NOT DISTINCT"
            if index_predicate is not None:
                index_definition += f" WHERE {index_predicate}"
            rows.append(
                (
                    schema,
                    name,
                    index_name,
                    item["method"],
                    item["unique"],
                    item["nulls_not_distinct"],
                    ",".join(columns),
                    index_definition,
                    index_expression,
                    index_predicate,
                    str(item["description"]),
                )
            )
    _require(
        expected_expression_names == set(CANONICAL_INDEX_EXPRESSIONS),
        "PostgreSQL 18.4 index expression deparse inventory differs from contract",
    )
    _require(
        expected_predicate_names == set(CANONICAL_INDEX_PREDICATES),
        "PostgreSQL 18.4 index predicate deparse inventory differs from contract",
    )
    return rows


def _predecessor_revision_sha(root: Path) -> str:
    manifest = _mapping(
        shared.load_yaml(_regular_file(root, PREDECESSOR_PATH, "ST-0302 predecessor")),
        "ST-0302 predecessor",
    )
    generated = _sequence(manifest.get("generated_artifacts"), "predecessor artifacts")
    uri = "repo://migrations/versions/202608030002_foundation_schemas.py"
    matches = [
        _mapping(item, "predecessor artifact")
        for item in generated
        if _mapping(item, "predecessor artifact").get("uri") == uri
    ]
    _require(len(matches) == 1, "ST-0302 revision artifact differs")
    digest = matches[0].get("sha256")
    _require(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
        "ST-0302 revision digest is invalid",
    )
    return digest


def render_validation_sql(
    contract: Mapping[str, Any],
    revision_sha256: str,
    predecessor_revision_sha256: str,
    schema_rows: Sequence[tuple[object, ...]],
) -> bytes:
    table_rows: list[tuple[object, ...]] = []
    type_rows: list[tuple[object, ...]] = []
    column_rows: list[tuple[object, ...]] = []
    for table_name in TABLE_CREATION_ORDER:
        table = _table_map(contract)[table_name]
        schema, name = table_name.split(".", 1)
        table_rows.append((schema, name, table["purpose"]))
        type_rows.append((schema, name, name, f"_{name}"))
        for position, column_value in enumerate(
            _sequence(table.get("columns"), "columns"), start=1
        ):
            column = _mapping(column_value, "column")
            column_rows.append(
                (
                    schema,
                    name,
                    position,
                    column["name"],
                    CATALOG_TYPES[str(column["type"])],
                    not bool(column["nullable"]),
                    _catalog_default(column),
                    column["description"],
                )
            )
    constraint_rows = _constraint_rows(contract)
    index_rows = _index_rows(contract)
    trigger_rows = []
    expected_trigger_names: set[str] = set()
    for trigger_value in _sequence(contract.get("triggers"), "triggers"):
        trigger = _mapping(trigger_value, "trigger")
        schema, table_name = str(trigger["table"]).split(".", 1)
        trigger_name = str(trigger["name"])
        expected_trigger_names.add(trigger_name)
        trigger_definition = CANONICAL_TRIGGER_DEFINITIONS.get(trigger_name)
        _require(
            trigger_definition is not None,
            f"missing PostgreSQL 18.4 trigger deparse: {trigger_name}",
        )
        trigger_rows.append(
            (
                schema,
                table_name,
                trigger_name,
                trigger["function"],
                19 if trigger["events"] == ["UPDATE"] else 27,
                trigger_definition,
                trigger["comment"],
            )
        )
    _require(
        expected_trigger_names == set(CANONICAL_TRIGGER_DEFINITIONS),
        "PostgreSQL 18.4 trigger deparse inventory differs from contract",
    )
    touch_comment = _mapping(
        _sequence(contract.get("functions"), "functions")[0], "function"
    )["comment"]
    reject_comment = _mapping(
        _sequence(contract.get("functions"), "functions")[1], "function"
    )["comment"]
    anchor_sha = framework.REVISION_SPECS[0].sha256
    text = f"""\
-- ST-0303 deterministic PostgreSQL 18.4 IAM/OPS validation.
-- Execute as the migration owner after upgrading to revision {REVISION}.
DO $raos_st0303_validation$
DECLARE
    observed_count pg_catalog.int8;
BEGIN
    IF pg_catalog.current_setting('server_version_num')::pg_catalog.int4 <> 180004 THEN
        RAISE EXCEPTION 'ST0303_SERVER_VERSION_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('TimeZone') <> 'UTC' THEN
        RAISE EXCEPTION 'ST0303_TIMEZONE_MISMATCH';
    END IF;
    IF pg_catalog.current_setting('search_path') <> 'pg_catalog' THEN
        RAISE EXCEPTION 'ST0303_SEARCH_PATH_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(schema_rows)}
    ) AS expected(schema_name, schema_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    WHERE pg_catalog.pg_get_userbyid(namespace.nspowner) = current_user
      AND pg_catalog.obj_description(namespace.oid, 'pg_namespace')
              = expected.schema_comment
      AND (
          SELECT pg_catalog.array_agg(
                     acl.privilege_type ORDER BY acl.privilege_type
                 )
          FROM pg_catalog.aclexplode(
              COALESCE(
                  namespace.nspacl,
                  pg_catalog.acldefault('n', namespace.nspowner)
              )
          ) AS acl
          WHERE acl.grantee = namespace.nspowner
      ) = ARRAY['CREATE', 'USAGE']::pg_catalog.text[]
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  namespace.nspacl,
                  pg_catalog.acldefault('n', namespace.nspowner)
              )
          ) AS acl
          WHERE acl.grantee <> namespace.nspowner
      );
    IF observed_count <> 2 THEN
        RAISE EXCEPTION 'ST0303_SCHEMA_OWNER_OR_ACL_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = defaults.defaclnamespace
        WHERE defaults.defaclnamespace = 0
           OR namespace.nspname = ANY (
                  ARRAY['ops', 'iam', 'public']::pg_catalog.text[]
              )
    ) THEN
        RAISE EXCEPTION 'ST0303_DEFAULT_ACL_PRESENT';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM pg_catalog.pg_sequence AS sequence_record
    JOIN pg_catalog.pg_class AS sequence_relation
      ON sequence_relation.oid = sequence_record.seqrelid
    JOIN pg_catalog.pg_namespace AS sequence_namespace
      ON sequence_namespace.oid = sequence_relation.relnamespace
    JOIN pg_catalog.pg_depend AS dependency
      ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
     AND dependency.objid = sequence_relation.oid
     AND dependency.objsubid = 0
     AND dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
    JOIN pg_catalog.pg_class AS owned_relation
      ON owned_relation.oid = dependency.refobjid
    JOIN pg_catalog.pg_namespace AS owned_namespace
      ON owned_namespace.oid = owned_relation.relnamespace
    JOIN pg_catalog.pg_attribute AS owned_attribute
      ON owned_attribute.attrelid = owned_relation.oid
     AND owned_attribute.attnum = dependency.refobjsubid
    WHERE sequence_namespace.nspname = 'public'
      AND sequence_relation.relname = 'raos_migration_history_event_id_seq'
      AND pg_catalog.pg_get_userbyid(sequence_relation.relowner) = current_user
      AND sequence_relation.relkind = 'S'
      AND sequence_relation.relpersistence = 'p'
      AND pg_catalog.format_type(sequence_record.seqtypid, NULL) = 'bigint'
      AND sequence_record.seqstart = 1
      AND sequence_record.seqincrement = 1
      AND sequence_record.seqmin = 1
      AND sequence_record.seqmax = 9223372036854775807
      AND sequence_record.seqcache = 1
      AND sequence_record.seqcycle IS FALSE
      AND owned_namespace.nspname = 'public'
      AND owned_relation.relname = 'raos_migration_history'
      AND owned_attribute.attname = 'event_id'
      AND dependency.deptype = 'i';
    IF observed_count <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_sequence AS sequence_record
        JOIN pg_catalog.pg_class AS sequence_relation
          ON sequence_relation.oid = sequence_record.seqrelid
        JOIN pg_catalog.pg_namespace AS sequence_namespace
          ON sequence_namespace.oid = sequence_relation.relnamespace
        WHERE sequence_namespace.nspname = 'public'
    ) <> 1 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_depend AS dependency
        JOIN pg_catalog.pg_class AS sequence_relation
          ON sequence_relation.oid = dependency.objid
        JOIN pg_catalog.pg_namespace AS sequence_namespace
          ON sequence_namespace.oid = sequence_relation.relnamespace
        WHERE dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
          AND dependency.objsubid = 0
          AND dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
          AND sequence_namespace.nspname = 'public'
          AND sequence_relation.relname =
              'raos_migration_history_event_id_seq'
    ) <> 1 THEN
        RAISE EXCEPTION 'ST0303_PUBLIC_SEQUENCE_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(table_rows)}
    ) AS expected(schema_name, table_name, table_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    WHERE pg_catalog.pg_get_userbyid(relation.relowner) = current_user
      AND relation.relpersistence = 'p'
      AND relation.relreplident = 'd'
      AND relation.relispartition IS FALSE
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.pg_inherits AS inheritance
          WHERE inheritance.inhrelid = relation.oid
             OR inheritance.inhparent = relation.oid
      )
      AND relation.relrowsecurity IS FALSE
      AND relation.relforcerowsecurity IS FALSE
      AND pg_catalog.obj_description(relation.oid, 'pg_class') = expected.table_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  relation.relacl,
                  pg_catalog.acldefault('r', relation.relowner)
              )
          ) AS acl
          WHERE acl.grantee <> relation.relowner
      );
    IF observed_count <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
    ) <> 17 THEN
        RAISE EXCEPTION 'ST0303_TABLE_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(type_rows)}
    ) AS expected(schema_name, table_name, row_type_name, array_type_name)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    JOIN pg_catalog.pg_type AS row_type
      ON row_type.typnamespace = namespace.oid
     AND row_type.typname = expected.row_type_name
     AND row_type.oid = relation.reltype
    JOIN pg_catalog.pg_type AS array_type
      ON array_type.typnamespace = namespace.oid
     AND array_type.typname = expected.array_type_name
    WHERE pg_catalog.pg_get_userbyid(row_type.typowner) = current_user
      AND pg_catalog.pg_get_userbyid(array_type.typowner) = current_user
      AND row_type.typtype = 'c'
      AND row_type.typelem = 0
      AND row_type.typarray = array_type.oid
      AND row_type.typrelid = relation.oid
      AND row_type.typacl IS NULL
      AND pg_catalog.obj_description(row_type.oid, 'pg_type') IS NULL
      AND array_type.typtype = 'b'
      AND array_type.typelem = row_type.oid
      AND array_type.typarray = 0
      AND array_type.typrelid = 0
      AND array_type.typacl IS NULL
      AND pg_catalog.obj_description(array_type.oid, 'pg_type') IS NULL;
    IF observed_count <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_type AS object_type
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = object_type.typnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
    ) <> 34 THEN
        RAISE EXCEPTION 'ST0303_UNEXPECTED_OBJECT_CATALOG_MISMATCH';
    END IF;

    SELECT
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND (
               relation.relkind NOT IN ('r', 'i')
               OR pg_catalog.pg_get_userbyid(relation.relowner) <> current_user
               OR relation.relpersistence <> 'p'
               OR relation.relispartition IS TRUE
           ))
        +
        (SELECT CASE WHEN pg_catalog.count(*) = 95 THEN 0 ELSE 1 END
         FROM pg_catalog.pg_class AS relation
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_cast AS cast_record
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   cast_record.castsource, cast_record.casttarget
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_transform AS transform_record
         JOIN pg_catalog.pg_type AS object_type
           ON object_type.oid = transform_record.trftype
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = object_type.typnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_rewrite AS rewrite_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = rewrite_record.ev_class
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_policy AS policy_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = policy_record.polrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_collation AS collation_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = collation_record.collnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_conversion AS conversion_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = conversion_record.connamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_operator AS operator_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_record.oprnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_opclass AS operator_class
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_class.opcnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_opfamily AS operator_family
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = operator_family.opfnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_amop AS access_operator
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   access_operator.amoplefttype,
                   access_operator.amoprighttype
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_amproc AS access_procedure
         WHERE EXISTS (
             SELECT 1
             FROM pg_catalog.pg_type AS object_type
             JOIN pg_catalog.pg_namespace AS namespace
               ON namespace.oid = object_type.typnamespace
             WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
               AND object_type.oid IN (
                   access_procedure.amproclefttype,
                   access_procedure.amprocrighttype
               )
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_config AS search_configuration
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_configuration.cfgnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_dict AS search_dictionary
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_dictionary.dictnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_parser AS search_parser
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_parser.prsnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_ts_template AS search_template
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = search_template.tmplnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_statistic_ext AS statistics_record
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = statistics_record.stxnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication_rel AS publication_relation
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = publication_relation.prrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication_namespace AS publication_namespace
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = publication_namespace.pnnspid
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_publication)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_subscription AS subscription_record
         WHERE subscription_record.subdbid = (
             SELECT database_record.oid
             FROM pg_catalog.pg_database AS database_record
             WHERE database_record.datname = pg_catalog.current_database()
         ))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_largeobject_metadata)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_foreign_data_wrapper)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_foreign_server)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_inherits AS inheritance
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid IN (inheritance.inhrelid, inheritance.inhparent)
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_partitioned_table AS partitioned
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = partitioned.partrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[]))
        +
        (SELECT CASE WHEN pg_catalog.count(*) = 80 THEN 0 ELSE 1 END
         FROM pg_catalog.pg_trigger AS trigger_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = trigger_record.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND trigger_record.tgisinternal IS TRUE)
        +
        (SELECT pg_catalog.count(*)
         FROM pg_catalog.pg_trigger AS trigger_record
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = trigger_record.tgrelid
         JOIN pg_catalog.pg_namespace AS namespace
           ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
           AND trigger_record.tgisinternal IS TRUE
           AND (
               trigger_record.tgenabled <> 'O'
               OR trigger_record.tgconstraint = 0
               OR trigger_record.tgparentid <> 0
               OR pg_catalog.obj_description(
                      trigger_record.oid, 'pg_trigger'
                  ) IS NOT NULL
           ))
    INTO observed_count;
    IF observed_count <> 0 THEN
        RAISE EXCEPTION 'ST0303_UNEXPECTED_OBJECT_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(column_rows)}
    ) AS expected(
        schema_name, table_name, attribute_number, column_name, type_name,
        not_null, default_expression, column_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
     AND relation.relkind = 'r'
    JOIN pg_catalog.pg_attribute AS attribute
      ON attribute.attrelid = relation.oid
     AND attribute.attnum = expected.attribute_number
     AND attribute.attname = expected.column_name
     AND attribute.attisdropped IS FALSE
    LEFT JOIN pg_catalog.pg_attrdef AS default_value
      ON default_value.adrelid = relation.oid
     AND default_value.adnum = attribute.attnum
    WHERE pg_catalog.format_type(attribute.atttypid, attribute.atttypmod)
              = expected.type_name
      AND attribute.attnotnull = expected.not_null
      AND attribute.attidentity = ''
      AND attribute.attgenerated = ''
      AND COALESCE(
              pg_catalog.pg_get_expr(
                  default_value.adbin, default_value.adrelid, false
              ),
              ''
          ) = expected.default_expression
      AND pg_catalog.col_description(relation.oid, attribute.attnum)
              = expected.column_comment
      AND attribute.attacl IS NULL;
    IF observed_count <> 219 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_attribute AS attribute
        JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND attribute.attnum > 0
          AND attribute.attisdropped IS FALSE
    ) <> 219 OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS attribute
        JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND attribute.attnum > 0
          AND attribute.attisdropped IS TRUE
    ) THEN
        RAISE EXCEPTION 'ST0303_COLUMN_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(constraint_rows)}
    ) AS expected(
        schema_name, table_name, constraint_name, constraint_type,
        key_columns, target_table, target_columns, update_action, delete_action,
        match_type, is_deferrable, initially_deferred, constraint_definition,
        check_expression
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
    JOIN pg_catalog.pg_constraint AS constraint_record
      ON constraint_record.conrelid = relation.oid
     AND constraint_record.conname = expected.constraint_name
     AND constraint_record.contype = expected.constraint_type
    LEFT JOIN pg_catalog.pg_class AS target_relation
      ON target_relation.oid = constraint_record.confrelid
    LEFT JOIN pg_catalog.pg_namespace AS target_namespace
      ON target_namespace.oid = target_relation.relnamespace
    LEFT JOIN pg_catalog.pg_class AS constraint_index_relation
      ON constraint_index_relation.oid = constraint_record.conindid
    LEFT JOIN pg_catalog.pg_index AS constraint_index
      ON constraint_index.indexrelid = constraint_record.conindid
    WHERE constraint_record.convalidated IS TRUE
      AND constraint_record.conenforced IS TRUE
      AND constraint_record.conislocal IS TRUE
      AND constraint_record.coninhcount = 0
      AND constraint_record.connoinherit
              = (expected.constraint_type = ANY (
                    ARRAY['p', 'u', 'f']::pg_catalog.text[]
                ))
      AND constraint_record.conparentid = 0
      AND constraint_record.conperiod IS FALSE
      AND constraint_record.connamespace = namespace.oid
      AND (
          (
              expected.constraint_type = ANY (
                  ARRAY['p', 'u']::pg_catalog.text[]
              )
              AND constraint_record.conindid <> 0
              AND constraint_index_relation.relkind = 'i'
              AND constraint_index_relation.relnamespace
                      = constraint_record.connamespace
              AND constraint_index_relation.relname
                      = constraint_record.conname
              AND constraint_index.indrelid = constraint_record.conrelid
              AND constraint_index.indisunique IS TRUE
              AND constraint_index.indisvalid IS TRUE
              AND constraint_index.indisready IS TRUE
              AND constraint_index.indisprimary
                      = (expected.constraint_type = 'p')
          )
          OR (
              expected.constraint_type = 'f'
              AND constraint_record.conindid <> 0
              AND constraint_index_relation.relkind = 'i'
              AND constraint_index.indrelid = constraint_record.confrelid
              AND constraint_index.indisunique IS TRUE
              AND constraint_index.indisvalid IS TRUE
              AND constraint_index.indisready IS TRUE
          )
          OR (
              expected.constraint_type = ANY (
                  ARRAY['c', 'n']::pg_catalog.text[]
              )
              AND constraint_record.conindid = 0
          )
      )
      AND CASE WHEN expected.constraint_type = 'c' THEN '' ELSE COALESCE((
              SELECT pg_catalog.string_agg(
                  attribute.attname, ',' ORDER BY key_item.ordinality
              )
              FROM pg_catalog.unnest(constraint_record.conkey)
                   WITH ORDINALITY AS key_item(attribute_number, ordinality)
              JOIN pg_catalog.pg_attribute AS attribute
                ON attribute.attrelid = constraint_record.conrelid
               AND attribute.attnum = key_item.attribute_number
          ), '') END = expected.key_columns
      AND COALESCE(target_namespace.nspname || '.' || target_relation.relname, '')
              = expected.target_table
      AND COALESCE((
          SELECT pg_catalog.string_agg(attribute.attname, ',' ORDER BY key_item.ordinality)
          FROM pg_catalog.unnest(constraint_record.confkey)
               WITH ORDINALITY AS key_item(attribute_number, ordinality)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid = constraint_record.confrelid
           AND attribute.attnum = key_item.attribute_number
      ), '') = expected.target_columns
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confupdtype::pg_catalog.text
               ELSE '' END = expected.update_action
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confdeltype::pg_catalog.text
               ELSE '' END = expected.delete_action
      AND CASE WHEN expected.constraint_type = 'f'
               THEN constraint_record.confmatchtype::pg_catalog.text
               ELSE '' END = expected.match_type
      AND constraint_record.condeferrable = expected.is_deferrable
      AND constraint_record.condeferred = expected.initially_deferred
      AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              = expected.constraint_definition
      AND pg_catalog.pg_get_expr(
              constraint_record.conbin, constraint_record.conrelid, false
          ) IS NOT DISTINCT FROM expected.check_expression
      AND pg_catalog.obj_description(
              constraint_record.oid, 'pg_constraint'
          ) IS NULL
      AND pg_catalog.obj_description(
              constraint_record.conindid, 'pg_class'
          ) IS NULL;
    IF observed_count <> 267 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
    ) <> 267 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'n'
    ) <> 151 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'p'
    ) <> 17 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'u'
    ) <> 13 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'c'
    ) <> 66 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND relation.relkind = 'r'
          AND constraint_record.contype = 'f'
    ) <> 20 THEN
        RAISE EXCEPTION 'ST0303_CONSTRAINT_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(index_rows)}
    ) AS expected(
        schema_name, table_name, index_name, method_name, is_unique,
        nulls_not_distinct, key_columns, index_definition, index_expression,
        index_predicate, index_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS table_relation
      ON table_relation.relnamespace = namespace.oid
     AND table_relation.relname = expected.table_name
    JOIN pg_catalog.pg_index AS index_record
      ON index_record.indrelid = table_relation.oid
    JOIN pg_catalog.pg_class AS index_relation
      ON index_relation.oid = index_record.indexrelid
     AND index_relation.relname = expected.index_name
    JOIN pg_catalog.pg_am AS access_method
      ON access_method.oid = index_relation.relam
     AND access_method.amname = expected.method_name
    WHERE NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
      AND index_record.indisprimary IS FALSE
      AND index_record.indisunique = expected.is_unique
      AND index_record.indnullsnotdistinct = expected.nulls_not_distinct
      AND index_record.indisvalid IS TRUE
      AND index_record.indisready IS TRUE
      AND index_record.indislive IS TRUE
      AND index_record.indnkeyatts = index_record.indnatts
      AND pg_catalog.pg_get_userbyid(index_relation.relowner) = current_user
      AND COALESCE((
          SELECT pg_catalog.string_agg(attribute.attname, ',' ORDER BY key_item.ordinality)
          FROM pg_catalog.unnest(index_record.indkey)
               WITH ORDINALITY AS key_item(attribute_number, ordinality)
          JOIN pg_catalog.pg_attribute AS attribute
            ON attribute.attrelid = index_record.indrelid
           AND attribute.attnum = key_item.attribute_number
          WHERE key_item.ordinality <= index_record.indnkeyatts
      ), '') = expected.key_columns
      AND pg_catalog.pg_get_indexdef(index_record.indexrelid, 0, false)
              = expected.index_definition
      AND pg_catalog.pg_get_expr(
              index_record.indexprs, index_record.indrelid, false
          ) IS NOT DISTINCT FROM expected.index_expression
      AND pg_catalog.pg_get_expr(
              index_record.indpred, index_record.indrelid, false
          ) IS NOT DISTINCT FROM expected.index_predicate
      AND pg_catalog.obj_description(index_relation.oid, 'pg_class')
              IS NOT DISTINCT FROM NULLIF(expected.index_comment, '');
    IF observed_count <> 48 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_record
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_record.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
    ) <> 48 THEN
        RAISE EXCEPTION 'ST0303_INDEX_CATALOG_MISMATCH';
    END IF;
    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_class AS index_relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = index_relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND index_relation.relkind = 'i'
          AND pg_catalog.pg_get_userbyid(index_relation.relowner) = current_user
    ) <> 78 THEN
        RAISE EXCEPTION 'ST0303_INDEX_OWNER_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        ('ops', 'touch_mutable_row', {_sql_literal(TOUCH_FUNCTION_BODY)}, {_sql_literal(touch_comment)}),
        ('ops', 'reject_immutable_mutation', {_sql_literal(REJECT_FUNCTION_BODY)}, {_sql_literal(reject_comment)})
    ) AS expected(schema_name, function_name, function_source, function_comment)
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_proc AS routine
      ON routine.pronamespace = namespace.oid
     AND routine.proname = expected.function_name
     AND routine.pronargs = 0
    JOIN pg_catalog.pg_language AS language
      ON language.oid = routine.prolang
     AND language.lanname = 'plpgsql'
    WHERE routine.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype
      AND routine.prokind = 'f'
      AND routine.prosecdef IS FALSE
      AND routine.provolatile = 'v'
      AND routine.proconfig = ARRAY['search_path=pg_catalog']::pg_catalog.text[]
      AND routine.prosrc = expected.function_source
      AND pg_catalog.pg_get_userbyid(routine.proowner) = current_user
      AND pg_catalog.obj_description(routine.oid, 'pg_proc') = expected.function_comment
      AND NOT EXISTS (
          SELECT 1
          FROM pg_catalog.aclexplode(
              COALESCE(
                  routine.proacl,
                  pg_catalog.acldefault('f', routine.proowner)
              )
          ) AS acl
          WHERE acl.grantee <> routine.proowner
      );
    IF observed_count <> 2 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = routine.pronamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
    ) <> 2 THEN
        RAISE EXCEPTION 'ST0303_FUNCTION_CATALOG_MISMATCH';
    END IF;

    SELECT pg_catalog.count(*) INTO observed_count
    FROM (VALUES
        {_values(trigger_rows)}
    ) AS expected(
        schema_name, table_name, trigger_name, function_signature,
        trigger_type, trigger_definition, trigger_comment
    )
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.nspname = expected.schema_name
    JOIN pg_catalog.pg_class AS relation
      ON relation.relnamespace = namespace.oid
     AND relation.relname = expected.table_name
    JOIN pg_catalog.pg_trigger AS trigger_record
      ON trigger_record.tgrelid = relation.oid
     AND trigger_record.tgname = expected.trigger_name
    WHERE trigger_record.tgisinternal IS FALSE
      AND trigger_record.tgenabled = 'O'
      AND trigger_record.tgtype = expected.trigger_type
      AND trigger_record.tgfoid = pg_catalog.to_regprocedure(expected.function_signature)
      AND trigger_record.tgqual IS NULL
      AND trigger_record.tgnargs = 0
      AND trigger_record.tgattr::pg_catalog.text = ''
      AND pg_catalog.octet_length(trigger_record.tgargs) = 0
      AND trigger_record.tgconstraint = 0
      AND trigger_record.tgdeferrable IS FALSE
      AND trigger_record.tginitdeferred IS FALSE
      AND trigger_record.tgparentid = 0
      AND trigger_record.tgoldtable IS NULL
      AND trigger_record.tgnewtable IS NULL
      AND pg_catalog.pg_get_triggerdef(trigger_record.oid, false)
              = expected.trigger_definition
      AND pg_catalog.obj_description(trigger_record.oid, 'pg_trigger')
              = expected.trigger_comment;
    IF observed_count <> 4 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_trigger AS trigger_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = trigger_record.tgrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY (ARRAY['ops', 'iam']::pg_catalog.text[])
          AND trigger_record.tgisinternal IS FALSE
    ) <> 4 THEN
        RAISE EXCEPTION 'ST0303_TRIGGER_CATALOG_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conname = ANY (ARRAY[
            'fk_ops_job_site_id',
            'fk_iam_break_glass_record_incident_id'
        ]::pg_catalog.text[])
    ) OR pg_catalog.to_regclass('ops.ix_ops_job_site_id') IS NULL
       OR pg_catalog.to_regclass('iam.ix_iam_break_glass_record_incident_id') IS NULL THEN
        RAISE EXCEPTION 'ST0303_DEFERRED_FOREIGN_KEY_BOUNDARY_MISMATCH';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
          AND constraint_record.contype = 'c'
    ) <> 11 OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_index AS index_record
        WHERE index_record.indrelid = 'ops.job'::pg_catalog.regclass
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_constraint AS constraint_record
              WHERE constraint_record.conindid = index_record.indexrelid
          )
    ) <> 9 OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'ops.job'::pg_catalog.regclass
          AND constraint_record.conname = 'ck_ops_job_status'
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              LIKE ALL (ARRAY[
                  '%''REQUESTED''%', '%''QUEUED''%', '%''RUNNING''%',
                  '%''SUCCEEDED''%', '%''FAILED_RETRYABLE''%',
                  '%''RETRY_SCHEDULED''%', '%''FAILED_TERMINAL''%',
                  '%''QUARANTINED''%', '%''CANCELLED''%', '%''EXPIRED''%'
              ]::pg_catalog.text[])
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              NOT LIKE ALL (ARRAY['%''PENDING''%', '%''READY''%', '%''FAILED''%']::pg_catalog.text[])
    ) THEN
        RAISE EXCEPTION 'ST0303_JOB_CONTRACT_MISMATCH';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_record.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        JOIN pg_catalog.pg_index AS index_record
          ON index_record.indexrelid = constraint_record.conindid
        WHERE namespace.nspname = 'ops'
          AND relation.relname = 'runtime_setting_version'
          AND constraint_record.conname = 'uq_ops_setting_version'
          AND constraint_record.contype = 'u'
          AND index_record.indnullsnotdistinct IS FALSE
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS constraint_record
        WHERE constraint_record.conrelid = 'iam.break_glass_record'::pg_catalog.regclass
          AND constraint_record.contype = 'c'
          AND pg_catalog.pg_get_constraintdef(constraint_record.oid, false)
              LIKE '%principal_id%approved_by_principal_id%'
    ) THEN
        RAISE EXCEPTION 'ST0303_CANONICAL_LIMITATION_DRIFT';
    END IF;

    IF (SELECT pg_catalog.count(*) FROM public.raos_migration_version) <> 1
       OR NOT EXISTS (
           SELECT 1 FROM public.raos_migration_version
           WHERE version_num = '{REVISION}'
       ) THEN
        RAISE EXCEPTION 'ST0303_MIGRATION_VERSION_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.count(*) FROM public.raos_migration_history) <> 5
       OR NOT EXISTS (
        SELECT 1
        FROM public.raos_migration_history AS anchor
        JOIN public.raos_migration_history AS foundation_started
          ON foundation_started.event_id > anchor.event_id
        JOIN public.raos_migration_history AS foundation_succeeded
          ON foundation_succeeded.event_id > foundation_started.event_id
        JOIN public.raos_migration_history AS iam_ops_started
          ON iam_ops_started.event_id > foundation_succeeded.event_id
        JOIN public.raos_migration_history AS iam_ops_succeeded
          ON iam_ops_succeeded.event_id > iam_ops_started.event_id
        JOIN public.raos_migration_version AS version
          ON version.version_num = '{REVISION}'
        WHERE anchor.revision_id = '202608030001'
          AND anchor.story_id = 'ST-0301'
          AND anchor.direction = 'UPGRADE'
          AND anchor.status = 'SUCCEEDED'
          AND anchor.source_sha256 = '{anchor_sha}'
          AND anchor.runner_version = '1.0.0'
          AND foundation_started.revision_id = '{DOWN_REVISION}'
          AND foundation_started.story_id = 'ST-0302'
          AND foundation_started.direction = 'UPGRADE'
          AND foundation_started.status = 'STARTED'
          AND foundation_started.source_sha256 = '{predecessor_revision_sha256}'
          AND foundation_started.runner_version = '1.1.0'
          AND foundation_succeeded.revision_id = '{DOWN_REVISION}'
          AND foundation_succeeded.story_id = 'ST-0302'
          AND foundation_succeeded.direction = 'UPGRADE'
          AND foundation_succeeded.status = 'SUCCEEDED'
          AND foundation_succeeded.source_sha256 = '{predecessor_revision_sha256}'
          AND foundation_succeeded.runner_version = '1.1.0'
          AND iam_ops_started.revision_id = '{REVISION}'
          AND iam_ops_started.story_id = 'ST-0303'
          AND iam_ops_started.direction = 'UPGRADE'
          AND iam_ops_started.status = 'STARTED'
          AND iam_ops_started.source_sha256 = '{revision_sha256}'
          AND iam_ops_started.runner_version = '{RUNNER_VERSION}'
          AND iam_ops_succeeded.revision_id = '{REVISION}'
          AND iam_ops_succeeded.story_id = 'ST-0303'
          AND iam_ops_succeeded.direction = 'UPGRADE'
          AND iam_ops_succeeded.status = 'SUCCEEDED'
          AND iam_ops_succeeded.source_sha256 = '{revision_sha256}'
          AND iam_ops_succeeded.runner_version = '{RUNNER_VERSION}'
          AND anchor.server_version_num = 180004
          AND foundation_started.server_version_num = 180004
          AND foundation_succeeded.server_version_num = 180004
          AND iam_ops_started.server_version_num = 180004
          AND iam_ops_succeeded.server_version_num = 180004
          AND anchor.error_code IS NULL
          AND foundation_started.error_code IS NULL
          AND foundation_succeeded.error_code IS NULL
          AND iam_ops_started.error_code IS NULL
          AND iam_ops_succeeded.error_code IS NULL
          AND anchor.attempt_id <> foundation_started.attempt_id
          AND foundation_started.attempt_id = foundation_succeeded.attempt_id
          AND foundation_succeeded.attempt_id <> iam_ops_started.attempt_id
          AND iam_ops_started.attempt_id = iam_ops_succeeded.attempt_id
          AND foundation_started.transaction_id <> foundation_succeeded.transaction_id
          AND iam_ops_started.transaction_id <> iam_ops_succeeded.transaction_id
          AND iam_ops_succeeded.transaction_id = version.xmin::pg_catalog.text
          AND iam_ops_succeeded.xmin::pg_catalog.text = version.xmin::pg_catalog.text
    ) THEN
        RAISE EXCEPTION 'ST0303_MIGRATION_HISTORY_MISMATCH';
    END IF;
END
$raos_st0303_validation$;

SELECT
    'PASS'::pg_catalog.text AS status,
    17::pg_catalog.int4 AS table_count,
    219::pg_catalog.int4 AS column_count,
    20::pg_catalog.int4 AS immediate_foreign_key_count,
    2::pg_catalog.int4 AS deferred_foreign_key_count;
"""
    return text.encode("utf-8")


VALIDATION_ASSERTIONS: Final = (
    "EXACT_POSTGRESQL_18_4_UTC_PG_CATALOG_SEARCH_PATH",
    "EXACT_SCHEMA_OWNER_AND_ACL",
    "NO_GLOBAL_OR_STORY_SCHEMA_DEFAULT_ACL",
    "EXACT_17_TABLE_219_COLUMN_CATALOG",
    "EXACT_17_PK_13_UQ_66_CHECK_20_IMMEDIATE_FK",
    "EXACT_48_STANDALONE_AND_78_TOTAL_INDEXES",
    "EXACT_CURRENT_MIGRATION_ROLE_OWNERSHIP",
    "EXACT_TWO_SECURITY_INVOKER_FUNCTIONS",
    "EXACT_FOUR_TRIGGERS",
    "EXACT_TWO_DEFERRED_FKS_ABSENT_WITH_COLUMNS_AND_INDEXES_PRESENT",
    "EXACT_ST0002_FINAL_JOB_IDENTITY",
    "PRESERVE_DOCUMENTED_CANONICAL_LIMITATIONS",
    "EXACT_HEAD_AND_FIVE_EVENT_SUCCESS_HISTORY",
)


def render_catalog(
    root: Path,
    contract: Mapping[str, Any],
    revision: bytes,
    validation: bytes,
) -> bytes:
    tables = _sequence(contract.get("tables"), "tables")
    functions = _sequence(contract.get("functions"), "functions")
    document = {
        "document": {
            "id": "RAOS-IAM-OPS-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0303",
            "formal_verification": "NOT_EXECUTED",
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "sha256": _sha256(
                _regular_file(root, CONTRACT_PATH, "ST-0303 contract").read_bytes()
            ),
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "story_id": "ST-0303",
            "path": REVISION_PATH.as_posix(),
            "sha256": _sha256(revision),
            "runner_version": RUNNER_VERSION,
            "server_version_num": 180004,
            "transaction": "ALEMBIC_PER_REVISION",
        },
        "validation": {
            "path": VALIDATION_PATH.as_posix(),
            "sha256": _sha256(validation),
            "assertions": list(VALIDATION_ASSERTIONS),
            "success_row": {
                "status": "PASS",
                "table_count": 17,
                "column_count": 219,
                "immediate_foreign_key_count": 20,
                "deferred_foreign_key_count": 2,
            },
        },
        "inventory": dict(EXPECTED_INVENTORY),
        "creation_order": list(TABLE_CREATION_ORDER),
        "ownership": {
            "expected_owner": "CURRENT_MIGRATION_ROLE",
            "tables": [
                str(_mapping(item, "table")["fully_qualified_name"]) for item in tables
            ],
            "functions": [
                str(_mapping(item, "function")["fully_qualified_name"])
                for item in functions
            ],
            "indexes": "INHERIT_TABLE_OWNER_AND_VALIDATE_EXACT_COUNT",
            "constraints": "INHERENT_TABLE_OBJECT",
            "triggers": "INHERENT_TABLE_OBJECT",
            "owner_drift": "REJECT",
        },
        "tables": tables,
        "deferred_foreign_key_policy": contract["deferred_foreign_key_policy"],
        "functions": functions,
        "triggers": contract["triggers"],
        "security": contract["security"],
        "downgrade": contract["downgrade"],
        "known_canonical_limitations": contract["known_canonical_limitations"],
        "boundary": contract["boundary"],
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _regular_file(root, relative, "ST-0303 source artifact").read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _validate_predecessor_source_closure(root: Path) -> None:
    manifest = _mapping(
        shared.load_yaml(_regular_file(root, PREDECESSOR_PATH, "ST-0302 predecessor")),
        "ST-0302 predecessor",
    )
    source_artifacts = _sequence(
        manifest.get("source_artifacts"), "ST-0302 source artifacts"
    )
    observed_paths: list[Path] = []
    for artifact_value in source_artifacts:
        artifact = _mapping(artifact_value, "ST-0302 source artifact")
        uri = artifact.get("uri")
        _require(
            isinstance(uri, str) and uri.startswith("repo://"),
            "ST-0302 source artifact URI differs",
        )
        observed_paths.append(Path(uri.removeprefix("repo://")))
    _require(
        manifest.get("source_artifact_count") == len(source_artifacts) == 43,
        "ST-0302 source closure count differs",
    )
    _require(
        tuple(observed_paths) == PREDECESSOR_SOURCE_ARTIFACT_PATHS,
        "ST-0302 source closure paths differ",
    )


def render_manifest(
    root: Path,
    contract: Mapping[str, Any],
    outputs: Mapping[Path, bytes],
) -> bytes:
    _validate_predecessor_source_closure(root)
    _require(
        len(PREDECESSOR_SOURCE_ARTIFACT_PATHS) == 43,
        "ST-0302 source closure count differs",
    )
    _require(
        len(CURRENT_SOURCE_ARTIFACT_PATHS) == 11,
        "ST-0303 current source count differs",
    )
    _require(
        len(SOURCE_ARTIFACT_PATHS)
        == len(set(SOURCE_ARTIFACT_PATHS))
        == EXPECTED_SOURCE_ARTIFACT_COUNT,
        "cumulative source inventory differs",
    )
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
            "id": "RAOS-IAM-OPS-SCHEMA-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0303",
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
                "story_id": "ST-0302",
                "uri": f"repo://{PREDECESSOR_PATH.as_posix()}",
            },
            "allowlisted_security_normalization": contract["source_precedence"][
                "allowed_security_normalizations"
            ],
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": 180004,
        },
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "source_inventory_contract": {
            "status": "FINAL",
            "scope": "ST0302_CURRENT_SOURCE_CLOSURE_PLUS_ST0303_ACTIVE_SOURCES",
            "predecessor_source_artifact_count": len(PREDECESSOR_SOURCE_ARTIFACT_PATHS),
            "current_story_source_artifact_count": len(CURRENT_SOURCE_ARTIFACT_PATHS),
            "total_source_artifact_count": len(SOURCE_ARTIFACT_PATHS),
            "ordering": "ST0302_SOURCE_CLOSURE_THEN_ST0303_ACTIVE_SOURCES",
            "hash_binding": "EXACT_CURRENT_REPOSITORY_BYTES",
            "missing_duplicate_or_unlisted_source": "REJECTED",
            "shared_source_regeneration": "COMPLETED_AFTER_SECOND_FREEZE",
        },
        "boundary": {
            **dict(_mapping(contract["boundary"], "boundary")),
            "source_inventory_status": "FINAL_CUMULATIVE_ACTIVE_STORY_CLOSURE",
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
    framework.assert_generation_toolchain(root)
    _verify_inputs(root)
    contract = _load_contract(root)
    revision = render_revision(contract)
    validation = render_validation_sql(
        contract,
        _sha256(revision),
        _predecessor_revision_sha(root),
        _foundation_schema_rows(root),
    )
    catalog = render_catalog(root, contract, revision, validation)
    outputs: dict[Path, bytes] = {
        REVISION_PATH: revision,
        CATALOG_PATH: catalog,
        VALIDATION_PATH: validation,
    }
    outputs[MANIFEST_PATH] = render_manifest(root, contract, outputs)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output order differs")
    return outputs


@dataclass(slots=True)
class _StagedOutput:
    relative: Path
    descriptors: list[int]
    parent_descriptor: int
    temporary_name: str
    previous_content: bytes | None
    previous_mode: int | None
    committed: bool = False


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _write_descriptor(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise RuntimeError("generated artifact short write")
        view = view[written:]


def _stage_output(
    root: Path,
    relative: Path,
    content: bytes,
    ordinal: int,
) -> _StagedOutput:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError("unsafe generated path")
    root_metadata = root.lstat()
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("generated root must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    descriptor = os.open(root, directory_flags)
    descriptors.append(descriptor)
    temporary_name = ""
    try:
        for part in relative.parent.parts:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(part, directory_flags, dir_fd=descriptor)
            descriptor = child
            descriptors.append(descriptor)

        previous_content: bytes | None
        previous_mode: int | None
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is None:
            previous_content = None
            previous_mode = None
        else:
            if not stat.S_ISREG(target_metadata.st_mode):
                raise RuntimeError(
                    "generated target must be a regular non-symlink file"
                )
            if stat.S_IMODE(target_metadata.st_mode) != 0o644:
                raise RuntimeError("generated target mode differs from 0644")
            previous_descriptor = os.open(
                relative.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                previous_content = _read_descriptor(previous_descriptor)
            finally:
                os.close(previous_descriptor)
            previous_mode = stat.S_IMODE(target_metadata.st_mode)

        temporary_name = f".{relative.name}.st0303-{os.getpid()}-{ordinal}"
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=descriptor,
        )
        try:
            _write_descriptor(temporary_descriptor, content)
            os.fchmod(temporary_descriptor, 0o644)
            os.fsync(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        return _StagedOutput(
            relative=relative,
            descriptors=descriptors,
            parent_descriptor=descriptor,
            temporary_name=temporary_name,
            previous_content=previous_content,
            previous_mode=previous_mode,
        )
    except BaseException:
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=descriptor)
            except FileNotFoundError:
                pass
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
        raise


def _restore_output(stage: _StagedOutput, ordinal: int) -> None:
    target_name = stage.relative.name
    if stage.previous_content is None:
        try:
            os.unlink(target_name, dir_fd=stage.parent_descriptor)
        except FileNotFoundError:
            pass
        os.fsync(stage.parent_descriptor)
        return
    temporary_name = f".{target_name}.st0303-rollback-{os.getpid()}-{ordinal}"
    temporary_descriptor = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        stage.previous_mode or 0o644,
        dir_fd=stage.parent_descriptor,
    )
    try:
        _write_descriptor(temporary_descriptor, stage.previous_content)
        os.fchmod(temporary_descriptor, stage.previous_mode or 0o644)
        os.fsync(temporary_descriptor)
    finally:
        os.close(temporary_descriptor)
    try:
        os.replace(
            temporary_name,
            target_name,
            src_dir_fd=stage.parent_descriptor,
            dst_dir_fd=stage.parent_descriptor,
        )
        temporary_name = ""
        os.fsync(stage.parent_descriptor)
    finally:
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=stage.parent_descriptor)
            except FileNotFoundError:
                pass


def install_generated(root: Path = REPO_ROOT) -> None:
    outputs = render_outputs(root)
    staged: list[_StagedOutput] = []
    try:
        for ordinal, path in enumerate(GENERATED_PATHS):
            staged.append(_stage_output(root, path, outputs[path], ordinal))
        try:
            for stage in staged:
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
                    _restore_output(stage, ordinal)
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
            for opened in reversed(stage.descriptors):
                try:
                    os.close(opened)
                except OSError:
                    pass


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_outputs(root)
    for path in GENERATED_PATHS:
        target = _regular_file(root, path, "generated artifact")
        _require(
            stat.S_IMODE(target.stat().st_mode) == 0o644,
            "generated artifact mode differs from 0644",
        )
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
                "story_id": "ST-0303",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
