#!/usr/bin/env python3
"""Build the deterministic, synthetic ST-0307 migration fixture bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

try:
    from scripts import build_st0201_postgres_service as shared
    from scripts import build_st0304_domain_schemas as secure
except ModuleNotFoundError:
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]
    import build_st0304_domain_schemas as secure  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.migrations import catalog as migration_catalog  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0307/contracts/migration-upgrade-fixtures.v1.yaml"
)
README_PATH: Final = Path("changes/st-0307/README.md")
GENERATOR_PATH: Final = Path("scripts/build_st0307_migration_fixtures.py")
FIXTURE_ROOT: Final = Path("tests/fixtures/migrations/st0307")
JOB_FIXTURE_PATH: Final = FIXTURE_ROOT / "v0.1-job-alignment.v1.sql"
AI_FIXTURE_PATH: Final = FIXTURE_ROOT / "v0.2-ai-alignment.v1.sql"
CONTENT_FIXTURE_PATH: Final = FIXTURE_ROOT / "v0.3-content-alignment.v1.sql"
PREDECESSOR_FIXTURE_PATH: Final = FIXTURE_ROOT / "202608030004-predecessor.v1.sql"
CATALOG_PATH: Final = Path(
    "changes/st-0307/generated/migration-upgrade-fixture-catalog.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0307/manifest.yaml")
GENERATED_PATHS: Final = (
    JOB_FIXTURE_PATH,
    AI_FIXTURE_PATH,
    CONTENT_FIXTURE_PATH,
    PREDECESSOR_FIXTURE_PATH,
    CATALOG_PATH,
    MANIFEST_PATH,
)

EXPECTED_SERVER_VERSION_NUM: Final = 180004
EXPECTED_CONTRACT_SHA256: Final = (
    "958d54f1df02e79df5b970f19f33f81a87d94f5637a7c57d595d51d6bf83cf59"
)
EXPECTED_ARCHIVE_SHA256: Final = (
    "82597db880c80c632ac0337d583c91ba5defac827414ecee1b921f49d1f64357"
)
EXPECTED_BASELINE_MEMBER_SHA256: Final = (
    "5813f16989316c159dd3fbaa0d0807f91adde51dda51c3f18a26dfe3e5c8c38c"
)
UPSTREAM_ARCHIVE_PATH: Final = Path("docs/upstream/RAOS_03_data_model_package_v0.1.zip")
BASELINE_MEMBER_SUFFIX: Final = "sql/RAOS_03_001_baseline_v0.1.sql"
UPSTREAM_MEMBER_SPECS: Final = (
    (
        "BASELINE_DDL",
        BASELINE_MEMBER_SUFFIX,
        EXPECTED_BASELINE_MEMBER_SHA256,
    ),
    (
        "CHECKPOINT_ACL_PREDECESSOR",
        "sql/RAOS_03_002_roles_and_grants_v0.1.sql",
        "6b9218df65e39ed5b5d38ca593a62ee544e9870296f32a7d7a819008a9d9803e",
    ),
    (
        "REFERENCE_SEED_PREDECESSOR",
        "sql/RAOS_03_003_reference_seed_v0.1.sql",
        "943471a90d5fd4f90112c2685d6aade64c0de18da74bc2c14d16555bd38644f8",
    ),
    (
        "BASELINE_POST_DEPLOY_VALIDATION",
        "sql/RAOS_03_004_post_deploy_validation_v0.1.sql",
        "cf00f6efa9ea8834ea99dcd4963acdd8b7824a66458a3df291924a654da1c4d2",
    ),
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python "
    "scripts/build_st0307_migration_fixtures.py"
)

PINNED_CANONICAL_INPUTS: Final = {
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
EXPECTED_ALIGNMENT_MANIFESTS: Final = {
    "changes/st-0002/manifest.yaml": (
        "ec687f51795c4f97d4e4b08db38ce4bec7c94da0e337c7e9a1bff2a9b2cb0f1e"
    ),
    "changes/st-0003/manifest.yaml": (
        "142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482"
    ),
    "changes/st-0004/manifest.yaml": (
        "5ba47a83548e6acfaa706ab4d3595cd05af39d9fa53fb411c17c44d7b478f458"
    ),
}
EXPECTED_MIGRATION_MANIFESTS: Final = {
    "changes/st-0301/manifest.yaml": (
        "287d1f365523f39bb7b28535680317103cb6abad5d5b3f5e4db4bc60250eb2ff"
    ),
    "changes/st-0302/manifest.yaml": (
        "d9db1f849ec8ff29a10736e03e98dad34a9a978147c26ed46c8dfa65911b2aa0"
    ),
    "changes/st-0303/manifest.yaml": (
        "f795daab918844b2bd0c2fb6e8aa17031f4e849e9ccb5bcfe45d554ddf69fe8b"
    ),
    "changes/st-0304/manifest.yaml": (
        "d09aed90f37c7238f2a3dab4675e6e3b06f108b6c40d4468979541d70577ee51"
    ),
    "changes/st-0305/manifest.yaml": (
        "5783b9c20d4b2c6a47ac0fa8703e78a0ac35dd1829840b5dd1a6bd6b48a8a16a"
    ),
}
EXPECTED_CHECKPOINT_PREREQUISITE_ROLES: Final = (
    "raos_api_rw",
    "raos_auditor_ro",
    "raos_projection_rw",
    "raos_public_ro",
    "raos_reporting_ro",
    "raos_worker_rw",
)

FIXTURE_PATHS: Final = (
    JOB_FIXTURE_PATH,
    AI_FIXTURE_PATH,
    CONTENT_FIXTURE_PATH,
    PREDECESSOR_FIXTURE_PATH,
)
CURRENT_SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    Path("README.md"),
    Path("Makefile"),
    Path("docs/execplans/ST-0307.md"),
    Path("docs/worklogs/ST-0307.md"),
    GENERATOR_PATH,
    UPSTREAM_ARCHIVE_PATH,
    *(Path(path) for path in PINNED_CANONICAL_INPUTS),
    *(Path(path) for path in EXPECTED_ALIGNMENT_MANIFESTS),
    *(Path(path) for path in EXPECTED_MIGRATION_MANIFESTS),
    Path("python/raos/migrations/catalog.py"),
    Path("python/raos/migrations/runner.py"),
    *(spec.relative_path for spec in migration_catalog.CHECKPOINT_SPECS),
    Path("tests/st0307/conftest.py"),
    Path("tests/st0307/test_generation.py"),
    Path("tests/st0307/test_postgresql.py"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(
    root: Path,
    path: Path,
    label: str,
    limit: int = 16 * 1024 * 1024,
) -> bytes:
    return secure._secure_read(root, path, label, limit)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    return secure._mapping(value, label)


def _sequence(value: object, label: str) -> Sequence[Any]:
    return secure._sequence(value, label)


def _load_yaml(content: bytes, label: str) -> dict[str, Any]:
    return secure._load_yaml(content, label)


def _artifact(root: Path, path: Path) -> dict[str, object]:
    content = _read(root, path, f"source artifact {path}")
    return {
        "uri": f"repo://{path.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _contract_checkpoint_rows(
    contract: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    checkpoint_catalog = _mapping(
        contract.get("checkpoint_catalog"), "checkpoint catalog"
    )
    rows: list[dict[str, object]] = []
    for value in _sequence(checkpoint_catalog.get("entries"), "checkpoint entries"):
        row = _mapping(value, "checkpoint entry")
        rows.append(
            {
                "revision": str(row.get("revision")),
                "story_id": str(row.get("story_id")),
                "phase": str(row.get("phase")),
                "direction": str(row.get("direction")),
                "repeatable": row.get("repeatable"),
                "path": str(row.get("path")),
                "sha256": str(row.get("sha256")),
            }
        )
    return tuple(rows)


def _live_checkpoint_rows() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "revision": spec.revision,
            "story_id": spec.story_id,
            "phase": spec.phase,
            "direction": spec.direction.value,
            "repeatable": spec.repeatable,
            "path": spec.relative_path.as_posix(),
            "sha256": spec.sha256,
        }
        for spec in migration_catalog.CHECKPOINT_SPECS
    )


def _load_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    content = _read(root, CONTRACT_PATH, "ST-0307 source contract", 2 * 1024 * 1024)
    _require(
        _sha256(content) == EXPECTED_CONTRACT_SHA256, "source contract digest differs"
    )
    contract = _load_yaml(content, "ST-0307 source contract")
    document = _mapping(contract.get("document"), "document")
    story = _mapping(contract.get("story"), "story")
    database = _mapping(contract.get("database"), "database")
    graph = _mapping(contract.get("production_graph"), "production graph")
    checkpoints = _mapping(contract.get("checkpoint_catalog"), "checkpoint catalog")
    precedence = _mapping(contract.get("source_precedence"), "source precedence")
    security = _mapping(contract.get("security"), "security")
    test_harness = _mapping(
        contract.get("historical_test_harness"), "historical test harness"
    )
    _require(document.get("story_id") == "ST-0307", "contract story differs")
    _require(story.get("dependencies") == ["ST-0305"], "Story dependencies differ")
    _require(story.get("open_decisions") == [], "contract has open decisions")
    _require(story.get("required_suites") == ["TST-010"], "required suite differs")
    _require(
        database.get("exact_server_version_num") == EXPECTED_SERVER_VERSION_NUM,
        "PostgreSQL version differs",
    )
    _require(
        graph
        == {
            "anchor_revision": migration_catalog.ANCHOR_REVISION,
            "predecessor_revision": migration_catalog.DOMAIN_REVISION,
            "head_revision": migration_catalog.HEAD_REVISION,
            "revision_count": len(migration_catalog.REVISION_SPECS),
            "mutation": "FORBIDDEN",
            "new_revision": "FORBIDDEN",
            "checkpoint_activation": "FORBIDDEN",
        },
        "production graph boundary differs",
    )
    _require(checkpoints.get("count") == 18, "checkpoint count differs")
    canonical_rows = _sequence(
        precedence.get("canonical_and_upstream_inputs"), "canonical inputs"
    )
    observed_canonical = {
        str(_mapping(row, "canonical input").get("path")): str(
            _mapping(row, "canonical input").get("sha256")
        )
        for row in canonical_rows
    }
    _require(
        observed_canonical == PINNED_CANONICAL_INPUTS,
        "canonical input authority inventory differs",
    )
    upstream_baseline = _mapping(
        precedence.get("upstream_baseline"), "upstream baseline"
    )
    _require(
        upstream_baseline.get("archive_path") == UPSTREAM_ARCHIVE_PATH.as_posix()
        and upstream_baseline.get("archive_sha256") == EXPECTED_ARCHIVE_SHA256,
        "upstream archive authority differs",
    )
    observed_members = tuple(
        (
            str(_mapping(row, "upstream member").get("purpose")),
            str(_mapping(row, "upstream member").get("member_suffix")),
            str(_mapping(row, "upstream member").get("member_sha256")),
        )
        for row in _sequence(upstream_baseline.get("members"), "upstream members")
    )
    _require(
        observed_members == UPSTREAM_MEMBER_SPECS, "upstream member inventory differs"
    )
    _require(
        checkpoints.get("authority") == "python/raos/migrations/catalog.py",
        "checkpoint authority path differs",
    )
    _require(
        checkpoints.get("authority_file_sha256")
        == _sha256(
            _read(root, Path(str(checkpoints.get("authority"))), "catalog authority")
        ),
        "checkpoint authority file digest differs",
    )
    _require(
        tuple(checkpoints.get("forward_plan", ())) == migration_catalog.FORWARD_PLAN,
        "checkpoint forward plan differs",
    )
    _require(
        tuple(checkpoints.get("guarded_reverse_plan", ()))
        == migration_catalog.GUARDED_REVERSE_PLAN,
        "checkpoint guarded reverse plan differs",
    )
    _require(
        checkpoints.get("execution")
        == "SEPARATE_ORDERED_DISPOSABLE_TEST_DATABASES_ONLY",
        "checkpoint execution boundary differs",
    )
    _require(
        _contract_checkpoint_rows(contract) == _live_checkpoint_rows(),
        "checkpoint catalog differs from runtime authority",
    )
    _require(
        _mapping(
            security.get("generated_fixture_payloads"),
            "generated fixture security",
        ).get("roles_grants_or_rls")
        == "FORBIDDEN",
        "generated fixture authority boundary differs",
    )
    _require(
        tuple(test_harness.get("baseline_members_loaded", ()))
        == tuple(
            member_suffix for _purpose, member_suffix, _digest in UPSTREAM_MEMBER_SPECS
        )
        and test_harness.get("roles_and_grants_member_loaded") is True
        and test_harness.get("reference_seed_member_loaded") is True
        and test_harness.get("post_deploy_validation_member_loaded") is True
        and test_harness.get("bootstrap_source") == "PINNED_UPSTREAM_ONLY"
        and test_harness.get("environment") == "ISOLATED_EPHEMERAL_TEST_SETUP_ONLY",
        "historical baseline member boundary differs",
    )
    _require(
        tuple(test_harness.get("checkpoint_prerequisite_roles", ()))
        == EXPECTED_CHECKPOINT_PREREQUISITE_ROLES
        and test_harness.get("prerequisite_role_mode")
        == "EPHEMERAL_HASH_BOUND_UPSTREAM_MEMBER"
        and test_harness.get("acl_or_default_privilege_semantics") == "NOT_EVALUATED"
        and test_harness.get("tst_011") == "NOT_EXECUTED",
        "historical prerequisite role boundary differs",
    )
    fixture_rows = _sequence(contract.get("fixtures"), "fixtures")
    _require(len(fixture_rows) == len(FIXTURE_PATHS), "fixture count differs")
    _require(
        tuple(Path(str(_mapping(row, "fixture").get("path"))) for row in fixture_rows)
        == FIXTURE_PATHS,
        "fixture path inventory differs",
    )
    fixture_map = {
        str(_mapping(row, "fixture").get("id")): _mapping(row, "fixture")
        for row in fixture_rows
    }
    job = fixture_map["ST0307-V01-JOB-ALIGNMENT"]
    ai = fixture_map["ST0307-V02-AI-ALIGNMENT"]
    content = fixture_map["ST0307-V03-CONTENT-ALIGNMENT"]
    predecessor = fixture_map["ST0307-202608030004-PREDECESSOR"]
    first_wave = migration_catalog.FORWARD_PLAN[:5]
    second_wave = migration_catalog.FORWARD_PLAN[5:10]
    third_wave = migration_catalog.FORWARD_PLAN[10:]
    _require(
        tuple(
            _mapping(job.get("apply_at"), "job precursor").get(
                "completed_forward_checkpoints", ()
            )
        )
        == ()
        and tuple(job.get("ordered_forward_checkpoints", ())) == first_wave
        and job.get("guarded_reverse_checkpoint")
        == migration_catalog.GUARDED_REVERSE_PLAN[2],
        "job fixture checkpoint boundary differs",
    )
    _require(
        tuple(
            _mapping(ai.get("apply_at"), "AI precursor").get(
                "completed_forward_checkpoints", ()
            )
        )
        == first_wave
        and tuple(ai.get("ordered_forward_checkpoints", ())) == second_wave
        and ai.get("guarded_reverse_checkpoint")
        == migration_catalog.GUARDED_REVERSE_PLAN[1],
        "AI fixture checkpoint boundary differs",
    )
    _require(
        tuple(
            _mapping(content.get("apply_at"), "content precursor").get(
                "completed_forward_checkpoints", ()
            )
        )
        == first_wave + second_wave
        and tuple(content.get("ordered_forward_checkpoints", ())) == third_wave
        and content.get("guarded_reverse_checkpoint")
        == migration_catalog.GUARDED_REVERSE_PLAN[0],
        "content fixture checkpoint boundary differs",
    )
    predecessor_apply = _mapping(predecessor.get("apply_at"), "predecessor state")
    _require(
        predecessor_apply.get("production_revision")
        == migration_catalog.DOMAIN_REVISION
        and tuple(predecessor_apply.get("completed_production_revisions", ()))
        == tuple(spec.revision for spec in migration_catalog.REVISION_SPECS[:4])
        and tuple(predecessor.get("ordered_upgrade_revisions", ()))
        == (migration_catalog.HEAD_REVISION,),
        "production predecessor fixture boundary differs",
    )
    boundary = _mapping(contract.get("boundary"), "boundary")
    _require(
        boundary.get("formal_tst_010") == "NOT_EXECUTED", "formal boundary differs"
    )
    _require(
        boundary.get("production_execution") == "FORBIDDEN",
        "production boundary differs",
    )
    return contract


def _validate_hash_map(root: Path, expected: Mapping[str, str], label: str) -> None:
    for raw_path, digest in expected.items():
        path = Path(raw_path)
        observed = _sha256(_read(root, path, f"{label} {path}"))
        _require(observed == digest, f"{label} digest differs: {path}")


def _validate_archive(root: Path) -> None:
    content = _read(root, UPSTREAM_ARCHIVE_PATH, "upstream baseline archive")
    _require(
        _sha256(content) == EXPECTED_ARCHIVE_SHA256, "baseline archive digest differs"
    )
    archive_path = root / UPSTREAM_ARCHIVE_PATH
    with zipfile.ZipFile(archive_path) as archive:
        for _purpose, member_suffix, expected_sha256 in UPSTREAM_MEMBER_SPECS:
            matches = [
                name for name in archive.namelist() if name.endswith(member_suffix)
            ]
            _require(len(matches) == 1, "baseline member inventory differs")
            member = archive.read(matches[0])
            _require(
                _sha256(member) == expected_sha256,
                "baseline SQL member digest differs",
            )


def validate_source_inputs(root: Path = REPO_ROOT) -> dict[str, object]:
    """Verify every authority/hash boundary before rendering or writing."""

    contract = _load_contract(root)
    _validate_hash_map(root, PINNED_CANONICAL_INPUTS, "canonical input")
    _validate_hash_map(root, EXPECTED_ALIGNMENT_MANIFESTS, "alignment manifest")
    _validate_hash_map(root, EXPECTED_MIGRATION_MANIFESTS, "migration manifest")
    _validate_archive(root)
    verification = migration_catalog.verify_all_sources(root)
    _require(
        len(verification.checkpoint_sources) == 18, "verified checkpoint count differs"
    )
    _require(
        tuple(source.sha256 for source in verification.checkpoint_sources)
        == tuple(row["sha256"] for row in _contract_checkpoint_rows(contract)),
        "verified checkpoint digest order differs",
    )
    checkpoint_contract = _mapping(
        contract.get("checkpoint_catalog"), "checkpoint catalog"
    )
    _require(
        verification.catalog_sha256
        == checkpoint_contract.get("authority_catalog_sha256"),
        "checkpoint authority catalog digest differs",
    )
    return {
        "checkpoint_sources": len(verification.checkpoint_sources),
        "fixture_sources": len(FIXTURE_PATHS),
        "production_revisions": len(verification.revision_sources),
        "catalog_sha256": verification.catalog_sha256,
    }


def _fixture_header(fixture_id: str, apply_at: Mapping[str, Any]) -> str:
    apply_boundary = json.dumps(
        apply_at, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return f"""-- Generated by {GENERATOR_PATH.as_posix()}; do not edit.
-- Source: {CONTRACT_PATH.as_posix()}
-- Command: {GENERATION_COMMAND}
-- Fixture: {fixture_id}
-- Apply boundary: {apply_boundary}
-- Synthetic test data only. Disposable PostgreSQL 18.4 database only.
-- This file is not an Alembic revision and must never enter the production runner.

BEGIN;
DO $st0307$
BEGIN
    IF current_setting('server_version_num')::integer <> {EXPECTED_SERVER_VERSION_NUM} THEN
        RAISE EXCEPTION 'ST-0307 requires PostgreSQL server_version_num {EXPECTED_SERVER_VERSION_NUM}';
    END IF;
END
$st0307$;
"""


def render_job_fixture(source: Mapping[str, Any]) -> bytes:
    sql = (
        _fixture_header(
            "ST0307-V01-JOB-ALIGNMENT",
            _mapping(source.get("apply_at"), "job precursor"),
        )
        + """
INSERT INTO ops.job (
    display_id, job_type, queue_name, status, completed_at,
    created_by_actor_type
)
VALUES
    ('ST0307-JOB-PENDING', 'ops.st0307_job_alignment.v1', 'st0307', 'PENDING', NULL, 'SYSTEM'),
    ('ST0307-JOB-READY', 'ops.st0307_job_alignment.v1', 'st0307', 'READY', NULL, 'SYSTEM'),
    ('ST0307-JOB-RUNNING', 'ops.st0307_job_alignment.v1', 'st0307', 'RUNNING', NULL, 'SYSTEM'),
    ('ST0307-JOB-SUCCEEDED', 'ops.st0307_job_alignment.v1', 'st0307', 'SUCCEEDED', TIMESTAMPTZ '2026-08-05 00:00:00+00', 'SYSTEM'),
    ('ST0307-JOB-FAILED', 'ops.st0307_job_alignment.v1', 'st0307', 'FAILED', TIMESTAMPTZ '2026-08-05 00:01:00+00', 'SYSTEM'),
    ('ST0307-JOB-CANCELLED', 'ops.st0307_job_alignment.v1', 'st0307', 'CANCELLED', TIMESTAMPTZ '2026-08-05 00:02:00+00', 'SYSTEM'),
    ('ST0307-JOB-QUARANTINED', 'ops.st0307_job_alignment.v1', 'st0307', 'QUARANTINED', TIMESTAMPTZ '2026-08-05 00:03:00+00', 'SYSTEM');

COMMIT;
"""
    )
    return sql.encode("utf-8")


def render_ai_fixture(source: Mapping[str, Any]) -> bytes:
    sql = (
        _fixture_header(
            "ST0307-V02-AI-ALIGNMENT", _mapping(source.get("apply_at"), "AI precursor")
        )
        + """
INSERT INTO iam.principal (
    id, display_id, principal_type, status, display_name
)
VALUES (
    '00000000-0000-7000-8000-000000000307',
    'PRN-ST0307-LEGACY-AUTHOR', 'USER', 'ACTIVE',
    'Synthetic legacy prompt author'
);

SET LOCAL session_replication_role = replica;

INSERT INTO ai.ai_job (
    display_id, ops_job_id, task_definition_id, article_plan_id,
    source_packet_version_id, prompt_version_id, output_schema_version_id,
    model_route_version_id, status, max_cost_jpy, completed_at
)
VALUES
    ('AIJ-ST0307-PENDING', uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), 'PENDING', 100, NULL),
    ('AIJ-ST0307-FAILED', uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), 'FAILED', 100, TIMESTAMPTZ '2026-08-05 00:10:00+00'),
    ('AIJ-ST0307-BLOCKED', uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), uuidv7(), 'BLOCKED', 100, TIMESTAMPTZ '2026-08-05 00:11:00+00');

INSERT INTO ai.prompt_version (
    display_id, task_definition_id, prompt_code, version_no,
    git_path, git_commit_sha, template_sha256, status
)
VALUES (
    'PRM-ST0307-REJECTED', uuidv7(), 'PROMPT-ST0307-REJECTED', 1,
    'prompts/st0307-rejected.md', repeat('c', 40), repeat('d', 64),
    'REJECTED'
);

SET LOCAL session_replication_role = origin;
COMMIT;
"""
    )
    return sql.encode("utf-8")


def render_content_fixture(source: Mapping[str, Any]) -> bytes:
    sql = (
        _fixture_header(
            "ST0307-V03-CONTENT-ALIGNMENT",
            _mapping(source.get("apply_at"), "content precursor"),
        )
        + """
SET LOCAL session_replication_role = replica;

INSERT INTO editorial.article_version (
    display_id, article_id, version_no, content_schema_version,
    title, body_sha256, status, source_packet_version_id,
    created_by_actor_type
)
VALUES (
    'ARV-ST0307-NO-GUESS', uuidv7(), 1, 1,
    'Synthetic migration fixture', repeat('a', 64), 'DRAFT', uuidv7(),
    'SYSTEM'
);

SET LOCAL session_replication_role = origin;
COMMIT;
"""
    )
    return sql.encode("utf-8")


def render_predecessor_fixture(source: Mapping[str, Any]) -> bytes:
    sql = (
        _fixture_header(
            "ST0307-202608030004-PREDECESSOR",
            _mapping(source.get("apply_at"), "predecessor state"),
        )
        + """
INSERT INTO ops.object_artifact (
    id, display_id, artifact_kind, bucket_name, object_key,
    content_type, byte_size, sha256, encryption_state,
    retention_class, source_system
)
VALUES (
    '00000000-0000-0000-0000-000000000060',
    'ART-ST0307-PREDECESSOR', 'other', 'fixture',
    'migration/st0307-predecessor.json', 'application/json', 2,
    repeat('6', 64), 'LOCAL_DEV', 'TEST', 'ST0307_FIXTURE'
);

COMMIT;
"""
    )
    return sql.encode("utf-8")


def _fixture_catalog_rows(
    contract: Mapping[str, Any], fixture_outputs: Mapping[Path, bytes]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in _sequence(contract.get("fixtures"), "fixtures"):
        source = _mapping(raw, "fixture")
        path = Path(str(source.get("path")))
        content = fixture_outputs[path]
        rows.append(
            {
                "id": source.get("id"),
                "version": source.get("version"),
                "path": path.as_posix(),
                "apply_at": source.get("apply_at"),
                "checkpoint_story": source.get("checkpoint_story"),
                "expected_rows": source.get("expected_rows"),
                "expected_behavior": source.get("expected_behavior"),
                "bytes": len(content),
                "sha256": _sha256(content),
            }
        )
    return rows


def render_catalog(
    contract: Mapping[str, Any], fixture_outputs: Mapping[Path, bytes]
) -> bytes:
    value = {
        "schema_version": "migration-upgrade-fixture-catalog.v1",
        "story_id": "ST-0307",
        "source_contract": CONTRACT_PATH.as_posix(),
        "source_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "database": {
            "product": "PostgreSQL",
            "server_version_num": EXPECTED_SERVER_VERSION_NUM,
            "fixture_data": "SYNTHETIC_ONLY",
        },
        "production_graph": dict(
            _mapping(contract.get("production_graph"), "production graph")
        ),
        "fixture_count": len(fixture_outputs),
        "fixtures": _fixture_catalog_rows(contract, fixture_outputs),
        "checkpoint_catalog": {
            key: value
            for key, value in _mapping(
                contract.get("checkpoint_catalog"), "checkpoint catalog"
            ).items()
            if key != "entries"
        }
        | {
            "entries": list(_live_checkpoint_rows()),
        },
        "boundary": dict(_mapping(contract.get("boundary"), "boundary")),
    }
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_manifest(
    root: Path,
    contract: Mapping[str, Any],
    outputs: Mapping[Path, bytes],
) -> bytes:
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
    value = {
        "document": {
            "id": "RAOS-MIGRATION-UPGRADE-FIXTURE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0307",
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "upstream_baseline": {
                "uri": f"repo://{UPSTREAM_ARCHIVE_PATH.as_posix()}",
                "archive_sha256": EXPECTED_ARCHIVE_SHA256,
                "members": [
                    {
                        "purpose": purpose,
                        "member_suffix": member_suffix,
                        "member_sha256": member_sha256,
                    }
                    for purpose, member_suffix, member_sha256 in UPSTREAM_MEMBER_SPECS
                ],
            },
            "canonical_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in PINNED_CANONICAL_INPUTS.items()
            ],
            "alignment_manifests": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_ALIGNMENT_MANIFESTS.items()
            ],
            "migration_manifests": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_MIGRATION_MANIFESTS.items()
            ],
        },
        "production_graph": dict(
            _mapping(contract.get("production_graph"), "production graph")
        ),
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": generated_artifacts,
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "fixture_inventory": _fixture_catalog_rows(
            contract, {path: outputs[path] for path in FIXTURE_PATHS}
        ),
        "checkpoint_inventory": {
            "count": len(migration_catalog.CHECKPOINT_SPECS),
            "copy_or_concatenate": "FORBIDDEN",
            "runtime_activation": "FORBIDDEN",
        },
        "security_boundary": {
            "synthetic_only": True,
            "credentials_or_secrets": "FORBIDDEN",
            "generated_fixture_roles_grants_or_rls": "FORBIDDEN",
            "production_execution": "FORBIDDEN",
        },
        "historical_test_harness": dict(
            _mapping(contract.get("historical_test_harness"), "historical test harness")
        ),
        "boundary": dict(_mapping(contract.get("boundary"), "boundary")),
    }
    return yaml.dump(
        value,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    validate_source_inputs(root)
    contract = _load_contract(root)
    fixture_sources = {
        str(_mapping(row, "fixture").get("id")): _mapping(row, "fixture")
        for row in _sequence(contract.get("fixtures"), "fixtures")
    }
    outputs: dict[Path, bytes] = {
        JOB_FIXTURE_PATH: render_job_fixture(
            fixture_sources["ST0307-V01-JOB-ALIGNMENT"]
        ),
        AI_FIXTURE_PATH: render_ai_fixture(fixture_sources["ST0307-V02-AI-ALIGNMENT"]),
        CONTENT_FIXTURE_PATH: render_content_fixture(
            fixture_sources["ST0307-V03-CONTENT-ALIGNMENT"]
        ),
        PREDECESSOR_FIXTURE_PATH: render_predecessor_fixture(
            fixture_sources["ST0307-202608030004-PREDECESSOR"]
        ),
    }
    outputs[CATALOG_PATH] = render_catalog(contract, outputs)
    outputs[MANIFEST_PATH] = render_manifest(root, contract, outputs)
    _require(tuple(outputs) == GENERATED_PATHS, "generated output order differs")
    return outputs


def install_generated(root: Path = REPO_ROOT) -> None:
    outputs = render_outputs(root)
    staged: list[secure._StagedOutput] = []
    try:
        for ordinal, path in enumerate(GENERATED_PATHS):
            staged.append(secure._stage_output(root, path, outputs[path], ordinal))
        try:
            for stage in staged:
                secure._verify_stage_target_unchanged(stage)
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
                    secure._restore_output(stage, ordinal)
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
        observed = _read(root, path, f"generated artifact {path}", 8 * 1024 * 1024)
        metadata = (root / path).lstat()
        _require(
            stat.S_IMODE(metadata.st_mode) == 0o644, f"generated mode differs: {path}"
        )
        _require(observed == expected[path], f"generated artifact drift: {path}")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify generated outputs")
    mode.add_argument(
        "--source-check", action="store_true", help="verify frozen source inputs"
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
        zipfile.BadZipFile,
        yaml.YAMLError,
        migration_catalog.CatalogError,
    ) as error:
        print(f"ST-0307 generation failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "PASS", "story_id": "ST-0307", "mode": mode, **summary},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
