"""Add created and description to bookmarks

Revision ID: 06c58950ae27
Revises: 3fc331ea2de7
Create Date: 2019-12-23 17:06:46.618428

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "06c58950ae27"
down_revision = "3fc331ea2de7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bookmarks", sa.Column("created", sa.DateTime(timezone=True), nullable=False)
    )
    op.add_column("bookmarks", sa.Column("description", sa.String(), nullable=False))
    op.create_index(
        op.f("ix_bookmarks_created"), "bookmarks", ["created"], unique=False
    )
    op.create_index(
        op.f("ix_bookmarks_description"), "bookmarks", ["description"], unique=False
    )
    op.create_index(op.f("ix_urls_url_uuid"), "urls", ["url_uuid"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_urls_url_uuid"), table_name="urls")
    op.drop_index(op.f("ix_bookmarks_description"), table_name="bookmarks")
    op.drop_index(op.f("ix_bookmarks_created"), table_name="bookmarks")
    op.drop_column("bookmarks", "description")
    op.drop_column("bookmarks", "created")
