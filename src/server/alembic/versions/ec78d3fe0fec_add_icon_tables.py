"""Add icon tables

Revision ID: ec78d3fe0fec
Revises: 6af1c694f387
Create Date: 2020-11-18 09:12:43.050076

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ec78d3fe0fec"
down_revision = "6af1c694f387"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "icons",
        sa.Column("icon_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_blake2b_hash", postgresql.BYTEA(length=64), nullable=False),
        sa.Column("pixel_size", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("icon_uuid"),
    )
    op.create_index(
        op.f("ix_icons_original_blake2b_hash"),
        "icons",
        ["original_blake2b_hash"],
        unique=True,
    )
    op.create_table(
        "domain_icons",
        sa.Column("scheme", sa.String(), nullable=False),
        sa.Column("netloc", sa.String(), nullable=False),
        sa.Column("icon_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["icon_uuid"], ["icons.icon_uuid"],),
        sa.PrimaryKeyConstraint("scheme", "netloc"),
    )
    op.create_index(
        op.f("ix_domain_icons_icon_uuid"), "domain_icons", ["icon_uuid"], unique=False
    )
    op.create_table(
        "url_icons",
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("icon_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["icon_uuid"], ["icons.icon_uuid"],),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("url_uuid"),
    )
    op.create_index(
        op.f("ix_url_icons_icon_uuid"), "url_icons", ["icon_uuid"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_url_icons_icon_uuid"), table_name="url_icons")
    op.drop_table("url_icons")
    op.drop_index(op.f("ix_domain_icons_icon_uuid"), table_name="domain_icons")
    op.drop_table("domain_icons")
    op.drop_index(op.f("ix_icons_original_blake2b_hash"), table_name="icons")
    op.drop_table("icons")
