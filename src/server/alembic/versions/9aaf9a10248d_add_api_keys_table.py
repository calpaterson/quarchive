"""Add api_keys table

Revision ID: 9aaf9a10248d
Revises: 9a9e827e3ab5
Create Date: 2020-03-30 22:54:45.005159

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9aaf9a10248d"
down_revision = "9a9e827e3ab5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_keys",
        sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key", postgresql.BYTEA(length=16), nullable=False),
        sa.ForeignKeyConstraint(["user_uuid"], ["users.user_uuid"],),
        sa.PrimaryKeyConstraint("user_uuid"),
    )
    op.create_index(op.f("ix_api_keys_api_key"), "api_keys", ["api_key"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_api_keys_api_key"), table_name="api_keys")
    op.drop_table("api_keys")
