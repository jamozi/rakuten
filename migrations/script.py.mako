"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

RAOS metadata (replace every REQUIRED value before cataloging this revision):
- story: REQUIRED_STORY_ID
- requirement IDs: REQUIRED_REQUIREMENT_IDS_OR_NONE
- architecture: REQUIRED_ARCHITECTURE_SLICE
- risk class: REQUIRED_RISK_CLASS
- estimated lock: REQUIRED_LOCK_ESTIMATE
- backfill job: REQUIRED_JOB_OR_NONE
- rollback category: REQUIRED_ROLLBACK_CATEGORY
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "raise RuntimeError('FORWARD_RECOVERY_REQUIRED')"}
