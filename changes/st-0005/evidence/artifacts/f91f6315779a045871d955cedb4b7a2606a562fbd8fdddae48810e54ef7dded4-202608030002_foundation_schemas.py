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
        "COMMENT ON SCHEMA ops IS 'ジョブ、原本レジストリ、監査、障害、Kill Switch、実行時設定'"
    )
    op.execute("REVOKE ALL ON SCHEMA ops FROM PUBLIC")
    op.execute("CREATE SCHEMA iam")
    op.execute(
        "COMMENT ON SCHEMA iam IS 'OIDC主体、アプリケーションRole、権限、緊急アクセス'"
    )
    op.execute("REVOKE ALL ON SCHEMA iam FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP SCHEMA iam RESTRICT")
    op.execute("DROP SCHEMA ops RESTRICT")
