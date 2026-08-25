#!/usr/bin/env python3
"""Build the deterministic cumulative ST-0306 role and grant bundle."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import zipfile
import zlib
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
CONTRACT_PATH: Final = Path("changes/st-0306/contracts/database-roles-grants.v1.yaml")
README_PATH: Final = Path("changes/st-0306/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st0306_database_roles.py")
REVISION_PATH: Final = Path("migrations/versions/202608030006_database_roles.py")
CATALOG_PATH: Final = Path("changes/st-0306/generated/database-roles-grants.v1.json")
VALIDATION_PATH: Final = Path(
    "changes/st-0306/generated/database-roles-validation.v1.sql"
)
MANIFEST_PATH: Final = Path("changes/st-0306/manifest.yaml")
PREDECESSOR_MANIFEST_PATH: Final = Path("changes/st-0305/manifest.yaml")
UPSTREAM_ARCHIVE_PATH: Final = Path("docs/upstream/RAOS_03_data_model_package_v0.1.zip")
UPSTREAM_MEMBER: Final = (
    "RAOS_03_data_model_package_v0.1/sql/RAOS_03_002_roles_and_grants_v0.1.sql"
)
POLICY_SOURCE_PATH: Final = Path(
    "changes/st-0004/database/202607300013_content_expand.sql"
)
GENERATED_PATHS: Final = (
    REVISION_PATH,
    CATALOG_PATH,
    VALIDATION_PATH,
    MANIFEST_PATH,
)

REVISION: Final = "202608030006"
DOWN_REVISION: Final = "202608030005"
RUNNER_VERSION: Final = "1.5.0"
EXPECTED_SERVER_VERSION_NUM: Final = 180004
EXPECTED_CONTRACT_SHA256: Final = (
    "93f03ff2a762ff0d0b950b06a5b7416687ce20e44f7e7b7f6ea2a7ed2b873206"
)
EXPECTED_ARCHIVE_SHA256: Final = (
    "82597db880c80c632ac0337d583c91ba5defac827414ecee1b921f49d1f64357"
)
EXPECTED_MEMBER_SHA256: Final = (
    "6b9218df65e39ed5b5d38ca593a62ee544e9870296f32a7d7a819008a9d9803e"
)
EXPECTED_POLICY_SOURCE_SHA256: Final = (
    "cdb4ba3f94691425059b2282f343b0cdc82e6b82bb93fdbfe8dd3a6a3dd4290e"
)
EXPECTED_PREDECESSOR_MANIFEST_SHA256: Final = (
    "af6034f99374b427aee444a6048531a174f0d78ae58974b2456c2be97f3d33b9"
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python "
    "scripts/build_st0306_database_roles.py"
)

ROLES: Final = (
    "raos_migrator",
    "raos_api_rw",
    "raos_worker_rw",
    "raos_dispatcher_rw",
    "raos_projection_rw",
    "raos_public_ro",
    "raos_reporting_ro",
    "raos_auditor_ro",
)
SCHEMAS: Final = (
    "ops",
    "iam",
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
    "publishing",
    "freshness",
    "analytics",
    "finance",
    "readmodel",
)
RLS_TABLES: Final = (
    "editorial.article_disclosure_context",
    "editorial.article_methodology_binding",
    "editorial.article_template_version",
    "editorial.article_type_version",
    "editorial.content_schema_version",
    "editorial.editorial_methodology_version",
    "editorial.media_asset",
    "editorial.seo_metadata_version",
    "editorial.structured_data_manifest",
    "evidence.first_hand_experience_asset",
    "evidence.first_hand_experience_record",
)
RLS_POLICY_BASES: Final = (
    ("editorial.content_schema_version", "pl_content_schema"),
    ("editorial.article_type_version", "pl_article_type"),
    ("editorial.article_template_version", "pl_article_template"),
    ("editorial.editorial_methodology_version", "pl_methodology"),
    ("editorial.article_methodology_binding", "pl_article_methodology"),
    ("editorial.seo_metadata_version", "pl_seo_metadata"),
    ("editorial.structured_data_manifest", "pl_structured_data"),
    ("editorial.media_asset", "pl_media_asset"),
    ("evidence.first_hand_experience_record", "pl_first_hand_record"),
    ("evidence.first_hand_experience_asset", "pl_first_hand_asset"),
    ("editorial.article_disclosure_context", "pl_disclosure_context"),
)
AUDITOR_TABLES: Final = (
    "ops.audit_event",
    "iam.principal",
    "iam.principal_role_assignment",
    "iam.break_glass_record",
    "policy.policy_bundle",
    "policy.rule_version",
    "policy.quality_check_run",
    "policy.finding",
    "policy.quality_score",
    "policy.waiver",
    "policy.gate_decision",
    "publishing.review_assignment",
    "publishing.review_decision",
    "publishing.approval",
    "publishing.publication_snapshot",
    "publishing.publication_event",
    "publishing.rollback_record",
    "evidence.source_packet_version",
    "evidence.claim",
    "evidence.claim_evidence_link",
    *RLS_TABLES,
)
ABSENT_UPSTREAM_RELATIONS: Final = (
    "ops.audit_export",
    "ops.incident",
    "ops.incident_event",
    "ops.kill_switch_change",
    "ops.release",
)

PINNED_INPUTS: Final = {
    UPSTREAM_ARCHIVE_PATH.as_posix(): EXPECTED_ARCHIVE_SHA256,
    POLICY_SOURCE_PATH.as_posix(): EXPECTED_POLICY_SOURCE_SHA256,
    "changes/st-0304/contracts/domain-schema.v1.yaml": (
        "8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122"
    ),
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md": (
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c"
    ),
    "docs/upstream/key_documents/RAOS_03_migration_playbook_v0.1.md": (
        "d05d1d4ebe3f3904e58c104e0b1836bc897377dbf27f9019f57c3fc6440bd137"
    ),
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
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


def _load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    content = _read(root, CONTRACT_PATH, "ST-0306 contract")
    _require(_sha256(content) == EXPECTED_CONTRACT_SHA256, "contract digest differs")
    value = yaml.safe_load(content)
    contract = _mapping(value, "ST-0306 contract")
    story = _mapping(contract.get("story"), "story")
    _require(story.get("open_decisions") == [], "Story has an open decision")
    _require(tuple(contract.get("roles", ())) == ROLES, "role inventory differs")
    membership_boundary = _mapping(
        contract.get("role_membership_boundary"), "role membership boundary"
    )
    _require(
        membership_boundary
        == {
            "fresh_non_superuser_creation": {
                "pg_auth_members_roleid": "EACH_ST0306_ROLE",
                "pg_auth_members_member": "CURRENT_MIGRATION_SESSION_ROLE",
                "exact_edge_count": 8,
                "admin_option": True,
                "inherit_option": False,
                "set_option": False,
            },
            "workload_role_outbound_memberships": "forbidden",
            "existing_role_path": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
            "standalone_validation": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
        },
        "role membership boundary differs",
    )
    _require(tuple(contract.get("schemas", ())) == SCHEMAS, "schema inventory differs")
    rls = _mapping(contract.get("rls"), "RLS contract")
    _require(
        tuple(rls.get("enabled_and_forced_predecessor_tables", ())) == RLS_TABLES,
        "RLS table inventory differs",
    )
    _require(rls.get("exact_policy_count") == 22, "RLS policy count differs")
    boundary = _mapping(contract.get("translation_boundary"), "translation boundary")
    _require(
        tuple(boundary.get("absent_upstream_relations", ()))
        == ABSENT_UPSTREAM_RELATIONS,
        "absent upstream relation boundary differs",
    )
    return contract


def _upstream_member(root: Path = REPO_ROOT) -> str:
    archive = _read(root, UPSTREAM_ARCHIVE_PATH, "upstream role archive")
    _require(_sha256(archive) == EXPECTED_ARCHIVE_SHA256, "archive digest differs")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        info = bundle.getinfo(UPSTREAM_MEMBER)
        _require(not info.is_dir(), "upstream role member is not a file")
        _require(info.file_size <= 128 * 1024, "upstream role member is too large")
        content = bundle.read(info)
    _require(_sha256(content) == EXPECTED_MEMBER_SHA256, "role SQL digest differs")
    return content.decode("utf-8")


def _policy_source(root: Path = REPO_ROOT) -> str:
    content = _read(root, POLICY_SOURCE_PATH, "finalized policy source")
    _require(
        _sha256(content) == EXPECTED_POLICY_SOURCE_SHA256,
        "finalized policy source digest differs",
    )
    return content.decode("utf-8")


def validate_source_inputs(root: Path = REPO_ROOT) -> dict[str, int]:
    _load_contract(root)
    for path, digest in PINNED_INPUTS.items():
        _require(
            _sha256(_read(root, Path(path), "pinned input")) == digest,
            f"pinned input digest differs: {path}",
        )
    _require(
        _sha256(_read(root, PREDECESSOR_MANIFEST_PATH, "predecessor manifest"))
        == EXPECTED_PREDECESSOR_MANIFEST_SHA256,
        "predecessor manifest digest differs",
    )
    upstream = _upstream_member(root)
    policy_source = _policy_source(root)
    upstream_roles = tuple(re.findall(r"CREATE ROLE (raos_[a-z_]+) NOLOGIN", upstream))
    _require(upstream_roles == ROLES, "upstream role inventory differs")
    _require(
        upstream.count("ALTER DEFAULT PRIVILEGES") == 14, "default ACL count differs"
    )
    _require(policy_source.count("CREATE POLICY ") == 22, "policy count differs")
    _require(
        all(name in policy_source for name in RLS_TABLES), "RLS table source differs"
    )
    return {"roles": len(ROLES), "schemas": len(SCHEMAS), "rls_policies": 22}


def _role_statement(role: str) -> str:
    return f"""DO $raos_st0306_role$
DECLARE
    observed pg_catalog.pg_roles%ROWTYPE;
BEGIN
    SELECT * INTO observed FROM pg_catalog.pg_roles WHERE rolname = '{role}';
    IF NOT FOUND THEN
        CREATE ROLE {role} NOLOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    ELSIF observed.rolcanlogin OR observed.rolsuper OR NOT observed.rolinherit
       OR observed.rolcreatedb OR observed.rolcreaterole
       OR observed.rolreplication OR observed.rolbypassrls
       OR observed.rolconnlimit <> -1 OR observed.rolvaliduntil IS NOT NULL
       OR observed.rolconfig IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'ST0306_ROLE_ATTRIBUTE_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members AS membership
        WHERE membership.member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = '{role}')
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '55000', MESSAGE = 'ST0306_ROLE_OUTBOUND_MEMBERSHIP';
    END IF;
END
$raos_st0306_role$;"""


def _canonical_grant_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    statements = predecessor._split_sql_statements(_upstream_member(root))
    selected: list[str] = []
    for statement in statements:
        if "CREATE ROLE " in statement:
            continue
        body = statement.strip()
        if (
            body.endswith("BEGIN;")
            or body == "COMMIT;"
            or "SET LOCAL lock_timeout" in body
        ):
            continue
        if "GRANT SELECT ON ops.audit_event" in body:
            body = "GRANT SELECT ON ops.audit_event TO raos_auditor_ro;"
        selected.append(body)
    joined = "\n".join(selected)
    _require(
        all(identity not in joined for identity in ABSENT_UPSTREAM_RELATIONS),
        "absent table grant rendered",
    )
    _require(
        joined.count("ALTER DEFAULT PRIVILEGES") == 14, "default ACL render differs"
    )
    return tuple(selected)


def _policy_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    statements = predecessor._split_sql_statements(_policy_source(root))
    policies: list[str] = []
    refinements: list[str] = []
    for statement in statements:
        if "CREATE POLICY " in statement:
            policies.append(statement[statement.index("CREATE POLICY ") :].strip())
        elif (
            "editorial.content_schema_version" in statement
            and (
                "REVOKE ALL ON TABLE" in statement
                or "GRANT SELECT, INSERT, UPDATE ON TABLE" in statement
                or "GRANT SELECT ON TABLE" in statement
            )
        ) or "GRANT USAGE ON SCHEMA editorial TO raos_auditor_ro" in statement:
            marker = min(
                (
                    position
                    for token in ("REVOKE", "GRANT")
                    if (position := statement.find(token)) >= 0
                ),
                default=-1,
            )
            _require(marker >= 0, "policy ACL refinement is invalid")
            refinements.append(statement[marker:].strip())
    _require(len(policies) == 22, "rendered policy count differs")
    _require(len(refinements) == 5, "rendered policy ACL refinement count differs")
    return (*policies, *refinements)


def render_upgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    validate_source_inputs(root)
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL lock_timeout = '5000ms';",
        *(_role_statement(role) for role in ROLES),
    ]
    schema_list = ", ".join(SCHEMAS)
    for role in ROLES:
        statements.extend(
            (
                f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON SCHEMA {schema_list} FROM {role};",
            )
        )
    statements.extend(_canonical_grant_statements(root))
    statements.extend(_policy_statements(root))
    # PostgreSQL's implicit PUBLIC EXECUTE grant for functions is an owner-wide
    # default.  A per-schema REVOKE cannot override that global default, so the
    # deny must also be owner-wide.  This single catalog row protects every
    # managed schema (and any future schema owned by the migration principal).
    statements.append(
        "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;"
    )
    statements.append(render_security_validation_statement())
    joined = "\n".join(statements)
    _require(joined.count("CREATE POLICY ") == 22, "upgrade policy count differs")
    _require(
        " LOGIN" not in joined and " PASSWORD" not in joined, "credential SQL rendered"
    )
    return tuple(statements)


def render_downgrade_statements(root: Path = REPO_ROOT) -> tuple[str, ...]:
    statements: list[str] = [
        "SET LOCAL search_path = pg_catalog;",
        "SET LOCAL lock_timeout = '5000ms';",
    ]
    policy_source = _policy_statements(root)[:22]
    for statement in reversed(policy_source):
        match = re.search(
            r"CREATE POLICY ([a-z0-9_]+)\s+ON\s+([a-z0-9_.]+)",
            statement,
            re.DOTALL,
        )
        _require(match is not None, "policy identity cannot be parsed")
        statements.append(f"DROP POLICY {match.group(1)} ON {match.group(2)};")
    schema_list = ", ".join(SCHEMAS)
    for role in ROLES:
        statements.extend(
            (
                f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {schema_list} FROM {role};",
                f"REVOKE ALL PRIVILEGES ON SCHEMA {schema_list} FROM {role};",
            )
        )
    for schema in SCHEMAS[:-1]:
        statements.append(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE SELECT ON TABLES FROM raos_projection_rw;"
        )
    statements.extend(
        (
            "ALTER DEFAULT PRIVILEGES IN SCHEMA readmodel REVOKE SELECT ON TABLES FROM raos_public_ro;",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA readmodel REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM raos_projection_rw;",
        )
    )
    _require(
        not any("DROP ROLE" in item for item in statements), "downgrade drops role"
    )
    return tuple(statements)


def _render_bytes_tuple(name: str, content: bytes) -> str:
    chunks = tuple(content[index : index + 80] for index in range(0, len(content), 80))
    return (
        f"{name}: tuple[bytes, ...] = (\n"
        + "".join(f'    b"{chunk.decode("ascii")}",\n' for chunk in chunks)
        + ")"
    )


def render_revision(root: Path = REPO_ROOT) -> bytes:
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
    text = f'''"""Install the exact ST-0306 database role and grant contract.

Revision ID: {REVISION}
Revises: {DOWN_REVISION}
Create Date: 2026-08-05

RAOS metadata:
- story: ST-0306
- requirement IDs: FR-020
- architecture: RAOS-SEC-001 database workload-role boundary
- runner version: {RUNNER_VERSION}
- server version: {EXPECTED_SERVER_VERSION_NUM}
- risk class: B (cluster roles plus database-local grants/default ACLs/RLS policies)
- estimated lock: bounded catalog ACL and RLS policy updates
- backfill job: none
- rollback category: database-local authority reversible; cluster roles preserved
- transaction: one PostgreSQL transaction for the complete Story revision
- rollback: drop 22 policies and revoke all Story-local grants/default ACLs
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
story_id: str = "ST-0306"
server_version_num: int = {EXPECTED_SERVER_VERSION_NUM}
_PAYLOAD_SHA256 = "{payload_sha256}"
_MAX_PAYLOAD_BYTES = 512 * 1024

{_render_bytes_tuple("_PAYLOAD_B85", encoded)}


def _decode_payload() -> tuple[tuple[str, ...], tuple[str, ...]]:
    compressed = base64.b85decode(b"".join(_PAYLOAD_B85))
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, _MAX_PAYLOAD_BYTES + 1)
    if decompressor.unconsumed_tail or not decompressor.eof or decompressor.unused_data:
        raise RuntimeError("ST0306_PAYLOAD_COMPRESSION_INVALID")
    if len(raw) > _MAX_PAYLOAD_BYTES:
        raise RuntimeError("ST0306_PAYLOAD_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != _PAYLOAD_SHA256:
        raise RuntimeError("ST0306_PAYLOAD_DIGEST_MISMATCH")
    value: Any = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {{"upgrade", "downgrade"}}:
        raise RuntimeError("ST0306_PAYLOAD_SHAPE_INVALID")
    upgrade = value["upgrade"]
    downgrade = value["downgrade"]
    if (
        not isinstance(upgrade, list)
        or not isinstance(downgrade, list)
        or not all(isinstance(item, str) for item in (*upgrade, *downgrade))
    ):
        raise RuntimeError("ST0306_PAYLOAD_STATEMENTS_INVALID")
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


def _legacy_validation_sql(revision_sha256: str) -> bytes:
    roles = ", ".join(f"'{role}'" for role in ROLES)
    schemas = ", ".join(f"'{schema}'" for schema in SCHEMAS)
    rls_tables = ", ".join(f"'{table}'" for table in RLS_TABLES)
    sql_text = f"""-- Generated by {GENERATOR_PATH.as_posix()}; do not edit.
-- Story ST-0306 local candidate validation for exact PostgreSQL 18.4.
SET search_path = pg_catalog;
SET TIME ZONE 'UTC';

DO $raos_st0306_validation$
DECLARE
    mismatch_count bigint;
BEGIN
    IF pg_catalog.current_setting('server_version_num') <> '{EXPECTED_SERVER_VERSION_NUM}' THEN
        RAISE EXCEPTION 'ST0306_SERVER_VERSION_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.array_agg(version_num ORDER BY version_num) FROM public.raos_migration_version)
       IS DISTINCT FROM ARRAY['{REVISION}']::pg_catalog.text[] THEN
        RAISE EXCEPTION 'ST0306_REVISION_MISMATCH';
    END IF;
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM pg_catalog.pg_roles
    WHERE rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
      AND (rolcanlogin OR rolsuper OR NOT rolinherit OR rolcreatedb
           OR rolcreaterole OR rolreplication OR rolbypassrls
           OR rolconnlimit <> -1 OR rolvaliduntil IS NOT NULL
           OR rolconfig IS NOT NULL);
    IF mismatch_count <> 0 OR
       (SELECT pg_catalog.count(*) FROM pg_catalog.pg_roles
        WHERE rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])) <> {len(ROLES)} THEN
        RAISE EXCEPTION 'ST0306_ROLE_SHAPE_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members AS membership
        JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = membership.member
        WHERE member_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) THEN
        RAISE EXCEPTION 'ST0306_ROLE_OUTBOUND_MEMBERSHIP';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_database AS database_record
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = database_record.datdba
        WHERE database_record.datname = pg_catalog.current_database()
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace AS namespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = namespace.nspowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = relation.relowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = routine.proowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_type AS object_type
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = object_type.typnamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_type.typowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND object_type.typrelid = 0
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) THEN
        RAISE EXCEPTION 'ST0306_WORKLOAD_ROLE_OWNS_OBJECT';
    END IF;
    IF NOT pg_catalog.has_schema_privilege('raos_public_ro', 'readmodel', 'USAGE')
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_namespace AS namespace
            WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
              AND namespace.nspname <> 'readmodel'
              AND pg_catalog.has_schema_privilege('raos_public_ro', namespace.oid, 'USAGE')
       ) OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
              AND relation.relkind IN ('r', 'v', 'S')
              AND ((namespace.nspname = 'readmodel' AND relation.relkind IN ('r', 'v')
                    AND NOT pg_catalog.has_table_privilege('raos_public_ro', relation.oid, 'SELECT'))
                   OR (namespace.nspname <> 'readmodel'
                       AND pg_catalog.has_any_column_privilege('raos_public_ro', relation.oid, 'SELECT,INSERT,UPDATE,REFERENCES'))
                   OR pg_catalog.has_table_privilege('raos_public_ro', relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')))
       ) THEN
        RAISE EXCEPTION 'ST0306_PUBLIC_BOUNDARY_MISMATCH';
    END IF;
    SELECT pg_catalog.count(*) INTO mismatch_count
    FROM pg_catalog.pg_policy AS policy_record
    JOIN pg_catalog.pg_class AS relation ON relation.oid = policy_record.polrelid
    JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
    WHERE namespace.nspname || '.' || relation.relname = ANY(
        ARRAY[{rls_tables}]::pg_catalog.text[]
    );
    IF mismatch_count <> 22 THEN
        RAISE EXCEPTION 'ST0306_RLS_POLICY_COUNT_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = defaults.defaclnamespace
        WHERE defaults.defaclnamespace = 0
           OR namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])) <> 14 THEN
        RAISE EXCEPTION 'ST0306_DEFAULT_ACL_SHAPE_MISMATCH';
    END IF;
END
$raos_st0306_validation$;

SELECT '{REVISION}'::pg_catalog.text AS revision,
       '{revision_sha256}'::pg_catalog.text AS revision_sha256,
       {len(ROLES)}::pg_catalog.int4 AS role_count,
       22::pg_catalog.int4 AS rls_policy_count;
"""
    return sql_text.encode("utf-8")


def render_security_validation_statement() -> str:
    """Render exact in-transaction security postconditions."""

    roles = ", ".join(f"'{role}'" for role in ROLES)
    schemas = ", ".join(f"'{schema}'" for schema in SCHEMAS)
    rls_tables = ", ".join(f"'{table}'" for table in RLS_TABLES)
    schema_roles = {
        "raos_api_rw": set(SCHEMAS) - {"readmodel"},
        "raos_worker_rw": set(SCHEMAS) - {"iam", "readmodel"},
        "raos_dispatcher_rw": {"ops"},
        "raos_projection_rw": set(SCHEMAS),
        "raos_public_ro": {"readmodel"},
        "raos_reporting_ro": {
            "analytics",
            "finance",
            "readmodel",
            "portfolio",
            "editorial",
            "publishing",
        },
        "raos_auditor_ro": {
            "ops",
            "iam",
            "policy",
            "publishing",
            "evidence",
            "editorial",
        },
    }
    schema_acl_values = ",\n                ".join(
        f"('{role}', '{schema}', 'USAGE', false)"
        for role, granted_schemas in sorted(schema_roles.items())
        for schema in sorted(granted_schemas)
    )
    auditor_table_values = ",\n                ".join(
        f"('{identity.split('.', 1)[0]}', '{identity.split('.', 1)[1]}')"
        for identity in sorted(AUDITOR_TABLES)
    )
    policy_values: list[str] = []
    for table, base in RLS_POLICY_BASES:
        policy_values.extend(
            (
                f"('{table}', '{base}_api', '*', true, 'raos_api_rw', 'true', 'true', true, true)",
                f"('{table}', '{base}_read', 'r', true, 'raos_auditor_ro,raos_projection_rw,raos_reporting_ro,raos_worker_rw', 'true', NULL, true, true)",
            )
        )
    policy_values_sql = ",\n                ".join(policy_values)
    return f"""DO $raos_st0306_security_validation$
DECLARE
    mismatch_count bigint;
BEGIN
    IF pg_catalog.current_setting('server_version_num') <> '{EXPECTED_SERVER_VERSION_NUM}' THEN
        RAISE EXCEPTION 'ST0306_SERVER_VERSION_MISMATCH';
    END IF;
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_roles
        WHERE rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])) <> {len(ROLES)}
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles
            WHERE rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
              AND (rolcanlogin OR rolsuper OR NOT rolinherit OR rolcreatedb
                   OR rolcreaterole OR rolreplication OR rolbypassrls
                   OR rolconnlimit <> -1 OR rolvaliduntil IS NOT NULL
                   OR rolconfig IS NOT NULL)
       ) OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS member_role
              ON member_role.oid = membership.member
            WHERE member_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
       ) THEN
        RAISE EXCEPTION 'ST0306_ROLE_SHAPE_MISMATCH';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_database AS object_record
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_record.datdba
        WHERE object_record.datname = pg_catalog.current_database()
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace AS object_record
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_record.nspowner
        WHERE object_record.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS object_record
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = object_record.relnamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_record.relowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS object_record
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = object_record.pronamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_record.proowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_type AS object_record
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = object_record.typnamespace
        JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = object_record.typowner
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND object_record.typrelid = 0
          AND owner_role.rolname = ANY(ARRAY[{roles}]::pg_catalog.text[])
    ) THEN
        RAISE EXCEPTION 'ST0306_WORKLOAD_ROLE_OWNS_OBJECT';
    END IF;

    WITH expected(role_name, schema_name, privilege_type, is_grantable) AS (
        VALUES {schema_acl_values}
    ), observed AS (
        SELECT COALESCE(grantee.rolname, 'PUBLIC'), namespace.nspname,
               acl.privilege_type, acl.is_grantable
        FROM pg_catalog.pg_namespace AS namespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(namespace.nspacl, pg_catalog.acldefault('n', namespace.nspowner))
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND acl.grantee <> namespace.nspowner
    ), mismatches AS (
        (SELECT * FROM expected EXCEPT SELECT * FROM observed)
        UNION ALL
        (SELECT * FROM observed EXCEPT SELECT * FROM expected)
    )
    SELECT pg_catalog.count(*) INTO mismatch_count FROM mismatches;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0306_SCHEMA_ACL_MISMATCH';
    END IF;

    WITH objects AS (
        SELECT namespace.nspname AS schema_name, relation.relname AS table_name,
               namespace.nspname || '.' || relation.relname AS identity
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND relation.relkind IN ('r', 'v')
    ), auditor_targets(schema_name, table_name) AS (
        VALUES {auditor_table_values}
    ), expected(role_name, schema_name, table_name, privilege_type, is_grantable) AS (
        SELECT 'raos_api_rw', schema_name, table_name, privilege_type, false
        FROM objects
        CROSS JOIN LATERAL pg_catalog.unnest(
            ARRAY['INSERT','SELECT','UPDATE']::pg_catalog.text[]
        ) AS privilege_type
        WHERE schema_name <> 'readmodel'
        UNION ALL
        SELECT 'raos_worker_rw', schema_name, table_name, privilege_type, false
        FROM objects
        CROSS JOIN LATERAL pg_catalog.unnest(
            CASE WHEN identity = ANY(ARRAY[{rls_tables}]::pg_catalog.text[])
                 THEN ARRAY['SELECT']::pg_catalog.text[]
                 ELSE ARRAY['INSERT','SELECT','UPDATE']::pg_catalog.text[] END
        ) AS privilege_type
        WHERE schema_name NOT IN ('iam', 'readmodel')
        UNION ALL
        SELECT 'raos_dispatcher_rw', schema_name, table_name, privilege_type, false
        FROM (VALUES
            ('ops','outbox_event','SELECT'), ('ops','outbox_event','UPDATE'),
            ('ops','job','SELECT'), ('ops','job','UPDATE'),
            ('ops','inbox_receipt','SELECT'), ('ops','inbox_receipt','INSERT'),
            ('ops','job_attempt','SELECT'), ('ops','job_attempt','INSERT'),
            ('ops','audit_event','SELECT'), ('ops','audit_event','INSERT')
        ) AS dispatcher(schema_name, table_name, privilege_type)
        UNION ALL
        SELECT 'raos_projection_rw', schema_name, table_name, privilege_type, false
        FROM objects
        CROSS JOIN LATERAL pg_catalog.unnest(
            CASE WHEN schema_name = 'readmodel'
                 THEN ARRAY['DELETE','INSERT','SELECT','UPDATE']::pg_catalog.text[]
                 ELSE ARRAY['SELECT']::pg_catalog.text[] END
        ) AS privilege_type
        UNION ALL
        SELECT 'raos_public_ro', schema_name, table_name, 'SELECT', false
        FROM objects WHERE schema_name = 'readmodel'
        UNION ALL
        SELECT 'raos_reporting_ro', schema_name, table_name, 'SELECT', false
        FROM objects
        WHERE schema_name IN ('analytics','finance','readmodel','portfolio','editorial','publishing')
        UNION ALL
        SELECT 'raos_auditor_ro', objects.schema_name, objects.table_name, 'SELECT', false
        FROM objects JOIN auditor_targets USING (schema_name, table_name)
    ), observed AS (
        SELECT COALESCE(grantee.rolname, 'PUBLIC'), namespace.nspname,
               relation.relname, acl.privilege_type, acl.is_grantable
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(relation.relacl, pg_catalog.acldefault('r', relation.relowner))
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND relation.relkind IN ('r', 'v') AND acl.grantee <> relation.relowner
    ), mismatches AS (
        (SELECT * FROM expected EXCEPT SELECT * FROM observed)
        UNION ALL
        (SELECT * FROM observed EXCEPT SELECT * FROM expected)
    )
    SELECT pg_catalog.count(*) INTO mismatch_count FROM mismatches;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0306_TABLE_ACL_MISMATCH';
    END IF;

    WITH expected(role_name, function_name, privilege_type, is_grantable) AS (
        VALUES
            ('raos_api_rw','ai.guard_approved_source_packet()','EXECUTE',false),
            ('raos_api_rw','publishing.guard_final_approval()','EXECUTE',false),
            ('raos_api_rw','publishing.guard_publication_candidate()','EXECUTE',false),
            ('raos_api_rw','publishing.guard_publication_transition()','EXECUTE',false)
    ), observed AS (
        SELECT COALESCE(grantee.rolname, 'PUBLIC'),
               namespace.nspname || '.' || routine.proname || '(' ||
               pg_catalog.pg_get_function_identity_arguments(routine.oid) || ')',
               acl.privilege_type, acl.is_grantable
        FROM pg_catalog.pg_proc AS routine
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(routine.proacl, pg_catalog.acldefault('f', routine.proowner))
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND acl.grantee <> routine.proowner
    ), mismatches AS (
        (SELECT * FROM expected EXCEPT SELECT * FROM observed)
        UNION ALL
        (SELECT * FROM observed EXCEPT SELECT * FROM expected)
    )
    SELECT pg_catalog.count(*) INTO mismatch_count FROM mismatches;
    IF mismatch_count <> 0 OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(relation.relacl, pg_catalog.acldefault('S', relation.relowner))
        ) AS acl
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND relation.relkind = 'S' AND acl.grantee <> relation.relowner
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute AS attribute
        JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
          AND attribute.attnum > 0 AND attribute.attacl IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'ST0306_FUNCTION_SEQUENCE_OR_COLUMN_ACL_MISMATCH';
    END IF;

    WITH schema_names(schema_name) AS (
        SELECT pg_catalog.unnest(ARRAY[{schemas}]::pg_catalog.text[])
    ), expected(schema_name, object_type, role_name, privilege_type, is_grantable) AS (
        SELECT '<GLOBAL>', 'f', current_user, 'EXECUTE', false
        UNION ALL
        SELECT schema_name, 'r', 'raos_projection_rw', 'SELECT', false
        FROM schema_names WHERE schema_name <> 'readmodel'
        UNION ALL SELECT 'readmodel','r','raos_public_ro','SELECT',false
        UNION ALL SELECT 'readmodel','r','raos_projection_rw','DELETE',false
        UNION ALL SELECT 'readmodel','r','raos_projection_rw','INSERT',false
        UNION ALL SELECT 'readmodel','r','raos_projection_rw','SELECT',false
        UNION ALL SELECT 'readmodel','r','raos_projection_rw','UPDATE',false
    ), observed AS (
        SELECT COALESCE(namespace.nspname, '<GLOBAL>'),
               defaults.defaclobjtype::pg_catalog.text,
               COALESCE(grantee.rolname, 'PUBLIC'), acl.privilege_type,
               acl.is_grantable
        FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = defaults.defaclnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(defaults.defaclacl) AS acl
        LEFT JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE (defaults.defaclnamespace = 0
               OR namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[]))
          AND defaults.defaclrole = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
    ), mismatches AS (
        (SELECT * FROM expected EXCEPT SELECT * FROM observed)
        UNION ALL
        (SELECT * FROM observed EXCEPT SELECT * FROM expected)
    )
    SELECT pg_catalog.count(*) INTO mismatch_count FROM mismatches;
    IF mismatch_count <> 0 OR (
        SELECT pg_catalog.count(*) FROM pg_catalog.pg_default_acl AS defaults
        LEFT JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = defaults.defaclnamespace
        WHERE defaults.defaclnamespace = 0
           OR namespace.nspname = ANY(ARRAY[{schemas}]::pg_catalog.text[])
    ) <> 14 THEN
        RAISE EXCEPTION 'ST0306_DEFAULT_ACL_MISMATCH';
    END IF;

    WITH expected(
        table_name, policy_name, command, permissive, roles, qual,
        with_check, rls_enabled, rls_forced
    ) AS (VALUES
        {policy_values_sql}
    ), observed AS (
        SELECT namespace.nspname || '.' || relation.relname,
               policy_record.polname, policy_record.polcmd::pg_catalog.text,
               policy_record.polpermissive,
               (SELECT pg_catalog.string_agg(role_record.rolname, ',' ORDER BY role_record.rolname)
                FROM pg_catalog.unnest(policy_record.polroles) AS role_oid
                JOIN pg_catalog.pg_roles AS role_record ON role_record.oid = role_oid),
               pg_catalog.pg_get_expr(policy_record.polqual, policy_record.polrelid, false),
               pg_catalog.pg_get_expr(policy_record.polwithcheck, policy_record.polrelid, false),
               relation.relrowsecurity, relation.relforcerowsecurity
        FROM pg_catalog.pg_policy AS policy_record
        JOIN pg_catalog.pg_class AS relation ON relation.oid = policy_record.polrelid
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname || '.' || relation.relname = ANY(
            ARRAY[{rls_tables}]::pg_catalog.text[]
        )
    ), mismatches AS (
        (SELECT * FROM expected EXCEPT SELECT * FROM observed)
        UNION ALL
        (SELECT * FROM observed EXCEPT SELECT * FROM expected)
    )
    SELECT pg_catalog.count(*) INTO mismatch_count FROM mismatches;
    IF mismatch_count <> 0 THEN
        RAISE EXCEPTION 'ST0306_RLS_POLICY_MISMATCH';
    END IF;
END
$raos_st0306_security_validation$;"""


def render_validation_sql(revision_sha256: str) -> bytes:
    sql_text = f"""-- Generated by {GENERATOR_PATH.as_posix()}; do not edit.
-- Story ST-0306 local candidate validation for exact PostgreSQL 18.4.
SET search_path = pg_catalog;
SET TIME ZONE 'UTC';

DO $raos_st0306_revision_validation$
BEGIN
    IF (SELECT pg_catalog.array_agg(
                   version_num::pg_catalog.text ORDER BY version_num
               )
        FROM public.raos_migration_version)
       IS DISTINCT FROM ARRAY['{REVISION}']::pg_catalog.text[] THEN
        RAISE EXCEPTION 'ST0306_REVISION_MISMATCH';
    END IF;
END
$raos_st0306_revision_validation$;

{render_security_validation_statement()}

SELECT '{REVISION}'::pg_catalog.text AS revision,
       '{revision_sha256}'::pg_catalog.text AS revision_sha256,
       {len(ROLES)}::pg_catalog.int4 AS role_count,
       22::pg_catalog.int4 AS rls_policy_count;
"""
    return sql_text.encode("utf-8")


def render_catalog(revision: bytes, validation: bytes) -> bytes:
    document = {
        "document": {
            "id": "RAOS-DATABASE-ROLES-GRANTS-CATALOG-001",
            "version": "1.0.0",
            "story_id": "ST-0306",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "formal_verification": "NOT_EXECUTED",
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
        "roles": list(ROLES),
        "role_attributes": {
            "login": False,
            "superuser": False,
            "inherit": True,
            "createdb": False,
            "createrole": False,
            "replication": False,
            "bypassrls": False,
            "outbound_memberships": "FORBIDDEN",
        },
        "role_membership_boundary": {
            "fresh_non_superuser_creation": {
                "pg_auth_members_roleid": "EACH_ST0306_ROLE",
                "pg_auth_members_member": "CURRENT_MIGRATION_SESSION_ROLE",
                "exact_edge_count": 8,
                "admin_option": True,
                "inherit_option": False,
                "set_option": False,
            },
            "workload_role_outbound_memberships": "FORBIDDEN",
            "existing_role_path": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
            "standalone_validation": "OUTBOUND_ONLY_PRESERVE_EXTERNAL_INBOUND",
        },
        "schemas": list(SCHEMAS),
        "public_boundary": {
            "schema_usage": ["readmodel"],
            "table_privileges": ["SELECT"],
            "function_execute": [],
        },
        "rls": {"tables": list(RLS_TABLES), "policy_count": 22},
        "deferred_absent_relations": list(ABSENT_UPSTREAM_RELATIONS),
        "downgrade": {
            "database_local_authority_removed": True,
            "cluster_roles_preserved": True,
        },
    }
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


CURRENT_SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    UPSTREAM_ARCHIVE_PATH,
    POLICY_SOURCE_PATH,
    Path("changes/st-0304/contracts/domain-schema.v1.yaml"),
    README_PATH,
    Path("README.md"),
    Path("Makefile"),
    Path("docs/execplans/ST-0306.md"),
    Path("docs/worklogs/ST-0306.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0201_postgres_service.py"),
    Path("scripts/build_st0304_domain_schemas.py"),
    Path("scripts/build_st0305_publication_analytics_finance.py"),
    PREDECESSOR_MANIFEST_PATH,
    Path("migrations/versions/202608030005_publication_analytics_finance.py"),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/runner.py"),
    Path("tests/postgresql18.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("tests/st0301/test_catalog.py"),
    Path("tests/st0301/test_cli.py"),
    Path("tests/st0301/test_contract.py"),
    Path("tests/st0301/test_generation.py"),
    Path("tests/st0301/test_postgresql.py"),
    Path("tests/st0301/test_runner.py"),
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
    Path("tests/st0306/conftest.py"),
    Path("tests/st0306/test_generation.py"),
    Path("tests/st0306/test_postgresql.py"),
)


def _artifact(root: Path, path: Path) -> dict[str, object]:
    content = _read(root, path, "source artifact")
    return {
        "uri": f"repo://{path.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(root: Path, outputs: Mapping[Path, bytes]) -> bytes:
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
            "id": "RAOS-DATABASE-ROLES-GRANTS-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0306",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "pinned_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in PINNED_INPUTS.items()
            ],
            "upstream_member": {
                "archive": f"repo://{UPSTREAM_ARCHIVE_PATH.as_posix()}",
                "member": UPSTREAM_MEMBER,
                "sha256": EXPECTED_MEMBER_SHA256,
            },
            "predecessor_manifest": {
                "story_id": "ST-0305",
                "uri": f"repo://{PREDECESSOR_MANIFEST_PATH.as_posix()}",
                "sha256": EXPECTED_PREDECESSOR_MANIFEST_SHA256,
            },
        },
        "revision": {
            "revision": REVISION,
            "down_revision": DOWN_REVISION,
            "runner_version": RUNNER_VERSION,
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "single_transaction": True,
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "inventory": {
            "roles": len(ROLES),
            "schemas": len(SCHEMAS),
            "rls_policies": 22,
            "default_table_acl_schemas": 13,
            "default_function_acl_scope": "MIGRATION_OWNER_GLOBAL",
            "default_acl_records": 14,
        },
        "security_boundary": {
            "creates_login_roles": False,
            "creates_credentials": False,
            "public_readmodel_only": True,
            "application_role_owns_database": False,
            "cluster_roles_preserved_on_downgrade": True,
        },
        "formal_verification": "NOT_EXECUTED",
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
    validate_source_inputs(root)
    revision = render_revision(root)
    validation = render_validation_sql(_sha256(revision))
    catalog = render_catalog(revision, validation)
    outputs: dict[Path, bytes] = {
        REVISION_PATH: revision,
        CATALOG_PATH: catalog,
        VALIDATION_PATH: validation,
    }
    outputs[MANIFEST_PATH] = render_manifest(root, outputs)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output order differs")
    return outputs


def install_generated(root: Path = REPO_ROOT) -> None:
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
                if stage.committed:
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
    expected = render_outputs(root)
    for path in GENERATED_PATHS:
        _require(
            _read(root, path, "generated artifact", 8 * 1024 * 1024) == expected[path],
            f"generated artifact drift: {path}",
        )


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify generated outputs")
    mode.add_argument(
        "--source-check", action="store_true", help="validate only frozen sources"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
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
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        yaml.YAMLError,
        zipfile.BadZipFile,
    ) as error:
        print(f"ST-0306 generation failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "PASS", "story_id": "ST-0306", "mode": mode, **summary},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
