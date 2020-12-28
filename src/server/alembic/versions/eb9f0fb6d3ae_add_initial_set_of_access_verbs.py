"""Add initial set of access verbs

Revision ID: eb9f0fb6d3ae
Revises: 20a01e824eee
Create Date: 2020-12-28 12:51:04.008572

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "eb9f0fb6d3ae"
down_revision = "20a01e824eee"
branch_labels = None
depends_on = None

access_verbs_table = sa.table(
    "access_verbs",
    sa.column("access_verb_id", sa.SmallInteger),
    sa.column("access_verb_name", sa.String),
)


def upgrade():
    op.bulk_insert(
        access_verbs_table,
        [
            {"access_verb_id": 0, "access_verb_name": "NONE"},
            {"access_verb_id": 1, "access_verb_name": "READ"},
            {"access_verb_id": 2, "access_verb_name": "WRITE"},
            {"access_verb_id": 3, "access_verb_name": "READWRITE"},
            {"access_verb_id": 4, "access_verb_name": "READACCESS"},
            {"access_verb_id": 8, "access_verb_name": "WRITEACCESS"},
            {"access_verb_id": 15, "access_verb_name": "ALL"},
        ],
    )


def downgrade():
    op.truncate("access_verbs")
