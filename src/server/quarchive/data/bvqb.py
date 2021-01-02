from typing import Iterable
from uuid import UUID

from sqlalchemy import func, and_, distinct, SmallInteger
from sqlalchemy.orm import aliased, Session, joinedload
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY

from ..value_objects import User, BookmarkView, DiscussionDigest, DiscussionSource
from .models import (
    BookmarkTag,
    CanonicalUrl,
    DomainIcon,
    FullText,
    Link,
    SQLABookmark,
    SQLAUrl,
    SQLDiscussion,
    Tag,
    URLIcon,
)
from .functions import bookmark_from_sqla


class BookmarkViewQueryBuilder:
    def __init__(
        self, session: Session, user: User, page_size: int = 30, page: int = 1
    ):
        self.page_size = page_size
        self.page = page
        self.user = user
        self._session = session
        self._query = self._create_initial_query()

        # omit deleted bookmarks
        self._query = self._query.filter(~SQLABookmark.deleted)

    def _get_offset(self) -> int:
        return (self.page - 1) * self.page_size

    def _create_initial_query(self):
        # FIXME: The point has been reached where this should done using
        # SQLAlchemy core

        CanonicalSQLAUrl = aliased(SQLAUrl)

        B2 = aliased(SQLABookmark)
        link_counts = (
            self._session.query(
                SQLABookmark.url_uuid.label("url_uuid"),
                func.count().label("link_count"),
            )
            .join(Link, Link.from_url_uuid == SQLABookmark.url_uuid)
            .join(B2, Link.to_url_uuid == B2.url_uuid)
            .filter(SQLABookmark.url_uuid != B2.url_uuid)
            .filter(SQLABookmark.user_uuid == self.user.user_uuid)
            .filter(B2.user_uuid == self.user.user_uuid)
            .group_by(SQLABookmark.url_uuid)
            .subquery()
        )

        B3 = aliased(SQLABookmark)
        backlink_counts = (
            self._session.query(
                SQLABookmark.url_uuid.label("url_uuid"),
                func.count().label("backlink_count"),
            )
            .join(Link, Link.to_url_uuid == SQLABookmark.url_uuid)
            .join(B3, Link.from_url_uuid == B3.url_uuid)
            .filter(SQLABookmark.url_uuid != B3.url_uuid)
            .filter(SQLABookmark.user_uuid == self.user.user_uuid)
            .filter(B3.user_uuid == self.user.user_uuid)
            .group_by(SQLABookmark.url_uuid)
            .subquery()
        )

        discussion_digests = (
            self._session.query(
                SQLABookmark.url_uuid.label("url_uuid"),
                func.sum(SQLDiscussion.comment_count).label("comment_count"),
                func.count(SQLDiscussion.external_discussion_id).label(
                    "discussion_count"
                ),
                func.array_agg(SQLDiscussion.discussion_source_id).label("source_ids"),
            )
            .join(SQLDiscussion, SQLDiscussion.url_uuid == SQLABookmark.url_uuid)
            .filter(SQLABookmark.user_uuid == self.user.user_uuid)
            .group_by(SQLABookmark.url_uuid)
            .subquery()
        )

        query = (
            self._session.query(
                SQLAUrl,
                CanonicalSQLAUrl,
                SQLABookmark,
                func.coalesce(URLIcon.icon_uuid, DomainIcon.icon_uuid),
                func.coalesce(link_counts.c.link_count, 0),
                func.coalesce(backlink_counts.c.backlink_count, 0),
                func.coalesce(discussion_digests.c.comment_count, 0),
                func.coalesce(discussion_digests.c.discussion_count, 0),
                discussion_digests.c.source_ids,
            )
            .join(SQLABookmark, SQLAUrl.url_uuid == SQLABookmark.url_uuid)
            .options(joinedload(SQLABookmark.bookmark_tag_objs))
            .outerjoin(link_counts, link_counts.c.url_uuid == SQLABookmark.url_uuid)
            .outerjoin(
                backlink_counts, backlink_counts.c.url_uuid == SQLABookmark.url_uuid
            )
            .outerjoin(
                discussion_digests,
                SQLABookmark.url_uuid == discussion_digests.c.url_uuid,
            )
            .outerjoin(
                CanonicalUrl, SQLAUrl.url_uuid == CanonicalUrl.non_canonical_url_uuid
            )
            .outerjoin(
                CanonicalSQLAUrl,
                CanonicalUrl.canonical_url_uuid == CanonicalSQLAUrl.url_uuid,
            )
            .outerjoin(URLIcon, SQLAUrl.url_uuid == URLIcon.url_uuid)
            .outerjoin(
                DomainIcon,
                and_(
                    DomainIcon.scheme == SQLAUrl.scheme,
                    DomainIcon.netloc == SQLAUrl.netloc,
                ),
            )
            .filter(SQLABookmark.user_uuid == self.user.user_uuid)
        )
        return query

    def with_tag(self, tag: str) -> "BookmarkViewQueryBuilder":
        self._query = (
            self._query.join(BookmarkTag).join(Tag).filter(Tag.tag_name == tag)
        )
        return self

    def links(self, url_uuid: UUID) -> "BookmarkViewQueryBuilder":
        Link2 = aliased(Link)
        SQLABookmarkLink = aliased(SQLABookmark)
        self._query = (
            self._query.join(Link2, Link2.to_url_uuid == SQLAUrl.url_uuid)
            .join(SQLABookmarkLink, Link2.to_url_uuid == SQLABookmarkLink.url_uuid)
            .filter(Link2.from_url_uuid == url_uuid)
            .filter(Link2.to_url_uuid != Link2.from_url_uuid)
            .filter(SQLABookmarkLink.user_uuid == self.user.user_uuid)
            .filter(~SQLABookmarkLink.deleted)
        )
        return self

    def backlinks(self, url_uuid: UUID) -> "BookmarkViewQueryBuilder":
        Backlink = aliased(Link)
        SQLABookmarkBacklink = aliased(SQLABookmark)
        self._query = (
            self._query.join(Backlink, Backlink.from_url_uuid == SQLAUrl.url_uuid)
            .join(
                SQLABookmarkBacklink,
                Backlink.to_url_uuid == SQLABookmarkBacklink.url_uuid,
            )
            .filter(Backlink.to_url_uuid == url_uuid)
            .filter(Backlink.to_url_uuid != Backlink.from_url_uuid)
            .filter(SQLABookmarkBacklink.user_uuid == self.user.user_uuid)
            .filter(~SQLABookmarkBacklink.deleted)
        )
        return self

    def with_netloc(self, netloc: str) -> "BookmarkViewQueryBuilder":
        self._query = self._query.filter(SQLAUrl.netloc == netloc)
        return self

    def has_previous_page(self) -> bool:
        return self.page > 1

    def has_next_page(self) -> bool:
        return self._session.query(
            self._query.offset(self._get_offset() + self.page_size).exists()
        ).scalar()

    def text_search(self, tquery_str: str) -> "BookmarkViewQueryBuilder":
        self._query = self._query.outerjoin(
            FullText, FullText.url_uuid == SQLABookmark.url_uuid
        )
        # necessary to coalesce this as there may be no fulltext
        fulltext = func.coalesce(FullText.tsvector, func.to_tsvector(""))

        self._combined_tsvector = (
            func.to_tsvector(SQLABookmark.title)
            .op("||")(func.to_tsvector(SQLABookmark.description))
            .op("||")(fulltext)
        )
        self._tsquery = func.to_tsquery(tquery_str)
        self._query = self._query.filter(
            self._combined_tsvector.op("@@")(self._tsquery)
        )
        return self

    def only_url(self, url_uuid: UUID) -> "BookmarkViewQueryBuilder":
        self._query = self._query.filter(SQLAUrl.url_uuid == url_uuid)
        return self

    def order_by_created(self) -> "BookmarkViewQueryBuilder":
        self._query = self._query.order_by(SQLABookmark.created.desc())
        return self

    def order_by_search_rank(self) -> "BookmarkViewQueryBuilder":
        self._query.order_by(func.ts_rank(self._combined_tsvector, self._tsquery, 1))
        return self

    def execute(self) -> Iterable[BookmarkView]:
        paged_query = self._query.offset(self._get_offset()).limit(self.page_size)
        for (
            sqla_url,
            canonical_sqla_url,
            sqla_bookmark,
            icon_uuid,
            link_count,
            backlink_count,
            comment_count,
            discussion_count,
            source_ids,
        ) in paged_query:
            bookmark_view = BookmarkView(
                owner=self.user,
                bookmark=bookmark_from_sqla(sqla_url.to_url(), sqla_bookmark),
                icon_uuid=icon_uuid,
                canonical_url=canonical_sqla_url.to_url()
                if canonical_sqla_url is not None
                else None,
                link_count=link_count,
                backlink_count=backlink_count,
                discussion_digest=DiscussionDigest(
                    comment_count=comment_count,
                    discussion_count=discussion_count,
                    sources=set(DiscussionSource(i) for i in set(source_ids))
                    if source_ids is not None
                    else set(),
                ),
            )
            yield bookmark_view


def bookmarks_with_tag(session, user: User, tag: str) -> Iterable[BookmarkView]:
    yield from BookmarkViewQueryBuilder(session, user).with_tag(tag).execute()


def bookmarks_with_netloc(session, user: User, netloc: str) -> Iterable[BookmarkView]:
    yield from BookmarkViewQueryBuilder(session, user).with_netloc(netloc).execute()
