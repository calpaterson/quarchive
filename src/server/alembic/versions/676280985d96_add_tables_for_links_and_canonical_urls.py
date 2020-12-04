"""Add tables for links and canonical urls

Revision ID: 676280985d96
Revises: 64adb9cc1343
Create Date: 2020-12-04 16:07:04.372322

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "676280985d96"
down_revision = "64adb9cc1343"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "canonical_urls",
        sa.Column("canonical_url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "non_canonical_url_uuid", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.ForeignKeyConstraint(["canonical_url_uuid"], ["urls.url_uuid"],),
        sa.ForeignKeyConstraint(["non_canonical_url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("canonical_url_uuid", "non_canonical_url_uuid"),
        sa.UniqueConstraint("non_canonical_url_uuid"),
    )
    op.create_index(
        op.f("ix_canonical_urls_canonical_url_uuid"),
        "canonical_urls",
        ["canonical_url_uuid"],
        unique=False,
    )
    op.create_table(
        "links",
        sa.Column("from_url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["from_url_uuid"], ["urls.url_uuid"],),
        sa.ForeignKeyConstraint(["to_url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("from_url_uuid", "to_url_uuid"),
    )
    op.create_index(
        op.f("ix_links_from_url_uuid"), "links", ["from_url_uuid"], unique=False
    )
    op.create_index(
        op.f("ix_links_to_url_uuid"), "links", ["to_url_uuid"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_links_to_url_uuid"), table_name="links")
    op.drop_index(op.f("ix_links_from_url_uuid"), table_name="links")
    op.drop_table("links")
    op.drop_index(
        op.f("ix_canonical_urls_canonical_url_uuid"), table_name="canonical_urls"
    )
    op.drop_table("canonical_urls")
