"""Canonical, toolchain, graph, and semantic contract bindings."""

from __future__ import annotations

import importlib.metadata
import tomllib
from typing import Any

import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory

from .support import REPOSITORY_ROOT
from raos.migrations.catalog import (
    ANCHOR_REVISION,
    CHECKPOINT_SPECS,
    DATABASE_ROLES_REVISION,
    DOMAIN_REVISION,
    FOUNDATION_REVISION,
    GOOGLE_ANALYTICS_LIVE_REVISION,
    FORWARD_PLAN,
    GUARDED_REVERSE_PLAN,
    HEAD_REVISION,
    IAM_OPS_REVISION,
    PUBLICATION_ANALYTICS_FINANCE_REVISION,
    REVISION_SPECS,
)
from raos.migrations.runner import DOMAIN_SCHEMAS


def _record(document: dict[str, Any], key: str, identity: str) -> dict[str, Any]:
    matches = [item for item in document[key] if item["id"] == identity]
    assert len(matches) == 1
    return matches[0]


def test_canonical_story_is_exactly_the_framework_scope() -> None:
    path = REPOSITORY_ROOT / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    story = _record(document, "stories", "ST-0301")

    assert story == {
        "id": "ST-0301",
        "epic_id": "EPIC-03",
        "title": "Migration framework",
        "objective": "Version、transaction、lock、historyを実装",
        "depends_on": ["ST-0201", "ST-0002", "ST-0003", "ST-0004"],
        "requirement_ids": [],
        "design_refs": ["RAOS-DATA-001"],
        "deliverables": ["migration runner", "history table"],
        "acceptance_criteria": ["zero-to-latest"],
        "test_suites": ["TST-008", "TST-009"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": [],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }


def test_required_suites_remain_release_blocking_and_unexecuted() -> None:
    path = (
        REPOSITORY_ROOT / "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    baseline = _record(document, "suites", "TST-008")
    zero_to_latest = _record(document, "suites", "TST-009")

    assert baseline["name"] == "PostgreSQL baseline integration"
    assert baseline["candidate_tools"] == ["PostgreSQL 18 container", "pytest"]
    assert baseline["release_blocking"] is True
    assert baseline["environments"] == ["CI"]
    assert baseline["execution_status"] == "NOT_EXECUTED"
    assert zero_to_latest["name"] == "Migration zero-to-latest"
    assert zero_to_latest["candidate_tools"] == [
        "migration runner",
        "PostgreSQL 18",
    ]
    assert zero_to_latest["release_blocking"] is True
    assert zero_to_latest["environments"] == ["CI"]
    assert zero_to_latest["execution_status"] == "NOT_EXECUTED"


def test_contract_keeps_formal_and_future_wave_boundaries(
    migration_contract: dict[str, Any],
) -> None:
    assert migration_contract["document"]["formal_verification"] == "NOT_EXECUTED"
    assert migration_contract["story"]["required_suites"] == ["TST-008", "TST-009"]
    assert migration_contract["story"]["open_decisions"] == []
    assert migration_contract["boundary"] == {
        "environment": "LOCAL_AND_CI_IMPLEMENTATION_CANDIDATE",
        "foundation_schema_wave": "DEFERRED_TO_ST_0302",
        "checkpoint_execution": "DISABLED",
        "staging_or_recovery_execution": "NOT_IMPLEMENTED",
        "production_execution": "FORBIDDEN",
        "formal_tst_008": "NOT_EXECUTED",
        "formal_tst_009": "NOT_EXECUTED",
        "independent_migration_owner_review": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    }


def test_exact_toolchain_pins_are_installed_and_locked(
    migration_contract: dict[str, Any],
) -> None:
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = set(pyproject["project"]["dependencies"])
    lock = (REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8")

    assert migration_contract["toolchain"] == {
        "python": "3.14.6",
        "uv": "0.12.1",
        "alembic": "1.18.5",
        "sqlalchemy": "2.0.51",
        "psycopg": "3.3.4",
        "pyyaml": "6.0.3",
    }
    assert {
        "alembic==1.18.5",
        "sqlalchemy==2.0.51",
        "psycopg[binary]==3.3.4",
    } <= dependencies
    assert importlib.metadata.version("alembic") == "1.18.5"
    assert importlib.metadata.version("SQLAlchemy") == "2.0.51"
    assert importlib.metadata.version("psycopg") == "3.3.4"
    for package in ("alembic", "sqlalchemy", "psycopg", "psycopg-binary"):
        assert f'name = "{package}"' in lock


def test_production_alembic_graph_retains_one_reviewed_history_anchor(
    migration_contract: dict[str, Any],
) -> None:
    configuration = Config()
    configuration.set_main_option(
        "script_location", str(REPOSITORY_ROOT / "migrations")
    )
    script = ScriptDirectory.from_config(configuration)
    revisions = tuple(script.walk_revisions())

    assert ANCHOR_REVISION == "202608030001"
    assert FOUNDATION_REVISION == "202608030002"
    assert IAM_OPS_REVISION == "202608030003"
    assert DOMAIN_REVISION == "202608030004"
    assert PUBLICATION_ANALYTICS_FINANCE_REVISION == "202608030005"
    assert DATABASE_ROLES_REVISION == "202608030006"
    assert GOOGLE_ANALYTICS_LIVE_REVISION == HEAD_REVISION == "202608300001"
    assert script.get_heads() == [HEAD_REVISION]
    assert script.get_bases() == [ANCHOR_REVISION]
    assert len(revisions) == len(REVISION_SPECS) == 7
    assert revisions[-1].revision == ANCHOR_REVISION
    assert revisions[-1].down_revision is None
    assert revisions[-1].branch_labels == {"raos_framework"}
    assert migration_contract["revision_chain"]["version_table"] == (
        "public.raos_migration_version"
    )
    assert migration_contract["revision_chain"]["head"] == ANCHOR_REVISION
    assert migration_contract["revision_chain"]["revisions"] == [
        {
            "revision": REVISION_SPECS[0].revision,
            "down_revision": None,
            "story_id": "ST-0301",
            "name": "INSTALL_APPEND_ONLY_HISTORY_ANCHOR",
            "path": REVISION_SPECS[0].relative_path.as_posix(),
            "source_sha256": REVISION_SPECS[0].sha256,
            "runner_version": REVISION_SPECS[0].runner_version,
            "server_version_num": REVISION_SPECS[0].server_version_num,
            "transaction": "ALEMBIC_PER_REVISION",
            "downgrade": "FORBIDDEN_HISTORY_ANCHOR_RETAINED",
        }
    ]


def test_future_revision_template_requires_the_migration_playbook_metadata() -> None:
    template = (REPOSITORY_ROOT / "migrations/script.py.mako").read_text(
        encoding="utf-8"
    )
    for label in (
        "story",
        "requirement IDs",
        "architecture",
        "risk class",
        "estimated lock",
        "backfill job",
        "rollback category",
    ):
        assert f"- {label}: REQUIRED" in template


def test_checkpoint_contract_matches_exact_python_catalog_and_separate_plans(
    migration_contract: dict[str, Any],
) -> None:
    contract = migration_contract["checkpoint_catalog"]
    entries = contract["entries"]

    assert contract["execution"] == "DISABLED_UNTIL_OWNING_MIGRATION_WAVE_TRANSLATION"
    assert contract["default_head_membership"] is False
    assert len(entries) == len(CHECKPOINT_SPECS) == 18
    assert [entry["revision"] for entry in entries] == [
        item.revision for item in CHECKPOINT_SPECS
    ]
    for entry, item in zip(entries, CHECKPOINT_SPECS, strict=True):
        assert entry == {
            "revision": item.revision,
            "story_id": item.story_id,
            "phase": item.phase,
            "direction": item.direction.value,
            "repeatable": item.repeatable,
            "path": item.relative_path.as_posix(),
            "sha256": item.sha256,
        }
    assert tuple(contract["forward_plan"]) == FORWARD_PLAN
    assert tuple(contract["guarded_reverse_plan"]) == GUARDED_REVERSE_PLAN
    assert "202607300006" not in FORWARD_PLAN
    assert GUARDED_REVERSE_PLAN == (
        "202607300018",
        "202607300012",
        "202607300006",
    )


def test_framework_uses_public_metadata_without_claiming_domain_schemas(
    migration_contract: dict[str, Any],
) -> None:
    assert tuple(sorted(DOMAIN_SCHEMAS)) == (
        "ai",
        "analytics",
        "catalog",
        "editorial",
        "evidence",
        "finance",
        "freshness",
        "iam",
        "ops",
        "policy",
        "portfolio",
        "publishing",
        "readmodel",
    )
    assert migration_contract["history"]["table"] == ("public.raos_migration_history")
    assert migration_contract["history"]["public_privileges"] == "NONE"
    assert migration_contract["history"]["append_only_trigger"] is True


def test_execplan_contains_all_required_sections_and_current_boundary() -> None:
    text = (REPOSITORY_ROOT / "docs/execplans/ST-0301.md").read_text(encoding="utf-8")
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
    assert "formal Definition of Ready remains unmet" in text
    assert "No canonical status row has" in text


def test_operational_cli_and_env_have_no_url_or_deferred_sql_path() -> None:
    env_text = (REPOSITORY_ROOT / "migrations/env.py").read_text(encoding="utf-8")
    cli_text = (REPOSITORY_ROOT / "python/raos/migrations/cli.py").read_text(
        encoding="utf-8"
    )
    runner_text = (REPOSITORY_ROOT / "python/raos/migrations/runner.py").read_text(
        encoding="utf-8"
    )

    assert "context.is_offline_mode()" in env_text
    assert "transaction_per_migration=True" in env_text
    assert "on_version_apply=_record_success" in env_text
    assert "command.stamp" not in runner_text
    assert "command.downgrade" in runner_text
    assert "target_revision = spec.down_revision" in runner_text
    assert "CHECKPOINT_SPECS" not in runner_text
    assert "password" not in " ".join(cli_text.split()).casefold().split("_write(")[-1]
    assert all(
        item.relative_path.as_posix() not in env_text for item in CHECKPOINT_SPECS
    )
