"""milestones and signup

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05

- milestones: tasks assigned to a cohort, each with a due date.
- submissions.milestone_id: which task a report is for (nullable: older reports have none).
- cohorts.open_for_signup: whether the cohort appears in the public sign-up dropdown.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default fills in existing cohorts; the app always sets the value itself after that.
    op.add_column(
        "cohorts", sa.Column("open_for_signup", sa.Boolean(), nullable=False, server_default=sa.true())
    )

    op.execute(sa.schema.CreateSequence(sa.Sequence("milestones_id_seq")))
    op.create_table(
        "milestones",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("cohort_id", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["cohort_id"], ["cohorts.id"], name=op.f("fk_milestones_cohort_id_cohorts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestones")),
    )
    op.create_index(op.f("ix_milestones_cohort_id"), "milestones", ["cohort_id"], unique=False)

    op.add_column("submissions", sa.Column("milestone_id", sa.String(length=20), nullable=True))
    op.create_foreign_key(
        op.f("fk_submissions_milestone_id_milestones"), "submissions", "milestones", ["milestone_id"], ["id"]
    )
    op.create_index(op.f("ix_submissions_milestone_id"), "submissions", ["milestone_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_submissions_milestone_id"), table_name="submissions")
    op.drop_constraint(op.f("fk_submissions_milestone_id_milestones"), "submissions", type_="foreignkey")
    op.drop_column("submissions", "milestone_id")

    op.drop_index(op.f("ix_milestones_cohort_id"), table_name="milestones")
    op.drop_table("milestones")
    op.execute(sa.schema.DropSequence(sa.Sequence("milestones_id_seq")))

    op.drop_column("cohorts", "open_for_signup")
