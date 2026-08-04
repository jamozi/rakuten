"""Alembic runtime boundary for the RAOS migration runner."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

import sqlalchemy as sa
from alembic import context
from alembic.runtime.migration import MigrationContext, MigrationInfo
from sqlalchemy.engine import Connection


config = context.config


def _required_attribute(name: str) -> Any:
    value = config.attributes.get(name)
    if value is None:
        raise RuntimeError("ST0301_RUNNER_ATTRIBUTE_REQUIRED")
    return value


def _record_success(
    *,
    ctx: MigrationContext,
    step: MigrationInfo,
    heads: Collection[Any],
    run_args: Mapping[str, Any],
) -> None:
    del run_args
    if step.is_stamp or not step.is_migration or not step.is_upgrade:
        raise RuntimeError("ST0301_OPERATION_FORBIDDEN")
    revision = step.up_revision_id
    digests = _required_attribute("revision_digests")
    stories = _required_attribute("revision_stories")
    runner_versions = _required_attribute("revision_runner_versions")
    server_versions = _required_attribute("revision_server_versions")
    if (
        not isinstance(revision, str)
        or not isinstance(digests, dict)
        or not isinstance(stories, dict)
        or not isinstance(runner_versions, dict)
        or not isinstance(server_versions, dict)
        or revision not in digests
        or revision not in stories
        or revision not in runner_versions
        or revision not in server_versions
        or set(heads) != {revision}
    ):
        raise RuntimeError("ST0301_REVISION_GRAPH_MISMATCH")
    connection = ctx.connection
    if connection is None:
        raise RuntimeError("ST0301_CONNECTION_REQUIRED")
    connection.execute(
        sa.text(
            """
            INSERT INTO public.raos_migration_history (
                attempt_id,
                revision_id,
                story_id,
                direction,
                status,
                source_sha256,
                runner_version,
                server_version_num,
                error_code
            ) VALUES (
                CAST(:attempt_id AS uuid),
                :revision_id,
                :story_id,
                'UPGRADE',
                'SUCCEEDED',
                :source_sha256,
                :runner_version,
                :server_version_num,
                NULL
            )
            """
        ),
        {
            "attempt_id": _required_attribute("attempt_id"),
            "revision_id": revision,
            "story_id": stories[revision],
            "source_sha256": digests[revision],
            "runner_version": runner_versions[revision],
            "server_version_num": server_versions[revision],
        },
    )


def run_migrations_online() -> None:
    if context.is_offline_mode():
        raise RuntimeError("ST0301_OFFLINE_MODE_FORBIDDEN")
    connection = _required_attribute("connection")
    if not isinstance(connection, Connection):
        raise RuntimeError("ST0301_CONNECTION_REQUIRED")
    if connection.dialect.name != "postgresql":
        raise RuntimeError("ST0301_POSTGRESQL_REQUIRED")
    context.configure(
        connection=connection,
        target_metadata=None,
        version_table="raos_migration_version",
        version_table_schema="public",
        version_table_pk=True,
        transactional_ddl=True,
        transaction_per_migration=True,
        compare_type=False,
        compare_server_default=False,
        include_schemas=False,
        on_version_apply=_record_success,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
