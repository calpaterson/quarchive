"""Data functions related to discussions"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Tuple, Optional
from logging import getLogger
from uuid import UUID

from sqlalchemy import and_, case
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import select, literal, Select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from quarchive.value_objects import DiscussionSource, URL, Discussion
from .models import (
    DomainIcon,
    SQLABookmark,
    SQLDiscussionSource,
    SQLDiscussionFetch,
    SQLAUrl,
    SQLDiscussion,
)
from .functions import upsert_urls

log = getLogger(__name__)


class DiscussionFrontier:
    def __init__(self, session: Session, cutoff: Optional[datetime] = None):
        self.session = session
        if cutoff is None:
            self.cutoff = datetime.utcnow() - timedelta(days=31)
        else:
            self.cutoff = cutoff

        self.b = SQLABookmark.__table__
        self.ds = SQLDiscussionSource.__table__
        self.df = SQLDiscussionFetch.__table__
        self.u = SQLAUrl.__table__

    def _build_frontier_query(self) -> Select:
        query = (
            select([self.b.c.url_uuid, self.ds.c.discussion_source_id])
            .select_from(
                self.u.join(self.b)
                .join(self.ds, literal(True))
                .outerjoin(
                    self.df,
                    and_(
                        self.df.c.url_uuid == self.b.c.url_uuid,
                        self.df.c.discussion_source_id
                        == self.ds.c.discussion_source_id,
                        self.df.c.status_code == 200,
                        self.df.c.retrieved > self.cutoff,
                    ),
                )
            )
            .where(~self.u.c.netloc.like("%example.com"))
            .where(self.df.c.url_uuid.is_(None))
        )
        return query

    def contains_url_uuid(self, url_uuid: UUID) -> bool:
        ...

    def size(self) -> int:
        ...

    def iter(
        self, limit: Optional[int] = None
    ) -> Iterable[Tuple[UUID, DiscussionSource]]:
        query = self._build_frontier_query()
        if limit is not None:
            query = query.limit(limit)
        yield from (
            (u, DiscussionSource(s_id)) for (u, s_id) in self.session.execute(query)
        )


def upsert_discussions(session: Session, discussions: Iterable[Discussion]) -> None:
    stmt_values = []
    urls = set()
    for d in discussions:
        urls.add(d.url)
        stmt_values.append(
            {
                "external_discussion_id": d.external_id,
                "discussion_source_id": d.source.value,
                "url_uuid": d.url.url_uuid,
                "comment_count": d.comment_count,
                "created_at": d.created_at,
                "title": d.title,
            }
        )
    discussion_count = len(stmt_values)
    log.info("upserting %d discussions across %d urls", discussion_count, len(urls))
    if discussion_count == 0:
        # Nothing to upsert
        return
    upsert_urls(session, urls)
    insert_stmt = pg_insert(SQLDiscussion.__table__).values(stmt_values)
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["discussion_source_id", "external_discussion_id"],
        set_={
            "url_uuid": insert_stmt.excluded.url_uuid,
            "comment_count": insert_stmt.excluded.comment_count,
            "created_at": insert_stmt.excluded.created_at,
            "title": insert_stmt.excluded.title,
        },
    )
    session.execute(upsert_stmt)


def record_discussion_fetch(
    session: Session, url: URL, source: DiscussionSource
) -> None:
    insert_stmt = pg_insert(SQLDiscussionFetch.__table__).values(
        dict(
            url_uuid=url.url_uuid,
            discussion_source_id=source.value,
            status_code=200,  # FIXME: this column should probably have been a boolean
            retrieved=datetime.utcnow().replace(tzinfo=timezone.utc),
        )
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["url_uuid", "discussion_source_id"],
        set_={
            "status_code": insert_stmt.excluded.status_code,
            "retrieved": insert_stmt.excluded.retrieved,
        },
    )
    session.execute(upsert_stmt)


def sql_discussion_to_discussion(url: URL, sql_discussion: SQLDiscussion) -> Discussion:
    return Discussion(
        external_id=sql_discussion.external_discussion_id,
        source=DiscussionSource(sql_discussion.discussion_source_id),
        url=url,
        title=sql_discussion.title,
        created_at=sql_discussion.created_at,
        comment_count=sql_discussion.comment_count,
    )


def get_discussions_by_url(session: Session, url: URL) -> Iterable["DiscussionView"]:
    sql_discussions = (
        session.query(SQLDiscussion)
        .filter(SQLDiscussion.url_uuid == url.url_uuid)
        .order_by(SQLDiscussion.comment_count.desc())
    )
    for sql_d in sql_discussions:
        discussion = sql_discussion_to_discussion(url, sql_d)
        yield DiscussionView(discussion=discussion)


@dataclass
class DiscussionView:
    discussion: Discussion

    def title(self) -> str:
        return self.discussion.title

    def url(self) -> URL:
        if self.discussion.source == DiscussionSource.HN:
            return URL.from_string(
                f"https://news.ycombinator.com/item?id={self.discussion.external_id}"
            )
        else:
            return URL.from_string(
                f"https://old.reddit.com/{self.discussion.external_id}"
            )

    def icon_path(self) -> str:
        if self.discussion.source == DiscussionSource.HN:
            filename = "hn.png"
        else:
            filename = "reddit.png"
        return f"icons/{filename}"
