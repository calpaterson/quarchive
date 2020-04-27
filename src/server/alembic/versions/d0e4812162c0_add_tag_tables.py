"""Add tag tables

Revision ID: d0e4812162c0
Revises: 33a0d76cf976
Create Date: 2020-04-27 18:19:35.566477

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d0e4812162c0"
down_revision = "33a0d76cf976"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tags",
        sa.Column("tag_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tag_name", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("tag_id"),
    )
    op.create_index(op.f("ix_tags_tag_name"), "tags", ["tag_name"], unique=True)
    op.create_table(
        "bookmark_tags",
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.tag_id"],),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.ForeignKeyConstraint(["user_uuid"], ["users.user_uuid"],),
        sa.PrimaryKeyConstraint("url_uuid", "user_uuid", "tag_id"),
    )
    op.create_index(
        op.f("ix_bookmark_tags_tag_id"), "bookmark_tags", ["tag_id"], unique=False
    )
    op.create_index(
        op.f("ix_bookmark_tags_url_uuid"), "bookmark_tags", ["url_uuid"], unique=False
    )
    op.create_index(
        op.f("ix_bookmark_tags_user_uuid"), "bookmark_tags", ["user_uuid"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_bookmark_tags_user_uuid"), table_name="bookmark_tags")
    op.drop_index(op.f("ix_bookmark_tags_url_uuid"), table_name="bookmark_tags")
    op.drop_index(op.f("ix_bookmark_tags_tag_id"), table_name="bookmark_tags")
    op.drop_table("bookmark_tags")
    op.drop_index(op.f("ix_tags_tag_name"), table_name="tags")
    op.drop_table("tags")
