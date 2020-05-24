"""Add timezone column for user

Revision ID: 7136aec565b4
Revises: 226d0aa029ad
Create Date: 2020-05-24 11:45:16.083075

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7136aec565b4"
down_revision = "226d0aa029ad"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("timezone", sa.String(), nullable=True))
    op.execute("UPDATE users SET timezone = 'Europe/London'")
    op.alter_column("users", "timezone", nullable=False)


def downgrade():
    op.drop_column("users", "timezone")
