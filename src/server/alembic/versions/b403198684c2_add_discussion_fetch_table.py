"""Add discussion fetch table

Revision ID: b403198684c2
Revises: 0067f9395dcd
Create Date: 2021-01-03 13:10:11.764881

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b403198684c2"
down_revision = "0067f9395dcd"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sql_discussion_fetches",
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
        op.f("ix_sql_discussion_fetches_retrieved"),
        "sql_discussion_fetches",
        ["retrieved"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sql_discussion_fetches_status_code"),
        "sql_discussion_fetches",
        ["status_code"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_sql_discussion_fetches_status_code"),
        table_name="sql_discussion_fetches",
    )
    op.drop_index(
        op.f("ix_sql_discussion_fetches_retrieved"), table_name="sql_discussion_fetches"
    )
    op.drop_table("sql_discussion_fetches")
