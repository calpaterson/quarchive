from typing import TYPE_CHECKING, Any, List
from uuid import UUID

from sqlalchemy import Column, ForeignKey, and_, types as satypes, UniqueConstraint
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TSVECTOR, UUID as _PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import RelationshipProperty, foreign, relationship, remote, backref
from sqlalchemy.schema import CheckConstraint

from quarchive.value_objects import URL, Discussion, DiscussionSource

# https://github.com/dropbox/sqlalchemy-stubs/issues/94
if TYPE_CHECKING:
    PGUUID = satypes.TypeEngine[UUID]
else:
    PGUUID = _PGUUID(as_uuid=True)

Base: Any = declarative_base()


class SQLAUrl(Base):
    __tablename__ = "urls"

    # Synthetic key for foreign references
    url_uuid = Column(PGUUID, nullable=False, index=True, unique=True)

    # The actual url
    scheme = Column(satypes.String, nullable=False, index=True, primary_key=True)
    netloc = Column(satypes.String, nullable=False, index=True, primary_key=True)
    path = Column(satypes.String, nullable=False, index=True, primary_key=True)
    query = Column(satypes.String, nullable=False, index=True, primary_key=True)
    fragment = Column(satypes.String, nullable=False, index=True, primary_key=True)

    def to_url(self) -> URL:
        return URL(
            self.url_uuid,
            self.scheme,
            self.netloc,
            self.path,
            self.query,
            self.fragment,
        )

    @classmethod
    def from_url(self, url: URL) -> "SQLAUrl":
        return SQLAUrl(
            url_uuid=url.url_uuid,
            scheme=url.scheme,
            netloc=url.netloc,
            path=url.path,
            query=url.query,
            fragment=url.fragment,
        )

    def to_url_string(self) -> str:
        return self.to_url().to_string()

    links: "RelationshipProperty[Link]" = relationship(
        "Link",
        primaryjoin="SQLAUrl.url_uuid==Link.from_url_uuid",
        backref=backref("from_url_obj", uselist=False),
    )
    backlinks: "RelationshipProperty[Link]" = relationship(
        "Link",
        primaryjoin="SQLAUrl.url_uuid==Link.to_url_uuid",
        backref=backref("to_url_obj", uselist=False),
    )

    canonical_url_obj: "RelationshipProperty[CanonicalUrl]" = relationship(
        "CanonicalUrl",
        primaryjoin="SQLAUrl.url_uuid==CanonicalUrl.non_canonical_url_uuid",
        uselist=False,
    )


class Link(Base):
    """Links between urls, stored as a tuple of (from, to)."""

    __tablename__ = "links"

    from_url_uuid = Column(
        PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, index=True
    )
    to_url_uuid = Column(
        PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, index=True
    )


class CanonicalUrl(Base):
    """Canonical urls, stored as a tuple of (canon, non-canon)."""

    __tablename__ = "canonical_urls"

    canonical_url_uuid = Column(
        PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, index=True
    )
    non_canonical_url_uuid = Column(
        PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, unique=True
    )


class SQLABookmark(Base):
    __tablename__ = "bookmarks"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True)
    user_uuid = Column(
        PGUUID, ForeignKey("users.user_uuid"), primary_key=True, index=True
    )

    title = Column(satypes.String, nullable=False, index=True)
    description = Column(satypes.String, nullable=False, index=True)

    created = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    updated = Column(satypes.DateTime(timezone=True), nullable=False, index=True)

    unread = Column(satypes.Boolean, nullable=False, index=True)
    deleted = Column(satypes.Boolean, nullable=False, index=True)

    url_obj: "RelationshipProperty[SQLAUrl]" = relationship(
        SQLAUrl, uselist=False, backref="bookmark_objs"
    )

    user_obj: "RelationshipProperty[SQLUser]" = relationship(
        "SQLUser", uselist=False, backref="bookmarks"
    )
    bookmark_tag_objs: "RelationshipProperty[List[BookmarkTag]]"


class CrawlRequest(Base):
    __tablename__ = "crawl_requests"

    crawl_uuid = Column(PGUUID, primary_key=True)
    # FIXME: url_uuid should be NOT NULL
    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), index=True)
    requested = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    # FIXME: should default to false
    got_response = Column(satypes.Boolean, index=True)

    url_obj: "RelationshipProperty[SQLAUrl]" = relationship(
        SQLAUrl, uselist=False, backref="crawl_reqs"
    )


class CrawlResponse(Base):
    __tablename__ = "crawl_responses"

    crawl_uuid = Column(
        PGUUID, ForeignKey("crawl_requests.crawl_uuid"), primary_key=True
    )
    body_uuid = Column(PGUUID, unique=True, nullable=False)
    headers = Column(JSONB(), nullable=False, index=False)
    status_code = Column(satypes.SmallInteger, nullable=False, index=True)

    request_obj: "RelationshipProperty[CrawlRequest]" = relationship(
        CrawlRequest, uselist=False, backref=backref("response_obj", uselist=False),
    )


class FullText(Base):
    __tablename__ = "full_text"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True)
    crawl_uuid = Column(
        PGUUID, ForeignKey("crawl_requests.crawl_uuid"), nullable=False, index=True,
    )
    inserted = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    full_text = Column(satypes.String(), nullable=False)
    tsvector = Column(TSVECTOR, nullable=False)

    # __table_args__ = (Index("abc", "tsvector", postgresql_using="gin"),)

    crawl_req: "RelationshipProperty[CrawlRequest]" = relationship(
        CrawlRequest, uselist=False, backref="full_text_obj"
    )

    url_obj: "RelationshipProperty[SQLAUrl]" = relationship(
        SQLAUrl, uselist=False, backref="full_text_obj"
    )


class IndexingError(Base):
    __tablename__ = "index_errors"

    crawl_uuid = Column(
        PGUUID, ForeignKey("crawl_requests.crawl_uuid"), primary_key=True
    )
    description = Column(satypes.String, nullable=False)


class SQLUser(Base):
    __tablename__ = "users"
    __tableargs__ = (CheckConstraint("username ~ '^[-A-z0-9]+$'"),)

    user_uuid = Column(PGUUID, primary_key=True)
    username = Column(
        satypes.String(length=200), nullable=False, unique=True, index=True
    )
    password = Column(satypes.String, nullable=False)
    timezone = Column(satypes.String, nullable=False)
    registered = Column(satypes.DateTime(timezone=True), nullable=False)

    email_obj: "RelationshipProperty[UserEmail]" = relationship(
        "UserEmail", uselist=False, backref="user"
    )

    api_key_obj: "RelationshipProperty[APIKey]" = relationship(
        "APIKey", uselist=False, backref="user"
    )


class UserEmail(Base):
    __tablename__ = "user_emails"

    user_uuid = Column(PGUUID, ForeignKey("users.user_uuid"), primary_key=True)
    email_address = Column(satypes.String(length=200), nullable=False, index=True)


class APIKey(Base):
    __tablename__ = "api_keys"

    user_uuid = Column(PGUUID, ForeignKey("users.user_uuid"), primary_key=True)
    api_key = Column(BYTEA(length=16), nullable=False, unique=True, index=True)


class BookmarkTag(Base):
    __tablename__ = "bookmark_tags"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, index=True)
    user_uuid = Column(
        PGUUID, ForeignKey("users.user_uuid"), primary_key=True, index=True
    )
    tag_id = Column(
        satypes.Integer, ForeignKey("tags.tag_id"), primary_key=True, index=True
    )
    updated = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    deleted = Column(satypes.Boolean, nullable=False, index=True)

    tag_obj: "RelationshipProperty[Tag]" = relationship(
        "Tag", uselist=False, backref="bookmark_tag_objs"
    )

    bookmark_obj: "RelationshipProperty[SQLABookmark]" = relationship(
        SQLABookmark,
        primaryjoin=and_(
            foreign(url_uuid) == remote(SQLABookmark.url_uuid),
            foreign(user_uuid) == remote(SQLABookmark.user_uuid),
        ),
        backref="bookmark_tag_objs",
        uselist=False,
    )


class Tag(Base):
    __tablename__ = "tags"
    __tableargs__ = (CheckConstraint("tag_name ~ '^[-a-z0-9]+$'"),)

    # Presumably 4bn tags is enough
    tag_id = Column(satypes.Integer, primary_key=True, autoincrement=True)
    tag_name = Column(
        satypes.String(length=40), nullable=False, index=True, unique=True
    )

    bookmarks_objs: "RelationshipProperty[SQLABookmark]" = relationship(
        SQLABookmark,
        backref="tag_objs",
        secondary=BookmarkTag.__table__,
        primaryjoin=tag_id == BookmarkTag.tag_id,
        secondaryjoin=and_(
            foreign(BookmarkTag.__table__.c.url_uuid) == remote(SQLABookmark.url_uuid),
            foreign(BookmarkTag.__table__.c.user_uuid)
            == remote(SQLABookmark.user_uuid),
        ),
    )


class DomainIcon(Base):
    """Records raditional "favicons" served from http://{url}/favicon.ico."""

    __tablename__ = "domain_icons"

    scheme = Column(satypes.String, nullable=False, primary_key=True)
    netloc = Column(satypes.String, nullable=False, primary_key=True)
    icon_uuid = Column(
        PGUUID, ForeignKey("icons.icon_uuid"), nullable=False, index=True
    )

    icon: "RelationshipProperty[Icon]" = relationship("Icon", backref="domains")


class URLIcon(Base):
    """Records favicons referred to by <link rel="..."> HTML"""

    __tablename__ = "url_icons"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True)
    icon_uuid = Column(
        PGUUID, ForeignKey("icons.icon_uuid"), nullable=False, index=True
    )

    icon: "RelationshipProperty[Icon]" = relationship("Icon", backref="urls")


class IconSource(Base):
    """Records urls where we found an icon.  Used for deduplication"""

    __tablename__ = "icon_sources"

    icon_uuid = Column(PGUUID, ForeignKey("icons.icon_uuid"), primary_key=True)
    url_uuid = Column(
        PGUUID, ForeignKey("urls.url_uuid"), primary_key=True, unique=True
    )

    icon: "RelationshipProperty[Icon]" = relationship(
        "Icon", backref="icon_sources", uselist=False
    )


class Icon(Base):
    """An icon we have retrived, scaled and stored in our S3-compatible
    store."""

    __tablename__ = "icons"

    # This is a key into our S3 bucket
    icon_uuid = Column(PGUUID, primary_key=True)

    # BLAKE2b hash to help deduplicate the same icon file served from different
    # locations
    source_blake2b_hash = Column(BYTEA(length=64), nullable=False, unique=True)


class SQLShareGrant(Base):
    __tablename__ = "share_grants"

    access_object_id = Column(
        satypes.BigInteger,
        ForeignKey("access_objects.access_object_id"),
        nullable=False,
    )
    access_verb_id = Column(
        satypes.SmallInteger, ForeignKey("access_verbs.access_verb_id"), nullable=False
    )
    revoked = Column(satypes.Boolean, nullable=False, index=True)
    share_token = Column(BYTEA(), nullable=False, primary_key=True)


class SQLAccessObject(Base):
    __tablename__ = "access_objects"
    __table_args__ = (UniqueConstraint("access_object_name", "params"),)

    access_object_id = Column(satypes.BigInteger, primary_key=True, autoincrement=True)
    access_object_name = Column(satypes.String, nullable=False)
    params = Column(JSONB(), nullable=False)


class SQLAccessVerb(Base):
    __tablename__ = "access_verbs"

    access_verb_id = Column(satypes.SmallInteger, primary_key=True, autoincrement=False)
    access_verb_name = Column(satypes.String, unique=True, nullable=False)


class SQLDiscussion(Base):
    __tablename__ = "discussions"

    external_discussion_id = Column(satypes.String, primary_key=True)
    discussion_source_id = Column(
        satypes.SmallInteger,
        ForeignKey("discussion_sources.discussion_source_id"),
        primary_key=True,
    )
    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), index=True, nullable=False)
    comment_count = Column(satypes.Integer, nullable=False)
    created_at = Column(satypes.DateTime(timezone=True), nullable=False)
    title = Column(satypes.String, nullable=False)


class SQLDiscussionSource(Base):
    __tablename__ = "discussion_sources"

    discussion_source_id = Column(
        satypes.SmallInteger, primary_key=True, autoincrement=False
    )
    discussion_source_name = Column(satypes.String, unique=True, nullable=False)


class SQLDiscussionFetch(Base):
    __tablename__ = "discussion_fetches"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True)
    discussion_source_id = Column(
        satypes.SmallInteger,
        ForeignKey("discussion_sources.discussion_source_id"),
        primary_key=True,
    )
    status_code = Column(satypes.SmallInteger, nullable=False, index=True)
    retrieved = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
