from uuid import UUID
from typing import (
    Dict,
    Mapping,
    Sequence,
    Set,
    FrozenSet,
    Any,
    Optional,
    Callable,
    Iterable,
    MutableSequence,
    cast,
    TypeVar,
    Tuple,
    BinaryIO,
    List,
    Union,
    TYPE_CHECKING,
)
from urllib.parse import urlunsplit

from sqlalchemy import (
    Column,
    ForeignKey,
    types as satypes,
    func,
    create_engine,
    and_,
    cast as sa_cast,
)
from sqlalchemy.orm import (
    foreign,
    remote,
    relationship,
    RelationshipProperty,
    Session,
    sessionmaker,
    scoped_session,
)
from sqlalchemy.dialects.postgresql import (
    UUID as _PGUUID,
    insert as pg_insert,
    BYTEA,
    JSONB,
    TSVECTOR,
    array as pg_array,
    ARRAY as PGARRAY,
)
from sqlalchemy.schema import CheckConstraint
from sqlalchemy.ext.declarative import declarative_base

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

    def to_url_string(self) -> str:
        return urlunsplit(
            [self.scheme, self.netloc, self.path, self.query, self.fragment]
        )


class SQLABookmark(Base):
    __tablename__ = "bookmarks"

    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), primary_key=True)
    user_uuid = Column(PGUUID, ForeignKey("users.user_uuid"), primary_key=True)

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
        CrawlRequest, uselist=False, backref="response_obj"
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


class SQLUser(Base):
    __tablename__ = "users"
    __tableargs__ = (CheckConstraint("username ~ '^[-A-z0-9]+$'"),)

    user_uuid = Column(PGUUID, primary_key=True)
    username = Column(
        satypes.String(length=200), nullable=False, unique=True, index=True
    )
    password = Column(satypes.String, nullable=False)

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
