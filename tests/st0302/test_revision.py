"""Static ST-0302 revision, graph, and one-step command tests."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest

from .support import REPOSITORY_ROOT
from raos.migrations import catalog
from raos.migrations import cli
from raos.migrations import runner


REVISION_PATH = Path("migrations/versions/202608030002_foundation_schemas.py")


def _revision_module() -> Any:
    import importlib.util

    path = REPOSITORY_ROOT / REVISION_PATH
    spec = importlib.util.spec_from_file_location("st0302_foundation_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _OperationRecorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def test_revision_metadata_and_alembic_graph_are_exact() -> None:
    module = _revision_module()
    configuration = Config()
    configuration.set_main_option(
        "script_location", str(REPOSITORY_ROOT / "migrations")
    )
    script = ScriptDirectory.from_config(configuration)

    assert module.revision == catalog.FOUNDATION_REVISION
    assert module.down_revision == catalog.ANCHOR_REVISION
    assert module.branch_labels is None
    assert module.depends_on is None
    assert script.get_heads() == [catalog.DATABASE_ROLES_REVISION]
    assert script.get_bases() == [catalog.ANCHOR_REVISION]
    assert [item.revision for item in script.walk_revisions()] == [
        catalog.DATABASE_ROLES_REVISION,
        catalog.PUBLICATION_ANALYTICS_FINANCE_REVISION,
        catalog.DOMAIN_REVISION,
        catalog.IAM_OPS_REVISION,
        catalog.FOUNDATION_REVISION,
        catalog.ANCHOR_REVISION,
    ]


def test_upgrade_and_downgrade_emit_only_the_allowlisted_ddl() -> None:
    module = _revision_module()
    recorder = _OperationRecorder()
    module.op = recorder

    module.upgrade()
    assert recorder.statements == [
        "CREATE SCHEMA ops",
        "COMMENT ON SCHEMA ops IS "
        "'ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定'",
        "REVOKE ALL ON SCHEMA ops FROM PUBLIC",
        "CREATE SCHEMA iam",
        "COMMENT ON SCHEMA iam IS 'OIDC主体、アプリケーションRole、権限、緊急アクセス'",
        "REVOKE ALL ON SCHEMA iam FROM PUBLIC",
    ]

    recorder.statements.clear()
    module.downgrade()
    assert recorder.statements == [
        "DROP SCHEMA iam RESTRICT",
        "DROP SCHEMA ops RESTRICT",
    ]


def test_revision_contains_no_idempotent_or_destructive_escape_hatch() -> None:
    text = (REPOSITORY_ROOT / REVISION_PATH).read_text(encoding="utf-8")
    upper = text.upper()

    for forbidden in (
        "IF NOT EXISTS",
        "IF EXISTS",
        "CASCADE",
        "CREATE TABLE",
        "CREATE TYPE",
        "CREATE DOMAIN",
        "CREATE EXTENSION",
        "CREATE FUNCTION",
        "CREATE ROLE",
        "GRANT ",
        "DROP TABLE",
    ):
        assert forbidden not in upper


def test_public_downgrade_is_target_free_and_cli_accepts_no_target_revision() -> None:
    signature = inspect.signature(runner.MigrationRunner.downgrade)
    assert list(signature.parameters) == ["self"]

    parser = cli._parser()
    namespace = parser.parse_args(
        [
            "downgrade",
            "--environment",
            "ENV-CI",
            "--host",
            "/tmp/socket",
            "--port",
            "5432",
            "--database",
            "raos_st0302",
            "--user",
            "raos_migrator",
            "--password-file",
            "/tmp/password",
        ]
    )
    assert namespace.command == "downgrade"
    assert not hasattr(namespace, "revision")


def test_no_open_attempt_still_runs_strict_pre_upgrade_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bool, bool]] = []

    def validate(
        connection: object,
        current_revision: str,
        *,
        allow_open: bool = False,
        allow_foundation_objects: bool = False,
    ) -> None:
        del connection
        assert current_revision == catalog.FOUNDATION_REVISION
        calls.append((allow_open, allow_foundation_objects))
        return None

    monkeypatch.setattr(
        runner.MigrationRunner,
        "_assert_same_session",
        lambda *args: None,
    )
    monkeypatch.setattr(runner, "_validate_installed", validate)

    instance = object.__new__(runner.MigrationRunner)
    instance._reconcile_interrupted_attempt(
        object(),  # type: ignore[arg-type]
        catalog.FOUNDATION_REVISION,
        object(),  # type: ignore[arg-type]
        allow_foundation_objects=True,
        strict_after_reconcile=True,
    )

    assert calls == [(True, True), (False, False)]
