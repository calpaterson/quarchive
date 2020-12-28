"""Add share link tables

Revision ID: 20a01e824eee
Revises: 676280985d96
Create Date: 2020-12-28 12:43:27.584266

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20a01e824eee"
down_revision = "676280985d96"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "access_objects",
        sa.Column(
            "access_object_id", sa.BigInteger(), autoincrement=True, nullable=False
        ),
        sa.Column("access_object_name", sa.String(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("access_object_id"),
        sa.UniqueConstraint("access_object_name", "params"),
    )
    op.create_table(
        "access_verbs",
        sa.Column(
            "access_verb_id", sa.SmallInteger(), nullable=False, autoincrement=False
        ),
        sa.Column("access_verb_name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("access_verb_id"),
        sa.UniqueConstraint("access_verb_name"),
    )
    op.create_table(
        "share_grants",
        sa.Column("access_object_id", sa.BigInteger(), nullable=False),
        sa.Column("access_verb_id", sa.SmallInteger(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("share_token", postgresql.BYTEA(), nullable=False),
        sa.ForeignKeyConstraint(
            ["access_object_id"], ["access_objects.access_object_id"],
        ),
        sa.ForeignKeyConstraint(["access_verb_id"], ["access_verbs.access_verb_id"],),
        sa.PrimaryKeyConstraint("share_token"),
    )
    op.create_index(
        op.f("ix_share_grants_revoked"), "share_grants", ["revoked"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_share_grants_revoked"), table_name="share_grants")
    op.drop_table("share_grants")
    op.drop_table("access_verbs")
    op.drop_table("access_objects")
