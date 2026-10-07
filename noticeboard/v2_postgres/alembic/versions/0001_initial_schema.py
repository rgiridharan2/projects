"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-03

Generated with `alembic revision --autogenerate`, then tidied and given the id sequences
(autogenerate does not detect standalone sequences).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# One per table with a generated id; see Model.id_seq in app/models.py.
ID_SEQUENCES = ["cohorts_id_seq", "users_id_seq", "notices_id_seq", "submissions_id_seq"]


def upgrade() -> None:
    for name in ID_SEQUENCES:
        op.execute(sa.schema.CreateSequence(sa.Sequence(name)))

    op.create_table(
        "cohorts",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("track_type", sa.String(length=10), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cohorts")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("cohort_id", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["cohort_id"], ["cohorts.id"], name=op.f("fk_users_cohort_id_cohorts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_cohort_id"), "users", ["cohort_id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "notices",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("target_cohort_id", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_cohort_id"], ["cohorts.id"], name=op.f("fk_notices_target_cohort_id_cohorts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
    )
    op.create_index(op.f("ix_notices_target_cohort_id"), "notices", ["target_cohort_id"], unique=False)

    op.create_table(
        "notice_reads",
        sa.Column("notice_id", sa.String(length=20), nullable=False),
        sa.Column("trainee_id", sa.String(length=20), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notice_id"], ["notices.id"], name=op.f("fk_notice_reads_notice_id_notices")),
        sa.ForeignKeyConstraint(["trainee_id"], ["users.id"], name=op.f("fk_notice_reads_trainee_id_users")),
        sa.PrimaryKeyConstraint("notice_id", "trainee_id", name=op.f("pk_notice_reads")),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("trainee_id", sa.String(length=20), nullable=False),
        sa.Column("milestone_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("asset_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trainee_id"], ["users.id"], name=op.f("fk_submissions_trainee_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(op.f("ix_submissions_trainee_id"), "submissions", ["trainee_id"], unique=False)


def downgrade() -> None:
    # Children before parents, so no foreign key points at a dropped table.
    op.drop_index(op.f("ix_submissions_trainee_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_table("notice_reads")
    op.drop_index(op.f("ix_notices_target_cohort_id"), table_name="notices")
    op.drop_table("notices")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_cohort_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("cohorts")

    for name in reversed(ID_SEQUENCES):
        op.execute(sa.schema.DropSequence(sa.Sequence(name)))
