"""Add registration date for users

Revision ID: 5ac4cd2a9b5c
Revises: eb9f0fb6d3ae
Create Date: 2020-12-29 16:21:33.645257

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5ac4cd2a9b5c"
down_revision = "eb9f0fb6d3ae"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("registered", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("update users set registered = current_timestamp")
    op.alter_column("users", "registered", nullable=False)


def downgrade():
    op.drop_column("users", "registered")
