from dataclasses import dataclass, asdict as dataclass_as_dict
import re
import contextlib
from datetime import datetime, timezone, timedelta
from functools import wraps, lru_cache
import itertools
import logging
from uuid import uuid4, UUID
from typing import Mapping, Set, Any, Optional, Callable, Iterable, cast, Tuple, TypeVar
from os import environ
from urllib.parse import urlsplit, urlunsplit
import json

import click
import boto3
import requests
from werkzeug import exceptions as exc
from werkzeug.urls import url_encode
from dateutil.parser import isoparse
from babel.dates import format_timedelta
from sqlalchemy import Column, ForeignKey, types as satypes, func, create_engine
from sqlalchemy.orm import (
    relationship,
    RelationshipProperty,
    Session,
    sessionmaker,
    scoped_session,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, insert as pg_insert, JSONB
from sqlalchemy.ext.declarative import declarative_base
from flask_sqlalchemy import SQLAlchemy
import flask
from flask_cors import CORS

log = logging.getLogger("quarchive")

# fmt: off
# Config loading
...
# fmt: on

REQUIRED_CONFIG_KEYS = {
    "QM_SQL_URL",
    "QM_PASSWORD",
    "QM_SECRET_KEY",
}


def load_config() -> None:
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


@dataclass(frozen=True)
class Bookmark:
    url: str

    title: str
    description: str

    created: datetime
    updated: datetime

    unread: bool
    deleted: bool

    def merge(self, other: "Bookmark") -> "Bookmark":
        more_recent: "Bookmark" = sorted(
            (self, other),
            key=lambda b: (b.updated, len(b.title) + len(b.description)),
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
        )

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


# fmt: off
# DB layer
...
# fmt: on

Base: Any = declarative_base()


class SQLAUrl(Base):
    __tablename__ = "urls"

    # Synthetic key for foreign references
    url_uuid = Column(PGUUID(as_uuid=True), nullable=False, index=True, unique=True)

    # The actual url
    scheme = Column(satypes.String, nullable=False, index=True, primary_key=True)
    netloc = Column(satypes.String, nullable=False, index=True, primary_key=True)
    path = Column(satypes.String, nullable=False, index=True, primary_key=True)
    query = Column(satypes.String, nullable=False, index=True, primary_key=True)
    fragment = Column(satypes.String, nullable=False, index=True, primary_key=True)


class SQLABookmark(Base):
    __tablename__ = "bookmarks"

    url_uuid = Column(
        PGUUID(as_uuid=True), ForeignKey("urls.url_uuid"), primary_key=True
    )

    title = Column(satypes.String, nullable=False, index=True)
    description = Column(satypes.String, nullable=False, index=True)

    created = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    updated = Column(satypes.DateTime(timezone=True), nullable=False, index=True)

    unread = Column(satypes.Boolean, nullable=False, index=True)
    deleted = Column(satypes.Boolean, nullable=False, index=True)

    url_obj: RelationshipProperty = relationship(
        SQLAUrl, uselist=False, backref="bookmark_objs"
    )


class CrawlRequest(Base):
    __tablename__ = "crawl_requests"

    crawl_uuid = Column(PGUUID(as_uuid=True), primary_key=True)
    url_uuid = Column(PGUUID(as_uuid=True), ForeignKey("urls.url_uuid"), index=True)
    requested = Column(satypes.DateTime(timezone=True), nullable=False, index=True)
    got_response = Column(satypes.Boolean, index=True)


class CrawlResponse(Base):
    __tablename__ = "crawl_responses"

    crawl_uuid = Column(
        PGUUID(as_uuid=True), ForeignKey("crawl_requests.crawl_uuid"), primary_key=True
    )
    body_uuid = Column(PGUUID(as_uuid=True), unique=True, nullable=False)
    headers = Column(JSONB(), nullable=False, index=True)
    status_code = Column(satypes.SmallInteger, nullable=False, index=True)

    request_obj: RelationshipProperty = relationship(
        CrawlRequest, uselist=False, backref="response_obj"
    )


def get_bookmark_by_url(session: Session, url: str) -> Optional[Bookmark]:
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
        )
        .first()
    )
    if sqla_bookmark is None:
        return None
    else:
        return bookmark_from_sqla(url, sqla_bookmark)


def get_bookmark_by_url_uuid(session, url_uuid: UUID) -> Optional[Bookmark]:
    sqla_bookmark = session.query(SQLABookmark).get(url_uuid)
    if sqla_bookmark is None:
        return None
    url = URL.from_sqla_url(sqla_bookmark.url_obj).to_url()
    return bookmark_from_sqla(url, sqla_bookmark)


def upsert_url(session, url) -> UUID:
    scheme, netloc, path, query, fragment = urlsplit(url)
    proposed_uuid = uuid4()
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


def set_bookmark(session: Session, bookmark: Bookmark) -> UUID:
    scheme, netloc, path, query, fragment = urlsplit(bookmark.url)
    proposed_uuid = uuid4()
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
    )
    bookmark_upsert_stmt = bookmark_insert_stmt.on_conflict_do_update(
        index_elements=["url_uuid"],
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


def merge_bookmarks(session, recieved_bookmarks: Set[Bookmark]) -> Set[Bookmark]:
    changed_bookmarks: Set[Bookmark] = set()
    for recieved in recieved_bookmarks:
        existing = get_bookmark_by_url(session, url=recieved.url)
        if existing is None:
            # If it doesn't exist in our db, we create it - but client already
            # knows
            set_bookmark(session, recieved)
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
                set_bookmark(session, merged)
            else:
                log.debug("no change to %s", recieved)
            if merged != recieved:
                # If what we have is different from what were sent, we need to
                # tell the client
                changed_bookmarks.add(merged)
    return changed_bookmarks


def all_bookmarks(session) -> Iterable[Bookmark]:
    query = session.query(SQLABookmark)
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


def sign_in_required(handler: V) -> V:
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if "username" not in flask.session:
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
            api_key = flask.request.headers["X-QM-API-Key"]
        except KeyError:
            flask.current_app.logger.info("no api credentials")
            return flask.jsonify({"error": "no api credentials"}), 400
        if (
            username == "calpaterson"
            and api_key == flask.current_app.config["PASSWORD"]
        ):
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
    query = db.session.query(SQLABookmark).filter(~SQLABookmark.deleted)

    if "q" in flask.request.args:
        search_query = flask.request.args["q"]
        combined_tsvector = func.to_tsvector(SQLABookmark.title).op("||")(
            func.to_tsvector(SQLABookmark.description)
        )
        query = query.filter(
            combined_tsvector.op("@@")(func.websearch_to_tsquery(search_query))
        )

    sqla_objs = (
        query.order_by(SQLABookmark.created.desc()).offset(offset).limit(page_size)
    )

    prev_page_exists = page > 1
    next_page_exists: bool = db.session.query(
        query.order_by(SQLABookmark.created.desc()).offset(offset + page_size).exists()
    ).scalar()

    bookmarks = []
    for sqla_obj in sqla_objs:
        url_obj: SQLAUrl = sqla_obj.url_obj
        url = URL.from_sqla_url(sqla_obj.url_obj)
        bookmarks.append((url, bookmark_from_sqla(url.to_url(), sqla_obj)))
    return flask.make_response(
        flask.render_template(
            "index.j2",
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
    return flask.make_response(flask.render_template("create_or_edit_bookmark.j2",))


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
    url_uuid = set_bookmark(db.session, bookmark)
    db.session.commit()
    flask.flash("Bookmarked: %s" % bookmark.url)
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
        bookmark = get_bookmark_by_url_uuid(db.session, url_uuid)
        # FIXME: what if it doesn't exist?
        return flask.make_response(
            flask.render_template(
                "create_or_edit_bookmark.j2", url_uuid=url_uuid, bookmark=bookmark
            )
        )
    else:
        form = flask.request.form
        fields = set(["title", "description", "unread", "deleted"])
        bookmark = get_bookmark_by_url_uuid(db.session, url_uuid)
        if bookmark is None:
            raise exc.NotFound()
        bookmark_fields = dataclass_as_dict(bookmark)
        bookmark_fields["title"] = form["title"]
        bookmark_fields["description"] = form["description"]
        bookmark_fields["unread"] = "unread" in form
        bookmark_fields["deleted"] = "deleted" in form
        bookmark_fields["updated"] = datetime.utcnow().replace(tzinfo=timezone.utc)
        final_bookmark = Bookmark(**bookmark_fields)
        set_bookmark(db.session, final_bookmark)
        db.session.commit()
        flask.flash("Edited: %s" % bookmark.url)
        return flask.make_response("ok")


@blueprint.route("/url/<uuid:url_uuid>")
@sign_in_required
def view_url(url_uuid: UUID) -> Tuple[flask.Response, int]:
    url_obj = db.session.query(SQLAUrl).filter(SQLAUrl.url_uuid == url_uuid).first()
    if url_obj is None:
        raise exc.NotFound()
    else:
        return flask.make_response(
            flask.render_template("url.j2", url=URL.from_sqla_url(url_obj))
        )


@blueprint.route("/netloc/<string:netloc>")
@sign_in_required
def view_netloc(netloc: str) -> Tuple[flask.Response, int]:
    url_objs = db.session.query(SQLAUrl).filter(SQLAUrl.netloc == netloc)
    if url_objs.count() == 0:
        raise exc.NotFound()
    else:
        return flask.make_response(
            flask.render_template("netloc.j2", netloc=netloc, url_objs=url_objs)
        )


@blueprint.route("/sign-in", methods=["GET", "POST"])
def sign_in() -> flask.Response:
    if flask.request.method == "GET":
        return flask.make_response(flask.render_template("sign-in.j2"))
    else:
        username = flask.request.form.get("username")
        password = flask.request.form.get("password")
        if password == flask.current_app.config["PASSWORD"]:
            flask.current_app.logger.info("successful sign in")
            flask.session["username"] = "username"

            # Make it last for 31 days
            flask.session.permanent = True

            # flask.redirect("/", code=303)
            response = flask.make_response("Redirecting...", 303)
            response.headers["Location"] = "/"
            return response
        else:
            flask.current_app.logger.info("unsuccessful sign in")
            raise exc.BadRequest()


@blueprint.route("/ok")
def ok() -> flask.Response:
    return flask.json.jsonify({"ok": True})


@blueprint.route("/sync", methods=["POST"])
@api_key_required
def sync() -> flask.Response:
    body = flask.request.json
    recieved_bookmarks: Set[Bookmark] = set(
        Bookmark.from_json(item) for item in body["bookmarks"]
    )

    changed_bookmarks = merge_bookmarks(db.session, recieved_bookmarks)
    db.session.commit()
    if "full" in flask.request.args:
        response_bookmarks = all_bookmarks(db.session)
    else:
        response_bookmarks = changed_bookmarks
    return flask.json.jsonify({"bookmarks": [b.to_json() for b in response_bookmarks]})


def init_app(db_uri: str, password: str, secret_key: str) -> flask.Flask:
    app = flask.Flask("quarchive")
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # By default Postgres will consult the locale to decide what timezone to
    # return datetimes in.  We want UTC in all cases.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"options": "-c timezone=utc"}
    }

    app.config["PAGE_SIZE"] = 30
    app.config["PASSWORD"] = password
    db.init_app(app)
    cors.init_app(app)
    app.register_blueprint(blueprint)

    @app.template_filter("relativetime")
    def relativetime(dt: datetime):
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        td = dt - now
        return format_timedelta(td, add_direction=True, locale="en_GB")

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


@lru_cache(1)
def get_session_cls() -> Session:
    session_factory = sessionmaker(bind=create_engine(environ["QM_SQL_URL"]))
    Session = scoped_session(session_factory)
    return Session


@lru_cache(1)
def get_client() -> requests.Session:
    return requests.Session()


@lru_cache(1)
def get_s3():
    return boto3.resource("s3")


@lru_cache(1)
def get_response_body_bucket():
    return get_s3().Bucket("test_bucket")


def crawl_url(crawl_uuid: UUID, url: str):
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
        response = client.get(url, stream=True)
        crawl_request.got_response = True

        body_uuid = uuid4()
        # Typeshed type looks wrong, proposed a fix in https://github.com/python/typeshed/pull/3610
        headers = cast(requests.structures.CaseInsensitiveDict, response.headers)
        session.add(
            CrawlResponse(
                crawl_uuid=crawl_uuid,
                body_uuid=body_uuid,
                headers=dict(headers.lower_items()),
                status_code=response.status_code,
            )
        )

        bucket.upload_fileobj(response.raw, Key=str(body_uuid))
        session.commit()


# fmt: off
# Entry points
...
# fmt: on


def main() -> None:
    app = init_app(
        environ["QM_SQL_URL"], environ["QM_PASSWORD"], environ["QM_SECRET_KEY"]
    )
    logging.basicConfig(level=logging.INFO)
    app.run()


@click.command()
@click.argument("json_file", type=click.File("rb"))
def pinboard_import(json_file):
    def pinboard_bookmark_to_bookmark(mapping: Mapping[str, str]) -> Bookmark:
        return Bookmark(
            url=mapping["href"],
            title=mapping["description"],
            description=mapping["extended"],
            updated=datetime.utcnow().replace(tzinfo=timezone.utc),
            created=isoparse(mapping["time"]),
            unread=True if mapping["toread"] == "yes" else False,
            deleted=False,
        )

    logging.basicConfig(level=logging.INFO)
    document = json.load(json_file)
    keys = set(itertools.chain(*[item.keys() for item in document]))
    log.info("keys = %s", keys)
    app = init_app(
        environ["QM_SQL_URL"], environ["QM_PASSWORD"], environ["QM_SECRET_KEY"]
    )
    with app.app_context():
        for pinboard_bookmark in document:
            set_bookmark(db.session, pinboard_bookmark_to_bookmark(pinboard_bookmark))
        db.session.commit()
