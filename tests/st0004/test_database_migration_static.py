"""Static fail-closed checks for the six ST-0004 SQL checkpoints."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from scripts import build_st0004_revision as revision


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE_ROOT = REPOSITORY_ROOT / "changes" / "st-0004" / "database"
FORWARD = tuple(DATABASE_ROOT / name for name in revision.MIGRATION_PHASES)
DOWNGRADE = DATABASE_ROOT / revision.GUARDED_DOWNGRADE
EXPECTED_FILES = {
    *revision.MIGRATION_PHASES,
    revision.GUARDED_DOWNGRADE,
    revision.FORWARD_RECOVERY,
}
EXPECTED_TABLES = {
    "editorial.content_schema_version",
    "editorial.article_type_version",
    "editorial.article_template_version",
    "editorial.editorial_methodology_version",
    "editorial.article_methodology_binding",
    "editorial.seo_metadata_version",
    "editorial.structured_data_manifest",
    "editorial.media_asset",
    "evidence.first_hand_experience_record",
    "evidence.first_hand_experience_asset",
    "editorial.article_disclosure_context",
}


def sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(path: Path) -> str:
    return re.sub(r"\s+", " ", sql(path).lower())


def test_database_source_inventory_is_exact_and_never_installs_upstream_proposals() -> None:
    actual = {path.name for path in DATABASE_ROOT.iterdir() if path.is_file()}
    assert actual == EXPECTED_FILES
    assert not any("alignment_patch" in name or "proposal" in name for name in actual)
    proposal_names = {
        "RAOS_06_001_data_alignment_patch_v0.1.sql",
        "RAOS_06_002_api_alignment_patch_v0.1.yaml",
        "RAOS_06_003_ai_alignment_patch_v0.1.yaml",
    }
    assert not (actual & proposal_names)


@pytest.mark.parametrize("path", (*FORWARD, DOWNGRADE))
def test_each_checkpoint_is_transactional_version_gated_and_non_idempotent(path: Path) -> None:
    text = normalized(path)
    assert re.search(r"\bbegin(?:\s+isolation\s+level\s+repeatable\s+read)?\s*;", text)
    assert "commit;" in text
    assert "server_version_num" in text and "180000" in text
    for idempotent_ddl in (
        r"create\s+table\s+if\s+not\s+exists",
        r"create\s+(?:unique\s+)?index(?:\s+concurrently)?\s+if\s+not\s+exists",
        r"add\s+column\s+if\s+not\s+exists",
        r"add\s+constraint\s+if\s+not\s+exists",
        r"drop\s+table\s+if\s+exists",
        r"drop\s+column\s+if\s+exists",
        r"drop\s+constraint\s+if\s+exists",
    ):
        assert not re.search(idempotent_ddl, text), idempotent_ddl
    assert "drop schema" not in text
    assert " cascade" not in text


def test_expand_creates_exact_eleven_resources_and_four_article_bindings() -> None:
    text = normalized(FORWARD[0])
    for table in EXPECTED_TABLES:
        assert f"create table {table}" in text, table
    assert len(re.findall(r"\bcreate table\s+(?:editorial|evidence)\.", text)) == 11
    assert "alter table editorial.article_version" in text
    for column in (
        "content_schema_version_id",
        "article_type_version_id",
        "article_template_version_id",
        "seo_metadata_version_id",
    ):
        assert column in text
    assert "revoke all on table" in text
    assert "from public, raos_public_ro, raos_worker_rw" in text
    assert "to raos_api_rw" in text
    media_table = text.split("create table editorial.media_asset", 1)[1].split(
        "create table evidence.first_hand_experience_record", 1
    )[0]
    methodology_binding = text.split(
        "create table editorial.article_methodology_binding", 1
    )[1].split("create table editorial.seo_metadata_version", 1)[0]
    assert "source_id uuid not null" in media_table
    assert "raw_artifact_id uuid not null" in media_table
    assert "bound_by_principal_id uuid not null" in methodology_binding
    media_guard, first_hand_tail = text.split(
        "create function editorial.guard_media_asset_mutation()", 1
    )[1].split("create function evidence.guard_first_hand_experience_mutation()", 1)
    first_hand_guard = first_hand_tail.split(
        "create function editorial.guard_disclosure_context_mutation()", 1
    )[0]
    assert "tester_principal_id" not in media_guard
    assert "new.tester_principal_id" in first_hand_guard
    assert "first-hand experience tester must be an active user" in first_hand_guard
    assert "experience reviewer must differ from tester" in first_hand_guard


def test_validate_and_batch_phases_are_split_repeatable_and_bounded() -> None:
    validate = normalized(FORWARD[1])
    batch = normalized(FORWARD[2])
    assert validate.count("validate constraint") >= 4
    assert len(
        re.findall(
            r"(?im)^\s*create index concurrently\s+\w+",
            sql(FORWARD[1]),
        )
    ) == 26
    assert "run with autocommit enabled" in validate
    assert "must not be wrapped" in validate
    assert "update editorial.article_version" not in batch
    assert "1000" in batch
    assert "automatic_remaining_rows" in batch
    assert "operator_binding_rows" in batch
    assert "never invent those bindings" in batch
    assert "remaining_rows" in batch


def test_contract_prepare_and_contract_are_fail_closed_and_acl_explicit() -> None:
    prepare = normalized(FORWARD[3])
    contract = normalized(FORWARD[4])
    assert "reporting remaining_rows = 0" in prepare
    assert "raise exception" in prepare
    assert prepare.count("check (") >= 4 and prepare.count("not valid") >= 4
    assert "human provenance readiness drift" in prepare
    assert "public privilege drift" in prepare
    assert "foreign key without a leading index" in prepare
    assert contract.count("validate constraint") >= 4
    assert contract.count("set not null") == 4
    assert "canonical foreign-key abi is incomplete" in contract
    assert "canonical active-singleton indexes drifted" in contract
    assert "raos_api_rw" in prepare
    assert "raos_worker_rw" in prepare
    expand = normalized(FORWARD[0])
    assert "raos_reporting_ro" in expand


def test_guarded_downgrade_refuses_nonempty_state_and_preserves_predecessor_schemas() -> None:
    text = normalized(DOWNGRADE)
    assert "raise exception" in text
    for table in EXPECTED_TABLES:
        assert table in text
    assert "drop table" in text
    assert "drop column" in text
    assert "drop schema editorial" not in text
    assert "drop schema evidence" not in text
    assert "drop schema ai" not in text
    recovery = (DATABASE_ROOT / revision.FORWARD_RECOVERY).read_text(encoding="utf-8")
    for name in revision.MIGRATION_PHASES:
        assert name in recovery
    assert "`018`" in recovery
    assert "guarded downgrade" in recovery.lower()
