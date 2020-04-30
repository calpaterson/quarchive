from dataclasses import dataclass, asdict as dataclass_as_dict
import re
import configparser
import contextlib
from datetime import datetime, timezone
import gzip
from functools import wraps, lru_cache
import itertools
import logging
import mimetypes
from uuid import uuid4, UUID, uuid5, NAMESPACE_URL as UUID_URL_NAMESPACE
from typing import (
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
from os import environ, path
from urllib.parse import urlsplit, urlunsplit
import json
import tempfile
import shutil
from abc import ABCMeta, abstractmethod
import cgi
import secrets

from passlib.context import CryptContext
import lxml
import lxml.html
import click
import boto3
from botocore.utils import fix_s3_host
import requests
from celery import Celery
from werkzeug import exceptions as exc
from werkzeug.urls import url_encode
from dateutil.parser import isoparse
from sqlalchemy import Column, ForeignKey, types as satypes, func, create_engine, and_
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
)

from sqlalchemy.ext.declarative import declarative_base
from flask_sqlalchemy import SQLAlchemy
import flask
from flask_cors import CORS
import missive
from missive.adapters.rabbitmq import RabbitMQAdapter
from flask_babel import Babel
import magic

# https://github.com/dropbox/sqlalchemy-stubs/issues/94
if TYPE_CHECKING:
    PGUUID = satypes.TypeEngine[UUID]
else:
    PGUUID = _PGUUID(as_uuid=True)

log = logging.getLogger("quarchive")

# fmt: off
# Config loading
...
# fmt: on

REQUIRED_CONFIG_KEYS = {
    "QM_SQL_URL",
    "QM_SECRET_KEY",
    "QM_RESPONSE_BODY_BUCKET_NAME",
    "QM_AWS_ACCESS_KEY",
    "QM_AWS_REGION_NAME",
    "QM_AWS_SECRET_ACCESS_KEY",
    "QM_AWS_S3_ENDPOINT_URL",
}


def load_config(env_ini: Optional[str] = None) -> None:
    if env_ini is not None:
        log.info("loading from %s", path.abspath(env_ini))
        parser = configparser.ConfigParser()
        # mypy confused by this unusual pattern
        # https://github.com/python/mypy/issues/708
        parser.optionxform = str  # type: ignore
        parser.read(env_ini)
        environ.update(parser["env"].items())
    else:
        log.warning("not loading env from any config file")

    if not REQUIRED_CONFIG_KEYS.issubset(set(environ.keys())):
        missing_keys = REQUIRED_CONFIG_KEYS.difference(set(environ.keys()))
        raise RuntimeError("incomplete configuration! missing keys: %s" % missing_keys)


# fmt: off
# Dataclasses
...
# fmt: on


@dataclass(frozen=True)
class URL:
    url_uuid: UUID

    scheme: str
    netloc: str
    path: str
    query: str
    fragment: str

    def to_url(self) -> str:
        return urlunsplit(
            (self.scheme, self.netloc, self.path, self.query, self.fragment)
        )

    @classmethod
    def from_sqla_url(cls, sql_url: "SQLAUrl") -> "URL":
        # sqlalchemy-stubs can't figure this out
        url_uuid = cast(UUID, sql_url.url_uuid)
        return cls(
            url_uuid=url_uuid,
            scheme=sql_url.scheme,
            netloc=sql_url.netloc,
            path=sql_url.path,
            query=sql_url.query,
            fragment=sql_url.fragment,
        )


TagTriple = Tuple[str, datetime, bool]
TagTriples = FrozenSet[TagTriple]


@dataclass(frozen=True)
class Bookmark:
    url: str

    title: str
    description: str

    created: datetime
    updated: datetime

    unread: bool
    deleted: bool

    tag_triples: TagTriples = frozenset()

    def tags(self) -> List[str]:
        return []

    def merge(self, other: "Bookmark") -> "Bookmark":
        more_recent: "Bookmark" = sorted(
            (self, other),
            # 1. Take the most recently updated.
            # 2. If they're equally recent, take the longer title
            # 3. If that's not enough add the longest description
            # 4. If that's not enough compare the titles
            # 5. If that's not enough compare the description
            # 6. Then compare everything else
            key=lambda b: (
                b.updated,
                len(b.title),
                len(b.description),
                b.title,
                b.description,
                b.unread,
                not b.deleted,
            ),
            reverse=True,
        )[0]
        # The strategy in short:
        # Take the fields from the most recently updated bookmark, EXCEPT:
        # created - for which take the oldest value
        # updated - for which take the latest value
        return Bookmark(
            url=self.url,
            created=min((self.created, other.created)),
            updated=max((self.updated, other.updated)),
            title=more_recent.title,
            description=more_recent.description,
            unread=more_recent.unread,
            deleted=more_recent.deleted,
            tag_triples=Bookmark.merge_tag_triples(self.tag_triples, other.tag_triples),
        )

    @staticmethod
    def tag_from_triple(triple: TagTriple) -> str:
        return triple[0]

    @staticmethod
    def tag_triple_order_key(triple: TagTriple) -> Tuple[datetime, bool]:
        return triple[1], not triple[2]

    @staticmethod
    def merge_tag_triples(triples_1: TagTriples, triples_2: TagTriples) -> TagTriples:
        result_set: Set[TagTriple] = set()
        for _, group_iter in itertools.groupby(
            sorted(itertools.chain(triples_1, triples_2), key=Bookmark.tag_from_triple),
            key=Bookmark.tag_from_triple,
        ):
            group = list(group_iter)
            merged = max(group, key=Bookmark.tag_triple_order_key)
            result_set.add(merged)
        return frozenset(result_set)

    # @staticmethod
    # def merge_pair_of_tag_triples(a: TagTriple, b: TagTriple) -> TagTriple:
    #     return max([a, b], key=lambda tt: tt[1])

    def to_json(self) -> Mapping:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "unread": self.unread,
            "deleted": self.deleted,
        }

    @classmethod
    def from_json(cls, mapping: Mapping[str, Any]) -> "Bookmark":
        try:
            updated = isoparse(mapping["updated"])
            created = isoparse(mapping["created"])
        except ValueError:
            log.error(
                "Got invalid datetime: [%s, %s] for %s",
                mapping["updated"],
                mapping["created"],
                mapping["url"],
            )
            raise
        return cls(
            url=mapping["url"],
            title=mapping["title"],
            description=mapping["description"],
            updated=isoparse(mapping["updated"]),
            created=isoparse(mapping["created"]),
            unread=mapping["unread"],
            deleted=mapping["deleted"],
        )


def bookmark_from_sqla(url: str, sqla_obj: "SQLABookmark") -> Bookmark:
    return Bookmark(
        url=url,
        created=sqla_obj.created,
        description=sqla_obj.description,
        updated=sqla_obj.updated,
        unread=sqla_obj.unread,
        deleted=sqla_obj.deleted,
        title=sqla_obj.title,
    )


@dataclass
class User:
    user_uuid: UUID
    username: str
    email: Optional[str]


# fmt: off
# DB layer
...
# fmt: on

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

    url_obj: RelationshipProperty = relationship(
        SQLAUrl, uselist=False, backref="bookmark_objs"
    )

    user_obj: RelationshipProperty = relationship(
        "SQLUser", uselist=False, backref="bookmarks"
    )


class CrawlRequest(Base):
    __tablename__ = "crawl_requests"

    crawl_uuid = Column(PGUUID, primary_key=True)
    # FIXME: url_uuid should be NOT NULL
    url_uuid = Column(PGUUID, ForeignKey("urls.url_uuid"), index=True)
    requested = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    got_response = Column(satypes.Boolean, index=True)

    url_obj: RelationshipProperty = relationship(
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

    request_obj: RelationshipProperty = relationship(
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

    crawl_req: RelationshipProperty = relationship(
        CrawlRequest, uselist=False, backref="full_text_obj"
    )

    url_obj: RelationshipProperty = relationship(
        SQLAUrl, uselist=False, backref="full_text_obj"
    )


class SQLUser(Base):
    __tablename__ = "users"

    user_uuid = Column(PGUUID, primary_key=True)
    username = Column(
        satypes.String(length=200), nullable=False, unique=True, index=True
    )
    password = Column(satypes.String, nullable=False)

    email_obj: RelationshipProperty = relationship(
        "UserEmail", uselist=False, backref="user"
    )

    api_key_obj: RelationshipProperty = relationship(
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


class Tag(Base):
    __tablename__ = "tags"

    # Presumably 4bn tags is enough
    tag_id = Column(satypes.Integer, primary_key=True, autoincrement=True)
    tag_name = Column(
        satypes.String(length=40), nullable=False, index=True, unique=True
    )

    bookmarks_objs: RelationshipProperty = relationship(
        SQLABookmark,
        backref="tags_objs",
        secondary=BookmarkTag.__table__,
        primaryjoin=tag_id == BookmarkTag.tag_id,
        secondaryjoin=and_(
            foreign(BookmarkTag.__table__.c.url_uuid) == remote(SQLABookmark.url_uuid),
            foreign(BookmarkTag.__table__.c.user_uuid)
            == remote(SQLABookmark.user_uuid),
        ),
    )


def is_correct_api_key(session: Session, username: str, api_key: bytes) -> bool:
    api_key_from_db = get_api_key(session, username)
    return secrets.compare_digest(api_key, api_key_from_db)


def get_api_key(session, username: str) -> bytes:
    return (
        session.query(APIKey.api_key)
        .join(SQLUser)
        .filter(SQLUser.username == username)
        .scalar()
    )


def username_exists(session: Session, username: str) -> bool:
    return session.query(
        session.query(SQLUser).filter(SQLUser.username == username).exists()
    ).scalar()


def user_from_username(session, username: str) -> User:
    user_uuid, email = (
        session.query(SQLUser.user_uuid, UserEmail.email_address)
        .outerjoin(UserEmail)
        .filter(SQLUser.username == username)
        .one()
    )
    return User(user_uuid=user_uuid, username=username, email=email,)


def user_from_user_uuid(session, user_uuid: UUID) -> User:
    username, email = (
        session.query(SQLUser.username, UserEmail.email_address)
        .outerjoin(UserEmail)
        .filter(SQLUser.user_uuid == user_uuid)
        .one()
    )
    return User(user_uuid=user_uuid, username=username, email=email,)


def create_user(
    session: Session,
    crypt_context: Any,
    username: str,
    password_plain: str,
    email: Optional[str] = None,
) -> UUID:
    user_uuid = uuid4()
    password_hashed = crypt_context.hash(password_plain)
    sql_user = SQLUser(user_uuid=user_uuid, username=username, password=password_hashed)

    if email is not None:
        log.info("got an email for %s", username)
        sql_user.email_obj = UserEmail(email_address=email)

    sql_user.api_key_obj = APIKey(api_key=secrets.token_bytes(32))

    session.add(sql_user)
    return user_uuid


def get_bookmark_by_url(
    session: Session, user_uuid: UUID, url: str
) -> Optional[Bookmark]:
    scheme, netloc, path, query, fragment = urlsplit(url)
    sqla_bookmark = (
        session.query(SQLABookmark)
        .join(SQLAUrl)
        .filter(
            SQLAUrl.scheme == scheme,
            SQLAUrl.netloc == netloc,
            SQLAUrl.path == path,
            SQLAUrl.query == query,
            SQLAUrl.fragment == fragment,
            SQLABookmark.user_uuid == user_uuid,
        )
        .first()
    )
    if sqla_bookmark is None:
        return None
    else:
        return bookmark_from_sqla(url, sqla_bookmark)


def get_bookmark_by_url_uuid(
    session: Session, user_uuid: UUID, url_uuid: UUID
) -> Optional[Bookmark]:
    sqla_bookmark = (
        session.query(SQLABookmark)
        .filter(SQLABookmark.user_uuid == user_uuid, SQLABookmark.url_uuid == url_uuid)
        .first()
    )
    if sqla_bookmark is None:
        return None
    url = URL.from_sqla_url(sqla_bookmark.url_obj).to_url()
    return bookmark_from_sqla(url, sqla_bookmark)


def create_url_uuid(url: str) -> UUID:
    # Use uuid5's namespace system to make url uuid deterministic
    return uuid5(UUID_URL_NAMESPACE, url)


def upsert_url(session: Session, url: str) -> UUID:
    scheme, netloc, path, query, fragment = urlsplit(url)
    proposed_uuid = create_url_uuid(url)
    url_stmt = (
        pg_insert(SQLAUrl.__table__)
        .values(
            url_uuid=proposed_uuid,
            scheme=scheme,
            netloc=netloc,
            path=path,
            query=query,
            fragment=fragment,
        )
        .on_conflict_do_nothing(
            index_elements=["scheme", "netloc", "path", "query", "fragment"]
        )
        .returning(SQLAUrl.__table__.c.url_uuid)
    )
    upsert_result_set = session.execute(url_stmt).fetchone()

    url_uuid: UUID
    if upsert_result_set is None:
        # The update didn't happen, but we still need to know what the url uuid
        # is...
        (url_uuid,) = (
            session.query(SQLAUrl.url_uuid)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .one()
        )
    else:
        # If the update did happen, we know our proposed uuid was used
        url_uuid = proposed_uuid
    return url_uuid


def set_bookmark(session: Session, user_uuid: UUID, bookmark: Bookmark) -> UUID:
    scheme, netloc, path, query, fragment = urlsplit(bookmark.url)
    proposed_uuid = create_url_uuid(bookmark.url)
    url_stmt = (
        pg_insert(SQLAUrl.__table__)
        .values(
            url_uuid=proposed_uuid,
            scheme=scheme,
            netloc=netloc,
            path=path,
            query=query,
            fragment=fragment,
        )
        .on_conflict_do_nothing(
            index_elements=["scheme", "netloc", "path", "query", "fragment"]
        )
        .returning(SQLAUrl.__table__.c.url_uuid)
    )
    upsert_result_set = session.execute(url_stmt).fetchone()

    url_uuid: UUID
    if upsert_result_set is None:
        # The update didn't happen, but we still need to know what the url uuid
        # is...
        (url_uuid,) = (
            session.query(SQLAUrl.url_uuid)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .one()
        )
    else:
        # If the update did happen, we know our proposed uuid was used
        url_uuid = proposed_uuid

    bookmark_insert_stmt = pg_insert(SQLABookmark.__table__).values(
        created=bookmark.created.replace(tzinfo=timezone.utc),
        deleted=bookmark.deleted,
        description=bookmark.description,
        title=bookmark.title,
        unread=bookmark.unread,
        updated=bookmark.updated.replace(tzinfo=timezone.utc),
        url_uuid=url_uuid,
        user_uuid=user_uuid,
    )
    bookmark_upsert_stmt = bookmark_insert_stmt.on_conflict_do_update(
        index_elements=["url_uuid", "user_uuid"],
        set_=dict(
            created=bookmark_insert_stmt.excluded.created,
            deleted=bookmark_insert_stmt.excluded.deleted,
            description=bookmark_insert_stmt.excluded.description,
            title=bookmark_insert_stmt.excluded.title,
            unread=bookmark_insert_stmt.excluded.unread,
            updated=bookmark_insert_stmt.excluded.updated,
        ),
    )
    session.execute(bookmark_upsert_stmt)
    return url_uuid


def merge_bookmarks(
    session: Session, user_uuid: UUID, recieved_bookmarks: Iterable[Bookmark]
) -> Set[Bookmark]:
    changed_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(session, user_uuid, url=recieved.url)
        if existing is None:
            # If it doesn't exist in our db, we create it - but client already
            # knows
            set_bookmark(session, user_uuid, recieved)
            log.debug("added: %s", recieved)
        else:
            merged = existing.merge(recieved)
            if merged != existing:
                # If it exists but is old we have to update it
                log.debug(
                    "recieved bm merged, changing local: %s + %s = %s",
                    recieved,
                    existing,
                    merged,
                )
                set_bookmark(session, user_uuid, merged)
            else:
                log.debug("no change to %s", recieved)
            if merged != recieved:
                # If what we have is different from what were sent, we need to
                # tell the client
                changed_bookmarks.add(merged)
    return changed_bookmarks


def all_bookmarks(session, user_uuid: UUID) -> Iterable[Bookmark]:
    query = session.query(SQLABookmark).filter(SQLABookmark.user_uuid == user_uuid)
    for sqla_bookmark in query:
        url_obj = sqla_bookmark.url_obj
        url = urlunsplit(
            [
                url_obj.scheme,
                url_obj.netloc,
                url_obj.path,
                url_obj.query,
                url_obj.fragment,
            ]
        )
        yield bookmark_from_sqla(url, sqla_bookmark)


# fmt: off
# # Web layer
...
# fmt: on

db = SQLAlchemy()
cors = CORS()
blueprint = flask.Blueprint("quarchive", "quarchive")


# Flask's "views" are quite variable
V = TypeVar("V", bound=Callable)


def get_current_user() -> User:
    """Utility function to get the current user.

    The only purpose of this is for typing - flask.g.user is unavoidably Any
    whereas the return type of this is User.

    """
    return flask.g.user


@blueprint.before_request
def put_user_in_g() -> None:
    user_uuid: Optional[UUID] = flask.session.get("user_uuid")
    if user_uuid is not None:
        flask.g.user = user_from_user_uuid(db.session, user_uuid)
        flask.current_app.logger.debug("currently signed in as: %s", flask.g.user)
    else:
        flask.current_app.logger.debug("not signed in")


@blueprint.before_app_first_request
def log_db() -> None:
    flask.current_app.logger.info("using engine: %s", db.session.bind)


def sign_in_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if flask.g.get("user", None) is None:
            # FIXME: This should use redirect_to
            return flask.redirect("/sign-in"), 302
        else:
            return handler(*args, **kwargs)

    return cast(V, wrapper)


def observe_redirect_to(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        response = handler(*args, **kwargs)
        if response.status_code == 200 and "redirect_to" in flask.request.args:
            redirection = flask.make_response("redirecting",)
            redirection.headers["Location"] = flask.request.args["redirect_to"]
            return redirection, 303
        else:
            return response

    return cast(V, wrapper)


def api_key_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            username = flask.request.headers["X-QM-API-Username"]
            api_key_str = flask.request.headers["X-QM-API-Key"]
        except KeyError:
            flask.current_app.logger.info("no api credentials")
            return flask.jsonify({"error": "no api credentials"}), 400

        if is_correct_api_key(db.session, username, bytes.fromhex(api_key_str)):
            flask.g.user = user_from_username(db.session, username)
            return handler()
        else:
            flask.current_app.logger.info("bad api credentials")
            return flask.jsonify({"error": "bad api credentials"}), 400

    return cast(V, wrapper)


@blueprint.route("/")
@sign_in_required
def index() -> Tuple[flask.Response, int]:
    page_size = flask.current_app.config["PAGE_SIZE"]
    page = int(flask.request.args.get("page", "1"))
    offset = (page - 1) * page_size
    user = get_current_user()
    query = db.session.query(SQLABookmark).filter(
        SQLABookmark.user_uuid == user.user_uuid
    )

    if "q" in flask.request.args:
        query = query.outerjoin(FullText, FullText.url_uuid == SQLABookmark.url_uuid)

        search_str = flask.request.args["q"]
        tquery_str = parse_search_str(search_str)
        log.debug('search_str, tquery_str = ("%s", "%s")', search_str, tquery_str)

        # necessary to coalesce this as there may be no fulltext
        fulltext = func.coalesce(FullText.tsvector, func.to_tsvector(""))

        combined_tsvector = (
            func.to_tsvector(SQLABookmark.title)
            .op("||")(func.to_tsvector(SQLABookmark.description))
            .op("||")(fulltext)
        )
        tsquery = func.to_tsquery(tquery_str)
        query = query.filter(combined_tsvector.op("@@")(tsquery))
        query = query.order_by(func.ts_rank(combined_tsvector, tsquery, 1))
        page_title = search_str
    else:
        page_title = "Quarchive"

    if page > 1:
        page_title += " (page %s)" % page

    # omit deleted bookmarks
    query = query.filter(~SQLABookmark.deleted)

    sqla_objs = (
        query.order_by(SQLABookmark.created.desc()).offset(offset).limit(page_size)
    )

    prev_page_exists = page > 1
    next_page_exists: bool = db.session.query(
        query.order_by(SQLABookmark.created.desc()).offset(offset + page_size).exists()
    ).scalar()

    bookmarks = []
    for sqla_obj in sqla_objs:
        url = URL.from_sqla_url(sqla_obj.url_obj)
        bookmarks.append((url, bookmark_from_sqla(url.to_url(), sqla_obj)))
    return flask.make_response(
        flask.render_template(
            "index.html",
            page_title=page_title,
            bookmarks=bookmarks,
            page=page,
            prev_page_exists=prev_page_exists,
            next_page_exists=next_page_exists,
            q=flask.request.args.get("q"),
        )
    )


@blueprint.route("/create-bookmark")
@sign_in_required
def create_bookmark_form() -> flask.Response:
    return flask.make_response(
        flask.render_template(
            "create_or_edit_bookmark.html", page_title="Create bookmark",
        )
    )


@blueprint.route("/about")
def about() -> flask.Response:
    return flask.make_response(
        flask.render_template("about.html", page_title="About Quarchive",)
    )


@blueprint.route("/bookmark", methods=["POST"])
@sign_in_required
def create_bookmark() -> flask.Response:
    form = flask.request.form
    creation_time = datetime.utcnow().replace(tzinfo=timezone.utc)
    bookmark = Bookmark(
        url=form["url"],
        title=form["title"],
        description=form["description"],
        unread="unread" in form,
        deleted=False,
        updated=creation_time,
        created=creation_time,
    )
    url_uuid = set_bookmark(db.session, get_current_user().user_uuid, bookmark)
    db.session.commit()
    flask.flash("Bookmarked: %s" % bookmark.title)
    response = flask.make_response("Redirecting...", 303)
    response.headers["Location"] = flask.url_for(
        "quarchive.edit_bookmark", url_uuid=url_uuid
    )
    return response


@blueprint.route("/bookmark/<uuid:url_uuid>", methods=["GET", "POST"])
@sign_in_required
@observe_redirect_to
def edit_bookmark(url_uuid: UUID) -> flask.Response:
    if flask.request.method == "GET":
        bookmark = get_bookmark_by_url_uuid(
            db.session, get_current_user().user_uuid, url_uuid
        )
        # FIXME: what if it doesn't exist?
        return flask.make_response(
            flask.render_template(
                "create_or_edit_bookmark.html",
                url_uuid=url_uuid,
                bookmark=bookmark,
                page_title="Edit bookmark: %s" % bookmark.url,  # type: ignore
            )
        )
    else:
        form = flask.request.form
        fields = set(["title", "description", "unread", "deleted"])
        bookmark = get_bookmark_by_url_uuid(
            db.session, get_current_user().user_uuid, url_uuid
        )
        if bookmark is None:
            raise exc.NotFound()
        bookmark_fields = dataclass_as_dict(bookmark)
        bookmark_fields["title"] = form["title"]
        bookmark_fields["description"] = form["description"]
        bookmark_fields["unread"] = "unread" in form
        bookmark_fields["deleted"] = "deleted" in form
        bookmark_fields["updated"] = datetime.utcnow().replace(tzinfo=timezone.utc)
        final_bookmark = Bookmark(**bookmark_fields)
        set_bookmark(db.session, get_current_user().user_uuid, final_bookmark)
        db.session.commit()
        flask.flash("Edited: %s" % bookmark.title)
        return flask.make_response("ok")


@blueprint.route("/url/<uuid:url_uuid>")
@sign_in_required
def view_url(url_uuid: UUID) -> Tuple[flask.Response, int]:
    sqla_obj = db.session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url_uuid).first()
    if sqla_obj is None:
        raise exc.NotFound()
    else:
        url_obj = URL.from_sqla_url(sqla_obj)
        return flask.make_response(
            flask.render_template(
                "url.html", url=url_obj, page_title="View: %s" % url_obj.to_url()
            )
        )


@blueprint.route("/netloc/<string:netloc>")
@sign_in_required
def view_netloc(netloc: str) -> Tuple[flask.Response, int]:
    url_objs = db.session.query(SQLAUrl).filter(SQLAUrl.netloc == netloc)
    if url_objs.count() == 0:
        raise exc.NotFound()
    else:
        return flask.make_response(
            flask.render_template(
                "netloc.html",
                netloc=netloc,
                url_objs=url_objs,
                page_title="Netloc: %s" % netloc,
            )
        )


@blueprint.route("/register", methods=["GET", "POST"])
def register() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("register.html", page_title="Register")
        )
    else:
        username = flask.request.form["username"]
        password_plain = flask.request.form["password"]
        email: Optional[str] = flask.request.form["email"] or None

        if username_exists(db.session, username):
            log.error("username already registered: %s", username)
            flask.abort(400, description="username already exists")

        username_regex = r"^[A-z0-9_\-]+$"
        if not re.compile(username_regex).match(username):
            log.error("invalid username: %s", username)
            flask.abort(
                400, description="invalid username - must match %s" % username_regex
            )

        user_uuid = create_user(
            db.session,
            flask.current_app.config["CRYPT_CONTEXT"],
            username,
            password_plain,
            email,
        )

        db.session.commit()
        response = flask.make_response("Redirecting...", 303)
        response.headers["Location"] = flask.url_for("quarchive.index")
        log.info("created user: %s", username)
        flask.session["user_uuid"] = user_uuid
        return response


@blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(
            flask.render_template("sign-in.html", page_title="Sign in")
        )
    else:
        crypt_context = flask.current_app.config["CRYPT_CONTEXT"]

        username = flask.request.form.get("username")
        user = db.session.query(SQLUser).filter(SQLUser.username == username).first()

        if user is None:
            flask.current_app.logger.info(
                "unsuccessful sign in - no such user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")

        password = flask.request.form.get("password")
        is_correct_password: bool = crypt_context.verify(password, user.password)
        if is_correct_password:
            flask.current_app.logger.info("successful sign in")
            flask.session["user_uuid"] = user.user_uuid

            # Make it last for 31 days
            flask.session.permanent = True
            flask.flash("Signed in")

            response = flask.make_response("Redirecting...", 303)
            response.headers["Location"] = "/"
            return response
        else:
            flask.current_app.logger.info(
                "unsuccessful sign in - wrong password for user: %s", username
            )
            raise exc.BadRequest("unsuccessful sign in")


@blueprint.route("/sign-out", methods=["GET"])
def sign_out() -> flask.Response:
    flask.session.clear()
    flask.flash("Signed out")
    return flask.make_response(flask.render_template("base.html"))


@blueprint.route("/user/<username>")
def user_page(username: str) -> flask.Response:
    user = user_from_username(db.session, username)
    api_key: Optional[bytes]
    if user == flask.g.user:
        api_key = get_api_key(db.session, user.username)
    else:
        api_key = None
    return flask.make_response(
        flask.render_template("user.html", user=user, api_key=api_key,)
    )


@blueprint.route("/ok")
def ok() -> flask.Response:
    return flask.json.jsonify({"ok": True})


@blueprint.route("/sync", methods=["POST"])
@api_key_required
def sync() -> flask.Response:
    use_jsonlines = flask.request.headers["Content-Type"] != "application/json"

    if not use_jsonlines:
        log.warning("sync request using deprecated single json object")
        body = flask.request.json
        recieved_bookmarks = set(Bookmark.from_json(item) for item in body["bookmarks"])
    else:
        log.info("sync request using jsonlines")
        recieved_bookmarks = set(
            Bookmark.from_json(json.loads(l)) for l in flask.request.stream.readlines()
        )

    changed_bookmarks = merge_bookmarks(
        db.session, get_current_user().user_uuid, recieved_bookmarks
    )
    db.session.commit()
    if "full" in flask.request.args:
        response_bookmarks = all_bookmarks(db.session, get_current_user().user_uuid)
    else:
        response_bookmarks = changed_bookmarks

    # If we got JSON, send json back
    if not use_jsonlines:
        return flask.json.jsonify(
            {"bookmarks": [b.to_json() for b in response_bookmarks]}
        )
    else:

        def generator():
            for b in response_bookmarks:
                yield json.dumps(b.to_json())
                yield "\n"

        return flask.Response(generator(), mimetype="application/x-ndjson",)


def init_app() -> flask.Flask:
    load_config(env_ini=environ.get("QM_ENV_INI", None))
    app = flask.Flask("quarchive")
    app.config["SECRET_KEY"] = environ["QM_SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"] = environ["QM_SQL_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["CRYPT_CONTEXT"] = CryptContext(["bcrypt"])
    log.info("setting sql url to: %s", environ["QM_SQL_URL"])

    # By default Postgres will consult the locale to decide what timezone to
    # return datetimes in.  We want UTC in all cases.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"options": "-c timezone=utc"}
    }

    app.config["PAGE_SIZE"] = 30
    db.init_app(app)
    cors.init_app(app)
    Babel(app, default_locale="en_GB", default_timezone="Europe/London")
    app.register_blueprint(blueprint)

    @app.context_processor
    def context_processor():
        return {"urlunsplit": urlunsplit}

    @app.template_global(name="modify_query")
    def modify_query(**new_args):
        args = flask.request.args.copy()

        for key, value in new_args.items():
            if value is not None:
                args[key] = value
            else:
                # None is a request to unset
                del args[key]

        return "?%s" % url_encode(args)

    return app


# fmt: off
# Crawling / background tasks
...
# fmt: on

celery_app = Celery("quarchive")

processor: missive.Processor[missive.JSONMessage] = missive.Processor()


@processor.handle_for([lambda m: m.get_json()["event_type"] == "test"])
def test_message(message, ctx):
    log.info("test message recieved")
    ctx.ack(message)


adapted_processor = RabbitMQAdapter(missive.JSONMessage, processor, "quarchive-events")


@lru_cache(1)
def get_session_cls() -> Session:
    url: str = environ["QM_SQL_URL"]
    engine = create_engine(url)
    session_factory = sessionmaker(bind=engine)
    Session = scoped_session(session_factory)
    log.info("using engine: %s", engine)
    return Session


REQUESTS_TIMEOUT = 30


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


@lru_cache(1)
def get_s3():
    session = boto3.Session(
        aws_access_key_id=environ["QM_AWS_ACCESS_KEY"],
        aws_secret_access_key=environ["QM_AWS_SECRET_ACCESS_KEY"],
        region_name=environ["QM_AWS_REGION_NAME"],
    )

    # This is a magic value to facilitate testing
    resource_kwargs = {}
    if environ["QM_AWS_S3_ENDPOINT_URL"] != "UNSET":
        resource_kwargs["endpoint_url"] = environ["QM_AWS_S3_ENDPOINT_URL"]

    resource = session.resource("s3", **resource_kwargs)
    resource.meta.client.meta.events.unregister("before-sign.s3", fix_s3_host)
    log.info("constructed s3 resource")
    return resource


@lru_cache(1)
def get_response_body_bucket():
    bucket = get_s3().Bucket(environ["QM_RESPONSE_BODY_BUCKET_NAME"])
    log.info("constructed response body bucket")
    return bucket


@celery_app.task
def celery_ok():
    log.info("ok")


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # FIXME: add periodic tasks here
    pass


def enqueue_crawls_for_uncrawled_urls():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(
                SQLAUrl.scheme,
                SQLAUrl.netloc,
                SQLAUrl.path,
                SQLAUrl.query,
                SQLAUrl.fragment,
            )
            .join(SQLABookmark)
            .outerjoin(CrawlRequest, SQLAUrl.url_uuid == CrawlRequest.url_uuid)
            .filter(CrawlRequest.crawl_uuid.is_(None))
        )
        uncrawled_urls = (urlunsplit(tup) for tup in rs)
    index = 0
    for index, uncrawled_url in enumerate(uncrawled_urls, start=1):
        log.info("enqueuing %s for crawl", uncrawled_url)
        ensure_crawled.delay(uncrawled_url)
    log.info("enqueued %d urls", index)


def enqueue_fulltext_indexing():
    with contextlib.closing(get_session_cls()) as sesh:
        rs = (
            sesh.query(CrawlResponse.crawl_uuid)
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .filter(FullText.crawl_uuid.is_(None))
        )
        for index, (crawl_uuid,) in enumerate(rs, start=1):
            log.info("enqueuing %s for crawl", crawl_uuid)
            ensure_fulltext.delay(crawl_uuid)
    log.info("enqueued %d items", index)


def get_meta_descriptions(root: lxml.html.HtmlElement) -> List[str]:
    meta_description_elements = root.xpath("//meta[@name='description']")
    if len(meta_description_elements) == 0:
        return []
    else:
        return [e.attrib.get("content", "") for e in meta_description_elements]


def extract_full_text_from_html(filelike: Union[BinaryIO, gzip.GzipFile]) -> str:
    # union required as gzip.GzipFile doesn't implement the full API required
    # by BinaryIO - we only need the shared subset
    document = lxml.html.parse(filelike)
    root = document.getroot()
    meta_descs = get_meta_descriptions(root)
    text_content: str = root.text_content()
    return " ".join(meta_descs + [text_content])


def upload_file(bucket, filelike: BinaryIO, filename: str) -> None:
    """Upload a fileobj into the bucket (compressed)"""
    with tempfile.TemporaryFile(mode="w+b") as temp_file:
        gzip_fileobj = gzip.GzipFile(mode="w+b", fileobj=temp_file)
        shutil.copyfileobj(filelike, gzip_fileobj)
        gzip_fileobj.close()
        temp_file.seek(0)
        bucket.upload_fileobj(temp_file, Key=filename)


def download_file(bucket, filename: str) -> gzip.GzipFile:
    """Download a fileobj from a bucket (decompressed)"""
    temp_file = tempfile.TemporaryFile(mode="w+b")
    bucket.download_fileobj(filename, temp_file)
    temp_file.seek(0)
    gzip_fileobj = gzip.GzipFile(mode="r+b", fileobj=temp_file)
    return gzip_fileobj


@lru_cache(1)
def known_content_types() -> FrozenSet[str]:
    mimetypes.init()
    return frozenset(mimetypes.types_map.values())


@celery_app.task
def ensure_crawled(url: str) -> None:
    """Crawl a url only if it has never been crawled before.

    For use from celery beat"""
    scheme, netloc, path, query, fragment = urlsplit(url)
    with contextlib.closing(get_session_cls()) as sesh:
        is_crawled: bool = sesh.query(
            sesh.query(CrawlRequest)
            .join(SQLAUrl)
            .filter(
                SQLAUrl.scheme == scheme,
                SQLAUrl.netloc == netloc,
                SQLAUrl.path == path,
                SQLAUrl.query == query,
                SQLAUrl.fragment == fragment,
            )
            .exists()
        ).scalar()
        if not is_crawled:
            crawl_uuid = uuid4()
            crawl_url(sesh, crawl_uuid, url)


def infer_content_type(fileobj: Union[BinaryIO, gzip.GzipFile]) -> str:
    """Use libmagic to infer the content type of a file from the first 2k."""
    content_type = magic.from_buffer(fileobj.read(2048), mime=True)
    fileobj.seek(0)
    return content_type


@celery_app.task
def ensure_fulltext(crawl_uuid: UUID) -> None:
    """Populate full text table for crawl"""
    with contextlib.closing(get_session_cls()) as sesh:
        content_type_header: Optional[str]
        body_uuid, content_type_header, sqla_url_obj, inserted = (
            sesh.query(
                CrawlResponse.body_uuid,
                CrawlResponse.headers["content-type"],
                SQLAUrl,
                FullText.inserted,
            )
            .outerjoin(FullText, CrawlResponse.crawl_uuid == FullText.crawl_uuid)
            .join(CrawlRequest, CrawlResponse.crawl_uuid == CrawlRequest.crawl_uuid)
            .join(SQLAUrl, CrawlRequest.url_uuid == SQLAUrl.url_uuid)
            .filter(CrawlResponse.crawl_uuid == crawl_uuid)
            .one()
        )

        url = URL.from_sqla_url(sqla_url_obj)

        if inserted is not None:
            log.info(
                "%s (%s) already indexed - not indexing again", url.to_url(), crawl_uuid
            )
            return

        bucket = get_response_body_bucket()
        # Try to avoid downloading the content unless we need it
        fileobj = None

        # FIXME: Some error modes not handled here, see
        # https://github.com/calpaterson/quarchive/issues/11
        if content_type_header is not None:
            content_type, parameters = cgi.parse_header(content_type_header)
            # charset = parameters.get("charset")

            # If we were given something we don't recognise, infer the content type
            if content_type not in known_content_types():
                old_content_type = content_type
                fileobj = download_file(bucket, str(body_uuid))
                content_type = infer_content_type(fileobj)
                log.info(
                    "inferred %s for %s (instead of %s)",
                    content_type,
                    url.to_url(),
                    old_content_type,
                )
        else:
            # No Content-Type, so infer it
            fileobj = download_file(bucket, str(body_uuid))
            content_type = infer_content_type(fileobj)
            log.info("inferred %s for %s (none provided)", content_type, url.to_url())

        if content_type != "text/html":
            log.info(
                "%s (%s) has wrong content type: %s - skipping",
                url.to_url(),
                crawl_uuid,
                content_type,
            )
            return

        # If we didn't download it before, we should now
        if fileobj is None:
            fileobj = download_file(bucket, str(body_uuid))

        # FIXME: charset should be handed to extract_full_text_from_html
        text = extract_full_text_from_html(fileobj)

        fulltext_obj = FullText(
            url_uuid=sqla_url_obj.url_uuid,
            crawl_uuid=crawl_uuid,
            inserted=datetime.utcnow().replace(tzinfo=timezone.utc),
            full_text=text,
            tsvector=func.to_tsvector(text),
        )
        sesh.add(fulltext_obj)
        sesh.commit()
        log.info("indexed %s (%s)", url.to_url(), crawl_uuid)


def crawl_url(session: Session, crawl_uuid: UUID, url: str) -> None:
    client = get_client()
    bucket = get_response_body_bucket()
    with contextlib.closing(get_session_cls()) as session:
        url_uuid = upsert_url(session, url)
        crawl_request = CrawlRequest(
            crawl_uuid=crawl_uuid,
            url_uuid=url_uuid,
            requested=datetime.utcnow().replace(tzinfo=timezone.utc),
            got_response=False,
        )
        session.add(crawl_request)

        try:
            response = client.get(url, stream=True, timeout=REQUESTS_TIMEOUT)
        except requests.exceptions.RequestException as e:
            log.warning("unable to request %s - %s", url, e)
            session.commit()
            return
        log.info("crawled %s", url)

        crawl_request.got_response = True

        body_uuid = uuid4()
        # Typeshed type looks wrong, proposed a fix in
        # https://github.com/python/typeshed/pull/3610
        headers = cast(requests.structures.CaseInsensitiveDict, response.headers)
        session.add(
            CrawlResponse(
                crawl_uuid=crawl_uuid,
                body_uuid=body_uuid,
                headers=dict(headers.lower_items()),
                status_code=response.status_code,
            )
        )

        # Otherwise we'll get the raw stream (often gzipped) rather than the
        # raw payload (usually html bytes)
        response.raw.decode_content = True

        upload_file(bucket, response.raw, str(body_uuid))

        session.commit()


# fmt: off
# Search
...
# fmt: on

LEXER_REGEX = re.compile(r"[0-9A-z]+|['\"]")


class Term(metaclass=ABCMeta):
    @abstractmethod
    def render(self) -> str:
        pass


class Literal(Term):
    word: str

    def __init__(self, word: str) -> None:
        self.word = word

    def render(self):
        return "'" + self.word + "'"


class CompoundTerm(Term, metaclass=ABCMeta):
    @abstractmethod
    def append(self, term: Term) -> None:
        pass


class Conjunction(CompoundTerm):
    elems: MutableSequence[Term]

    def __init__(self) -> None:
        self.elems = []

    def append(self, term: Term) -> None:
        self.elems.append(term)

    def render(self) -> str:
        return " & ".join(e.render() for e in self.elems)


class Quote(CompoundTerm):
    quotes = {"'", '"'}

    literals: MutableSequence[Term]
    parent: CompoundTerm
    quote_char: str

    def __init__(self, parent: CompoundTerm) -> None:
        self.literals = []
        self.parent = parent

    def append(self, literal: Term) -> None:
        self.literals.append(literal)

    def render(self) -> str:
        return " <-> ".join(l.render() for l in self.literals)


def parse_search_str(search_str: str) -> str:
    """Parse a web search string into tquery format"""
    token_iterator = LEXER_REGEX.finditer(search_str)

    current_term: CompoundTerm = Conjunction()
    base_term = current_term
    for match_obj in token_iterator:
        token = match_obj.group(0)
        log.debug("token = '%s'", token)
        log.debug("base_term = '%s'", base_term.render())
        # FIXME: Need to handle apostrophe
        if token in Quote.quotes:
            if isinstance(current_term, Quote):
                current_term = current_term.parent
            else:
                quote = Quote(current_term)
                current_term.append(quote)
                current_term = quote
        else:
            term = Literal(token)
            current_term.append(term)

    return base_term.render()


# fmt: off
# Entry points
...
# fmt: on


def message_processor() -> None:
    logging.basicConfig(level=logging.INFO)
    adapted_processor.run()


def main() -> None:
    app = init_app()
    logging.basicConfig(level=logging.INFO)
    app.run()


@click.command()
@click.argument("user_uuid", type=click.UUID)
@click.argument("json_file", type=click.File("rb"))
@click.option(
    "--as-of",
    type=click.DateTime(),
    default=lambda: datetime.strftime(datetime.utcnow(), "%Y-%m-%d %H:%M:%S"),
)
def pinboard_import(user_uuid: UUID, json_file, as_of: datetime):
    as_of_dt = as_of.replace(tzinfo=timezone.utc)
    log.info("as of: %s", as_of_dt)

    def pinboard_bookmark_to_bookmark(mapping: Mapping[str, str]) -> Bookmark:
        return Bookmark(
            url=mapping["href"],
            title=mapping["description"],
            description=mapping["extended"],
            updated=as_of_dt,
            created=isoparse(mapping["time"]),
            unread=True if mapping["toread"] == "yes" else False,
            deleted=False,
        )

    logging.basicConfig(level=logging.INFO)
    document = json.load(json_file)
    keys = set(itertools.chain(*[item.keys() for item in document]))
    log.info("keys = %s", keys)
    app = init_app()
    with app.app_context():
        generator = (pinboard_bookmark_to_bookmark(b) for b in document)
        changed = merge_bookmarks(db.session, user_uuid, generator)
        log.info("changed %d bookmarks", len(changed))
        db.session.commit()
