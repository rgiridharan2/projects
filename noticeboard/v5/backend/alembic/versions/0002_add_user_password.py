"""add user password

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04

The column is nullable on purpose: a migration can't invent passwords for users that already
exist. Those users simply can't log in until a password is set (seed.py sets one for everyone).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "hashed_password")
