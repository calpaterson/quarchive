"""Add discussion source data

Revision ID: 0067f9395dcd
Revises: 6d95f2bca9da
Create Date: 2020-12-30 16:37:17.450543

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0067f9395dcd"
down_revision = "6d95f2bca9da"
branch_labels = None
depends_on = None

discussion_source_table = sa.table(
    "discussion_sources",
    sa.column("discussion_source_id", sa.SmallInteger),
    sa.column("discussion_source_name", sa.String),
)


def upgrade():
    op.bulk_insert(
        discussion_source_table,
        [
            {"discussion_source_id": 1, "discussion_source_name": "HN"},
            {"discussion_source_id": 2, "discussion_source_name": "REDDIT"},
        ],
    )


def downgrade():
    op.truncate("discussion_sources")
