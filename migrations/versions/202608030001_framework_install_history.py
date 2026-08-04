"""Install the append-only RAOS migration history anchor.

Revision ID: 202608030001
Revises: none
Create Date: 2026-08-03

RAOS metadata:
- story: ST-0301
- requirement IDs: none
- architecture: RAOS-DATA-001 migration framework
- risk class: A (additive metadata)
- estimated lock: new metadata objects only
- backfill job: none
- rollback category: retained history anchor, forward recovery only
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "202608030001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = "raos_framework"
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raos_migration_history",
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.String(length=32), nullable=False),
        sa.Column("story_id", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=9), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("source_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("runner_version", sa.String(length=32), nullable=False),
        sa.Column("server_version_num", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("transaction_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            sa.Text(),
            server_default=sa.text("pg_current_xact_id()::text"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_id ~ '^[0-9]{12}$'",
            name="ck_raos_migration_history_revision",
        ),
        sa.CheckConstraint(
            "story_id ~ '^ST-[0-9]{4}$'",
            name="ck_raos_migration_history_story",
        ),
        sa.CheckConstraint(
            "direction IN ('UPGRADE', 'DOWNGRADE')",
            name="ck_raos_migration_history_direction",
        ),
        sa.CheckConstraint(
            "status IN ('STARTED', 'SUCCEEDED', 'FAILED')",
            name="ck_raos_migration_history_status",
        ),
        sa.CheckConstraint(
            "source_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_raos_migration_history_source_sha256",
        ),
        sa.CheckConstraint(
            "runner_version ~ '^[0-9]+[.][0-9]+[.][0-9]+$'",
            name="ck_raos_migration_history_runner_version",
        ),
        sa.CheckConstraint(
            "server_version_num BETWEEN 100000 AND 999999",
            name="ck_raos_migration_history_server_version",
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND error_code IS NOT NULL) OR "
            "(status <> 'FAILED' AND error_code IS NULL)",
            name="ck_raos_migration_history_error_code",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_raos_migration_history"),
        sa.UniqueConstraint(
            "attempt_id",
            "status",
            name="uq_raos_migration_history_attempt_status",
        ),
        schema="public",
    )
    op.execute(
        """
        CREATE FUNCTION public.raos_reject_migration_history_mutation_st0301()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = 'RAOS migration history is append-only';
        END;
        $function$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_raos_migration_history_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE
        ON public.raos_migration_history
        FOR EACH STATEMENT
        EXECUTE FUNCTION public.raos_reject_migration_history_mutation_st0301()
        """
    )
    op.execute("REVOKE ALL ON TABLE public.raos_migration_version FROM PUBLIC")
    op.execute("REVOKE ALL ON TABLE public.raos_migration_history FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON SEQUENCE public.raos_migration_history_event_id_seq FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "public.raos_reject_migration_history_mutation_st0301() FROM PUBLIC"
    )
    op.execute(
        "COMMENT ON TABLE public.raos_migration_history IS "
        "'ST-0301 append-only migration attempt history'"
    )


def downgrade() -> None:
    raise RuntimeError("ST0301_HISTORY_ANCHOR_RETAINED")
