"""Standardise url.url_uuid column name

Revision ID: 3fc331ea2de7
Revises: b1fd31fdbd7a
Create Date: 2019-12-21 15:05:39.528180

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3fc331ea2de7"
down_revision = "b1fd31fdbd7a"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("urls", "uuid", new_column_name="url_uuid")
    op.alter_column("bookmarks", "url", new_column_name="url_uuid")


def downgrade():
    op.alter_column("urls", "url_uuid", new_column_name="uuid")
    op.alter_column("bookmarks", "uuid", new_column_name="url")
