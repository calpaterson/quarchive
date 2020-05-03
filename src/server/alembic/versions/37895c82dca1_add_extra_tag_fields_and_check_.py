"""Add extra tag fields and check constraints on tag and user name

Revision ID: 37895c82dca1
Revises: d0e4812162c0
Create Date: 2020-05-03 13:15:41.972762

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "37895c82dca1"
down_revision = "d0e4812162c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bookmark_tags", sa.Column("deleted", sa.Boolean(), nullable=False))
    op.add_column(
        "bookmark_tags",
        sa.Column("updated", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        op.f("ix_bookmark_tags_deleted"), "bookmark_tags", ["deleted"], unique=False
    )
    op.create_index(
        op.f("ix_bookmark_tags_updated"), "bookmark_tags", ["updated"], unique=False
    )
    op.create_check_constraint("ck_tags_tag_name", "tags", "tag_name ~ '^[-a-z0-9]+$'")
    op.create_check_constraint(
        "ck_users_username", "users", "username ~ '^[-A-z0-9]+$'"
    )


def downgrade():
    op.drop_constraint("ck_tags_tag_name", "tags")
    op.drop_constraint("ck_users_username", "users")
    op.drop_index(op.f("ix_bookmark_tags_updated"), table_name="bookmark_tags")
    op.drop_index(op.f("ix_bookmark_tags_deleted"), table_name="bookmark_tags")
    op.drop_column("bookmark_tags", "updated")
    op.drop_column("bookmark_tags", "deleted")
