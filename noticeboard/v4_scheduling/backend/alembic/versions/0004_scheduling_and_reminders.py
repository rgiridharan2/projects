"""scheduling and reminders

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06

- milestones.due_date: DATE -> TIMESTAMPTZ (an exact deadline instead of a whole day).
- milestones.milestone_order: position within the cohort, unique per cohort.
- schedule_blocks: timed sessions shown on the trainee agenda.
- reminders: a manager's nudge about one overdue task.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing dates become "23:59 UTC on that day": the end of the day the task was due.
    op.alter_column(
        "milestones",
        "due_date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="(due_date + time '23:59') AT TIME ZONE 'UTC'",
    )

    # Number existing milestones 1, 2, 3... per cohort by due date, then make the column required.
    op.add_column("milestones", sa.Column("milestone_order", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE milestones m SET milestone_order = ranked.n
        FROM (SELECT id, row_number() OVER (PARTITION BY cohort_id ORDER BY due_date, id) AS n FROM milestones) ranked
        WHERE m.id = ranked.id
        """
    )
    op.alter_column("milestones", "milestone_order", nullable=False)
    op.create_unique_constraint(op.f("uq_milestones_cohort_id"), "milestones", ["cohort_id", "milestone_order"])

    op.execute(sa.schema.CreateSequence(sa.Sequence("schedule_blocks_id_seq")))
    op.create_table(
        "schedule_blocks",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("cohort_id", sa.String(length=20), nullable=False),
        sa.Column("milestone_id", sa.String(length=20), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cohort_id"], ["cohorts.id"], name=op.f("fk_schedule_blocks_cohort_id_cohorts")),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"], name=op.f("fk_schedule_blocks_milestone_id_milestones")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_blocks")),
    )
    op.create_index(op.f("ix_schedule_blocks_cohort_id"), "schedule_blocks", ["cohort_id"], unique=False)
    op.create_index(op.f("ix_schedule_blocks_starts_at"), "schedule_blocks", ["starts_at"], unique=False)

    op.execute(sa.schema.CreateSequence(sa.Sequence("reminders_id_seq")))
    op.create_table(
        "reminders",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("trainee_id", sa.String(length=20), nullable=False),
        sa.Column("milestone_id", sa.String(length=20), nullable=False),
        sa.Column("sent_by", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], name=op.f("fk_reminders_milestone_id_milestones")),
        sa.ForeignKeyConstraint(["sent_by"], ["users.id"], name=op.f("fk_reminders_sent_by_users")),
        sa.ForeignKeyConstraint(["trainee_id"], ["users.id"], name=op.f("fk_reminders_trainee_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index(op.f("ix_reminders_trainee_id"), "reminders", ["trainee_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reminders_trainee_id"), table_name="reminders")
    op.drop_table("reminders")
    op.execute(sa.schema.DropSequence(sa.Sequence("reminders_id_seq")))

    op.drop_index(op.f("ix_schedule_blocks_starts_at"), table_name="schedule_blocks")
    op.drop_index(op.f("ix_schedule_blocks_cohort_id"), table_name="schedule_blocks")
    op.drop_table("schedule_blocks")
    op.execute(sa.schema.DropSequence(sa.Sequence("schedule_blocks_id_seq")))

    op.drop_constraint(op.f("uq_milestones_cohort_id"), "milestones", type_="unique")
    op.drop_column("milestones", "milestone_order")
    op.alter_column(
        "milestones",
        "due_date",
        type_=sa.Date(),
        postgresql_using="(due_date AT TIME ZONE 'UTC')::date",
    )
