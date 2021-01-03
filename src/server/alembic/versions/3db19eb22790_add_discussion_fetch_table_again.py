"""Add discussion fetch table (again)

Revision ID: 3db19eb22790
Revises: 0067f9395dcd
Create Date: 2021-01-03 14:41:58.778377

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3db19eb22790"
down_revision = "0067f9395dcd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discussion_fetches",
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discussion_source_id", sa.SmallInteger(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("retrieved", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["discussion_source_id"], ["discussion_sources.discussion_source_id"],
        ),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("url_uuid", "discussion_source_id"),
    )
    op.create_index(
        op.f("ix_discussion_fetches_retrieved"),
        "discussion_fetches",
        ["retrieved"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discussion_fetches_status_code"),
        "discussion_fetches",
        ["status_code"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_discussion_fetches_status_code"), table_name="discussion_fetches"
    )
    op.drop_index(
        op.f("ix_discussion_fetches_retrieved"), table_name="discussion_fetches"
    )
    op.drop_table("discussion_fetches")
