"""Remove index from crawl_responses.headers

Revision ID: ab403d97d9fa
Revises: 9270d860cf1f
Create Date: 2020-01-25 20:05:19.738799

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab403d97d9fa"
down_revision = "9270d860cf1f"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_crawl_responses_headers", table_name="crawl_responses")


def downgrade():
    op.create_index(
        "ix_crawl_responses_headers", "crawl_responses", ["headers"], unique=False
    )
