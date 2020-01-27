"""Add full text table

Revision ID: 811d023d3ea2
Revises: ab403d97d9fa
Create Date: 2020-01-27 15:16:44.664827

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "811d023d3ea2"
down_revision = "ab403d97d9fa"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "full_text",
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "crawl_uuid",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("crawl_requests.crawl_uuid"),
            nullable=False,
            index=True,
        ),
        sa.Column("inserted", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("full_text", sa.String(), nullable=False),
        sa.Column("tsvector", postgresql.TSVECTOR, nullable=False),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("url_uuid"),
    )


def downgrade():
    op.drop_table("full_text")
