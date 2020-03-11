"""Add user and user email tables

Revision ID: 9a9e827e3ab5
Revises: 811d023d3ea2
Create Date: 2020-03-11 21:57:09.440814

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9a9e827e3ab5"
down_revision = "811d023d3ea2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("user_uuid"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_table(
        "user_emails",
        sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_address", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["user_uuid"], ["users.user_uuid"],),
        sa.PrimaryKeyConstraint("user_uuid"),
    )
    op.create_index(
        op.f("ix_user_emails_email_address"),
        "user_emails",
        ["email_address"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_user_emails_email_address"), table_name="user_emails")
    op.drop_table("user_emails")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
