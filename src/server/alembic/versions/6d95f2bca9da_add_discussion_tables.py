"""Add discussion tables

Revision ID: 6d95f2bca9da
Revises: 5ac4cd2a9b5c
Create Date: 2020-12-30 15:47:09.432895

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "6d95f2bca9da"
down_revision = "5ac4cd2a9b5c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discussion_sources",
        sa.Column(
            "discussion_source_id",
            sa.SmallInteger(),
            nullable=False,
            autoincrement=False,
        ),
        sa.Column("discussion_source_name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("discussion_source_id"),
        sa.UniqueConstraint("discussion_source_name"),
    )
    op.create_table(
        "discussions",
        sa.Column("external_discussion_id", sa.String(), nullable=False),
        sa.Column("discussion_source_id", sa.SmallInteger(), nullable=False),
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["discussion_source_id"], ["discussion_sources.discussion_source_id"],
        ),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("external_discussion_id", "discussion_source_id"),
    )
    op.create_index(
        op.f("ix_discussions_url_uuid"), "discussions", ["url_uuid"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_discussions_url_uuid"), table_name="discussions")
    op.drop_table("discussions")
    op.drop_table("discussion_sources")
