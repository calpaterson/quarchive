"""Add crawl request/response tables

Revision ID: 9270d860cf1f
Revises: 06c58950ae27
Create Date: 2020-01-13 22:08:26.542458

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9270d860cf1f"
down_revision = "06c58950ae27"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crawl_requests",
        sa.Column("crawl_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url_uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested", sa.DateTime(timezone=True), nullable=False),
        sa.Column("got_response", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["url_uuid"], ["urls.url_uuid"],),
        sa.PrimaryKeyConstraint("crawl_uuid"),
    )
    op.create_index(
        op.f("ix_crawl_requests_got_response"),
        "crawl_requests",
        ["got_response"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawl_requests_requested"),
        "crawl_requests",
        ["requested"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crawl_requests_url_uuid"), "crawl_requests", ["url_uuid"], unique=False
    )
    op.create_table(
        "crawl_responses",
        sa.Column("crawl_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["crawl_uuid"], ["crawl_requests.crawl_uuid"],),
        sa.PrimaryKeyConstraint("crawl_uuid"),
        sa.UniqueConstraint("body_uuid"),
    )
    op.create_index(
        op.f("ix_crawl_responses_headers"), "crawl_responses", ["headers"], unique=False
    )
    op.create_index(
        op.f("ix_crawl_responses_status_code"),
        "crawl_responses",
        ["status_code"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_crawl_responses_status_code"), table_name="crawl_responses")
    op.drop_index(op.f("ix_crawl_responses_headers"), table_name="crawl_responses")
    op.drop_table("crawl_responses")
    op.drop_index(op.f("ix_crawl_requests_url_uuid"), table_name="crawl_requests")
    op.drop_index(op.f("ix_crawl_requests_requested"), table_name="crawl_requests")
    op.drop_index(op.f("ix_crawl_requests_got_response"), table_name="crawl_requests")
    op.drop_table("crawl_requests")
