"""Add user uuid index to bookmarks

Revision ID: d933061dc77f
Revises: 3db19eb22790
Create Date: 2021-11-24 22:06:50.159205

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d933061dc77f"
down_revision = "3db19eb22790"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        op.f("ix_bookmarks_user_uuid"), "bookmarks", ["user_uuid"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_bookmarks_user_uuid"), table_name="bookmarks")
