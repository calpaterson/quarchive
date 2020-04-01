"""Add user column to bookmark

Revision ID: 33a0d76cf976
Revises: 9aaf9a10248d
Create Date: 2020-03-31 20:00:51.843439

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "33a0d76cf976"
down_revision = "9aaf9a10248d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bookmarks",
        sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_foreign_key(None, "bookmarks", "users", ["user_uuid"], ["user_uuid"])
    op.drop_constraint("bookmarks_pkey", "bookmarks")
    op.create_primary_key(None, "bookmarks", ["url_uuid", "user_uuid"])


def downgrade():
    op.drop_constraint("bookmarks_pkey", "bookmarks")
    op.drop_constraint("bookmarks_user_uuid_fkey", "bookmarks", type_="foreignkey")
    op.drop_column("bookmarks", "user_uuid")
    op.create_primary_key(None, "bookmarks", ["url_uuid"])
