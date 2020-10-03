"""Add an table for storing index errors

Revision ID: 6af1c694f387
Revises: 7136aec565b4
Create Date: 2020-10-02 20:53:27.318775

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "6af1c694f387"
down_revision = "7136aec565b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "index_errors",
        sa.Column("crawl_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_uuid"], ["crawl_requests.crawl_uuid"],),
        sa.PrimaryKeyConstraint("crawl_uuid"),
    )


def downgrade():
    op.drop_table("index_errors")
