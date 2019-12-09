"""initial schema

Revision ID: b1fd31fdbd7a
Revises:
Create Date: 2019-12-09 16:33:05.739915

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b1fd31fdbd7a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "urls",
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme", sa.String(), nullable=False),
        sa.Column("netloc", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("fragment", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("scheme", "netloc", "path", "query", "fragment"),
    )
    op.create_index(op.f("ix_urls_fragment"), "urls", ["fragment"], unique=False)
    op.create_index(op.f("ix_urls_netloc"), "urls", ["netloc"], unique=False)
    op.create_index(op.f("ix_urls_path"), "urls", ["path"], unique=False)
    op.create_index(op.f("ix_urls_query"), "urls", ["query"], unique=False)
    op.create_index(op.f("ix_urls_scheme"), "urls", ["scheme"], unique=False)
    op.create_index(op.f("ix_urls_uuid"), "urls", ["uuid"], unique=True)
    op.create_table(
        "bookmarks",
        sa.Column("url", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unread", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["url"], ["urls.uuid"],),
        sa.PrimaryKeyConstraint("url"),
    )
    op.create_index(
        op.f("ix_bookmarks_deleted"), "bookmarks", ["deleted"], unique=False
    )
    op.create_index(op.f("ix_bookmarks_title"), "bookmarks", ["title"], unique=False)
    op.create_index(op.f("ix_bookmarks_unread"), "bookmarks", ["unread"], unique=False)
    op.create_index(
        op.f("ix_bookmarks_updated"), "bookmarks", ["updated"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_bookmarks_updated"), table_name="bookmarks")
    op.drop_index(op.f("ix_bookmarks_unread"), table_name="bookmarks")
    op.drop_index(op.f("ix_bookmarks_title"), table_name="bookmarks")
    op.drop_index(op.f("ix_bookmarks_deleted"), table_name="bookmarks")
    op.drop_table("bookmarks")
    op.drop_index(op.f("ix_urls_uuid"), table_name="urls")
    op.drop_index(op.f("ix_urls_scheme"), table_name="urls")
    op.drop_index(op.f("ix_urls_query"), table_name="urls")
    op.drop_index(op.f("ix_urls_path"), table_name="urls")
    op.drop_index(op.f("ix_urls_netloc"), table_name="urls")
    op.drop_index(op.f("ix_urls_fragment"), table_name="urls")
    op.drop_table("urls")
