"""Prevent tag_id inflation

Revision ID: 226d0aa029ad
Revises: d377220a4f4d
Create Date: 2020-05-18 16:10:16.328175

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "226d0aa029ad"
down_revision = "d377220a4f4d"
branch_labels = None
depends_on = None

FUNCTION_SQL = """
-- Insert a single bookmark
--
-- This is done as a "SQL" language query instead of via ORM-generated
-- statements or driver-level ah doc statements because it's idiomatic to do it
-- in SQL and avoids sending a bunch of data back and forth in several round
-- trips.
CREATE OR REPLACE FUNCTION insert_bookmark_v1 (
       url_uuid UUID,
       url_scheme TEXT,
       url_netloc TEXT,
       url_path TEXT,
       url_query TEXT,
       url_fragment TEXT,
       bookmark_user_uuid UUID,
       bookmark_title TEXT,
       bookmark_description TEXT,
       bookmark_created TIMESTAMP WITH TIME ZONE,
       bookmark_updated TIMESTAMP WITH TIME ZONE,
       bookmark_unread BOOLEAN,
       bookmark_deleted BOOLEAN,
       tag_triples_tag TEXT[],
       tag_triples_dt TIMESTAMPTZ[],
       tag_triples_deleted BOOLEAN[]
) RETURNS void AS $$

-- Upsert url
-- FIXME: this requires that all url_uuids are url_uuids
INSERT INTO urls (url_uuid, scheme, netloc, path, query, fragment)
VALUES (url_uuid, url_scheme, url_netloc, url_path, url_query, url_fragment)
ON CONFLICT DO NOTHING;

-- Upsert bookmark
INSERT INTO bookmarks (
url_uuid, user_uuid, created, deleted, description, title, unread, updated
) VALUES (
url_uuid,
bookmark_user_uuid,
bookmark_created,
bookmark_deleted,
bookmark_description,
bookmark_title,
bookmark_unread,
bookmark_updated
)
ON CONFLICT (url_uuid, user_uuid) DO UPDATE SET
created = excluded.created,
deleted = excluded.deleted,
description = excluded.description,
title = excluded.title,
unread = excluded.unread,
updated = excluded.updated
;

-- Upsert tags
INSERT INTO tags (tag_name)
SELECT tag_name FROM unnest(tag_triples_tag) tag_name
LEFT JOIN tags as existing_tags using (tag_name)
WHERE existing_tags.tag_name IS NULL;

-- Upsert bookmark tags
INSERT INTO bookmark_tags (url_uuid, user_uuid, tag_id, deleted, updated)
SELECT url_uuid, bookmark_user_uuid, tags.tag_id, triples.deleted, triples.updated
FROM tags
JOIN (
     SELECT tag_triples_tag[subscripts.n] as tag_name,
            tag_triples_dt[subscripts.n] as updated,
            tag_triples_deleted[subscripts.n] as deleted
     FROM (SELECT generate_subscripts(tag_triples_tag, 1) AS n) AS subscripts
     ) AS triples
ON tags.tag_name = triples.tag_name
ON CONFLICT (url_uuid, user_uuid, tag_id) DO UPDATE SET
deleted = excluded.deleted,
updated = excluded.updated
;

$$ LANGUAGE SQL;

"""


def upgrade():
    op.execute(FUNCTION_SQL)


def downgrade():
    raise NotImplementedError()
