"""audit log and escalations

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06

- audit_events: who did which administrative action, when (the activity drawer).
- escalations: tasks flagged for being more than 48 hours past deadline with nothing submitted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("audit_events_id_seq")))
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=20), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=20), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name=op.f("fk_audit_events_actor_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_created_at"), "audit_events", ["created_at"], unique=False)

    op.execute(sa.schema.CreateSequence(sa.Sequence("escalations_id_seq")))
    op.create_table(
        "escalations",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("trainee_id", sa.String(length=20), nullable=False),
        sa.Column("milestone_id", sa.String(length=20), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], name=op.f("fk_escalations_milestone_id_milestones")),
        sa.ForeignKeyConstraint(["trainee_id"], ["users.id"], name=op.f("fk_escalations_trainee_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalations")),
        sa.UniqueConstraint("trainee_id", "milestone_id", name=op.f("uq_escalations_trainee_id")),
    )


def downgrade() -> None:
    op.drop_table("escalations")
    op.execute(sa.schema.DropSequence(sa.Sequence("escalations_id_seq")))
    op.drop_index(op.f("ix_audit_events_created_at"), table_name="audit_events")
    op.drop_table("audit_events")
    op.execute(sa.schema.DropSequence(sa.Sequence("audit_events_id_seq")))
